from common import *
from copy import deepcopy
import gzip
f=read(DES/'freeze.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.ontology_work import profile, accumulation as acc, authoring_semantics as sem, assembly_compiler
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1230-source-meaning-evidence-live/artifacts/live'
def saved(p):
 v=json.loads(p.read_text())
 if set(v)=={'raw_json'}:
  with gzip.open(ROOT/v['raw_json']['path'],'rt') as h:return json.load(h)
 return v
p=profile.compile_profile(read(ROOT/f['code_root']/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(ROOT/f['code_root']/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
# Use the actual persisted profile, avoiding in-memory shared schema objects.
binding=saved(prior/'binding.json');p=saved(prior/'objects/objects'/(binding['profile']['work_hash']+'.json'))['profile']
n=saved(prior/'saved-007-a-normalized.json')['normalized'];inp=saved(prior/'input-004.json');raw=saved(prior/'output-004.json');sources=inp['context']['originals'];analysis=inp['context']['source_analysis']
schema=sem.request_schema(acc.accumulation_schema(p,[n],None,sources),analysis)
try:sem.restore(raw,schema,analysis,sources)
except ContractError as exc:original_error=str(exc)
else:raise AssertionError('original SAME must remain rejected')
changed=deepcopy(raw)
for c in changed['comparisons']:
 if c['relation']=='SAME':c['relation']='NEW'
try:
 canonical,receipt=sem.restore(changed,schema,analysis,sources)
 acc.validate_proposal(canonical,p,sources,[n],None)
 package=assembly_compiler.compile_package(canonical['graph'],p,sources,bundle_id='cb-kb-diagnostic',revision=1,glossary_refs=[])
 result={'hypothetical_relation_only_change_valid':True,'nodes':len(canonical['graph']['nodes']),'effect_actions':[r['slots']['action'] for r in canonical['graph']['nodes'] if r['kind']=='EFFECT'],'compile_preview':True}
except ContractError as exc:result={'hypothetical_relation_only_change_valid':False,'next_error':str(exc)}
put(ART/'saved-response-diagnostic-stored-profile.json',{'kind':'COUNTERFACTUAL_OFFLINE_DIAGNOSTIC_NOT_MODEL_SUCCESS','original_response_sha256':digest(raw),'original_rejected':True,'original_error':original_error,'modified_only':'copy comparisons SAME to NEW, no saved observation/DB/result mutation','new_model_calls':0,'new_drafts_saved':0,**result})
print(result)
