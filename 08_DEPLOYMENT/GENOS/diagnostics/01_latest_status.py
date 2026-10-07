#!/usr/bin/env python3
"""Summarize recent request outcomes without printing questions or answers."""
from __future__ import annotations

import argparse
from pathlib import Path

from trace_common import DEFAULT_ROOT, load, output, paths, records


def summarize(path: Path, report: dict) -> dict:
    result = report.get('result') or {}
    body = result.get('body') if isinstance(result, dict) else None
    body = body if isinstance(body, dict) else {}
    answer = body.get('answer')
    answer = answer if isinstance(answer, dict) else {}
    attempts = list(records(report, 'model_attempt'))
    statuses = [(row.get('response') or {}).get('status_code') for row in attempts]
    return {
        'file': str(path), 'created_at': report.get('created_at'),
        'request_id': report.get('request_id'), 'run_id': report.get('run_id'),
        'api_type': report.get('api_type'), 'http_status': result.get('status'),
        'journal_status': (report.get('journal') or {}).get('status'),
        'model_attempts': len(attempts), 'model_http_statuses': statuses,
        'answer_chars': len(answer.get('text') or ''),
        'claim_count': len(answer.get('claims') or []),
        'unresolved_count': len(answer.get('unresolved') or []),
        'error_events': [item.get('event') for item in report.get('service_events') or []
                         if item.get('level') == 'ERROR'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit는 1부터 100까지입니다')
    try:
        found = paths(args.root)[:args.limit]
        output([summarize(path, load(path)) for path in found])
    except (OSError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
