from common import *
import shutil,zipfile,ast,subprocess
D=ROOT/'08_DEPLOYMENT/GENOS/handoffs/vector_initial_20261028_r1';D.mkdir(parents=True,exist_ok=True)
f=read(DES/'freeze.json');C=ROOT/f['code_root'];stage=read(DES/'staging.json');P=D/'package';P.mkdir(exist_ok=True)
omitted={n:h for n,h in stage['files'].items() if Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs')}
files={n:h for n,h in stage['files'].items() if n not in omitted}
for n,h in f['files'].items():
 if n.startswith('08_DEPLOYMENT/DATAIKU/vector_initial_20261028_r1/') or n=='02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py':files[n]=h
for n,h in files.items():
 assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs');p=P/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p);assert sha(p)==h
manifest={'format':'vector-initial-delivery-v1','files':files,'serving_files':stage['files'],'base_release':'ontology-workflow-20261028-r1','release':'vector-initial-20261028-r1','data_included':False,'field_verified':False,'preserve_existing':omitted}
put(P/'CODE_MANIFEST.json',manifest);mh=sha(P/'CODE_MANIFEST.json');payload=D/'VECTOR_INITIAL_CODE_20261028_R1.zip'
with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in [*files,'CODE_MANIFEST.json']:z.write(P/n,n)
ph=sha(payload)
bootstrap='''import dataiku,hashlib,io,json,pathlib,sys,tempfile,zipfile,atexit,shutil
_vector_folder=dataiku.Folder("ehA8dpVm")
with _vector_folder.get_download_stream("VECTOR_INITIAL_CODE_20261028_R1.zip") as _stream:_vector_bytes=_stream.read(64*1024*1024+1)
assert len(_vector_bytes)<=64*1024*1024 and hashlib.sha256(_vector_bytes).hexdigest()=="PAYLOAD_HASH", "코드 ZIP 해시 불일치"
_vector_root=pathlib.Path(tempfile.mkdtemp(prefix="legal-vector-code-"));atexit.register(shutil.rmtree,_vector_root,ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(_vector_bytes)) as _zip:
 _names=_zip.namelist();assert len(_names)==len(set(_names))
 for _entry in _zip.infolist():
  _p=pathlib.PurePosixPath(_entry.filename)
  assert not _p.is_absolute() and ".." not in _p.parts and (_entry.external_attr>>16)&0o170000 != 0o120000
 _manifest=json.loads(_zip.read("CODE_MANIFEST.json"))
 assert set(_names)==set(_manifest["files"])|{"CODE_MANIFEST.json"}
 for _name,_hash in _manifest["files"].items():
  _body=_zip.read(_name);assert hashlib.sha256(_body).hexdigest()==_hash
  _dest=_vector_root/_name;_dest.parent.mkdir(parents=True,exist_ok=True);_dest.write_bytes(_body)
sys.path[:0]=[str(_vector_root/"02_BACKEND"),str(_vector_root/"08_DEPLOYMENT/DATAIKU/vector_initial_20261028_r1")]
'''.replace('PAYLOAD_HASH',ph)
install='''# Dataiku LEGAL_RAG 프로젝트 Python 노트북에서 이 TXT 전체를 한 셀로 실행합니다.
# 먼저 VECTOR_INITIAL_CODE_20261028_R1.zip을 기존 ehA8dpVm 폴더 루트에 업로드하세요.
# 첫 설치만 아래 실제 배포 모델 정보 3개를 입력합니다. 비밀키는 프로젝트 보안 변수 GENOS_EMBED_KEY에 둡니다.
EMBED_MODEL = "실제 임베딩 모델 ID"
EMBED_REVISION = "실제 배포 가중치 버전 또는 SHA256"
EMBED_DIMENSIONS = 0  # 실제 출력 차원 (예: 1024). 임의 추정하지 않습니다.
QUERY_RELEASE_ID = ""  # 기존 main query 게시본이면 공란. 신규 적재면 03의 complete.json query_release_id.
'''+bootstrap+'''
from semantic_runtime.initial_vector import profile,endpoint
assert EMBED_DIMENSIONS>0 and not EMBED_MODEL.startswith("실제") and not EMBED_REVISION.startswith("실제")
_project=dataiku.api_client().get_default_project()
_variables=_project.get_variables();_standard=_variables.setdefault("standard",{})
_env=dataiku.get_custom_variables();_endpoint=endpoint(_env)
_profile=profile({"schema_version":"legal-vector-profile-v1","model":EMBED_MODEL,"revision":EMBED_REVISION,"dimensions":EMBED_DIMENSIONS,"endpoint_sha256":hashlib.sha256(_endpoint.encode()).hexdigest(),"chunk_chars":800,"overlap_chars":100,"normalization":"l2","metric":"COSINE"})
if _standard.get("LEGAL_VECTOR_PROFILE") not in (None,_profile):raise ValueError("기존 임베딩 프로필과 다릅니다. 기존 작업을 보존하고 별도 게시 계획을 확인하세요.")
_standard["LEGAL_VECTOR_PROFILE"]=_profile
if QUERY_RELEASE_ID:
 assert len(QUERY_RELEASE_ID)==64 and all(c in "0123456789abcdef" for c in QUERY_RELEASE_ID)
 if _standard.get("LEGAL_VECTOR_QUERY_RELEASE") not in (None,QUERY_RELEASE_ID):raise ValueError("기존 query release 설정과 다릅니다.")
 _standard["LEGAL_VECTOR_QUERY_RELEASE"]=QUERY_RELEASE_ID
_project.set_variables(_variables)
from install_flow import install
install(_project,BOOTSTRAP)
print("다음: Flow의 LEGAL_04_VECTOR_INITIAL_R1 → Run. 적재·재개·READY 게시까지 실행됩니다.")
'''.replace('BOOTSTRAP',repr(bootstrap))
(D/'DATAIKU_VECTOR_INSTALL_RUN.txt').write_text(install)
ast.parse(install)
apply='''#!/usr/bin/env bash
set -euo pipefail
# bash GENOS_VECTOR_APPLY.txt /절대경로/VECTOR_INITIAL_CODE_20261028_R1.zip /절대경로/실제_Git_checkout
: "${1:?코드 ZIP 경로}" "${2:?실제 GENOS 채팅 RAG Git checkout 경로}"
python3 - "$1" "$2" <<'PY_APPLY'
import ast,hashlib,json,pathlib,shutil,subprocess,sys,tempfile,time,zipfile
archive=pathlib.Path(sys.argv[1]).resolve();root=pathlib.Path(sys.argv[2]).resolve()
assert archive.is_file() and root.is_dir()
assert subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True).strip()==str(root), 'Git checkout 루트 필요'
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True).strip(), '기존 작업 변경을 먼저 보관하세요'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='PAYLOAD_HASH', 'ZIP 해시 불일치'
backup=root.parent/('vector-backup-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(exist_ok=False)
with zipfile.ZipFile(archive) as z:
 names=z.namelist();assert len(names)==len(set(names))
 manifest=json.loads(z.read('CODE_MANIFEST.json'));assert set(names)==set(manifest['files'])|{'CODE_MANIFEST.json'}
 checked={}
 for name,h in manifest['preserve_existing'].items():
  assert (root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest()==h, '기존 UI JavaScript 버전 불일치: '+name
 for name,h in manifest['serving_files'].items():
  if name in manifest['preserve_existing']:continue
  p=pathlib.PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts and p.suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
  target=root/name;assert target.resolve().is_relative_to(root) and not target.is_symlink()
  body=z.read(name);assert hashlib.sha256(body).hexdigest()==h
  if name.endswith('.py'):ast.parse(body,filename=name)
  checked[name]=body
 receipt={'target':str(root),'zip_sha256':'PAYLOAD_HASH','files':manifest['serving_files'],'before':{},'git_commit_before':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'field_revision':None,'query_release_id':None}
 for name in checked:
  p=root/name
  if p.exists():
   assert p.is_file();b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,b);receipt['before'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
  else:receipt['before'][name]=None
 (backup/'RECEIPT.json').write_text(json.dumps(receipt,indent=2))
 for name,body in checked.items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
 for name,h in manifest['serving_files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h
 subprocess.run(['git','diff','--check'],cwd=root,check=True)
 print('CODE_BYTES_VERIFIED',len(checked),'BACKUP',backup)
 print('현재는 코드 반입만 완료. GUIDE의 Oracle/설정/실제 리비전 검증 후 commit/push/배포하세요.')
PY_APPLY
'''.replace('PAYLOAD_HASH',ph)
(D/'GENOS_VECTOR_APPLY.txt').write_text(apply);subprocess.run(['bash','-n',str(D/'GENOS_VECTOR_APPLY.txt')],check=True)
guide='''초기 벡터 검색 + 구조화 데이터 Oracle 적재 / 2026-10-28 R1

이번 전달본
- VECTOR_INITIAL_CODE_20261028_R1.zip: 누적 RAG 코드 457파일 + Dataiku 실행 3파일(기존 동일 JavaScript 1파일은 메일 제외·현장 해시 확인으로 보존). 원문/벡터/키는 미포함.
- GENOS_VECTOR_APPLY.txt: Linux 실제 채팅 RAG Git checkout에 반입, 기존 파일 백업, 코드 해시 확인.
- DATAIKU_VECTOR_INSTALL_RUN.txt: Dataiku Python 노트북 설치 셀. 한 번 설치한 뒤 LEGAL_04_VECTOR_INITIAL_R1 Run으로 적재/재개.
- 기존 문서 변환/파싱 R5 서비스와 별개입니다. 이 ZIP을 legal_pipeline_serving에 덮어쓰지 않습니다.

실행 순서
1. 기존 구조화 데이터의 실버 적재가 완료되어 있어야 합니다. SIDDS의 원문·조회행·COMPLETE query release를 읽습니다.
   기존 main query 게시본을 쓰거나, LEGAL_03_LOAD_SILVER_R1 결과 complete.json의 query_release_id를 설치 셀에 지정합니다.
   아직 구조화 파일만 있고 SQL 조회 게시본이 없다면 기존 03 적재를 먼저 실행합니다. 원문 전체를 GENOS로 내려받지 않습니다.
2. GENOS와 Dataiku에서 같은 임베딩 서비스의 실제 model ID/가중치 revision/차원을 확인합니다.
   승호님 경로처럼 GENOS_BASE_URL + /api/gateway/rep/serving/{GENOS_EMBED_SERVING_ID}/embeddings를 호출합니다.
   모델 자동 대체·/models 사전 호출·자동 HTTP 재시도는 없습니다. BGE와 KURE 벡터를 섞지 않습니다.
3. Dataiku 프로젝트 보안/기존 변수: GENOS_BASE_URL, GENOS_EMBED_SERVING_ID, GENOS_EMBED_KEY.
   직접 URL 환경만 GENOS_EMBED_URL을 대신 사용합니다. 직접 URL과 BASE+ID를 동시에 지정하지 않습니다.
   Oracle 연결은 기존 AIDP. 다르면 LEGAL_ORACLE_CONNECTION 하나만 변경합니다.
   설치 셀이 모델 정보 3개를 하나의 LEGAL_VECTOR_PROFILE JSON으로 보관합니다. 800자/100자겹침/16배치/100후보/20화면은 코드 계약입니다.
4. 코드 ZIP을 LEGAL_RAG/ehA8dpVm 루트에 업로드한 뒤 DATAIKU_VECTOR_INSTALL_RUN.txt 전체를 Python 셀에서 실행합니다.
   기존 프로젝트에 LEGAL_04_VECTOR_INITIAL_R1 및 S3 결과폴더만 추가합니다. 기존 레시피가 다르면 덮어쓰지 않고 중단합니다.
5. 새 레시피 Run. SIDDS.LGL_VCTR_PBLS_S, LGL_VCTR_SEG_S, LGL_VCTR_ACT_S를 만들고 필요한 구간만 임베딩해 저장합니다.
   개발계 계정의 CREATE TABLE/SELECT/INSERT/UPDATE와 원문 조회 권한, Oracle native VECTOR/COSINE 지원이 필요합니다.
   운영 골드의 메타마이너/DBA 승인은 별도입니다. 새로운 SIDDS 테이블 이름은 개발 후보이며 운영 승인 완료가 아닙니다.
6. 결과폴더 /vector/build-state.json에 READY와 publication_id/query_release_id/count를 확인합니다.
   전체 검사 전에는 활성 포인터를 바꾸지 않습니다. 원문 판본·문서 권한·프로필을 결속합니다.
   재실행은 저장한 입력/구간을 검증해 재사용합니다. 이미 READY면 임베딩 호출0회입니다.
7. GENOS 채팅 RAG checkout에 bash GENOS_VECTOR_APPLY.txt 코드ZIP경로 checkout경로 실행.
   GENOS_RAG_INITIAL_SEARCH=vector, 같은 임베딩 접속 3값을 설정하고 기존 oracle_query 조회 경로를 유지합니다.
   GENOS가 선택한 query release와 build-state query_release_id가 같아야 합니다. 새 원문 릴리스는 임의로 자동 교체하지 않습니다.
   검색은 권한 필터 후 조항별 최소 거리로 정렬합니다. 첫100조항, 화면20개, 다음 페이지 재사용. 명시 조항/부분 범위는 기존 경로입니다.
   빈 결과·일시 통신 실패는 기존 검색으로 복귀합니다. 미게시/프로필 불일치/권한 위반은 오류로 표시합니다.
   GENOS_RAG_INITIAL_SEARCH=keyword는 즉시 복구용(프로세스 재시작). 기본 auto는 벡터 미게시 시 기존 검색입니다.
   새 개발 SIDDS 매핑은 vector 설정에서 사용합니다. 기존 agent state의 SIDDA 조회/쓰기 권한은 여전히 필요합니다.
8. 실제 push checkout에서 git diff --check와 동봉 CODE_MANIFEST.json serving_files의 전체 SHA256을 다시 확인합니다.
   기존 조회 release를 Oracle로 조회해 원문/manifest 결속을 확인한 뒤 commit/push하고 해당 commit으로 코드서빙 리비전을 배포합니다.
   /health만으로 끝내지 말고 실제 질문 1개의 INITIAL_VECTOR_CANDIDATES → 원문 READ → 최종 주장/근거를 확인합니다.
   query release/원문 판본, 코드 commit/458파일 해시, GENOS 리비전, 요청ID와 응답을 함께 보관합니다.
   이 인계본은 전체 SQLite/NFS generation 복원 경로를 사용하지 않으므로 NFS 전용 게이트를 성공 증거로 대신 쓰지 않습니다.

중단·재개·롤백
- Dataiku에서 취소하고 현재 임베딩 요청 종료를 확인합니다. SQL/임베딩 총 호출과 원래 7일 기한을 유지합니다.
- 정상 실패는 쓰기 잠금을 해제하고 재실행합니다. 프로세스 강제 종료로 LEASE_ID가 남으면 같은 작업을 동시에 실행하지 않습니다.
  이전 Dataiku job이 종료됐음을 확인한 운영자만 아래 UPDATE를 실행한 뒤 재개합니다(실제 publication_id/lease_id로 바꿈).
  UPDATE SIDDS.LGL_VCTR_PBLS_S SET LEASE_ID=NULL WHERE PUB_ID=:pub AND LEASE_ID=:old_lease AND STATUS='BUILDING'; COMMIT;
- 새 source/profile 작업은 이전 build-state와 SQL 로그를 Dataiku에서 별도 보관한 후 시작합니다. 예산을 초기화하려고 기존 실패 상태를 지우지 않습니다.
- 벡터 게시 롤백은 저장된 previous.PUB_ID와 현재 REVISION으로 CAS UPDATE합니다. 기존 벡터/원문을 삭제하지 않습니다.
  UPDATE SIDDS.LGL_VCTR_ACT_S SET PUB_ID=:previous_pub,REVISION=REVISION+1 WHERE QUERY_ID=:query_id AND REVISION=:current_revision;
  SQL%ROWCOUNT=1 확인 후 COMMIT. 이전 게시본이 READY이고 같은 QUERY_ID인지 먼저 확인합니다.
- 코드 롤백은 GENOS 이전 검증 리비전/설정을 선택합니다. 반입 전 백업 RECEIPT.json의 before 값으로 파일 복원/신규 파일 제거 범위를 확인합니다.

검증 범위
새 생성/평가 모델 호출0. 임베딩 API는 모의, Oracle VECTOR 적재/거리검색/재개는 실제 로컬 임시 스키마.
현장 GENOS 임베딩 모델, Dataiku S3/Flow, 실제 SIDDS 권한, 전체 데이터 적재시간과 법률 정답 품질은 아직 미확인입니다.
1초 성능 달성을 주장하지 않습니다. 기존 온톨로지 ON/OFF 기본 OFF, 원문·번호·추가조사·최종검증 및 호출 예산을 유지합니다.
'''
(D/'GUIDE.txt').write_text(guide)
for n in ('GENOS_VECTOR_APPLY.txt','DATAIKU_VECTOR_INSTALL_RUN.txt','GUIDE.txt'):shutil.copyfile(D/n,P/n)
# A convenience outer archive includes executable TXT and the exact inner ZIP.
bundle=D/'GENOS_VECTOR_MAIN_20261028_R1.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in (payload,D/'GENOS_VECTOR_APPLY.txt',D/'DATAIKU_VECTOR_INSTALL_RUN.txt',D/'GUIDE.txt'):z.write(p,p.name)
with zipfile.ZipFile(bundle) as z:
 assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
 with zipfile.ZipFile(payload) as inner:assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in inner.namelist())
put(D/'DELIVERY.json',{'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (bundle,payload,D/'GENOS_VECTOR_APPLY.txt',D/'DATAIKU_VECTOR_INSTALL_RUN.txt',D/'GUIDE.txt')},'code_manifest_sha256':mh,'serving_files':458,'all_code_files':len(files),'tested_code_root':f['code_root'],'main_selected':False,'field_commit':None,'field_revision':None,'source_data_included':False})
print('Delivery',len(files),'codefiles',bundle.stat().st_size,'bytes',ph)
