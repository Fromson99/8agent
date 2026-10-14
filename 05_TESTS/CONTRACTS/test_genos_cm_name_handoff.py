"""R13 exact TXT preserves R11/R12 state while fixing individual document name binding."""
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
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r13'
R11=OUT.with_name('cm_shortcut_oneclick_20261007_r11')
R12=OUT.with_name('cm_shortcut_oneclick_20261007_r12')
R8=OUT.with_name('cm_shortcut_oneclick_20261007_r8')
R10=OUT.with_name('cm_shortcut_oneclick_20261007_r10')
BUDGET=OUT.with_name('investigation_budget_20261007_r1')
NAME='GENOS_CM_ONECLICK_20261008_R13'
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
    name='GENOS_CM_ONECLICK_20261007_R12' if folder==R12 else 'GENOS_CM_ONECLICK_20261007_R11'
    text=(folder/(name+'_RUN.txt')).read_text()
    packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text)[1]
    bundle=json.loads(zlib.decompress(base64.b64decode(packed)))
    module=types.ModuleType('sealed_parent');exec(compile(base64.b64decode(bundle['code']),'sealed_parent.py','exec'),module.__dict__)
    return module,bundle['spec']


def test_exact_module_edit_recipes_budget_pins_and_zip(tmp_path):
    module,spec=sealed_module();old=json.loads(gzip.decompress((R12/'PATCH_SPEC.json.gz').read_bytes()))
    assert spec['package_sha256']==old['package_sha256']
    assert len(spec['recipes'])==len(spec['r8_upgrades'])==len(spec['r10_upgrades'])==len(spec['r11_upgrades'])==len(spec['r12_upgrades'])==216
    allowed={PATH,'00_SYSTEM/PIPELINE.json'}
    budget,policy=module.budget_library(spec)
    for rid,target in spec['r12_upgrades'].items():
        old_recipe=old['recipes'][rid];new_recipe=spec['recipes'][target]
        before=old['inventories'][old_recipe['after']];after=spec['inventories'][new_recipe['after']]
        assert spec['r12_inventories'][rid]==old_recipe['after']
        assert before.keys()==after.keys()
        pipeline=json.loads(module.blob(spec,after['00_SYSTEM/PIPELINE.json']))
        engines={v['manifest'] for v in pipeline['engines'].values()}
        assert {p for p in before if before[p]!=after[p]}<=allowed|engines
        assert before['service.py']==after['service.py']
        raw=module.blob(spec,before[PATH]);updated=module.blob(spec,after[PATH])
        assert updated!=raw and sha(updated)==json.loads((OUT/'HANDOFF.json').read_bytes())['after_module_sha256']
        assert before['02_BACKEND/semantic_runtime/document_roles.py']==after['02_BACKEND/semantic_runtime/document_roles.py']
        assert sha(updated)==json.loads((OUT/'HANDOFF.json').read_bytes())['after_module_sha256']
        for entry in pipeline['engines'].values():
            content=module.blob(spec,after[entry['manifest']]);assert sha(content)==entry['sha256']
            engine=json.loads(content);assert all(after[p]==pin for p,pin in engine['files'].items())
        service=module.blob(spec,after['service.py'])
        assert module.without_budget(budget.transform(service,policy),spec)==service
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as z:
        assert z.testzip() is None
        assert z.read(NAME+'_RUN.txt')==(OUT/(NAME+'_RUN.txt')).read_bytes()
        assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
    subprocess.run([str(ROOT/'.venv/bin/python'),'-m','zipfile','-e',str(OUT/(NAME+'.zip')),str(tmp_path)],check=True)
    subprocess.run(['sha256sum','-c',NAME+'_SHA256SUMS.txt'],cwd=tmp_path,check=True)
    subprocess.run(['bash','-n',str(tmp_path/(NAME+'_RUN.txt'))],check=True)


@pytest.mark.parametrize('basis',['r11-budget','r12-budget','r11-plain','r12-plain','direct-plain'])
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
    if basis.endswith('-budget'):
        oldrun=transfer/'GENOS_CM_ONECLICK_20261007_R8_RUN.txt';oldrun.write_bytes((R8/oldrun.name).read_bytes())
        run(oldrun,'--validation-prefix',tmp_path,success=False)
        budget_run=BUDGET/'GENOS_INVESTIGATION_BUDGET_20261007_R1_RUN.txt'
        for command in ('check','apply','verify'):run(budget_run,command)
        r10run=transfer/'GENOS_CM_ONECLICK_20261007_R10_RUN.txt';r10run.write_bytes((R10/r10run.name).read_bytes())
        run(r10run,'--validation-prefix',tmp_path,success=False)
        budget_service=(root/'service.py').read_bytes()
        budget_meta=json.loads((root/'CODE_MANIFEST.json').read_bytes())['investigation_budget_settings']
    if basis!='direct-plain':
        parent=transfer/'GENOS_CM_ONECLICK_20261007_R11_RUN.txt';parent.write_bytes((R11/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path,success=False)
        assert 'target body document missing: 중소기업기본법' in (transfer/'cm-oneclick-r11/package-check.log').read_text()
        status=json.loads((transfer/'cm-oneclick-r11/STATUS.json').read_bytes())
        assert status['state']=='FAILED' and status['phase']=='공통 코드 적용'
    if basis.startswith('r12-'):
        parent=transfer/'GENOS_CM_ONECLICK_20261007_R12_RUN.txt';parent.write_bytes((R12/parent.name).read_bytes())
        run(parent,'--validation-prefix',tmp_path)
        assert json.loads((transfer/'cm-oneclick-r12/STATUS.json').read_bytes())['state']=='READY_FOR_REVISION_DEPLOYMENT'
    history={p:sha(p.read_bytes()) for folder in ('cm-oneclick-r8','cm-oneclick-r10','cm-oneclick-r11','cm-oneclick-r12')
        for p in (transfer/folder).rglob('*') if p.is_file()}
    history.update({p:sha(p.read_bytes()) for p in (tmp_path/'budget-logs').rglob('*') if p.is_file()})
    if basis.endswith('-budget'):
        binding=json.loads((root/module.CONFIG).read_bytes())
        backup=transfer/('cm-oneclick-r12' if basis.startswith('r12-') else 'cm-oneclick-r11')/'code-backup/CODE_MANIFEST.json';saved=backup.read_bytes()
        backup.write_bytes(saved+b' ')
        with pytest.raises(ValueError,match='parent backup differs'):
            module.prepare(root,spec,module.library(spec),binding)
        assert backup.read_bytes()==saved+b' ';backup.write_bytes(saved)
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
        status=json.loads((transfer/'cm-oneclick-r13/STATUS.json').read_bytes())
        assert status['state']=='READY_FOR_REVISION_DEPLOYMENT' and status['model_calls']==0
        assert status['code_serving_revision'] is None and status['workflow_verified'] is False
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        assert manifest['cm_oneclick']['revision']==NAME
        if basis.endswith('-budget'):
            assert (root/'service.py').read_bytes()==budget_service
            assert manifest['investigation_budget_settings']==budget_meta
            assert manifest['cm_oneclick']['preserved_investigation_budget']==budget_meta
        else:assert 'investigation_budget_settings' not in manifest
        checked=json.loads((transfer/'cm-oneclick-r13/DATA_CHECKED.json').read_bytes())
        assert checked['cases']==51 and checked['source_entries']==98 and len(checked['resolved_documents'])==21
        receipt=json.loads((transfer/'cm-oneclick-r13/CM51_REGISTERED.json').read_bytes())
        assert len(receipt['records'])==51 and receipt.get('already_imported',False)==(bool(replay) or basis.startswith('r12-'))
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
    folder=transfer/'cm-oneclick-r13/code-backup';journal=json.loads((folder/'receipt.json').read_bytes())
    for row in journal['files']:
        path=root/row['path'];assert sha(path.read_bytes())==row['after_sha256']
        if row['before_sha256'] is None:path.unlink()
        else:
            raw=(folder/row['path']).read_bytes();assert sha(raw)==row['before_sha256'];path.write_bytes(raw)
    if basis!='direct-plain':
        old,oldspec=prior_module(R12 if basis.startswith('r12-') else R11)
        old.verify_output(root,oldspec,old.library(oldspec),json.loads((root/old.CONFIG).read_bytes()))
    if budget_service is not None:assert (root/'service.py').read_bytes()==budget_service
    (OUT/('RUN-'+basis+'.log.gz')).write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
    (OUT/('VERIFIED-'+basis+'.json')).write_bytes(module.encoded({'basis':basis,'runs':2,
        'r11_body_failure_reproduced':basis!='direct-plain','prior_R12_registered':basis.startswith('r12-'),'cases':51,'entries':98,'documents':21,
        'budget_preserved':basis.endswith('-budget'),'parent_backup_drift_rejected':basis.endswith('-budget'),
        'unknown_self_consistent_code_rejected':basis.endswith('-budget'),'code_rollback_verified':True,
        'old_failure_and_budget_backups_preserved':True,'replay_no_duplicates':True,
        'same_checkout_commit_generation_gate_local_remote_push':True,'generation_unchanged':True,
        'local_main_pointer_unchanged':True,'model_calls':0,'GENOS_field_verified':False,
        'RUN_sha256':sha((OUT/(NAME+'_RUN.txt')).read_bytes())}))
