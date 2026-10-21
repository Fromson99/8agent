"""Prepare the explicitly requested Samsung mail from verified sealed bytes."""
import base64,hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
H=Path(__file__).resolve().parent
NAME='GENOS_MAIN87_PATCH_20261019_R1'
NAMES=[NAME+'.zip',NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt',
       'VALIDATION.json','FINAL_VERIFICATION.json','SHA256SUMS.txt']
sha=lambda b:hashlib.sha256(b).hexdigest()
assert not (H/'EMAIL_SENT.json').exists(),'Inspect existing send receipt before any repeat'
sealed=json.loads((H/'SEALED.json').read_bytes())
for n,row in sealed['files'].items():
    raw=(H/n).read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes'],n
assert json.loads((H/'FINAL_VERIFICATION.json').read_bytes())['status']=='PASS'
scanned=[]
def archive(raw,label):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        scanned.append({'archive':label,'members':len(z.namelist())})
        for n in z.namelist():
            assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'},n
            if n.lower().endswith('.zip'):archive(z.read(n),label+'/'+n)
archive((H/NAMES[0]).read_bytes(),NAMES[0])
with zipfile.ZipFile(H/NAMES[0]) as z:
    for n in NAMES[1:5]:assert z.read(n)==(H/n).read_bytes(),n
run=(H/NAMES[1]).read_text()
embedded=re.findall(r"raw=base64.b64decode\('([A-Za-z0-9+/=]+)'\)",run)
assert len(embedded)==1
archive(base64.b64decode(embedded[0],validate=True),'RUN embedded package')
subprocess.run(['bash','-n',str(H/NAMES[1])],check=True)
body=f'''<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>MAIN87 누적 패치 R1</strong>을 보내드립니다. 방금 실제 대사를 실행한 로컬 선택 버전 <code>cm-read-continuity-20261019-r1</code> 기준입니다.</p>
<p><strong>이전 MAIN84/83/82 및 MAIN81 R2 코드 적용본 대신 이번 {NAME}을 사용해 주세요.</strong>
출력 압축·시스템 고정값 조립, 본문 읽기 연속성·참조 복귀, 후속 조사 상태, 평가 입력 축약과 저장/표시 일치를 포함합니다.
선택된 MAIN87 서빙 370파일은 동일하며 대사 workflow 1.10.0과 근거 발견 1.0.0입니다. Oracle DP 연결과 기존 현장 설정을 유지합니다.</p>
<p><strong>파일을 실제 업로드한 TRANSFER 폴더에서 아래 순서로 실행합니다.</strong> 압축을 풀기 위해 먼저 DEV로 이동하지 마세요.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt status</pre>
<p>기존 <strong>~/DEV</strong>의 패키지 목록 안 코드를 백업 후 적용합니다. 적용 대상이 다를 때만 <code>--root /실제/DEV</code>를 붙입니다.
원문·NFS generation·검색 선택표·.env·Oracle/내부 모델 설정은 유지하며 기본 check/apply는 데이터 DB/색인 전체를 읽거나 재구축하지 않습니다.
ZIP 안의 RUN TXT와 별도 첨부 RUN TXT는 동일한 완전한 실행 파일입니다.</p>
<p><strong>MAIN87_CODE_APPLIED</strong> 확인 후 GUIDE의 코드 목록으로 기존 DEV 변경을 검토·commit하고, 원래 TRANSFER에서 <code>bash ./{NAME}/{NAME}_RUN.txt gate-code</code>를 실행합니다.
같은 checkout/generation의 전체 데이터 검사는 별도 <code>gate</code> 명령입니다. NFS I/O가 큰 검사이므로 한 번에 하나씩 실행하고, 데이터 검사 없이 코드 검사만 끝난 상태를 전체 검증 완료로 기록하지 마세요.</p>
<p>검증한 commit을 push한 뒤 같은 commit·generation으로 코드서빙 새 리비전을 배포하고 SSE를 재시작합니다.
<strong>{NAME}_WORKFLOW_PASTE_ALL.txt</strong> 전체를 기존 워크플로우 Python 단계에 붙여 넣고 별도로 저장하세요. 코드 ZIP 적용과 편집기 저장은 별도입니다.
실제 질의·warmup 확인은 <strong>워크플로우 테스트 화면</strong>에서 진행합니다.</p>
<p>확인 질의: 대사: 위험관리위원회운영준칙의 위원회 역할과 심의·의결사항을 관련 외규와 비교하고, 공통사항·차이·확인하지 못한 자료를 알려줘.</p>
<p>적용 중 중단은 같은 RUN의 <code>apply</code>로 재개하고, 코드 원복은 <code>undo</code>입니다.
처음부터 로그는 TRANSFER/main87-patch-r1-logs, 상태와 백업 경로는 main87-patch-r1-state/STATUS.json에 남습니다.
이미 진행 중인 요청을 마친 후 적용하고 새 버전은 새 요청 ID로 실행하세요.</p>
<p><strong>확인된 결과와 남은 사항:</strong> 로컬 외부 Qwen3.8의 CM8문항은 8응답/핵심7충족입니다. 실제 대사1건은 12호출·약9분10초로 최종 비교·저장·조회까지 완료했으나 <code>partial</code>, 두 항목 모두 <code>DEFERRED</code>였습니다.
참조 내규 미확보, 적용범위 오판, 반복 설명과 긴 답변(21,685자)이 남습니다. GENOS 내부 모델의 timeout 해소나 현장 배포 성공을 확인한 것은 아닙니다.</p>
<p>첨부: 누적 코드 ZIP, 완전한 RUN TXT, 워크플로우 편집기 전체본, 적용/복구 안내, 설치 검증 결과, 최종 ZIP 확인, SHA-256 목록.
무거운 검사는 하나씩 수행했고 패키지의 설치·재실행·중단 복구·수정 충돌 거부·원복 및 같은 committed checkout의 gate를 확인했습니다.</p>
<p>ZIP SHA-256: {sealed['files'][NAMES[0]]['sha256']}</p>
</body></html>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
for n in NAMES:
    raw=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
    parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] MAIN87 누적 패치 — 코드 ZIP·실행 TXT·워크플로우 전체본 (2026-10-19 R1)',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
check={'to':args['to'],'subject':args['subject'],'attachments':rows,'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,
       'archive_scan':scanned,'javascript_exclusions':'PASS','bash_syntax':'PASS','sealed_files':len(sealed['files'])}
(H/'EMAIL_PRECHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(check,ensure_ascii=False))
