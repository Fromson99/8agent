from pathlib import Path
import hashlib,json,os,shutil,subprocess
H=Path(__file__).resolve().parent;R=H.parents[3]
T=R/'09_ARTIFACTS/AUDITS/20261104-main140-oneclick-r1';T.mkdir(exist_ok=False)
dev=T/'physical-checkout';dev.mkdir();transfer=T/'TRANSFER';transfer.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active_before=sha(pointer)
before=R/'08_DEPLOYMENT/RELEASES/genos-embed-env-20261104-r1/code'
for n in json.loads((before.parent/'release.json').read_text())['files']:
 p=dev/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(before/n,p)
(dev/'.env').write_text('ONECLICK_FIXTURE=preserved\n')
(dev/'01_DATA').mkdir();(dev/'01_DATA/sentinel').write_text('source unchanged\n')
original={str(p.relative_to(dev)):sha(p) for p in dev.rglob('*') if p.is_file()}
subprocess.run(['git','init','-q',str(dev)],check=True)
for name in ('MAIN140_FULL_ORACLE_20261104_R1.zip','MAIN140_ONECLICK_R1.txt'):shutil.copyfile(H/name,transfer/name)
home_dev=Path.home()/'DEV'
assert not home_dev.exists() and not home_dev.is_symlink(),'Do not touch an existing HOME/DEV'
results=[];env={**os.environ,'GENOS_PYTHON':str(R/'.venv/bin/python')}
def run(*args,ok=True,filename='MAIN140_ONECLICK_R1.txt'):
 p=subprocess.run(['bash',filename,*map(str,args)],cwd=transfer,env=env,text=True,capture_output=True)
 (T/('step-'+str(len(results))+'.log')).write_text(p.stdout+p.stderr)
 results.append({'args':list(map(str,args)),'file':filename,'exit_code':p.returncode,'expected_success':ok})
 assert (p.returncode==0)==ok,p.stdout[-2000:]+p.stderr[-1000:]
 return p.stdout
home_dev.symlink_to(dev,target_is_directory=True)
try:
 js=dev/'02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js';raw=js.read_bytes();js.write_text('fixture-only wrong dependency')
 run(ok=False);assert sha(dev/'service.py')==original['service.py'];js.write_bytes(raw)
 out=run()
 assert 'MAIN140_TARGET='+str(dev) in out and 'MAIN140_ONECLICK_DONE' in out
 out=run();assert 'ALREADY INSTALLED' in out and 'MAIN140_ONECLICK_DONE' in out
 renamed='MAIN140_ONECLICK_R1 (1).txt';shutil.copyfile(transfer/'MAIN140_ONECLICK_R1.txt',transfer/renamed)
 assert 'MAIN140_ONECLICK_DONE' in run(filename=renamed)
 assert 'MAIN140_INSTALLED_HASHES_OK' in run('status')
 run('stage')
 subprocess.run(['git','-C',str(dev),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Verified handoff fixture'],check=True)
 run('gate-code')
 receipts=list((dev/'09_ARTIFACTS/BACKUPS/code-replacement').glob('*/receipt.json'));assert len(receipts)==1
 run('undo','--backup',receipts[0].parent)
 assert all(sha(dev/n)==h for n,h in original.items())
 assert not (dev/'CODE_MANIFEST.json').exists()
finally:
 assert home_dev.is_symlink() and home_dev.readlink()==dev
 home_dev.unlink()
assert sha(pointer)==active_before
result={'passed':True,'exact_no_argument_bash_tested':True,'HOME_environment_unmodified':True,'temporary_HOME_DEV_symlink_removed':True,
 'physical_target_resolved':True,'duplicate_install_verified':True,'renamed_TXT_verified':True,'required_JS_mismatch_rejected_before_replace':True,
 'original_files_restored':len(original),'actual_MAIN_unchanged':True,'field_executed':False,'steps':results}
(T/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(H/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
