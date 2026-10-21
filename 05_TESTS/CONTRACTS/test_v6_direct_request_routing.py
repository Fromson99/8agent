"""Synthetic v6 ingress contracts; no live model or routing-quality experiment."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import source_query_planning as planning
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_structure_first_search import structured_generation
from test_unified_legal_agent import ScriptedTransport, ok
from test_memory_runtime_v2 import command


class RoutingTransport(ScriptedTransport):
    def __init__(self):
        super().__init__()
        self.mode = 'DIRECT'
        self.views = []
        self.answer = '법률·규정이나 문서에 관한 질문을 입력해 주세요.'

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage') == 'source-request-route':
            self.phases.append('source-request-route')
            self.views.append(view)
            return wire({'mode': self.mode, 'answer': self.answer if self.mode == 'DIRECT' else '',
                         'reason': '모의 입력 분류'})
        return super().send_once(body=body, ticket=ticket)


@pytest.fixture
def routed_app(tmp_path, structured_generation):
    transport = RoutingTransport()
    app = create_app(tmp_path, structured_generation, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile={**settings(), 'max_model_attempts':40},
        legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id':'u', 'team_id':'risk_team', 'document_ids':['d']})
    with TestClient(app) as client:
        yield client, transport, tmp_path/'90_RUNTIME/semantic'


@pytest.mark.parametrize('capture', [True, False])
@pytest.mark.parametrize('question', ['Type Your Message', 'asdf', 'ㅋㅋㅋ', '????', '오늘 날씨 어때?', '김치찌개 만드는 법'])
def test_direct_input_never_resolves_case_or_acquires_originals(routed_app, capture, question, monkeypatch):
    client, transport, runtime = routed_app
    client.app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture'] = capture
    from semantic_runtime.legal_agent.procedure_memory import ProcedureMemory
    def forbid_command_replay(*args, **kwargs):
        raise AssertionError('direct input must exit before procedure lookup')
    monkeypatch.setattr(ProcedureMemory, 'lookup', forbid_command_replay)
    body = {'question':question, 'session_id':'s', 'request_id':'direct'}
    result = ok(client.post('/v1/rag/ask', json=body))
    assert result['answer']['text'] == transport.answer
    assert result['answer']['claims'] == []
    assert result['selection']['selected'] == []
    assert result['assembly']['context'] == []
    assert result['assembly']['term_agent']['request_routing']['mode'] == 'DIRECT'
    assert result['executed'] == [] and result['question_id'] is None
    assert transport.phases == ['source-request-route']
    assert 'current_goals' in transport.views[0] and transport.views[0]['current_goals'] == []
    assert 'allowed_documents' not in transport.views[0] and 'document_ids' not in transport.views[0]
    journal = next((runtime/'legal-agent/runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT count(*) FROM observation').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM evidence_unit').fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM event WHERE kind='CASE_JUDGMENT_ACCEPTED'").fetchone()[0] == 0
        assert db.execute('SELECT status FROM run').fetchone()[0] == 'COMPLETED'
    with sqlite3.connect(runtime/'case-memory'/('cases-v4.sqlite' if capture else 'cases-v3.sqlite')) as db:
        assert db.execute('SELECT count(*) FROM goal').fetchone()[0] == 0
    again = ok(client.post('/v1/rag/ask', json=body))
    assert again['answer'] == result['answer'] and again['run_id'] == result['run_id']
    assert again['execution_stats']['llm_calls'] == 0
    assert transport.phases == ['source-request-route']


def test_noise_keeps_current_case_and_next_short_correction(routed_app):
    client, transport, runtime = routed_app
    transport.mode = 'CASE'
    first = ok(client.post('/v1/rag/ask', json={'question':'안녕, 모의승인규정 제1조의 승인 대상은?',
                                             'session_id':'s', 'request_id':'first'}))
    assert first['answer']['claims']
    gid = first['question_id']
    path = runtime/'case-memory/cases-v4.sqlite'
    with sqlite3.connect(path) as db:
        before = db.execute('SELECT id,state,revision,status FROM goal').fetchall()
    transport.mode = 'DIRECT'
    transport.phases.clear()
    direct = ok(client.post('/v1/rag/ask', json={'question':'Type Your Message', 'session_id':'s','request_id':'noise'}))
    assert direct['answer']['claims'] == [] and transport.phases == ['source-request-route']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT id,state,revision,status FROM goal').fetchall() == before
    assert transport.views[-1]['current_goals'][0]['task'] == '모의승인규정 제1조의 승인 대상은?'
    transport.mode = 'CASE'
    transport.command = command('FACT_UPDATE', target=gid, facts=[{'name':'대상','value':'B'}])
    corrected = ok(client.post('/v1/rag/ask', json={'question':'대상을 B로 바꿔', 'session_id':'s','request_id':'correct'}))
    assert corrected['question_id'] == gid and corrected['executed'] == ['ASSESS','COMPOSE']
    assert corrected['answer']['claims']


def test_received_model_output_and_direct_choice_are_both_logged(routed_app,tmp_path):
    from semantic_runtime.request_report import live_log
    client, transport, runtime = routed_app
    result = ok(client.post('/v1/rag/ask',json={'question':'Type Your Message',
                                             'session_id':'s','request_id':'logged'}))
    with live_log(tmp_path/'logs','logged',runtime) as (path,handler):
        handler.run_id=result['run_id']
        handler.poll_journal()
        output=path.read_text()
    assert 'MODEL RAW RESPONSE' in output and '"mode": "DIRECT"' in output
    assert '대화 입력 분류' in output and '판단: 안내 답변' in output
    assert '이유: 모의 입력 분류' in output
    assert '모델이 별도 이유를 제공하지 않음' not in output


@pytest.mark.parametrize('reply', [
    {'mode':'DIRECT','answer':' ','reason':'안내'},
    {'mode':'CASE','answer':'법률 답변을 바로 한다','reason':'질문'},
    {'mode':'DIRECT','answer':'질문을 입력해 주세요.','reason':' '},
])
def test_invalid_route_is_rejected(reply):
    with pytest.raises(ValueError):
        planning.validate_case_routing(reply)
