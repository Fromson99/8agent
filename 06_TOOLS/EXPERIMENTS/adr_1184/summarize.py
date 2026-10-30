"""Post-run read-only audits and report registration; never executes a model."""
from common import *
import sys,sqlite3,gzip,statistics,math
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
f=read(DES/'freeze.json');C=ROOT/f['code_root'];m=read(ADR/'실험/manifest.json');cases=read(DES/'cases.json');refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')};baseline=read(DES/'baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'];assert all(sha(C/n)==h for n,h in f['files'].items())
check=read(ART/('check-'+f.get('execution_id',f['candidate_revision']['revision_id'])+'.json'));reg=read(ART/'regression-comparison.json');assert check['failed']==0 and not reg['new_regressions']
# The capture is gold-free until the read-only grading pass below.
data=ROOT/baseline['release']['data_path'];nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
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
   v=json.load(gzip.open(p,'rt'))['view']
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
  summaries.append({'case_id':cid,'executed':True,'calls':r['model_calls'],'seconds':r['seconds'],'http_status':r.get('http_status'),'status':r.get('status'),'gate':g,'outcome':a['accepted_outcome'],'source_checks':a['span_checks'],'delivered_checks':a['delivered_span_checks'],'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'budget_matches':a['physical_budget_matches']})
 else:summaries.append({'case_id':cid,'executed':False,'reason':'Previous live gate did not pass; no automatic followup or repeat'})
 rec=StageLedgerRecorder(cid,'bounded',identity_canonicalizer)
 for sid,kind,parents,values,discard in [('delivered_or_read','source',[],seen,[]),('original_read','select',['delivered_or_read'],reads,seen-reads),('final_cited','present',['original_read'],cites,reads-cites)]:
  if ran:rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Observed candidate not acquired' if kind=='select' else 'Acquired source not cited in final claims'} for x in coords(discard)])
  else:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Prior live gate failed; this case not executed or legally scored')
 gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in refs[cid]['targets']];graded.append(grade_capture(rec.capture(),gold));gold_total+=len(gold);gold_hits+=len(cites & {(g['doc_id'],g['node']) for g in gold});presented.append(len(cites));seen_counts.append(len(seen))
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1184',m['experiment_id'],[build_run_artifact('run-001',graded,{'bounded':['delivered_or_read','original_read','final_cited']})]))
usage={'input_tokens':sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls),'output_tokens':sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls),'known_response_cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls)}
unknown=sum(x.get('status')!='responded' for x in calls)
usage.update(usage_complete=all(isinstance(x.get('usage'),dict) for x in calls),unknown_attempts=unknown,note='Only provider-reported usage is totaled; local cancellation does not prove remote cancellation or zero cost.')
result={'status':'complete','candidate_revision':f['candidate_revision'],'candidate_files':len(f['files']),'technical_checks':check['passed'],'regression':reg,'cases':summaries,'physical_calls':len(calls),'usage':usage,'unknown_provider_attempts':unknown,'quality_certified':False,'legal_accuracy':None,'active_main':'MAIN112','active_main_unchanged':True,'production_integration':False,'main_promotion':False,'genos_deployed':False,'stronger_model_comparison':False,'failed_revisions_preserved':['rev001304pass/2result-artifact fixture errors: execution_id missing; originals preserved; finalrev002 includes preparation deadline and fresh full run']}

put(RUN/'result.json',result)
passed=all(x.get('executed') and x['gate']['passed'] for x in summaries)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=passed)
m['results'].update(status='complete',by_arm={'bounded':{'status':'complete','technical_success':True,'live_gate_passed':passed,'cases':summaries,'quality_certified':False}},comparisons=[],judge_disagreements=[],usage={'physical_requests':len(calls),'offline_evaluator_requests':0,**usage},latency={'case_seconds':[x['seconds'] for x in summaries if x['executed']],'improvement_certified':False},error_taxonomy=['Prior call003 upstream cause unknown; local idle timeout was not an absolute deadline','rev001 two result-record fixture failures preserved; final full check corrects binding','See per-case completion gates and content reviews for actual failures'])

def percentile(xs,p):
 xs=sorted(xs);return xs[max(0,math.ceil(len(xs)*p)-1)]
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=sum(seen_counts),after_filter=sum(presented),presented_total=sum(presented),presented_mean=statistics.mean(presented),presented_p50=percentile(presented,.5),presented_p95=percentile(presented,.95),golden_recall=gold_hits/gold_total,selectivity=statistics.mean(presented)/len(corpus),not_applicable_reason=None,metric_scope_note='Planned-set stage ledger includes executed=false cases. Coverage is not legal correctness; skipped cases are not scored as incorrect answers.');m['retrieval_accounting']['stage_ledger'].update(mode='measured',sha256=sha(RUN/'retrieval-ledger.json'))
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,row in zip(m['questions'],summaries):
 cid=q['case_id'];texts=[f'run-001 / bounded / {cid}; '+('실제 실행1회' if row['executed'] else '미실행'),refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용, 제품에 전달하지 않음. 법률 정답률 미인증.','[동결 요청](../artifacts/design/cases.json), [코드](../artifacts/design/execution-binding-001.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json). 관측 후보→원문 확보→최종 인용. 미실행은 executed=false.',f'[원시 요청과 응답](../artifacts/live/{cid}/calls.json), raw/call-*/request.json.gz,response.json.gz 및 canonical/*.json.gz.' if row['executed'] else '새 제품 호출0.',f'[단계별 호출](../artifacts/live/{cid}/generations.json)' if row['executed'] else '새 중간 호출0.','평가 모델0. 같은 사례 반복0. 알려진 사례 probe.','```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```'];p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
put(ART/'candidate-diff.json',{'candidate':f['candidate_revision'],'parent_changed':[n for n,h in f['files'].items() if read(DES/'parent-freeze.json')['files'].get(n)!=h],'main112_changed':[n for n,h in f['files'].items() if baseline['release']['files'].get(n)!=h],'working_product_integrated':False})
print(json.dumps(result,ensure_ascii=False,indent=2))
