"""Apply only reviewed deltas; keep concurrent unrelated files intact."""
from pathlib import Path
import json,hashlib,tarfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
result=read(A/'artifacts/run-001/result.json')
assert result['all_answers_completed'] and result['all_source_checks_passed'] and result['all_duplicates_identical_without_calls']
assert read(A/'artifacts/followup-audit.json')['same_goal_and_prior_evidence']
b=read(D/'retained-binding.json');C=R/b['code_root'];changes=read(D/'changes.json');names={x['path'] for x in changes}
assert all(sha(R/x['path'])==x['before'] and sha(C/x['path'])==x['after'] for x in changes)
assert all(sha(R/n)==h for n,h in b['serving_files'].items() if n not in names)
backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
with tarfile.open(backup,'w:gz') as tar:
 for x in changes:tar.add(R/x['path'],arcname=x['path'],recursive=False)
put(A/'artifacts/working-integration-plan.json',{'changes':changes,'backup':str(backup.relative_to(R)),'backup_sha256':sha(backup),'rollback':'Restore listed files from this archive only after verifying current after hashes; engine and pipeline pins are included.'})
for x in changes:(R/x['path']).write_bytes((C/x['path']).read_bytes())
assert all(sha(R/n)==h for n,h in b['serving_files'].items())
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'serving_files_exact':len(b['serving_files']),'candidate':b['candidate'],'active_pointer_changed':False,'GENOS_changed':False})
print('Integrated',len(changes),'reviewed files;',len(b['serving_files']),'serving files exact')
