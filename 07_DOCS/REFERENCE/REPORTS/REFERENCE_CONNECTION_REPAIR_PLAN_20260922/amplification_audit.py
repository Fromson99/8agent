"""Inspect completed graph/journal artifacts only; never execute navigation or models."""
import collections
import gzip
import hashlib
import json
import sqlite3
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
GEN = ROOT / '01_DATA/TERM_RELEASES/adr0523-gemma-bound-fulltext-v1/generation'
db = sqlite3.connect(f'file:{GEN}/navigation/navigation.sqlite?mode=ro', uri=True)
db.execute('PRAGMA query_only=ON')
RUNS = [
    ('0523', 'ADR-0523-gemma-scoped-exploration-probe', 'cm-009'),
    ('0524', 'ADR-0524-gemma-fp8-scoped-retrieval', 'cm-025'),
    ('0524', 'ADR-0524-gemma-fp8-scoped-retrieval', 'cm-040'),
    ('0524', 'ADR-0524-gemma-fp8-scoped-retrieval', 'cm-009'),
]


def gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@lru_cache(None)
def source(sid):
    return json.loads(db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()[0])


def label(sid):
    s = source(sid)
    return s['document_name'] + ' / ' + s['heading']


def physical(extent):
    return (extent['source_id'], tuple(sorted(set(extent['block_ids']))))


results = []
for adr, folder, case in RUNS:
    base = ROOT / '04_EXPERIMENTS/ADR' / folder / 'artifacts/run-001' / case / 'guarded'
    g = gz(base / 'graph.json.gz')
    assert g['checkpoint_hash'] == digest({k: v for k, v in g.items() if k != 'checkpoint_hash'})
    t = gz(base / 'trace.json.gz')
    states = {s['state_id']: s for s in g['states']}
    physical_counts = collections.Counter(physical(s['extent']) for s in states.values())
    expanded_physical = {physical(states[k]['extent']) for k in g['expanded_state_ids']}
    expanded_pending = set(g['expanded_state_ids']) & set(g['pending'])
    by_from = collections.defaultdict(list)
    distinct_edges = set()
    for e in g['edges']:
        by_from[e['from_state']].append(e)
        distinct_edges.add((e['reference_id'], e['direction'], physical(states[e['from_state']]['extent']),
                            tuple(sorted(physical(states[x]['extent']) for x in e['target_states']))))
    self_pending_edges = [e for e in g['edges'] if e['from_state'] in expanded_pending and e['from_state'] in e['target_states']]
    # Shortest paths inside the already-recorded graph, not a replay against the DB.
    distance = {sid: 0 for sid in g['root_states'].values()}
    parent = {}
    queue = collections.deque(distance)
    while queue:
        sid = queue.popleft()
        for e in by_from[sid]:
            for target in e['target_states']:
                if target not in distance:
                    distance[target] = distance[sid] + 1
                    parent[target] = (sid, e)
                    queue.append(target)
    first_source = {}
    for k, d in distance.items():
        sid = states[k]['extent']['source_id']
        first_source[sid] = min(d, first_source.get(sid, d))
    root_stats = []
    for root in g['roots']:
        extent = root['extent']; sid = extent['source_id']
        outgoing = by_from[g['root_states'][root['root_id']]]
        root_stats.append({'root_id': root['root_id'], 'source_id': sid, 'label': label(sid),
                           'blocks': extent['block_ids'], 'article_blocks': len(source(sid)['blocks']),
                           'first_edges': dict(collections.Counter(e['direction'] for e in outgoing)),
                           'first_target_sources': len({states[x]['extent']['source_id'] for e in outgoing for x in e['target_states']})})
    # Explain existing two-step incoming->outgoing paths through a different citation.
    pivots = []
    for root in g['roots']:
        start = g['root_states'][root['root_id']]
        for e in by_from[start]:
            if e['direction'] != 'incoming':
                continue
            for middle in e['target_states']:
                for f in by_from[middle]:
                    if f['direction'] != 'outgoing' or f['reference_id'] == e['reference_id']:
                        continue
                    for end in f['target_states']:
                        if states[end]['extent']['source_id'] == root['extent']['source_id']:
                            continue
                        pivots.append({'sources': [root['extent']['source_id'], states[middle]['extent']['source_id'], states[end]['extent']['source_id']],
                                       'labels': [label(root['extent']['source_id']), label(states[middle]['extent']['source_id']), label(states[end]['extent']['source_id'])],
                                       'state_ids': [start, middle, end], 'references': [e['reference_id'], f['reference_id']],
                                       'locators': [e.get('locator'), f.get('locator')]})
                        break
                    if len(pivots) >= 5:
                        break
                if len(pivots) >= 5:
                    break
            if len(pivots) >= 5:
                break
        if len(pivots) >= 5:
            break
    coverage = collections.defaultdict(set)
    for state in states.values():
        for bid in state['extent']['block_ids']:
            coverage[(state['extent']['source_id'], bid)].update(state['root_ids'])
    originals_chars = sum(len(b['text']) for sid in g['source_ids'] for b in source(sid)['blocks'])
    scoped_chars = sum(len(b['text']) for sid in g['source_ids'] for b in source(sid)['blocks'] if (sid, b['block_id']) in coverage)
    journal = sqlite3.connect(f'file:{base}/journal.sqlite?mode=ro', uri=True)
    journal.execute('PRAGMA query_only=ON')
    views = []
    for vid, phase, raw in journal.execute('SELECT view_id,phase,body_json FROM model_view ORDER BY created_seq'):
        v = json.loads(raw)
        if not v.get('reference_exploration'):
            continue
        views.append({'view_id': vid, 'phase': phase, 'chars': len(raw),
                      'successful_attempts': journal.execute("SELECT COUNT(*) FROM model_attempt WHERE view_id=? AND status='SUCCEEDED'", (vid,)).fetchone()[0],
                      'exploration': v['reference_exploration'],
                      'shown_counts': {k: len(v.get(k, [])) for k in ('exact_evidence', 'relation_menu', 'root_removal_impacts')},
                      'shown_section_chars': {k: len(json.dumps(v.get(k, []), ensure_ascii=False, separators=(',', ':'))) for k in ('exact_evidence', 'relation_menu', 'root_removal_impacts')},
                      'omitted_counts': v.get('omitted_counts'),
                      'impact_hashes': [p['preview_hash'] for p in v.get('root_removal_impacts', [])]})
    journal.close()
    groups = []
    for (sid, blocks), n in physical_counts.most_common(5):
        groups.append({'source_id': sid, 'label': label(sid), 'block_ids': list(blocks), 'state_count': n})
    result = {'adr': adr, 'case': case, 'graph_path': str((base / 'graph.json.gz').relative_to(ROOT)),
              'graph_file_sha256': hashlib.sha256((base / 'graph.json.gz').read_bytes()).hexdigest(),
              'checkpoint_hash': g['checkpoint_hash'], 'binding': g['binding'], 'status': g['status'],
              'checkpoint_hash_verified': True,
              'roots': root_stats, 'sources': len(g['source_ids']), 'states': len(states),
              'unique_physical_extents': len(physical_counts),
              'expanded_states': len(g['expanded_state_ids']), 'unique_expanded_physical_extents': len(expanded_physical),
              'pending': len(g['pending']), 'expanded_also_pending': len(expanded_pending),
              'expanded_pending_examples': sorted(expanded_pending)[:5],
              'expanded_pending_self_loop_edges': [{k: e[k] for k in ('reference_id', 'direction', 'from_state', 'target_states')} for e in self_pending_edges],
              'edges': len(g['edges']), 'edges_ignoring_arrival_guard': len(distinct_edges),
              'edge_directions': dict(collections.Counter(e['direction'] for e in g['edges'])),
              'suppressed_returns': sum(bool(e.get('suppressed_return_source_ids')) for e in g['edges']),
              'sources_by_shortest_recorded_hop': dict(sorted(collections.Counter(first_source.values()).items())),
              'top_repeated_extents': groups, 'incoming_outgoing_pivots': pivots,
              'unique_scoped_blocks': len(coverage), 'scoped_text_chars': scoped_chars,
              'whole_original_text_chars_for_reached_sources': originals_chars,
              'bundle_actually_saved': bool(t.get('source_bundle')),
              'saved_bundle_original_chars': sum(len(b['text']) for s in t.get('source_bundle', {}).get('reference_bundle', {}).get('sources', []) for b in s['blocks']),
              'removal_preview_inner_checks_per_call_from_code': len(g['source_ids']) * len(coverage) * len(g['roots']),
              'exclusive_blocks_by_root': {r['root_id']: sum(owners == {r['root_id']} for owners in coverage.values()) for r in g['roots']},
              'views': views, 'errors': t['errors'], 'evidence_count': len(t['evidence'])}
    results.append(result)
    print(json.dumps({k: result[k] for k in ('adr', 'case', 'sources', 'states', 'unique_physical_extents',
          'expanded_states', 'unique_expanded_physical_extents', 'pending', 'expanded_also_pending',
          'edges', 'edges_ignoring_arrival_guard', 'scoped_text_chars', 'whole_original_text_chars_for_reached_sources',
          'removal_preview_inner_checks_per_call_from_code')}, ensure_ascii=False))

reference_ids = ['ref:3c422964a89bc19933d739a3', 'ref:82537c3384a3ca9814bc4d71',
                 'ref:1e1f66d991f5c19b7047ceb1', 'ref:002048d8449af987f9e17c2e']
witnesses = {rid: json.loads(db.execute('SELECT json FROM reference WHERE id=?', (rid,)).fetchone()[0]) for rid in reference_ids}
runtime = ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/artifacts/runtime-guarded/02_BACKEND/semantic_runtime'
code_hashes = {str((runtime / path).relative_to(ROOT)): hashlib.sha256((runtime / path).read_bytes()).hexdigest()
               for path in ['reference_exploration.py', 'legal_agent/source_selection.py',
                            'legal_agent/workflow_tiers_session.py', 'legal_agent/workflow_tiers_views.py']}
result = {'kind': 'read_only_existing_trace_amplification_audit', 'runs': results,
          'code_hashes': code_hashes, 'pivot_reference_witnesses': witnesses,
          'limitations': ['No graph replay, evaluator, model calls, code fix, DB rebuild or activation.',
                         'Physical-extent grouping is diagnostic, not a proposed blind deduplication: return guards have semantics.',
                         'Recorded partial graphs only; no causal attribution of all reached sources to any single defect.',
                         'Whole-original characters quantify preservation footprint, not model-delivered token count.',
                         'Removal preview check count is a code-derived operation count, not measured wall time.']}
(OUT / 'amplification_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
db.close()
