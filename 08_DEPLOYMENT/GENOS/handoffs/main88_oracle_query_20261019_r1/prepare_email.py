"""Seal tested bytes and prepare the explicitly authorized Samsung email."""
from pathlib import Path
import base64,hashlib,html,io,json,subprocess,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3];N='GENOS_MAIN88_ORACLE_QUERY_20261019_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'EMAIL_SENT.json').exists(),'Inspect existing send receipt before retrying'
assert (H/'SOURCE_POINTER.json').read_bytes()==(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes(),'Latest selected MAIN changed'
final=json.loads((H/'FINAL_VERIFICATION.json').read_bytes());assert final['status']=='PASS'
assert final['outer_zip_sha256']==sha((H/(N+'.zip')).read_bytes())
names=[N+'.zip',N+'_RUN.txt',N+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt','VALIDATION.json','FINAL_VERIFICATION.json']
with zipfile.ZipFile(H/names[0]) as z:
 for n in names[1:-1]:assert z.read(n)==(H/n).read_bytes(),n
count=0
def scan(raw):
 global count
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  assert z.testzip() is None
  for item in z.infolist():
   assert Path(item.filename).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
   count+=1
   if item.filename.lower().endswith(('.zip','.whl')):scan(z.read(item.filename))
scan((H/names[0]).read_bytes())
subprocess.run(['bash','-n',str(H/names[1])],check=True)
(H/'SHA256SUMS.txt').write_text(''.join(sha((H/n).read_bytes())+'  '+n+'\n' for n in names))
names+=['SHA256SUMS.txt']
seal={'version':N,'main_release':'answer-first-followup-20261019-r1','pointer_generation':88,
 'files':{n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in names},'field_deployment':'NOT_VERIFIED'}
if (H/'SEALED.json').exists():assert json.loads((H/'SEALED.json').read_bytes())==seal
else:(H/'SEALED.json').write_bytes(enc(seal))
body=f'''<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>최신 MAIN88 + Oracle 직접 조회 통합본</strong>을 보내드립니다.</p>
<p>기준 MAIN은 <code>answer-first-followup-20261019-r1</code>(선택 포인터 generation 88)입니다. 확보한 근거로 먼저 답하고 후속 질문을 이어가는 변경, 팀·세션 처리와 로깅을 유지했습니다.</p>
<p><strong>이전 MAIN87 / SESSION_IDENTITY / ORACLE_LOGGING 패치 대신 이번 {N} ZIP을 사용하세요.</strong> 누적 전체 코드입니다. 기존 사용자 코드 파일은 백업 후 교체하며 .env·원본 데이터·완료 세대는 보존합니다.</p>
<ul><li><code>DP=oracle</code>: 필요한 검색·관계·원문만 Oracle에서 요청별 조회합니다. 서빙으로 전체 SQLite/색인을 내려받지 않습니다.</li>
<li>기존 SQLite 모드도 유지합니다. 대화·실행 이력과 요청 로그는 기존 외부 NFS/CIFS에 둡니다.</li>
<li>주기 갱신은 Dataiku에서 새 조회 릴리스를 게시·검증한 뒤 <code>main</code> 채널을 전환합니다. 새 요청부터 새 버전을 선택하고 진행 중 요청은 이전 버전을 유지합니다.</li></ul>
<p><strong>먼저 Dataiku 쪽에 조회 테이블 4개와 새 조회 릴리스를 준비해야 합니다.</strong> ZIP의 DDL과 GUIDE에 명령을 넣었습니다. 기존 원문 이관 <code>DP_RELEASE_ID</code>를 새 조회 릴리스 ID로 그대로 사용하면 안 됩니다. 서빙은 <code>DP_QUERY_CHANNEL=main</code> 또는 <code>DP_QUERY_RELEASE_ID</code> 하나를 선택합니다. 실제 외부 NFS/CIFS 경로와 기존 ORDS 인증·내부 모델 설정을 사용하세요.</p>
<p><strong>ZIP을 실제 업로드한 TRANSFER 폴더에서 실행하세요.</strong> 아래 <code>/workspace</code>는 제공된 현장 사진의 실제 checkout 경로입니다. 현재 실제 경로가 다르면 확인한 경로로 바꾸세요.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt deps --root /workspace
bash ./{N}/{N}_RUN.txt check --root /workspace
bash ./{N}/{N}_RUN.txt apply --root /workspace
bash ./{N}/{N}_RUN.txt status --root /workspace</pre>
<p><code>deps</code>는 동봉된 sqlglot 30.23.0 wheel을 오프라인 설치합니다. 최초 실행부터 TRANSFER의 <code>main88-oracle-query-r1-logs</code>에 로그/종료 코드가 남고, 패키지 폴더의 STATUS.json에 백업·적용 상태가 남습니다.</p>
<p>GUIDE에 따라 기존 checkout 변경 검토·commit → <code>gate-code</code> → push → 같은 commit의 새 코드서빙 리비전 배포를 진행하세요. <strong>워크플로우 Python 단계에는 첨부 WORKFLOW_PASTE_ALL.txt 전체를 별도로 반영해야 합니다.</strong> 현장 확인은 워크플로우 테스트 화면에서 WARMUP_STATUS와 실제 근거 질문으로 수행합니다. 코드 적용/데이터 게시/리비전 배포/워크플로우 편집기 저장은 각각 별도 단계입니다.</p>
<p><strong>검증:</strong> 통합 코드 계약/API 120개 통과, 실제 ZIP/TXT 설치 2개 시나리오 통과(중단 복구·재실행·같은 committed checkout 코드 게이트·변조 거부·정확한 원복 포함), Python 3.11에서 752개 모듈 컴파일 통과. 최종 ZIP도 다시 설치·상태·원복 확인했습니다. 앞선 Oracle 변경은 별도 로컬 Oracle 23 실제 SQL 검사까지 통과한 기록을 포함합니다.</p>
<p><strong>현장 Oracle 19/ORDS·내부 모델·실제 NFS·전체 데이터 성능과 현장 배포는 미검증</strong>입니다. 이번 반입본 작성이 로컬 MAIN 포인터나 현장 리비전을 변경한 것은 아닙니다. 상세 한계·설정·재개·원복은 GUIDE/VALIDATION을 확인하세요.</p>
<p>첨부: ZIP, 별도 실행 TXT, 워크플로우 편집기 전체본, 적용 안내, 검증 결과, 최종 ZIP 확인, SHA-256 목록. ZIP 내부와 별도 실행 TXT는 동일합니다.</p>
<p>ZIP SHA-256: <code>{seal['files'][N+'.zip']['sha256']}</code></p>
</body></html>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
for n in names:
 raw=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
 parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
 rows.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] 최신 MAIN88 + Oracle 직접 조회 통합본 (2026-10-19 R1)',
 'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_bytes(json.dumps(args,ensure_ascii=False).encode());(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_bytes(enc(rows))
(H/'EMAIL_PRECHECK.json').write_bytes(enc({'status':'PASS','to':args['to'],'subject':args['subject'],'attachments':rows,
 'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size,'members_scanned':count,'javascript_exclusions':'PASS','bash_syntax':'PASS'}))
print(json.dumps({'status':'PASS','to':args['to'],'attachments':len(rows),'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size}))
