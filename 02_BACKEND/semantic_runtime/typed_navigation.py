"""Stored keyword types -> grounded entity handles -> executable navigation choices."""
from copy import deepcopy
import hashlib,json,re,sqlite3,time
from . import multi_entry_navigation as previous
folders=previous.folders;legal=previous.legal

HELP={
 'folder':('여러 문서를 묶은 폴더입니다. 원문 근거가 아닙니다. 하위 폴더·문서를 펼치거나 그 안의 문서 제목만 검색할 수 있습니다.',('OPEN_FOLDER','FOLDER_TREE','DOCUMENT_TITLES')),
 'document':('특정 문서입니다. 선택하면 후속 검색을 이 문서로 제한하고 저장 목차·조항을 조회할 수 있습니다.',('SELECT_DOCUMENT','DOCUMENT_OUTLINE')),
 'structure':('문서에 저장된 장·절·조문 표제입니다. 구조 ID와 원문 읽기 핸들은 다릅니다.',('STRUCTURE','LIST')),
 'coordinate':('저장된 구조에 대응하는 조·항 좌표입니다. 소속 문서·본문/부칙을 확인하고 FIND_ARTICLE로 조회합니다.',('FIND_ARTICLE',)),
 'term':('등록 용어입니다. 정의와 문서 연결을 탐색하는 단서이며 폴더나 원문 근거와 다릅니다.',('OPEN_TERM','GRAPH','LIST')),
}

class TypeRegistry:
    def __init__(self,matcher,authorized,question=None):
        self.m=matcher;self.scope=set(matcher.tools.validate_scope(authorized));self.entities={};self.folders={};self.documents={};self.offered=set()
        nq=folders.normalized(question) if question is not None else None
        for did in sorted(self.scope):
            d=matcher.document_catalogue[did];path=d.get('navigation_folder');self.documents[did]=self.add('document',did,d['name'],[d['name']],document_ids=[did],folder=path)
            if path:
                parts=path.split('/')
                for i in range(1,len(parts)+1):
                    p='/'.join(parts[:i]);self.folders.setdefault(p,set()).add(did)
        for path,ids in sorted(self.folders.items()):
            label=path.rsplit('/',1)[-1];aliases=[label,path]
            if path=='internal':aliases+=['내규','내부문서','내부 문서']
            if path=='external':aliases+=['외부문서','외부 문서']
            if label=='kofia':aliases+=['금융투자협회']
            self.add('folder',path,label,aliases,document_ids=sorted(ids),path=path)
        for (did,uid),u in matcher.units.items():
            if did not in self.scope:continue
            title=u.get('title') or ''
            if title and (nq is None or folders.normalized(title) in nq):self.add('structure',did+':'+uid,title,[title],document_ids=[did],structure_id='structure:'+did+':'+uid)
        for tid,t in matcher.tools.terms.items():
            if t.get('scope_document_id') and t['scope_document_id'] not in self.scope:continue
            label=t.get('label','')
            if label and (nq is None or folders.normalized(label) in nq):self.add('term',tid,label,[label],term_id=tid)
    def add(self,kind,identity,label,aliases,**fields):
        h='KH'+hashlib.sha256((kind+'|'+identity).encode()).hexdigest()[:20]
        self.entities[h]={'handle':h,'type':kind,'identity':identity,'label':label,'aliases':list(dict.fromkeys(aliases)),**fields};return h
    @staticmethod
    def alias_keys(entity):
        # Normalized alias surfaces are stable per entity; matches() reuses them.
        if '_alias_keys' not in entity or len(entity['_alias_keys'])!=len(entity['aliases']):
            entity['_alias_keys']=[folders.normalized(a) for a in entity['aliases']]
        return entity['_alias_keys']
    def card(self,h):
        e=self.entities[h];kind=e['type'];self.offered.add(h);out={k:deepcopy(v) for k,v in e.items() if k not in ('aliases','document_ids','_alias_keys')}
        text,tools=HELP[kind];out.update(meaning=text,available_tools=list(tools),is_source_evidence=False)
        if kind=='folder':
            path=e['path'];out.update(document_count=len(e['document_ids']),child_folder_count=sum(p.rpartition('/')[0]==path for p in self.folders),parent_path=path.rpartition('/')[0] or None)
        if kind=='document':out['document_id']=e['identity']
        out['suggested_actions']=[{'tool':t,'args':{'handle':h}} for t in tools if t in ('OPEN_FOLDER','FOLDER_TREE','DOCUMENT_TITLES','SELECT_DOCUMENT','DOCUMENT_OUTLINE')]
        if kind=='term':out['suggested_actions']=[{'tool':'OPEN_TERM','args':{'term_id':e['term_id']}}]
        if kind=='coordinate':out['suggested_actions']=[{'tool':'FIND_ARTICLE','args':{'locator':e['label'],'document_id':e['document_id']}}]
        if kind=='structure':out['suggested_actions']=[{'tool':'STRUCTURE','args':{'structure_id':e['structure_id']}}]
        return out
    def matches(self,question,offset=0,limit=16):
        self.page_args(offset,limit)
        # Match only admitted metadata labels, never raw article text.
        norm=[];positions=[]
        for i,ch in enumerate(question):
            for c in folders.normalized(ch):norm.append(c);positions.append(i)
        q=''.join(norm);hits=[]
        for h,e in self.entities.items():
            spans=[]
            for n in self.alias_keys(e):
                if len(n)<2:continue
                start=0
                while (at:=q.find(n,start))>=0:
                    end=at+len(n);start=end
                    if n.isascii() and n.isalpha() and ((at and q[at-1].isascii() and q[at-1].isalpha()) or (end<len(q) and q[end].isascii() and q[end].isalpha())):continue
                    spans.append({'text':question[positions[at]:positions[end-1]+1],'start':positions[at],'end':positions[end-1]+1})
            if spans:hits.append((min(x['start'] for x in spans),h,spans))
        hits.sort(key=lambda x:(x[0],x[1]));items=[{**self.card(h),'question_spans':spans} for _,h,spans in hits[offset:offset+limit]]
        return {'items':items,'total':len(hits),'offset':offset,'next_offset':offset+limit if offset+limit<len(hits) else None,'authority':'stored folder/document/structure/term registry; lexical match identifies a typed entity, not body occurrence','ambiguity_policy':'retain all matching types; choose by requested operation; never silently merge folder and term'}
    @staticmethod
    def page_args(offset,limit):
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=500:raise ValueError('invalid page bounds')
    def get(self,h,kind=None):
        if h not in self.offered:raise ValueError('currently offered typed entity handle required')
        e=self.entities[h]
        if kind and e['type']!=kind:raise ValueError('entity type mismatch: expected '+kind)
        return e
    def folder_handle(self,path):return next(h for h,e in self.entities.items() if e['type']=='folder' and e['path']==path)
    def open_folder(self,handle,offset=0,limit=50,tree=False):
        self.page_args(offset,limit)
        root=self.get(handle,'folder');path=root['path'];handles=[]
        def children(parent):
            for p in sorted(self.folders):
                if p.rpartition('/')[0]==parent:
                    handles.append(self.folder_handle(p))
                    if tree:children(p)
            for did in sorted(root['document_ids']):
                h=self.documents[did]
                if self.entities[h]['folder']==parent:handles.append(h)
        children(path)
        return {'root':self.card(handle),'items':[self.card(h) for h in handles[offset:offset+limit]],'total':len(handles),'offset':offset,'next_offset':offset+limit if offset+limit<len(handles) else None,'view':'tree' if tree else 'immediate children','content_read':False}

    def titles(self,handle,query='',offset=0,limit=50):
        self.page_args(offset,limit)
        if not isinstance(query,str) or len(query)>500:raise ValueError('bounded title query required')
        e=self.get(handle,'folder');q=folders.normalized(query);ids=[d for d in e['document_ids'] if q in folders.normalized(self.m.documents[d])]
        return {'items':[self.card(self.documents[d]) for d in ids[offset:offset+limit]],'total':len(ids),'offset':offset,'next_offset':offset+limit if offset+limit<len(ids) else None,'field':'document.name','folder':e['path'],'content_read':False}

ARGS=deepcopy(previous.ARGS)
for tool in ('OPEN_FOLDER','FOLDER_TREE','DOCUMENT_TITLES','SELECT_DOCUMENT','DOCUMENT_OUTLINE'):
    props={'handle':legal.STR}
    if tool!='SELECT_DOCUMENT':props['offset']=legal.INT
    if tool=='DOCUMENT_TITLES':props['query']=legal.STR
    ARGS[tool]=legal.obj(props,['handle'])
ARGS['KEYWORD_TYPES']=legal.obj({'offset':legal.INT},[])
SCHEMA=deepcopy(previous.SCHEMA);SCHEMA['properties']['actions']['items']['anyOf']=[legal.action_schema(k,v) for k,v in ARGS.items()]
SYSTEM=previous.SYSTEM+'''\nkeyword_types는 질문에서 발견한 실제 저장 개체의 타입이다. folder는 원문 단어가 아니라 문서 묶음이다. 폴더 문서 목록 요청은 OPEN_FOLDER 또는 DOCUMENT_TITLES, 트리는 FOLDER_TREE를 사용한다. 제목 검색에는 DOCUMENT_TITLES만 사용하고 같은 이름을 본문 검색어로 자동 전환하지 않는다. document를 SELECT_DOCUMENT하면 이후 검색 범위가 그 문서로 좁혀진다. 구조/좌표/용어는 카드의 의미와 도구 안내를 따른다. 같은 표기가 여러 타입이면 모두 보고 사용자 요청 동작에 맞춰 선택한다.''' 

class TypedSession(previous.MultiSession):
    SYSTEM=SYSTEM;SCHEMA=SCHEMA;ARGS=ARGS
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.registry=TypeRegistry(self.m,self.scope,self.question);self.type_page=self.registry.matches(self.question);self.selected_documents=None;self.scope_narrowing=[]
        # Recognize explicit coordinates using ingestion's grammar and stored values.
        for c in self.query_coordinates(self.question):
            for (did,uid),stored in self.structure_coordinates.items():
                if stored.canonical_surface()!=c.canonical_surface():continue
                h=self.registry.add('coordinate',did+':'+uid,c.canonical_surface(),[c.canonical_surface(),c.canonical_surface().replace('제','')],document_ids=[did],document_id=did,unit_id=uid,coordinate_key=self.m.units[(did,uid)].get('coordinate_key'))
        self.type_page=self.registry.matches(self.question)
    def context(self):
        data=super().context();data['keyword_types']=deepcopy(self.type_page)
        data['tools'].update({'KEYWORD_TYPES':'질문 키워드 타입 후보의 다음 offset 페이지','OPEN_FOLDER':'{handle,offset}: 폴더의 바로 아래 폴더·문서','FOLDER_TREE':'{handle,offset}: 폴더 아래 저장 경로 트리','DOCUMENT_TITLES':'{handle,query,offset}: 선택 폴더 안 문서명만 검색','SELECT_DOCUMENT':'{handle}: 문서 타입 카드 선택; 이후 검색은 이 문서 안','DOCUMENT_OUTLINE':'{handle,offset}: 문서 저장 구조 목차'})
        data['typed_guidance']='카드의 타입별 available_tools를 보고 다음 행동을 고른다. 매칭은 본문 근거나 읽기 완료가 아니다.'
        if len(json.dumps(data,ensure_ascii=False))>self.limits['context_chars']:raise ValueError('typed navigation context budget exceeded')
        return data
    def response_schema(self):
        schema=super().response_schema();opts=schema['properties']['actions']['items']['anyOf'];opts.append(legal.action_schema('KEYWORD_TYPES',deepcopy(ARGS['KEYWORD_TYPES'])))
        for tool,kind in [('OPEN_FOLDER','folder'),('FOLDER_TREE','folder'),('DOCUMENT_TITLES','folder'),('SELECT_DOCUMENT','document'),('DOCUMENT_OUTLINE','document')]:
            handles=sorted(h for h in self.registry.offered if self.registry.entities[h]['type']==kind)
            if handles:
                args=deepcopy(ARGS[tool]);args['properties']['handle']=legal.enum(*handles);opts.append(legal.action_schema(tool,args))
        return schema
    def execute(self,tool,a):
        if tool=='KEYWORD_TYPES':self.type_page=self.registry.matches(self.question,**a);return self.type_page
        if tool in ('OPEN_FOLDER','FOLDER_TREE'):return self.registry.open_folder(**a,tree=tool=='FOLDER_TREE')
        if tool=='DOCUMENT_TITLES':return self.registry.titles(**a)
        if tool=='DOCUMENT_OUTLINE':
            e=self.registry.get(a['handle'],'document');nav=folders.FolderNavigator(self.m,self.store_view());return nav.outline(list(self.scope),context=None,document_id=e['identity'],offset=a.get('offset',0))
        if tool=='SELECT_DOCUMENT':
            e=self.registry.get(a['handle'],'document');did=e['identity']
            if did not in self.scope:raise ValueError('document outside current scope')
            if self.read_segments:raise ValueError('document selection must precede evidence reading; use a new scoped request')
            removed=set(self.pool)-{sid for sid,v in self.metadata.items() if v['document_id']==did};self.scope={did};self.metadata={sid:v for sid,v in self.metadata.items() if v['document_id']==did};self.pool={sid:v for sid,v in self.pool.items() if sid in self.metadata};self.initial_pool_ids=[s for s in self.initial_pool_ids if s in self.metadata];self.known_sources&=set(self.metadata);self.occurrences={}
            self.structure_keys={k:v for k,v in self.structure_keys.items() if v[0]==did};self.structure_coordinates={k:v for k,v in self.structure_coordinates.items() if k[0]==did};self.known_structures&=set(self.structure_keys)
            for k in ('structures','explicit'):self.seed[k]=[x for x in self.seed[k] if x['document_id']==did]
            self.registry=TypeRegistry(self.m,[did],self.question);self.type_page=self.registry.matches(self.question);self.registry.offered.add(self.registry.documents[did])
            self.selected_documents=[did];self.scope_narrowing.append({'document_id':did,'removed_source_ids':sorted(removed),'reason':'explicit document selection'})
            return {'document_id':did,'scope_document_ids':[did],'content_read':False,'next_tool':'DOCUMENT_OUTLINE or FIND_ARTICLE or scoped LIST'}
        return super().execute(tool,a)
    def store_view(self):
        # Bound matcher carries an explicitly attached source store for metadata tools.
        return self.m.navigation_store
    def final_state(self,state):
        state=super().final_state(state)
        state.update(keyword_types=self.type_page,selected_documents=self.selected_documents,scope_narrowing=self.scope_narrowing)
        return state

class TypedAgent(previous.MultiAgent):
    session_type=TypedSession
    def retrieve(self,plan,use_llm=True):
        self.matcher.navigation_store=self.pipeline.store
        registry=TypeRegistry(self.matcher,plan['scope']['document_version_ids'],plan['question'])
        matches=registry.matches(plan['question'],limit=500)
        result=super().retrieve(plan,use_llm)
        state=result['term_agent'];state.setdefault('keyword_types',matches)
        if state.get('selected_documents') and hasattr(self,'navigator'):
            self.last_navigation_context=self.navigator.remember(state['selected_documents'],{'selection':'typed document handle'})
        return result

class Conversation(previous.Conversation):
    def describe_keywords(self,question,offset=0):
        registry=TypeRegistry(self.agent.matcher,self.navigator.scope(self.authorized,self.context),question)
        return registry.matches(question,offset=offset)
