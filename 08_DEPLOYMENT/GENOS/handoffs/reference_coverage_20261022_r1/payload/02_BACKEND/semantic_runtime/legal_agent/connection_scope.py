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


def enabled(inv):
    return bool(inv.modern and inv.policy.get('selected_connection_scope'))


def acquired_signature(inv):
    return digest(sorted((gid, digest(r['offer'])) for gid, r in inv.p['selected'].items()
                         if inv.p['groups'][gid]['status'] != 'EXCLUDED'))


def current(inv):
    value = inv.p.get('selected_connection_scope')
    if not value:
        return None
    scope = value['scope']
    if scope['id'] != digest({k: v for k, v in scope.items() if k != 'id'}):
        raise ContractError('connection scope hash mismatch')
    if value['binding'] != digest(inv.p['binding']):
        raise ContractError('connection scope request binding mismatch')
    if value['acquired_signature'] != acquired_signature(inv):
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
    return result


def offer_choices(inv, data, actions):
    if not enabled(inv):
        return
    from .law_candidates import token
    choices = []; previews = {}; cards = []
    inv.bind_reference_delivery(current_pages=data.get('sources', []))
    for scope, refs in candidates(inv, data):
        identity = {'connection_scope': scope}
        target = token(inv.s, 'T', ['FOLLOW_CONNECTION', identity])
        action = {'id': target, 'action': 'FOLLOW_CONNECTION', 'identity': identity,
                  'label': scope['label'] + ' — 이 선택 범위의 연결 확인'}
        # The recovery owner suppresses failed operations and retains their reason.
        if any(f['action'] == 'FOLLOW_CONNECTION' and f['targets'] == [identity]
               for f in inv.p.get('tool_failures', [])):
            continue
        # Inspect each exact source scope independently, without selecting it or
        # merging other acquired articles into its connection frontier.
        preview_key = digest(scope['members'])
        if preview_key in previews:
            continue  # Same delivered spans through another selection alias.
        previews[preview_key] = preview(inv, scope)
        result = previews[preview_key]
        inline = result['status'] == 'COMPLETE' and result['connection_count'] <= INLINE_CONNECTION_LIMIT
        if not inline and result['status'] != 'FAILED':
            actions[target] = action
        if inline:
            shown = inline_cards(inv, scope, refs, result['groups'], actions)
            for card in shown:
                if card.get('requires_scope_menu'):
                    actions[target] = action
                    card['scope_menu_action'] = target
            cards.extend(shown)
        choices.append({'id': scope['id'], 'label': scope['label'], 'source_refs': refs,
                        'structural_selection': scope['structural_selection'],
                        'read_action': target if target in actions else None, 'automatic_adoption': False,
                        'connection_preview': {k:deepcopy(v) for k,v in result.items() if k!='groups'},
                        'connections_presented_inline': inline})
    references = data['references']
    references['dependency_cards'] = cards
    references['inline_connection_limit'] = INLINE_CONNECTION_LIMIT
    references['inline_connection_count'] = len(cards)
    references['omitted_dependency_cards'] = sum(
        p['connection_count'] or 0 for p in previews.values()
        if p['status']!='COMPLETE' or (p['connection_count'] or 0)>INLINE_CONNECTION_LIMIT)
    references['preview_counts_complete'] = all(p['status']=='COMPLETE' for p in previews.values())
    references['menu'] = ('연결이 5개 이하인 정확한 원문 범위는 dependency_cards에 바로 제시했다. '
        '질문과 sources의 확보 원문으로 필요성을 판단하고 필요한 대상의 read_action을 선택한다. '
        '이미 확보한 대상은 다시 조회하지 말고 원문으로 판단한다. 더 많은 연결은 해당 범위의 연결 메뉴로 확인한다.')
    data['connection_scope_choices'] = choices
    data['connection_scope_rule'] = ('읽은 원문 중 현재 요청에 쓸 범위를 판단한다. 연결이 5개 이하이면 '
        '바로 제시된 dependency_cards에서 필요한 원문 READ를 선택한다. 별도 연결 보기 판단은 필요 없다. '
        '더 많은 연결은 해당 범위의 FOLLOW_CONNECTION을 고른다. '
        '다른 원문은 보존되지만 연결 출발점으로 자동 합치지 않는다. 연결 없음·실패는 원문 부재가 아니며 '
        '필요한 법령명·번호를 알면 LOCATE/CATALOG_SEARCH로 구조를 조회하고 원문을 읽는다.')
    data['actions'] = [{k: a[k] for k in ('id', 'action', 'label')} for a in actions.values()]


def preview(inv, scope):
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
                max_connections=INLINE_CONNECTION_LIMIT+1)
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
    cards = []
    closed = inv.closed_reference_decisions(groups, inv.read_records(),
        [m['source_id'] for m in scope['members']])
    for group in groups:
        for connection in group['connections']:
            decision = closed.get(group['key'])
            options = [group['offers'][key] for key in connection['endpoint_scopes']]
            # The endpoint subtree preserves all its children; no article-wide
            # substitution when the reference names a paragraph/item instead.
            plan = next(((h,o) for h,o in options if o['extent']=='subtree'), None)
            if plan is None:
                plan = next(((h,o) for h,o in options
                    if o.get('reader_target')=='source' and o['unit_id'] is None), None)
            target = deepcopy(group['target'])
            card = {'reference_id':connection['reference_id'], 'connection_scope_id':scope['id'],
                'source_refs':list(source_refs), 'anchor':deepcopy(group['anchor']),
                'anchor_excerpt':connection['witness'], 'direction':group['direction'],
                'reading_policy':connection['reading_policy'], 'resolution':connection['resolution'],
                'already_read':connection['already_read'], 'target':target,
                'applicability':decision['applicability'] if decision else 'UNDETERMINED',
                'issue_refs':[i['id'] for i in inv.p.get('issues',[])],
                'preview_is_reference_witness':True}
            if decision:
                card['decision'] = deepcopy(decision)
            if plan is None and not card['already_read'] and not decision:
                card['requires_scope_menu'] = True
            if plan:
                hit, option = plan
                target['unit_id'] = option['unit_id']
                card.update(document_id=target['document_id'], document_name=target['document_name'],
                            heading=target['heading'], coordinate=ur.unit_label(inv.s,hit))
                if not card['already_read'] and not decision:
                    identity = {k:target[k] for k in ('source_id','document_id','unit_id')}
                    identity['connection'] = {'scope_id':scope['id'], 'reference_id':connection['reference_id'],
                        'group_signature':rel.group_signature(inv.question, group),
                        'witness_sha256':connection['witness_sha256'],
                        'endpoint_block_ids':connection['endpoint_block_ids']}
                    ident = lc.token(inv.s,'T',['READ_ARTICLES',identity])
                    actions[ident] = {'id':ident,'action':'READ_ARTICLES','identity':identity,
                        'label':target['document_name']+' '+card['coordinate']+' 연결 원문 읽기'}
                    card['read_action'] = ident
            cards.append(card)
    return cards


def validate_inline_read(inv, identity, data, reason):
    """Recheck the offered witness and endpoint before using the normal reader."""
    link = identity.get('connection')
    if not link:
        return
    from . import unit_relations as rel
    scope = next((s for s,_ in candidates(inv,data) if s['id']==link['scope_id']), None)
    if scope is None:
        raise ContractError('stale inline connection scope')
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


def overview(inv):
    value = current(inv)
    result = value.get('result', {}) if value else {}
    return {'pending': bool(result.get('pending')), 'connection_groups': 0, 'unresolved_count': result.get('unresolved_count', 0),
            'current_anchor_ids': [], 'current_anchors': [], 'closed_connection_groups': 0,
            'dependency_cards': [], 'omitted_dependency_cards': 0,
            'scope_status': value['status'] if value else 'SELECT_SOURCE_SCOPE',
            'absence_proven': False, 'fallback': 'SEARCH_STRUCTURE', 'selected_scope_result': result,
            'menu': '먼저 사용할 원문의 구조 범위를 선택한다. 연결 누락·실패 시 기존 구조 검색을 사용할 수 있다.'}
