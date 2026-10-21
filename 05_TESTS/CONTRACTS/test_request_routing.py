"""Request routing and publication contracts; synthetic model, no quality experiment."""
import json
import sqlite3
import runpy
from pathlib import Path
import pytest
from test_legal_agent_double_harness import generation, wire
from test_bounded_source_main import Transport, settings
from test_legal_agent_v5 import app_for
from semantic_runtime.folder_navigation import request
from semantic_runtime.legal_agent import source_query_planning as planning


class DirectTransport(Transport):
    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def send_once(self, *, body, ticket):
        self.calls.append(body)
        view = json.loads(body['messages'][1]['content'])['view']
        assert view['source_stage'] == 'source-query-plan', 'direct response must not search/compose/review'
        assert '선택 원문 읽기' in view['capabilities']['available']
        return wire({'mode': 'DIRECT', 'law_names': [], 'queries': [],
            'answer': self.answer, 'reason': '인사 또는 사용법 안내',
            'document_category': 'all', 'browse_view': 'documents', 'title_query': '', 'inspect_documents': False})


@pytest.mark.parametrize('question,answer', [
    ('안녕', '안녕하세요. 법령검색 에이전트입니다. 무엇을 확인하시겠어요?'),
    ('어떤 질문이 가능해?', '문서 목록 확인, 제목·본문 검색과 원문 근거를 바탕으로 한 질문을 도와드립니다.'),
])
def test_direct_answer_is_published_without_search_or_empty_evidence_warning(tmp_path, generation, question, answer):
    transport = DirectTransport(answer)
    app = app_for(tmp_path, generation, transport, settings())
    try:
        ask = lambda question, docs: app.state.pipeline.run(question, docs, execution_context={'runtime':tmp_path/'runtime','publish':True})
        result = ask(question, ['d'])
        assert result['answer']['text'] == answer
        assert result['answer']['claims'] == []
        assert result['answer']['unresolved'] == []
        meta = result['assembly']['term_agent']
        assert meta['request_routing']['mode'] == 'DIRECT'
        assert meta['bounded_source_workflow']['read_complete_count'] == 0
        assert meta['source_bundle']['sources'] == []
        assert result['answer']['provider_receipt']['physical_attempts'] == 1
        assert len(transport.calls) == 1
        path = next((tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT status FROM run').fetchone()[0] == 'COMPLETED'
            assert db.execute('SELECT count(*) FROM observation').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM evidence_unit').fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM event WHERE kind='REQUEST_ROUTED'").fetchone()[0] == 1
        saved = tmp_path/'runtime/runs'/(result['run_id']+'.json')
        assert json.loads(saved.read_text())['answer']['text'] == answer
        # GENOS uses this renderer for the same /json and SSE final result.
        bridge = runpy.run_path(str(Path(__file__).resolve().parents[2]/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'))
        assert bridge['render'](result) == answer
    finally:
        app.state.pipeline.store.close()


@pytest.mark.parametrize('question', ['현재 볼 수 있는 문서가 뭐야?', '현재 볼 수 있는 문서 알려줘',
    '현재 문서 목록 보여줘', '현재 볼수있는 문서 목록', '전체 문서 목록 보여줘'])
def test_available_documents_use_model_selected_scoped_catalogue(tmp_path, generation, question):
    transport = Transport(browse=True)
    app = app_for(tmp_path, generation, transport, settings())
    try:
        ask = lambda question, docs: app.state.pipeline.run(question, docs, execution_context={'runtime':tmp_path/'runtime','publish':True})
        result = ask(question, ['d'])
        assert '모의승인규정' in result['answer']['text']
        assert not result['answer']['claims']
        assert len(transport.calls) == 1
        assert request(question) is None
    finally:
        app.state.pipeline.store.close()


def test_greeting_with_legal_question_still_recalls_and_answers(tmp_path, generation):
    transport = Transport()
    app = app_for(tmp_path, generation, transport, settings())
    try:
        ask = lambda question, docs: app.state.pipeline.run(question, docs, execution_context={'runtime':tmp_path/'runtime','publish':True})
        result = ask('안녕, 모의승인규정의 승인 대상은?', ['d'])
        assert result['answer']['claims']
        assert result['assembly']['term_agent']['request_routing']['mode'] == 'SEARCH'
        assert result['assembly']['term_agent']['source_bundle']['sources']
        assert len(transport.calls) > 1
    finally:
        app.state.pipeline.store.close()


@pytest.mark.parametrize('row', [
    {'agent_required': True, 'answer': '', 'queries': []},
    {'agent_required': True, 'answer': '법적 결론', 'queries': ['승인 대상']},
    {'agent_required': False, 'answer': ' ', 'queries': []},
    {'agent_required': False, 'answer': '안녕하세요', 'queries': ['승인 대상']},
    {'agent_required': False, 'answer': '안녕하세요', 'queries': [], 'law_names': ['모의승인규정']},
])
def test_inconsistent_route_is_rejected(row):
    value = {'plans': [{'case_id': 'request', 'law_names': [], 'reason': '분류 검사', **row}]}
    with pytest.raises(ValueError):
        planning.validate_routing(value, [{'case_id': 'request'}], ['모의승인규정'])


def test_available_document_phrase_does_not_swallow_content_request():
    assert request('현재 볼 수 있는 문서에서 승인 요건을 설명해줘') is None
    assert request('자본시장법 문서 목록 보여줘') is None
    # Completed search-only callers keep their original schema and response contract.
    value = {'plans': [{'case_id': 'old', 'law_names': [], 'queries': ['승인 대상']}]}
    assert planning.validate(value, [{'case_id': 'old'}], [])['old']['queries'] == ['승인 대상']
