"""Seal and verify the diagnostic ZIP, then prepare explicit email arguments."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_CODE_INVENTORY_DIAG_20261015_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()


def main():
    archive = OUT / (NAME + '.zip')
    assert not archive.exists(), 'Preserve sealed delivery'
    validation = json.loads((OUT / 'VALIDATION.json').read_bytes())
    assert validation['actual_txt_runs'] == validation['passed'] == 10
    summary = ('GENOS 코드 구성 읽기 전용 진단 R1 검증\n\n'
               '실제 Bash TXT 10회 실행 통과: 알려진2구성, 반복 실행, 미지원 구성, 파일 변경,\n'
               'manifest 없음/구문 오류, 민감 경로 제외, 알려진 적용 후 구성, 엔진 연결 오류.\n'
               '모든 검사에서 대상 checkout의 파일 바이트와 권한 보존.\n'
               'FACT_REASON R1의 봉인된 해시/엔진/정규화 검사 함수를 그대로 사용.\n'
               '외부 모델/GENOS 접속 0회. 현장 실제 실행은 미확인.\n'
               '제품 코드와 로컬 MAIN66, 데이터 및 GENOS 배포 상태는 변경하지 않음.\n')
    (OUT / 'VALIDATION_SUMMARY.txt').write_text(summary)
    members = [NAME + '_RUN.txt', 'diagnose.py', 'GUIDE_UTF8.txt', 'SOURCE_BINDING.json',
               'VALIDATION.json', 'VALIDATION_SUMMARY.txt']
    manifest = {'schema_version': 'genos-read-only-diagnostic-v1', 'revision': NAME,
                'files': [{'path': n, 'bytes': (OUT / n).stat().st_size,
                           'sha256': sha((OUT / n).read_bytes())} for n in members]}
    (OUT / 'CODE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in members + ['CODE_MANIFEST.json']:
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.write(OUT / name, name)
    with tempfile.TemporaryDirectory(prefix='code-diag-sealed-') as td:
        base = Path(td)
        transfer = base / 'TRANSFER'
        transfer.mkdir()
        unpack = transfer / NAME
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist())) == len(members) + 1
            assert all(Path(n).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
            z.extractall(unpack)
        for row in manifest['files']:
            raw = (unpack / row['path']).read_bytes()
            assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        assert (unpack / (NAME + '_RUN.txt')).read_bytes() == (OUT / (NAME + '_RUN.txt')).read_bytes()
        subprocess.run(['bash', '-n', str(unpack / (NAME + '_RUN.txt'))], check=True)
        prior = OUT.with_name('length_recovery_20261014_r1')
        fixture = json.loads((prior / 'FIXTURES.json').read_bytes())[0]
        root = base / 'checkout'
        with zipfile.ZipFile(prior / fixture['path']) as z:
            z.extractall(root)
        before = {str(p.relative_to(root)): (sha(p.read_bytes()), p.stat().st_mode & 0o777)
                  for p in root.rglob('*') if p.is_file()}
        env = dict(os.environ, GENOS_DEV_ROOT=str(root), PYTHONDONTWRITEBYTECODE='1')
        env['PATH'] = str(ROOT / '.venv/bin') + os.pathsep + env['PATH']
        result = subprocess.run(['bash', str(unpack / (NAME + '_RUN.txt'))], cwd=transfer,
                                env=env, capture_output=True, text=True, timeout=200)
        assert result.returncode == 0, result.stdout[-2000:]
        assert 'STATUS=KNOWN_PREDECESSOR' in result.stdout
        after = {str(p.relative_to(root)): (sha(p.read_bytes()), p.stat().st_mode & 0o777)
                 for p in root.rglob('*') if p.is_file()}
        assert before == after
    attachments = [archive.name, NAME + '_RUN.txt', 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt']
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha((OUT / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    attachments.append('SHA256SUMS.txt')
    body = '''<p>요청하신 FACT_REASON R1 설치 오류 확인용 진단 코드를 보내드립니다.</p>
<p>현재 DEV 코드의 적용 버전, 파일 해시, 엔진 연결과 FACT_REASON R1 지원 여부를 검사합니다. <b>기존 코드·manifest·데이터·설정을 변경하지 않고 진단 결과만 저장합니다.</b> 모델 호출이나 자동 전송은 없습니다.</p>
<p>실제로 첨부파일을 업로드한 <b>TRANSFER 폴더에서</b> 다음 두 줄을 실행해 주세요. 먼저 DEV로 이동하지 않습니다.</p>
<pre>python3 -m zipfile -e ./GENOS_CODE_INVENTORY_DIAG_20261015_R1.zip ./GENOS_CODE_INVENTORY_DIAG_20261015_R1
bash ./GENOS_CODE_INVENTORY_DIAG_20261015_R1/GENOS_CODE_INVENTORY_DIAG_20261015_R1_RUN.txt</pre>
<p>검사 대상은 기존 ~/DEV이며 현재 지정한 GENOS_DEV_ROOT/GENOS_DEV가 있으면 그 경로를 따릅니다. 별도 입력값은 없습니다. ZIP 내부와 별도 첨부의 실행 TXT는 동일합니다.</p>
<p>현재 TRANSFER의 <b>code-inventory-diag-r1-results/실행별폴더/</b>에 SUMMARY.txt, DIAGNOSIS.json, DIAGNOSIS.log, EXIT.txt가 생깁니다. 화면 마지막 요약 또는 <b>SUMMARY.txt와 DIAGNOSIS.json</b> 결과를 전달해 주세요. .env·문서 원문·질문·모델 입출력은 수집하지 않습니다.</p>
<p>종료 코드 0은 알려진 코드 지문, 2는 확인할 차이, 3은 진단 미완료입니다. UNSUPPORTED_INVENTORY가 나오면 이번 사진의 지원 목록 불일치를 확인한 것입니다. 진단에는 apply나 해시 재작성 기능이 없으며, 기존 FACT_REASON 패치를 대체하지 않습니다.</p>
<p>실제 TXT 10회 검사와 ZIP에서 꺼낸 TXT 1회 실행을 확인했습니다. 정상/미지원/파일 변경/목록 오류/민감 경로 제외/엔진 오류/반복 실행에서 기존 파일 바이트와 권한이 보존됐습니다. GENOS 현장 실행·배포 성공은 별도 확인 사항입니다.</p>'''
    (OUT / 'EMAIL_BODY_UTF8.html').write_text(body)
    parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
    bindings = []
    for name in attachments:
        raw = (OUT / name).read_bytes()
        mime = 'application/zip' if name.endswith('.zip') else 'text/plain'
        parts.append({'mime_type': mime, 'content_disposition': 'attachment', 'filename': name,
                      'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
        bindings.append({'name': name, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
    (OUT / 'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(bindings, indent=2) + '\n')
    args = {'to': 'hyungjininfocz.son@partner.samsung.com',
            'subject': '[GENOS 코드 진단 R1] FACT_REASON 설치 오류 확인용 ZIP·실행 TXT',
            'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
            'response_fields': ['id', 'thread_id', 'label_ids']}
    (OUT / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=True))
    record = {'revision': NAME, 'zip_sha256': sha(archive.read_bytes()), 'members': members + ['CODE_MANIFEST.json'],
              'member_hashes_verified': True, 'no_javascript': True, 'standalone_txt_identical': True,
              'bash_syntax': 'PASS', 'sealed_txt_execution': 'KNOWN_PREDECESSOR',
              'sealed_execution_code_bytes_and_modes_preserved': True, 'attachments': bindings}
    (OUT / 'SEALED_UNPACK_CHECK.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'zip_bytes': archive.stat().st_size, 'attachments': bindings, 'sealed_execution': 'PASS'}))


if __name__ == '__main__':
    main()
