# 모델 데이터 전달 경로 수정 계획

2026-09-29 · 설계안 · 구현·모델 호출·새 실험·MAIN 전환·GENOS 배포 미실행

## 1. 수정 방향과 적용 순서

**모델에게 보여 줄 자료를 단계별로 명시하고, 같은 출처의 본문은 요청 안에서 한 번만 정의하며, 출처·구조·관계·진행 상태를 ID로 연결한다.** 원문의 조건·예외를 요약하거나 잘라서 입력량을 줄이는 방식은 적용하지 않는다.

첫 적용 범위는 현행 v5의 검색 계획 → 근거 선별 → 답변 작성이다. 이어서 명시 도구 탐색·관계 카드와 용어 의미 검토·참조 해소에 같은 원칙을 연결한다. PDF 구조화는 프로토콜별 측정과 텍스트 반복 정리부터 진행한다. 사용자 출처 API와 감사 원장의 저장 중복(DATA-10)은 별도 후속 범위다.

| 순서 | 작업 묶음 | 해결 항목 | 완료 산출물·종료 조건 |
|---|---|---|---|
| P0 | 전달 계약·실제 요청 계측 | 전 단계 공통 | 단계별 필드 계약, 실제 전송 내역·복원 매핑·버전 검증 설계 |
| P1 | 작성 자료 집합 제한 | DATA-05 | 선택 근거와 명시된 필수 연결 근거만 포함; 남는 공간 채우기 제거 |
| P2 | 선별 관계 공통화·작성 출처 표현 | DATA-01~04, DATA-06 | 동일 표시 관계 통합, 출처 이름표, 공통 본문·근거 번호 복원, 요구 정의/상태 분리 |
| P3 | 검색 계획·도구 탐색 연결 | DATA-06~07 | 문서 ID 폐쇄 선택, 문서·마디·witness 사전과 edge 참조, 도구·페이지 계약 유지 |
| P4 | 용어 의미 검토·참조 해소 연결 | DATA-08 | 전체 원문 한 번+문장 범위 참조; 기존 검증·인용 복원·재개 계약 유지 |
| P5 | PDF 구조화 분기별 정리 | DATA-09 | 기본 basic 검증, compact/legacy 실제 호출별 계측, 필요한 이미지·문맥 보존 |

P0를 먼저 정하고 P1·P2를 하나의 첫 검증 후보로 만든다. P3 이후는 별도 검증 범위로 나눈다. 이 순서는 개발·검증 순서이며, 각 묶음을 검증 없이 MAIN에 순차 적용한다는 의미가 아니다.

## 2. 현재 실행 경로와 기준 상태

- 로컬 활성 포인터: `legal-agent-structure-catalogue-pecab-repair-20260929-r1`, generation **31**, `quality_certified=false`.
- 원문·색인 기준: `01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation`.
- 포인터가 지정한 release manifest의 SHA-256 일치를 확인했다. 핵심 전달 파일 6개(`gateway`, `relation_views`, `source_selection`, `relations_repository`, `numbered_references`, `bounded_source_session`)는 작업 코드와 선택 frozen 코드의 SHA-256이 같다. 전체 작업 코드가 frozen 코드와 동일하다고 확장하지 않는다.
- 실제 요청 계측의 출처는 기존 감사의 **39회 물리 요청**이다. ADR-0557 당시 generation 30의 기록이며, 현재 generation 31로 새 요청을 실행한 결과가 아니다. 여러 단계·반복 호출이므로 독립 질문 39개로 취급하지 않는다.
- 현재 Codex에서는 GENOS에 접근할 수 없다. GENOS 코드 연결은 저장소 자료로 확인했고 현장 모델·배포·지연은 미확인이다.

RAG의 연결은 `service.py._resolve_binding()` → 선택 코드의 `semantic_runtime.app` → `PIPELINE.json`의 `legal-rag` → `ServingLegalAgent`다. v5 프로필에 따라 `BoundedSourceSession` 또는 `ObligationSession`으로 들어간다. bounded 선별은 `_Gateway`, 일반 작성·검토는 `ModelGateway`를 사용한다. 두 gateway를 함께 다뤄야 전체 경로가 바뀐다.

용어 정의 검토는 `pipeline.py glossary review …` 및 통합 구축의 검토 경로 → `glossary_review.run()` → `Genos.call()`이다. RAG의 `compact_wire_view()`를 통과하지 않는다. 참조 해소와 PDF 구조화도 별도의 호출 경계를 갖는다.

## 3. 목표 전달 계약

### 3.1 공통 정의와 단계별 자료

새 내부 계약 이름은 **제안** `model-presentation-v1`이다. 모델 입력용 표현과 복원 영수증을 정의하며, 원문 DB·외부 `term-runtime-v1` 응답·용어 검토 정본을 대체하지 않는다.

| 공통 정보 | 서버에서 식별하는 단위 | 모델이 받는 정의·참조 |
|---|---|---|
| 문서 | 문서 ID+선택 판본/원본 해시+세대 결속 | 문서명·기록된 판본, 짧은 문서 번호 |
| 구조 마디 | 문서 판본+unit ID+부모 구조 | 장·절·조·항·호의 저장된 표기·표제, 부모 번호 |
| 원문 | 같은 판본의 canonical block과 정확한 범위 | 공통 본문 한 번, 본문 번호 |
| 인용 가능한 근거 | 기존 evidence ID+선택 상태+정확 범위 | 기존 요청 내 근거 번호와 공통 본문/구간 참조 |
| 관계 | 출발·대상·방향·종류·해소·적용범위·witness | 노드·witness 번호, 구분되는 관계 의미·상태 |
| 검색 경로 | 질의·branch·참조 발생 기록 | 질의 정의 한 번, 묶은 경로·반복 상태 |
| 질문 요구 | 기존 obligation ID와 question_refs | 요구 정의 한 번, ID별 진행 상태·근거 |

본문이 같다는 이유만으로 다른 문서·판본·권한 범위를 합치지 않는다. 모델이 필요로 하는 원문 범위를 요청 안에서 공유하는 것이며, 문서 전체를 매번 추가하라는 뜻이 아니다. 독립 호출은 각자의 필수 본문을 다시 포함한다.

초기 구현은 정확히 같은 canonical 범위의 중복 제거부터 한다. 부분 중첩은 같은 판본·블록에서 원문 일치와 구간 대응을 증명할 수 있을 때만 합친다. 불연속 범위를 이어 붙일 때 누락 구간·구분자를 표시하고 FULL/PARTIAL 상태를 보존한다. 증명하지 못한 범위는 별도 본문으로 유지한다.

여러 기존 evidence가 한 본문을 공유해도 근거 번호를 하나로 합치지 않는다. **본문 사전과 인용 근거 목록을 분리**하고 각 기존 번호가 어느 본문 구간을 뜻하는지 보존한다. 모델 출력은 기존 근거 번호로 받아 기존 evidence ID로 복원한다.

### 3.2 단계별 허용 범위

| 단계 | 전송할 자료 | 전달 계약 |
|---|---|---|
| 검색 계획 | 질문·허용 문서 사전·사용 가능한 검색 기능 | schema는 짧은 허용 문서 ID를 선택; 서버가 기존 문서명 계약으로 복원 |
| 탐색 | 후보·구조 이름표·필요한 preview·실행 가능한 도구 인자 | 도구 handle/cursor와 페이지 상태는 유지; 읽지 않은 preview를 정확 근거로 처리하지 않음 |
| 선별 | 후보표·요구·원문/명시 발췌·관련 경로 | 표시 후 중복 통합을 수행한 다음 고유 경로 한도 적용; 생략 수 보존 |
| 작성 | 선택 근거·명시한 필수 연결 근거·요구·출처 이름표 | 과거 observation의 미선택 본문은 자동 추가하지 않음; 탐색 이동 번호는 제외 |
| 검토/반론 | 초안 주장·해당 정확 원문·요구 대응·후속 행동 | 현재 검토 활성화 정책 유지; 새 형식 때문에 검토를 자동 활성화하지 않음 |
| 오류 수정 | 해당 요청의 같은 유효 자료·이번 오류·필요한 이전 출력 | 번호·허용 집합·프로젝션 버전 고정; 과거 오류 봉투를 누적하지 않음 |
| 구축 검토 | 후보·범위·원문 한 번·문장/참조 위치 | 서버에서 정확 인용문·해시를 복원하고 기존 정본 검증 수행 |

### 3.3 전송과 검증을 함께 연결

공통 순수 함수 모듈 `lawrag.core.model_presentation`과 `00_SYSTEM/SCHEMAS/model-presentation-v1.schema.json`을 **제안**한다. provider·DB·검색에 의존하지 않는 자료 사전/범위 처리·검증을 공유하고, 각 caller의 단계 자료 선택은 기존 모듈에서 맡는다. 새 실행기를 만들지 않는다.

RAG에서는 `compact-v5-v2`를 **제안**하며 기존 `compact-v5-v1`과 구분한다. 요청 생성과 `relations_repository.reserve_attempt()`가 같은 버전의 순수 프로젝션을 실행하고, 저장 입력·번호 매핑·실제 전송 hash를 대조한다. 원문·구조 정보는 긴 ID가 제거되기 전에 구성해야 한다.

현재 `NumberedReferences.project()`는 일반 `id`와 private 필드를 제거한다. 새 문서·마디·본문 사전을 그냥 추가하면 참조가 사라질 수 있다. 새 namespace의 수집·투영·해소를 명시하고 기존 source/obligation/claim 번호의 의미를 유지한다. 작성의 탐색 번호 제거가 출처 이름표 사전까지 지우지 않게 한다.

영수증에는 projection 버전, 저장 입력 hash, 실제 요청 hash, typed 번호 매핑, 각 근거의 본문·정확 범위 대응, 실제 전달 집합과 역할을 남긴다. 저장본에서 모든 선택 evidence의 원문을 재구성해 검증하고 성공한 물리 전송만 전달로 인정한다. 전송 성공은 모델 이해·검토 완료를 뜻하지 않는다.

## 4. 구체적인 변경 지도

아래 파일명은 각 기존 디렉터리 안의 현행 파일이다. 신규 이름은 모두 제안이며 아직 생성하지 않았다.

| 위치·함수 | 변경 내용 | 소비자·연결 검사 |
|---|---|---|
| `legal_agent/relation_views.py:build_view` | compose에서 `preferred`를 과거 observation 전체로 채우지 않음. 선택 근거와 명시한 연결 근거 집합으로 구성. relation assessment가 `required`를 확대하는 부분도 역할·선택 범위와 대조 | 저장 view·전송 view·작성 visibility가 같은 허용 집합을 설명하는지 검사 |
| `workflow_tiers_session.py:select`, `commit_draft`, `relation_requirements` | 자료 역할과 인용 가능 여부를 명확히 함. 연결 자료가 법적 주장에 필요하면 선별 결과에 포함; 문맥만 필요한 자료는 인용 불가로 명시 | 기존 selected-only 인용 검사·정참조/역참조 방향·witness/target 검증 유지 |
| `source_selection.py:provenance`, 내부 `card`, `compact_view` | 내부 참조 기록을 유지하고 최종 표시 기준으로 관계를 묶음. 원래 관계·발생 구간·branch는 매핑 영수증으로 연결. 공통 문서·질의·출발 마디 사전 사용 | 원래 후보 집합·전체 경로 원장 유지. 상세/압축표 각각 투영 후 중복 검사 |
| `gateway.py:compact_wire_view`, `ModelGateway.request` + `bounded_source_session.py:_Gateway.request` | 단계별 새 프로젝션. 작성 본문·출처 사전과 기존 근거 번호를 연결. 모델에 불필요한 span 객체는 서버 대응표로 이동 | system 지침·wire schema·오류 수정·SSE 경로·물리 요청 byte gate 일치 |
| `numbered_references.py` + `relations_repository.py:reserve_attempt` | 새 사전 ID 처리와 매핑 검사, 버전별 결정론 재계산, 실제 전달 범위 증명 | stale view·위조 번호·본문 변조 거부. 과거 영수증은 당시 버전으로 읽음 |
| `exploration_tools.py:ancestors`, `location` + `workflow_tiers_session.py:build_bundle` | 저장 구조에서 표시용 이름표 생성. build_bundle의 조상 표기 조합 로직을 재사용할 순수 helper로 분리 | 출력 출처와 모델 출처의 조문 위치 일치. 제목/판본 누락은 미확인 표시 |
| `question_obligations.py:obligation_view`, `obligation_status` | wire에서 요구 정의와 상태를 분리. 원질문은 한 번, 실제 원질문 구간임을 검증할 수 있는 question piece는 범위 참조 가능 | 기존 원장/결과 상태 유지, 모든 실제 요구·배경의 대응 검사. 비연속/변환 구간은 별도 text 유지 |
| `source_query_planning.py:catalogue_schema`, `validate_catalogue` + `BoundedSourceSession.plan_request_search` | 허용 문서 사전과 ID enum; decode한 결과를 기존 문서명 계약에 넘김 | DIRECT/OUT_OF_DOMAIN/BROWSE/SEARCH, category, 명시 문서·약칭 분기 유지 |
| `workflow_tiers_views.py:menu`, `build` + `workflow_relation_cards.py:references` | 문서·구조·개념·witness를 공통화하고 관계는 ID로 연결. 원장이 갖는 구분 정보 유지 | 페이지·도구 인자·읽기 상태·구분되는 적용범위·notice hash 검사 |
| `glossary_senses.py:pair_context`, `validate_context`, `hydrate` + `glossary_review.py:run` | 정본 context는 유지하고 전송 adapter에서 evidence.text를 source ID/범위 참조로 표현. 문장 ID·원문·예외 문맥 유지 | 응답 검증·인용 복원은 정본 context로 수행. context hash와 wire hash 별도 기록 |
| `reference_resolution_repository.py:case_view`, `save_view` 및 해당 model caller | batch의 공통 원문/witness 사전, case별 후보·범위·폐쇄 선택 유지 | candidate_set hash·case 완전성·자동 승인 이전 기존 검증 유지 |
| `recipe_runtime.py`, `recipe_basic.py`, `recipe_compact.py`, `recipe_regions.py` | 호출별 텍스트·schema·이미지·출력 예약 계측. family의 반복 원문 표현과 완료 규칙 전달 필요성 검토 | basic/compact/legacy 각각 검사. 독립 family 호출에 필수 문맥 누락 금지 |

### 작성 자료의 두 집합

`selected_citable`은 실제 선택된 근거다. `required_context`는 특정 선택 근거·요구·명시 관계에 연결되고 필요한 이유가 기록된 문맥이다. 작성 본문은 이 둘의 합집합과 일치해야 한다.

예외·위임·반대 근거 자체가 법적 주장을 뒷받침한다면 `selected_citable`로 채택해야 한다. 후보가 부족하면 기존 선별/추가 읽기 경로에서 보완하거나 미확인을 남긴다. `required_context`를 핑계로 기존 미선택 자료 전체를 다시 넣거나, 전달만 했다는 이유로 인용을 허용하지 않는다. 현재의 selected-only 검증을 우회하지 않는다.

연결 자료 추가에는 출발 선택 근거·요구 ID·관계 ID 또는 구체적 문맥 필요 이유·서버가 검증한 정확 범위를 남긴다. 단지 같은 문서이거나 과거에 읽었다는 이유는 추가 조건이 아니다. 불필요한 자동 확대와 필요한 연결 누락을 함께 검사한다.

### 선별 관계를 묶는 기준

모델에 보이는 출발·대상·방향·해소·predicate·범위·승인 상태가 같을 때 설명은 한 번으로 묶는다. 같은 설명에 매핑된 내부 참조의 개수는 독립 법적 증거 수가 아님을 표시한다. 참조마다 다른 mention 위치나 적용범위가 있으면 차이를 표시하며 서로 다른 법적 연결로 유지한다.

현재 `card`는 내부 3개, `compact_view`는 그중 2개를 먼저 자른다. **묶은 다음 고유 경로 한도를 적용**해야 같은 행이 한도를 소모하지 않는다. 압축표 투영으로 또 같아진 표현에도 같은 검사를 한다. 기존 모든 경로는 원장에 보존하며 `more_*`는 표시한 고유 경로와 내부 발생 건수를 혼동하지 않게 구분한다.

## 5. 대표 실행·실패 시나리오

| 상황 | 처리·검증 | 최종 상태·복구 |
|---|---|---|
| 같은 조문을 여러 질의와 참조로 회수 | 원문 한 번, 경로 그룹에 각 유입 연결. 선별 후 선택 근거만 작성에 전달 | 정확 본문과 기존 근거 번호로 답변·출처 발행 |
| 선별에서 예외·반대 근거 누락 | 기존 선별/읽기에서 필요한 이유와 역할로 보완. 완료 못 하면 unresolved | 자료 부재를 규정 부재로 단정하지 않음 |
| 같은 문장, 다른 판본 또는 접근 범위 | identity·권한을 먼저 검사; 서로 다른 근거로 유지 | 해당 요청에 허용된 판본만 전달. 세대 변경 시 stale 거부 |
| 긴 선택 근거가 한도를 초과 | 최종 wire의 byte/토큰 한도 검사. 필수 원문을 조용히 자르지 않음 | 기존 추가 선별·보류 경로 또는 명시 한계/실패. 원문 원장 보존 |
| 부분 READ·중첩/불연속 범위 | cp 범위·원문 일치·누락 구간 검사; 부분 상태 유지 | 복원 불가 시 범위 공유를 중단하고 개별 표현; FULL로 승격하지 않음 |
| 구조 이름표·판본이 없음 | 저장된 표제/heading까지만 표시하고 나머지는 미확인 | 숫자 handle에서 장·절 이름을 추정하지 않음 |
| 잘못된 번호·변조·오래된 응답 | 번호 및 canonical 범위·저장 view·전송 hash 검사 | 기존 계약 오류/수정 예산. 범위·예산 확대 금지 |
| 용어 검토 중 구현·projection 변경 | 새 review state에서 prepare; 이전 완료 job/input을 유지 | 다른 구현으로 기존 state 재개 거부를 유지, 명시 검증된 결과만 재사용 |
| SSE 답변이 일부 출력된 뒤 오류 | 기존 append-only 스트림·재시도 제약 유지 | 이미 출력한 본문을 새 번호로 바꿔 재전송하지 않음; canonical 결과 별도 확인 |

## 6. 검증 계획과 사전 통과 기준

### 6.1 계약·회귀 검사

아래는 **제안 목표**이며 실제 통과 결과가 아니다. 일반 계약 검사는 구현 correctness를 확인한다. 후보 전후 입력량·효과 비교는 별도 ADR 실험으로 다룬다.

| ID | 통과 목표·분모 | 확인 방법 |
|---|---|---|
| T01 | 작성 요청마다 허용 집합 밖의 본문 0개 | 실제 wire의 정확 범위 집합을 selected_citable∪required_context와 대조 |
| T02 | 동일 표시 관계의 초과 반복 0행 | 최종 상세 표현과 압축 표현별 동일 행 검사; 서로 다른 범위·방향은 유지 |
| T03 | 모든 전송 참조의 해소율 100% | 문서·마디·본문·관계·요구 namespace와 기존 출력 번호 복원 검사 |
| T04 | 선택 근거의 정확 원문·범위 복원 일치 100% | 기존 evidence별 원문·offset·해시·순서·coverage 비교; Unicode·반복 문구·불연속 구간 포함 |
| T05 | 표시 근거마다 출처 설명 또는 명시 미확인 상태 100% | 문서/기록된 판본/조문 위치를 저장 구조와 대조; 이름표 없는 숫자 경로만 남는 경우 차단 |
| T06 | 변조·cross-request·cross-version·미선택 인용 수락 0건 | 성공 전송 영수증·visibility·선택 상태·권한·해시 음성 검사 |
| T07 | 단순 표현 변경으로 새 모델 단계 0개 | bounded/도구 경로의 호출 순서, 최종 검토 기본 정책·수정 예산·SSE 회귀 검사 |

기존 `test_legal_agent_compact_prompt.py`, `test_legal_agent_v5_numbers.py`, `test_legal_agent_v5_sources.py`, `test_bounded_source_selection.py`, `test_bounded_source_main.py`, `test_model_decision_repair.py`의 계약을 확장한다. 구축은 `test_glossary_review.py`, `test_reference_resolution.py`, `test_recipe_basic.py`, `test_recipe_compact.py`, `test_recipe_regions.py`를 범위에 맞게 실행한다. 전체 재시험은 새 실패·변경·미해결 연결이 있을 때 추가한다.

### 6.2 품질·입력량·지연 실험

실행 시 두 표준 문서에 따라 동일 scope의 진행 reservation을 다시 확인하고, 첫 후보 쓰기 전에 stable runner의 `adr_structure.py new --adr-root 04_EXPERIMENTS/ADR`로 선점한다. 번호는 지금 예약하거나 추정하지 않는다. 현재 기록에서 문장 범위 작업 ADR-0530이 진행 중이므로 문장 segmentation/정본 범위 수정과 scope가 겹치지 않도록 한다.

감사 사례는 이미 문제를 보고 설계한 **probe**다. 39회 요청은 형식·보존 회귀 자료로 쓰고, 정확도 일반화나 MAIN 채택 근거는 별도로 분리한다. 모델 재실행 또는 후보 입력 재구성의 전후 효과를 측정하는 순간 새 ADR/run으로 기록한다.

계보 참고 대상은 완료된 `ADR-0557-experiment-v1/structure-main`이다. 이 결과는 과거 Qwen/generation 30 기록이므로 새 Gemma 성능의 baseline 수치로 재사용하지 않는다. 실제 실험 baseline은 시작 시 선택된 전체 파이프라인·코드·데이터를 다시 고정하고, 과거 완료 arm에서 달라진 generation 31의 repair 등은 변경 내역으로 기록한다. 단순 참고·의존은 `relationships`, 실제 계승은 정확 parent arm으로 구분한다.

권장 arm은 A=현재 고정 baseline, B=공통 표현 변경, C=공통 표현+작성 자료 제한이다. B는 자료 identity/범위를 유지하며, C는 실제 작성 전달 집합이 달라진다. 후보 파일은 snapshot/register/freeze로 격리하고 hash가 고정된 runner가 기존 Pipeline에 명시 주입한다. 운영 registry가 연구 후보를 자동 선택하지 않게 한다. arm·반복 수·실행 순서·표본·판정·비용 한계는 호출 전에 동결한다.

- 1차 probe: 감사의 동일 관계 반복, 긴 좌표, 작은 선택 본문/큰 미선택 본문, 구조 원문 우선, 보류 회복을 포함한다. 새 출력·후속 설계는 과거 결과를 덮어쓰지 않는다.
- 분리 평가: 문서 추천·명시 조문·항/호·위임·정의·예외·반대 근거·다른 판본·부분 읽기·인사·범위 밖·목록/폴더 질문을 포함한다. 질문별 의역은 원사례 묶음으로 관리한다. 원문 판본과 요구별 정답 근거를 동결하고 제품 입력에 gold를 넣지 않는다.
- 사전 제안 기준: T01~T07 충족, 기준에서 충족한 핵심 요구·조건/예외·수치/시행 버전·근거 정확성의 신규 회귀 0건. 평균점수의 상승으로 치명적 회귀를 상쇄하지 않는다. 분리된 고정 평가를 통과해도 모집단 오류 0을 의미하지 않는다.
- 운영 이점 판정: 동일 평가 집합의 전체 물리 요청 입력 토큰 합 감소를 목표로 한다. 출력·보정·재시도까지 포함한 전체 토큰/비용·완료율·질문 단위 p50/p95와 후보 프로젝션 CPU 시간을 별도 보고한다. 기간·비용 한계의 구체 값은 실행 전에 동결해야 하며 현재는 미산정이다.
- C는 source/retrieve/union/canonicalize/select/present의 후보·선택·실제 전달 집합과 discard 이유를 measured stage-ledger에 기록한다. golden recall/selectivity는 offline에서만 결합한다. B도 표현 통합으로 canonical identity가 바뀌었는지 확인하고 occurrence와 조문 수를 구분한다.
- 외부 실험은 `ExperimentClient`, `google/gemma-4-31b-it`, Parasail FP8, thinking off, fallback 없음. 반출 설정에서 허용한 공개 자료만 사용한다. 내부 자료는 동일 계약의 모의 자료로 외부 검사하고 실제 검증은 GENOS 내부 모델로 한다.

호출 최종 경계에서 본문/출처·구조/관계·경로/질문·상태/system/schema/오류 수정의 문자·UTF-8 byte와 request hash를 기록한다. 토큰은 provider usage 또는 검증된 tokenizer가 있을 때만 숫자로 기록한다. 미지원 항목은 unknown으로 둔다. 이미지 개수·해상도와 이미지 입력 토큰은 구분하고, 입력+출력 예약량의 실제 context gate는 backend 규약을 확인한다. 새 tokenizer 의존성을 임의로 설치하거나 문자 수를 토큰으로 환산하지 않는다.

일반 로그에는 길이·hash·ID·상태만 남긴다. 정확 payload는 기존 접근 제한된 요청 원장에 보존한다. 매 후보 추가마다 전체 요청을 반복 생성하는 비용과 저장 view 기준 한도가 먼저 막는 경우도 확인하고, 최종 실제 wire 검사와 저장자료 자원 한도를 구분한다.

## 7. 기대효과·비용·일정의 판단

| ID | 종류·단위/분모 | 근거·산식·적용 한계 |
|---|---|---|
| N01 | 관측: 물리 요청 39회 | 기존 감사/ADR-0557. 독립 질문 수나 현장 검증 건수가 아님 |
| N02 | 관측: 표시 중복 값 42,301자 | 감사의 여러 요청 내 반복 문자열 합. 전체 객체/새 ID 사전 크기를 포함한 절감량이 아님 |
| N03 | 관측: CM-040 미선택 본문 17,035자 | 선택 1,117자 외의 추가 본문. 필수 문맥 역할을 판별해야 실제 제외량을 결정할 수 있음 |
| N04 | 관측: CM-051 span JSON 16,486자/본문 13,868자 | 좌표 메타데이터 총량. 일부 구간 표시는 여전히 필요하므로 전량 절감 예상으로 쓰지 않음 |
| N05 | 과거 관측: ADR-0548 최초 입력 32,927→19,420토큰, 논리 호출 p50 39.144→40.257초 | 다른 고정 compose 사례 3회/arm, 양쪽 최종 형식 완료 0/3. 새 후보 예상치로 전용하지 않음 |
| N06 | 미확인: 새 후보 토큰·시간·금액·정확도 | 동일 조건의 위 실험과 GENOS 현장 기록이 필요. 절감률·완료 시간 보장 미산정 |

순 입력 절감은 `없앤 반복·불필요 입력 토큰 − 새 사전·참조·필수 문맥 토큰`으로 판단한다. 사전이 더 크거나 참조 해석 오류로 재시도가 늘면 전체 비용이 악화될 수 있다. 독립 호출 간 필수 본문 재전송과 필요한 VLM 이미지 비용은 남는다.

일정은 P0~P2의 첫 후보, P3의 탐색 확장, P4의 구축 검토, P5의 구조화 분기로 관리한다. 각 묶음에 구현·계약 검사·모델 평가·기록 정리 시간을 포함하되, 현장 시험/검토 대기와 개발 인일을 구분한다. 현재 착수 인력·평가 표본·내부 모델 가용성이 확정되지 않아 달력 일수·총금액은 산정하지 않았다. 첫 후보의 계약 완료와 probe 기록 후 남은 작업량을 재산정한다.

## 8. 이행·MAIN 반영·롤백

RAG P1~P3은 모델 전달 코드·지침·내부 입력 스키마·엔진 코드 pin/PIPELINE manifest 결속 변경이다. 원문·용어·PeCab 색인 재구축은 원칙적으로 필요 없다. 표시 이름표는 기존 저장 구조를 사용하며 없는 정보는 미확인으로 남긴다.

P4는 `glossary_review.implementation()` 변경을 포함하므로 **기존 review state를 그대로 새 코드에서 재개할 수 없을 수 있다**. 새 prepare/state와 projection 버전·정본 context hash·wire hash를 결속한다. 기존 완료 원장·용어집 버전은 보존한다. 검토 내용이 바뀌어 새 용어집/참조 결과를 채택한다면 관련 문서 연결·navigation/fulltext·서빙 묶음을 새 세대로 만드는 기존 구축 계약을 따른다. 단순 입력 표현 변경을 이유로 활성 데이터 전체를 자동 재구축하지 않는다.

P5는 recipe/parser 지문과 cache 재사용 조건에 영향을 줄 수 있다. 새 구현으로 처리할 문서는 새 지문/run으로 관리한다. 과거 구조 원문은 덮어쓰지 않으며 새 구조 결과를 채택할 때만 하위 구축을 연결한다.

도입 전 실험의 `validate --final`과 `graph`를 수행하고 실패를 보존한다. Accepted·out-of-sample·decision_eligible=true·complete arm만 승격 대상으로 삼는다. 여러 완료 결과를 결합하면 정확 부모와 채택/제외·충돌·rollback을 기록한 merge ADR을 만든다.

MAIN 승격은 stable runner의 `rag_main_promotion.py prepare/check`와 hash 고정 plan, 등록 guard, 명시 `--confirm-main` 절차를 따른다. **현재 승격 도구의 state와 `service.py`가 소비하는 frozen `ACTIVE_RELEASE`는 별도이므로 도구 apply만으로 generation 31의 실행 코드가 바뀐다고 가정하면 안 된다.** 검증 코드·스키마·데이터를 새 frozen 릴리스로 결속하고 실제 선택 포인터/엔진 로더가 그 결과를 소비하는 연결을 확인한다. 이 연결과 guard가 미결속이면 배포 준비의 종료 조건을 충족하지 못한 것으로 남긴다. 사용자 지시 전환 이력을 실험 품질 통과로 재사용하지 않는다.

롤백 단위는 모델 표현 버전 하나와 그에 맞는 코드·번호 복원·검증·지침·엔진 pin의 묶음이다. 이전 frozen 릴리스와 데이터/프로필 결속으로 돌아가며 apply/rollback 영수증을 남긴다. 실행 중인 요청은 시작 시 고정한 버전을 유지하고 새 번호 체계를 중간에 섞지 않는다. 구 버전 실행 중단점을 새 코드로 임의 재개하지 않는다.

GENOS 반입 시 검증 코드 ZIP·의존성·설정 이름·입출력 계약·적용/재개/확인/원복 TXT를 제공한다. 기존 `~/DEV`의 검증 대상 파일을 백업 후 적용하고 지속 로그·재실행 검사를 포함한다. 코드 적용·Git push·코드서빙 리비전·트래픽 선택을 따로 확인한다. 현장 질의·warmup은 워크플로우 테스트 화면에서 확인한다. 외부 입력 개선 결과가 내부 자료·GENOS 성능 인증을 대신하지 않는다.

## 9. 근거와 현재 완료 범위

확인한 주요 자료:

- [기존 전달 경로 감사 및 수치 원장](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260929-model-data-presentation-audit/REPORT.ko.md)
- [전체 MAIN 책임·현재 배선](/home/jin/8-AGENT/00_SYSTEM/ARCHITECTURE.md), [현행 데이터 계약](/home/jin/8-AGENT/00_SYSTEM/DATA_MODEL.md), [실행 명세](/home/jin/8-AGENT/00_SYSTEM/PIPELINE.json)
- [선별 카드·관계 표시](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/source_selection.py:101), [작성 view 구성](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/relation_views.py:17)
- [전송 프로젝션](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/gateway.py:22), [번호 변환](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/numbered_references.py), [실제 wire 대조](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/relations_repository.py:92)
- [작성의 선택 근거 검증과 사용자 출처](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/workflow_tiers_session.py:298), [bounded 연결](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py:48)
- [용어 원문/문장 정본](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/glossary_senses.py:60), [용어 검토 호출·재개](/home/jin/8-AGENT/02_BACKEND/lawrag/pipeline/glossary_review.py:285), [참조 case view](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/reference_resolution_repository.py:149)
- [기존 축약의 구현·실패·실측 이력](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_PROMPT_COMPACTION_20260928.md), [용어집 운영 진입점](/home/jin/8-AGENT/07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md), [GENOS 진입점](/home/jin/8-AGENT/GENOS.md)
- [실험 실행 표준](/home/jin/8-AGENT/04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md), [ADR·검증 표준](/home/jin/8-AGENT/04_EXPERIMENTS/LEGACY_ADR/STANDARD.md), [현재 MAIN 승격 구현](/home/jin/8-AGENT/02_BACKEND/lawrag/platform/main_promotion.py)
- [설계 근거 파일 hash·상태 확인 기록](EVIDENCE.json)

이번 작업은 보고서·실제 코드·선택 릴리스의 연결과 수정 경계를 확인하고 계획을 작성한 것이다. WSL 개발 환경 검사는 통과했다. 자체 설계 검토이며 독립 감독 검토는 수행하지 않았다. 신규 후보·효과 측정·모델 호출·MAIN 수정·배포는 수행하지 않았다.
