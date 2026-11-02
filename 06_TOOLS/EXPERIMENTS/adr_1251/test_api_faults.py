import os, json, sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_unit_fulltext_adaptive_read import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import PROFILE
from test_serving_provider import CFG, HASH
from test_unified_legal_agent import ScriptedTransport
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.errors import TransportError

@pytest.mark.parametrize('failure', ['deadline', 'untyped'])
def test_native_api_preserves_failure_and_unknown(tree, tmp_path, failure):
    gen, idx = tree
    class Transport(ScriptedTransport):
        binding = PROFILE['model_binding']
        provider_policy = CFG
        routing_hash = HASH
        def __init__(self): self.sent = 0
        def send_once(self, **kwargs):
            self.sent += 1
            if failure == 'untyped': raise TypeError('synthetic adapter failure')
            error = TransportError('synthetic deadline', unknown=True)
            error.code = 'MODEL_DEADLINE_EXCEEDED'
            error.http_status = 504
            raise error
    t = Transport()
    profile = {**settings(), 'model_binding': t.binding, 'max_output_tokens': None,
        'max_model_attempts': 40, 'max_transport_retries': 0,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True, 'completion_contract': True}}
    principal = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']}
    app = create_app(tmp_path, gen, contracts_root=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']),
        provider=object(), implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=t, memory_identity=lambda _: principal)
    app.state.pipeline.term_agent.unit_fulltext = idx
    try:
        with TestClient(app) as api:
            response = api.post('/v1/rag/ask', json={'question': '모의승인규정 제1조 승인 기준은?',
                'session_id': 's', 'request_id': 'r1', 'team_id': 'risk_team', 'document_ids': ['d']})
            assert response.status_code == (504 if failure == 'deadline' else 502), response.text
            assert 'AttributeError' not in response.text
        assert t.sent == 1
        states = []
        for path in tmp_path.rglob('journal.sqlite'):
            with sqlite3.connect(path) as db:
                states.extend(row[0] for row in db.execute('SELECT status FROM model_attempt'))
        assert states == ['UNKNOWN']
    finally:
        app.state.pipeline.store.close()
