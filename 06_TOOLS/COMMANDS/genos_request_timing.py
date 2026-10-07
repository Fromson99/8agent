"""Summarize one GENOS request-report JSON without exporting request content.

Run inside GENOS against the JSON written by GENOS_SHARED_LOG_DIR. An optional
workflow JSONL export adds the workflow -> code-serving -> screen boundary.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys


def _seconds(value):
    try:
        return f"{float(value):.3f}s"
    except (TypeError, ValueError):
        return "unknown"


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _elapsed(start, end):
    a, b = _timestamp(start), _timestamp(end)
    return max(0.0, (b - a).total_seconds()) if a and b else None


def _workflow_events(path: Path | None, request_id: str):
    if path is None:
        return []
    found = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # Container logs can include non-JSON lines.
            if isinstance(row, dict) and row.get("request_id") == request_id:
                found.append(row)
    return found


def summarize(report: dict, workflow_events: list[dict] | None = None) -> str:
    if report.get("schema_version") != "genos-request-report-v1":
        raise ValueError("expected genos-request-report-v1 JSON")
    service = [e for e in report.get("service_events", []) if isinstance(e, dict)]
    workflow = workflow_events or []
    journal = report.get("journal") or {}
    timeline = journal.get("timeline") or []
    result = report.get("result") or {}
    body = result.get("body") or {}
    answer = body.get("answer") or {}
    state = journal.get("state") or {}
    run = next(iter(state.get("run") or []), {})
    first = next((e for e in service if e.get("event") == "request.started"), {})
    ready = next((e for e in reversed(service) if e.get("event") == "request.finished"), {})
    returning = next((e for e in reversed(service) if e.get("event") == "request.returning"), {})
    last = returning or ready
    wall_ms = last.get("duration_ms")
    if not isinstance(wall_ms, (int, float)):
        wall = _elapsed(first.get("ts"), last.get("ts"))
    else:
        wall = wall_ms / 1000
    lines = [
        "GENOS 요청 시간 진단 (내용 비포함)",
        "=" * 36,
        f"request_id: {report.get('request_id') or 'unknown'}",
        f"run_id: {report.get('run_id') or 'unknown'}",
        f"code_serving_http: {result.get('status', 'unknown')}",
        f"code_serving_wall: {_seconds(wall)}",
        f"timing_boundary: {last.get('event', 'unknown')} (not gateway delivery confirmation)",
        f"journal: {journal.get('status', 'unknown')}",
        f"run_status: {run.get('status', 'unknown')}",
        f"gate: {run.get('gate', 'unknown')}",
        f"answer_chars: {len(str(answer.get('text') or ''))}",
        "",
        "단계별 시간 (중첩 구간은 합계에 다시 더하지 않음)",
    ]
    if not returning:
        lines.append('주의: 이전 request.finished는 보고서 저장 전 내부 결과 준비 시점. 실제 반환 시간은 미확인.')
    steps = []
    for e in service:
        event = e.get("event")
        duration = e.get("duration_ms")
        if not isinstance(duration, (int, float)):
            continue
        if event in ("step.finished", "step.failed"):
            steps.append((str(e.get("step") or "unknown"), duration / 1000, event))
    for name, seconds, status in sorted(steps, key=lambda row: row[1], reverse=True):
        lines.append(f"- {name}: {_seconds(seconds)} ({status})")
    if not steps:
        lines.append("- 단계 시간 이벤트 없음")

    attempts = []
    for e in service:
        if e.get("event") not in ("model.attempt.received", "model.attempt.failed"):
            continue
        duration = e.get("duration_ms")
        if not isinstance(duration, (int, float)):
            continue
        attempts.append((str(e.get("phase") or "unknown"), duration / 1000,
                         str(e.get("event")), str(e.get("attempt_id") or "unknown"),
                         e.get("http_status")))
    lines.extend(["", "모델 호출 시간"])
    if attempts:
        totals = defaultdict(float)
        counts = Counter()
        for phase, seconds, event, _, _ in attempts:
            totals[phase] += seconds
            counts[phase] += 1
        for phase in sorted(totals, key=totals.get, reverse=True):
            lines.append(f"- {phase}: {counts[phase]}회, 합계 {_seconds(totals[phase])}")
        lines.append("가장 긴 호출:")
        for phase, seconds, event, attempt_id, http in sorted(attempts, key=lambda row: row[1], reverse=True)[:10]:
            lines.append(f"- {phase} {attempt_id}: {_seconds(seconds)}, {event}, HTTP {http or 'unknown'}")
    else:
        # A journal can exist even when application event capture was disabled.
        records = [c.get("record") or {} for row in timeline for c in row.get("created_records") or []
                   if c.get("table") == "model_attempt"]
        for record in records:
            seconds = _elapsed(record.get("started_at"), record.get("finished_at"))
            lines.append(f"- {record.get('attempt_id', 'unknown')}: {_seconds(seconds)}, {record.get('status', 'unknown')} (journal clock)")
        if not records:
            lines.append("- 모델 호출 기록 없음")

    failures = Counter(e.get("event") for e in service if e.get("event") in
                       ("model.attempt.failed", "model_http.failed", "shared_report.failed", "runtime.request.failed"))
    repairs = Counter((row.get("event") or {}).get("kind") for row in timeline
                      if (row.get("event") or {}).get("kind") in ("SEMANTIC_REPAIR", "WORKFLOW_REPAIR"))
    lines.extend(["", "오류·재시도 신호"])
    lines.extend(f"- {key}: {count}회" for key, count in sorted((failures + repairs).items()))
    if not failures and not repairs:
        lines.append("- 기록된 오류·수정 재시도 없음")

    lines.extend(["", "워크플로우 → 화면 전달"])
    if workflow:
        started = next((e for e in workflow if e.get("event") == "code_serving.request.started"), {})
        timeout = started.get("timeout_seconds")
        if isinstance(timeout, (int, float)):
            lines.append(f"- code_serving_timeout: {_seconds(timeout)}")
            if wall is not None and wall > timeout:
                lines.append("- 주의: 코드서빙 처리 시간이 워크플로우 대기 상한보다 길었음")
        for e in workflow:
            if e.get("event") in ("code_serving.response.received", "workflow.request.finished",
                                  "code_serving.request.failed", "workflow.request.crashed"):
                lines.append(f"- {e.get('event')}: status={e.get('http_status', e.get('answer_status', 'unknown'))}, "
                             f"duration={_seconds(e.get('duration_ms') / 1000 if isinstance(e.get('duration_ms'), (int, float)) else e.get('tm_total'))}")
    else:
        lines.append("- 워크플로우 로그 미제공: 화면 전달 여부는 이 JSON만으로 확인 불가")
    lines.extend(["", "판정 범위: 시간·상태만 추출. 질문, 원문, 프롬프트, 답변, 키는 출력하지 않음."])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="GENOS_SHARED_LOG_DIR의 요청별 JSON")
    parser.add_argument("--workflow-log", type=Path, help="같은 request_id를 포함하는 워크플로우 JSONL (선택)")
    parser.add_argument("--output", required=True, type=Path, help="새 TXT 파일 경로")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    content = summarize(report, _workflow_events(args.workflow_log, str(report.get("request_id") or "")))
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(content)
    print(args.output)


if __name__ == "__main__":
    sys.exit(main())
