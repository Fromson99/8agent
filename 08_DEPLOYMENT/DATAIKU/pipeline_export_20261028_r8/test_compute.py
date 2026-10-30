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
import time
import types
import zipfile
import pytest

HERE=Path(__file__).parent

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.fixture
def env(tmp_path,monkeypatch):
    with zipfile.ZipFile(HERE/'GENOS_DATAIKU_COMPUTE_20261028_R8.zip') as z:z.extractall(tmp_path)
    service=tmp_path/'GENOS_DATAIKU_COMPUTE_20261028_R8'
    with zipfile.ZipFile(HERE/'DATAIKU_COMPUTE_RECIPES_20261028_R8.zip') as z:z.extractall(tmp_path/'dku')
    dku=tmp_path/'dku'
    monkeypatch.syspath_prepend(str(dku/'client/02_BACKEND'))
    monkeypatch.syspath_prepend(str(dku/'client'));monkeypatch.syspath_prepend(str(dku))
    shared=tmp_path/'shared';shared.mkdir()
    monkeypatch.setenv('GENOS_PDF_PARSER','preprocessor')
    monkeypatch.delenv('GENOS_PREPROCESSOR_URL',raising=False)
    monkeypatch.setenv('GENOS_PREPROCESSOR_ID','987')
    monkeypatch.setenv('GENOS_PREPROCESSOR_SHARED_ROOT',str(shared))
    monkeypatch.setenv('GENOS_PREPROCESSOR_RESPONSE_MODE','auto')
    monkeypatch.setenv('LLM_BACKEND','genos')
    monkeypatch.setenv('GENOS_LLM_URL','http://fixture.invalid')
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM','on')
    monkeypatch.syspath_prepend(str(service))
    monkeypatch.syspath_prepend(str(service/'02_BACKEND'))
    for n in list(sys.modules):
        if n=='lawrag' or n.startswith('lawrag.'):
            monkeypatch.delitem(sys.modules,n)
    for n in ('upgrade_review','transport','worker','dataiku_run','managed_job','legacy_runner','recipes_runtime','controller','checkpoint_upgrade','parser_config','review_audit','sample_worker','probe_runtime','probe_client','selection','partial_pipeline','pipeline_coverage','http_parser_config','pod_parser_config'):
        if n in sys.modules:monkeypatch.delitem(sys.modules,n)
    t=module('transport',service/'transport.py');monkeypatch.setitem(sys.modules,'transport',t)
    w=module('worker',service/'worker.py');monkeypatch.setitem(sys.modules,'worker',w)
    api=module('compute_api',service/'service.py')
    import controller as c
    # Transport supervision tests isolate the image-specific preflight.
    monkeypatch.setattr(api.parser_config,'inspect',lambda root: {'ready':True,'config_sha256':'e'*64,'errors':[],'transport':'same-pod'})
    yield types.SimpleNamespace(api=api,c=c,t=t,w=w,root=service,dku=dku,tmp=tmp_path)
    for h in list(api.HANDLES.values()):
        h['cancel'].set();api.stop_child(h['child']);shutil.rmtree(h['folder'],ignore_errors=True)
    api.HANDLES.clear()


def opened(e):
    a=e.api;health=a.handle({'API_TYPE':'HEALTH'})
    auth={'handle':'a'*32,'handle_token':'b'*64,'instance':health['instance'],'code_sha256':health['code_sha256'],'parser_config_sha256':health['preprocessor']['config_sha256']}
    arc={'sha256':hashlib.sha256(b'x').hexdigest(),'bytes':1}
    result=a.handle(dict(API_TYPE='OPEN',**auth,archives={'raw':arc,'support':arc},deadline=time.time()+600))
    return auth,result


def call(e,a,op,**kw):return e.api.handle(dict(API_TYPE=op,**a,**kw))


def test_health_protocol_and_no_disk_registry(env):
    a,r=opened(env)
    assert r['state']=='RECEIVING'
    assert env.api.handle({'API_TYPE':'HEALTH'})['s3_access'] is False
    assert list(env.api.HANDLES[a['handle']]['folder'].iterdir())==[env.api.HANDLES[a['handle']]['folder']/'compute.log']
    for name in ('state.json','instance.json','dispatch.lock'):assert not list(env.tmp.rglob(name))


def test_upload_duplicate_hash_and_bounds(env):
    a,_=opened(env);args=dict(slot='raw',offset=0,content='eA==',sha256=hashlib.sha256(b'x').hexdigest())
    assert call(env,a,'PUT',**args)['received']['raw']==1
    assert call(env,a,'PUT',**args)['received']['raw']==1
    with pytest.raises(ValueError,match='CHUNK_HASH'):call(env,a,'PUT',**{**args,'sha256':'0'*64})
    with pytest.raises(ValueError,match='UPLOAD_OFFSET'):call(env,a,'PUT',**{**args,'offset':3})


def test_auth_restart_and_expiry(env):
    a,_=opened(env)
    with pytest.raises(ValueError,match='COMPUTE_AUTH'):call(env,{**a,'handle_token':'c'*64},'POLL')
    with pytest.raises(ValueError,match='INSTANCE_CHANGED'):call(env,{**a,'instance':'d'*32},'POLL')
    env.api.HANDLES[a['handle']]['lease_until']=time.monotonic()-1
    with pytest.raises(ValueError,match='LEASE_EXPIRED'):call(env,a,'POLL')


def test_cancel_receiving_and_close(env):
    a,_=opened(env)
    assert call(env,a,'CANCEL')['state']=='CANCELLED'
    assert call(env,a,'CLOSE')['closed']
    with pytest.raises(ValueError,match='HANDLE_GONE'):call(env,a,'POLL')


@pytest.mark.parametrize("reason",["cancel","lease","deadline"])
def test_cancel_real_child_and_descendant(env,monkeypatch,reason):
    a,_=opened(env);h=env.api.HANDLES[a['handle']]
    # Exercise the published supervisor with a real process group, without heavy parsing.
    fake=env.tmp/'fake-worker.py'
    fake.write_text('import subprocess,time,sys\nsubprocess.Popen([sys.executable,"-c","import time; time.sleep(90)"])\nprint("RUNNING",flush=True)\ntime.sleep(90)\n')
    root=env.tmp/'fake';root.mkdir();shutil.copyfile(fake,root/'worker.py')
    shutil.copyfile(env.root/'CODE_PINS.json',root/'CODE_PINS.json')
    monkeypatch.setattr(env.api,'ROOT',root)
    h['state']='RUNNING'
    import threading
    thread=threading.Thread(target=env.api.run_compute,args=(h,));thread.start()
    end=time.time()+5
    while h['child'] is None and time.time()<end:time.sleep(.02)
    child=h['child'];assert child is not None
    if reason=='cancel':
        assert call(env,a,'CANCEL')['state']=='RUNNING'
    elif reason=='lease':h['lease_until']=time.monotonic()-1
    else:h['deadline']=time.time()-1
    thread.join(8)
    assert not thread.is_alive() and child.poll() is not None
    assert h['state']==('CANCELLED' if reason=='cancel' else 'FAILED')
    assert env.w.process_group_rss(child.pid)==0


def test_run_idempotent_and_completed_handles_do_not_block(env,monkeypatch):
    a,_=opened(env);h=env.api.HANDLES[a['handle']];h['received']={'raw':1,'support':1}
    hits=[]
    def compute(x):hits.append(x['id']);x.update(state='COMPLETE',result={'bytes':1,'sha256':'f'*64})
    monkeypatch.setattr(env.api,'run_compute',compute)
    call(env,a,'RUN');time.sleep(.05);call(env,a,'RUN')
    assert len(hits)==1
    b={**a,'handle':'c'*32};arc=h['archives']
    call(env,b,'OPEN',archives=arc,deadline=time.time()+600)
    env.api.HANDLES[b['handle']]['received']={'raw':1,'support':1}
    call(env,b,'RUN');time.sleep(.05)
    assert len(hits)==2


class Folder:
    def __init__(self):self.files={}
    def list_paths_in_partition(self):return ['/'+x for x in self.files]
    def upload_stream(self,p,f):self.files[p.lstrip('/')]=f.read()
    def get_download_stream(self,p):return io.BytesIO(self.files[p.lstrip('/')])


def identity():return {'input':{'archives':{},'landing':'ehA8dpVm','raw':'r'},'database':{'db':'fixture'},'service_url_sha256':'f'*64,'version':'new','service_code':'new'}


def test_migration_preserves_old_deadline_budget_no_remote_calls(env):
    f=Folder();ident=identity();old=env.c.ManagedJob(f,'one',{**ident,'service_code':'old','version':'old'})
    old.value.update(deadline=1234,reserved_sql_calls=192,phase='NEW');old.save()
    original=dict(f.files)
    new=env.c.open_store(f,'one',ident)
    assert new.value['deadline']==1234 and new.value['reserved_sql_calls']==192
    assert all(f.files[k]==v for k,v in original.items())
    assert new.value['legacy_checkpoint']['remote_state']=='NOT_QUERIED'


def test_migration_rejects_result_and_binding_conflict(env):
    f=Folder();ident=identity();old=env.c.ManagedJob(f,'one',ident)
    old.value['phase']='STRUCTURED';old.save()
    with pytest.raises(ValueError,match='LEGACY_RETURN'):env.c.open_store(f,'one',ident)


def test_result_chunks_survive_local_loss_and_need_no_genos(env,tmp_path):
    c=env.c;store=c.ManagedJob(c.Scope(Folder()),'one',identity());state={'handle':'a'*32,'instance':'b'*32,'handle_token':'c'*64,'code_sha256':'d'*64}
    from test_partial import result_bytes
    raw=result_bytes(env,tmp_path);result={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    calls=[]
    class Remote:
        def call(self,op,**kw):
            calls.append(op);assert op=='READ'
            return dict(content=base64.b64encode(raw).decode(),offset=0,bytes=len(raw),sha256=result['sha256'])
    c.collect_result(store,Remote(),state,result,tmp_path)
    assert calls==['READ'] and store.value['phase']=='STRUCTURED'
    (tmp_path/'result.zip').unlink();calls.clear()
    c.collect_result(store,Remote(),state,result,tmp_path)
    assert calls==[] and (tmp_path/'result.zip').read_bytes()==raw


def test_bad_return_hash_never_publishes(env,tmp_path):
    c=env.c;store=c.ManagedJob(c.Scope(Folder()),'one',identity());state={'handle':'a'*32,'instance':'b'*32,'handle_token':'c'*64,'code_sha256':'d'*64}
    class Remote:
        def call(self,*a,**kw):return dict(content='eA==',offset=0,bytes=1,sha256='0'*64)
    with pytest.raises(ValueError,match='CHUNK_HASH'):c.collect_result(store,Remote(),state,{'bytes':1,'sha256':'f'*64},tmp_path)
    assert 'result_blob' not in store.value


def test_control_cancel_marker_is_bound_to_handle(env):
    store=env.c.ManagedJob(env.c.Scope(Folder()),'one',identity());store.value['compute']={'handle':'a'*32}
    store.folder.upload_stream('controls/one/cancel.json',io.BytesIO(json.dumps({'handle':'b'*32}).encode()))
    assert not env.c.cancelled(store,'one')
    store.folder.upload_stream('controls/one/cancel.json',io.BytesIO(json.dumps({'handle':'a'*32}).encode()))
    assert env.c.cancelled(store,'one')


def test_wire_error_secrets_are_not_echoed(env):
    a,_=opened(env)
    result=asyncio.run(env.api.service({},dict(API_TYPE='PUT',**a,slot='raw',offset=0,content='secret-invalid')))
    assert result['code']==1 and 'secret' not in json.dumps(result)


def test_retry_preserves_global_budget_and_requires_terminal(env,tmp_path):
    c=env.c;store=c.ManagedJob(c.Scope(Folder()),'one',identity());handle='a'*32
    store.value.update(compute={'handle':handle},phase='FAILED',deadline=time.time()+99,reserved_sql_calls=128,reserved_http_calls=256,log_offset=10)
    store.save();deadline=store.value['deadline']
    store.folder.upload_stream('controls/one/retry.json',io.BytesIO(json.dumps({'handle':handle}).encode()))
    c.apply_retry(store,'one',tmp_path)
    assert store.value['phase']=='NEW' and store.value['deadline']==deadline and store.value['reserved_sql_calls']==128
    assert store.value['reserved_http_calls']==256 and store.value['attempt_count']==2
    assert 'compute' not in store.value and 'log_offset' not in store.value
    assert 'attempts/'+handle+'/controller-checkpoint.json' in {p.lstrip('/') for p in store.folder.list_paths_in_partition()}
    store.value.update(compute={'handle':handle},phase='UNKNOWN')
    with pytest.raises(ValueError,match='CONFIRMED_TERMINAL'):c.apply_retry(store,'one',tmp_path)


def test_log_is_saved_to_dataiku_and_offset_survives_restart(env):
    c=env.c;store=c.ManagedJob(c.Scope(Folder()),'one',identity());state={'handle':'a'*32,'instance':'b'*32,'handle_token':'c'*64,'code_sha256':'d'*64}
    raw=b'PHASE STRUCTURE\nfixture exception\n';calls=[]
    class Remote:
        def call(self,op,**kw):
            calls.append(op)
            return dict(content=base64.b64encode(raw).decode(),offset=0,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    c.drain_log(store,Remote(),state,len(raw))
    restored=c.ManagedJob(store.folder,'one',identity())
    c.drain_log(restored,Remote(),state,len(raw))
    assert calls==['READ'] and restored.value['log_offset']==len(raw)
    assert any(p.endswith('.log') for p in store.folder.list_paths_in_partition())


@pytest.mark.parametrize('previous_index',[0,1,2])
def test_published_sdk_installer_apply_repeat_rollback(env,monkeypatch,previous_index):
    sys.path.insert(0,str(HERE.parent/'pipeline_recipes_20261027_r1'))
    sdk=module('original_sdk_tests',HERE.parent/'pipeline_recipes_20261027_r1/test_sdk.py')
    backend=sdk.Backend();project=sdk.DSSProject(backend,'LEGAL_RAG')
    ref=json.loads((env.dku/'REFERENCE.json').read_text())
    cfg=sdk.install_flow.install(project,ref['prior_compute_bootstrap'],'ehA8dpVm')
    updater=module('new_updater',env.dku/'updater.py');landing=Folder()
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda _:landing))
    # Field mix: R2 named inputs + R3 resume on 02.
    resume=(env.dku/'resume_source.txt').read_text()
    for stage,name,_,_ in updater.STAGES:
        backend.items['recipes'][name]['payload']=updater.variants(stage,cfg,ref,resume)[previous_index]
    original={n:v['payload'] for n,v in backend.items['recipes'].items()}
    bootstrap=(HERE/'bootstrap.txt').read_text()
    updater.update(project,env.dku,bootstrap,'apply')
    after={n:v['payload'] for n,v in backend.items['recipes'].items()}
    assert all('controller.execute' in code for code in after.values())
    assert updater.update(project,env.dku,bootstrap,'apply')==cfg
    updater.update(project,env.dku,bootstrap,'rollback')
    assert {n:v['payload'] for n,v in backend.items['recipes'].items()}==original


def test_sdk_unknown_code_causes_no_mutation(env,monkeypatch):
    sys.path.insert(0,str(HERE.parent/'pipeline_recipes_20261027_r1'))
    sdk=module('sdk_conflict',HERE.parent/'pipeline_recipes_20261027_r1/test_sdk.py')
    backend=sdk.Backend();project=sdk.DSSProject(backend,'LEGAL_RAG')
    ref=json.loads((env.dku/'REFERENCE.json').read_text())
    sdk.install_flow.install(project,ref['baseline_bootstrap'],'ehA8dpVm')
    before=json.dumps(backend.items,sort_keys=True)
    backend.items['recipes']['LEGAL_03_LOAD_SILVER_R1']['payload']='# custom\n'+backend.items['recipes']['LEGAL_03_LOAD_SILVER_R1']['payload']
    original=json.dumps(backend.items,sort_keys=True)
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda _:Folder()))
    updater=module('new_updater_conflict',env.dku/'updater.py')
    with pytest.raises(ValueError,match='UNKNOWN_RECIPE'):updater.update(project,env.dku,(HERE/'bootstrap.txt').read_text(),'apply')
    assert json.dumps(backend.items,sort_keys=True)==original


@pytest.mark.parametrize('baseline',['r1','r3','r4','r5','r6','r7'])
def test_genos_install_same_checkout_commit_verify_rollback(env,tmp_path,baseline):
    dev=tmp_path/'DEV';dev.mkdir()
    old=HERE.parent/'pipeline_stateless_20261027_r1/GENOS_DATAIKU_COMPUTE_20261027_R1.zip'
    if baseline=='r3':old=HERE.parent/'pipeline_preprocessor_20261027_r3/GENOS_DATAIKU_COMPUTE_20261027_R3.zip'
    old_hash='868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa' if baseline=='r1' else '8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1'
    if baseline=='r4':
        old=HERE.parent/'pipeline_pod_20261028_r4/GENOS_DATAIKU_COMPUTE_20261028_R4.zip'
        old_hash='8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685'
    if baseline=='r5':
        old=HERE.parent/'document_four_types_20261028_r1/GENOS_DATAIKU_COMPUTE_20261028_R5.zip'
        old_hash='78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c'
    if baseline=='r6':
        old=HERE.parent/'pipeline_partial_20261028_r6/GENOS_DATAIKU_COMPUTE_20261028_R6.zip'
        old_hash='31a3d3dd1b2be7b4618e40153bd08e4df8f12c768e57cb1458e856d985ddf548'
    if baseline=='r7':
        old=HERE.parent/'pipeline_skip_parser_20261028_r7/GENOS_DATAIKU_COMPUTE_20261028_R7.zip'
        old_hash='1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
    with zipfile.ZipFile(old) as z:
        for n in z.namelist():
            relative=n.split('/',1)[1];p=dev/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
    def run(*args):return subprocess.run(args,cwd=dev,text=True,capture_output=True,check=True)
    run('git','init','-q');run('git','config','user.email','fixture@example.invalid');run('git','config','user.name','Fixture')
    run('git','add','.');run('git','commit','-qm','baseline')
    shutil.copyfile(HERE/'GENOS_DATAIKU_COMPUTE_20261028_R8.zip',dev/'GENOS_DATAIKU_COMPUTE_20261028_R8.zip')
    installer=HERE/'install_compute.py'
    run(sys.executable,str(installer),'apply');run(sys.executable,str(installer),'apply')
    pins=json.loads((dev/'CODE_PINS.json').read_text())
    assert all(hashlib.sha256((dev/n).read_bytes()).hexdigest()==h for n,h in pins['files'].items())
    run(sys.executable,str(installer),'stage');run('git','commit','-qm','compute')
    run(sys.executable,str(installer),'check')
    run(sys.executable,str(installer),'rollback')
    assert hashlib.sha256((dev/'CODE_PINS.json').read_bytes()).hexdigest()==old_hash
