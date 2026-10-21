from pathlib import Path
from copy import deepcopy
import importlib.util,json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import decision_projection as dp, output_contract as oc, minimal_output
from semantic_runtime.legal_agent.errors import ProposalError
from test_read_choice_input_preservation import unit
from test_output_contract_recovery import Journal
spec=importlib.util.spec_from_file_location('prior_intent_contracts',Path(__file__).resolve().parents[1]/'adr_0910/test_intent.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
test_return_receipt_survives_restart_and_only_new_progress_reopens=prior.test_return_receipt_survives_restart_and_only_new_progress_reopens
test_actual_return_executor_records_and_rejects_unchanged_second_return=prior.test_actual_return_executor_records_and_rejects_unchanged_second_return

def work(kind='RESEARCH',target='T2',**extra):
    if kind=='RESEARCH':extra.setdefault('queries',['주체 행위'])
    return {'intent':'CONTINUE','work':unit.choice(kind,target,**extra)}
def finish():return {'intent':'FINALIZE','basis_refs':['E1'],'issue_refs':['Q1'],'evidence_sufficient':False,'reason':'확인된 범위와 부족을 평가 단계에 넘긴다'}

def fixture(monkeypatch,value):return prior.fixture(monkeypatch,value)

@pytest.mark.parametrize('value',[work(),finish(),work('RETURN_TO','T7',resume_action='RESEARCH')])
def test_tagged_operation_dispatches_once_without_semantic_inference(monkeypatch,value):
    inv,d,a,shown,out=fixture(monkeypatch,value);v=dp.choose_read(inv,d,a,'tagged')
    assert len(shown)==1 and v['next_action']==('FINISH' if value['intent']=='FINALIZE' else value['work']['choice'])
    assert v['evidence_sufficient'] is False and d['sources']==[{'id':'E1','text':'원문'}]

@pytest.mark.parametrize('value',[{'intent':'FINALIZE','work':work()['work']},{**finish(),'choice':'FOLLOW_CONNECTION'}, {'intent':'CONTINUE',**{k:v for k,v in finish().items() if k!='intent'}}, {'intent':'FINALIZE','choice':'FOLLOW_CONNECTION','missing_need':'원문 확보 완료'},work('RETURN_TO','T7')])
def test_conflicting_or_incomplete_shapes_never_execute(monkeypatch,value):
    inv,d,a,shown,out=fixture(monkeypatch,value)
    with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,d,a,'conflict')
    assert not out and not inv.p.get('executed_compact_choices')

def test_current_provider_codec_has_disjoint_structures_and_explicit_intent(monkeypatch):
    inv,d,a,_,_=fixture(monkeypatch,finish());schemas=[]
    def capture(repo,owner,payload,schema,invoke,expand,**kw):schemas.append(schema);expand(finish());return finish()
    monkeypatch.setattr(oc,'bounded_decision',capture);dp.choose_read(inv,d,a,'wire')
    codec=minimal_output._Node(schemas[0])
    for value in (finish(),work()):
        raw=codec.project(value);assert raw['intent']==value['intent'];assert codec.expand(raw)==value
    bad={**codec.project(finish()),'work':{'choice':'FOLLOW_CONNECTION'}}
    with pytest.raises((ValidationError,ProposalError)):codec.expand(bad)
    raw=codec.project(work());raw.pop('intent')
    with pytest.raises((ValidationError,ProposalError)):codec.expand(raw)

@pytest.mark.parametrize('second_valid',[True,False])
def test_repair_uses_same_sources_once_and_persists_exhaustion(tmp_path,monkeypatch,second_valid):
    original=oc.bounded_decision;inv,d,a,_,_=fixture(monkeypatch,work());monkeypatch.setattr(oc,'bounded_decision',original)
    repo=Journal(tmp_path/'state.sqlite');repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3);inv.s.repo=repo;inv.control=False;inv.left=lambda:120;calls=[]
    def invoke(system,payload,schema,phase,timeout):
        calls.append(deepcopy(payload));return finish() if second_valid and len(calls)==2 else {'intent':'FINALIZE','work':work()['work']}
    inv.invoke=invoke
    if second_valid:
        assert dp.choose_read(inv,d,a,'repair')['next_action']=='FINISH'
        assert dp.choose_read(inv,d,a,'repair')['next_action']=='FINISH'
    else:
        with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,d,a,'repair')
        inv.p=json.loads(json.dumps(inv.p))
        with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,d,a,'repair')
    assert len(calls)==2 and calls[0]['sources']==calls[1]['sources']
    assert calls[1]['repair_contract']['max_attempts']==1


def test_no_extra_review_at_reserve(monkeypatch):
    inv,d,a,shown,_=fixture(monkeypatch,work());inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=35,finalization_reserve=3)
    assert dp.choose_read(inv,d,a,'budget') is None and not shown


def test_repeated_return_blocked_but_continued_research_remains(monkeypatch):
    inv,d,a,shown,_=fixture(monkeypatch,work());inv.p['action_chain']['steps'].append(prior.receipt(inv.p))
    assert dp.choose_read(inv,d,a,'guard')['next_action']=='RESEARCH'
    assert shown[0]['navigation_feedback']['return_without_new_progress_blocked']
    assert not any(x['choice']=='RETURN_TO' for x in shown[0]['tool_options'])


def test_finalize_without_sources_remains_pending(monkeypatch):
    inv,d,a,shown,_=unit.fixture(monkeypatch,{'intent':'FINALIZE','reason':'허용 범위에서 필요한 원문 미확보'},original=False)
    assert dp.choose_read(inv,d,a,'pending')['next_action']=='PENDING'
