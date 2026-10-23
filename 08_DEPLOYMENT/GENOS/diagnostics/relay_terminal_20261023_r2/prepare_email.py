"""Prepare email from the already sealed R2 artifacts without rebuilding them."""
import base64
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
NAME = 'GENOS_RELAY_CHECK_20261023_R2'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    sealed = json.loads((HERE / 'SEALED.json').read_text())
    validation = json.loads((HERE / 'VALIDATION.json').read_text())
    assert sealed['status'] == validation['status'] == 'PASS'
    assert validation['checks'] == 14
    for name, sha in validation['artifacts'].items():
        assert digest((HERE / name).read_bytes()) == sha, name
    archive = HERE / (NAME + '.zip')
    assert digest(archive.read_bytes()) == sealed['zip_sha256']
    assert archive.stat().st_size == sealed['zip_bytes']
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(sealed['members'])
        for name in z.namelist():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            assert z.read(name) == (HERE / name).read_bytes(), name
    body = f'''<html><body>
<p>중계서버 요청 확인용 <b>R2</b>를 보냅니다. 이번 확인에는 이전 R1 대신 첨부 R2를 사용하세요. 기존 실행 결과는 그대로 보존하면 됩니다.</p>
<p>사진의 샘플에 맞춰 <code>/law/making</code> GET 요청과 <code>target_url</code> 헤더·조회 조건을 반영했습니다. 로그는 <b>터미널에 즉시 표시하면서 파일에도 저장</b>합니다. TCP 연결, TLS 협상, HTTP 응답 대기 단계를 구분합니다.</p>
<p>기존 RAG와 별개인 <b>구조화·수집용 코드서빙 작업 공간</b>의 터미널에서 실행하세요. <b>첨부를 실제 올린 폴더</b>가 실행 위치이며, TRANSFER라는 폴더가 반드시 필요한 것은 아닙니다.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
python3 -u ./{NAME}/{NAME}.txt</pre>
<p>국민참여입법센터에 현재 등록된 OC를 비표시 입력합니다. 중계 Cookie가 필요한 경우 현재 허가된 값을 입력하고, 필요 없으면 Enter를 누르세요. TXT는 Python 코드이므로 <code>python3</code>로 실행합니다. 별도 설치 없이 Python 3.9 이상 표준 라이브러리를 사용합니다.</p>
<p>별도 첨부한 실행 TXT만 사용하는 경우에는 아래 명령으로 실행할 수 있습니다. ZIP 안의 TXT와 동일한 파일이므로 둘 중 한 경로만 사용하면 됩니다.</p>
<pre>python3 -u ./{NAME}.txt</pre>
<p>기본 결과 폴더: <code>./GENOS_RELAY_RESULTS_R2/notice-01/</code><br>
결과: <code>result.json</code> / 실시간 로그 사본: <code>terminal.log</code> / 구조화 로그: <code>events.jsonl</code><br>
응답 수신 시 자격값을 제거한 <code>response.body.gz</code>도 저장합니다.</p>
<p>같은 실행은 기록된 결과를 보여주며 요청을 반복하지 않습니다. 새로 시도할 때는 실행 명령 끝에 <code>--run-id notice-02</code>를 추가하세요.</p>
<p><code>NOTICE_XML_REVIEW_REQUIRED</code>는 HTTP 200과 XML 수신까지 확인한 상태이며, 실제 예고 데이터·0건·업무 오류 여부는 응답을 확인해야 합니다. 법령 본문을 별도로 확인할 때는 <code>--request law</code>를 추가하고 국가법령정보센터 OC를 입력하세요.</p>
<p>최종 TXT로 로컬 TLS 전송·시간초과·로그·중단·중복·부분 전송 등 14개 검사를 통과했습니다. GENOS 현장 통신은 실행 결과로 확인해야 합니다. 첨부 안내 TXT에 단계별 판독과 실행 옵션을 정리했습니다.</p>
</body></html>'''
    parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
    metadata = []
    for path, filename in ((archive, archive.name), (HERE / (NAME + '.txt'), NAME + '.txt'), (HERE / 'GUIDE.txt', NAME + '_GUIDE.txt')):
        raw = path.read_bytes()
        mime = 'application/zip' if path.suffix == '.zip' else 'text/plain'
        part = {'mime_type': mime, 'filename': filename, 'content_disposition': 'attachment', 'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode().rstrip('=')}}
        if mime == 'text/plain':
            part['charset'] = 'UTF-8'
        parts.append(part)
        metadata.append({'name': filename, 'bytes': len(raw), 'sha256': digest(raw), 'mime_type': mime})
    payload = {'to': 'hyungjininfocz.son@partner.samsung.com', 'subject': '[GENOS] 중계 요청 확인 R2 — 사진 샘플 GET·터미널/파일 실시간 로그', 'payload': {'mime_type': 'multipart/mixed', 'parts': parts}}
    for name, value in (('EMAIL_PAYLOAD.json', payload), ('EMAIL_ATTACHMENTS.json', metadata)):
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'EMAIL_BODY.html').write_text(body)
    print(json.dumps({'status': 'READY', 'to': payload['to'], 'attachments': metadata}, ensure_ascii=False))


if __name__ == '__main__':
    main()
