"""Extended discovery through the sealed GENOS handler; no model/database execution."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile
import pytest
import discovery as x

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_busy_inspection_20261027_r1'
spec=importlib.util.spec_from_file_location('prior_inspection_tests',BASE/'test_inspection.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
d=base.d;env=base.env


def fixture_project(env):
    folders={k:base.Folder() for k in ['ehA8dpVm','raw','structured','load','legacy-old']}
    known=[{'id':k,'name':k} for k in folders]
    project=SimpleNamespace(list_managed_folders=lambda:known)
    dataiku=SimpleNamespace(default_project_key=lambda:d.PROJECT,
        get_custom_variables=lambda:env.variables,
        api_client=lambda:SimpleNamespace(get_project=lambda key:project),
        Folder=lambda fid,project_key=None:folders[fid])
    old=copy.deepcopy(env.checkpoint)
    old['binding']['input']['folder_id']='legacy-old'
    state=json.loads(env.state_path.read_text())
    old['client'].update(archives=state['archives'],deadline=state['deadline'])
    old['deadline']=state['deadline']
    folders['legacy-old'].put('run_20261023_01_20261023_01',old)
    current=copy.deepcopy(old)
    current['binding'].update(version='recipes-20261027-r1',input={'landing':'ehA8dpVm','raw':'raw'})
    current['client']['job_id']='2'*32
    folders['structured'].put('recipes_20261027_r1',current)
    env.calls.clear()
    return folders,known,dataiku,old,current


def test_discovers_old_folder_that_three_folder_inspection_missed(env,capsys):
    folders,known,dataiku,old,current=fixture_project(env)
    before=copy.deepcopy({k:f.data for k,f in folders.items()})
    rows,summary=x.discover(d,dataiku)
    blocked=[r for r in rows if r.get('blocks_new_start')]
    assert len(blocked)==1 and blocked[0]['folder_id']=='legacy-old'
    assert blocked[0]['status']=='FAILED' and blocked[0]['phase']=='STRUCTURE'
    missing=next(r for r in rows if r.get('job_name')=='recipes_20261027_r1')
    assert missing['status']=='STATUS_UNCONFIRMED' and missing['error_code']=='JOB_LOST'
    assert summary['blocking_job_ids']==[env.auth['job_id']]
    assert before=={k:f.data for k,f in folders.items()}
    assert {c['API_TYPE'] for c in env.calls}=={'HEALTH','STATUS'}
    out=capsys.readouterr().out
    assert env.variables['LEGAL_PIPELINE_TOKEN'] not in out and env.auth['job_token'] not in out


def test_duplicate_capability_queried_once(env):
    folders,known,dataiku,old,current=fixture_project(env)
    current['client']=copy.deepcopy(old['client'])
    folders['structured'].data.clear();folders['structured'].put('same-other-checkpoint',current)
    rows,summary=x.discover(d,dataiku)
    assert summary['http_calls']==2 and summary['blocking_job_ids']==[env.auth['job_id']]


@pytest.mark.parametrize('change',['endpoint','code','instance','folder','client','deadline'])
def test_mismatched_binding_cannot_be_used_to_query_a_job(env,change):
    folders,known,dataiku,old,current=fixture_project(env)
    folders['structured'].data.clear()
    if change=='endpoint':old['binding']['service_url_sha256']='0'*64
    elif change=='code':old['binding']['service_code']='0'*64
    elif change=='instance':old['client']['instance']='9'*32
    elif change=='folder':old['binding']['input']['folder_id']='unrelated'
    elif change=='client':old['binding']['input']['client_sha256']='0'*64
    else:old['deadline']+=1
    folders['legacy-old'].data.clear();folders['legacy-old'].put('old',old)
    rows,summary=x.discover(d,dataiku)
    assert not summary['blocking_job_ids']
    assert [c['API_TYPE'] for c in env.calls]==['HEALTH']


def test_corrupt_checkpoint_never_sent_and_other_folder_still_checked(env):
    folders,known,dataiku,old,current=fixture_project(env)
    key=next(iter(folders['structured'].data));folders['structured'].data[key]=b'wrong'
    rows,summary=x.discover(d,dataiku)
    assert summary['blocking_job_ids']==[env.auth['job_id']]
    assert any(r.get('error_code')=='CHECKPOINT_HASH' for r in rows)


def local_work(tmp_path,old):
    root=tmp_path/'legal_pipeline_work';(root/'jobs'/'old').mkdir(parents=True)
    binding=copy.deepcopy(old['binding']['input'])
    binding['archives']={'PIPELINE_SUPPORT.zip':old['client']['archives']['support']}
    (root/'input-binding.json').write_text(json.dumps(binding))
    (root/'jobs'/'old'/'client.json').write_text(json.dumps(old['client']))
    return root


def test_known_local_notebook_can_find_capability_when_managed_record_missing(env,tmp_path):
    folders,known,dataiku,old,current=fixture_project(env)
    folders['legacy-old'].data.clear()
    root=local_work(tmp_path,old)
    before={str(p):p.read_bytes() for p in root.rglob('*.json')}
    rows,summary=x.discover(d,dataiku,[root,root])
    assert summary['blocking_job_ids']==[env.auth['job_id']] and summary['counts']['local_clients']==1
    assert next(r for r in rows if r.get('source')=='local')['status']=='FAILED'
    assert all(Path(p).read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('kind',['support','project','symlink'])
def test_unbound_local_clients_not_queried(env,tmp_path,kind):
    folders,known,dataiku,old,current=fixture_project(env)
    folders['legacy-old'].data.clear();folders['structured'].data.clear()
    root=local_work(tmp_path,old)
    if kind=='symlink':
        alias=tmp_path/'link';alias.symlink_to(root,target_is_directory=True);root=alias
    else:
        p=root/'input-binding.json';v=json.loads(p.read_text())
        if kind=='project':v['project']='OTHER'
        else:v['archives']['PIPELINE_SUPPORT.zip']['sha256']='0'*64
        p.write_text(json.dumps(v))
    rows,summary=x.discover(d,dataiku,[root])
    assert not summary['blocking_job_ids'] and [v['API_TYPE'] for v in env.calls]==['HEALTH']


def test_raw_file_contents_never_read(env):
    folders,known,dataiku,old,current=fixture_project(env)
    folders['raw'].data['snapshots/large/raw.pdf']=b'not a checkpoint'
    folders['raw'].get_download_stream=lambda path:pytest.fail('opened original raw')
    rows,summary=x.discover(d,dataiku)
    assert summary['counts']['checkpoints']==2


def test_unknown_folder_failure_does_not_claim_no_blocker(env):
    folders,known,dataiku,old,current=fixture_project(env)
    folders['legacy-old'].list_paths_in_partition=lambda:(_ for _ in ()).throw(RuntimeError('secret URL'))
    rows,summary=x.discover(d,dataiku)
    assert not summary['blocking_job_ids']
    assert any(r.get('status')=='FOLDER_UNCONFIRMED' for r in rows)
    assert 'secret URL' not in json.dumps(rows)


def test_full_delivered_cell_reuses_baseline_and_matches_zip(env,tmp_path,monkeypatch):
    folders,known,dataiku,old,current=fixture_project(env)
    root=local_work(tmp_path,old)
    monkeypatch.setitem(sys.modules,'dataiku',dataiku);monkeypatch.chdir(tmp_path)
    name='DATAIKU_GENOS_BUSY_DISCOVERY_20261027_R2.txt'
    source=(HERE/name).read_text();namespace={'WORK_DIR':str(root)}
    exec(compile(source,name,'exec'),namespace)
    assert namespace['DISCOVERY_SUMMARY']['blocking_job_ids']==[env.auth['job_id']]
    assert namespace['DISCOVERY_SUMMARY']['http_calls']==3
    with zipfile.ZipFile(HERE/name.replace('.txt','.zip')) as z:
        assert z.read(name)==source.encode()
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
