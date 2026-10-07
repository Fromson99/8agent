"""Synthetic handoff/read contracts, not a performance experiment."""
import ast
from copy import deepcopy
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_legal_agent_double_harness import generation

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'08_DEPLOYMENT/GENOS/patches'
PATCH = BASE/'fulltext_location_20260929_r1'
PRE = ROOT/'90_RUNTIME/diagnostics/fulltext-location-20260929-preimage-002402'
TARGET = '02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(PATCH))
    return module('location_patch_apply',PATCH/'apply.py'),module('location_patch_bench',PATCH/'benchmark.py'),module('location_patch_transform',PATCH/'transform.py')

def commit(root):
    subprocess.run(['git','-C',str(root),'add','00_SYSTEM','02_BACKEND','other.py'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                    '-c','core.hooksPath=/dev/null','commit','-qm','fixture'],check=True)

@pytest.fixture
def installed(tmp_path,monkeypatch,modules):
    installer,bench,transform=modules
    root=tmp_path/'DEV';root.mkdir()
    path=root/TARGET;path.parent.mkdir(parents=True)
    path.write_bytes((PRE/TARGET).read_bytes()+b'\nONSITE_FEATURE = 731\n')
    (root/'other.py').write_text('OTHER_FEATURE = 1\n')
    files={name:installer.sha((root/name).read_bytes()) for name in (TARGET,'other.py')}
    engines={}
    for i in range(2):
        name=f'02_BACKEND/ENGINES/fixture{i}.json';dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps({'files':files},indent=2)+'\n')
        engines[str(i)]={'manifest':name,'sha256':installer.sha(dest.read_bytes())}
    schema=root/'00_SYSTEM/schema.json';schema.parent.mkdir();schema.write_text('{}\n')
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps({'engines':engines,'contracts':{
        'fixture':{'schema_path':'00_SYSTEM/schema.json','schema_sha256':installer.sha(schema.read_bytes())}},
        'profiles':{'unchanged':731}},indent=2)+'\n')
    subprocess.run(['git','init','-q',str(root)],check=True);commit(root)
    monkeypatch.setattr(sys,'argv',['apply.py','--deploy-root',str(root)])
    return root,installer

def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}

def test_standalone_apply_reapply_gate_rollback_and_root_symlink(installed,tmp_path):
    root,installer=installed;before=snapshot(root)
    link=tmp_path/'linked-DEV';link.symlink_to(root,target_is_directory=True)
    env={**os.environ,'DEPLOY_ROOT':str(link),'PYTHON_BIN':sys.executable,'TMPDIR':str(tmp_path)}
    txt=BASE/'GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt'
    def run():return subprocess.run(['bash',str(txt)],env=env,text=True,capture_output=True)
    first=run();assert first.returncode==0,first.stdout+first.stderr
    assert 'BACKUP_READY' in first.stdout and b'ONSITE_FEATURE = 731' in (root/TARGET).read_bytes()
    assert 'ALREADY_APPLIED' in run().stdout
    config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes());assert config['profiles']=={'unchanged':731}
    for entry in config['engines'].values():
        assert installer.sha((root/entry['manifest']).read_bytes())==entry['sha256']
        assert json.loads((root/entry['manifest']).read_bytes())['files'][TARGET]==installer.sha((root/TARGET).read_bytes())
    env['MODE']='code-only';assert run().returncode!=0
    commit(root);result=run();assert result.returncode==0,result.stdout+result.stderr
    state=root/'TRANSFER'/installer.PATCH_ID
    backup=next(state.glob('backup-*'))
    env.update(MODE='rollback',ROLLBACK_FROM=str(backup))
    result=run();assert result.returncode==0,result.stdout+result.stderr
    assert snapshot(root)==before
    assert len(list(tmp_path.glob('genos-fulltext-location-r1-*.log')))==5

@pytest.mark.parametrize('file',['other.py','02_BACKEND/ENGINES/fixture0.json','00_SYSTEM/schema.json'])
def test_invalid_pins_stop_before_writes(installed,file):
    root,installer=installed
    with (root/file).open('ab') as f:f.write(b'\n# unexpected\n')
    before=snapshot(root)
    with pytest.raises(ValueError):installer.main()
    assert snapshot(root)==before

def test_unknown_search_stops_before_writes(installed):
    root,installer=installed
    path=root/TARGET;path.write_bytes(path.read_bytes().replace(b"self._search_stage='execute'",b"self._search_stage='unknown'",1))
    before=snapshot(root)
    with pytest.raises(ValueError,match='unknown search'):installer.main()
    assert snapshot(root)==before

def test_write_failure_and_interrupted_transaction_recover(installed,monkeypatch):
    root,installer=installed;before=snapshot(root);atomic=installer.atomic;failed=False
    def fail(path,data):
        nonlocal failed
        if path==root/'00_SYSTEM/PIPELINE.json' and not failed:
            failed=True
            raise OSError('synthetic interrupted write')
        atomic(path,data)
    monkeypatch.setattr(installer,'atomic',fail)
    with pytest.raises(OSError):installer.main()
    assert snapshot(root)==before
    monkeypatch.setattr(installer,'atomic',atomic)
    backup=next((root/'TRANSFER'/installer.PATCH_ID).glob('backup-*'))
    receipt=json.loads((backup/'receipt.json').read_bytes());assert receipt['status']=='PREPARED'
    spec=json.loads((PATCH/'PATCH_MANIFEST.json').read_bytes())
    changes=installer.prepare(root,spec)
    atomic(root/TARGET,changes[TARGET]) # simulate kill between code and manifest writes
    installer.main()
    assert json.loads((backup/'receipt.json').read_bytes())['status']=='RECOVERED'
    assert b'ONSITE_FEATURE = 731' in (root/TARGET).read_bytes()

def test_rollback_later_edit_refused(installed):
    root,installer=installed;installer.main()
    backup=next((root/'TRANSFER'/installer.PATCH_ID).glob('backup-*'))
    with (root/TARGET).open('ab') as f:f.write(b'\n# later onsite edit\n')
    before=snapshot(root)
    with pytest.raises(ValueError,match='rollback refused'):installer.rollback(root,backup)
    assert snapshot(root)==before

def test_offline_runner_real_v5_session_identical_and_no_model_calls(tmp_path,generation,modules,monkeypatch):
    installer,bench,transform=modules
    from semantic_runtime import observability as obs
    from semantic_runtime import pipeline as runtime
    from semantic_runtime.storage import Store
    from semantic_runtime.legal_agent import workflow_relations_tools as relations
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    profile={**deepcopy(DEFAULT_PROFILE),'model_binding':None,'page_size':1}
    with closing(Store(generation)) as store:
        p=runtime.Pipeline(ROOT,store,provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile=profile)
        assert p.term_agent.transport is None
        plan=p.plan('승인',['d'])
        records=[]
        for arm,name in [('baseline','baseline.py'),('metadata-location','candidate.py')]:
            fn=transform.function((PATCH/name).read_bytes(),vars(relations))
            row=bench.one(p,plan,'승인',fn,tmp_path/'runtime',obs)
            row.update(arm=arm,case_id='fixture',pair=1);records.append(row)
        assert records[0]['total']>1
        assert records[0]['result_sha256']==records[1]['result_sha256']
        assert records[0]['location']['source_sql_count']>0
        assert records[1]['location']['source_sql_count']==0
        assert records[1]['page_count']==1
        # Verify summary won't call an empty or changed-result case improved.
        bad=deepcopy(records);bad[1]['result_sha256']='different'
        assert not bench.summarize(bad,[{'case_id':'fixture'}],1)[0]['observed_location_improvement']
        empty=deepcopy(records)
        for row in empty:row['total']=0
        assert not bench.summarize(empty,[{'case_id':'fixture'}],1)[0]['observed_location_improvement']

def test_zip_inventory_and_bash_syntax(modules):
    installer,bench,transform=modules
    import zipfile
    archive=BASE/'GENOS_FULLTEXT_LOCATION_20260929_R1.zip'
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();manifest=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(names)=={r['path'] for r in manifest['files']}|{'CODE_MANIFEST.json'}
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in names)
        for row in manifest['files']:
            assert installer.sha(z.read(row['path']))==row['sha256']
    for mode in ('APPLY','BENCH'):
        subprocess.run(['bash','-n',str(BASE/f'GENOS_FULLTEXT_LOCATION_20260929_R1_{mode}.txt')],check=True)
    bench.verify_package()

def test_offline_full_runner_synthetic_freeze_report_and_no_product_writes(tmp_path,generation,modules):
    installer,bench,transform=modules
    out=tmp_path/'offline-fixture';out.mkdir()
    before=(ROOT/TARGET).read_bytes()
    bench.run(ROOT,generation,out,[{'team':None,'query':'승인'}],2)
    assert (ROOT/TARGET).read_bytes()==before
    frozen=json.loads((out/'FROZEN_PLAN.json').read_bytes())
    result=json.loads((out/'RESULTS.json').read_bytes())
    assert frozen['frozen_before_measurement'] is True
    assert result['llm_calls']==0 and result['workflow_verified'] is False
    assert len(result['rows'])==4 and result['cases'][0]['same_results']
    assert all(r['location']['source_sql_count']==0 for r in result['rows'] if r['arm']=='metadata-location')
    assert '모의승인규정' not in (out/'RESULTS.json').read_text()
    assert 'preview_spans' not in (out/'RESULTS.json').read_text()
