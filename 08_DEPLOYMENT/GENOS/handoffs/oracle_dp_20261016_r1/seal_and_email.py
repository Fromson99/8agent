"""Final package audit and explicitly requested Samsung mail arguments; no send here."""
import base64,hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
H=Path(__file__).resolve().parent;ROOT=H.parents[3];NAME='GENOS_ORACLE_DP_20261016_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
validation=json.loads((H/'VALIDATION.json').read_text());assert validation['status']=='PASS'
binding=json.loads((H/'PACKAGE_BINDING.json').read_text());tested=validation['package_binding']
for name in (NAME+'_RUN.txt',NAME+'_PUBLISH_CELL.txt',NAME+'_CREATE_TABLES.txt'):
    assert binding['files'][name]==tested['files'][name],name
assert binding['payload_sha256']==tested['payload_sha256']
scans=[]
def scan(blob,label):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None;scans.append({'archive':label,'members':len(z.namelist())})
        for n in z.namelist():assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs','.key','.pem','.pfx'),n
        return {n:z.read(n) for n in z.namelist()}
outer=scan((H/(NAME+'.zip')).read_bytes(),'outer')
for n in binding['files']:
    if n.endswith('.zip'):continue
    assert outer[n]==(H/n).read_bytes()
run=(H/(NAME+'_RUN.txt')).read_text();blob=base64.b64decode(re.findall(r"raw=base64.b64decode\('([^']+)'\)",run)[0],validate=True)
inner=scan(blob,'RUN embedded')
spec=json.loads(inner['PATCH_SPEC.json'])
for n,pin in spec['after'].items():assert sha(inner['payload/'+n])==pin and outer['payload/'+n]==inner['payload/'+n]
subprocess.run(['bash','-n',H/(NAME+'_RUN.txt')],check=True)
proof={'status':'PASS','tested_execution_files_unchanged':True,'payload_sha256':spec['payload_sha256'],'scans':scans,
       'local_main_pointer_changed_by_this_task':False,'field_deployment':'NOT_PERFORMED'}
(H/'FINAL_VERIFICATION.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
records={n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in binding['files']}
(H/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+n+'\n' for n,v in records.items()))
(H/'SEALED.json').write_text(json.dumps({'files':records,'payload_sha256':spec['payload_sha256'],'final_verification':proof},ensure_ascii=False,indent=2)+'\n')
body=f'''<!doctype html><html><body>
<p>요청하신 <b>원문 전체 이관 코드</b>는 앞선 메일 <b>[법규 RAG] SQLite → SIDDA 원문 3테이블 전체 이관 코드 R1</b>로 발송했습니다. 이번에는 <b>MAIN81 R2에 추가하는 Oracle DP 패치, 색인 업로드 셀, 추가 테이블 SQL</b>을 보냅니다.</p>
<p><b>순서</b></p><ol>
<li>앞선 전체 이관 셀에서 ACTION="run"으로 SOURCE_COMPLETE까지 진행하고, ACTION="verify"로 VERIFIED를 확인합니다.</li>
<li>이번 CREATE_TABLES.txt의 CREATE 2개를 Dataiku AIDP SQL 노트북에서 각각 실행합니다. SIDDA.LEGAL_RAG_ASSET_PART_A와 SIDDA.LEGAL_RAG_RELEASE_A에 BAIP04APP의 SELECT/INSERT 권한이 필요합니다.</li>
<li>R6 노트북의 같은 연결에서 PUBLISH_CELL.txt 전체를 새 Code 셀에 붙여 실행합니다. VERIFIED 이관 receipt를 사용해 기존 탐색/전문검색 색인과 용어집을 Oracle에 게시합니다. 완료 시 DP_RELEASE_ID가 출력됩니다.</li>
<li>이미 발송한 GENOS_MAIN_FULL_20261016_R2를 기존 ~/DEV에 적용한 뒤 아래 DP 추가 패치를 적용합니다. MAIN81 R2 파일과 다르면 덮어쓰지 않고 중단합니다.</li>
</ol>
<p>첨부를 실제 업로드한 <b>TRANSFER 폴더</b>를 현재 위치로 두고 실행합니다.</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply</pre>
<p>GUIDE의 정확한 변경 파일 목록으로 DEV에서 검토·commit한 뒤 같은 TRANSFER에서 <code>RUN.txt gate-code</code>를 실행하고, 통과한 커밋을 push·새 코드서빙 리비전에 배포합니다. 원복은 같은 RUN의 <code>undo</code>입니다. 적용/재실행/원복 로그와 백업을 보존합니다.</p>
<p><b>코드서빙 환경변수</b>: <code>DP=oracle</code>, <code>DP_RELEASE_ID=게시 결과의 실제 값</code>, <code>DP_CACHE_DIR=/var/tmp/8-agent-oracle-dp</code>. 현장의 비밀 설정으로 <code>ORACLE_ORDS_SCHEMA=b04</code>, 승인된 <code>ORACLE_ORDS_CLIENT_ID</code>/<code>ORACLE_ORDS_CLIENT_SECRET</code>을 설정합니다. SIDDA는 테이블 소유자이며 연결 alias가 아닙니다. 사진의 인증 값은 첨부/메일에 넣지 않았습니다.</p>
<p><b>캐시/색인</b>: 첫 기동에 Oracle 원문 3테이블과 버전에 묶인 색인·용어집을 로컬 디스크로 내려받고 검증합니다. 기존 색인 바이트를 재사용하므로 재색인·재임베딩하지 않습니다. 이후에는 해당 버전의 로컬 캐시로 검색하며 NFS 원문/색인을 읽지 않습니다. 대화/로그 runtime의 기존 저장 위치는 별도입니다. 자료 갱신은 새 버전 게시 후 DP_RELEASE_ID 변경과 프로세스 재시작으로 반영합니다.</p>
<p>자산 게시에는 NFS 파일 읽기와 전송이 필요하고, 최초 캐시 준비 시간/공간은 실제 데이터량에 따라 달라집니다. 로컬 디스크가 리비전 교체 때 지워지는 환경이면 다시 내려받습니다. 별도 vectors가 선언된 generation은 이번 지원 범위 밖이므로 자동 누락하지 않고 중단합니다.</p>
<p>새 리비전에서 <b>워크플로우 테스트 화면</b>으로 WARMUP → WARMUP_STATUS를 실행합니다. READY, data_provider=oracle, 지정 dp_release_id, nfs_source_used=false를 확인한 후 기존 근거 질문으로 확인합니다. RUNNING 동안은 준비를 기다립니다.</p>
<p>봉인 MAIN81 R2를 별도의 실제 Git checkout에 설치해 <b>32개 로컬 계약 검사</b>, 같은 committed checkout의 코드 게이트, 반복 적용/충돌 거부/원복을 확인했습니다. 원문 폴더를 제거한 뒤 Oracle 모의 응답으로 cold/warm 기동·원문 읽기·모의 모델 RAG를 검사했습니다. <b>실제 Oracle 엔진/대용량 성능/현장 배포/GENOS 내부 모델 성공은 아직 미확인</b>입니다.</p>
<p>전체 절차는 GUIDE_UTF8.txt에 있습니다. ZIP 안 실행 TXT와 별도 첨부 실행 TXT는 동일합니다.</p>
</body></html>'''
(H/'EMAIL_BODY_UTF8.html').write_text(body)
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
names=[*binding['files'],'GUIDE_UTF8.txt','FINAL_VERIFICATION.json','SHA256SUMS.txt']
for n in names:
    data=(H/n).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(n).suffix,'text/plain')
    parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(data).decode()}})
    rows.append({'filename':n,'bytes':len(data),'sha256':sha(data)})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[법규 RAG] MAIN81 R2 추가 패치 — Oracle DP 전환·색인 업로드·추가 SQL R1',
    'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(H/'EMAIL_ATTACHMENTS.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'to':args['to'],'subject':args['subject'],'attachments':rows,'final':proof},ensure_ascii=False))
