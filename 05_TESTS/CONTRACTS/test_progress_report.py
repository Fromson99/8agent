"""An agent stop answers with a progress report instead of an error (user 2026-11-11).

"1번 3번 케이스는 LLM을 강제로 호출해서 답변이 나오게 … 어떤 것까지 했고 어떤 게 부족하고 어떤 걸
결정해 줘야 하고 … 500은 진짜 500인 경우에만." / "500·503이 아닌 경우, 즉 우리 에이전트 문제인 경우
에러 발생이 아니라 지금까지 된 작업이 어땠는지, 판단이 충돌했으면 판단하기 어려운 지점입니다 …
사용자한테 어떻게 해야 될지 묻는 거야. 에러 숫자도 표시하지 마."

Actual HTTP/store/pipeline boundary with a scripted model transport; the ASSESS stop is injected
after the guided investigation has read an original.
"""
import json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_answer, progress_report as pr
from semantic_runtime.legal_agent.errors import (BudgetExhausted, ContractError, DeadlineExceeded,
    InvestigationPending, ProposalError, TransportError)
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_guided_continue_bounds import Transport, NAMED
from test_legal_agent_double_harness import ROOT, wire
from test_multiturn_structured_scope import tree

REPORT = {'found': '모의승인규정 제1조제1항은 각 호의 승인 기준을 적용한다고 정합니다.',
          'unclear': '각 호 중 어느 기준이 이번 거래에 해당하는지에서 판단이 갈립니다.',
          'done': ['모의승인규정 제1조제1항을 읽었습니다.'],
          'missing': ['각 호의 세부 기준이 이번 질문에 맞는지 확인하지 못했습니다.'],
          'decisions': ['적용할 거래의 종류를 알려 주시겠어요?']}
EMPTY = {'found': '', 'unclear': '', 'done': [], 'missing': [], 'decisions': []}


class Reporting(Transport):
    def __init__(self, reply=REPORT):
        super().__init__(NAMED, 'named', {'reads': 1}); self.reply = reply; self.reports = []

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        if (view.get('source_stage') or view['phase']) == pr.PHASE:
            self.reports.append({'view': view, 'system': body['messages'][0]['content']})
            return wire(self.reply)
        return super().send_once(body=body, ticket=ticket)


def serve(tree, tmp_path, transport, stop, monkeypatch, *, requests=1):
    def stopped(executor, *args, **kwargs):
        raise stop(executor)
    monkeypatch.setattr(guided_answer, 'assess', stopped)
    gen, idx = tree
    runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app, raise_server_exceptions=False) as api:
        body = {'session_id': 's', 'request_id': '1', 'question': NAMED}
        responses = [api.post('/v1/rag/ask', json=body) for _ in range(requests)]
    db = connect(selected_store(runtime))
    status = [r[0] for r in db.execute('SELECT status FROM request')]
    db.close()
    return responses, status


def serve_real(tree, tmp_path, transport):
    """The real answer stage; the caller decides what the guided answer does."""
    gen, idx = tree
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=tmp_path / 'runtime',
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app, raise_server_exceptions=False) as api:
        return api.post('/v1/rag/ask', json={'session_id': 's', 'request_id': '1', 'question': NAMED})


def pending(executor):
    return InvestigationPending('질문에 답할 근거가 충분히 확인되지 않았습니다.', stage='ASSESS',
                                diagnostics={'cause_codes': ['NO_SUPPORTED_CLAIMS']})


def unresolved(executor):
    return InvestigationPending('같은 판단의 수정 한도를 소진했습니다.', stage='ASSESS',
                                diagnostics={'cause_codes': ['ASSESSMENT_CONTRACT_UNRESOLVED']})


def rejected(executor):
    return ProposalError('assessment claim links conflict')


def exhausted(executor):
    work = executor.s.work
    with work.transaction():
        work.db.update('budget', lambda row: {'model_reserved': row['model_limit']}, singleton=1)
    return BudgetExhausted('model attempt limit; finalization reserve preserved')


def no_answer(executor):
    return TransportError('model deadline', unknown=True)


def shown(response):
    v = adapter.views()
    return v.render(v.public_response(response.json(), status=response.status_code))


@pytest.mark.parametrize('stop,kind,note', [(pending, 'REVIEW_INCOMPLETE', '필요한 조문을 다 확인하지 못해'),
                                            (exhausted, 'LIMIT', '조사 분량'),
                                            (unresolved, 'JUDGMENT_CONFLICT', '판단하기 어려운 지점입니다'),
                                            (rejected, 'JUDGMENT_CONFLICT', '판단하기 어려운 지점입니다')])
def test_agent_stop_answers_with_one_forced_report_and_asks_how_to_go_on(tree, tmp_path, monkeypatch, stop, kind, note):
    transport = Reporting()
    (response,), status = serve(tree, tmp_path, transport, stop, monkeypatch)
    assert response.status_code == 200, response.text
    text = response.json()['answer']['text']
    assert text.startswith(pr.NOTES[kind])
    assert note in text and '최종 답변은 아닙니다' in text
    unclear = '**여기서 판단하기 어렵습니다**' if kind == 'JUDGMENT_CONFLICT' else '**여기서 잘 모르겠습니다**'
    for part in ('**여기까지 확인했습니다**', REPORT['found'], '- 읽은 원문: ', unclear, REPORT['unclear'],
                 '**더 확인이 필요한 것**', REPORT['missing'][0], '**어떻게 진행할까요?**', REPORT['decisions'][0]):
        assert part in text
    assert text.index('**여기까지 확인했습니다**') < text.index(unclear) < text.index('**어떻게 진행할까요?**')
    assert response.json()['answer']['claims'] == [], 'a progress report carries no accepted claim'
    assert len(transport.reports) == 1, 'exactly one forced call'
    view = transport.reports[0]['view']
    assert view['question'] == NAMED and view['originals'], 'the model sees the originals this request read'
    assert view['stop']['stage'] == '읽은 조문으로 판단'
    assert view['drafts'] and all(d['stage'] == '조사 판단' for d in view['drafts']), 'the agent\'s own judgments so far'
    assert view['rejections'][0]['reason']
    assert view['connections'] == [] and '**이어서 확인할 수 있는 연결' not in text, 'this fixture has no unread link'
    assert status == ['COMPLETE']
    display = shown(response)
    assert REPORT['found'] in display and '현재 충분한 법률 검토를 하지 못했습니다' not in display


def test_the_same_request_again_returns_the_saved_report_without_a_model_call(tree, tmp_path, monkeypatch):
    transport = Reporting()
    first, again = serve(tree, tmp_path, transport, pending, monkeypatch, requests=2)[0]
    assert again.status_code == 200 and again.json()['answer']['text'] == first.json()['answer']['text']
    assert len(transport.reports) == 1


@pytest.mark.parametrize('stop', [pending, exhausted, rejected])
def test_a_failed_report_call_still_answers_with_the_servers_own_report(tree, tmp_path, monkeypatch, stop):
    transport = Reporting(reply=EMPTY)
    (response,), status = serve(tree, tmp_path, transport, stop, monkeypatch)
    assert response.status_code == 200, response.text
    text = response.json()['answer']['text']
    assert '- 읽은 원문: ' in text and pr.ASK in text and '**어떻게 진행할까요?**' in text
    assert ('**여기서 판단하기 어렵습니다**' if stop is rejected else '**여기서 잘 모르겠습니다**') in text
    assert len(transport.reports) == 1, 'no repair or retry of the report call'
    assert status == ['COMPLETE']
    assert not any(f'({n})' in shown(response) for n in (422, 500, 502, 504))


def test_a_model_that_did_not_answer_is_not_called_again(tree, tmp_path, monkeypatch):
    transport = Reporting()
    (response,), status = serve(tree, tmp_path, transport, no_answer, monkeypatch)
    assert response.status_code == 200, response.text
    text = response.json()['answer']['text']
    assert text.startswith(pr.NOTES['MODEL_NO_ANSWER']) and '- 읽은 원문: ' in text and pr.ASK in text
    assert transport.reports == []
    assert status == ['COMPLETE']


def test_a_check_failure_after_reading_answers_with_a_report(tree, tmp_path, monkeypatch):
    # 2026-11-12 contract change (user: "검사에서 실패했다고 죽지말고"): until MAIN218 this was a 500 with no report.
    transport = Reporting()
    (response,), status = serve(tree, tmp_path, transport, lambda e: ContractError('stored evidence hash mismatch'), monkeypatch)
    assert response.status_code == 200, response.text
    assert response.json()['answer']['text'].startswith(pr.NOTES['CHECK_FAILED'])
    assert len(transport.reports) == 1
    assert status == ['COMPLETE']
    assert '(500)' not in shown(response)


def test_server_report_lists_the_unconfirmed_draft_judgments():
    items = [{'stage': '답변 초안', 'draft': '{"answer_points": [{"text": "심사검토기간은 10영업일 이상입니다."}]}'},
             {'stage': '조사 판단', 'draft': '{"reason": {"text": "조사 이유"}}'}]
    value = pr.server_report('JUDGMENT_CONFLICT', ['상품관리준칙 제2-1조'], pr.draft_texts(items))
    text = pr.render('JUDGMENT_CONFLICT', ['상품관리준칙 제2-1조'], value)
    assert text.startswith('판단하기 어려운 지점입니다.')
    assert '확정 전' in text and '심사검토기간은 10영업일 이상입니다.' in text and '조사 이유' not in text
    assert '**여기서 판단하기 어렵습니다**' in text and pr.ASK in text


def test_a_saved_unread_link_reaches_the_report_and_the_screen(tree, tmp_path, monkeypatch):
    from semantic_runtime.legal_agent import connection_scope
    link = {'from_label': '모의승인규정 제1조(승인)', 'target_label': '모의승인규정 제2조(예외)',
            'relation_text': '예외를 정한 조문', 'reason': '이번 요청의 자동 읽기 대상에서 빠져서'}
    monkeypatch.setattr(connection_scope, 'unread_connections',
                        lambda inv: {'entries': [link], 'total': 1, 'meaning': 'fixture'})
    transport = Reporting()
    (response,), _ = serve(tree, tmp_path, transport, pending, monkeypatch)
    assert response.status_code == 200, response.text
    view = transport.reports[0]['view']
    assert view['connections'] == [{'from': link['from_label'], 'to': link['target_label'],
                                    'relation': link['relation_text'], 'why_not_read': link['reason']}]
    assert '연결을 따라가 볼까요' in transport.reports[0]['system']
    text = response.json()['answer']['text']
    # 2026-11-12: the unread link is a numbered failure point the next turn can name.
    assert '2. [이어진 조문] 읽으려다 건너뜀 — 모의승인규정 제2조(예외)' in text


def test_unread_links_are_listed_and_offered_as_the_next_step():
    links = [{'from': '상품위원회운영지침 제3조', 'to': '「상품관리준칙」 제2-1조', 'relation': '위임(관련 준칙)', 'why_not_read': '자동 읽기 대상에서 빠져서'}]
    value = pr.server_report('REVIEW_INCOMPLETE', ['상품위원회운영지침 제3조'], (), links)
    text = pr.render('REVIEW_INCOMPLETE', ['상품위원회운영지침 제3조'], value, links)
    assert '**이어서 확인할 수 있는 연결 (아직 읽지 않음)**' in text
    assert '- 상품위원회운영지침 제3조 → 「상품관리준칙」 제2-1조 (위임(관련 준칙))' in text
    assert value['decisions'][0] == '아래 연결 조문을 이어서 읽어 볼까요?'
    assert text.index('연결 (아직 읽지 않음)') < text.index('**어떻게 진행할까요?**')


def test_only_agent_stops_are_reported():
    assert pr.stop_kind(pending(None)) == 'REVIEW_INCOMPLETE'
    assert pr.stop_kind(unresolved(None)) == 'JUDGMENT_CONFLICT'
    assert pr.stop_kind(ProposalError('x')) == 'JUDGMENT_CONFLICT'
    assert pr.stop_kind(BudgetExhausted('x')) == 'LIMIT'
    assert pr.stop_kind(DeadlineExceeded('x')) == 'TIME_LIMIT'
    assert pr.stop_kind(TransportError('x', unknown=True)) == 'MODEL_NO_ANSWER'
    for other in (ContractError('x'), KeyError('x'), RuntimeError('x'), OSError('x')):
        assert pr.stop_kind(other) is None
    assert BudgetExhausted.http_status == 422


@pytest.mark.parametrize('status,number', [(422, False), (409, False), (502, False), (504, False), (500, True), (503, True)])
def test_screen_shows_a_number_only_for_a_real_server_fault(status, number):
    v = adapter.views()
    text = v.render(v.public_response({'error': 'x', '_gateway_status': status, 'request_id': 'r'}))
    assert (f'({status})' in text) == number
