"""R15 exact TXT preserves the verified full-error R10 overlay and budget settings."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import types
import zipfile
import zlib

import pytest

from test_genos_cm_budget_handoff import field_fixture, sealed_module as r11_module

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15'
R11=OUT.with_name('cm_shortcut_oneclick_20261007_r11')
R12=OUT.with_name('cm_shortcut_oneclick_20261007_r12')
R13=OUT.with_name('cm_shortcut_oneclick_20261008_r13')
R14=OUT.with_name('cm_shortcut_oneclick_20261008_r14')
FULL=OUT.with_name('full_error_logging_20261007_r10')
R8=OUT.with_name('cm_shortcut_oneclick_20261007_r8')
R10=OUT.with_name('cm_shortcut_oneclick_20261007_r10')
BUDGET=OUT.with_name('investigation_budget_20261007_r1')
NAME='GENOS_CM_ONECLICK_20261008_R15'
PATH='02_BACKEND/lawrag/pipeline/shortcut_package.py'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def sealed_module():
    text=(OUT/(NAME+'_RUN.txt')).read_text()
    packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text)[1]
    bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
    code=base64.b64decode(bundle['code']);module=types.ModuleType('sealed_r12')
    exec(compile(code,'sealed_r12.py','exec'),module.__dict__)
    assert sha(code)==json.loads((OUT/'HANDOFF.json').read_bytes())['oneclick_source_sha256']
    return module,bundle['spec']


def prior_module(folder):
    name=json.loads((folder/'HANDOFF.json').read_bytes())['version']
    text=(folder/(name+'_RUN.txt')).read_text()
    packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text)[1]
    bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
    module=types.ModuleType('sealed_parent');exec(compile(base64.b64decode(bundle['code']),'sealed_parent.py','exec'),module.__dict__)
    return module,bundle['spec']


def test_sealed_recipe_unchanged_full_error_pins_zip_and_syntax(tmp_path):
    module,spec=sealed_module();old=json.loads(gzip.decompress((R14/'PATCH_SPEC.json.gz').read_bytes()))
    for key in ('inventories','patch_sets','recipes','blobs','states','package_sha256','paths'):
        assert spec[key]==old[key],key
    assert spec['r14_upgrades']=={rid:rid for rid in old['recipes']}
    logging,policy=module.logging_library(spec)
    assert policy==json.loads((FULL/'PATCH_SPEC.json').read_bytes())
    assert spec['full_error_logging_overlay']['library_sha256']==sha((FULL/'INSTALL.py').read_bytes())
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:
        assert z.testzip() is None
        assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
        assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
        z.extractall(tmp_path)
    subprocess.run(['sha256sum','-c',NAME+'_SHA256SUMS.txt'],cwd=tmp_path,check=True)
    subprocess.run(['bash','-n',str(tmp_path/(NAME+'_RUN.txt'))],check=True)


@pytest.mark.parametrize('basis',['r11-budget-logging','r12-budget-logging','r14-budget-logging','r14-plain-logging','r14-budget','direct-budget-logging','direct-plain'])
def test_exact_txt_body_failure_recovery_preservation_replay_and_rollback(tmp_path,term_glossary,basis):
    module,spec=sealed_module()
    root,transfer,generation,database,remote,git,env=field_fixture(tmp_path,term_glossary,spec,plain_body_title='중소기업기본법')
    initial={p.relative_to(generation).as_posix():sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    main_pointer=(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()
    transcript=[];budget_service=None;budget_meta=None
    def run(script,*args,success=True):
        result=subprocess.run(['bash',str(script),*map(str,args)],cwd=tmp_path,env=env,
            capture_output=True,text=True,timeout=180)
        transcript.append(script.name+' '+str(args)+'\n'+result.stdout+result.stderr)
        if (result.returncode==0)!=success:
            (OUT/('FAIL-'+basis+'.log.gz')).write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
        assert (result.returncode==0)==success,transcript[-1]
        return result
    if 'budget' in basis:
        oldrun=transfer/'GENOS_CM_ONECLICK_20261007_R8_RUN.txt';oldrun.write_bytes((R8/oldrun.name).read_bytes())
        run(oldrun,'--validation-prefix',tmp_path,success=False)
        budget_run=BUDGET/'GENOS_INVESTIGATION_BUDGET_20261007_R1_RUN.txt'
        for command in ('check','apply','verify'):run(budget_run,command)
        r10run=transfer/'GENOS_CM_ONECLICK_20261007_R10_RUN.txt';r10run.write_bytes((R10/r10run.name).read_bytes())
        run(r10run,'--validation-prefix',tmp_path,success=False)
        budget_service=(root/'service.py').read_bytes()
        budget_meta=json.loads((root/'CODE_MANIFEST.json').read_bytes())['investigation_budget_settings']
    if not basis.startswith('direct-'):
        parent=transfer/'GENOS_CM_ONECLICK_20261007_R11_RUN.txt';parent.write_bytes((R11/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path,success=False)
        assert 'target body document missing: 중소기업기본법' in (transfer/'cm-oneclick-r11/package-check.log').read_text()
        status=json.loads((transfer/'cm-oneclick-r11/STATUS.json').read_bytes())
        assert status['state']=='FAILED' and status['phase']=='공통 코드 적용'
    if basis.startswith(('r12-','r13-','r14-')):
        parent=transfer/'GENOS_CM_ONECLICK_20261007_R12_RUN.txt';parent.write_bytes((R12/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path)
        assert json.loads((transfer/'cm-oneclick-r12/STATUS.json').read_bytes())['state']=='READY_FOR_REVISION_DEPLOYMENT'
    if basis.startswith('r13-'):
        parent=transfer/'GENOS_CM_ONECLICK_20261008_R13_RUN.txt';parent.write_bytes((R13/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path)
    if basis.startswith('r14-'):
        parent=transfer/'GENOS_CM_ONECLICK_20261008_R14_RUN.txt';parent.write_bytes((R14/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path)
    full_error_manifest=None;full_error_files={};full_before=None
    if basis.endswith('-logging'):
        full_before=(root/'service.py').read_bytes()
        for command in ('check','apply','verify'):run(FULL/'GENOS_FULL_ERROR_LOGGING_20261007_R10_RUN.txt',command)
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        full_error_manifest=manifest['full_error_logging']
        full_error_files={n:(root/n).read_bytes() for n in full_error_manifest['modified_paths']}
        if 'budget' in basis:
            assert sha(full_before)=='2cfb9c6e36c0a80ffd8ce1409060d4666c074479be699028ebe28272827d86af'
            assert sha((root/'service.py').read_bytes())=='daea3108798e70737f29288fd8e3b23eeb9f32cea7b956d583753d3e185b8276'
        oldrun=transfer/'GENOS_CM_ONECLICK_20261008_R14_RUN.txt';oldrun.write_bytes((R14/oldrun.name).read_bytes())
        result=run(oldrun,'--validation-prefix',tmp_path,success=False)
        if 'budget' in basis and basis.startswith(('r11-','r12-')):
            assert 'budget service inventory differs; preserved' in result.stdout+result.stderr
        else:assert any(e in result.stdout+result.stderr for e in ('installed code differs from sealed recipe','budget service inventory differs','budget parent inventory differs'))
        assert json.loads((transfer/'cm-oneclick-r14/STATUS.json').read_bytes())['state']=='FAILED'
    before_upgrade={r['path']:(root/r['path']).read_bytes() for r in json.loads((root/'CODE_MANIFEST.json').read_bytes())['files']}
    before_upgrade['CODE_MANIFEST.json']=(root/'CODE_MANIFEST.json').read_bytes()
    history={p:sha(p.read_bytes()) for folder in ('cm-oneclick-r8','cm-oneclick-r10','cm-oneclick-r11','cm-oneclick-r12','cm-oneclick-r13','cm-oneclick-r14','full-error-logging-r10')
        for p in (transfer/folder).rglob('*') if p.is_file()}
    history.update({p:sha(p.read_bytes()) for p in (tmp_path/'budget-logs').rglob('*') if p.is_file()})
    binding=json.loads((root/module.CONFIG).read_bytes()) if (root/module.CONFIG).exists() else {
        'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':str(generation),
        'runtime':str(database.parent.parent),'state':None,'generation_manifest_sha256':sha((generation/'manifest.json').read_bytes()),
        'source':'confirmed field paths and NFS transfer mail 1a115df82c32b2f5'}
    if basis.endswith('-logging'):
        folder=next((transfer/'full-error-logging-r10').glob('backup-*'))
        for target in (folder/'CODE_MANIFEST.json',folder/'service.py',folder/'APPLIED_CODE.zip'):
            saved=target.read_bytes();target.write_bytes(saved+b' ')
            with pytest.raises(ValueError):module.prepare(root,spec,module.library(spec),binding)
            assert target.read_bytes()==saved+b' ';target.write_bytes(saved)
        receipt=folder/'receipt.json';saved=receipt.read_bytes();record=json.loads(saved);record['state']='PREPARED'
        receipt.write_bytes(module.encoded(record))
        with pytest.raises(ValueError,match='identity/state differs'):module.prepare(root,spec,module.library(spec),binding)
        receipt.write_bytes(saved)
    # A self-consistent manifest cannot approve an unsealed source edit.
    saved_service=(root/'service.py').read_bytes();saved_manifest=(root/'CODE_MANIFEST.json').read_bytes()
    drift=saved_service+b'\n# unapproved field change\n';(root/'service.py').write_bytes(drift)
    manifest=json.loads(saved_manifest)
    for row in manifest['files']:
        if row['path']=='service.py':row.update(sha256=sha(drift),bytes=len(drift))
    for row in manifest.get('required_files',[]):
        if isinstance(row,dict) and row['path']=='service.py':row['sha256']=sha(drift)
    (root/'CODE_MANIFEST.json').write_bytes(module.encoded(manifest))
    with pytest.raises(ValueError):module.prepare(root,spec,module.library(spec),binding)
    assert (root/'service.py').read_bytes()==drift
    (root/'service.py').write_bytes(saved_service);(root/'CODE_MANIFEST.json').write_bytes(saved_manifest)
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:z.extractall(transfer)
    installed=None
    for replay in range(2):
        result=run(transfer/(NAME+'_RUN.txt'),'--validation-prefix',tmp_path)
        status=json.loads((transfer/'cm-oneclick-r15/STATUS.json').read_bytes())
        assert status['state']=='READY_FOR_REVISION_DEPLOYMENT' and status['model_calls']==0
        assert status['code_serving_revision'] is None and status['workflow_verified'] is False
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        assert manifest['cm_oneclick']['revision']==NAME
        if 'budget' in basis:
            assert (root/'service.py').read_bytes()==(full_error_files.get('service.py',budget_service))
            assert manifest['investigation_budget_settings']==budget_meta
            assert manifest['cm_oneclick']['preserved_investigation_budget']==budget_meta
        else:assert 'investigation_budget_settings' not in manifest
        if basis.endswith('-logging'):
            assert manifest['full_error_logging']==full_error_manifest
            assert manifest['cm_oneclick']['preserved_full_error_logging']['revision']=='GENOS_FULL_ERROR_LOGGING_20261007_R10'
            # CM repins engines and its name module. Preserve every actual R10 source byte.
            for name,raw in full_error_files.items():
                if not name.startswith('02_BACKEND/ENGINES/') and name!='00_SYSTEM/PIPELINE.json':
                    assert (root/name).read_bytes()==raw,name
            logmod,policy=module.logging_library(spec)
            logmod.local_verification({r['path']:(root/r['path']).read_bytes() for r in manifest['files']},policy)
        else:assert manifest['cm_oneclick']['preserved_full_error_logging'] is None
        checked=json.loads((transfer/'cm-oneclick-r15/DATA_CHECKED.json').read_bytes())
        assert checked['cases']==51 and checked['source_entries']==98 and len(checked['resolved_documents'])==21
        receipt=json.loads((transfer/'cm-oneclick-r15/CM51_REGISTERED.json').read_bytes())
        assert len(receipt['records'])==51 and receipt.get('already_imported',False)==(bool(replay) or basis.startswith(('r12-','r13-','r14-')))
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT value FROM keep_fixture').fetchone()[0]=='preserve'
            assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
        assert git('rev-parse','HEAD')==subprocess.run(['git','--git-dir',str(remote),'rev-parse','HEAD'],
            check=True,capture_output=True,text=True).stdout.strip()
        logfile=Path(re.search(r'^EXIT=0 LOG=(.+)$',result.stdout,re.M)[1])
        assert json.loads(Path(str(logfile)+'.EXIT_STATUS.json').read_bytes())['exit_code']==0
        assert all(p.exists() and sha(p.read_bytes())==pin for p,pin in history.items())
        state={r['path']:sha((root/r['path']).read_bytes()) for r in manifest['files']}
        if installed is not None:assert state==installed
        installed=state
    assert initial=={p.relative_to(generation).as_posix():sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    assert (ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==main_pointer
    # Exercise the documented rollback's hash guard and restore exact code bytes.
    folder=transfer/'cm-oneclick-r15/code-backup';journal=json.loads((folder/'receipt.json').read_bytes())
    for row in journal['files']:
        path=root/row['path'];assert sha(path.read_bytes())==row['after_sha256']
        if row['before_sha256'] is None:path.unlink()
        else:
            raw=(folder/row['path']).read_bytes();assert sha(raw)==row['before_sha256'];path.write_bytes(raw)
    for name,raw in before_upgrade.items():assert (root/name).read_bytes()==raw,name
    if basis.endswith('-logging'):
        logmod,policy=module.logging_library(spec);logmod.verify(root,policy)
    if budget_service is not None:assert (root/'service.py').read_bytes()==full_error_files.get('service.py',budget_service)
    (OUT/('RUN-'+basis+'.log.gz')).write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
    (OUT/('VERIFIED-'+basis+'.json')).write_bytes(module.encoded({'basis':basis,'runs':2,
        'r11_body_failure_reproduced':not basis.startswith('direct-'),'prior_R12_registered':basis.startswith(('r12-','r13-','r14-')),'cases':51,'entries':98,'documents':21,
        'budget_preserved':'budget' in basis,'full_error_verified_backups_and_archive_drift_rejected':basis.endswith('-logging'),'R14_failure_reproduced':basis.endswith('-logging'),'full_error_source_bytes_preserved':basis.endswith('-logging'),
        'unknown_self_consistent_code_rejected':'budget' in basis,'code_rollback_verified':True,
        'old_failure_and_budget_backups_preserved':True,'replay_no_duplicates':True,
        'same_checkout_commit_generation_gate_local_remote_push':True,'generation_unchanged':True,
        'local_main_pointer_unchanged':True,'model_calls':0,'GENOS_field_verified':False,
        'RUN_sha256':sha((OUT/(NAME+'_RUN.txt')).read_bytes())}))


def test_partial_r15_write_restores_verified_logging_then_exact_txt_resumes(tmp_path,term_glossary):
    module,spec=sealed_module()
    root,transfer,generation,database,remote,git,env=field_fixture(tmp_path,term_glossary,spec,plain_body_title='중소기업기본법')
    parent=transfer/'GENOS_CM_ONECLICK_20261007_R11_RUN.txt';parent.write_bytes((R11/parent.name).read_bytes())
    result=subprocess.run(['bash',str(parent),'--validation-prefix',str(tmp_path)],cwd=tmp_path,env=env,
        capture_output=True,text=True,timeout=180)
    assert result.returncode==1 and 'target body document missing: 중소기업기본법' in (transfer/'cm-oneclick-r11/package-check.log').read_text()
    logging,policy=module.logging_library(spec)
    log_artifacts=transfer/'full-error-logging-r10';log_artifacts.mkdir()
    logging.apply(root,policy,log_artifacts)
    before={r['path']:(root/r['path']).read_bytes() for r in json.loads((root/'CODE_MANIFEST.json').read_bytes())['files']}
    before['CODE_MANIFEST.json']=(root/'CODE_MANIFEST.json').read_bytes()
    binding={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':str(generation),
        'runtime':str(database.parent.parent),'state':None,'generation_manifest_sha256':sha((generation/'manifest.json').read_bytes()),
        'source':'confirmed field paths and NFS transfer mail 1a115df82c32b2f5'}
    artifacts=transfer/'cm-oneclick-r15';artifacts.mkdir()
    lib=module.library(spec);atomic=lib.atomic;failed=False
    def fault(path,raw,mode=0o600):
        nonlocal failed
        atomic(path,raw,mode)
        if not failed and path.is_relative_to(root) and not path.is_relative_to(transfer):
            failed=True
            raise OSError('SYNTHETIC_WRITE_FAILURE_AFTER_FIRST_REPLACEMENT')
    lib.atomic=fault
    with pytest.raises(OSError,match='SYNTHETIC_WRITE_FAILURE'):
        module.apply(root,spec,lib,binding,artifacts)
    assert failed
    lib.atomic=atomic
    with pytest.raises(ValueError):lib.inventory(root,json.loads((root/'CODE_MANIFEST.json').read_bytes()))
    module.recover_partial(root,lib,artifacts)
    for name,raw in before.items():assert (root/name).read_bytes()==raw,name
    assert len(list(artifacts.glob('recovered-backup-*')))==1
    logging.verify(root,policy)
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:z.extractall(transfer)
    result=subprocess.run(['bash',str(transfer/(NAME+'_RUN.txt')),'--validation-prefix',str(tmp_path)],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
    status=json.loads((artifacts/'STATUS.json').read_bytes())
    assert status['state']=='READY_FOR_REVISION_DEPLOYMENT'
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT value FROM keep_fixture').fetchone()[0]=='preserve'
        assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
    logfile=OUT/'RUN-partial-r15.log.gz';logfile.write_bytes(gzip.compress((result.stdout+result.stderr).encode(),mtime=0))
    (OUT/'VERIFIED-partial-r15.json').write_bytes(module.encoded({'synthetic_partial_R15_write_failure_reproduced':True,
        'recovery_bypasses_full_inventory_dispatch_guard':True,'all_original_logging_code_restored_exactly':True,
        'failure_backup_preserved':True,'exact_txt_resumed_registration_gate_push':True,
        'R10_partial_apply_undo_repaired':False,'model_calls':0,'GENOS_field_verified':False,
        'RUN_sha256':sha((OUT/(NAME+'_RUN.txt')).read_bytes())}))
