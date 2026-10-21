"""Prepare the explicitly requested Samsung mail from verified sealed bytes."""
import base64,hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
H=Path(__file__).resolve().parent
NAME='GENOS_MAIN_FULL_20261016_R2'
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
body=f'''<!doctype html><html><body>
<p>요청하신 대사 개선 전체를 <strong>로컬 MAIN81에 반영</strong>했고, GENOS에 적용할 검증된 코드 ZIP과 완전한 실행 TXT를 보냅니다.</p>
<p><strong>이전 GENOS_MAIN_FULL_20261016_R1 대신 이번 {NAME}을 사용해 주세요.</strong>
지정 내규 전문 읽기, 기존 참조 연결 우선 조회, 자식 RAG 원문 반환, 쟁점별 비교표가 포함됩니다.
이전 GENOS 전용 출력 상한 제거·추가 사실 안내 수정도 유지했습니다.</p>
<p><strong>실제 파일을 업로드한 TRANSFER 폴더에서 실행</strong></p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt status</pre>
<p>기존 <strong>~/DEV</strong>에 목록 안 코드를 백업 후 적용합니다. ZIP을 풀기 위해 먼저 DEV로 이동하지 않습니다.
기존 NFS 원문·참조 연결·검색 선택표·고정 generation 설정을 유지하며 기본 check/apply에서는 DB나 색인을 읽지 않습니다.
ZIP 안 RUN과 별도 첨부 RUN은 같은 완전한 실행 파일입니다.</p>
<p><strong>MAIN81_CODE_APPLIED / 종료코드0</strong> 확인 후 GUIDE의 파일 목록으로 DEV 변경을 검토·commit합니다.
원래 TRANSFER에서 <code>bash ./{NAME}/{NAME}_RUN.txt gate-code</code>로 동일 checkout과 ZIP을 확인합니다.
전체 데이터 검사는 별도 <code>gate</code> 명령이며 NFS DB·색인을 읽습니다. 앞선 대규모 I/O 금지 상태에서는 이 명령을 미루고, 코드 검사와 데이터 검증 완료를 구분합니다.</p>
<p>전체 gate를 통과한 commit과 기존 generation으로 push·코드서빙 새 리비전·SSE 재시작을 진행합니다.
<strong>{NAME}_WORKFLOW_PASTE_ALL.txt</strong> 전체를 별도 워크플로우 Python 단계에 반영하고 저장합니다.
이 편집기 반영은 코드 ZIP/Git push와 별도입니다. 실제 질의·warmup은 <strong>워크플로우 테스트 화면</strong>에서만 확인합니다.</p>
<p>중단 후 같은 RUN의 apply로 재개하고, 원복은 같은 RUN의 undo입니다.
처음부터의 로그는 TRANSFER/main-full-r2-logs, 상태·백업 경로는 main-full-r2-state/STATUS.json에 남습니다.</p>
<p>검증한 전달 코드의 설치·중단 복구·중복·원복·계약·GENOS 방식 서비스 시작 및 committed checkout gate 결과를 첨부했습니다.
검사는 로컬 합성 데이터/모델 응답으로 수행했으며 실제 GENOS 배포·내부 모델 대사 결과는 현장 확인 전 미확인입니다.</p>
<p>첨부: 코드 ZIP, 완전한 RUN TXT, 워크플로우 편집기본, 적용 안내, 검증 결과, 최종 ZIP 확인, SHA-256 목록.</p>
<p>ZIP SHA-256: {sealed['files'][NAMES[0]]['sha256']}</p>
</body></html>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
for n in NAMES:
    raw=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
    parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] MAIN81 대사 개선 전체 적용본 — 코드 ZIP·실행 TXT (2026-10-16 R2)',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
check={'to':args['to'],'subject':args['subject'],'attachments':rows,'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,
       'archive_scan':scanned,'javascript_exclusions':'PASS','bash_syntax':'PASS','sealed_files':len(sealed['files'])}
(H/'EMAIL_PRECHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(check,ensure_ascii=False))
