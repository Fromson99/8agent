"""Scripted reviewer decisions test execution contracts, not model accuracy."""
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from semantic_runtime.legal_agent import reason_decision_review as review, output_contract as output
from semantic_runtime.legal_agent.errors import ContractError, TransportError


class Repo:
    def __init__(self):self.states={};self.events=[]
    def transaction(self):return nullcontext()
    def output_decision_state(self,key):return deepcopy(self.states.get(key))
    def output_decision_event(self,row):self.states[row['decision_key']]=deepcopy(row)
    def event(self,kind,value):self.events.append((kind,deepcopy(value)))


def conflict(proposal, reason='/reason', decision='/decision'):
    return {'decision':'REPAIR','issues':[{'reason_path':'/proposal'+reason,
        'decision_path':'/proposal'+decision,
        'reason_quote':review.resolve(proposal,reason),
        'explanation':'제출한 이유와 선택 필드를 현재 자료로 함께 재판단하세요.'}]}


def run(repo,proposal,invoke,**kwargs):
    return review.review(repo,stage='TEST',context={'original':'실제 근거','revision':1},
        proposal=proposal,binding={'acl':'current'},invoke=invoke,**kwargs)


@pytest.mark.parametrize('stage,decision,reason',[
    ('CONVERSATION','CASE_START','직전 질문의 후속이다.'),
    ('INVESTIGATION','FINISH','답변에 필요한 원문을 더 읽어야 한다.'),
    ('ASSESSMENT','COVERED','핵심 근거가 부족하다.'),
    ('WIKI_COMPARE','SAME','기존 규칙과 충돌한다.'),
    ('ONTOLOGY_USE',[],'이 승인 경로를 이번 주장에 사용했다.')])
def test_five_boundaries_reject_without_changing_the_primary(stage,decision,reason):
    repo=Repo();proposal={'decision':decision,'reason':reason};before=deepcopy(proposal)
    def invoke(prompt,body,schema):
        assert body['stage']==stage and body['proposal']==before
        return conflict(proposal)
    with pytest.raises(review.ReviewConflict) as caught:
        review.review(repo,stage=stage,context={'source':'원문'},proposal=proposal,binding={},invoke=invoke)
    assert caught.value.issues[0]['path']=='/reason'
    assert caught.value.issues[0]['related_paths']==['/decision']
    assert proposal==before and repo.events[0][1]['decision']['decision']=='REPAIR'


@pytest.mark.parametrize('decision,reason',[
    ('FOLLOW','이전 조건을 유지하며 후속 질문을 검토한다.'),
    ('FINISH','읽은 원문을 최종 판단 단계에 전달하며 충분성은 아직 확정하지 않는다.'),
    ('PARTIAL','범위 밖 조건은 미확인으로 남긴다.'),
    ('CONTRADICTION','현재 원문과 충돌하므로 별도 검토로 보존한다.'),
    ([], '승인 경로는 참고만 했고 현재 원문으로 직접 답했다.')])
def test_consistent_partial_and_nonuse_decisions_pass_unchanged(decision,reason):
    p={'decision':decision,'reason':reason};before=deepcopy(p);repo=Repo();calls=[]
    def invoke(*args):calls.append(args);return {'decision':'PASS'}
    assert run(repo,p,invoke)['decision']=={'decision':'PASS'}
    assert run(repo,p,invoke)['reused'] and len(calls)==1 and p==before


def test_owner_reconsiders_and_only_corrected_choice_is_executed():
    repo=Repo();calls=[];executed=[];reviews=[]
    first={'decision':'FINISH','reason':'필수 원문을 읽어야 한다.'}
    second={'decision':'READ','reason':'필수 원문을 읽어야 한다.'}
    def judge(prompt,body,schema):
        reviews.append(body)
        return conflict(first) if len(reviews)==1 else {'decision':'PASS'}
    def primary(payload,attempt):
        calls.append(payload)
        if attempt:
            assert payload['rejected_decision']==first
            assert payload['repair_contract']['validation']['issues'][0]['code']=='REASON_DECISION_CONFLICT'
        return deepcopy(first if not attempt else second)
    def validate(p):run(repo,p,judge)
    value=output.bounded_decision(repo,'primary',{}, {},primary,validate)
    executed.append(value['decision'])
    assert executed==['READ'] and len(calls)==2 and len(reviews)==2
    assert reviews[1]['previous_rejections'][0]['proposal']==first
    assert output.bounded_decision(repo,'primary',{}, {},primary,validate)==second
    assert len(calls)==2 and len(reviews)==2


def test_reason_only_rewrite_is_reviewed_again_with_rejected_reason_not_auto_accepted():
    repo=Repo();seen=[]
    a={'decision':'FINISH','reason':'필수 원문을 읽어야 한다.'}
    b={'decision':'FINISH','reason':'확인이 끝났다.'}
    def judge(prompt,body,schema):
        seen.append(body)
        return conflict(body['proposal'])
    with pytest.raises(review.ReviewConflict):run(repo,a,judge)
    with pytest.raises(review.ReviewConflict):run(repo,b,judge)
    assert seen[1]['previous_rejections'][0]['proposal']==a
    with pytest.raises(review.ReviewUnavailable,match='budget'):
        run(repo,{**b,'reason':'다시 끝났다.'},judge)
    assert len(seen)==2


@pytest.mark.parametrize('bad',[
    {'decision':'PASS','action':'READ'},
    {'decision':'REPAIR','issues':[]},
    {'decision':'REPAIR','issues':[{'reason_path':'/proposal/absent','decision_path':'/proposal/decision',
         'reason_quote':'없는 문장','explanation':'거절'}]},
    {'decision':'REPAIR','issues':[{'reason_path':'/proposal/reason','decision_path':'/proposal/absent',
         'reason_quote':'확인','explanation':'거절'}]},
    {'decision':'REPAIR','issues':[{'reason_path':'/proposal/reason','decision_path':'/proposal/decision',
         'reason_quote':'원래 없는 인용','explanation':'거절'}]}])
def test_invalid_diagnosis_stops_without_primary_repair_or_resend(bad):
    repo=Repo();p={'decision':'READ','reason':'확인'};calls=[]
    def invoke(*a):calls.append(a);return bad
    with pytest.raises(review.ReviewUnavailable):run(repo,p,invoke)
    with pytest.raises(review.ReviewUnavailable):run(repo,p,invoke)
    assert len(calls)==1


def test_unknown_blocks_changed_proposal_and_restart():
    repo=Repo();calls=[]
    def invoke(*args):calls.append(args);raise TransportError('timeout',unknown=True)
    with pytest.raises(TransportError):run(repo,{'decision':'READ','reason':'확인'},invoke)
    restored=Repo();restored.states=deepcopy(repo.states)
    with pytest.raises(review.ReviewUnavailable,match='unknown'):
        run(restored,{'decision':'FINISH','reason':'새 문구'},invoke)
    assert len(calls)==1


@pytest.mark.parametrize('change',['original','revision','acl','proposal'])
def test_changed_binding_never_reuses_old_pass(change):
    repo=Repo();calls=[];p={'decision':'READ','reason':'확인'}
    def invoke(*a):calls.append(a);return {'decision':'PASS'}
    run(repo,p,invoke)
    context={'original':'실제 근거','revision':1};binding={'acl':'current'}
    if change in context:context[change]='changed'
    if change=='acl':binding['acl']='changed'
    if change=='proposal':p['decision']='FINISH'
    review.review(repo,stage='TEST',context=context,proposal=p,binding=binding,invoke=invoke)
    assert len(calls)==2


def test_changed_input_during_review_cannot_receive_pass():
    repo=Repo();p={'decision':'READ','reason':'확인'}
    def invoke(*a):p['decision']='FINISH';return {'decision':'PASS'}
    with pytest.raises(ContractError,match='changed during'):run(repo,p,invoke)
    assert not repo.events


def test_execution_context_change_keeps_one_primary_repair_budget():
    repo=Repo();seen=[]
    def invoke(prompt,body,schema):seen.append(body);return conflict(body['proposal'])
    for action in ('FINISH','READ'):
        with pytest.raises(review.ReviewConflict):
            review.review(repo,stage='TEST',scope={'input':'same'},context={'execution':action},
                proposal={'decision':action,'reason':'확인'},binding={},invoke=invoke)
    assert len(seen[1]['previous_rejections'])==1


def test_common_schema_is_short_and_pass_does_not_echo_a_proposal():
    import json
    assert len(json.dumps(review.SCHEMA))<1800
    v=Draft202012Validator(review.SCHEMA)
    assert v.is_valid({'decision':'PASS'})
    assert not v.is_valid({'decision':'PASS','reason':'good'})


@pytest.mark.parametrize('phase',['memory-reason-decision-review','source-reason-decision-review','memory-final-reason-review'])
def test_shared_review_has_no_gateway_correction_owner(phase):
    assert output.owner_for(phase)=='reason-decision-review'


def test_real_case_journal_repair_keeps_the_existing_goal(tmp_path):
    from test_memory_runtime_v2 import Fake, Wire, command
    from semantic_runtime.legal_agent.corrected_memory import Memory
    fake=Fake();wire=Wire();mem=Memory(tmp_path/'memory.sqlite',fake,wire)
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    first_body={'question':'규정 설명','session_id':'s','request_id':'first'}
    wire.command=command('CASE_START',task='규정 설명',facts=[])
    first=mem.execute(first_body,principal);gid=first['goal_id']
    fake.pipeline=SimpleNamespace(term_agent=SimpleNamespace(profile={'candidate_navigation':{'supervisor_mode':'enforce'}}))
    seen=[];primary=[]
    bad=command('CASE_START',task='후속 설명',facts=[],reason='직전 질문의 후속이다.')
    good=command('RESEARCH_REENTER',target=gid,stage='ASSESS',reason='직전 목표와 원문을 유지해 후속 판단한다.')
    def invoke(prompt,data,schema,phase):
        if phase.startswith('memory-resolve'):
            primary.append(data);return deepcopy(bad if len(primary)==1 else good)
        if phase=='memory-reason-decision-review':
            seen.append(data)
            return conflict(bad,decision='/method_id') if len(seen)==1 else {'decision':'PASS'}
        raise AssertionError(phase)
    mem.invoke=invoke
    body={'question':'그 근거도 설명해 줘','session_id':'s','request_id':'second'}
    result=mem.execute(body,principal)
    assert result['goal_id']==gid and mem.db.execute('SELECT count(*) FROM goal').fetchone()[0]==1
    assert len(primary)==2 and len(seen)==2
    assert mem.execute(body,principal)==result and len(primary)==2
    mem.close()
