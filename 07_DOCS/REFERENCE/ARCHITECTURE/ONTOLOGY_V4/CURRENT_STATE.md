# 현재 상태와 관측 근거

**최신 화면 r4 — 표형 기록:** 모인 기록·검토 목록과 선택한 조사 판단을 표로 정리했다. 행 선택 후 상세에서 기존 초안 생성·사람 승인으로 이어진다. [r4 구현·검증과 남은 과제](APPLICATION_READINESS_20261028.md). 아래 r3는 3단계 연결 당시 기록이다.

**최신 화면 r3:** 기존 준비함의 모인 기록 확인 → 명시적 초안 생성 → 사람 승인 흐름을 3단계로 연결했다. 사람과 LLM의 역할을 표시하며 생성 완료는 DRAFT이고 골드 반영과 별개다. 전체 숏컷 자동 수집/병합은 미연결, 외부 공개 화면은 합성 예시 생성이다. [현재 범위·검증·남은 과제](APPLICATION_READINESS_20261028.md). 아래 r2의 생성 버튼 제거 상태와 구분한다.

**같은 날 후속 — 화면 단순화:** 사용자 요청으로 6메뉴 대시보드를 승인함 하나로 교체했다. 목록·내용·원문·승인/반려·골드 후속 안내만 제공한다. 아래 6화면은 이전 구현 기록이며, 현재 화면은 [적용 계획의 최신 정정](APPLICATION_READINESS_20261028.md)을 따른다. 서버 승인 계약·MAIN112·실제 데이터는 변경하지 않았다.

## 2026-10-28 최신 — 대시보드 구현과 실제 적용 경계

[실제 적용 계획](APPLICATION_READINESS_20261028.md)에 현재 코드·화면·골드 절차와 첫 적용 P1~P6을 정리했다. 실제 Streamlit 6화면과 기존 앱 진입점을 작업 프런트엔드에 연결했고 새19+기존22=41검사·그래프 클릭 왕복을 확인했다. 새 골드 화면은 **승인 판본의 이관 요청 저장**까지이며 실제 모델 검증·SQL 적재·사용 전환과 영속 이관 상태 조회는 남아 있다.

현재 선택은 **MAIN112**, 온톨로지 기본 OFF·데이터 미포함이다. 이번 대조의 `ontology_work` 10모듈은 선택 코드와 같지만 전체 작업 코드 일치 판정은 아니다. Dataiku S3/이벤트 입력·GENOS 조회 권한/리비전·운영 Gold 매핑은 현장 미확인이다. 첫 적용 목표는 질문 A에서 만든 승인 지식을 골드에 반영한 뒤 다른 질문 B가 같은 원문에 도착했을 때 재사용하는 것이다.

원문 조사 후속은 [ADR1178 결과](../../../../09_ARTIFACTS/AUDITS/20261028-response-contract-recovery/수정과_재시험결과.txt)를 따른다. 001은 완료 조건 통과, 007은 두 시장 13조 미확보, 009는 최신 연속 시험에서 미실행이다. 최종 포함 판정 수정 뒤 실모델·작업 통합·MAIN 승격·GENOS 확인은 미수행이다. 아래 MAIN111 연결 및 MAIN103 시점 설명은 해당 시점의 기록으로 읽는다.

<!-- ONTOLOGY_WORKFLOW_20261028 -->
## 2026-10-28 생성·승인·게시 연결

기존의 “화면/S3/Oracle 미연결” 설명은 선행 상태다. 이번 구현은 기존 화면·Dataiku 스트림 저장 어댑터·Oracle/SQLite 게시 저장소·RAG 원문 좌표 조회를 연결한다. 실제 현장 설치·권한·GENOS 배포와 로컬 검증 결과를 구분한다.

[최신 계약·테이블·실행 경로·검증 경계](WORKFLOW_CONNECTED_20261028.md). 아래 날짜별 내용은 당시 기록이며 최신 연결 상태로 확대하지 않는다.
<!-- /ONTOLOGY_WORKFLOW_20261028 -->

<!-- MAIN104_SQL_FOLLOWUP -->
**2026-10-27 — MAIN105 반영·실제 서비스 확인 완료:** [전체 반영·실제 실행·온톨로지 후속](MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 최초211초 원인의 MAIN104 SQL 수정에 반복 원문 확인 재사용과 네 연결 TEMP VIEW의 ID 점조회를 더했다. 보관응답1회 재생의 동일 계측35화면736.500→93.718초(87.275% 감소), 원문·행동·최종 답변 동일, 새 모델 호출0회다. 신규237조건·관측보조1,345조건을 구분한 ADR1081 검증 후 MAIN105 `navigation-validation-20261027-r1`을 선택했고 실제 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)이 통과했다. 작업 코드 통합에서 새4검사 통과, 기존7실패는 변경 전후 동일하다. 온톨로지는1074 부분실패→1077 상태 전환 수리→MAIN105 결합1079 실모델1셀/10호출을 완료했다. 두 원문의 판단 보존을 확인했지만 근거 연결 보완1회·제한 답변으로 품질 효과는 미인증이다. MAIN105 최종 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했다. 설치144명령·SQL18·상태13쌍을 통과했으며 MAIN104 첨부를 대체한다. P0~P4 전체 구현·전체 응답시간 개선·법률 품질·온톨로지 MAIN·GENOS 현장 배포 완료로 확대하지 않는다. 아래 이전 상태 기록과 구분한다.
<!-- /MAIN104_SQL_FOLLOWUP -->

[v4 목차](../ONTOLOGY_V4.md) · [프로토타입 구현](PROTOTYPE_DESIGN.md)

2026-10-23 최초 확인, 2026-10-24 두 차례 추가 확인. v4는 새 설계이며, 아래 기존 구현의 존재와 기본 활성화를 구분한다. 제품 코드·선택 포인터·완료 실험·v3는 문서 작업에서 수정하지 않는다.

## 2026-10-24 구축 결정을 위한 확인

[구축 순서](BUILD_PLAN.md)를 정하며 작업 코드와 MAIN103 릴리스를 대조했다.

| 확인 대상 | 결과 | 작업 코드 = MAIN103 |
|---|---|---|
| 턴 분류 | [memory_methods.py](../../../../02_BACKEND/semantic_runtime/legal_agent/memory_methods.py)에 12가지 요청 종류. `corrected_memory.resolve`가 LLM으로 하나를 고름 | 같음 |
| 수정 가능한 필드 | `task`, `source_category`, `document_ids`, `facts`, `queries`. 개별 판단 기록은 지정해 바꿀 수 없음 | 같음 |
| 이전 질문 참고 | 같은 세션에서 직전 READY 질문 1개(`LIMIT 1`)의 조사 요약, 현재 질문의 최근 수정 이력 6개 | 같음 |
| 세션 | [case_repository.py](../../../../02_BACKEND/semantic_runtime/legal_agent/case_repository.py): 세션 → 질문 → 이벤트, 세션 소유자(user·team) 검사, 로컬 SQLite | 같음 |
| 연결 타입 | [relation_read_policy.py](../../../../02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py)에 14종과 FOLLOW/SKIP/DEFER 판단 규칙 | 같음 |
| 읽기 판단 | [read_judgment.py](../../../../02_BACKEND/semantic_runtime/legal_agent/read_judgment.py)의 CORE/SUPPORT/CONDITIONAL/DEFER/EXCLUDE | **작업 코드에만 있음** |
| 판단 투영 | `judgment_view.build` → `judgment-view-v1` | **다름** |
| 지식 저장 | `lk_record.payload`에 레코드 JSON 통째 저장(로컬 SQLite·Oracle CLOB 모두). Oracle 어댑터는 테이블 이름 매핑(`lk_record`·`lk_head`·`lk_lookup` → 승인된 실제 이름)만 검증하고 필드 단위 매핑은 없음 | 같음 |
| 계산 연산 | `ontology.evaluate`: all·any·not·eq·in·lt·lte·gt·gte·add·subtract·multiply·divide·before·after. `min` 없음 | — |
| 승인 화면 | [Streamlit 지식 작업공간](../../../../03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py)에 승인·반려·수정 | — |
| GENOS Oracle 원문 표 | [9개 표 패키지](../../../../08_DEPLOYMENT/DATAIKU/legal_oracle_all_tables_20261019_r1/LEGAL_ORACLE_ALL_9_TABLES_20261019_R1.sql): `LEGAL_SRC_*` 3개, `LEGAL_RAG_*` 6개 | — |

2026-10-24 별표 연결 수정(작업 코드): 별도 파일로 저장된 별표를 같은 법령 폴더의 파일로 연결하는 규칙을 색인 생성기와 실행 중 연결 목록에 넣었다. 현재 선택 세대의 미해결 별표 인용 8,013건 중 5,451건이 연결된다. [기록](../../../../09_ARTIFACTS/AUDITS/20261024-annex-binding/README.md). 색인의 연결 종류 표시는 대부분 단순 인용(`CITES`)이고 위임(`DELEGATES_TO`)은 0건이며, 그 표시로 후보를 정렬하는 현재 방식은 [남은 결정](BUILD_PLAN.md#남은-결정)에 올렸다.

멀티턴 뼈대(분류·세션)는 이미 MAIN103에 있다. 빠진 것은 판단 기록 지정 재지시, 10개 질문 연결, 에이전트 레이어 저장이다.

## 2026-10-24 멀티턴 설계를 위한 추가 확인

2026-10-24 확인 당시 활성 포인터는 MAIN103/output-unlimited-20261023-r1이었다. 새 [멀티턴 설계](MULTITURN_LEGAL_AGENT.md)는 온톨로지를 사용하는 목표 구조이며 런타임 전환은 수행하지 않았다. 기존 2026-10-23 근거·검증과 발송 문서는 당시 기록으로 보존한다. [추가 코드 지문](MULTITURN_EVIDENCE_20261024.json)은 이번 확인 당시의 작업/선택 코드와 보존 자료를 별도로 고정한다.

- `corrected_memory.Memory.resolve/execute`에는 후속 질문·사실/범위 수정·기존 사건 재진입이 이미 있다. 멀티턴 자체가 전혀 없는 시스템으로 설명하지 않는다. 명령 검증의 COMPOSE 종결과 새로운 턴/사건 완료 분리 계약을 함께 변경해야 한다.
- `completion_execution.CompletionExecution.completion_stage`는 신규 material gap·재진입 한도·예산이 허용되면 SELECT로 재진입한다. 반복·예산 소진 등에 제한 답변/원문 전달 경로도 있다. 이번 변경은 그 기반에 사용자 선택이 필요한 분기와 정상 턴 반환을 명시적으로 넣는 것이다.
- `unified_runtime.result_port`는 판단 투영과 accepted outcome을 조립하며 `final=True`, 일부 경로의 `investigation_status=COMPLETED`를 사용한다. `publication.prepare`는 FINAL, `unified_publication.validate_saved`는 READY와 현재 route·판단·근거를 확인한다. 턴 발행 완료를 조사 전체 완료와 분리하려면 출력·발행·저장·재개 소비자를 함께 바꿔야 한다. 이 표기만으로 모든 현재 제한 답변을 잘못된 완료라고 단정하지 않는다.
- 지식 설정은 여전히 management=false, consumer=off다. 조회 가능한 온톨로지·합성 경로·턴 상태가 연결된 새 기본 실행은 아직 없다.
- 사용자의 문서 단독 추출 불량 보고를 설계 동기로 기록했다. 이번에 해당 실험 원시 결과를 추가 확인하거나 새 품질 비교를 실행하지 않았다.

## 2026-10-24에 확인한 실행과 작업 코드 — 역사 기록

| 구분 | 확인한 값·상태 |
|---|---|
| 로컬 활성 포인터 | [ACTIVE_RELEASE.json](../../../../01_DATA/ACTIVE/local/ACTIVE_RELEASE.json): generation 103 |
| 선택 릴리스 | output-unlimited-20261023-r1, 코드 목록 420개 |
| manifest | [release.json](../../../../08_DEPLOYMENT/RELEASES/output-unlimited-20261023-r1/release.json); 포인터의 SHA-256과 일치 확인 |
| 선택 데이터 | 01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation; manifest에 결속된 경로이며 이번 작업에서 재구축하지 않음 |
| 품질 상태 | USER_DIRECTED_CUTOVER, quality_certified=false; v4나 읽기 판단 실험의 품질 통과를 뜻하지 않음 |
| 지식 기능 설정 | 작업 코드와 선택 릴리스 모두 management_enabled=false, consumer_mode=off |
| AD 설정 | ad_management.enabled=false. 독립 지식 관리 router와 AD 채팅은 별도 기능 |
| GENOS | 접근·활성화·현장 연결 확인 없음 |

[EVIDENCE.json](EVIDENCE.json)에 확인한 18개 경로의 작업/선택 코드 hash와 문서 근거, v3 16개 파일의 보존 기준을 저장했다. 이는 전체 작업 트리의 기능 동등성 검사나 서비스 실측이 아니다. request_entry·judgment_view·read_judgment·PIPELINE은 작업 코드와 선택 릴리스가 다르다. legal_knowledge의 주요 service·계약·계산기·router·viewer, corrected_memory, basis_links의 확인한 파일은 동일하다. 동일 파일이 있다는 것만으로 해당 기능이 활성 상태가 되지는 않는다.

## 2026-10-23~24에 확인한 실행 경로 — 역사 기록

[service.py](../../../../service.py)의 RAG_ASK에서 /v1/rag/ask의 native legal_agent로 들어간다. [request_entry.py](../../../../02_BACKEND/semantic_runtime/legal_agent/request_entry.py)의 prepare/augment 연결은 [knowledge_bridge.py](../../../../02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py)를 호출한다.

knowledge_bridge.prepare는 mode가 off이면 지식 조회를 소비하지 않는다. 켜더라도 인증 주체, 승인된 factory, 원문 결속이 필요하다. 현재 호출은 Service.plan에 query와 source binding을 전달하며, facts·context·as_of를 넘기지 않는다. augment는 안내 지식을 legal_review_guidance로 전달한다. 반환 단계 목록을 코드가 실행하는 컴파일러가 아니다.

따라서 현재 설정을 켜는 일만으로 대화에서 축적한 온톨로지가 현재 사건의 조건을 계산하고 경로를 자동 실행하게 되지는 않는다. 지식 회수와 실제 실행 계획 소비 사이의 연결을 추가해야 한다.

사용자 추가 요구에 따라 조문 도착 경로도 확인했다. unit_reading.read의 검증된 원문 반환, law_navigation.Investigation의 읽기 상태/관계 화면, unit_relations.catalog의 근거 있는 READ 선택지, relations_tools의 기존 관계 큐를 새 경로의 연결 지점으로 삼는다. 기존 기능을 합쳐 목적별 경로를 컴파일하고 동일 계획에서 설명·원문 묶음을 제공하는 전체 소비 경로는 아직 미구현이다. [추가 코드 지문](SOURCE_ENTRY_EVIDENCE.json)의 5개 경로는 초기 EVIDENCE.json과 별도이며 law_navigation·unit_relations는 작업/선택 코드가 다르다. [구체 변경 지도](SOURCE_ENTRY_COMPOSITION.md)를 따른다.

## 기존 기능의 활용 범위

2026-10-24 저장 구조 결정 이후 v4는 `legal_knowledge` 저장소(초안·게시)를 거치지 않는다. 아래 셋째 열은 2026-10-23 당시의 확장 구상이며, 현재 v4에서의 처리는 [프로토타입 설계의 기존 기능 처리](PROTOTYPE_DESIGN.md#기존-기능의-처리)를 따른다.

| 확인한 코드 | 현재 제공하는 기능 | 2026-10-23 당시 확장 구상 |
|---|---|---|
| [judgment_view.build](../../../../02_BACKEND/semantic_runtime/legal_agent/judgment_view.py) | 현재 head·허용 원문을 투영, 단계별 판단·이유·출처와 실행/재사용 표시. 작업 코드에는 읽기 판단 원장 연결 | 실제 사용자 표시 이벤트·정정 대상·전후 그래프 결속 |
| [corrected_memory.Memory](../../../../02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py) | 질문·범위·facts·제시 방식 변경, 사건 revision·변경 이벤트·재진입 | 원문/지식 객체를 정확히 고치는 typed 변경 명령과 시나리오 분리 |
| [basis_links.service](../../../../02_BACKEND/semantic_runtime/basis_links/service.py) | 원문 연결 제안·새 revision·검토 승인/반려/철회, expected revision/view hash | 다양한 의미 관계와의 정본 소유권·참조 연결 |
| [basis_links.chat](../../../../02_BACKEND/semantic_runtime/basis_links/chat.py) | AD의 명시적 목록·번호 승인/반려/취소, 표시 목록 결속 | 자유 대화에서 임의 온톨로지 정정을 수행하는 기능과 구분 |
| [legal_knowledge.Service](../../../../02_BACKEND/lawrag/legal_knowledge/application/__init__.py) | 초안·의존 검증·검토 기록·게시·롤백·feedback 후보 | (v4 경로에서 쓰지 않음) 당시 구상: 대화 후보 생산·정정 변환·시나리오 및 실행 소비 연결 |
| Service.impact | 현재 게시 묶음에서 참조 ID의 직접 의존 검사. scope= CURRENT_RELEASE_DIRECT_DEPENDENCIES | 여러 단계의 역의존, 정확한 revision별 사용 영향, 재계산 |
| [planning.assemble](../../../../02_BACKEND/lawrag/legal_knowledge/application/planning.py) | 범위·시점·조건·부족 입력을 포함한 안내 계획 | typed 입력/출력·실제 도구·실행 receipt를 갖는 계획 |
| [ontology.evaluate](../../../../02_BACKEND/lawrag/legal_knowledge/ontology/__init__.py) | 제한된 연산·타입·단위 검사, TRUE/FALSE/VALUE/UNKNOWN/CONFLICT | 검토된 원문 값 및 사건 입력의 안정된 결속, 그래프 결과 소비 |
| [관리 router](../../../../02_BACKEND/lawrag/api/routers/legal_knowledge.py)와 [viewer](../../../../02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js) | 객체·초안·게시·feedback·직접 영향·안내 preview | (v4 화면은 Streamlit) 당시 구상: 판단에서 정정하는 UI, 시나리오·전후 그래프 |

[contracts.py](../../../../02_BACKEND/lawrag/legal_knowledge/contracts.py)는 FIELD, METHOD, APPLICATION, WIKI_LINK, SHORTCUT_LINK의 다섯 kind를 지원한다. REF는 기존 CONCEPT·DEFINITION 등을 참조할 수 있다. STEP은 id·label·capability·after이며 노드별 실행 입출력 계약은 없다. FIELD는 값의 타입·단위 차원·목적을 정의하지만 독립적인 원문 기본값 객체를 제공하지 않는다.

현재 _feedback은 원래 요청이 검증된 사실인지 확인되지 않은 PROPOSED 후보를 저장한다. 피드백을 받았다고 지식이 자동 수정·게시되는 것은 아니다. _prepare_publication의 사람 검토 기록도 법률 정답 인증이 아니다.

[repository](../../../../02_BACKEND/lawrag/legal_knowledge/adapters/repository.py)는 불변 revision과 head/CAS를, [Oracle 어댑터](../../../../02_BACKEND/lawrag/legal_knowledge/adapters/oracle.py)는 주입된 연결·테이블 매핑을 사용한다. 실제 Oracle 연결/운영 테이블 생성이 완료됐다는 근거는 이 코드에 없다. 기존 로컬 case journal을 GENOS의 목표 저장 방식으로 삼지 않는다.

## 최근 실제 실패가 보여주는 요구

[ADR-1037 결과](../../../../04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/RESULT.txt)는 알려진 질문 하나에 대한 후보 실행이며 MAIN103의 모든 탐색 기능을 시험한 결과가 아니다. 당시 질문은 “양도차익을 산정할 때 양도가액에서 공제되는 경비는 무엇인가?”였다.

- 총 7회 모델 호출, 서비스 264.935초, 입력 214,852토큰·출력 3,925토큰. 출력 상한 필드·429·length 중단은 관측되지 않았다.
- 제97조는 읽었지만 시행령 제163조는 확보하지 않았다. 제한 답변은 반환했으며 법률 gold 채점은 하지 않았다.
- 다음 행동이 DEPENDENCY인데 source_ref가 null인 제안과 보정이 거부됐다. 같은 응답의 제97조 CORE 판단 제안도 함께 commit되지 않았다. 원문은 유지돼 최종 검토에서 사용됐다.
- 이전 판단은 보존됐지만 needs/conflicts는 처음부터 0개였다. 최종 설명에 대통령령 미확인이 있었으나 gaps는 비어 있었다. 등록 항목 보존과 부족 발견·기록은 별개다.
- 같은 연결 목록의 반복 재선택은 이 실행에서 없었다. 과거의 목록 왕복 문제와 이번 행동 검증 실패를 같은 원인으로 묶지 않는다.

이 근거는 판단·행동의 실패 경계, 외부 설명과 구조화 부족의 정합성, 실제 사용 이력의 필요성을 보여준다. 온톨로지 도입만으로 탐색 누락·정답률이 해결된다는 증거는 아니다. 실험의 상세 수치·제약은 원래 결과와 [manual-review.json](../../../../04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/artifacts/manual-review.json)에 보존한다.

## 이번 문서 작업의 검증 범위

2026-10-23의 기존 선택 코드 금액 비교 세 가지 합성 단위 확인은 FALSE/TRUE/UNKNOWN을 확인한 범위다. 새로운 모델·검색 효과 실험은 하지 않았다. 당시 문서·지문 검사는 [VALIDATION.json](VALIDATION.json)에 보존하고, 2026-10-24 변경 검사는 [VALIDATION_MULTITURN_20261024.json](VALIDATION_MULTITURN_20261024.json)에 분리한다. 이번 변경에서 계산기 단위 확인을 재실행하지 않았다. 재현 코드는 [검증과 도입](VALIDATION_AND_ROLLOUT.md)에 둔다.

프로토타입 서비스·새 API·UI·Agent/Gold 운영 저장·복구·MAIN 연결·GENOS 배포는 모두 이후 구현과 검증 대상이다.

2026-10-24 후속 [성능 입증 설계](PERFORMANCE_EVIDENCE_PLAN.md)를 추가했다. 알려진 후보 실패·사용자 추출 실패 보고·기존 계산기 단위 확인은 새 기준군 대비 우위의 증거가 아니다. 이번 후속은 연구 초록/출처와 기존 기록의 읽기 전용 확인, 평가 설계 및 문서 검사이며 새 모델 호출·재채점·비교 실행은 없다. [문서 검사 기록](VALIDATION_EVIDENCE_PLAN_20261024.json)에서 기존 자료 보존을 확인한다.

## 2026-10-24 MVP 작업 뒤 추가 확인

위 부팅 실패 기록은 정비 전 확인이다. ADR-1041 작업에서 v5·v6 프로필 고정값과 v6 엔진 프로필 결속을 맞췄고 기본 v6 원문 반환 API 및 합성 모델 정상·복구·요청 재사용 검사를 통과했다. 온톨로지 기능은 별도 `compiler-r4/rev-001` 후보이며88개 합성 검사와 A0/A1/A2 로컬 API 검사를 통과했다. 씨앗31개는 CANDIDATE 검토 대기, 실모델 호출0회다. 구버전 계약·실패 HTTP 재실행 등의 기존 문제는 남아 있다. [정확한 상태·제한·로그](../../../../04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler/artifacts/IMPLEMENTATION.md). 선택 MAIN103과 GENOS는 바뀌지 않았다.
