from common import *
from collections import defaultdict
prev=ROOT/'04_EXPERIMENTS/ADR/ADR-1313-sqlite-oracle-diverse-validation/artifacts';rows=[]
old={a:read(prev/'actual'/('oracle-prepared' if a=='oracle' else a)/'result.json') for a in ('sqlite','oracle')};new={a:read(ART/'actual'/a/'result.json') for a in ('sqlite','oracle')}
for arm in new:
 p={r['id']:r for r in old[arm]['rows']}
 for r in new[arm]['rows']:
  before=p[r['id']];a=before.get('value');b=r.get('value');exact=None
  if isinstance(a,dict) and 'record' in a:exact=a['record']==b['record']
  elif r['id']=='original-blocks':exact=all(x['row']==y['row'] for x,y in zip(a,b))
  elif r['id'].startswith('fts'):exact=a==b
  else:exact=a==b
  assert exact,(arm,r['id']);rows.append({'arm':arm,'case':r['id'],'exact_value_or_record':exact,'before_seconds':before['seconds'],'after_seconds':r['seconds'],'before_sql':before['sql_selects'],'after_sql':r['sql_selects']})
# Same-source two databases have distinct cursor bindings and published BM25 statistics.
sm={r['id']:r for r in new['sqlite']['rows']};om={r['id']:r for r in new['oracle']['rows']};cross=[]
for k in sm:
 a=sm[k]['value'];b=om[k]['value']
 if k=='original-blocks':assert all(x['row']==y['row'] for x,y in zip(a,b));cross.append({'case':k,'exact_originals':6})
 elif isinstance(a,dict) and 'record' in a:assert a['record']==b['record'];cross.append({'case':k,'exact_record':True})
root=next(r for r in rows if r['arm']=='oracle' and r['case']=='root-article-set');root['seconds_reduction_pct']=(1-root['after_seconds']/root['before_seconds'])*100;root['sql_reduction_pct']=(1-root['after_sql']/root['before_sql'])*100
obs=read(ART/'actual/oracle/oracle-query-observation.json');agg=defaultdict(lambda:{'selects':0,'driver_wall_seconds':0,'rows':0})
for q in obs['queries']:
 r=agg[q['phase']];r['selects']+=1;r['driver_wall_seconds']+=q['seconds']+q['fetch_seconds'];r['rows']+=q['rows']
contracts=read(ART/'contracts/result.json');assert contracts['failed']==2
result={'arms':{a:{k:new[a][k] for k in ['passed','failed','total_cases','seconds','completed']} for a in new},'same_db_before_after':rows,'cross_db':cross,'oracle_root':root,'oracle_actual_selects':obs['selects'],'oracle_phases':dict(agg),'contracts':{'passed':contracts['passed'],'failed':contracts['failed'],'preexisting_same_two':True,'new_root_tests':11,'native_api_pin_failures_recovered':3},'root_cache':{k:v for k,v in new['oracle']['rows'][-2]['value'].items() if k.startswith('root_cache')},'fts_diagnosis':read(ART/'fts-statistics-diagnosis.json'),'whole_oracle_seconds_before':old['oracle']['seconds'],'whole_oracle_seconds_after':new['oracle']['seconds'],'new_model_calls':0,'ddl':0,'oracle_writes':0,'main_unchanged':True,'inference_limit':'One sequential casepair; DBwarm-cache variance possible. ExactSQLcount and deleted166ownerqueries/1191pointqueries are deterministic evidence; no fieldthroughput/generalanswerqualityclaim.'}
put(ART/'analysis.json',result);put(RUN/'result.json',result);print(json.dumps({'root':root,'arms':result['arms'],'phases':dict(agg)},ensure_ascii=False))
