"""Exact historical wire projection only; no generation, response grading or replay."""
from common import *
from collections import Counter
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import assessment_input as ai
source=ROOT/'04_EXPERIMENTS/ADR/ADR-1281-scenario-review-schema-live/artifacts/live/review-whatif/raw'
def strings(value):
 if isinstance(value,str):yield value
 elif isinstance(value,dict):
  for child in value.values():yield from strings(child)
 elif isinstance(value,list):
  for child in value:yield from strings(child)
def size(value):return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
rows=[]
for folder in sorted(source.glob('call-*')):
 started=read(folder/'started.json')
 if started['stage'] not in ('memory-assess','memory-assess-repair'):continue
 request=read(folder/'request.json.gz')
 view=json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'))['view']
 if not ai.applies(view,stage=started['stage']):continue
 projected=ai.project(view,stage=started['stage']);restored=ai.restore(projected)
 assert view==restored
 before=Counter(strings(view));after=Counter(strings(projected))
 repeated=[{'text_sha256':hashlib.sha256(s.encode()).hexdigest(),'characters':len(s),'before':n,'after':after[s]} for s,n in before.items() if len(s)>=80 and n>1]
 assert all(r['after']==1 for r in repeated)
 rows.append({'call':started['number'],'stage':started['stage'],'source':bind(folder/'request.json.gz'),
  'round_trip_equal':True,'before_view_utf8_bytes':size(view),'after_view_utf8_bytes':size(projected),
  'exact_repeated_texts':sorted(repeated,key=lambda r:r['characters']*(r['before']-1),reverse=True),
  'current_case':list(projected['current_case']), 'source_ids_and_roles_preserved':True})
assert len(rows)==5,len(rows)
put(ART/'offline-wire-projection.json',{'candidate':bind(DES/'freeze.json'),'rows':rows,'model_calls':0,
 'limits':['Offline display transform applied to historical provider views; not a new provider request or response',
 'View UTF8 bytes only, not tokens or complete request size',
 'No causal model-quality or latency improvement claim; five requests belong to the same historical experiment']})
print(json.dumps([{'call':r['call'],'bytes':[r['before_view_utf8_bytes'],r['after_view_utf8_bytes']], 'repetitions':[[x['characters'],x['before'],x['after']] for x in r['exact_repeated_texts']]} for r in rows],ensure_ascii=False))
