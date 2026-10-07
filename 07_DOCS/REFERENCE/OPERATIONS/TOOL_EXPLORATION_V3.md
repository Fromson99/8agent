# 관계 전반의 탐색·판단 기록 v3

2026-09-21 작업 코드 구현. 명시 선택 `legal-agent-tools-v3` / 파이프라인 프로필
`legal-agent-rag-v3`. 원문과 후보의 연결을 자동 안내하고, 질문별 채택·기각·보류와 관계 검토를
journal·다음 모델 입력·출력 화면으로 전달한다. 기존 요청 → Pipeline → 요청 세션 →
Coordinator/StageRunner → outbox 경로를 사용한다.

작업 기본 `legal-agent-tools-v2`, 로컬 활성 포인터 `document-navigation-rag-20260921-v1`
(generation 17)은 유지했다. Qwen CM 3문항의 탐색 기록은 ADR-0485에 있으며,
답변 완료 실패로 품질 개선은 미확인이다. 아래 입력 분할 수정 이후의 실모델 재실험은 아직 없다.
MAIN 승격·GENOS 현장 배포는 수행하지 않았다. v1/v2 journal을 변환하지 않으며 v3는 새 요청 journal만 만든다.

## 관계와 처리

| 구분 | 실제 연결 | 완료 판단 |
|---|---|---|
| 원문 참조 | 인용·준용·위임사항 구체화·공식 위임·별표/서식, 정방향/역방향 | 채택 E에 연결된 outgoing 참조는 질문별 관련성 판단 필요 |
| 정의 | 읽은 용어 → 문서별 정의 후보와 적용 범위 상태 | 의존 주장에는 실제 정의 원문 READ와 범위 검토 필요 |
| 용어 | 동의·반의·상위·하위·연관, 원래 코드와 방향 | 탐색 단서. 반의어를 동의어로 확장하지 않음 |
| 출현 | 읽은 용어 → 같은 용어가 출현한 원문 | 출현 자체는 법적 관련성 확정이 아님 |
| 구조 | 실제 읽은 항/호 → 상위·하위·같은 계층 마디 | 구조를 법적 우선순위로 해석하지 않음 |
| 원천 지식 | 표제어 개념 대응 → 직접 원천 관계·정의, 대응/보류 상태 | FIBO/Wikidata/NLSH 등은 원래 predicate·출처 보존 |
| 의미 검토 관측 | 선택 용어집의 sense_assertion이 있을 때 동일성·포함·중첩·상보·연관 관측 | PROPOSED/충돌 상태 보존. 정본 승인으로 승격하지 않음 |

선택 용어집에 의미 관측 테이블이 없으면 `lexical_observations=UNAVAILABLE_IN_SELECTED_GLOSSARY`다.
원천 지식 조회기·테이블이 없거나 조회 실패·페이지 잔여가 있으면 미확인으로 남긴다.
예외·특례·우선 적용·치환 등을 새로운 정본 의미 관계로 추론하여 생성하지 않는다.
기존 색인의 참조 역할은 문장 수준 단서이므로 혼합 문장은 AMBIGUOUS로 안내한다.

READ마다 6개 관계 묶음의 첫 페이지 조회 작업을 원문과 함께 원자적으로 등록한다.
추가 페이지는 `follow_relations(target=E/T/K, family=..., cursor=...)`로 이어 읽는다.
`all`은 관계 묶음별 페이지를 차례로 순회한다. 수동 `follow_reference`도 같은 어댑터를 쓴다.
참조 스캔 미완료는 관련 주장 완료를 차단한다. 다른 탐색 관계의 미완료는 출력 요약에 남긴다.
관계에 의존하는 주장은 종류와 무관하게 relation_dependencies와 관계 검토에 연결한다.

자동 전문 읽기는 **검증된 단일 문구·유일한 정확 범위·허용 scope의 outgoing 준용**에만 적용한다.
6개 관계 묶음의 첫 조회가 모두 완료되고 전체 관계가 `relation_page_size` 이내일 때만
선읽기를 예약한다. 관계가 많거나 조회가 미완료이면 `SKIPPED_SELECTION`을 보존하고 모델 선택을 기다린다.
A→B 직접 대상 한 단계이며 B→C는 안내만 한다. 역참조·일반 인용·정의·용어·구조는 모델이
선택하여 READ한다. 원문 재제시나 캐시 재사용으로 자동 깊이를 초기화하지 않는다.
순환 edge를 보존하면서 같은 대상의 자동 재읽기는 방지한다.

## 입력 분할과 관계 선택

`R`은 자료 묶음, `F`는 폴더이므로 READ할 수 없다. 시작 시 root만 있으면
`locate` 또는 `search` → 반환된 D/P/U 위치 READ 순서다. 도구 스키마·시스템 설명과
잘못된 READ 응답에 수정 가능한 호출 경로를 제공한다.

관계가 12개(설정 `relation_page_size`)를 넘으면 `relation_menu`에 유형·방향·대상 위치·
미해결 상태를 먼저 제시한다. 모델은 `inspect_relation(relation_id=...)`로 관계를 펼치고,
필요한 대상만 READ한다. 메뉴에는 대상 전문·발췌를 넣지 않으며 메뉴 제시는 관계 검토나
정확 원문 제시 영수증으로 인정하지 않는다. 펼친 관계와 출발·대상 원문을 실제로 제시해야
기존 질문별 판단·공동 검토 계약을 충족한다.

`relation_views.py`는 원문·관계·행동·판단 기록을 예산 안에 넣고 생략분을 `continuations`로
안내한다. 모델이 제공된 `view_page(section, cursor)`를 선택하면 다음 부분을 제시한다.
페이지 토큰은 요청·작업 종류·자료 binding에 결속된 SQLite `navigation_cursor`의
불변 snapshot이며, 이전 페이지를 앞에 다시 끼워 넣지 않는다. 메뉴·기록 이어보기는
원문 READ가 아니며 새 읽기 글자 수를 늘리지 않는다.

READ는 설정 상한과 `max_context_chars / 8`, 모델 byte 예산에 따른 보수적 한도 중
작은 값을 적용한다. 원문을 정확 span으로 나누고 기존 READ 인자와 `next_cursor`로
이어 읽는다. 저장된 원문을 임의로 잘라 기존 E ID의 내용·hash를 바꾸지 않는다.
입력 검사는 최종 직렬화한 한글 UTF-8, 시스템 설명과 두 스키마 사본까지 포함한다.
필수 출발·대상 공동 검토 자체가 한도를 넘는 주장은 미확인 상태로 남긴다.

fulltext 검색은 순위·범위·중복 제거 후 현재 페이지의 후보만 발췌·위치 카드로 만든다.
종료 요약은 모든 구역을 합쳐 64줄로 제한하며 전체 건수·생략 안내·실행 ID를 유지한다.
전체 행동·판단·관계 원장은 요약 길이와 무관하게 journal에 보존한다.

## 계약·설정

- `relations_protocol.py`: v3 모델 출력 스키마와 AuditSummary 검증.
- `relations_tools.py`, `relation_cards.py`: 기존 SourceSession._read를 재사용하는 탐색·발췌·관계 조회.
- `relations_repository.py`, `journal-v3.sql`: 목적, 실행 결과, 원문·자동 작업 원자성,
  질문별 평가 버전, 관계·관계 집합 의존성, 정확 제시 영수증.
- `relations_session.py`: 실제 wire 제시 확인, 질문별 평가·수정 이력, 출발/대상 공동 검토,
  누락 의존성 차단과 독립 주장 보존, 완료/중단 요약.
- 외부 닫힌 `term-runtime-v1` Result 유지. 새 출력은 `assembly.term_agent.exploration_v3`.

프로필은 `00_SYSTEM/LEGAL_AGENT/profile-tools-v3.json`이다. 기본 모델 binding은 비어 있다.
실제 요청에는 선택 환경에서 검증한 모델 ID·adapter·endpoint identity·trust zone·입력 byte 한도를
명시한 프로필과 SHA256이 필요하다. 자동 provider/model fallback은 없다.

초기 정책 상한: 발췌 360자/개·view 합계 3,600자, 관계 12개/페이지·14,000자/조회,
스캔 5초/호출, 자동 준용 READ 3회/요청·예약 원문량 12,000자/요청·깊이 1,
자동 작업이 남겨 두는 도구 슬롯 4개. 모델 최종 작성·검토 예약은 기존 finalization_reserve를 따른다.
이는 정책 상한이며 처리량·정답률·최적값의 실측 결과가 아니다.
자동 원문량은 보수적 예약량이고 실제 읽기/재사용 글자 수는 각 결과의 budget에 따로 기록한다.

모델 없는 목록 조회는 기존 필터를 유지하고 모델 호출·관계 선읽기를 하지 않는다.
발췌와 READ는 구별되며 발췌만으로 인용할 수 없다. 발췌는 실제 전송 view에서 살아남은
범위·hash만 제시로 기록한다. 정확 E도 실제 wire가 저장 view와 일치해야 제시로 인정한다.

## 실행·확인

WSL 저장소에서 계약을 재생성한다. 이 명령은 작업 계약/엔진 hash를 갱신하고 v3를 명시 프로필로
등록한다. 활성 포인터나 기본 프로필을 전환하지 않는다.

```bash
bash 06_TOOLS/check_wsl_dev_environment.sh
.venv/bin/python 06_TOOLS/run_tool.py legal_agent_contracts.py --version v3
.venv/bin/python -m pytest 05_TESTS/CONTRACTS/test_tool_exploration_v3.py 05_TESTS/CONTRACTS/test_tool_exploration_v3_paging.py 05_TESTS/CONTRACTS/test_tool_exploration_v2.py -q
```

로컬 API는 기존 create_app의 `implementation='legal-agent-tools-v3'`, `legal_agent_profile`,
`legal_agent_transport`로 명시 선택한다. GENOS에서는 `GENOS_RAG_IMPLEMENTATION=legal-agent-tools-v3`,
`LEGAL_AGENT_PROFILE`, `LEGAL_AGENT_PROFILE_SHA256`을 설정한다. 코드와 선택 세대·용어집·설정 hash를
함께 반입한다. 플랫폼 내부 모델과 현장 실행은 [GENOS.md](../../../GENOS.md) 및 기존
[서비스 운영 안내](GENOS_CODE_SERVING_CURRENT.md)를 따른다. 현장 연결은 이 세션에서 시도하지 않는다.

로컬 `/rag/`의 ‘탐색·근거 판단’은 textContent로 표시하며, GENOS 채팅 render는 이스케이프한
확인 과정·미확인 요약을 덧붙인다. 모델로 답변을 다시 생성하지 않는다. 모델 제출 설명과 시스템
정책을 구분하고, 요약 생략·전체 건수·실행 ID를 표시한다. 원문·provider wire·키를 공개 요약으로
복사하지 않는다. 기존 피드백은 실행/답변/세대 결속을 그대로 사용한다.

운영자 조회는 해당 journal 소유 계정으로 실제 semantic runtime root와 run ID를 지정한다.
예시 경로는 로컬 기본값이며 다른 실행 환경에서는 실제 선택 root로 바꾼다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py legal_agent_trace.py \
  --runtime-root /home/jin/8-AGENT/90_RUNTIME/semantic --run-id <실제_run_id>
```

읽기 전용 SQLite 연결로 root 범위·소유 계정·DB 버전·binding/이벤트/평가 hash를 검사하고
목적·결과·평가 버전·제시 기록을 반환한다. provider 요청·응답 원문은 출력하지 않는다.
공개 HTTP에 run ID만으로 journal을 조회하는 endpoint는 추가하지 않았다.

## 중단·재게시·롤백

살아 있는 요청의 동일 action ID 재전송은 목적을 포함한 canonical proposal hash가 같아야 한다.
같은 인자라도 이유가 다르면 별도 행동 ID가 필요하며 원문 I/O 캐시만 공유할 수 있다.
원문 저장 이후 관계 조회/선읽기가 실패해도 앞선 원문과 목적 기록은 유지한다.
저장됐지만 제시되지 않은 E, 제시 후 미평가, DEFER, STALE, UNASSESSED_AT_STOP을 구분한다.
새 관계 발견·질문별 평가 변경은 그 버전에 의존한 주장/검토를 무효화한다.

소유자를 잃은 RUNNING은 INTERRUPTED로 종료한다. 미완료 자동 작업·행동과 원문 미평가 상태를
남기며 중단된 모델 세션을 자동 재개하지 않는다. COMMIT_READY는 고정 outbox만 재게시한다.
재게시 시 관계 재조회·모델 재호출은 없다.

롤백은 요청 drain 후 이전 검증된 프로필/릴리스를 명시 선택한다. 진행 중 v3 요청에 v2 코드를
주입하거나 v3 DB를 v2로 변환하지 않는다. 새 생성 데이터/색인은 이번 구현에 없다.
이미 기록한 실행·응답·평가·피드백은 보존한다.
