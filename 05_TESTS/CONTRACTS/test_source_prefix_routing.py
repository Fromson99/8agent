"""Leading source markers constrain the real MAIN query and request scope."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.pipeline import route_question
from semantic_runtime.folder_navigation import request as catalogue_request
from test_document_release import source
from test_legal_agent_v5 import app_for
from test_bounded_source_main import settings
from test_request_routing import DirectTransport


@pytest.fixture
def mixed_generation(tmp_path, term_glossary):
    raw = source(tmp_path / 'raw.sqlite', [
        ('internal', '모의내규', ['내부 승인 절차는 영업일에 따른다.']),
        ('external', '모의외규', ['외부 승인 절차는 영업일에 따른다.']),
        ('unknown', '출처미확인', ['승인 절차는 영업일에 따른다.']),
    ])
    with sqlite3.connect(raw) as db:
        for did, category in [('internal', 'internal'), ('external', 'external')]:
            db.execute('UPDATE document SET json=? WHERE document_id=?',
                       (json.dumps({'document_category': category}), did))
    build_generation(raw, term_glossary, tmp_path / 'built', serving=True)
    return tmp_path / 'built/generation'


@pytest.mark.parametrize('question,cleaned,category', [
    ('내규: 승인 절차는?', '승인 절차는?', 'internal'),
    (' 외규, 승인 절차는?', '승인 절차는?', 'external'),
    ('내규 승인 절차는?', '승인 절차는?', 'internal'),
    ('승인 절차의 내규와 외규는?', '승인 절차의 내규와 외규는?', None),
    ('내규정의 승인 절차는?', '내규정의 승인 절차는?', None),
])
def test_prefix_only_at_start(question, cleaned, category):
    assert route_question(question) == (cleaned, category)


def test_colloquial_data_inventory_is_a_catalogue_request():
    assert catalogue_request('내규데데이터 뭐있냐')['category'] == 'internal'
    assert route_question('내규: 내규데데이터 뭐있냐') == ('전체 문서 목록', 'internal')
    assert route_question('외규: 내규 데이터 뭐있냐') == ('전체 문서 목록', 'external')


def test_prefix_filters_plan_and_real_request_scope(tmp_path, mixed_generation, monkeypatch):
    app = app_for(tmp_path, mixed_generation)
    pipeline = app.state.pipeline
    try:
        assert pipeline.plan('승인 절차는?')['scope']['document_version_ids'] == [
            'external', 'internal', 'unknown']
        for marker, expected in [('내규', 'internal'), ('외규', 'external')]:
            query = pipeline.plan(f'{marker}: 승인 절차는?')
            assert query['question'] == '승인 절차는?'
            assert query['scope']['document_version_ids'] == [expected]
            assert pipeline.plan(f'{marker} 승인 절차는?', ['internal', 'external'])[
                'scope']['document_version_ids'] == [expected]
            captured = {}
            def open_session(request, *, query, **kwargs):
                from contextlib import contextmanager
                @contextmanager
                def session():
                    captured.update(request=request, query=query, options=kwargs)
                    raise RuntimeError('scope captured')
                    yield
                return session()
            monkeypatch.setattr(pipeline.term_agent, 'open_session', open_session)
            with pytest.raises(RuntimeError, match='scope captured'):
                pipeline.run(f'{marker}: 승인 절차는?', ['internal', 'external'])
            assert captured['request']['question'] == '승인 절차는?'
            assert captured['request']['document_ids'] == [expected]
            assert captured['query']['scope']['document_version_ids'] == [expected]
            assert captured['options']['requested_source_category'] == expected
        with pytest.raises(ValueError, match='no documents'):
            pipeline.plan('내규: 승인 절차는?', ['external'])
        with pytest.raises(ValueError, match='requires a question'):
            pipeline.plan('외규:')
    finally:
        pipeline.store.close()


def test_prefix_filters_main_ask_document_list(tmp_path, mixed_generation):
    app = app_for(tmp_path, mixed_generation)
    with TestClient(app) as client:
        for marker, included, excluded in [
            ('내규', '모의내규', '모의외규'),
            ('외규', '모의외규', '모의내규'),
        ]:
            response = client.post('/v1/rag/ask', json={
                'question': f'{marker}: 전체 문서 목록', 'use_llm': False})
            assert response.status_code == 200, response.text
            text = response.json()['answer']['text']
            assert included in text
            assert excluded not in text
            assert '출처미확인' not in text
        response = client.post('/v1/rag/ask', json={
            'question': '전체 문서 목록', 'use_llm': False})
        assert response.status_code == 200, response.text
        assert '모의내규' in response.json()['answer']['text']
        assert '모의외규' in response.json()['answer']['text']


def test_user_wording_opens_prefixed_catalogue_without_model(tmp_path, mixed_generation):
    app = app_for(tmp_path, mixed_generation)
    with TestClient(app) as client:
        for question, included, excluded in [
            ('내규: 내규데데이터 뭐있냐', '모의내규', '모의외규'),
            ('외규: 내규 데이터 뭐있냐', '모의외규', '모의내규'),
        ]:
            response = client.post('/v1/rag/ask', json={'question': question})
            assert response.status_code == 200, response.text
            result = response.json()
            assert included in result['answer']['text']
            assert excluded not in result['answer']['text']
            assert '출처미확인' not in result['answer']['text']
            assert result['answer']['provider_receipt']['physical_attempts'] == 0


@pytest.mark.parametrize('marker,category,notice', [
    ('내규', 'internal', '현재 내규 데이터에 한정해서 작업하고 있다'),
    ('외규', 'external', '현재 외규 데이터에 한정해서 작업하고 있다'),
])
def test_prefixed_content_question_tells_model_its_bound_source_scope(
        tmp_path, mixed_generation, marker, category, notice):
    transport = DirectTransport('안녕하세요')
    app = app_for(tmp_path, mixed_generation, transport, settings())
    pipeline = app.state.pipeline
    try:
        query = pipeline.plan(f'{marker}: 승인 절차는?')
        request = {'question': query['question'], 'document_ids': query['scope']['document_version_ids'],
                   'use_llm': True}
        with pipeline.term_agent.open_session(
                request, query=query, runtime=tmp_path/'runtime',
                requested_source_category=category) as session:
            session.plan_request_search()
            assert session.context.binding['requested_source_category'] == category
            assert notice in transport.calls[0]['messages'][0]['content']
            assert set(session.sources.scope) == set(query['scope']['document_version_ids'])
    finally:
        pipeline.store.close()
