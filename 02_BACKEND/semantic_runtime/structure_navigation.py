"""Template-output coordinates and server-issued READ handles; research injection only."""
from copy import copy,deepcopy
from types import MethodType
import json,hashlib,threading
from . import legal_navigation as previous
from lawrag.core.legal_coordinate import LegalCoordinate,parse_label,find_coordinates

# Validated stored units of one immutable generation; read-only after construction.
_UNITS_CACHE={};_UNITS_LOCK=threading.Lock()

def stored_units(store):
    key=(store.manifest['generation_id'],store.manifest['store_sha256'])
    with _UNITS_LOCK:
        if key in _UNITS_CACHE:return _UNITS_CACHE[key]
    units={}
    for row in store.db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit ORDER BY document_id,CAST(unit_id AS INTEGER)'):
        raw=json.loads(row['json']);parent=str(row['parent_id']) if row['parent_id'] is not None else None
        if raw.get('parent') is not None and str(raw['parent'])!=parent:raise ValueError('stored structure parent mismatch')
        units[(row['document_id'],str(row['unit_id']))]={**raw,'parent':parent,'raw_structure':raw}
    for (did,uid),unit in units.items():
        if unit['parent'] is not None and (did,unit['parent']) not in units:raise ValueError('stored parent missing')
        seen=set();cur=uid
        while (did,cur) in units:
            if cur in seen:raise ValueError('stored structure cycle')
            seen.add(cur);cur=units[(did,cur)]['parent']
    with _UNITS_LOCK:
        return _UNITS_CACHE.setdefault(key,units)


def bind_structure(matcher,store):
    """Copy actual stored fields. Do not identify articles from source heading/body."""
    bound=copy(matcher);bound.structure_binding={'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],'authority':'source_unit.json'}
    # Shared validated units; callers that derive bindings copy before writing.
    bound.units=stored_units(store)
    for name in ('_unit_sources','starts'):
        method=getattr(matcher,name)
        if getattr(method,'__self__',None) is matcher:setattr(bound,name,MethodType(method.__func__,bound))
    return bound


def stored_coordinate(units,did,uid,seen=None):
    seen=set() if seen is None else seen
    if uid in seen:raise ValueError('structure cycle')
    seen.add(uid);u=units[(did,uid)];raw=u.get('raw_structure',u)
    value=raw.get('legal_coordinate')
    if isinstance(value,dict) and value.get('surface'):
        chain=value.get('chain',[]);subs=tuple(x.get('sub') for x in chain)
        parsed=LegalCoordinate(value['unit'],value['n'],sub=value.get('sub'),dash=value.get('dash'),chain=tuple((x['unit'],x['n']) for x in chain),chain_subs=subs if any(x is not None for x in subs) else ())
        if parsed.as_dict()==value:return parsed
        raise ValueError('stored legal_coordinate disagrees with shared coordinate contract')
    # Older source generations retain surface/ordinal + scope/key but no full object.
    # Reuse ingestion's shared label grammar; never inspect the article title/body.
    component=parse_label(raw.get('surface',''))
    if component is None:return None
    if component.unit in ('항','호','목'):
        parent=u['parent']
        if parent is None:return None
        base=stored_coordinate(units,did,parent,seen)
        return base.append_part(component) if base and base.unit=='조' else None
    return component


class BoundSession(previous.LegalSession):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not hasattr(self.m,'structure_binding'):raise ValueError('stored structure adapter required')
        self.read_handles={};self.handle_by_source={};self.offered_handles=set();self.route_actions=[]
        # inherited_navigation.bind_structure precomputes every stored coordinate once per generation.
        computed=getattr(self.m,'stored_coordinates',None)
        if computed is None:
            computed={key:stored_coordinate(self.m.units,*key) for key in self.m.units}
        self.structure_coordinates={key:c for key,c in computed.items() if c and key[0] in self.scope}
    def source_card(self,sid):
        card=super().source_card(sid)
        if sid not in self.handle_by_source:
            handle='RH'+str(len(self.read_handles)+1);source=self.t.sources[sid]
            self.handle_by_source[sid]=handle;self.read_handles[handle]={'source_id':sid,'document_id':source['document_id'],'text_sha256':source['text_sha256'],'binding':deepcopy(self.m.structure_binding)}
        handle=self.handle_by_source[sid]
        return {**card,'read_handle':handle,'read_action':{'tool':'READ','args':{'source_id':handle}}}
    def structure_card(self,key):
        card=super().structure_card(key);did,uid=self.structure_keys[key];u=self.m.units[(did,uid)]
        return {**card,'coordinate_scope':u.get('coordinate_scope'),'coordinate_key':u.get('coordinate_key'),'legal_coordinate':u.get('legal_coordinate'),'read_action':None,'read_instruction':'FIND_ARTICLE or LIST returns a server-issued read_handle; structure IDs cannot be READ source_id.'}
    def query_coordinates(self,locator):
        text=previous.normalized(locator)[0]
        # Omitted 제 is normalized only using a surface already present in stored structure.
        for c in sorted(self.structure_coordinates.values(),key=lambda c:-len(c.canonical_surface())):
            label=c.canonical_surface();bare=label.removeprefix('제')
            if bare==label:continue
            start=text.find(bare)
            if start>=0 and (start==0 or (not text[start-1].isdigit() and text[start-1]!='제')):text=text[:start]+'제'+text[start:]
        return [x.coordinate for x in find_coordinates(text)]
    def find_article(self,locator,document_id='',branch='any',offset=0):
        if not isinstance(locator,str) or len(locator)>500:raise ValueError('bounded locator required')
        if document_id and document_id not in self.scope:raise ValueError('document outside scope')
        if branch not in ('body','appendix','any'):raise ValueError('unknown branch')
        wanted={c.canonical_surface() for c in self.query_coordinates(locator)}
        if not wanted:return {'status':'UNRESOLVED','reason':'NO_STORED_COORDINATE_MATCH','items':[],'content_read':False}
        matches=[];unresolved=[]
        for (did,uid),c in self.structure_coordinates.items():
            if document_id and did!=document_id or c.canonical_surface() not in wanted:continue
            u=self.m.units[(did,uid)];scope=u.get('coordinate_scope');key=u.get('coordinate_key')
            if not scope or not key:unresolved.append({'unit_id':uid,'document_id':did,'reason':'STORED_COORDINATE_SCOPE_OR_KEY_MISSING'});continue
            if branch=='body' and scope!='body' or branch=='appendix' and scope!='addendum':continue
            targets=[sid for sid in self.m._unit_sources(did,uid) if sid in self.metadata]
            if not targets:unresolved.append({'unit_id':uid,'document_id':did,'reason':'STRUCTURE_SOURCE_UNRESOLVED'});continue
            for sid in targets:matches.append({'source_id':sid,'document_id':did,'unit_id':uid,'coordinate_scope':scope,'coordinate_key':key,'coordinate':c.as_dict(),'family':u.get('family'),'ordinal':u.get('ordinal'),'parent':u['parent']})
        matches.sort(key=lambda x:(x['document_id'],int(x['unit_id']),x['source_id']));p=self.page(matches,offset)
        p['items']=[{**self.source_card(x['source_id']),'structure_match':x,'read_extent':'bound source article; selected paragraph coordinates preserved'} for x in p['items']]
        return {**p,'status':'NEEDS_SELECTION' if len(matches)>1 else 'MATCHES' if matches else 'UNRESOLVED' if unresolved else 'EMPTY','unresolved':unresolved,'content_read':False,'binding':self.m.structure_binding,'authority':'stored structure coordinate values; no heading classification'}
    def context(self):
        # Bypass ADR0446 heading-regex route suggestions; all coordinate suggestions use stored values.
        data=previous.StructuredSession.context(self)
        data['tools']=deepcopy(previous.TOOLS)
        data['tools']['READ']='{source_id:read_handle,unit_id:"",offset:0}: source_id에는 서버가 제시한 RH 읽기 핸들만. D/A/S/조번호를 만들지 말고 read_action 그대로 선택.'
        data['tools']['FIND_ARTICLE']='{locator,document_id:"",branch:body|appendix|any,offset:0}: 구조화 결과의 좌표·계층·scope/key 조회. 제목/본문을 재분류하지 않음.'
        data['request_contract']={**self.contract,'pending':self.pending(),'search_receipts':self.search_mode_receipts}
        self.route_actions=[];needed=self.prerequisite_pending()
        if needed:
            ids=sorted(s for s,v in self.metadata.items() if v['document_id']==needed);page=self.page(ids,0);page['items']=[self.source_card(s) for s in page['items']];data['prerequisite_candidates']=page
            self.route_actions=[x['read_action'] for x in page['items']]
        else:
            for row in self.last:
                result=row.get('result',{})
                if row.get('status')!='OK':continue
                if row['tool']=='OPEN_TERM':self.route_actions.append({'tool':'LIST','args':{'term_ids':[row['args']['term_id']],'match':'any'}})
                if row['tool'] in ('LIST','GREP','SEARCH','LEGAL_SEARCH','FIND_ARTICLE'):
                    self.route_actions.extend(x['read_action'] for x in result.get('items',[]) if x.get('read_action'))
                    self.route_actions.extend(result.get('recovery_actions',[]))
        suggestions=list(self.route_actions)
        if self.query_coordinates(self.question):
            docs=[d for d in self.scope if previous.normalized(self.m.documents[d])[0] in previous.normalized(self.question)[0]]
            suggestions.append({'tool':'FIND_ARTICLE','args':{'locator':self.question,'document_id':docs[0] if len(docs)==1 else '', 'branch':'appendix' if '부칙' in self.question else 'body' if '본문' in self.question else 'any'}})
        data['next_actions']=suggestions[:12];data['structure_binding']=self.m.structure_binding
        data['route_policy']='OPEN_TERM -> linked LIST; matched source -> READ; empty scoped LIST -> relax optional document filter inside authorized scope. Incomplete stop remains available.'
        if len(json.dumps(data,ensure_ascii=False))>self.limits['context_chars']:raise ValueError('structure context exceeds budget')
        return data
    def response_schema(self):
        schema=super().response_schema();self.offered_handles=set(list(self.read_handles)[-64:])
        options=[]
        for item in schema['properties']['actions']['items']['anyOf']:
            tool=item['properties']['tool']['enum'][0]
            if tool=='READ':
                if not self.offered_handles:continue
                item['properties']['args']['properties']['source_id']={'type':'string','enum':sorted(self.offered_handles),'description':'Copy a server-issued RH read_handle, not article/document/structure IDs.'}
            options.append(item)
        # Executable transition proposals, constrained by actual preceding tool receipts.
        if self.route_actions:
            routed=[]
            for a in self.route_actions[:12]:
                tool=a['tool'];args=deepcopy(previous.ARGS[tool]);props=args['properties']
                for key,val in a['args'].items():
                    if isinstance(val,list):props[key]={'type':'array','items':{'type':'string','enum':val},'minItems':len(val),'maxItems':len(val)}
                    else:props[key]={'type':'integer' if isinstance(val,int) else 'string','enum':[val]}
                args['required']=list(a['args']);routed.append(previous.action_schema(tool,args))
            stop=previous.action_schema('STOP',deepcopy(previous.ARGS['STOP']));stop['properties']['args']['properties']['status']=previous.enum('incomplete');routed.append(stop)
            options=self.wire(routed)
        schema['properties']['actions']['items']['anyOf']=options
        return schema
    def execute(self,tool,a):
        if tool=='READ':
            handle=a.get('source_id')
            if handle not in self.offered_handles or handle not in self.read_handles:raise ValueError('READ_HANDLE_REQUIRED: use currently offered RH read_action')
            binding=self.read_handles[handle];sid=binding['source_id']
            if binding['document_id'] not in self.scope or self.t.sources[sid]['text_sha256']!=binding['text_sha256'] or binding['binding']!=self.m.structure_binding:raise ValueError('stale read handle')
            a={**a,'source_id':sid}
        result=super().execute(tool,a)
        if tool=='LIST' and result.get('total')==0:
            repaired={k:v for k,v in a.items() if k not in ('document_id','structure_id','offset','facet_offset')}
            result['recovery_actions']=[]
            if repaired.get('term_ids') and (a.get('document_id') or a.get('structure_id')):result['recovery_actions'].append({'tool':'LIST','args':repaired})
            for tid in a.get('term_ids',[]):
                label=self.t.terms[tid]['label'];result['recovery_actions'].append({'tool':'LEGAL_SEARCH','args':{'query':label,'mode':'tokens'}})
        return result

class BoundAgent(previous.RoutedAgent):
    session_type=BoundSession
