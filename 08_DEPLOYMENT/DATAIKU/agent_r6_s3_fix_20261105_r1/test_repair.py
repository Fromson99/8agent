"""Reproduce R6 default-bucket failure and execute the delivered recovery cell."""
import ast
import copy
import fcntl
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
R6=HERE.parent/'agent_layer_zip_20261105_r6'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


old=load('dss_folder_contract_fixture',HERE.parent/'gold_zip_upload_20261104_r1/test_notebook.py')
fix=load('r6_s3_fix_contract',HERE/'repair.py')
tree=ast.parse((R6/'DATAIKU_SETUP_R6.txt').read_text())
BOOTSTRAP=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='BOOTSTRAP'))
PARAMS=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='PARAMS'))


@pytest.fixture
def env(monkeypatch,tmp_path):
    runtime=tmp_path/'runtime'
    with zipfile.ZipFile(R6/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip') as z:z.extractall(runtime)
    monkeypatch.syspath_prepend(str(runtime))
    for name in ('transport','archive_input','dev_guard','flow_runtime'):
        monkeypatch.delitem(sys.modules,name,raising=False)
    installer=load('sealed_r6_install',runtime/'flow_install.py')
    project=old.Project();project.project_key='TEST_LEGAL'
    project.jobs=[{'def':{'id':'Build_LGL_AGENT_R6_PROD_03_LOAD_OUT_2026'},'state':'FAILED','stableState':True}]
    project.list_jobs=lambda:project.jobs
    monkeypatch.setattr(old.Scenario,'get_current_run',lambda s:None,raising=False)
    monkeypatch.setattr(old.Recipe,'move_to_zone',lambda r,z:None,raising=False)
    source=project.folders['ehA8dpVm'];source.type='S3'
    source.params={'connection':'OBS','bucket':'READABLE_BUCKET','path':'/dataiku/${projectKey}/${odbId}'}
    project.stores={};project.old_readable=False;project.fail_write=None;project.bad_effective=False
    def info(folder,sensitive_info=False):
        assert sensitive_info is False
        params=folder.params
        root=params['path'].replace('${projectKey}',project.project_key).replace('${odbId}',folder.id)
        if project.bad_effective and folder.id!=source.id:
            root=source.params['path'].replace('${projectKey}',project.project_key).replace('${odbId}',source.id)
        return {'type':'S3','accessInfo':{'bucket':params.get('bucket','WRONG_DEFAULT'), 'root':root,'secret':'never-print-secret'}}
    def store(folder):
        access=info(folder)['accessInfo'];key=(access['bucket'],access['root'])
        if key[0]!='READABLE_BUCKET' and not project.old_readable:
            raise Exception('Either the bucket does not exist or you are not authorized (S3 Status Code: 404)')
        return project.stores.setdefault(key,{})
    def upload(folder,path,stream):
        if folder.id==project.fail_write:raise PermissionError('fixture S3 write denied')
        store(folder)[path.lstrip('/')]=stream.read()
    monkeypatch.setattr(old.Folder,'get_info',info,raising=False)
    monkeypatch.setattr(old.Folder,'list_paths_in_partition',lambda f:['/'+n for n in store(f)])
    monkeypatch.setattr(old.Folder,'get_download_stream',lambda f,p:io.BytesIO(store(f)[p.lstrip('/')]))
    monkeypatch.setattr(old.Folder,'upload_stream',upload)
    create=project.create_managed_folder
    def new_folder(*args,**kwargs):
        folder=create(*args,**kwargs)
        folder.params.update(bucket='WRONG_DEFAULT',path='/dataiku/${projectKey}/${odbId}')
        return folder
    project.create_managed_folder=new_folder
    store(source).update({name:(R6/name).read_bytes() for name in fix.SAMPLES})
    source_before=copy.deepcopy(store(source))
    api=SimpleNamespace(api_client=lambda:project,Folder=lambda key,**kw:project.folders[key],
                        get_custom_variables=lambda:{'AGENT_FLOW_TRIAL':'trial-001','AGENT_PIPELINE_TOKEN':'never-print-secret'})
    monkeypatch.setitem(sys.modules,'dataiku',api)
    params=dict(PARAMS,CODE_FOLDER_ID=source.id,INPUT_FOLDER_ID=source.id,SUPPORT_FOLDER_ID=source.id,
                INPUT_MODE='ZIP',ENVIRONMENT='PROD',WORK_DIR=str(tmp_path/'work'))
    cfg=installer.install(params,BOOTSTRAP)
    first=project.folders[cfg['folders']['submit']]
    with pytest.raises(Exception,match='bucket.*404'):
        first.upload_stream('trial-001/intent.json',io.BytesIO(b'original intent'))
    request_dir=Path(cfg['WORK_DIR'])/'agent-layer-zip-r6'/project.project_key/'PROD/trial-001'
    request_dir.mkdir(parents=True)
    request=request_dir/'request.json'
    request.write_text(json.dumps({'opened':False,'intent':{'context':{'project':project.project_key}},
                                  'auth':{'handle_token':'private-fixture-token'},'deadline':1799000000}))
    before={k:copy.deepcopy(f.params) for k,f in project.folders.items()}
    scripts={k:r.script for k,r in project.recipes.items()}
    def run(mode='REPAIR'):return fix.repair(api,BOOTSTRAP,mode=mode)
    return SimpleNamespace(project=project,source=source,source_before=source_before,store=store,
                           cfg=cfg,request=request,original_request=request.read_bytes(),before=before,
                           scripts=scripts,run=run,api=api)


def test_exact_delivered_cell_repairs_original_r6_and_preserves_state(env,capsys):
    ns={};exec(compile((HERE/'DATAIKU_R6_S3_FIX_R1.txt').read_text(),'<delivered R6 S3 fix>','exec'),ns)
    assert ns['REPAIR_RESULT']['status']=='REPAIR_COMPLETE'
    assert set(env.before)==set(env.project.folders)
    assert env.scripts=={k:r.script for k,r in env.project.recipes.items()}
    assert env.source_before==env.store(env.source)
    assert env.source.params==env.before[env.source.id]
    assert env.request.read_bytes()==env.original_request
    assert all(f.params==env.source.params for f in env.project.folders.values())
    assert next(iter(env.project.scenarios.values())).runs==0
    assert 'never-print-secret' not in capsys.readouterr().out


def test_repeat_and_pre_run_rollback_preserve_objects(env):
    env.run();env.run();objects=copy.deepcopy(env.project.stores)
    assert env.run('ROLLBACK')['status']=='ROLLBACK_COMPLETE'
    assert env.before=={k:f.params for k,f in env.project.folders.items()}
    assert env.project.stores==objects
    assert env.run()['status']=='REPAIR_COMPLETE'


def test_probe_permission_failure_resumes_with_original_backup(env):
    env.project.fail_write=env.cfg['folders']['wait']
    with pytest.raises(PermissionError):env.run()
    env.project.fail_write=None
    result=env.run()
    assert result['status']=='REPAIR_COMPLETE'
    assert result['before']['submit']['bucket']=='WRONG_DEFAULT'
    assert env.request.read_bytes()==env.original_request


@pytest.mark.parametrize('change,match',[
    ('active','JOB_IS_RUNNING'),('recipe','RECIPE_CODE_CHANGED'),('source_path','PATH_TEMPLATE'),
    ('opened','ALREADY_OPENED'),('missing_request','PRE_OPEN_REQUEST'),('existing','EXISTING_CHECKPOINTS'),
    ('connection','CONNECTION_CHANGED'),('sample','SAMPLE_ZIP_NOT_READABLE')])
def test_incompatible_state_stops_before_remote_change(env,change,match):
    if change=='active':env.project.jobs[0].update(state='RUNNING',stableState=False)
    if change=='recipe':next(iter(env.project.recipes.values())).script='# edited\n'+next(iter(env.project.recipes.values())).script
    if change=='source_path':env.source.params['path']='/fixed-source'
    if change=='opened':env.request.write_text(json.dumps({'opened':True}))
    if change=='missing_request':env.request.unlink()
    if change=='existing':
        env.project.old_readable=True
        env.store(env.project.folders[env.cfg['folders']['wait']])['trial-001/ready.json']=b'preserve'
    if change=='connection':env.project.folders[env.cfg['folders']['wait']].params['connection']='OTHER'
    if change=='sample':env.store(env.source)['LAW_SAMPLE_R2.zip']=b'changed'
    before=copy.deepcopy({k:f.params for k,f in env.project.folders.items()})
    with pytest.raises(ValueError,match=match):env.run()
    assert before=={k:f.params for k,f in env.project.folders.items()}


def test_flow_lock_prevents_relocation_during_recipe(env):
    with (env.request.parent/'flow.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):env.run()
    assert env.before=={k:f.params for k,f in env.project.folders.items()}


def test_resolved_input_collision_is_detected_before_probe(env):
    env.project.bad_effective=True
    with pytest.raises(ValueError,match='LOCATION_OVERLAP'):env.run()
    assert len(env.project.stores)==1
    env.project.bad_effective=False
    assert env.run()['status']=='REPAIR_COMPLETE'


def test_rollback_refuses_to_hide_new_business_receipts(env):
    env.run()
    env.store(env.project.folders[env.cfg['folders']['submit']])['trial-001/intent.json']=b'preserve'
    current=copy.deepcopy({k:f.params for k,f in env.project.folders.items()})
    with pytest.raises(ValueError,match='EXISTING_CHECKPOINTS'):env.run('ROLLBACK')
    assert current=={k:f.params for k,f in env.project.folders.items()}


def test_unrelated_running_job_does_not_block_repair(env):
    env.project.jobs=[{'def':{'id':'other-task'},'stableState':False,'state':'RUNNING'}]
    assert env.run()['status']=='REPAIR_COMPLETE'


def test_changed_settings_after_backup_are_preserved(env):
    env.run();env.project.folders[env.cfg['folders']['wait']].params['bucket']='USER_EDIT'
    before=copy.deepcopy({k:f.params for k,f in env.project.folders.items()})
    with pytest.raises(ValueError,match='RESULT_CHANGED_SINCE_BACKUP'):env.run()
    assert before=={k:f.params for k,f in env.project.folders.items()}
