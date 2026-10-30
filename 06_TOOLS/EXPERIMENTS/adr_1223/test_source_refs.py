from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.ontology_work import accumulation as a
from semantic_runtime.legal_agent.errors import ContractError
from test_domain_profile_workflow import env,add_observation,proposal
from test_accumulation_refs import prepare

@pytest.mark.parametrize('source,valid',[('S1',True),('O1',False),('o-incoming',False)])
def test_all_basis_sources_are_bound_to_offered_originals(env,source,valid):
 o,ns,p,v=prepare(env);old=deepcopy(p)
 for row in [v['graph']['nodes'][0],v['comparisons'][0]]:row['basis'][0]['source']=source
 schema=a.accumulation_schema(p,ns,originals=[env.source])
 assert Draft202012Validator(schema).is_valid(v) is valid and p==old

def test_unknown_metadata_can_keep_no_basis_or_graph_link(env):
 o,ns,p,v=prepare(env);v['comparisons'][0].update(verdict='UNKNOWN',basis=[],node_ids=[])
 a.validate_proposal(v,p,[env.source],ns)

def test_basis_error_paths_report_unknown_source_and_inexact_quote(env):
 o,ns,p,v=prepare(env);v['comparisons'][0]['basis'][0]['source']='O1';v['graph']['nodes'][0]['basis'][0]['quote']='가상 문구 조작'
 with pytest.raises(ContractError) as exc:a.validate_proposal(v,p,[env.source],ns)
 assert '/comparisons/0/basis/0/source' in str(exc.value) and '/graph/nodes/0/basis/0/quote' in str(exc.value)

def test_actual_accumulation_request_binds_sources_and_repairs_once(env):
 o,ns,p,v=prepare(env);calls=[]
 def generate(prompt,context,schema):
  calls.append(deepcopy(context));text=str(schema)
  assert "'enum': ['S1']" in text and 'basis=[]' in prompt
  value=deepcopy(v)
  if len(calls)==1:value['comparisons'][0]['basis'][0]['source']='O1'
  else:assert '/comparisons/0/basis/0/source' in context['repair']['previous']['error']
  return value,{'synthetic':True}
 env.w.generate=generate
 r=env.w.accumulate(bundle_id='cb-kb-source',expected_revision=0,profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,observation_ids=[o['bundle_id']],originals=[env.source])
 assert r['revision']==1 and len(calls)==2
