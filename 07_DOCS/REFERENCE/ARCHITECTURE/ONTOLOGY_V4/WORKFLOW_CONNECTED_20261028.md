# 온톨로지 생성·검토·게시·사용 — 2026-10-28

사용자 요청에 따라 기존 MVP의 사전 조립 시나리오를 운영 입력·화면·DB 소비자까지 연결한다. 과거 MVP의 “화면/S3/SQL은 범위 밖”은 선행 단계 기록이며, 이번 구현의 범위는 이 문서를 따른다. **실제 현장 설치·권한·모델 품질은 로컬 구현 검증과 구분한다.**

**후속 상태:** 현재 선택은 MAIN112이며 아래 MAIN111의 연결 구현을 계승한다. 이번 확인의 `ontology_work` 10모듈은 작업/선택 코드가 같다. 새 [Streamlit 대시보드와 실제 적용 계획](APPLICATION_READINESS_20261028.md)은 승인→이관 요청 준비까지 연결하며, 운영 Gold의 모델/DB 확인·적재·검증·사용 전환은 후속이다. 아래 개발 `publish`의 즉시 활성화를 운영 골드 절차 완료로 해석하지 않는다.

**연결 구현 당시 선택: 로컬 MAIN111 / `ontology-workflow-20261028-r1`.** 기술254조건(244테스트+실제 로컬 Oracle10), 선택 서비스의 OFF/ON미설정/ON빈DB 각42·총126확인을 통과했다. 모델은 모의 응답을 사용했으며 새 실제 모델 호출은 0회다. 온톨로지 데이터는 넣지 않았고 기본 OFF다.

## 구현한 흐름

1. **기존 에이전트 판단에서 생성 입력을 만든다.** `read_judgment.apply → ontology_work.capture.record_if_enabled`가 유효한 판단과 이미 읽고 검증한 원문만 모은다. 질문은 발견 이력이고 재사용 단위는 문서 판본·조항이다. 판단이 아직 없으면 만들지 않는다. 원문을 새로 읽거나 묶음을 자동 승인하지 않는다. `GENOS_ONTOLOGY_CAPTURE_ENABLED=on`일 때 기존 저널에 `ONTOLOGY_WORK_INPUT` 이벤트를 저장한다. 기본값은 off이며 RAG 사용 스위치와 별도다.
2. **Dataiku가 작업을 보관한다.** 기존 에이전트 이벤트를 읽는 `ingest_agent_events.py` Python 레시피가 입력 해시를 확인하고 생성 대기 목록에 넣는다. 작업 JSON은 Dataiku S3 관리 폴더의 `objects/<내용해시>.json`에 저장하며, SQL에는 상태·객체 해시·행위자 기록을 둔다. 재실행은 같은 입력을 중복 생성하지 않는다. GENOS가 S3에 접속하는 구조가 아니다.
3. **기존 화면에서 초안을 생성한다.** 온톨로지 관리 화면의 ‘저장된 판단으로 시나리오 생성’은 원문과 과거 판단을 GENOS 모델에 보내 명시적 레시피를 제안받는다. 판단은 발견 단서이고 원문보다 우선하지 않는다. 모델은 조건·측정·산정·효과·예외를 작성하고, 코드는 근거 인용·ID·의존·순환·미사용 요소 사유를 검사한다. 형식 보완은 한 번이며 전송 결과 불명이나 저장 실패를 모델 재생성으로 처리하지 않는다.
4. **사전에 조립하고 사람이 승인한다.** 각 경로의 조건·산정 방법·결과·미확인 사항·출처를 미리 펼쳐 화면에 보여준다. 수정은 새 작업 판본을 만들고 승인을 다시 받아야 한다. 검토자는 현재 원문과 조립된 내용을 보고 승인/반려한다. 승인자는 Dataiku의 브라우저 인증 정보로 식별하고 설정된 운영자·문서 범위를 확인한다. [Dataiku 인증 계약](https://doc.dataiku.com/dss/latest/webapps/security.html)을 따른다.
5. **DB에 게시한다.** 승인된 작업 판본·작업 해시·승인 영수증·예상 활성 순번을 대조한다. 원문을 다시 확인하고 사전 조립본·원문 좌표 색인·활성 포인터·게시 이벤트를 같은 트랜잭션으로 기록한다. 승인만으로 RAG에는 노출되지 않는다. 중복 게시 확인은 같은 영수증을 반환하고, 게시 중지나 롤백을 되돌리지 않는다.
6. **RAG는 도달한 원문에 연결된 게시본을 조회한다.** ON이고 DB 설정이 있을 때 기존 READ의 문서 판본·조항 좌표로 조회한다. 권한 밖 문서가 포함된 게시본은 본문을 가져오기 전에 제외한다. 현재 요청에 결속한 게시본은 요청 중 바꾸지 않는다. 원문·판본·범위·현재 근거번호를 다시 확인하고 A1에는 이미 조립된 경로를 전달한다. 요청 시 레시피 컴파일이나 법률 문장 생성은 하지 않는다.
7. **A1은 업무에 필요한 경로를 복수 선택한다.** MAIN110의 365자 지침·복수 선택·한 번 재선택·충분성 판단·기존 탐색 복귀를 유지한다. 여러 묶음의 같은 경로 ID는 게시 패키지 해시로 구분한다. 선택한 시나리오 문장을 기존 최종 발행 경로가 사용한다. 온톨로지 없음·조회 실패·맞는 경로 없음은 기존 RAG로 이어지며 사실 부족을 법령 탐색으로 지어내지 않는다.

## 상태와 책임

| 대상 | 상태/변화 | RAG에서 사용 |
|---|---|---|
| 입력 수집 | INPUT | 안 함 |
| 검증된 생성·수정 | DRAFT | 안 함 |
| 화면 승인 | APPROVED + 승인 영수증 | 게시 전에는 안 함 |
| 반려 | REJECTED | 해당 새 판본을 사용하지 않음 |
| DB 게시 | PUB 행 + HEAD 활성 게시 ID | ON인 새 요청부터 가능 |
| 새 초안 작성 | 새 REV, 기존 승인 상속 안 함 | 기존 활성 게시본은 유지 |
| 게시 중지·롤백 | HEAD 순번 증가, 이력 보존 | 새 요청의 게시본 변경 |
| 원문 판본·내용 변경 | 조회 불일치 또는 NEEDS_REVIEW | 해당 경로 사용 보류, 기존 탐색 |

구 문서의 `LOADED`는 이 개발 게시 구현에서는 **활성 게시 영수증이 존재하는 상태**로 판단한다. 운영 골드의 적재/검증/활성은 [별도 상태](STREAMLIT_DATAIKU_GOLD_UI_DESIGN_20261028.md)로 관리해야 하며 같은 의미로 사용하지 않는다. 작업 상태 문자열 하나로 승인과 적재를 혼동하지 않는다. 게시 중지의 적용은 새 요청부터이며 이미 진행 중인 요청의 게시본을 중간에 교체하지 않는다. 현재 원문 권한·무결성 검사는 계속 수행한다.

## 현재 자료구조

- `ontology-bundle-v0`: 원문 확보 범위와 판본을 나타내는 호환 계약. 누락됐던 파일을 서빙 목록에 명시적으로 결속한다.
- `ontology-work-v1`: 원문 목록, 판단과 발견 이력, 개념명. 원문마다 문서 ID·판본·조항·본문 해시를 가진다. 질문별 답변을 저장 단위로 삼지 않는다.
- `ontology-scenario-proposal-v1`: `components(id,text,requires,basis)`와 `paths(id,title,business_use,conditions,calculations,outcomes,notes)`, 미사용 요소 사유. 측정·산정 의미는 원문 근거와 명시적인 구성요소 의존으로 보존한다.
- `ontology-scenarios-v1`: 컴파일한 경로 본문, 구성요소, 필요 원문, 레시피/본문/패키지 해시, 승인 참조. 공통 요소의 의존을 데이터 구축 단계에서 펼친다. 숫자 계산을 실행하는 엔진은 아니다.
- `ontology-connection-v1`: 배포자가 지정하는 연결·작업 폴더·운영자 문서 범위. 사용자 질문이나 업로드 JSON으로 DB 접속 설정을 바꿀 수 없다. 비밀값은 환경 변수에 두며 설정 파일에는 환경 변수 이름만 둔다.

새 필드·새 테이블을 모델이 임의로 승인·생성하는 기능은 추가하지 않았다. 이번 MVP는 고정된 레시피 계약을 이용한다. 일반 스키마 제안과 메타 등록/DBA 신청 화면은 별도 후속 범위다.

## 개발계 테이블 설계

최신 물리 배치는 **원문·검색 `SIDDS.*_S`, 온톨로지·에이전트 `SIDDA.*_A`**다. 이전 운영 골드 설명은 논리적 승인 지식의 책임이며 개발계 owner와 혼용하지 않는다.

| 개발계 테이블 | 한 행·PK | 데이터 유형 | 용도/소비자 |
|---|---|---|---|
| `SIDDA.LGL_ONT_WORK_A` | 묶음 ID + 작업 REV | HISTORY | S3 작업 객체 해시·INPUT/DRAFT/APPROVED/REJECTED·승인자. 관리 화면과 게시자 |
| `SIDDA.LGL_ONT_EVT_A` | 이벤트 ID | HISTORY | 생성·승인·반려·게시·중지·롤백의 행위자·시각·영수증. 감사 조회 |
| `SIDDA.LGL_ONT_PUB_A` | 게시 ID | SNAPSHOT | 승인 판본의 사전 조립 패키지 및 해시. 원문 기반 불변 게시본 |
| `SIDDA.LGL_ONT_HEAD_A` | 묶음 ID | MASTER | 활성 게시 ID와 변경 순번. 트랜잭션 잠금·경쟁 변경 검출 |
| `SIDDA.LGL_ONT_ANC_A` | 게시 ID + 원문 좌표 해시 | SNAPSHOT | 문서 ID·판본·조항→게시본 조회 색인. RAG는 이 좌표로 점조회 |

[실행 DDL](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/01_CREATE_TABLES.sql) · [컬럼 정의 CSV](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/TABLE_COLUMNS.csv) · [매핑 계약](../../../../00_SYSTEM/SCHEMAS/ontology-db-mapping-v1.json).

[테이블 목록·Bizmeta·등록 대상 CSV](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/TABLE_BIZMETA.csv) · [테이블/컬럼 Description SQL](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/02_COMMENTS.sql) · [설치·연결 안내](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/GUIDE.txt).

테이블/컬럼 물리명은 30바이트 이내의 **명명 후보**다. 표준단어·용어·도메인·인포타입 대조, 메타 신청·승인, DBA 신청·생성은 미완료다. `VARCHAR2` 식별자는 BYTE 기준, 한국어 본문은 CLOB로 보존한다. 대상 ADB의 표준 타입/길이 승인을 대신하지 않는다. 승인 지식의 PUB/HEAD/ANC는 운영 골드 등록 검토 대상이고 WORK/EVT는 에이전트 운영기록이다.

공통 Bizmeta: 과제 식별은 A1 온톨로지(공식 메타 과제번호 별도 확인), 출처는 `SIDDS`의 게시된 문서 판본·조항 및 기존 에이전트 판단이다. Dataiku가 JSON 검토·컴파일·승인 후 원문을 재확인해 적재한다. 생성 시각은 사용자 작업/게시 시점이며 DB 이벤트의 UTC 시각으로 남긴다. 게시본은 삭제하지 않고 새 게시본/활성 포인터로 갱신한다. 현장 보존기간·개인정보 정책·업무 소유자는 운영 등록 시 확정한다. 날짜·임계값·산식은 JSON의 승인된 의미 데이터이며 이 다섯 테이블에서 재계산하지 않는다.

원문·검색 테이블을 복사하지 않는다. RAG 계정은 PUB/HEAD/ANC에 SELECT만 필요하며 WORK/EVT 쓰기 권한은 필요 없다. Dataiku 게시 계정에는 해당 작업·감사·게시·색인 INSERT와 상태/포인터 UPDATE가 필요하다. 원문 검증에는 허용된 `SIDDS` 문서·블록 조회가 필요하다. **GENOS 개발계의 SIDDA 접근은 현장 확인이 남아 있다.**

## 파일과 실행 진입점

- 런타임 및 관리자 공통 구현: `02_BACKEND/semantic_runtime/ontology_work/`.
- 기존 실행 진입점: `06_TOOLS/pipeline.py ontology-work`의 `enqueue / generate / draft / preview / approve / reject / publish / withdraw / status / ddl`.
- 기존 화면: `03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py`에서 연결 설정이 있으면 같은 폴더의 `app.py`로 들어간다. 기존 여섯 메뉴 중 온톨로지 관리·시뮬레이션만 실제 연결을 사용하고 다른 메뉴는 기존 시안이다. 설정이 없으면 기존 시안을 표시한다.
- RAG 진입점: `service._investigation_profile → ontology_context.acquire → ontology_work.runtime → Repository.lookup → ontology_assessment.project → ontology_scenario_runtime.assess`.
- Dataiku 입력: [Python 레시피](../../../../08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1/ingest_agent_events.py), 입력 열 `kind`, `payload_json`(또는 `payload`). 기존 허용된 에이전트 로그 내 `ONTOLOGY_WORK_INPUT` 이벤트만 소비한다.

## 실패와 재사용 범위

원문/인용/해시/권한 불일치는 차단한다. 오래된 화면에서 승인·게시하면 재조회해야 한다. 형식 보완만 최대 한 번, 실제 모델 전송은 시도당 한 번이다. 결과 불명은 실패 기록과 요청/응답을 보존하며 자동 재전송하지 않는다. DB 게시 확인이 끊기면 같은 판본·영수증으로 조회해 확인하며 임의의 새 ID로 재게시하지 않는다. RAG의 DB 조회는 요청 내 도달 좌표당 한 번이며 실패를 ‘지식 없음’으로 기록하지 않고 `UNAVAILABLE`로 남긴 뒤 기존 탐색으로 간다.

한 조회/요청에서 최대 8개 묶음, 기존 원문 확보 예산·문자 예산을 유지한다. 범위를 넘으면 제한을 기록하고 기존 탐색을 사용한다. 전체 연결관계를 전개하지 않고 승인된 레시피의 명시적 의존만 펼친다. DB에 자료가 많아져도 모든 원문·온톨로지를 GENOS 로컬 파일로 내려받지 않는다.

## 검증과 미확인 경계

최종 결과와 선택 MAIN은 [구현·검증 결과](../../../../09_ARTIFACTS/AUDITS/20261028-ontology-workflow-main/결과.txt)에 기록한다. ADR1156 SQLite 바인드 실패,1157 검증기 변수/화면 경로 실패,1158 수집 검증자료·로컬 Oracle 중지,1159 Oracle JSON 반환 차이는 그대로 보존한다.

기술 연결 검증의 모델은 모의 응답이며 신규 외부 모델 호출은 없다. 자동 생성 레시피의 법률적 타당성·보지 않은 질문에 대한 A1 정확도·전체 속도 개선을 인증하지 않는다. Dataiku 실제 S3·Flow 설치, 실제 GENOS 생성 모델 접속, SIDDA 권한, GENOS 리비전 배포는 현장 검증이 필요하다. 기존 운영 원문과 승인 온톨로지 데이터는 이 코드 반영에 포함하지 않는다.
