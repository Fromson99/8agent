"""Thinking diagnostics must survive redaction without exposing model text."""
import json
import logging
from types import SimpleNamespace

import pytest

from semantic_runtime import observability as obs
from semantic_runtime.legal_agent.gateway import ModelGateway, _response_diagnostics


@pytest.mark.parametrize('reasoning_key', ['reasoning', 'reasoning_content', 'thinking'])
def test_reasoning_presence_is_reported_without_content(reasoning_key):
    body = {'choices': [{'message': {'content': '{"ok":true}', reasoning_key: 'PRIVATE THOUGHT'},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 3000, 'completion_tokens': 1200, 'total_tokens': 4200,
                      'completion_tokens_details': {'reasoning_tokens': 900},
                      'prompt_tokens_details': {'cached_tokens': 2000}}}
    fields = _response_diagnostics(body)
    record = logging.LogRecord('genos.fixture', logging.INFO, __file__, 1, 'model.attempt.received', (), None)
    record.fields = fields
    formatted = obs.JsonFormatter().format(record)
    rendered = json.loads(formatted)
    assert rendered['thinking_observation'] == 'reasoning_reported'
    assert rendered['reasoning_nonempty'] is True
    assert rendered['reasoning_tokens'] == 900 and rendered['prompt_tokens'] == 3000
    assert rendered['completion_tokens'] == 1200 and rendered['cached_tokens'] == 2000
    assert 'PRIVATE THOUGHT' not in formatted and '{"ok":true}' not in formatted


@pytest.mark.parametrize('body', [None, {}, {'choices': []}, {'usage': [], 'choices': [None]},
    {'choices': [{'message': {'content': 'answer'}}], 'usage': {'completion_tokens': 20}}])
def test_missing_metadata_is_unknown_never_off(body):
    fields = _response_diagnostics(body)
    assert fields['thinking_observation'] == 'unknown'
    assert fields['reasoning_tokens'] is None


def test_empty_channel_marker_does_not_claim_reasoning_is_running():
    fields = _response_diagnostics({'choices': [{'message': {
        'content': '<|channel>thought\n<channel|>answer'}}]})
    assert fields['thought_channel_marker_present'] is True
    assert fields['thinking_observation'] == 'unknown'
    fields = _response_diagnostics({'choices': [{'message': {'reasoning': '', 'content': 'answer'}}],
                                   'usage': {'completion_tokens_details': {'reasoning_tokens': 0}}})
    assert fields['thinking_observation'] == 'no_reasoning_reported'


@pytest.mark.parametrize('unsafe', ['SECRET', {'api_key': 'SECRET'}, ['SECRET'], True, -1, 1.2])
def test_count_field_cannot_bypass_secret_filter(unsafe):
    assert obs._safe_fields({'prompt_tokens': unsafe, 'reasoning_tokens': unsafe}) == {}
    assert obs._safe_fields({'access_token': 12, 'api_key': 12}) == {}


def test_single_send_records_request_flag_and_response_without_changing_body(monkeypatch):
    captured = []
    monkeypatch.setattr(obs, 'event', lambda logger, name, **fields: captured.append((name, obs._safe_fields(fields))))
    binding = {'model': 'synthetic', 'trust_zone': 'internal', 'max_input_bytes': 10000}
    sent = []
    class Transport:
        def send_once(self, *, body, ticket):
            sent.append(body)
            return {'status_code': 200, 'response_bytes': 300, 'body_json': {
                'model': 'synthetic', 'choices': [{'message': {'content': '{"ok":true}',
                            'reasoning': 'PRIVATE THOUGHT'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 20,
                          'completion_tokens_details': {'reasoning_tokens': 8}}}}
    transport = Transport(); transport.binding = binding
    context = SimpleNamespace(binding={'export_allowed': False}, run_id='fixture-run', remaining=lambda: 60)
    repo = SimpleNamespace(reserve_attempt=lambda *args, **kw: 'fixture-attempt',
        attempt_sent=lambda *args: None, finish_attempt=lambda *args: 'SUCCEEDED')
    protocol = SimpleNamespace(schema=lambda name: {}, validate=lambda name, value: None)
    gateway = ModelGateway(repo, context, {'model_binding': binding, 'max_output_tokens': 6400,
        'max_transport_retries': 0, 'max_schema_repairs': 0}, {}, transport,
        message_protocol=protocol, system='PRIVATE SYSTEM', prompts={'investigate': 'PRIVATE PROMPT'})
    assert gateway.generate('investigate', {'question': 'PRIVATE QUESTION'}, 'fixture') == {'ok': True}
    assert len(sent) == 1 and sent[0]['chat_template_kwargs'] == {'enable_thinking': False}
    assert sent[0]['stream'] is False
    started = next(fields for name, fields in captured if name == 'model.attempt.started')
    received = next(fields for name, fields in captured if name == 'model.attempt.received')
    assert started['thinking_requested'] is False and started['max_tokens'] == 6400
    assert received['thinking_observation'] == 'reasoning_reported'
    assert received['prompt_tokens'] == 12 and received['reasoning_tokens'] == 8
    assert 'PRIVATE' not in json.dumps(captured)
