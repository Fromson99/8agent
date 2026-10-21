import base64
import hashlib
import html
import json
from pathlib import Path
import zipfile

H=Path(__file__).resolve().parent
NAME='GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sealed=json.loads((H/'SEALED.json').read_text())
checked=json.loads((H/'DELIVERY_VALIDATION.json').read_text())
assert checked['status']=='PASS' and checked['commands']==35 and checked['expected_rejections']==12
assert checked['zip_sha256']==sealed['files'][NAME+'.zip']==sha(H/(NAME+'.zip'))
files=[NAME+'.zip','BUILD_DEV_ZIP.txt','RESTORE_NFS.txt','GUIDE_UTF8.txt']
with zipfile.ZipFile(H/(NAME+'.zip')) as z:
    assert z.testzip() is None
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    for name in files[1:]:assert z.read(name)==(H/name).read_bytes()
body=f'''<p>요청하신 대로 <b>명령 두 개</b>로 나눴습니다.</p>
<ol><li><b>BUILD_DEV_ZIP.txt</b>: NFS 데이터의 최신판 선택 정보를 준비해 <code>~/DEV/GENOS_LATEST_SELECTION_DATA_20261021_R1.zip</code> 생성. 이 단계는 NFS 선택 파일을 변경하지 않습니다.</li>
<li><b>RESTORE_NFS.txt</b>: DEV에 있는 위 ZIP을 열어 검증한 뒤 NFS의 <code>SEARCH_SELECTION/generation.json</code>에 적용.</li></ol>
<p><b>이번 첨부 도구 ZIP을 실제 업로드한 폴더에서</b> 아래 세 줄을 순서대로 실행하세요. DEV에 올렸으면 DEV에서, TRANSFER에 올렸으면 그 폴더에서 실행합니다. 코드 조회 대상은 기존 <code>~/DEV</code>입니다.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/BUILD_DEV_ZIP.txt
bash ./{NAME}/RESTORE_NFS.txt</pre>
<p>생성/적용 대상 파일:</p><pre>/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/SEARCH_SELECTION/generation.json</pre>
<p>파일이 없거나 정상 구형이면 첫 명령이 <b>현장 데이터와 기존 승인 정책</b>으로 최신판 JSON을 준비합니다. 파일/데이터 해시가 잘못됐거나 DEV의 선택 경로가 사진과 다르면 쓰기 전에 중단합니다. 두 번째 명령은 기존 파일을 백업하고 같은 명령 재실행 및 원복을 지원합니다.</p>
<p>적용 성공 후 <b>같은 NFS를 읽는 코드서빙/SSE 프로세스를 재시작</b>하고 워크플로우 테스트 화면에서 원래 질문을 확인하세요. ZIP 생성, NFS 적용, 서버 재시작, 실제 질문 성공은 각각 별도 상태입니다. 원문/색인 재구축이나 제품 코드 교체는 없습니다.</p>
<p>검사/상태/원복:</p><pre>bash ./{NAME}/RESTORE_NFS.txt check
bash ./{NAME}/RESTORE_NFS.txt status
bash ./{NAME}/RESTORE_NFS.txt rollback</pre>
<p>로컬 최종 ZIP의 실제 bash <b>35명령</b>(예상 차단12회 포함), 파일/권한 보존, 중단 복구와 원복을 확인했습니다. 최신판 v2 실제 API 검사를 포함한 기존 계약28개가 통과했습니다. 구형 v1을 전제한 API fixture2개는 같은 최신판 검사에서 실패하며 통과로 계산하지 않았습니다. 실제 GENOS 실행은 아직 확인하지 못했습니다.</p>
<p>사진의 별도 요청에서 나온 <b>멀티턴 세션 ID 누락</b>은 이 NFS 파일 작업의 해결 범위에 포함되지 않습니다.</p>
<p>첨부4개: 도구 ZIP, 첫 번째 실행 TXT, 두 번째 실행 TXT, 안내 TXT. ZIP 안에도 두 실행 TXT와 안내/검증 결과가 있습니다.</p>
<p>도구 ZIP SHA-256: <code>{sha(H/(NAME+'.zip'))}</code></p>'''
parts=[{'mime_type':'text/html','charset':'utf-8','body':{'content':body}}]
metadata=[]
for name in files:
    p=H/name;mime='application/zip' if name.endswith('.zip') else 'text/plain'
    part={'mime_type':mime,'filename':name,'content_disposition':'attachment',
          'body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}}
    if mime=='text/plain':part['charset']='utf-8'
    parts.append(part);metadata.append({'filename':name,'mime_type':mime,'bytes':p.stat().st_size,'sha256':sha(p)})
request={'to':'hyungjininfocz.son@partner.samsung.com',
    'subject':'[GENOS] NFS 최신판 파일 → DEV ZIP 생성 / DEV ZIP → NFS 적용 — 실행 TXT 2개',
    'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_BODY.html').write_text(body)
(H/'EMAIL_MANIFEST.json').write_text(json.dumps({'recipient':request['to'],'subject':request['subject'],
    'attachments':metadata,'body_sha256':hashlib.sha256(body.encode()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
(H/'MAIL_TRANSFER.json').write_text(json.dumps(request,ensure_ascii=True,separators=(',',':')))
print(json.dumps({'recipient':request['to'],'attachments':metadata,'request_bytes':(H/'MAIL_TRANSFER.json').stat().st_size},ensure_ascii=False))
