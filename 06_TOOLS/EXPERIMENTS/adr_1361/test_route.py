import pytest
from common import *
from semantic_runtime.legal_agent.provider_routing import validate_policy,route,validate_response
from semantic_runtime.legal_agent import provider_routing as routing
from semantic_runtime.legal_agent.local_gemma import provider_request

def test_bf16_single_provider_strict_no_fallback():
    cfg=validate_policy(read(DES/'provider-deepinfra.json'));p=cfg['providers'][0];r=route(p)
    assert r['only']==r['order']==['deepinfra/bf16'] and r['quantizations']==['bf16']
    assert r['require_parameters'] and not r['allow_fallbacks']
    validate_response({'provider':'DeepInfra','model':cfg['model']},p,cfg['model'])
@pytest.mark.parametrize('model,provider',[('wrong','DeepInfra'),('qwen/qwen3.8-27b','Parasail')])
def test_wrong_provider_or_model_is_rejected(model,provider):
    cfg=validate_policy(read(DES/'provider-deepinfra.json'))
    with pytest.raises(ValueError):validate_response({'provider':provider,'model':model},cfg['providers'][0],cfg['model'])
def test_all_other_product_bytes_equal_parent():
    p=read(DES/'candidate-parent.json');f=read(DES/'candidate-repaired.json');changed=[n for n,h in p['selected_files'].items() if f['selected_files'][n]!=h]
    product=[n for n in changed if not n.startswith('02_BACKEND/ENGINES/') and n not in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py')]
    assert product==['02_BACKEND/semantic_runtime/legal_agent/provider_routing.py']
