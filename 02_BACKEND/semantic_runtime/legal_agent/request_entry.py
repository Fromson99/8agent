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
SYSTEM=CASE_ROUTING_SYSTEM+'\n'+INTENT_PROMPT+'\n현재 사건·기억 없는 최초 입력이다. 분류·목적·쟁점·사실·검색 계획을 한 번에 작성한다. 새 법률 질문과 문서/범위 지정은 CASE/CASE_START다. 목적·쟁점은 실제 요청을 보존하고 배경이나 모든 관련 사안을 추가하지 않는다. 구조 설명 요청에는 그 구조만 쟁점으로 둔다.\nfacts는 실제 사용자 사건 조건·가정만 name/value와 정확한 user_quote로 작성한다. 일반 설명은 facts=[]다. 명시 내규/외규면 source_category=internal/external, 그 외 ALL; 형식 요청이 없으면 prose다.\nFULLTEXT queries는 독립 쟁점별 구별력 있는 가장 짧은 핵심 표현1개, 최대4개다. 법령명·전체 질문·요건/기준/절차·넓은 유사어를 반복하지 않는다. 검색어는 OR 합산되므로 불필요한 일반어가 결과를 넓힌다. 주체·조건은 intent에 보존한다. 사용자나 실제 조회에 없는 조문번호·법령명·ID·법률 결론은 만들지 않는다. 제외된 참조 번호로 실제 요청 제목을 대체하지 않는다.\nsearch.scope_decision이 유일한 범위 판단이다. 실제 조사 대상으로 요청한 문서는 NAMED_SCOPE이며 hints에 없어도 그 이름을 보존한다. 문서 전체는 structure=null,selection=null; 실제 번호·목차·제목 위치를 요청하면 STRUCTURE, 문서만 알고 내용을 찾으면 FULLTEXT다. 두 검색 모두 지정 범위 안에서 실행한다. 명시한 대상이 없을 때만 AUTHORIZED_SCOPE,targets=[],user_quote=""다.\nlaw_title_hints는 위치 단서다. EXACT_TITLE/REGISTERED_ALIAS는 이름 일치, PARTIAL_TITLE/DERIVED_ABBREVIATION은 미확정 유사 후보다. question_span과 실제 title을 비교하되 후보 존재를 적용 근거로 삼지 않는다. title_hint_ids나 command.search_scope_change를 별도로 출력하지 않는다.\ncontext_quotes는 배경·업무 문맥의 연속 원문이다. 적용 가정과 원문 읽기 제외는 구분한다. 기존 판단의 정정·복원·재사용만 요구하고 대상이 없으면 CASE/NEED_TARGET,intent=null,search=null이며 필요한 대상을 reason에 쓴다. 새 법률 질문의 법령 미확인은 CASE_START로 조사한다.\nDIRECT/BROWSE는 command=null,intent=null,search=null,context_quotes=[]다. CASE answer는 빈 문자열이다. 실제 목록은 서버가 구성한다. CASE_START는 intent와 search를 작성한다. JSON만 출력한다.'

from .structure_selection import PROMPT as ENTRY_SELECTION_PROMPT
ENTRY_SCOPE_PROMPT = ENTRY_SELECTION_PROMPT + """
search.scope_decision은 이 최초 요청의 유일한 범위 판단이다. NAMED_SCOPE의 targets에는 실제 요청한 문서명과 구조만 넣고 user_quote는 현재 question의 연속 원문을 그대로 복사한다.
생략·대명사·약칭이 가리키는 법령은 문맥을 보고 해석한 문서명으로 targets에 작성하고 reason에 해석 이유를 쓴다. user_quote에는 해석 전 현재 질문의 원문을 그대로 보존한다. 확인되지 않은 이름을 지어내지 않는다.
문서 전체는 structure=null, selection=null이다. 번호의 복수·범위·제외는 selection으로 표현하고 structure=null이다. 번호 없는 목차 제목은 structure에 쓴다. 범위 없이 허용 자료에서 찾는 AUTHORIZED_SCOPE는 targets=[], user_quote=""다.
법령을 검색 대상으로 준 질문은 NAMED_SCOPE다. 검색 대상의 명시 여부와 실제 문서의 검색 가능 여부는 별개다. 법령명이 law_title_hints에 없거나 저장소에 없을 것 같아도 사용자가 그 법령에 따른 설명을 요청하면 NAMED_SCOPE와 그 이름을 보존한다. 문서 해석·검증 실패는 시스템이 미확인으로 처리하므로 허용 전체 범위로 바꾸지 않는다. 조문 번호가 없어도 특정 법령 전체를 요청한 것이다. 단순 배경 언급, 적용 가정, 읽기 제외를 구분하며 reason에 요청에 근거한 결정을 짧게 설명한다. STRUCTURE/FULLTEXT 모두 이 범위를 쓴다.
"""

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
    result = object_schema({'routing':case_routing_schema(),
        'command':{'anyOf':[command,{'type':'null'}]},
        'intent':{'anyOf':[intent,{'type':'null'}]},
        'context_quotes':{'type':'array','items':{'type':'string','minLength':1},'maxItems':8},
        'search':{'anyOf':[object_schema({'mode':{'enum':['STRUCTURE','FULLTEXT']},
            'title_hint_ids':{'type':'array','items':{'type':'string'},'maxItems':4},
            'reason':{'type':'string','minLength':1}}),{'type':'null'}]}})
    if model:
        command['properties'].pop('search_scope_change')
        command['required'].remove('search_scope_change')
        search = result['properties']['search']['anyOf'][0]
        search['properties'].pop('title_hint_ids')
        search['required'].remove('title_hint_ids')
        search['properties']['scope_decision'] = object_schema({
            'mode': {'enum': ['NAMED_SCOPE', 'AUTHORIZED_SCOPE']},
            'targets': deepcopy(command_scope_targets()),
            'user_quote': {'type': 'string'},
            'reason': {'type': 'string', 'minLength': 1}})
        search['required'].append('scope_decision')
    return constrain_schema(result) if model else result


def constrain_schema(request_schema):
    """Keep the public fields, but generate only complete entry alternatives.

    Rebuild after quote/history augmentation so every alternative retains the
    same request-local provenance and optional recall fields. Existing stored
    canonical entries still use schema(model=False).
    """
    result = deepcopy(request_schema)
    result.pop('anyOf', None)
    branches = []
    for mode, method in (('DIRECT', None), ('BROWSE', None),
                         ('CASE', 'NEED_TARGET'), ('CASE', 'CASE_START')):
        branch = deepcopy(result)
        props = branch['properties']
        route = props['routing']
        route['properties']['mode'] = {'const': mode}
        if mode == 'BROWSE':
            route['required'].append('catalogue')
            route['properties']['catalogue'] = route['properties']['catalogue']['anyOf'][0]
        else:
            route['properties']['catalogue'] = {'type': 'null'}
        if mode != 'DIRECT':
            route['properties']['answer'] = {'const': ''}
        else:
            route['properties']['answer']['minLength'] = 1
        if method is None:
            props['command'] = {'type': 'null'}
        else:
            command = deepcopy(props['command']['anyOf'][0])
            command['properties']['method_id'] = {'const': method}
            if method == 'NEED_TARGET':
                for field in ('facts', 'queries'):
                    command['properties'][field]['maxItems'] = 0
            props['command'] = command
        for field in ('intent', 'search'):
            props[field] = (deepcopy(props[field]['anyOf'][0])
                            if method == 'CASE_START' else {'type': 'null'})
        if method != 'CASE_START':
            props['context_quotes']['maxItems'] = 0
        branches.append(branch)
    result['anyOf'] = branches
    return result


class EntryConflict(output.OutputContractError, MemoryError):
    """Preserve the old domain exception boundary and structured diagnostics."""
    def __init__(self, message, issues):
        super().__init__(message, issues, category='DECISION_CONFLICT')


def decision_issues(value):
    """Collect field conflicts on a shape-validated proposal without editing it."""
    issues = []
    command = value['command']
    method = command['method_id'] if command is not None else None
    mode = value['routing']['mode']
    start = mode == 'CASE' and method == 'CASE_START'
    def add(code, path, related, expected):
        issues.append(output.issue(code, path, related=related, expected=expected))
    if mode in ('DIRECT', 'BROWSE') and command is not None:
        add('ENTRY_ROUTE_COMMAND_CONFLICT', '/command', ['/routing/mode'],
            'DIRECT/BROWSE requires command=null; CASE requires its selected command.')
    if mode == 'CASE' and command is None:
        add('ENTRY_COMMAND_REQUIRED', '/command', ['/routing/mode'],
            'CASE requires CASE_START or NEED_TARGET selected from the current request.')
    for field in ('intent', 'search'):
        if (value[field] is not None) != start:
            add('ENTRY_'+field.upper()+'_CONFLICT', '/'+field,
                ['/routing/mode', '/command/method_id'],
                'CASE/CASE_START requires intent and search objects; '
                'DIRECT/BROWSE/NEED_TARGET requires both null. Reconsider the whole decision from the same request.')
    if not start and value['context_quotes']:
        add('ENTRY_BACKGROUND_CONFLICT', '/context_quotes', ['/routing/mode', '/command/method_id'],
            'Only CASE/CASE_START can carry context_quotes; other decisions require [].')
    if method == 'NEED_TARGET':
        for field in ('facts', 'queries'):
            if command[field]:
                add('ENTRY_CLARIFICATION_STATE_CONFLICT', '/command/'+field, ['/command/method_id'],
                    'NEED_TARGET cannot edit case state: facts=[] and queries=[].')
    return issues


def validate_decision(value):
    issues = decision_issues(value)
    if issues:
        raise EntryConflict('request entry decision fields conflict', issues)


def rejected_branch(error, shape_schema):
    """Recover only a root branch-validation proposal for the stage validator.

    The native grammar validator rejects before invoke returns. Its chained
    JSON Schema error retains the exact object, which the same stage must reject
    with field paths and journal as the failed proposal. Never recover JSON,
    transport, integrity, or other validation failures through this boundary.
    """
    seen = set()
    cause = error.__cause__
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if (isinstance(cause, ValidationError) and cause.validator == 'anyOf'
                and not cause.absolute_path and isinstance(cause.instance, dict)):
            raw = cause.instance
            try:
                output.validate_shape(raw, shape_schema)
            except output.OutputContractError:
                return None
            if decision_issues(raw):
                return deepcopy(raw)
            return None
        cause = cause.__cause__
    return None


def command_scope_targets():
    from .query_scope import model_change_schema
    return model_change_schema()['properties']['targets']


def decode_scope(value, hints):
    """Mechanical projection of the sole model decision, never title inference."""
    validate_decision(value)
    out = deepcopy(value)
    search = out.get('search')
    if search is None:
        return out
    choice = search.pop('scope_decision')
    named = choice['mode'] == 'NAMED_SCOPE'
    if named != bool(choice['targets']):
        raise MemoryError('NAMED_SCOPE requires targets; AUTHORIZED_SCOPE must have no targets')
    if not named and choice['user_quote']:
        raise MemoryError('AUTHORIZED_SCOPE must have an empty scope quote')
    if not choice['reason'].strip():
        raise MemoryError('scope decision requires its request-specific reason')
    out['command']['search_scope_change'] = {
        'operation': 'REPLACE' if named else 'KEEP',
        'targets': deepcopy(choice['targets']), 'user_quote': choice['user_quote']}
    from ..navigation_match import norm
    names = {norm(t['document']) for t in choice['targets'] if t['document']}
    search['title_hint_ids'] = [h['hint_id'] for h in hints['candidates']
        if norm(h['title']) in names or norm(h.get('matched_label') or '') in names][:4]
    return out


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
    request_schema=constrain_schema(request_schema)
    shape_schema={k:v for k,v in request_schema.items() if k!='anyOf'}
    prepared={}
    def propose(payload,attempt):
        try:
            return repo.invoke(SYSTEM+ENTRY_SCOPE_PROMPT+('\n'+SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다.' if scoped else '')+recall_prompt+task_prompt,
                payload,request_schema,'request-entry' if not attempt else 'request-entry-repair')
        except output.OutputContractError as exc:
            raw=rejected_branch(exc,shape_schema)
            if raw is None:raise
            # check() immediately rejects this unchanged proposal before admission.
            return raw
    def check(raw, *, from_host=False):
        output.validate_shape(raw,schema(scoped) if from_host else shape_schema)
        validate_decision(raw)
        if not from_host:output.validate_shape(raw,request_schema)
        value=deepcopy(raw);history_ids=value.pop('history_ids',[])
        try:
            if not from_host:value=decode_scope(value,repo._entry_title_hints)
            routing,command,intent=accept(repo,context,value,scoped=scoped,admit=False)
        except output.OutputContractError:
            raise
        except MemoryError as exc:
            raise output.OutputContractError(str(exc),[output.issue('REQUEST_ENTRY_CONFLICT')],
                category='DECISION_CONFLICT') from exc
        # Admission is outside the model-correction boundary for permission/state failures.
        if command is not None:repo.admit(command,context)
        prepared.update(value=value,history_ids=history_ids,routing=routing,command=command,intent=intent,
            scope_decision=deepcopy((raw.get('search') or {}).get('scope_decision')))
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
        try:
            output.bounded_decision(repo,'request-entry',data,request_schema,propose,check,
                identity={'request':repo._entry_body,'principal':repo._entry_principal,
                    'binding':repo.executor.binding,'view':data})
        except output.OutputContractError as exc:
            # The sole owner has already spent or denied its remaining repair.
            # Keep the cause/field diagnostics, but do not advertise a new retry.
            raise output.OutputContractError(str(exc),
                [{**row,'repairable':False} for row in exc.issues],
                category=exc.category,repairable=False) from exc
    value=prepared['value'];routing=prepared['routing'];command=prepared['command'];intent=prepared['intent']
    if memory:wiki_recall.choose(repo.executor,prepared['history_ids'] if intent is not None else [],work.event)
    entry={'scope_decision':prepared.get('scope_decision'),'contract':POLICY,'request_hash':digest(repo._entry_body),
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
