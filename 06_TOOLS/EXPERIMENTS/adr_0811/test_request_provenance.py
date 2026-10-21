"""Whole request provenance and semantic planning boundaries; no model calls."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest
from jsonschema import validate, ValidationError

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import completion_v5, completion_v6, investigation_scope
from semantic_runtime.legal_agent import investigation_contracts as ic
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.corrected_memory import Memory, COMMAND
from semantic_runtime.legal_agent.decision_projection import prepare as project_decision
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.memory_rag import INTENT
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.request_entry import accept, bind_task_quotes, schema
from semantic_runtime.legal_agent.workflow_execution import (
    child_execution, entry_proposal, issue_map, register, validate_task,
)
from workflow.risk_team_compare_workflow import query_scope
from workflow.risk_team_compare_workflow.retrieval import discover


def task():
    return {'source_category':'internal','search_hints':['승인 기준'],
        'issues':[{'id':'parent-27','question':'승인 조건','numeric':False},
                  {'id':'parent-4','question':'보고 기한','numeric':True}], 'facts':[]}


def original(size):
    tail='\n마지막 요구: 별표에 규정된 적용 예외까지 확인해 주세요.'
    return '가' * (size-len(tail)) + tail


@pytest.mark.parametrize('size',[2001,6100,15900])
def test_admitted_long_request_survives_entry_and_memory_admission(size):
    request=original(size)
    value=entry_proposal(task(),request,True)
    validate(value,schema(True))
    assert all(issue['request_quote']==request for issue in value['intent']['issues'])
    context={'utterance':request,'goals':[],'knowledge':[],
             'allowed_documents':[],'wiki_links':{}}
    repo=NS(_entry_title_hints={'candidates':[]},
            admit=lambda command,ctx:Memory.admit(None,command,ctx))
    _,command,intent=accept(repo,context,value,scoped=True)
    assert command['task']==request and intent['issues'][-1]['request_quote']==request
    # The generation contract is still compact. Only the exact admitted copy
    # is permitted by the memory admission boundary, not arbitrary longer text.
    assert COMMAND['properties']['task']['maxLength']==600
    changed=deepcopy(command);changed['task']=request+'없는 사용자 요구'
    with pytest.raises(ValidationError):Memory.admit(None,changed,context)


@pytest.mark.parametrize('contract',[completion_v5,completion_v6])
def test_each_live_intent_contract_accepts_complete_request_and_rejects_foreign_quote(contract):
    request=original(9001)
    value=entry_proposal(task(),request,True)['intent']
    value['background_quotes']=[]
    validate(value,contract.intent_schema(ic.intent_schema(INTENT)))
    contract.verify_intent(value,request)
    value['issues'][1]['request_quote']=request+'없는 문구'
    with pytest.raises(Exception):contract.verify_intent(value,request)


def test_quote_option_is_one_complete_request_without_character_partition():
    request=original(8001)
    bound,options=bind_task_quotes(schema(True),request)
    assert options==[{'start_cp':0,'end_cp':len(request),'text':request}]
    value=entry_proposal(task(),request,True)
    validate(value,bound)
    value['intent']['issues'][0]['request_quote']='마지막 요구'
    with pytest.raises(ValidationError):validate(value,bound)


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def test_navigation_restores_complete_bound_request_after_legacy_character_limit():
    request=original(7001)
    view={'completion_contract':cc.V8,
          'issues':[{'id':'Q1','request_quote':request}], 'sources':[],
          'investigation_scope':{'request':request}}
    base=object_schema({'next_action':{'const':'READ_ARTICLES'},
        'targets':{'type':'array','items':{'enum':['T1']}},
        'issue_refs':{'type':'array','items':{'enum':['Q1']}},
        'exploration':investigation_scope.schema(view,{'T1'})})
    canonical={**deepcopy(base),'anyOf':[base]}
    wire,expand,_=project_decision(canonical,view)
    proposal={'next_action':'READ_ARTICLES','targets':['T1'],
              'exploration':[{'target':'T1','issue_id':'Q1','missing_need':'원문 적용 예외',
                              'relation':'DIRECT'}]}
    validate(proposal,wire)
    out=expand(proposal)
    investigation_scope.validate(out,view)
    assert out['exploration'][0]['request_quote']==request
    bad=deepcopy(proposal);bad['exploration'][0]['request_quote']='다른 요청'
    with pytest.raises(Exception):expand(bad)


@pytest.mark.parametrize('question,numeric',[
    ('비율이라는 문서 제목의 개정 이력만 알려 주세요.',False),
    ('두 규정의 필요 준비금이 자산의 두 배와 세 배로 다른지 비교해 주세요.',True),
])
def test_numeric_is_the_semantic_issue_decision_not_a_keyword_gate(question,numeric):
    value={'issues':[{'id':'I1','label':'요구한 규정 항목','numeric':numeric,
                     'internal_task':'내규 요구 항목','external_task':'외규 요구 항목'}],
           'internal_queries':['요구 항목'],'external_queries':['요구 항목'],
           'scope_note':'질문의 실제 요구','facts':[],'missing_user_facts':[]}
    calls=[]
    def decide(stage,view,rule,prompt,check):
        calls.append(stage);validate(value,rule);check(value);return value
    ctx=NS(request={'question':question,'as_of':None,'use_llm':True},model=NS(decide=decide))
    assert query_scope.prepare(ctx)['issues'][0]['numeric'] is numeric
    assert calls==['INTAKE']


def test_system_only_path_preserves_full_request_without_making_search_or_numeric_claims():
    request=original(15001)+' 비율'
    ctx=NS(request={'question':request,'as_of':None,'use_llm':False},
           model=NS(decide=lambda *a:pytest.fail('system-only path called model')))
    scope=query_scope.prepare(ctx)
    assert scope['internal_queries']==scope['external_queries']==[]
    assert scope['issues'][0]['label']==scope['issues'][0]['internal_task']==scope['issues'][0]['external_task']==request
    assert scope['issues'][0]['numeric'] is False and '판단은 수행하지 않아' in scope['scope_note']
    calls=[]
    def call(action,call_id):
        calls.append(action);validate_task(action['args']['task'],request)
        return {'status':'partial','unresolved':[],'evidence_ids':[]}
    ctx.rag=NS(call=call);ctx.repo=NS(save=lambda _:None)
    state={'scope':scope,'history':[],'gaps':[]}
    discover(ctx,state,'internal')
    assert calls[0]['args']['question']==request
    assert calls[0]['args']['task']['issues'][0]['question']==request
    assert calls[0]['args']['task']['search_hints']==[]


def test_parent_issue_map_is_saved_in_child_journal_and_survives_reopen(tmp_path):
    request=original(3001)
    query={'id':'query','question':request,'scope':{'document_version_ids':['doc']}}
    parent_context=RequestContext.create(query,{'question':request},{'documents':['doc']},60)
    child_context=RequestContext.create(query,{'question':request},{'documents':['doc']},60)
    profile={'max_model_attempts':4,'finalization_reserve':1,'max_tool_actions':8}
    parent=WorkRepository(tmp_path/'parent.sqlite',parent_context,profile)
    child=WorkRepository(tmp_path/'child.sqlite',child_context,profile)
    supplied=task();before=deepcopy(supplied)
    try:
        with child_execution(parent,parent_context,'call-1',{'doc'},task=supplied):register(child)
        expected=issue_map(before)
        row=child.db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'").fetchone()
        value=json.loads(row[0])
        assert value['issue_map']==expected=={'Q1':'parent-27','Q2':'parent-4'}
        assert value['task']==before and value['task_hash']==digest(before)
        assert value['parent_request_hash']==digest(request) and value['call_id']=='call-1'
    finally:
        child.close();parent.close()
    reopened=WorkRepository(tmp_path/'child.sqlite')
    try:
        saved=json.loads(reopened.db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'").fetchone()[0])
        assert saved==value
    finally:reopened.close()


def test_parent_task_does_not_accept_overlong_search_phrase_or_duplicate_identity():
    value=task();value['search_hints']=['가'*181]
    with pytest.raises(ContractError):validate_task(value,original(4001))
    value=task();value['issues'][1]['id']=value['issues'][0]['id']
    with pytest.raises(ContractError):validate_task(value,original(4001))
