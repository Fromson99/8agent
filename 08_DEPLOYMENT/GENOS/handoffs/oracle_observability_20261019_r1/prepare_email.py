"""Prepare the user-authorized Samsung handoff from sealed patch bytes."""
import base64
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

H = Path(__file__).resolve().parent
NAME = 'GENOS_ORACLE_LOGGING_20261019_R1'
NAMES = [NAME + '.zip', NAME + '_RUN.txt', 'GUIDE_UTF8.txt',
         'VALIDATION.json', 'SHA256SUMS.txt']
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert not (H / 'EMAIL_SENT.json').exists(), 'Inspect existing send receipt before repeating'
assert not (H / 'EMAIL_SEND_RESULT.json').exists(), 'Resolve prior send outcome before repeating'
sealed = json.loads((H / 'SEALED.json').read_bytes())
for name, digest in sealed['files'].items():
    assert sha((H / name).read_bytes()) == digest, name
assert json.loads((H / 'VALIDATION.json').read_bytes())['status'] == 'PASS'
scanned = []

def scan_archive(raw, label):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        scanned.append({'archive': label, 'members': len(archive.namelist())})
        for name in archive.namelist():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}, name
            if name.lower().endswith('.zip'):
                scan_archive(archive.read(name), label + '/' + name)

scan_archive((H / NAMES[0]).read_bytes(), NAMES[0])
with zipfile.ZipFile(H / NAMES[0]) as archive:
    for name in [NAMES[1], 'GUIDE_UTF8.txt']:
        assert archive.read(name) == (H / name).read_bytes(), name
embedded = re.findall(r"raw=base64.b64decode\('([A-Za-z0-9+/=]+)'\)", (H / NAMES[1]).read_text())
assert len(embedded) == 1
scan_archive(base64.b64decode(embedded[0], validate=True), 'RUN embedded package')
subprocess.run(['bash', '-n', str(H / NAMES[1])], check=True)
for line in (H / 'SHA256SUMS.txt').read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    assert sha((H / name.lstrip('*')).read_bytes()) == digest

body = f'''<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>Oracle 준비 진행·워크플로우 진입 로깅 패치 R1</strong>을 보내드립니다.</p>
<p>이번 <strong>{NAME}</strong>은 기존 <code>GENOS_MAIN87_PATCH_20261019_R1</code> 또는 <code>GENOS_SESSION_IDENTITY_20261019_R1</code> 적용본 위에 추가하는 작은 패치입니다. 설치기가 기존 버전을 해시로 판별해 그 버전에 맞게 적용합니다. 알 수 없는 코드 변경은 덮어쓰지 않습니다.</p>
<p>준비 단계·처리 행/분할 수·Oracle 응답 대기·마지막 진행 시각을 표시하고, 준비 중에는 기본 INFO 컨테이너 로그에 15초마다 heartbeat를 남깁니다. <code>WARMUP_STATUS</code>는 AD 저장소 초기화와 분리했습니다. 워크플로우 Python 진입 및 코드서빙 호출 지점을 확인할 수 있습니다. heartbeat만 찍히는 것으로 실제 데이터 진행을 판단하지 않고 카운터와 마지막 진행 시각을 함께 확인하세요.</p>
<p><strong>실제 첨부를 업로드한 TRANSFER 폴더에서 아래 순서로 실행하세요.</strong></p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt status</pre>
<p>적용 대상은 기존 <code>~/DEV</code>입니다. 실제 checkout 위치가 다를 때만 <code>--root /실제/checkout</code>을 붙입니다. 로그는 <code>./oracle-logging-r1-logs</code>에 남습니다. 중단 시 같은 apply로 재개하고 undo로 원복합니다. 전체 순서와 백업 위치는 <strong>GUIDE_UTF8.txt</strong>에 있습니다.</p>
<p>적용 후 GUIDE 순서대로 DEV 변경 확인·commit → <code>gate-code</code> → 기존 원격에 push → 같은 commit의 새 코드서빙 리비전 배포를 진행하세요. 기존 Oracle 인증·DP_RELEASE_ID·캐시·내부 모델 설정은 유지합니다. 코드 gate는 현장 Oracle 데이터 검증을 대신하지 않습니다.</p>
<p><strong>워크플로우 Python 편집기도 별도로 저장해야 합니다.</strong> apply가 현재 설치본에 맞춰 생성하는 <code>./oracle-logging-r1-state/WORKFLOW_PASTE_ALL.txt</code> 전체를 기존 Python 단계에 반영하세요. 기존 URL·코드서빙 ID·인증·팀/세션 설정은 유지합니다. Git push만으로 편집기 코드가 바뀌지는 않습니다.</p>
<p>현장 확인은 <strong>워크플로우 테스트 화면</strong>에서 <code>{{"question":"WARMUP_STATUS"}}</code>로 시작합니다. NOT_STARTED/FAILED이면 원인을 확인하고 WARMUP을 한 번 시작합니다. RUNNING이면 상태와 카운터를 확인하고, READY에서 oracle 공급자·release_id 일치·nfs_source_used=false를 확인한 후 SSE_CHECK와 근거를 아는 질문 한 건을 테스트하세요.</p>
<p><strong>사진의 “시스템 내 MODEL 오류로 가드레일 기능이 정상 동작하지 않습니다”는 별도 플랫폼 오류입니다.</strong> 이 패치가 그 모델 오류를 해결한 것은 아닙니다. 입력/출력 어느 단계인지 현장 실행 기록이 필요합니다. <code>workflow.entry.received</code>가 없는지, 이어서 <code>code_serving.request.started</code>와 서버의 <code>http.request.started</code>·<code>service.entered</code>가 찍히는지 대조하면 요청이 도달한 지점을 구분할 수 있습니다.</p>
<p>로컬 검증: 관련 합성 계약 38개, 두 기존 버전 설치·재개·중복 적용·같은 committed checkout의 gate·정확한 원복 32명령, Python 3.11.15 구문 13파일을 확인했습니다. 최초 tmpfs 테스트 실패와 재검사 결과도 보존했습니다. 실제 현장 Oracle·가드레일 모델·리비전·편집기 저장·답변 성공은 아직 미확인입니다. 로컬 MAIN 포인터는 변경하지 않았습니다.</p>
<p>첨부 5개: 패치 ZIP, 완전한 실행 TXT, 적용/복구 안내, 검증 결과, SHA-256 목록. 실행 TXT와 안내는 ZIP 안에도 들어 있습니다.</p>
<p>ZIP SHA-256: <code>{sealed['files'][NAMES[0]]}</code></p>
</body></html>'''
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
rows = []
for name in NAMES:
    raw = (H / name).read_bytes()
    mime = {'.zip': 'application/zip', '.json': 'application/json'}.get(Path(name).suffix, 'text/plain')
    parts.append({'mime_type': mime, 'filename': name, 'content_disposition': 'attachment',
                  'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name': name, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
args = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[GENOS] Oracle 준비 진행·워크플로우 진입 로깅 패치 (2026-10-19 R1)',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
(H / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=False))
(H / 'EMAIL_BODY_UTF8.html').write_text(body)
(H / 'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
check = {'to': args['to'], 'subject': args['subject'], 'attachments': rows,
         'args_bytes': (H / 'EMAIL_ARGS.json').stat().st_size,
         'archive_scan': scanned, 'javascript_exclusions': 'PASS', 'bash_syntax': 'PASS',
         'sealed_files': len(sealed['files'])}
(H / 'EMAIL_PRECHECK.json').write_text(json.dumps(check, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(check, ensure_ascii=False))
