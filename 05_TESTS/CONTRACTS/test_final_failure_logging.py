"""Failure response schema stays connected to the shared log and journal."""
import json
import threading
from contextlib import contextmanager

import pytest

from semantic_runtime import request_report as rr
from semantic_runtime import observability as obs
from tests.core.test_genos_llm_raw_log import record, read


def failed():
    return {'status': 422, 'body': {'request_id': 'req-final', 'answer_status': 'failed',
        'message': '현재 충분한 법률 검토를 하지 못했습니다.',
        'failure_reason': 'review_incomplete', 'error_code': 'MODEL_OUTPUT_INVALID'}}


@pytest.mark.parametrize('late_open', [False, True])
def test_failure_message_reaches_log_report_and_text_even_when_live_open_is_late(tmp_path, monkeypatch, late_open):
    ready = threading.Event()
    original = rr.safe_live_log
    @contextmanager
    def delayed(*args, **kwargs):
        if late_open: assert ready.wait(5)
        with original(*args, **kwargs) as result: yield result
    monkeypatch.setattr(rr, 'safe_live_log', delayed)
    try:
        with rr.DeferredReport(tmp_path/'shared', tmp_path/'runtime', request_id='req-final',
                api_type='LEGAL_AGENT', request={'question': '모의 질문'}, events=[]) as report:
            if not late_open: assert report._live_ready.wait(2)
            report.detach()  # Actual service detaches before complete().
            report.complete(failed())
    finally:
        ready.set()
        rr._FINALIZER_QUEUE.join()
    logs = list((tmp_path/'shared').rglob('*.log'))
    assert len(logs) == 1
    text = logs[0].read_text()
    assert 'FINAL RESPONSE / ANSWER' in text and 'review_incomplete' in text
    assert failed()['body']['message'] in text and '"answer_present": false' in text
    assert '"final_text_kind": "failure_guidance"' in text
    report = json.loads(logs[0].with_suffix('.json').read_text())
    assert report['result'] == failed()
    assert failed()['body']['message'] in logs[0].with_suffix('.txt').read_text()


def test_outcome_queued_before_slow_summary_and_not_mistaken_for_answer(tmp_path, monkeypatch):
    with rr.DeferredReport(tmp_path/'shared', tmp_path/'runtime', request_id='req-final',
            api_type='LEGAL_AGENT', request={}, events=[]) as report:
        assert report._live_ready.wait(2)
        report.detach()
        report.complete(failed())
        assert report.handler.writer.drain(2)
        assert 'SERVICE OUTCOME' in report.log_path.read_text()
        assert 'failure_guidance' in report.log_path.read_text()
    rr._FINALIZER_QUEUE.join()


def test_failure_projection_recovers_only_same_request_journal(tmp_path):
    run, journal = record(tmp_path/'runtime', [{'status_code': 200, 'body_json': {
        'choices': [{'finish_reason': 'length', 'message': {'content': 'incomplete'}}]}}])
    event = {'event': 'ask.failed', 'request_id': 'req-final', 'run_id': run}
    path = rr.write_report(tmp_path/'shared', tmp_path/'runtime', request_id='req-final',
        api_type='LEGAL_AGENT', request={}, result=failed(), events=[event,
            {'event': 'ask.failed', 'request_id': 'foreign', 'run_id': 'a'*32}])
    report = json.loads(path.read_text())
    assert report['run_id'] == run and report['run_id_basis'] == 'captured_event'
    assert report['journal']['status'] == 'FOUND'
    path = rr.write_report(tmp_path/'shared', tmp_path/'runtime', request_id='req-other',
        api_type='LEGAL_AGENT', request={}, result=failed(), events=[event])
    assert json.loads(path.read_text())['journal']['status'] == 'NO_RUN_ID'


def test_raw_sidecar_binds_actual_input_and_provider_usage(tmp_path):
    request = {'messages': [{'role': 'system', 'content': 'PRIVATE SYSTEM'},
        {'role': 'user', 'content': '질문'}], 'max_tokens': 6400}
    reply = {'status_code': 200, 'body_json': {'model': 'fixture', 'choices': [
        {'finish_reason': 'length', 'message': {'content': '미완성'}}],
        'usage': {'prompt_tokens': 15186, 'completion_tokens': 6400}}}
    run, _ = record(tmp_path/'runtime', [reply], [request])
    output, rows, _ = read(tmp_path/'runtime', tmp_path/'shared', run)
    metrics = rows[0]['input_metrics']
    assert metrics['prompt_plus_max_tokens'] == 21586
    assert metrics['length_diagnosis'] == 'output_cap_reached'
    assert not metrics['context_limit_known'] and metrics['input_content_chars'] == 16
    assert 'PRIVATE SYSTEM' not in output


def test_new_numeric_token_field_cannot_bypass_redaction():
    for value in ('PRIVATE TOKEN', {'api_key': 'PRIVATE KEY'}, True, -1):
        assert obs._safe_fields({'prompt_plus_max_tokens': value}) == {}


def test_failed_partial_answer_is_never_labeled_completed_answer():
    result = rr.final_response_summary({'status': 500, 'body': {
        'answer_status': 'failed', 'answer': {'text': 'partially transmitted'}}})
    assert result['answer_present'] and result['final_text_kind'] == 'incomplete_answer'
    assert result['delivery_confirmed'] is False
