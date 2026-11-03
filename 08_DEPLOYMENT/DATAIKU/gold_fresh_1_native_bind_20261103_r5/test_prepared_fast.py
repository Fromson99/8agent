import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS
import pytest
HERE=Path(__file__).resolve().parent
PACKAGE=Path(os.environ.get('R5_PACKAGE_DIR', HERE/'package'))
sys.path.insert(0,str(PACKAGE))
import run_full as loader
import reduced_projection as policy
import reduced_export as exporter
import fast_loader as fast
import fast_inputs
from gold_io import Contract,digest
from lawrag.pipeline import oracle_query_publish as pub, oracle_query_package as pack, oracle_migration as migration
from semantic_runtime import oracle_dp_io as io

class Progress:
    def emit(self,*a,**k):pass
    def set(self,*a,**k):pass


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
        db.execute('CREATE TABLE definition(id TEXT,document_id TEXT,json TEXT)')
        for sid,did in [('s1','d1'),('s2','d2')]:
            db.execute('UPDATE source SET json=? WHERE id=?',(json.dumps({'id':sid,'document_id':did,'unit_id':None,'heading':'제목'}),sid))
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
    from lawrag.pipeline.oracle_query_navigation_publish import records
    for relative in paths:
        for row in records(root/relative,relative,source):
            spec=original['tables'].setdefault(row['kind'],{'asset':relative,'rows':0,'chain':'0'*64})
            spec['rows']+=1;spec['chain']=digest([spec['chain'],row['row_id'],row['sha256']])
            pub._column_shapes(spec,row['value'])
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
    backend = Path(pub.__file__).parents[2]
    components = {m.__name__: loader.file_hash(r1 / 'vendor/02_BACKEND' / Path(m.__file__).relative_to(backend)) for m in modules}
    executor = loader.file_hash(r1 / 'vendor/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py')
    body = {'binding': {'source': digest(source), 'files': files, 'components': components, 'executor': executor},
            'paths': paths, 'tables': original['tables']}
    loader.atomic(old_job / 'projection-descriptor-r7.json', dict(body, checksum=digest(body)))
    query = pack.query_manifest(root, source, paths, original['tables'], items)
    loader.atomic(old_job / 'full-state.json', {'identity': {'generation': str(root), 'target': 'fixture-target'},
                  'deferred': {'plan': {'source_release_id': digest(source), 'query_release_id': digest(query)}}})
    return old_job, root, files, source, query, paths


@pytest.mark.parametrize('mode',['full','reduced'])
def test_real_prepared_inputs_and_insert_only_end_to_end(prepared,tmp_path,monkeypatch,mode):
    old_job,root,files,source,original,paths=prepared
    contract=fast.Contract(HERE/'package/contract.json')
    parent=old_job.parent/('gold-shape-'+contract.sha256[:12]);parent.mkdir()
    directory=parent
    parents=loader.read(HERE/'package/NATIVE_PARENTS.json')['parents']
    query=policy.plan(root,source,original,paths) if mode=='reduced' else original
    if mode=='reduced':directory=parent.with_name(parent.name+'-reduced-r4');directory.mkdir()
    binding={'code':parents[2 if mode=='reduced' else 1]['code_binding'],'contract':contract.sha256,
             'generation':str(root),'files':files,'source_release':digest(source),'query_release':digest(query),
             'database':[{'LOGIN_USER':'PIDD2APP'}],'objects':[{'OBJECT_ID':i} for i in range(17)]}
    if mode=='reduced':binding['projection_policy']=policy.POLICY;loader.atomic(directory/'query-reduced.json',query)
    state={'binding':binding,'deadline':0,'source':{},'query':{},'verify_source':{},'verify_query':{},'pending':None,'status':'NEW'}
    loader.atomic(directory/'state.json',state)
    sha=io.file_sha
    def metadata_only(path):
        if str(path).endswith('.sqlite'):pytest.fail('runtime must not hash full SQLite input')
        return sha(path)
    monkeypatch.setattr(io,'file_sha',metadata_only)
    # Every module's existing imported alias for large-file hashing is trapped too.
    from semantic_runtime import oracle_dp_assets as assets
    monkeypatch.setattr(assets,'file_sha',metadata_only)
    monkeypatch.setattr(pack,'immutable_inputs',lambda *a:pytest.fail('full immutable scan'))
    monkeypatch.setattr(migration,'source_counts',lambda *a:pytest.fail('source count scan'))
    actual=fast_inputs.inputs(loader,old_job,directory,state,Progress())
    assert actual==(root,files,source,query,paths)
    assert fast_inputs.inputs(loader,old_job,directory,state,Progress())==actual
    statements=[]
    class DB:
        def __init__(self,*a):pass
        def query(self,sql,**kw):
            if 'ALL_OBJECTS' in sql:return binding['objects']
            if 'SYS_CONTEXT' in sql:return binding['database']
            pytest.fail('unexpected runtime readback: '+sql)
        def block(self,sql,binds=(),**kw):
            assert all(x not in sql for x in ['COUNT(', 'DBMS_LOB.COMPARE', 'NOT EXISTS'])
            assert kw=={'transaction_managed':True}
            statements.append((sql,binds));return 0.01
        def close(self):pass
    monkeypatch.setattr(loader,'Database',DB)
    monkeypatch.setattr(loader,'resource_check',lambda p:None)
    monkeypatch.setattr(Contract,'create',lambda *a,**k:pytest.fail('17-table deep preflight'))
    monkeypatch.setitem(sys.modules,'dataiku',NS(SQLExecutor2=lambda **kw:None))
    fast.run('load',old_job,mode,directory)
    saved=loader.read(directory/'state.json')
    assert saved['status']=='LOADED_INSERT_ACK' and saved['full_values_verified'] is False
    assert saved['source']['document']['rows']==1
    count=len(statements)
    fast.run('load',old_job,mode,directory)
    assert len(statements)==count  # already completed rows do not get re-read or re-inserted
    fast.run('publish',old_job,mode,directory)
    assert len(statements)==count+3
    assert loader.read(directory/'state.json')['status']=='SOURCE_QUERY_PUBLISHED'
    fast.run('publish',old_job,mode,directory)
    assert len(statements)==count+3
    assert loader.read(directory/'state.json')['binding']['query_release']==binding['query_release']


def test_source_search_rows_identical_without_chain_recalculation(prepared,monkeypatch):
    from fast_export import source_records
    old_job,root,files,source,query,paths=prepared
    expected=list(pub.source_records(root/'store.sqlite',source))
    monkeypatch.setattr(migration,'extend_chain',lambda *a:pytest.fail('redundant rolling chain'))
    assert list(source_records(root/'store.sqlite',source))==expected
