"""Regression for the field failure: real saved preparation -> real loader.inputs.

Small synthetic generation only. No Oracle calls and no field state rewriting.
"""
import ast
import copy
import inspect
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from test_reduced import inputs, Progress, HERE, loader, policy, resume, pub, exporter
from gold_io import Contract, digest
from lawrag.pipeline import oracle_deferred_import as deferred, oracle_query_package as pack
from lawrag.pipeline import oracle_migration as migration
from semantic_runtime import oracle_dp_io as io


@pytest.fixture
def prepared(tmp_path, inputs):
    root, _, original, paths, _ = inputs
    # Three real source tables, one source row, and an explicit bound selection.
    with sqlite3.connect(root / 'store.sqlite') as db:
        for kind, columns in io.COLUMNS.items():
            names = [('json' if c == 'SOURCE_JSON' else c.lower()) for c in columns if c != 'DATASET_VERSION']
            db.execute('CREATE TABLE ' + kind + '(' + ','.join(n + ' TEXT' for n in names) + ')')
        db.execute('INSERT INTO document VALUES(?,?,?,?)', ('d1', '문서', 'a' * 64, '{}'))
    cache = root / 'cache'; cache.mkdir()
    with sqlite3.connect(cache / 'receipt.sqlite') as db:
        db.execute('CREATE TABLE evidence(id TEXT)')
    loader.atomic(cache / 'receipt.json', {'sha256': loader.file_hash(cache / 'receipt.sqlite')})
    loader.atomic(root / 'glossary/manifest.json', {'dictionary_sha256': paths['glossary/dictionary.sqlite'], 'files': []})
    manifest = {'schema_version': 'term-source-generation-v2', 'generation_id': 'regression-fixture',
                'store_sha256': loader.file_hash(root / 'store.sqlite'),
                'counts': {'document': 1, 'source_unit': 0, 'source_block': 0},
                'glossary': {'bundle': 'glossary', 'dictionary': 'glossary/dictionary.sqlite',
                             'manifest_sha256': loader.file_hash(root / 'glossary/manifest.json'),
                             'cache': 'cache', 'cache_receipt': 'receipt.json',
                             'cache_receipt_sha256': loader.file_hash(cache / 'receipt.json')}}
    loader.atomic(root / 'navigation/manifest.json', {
        'index_sha256': paths['navigation/navigation.sqlite'],
        'source_store_sha256': manifest['store_sha256'], 'source_manifest_sha256': digest(manifest)})
    manifest['navigation'] = {'path': 'navigation', 'manifest_sha256': loader.file_hash(root / 'navigation/manifest.json')}
    loader.atomic(root / 'manifest.json', manifest)
    selection = root.parent / 'SEARCH_SELECTION'; selection.mkdir()
    loader.atomic(selection / 'generation.json', {'schema_version': 'filename-search-selection-v1',
        'generation_id': manifest['generation_id'],
        'store_sha256': manifest['store_sha256'], 'manifest_sha256': loader.file_hash(root / 'manifest.json'), 'excluded': []})
    root, manifest, items, files, selected = pack.immutable_inputs(root)
    source = pack.offline_source(root, manifest, items, selected)
    old_job = tmp_path / 'oracle-import-r2'; old_job.mkdir()
    binding, _ = migration.source_binding(root / 'store.sqlite'); binding['target_binding'] = 'fixture-target'
    (old_job / 'source/completed').mkdir(parents=True)
    loader.atomic(old_job / 'source/completed/state.json', {
        'binding': binding, 'pending': None, 'status': 'SOURCE_COMPLETE', 'tables': source['source_rows']})
    # Independent legacy producer files, not hashes calculated from the candidate.
    from lawrag.pipeline import oracle_query_navigation_publish as nav
    from semantic_runtime import navigation_match, structure_navigation, inherited_navigation, term_index, term_links
    modules = (pub, pack, nav, navigation_match, structure_navigation, inherited_navigation, term_index, term_links)
    r1 = HERE.parent / 'gold_fresh_1_20261102_r1/package'
    backend = HERE / 'package/vendor/02_BACKEND'
    components = {m.__name__: loader.file_hash(r1 / 'vendor/02_BACKEND' / Path(m.__file__).relative_to(backend)) for m in modules}
    executor = loader.file_hash(r1 / 'vendor/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py')
    body = {'binding': {'source': digest(source), 'files': files, 'components': components, 'executor': executor},
            'paths': paths, 'tables': original['tables']}
    loader.atomic(old_job / 'projection-descriptor-r7.json', dict(body, checksum=digest(body)))
    query = pack.query_manifest(root, source, paths, original['tables'], items)
    loader.atomic(old_job / 'full-state.json', {'identity': {'generation': str(root), 'target': 'fixture-target'},
                  'deferred': {'plan': {'source_release_id': digest(source), 'query_release_id': digest(query)}}})
    return old_job, root, files, source, query, paths


def test_actual_inputs_reuses_legacy_preparation_without_scan_or_rewrite(prepared, monkeypatch):
    old_job, root, files, source, query, paths = prepared
    before = {p: p.read_bytes() for p in old_job.rglob('*.json')}
    monkeypatch.setattr(pub, 'describe', lambda *a: pytest.fail('unexpected preparation rebuild'))
    monkeypatch.setattr(migration, 'source_batch', lambda *a: pytest.fail('unexpected source rescan'))
    actual = loader.inputs(old_job, Progress())
    assert actual == (root, files, source, query, paths)
    reduced = policy.plan(root, source, query, paths)
    assert reduced['projection_policy']['excluded_rows'] == 9
    # Exercise the handoff from the real recovered manifest into child creation.
    contract = Contract(HERE / 'package/contract.json')
    parent = old_job.parent / ('gold-shape-' + contract.sha256[:12]); parent.mkdir()
    child = parent.with_name(parent.name + policy.DIRECTORY_SUFFIX); child.mkdir()
    binding = {'code': loader.read(HERE / 'package/PARENTS.json')['parents'][0]['code_binding'],
               'contract': contract.sha256, 'generation': str(root), 'files': files,
               'source_release': digest(source), 'query_release': digest(query), 'database': [], 'objects': []}
    state = {'binding': binding, 'deadline': 9999999999, 'source': source['source_rows'],
             'query': {}, 'verify_source': {}, 'verify_query': {}, 'pending': None, 'status': 'WRITE_UNCONFIRMED'}
    loader.atomic(parent / 'state.json', state)
    new_binding = dict(binding, code=loader.verify_code(), query_release=digest(reduced), projection_policy=policy.POLICY)
    result = resume.prepare(loader, child, parent, new_binding, reduced, Progress())
    assert result['source'] == state['source'] and result['query'] == {} and result['deadline'] == state['deadline']
    assert loader.read(parent / 'state.json') == state
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_original_r4_reproduces_photographed_failure_against_same_preparation(prepared):
    old_job = prepared[0]
    r4 = HERE.parent / 'gold_fresh_1_reduced_20261103_r4/package'
    code = "from pathlib import Path; import run; run.inputs(Path(__import__('sys').argv[1]), type('P',(),{'emit':lambda *a,**k:None})())"
    result = subprocess.run([sys.executable, '-c', code, str(old_job)], cwd=r4, text=True, capture_output=True)
    assert result.returncode != 0 and 'RESUME_PREPARATION_BINDING_CHANGED: no automatic rebuild' in result.stderr
    assert 'RESUME_SOURCE_DESCRIPTOR_REUSED' in result.stdout


@pytest.mark.parametrize('change', ['component', 'executor', 'checksum', 'release', 'files', 'source_receipt', 'missing'])
def test_real_input_guards_still_refuse_changed_or_missing_preparation(prepared, monkeypatch, change):
    old_job = prepared[0]
    descriptor = old_job / 'projection-descriptor-r7.json'
    value = loader.read(descriptor)
    if change in {'component', 'executor', 'files', 'checksum'}:
        if change == 'component': value['binding']['components'][pub.__name__] = '0' * 64
        elif change == 'executor': value['binding']['executor'] = '0' * 64
        elif change == 'files': value['binding']['files']['store.sqlite'] = '0' * 64
        value['checksum'] = '0' * 64 if change == 'checksum' else digest({k: v for k, v in value.items() if k != 'checksum'})
        loader.atomic(descriptor, value)
    elif change == 'release':
        p = old_job / 'full-state.json'; v = loader.read(p); v['deferred']['plan']['query_release_id'] = '0' * 64; loader.atomic(p, v)
    elif change == 'source_receipt':
        p = old_job / 'source/completed/state.json'; v = loader.read(p); v['pending'] = {'unknown': True}; loader.atomic(p, v)
    else: descriptor.unlink()
    before = {p: p.read_bytes() for p in old_job.rglob('*.json')}
    monkeypatch.setattr(pub, 'describe', lambda *a: pytest.fail('unexpected rebuild'))
    with pytest.raises((io.DPError, loader.Stop, ValueError)):
        loader.inputs(old_job, Progress())
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_legacy_producer_exact_bytes_and_exporter_only_adds_preselect_skip():
    relative = 'vendor/02_BACKEND/lawrag/pipeline/oracle_query_publish.py'
    for version in ('gold_fresh_1_20261102_r1', 'gold_fresh_1_transport_20261103_r3'):
        assert (HERE / 'package' / relative).read_bytes() == (HERE.parent / version / 'package' / relative).read_bytes()
    legacy = ast.parse(inspect.getsource(pub._asset_rows))
    reduced = ast.parse(inspect.getsource(exporter._asset_rows))
    fn = reduced.body[0]; fn.args.kwonlyargs = []; fn.args.kw_defaults = []
    # The one changed condition is the only data-path difference.
    loop = next(n for n in fn.body if isinstance(n, ast.For))
    test = loop.body[1].test
    assert isinstance(test, ast.BoolOp) and ast.unparse(test.values[-1]) == 'table in excluded_tables'
    test.values.pop()
    assert ast.dump(legacy, include_attributes=False) == ast.dump(reduced, include_attributes=False)


@pytest.mark.parametrize('executor', [deferred.R8_DESCRIPTOR_EXECUTOR, deferred.R9_DESCRIPTOR_EXECUTOR, deferred.R10_DESCRIPTOR_EXECUTOR])
def test_already_supported_legacy_executors_still_reuse_exact_components(prepared, executor):
    old_job, root, files, source, query, paths = prepared
    p = old_job / 'projection-descriptor-r7.json'; value = loader.read(p)
    value['binding']['executor'] = executor
    value['checksum'] = digest({k: v for k, v in value.items() if k != 'checksum'})
    loader.atomic(p, value); before = p.read_bytes()
    assert loader.inputs(old_job, Progress()) == (root, files, source, query, paths)
    assert p.read_bytes() == before


def test_actual_attachment_in_fresh_process_reads_preparation_and_exports_reduced_rows(prepared, tmp_path):
    old_job = prepared[0]
    destination = tmp_path / 'extracted-code'
    with zipfile.ZipFile(HERE / 'DATAIKU_GOLD_FRESH_1_REDUCED_20261103_R4_1.zip') as z:
        z.extractall(destination)
    script = '''from pathlib import Path
import run, reduced_projection, reduced_export
run.verify_code()
root, files, source, original, paths = run.inputs(Path(__import__('sys').argv[1]), type('P', (), {'emit': lambda *a, **k: None})())
query = reduced_projection.plan(root, source, original, paths)
rows = [row for relative in paths for row in reduced_export.asset_rows(root/relative, relative, excluded_tables=reduced_projection.exclusions(query, relative))]
assert len(rows) == query['projection_policy']['retained_rows']
assert not any(row['kind'] in query['projection_policy']['excluded_tables'] for row in rows)
print('ATTACHMENT_REAL_INPUTS_AND_EXPORT_PASS')
'''
    result = subprocess.run([sys.executable, '-c', script, str(old_job)], cwd=destination, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'PROJECTION_PREPARATION_REUSED' in result.stdout
    assert 'ATTACHMENT_REAL_INPUTS_AND_EXPORT_PASS' in result.stdout
