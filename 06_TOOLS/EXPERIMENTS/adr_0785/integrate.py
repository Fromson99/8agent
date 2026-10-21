"""Apply only audited deltas after the implementation decision, with CAS receipts."""
from pathlib import Path
import hashlib,json,os,tempfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json');decision=read(A/'artifacts/implementation-decision.json')
assert result['strict_success'] and decision['working_integration_approved'] and not decision['main_promotion_approved']
assert not (A/'artifacts/working-integration.json').exists()
assert all(sha(R/p)==h for p,h in f['files'].items())
code=R/f['code_root'];changes=[]
for name,h in f['serving_files'].items():
 p=R/name;before=sha(p) if p.exists() else None
 assert before==f['upstream'][name],name+' changed concurrently; manual reconciliation required'
 if before!=h:changes.append({'path':name,'before':before,'after':h})
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=True)
for row in changes:
 p=R/row['path'];p.parent.mkdir(parents=True,exist_ok=True)
 if row['before'] is not None:
  b=backup/row['before']
  if not b.exists():b.write_bytes(p.read_bytes())
  row['backup']=str(b.relative_to(R))
 # Per-file replacement is atomic; the full receipt is published only after all hashes match.
 with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as handle:
  handle.write((code/row['path']).read_bytes());temp=Path(handle.name)
 os.chmod(temp,p.stat().st_mode if p.exists() else 0o644);os.replace(temp,p)
assert all(sha(R/n)==h for n,h in f['serving_files'].items())
receipt={'status':'applied','code_root':f['code_root'],'changes':changes,'all_serving_bytes_equal':True,
 'main_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'main_changed':False,'genos_deployed':False,
 'rollback':'Restore only each recorded backup or remove a newly added file after checking that its current hash still equals after. Then verify engine pins. Never overwrite concurrent changes.'}
(A/'artifacts/working-integration.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print('Integrated',len(changes),'files; MAIN pointer unchanged')
