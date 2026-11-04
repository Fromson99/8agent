from copy import deepcopy
import json,pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import decision_projection as dp,output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError
from test_answer_progress import fixture,read_choice

@pytest.mark.parametrize('length,valid',[(0,False),(1,True),(400,True),(401,False)])
def test_rationale_boundary_in_host_and_provider_schema(monkeypatch,length,valid):
    from semantic_runtime.legal_agent.local_gemma import provider_request
    from jsonschema import Draft202012Validator
    value=read_choice();value.pop('answer_progress');value['selections'][0]['missing_need']='가'*length
    inv,data,actions,events,_=fixture(monkeypatch,value);inv.policy['answer_progress_control']=False
    def capture(repo,owner,payload,schema,*args,**kwargs):
        wire=provider_request({'response_format':{'json_schema':{'schema':schema}}})['response_format']['json_schema']['schema']
        assert Draft202012Validator(schema).is_valid(value)==valid
        assert Draft202012Validator(wire).is_valid(value)==valid
        changed=deepcopy(value);changed['selections'][0]['target']='OUTSIDE'
        assert not Draft202012Validator(schema).is_valid(changed)
        raise RuntimeError('boundary verified before tool execution')
    monkeypatch.setattr(oc,'bounded_decision',capture)
    with pytest.raises(RuntimeError,match='boundary verified'):dp.choose_read(inv,data,actions,'boundary')
    assert not any(e[0]=='READ_CHOICE_SELECTED' for e in events)
@pytest.mark.parametrize('repair_succeeds',[True,False])
def test_oversize_reason_repairs_once_and_restart_preserves_budget(tmp_path,monkeypatch,repair_succeeds):
    from test_output_contract_recovery import Journal
    real=oc.bounded_decision
    value=read_choice();inv,d,a,*_=fixture(monkeypatch,value)
    inv.policy['answer_progress_control']=False
    monkeypatch.setattr(oc,'bounded_decision',real)
    path=tmp_path/'journal.sqlite';repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv.s.repo=repo;inv.s.profile={'selection_time_reserve_seconds':20}
    calls=[]
    def invoke(system,payload,schema,phase,timeout):
        calls.append(deepcopy(payload))
        if len(calls)==2:
            assert payload['repair_contract']['same_evidence_scope']
            assert payload['sources']==calls[0]['sources'] and payload['contract_error']
        result=read_choice();result.pop('answer_progress')
        result['selections'][0]['missing_need']='반복'*201 if len(calls)==1 or not repair_succeeds else '위임된 필수 항목을 확인한다.'
        if len(calls)==2:assert payload['rejected_decision']['selections'][0]['missing_need']=='반복'*201
        return result
    inv.invoke=invoke
    if repair_succeeds:
        first=dp.choose_read(inv,d,a,'t');assert first['next_action']=='READ_ARTICLES'
    else:
        with pytest.raises((ProposalError,ValidationError)):dp.choose_read(inv,d,a,'t')
    repo.db.commit();repo.db.close()
    inv.p=json.loads(json.dumps(inv.p));repo=Journal(path);repo.budget=lambda:dict(model_limit=40,model_reserved=2,finalization_reserve=3);inv.s.repo=repo
    if repair_succeeds:assert dp.choose_read(inv,d,a,'t')==first
    else:
        with pytest.raises(oc.OutputContractError):dp.choose_read(inv,d,a,'t')
    assert len(calls)==2
    repo.db.close()


