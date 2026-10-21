import base64
import hashlib
import html
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
CELL = 'DATAIKU_NETWORK_EVIDENCE_20261015_R1_CELL.txt'
ARCHIVE = 'DATAIKU_NETWORK_EVIDENCE_20261015_R1.zip'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
validation = json.loads((HERE / 'VALIDATION.json').read_text())
assert validation['status'] == 'PASS' and validation['tests'] == 13
assert validation['delivered_cell_sha256'] == sha((HERE / CELL).read_bytes())
parent = HERE.parent / 'law_api_20261015_r1' / 'relay_check.py'
binding = {'version': 'dataiku-network-evidence-20261015-r1', 'cell_sha256': sha((HERE / CELL).read_bytes()),
           'parent_relay_helper_sha256': sha(parent.read_bytes()), 'parent_modified': False,
           'test_file_sha256': sha((HERE / 'test_evidence.py').read_bytes()),
           'destination_scope': 'Provided development relay 45.101.64.86:8443 only',
           'samsung_internal_calls_by_author': 0, 'field_result': 'AWAITING_USER_EXECUTION',
           'firewall_block_confirmed': False}
(HERE / 'SOURCE_BINDING.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
members = [CELL, 'GUIDE_UTF8.txt', 'VALIDATION.json', 'FIELD_OBSERVATION.json', 'SOURCE_BINDING.json', 'TEST_TRANSCRIPT.txt']
(HERE / 'SHA256SUMS.txt').write_text(''.join(sha((HERE / name).read_bytes()) + '  ' + name + '\n' for name in members))
members.append('SHA256SUMS.txt')
assert all(Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for name in members)
with zipfile.ZipFile(HERE / ARCHIVE, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in members:
        z.write(HERE / name, arcname='DATAIKU_NETWORK_EVIDENCE_20261015_R1/' + name)
with zipfile.ZipFile(HERE / ARCHIVE) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(members)
    for name in members:
        assert z.read('DATAIKU_NETWORK_EVIDENCE_20261015_R1/' + name) == (HERE / name).read_bytes()

body = '''기존 요청을 사진과 대조한 결과, 같은 중계 IP·포트를 사용했지만 사진 1의 curl과 완전히 같지는 않았습니다.
사진은 /law/making 행정예고 조회이고 기존 R1/추가 진단은 /law/DRF 법령 본문 조회였습니다. 이 차이를 정정합니다.

현재 현장 화면의 핵심 증거는 ConnectTimeout, 8.01초, HTTP 응답 없음, 명시적 프록시 없음입니다.
방화벽 차단 확정에는 해당 시각/출발지/NAT/목적지와 일치하는 DENY/DROP 로그 및 정책 ID가 필요합니다.
awaiting_response_headers는 코드 단계명이며 서버가 요청을 수신했다는 증거가 아닙니다.

이번 첨부는 증거 수집용 추가 셀입니다. 기존 R1 Notebook의 같은 커널에서 맨 아래 새 Code 셀을 만들고 CELL.txt 전체를 붙여 넣어 Shift+Enter 하세요. Kernel Restart/Run All은 누르지 마세요.
ZIP에도 같은 실행 TXT와 가이드가 들어 있으며, 실행 TXT는 별도 첨부했습니다. 이 TXT는 Python 셀용이며 bash 파일이 아닙니다.

TCP 연결 1회(8초)와 사진의 /law/making 경로·조회 조건·target_url을 쓰는 실제 curl 1회(최대 20초)를 수행합니다. 시각, 로컬 IP/port, 목적지, curl TCP/TLS 시간과 종료코드를 JSON으로 남깁니다. 기존 결과/차단 상태는 유지하고 재실행하면 저장 결과만 표시합니다.

사진과 남는 차이도 기록합니다: 현재 허가받은 OC/Cookie 사용, 한글 URL 인코딩, 최초 요청 뒤 리다이렉트 중단, 시간 한도, 기존 세션의 프록시·CA 설정. Cookie가 없으면 입력창에서 Enter로 건너뛸 수 있으나 인증 헤더까지 동일한 재현은 아닙니다. 사진 속 타인 세션값은 사용하지 마세요.

완료 후 기존 8번 Managed Folder 저장 셀만 다시 실행하면 network_evidence_r1.json이 기존 run 폴더에 추가됩니다. 이 JSON과 가이드 7번 요청문을 네트워크 담당자에게 전달하면 됩니다. 가이드에는 로그 대조 필드, 결과별 해석, 관리자용 제한 패킷 캡처 명령도 포함했습니다.

로컬 HTTPS와 모의 오류 검증 13개를 통과했습니다. 실제 curl의 경로·쿼리·헤더와 기존 Managed Folder 저장 연결을 확인했습니다. 이 개발 환경에서 삼성 내부 주소로 접속한 횟수는 0이며, 현장 방화벽 차단 여부는 여전히 미확정입니다.'''
(HERE / 'EMAIL_BODY_UTF8.txt').write_text(body + '\n')
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': '<div>' + ''.join('<p>' + html.escape(p).replace('\n', '<br>') + '</p>' for p in body.split('\n\n')) + '</div>'}}]
attachments = []
for name in [ARCHIVE, CELL, 'GUIDE_UTF8.txt', 'VALIDATION.json']:
    raw = (HERE / name).read_bytes()
    mime = 'application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/plain'
    parts.append({'mime_type': mime, 'filename': name, 'content_disposition': 'attachment',
                  'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode().rstrip('=')}})
    attachments.append({'name': name, 'bytes': len(raw), 'mime_type': mime, 'sha256': sha(raw)})
args = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[Dataiku 방화벽 증거] 사진 샘플 curl 대조·TCP 진단 셀',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts}, 'response_fields': ['id', 'thread_id', 'label_ids']}
(HERE / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=False))
(HERE / 'EMAIL_BINDING.json').write_text(json.dumps({'to': args['to'], 'subject': args['subject'], 'attachments': attachments}, ensure_ascii=False, indent=2))
(HERE / 'SEALED_CHECK.json').write_text(json.dumps({'archive_sha256': sha((HERE / ARCHIVE).read_bytes()),
                                                  'members_verified': members, 'excluded_javascript': True,
                                                  'validation_cell_hash_matched': True}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'zip_bytes': (HERE / ARCHIVE).stat().st_size, 'attachments': attachments}, ensure_ascii=False, indent=2))
