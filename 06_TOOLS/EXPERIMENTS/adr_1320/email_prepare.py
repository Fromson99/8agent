from common import *
import base64,zipfile,subprocess
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main139_oneclick_mail_20261104_r1'
ZIP='MAIN139_FULL_ORACLE_20261104_R1.zip';RUN='MAIN139_ONECLICK_R1.txt'
v=read(H/'VALIDATION.json');assert v['passed']
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
v.update(main_generation=139,technical_contracts=60,prepared_contracts=25,counts_overlap=True,
 selected_MAIN_checks=16,Gold_same_engine_checks=9,native_SQL_plans_unchanged=639,engine_preflight={'engines':30,'files':497},
 profile_hash_env_required=False,gateway_model_env_required=False,real_GENOS_embedding_calls=0,real_Oracle_calls_this_revision=0)
(H/'VALIDATION.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
names=[ZIP,RUN,'GUIDE.txt','ENVIRONMENT.txt','VALIDATION.json']
(H/'SHA256SUMS.txt').write_text(''.join(sha(H/n)+'  '+n+'\n' for n in names));names.append('SHA256SUMS.txt')
with zipfile.ZipFile(H/ZIP) as z:
 manifest=json.loads(z.read('CODE_MANIFEST.json'))
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.zip','.tar','.gz','.7z'} for n in z.namelist())
 assert all(hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256'] for row in manifest['files'])
 active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/active['manifest_path'])
 assert active['generation']==139
 payload={row['path']:row['sha256'] for row in manifest['files']}
 required={row['path']:row['sha256'] for row in manifest['required_files']}
 assert all((payload|{k:h for k,h in required.items()})[n]==h==sha(ROOT/r['code_root']/n) for n,h in r['files'].items())
 # The archive is built solely from the selected public code inventory and the
 # three existing operator tools. No environment file, credential or data added.
 assert set(z.namelist())==set(payload)|{'CODE_MANIFEST.json'}
subprocess.run(['git','diff','--check','--',*read(ART/'working-integration.json')['after']],cwd=ROOT,check=True)
body='''<p>요청하신 임베딩 환경설정을 반영한 <b>MAIN139 전체 코드 수정본</b>입니다. 이전 MAIN138 ZIP·실행 TXT 대신 이번 첨부를 사용해주세요.</p>
<p>TRANSFER에 ZIP과 TXT를 함께 넣고 아래 한 줄만 실행합니다.</p><pre>bash MAIN139_ONECLICK_R1.txt</pre>
<p>이번 수정: <b>GENOS_EMBED_ID</b>와 <b>GENOS_EMBED_TOKEN</b>을 그대로 사용합니다. 기존 GENOS_BASE_URL은 유지하면 됩니다. <b>GENOS_EMBED_PROFILE_SHA256은 입력하지 않아도 됩니다.</b> Oracle 게시의 임베딩 프로필을 자동으로 읽습니다. GENOS gateway는 서빙 ID로 모델을 선택하므로 GENOS_EMBED_MODEL도 생략 가능합니다.</p>
<pre>DP=oracle
GENOS_ORACLE_TABLE_MAPPING=development_g19_1
GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6
GENOS_RAG_INITIAL_SEARCH=vector
GENOS_EMBED_ID=알고_계신_임베딩_서빙_ID
GENOS_EMBED_TOKEN=알고_계신_임베딩_서빙_토큰</pre>
<p>개발계는 코드에 포함된 G19 ..._1 테이블 매핑을 선택하므로 <b>별도 Gold 매핑 파일은 필요 없습니다.</b> 기존 ORDS 접속정보·검색 채널·LLM·NFS 로그 설정을 유지합니다. 세부사항은 ENVIRONMENT.txt에 있습니다.</p>
<p>같은 임베딩 모델이라는 사용자 확인을 전제로 하며 게시 무결성·원문/권한·벡터 차원/정상값 검사는 유지했습니다. 기술60검사, MAIN 기동·엔진 결속, 실제 무인자 bash 설치/재실행/코드게이트/복구를 검증했습니다. 현장 GENOS 실제 모델 호출과 코드서빙 배포는 별도입니다.</p>
<p>프로필 조회 명령은 선택 진단이며 설치 전 필수 단계가 아닙니다. 환경변수는 새 코드서빙 revision에도 적용해주세요.</p>'''
(H/'EMAIL_BODY.html').write_text(body)
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
rows=[]
for n in names:
 raw=(H/n).read_bytes();mime='application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain'
 parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
 rows.append({'name':n,'bytes':len(raw),'sha256':sha(H/n),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 수정본] MAIN139 임베딩 ID·TOKEN 사용 / 프로필 입력 생략 / TRANSFER 한 줄 실행','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
put(H/'EMAIL_PRECHECK.json',{'to':args['to'],'subject':args['subject'],'attachments':rows,'selected_release':active,'zip_files':len(manifest['files']),'JS_excluded':True,'nested_archive':False,'oneclick_verified':True,'no_environment_or_data_files':True})
print(json.dumps({'args_chars':len((H/'EMAIL_ARGS.json').read_text()),'attachments':rows},ensure_ascii=False))
