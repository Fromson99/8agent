"""Bounded, standard-library-only reader of existing GENOS request reports."""
import argparse
import bisect
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

MAX_INPUT = 256 * 1024 * 1024
MAX_EVENT = 16 * 1024 * 1024
MAX_EVENTS = 50000
TOKEN = re.compile(r'[A-Za-z0-9_.:-]{1,160}\Z')
SPECIAL = re.compile(r'["\\\x00-\x1f]')
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')


class ExtractionError(Exception):
    pass


class Reader:
    """Validate JSON incrementally; only selected small values are materialized."""
    def __init__(self, stream):
        self.stream, self.buf, self.i = stream, '', 0
        self.bytes = self.pos = 0
        self.deadline = time.monotonic() + 60
        self.event_start = None
        self.journal_number = 0

    def peek(self):
        if self.i == len(self.buf):
            if time.monotonic() > self.deadline:
                raise ExtractionError('READ_TIME_LIMIT')
            self.buf, self.i = self.stream.read(65536), 0
            self.bytes += len(self.buf.encode('utf-8'))
            if self.bytes > MAX_INPUT:
                raise ExtractionError('INPUT_SIZE_LIMIT')
        return self.buf[self.i:self.i + 1]

    def advance(self, n=1):
        self.i += n
        self.pos += n
        if self.event_start is not None and self.pos - self.event_start > MAX_EVENT:
            raise ExtractionError('EVENT_SIZE_LIMIT')

    def ws(self):
        while self.peek() and self.peek() in ' \t\r\n':
            match = re.match(r'[ \t\r\n]+', self.buf[self.i:])
            self.advance(len(match[0]))

    def expect(self, char):
        self.ws()
        if self.peek() != char:
            raise ExtractionError('JSON_FORMAT_OR_TRUNCATED')
        self.advance()

    def string(self, keep):
        self.expect('"')
        parts, size = ['"'] if keep else None, 0
        while True:
            if not self.peek():
                raise ExtractionError('JSON_TRUNCATED_STRING')
            match = SPECIAL.search(self.buf, self.i)
            end = match.start() if match else len(self.buf)
            chunk = self.buf[self.i:end]
            self.advance(len(chunk))
            size += len(chunk)
            if keep:
                parts.append(chunk)
                if size > MAX_EVENT:
                    raise ExtractionError('STRING_SIZE_LIMIT')
            char = self.peek()
            if not match:
                continue
            self.advance()
            if char == '"':
                if keep:
                    parts.append('"')
                    return json.loads(''.join(parts))
                return None
            if char != '\\':
                raise ExtractionError('JSON_CONTROL_CHARACTER')
            escaped = self.peek()
            if not escaped or escaped not in '"\\/bfnrtu':
                raise ExtractionError('JSON_ESCAPE')
            self.advance()
            suffix = escaped
            if escaped == 'u':
                for _ in range(4):
                    digit = self.peek()
                    if not digit or digit not in '0123456789abcdefABCDEF':
                        raise ExtractionError('JSON_UNICODE_ESCAPE')
                    suffix += digit
                    self.advance()
            if keep:
                parts.append('\\' + suffix)

    def value(self, keep=False, depth=0):
        if depth > 64:
            raise ExtractionError('JSON_DEPTH_LIMIT')
        self.ws()
        char = self.peek()
        if char == '"':
            return self.string(keep)
        if char in ('{', '['):
            obj = char == '{'
            self.advance()
            out = ({} if obj else []) if keep else None
            close = '}' if obj else ']'
            self.ws()
            if self.peek() == close:
                self.advance()
                return out
            while True:
                if obj:
                    key = self.string(keep)
                    self.expect(':')
                    if keep and key in out:
                        raise ExtractionError('DUPLICATE_EVENT_FIELD')
                item = self.value(keep, depth + 1)
                if keep:
                    if obj:
                        out[key] = item
                    else:
                        out.append(item)
                self.ws()
                if self.peek() == close:
                    self.advance()
                    return out
                self.expect(',')
        literal = ''
        while self.peek() and self.peek() not in ',]} \r\n\t':
            literal += self.peek()
            self.advance()
            if len(literal) > 128:
                raise ExtractionError('JSON_LITERAL_LIMIT')
        if literal not in ('true', 'false', 'null') and not NUMBER.fullmatch(literal):
            raise ExtractionError('JSON_LITERAL')
        result = json.loads(literal)
        if isinstance(result, float) and not math.isfinite(result):
            raise ExtractionError('NONFINITE_NUMBER')
        return result if keep else None

    def array(self, consume):
        self.expect('[')
        self.ws()
        if self.peek() != ']':
            while True:
                consume()
                self.ws()
                if self.peek() == ']':
                    break
                self.expect(',')
        self.expect(']')

    def mapping(self, consume):
        self.expect('{')
        keys = set()
        self.ws()
        if self.peek() != '}':
            while True:
                key = self.string(True)
                if key in keys:
                    raise ExtractionError('DUPLICATE_JOURNAL_FIELD')
                keys.add(key)
                self.expect(':')
                consume(key)
                self.ws()
                if self.peek() == '}':
                    break
                self.expect(',')
        self.expect('}')

    def journal(self, rows, depth=0):
        if depth > 8:
            raise ExtractionError('JOURNAL_DEPTH_LIMIT')
        self.journal_number += 1
        scope = 'J' + str(self.journal_number)
        def entry():
            def field(key):
                if key != 'event':
                    self.value(False)
                    return
                self.event_start = self.pos
                event = self.value(True)
                self.event_start = None
                if not isinstance(event, dict):
                    raise ExtractionError('INVALID_JOURNAL_EVENT')
                payload = event.get('payload')
                payload = payload if isinstance(payload, dict) else {}
                row = project({**payload, 'event': 'journal.' + (token(event.get('kind')) or 'UNKNOWN'),
                               'ts': event.get('created_at')}, len(rows) + 1)
                row['journal_scope'] = scope
                rows.append(row)
                if len(rows) > MAX_EVENTS:
                    raise ExtractionError('EVENT_COUNT_LIMIT')
            self.mapping(field)
        def child():
            self.mapping(lambda k: self.journal(rows, depth + 1) if k == 'journal' else self.value(False))
        def field(key):
            if key == 'timeline':
                self.array(entry)
            elif key == 'children':
                self.array(child)
            else:
                self.value(False)
        self.mapping(field)

    def report(self):
        self.expect('{')
        root, rows, keys = {}, [], set()
        self.ws()
        if self.peek() == '}':
            raise ExtractionError('UNSUPPORTED_REPORT')
        while True:
            key = self.string(True)
            if key in keys:
                raise ExtractionError('DUPLICATE_ROOT_FIELD')
            keys.add(key)
            self.expect(':')
            if key == 'service_events':
                self.expect('[')
                self.ws()
                if self.peek() != ']':
                    while True:
                        self.event_start = self.pos
                        row = self.value(True)
                        self.event_start = None
                        if not isinstance(row, dict):
                            raise ExtractionError('INVALID_EVENT')
                        rows.append(project(row, len(rows) + 1))
                        if len(rows) > MAX_EVENTS:
                            raise ExtractionError('EVENT_COUNT_LIMIT')
                        self.ws()
                        if self.peek() == ']':
                            break
                        self.expect(',')
                self.expect(']')
            elif key in ('schema_version', 'request_id', 'run_id', 'component'):
                root[key] = self.value(True)
                if not isinstance(root[key], (str, type(None))):
                    raise ExtractionError('INVALID_REPORT_METADATA')
            elif key == 'journal':
                self.journal(rows)
            else:
                self.value(False)
            self.ws()
            if self.peek() == '}':
                self.advance()
                break
            self.expect(',')
        self.ws()
        if self.peek():
            raise ExtractionError('TRAILING_REPORT_DATA')
        if root.get('schema_version') != 'genos-request-report-v1' or 'service_events' not in keys:
            raise ExtractionError('UNSUPPORTED_REPORT')
        if not rows:
            raise ExtractionError('NO_RECORDED_EVENTS')
        return {k: token(v) for k, v in root.items()}, rows


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def token(value):
    return value if isinstance(value, str) and TOKEN.fullmatch(value) else None


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.timestamp() if dt.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


TEXT_FIELDS = set('event phase source_stage step status purpose schema run_id request_id workflow_request_id workflow_run_id attempt_id logical_call_id previous_event previous_step failure_kind error_code error_type finish_reason thinking_observation journal_status transport_backend stream_termination'.split())
NUM_FIELDS = set('attempt_no call prompt_tokens completion_tokens total_tokens cached_tokens reasoning_tokens reasoning_chars request_bytes response_bytes response_content_chars tool_argument_chars input_message_count input_content_chars input_content_utf8_bytes input_system_chars input_user_chars input_messages_json_bytes response_format_chars response_format_utf8_bytes canonical_schema_bytes wire_schema_bytes max_tokens prompt_plus_max_tokens http_status result_count fetched_count selected_count source_count document_count unit_count checked_count query_count sql_count cache_hits cache_misses dropped_count write_error_count seconds'.split())
BOOL_FIELDS = set('thinking_requested thinking_control_present reasoning_field_present reasoning_nonempty thought_channel_marker_present stream_requested stream_complete retry_scheduled retryable unknown committed context_limit_known output_cap_reached changed write'.split())


def project(row, index):
    out = {'index': index, 'event': token(row.get('event')) or 'UNRECOGNIZED_EVENT',
           'ts': row.get('ts') if stamp(row.get('ts')) is not None else None}
    for key, value in row.items():
        if key in TEXT_FIELDS and token(value) is not None:
            out[key] = value
        elif key in BOOL_FIELDS and (type(value) is bool or value is None):
            out[key] = value
        elif (key in NUM_FIELDS or (token(key) and key.endswith('_ms'))) and (numeric(value) or value is None):
            out[key] = value
    if row.get('event') == 'oracle.sql' and row.get('binding') is not None:
        out['binding_fingerprint'] = hashlib.sha256(json.dumps(row['binding'], sort_keys=True).encode()).hexdigest()[:24]
    if row.get('event') == 'execution.metrics':
        stats = row.get('execution_stats')
        if isinstance(stats, dict) and stats.get('schema_version') == 'rag-execution-stats-v1':
            out['execution_stats'] = {k: stats[k] for k in ('request_duration_ms', 'llm_duration_ms', 'llm_calls') if numeric(stats.get(k))}
            out['execution_stats']['timing_complete'] = stats.get('timing_complete') is True
    if row.get('event') == 'session.prepare.timings' and isinstance(row.get('phases'), dict):
        out['phases'] = {k: {n: v for n, v in d.items() if n in ('wall_ms', 'thread_cpu_ms') and numeric(v)}
                         for k, d in row['phases'].items() if k in ('session.store', 'session.resources', 'session.context', 'session.journal', 'session.sources', 'session.gateway') and isinstance(d, dict)}
    return out


def analyze(meta, rows):
    warnings = []
    timed = sorted((r for r in rows if stamp(r['ts']) is not None), key=lambda r: (stamp(r['ts']), r['index']))
    if len(timed) != len(rows):
        warnings.append('INVALID_OR_MISSING_EVENT_TIMESTAMPS')
    runs = defaultdict(set)
    for r in rows:
        if r.get('attempt_id') and r.get('run_id'):
            runs[r['attempt_id']].add(r['run_id'])
    attempts = {}
    for r in rows:
        if not r['event'].startswith(('model.call.', 'model_http.', 'model.attempt.')):
            continue
        ident = r.get('attempt_id')
        if not ident:
            warnings.append('MODEL_EVENT_WITHOUT_ATTEMPT_ID')
            continue
        run = r.get('run_id')
        if not run and len(runs[ident]) == 1:
            run = next(iter(runs[ident]))
        elif not run and len(runs[ident]) > 1:
            warnings.append('AMBIGUOUS_ATTEMPT_RUN')
            continue
        key = (run, ident)
        attempt = attempts.setdefault(key, {'run_id': run, 'attempt_id': ident, 'events': []})
        attempt['events'].append(r)
    calls, valid_intervals = [], []
    for attempt in attempts.values():
        events = attempt['events']
        starts = [r for r in events if r['event'] == 'model.call.started']
        ends = [r for r in events if r['event'] == 'model.call.finished']
        attempt['paired'] = (len(starts) == len(ends) == 1 and stamp(starts[0]['ts']) is not None and stamp(ends[0]['ts']) is not None
                             and stamp(ends[0]['ts']) >= stamp(starts[0]['ts']) and starts[0]['index'] < ends[0]['index'])
        attempt['call_duration_ms'] = ends[0].get('duration_ms') if len(ends) == 1 else None
        attempt['start_ts'] = starts[0]['ts'] if len(starts) == 1 else None
        attempt['end_ts'] = ends[0]['ts'] if len(ends) == 1 else None
        attempt['metadata'] = {}
        for r in events:
            attempt['metadata'].update({k: v for k, v in r.items() if k in TEXT_FIELDS | NUM_FIELDS | BOOL_FIELDS and k not in ('event', 'run_id', 'request_id', 'previous_event', 'previous_step')})
        if not attempt['paired']:
            warnings.append('UNPAIRED_OR_DUPLICATE_MODEL_BOUNDARY')
        elif numeric(attempt['call_duration_ms']) and abs((stamp(attempt['end_ts']) - stamp(attempt['start_ts'])) * 1000 - attempt['call_duration_ms']) > 250:
            warnings.append('MODEL_WALL_CLOCK_VS_MONOTONIC_MISMATCH')
        calls.append(attempt)
    calls.sort(key=lambda c: (stamp(c['start_ts']) if stamp(c['start_ts']) is not None else float('inf'), c['attempt_id']))
    for i, c in enumerate(calls, 1):
        c['number'] = i
        if c['paired']:
            valid_intervals.append([stamp(c['start_ts']), stamp(c['end_ts']), [i]])
    merged = []
    for begin, end, numbers in sorted(valid_intervals):
        if merged and begin < merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
            merged[-1][2].extend(numbers)
        else:
            merged.append([begin, end, numbers])
    overlaps = any(len(c[2]) > 1 for c in merged)
    snapshots = [r['execution_stats'] for r in rows if 'execution_stats' in r]
    measured = [c['call_duration_ms'] for c in calls if numeric(c['call_duration_ms'])]
    matches = [s for s in snapshots if s.get('llm_calls') == len(calls) and len(measured) == len(calls)
               and numeric(s.get('llm_duration_ms')) and abs(s['llm_duration_ms'] - sum(measured)) <= len(calls)]
    selected = matches[-1] if matches else None
    if not selected:
        warnings.append('NO_REQUEST_METRICS_MATCHING_ALL_MODEL_ATTEMPTS')
    elif selected.get('timing_complete') is not True:
        warnings.append('MODEL_TIMING_INCOMPLETE')
    if not calls:
        warnings.append('NO_MODEL_BOUNDARIES')
    exact = not warnings
    gaps = []
    if exact and merged:
        for left, right in zip(merged, merged[1:]):
            gaps.append({'label': '호출 ' + ','.join(map(str, left[2])) + ' → ' + ','.join(map(str, right[2])), 'start': left[1], 'end': right[0]})
        qid = meta.get('request_id')
        request_rows = [r for r in timed if not r.get('request_id') or r.get('request_id') == qid]
        first = next((r for r in request_rows if r['event'] == 'request.started'), None)
        last = next((r for r in reversed(request_rows) if r['event'] in ('request.returning', 'request.finished')), None)
        if first and stamp(first['ts']) <= merged[0][0]:
            gaps.append({'label': '요청 시작 → 첫 모델 호출', 'start': stamp(first['ts']), 'end': merged[0][0]})
        if last and stamp(last['ts']) >= merged[-1][1]:
            gaps.append({'label': '마지막 모델 호출 → 요청 종료', 'start': merged[-1][1], 'end': stamp(last['ts'])})
    times = [stamp(r['ts']) for r in timed]
    for gap in gaps:
        gap['seconds'] = round(gap['end'] - gap['start'], 6)
        inside = timed[bisect.bisect_left(times, gap['start']):bisect.bisect_right(times, gap['end'])]
        meaningful = [r for r in inside if r['event'] != 'request.heartbeat']
        points = [{'ts': datetime.fromtimestamp(gap['start']).astimezone().isoformat(), 'event': 'BOUNDARY_START'}]
        points += meaningful
        points += [{'ts': datetime.fromtimestamp(gap['end']).astimezone().isoformat(), 'event': 'BOUNDARY_END'}]
        segments = [{'seconds': round(stamp(b['ts']) - stamp(a['ts']), 6), 'after_event': label(a), 'before_event': label(b)}
                    for a, b in zip(points, points[1:]) if stamp(b['ts']) > stamp(a['ts'])]
        gap['largest_adjacent_event_intervals'] = sorted(segments, key=lambda s: s['seconds'], reverse=True)[:5]
        gap['event_counts'] = dict(Counter(r['event'] for r in inside))
    oracle_groups = defaultdict(list)
    for r in rows:
        if r['event'] == 'oracle.sql':
            oracle_groups[(r.get('run_id'), r.get('binding_fingerprint'), r.get('call'))].append(r)
    oracle = []
    for (run, binding, call), events in oracle_groups.items():
        starts = [r for r in events if r.get('status') == 'STARTED']
        ends = [r for r in events if r.get('status') in ('ACKNOWLEDGED', 'READ_FAILED', 'WRITE_UNCONFIRMED')]
        paired = len(starts) == len(ends) == 1 and binding is not None and type(call) is int
        paired = paired and starts[0]['ts'] is not None and ends[0]['ts'] is not None and starts[0]['index'] < ends[0]['index'] and stamp(ends[0]['ts']) >= stamp(starts[0]['ts'])
        oracle.append({'run_id': run, 'call': call, 'paired': paired, 'status': ends[0].get('status') if len(ends) == 1 else 'INCOMPLETE',
                       'seconds': round(stamp(ends[0]['ts']) - stamp(starts[0]['ts']), 6) if paired else None})
    return {'schema_version': 'genos-timing-extract-v2', 'metadata': meta, 'warnings': sorted(set(warnings)),
            'exact_model_gaps_available': exact, 'overlapping_model_calls': overlaps, 'selected_execution_stats': selected,
            'execution_snapshots': snapshots, 'calls': calls, 'model_interval_union_seconds': round(sum(e - b for b, e, _ in merged), 6) if exact else None,
            'gaps': sorted(gaps, key=lambda g: g['seconds'], reverse=True), 'oracle_calls': oracle,
            'events': rows, 'timeline': timed}


def label(row):
    detail = [row[k] for k in ('step', 'source_stage', 'status', 'phase') if row.get(k)]
    return row['event'] + (' [' + '/'.join(detail) + ']' if detail else '')


def sec(ms):
    return f'{ms / 1000:.3f}초' if numeric(ms) else '미기록'


def summary(data):
    lines = ['GENOS 시간·모델·구간 상세 R2', '질문/답변/원문/SQL/모델 출력 본문은 제외했습니다.']
    s = data['selected_execution_stats']
    if s:
        lines += [f"요청: {sec(s.get('request_duration_ms'))} / 모델: {sec(s.get('llm_duration_ms'))} / 호출: {s.get('llm_calls')}"]
        if data['exact_model_gaps_available'] and not data['overlapping_model_calls'] and numeric(s.get('request_duration_ms')) and s['request_duration_ms'] >= s['llm_duration_ms']:
            lines += ['요청 - 모델 합계: ' + sec(s['request_duration_ms'] - s['llm_duration_ms'])]
    else:
        lines += ['요청 전체와 모든 모델 호출의 결속 미확인. 개별 계측값은 DIAGNOSTICS.json 참조.']
    if data['overlapping_model_calls']:
        lines += ['겹친 모델 호출 있음: 모델 합계를 전체 시간에서 빼 비모델 시간으로 해석하지 않습니다.']
    lines += ['HTTP/모델/수신 경과는 중첩 계측입니다. 합산하지 않습니다.',
              '모델 타이머는 전송 함수 전체: 네트워크·서버 대기·생성·내부 추론(있다면)·수신이 포함됩니다.',
              '내부 추론 초는 별도 측정되지 않습니다. reasoning 미기록/0은 내부 추론 OFF 증명이 아닙니다.']
    for c in data['calls']:
        m = c['metadata']
        lines += [f"\n호출 {c['number']} | {m.get('source_stage') or m.get('purpose') or m.get('phase') or '단계 미기록'} | 모델 {sec(c['call_duration_ms'])} | 경계완료={c['paired']}",
                  f"  시작 {c['start_ts']} / 종료 {c['end_ts']}"]
        for event_name in ('model_http.finished', 'model_http.failed', 'model.attempt.received', 'model.attempt.failed', 'model.attempt.accepted'):
            for r in c['events']:
                if r['event'] == event_name:
                    lines.append(f"  {event_name}: {sec(r.get('duration_ms'))}; HTTP={r.get('http_status', '미기록')}; 재시도예정={r.get('retry_scheduled', '미기록')}")
        for keys in (('prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'total_tokens'),
                     ('thinking_requested', 'thinking_control_present', 'thinking_observation', 'reasoning_chars', 'reasoning_field_present'),
                     ('input_content_chars', 'response_format_utf8_bytes', 'request_bytes', 'response_bytes', 'finish_reason', 'stream_requested')):
            lines.append('  ' + ' / '.join(k + '=' + str(m.get(k, '미기록')) for k in keys))
    lines += ['\n모델 밖 구간: 긴 순서. 인접 이벤트 시간 차는 원인 확정이나 작업별 실행 시간이 아닙니다.']
    if not data['exact_model_gaps_available']:
        lines += ['모델 경계/계측 불완전 또는 시계 이상: 정확한 구간 분해를 유보합니다.']
    for g in data['gaps'][:10]:
        lines += [f"\n{g['label']}: {g['seconds']:.3f}초"]
        for part in g['largest_adjacent_event_intervals']:
            lines += [f"  {part['seconds']:.3f}초 | {part['after_event']} → {part['before_event']}"]
        lines += ['  이벤트: ' + ', '.join(f'{k}={v}' for k, v in sorted(g['event_counts'].items()))]
    rows = data['events']
    lines += ['\n준비·상태 DB (다른 항목과 포함 관계가 있을 수 있음)']
    for r in rows:
        if r['event'] == 'session.prepare.timings':
            lines += ['준비: ' + sec(r.get('elapsed_ms')) + ' / CPU: ' + sec(r.get('thread_cpu_ms'))]
            for phase, v in r.get('phases', {}).items():
                lines += ['  ' + phase + ': ' + sec(v.get('wall_ms'))]
    journal = [r for r in rows if r['event'] == 'journal.transaction.timings']
    lines += [f"상태 DB 트랜잭션 {len(journal)}건 / 커밋확인 {sum(r.get('committed') is True for r in journal)}건"]
    for key in ('begin_ms', 'body_ms', 'commit_ms'):
        vals = [r[key] for r in journal if numeric(r.get(key))]
        lines += [key + ': ' + (sec(sum(vals)) + f' / 기록 {len(vals)}건' if vals else '미기록')]
    oracle = data['oracle_calls']
    matched = [r for r in oracle if r['paired']]
    lines += [f"\nOracle 왕복 경계: {len(oracle)}건 / 결속 {len(matched)}건 / 미결속 {len(oracle) - len(matched)}건",
              '상태 DB 계측과 별개이며, Oracle 서버 내부 SQL 실행 시간만을 뜻하지 않습니다.']
    if matched:
        lines += [f"결속된 왕복 합계 {sum(r['seconds'] for r in matched):.3f}초 (다른 계측과 합산 금지)"]
        for r in sorted(matched, key=lambda r: r['seconds'], reverse=True)[:10]:
            lines += [f"  call={r['call']} {r['status']} {r['seconds']:.3f}초"]
    else:
        lines += ['Oracle 시간 미확인: 이벤트 부재를 Oracle 미사용/0초의 증명으로 삼지 않습니다.']
    durations = [(r.get('duration_ms', r.get('work_ms', r.get('elapsed_ms'))), r) for r in rows
                 if not r['event'].startswith(('model.', 'model_http.', 'request.')) and r['event'] != 'execution.metrics']
    lines += ['\n기록된 개별 작업 경과 상위 15개 (상위/하위 작업 중복 가능)']
    for value, r in sorted((p for p in durations if numeric(p[0])), key=lambda p: p[0], reverse=True)[:15]:
        lines += [f"  {sec(value)} | {label(r)} | CPU {sec(r.get('thread_cpu_ms'))}"]
    logging_rows = [r for r in rows if numeric(r.get('previous_log_ms'))]
    lines += ['\n이전 로그 출력 처리 경과 상위 10개 (logger 호출의 정제/핸들러/쓰기 등; 시간 전체와 중복 가능)']
    for r in sorted(logging_rows, key=lambda r: r['previous_log_ms'], reverse=True)[:10]:
        lines += [f"  {sec(r['previous_log_ms'])} | 이전={r.get('previous_event', '미기록')} / step={r.get('previous_step', '미기록')}"]
    lines += ['\n수집 경고: ' + (', '.join(data['warnings']) if data['warnings'] else '없음'),
              '계측이 꺼져 있거나 기록이 없는 검색/읽기/검증/대기 시간은 복원하지 않습니다.',
              'TIMELINE.txt는 전체 메타데이터 순서, DIAGNOSTICS.json은 같은 결과의 구조화 파일입니다.',
              '서버 코드·설정·DB·모델·MAIN을 변경하지 않았습니다.']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description='기존 GENOS 요청 JSON/gzip의 시간·호출·메타데이터만 추출')
    parser.add_argument('report')
    parser.add_argument('--output-dir', required=True, help='기존 파일을 덮어쓰지 않을 새/빈 결과 폴더')
    args = parser.parse_args(argv)
    try:
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = 384 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (min(limit, hard) if hard >= 0 else limit, hard))
        path = Path(args.report).expanduser()
        before = path.stat()
        opener = gzip.open if path.suffix.lower() == '.gz' else open
        with opener(path, 'rt', encoding='utf-8', errors='strict') as source:
            meta, rows = Reader(source).report()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ExtractionError('REPORT_CHANGED_DURING_READ')
        data = analyze(meta, rows)
        text = summary(data)
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        names = ('SUMMARY.txt', 'TIMELINE.txt', 'DIAGNOSTICS.json')
        if any((out / n).exists() for n in names):
            raise ExtractionError('OUTPUT_EXISTS')
        with (out / 'DIAGNOSTICS.json').open('x', encoding='utf-8') as dest:
            json.dump({k: v for k, v in data.items() if k not in ('timeline',)}, dest, ensure_ascii=False, indent=2, allow_nan=False)
            dest.write('\n')
        with (out / 'TIMELINE.txt').open('x', encoding='utf-8') as dest:
            dest.write('시각은 UTC offset 포함. Δ는 인접 이벤트 사이 시간이며 원인 소요 시간이 아닙니다.\n')
            previous = None
            for row in data['timeline']:
                when = stamp(row['ts'])
                gap = when - previous if previous is not None else 0
                dest.write(f"{row['ts']} Δ={gap:.6f}s #{row['index']} " + json.dumps({k: v for k, v in row.items() if k not in ('index', 'ts')}, ensure_ascii=False) + '\n')
                previous = when
        with (out / 'SUMMARY.txt').open('x', encoding='utf-8') as dest:
            dest.write(text)
        print(text, end='')
        print('EXTRACTION_COMPLETE' if not data['warnings'] else 'EXTRACTION_COMPLETE_WITH_WARNINGS')
        return 0
    except (ExtractionError, OSError, EOFError, UnicodeError, ValueError, TypeError, RecursionError, MemoryError) as exc:
        code = str(exc) if isinstance(exc, ExtractionError) else type(exc).__name__
        print('EXTRACTION_FAILED: ' + code, file=sys.stderr)
        print('완료 표시가 없는 결과는 사용하지 마세요. 원본은 변경하지 않았습니다. 같은 원본으로 재실행 가능합니다.', file=sys.stderr)
        return 1


# Appended before the original bounded reader's main entry point (R2 function/segment timing).
_original_project = project
_original_analyze = analyze
_original_summary = summary
_original_main = main
_CODE_ROOT = None
FRAME = re.compile(r'[A-Za-z0-9_./:<>\[\]-]{1,300}\Z')
FILE = re.compile(r'[A-Za-z0-9_./<>-]{1,200}\Z')
SEGMENT = re.compile(r'(?:PRE|POST|[GM][0-9]{1,4})\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')
SEGMENT_INTS = set('samples gc_count gc_gen2 source_calls check_calls hook_calls threads_max timeslices'.split())
LIST_LIMITS = {'top_own_lines':40, 'top_functions':40, 'top_leaf':25, 'categories':16}


def frame_rows(rows, limit):
    if not isinstance(rows, list) or len(rows) > limit:raise ExtractionError('FUNCTION_PROFILE_LIMIT')
    out = []
    for row in rows:
        if not isinstance(row, dict):raise ExtractionError('INVALID_FRAME_ROW')
        frame = row.get('frame')
        if isinstance(frame, str) and FRAME.fullmatch(frame) and numeric(row.get('ms')) and numeric(row.get('samples')):
            out.append({'frame':frame, 'ms':row['ms'], 'samples':row['samples']})
    return out


def clean_function_rows(value, name, limit):
    rows = value.get(name, [])
    if not isinstance(rows, list) or len(rows) > limit:raise ExtractionError('FUNCTION_PROFILE_LIMIT')
    out = []
    for row in rows:
        if not isinstance(row, dict):raise ExtractionError('INVALID_FUNCTION_ROW')
        clean = {k:v for k,v in row.items() if k in ('function','parent','error_type','segment') and token(v)}
        clean.update({k:v for k,v in row.items() if k in ('calls','errors','candidate_total','candidate_max','wall_ms','self_ms',
            'cpu_ms','self_cpu_ms','max_ms','start_ms','duration_ms') and numeric(v)})
        if type(row.get('failed')) is bool:clean['failed'] = row['failed']
        out.append(clean)
    return out


def safe_profile(value):
    if not isinstance(value, dict) or value.get('schema_version') not in ('genos-function-timing-v1', 'genos-function-timing-v2'):
        raise ExtractionError('INVALID_FUNCTION_PROFILE')
    result = {'schema_version':value['schema_version']}
    for key in ('request_scope_ms','measured_calls','completed_calls','skipped_calls','thread_count','inflight_calls',
                'source_calls','source_unique_blocks','source_repeated_blocks','source_untracked_blocks',
                'model_calls','concurrency_peak','interval_ms'):
        if numeric(value.get(key)):result[key] = value[key]
    for key in ('mode','probe_revision'):
        if token(value.get(key)):result[key] = value[key]
    result['warnings'] = [v for v in value.get('warnings',[])[:40] if token(v)]
    result['functions'] = clean_function_rows(value, 'functions', 256)
    result['edges'] = clean_function_rows(value, 'edges', 512)
    result['slow_calls'] = clean_function_rows(value, 'slow_calls', 30)
    if value['schema_version'] == 'genos-function-timing-v1':
        return result
    sampling = value.get('sampling')
    if not isinstance(sampling, dict):raise ExtractionError('INVALID_SAMPLING')
    result['sampling'] = {k:v for k,v in sampling.items() if k in ('ticks','late_ticks','sampled_ms','sampler_cpu_ms','overflow_ms') and numeric(v)}
    segments = value.get('segments')
    if not isinstance(segments, list) or len(segments) > 200:raise ExtractionError('SEGMENT_LIMIT')
    result['segments'] = []
    for row in segments:
        if not isinstance(row, dict) or not (isinstance(row.get('segment'), str) and SEGMENT.fullmatch(row['segment'])):
            raise ExtractionError('INVALID_SEGMENT')
        clean = {'segment':row['segment']}
        for key, item in row.items():
            if key in ('stage','next_stage','previous_stage') and token(item):clean[key] = item
            elif key == 'same_thread' and type(item) is bool:clean[key] = item
            elif token(key) and (key.endswith('_ms') or key in SEGMENT_INTS or key.startswith(('thread_','process_','cgroup_'))) and numeric(item):
                clean[key] = item
            elif key in LIST_LIMITS:clean[key] = frame_rows(item, LIST_LIMITS[key])
            elif key == 'hooked_functions':clean[key] = clean_function_rows(row, key, 10)
        result['segments'].append(clean)
    aggregate = value.get('nonmodel')
    if not isinstance(aggregate, dict):raise ExtractionError('INVALID_NONMODEL')
    result['nonmodel'] = {k:aggregate[k] for k in ('segments','wall_ms') if numeric(aggregate.get(k))}
    for key, limit in (('own_lines',40),('functions',40),('leaf',25),('categories',16)):
        result['nonmodel'][key] = frame_rows(aggregate.get(key, []), limit)
    stacks = value.get('stacks', [])
    if not isinstance(stacks, list) or len(stacks) > 80:raise ExtractionError('STACK_LIMIT')
    result['stacks'] = []
    for row in stacks:
        if not isinstance(row, dict) or not isinstance(row.get('frames'), list) or len(row['frames']) > 20:
            raise ExtractionError('INVALID_STACK')
        if SEGMENT.fullmatch(str(row.get('segment'))) and numeric(row.get('ms')) and numeric(row.get('samples')):
            result['stacks'].append({'segment':row['segment'], 'ms':row['ms'], 'samples':row['samples'],
                'frames':[f for f in row['frames'] if isinstance(f, str) and FRAME.fullmatch(f)]})
    files = value.get('own_files', [])
    if not isinstance(files, list) or len(files) > 200:raise ExtractionError('OWN_FILE_LIMIT')
    result['own_files'] = [{'file':r['file'], 'sha256':r['sha256'] if isinstance(r.get('sha256'), str) and HEX.fullmatch(r['sha256']) else None}
        for r in files if isinstance(r, dict) and isinstance(r.get('file'), str) and FILE.fullmatch(r['file']) and '..' not in r['file'].split('/')]
    return result


def project(row, index):
    out = _original_project(row, index)
    if row.get('event') == 'timing.probe.summary':
        out['profile'] = safe_profile(row.get('profile'))
    elif row.get('event') == 'timing.probe.started':
        coverage = row.get('coverage', {})
        if not isinstance(coverage, dict):raise ExtractionError('INVALID_PROFILE_COVERAGE')
        out['coverage'] = {key:[v for v in coverage.get(key,[])[:256] if token(v)] for key in ('installed','missing')}
        bounds = coverage.get('boundaries', {})
        if isinstance(bounds, dict):
            out['coverage']['boundaries'] = {key:[v for v in bounds.get(key,[])[:16] if token(v)] for key in ('installed','missing')}
        out['coverage']['loaded_code_fingerprints'] = [{'function':r['function'],'sha256':r['sha256']}
            for r in coverage.get('loaded_code_fingerprints',[])[:256] if isinstance(r,dict) and token(r.get('function'))
            and isinstance(r.get('sha256'),str) and HEX.fullmatch(r['sha256'])]
        for key in ('mode',):
            if token(row.get(key)):out[key] = row[key]
        if numeric(row.get('interval_ms')):out['interval_ms'] = row['interval_ms']
    if str(row.get('event','')).startswith('fulltext.'):
        for key, value in row.items():
            if token(key) and (key.endswith(('_ms','_count','_bytes','_delta')) or key in ('active_searches_at_start','active_peak')) and numeric(value):out[key] = value
        for key in ('sql_status','search_id','diagnostic_revision'):
            if token(row.get(key)):out[key] = row[key]
    return out


def analyze(meta, rows):
    result = _original_analyze(meta, rows)
    result['function_profiles'] = [r for r in rows if r['event'].startswith('timing.probe.')]
    result['fulltext_details'] = [r for r in rows if r['event'].startswith('fulltext.')]
    return result


def code_line(frame, hashes):
    """Show a code line only when the code root file matches the recorded file hash."""
    if _CODE_ROOT is None:return None
    try:
        name, _, rest = frame.partition(':')
        line = int(rest.rsplit(':', 1)[1])
        expected = hashes.get(name)
        path = (_CODE_ROOT/name).resolve()
        path.relative_to(_CODE_ROOT.resolve())
        if expected is None or path.stat().st_size > 8*1024*1024:return '  └ 코드 줄 생략: 기록된 파일 해시 없음/크기 초과'
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:return '  └ 코드 줄 생략: --code-root 파일 해시가 서빙 코드와 다름'
        lines = raw.decode('utf-8', 'replace').splitlines()
        if not 1 <= line <= len(lines):return None
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', lines[line-1].strip())
        return '  └ 코드: '+text[:160]
    except (ValueError, IndexError, OSError):
        return None


def pct(part, whole):
    return f'{part/whole*100:4.1f}%' if numeric(part) and numeric(whole) and whole > 0 else '  -  '


def wait_estimate(seg):
    if not (seg.get('same_thread') and numeric(seg.get('thread_cpu_ms'))):return None
    return max(0.0, seg['wall_ms']-seg['thread_cpu_ms']-seg.get('runqueue_wait_ms', 0))


def segment_name(seg):
    label = seg['segment']
    if label == 'PRE':return 'PRE 요청 수신→RAG 시작'
    if label == 'POST':return 'POST RAG 종료→응답 반환'
    if label.startswith('M'):return f"{label} 모델 호출{label[1:]} [{seg.get('stage','단계 미기록')}]"
    number = int(label[1:])
    before = '시작' if number == 0 else f'호출{number}'
    after = f"호출{number+1} [{seg['next_stage']}]" if seg.get('next_stage') else 'RAG 종료'
    return f'{label} {before}→{after}'


def r2_summary(p, start_event, summary_ms):
    lines = ['\n함수·구간 시간 진단 R2 (요청 처리 스레드 샘플링 + 모델 호출 경계 + 함수 계측)']
    sampling = p.get('sampling', {})
    lines.append(f"모드={p.get('mode','미기록')} / 샘플 간격 {p.get('interval_ms','미기록')}ms / 샘플 틱 {sampling.get('ticks','미기록')}"
                 f" / 지연 틱 {sampling.get('late_ticks','미기록')} / 샘플러 CPU {sec(sampling.get('sampler_cpu_ms'))}"
                 f" / 요약 생성 {sec(summary_ms)} / 동시 요청 최대 {p.get('concurrency_peak','미기록')}")
    if start_event:
        coverage = start_event.get('coverage', {})
        bounds = coverage.get('boundaries', {})
        lines.append(f"모델 경계 연결 {len(bounds.get('installed',[]))}개(미연결 {', '.join(bounds.get('missing',[])) or '없음'})"
                     f" / 함수 계측 {len(coverage.get('installed',[]))}개(미연결 {len(coverage.get('missing',[]))}개)")
    lines.append('경고: '+(', '.join(p.get('warnings',[])) or '없음'))
    segments = p.get('segments', [])
    total = p.get('request_scope_ms')
    model = sum(s['wall_ms'] for s in segments if s['segment'].startswith('M') and numeric(s.get('wall_ms')))
    lines.append(f"계측 범위 {sec(total)} / 모델 구간 합 {sec(model)} / 모델 밖 구간 합 {sec(p.get('nonmodel',{}).get('wall_ms'))}")
    lines.append('\n[구간 개요] 경과 | 스레드CPU | CPU대기 | 그 외 대기(추정) | GC | 원문조회 | 변경검사')
    for seg in segments:
        wait = wait_estimate(seg)
        lines.append(f"  {segment_name(seg)}: {sec(seg.get('wall_ms'))} | {sec(seg.get('thread_cpu_ms'))} | {sec(seg.get('runqueue_wait_ms'))}"
                     f" | {sec(wait)} | {sec(seg.get('gc_ms'))} | {seg.get('source_calls','-')}회 | {seg.get('check_calls','-')}회")
    hashes = {r['file']:r['sha256'] for r in p.get('own_files', [])}
    nonmodel = sorted((s for s in segments if not s['segment'].startswith('M')), key=lambda s:s.get('wall_ms',0), reverse=True)
    lines.append('\n[모델 밖 구간 상세 — 긴 순서, 최대 10개]')
    for seg in nonmodel[:10]:
        wall = seg.get('wall_ms')
        lines.append(f"\n{segment_name(seg)}: {sec(wall)}")
        wait = wait_estimate(seg)
        if wait is not None:
            lines.append(f"  스레드 CPU {sec(seg.get('thread_cpu_ms'))} ({pct(seg.get('thread_cpu_ms'), wall)}) / CPU 대기 {sec(seg.get('runqueue_wait_ms'))}"
                         f" / 그 외 대기 추정 {sec(wait)} ({pct(wait, wall)}; I/O·잠금·sleep·네트워크 등)")
        else:
            lines.append('  스레드 CPU/대기: 시작·종료 경계가 다른 스레드라 분해 불가 (프로세스 CPU '+sec(seg.get('process_cpu_ms'))+')')
        lines.append(f"  GC {sec(seg.get('gc_ms'))} / {seg.get('gc_count',0)}회 (2세대 {seg.get('gc_gen2',0)}회)"
                     f" / 읽기 시스템콜 {seg.get('thread_read_calls','-')}회 · 읽은 문자 {seg.get('thread_read_chars','-')} · 저장장치 읽기 {seg.get('thread_storage_read_bytes','-')}바이트"
                     f" / 자발적 전환 {seg.get('thread_voluntary_switches','-')} · 비자발적 {seg.get('thread_involuntary_switches','-')}"
                     f" / cgroup 제한 {sec(seg.get('cgroup_throttled_ms'))}")
        lines.append(f"  원문 조회(Store.source) {seg.get('source_calls',0)}회 / 데이터 변경 검사(check_unchanged) {seg.get('check_calls',0)}회 / 계측 함수 진입 {seg.get('hook_calls',0)}회")
        lines.append(f"  샘플 {seg.get('samples',0)}개 = {sec(seg.get('sampled_ms'))} (지연 틱 몫 {sec(seg.get('late_ms'))})")
        if seg.get('categories'):
            lines.append('  맨 안쪽 프레임 분류: '+' / '.join(f"{r['frame']} {pct(r['ms'], seg.get('sampled_ms'))}" for r in seg['categories'][:6]))
        if seg.get('top_own_lines'):
            lines.append('  맨 안쪽 우리 코드 줄 (샘플 시간 순):')
            for r in seg['top_own_lines']:
                lines.append(f"    {pct(r['ms'], seg.get('sampled_ms'))} {sec(r['ms'])} {r['frame']}")
                text = code_line(r['frame'], hashes)
                if text:lines.append('    '+text)
        if seg.get('top_functions'):
            lines.append('  스택에 있던 우리 함수 (포함 시간, 합산 금지):')
            for r in seg['top_functions'][:8]:
                lines.append(f"    {pct(r['ms'], seg.get('sampled_ms'))} {sec(r['ms'])} {r['frame']}")
        if seg.get('top_leaf'):
            lines.append('  맨 안쪽 프레임 (라이브러리 포함):')
            for r in seg['top_leaf'][:5]:
                lines.append(f"    {pct(r['ms'], seg.get('sampled_ms'))} {sec(r['ms'])} {r['frame']}")
        if seg.get('hooked_functions'):
            lines.append('  계측 함수 자체 시간 상위:')
            for r in seg['hooked_functions'][:6]:
                lines.append(f"    {r.get('function')} | {r.get('calls')}회 포함={sec(r.get('wall_ms'))} 자체={sec(r.get('self_ms'))}")
        stacks = [s for s in p.get('stacks', []) if s['segment'] == seg['segment']][:3]
        for s in stacks:
            lines.append(f"  호출 경로 {sec(s['ms'])}: "+' > '.join(f.split(':',1)[-1] if not f.startswith(('std:','pkg:','ext:')) else f for f in s['frames']))
    models = [s for s in segments if s['segment'].startswith('M')]
    if models:
        lines.append('\n[모델 구간 확인] 모델 호출 중 실행 스레드의 맨 안쪽 프레임 (응답 대기 여부 확인용)')
        for seg in sorted(models, key=lambda s:s.get('wall_ms',0), reverse=True)[:6]:
            leaf = ', '.join(f"{r['frame']} {pct(r['ms'], seg.get('sampled_ms'))}" for r in seg.get('top_leaf', [])[:2]) or '샘플 없음'
            lines.append(f"  {segment_name(seg)} {sec(seg.get('wall_ms'))}: {leaf}")
    aggregate = p.get('nonmodel', {})
    if aggregate.get('own_lines'):
        lines.append('\n[모델 밖 전체 합계 — 맨 안쪽 우리 코드 줄 상위 20]')
        for r in aggregate['own_lines'][:20]:
            lines.append(f"  {sec(r['ms'])} {r['frame']}")
            text = code_line(r['frame'], hashes)
            if text:lines.append('  '+text)
        lines.append('[모델 밖 전체 합계 — 분류] '+' / '.join(f"{r['frame']} {sec(r['ms'])}" for r in aggregate.get('categories', [])))
    lines += ['\n해석 기준',
        '- 샘플은 간격마다 실행 스레드의 스택을 읽은 추정치입니다. 짧은 구간·짧은 함수는 오차가 큽니다.',
        '- CPU 대기는 실행 가능한데 CPU를 기다린 시간(경합·제한), 그 외 대기는 경과-CPU-CPU대기 추정치입니다.',
        '  그 외 대기에는 디스크/NFS·잠금·sleep·네트워크·자식 스레드 대기가 섞이며 특정 저장소 시간으로 단정하지 않습니다.',
        '- 분류는 맨 안쪽 프레임의 모듈 이름 기준 읽기 보조이며 원인 판정이 아닙니다. C 함수(SQLite·해시 등)는 호출한 우리 코드 줄로 잡힙니다.',
        '- GC·프로세스 I/O·cgroup 값은 프로세스 단위입니다. 동시 요청 경고가 있으면 다른 요청과 섞였을 수 있습니다.',
        '- 샘플러·함수 계측 부하가 요청 시간에 포함됩니다. GENOS_FUNCTION_TIMING_MODE=sample로 함수 계측 없이 재측정할 수 있습니다.',
        '- 모델 서버의 큐/입력 처리/생성 분리는 모델 서버 자체 계측이 필요합니다.']
    return lines


def summary(data):
    lines = [_original_summary(data)]
    profiles = [r for r in data['function_profiles'] if 'profile' in r]
    starts = [r for r in data['function_profiles'] if r['event'] == 'timing.probe.started']
    if not profiles:
        lines += ['\n함수·구간 계측 미기록: 기존 이벤트만으로 함수별 시간/구간 분해는 복원할 수 없습니다.',
                  '패치 적용·GENOS_FUNCTION_TIMING=1·새 요청의 timing.probe.summary 기록을 확인하세요.']
        if starts:lines.append('시작 이벤트만 있음: 중단/저장 누락 가능. 계측 완료로 보지 않습니다.')
    for row in profiles:
        p = row['profile']
        if p['schema_version'] == 'genos-function-timing-v2':
            lines += r2_summary(p, starts[0] if starts else None, row.get('summary_ms'))
        lines += ['\n함수 계측 집계',
            f"완료 호출 {p.get('completed_calls')} / 건너뜀 {p.get('skipped_calls')} / 계측 스레드 {p.get('thread_count')}",
            f"원문 source 호출 {p.get('source_calls')} / 고유 블록키 {p.get('source_unique_blocks')} / 같은 키 재호출 {p.get('source_repeated_blocks')}",
            '주의: source 호출은 Python 조회 호출 수이며 물리 SQL/디스크 I/O 수와 다릅니다. 재호출이 모두 제거 가능한 중복이라는 뜻도 아닙니다.',
            '자체 시간 상위 25개. 자체=계측 자식 시간을 뺀 나머지, 미계측 하위 작업은 포함.']
        for f in sorted(p['functions'], key=lambda r:r.get('self_ms',0), reverse=True)[:25]:
            lines.append(f"{f.get('function')} | 횟수={f.get('calls')} 오류={f.get('errors')} 포함={sec(f.get('wall_ms'))} 자체={sec(f.get('self_ms'))} 자체CPU={sec(f.get('self_cpu_ms'))} 최대={sec(f.get('max_ms'))}")
        lines.append('호출 관계 상위 15개 (포함 시간 순, 중첩되어 합산 금지)')
        for f in sorted(p['edges'], key=lambda r:r.get('wall_ms',0), reverse=True)[:15]:
            lines.append(f"{f.get('parent')} -> {f.get('function')} | {f.get('calls')}회 포함={sec(f.get('wall_ms'))} 자체={sec(f.get('self_ms'))}")
    lines.append('\n기존 fulltext 로그 상세 (최대 20건; 전체는 DIAGNOSTICS.json/TIMELINE.txt)')
    ft = [r for r in data['fulltext_details'] if any(k.endswith('_ms') for k in r)]
    if not ft:lines.append('fulltext 세부 시간 미기록. 캐시/다른 검색 구현/미계측 가능; 0초나 미실행으로 해석하지 않습니다.')
    for row in ft[:20]:lines.append(json.dumps(row, ensure_ascii=False))
    return '\n'.join(lines)+'\n'


def main(argv=None):
    global _CODE_ROOT
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--code-root' in argv:
        index = argv.index('--code-root')
        if index+1 >= len(argv):
            print('EXTRACTION_FAILED: CODE_ROOT_REQUIRED', file=sys.stderr)
            return 1
        _CODE_ROOT = Path(argv[index+1]).expanduser()
        del argv[index:index+2]
        if not _CODE_ROOT.is_dir():
            print('EXTRACTION_FAILED: CODE_ROOT_NOT_DIRECTORY', file=sys.stderr)
            return 1
    return _original_main(argv)

if __name__ == '__main__':
    sys.exit(main())
