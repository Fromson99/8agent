from common import *
from collections import defaultdict
results={};pairs=[]
for db in ('sqlite','oracle'):
 results[db]={a:read(ART/'actual'/(db+'-'+a)/'result.json') for a in ('before','after')}
 a,b=results[db]['before'],results[db]['after']
 assert a['completed'] and b['completed'] and not a['failed'] and not b['failed']
 old={r['id']:r for r in a['rows']}
 assert read(ART/'actual'/(db+'-before')/'catalogue.json')==read(ART/'actual'/(db+'-after')/'catalogue.json')
 for r in b['rows']:
  p=old[r['id']];x=p['value'];y=r['value']
  if isinstance(x,dict) and 'record' in x:equal=x['record']==y['record']
  elif r['id']=='original-blocks':equal=[v['row'] for v in x]==[v['row'] for v in y]
  else:equal=x==y
  assert equal,(db,r['id'])
  pairs.append({'db':db,'case':r['id'],'exact':equal,'before_seconds':p['seconds'],'after_seconds':r['seconds'],'before_sql':p['sql_selects'],'after_sql':r['sql_selects']})
sm={r['id']:r for r in results['sqlite']['after']['rows']};om={r['id']:r for r in results['oracle']['after']['rows']};cross=[]
for k,v in sm.items():
 x=v['value'];y=om[k]['value']
 if k=='original-blocks':assert [r['row'] for r in x]==[r['row'] for r in y];cross.append({'case':k,'originals':6})
 elif isinstance(x,dict) and 'record' in x:assert x['record']==y['record'];cross.append({'case':k,'exact_record':True})
roots=[r for r in pairs if r['case']=='root-article-set']
for r in roots:r['seconds_reduction_pct']=(1-r['after_seconds']/r['before_seconds'])*100
phases={}
for arm in ('before','after'):
 obs=read(ART/'actual'/('oracle-'+arm)/'oracle-query-observation.json');agg=defaultdict(lambda:{'sql':0,'driver_wall_seconds':0,'rows':0})
 for q in obs['queries']:
  r=agg[q['phase']];r['sql']+=1;r['driver_wall_seconds']+=q['seconds']+q['fetch_seconds'];r['rows']+=q['rows']
 phases[arm]=dict(agg)
summary={db:{a:{k:results[db][a].get(k) for k in ['passed','failed','total_cases','seconds','completed','events']} for a in ('before','after')} for db in results}
r={'same_db_pairs':pairs,'cross_db':cross,'roots':roots,'arms':summary,'oracle_phases':phases,'new_models':0,'ddl':0,'dml':0,'catalogue_exact_both':True,'limitation':'One sequential before/after pair. No new answer quality, model latency or field Oracle19 certification.'}
put(ART/'analysis.json',r);put(RUN/'result.json',r);print(json.dumps({'arms':summary,'roots':roots,'oracle_phases':phases},ensure_ascii=False))
