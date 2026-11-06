from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
from semantic_runtime.legal_agent.memory_methods import literal_repeat_target
from semantic_runtime.legal_agent.corrected_memory import Conflict

@pytest.fixture
def repeat():
    state={'task':'동일한 질문','facts':[],'queries':['대상'],'document_ids':['doc'],'source_category':'external'}
    goal={'id':'goal','state':state,'status':'READY','command_ready':True,'pending':None,
          'events':[{'id':1,'utterance':'동일한 질문','after':deepcopy(state)}],'revision':2}
    ctx={'utterance':'동일한 질문','goals':[goal]}
    body={'question':'동일한 질문','session_id':'session','request_id':'new','document_ids':['doc']}
    principal={'document_ids':['doc']}
    assess={'disposition':'ANSWER','answer_coverage':'COVERED','claims':[{'text':'기존 답변'}]}
    repo=SimpleNamespace(context=Mock(return_value=ctx),parts=Mock(return_value={'ASSESS':{'payload':assess}}),
        goal=Mock(return_value=goal),committed_response=Mock(return_value={'route_id':3,'answer':'same'}),
        direct_request=Mock(return_value={'status':'CONTINUE'}),executor=SimpleNamespace(model=SimpleNamespace(ensure=lambda:SimpleNamespace(work=SimpleNamespace(event=Mock())))))
    return repo,ctx,goal,assess,body,principal

def test_current_completed_literal_skips_router(repeat):
    repo,ctx,goal,assess,body,principal=repeat
    assert ShortcutCases._execute(repo,body,principal)=={'route_id':3,'answer':'same'}
    repo.direct_request.assert_not_called()
    repo.committed_response.assert_called_once_with(goal,body,principal,'ANSWER_PRESENT')

@pytest.mark.parametrize('change',['failed','uncovered','no_claims','pending','stale','changed_facts','new_question','scope','scenario','not_ready'])
def test_changed_or_incomplete_request_uses_normal_route(repeat,change):
    repo,ctx,goal,assess,body,principal=repeat
    if change=='failed':assess['disposition']='LIMITED_ANSWER'
    if change=='uncovered':assess['answer_coverage']='INSUFFICIENT'
    if change=='no_claims':assess['claims']=[]
    if change=='pending':goal['pending']='ASSESS'
    if change=='stale':goal['command_ready']=False
    if change=='changed_facts':goal['state']['facts']=[{'name':'새 조건','value':'다름'}]
    if change=='new_question':body['question']='다른 질문';ctx['utterance']=body['question']
    if change=='scope':body['document_ids']=['other'];principal['document_ids'].append('other')
    if change=='scenario':goal['state']['scenario_context']={'example':True}
    if change=='not_ready':goal['status']='PENDING'
    assert ShortcutCases._execute(repo,body,principal)=={'status':'CONTINUE'}
    repo.committed_response.assert_not_called()

def test_expected_revision_is_checked_before_display(repeat):
    repo,ctx,goal,assess,body,principal=repeat
    body['expected_revision']=1
    with pytest.raises(Conflict):ShortcutCases._execute(repo,body,principal)
    repo.committed_response.assert_not_called()
