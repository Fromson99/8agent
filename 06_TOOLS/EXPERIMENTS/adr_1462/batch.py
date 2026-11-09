"""Each question once per arm (baseline, then candidate), one isolated process per request; no automatic retries."""
from common import *
import subprocess,time,html,fcntl
from progress_panel import ProgressPanel

def main():
 cases=read(DES/'live-cases.json');results=[];consecutive_unknown=0
 lock=(ART/'batch.lock').open('a+')
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (ART/'batch-started.json').exists():raise RuntimeError('Existing batch may not be replayed')
 started=time.time();put(ART/'batch-started.json',{'time':started,'pid':os.getpid(),'cases':len(cases)})
 stop=None
 def sink(fragment,plain,final):
  rows=''.join('<tr><td>'+html.escape(r['case_id'])+'</td><td>'+html.escape(str(r.get('http_status','未完了')))+'</td><td>'+html.escape(str(r.get('seconds','')))+'</td><td>'+html.escape(r['arm'])+'</td><td><a href="public-live/'+r['case_id']+'-'+r['arm']+'/turn-1/public-answer.txt">답변</a></td></tr>' for r in results)
  page='<!doctype html><html lang="ko"><meta charset="utf-8">'+('' if final else '<meta http-equiv="refresh" content="3">')+'<title>이하 약칭 검색 · 6문항 × 2</title><body>'+fragment+'<p>완료량은 시험 요청 종료 건수입니다. 정답 여부는 별도 검토합니다. 약칭 질문 5 + 정식 이름 대조 1, 기준(MAIN178)과 후보 각 1회.</p><table><tr><th>질문</th><th>HTTP</th><th>초</th><th>갈래</th><th>결과</th></tr>'+rows+'</table></body></html>'
  temp=ART/'.status.html.tmp';temp.write_text(page);os.replace(temp,ART/'통합테스트_상태.html')
 panel=ProgressPanel('ADR-1462 · 이하 약칭 검색 · 6문항 × 2',str(ART/'batch.log'),sink=sink)
 panel.start_phase('실제 질문 순차 실행',total=2*len(cases),unit='요청')
 for case,arm in [(c,a) for c in cases for a in ('baseline','candidate')]:
  cid=case['id'];folder=ART/'public-live'/(cid+'-'+arm)
  panel.update(message=cid+' '+arm+' · '+case['steps'][0]['question'])
  with (ART/'batch.log').open('a') as log:
   proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('live.py')),cid,arm],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   while proc.poll() is None:
    calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
    stage=calls[-1].get('stage','서비스 준비') if calls else '서비스 준비'
    panel.update(message=cid+' · '+str(stage),metrics={'현재 문항 모델호출':len(calls)})
    time.sleep(1)
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'result.json') if (folder/'result.json').exists() else {}
  turns=result.get('turns',[]);turn=turns[-1] if turns else {}
  unknown=any(c['status'] in ('unknown','started') for c in calls)
  row={'case_id':cid,'arm':arm,'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'physical_calls':len(calls),'unknown':unknown,'claims':turn.get('claims',0),'needs_guidance':turn.get('needs_guidance')}
  results.append(row);put(folder/'worker-exit.json',row)
  consecutive_unknown=consecutive_unknown+1 if unknown else 0
  if proc.returncode!=0:stop='Runner or resource failure; inspect preserved worker diagnostics'
  elif consecutive_unknown>=3:stop='Three consecutive independent questions ended with UNKNOWN transport outcomes'
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=200 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=1.5:stop='Frozen experiment budget reached'
  put(ART/'batch-status.json',{'state':'STOPPED' if stop else 'RUNNING','completed_requests':len(results),'total':2*len(cases),'cases':results,'stop':stop,'physical_calls':len(allcalls)})
  panel.update(done=len(results),message=cid+' 실행 종료')
  print(json.dumps(row,ensure_ascii=False),flush=True)
  if not stop and time.time()-started>=45*60 and len(results)<2*len(cases):stop='Frozen 45-minute time box reached before the next request'
  if stop:break
 status='STOPPED' if stop else 'EXECUTION_FINISHED_REVIEW_REQUIRED'
 put(ART/'batch-completed.json',{'state':status,'cases':results,'stop':stop,'remaining':[(c['id'],a) for c in cases for a in ('baseline','candidate')][len(results):],'quality_certified':False})
 if stop:panel.finish('STOPPED',message=stop)
 else:panel.finish('UNKNOWN',message='12요청 실행 종료. 원문 대조·정답 검토 중.')
 print(status,flush=True)

if __name__=='__main__':main()
