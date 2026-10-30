"""Focused failures against the actual packaged service/controller, synthetic inputs."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import pytest
from test_compute import env, opened, call, Folder, identity


def test_health_config_missing_never_creates_handle(env, monkeypatch, capsys):
    monkeypatch.delenv('GENOS_PREPROCESSOR_ID')
    monkeypatch.delenv('GENOS_PREPROCESSOR_SHARED_ROOT')
    health=env.api.handle({'API_TYPE':'HEALTH'})
    assert health['preprocessor']['ready'] is False
    assert health['preprocessor']['errors']==['PREPROCESSOR_ENDPOINT_REQUIRED','PREPROCESSOR_SHARED_ROOT_REQUIRED']
    class Remote:
        def call(self, op): assert op=='HEALTH';return health
    with pytest.raises(ValueError,match='NOT_READY'):env.c.health(Remote())
    arc={'sha256':'f'*64,'bytes':1}
    with pytest.raises(ValueError,match='ENDPOINT_REQUIRED'):
        env.api.handle({'API_TYPE':'OPEN','handle':'a'*32,'handle_token':'b'*64,
                        'instance':health['instance'],'code_sha256':health['code_sha256'],
                        'archives':{'raw':arc,'support':arc},'deadline':time.time()+600})
    assert not env.api.HANDLES
    assert 'PREPROCESSOR_ENDPOINT_REQUIRED' in capsys.readouterr().out


@pytest.mark.parametrize('key,value,error',[
    ('GENOS_PDF_PARSER','local','MODE_REQUIRED'),
    ('GENOS_PREPROCESSOR_ID','bad','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_URL','https://u:secret@example.invalid/run','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_URL','https://example.invalid/ui/761','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_SHARED_ROOT','relative','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_SHARED_ROOT','/nonexistent/parser/shared','SHARED_ROOT_UNAVAILABLE'),
    ('GENOS_PREPROCESSOR_REMOTE_ROOT','relative','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_TIMEOUT','0','CONFIG_INVALID'),
    ('GENOS_PREPROCESSOR_RESPONSE_MODE','broken','RESPONSE_MODE_INVALID'),
])
def test_invalid_environment_is_bounded_public_error(env,monkeypatch,key,value,error):
    monkeypatch.setenv(key,value)
    status=env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']
    assert not status['ready'] and any(error in e for e in status['errors'])
    assert 'secret' not in json.dumps(status)


def test_url_precedence_defaults_secret_and_symlink(env,monkeypatch,tmp_path):
    monkeypatch.delenv('GENOS_PDF_PARSER')
    monkeypatch.delenv('GENOS_PREPROCESSOR_RESPONSE_MODE')
    monkeypatch.setenv('GENOS_PREPROCESSOR_ID','invalid-but-url-has-priority')
    monkeypatch.setenv('GENOS_PREPROCESSOR_URL','http://parser.example:8080/parser')
    monkeypatch.setenv('GENOS_PREPROCESSOR_API_KEY','never-publish-this')
    status=env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']
    assert status['ready'] and status['response_mode']=='auto'
    assert 'never-publish-this' not in json.dumps(status) and 'parser.example' not in json.dumps(status)
    monkeypatch.setenv('GENOS_PREPROCESSOR_API_KEY','rotated-secret')
    assert env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']['config_sha256']==status['config_sha256']
    linked=tmp_path/'symlink';linked.symlink_to(tmp_path/'shared',target_is_directory=True)
    monkeypatch.setenv('GENOS_PREPROCESSOR_SHARED_ROOT',str(linked))
    assert env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']['ready'] is False


def test_changed_environment_blocks_run_but_allows_cancel(env,monkeypatch):
    auth,_=opened(env)
    h=env.api.HANDLES[auth['handle']];h['received']={'raw':1,'support':1}
    monkeypatch.setenv('GENOS_PREPROCESSOR_ID','988')
    with pytest.raises(ValueError,match='CONFIG_CHANGED'):call(env,auth,'RUN')
    assert h['state']=='RECEIVING' and h['child'] is None
    assert call(env,auth,'CANCEL')['state']=='CANCELLED'


def failed(env,folder=None):
    c=env.c;folder=folder or Folder()
    new={**identity(),'version':c.PROTOCOL,'service_code':c.EXPECTED}
    oldident={**new,'service_code':c.checkpoint_upgrade.PREVIOUS_CODE}
    old=c.ManagedJob(c.Scope(folder),'same',oldident)
    old.value.update(phase='FAILED',deadline=time.time()+900,reserved_sql_calls=192,
                     reserved_http_calls=512,attempt_count=1,migration_checked=True,
                     compute={'handle':'a'*32,'code_sha256':oldident['service_code']},
                     last_observed={'handle':'a'*32,'state':'FAILED','error':'NATIVE_PIPELINE_FAILED'},log_offset=99)
    old.save()
    return folder,old,new


def test_failed_upgrade_preserves_history_budget_and_is_idempotent(env):
    folder,old,new=failed(env);before=dict(folder.files);deadline=old.value['deadline']
    migrated=env.c.open_store(folder,'same',new)
    assert migrated.value['phase']=='NEW' and migrated.value['attempt_count']==2
    assert migrated.value['deadline']==deadline and migrated.value['reserved_sql_calls']==192
    assert migrated.value['reserved_http_calls']==512 and 'compute' not in migrated.value
    assert migrated.value['upgrade_history'][0]['previous_handle']=='a'*32
    assert all(folder.files[k]==v for k,v in before.items())
    sequence=migrated.seq
    assert env.c.open_store(folder,'same',new).seq==sequence


@pytest.mark.parametrize('change,error',[
    ({'phase':'UNKNOWN'},'CONFIRMED_TERMINAL'),
    ({'phase':'COMPUTING'},'CONFIRMED_TERMINAL'),
    ({'last_observed':{'handle':'b'*32,'state':'FAILED'}},'CONFIRMED_TERMINAL'),
    ({'result_blob':{'sha256':'x'}},'RETURN_EXISTS'),
    ({'attempt_count':3},'ATTEMPT_BUDGET'),
    ({'deadline':1},'DEADLINE'),
])
def test_failed_upgrade_refuses_unsafe_or_exhausted_state(env,change,error):
    folder,old,new=failed(env);old.value.update(change);old.save();before=dict(folder.files)
    with pytest.raises(ValueError,match=error):env.c.open_store(folder,'same',new)
    assert folder.files==before


def test_upgrade_refuses_changed_input_and_tampered_checkpoint(env):
    folder,old,new=failed(env);before=dict(folder.files)
    changed={**new,'input':{'different':True}}
    with pytest.raises(ValueError,match='BINDING_CHANGED'):env.c.open_store(folder,'same',changed)
    assert folder.files==before
    latest=env.c.legacy_state(env.c.Scope(folder),'same')
    path=env.c.NAMESPACE+latest['path'].lstrip('/')
    folder.files[path]+=b' '
    with pytest.raises(ValueError,match='HASH'):env.c.open_store(folder,'same',new)


def test_worker_preflight_happens_before_input_extraction(env,monkeypatch,tmp_path):
    monkeypatch.delenv('GENOS_PREPROCESSOR_ID')
    target=tmp_path/'compute';target.mkdir()
    with pytest.raises(ValueError,match='ENDPOINT_REQUIRED'):
        env.w.compute(target,'test',{},'0'*64)
    assert list(target.iterdir())==[]


def test_worker_forwards_env_and_has_no_local_cli_override(env,monkeypatch,tmp_path):
    monkeypatch.delenv('GENOS_PDF_PARSER');monkeypatch.delenv('GENOS_PREPROCESSOR_RESPONSE_MODE')
    monkeypatch.setenv('GENOS_PREPROCESSOR_API_KEY','private-forwarded-key')
    monkeypatch.setenv('GENOS_PREPROCESSOR_REMOTE_ROOT','/server/shared')
    parser_sha=env.api.handle({'API_TYPE':'HEALTH'})['preprocessor']['config_sha256']
    target=tmp_path/'compute';target.mkdir()
    raw=tmp_path/'input';raw.write_bytes(b'fixture')
    arcs={}
    for slot,files,metadata in [
        ('raw',{'01_DATA/RAW/internal/team/mock.pdf':raw},{}),
        ('support',{'01_DATA/CATALOG/mock.json':raw},{'glossary_config_sha256':env.t.sha(env.root/'00_SYSTEM/GLOSSARY_PIPELINE.json')})]:
        result=env.t.pack(files,target/(slot+'.zip'),metadata=metadata)
        arcs[slot]={k:result[k] for k in ('sha256','bytes')}
    runs=[]
    def run(command,**kwargs):
        runs.append((command,kwargs))
        assert kwargs['env']['GENOS_PDF_PARSER']=='preprocessor'
        assert kwargs['env']['GENOS_PREPROCESSOR_RESPONSE_MODE']=='auto'
        assert kwargs['env']['GENOS_PREPROCESSOR_API_KEY']=='private-forwarded-key'
        assert kwargs['env']['GENOS_PREPROCESSOR_REMOTE_ROOT']=='/server/shared'
        assert '--pdf-parser' not in command
        assert kwargs['check'] is True
    monkeypatch.setattr(env.w.subprocess,'run',run)
    env.w.compute(target,'fixture',arcs,parser_sha)
    assert len(runs)==4
    assert runs[0][0][runs[0][0].index('--structure-vlm')+1]=='on'
