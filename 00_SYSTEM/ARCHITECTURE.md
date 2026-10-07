# MAIN — 원문과 용어 기반 탐색

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
| 통합 구축 | `pipeline.py build-all --run-id NAME --execute [--reference-model-profile PROFILE]` | 전체 문서 구조화 → 명시 원문 통합 → 기존·신규 용어 후보 검토 → 결정론 연결 → 설정한 모델의 참조 해소·자동 승인 → 색인·서빙 후보 검증. 기존 `--reference-review-state` 소비도 유지 |
| 단계별 통합 구축 | `pipeline.py document-release select/merge/prepare/review/index/status/verify` | 종료된 구조화의 성공분을 명시 새 범위로 선택 가능. 원래 실패 기록·제외 사유와 해시를 보존하며 통합/검토/색인을 각각 실행·재개. [실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_RELEASE_STAGES.md) |
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
