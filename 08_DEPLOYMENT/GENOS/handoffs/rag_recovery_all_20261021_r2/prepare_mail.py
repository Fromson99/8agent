"""Build the authorized Samsung mail from the exact sealed delivery; no send."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
NAME = 'GENOS_RAG_RECOVERY_ALL_20261021_R2'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sealed = read(HERE/'SEALED.json')
result = read(HERE/'DELIVERY_VALIDATION.json')
assert sealed['archive_sha256'] == result['archive_sha256'] == sha(HERE/(NAME+'.zip'))
assert result['status'] == 'PASS' and result['installed_service_tests'] == 120
assert result['api_scenarios'] == result['restart_scenarios'] == 4

def inspect(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}, name
            if name.lower().endswith('.zip'):
                inspect(archive.read(name))

names = [NAME+'.zip', NAME+'_RUN.txt', 'GENOS_COMPARISON_READABLE_WORKFLOW_ALL.txt', 'PATCH_NOTE.txt']
inspect((HERE/names[0]).read_bytes())
archive_hash = sha(HERE/names[0])
body = f'''<p>요청하신 <b>추가 조사 없이 종료하는 문제의 재판단 수정</b>을 담은 통합 R2입니다. <b>앞서 보낸 GENOS_RAG_RECOVERY_ALL_20261021_R1 대신 이번 R2 ZIP을 사용하세요.</b></p>
<p>추가 원문이 필요하다고 판단했는데 읽을 수 있는 대상에 조사 행동 없이 FINISH하면, 기존 수정 예산 안에서 <b>1회 재판단</b>합니다. 원문 도구를 선택하거나 이유를 갖춰 조사 필요성을 다시 판단할 수 있습니다. 같은 충돌이 반복되면 종료 사유를 기록하고 읽은 원문·출처·미확인을 제한 답변으로 보존합니다.</p>
<p>이전 원문 선택 미완료 복구, 출처/표 펼치기, 근거 부족 시 정확 원문 제한 답변, 대사 10분 제한도 포함합니다. MAIN96 또는 앞선 알려진 누적 패치(R1 포함)에 이번 ZIP 하나를 적용하면 됩니다.</p>
<p><b>ZIP을 업로드한 실제 TRANSFER 폴더에서 실행하세요.</b> 코드 적용 대상은 기존 ~/DEV입니다. 다른 checkout이면 bash 명령마다 같은 <code>--root /실제/checkout</code>을 추가하세요.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt gate</pre>
<p>백업·로그·재실행·중단 복구·원복을 지원합니다. 이어서 실제 checkout에서 변경 검토·commit → TRANSFER에서 실행 TXT의 <code>gate-code</code> → 같은 commit push·코드서빙 리비전 배포를 진행하세요. 실제 선택 세대 검증과 원복은 PATCH_NOTE.txt를 따르세요.</p>
<p><b>워크플로우 편집기 TXT는 이전 READABLE/R1과 동일합니다.</b> 이미 반영했다면 다시 바꿀 필요가 없습니다. 아직 미반영이면 기존 Python 단계 전체를 백업한 뒤 첨부 WORKFLOW_ALL.txt 내용으로 교체·저장하세요. 이 파일은 bash 실행용이 아닙니다.</p>
<p>로컬 MAIN97에는 같은 재판단 수정이 반영돼 있습니다. <b>이번 현장 ZIP은 기존 R1/workflow1.20.6의 누적 수정본이며 MAIN97 전체 교체본은 아닙니다.</b> 별도 멀티턴 범위 기능/workflow1.20.7은 포함하지 않습니다.</p>
<p>발송하는 최종 ZIP을 설치한 코드에서 <b>{result['installed_service_tests']}검사, API4경로·재시작4경로, 설치/업그레이드/중단 복구/변조 거부/원복 {result['commands']}명령(예상 거부{result['expected_rejections']} 포함)</b>을 확인했습니다. 고정 모의 응답을 사용했고 실제 모델 호출은 0회입니다. 기존 관련 검사6실패와 구 전송 재개1실패는 해결한 것으로 계산하지 않습니다.</p>
<p><b>GENOS 반입·배포·내부 모델 답변 품질은 아직 미검증입니다.</b> 배포 후 워크플로우 테스트 화면에서 사진의 보유·인수 적용 규정 질문을 새 요청으로 실행해 재판단·추가 조사 또는 제한 답변 기록을 확인하세요.</p>
<p>첨부: 누적 ZIP, 별도 실행 TXT, 워크플로우 편집기 TXT, 적용·원복 안내. ZIP 안에도 실행 파일과 안내가 들어 있습니다.</p>
<p>ZIP SHA-256: <code>{archive_hash}</code></p>'''
subject = '[GENOS 통합 R2] 추가 조사 없이 종료하는 문제 재판단 수정 — R1 대체'
parts = [{'mime_type':'text/html', 'charset':'utf-8', 'body':{'content':body}}]
metadata = []
for name in names:
    p = HERE/name
    mime = 'application/zip' if p.suffix == '.zip' else 'text/plain'
    part = {'mime_type':mime, 'filename':name, 'content_disposition':'attachment',
            'body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}}
    if mime == 'text/plain':
        part['charset'] = 'utf-8'
    parts.append(part)
    metadata.append({'filename':name,'mime_type':mime,'bytes':p.stat().st_size,'sha256':sha(p)})
request = {'to':'hyungjininfocz.son@partner.samsung.com','subject':subject,
           'payload':{'mime_type':'multipart/mixed','parts':parts},
           'response_fields':['id','thread_id','label_ids']}
(HERE/'EMAIL_BODY.html').write_text(body)
(HERE/'EMAIL_MANIFEST.json').write_text(json.dumps({'recipient':request['to'],'subject':subject,
    'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'attachments':metadata},ensure_ascii=False,indent=2)+'\n')
transport = json.dumps(request,ensure_ascii=True,separators=(',',':'))
(HERE/'MAIL_TRANSFER.json').write_text(transport,encoding='ascii')
print(json.dumps({'transport_bytes':len(transport),'transport_sha256':hashlib.sha256(transport.encode()).hexdigest(),
                  'attachments':metadata,'recipient':request['to']},ensure_ascii=False))
