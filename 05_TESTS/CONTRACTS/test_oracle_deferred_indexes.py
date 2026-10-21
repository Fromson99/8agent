"""Explicit development import policy; real delivered entry, synthetic SQL only."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from test_oracle_query_schema import SchemaOracle
from lawrag.pipeline import oracle_full_package as pack, oracle_query_publish as publisher
from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q

ROOT = Path(__file__).resolve().parents[2]
D = ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r3'
N = 'LEGAL_ORACLE_EXISTING_ZIP_20261020_R3'
INDEXES = publisher.DEFERABLE_LOOKUP_INDEXES


def test_strict_default_and_only_named_missing_indexes_deferred(tmp_path):
    remote = SchemaOracle()
    remote.created = {s.split()[2].split('.')[1] for s in q.DDL} - INDEXES
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='test')
    assert set(publisher.schema(sql)['missing']) == INDEXES
    result = publisher.schema(sql, allow_missing_lookup_indexes=True)
    assert result['status'] == 'READY' and set(result['deferred_indexes']) == INDEXES
    remote.created.remove('LEGAL_RAG_QUERY_ROW_A')
    assert publisher.schema(sql, allow_missing_lookup_indexes=True)['missing'] == ['LEGAL_RAG_QUERY_ROW_A']
    assert not remote.writes


@pytest.mark.parametrize('damage', ['primary', 'foreign', 'json', 'column', 'index', 'disabled'])
def test_optin_still_rejects_incompatible_objects(tmp_path, damage):
    remote = SchemaOracle()
    remote.created = {s.split()[2].split('.')[1] for s in q.DDL} - INDEXES
    if damage == 'primary': remote.primary['LEGAL_RAG_QUERY_ROW_A'] = ['ROW_ID']
    if damage == 'foreign': remote.references = []
    if damage == 'json': remote.checks['LEGAL_RAG_QUERY_ROW_A'] = []
    if damage == 'column': remote.columns['LEGAL_RAG_QUERY_ROW_A'].pop()
    original = remote.request
    if damage == 'index':
        remote.created.add('LEGAL_Q_ROW_LOOKUP')
    def request(*args, **kwargs):
        result = original(*args, **kwargs)
        rows = result['items'][0]['resultSet']['items']
        statement = kwargs['json']['statementText']
        if damage == 'index' and 'ALL_IND_COLUMNS' in statement and rows:
            rows[-1]['COLUMN_NAME'] = 'WRONG'
        if damage == 'disabled' and 'SELECT CONSTRAINT_TYPE' in statement:
            rows[0]['STATUS'] = 'DISABLED'
        return result
    remote.request = request
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='test')
    with pytest.raises(io.DPError, match='QUERY_DDL'):
        publisher.schema(sql, allow_missing_lookup_indexes=True)
    assert not remote.writes


def test_import_without_indexes_preserves_dedup_readback_and_resume(full, tmp_path):
    full[3].created -= INDEXES
    def run(action, allow=True):
        return pack.import_generation(full[0], full[4], target_binding='fixture',
            directory=tmp_path/'job', action=action, allow_missing_lookup_indexes=allow)
    with pytest.raises(io.DPError, match='QUERY_SCHEMA'): run('check', False)
    assert not full[1].writes and not full[2].writes
    assert set(run('check')['deferred_indexes']) == INDEXES
    result = run('publish')
    assert result['status'] == 'FULL_DATA_VERIFIED' and set(result['deferred_indexes']) == INDEXES
    writes = (full[1].writes, full[2].writes)
    deadline = pack.bounded_json(tmp_path/'job/full-state.json')['deadline']
    assert run('publish') == result and run('status') == result
    assert (full[1].writes, full[2].writes) == writes
    assert pack.bounded_json(tmp_path/'job/full-state.json')['deadline'] == deadline
    full[2].rows.pop(next(iter(full[2].rows)))
    with pytest.raises(io.DPError): run('status')
    assert not full[2].active and not full[2].states


def test_optin_invalid_type_and_full_missing_table_rejected(full, tmp_path):
    with pytest.raises(io.DPError, match='QUERY_INDEX_POLICY'):
        pack.import_generation(full[0], full[4], target_binding='fixture',
            directory=tmp_path/'bad', allow_missing_lookup_indexes='False')
    full[3].created -= INDEXES | {'LEGAL_RAG_QUERY_ROW_A'}
    with pytest.raises(io.DPError, match='QUERY_SCHEMA'):
        pack.import_generation(full[0], full[4], target_binding='fixture',
            directory=tmp_path/'bad', allow_missing_lookup_indexes=True)
    assert not full[1].writes and not full[2].writes


def _mock_code():
    # Reuse only the SQL boundary doubles, not imports of the repository runtime.
    tests = ROOT/'05_TESTS/CONTRACTS'
    text = "import copy, hashlib, re\nfrom json import loads\n"
    text += "from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q\nDDL=q.DDL\n"
    for filename, names in [
        ('test_oracle_dp.py', {'substring', 'Oracle'}),
        ('test_oracle_dp_runtime.py', {'AssetOracle'}),
        ('test_oracle_query_catalog.py', {'Oracle'}),
        ('test_oracle_query_schema.py', {'SchemaOracle'}),
    ]:
        source = (tests/filename).read_text()
        text += '\n'.join(ast.get_source_segment(source, node) for node in ast.parse(source).body
                         if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names) + '\n'
        if filename == 'test_oracle_query_catalog.py': text += 'QueryOracle=Oracle\n'
    return text


def _notebook_runner(upload, text, mock_code):
    # Constructor injects the simulated SQL transport after the pinned entry has loaded.
    shim = f'''import sys, types, json
from pathlib import Path
m=types.ModuleType('dataiku')
class Folder:
 def __init__(self,ident): assert ident=='fixture'
 def get_download_stream(self,name): return (Path({str(upload)!r})/name.lstrip('/')).open('rb')
m.Folder=Folder
m.default_project_key=lambda:'fixture'
def executor(**kwargs):
 exec({mock_code!r},globals())
 from lawrag.pipeline.oracle_query_dataiku import DataikuClient
 remote_source=AssetOracle();remote_query=QueryOracle();remote_schema=SchemaOracle()
 remote_schema.created=set(remote_schema.columns)
 def request(self,method,path,json):
  statement=json['statementText']
  if 'WHERE 1=0' in statement: return {{'items':[{{'resultSet':{{'items':[],'hasMore':False,'offset':0}}}}]}}
  target=remote_schema if ':owner' in statement and 'ALL_' in statement else remote_query if 'LEGAL_RAG_QUERY_' in statement else remote_source
  return target.request('POST','/sql',json=json)
 DataikuClient.request=request
 DataikuClient.identity=lambda self:('fixture',{{'TEST_ONLY':True}})
 return object()
m.SQLExecutor2=executor
sys.modules['dataiku']=m
'''
    return shim + text


def test_exact_r2_failure_to_r3_notebook_reuses_restore_and_budget(full, tmp_path):
    work = tmp_path/'legal-existing-zip-r2-work'
    work.mkdir()
    shutil.copytree(full[4], work/'restored')
    before = (work/'restored/generation/store.sqlite').stat().st_ino
    upload = tmp_path/'managed'; upload.mkdir()
    old = D.with_name('legal_oracle_existing_zip_20261020_r2')
    oldname = 'LEGAL_ORACLE_EXISTING_ZIP_20261020_R2'
    for delivery, name in [(old, oldname), (D, N)]:
        shutil.copyfile(delivery/(name+'.zip'), upload/(name+'.zip'))
    mock = _mock_code()
    def run(delivery, action):
        text = (delivery/'package/DATAIKU_EXISTING_ZIP_IMPORT_RUN.txt').read_text()
        text = text.replace('ACTION = "inspect"', 'ACTION = "check"')
        text = text.replace('ACTION = "check"', 'ACTION = '+repr(action))
        text = text.replace('FOLDER_ID = "여기에_Managed_Folder_ID"', 'FOLDER_ID = "fixture"')
        text = text.replace('ORACLE_CONNECTION = "여기에_Oracle_연결_이름"', 'ORACLE_CONNECTION = "fixture"')
        runner = tmp_path/'notebook.py'; runner.write_text(_notebook_runner(upload, text, mock))
        return subprocess.run([sys.executable, str(runner)], cwd=tmp_path, capture_output=True, text=True)
    r = run(old, 'check')
    assert r.returncode != 0 and 'QUERY_SCHEMA' in r.stdout, r.stdout+r.stderr
    oldstate = work/'oracle-import/full-state.json'
    oldbytes = oldstate.read_bytes()
    r = run(D, 'check')
    assert r.returncode == 0 and 'READY_FOR_FULL_IMPORT' in r.stdout, r.stdout+r.stderr
    r = run(D, 'publish')
    assert r.returncode == 0 and 'FULL_DATA_VERIFIED' in r.stdout, r.stdout+r.stderr
    state = pack.bounded_json(work/'oracle-import-r3/full-state.json')
    assert state['deadline'] == json.loads(oldbytes)['deadline']
    assert state['prior_schema_calls'] > 0
    assert set(state['result']['deferred_indexes']) == INDEXES
    assert oldstate.read_bytes() == oldbytes
    assert (work/'restored/generation/store.sqlite').stat().st_ino == before


@pytest.mark.parametrize('damage', ['code', 'target', 'stages', 'write', 'expired'])
def test_prior_failure_upgrade_rejects_unsafe_state(full, tmp_path, damage):
    identity = {'target': 'fixture', 'data': 'test', 'generation': str(full[4]),
                'code': io.file_sha(pack.__file__)}
    oldidentity = dict(identity, code='641c45540ffb8d3e086bd8060e9cb556e3ae5ccf705d287fe4b5a5528c94c7e2')
    old = tmp_path/'old'; old.mkdir()
    state = {'identity': oldidentity, 'status': 'FAILED', 'stages': {}, 'deadline': 1,
             'error': 'QUERY_SCHEMA: missing index'}
    if damage == 'code': oldidentity['code'] = 'other'
    if damage == 'target': oldidentity['target'] = 'other'
    if damage == 'stages': state['stages']['source'] = {}
    io.atomic_json(old/'full-state.json', state)
    (old/'schema.jsonl').write_text(json.dumps({'binding': io.digest(oldidentity), 'call': 12,
                                              'write': damage == 'write'})+'\n')
    if damage == 'expired':
        # Preserve an expired deadline, never grant another seven days.
        assert pack._prior_schema_failure(old, identity)['deadline'] == 1
    else:
        with pytest.raises(io.DPError, match='IMPORT_UPGRADE'): pack._prior_schema_failure(old, identity)
