from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from test_main50_request_repair import tree
from test_bounded_delivered_handoff import StopTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from .conftest import WHO, command, publish


@pytest.fixture
def app(tmp_path, tree, service):
    gen, index = tree
    @contextmanager
    def factory(): yield service
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': 'investigation-completion-v8',
            'compact_input': True, 'assessment_reentry_limit': 0}}
    transport = StopTransport('repaired')
    transport.knowledge_views=[]
    original=transport.send_once
    def send_once(**kwargs):
        transport.knowledge_views.append(json.loads(kwargs['body']['messages'][1]['content'])['view'])
        return original(**kwargs)
    transport.send_once=send_once
    value = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport, runtime_root=tmp_path/'runtime',
        memory_identity=lambda _: {'user_id': WHO['user_id'], 'team_id': WHO['team_id'], 'document_ids': ['d']},
        knowledge_identity=lambda request: getattr(request.app.state, 'test_identity', None), knowledge_factory=factory)
    value.state.pipeline.term_agent.unit_fulltext = index
    value.state.test_identity = deepcopy(WHO)
    value.state.transport = transport
    yield value
    value.state.pipeline.store.close()


def enabled(app, mode='off'):
    app.state.pipeline.contracts.pipeline['legal_knowledge'].update(management_enabled=True, consumer_mode=mode)


def test_disabled_route_and_ad_are_independent(app):
    with TestClient(app) as client:
        assert client.get('/legal-knowledge/').status_code == 403
        assert client.get('/v1/legal-knowledge/status').status_code == 403
        enabled(app)
        assert client.get('/legal-knowledge/').status_code == 200
        assert client.get('/legal-knowledge/app.js').status_code == 200
        assert client.get('/v1/legal-knowledge/status').json()['consumer_mode'] == 'off'
        assert client.post('/v1/rag/memory/query', json={}).status_code == 403


@pytest.mark.parametrize('identity', [None, {**WHO, 'authenticated': False}])
def test_identity_cannot_be_supplied_by_client(app, identity):
    enabled(app);app.state.test_identity=identity
    with TestClient(app) as client:
        assert client.get('/v1/legal-knowledge/objects', headers={'user_id':'synthetic','team_id':'risk_team'}).status_code == 401
        assert client.get('/legal-knowledge/').status_code == 401


def test_api_edit_publish_status_and_csrf(app, definition):
    enabled(app)
    body={'schema_version':'legal-knowledge-v1','operation':'save_draft','operation_id':'api:save',
          'arguments':{'object_id':None,'expected_revision':0,'definition':definition}}
    with TestClient(app) as client:
        assert client.post('/v1/legal-knowledge/commands',json=body).status_code==403
        headers={'X-Knowledge-Request':'1','Origin':'https://foreign.invalid'}
        assert client.post('/v1/legal-knowledge/commands',json=body,headers=headers).status_code==403
        headers={'X-Knowledge-Request':'1'}
        response=client.post('/v1/legal-knowledge/commands',json=body,headers=headers)
        assert response.status_code==200,response.text
        draft=response.json()
        assert client.post('/v1/legal-knowledge/commands',json=body,headers=headers).json()==draft
        assert client.get('/v1/legal-knowledge/operations/api:save').json()['status']=='COMPLETE'
        assert client.get('/v1/legal-knowledge/objects').json()['items'][0]['id']==draft['id']
        app.state.test_identity={**WHO,'knowledge_roles':['read']}
        assert client.post('/v1/legal-knowledge/commands',json={**body,'operation_id':'api:denied'},headers=headers).status_code==403
        assert client.get('/legal-knowledge/%2e%2e').status_code in (404,422)


@pytest.mark.parametrize('mode', ['off','observe','consume'])
def test_actual_rag_entry_journal_and_answer_consumer(app, service, definition, mode):
    from semantic_runtime.legal_agent import completion_contracts as cc
    # Use the current completion enum, not a hand-written historical literal.
    app.state.pipeline.term_agent.profile['candidate_navigation']['completion_policy_version']=cc.V8
    enabled(app,mode)
    source=app.state.pipeline.store.manifest
    index=app.state.pipeline.term_agent.unit_fulltext.manifest
    binding={'generation':source['generation_id'],'store_sha256':source['store_sha256'],'unit_index_sha256':index['index_sha256']}
    publish(service,definition,binding)
    body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'knowledge','request_id':'knowledge:1'}
    with TestClient(app) as client:
        result=client.post('/v1/rag/ask',json=body)
        assert result.status_code==200,result.text
        value=result.json()
        metadata=value['assembly']['term_agent'].get('legal_knowledge')
        if mode=='off':assert metadata is None
        else:
            assert metadata['model_calls_added']==0
            assert metadata['bindings'] and any(b['items'] for b in metadata['bindings'])
            assert {b['mode'] for b in metadata['bindings']}=={mode}
        phases=list(app.state.transport.phases)
        duplicate=client.post('/v1/rag/ask',json=body)
        assert duplicate.status_code==200,duplicate.text
        assert duplicate.json()['answer']==value['answer']
        assert app.state.transport.phases==phases
        assert '승인' in value['answer']['text']
        visible=any('legal_review_guidance' in v for v in app.state.transport.knowledge_views)
        assert visible == (mode=='consume')
        if mode=='consume':
            command(service,'retire',{'expected_revision':1,'reason':'응답 이후 사용 중지'})
            rejected=client.post('/v1/rag/ask',json=body)
            assert rejected.status_code==409,rejected.text
            assert app.state.transport.phases==phases
