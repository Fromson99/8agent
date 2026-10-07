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


def test_system_request_intake_and_replay(online):
    client,t,p,runtime=online
    body={'question':'안녕하세요','session_id':'greetings','request_id':'g1'}
    first=client.post('/v1/rag/ask',json=body)
    assert first.status_code==200,first.text
    count=len(t.phases)
    second=client.post('/v1/rag/ask',json=body)
    assert second.status_code==200,second.text
    assert len(t.phases)==count
    assert first.json()['run_id']==second.json()['run_id']
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        assert db.execute("SELECT count(*) FROM sw_event WHERE kind='UTTERANCE_RECEIVED'").fetchone()[0]==1
        assert db.execute("SELECT status FROM sw_intake").fetchone()[0]=='COMPLETED'


def test_api_issue_command_idempotence_and_no_review_forgery(online):
    client,t,p,runtime=online
    answer=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s','request_id':'q'}).json()
    case=client.post('/v1/rag/memory/query',json={'query_kind':'investigation','investigation_id':answer['investigation_id']}).json()
    body={'operation':'issue','arguments':{'investigation_id':case['id'],'expected_revision':case['revision'],'question':'별도 자격 쟁점'},'session_id':'s','request_id':'organize1'}
    first=client.post('/v1/rag/memory/command',json=body);assert first.status_code==200,first.text
    assert client.post('/v1/rag/memory/command',json=body).json()==first.json()
    assert client.post('/v1/rag/memory/command',json={**body,'operation':'verification'}).status_code>=400
    changed={**body,'arguments':{**body['arguments'],'question':'다른 질문'}}
    assert client.post('/v1/rag/memory/command',json=changed).status_code==409


def test_native_procedure_uses_existing_source_tool(online):
    import json
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    from semantic_runtime.legal_agent.wiki_execution import CATALOGUE
    from lawrag.pipeline.legal_wiki_compiler import compile_snapshots
    from lawrag.pipeline.wiki_proposal import offered
    client,t,p,runtime=online
    t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[{'name':'holding','value':'8개월'}])
    first=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s','request_id':'initial'})
    assert first.status_code==200,first.text
    r=ShortcutRepository(runtime/'case-memory/cases-v4.sqlite')
    snapshot=r.snapshot(first.json()['investigation_id'],p);segments,sources,_=offered([snapshot])
    source=next(iter(sources.values()))['payload']
    segment=next(k for k,v in segments.items() if v['group']=='sources')
    condition={'op':'duration_lt','field':'holding','value':12,'unit':'month','args':[]}
    output={'units':[{'id':'u1','topic':'승인 조사','question':'모의승인규정 제1조의 승인 대상은?','completeness':'OPEN','unresolved':['법률 검증 필요'],'jurisdiction':'KR','applicable_time':'UNKNOWN'}],
      'members':[{'unit':'u1','segment_id':segment,'role':'SOURCE','reason':'원문 재조회'}],'claims':[],
      'procedures':[{'unit':'u1','id':'p1','preconditions':condition,'steps':[{'id':'read','tool':'read_durable_unit','document_id':source['document_id'],'unit_id':source['coordinate'],'after':[],'purpose':'해당 조문 재조회','result_check':'complete_source'}],'stop_rules':['원문이 완전하지 않으면 중단'],'reentry':'PLAN'}],
      'relations':[],'unassigned_spans':[],'conflicts':[],'completeness_checks':[{'unit':'u1','required_facts':False,'sources':True,'exceptions':False,'corrections':True}]}
    compile_snapshots(r,p,[snapshot],model=lambda *_:output,binding={'model':'scripted','policy_hash':'test','prompt_hash':'test'},catalogue=CATALOGUE,publish=True);r.close()
    client.app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['procedure']=True
    second=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s2','request_id':'reuse'})
    assert second.status_code==200,second.text
    journal=next((runtime/'legal-agent/runs').glob('*/'+second.json()['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        rows=db.execute("SELECT payload_json FROM event WHERE kind='WIKI_PROCEDURE_USED'").fetchall()
    assert rows
    assert json.loads(rows[0][0])['outcome']['status']=='COMPLETE'


def test_reviewed_judgment_rebinds_in_native_publication(online):
    import json
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    from semantic_runtime.legal_agent.wiki_execution import CATALOGUE
    from lawrag.pipeline.legal_wiki_compiler import compile_snapshots
    from lawrag.pipeline.wiki_proposal import offered
    client,t,p,runtime=online
    t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[{'name':'holding','value':'8개월'}])
    first=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s','request_id':'initial'})
    assert first.status_code==200,first.text
    r=ShortcutRepository(runtime/'case-memory/cases-v4.sqlite')
    snapshot=r.snapshot(first.json()['investigation_id'],p);segments,sources,_=offered([snapshot])
    source=next(iter(sources.values()))['payload']
    segment=next(k for k,v in segments.items() if v['group']=='sources')
    condition={'op':'duration_lt','field':'holding','value':12,'unit':'month','args':[]}
    output={'units':[{'id':'u1','topic':'승인 조사','question':'모의승인규정 제1조의 승인 대상은?','completeness':'OPEN','unresolved':['법률 검증 필요'],'jurisdiction':'KR','applicable_time':'UNKNOWN'}],
      'members':[{'unit':'u1','segment_id':segment,'role':'SOURCE','reason':'원문 재조회'}],'claims':[],
      'procedures':[{'unit':'u1','id':'p1','preconditions':condition,'steps':[{'id':'read','tool':'read_durable_unit','document_id':source['document_id'],'unit_id':source['coordinate'],'after':[],'purpose':'해당 조문 재조회','result_check':'complete_source'}],'stop_rules':['원문이 완전하지 않으면 중단'],'reentry':'PLAN'}],
      'relations':[],'unassigned_spans':[],'conflicts':[],'completeness_checks':[{'unit':'u1','required_facts':False,'sources':True,'exceptions':False,'corrections':True}]}
    output['procedures']=[]
    output['units'][0].update(completeness='BOUNDED',unresolved=[])
    output['claims']=[{'unit':'u1','id':'claim1','statement':'원문을 검토한 모의 법률 판단','condition':condition,'exceptions_checked':True,
                      'evidence_refs':[next(iter(sources))],'rationale':'검토 기록','unresolved':[],'document_name':source['document_name'],'quote':source['text'][:15]}]
    bound=compile_snapshots(r,p,[snapshot],model=lambda *_:output,binding={'model':'scripted','policy_hash':'test','prompt_hash':'test'},catalogue=CATALOGUE,publish=True)['units'][0]
    import time
    for kind in ('SOURCE','INTERPRETATION'):
        r.verification(bound['unit_id'],1,p,kind=kind,result='PASS',policy='reviewed-interpretation-v1',verifier='synthetic contract fixture',evidence=['test only'],expires=time.time()+300)
    r.close();t.phases=[]
    client.app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['judgment']=True
    second=client.post('/v1/rag/ask',json={'question':'모의승인규정 대상은?','session_id':'s2','request_id':'reuse'})
    assert second.status_code==200,second.text
    journal=next((runtime/'legal-agent/runs').glob('*/'+second.json()['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        rows=db.execute("SELECT payload_json FROM event WHERE kind='WIKI_JUDGMENT_USED'").fetchall()
    assert rows
    assert not any(phase.startswith('memory-assess') for phase in t.phases)
    assert second.json()['answer']['claims'][0]['text']=='원문을 검토한 모의 법률 판단'
