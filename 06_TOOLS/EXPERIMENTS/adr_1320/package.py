from common import *
import ast,zipfile,subprocess
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main139_oneclick_mail_20261104_r1';H.mkdir(exist_ok=False)
OLD=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main138_oneclick_mail_20261104_r2'
ZIP='MAIN139_FULL_ORACLE_20261104_R1.zip';RUN='MAIN139_ONECLICK_R1.txt'
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/a['manifest_path']);C=ROOT/r['code_root']
assert a['generation']==139 and r['release_id']=='genos-embed-env-20261104-r1'
assert all(sha(C/n)==sha(ROOT/n)==h for n,h in r['files'].items())
with zipfile.ZipFile(OLD/'MAIN138_FULL_ORACLE_20261104_R1.zip') as z:
 old=__import__('json').loads(z.read('CODE_MANIFEST.json'))
 files={n:z.read(n) for n in old['support_files']}
probe='06_TOOLS/COMMANDS/oracle_vector_probe.py'
files[probe]=files[probe].decode().replace("'required_GENOS_EMBED_PROFILE_SHA256':digest(profile)","'profile_sha256':digest(profile), 'profile_env_required':False").encode()
for n,h in r['files'].items():
 assert sha(C/n)==h
 files[n]=(C/n).read_bytes()
excluded={n:files.pop(n) for n in list(files) if Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}}
assert set(excluded)=={v['path'] for v in old['required_files']}
hashbytes=lambda x:hashlib.sha256(x).hexdigest()
manifest={k:v for k,v in old.items() if k not in ('files','original_verified_zip_sha256')}
manifest.update(release_id=a['release_id'],main_generation=139,release_manifest_sha256=sha(ROOT/a['manifest_path']),delivery_id=ZIP.removesuffix('.zip'),
 files=[{'path':n,'sha256':hashbytes(raw),'bytes':len(raw)} for n,raw in sorted(files.items())],prior_delivery_zip_sha256=sha(OLD/'MAIN138_FULL_ORACLE_20261104_R1.zip'))
assert all(hashbytes(excluded[v['path']])==v['sha256'] for v in manifest['required_files'])
raw=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
with zipfile.ZipFile(H/ZIP,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for n,data in sorted(files.items()):z.writestr(n,data)
 z.writestr('CODE_MANIFEST.json',raw)
s=(OLD/'MAIN138_ONECLICK_R2.txt').read_text().replace('MAIN138','MAIN139').replace('main138','main139')
s=s.replace(sha(OLD/'MAIN138_FULL_ORACLE_20261104_R1.zip'),sha(H/ZIP))
(H/RUN).write_text(s);subprocess.run(['bash','-n',str(H/RUN)],check=True)
ast.parse(s.split("<<'MAIN139_INSTALL_PY'\n",1)[1].rsplit('\nMAIN139_INSTALL_PY',1)[0],feature_version=(3,11))
(H/'ENVIRONMENT.txt').write_text('''MAIN139 개발계 Oracle 벡터 환경변수 — 프로필 수동입력 생략

코드서빙과 코드스페이스 시험환경에 설정:
DP=oracle
GENOS_ORACLE_TABLE_MAPPING=development_g19_1
GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6
GENOS_RAG_INITIAL_SEARCH=vector
GENOS_EMBED_ID=<사용자가 알고 있는 임베딩 서빙 ID>
GENOS_EMBED_TOKEN=<사용자가 알고 있는 임베딩 서빙 토큰>

기존 GENOS_BASE_URL을 유지한다. 임베딩은 승호님 코드의 GENOS_URL도 지원하며,
둘 다 있으면 GENOS_BASE_URL을 쓴다. 주소를 새로 추측하거나 변경할 필요 없다.
GENOS_EMBED_ID/TOKEN을 그대로 사용하므로 SERVING_ID/KEY 이름으로 중복 등록할 필요 없다.
옛 GENOS_EMBED_SERVING_ID/GENOS_EMBED_KEY도 지원한다. 두 이름이 모두 있으면 ID/TOKEN이 우선한다.

입력하지 않아도 되는 값:
GENOS_EMBED_PROFILE_SHA256: 생략 가능. 선택된 Oracle 벡터 게시의 프로필을 자동으로 사용한다.
  기존 비어 있지 않은 값을 유지하면 선택적 고정값으로 대조하고, 불일치 시 오류를 낸다.
GENOS_EMBED_MODEL: GENOS gateway는 서빙 ID로 모델을 선택하므로 생략 가능.
  명시 값이 있으면 사용하며, gateway가 아닌 직접 모델 URL은 여전히 실제 모델명 필요.
벡터 차원/COSINE/l2·유한값·게시/원문/권한 검사는 유지한다. 같은 적재/질의 모델이라는 사용자 확인을 따른다.

개발계 테이블:
development_g19_1 선택 시 코드에 포함된 SIDDS/SIDDA G19 ..._1 매핑을 사용한다.
별도 Gold 매핑 JSON이나 로컬 B03/B003 연결 설정을 넣지 않는다. 이 값은 DB 접속 비밀이 아니라 테이블 선택값이다.

기존 값 유지:
ORACLE_ORDS_BASE_URL / ORACLE_ORDS_SCHEMA / ORACLE_ORDS_CLIENT_ID / ORACLE_ORDS_CLIENT_SECRET
DP_QUERY_CHANNEL=<실제 개발계 게시채널> 또는 DP_QUERY_RELEASE_ID=<검색 게시ID> 중 하나.
  둘 다 생략 시 기존 기본 채널 main을 사용한다. 기존 개발계 채널이 있으면 그대로 유지한다.
기존 답변 LLM·GENOS_EMBED_TENANT_ID·runtime namespace·NFS 상세 로그 설정 유지.
PeCab/pyarrow 추가 환경변수 없음. 기존 DP_RELEASE_ID/DP_CACHE_DIR 로컬복원 방식은 사용하지 않는다.

설치 TXT는 비밀 환경변수를 자동 등록하지 않는다. 터미널 export는 코드서빙 설정을 바꾸지 않는다.
설정 변경 뒤 새 프로세스/새 코드서빙 리비전으로 실행한다. 토큰 값을 메일/채팅으로 회신하지 않아도 된다.
''')
(H/'GUIDE.txt').write_text('''MAIN139 한 줄 설치 — 개발계 GENOS / Oracle

이전 MAIN138 ZIP·실행 TXT 대신 이번 메일의 MAIN139 두 파일을 사용합니다.
GENOS 코드스페이스 TRANSFER 폴더에 압축을 풀지 않고 함께 넣습니다:
MAIN139_FULL_ORACLE_20261104_R1.zip
MAIN139_ONECLICK_R1.txt

TRANSFER 터미널에서 한 줄 실행:
bash MAIN139_ONECLICK_R1.txt

~/DEV의 실제 경로를 자동으로 찾고 ZIP/필수파일 검사 → 코드 백업 → 덮어쓰기 → 엔진검증을 실행합니다.
별도 --root, apply, export는 필요 없습니다. MAIN139_TARGET으로 대상 경로, MAIN139_ONECLICK_DONE으로 완료를 확인합니다.
Python 3.11 이상이 필요합니다. 기존 데이터/.env/Git/PeCab은 보존하며 app.js 1개는 메일 첨부제외 규칙에 따라 기존 해시를 확인합니다.
같은 명령을 다시 실행하면 설치된 코드가 일치하는지 검증합니다.
로그: TRANSFER/main139-install-logs
백업: DEV/09_ARTIFACTS/BACKUPS/code-replacement

환경설정은 ENVIRONMENT.txt를 참고합니다.
이번에는 GENOS_EMBED_ID/TOKEN을 그대로 받고 프로필 해시를 필수로 받지 않습니다.
게이트웨이에서 GENOS_EMBED_MODEL도 생략 가능하며 Oracle 게시의 차원/정규화 설정을 사용합니다.
개발계는 GENOS_ORACLE_TABLE_MAPPING=development_g19_1만 유지하고 별도 Gold 매핑 파일은 넣지 않습니다.

코드 반영 이후 현장의 기존 commit/push/새 코드서빙 revision 절차를 진행합니다. 설치 명령이 자동 배포하지는 않습니다.
전달본 파일만 stage하려면:
bash MAIN139_ONECLICK_R1.txt stage
commit 후 ZIP과 배포 checkout 일치를 확인하려면:
bash MAIN139_ONECLICK_R1.txt gate-code

선택 진단(기동의 필수 선행단계 아님):
cd "$HOME/DEV"
python3 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id '실제_문서_ID' --metadata-only
python3 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id '실제_문서_ID' --question '확인할 질문'
두 번째 명령은 실제 임베딩 1회 호출합니다. VECTOR_QUERY_COMPLETED와 candidate_count를 확인합니다.
그 후 새 리비전의 워크플로우 테스트 화면에서 실제 질문/원문을 확인합니다.
현장 GENOS 임베딩/전체 답변은 아직 이 세션에서 실행하지 않았습니다.

복구: 강제중단 후 복구 요청이 나오면 TRANSFER에서 로그의 백업경로로 실행한 뒤 다시 한 줄 설치합니다.
bash MAIN139_ONECLICK_R1.txt undo --backup '로그에 나온 백업 폴더 절대경로'
다른 작업으로 바뀐 파일은 자동 덮어쓰지 않고 중단합니다.
''')
put(H/'HANDOFF.json',{'revision':'main139-oneclick-r1','release':a,'zip':ZIP,'zip_sha256':sha(H/ZIP),'run':RUN,'files':len(files),
 'serving_files':len(r['files']),'required_existing_files':manifest['required_files'],'default_root':'~/DEV resolved','field_deployed':False,'real_GENOS_calls':0})
put(ART/'main/handoff.json',{'directory':str(H.relative_to(ROOT)),'zip_sha256':sha(H/ZIP)})
print(H,sha(H/ZIP))
