"""Synthetic reversible checkout handoff; no deployment/model/latency experiment."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'08_DEPLOYMENT/GENOS/patches'
PATCH=BASE/'request_prepare_20260929_r1'
PRE=ROOT/'90_RUNTIME/diagnostics/request-prepare-20260929-preimage'
PREFIX='GENOS_REQUEST_PREPARE_20260929_R1'


@pytest.fixture
def installed(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(PATCH))
    # Another handoff also calls its module transform.py; load this one explicitly.
    for key,file in [('transform','transform.py'),('prepare_installer','apply.py')]:
        spec=importlib.util.spec_from_file_location(key,PATCH/file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules,key,module)
    installer=sys.modules['prepare_installer']
    spec=json.loads((PATCH/'PATCH_MANIFEST.json').read_bytes())
    root=tmp_path/'DEV';root.mkdir();files={}
    for name in set(spec['files'])|{r['path'] for r in spec['requirements']}:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        raw=(PRE/name).read_bytes() if name in spec['files'] else (ROOT/name).read_bytes()
        path.write_bytes(raw+b'\nONSITE_FEATURE = 731\n');files[name]=installer.sha(path.read_bytes())
    schema=root/'00_SYSTEM/schema.json';schema.parent.mkdir();schema.write_text('{}\n')
    manifest=root/'02_BACKEND/ENGINES/fixture.json';manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'files':files},indent=2)+'\n')
    config={'engines':{'fixture':{'manifest':manifest.relative_to(root).as_posix(),'sha256':installer.sha(manifest.read_bytes())}},
            'contracts':{'fixture':{'schema_path':'00_SYSTEM/schema.json','schema_sha256':installer.sha(schema.read_bytes())}},
            'profiles':{'onsite':{'index':'unchanged','generation':'unchanged'}}}
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config,indent=2)+'\n')
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','00_SYSTEM','02_BACKEND'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                    '-c','core.hooksPath=/dev/null','commit','-qm','fixture'],check=True)
    monkeypatch.setattr(sys,'argv',['apply.py','--deploy-root',str(root)])
    return root,installer,spec


def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def test_apply_reapply_rollback_preserves_onsite_bytes_and_pins(installed):
    root,installer,spec=installed;before=snapshot(root)
    installer.main();after=snapshot(root)
    for name,row in spec['files'].items():
        assert b'ONSITE_FEATURE = 731' in after[name]
        import transform
        assert transform.signature(transform.function(after[name],row['qualified']))==row['after_ast_sha256']
    config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    assert config['profiles']=={'onsite':{'index':'unchanged','generation':'unchanged'}}
    entry=config['engines']['fixture'];assert installer.sha((root/entry['manifest']).read_bytes())==entry['sha256']
    for name,expected in json.loads((root/entry['manifest']).read_bytes())['files'].items():
        assert installer.sha((root/name).read_bytes())==expected
    installer.main();assert snapshot(root)==after
    backup=next((root/'TRANSFER'/installer.PATCH_ID).glob('backup-*'))
    installer.rollback(root,backup);assert snapshot(root)==before


def test_missing_cache_prerequisite_stops_before_any_writes(installed):
    root,installer,spec=installed
    path=root/spec['requirements'][0]['path'];path.write_text('def another(): pass\n')
    before=snapshot(root)
    with pytest.raises(ValueError,match='prerequisite'):installer.main()
    assert snapshot(root)==before


def test_unknown_preparation_function_stops_before_any_writes(installed):
    root,installer,spec=installed
    path=root/'02_BACKEND/semantic_runtime/legal_agent/repository.py'
    path.write_bytes(path.read_bytes().replace(b'create = not self.path.exists()',b'create = True',1))
    before=snapshot(root)
    with pytest.raises(ValueError,match='unknown preparation function'):installer.main()
    assert snapshot(root)==before


def test_failed_write_restores_checkout(installed,monkeypatch):
    root,installer,spec=installed;before=snapshot(root);atomic=installer.atomic;failed=False
    def interrupted(path,raw):
        nonlocal failed
        if path==root/'00_SYSTEM/PIPELINE.json' and not failed:
            failed=True;raise OSError('synthetic interruption')
        atomic(path,raw)
    monkeypatch.setattr(installer,'atomic',interrupted)
    with pytest.raises(OSError):installer.main()
    assert snapshot(root)==before


def test_standalone_txt_same_patch_on_python311_and_local_python(installed,tmp_path):
    root,installer,spec=installed;before=snapshot(root)
    for python in [sys.executable]+(['/usr/bin/python3.11'] if Path('/usr/bin/python3.11').exists() else []):
        env={**os.environ,'DEPLOY_ROOT':str(root),'PYTHON_BIN':python,'TMPDIR':str(tmp_path)}
        run=subprocess.run(['bash',str(BASE/(PREFIX+'_APPLY.txt'))],env=env,text=True,capture_output=True)
        assert run.returncode==0,run.stdout+run.stderr
    backup=next((root/'TRANSFER'/installer.PATCH_ID).glob('backup-*'))
    installer.rollback(root,backup);assert snapshot(root)==before
    with zipfile.ZipFile(BASE/(PREFIX+'.zip')) as archive:
        names=archive.namelist();inventory=json.loads(archive.read('CODE_MANIFEST.json'))
        assert len(names)==len(set(names))
        assert set(names)=={r['path'] for r in inventory['files']}|{'CODE_MANIFEST.json'}
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in names)
        for row in inventory['files']:assert installer.sha(archive.read(row['path']))==row['sha256']


def test_capture_only_prints_stage_metrics_and_missing_event_fails(tmp_path):
    report=tmp_path/'request.json'
    report.write_text(json.dumps({'question':'PRIVATE_FIXTURE','service_events':[{'event':'session.prepare.timings',
        'prepare_status':'READY','diagnostic_revision':'request-prepare-20260929-r1','elapsed_ms':12,'thread_cpu_ms':1,
        'process_id':2,'phases':{'session.journal':{'wall_ms':3,'cpu_ms':0.2}}}]}))
    env={**os.environ,'REPORT_JSON':str(report),'PYTHON_BIN':sys.executable,'TMPDIR':str(tmp_path)}
    def run():return subprocess.run(['bash',str(BASE/(PREFIX+'_CAPTURE.txt'))],env=env,text=True,capture_output=True)
    result=run();assert result.returncode==0,result.stdout+result.stderr
    assert 'session.journal' in result.stdout and 'PRIVATE_FIXTURE' not in result.stdout
    report.write_text('{"service_events":[]}')
    result=run();assert result.returncode!=0 and 'NO_PREPARATION_EVENT' in result.stdout
    for suffix in ('APPLY','CAPTURE'):subprocess.run(['bash','-n',str(BASE/(PREFIX+'_'+suffix+'.txt'))],check=True)
