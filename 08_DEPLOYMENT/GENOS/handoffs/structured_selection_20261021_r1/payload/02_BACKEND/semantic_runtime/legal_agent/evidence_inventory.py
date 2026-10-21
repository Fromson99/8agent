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
    for span in page['spans']:
        raw = session.store.source(page['document_id'], span['block_id'])
        if (type(span['start_cp']) is not int or type(span['end_cp']) is not int or
                not 0 <= span['start_cp'] <= span['end_cp'] <= len(raw['text']) or
                raw['text'][span['start_cp']:span['end_cp']] != span['text']):
            raise ContractError('delivered source range changed')



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
    saved=state.get('basis_history',{}).get(page['id'],{})
    fields=('id','branch_id','source_id','page','total_pages','scope_id','spans')
    if not saved.get('accepted') or any(saved.get(k)!=page.get(k) for k in fields):
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


def expected(session, did, blocks):
    out = []
    for bid in blocks:
        raw = session.store.source(did, bid)
        out.append({'block_id': str(bid), 'start_cp': 0, 'end_cp': len(raw['text']),
                    'block_hash': text_hash(raw['text'])})
    return out


def scope_path(session, hit, offer):
    from .unit_reading import unit_label
    scoped = {**hit, 'unit_id': offer['unit_id']}
    return hit['document_name'] + ' ' + unit_label(session, scoped)


def receipt(session, group, record, basis):
    want = expected(session, record['document_id'], record['offer']['block_ids'])
    acquired = [p for e in record['evidence'] for p in e['spans']]
    delivered = [p for b in basis if b.get('branch_id') == group['id']
                 and b.get('scope_id') == digest(record['offer']) for p in b.get('spans', [])]
    own = set(map(str, record['offer']['block_ids']))
    return {'contract': CONTRACT, 'scope_id': digest(record['offer']),
            'source_id': record['source_id'], 'document_id': record['document_id'],
            'generation_id': session.context.query['generation_id'],
            'scope': deepcopy(record['offer']), 'path': scope_path(session, group['hit'], record['offer']),
            'expected_spans': want, 'acquired_spans': acquired,
            'delivered_spans': [p for p in delivered if str(p['block_id']) in own],
            'ancestor_context_spans': [p for p in delivered if str(p['block_id']) not in own],
            'acquired_complete': covers(want, acquired),
            'delivered_complete': covers(want, delivered),
            'pages_total': len(group['page_plan']),
            'delivered_pages_count': len({b['page'] for b in basis if b.get('branch_id') == group['id']
                                         and b.get('scope_id') == digest(record['offer'])}),
            'article_delivered_complete': covers(expected(session, record['document_id'],
                [b['block_id'] for b in session.tools.sources[record['source_id']]['blocks']]), delivered),
            'semantic_quality_certified': False}


def inventory(session, state):
    basis = list(state['basis_history'].values()) + list(state.get('delivery_history', {}).values()); rows = []
    for gid, record in state['selected'].items():
        group = state['groups'][gid]
        value = receipt(session, group, record, basis)
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
    explicit_sources=set(sources)
    for ref in dict.fromkeys(context_refs):
        page=state['basis_history'].get(ref)
        if not page or not page.get('accepted') or not page.get('spans'):
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


def acquired_originals_for(session, state, limit):
    """Prepare acquired originals with governing context; never invent delivery."""
    from .decision_projection import original_groups
    sources={};gathered=defaultdict(list);evidence={};used=0;omitted=[]
    for gid in original_groups(state):
        group=state['groups'][gid];record=state['selected'][gid]
        if group['status']=='EXCLUDED' or not record['complete']:continue
        sid=record['source_id'];did=record['document_id']
        if did not in session.scope:raise ContractError('acquired original inaccessible')
        records=[record]+[r for r in state.get('contexts',{}).values() if r['source_id']==sid]
        bundle={}
        for r in records:
            if not r['complete'] or r['document_id']!=did:raise ContractError('governing context binding changed')
            for e in r['evidence']:
                if e['source_id']!=sid or e['document_id']!=did:
                    raise ContractError('acquired evidence record identity changed')
                session.source.verify(e)
                if e['evidence_id'] not in evidence:bundle[e['evidence_id']]=e
        size=sum(len(p['text']) for e in bundle.values() for p in e['spans'])
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
               'article_delivered_complete': row['receipt']['article_delivered_complete']}
            for row in inventory(session, state)]
