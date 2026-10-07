import json
import logging

from semantic_runtime import observability as obs


def test_genos_json_log_drops_content_and_credentials(monkeypatch):
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "secret-token-value")
    record = logging.LogRecord("genos.test", logging.INFO, __file__, 1, "request.finished", (), None)
    record.fields = {
        "request_id": "request-1",
        "question": "로그에 남으면 안 되는 질문",
        "authorization": "Bearer secret-token-value",
        "detail": "upstream failed with secret-token-value",
    }
    payload = json.loads(obs.JsonFormatter().format(record))
    assert payload["request_id"] == "request-1"
    assert payload["detail"] == "upstream failed with [REDACTED]"
    assert "question" not in payload
    assert "authorization" not in payload
    assert "secret-token-value" not in json.dumps(payload)


def test_context_adds_the_same_request_id_to_events(caplog):
    logger = obs.get_logger("correlation-test")
    with obs.context(request_id="request-2"):
        obs.event(logger, "step.finished", step="retrieve")
    record = next(record for record in caplog.records if record.getMessage() == "step.finished")
    assert record.fields["request_id"] == "request-2"
    assert record.fields["step"] == "retrieve"


def test_step_separates_log_write_time_from_work_and_cpu(monkeypatch):
    from types import SimpleNamespace
    clock = SimpleNamespace(wall=0.0, cpu=0.0)
    monkeypatch.setattr(obs, 'time', SimpleNamespace(
        perf_counter=lambda: clock.wall, thread_time=lambda: clock.cpu))
    records = []
    class SlowHandler(logging.Handler):
        def emit(self, record):
            records.append(record)
            clock.wall += 2.0  # deterministic simulated handler wait; no sleep
    logger = logging.Logger('timing-fixture')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(SlowHandler())
    with obs.context(request_id='timing-fixture', run_id='run-a'):
        with obs.step(logger, 'fixture.work'):
            clock.wall += 3.0
            clock.cpu += 0.4
        obs.event(logger, 'fixture.next')
    fields = records[1].fields
    assert fields['duration_ms'] == 5000
    assert fields['work_ms'] == 3000
    assert fields['thread_cpu_ms'] == 400
    assert fields['start_log_ms'] == 2000
    assert fields['previous_log_ms'] == 2000
    assert records[2].fields['previous_event'] == 'step.finished'
    assert records[2].fields['previous_step'] == 'fixture.work'
    with obs.context(request_id='other-request'):
        obs.event(logger, 'other.event')
    assert 'previous_log_ms' not in records[-1].fields


def test_failed_step_keeps_exception_and_timing(caplog):
    import pytest
    with pytest.raises(ValueError, match='fixture failure'):
        with obs.step(obs.get_logger('failure-timing'), 'fixture.fail'):
            raise ValueError('fixture failure')
    failed = next(r for r in caplog.records if r.getMessage() == 'step.failed')
    assert failed.exc_info[0] is ValueError
    assert all(failed.fields[k] >= 0 for k in ('work_ms', 'thread_cpu_ms', 'start_log_ms'))
