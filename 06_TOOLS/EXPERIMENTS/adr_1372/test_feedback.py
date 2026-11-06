from copy import deepcopy
from pathlib import Path
import gzip
import importlib.util
import json
import pytest
from semantic_runtime.legal_agent import need_continuity as nc
from semantic_runtime.legal_agent.output_contract import OutputContractError

ROOT = Path(__file__).resolve().parents[3]


def captured(number):
    directory = ROOT/'04_EXPERIMENTS/ADR/ADR-1370-integration-oneclick-provider-repeat/artifacts/public-live/B03-12-reka/raw'
    with gzip.open(directory/f'call-{number}/response.json.gz','rt') as stream:
        return json.loads(json.load(stream)['choices'][0]['message']['content'])


@pytest.mark.parametrize('number',['008','009'])
def test_real_use_error_names_selected_slot_and_actual_claims(number):
    raw = captured(number)
    saved = deepcopy(raw)
    with pytest.raises(OutputContractError) as rejection:
        nc._validate_assigned_uses(raw)
    detail = rejection.value.issues[0]
    assert detail['code'] == 'SCOPE_USE_UNSUPPORTED_RANGE'
    assert detail['path'] == '/read_judgment_review/original_reviews'
    assert detail['expected_constraint']['assignments_without_a_claim'] == [
        {'slot':'R2','group_index':2,'basis_refs':['S5'],'issue_refs':['Q2']}]
    assert detail['expected_constraint']['current_claims'] == [
        {'claim_id':'C1','evidence_refs':['S4','S7'],'issue_refs':['Q2']}]
    assert rejection.value.proposal == saved == raw and rejection.value.proposal is not raw


def test_scope_join_still_requires_both_the_original_and_issue():
    raw = captured('009')
    raw['claims'].append({'claim_id':'C2','issue_refs':['another issue'],'evidence_refs':['S5']})
    with pytest.raises(OutputContractError):
        nc._validate_assigned_uses(raw)
    raw['claims'][-1]['issue_refs']=['Q2']
    before=deepcopy(raw)
    nc._validate_assigned_uses(raw)
    assert raw == before


def test_assignment_expansion_reports_the_model_field_without_altering_the_choice():
    path=ROOT/'06_TOOLS/EXPERIMENTS/adr_1363/test_assignments.py'
    spec=importlib.util.spec_from_file_location('assignments1363',path)
    prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    _,_,raw,_,expand,expected=prior.shape()
    assert expand(raw)==expected
    review=raw['read_judgment_review']
    used=next(i for i,g in enumerate(review['original_review_groups'],1) if g['disposition']=='USE')
    slot=next(k for k,r in review['original_reviews'].items() if review['original_review_groups'][r['group_index']-1]['disposition']=='EXCLUDE')
    used_slot=next(k for k,r in review['original_reviews'].items() if r['group_index']==used)
    review['original_reviews'][used_slot]['group_index']=review['original_reviews'][slot]['group_index']
    review['original_reviews'][slot]['group_index']=used
    saved=deepcopy(raw)
    with pytest.raises(OutputContractError) as rejection:
        expand(raw)
    missing=rejection.value.issues[0]['expected_constraint']['assignments_without_a_claim']
    assert [x['slot'] for x in missing]==[slot]
    assert raw==saved and rejection.value.proposal==raw


@pytest.mark.parametrize('number',['006','007'])
def test_group_can_contain_both_cited_and_uncited_originals(number):
    path=ROOT/'04_EXPERIMENTS/ADR/ADR-1370-integration-oneclick-provider-repeat/artifacts/public-live/B05-03-reka/raw'/f'call-{number}/response.json.gz'
    with gzip.open(path,'rt') as stream:
        raw=json.loads(json.load(stream)['choices'][0]['message']['content'])
    with pytest.raises(OutputContractError) as rejection:
        nc._validate_assigned_uses(raw)
    missing=rejection.value.issues[0]['expected_constraint']['assignments_without_a_claim']
    assert [(x['slot'],x['group_index'],x['basis_refs']) for x in missing]==[
        ('R7',2,['S14']),('R9',2,['S15']),('R10',2,['S12'])]
    assert raw['read_judgment_review']['original_reviews']['R8']=={'group_index':2,'basis_refs':['S11']}
