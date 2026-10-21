from pathlib import Path
import json,subprocess,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0827-comparison-resume-live-check';O=A/'artifacts/run-001/risk-104'
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
with (A/'artifacts/live.log').open('w') as log:r=subprocess.run([str(R/'.venv/bin/python'),str(T/'live.py'),'risk-104'],stdout=log,stderr=subprocess.STDOUT,timeout=1920)
print('original process exit',r.returncode,flush=True)
if r.returncode==73:
 assert (O/'injection.json').exists() and not (O/'result.json').exists()
 p=next((O/'runtime/workflows').glob('*/journal.sqlite'));db=sqlite3.connect(p);db.row_factory=sqlite3.Row
 row=dict(db.execute('select revision,status from workflow_state').fetchone());row.update(dict(db.execute('select run_id,started_at,deadline_at from run').fetchone()));row.update(dict(db.execute('select model_reserved,tool_used from budget').fetchone()));db.close()
 plan={'reason':'Predeclared process exit after durable external source checkpoint; exact revision resume','before':row,'previous_calls':len(list((O/'raw').glob('call-*'))),'previous_usage_entries':len(json.loads((O/'raw/usage.json').read_text())),'product_code_changed':False,'budget_reset':False}
 assert row['status']=='running' and plan['previous_calls']==row['model_reserved']
 put(A/'artifacts/resume-plan.json',plan)
 put(A/'artifacts/resume-freeze.json',{'files':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (T/'resume.py',A/'artifacts/resume-plan.json')},'same_request_and_budget':True})
 with (A/'artifacts/resume.log').open('w') as log:r=subprocess.run([str(R/'.venv/bin/python'),str(T/'resume.py'),'risk-104'],stdout=log,stderr=subprocess.STDOUT,timeout=1920)
 print('resume process exit',r.returncode,flush=True)
raise SystemExit(r.returncode)
