"""Continue the frozen single rerun after the session time limit killed rerun.py (deviation-harness-timeout.json):
resource-stopped questions with no rerun result yet run once alone."""
from common import *
import subprocess,time
for cid in json.loads(sys.argv[1]):
 case=next(c for c in read(DES/'live-cases.json') if c['id']==cid)
 folder=ART/'public-live'/(cid+'-candidate-rerun')
 if folder.exists():continue
 with (ART/'rerun.log').open('a') as log:
  log.write('\n=== '+cid+' rerun (continued) '+time.strftime('%H:%M:%S')+'\n');log.flush()
  proc=subprocess.run([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),cid,'--rerun'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_PROFILE':case['provider_profile']})
 result=read(folder/'result.json') if (folder/'result.json').exists() else {};turn=(result.get('turns') or [{}])[-1]
 row={'case_id':cid,'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'continued':True}
 put(folder/'worker-exit.json',row);print(json.dumps(row,ensure_ascii=False),flush=True)
