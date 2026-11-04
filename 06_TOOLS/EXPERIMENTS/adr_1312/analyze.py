from common import *
import collections
rows=[]
audit=read(ART/'source-wire-audit.json');semantic=read(ART/'semantic-review.json')
for a in audit['cells']:
 p=ART/'live'/a['cell'];r=read(p/'result.json');sql=read(p/'sql-observation.json');calls=read(p/'calls.json')
 queries=[q for q in sql['rows'] if q['phase']=='request']
 finish=[]
 for f in sorted((p/'canonical').glob('*-output.json.gz')):
  v=read(f)
  if v.get('choice')=='FINISH':finish.append(int(f.name.split('-')[0]))
 handoffs=[e for e in a['supervisor_events'] if e['kind']=='SUPERVISOR_FINISH_HANDOFF']
 row={'cell':a['cell'],'case_id':a['case_id'],'arm':a['arm'],'http_status':r['http_status'],'seconds':r['request_seconds'],'model_seconds':a['model_seconds'],'outside_model_seconds':r['request_seconds']-a['model_seconds'],'physical_calls':len(calls),'claims':r['claims'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_mismatches':len(a['wire_mismatches']),'budget_matches':a['budget_matches'],'reported_cost_usd':a['reported_cost_usd'],'reported_tokens':a['reported_tokens'],'unknown':a['unknown'],'providers':a['actual_providers'],'finish_proposals':finish,'finish_handoffs':len(handoffs),'supervisor_calls':sum('supervisor' in str(c['stage']) for c in calls),'sql_api_seconds':sum(q['api_seconds'] for q in queries),'fts_calls':None,'fts_seconds':None,'fts_unmeasured_reason':'Live observer aggregates operations, query-shape timings only available in1311 replay','source_select_traces':sum(q['trace_statements'] for q in queries if q['database']=='corpus' and q['operation'] in ('SELECT','WITH')),'duplicate':r.get('duplicate'),'answer_review':next(x for x in semantic['rows'] if x['cell']==a['cell'])}
 assert not (row['source_mismatches'] or row['acl_violations'] or row['wire_mismatches']) and row['budget_matches']
 rows.append(row)
paired=[r for r in rows if r['case_id']=='ontology-369'];b=next((r for r in paired if r['arm']=='before'),None);a=next((r for r in paired if r['arm']=='after'),None)
comparison={'eligible':bool(a and b and all(r['http_status']==200 and r['answer_review']['verdict']=='PASS' for r in (a,b))),'note':'Single stochastic live pair, both already use1311 performance repair; no isolated general whole-service effect. Historical1309 comparison also changes model path/time.'}
if comparison['eligible']:comparison.update(before_seconds=b['seconds'],after_seconds=a['seconds'],reduction_percent=100*(1-a['seconds']/b['seconds']),before_calls=b['physical_calls'],after_calls=a['physical_calls'])
result={'status':'complete','rows':rows,'paired369':comparison,'physical_calls':sum(r['physical_calls'] for r in rows),'reported_cost_usd':sum(r['reported_cost_usd'] for r in rows),'reported_tokens':sum(r['reported_tokens'] for r in rows),'unknown':sum(r['unknown'] for r in rows),'after_content_pass':sum(r['arm']=='after' and r['answer_review']['verdict']=='PASS' for r in rows),'new_model_judge_calls':0,'oracle_calls':0,'main_changed':False}
put(ART/'analysis.json',result);put(RUN/'result.json',result)
print(json.dumps([{k:r[k] for k in ('cell','seconds','model_seconds','outside_model_seconds','physical_calls','claims','finish_proposals','finish_handoffs','supervisor_calls')} for r in rows],ensure_ascii=False,indent=2));print(comparison)
