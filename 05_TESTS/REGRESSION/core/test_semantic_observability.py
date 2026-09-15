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
