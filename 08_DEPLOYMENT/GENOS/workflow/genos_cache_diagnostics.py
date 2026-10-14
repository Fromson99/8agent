"""Paste ALL into a separate workflow Python TEST step. Entry: run(data).

Uses that test workflow's existing GENOS_BASE_URL / CODESERVING_ID / token.
Makes three readonly requests to the deployed process; does not ask a model.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REVISION = 'genos-cache-diagnostics-20261008-r1'


def unwrap(value):
    for _ in range(8):
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            break
        if value.get('response_schema') == REVISION:
            return value
        if 'state' in value and 'worker_id' in value:
            return value
        value = next((value[key] for key in ('body', 'data', 'result')
                      if isinstance(value.get(key), (dict, str))), None)
    raise ValueError('expected deployed diagnostic response absent')


def call(operation):
    base = os.environ.get('GENOS_BASE_URL', '').strip().rstrip('/')
    serving_id = os.environ.get('GENOS_CODESERVING_ID', '').strip()
    token = (os.environ.get('GENOS_CODESERVING_TOKEN') or os.environ.get('GENOS_CODE_KEY') or '').strip()
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('base URL setting invalid')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', serving_id) or not token:
        raise ValueError('serving identity or credential absent')
    endpoint = base + '/api/gateway/code_serving/' + serving_id + '/json'
    request = urllib.request.Request(endpoint, method='POST',
        data=json.dumps({'API_TYPE': operation, 'request_id': uuid.uuid4().hex}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    started = time.monotonic()
    with opener.open(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('response size limit')
    return unwrap(json.loads(raw.decode('utf-8'))), round((time.monotonic() - started) * 1000, 3)


def run(data):
    rows = []
    lines = ['코드서빙 캐시 검사: 원본·캐시를 변경하지 않는 조회']
    # Inputs cannot choose an endpoint, credential, file path, query, or code.
    for operation in ('WARMUP_STATUS', 'CACHE_DIAGNOSTICS', 'WARMUP_STATUS'):
        try:
            report, elapsed = call(operation)
            rows.append({'operation': operation, 'response_ms': elapsed, 'report': report})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            rows.append({'operation': operation, 'error_type': type(exc).__name__, 'http_status': status})
    states = [row['report'] for row in rows if row.get('report', {}).get('state')]
    reports = [row['report'] for row in rows if row.get('report', {}).get('response_schema') == REVISION]
    workers = [value['worker_id'] for value in states]
    workers += [report['worker']['worker_id'] for report in reports]
    lines.append('호출별 worker_id: ' + ', '.join(workers))
    lines.append('이번 호출에서 관측한 서로 다른 프로세스 수: ' + str(len(set(workers))))
    if len(set(workers)) > 1:
        lines.append('다른 워커/리비전으로 라우팅되거나 프로세스가 재시작됐습니다. 같은 프로세스끼리 비교하세요.')
    if not reports:
        lines.append('상세 캐시 상태 미확인: 진단 훅 배포 또는 코드서빙 로그를 확인하세요.')
    for report in reports:
        lines.append('실제 선택 generation: ' + str(report['selection']['generation_path']))
        for pool in report['resident_pools']:
            lines.append('전체 데이터 캐시: mode=' + str(pool.get('effective_mode')) +
                         ', 보관 파일=' + str(pool.get('entry_count')) +
                         ', RAM 예약 bytes=' + str(pool.get('memory_reserved_bytes')) +
                         ', 로컬 bytes=' + str(pool.get('local_bytes')))
        for cache in report['result_caches']:
            lines.append('검색 결과 캐시: 항목=' + str(cache.get('entry_count')) +
                         ', bytes=' + str(cache.get('bytes')) + ', 축출=' + str(cache.get('evictions')))
            for match in cache.get('recent_matches', []):
                if match['overflow_marker']:
                    lines.append('전체 SQL 재계산 조건 발견: 적중이 ' + str(match['row_limit']) + '개를 넘는 캐시 항목이 있습니다.')
    lines.append('READY는 준비 성공입니다. SQL 적중률/정확한 FULLTEXT 소요 시간은 이 스냅샷만으로 확정하지 않습니다.')
    # Deliberately no raw gateway error bodies, exception messages, or input data.
    return {'text': '\n'.join(lines), 'cache_diagnostics_schema': REVISION,
            'cache_diagnostics': rows, 'observed_worker_ids': sorted(set(workers)),
            'live_cache_observed': bool(reports)}
