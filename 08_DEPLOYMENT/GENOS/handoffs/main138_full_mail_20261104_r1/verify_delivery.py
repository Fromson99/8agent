from pathlib import Path
import hashlib,json,os,shutil,subprocess,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3]
T=R/'09_ARTIFACTS/AUDITS/20261104-main138-samsung-handoff';T.mkdir(exist_ok=False)
dev=T/'fixture-checkout';dev.mkdir()
before=R/'08_DEPLOYMENT/RELEASES/query-latency-native-20261104-r1/code'
release=json.loads((before.parent/'release.json').read_text())
for n in release['files']:
 p=dev/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(before/n,p)
(dev/'.env').write_text('UNCHANGED_FIXTURE=1\n')
(dev/'01_DATA').mkdir();(dev/'01_DATA/sentinel.txt').write_text('Do not change Oracle or local source data\n')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
initial={str(p.relative_to(dev)):sha(p) for p in dev.rglob('*') if p.is_file()}
subprocess.run(['git','init','-q',str(dev)],check=True)
env={**os.environ,'GENOS_PYTHON':str(R/'.venv/bin/python'),'GIT_AUTHOR_NAME':'Handoff Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Handoff Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'}
run=H/'MAIN138_FULL_ORACLE_20261104_R1_RUN.txt';results=[]
def command(action,*args,ok=True):
 p=subprocess.run(['bash',str(run),action,'--root',str(dev),*map(str,args)],env=env,text=True,capture_output=True)
 (T/(str(len(results))+'-'+action+'.log')).write_text(p.stdout+p.stderr)
 results.append({'action':action,'exit_code':p.returncode,'expected_success':ok})
 assert (p.returncode==0)==ok,p.stdout[-2500:]+p.stderr[-1500:]
 return p.stdout
# Fail before replacement when the excluded JS dependency does not match.
js=dev/'02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js';saved=js.read_bytes();js.write_text('fixture tamper')
command('check',ok=False);assert sha(dev/'service.py')==initial['service.py'];js.write_bytes(saved)
command('check');command('apply');command('apply');command('status')
command('stage')
subprocess.run(['git','-C',str(dev),'commit','-qm','Install exact delivery fixture'],env=env,check=True)
command('gate-code')
receipts=list((dev/'09_ARTIFACTS/BACKUPS/code-replacement').glob('*/receipt.json'));assert len(receipts)==1
backup=receipts[0].parent
service=dev/'service.py';installed=service.read_bytes();service.write_bytes(installed+b'\n# concurrent fixture edit\n')
command('undo','--backup',backup,ok=False);assert service.read_bytes().endswith(b'# concurrent fixture edit\n')
service.write_bytes(installed)
command('undo','--backup',backup)
assert all(sha(dev/n)==h for n,h in initial.items())
assert not (dev/'02_BACKEND/semantic_runtime/oracle_query_vector.py').exists()
with zipfile.ZipFile(H/'MAIN138_FULL_ORACLE_20261104_R1.zip') as z:
 assert z.testzip() is None
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.zip'} for n in z.namelist())
 summary={'passed':True,'actions':results,'original_files_restored':len(initial),'data_env_preserved':True,
  'JavaScript_excluded_and_existing_hash_enforced':True,'nested_archives':0,'field_executed':False,'actual_workspace_modified':False}
(T/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(H/'VALIDATION.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
