별도 R12 골드 연결 폴더 — 기존 MAIN120 엔진

2026-10-30 실제 Oracle 이름 변경 완료: A8_GR12_CM1208의 컬럼9종/16위치를 사진의 물리명으로 변경했다. 테이블13개는 등록된 B03 명칭과 이미 같아 유지했다. 기본 실행은 ACTIVE_MAPPING.json → mapping_local_current.json을 사용한다. 데이터 타입·크기는 보존했다. 원문21문서/벡터16,085개 및 모든 테이블 행 수·객체 ID·제약조건·권한·게시명세 해시는 변경 전후 동일하다. 새 이름의 기본 연결기로 원문·용어집·벡터 검색100후보와 온톨로지 EMPTY 조회를 확인했다. 아래 '현재 로컬 구명칭' 설명은 이름 변경 전 기록이다.
실제 변경·검증·되돌림: 09_ARTIFACTS/AUDITS/20261030-gold-physical-rename/변경과_검증결과.txt

2026-10-30 사진 컬럼명 반영: --mapping으로 13테이블·60컬럼의 물리명을 한 JSON에서 지정한다. mapping_r14_photos.json은 사진의38개 용어, mapping_r12_local.json은 현재 로컬 구명칭에 해당한다. 원문/검색/벡터/온톨로지 조회와 게시 포트에 매핑을 적용했다. 실제 DB 명세가 다르면 조회 전에 거절한다. 사용 방법과 적용 범위는 같은 폴더 MAPPING_GUIDE.txt 참조. 기본 MAIN과 현장 DB는 자동 교체하지 않는다.

2026-10-30 온톨로지 설명 정정: 현재 골드의 ONTL_POST/HEAD/ANC 물리 테이블3개는 존재하며 각각0행이다. 기존 온톨로지 조회 코드의 구테이블/컬럼명과 R12 매핑·적재·설정 연결이 남아 있다. 검색 게시 명세의 ontology 종류0을 물리 테이블 부재로 해석하지 않는다.
정정 상세: 09_ARTIFACTS/AUDITS/20261030-gold-e2e-revalidation/온톨로지_물리테이블_확인과_정정.txt

2026-10-30 후속 실제검증: ADR1232의009는 SQL3,992회로 최종평가에 도달했으나 마지막 모델공백응답/기한종료로504·답변0이었다. UNKNOWN1로007은미실행. 실제벡터 임베딩1→Oracle100후보→3원문→최종입력 연결을 확인했다. 승인온톨로지는 이골드게시물에서제외·설정OFF로미연결이다. MAIN123의별도모의native6검사통과와실제골드E2E를구분한다.
후속 상세: 09_ARTIFACTS/AUDITS/20261030-gold-e2e-revalidation/실제재검증_온톨로지_벡터_E2E결과.txt
아래 실제7·9기록은 선행ADR1214의결과다.

이 폴더는 기존 제품 파일을 수정하지 않고, 검증용으로 고정한 MAIN120의 Oracle Store를 새 골드 게시물에 연결한다.
현재 활성 MAIN 선택과 독립적이다. 전체 추론 성공 여부는 ADR1214의 실제 시험 결과를 확인한다.
데이터 준비/원문 조회 성공은 법률 답변 품질 통과를 의미하지 않는다.
실제 7번은 연결 오류, 9번은 SQL 한도로 중단되어 최종 답변0이다.
후속 보완본은 저장된 9번 응답을 추가 외부 호출 없이 재생하여 SQL4,812회로 기존 중단 지점 이후까지 진행했다.
새 실제 모델로 최종 답변을 완성한 검증은 아직 없다. 새 채널 cm-r12-engine은 별도 실험용이며 기본 연결은 게시물 ID를 고정한다.

기본값
- Oracle: A8_GR12_CM1208, B03 / 13개 테이블·60개 컬럼
- 문서: CM 필수 21문서. 전체 보유 문서 이관이 아니다.
- 게시물: binding.json의 query_release_id. 기존 cm-r12 채널을 변경하지 않는다.
- 엔진: binding.json의 MAIN120 487파일을 실행 전에 해시 대조한다.
- 자격증명: ~/.local/state/8-agent/gold-r12-1208/readonly-connection.json
  비밀번호는 이 폴더나 결과 파일에 복사하지 않는다. 파일 권한은 0600이어야 한다.

저장소 루트에서 실행
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py health
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py terms 세입자
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py source 3521c3aaa5a735fd 0

설정은 명령 앞의 --config, --credentials, --documents, --release-id 또는 --channel로 전달한다.
--documents 파일은 문서 ID 문자열의 JSON 배열이며 기본 21문서보다 좁힐 수만 있다.
사용자 입력의 문서 목록은 인증 권한이 아니다. 서비스 연결 시 호스트가 인증한 범위와 교집합을 전달해야 한다.
다른 게시물·소유자는 같은 R12 구조와 원문/판본/컴파일/벡터 결속을 충족해야 한다.

기존 엔진에 연결
connect.open_store(...) 문맥 안에서 반환되는 store를 기존 create_app의 data_store로 전달한다.
모델 정책·사용자 인증·외부 전송 권한은 호출 호스트가 제공한다. 이 명령은 실제 모델을 자동 호출하지 않는다.
원문/검색/용어/조문/벡터 자료는 Oracle만 읽는다. 별도 로컬 파일로 corpus를 우회하지 않는다.
문서 메타 8MiB·원문 16MiB 한도 내에서, 완전한 원문/게시 해시 검증을 통과한 값만 같은 요청 안에서 재사용한다.
권한·판본 결속이 바뀌면 거절한다. 새 요청은 다시 검증하며 실패·부분 조회는 재사용하지 않는다.
벡터는 기존 BGE-M3 16,085개를 검증해 재사용하며, 질문 벡터는 같은 로컬 모델로 계산한다.

반드시 별도 새 프로세스에서 실행한다. 연결부는 그 프로세스의 데이터 포트를 설치하고 문맥 종료 시 복구한다.
기존 엔진과 같은 프로세스에서 동시에 서비스하거나, 이 예제를 인증 없는 공개 API로 띄우지 않는다.
Oracle/CPU 모델/설계 manifest가 있는 이 작업 공간용 연결기다. GENOS/ORDS/NFS 현장 배포와 B05 실DB는 미검증이다.

증거
04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation/artifacts/run-001
09_ARTIFACTS/AUDITS/20261029-gold-connected-glossary
