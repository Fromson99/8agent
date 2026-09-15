#!/usr/bin/env python3
"""Read-only queue progress; standard library only, no model calls or queue recovery."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3
import sys
import time

SUCCESS = 'REVIEW_PASSED_CANDIDATE'
SUPERSEDED = 'SUPERSEDED_BY_REWORK'


def snapshot(queue, failures=5):
    path = Path(queue).expanduser()
    if path.is_dir():
        path /= 'queue.sqlite'
    if not path.is_file():
        raise ValueError('queue.sqlite not found; run prepare first: ' + str(path))
    # mode=ro avoids creating a missing DB; no immutable flag (must see live WAL commits).
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        all_states = dict(db.execute('SELECT state,count(*) FROM job GROUP BY state'))
        active = sum(n for s, n in all_states.items() if s != SUPERSEDED)
        counts = lambda sql: db.execute(sql).fetchone()[0]
        attempted = counts("SELECT count(*) FROM job j WHERE state!='SUPERSEDED_BY_REWORK' AND EXISTS (SELECT 1 FROM attempt a WHERE a.job_id=j.id)")
        attempts = dict(db.execute('SELECT state,count(*) FROM attempt GROUP BY state'))
        stages = dict(db.execute('SELECT stage,count(*) FROM attempt GROUP BY stage'))
        received = counts('SELECT count(*) FROM attempt WHERE response IS NOT NULL')
        first, last, seconds = db.execute('SELECT min(started_at),max(coalesce(finished_at,started_at)),coalesce(sum(latency),0) FROM attempt').fetchone()
        # Handle legacy/malformed usage without treating absent usage as zero-token calls.
        usage = {'known_input_tokens': 0, 'known_output_tokens': 0, 'unknown_usage_attempts': 0}
        for row in db.execute('SELECT usage FROM attempt'):
            try:
                u = json.loads(row[0]) if row[0] else {}
            except (ValueError, TypeError):
                u = {}
            i, o = (u.get('prompt_tokens'), u.get('completion_tokens')) if isinstance(u, dict) else (None, None)
            if type(i) is int and type(o) is int and i >= 0 and o >= 0:
                usage['known_input_tokens'] += i
                usage['known_output_tokens'] += o
            else:
                usage['unknown_usage_attempts'] += 1
        failed = all_states.get('FAILED', 0)
        review = all_states.get('NEEDS_REVIEW', 0)
        passed = all_states.get(SUCCESS, 0)
        waiting = all_states.get('READY', 0)
        running = all_states.get('RUNNING', 0)
        other = {s: n for s, n in all_states.items() if s not in {SUCCESS, SUPERSEDED, 'FAILED', 'NEEDS_REVIEW', 'READY', 'RUNNING'}}
        recent = [dict(r) for r in db.execute("SELECT id,stage,state,substr(error,1,240) AS error FROM job WHERE state IN ('FAILED','NEEDS_REVIEW') ORDER BY id LIMIT ?", (failures,))]
        return {'schema_version': 'genos-progress-v1', 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'queue': str(path.resolve()), 'jobs': {'total_active': active, 'attempted_active': attempted,
                'never_attempted': active-attempted, 'passed': passed, 'failed': failed, 'needs_review': review,
                'waiting': waiting, 'running_recorded': running, 'remaining_to_success': active-passed,
                'settled': passed+failed+review, 'superseded_history': all_states.get(SUPERSEDED, 0),
                'pass_percent': round(100*passed/active, 2) if active else 0, 'other_states': other},
                'calls': {'attempts_total': sum(attempts.values()), 'responses_saved': received,
                          'by_stage': stages, 'by_state': attempts, 'unknown_remote_completion': attempts.get('INTERRUPTED_UNKNOWN', 0),
                          'recorded_in_flight': attempts.get('STARTED', 0)}, 'usage': usage,
                'timing': {'first_attempt_unix': first, 'latest_attempt_unix': last, 'summed_call_seconds': seconds},
                'failure_samples': recent,
                'notes': ['Counts cover this authoring queue only, not downstream RAG calls.',
                          'Attempts are durable request claims, not guaranteed provider executions.',
                          'Remaining includes failed/review-held jobs; exhausted jobs require explicit retry/rework.',
                          'RUNNING/STARTED are persisted states, not proof that a process is alive.']}


def render(data):
    j, c, u = data['jobs'], data['calls'], data['usage']
    n = lambda x: format(x, ',')
    lines = [f"GENOS 구축 진행 | {data['observed_at']}", f"큐: {data['queue']}",
             f"전체 작업 {n(j['total_active'])} | 시도한 작업 {n(j['attempted_active'])} | 아직 미시도 {n(j['never_attempted'])}",
             f"성공 {n(j['passed'])} ({j['pass_percent']}%) | 실패 {n(j['failed'])} | 검토 보류 {n(j['needs_review'])}",
             f"남은 작업 {n(j['remaining_to_success'])} [대기 {n(j['waiting'])} / 실행중 기록 {n(j['running_recorded'])} / 실패·보류 포함]",
             f"호출 시도 {n(c['attempts_total'])} | 응답 저장 {n(c['responses_saved'])} | " + ' / '.join(f'{k} {n(v)}' for k,v in sorted(c['by_stage'].items())),
             f"응답 검증 실패 {n(c['by_state'].get('INVALID',0))} | 전송 오류 {n(c['by_state'].get('TRANSPORT_ERROR',0))} | 결과 불명 {n(c['unknown_remote_completion'])}",
             f"알려진 토큰: 입력 {n(u['known_input_tokens'])} / 출력 {n(u['known_output_tokens'])} | 사용량 미확인 시도 {n(u['unknown_usage_attempts'])}",
             f"대체된 과거 작업 {n(j['superseded_history'])} (전체 작업에서 제외, 호출 이력은 포함)"]
    if j['other_states']:
        lines.append('기타 상태: '+json.dumps(j['other_states'], ensure_ascii=False))
    if data['failure_samples']:
        lines.append('실패·보류 예시:')
        for r in data['failure_samples']:
            # Avoid terminal control sequences in untrusted model error text.
            error = ''.join(ch if ch.isprintable() else ' ' for ch in (r['error'] or '상세 오류 없음'))
            lines.append(f"  {r['id']} [{r['stage']}/{r['state']}] {error}")
    lines.append('※ 작업 단위는 분할 조각이며 조문 수와 다를 수 있습니다. 이 큐의 구축 호출만 집계합니다.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', required=True, help='queue directory or queue.sqlite')
    parser.add_argument('--watch', type=float, default=0, metavar='SECONDS')
    parser.add_argument('--json', action='store_true', help='watch mode emits JSON Lines')
    parser.add_argument('--failures', type=int, default=5)
    args = parser.parse_args(argv)
    if args.watch < 0 or 0 < args.watch < 1 or args.failures < 0:
        parser.error('--watch must be 0 or >=1; --failures must be >=0')
    try:
        while True:
            try:
                data = snapshot(args.queue, args.failures)
                if args.watch and sys.stdout.isatty() and not args.json:
                    print('\033[2J\033[H', end='')
                print(json.dumps(data, ensure_ascii=False) if args.json else render(data), flush=True)
            except (ValueError, sqlite3.Error, OSError) as exc:
                if args.json:
                    print(json.dumps({'error': str(exc)}, ensure_ascii=False), flush=True)
                else:
                    print('상태 조회 실패: '+str(exc), file=sys.stderr, flush=True)
                if not args.watch:
                    return 2
            if not args.watch:
                return 0
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 0

if __name__ == '__main__':
    raise SystemExit(main())
