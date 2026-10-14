"""Timing export uses only metadata from a content-bearing GENOS report."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "06_TOOLS/COMMANDS/genos_request_timing.py"
SPEC = importlib.util.spec_from_file_location("genos_request_timing", SCRIPT)
timing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(timing)


def test_timing_txt_reports_attempts_and_never_copies_content():
    report = {
        "schema_version": "genos-request-report-v1", "request_id": "req-1", "run_id": "run-1",
        "request": {"question": "SECRET QUESTION"},
        "result": {"status": 200, "body": {"answer": {"text": "SECRET ANSWER"}}},
        "service_events": [
            {"event": "request.started", "ts": "2026-09-23T00:00:00Z"},
            {"event": "step.finished", "step": "runtime.bootstrap", "duration_ms": 900},
            {"event": "model.attempt.received", "phase": "investigate", "attempt_id": "M1", "duration_ms": 2100, "http_status": 200},
            {"event": "model.attempt.failed", "phase": "investigate", "attempt_id": "M2", "duration_ms": 1000, "http_status": 429},
            {"event": "request.finished", "ts": "2026-09-23T00:00:05Z", "duration_ms": 5000},
        ],
        "journal": {"status": "FOUND", "timeline": [{"event": {"kind": "SEMANTIC_REPAIR"}}],
                    "state": {"run": [{"status": "COMPLETED", "gate": "CLARIFY"}]}},
    }
    output = timing.summarize(report, [
        {"event": "code_serving.request.started", "timeout_seconds": 4},
        {"event": "workflow.request.finished", "tm_total": 5.2},
    ])
    assert "code_serving_wall: 5.000s" in output
    assert "investigate: 2회, 합계 3.100s" in output
    assert "SEMANTIC_REPAIR: 1회" in output
    assert "workflow.request.finished" in output
    assert "코드서빙 처리 시간이 워크플로우 대기 상한보다 길었음" in output
    assert "SECRET QUESTION" not in output
    assert "SECRET ANSWER" not in output


def test_return_boundary_takes_precedence_over_internal_result_ready():
    report = {'schema_version': 'genos-request-report-v1', 'service_events': [
        {'event': 'request.finished', 'duration_ms': 230000},
        {'event': 'request.returning', 'duration_ms': 230100},
    ]}
    output = timing.summarize(report)
    assert 'code_serving_wall: 230.100s' in output
    assert 'timing_boundary: request.returning' in output


def model_report():
    """Three saved calls, with the last failing after evidence was added."""
    report = {'schema_version': 'genos-request-report-v1', 'request_id': 'req-1',
              'run_id': 'run-1', 'journal': {'status': 'FOUND', 'timeline': [], 'state': {}},
              'service_events': [{'event': 'model.attempt.failed', 'attempt_id': 'M3',
                  'duration_ms': 7567, 'http_status': 500, 'retryable': True, 'retry_scheduled': False}]}
    for i, stage in enumerate(('request-entry', 'source-law-navigation-1', 'source-law-navigation-2'), 1):
        request = {'model': '2650', 'max_tokens': 6400, 'temperature': 0, 'stream': False,
            'chat_template_kwargs': {'enable_thinking': False},
            'messages': [{'role': 'system', 'content': 'PRIVATE SYSTEM PROMPT'},
                {'role': 'user', 'content': json.dumps({'view': {'source_stage': stage,
                    'articles': ['PRIVATE ARTICLE TEXT' * i]}})}],
            'response_format': {'type': 'json_schema', 'json_schema': {'strict': True,
                'schema': {'type': 'object', 'properties': {'PRIVATE ARTICLE KEY':
                    {'enum': ['PRIVATE TITLE'] if i < 3 else []}}}}},
            'authorization': 'PRIVATE AUTH VALUE'}
        response = {'status_code': 500 if i == 3 else 200, 'response_bytes': 21 if i == 3 else 1500,
            'body_text': 'Internal Server Error' if i == 3 else None,
            'body_json': None if i == 3 else {'model': '2650',
                'usage': {'prompt_tokens': 1082 if i == 1 else 10145, 'completion_tokens': 223},
                'choices': [{'message': {'content': 'PRIVATE ANSWER'}}]}}
        attempt = {'attempt_id': f'M{i}', 'view_id': f'V{i}', 'created_seq': i * 2,
                   'status': 'FAILED' if i == 3 else 'SUCCEEDED', 'request': request,
                   'response': response}
        report['journal']['timeline'].append({'event': {'kind': 'ATTEMPT_RESERVED'},
            'created_records': [{'table': 'model_attempt', 'record': attempt}]})
    return report


def test_models_only_distinguishes_successful_context_from_unknown_failed_tokens():
    report = model_report()
    output = timing.summarize_models(report)
    assert '#02 source-law-navigation-1 | HTTP 200 | SUCCEEDED' in output
    assert '#03 source-law-navigation-2 | HTTP 500 | FAILED | 7.567s' in output
    assert 'prompt_tokens=10145' in output
    assert 'prompt_tokens=unknown' in output
    assert 'empty_enums=1' in output
    assert 'schema_same=False' in output
    assert '직전 성공 #02 비교: model_same=True' in output
    assert 'retryable=True retry_scheduled=False' in output
    assert 'error_body=Internal Server Error' in output
    assert 'PRIVATE' not in output
    assert '토큰 수가 아닙니다' in output


def test_models_only_handles_encoded_columns_state_records_and_redacts_error_body():
    report = model_report()
    records = [item['created_records'][0]['record'] for item in report['journal']['timeline']]
    last = records[-1]
    last['response']['body_text'] = 'PRIVATE KEY: abc; maximum context exceeded'
    for row in records:
        for key in ('request', 'response'):
            row[key + '_json'] = json.dumps(row.pop(key))
    report['journal']['state']['model_attempt'] = records
    output = timing.summarize_models(report)
    assert '모델 호출 기록: 3개' in output  # no duplicate timeline/state rows
    assert 'error_hints=maximum context' in output
    assert 'PRIVATE' not in output


def test_models_only_missing_journal_does_not_claim_zero_model_calls():
    report = model_report()
    report['journal'] = {'status': 'NOT_FOUND'}
    output = timing.summarize_models(report)
    assert '실제 요청 비교 불가' in output
    assert 'M3 model.attempt.failed HTTP 500' in output


def test_models_only_cli_preserves_original_and_refuses_overwrite(tmp_path):
    source, output = tmp_path / 'report.json', tmp_path / 'diag.txt'
    raw = json.dumps(model_report(), ensure_ascii=False).encode()
    source.write_bytes(raw)
    args = ['--report', str(source), '--output', str(output), '--models-only']
    assert timing.main(args) == 0
    assert source.read_bytes() == raw
    assert output.stat().st_mode & 0o777 == 0o600
    first = output.read_bytes()
    with pytest.raises(FileExistsError):
        timing.main(args)
    assert output.read_bytes() == first
    assert source.read_bytes() == raw


def test_models_only_rejects_response_sidecar():
    with pytest.raises(ValueError, match='llm_raw'):
        timing.summarize_models({'raw_log_revision': 'llm-raw-log-20260929-r1'})


@pytest.mark.parametrize('finish,body,expected', [
    ('stop', '{"paragraphs":[{"text":"PRIVATE ANSWER"}]}', 'parsed'),
    (None, '{"paragraphs":[{"text":"PRIVATE', 'incomplete_or_invalid'),
    ('length', '', 'empty'),
    ('PRIVATE FINISH', '{}', 'parsed'),
])
def test_saved_stream_diagnostics_distinguish_partial_content_without_claiming_done(finish, body, expected):
    report = model_report()
    row = report['journal']['timeline'][-1]['created_records'][0]['record']
    row['request']['stream'] = True
    row['status'] = 'UNKNOWN'
    row['response'] = {'status_code': None, 'body_json': None, 'stream_complete': False,
        'response_bytes': 6069, 'stream_events': [
            {'model': '2650', 'choices': [{'index': 0, 'delta': {'content': body}}]},
            {'model': '2650', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
            {'choices': [], 'usage': {'prompt_tokens': 900, 'completion_tokens': 22}}]}
    output = timing.summarize_models(report)
    assert 'sse_events=3' in output and 'response_bytes=6069' in output
    assert 'content_json=' + expected in output
    assert 'done_marker=unknown' in output and 'stream_complete=False' in output
    assert 'stream_prompt_tokens=900 stream_completion_tokens=22' in output
    assert 'last_event_has_choices=False last_event_has_usage=True' in output
    assert 'PRIVATE' not in output
    assert ('"stop": 1' if finish == 'stop' else 'none_recorded' if finish is None
            else '"length": 1' if finish == 'length' else '"other": 1') in output


def test_saved_stream_missing_empty_malformed_and_tool_channel_do_not_disclose_content():
    request = {'stream': True, 'model': 'fixture'}
    assert 'sse_events=unknown' in '\n'.join(timing._stream_summary({}, request))
    assert 'sse_events=0' in '\n'.join(timing._stream_summary({'stream_events': []}, request))
    response = {'stream_events': [None, {'error': 'PRIVATE ERROR', 'model': 'PRIVATE MODEL',
        'choices': [None, {'index': 1, 'delta': {'content': 'PRIVATE OTHER CHOICE'}},
            {'index': 0, 'message': {'content': 'PRIVATE MESSAGE'},
             'finish_reason': {'PRIVATE': 'FINISH'}, 'delta': {
                 'reasoning_content': 'PRIVATE REASONING', 'tool_calls': [
                     {'index': 0, 'function': {'arguments': '{"PRIVATE":"ARGUMENT"}'}},
                     {'index': 1, 'function': {'arguments': 'PRIVATE OTHER CALL'}}]}}]}]}
    output = '\n'.join(timing._stream_summary(response, request))
    assert 'PRIVATE' not in output
    assert 'tool_arguments_json=parsed' in output
    assert 'invalid_events=1 error_events=1' in output
    assert 'model_mismatches=1' in output
    assert 'nonzero_choices=1 nonzero_tool_calls=1' in output
    assert 'done_marker=unknown' in output
