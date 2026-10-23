from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import answer_progress as ap, decision_projection as dp, output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_answer_progress import fixture, read_choice, review


def terminal_tool(status='ANSWERABLE'):
    value=read_choice();value['answer_progress']=review(status=status)
    return value


@pytest.mark.parametrize('status',['ANSWERABLE','NO_PROGRESS'])
def test_terminal_opinion_assembles_finish_without_changing_meaning(monkeypatch,status):
    value=terminal_tool(status);original=deepcopy(value)
    inv,data,actions,events,calls=fixture(monkeypatch,value)
    result=dp.choose_read(inv,data,actions,'test')
    assert len(calls)==1 and result['next_action']=='FINISH'
    assert result['evidence_sufficient']==(status=='ANSWERABLE')
    assert value==original
    state=ap.state_for(inv,data);receipt=next(iter(state['receipts'].values()))
    assert receipt['review']==original['answer_progress']
    assert receipt['correction']['original_proposal']==original
    assert not receipt['correction']['additional_model_call']
    assert not receipt['correction']['semantic_opinions_changed']
    assert inv.p['executed_compact_choices'][0]['choice']=='FINISH'


@pytest.mark.parametrize('gate',['connection','no_finish_basis','assessment_gap','unknown_evidence','invalid_issue'])
def test_correction_never_bypasses_existing_source_or_completion_gates(monkeypatch,gate):
    value=terminal_tool();inv,data,actions,events,calls=fixture(monkeypatch,value)
    if gate=='connection':data['connection_review']={'required_before_finish':True}
    elif gate=='no_finish_basis':data['basis']=[]
    elif gate=='assessment_gap':data['assessment_gaps']=[{'id':'gap-needs-explicit-resolution'}]
    elif gate=='unknown_evidence':value['answer_progress']['goals'][0]['basis_refs']=['PRIVATE']
    else:value['answer_progress']['goals'][0]['issue_id']='invented'
    if gate in ('unknown_evidence','invalid_issue'):
        with pytest.raises((ContractError,ProposalError)):ap.resolve_action(inv,data,value)
    else:
        resolved,correction=ap.resolve_action(inv,data,value)
        assert resolved==value and correction is None
        with pytest.raises(ProposalError):ap.validate_review(resolved,{s['id']:s for s in data['sources']},data['issues'])
    assert not events and 'answer_progress_reviews' not in inv.p


def test_real_journal_resume_never_requests_a_correction_model_call(tmp_path,monkeypatch):
    from test_output_contract_recovery import Journal
    real=oc.bounded_decision;value=terminal_tool()
    inv,data,actions,events,calls=fixture(monkeypatch,value)
    monkeypatch.setattr(oc,'bounded_decision',real)
    path=tmp_path/'journal.sqlite';repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv.s.repo=repo;inv.s.profile={'selection_time_reserve_seconds':20}
    inv.invoke=lambda system,payload,schema,phase,timeout:(calls.append(phase) or deepcopy(value))
    assert dp.choose_read(inv,data,actions,'test')['next_action']=='FINISH'
    repo.db.commit();repo.db.close();inv.p=json.loads(json.dumps(inv.p))
    repo=Journal(path);repo.budget=lambda:dict(model_limit=40,model_reserved=1,finalization_reserve=3);inv.s.repo=repo
    assert dp.choose_read(inv,data,actions,'test')['next_action']=='FINISH'
    assert calls==['test-read-choice']
    assert len(ap.state_for(inv,data)['receipts'])==1
    assert repo.db.execute("SELECT count(*) FROM event WHERE kind='GOAL_ACTION_ASSEMBLED'").fetchone()[0]==1
    repo.db.close()
