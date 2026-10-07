"""Read-only paired fixed-root navigation through baseline and research overlay."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0532-overlay-reference-connectivity'
DESIGN = ADR / 'artifacts/frozen-design.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin():
    path = ROOT / '06_TOOLS/EXPERIMENTS/adr_0531/bootstrap.py'
    spec = importlib.util.spec_from_file_location('adr0531_bootstrap', path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    overlay = bootstrap.load_candidate()
    from semantic_runtime.reference_exploration import ReferenceNavigator
    runtime = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0530/repaired/revisions/rev-003/snapshot/02_BACKEND'
    if not Path(sys.modules['semantic_runtime'].__file__).is_relative_to(runtime):
        raise ValueError('frozen navigator not selected')
    return ReferenceNavigator, overlay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=('baseline', 'overlay'), required=True)
    parser.add_argument('--case', choices=('cm-025', 'cm-040'), required=True)
    args = parser.parse_args()
    design = read(DESIGN)
    for key in ('root_input', 'public_scope'):
        if sha(ROOT / design[key]) != design[key + '_sha256']:
            raise ValueError('frozen input drift: ' + key)
    Navigator, overlay = pin()
    scope = read(ROOT / design['public_scope'])['public_scope_document_ids']
    seed = read(ROOT / design['root_input'])[args.case]
    arm = design['arms'][args.arm]
    generation = ROOT / arm['generation']
    if sha(generation / 'manifest.json') != arm['manifest_sha256']:
        raise ValueError('generation manifest drift')
    if args.arm == 'baseline':
        db_path = generation / 'navigation/navigation.sqlite'
        db = sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)
    else:
        db = overlay.open_research_overlay(generation)
    try:
        placeholders = ','.join('?' for _ in scope)
        sources = {source['id']: source for (raw,) in db.execute(
            'SELECT json FROM source WHERE document_id IN (' + placeholders + ')', scope)
            for source in [json.loads(raw)]}
        for row in seed:
            sid = row['source_id']
            if sid not in sources or sources[sid]['document_id'] != row['document_id']:
                raise ValueError('fixed root source changed: ' + sid)
            if sorted(str(b) for b in row['block_ids']) != sorted(str(b['block_id']) for b in sources[sid]['blocks']):
                raise ValueError('fixed root blocks changed: ' + sid)
        navigator = Navigator(db, sources, scope, design['binding'])
        roots = [navigator.root(row['source_id'], query=row['query'], reason=row['reason'],
                                block_ids=row['block_ids']) for row in seed]
        started = time.monotonic()
        graph = navigator.walk(roots, max_states=design['max_states'], max_seconds=design['max_seconds'])
        elapsed = time.monotonic() - started
        out = ADR / 'artifacts/run-001' / args.case / args.arm
        out.mkdir(parents=True, exist_ok=False)
        with gzip.open(out / 'graph.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(graph, stream, ensure_ascii=False, separators=(',', ':'))
        physical = sorted({(state['extent']['source_id'], tuple(state['extent']['block_ids']),
                            json.dumps(state['extent'].get('spans'), ensure_ascii=False, sort_keys=True))
                           for state in graph['states']})
        row = {'schema_version': 'fixed-start-comparison-v1', 'case_id': args.case,
               'arm_id': args.arm, 'runtime_revision': 'ADR-0530/repaired/rev-003',
               'generation': arm['generation'], 'generation_manifest_sha256': arm['manifest_sha256'],
               'root_source_ids': [r['source_id'] for r in seed], 'root_count': len(roots),
               'budget': {'max_states': design['max_states'], 'max_seconds': design['max_seconds']},
               'status': graph['status'], 'seconds': round(elapsed, 3),
               'state_count': len(graph['states']), 'physical_extent_count': len(physical),
               'edge_count': len(graph['edges']), 'gap_count': len(graph['gaps']),
               'pending_count': len(graph['pending']), 'source_ids': graph['source_ids'],
               'no_model_calls': True, 'presented_source_ids': [], 'gold_visible': False,
               'quality_certified': False}
        (out / 'summary.json').write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in row.items() if k != 'source_ids'}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == '__main__':
    main()
