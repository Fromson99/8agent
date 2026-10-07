"""Timing export uses only metadata from a content-bearing GENOS report."""
import importlib.util
from pathlib import Path


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
