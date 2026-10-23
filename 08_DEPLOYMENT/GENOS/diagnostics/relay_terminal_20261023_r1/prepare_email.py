"""Seal the verified terminal diagnostic for the explicitly requested Samsung email."""
import base64
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
NAME = 'GENOS_RELAY_CHECK_20261023_R1'
SCRIPT = NAME + '.txt'
TO = 'hyungjininfocz.son@partner.samsung.com'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    report = json.loads((HERE / 'VALIDATION.json').read_text())
    for name, sha in report['artifacts'].items():
        assert digest((HERE / name).read_bytes()) == sha, name
    source = (HERE / SCRIPT).read_text()
    compile(source, SCRIPT, 'exec')
    assert report['status'] == 'PASS' and report['checks'] == 12
    guide = f'''GENOS 중계서버 확인 — 삼성메일 첨부 사용법 / 2026-10-23 R1

첨부: {NAME}.zip / {SCRIPT} / {NAME}_GUIDE.txt
ZIP 안에도 같은 실행 TXT와 안내/검증 기록이 있습니다.
아래 TXT는 Python 코드입니다. bash로 실행하지 않습니다.

권장 ZIP 경로
1. 실제 파일을 올린 TRANSFER 폴더를 현재 작업 위치로 둡니다. DEV로 이동하지 않습니다.
2. 압축을 풉니다.
   python3 -m zipfile -e ./{NAME}.zip ./{NAME}
3. 중계 TCP/HTTPS 연결을 확인합니다.
   python3 ./{NAME}/{SCRIPT}
4. 같은 실행 기록에서 법령 본문 GET을 추가합니다.
   python3 ./{NAME}/{SCRIPT} --body
   법제처 등록 OC를 비표시 입력합니다. 중계 Cookie가 필요 없으면 Enter입니다.

별도 TXT를 사용하는 경우
   python3 ./{SCRIPT}
   python3 ./{SCRIPT} --body
ZIP 내부 TXT와 같은 바이트입니다. 둘 중 한 경로만 사용하면 됩니다.

결과: 현재 작업 위치의 ./GENOS_RELAY_RESULTS/relay-check-01/result.json
지속 로그: 같은 폴더 events.jsonl. 본문 수신 시 law_response.xml.gz도 저장합니다.
TCP_OK → HTTP_RESPONSE_RECEIVED는 네트워크 응답 확인이며, BODY_OK는 요청 법령 XML 확인입니다.
HEAD401/403/404/405를 법제처 본문 성공으로 해석하지 않습니다.
같은 run-id는 기존 결과만 보여줍니다. 15분이 지났거나 새 확인이 필요하면:
   python3 ./{NAME}/{SCRIPT} --body --run-id relay-check-02

기본 개발계: https://45.101.64.86:8443/law/DRF
기본 법령: 자본시장과 금융투자업에 관한 법률 / ID010513 / 공포일 기준 target=law
직접 연결, 환경 프록시 자동 사용 없음, 자동 재시도0, TLS 검증 사용.
필요한 경우 담당자가 지정한 주소/CA를 --relay / --ca로 지정하고 새 run-id로 실행합니다.
Python3.9 이상 표준 라이브러리만 사용합니다. 별도 pip 설치가 필요 없습니다.

로컬 TLS 서버에 최종 TXT를 실제 실행한 12검사 통과. GENOS 현장 실행은 미수행입니다.
사용자가 전달한 GENOS 방화벽 해제 안내와 이번 현장 실측 결과는 구분합니다.
코드스페이스 터미널 성공은 배포된 코드서빙 컨테이너 성공까지 의미하지 않습니다.
제품 코드/MAIN/DB/NFS를 변경하는 설치 스크립트가 아닙니다.
'''
    guide_name = NAME + '_GUIDE.txt'
    (HERE / guide_name).write_text(guide)
    members = {SCRIPT: (HERE / SCRIPT).read_bytes(), guide_name: guide.encode()}
    for name in ('GUIDE.txt', 'SOURCE_BINDING.json', 'VALIDATION.json', 'TEST_RESULTS.txt', 'WORK_CONTRACT.txt'):
        members[name] = (HERE / name).read_bytes()
    members['SHA256SUMS.txt'] = ''.join(digest(raw)+'  '+name+'\n' for name, raw in sorted(members.items())).encode()
    archive = HERE / (NAME + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(members.items()):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.writestr(name, raw)
    with tempfile.TemporaryDirectory(prefix='relay-mail-') as folder:
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert set(z.namelist()) == set(members)
            for name, raw in members.items():
                assert z.read(name) == raw
            z.extractall(folder)
        result = subprocess.run([sys.executable, str(Path(folder)/SCRIPT), '--help'], capture_output=True, text=True)
        assert result.returncode == 0 and '--body' in result.stdout
    body = f'''<html><body>
<p>GENOS 터미널에서 API 중계서버 연결과 법령 XML 수신을 확인하는 스크립트입니다.</p>
<p>첨부 ZIP을 실제 업로드한 <b>TRANSFER 폴더</b>에서 아래 순서로 실행하세요. DEV로 이동하거나 제품 코드를 교체하지 않습니다.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
python3 ./{NAME}/{SCRIPT}
python3 ./{NAME}/{SCRIPT} --body</pre>
<p>첫 실행은 TCP와 HTTPS 연결만 확인합니다. <code>--body</code>는 법제처 등록 OC를 비표시 입력받아 법령 본문 GET을 한 번 추가합니다. Cookie는 필요 없으면 Enter를 누르세요. TXT는 Python 코드이므로 bash로 실행하지 않습니다.</p>
<ul><li>기본 개발계: <code>https://45.101.64.86:8443/law/DRF</code></li>
<li><code>TCP_OK → HTTP_RESPONSE_RECEIVED</code>: 해당 터미널에서 중계 HTTP 응답 수신.</li>
<li><code>BODY_OK</code>: 자본시장법(ID010513)의 XML 법령 ID·명칭·조문 확인.</li>
<li>결과: <code>./GENOS_RELAY_RESULTS/relay-check-01/result.json</code>, 지속 로그: <code>events.jsonl</code>.</li>
<li>같은 명령은 기존 기록을 재사용합니다. 새 확인이나 15분 경과 시 <code>--run-id relay-check-02</code>를 추가하세요.</li></ul>
<p>Python 표준 라이브러리만 사용하며 별도 설치는 필요 없습니다. ZIP 내부와 같은 실행 TXT 및 상세 안내 TXT도 별도 첨부했습니다. ZIP과 별도 TXT 중 한 경로만 사용하면 됩니다.</p>
<p>최종 TXT의 로컬 TLS 실전송 포함 12검사를 통과했습니다. GENOS 현장 통신은 아직 확인하지 않았습니다. 터미널 성공과 배포 코드서빙 컨테이너 성공은 구분합니다. 이번 파일은 제품 코드·MAIN·DB·NFS를 변경하지 않습니다.</p>
</body></html>'''
    (HERE / 'EMAIL_BODY.html').write_text(body)
    attachments = [archive, HERE / SCRIPT, HERE / guide_name]
    parts = [{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    metadata = []
    for path in attachments:
        raw = path.read_bytes()
        mime = 'application/zip' if path.suffix == '.zip' else 'text/plain'
        parts.append({'mime_type':mime, 'filename':path.name, 'content_disposition':'attachment',
                      'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode().rstrip('=')}})
        if mime == 'text/plain':
            parts[-1]['charset'] = 'UTF-8'
        metadata.append({'name':path.name, 'bytes':len(raw), 'sha256':digest(raw), 'mime_type':mime})
    payload = {'to':TO,'subject':'[GENOS] API 중계서버 터미널 연결·법령 XML 확인 스크립트 (20261023 R1)',
               'payload':{'mime_type':'multipart/mixed','parts':parts}}
    (HERE / 'EMAIL_PAYLOAD.json').write_text(json.dumps(payload, ensure_ascii=False))
    (HERE / 'EMAIL_ATTACHMENTS.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    (HERE / 'PACKAGING_VALIDATION.json').write_text(json.dumps({'status':'PASS','members':sorted(members),
            'forbidden_javascript_members':[], 'script_matches_validated_sha256':report['artifacts'][SCRIPT],
            'extracted_entrypoint_help':'PASS','attachments':metadata},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'to':TO,'attachments':metadata,'status':'READY'},ensure_ascii=False))


if __name__ == '__main__':
    build()
