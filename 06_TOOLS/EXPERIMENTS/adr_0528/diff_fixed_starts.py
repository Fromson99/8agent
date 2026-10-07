"""Compare raw source spans from paired bounded walks without treating counts as quality."""
import json
import gzip
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0528-extended-mok-annex-scope'


def read(case, arm):
    folder = ADR / 'artifacts/fixed-start-run001' / case / arm
    with gzip.open(folder / 'graph.json.gz', 'rt') as stream:
        graph = json.load(stream)
    return graph, json.loads((folder / 'summary.json').read_text())


def span_set(graph):
    return {
        (state['extent']['source_id'], str(span['block_id']),
         span['start_cp'], span['end_cp'], span['block_hash'])
        for state in graph['states'] for span in state['extent'].get('spans', [])
    }


def compact_spans(spans):
    return [dict(zip(('source_id', 'block_id', 'start_cp', 'end_cp', 'block_hash'), row))
            for row in sorted(spans)[:100]]


def root_edges(graph):
    roots = set(graph['root_states'].values())
    source_by_state = {state['state_id']: state['extent']['source_id']
                       for state in graph['states']}
    return {
        (source_by_state.get(edge['from_state']), edge['direction'],
         edge['locator'], tuple(edge['origins']),
         tuple(sorted(source_by_state[state] for state in edge['target_states']
                      if state in source_by_state)))
        for edge in graph['edges'] if edge['from_state'] in roots
    }


def compact_edges(edges):
    return [dict(zip(('source_id', 'direction', 'locator', 'origins', 'target_source_ids'), row))
            for row in sorted(edges)[:100]]


result = {'schema_version': 'fixed-start-evidence-diff-v1', 'cases': {},
          'interpretation': 'Both walks have fixed 500-state budgets and can be PARTIAL; observed differences are not adjudicated recall or legal correctness.'}
for case in ('cm-025', 'cm-040'):
    base, bs = read(case, 'baseline')
    candidate, cs = read(case, 'repaired')
    assert bs['root_source_ids'] == cs['root_source_ids']
    b, c = span_set(base), span_set(candidate)
    be, ce = root_edges(base), root_edges(candidate)
    bsrc, csrc = set(base['source_ids']), set(candidate['source_ids'])
    result['cases'][case] = {
        'root_source_ids': bs['root_source_ids'],
        'baseline': {key: bs[key] for key in ('status', 'state_count', 'physical_extent_count', 'edge_count', 'gap_count', 'pending_count')},
        'repaired': {key: cs[key] for key in ('status', 'state_count', 'physical_extent_count', 'edge_count', 'gap_count', 'pending_count')},
        'source_ids_shared': len(bsrc & csrc),
        'source_ids_only_baseline': sorted(bsrc - csrc),
        'source_ids_only_repaired': sorted(csrc - bsrc),
        'raw_spans_shared': len(b & c),
        'raw_spans_only_baseline_count': len(b - c),
        'raw_spans_only_repaired_count': len(c - b),
        'raw_spans_only_baseline_sample': compact_spans(b - c),
        'raw_spans_only_repaired_sample': compact_spans(c - b),
        'direct_root_edges_shared': len(be & ce),
        'direct_root_edges_only_baseline': len(be - ce),
        'direct_root_edges_only_repaired': len(ce - be),
        'direct_root_edges_only_baseline_sample': compact_edges(be - ce),
        'direct_root_edges_only_repaired_sample': compact_edges(ce - be),
        'baseline_frontier_not_exhausted': bool(base['pending']),
        'candidate_frontier_not_exhausted': bool(candidate['pending']),
        'quality_certified': False,
    }
output = ADR / 'artifacts/fixed-start-evidence-diff.json'
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({case: {key: value for key, value in row.items() if not key.endswith('_sample') and not key.startswith('source_ids_only')}
                  for case, row in result['cases'].items()}, ensure_ascii=False, indent=2))
