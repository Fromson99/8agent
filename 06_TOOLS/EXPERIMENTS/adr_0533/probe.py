"""Read-only graph and exclusion-impact cost probe for a research overlay."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0533-overlay-removal-impact-amplification'
DESIGN = ADR / 'artifacts/frozen-design.json'
PARENT_DESIGN = ROOT / '04_EXPERIMENTS/ADR/ADR-0532-overlay-reference-connectivity/artifacts/frozen-design.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_modules(design):
    for key in ('bootstrap', 'runtime_candidate', 'overlay_candidate'):
        if sha(ROOT / design[key]) != design[key + '_sha256']:
            raise ValueError('frozen input drift: ' + key)
    path = ROOT / design['bootstrap']
    spec = importlib.util.spec_from_file_location('adr0531_bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    overlay = module.load_candidate()
    from semantic_runtime.reference_exploration import ReferenceNavigator
    from semantic_runtime.legal_agent.source_selection import coverage_index, removal_preview, review_removal
    expected = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0530/repaired/revisions/rev-003/snapshot/02_BACKEND'
    if not Path(sys.modules['semantic_runtime'].__file__).is_relative_to(expected):
        raise ValueError('frozen rev-003 runtime not selected')
    return overlay, ReferenceNavigator, coverage_index, removal_preview, review_removal


def saved_graph(design, case, arm):
    row = design['inputs'][f'{case}/{arm}']
    path = ROOT / row['path']
    if sha(path) != row['sha256']:
        raise ValueError('saved graph drift: ' + str(path))
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        graph = json.load(stream)
    return graph


def measures(graph, coverage_index, removal_preview, review_removal, issues):
    started = time.monotonic()
    coverage = coverage_index(graph)
    coverage_seconds = time.monotonic() - started
    started = time.monotonic()
    previews = [removal_preview(graph, root['root_id'], issues, coverage=coverage)
                for root in graph['roots']]
    preview_seconds = time.monotonic() - started
    guard = None
    if previews:
        try:
            review_removal(previews[0], {'preview_hash': previews[0]['preview_hash']},
                           adopted_roots=[], delivered_evidence=[])
        except ValueError as exc:
            guard = str(exc)
    source_blocks = {(state['extent']['source_id'], str(block)) for state in graph['states']
                     for block in state['extent']['block_ids']}
    physical = {(state['extent']['source_id'], tuple(state['extent']['block_ids']),
                 json.dumps(state['extent'].get('spans'), ensure_ascii=False, sort_keys=True))
                for state in graph['states']}
    preview_chars = [len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
                     for value in previews]
    return {'status': graph['status'], 'source_count': len(graph['source_ids']),
            'state_count': len(graph['states']), 'physical_extent_count': len(physical),
            'edge_count': len(graph['edges']), 'pending_count': len(graph['pending']),
            'root_count': len(graph['roots']), 'unique_source_blocks': len(source_blocks),
            'legacy_nested_condition_checks_estimate': len(graph['source_ids']) * len(source_blocks) * len(graph['roots']),
            'new_span_owner_events': sum(len(state['extent'].get('spans', [])) * len(state['root_ids'])
                                         for state in graph['states']),
            'coverage_index_seconds': round(coverage_seconds, 3),
            'removal_preview_seconds': round(preview_seconds, 3),
            'exclusive_extent_counts': [len(value['exclusive_extents']) for value in previews],
            'preview_chars_by_root': preview_chars,
            'preview_chars_total': sum(preview_chars),
            'review_removal_guard': guard,
            'expanded_also_pending': len(set(graph['expanded_state_ids']) & set(graph['pending'])),
            'checkpoint_hash': graph['checkpoint_hash'],
            'peak_rss_kib_process': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def resume(graph, arm, overlay, Navigator, parent):
    generation = ROOT / parent['arms'][arm]['generation']
    if sha(generation / 'manifest.json') != parent['arms'][arm]['manifest_sha256']:
        raise ValueError('generation manifest drift')
    scope = read(ROOT / parent['public_scope'])['public_scope_document_ids']
    if arm == 'overlay':
        db = overlay.open_research_overlay(generation)
    else:
        path = generation / 'navigation/navigation.sqlite'
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        placeholders = ','.join('?' for _ in scope)
        sources = {source['id']: source for (raw,) in db.execute(
            'SELECT json FROM source WHERE document_id IN (' + placeholders + ')', scope)
            for source in [json.loads(raw)]}
        nav = Navigator(db, sources, scope, parent['binding'])
        start = time.monotonic()
        result = nav.walk(graph['roots'], max_states=10000, max_seconds=30, checkpoint=graph)
        elapsed = time.monotonic() - start
        outside = sorted({state['extent']['document_id'] for state in result['states']} - set(scope))
        if outside or set(result['root_states']) != set(graph['root_states']):
            raise ValueError('scope/root drift')
        return result, round(elapsed, 3)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=('baseline', 'overlay'), required=True)
    args = parser.parse_args()
    design = read(DESIGN)
    parent = read(PARENT_DESIGN)
    for key in ('root_input', 'public_scope'):
        if sha(ROOT / parent[key]) != parent[key + '_sha256']:
            raise ValueError('parent input drift: ' + key)
    overlay, Navigator, coverage_index, removal_preview, review_removal = frozen_modules(design)
    output = ADR / 'artifacts/run-001' / args.arm
    output.mkdir(parents=True, exist_ok=False)
    fixed = {}
    for case in ('cm-025', 'cm-040'):
        graph = saved_graph(design, case, args.arm)
        fixed[case] = measures(graph, coverage_index, removal_preview, review_removal,
                               design['issues_for_preview'])
    stress_graph, walk_seconds = resume(saved_graph(design, 'cm-040', args.arm), args.arm,
                                        overlay, Navigator, parent)
    with gzip.open(output / 'stress-cm-040-graph.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(stress_graph, stream, ensure_ascii=False, separators=(',', ':'))
    stress = measures(stress_graph, coverage_index, removal_preview, review_removal,
                      design['issues_for_preview'])
    stress['walk_seconds'] = walk_seconds
    result = {'schema_version': 'overlay-removal-amplification-v1', 'arm': args.arm,
              'fixed': fixed, 'stress_cm040': stress, 'model_calls': 0,
              'actual_model_view_measured': False, 'main_wiring_unchanged': True}
    (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'arm': args.arm, 'fixed': {k: {x: v[x] for x in
          ('status', 'source_count', 'state_count', 'coverage_index_seconds', 'preview_chars_total')}
          for k, v in fixed.items()}, 'stress': {x: stress[x] for x in
          ('status', 'source_count', 'state_count', 'coverage_index_seconds',
           'removal_preview_seconds', 'preview_chars_total', 'pending_count',
           'walk_seconds', 'peak_rss_kib_process')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
