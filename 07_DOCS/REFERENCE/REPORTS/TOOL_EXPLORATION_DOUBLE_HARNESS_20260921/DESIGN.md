# 도구 선택형 탐색과 시스템·도메인 더블하네스 상세 설계

작성일: 2026-09-21. 상태: 설계안. 제품 구현·모델 실험·MAIN 활성화·GENOS 배포 미실행.
작성·검토: implementation-design-report와 design-reality-review에 따른 자체 검토. 독립 에이전트 검토가 아니다.
사용자 최신 요구: 트리는 필요할 때 현재 주변을 보는 도구다. 검색은 단서로 목적 위치를 찾는 도구다. 트리 열기나 목록 조회를 선행 단계로 강제하지 않는다.

함께 읽기: [상세 계약](CONTRACTS.md), [수용 시나리오](ACCEPTANCE.md), [자체 검토](SELF_REVIEW.md), [확인한 파일 지문](sources.json).

## 1. 구현할 결과와 경계

에이전트는 하나의 요청 안에서 목록/트리, 검색, 용어 역매칭, 정의, 좌표 지목, 참조, 원문 읽기를 선택한다. 검색에서 바로 원문으로 갈 수도 있고, 원문을 읽다가 문서의 주변 헤딩을 볼 수도 있다. 처음 고른 문서·용어·가설·근거·결론은 모두 틀릴 수 있으며 수정 가능하다.

**이번 대화에서 사용자가 자료 범위를 제한한 적은 없다.** 기본 탐색 범위는 선택된 서빙 세대에 등록된 전체 자료다. 특정 문서를 언급하거나 그 문서 안을 잠시 검색하는 것은 다른 문서를 보지 말라는 지시가 아니다. 에이전트는 추가 허락 없이 다른 문서·폴더로 이동하거나 전체 검색으로 돌아갈 수 있다. 이후 등장하는 명시적 제한 사례는 ‘이 문서만 사용하라’ 같은 별도 요청이 있는 경우의 예외 시나리오다.

시스템 하네스는 도구와 모델 실행, 상태, 입력 전달, 오류 복구, 자원, 종료를 집행한다. 도메인 하네스는 법률 질문의 근거 자격·적용 범위·조건·예외·사실 부족·상충 및 답변 충족 여부를 다룬다. AgentProfile은 시스템 하네스의 설정 일부이며 시스템 하네스 전체를 뜻하지 않는다. 두 하네스는 별도 모델 두 개를 뜻하지 않는다.

대상은 MAIN 중 **용어 기반 RAG 서빙 및 실행에 결속된 피드백** 단계다. 앞단 문서 구조화·용어집·출현·정의·명시 참조 색인을 재사용한다. 원문을 Rule/조건/효과 의미 DB로 다시 쓰지 않는다. 해석·요약·쟁점·관계 의심은 실행 중 관측으로 저장한다.

완료의 최소 의미는 도구 존재가 아니다. 실제 요청 → 선택 도구 실행 → 실제 모델 입력 전달 → 읽은 원문 판단 → 필요 시 다른 도구 선택 → 근거 보존 → 답변/한계 게시까지 연결돼야 한다. 그 연결 성공과 정답률은 별도 판정이다.

## 2. 현재 구현에 대한 판정

| 구분 | 확인한 상태 | 설계에 주는 제약 |
|---|---|---|
| 활성 로컬 서빙 | ACTIVE_RELEASE는 document-navigation-rag-20260921-v1, 포인터 generation 17, quality_certified=false | 작업 코드나 후보 존재를 활성화로 표현하지 않는다 |
| 기존 더블하네스 | legal-agent-v1의 SourceSession에 문서 목록·구조·문자열 검색·정의·참조·읽기 존재 | 문서 목록과 구조 기능을 재사용하되 전체 도구와 새 계약을 통합해야 한다 |
| source-first 후보 | ADR-0482 run-002의 모델 행동은 search/read/page. 검색은 locator와 형태소 FTS | 목록·트리·정의·용어 역매칭을 호출할 수 있는 모델 인터페이스가 빠졌다 |
| 용어 역매칭 | navigation_match의 일상어 bridge와 work_navigation의 occurrence 연결 존재 | 독립 도구 adapter로 추출하고 기존 모호성·관계 영수증을 보존해야 한다 |
| 목차 | FolderNavigator.outline은 일부 하위 번호 유형을 제외하는 식. document_browser.outline은 평탄한 마디 목록 | 실제 자식, 주변, 큰 단위 개요를 각각 정확하게 정의해야 한다 |
| 시스템 연결 | Pipeline.run → 요청 세션 → Coordinator → StageRunner, journal/outbox 존재 | 이 진입점을 확장한다. 별도 제품 runner를 만들지 않는다 |
| 경계 | Request, DomainSpec, AgentProfile, 구현 선택 분기 일부가 닫혀 있음 | 이름/필드만 추가하는 설정 변경으로는 연결되지 않는다 |

현재 작업 트리에 다수의 기존 수정이 있다. 기준은 sources.json에 고정한 파일 내용이며 HEAD만으로 대표하지 않는다. ARCHITECTURE와 운영 문서의 과거 generation 표기는 당시 기록이다. 현재 활성 포인터와 동결 후보를 따로 확인했다.

## 3. 과거 실패에서 도출한 요구

아래는 저장 기록의 관측이다. 같은 실패의 유일한 원인을 증명하거나 새 설계의 개선률로 해석하지 않는다. 오래된 모델/provider는 당시 조건이며 신규 실험 모델 정책을 대체하지 않는다.

| ID | 기록과 확인 사실 | 반드시 설계할 것 | 연결 검사 |
|---|---|---|---|
| F01 | ADR-0438: 모의 계약 통과 후 실모델에서 읽기·설명 실패. 자동 보호 판정과 실제 동작도 불일치 | 서버 발급 핸들·좌표, 형식/실행/의미 품질 분리, judge 오판 확인 | A12,A33,A44 |
| F02 | ADR-0466: 확인표 방식은 같은 모델 plain 대비 이득이 없고 호출 증가. 누락 보완도 반복 | 전 원문·전 항목 장부 작성을 입장권으로 삼지 않음. 사용한 근거의 짧은 판단과 표적 검토 | A21,A45 |
| F03 | ADR-0474 궤적 감사: 기존 검색에서 보이던 결정 조문이 새 하네스 검색에서 사라짐 | 원래 FTS·locator·역매칭의 기능 계약을 보존하고 실제 도구 노출까지 검사 | A07,A08,A34 |
| F04 | 같은 감사: node를 evidence로 사용, batch-local 의존 오류, 모델 형식 실패를 전송 실패로 오분류 | 타입별 핸들, 사전 검증, 부분 실행 계약, format/semantic/transport 구분 | A12,A13,A28 |
| F05 | 같은 감사 cm-003: 읽고 finding/초안을 만든 뒤 검토에서 소실 | 근거 있는 검토 이의만 대상 주장에 적용. 초안·반론 보존, 오검토 복구 | A24,A25 |
| F06 | ADR-0476와 행동피드백 계획: 동일 READ 반복, 결과가 다음 view에 연결되지 않음 | last_action_results·read_state·현재 제시 E·커서·실행 결과를 전송 payload까지 확인 | A14,A15,A35 |
| F07 | ADR-0478: 두 결정 원문이 제시됐지만 예외 원문은 선택되지 않아 작성·검토에서 소실 | ADOPT/REJECT/DEFER와 이유, 반대·예외 원문도 검토 입력으로 보존 | A22,A23 |
| F08 | ADR-0479: 두 원문을 작성·검토에 전달하고도 잘못 적용하고 SUPPORTED 승인 | 인용 적법성과 의미적 지지 분리. 조건과 사용자 사실의 적용 연결 검토 | A23,A26,A44 |
| F09 | ADR-0480: 수동 관계 한 건으로 정확한 subtree READ 확인. 모델 탐색·사람 승인·정답률은 미검증 | 관계→정확 범위 도구는 재사용 가능. 연결을 적용 정답으로 자동 승격하지 않음 | A10,A17,A46 |
| F10 | ADR-0482: 후보 최종 주장 없음. 동결 코드에서 P/E 선택 의미 오류가 조사 break로 이어짐 | 오류를 구조화해 다음 판단으로 반환. 형식 오류 한 번으로 전체 탐색 폐기 금지 | A12,A16,A36 |
| F11 | ADR-0474 어댑터 감사: 숨은 수리와 전송 인자 소실로 실제 호출과 장부 불일치 | 단일 전송 어댑터, retry/repair의 단일 소유자와 물리 호출 회계 | A28,A29 |
| F12 | ADR-0473/선행 궤적: 새 참조 후보가 마지막에 생겨 미제시되거나 연결만으로 동반 채택 | 발견/반환/제시/평가/선택/조립/인용을 분리. 마지막 도구 결과 관찰 후에만 종료 판단 | A18,A35 |

ADR-0481 README는 확인 시 in_progress이며 결과란이 미작성이다. 이 문서의 설계 근거에 성공/실패 결과로 사용하지 않는다. ADR-0482는 Rejected이며 그 결과를 승격 근거로 쓰지 않는다.

직접 확인한 실패 출처:

- F01: [ADR-0438 원인 진단](../../../../04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation/artifacts/diagnosis.md). 모델 문자 위치 오류와 동일 입력 재시도 확인.
- F02: [ADR-0466](../../../../04_EXPERIMENTS/ADR/ADR-0466-legal-agent-composer-audit/README.md). 확인표 효과·호출·회귀는 당시 인샘플 조건이다.
- F03/F04/F05/F11: [ADR-0474 궤적 감사](../ADR-0474_PHASE0_TRAJECTORY_AUDIT_20260920.md). 검색 소실·계약·검토·전송 회계의 단계를 구분했다.
- F06: [읽기 결과 피드백 계획의 관측](../SOURCE_FIRST_ACTION_FEEDBACK_PLAN_20260920/PLAN.md). 해당 원인과 모델 반복의 유일한 인과를 구분했다.
- F07: [ADR-0478](../../../../04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest/README.md). 예외 E가 선택 단계에서 빠져 작성·검토 입력에 없었던 사례.
- F08: [ADR-0479](../../../../04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence/README.md). 원문 보존 후에도 적용 결론과 자체 검토가 틀린 사례.
- F09: [ADR-0480](../../../../04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations/README.md). 정확 subtree 조회와 법률 정답 판정의 경계.
- F10: [ADR-0482 사례 1](../../../../04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout/실험/질문-001-fsc-hard-001.md)과 sources.json의 frozen source_first_session.py. 실제 E 별칭 오류와 break 경로.
- F12: [ADR-0473](../../../../04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4/README.md) 및 원문 중심 설계의 [실패 목록](../LEGAL_AGENT_SOURCE_FIRST_DOUBLE_HARNESS_20260920/DESIGN.md). 미개봉 목록 채택·마지막 고르기·관계 자동 편입의 효과와 회귀를 분리했다.

## 4. 전체 실행 구조

```text
기존 POST /v1/rag/ask → Pipeline.run → 요청 세션 / Coordinator
                                      │
                 시스템 하네스: 상태·도구·예산·전달·오류·복구
                                      │
                     현재 상태와 도구 목록 → 에이전트
                                      │ 행동 제안
                 도구 검증/실행 → 결과 → 다음 판단
                   ↙         ↓           ↘
               주변 보기   검색·역매칭     원문/정의/참조 읽기
                   ↘         ↓           ↙
                    원문 평가·가설 수정·잠정 근거
                                      │ 작성 제안
                 조립 → 초안 → 도메인 검토 + 시스템 검사
                               │
                   추가 탐색 / 재작성 / 검토 이의 처리
                               │
                    답변 또는 구체적 한계 → outbox
```

모든 행동을 순서대로 실행하는 다이어그램이 아니다. 조사 중 도구 선택은 자유이고, 작성·검토가 부족을 발견하면 같은 요청 상태로 재진입한다. 정답 조문 ID나 golden은 제품에서 알지 못한다.

시작 상태에는 원질문, 기본적으로 등록된 전체 자료를 가리키는 ROOT, 선택 가능한 도구, 사용자가 명시한 문서/조문 단서, 제한 예산만 준다. 트리/목록 조회·계획 모델 호출·도메인 쟁점 목록 생성을 의무화하지 않는다. 질문에 정확한 조문이 있으면 locate→read, 일상어이면 match_terms, 문서 자체를 모르면 browse나 search를 선택할 수 있다.

선읽기는 시스템 정책의 선택 기능이다. 현재 서버 선읽기 성과를 보존할 수 있으나 MODEL_CHOSEN과 SERVER_PREREAD를 별도 기록한다. 초기 트리 조회는 선읽기의 부수 조건이 아니다. bootstrap 모드는 같은 예산에 결속하고 비교 시 동결한다.

## 5. 탐색 공간과 도구

### 5.1 대상과 위치

탐색 대상은 등록 자료의 논리 공간이다. 임의 OS 파일시스템을 열거나 셸 ls를 모델에게 주지 않는다. 문서가 여러 표현본을 가지면 논리 문서와 원본 파일 별칭을 구별한다.

대상 계층은 ROOT → 실제 출처 폴더/문서 집합 → 문서 → 저장 구조 마디다. 폴더 계층은 출처 메타데이터, 문서 내부 계층은 source_unit.parent_id가 정본이다. 폴더 정보가 없으면 미분류에 표시하고 문서명으로 폴더를 만들지 않는다. 본문에서 장/절/조를 다시 추정해 가짜 구조를 만들지 않는다.

모든 조회는 target을 명시한다. 숨은 현재 작업 디렉터리에 의존하지 않는다. last_location은 표시와 추천에만 사용하며 인자 누락을 조용히 다른 문서로 해석하지 않는다. 각 결과는 scope_root, document, parent, breadcrumb, focus, 실행 가능한 navigation_targets를 포함한다.

### 5.2 공통 도구 목록

아래 이름은 새 계약의 제안 이름이다. 기존에 모두 구현된 API 이름이 아니다. 모든 도구의 성공 결과는 판정 재료이고 자동 근거 채택은 아니다.

| 도구 | 질문/목적 | 주요 인자 | 결과 | 연결할 기존 기능 |
|---|---|---|---|---|
| browse | 여기에/주변에 무엇이 있나 | target, view, relation, depth, cursor | 문서·마디 헤딩, 부모/자식/형제, 페이지 | FolderNavigator, stored_units, document_browser |
| search | 이 단서에 맞는 위치는 어디인가 | query, target, mode, cursor | P/U 위치, 적중 구간·검색식·범위 | FulltextIndex, search_structure, source block 조회 |
| match_terms | 이 표현은 어떤 등록 용어인가 | text, target, strategy | T 용어, 일상어→법률용어 L 관계, 질문 구간 | NavigationMatcher.starts/_bridge |
| term_occurrences | 이 용어가 어디에 등장하나 | terms, target, match, cursor | 출현한 P, T/L 유입 경로 | occurrence 색인 |
| locate | 문서명·조번호가 가리키는 위치 | locator, target, branch, cursor | 정확 마디 또는 복수 해석 후보 | stored_coordinate, 공식 약칭/locator |
| lookup_definition | 여기서 이 용어의 정의는 무엇인가 | query, target, cursor | 문서 내 정의/사전 후보, 적용 범위 | definition 색인, Glossary.lookup |
| follow_reference | 이 원문이 가리키거나 이를 가리키는 곳 | evidence, direction, cursor | L 관계, 출처 문구, 대상 마디·해소 상태 | reference/reference_end, exact subtree |
| read | 이 위치의 실제 원문은 무엇인가 | target, extent, cursor | 정확 E, 부분읽기 범위, 이어읽기, 주변 탐색 위치 | SourceSession._read/verify |
| inspect | 무엇을 했고 왜 보류했나 | section, cursor | 최근 결과, 근거평가, 제외 후보, 미해결 항목 | WorkRepository와 요청 상태 |

제목 검색과 fulltext는 search의 명시적 mode로 구별한다. 문자열 검색을 fulltext라고 부르지 않는다. 검색 범위 ROOT/폴더/문서/subtree를 명시하며 좁은 검색 실패 시 서버가 자동으로 ROOT로 넓히지 않는다. 모델은 제공받은 ROOT handle로 다시 검색할 수 있다.

### 5.3 browse: 트리와 주변 조회의 정확한 의미

1. view=children: 실제 직접 자식만 반환한다. 문서 집합에서는 폴더/문서, 문서에서는 최상위 구조 마디, 조문에서는 항 등이다.
2. view=outline: 문서나 subtree의 개요다. 저장된 편/장/절/관 헤딩과 **조 단위**를 보여주고 항/호/목은 접는다. 일반 문서는 저장된 상위 section을 보여준다. 법적 구조가 불명확하면 children만 제공하고 불명확함을 알린다.
3. view=tree: 사용자가 지정한 깊이까지만 실제 부모-자식 계층을 펼친다. 기본은 직접 자식 깊이이며 전체 문서를 재귀 펼치지 않는다. 깊이와 한 페이지 행 수 상한을 구별한다.
4. view=neighbors: focus의 같은 부모 아래 앞뒤 형제를 보여준다. 조문 수준 주변이 필요하면 enclosing_article로 투영한 뒤 그 조문들의 주변을 본다. 같은 문서의 다음 source_id를 형제로 간주하지 않는다.
5. relation=self/parent/document/root는 target으로부터 조회 기준을 해소한다. 읽은 E나 후보 P는 서버의 node 매핑을 통해 해소한다. parent가 여러 개인 합성 근거는 후보 위치 목록을 반환하고 임의 하나를 고르지 않는다.
6. 본칙·부칙·별표·별지의 branch/시행일 등 저장 메타데이터를 표시한다. 서로 다른 부칙 제1조는 별도 노드다. 표는 구조 행/열 정보가 있으면 유지한다.
7. 기본 출력은 제목·좌표·구조만이다. content_read=false, citation_eligible=false. 헤딩 확인은 본문을 읽었다는 영수증이 아니다.
8. 모든 모드에서 페이지 누락을 명시한다. 평탄 tree 페이지는 각 행에 ancestor path를 동봉하여 페이지 시작이 고아 노드처럼 보이지 않게 한다.

예: read(P7) 결과를 읽어도 잘 모르겠으면 browse(E3, relation=document, view=outline)을 호출한다. E3가 속한 문서의 큰 헤딩/조문만 본 후 다른 U를 read하거나 그 문서 안에서 search한다. 이 단계는 필요할 때만 실행된다.

### 5.4 전문검색·역매칭·참조의 구별

search(mode=fulltext)는 기존 Kiwi 형태소·BM25를 재사용한다. query 토큰·필터·ranking 버전·잘림·후속 페이지를 기록한다. 현재 source 단위 FTS를 subtree에 적용할 때는 반환 적중 구간이 해당 subtree 안에 실제 존재하는지 다시 확인한다. 조문 일부를 읽는 범위와 조문 전체의 검색 점수를 혼동하지 않는다.

match_terms(strategy=auto)는 현재 직접 법률용어 우선 및 일상어 bridge의 정책을 재사용한다. 전략은 auto/direct/bridge를 명시 지원한다. bridge는 등록된 일상용어와 공식 관계만 사용한다. direct가 있어도 모델이 다른 뜻을 검토하려고 bridge를 명시하면 후보로 볼 수 있으며, 이것은 기존 auto 경로와 다른 제안 동작으로 분리 검증한다. 동의어/관련어/상하위 관계와 반의어 제외, 방향, 출처, scope 내 출현 여부를 표시한다. 새 관계를 모델이 사실로 생성하지 않는다.

term_occurrences는 T로 source를 조회한다. 같은 source라도 질문 구간·용어·관계별 유입 경로를 모두 보존한다. 잘못된 관계 L을 거절하면 그 경로만 비활성화한다. 다른 FTS/직접용어 경로로도 온 후보를 함께 없애지 않는다. 요청 중 거절과 영구 용어집 수정은 별개다.

짧은 표현은 무조건 길이 컷으로 제거하지 않는다. 기존 형태소 경계·등록된 짧은 약어·문맥 조건을 재사용하고 매칭 근거를 보여준다. 등록되지 않은 짧은 토큰은 단독 bridge 승격을 피하되 명시 fulltext/literal 검색은 가능하다. ‘위키가 짧은 표현을 모두 차단한다’는 기존 인상을 정본 계약으로 채택하지 않는다. 위키는 별도 해석자료이며 원문 근거와 역할을 분리한다.

follow_reference의 incoming은 **조문 역참조**다. 일상어 역매칭과 별개다. 해소된 대상의 항/호 범위와 참조 문장 witness를 같이 반환한다. 모호한 법령명·복수 판본·미해소 범위는 UNRESOLVED로 남기고 locate/search/browse 선택지를 제공한다. 링크만으로 예외 적용이나 상위 규범 우선 결론을 내리지 않는다.

## 6. 상태·전달·근거 계약

### 6.1 서버가 소유할 상태

| 상태 | 내용 | 수정 규칙 |
|---|---|---|
| Binding | 코드·원문·색인·용어집·도메인·시스템 프로필·모델·허용 범위 해시 | 요청 중 불변. 변경 감지 시 재결속 필요 |
| Navigation | 반환된 위치, 검색식, 탐색 범위, 방문 페이지 | 서버 발급. 같은 자료 재접근 가능 |
| Candidate | canonical source/node/extent와 복수 routes, 표시 상태 | 새 검색이 기존 후보를 삭제하지 않음 |
| Evidence | 원문 span·좌표·해시·READ coverage | 불변. 이어읽기는 추가 E/범위로 기록 |
| Presentation | 어떤 view/물리 호출에 어떤 E 원문이 들어갔나 | 전송 payload 기준. 저장만 된 근거와 구별 |
| Assessment | E 요약, ADOPT/REJECT/DEFER, 용도·이유·쟁점 | 버전 추가. 변경 시 종속 초안/검토 무효화 |
| Question work | 원질문 Q 구간, 잠정 해석·사실·미해결 질문 | 모델 수정 가능. 원질문은 삭제/치환 불가 |
| Claim/review | C 문장, E 근거, 사실 조건, 검토 및 반론 | 해당 버전끼리 결속 |
| Action receipt | 실행 결과·오류·재사용·부분 성공·예산 | append-only. 중복 완료를 중복 성공으로 세지 않음 |

### 6.2 원문을 읽은 뒤 짧은 판단을 남기는 방식

에이전트가 평가한 E에는 summary, disposition, reason, role, question_refs를 남긴다. 예: ‘일반 제한을 규정하지만 적용 대상이 질문의 회사와 다름’ → REJECT. ‘예외 조건을 규정하지만 회사 유형 미확인’ → DEFER. 요약과 이유는 모델의 관측이며 법률 정본도 원문 대체물도 아니다.

ADOPT/REJECT 결정에는 이 짧은 평가를 요구한다. 읽어 둔 모든 원문에 별도 모델 호출을 강제하지 않는다. 아직 평가하지 않은 READ는 UNASSESSED로 남고, 선택하지 않았다는 이유만으로 REJECT로 기록하지 않는다. DRAFT 전에 채택 E 및 결론을 뒤집을 수 있다고 제기된 challenge E에 대한 처리 근거를 확인한다. 모든 후보/쟁점 장부를 채우는 전역 관문은 만들지 않는다.

P는 후보, E는 원문이다. 후보 보류는 park_candidate로 기록하고 언제든 reopen할 수 있다. E의 REJECT도 재평가 가능하다. 원문을 삭제하거나 이후 검색에서 영구 금지하지 않는다. 새 원문·질문 해석 변경으로 관련 과거 판단이 STALE이 되면 다시 보여준다.

### 6.3 다음 모델 입력에 반드시 전달할 것

원질문, 도구 capability 목록, 현재 조회 위치/범위, 최근 행동별 결과, 현재 제시 E 원문과 카드 매핑, 채택/보류 요약, 미해결 challenge, 남은 예산, 복구 오류를 포함한다. 오래된 전체 대화를 반복 전송할 필요는 없으나, 과거 행동의 결과가 상태에 없으면 단순 view-only 프로토콜은 충분하지 않다.

입력 선정 순서: 현재 판단 대상의 정확 원문·미해결 반론 → 직전 실행 결과와 오류 → 상태 요약 → 새 후보 헤딩. 후보 미리보기를 먼저 줄인다. 채택 근거/초안 인용 근거가 빠지면 missing_evidence_ids와 REHYDRATE 경로를 제공한다. 원문 없는 요약만 보고 인용 승인하지 않는다. 전체 request의 schema·system·user·출력 예약까지 byte/token 한도를 검사한다.

READ_COMPLETE, PRESENTED, ASSESSED, ADOPTED, PACKED, CITED는 독립 상태다. 마지막 cursor=null만으로 전체 원문을 읽었다고 판단하지 않는다. 실제 span 합집합과 요청 extent를 대조한다. ‘읽었는데 다시 읽음’은 현재 문맥에 없던 원문을 복원하는 정상 행동일 수도 있다.

## 7. 시스템 하네스: 실행과 오류 복구

### 7.1 한 턴의 원자성과 실행 순서

서버는 view_id/state_revision을 가진 입력을 발급한다. 모델은 짧은 행동과 평가만 반환하고 DB ID·해시·revision·SQL을 만들지 않는다. 모델 출력 전체의 스키마와 기존 핸들 참조를 먼저 검사한다. 잘못된 참조가 있으면 그 결정은 실행 전 거절하고 정정 정보를 다음 호출에 준다.

유효한 평가 갱신은 하나의 transaction으로 적용한다. 그 뒤 도구 행동은 action_id별로 실행·기록한다. 실행 중 일부 도구가 실패해도 성공한 READ를 버리지 않는다. 같은 묶음에서 아직 생성되지 않은 핸들을 다른 행동의 인자로 쓸 수 없다. 종속 행동은 다음 턴으로 나눈다. 독립 읽기/검색만 예산과 자료 접근이 허용할 때 병렬화한다.

도구 결과를 만든 턴에 DRAFT가 함께 와도 아직 보지 않은 결과를 선택한 것으로 간주하지 않는다. 다음 입력에서 결과를 관찰한 뒤 판단한다. 메타데이터만 요구한 요청은 서버가 검증된 목록을 직접 렌더링해 끝낼 수 있다.

### 7.2 오류 분류와 복구

| 오류 | 시스템 처리 | 모델에 전달할 정보 | 종료 조건 |
|---|---|---|---|
| JSON/스키마 형식 오류 | 동일 결정의 bounded repair | 잘못된 필드·기대 타입·허용 도구 | 공유 복구 예산 부족/같은 오류 반복 |
| P를 E로 선택 | 실행 전 semantic validation, 상태 보존 | P의 읽음 상태와 현재 제시 E 후보. 복수 E면 복수 그대로 | 복구 실패면 해당 판단 미완료 |
| stale view/중복 결정 | 중복은 기록 재사용, stale은 최신 view | 이미 실행한 action과 현재 유효 상태 | 요청 종료/세대 변경 |
| 잘못된 대상/커서 | 실행 거절, 성공 기록 유지 | 올바른 부모·문서·ROOT, 커서의 소속 | 권한 범위 외 대상이면 대체 공개 금지 |
| 검색 결과 없음 | 정상 EMPTY | 실행 범위·검색식·미실행 경로 | 모델이 다른 검색/주변조회/보류 선택 |
| 같은 페이지/원문 반복 | 성공 캐시 재사용, 문맥 복원 구별 | 새 정보 없음 또는 재제시됨 | 의미 있는 변화 없이 반복 한도 소진 |
| 도구 부분 실패 | 항목별 PARTIAL/ERROR, 성공 분량 보존 | 재시도 가능한 항목과 원인 | 총 deadline/도구 예산 |
| transport timeout | 물리 호출 기록, 사용량 unknown 가능 | 원격 완료 불명; 형식 오류와 구별 | retry 상한/마무리 예산 |
| 원문·색인·scope 무결성 위반 | 영향 자료 격리, 보통 요청 중단 | 기술적 확인 실패 | 새 바인딩 없이 계속 진행 불가 |
| 입력 초과 | 정확 근거 중심으로 재조립/분할 | 빠진 E와 처리 불가 부분 | 필수 원문 자체가 맞지 않으면 BOUNDED |

숫자 suffix가 같다는 이유로 P3→E3로 자동 변환하지 않는다. P3→E5/E6처럼 서버가 확인한 매핑을 보여주고 모델이 선택한다. 복구 요청은 법률적으로 무엇을 채택하라고 강제하지 않는다.

### 7.3 무진전·예산·종료

진전은 새로운 원문 범위, 처음 본 구조 위치, 새로운 검색 경로, 근거 있는 판단 수정, 해결된 구체적 질문이다. UUID/revision/페이지 offset만 바뀌는 것을 진전으로 세지 않는다. A→B→A 같은 왕복은 canonical 대상과 검색식·scope·cursor·범위 지문으로 감지한다. 새 트리 위치 자체는 탐색 진전일 수 있지만 무한한 주변 구경도 총 예산으로 제한된다.

시스템 프로필 초깃값은 현행 상한을 참고하되 개선 예측으로 쓰지 않는다. N01: 물리 모델 시도 14회/요청, 도구 행동 56회/요청, 요청 시간 300초, 작성·검토 예약 3회, answer cycle 최대 3회는 현행 설정 관측값이다. 새 후보 초기 비교에서는 동일하게 고정하는 것을 제안한다. 성공률에 맞춰 사후 상향하지 않는다.

형식 수리·의미 정정·무진전 복구·검토 이의 처리 모두 같은 물리 호출 예산에 포함된다. 복구 모듈마다 별도 무제한 재시도를 두지 않는다. 초깃값 가정 N02: 같은 오류 지문에 추가 정정 기회 1회, 같은 주장 버전의 검토 이의 재검토 1회. 전역 예산이 우선하며 근거/주장 버전이 바뀌어도 총 예산은 초기화하지 않는다.

종료 결정은 FINAL(실행 종료)과 결과 상태를 분리한다. READY는 검토된 범위의 답변 준비, BOUNDED는 일부 미확인, CLARIFY는 사용자 사실/범위 확인 필요다. 의미 정답 인증 상태는 없다. 남은 예산이 검토에 부족하면 이미 검토된 주장만 반환하거나 한계를 반환한다. 빈 선택이라고 자동 상위 후보를 채택하지 않는다.

## 8. 도메인 하네스: 탐색자와 검토자 모두 틀릴 수 있다

### 8.1 고정 규칙과 수정 가능한 판단

고정 계약은 원문/판본/범위/실제 제시/인용 연결이다. 어떤 조문이 적용되는지, 무엇이 예외인지, 질문의 사실이 어떤 법적 유형인지는 수정 가능한 의미 판단이다. 모델의 ‘필수 쟁점’도 틀릴 수 있으므로 초기 쟁점이 도구 접근 범위를 막지 않는다.

질문에서 직접 주어진 사실, 모델이 추정한 사실, 원문에서 확인한 규정, 사용자가 아직 말하지 않은 사실을 구분한다. 적용 기준일이나 법적 지위가 결론을 바꾸는데 근거가 없으면 조건부 분기 또는 CLARIFY로 처리한다. 모든 시간/역할이 unknown이라는 이유로 유효한 원문 설명 자체를 전부 지우지 않는다.

### 8.2 표적 검토 항목

| 상황 | 확인할 질문 | 모델이 할 수 있는 다음 행동 |
|---|---|---|
| 용어 매칭 | 이 일상어가 이 법률용어 뜻인가 | L 거절/보류, 다른 T 조회, fulltext |
| 후보/원문 선택 | 제목만 비슷한가, 적용 대상·행위가 맞나 | REJECT/DEFER, 문서 개요, 다른 검색 |
| 일부 조문만 읽음 | 적용 결론에 영향을 주는 단서가 잘렸나 | 이어읽기, 상위 범위, 주변 항/조문 |
| 위임·준용·예외 단서 | 원칙의 적용 범위가 어떻게 바뀌나 | 참조/역참조, 정의, 조건 비교 |
| 복수 규정 충돌 | 같은 대상·시점·사실에서 실제로 충돌하나 | 양쪽 원문 제시, 판본/위계·특별관계 검토 |
| 부재 주장 | ‘못 찾음’과 ‘규정 없음’을 혼동하나 | 범위와 조사기록 확인, 제한된 부재 표현 |
| 답변 작성 | E가 C의 해당 결론을 지지하나 | 수치/요건/예외·사실 연결 재작성 |
| 검토 승인 | 반대 근거를 빼고 승인했나 | 반대 E 재제시, 적용 논리의 짧은 대조 |

이 표를 모든 질문·모든 원문마다 채우지 않는다. 원질문이나 실제 읽은 단서에 연결되는 항목만 활성화한다. 정규식 단서는 검사 제안이며 법적 효과 판정이 아니다. 단서 표지가 없는 예외도 존재할 수 있으므로 표지 부재를 검사 완료로 쓰지 않는다.

### 8.3 채택하지 않은 근거를 잃지 않는 조립

근거 묶음은 support(명시 채택), challenge(결론에 영향을 줄 수 있는 반대·예외/조건), contextual(정의·문맥)으로 나눈다. 모두 읽고 현재 입력에 제시된 정확 E만 들어간다. challenge를 묶음에 넣었다고 ADOPT로 바꾸지 않는다.

challenge 선정은 (a) 현재 주장/질문에 연결된 모델 제안, (b) 정확한 참조 witness로 연결된 서버 단서, (c) 배제 이유가 새 판단과 충돌한 근거를 입력으로 한다. 관계가 잘못됐을 수 있음을 표시한다. 미독 대상은 원문 대신 ‘추가 읽기 가능’ 항목으로 남긴다. 중요한 후보의 포함 여부·누락 이유는 실행 기록에 남긴다.

고정 source 개수 컷만으로 원문을 잘라 예외를 지우지 않는다. 정확 단위/페이지로 읽고 필요한 원칙·조건·예외 묶음이 입력에 맞는지 검사한다. 맞지 않으면 표적 쟁점별 검토로 나눌 수 있으나 최종 주장과 직접 관련된 반대 원문을 제외한 승인에는 COMPLETE를 주지 않는다. 축약 요약만으로 원문 승인하지 않는다.

### 8.4 검토자 오류와 이의 처리

검토 결과는 claim/version, verdict, 원문 E, 원문과 주장 사이의 구체적 불일치, 영향, 권고 행동을 요구한다. 잘 모르겠으면 UNCERTAIN을 허용한다. ‘부족하다’는 자유 문장만으로 전체 답변 삭제를 지시할 수 없다.

SUPPORTED도 시스템의 인용·제시·버전 검사를 통과해야 한다. NEEDS_RESEARCH에는 실행 가능한 탐색 행동 또는 알려진 미해결 대상이 필요하다. NEEDS_REWRITE에는 어떤 문장·조건이 원문과 다른지 있어야 한다. 잘못된 E/없는 문구/범위 외 원문을 근거로 한 검토는 INVALID_REVIEW로 되돌린다.

의미적으로 그럴듯하지만 틀린 검토는 코드로 확정할 수 없다. 작성/탐색 역할이 짧은 rebuttal(해당 C, 대조 E, 이유)을 제출할 수 있다. 동일 원문과 반론을 제한된 재검토에 함께 제시한다. 정당한 objection이면 해당 주장만 수정/철회하고, 반론이 받아들여지면 objection 철회 이력을 보존한다. 미해결이면 영향 주장만 BOUNDED/조건부 처리하고 서로 독립적인 검토 완료 주장은 유지한다. 의존 주장들은 함께 무효화한다.

동일 모델의 재검토나 여러 표의 합의는 독립 정답 인증이 아니다. 서로 같은 오독을 승인하는 실패는 남는다. 별도 평가에서는 검토의 오승인과 오거절을 둘 다 측정한다. domain policy 자체의 결함은 실행 중 모델이 정본을 수정하지 않고 피드백 후보로 남긴다.

## 9. 전체 사례: 선택적으로 도구를 바꾸며 진행

다음은 설계용 가상 규정·가상 제목이다. 실제 법률 적용 결론이나 실행 로그가 아니다.

| 단계 | 입력/상태 | 선택/서버 실행 | 다음 판단과 산출물 |
|---|---|---|---|
| 1 | 질문 ‘이 회사는 빚을 갚지 못하면 어떤 절차를 밟나?’ | 모델 match_terms(ROOT, ‘빚을 갚지 못함’) | T 금융채무와 다른 의미 후보, L 관계·출처 |
| 2 | T 확인 | term_occurrences(T, ROOT)와 search(fulltext, ‘채무 불이행 절차’) | 복수 경로가 붙은 P. tree는 아직 안 씀 |
| 3 | P7이 유망함 | read(P7) | E3와 문서 D2, 부모/조문 위치, 범위·읽음 상태 |
| 4 | ‘이 문서는 맞는데 E3은 정의만 있다’ | E3 DEFER + browse(E3, document, outline) | D2의 큰 헤딩·조문 목록. E3를 REJECT로 추정하지 않음 |
| 5 | ‘조치’ 헤딩 U12 발견 | read(U12) | 원칙 E4와 ‘별도 기준에서 정한다’는 witness |
| 6 | 세부 기준 필요 | follow_reference(E4, outgoing) | 미해소 대상 L8. 이미 읽었다고 표시하지 않음 |
| 7 | 연결 문서명이 모호함 | search(title, ROOT, ‘채무조정 세부기준’) | 복수 문서 D3/D4와 판본. 모델 D3 선택 |
| 8 | D3 내부 위치 모름 | search(fulltext, D3, ‘신청 요건’) 또는 browse(D3, outline) | 둘 중 필요 도구를 선택. 고정 순서 없음 |
| 9 | E5 읽음 | E4 ADOPT, E5 DEFER: 특정 회사 유형만 해당 | 사용자 사실 부족 Q 표시, 조건부 초안 |
| 10 | 도메인 검토 | E4 원칙과 E5 조건, 사용자 사실 대조 | 적용 사실이 없는데 단정한 C2만 NEEDS_REWRITE |
| 11 | 재작성 | 사실별 조건부 C2, E4/E5 재제시·검토 | 검토된 설명 + 필요한 사실 질문, CLARIFY |

우회 사례: 질문에 정확한 ‘가상 업무규정 제12조’가 있으면 locate→read→작성/검토로 끝날 수 있다. 트리를 한 번도 쓰지 않아도 정상이다. 반대로 ‘어떤 문서가 있나’에는 browse 결과만으로 끝나며 법률 검토 모델을 호출하지 않는다.

잘못된 판단의 재진입 사례: 처음 D2가 맞다고 보고 탐색했으나 대상 회사 유형이 다름을 발견 → D2 가설 REVISED → 해당 평가·C를 STALE로 표시 → ROOT에서 search/다른 match_terms. 성공한 READ는 남는다. 원래 사용자가 D2로 명시 제한한 요청이면 ROOT도 D2 범위이므로 밖으로 나가지 않고 범위 확대 필요를 알린다.

## 10. 실제 코드 변경 지도

새 파일명·프로필명은 제안이다. 기존 후보 snapshot을 수정하거나 운영에서 research 모듈을 직접 import하지 않는다. 새 구현은 얇은 composition adapter로 연결하고 기존 다층 상속을 더 늘리지 않는다.

| 위치 | 변경 책임 | 입력/출력·소비자 | 설정/이행 |
|---|---|---|---|
| service.py / application | 명시 후보 선택 및 프로필 binding | 선택된 code/data → create_app | 구현 allowlist 확장, frozen local override 금지 유지 |
| app.py / create_app, ask | 후보를 요청 세션 경로로 분기 | 기존 Request/Result 유지 | is_legal_agent와 lifespan/publication 분기 함께 확장 |
| pipeline.py / __init__, run | 제안 legal-agent-tools-v2 명시 분기 | legal-agent-rag-v2 → 동일 4개 stage | v1 문자열 비교를 지원 프로필 집합으로 명시 확장 |
| PIPELINE.json, ENGINES/legal_agent | 제안 v2 engine/contract 선언 | retrieve/select/assemble/answer 및 legal.control | code/schema hash 재결속. READY 표지만으로 완료 처리 금지 |
| legal_agent/coordinator.py | 선택된 프로필 사용, RESEARCH/RECOMPOSE/REVIEW 재진입 | 세션/runner → FINAL | 현재 v1 하드코딩 제거. 기존 v1 동작 회귀 검사 |
| legal_agent_adapter.py와 제안 tool_agent_adapter.py | store/index/glossary scope와 세션 수명 | 기존 resources → ToolsSession | capability startup 검사. 연구 runner 의존 금지 |
| 제안 tools_registry.py | 이름·schema·예산·권한·실제 handler 정본 | 모델 도구 목록과 dispatcher를 한 정의로 생성 | 목록에만 있고 실행 안 되는 도구 금지 |
| 제안 browse_tools.py | children/outline/tree/neighbors와 역위치 | canonical metadata → N/D/U 위치 | FolderNavigator/stored_units 재사용, flatten 규칙 교체 |
| 제안 retrieval_tools.py | FTS/literal/title·match_terms·occurrences | 검색 결과 → P/T/L | 기존 tokenizer·bridge 정책 해시 고정 |
| source_tools.py와 제안 read_adapter.py | 정확 READ·정의·참조·coverage | D/U/P → E + navigation_targets | v1 의미를 보존하며 새 extent 계약 별도 버전 |
| 제안 tools_protocol.py | typed action/assessment/review validation | 모델 JSON → 검증된 변경안 | 추가 필드에 v1 닫힌 스키마 재사용 금지 |
| 제안 tools_session.py | 임의 도구 선택·진전·복구·현재 view | action/result/evidence/review → stage 포트 | source-first 참고하되 동결 모듈 직접 의존 금지 |
| repository.py / journal-v2.sql(제안) | 서버 ID·상태·평가·반론·route·action receipt | append-only 사건 → view/검토/출력 | 새 요청 DB schema_version. 과거 DB 수정 안 함 |
| gateway.py / transport.py | 물리 호출, 오류 분류, 전체 payload 영수증 | 표준 gateway → 환경 고정 모델 | 숨은 retry 금지, provider/model fallback 없음 |
| packer/composer/reviewer/gate | support/challenge/contextual와 표적 검토 | E → C → 검토/반론 → control | finding 완성을 입장권으로 쓰지 않음 |
| domain.py 또는 versioned policy loader | SystemHarnessProfile와 LegalDomainSpec v2 | 버전/해시 검사된 정책 | 기존 domain(value)==DOMAIN 분기와 분리 |
| publication.py / recover | v2 journal 판독 및 durable publish | FINAL Result → run JSON | COMMIT_READY 재게시, RUNNING 중단 유지 |
| term-runtime-v1 응답·화면 소비자 | term_agent.exploration_v2에 실행 요약 | 사용자용 답변·확인 한계·선택적 근거 사유 | Request 추가 필드 없이 내부 도구 먼저 연결 |

별도 REVIEW 재진입은 기존 control enum에 없는 제안이다. legal.control v2와 Coordinator·StageRunner·검사기를 함께 변경해야 한다. 대안으로 answer 내부 상태로 재검토를 처리할 수 있으나, 구현 기준은 v2 control=REVIEW와 current draft/assembly 검증으로 고정한다. v1 제어 계약은 유지한다.

app.py의 기존 /documents와 /outline이 있다고 모델이 자동 호출 가능한 것은 아니다. 내부 ToolRegistry에 handler를 연결하고 모델 schema와 실제 입력에 노출해야 한다. 기존 GET API의 전체목록/평탄 outline 응답 의미를 조용히 바꾸지 않는다. 새 browse는 내부 도구로 먼저 제공하고 UI가 필요하면 버전 명시 API를 후속 연결한다.

## 11. 저장·스키마·세대·권한

외부 Request는 현재 question/document_ids/use_llm/scope만 받는 닫힌 계약을 유지한다. 재개 ID·마음대로 만든 metadata를 넣지 않는다. 최초 구현은 한 요청 안의 작업이다. 후속 사용자 발화로 journal을 이어 쓰는 기능은 별도 계약 없이는 제공하지 않는다.

외부 Result는 기존 query/retrieval/selection/assembly/answer를 유지한다. answer.claims에는 canonical source_ids를 내보내고 P/E 별칭을 source_id처럼 넣지 않는다. 별칭·평가·trace 요약은 허용된 term_agent 객체 안의 versioned exploration_v2에 둔다. 상세 전체 journal은 서버에 보관하고 사용자 출력에는 결론/인용/실질 한계 및 요청 시 근거 판단 요약만 표시한다.

새 내부 계약은 tool-exploration-v2, legal-domain-v2, system-harness-profile-v2, legal.control-v2, journal-v2를 명시한다. profile unknown field 허용으로 우회하지 않는다. 모델은 schema version이나 해시를 선택하지 않는다.

기존 원문/색인 필드가 충분하면 서빙 코드·프로필·journal 변경만 필요하다. source_unit에 부모/범위가 없거나 깨졌으면 트리를 추측하지 말고 해당 capability를 비활성 또는 필수 기능 준비 실패로 표시한다. 보완은 새 구조화/색인 세대다. tokenizer·occurrence·참조 해소 정책 변경도 새 파생 색인과 manifest를 필요로 한다. browse용 children map/DF는 원본 세대 해시에 결속된 읽기 캐시로 만들 수 있다.

기본 ROOT는 등록된 전체 자료이며, 에이전트가 정한 임시 검색 필터와 구별한다. 문서명 언급·검색 적중·가설만으로 ROOT를 좁히지 않는다. ‘이 문서만 사용’이라는 명시적 지시나 API 호출자가 실제로 지정한 document_ids가 있을 때만 그 요청의 제한과 출처를 별도로 기록한다. 이번 대화에는 그런 지시가 없다. FolderNavigator의 이전 context 교집합만 계속 사용해 ROOT로 돌아갈 수 없는 함정을 피하기 위해 immutable corpus_root와 reversible exploration_filter를 따로 둔다. 조직별 사용자 ACL을 이미 구현한 것으로 가정하지 않는다.

현행 Pipeline.plan은 scope 미지정 시 document_roles.DEFAULT_SCOPE='기본'을 사용하여 개정이력을 제외한다. 이는 제품의 기존 기본값이며 이번 사용자의 제한이 아니다. 새 v2는 명시 제한이 없으면 '전체'로 ROOT를 구성하는 제안이다. 기존 v1 동작은 유지하고 v2 adapter/plan 분기에서 기본 의미의 변경을 명시한다. 개정이력·현행 본문 역할을 표시하여 탐색 가능성과 현재 적용 근거를 구분한다. 기존 UI가 자동으로 넣는 기본 필터를 사용자 명시 제한으로 잘못 간주하지 않도록 호출 경로도 확인한다.

요청마다 별도 journal·alias·cursor·상태를 사용한다. 캐시는 세대/해시/도구 정책/유효 scope/검색 인자에 결속한다. 프로세스 간 공유 캐시가 권한을 대신하지 않는다. 원문 세대 변경을 같은 요청에 몰래 섞지 않는다.

동일 action 재전송은 action_id+canonical args로 이전 완료 영수증을 반환한다. 도구는 읽기 전용이지만 감사 중복·예산 이중 소비 여부를 구분한다. 새 모델이 의도적으로 같은 READ를 호출한 것은 새 행동 시도이며 I/O 재사용과 분리 계측한다.

프로세스 재시작 시 COMMIT_READY는 기존 outbox를 다시 게시한다. RUNNING은 INTERRUPTED로 보존하며 모델 자동 재호출은 하지 않는다. 새 사용자 요청은 새 세션이고 canonical 자료를 재확인한다. v1/v2 journal opener가 버전을 검사하고 자기 버전만 읽는다.

## 12. 프롬프트·도메인 규칙의 배치

탐색 역할 지침: ‘현재 부족한 정보를 얻을 도구를 고른다. 트리는 주변을 볼 때, 검색은 단서로 위치를 찾을 때 쓴다. 정해진 순서는 없다. 이미 본 원문을 채택/배제할 때 짧은 요약과 이유를 남긴다. 기존 해석·선택은 수정할 수 있다. 결과가 없음을 규정 부재로 단정하지 않는다.’

검토 역할 지침: ‘원질문·현재 주장·support/challenge 원문·사실 가정을 대조한다. 인용이 존재한다는 것만으로 승인하지 않는다. 문제를 특정 주장과 E에 연결한다. 자료 부족과 해석 오류를 구분한다. 자신도 틀릴 수 있으므로 반론을 받아 원문으로 다시 대조하고, 해결되지 않으면 불확실성을 남긴다.’

도구/원문 내용은 데이터 영역에 둔다. 원문 속 명령을 시스템 지침으로 실행하지 않는다. 프롬프트 표현 강도·모델 설정·한도는 SystemHarnessProfile, 원문 적격성·사실 구분·표적 법률검토 기준은 LegalDomainSpec에 둔다. 버전과 해시를 요청에 결속한다.

## 13. 검증 계획과 도입 단계

현재는 문서 설계·정적 일관성 확인만 수행한다. 새 모델 호출, 과거 실행 재채점, 품질 실험은 하지 않는다. 미래 실험은 저장소 실험 표준을 끝까지 읽고 동일 scope reservation을 확인한 뒤 새 ADR을 선점한다. 이미 완료된 snapshot/run은 변경하지 않는다.

| 단계 | 산출물 | 진입 조건 | 종료 기준 |
|---|---|---|---|
| P1 계약·자료 연결 | 버전 계약, registry, 읽기 전용 adapter | 본 설계와 부모 코드/데이터 선택 | 전체 도구가 모델 schema→handler→receipt까지 연결 |
| P2 주변/검색 도구 | browse/search/match/occurrence/locate | P1 | 실제 children·outline·범위·cursor·역매칭 시나리오 통과 |
| P3 상태·복구 | view·assessment·typed repair·journal | P2 | P/E 오입력·반복·부분 실패 뒤 유효 작업 보존 |
| P4 도메인/검토 | 근거 묶음·표적 challenge·반론·gate | P3 | 잘못된 선택·예외 누락·오승인·오거절 모의 시나리오 |
| P5 API/출력/재시작 | 4 stage·control-v2·publication·소비자 | P4 | POST ask부터 출력·피드백·outbox까지 연결, v1 회귀 |
| P6 실제 품질 평가 | 사전 동결 기준군/후보/새 질문 | 실험 ADR·데이터/모델 허용 확인 | 아래 품질·비용·회귀 기준을 사전 동결하고 평가 |
| P7 활성화/현장 | 새 release·apply/rollback·인계 | 승격 자격과 명시 절차 충족 | 로컬 활성화와 GENOS 현장 실행 각각 증거 확보 |

기능 검사는 [ACCEPTANCE.md](ACCEPTANCE.md)로 추적한다. fixture의 고정 답안은 제품 모델 입력에 넣지 않는다. 도구 목록에 이름이 있는 것, 내부 handler 단위 테스트, 실제 HTTP 경로, 의미 품질을 각각 보고한다.

품질 평가는 (1) 문서 탐색, (2) 일상어 역매칭, (3) 첫 후보가 틀린 질문, (4) 원문은 맞지만 예외 적용이 어려운 질문, (5) 사실 부족/규정 부재, (6) 검토자 오류를 포함한다. 기존 실패 사례는 개발 회귀용이고 새로운 holdout은 문항/문서군 단위로 분리한다. 의역 여러 개를 독립 사례로 부풀리지 않는다.

단계별 metric: 발견→도구 반환→모델 제시→READ→평가→명시 채택→support/challenge 조립→검토→인용의 유일 source/정확 extent 집합. READ가 선행 제시보다 먼저일 수 있으므로 이벤트 순서와 각 상태를 모두 저장한다. server preread와 model action을 분리한다. 근거를 보여 줬다는 사실을 이해/자율 발견으로 세지 않는다.

오류 지표: 잘못된 범위에서 회복한 비율, P/E 복구, 예외 누락, 거절된 정답 근거, 잘못 승인된 주장, 잘못 거절된 맞는 주장, false ‘없음’, 근거 없는 사용자 사실, 유효 부분답 보존. 최종 정답·인용 정확도·미답변·회귀·물리 호출·입출력 토큰·E2E p50/p95를 함께 본다. 모델 자기 승인률을 정확도로 보고하지 않는다.

계약 fixture 통과 목표 N03은 해당 고정 사례 전부 통과이며 일반 정답률 100% 목표가 아니다. 품질 수치 목표는 미산정이다. 실제 실험 전에 기준군 품질·허용 회귀·비용/지연 상한·표본·중단 기준을 결정하고 동결해야 하며, 이 값들이 비어 있으면 승격 판정은 할 수 없다.

## 14. 비용·성능·일정의 예상 범위

| ID | 구분 | 단위/근거 | 값·산식 | 해석/검증 |
|---|---|---|---|---|
| N01 | 관측 설정/제안 비교 조건 | 요청당, domain.py DEFAULT_PROFILE | 모델14, 도구56, wall300초, reserve3, cycle3 | 실제 소비량·처리량 아님. 실험 전 재확인 |
| N02 | 가정 설정 | 같은 오류 지문/주장 버전 | 정정1회, 이의 재검토1회 | 전역 한도 우선. 효과 미검증 |
| N03 | 목표 | ACCEPTANCE 고정 fixture | 해당 계약 전부 통과 | 실제 질문 정답률과 분리 |
| N04 | 계산식 | 요청당 모델 토큰·모델별 요율 | C=sum(input_i*rate_in_i+output_i*rate_out_i)+tool_IO+운영/검토비 | provider 요율의 단위를 맞춰 적용. 현재 금액 미산정 |
| N05 | 계산식 | 기준 대비 요청당 비용 | ΔC=추가 도구결정+평가출력+challenge/재검토-중복읽기/잘못된경로 절감 | 손익분기 ΔC=0. 추가 검토가 회복 없이 늘면 비용 악화 |
| N06 | 미확인 | 새로운 holdout/실제 환경 | 정확도 개선·회귀·p95·동시 처리량 | 이 설계에서 추정하지 않음 |
| N07 | 미확인 | 구현 인일/달력 일정 | P1~P5 구현+통합+계약+문서+재작업, 이후 실험/현장 별도 | 담당자 처리량과 데이터 결함 미측정. 임의 일수 미제시 |

트리 조회는 모델 없이 실행되는 도구이나 모델이 이를 선택하고 결과를 읽는 토큰·호출 비용이 생긴다. 짧은 평가를 기존 결정 응답에 함께 넣어도 출력 토큰과 입력 반복 비용이 있다. challenge 원문 보존은 오답 방지의 후보 수단이며 비용 절감으로 단정하지 않는다.

민감도: 추가 재검토 한 번이면 그 검토 input/output 비용과 왕복 지연만큼 증가한다. 이것이 줄이는 후속 재탐색/오답 비용보다 크면 손해다. 토큰·호출·시간을 서로 대체하지 않는다. 단회 지연으로 p95를 예측하지 않는다. 하네스 강도를 강화할수록 미답변이 늘어나는 조건도 평가한다.

## 15. 남는 위험과 도입 책임

| 위험 | 탐지·대응 | 남는 한계/책임 |
|---|---|---|
| 탐색자와 검토자가 같은 오독 | 원문 적용 대조·challenge·별도 holdout/사람 검토 | 코드만으로 해결 불가, 도메인 평가 책임 |
| 구조/용어/참조 데이터 결함 | 해시와 연결 검사, 미해소 표시, 대체 검색 | 해시는 의미 정확성 보증 아님, 데이터 구축 책임 |
| 과도한 장부/검토 | 사용 근거 중심 평가, 표적 검토, 비용·미답변 지표 | 최적 강도는 모델별 검증 필요, 시스템 프로필 책임 |
| 좁은 범위에 갇힘 | ROOT와 임시 필터 분리, breadcrumb/오류 피드백 | 명시 사용자 범위 밖은 확장 불가 |
| 후보가 너무 많음 | 페이지·route별 탐색·inspect·필터 | 임의 top-k 외 결과도 접근 가능하게 유지, 검색 구현 책임 |
| 잘못 배제한 자료 재발견 못함 | park/reopen·route provenance·판단 STALE | 모델이 다시 보지 않을 수 있음, 회귀 평가 필요 |
| 재검토에서 맞는 답 소실 | 근거 있는 objection·표적 무효화·반론 | 미해결 의미 충돌은 부분답/한계 |
| 동시 요청/재시작 오염 | 별도 journal·버전 opener·outbox·cache binding | 전역 수용량/조직 ACL은 현장 검증 별도 |

담당 책임은 코드 변경 지도 기준으로 나눈다. 도구/계약/복구는 런타임 구현, 데이터 무결성과 재색인은 구축 경로, 적용 판단 정책과 평가 기준은 도메인 검토, 활성화는 release 운영 절차다. 모델에게 이 책임의 정본 변경 권한을 넘기지 않는다.

## 16. 배포·롤백·문서의 완료 조건

설계 산출물은 이 디렉터리에만 추가한다. 기존 설계/ADR/원문/활성 포인터를 덮어쓰지 않는다. 제품 구현 시 frozen candidate와 코드·schema·정책·세대 manifest를 함께 결속한다. 선택 이름은 제안 legal-agent-tools-v2이며 현재 service allowlist에 있는 것처럼 실행 명령을 제시하지 않는다.

승격은 저장소의 Accepted/out-of-sample/decision_eligible/complete 조건과 hash 고정 promotion plan, 명시 apply 절차를 따른다. 실패하면 이전 code/data/profile release로 돌아간다. 새 journal은 보존하고 과거 journal을 다운그레이드 변환하지 않는다.

GENOS는 이 세션에서 접근할 수 없다. 인계에는 코드 리비전, 의존성, 모델/프로필 설정 이름, 기존 API 계약, 시작 capability 검사, 계약 검사, 중단/재게시/롤백 방법을 포함한다. 외부 신규 실험은 현행 Gemini 정책과 허용 공개 자료 범위, 최종 GENOS는 내부 모델·자료 경계를 따른다. 로컬 설계·검사로 현장 배포 성공을 선언하지 않는다.

이 문서 자체의 완료는 요구사항→도구/하네스 계약→변경 파일→실패 사례→검사 연결이 있고, 자체 검토와 파일 지문을 남기는 것이다. 제품 구현 완료와 품질 인증은 이후의 별도 결과다.
