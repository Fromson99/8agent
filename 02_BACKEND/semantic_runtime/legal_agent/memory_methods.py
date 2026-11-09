"""Closed memory-operation catalogue. This is not a legal concept ontology."""
from copy import deepcopy
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
알고 싶은 내용 자체가 바뀌어 새 측면을 묻는 FOLLOWUP이면 같은 goal을 보존하면서 task를 현재 목적에 맞게 변경해야 한다. 목적은 같고 아직 확인하지 못한 대상·근거만 지정했으면 CONTINUE다.
목적이 달라졌는데 RESEARCH_REENTER/task=null이면 기존 목적과 쟁점이 그대로 실행되므로 valid=false다.
RESEARCH_REENTER는 목적·조건이 같은 반복/중단 재개/재검토에만 쓴다. 새 주제 NEW_TOPIC은 CASE_START다.
NEW_TOPIC은 기존 goal의 질문·답변이 다루지 않은 다른 제도·의무·기구·주제를 직접 말하고 묻는 완결된 질문이다. 같은 회사·규정집·업무 분야라는 것만으로 FOLLOWUP이 아니다. 법령이나 묻는 측면을 생략한 짧은 질문이라도 다른 기구·제도·조문을 직접 말하면 NEW_TOPIC이다(예: 주주총회 결의 요건을 물은 뒤 "이사회 결의는?"은 다른 기관의 결의 요건이므로 NEW_TOPIC, 생략한 상법·결의 요건은 task에 이어받는다). 같은 법령, 같은 종류의 요건이라는 것만으로 FOLLOWUP이 아니다. FOLLOWUP은 같은 기구·제도·조문에서 다른 측면(조건·예외·다른 항·기간 등)을 묻는 경우이며, 같은 기구·제도에 대해 다른 조문을 묻는 것(예: 위험관리위원회 심의사항 다음의 "자산총액 2조원 이상이면 위험관리위원회를 꼭 둬야 해?"는 설치 의무 조문)도 FOLLOWUP이다. 현재 요청이 기존 goal의 대상과 조금이라도 이어져 있으면 FOLLOWUP/CONTINUE/PRESENTATION 중 하나이고 NEW_TOPIC이 아니다. 사용자가 "새로 찾아줘", "새 질문으로", "별도로 조사해줘"처럼 새 질문임을 직접 말한 요청은 내용이 이어져 있어도 NEW_TOPIC이다. 다른 대상에 대한 질문을 PURPOSE_REVISE·RESEARCH_REPLAN으로 기존 goal에 덮어쓰면 기존 질문이 사라지므로 valid=false다. NEW_TOPIC의 requested_task는 현재 요청 문장 그대로이며(현재 요청이 생략한 법령·측면을 관련 질문에서 이어받아 task에 쓴 경우는 그 task) 이전 질문의 내규/외규 표시와 현재 요청이 묻지 않은 대상·조건을 붙이지 않는다.
context.related_selection은 이 명령 전에 고른 관련 이전 질문이고 question_catalogue는 이 대화의 이전 질문 전체다. 관련 질문을 빠뜨렸거나 무관한 질문을 골라 명령이 현재 요청과 어긋났으면 valid=false로 그 이유를 쓴다.
transition.applies_pending_request가 있으면 현재 발언은 적용되지 않았던 그 요청을 어떻게 처리할지에 대한 답이다. 요청 관계와 requested_task는 그 대기 요청의 내용으로 판단한다(새 질문으로 하라는 답이면 NEW_TOPIC, 이전 질문에 이어서 하라는 답이면 FOLLOWUP).
CONTINUE는 직전 답변이 더 찾아보거나 이어서 읽을지 제안했고 사용자가 "응", "계속해줘", "이어서 찾아줘"처럼 그 조사를 이어가라고 동의한 요청이다. 질문의 목적은 그대로 두고 직전 답변에서 아직 확인하지 못한 대상·근거(제안된 조문, 특정 법령의 해당 규정 등)를 지정해 확인하라는 요청도 CONTINUE다. 목적·사실은 그대로이며 RESEARCH_CONTINUE로 같은 goal의 조사와 답변을 이어간다. requested_task에는 현재 task를 그대로 복사한다. 알고 싶은 내용 자체가 바뀌는 FOLLOWUP과 구분한다.
직전 답변에서 이미 설명한 부분을 다시 묻거나 그 부분만 더 자세히 묻는 요청도 목적이 같은 CONTINUE다(예: 정관 변경 요건 답변이 종류주주총회 결의까지 설명했는데 "종류주식을 발행한 회사면 뭐가 더 필요해?"). requested_task에는 현재 task를 그대로 복사하고, reason에는 직전 답변의 어느 부분을 다시 묻는지 쓴다. 이 요청을 직전 답변이 읽지 않았다고 안내한 위치를 읽자는 동의로 해석하지 않는다. continue_reads는 사용자가 그 위치를 지목하거나 이어서 읽자고 했을 때만 고른다.
CONDITION_CHANGE는 현재 facts의 실제 변경을 확인하고 기존 미변경 사실을 지우지 않는다.
현재 요청의 목적이 transition.after.task에 정확히 반영됐으면 requested_task에 그 값을 그대로 복사한다.
반영되지 않았으면 requested_task에 필요한 목적을 적고 valid=false로 반환한다. 표현 차이만으로 거절하지 않는다.
task 변경은 INTENT부터 쟁점을 다시 구성하고, facts 변경은 기존 목적을 유지해 재판단한다.
before와 after가 같은데 현재의 수행 목적이 달라졌다면 valid=true로 승인하지 않는다.
review_recovery가 null/available=false면 과거 검토 실패를 창작하지 않는다.
요청 관계·목적/조건·직접 검색 범위·실제 재시작 단계를 함께 검사한다. 법률 정답을 추측해 범위를 바꾸지 않는다.
PRESENTATION은 대상 goal의 답변(previous_response)에 이미 있는 내용의 일부를 다시 묻거나 표현만 바꿔 달라는 요청이다(예: 앞서 답한 면제 기준의 금액을 "얼마였지?"라고 다시 묻기). 앞선 다른 주제의 질문으로 돌아와 묻는 경우도 같다. 목적은 그대로이며 requested_task에는 대상 goal의 현재 task를 그대로 복사한다. FOLLOWUP은 그 답변이 다루지 않은 새 측면을 묻는 경우다.
아직 답을 찾지 못했거나 덜 찾은 질문에 사용자가 찾을 법령·조문·위치·용어를 알려 주는 요청은 그 질문의 목적이 같은 CONTINUE다. 목적은 그대로 두고 그 단서로 검색 범위·검색어를 바꾸는 RESEARCH_REPLAN 또는 RESEARCH_CONTINUE가 맞다. 처음 언급된 조문이라는 이유만으로, 또는 이전 답변이 조사한 법령과 다른 법령이라는 이유만으로 NEW_TOPIC으로 보지 않는다(직전 답변이 어느 법령·조문에 있는지 물었고 사용자가 "~을 보면 될 거야"로 법령·조문을 알려 준 경우는 그 질문의 CONTINUE이며, 그것을 CASE_START로 만들면 valid=false다).
명령과 관계는 이렇게 대응한다: CASE_START=NEW_TOPIC, PURPOSE_REVISE=FOLLOWUP, RESEARCH_REPLAN=FOLLOWUP(목적 변경) 또는 CONTINUE(목적 그대로 단서로 검색 계획만 변경), RESEARCH_CONTINUE=CONTINUE, RESEARCH_REENTER=REPEAT·REVIEW·CONTINUE, ANSWER_PRESENT=PRESENTATION, FACT_UPDATE=CONDITION_CHANGE, HISTORY_EXPLAIN=HISTORY, EXPERIENCE_CONFIRM=CONFIRMATION, STATE_RESTORE=RESTORE, EXPERIENCE_REUSE·WIKI_RELINK=REUSE, NEED_TARGET=UNCLEAR. 명령이 현재 요청에 맞다고 판단해 valid=true를 쓰면 request_relation은 그 명령에 대응하는 관계를 쓴다. 다른 관계가 맞다고 보면 valid=false와 그 관계를 쓴다.
reason만 고쳐서 같은 잘못된 명령을 통과시키지 않는다. 오류는 원래 명령 작성 모델에 전달된다.
'''


PENDING_METHODS=('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN','RESEARCH_CONTINUE')
RELATED_VERSION='related-questions-v2'


def question_catalogue(context, answer_chars=400):
    """Every earlier question of this conversation, compact, for choosing the related ones.

    Data only: the question purpose, what the user actually said, the start of the answer.
    """
    goals=context.get('goals',[])
    latest=goals[-1]['id'] if goals else None
    answers={}
    for turn in context.get('recent_dialogue',[]):
        if turn.get('speaker')=='assistant' and turn.get('goal_id'):answers[turn['goal_id']]=turn.get('text','')
    rows=[]
    for order,g in enumerate(goals,1):
        said=list(dict.fromkeys(e['utterance'] for e in g.get('events',[]) if e.get('utterance')))[-3:]
        previous=g.get('previous_response') or {}
        answer=previous.get('text') or answers.get(g['id'],'')
        guide=previous.get('guidance') or {}
        row={'goal_id':g['id'],'order':order,'question':g['state'].get('task'),
            'user_requests':said,'answer_start':str(answer)[:answer_chars],'latest':g['id']==latest,
            'earlier_topic':bool(g.get('earlier_topic')),'status':g.get('status')}
        if previous:
            # Whether the answer was found matters: a later law or article name may be guidance for it.
            row['answer_found']=bool(previous.get('legal_conclusion_confirmed')) and previous.get('answer_coverage') not in ('PARTIAL','INSUFFICIENT')
            row['asked_user']=[str(q.get('question','')) for q in guide.get('questions',[]) if isinstance(q,dict)][:3]
        rows.append(row)
    return rows


def related_schema(goal_ids):
    """One yes/no judgment per earlier question (q1..qN, in question order), after the overall reason.

    ADR-1449: with a free list Qwen named the related question in its reason and still returned [].
    """
    judgment={'type':'object','additionalProperties':False,'required':['related','why'],
              'properties':{'related':{'type':'string','enum':['YES','NO','UNSURE']},'why':{'type':'string','minLength':1}}}
    keys=['q'+str(i) for i in range(1,len(goal_ids)+1)]
    return {'type':'object','additionalProperties':False,'required':['reason',*keys],
            'properties':{'reason':{'type':'string','minLength':1},**{k:deepcopy(judgment) for k in keys}}}


def check_related(value, goal_ids):
    """Shape check; the server keeps the questions judged related and maps each to its goal ID.

    The judgment itself stays the model's. Returns the stored form.
    """
    from . import output_contract as output
    output.validate_shape(value,related_schema(goal_ids))
    rows=lambda answer:[{'order':i,'goal_id':goal,'why':value['q'+str(i)]['why']}
                        for i,goal in enumerate(goal_ids,1) if value['q'+str(i)]['related']==answer]
    return {'reason':value['reason'],'related':rows('YES'),'unsure':rows('UNSURE')}


def scope_quote_issues(command, allowed_texts):
    """A scope change quotes one contiguous span of the user's own words (same rule query_scope.resolve applies
    at execution), checked while the command can still be corrected."""
    from ..navigation_match import norm
    from . import output_contract as output
    change=command.get('search_scope_change') or {}
    if change.get('operation','KEEP')=='KEEP':return []
    quote=change.get('user_quote') or ''
    texts=[t for t in allowed_texts if isinstance(t,str) and t]
    if not quote or not any(quote in t for t in texts):
        return [output.issue('SCOPE_QUOTE_NOT_USER_WORDS','/search_scope_change/user_quote',
            expected={'rule':'user_quote is one contiguous span copied from exactly one of these user texts; do not join texts',
                      'user_texts':texts})]
    if command.get('method_id')!='CASE_START':
        for target in change.get('targets') or []:
            for value in (target.get('document'),target.get('structure')):
                if value and norm(value) not in norm(quote):
                    return [output.issue('SCOPE_NAME_NOT_IN_QUOTE','/search_scope_change/targets',
                        expected={'rule':'for a follow-up command every target name appears inside user_quote','name':value,'user_quote':quote})]
    return []


def stored_related(value, goal_ids):
    """A stored selection still names questions of this conversation, each once."""
    from .errors import ContractError
    rows=(value or {}).get('related') if isinstance(value,dict) else None
    if not isinstance(rows,list) or not isinstance(value.get('reason'),str):
        raise ContractError('related question selection missing')
    ids=[r.get('goal_id') for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or len(ids)!=len(set(ids)) or not set(ids)<=set(goal_ids):
        raise ContractError('related question selection names an unknown or repeated question')
    unsure=value.get('unsure',[])
    if not isinstance(unsure,list) or any(not isinstance(r,dict) or r.get('goal_id') not in goal_ids for r in unsure):
        raise ContractError('related question selection names an unknown question')
    for r in [*rows,*unsure]:
        if not r.get('host_record') and goal_ids.index(r['goal_id'])+1!=r.get('order'):
            raise ContractError('related question order and goal differ')
    return ids


def pending_requests(context):
    """User requests of the trailing clarification exchange that were not applied.

    Host-owned exact text: a reply such as "새 질문으로 해줘" selects one by event_id.
    """
    from .query_scope import pending_clarifications
    rows=[]
    for turn in pending_clarifications(context.get('recent_dialogue',[])):
        if turn.get('speaker')=='user' and turn.get('text') and turn['text']!=context.get('utterance'):
            rows.append({'event_id':turn['event_id'],'text':turn['text']})
    return rows


def effective_request(command, context):
    """The request a command executes: the current utterance or the selected pending one."""
    chosen=command.get('pending_request')
    if chosen is None:return context['utterance']
    row=next((r for r in pending_requests(context) if r['event_id']==chosen),None)
    if row is None:raise ValueError('pending_request is not an unapplied request of this conversation')
    return row['text']


def _marker(text):
    from ..pipeline import _QUESTION_SOURCE_PREFIX
    match=_QUESTION_SOURCE_PREFIX.match(text) if isinstance(text,str) else None
    return (match.group(0),text[match.end():].strip()) if match else ('',text.strip() if isinstance(text,str) else text)


def bind_request_marker(task, request):
    """A new question's 내규/외규 marker is the request's own UI configuration.

    A marker copied from an earlier turn is replaced by the request's marker (or removed);
    the purpose text itself is never rewritten.
    """
    if not isinstance(task,str):return task
    _,body=_marker(task)
    marker,_=_marker(request)
    return marker+body if body else task


def same_task(a, b):
    """Purpose equality without the UI source marker or surrounding whitespace."""
    return isinstance(a,str) and isinstance(b,str) and _marker(a)[1]==_marker(b)[1]


def transition_preview(command, context):
    """Pure application of submitted edits; never infer a new intent or scope."""
    from copy import deepcopy
    goal=next((g for g in context['goals'] if g['id']==command.get('target')),None)
    before=deepcopy(goal['state']) if goal else None
    after=deepcopy(before) if before is not None else {
        'task':effective_request(command,context),'source_category':'ALL','facts':[],'queries':[]}
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
        **({'applies_pending_request':effective_request(command,context)} if command.get('pending_request') is not None else {}),
        'purpose_change_rebuilds_issues_from':'INTENT'}


def validate_transition(command, transition, review, request=None):
    """Enforce declared intent versus actual edits, without choosing an action."""
    from . import output_contract as output
    output.validate_shape(review,TRANSITION_CHECK)
    relation=review['request_relation'];after=transition['after'];before=transition['before']
    override=None
    if not review['valid']:
        # ADR-1456 S8 T4 (run-2): the reviewer wrote valid=false while naming the relation of the very
        # command proposed (CONTINUE for RESEARCH_CONTINUE) and asking for a task text the same-purpose
        # relation forbids changing. A same-purpose relation that maps to the proposed command on an
        # unchanged task is self-consistent; the contradiction is recorded, not turned into a refusal.
        # FOLLOWUP/NEW_TOPIC/CONDITION_CHANGE disagreements are still refusals.
        # Only the internal contradiction is overridden: a same-purpose relation (task unchanged by
        # definition) whose requested_task nevertheless differs from the unchanged task. A rejection
        # that keeps the task (e.g. a wrong continue_reads choice) is a genuine refusal.
        mapped=relation in SAME_PURPOSE_METHODS.get(command['method_id'],())
        if (mapped and before is not None and same_task(after.get('task'),before.get('task'))
                and not same_task(review['requested_task'],after.get('task'))):
            override={'kind':'COMMAND_CHECK_SELF_CONTRADICTION','relation':relation,'method_id':command['method_id'],
                      'reviewer_reason':review['reason'],'reviewer_task':review['requested_task'],'effective_task':after.get('task')}
        else:
            raise output.OutputContractError(review['reason'],
                [output.issue('COMMAND_INTENT_CONFLICT','/check',expected=review)],category='DECISION_CONFLICT')
    issues=[]
    # A new question whose task is the user's own request text cannot be missing the
    # current purpose; a reviewer's paraphrase of it is not a conflict.
    verbatim=(relation=='NEW_TOPIC' and command['method_id']=='CASE_START'
              and request is not None and same_task(after.get('task'),request))
    # ADR-1456 S8 T4: the reviewer approved RESEARCH_CONTINUE (valid=true, CONTINUE) but copied the task
    # with an annotation "(제24조 관련 확인)". A same-purpose relation on a command that leaves the task
    # unchanged has, by definition, the current task as its purpose; the reviewer's paraphrase of that
    # unchanged task is not a conflict. A FOLLOWUP/NEW_TOPIC purpose is still compared exactly.
    unchanged_purpose=(relation in ('CONTINUE','PRESENTATION','REPEAT','REVIEW','CONFIRMATION','HISTORY','RESTORE','REUSE')
                       and before is not None and same_task(after.get('task'),before.get('task')))
    if relation!='UNCLEAR' and not verbatim and not unchanged_purpose and not same_task(review['requested_task'],after.get('task')):
        issues.append(output.issue('COMMAND_CURRENT_TASK_MISSING','/command/task',
            related=('/check/requested_task',),expected={'requested_task':review['requested_task'],
                'effective_task':after.get('task')}))
    if relation=='FOLLOWUP' and (before is None or command['method_id'] not in
            ('PURPOSE_REVISE','RESEARCH_REPLAN') or after.get('task')==before.get('task')):
        issues.append(output.issue('FOLLOWUP_PURPOSE_NOT_APPLIED','/command/method_id',
            related=('/command/task',),expected='Same goal, explicitly changed current purpose; rebuild its issues'))
    guided_replan=(command['method_id']=='RESEARCH_REPLAN' and before is not None
                   and same_task(after.get('task'),before.get('task')))
    if relation=='CONTINUE' and ((command['method_id'] not in ('RESEARCH_CONTINUE','RESEARCH_REENTER') and not guided_replan)
            or command.get('stage') not in ('INTENT','PLAN','RECALL','READ','SELECT')):
        issues.append(output.issue('CONTINUE_RESEARCH_NOT_RESUMED','/command/method_id',
            expected='RESEARCH_CONTINUE: same goal, purpose and facts; resume the investigation'))
    if relation=='NEW_TOPIC' and command['method_id']!='CASE_START':
        issues.append(output.issue('NEW_TOPIC_NOT_STARTED','/command/method_id',expected='CASE_START'))
    if relation=='CONDITION_CHANGE' and (before is None or after.get('facts')==before.get('facts')):
        issues.append(output.issue('CURRENT_FACT_CHANGE_NOT_APPLIED','/command/facts'))
    if issues:raise output.OutputContractError('Current request is not reflected in executable state',
        issues,category='DECISION_CONFLICT')
    return override


SAME_PURPOSE_METHODS={'RESEARCH_CONTINUE':('CONTINUE',),'RESEARCH_REENTER':('CONTINUE','REPEAT','REVIEW'),
                      'ANSWER_PRESENT':('PRESENTATION',),'HISTORY_EXPLAIN':('HISTORY',),'EXPERIENCE_CONFIRM':('CONFIRMATION',)}


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

def proposed_reads(context, target):
    """IDs the previous answer of this goal itself proposed to read next."""
    goal=next((g for g in context['goals'] if g['id']==target),None) or {}
    guidance=(goal.get('previous_response') or {}).get('guidance') or {}
    return [r['read_id'] for r in guidance.get('proposed_reads',[]) if isinstance(r,dict) and r.get('read_id')]


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
    reads=list(c.get('continue_reads') or [])
    if reads:
        if key!='RESEARCH_CONTINUE':raise ValueError('continue_reads belongs to RESEARCH_CONTINUE only')
        if len(reads)!=len(set(reads)):raise ValueError('duplicate continue_reads')
        if set(reads)-set(proposed_reads(context,c.get('target'))):
            raise ValueError('continue_reads must be proposed_reads of the target goal answer')
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
    if c.get('pending_request') is not None:
        if key not in PENDING_METHODS:raise ValueError('pending_request applies only to a new question or a changed purpose')
        effective_request(c,context)
    if key=='CASE_START':
        request=effective_request(c,context)
        # The UI 내규/외규 marker belongs to the executed request, never to an earlier turn.
        if c.get('task') is not None:c['task']=bind_request_marker(c['task'],request)
        # A new question that names no source category searches the authorized scope; an earlier
        # turn's 내규/외규 choice is not this request's configuration (ALL only widens, never grants).
        marker,text=_marker(request)
        if (not marker and c.get('source_category') in ('internal','external')
                and not any(word in text for word in ('내규','외규'))):
            c['source_category']='ALL'
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
        reads = list(dict.fromkeys(i for t in targets if t is not None for i in proposed_reads(context,t)))
        if reads:
            props['continue_reads'] = {'type':'array','maxItems':min(4,len(reads)),'items':{'type':'string','enum':reads}}
            if 'continue_reads' not in branch.get('required',[]):
                branch['required'] = [*branch.get('required',[]),'continue_reads']
    if name != 'RESEARCH_CONTINUE' or not reads:
        props['continue_reads'] = {'type':'array','maxItems':0,'items':{'type':'string'}}
    if name in ('EXPERIENCE_REUSE','WIKI_RELINK'):
        props['knowledge_id'] = {'type':'string','enum':[k['id'] for k in context['knowledge']]}
    pending = [r['event_id'] for r in pending_requests(context)]
    props['pending_request'] = ({'anyOf':[{'type':'integer','enum':pending},{'type':'null'}]}
                                if pending and name in PENDING_METHODS else {'type':'null'})
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
        i.get('path','/') in ('/','/method_id','/target','/pending_request') for i in issues):return schema
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
