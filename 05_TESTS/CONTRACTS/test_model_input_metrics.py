"""Input/output measurements on synthetic calls; no model or quality experiment."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from semantic_runtime import observability as obs
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.model_contract import request_metrics, response_length_metrics
from semantic_runtime.legal_agent.errors import ProposalError, TransportError
from semantic_runtime.legal_agent.repository import encoded
from semantic_runtime.request_report import live_log, capture_events, format_readable_report
from test_legal_agent_double_harness import work, PROFILE, wire
from test_investigation_completion_adr0678 import completed_app, tree


def test_unicode_messages_schema_and_canonical_bytes_are_distinct():
    request = {'messages': [{'role': 'system', 'content': '가😀'},
        {'role': 'user', 'content': '질문\n답'}, {'role': 'user', 'content': '수정'}],
        'response_format': {'type': 'json_schema', 'schema': {'enum': ['가']}}, 'max_tokens': 6400}
    before = deepcopy(request)
    metrics = request_metrics(request)
    assert metrics['input_content_chars'] == 8
    assert metrics['input_content_utf8_bytes'] == 23
    assert metrics['input_system_chars'] == 2 and metrics['input_user_chars'] == 6
    assert metrics['input_message_count'] == 3
    assert metrics['request_bytes'] == len(encoded(request).encode())
    assert metrics['response_format_utf8_bytes'] == len(encoded(request['response_format']).encode())
    assert not metrics['context_limit_known'] and request == before
    assert '질문' not in json.dumps(metrics, ensure_ascii=False)


@pytest.mark.parametrize('finish,usage,diagnosis,reached', [
    ('length', {'prompt_tokens': 15186, 'completion_tokens': 6400}, 'output_cap_reached', True),
    ('length', {'prompt_tokens': 15186, 'completion_tokens': 1000}, 'length_stop_cause_unknown', False),
    ('length', {}, 'length_stop_cause_unknown', None),
    ('length', {'completion_tokens': True}, 'length_stop_cause_unknown', None),
    ('content_filter', {'completion_tokens': 2}, 'content_filter', False),
    ('stop', {'completion_tokens': 6400}, 'no_length_stop', True),
    (None, {}, 'unknown', None),
])
def test_length_never_invents_model_context_limit(finish, usage, diagnosis, reached):
    result = response_length_metrics({'max_tokens': 6400},
        {'choices': [{'finish_reason': finish}], 'usage': usage})
    assert result['length_diagnosis'] == diagnosis and result['output_cap_reached'] is reached
    assert result['context_limit_known'] is False
    assert result['prompt_plus_max_tokens'] == (21586 if 'prompt_tokens' in usage else None)


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_repair_counts_live_log_receipt_and_rejected_output_remain_consistent(work, tmp_path, repair_succeeds):
    sent = []
    class Transport:
        binding = PROFILE['model_binding']
        def send_once(self, *, body, ticket):
            sent.append(deepcopy(body))
            response = wire({'ok': True})
            response['body_json']['choices'][0]['finish_reason'] = 'stop' if len(sent) == 2 and repair_succeeds else 'length'
            response['body_json']['usage'] = {'prompt_tokens': 100 + len(sent), 'completion_tokens': 6400}
            return response
    profile = {**PROFILE, 'max_output_tokens': 6400, 'max_schema_repairs': 1,
        'candidate_navigation': {'completion_contract': True}}
    gateway = ModelGateway(work, work.context, profile, {}, Transport(),
        message_protocol=SimpleNamespace(schema=lambda _: {}, validate=lambda *a: None),
        system='PRIVATE SYSTEM', prompts={'investigate': 'PRIVATE PROMPT'})
    view = work.save_view('investigate', {'source_stage': 'source-query-plan', 'question': 'PRIVATE QUESTION'}, [])
    with live_log(tmp_path/'logs', 'metrics') as (path, handler), capture_events('metrics') as events:
        with obs.context(request_id='metrics'):
            if repair_succeeds:
                assert gateway.generate('investigate', view, 'fixture') == {'ok': True}
            else:
                with pytest.raises(ProposalError): gateway.generate('investigate', view, 'fixture')
        assert handler.writer.drain(2)
        output = path.read_text()
    assert len(sent) == 2 and work.budget()['model_reserved'] == 2
    starts = [e for e in events if e['event'] == 'model.attempt.started']
    assert starts[0]['input_message_count'] == 2 and starts[1]['input_message_count'] == 3
    assert starts[1]['input_content_chars'] > starts[0]['input_content_chars']
    assert len({e['logical_call_id'] for e in starts}) == 1
    assert len({e['attempt_id'] for e in starts}) == 2
    receipts = [json.loads(r[0]) for r in work.db.execute('SELECT receipt_json FROM model_attempt ORDER BY attempt_no')]
    for request, receipt in zip(sent, receipts):
        assert receipt['input_metrics']['request_bytes'] == len(encoded(request).encode())
    assert 'length_diagnosis=output_cap_reached' in output
    assert 'context_limit_known=false' in output and 'source_stage=source-query-plan' in output
    assert 'prompt_plus_max_tokens=6501' in output
    assert 'PRIVATE' not in output and 'PRIVATE' not in json.dumps(events)
    assert 'input_content_chars=' in format_readable_report({'service_events': events})
    invalid = [json.loads(r[0]) for r in work.db.execute("SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID'")]
    assert len(invalid) == (1 if repair_succeeds else 2)
    assert invalid[0]['input_metrics']['length_diagnosis'] == 'output_cap_reached'
    assert not work.heads('finding')


def test_failed_transport_still_records_input_size_without_usage(work, tmp_path):
    class Transport:
        binding = PROFILE['model_binding']
        def send_once(self, **kwargs): raise TransportError('timeout', unknown=True)
    gateway = ModelGateway(work, work.context, PROFILE, {}, Transport(),
        message_protocol=SimpleNamespace(schema=lambda _: {}, validate=lambda *a: None))
    view = work.save_view('investigate', {'question': '모의 질문'}, [])
    with capture_events('metrics-failed') as events, obs.context(request_id='metrics-failed'):
        with pytest.raises(TransportError): gateway.generate('investigate', view, 'fixture')
    start = next(e for e in events if e['event'] == 'model.attempt.started')
    assert start['input_content_chars'] > 0
    assert not any(e['event'] == 'model.attempt.received' for e in events)
    row = work.db.execute('SELECT status,request_json FROM model_attempt').fetchone()
    assert row[0] == 'UNKNOWN' and request_metrics(json.loads(row[1]))['request_bytes'] == start['request_bytes']


@pytest.mark.parametrize('fail', [False, True])
def test_real_native_api_preserves_publication_boundary_and_records_sizes(completed_app, monkeypatch, fail):
    api, transport, runtime = completed_app
    original = transport.send_once
    def send(**kwargs):
        response = original(**kwargs)
        response['body_json']['usage'] = {'prompt_tokens': 321, 'completion_tokens': kwargs['body']['max_tokens'] if fail else 10}
        response['body_json']['choices'][0]['finish_reason'] = 'length' if fail else 'stop'
        return response
    monkeypatch.setattr(transport, 'send_once', send)
    result = api.post('/v1/rag/ask', json={'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 's', 'request_id': 'metrics-api'})
    if fail:
        assert result.status_code >= 400 and not result.json().get('answer'), result.text
    else:
        assert result.status_code == 200 and result.json()['answer']['claims'], result.text
    rows = []
    for journal in (runtime/'legal-agent/runs').glob('*/*/journal.sqlite'):
        with sqlite3.connect(journal) as db:
            rows.extend(db.execute('SELECT request_json,receipt_json FROM model_attempt').fetchall())
    assert rows
    for request, receipt in rows:
        metrics = json.loads(receipt)['input_metrics']
        assert metrics['prompt_tokens'] == 321 and not metrics['context_limit_known']
        assert metrics['request_bytes'] == len(encoded(json.loads(request)).encode())
