"""Read saved canonical choices and matching source locations; no model calls."""
from common import *
def walk(v,path=''):
 if isinstance(v,dict):
  yield path,v
  for k,x in v.items():yield from walk(x,path+'/'+k)
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,path+'/'+str(i))
allrows=[]
for base in sorted((ART/'public-live').glob('*')):
 rows=[]
 for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  d=read(p);op=p.with_name(p.name.replace('.json.gz','-output.json.gz'));out=read(op) if op.exists() else None
  locations=[]
  for path,x in walk(d['view']):
   if any(key in x for key in ('read_candidates','connection_review','connection_scope_choices','source_goal_context','references','research_guidance')):
    locations.append({'path':path,'fields':{k:v for k,v in x.items() if k in ('read_candidates','connection_review','connection_scope_choices','source_goal_context','references','research_guidance')}})
  rows.append({'number':int(p.name[:3]),'stage':d['view'].get('source_stage',d['phase']),'output':out,'locations':locations})
 allrows.append({'cell':base.name,'frames':rows})
 print(base.name)
 for row in rows:print(json.dumps({k:v for k,v in row.items() if k!='locations'},ensure_ascii=False)[:7000])
 if (base/'turn-1/public-answer.txt').exists():print('ANSWER', (base/'turn-1/public-answer.txt').read_text())
if '--save' in sys.argv:
 ref=write_raw_json(ART/'navigation-diagnosis.json.gz',allrows);put(ART/'navigation-diagnosis-ref.json',ref)
