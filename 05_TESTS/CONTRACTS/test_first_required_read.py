from copy import deepcopy
import json
import pytest
from semantic_runtime.legal_agent import answer_progress as ap, decision_projection as dp
from test_answer_progress import fixture, read_choice
from test_assessment_goal_binding import gap_data


def ready(monkeypatch):
    value=read_choice();inv,data,actions,events,calls=fixture(monkeypatch,value)
    gap_data(data,inv)
    dp.choose_read(inv,data,actions,'test')
    value['answer_progress']['goals'][0]['previous_effect']='NO_CHANGE'
    data['presentation_id']='P2';dp.choose_read(inv,data,actions,'test')
    data['presentation_id']='P3'
    return value,inv,data,actions,events,calls


def test_first_required_body_read_is_not_preempted_and_never_regranted(monkeypatch):
    value,inv,data,actions,events,calls=ready(monkeypatch)
    assert dp.choose_read(inv,data,actions,'test')['next_action']=='READ_ARTICLES'
    state=ap.state_for(inv,data)
    assert state['unchanged_steps_by_issue']['Q1']==2
    assert len(state['first_required_read_grants'])==1
    assert state['history'][-1]['review']==value['answer_progress']
    inv.p=json.loads(json.dumps(inv.p));data['presentation_id']='P4'
    with pytest.raises(ap.ProgressHandoff):dp.choose_read(inv,data,actions,'test')
    assert ap.state_for(inv,data)['unchanged_steps_by_issue']['Q1']==3
    assert sum(e[0]=='FIRST_REQUIRED_READ_ALLOWED' for e in events)==1


@pytest.mark.parametrize('status',['COMPLETED','FAILED'])
def test_prior_body_attempt_counts_even_when_failed_or_no_gap_id(monkeypatch,status):
    value,inv,data,actions,events,calls=ready(monkeypatch)
    data['gap_action_receipts']=[{'id':'R1','action':'READ_ARTICLES','status':status,'gap_ids':[],
        'targets':[{'identity':{'document_id':'D1'}}]}]
    with pytest.raises(ap.ProgressHandoff):dp.choose_read(inv,data,actions,'test')
    assert not any(e[0]=='FIRST_REQUIRED_READ_ALLOWED' for e in events)


def test_structure_attempt_is_not_body_attempt_and_replay_does_not_duplicate_grant(monkeypatch):
    value,inv,data,actions,events,calls=ready(monkeypatch)
    data['gap_action_receipts']=[{'id':'R1','action':'SEARCH_STRUCTURE','status':'COMPLETED','gap_ids':['G1'],
        'targets':[{'identity':{'document_id':'D1'}}]}]
    first=dp.choose_read(inv,data,actions,'test')
    assert dp.choose_read(inv,data,actions,'test')==first
    assert sum(e[0]=='FIRST_REQUIRED_READ_ALLOWED' for e in events)==1


@pytest.mark.parametrize('mutation',['unrelated_document','missing_action','nonmaterial','user_fact','budget'])
def test_allowance_never_bypasses_target_or_budget(monkeypatch,mutation):
    value,inv,data,actions,events,calls=ready(monkeypatch)
    if mutation=='unrelated_document':actions['T1']['identity']['document_id']='OTHER'
    elif mutation=='missing_action':actions={}
    elif mutation in ('nonmaterial','user_fact'):
        gap=data['assessment_gaps'][0]
        if mutation=='nonmaterial':gap['material']=False
        else:gap['kind']='MISSING_FACT'
        inv.p['assessment_gaps']=deepcopy(data['assessment_gaps'])
    else:
        before=len(calls);inv.s.repo.budget=lambda:dict(model_limit=14,model_reserved=11,finalization_reserve=3)
        assert dp.choose_read(inv,data,actions,'test') is None and len(calls)==before
        return
    assert not ap.first_required_read_grants(data,value,actions,ap.state_for(inv,data))


def test_mixed_batch_does_not_use_one_gap_to_continue_unrelated_reads(monkeypatch):
    value,inv,data,actions,events,calls=ready(monkeypatch)
    actions['T2']={'action':'READ_ARTICLES','identity':{'document_id':'OTHER'}}
    value['selections'].append({**value['selections'][0],'target':'T2'})
    assert not ap.first_required_read_grants(data,value,actions,ap.state_for(inv,data))
