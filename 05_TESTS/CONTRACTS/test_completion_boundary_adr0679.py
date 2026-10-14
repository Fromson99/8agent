"""Real boundary classes and native decision correction, without model calls."""
from pathlib import Path
import importlib.util
import pytest
from test_investigation_completion_adr0678 import tree,session,inv_for,decision,assess
from test_legal_agent_double_harness import wire
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError,ContractError


def audited_client():
    path=Path(__file__).resolve().parents[2]/'02_BACKEND/lawrag/research/experiment_client.py'
    spec=importlib.util.spec_from_file_location('boundary_experiment_client',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('kind',['native-length','native-filter','audited-length'])
def test_completed_http_but_incomplete_output_is_proposal_failure(session,monkeypatch,kind):
    native,_=session;inv_for(native);calls=[]
    response=wire({'ok':True});response['body_json']['model']=native.gateway.transport.binding['model']
    response['body_json']['choices'][0]['finish_reason']='content_filter' if kind=='native-filter' else 'length'
    error=audited_client().ExperimentFormatError('incomplete response',response=response)
    def send_once(**kwargs):
        calls.append(1)
        if kind=='audited-length':raise error
        return response
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    with pytest.raises(ProposalError):native.structured('synthetic',{},cc.obj({'ok':{'type':'boolean'}}),'memory-assess',30)
    assert len(calls)==1 and native.work.budget()['model_reserved']==1


@pytest.mark.parametrize('kind',['native-policy','adapter-policy','format-model-mismatch'])
def test_policy_and_binding_rejections_do_not_become_repairable_output(session,monkeypatch,kind):
    native,_=session;inv_for(native);calls=[]
    response=wire({'ok':True});response['body_json']['model']=native.gateway.transport.binding['model']
    client=audited_client()
    if kind=='native-policy':error=ContractError('source authorization mismatch')
    elif kind=='adapter-policy':error=client.ExperimentProviderError('reasoning/provider policy mismatch',response=response)
    else:
        response['body_json']['model']='wrong-model'
        error=client.ExperimentFormatError('truncated',response=response)
    def send_once(**kwargs):calls.append(1);raise error
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    with pytest.raises(ContractError):native.structured('synthetic',{},cc.obj({'ok':{'type':'boolean'}}),'memory-assess',30)
    assert len(calls)==1


@pytest.mark.parametrize('repair_succeeds',[True,False])
def test_navigation_owns_one_full_correction_for_wire_failure(session,repair_succeeds):
    native,_=session;inv=inv_for(native);data,actions=inv.view();calls=[]
    card=data['articles'][0];valid=decision(data,'READ_PARENT',card['read_parent_action'])
    def invoke(system,payload,schema,phase,seconds):
        calls.append(phase)
        if len(calls)==1 or not repair_succeeds:raise ProposalError('truncated or invalid JSON')
        assert payload['rejected_decision'] is None
        assert payload['repair_contract']['response_mode']=='FULL_DECISION'
        return valid
    inv.invoke=invoke
    if repair_succeeds:assert inv.request_decision(data,actions,'source-law-navigation-1')==valid
    else:
        with pytest.raises(ProposalError):inv.request_decision(data,actions,'source-law-navigation-1')
        with pytest.raises(ProposalError):inv.request_decision(data,actions,'source-law-navigation-1')
    assert calls==['source-law-navigation-1','source-law-navigation-1-repair']
    assert inv.p['reentry_counters']['CONTRACT_REPAIR']==1


def test_user_fact_cannot_point_to_missing_saved_law():
    gap={'issue_id':'Q1','kind':'MISSING_FACT','reason':'원문 세부 항 미확인','material_id':'B1','material':True,'suggested_action':'REQUEST_FACT'}
    v,o,issues=assess([gap],'PARTIAL');schema=cc.assessment_schema(issues,['B1'],o)
    assert any('cannot target a saved legal material' in e for e in cc.assessment_errors(v,schema,issues))
    gap.update(kind='MISSING_SOURCE',suggested_action='RETURN_TO');v['disposition']='NEEDS_INVESTIGATION'
    assert cc.assessment_errors(v,schema,issues)==[]


def test_missing_source_does_not_request_user_fact():
    gap={'issue_id':'Q1','kind':'MISSING_SOURCE','reason':'관련 원문 미확보','material_id':None,'material':True,'suggested_action':'REQUEST_FACT'}
    v,o,issues=assess([gap],'PARTIAL');schema=cc.assessment_schema(issues,[],o)
    assert any('legal source gap' in e for e in cc.assessment_errors(v,schema,issues))
    gap.update(kind='MISSING_FACT',reason='개별 사건 신청일 미제공')
    assert cc.assessment_errors(v,schema,issues)==[]
