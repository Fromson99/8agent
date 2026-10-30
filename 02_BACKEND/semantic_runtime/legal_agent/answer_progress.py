"""Per-request goal opinions inside the existing navigation choice, never a new call.

The LLM judges meaning. Code preserves the original issues, binds proposed tools
only to reported missing needs, and verifies receipts, evidence and counters.
"""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError, ProposalError
from .completion_contracts import obj

REVISION = 'answer-progress-v2'
NO_CHANGE_LIMIT = 2


class ProgressHandoff(Exception):
    """Retain verified originals and use the existing assessment/publication path."""


# One response updates the goals and chooses the tool. No separate planner/reviewer.
PROMPT = '''다음 행동을 고르는 이 응답 안에서 answer_progress.goals를 먼저 갱신한다. 별도의 검토나 답변 생성 요청이 아니다.
issues의 사용자 요구마다 정확히 한 행을 쓴다. 요구를 새로 만들거나 삭제·축소하지 않는다. 처음에는 질문의 답에 필요한 내용을 정리하고, 이후에는 이전 goal 의견과 실제 행동 결과·현재 원문을 비교한다. 과거 의견은 정답이나 근거가 아니다.
answer_so_far에는 지금 원문으로 답할 수 있는 내용을 짧게, basis_refs에는 현재 sources의 근거를 쓴다. material_need에는 그 요구의 답을 바꿀 구체적인 필수 부족만, next_answer_change에는 다음 조회 후 무엇이 확정·수정될지 쓴다. 요구별 상태는 다음과 같다.
ANSWERABLE: 요청한 내용을 현재 원문으로 설명할 수 있다. material_need와 next_answer_change는 빈 문자열이다. 그 요구로 추가 도구를 고르지 않는다. 모든 요구가 ANSWERABLE이면 FINISH한다.
NEEDS_SOURCE: 답의 필수 내용이 빠졌다. 그 부족에 직접 연결되는 행동을 선택한다. 원문이 구체 내용을 다른 조문에 위임한 경우 그 내용이 필요한지 판단하고, 필요한 본문을 아직 읽지 않았다면 충분하다고 하지 않는다. 연결 목록 확인 전에는 필요한 원문 범위의 연결부터 확인한다. 이미 읽은 근거를 새로 발견한 것으로 쓰지 않는다.
NO_PROGRESS: 남은 부족이 있지만 유효한 조사 경로가 없거나 반복 조사로 답이 달라지지 않는다. 부족을 지우지 않고 보존한다. 확보 원문이 있으면 evidence_sufficient=false로 FINISH하고, 원문이 전혀 없으면 PENDING이다.
READ 등의 issue_id는 NEEDS_SOURCE인 요구만 선택한다. missing_need는 시스템이 해당 요구의 material_need로 조립한다. 질문이 일반 규칙을 묻고 있다면, 단지 관련 조항·특례가 목록에 있다는 이유로 모든 사건의 적용 조건까지 새 목표로 만들지 않는다. 위임된 필수 내용과 요청 밖 사례를 실제 원문으로 구분한다.
assessment_requirements는 직전 검토(ASSESS)가 원문을 보고 남긴 필수 부족이다. 과거 탐색의 ANSWERABLE 의견과 다를 수 있다. effective_goal_states의 NEEDS_SOURCE는 이 부족이 남아 있다는 실행 상태이며 법률 정답 판정이 아니다. 해당 부족의 offered_actions로 조사하거나, 종료할 때 기존 gap_resolutions에 재판단 이유를 남긴다. 충분하다는 과거 의견만으로 검토의 부족을 지우지 않는다.
previous_effect는 직전 행동이 이 요구에 미친 실제 결과다: ANSWER_CHANGED는 답할 내용이 달라짐, NEED_NARROWED는 필수 부족의 경로가 구체화됨, NO_CHANGE는 둘 다 없음, TOOL_FAILED는 조회 실패, INITIAL은 최초 검토다. 새 문서나 문자를 읽었다는 사실만으로 ANSWER_CHANGED가 되지 않는다. 필요한 연쇄 참조의 경로를 좁히는 것은 진전이다. 의미상 불확실성만 남으면 확인한 답과 한계를 전달한다.'''


def enabled(inv):
    return bool(getattr(inv, 'policy', {}).get('answer_progress_control', False))


def request_key(inv, data):
    return digest([REVISION, inv.p['binding'], data.get('current_request', inv.question), data.get('issues', [])])


def _seal(state):
    return digest({k: v for k, v in state.items() if k != 'state_hash'})


def state_for(inv, data):
    state = inv.p.get('answer_progress_reviews', {}).get(request_key(inv, data), {})
    if state and state.get('state_hash') != _seal(state):
        raise ContractError('goal progress state hash mismatch')
    return state


def assessment_requirements(data, inv=None):
    """Project validated ASSESS opinions; never infer a missing fact or locator."""
    issues = {i['id'] for i in data.get('issues', [])}
    menus = {m['gap_id']: m for m in data.get('gap_targets', [])}
    requirements = []
    seen = set()
    for gap in data.get('assessment_gaps', []):
        if not gap.get('material') or gap.get('kind') == 'MISSING_FACT':
            continue
        gid = gap['gap_id']
        if gid in seen or gap['issue_id'] not in issues:
            raise ContractError('assessment requirement must bind one known gap and original issue')
        seen.add(gid)
        binding = gap.get('target_binding', {})
        if not binding or not gap.get('target_binding_hash'):
            raise ContractError('assessment requirement lacks a bound target')
        if inv is not None:
            saved = next((g for g in inv.p.get('assessment_gaps', []) if g.get('gap_id') == gid), None)
            if saved != gap:
                raise ContractError('assessment requirement differs from current saved review')
            expected = {'generation': inv.s.context.query['generation_id'],
                        'scope': sorted(inv.s.scope),
                        'index': inv.s.matcher.unit_fulltext.manifest['index_sha256']}
            if gap['target_binding_hash'] != digest(expected):
                raise ContractError('assessment requirement authorization or generation changed')
        if not str(gap.get('reason', '')).strip():
            raise ContractError('assessment requirement needs the existing review reason')
        menu = menus.get(gid, {})
        requirements.append({'gap_id': gid, 'gap_key': gap.get('gap_key'),
            'issue_id': gap['issue_id'], 'reason': gap['reason'],
            'missing_target': gap.get('missing_target'),
            'target_binding_hash': gap['target_binding_hash'],
            'offered_actions': list(dict.fromkeys(menu.get('read_actions', []) + menu.get('navigation_actions', []))),
            'origin': 'VALIDATED_ASSESS_OPINION', 'legal_claim_approved': False})
    return requirements


def requirements_for_selection(row, requirements):
    return [r for r in requirements if r['issue_id'] == row['issue_id']
            and row['target'] in r['offered_actions']]


def effective_goal_states(goals, requirements):
    return {g['issue_id']: ('NEEDS_SOURCE' if any(r['issue_id'] == g['issue_id'] for r in requirements)
                            else g['status']) for g in goals}


def context(inv, data):
    state = state_for(inv, data)
    requirements = assessment_requirements(data, inv)
    return {'assessment_requirements': requirements,
            'effective_goal_states': effective_goal_states(state.get('goals', []), requirements),
            'revision': REVISION, 'original_issues': deepcopy(data.get('issues', [])),
            'current_goals': deepcopy(state.get('goals', [])),
            'previous_model_opinions': deepcopy(state.get('history', [])[-2:]),
            'unchanged_steps_by_issue': deepcopy(state.get('unchanged_steps_by_issue', {})),
            'meaning': '같은 요청의 과거 모델 의견이다. 현재 원문으로 재검토하며 원문 부재나 법률 정답의 증명이 아니다.',
            'handoff_after_unchanged_steps': NO_CHANGE_LIMIT}


def schema(current, issues, has_previous):
    refs = {'type': 'array', 'maxItems': min(4, len(current)), 'uniqueItems': True,
            'items': {'enum': list(current)}} if current else {'type': 'array', 'maxItems': 0, 'items': {'type': 'string'}}
    common = {'issue_id': {'type': 'string', 'enum': [i['id'] for i in issues]},
              'answer_so_far': {'type': 'string', 'maxLength': 700}, 'basis_refs': refs,
              'material_need': {'type': 'string', 'maxLength': 400},
              'next_answer_change': {'type': 'string', 'maxLength': 400},
              'previous_effect': {'enum': ['ANSWER_CHANGED', 'NEED_NARROWED', 'NO_CHANGE', 'TOOL_FAILED'] if has_previous else ['INITIAL']}}
    alternatives = []
    for status in ('ANSWERABLE', 'NEEDS_SOURCE', 'NO_PROGRESS'):
        if status == 'ANSWERABLE' and not current:continue
        props = deepcopy(common); props['status'] = {'const': status}
        if status == 'ANSWERABLE':
            props['answer_so_far']['minLength'] = 1
            props['basis_refs']['minItems'] = 1
            props['material_need'] = props['next_answer_change'] = {'const': ''}
        else:
            props['material_need']['minLength'] = 1
            if status == 'NEEDS_SOURCE': props['next_answer_change']['minLength'] = 1
        alternatives.append(obj(props))
    return obj({'goals': {'type': 'array', 'minItems': len(issues), 'maxItems': len(issues),
                          'items': {'anyOf': alternatives}}})


def attach(schema_value, inv, data, current, key):
    value = deepcopy(schema_value)
    state = state_for(inv, data)
    prior = state.get('receipts', {}).get(key)
    has_previous = (prior['review']['goals'][0]['previous_effect'] != 'INITIAL'
                    if prior else bool(state.get('history')))
    review = schema(current, data['issues'], has_previous)
    for branch in value['anyOf']:
        choice = branch['properties']['choice']['const']
        # The missing need is already in the goal review. Do not ask for it twice.
        target = branch['properties']['selections']['items'] if choice == 'READ' else branch
        target['properties'].pop('missing_need', None)
        target['required'] = [k for k in target['required'] if k != 'missing_need']
        branch['properties']['answer_progress'] = deepcopy(review)
        branch['required'].append('answer_progress')
    return value


def validate_review(value, current, issues, *, check_action=True, data=None, inv=None):
    goals = value['answer_progress']['goals']
    by_id = {r['issue_id']: r for r in goals}
    if len(by_id) != len(goals) or set(by_id) != {i['id'] for i in issues}:
        raise ProposalError('goal review must cover every original issue exactly once')
    for row in goals:
        if set(row['basis_refs']) - set(current):
            raise ContractError('goal review refers to an unoffered original')
        if row['status'] == 'ANSWERABLE':
            if not row['basis_refs'] or not row['answer_so_far'].strip() or row['material_need'] or row['next_answer_change']:
                raise ProposalError('answered goal requires current evidence and no material missing need')
        elif not row['material_need'].strip():
            raise ProposalError('unresolved goal must preserve its concrete missing need')
        if row['status'] == 'NEEDS_SOURCE' and not row['next_answer_change'].strip():
            raise ProposalError('continued goal needs an expected answer change')
    if not check_action:
        return
    if value['choice'] in ('FINISH', 'PENDING'):
        if any(r['status'] == 'NEEDS_SOURCE' for r in goals):
            raise ProposalError('termination conflicts with a goal that still requests investigation')
        if value.get('evidence_sufficient') and any(r['status'] != 'ANSWERABLE' for r in goals):
            raise ProposalError('unresolved goals must preserve insufficient evidence')
        if value['choice'] == 'FINISH':
            if set(value['issue_refs']) != set(by_id):
                raise ProposalError('finish must retain every original issue, including unresolved ones')
            required = {b for r in goals for b in r['basis_refs']}
            if required - set(value['basis_refs']):
                raise ProposalError('finish must retain the goal review evidence')
    else:
        selections = value['selections'] if value['choice'] == 'READ' else [value]
        requirements = assessment_requirements(data or {}, inv)
        for row in selections:
            if row['issue_id'] not in by_id or (by_id[row['issue_id']]['status'] != 'NEEDS_SOURCE'
                    and not requirements_for_selection(row, requirements)):
                raise ProposalError('proposed tool must bind a missing goal or exact ASSESS requirement action')


def resolve_action(inv, data, value):
    """Use a terminal semantic opinion as-is; do not ask for a second opinion.

    Only pre-authorized mechanical correction: all original goals are terminal,
    source IDs are current, and the existing connection and FINISH gates allow it.
    Other conflicts keep the existing bounded failure/repair path.
    """
    current = {s['id']: s for s in data.get('sources', []) if s.get('text')}
    validate_review(value, current, data['issues'], check_action=False)
    goals = value['answer_progress']['goals']
    if value['choice'] in ('FINISH', 'PENDING') or any(g['status'] == 'NEEDS_SOURCE' for g in goals):
        return value, None
    if data.get('connection_review', {}).get('required_before_finish', False):
        return value, None
    basis = {b['id'] for b in data.get('basis', []) if b.get('branch_id')} & set(current)
    refs = sorted({ref for g in goals for ref in g['basis_refs']})
    if not refs or not set(refs) <= basis:
        return value, None
    # An assessment reentry has explicit gap resolution duties. Do not erase them.
    if data.get('assessment_gaps'):
        return value, None
    resolved = {'choice': 'FINISH', 'basis_refs': refs,
                'issue_refs': [i['id'] for i in data['issues']],
                'evidence_sufficient': all(g['status'] == 'ANSWERABLE' for g in goals),
                'reason': '요구별 모델 검토가 종료 상태이므로 확보 원문을 판단 단계에 전달한다.',
                'answer_progress': deepcopy(value['answer_progress'])}
    correction = {'rule': 'TERMINAL_GOAL_TO_FINISH', 'original_proposal': deepcopy(value),
                  'resolved_hash': digest(resolved), 'semantic_opinions_changed': False,
                  'additional_model_call': False}
    return resolved, correction


def bind_action(value, data=None, inv=None):
    """Assemble executable reasons from the validated goal opinion, not new text."""
    value = deepcopy(value)
    goals = {r['issue_id']: r for r in value['answer_progress']['goals']}
    if value['choice'] not in ('FINISH', 'PENDING'):
        selections = value['selections'] if value['choice'] == 'READ' else [value]
        requirements = assessment_requirements(data or {}, inv)
        for row in selections:
            goal = goals[row['issue_id']]
            matched = requirements_for_selection(row, requirements)
            row['missing_need'] = (goal['material_need'] if goal['status'] == 'NEEDS_SOURCE'
                else '; '.join(r['reason'] for r in matched))
    return value


def first_required_read_grants(data, value, actions, state):
    """One offered body-read attempt for a reviewed need, within existing budgets.

    Structure lookup/directory display is not a body-read attempt. This does not
    change the model's no-change opinion, counters, or meaning of the evidence.
    Canonical action validation has already checked the offered targets.
    """
    if value['choice'] != 'READ':
        return []
    granted = []
    used = state.get('first_required_read_grants', {})
    for gap in data.get('assessment_gaps', []):
        if not gap.get('material') or gap.get('kind') == 'MISSING_FACT':
            continue
        target = gap.get('target_binding', {})
        docs = set(target.get('document_candidates', [])) | {p['document_id'] for p in target.get('pairs', [])}
        if not docs:
            continue
        key = digest([gap.get('identity_key', gap.get('gap_key')), gap['target_binding_hash']])
        if key in used:
            continue
        selected = [r for r in value['selections'] if r['issue_id'] == gap['issue_id']
                    and actions.get(r['target'], {}).get('action') == 'READ_ARTICLES'
                    and actions[r['target']]['identity'].get('document_id') in docs]
        if not selected:
            continue
        attempted = any(r.get('status') in ('COMPLETED', 'FAILED') and r.get('action') == 'READ_ARTICLES'
            and (gap['gap_id'] in r.get('gap_ids', []) or any(t.get('identity', {}).get('document_id') in docs
                 for t in r.get('targets', []))) for r in data.get('gap_action_receipts', []))
        if not attempted:
            granted.append({'key': key, 'gap_id': gap['gap_id'], 'issue_id': gap['issue_id'],
                            'targets': sorted({r['target'] for r in selected})})
    if any(not any(g['issue_id'] == r['issue_id'] and r['target'] in g['targets'] for g in granted)
           for r in value['selections']):
        return []
    return granted


def record(inv, data, value, key, *, original=None, correction=None, actions=None):
    """Persist once after validation; resume cannot reset the goal streak."""
    state = state_for(inv, data)
    requirements = assessment_requirements(data, inv)
    proposal_hash = digest(original if original is not None else value)
    if key in state.get('receipts', {}):
        old = state['receipts'][key]
        if old.get('assessment_requirements', []) != requirements:
            raise ContractError('assessment requirements changed for the same accepted choice')
        if old['proposal_hash'] != proposal_hash:
            raise ContractError('goal progress proposal changed for the same accepted choice')
        return old['handoff']
    namespace = deepcopy(state) if state else {'revision': REVISION, 'receipts': {}, 'history': [],
                                              'unchanged_steps_by_issue': {}, 'goals': []}
    review = deepcopy(value['answer_progress'])
    counts = namespace['unchanged_steps_by_issue']
    for row in review['goals']:
        ident = row['issue_id']
        counts[ident] = counts.get(ident, 0) + 1 if namespace['history'] and row['previous_effect'] in ('NO_CHANGE', 'TOOL_FAILED') else 0
    selected = (value['selections'] if value['choice'] == 'READ' else [value]) if value['choice'] not in ('FINISH', 'PENDING') else []
    originals = sorted(digest({k: s.get(k) for k in ('document_id', 'source_id', 'heading', 'text')})
                       for s in data.get('sources', []) if s.get('text'))
    handoff = bool(originals and selected and all(counts[r['issue_id']] >= NO_CHANGE_LIMIT for r in selected))
    requirements = assessment_requirements(data, inv)
    grants = first_required_read_grants(data, value, actions or {}, namespace) if handoff else []
    if grants:
        handoff = False
        namespace.setdefault('first_required_read_grants', {}).update({g['key']: deepcopy(g) for g in grants})
    bound = sorted({r['gap_id'] for row in selected for r in requirements_for_selection(row, requirements)})
    receipt = {'assessment_requirements': requirements, 'bound_requirement_ids': bound,
               'effective_goal_states': effective_goal_states(review['goals'], requirements),
               'first_required_read_grants': deepcopy(grants),
               'key': key, 'proposal_hash': proposal_hash, 'review': review, 'choice': value['choice'],
               'original_signature': digest(originals), 'unchanged_steps_by_issue': deepcopy(counts),
               'handoff': handoff, 'legal_claim_approved': False, 'correction': deepcopy(correction)}
    namespace['receipts'][key] = receipt
    namespace['history'] = (namespace['history'] + [receipt])[-8:]
    namespace['goals'] = deepcopy(review['goals'])
    namespace['state_hash'] = _seal(namespace)
    inv.p.setdefault('answer_progress_reviews', {})[request_key(inv, data)] = namespace
    if grants:
        inv.s.repo.event('FIRST_REQUIRED_READ_ALLOWED', {'key': key, 'grants': deepcopy(grants),
            'no_change_counts_preserved': deepcopy(counts), 'additional_model_call': False,
            'budget_extended': False, 'source_acquired': False})
    if bound:
        inv.s.repo.event('GOAL_REQUIREMENT_BOUND', {'key': key, 'gap_ids': bound,
            'requirements_hash': digest(requirements), 'additional_model_call': False,
            'semantic_opinions_changed': False})
    if correction:
        inv.s.repo.event('GOAL_ACTION_ASSEMBLED', {'key': key, **deepcopy(correction)})
    inv.s.repo.event('ANSWER_PROGRESS_REVIEWED', deepcopy(receipt))
    inv.save()
    return handoff
