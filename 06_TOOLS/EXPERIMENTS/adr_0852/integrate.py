"""Apply reviewed task deltas with concurrent-file CAS and a lossless backup."""
from pathlib import Path
import json,hashlib,tarfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0852-basis-workflow-ingress-repair';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0847-basis-link-lifecycle/artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');C=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);before=read(D/'working-before.json');initial=read(P/'working-before.json');merge=read(P/'concurrent-service-merge.json');base=read(D/'baseline.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
changes=[]
for row in cm['files']:
 n=row['target_path'];after=sha(C/n);current=sha(R/n) if (R/n).exists() else None
 if current==after:continue
 assert current==before.get(n),('concurrent change',n)
 assert n=='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',('unexpected new repair',n)
 changes.append({'path':n,'before':current,'after':after})
backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
with tarfile.open(backup,'w:gz') as archive:
 for row in changes:
  if row['before'] is not None:archive.add(R/row['path'],arcname=row['path'],recursive=False)
put(A/'artifacts/working-integration-plan.json',{'changes':changes,'backup':str(backup.relative_to(R)),'backup_sha256':sha(backup)})
for i,row in enumerate(changes):
 p=R/row['path'];assert (sha(p) if p.exists() else None)==row['before'],('changed during write',row['path'])
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((C/row['path']).read_bytes())
 put(A/'artifacts/working-integration-progress.json',{'completed':i+1,'total':len(changes)})
assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'all698_candidate_files_match':True,'candidate':f['candidate'],'active_pointer_changed':False,'genos_deployed':False,'backup':str(backup.relative_to(R)),'backup_sha256':sha(backup)})
print('Integrated',len(changes),'reviewed deltas;698 candidate files match; pointer unchanged')
