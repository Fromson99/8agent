"""One-click bounded R4 run. Reentry reads completed cells; never resends partial cells."""
from common import *
import argparse,csv,fcntl,html,subprocess,time,signal
from progress_panel import ProgressPanel
HERE=Path(__file__).parent

def classify(result, audit=None):
 if not result:return 'NOT_EXECUTED'
 turns=result.get('turns',[])
 if result.get('unknown') or any(t.get('unknown') for t in turns):return 'UNKNOWN'
 if not turns:return 'RUNNER_FAILED'
 if any(t.get('http_status')!=200 for t in turns):return 'API_FAILED'
 if any(not t.get('claims') for t in turns):return 'SOURCE_ONLY_OR_INCOMPLETE'
 if audit is None:return 'AUDIT_REQUIRED'
 if any(audit.get(k) for k in ('source_mismatches','acl_violations','wire_mismatches')) or not audit.get('budget_matches'):return 'INTEGRITY_FAILED'
 if result.get('case_id') in ('B03-03','B03-17'):
  for turn in turns:
   outcome=turn.get('accepted_outcome') or {}
   if (outcome.get('disposition'),outcome.get('answer_coverage'))!=('ANSWER','COVERED'):return 'PARTIAL_OR_UNVERIFIED'
 return 'EXPLANATION_REVIEW_REQUIRED'

def eligible(results):
 return len(results)==2 and all(x['verdict']=='EXPLANATION_REVIEW_REQUIRED' for x in results)

def observed():
 rows=[]
 for d in sorted((ART/'public-live').glob('*')):
  if not d.is_dir():continue
  calls=read(d/'calls.json') if (d/'calls.json').exists() else []
  result=read(d/'result.json') if (d/'result.json').exists() else None
  audit=read(d/'audit.json') if (d/'audit.json').exists() else None
  verdict=classify(result,audit)
  if not result and d.exists():verdict='INCOMPLETE_NO_RETRY'
  rows.append({'cell':d.name,'case_id':d.name.rsplit('-',1)[0],'provider':d.name.rsplit('-',1)[1], 'verdict':verdict,'calls':len(calls),'unknown':sum(c.get('status') in ('started','unknown') for c in calls),'reported_cost_usd':sum((c.get('usage') or {}).get('cost') or 0 for c in calls),'seconds':sum(t.get('request_seconds',0) for t in (result or {}).get('turns',[])),'claims':sum(t.get('claims',0) for t in (result or {}).get('turns',[]))})
 return rows

def report(state='RUNNING',selected=None):
 obs=observed();cases=read(DES/'live-cases.json');grading={x['id']:x for x in read(DES/'grading-only.json')}
 table=[]
 for c in cases:
  attempts=[x for x in obs if x['case_id']==c['id']]
  chosen=next((x for x in attempts if x['provider']==selected),None)
  status=chosen['verdict'] if chosen else 'MANUAL_UI_REQUIRED' if c['execution']=='MANUAL_UI' else 'INTERNAL_ENVIRONMENT_REQUIRED' if c['execution']=='INTERNAL_ENVIRONMENT' else 'SCREENED_ONLY' if attempts else 'NOT_EXECUTED'
  table.append({'id':c['id'],'title':c['title'],'execution':c['execution'],'status':status,'provider':selected if chosen else '', 'attempts':len(attempts),'expected':grading[c['id']]['expected'],'answer_path':str(ART/'public-live'/chosen['cell']/'turn-1/answer.txt') if chosen else ''})
 summary={'state':state,'selected_provider':selected,'total_cases':60,'all_passed':False,'quality_certified':False,'reason':'Actual GENOS UI/internal cases and independent semantic review remain required','physical_calls':sum(x['calls'] for x in obs),'unknown':sum(x['unknown'] for x in obs),'reported_cost_usd':sum(x['reported_cost_usd'] for x in obs),'cells':obs,'cases':table}
 put(ART/'summary.json',summary)
 with (ART/'통합테스트_결과.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
 body=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k in ('id','title','status','provider','expected'))+'</tr>' for r in table)
 text='<meta charset="utf-8"><meta http-equiv="refresh" content="10"><title>통합테스트 진행</title><style>body{font:15px sans-serif;margin:28px;background:#f4f6fa}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}table{background:white;border-collapse:collapse}h1{font-size:25px}</style><h1>R4 통합테스트 — '+html.escape(state)+'</h1><p>전체 60개 · 모델 호출 '+str(summary['physical_calls'])+'회 · 보고 비용 $'+format(summary['reported_cost_usd'],'.5f')+' · 미확정 호출 '+str(summary['unknown'])+'회</p><p>전체 통과 아님. 설명 생성, 원문 일치, 의미 검토, 실제 화면 확인을 구분합니다.</p><table><tr><th>번호</th><th>항목</th><th>상태</th><th>제공자</th><th>기대 결과</th></tr>'+body+'</table>'
 temp=ART/'.status.html';temp.write_text(text);os.replace(temp,ART/'통합테스트_상태.html')
 return summary

def execute_cell(case,provider,panel,done,total):
 d=ART/'public-live'/(case+'-'+provider)
 if d.exists():return # Completed or interrupted physical work is never replayed.
 if (ART/('STOP_'+provider+'.json')).exists():return
 previous=observed()
 if sum(x['calls'] for x in previous)>=1560 or sum(x['reported_cost_usd'] for x in previous)>=10:raise RuntimeError('Frozen total call/cost stop')
 log=ART/(case+'-'+provider+'.log')
 with log.open('x') as stream:
  proc=subprocess.Popen([sys.executable,str(HERE/'live_public.py'),case,provider],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   while proc.poll() is None:
    calls=read(d/'calls.json') if (d/'calls.json').exists() else []
    panel.update(done=done,total=total,message=f'{provider} / {case} / 호출 {len(calls)}회',metrics={'마지막 단계':calls[-1].get('stage','준비') if calls else '준비'})
    report(selected=None);time.sleep(1)
  except BaseException:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=8)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   put(ART/('STOP_'+provider+'.json'),{'reason':'User interruption; process collected; remote outcome unconfirmed','no_retry':True});raise
 put(d/'worker-exit.json',{'returncode':proc.returncode,'process_collected':True})
 # A successful process is not an answer success. Audit native stored evidence.
 with (ART/'audit.log').open('a') as log:
  audit=subprocess.run([sys.executable,str(HERE/'audit.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
 if audit.returncode:raise RuntimeError('Source/wire audit failed; see audit.log')
 if proc.returncode and not (d/'result.json').exists():
  put(ART/('STOP_'+provider+'.json'),{'reason':'Runner/resource failure; remaining cells quarantined','no_retry':True})

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--status',action='store_true');parser.add_argument('--screen-only',action='store_true');args=parser.parse_args()
 if args.status:
  s=read(ART/'summary.json') if (ART/'summary.json').exists() else report('NOT_STARTED');print(json.dumps({k:v for k,v in s.items() if k not in ('cells','cases')},ensure_ascii=False));return 0
 with (ART/'runner.lock').open('a+') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('이미 실행 중입니다. 상태 HTML을 확인하세요.');return 3
  if (ART/'run-completed.json').exists():print('기존 실행 결과를 보존합니다. 새 실험은 새 ADR에서 시작해야 합니다.');return 2
  for n,h in read(DES/'freeze-public.json')['files'].items():
   if sha(ROOT/n)!=h:raise RuntimeError('Frozen runner/config changed: '+n)
  plan=read(DES/'criteria.json')['plan'];panel=ProgressPanel('R4 통합테스트',str(ART),run_id='ADR1370/run-001')
  screen=[(c,p) for p in plan['providers'] for c in plan['screen']];panel.start_phase('제공자 비교',total=len(screen))
  selected=None
  try:
   for i,(c,p) in enumerate(screen):execute_cell(c,p,panel,i,len(screen));panel.update(done=i+1)
   obs=observed();choices=[]
   for p in plan['providers']:
    rows=[x for x in obs if x['provider']==p and x['case_id'] in plan['screen']]
    if eligible(rows):choices.append((sum(x['seconds'] for x in rows),p))
   if choices:
    selected=min(choices)[1];put(ART/'provider-selection.json',{'selected':selected,'eligible':choices,'selection_basis':'Two explanations + source/ACL/wire/budget checks; semantic correctness not certified'})
   if selected and not args.screen_only:
    cases=[c['id'] for c in read(DES/'live-cases.json') if c['execution']=='PUBLIC_API'];panel.start_phase('공개 질문 전체 확인',total=len(cases))
    for i,c in enumerate(cases):execute_cell(c,selected,panel,i,len(cases));panel.update(done=i+1)
   state='SCREEN_COMPLETE' if args.screen_only else 'RUN_COMPLETE_NOT_ALL_PASSED'
   result=report(state,selected);put(ART/'run-completed.json',{'state':state,'selected':selected,'all_passed':False})
   panel.finish('FAILED',exit_code=2,message='실행 기록 완료 · 전체 통과 아님',error='미실행 항목과 답변 검토 결과를 상태표에서 확인하세요.');return 2
  except BaseException as exc:
   put(ART/'runner-stop.json',{'type':type(exc).__name__,'error':str(exc),'no_automatic_retry':True});report('STOPPED',selected)
   panel.finish('STOPPED',exit_code=130,message='중단 · 기존 결과 보존',error=str(exc));return 130
if __name__=='__main__':raise SystemExit(main())
