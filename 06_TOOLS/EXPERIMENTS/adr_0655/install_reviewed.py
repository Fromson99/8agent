"""Install exact reviewed files only after qualified source completion, with backups."""
import hashlib,json,os,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0655-shortcut-serving-closure';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def binding(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
m=read(A/'실험/manifest.json');result=A/'artifacts/run-001/result.json';assert read(result)['strict_success'] is True
assert m['reservation']['status']=='completed' and m['decision_eligible'] is True and m['in_sample'] is False
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
q={'source':binding(A/'실험/manifest.json'),'readme':binding(A/'README.md'),'arm':'integrated','result':binding(result),'rebase':binding(D/'release-rebase.json')}
report={'structural_checks_passed':True,'contract_tests':103,'integration':read(D/'integration.json'),'source_final_validation':binding(A/'artifacts/final-validation.txt'),'source_result':binding(result),'limitations':['Small separated public/synthetic validation, not expert legal certification','GENOS not executed']}
authorization={'authorized_by':'user','authorization_text':'최초 선별 실패와 실제 모델 멀티턴 검증까지 하고 메인 배선해봐','quality_gate_override':False,'qualification':q,'rollback_pipeline':{'path':str((A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json').relative_to(R)),'sha256':sha(R/'00_SYSTEM/PIPELINE.json')}}
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',report)
b=read(D/'bindings.json');C=R/b['candidate'];c=read(C/'candidate.json');rev=c['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,authorization,report)
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']
for f,h in read(D/'release-freeze.json')['files'].items():assert sha(R/f)==h,f
frozen={f['snapshot_path']:f for f in rev['files']};changes=[]
for row in c['files']:
 target=R/row['target_path'];before=sha(target) if target.exists() else None
 assert before==row.get('upstream_sha256'), 'Concurrent working tree change: '+row['target_path']
 f=frozen[row['snapshot_path']];after=f['snapshot_sha256'];assert sha(R/f['frozen_path'])==after
 if before!=after:changes.append({'path':row['target_path'],'before':before,'after':after,'frozen_path':f['frozen_path']})
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
for row in changes:
 target=R/row['path']
 if row['before'] is not None:
  saved=backup/row['path'];saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved);assert sha(saved)==row['before']
put(A/'artifacts/working-install-plan.json',{'source':q,'files':changes,'backup':str(backup.relative_to(R))})
installed=[]
try:
 for row in changes:
  target=R/row['path'];assert (sha(target) if target.exists() else None)==row['before'];target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.'+target.name+'.shortcut-install');shutil.copy2(R/row['frozen_path'],temp);os.replace(temp,target);installed.append(row)
 for row in installed:assert sha(R/row['path'])==row['after']
except BaseException:
 for row in reversed(installed):
  target=R/row['path']
  if row['before'] is None:target.unlink()
  else:shutil.copy2(backup/row['path'],target)
 raise
put(A/'artifacts/working-install-receipt.json',{'status':'installed','count':len(installed),'files':installed,'main_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']});print('Installed reviewed files',len(installed))
