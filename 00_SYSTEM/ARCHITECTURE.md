# MAIN — 원문과 용어 기반 탐색

<!-- CURRENT_LOCAL_RAG_RELEASE -->
2026-10-21 사용자 “실제 LLM으로 다양한 범위·복수·제외 표현도 테스트해보고 문제없으면 메인에 반영하고 GENOS 반입용 ZIP도 만들어줘” 지시에 따라 **로컬 RAG MAIN99 / workflow1.20.8**을 선택했다. 릴리스는 `structured-selection-20261021-r1`, 정본은 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이다. 자연어 분류를 LLM에 맡기는 기존 수정과 구조화 범위·복수·제외 선택을 통합했다. 초기·후속 범위 판단을 필수 출력하고 저장된 조·항·호·목 집합과 명시적 비교 연산을 실행한다. 적용 가정과 원문 제외를 구분하며 권한·원문·상태·해시 검사를 유지한다. ADR0972 후보16/32와 ADR0973 후보31/32는 거절 기록으로 보존했다. 최종 ADR0974 신규 합성32사례에서 기존1/32·후보32/32, 실제Qwen64요청·63응답(기준 HTTP429 1회 보존); 전체 답변 정확도·현장 성능 인증은 아니다. 최종199계약, 후보/작업/선택 서비스 HEALTH와419파일 결속을 확인했다. 데이터·모델 프로필·검색 선택 유지. 무거운 기존 임베딩 작업과 전체 원문 로딩을 병렬 실행하지 않았으며 실제 원문 읽기는 같은 코드의 합성 API와 모델 경계 검사로 확인했다. `VALIDATED_ADR_PROMOTION`, 품질 우회 없음, `quality_certified=false`. GENOS ZIP 설치 검사와 현장 반입·배포는 별도 상태이며 Git commit/push 미수행. 이전 전역 graph·의미 오류는 해결한 것으로 보지 않는다. 전환·복원: `09_ARTIFACTS/AUDITS/20261021-structured-selection-main/RESULT.txt`.
<!-- /CURRENT_LOCAL_RAG_RELEASE -->

2026-10-21 **작업 코드에 업무 검토 지식 관리·RAG 안내 연결을 추가했다.** `lawrag/legal_knowledge`와 같은 앱의 `/legal-knowledge/`, `/v1/legal-knowledge`가 공통 계약·Oracle 주입 포트를 사용한다. 관리 기본값 false, 소비 off이며 AD는 계속 비활성이다. 초안/게시/CAS/멱등 receipt와 기존 저널 참조를 연결했다. 실제 Oracle·GENOS 인증 주입, 실모델 효과·MAIN 승격은 미확인/미수행이다. 전체 설계 중 자동 생략·복합 계산·전역 영향·실행 역색인은 남았다. [구현 범위·연결·복구](../07_DOCS/REFERENCE/REPORTS/CM_KNOWLEDGE_SYSTEM_DESIGN_20261020/IMPLEMENTATION_20261021.md).

아래는 이전 구현·검증 시점의 기록이다. 당시 MAIN 미반영 표시는 위 현재 선택 상태로 대체된다.

2026-10-20 **작업 코드**의 대사 workflow는 **1.19.2**다. [research_state.py](../02_BACKEND/semantic_runtime/research_state.py)의 `ResearchLedger`가 부모의 조사 필요·시도·검토·횟수, `NativeResearchTasks`가 자식 실행 기록, `OriginalProgress`가 원문 확보 진전을 담당한다. 기존 checkpoint/journal이 저장 정본이며 호출·권한·트랜잭션은 기존 실행기가 담당한다. 새 원문 ID가 없어도 새 단서·조사 결과가 생기면 부모가 한 번 검토한다. 기존 부족 해소는 명시적 `need_resolution=RESOLVED`와 원문 인용·이유가 필요하며 빈 `missing`만으로 해소하지 않는다. 복구 선택은 완료된 행동의 상태 버전과 새로 노출된 실제 대상을 기준으로 최대 3회 연결하며, 동일 대상·변조·낡은 상태·누적 예산 검사를 유지한다. 원문 전달과 법률적 충분성 판단은 분리한다.

최종 후보 573계약, 작업 코드의 일반 회귀 33검사, 후보·작업의 실제 원문/서비스 연결 검사가 통과했다. 전체 389파일이 후보와 일치한다. **선택 로컬 MAIN은 generation90 / workflow1.16.0을 유지**한다. 실제 비용 관찰에는 제공자429·호출 중단·사용량 누락이 있어 전체 비용과 최종 후보의 실제 모델 효과를 확정하지 않았다. GENOS 미반영. [현재 통합·한계·복구 기록](../09_ARTIFACTS/AUDITS/20261020-research-decision-main/RESULT.txt), [이전 1.18 상태 소유자 리팩터링](../09_ARTIFACTS/AUDITS/20261020-research-state-refactor/RESULT.txt).

앞선 **1.17.0** 작업은 조사 필요를 쟁점·항목·내외규별로 유지하고 부모의 조사 목적·과거 시도·근거 검토를 자식 입력 검증과 원문 조사 화면까지 연결했다. 후보 발견과 새 원문 구간 확보를 구분하며 같은 근거의 미확보 설명 변경 및 표시 이름만 다른 동일 조회를 재사용한다. 원문 전달·미확인 상태·누적 예산·재개 기록을 유지한다. [1.17 통합·검사 기록](../09_ARTIFACTS/AUDITS/20261020-research-continuity/RESULT.txt).

## 전체 인프라 — 사용자 확인 2026-10-16

최종 목표의 Legal Agent·Legal Wiki·Legal Ontology 역할, 저장 값, Oracle 논리 구조와 구현 순서는
[상세 아키텍처](../07_DOCS/REFERENCE/ARCHITECTURE/LEGAL_KNOWLEDGE_INFRA_20261017/ARCHITECTURE.md)를 따른다.
2026-10-17 목표 설계이며 현재 연결·선택 릴리스·GENOS 현장 상태를 구분한다.

사용자가 설명한 전체 인프라의 기준이다. **GENOS는 채팅과 에이전트 백엔드 실행,
데이터플랫폼의 Dataiku는 데이터 수집·가공·적재 흐름, Dataiku에 연결된 Oracle DB는
법령·용어 등의 지식그래프와 온톨로지 저장을 담당한다.** 지식그래프와 온톨로지는
Oracle의 RDB 테이블에 그래프 형태로 표현되어 있으며, GENOS 에이전트는 이 데이터를
쿼리로 조회해 RAG를 수행한다.

| 흐름 | 입력 → 처리 → 소비자 |
|---|---|
| 사용자 질의 | 사용자 → GENOS 채팅 앱 → GENOS 백엔드 에이전트 → Oracle의 지식그래프·온톨로지 조회 → RAG 답변 → GENOS 채팅 앱 |
| 외규 갱신 | Dataiku의 매일 배치 → API 중계서버 → 법제처 API에 신규·갱신 데이터 확인 → 변경 자료 수집 → 구조적 파싱·VLM 파싱으로 구조 분해 → 색인 → Oracle 지식그래프 적재·갱신 |
| 내규 반입 | 현업이 데이터 포탈에 내규 업로드 → Dataiku 연결·수집 → 구조적 파싱 → 색인·Oracle 지식그래프 적재 |

외규는 법제처 API의 변경 확인으로, 내규는 현업의 데이터 포탈 업로드로 유입된다.
두 경로는 구조화·색인·지식그래프 적재 후 GENOS의 RAG 조회로 이어진다.
이 인프라는 아래 MAIN의 입력·구조화·용어집/문서 연결·색인·RAG·피드백 단계가
배치되는 환경이며, MAIN의 단계별 책임과 계약을 대체하지 않는다.

확인 출처는 **2026-10-16 사용자의 전체 인프라 설명**이다. 직접 SQL 접속인지 조회 API를
거치는지, 실제 테이블·스키마, 파서/VLM의 실행 위치와 배포 리비전은 이번 설명에서
지정하지 않았다. 여기서 임의로 정하지 않는다. 아래의 SQLite·NFS generation·로컬 릴리스
기록은 각각의 구현·반입·검증 범위이며, Oracle 중심 전체 인프라를 대신하는 설명으로
사용하지 않는다. 이번 기록은 현장 접속·배치 실행·Oracle 연동을 새로 검증했다는 뜻이 아니다.

### 서빙 데이터 저장 금지 — 사용자 명시 2026-10-19

사용자가 "서빙쪽에는 데이터를 저장하면 안됨"을 명시했다. GENOS 코드서빙에 원문·용어·관계·색인을 전체 복제하거나 로컬 SQLite/파일/영속 볼륨에 보관하는 구조를 최종 운영안으로 사용하지 않는다. 서빙은 Oracle 또는 승인된 조회 API에 조건·판본·접근 범위를 전달하고, 필요한 결과만 받아 요청 처리 중 일시적으로 사용한다. 요청 간 재사용을 위한 데이터 캐시도 서빙 내부에 추가하지 않는다.

기본 캐시는 Oracle DB 내부의 데이터 블록 캐시이며 DB 운영 영역이다. 별도 조회 결과 캐시는 성능 측정으로 필요성이 확인될 때 서빙 밖의 데이터 계층에서 검토하고, 데이터 버전·조회 조건·권한 범위·갱신/무효화 정책을 결속한다. Redis 등 특정 제품의 설치·사용 가능성은 확인되지 않았다. 서빙의 대화/실행 상태 보존도 필요한 범위를 외부 저장소에 연결해야 하며, 기존 로컬 상태 소비자는 별도 점검 대상이다.

Dataiku는 수집·구조화·용어 연결·색인·검증한 버전 게시를 담당하고, Oracle에서 검색·관계 탐색·원문 조회가 가능하도록 테이블과 조회 경로를 연결해야 한다. SQLite 색인 파일을 Oracle 자산 테이블에 보관한 것만으로 Oracle 직접 검색이 구현된 것은 아니다. 갱신은 새 버전의 게시 완료 후 신규 요청이 그 버전을 선택하고, 진행 중인 요청의 버전 결속을 유지하는 방향으로 설계한다.

**작업 코드 전환 — 2026-10-19:** `service.py`의 `DP=oracle`은 `oracle_query_service.Factory`로 연결되어 Oracle 원문·검색·관계를 요청별로 조회한다. 기존 `oracle_dp.resolve()` 전체 복원 유틸리티는 서빙에서 호출하지 않으며 SQLite 모드는 보존한다. Dataiku가 게시한 불변 query release와 활성 채널 revision을 요청 시작에 고정한다. 원문·색인 데이터의 파일/SQLite 복제와 요청 간 데이터 캐시는 없고, 실행 이력·로그는 명시한 외부 NFS/CIFS를 사용한다. 외부 마운트가 없으면 로컬에 쓰지 않고 실패한다. 로컬 Oracle 23과 모의 모델로 서비스 연결을 검사했으며, 실제 현장 ORDS·NFS·모델·배포 성능은 미검증이다. Oracle STATE 테이블의 CAS 포트도 제공하지만 기존 이력 소비자는 NFS에 유지한다. 이 작업은 선택 포인터·GENOS 리비전을 변경하지 않았다. 완료 시 별도 ADR-0917의 MAIN88 선택을 확인했으며 그 릴리스에는 새 Oracle 조회 모듈이 없다. [구현/설정/검증 범위](../09_ARTIFACTS/AUDITS/20261019-oracle-query/IMPLEMENTATION_UTF8.txt).

## 로컬 구현·릴리스와 검증 이력

2026-10-20 현행 로컬 RAG 서빙은 **MAIN90 `durable-research-review-20261020-r1` / workflow 1.16.0**다. 질문에 근거한 조사 항목, 미확보 조사 보존·추가 조사 연결, 새 근거 갱신 형식 정규화와 RP 연결 문서 등록 수정을 통합했다. 분리 stage와 선택 릴리스의 387파일은 검증 후보와 동일하다. 작업 코드에는 같은 40파일을 통합하고 별도 화면 작업 2파일을 보존했다. stage/작업 각각 87개 계약·API·화면 검사와 실제 선택 서비스의 12개 연결 검사를 통과했다. 데이터·모델 설정은 MAIN89와 같다. 이전 4문항 결과의 RP 필수 근거 미확보와 레버리지 현재 문장 직접 인용 문제는 남아 있다. 해당 한계를 설명한 뒤 받은 사용자 지시에 따른 `USER_DIRECTED_CUTOVER`이며 `quality_certified=false`다. ADR-0936의 Rejected 기록은 유지했다. 이번 새 모델 호출은 0회이고 GENOS 배포·Git main 병합은 별도다. [반영·검증·원복](../09_ARTIFACTS/AUDITS/20261020-durable-research-main/RESULT.txt).

2026-10-16 이전 로컬 RAG 서빙은 **MAIN81 `source-return-comparison-20261016-r1` / workflow 1.8.0**다. 지정한 짧은 내규 전문 읽기, 기존 명시 참조 연결 우선 조회, 대사 자식의 정상 원문 반환, 쟁점별 단일 비교표를 구현했다. 불확실성은 의견·미확보로 표시하고 원문·권한·해시·상태 검사는 유지한다. 검증 후보와 선택344파일 동일, 후보/작업 각각76검사와 활성 서비스13검사 통과. 개발 후보의 실제 Qwen 대사는9호출·510초·2비교행을 반환했다. 이후 원장 종료·SELECT 스키마 보완본은 API·실제 데이터 소비자로 검증했으며 전체 모델 질의를 다시 호출하지 않았다. 법률 정답 인증·GENOS 배포는 별도다. [구현·검증·한계·원복](../09_ARTIFACTS/AUDITS/20261016-risk-comparison-source-return/RESULT.txt).

2026-10-16 이전 로컬 RAG 서빙 **MAIN80 `direct-comparison-20261016-r1` / workflow1.7.0**다. 항목 검토의 원문을 바로 비교로 전달하고 별도 BASIS 승인 호출을 제거했다. 조사 관리 필드와 별도 채택 표시가 유효한 읽기·종료를 막지 않으며, 조사 미완료에서도 실제 원문과 실패 상태를 함께 보존한다. 후보/작업 회귀113개, 새 기술 상태168개, 양측 기존 회귀84개, 활성 서비스13개 통과. 최종 선택 서비스의 새 검색부터 실제 대사를 실행해19호출·809초에4항목·2비교행을 반환했다. 외규 정리 실패에도52읽은 원문을 보존해 비교를 끝냈으며, 미확인 자료는partial로 표시했다. 법률 정답 인증은 아니다. GENOS 미반영. [검증·한계·원복](../09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/LIVE_COMPARISON_MAIN80.txt).

2026-10-16 이전 로컬 RAG 서빙 **MAIN79 `llm-comparison-judgment-20261016-r1` / workflow 1.5.2**다. 비교의 의미 판단은 LLM에 맡기고, 미확보 설명·표현 차이·수치 차원 목록과 메타데이터의 부족을 이유로 비교 전체를 거절하던 검사를 줄였다. 위치에 따른 도구·근거 연결은 시스템이 조립하고 실제 인용·권한·해시·상태 보존은 검사한다. 후보와 선택342파일 동일, 작업 회귀53개·기술 상태84개·활성 서비스13개를 확인했다. 알려진 원문 묶음의 새 모델 응답1건을 보존했으며, 전체 대사 품질·검색 범위 문제는 미검증/미해결이다. GENOS 미반영. [반영·검증·한계·원복](../09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/LLM_JUDGMENT_MAIN79.txt).

2026-10-16 이전 로컬 RAG 서빙 **MAIN77 `comparison-task-guidance-20261016-r1` / workflow 1.4.2**다. 비교 항목 설정·양방향 조사 과제·부족 항목 조사·성공 근거 보존·자식 요청 재개·부분 결과 반환을 기존 RAG에 연결했다. 최종 검증 후보와 선택된342파일이 같고, 통합 후 API58개와 활성 서비스13개를 확인했다. 공통 회귀는 양쪽208통과·동일6실패다. 실제 Qwen 대사는429로 미완료였으며, 그 실패 원장 재생에서 확보 외규6근거의 반환을 확인했다. 법률 정확도 개선률은 미인증이고 GENOS는 미반영이다. [구현·검증·복원 기록](../09_ARTIFACTS/AUDITS/20261016-risk-comparison-task-guidance/IMPLEMENTATION.txt).

2026-10-15의 이전 로컬 RAG **MAIN75 `system-owned-workflow-20261015-r1`**는 대사의 질문 재해석·인용 복사·고정 필드·정의 원문 읽기·자식 문장화·보류 재판단·행 저장/재개·최종 근거 표시를 시스템에 맡긴다. 의미 판단은 모델에 유지한다. 후보269/신규기술8/활성서비스12 검사, 선택338파일 동일. 전체 Qwen 유동성 질의는 partial·0행이며 수정한 BASIS 재생의3짝/3보류행과 구분한다. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification/MAIN_RESULT.txt). GENOS 미반영.

2026-10-15 이전 로컬 RAG **MAIN74 `workflow-adopted-evidence-20261015-r1`**은 대사 자식의 채택 원문만 전달하고 현재 판단·조건 의존성·입력 한도·비교·표시를 연결한다. MAIN72 최초 정의 탐색과 MAIN73 최신 선택을 유지한다. 기능278계약/UI4/실제 서비스12 검사 통과. 실제 Qwen 유동성 질의는 partial·비교0행으로 미해결이며 기능 검증과 구분한다. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/MAIN_RESULT.txt). GENOS 미반영.

2026-10-15 이전 로컬 RAG **MAIN73 `latest-document-selection-20261015-r1`**은 승인 파일명 예외와 최신 표시를 RAW 구조화 입력 및 기존 세대 검색·탐색에 연결한다. 원본 세대는 보존하고 선택표/네이티브 메타데이터를 검증한다. MAIN72의 최초 정의 탐색을 유지하며 로컬 내규11개 모두 최신 검색 대상으로 마킹했다. [실제 연결·검증·원복](../04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search/MAIN_RESULT.txt). GENOS 현장 적용은 별도다.

2026-10-15 이전 로컬 RAG **MAIN72 `definition-entry-navigation-20261015-r1`**은 질문에 일치하는 저장 정의와 명시 참조 조문을 첫 탐색 읽기 후보에 제공한다. 정의·참조 원문/해시·권한을 검사하며 기존 전문검색을 보존한다. 외부 제공자 문법의 반복 행동 조건을 줄이고 서버의 원래 검증을 유지했다. 계약516건, 후보/활성 실제 서비스8건씩, 선택329파일 hash 확인. 공개 유동성 사례에서 첫 선택으로 정의와 제3-24조의4제2항을 읽고 최종 답변에 포함했다. 알려진 사례이며 일반 답변 정확도 미인증, GENOS 미배포. [검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding/MAIN_RESULT.txt).

2026-10-15 이전 로컬 RAG **MAIN71 `risk-committee-team-metadata-20261015-r1`**은 MAIN70 코드·검색·모델을 유지하고, 추가 준칙의 팀 메타데이터 위치를 교정했다. 위험관리팀 선택442→443, 대사 내규 자식10→11이며 실제 서비스에서 목록·원문·검색·대사 scope를 확인했다. 전체 원문 행 대조,23기술검사 및 선택328파일 hash 확인 완료. 유동성 정의 연결의 최초 검색 미사용과 Parasail schema 크기 오류는 미수정이다. GENOS 미배포. [검증·진단·원복](../04_EXPERIMENTS/ADR/ADR-0792-risk-committee-team-metadata/MAIN_RESULT.txt).

2026-10-15 이전 로컬 RAG **MAIN70 `risk-rag-orchestration-20261015-r3`**는 대사 질문을 기존 RAG에 `내규:`/`외규:`로 각각 전달하고 답변·검증 원문·조사 기록을 받아 판단한다. 정정한 위험관리위원회운영준칙1문서와 명명 정의·참조635건을 추가한 세대를 선택했다. 부모 전체회귀1187건, 후속 재시작42건, 통합12건과 실제 fresh service.service 프로세스2개의 동일 요청 재사용을 확인했다. 최초 MAIN68의 재시작 결함은 즉시 롤백 후 수정했다. Qwen 실질문은 partial이며 필요한 내규와 정답 조문을 놓친 문제가 남아 있다. GENOS는 미배포다. [배선·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0791-risk-rag-restart-binding/MAIN_RESULT.txt).

2026-10-15 명시 인용을 포함한 명명 정의는 기존 SQLite에 증분 보강할 수 있다. `pipeline.py document-release augment-definitions`가 원문·FTS를 재사용해 정의/참조 연결만 추가하며 기존 정의 조회가 소비한다. 최종 635건 추가, 계약12통과 및 MAIN67 코드의 도구/API 연결 확인. 당시 갱신본은 미활성화였으며 현재 결합 세대 선택은 위 MAIN72 기록을 따른다. 일반 검색 우선 회수 개선은 별도다. [결과](../09_ARTIFACTS/AUDITS/20261015-naming-definition-append/RESULT.txt).

2026-10-15 이전 구현 이력: **작업 코드에 Risk팀 대사 workflow를 통합**했다(ADR-0785). `대사:` → 공통 `workflow` 실행부 → `risk_team_compare_workflow` → 기존 RAG 원문·정의·참조 도구로 연결하며, 관계 확인·내용 비교와 사유별 복귀를 분리한다. 새 DOCX를 포함한1547문서 세대와 같은 코드로 로컬 서비스 경로를 확인했다. 후보500계약·추가 v6검사1건, 통합 후60계약 통과. 활성 MAIN66과 GENOS는 변경하지 않았고 실제 내부 모델 법률 판단은 미검증이다. [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md), [구현·검증·한계](../09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow/IMPLEMENTATION_RESULT.txt).

2026-10-15 이전 로컬 RAG **MAIN67 `navigation-delivery-recovery-20261015-r1`**에 원문 전달 기록과 채택 판단 분리, FINISH 교정 계약, 쟁점별 채택 검증 일치, 실패한 동일 조사 재호출 차단을 반영했다. 100상태 포함1113회귀 통과, 동결/선택308파일과 실제 WSL service.service를 확인했다. Qwen 보조4회는 모두 미확보 쟁점 경고가 남았으며 모델 판단 개선을 입증하지 않는다. 관련7작업 소스만 통합하고 다른 작업은 보존했다. GENOS는 미배포다. [결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0788-navigation-finish-delivery-recovery/MAIN_RESULT.txt).

2026-10-15 이전 로컬 RAG **MAIN66 `length-recovery-20261015-r1`**에 기존4실패·길이복구·선택 로컬 어댑터의 종료원인 보존을 통합했다.296유한 계약·896회귀 모두 통과, 작업/검증/선택308파일과 실제 WSL service.service를 확인했다. 정상6400 유지·법령탐색 length 수정1회만12800이며 GENOS 현장 재질의 성공은 미확인이다. [결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0784-length-adapter-parity/MAIN_RESULT.txt).

2026-10-14 당시 로컬 RAG **MAIN65 `length-recovery-20261014-r2`**는 경로 별칭도 실제 해석된 의존 경로로 검사해 기존 연구 코드 차단을 보존한다.264유한 계약·887회귀 모두 통과, 작업/검증/선택308파일과 실제 WSL service.service를 확인했다. MAIN64 다음의 검증 이력이며 현재 선택은 위 MAIN72이다. [결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0783-length-recovery-path-integrity/MAIN_RESULT.txt).

2026-10-14 중간 로컬 RAG MAIN64는 `length-recovery-20261014-r1`(포인터 generation **64**)이다. 법령 탐색 length 수정1회에만 명시12800토큰을 허용하고 정상6400·원문·모델·검색 설정을 유지한다. 기존4계약실패와 host 경로 오분류를 수정했다. 동결256계약·887회귀 모두 통과, 작업/검증/선택308파일 및 실제 WSL service.service를 확인했다. GENOS 현장 재질의는 미확인이다. [결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0782-length-recovery-final/MAIN_RESULT.txt).

2026-10-14 이전 로컬 RAG MAIN63은 `tool-recovery-20261014-r1`(포인터 generation **63**)이다. MAIN62의 원문·모델·검색 정책을 보존하면서 도구 실패 P1~P3와 이전 구조 부모 읽기·의존 조사·도구 노출 수정을 통합했다. 동결 정책5994조합·회귀842통과/기존4실패, 작업/검증/선택306파일과 실제 WSL `service.service` HEALTH/검색/목록/실패 경계를 확인했다. 전역 graph는 과거8오류 유지·추가0이다. GENOS 배포·내부 모델·사진 질문의 현장 재실행은 별도다. [MAIN 반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main/MAIN_RESULT.txt).

2026-10-14 MAIN61 전환 당시 로컬 RAG MAIN은 `public-failure-guidance-20261014-r1`(포인터 generation **61**)이다. MAIN60의 모델·검색·데이터를 유지하며 검토 미완료와 기술 예외를 일관된 법률 검토 안내로 표시하고 오류 코드·실패 상태·요청 ID를 보존한다. 합성 프로토콜2400조합·관련298계약, 선택301파일과 실제 WSL `service.service` 정상조회/503/timeout/limit 경계를 확인했다. [MAIN 반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0775-public-failure-main/MAIN_RESULT.txt). GENOS 현장 배포/편집기 저장/화면은 별도다.

2026-10-13 MAIN60 전환 당시 로컬 RAG MAIN은 `assessment-gap-action-20261013-r1`(포인터 generation **60**)다. MAIN59의 정상 완료 shortcut 정책과 원문 세대를 보존하며 원문 gap의 잘못된 사실 질문 행동만 기존 조사로 연결한다. 고정 합성952조합·관련353계약, 작업/검증/선택301파일 및 실제 WSL `service.service` HEALTH/RAG_SEARCH200을 확인했다. [실패·충돌 필수 코딩 지침](../07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md)은 전역 구현 완료를 뜻하지 않는다. GENOS 현장 배포와 기존 복구4건은 별도다. [반영·근거·롤백](../04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main/MAIN_RESULT.txt).

2026-10-13 MAIN58 전환 당시 로컬 RAG MAIN은 `source-provider-20261013-r2`(포인터 generation **58**)다. MAIN57의 원문·검색·모델·진단 저장을 유지하고 기관별 한국어 법령 번호 목록과 `internal → 내부 규정` 표시를 연결했다. 합성24조합과 후보/작업 각각97계약, 검증후보·선택297파일, 실제 `service.service` HEALTH/RAG_SEARCH200과 표시 소비자를 확인했다. 별도 작업의 모델 전송 수정은 작업 트리에 보존했으나 이번 MAIN58에는 섞지 않았다. GENOS 편집기 R2는 삼성메일로 발송했고 현장 저장/화면 검증은 별도다. [반영·근거·롤백](../04_EXPERIMENTS/ADR/ADR-0772-source-provider-display/MAIN_RESULT.md).

2026-10-13 MAIN57 전환 당시 로컬 RAG MAIN은 `source-cards-20261013-r1`(포인터 generation **57**)이다. MAIN56의 모델·검색·원문·답변 토큰 스트리밍을 보존하면서 법령 경로가 실제 표시 소비자에 전달되도록 연결하고, 경로별 줄바꿈과 연속 원문 확인의 단일 카드 출력을 반영했다. 합성 경계24조합·후보/작업 각각48계약, 작업/검증/선택297파일과 실제 service.service HEALTH/RAG_SEARCH200 및 선택된 원문12개/카드1개를 확인했다. GENOS 편집기 R1을 삼성메일로 발송했으며 편집기 저장/현장 화면은 별도다. [반영·발송·한계·롤백](../04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring/MAIN_RESULT.md).

2026-10-13 MAIN56 전환 당시 로컬 RAG MAIN은 `token-stream-20261013-r1`(포인터 generation **56**)이다. MAIN54의 bounded recall·shortcut·원문을 보존한 설명형 답변 MAIN55에 최종 텍스트 delta 도착 즉시 송신을 연결했다. 문장/문단 완료를 기다리지 않으며 누적 본문은 정본과 일치한다. 전송 경계40조합·직접142계약·선택 스트리밍64계약, 작업/검증/선택297파일과 실제 service.service 결속을 확인했다. 외부 공개 transport는 buffered이며 내부 streaming은 모의 경로로 검증했다. GENOS R2 ZIP은 삼성메일로 발송했으며 현장 배포/화면/내부 모델 검증은 별도다. [반영·AD·발송·한계·롤백](../04_EXPERIMENTS/ADR/ADR-0770-token-answer-stream/MAIN_RESULT.md).

2026-10-13 MAIN54 전환 당시 로컬 RAG MAIN은 `bounded-wiki-recall-20261013-r1`(포인터 generation **54**)이다. MAIN53 위에 저장 시 검색 카드 구축 → 질문당 단회·최대3개 회수 → 기존 판단에서 관련성 선택 → 현재 원문 재확인 경로를 통합했다. 별도 위키 모델 호출0이며 불일치/오류 시 기존 조사를 계속한다. 기존 51개 기록을 원본 변경 없이 색인했다. 새22검사 통과·관련 회귀193검사 신규실패0(기존25실패), 작업/검증/선택296파일 및 실제 service.service 결속 확인. 내부CM은 외부 모델에 노출하지 않고 GENOS 현장 검증은 별도다. [반영·결과·한계·원복](../04_EXPERIMENTS/ADR/ADR-0768-bounded-wiki-public-qualification/MAIN_RESULT.md).

2026-10-13 MAIN53 전환 당시 로컬 RAG MAIN은 `focused-rules-20261013-r1`(포인터 generation **53**)이다. 실제 입력의 가역 ID·카드 압축, 사용자 요구에 연결된 추가 탐색, 제목 부재 진단, 완료된 검색의 실제 진전 반영·원문 양태와 단일 규정 출력을 MAIN52 위에 통합했다. 새 공개1문항 정상 완료 쌍 입력 17.1% 감소, 핵심161검사·전체432검사 신규회귀0(기존15실패), 작업/검증/선택295파일과 실제 service.service 결속을 확인했다. 원문 세대와 캐시는 유지하며 GENOS 현장 배포는 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0761-scoped-title-public-qualification/MAIN_RESULT.md).

2026-10-12 MAIN52 전환 당시 로컬 RAG MAIN은 `compact-navigation-20261012-r1`(포인터 generation **52**)이다. 직접 원문 우선 안내·유효한 구조 필터 결속·외부 스키마 참조 공유·중복 원문 메타데이터 축소를 MAIN51 위에 통합했다. 공개3문항 근거 응답1→3, 전체 입력14.7% 감소지만 기준 실패2건을 포함하며 정상 완료 쌍의 절감은0.43%다. 핵심59검사·전체330검사 신규회귀0(기존15실패), 작업/검증/선택290파일과 실제 service.service binding을 확인했다. 별도 추가 압축729/730은 기준 미달·외부429로 미반영했다. 원문 세대는 유지하며 GENOS 현장은 별도다. [반영·한계·원복](../04_EXPERIMENTS/ADR/ADR-0728-navigation-input-public-qualification/MAIN_RESULT.md).

2026-10-12 MAIN51 전환 당시 로컬 RAG MAIN은 `source-recovery-20261012-r1`(포인터 generation **51**)이다. 정확한 부족 대상·현재 원문 재사용·일시적 도구 실패 복구·부분 묶음 읽기 재개·요청 경계와 판단 내용 보존을 기존 MAIN50에 통합했다. 신규40계약과 작업/후보311검사 대비 신규 회귀0(기존15실패 유지), 공개 신규2문항 비교와 실제 service.service 선택, 서빙289파일 일치를 확인했다. 구조/fulltext는 선택형이며 원문 세대는 유지한다. 의미적 검색 판단·전체 CM51·GENOS 현장은 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification/MAIN_RESULT.md).

2026-10-09 전환 당시 로컬 RAG MAIN은 `compact-input-20261009-r1`(포인터 generation **50**)이다. MAIN49 위에 미선택 법령 상세 지연 제공, 간결한 탐색 지침·전체 행동 이력, 탐색 원문 중복 축소를 연결했다. 신규 공개3질문 입력 38.3% 감소·모델 12→12회, 알려진2질문·후보/작업288계약과 실제 service.service 선택을 확인했다. 원문 세대는 유지하고 구조/fulltext는 계속 선택형 도구다. GENOS 배포는 별도다. [실제 반영·검증·롤백](../04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context/MAIN_RESULT.md).

2026-10-09 MAIN49 전환 당시 로컬 RAG MAIN은 `grounded-entry-20261009-r1`(포인터 generation **49**)이다. MAIN48의 표시·계측·판단·원문 세대 위에 새 질문 앞단 통합, 실제 법령 제목 힌트, 모델이 선택하는 구조/fulltext 검색을 연결했다. 후보·작업271계약과 공개3질문 paired 검증, 작업·검증·선택287파일 및 실제 service.service 선택을 확인했다. 이유/행동 불일치와 난이도별 예산은 후속이며 GENOS 배포는 별도다. [실제 반영·검증·롤백](../04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main/MAIN_RESULT.md).

2026-10-09 MAIN48 전환 당시 로컬 RAG MAIN은 `compact-progress-20261009-r1`(포인터 generation **48**)이다. MAIN47의 구조 우선 검색·판단·원문 세대를 유지하면서 사용자 진행 표시를 최대5단계로 압축하고 최종 접힘에 실제 모델 전송 시도별 시간·횟수와 서버 요청 시간을 연결했다. 전체 내부 로그는 보존한다. 계약233개와 합성 표시20조합, 작업·검증·선택285파일 해시와 실제 서비스 선택을 확인했다. 신규 외부 모델 호출0회이며 GENOS 현장 배포는 별도다. [검증·선택·롤백](../04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics/MAIN_RESULT.md).

2026-10-09 MAIN47 전환 당시 로컬 RAG MAIN은 `structured-judgment-20261009-r1`(포인터 generation **47**)이다. MAIN46의 원문·색인·폴더 세대를 보존하면서 구조 우선 검색 → 선택한 문서/하위 구조 안의 본문 검색, 승인 판단·조건/예외 계약, 선택 범위 묶음 읽기·재개, 로그와 공개 표시 분리를 통합했다. 새 공개3문항과 알려진2회귀를 동일 코드로 검증했고 작업·검증 후보·선택 릴리스의 서빙284파일 해시와 실제 `service.service` HEALTH/RAG_SEARCH binding을 확인했다. 전체 MAIN의 상위 단계와 GENOS 현장 배포는 별도다. [검증·실제 선택·롤백](../04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout/MAIN_RESULT.md).

2026-10-08 전환 당시 로컬 RAG MAIN은 `native-cm-serving-20261008-r1`(포인터 generation **46**)이다. 선택 원문은 `term-source-8729f978a28924cb8c5b`의 1,546문서다. 모델 없이 구조화한 팀 RAW 1,544문서에 CM 필수 공개 원문 2개를 명시적으로 보충했고, compact-v2/navigation-v7/unit 전문 색인 255,777단위를 선택했다. CM 공통 51문항의 근거 98개를 21문서의 새 조문·span에 결속하고, 원문 해시·문서 권한·개인 이력 보존을 확인했다. 실제 루트 `service.service`에서 frozen 코드와 새 데이터 선택, HEALTH, 원문 읽기를 검증했다. 검증의 모델 호출은 0회이며 답변 품질 인증과 GENOS 배포는 수행하지 않았다. 외부 모델의 공개 원문 범위는 기존 승인 원문과 같은 65문서이며 내부 CM 질문의 반출 제한은 유지한다. [활성 선택·코드·데이터·CM·롤백 기록](../09_ARTIFACTS/AUDITS/20261008-native-cm-serving/completion.json).

아래 MAIN45 설명은 이전 선택 상태의 기록이다. 병행 판단 루프·통신 코드의 미통합 상태에 관한 설명은 MAIN46 전환 당시 기록이며, 현재 MAIN48의 선별 반영 범위는 위 완료 기록을 따른다.

2026-10-07 현재 로컬 RAG MAIN은 `session-runtime-v6-20261007-r1`(generation **45**)다. 세션 멀티턴에서 user_wiki 생성·조회·개인 질문 이력의 자동 모델 입력과 별도 signing을 제거했다. 세션 상태·shortcut 공통 저장소·legal_wiki 컴파일과 재구축·기존 플랫폼/API 경계는 유지한다. 후보/선택268파일 및 실제 새 service.service의 binding을 확인했고 신규30개·동일 회귀88개와 유지 계약35개를 통과했다. 병행 작업의 미선택 latency/engine 변경은 보존했으며 해당 pending 작업까지 승격한 것은 아니다. 원문 세대와 이전 릴리스·개인 위키 기록은 보존한다. GENOS 현장 배포는 별도다. [변경·실제 연결·원복](../04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing/MAIN_RESULT.md).

2026-10-07 루트 `service.py`/`service.service`에서 v5/v6의 요청당 모델·도구·시간·추가 검색·판단 후 재조사 한도를 환경 설정으로 선택할 수 있게 연결했다. 로컬 MAIN45의 frozen 엔진/프로필·원문 세대·포인터는 유지하며, 실제 적용한 한도와 전체 프로필 해시·서비스 입구 해시를 HEALTH의 release binding에 별도로 표시한다. 기본값은 모델40회(최종 판단3회 예약), 도구1024회,1800초, 추가 검색8회, 재조사2회다. GENOS 현장 반입·배포는 별도다. [설정·적용·조회](../07_DOCS/REFERENCE/OPERATIONS/UNIFIED_LEGAL_AGENT_20261002.md).

2026-10-08 **작업 코드**에 법률 에이전트 판단 루프 회복을 반영했다(로컬 MAIN45·GENOS 미반영). 판단 완료 계약을 `investigation-completion-v2`로 올리고 과거 v1 route는 원래 렌더링으로 검증한다. ① ASSESS가 낸 원문 부족은 조사 라운드로 열리고, 탐색의 FINISH는 부족마다 RESOLVED(새 채택 원문)/NOT_AVAILABLE(조사 후 없음)/NOT_NEEDED를 기록해야 하며, 같은 부족(문서·조문 표기 기준)은 다시 조사로 되돌아가지 않는다. ② 거절된 탐색 결정·이전 검색식·행동별 실제 결과를 다음 화면에 보이고, 조문번호가 다른 검색을 같은 검색으로 막지 않는다. ③ ASSESS 2회 구조 충돌은 422 대신 부분 충족 제한 답변으로 정리하고, 채택 없이 멈춘 탐색은 실제 전달한 원문으로 판단하며(DEFER·EXCLUDE 제외), 모델 PENDING도 확인 원문이 있으면 제한 답변으로 끝낸다. ④ 답변은 쟁점별로 묶고 한계 문구에 빠진 문서·조문과 조사 결과·종료 사유를 표시한다. ⑤ 사용자 재조사·목적 정정은 이전 조사 상태를 힌트로 새로 시작하거나 다시 열며, 같은 세션의 이전 질문 조사 요약을 새 질문에 단서로 준다. 요청별 재진입 한도는 새 요청마다 초기화한다. ⑥ 부분 답변 route는 절차 재생에 활성화하지 않는다. 검증은 합성 원문·가짜 모델 계약 테스트이며 실제 모델 품질·GENOS 성능은 미확인이다. [설치 영수증·롤백](../90_RUNTIME/LEGAL_AGENT_FIX_20261008/receipt.json), [계약 테스트](../05_TESTS/CONTRACTS/test_judgment_loop_recovery.py).

아래는 이전 전환 시점의 이력이다.

2026-10-07 **조사 완료 계약의 로컬 MAIN**은 `investigation-completion-v6-20261007-r1`(generation **44**)다. 기존7단계와 전체 MAIN의 상위 파이프라인을 유지하면서 읽기/채택 계약, 보류·복귀, 진전·예산·재개, 부족분 재조사, 원문 span 인용, 확정 판단 표시, 오류 분류와 워크플로우 소비를 개선했다. 검증 후보·작업 코드·선택 릴리스268파일 및 실제 새 service.service의 실행 지문을 확인했다. 30개 핵심 계약 및25개 소비자 계약과 새로운 주 조문16질문, 알려진12회귀 결과·의미 오류·미답변을 분리해 기록했다. 사용자 지시에 따라 세부 정답100%를 요구하지 않았으며 심각한 무결성 기준과 quality_certified=false를 유지한다. GENOS 현장 실행은 별도다. [현재 결과와 원복](../04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration/MAIN_RESULT.md).

아래는 이전 전환 시점의 이력이다.

2026-10-07 **조사 제어 통합의 로컬 MAIN**을 `investigation-control-v6-20261007-r1`(활성 포인터 generation **43**)로 전환했다. 기존 v6/AD/shortcut·wiki/SQL·NFS·서비스 변경 위에 법령별 탐색·요청 단위 우선 정렬, 정확한 확보·전달·채택 범위, 저장 원문 재열람, 쟁점별 충분성·gaps, 번호가 있는 행동·이유 체인, RETURN_TO와 제한된 재진입을 연결했다. 검토 파일67개를 작업 코드에 통합했고 검증 후보·작업 코드·선택 릴리스의 서빙265파일 해시가 같다. 계약146개와 동결 독립32질문·기존8회귀 및 실제 새 `service.service`의 HEALTH/RAG_SEARCH/RAG_ASK를 확인했다. 사용자 지시에 따라 세부 판단 실수는 개선 기록으로 분리하며 게시된 원문·권한·상태·실행 지문의 무결성 기준을 유지한다. 원문 세대·공개 승인145문서·Qwen3.8 정책을 유지하고 GENOS 현장 배포·Git main 병합·전문가 품질 인증은 별도다. [실제 배선·결과·원복](../04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization/MAIN_RESULT.md).

평가 프로필과 실제 서비스 프로필은 전송 재시도 1회→0회 보정 한 항목이 다르다. 이 보정은 동결된 서비스 팩터리에도 존재하며 실제 실행 지문과 일치함을 별도 기록했다. 실제 확인 답변에서 질문 밖의 회사 유형·조문 연결 오류도 발견해 원문 근거와 함께 남겼다. 실행 배선 완료와 모든 세부 설명의 정답 보증은 구분한다.

이하 날짜별 설명은 당시 구현·전환 이력이다.

2026-10-06 사용자 요청으로 **로컬 RAG 서빙**을
`local-genos-unit-v6-20261006-r1`(활성 포인터 generation **42**)로 전환했다.
최신 GENOS 인계본 `investigation_logging_20261006_r2`의 누적 런타임을 동결하고,
설정된 최신 용어집 초안으로 glossary-serving-v2와 같은 reader의 캐시를 재구축했다.
원문 v2·navigation v7·230,299개 소유 본문 단위 fulltext를 새 세대로 연결했다.
159개 문서·230,417개 구조 단위·308,795개 블록의 내용과 사전 원본을 보존했으며,
모델 반출 허용 문서 145개도 유지한다. 기본 READ는 먼저 12개 후보 그룹을 획득한다.
로컬 공개 자료·Qwen3.8을 사용하며 GENOS 내부 자료·모델·현장 리비전 일치는 미확인이다.
사용자 지시 전환이며 품질 인증·Git 병합·GENOS 배포와는 별도다.
[전환·검증·원복 기록](../09_ARTIFACTS/AUDITS/20261006-local-genos-parity-r1/검증결과.txt).

2026-10-06 **작업 코드/GENOS 반입 R2**에 현재 사건 route의 일곱 판단 단계를
검증해 표시하는 `assembly.term_agent.judgment_view`를 연결했다. 전체·단계·데이터의
중첩 토글과 Mermaid는 저장된 판단/원문으로 코드가 생성한다. 기존 answer/claims와
LLM 입력·호출은 유지한다. 기존 완료 응답에 소급 적용하지 않으며 frozen MAIN,
원문 generation/CURRENT, GENOS 현장 배포·렌더링은 전환하지 않았다.
[표시 계약·생산/소비·반입·검증](../07_DOCS/REFERENCE/OPERATIONS/GENOS_JUDGMENT_VIEW_20261006.md).

2026-10-05 **로컬 제품 MAIN**을 `shortcut-integrated-v6-20261005-r2`,
활성 포인터 generation **40**, 기본 `legal-agent-unified-v6`로 전환했다.
대화·정정·도구·판단 기록은 shortcut DB에 저장하고 기존 action-memory /
unified-memory 명령으로 legal_wiki의 구성·검토·투영을 연결한다. 동일 입력의 탐색 절차는
결정적으로 재실행하되 원문·조건·메뉴가 달라지면 재판단한다. 현재 요청의 판단 범위를
ASSESS에도 전달한다. ADR-0654의 분리 멀티턴 9/9와 103개 계약 검사, ADR-0656의
서빙 243파일·엔진 30개 의존성 전수 검사 및 실제 활성 서비스 검사를 통과했다.
첫 r1의 배포 파일 누락은 generation39로 복구한 후 r2에서 수정했다.
원문 데이터 세대는 유지하며 사용자별 세션 연결은 신뢰된 인증 어댑터가 필요하다.
GENOS 배포·Git main 병합·전문가 법률 인증은 별도이며 quality_certified=false다.
[최종 배선·측정·이행·원복 기록](../04_EXPERIMENTS/ADR/ADR-0656-shortcut-packaged-main-validation/MAIN_RESULT.md).

2026-10-02 후속 사용자 사진에서 GENOS latest 로더의 실제 입구는
`project_root/service/service.py`이며 컨테이너 로그도 `/app/service/service.py`를 가리킨다.
사진의 직접 오류는 `unsupported GENOS_RAG_IMPLEMENTATION`이고, 값 원문·실제 코드 hash는
미확인이므로 경로 오류 하나로 원인을 확정하지 않는다. 작업 저장소에는 루트 `service.py`만
있었고 R2의 v6 변경이 플랫폼 입구에 연결되지 않을 가능성을 확인했다.
`service/service.py` 배포 adapter가 정확한 루트 v6 구현을 읽고 `service`/`service.service`
import는 같은 모듈·cache·warmup을 공유한다. 루트 구현·데이터 경로는 보존하며 별도 실행기를
늘리지 않는다. `service/`는 사용자 요청에 따른 플랫폼 호환 입구이며 MAIN의 논리 데이터 root가 아니다.
기존 Python 워크플로우와 service JSON 입구를 유지하고 `/chat` 이관은 선택사항이다.
앞선 연결 전용 R1과 main.py 제거 R2 롤백 안내는 적용 금지다. 사진 이후의 어댑터 반입·새
코드서빙 리비전·실제 v6 질문 성공은 현장 확인 전까지 미확인이다.


2026-10-02 사용자 사진과 승호 cicd `5fca5fa353f2f6b1463e38a020bddd64b1f3018e`의
실제 `main.py`/`workflow/chat.py`를 대조해 루트 `main.py`의 `/chat`을 추가했다.
채팅 입력·출처 표시·최종 누적 Reasoner 자료는 코드서빙의 chat adapter에서 처리하고
기존 `service.service → /v1/rag/ask → legal_agent v6`를 같은 프로세스에서 호출한다.
HTTP 자기 호출은 없으며 `code/data/text` 응답과 원래 채팅 필드를 보존한다.
개인 기억은 기존 서명 또는 명시적으로 인증한 플랫폼 연결을 요구한다.
NFS runtime은 `/nfs-root/diamo/8-agent/runtime`, 경험 DB 저널은 DELETE다.
작업 코드·반입 R2이며 로컬 MAIN 활성 포인터와 GENOS 현장 리비전 전환은 별도다.
[반입·설정·현장 확인·원복](../08_DEPLOYMENT/GENOS/handoffs/unified_v6_nfs_main_20261002_r2/GUIDE_UTF8.txt).

2026-10-02 **작업 코드**에 legal_agent를 유지하는 명시 선택 통합 v6를 추가했다.
일반 질문·정정은 같은 Pipeline/Coordinator/native 요청 journal을 사용하며, 최종 확인 경험을
shortcut과 user_wiki/legal_wiki가 같은 ID·revision·판단 refs로 조회한다. 원문·주체·현재 경로를
게시 전에 재검사하며 이관 기록은 LEGACY_UNBOUND로 보존한다. 초기 도메인 카탈로그는
조사 절차 통제와 발견 후보 구분이며 전체 법률 개념 승인은 별도다.
활성 MAIN·데이터 generation·GENOS 리비전은 바꾸지 않았다.
[실제 호출·계약·복구·검증 범위](../07_DOCS/REFERENCE/OPERATIONS/UNIFIED_LEGAL_AGENT_20261002.md).

2026-10-02 누적 멀티턴 정정 구현을 최신 MAIN **작업 코드**에 통합했다.
기존 `service.py → /v1/rag/ask`에서 명시적 memory 요청만 처리하며,
작업 원장과 최종 확인 경험을 분리하고 RAG 중간 단계로 재진입한다.
GENOS 워크플로우의 새 경로는 기본 비활성이다. 도메인 온톨로지 전체 통제는
설계 보존 상태이며 선택된 r3/generation37·원문 세대·현장 배포는 바꾸지 않았다.
[반영 범위·검사·남은 문제](../07_DOCS/REFERENCE/OPERATIONS/SYSTEM_MEMORY_INTEGRATION_20261002.md).

실험 후보를 로컬 RAG MAIN 릴리스에 이식할 때는 활성 릴리스 대비 파일별 변경과
frozen 후보의 원본 해시를 `prepare` 단계에서 검사한다. 후보 snapshot은
작업 트리의 필요한 파일만 복사하므로 최신 활성 릴리스와 자동 병합되지 않는다.
[통합·보존 검사 절차](../07_DOCS/REFERENCE/OPERATIONS/EXPERIMENT_MAIN_INTEGRATION.md).

2026-09-30 사용자 지시로 질문 맨 앞의 독립된 `내규`·`외규` 표시를 먼저 분리해
선택 세대의 해당 category 문서만 검색하도록 로컬 MAIN
`legal-agent-source-prefix-20260930-r1`(포인터 generation 35)에 반영했다.
사용자가 실제 입력한 `내규: 내규데데이터 뭐있냐`가 목록 대신 내용 검색으로 가는
문제를 고쳐 `legal-agent-source-prefix-20260930-r2`(generation 36)로 재전환했다.
명시한 출처 범위를 모델 시스템 프롬프트에도 전달하고 세션 문서 범위를 확인하는
`legal-agent-source-prefix-20260930-r3`를 로컬 MAIN generation 37에 반영했다.
표시가 없으면 기존 전체 범위를 사용한다. 팀·명시 문서·scope와는 교집합이며
GENOS 내부 리비전 배포·현장 답변 검증은 별도다.
[라우팅·검증·복구](../07_DOCS/REFERENCE/OPERATIONS/SOURCE_PREFIX_ROUTING_MAIN_20260930.md).

2026-09-30 사용자 지시로 질문 시 문서·조항·용어·정의의 짧은 탐색 맥락과
명시 문서의 단일 인용 정의 용어 직접 경로를 로컬 MAIN
`legal-agent-question-navigation-qwen38-20260930-r2`(포인터 generation 34)에
반영했다. 원문 세대·Qwen3.8 공개 범위는 유지한다. 기본 원문 읽기는 여전히 조 단위이고
새 경로의 실제 답변 품질·시간은 미측정이다.
[실행·검증·복구](../07_DOCS/REFERENCE/OPERATIONS/QUESTION_NAVIGATION_CONTEXT_MAIN_20260930.md).

2026-09-29 사용자 지시로 형식·판단 오류 수정 기능을
`legal-agent-structure-catalogue-pecab-repair-20260929-r1`에 동결하고 로컬 MAIN generation31로
활성화했다. 같은 입력에서 오류·이전 출력을 반환해 판단을 수정하며 기존 PeCab 세대를 유지한다.
사용자 지시 전환이며 품질 인증·Git main 병합·GENOS 배포는 별도다.
[MAIN 적용 상태](../07_DOCS/REFERENCE/OPERATIONS/MODEL_DECISION_REPAIR_MAIN_20260929.md).

2026-09-29 사용자 지시로 MAIN 작업 코드의 구조 기반 판단에 형식·참조 오류 수정 재요청을
연결했다. JSON Schema와 읽기 전용 판단 검증을 통과한 뒤 상태를 저장하고,
거절 시 같은 입력·범위에서 오류와 이전 출력을 반환한다. 선택 프로필의 수정 횟수와
기존 전체 예산을 유지한다. frozen MAIN·데이터·GENOS 배포는 별도다.
[실행·검증 범위](../07_DOCS/REFERENCE/OPERATIONS/MODEL_DECISION_REPAIR_20260929.md).

2026-09-29 최신 사용자 지시로 구조 원문 우선·네 가지 요청 분류·PeCab 세대·답변 SSE를
통합하고 로컬 MAIN을 `legal-agent-structure-catalogue-pecab-20260929-r1`로 전환한다.
진행 중 품질 실험의 통과로 간주하지 않으며 `quality_certified=false`를 유지한다.
GENOS 환경도 bounded 경로를 사용하도록 연결했다. 공개 색인과 내부 전체 구축을 구분하며
Git main 병합·GENOS 배포·워크플로우 확인은 별도다.
[통합 범위·현재 상태·현장 인계](../07_DOCS/REFERENCE/OPERATIONS/RAG_USER_DIRECTED_MAIN_20260929.md).

2026-09-29 사용자 요청으로 v5 MAIN **작업 코드**에 구조 원문 우선 검색을 연결했다.
명시 문서명/등록 약칭과 저장 조문 좌표·표제가 유일하면 해당 원문부터 읽고,
부족한 근거 또는 구조 미일치는 기존 fulltext 회수로 이어진다. bounded와 모델 도구
탐색 경로에 적용하며 로컬 frozen 릴리스·데이터·GENOS 배포와 구분한다.
[구조 우선 실행·검증·복구](../07_DOCS/REFERENCE/OPERATIONS/STRUCTURE_FIRST_SEARCH.md).

2026-09-29 사용자 지시로 v5 MAIN **작업 코드**의 첫 검색 계획에 인사·사용법의 직접 안내
응답을 연결했다. 원문 질문은 기존 회수·선별·답변 경로를 사용하고 문서 목록은 저장된
메타데이터로 응답한다. 현재/볼수있는 표현의 목록 인식·제목 필터를 보완했다.
활성 frozen 릴리스·데이터·GENOS 배포와 구분한다.
[요청 분기 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_REQUEST_ROUTING_20260929.md).

2026-09-29 사용자 지시로 구축 감사 원장과 서빙 navigation을 분리한 공통 파이프라인을
반영하고 로컬 MAIN을 `legal-agent-navigation-storage-20260929-r3`(포인터 generation 29)로
전환했다. 검색 12표/6,821,126행·색인 SQL·원문·용어집·fulltext payload를 보존하고 서빙
navigation을 13.91→1.81 GiB로 줄였다. 구축 근거·이전 세대는 보존하며 서빙 구현·스키마·모델 프로필은
직전 r3 frozen 릴리스와 같고 PIPELINE의 navigation/fulltext 경로·해시만 갱신했다. 현재 진입점의 로컬 profile도 선택 릴리스 policy로 결속한다.
작업 v5의 다른 변경·Git 병합·GENOS 배포·법률 품질 인증과 구분한다.
[실행·검증·감사·복구](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_STORAGE.md).

2026-09-29 사용자 지시로 v5 MAIN **작업 코드**의 fulltext 위치 구성은
문서/폴더 범위에서 검증된 matcher 메타데이터를 사용한다. 결과 전체의 본문 조회를
줄이며 조문 내부 범위 검사·페이지 프리뷰·READ·순위·정확 total/cursor는 유지한다.
원문·용어집·데이터 generation과 로컬 활성 frozen 릴리스는 변경하지 않는다.
[실행·검증·원복](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FULLTEXT_LOCATION_20260929.md).

2026-09-28 사용자 지시로 v5 MAIN **작업 코드**의 최종 답변 검토 기본값을
`final_review_enabled=false`로 변경했다. 탐색·선별·작성 후 답변을 반환하며 검토 생략을
기록한다. 작성의 원문·범위·세대·참조 검증은 유지한다. 로컬 활성 frozen 릴리스와
GENOS 리비전 배포는 별도다. [실행 계약과 복구](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FINAL_REVIEW_DISABLED_20260928.md).

2026-09-28 v5 MAIN **작업 코드**의 LLM 전송에서 중복 원문·메시지 내 출력 스키마·작성용
탐색 안내를 제거하고 단계별 지침을 정리했다. 서버 원문·좌표·출력 계약은 유지하며
저장 view와 실제 전송 projection을 해시로 연결한다. 로컬 활성 frozen 릴리스·데이터
세대·GENOS 리비전은 별도다. [전송 계약과 확인 범위](../07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_PROMPT_COMPACTION_20260928.md).

2026-09-30 로컬 활성 릴리스는 `legal-agent-qwen38-public-20260930-r1`
(포인터 generation 32)이다. 공개 질문·승인된 공개 문서 145개에 한해
OpenRouter Parasail FP8의 `qwen/qwen3.8-27b`를 호출한다. 신규 외부 실험 기본값도
`qwen38-experiments-v1`이다. GENOS 내부 모델과 배포는 변경되지 않았다.
실제 원문 확장 사례 3건은 근거 회수에 성공했지만 모두 조 전체를 읽어 시간 단축은
입증하지 못했다. [실험 기록](../04_EXPERIMENTS/ADR/ADR-0585-qwen38-empty-enum-omission-fix/README.md).

2026-09-23 로컬 모델 분기 이력: 당시 로컬 활성 릴리스는 `legal-agent-local-gemma-20260923-r1`
(generation 22)이며 공개 질문·승인된 공개 문서 145개에 한해 OpenRouter Parasail FP8의
`google/gemma-4-31b-it`을 호출한다. 요청은 `public_question:true`를 명시한다.
GENOS 세대 실행은 기존 내부 모델 환경 파라미터 결속을 유지한다. [로컬 실행·검증](../07_DOCS/REFERENCE/OPERATIONS/LOCAL_GEMMA_SERVING.md).
아래 `legal-agent-source-recovery-20260923-r1`은 직전 로컬 활성 이력이다.

2026-09-23 현행 로컬 MAIN: 사용자 지시로 **ADR-0513 원문 회수 + ADR-0517 선별·누락 복구**를 v5 요청 경로에 연결하고, `legal-agent-source-recovery-20260923-r1`(활성 포인터 generation 21)로 전환했다. DB는 `relation-subtree-main-serving-20260920-v1/generation`을 유지한다. 과거 Gemma의 80/90은 원문 보존 실험 결과이며 새 서빙 측정이나 답변 품질 인증이 아니다. DB 구조화·오연결 수정은 후속 후보로 검증 후 교체한다. [배선·한계·원복](../07_DOCS/REFERENCE/OPERATIONS/BOUNDED_SOURCE_RECOVERY_MAIN.md). 아래 날짜별 전환 설명은 당시 이력이다.

2026-09-22 현행 보강: 사용자 지시에 따라 MAIN 작업 기본 RAG를 `legal-agent-tools-v5`로 연결했다. 질문 요구 추적·요청별 번호·판단/행동 일관성·원문/초안 대조를 기존 Pipeline/Coordinator에 결속하며 CLI도 동일 세션으로 실행한다. 품질 인증과 내부 Gemma 모델 결속·GENOS 배포는 별도다. [v5 실행·전환 상태](../07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_V5.md). 아래 v2/v4 전환 설명은 당시 이력이다.

2026-09-21 source tier opt-in: `legal-agent-tools-v4` / `legal-agent-rag-v4`를 기존 요청 세션·StageRunner·outbox에 연결했다. 모델의 CORE/SUPPLEMENTAL 선택을 claims와 별도 보존한다. 로컬 모의 계약 24개 통과이며, 전체 TO-BE 판정·실제 모델 품질·GENOS 현장은 [v4 실행 및 미완료 범위](../07_DOCS/REFERENCE/OPERATIONS/SOURCE_TIERS_V4.md)를 따른다. 기본 v2와 ACTIVE_RELEASE는 전환하지 않았다.

2026-09-21 추가 작업: `legal-agent-tools-v3` / `legal-agent-rag-v3`를 명시 선택 경로로 구현했다. 인용·준용·위임·정의·용어·구조·원천 지식의 관계 안내, 질문별 판단 이력과 실제 제시 확인, 제한된 준용 선읽기와 관계 의존 주장 검토를 기존 요청 세션에 연결한다. 작업 기본 v2·로컬 활성 포인터는 유지하며 실제 모델 품질·GENOS 배포는 미확인이다. [v3 설정·검증·복구](../07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V3.md).

2026-09-15 사용자 지시로 법률 의미 상세 스키마를 RAG와 신규 데이터 생성에서 제거했다.
현행 계약은 [DATA_MODEL.md](DATA_MODEL.md), 엔진 선택은 [PIPELINE.json](PIPELINE.json)이다.
이전 Rule·SemanticClause·Proviso·조건식·템플릿 설계는 [변경 전 기록](../09_ARTIFACTS/AUDITS/20260915-term-only-schema-removal/before/00_SYSTEM-ARCHITECTURE.md)에 보존한다.

## 전체 흐름

2026-09-29 사용자 지시로 명시 참조 LLM 해소를 통합 MAIN **작업 구축 경로**에 연결했다.
`build-all --reference-model-profile PROFILE` 또는 `REFERENCE_RESOLUTION_PROFILE` 설정은
결정론 baseline → 폐쇄 후보 모델 선택 → 유효한 선택 전부 자동 승인 → 새 navigation/fulltext 결속으로
이어진다. 모델 기권은 UNKNOWN이며 사람 승인을 기다리지 않는다. 틀린 사례에 대한 별도 의미 차단 규칙은
추가하지 않았다. 공개 범위의 Qwen3.8-27B OpenRouter Parasail FP8 프로필과 GENOS 내부 프로필을
구분하며 기존 활성 릴리스·데이터와 GENOS 배포는 별도다.

```text
문서: 내부·외부 RAW → 전체 구조 복원 → 원문·좌표·버전 저장 → 명시 원문 통합
용어집: 기존 사전 + 통합 문서의 정의 후보 → 기존 미검토·신규 후보 통합 검토
  → 검토된 초안으로 전체 용어 출현 연결 + 문서 정의 + 명시 조문 참조
  → 설정한 LLM의 모호한 참조 해소·자동 승인 → 탐색 색인
  → 용어 탐색 → 원문 확인 → 부족한 근거에 따른 추가 탐색/질문 → 답변
  → 실행·원문 세대에 연결된 피드백 후보
```

의미 추출로 문장을 Rule·조건·효과로 재작성하는 단계는 없다. 에이전트는 원문을 읽고 판단 상태를 생성한다. 용어 관계와 정의는 탐색 단서이며 법적 결론을 자동 확정하지 않는다.

## 단계별 실제 연결

| 단계 | 진입점 | 출력·소비자 |
|---|---|---|
| 용어집 | `pipeline.py glossary …` | 출처별 사전·정의·관계. `GLOSSARY_SCHEMA.json`은 용어집 검토 계약만 소유 |
| 통합 구축 | `pipeline.py build-all --run-id NAME --execute` | MAIN 기본 `native-no-models`: 팀 RAW 원본 직접 구조화(VLM off, 로컬 PDF) → 명시 원문 통합·문서 근거 교체 → GENOS 최종 compact-v2 native 연결/navigation-v7/storage-v3/단위 전문 색인. 모델 0회, 서빙 자원 포함 후보와 감사 원장 생성·오프라인 검사. 활성 릴리스 전환은 별도. 기존 모델 검토 구축은 `--with-model-review`로 명시 |
| 단계별 통합 구축 | `pipeline.py document-release select/merge/prepare/review/index/reindex/status/verify` | 종료된 구조화의 성공분을 명시 새 범위로 선택 가능. `reindex --from-run-id PREPARED --run-id NEW`는 GENOS compact-v2 구현으로 준비된 원문·용어집·완료 지식 묶음을 재사용하며 모델을 호출하지 않는다. 저장 방식과 단위 전문 색인을 명시 고정하고 후보의 서빙 자원·오프라인 계약을 검사한다. 원래 실패 기록·제외 사유와 해시를 보존한다. [실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_RELEASE_STAGES.md) |
| 입력·구조화 | `pipeline.py build-data-stages --stage structure --run-id NAME --execute` | `STRUCTURE/<fingerprint>/source.sqlite`; 문서·구조 마디·본문만 저장. PDF 구조 복원의 VLM은 유지 |
| 색인·적재 | 같은 명령의 `--stage index` 또는 `all` | `TERM/<run>/<document>/generation`: 원문 세대와 용어·정의·참조 탐색 색인. `term_generation.build_generation`이 같은 계약으로 생성 |
| RAG | `service.py` → `semantic_runtime.app` → PIPELINE의 `legal-rag` | 원문·용어 탐색 전용. QueryPlan/CardSet·규칙·조건 평가·의미 그래프 fallback 없음 |
| 피드백 | `/v1/rag/feedback` → `legal-feedback` | 답변·실행 해시·원문 세대를 가리키는 PROPOSED 후보. 자동 반영 없음 |
| 로그 기반 개념 구축 | `pipeline.py action-memory build/status` | 완료된 native 요청의 질문·행동 이유·완독 원문·선별 근거 → 버전 결속 목적 개념·`GUIDES_TO`와 제외 후보. 야간 오프라인 CLI·상태 로그까지 연결; 온라인 숏컷은 ADR-0575 속도 기준 실패로 활성 릴리스에 미반영. [실행·현황·범위](../07_DOCS/REFERENCE/OPERATIONS/ACTION_MEMORY_NIGHTLY.md) |
| 근거 결속 실패 개선 | `pipeline.py action-memory diagnose/propose/comparison-plan/compare`; `golden score-native` | terminal v5/v6 요청 → read-only snapshot 진단 → 단일 Tool 층 불변 후보 → 독립 split·검토 결과 비교. v6 원문 span/성공 호출 전달/인용·답변 hash와 기존 golden scorer를 연결. 모의 계약·로컬 v5 진단 확인; 실제 품질 개선·온라인 후보 실행·자동 예약·MAIN/GENOS 활성화는 미실행. [계약·실행·한계](../07_DOCS/REFERENCE/OPERATIONS/FAILURE_IMPROVEMENT.md) |
| 조사 경험 위키 | 같은 `action-memory build` 종료 / `action-memory wiki-export/check/unlink/retire` | 기존 LLM 조사 목적을 `legal_llm_wiki` 불변 원자료·개념 페이지·index·log로 저장. 이유·세대·원문 근거를 연결하고 오개념화 관계/개념을 이력 보존하며 중단. DB catalogue/compile은 중단 overlay 반영; 온라인 위키 주입·의미 매칭·정답 인증·활성 릴리스는 미반영. [저장·검증·복구](../07_DOCS/REFERENCE/OPERATIONS/LEGAL_LLM_WIKI.md) |
| 표현 학습·절차 재사용 | `pipeline.py glossary learn` + 선택형 `term_agent.learning` | 질문 구간 후보 → 운영자 검토 → 세대·해시 결속 번들 → 기존 NavigationSession. [작업 코드 계약](../07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_LEARNING.md). 기본 꺼짐, 활성 릴리스 미반영 |
| 개념 정의·범위 작업 하네스 | `pipeline.py task-harness` + 선택형 `definition-scope-harness-v1` | 검토된 DB 정의 → 원문 span 해석 → 후보 검토 → 의무별 원문·의미 검토 → 완료/미확인 → 개선 후보. [구현·실행 계약](../07_DOCS/REFERENCE/OPERATIONS/TASK_HARNESS.md). 작업 코드와 모의 계약 검사, 활성 릴리스·GENOS 미반영 |
| 명시 참조 해소 | `build-all` / `document-release build/references`의 모델 프로필 + `reference-resolution` | 결정론 baseline → 폐쇄 후보 observation → 유효한 모델 선택 자동 승인 → 새 navigation generation. [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/REFERENCE_RESOLUTION.md). 미설정 구축은 모델 0회, 활성화·GENOS 배포는 별도 |
| 골든 관리·평가 | `pipeline.py golden` | 원문 좌표 검증·suite 동결 → GENOS 코드스페이스의 같은 `/v1/rag/ask` 앱으로 배치 → 단계별 회수·인용 점수 + 사람 답변 검토. 제품 입력과 정답 분리, [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_GOLDEN_EVALUATION.md). 현장 실행 미확인 |

현재 신규 문서 생성은 DRAFT를 만들며 MAIN을 자동 활성화하지 않는다. source-only 게시 API도 동일한 용어 색인 생성기를 사용한다. GENOS 현장 실행·반입·배포는 아직 확인하지 않았다.

GENOS 문서 구축의 PDF는 환경변수로 선택한 전처리기에 파싱을 맡긴다. `data.document`의
Docling JSON 또는 완전한 인덱스 청크 배열을 받아 기존 구조화·원문 SQLite·용어 색인으로 연결한다. 청크는 원문·순서·페이지 출처를 보존해 합치고, 전체 파싱 텍스트로 틀 생성 → 원본 PDF VLM 검수·틀 보정 → 최종 틀로 전체 재구조화한다. 청크 입력은 전 페이지 검수 필수이며 없는 표 셀·좌표를 생성하지 않는다. 전처리기 ID/URL과
선택적 배포 리비전, 공유 경로는 코드스페이스 환경 설정으로 지정한다. 코드스페이스에서 PDF용
Docling 모델을 다시 실행하지 않는다. [연결·실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md).
2026-09-16 현장 사진에서 기존 전처리기의 성공 청크 응답을 확인했다. 새 청크 수신·VLM 연결 및 별도 구조 응답 전처리기 수정본은 로컬 모의 계약 검증이며 현장 배포·품질은 미확인이다.

## 서빙과 이행

GENOS의 공유 NFS 색인 세대 교체와 코드서빙 RAG 모델·출력 토큰 설정은
[세대 교체 서빙 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_RAG_GENERATION_HANDOFF.md)에 기록한다.

2026-09-21 사용자 지시로 **작업 코드의 MAIN 기본 RAG는 `legal-agent-tools-v2`**로 연결했다. 기존 HTTP → Pipeline → 요청 세션 → Coordinator/StageRunner → outbox를 유지하며 도구 선택·정확 READ·현재 입력 전달·원문 평가·검토/반론 재진입을 수행한다. 내부 계약과 journal은 v2, 외부 Request/Result는 term-runtime-v1이다. 기본 모델 프로필은 미결속이며 실제 모델 요청에는 명시 설정이 필요하다. [배선·설정·복구](../07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V2.md). 합성 계약 검증과 모델 품질/현장 검증은 구분한다.

2026-09-21 당시 로컬 활성 포인터는 `document-navigation-rag-20260921-v1`, generation 17, quality_certified=false였다. 현행 선택은 문서 상단의 2026-09-23 전환과 ACTIVE_RELEASE를 따른다. 해당 과거 frozen release와 명시 호환 경로의 `document-navigation-v1`은 질문을 목록·트리·목차·내용·매핑으로 먼저 해석한다.
문서 목록·폴더 트리·목차는 저장된 메타데이터로 답하고, 내용 질문만 여러 원문 읽기·검토·종합으로 넘긴다.
GENOS에서는 `GENOS_RAG_IMPLEMENTATION`으로도 명시 선택한다. [GENOS 반입·계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_TOOLS.md).

2026-09-17 당시 확인한 로컬 활성 릴리스는 `document-navigation-rag-20260917-v2`, 포인터 generation 16이었다(사용자 지시 전환 뒤 전수 조사·수정 재릴리스, 품질 인증 false).
내용 질문은 질문 개념별 후보(컷 없음, 개념 적중 순)를 3건씩 읽고 검토하며, 채택 근거가 있으면 후보를 다 읽지 않아도 종합·검증한다.
로컬 159문서 세대의 폴더는 해시로 검증한 출처 파일로 분류한다: kofia 72 · law 62 · krx 11 · internal/risk_team 10, 미확인 4.
[현재 배선·운영 계약](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_MAIN.md).

로컬 MAIN 릴리스 및 포인터의 최종 상태는 [문서 탐색 배선 기록](../09_ARTIFACTS/AUDITS/20260917-document-navigation-main-wiring/README.md)과 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`을 따른다. 직전 탐색 루프 릴리스는 [탐색 루프 배선 기록](../09_ARTIFACTS/AUDITS/20260916-navigation-main-wiring/README.md)에 보존한다. 코드 변경·Git main 병합·데이터 세대 선택·로컬 MAIN 활성화·GENOS 배포는 각각 별도 상태다.

- 원문 159문서의 ID·본문·구조·해시를 그대로 새 원문 전용 세대로 옮겼다.
- 기존 의미 테이블·projection은 새 세대로 복사하지 않았다. 과거 세대·ADR·릴리스는 보존한다.
- 정의의 원문 블록과 해시를 검증하고, 인용·준용은 원문에 명시된 조문 표기를 색인한다. 구조 좌표가 완전한 단순 범위는 규칙으로 확장하고, 외부 문서·약칭·문맥·복수 후보는 검토 전까지 미확인으로 둔다.
- 원문·용어집·코드 변경은 새 세대와 색인을 만든다. 기존 파서 캐시는 사용한 파서 지문이 같을 때만 재사용한다.
- 품질 인증은 `false`다. 이번 변경의 검사는 구조·계약·배선 검사이며, 법률 답변 품질 통과를 의미하지 않는다.

전체 파이프라인 실험은 입력·설정·모델·프롬프트·코드와 변경하지 않은 단계도 함께 고정한다. 원문 근거·버전·감사·롤백·접근권한을 보존한다. 피드백에서 재구축·검증·MAIN 채택까지의 자동 루프는 미완성이다.

현행 구축 단위와 의존성은 `PIPELINE.json.authorities.document_build` 및 [실행 안내](../07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md)를 따른다. 내규도 `RAW/internal`에서 형식별 처리한다. 구조화 단독 실행은 용어집을 읽지 않는다.

추가 문서의 통합 서빙 후보는 `TERM_RELEASES/<run>`에 생성한다. `document-release`가 동일 실행 명세의 후속 단위이며 활성화는 명시적 CURRENT CAS/롤백 절차다. [추가 문서 연결 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md). 작업 코드의 이 연결은 기존 로컬 활성 릴리스나 GENOS 배포를 변경하지 않는다.

### 최소 구조 단위 fulltext 작업 경로 (2026-10-02)

완료된 구조화/navigation에서 `06_TOOLS/pipeline.py fulltext --generation PATH --output NEW_PATH`로 항·호·목 소유 본문만 새 색인에 결속한다. 원본과 연결/navigation을 재구축하지 않는다. 로컬 작업 코드에 연결했으며 GENOS/활성 릴리스는 별도 반입·선택이 필요하다. 입력·스키마·소비자·로그·재개 계약은 [최소 단위 fulltext 안내](../07_DOCS/REFERENCE/OPERATIONS/MINIMUM_UNIT_FULLTEXT_20261002.md)를 따른다.


## 2026-10-06 shortcut·legal_wiki AD 제어

[구현 설계와 운영 계약](../07_DOCS/REFERENCE/REPORTS/SQL_AD_MODE_SHORTCUT_WIKI_20261006/README.md). 정확한 `[AD모드 시작]`/`[AD모드 종료]` 경계와 SQL 관리 상태를 기존 서비스에 연결했다. 이 AD 인계본 준비 당시 로컬 서빙 MAIN은 `sql-ad-mode-v6-20261006-r1`(generation 41)이었다. 이후 generation 42 전환은 문서 상단 기록을 따른다. GENOS 현장 배포는 별도다. 일반 법률 실행과 AD 제어는 분리한다. GENOS_STATE_DIR의 영속 로컬 SQL 볼륨·상주 작업자·워크플로우 Python 교체 조건을 인계에서 확인한다. Redis는 사용하지 않는다.


### AD 자연어·멀티턴 해석 연결 (2026-10-06)

사용자 요청으로 활성 AD의 매 턴을 GENOS 내부 LLM으로 해석하는 작업 코드를 연결했다.
현재/최근 표·선택·이전 확인 질문을 SQL 맥락으로 전달하고 닫힌 action/args를 검증해
기존 SQL 실행기로 처리한다. 상세·상태·변경 결과는 표로 출력한다. 이전 고정 표현만
지원/관리 명령 모델 호출 없음 규칙을 대체하며 정확한 모드 경계는 유지한다.
[계약·실제 배선·검증·적용 상태](../07_DOCS/REFERENCE/OPERATIONS/AD_NATURAL_LANGUAGE_20261006.md).
52개 관련 계약과 35개 SQL AD 호환 회귀 통과. 모의 모델 배선 검사이며 내부 모델 품질·
GENOS 배포·Git push는 미확인이다. 활성 frozen MAIN·데이터 CURRENT는 전환하지 않았다.

## 2026-10-06 법령별 후보 탐색 작업 코드

[구현과 완료 정책](../07_DOCS/REFERENCE/REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/IMPLEMENTATION.md). MAIN의 RAG 서빙 단계에서 소유 본문 색인을 법령 판본→조→적중 단위 페이지로 조회하고, 기존 SELECT가 법령 선택 이유·부모/형제 READ·다른 법령 이동·전체 허용 범위 재검색을 수행한다. 기존 원문/navigation/용어 단계 계약은 유지한다. 사용자 후속 지시에 따라 미해결 필수 연결은 완료 관문에서 제외하며 실제 미해결 상태와 경고는 보존한다. v6 작업 프로필과 기존 native API/SQL checkpoint에 연결한 상태이며 로컬 frozen MAIN 및 GENOS 배포 전환은 수행하지 않았다.


## 2026-10-16 공용 근거 관계 원장 — 로컬 MAIN82

`basis-link-lifecycle-20261016-r1`(포인터 generation82)에 질의·대사·내규 전체 조사·사용자 검토·개정 이행이 공유하는 `semantic_runtime/basis_links`를 연결했다. 원문과 용어집 구축을 대체하지 않는 관계 검토·재사용 층이다. `internal_basis_discovery_workflow` 1.0.0은 기존 workflow Runtime에 등록되며 승인 관계는 다음 요청부터 기존 원문 도구로 우선 읽는다. `document_release.activate`와 기존 Oracle 게시 함수에는 판본별 binding의 prepare/verify 후속 단계를 연결했다.

검증 후보와 최종 작업 코드, 선택 릴리스의 해시를 연결했다. 최종 작업 코드214검사와 선택된 실제 로컬 서비스10검사가 통과했으며 데이터 세대는 유지했다. 동시 완료된 최소 모델 출력 계약(ADR0850)도 보존하여 ADR0853의 명시적 부모 통합으로 선택했다. [구현 결과](../09_ARTIFACTS/AUDITS/20261016-internal-external-basis-lifecycle-design/IMPLEMENTATION.txt), [실행 binding과 hash](../09_ARTIFACTS/AUDITS/20261016-internal-external-basis-lifecycle-design/IMPLEMENTATION_RESULT.json), [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/BASIS_LINK_LIFECYCLE_20261016.txt).

GENOS의 Oracle 관계 저장·인증된 사용자·Dataiku 실제 배치 연결은 구현된 factory/hook에 현장 계약을 주입해야 한다. 현장 반입·배포·워크플로우 편집기 반영은 수행하지 않았다. Oracle DB-API 테스트 더블과 로컬 원문을 이용한 기술 검증이며 실제 모델 정확도·현장 성능 인증이 아니다. 기존 로컬 상주 프로세스도 재시작하지 않았다.


## 2026-10-18 시스템 조립 출력 계약 — 로컬 MAIN83

`host-assembled-output-20261018-r1`(포인터 generation83)은 MAIN82의 전체 단계 책임, 대사 workflow1.9.0, 내규 근거 발굴 workflow1.0.0, 공용 근거 관계 원장과 Oracle 연결을 유지한다. 원문 데이터 세대·검색 선택·모델 정책·실패 예산은 바꾸지 않았다. MAIN의 서빙 단계에서 모델 생성 → 최소 출력 복원 → 원래 검증/소비자 순서를 유지하며 생성·복원 계약만 맞췄다.

모델은 판단·이유·필요한 대상을 반환한다. 계약으로 확정 가능한 고정값·빈 구조·상태/표시 ID와 중복 대상·쟁점 연결은 시스템이 조립한다. 단일 대상 행동은 `targets`, 여러 원문 읽기는 `exploration`에서 한 번 선택한다. 행동별 필수값/허용 대상과 부모·중첩 분기의 제약을 생성 스키마에서도 보존하며, 서로 모순되는 구 응답을 임의로 고치지 않는다. 원문 인용·권한·상태·예산 검사와 의미 불확실성 표시 원칙은 유지한다.

ADR0870 후보413검사, 통합 작업415검사와 후보/작업/선택 릴리스의 실제 데이터·서비스 각10검사를 확인했다. 후보711파일과 작업 코드, 서빙370파일과 선택 릴리스가 일치한다. ADR0871의 동일 코드 외부 Qwen fulltext16호출에서는 생성 스키마·복원 오류0회, 최종 답변1건·조사 미완료1건이었다. 법률 정답률이나 GENOS 내부 모델 timeout 해소의 증명이 아니다. 완료0870 기록을 바꾸지 않고 ADR0872에서 승격 결속10검사를 별도로 수행했다.

[반영 결과·자원 기록·한계·롤백](../08_DEPLOYMENT/RELEASES/host-assembled-output-20261018-r1/IMPLEMENTATION.txt)과 [정확한 선택/서비스 binding](../08_DEPLOYMENT/RELEASES/host-assembled-output-20261018-r1/IMPLEMENTATION_RESULT.json)을 따른다. 무거운 검사는 하나씩 실행하고 원문·색인을 공유했다. GENOS 현장 코드 적용·Git push·리비전·워크플로우 편집기 반영·내부 모델 검증은 별도 미확인 상태다.

## 2026-10-18 대사 후속 조사·상태 계약 — 로컬 MAIN84

`bounded-followup-20261018-r1`(포인터 generation84)은 MAIN83의 단계 책임·출력 압축·시스템 조립·근거 원장·Oracle 연결·데이터·검색을 유지한다. 대사 workflow1.9.1의 기존 task board에서 과제별 입력 → 자식 원문 조사 → 정확한 과제 receipt → 부모 상태 저장 → 새 근거가 있을 때 항목 재검토 → 비교/답변으로 연결한다. 첫 빈 조회 뒤 다른 독립 과제는 기존2회 한도 안에서 진행하며, 동일 자료 획득은 항목 간 재사용한다. 자식 호출 성공과 원문 확보 완료를 구분하고 재개 전 근거 목록·호출 ID·누적 예산을 유지한다. 내규 근거 발굴 workflow1.0.0은 공유 코드 pin만 갱신했다.

MAIN83 실제 모델 기준8호출과 동일 데이터의 고정 수정 후보12호출을 실행했다. 후보는 빈 내규 조회 뒤 외규 추가 조사와 재검토를 거쳐 최종2항목 부분 결과를 반환했다. 인용 span·권한·상태/중복·소비자 검사를 통과했으나 원문 부족·모델 적용범위 판단 오류가 남아 법률 정답으로 인증하지 않는다.311계약, 후보·작업·실제 활성 서비스 각10검사를 통과했고 선택370파일과 후보/작업711파일을 결속했다. 이 검증은 RAG 대사 서빙 경로이며 전체 데이터 수집 파이프라인 또는 GENOS 내부 모델 배포 검증을 대신하지 않는다.

[실제 선택/서비스 binding·원복](../08_DEPLOYMENT/RELEASES/bounded-followup-20261018-r1/IMPLEMENTATION_RESULT.json), [실제 모델 원문·판정 한계](../04_EXPERIMENTS/ADR/ADR-0875-bounded-followup-live/artifacts/run-001/manual-review.json)를 따른다.

## 2026-10-18 원문 문맥·쟁점 연결 — 로컬 MAIN85

`original-context-20261018-r1`(포인터 generation85)은 MAIN84의 전체 단계 책임과 데이터·검색·모델·예산을 유지한다. 대사 workflow1.10.0은 항목 선택 근거 → 동일 출처/문서/쪽/쟁점의 확보 원문 문맥 → 해당 쟁점과 항목 의견 → 최종 비교로 연결한다. 모델 인용 선택이 이미 읽은 단서를 누락시키지 않도록 pair 허용 근거와 입력 문맥을 같이 결속한다. 새 의미 승인 관문이나 강제 재시도는 추가하지 않는다. 읽기 선택지와 전달 원문 수는 시스템이 제공하며, 충분성·적용범위는 검토 가능한 모델 의견이다.

내부 참조 규정의 미등록, 금융소비자보호법 RAW와 명시 팀 입력 범위 차이, 이미 확보된 원문 전달 누락을 구분했다. 워크플로우 부분 결과와 모델의 검색·미확인 조문번호 오류를 보존한다. 제8조 단서 범위는 별도 실제 모델 원문 검사에서 확인했으며 전체 검색·법률 정답률을 인증하지 않는다. [정확 코드·선택·서비스 결속](../08_DEPLOYMENT/RELEASES/original-context-20261018-r1/IMPLEMENTATION_RESULT.json)과 [원인·잔여 사항](../08_DEPLOYMENT/RELEASES/original-context-20261018-r1/IMPLEMENTATION.txt)을 따른다. GENOS 현장 적용은 별도다.


## MAIN86 읽기 선택과 시스템 조립 계약 — 2026-10-18

2026-10-18 당시 선택 로컬 RAG는 **MAIN86 `read-first-host-contract-20261018-r1` / 포인터 generation86**, 대사 workflow **1.10.0**이다. MAIN85의 데이터·검색·Oracle·대사·출력 압축·재개·예산을 유지하고, 본문 읽기 선택과 읽은 원문 유지, 평가 고정값·질문 인용 시스템 조립, 조건 관계식 복원을 연결했다.404기술 검사와 후보/작업/활성 서비스 각10검사를 통과했다. 같은 CM5문항은 최초4답변/1RAM보호중단이며 CM008별도 재검증을 보존했다. **일부 재검색·조기 판단·불필요한 확인 문구와 CM003/051의 답변 완결성 문제는 남고, GENOS현장과새ZIP/TXT는 미수행**이다. [실제 결과·한계·원복](../08_DEPLOYMENT/RELEASES/read-first-host-contract-20261018-r1/IMPLEMENTATION.txt) · [선택 binding](../08_DEPLOYMENT/RELEASES/read-first-host-contract-20261018-r1/IMPLEMENTATION_RESULT.json).


## MAIN87 원문 전달 연속성과 응답 일치 — 2026-10-19

2026-10-19 현재 선택 로컬 RAG는 **MAIN87 `cm-read-continuity-20261019-r1` / 포인터 generation87**, 대사 workflow **1.10.0**이다. MAIN86 데이터·출력 압축·재개·예산·Oracle·근거 원장을 유지하고 원문 탐색/전달 연속성, 참조 판단의 제한 복구, 평가 입력 축약과 저장·공개 응답 일치를 연결했다. 669기술 검사와 후보/작업/활성 서비스 각10검사 통과. 기존CM5+추가011·022·038 실제 RAG는8응답/핵심7충족이며 **CM003 의미 판단, 불필요한 확인 문구·일부 반복 조사는 남는다.** 전체 대사8회 또는 GENOS현장 검증 결과가 아니다. [실제 결과·한계·원복](../08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION.txt) · [선택 binding](../08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION_RESULT.json).
