"""Paste ALL into a GENOS workflow Python test step; entry is run(data)."""
import json
import os
import re
import urllib.error
import urllib.request
import uuid

REVISION = 'nfs-data-probe-20261006-r1'
EXPECTED_PROBE_ID = '__PREPARED_PROBE_ID__'
EXPECTED_COMMIT = '__PREPARED_COMMIT__'


def unwrap(value):
    for _ in range(8):
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError('gateway response must be an object')
        if value.get('response_schema') == REVISION:
            return value
        value = next((value[k] for k in ('body', 'data', 'result') if isinstance(value.get(k), (dict, str))), None)
    raise ValueError('diagnostic response schema absent')


def run(data):
    request_id = uuid.uuid4().hex
    base = os.environ.get('GENOS_BASE_URL', '').strip().rstrip('/')
    serving_id = os.environ.get('GENOS_CODESERVING_ID', '').strip()
    token = (os.environ.get('GENOS_CODESERVING_TOKEN') or os.environ.get('GENOS_CODE_KEY') or '').strip()
    if not base.startswith(('http://', 'https://')) or not re.fullmatch(r'[A-Za-z0-9_.:-]+', serving_id) or not token:
        return {'text': 'NFS 검사 FAIL: 기존 GENOS_BASE_URL / GENOS_CODESERVING_ID / 코드서빙 인증키 설정을 확인하세요.', 'nfs_probe_pass': False}
    if EXPECTED_PROBE_ID.startswith('__') or EXPECTED_COMMIT.startswith('__'):
        return {'text': 'NFS 검사 FAIL: prepare가 생성한 WORKFLOW_PASTE_ALL.txt 전체를 사용하세요.', 'nfs_probe_pass': False}
    endpoint = base + '/api/gateway/code_serving/' + serving_id + '/json'
    request = urllib.request.Request(endpoint, method='POST',
        data=json.dumps({'API_TYPE': 'NFS_DATA_PROBE', 'request_id': request_id, 'include_listing': True,
                         'offset': data.get('offset', 0) if isinstance(data, dict) else 0,
                         'limit': data.get('limit', 100) if isinstance(data, dict) else 100}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    # Never follow redirects carrying the code-serving credential to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    http_status = None
    try:
        try:
            response = opener.open(request, timeout=120)
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 503):
                return {'text': 'NFS 검사 FAIL: HTTP ' + str(exc.code) + '. 코드서빙 대상·커밋·인증 설정을 확인하세요.',
                        'nfs_probe_pass': False, 'request_id': request_id}
            response = exc
        with response:
            http_status = response.code
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('diagnostic response too large')
        report = unwrap(json.loads(raw.decode('utf-8')))
        identity = report.get('probe_id') == EXPECTED_PROBE_ID and report.get('expected_commit') == EXPECTED_COMMIT
        passed = (http_status == 200 and report.get('ok') is True and identity
                  and report.get('stage') == 'code-serving' and isinstance(report.get('data_listing'), dict))
        lines = ['NFS 데이터 읽기 검사 ' + ('PASS' if passed else 'FAIL'),
                 '준비 커밋: ' + EXPECTED_COMMIT,
                 '코드서빙 응답 커밋: ' + str(report.get('expected_commit')),
                 '세대: ' + str(report.get('generation')),
                 'runtime: ' + str(report.get('runtime'))]
        if not identity:
            lines.append('FAIL: 배포한 커밋 또는 검사 식별자가 준비한 값과 다릅니다.')
        for row in report.get('checks', []):
            lines.append(str(row.get('status')) + ' | ' + str(row.get('name')) + ' | ' + str(row.get('path', ''))
                         + (' | ' + str(row['error_type']) if row.get('error_type') else '')
                         + (' | ' + str(row['reason']) if row.get('reason') else ''))
        listing = report.get('data_listing') or {}
        for key, label in (('generation_directory', 'generation 파일/폴더'), ('runtime_directory', 'runtime 파일/폴더')):
            section = listing.get(key) or {}
            lines.append(label + ': ' + str(section.get('path', '')))
            for item in section.get('entries', []):
                lines.append('  ' + str(item.get('kind')) + ' | ' + str(item.get('name'))
                             + (' | ' + str(item['bytes']) + ' bytes' if item.get('bytes') is not None else ''))
            if section.get('truncated'):
                lines.append('  상한에 도달하여 파일/폴더 목록 일부만 표시했습니다.')
        documents = listing.get('document_metadata') or {}
        if documents.get('listed'):
            lines.append('문서 목록: ' + str(documents.get('team_id')) + ' | 총 ' + str(documents.get('total')) + '건')
            for row in documents.get('documents', []):
                lines.append('  ' + str(row.get('document_id')) + ' | ' + str(row.get('name')))
            if documents.get('has_more'):
                lines.append('  다음 페이지 offset=' + str(documents['offset'] + len(documents.get('documents', []))))
        else:
            lines.append('문서명 목록은 준비 시 --team-id risk_team처럼 실제 팀을 지정하면 표시됩니다.')
        lines.append('검증 범위: 파일 읽기·SQL 조회·커밋 코드 대조. 전체 RAG/모델·쓰기 성공은 별도입니다.')
        return {'text': '\n'.join(lines), 'nfs_probe_pass': passed, 'request_id': request_id,
                'nfs_probe_report': report}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # No raw HTTP body, exception text, token or original user input in output.
        return {'text': 'NFS 검사 FAIL: ' + type(exc).__name__ + '. 워크플로우·코드서빙 로그를 확인하세요.',
                'nfs_probe_pass': False, 'request_id': request_id, 'http_status': http_status}
