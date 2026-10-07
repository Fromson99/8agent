#!/usr/bin/env python3
"""Inspect model request shape and upstream rejection without printing prompts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from trace_common import DEFAULT_ROOT, latest, load, output, paths, records


HINTS = ('json_schema', 'response_format', 'max_tokens', 'chat_template_kwargs',
         'enable_thinking', 'context length', 'token limit', 'rate limit',
         'authentication', 'permission', 'payload too large')


def inspect_attempt(row: dict, *, show_message: bool = False) -> dict:
    request = row.get('request') or {}
    response = row.get('response') or {}
    body = response.get('body_json') or {}
    body = body if isinstance(body, dict) else {}
    error = body.get('error')
    error = error if isinstance(error, dict) else {}
    fmt = request.get('response_format') or {}
    schema = fmt.get('json_schema') or {}
    messages = request.get('messages') or []
    message = error.get('message') or body.get('message') or response.get('body_text')
    message = message if isinstance(message, str) else None
    detail = body.get('detail')
    locations = []
    if isinstance(detail, list):
        for item in detail[:10]:
            if isinstance(item, dict):
                locations.append({'loc': item.get('loc'), 'type': item.get('type')})
    out = {
        'attempt_id': row.get('attempt_id'), 'attempt_no': row.get('attempt_no'),
        'status': row.get('status'), 'http_status': response.get('status_code'),
        'model': request.get('model'), 'max_tokens': request.get('max_tokens'),
        'stream': request.get('stream'), 'temperature': request.get('temperature'),
        'response_format_type': fmt.get('type'), 'json_schema_name': schema.get('name'),
        'json_schema_strict': schema.get('strict'),
        'schema_property_count': len((schema.get('schema') or {}).get('properties') or {}),
        'enable_thinking': (request.get('chat_template_kwargs') or {}).get('enable_thinking'),
        'message_count': len(messages),
        'message_content_chars': [len(json.dumps(item.get('content'), ensure_ascii=False))
                                  for item in messages if isinstance(item, dict)],
        'upstream_error_type': error.get('type'),
        'upstream_error_code': error.get('code'),
        'upstream_error_param': error.get('param'),
        'validation_locations': locations,
        'upstream_message_chars': len(message) if message is not None else None,
        'upstream_message_sha256': hashlib.sha256(message.encode()).hexdigest() if message else None,
        'upstream_message_hints': [hint for hint in HINTS if message and hint in message.casefold()],
    }
    if show_message:
        out['upstream_message_LOCAL_ONLY'] = message
    return out


def select_report(root: Path, run_id: str | None, *, newest: bool = False):
    if run_id is not None or newest:
        path, report = latest(root, run_id)
        return path, report, 'specified_run_id' if run_id is not None else 'newest_report'
    # A later source-only or browsing turn must not hide the preceding model
    # rejection. Walk newest first and select the first actual model failure.
    for path in paths(root):
        report = load(path)
        attempts = list(records(report, 'model_attempt'))
        if any(isinstance((row.get('response') or {}).get('status_code'), int)
               and (row.get('response') or {})['status_code'] >= 400 for row in attempts):
            return path, report, 'latest_model_failure'
        if any(event.get('event') == 'model_http.failed'
               for event in report.get('service_events') or []):
            return path, report, 'latest_model_failure'
    path, report = latest(root)
    return path, report, 'no_model_failure_found_newest_report'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--run-id', help='선택한 요청의 32자리 run_id; 생략하면 가장 최근 모델 실패')
    parser.add_argument('--newest', action='store_true', help='모델 실패와 무관하게 가장 최근 요청 선택')
    parser.add_argument('--show-message', action='store_true',
                        help='오류 원문을 현장 화면에만 표시; 외부 공유 전 내부 정보 확인')
    args = parser.parse_args()
    if args.run_id and args.newest:
        parser.error('--run-id와 --newest는 함께 사용할 수 없습니다')
    try:
        path, report, selection = select_report(args.root, args.run_id, newest=args.newest)
        attempts = [inspect_attempt(row, show_message=args.show_message)
                    for row in records(report, 'model_attempt')]
        output({'file': str(path), 'selection': selection, 'run_id': report.get('run_id'),
                'journal_status': (report.get('journal') or {}).get('status'),
                'failed_attempts': [row for row in attempts
                                    if isinstance(row['http_status'], int) and row['http_status'] >= 400],
                'all_attempt_count': len(attempts),
                'model_http_failures': [
                    {key: event.get(key) for key in ('event', 'http_status', 'failure_kind',
                        'upstream_error_type', 'upstream_error_code', 'upstream_error_param',
                        'validation_locations', 'validation_error_types', 'upstream_error_hints')}
                    for event in report.get('service_events') or []
                    if event.get('event') == 'model_http.failed'],
                'note': '오류 원문은 --show-message에서만 현장 출력합니다. 질문·원문·프롬프트는 출력하지 않습니다.'})
    except (OSError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
