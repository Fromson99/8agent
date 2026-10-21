"""One frozen pair of requests, serialized and guarded, without request replay."""
from pathlib import Path
import subprocess, sys, json, datetime, time
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0952-risk-photo-live-comparison'
schedule=json.loads((A/'artifacts/design/schedule.json').read_text())
receipt=A/'artifacts/sequence.jsonl'
assert not receipt.exists(),'Never replay a complete or partial request with a new budget'
with receipt.open('x') as out:
    for i,row in enumerate(schedule,1):
        if i>1:time.sleep(30)
        stem=f"{i:02d}-{row['arm']}-{row['case_id']}"
        cmd=[sys.executable,'06_TOOLS/EXPERIMENTS/resource_guard.py','--record',str(A/f'artifacts/resource-{stem}.json'),
            '--rss-gib','6','--as-gib','8','--min-available-gib','4','--min-disk-gib','10',
            '--',sys.executable,str(T/'live.py'),row['arm'],row['case_id']]
        print('START '+stem,flush=True)
        started=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (A/f'artifacts/{stem}.log').open('x') as log:
            run=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT)
        value={**row,'number':i,'started_at':started,'returncode':run.returncode,'command':cmd}
        p=A/'artifacts/run-001'/row['arm']/row['case_id']/'result.json'
        if p.exists():
            with (A/f'artifacts/{stem}-audit.log').open('x') as log:
                audit=subprocess.run([sys.executable,str(T/'audit.py'),row['arm'],row['case_id']],cwd=R,stdout=log,stderr=subprocess.STDOUT)
            value['audit_returncode']=audit.returncode
        out.write(json.dumps(value,ensure_ascii=False)+'\n');out.flush()
        print('END '+json.dumps(value,ensure_ascii=False),flush=True)
