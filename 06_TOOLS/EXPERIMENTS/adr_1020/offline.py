from common import *
import sys,importlib.util
C=ROOT/read(ART/'stage.json')['roots']['candidate'];sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent.gateway import _response_diagnostics
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1018-complete-connection-directory/artifacts/known-query/candidate'
rows=[]
for n in (11,12):
 p=prior/f'model/call-{n:03}-service/response.json';r=read(p);d=_response_diagnostics(r)
 assert d['finish_reason']=='length'
 rows.append({'source':str(p.relative_to(ROOT)),'sha256':sha(p),'finish_reason':d['finish_reason'],'completion_tokens':d['completion_tokens'],
 'new_action':'SOURCE_EXCERPTS_WITH_INCOMPLETE_REVIEW; no further model call', 'partial_claims_accepted':False})
save(ART/'parent-failure-replay.json',{'exact_parent_metadata':rows,'live_calls':0,'limits':'Read-only classification of captured failures; actual host source publication separately verified by synthetic API failure injection.'})
print('Both parent failures are typed OUTPUT_LENGTH_LIMIT; no prefix claim decoding')
