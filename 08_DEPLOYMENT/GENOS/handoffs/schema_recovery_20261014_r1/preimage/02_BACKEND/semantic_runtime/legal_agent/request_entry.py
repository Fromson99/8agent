"""Opt-in fresh-request fusion. Existing case mutations use the legacy resolver."""
from copy import deepcopy
from jsonschema import validate, ValidationError
from .corrected_memory import MemoryError, digest, object_schema, COMMAND, FIELDS
from .memory_methods import normalize
from .source_query_planning import CASE_ROUTING_SYSTEM, CAPABILITIES, case_routing_schema, validate_case_routing
from .completion_execution import INTENT_PROMPT
from . import completion_contracts as cc, investigation_contracts as ic
from .memory_rag import INTENT
from .errors import ProposalError

POLICY='fused-title-v1'
SYSTEM=CASE_ROUTING_SYSTEM+'\n'+INTENT_PROMPT+'''
이번 입력에는 현재 사건·기억이 없다. 분류와 새 질문의 수행 목적·조건·검색어·쟁점을 한 번에 작성한다.
CASE의 새 질문은 command.method_id=CASE_START이고 intent를 작성한다. purpose는 조건을 뺀 수행 목적이며 원문 대상·범위를 보존한다.
facts는 사용자가 실제로 준 사건 조건만 name/value로 추출하며 user_quote에 그 조건의 현재 발언 원문을 그대로 복사한다. 일반 법률 설명 질문에는 특정 사건 사실을 만들지 말고 facts=[]로 둔다.
queries는 최대4개·각180자 이내다. 문서명·조문·법령 약칭 등 실제 단서를 보존한다. 문서 ID·실제 법률 결론을 추측하지 않는다.
질문이 실제로 설명을 요구한 제목·행위를 먼저 찾는다. 사용자가 추가로 다루지 말라고 하거나 제외한 참조 조문번호는 초기 queries의 대상이 아니다. 제외한 조문이 유일한 번호여도 그 번호로 원하는 제목을 대체하지 않는다. 요청한 제목이나 핵심 문구와 문서명을 검색어로 쓰고, 처음부터 모든 역할·참조를 별개 주변 조문으로 분산하지 않는다. 필요한 직접 조문을 읽은 뒤 부족한 의존성만 추가 조사한다.
source_category는 명시한 내규/외규일 때만 internal/external, 나머지는 ALL이다. 표 요청이 없으면 format=prose다.
기록에 없는 이전 판단의 정정·복원·재사용만 요구하면 CASE/NEED_TARGET, intent=null로 두고 reason에 필요한 확인을 짧게 쓴다. 새 법률 질문의 자료·법령명이 미확인이어도 CASE_START로 조사한다.
DIRECT는 command=null, intent=null이다. CASE의 answer는 빈 문자열이다. 중복 쟁점이나 질문에 없는 배경 쟁점을 추가하지 않는다. JSON만 출력한다.'''

SYSTEM += '''
law_title_hints는 사용자 표현과 허용 문서 제목/약칭을 대조한 위치 단서이며 정답이나 적용 법령의 확정이 아니다.
EXACT_TITLE/REGISTERED_ALIAS는 확인된 이름 일치다. PARTIAL_TITLE/DERIVED_ABBREVIATION은 유사 후보이며 등록된 약칭으로 단정하지 않는다.
question_span, title_matches와 실제 title을 비교해 문맥에 맞는 후보만 search.title_hint_ids로 선택한다. 없거나 틀리면 빈 배열로 둔다.
search.mode는 STRUCTURE(법령/목차/조문 부근의 단서로 위치 조회) 또는 FULLTEXT(세부 내용/문구로 본문 검색)다. FULLTEXT 전에 STRUCTURE를 반드시 거칠 필요가 없다.
선택한 제목 후보를 queries에 쓸 때는 실제 title로 적고 실제 조사 대상으로 요청된 조문번호를 보존한다. 제외된 참조 조문번호는 넣지 않는다. 이 후보 외 문서도 조사할 수 있다.
context_quotes는 배경/업무 문맥의 원문을 그대로 복사한 목록이다. 구조 설명만 요청했다면 해당 범위 전체의 구조 설명만 쟁점으로 두고, 업무 문맥에 대한 적용·평가·계산을 추가 과제로 만들지 않는다. 필요한 참조를 읽는 것은 가능하다.
DIRECT 또는 NEED_TARGET이면 search=null, context_quotes=[]다. CASE_START이면 search를 작성한다.'''

def schema(scoped=False):
    fact=object_schema({'name':{'type':'string','minLength':1,'maxLength':100},
        'value':{'type':['string','null'],'maxLength':600},
        'user_quote':{'type':'string','minLength':1,'maxLength':1000}})
    command=object_schema({'method_id':{'enum':['CASE_START','NEED_TARGET']},
        'source_category':{'enum':['ALL','internal','external']},
        'facts':{'type':'array','items':fact,'maxItems':16},
        'queries':deepcopy(COMMAND['properties']['queries']),
        'format':{'enum':['prose','table']},'reason':deepcopy(COMMAND['properties']['reason'])})
    intent=ic.intent_schema(INTENT)
    if scoped:
        from .completion_v5 import intent_schema
        intent=intent_schema(intent)
        del intent['properties']['background_quotes']
        intent['required'].remove('background_quotes')
    intent['properties']['purpose'].update(minLength=1,maxLength=600)
    return object_schema({'routing':case_routing_schema(),
        'command':{'anyOf':[command,{'type':'null'}]},
        'intent':{'anyOf':[intent,{'type':'null'}]},
        'context_quotes':{'type':'array','items':{'type':'string','minLength':1,'maxLength':1000},'maxItems':8},
        'search':{'anyOf':[object_schema({'mode':{'enum':['STRUCTURE','FULLTEXT']},
            'title_hint_ids':{'type':'array','items':{'type':'string'},'maxItems':3},
            'reason':{'type':'string','minLength':1,'maxLength':600}}),{'type':'null'}]}})

def eligible(repo,context):
    profile=repo.executor.model.pipeline.term_agent.profile
    return (profile.get('request_entry_policy','legacy')==POLICY and cc.enabled(profile)
        and not context['goals'] and not context.get('knowledge') and not getattr(repo,'resume_goal',None))

def fresh_state(body,principal,command):
    state={'task':body['question'],'source_category':'ALL',
        'document_ids':body.get('document_ids') or list(principal['document_ids']),'facts':[],'queries':[]}
    for field in FIELDS:
        value=command[field]
        if value is not None and not (field=='source_category' and value=='KEEP'):state[field]=value
    return state

def accept(repo,context,value,*,scoped=False):
    validate(value,schema(scoped)); routing=validate_case_routing(value['routing'])
    proposed=value['command']; intent=value['intent']
    search=value['search']; quotes=value['context_quotes']
    if any(q not in context['utterance'] for q in quotes):raise MemoryError('context quote outside current request')
    if intent is None and (search is not None or quotes):raise MemoryError('non-start entry cannot carry search or background')
    if intent is not None:
        if scoped:
            from .completion_v5 import verify_intent
            intent['background_quotes']=deepcopy(quotes)
            verify_intent(intent,context['utterance'])
        if search is None:raise MemoryError('case start requires search selection')
        ids=search['title_hint_ids']; allowed={h['hint_id'] for h in repo._entry_title_hints['candidates']}
        if len(ids)!=len(set(ids)) or set(ids)-allowed:raise MemoryError('unknown or duplicate law title hint')
    if routing['mode']=='DIRECT':
        if proposed is not None or intent is not None:raise MemoryError('direct entry must not carry legal state')
        return routing,None,None
    if proposed is None:raise MemoryError('case entry requires command')
    is_start=proposed['method_id']=='CASE_START'
    if is_start != (intent is not None):raise MemoryError('only case start requires intent')
    if intent is not None and len({i['id'] for i in intent['issues']})!=len(intent['issues']):
        raise MemoryError('duplicate request issue')
    if not is_start and (proposed['facts'] or proposed['queries']):raise MemoryError('clarification cannot edit case state')
    for fact in proposed['facts']:
        if fact['user_quote'] not in context['utterance']:raise MemoryError('fact quote outside current request')
    c=normalize({'method_id':proposed['method_id'],'document_scope_mode':'AUTHORIZED' if is_start else 'KEEP',
        'target':None,'knowledge_id':None,'stage':'INTENT' if is_start else 'NONE',
        'task':context['utterance'] if is_start else None,'source_category':proposed['source_category'] if is_start else 'KEEP',
        'document_ids':None,'facts':[{k:f[k] for k in ('name','value')} for f in proposed['facts']] if is_start else None,
        'queries':proposed['queries'] if is_start else None,'restore_event':None,'restore_fields':[],
        'format':proposed['format'],'reason':proposed['reason']},context)
    if is_start:
        from ..pipeline import route_question
        _,category=route_question(context['utterance'])
        if category is not None:c['source_category']=category
    repo.admit(c,context)
    return routing,c,intent

def run(repo,context):
    data={'question':context['utterance'],'current_goals':[],
        'capabilities':{**CAPABILITIES,'limitations':['등록되고 요청 범위에 허용된 자료만 조회']}}
    session=repo.executor.model.ensure();work=session.work
    from .law_title_hints import hints
    scope=set(session.sources.scope)&set(repo._entry_principal['document_ids'])
    if repo._entry_body.get('document_ids'):scope &= set(repo._entry_body['document_ids'])
    from ..pipeline import route_question
    _,category=route_question(context['utterance'])
    if category:scope={d for d in scope if session.sources.matcher.document_context.get(d,{}).get('source_category')==category}
    import time
    started=time.perf_counter()
    repo._entry_title_hints=hints(context['utterance'],session.sources.matcher,scope)
    data['law_title_hints']=repo._entry_title_hints
    work.event('LAW_TITLE_HINTS',{'hints':deepcopy(repo._entry_title_hints),'seconds':time.perf_counter()-started,'model_calls':0})
    from .request_repair import enabled
    from .completion_v5 import SCOPE_PROMPT
    scoped=enabled(repo.executor.model.pipeline.term_agent.profile)
    from . import wiki_recall
    memory=wiki_recall.offer(repo.executor,repo._entry_principal,context['utterance'],scope,work.event)
    request_schema=schema(scoped)
    data,request_schema=wiki_recall.augment(data,request_schema,memory)
    recall_prompt=wiki_recall.PROMPT if memory else ''
    for attempt in range(2):
        value=None
        try:
            value=repo.invoke(SYSTEM+('\n'+SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다.' if scoped else '')+recall_prompt,data,request_schema,'request-entry' if attempt==0 else 'request-entry-repair')
            history_ids=value.pop('history_ids',[])
            routing,command,intent=accept(repo,context,value,scoped=scoped)
        except (ValidationError,ValueError,MemoryError,ProposalError) as exc:
            work.event('REQUEST_ENTRY_REJECTED',{'attempt':attempt+1,'proposal':value,'error':str(exc)})
            if attempt:raise MemoryError('request entry proposal rejected twice') from exc
            data={**data,'rejected_proposal':value,'repair_feedback':str(exc)}
            continue
        if memory:wiki_recall.choose(repo.executor,history_ids if intent is not None else [],work.event)
        entry={'contract':POLICY,'request_hash':digest(repo._entry_body),
            'principal_hash':digest(repo._entry_principal),'binding_hash':digest(repo.executor.binding),
            'title_hints':deepcopy(repo._entry_title_hints),'search':deepcopy(value['search']),'context_quotes':value['context_quotes'],
            'utterance':context['utterance'],'routing':routing,'command':command,'intent':intent,
            'state_hash':digest(fresh_state(repo._entry_body,repo._entry_principal,command)) if intent else None}
        entry['hash']=digest(entry)
        repo.executor.request_entry=entry
        session.sources.entry_search=deepcopy(entry['search'])
        repo.request_routing=routing
        work.event('REQUEST_ENTRY_ACCEPTED',deepcopy(entry))
        return

def consume(execution,state,utterance):
    entry=getattr(execution.host,'request_entry',None)
    if entry is None:return None
    record={k:v for k,v in entry.items() if k!='hash'}
    model=execution.host.model
    repo=model.cases
    if (entry['hash']!=digest(record) or entry['intent'] is None
        or entry['utterance']!=utterance or entry['state_hash']!=digest(state)
        or entry['request_hash']!=digest(repo._entry_body)
        or entry['principal_hash']!=digest(execution.principal)
        or entry['binding_hash']!=digest(execution.host.binding)):
        raise MemoryError('request entry binding mismatch')
    execution.s.work.event('REQUEST_ENTRY_INTENT_CONSUMED',{'entry_hash':entry['hash'],'state_hash':entry['state_hash'],'model_call':False})
    return deepcopy(entry['intent'])
