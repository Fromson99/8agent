"""ADR-1504: every request that ended with a published progress report after an unknown model outcome
got HTTP 502 when the same request arrived again (8 of 8): the session was opened before the saved
response was read and the resume check refused it ("previous request has an unknown model outcome").
The answered request now returns its saved response; the unknown call is still never sent again."""
import json

from fastapi.testclient import TestClient

from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_answer
from semantic_runtime.legal_agent.errors import TransportError
from test_progress_report import Reporting
from test_guided_continue_bounds import NAMED
from test_legal_agent_double_harness import ROOT
from test_multiturn_structured_scope import tree  # noqa: F401 - fixture


class NoAnswer(Reporting):
    """The guided answer call has an unknown outcome (the provider never answered)."""
    def __init__(self):
        super().__init__();self.answer_calls = 0

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        if (view.get('source_stage') or view['phase']) == guided_answer.PHASE:
            self.answer_calls += 1
            raise TransportError('absolute model request deadline exceeded', unknown=True)
        return super().send_once(body=body, ticket=ticket)


def test_answered_request_after_an_unknown_call_returns_its_saved_response(tree, tmp_path):
    gen, idx = tree
    transport = NoAnswer()
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=tmp_path / 'runtime',
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    body = {'session_id': 's', 'request_id': '1', 'question': NAMED}
    with TestClient(app, raise_server_exceptions=False) as api:
        first = api.post('/v1/rag/ask', json=body)
        assert first.status_code == 200, first.text
        calls = transport.answer_calls
        assert calls == 1
        again = api.post('/v1/rag/ask', json=body)
    assert again.status_code == 200, again.text
    assert again.json()['answer'] == first.json()['answer']
    assert transport.answer_calls == calls, 'the unknown answer call is not sent again'
