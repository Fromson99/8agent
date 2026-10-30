"""Existing generation bytes, durable transfer and maintained import, without rebuild."""
import asyncio
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import types
import zipfile

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from lawrag.pipeline import oracle_existing_nfs as nfs, oracle_full_package as pack

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT/'08_DEPLOYMENT/DATAIKU/existing_nfs_transfer_20261029_r1'
CODE = 'a'*64


def copy_snapshot(source, target):
    for name, item in source.info['files'].items():
        p = target/name; p.parent.mkdir(parents=True, exist_ok=True)
        offset = 0
        with p.open('wb') as stream:
            while offset < item['bytes']:
                result = source.read(source.info['snapshot_sha256'], name, offset)
                block = base64.b64decode(result['content'])
                assert hashlib.sha256(block).hexdigest() == result['sha256']
                stream.write(block); offset += len(block)
    return nfs.finish_received(target, source.info)


def test_full_roundtrip_and_no_regeneration(full, tmp_path, monkeypatch):
    generation = full[7]
    before = {str(p): (p.stat().st_mtime_ns, pack.io.file_sha(p)) for p in generation.rglob('*') if p.is_file()}
    snapshot = nfs.Snapshot(generation, CODE)
    nfs.validate_info(snapshot.info, code_sha256=CODE, generation=str(generation.resolve()))
    dest = tmp_path/'nfs-restored'
    copy_snapshot(snapshot, dest)
    result = pack.import_generation(full[0], dest, target_binding='synthetic-nfs', directory=tmp_path/'load', action='publish')
    assert result['status'] == 'FULL_DATA_VERIFIED'
    writes = (full[1].writes, full[2].writes)
    assert pack.import_generation(full[0], dest, target_binding='synthetic-nfs', directory=tmp_path/'load', action='publish') == result
    assert writes == (full[1].writes, full[2].writes)
    assert not full[2].active and not full[2].states
    assert before == {str(p): (p.stat().st_mtime_ns, pack.io.file_sha(p)) for p in generation.rglob('*') if p.is_file()}


@pytest.mark.parametrize('damage', ['file','manifest','wal','selection','undeclared','offset','binding'])
def test_source_change_and_read_scope(structured_generation, damage):
    s = nfs.Snapshot(structured_generation, CODE)
    name, offset, binding = 'generation/store.sqlite', 0, s.info['snapshot_sha256']
    if damage == 'file':
        with (structured_generation/'store.sqlite').open('ab') as stream: stream.write(b'x')
    elif damage == 'manifest':
        with (structured_generation/'manifest.json').open('ab') as stream: stream.write(b' ')
    elif damage == 'wal':
        Path(str(structured_generation/'store.sqlite')+'-wal').write_bytes(b'x')
    elif damage == 'selection':
        s.selection_path.parent.mkdir(exist_ok=True); s.selection_path.write_text('{}')
    elif damage == 'undeclared': name = '../outside'
    elif damage == 'offset': offset = -1
    else: binding = 'b'*64
    with pytest.raises(ValueError): s.read(binding, name, offset)


def test_inventory_binding_and_large_manifest(structured_generation):
    from semantic_runtime.oracle_dp_io import file_sha, atomic_json
    root = structured_generation
    main = json.loads((root/'manifest.json').read_text())
    path = root/main['fulltext']['path']/'manifest.json'
    fm = json.loads(path.read_text()); fm['diagnostic_padding'] = 'x'*3300000
    atomic_json(path, fm); main['fulltext']['manifest_sha256'] = file_sha(path); atomic_json(root/'manifest.json', main)
    s = nfs.Snapshot(root, CODE)
    assert s.info['files']['generation/fulltext/manifest.json']['bytes'] > 1024**2
    changed = {**s.info, 'code_sha256': 'b'*64}
    with pytest.raises(ValueError, match='NFS_SERVICE_BINDING'):
        nfs.validate_info(changed, code_sha256=CODE, generation=str(root.resolve()))


class Folder:
    def __init__(self): self.values = {}
    def list_paths_in_partition(self): return ['/'+k for k in self.values]
    def get_download_stream(self, name): return io.BytesIO(self.values[name.lstrip('/')])
    def upload_stream(self, name, stream): self.values[name.lstrip('/')] = stream.read()


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path/'client'
    with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip') as z: z.extractall(root)
    for path in (root/'client/02_BACKEND', root/'client', root): monkeypatch.syspath_prepend(str(path))
    monkeypatch.setitem(sys.modules, 'dataiku', types.SimpleNamespace())
    for name in ('transport','managed_job','dataiku_run','recipes_runtime','legacy_runner','updater','existing_client'):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import existing_client as c
    return c


def test_receive_restart_and_transient_read_failure(client, structured_generation, tmp_path, monkeypatch):
    c = client
    snapshot = nfs.Snapshot(structured_generation, CODE)
    folder = Folder(); store = c.ManagedJob(folder, 'fixture', {'code': CODE})
    original_deadline = store.value['deadline']
    class Wire:
        calls = 0
        def call(self, op, **fields):
            self.calls += 1
            if self.calls == 2: raise RuntimeError('NFS_HTTP_503')
            return snapshot.read(fields['snapshot_sha256'], fields['file'], fields['offset'])
    wire = Wire(); monkeypatch.setattr(c.time, 'sleep', lambda seconds: None)
    dest = tmp_path/'received'
    c.receive(store, wire, snapshot.info, dest)
    assert store.value['phase'] == 'RECEIVED_VERIFIED' and wire.calls > 2
    assert store.value['read_failures'][0]['error'] == 'NFS_HTTP_503'
    shutil.rmtree(dest)
    restarted = c.ManagedJob(folder, 'fixture', {'code': CODE})
    previous = wire.calls
    c.receive(restarted, wire, snapshot.info, dest)
    assert wire.calls == previous and restarted.value['deadline'] == original_deadline
    assert restarted.value['reserved_http_calls'] == store.value['reserved_http_calls']
    part = next(k for k in folder.values if k.endswith('.bin'))
    folder.values[part] = b'corrupt'
    shutil.rmtree(dest)
    with pytest.raises(ValueError, match='NFS_SAVED_CHUNK_HASH'):
        c.receive(restarted, wire, snapshot.info, dest)


def test_http_exhaustion_budget_and_no_compute(client, monkeypatch):
    c = client; store = c.ManagedJob(Folder(), 'fixture', {})
    monkeypatch.setattr(c.time, 'sleep', lambda seconds: None)
    class Wire:
        calls = []
        def call(self, op, **fields): self.calls.append(op); raise RuntimeError('NFS_HTTP_503')
    wire = Wire()
    with pytest.raises(RuntimeError): c.request(store, wire, 'EXISTING_NFS_INFO')
    assert wire.calls == ['EXISTING_NFS_INFO']*3
    assert len(store.value['read_failures']) == 3
    store.value['deadline'] = 0
    with pytest.raises(ValueError, match='DEADLINE'): c.request(store, wire, 'EXISTING_NFS_INFO')
    with pytest.raises(ValueError, match='READ_ONLY'): c.request(store, wire, 'RUN')
    assert len(wire.calls) == 3


def test_delivered_service_entrypoint(structured_generation, tmp_path):
    with zipfile.ZipFile(HERE/'GENOS_EXISTING_NFS_20261029_R1.zip') as z: z.extractall(tmp_path/'server')
    root = tmp_path/'server/GENOS_EXISTING_NFS_20261029_R1'
    program = '''import asyncio,base64,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root),str(root/'02_BACKEND')]
import service,nfs_source,transport
nfs_source.GENERATION=sys.argv[2]
code=transport.sha(root/'CODE_PINS.json')
def call(op,**fields):return asyncio.run(service.service({},dict(API_TYPE=op,code_sha256=code,**fields)))
info=call('EXISTING_NFS_INFO');assert info['code']==0,info
info=info['data'];assert info['rebuild'] is False
result=call('EXISTING_NFS_READ',snapshot_sha256=info['snapshot_sha256'],file='generation/manifest.json',offset=0)
assert result['code']==0,result
assert base64.b64decode(result['data']['content'])==(Path(sys.argv[2])/'manifest.json').read_bytes()
bad=call('EXISTING_NFS_READ',snapshot_sha256=info['snapshot_sha256'],file='../outside',offset=0)
assert bad['code']==1 and bad['error']=='NFS_UNDECLARED_FILE'
assert not service.HANDLES
print('NATIVE_SERVICE_PASS')
'''
    result = subprocess.run([sys.executable, '-c', program, str(root), str(structured_generation)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'NATIVE_SERVICE_PASS' in result.stdout


def test_delivered_notebook_check_transfer_load_and_resume(client, full, tmp_path, monkeypatch):
    c = client
    snapshot = nfs.Snapshot(full[7], c.EXPECTED)
    # Change the local fixture's advertised root only; real client keeps its fixed NFS root.
    snapshot.info['generation'] = c.GENERATION
    snapshot.info['snapshot_sha256'] = nfs.digest({k:v for k,v in snapshot.info.items() if k != 'snapshot_sha256'})
    landing, results = Folder(), Folder()
    name = 'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip'
    landing.values[name] = (HERE/name).read_bytes()
    cfg = dict(landing='ehA8dpVm', connection='c', raw='r', structured='s', load='l')
    recipe = types.SimpleNamespace(get_settings=lambda: types.SimpleNamespace(
        get_code=lambda: 'run_recipe('+repr('structure')+', '+repr(cfg)+')'))
    project = types.SimpleNamespace(get_recipe=lambda name: recipe)
    variables = dict(LEGAL_PIPELINE_SCRATCH=str(tmp_path), LEGAL_PIPELINE_URL='https://fixture.invalid/api',
                     LEGAL_PIPELINE_TOKEN='synthetic-not-a-credential')
    sdk = types.SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',
        api_client=lambda:types.SimpleNamespace(get_project=lambda name:project),
        get_custom_variables=lambda:variables, Folder=lambda name: landing if name=='ehA8dpVm' else results,
        SQLExecutor2=lambda **kwargs:object())
    monkeypatch.setitem(sys.modules,'dataiku',sdk)
    from lawrag.pipeline import oracle_query_dataiku
    from semantic_runtime.physical_mapping import SchemaMap
    oracle = full[0]; oracle.schema_map = None
    oracle.identity = lambda:('synthetic-nfs-notebook', {})
    monkeypatch.setattr(oracle_query_dataiku,'DataikuClient',lambda *a,**k:oracle)
    checked = []
    monkeypatch.setattr(SchemaMap,'preflight',lambda self, sql:checked.append(self.owners))
    calls=[]
    def wire(self, op, **fields):
        calls.append(op)
        if op == 'EXISTING_NFS_INFO': return snapshot.info
        return snapshot.read(fields['snapshot_sha256'], fields['file'], fields['offset'])
    monkeypatch.setattr(c.Wire,'call',wire)
    text = (HERE/'DATAIKU_EXISTING_NFS_RUN.txt').read_text()
    def execute(action):
        scope={};exec(compile(text.replace("ACTION = 'check'", "ACTION = "+repr(action)), 'delivered.txt','exec'),scope)
        return scope['NFS_RESULT']
    assert execute('check')['status']=='NFS_READY_FOR_TRANSFER'
    assert checked and 'SIDDS' in checked[0].values()
    assert execute('transfer')['status']=='NFS_RECEIVED_VERIFIED'
    assert full[1].writes == full[2].writes == 0
    result=execute('load');assert result['status']=='FULL_DATA_VERIFIED'
    before=len(calls);writes=full[1].writes,full[2].writes
    assert execute('status')['phase']=='COMPLETE' and len(calls)==before
    local=tmp_path/'legal-existing-nfs-20261029-r1'/c.JOB_NAME
    shutil.rmtree(local)
    assert execute('load')==result
    assert calls[before:]==['EXISTING_NFS_INFO']
    assert (full[1].writes,full[2].writes)==writes
    assert not full[2].active
    assert all(p.startswith(c.NAMESPACE) for p in results.values)


def test_installer_apply_stage_rollback_and_source_gate(structured_generation, tmp_path):
    baseline=HERE.parent/'pipeline_single_cpu_20261029_r10/GENOS_DATAIKU_COMPUTE_20261029_R10.zip'
    with zipfile.ZipFile(baseline) as z:z.extractall(tmp_path)
    checkout=tmp_path/'GENOS_DATAIKU_COMPUTE_20261029_R10'
    archive='GENOS_EXISTING_NFS_20261029_R1.zip'
    shutil.copyfile(HERE/archive,checkout/archive)
    def run(*args):
        result=subprocess.run(args,cwd=checkout,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        return result.stdout
    run('git','init','-q');run('git','add','--all')
    run('git','-c','user.name=Synthetic Test','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
    old=(checkout/'CODE_PINS.json').read_bytes()
    run(sys.executable,str(HERE/'install_compute.py'),'apply')
    run(sys.executable,str(HERE/'install_compute.py'),'apply')
    run(sys.executable,str(HERE/'install_compute.py'),'stage')
    run('git','diff','--cached','--check')
    run('git','-c','user.name=Synthetic Test','-c','user.email=fixture@example.invalid','commit','-qm','candidate')
    run(sys.executable,'VERIFY_PIPELINE_RELEASE.py','--code-root',str(checkout),'--require-committed')
    program='''import sys,runpy
from pathlib import Path
root=Path.cwd();sys.path[:0]=[str(root),str(root/'02_BACKEND')]
import nfs_source
nfs_source.GENERATION=sys.argv[1]
runpy.run_path(str(root/'NFS_VERIFY.py'),run_name='__main__')
'''
    assert 'NFS_SOURCE_VERIFIED' in run(sys.executable,'-c',program,str(structured_generation))
    run(sys.executable,str(HERE/'install_compute.py'),'rollback')
    assert (checkout/'CODE_PINS.json').read_bytes()==old
    assert not (checkout/'nfs_source.py').exists()
    for name in ('GENOS_EXISTING_NFS_INSTALL.txt','ROLLBACK_GENOS.txt'):
        run('bash','-n',str(HERE/name))
