import sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from test_unified_legal_agent import ScriptedTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_memory_runtime_v2 import command

@pytest.fixture
def online(tmp_path,structured_generation):
    t=ScriptedTransport();p={'user_id':'u','team_id':'risk_team','document_ids':['d'],'authenticated':True}
    app=create_app(tmp_path,structured_generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
                   legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,memory_identity=lambda _:p)
    app.state.pipeline.contracts.pipeline['shortcut_v4']={'features':{'capture':True}}
    with TestClient(app) as client:yield client,t,p,tmp_path/'90_RUNTIME/semantic'

def test_online_intake_response_replay(online):
    client,t,p,runtime=online
    body={'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'r'}
    response=client.post('/v1/rag/ask',json=body)
    assert response.status_code==200,response.text
    value=response.json();before=len(t.phases)
    repeated=client.post('/v1/rag/ask',json=body)
    assert repeated.status_code==200,repeated.text
    assert len(t.phases)==before
    assert repeated.json()['run_id']==value['run_id']
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM sw_trace').fetchone()[0]>=7

def test_online_classification_failure_intake_saved(online):
    client,t,p,runtime=online;t.fail='memory-resolve'
    response=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s','request_id':'r'})
    assert response.status_code>=400
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        assert db.execute('SELECT status FROM sw_intake').fetchone()[0]=='FAILED'
        assert db.execute("SELECT count(*) FROM sw_event WHERE kind='UTTERANCE_RECEIVED'").fetchone()[0]==1

def test_cross_session_correction_reuses_same_goal(online):
    client,t,p,runtime=online
    a=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s1','request_id':'r1'})
    assert a.status_code==200,a.text
    value=a.json();gid=value['goal_id']
    t.command=command('FACT_UPDATE',target=gid,facts=[{'name':'기간','value':'8개월'}])
    b=client.post('/v1/rag/ask',json={'question':'기간을 8개월로 정정','session_id':'s2','request_id':'r2','investigation_id':value['investigation_id']})
    assert b.status_code==200,b.text
    assert b.json()['goal_id']==gid
    assert b.json()['executed']==['ASSESS','COMPOSE']
    queried=client.post('/v1/rag/memory/query',json={'query_kind':'investigations','session_id':'s2','request_id':'q'})
    assert queried.status_code==200,queried.text
    assert len(queried.json()['investigations'])==1
    stale=client.post('/v1/rag/ask',json={'question':'기간 정정','session_id':'s2','request_id':'r3','investigation_id':value['investigation_id'],'investigation_revision':1})
    assert stale.status_code>=400

def test_new_question_same_session_starts_distinct_case(online):
    client,t,p,runtime=online
    first=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s','request_id':'a'})
    assert first.status_code==200,first.text
    body={'question':'별도 C사 모의승인 대상은?','session_id':'s','request_id':'b'}
    second=client.post('/v1/rag/ask',json=body)
    assert second.status_code==200,second.text
    assert first.json()['investigation_id']!=second.json()['investigation_id']
    count=len(t.phases)
    repeat=client.post('/v1/rag/ask',json=body)
    assert repeat.status_code==200,repeat.text
    assert count==len(t.phases)
