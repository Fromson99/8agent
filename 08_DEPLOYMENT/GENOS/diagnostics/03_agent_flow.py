#!/usr/bin/env python3
"""List agent decisions, tool/model steps, and journal completeness in order."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from trace_common import DEFAULT_ROOT, latest, output, records


EVENT_FIELDS = ('phase', 'stage', 'http_status', 'duration_ms', 'candidate_count',
                'selected_count', 'context_count', 'answer_chars', 'claim_count',
                'unresolved_count', 'failure_kind', 'error_code')


def summarize(report: dict) -> dict:
    journal = report.get('journal') or {}
    timeline = journal.get('timeline') or []
    sequences = [item.get('event', {}).get('seq') for item in timeline]
    valid_sequences = [seq for seq in sequences if isinstance(seq, int)]
    event_flow = []
    for item in report.get('service_events') or []:
        event_flow.append({'ts': item.get('ts'), 'event': item.get('event'),
                           **{key: item[key] for key in EVENT_FIELDS if key in item}})
    journal_flow = []
    for item in timeline:
        event = item.get('event') or {}
        created = item.get('created_records') or []
        journal_flow.append({
            'seq': event.get('seq'), 'kind': event.get('kind'),
            'decision': (event.get('payload') or {}).get('decision'),
            'records': [
                {'table': row.get('table'),
                 **({'status': row['record'].get('status')} if row.get('table') in ('model_attempt', 'observation') else {}),
                 **({'kind': row['record'].get('kind')} if row.get('table') == 'entity_version' else {}),
                 **({'tool': row['record'].get('tool')} if row.get('table') == 'observation' else {})}
                for row in created if isinstance(row.get('record'), dict)]})
    run_rows = (journal.get('state') or {}).get('run') or []
    run = run_rows[0] if run_rows else {}
    result = report.get('result') or {}
    body = result.get('body') or {}
    answer = body.get('answer') if isinstance(body, dict) else None
    answer = answer if isinstance(answer, dict) else {}
    return {
        'request_id': report.get('request_id'), 'run_id': report.get('run_id'),
        'http_status': result.get('status'), 'journal_status': journal.get('status'),
        'run_status': run.get('status'), 'run_phase': run.get('phase'),
        'event_sequence_contiguous': valid_sequences == list(range(1, len(valid_sequences) + 1)),
        'journal_event_count': len(timeline),
        'table_record_counts': dict(Counter(row.get('table') for item in timeline
                                            for row in item.get('created_records') or [])),
        'model_attempt_count': len(list(records(report, 'model_attempt'))),
        'tool_observation_count': len(list(records(report, 'observation'))),
        'claim_count': len(answer.get('claims') or []),
        'unresolved_count': len(answer.get('unresolved') or []),
        'service_flow': event_flow, 'agent_flow': journal_flow,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--run-id', help='선택한 요청의 32자리 run_id; 생략하면 가장 최근 파일')
    args = parser.parse_args()
    try:
        path, report = latest(args.root, args.run_id)
        output({'file': str(path), **summarize(report)})
    except (OSError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
