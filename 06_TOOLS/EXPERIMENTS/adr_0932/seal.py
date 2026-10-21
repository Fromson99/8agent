from pathlib import Path
import json,hashlib,subprocess,sys,datetime,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0932-packet-evidence-update';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
if (D/'freeze.json').exists():
 assert not (A/'artifacts/sequence.jsonl').exists()
 history=D/'prelive-history';history.mkdir(exist_ok=True);h=history/f'{len(list(history.iterdir()))+1:03d}';h.mkdir()
 for p in D.glob('*.json'):shutil.copy2(p,h/p.name)
names=read(D/'serving-files.json');base=read(D/'baseline.json')['manifest'];candidates=[];files={}
for arm in ('fixed',):
 cid=arm.replace('_','-');C=R/'02_BACKEND/lawrag/research/candidates/adr_0932'/cid;S=C/'snapshot'
 for p in (S/'02_BACKEND/workflow').rglob('manifest.json'):
  v=read(p)
  for n in v.get('files',{}):v['files'][n]=sha(S/'02_BACKEND/workflow'/n)
  put(p,v)
 for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
  v=read(p)
  if not isinstance(v.get('files'),dict):continue
  for n in v['files']:v['files'][n]=sha(S/n)
  put(p,v)
 p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
 for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
 for w in v.get('workflows',{}).get('registered',[]):w['sha256']=sha(S/w['manifest'])
 put(p,v)
 for cmd in ('refresh','freeze','validate'):
  proc=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',cmd,str(C)],capture_output=True,text=True)
  assert proc.returncode==0,(cmd,proc.stdout,proc.stderr)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
 candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':cid,'arm_id':arm,'experiment_id':'ADR-0932-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
 binding={'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in names},'candidate':candidate,'release_id':'adr0932-'+cid,'generation':89}
 put(D/(arm+'-binding.json'),binding);candidates.append(candidate)
 put(D/(arm+'-changes.json'),[{'path':n,'before':base['files'][n],'after':sha(code/n)} for n in names if base['files'][n]!=sha(code/n)])
 files.update({str((code/n).relative_to(R)):sha(code/n) for n in names})
 print(arm,rev['revision_id'])
paths=[*T.glob('*.py'),*(p for p in D.glob('*.json') if p.name!='freeze.json'),*R.glob('05_TESTS/**/*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_08*/test*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_09*/test*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
paths += [R/base['data_path']/n for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'candidates':candidates,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates);put(A/'실험/manifest.json',m)
