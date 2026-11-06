"""Closed memory-operation catalogue. This is not a legal concept ontology."""
METHODS={
 'CASE_START':{'action':'START','stage':'INTENT','purpose':'새 질문의 목적과 조건을 분리한다'},
 'FACT_UPDATE':{'action':'CORRECT','stage':'ASSESS','purpose':'현재 사건 사실만 바꾸고 적용 판단을 다시 확인한다'},
 'STATE_RESTORE':{'action':'CORRECT','stage':'NONE','purpose':'기록된 특정 이벤트의 조건을 정확히 복원한다'},
 'PURPOSE_REVISE':{'action':'CORRECT','stage':'INTENT','purpose':'질문 자체의 수행 목적을 변경한다'},
 'RESEARCH_REPLAN':{'action':'CORRECT','stage':'PLAN','purpose':'문서 범위·검색 계획과 필요한 조건을 수정한다'},
 'RESEARCH_REENTER':{'action':'FOLLOW','stage':None,'purpose':'기존 원문을 재사용해 지정된 조사 단계 또는 실패한 검토 단계부터 다시 확인한다'},
 'RESEARCH_CONTINUE':{'action':'FOLLOW','stage':'SELECT','purpose':'직전 답변이 제안한 추가 조사·미확인 대상을 같은 목적·사실로 이어서 조사한다'},
 'ANSWER_PRESENT':{'action':'PRESENT','stage':'COMPOSE','purpose':'판단과 조건을 유지하고 최종 표현만 바꾼다'},
 'HISTORY_EXPLAIN':{'action':'INSPECT','stage':'NONE','purpose':'실제 정정 이벤트와 현재 판단 근거를 조회해 설명한다'},
 'EXPERIENCE_CONFIRM':{'action':'FINALIZE','stage':'NONE','purpose':'사용자가 확인한 현재 최종 판단 묶음을 발행한다'},
 'EXPERIENCE_REUSE':{'action':'REUSE','stage':'COMPOSE','purpose':'현재 조건과 동등한 최종 확인 경험을 활용한다'},
 'WIKI_RELINK':{'action':'REMAP','stage':'NONE','purpose':'위키의 경험 연결만 정정한다'},
 'NEED_TARGET':{'action':'CLARIFY','stage':'NONE','purpose':'기록에서 요청 대상을 특정할 수 없어 확인한다'},
}
FIELDS=('task','source_category','document_ids','facts','queries')

# This is a current-request intent review, separate from a reason/action review.
# The task is copied exactly from after_state only when it answers the current
# request; otherwise the reviewer supplies the missing purpose for correction.
TRANSITION_CHECK = {'type':'object','additionalProperties':False,
 'required':['valid','reason','request_relation','requested_task'],
 'properties':{'valid':{'type':'boolean'},'reason':{'type':'string'},
  'request_relation':{'enum':['NEW_TOPIC','FOLLOWUP','CONTINUE','CONDITION_CHANGE','REPEAT',
      'REVIEW','PRESENTATION','HISTORY','CONFIRMATION','RESTORE','REUSE','UNCLEAR']},
  'requested_task':{'type':['string','null']}}}
TRANSITION_PROMPT = '''
현재 발언과 명령 적용 후 실제 상태 transition.after를 독립 대조한다.
먼저 현재 발언의 관계 request_relation과 수행 목적 requested_task를 판단한다.
기존 기록은 참고 자료다. 이전 목표와 연결된다는 사실은 이전 질문의 그대로 재실행을 뜻하지 않는다.
새 측면·대상·근거를 묻는 FOLLOWUP이면 같은 goal을 보존하면서 task를 현재 목적에 맞게 변경해야 한다.
목적이 달라졌는데 RESEARCH_REENTER/task=null이면 기존 목적과 쟁점이 그대로 실행되므로 valid=false다.
RESEARCH_REENTER는 목적·조건이 같은 반복/중단 재개/재검토에만 쓴다. 새 주제 NEW_TOPIC은 CASE_START다.
CONTINUE는 직전 답변이 더 찾아보거나 이어서 읽을지 제안했고 사용자가 "응", "계속해줘", "이어서 찾아줘"처럼 그 조사를 이어가라고 동의한 요청이다. 목적·사실은 그대로이며 RESEARCH_CONTINUE로 같은 goal의 조사를 이어간다. requested_task에는 현재 task를 그대로 복사한다. 새 측면이나 대상을 추가로 묻는 FOLLOWUP과 구분한다.
CONDITION_CHANGE는 현재 facts의 실제 변경을 확인하고 기존 미변경 사실을 지우지 않는다.
현재 요청의 목적이 transition.after.task에 정확히 반영됐으면 requested_task에 그 값을 그대로 복사한다.
반영되지 않았으면 requested_task에 필요한 목적을 적고 valid=false로 반환한다. 표현 차이만으로 거절하지 않는다.
task 변경은 INTENT부터 쟁점을 다시 구성하고, facts 변경은 기존 목적을 유지해 재판단한다.
before와 after가 같은데 현재의 수행 목적이 달라졌다면 valid=true로 승인하지 않는다.
review_recovery가 null/available=false면 과거 검토 실패를 창작하지 않는다.
요청 관계·목적/조건·직접 검색 범위·실제 재시작 단계를 함께 검사한다. 법률 정답을 추측해 범위를 바꾸지 않는다.
reason만 고쳐서 같은 잘못된 명령을 통과시키지 않는다. 오류는 원래 명령 작성 모델에 전달된다.
'''


def transition_preview(command, context):
    """Pure application of submitted edits; never infer a new intent or scope."""
    from copy import deepcopy
    goal=next((g for g in context['goals'] if g['id']==command.get('target')),None)
    before=deepcopy(goal['state']) if goal else None
    after=deepcopy(before) if before is not None else {
        'task':context['utterance'],'source_category':'ALL','facts':[],'queries':[]}
    for field in FIELDS:
        value=command.get(field)
        if value is not None and not(field=='source_category' and value=='KEEP'):
            after[field]=deepcopy(value)
    if command.get('restore_fields'):
        event=next(e for e in goal['events'] if e['id']==command['restore_event'])
        for field in command['restore_fields']:after[field]=deepcopy(event['after'].get(field))
    # Host-owned document inventories are deliberately absent from model input.
    visible=lambda state:{k:deepcopy(v) for k,v in state.items() if k!='document_ids'}
    tracked=('task','source_category','facts','queries')
    return {'contract':'memory-command-transition-v1','target':command.get('target'),
        'before':visible(before) if before is not None else None,'after':visible(after),
        'changed_fields':[f for f in tracked if before is None or before.get(f)!=after.get(f)],
        'search_scope_change':deepcopy(command.get('search_scope_change')),
        'requested_entry':command['stage'],
        'purpose_change_rebuilds_issues_from':'INTENT'}


def validate_transition(command, transition, review):
    """Enforce declared intent versus actual edits, without choosing an action."""
    from . import output_contract as output
    output.validate_shape(review,TRANSITION_CHECK)
    if not review['valid']:
        raise output.OutputContractError(review['reason'],
            [output.issue('COMMAND_INTENT_CONFLICT','/check',expected=review)],category='DECISION_CONFLICT')
    relation=review['request_relation'];after=transition['after'];before=transition['before']
    issues=[]
    if relation!='UNCLEAR' and review['requested_task']!=after.get('task'):
        issues.append(output.issue('COMMAND_CURRENT_TASK_MISSING','/command/task',
            related=('/check/requested_task',),expected={'requested_task':review['requested_task'],
                'effective_task':after.get('task')}))
    if relation=='FOLLOWUP' and (before is None or command['method_id'] not in
            ('PURPOSE_REVISE','RESEARCH_REPLAN') or after.get('task')==before.get('task')):
        issues.append(output.issue('FOLLOWUP_PURPOSE_NOT_APPLIED','/command/method_id',
            related=('/command/task',),expected='Same goal, explicitly changed current purpose; rebuild its issues'))
    if relation=='CONTINUE' and (command['method_id'] not in ('RESEARCH_CONTINUE','RESEARCH_REENTER')
            or command.get('stage') not in ('INTENT','PLAN','RECALL','READ','SELECT')):
        issues.append(output.issue('CONTINUE_RESEARCH_NOT_RESUMED','/command/method_id',
            expected='RESEARCH_CONTINUE: same goal, purpose and facts; resume the investigation'))
    if relation=='NEW_TOPIC' and command['method_id']!='CASE_START':
        issues.append(output.issue('NEW_TOPIC_NOT_STARTED','/command/method_id',expected='CASE_START'))
    if relation=='CONDITION_CHANGE' and (before is None or after.get('facts')==before.get('facts')):
        issues.append(output.issue('CURRENT_FACT_CHANGE_NOT_APPLIED','/command/facts'))
    if issues:raise output.OutputContractError('Current request is not reflected in executable state',
        issues,category='DECISION_CONFLICT')


def assert_transition_applied(transition, command, state):
    """A reviewed proposal cannot execute a different typed question or facts."""
    from .errors import ContractError
    if transition.get('target')!=command.get('target') or any(
            state.get(f)!=transition['after'].get(f) for f in ('task','source_category','facts','queries')):
        raise ContractError('reviewed memory transition differs from actual execution state')


def review_recovery(assessment):
    """Expose verified record diagnostics; not a legal or automatic retry choice."""
    proposal = assessment.get('model_proposal') or {}
    failure = proposal.get('failure')
    if not isinstance(failure, dict):
        return None
    from copy import deepcopy
    eligible = bool(assessment.get('source_excerpt_reply')
        and proposal.get('review_status') == 'INCOMPLETE'
        and proposal.get('failure_code') == 'ASSESSMENT_CONTRACT_UNRESOLVED'
        and failure.get('category') in (
            'FINAL_READ_REVIEW_INVALID', 'REQUIREMENT_REVIEW_INVALID', 'OUTPUT_SHAPE_INVALID')
        and failure.get('repairable'))
    incomplete_acquisition = eligible and any(isinstance(row,dict) and
        row.get('code') == 'SCOPE_ACQUISITION_INCOMPLETE' for row in (failure.get('issues') or []))
    return {'failure': deepcopy(failure), 'available': eligible,
        'restart_stage': ('SELECT' if incomplete_acquisition else 'ASSESS') if eligible else None,
        'requires_source_completion': bool(incomplete_acquisition),
        'all_requested_sources_acquired': False if incomplete_acquisition else None,
        'source_acquisition_confirmed': bool(assessment.get('source_excerpt_reply')),
        'does_not_establish_missing_source': eligible and not incomplete_acquisition,
        'automatic_retry': False, 'requires_new_user_request': True,
        'legal_conclusion_confirmed': False}


def literal_repeat_target(context, body, principal):
    """Exact request/state identity, never semantic similarity or answer truth."""
    if body.get('question') != context['utterance']:return None
    events = [(e, g) for g in context['goals'] for e in g.get('events', []) if e.get('after')]
    if not events:return None
    event, goal = max(events, key=lambda pair:pair[0]['id'])
    state = goal['state']
    if (goal.get('status') != 'READY' or not goal.get('command_ready') or goal.get('pending')
            or state.get('scenario_context') or event.get('after') != state
            or event.get('utterance') != context['utterance']
            or state.get('task') != context['utterance']):return None
    allowed = set(principal.get('document_ids', []))
    requested = set(body.get('document_ids') or allowed)
    if set(state['document_ids']) != requested or not requested <= allowed:return None
    return goal['id']


def offered(context):
    """Expose only commands with at least one currently valid host-owned target."""
    goals=context['goals'];ids=[g['id'] for g in goals]
    ready=[g['id'] for g in goals if g.get('status')=='READY' and g.get('command_ready',True)]
    restorable=[g['id'] for g in goals if any(e.get('after') for e in g.get('events',[]))]
    knowledge=[k['id'] for k in context.get('knowledge',[])]
    result={}
    for name,method in METHODS.items():
        targets=([None] if name=='CASE_START' else [None,*ids] if name=='NEED_TARGET' else
                 ready if name in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','RESEARCH_CONTINUE') else
                 restorable if name=='STATE_RESTORE' else
                 [None,*ids] if name=='EXPERIENCE_REUSE' and knowledge else
                 ids if name!='EXPERIENCE_REUSE' else [])
        if name=='WIKI_RELINK' and not knowledge:targets=[]
        from .tool_policy import assess_availability
        if assess_availability('memory',name,binding=None,reason=None if targets else 'NO_VALID_TARGET').offered:
            result[name]={**method,'targets':targets}
    repeat = context.get('literal_repeat_target')
    if repeat:
        result = {name:{**item,'targets':[repeat]} for name,item in result.items()
                  if name in ('ANSWER_PRESENT','RESEARCH_REENTER','NEED_TARGET') and repeat in item['targets']}
    return result

def require_offered(command,context):
    item=offered(context).get(command.get('method_id'))
    if item is None or command.get('target') not in item['targets']:
        raise ValueError('memory method or target unavailable in current state')

def normalize(c,context):
    c=dict(c)
    mode=c.get('document_scope_mode')
    key=c.get('method_id')
    if mode=='KEEP':
        if c.get('document_ids') is not None:raise ValueError('KEEP scope must not change document IDs')
    elif mode=='AUTHORIZED':
        if key not in ('CASE_START','EXPERIENCE_REUSE','RESEARCH_REPLAN'):raise ValueError('authorized scope change requires a new question, reuse or replan')
        if c.get('document_ids') is not None:raise ValueError('AUTHORIZED scope is host-owned; document_ids must be null')
        if c.get('target') is not None:
            if key!='RESEARCH_REPLAN':raise ValueError('existing experience reuse must keep scope')
            # Authorization remains host-owned; never serialize its inventory into a command.
            pass
    elif mode=='EXPLICIT':
        if not c.get('document_ids'):raise ValueError('explicit scope requires document IDs')
    else:raise ValueError('document_scope_mode required')
    method=METHODS.get(c.get('method_id'))
    if method is None:raise ValueError('method_id must be an offered registered method')
    require_offered(c,context)
    c['action']=method['action']
    if method['stage'] is not None:c['stage']=method['stage']
    key=c['method_id'];given={f for f in FIELDS if c.get(f) is not None and not(f=='source_category' and c[f]=='KEEP')}
    scope_change=c.get('search_scope_change') or {}
    scope_changed=scope_change.get('operation','KEEP')!='KEEP'
    if scope_changed and key not in ('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN'):
        raise ValueError('search scope changes require a new question or research/purpose revision')
    if key in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','WIKI_RELINK','RESEARCH_REENTER','RESEARCH_CONTINUE'):
        if given or c.get('restore_fields'):raise ValueError(key+' cannot edit case facts, purpose, search or scope')
    if key=='FACT_UPDATE':
        if given!={'facts'} or c.get('restore_fields'):raise ValueError('FACT_UPDATE changes only facts; use RESEARCH_REPLAN for new search requirements')
    if key=='PURPOSE_REVISE' and not c.get('task'):raise ValueError('PURPOSE_REVISE requires changed task, not a condition or presentation request')
    if key=='RESEARCH_REPLAN' and not (given & {'queries','document_ids','source_category'} or scope_changed or mode=='AUTHORIZED'):raise ValueError('RESEARCH_REPLAN requires a retrieval-plan or scope change')
    if key=='RESEARCH_REENTER' and c.get('stage') not in ('INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE'):raise ValueError('RESEARCH_REENTER requires an explicitly selected stage')
    if key=='STATE_RESTORE':
        fs=c.get('restore_fields') or []
        if not fs:raise ValueError('STATE_RESTORE requires original event and restored fields')
        goals={g['id']:g for g in context['goals']};es=goals.get(c.get('target'),{}).get('events',[])
        origin=next((e for e in es if e['id']==c.get('restore_event')),None)
        if origin is None:raise ValueError('restore event is not offered for the selected goal')
        for f in given:
            if f not in fs or c[f]!=origin['after'][f]:raise ValueError('restoration cannot hide a different explicit state edit')
        c['stage']='INTENT' if 'task' in fs else 'PLAN' if set(fs)&{'source_category','document_ids','queries','search_scope'} else 'ASSESS'
    elif c.get('restore_fields') or c.get('restore_event') is not None:raise ValueError('restore fields require STATE_RESTORE')
    if key=='CASE_START' and c.get('target') is not None:raise ValueError('new case target must be null')
    return c

def command_branch(schema, name, context):
    """Expose the same mechanical field constraints enforced by normalize.

    Semantic intent, authorization and restoration receipts are still checked
    after the proposal; this function never chooses a method or a legal scope.
    Persisted legacy EXPLICIT commands remain readable by normalize.
    """
    from copy import deepcopy
    branch = deepcopy(schema)
    props = branch['properties']
    props['method_id'] = {'type':'string', 'const':name}
    targets = offered(context)[name]['targets']
    choices = ([{'type':'string','enum':[t for t in targets if t is not None]}]
               if any(t is not None for t in targets) else [])
    if None in targets:choices.append({'type':'null'})
    props['target'] = {'anyOf':choices}
    if name not in ('CASE_START','EXPERIENCE_REUSE','RESEARCH_REPLAN'):
        props['document_scope_mode'] = {'type':'string','const':'KEEP'}
    if name == 'EXPERIENCE_REUSE':
        branch['allOf'] = [{'anyOf':[
            {'properties':{'target':{'type':'null'}}},
            {'properties':{'document_scope_mode':{'const':'KEEP'}}}]}]
    if name not in ('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN'):
        props['search_scope_change'] = {'type':'object',
            'properties':{'operation':{'const':'KEEP'},'targets':{'type':'array','maxItems':0},
                          'user_quote':{'const':''}},
            'required':['operation','targets','user_quote'],'additionalProperties':False}
    if name != 'STATE_RESTORE':
        props['restore_event'] = {'type':'null'}
        props['restore_fields'] = {'type':'array','maxItems':0}
    if name in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','WIKI_RELINK','RESEARCH_REENTER','RESEARCH_CONTINUE','FACT_UPDATE'):
        for field in FIELDS:
            if name == 'FACT_UPDATE' and field == 'facts':continue
            props[field] = {'const':'KEEP'} if field == 'source_category' else {'type':'null'}
    if name == 'FACT_UPDATE':props['facts']['type'] = 'array'
    if name == 'PURPOSE_REVISE':props['task'].update(type='string',minLength=1)
    if name == 'RESEARCH_REENTER':
        props['stage'] = {'enum':['INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']}
    if name == 'RESEARCH_CONTINUE':
        props['stage'] = {'const':'SELECT'}
    if name in ('EXPERIENCE_REUSE','WIKI_RELINK'):
        props['knowledge_id'] = {'type':'string','enum':[k['id'] for k in context['knowledge']]}
    return branch


def repair_schema(schema, payload, context):
    """A mechanical field correction cannot replace a valid action/target.

    Semantic command-check or admission failures retain the full decision menu.
    No default command, inferred intent, or implicit field correction is applied.
    """
    from copy import deepcopy
    prior = payload.get('rejected_decision')
    if not isinstance(prior,dict) or prior.get('check') is not None:return schema
    raw = prior.get('command')
    if not isinstance(raw,dict):return schema
    item = offered(context).get(raw.get('method_id'))
    if not item or raw.get('target') not in item['targets']:return schema
    issues = payload.get('repair_contract',{}).get('validation',{}).get('issues',[])
    if not issues or any(not i.get('code','').startswith('SCHEMA_') or
        i.get('path','/') in ('/','/method_id','/target') for i in issues):return schema
    value = deepcopy(schema)
    value['properties']['method_id'] = {'const':raw['method_id']}
    value['properties']['target'] = {'const':raw['target']}
    value['description'] = '필드 형식 보완: 원래 method_id와 target을 유지한다. 새로운 목표로 바꾸지 않는다.'
    return value


def history_projection(events):
    out=[]
    for e in events:
        before=e['before'] or {};after=e['after'];changed=[f for f in (*FIELDS,'search_scope') if before.get(f)!=after.get(f)]
        out.append({'event_id':e['id'],'kind':e['kind'],'correction_ordinal':e.get('correction_ordinal'),
          'utterance':e['utterance'],'method_id':e['command'].get('method_id'),'reason':e['command'].get('reason'),
          'restore_event':e['command'].get('restore_event'),'restore_fields':e['command'].get('restore_fields',[]),
          'changes':{f:{'before':before.get(f),'after':after.get(f)} for f in changed}})
    return out

def history_answer(events,answer):
    import json
    records=history_projection(events);lines=['현재 판단과 실제 수정 이력입니다.','',answer['text'],'','수정 이력:']
    names={'task':'질문 목적','source_category':'문서 구분','document_ids':'문서 범위','facts':'사건 조건','queries':'검색 계획','search_scope':'직접 검색 범위'}
    for r in records:
        label='최초 질문' if r['kind'] in ('START','REUSE') else str(r['correction_ordinal'])+'차 정정' if r['correction_ordinal'] else '표현·검토 요청'
        lines.append(f"- [{r['event_id']}] {label}: {r['utterance']}")
        for f,v in r['changes'].items():lines.append('  '+names[f]+': '+json.dumps(v['before'],ensure_ascii=False)+' → '+json.dumps(v['after'],ensure_ascii=False))
        if r['restore_event'] is not None:lines.append(f"  기록 [{r['restore_event']}]의 지정 조건을 복원했습니다.")
        if r['method_id']:lines.append('  적용 방법: '+r['method_id']+' — '+METHODS[r['method_id']]['purpose'])
    lines+=['','현재 판단의 원문 근거:']
    for c in answer['claims']:lines.append('- '+c['text']+' / '+c['source_id']+' / 원문: '+c['quote'])
    return {**answer,'text':'\n'.join(lines)},records
