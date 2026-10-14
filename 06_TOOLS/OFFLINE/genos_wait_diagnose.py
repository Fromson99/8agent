#!/usr/bin/env python3
"""Read existing logs and separate LLM HTTP waits from measured search spans.

Standard library only. No network, model, SQL, or source write. Output omits
questions, model content, credentials and raw error messages.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

EVENTS = ('model_http.started', 'model_http.finished', 'model_http.failed',
          'model.attempt.started', 'model.attempt.received', 'model.attempt.failed',
          'request.started', 'request.returning', 'request.heartbeat',
          'step.started', 'step.finished', 'step.failed', 'fulltext.search.finished')
FIELDS = {'event', 'request_id', 'attempt_id', 'phase', 'duration_ms', 'elapsed_ms',
          'step', 'work_ms', 'http_status', 'prompt_tokens', 'completion_tokens',
          'cached_tokens', 'thinking_requested', 'thinking_observation',
          'stream_requested', 'cache_hit', 'cache_storage', 'cache_overflow',
          'cache_admitted', 'cache_evictions', 'worker_id', 'process_id',
          'sql_execute_ms', 'sql_fetch_ms', 'timestamp'}


def parse(line):
    if line.lstrip().startswith('{'):
        try:
            value = json.loads(line)
        except ValueError:
            return None
        if not isinstance(value, dict) or value.get('event') not in EVENTS:
            return None
        return {key: value[key] for key in FIELDS if key in value}
    match = re.match(r'^(\S+)\s+(?:INFO|WARNING|ERROR|DEBUG)\s+(' +
                     '|'.join(re.escape(event) for event in EVENTS) + r')\s', line.strip())
    if not match:
        return None
    row = {'event': match[2], 'timestamp': match[1]}
    for key, raw in re.findall(r'\b([a-z_]+)=([^\s]+)', line[match.end():]):
        if key not in FIELDS:
            continue
        try:
            row[key] = json.loads(raw)
        except ValueError:
            row[key] = raw
    return row


def summarize(lines, request_id=None):
    groups = defaultdict(list)
    seen = set()
    for line in lines:
        row = parse(line)
        if not row or not row.get('request_id'):
            continue
        if request_id is not None and row['request_id'] != request_id:
            continue
        identity = json.dumps(row, sort_keys=True, separators=(',', ':'))
        if identity in seen:
            continue
        seen.add(identity)
        groups[row['request_id']].append(row)
    requests = []
    for ident, rows in groups.items():
        http = [row for row in rows if row['event'] in ('model_http.finished', 'model_http.failed')
                and isinstance(row.get('duration_ms'), (int, float))]
        attempts = [row for row in rows if row['event'] == 'model.attempt.received']
        spans = defaultdict(list)
        for row in rows:
            if row['event'] in ('step.finished', 'step.failed') and isinstance(row.get('duration_ms'), (int, float)):
                spans[row.get('step', 'unknown')].append(row['duration_ms'])
        totals = [row['duration_ms'] for row in rows if row['event'] == 'request.returning'
                  and isinstance(row.get('duration_ms'), (int, float))]
        heartbeat = [row['elapsed_ms'] for row in rows if row['event'] == 'request.heartbeat'
                     and isinstance(row.get('elapsed_ms'), (int, float))]
        # HTTP and attempt durations overlap: report both, never add them together.
        requests.append({'request_id': ident,
                         'completed_or_failed_model_http_calls': len(http),
                         'sum_model_http_ms': sum(row['duration_ms'] for row in http) if http else None,
                         'max_request_return_ms': max(totals) if totals else None,
                         'max_observed_heartbeat_elapsed_ms': max(heartbeat) if heartbeat else None,
                         'model_http_calls': http, 'model_attempt_receipts': attempts,
                         'workers': sorted({row['worker_id'] for row in rows if row.get('worker_id')}),
                         'measured_spans': [{'step': key, 'count': len(values), 'sum_ms': sum(values),
                                             'max_ms': max(values)} for key, values in sorted(spans.items())],
                         'search_timing_available': any(key.startswith(('unit_fts.', 'law.recall.',
                                                        'resident_data.', 'resources.fulltext')) for key in spans)})
    return {'schema': 'genos-wait-diagnosis-v1', 'requests': requests,
            'notes': ['Missing search spans mean unmeasured, not zero search time.',
                      'model_http time includes upstream queue/prefill/generation/network wait.',
                      'cached_tokens=null means model prompt-cache statistics were not reported.',
                      'Nested spans and model HTTP/attempt times overlap. Concurrent call sums are not wall-clock time.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('log', type=Path)
    parser.add_argument('--request-id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with args.log.open(encoding='utf-8', errors='replace') as stream:
        result = summarize(stream, args.request_id)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
