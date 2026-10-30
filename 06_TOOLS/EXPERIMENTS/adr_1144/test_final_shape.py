from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import read_judgment_final as fj
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.local_gemma import provider_request
from test_final_diagnostics import fixture

@pytest.mark.parametrize('disposition',['USE','CONDITIONAL','UNRESOLVED','NOT_USED'])
@pytest.mark.parametrize('has_claim',[False,True])
def test_claim_shape_survives_native_projection(disposition,has_claim):
 c,v=fixture();s=fj.review_schema(c['view']['read_judgments'],c['view']['evidence_options'],enforce_claim_shape=True)['properties']['judgments']['items']
 row=deepcopy(v[fj.FIELD]['judgments'][0]);row.update(disposition=disposition,claim_refs=['C1'] if has_claim else [])
 expected=(disposition in ('USE','CONDITIONAL'))==has_claim
 assert Draft202012Validator(s).is_valid(row)==expected
 if not expected:return
 p=Projection(s);wire=p.project(row);assert p.expand(wire)==row
 actual=provider_request({'response_format':{'type':'json_schema','json_schema':{'name':'final_shape','strict':True,'schema':p.wire}}})['response_format']['json_schema']['schema']
 Draft202012Validator(actual).validate(wire)
 invalid=deepcopy(wire)
 if has_claim:invalid['claim_refs']=[]
 else:invalid['claim_refs']=['C1']
 assert not Draft202012Validator(actual).is_valid(invalid)
