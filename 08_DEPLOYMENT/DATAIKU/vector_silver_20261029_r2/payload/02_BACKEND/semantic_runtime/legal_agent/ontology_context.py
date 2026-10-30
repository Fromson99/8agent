"""Approved, scope-preserving ontology originals on an explicit READ.

The profile contains an explicitly injected immutable snapshot, never a path to
discover. The ordinary reader, journal and request budget own all source I/O.
Compilation does not select/adopt evidence or authorize a wider investigation.
"""
from copy import deepcopy
import json
import sqlite3

from ..contracts import digest
from ..term_references import reference_targets
from .errors import BudgetExhausted, ContractError, ToolExecutionError
from . import ontology_compiler as compiler
from . import query_scope as qs, unit_reading as ur, unit_relations as rel
from . import law_candidates as lc, connection_scope as cs
from . import evidence_inventory as inventory
from . import ontology_io

VERSION = 'ontology-context-v0'
MAX_SNAPSHOT_BYTES = 2_000_000
MAX_READS = 128
MAX_CHARS = 24000


def configuration(value):
    if value == {'mode': 'DB'}:
        return {'mode': 'DB'}
    if not isinstance(value, dict) or value.get('mode') not in ('A0', 'A1', 'A2'):
        raise ContractError('invalid ontology mode')
    if value['mode'] == 'A0':
        if set(value) != {'mode'}:
            raise ContractError('A0 must not bind an ontology snapshot')
        return deepcopy(value)
    if set(value) not in ({'mode', 'snapshot', 'snapshot_sha256'}, {'mode', 'snapshot', 'snapshot_sha256', 'semantic_binding'}, {'mode', 'snapshot', 'snapshot_sha256', 'scenario_package'}):
        raise ContractError('explicit ontology snapshot and hash required')
    snapshot = value['snapshot']
    # Reject cycles/depth/huge input before JSON serialization allocates a copy.
    compiler._bounded_json(snapshot)
    if (not isinstance(snapshot, dict) or set(snapshot) != {'schema_version', 'bundles'}
            or snapshot['schema_version'] != 'ontology-snapshot-v0'
            or not isinstance(snapshot['bundles'], list) or not 1 <= len(snapshot['bundles']) <= 256
            or len(json.dumps(snapshot, ensure_ascii=False).encode()) > MAX_SNAPSHOT_BYTES
            or value['snapshot_sha256'] != digest(snapshot)):
        raise ContractError('ontology snapshot binding invalid')
    if 'semantic_binding' in value:
        from . import ontology_semantics
        binding=value['semantic_binding']
        ontology_semantics.validate(binding['proposal'],binding['originals'],binding['judgments'])
        for key in ('proposal','originals','judgments'):
            if digest(binding[key])!=binding[key+'_sha256']:raise ContractError('semantic snapshot changed')
    if 'scenario_package' in value:
        from .ontology_scenarios import verify_package, APPROVED_AUTHORITY
        package=verify_package(value['scenario_package'])
        if package['authority'] != APPROVED_AUTHORITY:
            raise ContractError('runtime scenario requires approved publication; research data is not loadable')
    identities = set()
    for bundle in snapshot['bundles']:
        compiler.validate_bundle(bundle)
        identity = bundle['bundle_id']
        if identity in identities or bundle['status'] != 'APPROVED':
            raise ContractError('ontology snapshot requires unique approved bundles')
        identities.add(identity)
    return deepcopy(value)


def enabled(policy):
    return policy.get('ontology_enabled') is True and policy.get('ontology_context', {}).get('mode', 'A0') != 'A0'


def config(inv):
    if not enabled(inv.policy):
        return {'mode': 'A0'}
    value = inv.policy.get('ontology_context', {'mode': 'A0'})
    if value == {'mode': 'DB'}:
        from ..ontology_work.runtime import config as database_config
        return database_config(inv.policy, inv.p, inv.p['binding'])
    # Detect any mutation before reusing validation; the cache is owned by this
    # investigation only and holds no original data or authority grants.
    compiler._bounded_json(value)
    fingerprint = digest(value)
    cached = getattr(inv, '_ontology_configuration', None)
    if cached is None or cached[0] != fingerprint:
        cached = (fingerprint, configuration(value))
        inv._ontology_configuration = cached
    return deepcopy(cached[1])


def resolve(session, anchor):
    """Check direct investigation scope before consulting any original body."""
    did, uid = anchor['document_id'], anchor['unit_id']
    if did not in session.scope:
        return None, 'DOCUMENT_NOT_AUTHORIZED'
    if (did, uid) not in session.matcher.units:
        return None, 'UNIT_NOT_AVAILABLE'
    if not qs.direct(session, did, uid):
        return None, 'OUTSIDE_INVESTIGATION_SCOPE'
    ids = ur.blocks(session, did, uid, 'exact')
    if not ids:
        return None, 'NO_OWN_BODY'
    sources = [sid for sid in session.matcher._unit_sources(did, uid)
               if sid in session.tools.sources and set(ids) <= {
                   str(b['block_id']) for b in session.tools.sources[sid]['blocks']}]
    if len(sources) != 1:
        return None, 'SOURCE_NOT_UNIQUE'
    sid = sources[0]
    if session.tools.sources[sid]['source_artifact_sha256'] != anchor['version']:
        return None, 'SOURCE_VERSION_CHANGED'
    hit = rel.hit_for(session, sid, uid)
    offers, _ = ur.offer_plan(session, hit)
    offer = next((o for o in offers if o['extent'] == 'exact' and o['unit_id'] == uid), None)
    if offer is None or set(offer['block_ids']) != set(ids):
        return None, 'EXACT_SCOPE_UNAVAILABLE'
    return (hit, offer), None


def arrived(inv, bundle, primary_records):
    for provision in bundle['provisions']:
        anchor = provision['anchor']
        did, uid = anchor['document_id'], anchor['unit_id']
        if (did, uid) not in inv.s.matcher.units or did not in inv.s.scope:
            continue
        ids = set(ur.blocks(inv.s, did, uid, 'exact'))
        for record in primary_records.values():
            if record and record['document_id'] == did and ids.intersection(record['offer']['block_ids']):
                return True
    return False


def _link_covered(group, link, covered, *, incoming_extents=()):
    """Both exact endpoints must be proved; ontology direction can be inverse."""
    outgoing = group['direction'] == 'OUTGOING'
    source = group['anchor']['source_id'] if outgoing else group['target']['source_id']
    target = group['target']['source_id'] if outgoing else group['anchor']['source_id']
    endpoint = set(map(str, link['endpoint_block_ids']))
    if not endpoint:
        return False
    for first, second in covered:
        for left, right in ((first, second), (second, first)):
            if left['source_id'] != source or right['source_id'] != target:
                continue
            own = set(map(str, left['block_ids'])); opposite = set(map(str, right['block_ids']))
            if str(link['witness_block_id']) not in own:
                continue
            if outgoing and endpoint <= opposite:
                return True
            if (not outgoing and endpoint <= own and incoming_extents
                    and all(bool(extent) and set(map(str, extent)) <= opposite for extent in incoming_extents)):
                return True
    return False


def _remaining(inv, bundle, receipts, primary_records):
    """Compare exact verified endpoints; a partial scan is never absence."""
    records = dict(primary_records)
    evidence = ontology_io.evidence(inv.s.repo, [eid for row in receipts for eid in row['evidence_ids']])
    for row in receipts:
        records[row['key']] = {'source_id': row['source_id'], 'document_id': row['anchor']['document_id'],
            'offer': {'block_ids': row['block_ids']},
            'evidence': [evidence[eid] for eid in row['evidence_ids']]}
    # connection_scope.bound indexes members by source_id. Merge same-source
    # own blocks first so a later provision cannot erase an earlier anchor.
    by_source = {}
    for record in records.values():
        member = by_source.setdefault(record['source_id'], {
            'source_id': record['source_id'], 'document_id': record['document_id'], 'spans': []})
        if member['document_id'] != record['document_id']:
            raise ContractError('ontology connection source identity changed')
        member['spans'].extend(cs._spans([p for e in record['evidence'] for p in e['spans']],
                                       set(map(str, record['offer']['block_ids']))))
    members = list(by_source.values())
    for member in members:
        member['spans'] = cs._spans(member['spans'], {str(p['block_id']) for p in member['spans']})
    scope = cs._scope('ontology exact acquired originals', None, members)
    with cs.bound(inv.s, scope):
        groups, statuses, limits, unresolved = rel.catalog(inv.s,
            list(dict.fromkeys(r['source_id'] for r in records.values())), records, set(),
            grant_reads=False, max_connections=compiler.MAX_CONNECTIONS)
    by_label = {r['anchor']['label']: r for r in receipts}
    covered = []
    for edge in bundle['relations']:
        left, right = by_label.get(edge['from']), by_label.get(edge['to'])
        if left and right and edge['type'] != 'UNKNOWN':
            covered.append((left, right))
    remaining = []
    reference_cache = {}
    for group in groups:
        for link in group['connections']:
            incoming_extents = []
            if group['direction'] == 'INCOMING':
                # For incoming links endpoint_block_ids is the witness owner's
                # extent, not the original cited anchor. Recover every cited
                # anchor extent from the already-verified stored reference.
                rid = link['reference_id']
                if rid not in reference_cache:
                    raw = inv.s.tools.db.execute('SELECT json FROM reference WHERE id=?', (rid,)).fetchone()
                    reference_cache[rid] = json.loads(raw[0]) if raw else None
                reference = reference_cache[rid]
                if reference:
                    incoming_extents = [rel.endpoint_blocks(inv.s, endpoint)
                        for endpoint in reference_targets(reference)
                        if endpoint.get('source_id') == group['anchor']['source_id']]
            handled = _link_covered(group, link, covered, incoming_extents=incoming_extents)
            if not handled:
                remaining.append({'reference_id': link['reference_id'],
                    'anchor': deepcopy(group['anchor']), 'target': deepcopy(group['target']),
                    'direction': group['direction'], 'locator': deepcopy(link.get('locator')),
                    'endpoint_block_ids': list(link['endpoint_block_ids']), 'acquired': link['already_read']})
    if len(remaining) > compiler.MAX_CONNECTIONS:
        # One catalogue reference may resolve to several endpoints after its
        # preview boundary. Preserve the overflow as an explicit pending scan.
        limits = [*limits, {'kind': 'ontology_connection_display_limit', 'more_available': True,
                           'omitted_count': len(remaining) - compiler.MAX_CONNECTIONS}]
        remaining = remaining[:compiler.MAX_CONNECTIONS]
    return remaining, {'statuses': statuses, 'limits': limits, 'unresolved': unresolved}


def _interrupted(inv, plan):
    """An unfinished saved operation is not safe to replay as a fresh read.

    Preserve all recorded receipts/reservations, and make the interrupted part
    explicit. Ordinary investigation can continue using its acquired originals.
    """
    if plan['status'] != 'STARTED':
        return
    plan['status'] = 'PARTIAL'
    plan['unresolved'].append({'reason': 'ACQUISITION_INTERRUPTED', 'retry_performed': False})
    inv.s.repo.event('ONTOLOGY_ACQUISITION_INTERRUPTED', {
        'plan_id': plan['id'], 'status': 'PARTIAL', 'retry_performed': False,
        'completed_fragments': len(plan['fragments']), 'reservations_preserved': True})
    inv.save()


def acquire(inv, primary, *, primary_records=None):
    if enabled(inv.policy) and inv.policy.get('ontology_context') == {'mode': 'DB'}:
        from ..ontology_work.runtime import acquire as database_acquire
        database_acquire(inv, primary, primary_records)
    settings = config(inv)
    if settings['mode'] == 'A0':
        return []
    state = inv.p.setdefault('ontology_context', {'version': VERSION,
        'snapshot_sha256': settings['snapshot_sha256'], 'reads': {}, 'plans': {}, 'reserved_chars': 0})
    if state['snapshot_sha256'] != settings['snapshot_sha256'] or state['version'] != VERSION:
        raise ContractError('ontology checkpoint binding changed')
    # register_read may replace a group with another own-block scope. Arrival
    # must stay bound to the caller's explicit originals, never that mutation.
    original_records = inv.p['selected'] if primary_records is None else primary_records
    primary_records = {gid: deepcopy(original_records[gid]) for gid in primary if gid in original_records}
    added = []
    for bundle in sorted(settings['snapshot']['bundles'], key=lambda row: row['bundle_id']):
        if not arrived(inv, bundle, primary_records):
            continue
        key = digest([inv.p['binding'], settings['snapshot_sha256'], bundle['bundle_id']])
        if key in state['plans']:
            previous = state['plans'][key]
            _interrupted(inv, previous)
            added.extend(previous['groups'])
            continue
        plan = state['plans'][key] = {'id': key, 'bundle_id': bundle['bundle_id'],
            'status': 'STARTED', 'fragments': [], 'unresolved': [], 'groups': [],
            'remaining_connections': [], 'scan': {'status': 'NOT_RUN'}}
        inv.save()
        for provision in bundle['provisions']:
            anchor = provision['anchor']
            pair, reason = resolve(inv.s, anchor)
            if reason:
                plan['unresolved'].append({'anchor': deepcopy(anchor), 'reason': reason})
                if reason == 'SOURCE_VERSION_CHANGED':
                    plan['status'] = 'NEEDS_REVIEW'
                    break
                continue
            hit, offer = pair
            read_key = digest([inv.p['binding'], anchor])
            prior = state['reads'].get(read_key)
            if prior is None:
                limit = min(MAX_CHARS, inv.s.profile['max_context_chars'] // 3)
                if len(state['reads']) >= MAX_READS or state['reserved_chars'] + offer['chars'] > limit:
                    plan['unresolved'].append({'anchor': deepcopy(anchor), 'reason': 'ONTOLOGY_CONTEXT_BOUND'})
                    continue
                state['reserved_chars'] += offer['chars']
                prior = state['reads'][read_key] = {'status': 'RESERVED'}
                inv.save()
                try:
                    material = ur.read(inv.s, hit, offer, action_state=inv.p['read_state'])
                    if not material['complete']:
                        raise ContractError('ontology own-body acquisition incomplete')
                    inv.add_reads([{**material, 'hit': hit}])
                    gid = lc.token(inv.s, 'B', [hit['source_id'], lc.parent_offer(inv.s, hit)['id']])
                    # Ancestors are explicit, separately bound provisions. Do not
                    # create an implicit ancestor scope grant from this read.
                    inv.register_read(inv.p['groups'][gid], material,
                        reason='승인 온톨로지 묶음의 범위 내 원문 확보; 적용·채택 판단 전', acquire_context=False)
                    prior.update(status='ACQUIRED', key=read_key, anchor=deepcopy(anchor),
                        group_id=gid, source_id=hit['source_id'], block_ids=list(offer['block_ids']),
                        evidence_ids=list(material['evidence_ids']))
                    if compiler.content_hash(material['text']) != anchor['content_sha256']:
                        prior['status'] = 'SOURCE_CONTENT_CHANGED'
                    inv.save()
                except (BudgetExhausted, TimeoutError, ToolExecutionError, sqlite3.OperationalError) as error:
                    from .request_repair import recoverable_tool_failure
                    from .definition_context import record_failure
                    if not isinstance(error, BudgetExhausted) and recoverable_tool_failure(error) is None:
                        raise
                    prior.update(status='FAILED', reason=type(error).__name__)
                    plan['unresolved'].append({'anchor': deepcopy(anchor), 'reason': type(error).__name__})
                    recovery = record_failure(inv, error, stage='READ', identity=hit, offer=offer,
                        group_id=None, anchor_key=key, origin='ONTOLOGY_CONTEXT', revision=VERSION)
                    inv.save()
                    if recovery == 'STOP':
                        _interrupted(inv, plan)
                        raise
                    continue
            if prior['status'] == 'SOURCE_CONTENT_CHANGED':
                plan['status'] = 'NEEDS_REVIEW'
                plan['unresolved'].append({'anchor': deepcopy(anchor), 'reason': 'SOURCE_CONTENT_CHANGED'})
                break
            if prior['status'] != 'ACQUIRED':
                plan['unresolved'].append({'anchor': deepcopy(anchor), 'reason': prior['status']})
                continue
            plan['fragments'].append(deepcopy(prior))
            plan['groups'].append(prior['group_id'])
        plan['groups'] = list(dict.fromkeys(plan['groups']))
        if plan['status'] != 'NEEDS_REVIEW':
            try:
                plan['remaining_connections'], plan['scan'] = _remaining(inv, bundle, plan['fragments'], primary_records)
            except (BudgetExhausted, TimeoutError, sqlite3.OperationalError) as error:
                from .request_repair import recoverable_tool_failure
                if not isinstance(error, BudgetExhausted) and recoverable_tool_failure(error) is None:
                    raise
                plan['scan'] = {'status': 'UNAVAILABLE', 'reason': type(error).__name__, 'absence_proven': False}
            plan['status'] = 'PARTIAL' if plan['unresolved'] else 'ACQUIRED'
        inv.s.repo.event('ONTOLOGY_BUNDLE_ACQUISITION', {'plan_id': key, 'bundle_id': bundle['bundle_id'],
            'status': plan['status'], 'snapshot_sha256': settings['snapshot_sha256'],
            'groups': plan['groups'], 'unresolved': plan['unresolved'], 'recursion': False,
            'automatic_adoption': False, 'scope_extended': False})
        added.extend(plan['groups'])
        inv.save()
    return list(dict.fromkeys(added))


def _delivery_pages(inv, group, block_ids, existing):
    """Reuse visible originals or project real page spans, never whole siblings.

    A projection is a valid existing evidence-page shape, but is not delivery of
    a whole canonical page. Navigation must not advance its page cursor for an
    ontology_projection; the ordinary exact-span ledger still acknowledges it.
    """
    wanted = set(map(str, block_ids)); output = []; refs = []
    for number in range(len(group['page_plan'])):
        page = inv.render_page(group, number)
        spans = [deepcopy(span) for span in page['spans'] if str(span['block_id']) in wanted]
        if not spans:
            continue
        visible = next((row for row in existing if row['id'] == page['id']), None)
        if visible is not None:
            inventory.check_presented_page(inv.s, inv.p, visible)
            if visible['spans'] != page['spans']:
                raise ContractError('ontology visible delivery page changed')
            refs.append(page['id'])
            continue
        # Always mark newly added pages as projections: even a page consisting
        # solely of this provision may follow an unrelated, unshown page.
        page = {**page, 'spans': spans, 'text': '\n'.join(span['text'] for span in spans),
                'ontology_projection': True, 'group_complete': False}
        page['id'] = lc.token(inv.s, 'E', [group['id'], 'ontology-own-blocks', number, spans])
        page['selected_scope_complete'] = inventory.presentation_receipt(inv.s, group,
            inv.p['selected'][group['id']], [page], state=inv.p)['presented_complete']
        inventory.check_presented_page(inv.s, inv.p, page)
        visible = next((row for row in [*existing, *output] if row['id'] == page['id']), None)
        if visible is None:
            output.append(page)
        elif visible != page:
            raise ContractError('ontology projected delivery identity changed')
        refs.append(page['id'])
    return output, refs


def attach(inv, data):
    # Restored views may carry a previous rendering. Its metadata is not a new
    # budget charge or proof that the current snapshot still compiles.
    data.pop('ontology_bundles', None)
    data.pop('ontology_context_limits', None)
    settings = config(inv)
    if settings['mode'] == 'A0' or not inv.p.get('ontology_context'):
        return
    state = inv.p['ontology_context']
    if state['snapshot_sha256'] != settings['snapshot_sha256']:
        raise ContractError('ontology view snapshot changed')
    bundles = {b['bundle_id']: b for b in settings['snapshot']['bundles']}
    cards = []; worst_card_chars = 0; omitted = []
    all_ids = [plan['bundle_id'] for plan in state['plans'].values()]
    limit_reason = 'ONTOLOGY_CONTEXT_BOUND'
    # Reserve the full omission indicator before accepting any card. Receipt
    # storage retains exact plans; nothing is silently truncated to fit input.
    reserve = len(json.dumps({'ontology_context_limits': {'reason': limit_reason,
        'omitted_bundles': all_ids}}, ensure_ascii=False))
    context_limit = inv.s.profile['max_context_chars']
    review_mode = inv.policy.get('execution_review', False)
    evidence_by_id = {}
    for plan in sorted(state['plans'].values(), key=lambda row: row['bundle_id']):
        expected_id = digest([inv.p['binding'], settings['snapshot_sha256'], plan['bundle_id']])
        if plan['id'] != expected_id or plan['bundle_id'] not in bundles:
            raise ContractError('ontology plan binding changed')
        _interrupted(inv, plan)
        if plan['status'] == 'NEEDS_REVIEW':
            card = {'plan_id': plan['id'], 'bundle_id': plan['bundle_id'],
                'status': 'NEEDS_REVIEW', 'text': '온톨로지 확인 필요: 원문 판본 또는 내용이 달라 묶음을 사용하지 않습니다.'}
            card_chars = len(json.dumps(card, ensure_ascii=False))
            if not review_mode and len(json.dumps(data, ensure_ascii=False)) + worst_card_chars + card_chars + reserve > context_limit:
                omitted.append(plan['bundle_id'])
            else:
                cards.append(card); worst_card_chars += card_chars
            continue
        staged = {**data, 'sources': list(data['sources']), 'basis': list(data['basis'])}
        fragments = []
        delivery_bindings = []
        resolved = []
        for row in plan['fragments']:
            pair, reason = resolve(inv.s, row['anchor'])
            if reason:
                raise ContractError('acquired ontology fragment binding changed: ' + reason)
            hit, offer = pair
            if (row['source_id'] != hit['source_id']
                    or set(map(str, row['block_ids'])) != set(map(str, offer['block_ids']))):
                raise ContractError('stored ontology own-block scope changed')
            resolved.append((row, hit, offer))
        # Preflight every current authorization and exact extent before any
        # batch read; denied anchors must never become a journal read request.
        missing = [eid for row, _, _ in resolved for eid in row['evidence_ids']
                   if eid not in evidence_by_id]
        if missing:
            evidence_by_id.update(ontology_io.evidence(inv.s.repo, missing))
        for row, hit, offer in resolved:
            evidence = [evidence_by_id[eid] for eid in row['evidence_ids']]
            for item in evidence:
                inv.s.source.verify(item)
                if (item['source_id'] != hit['source_id'] or item['document_id'] != hit['document_id']
                        or any(str(p['block_id']) not in set(map(str, offer['block_ids'])) for p in item['spans'])):
                    raise ContractError('stored ontology evidence escaped own-block scope')
            spans = [p for item in evidence for p in item['spans']]
            if not inventory.covers(inventory.expected(inv.s, hit['document_id'], offer['block_ids']), spans):
                raise ContractError('stored ontology evidence incomplete')
            text = ur.reassemble(evidence)
            if compiler.content_hash(text) != row['anchor']['content_sha256']:
                raise ContractError('stored ontology fragment content changed')
            gid = row['group_id']; group = inv.p['groups'][gid]
            if group['source_id'] != hit['source_id']:
                raise ContractError('ontology delivery group source changed')
            pages, refs = _delivery_pages(inv, group, row['block_ids'], staged['sources'])
            for page in pages:
                staged['sources'].append(page)
                staged['basis'].append({k: page[k] for k in ('id', 'branch_id', 'source_id', 'page', 'total_pages')})
            if not refs:
                raise ContractError('ontology source has no delivery page')
            fragments.append({'anchor': row['anchor'], 'text': text, 'evidence_refs': refs})
            if review_mode:
                # Stored compiler objects keep the v0 contract. Exact delivery
                # coordinates belong to this request's projection, not to the
                # approved knowledge or to a claimed model-review result.
                delivery_bindings.append({'anchor_key': compiler.anchor_key(row['anchor']),
                    'source_id': hit['source_id'], 'document_id': hit['document_id'],
                    'spans': [{'block_id': str(p['block_id']), 'start_cp': p['start_cp'],
                               'end_cp': p['end_cp'], 'text_hash': digest(p['text'])}
                              for p in spans]})
        card = compiler.compile_bundle(bundles[plan['bundle_id']], fragments,
            unresolved=plan['unresolved'], remaining_connections=plan['remaining_connections'], mode=settings['mode'])
        card = {**card, 'plan_id': plan['id'], 'connection_scan': deepcopy(plan['scan'])}
        card_chars = 0
        if not review_mode:
            alternate = compiler.compile_bundle(bundles[plan['bundle_id']], fragments,
                unresolved=plan['unresolved'], remaining_connections=plan['remaining_connections'],
                mode='A1' if settings['mode'] == 'A2' else 'A2')
            alternate = {**alternate, 'plan_id': plan['id'], 'connection_scan': plan['scan']}
            card_chars = max(len(json.dumps(row, ensure_ascii=False)) for row in (card, alternate))
        if not review_mode and len(json.dumps(staged, ensure_ascii=False)) + worst_card_chars + card_chars + reserve > context_limit:
            omitted.append(plan['bundle_id'])
            continue
        data['sources'], data['basis'] = staged['sources'], staged['basis']
        if review_mode:
            card['delivery_bindings'] = delivery_bindings
        cards.append(card); worst_card_chars += card_chars
    data['ontology_bundles'] = cards
    if omitted:
        data['ontology_context_limits'] = {'reason': limit_reason, 'omitted_bundles': omitted}
