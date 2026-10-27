"""Packaged recipe contracts; synthetic bytes, no internal network or models."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import ssl
import sys
import tempfile
from types import SimpleNamespace
import urllib.error
import zipfile
import pytest

HERE = Path(__file__).resolve().parent
PACKAGE = HERE/'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip'
EXTRACT = tempfile.TemporaryDirectory(prefix='a8-recipe-contract-')
CODE = Path(EXTRACT.name)
with zipfile.ZipFile(PACKAGE) as z: z.extractall(CODE)
sys.path[:0] = [str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
import recipes_runtime as r
import install_flow


class Folder:
    def __init__(self): self.data = {}; self.corrupt = False; self.writes = 0
    def list_paths_in_partition(self): return ['/'+p for p in self.data]
    def get_download_stream(self, name): return io.BytesIO(self.data[name.lstrip('/')])
    def upload_stream(self, name, stream):
        self.writes += 1
        self.data[name.lstrip('/')] = stream.read() + (b'bad' if self.corrupt else b'')


def archives(tmp_path):
    landing = Folder()
    for name, file in [('RAW_INPUT.zip','01_DATA/RAW/internal/team/한글.docx'),
                       ('PIPELINE_SUPPORT.zip','01_DATA/CATALOG/sample.json')]:
        p = tmp_path/(name+'.input'); p.write_bytes('원문 그대로'.encode())
        target = tmp_path/name
        receipt = r.t.pack({file:p}, target)
        landing.data[name.replace('.zip',' (1).zip')] = target.read_bytes()
        landing.data[name+'.receipt (1).json'] = json.dumps({'archive':name,**receipt}).encode()
    return landing


def test_exact_payload_pins_and_old_worker_preserved():
    manifest = json.loads((HERE/'DELIVERY_MANIFEST.json').read_text())
    for name,sha in manifest['files'].items(): assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha
    pins = json.loads((CODE/'PACKAGE_FILES.json').read_text())
    for name,sha in pins.items(): assert hashlib.sha256((CODE/name).read_bytes()).hexdigest()==sha
    old = HERE.parent/'pipeline_layers_20261027_r1'
    with zipfile.ZipFile(old/'DATAIKU_PIPELINE_CLIENT_20261027_R1.zip') as z:
        for name in z.namelist(): assert (CODE/'client'/name.split('/',1)[1]).read_bytes()==z.read(name)
    assert not any(p.suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for p in CODE.rglob('*'))


def test_raw_durable_exact_and_idempotent(tmp_path):
    landing, raw = archives(tmp_path), Folder()
    result = r.unpack_raw(landing,raw,tmp_path)
    assert result['status']=='RAW_SAVED' and result['oracle_written'] is False
    record = r.raw_manifest(raw,r.input_receipts(landing)['RAW_INPUT.zip'])
    item = record['files']['01_DATA/RAW/internal/team/한글.docx']
    assert raw.data[item['path']]=='원문 그대로'.encode()
    writes = raw.writes
    r.unpack_raw(landing,raw,tmp_path)
    assert raw.writes==writes
    raw.data[item['path']]=b'x'*item['bytes']
    with pytest.raises(ValueError,match='CONFLICT'): r.unpack_raw(landing,raw,tmp_path)
    assert raw.data[item['path']]==b'x'*item['bytes']


def test_corrupt_upload_never_publishes_raw_manifest(tmp_path):
    landing,raw=archives(tmp_path),Folder(); raw.corrupt=True
    with pytest.raises(ValueError): r.unpack_raw(landing,raw,tmp_path)
    assert not any(p.endswith('manifest.json') for p in raw.data)


def test_input_alias_ambiguity_refused(tmp_path):
    landing=archives(tmp_path)
    landing.data['RAW_INPUT.zip']=landing.data['RAW_INPUT (1).zip']
    with pytest.raises(ValueError,match='AMBIGUOUS'):r.input_receipts(landing)


def test_unsafe_archive_refused_without_s3_publication(tmp_path):
    landing=archives(tmp_path); raw=Folder()
    bad=io.BytesIO()
    with zipfile.ZipFile(bad,'w') as z:
        z.writestr('../escape',b'x')
        z.writestr('TRANSPORT.json',json.dumps({'format':r.t.FORMAT,'files':{'../escape':{'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}}}))
    data=bad.getvalue()
    landing.data['RAW_INPUT (1).zip']=data
    landing.data['RAW_INPUT.zip.receipt (1).json']=json.dumps({'archive':'RAW_INPUT.zip','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}).encode()
    job=tmp_path/'unsafe-run';job.mkdir()
    with pytest.raises(ValueError,match='UNSAFE_PATH'):r.unpack_raw(landing,raw,job)
    assert not raw.data and not (tmp_path.parent/'escape').exists()


def test_materialize_uses_s3_original_and_checks_hash(tmp_path):
    landing,raw=archives(tmp_path),Folder()
    r.unpack_raw(landing,raw,tmp_path)
    record=r.raw_manifest(raw,r.input_receipts(landing)['RAW_INPUT.zip'])
    job=tmp_path/'next-recipe';job.mkdir()
    result=r.materialize(raw,record,job)
    assert (result/'01_DATA/RAW/internal/team/한글.docx').read_bytes()=='원문 그대로'.encode()
    item=next(iter(record['files'].values()));raw.data[item['path']]=b'wrong'
    job=tmp_path/'tampered';job.mkdir()
    with pytest.raises(r.legacy.RunError,match='HASH_OR_SIZE'):r.materialize(raw,record,job)


@pytest.mark.parametrize('failure,code',[
    (urllib.error.HTTPError('https://secret',401,'token-secret',{},None),'GENOS_HTTP_401'),
    (urllib.error.HTTPError('https://secret',302,'token-secret',{},None),'GENOS_HTTP_302'),
    (urllib.error.URLError(socket.gaierror('token-secret')),'GENOS_DNS'),
    (urllib.error.URLError(ssl.SSLCertVerificationError('token-secret')),'GENOS_TLS_CERTIFICATE'),
    (TimeoutError('token-secret'),'GENOS_TIMEOUT'),
])
def test_http_one_attempt_diagnostic_without_secret(tmp_path,monkeypatch,failure,code,capsys):
    calls=[]
    def invoke(req,timeout): calls.append(req);raise failure
    monkeypatch.setattr(r.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=invoke))
    folder=Folder()
    with pytest.raises(RuntimeError,match=code):
        r.connection({'LEGAL_PIPELINE_URL':'https://example.invalid/api','LEGAL_PIPELINE_TOKEN':'token-secret'},folder,tmp_path)
    assert len(calls)==1 and json.loads(calls[0].data)=={'API_TYPE':'HEALTH'}
    assert 'token-secret' not in capsys.readouterr().out
    assert b'token-secret' not in b''.join(folder.data.values())


@pytest.mark.parametrize('body,expected',[
    ({'code':0,'data':{'code_sha256':r.EXPECTED,'instance':'fixture'}},'CONNECTED_CODE_MATCH'),
    ({'code':0,'data':{'code_sha256':'0'*64,'instance':'fixture'}},'DEPLOYED_CODE_MISMATCH'),
    ({'code':0,'data':{'code_sha256':r.EXPECTED}},'GENOS_HEALTH_CONTRACT'),
    ({'code':1,'error':'Bearer token-secret'},'GENOS_REPLY_'),
    ('<html>token-secret</html>','GENOS_NOT_JSON'),
])
def test_connection_wire_and_code_match(tmp_path,monkeypatch,body,expected,capsys):
    calls=[];raw=body.encode() if isinstance(body,str) else json.dumps(body).encode()
    def invoke(req,timeout):calls.append(req);return io.BytesIO(raw)
    monkeypatch.setattr(r.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=invoke))
    folder=Folder();variables={'LEGAL_PIPELINE_URL':'https://example.invalid/api','LEGAL_PIPELINE_TOKEN':'token-secret'}
    if expected=='CONNECTED_CODE_MATCH':assert r.connection(variables,folder,tmp_path)['status']==expected
    else:
        with pytest.raises((ValueError,RuntimeError),match=expected):r.connection(variables,folder,tmp_path)
    assert len(calls)==1
    assert json.loads(calls[0].data)=={'API_TYPE':'HEALTH'}
    assert 'token-secret' not in capsys.readouterr().out
    assert b'token-secret' not in b''.join(folder.data.values())


def test_seed_load_deadline_budget_stable_and_upstream_immutable():
    upstream=r.ManagedJob(Folder(),'same',{'b':1})
    upstream.value.update(deadline=1234,reserved_sql_calls=128,client={'job_token':'private'})
    upstream.save()
    copy_before=copy.deepcopy(upstream.folder.data)
    dest=Folder();load=r.ManagedJob(dest,'same',{'b':2})
    r.seed_load(load,upstream)
    load.value['reserved_sql_calls']=192;load.save()
    resumed=r.ManagedJob(dest,'same',{'b':2})
    r.seed_load(resumed,upstream)
    assert resumed.value['deadline']==1234 and resumed.value['reserved_sql_calls']==192
    assert upstream.folder.data==copy_before
    upstream.value['deadline']=9999
    with pytest.raises(ValueError,match='CHANGED'):r.seed_load(resumed,upstream)


def test_missing_upstream_cannot_be_created_by_load():
    folder=Folder()
    with pytest.raises(ValueError,match='UPSTREAM_STAGE_NOT_READY'):
        r.ManagedJob(r.ReadOnlyFolder(folder),'missing',{})
    assert not folder.data


def test_generated_cells_compile_and_do_not_start_pipeline():
    for name in ('DATAIKU_RECIPE_INSTALL_20261027_R1.txt','DATAIKU_GENOS_CONNECTION_CHECK_20261027_R1.txt'):
        compile((HERE/name).read_text(),name,'exec')
    script=(HERE/'DATAIKU_RECIPE_INSTALL_20261027_R1.txt').read_text()
    assert "module.install(" in script
    assert "module.execute(" not in script
    datasets=json.loads((CODE/'oracle_datasets.json').read_text())
    assert len(datasets)==7
    assert all(x['params']['schema']=='SIDDS' and x['params']['table'].endswith('_S') for x in datasets)
