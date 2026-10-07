"""Keep structured case context out of both native lexical-search entrypoints."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

from semantic_runtime.fulltext import question_terms
from semantic_runtime.legal_agent.memory_rag import NativeRag
from semantic_runtime.legal_agent.unified_rag import UnifiedRag


def state():
    return {'task': '내부회계관리자를 누가 지정하는지 확인',
            'facts': [{'name': '질문 대상', 'value': '내부회계관리자 지정 주체'}],
            'document_ids': ['d'], 'queries': [], 'source_category': 'ALL'}


def test_actual_tokenizer_never_receives_fact_serialization():
    host = NativeRag.__new__(NativeRag)
    current = state(); before = deepcopy(current)
    terms = set(question_terms(host.retrieval_question(current)))
    assert {'내부', '회계', '관리자', '지정'} <= terms
    assert not terms & {'a', 'e', 'l', 'm', 'n', 'u', 'v', '질문', '대상'}
    assert current == before
    assert '"name"' in host.question(current) and '"value"' in host.question(current)


def test_null_empty_duplicate_and_real_fact_values():
    host = NativeRag.__new__(NativeRag)
    current = state()
    current['facts'] = [
        {'name': '미확인', 'value': None}, {'name': '빈 값', 'value': ' '},
        {'name': '업무 목적', 'value': current['task']},
        {'name': '적용 기준', 'value': 'IFRS 17'},
        {'name': '중복', 'value': 'IFRS 17'},
    ]
    assert host.retrieval_question(current).splitlines() == [current['task'], 'IFRS 17']


def test_question_without_facts_and_literal_user_text_is_preserved():
    host = NativeRag.__new__(NativeRag)
    current = state()
    current.update(task='name/value라는 용어의 정의를 찾아줘', facts=[])
    assert host.retrieval_question(current) == current['task']


def test_native_session_plan_and_request_use_clean_search():
    host = NativeRag.__new__(NativeRag); captured = {}
    session = SimpleNamespace(work=SimpleNamespace(event=lambda *_: None),
                              check_sources_unchanged=lambda: None)
    @contextmanager
    def open_session(request, **kwargs):
        captured.update(request=request, options=kwargs)
        yield session
    def plan(question, documents):
        captured['plan_question'] = question
        return {'question': question}
    host.pipeline = SimpleNamespace(plan=plan, term_agent=SimpleNamespace(open_session=open_session))
    host.runtime = 'runtime'
    host.documents = lambda *_: ['d']
    current = state()
    with host.open(current, {'user_id': 'u', 'team_id': 't'}, {'request_id': 'r', 'session_id': 's'}):
        assert captured['plan_question'] == host.retrieval_question(current)
        assert captured['request']['question'] == host.retrieval_question(current)
        assert '"name"' not in captured['request']['question']


@dataclass
class Context:
    query: dict
    request: dict


def test_unified_session_rebinds_clean_search_preserving_authorization():
    host = UnifiedRag.__new__(UnifiedRag)
    context = Context(query={'id': 'q', 'question': 'previous'},
                      request={'question': 'previous', 'document_ids': ['d'], 'use_llm': True})
    tools = SimpleNamespace(context=context, source=SimpleNamespace(context=context, scope=['d']),
                            handle=lambda *_: 'root')
    session = SimpleNamespace(context=context, sources=tools,
        work=SimpleNamespace(binding={'scope': {'document_version_ids': ['d']}}, event=lambda *_: None),
        check_sources_unchanged=lambda: None)
    host.model = SimpleNamespace(ensure=lambda: session)
    host.documents = lambda *_: ['d']
    host.execution_class = lambda *args: SimpleNamespace()
    current = state()
    with host.open(current, {}, {'request_id': 'r', 'session_id': 's'}):
        assert session.context.request['question'] == host.retrieval_question(current)
        assert session.context.query['question'] == host.retrieval_question(current)
        assert session.context.request['document_ids'] == ['d']
        assert session.sources.source.context is session.context
        assert session.sources.scope == ['d']
        assert '"name"' in host.question(current)
