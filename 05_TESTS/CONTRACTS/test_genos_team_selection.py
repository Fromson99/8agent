"""Synthetic workflow -> API -> v5 scope contracts; no network/model evaluation."""
import asyncio
import importlib.util
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.team_scope import document_teams
from semantic_runtime.legal_agent.errors import ProposalError
from test_document_release import source, ROOT
from test_legal_agent_v5 import app_for
from test_tool_exploration_v3 import tool


@pytest.fixture
def team_generation(tmp_path, term_glossary):
    raw=source(tmp_path/'raw.sqlite',[
        ('risk','모의위험규정',['영업일에 승인한다. 「모의재무규정」 제1조에 따른다.']),
        ('finance','모의재무규정',['영업일에 재무팀만 검토한다.']),
        ('shared','공통모의자료',['영업일의 공통자료이다.']),
        ('duplicate','중복모의자료',['두 팀이 같은 원문을 보유한다.'])])
    with sqlite3.connect(raw) as db:
        for did,metadata in [('risk',{'team':'risk_team'}),('finance',{'team':'financial_team'}),
                             ('duplicate',{'team':'risk_team','aliases':[{'team':'financial_team'}]})]:
            db.execute('UPDATE document SET json=? WHERE document_id=?',
                       (json.dumps({'document_metadata':metadata}),did))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    return tmp_path/'built/generation'


def test_team_catalogue_plan_and_fail_closed(tmp_path,team_generation):
    app=app_for(tmp_path,team_generation)
    with TestClient(app) as c:
        p=app.state.pipeline
        assert document_teams(p.store)['duplicate']=={'risk_team','financial_team'}
        assert p.plan('승인?',team_id='risk_team')['scope']['document_version_ids']==['duplicate','risk']
        assert p.plan('승인?',team_id='financial_team')['scope']['document_version_ids']==['duplicate','finance']
        assert len(p.plan('승인?')['scope']['document_version_ids'])==4
        with pytest.raises(ValueError,match='outside selected team'):
            p.plan('승인?',['finance'],team_id='risk_team')
        with pytest.raises(ValueError,match='no documents'):
            p.plan('승인?',scope='개정이력',team_id='risk_team')
        teams=c.get('/v1/rag/teams').json()
        assert teams['teams']==[{'team_id':'financial_team','document_count':2},{'team_id':'risk_team','document_count':2}]
        assert teams['unassigned_document_count']==1
        for invalid in (None,'','missing_team','../risk_team',42,['risk_team']):
            r=c.post('/v1/rag/ask',json={'question':'목록','team_id':invalid,'use_llm':False})
            assert r.status_code==422,r.text


def test_team_browse_read_and_reference_api(tmp_path,team_generation):
    app=app_for(tmp_path,team_generation)
    with TestClient(app) as c:
        params={'team_id':'risk_team'}
        page=c.get('/v1/rag/documents',params={**params,'limit':1}).json()
        assert page['total']==2 and page['next_offset']==1
        page2=c.get('/v1/rag/documents',params={**params,'offset':1}).json()
        assert {d['id'] for d in page['documents']+page2['documents']}=={'risk','duplicate'}
        scopes=c.get('/v1/rag/scopes',params=params).json()
        assert {d['document_id'] for d in scopes['documents']}=={'risk','duplicate'}
        for route in ('document/read','document/outline','nodes','section'):
            assert c.get('/v1/rag/'+route,params={**params,'doc_id':'finance','node':'0'}).status_code==422
        r=c.get('/v1/rag/document/read',params={**params,'doc_id':'risk'})
        assert r.status_code==200 and r.json()['document_id']=='risk'
        index=app.state.pipeline.term_agent.get_index()
        with sqlite3.connect(index.path/'navigation.sqlite') as db:
            sid=db.execute("SELECT id FROM source WHERE document_id='risk'").fetchone()[0]
        assert c.get('/v1/rag/links',params={'source_id':sid}).json()['references']
        assert c.get('/v1/rag/links',params={**params,'source_id':sid}).json()['references']==[]


def test_v5_team_scope_survives_search_read_and_relation_expansion(tmp_path,team_generation):
    app=app_for(tmp_path,team_generation);p=app.state.pipeline
    try:
        query=p.plan('영업일 승인',team_id='risk_team')
        request={'question':'영업일 승인','document_ids':query['scope']['document_version_ids'],'use_llm':False}
        with p.term_agent.open_session(request,query=query,runtime=tmp_path/'runtime') as s:
            assert set(s.sources.scope)=={'risk','duplicate'}
            root=s.sources.root
            r=s.sources.execute(tool('search',target=root,query='영업일',mode='literal',cursor=None),'search')
            assert r['items']
            assert all(s.sources.resolve(x['target'])['document_id']=='risk' for x in r['items'])
            target=r['items'][0]['target']
            read=s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),'read')
            assert read['evidence_ids']
            assert all(s.work.evidence(e)['document_id']=='risk' for e in read['evidence_ids'])
            rel=s.sources.execute(tool('follow_reference',evidence=read['evidence_ids'][0],direction='both',cursor=None),'references')
            assert '재무팀만 검토' not in json.dumps(rel,ensure_ascii=False)
            for row in s.work.db.execute("SELECT identity_json FROM navigation_handle WHERE kind IN ('D','P','U')"):
                value=json.loads(row[0])
                assert value.get('document_id') in (None,'risk','duplicate')
            forged=s.sources.handle('D',{'document_id':'finance'})
            with pytest.raises(ProposalError,match='outside'):
                s.sources.resolve(forged)
    finally:p.store.close()


def test_workflow_legal_agent_through_service_to_real_v5_app(tmp_path,team_generation,monkeypatch):
    import service
    app=app_for(tmp_path,team_generation)
    spec=importlib.util.spec_from_file_location('team_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
    monkeypatch.setattr(workflow,'_settings',lambda:('http://synthetic.invalid/json','synthetic-token',120))
    captured={}
    with TestClient(app) as client:
        class Reply:
            status=200
            headers={'Content-Type':'text/event-stream'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def __iter__(self):
                yield ('data: '+json.dumps({'event':'result','data':self.envelope})+'\n\n').encode()
        def send(request,timeout):
            payload=json.loads(request.data);captured.update(payload)
            normalized=service._normalize(payload)
            r=client.post(normalized['path'],json=normalized['json'])
            assert r.status_code==200,r.text
            reply=Reply();reply.envelope={'status':r.status_code,'body':r.json()}
            captured['result']=r.json()
            return reply
        monkeypatch.setattr(workflow.urllib.request,'urlopen',send)
        r=asyncio.run(workflow.run({'question':'전체 문서 목록','team_id':'risk_team','use_llm':False,'user_id':'fixture-user'}))
        assert captured['API_TYPE']=='LEGAL_AGENT'
        assert captured['team_id']=='risk_team'
        assert r['text'] and r['run_id']
        assert '모의재무규정' not in r['text'] and '공통모의자료' not in r['text']
        journal=next((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite'))
        with sqlite3.connect(journal) as db:
            row=db.execute('SELECT binding_json FROM run').fetchone()
            assert set(json.loads(row[0])['scope']['document_version_ids'])=={'risk','duplicate'}
        assert workflow._extract_question({'team_id':'risk_team','scope':'전체'})==''
        # Exercise the actual platform entrypoint too, with successive team selections
        # in one cached application; request scope must never stick to another call.
        monkeypatch.setattr(service,'_APP',app)
        for team,excluded in [('financial_team','모의위험규정'),('risk_team','모의재무규정')]:
            reply=asyncio.run(service.service({}, {'API_TYPE':'LEGAL_AGENT',
                'question':'전체 문서 목록','team_id':team,'use_llm':False,'user_id':'fixture-user'}))
            assert reply['status']==200,reply
            assert excluded not in reply['body']['answer']['text']


@pytest.mark.parametrize('api_type',['LEGAL_AGENT','legal_agent','ELS_QUERY'])
def test_alias_transport_metadata_is_removed(api_type):
    import service
    body={'question':'승인?','team_id':'risk_team','user_id':'u','session_id':'s','channel':'chat','request_id':'r'}
    for payload in ({'API_TYPE':api_type,**body},{'API_TYPE':api_type,'json':body}):
        assert service._normalize(payload)['json']=={'question':'승인?','team_id':'risk_team'}


def test_current_generation_boot_and_team_search(tmp_path,team_generation,monkeypatch):
    import service
    monkeypatch.setattr(service,'_APP',None)
    monkeypatch.setattr(service,'_BINDING',None)
    monkeypatch.setattr(service,'_provider',lambda *args:object())
    monkeypatch.setenv('GENOS_GENERATION',str(team_generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'serving'))
    for key in ('GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256'):
        monkeypatch.delenv(key,raising=False)
    try:
        health=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}))
        assert health['status']==200,health
        assert health['body']['release']['mode']=='genos-generation'
        result=asyncio.run(service.service({}, {'API_TYPE':'RAG_SEARCH','q':'영업일','team_id':'risk_team'}))
        assert result['status']==200,result
        assert '재무팀만 검토' not in json.dumps(result,ensure_ascii=False)
        invalid=asyncio.run(service.service({}, {'API_TYPE':'RAG_SEARCH','q':'영업일','team_id':'missing_team'}))
        assert invalid['status']==422,invalid
    finally:
        if service._APP is not None:service._APP.state.pipeline.store.close()


def test_genos_v5_uses_environment_model_without_profile_file(tmp_path, team_generation, monkeypatch):
    import hashlib
    import service
    import semantic_runtime.app as runtime_app
    from semantic_runtime.legal_agent.transport import GenosTransport

    captured = {}
    monkeypatch.delenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', raising=False)
    monkeypatch.setattr(service, '_APP', None)
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    monkeypatch.setattr(runtime_app, 'create_app', lambda *args, **kwargs: captured.update(kwargs) or object())
    monkeypatch.setenv('GENOS_GENERATION', str(team_generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path/'serving'))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION', 'legal-agent-tools-v5')
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('GENOS_LLM_MAX_INPUT_BYTES', '')
    monkeypatch.setenv('GENOS_RAG_MAX_OUTPUT_TOKENS', '80000')
    for key in ('GENOS_LLM_URL', 'LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256'):
        monkeypatch.delenv(key, raising=False)
    service.application()
    model_binding = captured['legal_agent_profile']['model_binding']
    assert model_binding['model'] == 'fixture-model'
    assert 'max_input_bytes' not in model_binding
    assert captured['legal_agent_profile']['max_output_tokens'] == 80000
    assert captured['legal_agent_profile']['wall_seconds'] == 1800
    assert captured['legal_agent_profile']['max_concurrent_requests_per_process'] == 0
    assert model_binding['endpoint_identity'] == hashlib.sha256(
        b'https://internal-fixture.invalid/api/gateway/rep/serving/123').hexdigest()
    assert isinstance(captured['legal_agent_transport'], GenosTransport)
    assert captured['legal_agent_transport'].binding == model_binding
    assert captured['implementation'] == 'legal-agent-tools-v5'
    assert 'synthetic-test-key' not in json.dumps(captured['legal_agent_profile'])


def test_genos_v5_environment_binding_needs_no_input_limit_setting(monkeypatch):
    import service
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.delenv('GENOS_LLM_MAX_INPUT_BYTES', raising=False)
    monkeypatch.delenv('GENOS_RAG_MAX_OUTPUT_TOKENS', raising=False)
    binding = service._genos_v5_environment_binding()[0]['model_binding']
    assert 'max_input_bytes' not in binding


@pytest.mark.parametrize('value', ['1', '4', '-1', '1.5', 'many'])
def test_genos_v5_ignores_retired_request_limit(monkeypatch, value):
    import service
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', value)
    configured = service._genos_v5_environment_binding()[0]
    assert configured['max_concurrent_requests_per_process'] == 0


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'many'])
def test_genos_v5_rejects_invalid_output_token_limit(monkeypatch, value):
    import service
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_RAG_MAX_OUTPUT_TOKENS', value)
    with pytest.raises(ValueError, match='GENOS_RAG_MAX_OUTPUT_TOKENS'):
        service._genos_v5_environment_binding()


def test_genos_v5_output_limit_survives_current_generation_switch(tmp_path, team_generation, monkeypatch):
    import hashlib
    import shutil
    import service
    import semantic_runtime.app as runtime_app

    data_root = tmp_path / 'shared-data'
    generations = data_root / 'generations'
    created = []
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    monkeypatch.setattr(runtime_app, 'create_app',
                        lambda *args, **kwargs: created.append((args, kwargs)) or object())
    monkeypatch.delenv('GENOS_GENERATION', raising=False)
    monkeypatch.delenv('GENOS_RAG_IMPLEMENTATION', raising=False)
    monkeypatch.delenv('LEGAL_AGENT_PROFILE', raising=False)
    monkeypatch.delenv('LEGAL_AGENT_PROFILE_SHA256', raising=False)
    monkeypatch.setenv('GENOS_DATA_ROOT', str(data_root))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('GENOS_RAG_MAX_OUTPUT_TOKENS', '80000')

    for name in ('first', 'second'):
        generation = generations / name
        shutil.copytree(team_generation, generation)
        manifest_sha = hashlib.sha256((generation / 'manifest.json').read_bytes()).hexdigest()
        (generations / 'CURRENT.json').write_text(json.dumps({
            'schema_version': 'genos-current-generation-v1',
            'generation_id': name, 'path': str(generation),
            'manifest_sha256': manifest_sha,
        }))
        monkeypatch.setattr(service, '_APP', None)
        service.application()
        args, kwargs = created[-1]
        assert args[1] == generation
        assert kwargs['release']['mode'] == 'genos-data-current'
        assert kwargs['legal_agent_profile']['max_output_tokens'] == 80000
        assert kwargs['legal_agent_profile']['wall_seconds'] == 1800


def test_genos_v5_environment_model_boots_real_app(tmp_path, team_generation, monkeypatch):
    import service
    from semantic_runtime.legal_agent.transport import GenosTransport

    monkeypatch.setattr(service, '_APP', None)
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    monkeypatch.setenv('GENOS_GENERATION', str(team_generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path/'serving'))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION', 'legal-agent-tools-v5')
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.delenv('GENOS_LLM_MAX_INPUT_BYTES', raising=False)
    monkeypatch.delenv('GENOS_RAG_MAX_OUTPUT_TOKENS', raising=False)
    for key in ('GENOS_LLM_URL', 'LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256'):
        monkeypatch.delenv(key, raising=False)
    checked = []
    async def model_list(self, method, path, body, seconds):
        checked.append((method, path, self.binding['model']))
        return {'body_json': {'data': [{'id': 'fixture-model'}]}}
    monkeypatch.setattr(GenosTransport, '_request', model_list)
    try:
        health = asyncio.run(service.service({}, {'API_TYPE': 'HEALTH'}))
        assert health['status'] == 200, health
        app = service._APP
        assert checked == [('GET', '/models', 'fixture-model')]
        assert app.state.pipeline.term_agent.transport.binding['model'] == 'fixture-model'
        assert app.state.pipeline.term_agent.profile['max_output_tokens'] == 6400
        assert app.state.pipeline.term_agent.profile['wall_seconds'] == 1800
        with TestClient(app) as client:
            reply = client.post('/v1/rag/ask', json={'question': '전체 문서 목록', 'use_llm': False})
            assert reply.status_code == 200, reply.text
    finally:
        if service._APP is not None:
            service._APP.state.pipeline.store.close()
        service._APP = None
