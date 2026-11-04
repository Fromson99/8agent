"""Describe saved final-review failures without changing or replaying calls."""
from common import *
rows=[]
for d in sorted((ART/'usage-live').iterdir()):
 if not (d/'result.json').exists():continue
 repairs=[]
 for f in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=read(f).get('view',{});fb=v.get('repair_feedback') or {}
  if fb:
   validation=fb.get('validation') or {}
   repairs.append({'call':f.name,'category':validation.get('category'),'issues':validation.get('issues',[]),'source_stage':v.get('source_stage')})
 calls=read(d/'calls.json')
 body=read(d/'turn-1/response.json.gz')['body']
 rows.append({'cell':d.name,'repairs':repairs,'call_stages':[{'number':c['number'],'stage':c['stage'],'status':c['status'],'seconds':c.get('seconds')} for c in calls],'body_keys':list(body),'model_seconds':sum(c.get('seconds',0) for c in calls),'review_seconds':sum(c.get('seconds',0) for c in calls if 'assess' in c['stage'])})
put(ART/'review-diagnostics.json',{'rows':rows,'new_model_calls':0,'scope':'Actual saved repair feedback; excluded-target/claim mismatches are observed, not a general causal attribution to ontology.'})
print(json.dumps([{'cell':r['cell'],'review_seconds':r['review_seconds'],'repair_codes':sorted({i['code'] for x in r['repairs'] for i in x['issues']})} for r in rows],ensure_ascii=False))
