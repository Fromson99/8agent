#!/usr/bin/env python3
"""Opt-in GENOS pre-LLM optimization, no installed files changed.

Default: run sibling genos_structure_timing.py[.txt] with optimization enabled.
--pipeline: forward remaining arguments to installed genos_data_stages.py.
Use a new pipeline run ID. Original command remains the rollback entrypoint.
"""
from __future__ import annotations

import argparse
import ast
import copy
from contextlib import contextmanager
import heapq
import importlib.util
import inspect
import json
import os
from pathlib import Path
import runpy
import shutil
import sqlite3
import sys
import textwrap
import uuid

RECIPE = 'indexed-source-jobs-projection-v1'


def indexed_groups(blocks, units):
    """Legacy priority: article first, shortest span next, original order on ties.

    Attachments participate in ownership, but (like legacy queue.prepare) only
    span intersections participate in downstream structural context.
    Complexity O((nodes+attachments) log(nodes+attachments) + blocks log(nodes)
    + emitted span memberships). Deep overlapping context can still be large.
    """
    starts = []
    for ordinal, unit in enumerate(units):
        lo, hi = unit['span']
        starts.append((lo, hi, ordinal, True))
        for attached in unit.get('attachments', []):
            idx = attached['block']
            starts.append((idx, idx+1, ordinal, False))
    starts.sort()
    ends, anchors, count, active_spans = [], [], [0]*len(units), set()
    groups, contexts = {}, {}
    position, previous = 0, -1
    for block in blocks:
        idx = int(block['idx'])
        if idx < previous:
            raise ValueError('Source blocks not ordered')
        previous = idx
        while position < len(starts) and starts[position][0] <= idx:
            lo, hi, ordinal, span = starts[position]
            position += 1
            if hi <= idx:
                continue
            count[ordinal] += 1
            heapq.heappush(ends, (hi, ordinal, span))
            unit = units[ordinal]
            heapq.heappush(anchors, (unit.get('family') != 'kr_article',
                                    unit['span'][1]-unit['span'][0], ordinal))
            if span:
                active_spans.add(ordinal)
        while ends and ends[0][0] <= idx:
            _, ordinal, span = heapq.heappop(ends)
            count[ordinal] -= 1
            if span:
                active_spans.discard(ordinal)
        while anchors and not count[anchors[0][2]]:
            heapq.heappop(anchors)
        if not anchors:
            raise ValueError(f'block {idx} has no structural unit')
        uid = str(units[anchors[0][2]]['id'])
        groups.setdefault(uid, []).append(block)
        contexts.setdefault(uid, set()).update(active_spans)
    if not groups:
        raise ValueError('empty structured document')
    return groups, {uid: [units[i] for i in sorted(indices)] for uid, indices in contexts.items()}


def assert_consumer_compatible(runtime):
    """Refuse unknown queue semantics; do not silently narrow a changed consumer."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(runtime.prepare)))
    expected = ast.parse("[u for u in value['structural_units'] if any(u['span'][0] <= int(b['idx']) < u['span'][1] for b in blocks)]", mode='eval').body
    target = ast.dump(ast.parse("part['structural_units']", mode='eval').body, include_attributes=False)
    # Assignment targets use Store context, while expression parsing uses Load.
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            lhs = copy.deepcopy(node.targets[0])
            if isinstance(lhs, ast.Subscript):
                lhs.ctx = ast.Load()
            if ast.dump(lhs, include_attributes=False) == target:
                matches.append(ast.dump(node.value, include_attributes=False))
    if matches != [ast.dump(expected, include_attributes=False)]:
        raise ValueError('Unsupported installed queue structure projection; optimization not enabled')
    reads = [n for n in ast.walk(tree) if isinstance(n, ast.Subscript)
             and isinstance(n.value, ast.Name) and n.value.id == 'value'
             and isinstance(n.slice, ast.Constant) and n.slice.value == 'structural_units']
    if len(reads) != 1:
        raise ValueError('Unsupported additional structural_units consumer')


def assert_producer_compatible(builder):
    tree = ast.parse(textwrap.dedent(inspect.getsource(builder.source_jobs)))
    expected = {
        'covering': "[u for u in units if u['span'][0] <= int(block['idx']) < u['span'][1] or any(a['block'] == int(block['idx']) for a in u.get('attachments', []))]",
        'articles': "[u for u in covering if u.get('family') == 'kr_article']",
        'anchor': "min(articles or covering, key=lambda u: u['span'][1] - u['span'][0])",
    }
    for name, expression in expected.items():
        actual = [ast.dump(n.value, include_attributes=False) for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name]
        if actual != [ast.dump(ast.parse(expression, mode='eval').body, include_attributes=False)]:
            raise ValueError('Unsupported installed source grouping: '+name)


def verify_projection(folder):
    """Independent legacy ownership/context check after timing; no model calls.

    Does not construct the old multi-GB repeated JSON. Exact job context equality
    with the union of legacy per-block span matches proves equality for every
    subsequent chunk partition, including long-block character segmentation.
    """
    database = (folder/'authoring-source.sqlite').absolute()
    checked_jobs, checked_blocks = 0, 0
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for did, name, raw_sha, document_json in db.execute('SELECT * FROM document ORDER BY document_id').fetchall():
            units = [json.loads(r[0]) for r in db.execute('SELECT json FROM source_unit WHERE document_id=?', (did,))]
            blocks = [json.loads(r[0]) for r in db.execute('SELECT json FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)', (did,))]
            expected, context = {}, {}
            for block in blocks:
                idx = int(block['idx'])
                covering = [u for u in units if u['span'][0] <= idx < u['span'][1]
                            or any(a['block'] == idx for a in u.get('attachments', []))]
                articles = [u for u in covering if u.get('family') == 'kr_article']
                anchor = min(articles or covering, key=lambda u: u['span'][1]-u['span'][0])
                uid = str(anchor['id'])
                expected.setdefault(uid, []).append(block)
                indices = context.setdefault(uid, set())
                indices.update(i for i, u in enumerate(units) if u['span'][0] <= idx < u['span'][1])
            jobs = list(db.execute('SELECT job_id,state,input_json FROM authoring_job WHERE document_id=? ORDER BY rowid', (did,)))
            if [r[0] for r in jobs] != [did+':'+uid for uid in expected]:
                raise ValueError('Equivalence failure: job ID/order')
            source_set = json.loads((folder/'source.json').read_text())['source_set_sha256']
            for (job_id, state, payload), (uid, members) in zip(jobs, expected.items()):
                expected_payload = dict(document_version_id=did, document_name=name,
                    document_metadata=json.loads(document_json).get('document_metadata', {}),
                    source_artifact_sha256=raw_sha, source_set_sha256=source_set,
                    article_unit_id=uid, blocks=members,
                    structural_units=[units[i] for i in sorted(context[uid])])
                if state != 'PENDING_EXTRACTION' or json.loads(payload) != expected_payload:
                    raise ValueError('Equivalence failure: source job '+job_id)
            checked_jobs += len(jobs)
            checked_blocks += len(blocks)
    return dict(status='PASSED', jobs=checked_jobs, blocks=checked_blocks,
                method='Independent legacy grouping and exact per-job union projection; no model calls')


def compact_source_jobs(build_dir, plan, builder):
    target, marker = build_dir/'authoring-source.sqlite', build_dir/'source.json'
    if marker.exists():
        receipt = json.loads(marker.read_text())
        if receipt.get('job_recipe') != RECIPE or builder.sha(target) != receipt['sha256']:
            raise ValueError('Optimization recipe/source hash mismatch; use a new run')
        return target, receipt
    store = builder._build_source_store
    # Preserve old/new installed score policy instead of replacing it.
    kwargs = {'allow_score_advisory': True} if 'allow_score_advisory' in inspect.signature(store).parameters else {}
    source, original = store(build_dir, **kwargs)
    if set(original['document_ids']) != {r['document_id'] for r in plan['files']}:
        raise ValueError('some input documents did not reach the source store')
    temporary = build_dir/('source-'+uuid.uuid4().hex+'.tmp.sqlite')
    shutil.copyfile(source, temporary)
    node_references, legacy_references = 0, 0
    with sqlite3.connect(temporary) as db:
        db.execute('CREATE TABLE authoring_job(job_id TEXT PRIMARY KEY,document_id TEXT,state TEXT,input_json TEXT)')
        for did, name, raw_sha, document_json in db.execute('SELECT * FROM document ORDER BY document_id').fetchall():
            units = [json.loads(r[0]) for r in db.execute('SELECT json FROM source_unit WHERE document_id=?', (did,))]
            blocks = [json.loads(r[0]) for r in db.execute('SELECT json FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)', (did,))]
            groups, contexts = indexed_groups(blocks, units)
            metadata = json.loads(document_json).get('document_metadata', {})
            for uid, members in groups.items():
                context = contexts[uid]
                payload = {'document_version_id': did, 'document_name': name,
                           'document_metadata': metadata, 'source_artifact_sha256': raw_sha,
                           'source_set_sha256': original['source_fingerprint'],
                           'article_unit_id': uid, 'blocks': members, 'structural_units': context}
                db.execute('INSERT INTO authoring_job VALUES (?,?,?,?)',
                           (did+':'+uid, did, 'PENDING_EXTRACTION', json.dumps(payload, ensure_ascii=False)))
                node_references += len(context)
                legacy_references += len(units)
    os.replace(temporary, target)
    receipt = {'sha256': builder.sha(target), 'source_set_sha256': original['source_fingerprint'],
               'documents': original['documents'], 'blocks': original['blocks'],
               'document_ids': original['document_ids'], 'job_recipe': RECIPE,
               'stored_node_references': node_references, 'legacy_node_references': legacy_references}
    builder.atomic(marker, receipt)
    print(f'[OPTIMIZED] stored_node_references={node_references} legacy_node_references={legacy_references}', flush=True)
    return target, receipt


def verify_once(folder, stages):
    """One hash per file in this verification; no cross-call hash cache."""
    folder = stages.plain_path(folder)
    receipt = json.loads((folder/'structure-receipt.json').read_text())
    if receipt['plan'] != json.loads((folder/'prepared-plan.json').read_text()):
        raise ValueError('Structure plan/receipt mismatch')
    if receipt['key'] != stages.structure_key(receipt['input_row'], receipt['plan'], receipt['parser']):
        raise ValueError('Structure identity mismatch')
    actual = stages.files_hashes(folder)
    if actual != receipt['files']:
        raise ValueError('Structure cache file/hash mismatch')
    source = json.loads((folder/'source.json').read_text())
    if source['sha256'] != actual.get('authoring-source.sqlite'):
        raise ValueError('Structure source SQLite hash mismatch')
    return receipt


@contextmanager
def enabled(root):
    from lawrag.pipeline import genos_build as builder, genos_stages as stages
    runtime = builder.authoring()
    assert_consumer_compatible(runtime)
    assert_producer_compatible(builder)
    identity = {'recipe': RECIPE, 'runner_sha256': builder.sha(__file__),
                'consumer_sha256': builder.sha(runtime.__file__)}
    original_jobs, original_identity, original_verify = builder.source_jobs, stages.parser_identity, stages.verify_structure
    def source_jobs(build_dir, plan):
        return compact_source_jobs(build_dir, plan, builder)
    def parser_identity(path):
        result = original_identity(path)
        result['source_job_optimization'] = identity
        return result
    def verify_structure(folder):
        return verify_once(folder, stages)
    builder.source_jobs, stages.parser_identity, stages.verify_structure = source_jobs, parser_identity, verify_structure
    try:
        print('[OPTIMIZED] '+json.dumps(identity), flush=True)
        yield identity
    finally:
        builder.source_jobs, stages.parser_identity, stages.verify_structure = original_jobs, original_identity, original_verify


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--pipeline', action='store_true', help='Use installed stages CLI instead of one-document timing')
    args, rest = parser.parse_known_args(argv)
    root = Path(args.root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        parser.error('Use physical DEV root')
    if not (root/'02_BACKEND/lawrag/pipeline/genos_stages.py').is_file():
        parser.error('Run from GENOS DEV root')
    sys.path.insert(0, str(root/'02_BACKEND'))
    try:
        with enabled(root) as optimization:
            if args.pipeline:
                script = root/'06_TOOLS/COMMANDS/genos_data_stages.py'
                previous = sys.argv
                try:
                    sys.argv = [str(script), *rest]
                    runpy.run_path(str(script), run_name='__main__')
                finally:
                    sys.argv = previous
                return 0
            folder = Path(__file__).parent
            candidates = [folder/'genos_structure_timing.py.txt', folder/'genos_structure_timing.py']
            path = next((p for p in candidates if p.is_file()), None)
            if path is None:
                raise ValueError('Place mailed genos_structure_timing.py.txt beside this file')
            # .txt attachments need an explicit SourceFileLoader.
            from importlib.machinery import SourceFileLoader
            spec = importlib.util.spec_from_loader('genos_timing_opt', SourceFileLoader('genos_timing_opt', str(path)))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            class OptimizedTiming(module.Timing):
                def __init__(self, directory):
                    self.directory = directory
                    super().__init__(directory)
                    self.emit('OPTIMIZATION', RECIPE, **optimization)

                def close(self):
                    try:
                        summary_path = self.directory/'summary.json'
                        if summary_path.is_file():
                            report = json.loads(summary_path.read_text())
                            report.update(experiment_id='ADR-0344-experiment-v1', arm_id='optimized',
                                          optimization=optimization)
                            summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
                    finally:
                        super().close()
            module.Timing = OptimizedTiming
            original_summary = module.summarize_source
            def summarize_source(folder, timing):
                counts = original_summary(folder, timing)
                if '--rebuild' in rest:
                    with timing.stage('최적화 동일성 확인 (성능 측정과 별도)'):
                        proof = verify_projection(folder)
                    (folder/'../projection-equivalence.json').resolve().write_text(
                        json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
                    timing.emit('EQUIVALENCE', '블록 배정·최종 청크 문맥 보존', **proof)
                    counts['equivalence'] = proof
                return counts
            module.summarize_source = summarize_source
            return module.main(['--root', str(root), *rest])
    except Exception as exc:
        print('[ERROR] '+type(exc).__name__+': '+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
