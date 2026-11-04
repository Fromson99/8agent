"""Union independent stored entry paths before review; scoped typed catalogue."""
from copy import deepcopy
from collections import defaultdict
import json,re,time,sqlite3
import threading
from types import MappingProxyType
from .team_scope import generation_key
from .contracts import digest
from . import inherited_navigation as previous
from . import folder_navigation as folders
legal=previous.previous.previous
ARGS=deepcopy(legal.ARGS)
ARGS.update({'CANDIDATES':legal.obj({'offset':legal.INT},[]),
 'DISMISS':legal.obj({'read_handles':{'type':'array','items':legal.STR,'minItems':1,'maxItems':16},'reason':legal.STR},['read_handles','reason']),
 'CATALOG':legal.obj({'offset':legal.INT,'category':legal.enum('all','internal','external','unknown')},[])})
SCHEMA=deepcopy(legal.SCHEMA);SCHEMA['properties']['actions']['items']['anyOf']=[legal.action_schema(k,a) for k,a in ARGS.items()]
SYSTEM=legal.SYSTEM+'''\n현재는 복수 진입점 후보를 먼저 합치는 탐색이다. CANDIDATES의 모든 초기 후보 페이지를 먼저 확인한다. 각 후보의 문서명·조문 표제와 entry_ids를 보고 READ하거나, 적용 대상/자료 성격이 명백히 다른 후보만 DISMISS로 제외 이유를 남긴다. 내용 확인이 필요한 경우 메타데이터만 보고 제외하지 않는다. READ 후 JUDGE adopted/excluded를 해야 검토 완료다. 서로 다른 진입점의 근거를 함께 검토하고, 조건·예외·명시 참조의 결론을 각 claim에 빠짐없이 기록하라. 한 근거가 충분해 보여도 pending_candidates가 남으면 sufficient가 거절된다. 관계 경로는 의미상 동일성의 보증이 아니다.''' 


def bind_structure(matcher,store,origin_projection=None):
    bound = folders.bind_catalogue(previous.bind_structure(matcher,store),store,origin_projection)
    key = (generation_key(store), digest(origin_projection),
           tuple(sorted(getattr(matcher,'projection_aliases',{}).items())), id(matcher.sources))
    with _PREPARED_LOCK:
        value = _PREPARED.get(key)
        if value is None:
            units = FrozenDict({k: freeze(v) for k,v in bound.units.items()})
            by_document = defaultdict(list)
            for key_unit in units:by_document[key_unit[0]].append(key_unit)
            sources = defaultdict(list)
            for ordinal,(sid,source) in enumerate(matcher.sources.items()):
                sources[source['document_id']].append((ordinal,sid))
            value = {'units':units, 'unit_index':MappingProxyType({d:tuple(v) for d,v in by_document.items()}),
                     'source_index':MappingProxyType({d:tuple(v) for d,v in sources.items()}),
                     'coordinates':MappingProxyType(dict(bound.stored_coordinates)),
                     'validated':frozenset(), 'lock':threading.Lock()}
            _PREPARED.clear()
            _PREPARED[key] = value
        bound.units = value['units']
        bound.prepared_structure = value
        bound.stored_coordinates = value['coordinates']
        bound._structure_store = store
        # A bound matcher owns successful selection reuse; never share mutable request results.
        bound._selection_resolution_cache = None
    return bound


_PREPARED = {}
_PREPARED_LOCK = threading.Lock()


class FrozenDict(dict):
    def _deny(self,*args,**kwargs):raise TypeError('generation data is immutable')
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=_deny
    def __deepcopy__(self,memo):return {deepcopy(k,memo):deepcopy(v,memo) for k,v in self.items()}


class FrozenList(list):
    def _deny(self,*args,**kwargs):raise TypeError('generation data is immutable')
    __setitem__=__delitem__=append=extend=insert=pop=remove=clear=reverse=sort=__iadd__=__imul__=_deny
    def __deepcopy__(self,memo):return [deepcopy(v,memo) for v in self]


def freeze(value, memo=None, active=None):
    # Stored fields and raw_structure often share the same lists/dicts.
    # Freeze each shared object once within one unit, without cross-unit lifetime.
    if not isinstance(value, (dict, list)):return value
    memo = {} if memo is None else memo
    active = set() if active is None else active
    identity = id(value)
    if identity in active:raise ValueError('cyclic generation metadata')
    if identity in memo:return memo[identity]
    active.add(identity)
    try:
        frozen = (FrozenDict({k:freeze(v,memo,active) for k,v in value.items()})
                  if isinstance(value,dict) else FrozenList(freeze(v,memo,active) for v in value))
        memo[identity] = frozen
        return frozen
    finally:active.remove(identity)


def validate_structure(matcher, scope):
    """Cache successful checks only for the final immutable binding; mutable adapters rescan."""
    if hasattr(matcher,'validate_structure'):
        return matcher.validate_structure(scope)
    from .legal_agent.errors import ContractError
    prepared = getattr(matcher,'prepared_structure',None)
    reusable = prepared is not None and matcher.units is prepared['units']
    guard = prepared['lock'] if reusable else threading.Lock()
    with guard:
        pending = set(scope) - prepared['validated'] if reusable else set(scope)
        done=set();checked=0
        keys = (key for d in sorted(pending) for key in prepared['unit_index'].get(d,())) if reusable else (
            key for key in matcher.units if key[0] in pending)
        for did,uid in keys:
            span=matcher.units[(did,uid)].get('span')
            if (not isinstance(span,list) or len(span)!=2 or any(type(v) is not int for v in span)
                or span[0]<0 or span[1]<span[0]):raise ContractError('stored structure span missing/invalid')
            seen=set();cur=uid
            while cur is not None and (did,str(cur)) not in done:
                cur=str(cur);key=(did,cur)
                if cur in seen or key not in matcher.units:raise ContractError('missing/cyclic stored parent')
                seen.add(cur);cur=matcher.units[key]['parent']
            done.update((did,u) for u in seen);checked+=1
        if reusable:prepared['validated'] = prepared['validated'] | pending
        return checked


RESOLVED_REFERENCES = {'RESOLVED', 'EXACT_NAMED_DOCUMENT_ARTICLE', 'EXACT_SAME_DOCUMENT_ARTICLE',
                       'EXACT_SAME_ARTICLE_PROVISION', 'EXACT_CONTINUED_PROVISION', 'EXACT_SAME_DOCUMENT_PROVISION',
                       'EXACT_NAMED_DOCUMENT_ANNEX', 'EXACT_SAME_DOCUMENT_ANNEX', 'OFFICIAL_DELEGATION',
                       'EXACT_COMPLETE_COORDINATE', 'EXACT_FRAME_PATH', 'EXACT_DETERMINISTIC_RANGE'}


def reference_resolved(value):
    return value in RESOLVED_REFERENCES


def catalogue_request(question):
    """Compatibility hook: the navigation model selects catalogue operations."""
    return None


def document_listing(matcher,scope,category):
    if category not in ('all','internal','external','unknown'):raise ValueError('invalid catalogue category')
    allowed=set(matcher.tools.validate_scope(scope));records=[matcher.document_catalogue[d] for d in sorted(allowed)];items=[deepcopy(r) for r in records if category=='all' or r['category']==category]
    unknown=sum(r['category']=='unknown' for r in records)
    return {'documents':items,'total':len(items),'category':category,'scope_document_count':len(allowed),'unknown_category_count':unknown,'classification_complete':unknown==0,'scope_note':'selected generation and authorized document scope only'}


class MultiSession(previous.InheritedSession):
    SYSTEM=SYSTEM;SCHEMA=SCHEMA;ARGS=ARGS
    def __init__(self,*args,**kwargs):
        self.pool={};self.entries=[];self.shown=set();self.dismissals={};self.pool_pages={};self.blocked_references={};self.catalogue_filter='all';self.source_origin='followup'
        super().__init__(*args,**kwargs)
        self.seed_pool()
        self.initial_pool_ids=sorted(self.pool)
    def seed_pool(self):
        # Seed retrieval is deterministic and gold-free. Every matched path contributes.
        for seed in self.seed['terms']:
            tid=seed['id'];term=self.t.terms[tid]
            if term.get('scope_document_id') and term['scope_document_id'] not in self.scope:continue
            eid='entry:'+str(len(self.entries)+1);paths={};terms=[(tid,[])]
            for edge in sorted(self.t.edges.get(tid,[]),key=lambda x:x['id']):
                other=edge['target'] if edge['source']==tid else edge['source'];t=self.t.terms[other]
                if not t.get('scope_document_id') or t['scope_document_id'] in self.scope:terms.append((other,[edge['id']]))
            for node,edges in terms:
                for sid in self.occurrence(node):paths.setdefault(sid,[]).append({'term_id':node,'edge_ids':edges})
            self.entries.append({'id':eid,'kind':'term','term_id':tid,'label':term['label'],'question_spans':seed['question_spans'],'candidate_count':len(paths),'retrieval':'registered occurrences + one-hop registered relations','unresolved':not paths})
            for sid,routes in paths.items():self.add_candidate(sid,eid,{'routes':routes})
        for seed in self.seed['structures']:
            key=seed['id']
            if key not in self.structure_keys:continue
            eid='entry:'+str(len(self.entries)+1);ids=[sid for sid in self.m._unit_sources(*self.structure_keys[key]) if sid in self.metadata]
            self.entries.append({'id':eid,'kind':'structure','structure_id':key,'question_spans':seed['question_spans'],'candidate_count':len(ids),'retrieval':'stored structural membership','unresolved':not ids})
            for sid in ids:self.add_candidate(sid,eid,{'structure_id':key})
    def query_coordinates(self,locator):
        # User spelling normalization only. Actual coordinates always match stored nodes.
        text=re.sub(r'\s+','',locator)
        text=re.sub(r'(?<![제0-9])([0-9]+(?:-[0-9]+)?)([편장절관조항호])',r'제\1\2',text)
        return [x.coordinate for x in previous.previous.find_coordinates(text)]
    def unresolved_references(self):
        adopted={j['source_id'] for j in self.judgments.values() if j['status']=='adopted'}
        return [v for v in self.blocked_references.values() if v['from_source_id'] in adopted]
    def add_candidate(self,sid,entry,route=None):
        if sid not in self.metadata:raise ValueError('candidate outside authorized scope')
        origins=self.pool.setdefault(sid,{})
        if entry not in origins:origins[entry]=route or {}
    def source_card(self,sid):
        self.add_candidate(sid,self.source_origin)
        card=super().source_card(sid);hits=self.term_hits(sid)
        return {**card,'entry_ids':sorted(self.pool[sid]),**({'term_hits':hits} if hits else {})}
    def term_hits(self,sid,limit=3,width=60):
        # Where the entry terms sit in the article: a short preview, not a read segment.
        if not hasattr(self,'_has_spans'):
            self._has_spans=bool(self.t.db.execute("SELECT 1 FROM sqlite_master WHERE name='occurrence_span'").fetchone())
        if not self._has_spans:return []
        tids=[r['term_id'] for route in self.pool.get(sid,{}).values() for r in route.get('routes',[])]
        text=self.t.sources[sid]['text'];hits=[]
        for tid in dict.fromkeys(tids):
            row=self.t.db.execute('SELECT start,end FROM occurrence_span WHERE term_id=? AND source_id=? ORDER BY start LIMIT 1',(tid,sid)).fetchone()
            if row:
                s,e=row;hits.append({'label':self.t.terms[tid]['label'],'context':text[max(0,s-width):e+width],'preview_only':True})
            if len(hits)>=limit:break
        return hits
    def candidates(self,offset=0):
        ids=sorted(self.pool);page=self.page(ids,offset);page['items']=[self.source_card(s) for s in page['items']];self.pool_pages[offset]=[x['id'] for x in page['items']]
        return {**page,'pending':len(self.pending_candidates()),'content_read':False,'initial_entry_count':len(self.entries),'initial_union_count':len(self.initial_pool_ids),'deduplication':'source identity; all entry paths preserved'}
    def pending_candidates(self):
        reviewed={j['source_id'] for j in self.judgments.values() if j['status'] in ('adopted','excluded')}
        return set(self.pool)-reviewed-set(self.dismissals)
    def progress_marker(self):return (super().progress_marker(),len(self.pool),len(self.shown),len(self.dismissals))
    def catalogue(self,offset=0,category='all'):
        if self.catalogue_delivered and category!=self.catalogue_filter:raise ValueError('catalogue filter cannot change after delivery')
        self.catalogue_filter=category;listing=document_listing(self.m,self.scope,category);page=self.page(listing['documents'],offset);self.catalogue_pages[offset]=page
        return {**page,**{k:v for k,v in listing.items() if k not in ('documents','total')},'content_read':False,'status':'COMPLETE_PAGE'}
    def visible_this_turn(self):
        visible=set(self.shown)
        for rec in self.last:
            if rec.get('status')=='OK':visible.update(x['id'] for x in rec.get('result',{}).get('items',[]) if isinstance(x,dict) and x.get('read_handle'))
        return visible
    def context(self):
        data=legal.StructuredSession.context(self);data['tools']=deepcopy(legal.TOOLS);data['tools'].update({'CANDIDATES':'{offset:0}: 모든 초기 진입점 후보 합집합. 먼저 모든 페이지를 확인한 뒤 READ 또는 명백한 대상 차이에 한해 DISMISS.','DISMISS':'{read_handles:[],reason}: 제시된 후보를 문서/표제의 명백한 부적합 이유로 제외. 내용 판단은 READ/JUDGE.','CATALOG':'{offset:0,category:all|internal|external|unknown}: 저장된 문서 분류로 목록 조회. 분류 미확인은 unknown.'})
        data['tools']['READ']='{source_id:RH read_handle,unit_id:""}: offered read_action only; never invent raw source/structure IDs.'
        data['entry_paths']=self.page(self.entries,0,16);data['candidate_review']={'total':len(self.pool),'unseen':len(set(self.pool)-self.visible_this_turn()),'pending':len(self.pending_candidates()),'metadata_excluded':len(self.dismissals),'next_candidate_offset':next((i for i,s in enumerate(sorted(self.pool)) if s not in self.visible_this_turn()),None)}
        data['blocked_references']=self.unresolved_references();data['request_contract']={**self.contract,'pending':self.pending()};data['next_actions']=[]
        unseen=set(self.pool)-self.visible_this_turn()
        if unseen:data['next_actions']=[{'tool':'CANDIDATES','args':{'offset':data['candidate_review']['next_candidate_offset']}}]
        elif self.prerequisite_pending():
            ids=[s for s in self.pool if self.metadata[s]['document_id']==self.prerequisite_pending()];data['next_actions']=[self.source_card(s)['read_action'] for s in sorted(ids)]
        # Prompt never receives undisplayed raw candidate body; source cards are paged.
        if len(json.dumps(data,ensure_ascii=False))>self.limits['context_chars']:raise ValueError('multi-entry context budget exceeded')
        return data
    def response_schema(self):
        self.route_actions=[];schema=super().response_schema();options=[]
        for item in schema['properties']['actions']['items']['anyOf']:
            tool=item['properties']['tool']['enum'][0]
            if tool=='CATALOG':item=self.wire(legal.action_schema(tool,deepcopy(ARGS[tool])))
            options.append(item)
        options.append(legal.action_schema('CANDIDATES',deepcopy(ARGS['CANDIDATES'])))
        if self.offered_handles:
            args=deepcopy(ARGS['DISMISS']);args['properties']['read_handles']['items']=legal.enum(*sorted(self.offered_handles));options.append(legal.action_schema('DISMISS',args))
        if set(self.pool)-self.visible_this_turn():
            args=deepcopy(ARGS['CANDIDATES']);args['properties']['offset']={'type':'integer','enum':[next(i for i,s in enumerate(sorted(self.pool)) if s not in self.visible_this_turn())]};args['required']=['offset'];stop=deepcopy(ARGS['STOP']);stop['properties']['status']=legal.enum('incomplete');options=[legal.action_schema('CANDIDATES',args),legal.action_schema('STOP',stop)]
        elif self.pending_candidates() or self.unresolved_references():
            for item in options:
                if item['properties']['tool']['enum']==['STOP']:item['properties']['args']['properties']['status']=legal.enum('incomplete')
        schema['properties']['actions']['items']['anyOf']=options;return schema
    def execute(self,tool,a):
        if tool=='CANDIDATES':return self.candidates(**a)
        if tool=='DISMISS':
            if not a.get('reason','').strip():raise ValueError('metadata dismissal reason required')
            ids=[]
            for h in a['read_handles']:
                if h not in self.offered_handles:raise ValueError('currently offered handle required')
                sid=self.read_handles[h]['source_id']
                if sid not in self.shown:raise ValueError('candidate metadata not yet delivered')
                if any(j['source_id']==sid and j['status']=='adopted' for j in self.judgments.values()):raise ValueError('use JUDGE to change adopted evidence')
                ids.append(sid)
            for sid in ids:self.dismissals[sid]={'reason':a['reason'],'basis':'metadata-only, not content verification'}
            return {'dismissed_source_ids':ids,'pending':len(self.pending_candidates())}
        if tool=='CATALOG':return self.catalogue(**a)
        if tool=='STOP' and a.get('status')=='sufficient' and self.unresolved_references():raise ValueError('REQUIRED_REFERENCE_OUTSIDE_SCOPE_OR_UNRESOLVED')
        if tool=='STOP' and a.get('status')=='sufficient' and self.pending_candidates():raise ValueError('UNREVIEWED_ENTRY_CANDIDATES: '+str(len(self.pending_candidates())))
        result=super().execute(tool,a)
        if tool=='READ' and result.get('source_id'):self.dismissals.pop(result['source_id'],None)
        if tool=='JUDGE' and a.get('status')=='adopted':
            sid=result['source_id']
            # Follow actual resolved outgoing references, bounded by the same source scope.
            for row in self.t.db.execute('SELECT DISTINCT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=?',(sid,)):
                ref=json.loads(row[0])
                if ref.get('source_id')==sid and reference_resolved(ref.get('resolution')):
                    for target in ref.get('target_source_ids',[]):
                        if target in self.metadata:self.add_candidate(target,'reference:'+ref['id'],{'from_source_id':sid})
                        else:self.blocked_references[ref['id']]={'from_source_id':sid,'reference_id':ref['id'],'reason':'target outside authorized scope'}
                elif ref.get('source_id')==sid:self.blocked_references[ref['id']]={'from_source_id':sid,'reference_id':ref['id'],'reason':'unresolved stored reference'}
        return result
    def note_results(self):
        super().note_results()
        for rec in self.last:
            if rec.get('status')=='OK':
                self.shown.update(x['id'] for x in rec.get('result',{}).get('items',[]) if isinstance(x,dict) and x.get('read_handle'))
    def final_state(self,state):
        state=super().final_state(state)
        state.update(entry_paths=deepcopy(self.entries),initial_pool_source_ids=self.initial_pool_ids,candidate_pool={s:list(paths) for s,paths in self.pool.items()},shown_source_ids=sorted(self.shown),pending_source_ids=sorted(self.pending_candidates()),metadata_dismissals=deepcopy(self.dismissals))
        if self.stop['status']=='catalogue':state['catalogue']={**document_listing(self.m,self.scope,self.catalogue_filter),'complete':True}
        return state

class MultiAgent(previous.InheritedAgent):
    session_type=MultiSession
    def retrieve(self,plan,use_llm=True):
        return super().retrieve(plan,use_llm)
    def local_result(self,plan,output,text,tool,args,*,notes=(),read=None):
        sid=read['source_id'] if read else None
        state={'status':'FINISH','stop':{'status':'catalogue' if tool=='CATALOG' else 'metadata','unresolved':list(notes)},'failure':None,'calls':0,'actions':1,'provider_receipts':[],'trace':[{'tool':tool,'args':args,'status':'OK','result':deepcopy(output),'reason':'explicit scoped metadata/coordinate request'}],'judgments':[],'adopted':[],'read_segments':[read] if read else [],'read_source_ids':[sid] if sid else [],'known_source_ids':[sid] if sid else [],'selected_ids':[sid] if sid else [],'use_llm':True,'elapsed_seconds':0,'quality_certified':False,'context_chars':[],'catalogue':{**output,'complete':output.get('complete',True)} if tool=='CATALOG' else {'complete':False,'documents':[]},'final':{'findings':[{'text':read['text'],'source_ids':[sid]}] if read else [],'evidence_ids':[sid] if sid else [],'open_questions':[{'kind':'METADATA','text':n} for n in notes] or ([] if tool=='CATALOG' or read else [{'kind':'METADATA','text':text}]),'question_for_user':'','next_action':'FINISH'},'entry_paths':[],'initial_pool_source_ids':[],'candidate_pool':{},'shown_source_ids':[],'pending_source_ids':[],'metadata_dismissals':{}}
        if text:state['navigation_output']={'text':text,'data':output,'kind':tool,'content_read':bool(read),'unresolved':list(notes)}
        rows=[{**self.matcher.tools.sources[sid],'ancestors':[],'routes':['scoped_coordinate'],'score':0}] if sid else []
        return {'candidates':rows,'routes':{'scoped_navigation':len(rows)},'vector_status':'NOT_USED','generation_id':plan['generation_id'],'term_agent':state}

class Conversation:
    """Explicit research adapter: instantiate per user conversation, never globally.

    Metadata rendering consumes stored navigation_output after the existing pipeline.
    Content/LLM queries use the same existing retrieve/select/assemble/answer stages
    with the narrowed document allowlist. reset_scope is an explicit caller action.
    """
    def __init__(self,pipeline,agent,authorized):
        self.pipeline,self.agent=pipeline,agent;self.authorized=list(agent.matcher.tools.validate_scope(authorized));self.navigator=folders.FolderNavigator(agent.matcher,pipeline.store);self.context=None
        agent.navigator=self.navigator;pipeline.term_agent=agent
    def catalogue(self,**filters):
        result=self.navigator.catalogue(self.authorized,context=self.context,**filters);self.context=result['context'];return result
    def select(self,document_id):
        self.context=self.navigator.select(self.authorized,self.context,document_id);return self.context
    def outline(self,**args):return self.navigator.outline(self.authorized,context=self.context,**args)
    def search_structure(self,**args):return folders.search_structure(self.navigator,self.authorized,context=self.context,**args)
    def read_structure(self,**args):return self.navigator.read_unit(self.authorized,context=self.context,**args)
    def reset_scope(self):self.context=None
    def run(self,question,use_llm=True):
        allowed=sorted(self.navigator.scope(self.authorized,self.context))
        self.agent.navigation_context=self.context
        self.agent.last_navigation_context=self.context
        if not allowed:
            return {'status':'EMPTY_SCOPE','answer':{'text':'현재 선택 범위에 문서가 없습니다. 검색 범위를 다시 선택해 주세요.'},'navigation_context':self.context}
        # Explicit catalogue/outline/read API methods remain available. Free text
        # always reaches the agent; mentioning a coordinate is not a read command.
        result=self.pipeline.run(question,allowed,use_llm)
        state=result['retrieval']['term_agent'];meta=state.get('navigation_output')
        if meta:
            result['answer']['text']=meta['text']
            result['answer']['unresolved']=[{'reason':x} for x in meta['unresolved']]
        self.context=self.agent.last_navigation_context
        state['navigation_context']=self.context
        self.pipeline.contracts.validate(result,'urn:8-agent:term-runtime-v1','Result')
        return result
