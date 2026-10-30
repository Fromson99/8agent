"""Identity and final accounting of model-declared needs, without legal inference.

The supervisor checkpoint owns declarations. Source goals and structure sets keep
their existing acquisition receipts. Final accounting lives in read_judgment_review
and uses the existing ASSESS repair/reentry budget.
"""
from copy import deepcopy

from ..contracts import digest
from .errors import ContractError
from . import read_judgment as rj

VERSION = 'declared-need-continuity-v1'
PROMPT = '''read_judgments.need_continuity가 있으면 needs의 모든 ID를 최종 검토한다. 조사 종료나 최신 ANSWERABLE 의견은 이전 필요의 해결이 아니다. 각 필요를 RESOLVED/NOT_NEEDED/OPEN 중 하나로 처리한다. 필요의 선언 이력은 행동이 거절된 응답에서도 독립 검증해 보존되며, 그 이력의 answer_so_far·proposed_actions는 채택된 주장이나 실행 완료의 증거가 아니다.
RESOLVED는 같은 쟁점의 실제 claim_refs와 그 주장이 사용하는 현재 basis_refs를 연결한다. 필요를 해결한 원문 목표/범위는 target_refs에 제시된 ID로 연결한다. 조문 표제나 일부 하위 원문만으로 전체 범위 해결을 주장하지 않는다.
NOT_NEEDED는 사용자 질문의 정확한 scope_quote 또는 현재 원문 basis_refs로 제외 이유를 설명한다. 원문을 못 찾았다는 이유만으로 제외하지 않는다. OPEN은 material=true와 같은 쟁점의 실제 핵심 gap_indices(1부터)를 연결하고 해당 쟁점을 COVERED로 표시하지 않는다. 모든 배열과 scope_quote는 사용하지 않으면 []/빈 문자열로 쓴다. 이전 필요의 문장을 바꾸거나 생략해 종결시키지 않는다. 필요한 조문·범위와 의미 판단은 네가 결정한다.'''


def known_needs(inv, data):
    from . import answer_progress
    state=inv.p.get('investigation_supervisor',{}).get(answer_progress.request_key(inv,data),{})
    return {**state.get('material_needs',{}),**rj.state_for(inv,data).get('needs',{})}


def record(state, value, key):
    """Record validated progress independently of action/opinion acceptance."""
    needs = state.setdefault('material_needs', {})
    for goal in value['answer_progress']['goals']:
        text = goal['material_need'].strip()
        if not text:
            continue
        ident = 'MN' + digest([state['binding'], goal['issue_id'], ' '.join(text.split())])[:24]
        row = needs.setdefault(ident, {'id': ident, 'text': text,
            'issue_refs': [goal['issue_id']], 'status': 'OPEN', 'origin': 'ANSWER_PROGRESS',
            'declarations': []})
        declaration = {'decision_key': key, 'proposal_hash': digest(value),
            'status': goal['status'], 'answer_so_far': goal['answer_so_far'],
            'basis_refs': deepcopy(goal['basis_refs']), 'next_answer_change': goal['next_answer_change']}
        actions = value.get('selections', []) if value.get('choice') == 'READ' else [value]
        declaration['proposed_actions'] = [{k: deepcopy(a[k]) for k in
            ('choice','target','missing_need','judgment_refs','structure_filter') if k in a}
            for a in actions if a.get('issue_id') == goal['issue_id']]
        declaration['action_execution_confirmed'] = False
        if declaration not in row['declarations']:
            row['declarations'].append(declaration)
    # A later ANSWERABLE or an omitted need cannot close this ledger.


def observe_progress(inv, data, schema, key):
    """Bind an observer before invoke; retain needs before action validation.

    This is a separate checkpoint operation, never a side effect of a validator.
    Rejected actions cannot discard an independently valid declaration. Neither
    current goals, accepted judgments, source targets nor review budgets change.
    """
    from jsonschema import ValidationError
    from . import answer_progress as progress, investigation_supervisor as supervisor
    from . import evidence_inventory as inventory
    from .schema_preparation import validate
    from .errors import ProposalError

    rules = [b['properties']['answer_progress'] for b in schema['anyOf']
             if 'answer_progress' in b.get('properties', {})]
    if not rules or any(r != rules[0] for r in rules):
        raise ContractError('need declaration requires one bound progress contract')
    rule = deepcopy(rules[0])
    current = {s['id']: deepcopy(s) for s in data.get('sources', []) if s.get('text')}
    issues = deepcopy(data['issues'])
    binding = inv.p['binding']
    request = progress.request_key(inv, data)
    question = inv.question
    version = data.get('state_version')
    presentation = data['presentation_id']

    def observe(value, slot):
        if not isinstance(value, dict) or 'answer_progress' not in value:
            return
        try:
            validate(value['answer_progress'], rule, owner=inv.s)
            progress.validate_review(value, current, issues, check_action=False)
        except (ValidationError, ProposalError):
            # The ordinary decision validator still rejects this proposal.
            return
        goals = [g for g in value['answer_progress']['goals'] if g['material_need'].strip()]
        if not goals:
            return  # ANSWERABLE cannot close any prior declaration.
        if (inv.p['binding'] != binding or inv.question != question
                or progress.request_key(inv, data) != request
                or data.get('presentation_id') != presentation
                or inv.p.get('state_version') != version):
            raise ContractError('need declaration request/presentation is stale')
        refs = sorted({ref for g in goals for ref in g['basis_refs']})
        delivered = inventory.confirmed_pages(inv.p) if getattr(inv, 'control', False) else None
        for ref in refs:
            page = current[ref]
            inventory.check_presented_page(inv.s, inv.p, page)
            if delivered is not None and any(delivered.get(ref, {}).get(k) != page.get(k)
                    for k in ('id', 'branch_id', 'source_id', 'scope_id', 'spans')):
                raise ContractError('need declaration lacks confirmed original delivery')
        st = supervisor.state_for(inv, data)
        ident = digest([key, slot])
        receipt = {'decision_key': key, 'slot': slot, 'proposal_hash': digest(value),
            'progress_hash': digest(value['answer_progress']), 'schema_hash': digest(rule),
            'request_key': request, 'presentation_id': presentation, 'state_version': version,
            'basis_hash': digest([current[ref] for ref in refs]),
            'action_accepted': False, 'judgments_adopted': False, 'status': 'OPEN'}
        prior = st.get('need_declaration_receipts', {}).get(ident)
        if prior is not None:
            if prior != receipt:
                raise ContractError('observed need declaration changed')
            return
        before = deepcopy(st)
        if 'material_needs' not in st and st['goals']:
            record(st, {'answer_progress': {'goals': st['goals']}}, 'LEGACY_LAST_GOALS')
        record(st, value, key)
        st.setdefault('need_declaration_receipts', {})[ident] = receipt
        try:
            supervisor.save(inv, st)
        except BaseException:
            st.clear(); st.update(before)
            raise
        inv.s.repo.event('NEED_DECLARATION_OBSERVED', {'receipt_id': ident, **receipt})

    return observe


def state_hash(investigation):
    return digest({k: investigation.get(k, {}) for k in
        ('binding', 'investigation_supervisor', 'structure_selections', 'structure_need_bindings')})


def bind_structure(inv, data, decision, selected):
    """Bind an executed model selection to its explicit issue, not all issues."""
    issues = sorted(set(decision['issue_refs']))
    if not issues or not set(issues) <= {i['id'] for i in data['issues']}:
        raise ContractError('structure need must bind selected question issues')
    row={'selection_id':selected['hash'], 'request_key':rj.request_key(inv,data),
        'issue_refs':issues, 'decision_hash':digest(decision)}
    row['binding_hash']=digest(row)
    bindings=inv.p.setdefault('structure_need_bindings',{}).setdefault(selected['hash'],[])
    if row not in bindings:bindings.append(row)


def available(target, options):
    from .evidence_inventory import covers
    spans = [o for o in options if o['document_id'] == target['document_id']]
    return (target.get('acquired', False) and not target.get('membership_gaps')
            and bool(target['expected']) and covers(target['expected'], spans))


def extend_context(ctx, investigation, question, issues, options, allowed, *, session=None):
    from . import answer_progress, investigation_supervisor as supervisor
    key = digest([answer_progress.REVISION, investigation.get('binding'), question, issues])
    state = investigation.get('investigation_supervisor', {}).get(key)
    sets = investigation.get('structure_selections', {})
    if not state and not sets:
        return
    ids = [i['id'] for i in issues]
    targets = []
    additions = []
    if state:
        if state.get('state_hash') != supervisor.seal(state) or state.get('binding') != investigation.get('binding'):
            raise ContractError('need continuity supervisor binding/hash mismatch')
        additions.extend(deepcopy(list(state.get('material_needs', {}).values())))
        # An old checkpoint has only its last goals. Preserve those explicitly;
        # do not pretend to reconstruct earlier overwritten declarations.
        if 'material_needs' not in state:
            legacy = {'binding': state['binding']}
            record(legacy, {'answer_progress': {'goals': state.get('goals', [])}}, 'LEGACY_LAST_GOALS')
            additions.extend(legacy.get('material_needs', {}).values())
        for goal in state.get('source_goals', []):
            if goal['issue_id'] not in ids:
                raise ContractError('source need belongs to another issue')
            ident = 'GN' + digest([key, goal['identity']])[:24]
            target = {'id': ident, 'origin_id': goal['goal_id'], 'kind': 'SOURCE_GOAL',
                'document_id': goal['document_id'], 'issue_refs': [goal['issue_id']],
                'coordinate': goal['coordinate'], 'coordinate_scope': goal['coordinate_scope'],
                'expected': deepcopy(goal.get('expected', [])),
                'acquired': goal['status'] == 'ACQUIRED' or bool(goal.get('arrivals') and goal.get('expected')),
                'linked_need_ids':deepcopy(goal.get('need_refs',[])),
                'acquisition_status': goal['status'], 'arrivals': deepcopy(goal.get('arrivals', []))}
            targets.append(target)
            additions.append({'id': ident, 'origin': 'SOURCE_GOAL', 'text': goal['reason'],
                'issue_refs': [goal['issue_id']], 'status': 'OPEN', 'target_refs': [ident]})
    for ident, selected in sets.items():
        if selected.get('hash') != ident or digest({k:v for k,v in selected.items() if k != 'hash'}) != ident:
            raise ContractError('need continuity structure hash mismatch')
        if selected['document_id'] not in allowed:
            raise ContractError('selected range outside authorized assessment scope')
        expected = []
        if session is not None:
            from . import structure_selection, evidence_inventory, unit_reading
            structure_selection.verify(selected, session.matcher, allowed)
            for uid in selected['unit_ids']:
                expected.extend(evidence_inventory.expected(session, selected['document_id'],
                    unit_reading.blocks(session, selected['document_id'], uid, 'subtree')))
        nid = 'SN' + ident[:24]
        bindings=investigation.get('structure_need_bindings',{}).get(ident,[])
        for row in bindings:
            if (row.get('binding_hash')!=digest({k:v for k,v in row.items() if k!='binding_hash'})
                    or row.get('selection_id')!=ident):
                raise ContractError('structure need issue binding hash mismatch')
        current=[b for b in bindings if b['request_key']==ctx['request_key']]
        selected_issues=sorted({i for b in current for i in b['issue_refs']}) if current else ids
        target = {'id': nid, 'origin_id': ident, 'kind': 'STRUCTURE_SELECTION',
            'document_id': selected['document_id'], 'issue_refs': selected_issues,
            'selection': deepcopy(selected['selection']), 'unit_ids': selected['unit_ids'],
            'expected': expected, 'acquired': bool(expected),
            'membership_gaps': deepcopy(selected.get('membership_gaps', []))}
        targets.append(target)
        additions.append({'id': nid, 'origin': 'STRUCTURE_SELECTION',
            'text': '모델이 선택한 원문 범위 전체 확인', 'issue_refs': selected_issues,
            'status': 'OPEN', 'target_refs': [nid]})
    for target in targets:
        if target['document_id'] not in allowed:
            raise ContractError('declared source need outside authorized assessment scope')
        target['available_complete'] = bool(available(target, options))
        target['available_evidence_refs'] = [o['id'] for o in options
            if o['document_id'] == target['document_id'] and any(str(o['block_id']) == str(s['block_id'])
            and o['start_cp'] < s['end_cp'] and s['start_cp'] < o['end_cp'] for s in target['expected'])]
    ctx['needs'].extend(additions)
    if len({n['id'] for n in ctx['needs']}) != len(ctx['needs']):
        raise ContractError('duplicate persistent need identity')
    for need in ctx['needs']:
        if not set(need['issue_refs']) <= set(ids):
            raise ContractError('declared need issue binding changed')
        linked=[t['id'] for t in targets if need['id'] in t.get('linked_need_ids',[])]
        if linked:need['target_refs']=sorted(set(need.get('target_refs',[])) | set(linked))
    known={n['id']:n for n in ctx['needs']}
    if any(n not in known or not set(known[n]['issue_refs']).intersection(t['issue_refs'])
           for t in targets for n in t.get('linked_need_ids',[])):
        raise ContractError('source target persistent need binding changed')
    # The old provisional status is not promoted to a final answer. Expose the
    # last explicit final accounting alongside it on assessment reentry.
    for receipt in ctx.get('previous_final_review',[]):
        for row in (receipt.get('review') or {}).get('needs',[]):
            if row['id'] in known:
                known[row['id']]['previous_final_disposition']=deepcopy(row)
    ctx['need_continuity'] = {'version': VERSION, 'input_state_hash': state_hash(investigation),
        'question': question, 'targets': targets, 'stop_reason': state.get('halt') if state else None,
        'latest_goals': deepcopy(state.get('goals', [])) if state else [],
        'supervisor_reviews': deepcopy(state.get('coverage_review', [])) if state else [],
        'legacy_history_unavailable': bool(state and 'material_needs' not in state)}


def extend_schema(schema, ctx):
    if 'need_continuity' not in ctx:
        return
    node = schema['properties']['needs']['items']
    fields = {'claim_refs': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}},
        'gap_indices': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'integer', 'minimum': 1}},
        'target_refs': rj.strings([t['id'] for t in ctx['need_continuity']['targets']]),
        'scope_quote': {'type': 'string'}}
    node['properties'].update(fields)
    node['required'].extend(fields)


def validate_review(value, ctx, options, fail):
    if 'need_continuity' not in ctx:
        return
    known = {n['id']: n for n in ctx['needs']}
    targets = {t['id']: t for t in ctx['need_continuity']['targets']}
    claims = {c['claim_id']: c for c in value['claims']}
    by_ref = {o['id']: o for o in options}
    gaps = value.get('gaps', [])
    statuses = {i['issue_id']: i['status'] for i in value.get('issue_assessments', [])}
    for index, row in enumerate(value['read_judgment_review']['needs']):
        if row['id'] not in known:
            continue  # ID coverage has its own diagnostic; never dereference an unknown ID.
        need = known[row['id']]
        path = '/read_judgment_review/needs/' + str(index)
        def invalid(code, expected):
            fail(code, path, 'declared need requires explicit, evidence-bound final accounting', expected)
        issue_refs = set(need['issue_refs'])
        refs = set(row['basis_refs'])
        selected_targets = set(row['target_refs']) | set(need.get('target_refs', []))
        if any(not issue_refs.intersection(targets[t]['issue_refs']) for t in selected_targets):
            invalid('NEED_TARGET_ISSUE', {'issue_refs': sorted(issue_refs)})
        if row['status'] == 'OPEN':
            linked = [gaps[g-1] for g in row['gap_indices'] if 1 <= g <= len(gaps)]
            if (not row['material'] or not linked or len(linked) != len(row['gap_indices'])
                    or any(not g['material'] or g['issue_id'] not in issue_refs for g in linked)
                    or any(statuses.get(i) == 'COVERED' for i in issue_refs)
                    or row['claim_refs'] or row['scope_quote']):
                invalid('NEED_OPEN_GAP', {'material': True, 'issue_refs': sorted(issue_refs),
                    'gap_indices': 'same-issue material gaps (1-based)', 'coverage': 'PARTIAL or INSUFFICIENT'})
            continue
        if row['gap_indices']:
            invalid('NEED_CLOSED_GAP', {'gap_indices': []})
        if row['status'] == 'NOT_NEEDED':
            quote = row['scope_quote']
            scope_bound = bool(quote.strip() and quote in ctx['need_continuity']['question'])
            if row['claim_refs'] or (quote and not scope_bound) or (not scope_bound and not refs):
                invalid('NEED_EXCLUSION_BASIS', {'basis_refs': 'current originals or exact user scope_quote', 'claim_refs': []})
            if scope_bound:
                continue
            # Exclusion is a model judgment based on current original evidence,
            # not an assertion that the unused target was read in full.
            if refs:
                continue
        else:
            selected_claims = [claims[c] for c in row['claim_refs'] if c in claims]
            if (not selected_claims or len(selected_claims) != len(row['claim_refs']) or not refs
                    or row['scope_quote'] or any(not issue_refs.intersection(c['issue_refs'])
                    or not refs.intersection(c['evidence_refs']) for c in selected_claims)):
                invalid('NEED_RESOLUTION_CLAIM', {'claim_ids': list(claims), 'issue_refs': sorted(issue_refs)})
            adopted_refs = {r for judgment in value['read_judgment_review']['judgments']
                if judgment['disposition'] in ('USE','CONDITIONAL')
                and set(judgment['claim_refs']).intersection(row['claim_refs']) for r in judgment['basis_refs']}
            if not refs.intersection(adopted_refs):
                invalid('NEED_RESOLUTION_JUDGMENT', {'claim_refs':row['claim_refs'],
                    'required':'a final USE/CONDITIONAL judgment sharing current original evidence'})
            claim_evidence = {r for c in selected_claims for r in c['evidence_refs']}
            refs &= claim_evidence & adopted_refs
        for tid in selected_targets:
            target = targets[tid]
            if not available(target, [by_ref[r] for r in refs]):
                invalid('NEED_TARGET_INCOMPLETE', {'target_id': tid,
                    'available_complete': target['available_complete'],
                    'required_evidence_refs': target['available_evidence_refs']})


def resolution_links(review):
    return [{'need_id':n['id'], 'status':n['status'], 'target_refs':n['target_refs'],
        'claim_refs':n['claim_refs'], 'basis_refs':n['basis_refs'], 'gap_indices':n['gap_indices'],
        'judgment_refs':[j['id'] for j in review['judgments']
            if set(j['basis_refs']).intersection(n['basis_refs'])
            and (n['status']!='RESOLVED' or set(j['claim_refs']).intersection(n['claim_refs']))]}
        for n in review['needs']]


def verify_state(ctx, investigation):
    if ctx.get('need_continuity') and ctx['need_continuity']['input_state_hash'] != state_hash(investigation):
        raise ContractError('stale declared need revision')


def pending_goals(result, goals):
    """A validated exclusion closes answer duty, never the acquisition receipt."""
    receipt = result.get('read_judgment_review', {})
    if receipt.get('status') != 'REVIEWED' or not receipt.get('need_continuity'):
        return goals
    rows = {r['id']: r for r in receipt['review']['needs']}
    excluded = {t['origin_id'] for t in receipt['need_continuity']['targets']
        if t['kind'] == 'SOURCE_GOAL' and rows[t['id']]['status'] == 'NOT_NEEDED'}
    return [g for g in goals if g['goal_id'] not in excluded]
