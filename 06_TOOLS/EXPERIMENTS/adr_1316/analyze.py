from common import *
from collections import defaultdict
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1315-bounded-structure-query-main/artifacts';pairs=[];arms={};after={}
for db in ('sqlite','oracle'):
 old=read(P/'actual'/(db+'-after')/'result.json');new=read(ART/'actual'/(db+'-after')/'result.json');after[db]=new
 assert new['completed'] and not new['failed'] and new['code_unchanged']
 assert read(P/'actual'/(db+'-after')/'catalogue.json')==read(ART/'actual'/(db+'-after')/'catalogue.json')
 prior={r['id']:r for r in old['rows']}
 for r in new['rows']:
  before=prior[r['id']];x=before['value'];y=r['value']
  if isinstance(x,dict) and 'record' in x:exact=x['record']==y['record']
  elif r['id']=='original-blocks':exact=[v['row'] for v in x]==[v['row'] for v in y]
  else:exact=x==y
  assert exact,(db,r['id'])
  pairs.append({'db':db,'case':r['id'],'exact':True,'before_seconds':before['seconds'],'after_seconds':r['seconds'],'before_sql':before['sql_selects'],'after_sql':r['sql_selects']})
 arms[db]={a:{k:v[k] for k in ['passed','failed','total_cases','seconds','events']} for a,v in [('before',old),('after',new)]}
sm={r['id']:r for r in after['sqlite']['rows']};om={r['id']:r for r in after['oracle']['rows']};cross=[]
for k,r in sm.items():
 x,y=r['value'],om[k]['value']
 if k=='original-blocks':assert [v['row'] for v in x]==[v['row'] for v in y];cross.append({'case':k,'originals':6})
 elif isinstance(x,dict) and 'record' in x:assert x['record']==y['record'];cross.append({'case':k,'exact_record':True})
root=next(r for r in pairs if r['db']=='oracle' and r['case']=='root-article-set');root['reduction_pct']=(1-root['after_seconds']/root['before_seconds'])*100
obs=read(ART/'actual/oracle-after/oracle-query-observation.json');agg=defaultdict(lambda:{'sql':0,'driver_wall_seconds':0,'rows':0})
for q in obs['queries']:
 r=agg[q['phase']];r['sql']+=1;r['driver_wall_seconds']+=q['seconds']+q['fetch_seconds'];r['rows']+=q['rows']
contracts=read(ART/'batch-contracts/result.json');assert contracts['failed']==0 and root['after_seconds']<root['before_seconds']*.75
result={'verified':True,'arms':arms,'oracle_root':root,'same_db_pairs':pairs,'cross_db':cross,'oracle_phases':dict(agg),'oracle_selects':obs['selects'],'batch_contracts':contracts['passed'],'inherited_contracts':read(P/'qualification.json'),'new_models':0,'ddl':0,'dml':0,'limitations':'One sequential pair; prior baseline from1315after. No model/answer/field certification. Lower driver wall time, not reduced SQL count.'}
put(ART/'analysis.json',result);put(RUN/'result.json',result);print(json.dumps({'root':root,'arms':arms,'oracle_phases':dict(agg)},ensure_ascii=False))
