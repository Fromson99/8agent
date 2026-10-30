import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile
import pytest
from test_compute import env,opened,call,Folder,identity,HERE,module

OLD='8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1'


def config(env,monkeypatch):
    from lawrag.core import genos_pod as pod
    monkeypatch.setattr(pod,'root',lambda:env.root)
    p=env.tmp/'pod.yaml';p.write_text('layout:\n  layout_model_type: genos_layout\n  genos_layout:\n    endpoint: http://fixture.invalid/layout\nocr:\n  ocr_mode: disable\nenrichment: []\noutput:\n  format: docling\n')
    monkeypatch.setenv('GENOS_STRUCTURE_CONFIG',str(p))
    monkeypatch.setenv('GENOS_PREPROCESSOR_TRANSPORT','pod')
    return pod,p


def test_settings_use_pod_despite_obsolete_187_env(env,monkeypatch):
    from lawrag.core import genos_preprocessor as wire
    pod,p=config(env,monkeypatch)
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL','not-a-url')
    monkeypatch.setenv('GENOS_PREPROCESSOR_SHARED_ROOT','/nonexistent')
    settings=wire.Settings.from_env()
    assert isinstance(settings,pod.Settings) and settings.identity()['transport']=='same-pod'
    p.write_text(p.read_text()+'# modified config\n')
    assert settings.revision!=wire.Settings.from_env().revision


@pytest.mark.parametrize('bad',['missing','enrichment','placeholder','local_layout'])
def test_config_errors_fail_before_runtime(env,monkeypatch,bad):
    pod,p=config(env,monkeypatch)
    if bad=='missing':p.unlink()
    elif bad=='enrichment':p.write_text(p.read_text().replace('enrichment: []','enrichment: [toc]'))
    elif bad=='placeholder':p.write_text(p.read_text().replace('fixture.invalid','<LAYOUT_SERVING_ID>'))
    else:p.write_text(p.read_text().replace('layout_model_type: genos_layout','layout_model_type: docling_layout'))
    with pytest.raises(ValueError,match='POD_'):pod.Settings.from_env()


def test_real_preflight_missing_runtime_does_not_accept_open(env,monkeypatch):
    pod,p=config(env,monkeypatch)
    actual=module('real_pod_preflight',env.root/'parser_config.py')
    # Current local image intentionally lacks the GENOS docling fork.
    result=actual.inspect(env.root)
    assert not result['ready'] and result['errors']
    assert 'secret' not in json.dumps(result)
    monkeypatch.setattr(env.api,'parser_config',actual)
    health=env.api.handle({'API_TYPE':'HEALTH'})
    arc={'sha256':'a'*64,'bytes':1}
    with pytest.raises(ValueError):
        env.api.handle(dict(API_TYPE='OPEN',handle='a'*32,handle_token='b'*64,instance=health['instance'],code_sha256=health['code_sha256'],parser_config_sha256='e'*64,archives={'raw':arc,'support':arc},deadline=time.time()+600))
    assert not env.api.HANDLES


def old_state(env):
    new={**identity(),'version':env.c.PROTOCOL,'service_code':env.c.EXPECTED}
    oldident={**new,'service_code':OLD};folder=Folder()
    store=env.c.ManagedJob(env.c.Scope(folder),'same',oldident)
    store.value.update(phase='FAILED',model_execution_possible=True,deadline=time.time()+900,
        reserved_sql_calls=192,reserved_http_calls=512,attempt_count=1,migration_checked=True,
        compute={'handle':'a'*32,'code_sha256':OLD},
        last_observed={'handle':'a'*32,'state':'FAILED'})
    return folder,store,new


@pytest.mark.parametrize('case',['zero','nonzero','missing','tampered','count_mismatch','exhausted'])
def test_r3_migration_budget_proof(env,tmp_path,case):
    folder,store,new=old_state(env)
    n=1 if case=='nonzero' else 0
    ledger={'calls':n,'events':[{'status':'RESERVED'}]*n}
    if case=='count_mismatch':ledger['events']=[{'status':'RESERVED'}]
    h=hashlib.sha256(json.dumps(ledger,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    summary=tmp_path/'summary.json';summary.write_text(json.dumps({'reserved_model_calls':n,'ledger_errors':[]}))
    journal=tmp_path/'ledger.json';journal.write_text(json.dumps({'state':ledger,'sha256':h}))
    z=tmp_path/'audit.zip'
    arc=env.t.pack({'audit/review-summary.json':summary,'audit/structure/doc/model-calls/x.json':journal},z,metadata={})
    if case!='missing':
        store.value['audit_blob']=store.put_blob(z)
        store.value['last_observed']['audit']={k:arc[k] for k in ('bytes','sha256')}
    if case=='tampered':folder.files[env.c.NAMESPACE+store.value['audit_blob']['path']]+=b'x'
    if case=='exhausted':store.value['attempt_count']=3
    store.save();before=dict(folder.files);olddeadline=store.value['deadline']
    if case!='zero':
        with pytest.raises(ValueError):env.c.open_store(folder,'same',new)
        assert folder.files==before
    else:
        migrated=env.c.open_store(folder,'same',new)
        assert migrated.value['deadline']==olddeadline and migrated.value['attempt_count']==2
        assert migrated.value['reserved_http_calls']==512 and migrated.value['reserved_sql_calls']==192
        assert migrated.value['upgrade_history'][-1]['zero_review_proof']['reserved_review_calls']==0
        assert all(folder.files[k]==v for k,v in before.items())


def test_failure_audit_returns_generated_pdf_without_success(env,tmp_path):
    a,_=opened(env);h=env.api.HANDLES[a['handle']];work=h['folder']/'workspace'
    data=work/'01_DATA';p=data/'RAW/internal/a.pdf';p.parent.mkdir(parents=True);p.write_bytes(b'%PDF-fixture')
    source=data/'RAW/internal/a.doc';source.write_bytes(b'source')
    cat=data/'CATALOG/RAW_DERIVATIVES.json';cat.parent.mkdir()
    cat.write_text(json.dumps({'files':{'RAW/internal/a.pdf':{'kind':'native_rendered_pdf','sha256':env.t.sha(p),'origin':'RAW/internal/a.doc','origin_sha256':env.t.sha(source)}}}))
    env.api.review_audit.export(h['folder'])
    with zipfile.ZipFile(h['folder']/'audit.zip') as z:
        assert z.read('audit/derivatives/RAW/internal/a.pdf')==p.read_bytes()
        assert not any(n.startswith('query/') for n in z.namelist())
    p.write_bytes(b'changed')
    with pytest.raises(ValueError,match='DERIVED_PDF_HASH_CHANGED'):env.api.review_audit.export(h['folder'])


def test_new_file_collision_does_not_modify_checkout(env,tmp_path):
    import subprocess,shutil
    dev=tmp_path/'DEV';dev.mkdir()
    with zipfile.ZipFile(HERE.parent/'pipeline_preprocessor_20261027_r3/GENOS_DATAIKU_COMPUTE_20261027_R3.zip') as z:
        for n in z.namelist():
            p=dev/n.split('/',1)[1];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
    subprocess.run(['git','init','-q',str(dev)],check=True)
    custom=dev/'pod_parser.py';custom.write_text('# user source\n')
    before=(dev/'CODE_PINS.json').read_bytes()
    shutil.copyfile(HERE/'GENOS_DATAIKU_COMPUTE_20261028_R4.zip',dev/'GENOS_DATAIKU_COMPUTE_20261028_R4.zip')
    result=subprocess.run([sys.executable,str(HERE/'install_compute.py'),'apply'],cwd=dev,text=True,capture_output=True)
    assert result.returncode and 'NEW_FILE_COLLISION' in result.stderr
    assert custom.read_text()=='# user source\n' and before==(dev/'CODE_PINS.json').read_bytes()
