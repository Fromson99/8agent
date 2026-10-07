"""Read-only posthoc audit of frozen reports; no model imports, calls, or regrading."""
import json,hashlib,statistics,math,sqlite3
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0500-gemma-qwen-behavior-audit';P=R/'04_EXPERIMENTS/ADR'
SPECS={'qwen':('ADR-0496-qwen-source-workflow-cm51-fsc10','repaired'),'gemma':('ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10','gemma'),'qwen_retry':('ADR-0499-qwen-interrupted-five-retry','repaired')}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def stats(xs):return {'n':len(xs),'median':statistics.median(xs) if xs else None,'p95':sorted(xs)[math.ceil(.95*len(xs))-1] if xs else None,'total':sum(xs)}
def body(raw):
 try:
  x=json.loads(raw);b=x.get('body_json') or json.loads(x.get('body_text') or '{}');return b
 except (ValueError,TypeError):return {}
def main():
 inp=read(A/'artifacts/inputs.json')
 for p,h in inp['sha256'].items():assert sha(R/p)==h,p
 datasets={};out={};phase_stats={}
 for label,(slug,arm) in SPECS.items():
  base=P/slug;met=read(base/'artifacts/metrics.json');di=read(base/'artifacts/workflow-diagnostics.json');prod=read(base/'artifacts/run-001/results.json');gold={x['case_id']:set(x['decisive_source_ids']) for x in read(base/'gold-cases.json')['cases']}
  metrics={x['case_id']:x for x in met['by_case']};diagnostics={x['case_id']:x for x in di['by_case']};rows={cid:{'metric':metrics[cid],'diagnostic':diagnostics[cid],'product':p[arm],'gold':gold[cid]} for cid,p in prod['cases'].items()};datasets[label]=rows
  sem=di['by_cohort']['all']['semantic_error_messages'];policy=read(base/'artifacts/model-audit.json');model_id='google/gemma-4-31b-it' if label=='gemma' else 'qwen/qwen3.5-122b-a10b';wire=[r for r in policy['rows'] if r['role']=='product']
  usage=[u for r in rows.values() for u in r['product']['usage']];traces={};durations={};finishes=Counter();errors=Counter();review_data=[];stagegold={s:sum(len(set(r['product']['stages'].get(s,[]))&r['gold']) for r in rows.values()) for s in ['discovered','read','presented','selected','payload_sources','final_sources']}
  for cid,r in rows.items():
   folder=base/'artifacts/run-001'/cid/arm;traces[cid]=read(folder/'trace.json')
   with sqlite3.connect('file:'+str(folder/'journal.sqlite')+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    for x in db.execute('SELECT a.*,v.phase FROM model_attempt a JOIN model_view v USING(view_id)'):
     b=body(x['response_json']);choices=b.get('choices') or []
     if choices:
      finishes[choices[0].get('finish_reason')]+=1
      if x['phase']=='review':
       try:parsed=json.loads(choices[0]['message']['content'])
       except (ValueError,TypeError,KeyError):parsed=None
       if parsed:review_data.append({'case':cid,'parsed':parsed,'view_id':x['view_id']})
     if x['started_at'] and x['finished_at']:
      from datetime import datetime
      try:sec=(datetime.fromisoformat(x['finished_at'])-datetime.fromisoformat(x['started_at'])).total_seconds()
      except (ValueError,TypeError):continue
      durations.setdefault(x['phase'],[]).append(sec)
   if r['product'].get('error'):errors[r['product']['error']['type']]+=1
  out[label]={'case_count':len(rows),'original_aggregate':met['by_arm'][arm],'stage_gold_recomputed':stagegold,'gold_total':sum(len(r['gold']) for r in rows.values()),'worker_result_count':sum(not r['product'].get('reconstruction') for r in rows.values()),'reviewed_answer_count':sum(r['metric']['claims']>0 for r in rows.values()),'execution_error_types':dict(errors),'publication_errors':[cid for cid,r in rows.items() if r['product'].get('publication_error')],'schema_errors':di['by_cohort']['all']['schema_error_events'],'workflow_errors':di['by_cohort']['all']['workflow_error_events'],'workflow_error_cases':di['by_cohort']['all']['workflow_error_cases'],'semantic_event_counts':sem,'semantic_case_counts':{msg:sum(any(e.get('message')==msg for e in r['diagnostic']['semantic_events']) for r in rows.values()) for msg in sem},'model_call_stats_per_case':stats([r['metric']['calls'] for r in rows.values()]),'returned_call_seconds':stats([u['seconds'] for u in usage]),'output_tokens_per_returned_call':stats([u.get('output_tokens') or 0 for u in usage]),'product_latency_uncensored':stats([r['product']['seconds'] for r in rows.values() if not r['product'].get('latency_censored')]),'finish_reasons':dict(finishes),'attempt_statuses':di['by_cohort']['all']['attempt_statuses'],'phases':{k:stats(v) for k,v in durations.items()},'repeated_exact_operations_per_case':stats([r['diagnostic']['exact_repeated_model_operations'] for r in rows.values()]),'repeat_reads_zero_new_chars':sum(r['diagnostic']['zero_new_chars_model_reads'] for r in rows.values()),'expected_product_model':model_id,'request_policy_role_aware_valid':all(r['requested_model']==model_id and r['fp8_requested'] and r['provider_fallbacks_disabled'] and r['reasoning_disabled'] for r in wire),'reviews_raw':review_data}
 q=datasets['qwen'];g=datasets['gemma'];cohorts={'all61':list(q),'qwen_no_infrastructure56':[cid for cid in q if not q[cid]['product'].get('reconstruction')],'both_without_execution_or_publication_error':[cid for cid in q if not q[cid]['product'].get('error') and not g[cid]['product'].get('error') and not q[cid]['product'].get('publication_error') and not g[cid]['product'].get('publication_error')],'both_reviewed':[cid for cid in q if q[cid]['metric']['claims'] and g[cid]['metric']['claims']]};paired={}
 for name,ids in cohorts.items():
  cohort={'ids':ids,'n':len(ids),'by_model':{}};passpairs=Counter();answerspairs=Counter();joint_gold=[]
  for cid in ids:
   qr=q[cid];gr=g[cid];qc=qr['metric']['correct'];gc=gr['metric']['correct'];passpairs['ungraded' if qc is None or gc is None else 'both' if qc and gc else 'qwen_only' if qc else 'gemma_only' if gc else 'neither']+=1;answerspairs['both' if qr['metric']['claims'] and gr['metric']['claims'] else 'qwen_only' if qr['metric']['claims'] else 'gemma_only' if gr['metric']['claims'] else 'neither']+=1
   shared=set(qr['product']['stages'].get('presented',[]))&set(gr['product']['stages'].get('presented',[]))&qr['gold']
   for sid in shared:joint_gold.append({'case':cid,'source':sid,'qwen_selected':sid in qr['product']['stages'].get('selected',[]),'gemma_selected':sid in gr['product']['stages'].get('selected',[])})
  for label,rows in [('qwen',q),('gemma',g)]:
   selected=[rows[cid] for cid in ids];cohort['by_model'][label]={'raw_pass':sum(r['metric']['correct'] is True for r in selected),'reviewed':sum(r['metric']['claims']>0 for r in selected),'ungraded':sum(r['metric']['correct'] is None for r in selected),'draft_rejection_cases':sum(any(e.get('message')=='draft may cite selected delivered sources only' for e in r['diagnostic']['semantic_events']) for r in selected),'review_question_coverage_rejection_cases':sum(any(e.get('message')=='review must cover original question' for e in r['diagnostic']['semantic_events']) for r in selected),'stage_gold':{s:sum(len(set(r['product']['stages'].get(s,[]))&r['gold']) for r in selected) for s in ['read','presented','selected','payload_sources','final_sources']}}
  cohort.update(raw_pass_pairs=dict(passpairs),reviewed_pairs=dict(answerspairs),joint_presented_gold={'count':len(joint_gold),'qwen_selected':sum(x['qwen_selected'] for x in joint_gold),'gemma_selected':sum(x['gemma_selected'] for x in joint_gold),'records':joint_gold});paired[name]=cohort
 per_case=[]
 for cid in q:
  r={'case_id':cid}
  for label,rows in [('qwen',q),('gemma',g)]:
   x=rows[cid];r[label]={'reviewed_claims':x['metric']['claims'],'auto_pass':x['metric']['correct'],'judge_reason':x['metric']['judge_reason'],'execution_error':x['product'].get('error',{}),'stages':x['diagnostic']['stage_counts'],'gold':x['diagnostic']['gold_by_stage'],'semantic_errors':[e.get('message') for e in x['diagnostic']['semantic_events']],'calls':x['metric']['calls']}
  per_case.append(r)
 result={'comparison':'Historical descriptive audit, not controlled model-effect estimate','additional_model_calls':0,'known_prior_scores':{'qwen':2,'gemma':8},'aggregates':out,'cohorts':paired,'cases':per_case,'warnings':['One trial per model; provider and resource environment differ.','Same canonical source exposure does not imply identical text spans/context.','Conditional no-error/reviewed subsets are selected after execution and subject to selection bias.','Judge is Qwen for both; no independent human calibration; raw scores not revised.','Qwen infrastructure retries are separate appendix, never choose best run.']}
 dump(A/'artifacts/comparison.json',result)
 print(json.dumps({'aggregates':{k:{f:v[f] for f in ['case_count','reviewed_answer_count','execution_error_types','model_call_stats_per_case','returned_call_seconds','finish_reasons','request_policy_role_aware_valid']} for k,v in out.items()},'cohorts':{k:{f:v[f] for f in ['n','by_model','raw_pass_pairs','reviewed_pairs']} for k,v in paired.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
