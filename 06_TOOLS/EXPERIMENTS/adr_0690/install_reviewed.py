"""Install only reviewed judgment edits after qualification; preserve other work."""
from pathlib import Path
import json,hashlib,shutil,subprocess,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');code=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);rows={x['target_path']:x for x in cm['files']}
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
scoped=['02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py','02_BACKEND/semantic_runtime/legal_agent/law_navigation.py','05_TESTS/CONTRACTS/test_judgment_loop_recovery.py']
extra='05_TESTS/CONTRACTS/test_judgment_loop_review_repairs.py';extra_source=R/'06_TOOLS/EXPERIMENTS/adr_0689/test_review_repairs.py'
assert not (R/extra).exists()
for p in scoped:assert sha(R/p)==rows[p]['upstream_sha256'],p
for p,h in f['serving_files'].items():assert sha(code/p)==h,p
pins=['00_SYSTEM/PIPELINE.json']+sorted({e['manifest'] for e in read(R/'00_SYSTEM/PIPELINE.json')['engines'].values()})
before={str(p.relative_to(R)):sha(p) for p in (R/'02_BACKEND/semantic_runtime').rglob('*.py')}
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False);plan=[]
for p in scoped+pins+[extra]:
 path=R/p;h=sha(path) if path.exists() else None
 if h:
  target=backup/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
 plan.append({'path':p,'before':h,'kind':'runtime' if p in scoped[:2] else 'test' if p in scoped[2:]+[extra] else 'engine-pin'})
put(A/'artifacts/working-install-plan.json',{'files':plan,'backup':str(backup.relative_to(R)),'unrelated_runtime_before':before})
for p in scoped+[extra]:
 source=extra_source if p==extra else code/p;target=R/p;temp=target.with_name('.'+target.name+'.judgment-install')
 shutil.copy2(source,temp);os.replace(temp,target)
with (A/'artifacts/working-rehash.json').open('w') as out:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','rehash-engines','--apply'],cwd=R,check=True,stdout=out)
for p,h in before.items():
 if p not in scoped:assert sha(R/p)==h,p
for row in plan:row['after']=sha(R/row['path'])
put(A/'artifacts/working-install-receipt.json',{'status':'installed','files':plan,'scoped_runtime_matches_candidate':all(sha(R/p)==sha(code/p) for p in scoped[:2]),'unrelated_runtime_preserved':True,'main_pointer_unchanged':True})
print('Installed two runtime files and maintained tests; unrelated runtime preserved')
