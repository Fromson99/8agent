"""Post-run-edge unit diagnosis, no model or source-index loading."""
from common import *
from types import SimpleNamespace as N
import sys
meta=read(DES/'candidate.json');C=ROOT/meta['path']/'revisions/rev-001/snapshot'/meta['selected_code_relative'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.knowledge_delivery import enrich
host=N(pipeline=N(term_agent=N(transport=N(knowledge_delivery_enabled=True))),binding={},knowledge_plan={'mode':'consume','plan':{'binding':None,'items':[]}})
selection={'selected_originals':[],'selected_evidence':[]}
try:
 result=enrich(N(host=host,s=N(sources=N())),selection)
 observation={'status':'PASS' if result is selection else 'FAIL','result':result}
except Exception as exc:
 observation={'status':'FAIL','error_type':type(exc).__name__,'error':str(exc)}
put(ART/'no-match-contract.json',{'test':'Empty knowledge plan must preserve ordinary source research','expected':'same selection, no extra reads','observation':observation,'model_calls':0,'source_loads':0,'candidate_changed':False})
print(json.dumps(observation))
