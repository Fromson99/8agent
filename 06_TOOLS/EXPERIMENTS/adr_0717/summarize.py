"""Read completed per-question audits, with assessment excluded from main metrics."""
from pathlib import Path
from collections import Counter
import argparse,csv,gzip,hashlib,json,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile';D=A/'artifacts/design';O=A/'artifacts/run-001';ARM='measured-main50'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8') as f:f.write(canon(v)+'\n')
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def percentile(xs,q):
 if not xs:return None
 ys=sorted(xs);i=(len(ys)-1)*q;j=int(i);return ys[j]+(ys[min(j+1,len(ys)-1)]-ys[j])*(i-j)
p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');args=p.parse_args()
dataset=read(D/'dataset.json');qs={c['case_id']:c['question'] for c in dataset['cases']};rows=[read(p) for p in sorted(O.glob('*/diagnostic.json'))];n=len(rows)
for x in rows:
 output=read(O/x['case_id']/'result.json').get('output',{});answer=output.get('answer',{})
 has_final_answer=x['http_status']==200 and isinstance(answer,dict) and bool(answer.get('text','').strip())
 op=A/'artifacts/observations'/(x['case_id']+'.json')
 if args.final:assert op.exists(),'Actual model dispositions required for final drafting-time accounting'
 ocalls=read(op)['calls'] if op.exists() else []
 tail=ocalls[x['before_terminal_assessment_calls']:]
 decisions=[c['decision'].get('disposition') for c in tail if isinstance(c.get('decision'),dict)]
 last_disposition=decisions[-1] if decisions else None
 is_drafting=last_disposition in ('ANSWER','LIMITED_ANSWER') or has_final_answer
 x['terminal_group_disposition']=last_disposition
 x['terminal_group_is_answer_drafting']=is_drafting
 x['final_answer_excluded_calls']=x['before_terminal_assessment_calls'] if is_drafting else x['all_model_calls']
 x['final_answer_excluded_seconds']=x['before_terminal_assessment_seconds'] if is_drafting else x['all_model_seconds']
 x['returned_final_answer']=has_final_answer
if args.final:assert n==51 and {x['case_id'] for x in rows}==set(qs),'All51 audited outcomes are required'
def stats(rs,prefix='investigation'):
 vals=[x[prefix+'_seconds'] for x in rs];cs=[x[prefix+'_calls'] for x in rs]
 return {'cases':len(rs),'calls_total':sum(cs),'calls_mean':statistics.mean(cs) if cs else None,'calls_distribution':dict(sorted(Counter(cs).items())),'seconds_total':sum(vals),'seconds_mean':statistics.mean(vals) if vals else None,'seconds_median':statistics.median(vals) if vals else None,'seconds_p95':percentile(vals,.95),'seconds_max':max(vals) if vals else None}
summary={'completed':n,'planned':51,'status':'complete' if n==51 else 'running','primary_definition':'All physical attempts excluding memory-assess and its repairs; local/cache processing excluded. Reopened navigation remains included.','main':stats(rows),'http_200':stats([x for x in rows if x['http_status']==200]),'http_statuses':dict(Counter(x['http_status'] for x in rows)),'all_model_calls':sum(x['all_model_calls'] for x in rows),'assessment_calls':sum(x['assessment_calls'] for x in rows),'assessment_seconds':sum(x['assessment_seconds'] for x in rows),'repair_calls':sum(x['repair_calls'] for x in rows),'reentry_cases':[x['case_id'] for x in rows if x['assessment_reentries']],'research_cases':[x['case_id'] for x in rows if x['research']],'return_cases':[x['case_id'] for x in rows if x['returns']],'multiple_original_cases':[x['case_id'] for x in rows if len(x['presented_ids'])>1],'multiple_read_cases':[x['case_id'] for x in rows if x['read_choices']>1],'outliers':[x['case_id'] for x in rows if x['investigation_calls']>=6 or x['investigation_seconds']>=60 or x['read_choices']>=2 or len(x['presented_ids'])>=2 or x['research'] or x['returns'] or x['assessment_reentries']],'top_calls':[{'case_id':x['case_id'],'question':qs[x['case_id']],'calls':x['investigation_calls'],'seconds':x['investigation_seconds']} for x in sorted(rows,key=lambda x:(-x['investigation_calls'],-x['investigation_seconds']))[:10]],'top_time':[{'case_id':x['case_id'],'calls':x['investigation_calls'],'seconds':x['investigation_seconds']} for x in sorted(rows,key=lambda x:-x['investigation_seconds'])[:10]],'quality':'No independent semantic correctness score; HTTP200 and exact citation checks are not legal correctness','main_wiring':'unchanged','GENOS_execution':False}
summary['before_terminal_assessment']=stats(rows,'before_terminal_assessment')
summary['final_answer_excluded']=stats(rows,'final_answer_excluded')
summary['final_answer_excluded_definition']='Exclude the last contiguous answer-drafting/repair group when its last parsed disposition is ANSWER or LIMITED_ANSWER (including rejected drafts), or an answer was returned. A final NEEDS_INVESTIGATION assessment is intermediate reasoning and remains included even if reentry failed before another model call. Unknown failed stages remain included conservatively. Frozen primary and pre-terminal metrics remain unchanged; all attempts and durations are separately retained.'
summary['final_answer_excluded_top_calls']=[{'case_id':x['case_id'],'question':qs[x['case_id']],'calls':x['final_answer_excluded_calls'],'seconds':x['final_answer_excluded_seconds'],'http_status':x['http_status']} for x in sorted(rows,key=lambda x:(-x['final_answer_excluded_calls'],-x['final_answer_excluded_seconds']))[:10]]
summary['before_terminal_assessment_definition']='Exclude only the final contiguous memory-assess group (including its repairs); retain all earlier assessments and reopened investigation. Predeclared secondary metric, best matched to excluding only final answer.'
summary['before_terminal_top_calls']=[{'case_id':x['case_id'],'question':qs[x['case_id']],'calls':x['before_terminal_assessment_calls'],'seconds':x['before_terminal_assessment_seconds']} for x in sorted(rows,key=lambda x:(-x['before_terminal_assessment_calls'],-x['before_terminal_assessment_seconds']))[:10]]
put(O/'summary.json',summary)
columns=['case_id','question','http_status','final_answer_excluded_calls','final_answer_excluded_seconds','before_terminal_assessment_calls','before_terminal_assessment_seconds','investigation_calls','investigation_seconds','assessment_calls','assessment_seconds','all_model_calls','all_model_seconds','terminal_group_disposition','research','returns','read_choices','assessment_reentries','repair_calls','presented_originals','gold_presented','gold_total']
with (O/'questions.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
 for x in rows:w.writerow({k:(qs[x['case_id']] if k=='question' else len(x['presented_ids']) if k=='presented_originals' else x[k]) for k in columns})
table='| 질문 | 최종 답변 제외 호출 | 최종 답변 제외 LLM 시간 | 순수 탐색 호출/시간 | 원문 수 | 재검색/복귀 | 판단 후 재조사 | 응답 |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
for x in rows:table+=f"| [{x['case_id']}]({x['case_id']}/answer.txt) {qs[x['case_id']].replace(chr(10),' ')} | {x['final_answer_excluded_calls']} | {x['final_answer_excluded_seconds']:.1f}초 | {x['investigation_calls']}회 / {x['investigation_seconds']:.1f}초 | {len(x['presented_ids'])} | {x['research']}/{x['returns']} | {x['assessment_reentries']} | {x['http_status']} |\n"
(O/'questions.md').write_text('# CM51 질문별 탐색 기록\n\n'+f'{n}/51건 확인. 「최종 답변 제외」는 마지막 답변 작성·수정 묶음을 제외하고 중간 판단과 재조사를 포함한다. 최종 작성이 검증에 실패해도 같은 기준으로 제외한다. 단, 마지막 판단이 NEEDS_INVESTIGATION이면 답변 작성이 아니므로 포함한다. 「순수 탐색」은 모든 memory-assess 구간을 별도로 분리한 사전 주 지표다. 코드/캐시 시간은 제외한다.\n\n'+table+'\n전체 호출·개별 시간·행동 체인은 각 질문 diagnostic.json, 실제 답변은 answer.txt에 있다. 마지막 호출의 실제 역할에 따라 답변 작성과 재조사 판단을 구분한 파생 집계이며, 사전 지표를 수정하거나 모델을 재호출하지 않았다.\n')
if args.final:
 m=read(A/'실험/manifest.json');caseledgers=[]
 request_rows=[read(O/c['case_id']/'result.json') for c in dataset['cases']]
 process_ids=sorted({r['process_id'] for r in request_rows})
 sequence=[];active=None;serial=True;rss_samples=[];available_samples=[]
 for line in (A/'artifacts/worker.log').read_text().splitlines():
  if line.startswith('CASE_START '):
   parts=line.split();serial=serial and active is None;active=parts[1];sequence.append(active);available_samples.append(int(parts[-1]))
  elif line.startswith('CASE_FINISHED '):
   parts=line.split();serial=serial and active==parts[1];active=None;rss_samples.append(int(parts[-2]))
 serial=serial and active is None and sequence==[c['case_id'] for c in dataset['cases']]
 put(O/'sequential-execution.json',{'process_ids':process_ids,'ordered_nonoverlapping_cases':serial,'sequence':sequence,'rss_after_case_max_kib':max(rss_samples),'available_before_case_min_mib':min(available_samples),'measurement_limit':'Case-boundary samples, not a measured peak inside each request'})
 for c in dataset['cases']:
  with gzip.open(O/c['case_id']/'ledger-case.json.gz','rt',encoding='utf-8') as f:caseledgers.append(json.load(f))
 ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':ARM,'declared_stage_ids':['catalogue','acquired','presented'],'cases':caseledgers,'aggregate':{'cases':51,'presented_total':sum(len(x['presented_ids']) for x in rows),'gold_total':sum(x['gold_total'] for x in rows)}}]}],'audit':{'historical_reference_targets_not_current_law_certification':True,'adoption_reported_separately':True,'one_active_request_at_a_time':True}}
 ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
 frozen=read(D/'freeze.json');base=read(D/'baseline.json');checks={'all51_audited':n==51,'frozen_files_unchanged':all(sha(R/n)==h for n,h in frozen['files'].items()),'MAIN_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'],'no_failed_integrity_checks':all(all(v is not False for v in x['checks'].values()) for x in rows),'one_worker':read(D/'criteria.json')['execution']['workers']==1,'authorized_exact_questions':read(A/'artifacts/question-export-authorization.json')['dataset_sha256']==sha(D/'dataset.json'),'archives_verified':all(read(O/x['case_id']/'raw-archive.json')['verified'] for x in rows)}
 checks['actual_single_process']=len(process_ids)==1
 checks['actual_nonoverlapping_numeric_sequence']=serial
 result={**summary,'checks':checks,'diagnostic_success':all(checks.values()),'cases':rows};put(O/'result.json',result)
 m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={ARM:{'status':'complete','cases':51,'http_statuses':summary['http_statuses'],'accuracy':None,'accuracy_not_measured':'No independent semantic judge','investigation':summary['main'],'all_model_calls':summary['all_model_calls']}},comparisons=[],judge_disagreements=None,usage={ARM:{k:sum(x['usage'][k] for x in rows) for k in ('input_tokens','output_tokens','cost_usd')}},latency={ARM:summary['main']},error_taxonomy=[{'type':'other','case_id':x['case_id'],'detail':'HTTP'+str(x['http_status'])+'; see preserved original failure and diagnostic'} for x in rows if x['http_status']!=200])
 ra=m['retrieval_accounting'];ra['corpus_total']=max(c['stages'][0]['after_count'] for c in caseledgers)
 # The canonical retrieval ledger uses a nearest-rank index; time p95 above
 # remains explicitly interpolated and is a different metric.
 counts=[c['stages'][-1]['after_count'] for c in caseledgers]
 for key,val in [('before_filter',sum(c['stages'][0]['after_count'] for c in caseledgers)),('after_filter',sum(c['stages'][1]['after_count'] for c in caseledgers)),('presented_total',sum(counts)),('presented_mean',statistics.mean(counts)),('presented_p50',statistics.median(counts)),('presented_p95',sorted(counts)[round((len(counts)-1)*.95)]),('golden_recall',sum(c['stages'][-1]['gold_after'] for c in caseledgers)/sum(c['gold_total'] for c in caseledgers)),('selectivity',statistics.mean(counts)/ra['corpus_total'])]:ra[key]={ARM:val}
 ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({k:summary[k] for k in ('completed','main','http_statuses','multiple_original_cases','reentry_cases','top_calls')},ensure_ascii=False,indent=2))
