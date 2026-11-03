2026-11-03 현재 로컬 MAIN135: ordinary-assessment-20261103-r1 / 서빙516파일.
일반 ASSESS 무손실 입력·공유 검토 연결·완전확보 조사장부 서버조립 반영.
계약196/모의API22·준비API13(중복)/root16/Gold9 통과. 새실모델·Oracle0, 법률품질 미인증.
Gold query/매핑/온톨로지설정/연결기는 유지. 이전 MAIN134 binding 원복은
09_ARTIFACTS/AUDITS/20261103-ordinary-assessment-contract-main/gold-before.json.
아래 안내의 이전 MAIN 번호는 각 시점의 기록이다.

Gold 연결기 — 로컬 MAIN134 온톨로지 관리·가정 표시 연결 / 2026-11-03

현재 실행
- 엔진: ontology-console-20261103-r1 / MAIN134, 선택 코드515파일.
- 정본: 01_DATA/ACTIVE/local/ACTIVE_RELEASE.json → release.json.
- binding.json이 선택 release ID·manifest hash·515파일과 일치해야 실행한다.
  MAIN을 바꿨다면 Gold 포트 호환성을 검증하고 binding을 함께 갱신한다.
  불일치 시 조회 전에 거절하며 다른 엔진으로 자동 우회하지 않는다.
- 같은 원문 새evidence ID 재결속과 새claim ID 충돌 수정을 정식 코드에 포함했다.
  runtime_patches/와 runtime_patch_binding.json은 과거 이력이며 현재 실행하지 않는다.
- 데이터 포트는 기존 rev036의 해시 고정 Oracle 어댑터를 재사용한다.
  maintained engine_common.py가 선택된 MAIN으로 import를 연결한다.
  과거 MAIN120 snapshot과 연구 어댑터 파일은 수정하지 않았다.

현재 데이터·물리명
- A8_GR12_CM1208 / B03 13테이블60컬럼, CM21문서.
- ACTIVE_MAPPING.json → mapping_local_vctr_current.json.
- 벡터구간ID VCTR_SCTN_ID, 명세해시값 DTLS_HASH_VALU.
- 내부 VCTR_SEG_ID/MNFST 논리키는 호환을 위해 유지한다.
- 신청용 R18: mapping_r18_registration.json. 현재 로컬 보존 타입과 구분한다.
- 검색 게시물은 binding.json의 기존 query_release_id로 고정한다.
- 이 통합은 DB 내용·기존 게시물·MAIN 기본 데이터 generation을 바꾸지 않았다.

온톨로지
ontology_settings.json enabled=true, store.gold_profile은 ON/DB다.
상법365/368/369조3게시·원문12앵커·9경로가 기존 Gold에 있다.
기본 MAIN 프로필은 OFF를 유지하며 Gold 요청에만 store.gold_profile을 사용한다.
사용법은 ONTOLOGY_ON_GUIDE.txt, 물리 매핑은 MAPPING_GUIDE.txt를 따른다.

저장소 루트에서 실행
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py health
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py terms 세입자
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py source 3521c3aaa5a735fd 0

API 연결
먼저 새 전용 프로세스에서 connect.open_store(...)를 연다. semantic_runtime을 먼저 import하지 않는다.
with connect.open_store(documents=authenticated_document_ids) as (store, request, transport):
    from semantic_runtime.app import create_app
    # create_app(..., data_store=store, legal_agent_profile=store.gold_profile, ...)
    # contracts_root도 binding.json의 engine_root로 지정한다.
    # 모델/사용자 인증은 기존 호스트의 검증된 값을 사용한다.

--documents는 호스트가 인증한 범위를 제공하며 기본21문서의 부분집합만 가능하다.
사용자 입력 문서 목록 자체가 권한을 부여하지 않는다. 하나의 프로세스에서 다른 엔진과 혼용하지 않는다.
명시 --mapping/--mapping-sha256/--owner/--credentials/--release-id 또는 --channel도 기존 계약을 지켜야 한다.
기본 자격증명은 ~/.local/state/8-agent/gold-r12-1208/readonly-connection.json이며 권한0600을 요구한다.
비밀번호를 코드나 결과 파일에 복제하지 않는다.

검증 결과와 한계
ADR1240 관련114검사 통과/기존8 MAIN124동일·새0. 선택서비스68조건×3설정=204/HEALTH3·모의HTTP3 통과.
실제 Gold 원문·용어·저장벡터3행/native100후보 SQL73, 온톨로지3게시12앵커9경로 SQL157 통과.
SQLite/Oracle scope_keys 포트로 범위 조회를 연결했다. 실제 Oracle 좁은 범위4원문·빈범위0SQL·권한밖거절 확인.
ADR1241 실제 재검증은 호스트 스왑 증가128MiB 초과로4번째 모델 요청 중 중단했다. 정상응답3/진행중결과미확인1·최종답변0.
새임베딩1/벡터100후보/온톨로지369묶음ACQUIRED·원문7대조는 확인했으나 최종입력·답변까지의 전체 E2E는 미완료다.
이번 모델은 문서전체 범위를 골라 좁은 범위 수정함수를 재호출하지 않았다. 해당 수정의 직접 검증은 기술계약과 실제 Oracle 구성요소다.
감독 UNKNOWN은 최종·보완으로 진행하지 않도록 구현되어 있으나 이번 자원감시 종료는 감독 UNKNOWN의 실모델검증이 아니다.
반복 문서페이지 조회 지연은 남는다. 종류 제한 SQL 후보는 속도 이득이 없어 미채택했고 기존 연결기3파일을 유지했다.
필요원문 없는 RESOLVED 반복제출은 NEED_TARGET_INCOMPLETE 등으로 계속 거절한다.
법률 의미·벡터품질·온톨로지 인과효과·현장 Oracle/GENOS 미인증. DB내용·DDL 변경0.

롤백·이력
직전 MAIN124 정식 릴리스와 이전 Gold binding을 보존했다.
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/gold-rollback.json
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/gold-before/binding.json
MAIN124로 공식 롤백할 때 Gold binding도 함께 복구한다. 이번에는 connect.py/engine_common.py/physical_mapping.py를 바꾸지 않았다.
ACTIVE_MAPPING과 ontology_settings, 기존 runtime_patches를 보존했다. runtime_patches는 현재 실행하지 않는다.
기존 호스트 프로세스를 자동 재시작하지 않았다. 새 전용 프로세스에서 선택 엔진을 읽는다.
현장 GENOS 배포·Git commit/push·메일 없음.

상세 근거
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt
04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md
04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md
이전 MAIN124 통합과 실제 실패는 ADR1238·1239, Gold ON 실패는 ADR1233·1235에 보존했다.

2026-11-03: ADR1292 합성 계약169/준비API14·로컬Oracle 격리게시/재조회/철회 검증. 실제 모델 효과/현장 GENOS 품질 미인증. 별도 관리 화면 GUIDE는 ../.. 경로의 DATAIKU/ontology_console_20261103_r1/GUIDE.txt 참조.
