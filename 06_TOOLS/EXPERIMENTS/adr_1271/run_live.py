"""Run each predeclared cell once, serially; preserve unavailable/failed cells."""
from common import *
import subprocess
T=Path(__file__).parent
outcomes=[];stop=None
for case in read(DES/'cases.json'):
 name=case['id']
 if stop:
  outcomes.append({'case_id':name,'status':'NOT_RUN','reason':stop});continue
 log=ART/('live-'+name+'.log')
 with log.open('x') as stream:
  process=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(T/'live.py'),name],stdout=stream,stderr=subprocess.STDOUT)
  print('START',name,'pid',process.pid,flush=True);code=process.wait()
 base=ART/'live'/name
 if not (base/'result.json').exists():
  stop='Preparation/resource interruption; inspect preserved log before further calls'
  outcomes.append({'case_id':name,'exit':code,'status':'INCOMPLETE','reason':stop});continue
 result=read(base/'result.json');outcomes.append(result|{'exit':code})
 with (ART/('audit-'+name+'.log')).open('x') as stream:
  audit=subprocess.run([str(ROOT/'.venv/bin/python'),str(T/'audit.py'),name],stdout=stream,stderr=subprocess.STDOUT)
 calls=read(base/'calls.json');unknown=any(r['status'] in ('unknown','started') for r in calls)
 if unknown:stop='UNKNOWN preserved; no additional actual model cells'
 elif calls and calls[-1].get('http_status')==429:stop='Confirmed provider 429 exhaustion'
 elif result.get('error_type'):stop='Harness or unhandled execution error'
 elif audit.returncode:stop='Offline source/wire audit failed'
 elif not result.get('injections'):stop='No qualifying READ; NOT_TESTED, remaining cells stopped'
 print('DONE',name,result.get('http_status'),'calls',len(calls),'stop',stop,flush=True)
put(ART/'live-runner-summary.json',{'cells':outcomes,'stop':stop,'same_cell_redispatch':0})
