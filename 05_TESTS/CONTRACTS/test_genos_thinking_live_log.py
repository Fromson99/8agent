"""Exercise the live shared .log that GENOS operators actually view."""
import json
from types import SimpleNamespace

import pytest

from semantic_runtime import observability as obs
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.request_report import live_log, capture_events, format_readable_report


@pytest.mark.parametrize('reasoning,expected,token_value', [
    ({}, 'unknown', 'null'),
    ({'reasoning': ''}, 'no_reasoning_reported', '0'),
    ({'reasoning': 'PRIVATE THOUGHT'}, 'reasoning_reported', '8'),
])
def test_model_call_reaches_actual_live_log_and_summary_without_private_text(tmp_path, reasoning, expected, token_value):
    binding = {'model': 'synthetic', 'trust_zone': 'internal', 'max_input_bytes': 10000}
    class Transport:
        def send_once(self, *, body, ticket):
            usage = {'prompt_tokens': 300, 'completion_tokens': 20}
            if reasoning:
                usage['completion_tokens_details'] = {'reasoning_tokens': 8 if reasoning['reasoning'] else 0}
            return {'status_code': 200, 'response_bytes': 500, 'body_json': {'model': 'synthetic',
                'choices': [{'message': {'content': '{"ok":true}', **reasoning}, 'finish_reason': 'stop'}],
                'usage': usage}}
    transport = Transport(); transport.binding = binding
    repo = SimpleNamespace(reserve_attempt=lambda *a, **kw: 'fixture-attempt',
        attempt_sent=lambda *a: None, finish_attempt=lambda *a: 'SUCCEEDED')
    context = SimpleNamespace(binding={'export_allowed': False}, run_id='a'*32, remaining=lambda: 60)
    protocol = SimpleNamespace(schema=lambda name: {}, validate=lambda name, value: None)
    gateway = ModelGateway(repo, context, {'model_binding': binding, 'max_output_tokens': 6400,
        'max_transport_retries': 0, 'max_schema_repairs': 0}, {}, transport,
        message_protocol=protocol, system='PRIVATE SYSTEM', prompts={'investigate': 'PRIVATE PROMPT'})
    with live_log(tmp_path, 'req-thinking-live') as (path, handler), capture_events('req-thinking-live') as events:
        with obs.context(request_id='req-thinking-live'):
            assert gateway.generate('investigate', {'question': 'PRIVATE QUESTION'}, 'fixture') == {'ok': True}
        assert handler.writer.drain(2)
        output = path.read_text()
    assert 'live_diagnostics_version=thinking-live-20260928-r3' in output
    assert 'thinking_requested=false' in output and 'thinking_control_present=true' in output
    assert 'stream_requested=false' in output and 'max_tokens=6400' in output
    assert 'prompt_tokens=300' in output and 'completion_tokens=20' in output
    assert 'reasoning_tokens='+token_value in output
    assert 'cached_tokens=null' in output
    assert 'thinking_observation='+expected in output and 'finish_reason=stop' in output
    assert 'PRIVATE' not in output and 'PRIVATE' not in json.dumps(events)
    text = format_readable_report({'service_events': events})
    assert 'thinking_requested=false' in text and 'reasoning_tokens='+token_value in text
    assert 'thinking_observation='+expected in text and 'PRIVATE' not in text


def test_live_count_and_boolean_fields_refuse_credential_shaped_values(tmp_path):
    logger = obs.get_logger('diagnostic-privacy')
    with live_log(tmp_path, 'req-privacy') as (path, handler):
        with obs.context(request_id='req-privacy'):
            obs.event(logger, 'model.attempt.received', prompt_tokens='PRIVATE TOKEN',
                      reasoning_tokens={'api_key': 'PRIVATE KEY'}, reasoning_chars='PRIVATE_TEXT',
                      thinking_requested='PRIVATE_TEXT', thinking_observation='PRIVATE_TEXT',
                      finish_reason='PRIVATE_TEXT')
        assert handler.writer.drain(2)
        output = path.read_text()
    assert 'model.attempt.received' in output and 'PRIVATE' not in output
