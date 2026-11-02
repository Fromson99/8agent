"""Bounded read-only diagnosis of the existing R8/R9/R10 load receipts.

No database calls, source scans, imports of the loader, writes, or sleep.
All output is deliberately compact and contains no raw journal/payload values.
"""
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

JSON_LIMIT = 16 * 1024 * 1024
PROGRESS_LIMIT = 8 * 1024 * 1024
SQL_LIMIT = 2 * 1024 * 1024


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and value >= 0


def read_json(path, limit=JSON_LIMIT):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return {}, 'SIZE_LIMIT'
        obj = json.loads(raw)
        return (obj, '') if isinstance(obj, dict) else ({}, 'FORMAT')
    except (OSError, ValueError) as exc:
        return {}, type(exc).__name__


def tail_jsonl(path, limit):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            raw = stream.read(limit)
        if size > limit:
            raw = raw.partition(b'\n')[2]
        rows = []
        skipped = 0
        for line in raw.splitlines():
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except (ValueError, UnicodeError):
                skipped += 1
        return rows, {'truncated': size > limit, 'skipped': skipped, 'error': ''}
    except OSError as exc:
        return [], {'truncated': False, 'skipped': 0, 'error': type(exc).__name__}


def run_samples(rows):
    """Never calculate throughput across an elapsed counter restart."""
    current = []
    previous = None
    for row in rows:
        elapsed = row.get('elapsed_seconds')
        if not number(elapsed) or elapsed < 0:
            continue
        if previous is not None and elapsed < previous:
            current = []
        previous = elapsed
        current.append(row)
    samples = [r for r in current if integer(r.get('write_rows_this_run'))
               and integer(r.get('write_requests_this_run'))]
    if not samples:
        return current, None
    end = samples[-1]
    recent = [r for r in samples if r['elapsed_seconds'] >= end['elapsed_seconds'] - 600]
    if len(recent) < 2:
        return current, None
    start = recent[0]
    seconds = end['elapsed_seconds'] - start['elapsed_seconds']
    count = end['write_rows_this_run'] - start['write_rows_this_run']
    if seconds < 60 or count < 0:
        return current, None
    return current, {'seconds': seconds, 'rows': count, 'rate': count / seconds,
                     'requests': end['write_requests_this_run'] - start['write_requests_this_run']}


def sql_samples(rows, now):
    starts = {}
    durations = []
    latest = None
    for row in rows:
        call, at = row.get('call'), row.get('at')
        if not integer(call) or not number(at):
            continue
        latest = row
        if row.get('status') == 'STARTED':
            starts[call] = at
        elif row.get('status') in ('ACKNOWLEDGED', 'WRITE_UNCONFIRMED', 'READ_FAILED'):
            began = starts.pop(call, None)
            if began is not None and at >= began and row.get('status') == 'ACKNOWLEDGED':
                durations.append(at - began)
    recent = durations[-20:]
    return {'recent': recent, 'latest': latest, 'pending_age':
            max(0, now - max(starts.values())) if starts else None}


def descriptor_total(descriptor, state):
    if not descriptor:
        return None, {}, '준비 명세 없음'
    body = {k: v for k, v in descriptor.items() if k != 'checksum'}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(encoded).hexdigest() != descriptor.get('checksum'):
        return None, {}, '명세 해시 불일치'
    binding = body.get('binding', {})
    plan = state.get('deferred', {}).get('plan', {})
    if (not plan or binding.get('source') != plan.get('source_release_id')
            or binding.get('files') != plan.get('files')):
        return None, {}, '현재 작업과 명세 결속 미확인'
    tables = body.get('tables')
    if not isinstance(tables, dict) or not tables:
        return None, {}, '명세 행수 없음'
    assets = {}
    for value in tables.values():
        if not isinstance(value, dict) or not integer(value.get('rows')):
            return None, {}, '명세 행수 형식 미확인'
        asset = value.get('asset')
        if isinstance(asset, str):
            assets[asset] = assets.get(asset, 0) + value['rows']
    return sum(v['rows'] for v in tables.values()), assets, ''


def duration(seconds):
    if seconds < 3600:
        return '{:.0f}분'.format(seconds / 60)
    if seconds < 86400:
        return '{:.1f}시간'.format(seconds / 3600)
    return '{:.1f}일({:.0f}시간)'.format(seconds / 86400, seconds / 3600)


def build_report(job, now=None, detail=True):
    now = time.time() if now is None else now
    job = Path(job)
    state, state_error = read_json(job / 'full-state.json')
    if not state:
        return ['[빠른 진단 R1] 읽기 전용 / DB 조회 0 / 파일 변경 0',
                '기존 적재 기록을 읽지 못했습니다: ' + state_error,
                '같은 실행 환경과 LEGAL_PIPELINE_SCRATCH 설정의 별도 노트북에서 실행하세요.',
                '기록이 안 보이는 것만으로 적재 중단이나 0행으로 판단하지 않습니다.']
    progress, pi = tail_jsonl(job / 'progress.jsonl', PROGRESS_LIMIT)
    latest_file, _ = read_json(job / 'progress-latest.json', 65536)
    if latest_file and (not progress or latest_file.get('at', 0) > progress[-1].get('at', 0)):
        progress.append(latest_file)
    current, rate = run_samples(progress)
    latest = current[-1] if current else {}
    descriptor, de = read_json(job / 'projection-descriptor-r7.json')
    total, assets, total_error = descriptor_total(descriptor, state)
    journal, ji = tail_jsonl(job / 'deferred_load.jsonl', SQL_LIMIT)
    sql = sql_samples(journal, now)
    deferred = state.get('deferred', {})
    frames = deferred.get('loaded_query_batches')
    rows = latest.get('write_rows_this_run')
    requests = latest.get('write_requests_this_run')
    at = latest.get('at')
    age = max(0, now - at) if number(at) else None
    status = str(state.get('status', '미기록'))[:48]
    lines = ['[빠른 진단 R1] 읽기 전용 / DB 조회 0 / 파일 변경 0',
             '01 저장 상태: ' + status,
             '02 마지막 진행 기록: ' + ('{:.0f}초 전'.format(age) if age is not None else '미확인')]
    lines.append('03 현재 표시: ' + str(latest.get('phase', '미확인'))[:60])
    lines.append('04 이번 실행: ' + ('{:,}행 / {:,}요청'.format(rows, requests)
                 if integer(rows) and integer(requests) else '행수·요청수 미기록'))
    lines.append('05 전체 검색행: ' + ('{:,}행(저장 명세)'.format(total)
                 if total is not None else '미확인 — ' + total_error))
    lines.append('06 재개 기록: ' + ('{:,}묶음(각 1~20행; 500행 요청수와 다름)'.format(frames)
                 if integer(frames) else '미확인'))
    remaining = None
    if total is not None and integer(frames):
        # Each acknowledged legacy frame contains 1..20 rows. Never call 20*frames exact.
        completed_min, completed_max = frames, frames * 20
        if integer(rows) and latest.get('query_batches_loaded') == frames:
            completed_min = max(completed_min, rows)
        if deferred.get('load_finished'):
            completed_min = completed_max = total
        if completed_min <= total and completed_min <= completed_max:
            remaining = (max(0, total - completed_max), total - completed_min)
    lines.append('07 남은 검색행: ' + ('{:,}~{:,}행(재개 기록의 보수적 범위)'.format(*remaining)
                 if remaining is not None else '정확 계산 불가 — 930만 행 가정 안 함'))
    lines.append('08 최근 속도: ' + ('{:.1f}행/초 ({:.0f}분 동안 {:,}행)'.format(
                 rate['rate'], rate['seconds'] / 60, rate['rows']) if rate else '같은 실행의 60초 이상 표본 부족'))
    if deferred.get('load_finished'):
        estimate = '검색행 적재 완료 기록 있음; 전수검증 상태는 별도'
    elif status in ('FAILED', 'STOPPED', 'PAUSED', 'BUDGET_PAUSED'):
        estimate = '저장 상태가 중단·실패이므로 보류'
    elif age is None or age > 90:
        estimate = '진행 기록이 오래되었거나 없어 보류'
    elif rate and rate['rate'] > 0 and remaining is not None:
        estimate = '{} ~ {}'.format(*(duration(n / rate['rate']) for n in remaining))
    else:
        estimate = '속도 0 또는 표본·전체량 부족으로 보류'
    lines.append('09 추가 적재 예상: ' + estimate)
    ds = sql['recent']
    lines.append('10 최근 요청: ' + ('{}건 / 중앙 {:.1f}초 / 최대 {:.1f}초'.format(
                 len(ds), statistics.median(ds), max(ds)) if ds else '완료 요청 쌍 부족'))
    event = sql['latest']
    lines.append('11 마지막 요청 상태: ' + (str(event.get('status', '미확인'))[:40] if event else '미확인'))
    lines.append('12 해석: 요청 시간에는 Dataiku·전송·DB 대기 등이 포함됨; DB CPU만의 시간이 아님')
    lines.append('13 예상은 현재 속도가 유지될 때의 검색행 적재 시간이며 전수검증은 제외')
    lines.append('14 이 코드는 적재를 중단·재개하지 않음; 출력만 캡처하세요')
    if detail:
        lines.append('[상세 — 최대 8줄]')
        lines.append('A 현재 파일: ' + str(latest.get('asset', '미기록'))[:90])
        elapsed = latest.get('elapsed_seconds')
        lines.append('B 실행 경과: ' + (duration(elapsed) if number(elapsed) else '미기록'))
        if sql['pending_age'] is not None:
            lines.append('C 성공 응답 없는 요청: {:.0f}초 경과(실행 중/중단/응답 유실 구별 불가)'.format(sql['pending_age']))
        else:
            lines.append('C 최근 로그에 미완료 STARTED 요청 없음')
        recent = ds[-5:]
        lines.append('D 최근 완료 요청 5건(초): ' + (', '.join('{:.1f}'.format(n) for n in recent) or '미기록'))
        asset = latest.get('asset')
        lines.append('E 현재 파일 전체 검색행: ' + ('{:,}행'.format(assets[asset]) if asset in assets else '미확인'))
        lines.append('F 읽기 한도: JSON 각16MiB / 진행 꼬리8MiB / 요청 꼬리2MiB')
        lines.append('G 꼬리만 읽음: 진행 {} / 요청 {}; 불완전 줄 제외 {}'.format(
            pi['truncated'], ji['truncated'], pi['skipped'] + ji['skipped']))
        warnings = [v for v in (de, pi['error'], ji['error']) if v]
        lines.append('H 기록 주의: ' + (', '.join(warnings) if warnings else '읽기 오류 없음; 현장 속도 개선 여부는 아직 미검증'))
    return lines


def main(job_dir=None, detail=True):
    if job_dir is None:
        import tempfile
        import dataiku
        base = Path(dataiku.get_custom_variables().get('LEGAL_PIPELINE_SCRATCH') or tempfile.gettempdir())
        job_dir = (base.expanduser() / 'legal-existing-nfs-20261029-r1'
                   / 'financial-risk-success-20261005-schema-r2' / 'oracle-import-r2')
    try:
        lines = build_report(job_dir, detail=detail)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        lines = ['[빠른 진단 R1] 기록 형식 확인 필요: ' + type(exc).__name__,
                 '적재나 파일을 변경하지 않았습니다. 이 두 줄을 캡처하세요.']
    for line in lines:
        print(line)


if __name__ == '__main__':
    main()
