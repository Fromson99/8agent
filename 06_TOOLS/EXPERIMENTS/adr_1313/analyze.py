from common import *
from collections import Counter,defaultdict
s=read(ART/'actual/sqlite/result.json');o=read(ART/'actual/oracle-prepared/result.json');sm={r['id']:r for r in s['rows']};om={r['id']:r for r in o['rows']};checks=[]
for k in sm.keys()&om.keys():
 a=sm[k];b=om[k];row={'id':k,'sqlite':a['status'],'oracle':b['status'],'sqlite_seconds':a['seconds'],'oracle_seconds':b['seconds'],'sqlite_sql':a['sql_selects'],'oracle_sql':b['sql_selects']}
 if a['status']==b['status']=='PASS':
  av=a['value'];bv=b['value']
  if k=='original-blocks':row.update(exact_originals=sum(x['row']==y['row'] for x,y in zip(av,bv)),original_count=len(av),repeat_sql_sqlite=sum(x['repeat_sql'] for x in av),repeat_sql_oracle=sum(x['repeat_sql'] for x in bv))
  elif isinstance(av,dict) and 'record' in av:row.update(exact_record=av['record']==bv['record'],repeat_sql_sqlite=av['verify_and_repeat_sql'],repeat_sql_oracle=bv['verify_and_repeat_sql'])
  elif k.startswith('fts-'):
   def normalize(v):return {p:None if v[p] is None else {'items':[{k:x for k,x in row.items() if k!='score'} for row in v[p]['items']],'total':v[p]['total'],'offset':v[p]['next_cursor']['offset'] if v[p]['next_cursor'] else None} for p in ['page1','page2']}
   row.update(exact_ranked_bodies_and_totals=normalize(av)==normalize(bv),exact_scores=all([x.get('score')==y.get('score') for p in ('page1','page2') if av[p] and bv[p] for x,y in zip(av[p]['items'],bv[p]['items'])]),repeat_sql_sqlite=av['repeat_sql'],repeat_sql_oracle=bv['repeat_sql'])
 checks.append(row)
queries=read(ART/'actual/oracle-prepared/oracle-query-observation.json')['queries'];agg=defaultdict(lambda:{'selects':0,'execute_seconds':0,'fetch_seconds':0,'rows':0})
for r in queries:
 v=agg[r['phase']];v['selects']+=1;v['execute_seconds']+=r['seconds'];v['fetch_seconds']+=r['fetch_seconds'];v['rows']+=r['rows']
contract=read(ART/'diverse-contracts-stable/result.json');baseline=read(ART/'baseline-failures/result.json')
put(ART/'analysis.json',{'sqlite':{k:s[k] for k in ('passed','failed','total_cases','seconds','completed')},'oracle':{k:o[k] for k in ('passed','failed','total_cases','seconds','completed')},'cross_db':sorted(checks,key=lambda x:x['id']),'oracle_phases':dict(agg),'oracle_actual_selects':len(queries),'oracle_preparation_failure_selects':1,'contracts':{'passed':contract['passed'],'failed':contract['failed'],'baseline_recheck_passed':baseline['passed'],'baseline_recheck_failed':baseline['failed'],'failed_types':{'preexisting_fixture':2,'captured_parallel_oracle_dp_code_pin_mismatch':3}},'metadata':{'same_original_store':True,'fulltext_scope_metadata_projection_only':True,'scores_differ_reason':'Pending exact publication/global statistics investigation; ranked first10bodies agree for observed hit queries; no score equality claim'},'new_models':0,'writes':0,'ddl':0,'main_unchanged':True,'candidate_preparation_issue':'Captured oracle_dp.py concurrent edit does not match frozen old engine pins; direct query tests run but3nativeAPIcalls blocked. Preserve and use immutable prior module in separate followup.'})
put(RUN/'result.json',read(ART/'analysis.json'));print(json.dumps({k:read(ART/'analysis.json')[k] for k in ['sqlite','oracle','oracle_phases']},ensure_ascii=False))
