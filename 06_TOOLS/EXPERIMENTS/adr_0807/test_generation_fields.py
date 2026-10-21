from copy import deepcopy
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.model_contract import genos_wire_schema,structured_request
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.decision_projection import prepare
from semantic_runtime.legal_agent.law_navigation import decision_schema
from semantic_runtime.legal_agent import completion_contracts as cc


def schemas():
    view={'presentation_id':'current','laws':[],'basis':[],'branches':[],
        'issues':[{'id':'Q1','request_quote':'기준은?'}], 'completion_contract':cc.V8,
        'investigation_scope':{'request':'기준은?'},'sources':[],'state_version':3}
    actions={'T1':{'id':'T1','action':'RESEARCH','identity':{},'label':'찾기'}}
    canonical=decision_schema(view,actions,set());wire,expand,_=prepare(canonical,view)
    return canonical,wire,expand


def test_generated_wire_never_asks_for_host_quotes_or_current_identifiers():
    canonical,wire,expand=schemas();before=deepcopy(wire)
    body=structured_request(model='test',max_tokens=200,messages=[],schema_name='nav',schema=wire)
    assert 'anyOf' not in provider_request(body)['response_format']['json_schema']['schema']
    for grammar in [body['response_format']['json_schema']['schema'],provider_request(body)['response_format']['json_schema']['schema']]:
        assert 'presentation_id' not in grammar['properties']
        assert 'targets' in grammar['required'] and 'queries' in grammar['required']
        from test_navigation_input_compaction import expand as expand_refs
        item=expand_refs(grammar)['properties']['exploration']['items']
        assert 'request_quote' not in item['properties'] and 'source_quote' not in item['properties']
    assert wire==before
    raw={'next_action':'RESEARCH','targets':['T1'],'queries':['기준'],
        'reason':'규정 찾기','evidence_sufficient':False,'sufficiency_reason':'아직 미확인',
        'exploration':[{'target':'T1','issue_id':'Q1','missing_need':'규정','relation':'DIRECT'}]}
    value=expand(raw);validate(value,canonical)
    assert value['exploration'][0]['request_quote']=='기준은?' and value['presentation_id']=='current'
    bad=deepcopy(raw);bad['exploration'][0]['request_quote']='모델이 바꾼 말'
    with pytest.raises(Exception):expand(bad)


def test_readonly_literals_and_required_fields_are_not_silently_removed():
    s={'type':'object','properties':{'keep':{'type':'string','readOnly':True},'skip':{'type':'string','readOnly':True}},
       'required':['keep'],'enum':[{'properties':{'skip':{'readOnly':True}}}]}
    out=genos_wire_schema(s)
    assert set(out['properties'])=={'keep'} and out['enum']==s['enum']


def test_long_no_model_question_uses_native_query_bound_without_losing_full_issue():
    from types import SimpleNamespace as NS
    from workflow.risk_team_compare_workflow.query_scope import prepare as scope
    from semantic_runtime.legal_agent.workflow_execution import entry_proposal
    q='적용 조건과 예외 및 승인 책임을 원문으로 비교해 주세요. '*20
    p=scope(NS(request={'question':q,'use_llm':False}))
    assert p['issues'][0]['label']==q and len(p['internal_queries'][0])==180
    task={'source_category':'internal','search_hints':p['internal_queries'],
          'issues':[{'id':i['id'],'question':i['internal_task'],'numeric':i['numeric']} for i in p['issues']], 'facts':[]}
    out=entry_proposal(task,q,True);assert out['intent']['issues'][0]['question']==q
