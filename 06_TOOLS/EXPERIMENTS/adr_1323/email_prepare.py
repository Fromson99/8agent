from common import *
import base64,zipfile,subprocess
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main140_oneclick_mail_20261104_r1'
ZIP='MAIN140_FULL_ORACLE_20261104_R1.zip';RUN='MAIN140_ONECLICK_R1.txt'
v=read(H/'VALIDATION.json');assert v['passed']
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
v.update(main_generation=140,technical_contracts=27,existing_fixture_failures=1,baseline_existing_fixture_failures=1,new_clean_startup_checks=6,prepared_contracts=6,counts_overlap=True,
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
 assert active['generation']==140
 payload={row['path']:row['sha256'] for row in manifest['files']}
 required={row['path']:row['sha256'] for row in manifest['required_files']}
 assert all((payload|{k:h for k,h in required.items()})[n]==h==sha(ROOT/r['code_root']/n) for n,h in r['files'].items())
 # The archive is built solely from the selected public code inventory and the
 # three existing operator tools. No environment file, credential or data added.
 assert set(z.namelist())==set(payload)|{'CODE_MANIFEST.json'}
subprocess.run(['git','diff','--check','--',*read(ART/'working-integration.json')['after']],cwd=ROOT,check=True)
body='''<p>보내주신 코드서빙 사진의 <b>ModuleNotFoundError: No module named semantic_runtime</b>를 재현하고 수정한 MAIN140 전체 코드입니다. 이전 MAIN139 첨부 대신 이번 ZIP·TXT를 사용해주세요.</p>
<p>원인: Oracle 모드 로그 초기화를 02_BACKEND import 경로 등록보다 먼저 호출했습니다. start_sse.py와 stream_app.py 두 파일에서 순서를 수정했습니다. Oracle 연결 전에 발생한 시작 오류입니다.</p>
<p>TRANSFER에 ZIP과 TXT를 함께 넣고 실행:</p><pre>bash MAIN140_ONECLICK_R1.txt</pre>
<p>~/DEV 실제 경로를 자동 확인하고 백업·코드 교체·검증합니다. 완료 표시는 MAIN140_ONECLICK_DONE입니다. 이후 기존 commit/push 절차와 <b>새 코드서빙 리비전 배포</b>를 진행해주세요. 설치 명령은 checkout만 적용합니다.</p>
<p>코드서빙 시작 명령은 사진과 동일하게 유지합니다.</p><pre>python3 08_DEPLOYMENT/GENOS/start_sse.py</pre>
<p><b>추가 환경변수나 PYTHONPATH 설정은 필요 없습니다.</b> 기존 Oracle·포트·GENOS 설정을 유지합니다. MAIN139의 GENOS_EMBED_ID/TOKEN, 프로필 해시/gateway MODEL 생략도 그대로입니다. 별도 Gold 매핑 파일 없이 development_g19_1을 사용합니다.</p>
<p>이전 코드의 동일 오류를 새 프로세스에서 재현했습니다. 수정 후 PYTHONPATH 없는 시작검사·직접 모듈 import·실제 로컬 HTTP /health·SSE_CHECK·/json PING이 통과했습니다. 관련27검사 통과, 오류 안내의 옛 문구를 기대하는 기존fixture1실패는 MAIN139에서도 동일하며 원본 보존했습니다. MAIN140/Gold결속과 한줄설치·코드게이트·복구를 확인했습니다.</p>
<p>현장 새 리비전의 실제 Oracle/임베딩/답변은 이 세션에서 실행하지 않았습니다. GUIDE.txt의 새리비전 시작 확인을 진행해주세요.</p>'''
(H/'EMAIL_BODY.html').write_text(body)
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
rows=[]
for n in names:
 raw=(H/n).read_bytes();mime='application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain'
 parts.append({'mime_type':mime,'filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
 rows.append({'name':n,'bytes':len(raw),'sha256':sha(H/n),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 오류 수정] MAIN140 Oracle 시작 semantic_runtime import 해결 — TRANSFER 한 줄 실행','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
put(H/'EMAIL_PRECHECK.json',{'to':args['to'],'subject':args['subject'],'attachments':rows,'selected_release':active,'zip_files':len(manifest['files']),'JS_excluded':True,'nested_archive':False,'oneclick_verified':True,'no_environment_or_data_files':True})
print(json.dumps({'args_chars':len((H/'EMAIL_ARGS.json').read_text()),'attachments':rows},ensure_ascii=False))
