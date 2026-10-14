"""One sequential shard in a persistent process; per-case sessions remain independent."""
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
import argparse,json,runpy,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0716-main50-cm51-investigation-profile'
p=argparse.ArgumentParser();p.add_argument('--worker',required=True,type=int,choices=range(3));args=p.parse_args()
assert (A/'artifacts/question-export-authorization.json').is_file(),'Question export approval has not been recorded'
cases=json.loads((A/'artifacts/design/dataset.json').read_text())['cases']
for c in cases[args.worker::3]:
 cid=c['case_id'];out=A/'artifacts/run-001'/cid;log=A/'artifacts'/('console-'+cid+'.log')
 if out.exists() or log.exists():
  print('PRESERVED existing or interrupted case; never resending',cid,flush=True);continue
 sys.argv=[str(R/'06_TOOLS/EXPERIMENTS/adr_0716/run_case.py'),'--case',cid]
 with log.open('x') as f,redirect_stdout(f),redirect_stderr(f):
  runpy.run_path(sys.argv[0],run_name='__main__')
 row=json.loads((out/'result.json').read_text())
 assert row['active_pointer_before']==row['active_pointer_after'],'MAIN changed; stop sending'
 calls=row['attempts'];investigate=[x for x in calls if not x['phase'].startswith('memory-assess')]
 print(json.dumps({'case_id':cid,'http_status':row['http_status'],'all_calls':row['model_calls'],'investigation_calls':len(investigate),'investigation_seconds':sum(x['seconds'] for x in investigate)},ensure_ascii=False),flush=True)
