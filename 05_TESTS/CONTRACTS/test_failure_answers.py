"""A failure after the work journal opened answers with what was done; its failure points can be continued.

User 2026-11-12: "가장 중요한건 불일치나 여러 이유로 중단되었을때 이전 내용을 기반으로 답변 … 검사에서 실패했다고
죽지말고 패스해" and "실패지점도 사용자한테 출처 박스 형태와 유사하게 알려주고 멀티턴에서 수정하게 해줘 …
일반적인 멀티턴도 가능해야해", "내용 저장한다고 여러번 쓰기해서 sql및 cpu에 부담이 안가게".

Actual HTTP/store/pipeline boundary with a scripted model transport; failures are injected at the ASSESS
stage (after the guided investigation read an original) or at publication.
"""
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from semantic_runtime import chat_adapter as adapter
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_answer, progress_report as pr, unified_runtime
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from semantic_runtime.oracle_dp_io import BudgetPause, DPError
from test_guided_continue_bounds import NAMED
from test_legal_agent_double_harness import ROOT
from test_multiturn_structured_scope import tree  # noqa: F401 - fixture
from test_progress_report import Reporting


class Turns(Reporting):
    """Reporting transport that can continue the stopped question on a later turn."""
    def __init__(self, resolve=('RESEARCH_REENTER', 'ASSESS'), relation='REVIEW'):
        super().__init__()
        self.plan.update(resolve=resolve, relation=relation)
        self.systems = {}

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        self.systems.setdefault((self.turn, view.get('source_stage') or view['phase']), body['messages'][0]['content'])
        return super().send_once(body=body, ticket=ticket)


def app_for(tree, tmp_path, transport):
    gen, idx = tree
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=tmp_path / 'runtime',
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    return app


def failing_once(monkeypatch, error):
    """guided_answer.assess raises `error(executor)` on its first call only."""
    real = guided_answer.assess
    calls = []

    def assess(executor, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise error(executor)
        return real(executor, *args, **kwargs)
    monkeypatch.setattr(guided_answer, 'assess', assess)
    return calls


def rows(tmp_path, sql):
    db = connect(selected_store(tmp_path / 'runtime'))
    try:
        return [tuple(r) for r in db.execute(sql)]
    finally:
        db.close()


def shown(response):
    v = adapter.views()
    return v.render(v.public_response(response.json(), status=response.status_code))


def points_of(response):
    return response.json()['assembly']['term_agent']['failure_points']


@pytest.mark.parametrize('error,kind', [
    (lambda e: ContractError('source excerpt reply differs from unresolved assessment or originals'), 'CHECK_FAILED'),
    (lambda e: TypeError("Object of type function is not JSON serializable"), 'SERVER_ERROR'),
    (lambda e: sqlite3.OperationalError('database is locked'), 'READ_FAILED'),
    (lambda e: DPError('READ_FAILED: ReadTimeout'), 'READ_FAILED'),
    (lambda e: BudgetPause('BUDGET_PAUSED: SQL statements'), 'LIMIT')])
def test_a_failure_after_reading_answers_with_what_was_done(tree, tmp_path, monkeypatch, error, kind):
    failing_once(monkeypatch, error)
    transport = Reporting()
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 200, response.text
    body = response.json()
    text = body['answer']['text']
    assert text.startswith(pr.NOTES[kind]) and '최종 답변은 아닙니다' in text
    assert body['answer']['claims'] == [], 'a stopped answer carries no accepted claim'
    assert '**확인하지 못한 지점**' in text and '1. [읽은 조문으로 판단] ' + pr.TITLES[kind] in text
    assert len(transport.reports) == 1, 'one report call; the failed stage is not retried'
    assert transport.reports[0]['view']['originals'], 'the report is written from the originals read'
    points = points_of(response)
    assert points[0]['stage'] == '읽은 조문으로 판단' and points[0]['stop'] == kind
    assert points[0]['resume'] == {'method': 'RESEARCH_REENTER', 'stage': 'ASSESS'}
    assert points[0]['next'].startswith(('“1번', '“이어서')), points[0]['next']
    # The originals read are shown as source cards of the stopped answer.
    assert body['retrieval']['candidates'] and body['selection']['selected']
    assert rows(tmp_path, 'SELECT status FROM request') == [('COMPLETE',)]
    display = shown(response)
    assert 'data-genos-failure="true"' in display and '확인하지 못한 지점 · ' in display
    assert 'data-genos-source="true"' in display, 'the originals read are folded like source boxes'
    assert '(500)' not in display and 'Traceback' not in display and 'ContractError' not in display


def test_a_request_conflict_stays_an_error(tree, tmp_path, monkeypatch):
    from semantic_runtime.legal_agent import corrected_memory

    def stale(self, *args, **kwargs):
        raise corrected_memory.Conflict('stale expected revision')
    monkeypatch.setattr(corrected_memory.Memory, 'context', stale)
    transport = Reporting()
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 409
    assert transport.reports == []
    assert rows(tmp_path, 'SELECT status FROM request') == [('FAILED',)]


def test_a_fault_while_resolving_the_request_also_answers(tree, tmp_path, monkeypatch):
    """The journal is open from the request entry on; a defect there is a report, not a 500."""
    from semantic_runtime.legal_agent import corrected_memory

    def broken(self, *args, **kwargs):
        raise TypeError('defect before any model call')
    monkeypatch.setattr(corrected_memory.Memory, 'context', broken)
    with TestClient(app_for(tree, tmp_path, Reporting()), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 200, response.text
    assert response.json()['answer']['text'].startswith(pr.NOTES['SERVER_ERROR'])
    assert points_of(response)[0]['stage'] == '질문 이해'
    assert rows(tmp_path, 'SELECT status FROM request') == [('COMPLETE',)]


def test_a_failing_report_keeps_the_original_error(tree, tmp_path, monkeypatch):
    failing_once(monkeypatch, lambda e: ContractError('stored evidence hash mismatch'))

    def report(*args, **kwargs):
        raise RuntimeError('report writer defect')
    monkeypatch.setattr(pr, 'report', report)
    with TestClient(app_for(tree, tmp_path, Reporting()), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 500
    assert rows(tmp_path, 'SELECT status FROM request') == [('FAILED',)]


def test_a_record_value_that_is_not_json_is_kept_as_text(tree, tmp_path, monkeypatch):
    """MAIN217 cm-014: a function object in a record event failed the whole answer."""
    seen = {}
    real = guided_answer.assess

    def assess(executor, *args, **kwargs):
        seen['seq'] = executor.s.work.event('ANSWER_READ_REENTRY_UNAVAILABLE', {'capacity': len, 'ratio': float('nan')})
        return real(executor, *args, **kwargs)
    monkeypatch.setattr(guided_answer, 'assess', assess)
    with TestClient(app_for(tree, tmp_path, Reporting()), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'READY', 'the answer is not lost to a record value'
    assert isinstance(seen['seq'], int)


def test_a_state_event_that_is_not_json_still_fails():
    from semantic_runtime.legal_agent.repository import recordable
    value = recordable('X', {'f': len, 'n': [1, float('inf')], 'ok': 'text'})
    assert value['ok'] == 'text' and value['recorded_as_text'] is True
    assert value['f'].startswith('<built-in function len') and isinstance(value['n'][1], str)


def test_the_same_request_again_returns_the_saved_report(tree, tmp_path, monkeypatch):
    failing_once(monkeypatch, lambda e: ContractError('composition differs'))
    transport = Reporting()
    body = {'session_id': 's', 'request_id': '1', 'question': NAMED}
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        first = api.post('/v1/rag/ask', json=body)
        again = api.post('/v1/rag/ask', json=body)
    assert first.status_code == again.status_code == 200, again.text
    assert again.json()['answer']['text'] == first.json()['answer']['text']
    assert len(transport.reports) == 1


def test_failure_points_ride_on_the_one_final_write(tree, tmp_path, monkeypatch):
    """No table, row or event per point: the request row and its one dialogue row carry them."""
    failing_once(monkeypatch, lambda e: ContractError('claim links conflict'))
    with TestClient(app_for(tree, tmp_path, Reporting()), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
    assert response.status_code == 200, response.text
    turns = rows(tmp_path, "SELECT command FROM event WHERE kind='CONVERSATION_TURN'")
    assert len(turns) == 1
    record = json.loads(turns[0][0])['record']
    assert record['clarification'] is False and record['goal_id'], 'an applied question that stopped is continued, not re-run'
    assert [p['no'] for p in record['failure_points']] == list(range(1, len(record['failure_points']) + 1))
    assert len(json.dumps(record['failure_points'], ensure_ascii=False)) < 4000, 'bounded'
    assert all('text' not in p for p in record['failure_points']), 'labels only; originals are not copied'


def test_point_number_continues_the_same_question(tree, tmp_path, monkeypatch):
    calls = failing_once(monkeypatch, lambda e: ContractError('composition differs from assessment'))
    transport = Turns()
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        first = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
        assert first.status_code == 200, first.text
        goal = rows(tmp_path, 'SELECT id FROM goal ORDER BY ordinal DESC LIMIT 1')[0][0]
        transport.target = goal; transport.task = NAMED; transport.turn = 2
        second = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '2', 'question': '1번 다시 확인해 줘'})
    assert second.status_code == 200, second.text
    body = second.json()
    assert body['status'] == 'READY' and body['executed'] == ['ASSESS', 'COMPOSE'] and body['method_id'] == 'RESEARCH_REENTER'
    assert body['goal_id'] == goal, 'the stopped question is continued, its originals kept'
    assert len(calls) >= 2, 'the stage that failed ran again'
    resolve = [r for r in transport.log if r['turn'] == 2 and r['phase'] == 'memory-resolve']
    assert resolve, [r['phase'] for r in transport.log if r['turn'] == 2]
    dialogue = resolve[0]['view']['recent_dialogue']
    stopped = [t for t in dialogue if t.get('failure_points')]
    assert stopped and stopped[-1]['goal_id'] == goal and stopped[-1]['failure_points'][0]['resume']['stage'] == 'ASSESS'
    assert 'failure_points' in transport.systems[(2, 'memory-resolve')], 'the resolver is told what the points mean'
    assert 'failure_points' not in str(body['assembly']['term_agent']), 'the new answer has no stop'


def test_an_ordinary_turn_has_no_failure_point_rule(tree, tmp_path):
    transport = Turns(resolve=('RESEARCH_CONTINUE', 'SELECT'), relation='CONTINUE')
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        first = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
        assert first.status_code == 200 and first.json()['status'] == 'READY', first.text
        goal = rows(tmp_path, 'SELECT id FROM goal ORDER BY ordinal DESC LIMIT 1')[0][0]
        transport.target = goal; transport.task = NAMED; transport.turn = 2
        second = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '2', 'question': '어 계속 찾아줘'})
    assert second.status_code == 200 and second.json()['status'] == 'READY', second.text
    resolve = [r for r in transport.log if r['turn'] == 2 and r['phase'] == 'memory-resolve']
    assert resolve and 'failure_points' not in transport.systems[(2, 'memory-resolve')], 'ordinary multi-turn prompt unchanged'


def test_a_publication_failure_answers_with_a_report(tree, tmp_path, monkeypatch):
    real = unified_runtime.result_port
    calls = []

    def port(pipeline, session, cases, result):
        calls.append(result['status'])
        if result['status'] == 'READY':
            raise ContractError('composition differs from the committed assessment')
        return real(pipeline, session, cases, result)
    monkeypatch.setattr(unified_runtime, 'result_port', port)
    transport = Reporting()
    body = {'session_id': 's', 'request_id': '1', 'question': NAMED}
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        response = api.post('/v1/rag/ask', json=body)
        again = api.post('/v1/rag/ask', json=body)
    assert response.status_code == 200, response.text
    text = response.json()['answer']['text']
    assert text.startswith(pr.NOTES['CHECK_FAILED']) and response.json()['answer']['claims'] == []
    assert points_of(response)[0]['stage'] == '답 내보내기'
    assert calls == ['READY', 'CLARIFY'] and len(transport.reports) == 1
    assert again.status_code == 200 and again.json()['answer']['text'] == text, 'resend returns the report'
    turns = rows(tmp_path, "SELECT command FROM event WHERE kind='CONVERSATION_TURN' ORDER BY id")
    # Events are append-only: the report's row follows the unpublished answer's row, and the dialogue
    # (recent_dialogue) reads only the latest row of the request.
    assert len(turns) == 2 and json.loads(turns[-1][0])['record']['text'] == text


def test_genos_cards_survive_markdown_projection():
    v = adapter.views()
    body = {'answer': {'text': '보고'}, 'assembly': {'term_agent': {'failure_points': [
        {'no': 1, 'stage': '읽은 조문으로 판단', 'title': '조문과 맞지 않는 내용을 뺌', 'target': None, 'detail': 'd<b>',
         'next': '“1번 다시 확인해 줘”'}]}}}
    html = v._failure_cards(body)
    assert html.count('data-genos-failure="true"') == 1 and 'd&lt;b&gt;' in html
    assert '1. &#91;읽은 조문으로 판단&#93; 조문과 맞지 않는 내용을 뺌' in html
    assert html in v._for_markdown('본문\n\n' + html)
    assert v._failure_cards({'answer': {'text': 'x'}}) == ''


def test_only_conflicts_and_admission_stay_errors():
    from semantic_runtime.legal_agent.corrected_memory import Conflict
    from semantic_runtime.legal_agent.errors import AdmissionRejected

    class Open:
        class model_resource:
            session = object()
    for kept in (Conflict('busy'), BlockingIOError('lease'), AdmissionRejected('full')):
        assert not pr.reportable(kept, Open)
    for other in (ContractError('x'), TypeError('x'), sqlite3.OperationalError('x'), DPError('x')):
        assert pr.reportable(other, Open) and not pr.reportable(other, object())
    assert pr.fault_kind(ContractError('x')) == 'CHECK_FAILED'
    assert pr.fault_kind(DPError('READ_FAILED: ReadTimeout')) == 'READ_FAILED'
    assert pr.fault_kind(BudgetPause('x')) == 'LIMIT'
    assert pr.fault_kind(TypeError('x'), deadline=0) == 'TIME_LIMIT', 'a query cut by the deadline is the time limit'
    assert pr.fault_kind(KeyError('x')) == 'SERVER_ERROR'


def test_reentering_the_investigation_brings_the_failure_points(tree, tmp_path, monkeypatch):
    failing_once(monkeypatch, lambda e: DPError('READ_FAILED: ReadTimeout'))
    transport = Turns(resolve=('RESEARCH_REENTER', 'SELECT'), relation='CONTINUE')
    with TestClient(app_for(tree, tmp_path, transport), raise_server_exceptions=False) as api:
        first = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})
        assert first.status_code == 200, first.text
        goal = rows(tmp_path, 'SELECT id FROM goal ORDER BY ordinal DESC LIMIT 1')[0][0]
        transport.target = goal; transport.task = NAMED; transport.turn = 2
        second = api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '2', 'question': '1번 다시 읽어 줘'})
    assert second.status_code == 200, second.text
    assert second.json()['goal_id'] == goal and second.json()['status'] == 'READY'
    nav = [r for r in transport.log if r['turn'] == 2 and r['phase'] == 'investigate']
    assert nav, 'the re-entry reaches the investigation'
    request = nav[0]['view']['continuation_request']
    assert request['user_request'] == '1번 다시 읽어 줘'
    assert request['previous_failure_points'][0]['title'] == pr.TITLES['READ_FAILED']


def test_a_failed_read_names_the_article_it_was_for():
    """"이 조문 못 읽음 — 「모의승인규정」 제2조": the read target handle of the journal, no extra query."""
    class Db:
        def one(self, table, **where):
            assert table == 'navigation_handle'
            return {'P2': {'identity_json': json.dumps({'document_id': 'd', 'read_label': '제2조'})}}.get(where['handle'])

    class Work:
        db = Db()

        def observations(self, limit=8):
            return [{'action': {'tool': 'read', 'args': {'target': 'P1'}}, 'status': 'OK'},
                    {'action': {'tool': 'read', 'args': {'target': 'P2'}}, 'status': 'ERROR'}]

        def evidence(self):
            return [{'document_id': 'd', 'metadata': {'document_name': '규정집 > 모의승인규정'}}]
    tools = pr.failed_reads(Work())
    assert tools == [{'tool': '조문 읽기', 'what': '「모의승인규정」 제2조'}]
    points = pr.failure_points('READ_FAILED', 'SELECT', tools,
        [{'from': '모의승인규정 제1조', 'to': '모의승인규정 제3조(예외)', 'relation': '예외를 정한 조문', 'why_not_read': '지정하신 검색 범위 밖이라서'}],
        ['모의승인규정 제1조'])
    assert [p['title'] for p in points] == ['조문을 불러오지 못함', '이 조문 못 읽음', '읽으려다 건너뜀']
    assert points[1]['target'] == '「모의승인규정」 제2조' and '읽으려 했으나 불러오지 못했습니다' in points[1]['detail']
    assert points[2]['detail'] == ('모의승인규정 제1조에 모의승인규정 제3조(예외)이(가) 이어져 있지만(예외를 정한 조문) '
                                   '읽지 않고 넘어갔습니다 — 지정하신 검색 범위 밖이라서.')


def test_screen_texts_have_no_internal_words():
    """Every failure text a legal user can see (user 2026-11-12: "도메인 전문가가 보면 이해하게")."""
    import re
    from semantic_runtime.legal_agent import connection_scope, review_explanation
    texts = [*pr.NOTES.values(), *pr.TITLES.values(), *pr.NEXT.values(), pr.NEXT_AGAIN, pr.NEXT_LINK, pr.NEXT_TOOL,
             *pr.STAGES.values(), *(c for c, _ in connection_scope.REASON_TEXT.values())]
    for kind in pr.TITLES:
        for p in pr.failure_points(kind, 'ASSESS', [{'tool': '조문 읽기', 'what': '「상법」 제434조'}],
                                   [{'from': '상법 제433조', 'to': '상법 제434조', 'relation': '준용', 'why_not_read': ''}], ['상법 제433조']):
            texts += [p['title'], p['detail'], p['next'], p['stage']]
    source = Path(review_explanation.__file__).read_text()
    block = source[source.index('explanations = {'):source.index("failures = [{'code'")]
    texts += re.findall(r":\s*'([^']+)'", block)
    banned = re.compile(r'모델|결속|해시|도구|스키마|JSON|SQL|API|토큰|원문 구간|주장|검사에서 불일치|[A-Z]{2,}_[A-Z_]+')
    found = [t for t in texts if banned.search(t)]
    assert not found, found
