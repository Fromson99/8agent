"""Verify the sealed attachments and prepare the explicitly requested Samsung email."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

O = Path(__file__).resolve().parent
N = 'GENOS_URLLIB_TLS_20261014_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
files = [N+'.zip', N+'_RUN.txt', 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt', 'VALIDATION.json', 'SHA256SUMS.txt']
for line in (O/'SHA256SUMS.txt').read_text().splitlines():
    h, n = line.split(maxsplit=1)
    assert sha((O/n.strip()).read_bytes()) == h
with zipfile.ZipFile(O/files[0]) as z:
    assert z.testzip() is None
    assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    for row in json.loads(z.read('CODE_MANIFEST.json'))['files']:
        raw = z.read(row['path'])
        assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    for n in files[1:-1]:
        assert z.read(n) == (O/n).read_bytes()
subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))], check=True)
v = json.loads((O/'VALIDATION.json').read_bytes())
assert v['installed_contract_tests'] == 224 and v['delivery_tests']['failures'] == 0
attachments = [{'filename': n, 'bytes': (O/n).stat().st_size, 'sha256': sha((O/n).read_bytes())} for n in files]
body = '''<p>요청하신 <b>승호님 방식의 urllib 모델 전송 전환 R1</b>을 전달합니다.</p>
<p>승호 최신 integration(6b3ec4789)의 ELS·발행어음 모델 호출과 10월 8일 httpx→urllib 변경(2e33171ac)을 확인했습니다.
우리 작업 코드에는 반영됐던 전환이 기존 GENOS 인계본에서는 httpx로 남아 있었습니다. 이번 패치는 그 인계 누락을 보완합니다.</p>
<p><b>수정 내용</b></p><ul>
<li>GENOS 모델 목록 조회·일반 JSON·임베딩, 법률 에이전트 및 AD 모델 호출, 최종 답변 스트리밍을 Python 표준 urllib로 연결합니다.</li>
<li>Python 기본 CA 저장소와 SSL_CERT_FILE/SSL_CERT_DIR를 사용합니다. 인증서와 호스트명 검증은 유지합니다.</li>
<li>기존 전체 시간 제한·단일 전송·SSE 종료 파서·오류 원장·최종 답변 검증과 최근 입력 길이 계측을 보존합니다. 모델/프롬프트/출력 상한/조사 예산/캐시/DB/NFS 설정은 바꾸지 않습니다.</li></ul>
<p><b>적용 순서</b><br>
AD_REQUEST_LOGS R2와 ASSESSMENT_GAP_ACTION R2까지 적용된 <b>기존 ~/DEV</b>에 추가 적용합니다.
성공 shortcut·공개 실패 안내·MODEL_INPUT_METRICS R1의 적용 유무를 지원합니다.
앞서 보낸 패치도 같이 설치할 경우 <b>이번 URLLIB_TLS R1을 마지막에 적용</b>하세요.
이번 패치는 기존 MODEL_STREAM_FIX의 종료 수정을 보존하며 전송만 바꿉니다.</p>
<pre>python3 -m zipfile -e ~/TRANSFER/GENOS_URLLIB_TLS_20261014_R1.zip ~/DEV/TRANSFER/urllib-tls-r1-package
bash ~/DEV/TRANSFER/urllib-tls-r1-package/GENOS_URLLIB_TLS_20261014_R1_RUN.txt check
bash ~/DEV/TRANSFER/urllib-tls-r1-package/GENOS_URLLIB_TLS_20261014_R1_RUN.txt apply</pre>
<p>위 ZIP 업로드 경로는 실제 위치로 바꾸세요. 별도 첨부 RUN.txt는 ZIP 안과 동일한 완전한 실행 파일입니다.
실행 첫 단계부터 로그와 실패 상태를 남기며 기존 파일을 백업합니다. 적용 후 GUIDE_UTF8.txt의 안내대로
<b>같은 checkout에서 변경 검토·commit·선택 generation 배포 gate·push·새 코드서빙 리비전 배포·별도 SSE 서버 재시작</b>을 진행합니다.
원문 재구축이나 이번 패치를 위한 워크플로우 편집기 교체는 없습니다. 원복 절차도 포함했습니다.</p>
<p><b>CA와 현장 확인</b><br>
실제 컨테이너의 기본 저장소에 사내 CA가 있으면 이를 사용합니다. 없다면 운영자가 제공한 올바른 CA 번들을
컨테이너에서 읽을 수 있게 설치하고 코드서빙/SSE 프로세스에 SSL_CERT_FILE을 적용해야 합니다.
인증서 검증을 끄지 않습니다. REQUESTS_CA_BUNDLE은 이 전송의 설정이 아닙니다.<br>
기존 <b>워크플로우 테스트 화면</b>에서 질의를 실행하고 동일 요청 로그의
transport_backend=urllib, transport_revision=genos-urllib-tls-20261008-r1 및 답변 스트리밍/완료를 확인하세요.</p>
<p><b>검증과 한계</b><br>
설치본 계약 224개, 설치/재실행/변조 거부/원복 4조합, 실제 RUN 100명령, 같은 committed checkout의 합성 generation gate 4회가 통과했습니다.
실제 localhost TLS로 service.service의 신뢰 CA 부팅 성공 4회와 미신뢰 인증서 거부 4회를 확인했습니다.
수정 3파일은 작업 코드/선택 MAIN61/설치본의 해시가 같습니다. 로컬 MAIN61 포인터와 외부 Qwen adapter는 유지합니다.<br>
작업 확대 검사 70개 중 66통과/4실패이며, 4개는 변경하지 않은 워크플로우의 공개 오류 표시 기대 불일치입니다.
실제 GENOS 또는 외부 모델 호출은 0회입니다. <b>현장 반입·CA 환경·리비전 배포·내부 모델 성공은 아직 미확인</b>입니다.</p>
<p>첨부 6개: 수정 ZIP, 독립 실행 RUN.txt, 적용/원복 안내, 검증 요약, 상세 검증 JSON, SHA256SUMS.txt.<br>
ZIP SHA-256: <code>ZIP_SHA</code></p>'''.replace('ZIP_SHA', attachments[0]['sha256'])
parts = [{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
for n in files:
    parts.append({'mime_type':'application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain',
        'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((O/n).read_bytes()).decode()}})
request = {'to':'hyungjininfocz.son@partner.samsung.com',
    'subject':'[GENOS 수정] 승호님 방식 urllib 모델 전송 전환 R1 — CA/HTTPS (2026-10-14)',
    'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(O/'EMAIL_REQUEST.json').write_text(json.dumps(request,ensure_ascii=False))
(O/'EMAIL_BODY.html').write_text(body)
(O/'EMAIL_ATTACHMENTS.json').write_text(json.dumps(attachments,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'integrity':'PASS','javascript_members':0,'bash_syntax':'PASS','attachments':attachments,
                  'request_bytes':(O/'EMAIL_REQUEST.json').stat().st_size},ensure_ascii=False))
