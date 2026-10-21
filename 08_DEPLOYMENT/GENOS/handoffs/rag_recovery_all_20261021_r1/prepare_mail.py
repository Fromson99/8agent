"""Prepare the sealed, explicitly requested Samsung mail; does not send."""
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
NAME = 'GENOS_RAG_RECOVERY_ALL_20261021_R1'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())

sealed = read(HERE/'SEALED.json')
validation = read(HERE/'DELIVERY_VALIDATION.json')
assert sealed['archive_sha256'] == validation['archive_sha256'] == sha(HERE/(NAME+'.zip'))
assert validation['status'] == 'PASS' and validation['installed_service_tests'] == 92
assert validation['commands'] == 70

def inspect_archive(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}, name
            if name.lower().endswith('.zip'):
                inspect_archive(archive.read(name))

names = [NAME+'.zip', NAME+'_RUN.txt', 'GENOS_COMPARISON_READABLE_WORKFLOW_ALL.txt', 'PATCH_NOTE.txt']
inspect_archive((HERE/names[0]).read_bytes())
archive_hash = sha(HERE/names[0])
body = f'''<p>요청하신 세 수정이 모두 들어 있는 <b>통합 누적본</b>입니다. 이전 ZIP을 차례로 설치하지 않고 이번 ZIP 하나만 적용하면 됩니다.</p>
<ol><li><b>원문 선택 미완료 복구</b>: 이미 전달·검증된 원문을 다음 판단 단계로 연결합니다.</li>
<li><b>출처·표 표시</b>: 임시 C번호를 정리하고 내규·외규 원문과 출처를 펼치기 표로 연결합니다.</li>
<li><b>이번 근거 부족 반복 복구</b>: 결론을 확정하지 못해도 확보한 정확 원문·출처·미확인 범위를 부분 답변으로 전달합니다.</li></ol>
<p>기존 10분 제한도 포함했습니다. MAIN96 또는 앞서 보낸 알려진 누적 패치에 적용합니다. 이 통합본이 NAVIGATION_DELIVERY R1 및 READABLE R1/R2/R3를 대신합니다.</p>
<p><b>ZIP을 업로드한 실제 TRANSFER 폴더에서 아래 네 줄을 실행하세요.</b> 코드 적용 대상은 기존 ~/DEV입니다. 다른 checkout이면 bash 명령마다 동일한 --root /실제/checkout 을 추가하세요.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt gate</pre>
<p>자동 백업과 실행 로그를 남기며 재실행·중단복구·원복을 지원합니다. 이후 실제 checkout에서 변경 검토·commit → TRANSFER에서 RUN.txt의 gate-code → 같은 commit push·코드서빙 리비전 배포를 진행하세요. 상세 명령과 원복 방법은 PATCH_NOTE.txt에 있습니다.</p>
<p><b>워크플로우 편집기 TXT는 이전 READABLE 버전과 동일합니다.</b> 이미 반영했다면 재교체할 필요가 없습니다. 아직 미반영이면 기존 Python 단계 전체를 백업하고 첨부 WORKFLOW_ALL.txt 내용으로 교체·저장하세요. 이 파일은 bash 실행용이 아닙니다.</p>
<p>첨부: 누적 ZIP, 별도 실행 RUN.txt, 워크플로우 Python 전체 TXT, 적용·원복 안내. ZIP 안에도 실행 파일과 안내를 함께 넣었습니다.</p>
<p>최종 ZIP을 설치한 코드의 서비스/API 등 <b>92검사</b>, 설치·재실행·중단복구·변조 거부·원복 <b>70명령(예상 거부7 포함)</b>을 확인했습니다. 실제 모델 호출은 0회입니다. 선택 MAIN96·데이터는 변경하지 않았고, GENOS 반입·배포·내부 모델·현장 질문/클릭은 아직 검증하지 않았습니다. 현장 확인은 워크플로우 테스트 화면에서 진행하세요.</p>
<p>ZIP SHA-256: <code>{archive_hash}</code></p>'''
subject = '[GENOS 3건 통합본] 원문 선택 미완료·출처/표·근거 부족 부분답변 — 이 ZIP 하나로 적용'
parts = [{'mime_type':'text/html', 'charset':'utf-8', 'body':{'content':body}}]
metadata = []
for name in names:
    p = HERE/name
    mime = 'application/zip' if p.suffix == '.zip' else 'text/plain'
    part = {'mime_type':mime, 'filename':name, 'content_disposition':'attachment',
            'body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}}
    if mime == 'text/plain': part['charset'] = 'utf-8'
    parts.append(part)
    metadata.append({'filename':name, 'mime_type':mime, 'bytes':p.stat().st_size, 'sha256':sha(p)})
request = {'to':'hyungjininfocz.son@partner.samsung.com', 'subject':subject,
           'payload':{'mime_type':'multipart/mixed', 'parts':parts},
           'response_fields':['id', 'thread_id', 'label_ids']}
(HERE/'EMAIL_BODY.html').write_text(body)
(HERE/'EMAIL_MANIFEST.json').write_text(json.dumps({'recipient':request['to'], 'subject':subject,
    'body_sha256':hashlib.sha256(body.encode()).hexdigest(), 'attachments':metadata},ensure_ascii=False,indent=2)+'\n')
transport = json.dumps(request, ensure_ascii=True, separators=(',', ':'))
(HERE/'MAIL_TRANSFER.json').write_text(transport, encoding='ascii')
print(json.dumps({'transport_bytes':len(transport), 'transport_sha256':hashlib.sha256(transport.encode()).hexdigest(),
                  'attachments':metadata, 'recipient':request['to']}, ensure_ascii=False))
