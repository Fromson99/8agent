from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.ontology_work import accumulation as a
from semantic_runtime.legal_agent.errors import ContractError
from test_domain_profile_workflow import env,add_observation,proposal,save

def prepare(e):
 o=add_observation(e);ns=[e.w.load(o['bundle_id'])['normalized']];p=e.w.selected_profile(e.profile_id,e.profile_work_hash)
 return o,ns,p,proposal(e,o)

@pytest.mark.parametrize('fault',['comparison','removed','unused','all','missing-comparison','unknown-observation','unknown-provenance'])
def test_bad_references_rejected_together(env,fault):
 o,ns,p,v=prepare(env)
 if fault in ('comparison','all'):v['comparisons'][0]['node_ids']=['input-element']
 if fault in ('removed','all'):v['removed_nodes']=[{'id':'input-element','reason':'bad namespace','basis':v['comparisons'][0]['basis']}]
 if fault in ('unused','all'):v['graph']['unused_nodes']=[{'id':'O1','reason':'not a graph node'}]
 if fault=='missing-comparison':v['comparisons']=[]
 if fault=='unknown-observation':v['comparisons'][0]['observation_ref']='invented'
 if fault=='unknown-provenance':v['graph']['nodes'][0]['observation_refs']=['invented']
 before=deepcopy(v)
 with pytest.raises(ContractError) as error:a.validate_proposal(v,p,[env.source],ns)
 assert v==before
 if fault=='all':assert all(t in str(error.value) for t in ['node_ids unknown','removed_nodes expected=[]','unused_nodes unknown'])

@pytest.mark.parametrize('fault',['valid','wrong-comparison','wrong-provenance','false-removal'])
def test_bound_schema_restricts_input_ids_without_profile_mutation(env,fault):
 o,ns,p,v=prepare(env);before=deepcopy(p);s=a.accumulation_schema(p,ns)
 if fault=='wrong-comparison':v['comparisons'][0]['observation_ref']='O1'
 if fault=='wrong-provenance':v['graph']['nodes'][0]['observation_refs']=['O1']
 if fault=='false-removal':v['removed_nodes']=[{'id':'N1','reason':'no previous','basis':v['comparisons'][0]['basis']}]
 Draft202012Validator.check_schema(s)
 assert Draft202012Validator(s).is_valid(v) is (fault=='valid') and p==before

def test_actual_previous_node_deletion_and_unused_reason_allowed(env):
 o,ns,p,v=prepare(env);extra=deepcopy(v['graph']['nodes'][0]);extra['id']='N2';v['graph']['nodes'].append(extra);v['graph']['unused_nodes']=[{'id':'N2','reason':'not applicable to this purpose'}]
 first=save(env,o,v);base=env.w.load(first['bundle_id']);second=proposal(env,o)
 second['removed_nodes']=[{'id':'N2','reason':'removed duplicated rule','basis':second['comparisons'][0]['basis']}]
 assert Draft202012Validator(a.accumulation_schema(p,ns,base)).is_valid(second)
 checks=a.validate_proposal(second,p,[env.source],ns,base);assert checks['diff']['nodes']['removed']==['N2']

@pytest.mark.parametrize('fault',['references','compiler','twice','unknown'])
def test_existing_job_owns_one_repair_and_preserves_failed_output(env,fault):
 o,ns,p,valid=prepare(env);calls=[]
 def generate(prompt,context,schema):
  calls.append(deepcopy(context));assert context['reference_contract']['previous_graph_node_ids']==[]
  assert 'semantic_elements' in prompt and schema['properties']['removed_nodes']['maxItems']==0
  if fault=='unknown':raise RuntimeError('unknown send')
  v=deepcopy(valid)
  if len(calls)==1 or fault=='twice':
   if fault=='compiler':
    node=deepcopy(v['graph']['nodes'][0]);node['id']='N2';v['graph']['nodes'].append(node)
   else:
    v['comparisons'][0]['node_ids']=['input-element'];v['graph']['unused_nodes']=[{'id':'O1','reason':'not graph'}]
  return v,{'synthetic':True}
 env.w.generate=generate
 args=dict(bundle_id='cb-kb-test',expected_revision=0,profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,observation_ids=[o['bundle_id']],originals=[env.source])
 if fault in ('twice','unknown'):
  with pytest.raises(Exception):env.w.accumulate(**args)
 else:
  r=env.w.accumulate(**args);assert r['revision']==1
  assert len(calls)==2 and 'repair' in calls[1]
  expected='every unused node' if fault=='compiler' else 'unused_nodes unknown'
  assert expected in calls[1]['repair']['previous']['error']
 jobs=[env.w.load(r['bundle_id']) for r in env.repo.list(prefix='job-')];job=next(j for j in jobs if j['stage']=='ACCUMULATE')
 assert len(calls)==(1 if fault=='unknown' else 2)
 assert job['phase']==('INVALID' if fault=='twice' else 'UNKNOWN' if fault=='unknown' else 'READY')
 if fault=='twice':assert job['response']['comparisons'][0]['node_ids']==['input-element'] and len(job['attempts'])==2
