from copy import deepcopy
import json
from types import SimpleNamespace as S
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import answer_progress as ap, decision_projection as dp, output_contract as oc
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_answer_progress import fixture, read_choice, review


def gap_data(data, inv, target='T1'):
    inv.s.context=S(query={'generation_id':'gen'});inv.s.scope=['D1']
    inv.s.matcher=S(unit_fulltext=S(manifest={'index_sha256':'index'}))
    binding={'status':'EXACT','source_ids':['S2'],'document_candidates':['D1'],'pairs':[]}
    data['assessment_gaps']=[{'gap_id':'G1','gap_key':'K1','issue_id':'Q1','material':True,'kind':'MISSING_SOURCE',
        'reason':'검토에서 확인한 필수 세부 원문','missing_target':'문서의 세부 규정',
        'target_binding':binding,'target_binding_hash':digest({'generation':'gen','scope':['D1'],'index':'index'})}]
    inv.p['assessment_gaps']=deepcopy(data['assessment_gaps'])
    data['gap_targets']=[{'gap_id':'G1','read_actions':[target],'navigation_actions':[]}]


def test_review_requirement_preserves_both_opinions_and_one_action_call(monkeypatch):
    value=read_choice();value['answer_progress']=review(status='ANSWERABLE')
    inv,data,actions,events,calls=fixture(monkeypatch,value);gap_data(data,inv)
    result=dp.choose_read(inv,data,actions,'test')
    assert len(calls)==1 and result['next_action']=='READ_ARTICLES'
    assert result['exploration'][0]['missing_need']=='검토에서 확인한 필수 세부 원문'
    state=ap.state_for(inv,data);receipt=next(iter(state['receipts'].values()))
    assert receipt['review']==value['answer_progress'] and receipt['bound_requirement_ids']==['G1']
    assert receipt['effective_goal_states']=={'Q1':'NEEDS_SOURCE'}
    context=ap.context(inv,data)
    assert context['current_goals'][0]['status']=='ANSWERABLE'
    assert context['effective_goal_states']['Q1']=='NEEDS_SOURCE'
    assert context['assessment_requirements'][0]['origin']=='VALIDATED_ASSESS_OPINION'
    assert sum(e[0]=='GOAL_REQUIREMENT_BOUND' for e in events)==1
    assert not any(e[0]=='GOAL_ACTION_ASSEMBLED' for e in events)


@pytest.mark.parametrize('mutation',['other_target','other_issue','tampered_binding','nonmaterial','user_fact','mixed_batch'])
def test_gap_exception_cannot_authorize_unrelated_or_unverified_tool(monkeypatch,mutation):
    value=read_choice();value['answer_progress']=review(status='ANSWERABLE')
    inv,data,actions,events,calls=fixture(monkeypatch,value);gap_data(data,inv)
    gap=data['assessment_gaps'][0]
    if mutation=='other_target':data['gap_targets'][0]['read_actions']=['T2']
    elif mutation=='other_issue':gap['issue_id']='Q2'
    elif mutation=='tampered_binding':gap['target_binding']['source_ids']=['forged']
    elif mutation=='nonmaterial':gap['material']=False
    elif mutation=='user_fact':gap['kind']='MISSING_FACT'
    else:value['selections'].append({**value['selections'][0],'target':'T2'})
    with pytest.raises((ProposalError,ContractError)):
        ap.validate_review(value,{'E1':data['sources'][0]},data['issues'],data=data,inv=inv)
    assert not events and 'answer_progress_reviews' not in inv.p


def test_same_request_resume_preserves_requirement_receipt_and_rejects_changed_gap(tmp_path,monkeypatch):
    from test_output_contract_recovery import Journal
    real=oc.bounded_decision;value=read_choice();value['answer_progress']=review(status='ANSWERABLE')
    inv,data,actions,events,calls=fixture(monkeypatch,value);gap_data(data,inv)
    monkeypatch.setattr(oc,'bounded_decision',real)
    path=tmp_path/'journal.sqlite';repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3)
    inv.s.repo=repo;inv.s.profile={'selection_time_reserve_seconds':20}
    inv.invoke=lambda system,payload,schema,phase,timeout:(calls.append(phase) or deepcopy(value))
    first=dp.choose_read(inv,data,actions,'test');repo.db.commit();repo.db.close()
    inv.p=json.loads(json.dumps(inv.p));repo=Journal(path)
    repo.budget=lambda:dict(model_limit=40,model_reserved=1,finalization_reserve=3);inv.s.repo=repo
    assert dp.choose_read(inv,data,actions,'test')==first and len(calls)==1
    assert repo.db.execute("SELECT count(*) FROM event WHERE kind='GOAL_REQUIREMENT_BOUND'").fetchone()[0]==1
    key=next(iter(ap.state_for(inv,data)['receipts']))
    data['assessment_gaps'][0]['reason']='changed review'
    with pytest.raises(ContractError):ap.record(inv,data,value,key)
    repo.db.close()


def test_current_review_removal_does_not_erase_past_opinions(monkeypatch):
    value=read_choice();value['answer_progress']=review(status='ANSWERABLE')
    inv,data,actions,events,calls=fixture(monkeypatch,value);gap_data(data,inv)
    dp.choose_read(inv,data,actions,'test')
    data['assessment_gaps']=[];data['gap_targets']=[]
    ctx=ap.context(inv,data)
    assert not ctx['assessment_requirements'] and ctx['effective_goal_states']['Q1']=='ANSWERABLE'
    assert ctx['previous_model_opinions'][0]['assessment_requirements'][0]['gap_id']=='G1'
