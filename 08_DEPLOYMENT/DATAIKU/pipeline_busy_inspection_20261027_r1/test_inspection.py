import asyncio
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import urllib.error
import zipfile

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('busy_inspection', HERE/'inspect_jobs.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Folder:
    def __init__(self): self.data = {}
    def list_paths_in_partition(self): return list(self.data)
    def get_download_stream(self, path): return io.BytesIO(self.data[path])
    def put(self, name, value, seq=1):
        raw = json.dumps(value).encode()
        key = f'_pipeline/jobs/{name}/checkpoint-{seq:010d}-{hashlib.sha256(raw).hexdigest()}.json'
        self.data[key] = raw
        return key


@pytest.fixture
def env(tmp_path, monkeypatch):
    archive = HERE.parent/'pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
    code = tmp_path/'code'; code.mkdir()
    with zipfile.ZipFile(archive) as z:
        for name in ('service.py', 'transport.py', 'CODE_PINS.json'):
            member = next(n for n in z.namelist() if n.split('/', 1)[1] == name)
            (code/name).write_bytes(z.read(member))
    monkeypatch.syspath_prepend(str(code))
    monkeypatch.delitem(sys.modules, 'transport', raising=False)
    spec = importlib.util.spec_from_file_location('busy_sealed_service', code/'service.py')
    service = importlib.util.module_from_spec(spec); spec.loader.exec_module(service)
    monkeypatch.setenv('PIPELINE_SCRATCH', str(tmp_path/'scratch'))
    assert service.code_pin() == d.SERVICE_SHA
    variables = {'LEGAL_PIPELINE_URL':'https://fixture.invalid/pipeline', 'LEGAL_PIPELINE_TOKEN':'private-api-token'}
    calls = []
    def open_request(request, timeout):
        data = json.loads(request.data); calls.append(data)
        return io.BytesIO(json.dumps(asyncio.run(service.service({}, data))).encode())
    monkeypatch.setattr(d.urllib.request, 'build_opener', lambda *_: SimpleNamespace(open=open_request))
    remote = d.StatusClient(variables)
    health = remote.call('HEALTH')
    auth = {'job_id':'1'*32, 'job_token':'a'*64, 'instance':health['instance'], 'code_sha256':d.SERVICE_SHA}
    archives = {slot:{'bytes':10, 'sha256':'b'*64} for slot in ('raw','support')}
    service.handle({'API_TYPE':'START', **auth, 'archives':archives, 'deadline':time.time()+600})
    path = tmp_path/'scratch'/auth['job_id']/'state.json'
    state = json.loads(path.read_text()); state.update(status='FAILED',phase='STRUCTURE',error='STAGE_FAILED: private-api-token')
    path.write_text(json.dumps(state))
    checkpoint = {'binding':{'service_code':d.SERVICE_SHA, 'service_url_sha256':remote.endpoint_sha,
        'input':{'project':d.PROJECT, 'folder_id':d.LANDING, 'client_sha256':sorted(d.CLIENT_SHAS)[0]}},
        'client':{**auth, 'status':'NEW'}, 'deadline':time.time()+600, 'reserved_sql_calls':128}
    return SimpleNamespace(service=service, remote=remote, health=health, auth=auth,
        checkpoint=checkpoint, calls=calls, state_path=path, archives=archives, variables=variables)


def inspect(env, checkpoint=None, role='legacy'):
    folder = Folder(); folder.put('sample', checkpoint or env.checkpoint)
    before = copy.deepcopy(folder.data)
    rows = d.inspect_folder(folder, role, 'raw-id', env.remote, env.health)
    assert folder.data == before
    assert {c['API_TYPE'] for c in env.calls} <= {'HEALTH','STATUS'}
    return rows


def test_actual_sealed_busy_then_failed_status(env):
    response = asyncio.run(env.service.service({}, {'API_TYPE':'START', **env.auth,
        'job_id':'2'*32, 'archives':env.archives, 'deadline':time.time()+600}))
    assert response['error'].startswith('BUSY:')
    before = env.state_path.read_bytes()
    row = inspect(env)[0]
    assert (row['status'],row['phase'],row['error_code'],row['blocks_new_start']) == ('FAILED','STRUCTURE','STAGE_FAILED',True)
    assert env.state_path.read_bytes() == before
    assert 'private-api-token' not in json.dumps(row) and 'a'*64 not in json.dumps(row)


@pytest.mark.parametrize('status,blocks', [('COMPLETE',True),('UPLOADING',True),('RELEASED',False),('CANCELLED',True)])
def test_terminal_and_upload_states(env, status, blocks):
    state = json.loads(env.state_path.read_text()); state['status']=status
    env.state_path.write_text(json.dumps(state))
    row = inspect(env)[0]
    assert row['status'] == status and row['blocks_new_start'] == blocks


@pytest.mark.parametrize('alive', [True,False])
def test_running_and_lost_worker_refresh(env, alive):
    state = json.loads(env.state_path.read_text())
    state.update(status='RUNNING', worker=env.service.pid_identity(os.getpid()) if alive else [99999999,'x','x'])
    env.state_path.write_text(json.dumps(state))
    assert inspect(env)[0]['status'] == ('RUNNING' if alive else 'INTERRUPTED')


def test_lost_job_is_not_absence_or_release(env):
    cp = copy.deepcopy(env.checkpoint); cp['client']['job_id']='2'*32
    row = inspect(env, cp)[0]
    assert row['status']=='STATUS_UNCONFIRMED' and row['error_code']=='JOB_LOST'
    assert 'blocks_new_start' not in row


@pytest.mark.parametrize('change,expected', [('instance','INSTANCE_CHANGED'),('endpoint','SKIPPED_BINDING'),('client','SKIPPED_BINDING')])
def test_stale_binding_makes_no_status_call(env, change, expected):
    cp = copy.deepcopy(env.checkpoint)
    if change=='instance': cp['client']['instance']='3'*32
    elif change=='endpoint': cp['binding']['service_url_sha256']='4'*64
    else: cp['binding']['input']['client_sha256']='5'*64
    assert inspect(env, cp)[0]['status']==expected
    assert len(env.calls)==1


def test_flow_binding_and_no_client(env):
    cp = copy.deepcopy(env.checkpoint)
    cp['binding'].update(version='recipes-20261027-r1',input={'landing':d.LANDING,'raw':'raw-id'})
    assert inspect(env, cp, 'structured')[0]['status']=='FAILED'
    cp.pop('client')
    assert inspect(env, cp, 'load')[0]['status']=='NO_CLIENT_STATE'


def test_hash_conflict_latest_and_record_limit(env):
    folder=Folder(); path=folder.put('sample',env.checkpoint)
    folder.data[path]+=b' '
    with pytest.raises(d.InspectionError,match='CHECKPOINT_HASH'): list(d.latest_checkpoints(folder))
    folder=Folder(); folder.put('sample',env.checkpoint)
    cp=copy.deepcopy(env.checkpoint);cp['reserved_sql_calls']=192
    folder.put('sample',cp)
    with pytest.raises(d.InspectionError,match='CONCURRENT'):list(d.latest_checkpoints(folder))
    folder=Folder();folder.put('sample',env.checkpoint);folder.put('sample',cp,2)
    assert list(d.latest_checkpoints(folder))[0][1]['reserved_sql_calls']==192
    with pytest.raises(d.InspectionError,match='RECORD_TOO_LARGE'):d.read_small(io.BytesIO(b'x'*(1024*1024+1)))


def test_wrong_response_identity_blocked(env, monkeypatch):
    monkeypatch.setattr(env.remote,'call',lambda *a,**kw:{'job_id':'2'*32, 'status':'RELEASED'})
    row=inspect(env)[0]
    assert row['status']=='STATUS_UNCONFIRMED' and row['error_code']=='STATUS_BINDING'


def test_transport_budget_allowlist_and_redaction(env, monkeypatch):
    for operation in ('START','ACK','CANCEL','EXECUTE'):
        with pytest.raises(d.InspectionError,match='INSPECTION_OPERATION_ONLY'):env.remote.call(operation)
    def failed(*args,**kwargs):raise urllib.error.URLError('private-api-token')
    monkeypatch.setattr(d.urllib.request,'build_opener',lambda *_:SimpleNamespace(open=failed))
    with pytest.raises(d.InspectionError,match='GENOS_TRANSPORT_UNCONFIRMED'):env.remote.call('STATUS')
    env.remote.deadline=0
    with pytest.raises(d.InspectionError,match='INSPECTION_BUDGET'):env.remote.call('HEALTH')
    assert d.error_code('private-api-token')=='DETAIL_WITHHELD'


def test_delivered_txt_full_notebook_entrypoint(env, monkeypatch):
    folders={key:Folder() for key in (d.LANDING,'structured-id','load-id')}
    folders[d.LANDING].put('old-notebook',env.checkpoint)
    cp=copy.deepcopy(env.checkpoint);cp['binding'].update(version='recipes-20261027-r1',input={'landing':d.LANDING,'raw':'raw-id'})
    cp['client']['job_id']='2'*32
    folders['structured-id'].put('recipes_20261027_r1',cp)
    listing=[{'name':name,'id':fid} for name,fid in [('LEGAL_RAW_SOURCE_R1','raw-id'),('LEGAL_STRUCTURED_RESULT_R1','structured-id'),('LEGAL_LGL_LOAD_RESULT_R1','load-id')]]
    sdk=SimpleNamespace(default_project_key=lambda:d.PROJECT,get_custom_variables=lambda:env.variables,
        api_client=lambda:SimpleNamespace(get_project=lambda key:SimpleNamespace(list_managed_folders=lambda:listing)),
        Folder=lambda fid,project_key:folders[fid])
    monkeypatch.setitem(sys.modules,'dataiku',sdk)
    delivered=(HERE/'DATAIKU_GENOS_BUSY_CHECK_20261027_R1.txt').read_bytes()
    assert delivered==(HERE/'inspect_jobs.py').read_bytes()
    before={k:copy.deepcopy(v.data) for k,v in folders.items()}
    output=io.StringIO();ns={'__name__':'__main__'}
    with contextlib.redirect_stdout(output):exec(compile(delivered,'delivered-TXT','exec'),ns)
    rows=ns['PIPELINE_JOBS']
    assert [r['status'] for r in rows]==['FAILED','STATUS_UNCONFIRMED']
    assert 'blocking_job_ids' in output.getvalue()
    assert env.variables['LEGAL_PIPELINE_TOKEN'] not in output.getvalue()
    assert env.variables['LEGAL_PIPELINE_URL'] not in output.getvalue()
    assert env.auth['job_token'] not in output.getvalue()
    assert before=={k:v.data for k,v in folders.items()}
    assert {c['API_TYPE'] for c in env.calls}=={'HEALTH','STATUS'}
