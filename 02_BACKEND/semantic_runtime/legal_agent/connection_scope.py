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

FINISH_GUIDANCE = '''connection_review의 한 범위 조회 완료는 다른 원문의 연결 확인을 대신하지 않는다. source_inspections는 현재 전달된 원문 구간별 실제 연결 조회 상태다. finish_connection_review의 uninspected_basis가 있으면 그 근거의 미확인 연결과 질문 대상 행위를 함께 검토한다. 질문 대상 원문에 수치·조건이 없다는 이유만으로 다른 일반 규정의 적용을 확정하지 않는다. 일반 규정의 '다른 정함', 예외·특칙 조건이 이번 행위에 어떻게 적용되는지 원문으로 확인한다. 대상 원문을 인용하는 INCOMING 연결도 별도 요건의 단서가 될 수 있다. 필요한 범위의 FOLLOW_CONNECTION과 필요한 원문 READ를 선택한다. 모든 원문·연결을 순회하거나 미확인 조항 번호를 추측하지 않는다. 확인할 수 없거나 요청에 불필요하면 실제 남은 범위와 이유를 보존해 기존 제한된 최종 검토로 넘긴다. 조회 실패·일부 확인은 별도 규정 부재의 증명이 아니다.'''


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
    if inv.policy.get('small_connection_context'):
        result = [(with_parent_bodies(inv, scope, pages), refs) for scope, refs in result]
    return result


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
    data['connection_review'] = {
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
    if not inv.policy.get('small_connection_context') or inv.policy.get('read_judgment'):
        return []
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


def overview(inv):
    value = current(inv, allow_acquired_change=True)
    result = value.get('result', {}) if value else {}
    return {'pending': bool(result.get('pending')), 'connection_groups': 0, 'unresolved_count': result.get('unresolved_count', 0),
            'current_anchor_ids': [], 'current_anchors': [], 'closed_connection_groups': 0,
            'dependency_cards': [], 'omitted_dependency_cards': 0,
            'scope_status': value['status'] if value else 'SELECT_SOURCE_SCOPE',
            'absence_proven': False, 'fallback': 'SEARCH_STRUCTURE', 'selected_scope_result': result,
            'menu': '먼저 사용할 원문의 구조 범위를 선택한다. 연결 누락·실패 시 기존 구조 검색을 사용할 수 있다.'}
