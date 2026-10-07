# 에이전트의 연결관계 판단 수정 계획

2026-09-29 · 구현 설계안 · 자체 검토 · 구현·모델 호출·실험·MAIN 전환·GENOS 배포 미실행

## 1. 수정 목표

**에이전트가 질문의 요구와 연결 후보를 함께 보고, 필요한 연결 원문을 확인한 뒤 답변 충분성을 결정하도록 한다.** 새 연결 생성 로직은 입력 데이터 계약으로 사용한다. 관계의 존재·좌표 해소와 질문에 대한 필요성 판단은 별도 상태로 남긴다.

CM003의 실패를 특정 단어·문항 차단 규칙으로 고치지 않는다. 에이전트가 필요한 관계를 선택하고, 서버는 실제 전달·읽기·범위·판단 기록의 일관성을 확인한다. 모든 연결 대상을 자동으로 읽는 정책으로 확대하지 않는다.

최초 범위는 현재 v5의 bounded 원문 질의 경로다. 명시 도구 탐색 경로와는 관계 카드·읽기·판단 기록을 공유한다. 입력 중복 정리 계획과 공통 표현을 사용하되, 여기서는 **질문 요구 → 관계 판단 → 원문 확인 → 종료 판단**의 실행 순서를 담당한다.

### 컨텍스트 최적화 작업과의 책임 분리

2026-09-29 후속 확인에서 컨텍스트 최적화 작업은 구현·실험 진행 상태였다. 두 계획은 `source_selection.py`, `bounded_source_session.py`, `workflow_tiers_session.py`, `workflow_relation_cards.py`, `relations_repository.py`의 같은 파일을 수정할 수 있다. 목표가 다르더라도 이 파일들을 동시에 독립 수정하면 충돌하거나 서로 필요한 필드를 지울 수 있다.

| 영역 | 컨텍스트 최적화 담당 | 이 판단 계획 담당 |
|---|---|---|
| 모델 입력 표현 | 공통 본문·문서·구조·관계 ID, 중복 제거, 실제 전송 예산·복원 영수증 | 판단에 필요한 역할·witness·범위·읽기 상태·요구 ID의 필수 입력 목록 제공 |
| `source_selection.py` | `compact_view`·`card`의 전송 표현, provenance 표시 중복 통합 | 읽기 전/후 판단 schema·충분성 결정, extent 완료와 선택 근거 연결 |
| `bounded_source_session.py` | `_Gateway.request`와 전송 projection | `investigate`의 순서·관계 선택 READ·요구별 종료/복구 |
| 관계 카드 | 표시용 문서·witness 공통화와 ID 대응 | 정본 target별 범위 해석, 현재 READ 범위와 관계 범위 대조 |
| 원장 | `reserve_attempt`의 projection·번호·wire 검증 | 판단/intent/event 저장과 질문·관계·원문 revision 의존성 |
| 작성 | 선택/필수 문맥의 전송 집합과 원문 복원 | 그 필수 관계를 누가 어떤 요구 때문에 선택했는지, 무엇이 미확인인지 연결 |

이 계획에서는 별도의 본문 압축·번호 변환·관계 표시기·전송 예산 모듈을 구현하지 않는다. 동일 파일의 수정은 컨텍스트 후보가 완료된 뒤 그 후보의 정확한 코드·schema·projection 버전을 기준으로 순차 적용한다. 다른 작업의 진행 중 코드나 활성 MAIN을 기준으로 무심코 섞지 않는다. 그동안 판단 계약·원문 범위 요구·테스트 시나리오 정의는 진행할 수 있다.

검증은 컨텍스트 후보 자체 → 같은 후보에 판단 수정 추가 → 결합 회귀 순서로 나눈다. 판단 비교의 두 arm은 같은 컨텍스트 표현·참조 세대·모델·예산을 사용한다. 완료 후보의 실험 ID/arm ID를 결속하고, 결합을 실험으로 실행할 때 표준의 정확 부모·관계·merge 계보를 따른다. 어느 쪽 개선 효과인지 구분되지 않는 동시 변경 비교는 피한다.

위 구분은 이 계획의 책임 경계다. 다른 작업에 지시를 보내거나 다른 작업의 코드·계획을 변경한 것은 아니다.

## 2. 확인한 기준과 문제

| 구분 | 확인 내용 |
|---|---|
| 현재 로컬 선택 | `legal-agent-structure-catalogue-pecab-repair-20260929-r1`, ACTIVE_RELEASE generation 31 |
| 현재 원문·색인 | `01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation`; navigation v3 |
| 진단 근거 | ADR-0557 CM003의 기존 공개 Qwen 요청·응답·journal. 당시 generation 30의 기록이며 generation 31 재실행은 아님 |
| 새 참조 구축 | MAIN 작업 구축 경로에 정밀 참조·모델 해소가 연결됨. 새 구축 결과가 현재 활성 DB를 교체했다는 뜻은 아님 |
| 실행 환경 | WSL 로컬 코드·저장 기록 확인. GENOS 현장 모델·배포·질문 실행은 미확인 |

CM003의 첫 선별 호출에는 제26조 원문과 후보 하나가 있었지만 `via_references=[]`였다. 원문에 세칙 예외가 명시되어 있는데도 모델은 `needs_fulltext=false`를 반환했다. journal에는 SYSTEM_POLICY READ 한 번, 관계 탐색과 자동 관계 작업은 각각 0번이었다. 작성 입력도 관계 목록이 비어 있었다.

현재 서버의 선별 검증은 JSON 형식, 허용 후보 ID, 중복 선택, 비어 있지 않은 이유를 확인한다. 충분성 판단에 필요한 관계가 확인됐는지는 검사하지 않는다. 구조 일치는 참조 확장 전에 반환하며, SYSTEM_POLICY READ는 자동 관계 탐색 예약 조건에서 빠진다.

일반 검색의 관계 경로도 source ID로 확장하고, 선별 입력은 방향·해소 상태 중심으로 축약한다. 새 관계의 역할·양끝 항호목·문자 범위·witness를 생성해도 현재 bounded 소비자가 그 정보를 모두 판단에 쓰는 것은 아니다.

## 3. 목표 실행 순서와 책임

```text
요청 분류
  → 원질문의 답변 요구 확정
  → 구조 우선 또는 fulltext로 출발 원문 확보
  → 읽은 범위에 연결된 정참조·역참조 후보 제시
  → 에이전트: 대상 읽기 / 현재 요구에 불필요 / 미확인
  → 선택한 대상의 정확 범위 읽기
  → 에이전트: 원문을 대조해 근거 채택·제외·보류
  → 요구별 충분성 판단
      ├─ 필요한 연결 원문이 남음: 관계 탐색 계속
      ├─ 연결로 회수할 수 없는 근거 부족: 기존 검색
      ├─ 사용자 사실 부족: 조건부 답변 또는 필요한 사실 질문
      └─ 충분 또는 예산 종료: 선택 근거로 작성, 미확인 사항 반영
```

| 서버의 책임 | 에이전트의 책임 |
|---|---|
| 저장된 관계·원문·정확 범위를 조회하고 요청 범위를 검증 | 어떤 관계가 원질문의 어느 요구에 필요한지 판단 |
| 보이는 후보 ID, 실제 전달·읽기 완료, 미조회 페이지와 예산을 기록 | 필요한 대상 선택, 불필요·보류 이유 설명 |
| 이미 읽은 정확 범위를 재사용하고 다른 항호목을 구분 | 원문을 확인한 뒤 선택·반대 근거·충분성을 판단 |
| 미읽기·미전달·미확인을 확인 완료로 기록하는 상태 모순 거부 | 원문만으로 확인할 수 없는 법적 의미는 미확인으로 유지 |

서버가 모델의 법률 판단을 키워드 규칙으로 대신하지 않는다. 형식·읽기 검증을 통과해도 필요성·불필요 판단의 의미가 틀릴 수 있으며, 이는 실제 모델 평가 대상으로 남는다.

## 4. 제안 판단 계약

새 내부 계약 `relation-investigation-v1`과 기존 디렉터리 안의 helper `legal_agent/relation_investigation.py`를 제안한다. 별도 실행기나 구축 파이프라인을 만들지 않는다. 외부 `term-runtime-v1`과 원문 DB 계약은 유지한다.

### 모델에 제공할 자료

- 원질문과 질문 요구 ID, 현재 읽은 출발 원문의 정확 본문.
- 관계 ID와 출발·대상 문서/판본·조/항/호/목, 원천 방향과 탐색 방향.
- 원천 관계 역할과 해소/범위 상태. 관계 역할과 질문에 대한 필요성은 별도 필드.
- 관계를 나타내는 원문 문구와 그 위치. 역참조의 출발 원문을 아직 읽지 않았다면 안내용 witness라고 표시.
- 대상 읽기 상태, 미해결 후보·자료 결손, 남은 페이지와 공통 예산.

본문·문서명은 공통 정의와 ID 참조로 전달한다. 서로 다른 관계의 witness·범위·역할을 지우며 묶지 않는다. 표현·번호·전송 영수증은 [입력 중복 정리 계획](../MODEL_DATA_PRESENTATION_REPAIR_PLAN_20260929/PLAN.ko.md)의 계약을 따른다.

### 읽기 전과 읽기 후 판단을 분리

| 시점 | 모델 출력 제안 | 기록과 검증 |
|---|---|---|
| 대상 읽기 전 | `READ_TARGET`, `NOT_NEEDED`, `DEFER`; 관계 ID·요구 ID·이유·판단에 쓴 자료 ID | 현재 성공한 요청에 전달된 후보만 허용. 읽지 않은 대상 본문을 확인했다고 쓰지 못함 |
| 대상 읽기 후 | 기존 `RELEVANT`, `NOT_RELEVANT`, `DEFER` 관계 평가 및 원문 근거 | 기존 `validate_relation_assessment`의 전달·출발/대상·span 검증을 재사용 |
| 종료 판단 | 요구별 `SUFFICIENT`, `NEEDS_RELATION_READ`, `NEEDS_SEARCH`, `MISSING_FACT`, `UNRESOLVED`; 근거·관계 ID·이유 | 미읽기 필요한 대상, 실패한 READ, 존재하지 않는 근거 ID와 확인 완료의 상태 모순 검사 |

원문에 참조 문구가 있지만 관계 대상이 없으면 에이전트가 해당 witness를 근거로 기존 검색을 요청할 수 있게 한다. 결과를 검증 없이 새 정본 edge로 저장하지 않는다. 관계 목록이 비었다는 사실만으로 필요한 예외가 없다고 결론짓지 않는다.

기존 `needs_fulltext` 불리언은 새 내부 판단에서 `NEEDS_SEARCH`로 서버가 유도한다. 구조 일치 후 관계 판단을 건너뛴 채 이 불리언 하나로 종료하는 분기를 대체한다. 지침·스키마·parser를 같은 버전으로 결속하고, 현재 SYSTEM의 “issues와 choices 두 키만 출력” 지침과 구조 분기의 추가 필드 충돌도 함께 정리한다.

## 5. 변경 지도

| 기존 위치 | 제안 변경 | 소비자·호환성 |
|---|---|---|
| `bounded_source_session.py:investigate`, `prepare_question_plan` | 법률 질의의 요구 구성을 충분성 판단 전에 실행. 기존 뒤쪽 호출을 이동하고 중복 호출하지 않음. 원문 확보 뒤 관계 판단·선택 READ·요구별 재판단을 연결 | 기존 요청 세션·gateway·공통 예산 사용. DIRECT/BROWSE 등 분류 경로 유지 |
| `source_recall.py:discover`, `_scoped_discover`; `source_recall_global.py:discover` | 구조 출발점과 fulltext 출발점 모두 같은 직접 관계 조회 소비자로 연결. 후보 발견과 모델이 선택한 후속 READ를 구분. source ID만으로 정→역참조를 이어 붙이는 확장 제거 | 기존 검색 초기 후보 유지. 관계를 더 적게 읽어 누락이 생기는지도 비교 검증 |
| `workflow_relation_cards.py:references`, `term_references.reference_targets` | target별 정보는 `reference_targets`로 해석하고 source/target의 문자 범위까지 보존. 읽은 출발 범위와 겹치는 관계만 조회; 역참조의 방향·witness 유지 | 새 정밀 계약을 우선 사용. 구 v3는 블록 범위로 읽고 정밀도 부족을 표시 |
| `workflow_relations_tools.py:execute`, `prefetch_direct` | bounded READ 뒤 관계 메타데이터 조회를 명시적으로 실행. 후보 제시는 actor 때문에 생략되지 않게 하고, 대상 READ는 이번 모델 선택으로 실행 | 관계 도구와 journal 재사용. 기존 일반 탐색의 자동 READ 정책 변경은 별도 프로필로 격리 |
| `source_tools.py:_read`, `workflow_relations_tools.py:read`, `covers`; `reference_spans.py` | target 문자 구간·하위 마디 READ와 cp 기준 완전성 검증. 조 전체·부모 문맥 확대는 모델의 별도 행동·이유로 기록 | 원문 조건·예외가 target 밖에 이어지면 주변 구조를 조회하고 필요한 범위를 추가 READ |
| `source_selection.py:originals`, `provenance`, `compact_view`, `select_sources` | 관계의 역할·witness·범위가 판단 입력에 남도록 함. 후속 근거는 source ID와 요청 extent를 함께 식별. 읽기 후 선택에 관계·요구 ID 연결 | 같은 조의 서로 다른 호를 하나의 완료 상태로 합치지 않음. 전달 표현은 공통 계획과 공유 |
| `relations_repository.py`, `relations_session.py` | 기존 `put`/version/event/intent/relation_assessment에 읽기 전 의도·읽기 후 평가·요구별 충분성 저장. relation·evidence·question revision 의존성을 연결 | 세대/view 변경 시 이전 판단 무효화. SQLite 정본 테이블을 새로 중복 생성하지 않음 |
| `bounded_source_session.py:persist_bounded_selection`; `workflow_tiers_session.py:relation_requirements`, `commit_draft` | 선택 근거의 `relation_refs=[]` 고정을 없앰. 해당 요구의 판단에서 사용·미확인으로 선언한 관계를 작성에 연결 | selected-only 인용·witness/target 검증 유지. 미확인 요구는 한계 또는 조건부 주장으로 연결 |
| v5 profile·domain·관련 schema·ENGINE/PIPELINE | 새 내부 판단 계약과 선택 기능을 후보 프로필에 결속하고 실제 호출 코드 hash를 갱신 | 기본 활성 프로필은 계획 단계에서 변경하지 않음. frozen 릴리스와 작업 코드 구분 |

### 정확 범위 읽기의 중요한 연결 조건

현재 `originals()`와 `spans_complete()`는 조문 전체를 읽어야 완료로 간주한다. READ만 좁히면 연결 근거가 미완료로 분류되어 선별에서 탈락한다. 따라서 **요청 범위 읽기 완료**를 새 별도 상태로 추가하고, 기존 **조문 전체 읽기 완료**의 의미를 보존해야 한다. source ID·문서 판본·범위 hash가 포함된 extent ID와 정확 evidence를 선택에 전달한다.

여러 extent가 같은 조문에 있어도 요청 범위를 합쳐 누락 없이 복원할 수 있을 때만 본문을 공유한다. 부분 READ를 조문 전체의 확인으로 승격하지 않는다. 기존 외부 출처는 같은 source ID를 유지하고 실제 인용 evidence/span이 읽은 범위를 설명한다.

## 6. 종료·복구·범위 정책

- 관계 일부가 미조회됐다는 이유만으로 모든 답변을 중단하지 않는다. 미조회·미읽기를 관계 부재의 증거로 사용하지 못하게 하고, 현재 요구에 중요한 미확인 부분을 구분한다.
- 중요한 연결에 대해 모델이 READ를 선택했으면 그 대상이 완료·전달되기 전 같은 요구를 충분으로 기록하지 못한다. 조회·읽기가 실패하면 성공으로 바꾸지 않는다.
- 불필요 판단은 요구와 원문/witness에 연결된 이유를 남긴다. 서버가 그 이유의 법률상 타당성을 자동 인증하지 않는다.
- 다음 페이지·추가 관계가 필요한 경우 기존 도구 cursor로 진행한다. 대상 재방문은 문서·판본·정확 범위와 요구별 상태로 제어한다. 다른 요구의 검토 상태까지 중복으로 제거하지 않는다.
- 전체 시각·모델·도구·입력 예산은 기존 요청 예산을 공유한다. 모델 오류 수정도 기존 수정 예산 안에서 같은 view의 오류를 반환한다.
- 예산 종료 시 확인된 근거로 답할 수 있는 부분을 제공하고 중요한 미확인 요구를 답변에 남긴다. 최종 검토 기본값을 다시 켜서 문제를 우회하지 않는다.
- 새 세대나 팀 범위 변경은 새로운 결속·요청으로 처리한다. 허용 범위 밖 대상은 제한 상태로 남기고 본문·위치를 모델에 노출하지 않는다.

## 7. 구현 순서와 완료 조건

| 순서 | 작업 | 종료 조건 |
|---|---|---|
| P0 | 판단 계약·요구 ID·전달 표현 합의 | 입력 정리 계획과 문서/관계/extent 번호·영수증의 책임이 일치 |
| P1 | 구조·fulltext 뒤 직접 관계 후보 제시, 읽기 전 판단 연결 | CM003 모의 계약에서 시행세칙 후보가 충분성 판단 전에 실제 전달됨. 불필요 결정도 가능한 경로 확인 |
| P2 | 선택한 대상의 정확 READ·coverage·근거 선택 연결 | 항·호·문자 범위가 READ부터 선별·작성까지 유지. 부분 읽기 탈락·조 전체 자동 확대 없음 |
| P3 | 요구별 충분성·관계 의존성·복구/종료 연결 | READ 필요 선언 뒤 미읽기 충분 판정을 거부하고, 완료 후 채택·제외·보류가 실제 작성에 반영됨 |
| P4 | 모델 비교와 도입 검증 | 같은 새 참조 세대·같은 모델·예산에서 필요한 연결 회수, 불필요 읽기, 최종 답변을 비교 |

P0~P3을 결속한 후보로 검증한다. P1만 활성화해 관계를 더 많이 쌓고 현행 작성 입력에 그대로 넘기면 컨텍스트가 증가할 수 있으므로, 입력 정리 계획의 관계·본문 표현과 함께 검증한다. 문서 추천·용어 의미 검토·PDF 구조화 정리 전체를 선행 조건으로 묶을 필요는 없다.

## 8. 검증 기준과 평가 경계

아래는 제안 수용 기준이며 통과 결과가 아니다. 기존 테스트의 성공을 새 기능 완료로 전용하지 않는다.

| 검사 | 확인할 행동 |
|---|---|
| CM003 재현 계약 | 제26조 원문 → 제23조④ 역참조 후보 전달 → 모델 READ 선택 → 정확 원문 전달 → 새 충분성 판단 순서 |
| 부적절한 조기 종료 | 필요한 대상으로 선언한 READ가 남아 있는데 충분 판정하면 같은 입력에서 오류 수정. 읽지 않아도 불필요라고 판단할 수 있는 계약도 별도 확인 |
| 단순 완결 질문 | 원문만으로 답할 수 있으면 관계가 존재해도 불필요 읽기 없이 종료할 수 있음 |
| 세칙·예외·위임·정의·산식 | 방향·역할·witness·범위가 선별 입력과 판단 결과에 남음. 특정 문항 전용 규칙 없음 |
| 모호·미해결·빈 관계 | 확인 못 함과 존재하지 않음을 구분. 필요 시 기존 검색, 결손이면 한계 표시 |
| 조 제10호/제39호나목 | 같은 조문 ID여도 불연속 범위 간 역참조가 전이되지 않음 |
| 복수 target·전단/후단/단서 | target별 범위와 선택을 보존. 인용 문자열을 조 전체로 치환하지 않음 |
| 원문 문맥 추가 | 필요한 상위 조건·다음 문장을 추가로 읽고 읽기 이유·새 범위를 기록 |
| 페이지·순환·중복·예산 | 미조회 cursor, 중복 READ 재사용, 순환 중단, 예산 종료의 미확인 상태 보존 |
| stale·위조·팀 제한 | 전달하지 않은 후보·범위·근거 및 과거 view 판단을 거부하고 요청 범위 밖 자료가 노출되지 않음 |
| 전송과 작성 | 실제 전송에서 같은 본문 반복 없음. 선택/필수 문맥 밖 원문 임의 추가 없음. 인용·요구·관계 대응 복원 |
| 단계 통합 | `test_structure_first_search`, `test_bounded_source_main`, `test_bounded_source_selection`, 관계·v5 계약을 변경 책임에 맞춰 확인 |

모델 비교는 아직 시작하지 않는다. 실행할 때 실험 표준을 끝까지 읽고 동일 scope reservation을 확인한 뒤 후보 구현·첫 호출 전에 새 ADR을 선점한다. 동일한 새 참조 세대에서 기존 판단 흐름과 후보 흐름을 비교해 데이터 재생성과 판단 수정 효과를 분리한다.

CM003은 이미 관찰한 진단 사례이며 독립 품질 인증으로 쓰지 않는다. 필요한 연결·불필요 연결·기권/결손·단순 질문을 포함한 문서/요구 단위 표본과 out-of-sample 사례를 결과 확인 전에 동결한다. 신규 외부 모델은 저장소 정책의 Gemma 공통 클라이언트를 기본으로 하고, 별도 모델 비교는 사용자 지시와 실험 결속에 따른다. 과거 Qwen 결과를 다른 모델 후보의 동일 조건 baseline이라고 부르지 않는다.

필요 연결 누락, 불필요 READ, 범위 초과, 최종 답변의 조건·예외·산식 정확성, 미확인 표현, 호출/토큰/시간을 각각 측정한다. 계약 오류와 답변 의미 오류를 구분하고, 수용할 회귀 범위는 실행 전에 동결한다.

## 9. 기대치·비용·도입

| ID | 종류·지표 | 근거·산식·확인 방법 |
|---|---|---|
| OBS-01 | 관측: CM003 READ 1회·관계 탐색 0회 | 기존 공개 실행 journal. 전체 요청의 평균이나 GENOS 수치가 아님 |
| OBS-02 | 관측: `needs_fulltext=false` | CM003 첫 선별의 실제 response. 후보 수정 후 결과는 미측정 |
| CFG-01 | 설정: 모델 예산 14회·max_cycles 3·context 100,000자 | 현재 v5 profile. 새 흐름의 실제 소비량·품질을 뜻하지 않음 |
| TARGET-01 | 목표: 필요한 연결의 확인 기록 후 충분성 결정 | 요구·관계·READ·전송·작성 receipt를 연속 검사 |
| CALC-01 | 계산: 호출 증감 | `새 판단/추가 확인/수정 호출 - 제거된 기존 판단/중복 탐색 호출`. 요구 구성은 이동하며 이중 호출하지 않음. 실측 전 증가량·절감률 미산정 |
| CALC-02 | 계산: 비용 증감 | 같은 모델 단가로 입력·출력 토큰 증감과 READ·전송 비용을 별도 계산. 호출 수만으로 비용을 추정하지 않음 |
| UNKNOWN-01 | 미확인: 정확도·평균/p95 지연·구현 인일 | 후보 계약 완료 후 같은 조건의 모델 평가·작업량으로 산정. GENOS 배포 대기는 별도 |

관계가 적고 원문만으로 충분한 질문은 판단 단계가 늘어 지연이 증가할 수 있다. 관계가 많은 조문은 자료량과 호출 예산이 먼저 소진될 수 있다. 중복 제거·요구별 선택·정확 범위 읽기로 줄인 비용이 추가 판단 비용을 넘는지 실측해야 한다. 개선률이나 일정은 현재 근거로 확정하지 않는다.

서빙 판단 코드 변경 자체는 원문 재파싱·PeCab 재색인을 요구하지 않는다. 새 정밀 관계 사용에는 별도로 검증·선택한 새 navigation 세대가 필요하다. 새 데이터 구축·로컬 MAIN 활성화·Git main 병합·GENOS 배포를 각각 확인한다.

실험 후 표준의 final/graph 검증과 MAIN 승격 조건을 충족한 코드·schema·profile·데이터 결속을 새 frozen 릴리스에 보존한다. GENOS 적용은 검증한 코드 리비전·데이터 세대·환경 설정·롤백 receipt를 인계하고 현장 워크플로우 테스트로 확인한다. 원복은 이전 릴리스/세대/프로필을 함께 선택하며 완료 기록을 덮어쓰지 않는다.

## 10. 근거와 문서 완료 범위

- [실제 CM003 선별 입력](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14/artifacts/run-001/cm-003/structure-main/calls/call-001-product-ecfdaf7a24b8/request.json), [모델 응답](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14/artifacts/run-001/cm-003/structure-main/calls/call-001-product-ecfdaf7a24b8/response.json).
- [최근 연결·입력 감사](/home/jin/8-AGENT/09_ARTIFACTS/AUDITS/20260929-main-relations-context-audit/REPORT.ko.md), [입력 표현 계획](../MODEL_DATA_PRESENTATION_REPAIR_PLAN_20260929/PLAN.ko.md).
- [선별 입력·충분성 분기](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/source_selection.py:226), [현재 선별 검증](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py:92).
- [구조 조기 반환](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/source_recall.py:263), [READ 후 예약](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py:477).
- [기존 관계 평가 검증](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/legal_agent/relations_session.py:45), [target별 계약](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/term_references.py:232), [문자 범위 helper](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/reference_spans.py).

계획과 호출/소비자 연결을 자체 검토했다. 독립 감독 검토·새 테스트·모델 비교·실제 구현·MAIN 전환·현장 배포는 수행하지 않았다. 문서와 검토 시점 파일 hash는 [EVIDENCE.json](EVIDENCE.json)에 보존한다.
