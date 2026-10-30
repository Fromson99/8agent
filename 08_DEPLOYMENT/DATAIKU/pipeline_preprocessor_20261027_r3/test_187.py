import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
import zipfile
import pytest
from test_compute import env, opened, call, Folder, identity, HERE
from test_preprocessor import failed


@pytest.mark.parametrize('mode',['auto','chunks','docling'])
def test_existing_187_modes_and_endpoint(env,monkeypatch,mode):
    monkeypatch.setenv('GENOS_PREPROCESSOR_ID','187')
    monkeypatch.setenv('GENOS_PREPROCESSOR_RESPONSE_MODE',mode)
    report=env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']
    assert report['ready'] and report['response_mode']==mode
    settings=env.api.parser_config.settings_module(str(env.root)).Settings.from_env()
    assert settings.url=='http://preprocessor-187:8080/run'


@pytest.mark.parametrize('name,value',[
    ('GENOS_LLM_URL',''),('LLM_BACKEND','openrouter'),
    ('STRUCTURE_RECIPE_VLM','off'),('GENOS_LLM_URL','http://user:secret@fixture.invalid')])
def test_missing_or_external_review_configuration_never_opens(env,monkeypatch,name,value):
    monkeypatch.delenv('GENOS_BASE_URL',raising=False)
    monkeypatch.setenv(name,value)
    status=env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']
    assert status['ready'] is False and 'PREPROCESSOR_REVIEW_CONFIG_REQUIRED' in status['errors']
    assert not env.api.HANDLES and 'secret' not in json.dumps(status)


def test_review_config_drift_does_not_allow_run(env,monkeypatch):
    a,_=opened(env);h=env.api.HANDLES[a['handle']];h['received']={'raw':1,'support':1}
    monkeypatch.setenv('GENOS_LLM_MODEL','different-model')
    with pytest.raises(ValueError,match='CONFIG_CHANGED'):call(env,a,'RUN')
    assert call(env,a,'CANCEL')['state']=='CANCELLED'


def test_r2_confirmed_failure_upgrade_preserves_budget(env):
    folder,old,new=failed(env)
    code='6903032227143a1b94fe0eec8a701592d819a2e08f061ce76453b42df687121c'
    old.value['binding']['service_code']=code
    old.value['compute']['code_sha256']=code
    old.value['attempt_count']=2
    old.save();before=dict(folder.files)
    store=env.c.open_store(folder,'same',new)
    assert store.value['attempt_count']==3
    assert store.value['reserved_http_calls']==512
    assert all(folder.files[n]==b for n,b in before.items())


def test_r3_retry_never_resets_model_budget(env,tmp_path):
    store=env.c.ManagedJob(env.c.Scope(Folder()),'same',identity())
    store.value.update(phase='FAILED',model_execution_possible=True,attempt_count=1,
                       deadline=time.time()+900,compute={'handle':'a'*32})
    marker={'handle':'a'*32}
    store.folder.upload_stream('controls/same/retry.json',io.BytesIO(json.dumps(marker).encode()))
    before=json.dumps(store.value,sort_keys=True)
    with pytest.raises(ValueError,match='PRESERVED_LEDGER_RESUME'):
        env.c.apply_retry(store,'same',tmp_path)
    assert json.dumps(store.value,sort_keys=True)==before


def test_failure_audit_s3_hash_gate_and_close_receipt(env,tmp_path):
    a,_=opened(env);h=env.api.HANDLES[a['handle']]
    evidence=h['folder']/'workspace/01_DATA/STRUCTURE/fixture/checkpoints/model-calls'
    evidence.mkdir(parents=True)
    ledger={'calls':1,'events':[{'status':'RESERVED'}]}
    digest=hashlib.sha256(json.dumps(ledger,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    (evidence/'call.json').write_text(json.dumps({'state':ledger,'sha256':digest}))
    (evidence.parent/'response.json').write_text('{"failure":"synthetic"}')
    env.api.review_audit.export(h['folder'])
    h.update(state='FAILED',audit=env.api.digest_file(h['folder']/'audit.zip'))
    with pytest.raises(ValueError,match='AUDIT_RECEIPT_REQUIRED'):call(env,a,'CLOSE')
    folder=Folder();store=env.c.ManagedJob(env.c.Scope(folder),'same',identity())
    store.value.update(phase='FAILED')
    class Wire:
        def call(self,op,**kw):return env.api.handle({'API_TYPE':op,**kw})
    state={**a,'code_sha256':env.api.t.sha(env.root/'CODE_PINS.json')}
    env.c.collect_audit(store,Wire(),state,h['audit'],tmp_path)
    assert store.value['phase']=='FAILED' and 'result_blob' not in store.value
    assert store.value['audit_blob']
    assert any('/audit/' in name for name in folder.files)
    with zipfile.ZipFile(tmp_path/'compute-audit.zip') as z:
        assert json.loads(z.read('audit/review-summary.json'))['reserved_model_calls']==1
    assert call(env,a,'CLOSE',audit_sha256=h['audit']['sha256'])['closed']


def test_corrupt_audit_never_publishes(env,tmp_path):
    store=env.c.ManagedJob(env.c.Scope(Folder()),'same',identity())
    class Wire:
        def call(self,op,**kw):
            return {'content':'eA==','offset':0,'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
    state={'handle':'a'*32,'handle_token':'b'*64,'instance':'c'*32,'code_sha256':'d'*64}
    with pytest.raises(ValueError,match='AUDIT_HASH'):
        env.c.collect_audit(store,Wire(),state,{'bytes':1,'sha256':'0'*64},tmp_path)
    assert 'audit_blob' not in store.value


def test_actual_worker_failure_retains_audit_before_terminal_close(env):
    a,_=opened(env);h=env.api.HANDLES[a['handle']]
    h['state']='RUNNING'
    # No input archive: real worker fails before parser/model, supervisor archives evidence.
    env.api.run_compute(h)
    observed=call(env,a,'POLL')
    assert observed['state']=='FAILED' and observed['audit'] and not observed['audit_error']
    with zipfile.ZipFile(h['folder']/'audit.zip') as z:
        assert 'audit/compute.log' in z.namelist()
        assert json.loads(z.read('audit/review-summary.json'))['reserved_model_calls']==0
    with pytest.raises(ValueError,match='AUDIT_RECEIPT_REQUIRED'):call(env,a,'CLOSE')


def test_bad_ledger_is_retained_as_failed_diagnostic_not_success(env):
    a,_=opened(env);folder=env.api.HANDLES[a['handle']]['folder']
    p=folder/'workspace/01_DATA/STRUCTURE/fixture/model-calls/call.json'
    p.parent.mkdir(parents=True);p.write_text('{"unfinished":true}')
    with pytest.raises(ValueError,match='LEDGER_MISMATCH'):
        env.api.review_audit.inventory(folder/'workspace')
    env.api.review_audit.export(folder)
    with zipfile.ZipFile(folder/'audit.zip') as z:
        summary=json.loads(z.read('audit/review-summary.json'))
        assert summary['reserved_model_calls'] is None and summary['ledger_errors']
        assert z.read('audit/structure/fixture/model-calls/call.json')==p.read_bytes()


def test_genos_upgrade_from_r2_and_rollback(env,tmp_path):
    dev=tmp_path/'r2-dev';dev.mkdir()
    with zipfile.ZipFile(HERE.parent/'pipeline_preprocessor_20261027_r2/GENOS_DATAIKU_COMPUTE_20261027_R2.zip') as z:
        for name in z.namelist():
            p=dev/name.split('/',1)[1];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
    def run(*a):return subprocess.run(a,cwd=dev,check=True,capture_output=True,text=True)
    run('git','init','-q');run('git','config','user.email','fixture@example.invalid');run('git','config','user.name','Fixture')
    run('git','add','.');run('git','commit','-qm','r2')
    old=(dev/'CODE_PINS.json').read_bytes()
    shutil.copyfile(HERE/'GENOS_DATAIKU_COMPUTE_20261027_R3.zip',dev/'GENOS_DATAIKU_COMPUTE_20261027_R3.zip')
    installer=str(HERE/'install_compute.py')
    run(sys.executable,installer,'apply');run(sys.executable,installer,'stage')
    run('git','commit','-qm','r3');run(sys.executable,installer,'check')
    run(sys.executable,installer,'rollback')
    assert (dev/'CODE_PINS.json').read_bytes()==old and not (dev/'review_audit.py').exists()
