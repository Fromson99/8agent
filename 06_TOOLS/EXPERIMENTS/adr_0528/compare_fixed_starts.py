"""Bounded, gold-free paired walk from identical saved public roots."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0528-extended-mok-annex-scope'
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0528/repaired'
DESIGN = ADR / 'artifacts/fixed-start-design.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin():
    candidate = read(CANDIDATE / 'candidate.json')
    revision = candidate['revisions'][-1]
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        if sha(path) != row['snapshot_sha256']:
            raise ValueError('frozen runtime drift: ' + str(path))
    code = CANDIDATE / 'revisions' / revision['revision_id'] / 'snapshot/02_BACKEND'
    sys.path.insert(0, str(code))
    from semantic_runtime.reference_exploration import ReferenceNavigator
    if not Path(sys.modules['semantic_runtime'].__file__).is_relative_to(code):
        raise ValueError('candidate runtime not selected')
    return ReferenceNavigator, revision['revision_id']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=('baseline', 'repaired'), required=True)
    parser.add_argument('--case', choices=('cm-025', 'cm-040'), required=True)
    args = parser.parse_args()
    design = read(DESIGN)
    if sha(ROOT / design['root_input']) != design['root_input_sha256']:
        raise ValueError('frozen root input drift')
    if sha(ROOT / design['public_scope']) != design['public_scope_sha256']:
        raise ValueError('frozen public scope drift')
    Navigator, revision = pin()
    scope = read(ROOT / design['public_scope'])['public_scope_document_ids']
    seed = read(ROOT / design['root_input'])[args.case]
    generation = ROOT / design['arms'][args.arm]['generation']
    db_path = generation / 'navigation/navigation.sqlite'
    db = sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)
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
        out = ADR / 'artifacts/fixed-start-run001' / args.case / args.arm
        out.mkdir(parents=True, exist_ok=False)
        with gzip.open(out / 'graph.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(graph, stream, ensure_ascii=False, separators=(',', ':'))
        physical = sorted({(state['extent']['source_id'], tuple(state['extent']['block_ids']),
                            json.dumps(state['extent'].get('spans'), ensure_ascii=False, sort_keys=True))
                           for state in graph['states']})
        row = {'schema_version': 'fixed-start-comparison-v1', 'case_id': args.case, 'arm_id': args.arm,
               'runtime_revision': revision, 'generation': design['arms'][args.arm]['generation'],
               'generation_manifest_sha256': sha(generation / 'manifest.json'),
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
