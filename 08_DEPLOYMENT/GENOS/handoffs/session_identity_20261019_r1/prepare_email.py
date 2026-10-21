"""Prepare the explicitly requested Samsung mail from verified sealed bytes."""
import base64,hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
H=Path(__file__).resolve().parent
NAME='GENOS_SESSION_IDENTITY_20261019_R1'
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
<p>요청하신 <strong>사용자 ID 요구 제거·팀/세션 기준 멀티턴 수정본 R1</strong>을 보내드립니다.</p>
<p><strong>직전 GENOS_MAIN87_PATCH_20261019_R1 대신 이번 {NAME}을 사용하세요.</strong> MAIN87 누적 코드를 기반으로 수정한 전체 패키지입니다. 기존 Oracle 연결·데이터·현장 설정은 유지합니다.</p>
<p><code>WORKFLOW_USER_ID</code> 설정이나 요청의 <code>user_id</code>가 필요하지 않습니다. 일반 RAG와 대사 실행의 저장·중복 요청·조회·재개를 <strong>team_id + session_id</strong>에 연결했습니다. 같은 채팅은 같은 세션 ID를 유지하고, 재시도에는 같은 request_id를 사용합니다. 팀/문서 접근범위와 코드·데이터·상태 해시 검사는 유지합니다.</p>
<p><strong>파일을 실제 업로드한 TRANSFER 폴더에서 실행하세요.</strong></p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt status</pre>
<p>적용 대상은 기존 <code>~/DEV</code>입니다. 위치가 실제로 다를 때만 <code>--root /실제/DEV</code>를 붙입니다. 로그는 처음부터 <code>./session-identity-r1-logs</code>, 상태/백업 정보는 <code>./session-identity-r1-state/STATUS.json</code>에 남습니다. 중단 후 같은 apply로 재개하며 undo로 원복합니다.</p>
<p><strong>코드 적용 후 GUIDE 순서대로 같은 DEV의 변경 검토·commit → gate-code → 필요 데이터 gate → push → 같은 commit의 코드서빙 새 리비전 배포·SSE 재시작을 진행하세요.</strong> 워크플로우 Python 단계에는 별도 첨부 <strong>{NAME}_WORKFLOW_PASTE_ALL.txt</strong> 전체를 붙여 넣고 저장해야 합니다. 기존 URL·인증·team_id 설정은 유지합니다.</p>
<p>적용 전 진행 중인 실행을 마치고, 적용 후 <strong>새 채팅 세션</strong>에서 워크플로우 테스트 화면으로 확인하세요. 이전 사용자 기준 대화·실행 기록은 보존하며 새 세션으로 자동 이행하지 않습니다. 이전 실행 재개는 원래 코드·데이터 결속이 필요합니다. 이 수정은 세션 식별자를 바로잡는 작업이며 별도 대사 실행 사이의 자연어 후속 대화 기능을 추가한 것은 아닙니다.</p>
<p><strong>로컬 검증:</strong> 관련 계약/API 100개 통과, 기존 MAIN87에서도 동일하게 실패하는 과거 검사8개는 별도 기록했습니다. 사용자 ID 없는 일반 RAG 멀티턴·대사 실행/저장/조회, 중복 요청, 중단/예산 소진 후 재개, 팀·문서·상태 회귀를 확인했습니다. 실제 ZIP/TXT 설치·중단 복구·같은 committed checkout의 gate·정확한 원복도 확인했습니다. 외부 모델 호출은 없으며 <strong>GENOS 현장 적용·내부 모델 실행은 아직 확인하지 않았습니다.</strong> 로컬 활성 MAIN87 포인터도 변경하지 않았습니다.</p>
<p>첨부는 누적 ZIP, 완전한 RUN TXT, 편집기 전체본, 적용/복구 안내, 검증 결과, 최종 ZIP 확인, SHA-256 목록입니다. ZIP 내부와 별도 RUN TXT는 동일합니다.</p>
<p>ZIP SHA-256: {sealed['files'][NAMES[0]]['sha256']}</p>
</body></html>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
for n in NAMES:
    raw=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
    parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] 사용자 ID 요구 제거 — 팀·세션 기반 멀티턴 수정본 (2026-10-19 R1)',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
check={'to':args['to'],'subject':args['subject'],'attachments':rows,'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,
       'archive_scan':scanned,'javascript_exclusions':'PASS','bash_syntax':'PASS','sealed_files':len(sealed['files'])}
(H/'EMAIL_PRECHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(check,ensure_ascii=False))
