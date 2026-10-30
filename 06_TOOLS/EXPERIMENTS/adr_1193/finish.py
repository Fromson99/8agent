"""Read-only case audit aggregation; no product imports or model requests."""
from common import *
import sqlite3,statistics,math
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
f=read(DES/'freeze.json');C=ROOT/f['code_root'];m=read(ADR/'실험/manifest.json');cases=read(DES/'cases.json');refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')};baseline=read(DES/'baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['files'].items())
nav=sqlite3.connect((ROOT/baseline['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
for sid,raw in nav.execute('select id,json from source'):
 x=json.loads(raw);c=x.get('article_coordinate') or {};did=c.get('doc_id',x.get('document_id'));node=c.get('node',x.get('unit_id'))
 if did in scope and str(node).isdigit():source[sid]=(did,int(node));corpus.add(source[sid])
nav.close()
def coords(xs):return [{'doc_id':d,'node':n} for d,n in sorted(xs)]
graded=[];summaries=[];calls=[];presented=[];seen_counts=[];gold_hits=0;gold_total=0
for case in cases:
 cid=case['id'];P=ART/'live'/cid;ran=(P/'dispatch.json').exists();seen=set();reads=set();cites=set()
 if ran:
  r=read(P/'result.json');a=read(P/'audit.json');g=read(P/'gate.json');physical=read(P/'calls.json');calls+=physical
  reads={source[s] for s in a['read_source_ids'] if s in source};cites={source[s] for s in a['published_source_ids'] if s in source};seen=set(reads)
  for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
   v=read(p)['view']
   for x in v.get('read_candidates',[]):
    for n in reversed(x.get('path',[])):
     if n.get('level')=='조' and str(n.get('unit_id','')).isdigit() and x.get('document_id'):seen.add((x['document_id'],int(n['unit_id'])));break
   def walk(x):
    if isinstance(x,dict):
     if x.get('source_id') in source and x.get('text'):seen.add(source[x['source_id']])
     for y in x.values():walk(y)
    elif isinstance(x,list):
     for y in x:walk(y)
   walk(v)
  summaries.append({'case_id':cid,'executed':True,'calls':r['model_calls'],'seconds':r['seconds'],'http_status':r.get('http_status'),'status':r.get('status'),'gate':g,'outcome':a['accepted_outcome'],'source_checks':a['span_checks'],'delivered_checks':a['delivered_span_checks'],'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'budget_matches':a['physical_budget_matches'],'content_review':read(P/'content-review.json')})
 else:summaries.append({'case_id':cid,'executed':False,'reason':'CM007 did not pass all frozen gates; no automatic followup or repeat'})
 rec=StageLedgerRecorder(cid,'scoped',identity_canonicalizer)
 for sid,kind,parents,values,discard in [('delivered_or_read','source',[],seen,[]),('original_read','select',['delivered_or_read'],reads,seen-reads),('final_cited','present',['original_read'],cites,reads-cites)]:
  if ran:rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Observed candidate not acquired' if kind=='select' else 'Acquired source not cited in final claims'} for x in coords(discard)])
  else:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Prior case gate failed; not executed or legally scored')
 gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in refs[cid]['targets']];graded.append(grade_capture(rec.capture(),gold));gold_total+=len(gold);gold_hits+=len(cites & {(g['doc_id'],g['node']) for g in gold});presented.append(len(cites));seen_counts.append(len(seen))
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1193',m['experiment_id'],[build_run_artifact('run-001',graded,{'scoped':['delivered_or_read','original_read','final_cited']})]))
usage={'input_tokens':sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls),'output_tokens':sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls),'known_response_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls)}
usage.update(usage_complete=all(isinstance(x.get('usage'),dict) for x in calls),unknown_attempts=sum(x.get('status')!='responded' for x in calls),note='Only reported usage counted; unknown completion does not imply zero cost or remote cancellation.')
ran=[x for x in summaries if x['executed']];passed=all(x.get('executed') and x['gate']['passed'] for x in summaries)
result={'status':'complete','candidate_revision':f['candidate_revision'],'active_release_unchanged':'MAIN115/parasail-primary-20261029-r1','executed_candidate':'ADR1192 prompt scoped, same-code ADR1193','serving_files':len(f['files']),'cases':summaries,'physical_calls':len(calls),'usage':usage,'question_gate_passed':sum(x['gate']['passed'] for x in ran),'executed_cases':len(ran),'planned_cases':len(cases),'quality_certified':False,'legal_accuracy':None,'active_main_unchanged':True,'product_changes':False,'resource_items_1_to_3_changed':False,'main_promotion':False,'genos_deployed':False,'stronger_model_comparison':False,'new_model_calls_during_audit':0}
put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=passed)
m['results'].update(status='complete',by_arm={'scoped':{'status':'complete','live_gate_passed':passed,'cases':summaries,'quality_certified':False}},comparisons=[],judge_disagreements=[],usage={'physical_requests':len(calls),'offline_evaluator_requests':0,**usage},latency={'case_seconds':[x['seconds'] for x in ran],'p50_seconds':statistics.median(x['seconds'] for x in ran),'p95_seconds':None,'not_measured_reason':'At most two known cases; no stable p95 or improvement claim'},error_taxonomy=[x['content_review'].get('failure_type','none') for x in ran if not x['gate']['passed']])
def percentile(xs,p):return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)]
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=sum(seen_counts),after_filter=sum(presented),presented_total=sum(presented),presented_mean=statistics.mean(presented),presented_p50=statistics.median(presented),presented_p95=percentile(presented,.95),golden_recall=gold_hits/gold_total,selectivity=statistics.mean(presented)/len(corpus),not_applicable_reason='No product retrieval changes; observed original acquisition and final citations are recorded.',metric_scope_note='Planned set ledger includes executed=false cases; skipped cases are not legally scored. Observed candidates union acquired roots is not entire internal search candidate universe.');m['retrieval_accounting']['stage_ledger'].update(mode='measured',sha256=sha(RUN/'retrieval-ledger.json'))
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,row in zip(m['questions'],summaries):
 cid=q['case_id'];texts=[f'run-001 / scoped / {cid}; '+('실제 실행1회' if row['executed'] else '미실행'),refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용이며 제품 모델에 전달하지 않음. 저장 판본 기준; 현행 법률 정확도 인증이 아님.','[동결 요청](../artifacts/design/cases.json), [코드](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json). 관측 후보→원문 확보→최종 인용. 미실행은 executed=false.',f'[물리 호출](../artifacts/live/{cid}/calls.json), raw/call-*/request.json.gz,response.json.gz 및 canonical/*.json.gz에 전체 원시 입출력과 스키마 보존.' if row['executed'] else '새 제품 호출0.',f'[단계별 호출](../artifacts/live/{cid}/generations.json)' if row['executed'] else '새 중간 호출0.','평가 모델0. 사전 동결 기준으로 오프라인 원문·답변 대조. 같은 사례 반복0. 알려진 사례 probe.','```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```'];p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
print(json.dumps({'physical_calls':len(calls),'case_gates':[{k:x.get(k) for k in ('case_id','executed','status','calls')} for x in summaries],'usage':usage},ensure_ascii=False))
