from pathlib import Path
from copy import deepcopy
import json,gzip
import pytest
from semantic_runtime.legal_agent import read_judgment_final as fj,output_contract as oc
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.minimal_output import Projection
BASE=Path(__file__).parents[3]/'04_EXPERIMENTS/ADR/ADR-1120-full-alternative-native-check/artifacts/run-002/fsc-hard-005'
def gz(p):return json.load(gzip.open(p,'rt'))
def fixture():
 c=gz(BASE/'canonical/015.json.gz');return c,gz(BASE/'canonical/014-output.json.gz')
def test_actual_zero_claims_error_has_judgment_paths_and_choices():
 c,v=fixture();ctx=c['view']['read_judgments'];options=c['view']['evidence_options'];assert v['claims']==[]
 with pytest.raises(oc.OutputContractError) as exc:fj.validate_review(v,ctx,options)
 issues=[i for i in exc.value.issues if i['code']=='FINAL_REVIEW_ACTUAL_CLAIM'];assert issues
 assert all(i['path'].startswith('/read_judgment_review/judgments/') and i['expected_constraint']['claim_count']==0 for i in issues)
 mapped=NavigationReferences(c['view']).view({'repair_feedback':{'errors':str(exc.value),'validation':oc.diagnostics(exc.value)}})
 assert all(len(i['expected_constraint']['judgment_id'])<6 for i in mapped['repair_feedback']['validation']['issues'] if i['code']=='FINAL_REVIEW_ACTUAL_CLAIM')
def test_final_unresolved_is_valid_without_automatic_claim():
 c,v=fixture();before=deepcopy(v)
 for r in v[fj.FIELD]['judgments']:r.update(disposition='UNRESOLVED',claim_refs=[],basis_refs=[])
 fj.validate_review(v,c['view']['read_judgments'],c['view']['evidence_options']);assert v['claims']==[] and before['claims']==[]
def test_final_wire_projection_stays_exact():
 c,v=fixture();refs=NavigationReferences(c['view']);p=Projection(refs.schema(c['schema']));actual=gz(BASE/'wire/015.json.gz')
 assert p.wire==actual['response_format']['json_schema']['schema']
@pytest.mark.parametrize('fault',['duplicates','reason','unadopted_claim'])
def test_final_guard_retains_precise_failures(fault):
 c,v=fixture()
 for r in v[fj.FIELD]['judgments']:r.update(disposition='UNRESOLVED',claim_refs=[],basis_refs=[])
 rows=v[fj.FIELD]['judgments']
 if fault=='duplicates':rows[-1]=deepcopy(rows[0])
 if fault=='reason':rows[0]['reason']=' '
 if fault=='unadopted_claim':rows[0]['claim_refs']=['K1']
 with pytest.raises((oc.OutputContractError,Exception)) as exc:fj.validate_review(v,c['view']['read_judgments'],c['view']['evidence_options'])
 assert exc.value
