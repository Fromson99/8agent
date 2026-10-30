from copy import deepcopy
import gzip,json
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import assessment_consistency as guard, completion_contracts as cc, narrative_answer as narrative
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from common import ROOT,DES,ART,put,read

@pytest.mark.parametrize('status',['PARTIAL','INSUFFICIENT'])
@pytest.mark.parametrize('gaps',[[],[{'issue_id':'Q2','material':True}],[{'issue_id':'Q1','material':False}]])
def test_unresolved_requires_same_issue_material_gap(status,gaps):
    v={'issue_assessments':[{'issue_id':'Q1','status':status}],'gaps':gaps}
    before=deepcopy(v)
    with pytest.raises(ProposalError):guard.validate_proposal(v)
    assert v==before

@pytest.mark.parametrize('kind',['MISSING_SOURCE','MISSING_SCOPE','UNRESOLVED_REFERENCE','MISSING_FACT','VERSION_AMBIGUOUS'])
def test_explicit_remaining_needs_are_not_suppressed(kind):
    v={'issue_assessments':[{'issue_id':'Q1','status':'PARTIAL'}],'gaps':[{'issue_id':'Q1','material':True,'kind':kind}]}
    guard.validate_proposal(v)

def test_covered_with_nonmaterial_optional_unknown_is_allowed():
    guard.validate_proposal({'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],'gaps':[{'issue_id':'Q1','material':False}]})

def test_saved_actual_cm001_rejected_before_adoption():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1173-required-source-server-execution/artifacts/live/cm-001'
    saved=read(p/'audit.json')['assessments'][-1]['payload']
    assert saved['issue_assessments'][0]['status']=='PARTIAL' and saved['gaps']==[]
    with pytest.raises(ProposalError):guard.validate_proposal(saved)
    assert not guard.may_rewrite(saved)
    with pytest.raises(ContractError):guard.verify_publication(saved)
    put(ART/'saved-cm001-rejection.json',{'source':str(p.relative_to(ROOT)),'assessment_rejected':True,'unsafe_composition_allowed':False,'new_model_calls':0,'meaning_scored':False})

def complete():return {'disposition':'ANSWER','answer_coverage':'COVERED','issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],'gaps':[],'limitations':[]}

def test_completed_answer_can_use_existing_composer():
    a=complete();assert guard.may_rewrite(a);guard.verify_publication(a)

@pytest.mark.parametrize('update',[{'answer_coverage':'PARTIAL'},{'disposition':'LIMITED_ANSWER'}, {'issue_assessments':[{'issue_id':'Q1','status':'PARTIAL'}]}, {'gaps':[{'material':True}]}, {'limitations':['open read judgment']}, {'source_excerpt_reply':{'x':1}}])
def test_all_unresolved_signals_disable_rewriting(update):
    a={**complete(),**update};assert not guard.may_rewrite(a)
    if a['limitations']:guard.verify_publication(a)
    else:
        with pytest.raises(ContractError):guard.verify_publication(a)

def test_nonmaterial_unknown_does_not_force_limited_answer():
    a={**complete(),'gaps':[{'material':False}]};assert guard.may_rewrite(a)

def test_flag_and_policy_validation():
    from semantic_runtime.legal_agent.law_candidates import validate_policy
    assert not guard.enabled({})
    with pytest.raises(ContractError):validate_policy({'assessment_consistency':'true'})
    with pytest.raises(ContractError):validate_policy({'assessment_consistency':True})
