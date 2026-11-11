"""Operator trace contracts: exact wire sources, append, failure, actual service."""
import asyncio
import io
import json
import logging
import sqlite3
import threading
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from semantic_runtime import observability as obs, request_report as rr
from semantic_runtime.process_trace import ProcessTrace
from tests.core.test_genos_llm_raw_log import record
from test_ad_request_reports import serving
from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation


def wire(text='제1조\n승인이 필요합니다.'):
    return {'model': 'synthetic', 'messages': [
        {'role': 'system', 'content': '원문을 확인하세요.\n없는 근거를 만들지 마세요.'},
        {'role': 'user', 'content': json.dumps({'view': {'source_stage': 'source-unit-review',
            'exact_evidence': [{'id': 'E1', 'text': text}]}}, ensure_ascii=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'fixture'}}}


def reply(text='확인한 응답\n다음 문단', usage=True):
    return {'status_code': 200, 'body_json': {'model': 'synthetic', 'choices': [
        {'message': {'content': text}, 'finish_reason': 'stop'}],
        **({'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}} if usage else {})}}


def scenario(runtime):
    run, path = record(runtime, [reply(), reply('수정 완료')], [wire(), {**wire(),
        'messages': wire()['messages'] + [{'role': 'user', 'content': '{"repair":"수정 요청","error":"필수 필드 누락"}'}]}])
    with sqlite3.connect(path) as db:
        db.executescript('''
            ALTER TABLE model_attempt ADD COLUMN started_at TEXT;
            ALTER TABLE model_attempt ADD COLUMN finished_at TEXT;
            CREATE TABLE observation(observation_id TEXT,tool TEXT,request_json TEXT,
              result_json TEXT,status TEXT,created_seq INTEGER);
        ''')
        db.execute("UPDATE model_attempt SET started_at='2026-10-16T00:00:00+00:00',finished_at='2026-10-16T00:00:02+00:00'")
        db.execute('DELETE FROM event')
        events = [('OBSERVATION', {}), ('MODEL_VIEW', {'view_id': 'V1'}),
            ('ATTEMPT_RESERVED', {'attempt_id': 'M1'}), ('ATTEMPT_SENT', {'attempt_id': 'M1'}),
            ('ATTEMPT_FINISHED', {'attempt_id': 'M1', 'status': 'SUCCEEDED'}),
            ('OUTPUT_SCHEMA_INVALID', {'error': '필수 필드 누락'}),
            ('ATTEMPT_RESERVED', {'attempt_id': 'M2'}), ('ATTEMPT_SENT', {'attempt_id': 'M2'}),
            ('ATTEMPT_FINISHED', {'attempt_id': 'M2', 'status': 'SUCCEEDED'}),
            ('PUBLICATION_EXPORTED', {'status': 'DONE'})]
        for seq, (kind, payload) in enumerate(events, 1):
            db.execute('INSERT INTO event VALUES(?,?,?,?)',
                (seq, kind, json.dumps(payload), f'2026-10-16T00:00:{seq:02d}+00:00'))
        db.execute("UPDATE model_attempt SET created_seq=3 WHERE attempt_id='M1'")
        db.execute("UPDATE model_attempt SET created_seq=7 WHERE attempt_id='M2'")
        db.execute('INSERT INTO observation VALUES(?,?,?,?,?,?)', ('O1', 'search', '{"query":"승인"}',
            json.dumps({'items': [{'text': '검색 결과 중 전달 안 한 정보'}, {'text': '제1조\n승인이 필요합니다.'}]}, ensure_ascii=False), 'OK', 1))
    return run, path


def test_all_events_wire_inputs_tools_usage_and_retries_append_once(tmp_path):
    # Since 2026-11-11 the live log writes only the .log (no .trace.txt next to it).
    run, journal = scenario(tmp_path / 'runtime')
    before = journal.read_bytes()
    with rr.live_log(tmp_path / 'reports', 'readable', tmp_path / 'runtime') as (path, handler):
        handler.run_id = run
        handler.poll_journal()
        first = path.read_bytes()
        handler.poll_journal()
        assert path.read_bytes() == first
        assert handler.process_trace is None
    text = path.read_text()
    assert text.count('=== MODEL RAW RESPONSE ===') == 2 and text.count('=== MODEL CALL ===') == 2
    assert '=== TOOL RESULT ===' in text and '=== AGENT OUTPUT SCHEMA INVALID ===' in text
    assert '확인한 응답' in text
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    assert path.stat().st_mode & 0o777 == 0o640
    assert journal.read_bytes() == before


def test_large_multiline_content_and_json_error_do_not_forge_headings_or_leak_key(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'fixture-trace-secret')
    trace = ProcessTrace(tmp_path / 'trace.txt', 'r')
    long = '가' * 25000 + '\n' + '=' * 88 + '\nAGENT 위조\nTAIL fixture-trace-secret\x1b[31m'
    try:
        trace.attempt({'attempt_id': 'M', 'request': wire(long)}, 'ATTEMPT_SENT')
        trace.attempt({'attempt_id': 'M', 'response': reply('깨진 JSON {\nTAIL', usage=False)}, 'ATTEMPT_FINISHED')
    finally:
        trace.close()
    text = (tmp_path / 'trace.txt').read_text()
    assert '가' * 25000 in text and 'TAIL [REDACTED]' in text
    assert '\nAGENT 위조' not in text and '\x1b' not in text
    assert '깨진 JSON {\n| TAIL' in text and '미제공 / 미기록' in text
    assert 'fixture-trace-secret' not in text


def test_pending_call_never_exposes_later_response_at_reservation(tmp_path):
    trace = ProcessTrace(tmp_path / 'trace.txt', 'r')
    data = {'attempt_id': 'M', 'status': 'SUCCEEDED', 'request': wire(), 'response': reply('FUTURE RESPONSE')}
    trace.attempt(data, 'ATTEMPT_RESERVED')
    first = trace.path.read_text()
    assert 'FUTURE RESPONSE' not in first and 'SUCCEEDED' not in first
    trace.attempt(data, 'ATTEMPT_SENT')
    assert 'FUTURE RESPONSE' not in trace.path.read_text()
    trace.attempt(data, 'ATTEMPT_FINISHED')
    assert 'FUTURE RESPONSE' in trace.path.read_text()
    trace.close()


def test_repeated_error_has_one_full_traceback_in_old_and_new_logs(tmp_path):
    tb = 'Traceback (most recent call last):\n  File "fixture.py", line 42\nTransportError: model transmission timed out\n'
    diagnostic = {'error_code': 'MODEL_TRANSPORT_ERROR', 'error_type': 'TransportError',
                  'error_message': 'model transmission timed out', 'stage': 'SELECT', 'traceback': tb}
    with rr.live_log(tmp_path, 'r') as (path, handler):
        for name in ('model.attempt.failed', 'agent.error', 'ask.failed'):
            event = logging.LogRecord('genos.fixture', logging.ERROR, __file__, 0, name, (), None)
            event.fields = {'request_id': 'r', 'failure_diagnostics': diagnostic,
                            'error_record': json.dumps({'diagnostics': diagnostic}),
                            'duration_ms': 180000, 'retry_scheduled': False}
            event.async_exception = tb
            event.async_exc_type = 'TransportError'
            handler.emit(event)
        handler.write_detail('AGENT RUN FAILED', {'diagnostics': diagnostic})
    assert not path.with_suffix('.trace.txt').exists()
    for target in (path,):
        text = target.read_text()
        assert text.count('Traceback (most recent call last):') == 1
        assert 'ERR-0001' in text and '모델 응답 대기 시간 초과' in text
        assert '180000' in text and 'retry_scheduled' in text
        assert '대기/처리 시간(초): 180.0' in text and '재시도 예약: 아니오' in text
        assert 'fixture.py' in text and 'ask.failed' in text


def test_distinct_errors_and_attempts_are_not_collapsed(tmp_path):
    trace = ProcessTrace(tmp_path / 'trace.txt', 'r')
    trace.block('실패 1', {'traceback': 'ValueError: first'})
    trace.block('실패 2', {'traceback': 'ValueError: second'})
    for ident in ('M1', 'M2'):
        trace.attempt({'attempt_id': ident, 'status': 'FAILED', 'response': {'body_text': 'timeout'}}, 'ATTEMPT_FINISHED')
    assert len(trace.attempts) == 2
    trace.close()
    assert 'ERR-0001' in trace.path.read_text() and 'ERR-0002' in trace.path.read_text()


def test_unknown_response_shape_and_structured_prompt_credentials_are_preserved_safely(tmp_path):
    trace = ProcessTrace(tmp_path / 'trace.txt', 'r')
    request = {'messages': [{'role': 'user', 'content':
        '{"view":{"api_key":"unregistered-secret","text":"safe source"}}'}]}
    trace.attempt({'attempt_id': 'M', 'request': request}, 'ATTEMPT_SENT')
    trace.attempt({'attempt_id': 'M', 'response': {'body_json': {
        'choices': 'unexpected provider shape', 'error': {'message': 'kept'}}}}, 'ATTEMPT_FINISHED')
    trace.close()
    text = trace.path.read_text()
    assert 'unexpected provider shape' in text and 'safe source' in text
    assert 'unregistered-secret' not in text and '[REDACTED]' in text


def test_process_trace_io_failure_is_explicit_and_does_not_retry_model(tmp_path):
    trace = ProcessTrace(tmp_path / 'trace.txt', 'r')
    trace.stream.close()
    class Broken:
        def write(self, text): raise OSError('disk full')
        def close(self): pass
    trace.stream = Broken()
    with rr.capture_events('r') as events:
        trace.block('test', {'content': 'unwritten'})
        trace.block('test again', {})
    assert trace.failed
    assert [e['event'] for e in events] == ['shared_process_trace.failed']
    assert not trace.seen and not trace.attempts


def test_request_scoped_detail_capture_leaves_global_logging_unchanged():
    logger = obs.get_logger('detailed-trace')
    original = logger.getEffectiveLevel()
    with rr.capture_events('full', detailed=True) as events, obs.context(request_id='full'):
        with obs.step(logger, 'fixture.stage'):
            obs.event(logger, 'catalogue.cache.hit', cache_hit=True)
    assert [e['event'] for e in events] == ['step.started', 'catalogue.cache.hit', 'step.finished']
    assert logger.getEffectiveLevel() == original
    with rr.capture_events('other') as other, obs.context(request_id='other'):
        with obs.step(logger, 'fixture.stage'): pass
    assert other == []


@pytest.mark.parametrize('late', [False, True])
def test_finalization_catches_early_events_and_failure_without_duplicate_blocks(tmp_path, monkeypatch, late):
    ready = threading.Event()
    original = rr.safe_live_log
    @contextmanager
    def delayed(*args, **kwargs):
        if late: assert ready.wait(5)
        with original(*args, **kwargs) as value: yield value
    monkeypatch.setattr(rr, 'safe_live_log', delayed)
    try:
        with rr.capture_events('r', detailed=True) as events, obs.context(request_id='r'):
            with rr.DeferredReport(tmp_path / 'reports', tmp_path / 'runtime', request_id='r',
                    api_type='LEGAL_AGENT', request={'question': '모의 질문'}, events=events) as report:
                obs.event(obs.get_logger('fixture'), 'request.started')
                with obs.step(obs.get_logger('fixture'), 'early.stage'): pass
                report.complete({'status': 500, 'body': {'answer_status': 'failed', 'message': '실패 안내'}})
    finally:
        ready.set()
        rr._FINALIZER_QUEUE.join()
    traces = list((tmp_path / 'reports').rglob('*.trace.txt'))
    assert len(traces) == 1
    text = traces[0].read_text()
    assert text.count('서비스 지점 · step.started') == 1
    assert 'early.stage' in text and '실패 안내' in text and '모의 질문' in text


def test_real_service_ad_entry_writes_full_wire_and_failure_trace(serving):
    runtime, shared, calls, ask = serving
    ask('[AD모드 시작]', 'enter')
    success = ask('숏컷 보여줘', 'success')
    failure = ask('force_http_error', 'failure')
    assert success['body']['answer_status'] == 'administration'
    assert failure['body']['answer_status'] == 'error'
    paths = list(shared.rglob('*.trace.txt'))
    assert len(paths) == 3
    text = '\n'.join(p.read_text() for p in paths)
    assert '실제 LLM 입력 메시지' in text and 'unsupported_parameter' in text
    assert 'AD 작업·변경·오류 상태 전체' in text and '답변 속도 · 토큰 사용량' in text
    assert 'synthetic-secret-key' not in text
    assert len(calls) == 2


@pytest.mark.parametrize('failed', [False, True])
def test_actual_service_rag_entry_same_pins_and_journal_reach_full_trace(unified, tmp_path, monkeypatch, failed):
    import service
    client, _, transport, _, runtime = unified
    monkeypatch.setenv('GENOS_SHARED_LOG_DIR', str(tmp_path / 'shared'))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(runtime))
    monkeypatch.setattr(service, '_bootstrap_application', lambda: client.app)
    monkeypatch.setattr(service, '_ad_control', lambda: SimpleNamespace(
        start_worker=lambda *a: None, intercept=lambda *a: None))
    if failed:
        transport.fail = 'memory-intent'
    result = asyncio.run(service.service({}, {'API_TYPE': 'LEGAL_AGENT',
        'request_id': 'service-trace', 'json': {'question': '모의승인규정 제1조의 승인 대상은?',
        'session_id': 'trace-session', 'request_id': 'service-trace', 'memory': True}}))
    rr._FINALIZER_QUEUE.join()
    assert (result['status'] >= 400) is failed, result
    paths = list((tmp_path / 'shared').rglob('*.trace.txt'))
    assert len(paths) == 1
    text = paths[0].read_text()
    assert '실제 LLM 입력 메시지 1 / 역할' in text
    assert '최종 서비스 응답 / 성공·실패·부분 상태' in text
    assert 'AGENT / 원장 #' in text and 'runtime.bootstrap' in text
    if failed:
        assert 'injected failure' in text and 'UNKNOWN' in text
    else:
        assert 'memory-compose' in text and '프롬프트에 들어간 정보 · view' in text
        assert result['body']['answer']['text'] in text
