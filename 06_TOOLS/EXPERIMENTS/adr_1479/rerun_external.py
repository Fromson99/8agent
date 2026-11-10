"""Deviation (recorded before the calls, deviation-external-rerun.json): every question whose first model
call got a provider 5xx (STOP_EXTERNAL.json, provider profile C = Near AI first) runs once more alone with the
same profile, in its own folder (…-candidate-rerun). Stops at the first question that gets a 5xx again."""
from common import *
import subprocess,time
def main():
 todo=[c for c in read(DES/'live-cases.json') if (ART/'public-live'/(c['id']+'-candidate')/'STOP_EXTERNAL.json').exists()
       and not (ART/'public-live'/(c['id']+'-candidate-rerun')).exists()]
 if not (ART/'deviation-external-rerun.json').exists():
  put(ART/'deviation-external-rerun.json',{'time':time.time(),'cases':[c['id'] for c in todo],'reason':'Provider profile C (Near AI FP8 first) answered HTTP 5xx on the first call of all 17 of its questions; the frozen rule reruns only resource stops. These questions run once more with the same profile so the comparison with ADR-1478 keeps the same provider per question.','frozen_rule_changed':False,'stop_on_repeat_5xx':True})
 for case in todo:
  if (ART/'STOP_ALL.json').exists():break
  folder=ART/'public-live'/(case['id']+'-candidate-rerun')
  with (ART/'rerun-external.log').open('a') as log:
   log.write('\n=== '+case['id']+' '+time.strftime('%H:%M:%S')+'\n');log.flush()
   proc=subprocess.run([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),case['id'],'--rerun'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_PROFILE':case['provider_profile']})
  result=read(folder/'result.json') if (folder/'result.json').exists() else {};turn=(result.get('turns') or [{}])[-1]
  row={'case_id':case['id'],'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'external_stop':(folder/'STOP_EXTERNAL.json').exists()}
  put(folder/'worker-exit.json',row);print(json.dumps(row,ensure_ascii=False),flush=True)
  if row['external_stop']:print('STOPPED: provider 5xx again');break
if __name__=='__main__':main()
