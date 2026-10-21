"""Package and inspect the authorized Samsung handoff without sending it."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = 'GENOS_TERM_RELEASE_STORAGE_20261016_R1'
assert not (ROOT / 'EMAIL_SENT.json').exists(), 'Inspect prior send before repeating'
BANNED = {'.js', '.jsx', '.mjs', '.cjs'}
RUN = VERSION + '.txt'
validation = json.loads((ROOT / 'VALIDATION.json').read_text())
for name, pin in validation['files'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == pin, name
subprocess.run(['bash', '-n', str(ROOT / RUN)], check=True)
source = (ROOT / RUN).read_text().split("<<'STORAGE_PY'\n", 1)[1].rsplit('\nSTORAGE_PY', 1)[0]
ast.parse(source, feature_version=(3, 11))
members = [RUN, 'GUIDE_UTF8.txt', 'VALIDATION.json', 'SHA256SUMS.txt',
           'test_delivery.py', 'TEST_COMMAND_TRANSCRIPT.json',
           'failures/PRIOR_TEST_RESULT.txt', 'failures/prior_full_scan_isolate_failed.log']
archive = ROOT / (VERSION + '.zip')
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
    for name in members:
        assert Path(name).suffix.lower() not in BANNED
        package.write(ROOT / name, name)
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    assert package.namelist() == members
    for name in package.namelist():
        assert Path(name).suffix.lower() not in BANNED
        assert package.read(name) == (ROOT / name).read_bytes()
body = f'''<!doctype html><html><body>
<p>요청하신 <strong>term-releases 정리 전 경량 경로 확인·격리·원복 도구</strong>를 보냅니다.</p>
<p>이 코드는 <strong>financial-risk-success-20261005-schema-r2 폴더 전체를 보존</strong>하고,
나머지 과거 세대를 정리하기 전 현재 고정 경로를 확인하는 도구입니다.
영구 삭제나 공간 확보를 자동으로 하지 않습니다.</p>
<p><strong>대규모 I/O를 피하도록 수정했습니다.</strong> 작은 설정·manifest와 폴더/파일 속성만 확인하며,
DB·색인 열기, du, 재귀 스캔, 전체 파일 해시, 모델 호출, warmup, 서버 재시작은 수행하지 않습니다.
경로 조회와 작은 로그 기록에는 소량의 I/O가 발생합니다.</p>
<p><strong>지금은 check만 실행해 주세요.</strong> 실제 파일을 올린 TRANSFER 폴더에서:</p>
<pre>python3 -m zipfile -e ./{VERSION}.zip ./{VERSION}
bash ./{VERSION}/{RUN} check</pre>
<p><strong>METADATA_CHECK_PASS</strong>와 <strong>STORAGE_EXIT=0</strong>을 확인합니다.
기존 ~/DEV의 GENOS_SERVING_PATHS.json과 선택 세대를 대조합니다. 코드 설치나 Git push는 필요 없습니다.</p>
<p>별도 명령 <code>isolate</code>는 과거 폴더를 같은 NFS의
<code>/nfs-root/diamo/8-agent/term-releases-quarantine-20261016-r1</code>으로
복사 없이 이동하고, <code>verify</code>는 메타데이터만 재확인합니다.
<code>restore</code>는 원위치 복구, <code>status</code>는 위치 확인입니다.
이 명령들은 check에서 자동 실행되지 않습니다. 자세한 순서는 첨부 안내를 참고해 주세요.</p>
<p><strong>현재 캐시를 사용하는 응답만으로 삭제 후 정상 동작을 확정할 수는 없습니다.</strong>
부하를 감당할 수 있을 때 서버 캐시 재적재와 워크플로우 테스트가 필요하며,
과거 재구축/롤백/감사 자료 보존을 확인한 뒤 최종 삭제해야 합니다.
이번 파일에는 영구 삭제 기능이 없습니다.</p>
<p>ZIP 안 TXT와 별도 첨부 TXT는 같은 완전한 실행 파일입니다. 이후에도 같은 위치의 TXT를 계속
사용해야 기록을 이어갑니다. 이미 단독 TXT로 check를 실행했다면 기존 TXT/상태 위치를 유지해 주세요.</p>
<p>로컬 검사 14개 및 실제 TXT 11명령을 확인했습니다. GENOS 현장 실행·서비스 정상 작동·공간 회수는
아직 수행하지 않았습니다. 로그/상태는 실행 TXT 옆에 저장됩니다.</p>
<p>첨부: ZIP, 별도 실행 TXT, 안내, 검증 기록, 첨부 SHA-256 목록.</p>
</body></html>'''
names = [archive.name, RUN, 'GUIDE_UTF8.txt', 'VALIDATION.json']
hashes = ROOT / 'EMAIL_ATTACHMENTS_SHA256.txt'
hashes.write_text(''.join(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() + '  ' + n + '\n' for n in names))
names.append(hashes.name)
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
bindings = []
for name in names:
    raw = (ROOT / name).read_bytes()
    mime = {'.zip': 'application/zip', '.json': 'application/json'}.get(Path(name).suffix, 'text/plain')
    parts.append({'mime_type': mime, 'content_disposition': 'attachment', 'filename': name,
                  'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
    bindings.append({'name': name, 'mime_type': mime, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
args = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[GENOS] term-releases 경량 확인·격리·원복 도구 — 대규모 I/O 없이 check부터 (2026-10-16 R1)',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
(ROOT / 'EMAIL_BODY_UTF8.html').write_text(body)
(ROOT / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=False))
(ROOT / 'EMAIL_PRECHECK.json').write_text(json.dumps({'to': args['to'], 'subject': args['subject'],
    'attachments': bindings, 'zip_members': members, 'javascript_files': 0,
    'bash_syntax': 'PASS', 'python_3_11_syntax': 'PASS', 'script_unchanged_from_test': True}, ensure_ascii=False, indent=2))
print(json.dumps({'to': args['to'], 'subject': args['subject'], 'attachments': bindings, 'zip_members': len(members)}, ensure_ascii=False))
