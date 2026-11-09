"""One isolated request per question on local Oracle Gold + vector; no automatic request retries."""
from common import *
import subprocess,time,html,fcntl,urllib.request
from progress_panel import ProgressPanel
PORT=int(os.environ.get('ADR1459_EMBED_PORT','8765'))

def main():
 cases=read(DES/'live-cases.json');results=[];consecutive_unknown=0
 lock=(ART/'batch.lock').open('a+')
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (ART/'batch-started.json').exists():raise RuntimeError('Existing batch may not be replayed')
 with urllib.request.urlopen('http://127.0.0.1:%d/health'%PORT,timeout=5) as r:assert r.status==200,'embedding endpoint not ready'
 pre=sorted((ART/'public-ready').glob('*/result.json'));assert pre and all(read(p).get('ready') for p in pre),'preflight required'
 started=time.time();put(ART/'batch-started.json',{'time':started,'pid':os.getpid(),'cases':len(cases),'embedding_status':json.loads(open(ART/'embed-server/status.json').read()) if (ART/'embed-server/status.json').exists() else None})
 stop=None
 def sink(fragment,plain,final):
  rows=''.join('<tr><td>'+html.escape(r['case_id'])+'</td><td>'+html.escape(str(r.get('http_status','未完了')))+'</td><td>'+html.escape(str(r.get('seconds','')))+'</td><td>'+html.escape(str(r.get('sql_calls','')))+'</td><td><a href="public-live/'+r['case_id']+'-candidate/turn-1/public-answer.txt">답변</a></td></tr>' for r in results)
  page='<!doctype html><html lang="ko"><meta charset="utf-8">'+('' if final else '<meta http-equiv="refresh" content="3">')+'<title>MAIN178+수정 · Oracle 벡터 CM 9문항</title><body>'+fragment+'<p>로컬 Oracle Gold(cm-r12-engine)·벡터 초기검색. 완료량은 요청 종료 건수이며 정답 여부는 별도 검토합니다.</p><table><tr><th>질문</th><th>HTTP</th><th>초</th><th>SQL</th><th>결과</th></tr>'+rows+'</table></body></html>'
  temp=ART/'.status.html.tmp';temp.write_text(page);os.replace(temp,ART/'통합테스트_상태.html')
 panel=ProgressPanel('MAIN178+수정 · Oracle 벡터 · financial CM 9문항',str(ART/'batch.log'),sink=sink)
 panel.start_phase('실제 질문 순차 실행',total=len(cases),unit='문항')
 for case in cases:
  cid=case['id'];folder=ART/'public-live'/(cid+'-candidate')
  panel.update(message=cid+' · '+case['steps'][0]['question'])
  with (ART/'batch.log').open('a') as log:
   proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),cid],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   while proc.poll() is None:
    calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
    stage=calls[-1].get('stage','서비스 준비') if calls else '서비스 준비'
    panel.update(message=cid+' · '+str(stage),metrics={'현재 문항 모델호출':len(calls)})
    time.sleep(1)
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'result.json') if (folder/'result.json').exists() else {}
  turns=result.get('turns',[]);turn=turns[-1] if turns else {}
  unknown=any(c['status'] in ('unknown','started') for c in calls)
  row={'case_id':cid,'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'physical_calls':len(calls),'unknown':unknown,'claims':turn.get('claims',0),'needs_guidance':turn.get('needs_guidance'),'sql_calls':turn.get('sql_calls'),'embedding_calls':turn.get('embedding_calls')}
  results.append(row);put(folder/'worker-exit.json',row)
  consecutive_unknown=consecutive_unknown+1 if unknown else 0
  if proc.returncode!=0:stop='Runner or resource failure; inspect preserved worker diagnostics'
  elif consecutive_unknown>=3:stop='Three consecutive independent questions ended with UNKNOWN transport outcomes'
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=360 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=3:stop='Frozen experiment budget reached'
  put(ART/'batch-status.json',{'state':'STOPPED' if stop else 'RUNNING','completed_requests':len(results),'total':len(cases),'cases':results,'stop':stop,'physical_calls':len(allcalls)})
  panel.update(done=len(results),message=cid+' 실행 종료')
  print(json.dumps(row,ensure_ascii=False),flush=True)
  if not stop and time.time()-started>=40*60 and len(results)<len(cases):stop='Frozen 40-minute time box reached before the next question'
  if stop:break
 status='STOPPED' if stop else 'EXECUTION_FINISHED_REVIEW_REQUIRED'
 put(ART/'batch-completed.json',{'state':status,'cases':results,'stop':stop,'remaining':[c['id'] for c in cases[len(results):]],'quality_certified':False})
 if stop:panel.finish('STOPPED',message=stop)
 else:panel.finish('UNKNOWN',message='9문항 실행 종료. 원문 대조·정답 검토 중.')
 print(status,flush=True)

if __name__=='__main__':main()
