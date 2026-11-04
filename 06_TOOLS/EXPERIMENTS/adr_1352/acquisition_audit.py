"""Compare recorded acquisition receipts; do not infer legal adoption."""
from common import *
rows=[]
for number,path in [(1345,ROOT/'04_EXPERIMENTS/ADR/ADR-1345-ontology-explicit-source-paired-use/artifacts'),(1352,ART)]:
 for d in sorted((path/'usage-live').glob('*ontology-on')):
  stages=[]
  for f in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):
   view=read(f).get('view',{});contexts=[]
   def walk(v):
    if isinstance(v,dict):
     for k,x in v.items():
      if k=='source_goal_context' and isinstance(x,dict):contexts.append(x)
      walk(x)
    elif isinstance(v,list):
     for x in v:walk(x)
   walk(view)
   goals=[{k:g.get(k) for k in ('goal_id','coordinate','status','arrivals')} for c in contexts for g in c.get('goals',[])]
   if goals:stages.append({'call':f.name,'source_stage':view.get('source_stage'),'goals':goals,'input_sha256':sha(f)})
  rows.append({'adr':number,'cell':d.name,'stages':stages})
put(ART/'acquisition-history-audit.json',{'rows':rows,'scope':'Actual model input receipts only. ACQUIRED does not certify adoption or final answer correctness. Different code and single stochastic runs are not causal latency evidence.','new_calls':0})
print([(r['adr'],r['cell'],len(r['stages'])) for r in rows])
