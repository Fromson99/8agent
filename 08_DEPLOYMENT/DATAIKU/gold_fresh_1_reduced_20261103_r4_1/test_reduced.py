"""Small contract fixtures only: no Oracle, performance benchmark, or corpus scan."""
import ast
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import types
import zipfile

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'package'))
import run as loader
import reduced_projection as policy
import reduced_resume as resume
import reduced_export as exporter
from gold_io import Contract, Stop, digest, canonical
from lawrag.pipeline import oracle_query_publish as pub


class Progress:
    def __init__(self): self.events = []
    def emit(self, *a, **kw): self.events.append((a, kw))
    def set(self, *a, **kw): self.events.append((a, kw))


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / 'generation'
    nav = 'navigation/navigation.sqlite'; dictionary = 'glossary/dictionary.sqlite'
    for relative in (nav, dictionary): (root / relative).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / nav) as db:
        db.executescript('''CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT);
          CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
          CREATE TABLE occurrence_keys(term_key INTEGER,source_key INTEGER,PRIMARY KEY(term_key,source_key)) WITHOUT ROWID;
          INSERT INTO term VALUES('t1','{}'),('t2','{}');
          INSERT INTO source VALUES('s1','d1','{}'),('s2','d2','{}');
          INSERT INTO occurrence_keys VALUES(1,1),(1,2),(2,2);''')
        db.execute(policy.VIEWS['occurrence'])
    with sqlite3.connect(root / dictionary) as db:
        db.executescript('''CREATE TABLE entry(id TEXT PRIMARY KEY,key TEXT,label TEXT,definition TEXT,source TEXT,provenance TEXT);
          CREATE TABLE occurrence(key TEXT,document_id TEXT,source_text TEXT);
          CREATE TABLE corpus_document(document_id TEXT PRIMARY KEY,name TEXT,source_sha256 TEXT);
          CREATE TABLE corpus_definition(id TEXT PRIMARY KEY,key TEXT,document_id TEXT,source_text TEXT,
             scope_hint TEXT,location TEXT,reference_hints TEXT);
          INSERT INTO entry VALUES('e1','k','한글','정의','corpus_definition','{}'),('e2','k','같은 말','','other','{}');
          INSERT INTO occurrence VALUES('k','d1','한글 원문'),('k','d2',NULL);
          INSERT INTO corpus_document VALUES('d1','문서1','h1'),('d2','문서2','h2');
          INSERT INTO corpus_definition VALUES('e1','k','d1','정의 원문','[]','[]','[]');
          CREATE VIRTUAL TABLE words USING fts5(text);
          INSERT INTO words VALUES('alpha alpha 한글'),('beta 한글');''')
        for name in ('entry_corpus_link', 'entry_definition_link'): db.execute(policy.VIEWS[name])
    source = {'source_manifest': {'navigation': {'path': 'navigation'},
                                 'glossary': {'dictionary': dictionary}}, 'dataset_version': 'd' * 64}
    tables = {}; rows = {}
    paths = {n: loader.file_hash(root / n) for n in (nav, dictionary)}
    for relative in paths:
        tables.update(pub.asset_schema(root / relative, relative))
        rows[relative] = list(pub.asset_rows(root / relative, relative))
        for row in rows[relative]:
            state = tables.setdefault(row['kind'], {'asset': relative, 'rows': 0, 'chain': '0' * 64})
            state['rows'] += 1
            state['chain'] = digest([state['chain'], row['row_id'], row['sha256']])
            pub._column_shapes(state, row['value'])
    query = {'schema_version': 'oracle-query-release-v1', 'status': 'COMPLETE',
             'source_release_id': digest(source), 'dataset_version': source['dataset_version'],
             'assets': paths, 'tables': tables}
    return root, source, query, paths, rows


def test_policy_removes_only_three_exact_kinds_and_preserves_every_retained_value(inputs):
    root, source, old, paths, rows = inputs
    before = copy.deepcopy(old)
    new = policy.plan(root, source, old, paths)
    excluded = new['projection_policy']['excluded_tables']
    assert {v['table'] for v in excluded.values()} == {'occurrence_keys', 'entry_corpus_link', 'entry_definition_link'}
    assert old == before and digest(old) != digest(new)
    for relative, original in rows.items():
        actual = list(exporter.asset_rows(root / relative, relative, excluded_tables=policy.exclusions(new, relative)))
        assert actual == [r for r in original if r['kind'] not in excluded]
        assert all(new['tables'][k] == old['tables'][k] for k in new['tables'])
        assert loader.file_hash(root / relative) == paths[relative]
    p = new['projection_policy']
    assert p['original_rows'] == p['retained_rows'] + p['excluded_rows']
    assert p['excluded_rows'] == 9
    assert any(k.endswith('words_posting') for k in new['tables'])


def test_excluded_views_are_skipped_before_select_and_other_files_are_untouched(inputs, monkeypatch):
    root, source, old, paths, rows = inputs
    new = policy.plan(root, source, old, paths)
    connect = sqlite3.connect; seen = []
    def traced(*args, **kw):
        db = connect(*args, **kw); db.set_trace_callback(seen.append); return db
    monkeypatch.setattr(sqlite3, 'connect', traced)
    for relative in paths:
        list(exporter.asset_rows(root / relative, relative, excluded_tables=policy.exclusions(new, relative)))
    assert not any('FROM "' + name + '"' in s for s in seen for name in ('occurrence_keys', 'entry_corpus_link', 'entry_definition_link'))
    assert any('FROM "occurrence"' in s for s in seen)
    assert policy.exclusions(new, 'unrelated/dictionary.sqlite') == ()


@pytest.mark.parametrize('change', ['view', 'column', 'table', 'role', 'count', 'already_reduced'])
def test_changed_schema_or_prepared_manifest_never_silently_drops_data(inputs, change):
    root, source, old, paths, _ = inputs
    if change == 'view':
        with sqlite3.connect(root / 'glossary/dictionary.sqlite') as db:
            db.execute('DROP VIEW entry_corpus_link')
            db.execute(policy.VIEWS['entry_corpus_link'] + ' WHERE 1=0')
    elif change == 'column':
        old['tables'][pub._kind('navigation/navigation.sqlite', 'occurrence_keys')]['columns']['extra'] = {}
    elif change == 'table': del old['tables'][pub._kind('glossary/dictionary.sqlite', 'entry')]
    elif change == 'role': source['source_manifest']['glossary']['dictionary'] = 'another.sqlite'
    elif change == 'count': next(iter(old['tables'].values()))['rows'] = -1
    else: old['projection_policy'] = {}
    with pytest.raises(Stop): policy.plan(root, source, old, paths)


def test_original_source_export_cannot_be_excluded():
    with pytest.raises(Exception, match='SOURCE_EXCLUSION_FORBIDDEN'):
        list(exporter.projected_rows(Path('unused'), 'store.sqlite', {}, excluded_tables=('document',)))


def parent_state(tmp_path, inputs, parent_index=0):
    root, source, old, paths, _ = inputs
    new = policy.plan(root, source, old, paths)
    contract = Contract(HERE / 'package/contract.json')
    parents = loader.read(HERE / 'package/PARENTS.json')['parents']
    identity = [{'LOGIN_USER': 'PIDD2APP', 'DB_NAME': 'MOCK', 'SERVICE_NAME': 'MOCK'}]
    objects = [{'OWNER': 'SIDDS', 'OBJECT_NAME': 'MOCK_1', 'OBJECT_ID': 1, 'DATA_OBJECT_ID': 1}]
    binding = {'code': parents[parent_index]['code_binding'], 'contract': contract.sha256,
               'database': identity, 'objects': objects, 'generation': str(root), 'files': paths,
               'source_release': digest(source), 'query_release': digest(old)}
    state = {'binding': binding, 'status': 'WRITE_UNCONFIRMED', 'deadline': 9999999999,
             'source': {'document': {'rows': 12, 'cursor': ['d1'], 'chain': 'x' * 64}},
             'query': {'navigation/navigation.sqlite': {'rows': 1}}, 'verify_source': {}, 'verify_query': {},
             'pending': {'table': 'SRCH_ROW', 'rows': 1, 'section': 'query', 'slot': 'navigation/navigation.sqlite',
                         'sha256': 'uncertain', 'verify_only': False, 'next': {'rows': 2}},
             'last_error': {'codes': ['ORA-01654']}}
    parent = tmp_path / ('gold-shape-' + contract.sha256[:12]); parent.mkdir()
    child = parent.with_name(parent.name + policy.DIRECTORY_SUFFIX); child.mkdir()
    loader.atomic(parent / 'state.json', state)
    binding = {**binding, 'code': loader.verify_code(), 'query_release': digest(new), 'projection_policy': policy.POLICY}
    return parent, child, state, binding, new


@pytest.mark.parametrize('parent_index', [0, 1])
def test_fork_keeps_original_bytes_deadline_and_source_but_never_reuses_search_offset(tmp_path, inputs, parent_index):
    parent, child, state, binding, new = parent_state(tmp_path, inputs, parent_index)
    raw = (parent / 'state.json').read_bytes()
    result = resume.prepare(loader, child, parent, binding, new, Progress())
    assert (parent / 'state.json').read_bytes() == raw
    assert result['source'] == state['source'] and result['deadline'] == state['deadline']
    assert result['query'] == result['verify_query'] == result['verify_source'] == {}
    assert result['pending'] is None and result['parent_pending_preserved']
    assert loader.read(child / ('parent-state-' + digest(state) + '.json')) == state
    assert resume.prepare(loader, child, parent, binding, new, Progress()) == result


@pytest.mark.parametrize('change', ['files', 'database', 'objects', 'query_release', 'code', 'deadline'])
def test_fork_refuses_stale_input_or_unregistered_parent_without_new_state(tmp_path, inputs, change):
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    if change == 'deadline': state['deadline'] = 1
    else: state['binding'][change] = 'changed'
    loader.atomic(parent / 'state.json', state)
    before = (parent / 'state.json').read_bytes()
    with pytest.raises(Stop): resume.prepare(loader, child, parent, binding, new, Progress())
    assert not (child / 'state.json').exists() and (parent / 'state.json').read_bytes() == before


def test_restart_is_refused_if_already_loaded_prefix_cancels_row_saving(tmp_path, inputs):
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    state['query'] = {'some': {'rows': new['projection_policy']['excluded_rows']}}
    loader.atomic(parent / 'state.json', state)
    with pytest.raises(Stop, match='NOT_FEWER_ROWS'): resume.prepare(loader, child, parent, binding, new, Progress())
    assert not (child / 'state.json').exists()


@pytest.mark.parametrize('which', ['parent', 'plan', 'snapshot'])
def test_resume_detects_parent_or_plan_or_evidence_drift(tmp_path, inputs, which):
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    resume.prepare(loader, child, parent, binding, new, Progress())
    if which == 'parent': target = parent / 'state.json'
    elif which == 'plan': target = child / 'query-reduced.json'
    else: target = child / ('parent-state-' + digest(state) + '.json')
    value = loader.read(target); value['changed'] = True; loader.atomic(target, value)
    before = (child / 'state.json').read_bytes()
    with pytest.raises(Stop): resume.prepare(loader, child, parent, binding, new, Progress())
    assert (child / 'state.json').read_bytes() == before


@pytest.mark.parametrize('outcome', ['saved', 'missing', 'unknown'])
def test_uncertain_source_is_verified_before_advancing_never_blindly_inserted(tmp_path, inputs, monkeypatch, outcome):
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    rows = [{'dummy': '원문'}]
    marker = {'table': 'DOC_VER', 'rows': 1, 'sha256': digest(rows), 'verify_only': False,
              'section': 'source', 'slot': 'document', 'next': {'rows': 13}}
    state['pending'] = marker; loader.atomic(parent / 'state.json', state)
    resume.prepare(loader, child, parent, binding, new, Progress())
    calls = []
    def block(sql, binds, rollback=False):
        calls.append((sql, rollback))
        if outcome != 'saved': raise RuntimeError('ORA-20042' if outcome == 'missing' else 'ORA-03113')
    contract = types.SimpleNamespace(batch=lambda k, r, verify_only=False: ('VERIFY' if verify_only else 'INSERT', []))
    job = loader.Job(types.SimpleNamespace(block=block), contract, child, binding, Progress())
    monkeypatch.setattr(job, 'guard', lambda: None)
    if outcome == 'saved':
        job.batch('DOC_VER', rows, {'rows': 13}, 'source', 'document')
        assert job.state['pending'] is None and job.state['source']['document']['rows'] == 13
    else:
        with pytest.raises(Stop, match='RECONCILIATION'): job.batch('DOC_VER', rows, {'rows': 13}, 'source', 'document')
        assert job.state['pending'] == marker and job.state['source']['document']['rows'] == 12
    assert calls == [('VERIFY', True)] and loader.read(parent / 'state.json') == state


def test_real_load_query_uses_filtered_stream_and_resumes_without_duplicate_batch(tmp_path, inputs, monkeypatch):
    root, source, old, paths, rows = inputs
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    resume.prepare(loader, child, parent, binding, new, Progress())
    from lawrag.pipeline import oracle_query_navigation_publish as native
    monkeypatch.setattr(native, 'records', lambda *a: iter(()))
    total = new['projection_policy']['retained_rows']; calls = []
    class DB:
        def block(self, sql, binds, rollback=False):
            payload = json.loads(binds[0][1]); calls.append((payload, rollback)); return 0.1
        def query(self, sql): return [{'N': total}]
    job = loader.Job(DB(), Contract(HERE / 'package/contract.json'), child, binding, Progress())
    monkeypatch.setattr(job, 'guard', lambda: None)
    loader.load_query(job, root, paths, source, new, paths)
    assert sum(len(p) for p, _ in calls) == total
    excluded = set(new['projection_policy']['excluded_tables'])
    assert all(p['c1'] not in excluded for values, _ in calls for p in values)
    before = len(calls)
    loader.load_query(job, root, paths, source, new, paths)
    assert len(calls) == before
    loader.load_query(job, root, paths, source, new, paths, verify_only=True)
    assert sum(len(p) for p, rollback in calls if rollback) == total


@pytest.mark.parametrize('result', ['saved', 'missing', 'conflict', 'unknown'])
def test_reduced_query_lost_response_resumes_by_exact_verification(tmp_path, inputs, monkeypatch, result):
    root, source, old, paths, _ = inputs
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    resume.prepare(loader, child, parent, binding, new, Progress())
    from lawrag.pipeline import oracle_query_navigation_publish as native
    monkeypatch.setattr(native, 'records', lambda *a: iter(()))
    inserted = {}; calls = []; lost = [False]
    class DB:
        def block(self, sql, binds, rollback=False):
            values = json.loads(binds[0][1]); calls.append(rollback)
            if rollback:
                if result == 'unknown': raise RuntimeError('ORA-03113')
                if any(inserted.get(tuple(v[f'c{i}'] for i in range(3))) != v for v in values):
                    raise RuntimeError('ORA-20042')
            else:
                for v in values:
                    key = tuple(v[f'c{i}'] for i in range(3))
                    if result != 'missing': inserted[key] = copy.deepcopy(v)
                if not lost[0]:
                    lost[0] = True
                    if result == 'conflict': next(iter(inserted.values()))['c8'] = 'changed'
                    raise RuntimeError('ORA-03113')
            return 0.1
        def query(self, sql): return [{'N': len(inserted)}]
    db = DB(); contract = Contract(HERE / 'package/contract.json')
    job = loader.Job(db, contract, child, binding, Progress()); monkeypatch.setattr(job, 'guard', lambda: None)
    with pytest.raises(RuntimeError, match='ORA-03113'): loader.load_query(job, root, paths, source, new, paths)
    assert job.state['status'] == 'WRITE_UNCONFIRMED' and job.state['pending']
    job = loader.Job(db, contract, child, binding, Progress()); monkeypatch.setattr(job, 'guard', lambda: None)
    if result == 'saved':
        loader.load_query(job, root, paths, source, new, paths)
        assert job.state['pending'] is None and len(inserted) == new['projection_policy']['retained_rows']
        assert calls[:2] == [False, True]
    else:
        with pytest.raises(Stop, match='RECONCILIATION'): loader.load_query(job, root, paths, source, new, paths)
        assert calls == [False, True] and job.state['pending']
    assert loader.read(parent / 'state.json') == state


def test_progress_uses_new_manifest_total_and_rejects_changed_plan(tmp_path, inputs):
    from progress_display import Display
    root, source, old, paths, _ = inputs
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    (root / 'manifest.json').write_text(json.dumps({'counts': {'document': 2, 'source_unit': 3, 'source_block': 4}}))
    binding['files'] = {**paths, 'manifest.json': loader.file_hash(root / 'manifest.json')}
    state['binding']['files'] = binding['files']; loader.atomic(parent / 'state.json', state)
    current = resume.prepare(loader, child, parent, binding, new, Progress())
    old_job = tmp_path / 'old'; old_job.mkdir()
    descriptor = {'binding': {'source': binding['source_release'], 'files': binding['files']}, 'tables': old['tables']}
    loader.atomic(old_job / 'projection-descriptor-r7.json', {**descriptor, 'checksum': digest(descriptor)})
    display = Display(old_job, binding['contract'], 'load')
    assert display.state_path == child / 'state.json'
    assert display.planned_totals(current) == {'source': 9, 'query': new['projection_policy']['retained_rows']}
    new['tables'][next(iter(new['tables']))]['rows'] += 1
    loader.atomic(child / 'query-reduced.json', new)
    with pytest.raises(ValueError): Display(old_job, binding['contract'], 'load').planned_totals(current)


def test_read_consumers_get_same_navigation_and_definition_from_retained_tables(inputs):
    root, source, old, paths, original = inputs
    new = policy.plan(root, source, old, paths)
    from semantic_runtime.term_index import OccurrenceMap
    from semantic_runtime.full_glossary_connections import ConnectionReader
    for relative in paths:
        native = sqlite3.connect(root / relative); native.row_factory = sqlite3.Row
        restored = sqlite3.connect(':memory:'); restored.row_factory = sqlite3.Row
        for spec in new['tables'].values():
            if spec.get('asset') == relative and 'columns' in spec:
                cols = ','.join('"' + n + '"' for n in spec['columns'])
                restored.execute('CREATE TABLE "' + spec['table'] + '"(' + cols + ')')
        for row in exporter.asset_rows(root / relative, relative, excluded_tables=policy.exclusions(new, relative)):
            spec = new['tables'][row['kind']]
            if 'columns' not in spec: continue
            cols = list(spec['columns']); value = row['value']
            restored.execute('INSERT INTO "' + spec['table'] + '" VALUES(' + ','.join('?' for _ in cols) + ')', [value[c] for c in cols])
        if relative.startswith('navigation/'):
            assert OccurrenceMap(restored)['s1'] == OccurrenceMap(native)['s1'] == {'t1'}
            assert OccurrenceMap(restored)['s2'] == OccurrenceMap(native)['s2'] == {'t1', 't2'}
        else:
            a = ConnectionReader({'dictionary': native}, None)
            b = ConnectionReader({'dictionary': restored}, None)
            assert a._definitions('dictionary', 'e1', 5) == b._definitions('dictionary', 'e1', 5)
            assert a._definitions('dictionary', 'e2', 5) == b._definitions('dictionary', 'e2', 5) == []
        native.close(); restored.close()


def test_current_main_oracle_reader_compiles_retained_tables_with_scope_and_rejects_removed(inputs):
    root, source, old, paths, _ = inputs
    new = policy.plan(root, source, old, paths)
    active = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    manifest = json.loads((ROOT / active['manifest_path']).read_text())
    relative = '02_BACKEND/semantic_runtime/oracle_query_db.py'
    path = ROOT / manifest['code_root'] / relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files'][relative]
    spec = importlib.util.spec_from_file_location('semantic_runtime._r4_reader_check', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    calls = []
    def query(sql, binds, limit): calls.append((sql, binds)); return []
    request = types.SimpleNamespace(sql=types.SimpleNamespace(query=query), release_id=digest(new),
                                   sources=types.SimpleNamespace(allowed={'d1'}),
                                   records=types.SimpleNamespace(manifest=new))
    db = module.Connection(request, 'navigation/navigation.sqlite')
    assert list(db.execute('SELECT term_id FROM occurrence WHERE source_id=?', ('s1',))) == []
    sql, binds = calls[-1]
    assert 'JSON_TABLE' in sql and 'DOCUMENT_ID' in sql
    assert any(v == digest(new) for _, v, _ in binds)
    assert any(v == '["d1"]' for _, v, _ in binds)
    for asset, table in [('navigation/navigation.sqlite', 'occurrence_keys'),
                         ('glossary/dictionary.sqlite', 'entry_corpus_link'),
                         ('glossary/dictionary.sqlite', 'entry_definition_link')]:
        with pytest.raises(Exception, match='undeclared'):
            list(module.Connection(request, asset).execute('SELECT * FROM ' + table))


@pytest.mark.parametrize('gate_failure', [False, True])
def test_actual_pipeline_entry_runs_plan_then_load_only_and_preserves_parent(tmp_path, inputs, monkeypatch, gate_failure):
    import pandas as pd
    import pipeline_entry, error_diagnostics
    root, source, old, paths, _ = inputs
    parent, child, state, binding, new = parent_state(tmp_path, inputs)
    raw = (parent / 'state.json').read_bytes()
    old_job = tmp_path / 'old'; old_job.mkdir()
    events = []
    class Executor:
        def query_to_df(self, sql, **kw):
            if kw.get('pre_queries'):
                block = kw['pre_queries'][0]
                assert 'TRANSPORT_ROUNDTRIP_MISMATCH' in block and kw['post_queries'] == ['ROLLBACK']
                events.append('codec')
                if gate_failure: raise RuntimeError('ORA-06550')
                return pd.DataFrame([{'OK': 1}])
            return pd.DataFrame(binding['database'] if 'SYS_CONTEXT' in sql else binding['objects'])
    monkeypatch.setitem(sys.modules, 'dataiku', types.SimpleNamespace(SQLExecutor2=lambda **kw: Executor()))
    monkeypatch.setattr(Contract, 'create', lambda *a, **kw: events.append(('schema', kw['allow_create'])))
    monkeypatch.setattr(loader, 'object_binding', lambda *a: binding['objects'])
    monkeypatch.setattr(loader, 'inputs', lambda *a: (root, paths, source, old, paths))
    def sources(job, *a, **kw):
        assert job.state['source'] == state['source']; events.append(('source', kw['verify_only']))
    monkeypatch.setattr(loader, 'load_sources', sources)
    monkeypatch.setattr(loader, 'load_query', lambda job, root, files, source, query, paths, **kw:
                        events.append(('query', query == new, kw['verify_only'])))
    monkeypatch.setattr(loader, 'publish', lambda *a: pytest.fail('automatic publish'))
    monkeypatch.setattr(error_diagnostics, 'install', lambda *a: lambda *a, **kw: None)
    monkeypatch.setenv('G19_OLD_JOB_DIR', str(old_job)); monkeypatch.setenv('G19_DIAGNOSTIC_FILE', str(tmp_path / 'errors.jsonl'))
    monkeypatch.setattr(sys, 'argv', ['pipeline_entry.py', 'load'])
    monkeypatch.setattr(loader.Database, 'block', loader.Database.block)
    monkeypatch.setattr(loader.Database, '_g8_transport', False, raising=False)
    assert pipeline_entry.main() == (1 if gate_failure else 0)
    assert (parent / 'state.json').read_bytes() == raw
    if gate_failure: assert not (child / 'state.json').exists()
    else:
        assert loader.read(child / 'state.json')['status'] == 'LOADED_UNVERIFIED'
        assert events == [('schema', False), 'codec', ('source', False), ('query', True, False)]


def test_archive_integrity_original_dml_and_no_nested_or_javascript_files():
    archive = HERE / 'DATAIKU_GOLD_FRESH_1_REDUCED_20261103_R4_1.zip'
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist()) == set(manifest['files']) | {'CODE_MANIFEST.json'}
        for name, sha in manifest['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == sha
            assert Path(name).suffix.lower() not in {'.zip', '.js', '.jsx', '.mjs', '.cjs', '.pyc'}
    r3 = HERE.parent / 'gold_fresh_1_transport_20261103_r3/package'
    for name in ('contract.json', 'gold_io.py', 'jdbc_transport.py', 'transport_gate.py'):
        assert (HERE / 'package' / name).read_bytes() == (r3 / name).read_bytes()
    for name in ('run.py', 'reduced_projection.py', 'reduced_resume.py', 'progress_display.py'):
        ast.parse((HERE / 'package' / name).read_text(), feature_version=(3, 9))


@pytest.mark.parametrize('failed', [False, True])
def test_complete_execution_txt_bootstrap_runs_only_load(tmp_path, monkeypatch, failed):
    import os, subprocess, tempfile
    text = (HERE / 'DATAIKU_GOLD_FRESH_1_RUN_R4_1.txt').read_text()
    name = 'DATAIKU_GOLD_FRESH_1_REDUCED_20261103_R4_1.zip'
    raw = (HERE / name).read_bytes()
    folder = types.SimpleNamespace(list_paths_in_partition=lambda: [name], get_download_stream=lambda p: io.BytesIO(raw))
    monkeypatch.setitem(sys.modules, 'dataiku', types.SimpleNamespace(Folder=lambda n: folder))
    monkeypatch.setitem(sys.modules, 'IPython', types.ModuleType('IPython'))
    monkeypatch.setitem(sys.modules, 'IPython.display', types.SimpleNamespace(clear_output=lambda **kw: None))
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path)); monkeypatch.chdir(tmp_path)
    actions = []
    def spawn(args, **kw):
        actions.append(args[-1])
        read_fd, write_fd = os.pipe(); os.close(write_fd)
        return types.SimpleNamespace(stdout=os.fdopen(read_fd, 'rb'), wait=lambda **kw: int(failed), poll=lambda: int(failed))
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    if failed:
        with pytest.raises(RuntimeError): exec(compile(text, 'attachment.txt', 'exec'), {})
    else: exec(compile(text, 'attachment.txt', 'exec'), {})
    assert actions == ['load']
