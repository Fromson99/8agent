"""Exact acquired, presented and adopted ranges over the existing read journal.

Offsets are Unicode codepoints. Ancestor introductions never prove subtree
coverage. Model assessments describe semantic coverage; receipts prove delivery.
"""
from collections import defaultdict
from copy import deepcopy
import json
from ..contracts import digest
from .errors import ContractError
from .repository import text_hash

CONTRACT = 'investigation-evidence-v2'
DELIVERY = 'confirmed-navigation-input-v1'


def record_delivery(repo, view, attempt_id):
    """Called only after a timely, complete response from the pinned model.

    This proves delivery of input, never acceptance of the model's output.
    Original bytes already live in model_view; the event stores only binding.
    """
    if not str(view.get('source_stage', '')).startswith('source-law-navigation-') or not view.get('sources'):
        return
    repo.event('NAVIGATION_INPUT_DELIVERED', {'contract': DELIVERY,
        'attempt_id': attempt_id, 'view_id': view['view_id'], 'view_sha256': digest(view),
        'presentation_id': view['presentation_id'], 'source_stage': view['source_stage'],
        'state_version': view.get('state_version'), 'sources_sha256': digest(view['sources'])})


def check_page(session, state, page, *, current_scope=True):
    if page['document_id'] not in session.scope:
        raise ContractError('presentation escaped current authorization')
    record = state['selected'].get(page['branch_id'])
    if (not record or record['source_id'] != page['source_id'] or
            record['document_id'] != page['document_id'] or
            (current_scope and page.get('scope_id', digest(record['offer'])) != digest(record['offer']))):
        raise ContractError('delivered source binding changed')
    texts = _block_texts(session, page['document_id'], [span['block_id'] for span in page['spans']])
    for span in page['spans']:
        raw = {'text': texts[str(span['block_id'])]}
        if (type(span['start_cp']) is not int or type(span['end_cp']) is not int or
                not 0 <= span['start_cp'] <= span['end_cp'] <= len(raw['text']) or
                raw['text'][span['start_cp']:span['end_cp']] != span['text']):
            raise ContractError('delivered source range changed')




def confirmed_pages(state):
    """Confirmed input and accepted decisions share a delivery ledger, not adoption."""
    pages = {}
    for page in state.get('delivery_history', {}).values():
        if page.get('delivery_contract') != DELIVERY or not page.get('spans'): continue
        prior = pages.get(page['id'])
        if prior and any(prior.get(k) != page.get(k) for k in ('branch_id','source_id','scope_id','spans')):
            raise ContractError('confirmed delivery identity changed')
        pages[page['id']] = page
    for page in state.get('basis_history', {}).values():
        if not page.get('accepted') or not page.get('spans'): continue
        prior = pages.get(page['id'])
        if prior and any(prior.get(k) != page.get(k) for k in ('branch_id','source_id','scope_id','spans')):
            raise ContractError('accepted and delivered source identity disagree')
        pages[page['id']] = page
    return pages


def check_presented_page(session, state, page):
    """Historical scope is valid only when identical to an accepted delivery."""
    record=state['selected'].get(page['branch_id'])
    if not record:
        check_page(session,state,page)
        return
    current=digest(record['offer'])
    if page.get('scope_id',current)==current:
        check_page(session,state,page)
        return
    saved=confirmed_pages(state).get(page['id'],{})
    fields=('id','branch_id','source_id','page','total_pages','scope_id','spans')
    if not saved or any(saved.get(k)!=page.get(k) for k in fields):
        raise ContractError('historical presentation lacks identical accepted delivery')
    # Do not trust a client historical flag. Receipt equality permits the old
    # scope; current ACL, source identity and original bytes must still match.
    check_page(session,state,page,current_scope=False)


def reconcile_delivery(session, state, data, phase):
    """Idempotently recover input receipts even when JSON/decision validation failed."""
    if not data.get('sources'): return False
    changed = False
    for row in session.repo.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED'"):
        event = json.loads(row['payload_json'])
        if event.get('presentation_id') != data.get('presentation_id') or event.get('source_stage') not in (phase, phase+'-repair'):
            continue
        if digest(event) != row['payload_hash'] or event.get('contract') != DELIVERY:
            raise ContractError('delivery receipt hash mismatch')
        view_row = session.repo.db.execute('SELECT body_json,body_hash FROM model_view WHERE view_id=?', (event['view_id'],)).fetchone()
        attempt = session.repo.db.execute('SELECT view_id,status FROM model_attempt WHERE attempt_id=?', (event['attempt_id'],)).fetchone()
        if not view_row or not attempt or attempt['status'] != 'SUCCEEDED' or attempt['view_id'] != event['view_id']:
            raise ContractError('delivery receipt lacks successful bound attempt')
        view = json.loads(view_row['body_json'])
        if (digest(view) != view_row['body_hash'] or digest(view) != event['view_sha256'] or
                view.get('presentation_id') != event['presentation_id'] or view.get('source_stage') != event['source_stage'] or
                view.get('state_version') != state.get('state_version') or view.get('state_version') != event.get('state_version') or
                digest(view.get('sources')) != event['sources_sha256'] or digest(data['sources']) != event['sources_sha256']):
            raise ContractError('delivery receipt view/state/source binding mismatch')
        # Validate the whole presentation before changing any state.
        for page in data['sources']: check_presented_page(session, state, page)
        receipts = state.setdefault('delivery_history', {})
        for page in data['sources']:
            key = event['attempt_id']+':'+page['id']
            if key in receipts: continue
            receipts[key] = {**{k:deepcopy(v) for k,v in page.items() if k != 'text'}, 'delivery_contract': DELIVERY,
                'presentation_id': data['presentation_id'], 'view_id': event['view_id'],
                'attempt_id': event['attempt_id'], 'accepted': False}
            changed = True
    return changed


def intervals(spans):
    result = defaultdict(list)
    for span in spans:
        lo, hi = span['start_cp'], span['end_cp']
        if type(lo) is not int or type(hi) is not int or lo < 0 or hi < lo:
            raise ContractError('invalid codepoint range')
        result[str(span['block_id'])].append((lo, hi))
    merged = {}
    for bid, values in result.items():
        rows = []
        for lo, hi in sorted(values):
            if rows and lo <= rows[-1][1]: rows[-1][1] = max(rows[-1][1], hi)
            else: rows.append([lo, hi])
        merged[bid] = rows
    return merged


def covers(expected, actual):
    if expected is None: return None
    have = intervals(actual)
    return all(any(a <= p['start_cp'] and z >= p['end_cp']
                   for a, z in have.get(str(p['block_id']), [])) for p in expected)


def _block_texts(session, did, bids):
    """Block text by ID; one bounded batch on stores that have it (Oracle: 3 SQL per 100 blocks)."""
    ids = [str(b) for b in bids]
    batch = getattr(session.store, 'sources', None)
    if callable(batch) and len(set(ids)) > 1:
        return {bid: raw['text'] for bid, raw in zip(ids, batch(did, ids))}
    return {bid: session.store.source(did, bid)['text'] for bid in dict.fromkeys(ids)}


def expected(session, did, blocks):
    out = []
    texts = _block_texts(session, did, blocks)
    for bid in blocks:
        raw = {'text': texts[str(bid)]}
        out.append({'block_id': str(bid), 'start_cp': 0, 'end_cp': len(raw['text']),
                    'block_hash': text_hash(raw['text'])})
    return out


def scope_path(session, hit, offer):
    from .unit_reading import unit_label
    scoped = {**hit, 'unit_id': offer['unit_id']}
    return hit['document_name'] + ' ' + unit_label(session, scoped)


def acquired_records(state, *, group_ids=None, include_context=True):
    """Current and historical scopes, bound by their original branch receipt.

    A historical record is not inferred from a matching title/source. The saved
    key must bind the exact branch and offer; source verification remains with
    each reader of the returned evidence, as for the current selected records.
    """
    selected = state.get('selected', {})
    wanted = set(selected if group_ids is None else group_ids)
    records = {gid: record for gid, record in selected.items() if gid in wanted}
    for key, record in state.get('material_history', {}).items():
        branches = [gid for gid in selected if digest([gid, record['offer']]) == key]
        if len(branches) != 1:
            raise ContractError('historical material lacks its exact branch/offer binding')
        gid = branches[0]; current = selected[gid]
        if any(record.get(field) != current.get(field)
               for field in ('source_id', 'document_id', 'article_unit_id')):
            raise ContractError('historical material source binding changed')
        if gid in wanted and record != current:
            records['HISTORY:'+gid+':'+key] = record
    if include_context:
        sources = {r['source_id']: r['document_id'] for r in records.values()}
        for key, record in state.get('contexts', {}).items():
            if record['source_id'] not in sources: continue
            if record['document_id'] != sources[record['source_id']]:
                raise ContractError('governing context source binding changed')
            records[key] = record
    return records


def _checked_source_pages(session, record, pages, *, group_id, state=None):
    """Revalidate same-source pages against the current ACL and original bytes."""
    checked = []
    for page in pages:
        if page.get('source_id') != record['source_id']: continue
        if state is None and page.get('branch_id') != group_id: continue
        bound = {**page, 'document_id': page.get('document_id', record['document_id'])}
        check_page(session, state if state is not None else {'selected': {group_id: record}},
                   bound, current_scope=False)
        checked.append(page)
    return checked


def _scope_ranges(want, actual, *, missing=False):
    """Compact codepoint coverage, without duplicating original text."""
    have = intervals(actual); out = []
    for part in want:
        lo, hi = part['start_cp'], part['end_cp']; cursor = lo
        for start, end in have.get(str(part['block_id']), []):
            start, end = max(lo, start), min(hi, end)
            if start >= end: continue
            if missing and cursor < start:
                out.append({'block_id': str(part['block_id']), 'start_cp': cursor, 'end_cp': start})
            if not missing:
                out.append({'block_id': str(part['block_id']), 'start_cp': start, 'end_cp': end})
            cursor = max(cursor, end)
        if missing and cursor < hi:
            out.append({'block_id': str(part['block_id']), 'start_cp': cursor, 'end_cp': hi})
    return out


def presentation_receipt(session, group, record, pages, *, state=None):
    """Current input coverage is separate from historical confirmed delivery."""
    want = expected(session, record['document_id'], record['offer']['block_ids'])
    actual = [span for page in _checked_source_pages(session, record, pages, group_id=group['id'], state=state)
              for span in page.get('spans', [])]
    shown = _scope_ranges(want, actual)
    return {'scope_id': digest(record['offer']), 'currently_presented': bool(shown),
            'presented_any': bool(shown), 'presented_complete': covers(want, actual),
            'presented_spans': shown, 'missing_spans': _scope_ranges(want, actual, missing=True)}


def receipt(session, group, record, basis, *, records=None, state=None):
    want = expected(session, record['document_id'], record['offer']['block_ids'])
    records = list(records) if records is not None else [record]
    acquired = []
    for material in records:
        if material['source_id'] != record['source_id'] or material['document_id'] != record['document_id']:
            raise ContractError('acquired material source binding changed')
        for evidence in material['evidence']:
            if evidence['source_id'] != record['source_id'] or evidence['document_id'] != record['document_id']:
                raise ContractError('acquired evidence record identity changed')
            session.source.verify(evidence)
            acquired.extend(evidence['spans'])
    confirmed = [b for b in basis if b.get('accepted') or b.get('delivery_contract') == DELIVERY]
    pages = _checked_source_pages(session, record, confirmed, group_id=group['id'], state=state)
    delivered = [p for b in pages for p in b.get('spans', [])]
    scopes = {}
    for material in records:
        offer = material['offer']; scope_id = digest(offer)
        scope_want = expected(session, record['document_id'], offer['block_ids'])
        scopes[scope_id] = {'scope_id': scope_id, 'path': scope_path(session, group['hit'], offer),
            'unit_id': offer['unit_id'], 'extent': offer.get('extent'),
            'block_ids': list(map(str, offer['block_ids'])),
            'acquired_complete': covers(scope_want, acquired), 'delivered_complete': covers(scope_want, delivered)}
    own = set(map(str, record['offer']['block_ids']))
    return {'contract': CONTRACT, 'scope_id': digest(record['offer']),
            'source_id': record['source_id'], 'document_id': record['document_id'],
            'generation_id': session.context.query['generation_id'],
            'available_scopes': list(scopes.values()),
            'scope': deepcopy(record['offer']), 'path': scope_path(session, group['hit'], record['offer']),
            'expected_spans': want, 'acquired_spans': acquired,
            'delivered_spans': [p for p in delivered if str(p['block_id']) in own],
            'ancestor_context_spans': [p for p in delivered if str(p['block_id']) not in own],
            'acquired_complete': covers(want, acquired),
            'delivered_complete': covers(want, delivered),
            'pages_total': len(group['page_plan']),
            'delivered_pages_count': len({b['id'] for b in pages if b.get('branch_id') == group['id']}),
            'article_delivered_complete': covers(expected(session, record['document_id'],
                [b['block_id'] for b in session.tools.sources[record['source_id']]['blocks']]), delivered),
            'semantic_quality_certified': False}


def inventory(session, state):
    basis = list(confirmed_pages(state).values()); rows = []
    for gid, record in state['selected'].items():
        group = state['groups'][gid]
        records = acquired_records(state, group_ids=[gid])
        value = receipt(session, group, record, basis, records=records.values(), state=state)
        rows.append({'material_id': gid, 'source_id': record['source_id'],
            'document_id': record['document_id'], 'path': value['path'],
            'scope_id': value['scope_id'], 'availability': 'DELIVERED' if value['delivered_complete'] else
                'PARTIALLY_DELIVERED' if value['delivered_spans'] else 'ACQUIRED',
            'status': group['status'], 'reason': group['reason'],
            'decisions': deepcopy(group.get('issue_decisions', {})), 'receipt': value})
    return rows


def acknowledge(session, state, page, presentation_id):
    check_presented_page(session, state, page)
    group = state['groups'][page['branch_id']]
    state['basis_history'][page['id']] = {
        k: deepcopy(page[k]) for k in ('id', 'branch_id', 'source_id', 'page', 'total_pages', 'spans')}
    state['basis_history'][page['id']].update(
        scope_id=page.get('scope_id', digest(state['selected'][group['id']]['offer'])),
        presentation_id=presentation_id, accepted=True)


def originals_for(session, state, selected_refs=(), *, context_refs=()):
    """Only explicitly adopted page spans enter the assessment proof pack."""
    sources = {}; gathered = defaultdict(list)
    for gid, group in state['groups'].items():
        if group['status'] != 'ACTIVE' or gid not in state['selected']: continue
        decisions = group.get('issue_decisions', {})
        refs = {r for d in decisions.values() if d['status'] in ('ADOPT', 'KEEP')
                for r in d.get('basis_refs', [])}
        for ref in refs:
            b = state['basis_history'].get(ref)
            if not b or not b.get('accepted') or b.get('branch_id') != gid:
                raise ContractError('adopted basis lacks an accepted delivery receipt')
            gathered[group['source_id']].extend(b.get('spans', []))
        record = state['selected'][gid]
        sources[group['source_id']] = record
    for ref in selected_refs:
        page=state['basis_history'].get(ref)
        if not page or not page.get('accepted') or not page.get('spans'):
            raise ContractError('completion original lacks an accepted delivery receipt')
        gid=page['branch_id'];group=state['groups'][gid]
        if gid not in state['selected'] or group['status'] in ('DEFERRED','EXCLUDED'):
            raise ContractError('completion selected a deferred or missing original')
        gathered[group['source_id']].extend(page['spans'])
        sources[group['source_id']]=state['selected'][gid]
    explicit_sources=set(gathered)
    confirmed=confirmed_pages(state)
    for ref in dict.fromkeys(context_refs):
        page=confirmed.get(ref)
        if not page or not page.get('spans'):
            raise ContractError('context original lacks an accepted delivery receipt')
        gid=page['branch_id'];group=state['groups'][gid]
        if gid not in state['selected'] or group['status']=='EXCLUDED':
            raise ContractError('context selected an excluded or missing original')
        record=state['selected'][gid]
        check_page(session,state,{**page,'document_id':record['document_id']},current_scope=False)
        gathered[group['source_id']].extend(page['spans']);sources[group['source_id']]=record
    result=_pack(session,state,sources,gathered)
    for original in result:
        original['delivered_context_only']=original['source_id'] not in explicit_sources
    return result


def delivered_originals_for(session, state, *, limit=None):
    """Bounded fallback: every page actually presented to the model, unadopted.

    Used only when navigation stopped without an adoption decision. Explicitly
    deferred or excluded branches stay out; the assessment still cites exact
    delivered spans. An optional character limit keeps each source's delivered
    context together instead of dropping conditions from a partial bundle."""
    sources = {}; gathered = defaultdict(list); used = 0
    for gid, group in state['groups'].items():
        if group['status'] in ('EXCLUDED', 'DEFERRED') or gid not in state['selected']: continue
        pages = [b for b in state['basis_history'].values()
                 if b.get('branch_id') == gid and b.get('accepted') and b.get('spans')]
        delivered = [b for b in state.get('delivery_history', {}).values()
                     if b.get('branch_id') == gid and b.get('delivery_contract') == DELIVERY and b.get('spans')]
        for page in delivered: check_page(session, state, page, current_scope=False)
        pages = list({b['id']: b for b in delivered + pages}.values())
        if not pages: continue
        spans = [span for page in pages for span in page['spans']]
        size = sum(hi-lo for ranges in intervals(spans).values() for lo,hi in ranges)
        if limit is not None and used+size > limit: continue
        used += size
        for b in pages:
            gathered[group['source_id']].extend(b['spans'])
        sources[group['source_id']] = state['selected'][gid]
    return _pack(session, state, sources, gathered)



def merge_delivered_originals(session, state, originals, limit):
    """Merge confirmed delivery into assessment context, without adopting it.

    Mandatory originals survive the limit. Additional source bundles are kept
    whole; omission is explicit and never reclassified as unread or absent.
    """
    current = {o['source_id']: deepcopy(o) for o in originals}
    used = sum(sum(hi-lo for ranges in intervals(o['adopted_spans']).values()
                   for lo,hi in ranges) for o in current.values())
    omitted = []; added = []
    for extra in reversed(delivered_originals_for(session, state)):
        sid = extra['source_id']; previous = current.get(sid)
        spans = (previous['adopted_spans'] if previous else []) + extra['adopted_spans']
        unique = list({digest(p): p for p in spans}.values())
        size = sum(hi-lo for ranges in intervals(unique).values() for lo,hi in ranges)
        old_size = sum(hi-lo for ranges in intervals(previous['adopted_spans']).values()
                       for lo,hi in ranges) if previous else 0
        if used + size - old_size > limit:
            omitted.append(sid)
            continue
        record = next(r for r in state['selected'].values() if r['source_id'] == sid)
        merged = _pack(session, state, {sid:record}, {sid:unique})[0]
        merged['delivered_context_only'] = previous.get('delivered_context_only', False) if previous else True
        current[sid] = merged; used += size-old_size
        if size > old_size: added.append(sid)
    return list(current.values()), {'confirmed_delivery_merged': added,
        'omitted_delivered_source_ids': omitted, 'character_limit': limit,
        'omission_reason': 'CONTEXT_LIMIT' if omitted else None,
        'automatic_adoption': False, 'source_absence_proven': False}


def acquired_originals_for(session, state, limit, *, include_deferred=True):
    """Prepare acquired originals with governing context; never invent delivery."""
    from .decision_projection import original_groups
    sources={};gathered=defaultdict(list);evidence={};used=0;omitted=[]
    for gid in original_groups(state):
        group=state['groups'][gid];record=state['selected'][gid]
        if group['status']=='EXCLUDED' or (not include_deferred and group['status']=='DEFERRED') or not record['complete']:continue
        sid=record['source_id'];did=record['document_id']
        if did not in session.scope:raise ContractError('acquired original inaccessible')
        records=acquired_records(state, group_ids=[gid]).values()
        bundle={}
        for r in records:
            if not r['complete'] or r['document_id']!=did:raise ContractError('governing context binding changed')
            for e in r['evidence']:
                if e['source_id']!=sid or e['document_id']!=did:
                    raise ContractError('acquired evidence record identity changed')
                session.source.verify(e)
                if e['evidence_id'] not in evidence:bundle[e['evidence_id']]=e
        before = intervals(gathered.get(sid, []))
        after = intervals(gathered.get(sid, []) + [p for e in bundle.values() for p in e['spans']])
        size = (sum(hi-lo for values in after.values() for lo,hi in values)
                - sum(hi-lo for values in before.values() for lo,hi in values))
        if used+size>limit:
            # Never deliver a subordinate rule while omitting its acquired conditions.
            # Existing paginated investigation remains available for a large bundle.
            omitted.extend(bundle);continue
        used+=size;sources[sid]=record
        for ident,e in bundle.items():
            evidence[ident]=e
            gathered[sid].extend({**p,'evidence_id':ident} for p in e['spans'])
    originals=_pack(session,state,sources,gathered)
    for source in originals:source['delivered_context_only']=True
    return originals,list(evidence.values()),list(dict.fromkeys(omitted))


def _pack(session, state, sources, gathered):
    out = []
    for sid, spans in gathered.items():
        r = sources[sid]; did = r['document_id']; merged = intervals(spans)
        if did not in session.scope: raise ContractError('adopted original inaccessible')
        parts = [session.store.source(did, bid)['text'][lo:hi]
                 for bid in sorted(merged, key=int) for lo, hi in merged[bid]]
        src = session.tools.sources[sid]
        out.append({'source_id': sid, 'document_id': did, 'unit_id': r['article_unit_id'],
            'document_name': r['document_name'], 'heading': r['heading'], 'text': '\n'.join(parts),
            'evidence_ids': list(dict.fromkeys(p['evidence_id'] for p in spans)),
            'read_scopes': [g['receipt']['scope'] for g in inventory(session, state) if g['source_id'] == sid and g['status'] == 'ACTIVE'],
            'adopted_spans': spans, 'article_complete': covers(expected(session, did,
                [b['block_id'] for b in src['blocks']]), spans)})
    return out


def saved_projection(session, state):
    """Metadata is a reinspection lead, never citation text."""
    return [{k: deepcopy(row[k]) for k in ('material_id', 'source_id', 'document_id', 'path',
             'scope_id', 'availability', 'status', 'reason', 'decisions')}
            | {'acquired_complete': row['receipt']['acquired_complete'],
               'delivered_complete': row['receipt']['delivered_complete'],
               'article_delivered_complete': row['receipt']['article_delivered_complete'],
               'available_scopes': deepcopy(row['receipt']['available_scopes'])}
            for row in inventory(session, state)]
