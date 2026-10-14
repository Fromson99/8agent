# MAIN50 본헤드성 agent 루프: 독립 검토와 다음 설계

**검토 범위.** `review-package` 안의 `candidate/`, `main50/`, `METRICS.json`, `synthetic-tests/`만 읽었습니다. 코드를 실행하거나 고치지 않았고, 모델도 호출하지 않았습니다.

**확인하지 못한 것:**
- 실제 journal (패키지에 없음)
- `lc.token`, `ur.read`, `sq.resolve` 내부
- `unified_runtime.py` 변경의 세부
- ADR0721의 ConnectError가 서비스 transport에서 났는지, 실험 클라이언트에서 났는지

**표기.** **[확인]**은 코드나 수치로 확인한 것, **[추정]**은 근거가 있는 추정, **[제안]**은 설계입니다.

**파일 약어** (모두 `candidate/02_BACKEND/semantic_runtime/legal_agent/` 아래):
- `LN` = `law_navigation.py`
- `RR` = `request_repair.py`
- `CE` = `completion_execution.py`
- `V5` = `completion_v5.py`
- `CM` = `corrected_memory.py`
- `TR` = `transport.py`
- `GW` = `gateway.py`

---

## 1. 결론: 목표를 얼마나 해결했나

**결론부터:** 후보는 두 가지는 실제로 막았습니다. "같은 판단의 수정 호출과 재개 무결성", 그리고 "정확한 좌표 대상의 해결·부재 증명"입니다. 하지만 루프의 몸통은 그대로입니다.

- (a) 같은 행동인지 판정할 때 여전히 표시 문자열과 질의 fingerprint를 씁니다.
- (b) "진전"을 요구와 상관없는 새로움으로 정의합니다.
- (c) ASSESS에서 SELECT로 돌아갈지를 "다시 조사하면 바뀔 수 있는가"가 아니라 "새 gap 키인가"로 정합니다.

그리고 ADR0719와 ADR0721 검증은 루프가 도는 경로를 거의 지나지 않았습니다. 그래서 루프가 줄었는지 판단할 근거가 되지 못합니다.

**METRICS 근거 [확인]**
- 0719와 0721에서 후보를 돌린 9회 모두 `logical_navigation_steps ≤ 2`, `rejected_proposals = 0`입니다.
- 0721은 호출 12→12, 사례별 4→4로 같습니다.
- 0719의 호출 감소(16→12)는 H01 한 사례(8→4)에서만 나왔습니다.
- 입력 토큰 감소는 ASSESS에서 원문 중복을 뺀 효과(`V5.project_assessment`)와 패턴이 맞습니다 [추정].
- 출력 +22%, 시간 +18%는 v5의 더 큰 답변 구조 때문일 수 있습니다 [추정: 단계별 분해가 없어 단정할 수 없음].

### 1.1 이미 막은 코드 결함 [확인]

| 결함 | 막은 위치 | 한계 |
|---|---|---|
| 지난 `decision_retry`가 남아 500 발생 | `RR.new_epoch` (`request_repair.py:23-35`) | — |
| 수정 결정 중 통신이 끊긴 뒤 재개할 때 해시 불일치 | `LN.run`에서 저장해 둔 입력·메뉴로 복원 (`law_navigation.py:1917-1927`) | — |
| 같은 결정에 세 번째 호출 | `request_decision` (`law_navigation.py:1789-1798`) | — |
| 다른 조문을 읽은 receipt로 NOT_AVAILABLE 승인, 다른 조문으로 RESOLVED 승인 | `RR.validate_resolutions` (`request_repair.py:241-265`) | EXACT 대상에만 적용 |
| 문구나 optional material_id가 달라 같은 부족이 새 gap이 됨 | `RR.bind_gap` (`request_repair.py:105-111`) | EXACT·ABSENT에만 적용 |
| 재조사 때 no_progress 초기화 | `law_navigation.py:371-374` | 대신 아래 원인 1의 새 조기 종료가 생김 |
| 이미 본 원문 재독 | `RR.annotate_reused_reads` | **지금 화면에 보이는 것**에만 적용 |

### 1.2 여전히 코드가 허용하는 무의미한 행동: 원인 5개

**원인 1. "진전"이 요구와 무관한 새로움이다** [확인]
- `RR.progress_facts`(`request_repair.py:178-202`)는 법령(`law:`), 후보(`candidate:`), 구조 위치(`location:`)를 진전으로 셉니다.
- 전역 RESEARCH, OPEN_LAW, NEXT_LAWS, SEARCH_STRUCTURE는 거의 항상 새 후보를 냅니다. 그때마다 `no_progress`가 0으로 돌아갑니다(`law_navigation.py:967-970`).
- 그래서 **탐색 루프는 카운터에 걸리지 않고**, 재독이나 RETURN_TO처럼 아무것도 새로 안 나오는 행동만 걸립니다.

여기에 **새 버그**가 하나 있습니다.
- RESEARCH 결과는 재진입 뒤 `__init__`의 `awaiting_search` 분기(`law_navigation.py:399-408`)에서 들어옵니다. 그런데 거기서는 `record_progress`를 부르지 않습니다.
- 그래서 RESEARCH 단계는 무진행(+1)으로 기록되고, 그 결과는 **다음 행동의 진전으로** 잘못 붙습니다.
- 직전 단계가 이미 무진행이었다면 RESEARCH 뒤 `no_progress = 2`가 됩니다. 그러면 재진입 직후 `run()`(`law_navigation.py:1901-1902`)이 `NO_PROGRESS`로 끝납니다. RECALL/READ 비용은 이미 썼는데 그 검색 결과는 보지도 못합니다.

**원인 2. 반복 판정이 "효과"가 아니라 "표시"에 묶여 있다** [확인]

`seen_actions`와 `read_choices`의 서명은 `digest({action(라벨 포함), catalogue query_fingerprint})`입니다(`law_navigation.py:987-992`, `:1282-1290`, `:1614-1616`). 그래서 다음 일이 생깁니다.
- RESEARCH를 한 번 하면 fingerprint가 바뀌어, 같은 OPEN_LAW나 READ가 "새 행동"이 됩니다.
- `RR.add_target_actions`는 `offer()`를 거치지 않고 같은 대상을 다른 라벨('부족 원문 읽기')로 메뉴에 넣습니다(`request_repair.py:283-285`).
  - 예전에 다른 라벨로 읽었으면 재독이 그대로 통과합니다.
  - 같은 라벨로 읽었으면 메뉴에는 있는데 validate가 거절해서 **수정 호출**이 납니다.
- RETURN_TO 문맥에서는 두 검사를 모두 건너뜁니다(`law_navigation.py:1283`, `:1286`).
- SEARCH_STRUCTURE, OPEN·BROWSE_STRUCTURE, SEARCH_BODY, FOLLOW_CONNECTION은 아예 검사 제외 목록에 있습니다(`:990-991`). SEARCH_STRUCTURE는 질의 문자열이 완전히 같을 때만 중복으로 봅니다(`:1222-1226`).
- `annotate_reused_reads`는 `data['sources']`(지금 화면)만 보고 `basis_history`(과거 전달분)는 보지 않습니다(`request_repair.py:297-298`).
  - 예전에 받은 조문을 READ_ARTICLES로 다시 고르면 `ur.read`가 돌고 `page_plan`이 다시 만들어지고 `delivery = 0`이 됩니다(`law_navigation.py:1476-1487`). 같은 원문이 모델에 다시 들어갑니다.
- **코드는 전달된 span(`basis_history`, `navigation_recovery.delivered_spans`)을 이미 갖고 있지만, 행동이 같은지 판정하는 데는 쓰지 않습니다.**

**원인 3. 재진입을 "새 gap 키인가"로만 정한다** [확인]
- `V5.prepare`는 UNRESOLVED_REFERENCE를 뺀 모든 gap을 `material = True`로 강제합니다(`completion_v5.py:132-133`). 이것이 그대로 `actionable`(`completion_execution.py:228`)로 들어갑니다.
  - 결과: 모델이 비핵심이라고 한 부족도 재진입을 일으킵니다.
  - 보수적 coverage 표시와 재진입 트리거가 플래그 하나에 묶여 있는 것이 문제입니다.
  - 테스트 `test_coverage_is_derived_from_gap_without_repair_call`이 이 동작을 고정하고 있습니다.
- EXACT 대상이 이미 채택 span에 들어 있는 gap도 키가 새로우면 재진입합니다. 이것은 ASSESS의 판단 오류라서 다시 조사해도 바뀔 것이 없습니다.
- UNLOCATED gap은 identity가 여전히 `text_key(missing_target or reason)`(`request_repair.py:108`)입니다. 표현만 바뀌어도 새 gap이 됩니다.
  - 또 `target_evidence_signature`는 pairs가 없으면 그 쟁점의 **모든** 채택 span을 봅니다(`request_repair.py:159-167`). 상관없는 조문을 채택해도 `may_reopen`이 참이 됩니다.
- UNLOCATED에서는 `covers_target`이 항상 False입니다(`request_repair.py:148`). 모델이 검색으로 실제 대상을 찾아 채택해도 RESOLVED가 거절되고, 수정 호출이 나거나 UNRESOLVED로 잘못 기록됩니다.
- `open_gap_round`는 gap 라운드를 열 때마다 `window = 'search'`로 되돌립니다(`law_navigation.py:468-469`). **정확한 대상이 있는데도 코드가 먼저 전역 검색 화면을 엽니다.**

**원인 4. 충분성 판단이 FINISH 뒤(ASSESS)에만 있다** [확인]
- `coverage_gate`(`law_navigation.py:1366-1373`)는 쟁점마다 채택 원문이 하나라도 있는지만 봅니다.
- 없으면 일부러 ProposalError를 냅니다. 그러면 "같은 FINISH를 다시 제출하라"는 **수정 호출 1회가 설계상 발생**합니다(`request_decision` 경로, `law_navigation.py:1828-1869`).
- FINISH의 `sufficiency_reason`은 자유 서술이고 코드가 쓰지 않습니다.
- 그래서 "읽었으니 충분하다"는 혼동은 ASSESS(호출 1~2회)와 재진입 nav(호출 1~2회 이상)를 거쳐야만 드러납니다.

**원인 5. 행동에 대상·기대 관측이 없고 결과 대조도 없다** [확인]
- 결정 스키마에는 자유 서술 `reason`과 선택적 `gap_ids`뿐입니다(`law_navigation.py:116-218`).
- `step_outcome`(`:917-927`)은 new_laws, new_reads 같은 일반적인 변화량만 기록합니다.
- 그래서 "이유에는 제X조라고 쓰고 실제로는 제Y조를 읽거나 전역 검색"하는 경우를 코드가 알 수 없습니다.
- 정확 대상을 우선하라는 것은 프롬프트 한 줄(`:1806-1807`)뿐입니다. 메뉴는 그대로입니다.
  - 전역 RESEARCH와 SEARCH_STRUCTURE를 항상 제시합니다(`:1144-1145`).
  - 과거의 모든 frame에 RETURN_TO를 붙입니다(`:843-851`).

### 1.3 모델 판단 책임 (코드로 정답을 만들 수 없는 것)

- INTENT에서 배경을 요구로 확대하는 것. v5의 `request_quote`/`background_quotes`는 출처만 검증합니다.
- "관련 주제 조문을 직접 근거로" 삼는 판단.
- 규칙 구조의 의미 오류: 서로 다른 결정 효과를 하나의 ALL로 묶기, 의무를 조건으로 쓰기, 중복.

다만 "다시 조사해도 바뀔 수 없는 판단 오류를 재조사로 보내지 않는 것"은 코드 책임입니다(원인 3).

### 1.4 Codex 접근에서 틀린 점

1. **검증이 목표 행동을 거치지 않습니다.** 2단계로 끝나는 새 질문으로 A/B를 반복하면 루프 코드는 동작하지 않습니다.
2. **증상별 patch에 머물렀습니다.** identity patch(문구, retry hash, optional ID), 프롬프트 지시, 전역 카운터를 유지했을 뿐입니다. 행동의 효과를 하나의 원장으로 판정하는 구조가 없어서, 새 표현·새 라벨·새 fingerprint마다 구멍이 다시 생깁니다.
3. **진전 정의를 내용 기반으로 바꿨지만 탐색의 새로움을 포함했습니다.** 그리고 RESEARCH 귀속 오류로 새로운 조기 종료 경로를 만들었습니다.
4. **테스트가 정확 좌표 대상(모의승인규정 제1조) 한 형태만 다룹니다.** 다단계 반복을 흉내 내는 스크립트 모델 검사가 없습니다. 강제 material에서 재진입으로 가는 동작도 테스트로 고정했습니다.
5. **진단 라벨이 섞입니다.** no_progress 때문에 재조사를 못 해도 `stop_reason = 'INVESTIGATION_BUDGET'`으로 기록됩니다(`completion_execution.py:246-247`).
6. **네트워크와 루프를 구분하지 않았습니다.**
   - `TR`은 연결 실패를 포함한 모든 네트워크 오류를 `unknown=True`로 올립니다(`transport.py:130-137`).
   - `GW`는 unknown이면 재시도하지 않습니다(`gateway.py:326-335`).
   - 그래서 요청이 나가지 않은 게 확실한 실패도 "결과 불명"이 됩니다.
   - ADR0721의 502가 이 경로였는지는 패키지로 확인할 수 없습니다. 어느 쪽이든 루프 판정과 섞이면 안 됩니다.

---

## 2. 최소 다음 구현 구조 [제안]

**원칙:**
- 새 실행기나 새 단계, 새 모듈을 만들지 않습니다.
- 기존 checkpoint(`Investigation.p`) 안에 **요청 단위 대상 원장** `p['ledger']` 하나만 추가합니다.
- 나머지는 기존 상태에서 그때그때 계산(projection)해서 두 군데에 진실이 생기지 않게 합니다.
- 함수는 `request_repair.py`를 확장해서 넣습니다. 서빙 파일 수는 289개 그대로입니다.

**흐름:**
```
INTENT issues(request_quote) ──┐
요청에 명시된 좌표(bind_gap 재사용) ──┼─► Target{key, issue_ids, binding, status, tried}
ASSESS gap(bind_gap) ─────────────┘            ▲ 상태 전이
메뉴 행동 ─ predict_effect(EffectKey vs 전달/실행 원장) ─► 메뉴 정리(중복 제거·재표시 변환·EXACT_LOCK)
결정{target_ref, expectation} ─► execute ─► observe_effect(실행 전후 차이) ─► Effect{verdict}
FINISH / ASSESS 재진입 / 종료 ◄─ Target 상태 집계 (전역 카운터는 백스톱으로만)
```

**재사용할 기존 상태:**

| 개념 | 기존 원천 |
|---|---|
| 요구 | `p['issues']` (INTENT, request_quote 포함) |
| 대상 해석 | `RR.bind_gap` → `sq.resolve`, `inv.expected`, `find_coordinates` |
| 전달 | `basis_history[*].spans`, `navigation_recovery.delivered_spans`, 현재 page |
| 채택 | `groups[*].issue_decisions` |
| 실행 | `action_chain.steps[*].id`, gap `action_receipts` |
| 대상 근거 서명 | `RR.target_evidence_signature`, `inv.covers` |

**새로 저장하는 타입:**
```python
Ledger = {'contract': 'target-ledger-v1',
          'boundary': int,        # USER_REENTRY·사용자 사실·권한·세대 변경 때만 +1. ASSESS 재진입 때는 그대로
          'targets': {key: Target}, 'effects': [Effect]}   # effects는 append-only
Target = {'key': str,             # EXACT/ABSENT/AMBIGUOUS는 bind_gap identity_key 재사용
          'origin': 'REQUEST'|'ASSESS_GAP'|'REFERENCE_FROM_TARGET',
          'issue_ids': [str], 'binding': dict,     # bind_gap의 target_binding
          'status': 'UNLOCATED'|'LOCATED'|'DELIVERED'|'ADOPTED'|'ABSENT_PROVEN'
                    |'AMBIGUOUS'|'EXHAUSTED'|'CLOSED_NOT_NEEDED',
          'tried': [effect_key], 'missed_families': [str], 'evidence_sig': str}
Effect = {'step_id': str, 'boundary': int, 'key': tuple, 'family': str,
          'target_ref': str|None, 'expectation': str|None,
          'predicted': 'NEW_TEXT'|'REDISPLAY'|'NEW_LOCATION'|'REFERENCE',
          'observed': {'target_spans': int, 'new_spans': int, 'new_candidates': int,
                       'transitions': [(key, frm, to)], 'adoptions': int},
          'verdict': 'MET'|'MISSED'|'PENDING'|'INTERRUPTED'|'MISMATCH'}
```

**UNLOCATED identity [제안]:** `(issue, kind, 범위 안 document_hits 정규화, find_coordinates 정규화)`로 만듭니다. 문서·좌표가 둘 다 없는 순수 서술이면 `(issue, kind, 'PROSE')` 하나로 합칩니다.
- 트레이드오프: 같은 쟁점의 서로 다른 서술형 부족 두 개가 하나로 합쳐질 수 있습니다.
- 그래도 위치 단서가 없는 재조사는 수확이 낮으니 보수적으로 합치고, 지표(§7)로 관찰합니다.

---

## 3. 같은 행동과 정당한 재방문을 구분하는 규칙 [제안]

**EffectKey: 무엇을 관측하게 되는가로 정의하고, 라벨이나 handle은 넣지 않습니다**

| family | 키 구성 | 중복 판정 |
|---|---|---|
| READ_*, VIEW_SAVED | (boundary, document_id, offer 기대 span의 intervals digest) | `covers(expected, 전달된 전체)` |
| SEARCH_STRUCTURE | (boundary, doc 또는 None, 정규 좌표 집합, 정규 제목 키, coordinate_scope) | 같은 키가 COMPLETED |
| RESEARCH, SEARCH_BODY | (boundary, 범위 unit, `search_key(queries)`) | 같은 키(기존 방식). 결과 후보가 이미 본 것의 부분집합이면 zero-yield |
| OPEN_LAW, NEXT_* | (boundary, doc·source, unit, terms, cursor) | 같은 키 |
| BROWSE, OPEN_STRUCTURE | (boundary, doc, unit, offset) | 현재 표시 위치와 같으면 제거 |
| FOLLOW_CONNECTION | 기존 `reference_signature` | 기존 방식 |
| RETURN_TO | frame id만. **복원된 메뉴의 각 행동은 위 규칙으로 다시 판정**(bypass 제거) | — |

**상황별 판정**

| 상황 | 판정 |
|---|---|
| 같은 검색어의 형태소 변형 (search_key 동일) | 차단(기존). v6에서는 수정 호출 대신 **캐시 receipt**("이미 조회함, 결과 handle 동일")로 처리. 추가 호출 0, 대상 tried에 MISSED |
| 형태소는 다르지만 결과가 기존 후보의 부분집합 | 실행 전에는 알 수 없으므로 허용. zero-yield로 기록. **같은 대상**에 같은 family가 2회 zero-yield면 그 대상의 LOCATE 메뉴에서 그 family 제거 (다른 family는 남김) |
| 같은 문서의 다른 span (다른 항·호) | NEW_TEXT로 허용 |
| 같은 span이 예전에 전달됐고, 지금 화면에 없고, 열린 issue·target에 아직 결정이 없음 | **REDISPLAY**: VIEW_SAVED 방식으로 다시 보여주고 재취득은 안 함. 진전으로 세지 않고 다음 결정에서 평가 |
| 같은 span이 지금 화면에 있음, 또는 모든 열린 issue에 이미 결정이 있음 | 메뉴에서 제거 |
| Q1에 채택한 조문이 Q2에도 필요 (`Target.issue_ids`에 새 issue) | 그 issue에 한해 REDISPLAY 허용 |
| 새 사용자 사실, 권한·세대·버전 변경 | boundary +1. 모든 키가 새로 생기므로 재방문 허용. 예전 effects는 감사용으로 보존 |
| 결과가 늦게 오는 도구 (RESEARCH AWAITING) | 결과가 도착하면 **그 RESEARCH effect에** yield를 귀속. `record_search_outcome`에서 계산 |
| INTERRUPTED | 같은 키를 1회 재실행 허용. 중복 계산은 COMPLETED만 대상 |
| RETURN_TO 뒤 같은 행동 | 위 규칙을 똑같이 적용 (`return_context` bypass 제거) |

---

## 4. 다음 행동, 종료, 재진입 [제안]

### 4.1 결정 계약 (자유 서술이 아니라 enum)
- 조사 행동(INVESTIGATIVE_ACTIONS)에는 두 필드를 필수로 둡니다.
  - `target_ref`: 열린 target key 또는 issue id 중 하나 (enum)
  - `expectation`: 아래 표의 값 (enum)
- 행동의 효과가 target에 닿지 않으면 **거절하지 않습니다**(수정 호출 0). 대신 `MISMATCH`로 기록하고 그 대상의 tried에 넣습니다.
- 반복은 메뉴 단계에서 막습니다(4.2). 그래서 거절이 필요 없습니다.

### 4.2 메뉴 모드 (ledger가 결정)

| 조건 | 모드 | 제시할 행동 |
|---|---|---|
| UNLOCATED 없음 + LOCATED 또는 미결정 DELIVERED 대상 있음 | **EXACT_LOCK** | 대상 READ·REDISPLAY, 이어보기, 대상 문서 안 SEARCH_BODY, **전달된 대상 원문에 witness가 있는** FOLLOW_CONNECTION(`reference_overview`가 이미 witness 커버를 검사함, `law_navigation.py:758-761`), DECIDE, FINISH, PENDING. 전역 RESEARCH, NEXT_LAWS, 전역 SEARCH_STRUCTURE, RETURN_TO는 제시 안 함 |
| UNLOCATED·AMBIGUOUS 있음 | LOCATE | 전체에서 REDUNDANT와 그 대상의 고갈된 family를 뺀 것. 정확 대상 READ를 맨 앞에 |
| target 없음 (첫 조사) | OPEN | 전체에서 REDUNDANT를 뺀 것. issue를 pseudo-target으로 사용 |
| 모든 target이 종결 상태 | CLOSE | DECIDE, FINISH, PENDING (미결정 REDISPLAY만 추가) |

**정확 대상 vs 추가 참조:**
- 대상 원문 안의 참조가 unresolved이면 `REFERENCE_FROM_TARGET` 대상을 새로 만들고 LOCATE를 엽니다.
- 근거는 모델의 자유 서술이 아니라 **전달된 원문 속 witness**입니다. 이것이 정당한 추가 탐색과 정확 대상을 두고 하는 전역 배회를 가르는 기준입니다.

### 4.3 결과 대조 (`observe_effect`)

| expectation | 충족(MET) 조건 |
|---|---|
| READ_TARGET | 새로 전달된 span이 대상 기대 span과 겹침 |
| REDISPLAY_FOR_DECISION | 바로 다음 결정에서 그 span을 ADOPT 또는 EXCLUDE |
| LOCATE_TARGET | 대상 상태가 바뀜(UNLOCATED에서 다른 상태로), 또는 구조 경로·좌표가 locator와 일치하는 새 후보가 나옴 |
| FIND_SOURCE | 새로운 (doc, source) 후보가 1개 이상 나옴 |
| FOLLOW_REFERENCE | 참조 대상에서 새 span이 전달됨 |

**진전(no_progress 백스톱):**
- 리셋: 대상 span 전달, 채택, 대상 상태 전이.
- 중립: 새 후보가 나온 탐색(yield > 0). 리셋도 증가도 하지 않습니다.
- +1: zero-yield, MISSED, REDISPLAY 뒤 결정 없음.

### 4.4 종료
- **대상별 종료:** 서로 다른 family 2개가 MISSED이고 상태 변화가 없으면 그 대상은 EXHAUSTED가 됩니다. 그 대상의 탐색 행동은 메뉴에서 빠지고, FINISH 때 UNRESOLVED가 자동으로 채워집니다(거절 없음). 전역 카운터와 달리 다른 대상의 조사는 막지 않습니다.
- **요청 종료:** 모든 대상이 {ADOPTED, ABSENT_PROVEN, EXHAUSTED, CLOSED_NOT_NEEDED} 중 하나면 메뉴가 CLOSE가 됩니다. 쓸모없는 조사 행동은 아예 선택할 수 없습니다.
- 기존 예산(40/1800/2/2/3)은 **백스톱으로만** 유지합니다.

### 4.5 ASSESS → SELECT 재진입 계획 (`RR.reentry_plan`, `CE:228-247`에 적용)

| gap 상태 | 처리 | 추가 nav 호출 |
|---|---|---|
| 모델이 매긴 원래 material = false | 재진입 없음 (coverage는 PARTIAL 유지) | 0 |
| EXACT이고 채택 span이 이미 대상을 덮음 | 재진입 없음. `ASSESS_TARGET_ALREADY_ADOPTED` 기록 (모델 판단 지표) | 0 |
| EXACT, 전달됐지만 미채택 | 재진입. 첫 화면 sources에 REDISPLAY | 1 (DECIDE 또는 FINISH) |
| EXACT, 미전달 | 재진입. **시스템 prefetch READ**(채택 아님. chain에 `SYSTEM_PREFETCH` 단계로 기록) 후 첫 화면에 제시 | 1 |
| ABSENT_PROVEN | 재진입 없음. NOT_AVAILABLE을 lookup receipt로 자동 기록 | 0 |
| AMBIGUOUS | 재진입 (LOCATE) | 1회 이상 |
| UNLOCATED, 아직 안 쓴 family 있음 | 재진입 (LOCATE) | 1회 이상 |
| UNLOCATED·EXHAUSTED, 또는 같은 key가 닫혔고 evidence_sig가 같음 | 재진입 없음 | 0 |

- 재조사 불가 사유는 `stop_reason`에 정확히 남깁니다: `NO_PROGRESS`, `TARGET_EXHAUSTED`, `BUDGET`을 구분합니다.
- `open_gap_round`(`law_navigation.py:468-469`)는 EXACT 대상만 있으면 `window = 'read'`로 두고, 전역 검색 화면은 UNLOCATED가 있을 때만 엽니다.

---

## 5. 추가 LLM 호출 없이 먼저 할 것 vs 모델 개선이 필요한 것

**코드만으로 먼저 할 것 (호출 0, 정답 하드코딩 없음):**
1. EffectKey 원장과 메뉴 정리, RETURN_TO bypass 제거, 이미 전달된 READ를 재표시나 제거로 처리.
2. 진전 재정의, RESEARCH yield 귀속 수정(조기 종료 버그 제거).
3. 재진입 계획표(4.5), `model_material` 보존(`completion_v5.py:132-133`에서 강제하기 전에 원값 저장), EXACT prefetch, `open_gap_round` 화면 수정.
4. `coverage_gate`의 설계상 수정 호출 제거. FINISH 스키마에 `issue_closure:[{issue_id, status: ADOPTED|NOT_FOUND}]`를 넣고, 채택이 없는 issue는 NOT_FOUND만 고를 수 있게 enum으로 묶어 같은 호출 안에서 처리.
5. UNLOCATED RESOLVED 허용: 라운드가 열린 뒤 새로 채택한 해당 issue span을 지정하면 그 위치로 다시 바인딩.
6. 중복 조회는 거절 대신 캐시 receipt로 처리.
7. `stop_reason` 라벨 분리.
8. (별도 변경) transport에서 연결 수립 전 실패는 `unknown=False, retryable` 1회로.

**모델 계약 변경이 필요한 것 (live 검증이 필요하고 기본 경로는 유지):**
- `target_ref`/`expectation` enum 채우기. 출력이 소폭 늘고, 비준수는 MISMATCH 지표로만 봅니다.
- (2단계) FINISH에서 모델이 아직 부족한 대상을 직접 선언(`missing_targets`) → ASSESS 전에 EXACT를 prefetch.
- 규칙 의미 품질(다른 결정 효과를 ALL로 묶기, 의무를 조건으로 쓰기, 중복): 스키마에서 "결정 효과마다 rule을 분리"하는 계약은 모델 개선 과제입니다. 코드는 문장을 바꾸거나 지우지 않습니다. answer_content 정본 원칙 때문입니다. 완전히 같은 문장이 결론·상세·의무에 걸쳐 중복되는 것은 **ASSESS가 이미 수정 시도를 할 때만** 피드백에 실어 보냅니다. 별도 호출은 만들지 않습니다.

---

## 6. 코드 변경 지도와 이행

| 파일 · 함수 | 변경 | 상태 영향 |
|---|---|---|
| `RR` (확장) | `ledger_enabled`, `ensure_ledger`, `effect_key`, `predict_effect`, `observe_effect`, `targets_from_request/gaps`, `transition`, `menu_mode`, `prune_menu`, `reentry_plan`, `progress_v6` 추가. `validate_resolutions`에 UNLOCATED 재바인딩과 EXHAUSTED/ABSENT 자동 처리 | `p['ledger']` |
| `LN.__init__` | `controller_version` 고정, ledger 초기화. USER_REENTRY 분기(`:335-348`)에서 `boundary += 1` | ledger |
| `LN.view` | `annotate_reused_reads` 다음에 `prune_menu`. 모델용 `target_ledger` 요약(대상, 상태, 시도한 수단, 다음 허용 수단). RETURN_TO는 REDUNDANT가 아닌 행동이 있는 frame만, 최대 6개 | data, actions |
| `LN.decision_schema` | v6: 조사 행동에 `target_ref`/`expectation` 필수, FINISH에 `issue_closure` | — |
| `LN.validate` | v6: `return_context` bypass 제거. seen 검사를 effect 기반으로 교체. `coverage_gate` 대신 `issue_closure` 검증. 중복 조회는 캐시 receipt 경로로 | — |
| `LN.execute` / `record_search_outcome` | `observe_effect`, `progress_v6`. RESEARCH 결과 도착 때 yield 귀속과 no_progress 재계산 | effects, no_progress |
| `LN.open_gap_round` | EXACT면 prefetch(`execute_tool` READ 경로 재사용, `SYSTEM_PREFETCH` 단계), window 유지 | groups, basis |
| `LN.run` | `progressed` 키 목록(`:1908`)에 `'ledger'` 추가. 빠뜨리면 accepted replay 때 원장이 사라짐 | — |
| `V5.prepare` | material을 강제하기 전에 `model_material` 저장 | gap |
| `CE` (`:228-247`) | `reentry_plan` 적용, stop_reason 분리 | — |
| `CM` (`:514-523`) | 로직 변경 없음. `new_epoch`의 deepcopy로 ledger가 보존되는지 테스트로 고정 | — |
| `law_candidates.policy` | `navigation_controller_version ∈ {None, 'target-ledger-v1'}`, v5 필수 | — |
| `investigation_chain.compact` | 각 단계에 effect verdict 요약 | — |
| 프로필 · PIPELINE · engine pin · UnifiedRag identity | 플래그와 해시 갱신 (파일 수 변화 없음) | — |
| `TR:130-137` (**별도 변경·별도 ADR**) | 연결 수립 전 실패만 known-not-sent | — |

**Target 상태 전이**

| 현재 | 사건 | 다음 |
|---|---|---|
| UNLOCATED | lookup MATCH, 또는 구조 경로가 일치하는 후보 | LOCATED |
| UNLOCATED | `MISSING_COORDINATE` + indexed_complete | ABSENT_PROVEN (→ NOT_AVAILABLE) |
| UNLOCATED | lookup AMBIGUOUS | AMBIGUOUS |
| UNLOCATED | 라운드 이후 새로 채택한 span + RESOLVED 지정 | ADOPTED (재바인딩) |
| UNLOCATED·AMBIGUOUS | 서로 다른 family 2개 MISSED, 상태 변화 없음 | EXHAUSTED |
| LOCATED | READ 또는 prefetch로 기대 span 전달 | DELIVERED |
| DELIVERED | ADOPT (해당 issue) + `covers_target` | ADOPTED |
| DELIVERED | 읽은 근거로 EXCLUDE | CLOSED_NOT_NEEDED |
| 아무 상태 | boundary 변경 | 새 key로 다시 열림 |

**메뉴 정리 의사코드:**
```python
def prune_menu(inv, data, actions):
    led = inv.p['ledger']; mode = menu_mode(led)
    for ident, a in list(actions.items()):
        kind = predict_effect(inv, a, data)       # NEW_TEXT|REDISPLAY|REDUNDANT|EXHAUSTED_FAMILY|NEW_LOCATION
        if kind in ('REDUNDANT', 'EXHAUSTED_FAMILY') or not allowed_in(mode, a, led):
            del actions[ident]
        elif kind == 'REDISPLAY':
            actions[ident] = as_view_saved(inv, a)   # 재취득 없이 다시 보여주기
    data['target_ledger'] = project(led); data['menu_mode'] = mode
```

**구버전 재개 · 롤백:**
- 재개된 요청은 **시작할 때의 controller_version을 끝까지 사용**합니다. accepted/decision_retry 스냅샷의 input_hash를 지키기 위해 필수입니다.
- v5 checkpoint를 USER_REENTRY로 다시 열 때만 새 epoch 경계에서 ledger를 backfill합니다. basis_history, selected, structure_search_history, query_keys, steps에서 결정적으로 재구성하고 `backfilled: true`를 붙입니다.
- 결과는 `investigation_state.ledger`와 `diagnostics.loop_metrics`에 남깁니다. 공개 응답에는 수치만 넣습니다.
- 롤백은 프로필 플래그만 끄면 됩니다. v5 경로와 그대로 같고, journal 스키마 이전은 필요 없습니다.

---

## 7. 검증 설계

### 7.1 합성 반례 (모델 호출 0, 신규 테스트로 추가)

| 분류 | 반례 |
|---|---|
| 가짜 진전 | ① 전역 RESEARCH가 새 법령만 내고 대상 span이 0일 때 no_progress가 리셋되지 않음 ② RESEARCH 결과가 늦게 도착하면 그 단계에 귀속, no_progress=1에서 RESEARCH를 해도 결과를 보기 전에 끝나지 않음 |
| 반복 탐색 | ③ "제6조", "제 6 조", "6조" SEARCH_STRUCTURE가 같은 키, 두 번째는 캐시 receipt이고 호출 0 ④ 결과가 부분집합인 RESEARCH 2회 뒤 그 대상의 RESEARCH family만 제거 ⑤ RETURN_TO 뒤 같은 OPEN_LAW는 메뉴에 없음 |
| 중복 읽기 | ⑥ X를 채택하고 RESEARCH로 fingerprint가 바뀐 뒤 X READ가 제거됨 ⑦ X 미채택·미표시면 REDISPLAY이고 `ur.read` 0회 ⑧ gap 라벨 READ와 구조 라벨 READ가 같은 효과로 판정되고 validate 거절 0 |
| 잘못된 FINISH · 재진입 | ⑨ 이미 채택된 EXACT 대상 gap은 재진입 0, nav 0 ⑩ model_material=false면 재진입 0, coverage PARTIAL ⑪ EXACT 미전달은 prefetch 후 nav 1회로 RESOLVED ⑫ 미커버 쟁점 FINISH에서 수정 호출 0 ⑬ UNLOCATED를 검색으로 찾아 채택하면 RESOLVED와 재바인딩 ⑭ UNLOCATED를 표현만 바꿔 다시 내도 같은 key |
| 정당한 재방문 | ⑮ 새 사용자 사실이 오면 같은 READ 허용 ⑯ 권한·세대 변경은 새 조사 ⑰ 같은 문서의 다른 항 허용 ⑱ Q1 채택 조문을 Q2용으로 REDISPLAY ⑲ INTERRUPTED는 1회 재실행 ⑳ EXACT_LOCK에서 witness 기반 FOLLOW 허용, 전역 RESEARCH는 미제시 ㉑ 대상 원문의 unresolved 참조는 derived target으로 LOCATE |
| 재개 · 인프라 | ㉒ v5 checkpoint는 v5 그대로, 해시 일치 ㉓ accepted replay 중 ledger 보존 ㉔ 연결 전 실패는 재시도 1회, 연결 후 실패는 unknown 유지(세 번째 호출 금지 유지) |

**기존 294개는 그대로 돌려 같은 15개만 실패하는지 확인합니다.**

### 7.2 반사실 replay (모델 0, 네트워크 0, 새 질문 없음)
- MAIN50 51문항의 기록된 nav 결정을 기존 `ScriptedTransport` 패턴으로 v6 controller에 순서대로 넣습니다. 데이터는 generation50 그대로입니다.
- 사례마다 다음을 기록합니다.
  - **첫 분기 지점**: 기록된 행동이 v6 메뉴에 없는 곳과 그 분류(REDUNDANT, EXHAUSTED, EXACT_LOCK).
  - v6이 건너뛸 재진입.
  - **오차단**: 막힌 행동의 effect가 원래 실행에서 최종 채택 span에 기여했는지. 반드시 0이어야 합니다.
- 이 단계는 상한 진단입니다. 모델이 대신 무엇을 했을지는 알 수 없으니 성공 주장에 쓰지 않습니다.
- journal은 내부 자료라 팀에서 돌려야 합니다.

### 7.3 Live A/B (사전 동결)
- **세트:** MAIN50 진단 기록에서 객관 기준으로 **전부** 뽑습니다(골라내기 금지).
  - 기준: ASSESS 재진입 ≥1, 거절 결정 ≥1, nav 단계 ≥4, stop_reason ∈ {NO_PROGRESS, REPEATED_ASSESSMENT_GAP, MODEL_DECISION_UNRESOLVED}, PARTIAL, 실패.
  - ADR0719와 0721의 공개 6문항은 쉬운 경로의 비회귀용으로 따로 둡니다.
- **세 가지 구성:** MAIN50 / v5 후보 / v6. 반복 r = 2~3. 질문 목록, 코드, 프로필 해시를 먼저 동결합니다.
- **인프라 규칙(사전 등록):** 첫 바이트 전에 연결 단계에서 실패하면 `INFRA_NOT_SENT`로 분류합니다. 같은 입력·같은 코드로 1회 재실행하고 따로 보고합니다. ADR0721에 소급 적용하지는 않습니다.

**측정 항목 (journal 이벤트에서 계산):**
1. 필요 원문 도달 단계와 FINISH 전 도달 여부
2. 실행된 중복 effect 수
3. 조사 행동당 대상 관련 신규 span·채택 수
4. 같은 gap 왕복(evidence_sig 변화 없이 다시 열림)
5. EXACT 대상이 열려 있는데 한 전역 탐색 수
6. 재진입 수와 유효 재진입 수
7. 단계별 호출 수: nav, nav-repair(오류 코드별), assess, assess-repair, reference. FOLLOW_CONNECTION은 최대 2호출입니다(`unit_relations.py:487,494`).
8. 지연(전체, 최종 답변 제외)과 입출력 토큰
9. 승인 answer_content 해시 보존, 인용 검증, 쌍대 coverage
10. MISMATCH 비율 (모델 지표, 참고용)

**성공·회귀 기준 (개선률 예측 없음):**
- **보장 (반드시 0):** 항목 2, 4, 5. 메뉴와 validator가 어긋나서 생긴 수정 호출. 반사실 오차단.
- **비열등:** 모든 반복에서 v6 coverage가 v5보다 낮은 사례는 0. 인용과 내용 보존은 100%.
- **효율:** 루프 유발 세트에서 nav와 수정 호출 합계, wall time이 v5보다 높지 않아야 합니다. 쉬운 세트는 호출 수가 같아야 합니다.
- 인프라를 뺀 완료가 사례마다 2회 이상이어야 판정합니다.

---

## 8. 우선순위

**가장 먼저 (2~3개):**
1. **Effect 원장, 메뉴 정리, 진전 재정의, RESEARCH 귀속 수정, RETURN_TO bypass 제거.** 반복 행동을 직접 막고, 결정적이며, 모델 변경이 없습니다.
2. **재진입 계획표, `model_material` 분리, EXACT prefetch, `open_gap_round` 화면 수정.** 가장 비싼 FINISH→ASSESS→SELECT 왕복을 줄입니다.
3. **설계상 수정 호출 제거.** `coverage_gate`를 `issue_closure`로 바꾸고, UNLOCATED RESOLVED와 중복 조회 캐시 receipt를 넣습니다.

**당장 유지할 것:**
- v5 epoch, retry 스냅샷, 세 번째 호출 금지
- `bind_gap`의 indexed_complete 부재 증명
- EXACT 해결 규칙
- answer_content 보존과 `verify_content`
- ASSESS 원문 투영
- assessment cache
- 예산(백스톱으로만)

**이번에는 하지 않을 것 (이유):**
- 매 단계 판단 모델이나 최종 검토 모델 상시화: 호출과 지연이 늘고, 원인은 판단이 아니라 제어 구조입니다.
- max_no_progress, search_rounds, 재진입 한도 숫자 조정: 증상이 다른 곳으로 옮겨갈 뿐입니다.
- 코드로 조건 논리나 중복 문장을 수정·삭제: 정본 원칙에 어긋나고 의미가 바뀔 위험이 있습니다.
- FINISH에서 모델이 부족 대상을 선언하는 기능: 원장 지표를 확보한 뒤 2단계로 미룹니다.
- 긴 프롬프트 추가, 새 공개 질문 교체로 통과 판정.

**효율적인 검증 순서:**
1. 합성 반례 ①~㉔와 기존 294개
2. MAIN50 반사실 replay (모델과 네트워크 0)
3. transport 연결 분류는 **별도 변경**으로, 단위 테스트만
4. 사전 동결한 루프 유발 세트로 live A/B
5. 그다음 MAIN 승격 판단

ADR0721의 통신 실패와 집계 스크립트 오류는 이 판정과 분리해 다루었습니다.
