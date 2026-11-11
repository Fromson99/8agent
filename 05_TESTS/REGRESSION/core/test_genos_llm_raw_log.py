"""Returned LLM output is literal and request-local; no model/network calls.

Since 2026-11-11 (LOG=on writes only the .log) the received output lives in the
.log block itself; there is no .llm_raw.jsonl sidecar.
"""
import hashlib
import json
import sqlite3

import pytest

from semantic_runtime.request_report import live_log
from tests.core.test_genos_agent_plain_log import recorded_attempts


def record(runtime, replies, requests=None):
    run_id = 'f' * 32
    journal = recorded_attempts(runtime, run_id,
        [('investigate', {'original_question': 'PRIVATE INPUT'}, {}, False)] * len(replies))
    with sqlite3.connect(journal) as db:
        db.execute('ALTER TABLE model_attempt ADD COLUMN logical_call_id TEXT')
        for i, response in enumerate(replies, 1):
            request = (requests or [{}] * len(replies))[i - 1]
            db.execute('UPDATE model_attempt SET response_json=?, request_json=?, logical_call_id=? WHERE attempt_id=?',
                (json.dumps(response, ensure_ascii=False), json.dumps(request, ensure_ascii=False), 'Lsame', f'M{i}'))
    return run_id, journal


def read(runtime, shared, run_id):
    with live_log(shared, 'req-raw', runtime) as (path, handler):
        handler.run_id = run_id
        handler.poll_journal()
        first = path.read_bytes()
        handler.poll_journal()
        assert path.read_bytes() == first
    raw_path = path.with_suffix('.llm_raw.jsonl')
    assert not raw_path.exists()
    output = first.decode('utf-8')
    return output, raw_headers(output), raw_path


def raw_headers(output):
    """The JSON header of each MODEL RAW RESPONSE block (everything but the literal content)."""
    decoder, rows, marker = json.JSONDecoder(), [], '=== MODEL RAW RESPONSE ===\n'
    start = output.find(marker)
    while start >= 0:
        row, _ = decoder.raw_decode(output, start + len(marker))
        rows.append(row)
        start = output.find(marker, start + 1)
    return rows


def test_original_json_whitespace_long_content_and_call_lineage(tmp_path):
    original = '{\n  "intent" : "DRAFT",\n\t"actions": [{"tool":"search"}],\n "reason":"' + '가' * 20000 + '"\n}\r\n'
    corrected = '{ "intent": "CONTINUE", "actions": [{"tool":"search"}] }'
    replies = [{'status_code': 200, 'body_json': {'model': 'fixture', 'choices': [{
        'index': 0, 'message': {'content': content}, 'finish_reason': 'stop'}]}} for content in (original, corrected)]
    run_id, journal = record(tmp_path / 'runtime', replies, [
        {'messages': [{'role': 'system', 'content': 'PRIVATE PROMPT'}]},
        {'messages': [{}, {}, {'content': json.dumps({'repair': 'correct the same object',
            'error': 'use CONTINUE for actions'})}]}])
    before = journal.read_bytes()
    output, rows, raw_path = read(tmp_path / 'runtime', tmp_path / 'shared', run_id)
    assert original in output and corrected in output
    assert hashlib.sha256(original.encode()).hexdigest() in output
    assert [row['attempt_id'] for row in rows] == ['M1', 'M2']
    assert [row['logical_call_id'] for row in rows] == ['Lsame', 'Lsame']
    assert [row['schema_repair'] for row in rows] == [False, True]
    assert rows[1]['validation_error'] == 'use CONTINUE for actions'
    assert not any(row['redaction_applied'] for row in rows)
    assert 'PRIVATE PROMPT' not in output and 'PRIVATE INPUT' not in output
    assert journal.read_bytes() == before


@pytest.mark.parametrize('reply', [
    {'status_code': 200, 'body_json': {'model': 'fixture', 'choices': [{'message': {
        'content': '', 'refusal': '정책상 답변을 제공할 수 없습니다.\n상세 사유'},
        'finish_reason': 'content_filter'}], 'guardrail_result': {'blocked': True},
        'unknown_guard_field': {'policy': 'fixture-policy'}}},
    {'status_code': 403, 'body_json': None, 'body_text': '<html>가드레일 차단\n원래 오류 응답</html>'},
    {'status_code': 200, 'body_json': {'choices': [{'message': {'content': None, 'tool_calls': [
        {'function': {'name': 'first', 'arguments': '{ "intent": "DRAFT" }'}},
        {'function': {'name': 'second', 'arguments': 'not json\nraw argument'}}]}, 'finish_reason': 'tool_calls'}]}},
    {'status_code': 200, 'body_json': {'choices': [{'message': {
        'content': 'unusual provider reply', 'tool_calls': 17}, 'finish_reason': 'stop'}]}},
])
def test_filter_refusal_non_json_and_all_tool_arguments_are_preserved(tmp_path, reply):
    run_id, _ = record(tmp_path / 'runtime', [reply])
    output, rows, _ = read(tmp_path / 'runtime', tmp_path / 'shared', run_id)
    assert len(rows) == 1 and rows[0]['http_status'] == reply['status_code']
    if reply.get('body_text'):
        assert reply['body_text'] in output
    elif reply['body_json'].get('guardrail_result'):
        assert 'content_filter' in output and 'message.refusal' in output
        assert '정책상 답변을 제공할 수 없습니다.\n상세 사유' in output
        assert rows[0]['guardrail_result'] == {'blocked': True}
    elif isinstance(reply['body_json']['choices'][0]['message']['tool_calls'], list):
        assert 'not json\nraw argument' in output and '{ "intent": "DRAFT" }' in output
    else:
        assert 'unusual provider reply' in output


def test_credentials_are_masked_and_redaction_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'fixture-raw-secret')
    content = '원래 답변 fixture-raw-secret\n나머지 원문은 유지'
    response = {'status_code': 200, 'body_json': {'api_key': 'fixture-raw-secret',
        'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]}}
    run_id, _ = record(tmp_path / 'runtime', [response])
    output, rows, _ = read(tmp_path / 'runtime', tmp_path / 'shared', run_id)
    assert 'fixture-raw-secret' not in output
    assert rows[0]['redaction_applied'] is True
    assert content.replace('fixture-raw-secret', '[REDACTED]') in output


def test_received_output_stays_in_the_log_without_a_sidecar(tmp_path):
    content = '수신 응답\n원문'
    run_id, _ = record(tmp_path / 'runtime', [
        {'body_json': {'choices': [{'message': {'content': content}}]}}])
    with live_log(tmp_path / 'shared', 'req-unavailable', tmp_path / 'runtime') as (path, handler):
        handler.run_id = run_id
        handler.poll_journal()
    output = path.read_text()
    assert content in output and 'raw_sidecar_status' not in output
    assert 'TRACE READER ERROR' not in output
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
