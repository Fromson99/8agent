"""Post-execution accounting/reporting only; never changes candidate or outputs."""
from pathlib import Path
import json,hashlib,sqlite3,statistics,ast
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0645-shortcut-deterministic-procedure';D=A/'artifacts/design';RUN=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def main():
 m=read(A/'실험/manifest.json');cases=read(D/'inputs.json');gold=read(D/'gold.json');b=read(D/'bindings.json');scores=read(RUN/'offline-judge/scores.json');judge=read(RUN/'offline-judge/summary.json');exceptions=read(RUN/'procedure-exceptions/result.json')
 rows=[r for c in cases for arm in ('baseline','procedure') for r in read(RUN/c['case_id']/arm/'result.json')]
 groups={mode:[r for r in rows if r['temperature']==mode] for mode in ('parent','cold','warm')}
 summary={}
 for mode,rs in groups.items():
  ss=[s for s in scores if s['temperature']==mode]
  summary[mode]={'correct':sum(s['correct'] for s in ss),'total':len(rs),'completed':sum(r['http_status']==200 for r in rs),'calls':sum(r['provider_calls'] for r in rs),'calls_by_case':{r['case_id']:r['provider_calls'] for r in rs},'median_seconds':statistics.median(r['seconds'] for r in rs),'p95_seconds':max(r['seconds'] for r in rs),'cost_usd':sum(u.get('cost_usd') or 0 for r in rs for u in r['usage']),'input_tokens':sum(u.get('input_tokens') or 0 for r in rs for u in r['usage']),'output_tokens':sum(u.get('output_tokens') or 0 for r in rs for u in r['usage'])}
 phases={};tool_receipts={}
 for c in cases:
  cid=c['case_id']
  for arm in ('baseline','procedure'):
   folder=RUN/cid/arm
   allcalls=[]
   for p in sorted((folder/'provider').glob('call-*/request.json')):
    raw=read(p);v=json.loads(raw['messages'][1]['content'])['view'];allcalls.append(v.get('source_stage',v['phase']))
   rs=read(folder/'result.json');offset=0
   for row in rs:
    phases[cid+'/'+row['temperature']]=allcalls[offset:offset+row['provider_calls']];offset+=row['provider_calls']
  dbpath=next((RUN/cid/'procedure/runtime').rglob('cases-v4.sqlite'))
  with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
   steps=[json.loads(r[0]) for r in db.execute('SELECT payload FROM sw_procedure_event ORDER BY id')]
   tool_receipts[cid]={'events':steps,'steps':db.execute('SELECT count(*) FROM sw_procedure_step').fetchone()[0],'activated':db.execute('SELECT count(*) FROM sw_procedure_activation').fetchone()[0]}
 put(RUN/'procedure-trace.json',{'phases':phases,'tool_receipts':tool_receipts})
 # Exact source identities are derived only now, after product choices are final.
 units={};coords={}
 with sqlite3.connect('file:'+str(R/b['generation']/'store.sqlite')+'?mode=ro',uri=True) as db:
  for doc,uid,parent,raw in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit'):
   v=json.loads(raw);units[(doc,str(uid))]=(None if parent is None else str(parent),v)
   if doc in b['scope'] and v.get('family')=='kr_article':coords[doc+'|'+str(uid)]={'doc_id':doc,'node':int(uid)}
 def root(doc,uid):
  while uid is not None:
   parent,v=units[(doc,str(uid))]
   if v.get('family')=='kr_article':return doc+'|'+str(uid)
   uid=parent
  return None
 def objects(s):return sorted((coords[k] for k in s),key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
 def sets_for(cid,arm,mode):
  row=next(r for r in rows if r['case_id']==cid and r['temperature']==mode);runid=row['output'].get('run_id');got={'read':set(),'present':set()}
  paths=list((RUN/cid/arm/'runtime').rglob('journal.sqlite'))
  for p in paths:
   if runid and p.parent.name!=runid:continue
   if not runid and len(paths)>1:continue
   with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
    for doc,uid in db.execute('SELECT document_id,unit_id FROM evidence_unit'):
     key=root(doc,uid)
     if key in coords:got['read'].add(key)
    for doc,uid in db.execute("SELECT DISTINCT e.document_id,e.unit_id FROM evidence_unit e JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"):
     key=root(doc,uid)
     if key in coords:got['present'].add(key)
  return got
 def caseledger(cid,arm,mode):
  case=next((c for c in cases if c['case_id']==cid),None)
  sets={'source':{k for k,v in coords.items() if case and v['doc_id']==case['document_id']},'read':set(),'present':set()}
  if case:sets.update(sets_for(cid,arm,mode))
  g={root(x['document_id'],x['unit_id']) for x in gold[cid]['originals']} if case else set()
  prev=set();stages=[]
  for stage in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
   now=sets[stage['stage_id']];add=now-prev;drop=prev-now;reason='not_in_recorded_'+stage['stage_id']
   stages.append({**stage,'executed':bool(case),'skip_reason':None if case else 'Separate synthetic procedure decision contract; no public corpus retrieval.','before':objects(prev),'added':objects(add),'discarded':objects(drop),'after':objects(now),'before_count':len(prev),'added_count':len(add),'discarded_count':len(drop),'after_count':len(now),'occurrence_counts':{'before':len(prev),'after':len(now),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in objects(drop)],'discard_reason_counts':{reason:len(drop)} if drop else {},'gold_total':len(g),'gold_before':len(prev&g),'gold_added':len(add&g),'gold_discarded':len(drop&g),'gold_after':len(now&g),'golden_recall':len(now&g)/len(g) if g else None,'gold_before_identities':objects(prev&g),'gold_added_identities':objects(add&g),'gold_after_identities':objects(now&g),'discarded_gold':[{'identity':x,'reason':reason} for x in objects(drop&g)]});prev=now
  return {'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(g),'gold_identities':objects(g),'stages':stages}
 metrics={};ledgerarms=[]
 for arm,mode in [('baseline','parent'),('procedure','warm')]:
  records=[caseledger(q['case_id'],arm,mode) for q in m['questions']]
  counts=[x['stages'][-1]['after_count'] for x in records];goldtotal=sum(x['gold_total'] for x in records)
  met={'before_filter':sum(x['stages'][0]['after_count'] for x in records),'after_filter':sum(x['stages'][1]['after_count'] for x in records),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':sum(x['stages'][-1]['gold_after'] for x in records)/goldtotal,'selectivity':statistics.mean(counts)/len(coords)}
  metrics[arm]=met;ledgerarms.append({'arm_id':arm,'declared_stage_ids':['source','read','present'],'cases':records,'aggregate':met})
  for record in records:put(RUN/record['case_id']/arm/'retrieval-stage-ledger.json',record)
 cold=[caseledger(c['case_id'],'procedure','cold') for c in cases];put(RUN/'cold-learning-retrieval.json',cold)
 ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':ledgerarms}],'audit':{'primary_comparison':'parent fresh vs candidate warm; candidate cold learning is separate cold-learning-retrieval.json','synthetic_case':'No source retrieval; marked skipped and excluded from quality denominator. Zero contributes to machine aggregate means only.','present_scope':'Successfully delivered model views, exact journal records. Full detailed search decisions in native journals and procedure-trace.json.'}}
 ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(RUN/'retrieval-stage-ledger.json',ledger)
 checks={'contracts':True,'warm_answers':summary['warm']['correct']==3,'cold_answers':summary['cold']['correct']==3,'warm_calls':all(r['provider_calls']<=2 for r in groups['warm']),'warm_procedural_calls_zero':all(all(p in ('memory-assess','memory-compose') for p in phases[r['case_id']+'/warm']) for r in groups['warm']),'latency':summary['warm']['median_seconds']<summary['parent']['median_seconds'],'exception_model_calls':[r['model_calls'] for r in exceptions['rows']]==[1,0,1,1,1],'exception_choices':[r['result']['selected'] for r in exceptions['rows']]==['R1','R1','R2','R1','R2'],'usage_complete':all(r['provider_calls']==len(r['usage']) for r in rows)}
 paired={key:0 for key in ('both_correct','candidate_only','baseline_only','both_wrong')}
 for c in cases:
  p=next(s for s in scores if s['case_id']==c['case_id'] and s['temperature']=='parent')['correct'];w=next(s for s in scores if s['case_id']==c['case_id'] and s['temperature']=='warm')['correct'];paired['both_correct' if p and w else 'candidate_only' if w else 'baseline_only' if p else 'both_wrong']+=1
 result={'status':'complete','summary':summary,'checks':checks,'strict_success':all(checks.values()),'paired':paired,'scores':scores,'phases':phases,'contract_tests':80,'exceptions':exceptions,'retrieval':metrics,'in_sample':True,'decision_eligible':False,'main_unchanged':True,'genos_tested':False}
 put(RUN/'result.json',result)
 m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete',**summary['parent']},'procedure':{'status':'complete',**summary['warm'],'cold_learning':summary['cold']}},comparisons=[{'paired':paired,'checks':checks}],judge_disagreements=sum(s['disagreement'] for s in scores),usage={'by_temperature':summary,'evaluator_calls':judge['calls'],'evaluator_usage':judge['usage'],'exceptions_calls':exceptions['calls']},latency={k:{'p50':v['median_seconds'],'p95':v['p95_seconds']} for k,v in summary.items()},error_taxonomy=[{'type':'other','case_id':r['case_id'],'temperature':r['temperature'],'detail':r['output']} for r in rows if r['http_status']!=200])
 m['retrieval_accounting']['corpus_total']=len(coords)
 for key in metrics['baseline']:m['retrieval_accounting'][key]={arm:v[key] for arm,v in metrics.items()}
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-stage-ledger.json')
 headings={}
 for node in ast.parse((R/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
  if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('ADR_HEADINGS','QUESTION_HEADINGS_COMMON'):headings[node.targets[0].id]=ast.literal_eval(node.value)
 qh=headings['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
 for q in m['questions']:
  cid=q['case_id'];case=next((c for c in cases if c['case_id']==cid),None)
  def calls(paths):return '\n'.join('### '+str(p.relative_to(RUN))+'\n'+block(read(p)) for path in paths for p in sorted(path.glob('*.json')))
  paths=[p for arm in ('baseline','procedure') for p in (RUN/cid/arm/'provider').glob('call-*')] if case else list((RUN/cid/'provider').glob('call-*'))
  raw=calls(paths);grader=calls(list((RUN/'offline-judge/provider').glob('call-*'+cid+'-*')))
  vals=['ADR0645/run-001. External public or explicitly synthetic; exact provider payloads.',case['question'] if case else block(read(D/'exception-inputs.json')),block(gold[cid]) if case else 'Offline expected choices: R1,R1,R2,R1,R2. Never supplied as gold to product.',block([r['input'] for r in rows if r['case_id']==cid]) if case else 'Synthetic full menus in actual calls below.',block({arm:read(RUN/cid/arm/'retrieval-stage-ledger.json') for arm in ('baseline','procedure')}),raw,'All intermediate actual calls above. Saved decision reuse and exceptional reasons: '+block({k:v for k,v in phases.items() if k.startswith(cid+'/')}) if case else block(exceptions),grader or 'No model grader: closed synthetic choice + call-count assertions.',block([s for s in scores if s['case_id']==cid]) if case else block(exceptions['rows'])]
  path=A/'실험'/q['file'];path.write_text('# '+cid+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,vals))+'\n');q['sha256']=sha(path)
 put(A/'실험/manifest.json',m)
 front=(A/'README.md').read_text().split('---',2)[1]
 vals=['검증된 절차 재실행 후보를 구현하고 공개 3질문 및 합성 이탈 사례를 실측했다. MAIN은 유지한다.'+block({'summary':summary,'checks':checks}),
 '부모 v6는 고정된 단계 방법 선택에 매번7회 모델을 호출했다. 후보는 같은 단계와 감사 기록을 코드로 만들며, DB에 저장한 조사 명령·검색계획·근거/참조 선택을 현재 입력과 대조해 재실행한다. 원문 읽기·해시·권한 검증과 최종 법률 판단은 유지한다.',
 m['design']['success_criteria'],
 '모든 질문에서 부모 fresh1회, 후보 cold1회+새 세션 warm1회. 공개3질문은 이미 관찰한 회귀 사례이며 holdout이 아니다. 부모와 후보 순서를 질문별로 교대했다. cold는 학습 비용이며 warm과 분리한다. synthetic exceptions are not legal-answer accuracy examples.',
 block({'source':b['generation'],'source_hash':b['source_sha256'],'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'candidate':b['candidate']}),
 '계약·회귀·프로세스 복구 검사80개 통과. 실제 답변 평가는 동일한 고정 원문/루브릭으로2회씩 수행했다.'+block(summary),
 block({'paired':paired,'checks':checks,'scores':scores}),
 block({'summary':summary,'retrieval':metrics,'judge_calls':judge['calls'],'exception_calls':exceptions['calls']}),
 '절차 재사용과 법률 판단 재사용을 분리했다. 정상 재사용에서도 fulltext·참조 탐색·원문 읽기를 실행한다. 저장 결정의 complete menu/prompt/schema, 질문, 사용자·문서 범위와 source/config binding이 같을 때만 모델을 생략한다. 이탈 시 예상/실제 입력과 모델 선택을 append-only로 남긴다.',
 '보수적인 exact-input 재사용 prototype. 의미가 같은 다른 표현이나 새 매개변수로 절차를 일반화하지 않는다. 문서/설정 세대 전체가 달라도 재판단한다. successful operational execution is not legal approval. Public simple questions may not traverse a substantive 준용 chain; synthetic reference-menu change is separately tested. 최초 조사 비용·메뉴 순서 변화·독립 holdout·GENOS 성능은 추가 검증 대상이다.',
 '격리 후보만 변경했다. 활성 MAIN pointer, 운영 DB, Git main과 GENOS는 유지. 알려진3사례 probe로 운영 승격하지 않는다. 문제가 있으면 후보 runner 사용을 중단하면 된다; 운영 롤백 불필요.',
 '후보 해시 검증: .venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate '+b['candidate']+'\n검사: SHORTCUT_CANDIDATE_SNAPSHOT=revisions/rev-001/snapshot PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q 06_TOOLS/EXPERIMENTS/adr_0645\n실측 runner/grade/exceptions는 완료 출력 덮어쓰기를 거부한다. 새 재실행은 새 ADR에서 수행한다.']
 (A/'README.md').write_text('---'+front+'---\n\n# ADR-0645 조사 절차 직접 실행\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(headings['ADR_HEADINGS'],vals))+'\n')
 (A/'실험/README.md').write_text('# 질문별 실제 기록\n\n'+''.join('- ['+q['case_id']+']('+q['file']+')\n' for q in m['questions'])+'\n'+block(summary))
 print(json.dumps({'summary':summary,'checks':checks},ensure_ascii=False))
if __name__=='__main__':main()
