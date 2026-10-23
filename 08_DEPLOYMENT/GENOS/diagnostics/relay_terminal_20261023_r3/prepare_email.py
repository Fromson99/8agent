"""Seal and prepare the user-authorized prefilled R3 email."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
OUT = HERE / 'private_delivery'
NAME = 'GENOS_RELAY_CHECK_20261023_R3'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    os.umask(0o077)
    report = json.loads((HERE/'TEST_STATUS.json').read_text())
    binding = json.loads((HERE/'SOURCE_BINDING.json').read_text())
    assert report['status'] == 'PASS' and report['checks'] == 17
    script = OUT/(NAME+'.txt')
    assert sha(script.read_bytes()) == binding['script_sha256']
    compile(script.read_text(), script.name, 'exec')
    members = {script.name: script.read_bytes()}
    for name in ('GUIDE.txt', 'SOURCE_BINDING.json', 'TEST_STATUS.json', 'TEST_RESULTS.txt'):
        members[name] = (HERE/name).read_bytes()
    members['SHA256SUMS.txt'] = ''.join(sha(raw)+'  '+name+'\n' for name, raw in sorted(members.items())).encode()
    archive = OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in members.items():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.writestr(name, raw)
    with tempfile.TemporaryDirectory(prefix='relay-r3-mail-') as folder:
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and set(z.namelist()) == set(members)
            for name, raw in members.items():
                assert z.read(name) == raw
            z.extractall(folder)
        check = subprocess.run([sys.executable, str(Path(folder)/script.name), '--help'], capture_output=True, text=True)
        assert check.returncode == 0 and '--request' in check.stdout
    body = f'''<html><body>
<p>요청하신 <b>OC·Cookie를 미리 넣은 R3</b>입니다. 이번 실행에는 이전 R1/R2 대신 첨부 R3를 사용하세요.</p>
<p>기본 행정예고 요청에는 로컬에 보관된 입법센터 샘플 OC와 Cookie를, <code>--request law</code>에는 로컬 <code>.env</code>의 법제처 OC를 연결했습니다. <b>별도 입력 없이 실행</b>됩니다. 입법센터 OC·Cookie는 <b>2026-10-15 보관 샘플</b>이며 현재 유효성은 현장 응답으로 확인해야 합니다.</p>
<p>기존 RAG와 별개인 구조화·수집용 코드서빙 작업 공간에서, 첨부를 실제 업로드한 폴더를 현재 위치로 두고 실행하세요. TRANSFER라는 이름의 폴더가 필수인 것은 아닙니다.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
python3 -u ./{NAME}/{NAME}.txt</pre>
<p>TXT는 Python 코드입니다. 별도 첨부 TXT만 사용하는 경우에는 아래 한 줄로 실행할 수 있습니다. ZIP 내부 TXT와 동일하므로 둘 중 한 경로만 사용하세요.</p>
<pre>python3 -u ./{NAME}.txt</pre>
<p>법령 본문 확인은 실행 명령 끝에 <code>--request law</code>를 추가합니다. 기본값은 사진의 <code>/law/making</code> GET이며, <code>target_url</code>과 조회 조건은 기존 R2와 같습니다.</p>
<p>로그는 <b>터미널에 즉시 표시하고 파일에도 저장</b>합니다. 결과는 <code>./GENOS_RELAY_RESULTS_R3/notice-01/</code>의 <code>result.json</code>, <code>terminal.log</code>, <code>events.jsonl</code>에 남습니다. 법령 모드는 <code>law-01/</code>입니다. OC·Cookie는 실행 파일에 포함되지만 로그와 저장 응답에서는 기존처럼 가립니다.</p>
<p>값을 변경하려면 실행 TXT 상단 <code>DEFAULT_CREDENTIALS</code>를 수정하거나 <code>LAW_OC</code>·<code>MAKING_OC</code>·<code>RELAY_COOKIE</code> 환경변수에 새 값을 지정하세요. 환경변수가 내장값보다 우선합니다. Cookie를 생략하려면 <code>RELAY_COOKIE=''</code>로 명시합니다. 값 변경 또는 새 시도에는 <code>--run-id notice-02</code> 또는 <code>--run-id law-02</code>를 추가하세요. 기존 기록은 보존됩니다.</p>
<p>최종 R3 실행본으로 로컬 TLS 전송·기본값 선택·환경변수 우선·자격값 가림·실시간 로그·실패/중단/중복 등 <b>17검사 통과</b>, ZIP 추출과 내부/별도 TXT 일치도 확인했습니다. GENOS 현장 통신·서빙 통합·배포는 아직 수행하지 않았습니다.</p>
</body></html>'''
    (OUT/'EMAIL_BODY.html').write_text(body)
    parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
    attachments = []
    for path, filename in ((archive, archive.name), (script, script.name), (HERE/'GUIDE.txt', NAME+'_GUIDE.txt')):
        raw = path.read_bytes()
        mime = 'application/zip' if path.suffix == '.zip' else 'text/plain'
        part = {'mime_type': mime, 'filename': filename, 'content_disposition': 'attachment',
                'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode().rstrip('=')}}
        if mime == 'text/plain':
            part['charset'] = 'UTF-8'
        parts.append(part)
        attachments.append({'name': filename, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
    payload = {'to': 'hyungjininfocz.son@partner.samsung.com',
               'subject': '[GENOS] 중계 요청 확인 R3 — OC·Cookie 사전 입력본 / 바로 실행',
               'payload': {'mime_type': 'multipart/mixed', 'parts': parts}}
    (OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload, ensure_ascii=False))
    (HERE/'EMAIL_ATTACHMENTS.json').write_text(json.dumps(attachments, ensure_ascii=False, indent=2)+'\n')
    sealed = {'status': 'PASS', 'checks': 17, 'zip_sha256': sha(archive.read_bytes()),
              'script_sha256': binding['script_sha256'], 'members': list(members), 'forbidden_javascript_members': [],
              'zip_member_bytes_verified': True, 'extracted_entrypoint_help': 'PASS', 'field_execution': False}
    (HERE/'SEALED.json').write_text(json.dumps(sealed, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': 'READY', 'to': payload['to'], 'attachments': attachments}, ensure_ascii=False))


if __name__ == '__main__':
    main()
