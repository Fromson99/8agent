"""Explicit review actions on the existing owner lock and request ledger."""
from copy import deepcopy
from ..contracts import digest
from .corrected_memory import Memory, MemoryError, Conflict
from .errors import ContractError
from .review_explanation import bind_case, verify


def execute(repo, body, principal):
    request = body['review_action']
    if not isinstance(request, dict) or set(request) - {'schema_version','action_id','view_hash','case_id','revision','operation_id','input'}:
        raise MemoryError('invalid review action fields')
    if request.get('schema_version') != 'review-action-v1' or request.get('operation_id') != body['request_id']:
        raise MemoryError('review operation must equal the durable request ID')
    if type(request.get('revision')) is not int or request['revision'] < 1:
        raise MemoryError('review revision must be a positive integer')
    goal = repo.goal(request.get('case_id'), body['session_id'])
    if not goal or goal['status'] != 'READY' or goal['revision'] != request.get('revision'):
        raise Conflict('stale review action; reload the current explanation')
    if not set(goal['state']['document_ids']) <= set(principal['document_ids']):
        raise MemoryError('review action document scope denied')
    parts = repo.parts(goal['id']); route = repo.route(goal['id'])
    repo.executor.verify(parts['READ']['payload'])
    assessment = parts['ASSESS']['payload']
    from ..ontology_work.runtime import assert_assessment
    assert_assessment(assessment, principal['document_ids'])
    saved = assessment.get('review_explanation')
    if not saved:
        raise Conflict('review explanation was not recorded for this revision')
    explanation = bind_case(saved, {'question_id':goal['id'], 'revision':goal['revision'], 'route_id':route['id']}, goal['state'])
    if explanation['content_sha256'] != request.get('view_hash'):
        raise Conflict('review view changed')
    action = next((a for a in explanation['actions'] if a['id'] == request.get('action_id')), None)
    if action is None or not action['enabled']:
        raise MemoryError('review action not offered')
    if body.get('use_llm') is False and action['kind'] not in ('VIEW_REVIEW','WHAT_IF'):
        raise MemoryError('this review action requires model execution')
    supplied = request.get('input') or {}
    if not isinstance(supplied, dict):
        raise MemoryError('review action input must be an object')
    kind = action['kind']
    if kind in ('VIEW_REVIEW', 'WHAT_IF', 'SCENARIO_REVIEW'):
        if body['question'] != action['label']:
            raise MemoryError('structured action and free text disagree')
        result = {'status':goal['status'], 'goal_id':goal['id'], 'revision':goal['revision'],
            'answer':parts['COMPOSE']['payload'], 'executed':[], 'method_id':kind}
        if kind in ('WHAT_IF','SCENARIO_REVIEW'):
            if not {'kind','changes'} <= set(supplied) or set(supplied) - {'kind','changes','bindings'}:
                raise MemoryError('scenario requires kind and changes')
            from .scenario_branch import compare
            result['scenario_comparison'] = compare(explanation, goal['state'], supplied['changes'],
                kind=supplied['kind'], operation_id=request['operation_id'], bindings=supplied.get('bindings'))
        elif supplied:
            raise MemoryError('review view takes no input')
        if kind == 'SCENARIO_REVIEW':
            return semantic_branch(repo,body,principal,goal,parts,explanation,result['scenario_comparison'])
        return result
    command = {'method_id':'RESEARCH_REENTER', 'document_scope_mode':'KEEP', 'action':'FOLLOW',
        'target':goal['id'], 'knowledge_id':None, 'stage':'ASSESS', 'task':None, 'source_category':'KEEP',
        'document_ids':None, 'facts':None, 'queries':None, 'restore_event':None, 'restore_fields':[],
        'format':'prose', 'reason':'사용자가 현재 검토 항목에 결속된 후속 행동을 명시적으로 요청함'}
    if kind == 'REQUEST_FACT':
        if set(supplied) != {'name','value'} or not all(isinstance(supplied[k],str) and supplied[k].strip() for k in supplied):
            raise MemoryError('fact action requires name and value')
        if supplied['name'] != action['fact_name']:
            raise MemoryError('fact name differs from the offered missing fact')
        if body['question'] != supplied['value']:
            raise MemoryError('fact input and free text disagree')
        facts = [deepcopy(f) for f in goal['state']['facts'] if f['name'] != supplied['name']]
        facts.append({'name':supplied['name'], 'value':supplied['value']})
        command.update(method_id='FACT_UPDATE', action='CORRECT', facts=facts)
    elif kind in ('REVIEW_AGAIN', 'READ_SCOPE', 'RESEARCH'):
        if supplied or body['question'] != action['label']:
            raise MemoryError('review action and free text disagree')
    else:
        raise MemoryError('unsupported review action')
    if kind in ('READ_SCOPE','RESEARCH'):
        command['stage']='SELECT'
    if kind == 'REVIEW_AGAIN':
        # Explicit rerun is bounded per unchanged facts/originals, including
        # across new case revisions. Different operation IDs cannot reset it.
        signature=digest([goal['state'], parts['SELECT']['payload'].get('selected_originals')])
        prior=repo.db.execute("SELECT request FROM event WHERE goal=? AND kind='REVIEW_ACTION_RESERVED' AND json_extract(journal_text(command),'$.signature')=?",
            (goal['id'],signature)).fetchone()
        if prior and prior[0] != body['request_id']:
            raise Conflict('same review already requested; new facts or originals are required')
        if not prior:
            from .corrected_memory import encoded
            repo.db.execute('INSERT INTO event(goal,request,utterance,command,kind) VALUES(?,?,?,?,?)',
                (goal['id'],body['request_id'],body['question'],encoded({'signature':signature,
                 'action_id':action['id'],'target_refs':action.get('target_refs',[])}),'REVIEW_ACTION_RESERVED'))
    context = repo.context(body['session_id'], principal, body['question'])
    repo.admit(command, context)
    repo._review_command = command
    repo._review_question = goal['state']['task']
    try:
        return Memory._execute(repo, body, principal)
    finally:
        repo.__dict__.pop('_review_command', None)
        repo.__dict__.pop('_review_question', None)


def semantic_branch(repo, body, principal, goal, parts, explanation, comparison):
    """Fork verified stages into a new goal, then use the ordinary ASSESS loop."""
    state=deepcopy(goal['state'])
    if state.get('scenario_context'):
        raise MemoryError('create a new assumption from the original case baseline')
    if comparison['unbound_changes']:
        raise MemoryError('가정 필드에 교체할 기존 사실을 연결하세요: ' + ', '.join(comparison['unbound_changes']) + '; 제공된 fact_options의 ID를 bindings에 지정하세요.')
    from . import scenario_facts, scenario_review, scenario_application, scenario_computation
    state['facts']=scenario_facts.effective(state,comparison['changes'],comparison['fact_bindings'],comparison['kind'])
    replaced={i for k,ids in comparison['fact_bindings'].items() if comparison['kind']=='FACT' and k in comparison['changes'] for i in ids}
    context={'schema_version':'scenario-context-v4', 'scenario_id':comparison['id'],
        'baseline':deepcopy(explanation['case']), 'baseline_hash':explanation['content_sha256'],
        'baseline_state_hash':digest(goal['state']), 'source_heads':deepcopy(repo.route(goal['id'])['payload']['judgment_refs']),
        'kind':comparison['kind'], 'changes':deepcopy(comparison['changes']),
        'baseline_task':goal['state']['task'], 'fact_bindings':deepcopy(comparison['fact_bindings']),
        'superseded_facts':[r for r in comparison['fact_options'] if r['id'] in replaced],
        'evaluations':deepcopy(comparison['evaluations']),
        'changed_fields':deepcopy(comparison['changed_fields']),
        'typed_comparisons':deepcopy(comparison['comparisons']), 'unresolved':deepcopy(comparison['unresolved']),
        'typed_inputs':scenario_application.inputs(explanation,goal['state'],comparison),
        'calculation_catalog':scenario_computation.catalog(explanation),
        'hypothetical':True, 'actual_case_changed':False, 'shared_rules_changed':False}
    context['content_sha256']=digest(context)
    state['scenario_context']=context
    command={'method_id':'CASE_START','document_scope_mode':'EXPLICIT','action':'START','target':None,
        'knowledge_id':None,'stage':'INTENT','task':state['task'],'source_category':state['source_category'],
        'document_ids':state['document_ids'],'facts':state['facts'],'queries':state['queries'],
        'restore_event':None,'restore_fields':[],'format':'prose','reason':'불변 기준 사건에서 별도 가정 분기 생성'}
    repo.admit(command,repo.context(body['session_id'],principal,body['question']))
    repo._review_question=state['task']
    repo._review_command=command;repo._scenario_seed={'state':state,'parts':parts}
    try:
        result=Memory._execute(repo,body,principal)
        if repo.goal(goal['id'],body['session_id']) != goal:
            raise ContractError('scenario changed its baseline case')
        return result
    finally:
        repo.__dict__.pop('_review_command',None);repo.__dict__.pop('_scenario_seed',None)
        repo.__dict__.pop('_review_question',None)
