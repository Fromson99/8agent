"""Execute the frozen sequence once, one memory-heavy process at a time."""
from pathlib import Path
import subprocess,sys,json,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update';D=A/'artifacts/design';T=Path(__file__).parent
schedule=json.loads((D/'schedule.json').read_text());receipt=A/'artifacts/sequence.jsonl'
assert not receipt.exists(),'No adaptive replay of completed/partial requests'
with receipt.open('x') as out:
 for i,row in enumerate(schedule,1):
  arm,case=row['arm'],row['case_id'];stem=f'{i:02d}-{arm}-{case}';log=A/('artifacts/'+stem+'.log')
  cmd=[sys.executable,'06_TOOLS/EXPERIMENTS/resource_guard.py','--record',str(A/('artifacts/resource-'+stem+'.json')),'--rss-gib','6','--as-gib','8','--min-available-gib','4','--min-disk-gib','10','--',sys.executable,str(T/'live.py'),arm,case]
  print('START',stem,flush=True)
  start=datetime.datetime.now(datetime.timezone.utc).isoformat()
  with log.open('x') as f:run=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT)
  record={**row,'number':i,'started_at':start,'returncode':run.returncode,'log':str(log.relative_to(R))}
  p=A/'artifacts/run-001'/arm/case/'result.json'
  if p.exists():
   with (A/('artifacts/'+stem+'-audit.log')).open('x') as f:audit=subprocess.run([sys.executable,str(T/'audit.py'),arm,case],cwd=R,stdout=f,stderr=subprocess.STDOUT)
   record['audit_returncode']=audit.returncode
  out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush();print('END',json.dumps(record,ensure_ascii=False),flush=True)
