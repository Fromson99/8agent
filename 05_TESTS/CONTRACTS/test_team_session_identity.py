"""Session-only ingress and durable consumers; synthetic sources, zero remote calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime import session_identity as identity
from semantic_runtime.legal_agent import corrected_memory as memory
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from test_risk_team_compare_workflow import generation, Scripted, ROOT, BINDING, DEFAULT_PROFILE
from test_memory_runtime_v2 import Fake, Wire, command
from test_unified_legal_agent import unified,ok
from test_structure_first_search import structured_generation

BODY={'question':'대사: 모의 승인 기준','team_id':'risk_team','session_id':'chat/한글:one',
      'request_id':'request-one','use_llm':False}


@pytest.fixture(autouse=True)
def no_user_environment(monkeypatch):
    for key in ('WORKFLOW_USER_ID','TEAM_ID','GENOS_MEMORY_ENABLED','GENOS_GENERATION','GENOS_DATA_ROOT'):
        monkeypatch.delenv(key,raising=False)


def app_at(tmp_path,generation,**kwargs):
    implementation=kwargs.pop('implementation','legal-agent-unified-v6')
    profile={**DEFAULT_PROFILE,'model_binding':BINDING}
    if implementation=='legal-agent-unified-v6':
        from lawrag.pipeline.fulltext_stage import derive
        selected=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-agent-rag-v6']
        config=next(n['parameters']['term_agent'] for n in selected['nodes'] if 'term_agent' in n.get('parameters',{}))
        profile=json.loads((ROOT/config['legal_agent']['profile']['path']).read_text())
        profile['model_binding']=BINDING
        derive(generation,tmp_path/'indexed',workers=1);generation=tmp_path/'indexed'
    return create_app(tmp_path,generation,contracts_root=ROOT,workspace_root=ROOT,
        runtime_root=tmp_path/'runtime',release={'mode':'genos-generation'},
        provider=object(),implementation=implementation,
        legal_agent_profile=profile,
        legal_agent_transport=Scripted(),**kwargs)


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value


@pytest.mark.parametrize('user',[None,'one','two','anonymous',''])
def test_user_has_no_identity_effect(user):
    expected=identity.bind(BODY)
    assert identity.bind({**BODY,'user_id':user})==expected


@pytest.mark.parametrize('field,value',[('session_id',None),('session_id',''),('session_id','sess-anonymous'),
    ('session_id','x'*257),('session_id','s\nother'),('team_id','risk'),('team_id',None)])
def test_invalid_selectors_fail_without_anonymous_fallback(field,value):
    with pytest.raises(ValueError):identity.bind({**BODY,field:value})


def test_exact_session_and_team_namespaces():
    bodies=[{**BODY,'session_id':s,'team_id':t}
            for s in ('s/a','s-a','x'*200+'a','x'*200+'b') for t in ('risk_team','financial_team')]
    values=[identity.bind(b)[0] for b in bodies]
    assert len({b['session_id'] for b in values})==8
    assert len({b['user_id'] for b in values})==8


def test_real_workflow_api_duplicate_status_resume_and_integrity(tmp_path,generation):
    app=app_at(tmp_path,generation)
    with TestClient(app) as api:
        result=api.post('/v1/rag/ask',json=BODY)
        assert result.status_code==200,result.text
        value=result.json();assert value['status']=='partial'
        assert value['session_id']==BODY['session_id']
        path=tmp_path/'runtime/workflows'/value['run_id']/'journal.sqlite'
        with sqlite3.connect(path) as db:
            before=db.execute('SELECT revision,request_json,binding_hash FROM workflow_state').fetchone()
        stored=json.loads(before[1]);assert stored['principal']['user_id'].startswith('session:')
        repeated=api.post('/v1/workflows/run',json={**BODY,'user_id':'changed-login'}).json()
        assert repeated['run_id']==value['run_id'] and repeated['usage']==value['usage']
        params={k:BODY[k] for k in ('team_id','session_id')}
        status=api.get('/v1/workflows/runs/'+value['run_id'],params=params)
        assert status.status_code==200,status.text
        assert status.json()['answer']==value['answer']
        assert api.get('/v1/workflows/runs/'+value['run_id'],params={**params,'session_id':'other'}).status_code==404
        resume={**params,'run_id':value['run_id'],'expected_revision':before[0]}
        response=api.post('/v1/workflows/resume',json=resume)
        assert response.status_code==200,response.text
        assert response.json()['usage']==value['usage']
        assert api.post('/v1/workflows/resume',json={**resume,'expected_revision':0}).status_code==409
        assert api.post('/v1/workflows/run',json={**BODY,'question':'대사: 다른 입력'}).status_code==409
        with sqlite3.connect(path) as db:
            after=db.execute('SELECT revision,request_json,binding_hash FROM workflow_state').fetchone()
            assert before==after
            db.execute("UPDATE workflow_state SET checkpoint_hash='tampered'")
        assert api.get('/v1/workflows/runs/'+value['run_id'],params=params).status_code==409
    app.state.pipeline.store.close()


def test_workflow_missing_session_and_document_scope(tmp_path,generation,monkeypatch):
    app=app_at(tmp_path,generation)
    with TestClient(app) as api:
        assert api.post('/v1/workflows/run',json={k:v for k,v in BODY.items() if k!='session_id'}).status_code==422
        assert api.post('/v1/workflows/run',json={**BODY,'document_ids':['hidden']}).status_code==403
        monkeypatch.setenv('TEAM_ID','financial_team')
        assert api.post('/v1/workflows/run',json=BODY).status_code==422
    assert not (tmp_path/'runtime/workflows').exists()
    app.state.pipeline.store.close()


def test_memory_real_api_multiturn_reopen_duplicate_and_team_isolation(tmp_path,generation,monkeypatch):
    from semantic_runtime import team_scope
    monkeypatch.setattr(team_scope,'select_documents',lambda store,team:['inside'])
    wire=Wire();wire.command=command('CASE_START',task='모의 보고',facts=[])
    captured=[]
    def factory(p,r,body,principal):
        captured.append((body,principal))
        path=tmp_path/'runtime/corrected-memory/memory-v2.sqlite';path.parent.mkdir(parents=True,exist_ok=True)
        return memory.Memory(path,Fake(),wire)
    body={**BODY,'question':'모의 질문','use_llm':True,'memory':True}
    app=app_at(tmp_path,generation,memory_factory=factory,implementation='legal-agent-tools-v5')
    with TestClient(app) as api:
        first=api.post('/v1/rag/ask',json=body);assert first.status_code==200,first.text
        result=first.json();gid=result['goal_id']
        duplicate=api.post('/v1/rag/ask',json={**body,'user_id':'irrelevant'})
        assert duplicate.status_code==200,duplicate.text
        assert {k:v for k,v in duplicate.json().items() if k!='execution_stats'}=={k:v for k,v in result.items() if k!='execution_stats'}
        wire.command=command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])
        second=api.post('/v1/rag/ask',json={**body,'request_id':'next'})
        assert second.status_code==200,second.text
        assert second.json()['goal_id']==gid and second.json()['executed']==['ASSESS','COMPOSE']
        assert api.post('/v1/rag/ask',json={**body,'request_id':'stale','expected_revision':1}).status_code==409
        assert api.post('/v1/rag/ask',json={**body,'question':'different'}).status_code==409
        wire.command=command('CASE_START',task='모의 보고',facts=[])
        for change in ({'session_id':'other'},{'team_id':'financial_team'}):
            other=api.post('/v1/rag/ask',json={**body,**change})
            assert other.status_code==200,other.text
            assert other.json()['goal_id']!=gid
    assert captured[0][0]==captured[1][0]
    app.state.pipeline.store.close()


def test_legacy_history_is_preserved_and_not_silently_restarted(tmp_path):
    path=tmp_path/'corrected-memory/memory-v2.sqlite'
    path.parent.mkdir(parents=True)
    mem=memory.Memory(path,Fake(),Wire());mem.identity(BODY['session_id'],{'user_id':'old-user','team_id':'risk_team'})
    mem.close();before=path.read_bytes()
    with pytest.raises(ValueError,match='SESSION_LEGACY_BINDING'):identity.reject_legacy(tmp_path,BODY)
    assert path.read_bytes()==before
    identity.reject_legacy(tmp_path,{**BODY,'session_id':'new-session'})


def test_shortcut_consumer_reopen_and_no_cross_session_access(tmp_path):
    body,p=identity.bind({**BODY,'question':'모의','use_llm':True,'document_ids':['inside']})
    p={**p,'document_ids':['inside'],'authenticated':True}
    path=tmp_path/'shortcut.sqlite';repo=ShortcutRepository(path)
    intake=repo.intake(body,p);case=repo.connect(intake['id'],p);repo.close()
    repo=ShortcutRepository(path)
    assert repo.intake({**body},p)['id']==intake['id']
    assert repo.connect(intake['id'],p)['id']==case['id']
    other,op=identity.bind({**BODY,'session_id':'other'})
    with pytest.raises(memory.MemoryError):repo.investigation(case['id'],{**op,'document_ids':['inside'],'authenticated':True})
    with pytest.raises(memory.MemoryError):repo.investigation(case['id'],{**p,'document_ids':[]})
    with pytest.raises(memory.Conflict):repo.intake({**body,'question':'changed'},p)
    repo.close()


def test_workflow_editor_and_real_service_entry(tmp_path,generation,monkeypatch):
    app=app_at(tmp_path,generation)
    workflow=module('session_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    service=module('session_service',ROOT/'service.py')
    monkeypatch.setattr(service,'application',lambda:app)
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','1')
    payload=workflow._request_body(BODY['question'],{'chatId':BODY['session_id'],'team_id':'risk_team',
                                                    'request_id':BODY['request_id'],'use_llm':False})
    assert 'user_id' not in payload and payload['session_id']==BODY['session_id']
    result=asyncio.run(service.service({},payload))
    assert result['status']==200,result
    status=asyncio.run(service.service({},dict(API_TYPE='WORKFLOW_STATUS',run_id=result['body']['run_id'],
                                             team_id='risk_team',session_id=BODY['session_id'])))
    assert status['status']==200,status
    assert status['body']['usage']==result['body']['usage']
    assert workflow._session_id({'chatId':'s/a'})!=workflow._session_id({'chatId':'s-a'})
    with pytest.raises(ValueError):workflow._request_body('질문',{'team_id':'risk_team'})
    app.state.pipeline.store.close()


@pytest.mark.parametrize('exhausted',[False,True])
def test_interrupted_workflow_resumes_same_checkpoint_budget_and_deadline(tmp_path,generation,monkeypatch,exhausted):
    import importlib
    app=app_at(tmp_path,generation);runtime=app.state.workflow_runtime
    package=runtime.__class__.__module__.rsplit('.',1)[0]
    repo=importlib.import_module(package+'.repository').Repository
    save=repo.save;stopped=[]
    def interrupted(self,checkpoint,**kw):
        value=save(self,checkpoint,**kw)
        if checkpoint['stage']=='FIND_EXTERNAL' and not stopped:
            stopped.append(True);raise KeyboardInterrupt('synthetic interruption after durable source receipt')
        return value
    monkeypatch.setattr(repo,'save',interrupted)
    body,p=identity.bind({**BODY,'workflow_id':'risk_team_compare_workflow'})
    p=runtime.services.principal(p['user_id'],p['team_id'])
    with pytest.raises(KeyboardInterrupt):runtime.execute(body,p)
    journal=next(runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
        used=db.execute('SELECT model_reserved,tool_used FROM budget').fetchone()
        calls=db.execute("SELECT call_id FROM workflow_call WHERE status='COMPLETE'").fetchall()
        if exhausted:db.execute('UPDATE budget SET tool_used=tool_limit')
    # Reload the API/runtime while retaining the same store and code binding.
    from semantic_runtime.workflow_bridge import install
    install(app,app.state.pipeline,tmp_path/'runtime',{'mode':'genos-generation'},None)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/resume',json={'run_id':journal.parent.name,
            'team_id':BODY['team_id'],'session_id':BODY['session_id'],'expected_revision':revision})
        assert response.status_code==200,response.text
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline
        later=db.execute('SELECT model_reserved,tool_used FROM budget').fetchone()
        assert all(a>=b for a,b in zip(later,used))
        assert all(db.execute('SELECT count(*) FROM workflow_call WHERE call_id=?',row).fetchone()[0]==1 for row in calls)
    app.state.pipeline.store.close()


@pytest.mark.parametrize('path',['/v1/workflows/run','/v1/rag/ask'])
def test_configured_authority_failure_never_falls_back(tmp_path,generation,path):
    app=app_at(tmp_path,generation,memory_identity=lambda request:None)
    with TestClient(app) as api:
        assert api.post(path,json=BODY).status_code==403
    app.state.pipeline.store.close()


def test_direct_chat_session_without_user_and_preserved_ad_scope(monkeypatch):
    from semantic_runtime import chat_adapter
    body=chat_adapter.request_body({'question':'모의','team_id':'risk_team','chatId':'x/y','request_id':'r'},'모의')
    assert body['session_id']=='x/y' and body['team_id']=='risk_team' and 'user_id' not in body
    assert body['ad_session_id']=='x/y'


def test_current_v6_multiturn_answer_correction_duplicate_without_login(unified):
    client,send,t,p,runtime=unified
    p.pop('user_id')
    first=ok(send(request_id='first'));gid=first['question_id'];calls=len(t.phases)
    duplicate=ok(send(request_id='first',user_id='ignored-login'))
    assert duplicate['question_id']==gid and duplicate['answer']==first['answer']
    assert len(t.phases)==calls
    second=ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}]),request_id='second'))
    assert second['question_id']==gid and second['executed']==['ASSESS','COMPOSE']
    assert second['answer']['text']
    # Current query/command endpoints must still honor the AD gate.
    from fastapi.testclient import TestClient
    with TestClient(client.app) as plain:
        for path in ('query','command'):
            response=plain.post('/v1/rag/memory/'+path,json={'team_id':'risk_team','session_id':'s','request_id':'no-ad'})
            assert response.status_code==403,response.text
