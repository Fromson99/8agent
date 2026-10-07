"""Return a completed answer even while NFS completion I/O is blocked."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import threading

import pytest

from semantic_runtime import request_report as reports
from semantic_runtime import request_summary as summaries


@pytest.fixture
def svc(monkeypatch, tmp_path):
    import service
    reports._FINALIZER_QUEUE.join()
    monkeypatch.setenv('GENOS_SHARED_LOG_DIR', str(tmp_path / 'nfs'))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))

    async def answer(*args):
        return {'status': 200, 'body': {'answer': {'text': 'completed answer'}}}

    monkeypatch.setattr(service, '_dispatch', answer)
    yield service
    reports._FINALIZER_QUEUE.join()


@pytest.mark.parametrize('blocked_step', ['report_directory', 'write_report', 'write_readable_report', 'stop', 'refresh'])
def test_gateway_loop_can_close_before_report_and_live_cleanup(svc, monkeypatch, tmp_path, blocked_step):
    entered, release = threading.Event(), threading.Event()
    owner = summaries if blocked_step == 'refresh' else reports._LiveLog if blocked_step == 'stop' else reports
    original = getattr(owner, blocked_step)

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5), 'test did not release finalizer'
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, blocked_step, blocked)
    with ThreadPoolExecutor(max_workers=1) as callers:
        future = callers.submit(asyncio.run, svc.service({}, {
            'API_TYPE': 'LEGAL_AGENT', 'request_id': 'blocked-' + blocked_step,
            'question': 'synthetic question',
        }))
        try:
            assert entered.wait(3)
            # Includes asyncio.run executor shutdown, not just coroutine completion.
            result = future.result(timeout=1)
            assert result['body']['answer']['text'] == 'completed answer'
        finally:
            release.set()
    reports._FINALIZER_QUEUE.join()
    report = json.loads(next((tmp_path / 'nfs').rglob('*.json')).read_text())
    assert report['result'] == result
    assert any(row['event'] == 'request.returning' for row in report['service_events'])
    assert list((tmp_path / 'nfs').rglob('*.txt'))


def test_completed_result_logging_does_not_write_nfs_on_gateway_thread(svc, monkeypatch):
    original = reports._LiveLog.emit

    def check(handler, record):
        assert record.getMessage() not in {'request.finished', 'request.returning'}
        return original(handler, record)

    monkeypatch.setattr(reports._LiveLog, 'emit', check)
    result = asyncio.run(svc.service({}, {'API_TYPE': 'LEGAL_AGENT'}))
    assert result['status'] == 200


def test_failed_report_preserves_response_and_releases_capacity(svc, monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise OSError('synthetic NFS error')

    monkeypatch.setattr(reports, 'write_report', fail)
    assert asyncio.run(svc.service({}, {'API_TYPE': 'LEGAL_AGENT'}))['status'] == 200
    reports._FINALIZER_QUEUE.join()
    assert 'shared_report.failed' in caplog.text


def test_saturated_reporting_does_not_block_or_create_more_workers(svc, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(reports, '_FINALIZER_SLOTS', threading.BoundedSemaphore(0))
    assert asyncio.run(svc.service({}, {'API_TYPE': 'LEGAL_AGENT'}))['status'] == 200
    assert not (tmp_path / 'nfs').exists()
    assert 'shared_report.skipped' in caplog.text


def test_cancellation_detaches_live_log_and_stops_heartbeat(svc, monkeypatch):
    handlers = []
    original = reports._LiveLog.start

    def record(handler):
        handlers.append(handler)
        original(handler)

    async def cancel(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(reports._LiveLog, 'start', record)
    monkeypatch.setattr(svc, '_dispatch', cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(svc.service({}, {'API_TYPE': 'LEGAL_AGENT'}))
    reports._FINALIZER_QUEUE.join()
    assert handlers and all(h.stop_event.is_set() and h.stream.closed for h in handlers)


def test_unrelated_request_never_acquires_another_live_logs_io_lock(monkeypatch):
    import io
    handler = reports._LiveLog('request-a', io.StringIO())
    record = logging.LogRecord('genos.test', logging.INFO, '', 1, 'request.returning', (), None)
    record.fields = {'request_id': 'request-b'}
    with monkeypatch.context() as patch:
        patch.setattr(handler, 'acquire', lambda: pytest.fail('unrelated NFS I/O lock acquired'))
        handler.handle(record)
