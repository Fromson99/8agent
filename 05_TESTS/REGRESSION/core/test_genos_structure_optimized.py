"""Synthetic exact-equivalence tests; no real documents, timing comparison or LLM."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import sqlite3
from types import SimpleNamespace

import pytest

from lawrag.pipeline import genos_build as build, genos_stages as stages
from .test_genos_build import setup, XML, Fake

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('opt_jobs', ROOT/'06_TOOLS/COMMANDS/genos_structure_optimized.py')
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)


def legacy(blocks, units):
    groups = {}
    for block in blocks:
        covering = [u for u in units if u['span'][0] <= int(block['idx']) < u['span'][1]
                    or any(a['block'] == int(block['idx']) for a in u.get('attachments', []))]
        articles = [u for u in covering if u.get('family') == 'kr_article']
        anchor = min(articles or covering, key=lambda u: u['span'][1]-u['span'][0])
        groups.setdefault(str(anchor['id']), []).append(block)
    return groups


@pytest.mark.parametrize('seed', range(25))
def test_indexed_exact_ownership_and_context(seed):
    rng = random.Random(seed)
    blocks = [{'idx': i, 'text': str(i)} for i in range(40)]
    units = [{'id': 0, 'span': [0, 40], 'family': 'chapter'}]
    for i in range(1, 70):
        lo = rng.randrange(40)
        units.append({'id': i, 'span': [lo, rng.randrange(lo+1, 41)],
                      'family': rng.choice(['kr_article', 'paragraph']),
                      'attachments': [{'block': rng.randrange(40)}]})
    groups, contexts = opt.indexed_groups(blocks, units)
    expected = legacy(blocks, units)
    assert list(groups.items()) == list(expected.items())
    for uid, members in groups.items():
        projected = [u for u in units if any(u['span'][0] <= b['idx'] < u['span'][1] for b in members)]
        assert contexts[uid] == projected
        # Every possible single-block child must have the same final context.
        for b in members:
            pred = lambda u: u['span'][0] <= b['idx'] < u['span'][1]
            assert list(filter(pred, contexts[uid])) == list(filter(pred, units))


def test_ties_attachment_and_priority():
    blocks = [{'idx': i} for i in range(4)]
    units = [dict(id=9, family='paragraph', span=[0,4]),
             dict(id=2, family='kr_article', span=[0,2], attachments=[{'block':3}]),
             dict(id=1, family='kr_article', span=[0,2]),
             dict(id=8, family='paragraph', span=[2,3])]
    groups, context = opt.indexed_groups(blocks, units)
    assert list(groups) == ['2', '8']  # input-order tie, not lowest ID
    assert groups == legacy(blocks, units)
    assert groups['2'][-1]['idx'] == 3
    with pytest.raises(ValueError, match='no structural unit'):
        opt.indexed_groups([{'idx': 10}], units)


def test_consumer_guard():
    opt.assert_consumer_compatible(build.authoring())
    def unknown():
        part = {}
        part['structural_units'] = []
    with pytest.raises(ValueError, match='Unsupported'):
        opt.assert_consumer_compatible(SimpleNamespace(prepare=unknown))


def test_actual_queue_inputs_and_requests_identical(setup):
    args, raw, out = setup
    # Multiple articles make unnecessary per-job contexts observable.
    original = (raw/'one.xml').read_text()
    article = original[original.index('<조문단위>'):original.index('</조문단위>')+len('</조문단위>')]
    original = original.replace(article, ''.join(article.replace('<조문번호>1', f'<조문번호>{n}').replace('제1조', f'제{n}조') for n in range(1,5)))
    (raw/'one.xml').write_text(original)
    plan = build.inventory(raw, 'internal')
    base, optimized = out/'base', out/'optimized'
    for folder in (base, optimized):
        folder.mkdir(parents=True)
        with build.isolated(folder):
            build.ingest_files(plan, folder, lambda _: None)
    with build.isolated(base):
        baseline, receipt = build.source_jobs(base, plan)
    with build.isolated(optimized):
        candidate, compact_receipt = opt.compact_source_jobs(optimized, plan, build)
    proof = opt.verify_projection(optimized)
    assert proof['status'] == 'PASSED' and proof['jobs'] == 4
    assert compact_receipt['stored_node_references'] < compact_receipt['legacy_node_references']
    assert not Fake.instances
    runtime = build.authoring()
    queues = []
    for n, source in enumerate((baseline, candidate)):
        queue = runtime.prepare(out/f'queue-{n}', source, runtime.EXTRACT_SYSTEM,
            runtime.contract_module().profile_schema('OBSERVATION', build.ROOT),
            model='fixture-model', revision='fixture', endpoint='http://fixture.invalid/chat/completions',
            authority_generation='fixed-test-generation', segment_chars=60, extraction_mode='staged')
        with queue.connect(readonly=True) as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM job ORDER BY id')]
        queues.append((queue, rows))
    assert queues[0][1] == queues[1][1]
    for (q1, rows1), (q2, rows2) in [(queues[0], queues[1])]:
        from lawrag.pipeline.genos_staged import queue_class
        a, b = queue_class(runtime)(q1.directory), queue_class(runtime)(q2.directory)
        for r1, r2 in zip(rows1, rows2):
            assert a.request(r1) == b.request(r2)
    # A changed block assignment is caught independently of the indexed producer.
    with sqlite3.connect(candidate) as db:
        ident, encoded = db.execute('SELECT job_id,input_json FROM authoring_job LIMIT 1').fetchone()
        value = json.loads(encoded)
        value['blocks'][0]['text'] += 'tampered'
        db.execute('UPDATE authoring_job SET input_json=? WHERE job_id=?', (json.dumps(value), ident))
    with pytest.raises(ValueError, match='Equivalence failure'):
        opt.verify_projection(optimized)


def test_verify_once_retains_both_hash_checks(tmp_path, monkeypatch):
    source = tmp_path/'authoring-source.sqlite'
    source.write_bytes(b'fixture')
    plan = {'files': []}
    row = {'document_id': 'fixture'}
    (tmp_path/'prepared-plan.json').write_text(json.dumps(plan))
    (tmp_path/'source.json').write_text(json.dumps({'sha256': build.sha(source)}))
    receipt = {'plan': plan, 'input_row': row, 'parser': {}, 'key': stages.structure_key(row, plan, {}),
               'files': stages.files_hashes(tmp_path)}
    (tmp_path/'structure-receipt.json').write_text(json.dumps(receipt))
    assert opt.verify_once(tmp_path, stages) == receipt
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='file/hash'):
        opt.verify_once(tmp_path, stages)
    # Even a self-consistent file manifest cannot hide a wrong source receipt.
    receipt['files'] = stages.files_hashes(tmp_path)
    (tmp_path/'structure-receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='SQLite'):
        opt.verify_once(tmp_path, stages)


def test_enable_restores_and_keys_differ():
    jobs, identity, verify = build.source_jobs, stages.parser_identity, stages.verify_structure
    with opt.enabled(ROOT) as feature:
        assert build.source_jobs is not jobs
        deps = stages.parser_identity(ROOT)
        assert deps['source_job_optimization'] == feature
        assert stages.structure_key({}, {}, deps) != stages.structure_key({}, {}, {})
    assert (build.source_jobs, stages.parser_identity, stages.verify_structure) == (jobs, identity, verify)


def test_full_structure_entrypoint_isolated_and_reusable(setup):
    args, raw, out = setup
    plan = build.inventory(raw, 'internal')
    with opt.enabled(ROOT):
        dependencies = stages.parser_identity(ROOT)
        folder, work = stages.structure(plan['files'][0], plan, out, dependencies, 120, lambda _: None)
        receipt = stages.verify_structure(folder)
        assert json.loads((folder/'source.json').read_text())['job_recipe'] == opt.RECIPE
        assert opt.verify_projection(folder)['status'] == 'PASSED'
        before = build.sha(folder/'authoring-source.sqlite')
        again, _ = stages.structure(plan['files'][0], plan, out, dependencies, 120, lambda _: None)
        assert again == folder and build.sha(again/'authoring-source.sqlite') == before
    assert stages.verify_structure(folder) == receipt
    assert not Fake.instances
