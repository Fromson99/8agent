"""Model-selected structural connection scopes; acquired originals stay intact.

Scope membership is exact delivered block spans, independent of hierarchy level.
Ancestor introductions are context, not automatically selected connection roots.
"""
from copy import deepcopy
from contextlib import contextmanager
import sqlite3
from ..contracts import digest
from .errors import ContractError, ToolExecutionError
from . import evidence_inventory as inventory, unit_reading as ur

VERSION = 'selected-connection-scope-v1'
INLINE_CONNECTION_LIMIT = 5

FINISH_GUIDANCE = '''사용자가 특정 조항의 문언이 정한 수치·시기·사항만 물었으면 전달된 해당 구간에서 답을 확인하고 그 조항의 범위로 설명한다. 다른 조항이 이 조항을 인용·준용한다는 사실만으로 원래 문언의 예외를 증명하거나 모든 적용 사례를 조사할 필요가 생기지는 않는다. 이미 읽은 연결 원문은 실제 답변 주장을 뒷받침할 때만 인용한다. 질문 밖의 적용 사례를 검토하다 생긴 필요도 최종 검토에서 그 이유와 범위를 명시한다. 반대로 요청이 사건 적용·예외·다른 조항과의 관계를 묻거나 대상 원문이 다른 규정의 요건에 의존하면 그 원문과 연결을 확인한다. connection_review의 한 범위 조회 완료는 다른 원문의 연결 확인을 대신하지 않는다. source_inspections는 현재 전달된 원문 구간별 실제 연결 조회 상태다. finish_connection_review의 uninspected_basis가 있으면 그 근거의 미확인 연결과 질문 대상 행위를 함께 검토한다. 질문 대상 원문에 수치·조건이 없다는 이유만으로 다른 일반 규정의 적용을 확정하지 않는다. 일반 규정의 '다른 정함', 예외·특칙 조건이 이번 행위에 어떻게 적용되는지 원문으로 확인한다. 대상 원문을 인용하는 INCOMING 연결도 별도 요건의 단서가 될 수 있다. 필요한 범위의 FOLLOW_CONNECTION과 필요한 원문 READ를 선택한다. 모든 원문·연결을 순회하거나 미확인 조항 번호를 추측하지 않는다. 확인할 수 없거나 요청에 불필요하면 실제 남은 범위와 이유를 보존해 기존 제한된 최종 검토로 넘긴다. 조회 실패·일부 확인은 별도 규정 부재의 증명이 아니다.'''


def finish_review(data, value):
    """Pure source-specific inspection facts, never a legal completion verdict.

    The old flag controls the first directory lookup only. A terminal proposal
    must not use that global lookup as a substitute for checking its own basis.
    Older persisted views have no exact-span projection; their unselected basis
    still requires supervision, while inspected legacy scopes remain compatible.
    """
    refs = set(value.get('basis_refs', []))
    for goal in value.get('answer_progress', {}).get('goals', []):
        refs.update(goal.get('basis_refs', []))
    review = data.get('connection_review', {})
    inspections = review.get('source_inspections')
    if inspections is None:
        choices = data.get('connection_scope_choices', [])
        inspections = []
        for ref in sorted(refs):
            offered = [c for c in choices if ref in c.get('source_refs', [])]
            if offered:
                inspections.append({'source_ref': ref,
                    'inspected_scope_ids': [c['id'] for c in offered
                        if c.get('connection_preview', {}).get('status') not in (None, 'NOT_SELECTED')],
                    'offered_scope_ids': [c['id'] for c in offered],
                    'read_actions': [c['read_action'] for c in offered if c.get('read_action')]})
    pending = [deepcopy(row) for row in inspections
               if row['source_ref'] in refs and not row['inspected_scope_ids']]
    return {'uninspected_basis': pending,
        'supervision_required': bool(review.get('required_before_finish') or pending),
        'all_connections_required': False, 'legal_sufficiency_approved': False}


def source_inspections(data, scopes, choices):
    """Bind directory attempts to fully contained, delivered source spans only."""
    by_id = {s['id']: s for s, _ in scopes}
    rows = []
    for page in data.get('sources', []):
        offered = [c for c in choices if page['id'] in c['source_refs']]
        if not offered:
            continue
        owned = {str(s['block_id']) for c in offered for m in by_id[c['id']]['members']
                 if m['document_id'] == page['document_id'] and m['source_id'] == page['source_id']
                 for s in m['spans']}
        delivered = [p for p in page.get('spans', []) if str(p['block_id']) in owned]
        inspected = []
        for choice in offered:
            if choice['connection_preview']['status'] == 'NOT_SELECTED':
                continue
            members = [m for m in by_id[choice['id']]['members']
                       if m['document_id'] == page['document_id'] and m['source_id'] == page['source_id']]
            spans = [s for m in members for s in m['spans']]
            # Ancestor context is not the selected anchor; partial overlap may
            # not certify the rest of a delivered source page.
            if delivered and all(any(str(s['block_id']) == str(p['block_id'])
                    and s['start_cp'] <= p['start_cp'] and s['end_cp'] >= p['end_cp']
                    for s in spans) for p in delivered):
                inspected.append(choice['id'])
        rows.append({'source_ref': page['id'], 'source_id': page['source_id'],
            'document_id': page['document_id'], 'inspected_scope_ids': inspected,
            'offered_scope_ids': [c['id'] for c in offered],
            'read_actions': [c['read_action'] for c in offered if c.get('read_action')]})
    return rows


def enabled(inv):
    return bool(inv.modern and inv.policy.get('selected_connection_scope'))


def acquired_signature(inv):
    return digest(sorted((gid, digest(r['offer'])) for gid, r in inv.p['selected'].items()
                         if inv.p['groups'][gid]['status'] != 'EXCLUDED'))


def current(inv, *, allow_acquired_change=False):
    value = inv.p.get('selected_connection_scope')
    if not value:
        return None
    scope = value['scope']
    if scope['id'] != digest({k: v for k, v in scope.items() if k != 'id'}):
        raise ContractError('connection scope hash mismatch')
    if value['binding'] != digest(inv.p['binding']):
        raise ContractError('connection scope request binding mismatch')
    if not allow_acquired_change and value['acquired_signature'] != acquired_signature(inv):
        return None
    for member in scope['members']:
        source = inv.s.tools.sources.get(member['source_id'])
        if not source or source['document_id'] != member['document_id'] or source['document_id'] not in inv.s.scope:
            raise ContractError('connection scope outside authorized original')
    return value


def _spans(spans, wanted):
    rows = {}
    for p in spans:
        if str(p['block_id']) not in wanted:
            continue
        q = {k: p[k] for k in ('block_id', 'start_cp', 'end_cp', 'text', 'block_hash', 'span_hash') if k in p}
        q['block_id'] = str(q['block_id'])
        rows[(q['block_id'], q['start_cp'], q['end_cp'])] = q
    return [rows[k] for k in sorted(rows)]


def _scope(label, structural, members):
    value = {'contract': VERSION, 'label': label, 'structural_selection': structural,
             'members': sorted(members, key=lambda r: (r['document_id'], r['source_id']))}
    value['id'] = digest(value)
    return value


def _subscopes(inv, record, spans):
    """Offer delivered descendants without reading or expanding the original.

    Walk each owned block's stored parents, stopping at the acquired root.
    Ancestor context and unread siblings cannot become connection anchors.
    """
    did = record['document_id']; root = str(record['offer']['unit_id'])
    units = inv.s.matcher.units
    grouped = {}
    for span in spans:
        uid = inv.s.store.source(did, span['block_id']).get('unit_id')
        path = []; seen = set()
        while uid is not None:
            uid = str(uid)
            if uid == root:
                for child in path:
                    grouped.setdefault(child, []).append(span)
                break
            if uid in seen:
                raise ContractError('connection scope parent cycle')
            seen.add(uid)
            unit = units.get((did, uid))
            if unit is None:
                break  # Block-only originals have no invented structure.
            path.append(uid); uid = unit.get('parent')
    return sorted(grouped.items(), key=lambda row: (units[did, row[0]]['span'][0], row[0]))


def candidates(inv, data):
    """Only model-visible originals can be selected, including partial scopes."""
    from .structure_query import node_label
    pages = data.get('sources', [])
    records = inv.p['selected']
    per_group = {}
    for page in pages:
        gid = page.get('branch_id')
        if gid not in records or inv.p['groups'][gid]['status'] == 'EXCLUDED':
            continue
        r = records[gid]
        if page.get('scope_id') != digest(r['offer']):
            # Historical pages remain evidence but cannot authorize the new scope.
            continue
        inventory.check_presented_page(inv.s, inv.p, page)
        per_group.setdefault(gid, []).append(page)
    result = []
    for gid, shown in per_group.items():
        r = records[gid]; g = inv.p['groups'][gid]
        spans = _spans([s for p in shown for s in p['spans']], set(map(str, r['offer']['block_ids'])))
        if not spans:
            continue
        member = {'source_id': r['source_id'], 'document_id': r['document_id'], 'spans': spans}
        selection = {'document_id': r['document_id'], 'unit_id': r['offer']['unit_id'],
                     'extent': r['offer']['extent'], 'scope_id': digest(r['offer'])}
        result.append((_scope(inventory.scope_path(inv.s, g['hit'], r['offer']), selection, [member]),
                       [p['id'] for p in shown]))
        for uid, selected_spans in _subscopes(inv, r, spans):
            sub_selection = {**selection, 'unit_id': uid, 'extent': 'subtree', 'delivered_only': True}
            sub_offer = {**r['offer'], 'unit_id': uid, 'extent': 'subtree'}
            positions = {(s['block_id'], s['start_cp'], s['end_cp']) for s in selected_spans}
            result.append((_scope(inventory.scope_path(inv.s, g['hit'], sub_offer), sub_selection,
                [{**member, 'spans': selected_spans}]), [p['id'] for p in shown
                    if any((str(s['block_id']), s['start_cp'], s['end_cp']) in positions for s in p['spans'])]))
    # A stored chapter/section or selected union can cross article roots. Bind
    # only its actually delivered intersection; excluded units never enter it.
    for ident, selection in inv.p.get('structure_selections', {}).items():
        from .structure_selection import verify
        verify(selection, inv.s.matcher, inv.s.scope)
        did = selection['document_id']
        wanted = set()
        for uid in selection['unit_ids']:
            wanted.update(ur.blocks(inv.s, did, uid, 'subtree'))
        members = {}; refs = []
        for shown in per_group.values():
            for page in shown:
                if page['document_id'] != did:
                    continue
                spans = _spans(page['spans'], wanted & set(map(str, records[page['branch_id']]['offer']['block_ids'])))
                if not spans:
                    continue
                sid = page['source_id']; refs.append(page['id'])
                member = members.setdefault(sid, {'source_id': sid, 'document_id': did, 'spans': []})
                member['spans'] = _spans(member['spans'] + spans, wanted)
        if members:
            label = inv.s.matcher.documents[did] + ' ' + ', '.join(
                node_label(inv.s.matcher, did, uid)['coordinate'] or str(uid) for uid in selection['unit_ids'])
            result.append((_scope(label, {'selection_id': ident, 'document_id': did,
                'selection': deepcopy(selection['selection']), 'unit_ids': list(selection['unit_ids']),
                'excluded_unit_ids': list(selection['excluded_unit_ids']),
                'delivered_only': True}, list(members.values())), list(dict.fromkeys(refs))))
    if small_context(inv):
        result = [(with_parent_bodies(inv, scope, pages), refs) for scope, refs in result]
    return result


def small_context(inv):
    """Bounded automatic endpoint reads apply only without per-read judgments.

    Guided conversation has no per-read judgment, so a tiny verified directory
    of the explicitly selected scope is read once without another model hop.
    Workflow and other read-judged navigation keep the explicit READ choice.
    """
    from .read_judgment import enabled as read_judged
    from .guided_navigation import enabled as guided
    policy = getattr(inv, 'policy', {})
    wanted = policy.get('small_connection_context') or (
        policy.get('selected_connection_scope') and guided(getattr(getattr(inv, 's', None), 'profile', {})))
    return bool(wanted) and not read_judged(inv)


def with_parent_bodies(inv, scope, pages):
    """Include delivered ancestor own text through the canonical article.

    Ancestors contribute their own blocks, never the rest of their subtrees.
    The selected structure stays unchanged; missing context remains explicit.
    """
    value = deepcopy(scope)
    for member in value['members']:
        did, sid = member['document_id'], member['source_id']
        canonical = {str(b['block_id']) for b in inv.s.tools.sources[sid]['blocks']}
        own = {str(p['block_id']) for p in member['spans']}
        wanted = set()
        for bid in own:
            uid = inv.s.store.source(did, bid).get('unit_id')
            if uid is None:
                continue
            unit = inv.s.matcher.units.get((did, str(uid)))
            if unit is None:
                raise ContractError('connection context structure missing')
            # Article own text has no ancestor inside its canonical source.
            current_uid = unit.get('parent')
            seen = {str(uid)}
            while current_uid is not None:
                current_uid = str(current_uid)
                if current_uid in seen:
                    raise ContractError('connection context parent cycle')
                seen.add(current_uid)
                parent = inv.s.matcher.units.get((did, current_uid))
                if parent is None:
                    raise ContractError('connection context parent missing')
                ids = set(ur.blocks(inv.s, did, current_uid, 'exact'))
                if not ids <= canonical:
                    break
                wanted.update(ids)
                current_uid = parent.get('parent')
        wanted -= own
        matching_pages = [page for page in pages if page['source_id'] == sid]
        for page in matching_pages:
            inventory.check_presented_page(inv.s, inv.p, page)
        presented = [span for page in matching_pages for span in page['spans']]
        inherited = _spans(presented, wanted)
        # Never label partial/missing parent text as a complete context.
        from .evidence_inventory import intervals
        ranges = intervals(inherited)
        missing = []
        for bid in sorted(wanted, key=int):
            end = 0
            for lo, hi in sorted(ranges.get(bid, [])):
                if lo > end:
                    break
                end = max(end, hi)
            if end < len(inv.s.store.source(did, bid)['text']):
                missing.append(bid)
        member['spans'] = _spans(member['spans'] + inherited, own | wanted)
        member['parent_body_block_ids'] = sorted(wanted, key=int)
        member['missing_parent_body_block_ids'] = missing
    value['id'] = digest({k:v for k,v in value.items() if k != 'id'})
    return value


def refresh_selected_delivery(inv, choices, selected):
    """New delivered bytes may extend the same already chosen structure.

    Candidates are rebuilt from verified model-visible pages. Their changing
    span hash must not erase the user's/model's structural choice. A different
    structure, exclusion, or loss/change of previously bound bytes is not a
    refresh. Keep host refreshes distinct from model selections in the journal.
    """
    if selected is None:
        return None
    old = selected['scope']
    if any(s['id'] == old['id'] for s, _ in choices):
        return selected
    matches = [s for s, _ in choices if s['structural_selection'] == old['structural_selection']]
    if len(matches) != 1:
        return selected
    new = matches[0]
    pieces = lambda scope: {(m['document_id'], m['source_id'], digest(p))
        for m in scope['members'] for p in m['spans']}
    if not pieces(old) < pieces(new):
        return selected
    if new['id'] != digest({k:v for k,v in new.items() if k != 'id'}):
        raise ContractError('refreshed connection scope hash mismatch')
    value = {**deepcopy(selected), 'scope':deepcopy(new),
        'acquired_signature':acquired_signature(inv), 'status':'SELECTED',
        'refresh_origin':'ACQUIRED_WITHIN_SELECTED_STRUCTURE', 'previous_scope_id':old['id']}
    value.pop('result', None)
    inv.p['selected_connection_scope'] = value
    inv.p.setdefault('connection_scope_history', []).append(deepcopy(value))
    inv.s.repo.event('CONNECTION_SCOPE_REFRESHED', {
        'previous_scope_id':old['id'], 'scope_id':new['id'],
        'structural_selection':deepcopy(new['structural_selection']),
        'model_selected_again':False, 'previous_spans':len(pieces(old)),
        'current_spans':len(pieces(new)), 'automatic_target_read':False})
    inv.save()
    return value


def directory_key(scope):
    # Equal delivered bytes share a directory even through different UI scopes.
    return digest(scope['members'])


def directory_receipt(inv, scope):
    receipt = inv.p.get('connection_directories', {}).get(directory_key(scope))
    if receipt is None:
        return None
    if receipt.get('sha256') != digest({k:v for k,v in receipt.items() if k != 'sha256'}):
        raise ContractError('connection directory receipt hash mismatch')
    if (receipt['binding'] != digest(inv.p['binding']) or
            receipt['authorized_scope'] != sorted(inv.s.scope) or
            receipt['members_hash'] != directory_key(scope)):
        raise ContractError('connection directory receipt binding mismatch')
    for member in scope['members']:
        source = inv.s.tools.sources.get(member['source_id'])
        if not source or source['document_id'] != member['document_id'] or source['document_id'] not in inv.s.scope:
            raise ContractError('connection directory anchor outside authorized original')
    return receipt


def reject_repeated_follow(inv, scope):
    from .errors import ProposalError
    if directory_receipt(inv, scope) is not None:
        raise ProposalError('connection directory already inspected for unchanged original scope; use saved targets or finish')


def directory_operation(inv):
    accepted = inv.p.get('accepted')
    return digest([accepted['input_hash'], accepted['decision']]) if accepted else None


def inspect_directory(inv, scope, *, preparation=None):
    """Durable request-local catalog; rendering never repeats its lookup.

    PARTIAL/FAILED are attempts, never evidence of absence. This directory path
    has no advancing cursor; retrying its unchanged request cannot add results.
    Target acquisition flags are derived afresh, without reopening the directory.
    """
    receipt = directory_receipt(inv, scope)
    if receipt is None:
        result = preview(inv, scope, preparation=preparation)
        receipt = {'scope_id':scope['id'], 'label':scope['label'],
            'members_hash':directory_key(scope), 'binding':digest(inv.p['binding']),
            'authorized_scope':sorted(inv.s.scope), 'operation':directory_operation(inv),
            'reason':(inv.p.get('selected_connection_scope') or {}).get('reason',''),
            'turn':inv.p.get('turn',0), 'result':deepcopy(result)}
        receipt['sha256'] = digest(receipt)
        inv.p.setdefault('connection_directories', {})[directory_key(scope)] = receipt
        inv.s.repo.event('CONNECTION_DIRECTORY_RECORDED', {
            'scope_id':scope['id'], 'members_hash':directory_key(scope),
            'status':result['status'], 'receipt_sha256':receipt['sha256'],
            'absence_proven':False})
        inv.save()
    result = deepcopy(receipt['result'])
    if result['groups']:
        from . import unit_relations as rel
        acquired, _ = rel.acquired_blocks(inv.s, inv.read_records(), preparation=preparation)
        for group in result['groups']:
            for endpoint in ('anchor','target'):
                row=group[endpoint]; source=inv.s.tools.sources.get(row['source_id'])
                if not source or source['document_id'] != row['document_id'] or row['document_id'] not in inv.s.scope:
                    raise ContractError('connection directory endpoint outside authorized original')
            known = acquired.get(group['target']['source_id'],set())
            group['read_blocks'] = sorted(known)
            for connection in group['connections']:
                connection['already_read'] = rel.blocks_covered(connection['endpoint_block_ids'], known)
    return result


def offer_choices(inv, data, actions):
    if not enabled(inv):
        return
    from .law_candidates import token
    from .unit_relations import CatalogReadPreparation
    preparation = CatalogReadPreparation()
    # Rebuilding a restored view must not retain a read from another scope.
    for key, action in list(actions.items()):
        identity = action.get('identity', {})
        if identity.get('connection') or identity.get('connection_scope'):
            del actions[key]
    choices = []; previews = {}; cards = []; seen = set(); history = []; historical_cards = []
    from .guided_navigation import enabled as guided_enabled
    guided_roles = guided_enabled(getattr(inv.s, 'profile', {})); listed = []
    scope_choices = candidates(inv, data)
    selected = refresh_selected_delivery(inv, scope_choices, current(inv, allow_acquired_change=True))
    selected_id = selected['scope']['id'] if selected else None
    inv.bind_reference_delivery(current_pages=data.get('sources', []))
    shown_directories = set()
    for scope, refs in sorted(scope_choices, key=lambda row: row[0]['id'] != selected_id):
        if scope['id'] in seen:
            continue
        seen.add(scope['id'])
        identity = {'connection_scope': scope}
        target = token(inv.s, 'T', ['FOLLOW_CONNECTION', identity])
        action = {'id': target, 'action': 'FOLLOW_CONNECTION', 'identity': identity,
                  'label': scope['label'] + ' — 이 선택 범위의 연결 확인'}
        # The recovery owner suppresses failed operations and retains their reason.
        if any(f['action'] == 'FOLLOW_CONNECTION' and f['targets'] == [identity]
               for f in inv.p.get('tool_failures', [])):
            continue
        # Acquisition is not a connection choice. Only the scope explicitly
        # accepted by FOLLOW_CONNECTION may query/present its links here.
        result = {'status': 'NOT_SELECTED', 'groups': [], 'connection_count': None,
                  'absence_proven': False}
        reviewed = directory_receipt(inv, scope)
        if scope['id'] == selected_id or reviewed is not None:
            result = previews[scope['id']] = inspect_directory(inv, scope, preparation=preparation)
            reviewed = directory_receipt(inv, scope)
        endpoint_count=len({endpoint_key(g,c) for g in result['groups'] for c in g['connections']})
        inline = result['status'] == 'COMPLETE'
        blocked = inv.p.get('connection_context_blocks',{}).get(scope['id'])
        if reviewed is None and not inline and result['status'] != 'FAILED' and not blocked:
            actions[target] = action
        # A partial catalog still contains verified links. Keep a bounded page
        # visible and retain FOLLOW_CONNECTION for the remaining frontier.
        visible = visible_connections(result, endpoint_count, inv.policy.get('delegation_frontier',False))
        presented_witnesses=0; omitted_witnesses=0
        if directory_key(scope) in shown_directories:visible = []
        if visible:
            shown_directories.add(directory_key(scope))
            shown = inline_cards(inv, scope, refs, visible, actions)
            if guided_roles:
                from .guided_navigation import question_terms
                shown = list_only_incoming(shown, actions, listed, question_terms(getattr(inv, 'question', '') or ''))
                remember_list_only(inv, listed)
            for card in shown:
                card['target_source_refs']=[p['id'] for p in data.get('sources',[])
                    if p.get('source_id')==card['target']['source_id'] and
                    set(map(str,card['target_scope']['block_ids'])) &
                    {str(span['block_id']) for span in p.get('spans',[])}]
                if card.get('requires_scope_menu') and not blocked and reviewed is None:
                    actions[target] = action
                    card['scope_menu_action'] = target
                presented_witnesses+=1+len(card.get('additional_reference_witnesses',[]))
                omitted_witnesses+=card.get('omitted_witness_count',0)
            if scope['id'] == selected_id:cards.extend(shown)
            else:historical_cards.extend(shown)
        if reviewed is not None:
            history.append({'scope_id':scope['id'], 'label':scope['label'],
                'status':result['status'], 'connection_count':result.get('connection_count'),
                'reason':reviewed['reason'], 'first_turn':reviewed['turn'],
                'receipt_sha256':reviewed['sha256'], 'repeat_available':False,
                'unread_target_count':sum(not c['already_read'] for c in shown) if visible else 0,
                'absence_proven':False})
        choices.append({'id': scope['id'], 'label': scope['label'], 'source_refs': refs,
                        'structural_selection': scope['structural_selection'],
                        'read_action': target if target in actions else None, 'automatic_adoption': False,
                        'selected': scope['id'] == selected_id, 'previously_inspected': reviewed is not None,
                        'connection_preview': {k:deepcopy(v) for k,v in result.items() if k!='groups'},
                        'connections_presented_inline': bool(visible),
                        'connections_complete': inline and not omitted_witnesses,
                        'menu_unavailable': deepcopy(blocked),
                        'connections_presented_count': presented_witnesses})
    references = data['references']
    references['dependency_cards'] = cards
    references['previously_inspected_cards'] = historical_cards
    data['connection_action_history'] = history
    data['automatic_connection_reads'] = [{k:deepcopy(row[k]) for k in
        ('scope_id','status','reason','endpoint_count','unresolved_count','model_called','recursive') if k in row}
        for row in inv.p.get('small_connection_directories',{}).values()]
    references['selected_scope_id'] = selected_id
    if guided_roles and listed:
        references['incoming_list_only'] = incoming_summary(listed)
    references['inline_connection_limit'] = None  # Every verified endpoint, within the existing context bound.
    references['inline_connection_count'] = len(cards)
    references['omitted_dependency_cards'] = 0
    references['preview_counts_complete'] = bool(previews) and all(p['status']=='COMPLETE' for p in previews.values())
    references['menu'] = ('연결은 최종 선택한 한 범위에 대해서만 제시한다. 미선택 범위의 빈 목록은 조회 결과가 아니다. '
        '선택한 범위에서 조회한 모든 연결 읽기 대상을 dependency_cards에 제시한다. '
        '같은 읽기 범위의 여러 인용은 additional_reference_witnesses에 함께 보존한다. '
        '카드의 omitted_witness_count는 표시하지 않은 추가 인용 수이며 scope_menu_action으로 나머지 연결 증거를 확인한다. '
        'OUTGOING은 anchor가 target을 인용하고 INCOMING은 target이 anchor를 인용한다. '
        'reference_witness는 표시된 문서·블록의 실제 인용문이며 anchor_endpoint_quote와 구분한다. '
        '질문과 sources의 확보 원문으로 필요성을 판단하고 필요한 대상의 read_action을 선택한다. '
        'already_read는 해당 연결 범위의 원문 확보 상태다. target_source_refs는 현재 sources에 표시한 대상 원문이며 '
        '조 전체 확보나 적용 판단 완료를 뜻하지 않는다. 이미 확보한 대상은 다시 조회하지 말고 원문으로 판단한다. '
        'previously_inspected_cards는 전에 명시적으로 선택해 확인한 범위의 저장된 연결이다. '
        'connection_action_history의 실제 결과와 미확보 대상을 확인하고, 필요한 원문은 read_action으로 바로 읽는다. '
        '이미 확인한 범위는 다시 FOLLOW_CONNECTION할 수 없다. 동일 조회로 추가 확보되지 않는 PARTIAL/FAILED는 구조 검색으로 조사하거나 미확인을 남긴다.')
    data['connection_scope_choices'] = choices
    attempted = next((c for c in choices if c['connection_preview']['status'] != 'NOT_SELECTED'), None)
    selectable = any(a['action'] == 'FOLLOW_CONNECTION' and
        a.get('identity', {}).get('connection_scope') for a in actions.values())
    if attempted:
        # Persist only verified target identities, not source bodies. Modern
        # FINISH may retain originals without ADOPT; its older reference export
        # can consequently be empty. The directory shown here remains evidence
        # of a stored location, independent of legal adoption.
        targets = {digest(c['target']): deepcopy(c['target']) for c in cards + historical_cards}
        receipt = {'scope_id': selected_id, 'binding': selected['binding'],
            'targets': [targets[k] for k in sorted(targets)],
            'status': attempted['connection_preview']['status']}
        receipt['sha256'] = digest(receipt)
        selected['locator_receipt'] = receipt
    from .guided_navigation import enabled as guided_enabled
    guided=guided_enabled(inv.s.profile)
    data['connection_review'] = {
        # Guided answers also look up connections once before answering; the
        # user is asked only about what remains after that bounded lookup.
        'required_before_finish': bool(data.get('sources') and selectable and not attempted),
        'source_inspections': source_inspections(data, scope_choices, choices),
        'first_lookup_only': True,
        'status': attempted['connection_preview']['status'] if attempted else
            ('SELECT_SCOPE' if selectable else 'UNAVAILABLE'),
        'scope_id': attempted['id'] if attempted else None,
        'all_targets_required': False,
        'rule': 'required_before_finish는 첫 연결 조회 여부이며 질문 대상 전체의 검토 완료가 아니다. '
                '종료 판단 전에 사용할 원문 범위를 FOLLOW_CONNECTION으로 선택해 저장 연결을 확인한다. '
                '조회 결과를 받은 뒤 필요한 연결만 읽는다. 빈 목록·일부 확인·실패도 상태를 보존해 종료할 수 있다. '
                '조회 불가나 예산 소진은 확보 원문을 전달하며 원문 부재로 단정하지 않는다.'}
    if guided:
        data['connection_review']['rule']=('답변하기 전에 사용할 원문 범위의 연결을 FOLLOW로 한 번 조회한다. 조회 결과에서 질문에 필요한 연결 대상만 읽는다. '
            '연결 대상은 다른 조문이 현재 조문을 인용하는 역방향(INCOMING)도 포함한다. 미확인 연결은 확인 완료로 표현하지 않는다.')

    data['connection_scope_rule'] = ('읽은 원문 중 현재 요청에 필요한 연결 출발 범위를 FOLLOW_CONNECTION으로 선택한다. '
        '조 전체를 선택하면 그 조 전체, 항·호·목을 선택하면 그 범위의 연결만 확인한다. '
        '이미 읽은 조 안의 하위 범위 선택에는 원문 재조회가 필요 없다. '
        '최종 선택 범위의 dependency_cards가 제시되었으면 필요한 원문 READ를 바로 선택한다. '
        '미확인 범위만 FOLLOW_CONNECTION을 고른다. 확인한 범위의 목록과 결과는 보존되므로 재조회하지 않는다. '
        '다른 원문은 보존되지만 연결 출발점으로 자동 합치지 않는다. 연결 없음·실패는 원문 부재가 아니며 '
        '필요한 법령명·번호를 알면 LOCATE/CATALOG_SEARCH로 구조를 조회하고 원문을 읽는다.')
    data['actions'] = [{k: a[k] for k in ('id', 'action', 'label')} for a in actions.values()]


def visible_connections(result, limit, prioritize=False):
    if result['status']=='FAILED':return []
    pairs=[(g,c,i) for i,(g,c) in enumerate((g,c) for g in result['groups'] for c in g['connections'])]
    if prioritize:
        # This is a lexical presentation hint over verified reference endpoints,
        # never a required-read or applicability decision. Scan bounds and all
        # omitted connections remain visible via the existing continuation menu.
        # A completed definition remains the explanation of this anchor. Do not
        # replace it with unrelated unread citations after acquiring its body.
        pairs.sort(key=lambda row:(not bool(row[1].get('defines_anchor_wording')),bool(row[1].get('already_read')),not row[1].get('anchor_delegation_wording_hint',False),
            row[1].get('witness_source_order',row[2]) if row[1].get('anchor_delegation_wording_hint') else row[2]))
    chosen=[]; endpoints=set()
    for group,connection,_ in pairs:
        endpoint=endpoint_key(group,connection)
        if endpoint not in endpoints:
            if len(endpoints)>=limit:continue
            endpoints.add(endpoint)
        target=next((g for g in chosen if g.get('key')==group.get('key')),None) if 'key' in group else None
        if target is None:target={**group,'connections':[]};chosen.append(target)
        target['connections'].append(connection)
    return chosen


def read_plan(group, connection):
    """Use the existing authorized exact endpoint offer, without expanding it."""
    options=[group['offers'][key] for key in connection['endpoint_scopes']]
    return next(((h,o) for h,o in options if o['extent']=='subtree'),None) or next(
        ((h,o) for h,o in options if o.get('reader_target')=='source' and o['unit_id'] is None),None)


def endpoint_key(group, connection):
    """Equal reading extents share a choice; their witnesses remain separate."""
    plan=read_plan(group,connection) if 'offers' in group and 'endpoint_scopes' in connection else None
    if plan:
        hit,offer=plan
        return digest([hit['source_id'],hit['document_id'],offer['unit_id'],offer['extent'],
                       offer.get('reader_target'),sorted(map(str,offer['block_ids']))])
    return digest(['reference',group.get('key'),connection.get('reference_id',connection)])


def witness_fields(group, connection):
    """A reverse citation belongs to the target, never to the anchor original."""
    origin=group['anchor'] if group['direction']=='OUTGOING' else group['target']
    return {'reference_witness':{'reference_id':connection['reference_id'],
        'source_id':origin['source_id'],
        'document_id':connection['witness_document_id'],
        'document_name':origin['document_name'],'heading':origin.get('heading',''),
        'block_id':connection['witness_block_id'],
        'unit_path':deepcopy(connection.get('source_unit_path',[])),
        'text':connection['witness'],'characters':connection.get('witness_chars',len(connection['witness'])),
        'truncated':connection.get('witness_truncated',False),
        'belongs_to':'anchor' if group['direction']=='OUTGOING' else 'target',
        'direction':group['direction']}}


def preview(inv, scope, *, preparation=None):
    """Read-only bounded catalog; no model call, adoption or target READ."""
    from . import unit_relations as rel, request_repair as rr
    key = digest([inv.p['binding'], sorted(inv.s.scope), scope['members']])
    failure = inv.p.get('connection_preview_failures', {}).get(key)
    if failure:
        return {**deepcopy(failure), 'groups': []}
    try:
        with bound(inv.s, scope):
            groups, statuses, limits, unresolved = rel.catalog(inv.s,
                [m['source_id'] for m in scope['members']], inv.read_records(), set(),
                max_connections=None, preparation=preparation)
    except (TimeoutError, ToolExecutionError, sqlite3.OperationalError) as error:
        code = rr.recoverable_tool_failure(error)
        if code is None:
            raise
        failure = {'status':'FAILED', 'reason':code, 'absence_proven':False,
                   'fallback':'SEARCH_STRUCTURE', 'binding':key, 'connection_count':None}
        inv.p.setdefault('connection_preview_failures', {})[key] = failure
        inv.s.repo.event('CONNECTION_PREVIEW_FAILED', failure)
        inv.save()
        return {**failure, 'groups':[]}
    return {'status':'PARTIAL' if limits else 'COMPLETE',
            'connection_count':sum(len(g['connections']) for g in groups),
            'groups':groups, 'anchor_status':statuses, 'limits':limits,
            'unresolved':unresolved, 'absence_proven':False}


def inline_cards(inv, scope, source_refs, groups, actions):
    from . import unit_relations as rel, law_candidates as lc
    cards = []; by_endpoint = {}
    closed = inv.closed_reference_decisions(groups, inv.read_records(),
        [m['source_id'] for m in scope['members']])
    for group in groups:
        for connection in group['connections']:
            decision = closed.get(group['key'])
            # The endpoint subtree preserves all its children; no article-wide
            # substitution when the reference names a paragraph/item instead.
            plan = read_plan(group,connection)
            target = deepcopy(group['target'])
            card = {'reference_id':connection['reference_id'], 'connection_scope_id':scope['id'],
                'source_refs':list(source_refs), 'anchor':deepcopy(group['anchor']),
                **witness_fields(group,connection), 'direction':group['direction'],
                'reading_policy':connection['reading_policy'], 'resolution':connection['resolution'],
                'already_read':connection['already_read'], 'target':target,
                'target_scope':{'extent':'reference_endpoint','block_ids':list(connection['endpoint_block_ids'])},
                'applicability':decision['applicability'] if decision else 'UNDETERMINED',
                'issue_refs':[i['id'] for i in inv.p.get('issues',[])],
                'preview_is_reference_witness':True,
                'anchor_coordinate':connection.get('locator') if group['direction']=='INCOMING' else None,
                'anchor_head_block_ids':connection.get('anchor_head_block_ids',[]),
                'anchor_endpoint_quote':connection.get('anchor_endpoint_quote',''),
                'anchor_endpoint_quote_truncated':connection.get('anchor_endpoint_quote_truncated',False),
                'anchor_delegation_wording_hint':connection.get('anchor_delegation_wording_hint',False),
                'defines_anchor_wording':connection.get('defines_anchor_wording'),
                'citation_role':connection.get('citation_role'),
                'citation_relation':deepcopy(connection.get('citation_relation')),
                'hint_imposes_read':False}
            if decision:
                card['decision'] = deepcopy(decision)
            if plan is None and not card['already_read'] and not decision:
                card['read_unavailable'] = 'NO_EXECUTABLE_ENDPOINT_SCOPE'
                card['fallback'] = 'SEARCH_STRUCTURE'
            if plan:
                hit, option = plan
                target['unit_id'] = option['unit_id']
                card.update(document_id=target['document_id'], document_name=target['document_name'],
                            heading=target['heading'], coordinate=ur.unit_label(inv.s,hit),
                            target_scope={'unit_id':option['unit_id'],'extent':option['extent'],
                                          'block_ids':list(option['block_ids'])})
                if not card['already_read'] and not decision:
                    identity = {k:target[k] for k in ('source_id','document_id','unit_id')}
                    identity['connection'] = {'scope_id':scope['id'], 'reference_id':connection['reference_id'],
                        'group_signature':rel.group_signature(inv.question, group),
                        'witness_sha256':connection['witness_sha256'],
                        'endpoint_block_ids':connection['endpoint_block_ids']}
                    ident = lc.token(inv.s,'T',['READ_ARTICLES',endpoint_key(group,connection)])
                    # Keep the first exact scope/witness binding. Execution
                    # revalidates that binding through validate_inline_read;
                    # other paths to this same extent cannot overwrite it.
                    actions.setdefault(ident,{'id':ident,'action':'READ_ARTICLES','identity':identity,
                        'label':target['document_name']+' '+card['coordinate']+' 연결 원문 읽기'})
                    card['read_action'] = ident
            key=(group['anchor']['source_id'],group['direction'],endpoint_key(group,connection))
            if key in by_endpoint:
                previous=by_endpoint[key]
                witness={k:deepcopy(card[k]) for k in ('reference_witness','anchor_coordinate',
                    'anchor_endpoint_quote','anchor_endpoint_quote_truncated','anchor_head_block_ids',
                    'defines_anchor_wording','reading_policy','resolution')}
                additional=previous.setdefault('additional_reference_witnesses',[])
                # Preserve every verified witness for this endpoint.
                additional.append(witness)
                if 'read_action' in card:previous['read_action']=card['read_action']
                previous['already_read']=previous['already_read'] and card['already_read']
                continue
            by_endpoint[key]=card
            cards.append(card)
    return cards



def validate_inline_read(inv, identity, data, reason):
    """Recheck the offered witness and endpoint before using the normal reader."""
    link = identity.get('connection')
    if not link:
        return
    # Earlier targets in the same accepted READ batch can add originals. They
    # do not change its chosen anchor. Still recheck the exact offered scope,
    # current authorization, witness and endpoint before every target read.
    selected = current(inv, allow_acquired_change=True)
    prior = any(c.get('connection_scope_id') == link['scope_id'] and
        c.get('reference_id') == link['reference_id'] and c.get('target',{}).get('source_id') == identity['source_id']
        for c in data.get('references',{}).get('previously_inspected_cards',[]))
    if not prior and (selected is None or selected['scope']['id'] != link['scope_id']):
        raise ContractError('inline connection is outside the final selected scope')
    from . import unit_relations as rel
    scope = next((s for s,_ in candidates(inv,data) if s['id']==link['scope_id']), None)
    if scope is None:
        raise ContractError('stale inline connection scope')
    if prior and directory_receipt(inv,scope) is None:
        raise ContractError('historical connection directory receipt missing')
    with bound(inv.s,scope):
        groups,_,_,_ = rel.catalog(inv.s,[m['source_id'] for m in scope['members']],
            inv.read_records(),set(),only_references={link['reference_id']})
    matching = [g for g in groups if g['target']['source_id']==identity['source_id']
        and any(c['reference_id']==link['reference_id']
            and c['witness_sha256']==link['witness_sha256']
            and c['endpoint_block_ids']==link['endpoint_block_ids'] and any(
            str(g['offers'][key][1]['unit_id'])==str(identity['unit_id'])
            for key in c['endpoint_scopes']) for c in g['connections'])]
    if not matching:
        raise ContractError('stale inline connection endpoint')
    accept(inv,scope,data,reason)


def accept(inv, scope, data, reason, *, replay=False):
    if replay:
        offered = {v['scope']['id']: v['scope'] for v in inv.p.get('connection_scope_history', [])
                   if v['binding'] == digest(inv.p['binding'])}
        # Immutable frame/history is presentation authority; original spans and
        # current authorization are independently revalidated on every replay.
        from .unit_relations import delivered_blocks
        delivered_blocks(inv.s, {m['source_id']: m['spans'] for m in scope['members']})
    else:
        offered = {s['id']: s for s, _ in candidates(inv, data)}
    if offered.get(scope.get('id')) != scope:
        raise ContractError('stale or undelivered selected connection scope')
    value = {'scope': deepcopy(scope), 'binding': digest(inv.p['binding']),
             'acquired_signature': acquired_signature(inv), 'reason': reason, 'status': 'SELECTED'}
    inv.p['selected_connection_scope'] = value
    inv.p.setdefault('connection_scope_history', []).append(deepcopy(value))
    inv.s.repo.event('CONNECTION_SCOPE_SELECTED', value)
    inv.save()
    return value


@contextmanager
def bound(session, scope):
    """Temporary catalog filter; delivery history and acquired evidence unchanged."""
    sentinel = object(); previous = getattr(session, 'connection_scope_spans', sentinel)
    session.connection_scope_spans = {r['source_id']: r['spans'] for r in scope['members']}
    try:
        yield
    finally:
        if previous is sentinel:
            del session.connection_scope_spans
        else:
            session.connection_scope_spans = previous


def acquire_small_directory(inv, scope, directory):
    """At most two complete distinct endpoints, once, without model recursion.

    The normal reader retains ownership of permissions, hashes, evidence and
    budgets. An acquired original is not an applicability or sufficiency vote.
    """
    if not small_context(inv):
        return []
    from .guided_navigation import enabled as guided
    if guided(getattr(inv.s, 'profile', {})):
        return acquire_role_chain(inv, scope, directory)
    from . import unit_relations as rel, law_candidates as lc, tool_availability as av
    from .definition_context import record_failure
    from .errors import BudgetExhausted
    from .request_repair import recoverable_tool_failure
    revision = 'small-connection-context-v1'
    key = digest([revision, inv.p['binding'], sorted(inv.s.scope), directory_key(scope)])
    history = inv.p.setdefault('small_connection_directories', {})
    attempts = inv.p.setdefault('small_connection_attempts', {})

    def check(row):
        if row.get('sha256') != digest({k:v for k,v in row.items() if k != 'sha256'}):
            raise ContractError('automatic connection receipt hash mismatch')

    def save(row):
        row['sha256'] = digest({k:v for k,v in row.items() if k != 'sha256'})
        inv.save()

    if key in history:
        check(history[key])
        if history[key]['status'] != 'STARTED':
            return list(history[key]['groups'])
    row = history.setdefault(key, {'scope_id':scope['id'], 'status':'STARTED',
        'groups':[], 'targets':[], 'reason':None, 'model_called':False,
        'recursive':False, 'absence_proven':False})
    save(row)
    plans = {}
    for group in directory['groups']:
        for link in group['connections']:
            endpoint = endpoint_key(group, link)
            if endpoint not in plans:
                plans[endpoint] = (group, link, read_plan(group, link))
    row['endpoint_count'] = len(plans)
    row['unresolved_count'] = len(directory.get('unresolved', []))
    reason = ('INCOMPLETE_DIRECTORY' if directory['status'] != 'COMPLETE'
              or directory.get('limits') else
              'MISSING_PARENT_BODY' if any(m.get('missing_parent_body_block_ids') for m in scope['members']) else
              'MORE_THAN_TWO_ENDPOINTS' if len(plans) > 2 else
              'UNREADABLE_ENDPOINT' if any(p is None for _,_,p in plans.values()) else None)
    sequences = []
    if reason is None:
        for _, link, plan in plans.values():
            if not link['already_read']:
                hit, offer = plan
                sequences.extend([(hit,offer), *av.context_plans(inv.s,hit,offer)])
        added, calls = av.sequence_cost(inv.s, sequences, inv.s.repo.evidence())
        reason = ('AUTO_CONTEXT_CHARACTER_LIMIT' if added > 12000 else
                  av.budget_reason(inv.s, added, calls, inv.p['read_state']))
    if reason:
        row.update(status='MENU_ONLY', reason=reason)
        save(row)
        inv.s.repo.event('SMALL_CONNECTION_DIRECTORY', deepcopy(row))
        return []
    for endpoint, (group, link, plan) in plans.items():
        hit, offer = plan
        if link['already_read']:
            continue
        identity = {k:hit[k] for k in ('source_id','document_id')}
        identity['unit_id'] = offer['unit_id']
        rid = digest([revision, inv.p['binding'], sorted(inv.s.scope), identity, offer])
        if rid in attempts:
            check(attempts[rid])
            prior = attempts[rid]
            if prior.get('group_id'):
                row['groups'] = list(dict.fromkeys(row['groups'] + [prior['group_id']]))
            if prior['status'] in ('COMPLETE','PARTIAL','FAILED'):
                if prior['status'] != 'COMPLETE': row['reason'] = 'PREVIOUS_TARGET_FAILURE'
                continue
        target = attempts.setdefault(rid, {'status':'RESERVED', 'identity':identity,
            'offer_hash':digest(offer), 'reference_id':link['reference_id'], 'group_id':None})
        row['targets'] = list(dict.fromkeys(row['targets'] + [rid]))
        save(target); save(row)
        stage = 'READ'; gid = None
        try:
            checked, unavailable = av.article_plan(inv.s, identity)
            if unavailable:
                raise ContractError('automatic connection endpoint changed: ' + unavailable)
            checked_hit, checked_offer = checked
            if set(checked_offer['block_ids']) != set(offer['block_ids']):
                raise ContractError('automatic connection endpoint extent changed')
            # Revalidate canonical action permissions as in manual navigation.
            from .query_scope import action_allowed
            if not action_allowed(inv.s, 'READ_ARTICLES', identity):
                row['reason'] = 'OUTSIDE_DIRECT_SEARCH_SCOPE'
                target.update(status='FAILED', reason=row['reason']); save(target)
                continue
            material = ur.read(inv.s, checked_hit, checked_offer, action_state=inv.p['read_state'])
            if not material['complete']:
                raise ContractError('automatic connection read incomplete')
            inv.add_reads([{**material,'hit':checked_hit}])
            gid = lc.token(inv.s,'B',[hit['source_id'],lc.parent_offer(inv.s,checked_hit)['id']])
            target['group_id'] = gid
            row['groups'] = list(dict.fromkeys(row['groups'] + [gid]))
            save(target); save(row)
            stage = 'CONTEXT'
            inv.register_read(inv.p['groups'][gid], material,
                reason='선택 범위와 상위 본문의 연결2개 이하 원문 동반 확보; 적용 판단 전')
            target['status'] = 'COMPLETE'; save(target); save(row)
            inv.s.repo.event('SMALL_CONNECTION_ORIGINAL_ACQUIRED', {
                'scope_id':scope['id'], 'group_id':gid, 'reference_id':link['reference_id'],
                'identity':identity, 'offer':material['offer'], 'automatic_adoption':False,
                'model_called':False, 'recursive':False})
        except (BudgetExhausted, TimeoutError, ToolExecutionError, sqlite3.OperationalError) as error:
            if not isinstance(error, BudgetExhausted) and recoverable_tool_failure(error) is None:
                raise
            target.update(status='PARTIAL' if gid else 'FAILED', reason=type(error).__name__)
            row['reason'] = 'TARGET_UNAVAILABLE'; save(target); save(row)
            recovery = record_failure(inv,error,stage=stage,identity=identity,offer=offer,
                group_id=gid,anchor_key=key,origin='SMALL_CONNECTION_CONTEXT',revision=revision)
            if recovery == 'STOP':
                raise
    row['status'] = 'PARTIAL' if row['reason'] or row['unresolved_count'] else 'COMPLETE'
    save(row)
    inv.s.repo.event('SMALL_CONNECTION_DIRECTORY', deepcopy(row))
    return list(row['groups'])


ROLE_CHAIN = 'role-chain-v1'
CHAIN_LIMITS = {'outgoing': 6, 'pair_incoming': 3, 'matched_incoming': 2, 'chars': 12000, 'depth': 2}
ROLE_LABELS = {'SPECIFIES': '구체화', 'EXCEPTION': '특칙·예외', 'MUTATIS': '준용', 'BORROWS': '차용',
               'TRANSITIONAL': '부칙 경과·적용례'}


def heading_terms(text):
    """Content words of an article heading, for a same-subject check; never a legal meaning."""
    from .guided_navigation import question_terms
    return {t for t in question_terms(text or '') if len(t) >= 2 and t not in HEADING_GENERIC}


HEADING_GENERIC = {'규정', '규칙', '기준', '정의', '목적', '적용', '범위', '특례', '특칙', '예외', '벌칙', '과태료', '위임', '준용', '기타', '사항', '조치', '절차', '방법'}


def same_subject(card, terms=()):
    """An incoming citation whose article heading shares a content word with the cited
    article's heading or with the user's question names the same subject (벤처기업법 제16조의3
    주식매수선택권 ← 제16조의5 주식매수선택권의 행사). Such an article stays selectable instead
    of being counted away as reuse; it is not read automatically and proves nothing."""
    target = heading_terms(((card.get('target') or {}).get('heading') or '') + ' ' + (card.get('heading') or ''))
    anchor = heading_terms((card.get('anchor') or {}).get('heading') or '')
    return bool(target & (anchor | {t for t in terms if len(t) >= 2}))


SENTENCE_CARD_LIMIT = 12
SENTENCE_CARD_NOTES = {
    'MUTATIS': '이 조문이 현재 조문을 다른 대상에 준용한다. 질문 대상이 그 대상이면 READ한다.',
    'APPLIES_CASE': '이 조문이 특정한 경우에 현재 조문의 적용 결과(금액·기준 등)를 따로 정한다. 질문이 그 경우이면 READ한다.',
    'IMPLEMENTS': '하위 규정이 현재 조문을 시행하는 세부를 정한다. 질문이 그 세부이면 READ한다.'}


def relation_kind(card):
    return (card.get('citation_relation') or {}).get('kind')


def term_overlap(text, terms):
    """How many question words appear in one citing sentence; an ordering hint only."""
    return sum(1 for t in terms if len(t) >= 2 and t in (text or ''))


def question_match(link, terms):
    """A reverse 준용 whose extended subject is a question word ("감사에 준용" for a question about
    감사), or a case-specific application whose sentence holds two or more question words
    ("주식매수선택권을 행사하여 취득한 주식을 양도하는 때에는 …"). The system reads these with the cited
    rule instead of leaving the choice to the model; it is a reading decision, not applicability."""
    from .citation_roles import MUTATIS, APPLIES_CASE
    relation = link.get('citation_relation') or {}
    if relation.get('kind') == MUTATIS:
        subject = relation.get('subject') or ''
        return any(len(t) >= 2 and t in subject for t in terms)
    if relation.get('kind') == APPLIES_CASE:
        return term_overlap(relation.get('sentence'), terms) >= 2
    return False


def list_only_incoming(cards, actions, listed, terms=()):
    """Guided reading keeps forward, pair and same-subject links. A reverse 준용, a case-specific
    application and a lower rule's implementing sentence stay selectable as one-sentence cards
    (question words first, bounded); other reuse stays a count."""
    from .citation_roles import PAIR_ROLES, CARD_KINDS
    kept = []; sentence_cards = []
    for card in cards:
        if card['direction'] == 'OUTGOING' or card.get('citation_role') in PAIR_ROLES or same_subject(card, terms):
            kept.append(card)
        elif relation_kind(card) in CARD_KINDS and card.get('read_action') and not card.get('already_read'):
            sentence_cards.append(card)
        else:
            listed.append(card)
    sentence_cards.sort(key=lambda c: -term_overlap((c.get('citation_relation') or {}).get('sentence'), terms))  # stable
    offered = set()
    for card in sentence_cards:
        # One sentence may cite the same rule twice; the limit counts distinct reads.
        if card['read_action'] not in offered and len(offered) >= SENTENCE_CARD_LIMIT:
            listed.append(card)
            continue
        offered.add(card['read_action'])
        relation = card['citation_relation']
        card['citation_note'] = SENTENCE_CARD_NOTES[relation['kind']] + (' 대상: ' + relation['subject'] + '.' if relation.get('subject') else '') + ' 맞지 않으면 읽지 않는다. READ는 차감되지 않는다.'
        kept.append(card)
    used = {c.get('read_action') for c in kept}
    for card in listed:
        ident = card.get('read_action')
        if ident and ident not in used:
            actions.pop(ident, None)
    return kept


def remember_list_only(inv, listed):
    """Keep identities of not-offered incoming links for the answer's unread notes."""
    saved = inv.p.setdefault('list_only_connections', {})
    for card in listed:
        target = card.get('target') or {}
        scope = card.get('target_scope') or {}
        key = digest([card.get('reference_id'), target.get('source_id'), scope.get('unit_id')])
        if key in saved or len(saved) >= 60:
            continue
        saved[key] = {'role': card.get('citation_role') or 'BORROWS', 'anchor_label': (card.get('anchor') or {}).get('heading', ''),
            'identity': {'source_id': target.get('source_id'), 'document_id': target.get('document_id'), 'unit_id': scope.get('unit_id')},
            'block_ids': list(scope.get('block_ids') or []), 'label': ' '.join(dict.fromkeys(((card.get('coordinate') or '') + ' ' + (target.get('heading') or '')).split())),
            'witness': (card.get('reference_witness') or {}).get('text', '')[:200] if isinstance(card.get('reference_witness'), dict) else ''}


def incoming_summary(listed):
    groups = {}
    for card in listed:
        row = groups.setdefault(card.get('citation_role') or 'BORROWS', {'count': 0, 'examples': []})
        row['count'] += 1
        if len(row['examples']) < 6:
            # The citing article is the card target for an incoming link.
            target = card.get('target') or {}
            words = ((card.get('coordinate') or '') + ' ' + (target.get('heading') or '')).split()
            row['examples'].append(' '.join(dict.fromkeys(words)))
    return {'meaning': '현재 조문을 인용하지만 규칙을 바꾸지 않는 연결(다른 사항에 빌려 씀·준용·부칙 경과)이다. 본문은 제공하지 않는다. '
                       '질문이 그 사항 자체를 물을 때만 구조 검색으로 해당 조문을 찾는다.',
            'by_role': {ROLE_LABELS.get(k, k): v for k, v in sorted(groups.items())}}


def chain_rows(directory, *, forward_only, terms=()):
    """Choose reads by citation role: forward links and rule-changing pairs only. Within one
    role, a citing sentence that shares question words comes first (the landing paragraph the
    search matched), then original order."""
    from .citation_roles import PAIR_ROLES, EXCEPTION
    rows = []; seen = set()
    for group in directory['groups']:
        for link in group['connections']:
            outgoing = group['direction'] == 'OUTGOING'
            pair = link.get('citation_role') in PAIR_ROLES
            matched = not outgoing and not pair and not forward_only and question_match(link, terms)
            if not outgoing and (forward_only or not (pair or matched)):
                continue
            endpoint = endpoint_key(group, link)
            if endpoint in seen:
                continue
            seen.add(endpoint)
            rows.append({'group': group, 'link': link, 'plan': read_plan(group, link), 'endpoint': endpoint,
                         'outgoing': outgoing, 'pair': pair, 'matched': matched, 'role': link.get('citation_role')})
    rows.sort(key=lambda r: (not r['pair'], r['role'] != EXCEPTION,
                             -term_overlap((r['link'].get('citation_relation') or {}).get('sentence'), terms),
                             r['link'].get('witness_source_order', 0)))
    # Question-matched reverse links are one short unit each; read them before the character
    # budget goes to the landing article's general forward citations.
    return ([r for r in rows if r['matched']][:CHAIN_LIMITS['matched_incoming']] +
            [r for r in rows if r['outgoing']][:CHAIN_LIMITS['outgoing']] +
            [r for r in rows if not r['outgoing'] and r['pair']][:CHAIN_LIMITS['pair_incoming']])


SECTION_LIMITS = {'articles': 10, 'reads': 2, 'preview_chars': 600}
REASON_TEXT = {  # (clause, judged_unneeded)
    'ROLE_CHAIN_CHARACTER_LIMIT': ('이번 요청의 자동 읽기 분량 한도(12,000자)를 넘어서', False),
    'CHAIN_COUNT_LIMIT': ('자동으로 읽는 연결 수 한도(정방향 6개·구체화/예외 3개)를 넘어서', False),
    'TOOL_ACTION_LIMIT': ('이번 요청의 도구 실행 한도에 닿아서', False),
    'OUTSIDE_DIRECT_SEARCH_SCOPE': ('사용자가 지정한 검색 범위 밖이라서', False),
    'TARGET_UNAVAILABLE': ('원문 조회가 완료되지 않아서', False),
    'NO_EXECUTABLE_ENDPOINT_SCOPE': ('읽을 수 있는 원문 범위가 확인되지 않아서', False),
    'SECTION_TERMS_NOT_MATCHED': ('같은 절 조문이지만 앞부분에 절 제목의 핵심 표현이 함께 나오지 않아서', True),
    'SECTION_READ_LIMIT': ('같은 절 자동 읽기 한도(2개)를 넘어서', False),
    'SECTION_TOO_LARGE': ('조문이 많은 절이라 같은 절 자동 읽기 대상에서 빠져서', False),
    'SAME_SUBJECT_INCOMING': ('현재 조문을 인용하는 같은 제도의 조문이라 자동 읽기 대상은 아니지만 필요하면 바로 읽을 수 있어서', False)}


def _chain_read(inv, row, attempts, budget, identity, hit, offer, *, reason, meta, char_limit=None):
    """One automatic read through the normal reader; returns (group_id, material) or None."""
    from . import law_candidates as lc, tool_availability as av
    from .definition_context import record_failure
    from .errors import BudgetExhausted
    from .request_repair import recoverable_tool_failure
    rid = digest([ROLE_CHAIN, inv.p['binding'], sorted(inv.s.scope), identity, offer])
    if rid in attempts:
        prior = attempts[rid]
        if prior.get('group_id'):
            row['groups'] = list(dict.fromkeys(row['groups'] + [prior['group_id']]))
        if prior['status'] == 'COMPLETE':
            return prior.get('group_id'), inv.p['selected'].get(prior.get('group_id'))
        return None
    sequences = [(hit, offer), *av.context_plans(inv.s, hit, offer)]
    added, calls = av.sequence_cost(inv.s, sequences, inv.s.repo.evidence())
    code = ('ROLE_CHAIN_CHARACTER_LIMIT' if budget['chars'] + added > (char_limit or CHAIN_LIMITS['chars']) else
            av.budget_reason(inv.s, added, calls, inv.p['read_state']))
    if code:
        row['skipped'].append({**meta, 'identity': identity, 'block_ids': list(offer['block_ids']), 'reason': code})
        return None
    target = attempts.setdefault(rid, {'status': 'RESERVED', 'identity': identity, 'offer_hash': digest(offer),
        'meta': deepcopy(meta), 'group_id': None})
    stage = 'READ'; gid = None
    try:
        checked, unavailable = av.article_plan(inv.s, identity)
        if unavailable:
            raise ContractError('automatic connection endpoint changed: ' + unavailable)
        checked_hit, checked_offer = checked
        if set(checked_offer['block_ids']) != set(offer['block_ids']):
            raise ContractError('automatic connection endpoint extent changed')
        from .query_scope import action_allowed
        if not action_allowed(inv.s, 'READ_ARTICLES', identity):
            target.update(status='FAILED', reason='OUTSIDE_DIRECT_SEARCH_SCOPE')
            row['skipped'].append({**meta, 'identity': identity, 'block_ids': list(offer['block_ids']), 'reason': 'OUTSIDE_DIRECT_SEARCH_SCOPE'})
            return None
        material = ur.read(inv.s, checked_hit, checked_offer, action_state=inv.p['read_state'])
        if not material['complete']:
            raise ContractError('automatic connection read incomplete')
        inv.add_reads([{**material, 'hit': checked_hit}])
        gid = lc.token(inv.s, 'B', [hit['source_id'], lc.parent_offer(inv.s, checked_hit)['id']])
        target['group_id'] = gid
        stage = 'CONTEXT'
        inv.register_read(inv.p['groups'][gid], material, reason=reason)
        target['status'] = 'COMPLETE'
        budget['chars'] += added
        row['groups'] = list(dict.fromkeys(row['groups'] + [gid]))
        row['reads'].append({**meta, 'identity': identity, 'chars': added})
        inv.s.repo.event('ROLE_CHAIN_ORIGINAL_ACQUIRED', {**meta, 'group_id': gid, 'identity': identity,
            'automatic_adoption': False, 'model_called': False})
        return gid, material
    except (BudgetExhausted, TimeoutError, ToolExecutionError, sqlite3.OperationalError) as error:
        if not isinstance(error, BudgetExhausted) and recoverable_tool_failure(error) is None:
            raise
        target.update(status='PARTIAL' if gid else 'FAILED', reason=type(error).__name__)
        row['skipped'].append({**meta, 'identity': identity, 'block_ids': list(offer['block_ids']), 'reason': 'TARGET_UNAVAILABLE'})
        if record_failure(inv, error, stage=stage, identity=identity, offer=offer, group_id=gid,
                anchor_key=meta.get('directory'), origin='ROLE_CHAIN', revision=ROLE_CHAIN) == 'STOP':
            raise
        return None


UNREAD_LIMITS = {'entries': 30, 'text_chars': 1500}
RELATION_TEXT = {'SPECIFIES': '규칙을 구체화하는 조문(역방향)', 'EXCEPTION': '특칙·예외 조문(역방향)',
    'MUTATIS': '이 조문을 준용하는 조문(역방향)', 'BORROWS': '이 조문을 기준으로 인용하는 조문(역방향)',
    'TRANSITIONAL': '부칙 경과 규정(역방향)', 'SAME_SECTION': '같은 절의 조문', None: '인용한 조문(정방향)'}
LIST_ONLY_REASON = {
    'MUTATIS': '다른 대상에 이 조문을 준용하는 규정이라 지금 질문의 기준을 바꾸지 않는 것으로 보아서',
    'BORROWS': '다른 제도가 이 조문을 기준으로 빌려 쓰는 규정이라 지금 질문의 기준을 바꾸지 않는 것으로 보아서',
    'TRANSITIONAL': '개정 전후의 적용 시기를 정하는 부칙이라 지금 기준 설명에는 필요하지 않다고 보아서'}


def document_name(session, did):
    """Registered catalogue name of one document, or '' when the port has none."""
    try:
        return str(session.matcher.documents[did] or '')
    except (AttributeError, KeyError, TypeError):
        return ''


def section_level(heading):
    """"제4장 내부통제 …" -> 장; the structure word of a heading (편/장/절/관), 절 when absent."""
    import re
    m = re.match(r'^\s*제\d+(?:의\d+)?\s*(편|장|절|관)', heading or '')
    return m.group(1) if m else '절'


def article_label(text):
    """"제433조 정관변경의 방법" -> "제433조(정관변경의 방법)"; other labels unchanged."""
    import re
    text = re.sub(r'\s+', ' ', text or '').strip()
    text = re.sub(r'(제\d+조(?:의\d+)?)\s*[①-⑳]\s*', r'\1 ', text)
    m = re.match(r'^(.*?제\d+조(?:의\d+)?)\s+([^()]+)$', text)
    return m.group(1) + '(' + m.group(2) + ')' if m else text


def unread_connections(inv):
    """Connections the system saw but did not read, with the system's own reason.

    This is a location record, never evidence: the text is shown separately
    as "not used for the answer" and the absence of a reading proves nothing.
    """
    import re
    known = {}
    for e in inv.s.repo.evidence():
        known.setdefault(e['source_id'], set()).update(str(p['block_id']) for p in e['spans'])
    rows = []
    for receipt in (inv.p.get('role_chain_directories') or {}).values():
        for skip in receipt.get('skipped', []):
            if skip.get('identity'):
                clause, judged = REASON_TEXT.get(skip['reason'], ('이번 요청의 자동 읽기 대상에서 빠져서', False))
                if skip['reason'] == 'SECTION_TERMS_NOT_MATCHED' and skip.get('terms'):
                    level = skip.get('section_level') or '절'
                    clause = '같은 ' + level + ' 조문이지만 앞부분에 ' + level + ' 제목의 핵심 표현(' + '·'.join(skip['terms']) + ')이 함께 나오지 않아서'
                rows.append({**skip, 'reason_code': skip['reason'], 'reason': clause, 'judged_unneeded': judged})
    for item in (inv.p.get('list_only_connections') or {}).values():
        rows.append({**item, 'outgoing': False, 'reason_code': 'LIST_ONLY_' + str(item['role']),
                     'reason': LIST_ONLY_REASON.get(item['role'], LIST_ONLY_REASON['BORROWS']), 'judged_unneeded': True})
    result = []; seen = set(); seen_labels = set()
    units = getattr(getattr(inv.s, 'matcher', None), 'units', None) or {}
    # A target in a document the answer did not read is named with its document.
    read_documents = {(inv.s.tools.sources.get(sid) or {}).get('document_id') for sid in known}
    for row in rows:
        ident = row['identity']; did = ident.get('document_id'); uid = ident.get('unit_id')
        blocks = [str(b) for b in row.get('block_ids') or []]
        key = (did, str(uid))
        if key in seen or did not in inv.s.scope or not blocks:
            continue
        read_part = set(blocks) & known.get(ident.get('source_id'), set())
        if read_part == set(blocks):
            continue
        seen.add(key)
        node = units.get((did, str(uid))) or {}
        label = row.get('label') or ' '.join(x for x in (node.get('surface'), node.get('title')) if x) or str(uid)
        label = article_label(label)
        # Paragraph units of one article carry the same article label: one entry per article.
        if (did, label) in seen_labels:
            continue
        seen_labels.add((did, label))
        # Only the unread part of an article some of whose text was already read.
        unread_blocks = [b for b in blocks if b not in read_part]
        if did not in read_documents:
            name = document_name(inv.s, did)
            if name:
                label = '「' + name + '」 ' + label
        if read_part:
            label += ' 중 읽지 않은 부분'
        text = ''
        for bid in (unread_blocks if len(result) < UNREAD_LIMITS['entries'] else []):
            if len(text) >= UNREAD_LIMITS['text_chars']:
                break
            text += inv.s.store.source(did, bid)['text'] + '\n'
        text = text.strip()
        clipped = len(text) > UNREAD_LIMITS['text_chars']
        anchor = article_label(row.get('anchor_label') or '')
        level = row.get('section_level') or '절'
        reason = row['reason']
        if row.get('role') == 'SAME_SECTION' and level != '절':
            for word in ('같은 절', '절 제목', '많은 절'):
                reason = reason.replace(word, word.replace('절', level))
        result.append({'unread_id': 'U' + str(len(result) + 1), 'from_label': anchor,
            'target_label': label, 'document_id': did, 'source_id': ident.get('source_id'), 'unit_id': str(uid),
            'relation': row.get('role') if not row.get('outgoing') else None,
            'relation_text': RELATION_TEXT.get(None if row.get('outgoing') else row.get('role'), '연결된 조문').replace('같은 절', '같은 ' + level),
            'reason_code': row['reason_code'], 'reason': reason, 'judged_unneeded': row['judged_unneeded'],
            'section': row.get('section') or '', 'section_level': level, 'partially_read': bool(read_part),
            'list_only': row['reason_code'].startswith('LIST_ONLY_'),
            'text': text[:UNREAD_LIMITS['text_chars']], 'text_clipped': clipped,
            'used_as_evidence': False, 'absence_proven': False})
    return {'entries': result[:UNREAD_LIMITS['entries']], 'total': len(result),
            'meaning': '시스템이 확인했지만 읽지 않은 연결 조문이다. 답변 근거가 아니며 읽지 않았다고 내용이 없다는 뜻이 아니다.'}


def _unit_label(inv, hit):
    try:
        return ur.unit_label(inv.s, hit)
    except (AttributeError, KeyError):
        return ''


def section_terms(title):
    """Content words of a section heading ("제5절 정관의 변경" -> 정관, 변경)."""
    import re
    text = re.sub(r'^\s*제\d+(?:편|장|절|관)(?:의\d+)?\s*', '', title or '')
    words = [re.sub(r'(?:의|및|등|에|관한|대한|에관한)$', '', w) for w in re.split(r'[\s·ㆍ,()]+', text)]
    return [w for w in words if len(w) >= 2]


def _article_source(session, did, uid):
    """Source of one article unit through the matcher's member index (point lookup on every port)."""
    for sid in session.matcher._unit_sources(did, str(uid)):
        src = session.tools.sources.get(sid) or {}
        if src.get('document_id') == did and str(src.get('unit_id')) == str(uid):
            return sid
    return None


def section_children(session, did, parent):
    """Child unit IDs of one parent, in document order, without enumerating the corpus.

    SQLite binds the whole generation as an in-memory dict, but the Oracle port pages
    published rows with a per-call row budget, so a units.items() scan fails there
    (QUERY_NAV_BUDGET). Same dispatch as structure_selection.children.
    """
    parent = str(parent)
    cache = session.__dict__.setdefault('_section_children_by_parent', {})
    if (did, parent) in cache:
        return cache[(did, parent)]
    matcher = session.matcher; values = matcher.units
    if hasattr(values, 'children_for'):
        rows = values.children_for(did, parent)
    else:
        prepared = getattr(matcher, 'prepared_structure', None)
        if prepared is not None and values is prepared['units']:
            from .structure_query import document_tree
            rows = (((did, u), values[(did, u)]) for u in document_tree(matcher, did)['children'].get(parent, ()))
        else:
            index = session.__dict__.setdefault('_section_children_index', {})
            if did not in index:
                found = {}
                source = values.for_document(did) if hasattr(values, 'for_document') else (
                    (key, unit) for key, unit in values.items() if key[0] == did)
                for key, unit in source:
                    owner = unit.get('parent')
                    found.setdefault(str(owner) if owner is not None else None, []).append((key, unit))
                index[did] = found
            rows = index[did].get(parent, ())
    out = []
    for (_, uid), unit in rows:
        owner = unit.get('parent')
        if (str(owner) if owner is not None else None) == parent:
            out.append((tuple(unit.get('span') or (0, 0)), str(uid)))
    cache[(did, parent)] = [u for _, u in sorted(out)]
    return cache[(did, parent)]


def section_neighbors(inv, scope):
    """Unread same-section articles of the selected scope, with a deterministic match.

    A small section groups one legal institution. A sibling whose own opening
    text contains every content word of the section heading is read
    automatically (bounded); other siblings stay as unread notes with the reason.
    """
    import re
    units = getattr(getattr(inv.s, 'matcher', None), 'units', None)
    if units is None:
        return []
    article = re.compile(r'^제\d+조(?:의\d+)?$')
    rows = []; seen = set()
    for member in scope['members']:
        src = inv.s.tools.sources.get(member['source_id']) or {}
        did, uid = src.get('document_id'), src.get('unit_id')
        if did is None or uid is None:
            continue
        uid = str(uid); hops = 0
        while (did, uid) in units and not article.match(str(units[(did, uid)].get('surface', ''))) and hops < 8:
            parent = units[(did, uid)].get('parent')
            if parent is None:
                break
            uid = str(parent); hops += 1
        node = units.get((did, uid)) or {}
        parent = node.get('parent')
        if not article.match(str(node.get('surface', ''))) or parent is None or (did, str(parent)) in seen:
            continue
        seen.add((did, str(parent)))
        section = units.get((did, str(parent))) or {}
        siblings = [u for u in section_children(inv.s, did, parent)
                    if article.match(str((units.get((did, u)) or {}).get('surface', '')))]
        terms = section_terms(section.get('title') or '')
        if len(siblings) > SECTION_LIMITS['articles']:
            continue  # a large section is not one institution; no automatic same-section reading
        for sib in siblings:
            sid = _article_source(inv.s, did, sib) if sib != uid else None
            if sib == uid or not sid:
                continue
            blocks = [str(b) for b in ur.blocks(inv.s, did, sib, 'subtree')]
            preview = ''.join(inv.s.store.source(did, b)['text'] for b in blocks[:4])[:SECTION_LIMITS['preview_chars']]
            if re.match(r'^\s*(?:제\d+조(?:의\d+)?\s*)?삭제', preview):
                continue  # repealed article: nothing to read
            label = ((units[(did, sib)].get('surface') or '') + ' ' + (units[(did, sib)].get('title') or '')).strip()
            rows.append({'anchor_source_id': member['source_id'],
                         'anchor_label': ((node.get('surface') or '') + ' ' + (node.get('title') or '')).strip(),
                         'section': section.get('title') or section.get('surface') or '', 'source_id': sid, 'document_id': did,
                         'section_level': section_level(section.get('surface') or section.get('title') or ''),
                         'unit_id': sib, 'label': label, 'block_ids': blocks,
                         'matched': bool(terms) and all(t in preview for t in terms), 'terms': terms,
                         'too_large': len(siblings) > SECTION_LIMITS['articles']})
    return rows


def acquire_role_chain(inv, scope, directory, *, depth=1):
    """Guided automatic reading without another model hop.

    Depth 1 reads the selected scope's forward citations and the incoming
    citations that specify or except its rule, then up to two same-section
    articles that share the section's content words. Depth 2 follows only the
    forward citations of originals reached through a rule pair, so landing on
    either side of a rule/exception pair yields the same originals. A request
    shares one character budget; every unread link keeps its reason.
    """
    key = digest([ROLE_CHAIN, inv.p['binding'], sorted(inv.s.scope), directory_key(scope), depth])
    history = inv.p.setdefault('role_chain_directories', {})
    attempts = inv.p.setdefault('role_chain_attempts', {})
    start = inv.p.get('request_turn_start', 0)
    budget = inv.p.get('role_chain_budget')
    if not budget or budget.get('request_turn_start') != start:
        budget = inv.p['role_chain_budget'] = {'request_turn_start': start, 'chars': 0}

    def seal(row):
        row['sha256'] = digest({k: v for k, v in row.items() if k != 'sha256'})
        inv.save()

    if key in history:
        if history[key].get('sha256') != digest({k: v for k, v in history[key].items() if k != 'sha256'}):
            raise ContractError('role chain receipt hash mismatch')
        if history[key]['status'] != 'STARTED':
            return list(history[key]['groups'])
    row = history.setdefault(key, {'scope_id': scope['id'], 'scope_label': scope.get('label', ''), 'depth': depth,
        'status': 'STARTED', 'groups': [], 'reads': [], 'skipped': [], 'model_called': False, 'absence_proven': False})
    seal(row)
    pairs = []
    from .citation_roles import PAIR_ROLES
    from .guided_navigation import question_terms
    terms = question_terms(getattr(inv, 'question', '') or '')
    chosen = chain_rows(directory, forward_only=depth > 1, terms=terms)
    chosen_keys = {r['endpoint'] for r in chosen}
    for group in directory['groups']:
        for link in group['connections']:
            outgoing = group['direction'] == 'OUTGOING'
            wanted = outgoing or (depth == 1 and (link.get('citation_role') in PAIR_ROLES or question_match(link, terms)))
            plan = read_plan(group, link)
            related = (not outgoing and depth == 1 and not wanted and not link['already_read'] and plan
                       and same_subject({'target': group.get('target'), 'anchor': group.get('anchor')}, terms))
            if related:
                hit, offer = plan
                row['skipped'].append({'endpoint': endpoint_key(group, link), 'role': link.get('citation_role'),
                    'outgoing': False, 'anchor_label': (group.get('anchor') or {}).get('heading', ''),
                    'identity': {'source_id': hit['source_id'], 'document_id': hit['document_id'], 'unit_id': offer['unit_id']},
                    'block_ids': list(offer['block_ids']), 'reason': 'SAME_SUBJECT_INCOMING'})
                continue
            if (not outgoing and depth == 1 and not wanted and not link['already_read'] and plan
                    and len(inv.p.setdefault('list_only_connections', {})) < 60):
                hit, offer = plan
                inv.p['list_only_connections'].setdefault(digest([link['reference_id'], hit['source_id'], offer['unit_id']]), {
                    'role': link.get('citation_role') or 'BORROWS', 'anchor_label': (group.get('anchor') or {}).get('heading', ''),
                    'identity': {'source_id': hit['source_id'], 'document_id': hit['document_id'], 'unit_id': offer['unit_id']},
                    'block_ids': list(offer['block_ids']), 'label': ' '.join(dict.fromkeys(
                        (_unit_label(inv, hit) + ' ' + ((group.get('target') or {}).get('heading') or '')).split()))})
            if wanted and not link['already_read'] and endpoint_key(group, link) not in chosen_keys and plan:
                hit, offer = plan
                row['skipped'].append({'endpoint': endpoint_key(group, link), 'role': link.get('citation_role'),
                    'outgoing': outgoing, 'anchor_label': (group.get('anchor') or {}).get('heading', ''),
                    'identity': {'source_id': hit['source_id'], 'document_id': hit['document_id'], 'unit_id': offer['unit_id']},
                    'block_ids': list(offer['block_ids']), 'reason': 'CHAIN_COUNT_LIMIT'})
    for item in chosen:
        group, link, plan = item['group'], item['link'], item['plan']
        if link['already_read'] or plan is None:
            if plan is None and not link['already_read']:
                row['skipped'].append({'endpoint': item['endpoint'], 'role': item['role'], 'outgoing': item['outgoing'],
                    'anchor_label': (group.get('anchor') or {}).get('heading', ''), 'reason': 'NO_EXECUTABLE_ENDPOINT_SCOPE'})
            continue
        hit, offer = plan
        identity = {'source_id': hit['source_id'], 'document_id': hit['document_id'], 'unit_id': offer['unit_id']}
        label = ('현재 조문을 질문 대상에 준용·적용' if item.get('matched') else
                 {'SPECIFIES': '현재 조문의 규칙을 구체화', 'EXCEPTION': '현재 조문의 특칙·예외'}.get(item['role'], '현재 조문이 인용'))
        got = _chain_read(inv, row, attempts, budget, identity, hit, offer,
            reason=label + '하는 연결 원문 자동 확보(' + ('정방향' if item['outgoing'] else '역방향') + '); 적용 판단 전',
            meta={'endpoint': item['endpoint'], 'role': item['role'], 'outgoing': item['outgoing'], 'depth': depth,
                  'anchor_label': (group.get('anchor') or {}).get('heading', ''), 'directory': key, 'kind': 'CONNECTION'})
        seal(row)
        if got and item['pair']:
            pairs.append((got[0], hit, offer, got[1]))
    if depth == 1:
        from . import tool_availability as av
        section_reads = 0
        row['section_neighbors'] = []
        for sib in section_neighbors(inv, scope):
            read_keys = {str(b) for b in sib['block_ids']}
            known = set()
            for e in inv.s.repo.evidence():
                if e['source_id'] == sib['source_id']:
                    known.update(str(p['block_id']) for p in e['spans'])
            if read_keys and read_keys <= known:
                continue
            code = ('SECTION_TOO_LARGE' if sib['too_large'] else 'SECTION_TERMS_NOT_MATCHED' if not sib['matched']
                    else 'SECTION_READ_LIMIT' if section_reads >= SECTION_LIMITS['reads'] else None)
            meta = {'kind': 'SECTION', 'role': 'SAME_SECTION', 'outgoing': False, 'depth': depth, 'directory': key,
                    'anchor_label': sib['anchor_label'].strip(), 'section': sib['section'], 'label': sib['label'],
                    'section_level': sib['section_level'],
                    'terms': sib['terms']}
            identity = {'source_id': sib['source_id'], 'document_id': sib['document_id'], 'unit_id': sib['unit_id']}
            if code:
                row['skipped'].append({**meta, 'identity': identity, 'block_ids': sib['block_ids'], 'reason': code})
                continue
            checked, unavailable = av.article_plan(inv.s, identity)
            if unavailable or not checked:
                row['skipped'].append({**meta, 'identity': identity, 'block_ids': sib['block_ids'], 'reason': 'NO_EXECUTABLE_ENDPOINT_SCOPE'})
                continue
            hit, offer = checked
            got = _chain_read(inv, row, attempts, budget, identity, hit, offer,
                reason='같은 ' + sib['section_level'] + '(' + sib['section'] + ')에서 ' + sib['section_level'] + ' 제목의 핵심 표현을 함께 쓰는 조문 자동 확보; 적용 판단 전', meta=meta)
            if got:
                section_reads += 1
            seal(row)
    if depth < CHAIN_LIMITS['depth']:
        for gid, hit, offer, record in pairs:
            if not record:
                continue
            wanted = set(map(str, offer['block_ids']))
            spans = _spans([p for e in record.get('evidence', []) for p in e['spans']], wanted)
            if not spans:
                continue
            member = {'source_id': hit['source_id'], 'document_id': hit['document_id'], 'spans': spans}
            # Display label only; the identity is the verified member spans.
            label = (inventory.scope_path(inv.s, hit, offer) if hit.get('document_name')
                     else str(hit['source_id']) + ' ' + str(offer['unit_id']))
            sub = _scope(label, {'unit_id': offer['unit_id'],
                'extent': offer['extent'], 'role_chain_depth': depth + 1}, [member])
            with bound(inv.s, sub):
                sub_directory = inspect_directory(inv, sub)
            row['groups'] = list(dict.fromkeys(row['groups'] + acquire_role_chain(inv, sub, sub_directory, depth=depth + 1)))
    row['status'] = 'COMPLETE'
    seal(row)
    inv.s.repo.event('ROLE_CHAIN_DIRECTORY', deepcopy(row))
    return list(row['groups'])


def overview(inv):
    value = current(inv, allow_acquired_change=True)
    result = value.get('result', {}) if value else {}
    return {'pending': bool(result.get('pending')), 'connection_groups': 0, 'unresolved_count': result.get('unresolved_count', 0),
            'current_anchor_ids': [], 'current_anchors': [], 'closed_connection_groups': 0,
            'dependency_cards': [], 'omitted_dependency_cards': 0,
            'scope_status': value['status'] if value else 'SELECT_SOURCE_SCOPE',
            'absence_proven': False, 'fallback': 'SEARCH_STRUCTURE', 'selected_scope_result': result,
            'menu': '먼저 사용할 원문의 구조 범위를 선택한다. 연결 누락·실패 시 기존 구조 검색을 사용할 수 있다.'}
