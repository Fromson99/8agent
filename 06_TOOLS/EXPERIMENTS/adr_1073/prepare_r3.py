"""Repair measurement-only main-table snapshot, retaining the failed run."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design-r2';D2=A/'artifacts/design-r3'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not D2.exists();D2.mkdir()
old=read(D/'freeze.json');old_code=R/old['code_root'];cm=read(R/old['candidate']['manifest_path']);m=read(A/'실험/manifest.json')
for name in ('criteria.json','baseline.json','working-before.json','candidate-preparation.json'):shutil.copyfile(D/name,D2/name)
put(D2/'runner-correction.json',{'reason':'Expected visible-anchor fixture ignored SQL NOT IN three-valued logic: a hidden endpoint with NULL reference_id causes all references to be hidden in the unchanged baseline. Preserve this fail-closed behavior and correct only the algebraic expected rows; product and finite case set unchanged.','failed_run':'run-002','failed_record_sha256':sha(A/'artifacts/run-002/FAILED.json'),'criteria_and_product_unchanged':True,'new_run':'run-003','old_runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit_r2.py')})
m['runs'][1].update(status='failed',artifact_path=str((A/'artifacts/run-002/FAILED.json').relative_to(R)),sha256=sha(A/'artifacts/run-002/FAILED.json'),failure_category='fixture_expected_null_not_in')
m['runs'].append({'id':'run-003','purpose':'primary','parent_run_id':'run-002','arm_ids':['baseline','optimized'],'selection_rule':m['runs'][1]['selection_rule'],'status':'planned','artifact_path':str((A/'artifacts/run-003/result.json').relative_to(R)),'sha256':'PENDING','runner_correction':str((D2/'runner-correction.json').relative_to(R))})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','sql-main-r3','--experiment-id',m['experiment_id'],'--arm-id','optimized','--run-id','run-003']
for row in cm['files']:cmd+=['--source',row['target_path']]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_1073/sql-main-r3'
for row in cm['files']:shutil.copyfile(old_code/row['target_path'],C/'snapshot'/row['target_path'])
text=(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit_r2.py').read_text().replace("D=A/'artifacts/design-r2'","D=A/'artifacts/design-r3'").replace('artifacts/run-002','artifacts/run-003')
text=text.replace("     assert rows==sorted(expected)","     if rstate=='null' and endpoint=='hidden':expected=[]\n     assert rows==sorted(expected)")
(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit_r3.py').write_text(text)
freeze=(R/'06_TOOLS/EXPERIMENTS/adr_1073/freeze_r2.py').read_text().replace("D=A/'artifacts/design-r2'","D=A/'artifacts/design-r3'").replace('sql-main-r2','sql-main-r3').replace("['run-002']","['run-003']").replace('adr_1073/audit_r2.py','adr_1073/audit_r3.py')
(R/'06_TOOLS/EXPERIMENTS/adr_1073/freeze_r3.py').write_text(freeze)
print('Preserved first two runner failures; same628case/product criteria, NULL fail-closed expected result corrected')
