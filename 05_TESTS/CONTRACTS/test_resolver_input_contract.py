"""Synthetic request, ACL, multi-turn and transport contracts; no external calls."""
import copy
import json
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import corrected_memory as m
from semantic_runtime.legal_agent.gateway import ModelGateway
from test_memory_runtime_v2 import memory, command, start
import test_unified_legal_agent as cases
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_structure_first_search import structured_generation
from test_source_prefix_routing import mixed_generation


def assert_no_inventory(value):
    if isinstance(value,dict):
        assert 'allowed_documents' not in value
        assert 'document_ids' not in value
        for child in value.values():assert_no_inventory(child)
    elif isinstance(value,list):
        for child in value:assert_no_inventory(child)


def test_resolve_repair_and_check_preserve_history_wiki_without_inventory(memory):
    cases,executor,wire,send,principal=memory
    gid=start(send)['goal_id']
    context=cases.context('s',principal,'조건을 바꿔줘')
    context['legal_wiki']=[{'topic':'모의 주제','question':'모의 질문'}]
    original=copy.deepcopy(context);calls=[]
    def invoke(system,data,schema,phase):
        calls.append((phase,copy.deepcopy(data),schema))
        assert_no_inventory(data)
        if phase=='memory-resolve':
            return command('RESEARCH_REPLAN',target=gid,document_scope_mode='EXPLICIT',document_ids=['outside-acl'])
        if phase=='memory-resolve-repair':
            return command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'법인'}])
        return {'valid':True,'reason':'synthetic check'}
    cases.invoke=invoke
    result=cases.resolve(context)
    assert result['method_id']=='FACT_UPDATE'
    assert [x[0] for x in calls]==['memory-resolve','memory-resolve-repair','memory-command-check']
    assert calls[0][1]['goals'][0]['id']==gid
    assert calls[0][1]['legal_wiki']==context['legal_wiki']
    assert calls[0][2]['properties']['document_ids']=={'type':'null'}
    assert context==original and context['allowed_documents']
    with pytest.raises(m.MemoryError,match='outside access scope'):
        cases.admit({**result,'document_ids':['outside-acl']},context)


@pytest.mark.parametrize('retired_limit',[None,1024])
def test_large_request_reaches_transport_without_byte_guard(retired_limit):
    binding={'model':'synthetic','trust_zone':'internal'}
    if retired_limit is not None:binding['max_input_bytes']=retired_limit
    sent=[];reserved=[]
    def send_once(*,body,ticket):
        sent.append(body)
        return {'status_code':200,'body_json':{'model':'synthetic',
            'choices':[{'message':{'content':'{"ok":true}'}}]}}
    transport=S(binding=binding,send_once=send_once)
    repo=S(reserve_attempt=lambda *a,**k:reserved.append(a) or 'attempt',
           attempt_sent=lambda *a:None,finish_attempt=lambda *a:'SUCCEEDED')
    context=S(binding={'export_allowed':False},run_id='synthetic-run',remaining=lambda:60)
    gateway=ModelGateway(repo,context,{'model_binding':binding,'max_output_tokens':8192,
        'max_transport_retries':0,'max_schema_repairs':0},{},transport,
        message_protocol=S(schema=lambda _: {},validate=lambda *a:None),
        system='synthetic system',prompts={'investigate':''})
    text='모의 입력입니다. '*20000
    assert gateway.generate('investigate',{'question':text},'synthetic')=={'ok':True}
    assert len(sent)==len(reserved)==1
    assert json.loads(sent[0]['messages'][1]['content'])['view']['question']==text
    assert sent[0]['max_tokens']==8192


@pytest.mark.parametrize('value',['1024','1','invalid'])
def test_retired_byte_env_is_ignored_and_output_tokens_are_retained(monkeypatch,value):
    import service
    for key,val in {'GENOS_BASE_URL':'https://synthetic.invalid',
                    'GENOS_LLM_SERVING_ID':'123','GENOS_LLM_MODEL':'synthetic',
                    'GENOS_LLM_KEY':'synthetic-test-key','GENOS_LLM_MAX_INPUT_BYTES':value,
                    'GENOS_RAG_MAX_OUTPUT_TOKENS':'8192'}.items():monkeypatch.setenv(key,val)
    monkeypatch.delenv('GENOS_LLM_URL',raising=False)
    configured,transport=service._genos_v5_environment_binding()
    assert 'max_input_bytes' not in configured['model_binding']
    assert transport.binding==configured['model_binding']
    assert configured['max_output_tokens']==8192


def test_current_v6_shortcut_multiturn_and_list_route(tmp_path,structured_generation):
    transport=cases.ScriptedTransport()
    transport.binding={**transport.binding,'max_input_bytes':1024}
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d'],'authenticated':True}
    seen=[]
    def inspect(phase,data):
        if phase.startswith('memory-resolve') or phase=='memory-command-check':
            assert_no_inventory(data);seen.append((phase,copy.deepcopy(data)))
    transport.before_return=inspect
    app=create_app(tmp_path,structured_generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'model_binding':transport.binding,'max_model_attempts':40},
        legal_agent_transport=transport,memory_identity=lambda _:principal)
    app.state.pipeline.contracts.pipeline['shortcut_v4']={'features':{'capture':True,'hint':True}}
    try:
        with TestClient(app) as client:
            first=client.post('/v1/rag/ask',json={'question':'모의승인규정 제1조의 승인 대상은?',
                'session_id':'s','request_id':'first'})
            assert first.status_code==200,first.text
            value=first.json();gid=value['goal_id']
            transport.command=command('FACT_UPDATE',target=gid,facts=[{'name':'기간','value':'8개월'}])
            second=client.post('/v1/rag/ask',json={'question':'기간을 8개월로 정정해줘',
                'session_id':'s','request_id':'second'})
            assert second.status_code==200,second.text
            assert second.json()['executed']==['ASSESS','COMPOSE']
            resolver=next(data for phase,data in reversed(seen) if phase=='memory-resolve')
            assert resolver['goals'][0]['id']==gid and resolver['goals'][0]['events']
            count=len(transport.phases)
            listing=client.post('/v1/rag/ask',json={'question':'전체 문서 목록','use_llm':True})
            assert listing.status_code==200,listing.text
            assert '모의승인규정' in listing.json()['answer']['text']
            assert len(transport.phases)==count
            path=tmp_path/'90_RUNTIME/semantic/case-memory/cases-v4.sqlite'
            with sqlite3.connect(path) as db:
                state=json.loads(db.execute('SELECT state FROM goal WHERE id=?',(gid,)).fetchone()[0])
                assert state['document_ids']==['d']
    finally:app.state.pipeline.store.close()


def test_current_v6_internal_external_change_and_exact_restore(tmp_path,mixed_generation):
    transport=cases.ScriptedTransport()
    principal={'user_id':'u','team_id':'risk_team',
        'document_ids':['internal','external'],'authenticated':True}
    captured=[]
    def inspect(phase,data):
        if phase.startswith('memory-resolve') or phase=='memory-command-check':
            assert_no_inventory(data);captured.append((phase,copy.deepcopy(data)))
    transport.before_return=inspect
    transport.command=command('CASE_START',document_scope_mode='AUTHORIZED',
        task='승인 절차는?',facts=[],queries=['승인'])
    app=create_app(tmp_path,mixed_generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},
        legal_agent_transport=transport,memory_identity=lambda _:principal)
    app.state.pipeline.contracts.pipeline['shortcut_v4']={'features':{'capture':True,'hint':True}}
    def ask(client,text,request):
        response=client.post('/v1/rag/ask',json={'question':text,'session_id':'s','request_id':request})
        assert response.status_code==200,response.text
        return response.json()
    try:
        with TestClient(app) as client:
            first=ask(client,'내규: 승인 절차는?','internal')
            gid=first['goal_id']
            assert {s['document_id'] for s in first['assembly']['context']}=={'internal'}
            transport.command=command('RESEARCH_REPLAN',target=gid,source_category='external',queries=['승인'])
            external=ask(client,'외규 기준으로 다시 찾아줘','external')
            assert {s['document_id'] for s in external['assembly']['context']}=={'external'}
            resolver=next(data for phase,data in reversed(captured) if phase=='memory-resolve')
            origin=resolver['goals'][0]['events'][0]['id']
            transport.command=command('STATE_RESTORE',target=gid,restore_event=origin,
                restore_fields=['source_category'])
            restored=ask(client,'처음 내규 기준으로 되돌려줘','restore')
            assert {s['document_id'] for s in restored['assembly']['context']}=={'internal'}
    finally:app.state.pipeline.store.close()
