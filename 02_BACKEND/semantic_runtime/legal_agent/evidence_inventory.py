"""Exact acquired, presented and adopted ranges over the existing read journal.

Offsets are Unicode codepoints. Ancestor introductions never prove subtree
coverage. Model assessments describe semantic coverage; receipts prove delivery.
"""
from collections import defaultdict
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError
from .repository import text_hash

CONTRACT = 'investigation-evidence-v2'


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
    basis = list(state['basis_history'].values()); rows = []
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
    if page['document_id'] not in session.scope:
        raise ContractError('presentation escaped current authorization')
    group = state['groups'][page['branch_id']]
    for span in page['spans']:
        raw = session.store.source(page['document_id'], span['block_id'])
        if raw['text'][span['start_cp']:span['end_cp']] != span['text']:
            raise ContractError('delivered source range changed')
    state['basis_history'][page['id']] = {
        k: deepcopy(page[k]) for k in ('id', 'branch_id', 'source_id', 'page', 'total_pages', 'spans')}
    state['basis_history'][page['id']].update(
        scope_id=page.get('scope_id', digest(state['selected'][group['id']]['offer'])),
        presentation_id=presentation_id, accepted=True)


def originals_for(session, state):
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
    return _pack(session, state, sources, gathered)


def delivered_originals_for(session, state):
    """Bounded fallback: every page actually presented to the model, unadopted.

    Used only when navigation stopped without an adoption decision. Explicitly
    deferred or excluded branches stay out; the assessment still cites exact
    delivered spans."""
    sources = {}; gathered = defaultdict(list)
    for gid, group in state['groups'].items():
        if group['status'] in ('EXCLUDED', 'DEFERRED') or gid not in state['selected']: continue
        pages = [b for b in state['basis_history'].values()
                 if b.get('branch_id') == gid and b.get('accepted') and b.get('spans')]
        if not pages: continue
        for b in pages:
            gathered[group['source_id']].extend(b['spans'])
        sources[group['source_id']] = state['selected'][gid]
    return _pack(session, state, sources, gathered)


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
