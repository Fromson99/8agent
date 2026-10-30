"""Post-run read-only aggregation; saved answer review is not a new full case."""
from common import *
import sqlite3,statistics,math
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
f=read(DES/'freeze-live.json');b=read(DES/'baseline.json');m=read(ADR/'실험/manifest.json');C=ROOT/f['code_root']
checks={label:all(sha(base/n)==h for n,h in rows.items()) for label,base,rows in [('candidate',C,f['files']),('scripts',ROOT,f['scripts']),('inputs',ROOT,f['inputs']),('working_product',ROOT,b['working_files']),('selected_service',ROOT/b['release']['code_root'],b['release']['files'])]}
checks['active_pointer']=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'];assert all(checks.values()),checks
parent=read(ROOT/b['parent']['manifest_path']);rev=next(x for x in parent['revisions'] if x['revision_id']==b['parent']['revision_id']);parent_files={x['frozen_path'].split('/snapshot/',1)[1]:x['snapshot_sha256'] for x in rev['files']}
delta=[n for n,h in f['files'].items() if parent_files.get(n)!=h]
put(ART/'post-run-integrity.json',{'checks':checks,'candidate_files':len(f['files']),'working_files_checked':len(b['working_files']),'selected_files_checked':len(b['release']['files']),'parent_changed_or_added':delta,'parent_removed':sorted(set(parent_files)-set(f['files'])),'post_dispatch_scripts':['audit_failure.py','audit_saved_review.py','aggregate_final.py','final_report.py'],'new_model_calls_during_audit':0})
P=ART/'live/cm-009';S=ART/'saved-cm007-review';r9=read(P/'result.json');a9=read(P/'audit.json');d9=read(P/'diagnosis.json');g9=read(P/'gate.json');failure=read(P/'failure-analysis.json');r7=read(S/'result.json');review=read(S/'content-audit.json');inp=read(S/'input.json.gz');calls=read(P/'calls.json')
nav=sqlite3.connect((ROOT/b['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
for sid,raw in nav.execute('select id,json from source'):
 x=json.loads(raw);c=x.get('article_coordinate') or {};did=c.get('doc_id',x.get('document_id'));node=c.get('node',x.get('unit_id'))
 if did in scope and str(node).isdigit():source[sid]=(did,int(node));corpus.add(source[sid])
nav.close()
def coords(xs):return [{'doc_id':d,'node':n} for d,n in sorted(xs)]
refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')};graded=[];counts=[];goldhits=0;goldtotal=0
for cid in ('cm-007','cm-009'):
 if cid=='cm-007':
  reads={source[x['source_id']] for x in inp['sources']};seen=set(reads)
  old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts/live/cm-007/audit.json')
  cites={source[s] for s in old['published_source_ids'] if s in source};assert cites<=reads
 else:
  reads={source[s] for s in a9['read_source_ids'] if s in source};cites=set();seen=set(reads)
  def walk(x):
   if isinstance(x,dict):
    if x.get('source_id') in source and x.get('text'):seen.add(source[x['source_id']])
    for y in x.values():walk(y)
   elif isinstance(x,list):
    for y in x:walk(y)
  for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
   v=read(p)['view'];walk(v)
   for x in v.get('read_candidates',[]):
    for n in reversed(x.get('path',[])):
     if n.get('level')=='조' and str(n.get('unit_id','')).isdigit() and x.get('document_id'):seen.add((x['document_id'],int(n['unit_id'])));break
 rec=StageLedgerRecorder(cid,'reviewed',identity_canonicalizer)
 for sid,kind,parents,values,discard in [('delivered_or_read','source',[],seen,set()),('original_read','select',['delivered_or_read'],reads,seen-reads),('final_cited','present',['original_read'],cites,reads-cites)]:
  reason='Observed source not acquired' if kind=='select' else ('Selected review source not cited in unchanged saved answer' if cid=='cm-007' else 'No accepted final answer: ASSESS contract failed')
  rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':reason} for x in coords(discard)])
 gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in refs[cid]['targets']];graded.append(grade_capture(rec.capture(),gold));goldtotal+=len(gold);goldhits+=len(cites & {(x['doc_id'],x['node']) for x in gold})
 counts.append({'case_id':cid,'scope':'saved answer inputs and original citations, no new retrieval' if cid=='cm-007' else 'new native request observed stages','observed':len(seen),'read':len(reads),'cited':len(cites)})
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1201',m['experiment_id'],[build_run_artifact('run-001',graded,{'reviewed':['delivered_or_read','original_read','final_cited']})]))
allusage=[x.get('usage') for x in calls]+[x.get('usage') for x in r7['usage']]
usage={'physical_requests':len(calls)+r7['physical_calls'],'reported_input_tokens':sum((x or {}).get('prompt_tokens',0) for x in allusage),'reported_output_tokens':sum((x or {}).get('completion_tokens',0) for x in allusage),'known_response_cost_usd':sum((x or {}).get('cost',0) for x in allusage),'usage_complete':all(isinstance(x,dict) for x in allusage),'unreported_usage_attempts':sum(x is None for x in allusage),'unknown_attempts':sum(x.get('status')!='responded' for x in calls),'note':'One confirmed429 has no reported usage; absent cost is not certified zero. Saved007 reviewer is a product call, not offline judge.'}
rows=[{'case_id':'cm-007','execution_kind':'new_review_of_saved1200','new_full_case_run':False,'executed':True,'status':r7['status'],'seconds':r7['seconds'],'physical_calls':r7['physical_calls'],'full_case_grade':'unchanged prior failure','reviewer_probe_passed':False,'content_review':review}, {'case_id':'cm-009','execution_kind':'new_native_full_case','new_full_case_run':True,'executed':True,'status':'FAILED','http_status':r9['http_status'],'seconds':r9['seconds'],'physical_calls':r9['model_calls'],'tools':sum(x['tool_used'] for x in d9['runs']),'model_transport_seconds':d9['model_transport_seconds'],'full_case_passed':False,'source_checks':a9['span_checks'],'delivered_checks':a9['delivered_span_checks'],'source_mismatches':a9['source_mismatches'],'acl_violations':a9['acl_violations'],'physical_budget_matches':a9['physical_budget_matches'],'reviewer_calls':failure['reviewer_calls'],'failure_analysis':failure,'gate':g9}]
r={'status':'complete','candidate_revision':f['candidate_revision'],'executed_candidate':'ADR1201 rev002 isolated native API; selected MAIN117 data/transport','serving_files':len(f['files']),'cases':rows,'physical_calls':usage['physical_requests'],'usage':usage,'new_full_cases':1,'new_saved_answer_reviews':1,'full_case_passed':0,'reviewer_probe_passed':False,'technical_tests_passed':28,'quality_certified':False,'legal_accuracy':None,'main117_unchanged':True,'working_product_unchanged':True,'main_promotion':False,'genos_deployed':False,'new_model_calls_during_audit':0,'retrieval_counts':counts,'metric_caveat':'Saved007 ledger records reused inputs/citations, not fresh retrieval. CM009 no_material_gap gate is vacuous without accepted assessment and is not a semantic pass.'}
put(RUN/'result.json',r)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'reviewed':{'status':'complete','live_gate_passed':False,'reviewer_probe_passed':False,'cases':rows,'quality_certified':False}},comparisons=[],judge_disagreements=[{'case_id':'cm-007','model_findings':2,'observed_false_positives':2,'known_defects_missed':2,'method':'saved source/answer comparison, no evaluation model'}],usage={**usage,'offline_evaluator_requests':0},latency={'saved_review_seconds':r7['seconds'],'new_live_case_seconds':r9['seconds'],'p50_seconds':None,'p95_seconds':None,'not_measured_reason':'One saved review and one full case are different workloads; no pooled latency percentile.'},error_taxonomy=['REVIEW_SOURCE_STATUS_CONFLICT','REVIEW_KNOWN_DEFECT_MISSED','REVIEW_FALSE_POSITIVE','REQUIREMENT_GAP_COVERAGE'])
presented=[x['cited'] for x in counts];m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=sum(x['observed'] for x in counts),after_filter=sum(presented),presented_total=sum(presented),presented_mean=statistics.mean(presented),presented_p50=statistics.median(presented),presented_p95=max(presented),golden_recall=goldhits/goldtotal,selectivity=statistics.mean(presented)/len(corpus),not_applicable_reason='Retrieval unchanged. Mixed ledger is inventory only, not a measured retrieval improvement.',metric_scope_note=r['metric_caveat']);m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,row in zip(m['questions'],rows):
 cid=q['case_id'];folder='saved-cm007-review' if cid=='cm-007' else 'live/cm-009'
 texts=[f"run-001 / reviewed / {cid} / {row['execution_kind']}; 1회",refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용. 제품·검토AI 입력에 전달하지 않았다. 현행법 인증이 아니다.','[동결](../artifacts/design/freeze-live.json), [질문](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json).007은 저장 답변의 원문·인용을 재사용한 목록이며 새 검색이 아니다.009는 실제 관측 후보→확보→최종 인용으로 최종 답변 부재를 보존한다.',f'../artifacts/{folder}/raw/의 request/response/output JSON 및 gzip에 실제 원문·스키마·응답을 보존했다. [결과](../artifacts/{folder}/result.json).','007: 새 검토AI1회, 전체 질문 재실행0.009: 물리13(4291/정상12), ASSESS2회(보완1), 새 검토AI0.','평가 모델0. 저장 원문과 실제 응답을 오프라인 대조했다. 같은 사례 자동 반복0.','```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```']
 p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
print(json.dumps({'usage':usage,'integrity':checks,'changed_files':len(delta),'retrieval_counts':counts},ensure_ascii=False))
