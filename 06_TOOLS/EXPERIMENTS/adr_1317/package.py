from common import *
import shutil,zipfile,ast
RELEASE='oracle-development-vector-20261104-r1';rp=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';release=read(rp)
out=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main138_oracle_vector_20261104_r1';out.mkdir(exist_ok=False)
code=out/'verified-code';code.mkdir();C=ROOT/release['code_root']
for n,h in release['files'].items():
 assert sha(C/n)==h
 p=code/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
extras={'06_TOOLS/COMMANDS/oracle_vector_probe.py':Path(__file__).parent/'oracle_vector_probe.py',
 '06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py':ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py',
 '06_TOOLS/COMMANDS/genos_release_gate.py':ROOT/'06_TOOLS/COMMANDS/genos_release_gate.py'}
for n,p in extras.items():
 ast.parse(p.read_text());dest=code/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
files=[{'path':str(p.relative_to(code)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(code.rglob('*')) if p.is_file()]
manifest={'format':'8agent-code/1','release_id':RELEASE,'main_generation':138,'files':files,
 'serving_files':len(release['files']),'support_files':sorted(extras),'release_manifest_sha256':sha(rp),
 'data_provider_required':'oracle','no_generation_files_included':True,'quality_certified':False}
(code/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
archive=out/'MAIN138_ORACLE_VECTOR_20261104_R1.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for row in files:z.write(code/row['path'],row['path'])
 z.write(code/'CODE_MANIFEST.json','CODE_MANIFEST.json')
with zipfile.ZipFile(archive) as z:
 for row in files:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
(out/'development.env.example').write_text('''# Existing GENOS/ORDS secrets must be supplied through the development secret settings.
DP=oracle
GENOS_ORACLE_TABLE_MAPPING=development_g19_1
DP_QUERY_CHANNEL=main
GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6
GENOS_RAG_INITIAL_SEARCH=vector
GENOS_RUNTIME_DIR=/__oracle_agent__/runtime
ORACLE_ORDS_BASE_URL=
ORACLE_ORDS_SCHEMA=
ORACLE_ORDS_CLIENT_ID=
ORACLE_ORDS_CLIENT_SECRET=
GENOS_BASE_URL=
GENOS_EMBED_SERVING_ID=
GENOS_EMBED_KEY=
GENOS_EMBED_TENANT_ID=
GENOS_EMBED_MODEL=
GENOS_EMBED_PROFILE_SHA256=
GENOS_GATEWAY_API_PREFIX=none
''')
(out/'개발계_확인방법.txt').write_text('''MAIN138 개발계 Oracle 원문·검색·벡터 확인 — 2026-11-04

로컬 MAIN138 반영 완료. 이 ZIP은 서빙525파일과 점검도구3파일이다.
개발계 GENOS/Dataiku에는 아직 반영하거나 요청하지 않았다.
PeCab/pyarrow/emoji와 requirements는 이번에 바꾸지 않았으며 패키지 추가 설치 명령도 없다.
SQLite 문법을 Oracle로 바꾸는 sqlglot은 개발 시 사전준비 용도뿐이다. 서빙은 준비된639계획을 사용한다.

1. 코드와 대상
ZIP을 별도 폴더에서 확인한 뒤 실제 push 대상 checkout에 반영한다.
CODE_MANIFEST.json과 서빙 파일은 이 패키지 그대로 유지한다. 기존 검증 없이 pin만 고치지 않는다.
작업 checkout에서 git diff --check와 변경 내용을 확인하고 commit한다.
그 checkout의 Python에서 아래를 실행한다. ZIP경로는 반입 ZIP의 실제 절대경로다.

python 06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py --code-root .
python 06_TOOLS/COMMANDS/genos_release_gate.py --code-zip ZIP경로 --deploy-root . --code-only

Oracle 전용이므로 이 gate에는 --code-only를 사용한다. NFS generation E2E를 실행한 것처럼 보고하지 않는다.
gate PASS는 코드 결속이며 개발계 SQL/모델 연결 PASS가 아니다.
현재 Git commit, 실제 코드서빙 revision, Oracle query/source/vector 게시ID는 HANDOFF.json에 아직 미확인이다.

2. 개발계 설정
development.env.example의 DP=oracle, GENOS_ORACLE_TABLE_MAPPING=development_g19_1을 사용한다.
이는 SIDDS 원문/검색/벡터, SIDDA 온톨로지/실행기록의 G19 ..._1 17테이블 계약이다.
로컬 B03 또는 등록용 B003 매핑과 섞지 않는다. 현장 스키마가 다르면 이 매핑의 검사에서 중단된다.
DP_QUERY_CHANNEL은 실제 개발계 채널로 정한다. 명시 게시ID를 쓸 때는 DP_QUERY_RELEASE_ID를 설정하고 채널은 비운다.
옛 DP_RELEASE_ID/DP_CACHE_DIR 방식은 쓰지 않는다. GENOS_GENERATION을 Oracle 데이터 선택값으로 쓰지 않는다.
기존 ORDS OAuth/스키마/주소와 GENOS 임베딩 serving ID/키/tenant를 비밀 설정에 넣는다.
일반 답변 모델의 기존 설정은 유지한다. 진단 로그는 기존 NFS 로그 설정을 사용하며 원문/검색/실행기록은 Oracle이다.
서빙 중 파일 SQLite를 데이터 원본이나 실행기록으로 열지 않는다. 요청 내 :memory: 계산은 남아 있다.
GENOS_RAG_INITIAL_SEARCH=vector는 벡터 실험 선택이다. keyword는 기존 키워드 검색이다.

3. Oracle 게시·임베딩 일치 확인 (코드스페이스 터미널, 모델 호출 없음)
권한 있는 실제 개발계 문서ID를 사용한다. 아래 DOC_ID는 문자 그대로 쓰는 값이 아니다.

python 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id DOC_ID --metadata-only

출력의 query_release_id/source_release_id/dataset_version/vector_publication_id를 기록한다.
profile의 모델/revision/차원/정규화가 적재 모델과 같은지 확인한다.
Dataiku Mesh 모델ID와 GENOS serving명은 서로 다를 수 있으므로 운영자가 동일 모델/설정을 확인해야 한다.
확인된 실제 serving 모델명을 GENOS_EMBED_MODEL에, 출력의 required_GENOS_EMBED_PROFILE_SHA256을
GENOS_EMBED_PROFILE_SHA256에 설정한다. 임의 모델에 해시만 복사해 맞춘 것으로 처리하지 않는다.
게이트웨이는 기본 /embeddings이고 직접 OpenAI 호환 모델 주소는 기본 /v1/embeddings다.
설정 변경 뒤 새 프로세스/서빙 리비전으로 확인한다. 실행 중 설정만 바꾸면 요청을 거부한다.

4. 실제 벡터 한 번 조회 (임베딩 요청 1회)

python 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id DOC_ID --question "확인할 질문"

VECTOR_QUERY_COMPLETED, candidate_count, embedding_calls=1, top5의 문서/원문ID를 확인한다.
candidate_count=0은 호출 성공과 별도로 데이터/질문 범위를 점검해야 한다.
출력은 후보이며 답변 근거 인증이 아니다. 실제 원문·인용은 서비스에서 확인한다.
VECTOR_NOT_PUBLISHED는 선택한 검색 게시에 활성 벡터가 없는 상태다.
VECTOR_BINDING/PROFILE은 적재와 질의 모델 설정 불일치, ORDS 오류는 주소/권한/테이블 계약을 확인한다.
오류를 숨기거나 별도 SQLite 데이터로 대신 성공시키지 않는다.

5. 워크플로우 테스트 UI로 실제 서비스 확인
새 코드서빙 revision과 위 환경설정을 저장한 뒤 워크플로우 테스트 화면에서 수행한다.
HEALTH → 실제 문서 원문 조회 → RAG_SEARCH → 실제 질문 순서로 요청ID/상태를 남긴다.
RAG_SEARCH는 문서/용어 시작점 조회여서 그200만으로 벡터 사용을 판정하지 않는다.
실제 질문의 initial_retrieval_status/vector_publication 또는 서버의 VECTOR_DISTANCE 실행 기록을 함께 확인한다.
원문 인용이 같은 Oracle 게시와 권한 문서에 속하는지 확인하고, 실행기록도 다음 요청에서 다시 읽는다.
현장 출력이 돌아오기 전에는 '개발계 전체 정상'이나 '실제 모델 품질 완료'로 판정하지 않는다.

로컬 확인 결과
- 임시 Oracle23.26.3의 G19 17테이블, 원문파일 격리·파일 SQLite 차단·runtime sqlglot 차단 상태로
  실제 service HEALTH/원문/RAG_SEARCH, 동일 서비스 자원의 벡터SQL, 권한/재사용/Oracle 기록 재조회 통과.
  최종 준비릴리스 이 검사에서92SQL, 임베딩은 고정3차원 응답1회이며 실제 GENOS 모델을 호출하지 않았다.
- 준비릴리스32계약, 사전준비SQL 실제Oracle39검사, MAIN 기동16/Gold 엔진결속9 통과. 일부 검사는 중복이다.
- 기존 Gold 실제BGE벡터 추가검사는 첫 결과 후 기록기 필드오류, 재검사는 메모리보호 중단으로 전체 미완료다.
  개발계 G19 합성자료 검사와 섞어 실제 모델 완료로 표시하지 않는다.
- 온톨로지 작성·게시 전체, 실제 답변 모델, 실제 GENOS/ORDS HTTP 서버 및 부하 성능은 이번 현장 미검증이다.

복귀
로컬 MAIN137 포인터는 새릴리스 rollback/ACTIVE_RELEASE.json에 보존했다.
Gold 이전 binding은 ADR1317/artifacts/main/gold-before.json에 있다.
현장에서는 반영 전 Git commit·코드서빙 revision·환경설정·Oracle 게시ID를 별도로 보존한다.
이번 작업은 기존 Oracle 게시/원문을 변경하지 않았다. 임시 검증용 스키마만 생성 후 삭제했다.
''')
handoff={'release_id':RELEASE,'main':138,'code_root':str(C.relative_to(ROOT)),'code_zip':str(archive.relative_to(ROOT)),'code_zip_sha256':sha(archive),
 'CODE_MANIFEST_sha256':sha(code/'CODE_MANIFEST.json'),'serving_files':len(release['files']),'total_code_files':len(files),
 'selected_local_generation':str((ROOT/release['data_path']).resolve()),'local_generation_manifest_sha256':release['data_manifest_sha256'],
 'development_data_selection':'Oracle DP_QUERY_CHANNEL or DP_QUERY_RELEASE_ID; no NFS generation',
 'field_git_checkout':None,'field_git_commit':None,'field_serving_revision':None,'field_query_release_id':None,'field_vector_publication_id':None,
 'field_executed':False,'quality_certified':False,'verified_bytes':True}
put(out/'HANDOFF.json',handoff)
(out/'SHA256SUMS.txt').write_text('\n'.join(sha(p)+'  '+p.name for p in (archive,out/'HANDOFF.json',out/'개발계_확인방법.txt',out/'development.env.example'))+'\n')
put(ART/'main/handoff.json',handoff)
print('Prepared handoff',len(files),'files',archive.stat().st_size,'bytes')
