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
from . import output_contract as output

from .query_scope import PROMPT as SEARCH_SCOPE_PROMPT, CHANGE as SEARCH_SCOPE_CHANGE
POLICY='fused-title-v1'
SYSTEM=CASE_ROUTING_SYSTEM+'\n'+INTENT_PROMPT+'''
이번 입력에는 현재 사건·기억이 없다. 분류와 새 질문의 수행 목적·조건·검색어·쟁점을 한 번에 작성한다.
CASE의 새 질문은 command.method_id=CASE_START이고 intent를 작성한다. purpose는 조건을 뺀 수행 목적이며 원문 대상·범위를 보존한다.
facts는 사용자가 실제로 준 사건 조건만 name/value로 추출하며 user_quote에 그 조건의 현재 발언 원문을 그대로 복사한다. 일반 법률 설명 질문에는 특정 사건 사실을 만들지 말고 facts=[]로 둔다.
queries는 최대4개다. 첫 검색어는 업무 문맥을 포함한 주체·핵심 행위 중심으로 짧게 만든다. 기간·비율·연장 같은 일반 낱말만 따로 추가하면 다른 제도가 섞이므로 핵심 주체·행위를 유지한다. 모르는 법령 이름을 만들어 검색하지 않는다. 문서명·조문·법령 약칭 등 실제 단서를 보존한다. 문서 ID·실제 법률 결론을 추측하지 않는다.
질문이 실제로 설명을 요구한 제목·행위를 먼저 찾는다. 사용자가 추가로 다루지 말라고 하거나 제외한 참조 조문번호는 초기 queries의 대상이 아니다. 제외한 조문이 유일한 번호여도 그 번호로 원하는 제목을 대체하지 않는다. 요청한 제목이나 핵심 문구와 문서명을 검색어로 쓰고, 처음부터 모든 역할·참조를 별개 주변 조문으로 분산하지 않는다. 필요한 직접 조문을 읽은 뒤 부족한 의존성만 추가 조사한다.
source_category는 명시한 내규/외규일 때만 internal/external, 나머지는 ALL이다. 표 요청이 없으면 format=prose다.
기록에 없는 이전 판단의 정정·복원·재사용만 요구하면 CASE/NEED_TARGET, intent=null로 두고 reason에 필요한 확인을 짧게 쓴다. 새 법률 질문의 자료·법령명이 미확인이어도 CASE_START로 조사한다.
DIRECT/BROWSE는 command=null, intent=null이다. BROWSE의 실제 목록은 서버가 검증된 조회 결과로 조립한다. CASE의 answer는 빈 문자열이다. 중복 쟁점이나 질문에 없는 배경 쟁점을 추가하지 않는다. JSON만 출력한다.'''

SYSTEM += '''
law_title_hints는 사용자 표현과 허용 문서 제목/약칭을 대조한 위치 단서이며 정답이나 적용 법령의 확정이 아니다.
EXACT_TITLE/REGISTERED_ALIAS는 확인된 이름 일치다. PARTIAL_TITLE/DERIVED_ABBREVIATION은 유사 후보이며 등록된 약칭으로 단정하지 않는다.
question_span, title_matches와 실제 title을 비교해 문맥에 맞는 후보만 search.title_hint_ids로 선택한다. 없거나 틀리면 빈 배열로 둔다.
search.mode는 STRUCTURE(법령/목차/조문 부근의 단서로 위치 조회) 또는 FULLTEXT(세부 내용/문구로 본문 검색)다. FULLTEXT 전에 STRUCTURE를 반드시 거칠 필요가 없다.
선택한 제목 후보를 queries에 쓸 때는 실제 title로 적고 실제 조사 대상으로 요청된 조문번호를 보존한다. 제외된 참조 조문번호는 넣지 않는다. 이 후보 외 문서도 조사할 수 있다.
context_quotes는 배경/업무 문맥의 원문을 그대로 복사한 목록이다. 구조 설명만 요청했다면 해당 범위 전체의 구조 설명만 쟁점으로 두고, 업무 문맥에 대한 적용·평가·계산을 추가 과제로 만들지 않는다. 필요한 참조를 읽는 것은 가능하다.
DIRECT/BROWSE 또는 NEED_TARGET이면 search=null, context_quotes=[]다. CASE_START이면 search를 작성한다.'''

def schema(scoped=False, *, model=False):
    fact=object_schema({'name':{'type':'string','minLength':1},
        'value':{'type':['string','null']},
        'user_quote':{'type':'string','minLength':1}})
    command=object_schema({'method_id':{'enum':['CASE_START','NEED_TARGET']},
        'source_category':{'enum':['ALL','internal','external']},
        'facts':{'type':'array','items':fact,'maxItems':16,
            'description':'사용자 사건 조건·가정. 특정 호에 미해당/적용 안 됨이라는 가정은 원문 읽기 제외가 아니며 selection.exclude로 중복 변환하지 않는다.'},
        'queries':deepcopy(COMMAND['properties']['queries']),
        'format':{'enum':['prose','table']},'reason':deepcopy(COMMAND['properties']['reason'])})
    command['properties']['search_scope_change']=deepcopy(SEARCH_SCOPE_CHANGE)
    if model:
        from .query_scope import model_change_schema
        command['properties']['search_scope_change']=model_change_schema()
        command['required'].append('search_scope_change')
    intent=ic.intent_schema(INTENT)
    if scoped:
        from .completion_v5 import intent_schema
        intent=intent_schema(intent)
        del intent['properties']['background_quotes']
        intent['required'].remove('background_quotes')
    intent['properties']['purpose'].update(minLength=1)
    return object_schema({'routing':case_routing_schema(),
        'command':{'anyOf':[command,{'type':'null'}]},
        'intent':{'anyOf':[intent,{'type':'null'}]},
        'context_quotes':{'type':'array','items':{'type':'string','minLength':1},'maxItems':8},
        'search':{'anyOf':[object_schema({'mode':{'enum':['STRUCTURE','FULLTEXT']},
            'title_hint_ids':{'type':'array','items':{'type':'string'},'maxItems':3},
            'reason':{'type':'string','minLength':1}}),{'type':'null'}]}})

def bind_task_quotes(request_schema, question):
    """Constrain host-task request quotes to exact, unedited user coordinates.

    This is a wire constraint, not a correction of a rejected model proposal.
    Request provenance is the complete admitted input. Search phrases and issue
    descriptions have separate contracts; they never replace this original.
    """
    if not isinstance(question,str) or not question:
        raise ValueError('workflow request quote source missing')
    bound=deepcopy(request_schema)
    intent=next(x for x in bound['properties']['intent']['anyOf'] if x.get('type')=='object')
    quote=intent['properties']['issues']['items']['properties']['request_quote']
    anchors=[{'start_cp':0,'end_cp':len(question),'text':question}]
    quote['enum']=[question]
    return bound,anchors


def eligible(repo,context):
    profile=repo.executor.model.pipeline.term_agent.profile
    from .workflow_execution import task_context
    task=task_context()
    return ((profile.get('request_entry_policy','legacy')==POLICY or bool(task and 'issues' in task)) and cc.enabled(profile)
        and not context['goals'] and not context.get('knowledge') and not getattr(repo,'resume_goal',None))

def fresh_state(body,principal,command):
    state={'task':body['question'],'source_category':'ALL',
        'document_ids':body.get('document_ids') or list(principal['document_ids']),'facts':[],'queries':[]}
    for field in FIELDS:
        value=command[field]
        if value is not None and not (field=='source_category' and value=='KEEP'):state[field]=value
    return state

def accept(repo,context,value,*,scoped=False,admit=True):
    validate(value,schema(scoped))
    try:routing=validate_case_routing(value['routing'])
    except (ValueError,ValidationError) as exc:raise MemoryError(str(exc)) from exc
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
    if routing['mode'] in ('DIRECT','BROWSE'):
        if proposed is not None or intent is not None:raise MemoryError('direct entry must not carry legal state')
        return routing,None,None
    if proposed is None:raise MemoryError('case entry requires command')
    from .tool_policy import require_registered
    require_registered('entry',proposed['method_id'])
    is_start=proposed['method_id']=='CASE_START'
    if is_start != (intent is not None):raise MemoryError('only case start requires intent')
    if intent is not None and len({i['id'] for i in intent['issues']})!=len(intent['issues']):
        raise MemoryError('duplicate request issue')
    if not is_start and (proposed['facts'] or proposed['queries']):raise MemoryError('clarification cannot edit case state')
    for fact in proposed['facts']:
        if fact['user_quote'] not in context['utterance']:raise MemoryError('fact quote outside current request')
    c=normalize({'method_id':proposed['method_id'],'document_scope_mode':'AUTHORIZED' if is_start else 'KEEP',
        **({'search_scope_change':proposed['search_scope_change']} if 'search_scope_change' in proposed else {}),
        'target':None,'knowledge_id':None,'stage':'INTENT' if is_start else 'NONE',
        'task':context['utterance'] if is_start else None,'source_category':proposed['source_category'] if is_start else 'KEEP',
        'document_ids':None,'facts':[{k:f[k] for k in ('name','value')} for f in proposed['facts']] if is_start else None,
        'queries':proposed['queries'] if is_start else None,'restore_event':None,'restore_fields':[],
        'format':proposed['format'],'reason':proposed['reason']},context)
    if is_start:
        from ..pipeline import route_question
        _,category=route_question(context['utterance'])
        if category is not None:c['source_category']=category
    if admit:repo.admit(c,context)
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
    from . import knowledge_bridge
    knowledge = knowledge_bridge.prepare(repo.executor,work,context['utterance'],repo._entry_principal,scope)
    data, knowledge_prompt = knowledge_bridge.augment(data,knowledge)
    work.event('LAW_TITLE_HINTS',{'hints':deepcopy(repo._entry_title_hints),'seconds':time.perf_counter()-started,'model_calls':0})
    from .request_repair import enabled
    from .completion_v5 import SCOPE_PROMPT
    scoped=enabled(repo.executor.model.pipeline.term_agent.profile)
    from . import wiki_recall
    memory=wiki_recall.offer(repo.executor,repo._entry_principal,context['utterance'],scope,work.event)
    request_schema=schema(scoped, model=True)
    data,request_schema=wiki_recall.augment(data,request_schema,memory)
    recall_prompt=wiki_recall.PROMPT if memory else ''
    from .workflow_execution import task_context
    task=task_context()
    task_prompt=knowledge_prompt
    if task is not None:
        data['workflow_task']=task
        task_prompt+='\nworkflow_task는 상위 워크플로우가 지정한 조사 범위와 검색 단서다. 사용자 발언이나 사건 사실이 아니다. '
        task_prompt+='question 원문에서 해당 source_category 범위의 질문만 이 자식의 수행 목적/쟁점으로 삼아라. 다른 쪽 규정 조사와 양측 비교는 상위가 담당하므로 이 자식의 부족 과제로 넣지 마라. '
        task_prompt+='search_hints는 초기 검색어를 돕는 단서이며 규정 존재·적용·법률 결론의 근거가 아니다. 실제 질문이 요구하지 않은 세부 과제를 더 만들지 마라. '
        task_prompt+='request_quote/context_quotes/user_quote는 question 안의 연속 문자열만 그대로 복사하라. workflow_task를 인용하거나 question의 줄바꿈·문구를 바꾸지 마라.'
        work.event('WORKFLOW_TASK_CONTEXT',{'task':task,'task_hash':digest(task),'user_utterance_unchanged':True})
    if scoped:
        request_schema,data['request_quote_options']=bind_task_quotes(request_schema,context['utterance'])
        task_prompt+=' 각 issue의 request_quote는 시스템이 질문 원문 전체로 고정한다. 목적과 쟁점은 요청 범위에서 별도로 판단한다.'
    prepared={}
    def propose(payload,attempt):
        return repo.invoke(SYSTEM+SEARCH_SCOPE_PROMPT+('\n'+SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다.' if scoped else '')+recall_prompt+task_prompt,
            payload,request_schema,'request-entry' if not attempt else 'request-entry-repair')
    def check(raw, *, from_host=False):
        output.validate_shape(raw,schema(scoped) if from_host else request_schema)
        value=deepcopy(raw);history_ids=value.pop('history_ids',[])
        try:routing,command,intent=accept(repo,context,value,scoped=scoped,admit=False)
        except MemoryError as exc:
            raise output.OutputContractError(str(exc),[output.issue('REQUEST_ENTRY_CONFLICT')],
                category='DECISION_CONFLICT') from exc
        # Admission is outside the model-correction boundary for permission/state failures.
        if command is not None:repo.admit(command,context)
        prepared.update(value=value,history_ids=history_ids,routing=routing,command=command,intent=intent)
    from .workflow_execution import entry_proposal
    host_entry=entry_proposal(task,context['utterance'],scoped)
    if host_entry is not None:
        check(host_entry, from_host=True)
        from .workflow_execution import issue_map
        work.event('WORKFLOW_ENTRY_BOUND',{'task_hash':digest(task),'entry_hash':digest(host_entry),
            'issue_links':[{'parent_id':parent,'child_id':child} for child,parent in issue_map(task).items()],
            'user_utterance_unchanged':True,'model_calls':0})
    else:
        # Entry may fail before a goal exists. Keep its correction budget in
        # the durable case journal so a new physical run cannot reset it.
        output.bounded_decision(repo,'request-entry',data,request_schema,propose,check,
            identity={'request':repo._entry_body,'principal':repo._entry_principal,
                'binding':repo.executor.binding,'view':data})
    value=prepared['value'];routing=prepared['routing'];command=prepared['command'];intent=prepared['intent']
    if memory:wiki_recall.choose(repo.executor,prepared['history_ids'] if intent is not None else [],work.event)
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

def consume(execution,state,utterance):
    entry=getattr(execution.host,'request_entry',None)
    if entry is None:return None
    record={k:v for k,v in entry.items() if k!='hash'}
    model=execution.host.model
    repo=model.cases
    if (entry['hash']!=digest(record) or entry['intent'] is None
        or entry['utterance']!=utterance or entry['state_hash']!=digest({k:v for k,v in state.items() if k!='search_scope'})
        or entry['request_hash']!=digest(repo._entry_body)
        or entry['principal_hash']!=digest(execution.principal)
        or entry['binding_hash']!=digest(execution.host.binding)):
        raise MemoryError('request entry binding mismatch')
    execution.s.work.event('REQUEST_ENTRY_INTENT_CONSUMED',{'entry_hash':entry['hash'],'state_hash':entry['state_hash'],'model_call':False})
    return deepcopy(entry['intent'])
