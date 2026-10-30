from copy import deepcopy
import pytest
from semantic_runtime.ontology_work import accumulation as a
from semantic_runtime.legal_agent.errors import ContractError
from test_domain_profile_workflow import env,save
from test_accumulation_refs import prepare

@pytest.mark.parametrize('has_base',[False,True])
def test_same_changed_or_absent_base_rejected_with_full_reference_errors(env,has_base):
 o,ns,p,v=prepare(env);base=env.w.load(save(env,o,v)['bundle_id']) if has_base else None
 v['comparisons'][0]['relation']='SAME'
 if has_base:
  v['graph']['nodes'][0]['id']='N2';v['graph']['purposes'][0]['roots']=['N2'];v['comparisons'][0]['node_ids']=['N2']
 before=deepcopy(v)
 with pytest.raises(ContractError) as exc:a.validate_proposal(v,p,[env.source],ns,base)
 assert 'SAME requires the entire proposed graph' in str(exc.value)
 if has_base:assert "removed_nodes expected=['N1']" in str(exc.value)
 assert v==before

def test_same_exact_graph_remains_accepted(env):
 o,ns,p,v=prepare(env);base=env.w.load(save(env,o,v)['bundle_id']);v['comparisons'][0]['relation']='SAME'
 result=a.validate_proposal(v,p,[env.source],ns,base)
 assert result['diff']['nodes']['added']==[] and len(result['comparison_history'])==2
