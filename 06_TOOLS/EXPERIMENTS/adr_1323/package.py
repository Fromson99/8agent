from common import *
import ast,zipfile,subprocess,shutil
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main140_oneclick_mail_20261104_r1';H.mkdir(exist_ok=False)
OLD=H.with_name('main139_oneclick_mail_20261104_r1')
ZIP='MAIN140_FULL_ORACLE_20261104_R1.zip';RUN='MAIN140_ONECLICK_R1.txt'
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/a['manifest_path']);C=ROOT/r['code_root']
assert a['generation']==140 and a['release_id']=='genos-oracle-startup-20261104-r1'
assert all(sha(C/n)==h for n,h in r['files'].items())
with zipfile.ZipFile(OLD/'MAIN139_FULL_ORACLE_20261104_R1.zip') as z:
 old=json.loads(z.read('CODE_MANIFEST.json'));files={n:z.read(n) for n in old['support_files']}
for n,h in r['files'].items():files[n]=(C/n).read_bytes()
excluded={n:files.pop(n) for n in list(files) if Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}}
hashbytes=lambda raw:hashlib.sha256(raw).hexdigest()
assert all(hashbytes(excluded[row['path']])==row['sha256'] for row in old['required_files'])
manifest={**old,'release_id':a['release_id'],'main_generation':140,'release_manifest_sha256':sha(ROOT/a['manifest_path']),
 'delivery_id':ZIP.removesuffix('.zip'),'prior_delivery_zip_sha256':sha(OLD/'MAIN139_FULL_ORACLE_20261104_R1.zip'),
 'files':[{'path':n,'sha256':hashbytes(raw),'bytes':len(raw)} for n,raw in sorted(files.items())]}
with zipfile.ZipFile(H/ZIP,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for n,raw in sorted(files.items()):z.writestr(n,raw)
 z.writestr('CODE_MANIFEST.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
s=(OLD/'MAIN139_ONECLICK_R1.txt').read_text().replace('MAIN139','MAIN140').replace('main139','main140')
s=s.replace(sha(OLD/'MAIN139_FULL_ORACLE_20261104_R1.zip'),sha(H/ZIP))
(H/RUN).write_text(s);subprocess.run(['bash','-n',str(H/RUN)],check=True)
ast.parse(s.split("<<'MAIN140_INSTALL_PY'\n",1)[1].rsplit('\nMAIN140_INSTALL_PY',1)[0],feature_version=(3,11))
(H/'ENVIRONMENT.txt').write_text((OLD/'ENVIRONMENT.txt').read_text().replace('MAIN139','MAIN140')+'\n이번 시작 오류 수정에 추가 환경변수는 없습니다. PYTHONPATH를 따로 넣지 않아도 됩니다.\n')
(H/'GUIDE.txt').write_text('''MAIN140 — Oracle 모드 시작 시 semantic_runtime import 오류 수정

이전 MAIN139 첨부 대신 이번 ZIP과 TXT를 GENOS 코드스페이스 TRANSFER에 함께 넣습니다. 압축을 풀지 않습니다.
MAIN140_FULL_ORACLE_20261104_R1.zip
MAIN140_ONECLICK_R1.txt

TRANSFER에서 한 줄:
bash MAIN140_ONECLICK_R1.txt

~/DEV 심볼릭 링크를 자동 해석하여 기존 코드 백업 → 목록 덮어쓰기 → 엔진검증을 실행합니다.
완료 표시는 MAIN140_ONECLICK_DONE입니다. 데이터·.env·Git·PeCab은 보존합니다.
로그는 TRANSFER/main140-install-logs, 백업은 DEV/09_ARTIFACTS/BACKUPS/code-replacement에 남습니다.
기존 JS1개는 메일첨부 제외 규칙에 따라 먼저 해시를 확인합니다.

중요: 반입된 checkout으로 기존 commit/push 절차를 진행하고 코드서빙에 새 리비전을 배포합니다.
기존 컨테이너를 그대로 재시작하면 이전 커밋의 코드를 실행할 수 있습니다.
설치 TXT는 Git push나 코드서빙 배포를 자동 실행하지 않습니다.
필요하면 전달본 파일만 stage:
bash MAIN140_ONECLICK_R1.txt stage
commit 후 ZIP과 checkout 일치 확인:
bash MAIN140_ONECLICK_R1.txt gate-code

코드서빙 시작 명령은 사진과 동일하게 유지합니다:
python3 08_DEPLOYMENT/GENOS/start_sse.py

추가 환경변수나 PYTHONPATH 설정은 필요 없습니다. 기존 수신 포트/Oracle/GENOS 환경설정을 유지합니다.
GENOS_EMBED_ID/TOKEN 지원, 프로필 해시 및 gateway 모델명 생략은 MAIN139 그대로입니다.
시작 코드와 직접 HTTP 모듈이 02_BACKEND 경로를 등록한 후 Oracle 로그 초기화를 실행하도록 순서만 수정했습니다.
NFS 검사·Oracle 설정·모델/데이터 조회 로직을 변경하거나 꺼서 우회하지 않았습니다.

코드스페이스 선택 사전검사:
cd "$HOME/DEV"
python3 08_DEPLOYMENT/GENOS/start_sse.py --check
이 검사는 의존성/시작 경로만 확인하며 Oracle/모델을 호출하지 않습니다.
새 컨테이너에서는 로그의 sse.server.starting, Uvicorn 시작과 HTTP /health를 확인한 뒤 실제 질문을 진행합니다.
로컬 새프로세스 실제HTTP health/SSE_CHECK/JSON PING 통과, 현장 새리비전과 실제Oracle/임베딩/답변은 미실행입니다.

복구가 필요하면 TRANSFER에서 로그의 백업 경로를 사용합니다:
bash MAIN140_ONECLICK_R1.txt undo --backup '로그에 나온 백업 폴더 절대경로'
''')
put(H/'HANDOFF.json',{'release':a,'zip':ZIP,'zip_sha256':sha(H/ZIP),'run':RUN,'files':len(files),'required_existing_files':manifest['required_files'],
 'default_root':'~/DEV resolved','same_MAIN139_except_two_startup_files':True,'other_working_multiturn_changes_excluded':True,'field_deployed':False})
put(ART/'main/handoff.json',{'directory':str(H.relative_to(ROOT)),'zip_sha256':sha(H/ZIP)})
print(H,sha(H/ZIP))
