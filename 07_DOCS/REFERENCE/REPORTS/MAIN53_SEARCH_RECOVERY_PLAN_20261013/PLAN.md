# MAIN53 제목 검색과 본문 검색 복구 구현 계획

2026-10-13. **계획 작성 완료 · 구현과 개선 실험 미실행.** Claude Opus 5.5가 두 차례 작성했고, Codex가 실제 코드·저장 호출과 대조해 범위 결속·표시 필드·배선·판정 기준을 보정했다. 원응답과 보정 기록은 보존한다.

현재 기준은 로컬 `focused-rules-20261013-r1`, 활성 포인터 generation 53이다. 전체 MAIN 중 RAG의 요청 해석·검색·원문 조사 단계만 다룬다. 원문 입력·구조화·용어집·문서–용어 연결과 데이터 세대는 유지한다. 실행 경로는 `service.service → service.py → /v1/rag/ask → unified_runtime/UnifiedRag → request_entry → law_candidates/Investigation → gateway`다.

## 0. 현재 상태와 핵심 결정

**현재 상태**

- 설계 요청 범위는 이전 로컬 MAIN53 측정과 이 계획 작성까지이며, 둘 다 완료되었습니다.
- 코드 변경, 실험 실행, 승격은 하지 않았습니다. 이 문서는 승인이나 실행을 주장하지 않습니다.

**핵심 결정**

1. 변경을 두 묶음으로 나눕니다.
   - **A**: 모델 입력 표시, SEARCH_BODY 범위 배선, repair 피드백
   - **B**: 제목 recall
   - B는 다시 둘로 나눕니다. **B1**은 정규화만 하고, **B2**는 필요할 때만 별도 ADR로 진행합니다.
   - A는 B의 성패와 관계없이 독립적으로 평가합니다.
2. 다음은 하지 않습니다.
   - 새 도구명, 새 상태 엔진, 판정용 LLM 호출 추가
   - P02 정답, 조문번호, 문서명, 특정 법이나 질문에 맞춘 regex를 제품 코드에 넣는 것
   - 모든 질의에 Fulltext를 강제하는 것
3. 답변 완료 계약 V8과 옛 기록은 그대로 둡니다. 바뀌는 것은 view, prompt, profile revision입니다.
4. 새 문서 전체 본문 검색 target은 **요청 범위 결속이 검증된 경우에만** 제시합니다. 결속이 모호하거나 미결속이면 UNKNOWN을 보존하고 기존 동작을 유지합니다.
5. 실험은 A 단독과 고정 MAIN53의 비교부터 동결합니다. 네 arm을 한꺼번에 실행하지 않습니다.

## 1. 원인 정정 (MAIN53 P02 관측)

| 항목 | 관측 사실 |
|---|---|
| 대상 확인 | 문서는 `EXACT_TITLE`로 확인됐습니다. 조항은 `UNRESOLVED_HEADING`(MISS ×3)이었습니다. |
| 후보 | 카탈로그 후보 7개는 문서 행 1개와 조문 6개입니다. 모델은 미확정 조문을 대상 조항처럼 READ했습니다. |
| 문서 범위 복귀 단서 | RESEARCH(허용 전체 본문)와 구조 root_action은 **원래 있었지만 선택되지 않았습니다.** 부족했던 점은 두 가지입니다. ① 현재 focus와 각 action의 실제 동작 범위가 따로 선명하게 표시되지 않았습니다(SEARCH_BODY 라벨은 항상 "현재 구조 범위"였지만 실제 범위는 focus에 따라 바뀜, `law_navigation.py:1099-1102`). ② focus가 생긴 뒤 문서 전체로 가는 SEARCH_BODY 직행 target이 없었습니다. |
| 이력 표시 | 모델이 보는 이력(`previous_search_queries`, `search_expression_history`)에 mode와 scope가 없어서 Fulltext 0회라는 사실이 보이지 않았습니다. 같은 문장으로 모드를 바꾸는 것은 **이미 허용되도록 구현돼 있습니다**(`structure:` prefix, body 키에 identity 포함). |
| 종료 흐름 | FINISH가 `no adopted originals for completion`으로 거절됐습니다. 일반 repair 문구가 나왔고, 같은 FINISH가 다시 제출돼 repair 2차도 실패했습니다. 여기서 바로 422가 된 것이 **아닙니다.** 결정 호출 6회 뒤 `MODEL_DECISION_UNRESOLVED` bounded_stop → read fallback assess → gap reentry 순으로 진행됐고, 마지막 REQUEST_FACT 오판이 2회 거절된 뒤 HTTP 422로 끝났습니다. 총 10 calls입니다. |
| M4 제목 매칭 진단 | `heading_term_candidates`(`structure_query.py:317`)의 통과 조건은 "매칭 ≥2 그리고 매칭 ≥ 제목 토큰의 2/3"입니다. 대상 제목은 14토큰이고 query별 교집합은 4토큰이어서 탈락했습니다. |
| 함의 | RESEARCH가 있었는데도 선택되지 않았으므로, 표시를 고친다고 행동이 바뀐다는 보장은 없습니다. A의 효과는 **미확인**입니다. |

## 2. 문제별 결정

| # | 결정 | 하지 않을 것 |
|---|---|---|
| P1 | 기존 SEARCH_BODY action 형태를 그대로 쓰고, target을 `REQUEST_SCOPE`와 `FOCUS` 두 종류로 구분합니다. 각 scope마다 1개씩만 둡니다. | "문서 대상 항상 제시", 후보 행마다 action을 복제하는 것 |
| P2 | 기존 기록을 합쳐 파생 view `search_attempts[]`와 `search_status`를 만듭니다. | 새 durable log, 누락 이력을 0으로 거짓 채우기 |
| P3 | `repair_contract`에 `NO_ADOPTED_ORIGINAL` conflict를 추가합니다(제안). | 스키마·검증 완화, 아무 원문이나 채택하라는 유도 |
| P4 | 문서 확인과 조항 해석 상태를 분리해서 표시합니다. | 미확정 후보를 대상 조항으로 표시하는 것 |
| P5 | B1(정규화)을 먼저 하고, 진단 결과를 보고한 뒤 필요하면 B2 ADR로 갑니다. | 전역 PeCab 변경, 임계값 무조건 완화, 전수 본문 제시 |
| P6 | 프롬프트에서 읽은 조문의 내용과 문서 전체 부재를 구분하게 합니다. | 코드가 검색 통계로 관련성이나 부재를 판정하는 것 |
| P7 | `bounded_result.adoption_fallback`의 위험을 기록만 합니다. | 이번 범위 안에서 변경하거나 삭제하는 것 |

## 3. 묶음 A 설계

### 3.1 요청 범위 결속 선행 조건

현재 entry/intent의 `request_quote`는 원 요청 인용을 보존하지만, 자연어 항·호 제한을 강제 범위 필드로 저장하지는 않는다. 제안 helper `law_navigation.request_scope_view`에서 선택·검증된 문서 제목/약칭 hint, request_quote, 기존 `structure_query.document_hits`와 저장 좌표 해석을 재사용한다. 별도 LLM 호출은 추가하지 않는다.

제안 모델 뷰는 `request_scope{status, document_id, unit_id, quote_span, reason}`다. 서버는 원 요청의 인용 span, 문서 이름/약칭 일치, 필요한 좌표의 실재, ACL을 대조한다. 첫 구현은 유일하게 명명된 문서와 모호하지 않은 단일 하위 범위를 다룬다. 문서·좌표의 부정/제외·비교 용법을 확실하게 결속하지 못하면 UNKNOWN으로 남긴다.

- 문서만 명시되고 결속 검증 통과: `BOUND`, `unit_id=null`. 문서 전체 본문 검색을 요청 범위 선택지로 유지한다.
- 명시적 하위 범위가 결속됨: `BOUND`, 해당 unit. 새 문서 전체 target은 숨기고 그 하위 범위만 제공한다.
- 요청 범위 자체가 모호하거나 인용·문서·필요 좌표 검증 실패: `UNKNOWN`. 새 문서 전체 shortcut을 만들지 않고 기존 제한된 탐색/필요시 범위 확인을 유지한다. 애매한 요청마다 새 모델 호출이나 사용자 질문을 강제하지 않는다.

**원하는 조항 제목이 미발견인 것과 요청 문서 범위가 미확정인 것은 별개다.** P02는 코스닥시장 공시규정 안에서 내용을 찾는 요청으로 문서명이 유일하고 조문번호 제한이 없다. `request_scope=문서 전체 BOUND`와 `heading_resolution=UNRESOLVED_HEADING`을 동시에 표현하고, 무관한 조항을 읽은 뒤에도 문서 전체 SEARCH_BODY를 유지하는 것이 목표다. 제목 조회 실패 때문에 문서 범위까지 UNKNOWN으로 바꾸지 않는다.

bound는 실제 선택할 수 있는 저장 위치를 결속한다. 인용·좌표 실재 검사가 자연어의 부정, 예시, 비교, 대명사, 판본 의도를 의미적으로 증명하지는 않는다. 이 정확도는 별도 의미 평가 대상이다.

우선 기존에 저장된 entry/intent와 구조 데이터에서 결정적으로 파생하고, 파생 규칙 revision을 profile 및 요청 재개 hash에 결속한다. 재개에 필요한 원 입력이 충분하지 않아 신규 저장이 불가피하면 독립 검색 상태 version과 이행·롤백을 설계한 별도 ADR로 다룬다. 구기록을 추측으로 채우지 않는다.

### 3.2 target 구성 (`law_navigation.py:1099-1102`)

- **offer 형태**: 서버의 기존 `{id, action: SEARCH_BODY, identity: {document_id, unit_id}, label}`를 재사용합니다. 모델은 현재 메뉴의 `id`를 `targets`로 선택하며 identity를 새로 작성하지 않습니다.
- **target 종류**
  - `REQUEST_SCOPE`: bound가 BOUND일 때만 제시합니다.
  - `FOCUS`: 현재 READ focus입니다. 기존 target이며, REQUEST_SCOPE와 identity가 같으면 하나로 합칩니다.
- **라벨**: identity로부터 생성합니다.
  - `unit_id=null`이면 "문서 전체 본문 표현 검색"
  - 그 외에는 "{좌표} 이하 본문 표현 검색"
  - OPEN_LAW 라벨도 같은 기준으로 맞춥니다.
- **위조 방어**: 현재 validator(`law_navigation.py:1268-1274`)는 제시된 targets enum과 identity 일치를 **이미 검사합니다.** 새 검사를 만드는 것이 아니라, 새 target과 재개 상황에서 그 검사가 유지되는지를 테스트로 고정합니다.
  - 제시 메뉴 밖의 target은 거부됩니다.
  - 현재 메뉴에 없는 과거 target 또는 다른 state/view의 결정을 거부합니다. 과거와 identity가 같고 현재에도 합법적으로 offer된 target까지 무조건 차단하지는 않습니다.
  - 동일 `digest([identity, key])` 반복 차단과 라운드 한도는 그대로 둡니다.
- **기존 경로 점검**: 검증된 명시 제한이 있을 때 RESEARCH와 READ가 새 범위 경계를 우회하지 않도록 offer와 validate의 필요한 지점에 같은 검사를 연결합니다. 기존 enum/identity/ACL 검사는 유지합니다. 범위 우회가 발견되면 A의 도입 조건 실패로 처리하고 원인을 고칩니다. 새 target만 숨기고 다른 경로의 우회를 방치하지 않습니다. 자연어 의도 자체의 정확도는 별도 의미 검토 대상입니다.

### 3.3 상태 표시 (제안 필드, 모델 사본 전용)

**파생 원천**

- 기존 journal, action-chain, 수락된 action identity의 실제 도구 호출·결과를 합쳐 만듭니다. 전체 과거 본문이나 모든 model view를 매 호출에 다시 읽지 않고 필요한 검색 영수증을 간결하게 투영합니다.
- `body_search_history`는 digest만 저장하므로, scope는 chain의 identity와 대조해 복원합니다.
- 복원할 수 없으면 UNKNOWN으로 둡니다.

**필드**

- `search_status`
  - `document_match`: entry에서 선택한 검증된 문서 제목/약칭 hint와 문서 이름 일치에서 파생
  - `heading_resolution`: 개별 `resolutions[].status/failure`에서 파생. 목록의 `lookup_status=NEEDS_SELECTION`이나 `failure=null`을 조항 발견으로 바꾸지 않습니다.
  - `body_search_status`: 항목 목록 `[{mode, scope, status}]`
- `search_attempts[]`: `{ref, mode(STRUCTURE|BODY|RESEARCH), scope(identity), query_refs, result{status, shown, has_more}}`
  - READ는 검색 모드에 넣지 않습니다. 읽기 이력은 기존 `investigation_chain`으로 표시합니다.
- `actions[].scope`: 표시용입니다. validator는 이 필드를 신뢰하지 않고 기존 identity와 대조합니다.

**상태값 규칙**

- `NOT_ATTEMPTED`는 범위, 모드, 질의 표현(또는 짧은 ref)이 구분되고 파생 chain이 완전할 때만 씁니다.
- 그 외에는 `UNKNOWN`입니다.
- 과거 기록을 Fulltext 0회로 채우지 않습니다.
- 별도의 `not_yet_attempted` 필드는 두지 않습니다. 같은 의미를 `body_search_status`에 담아 필드명을 하나로 맞춥니다.

**중복 처리**

- 모델 사본에서는 기존 중복 history(`previous_search_queries`, `search_expression_history`, `structure_search_history`, `body_search_history`)를 `search_attempts`로 대체합니다.
- 서버 원본 필드는 그대로 둡니다.
- output에 쓰이는 원문 메타는 늘리지 않습니다.

**최종 소비 경로**

- `ModelGateway.request`가 `NavigationReferences`로 view와 schema의 handle을 변환하고 `gateway.compact_wire_view`를 호출합니다. 이 함수 안에서 `navigation_input.compact_cards`가 표 압축을 수행합니다.
- 실제 provider 요청 본문에서 mode, scope, action 라벨이 남아 있는지와, handle이 올바른 identity로 복원되는지를 검증합니다.

**모델 입력 예** (형태 예시입니다. 값은 파생 결과가 들어갑니다)

```json
{
  "search_status": {
    "document_match": "EXACT_TITLE",
    "heading_resolution": "UNRESOLVED_HEADING",
    "body_search_status": [
      {"mode": "BODY", "scope_ref": "request", "query_refs": ["q1"], "status": "NOT_ATTEMPTED"}
    ]
  },
  "search_attempts": [
    {"ref": "s1", "mode": "STRUCTURE", "scope_ref": "request", "query_refs": ["q1"],
     "result": {"status": "NEEDS_SELECTION", "shown": 3, "has_more": false}}
  ],
  "actions": [
    {"id": "T1", "action": "SEARCH_BODY", "scope": "REQUEST_SCOPE", "label": "모의규정 문서 전체 본문 표현 검색"},
    {"id": "T2", "action": "SEARCH_BODY", "scope": "FOCUS", "label": "모의규정 제N조 이하 본문 표현 검색"}
  ]
}
```

`q1`은 이 화면의 실제 검색어 항목을 가리키며 참조 대상도 제공합니다. `request`의 실제 문서/하위 범위는 검증된 request_scope의 한 사본으로 제공합니다. 실행은 제공된 T1/T2 handle을 선택하며 서버 identity와 대조합니다. 이 예의 이름과 후보 수는 합성 예시입니다.

### 3.4 프롬프트 (`COMPACT_SYSTEM` 92-103행, `request_entry.py:24-27`)

**COMPACT_SYSTEM 97행 교체**

> 법령명·조문번호·제목 부근을 알면 SEARCH_STRUCTURE, 세부 문구로 찾으면 RESEARCH 또는 SEARCH_BODY를 고른다. SEARCH_BODY의 scope는 REQUEST_SCOPE(요청 범위) 또는 FOCUS(현재 읽은 위치 이하)이며 라벨과 같다. 구조 검색을 먼저 거칠 의무는 없다. (structure_filter 이하 기존 문장 유지)

**COMPACT_SYSTEM 추가 문장**

> 문서 제목 일치는 문서 확인이다. heading_resolution이 UNRESOLVED_HEADING 등 미확정 상태이면 목록의 조문은 위치 단서이며 요청 조항으로 확정된 것이 아니다. 읽은 조문이 요구와 다르면 search_status에서 시도하지 않은 범위나 모드를 고른다. 검색 결과 목록은 그 검색에서 보인 후보일 뿐 문서 전체의 부재 증명이 아니다. 읽은 조문에 내용이 없다는 것은 그 조문에 대한 사실이다.

**읽기 우선 문장 교체**

> 질문의 주체·행위·요구와 관련된 후보에 read_action이 있으면 바로 읽는다. read_action이 있다는 사실만으로 관련성이 확인된 것은 아니다. 읽은 후보가 무관하면 그 조문 안에 머물지 말고 제공된 요청 범위 검색으로 돌아간다. 같은 문구라도 제목 검색과 본문 검색, 서로 다른 허용 범위의 검색은 구분한다. 요청한 내용을 찾기 위한 같은 문서의 본문 검색은 별도 주변 주제로의 확장이 아니다.

**진입 프롬프트 추가 문장**

> 제목 일치는 문서 확인이며 조항 위치 확인이 아니다.

진입 프롬프트가 바뀌므로 `POLICY='fused-title-v1'` 갱신 여부도 이번 변경의 책임에 포함합니다(6절).

### 3.5 repair conflict (`law_navigation.py:284`)

**문구**

> 채택된 원문이 없어 종료할 수 없다. (1) 받은 원문 중 요구를 실제로 답하는 span만 ADOPT한다. (2) 시도하지 않은 검색이나 읽기를 고른다. (3) 더 조사할 수 없으면 PENDING으로 미확인을 보존한다.

**검사로 보장되는 것과 안 되는 것**

- 권한, 인용, provenance 검사는 **의미 관련성까지 보장하지 않습니다.** 무관한 ADOPT가 형식 검사를 통과할 수 있습니다.
- 합성 테스트는 형식만 검사합니다: valid targets, span 실재, 원문 일치, 범위.
- 실제 의미 오판은 별도 evaluator가 판정합니다.

**P02 회귀 목표**

- 통과: 적합한 원문을 확보해서 요구를 설명합니다.
- 안전 동작 부분 통과·품질 실패: 적합한 원문을 확보하지 못하고 미확인을 보존합니다.
- PENDING만 나온 것은 품질 통과가 아닙니다.
- 기존 bounded_stop·부분 답변·ASSESS 재조사 소비자는 보존합니다. 해당 경로 진입과 무관 근거 채택/부족 오분류를 관측합니다. 불필요한 채택이 늘면 실패로 기록하고, REQUEST_FACT 오분류가 남으면 해결됐다고 보고하지 않습니다.

## 4. 묶음 B (`structure_query.py:299-319`)

**전제 (정정)**

- lookup에는 **전체 후보 수 상한이 없고 `page_size`만 있습니다.** "기존 후보 총수 상한 보존"이라고 쓰지 않습니다.
- 대신 다음을 회귀 측정합니다.
  - paging 동작
  - 첫 페이지에 무엇이 보이는지
  - 짧은 일반 제목의 후보가 늘어나는지
  - 조건 없이 전수 본문을 제시하는 경로가 생기지 않았는지

**진행 순서**

1. **일치 진단**: 주석·숫자 형태별로 제목 토큰과 query 토큰의 교집합을 합성 fixture로 진단합니다.
   - 계산상 주석 제거만 하면 4/남은 8 = 50%가 될 수 있습니다. 이 경우 2/3를 넘지 못합니다.
2. **B1**: 매칭할 때만 제목을 정규화합니다.
   - 판본, 원문, 저장 title, `term_cache` 키는 바꾸지 않습니다.
   - 부모는 MAIN53입니다.
3. **결과 보고**: B1 결과를 보고한 뒤, 필요하면 **B2를 별도 ADR**로 엽니다.
   - 후보: 상대적 어휘 보존 토큰 매칭, 또는 제목 전용 검색 정책
   - B2는 이 계획에서 설계하지 않습니다.

**금지**

- 전역 PeCab 변경
- 임계값 무조건 완화
- 특정 법에 맞춘 regex

**재구축**

- B1은 질의 시점의 매칭만 바꿉니다.
- 원문, data generation, FTS rebuild 모두 불필요합니다.
- `index_sha256`이 바뀌지 않는지 검증합니다.

## 5. 변경 지도

| 위치 | 변경 |
|---|---|
| `law_navigation.py:1099-1102` | REQUEST_SCOPE/FOCUS target 구성, identity 기반 라벨 |
| 같은 파일 906-911 | 모델 사본에 `search_status`, `search_attempts` 파생, 중복 history 대체 |
| 같은 파일 92-103, 284 | 프롬프트, `NO_ADOPTED_ORIGINAL` conflict |
| 같은 파일 validate와 offer 구성 | 기존 enum/identity/반복 검사를 유지하고 검증된 요청 범위에 필요한 검사만 연결 |
| `request_entry.py:24-27` | 문장 1개 추가 |
| `law_navigation.request_scope_view` 제안 helper | 기존 entry/intent와 structure_query를 사용한 3.1절 범위 파생 |
| `navigation_input.py`, `gateway.compact_wire_view` | 압축 후 표시 보존을 확인하고, 필요한 경우에만 수정 |
| `law_candidates.py:276 fulltext_scope_keys` | 변경 없음. `unit_id=None`이 문서 전체로 해석되는 계약을 테스트로 고정 |
| `request_decision`, `decision_retry`, `repo.event(LAW_DECISION_*)` | 변경 없음 |
| `structure_query.py` | B1만 |

## 6. 테스트

**유지·확장할 기존 테스트**

- `test_structure_reading.py`
- `test_structure_first_search.py`
- `test_focused_input_modality.py`
- `test_main50_request_repair.py`
- `test_navigation_input_compaction.py`
- `test_wire_repair.py`

**신규 테스트와 그 의미** (합성 fixture만 사용, P02 문자열 금지)

| 테스트 | 의미 |
|---|---|
| bound 결정 | 인용 span, 문서, 좌표, ACL 중 하나라도 실패하면 UNKNOWN이 되고 새 target이 없습니다. 명시 subtree면 문서 전체 target이 숨겨집니다. 문서만 명시되면 REQUEST_SCOPE 1개가 나옵니다. |
| target 개수 | scope마다 1개입니다. focus와 REQUEST_SCOPE의 identity가 같으면 1개로 합쳐집니다. 후보 행마다 복제되지 않습니다. |
| 위조·재사용 | 메뉴 밖 identity와 현재 state/view에 결속되지 않은 결정을 거부합니다. 현재에도 제공된 동일 identity의 정당한 선택은 허용합니다. |
| 반복 규칙 | 같은 identity와 같은 key는 거부되고, scope만 바뀌면 허용됩니다. 같은 문장의 모드 전환 허용은 그대로입니다. |
| 기존 경로 경계 | 검증된 하위 제한을 RESEARCH·READ가 우회하지 않는지 검사합니다. 우회가 있으면 A 도입 조건 실패입니다. |
| 파생 view | `search_attempts`가 chain과 일치하고, 누락은 UNKNOWN입니다. 저장 state diff는 0입니다. READ는 mode로 들어가지 않습니다. |
| 최종 wire | 압축 후 provider 요청에 mode, scope, 라벨이 남아 있고, handle 왕복으로 identity가 정확히 복원됩니다. 정상 경로 입력 크기를 MAIN53과 비교해 기록합니다. |
| repair | conflict가 추가돼도 스키마 변화는 0입니다. 형식 검사(target, span, 원문, 범위)는 유지됩니다. 의미 판정 테스트는 두지 않습니다. |
| B1 | 저장 title이 불변입니다. 주석 형태별 진단표를 출력합니다. 짧은 일반 제목 후보와 paging 노출 변화를 측정합니다. `index_sha256`이 불변입니다. |
| pin | 제품 모델은 qwen/qwen3.8-27b, Parasail FP8, reasoning none, no fallback을 유지합니다. 변경 파일을 소비하는 engine manifest·PIPELINE 코드 pin과 profile/프롬프트 revision을 실제 의존성에 맞춰 갱신합니다. 모든 schema를 무조건 올리지는 않습니다. |

## 7. 버전·배포·롤백

**버전**

- 로그나 view 필드를 추가한다고 해서 답변 completion이 V9가 되는 것은 아닙니다.
- 답변 계약은 V8을 유지하고, 옛 기록도 그대로 둡니다.
- 새로 붙는 것: navigation view revision, prompt revision, profile revision, scope 파생 규칙 revision
- 독립 검색 상태 version은 저장 상태가 새로 생길 때만 둡니다(3.1절 6항).

**generation**

- 원문, data generation, FTS rebuild는 불필요합니다.
- 승격할 때만 새 코드 release와 pointer generation이 생깁니다.

**진행 중 요청**

- profile 고정이나 drain을 현재 자동 기능으로 가정하지 않습니다.
- 구 세션을 새 코드로 해석하는 것은 금지합니다. data digest가 바뀌므로 `decision retry presentation changed` 위험이 있습니다.
- 배포 전에 진행 중 요청을 drain할 수 있는지, 기존 실행을 기존 코드로 마칠 수 있는지 확인합니다.
- 둘 다 불가능하면 새 요청으로 다시 시작합니다. 원래 기록은 보존하고, 이 제약을 보고합니다.

**롤백**

- 새 revision으로 생성된 상태를 구버전이 읽거나 재개하면 안 됩니다.
- 재개 hash가 다르면 거절하고, 위와 같은 규칙으로 처리합니다.
- 롤백 receipt를 보존합니다.

## 8. 실험 계획 (실행 금지, 설계만)

**절차**

- AGENTS 실험 표준을 따릅니다: 끝까지 읽기 → 동일 scope reservation 확인 → ADR 예약 → 부모 완료 arm 확인 → snapshot/register/freeze → 시작.

**arm 순서**

1. A 단독 대 고정 MAIN53을 먼저 동결하고 실행합니다.
2. B1은 별도 arm으로, 부모를 MAIN53으로 둡니다.
3. B2는 B1 결과를 보고한 뒤, 필요할 때만 새 ADR로 진행합니다.
4. A+B 통합은 완료된 arm들의 정확한 `merged_from`을 명시한 별도 ADR로 진행합니다.

**문항**

- 기존 P02는 in-sample 회귀 검사입니다.
- 독립된 새 공개 문항 3개를 제안합니다. 알려진 문항을 의역한 3개가 아닙니다.
  - 다른 문서의 긴 주석 제목 회수 유형
  - 명시 하위 범위 제한 요청의 범위 가드 유형
  - 문서 수준 요청에서 무관한 조문을 READ한 뒤 복귀하는 유형
- 데이터와 판정 기준은 호출 전에 동결합니다.
- 문항 수가 적으므로 승격 효과를 일반화하는 데 한계가 있다고 명시합니다.

**평가 조건**

- 제품 모델은 공개 Qwen으로 고정합니다.
- 의미 evaluator는 freeze 전에 식별자를 동결합니다.
- 판정 축은 형식, 도구, 근거, 의미, 효율로 분리합니다.
- 통과 기준과 허용 회귀는 freeze 전에 확정합니다. 후보 기준은 "P02 위 3.5절 판정"과 "P01 정상 경로 호출 수 비증가"입니다.
- 실행이 요청되면 기준 로그와 기존 한도에 근거해 시간·비용 기준을 호출 전에 동결합니다. 새 예산이나 별도 승인이 필요한 경우에만 확인합니다. 현재 계획에서 근거 없는 절감률·시간 상한을 만들지는 않습니다.
- upstream 429는 정상 완료 효율 비교쌍에서 제외하되 전체 실패율·호출·보고 사용량·시간 집계에 보존합니다. 사용량 미보고를 0으로 채우거나 임의 재호출하지 않습니다. 정상 완료 쌍과 실패 포함 전체 비용을 나란히 보고합니다.
- 기존 15개 실패와 그래프 8개 오류는 역사 기준선으로 따로 두고, 신규 발생 0을 별도로 판정합니다. 세부 의미 오류를 기록하되 모든 세부 답변 100% 정답을 MAIN 반영의 자동 조건으로 만들지 않습니다. 인용·권한·검증된 범위·상태 보존·코드/데이터 해시·실제 서빙 연결의 심각한 문제는 계속 차단 기준입니다.

## 9. 승격 순서 (계획만)

1. 동일 코드로 통합 검증
2. 적격 arm 확인 (Accepted / out-of-sample / complete / decision_eligible)
3. hash 고정 promotion plan 작성
4. 명시적 `confirm-main` apply
5. apply receipt 기록
6. 선택된 pointer와 새 실제 service binding에서 HEALTH/RAG 확인
7. rollback receipt 보존

Git main 반영과 GENOS 현장 반영은 별도 상태로 관리합니다. 이 세션에서 GENOS에 접속하지 않습니다. 후속 인계는 GENOS.md에 따라 검증 코드·의존성·설정·입출력·재개·롤백을 포함하고, 현장 python3 및 워크플로우 테스트 화면에서 별도 확인합니다.

## 10. 수치 원장과 비용식

| 항목 | 실측 (1회 목적 표집) | 미확인 |
|---|---|---|
| M1 P02 MAIN53 | HTTP 422, 10 calls, 219.352초, input 228,678 tokens, output 7,944 tokens, Fulltext 0회 | 수정 효과 |
| M2 P01 MAIN53 | 4 calls, input 22,935 tokens, 105.474초 | 지연 변화 |
| M3 P03 MAIN53 | 응답 성공, 주체 조건 의미 오류 (범위 밖) | — |
| M4 제목 매칭 진단 | 14토큰 중 교집합 4. 주석만 제거하면 4/8 = 50%일 수 있음 | B1 효과 |

이 수치로 일반 품질이나 속도를 예측하지 않습니다.

**손익분기식 (토큰과 초를 더하지 않음)**

- 비용
  - ΔC = ΔIn·p_in + ΔOut·p_out
  - 단가 p_in, p_out은 같은 통화(원 또는 달러)로 계산합니다.
  - Lc = 실패 루프(거절·repair·재진입)의 비용으로, 같은 통화로 계산합니다.
  - 이득 조건: p_add·ΔC < p_fix·Lc
- 지연은 별도로 비교합니다: p_add·ΔT 대 p_fix·Lt
- 변수
  - p_add: 정상 경로에서 추가 검색이 쓰이는 비율
  - p_fix: 실패 루프가 끊기는 비율
- 모든 값은 실험으로만 채웁니다. 예측 비율이나 소요 일수는 만들지 않으며 **미확인**으로 둡니다.

## 11. 남은 위험과 미확인

- A의 표시 변경이 모델의 선택을 바꾸는지는 미확인입니다. RESEARCH가 있었는데도 선택되지 않은 선례가 있습니다.
- 원하는 제목 미발견을 문서 요청 범위 미확정으로 잘못 전파하면 복구 경로가 다시 사라집니다. P02형 회귀에서 두 상태의 독립성을 검사합니다.
- B1만으로 2/3 임계를 넘지 못할 수 있습니다.
- 진행 중 요청의 drain이나 기존 코드 유지 가능 여부는 배포 전에 확인해야 합니다.
- `adoption_fallback`이 무관한 원문을 넘길 위험은 기록만 하고 이번에 바꾸지 않습니다.


## 12 근거와 완료 산출물

- [기준 측정](../../../../04_EXPERIMENTS/ADR/ADR-0762-main53-three-public-cases/MEASUREMENT_RESULT.md): M1~M3는 로컬 공개 목적 표집 각 1회 결과이며 GENOS 성능이 아니다.
- [실제 입력과 선택 발췌](../../../../09_ARTIFACTS/AUDITS/20261013-main53-search-recovery-plan/observations.json): archive member와 요청/응답 해시, 실제 프롬프트·메뉴·반환 이유.
- [코드 결속 확인](../../../../09_ARTIFACTS/AUDITS/20261013-main53-search-recovery-plan/code-binding-check.json): 관련 5파일의 작업 코드·측정 snapshot·선택 MAIN53 코드 일치. 전체 릴리스 재인증이나 새 서비스 실행은 아니다.
- [자체 대조와 보정](../../../../09_ARTIFACTS/AUDITS/20261013-main53-search-recovery-plan/codex-review.json): M4는 동일 코드의 읽기 전용 토큰 대조다. PeCab 경고도 기록하며 정규화 개선 효과로 오인하지 않는다.
- [계획 모델 영수증](../../../../09_ARTIFACTS/AUDITS/20261013-main53-search-recovery-plan/model-receipt.json): Opus 5.5 실제 사용 모델과 요청·원응답·최종 계획 해시.

현재 산출물은 구현 계획과 근거·모델 영수증이다. 구현 시에는 A의 생산자→실제 wire→검증→재개 계약, B1 후보 변화, 독립 공개 평가, 동일 코드 통합, 활성 pointer/실제 서비스 binding, rollback receipt 순으로 완료 증거를 남긴다. 기존 완료 ADR0762와 원문 archive는 덮어쓰지 않는다.
