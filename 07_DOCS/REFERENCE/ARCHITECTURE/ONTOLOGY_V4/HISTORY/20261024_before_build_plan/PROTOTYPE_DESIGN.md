# 프로토타입 구현 설계

[v4 목차](../ONTOLOGY_V4.md) · [현재 상태](CURRENT_STATE.md) · [검증과 도입](VALIDATION_AND_ROLLOUT.md)

## 구축 결정 반영 — 2026-10-24 (최신)

구현 순서는 [구축 순서와 확정 결정](BUILD_PLAN.md)의 단계 0~8을 따른다. 아래 P0~P5 구상은 그 단계로 대체했다. 운영 반영도 바뀌었다. 이전 구상은 전체를 한 번에 교체하는 것이었으나, 사용자 결정에 따라 **단계 1·2를 묶어 먼저 MAIN에 반영하고 나머지는 그 뒤에 반영**한다. 각 반영 묶음 안에서는 조사 제어·저장·표시·재개가 같은 계약이어야 하며, 한 요청이 구 계약과 새 계약을 섞어 쓰지 않는다.

## 공통 실행 계약 변경 — 2026-10-24

아래 세 흐름을 [온톨로지 기반 멀티턴 조사](MULTITURN_LEGAL_AGENT.md)의 한 실행 계약으로 묶는다. 사용 중 관찰한 목적·필요 자료·선택·오류·정정을 원문 지식 후보로 생산한다. 매 턴 확인한 답·미확인·다음 경로 안내·실제 행동과 미실행 이유를 전달하고, 후속 선택은 같은 사건/표시 revision에서 이어간다. 문서 전체를 사전에 의미 추출해 완성하는 것을 선행 조건으로 두지 않는다.

개발·검사는 단계별로 한다. 운영 반영 단위는 위 최신 결정(단계 1·2 묶음 먼저, 나머지 이후)을 따르며, 각 묶음은 진입·조사 제어·원장·발행·화면·후속 재개가 같은 계약인 호환 가능한 릴리스여야 한다. 기존 읽기·조회·권한·저장 기능은 재사용한다.

## 독립적으로 구현해야 할 세 흐름

첫째, 조문에 도착하면 관계·개념을 회수하고 목적별 경로를 컴파일한다. 같은 계획에서 설명을 자동 생성하고, 사용자 또는 기존 조사 LLM이 묶음을 선택하면 확정된 경로의 원문과 적용 상위 조건을 가져온다. 이전 수정 이력이 없는 첫 조사에서도 작동해야 한다. [조문 진입의 상세 실행 계약](SOURCE_ENTRY_COMPOSITION.md)을 필수 구현 범위로 둔다.

둘째, 사용자가 답변의 판단과 실제 원문을 보고 잘못 연결된 근거를 정정한다. 정정은 원문에 결속된 후보·새 revision으로 보존되고, 다른 질문에서도 같은 원문에 도달하면 검토된 내용을 찾는다. 셋째, 사용자는 같은 그래프에서 한도 값을 가정상 바꾸고 영향을 받는 조건·판단과 변경 전후 결과를 확인한다. 정정·계산 화면만 구현하고 첫째 흐름을 미구현으로 남겨두면 프로토타입 완료가 아니다.

초기 구현은 작은 합성 규정과 제한된 검토 지식을 사용한다. 실제 법령 전체에 대한 해석 완전성·자연어 조건의 자동 계산·전사 전역 영향 분석은 성공 조건으로 잡지 않는다. 다음 내용은 모두 **구현 제안**이다. 신규 모듈·API·계약·설정은 아직 생성하거나 활성화하지 않았다.

## 실제 연결할 코드

| 책임 | 현재 진입점·함수 | 제안 변경과 소비자 |
|---|---|---|
| 질의와 원문 조사 | service.py의 RAG_ASK → /v1/rag/ask → legal_agent/request_entry.py | 기존 진입·조회 능력 재사용. 초기 목적과 후속 선택을 사건/턴에 결속하고, 원문 도달 후 지식 묶음과 턴 반환 지점 구성 |
| 조문 진입·관계 회수 | legal_agent/unit_reading.read → law_navigation.Investigation의 add_reads/register_read·reference_overview·view, unit_relations.catalog | 검증·저장된 읽기 상태에서 원문 anchor별 회수와 경로 준비. 기존 관계 목록·receipt 재사용; 원문 획득과 사용자/모델 전달은 별도 상태 |
| 판단 기록·표시 | legal_agent/judgment_view.py의 build, 기존 journal 및 작업 코드의 read_judgment | 기존 원장을 투영해 이유·원문·미확인·행동을 표시. 사용자 표시 이벤트와 정정 대상 revision 추가. 별도 판단 정본 생성 금지 |
| 턴 전환·조사 재진입 | legal_agent/completion_execution.py, corrected_memory.py의 resolve/execute | material gap이면 재진입하는 현재 조건에 목적·선택 경로·새 분기·무진전·턴 예산을 연결. 정상적인 사용자 선택 대기와 오류 복구 분리 |
| 응답·발행 | legal_agent/unified_runtime.py의 result_port, publication.py, unified_publication.py | 턴 응답 완료와 사건 조사 완료를 분리한 버전 계약, 출처·상태 검증·저장·스트리밍·텍스트/그래프 소비자 일치 |
| 턴 분류·판단 재지시 (단계 2) | legal_agent/memory_methods.py의 METHODS, corrected_memory.py의 resolve·investigation_hints | JUDGMENT_OVERRIDE 추가, 이전 질문 조회 1개 → 같은 세션 최근 10개, 분류 입력에 턴 목록과 판단 그래프. [상세](MULTITURN_LEGAL_AGENT.md) |
| 판단 기록 통합 (단계 1) | legal_agent/read_judgment.py(작업 코드에만 있음), unit_relations.py, relation_read_policy.py, judgment_view.py | 연결 판단·미판단 후보·읽기 판단에 고정 ID, 판단 그래프 v1. read_judgment를 MAIN 경로에 통합 |
| 판단 모음·승인 화면 (단계 4~5) | 03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py | 개념 묶음 승인·수정·쪼개기·합치기·반려, 스키마 제안·시뮬레이션, 필드 매핑 화면. [상세](CONTROLLED_KNOWLEDGE.md) |
| 대화 변경 | legal_agent/corrected_memory.py의 Memory.execute | 기존 사건 사실/질문 수정과 지식 정정·가정 변경을 분리하는 어댑터 추가. 기존 facts 문자열 수정만으로 그래프 정정 완료 처리 금지 |
| 관계 근거 | basis_links/integration.py, service.py, chat.py | 기존 내규–외규 연결 ID·원문·검토 이력을 참조. 범용 의미 관계와 같은 내용을 이중 정본으로 저장하지 않음 |
| 지식 후보·게시 | lawrag/legal_knowledge/application의 Service.command, _save_draft, _prepare_publication, _publish | 정규화 결과를 기존 초안·검토·게시 절차로 연결. 신규 계약은 버전으로 구분하고 기존 v1 소비자를 유지 |
| 지식 회수 | legal_agent/knowledge_bridge.py의 prepare/augment, Service.plan | 원문 anchor·개념·현재 범위·시점을 전달하는 명시적 확장. query 문자열 안내를 실행 계획으로 오인하지 않음 |
| 조립·조건 평가 | application/planning.py의 assemble, ontology.evaluate | 안내 계획과 typed 실행 계획을 분리. 검증된 입력 결속·의존 관계만 실행하고 결과 receipt 생성 |
| 영향 | Service.impact | 기존 직접 참조 결과 보존. 별도 버전 계약으로 역의존의 전이 폐쇄와 실행 사용 이력 추적 추가 |
| 저장·권한 | adapters/repository.py, adapters/oracle.py, ReferencePort | 기존 CAS·불변 revision·접근 검사 재사용. Agent 후보/실행 포트와 Gold 게시 포트를 책임에 맞게 분리 |
| API·화면·CLI | lawrag/api/routers/legal_knowledge.py, api/viewer/legal_knowledge/, lawrag/pipeline/legal_knowledge.py | 동일 인증·origin 검사·service factory에 새 기능 연결. 독립 관리 앱·별도 게시 파이프라인을 만들지 않음 |

경로는 모두 저장소의 02_BACKEND 아래 상대 경로다. 실제 함수 근거와 활성화 조건은 [현재 상태](CURRENT_STATE.md), 코드 지문은 [EVIDENCE.json](EVIDENCE.json)에 둔다. 후보에서 추가된 읽기 판단을 MAIN 기능으로 전제하지 않는다. 구현 시 필요한 변경만 작업 코드와 통합하고, 후보 snapshot 전체를 덮어쓰지 않는다.

## 모듈 경계 제안

기존 lawrag/legal_knowledge/application 안에 다음 책임을 추가한다. 파일명은 구현 제안이며 기존 application service가 유일한 변경 조정자가 된다.

지식 변경은 위 application service가 조정하고, 대화 턴·조사 제어·응답 발행은 기존 legal_agent 실행기가 소유한다. 같은 요청의 상태/예산을 두 조정자가 각각 관리하는 별도 챗봇이나 중복 재시도 실행기를 추가하지 않는다.

| 제안 모듈 | 입력 | 출력·소비자 |
|---|---|---|
| bundling.py | 에이전트 레이어의 판단 기록·재지시·정정, 용어집 개념 | 개념 묶음 후보 → 승인 화면 |
| schema_proposals.py | 새 필드 제안, 임시 JSON 지식 후보, 샘플 판단 기록 | 형식·변환 손실·재생·골드 규약 시뮬레이션 결과 → 스키마 제안 화면 |
| field_mapping.py | 임시 JSON 필드, 골드 승인 위치, 기존 Oracle 테이블 매핑 | 필드별 상태·불일치 → 매핑 화면, 게시 차단 |
| normalization.py | 판단/대화 참조, 원문 receipt, 허용 타입 registry, 표시 revision | 제한된 지식 후보 + 미매핑 표현 → 검토 UI와 changes |
| changes.py | 대상·expected revision·허용 patch·operation ID·권한 | 차이·영향 미리보기 또는 새 revision receipt → 기존 게시 및 시나리오 |
| compilation.py | 게시 지식·목적·원문 anchor·typed facts·시점·능력 allowlist | 목적별 고정 계획·같은 계획의 설명·미실행 블록 → 경로 선택/화면·기존 도구 실행기 |
| scenarios.py | 기준 snapshot·변경분·실행 계획 | 전후 결과·영향 경로·실패/미확인 → 비교 UI와 Agent 실행 기록 |

관계 타입·연산자·합성 허용표는 계약 registry 한 곳에서 관리한다. LLM 프롬프트마다 별도의 타입 목록을 복제하지 않는다. 모델에는 서버가 만든 선택 목록·템플릿 버전을 전달한다. 미지원 표현은 원문 그대로 보존하며 운영 registry를 수정하지 않는다.

## 필요한 계약과 변경 범위

| 계약 제안 | 반드시 고정할 정보 | 기존 소비자 처리 |
|---|---|---|
| 판단 표시 봉투 | run/판단 ID, revision, 원문 refs, 표시 hash, 이유 제공 여부, 실제 실행 상태 | 기존 judgment_view에 명시적 확장. 원장은 그대로 유지 |
| 턴 결과·후속 선택 | case/turn/revision, 확인한 답·부족·짧은 경로 안내·실제/권장 행동, option/plan ref, 누적 예산·원문/지식 binding | 기존 RAG 응답·발행·화면·후속 요청이 같은 버전 소비. 한 턴 발행을 조사 전체 완료로 해석하지 않음 |
| 정규화 후보 | 원래 의견, 타입/템플릿 버전, 값·단위·범위·근거, 미매핑·충돌, 검토 상태 | Agent에 저장. 골드 definition으로 바로 캐스팅 금지 |
| 변경 명령 | 정정/사실 변경/시나리오 구분, 대상 ref, expected revision, view hash, 제한된 patch, operation ID | 기존 명령 멱등성 적용. 자유 JSON patch·임의 필드 쓰기 금지 |
| 조문 진입·경로 묶음 | 출발 원문·목적·허용 합성·목표 범위·상위 조건·종료 기준, 표시 plan hash와 선택 상태 | 새로운 대화에서도 작동. 아래 실행 계획·receipt 공유; 별도 골드 kind 신설 불필요 |
| 실행 계획 | 입력/출력 변수·타입·의미·단위, source binding, dependency refs, 실행 능력, 예산 | review-plan-v1과 구분. 구 소비자는 지원하지 않는 실행 계약을 실행하지 않음 |
| 실행 receipt | 계획/입력 hash, 시작·완료·실패, 실제 읽은 원문, 결과와 부족, 누적 예산 | UI·답변·감사·재개가 같은 receipt 소비 |
| 사용 이력·역의존 | 정확한 지식 revision과 이를 사용한 계획/판단/답변 revision | 영향 조회와 캐시 무효화. 단순 문서 관련성으로 결과 의존 생성 금지 |

필드와 의미 관계의 영속 계약 확장은 [제한된 지식 형식](CONTROLLED_KNOWLEDGE.md)을 따른다. 스키마 v4를 한꺼번에 새로 만들지 않는다. 신규 계약을 도입하면 producer·consumer·이행 범위와 거부 동작을 명시한다. 과거 설명문을 자동으로 실행 규칙으로 변환하지 않는다.

## API 제안

지식 관리·시나리오 보조 API는 기존 /v1/legal-knowledge 관리 router 아래로 한정한다. 사용자 조사·후속 선택의 주 진입은 기존 /v1/rag/ask이며 아래 route API도 같은 사건·권한·예산·receipt를 소비한다. 아래 신규 경로는 **현재 존재하지 않는다**. endpoint 이름 확정은 기존 COMMAND 계약과의 중복 검토 후 한다.

| 제안 경로 | 동작 | 쓰기 경계 |
|---|---|---|
| POST /graph | 원문·지식 revision·권한 범위의 그래프 투영 | 지식 변경 없음; 불완전 탐색 표시 |
| POST /routes/preview | 원문 anchor의 관계 회수 → 목적별 경로 컴파일 → 같은 계획의 설명 생성 | Gold 변경 없음; Agent에 계획/표시 revision 기록 |
| POST /routes/{plan_id}/run | 선택한 고정 계획으로 필요한 원문·상위 조건 획득 | 기존 조사 예산·도구 사용, Agent 실행 receipt와 원문 묶음 |
| POST /normalizations | 선택한 대화·판단을 허용 형식의 후보로 저장 | Agent 후보만 생성 |
| POST /changes/preview | 유효한 대상과 제한된 변경의 전후·영향 표시 | 원본과 Gold 변경 없음 |
| POST /scenarios | 기준 snapshot과 가정 변경 저장 | Agent 시나리오 revision |
| POST /scenarios/{id}/run | 고정한 시나리오를 컴파일·실행 | Agent 실행 receipt; Gold 불변 |

실제 지식 정정 저장·게시·롤백은 기존 POST /commands를 확장해 재사용한다. 실행 ID별 결과 조회·중복 처리도 기존 operation 조회 계약에 연결한다. 경로 실행·시나리오 실행·정규화 요청은 operation ID를 받으며, 응답 유실 시 같은 ID를 조회한다. 재실행 버튼이 새 예산으로 기존 실행을 은밀히 재시작하지 않는다.

위 경로 API는 사용자 화면용 어댑터다. RAG의 조문 진입 hook은 같은 service의 제안 메서드 plan_from_anchor → compilation → 고정 계획 실행을 직접 호출하며 자기 HTTP API를 재호출하지 않는다. 조회·컴파일·기본 설명 렌더링은 코드가 하고, 목적 선택은 기존 조사 판단 호출을 활용한다. 단순 화면 재표시로 새 LLM 호출이나 원문 조회를 만들지 않는다.

기존 /preview는 query와 source binding 기반 안내 계획이다. 새 /changes/preview와 의미가 다르며 구 경로를 조용히 다른 계약으로 바꾸지 않는다. 모든 endpoint는 실제 service factory·인증 주체·문서 권한을 주입받아야 한다.

## 저장과 조회

Agent 레이어에 대화 원장 참조, 공개 판단, 정정 후보, 표시 이벤트, 시나리오와 실행 receipt를 둔다. Gold에는 게시된 원문 중심 개념·관계·조건·방법을 둔다. 현재 repository의 namespace 기능만으로 두 데이터 레이어가 실제 분리됐다고 간주하지 않는다. 연결 factory와 테이블 매핑을 별도로 설계·검증한다.

각 지식은 원문 판본·조항·span과 content hash를 참조하고, 발견한 질문·판단·사용자 수정 이력을 역참조한다. 각 사용 이력은 정확한 지식 revision을 가리킨다. 원문 본문·모델 입출력 전체를 모든 레코드에 복사하지 않는다. 영향 조회는 범위와 권한을 명시한 페이지·작은 배치로 수행한다.

Oracle에서 필요한 부분만 조회하고 서버 요청 동안 사용한다. 프로토타입은 합성 데이터와 기존 저장 포트의 테스트 어댑터를 사용할 수 있다. 실제 골드 테이블 도입은 기존 메타 정의서·표준명·도메인·권한·DBA 신청 절차를 거치며, 현재 문서는 운영 DDL이나 등록 완료를 확정하지 않는다.

## 화면 제안

기존 /legal-knowledge/ 화면과 RAG의 원문·판단 표시를 연결한다. 매 턴 먼저 확인한 답과 미확인 항목을 보여주고, 경로마다 무엇을 확인할 수 있는지 짧게 설명한다. 미읽은 본문은 요약하지 않으며 당시 선택·시도·미실행 이유와 다음 권장 행동을 펼쳐볼 수 있게 한다. 선택 뒤에는 실제 확보 원문을 묶음 안에서 확인한다. 판단 정정과 변경 비교도 같은 선택 대상에서 연다. 그래프 미지원 채팅은 같은 상태를 표·텍스트로 제공하고 자연어 선택을 받는다.

1. 왼쪽: 선택한 판단, 당시 이유, 실제 인용, 범위, 미확인, 수정 이력. 사용자가 어떤 부분을 정정하는지 고를 수 있다.
2. 가운데: 필요한 원문·개념·조건·값과 관계. 선택한 경로와 실제 실행 경로를 구분하고 부모 본문 조건을 함께 표시한다. 미확보 원문은 존재하는 원문 노드처럼 채우지 않는다.
3. 오른쪽: 정정/가정 변경, 기존 값과 변경 값, 영향받는 판단, 전후 결과, 재검토·실패. 원문 정정과 한도 가정 변경을 명확히 구분한다.

각 노드·연결은 안정된 ID와 revision을 갖는다. 화면 번호와 라벨 변경이 객체 의미를 바꾸지 않는다. 사용자에게는 업무 이름과 출처를 보여주고 기술 hash는 상세 기록에 둔다. 색만으로 후보·검토됨·미확인·실패를 구분하지 않고 텍스트 상태를 함께 표시한다.

## 구현 순서와 완료 조건

[구축 순서](BUILD_PLAN.md#단계)의 단계와 이전 P0~P5의 대응:

| 구축 단계 | 이전 구상 | 내용 |
|---|---|---|
| 0 샘플 13문항 | P0 fixture | 합성 fixture에 더해 CM·risk_cm·양도 필요경비 실제 질문 |
| 1 판단 기록 통합 | P1 판단 전달 | 세 종류 판단 기록에 고정 ID, read_judgment MAIN 통합 |
| 2 재지시·턴 분류 | P2 턴 제어 일부 | 판단 지정 재지시, 10개 질문 연결. 1·2 묶어 MAIN 반영 |
| 3 스키마 v0 | P0 계약 일부 | 세부 조항 구조 다섯 항목, 임시 JSON, 시뮬레이션 |
| 4 판단 모음·승인 | P3 사용 관찰 | 개념 묶음 승인 화면, 게시 |
| 5 골드 매핑 | 신규 | 필드 단위 매핑 화면 |
| 6 조문 진입 경로 | P1·P2 조문 진입 | 승인 지식으로 목적별 경로 묶음 |
| 7 GENOS 이식 | P5 일부 | 에이전트 레이어 세션 저장, Dataiku 배포 |
| 8 조건 변경 | P4 시나리오 | 100만 원 → 200만 원 |

단계별로 실제 API에 주입한 작은 fixture에서 검증한다. 실모델 의미 품질·탐색 효과 비교는 별도 ADR을 선점·동결한 뒤 수행한다. 정상·실패·재개·동시 수정 검사는 [검증과 도입](VALIDATION_AND_ROLLOUT.md)의 수용 기준을 따른다.

기능은 기본 비활성의 격리 후보에서 단계별로 개발·검증한다. 운영 반영은 위 반영 묶음 단위로 하고, 묶음 안에서는 턴 제어·지식 소비·표시·재개가 같은 계약이어야 한다. MAIN 반영을 요청받은 구현의 완료 범위는 동일 코드 검증·승격/선택·실제 service 진입점 확인까지다. GENOS는 별도 반입·배포·워크플로우 테스트 기록이 필요하다. 이번 설계 저장은 어느 단계의 실행 완료도 뜻하지 않는다.
