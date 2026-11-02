"""Offline gateway faults: preserve binding errors without a transport retry."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_legal_agent_double_harness import work, PROFILE, wire
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import provider_routing
from semantic_runtime.legal_agent.bounded_source_session import _Protocol
from semantic_runtime.legal_agent.errors import ContractError, TransportError
from semantic_runtime.legal_agent.gateway import ModelGateway


SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}
ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text())


@pytest.mark.parametrize('model', ['wrong-model', None])
@pytest.mark.parametrize('switch_first', [False, True])
def test_response_binding_failure_preserves_cause_budget_and_journal(work, model, switch_first):
    response = wire({'ok': True})
    if model is None:
        response['body_json'].pop('model')
    else:
        response['body_json']['model'] = model
    original = deepcopy(response)

    class Transport:
        binding = PROFILE['model_binding']
        provider_policy = POLICY
        routing_hash = digest(POLICY)

        def __init__(self):
            self.sent = []

        def send_once(self, *, body, ticket):
            self.sent.append(deepcopy(ticket))
            if switch_first and len(self.sent) == 1:
                raise TransportError('known rejection', retryable=True, unknown=False,
                    response={'status_code': 429, 'acceptance': 'KNOWN_REJECTED'})
            return response

    transport = Transport()
    gateway = ModelGateway(work, work.context,
        {**PROFILE, 'max_transport_retries': 0, 'max_schema_repairs': 0}, {}, transport,
        message_protocol=_Protocol(SCHEMA), system='synthetic')
    view = work.save_view('investigate', {'synthetic': True}, [])
    with pytest.raises(ContractError, match='actual response model differs from pinned model'):
        gateway.generate('investigate', view, 'BoundedSourceDecision')
    assert response == original
    assert len(transport.sent) == work.budget()['model_reserved'] == 1 + int(switch_first)
    state, _ = provider_routing.current(work, POLICY, transport.routing_hash, work.context.binding_hash)
    assert state['switches'] == int(switch_first)
    # SUCCEEDED here records HTTP completion, not acceptance of the proposal.
    statuses = [r[0] for r in work.db.execute('SELECT status FROM model_attempt ORDER BY rowid')]
    assert statuses == (['FAILED'] if switch_first else []) + ['SUCCEEDED']
    assert not work.heads('finding')
    # A fresh gateway cannot treat the rejected response as an accepted decision.
    with pytest.raises(ContractError, match='unknown'):
        gateway.generate('investigate', view, 'BoundedSourceDecision')
    assert len(transport.sent) == 1 + int(switch_first)
