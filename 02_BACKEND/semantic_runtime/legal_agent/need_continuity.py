"""Identity and final accounting of model-declared needs, without legal inference.

The supervisor checkpoint owns declarations. Source goals and structure sets keep
their existing acquisition receipts. Final accounting lives in read_judgment_review
and uses the existing ASSESS repair/reentry budget.
"""
from copy import deepcopy

from ..contracts import digest
from .errors import ContractError
from . import read_judgment as rj

LEGACY_VERSION = 'declared-need-continuity-v1'
VERSION = 'declared-need-continuity-v2'
PROMPT = """read_judgments.need_continuity가 있으면 모든 needs와 원문 목표를 명시적으로 검토한다. 확보·전달은 서버 영수증이고 법률 판단 완료가 아니다. 이전 선언·목적은 삭제하거나 최신 ANSWERABLE로 덮지 않는다.
read_judgment_review.scope_reviews에는 targets의 모든 target_id를 한 번씩 넣는다. 각 groups는 그 target의 available_evidence_refs를 빠짐없이 한 번씩 나누어 USE/EXCLUDE/OPEN으로 검토한다. 같은 처리·이유인 근거는 한 그룹으로 묶는다. 표제·다른 항도 자동 제외하지 말고 질문과 원문에 따른 이유를 남긴다.
USE는 해당 부분을 실제 사용하는 claim_refs, 그 주장과 일치하는 issue_refs를 쓴다. 각 근거는 그 claim과 채택 judgment 양쪽에 연결되어야 한다. EXCLUDE는 이번 요청에 쓰지 않는 이유와 해당 원문 basis_refs를 남기고 claim_refs/gap_indices는 비운다. OPEN은 같은 issue의 material=true gap_indices(첫 항목1)를 남기며 그 쟁점을 COVERED로 쓰지 않는다. 원문 미확보나 반대·예외를 확인하지 않은 것을 EXCLUDE로 숨기지 않는다.
needs의 origin이 SOURCE_GOAL/STRUCTURE_SELECTION이면 자료 범위 검토 작업이다. 최초 issue_refs는 읽기를 요청한 이력이며, 그 자료를 다른 쟁점에도 쓸 수 있다. RESOLVED는 전체 확보와 scope_reviews의 검토가 끝난 경우다. claim_refs에는 해당 범위의 USE에 실제 연결한 주장만 넣는다. 모든 부분이 정당하게 제외되었다면 claim_refs=[]도 가능하다. 읽기 작업 완료가 의미 필요의 해결은 아니다.
그 밖의 needs는 의미상의 필요다. RESOLVED는 그 필요의 같은 쟁점에 속하는 실제 주장과 근거를 연결한다. 필요를 해결한 target_refs의 범위 검토도 완료해야 한다. 같은 원문을 읽었다는 이유로 다른 쟁점의 주장을 연결하지 않는다. 한 자료는 여러 필요·쟁점에서 사용할 수 있으며 모든 원문을 모든 주장에 인용할 필요는 없다.
NOT_NEEDED는 정확한 사용자 scope_quote 또는 현재 원문으로 제외 이유를 설명한다. OPEN은 material=true와 해당 쟁점의 실제 핵심 gap_indices를 연결한다. 빠진 내용이 있으면 전체 해결로 표시하지 않는다. 쓰지 않는 배열은 [], scope_quote는 빈 문자열이다. repair_feedback이 있으면 지적된 연결·누락 구간을 모두 고치며 내용과 근거를 임의로 추가하거나 삭제하지 않는다."""


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
    _verify_scope_originals(targets, options, session)
    for receipt in ctx.get('previous_final_review', []):
        prior = receipt.get('need_continuity')
        if prior and prior.get('version') != VERSION:
            raise ContractError('final scope review version changed; original request must use its bound runtime')
    ctx['need_continuity'] = {'version': VERSION,
        'issue_refs': ids, 'scope_input_hash': digest([targets, options]), 'input_state_hash': state_hash(investigation),
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
    if ctx['need_continuity']['version'] == VERSION:
        _extend_scope_schema(schema, ctx)


def _validate_legacy_review(value, ctx, options, fail):
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


def bind_reviewed_targets(value, ctx, options):
    """Fill only a uniquely proven missing edge in an otherwise valid review.

    The model already declared need -> claim, judgment -> claim/evidence and
    scope USE -> claim/evidence. Joining those exact IDs is not a new opinion.
    Never remove declared targets or change claims, needs, evidence or coverage.
    """
    from . import read_judgment_final as final
    from .output_contract import OutputContractError
    if ctx.get('need_continuity', {}).get('version') != VERSION:
        return value, None
    try:
        final.validate_review(value, ctx, options)
        return value, None
    except OutputContractError as exc:
        from .output_contract import diagnostics
        problems = diagnostics(exc)['issues']
        if not problems or any(p['code'] != 'NEED_TARGET_CLAIM_LINK' for p in problems):
            raise
    targets = {t['id']: t for t in ctx['need_continuity']['targets']}
    needs = {n['id']: n for n in ctx['needs']}
    claims = {c['claim_id']: c for c in value['claims']}
    review = value[final.FIELD]
    result = deepcopy(value)
    changes = []
    for problem in problems:
        index = int(problem['path'].rsplit('/', 1)[-1])
        row = result[final.FIELD]['needs'][index]
        need = needs[row['id']]
        cid = problem['expected_constraint']['claim_id']
        claim = claims[cid]
        if need.get('origin') in ('SOURCE_GOAL', 'STRUCTURE_SELECTION'):
            continue
        adopted = {ref for j in review['judgments'] if j['disposition'] in ('USE', 'CONDITIONAL')
                   and cid in j['claim_refs'] for ref in j['basis_refs']}
        actual = set(row['basis_refs']) & set(claim['evidence_refs']) & adopted
        matches = []
        for scope in review['scope_reviews']:
            target = targets[scope['target_id']]
            if (not set(need['issue_refs']) & set(target['issue_refs'])
                    or not available(target, options)
                    or any(g['disposition'] == 'OPEN' for g in scope['groups'])):
                continue
            refs = {ref for g in scope['groups'] if g['disposition'] == 'USE'
                    and cid in g['claim_refs'] for ref in g['basis_refs']}
            proof = actual & refs & set(target['available_evidence_refs'])
            if proof:
                matches.append((target['id'], sorted(proof)))
        # Multiple overlapping scopes are not permission to pick an arbitrary one.
        if len(matches) != 1:
            continue
        tid, proof = matches[0]
        if tid in row['target_refs'] or tid in need.get('target_refs', []):
            continue
        row['target_refs'].append(tid)
        changes.append({'need_id': row['id'], 'claim_id': cid, 'target_id': tid,
                        'basis_refs': proof, 'path': problem['path'] + '/target_refs'})
    if not changes:
        return value, None  # The ordinary validator supplies the original rejection.
    final.validate_review(result, ctx, options)
    receipt = {'rule': 'BIND_UNIQUE_EXPLICIT_REVIEWED_TARGET', 'changes': changes,
               'original_hash': digest(value), 'bound_hash': digest(result),
               'context_hash': digest(ctx), 'evidence_hash': digest(options),
               'legal_content_changed': False, 'extra_model_calls': 0}
    return result, receipt


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


def _verify_scope_originals(targets, options, session):
    """Check every reviewed original, including excluded ranges, against source bytes."""
    if session is None:
        return  # Pure validation callers supply already-verified evidence options.
    from .repository import text_hash
    raw = {}
    def original(did, bid):
        key = (did, str(bid))
        if key not in raw:
            raw[key] = session.store.source(*key)['text']
        return raw[key]
    for target in targets:
        for span in target['expected']:
            if span.get('block_hash') and text_hash(original(target['document_id'], span['block_id'])) != span['block_hash']:
                raise ContractError('scope review original version/hash changed')
        for ref in target['available_evidence_refs']:
            option = next(o for o in options if o['id'] == ref)
            text = original(option['document_id'], option['block_id'])
            if (text[option['start_cp']:option['end_cp']] != option['text']
                    or digest(option['text']) != option['text_hash']):
                raise ContractError('scope review original range/hash changed')


def _extend_scope_schema(schema, ctx):
    from .completion_contracts import obj
    continuity = ctx['need_continuity']
    targets = continuity['targets']
    refs = sorted({ref for t in targets for ref in t['available_evidence_refs']})
    group = obj({'basis_refs': rj.strings(refs),
        'disposition': {'enum': ['USE', 'EXCLUDE', 'OPEN']},
        'claim_refs': {'type':'array','uniqueItems':True,'items':{'type':'string'}},
        'issue_refs': rj.strings(continuity['issue_refs']),
        'gap_indices': {'type':'array','uniqueItems':True,'items':{'type':'integer','minimum':1}},
        'scope_quote': {'type':'string'}, 'reason':rj.TEXT})
    group['properties']['basis_refs']['minItems'] = 1
    group['properties']['issue_refs']['minItems'] = 1
    schema['properties']['scope_reviews'] = {'type':'array','minItems':len(targets),'maxItems':len(targets),
        'items':obj({'target_id': {'enum':[t['id'] for t in targets]} if targets else {'type':'string'},
            'groups':{'type':'array','items':group}})}
    schema['required'].append('scope_reviews')


def validate_review(value, ctx, options, fail):
    continuity = ctx.get('need_continuity')
    if continuity is None:
        return
    if continuity.get('version') == LEGACY_VERSION:
        return _validate_legacy_review(value, ctx, options, fail)
    if continuity.get('version') != VERSION or continuity.get('scope_input_hash') != digest([continuity['targets'], options]):
        raise ContractError('scope review input/version binding changed')
    targets = {t['id']:t for t in continuity['targets']}
    claims = {c['claim_id']:c for c in value['claims']}
    review = value['read_judgment_review']
    judgments = {j['id']:j for j in ctx['judgments']}
    issues = set(continuity['issue_refs'])
    statuses = {r['issue_id']:r['status'] for r in value['issue_assessments']}
    gaps = value.get('gaps', [])
    def error(code, path, **expected):
        fail(code, path, 'scope/need review requires valid acquisition, disposition and per-claim evidence links', expected)
    def adopted(cid):
        # Evidence belongs to THIS claim and THIS judgment's actual source.
        return {ref for j in review['judgments'] if j['disposition'] in ('USE','CONDITIONAL')
            and cid in j['claim_refs'] and j['id'] in judgments for ref in j['basis_refs']
            if ref in judgments[j['id']]['available_evidence_refs']}
    def gap_links(indices, linked_issues):
        selected = [gaps[i-1] for i in indices if 1 <= i <= len(gaps)]
        return (bool(selected) and len(selected) == len(indices)
            and all(g['material'] and g['issue_id'] in linked_issues for g in selected)
            and not any(statuses.get(i) == 'COVERED' for i in linked_issues))
    seen_targets = [row['target_id'] for row in review.get('scope_reviews', [])]
    if set(seen_targets) != set(targets) or len(seen_targets) != len(set(seen_targets)):
        error('SCOPE_TARGET_COVERAGE','/read_judgment_review/scope_reviews',
            missing_targets=sorted(set(targets)-set(seen_targets)), duplicate_targets=sorted({t for t in seen_targets if seen_targets.count(t)>1}))
    scoped = {}
    for ti, row in enumerate(review.get('scope_reviews', [])):
        tid = row['target_id']
        if tid not in targets:
            continue
        target = targets[tid]; permitted = set(target['available_evidence_refs']); seen = []; used = {}; open_groups = []
        path = '/read_judgment_review/scope_reviews/'+str(ti)
        for gi, group in enumerate(row['groups']):
            gp = path+'/groups/'+str(gi); refs = set(group['basis_refs']); cis = group['claim_refs']; qis = set(group['issue_refs'])
            seen.extend(group['basis_refs'])
            if not refs or refs-permitted:
                error('SCOPE_FOREIGN_EVIDENCE',gp+'/basis_refs', target_id=tid, invalid_evidence_refs=sorted(refs-permitted), allowed_evidence_refs=sorted(permitted))
            if not group['reason'].strip() or not qis or qis-issues:
                error('SCOPE_REVIEW_REASON_ISSUE',gp, issue_refs=sorted(issues), reason='nonempty reasoning for a declared issue')
            quote = group['scope_quote']
            if quote and quote not in continuity['question']:
                error('SCOPE_QUOTE_INVALID',gp+'/scope_quote',required='exact current user question quote')
            if group['disposition'] == 'USE':
                if not cis or group['gap_indices'] or quote:
                    error('SCOPE_USE_LINK',gp, claim_refs='actual claims',gap_indices=[],scope_quote='')
                supported = set()
                for cid in cis:
                    claim = claims.get(cid)
                    actual = refs & set(claim['evidence_refs']) & adopted(cid) if claim else set()
                    if not claim or not actual or not qis.intersection(claim['issue_refs']):
                        error('SCOPE_CLAIM_EVIDENCE',gp,claim_id=cid,basis_refs=sorted(refs),
                            claim_evidence_refs=claim['evidence_refs'] if claim else [],adopted_evidence_refs=sorted(adopted(cid)),issue_refs=sorted(qis))
                    supported |= actual;used.setdefault(cid,set()).update(actual)
                if refs-supported:
                    error('SCOPE_USE_UNSUPPORTED_RANGE',gp+'/basis_refs',missing_evidence_refs=sorted(refs-supported),
                        required='each USE range must support a linked claim and its adopted judgment; separately review unused ranges')
            elif group['disposition'] == 'EXCLUDE':
                if cis or group['gap_indices']:
                    error('SCOPE_EXCLUSION_LINK',gp,claim_refs=[],gap_indices=[])
                using = [cid for cid,c in claims.items() if refs & set(c['evidence_refs']) & adopted(cid)]
                if using:
                    error('SCOPE_EXCLUDED_ADOPTED',gp,claim_ids=using,basis_refs=sorted(refs),
                        required='a currently adopted original must be reviewed as USE, even if its initial reading purpose is excluded')
            elif group['disposition'] == 'OPEN':
                open_groups.append(group)
                if cis or quote or not gap_links(group['gap_indices'],qis):
                    error('SCOPE_OPEN_GAP',gp,claim_refs=[],scope_quote='',issue_refs=sorted(qis),required='same issue material gaps and non-COVERED status')
        missing = permitted-set(seen); repeated = {ref for ref in seen if seen.count(ref)>1}
        if missing or repeated:
            error('SCOPE_RANGE_COVERAGE',path,missing_evidence_refs=sorted(missing),duplicate_evidence_refs=sorted(repeated),
                required='review every presented target range exactly once, without invented or conflicting ranges')
        scoped[tid] = {'used':used,'open':open_groups,'complete':not missing and not repeated and not open_groups,
                       'all_excluded':bool(row['groups']) and all(g['disposition']=='EXCLUDE' for g in row['groups'])}
    known = {n['id']:n for n in ctx['needs']}
    for ni, row in enumerate(review['needs']):
        if row['id'] not in known:
            continue
        need = known[row['id']];path='/read_judgment_review/needs/'+str(ni)
        source_work = need.get('origin') in ('SOURCE_GOAL','STRUCTURE_SELECTION')
        tids = set(row['target_refs']) | set(need.get('target_refs', []))
        nissues = set(need['issue_refs']); refs=set(row['basis_refs'])
        if row['status'] == 'OPEN':
            open_issues = {i for tid in tids for g in scoped.get(tid,{}).get('open',[]) for i in g['issue_refs']}
            allowed = (open_issues or nissues) if source_work else nissues
            if (not row['material'] or row['claim_refs'] or row['scope_quote'] or not gap_links(row['gap_indices'],allowed)):
                error('NEED_OPEN_GAP',path,issue_refs=sorted(allowed),material=True,required='same-issue material gap; no claims; non-COVERED')
            continue
        if row['gap_indices']:
            error('NEED_CLOSED_GAP',path,gap_indices=[])
        if row['status'] == 'NOT_NEEDED':
            quote = row['scope_quote']; quoted = bool(quote.strip() and quote in continuity['question'])
            if row['claim_refs'] or (quote and not quoted) or (not quoted and not refs):
                error('NEED_EXCLUSION_BASIS',path,required='current originals or exact scope quote; no claim adoption')
            if source_work:
                for tid in tids:
                    sc=scoped.get(tid,{})
                    if not sc.get('all_excluded') and not (quoted and not targets[tid]['available_evidence_refs']):
                        error('NEED_EXCLUSION_SCOPE',path,target_id=tid,required='explicit excluded range review; never silently discard an open/use range')
            continue
        # RESOLVED cannot be obtained merely by a model-supplied status or by reading a heading.
        for tid in tids:
            target=targets[tid]
            if not available(target,options):
                error('SCOPE_ACQUISITION_INCOMPLETE',path,target_id=tid,acquisition_status=target.get('acquisition_status'),
                    expected_ranges=target['expected'],available_evidence_refs=target['available_evidence_refs'])
            if not scoped.get(tid,{}).get('complete'):
                error('SCOPE_REVIEW_INCOMPLETE',path,target_id=tid,required='all presented ranges reviewed, no open material review')
        if row['scope_quote']:
            error('NEED_RESOLVED_QUOTE',path,scope_quote='')
        if source_work:
            available_claims={cid for tid in tids for cid in scoped.get(tid,{}).get('used',{})}
            if set(row['claim_refs']) != available_claims:
                error('SOURCE_WORK_CLAIM_LINKS',path,expected_claim_refs=sorted(available_claims),
                    required='source-work records the actual range uses, independent of its original requesting issue')
            continue
        if not row['claim_refs'] or not refs:
            error('NEED_RESOLUTION_CLAIM',path,required='actual same-issue claim and original evidence')
        for cid in row['claim_refs']:
            claim=claims.get(cid);actual=refs & set(claim['evidence_refs']) & adopted(cid) if claim else set()
            if not claim or not nissues.intersection(claim['issue_refs']) or not actual:
                error('NEED_CLAIM_LINK',path,claim_id=cid,need_issue_refs=sorted(nissues),
                    claim_issue_refs=claim['issue_refs'] if claim else [],basis_refs=sorted(refs),
                    claim_evidence_refs=claim['evidence_refs'] if claim else [],adopted_evidence_refs=sorted(adopted(cid)))
            if tids and not any(actual & scoped.get(tid,{}).get('used',{}).get(cid,set()) for tid in tids):
                error('NEED_TARGET_CLAIM_LINK',path,claim_id=cid,target_refs=sorted(tids),
                    required='the resolved claim must use reviewed evidence in a linked target')
