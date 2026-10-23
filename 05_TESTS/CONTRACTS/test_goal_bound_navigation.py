"""Goal/action consistency and stored opinions on the actual decision path."""
from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import answer_progress as ap, decision_projection as dp
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_answer_progress import fixture, read_choice, review


def two_goals(monkeypatch):
    value=read_choice()
    answered=review(status='ANSWERABLE')['goals'][0];answered['issue_id']='Q2'
    value['answer_progress']['goals'].append(answered)
    inv,data,actions,events,calls=fixture(monkeypatch,value)
    data['issues'].append({'id':'Q2','request_quote':'두 번째 요구'})
    return value,inv,data,actions,events,calls


def test_all_original_goals_update_in_one_call_and_reason_is_assembled(monkeypatch):
    value,inv,data,actions,events,calls=two_goals(monkeypatch)
    result=dp.choose_read(inv,data,actions,'test')
    assert len(calls)==1
    assert result['issue_refs']==['Q1']
    assert result['reason']==value['answer_progress']['goals'][0]['material_need']
    assert ap.state_for(inv,data)['goals']==value['answer_progress']['goals']
    assert calls[0]['answer_progress_context']['original_issues']==data['issues']
    assert 'missing_need' not in value['selections'][0]


@pytest.mark.parametrize('change',['answered_target','omitted','duplicate','invented','premature_finish','lost_goal','false_sufficiency','lost_evidence'])
def test_conflicting_goal_decisions_do_not_commit_or_execute(monkeypatch,change):
    value,inv,data,actions,events,calls=two_goals(monkeypatch)
    goals=value['answer_progress']['goals']
    if change=='answered_target':value['selections'][0]['issue_id']='Q2'
    elif change=='omitted':goals.pop()
    elif change=='duplicate':goals[1]['issue_id']='Q1'
    elif change=='invented':goals[1]['issue_id']='Q3'
    else:
        value.pop('selections');value.update(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1','Q2'],reason='현재 범위 종료',evidence_sufficient=False)
        if change!='premature_finish':goals[0]['status']='NO_PROGRESS'
        if change=='lost_goal':value['issue_refs']=['Q2']
        if change=='false_sufficiency':value['evidence_sufficient']=True
        if change=='lost_evidence':
            data['sources'].append({'id':'E2','document_id':'D1','source_id':'S2','text':'또 다른 원문'})
            data['basis'].append({'id':'E2','branch_id':'B2'})
            goals[1]['basis_refs']=['E2']
    with pytest.raises((ProposalError,ValidationError,ContractError)):
        dp.choose_read(inv,data,actions,'test')
    assert 'answer_progress_reviews' not in inv.p and not events


def test_partially_answerable_finish_keeps_every_goal_and_original(monkeypatch):
    value,inv,data,actions,events,calls=two_goals(monkeypatch)
    value.pop('selections');value.update(choice='FINISH',basis_refs=['E1'],issue_refs=['Q1','Q2'],reason='미확인 원문 보존',evidence_sufficient=False)
    value['answer_progress']['goals'][0]['status']='NO_PROGRESS'
    result=dp.choose_read(inv,data,actions,'test')
    assert result['next_action']=='FINISH' and not result['evidence_sufficient']
    assert result['issue_refs']==['Q1','Q2']
    assert ap.state_for(inv,data)['goals'][0]['material_need']
    assert len(calls)==1


@pytest.mark.parametrize('tamper',['goal','counter','receipt','history'])
def test_resumed_goal_state_tampering_fails_closed(monkeypatch,tamper):
    value,inv,data,actions,events,calls=two_goals(monkeypatch)
    dp.choose_read(inv,data,actions,'test')
    inv.p=json.loads(json.dumps(inv.p))
    state=ap.state_for(inv,data)
    if tamper=='goal':state['goals'][0]['status']='ANSWERABLE'
    elif tamper=='counter':state['unchanged_steps_by_issue']['Q1']=0.5
    elif tamper=='receipt':next(iter(state['receipts'].values()))['handoff']=True
    else:state['history']=[]
    with pytest.raises(ContractError,match='hash mismatch'):ap.context(inv,data)
    assert len(calls)==1


def test_new_original_does_not_reset_model_reported_no_answer_change(monkeypatch):
    value,inv,data,actions,events,calls=two_goals(monkeypatch)
    dp.choose_read(inv,data,actions,'1')
    for r in value['answer_progress']['goals']:r['previous_effect']='NO_CHANGE'
    data['presentation_id']='P2';data['sources'][0]['text']+='新 원문'
    dp.choose_read(inv,data,actions,'2')
    inv.p=json.loads(json.dumps(inv.p));data['presentation_id']='P3';data['sources'][0]['text']+='다른 원문'
    with pytest.raises(ap.ProgressHandoff):dp.choose_read(inv,data,actions,'3')
    assert len(calls)==3
    assert len(inv.p['executed_compact_choices'])==2
    assert ap.state_for(inv,data)['unchanged_steps_by_issue']['Q1']==2


def test_initial_scope_review_still_required_with_goal_progress_enabled(monkeypatch):
    from semantic_runtime.legal_agent import output_contract as oc
    value=read_choice();inv,data,actions,events,calls=fixture(monkeypatch,value)
    data['connection_review']={'required_before_finish':True,'status':'SELECT_SCOPE'}
    def choose(repo,phase,payload,schema,invoke,check,**kw):
        assert 'FINISH' not in {r['properties']['choice']['const'] for r in schema['anyOf']}
        assert all('answer_progress' in r['required'] for r in schema['anyOf'])
        check(value);return deepcopy(value)
    monkeypatch.setattr(oc,'bounded_decision',choose)
    assert dp.choose_read(inv,data,actions,'test')['next_action']=='READ_ARTICLES'
