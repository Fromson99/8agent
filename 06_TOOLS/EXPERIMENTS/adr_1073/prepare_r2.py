"""Repair measurement-only main-table snapshot, retaining the failed run."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design';D2=A/'artifacts/design-r2'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not D2.exists();D2.mkdir()
old=read(D/'freeze.json');old_code=R/old['code_root'];cm=read(R/old['candidate']['manifest_path']);m=read(A/'실험/manifest.json')
for name in ('criteria.json','baseline.json','working-before.json','candidate-preparation.json'):shutil.copyfile(D/name,D2/name)
put(D2/'runner-correction.json',{'reason':'sqlite3.iterdump uses unqualified table SELECTs and therefore sees installed TEMP visibility views. First baseline fixture was misclassified as main mutation. Use explicit main.sqlite_master and main.<table> snapshots.','failed_run':'run-001','failed_record_sha256':sha(A/'artifacts/run-001/FAILED.json'),'criteria_and_product_unchanged':True,'new_run':'run-002','old_runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit.py')})
m['runs'][0].update(status='failed',artifact_path=str((A/'artifacts/run-001/FAILED.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/FAILED.json'),failure_category='measurement_fixture_main_namespace')
m['runs'].append({'id':'run-002','purpose':'primary','parent_run_id':'run-001','arm_ids':['baseline','optimized'],'selection_rule':m['runs'][0]['selection_rule'],'status':'planned','artifact_path':str((A/'artifacts/run-002/result.json').relative_to(R)),'sha256':'PENDING','runner_correction':str((D2/'runner-correction.json').relative_to(R))})
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','sql-main-r2','--experiment-id',m['experiment_id'],'--arm-id','optimized','--run-id','run-002']
for row in cm['files']:cmd+=['--source',row['target_path']]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_1073/sql-main-r2'
for row in cm['files']:shutil.copyfile(old_code/row['target_path'],C/'snapshot'/row['target_path'])
text=(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit.py').read_text().replace("D=A/'artifacts/design'","D=A/'artifacts/design-r2'").replace('artifacts/run-001','artifacts/run-002')
helper='''def main_snapshot(db):
 schema=db.execute("SELECT type,name,sql FROM main.sqlite_master ORDER BY type,name").fetchall()
 rows={name:db.execute('SELECT * FROM main."'+name.replace('"','""')+'" ORDER BY rowid').fetchall()
       for kind,name,sql in schema if kind=='table' and not name.startswith('sqlite_')}
 return schema,rows
'''
text=text.replace('def selected(module,tmp):',helper+'def selected(module,tmp):').replace('list(db.iterdump())','main_snapshot(db)')
(R/'06_TOOLS/EXPERIMENTS/adr_1073/audit_r2.py').write_text(text)
freeze=(R/'06_TOOLS/EXPERIMENTS/adr_1073/freeze.py').read_text().replace("D=A/'artifacts/design'","D=A/'artifacts/design-r2'").replace('adr_1073/sql-main-r1','adr_1073/sql-main-r2').replace("'sql-main-r1'","'sql-main-r2'").replace("['run-001']","['run-002']").replace('adr_1073/audit.py','adr_1073/audit_r2.py')
freeze=freeze.replace("m['design']['code_isolation']['candidates']=[", "m['design']['code_isolation']['candidates'] += [")
(R/'06_TOOLS/EXPERIMENTS/adr_1073/freeze_r2.py').write_text(freeze)
print('Preserved run001; identical product and criteria; explicit main namespace measurement repair')
