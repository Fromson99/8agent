"""The typed retry always refers to the immediately preceding reply in this chat."""
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from semantic_runtime.legal_agent import review_actions as actions


@pytest.fixture
def case(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.create_function('journal_text', 1, lambda text: text)
    db.executescript('''
        CREATE TABLE sw_intake(id, scope, session, event, investigation, status, response);
        CREATE TABLE sw_event(id, aggregate_id, seq);
        INSERT INTO sw_event VALUES ('first','owner/session',1),('second','owner/session',2);
        INSERT INTO sw_intake VALUES ('now','owner','session','second','case','RUNNING',NULL);
    ''')
    db.execute('INSERT INTO sw_intake VALUES (?,?,?,?,?,?,?)',
               ('old','owner','session','first','case','COMPLETED',json.dumps({'goal_id':'goal','revision':4})))
    goal = {'id':'goal','status':'READY','revision':4,'state':{'source_category':'external','document_ids':['law']}}
    repo = SimpleNamespace(db=db, intake_id='now', active_case='case', goal=Mock(return_value=goal))
    action = {'kind':'REVIEW_AGAIN','item_id':'final-review','enabled':True, 'label':actions.REVIEW_LABEL}
    view = {'actions':[{'kind':'REVIEW_AGAIN','item_id':'other','enabled':True},action]}
    load = Mock(return_value=({}, {}, view))
    monkeypatch.setattr(actions,'current_review',load)
    body = {'question':'외규: '+actions.LEGACY_REVIEW_MESSAGE, 'session_id':'case','request_id':'new'}
    yield repo, goal, body, view, load
    db.close()


@pytest.mark.parametrize('reason',['new_session','other_scope','failed','intervening','branch','stale','successful'])
def test_unavailable_offer_never_executes(case, monkeypatch, reason):
    repo,goal,body,view,load = case
    if reason=='new_session': repo.db.execute("UPDATE sw_intake SET session='elsewhere' WHERE id='old'")
    if reason=='other_scope': repo.db.execute("UPDATE sw_intake SET scope='elsewhere' WHERE id='old'")
    if reason=='failed': repo.db.execute("UPDATE sw_intake SET status='FAILED' WHERE id='old'")
    if reason=='intervening': repo.db.execute("UPDATE sw_event SET seq=3 WHERE id='second'")
    if reason=='branch': repo.goal.return_value=None
    if reason=='stale': goal['revision']+=1
    if reason=='successful': view['actions']=[]
    apply = Mock(side_effect=AssertionError('unexpected review'))
    monkeypatch.setattr(actions,'apply_action',apply)
    result = actions.chat_review(repo,body,{'document_ids':['law']})
    assert result['executed']==[] and result['answer']['claims']==[] and result['status']=='CLARIFY'
    apply.assert_not_called()


@pytest.mark.parametrize('text',[actions.REVIEW_LABEL,'외규: '+actions.LEGACY_REVIEW_MESSAGE])
def test_selects_offered_final_review(case,monkeypatch,text):
    repo,goal,body,view,load=case
    body['question']=text
    apply=Mock(return_value={'status':'READY'})
    monkeypatch.setattr(actions,'apply_action',apply)
    assert actions.chat_review(repo,body,{'document_ids':['law']})=={'status':'READY'}
    assert apply.call_args.args[-2] is view['actions'][1]


def test_new_facts_do_not_trigger_the_literal_action(case):
    repo,goal,body,view,load=case
    body['question']+=' 단, 새로운 사실을 추가합니다.'
    assert actions.chat_review(repo,body,{}) is None
    load.assert_not_called()


@pytest.mark.parametrize('delta',[{'question':'내규: 검토 다시 하기'}, {'document_ids':['another']},{'expected_revision':3}])
def test_changed_scope_or_revision_rejected_before_reservation(case,delta):
    repo,goal,body,view,load=case
    body.update(delta)
    with pytest.raises(actions.Conflict):
        actions.apply_action(repo,body,{},goal,{}, {},view,view['actions'][1],{})


@pytest.mark.parametrize('code,stage',[('SCOPE_ACQUISITION_INCOMPLETE','SELECT'),('SCOPE_CLAIM_EVIDENCE','ASSESS')])
def test_restarts_at_recorded_failure_only(case,monkeypatch,code,stage):
    repo,goal,body,view,load=case
    repo.db.execute('CREATE TABLE event(goal,request,utterance,command,kind)')
    repo.context=Mock(return_value={})
    repo.admit=Mock()
    goal['state']['task']='법령 질문'
    assessment={'source_excerpt_reply':True,'model_proposal':{'review_status':'INCOMPLETE',
        'failure_code':'ASSESSMENT_CONTRACT_UNRESOLVED','failure':{'category':'FINAL_READ_REVIEW_INVALID',
        'repairable':True,'issues':[{'code':code}]}}}
    def run(repo,request,principal):
        return {'stage':repo._review_command['stage'],'task':repo._review_question}
    monkeypatch.setattr(actions.Memory,'_execute',run)
    action={**view['actions'][1],'id':'bound-offer'}
    assert actions.apply_action(repo,body,{},goal,{'SELECT':{'payload':{'selected_originals':[]}}},
        assessment,view,action,{})=={'stage':stage,'task':goal['state']['task']}
