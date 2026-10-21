"""Apply exactly qualified deltas; preserve concurrent work and active release."""
from pathlib import Path
import json,hashlib,tarfile,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification';D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert read(A/'artifacts/run-001/result.json')['strict_success']
f=read(D/'freeze.json');S=R/f['code_root'];before=read(D/'working-rebased-before.json')
assert not (A/'artifacts/working-integration.json').exists()
assert all((sha(R/n) if (R/n).exists() else None)==h for n,h in before.items()),'concurrent working change'
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline-rebased.json')['pointer_sha256']
assert all(sha(R/n)==h for n,h in f['files'].items()),'qualified input drift'
allowed=set(read(D/'rebase.json')['reviewed_changes'])
changed={n:sha(S/n) for n,h in before.items() if (S/n).exists() and sha(S/n)!=h}
assert all(n in allowed or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in changed)
rows=[{'path':n,'before':before[n],'after':h} for n,h in changed.items()]
backup=A/'artifacts/working-before.tar.gz'
with tarfile.open(backup,'w:gz') as out:
 for row in rows:
  if row['before'] is not None:out.add(R/row['path'],arcname=row['path'],recursive=False)
put(A/'artifacts/working-integration-progress.json',{'status':'prepared','changes':rows,'backup_sha256':sha(backup)})
for row in rows:
 n=row['path'];p=R/n
 assert (sha(p) if p.exists() else None)==row['before'],('concurrent change during apply',n)
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.adr0850.tmp')
 assert not tmp.exists();tmp.write_bytes((S/n).read_bytes());os.replace(tmp,p)
assert all(sha(R/n)==h for n,h in changed.items())
assert all(sha(R/n)==sha(S/n) for n in before if (S/n).exists()),'working candidate mismatch'
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':rows,'implementation_files':sorted(allowed),
 'candidate':f['candidate'],'code_root':f['code_root'],'all_registered_files_equal':True,
 'backup':str(backup.relative_to(R)),'backup_sha256':sha(backup),
 'active_pointer_changed':False,'genos_deployed':False,
 'graph_limitation':'Global graph has retained historical errors; no ADR0848/0850 error. final-validation.txt is PASS.',
 'rollback':'Restore only paths whose current hash equals this receipt after hash; preserve new edits. Restore backup bytes or remove new minimal_output.py. Active release was not changed.'})
print('Integrated',len(allowed),'implementation files and',len(rows)-len(allowed),'engine/pipeline pins; active release unchanged')
