"""Summarize one GENOS request-report JSON without exporting request content.

Run inside GENOS against the JSON written by GENOS_SHARED_LOG_DIR. An optional
workflow JSONL export adds the workflow -> code-serving -> screen boundary.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
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


def _object(value):
    return value if isinstance(value, dict) else {}


def _identifier(value):
    # Never stringify arbitrary journal objects or free-text error messages.
    return str(value) if isinstance(value, (str, int)) and re.fullmatch(
        r'[A-Za-z0-9_.:/-]{1,160}', str(value)) else 'unknown'


def _number(value):
    return value if type(value) in (int, float) else 'unknown'


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _column(row, key):
    value = row.get(key, row.get(key + '_json'))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return _object(value)


def _records(journal, table):
    for item in journal.get('timeline') or []:
        for created in _object(item).get('created_records') or []:
            if _object(created).get('table') == table:
                yield _object(created.get('record'))
    for record in _object(journal.get('state')).get(table) or []:
        yield _object(record)


def summarize_models(report: dict) -> str:
    """Read exact saved call payloads, but output only bounded diagnostic metadata."""
    if not isinstance(report, dict) or report.get('schema_version') != 'genos-request-report-v1':
        raise ValueError('요청별 .json 보고서를 지정하세요 (.llm_raw.jsonl 제외).')
    journal = _object(report.get('journal'))
    views = {v.get('view_id'): v for v in _records(journal, 'model_view')}
    service = [_object(e) for e in report.get('service_events') or []]
    attempts, seen = [], set()
    for record in _records(journal, 'model_attempt'):
        ident = record.get('attempt_id')
        if not isinstance(ident, str) or ident in seen:
            continue
        attempts.append(record)
        seen.add(ident)
    attempts.sort(key=lambda r: (str(r.get('started_at') or ''),
                                 r.get('created_seq') if type(r.get('created_seq')) is int else 0))
    lines = ['GENOS 모델 호출 요약 — 원문/질문/프롬프트/답변 미출력',
             'request_id: ' + _identifier(report.get('request_id')),
             'run_id: ' + _identifier(report.get('run_id')),
             'journal: ' + _identifier(journal.get('status')),
             f'모델 호출 기록: {len(attempts)}개', '']
    previous_success = None
    for index, record in enumerate(attempts, 1):
        request, response = _column(record, 'request'), _column(record, 'response')
        body = _object(response.get('body_json') or response.get('body'))
        events = [e for e in service if e.get('attempt_id') == record.get('attempt_id')]
        finished = next((e for e in reversed(events) if e.get('event') in
                         ('model.attempt.failed', 'model.attempt.received')), {})
        http_event = next((e for e in reversed(events) if e.get('event') in
                          ('model_http.failed', 'model.http.failed',
                           'model_http.finished', 'model.http.finished')), {})
        messages = request.get('messages')
        messages = messages if isinstance(messages, list) else []
        stage = None
        chars, non_text = Counter(), 0
        for message in messages:
            message = _object(message)
            text = message.get('content')
            role = message.get('role')
            role = role if role in ('system', 'user', 'assistant', 'tool') else 'other'
            if isinstance(text, str):
                chars[role] += len(text)
                if role == 'user':
                    try:
                        stage = _object(_object(json.loads(text)).get('view')).get('source_stage') or stage
                    except ValueError:
                        pass
            elif text is not None:
                non_text += 1
        view_record = views.get(record.get('view_id'), {})
        stage = stage or _column(view_record, 'body').get('source_stage') or view_record.get('phase')
        status = response.get('status_code', http_event.get('http_status', finished.get('http_status')))
        elapsed = (finished.get('duration_ms') / 1000 if type(finished.get('duration_ms')) in (int, float)
                   else _elapsed(record.get('started_at'), record.get('finished_at')))
        fmt = _object(request.get('response_format'))
        spec = _object(fmt.get('json_schema'))
        schema = spec.get('schema')
        schema_bytes = _json_bytes(schema) if schema is not None else None
        schema_sha = hashlib.sha256(schema_bytes).hexdigest() if schema_bytes is not None else None
        enums = empty_enums = 0
        stack = [schema]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if isinstance(item.get('enum'), list):
                    enums += len(item['enum'])
                    empty_enums += not item['enum']
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        usage = _object(body.get('usage'))
        prompt_tokens = usage.get('prompt_tokens', record.get('input_tokens'))
        request_size = len(_json_bytes(request)) if request else None
        model = request.get('model')
        lines += [f'#{index:02d} {_identifier(stage)} | HTTP {_number(status)} | '
                  f'{_identifier(record.get("status"))} | {_seconds(elapsed)}',
                  '  attempt_id=' + _identifier(record.get('attempt_id')) +
                  ' start=' + (str(_timestamp(record.get('started_at'))) if _timestamp(record.get('started_at')) else 'unknown'),
                  f'  model={_identifier(model)} max_tokens={_number(request.get("max_tokens"))} '
                  f'temperature={_number(request.get("temperature"))} '
                  f'stream={request.get("stream") if type(request.get("stream")) is bool else "unknown"} '
                  f'thinking={_object(request.get("chat_template_kwargs")).get("enable_thinking") if type(_object(request.get("chat_template_kwargs")).get("enable_thinking")) is bool else "unknown"}',
                  f'  input_chars={sum(chars.values()) if messages else "unknown"} '
                  f'(system={chars["system"]}, user={chars["user"]}, assistant={chars["assistant"]}, tool={chars["tool"]}, other={chars["other"]}) '
                  f'non_text_messages={non_text} request_json_bytes={_number(request_size)}',
                  f'  format={_identifier(fmt.get("type"))} '
                  f'strict={spec.get("strict") if type(spec.get("strict")) is bool else "unknown"} '
                  f'schema_bytes={len(schema_bytes) if schema_bytes is not None else "unknown"} '
                  f'schema_sha256={schema_sha or "unknown"} enum_values={enums} empty_enums={empty_enums}',
                  f'  prompt_tokens={_number(prompt_tokens)} completion_tokens={_number(usage.get("completion_tokens", record.get("output_tokens")))} '
                  f'response_bytes={_number(response.get("response_bytes", http_event.get("response_bytes")))}']
        if record.get('status') != 'SUCCEEDED':
            flags = ' '.join(f'{key}={finished[key]}' for key in ('retryable', 'retry_scheduled', 'unknown')
                             if type(finished.get(key)) is bool)
            lines.append('  ' + (flags or '재시도 여부: 기록 없음'))
            if response.get('body_text') == 'Internal Server Error':
                lines.append('  error_body=Internal Server Error (상세 원인 없음)')
            else:
                lowered = _json_bytes(body).decode('utf-8').lower() + str(response.get('body_text') or '').lower()
                hints = [h for h in ('context length', 'maximum context', 'max_tokens', 'json_schema',
                         'response_format', 'out of memory', 'cuda', 'authentication', 'rate limit') if h in lowered]
                lines.append('  error_hints=' + (', '.join(hints) or '알려진 단서 없음; 오류 본문 미출력'))
            if previous_success:
                prev_index, prev_model, prev_chars, prev_schema, prev_max = previous_success
                same = lambda a, b: ('unknown' if a is None or b is None else str(a == b))
                lines.append(f'  직전 성공 #{prev_index:02d} 비교: model_same={same(model, prev_model)} '
                             f'input_chars_delta={sum(chars.values()) - prev_chars if messages and prev_chars is not None else "unknown"} '
                             f'schema_same={same(schema_sha, prev_schema)} '
                             f'max_tokens_same={same(request.get("max_tokens"), prev_max)}')
        else:
            previous_success = (index, model, sum(chars.values()) if messages else None,
                                schema_sha, request.get('max_tokens'))
        lines.append('')
    if not attempts:
        lines.append('model_attempt 원장이 없어 실제 요청 비교 불가. 아래는 서비스 이벤트만 요약합니다.')
        for event in service:
            if event.get('event') in ('model.attempt.failed', 'model.attempt.received'):
                lines.append(f'  {_identifier(event.get("attempt_id"))} {_identifier(event.get("event"))} '
                             f'HTTP {_number(event.get("http_status"))}')
    lines += ['input_chars는 문자열 길이이며 토큰 수가 아닙니다. request_json_bytes는 저장 요청의 재직렬화 크기입니다.',
              'unknown은 기록 없음입니다. 입력/스키마 변화만으로 HTTP 500의 원인을 확정할 수 없습니다.',
              '서버 내부 예외는 같은 시각의 LLM 서빙/게이트웨이 로그에서 확인해야 합니다.']
    return '\n'.join(lines) + '\n'


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
    parser.add_argument("--models-only", action="store_true", help="모델 호출 상태·입력 크기·설정만 출력 (원문 제외)")
    parser.add_argument("--output", required=True, type=Path, help="새 TXT 파일 경로")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    content = (summarize_models(report) if args.models_only else
               summarize(report, _workflow_events(args.workflow_log, str(report.get("request_id") or ""))))
    with args.output.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content)
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
