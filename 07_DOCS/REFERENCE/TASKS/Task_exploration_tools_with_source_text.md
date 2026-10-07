# Task — 탐색 도구에 원문을 붙인다 (항법 복원 1단계)

- 등록일: 2026-09-20
- 상태: 설계 — 미구현, ADR 미선점
- 대상: `document-navigation-v1` 질의 루프 (`02_BACKEND/semantic_runtime/work_navigation.py`, `legal_navigation.py`, `navigation_loop.py`)
- 서비스 배선: 변경 없음. 이 문서만으로 MAIN·ACTIVE_RELEASE를 바꾸지 않는다.

---

## 1. 이 문서가 나온 경위

2026-09-20 세션에서 ADR-0474 0단계 감사 피드백을 검증하다가, 질의 경로 전체를
실행 기록으로 역추적했다. 확인하려던 것은 "데이터가 문제인가"였는데, 측정 결과는
데이터도 회수 알고리즘도 아닌 **에이전트 루프가 항법을 하지 않는다**는 것이었다.

추적에 쓴 정본은 다음 세 가지다.

- `04_EXPERIMENTS/ADR/ADR-0461-fulltext-candidate-ranking/artifacts/runs-run1/*.json` (51문항 실행 기록)
- 같은 ADR의 `metrics-run1.json`, `rank-fts.json`
- `04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts/judged-results.json` (의미정답 채점)

---

## 2. 기존 문제 — 측정된 것

### 2-1. 성능이 상한에 한참 못 미친다

| arm | 의미정답 |
|---|---:|
| baseline (ADR-0460, FTS 이전) | 15/51 |
| fts-run1 (현재 런타임) | **26/51** |
| ceiling-qwen (정답 조문만 주고 검색 생략) | 44/51 |
| ceiling-best (Opus 4.8, 정답 조문만) | 48/51 |

### 2-2. 손실 회계 (51문항 전수)

| 탈락 지점 | 건수 |
|---|---:|
| 조문을 채택하고도 종합 문장화에서 내용 소실 | 10 |
| 후보 보드 12개 컷 (결정 조문 13위 이하) | 6 |
| `title_query`가 정답 문서를 범위에서 제거 | 2 |
| 계약 실패 (cm-020/024/028/045) | 4 |
| BM25 순위 실패 (100위 밖) | 3 |
| 색인 부재 | 1 |

**데이터 순수 부재는 1건이다.**

### 2-3. 회수의 절벽은 12위와 13위 사이에 있다

| 결정 조문 최상위 FTS 순위 | 건수 | 읽음 | 정답 |
|---|---:|---:|---:|
| 1–12위 (보드 1페이지) | 41 | **39 (95%)** | 23 |
| 13–24위 | 2 | **0** | 0 |
| 25–100위 | 5 | 1 | 2 |
| 100위 초과 | 3 | 0 | 1 |

보드 페이지 크기는 `navigation_work_state.py`의 `page(rows, offset=0, limit=12)`이고,
`apply_reviews`가 검토마다 `self.board_offset = 0`으로 되돌린다. 51런 전체에서
`WORK_PAGE` 호출은 **0회**다. 따라서 실질 노출은 항상 같은 상위 12개다.

### 2-4. 모델은 탐색을 하지 않는다

51런 전체 도구 사용량:

```
READ 317   JUDGE 290   READ_BATCH 112   REVIEW 59
INTERPRET_QUERY 51   SYNTHESIZE 38   FIND_ARTICLE 8   LEGAL_SEARCH 7
```

0회인 도구: `WORK_PAGE` `GRAPH` `OPEN_TERM` `LIST` `REFERENCES` `DISMISS`
`REJECT_RELATION` `TOOL_RESULT` `STOP` `DOCUMENT_OUTLINE` `OPEN_FOLDER` `DOCUMENT_TITLES`

모델의 첫 실질 행동은 **50런 전부 `READ`** 였다. 예외가 없다.

읽은 조문 299건 중 268건(90%)이 FTS 시드(순위 ≤24) 안이었고,
**모델이 스스로 찾아온 조문은 5건(1.7%)** 이다.
채택 근거 111건 중 105건(95%)이 FTS top-12, 순위 중앙값은 3위다.

검색 호출 15건의 사유를 그대로 옮기면:

```
  4  verification requested missing evidence        ← 서버가 강제
  2  상증세법 시행령 제49조 제1항의 정확한 구조와 내용을 확인하기 위해…
  2  상증세법 시행령 제49조 제1항의 정확한 조문 구조를 확인하기 위해…
  2  상증세법 시행령 제49조 제1항의 정확한 조문 구조를 확인하여…
  1  정관 변경의 결의요건을 확인하기 위해…
  1  정관 변경의 결의요건에 관한 명시적 조문을 찾기 위해…
```

모델 자발 검색은 11회, 3개 질문에 몰려 있고 같은 질의를 반복했다.

---

## 3. 진단 — 왜 항법이 돌지 않는가

### 3-1. 탐색 행동에 보상이 없다

예산은 `max_calls: 14`를 전 구간이 공유한다. 모델 입장의 손익:

| 행동 | 돌아오는 것 | 비용 |
|---|---|---:|
| `READ_BATCH` → `JUDGE` | 조문 원문 최대 3건 + 채택 근거 | 2콜 |
| `GRAPH` / `OPEN_TERM` / `LIST` / `REFERENCES` | 이름·제목·ID **메타데이터만** | 1콜 |
| `WORK_PAGE` | 카드 12개 더. 원문 없음 | 1콜 |

`SYNTHESIZE`는 채택 근거가 있어야 스키마에 나타나고, 채택은 읽어야 생긴다.
**탐색은 순손실, 읽기는 즉시 이득.** 첫 행동이 항상 `READ`인 것은 합리적 선택이다.

근본 원인은 카드가 담는 정보에 있다. `navigation_loop.py:87`:

```python
self.metadata[sid] = {'id': sid, 'document_id': s['document_id'],
                      'document_name': matcher.documents[s['document_id']],
                      'heading': s['heading'], 'unit_id': s['unit_id']}
```

**본문이 없다.** 13번째 후보가 볼 가치가 있는지, 이 참조를 따라가야 하는지
판단할 근거가 모델에게 구조적으로 주어지지 않는다.

### 3-2. 설계 의도와 현재 상태가 뒤집혀 있다

ADR-0428은 후보를 "최초 8개 고정"으로 줬고, ADR-0429가 그것을 제거하며
모델 항법으로 전환했다. 그 뒤 ADR-0430부터 ADR-0460까지 약 30개 ADR 동안
결정 조문 읽기 비율은 0.25를 넘지 못했다. ADR-0461이 BM25 정렬을 넣자
0.253 → 0.627로 올랐다. **처음으로 숫자를 움직인 것이 BM25였기 때문에
BM25가 중심이 됐다.**

그 결과 없애려던 "고정 상위 N"이 "BM25 정렬 고정 상위 12"로 돌아왔다.
그런데 프롬프트는 아직 옛 설계를 말한다.

- `navigation_loop.py` SYSTEM: "점수나 상위8개 확정은 없다."
- `work_navigation.py` SYSTEM: "…전문검색 순위 순서로 제시되며 **컷 없이** 모두 페이지로 남는다."
- `context()`의 `candidate_review.order`: "…then distinct question concepts; **no cut**"

코드는 점수로 정렬해 12개에서 자르고, 프롬프트는 모델에게 점수도 컷도 없다고
말한다. 이 모순이 현재 상태의 요약이다.

### 3-3. 정렬 함수에서 항법 신호가 도달 불가능한 자리에 있다

`work_navigation.py`의 `candidate_order`:

```python
order = lambda s: (
    s not in waiting, s in demoted, s not in priority,
    s not in self.followup_ids, s not in self.explicit_ids,
    self.fulltext_rank.get(s, unranked),   # ⑥ 소스마다 고유한 정수
    -self.concept_hits.get(s, 0),          # ⑦ 동점이 없으므로 영원히 미발동
    s)
```

`fulltext_rank`가 고유값이라 ⑦ 이하는 실행되지 않는다. 용어 253,324개·
간선 48,101개가 만드는 신호가 순위에 개입할 수 없다.

---

## 4. 이렇게 바꾼다 — 설계

### 4-0. 원칙

> **탐색 도구가 원문을 돌려주게 한다. 단, 그 원문은 읽기 창을 소비하지 않고
> 인용 자격도 갖지 않는다.**

근거 계약은 그대로 유지된다. `quote_store`는 `legal_navigation.py:187`의
READ 시점에만 채워지므로, 발췌(preview)는 **구조적으로** 인용될 수 없다.
`check_reviews`의 다음 검사가 그대로 작동한다:

```python
q = self.quote_store.get(r['quote_ref'])
if not q or q['segment_id'] != r['segment_id']:
    raise ValueError('review quote is not bound to read segment')
```

### 4-1. 예산 계산 (실측)

조문 본문 길이 (4,000건 표본):

| 지표 | 값 |
|---|---:|
| 중앙값 | 221자 |
| p25 | 65자 |
| p75 | 643자 |
| p90 | 1,624자 |
| **200자 이하 비율** | **48%** |

**조문의 절반은 200자 이하다. 200자 발췌는 그 절반에게 전문이다.**

행동·검토 턴 컨텍스트 실측 (467턴):

| 지표 | 값 |
|---|---:|
| 중앙값 | 13,710자 |
| p90 | 30,273자 |
| 최대 | 46,224자 |
| 한도 `context_chars` | 60,000자 |
| **런별 최대 기준 여유 중앙값** | **30,992자** |

비용: 보드 12카드 × 200자 = **2,400자**. 여유의 8%.
보드를 32로 넓혀도 6,400자로 21%다.

### 4-2. 변경 C1 — `source_card`에 발췌를 붙인다

변경 지점은 하나다. `legal_navigation.py`의 `source_card`가 모든 조문 카드의
공통 생성자이므로, 여기에 붙이면 **후보 보드·`LIST`·`REFERENCES`·
`LEGAL_SEARCH`·`FIND_ARTICLE` 결과에 동시에 파급된다.**

추가 필드:

| 필드 | 뜻 |
|---|---|
| `preview` | 본문 앞 200자 (원문 그대로, 정규화 없음) |
| `preview_complete` | 200자 이내라 발췌가 곧 전문인가 (`bool`) |
| `preview_chars` | 전체 본문 길이 |

모델 프롬프트에 명시할 문장:

```
카드의 preview 는 조문 본문의 앞부분이다. preview_complete 가 true 면 그것이 전문이다.
preview 는 근거로 인용할 수 없다. 인용하려면 READ 로 읽어 quote_ref 를 받아야 한다.
preview 로 무관함이 분명하면 읽지 말고 DISMISS 한다.
```

### 4-3. 변경 C2 — READ_BATCH 결과에 참조 대상 발췌를 동봉한다

`read_batch`는 이미 읽을 때마다 참조를 등록한다:

```python
if result.get('source_id'):
    self.discover_references(result['source_id'])
```

지금은 이 참조들이 `open_reference_tasks()`에 **로케이터 문자열로만** 나타나고,
모델이 `REFERENCES`를 호출해야 조문에 닿는다. 그 호출은 51런에서 0회였다.

변경: 해결된 참조 대상(`reference_resolved(resolution)`이 참인 것)의
**카드 + 발췌를 READ_BATCH 결과에 그대로 동봉한다. 추가 모델 호출 0회.**

이것이 cm-003 유형을 직접 겨냥한다.

```
cm-003 「재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?」
  결정 조문: 코스닥시장 상장규정 제26조, 시행세칙 제23조
  현재 결과: 제26조는 채택, 시행세칙 제23조 제4항을 읽지 않아
             "제3호 제외 후 제4호 적용"을 확정하지 못함 → 오답
```

제26조를 읽는 순간 세칙 제23조의 발췌가 따라오면, 위임 추적이 모델의
선택이 아니라 **읽기의 부산물**이 된다.

동봉 상한: 참조 대상 최대 8건 × 200자 = 1,600자.

### 4-4. 변경 C3 — 발췌 예산 축소 정책

`context()`는 이미 초과 시 예외를 던진다:

```python
if len(json.dumps(data, ensure_ascii=False)) > self.limits['context_chars']:
    raise ValueError('work context budget exceeded; exact state retained')
```

발췌 때문에 이 예외가 나면 안 된다. 축소 순서를 정한다.

1. 참조 동봉 발췌를 200자 → 80자
2. 보드 카드 중 `review_status == 'reviewed'` 인 것의 발췌 제거
3. 보드 카드 발췌를 200자 → 80자
4. 그래도 초과하면 발췌 전부 제거하고 `preview_suppressed: true` 를 컨텍스트에 남긴다

축소가 발동한 턴은 `work.event`로 기록해 사후에 셀 수 있게 한다.

### 4-5. 변경하지 않는 것

이번 작업 범위 밖이다. 섞으면 효과를 귀속할 수 없다.

- 보드 페이지 크기 12 (`page(limit=12)`)
- `board_offset = 0` 리셋
- `candidate_order`의 `fulltext_rank` 위치
- `max_calls: 14` 등 예산
- 종합·검증 계약
- `title_query` 범위 좁히기
- MAIN 배선, ACTIVE_RELEASE, 데이터 세대

**이유:** 지금 필요한 답은 "발췌를 주면 모델이 탐색을 시작하는가" 하나다.
보드를 동시에 넓히면 회수 개선이 발췌 덕인지 보드 덕인지 갈라낼 수 없다.

---

## 5. 검증 계획

### 5-1. ADR 절차

`AGENTS.md`의 실험 절차를 따른다. 구현 수정 **전에** 선점한다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py new --adr-root 04_EXPERIMENTS/ADR
```

- 부모 arm: ADR-0461 `fts-run1` (같은 51문항, 같은 세대, 같은 설정)
- 평가셋: CM 골든 `cm-field-core-e2e-v3`, scorable 51건
  (`5e3227561a31123ccb77a3c55f0ca0d88b542d9b6ecac20aab26f812949eb169`)
- 제품 모델·데이터 세대·엔진 해시는 ADR-0461과 동일하게 고정한다.
- 의미정답 채점은 ADR-0462와 같은 Gemini 채점기·같은 system sha256을 쓴다.

### 5-2. 1차 지표 — 탐색이 살아났는가

이것이 이 변경의 직접 목표다. 회수·정답보다 먼저 본다.

| 지표 | 현재 (fts-run1) | 목표 |
|---|---:|---:|
| 탐색 도구 호출 수 (`REFERENCES`·`LIST`·`GRAPH`·`OPEN_TERM`·`LEGAL_SEARCH`·`FIND_ARTICLE`) | 15 | **≥ 60** |
| 모델 자발 검색이 발생한 질문 수 | 3/51 | **≥ 15/51** |
| `model_found` 조문 수 / 읽은 조문 | 5/299 (1.7%) | **≥ 10%** |
| `DISMISS` 호출 | 0 | **≥ 10** |
| C2 참조 동봉으로 읽힌 조문 수 | 0 | **≥ 20** |

### 5-3. 2차 지표 — 회수와 정답

| 지표 | 현재 | 기준 |
|---|---:|---|
| decisive 읽기 | 0.627 | 회귀 없음 (≥ 0.60) |
| decisive 채택 | 0.560 | 회귀 없음 (≥ 0.53) |
| 답변율 | 0.922 | ≥ 0.90 |
| 실행 실패 | 4 | ≤ 4 |
| 의미정답 | 26/51 | **≥ 26** (회귀 금지) |
| FTS 순위 13위 이상 결정 조문을 읽은 건수 | 1/10 | **≥ 3/10** |

마지막 줄이 핵심이다. 보드는 그대로 12개인데 13위 이하 조문을 읽었다면,
그건 **탐색 도구를 거쳐 들어왔다는 뜻**이다.

### 5-4. 반증 기준

- 탐색 도구 호출이 30회 미만이면 **발췌만으로는 부족**하다고 판정하고,
  예산 구조(탐색 콜 별도 배정)로 문제를 재규정한다.
- 탐색 호출은 늘었는데 decisive 읽기가 0.60 아래로 떨어지면,
  발췌가 읽기 예산을 잡아먹은 것이므로 발췌 길이를 80자로 낮춰 1회 재실행한다.
- 컨텍스트 축소(C3) 발동이 전체 턴의 20%를 넘으면 발췌 기본값을 재설계한다.

---

## 6. 위험

### 6-1. 보드가 더 똑똑해져서 탐색이 더 줄어들 수 있다

발췌가 붙은 보드 12개만으로 판단이 끝나면, 모델은 오히려 탐색할 이유를
잃는다. **BM25 의존이 깊어지는 방향이다.**

이 위험은 5-2와 5-3의 마지막 줄로 감시한다. 탐색 호출이 늘지 않고
decisive 읽기만 올랐다면 그것은 "더 좋은 리랭커"를 만든 것이지
항법을 복원한 것이 아니다. 그 경우 결과를 그렇게 기록한다.

### 6-2. 발췌가 조문의 결론부를 놓친다

앞 200자는 조문 제목과 제1항 앞부분이다. 단서·예외는 뒤에 있는 경우가 많다.
따라서 `preview_complete: false` 인 카드에 대해 모델이 `DISMISS`를 남발하면
정확도가 떨어진다. 프롬프트에 명시한다:

```
preview_complete 가 false 면 단서·예외가 뒤에 남아 있을 수 있다.
그 경우 무관 판단으로 DISMISS 하지 말고 READ 한다.
```

지표: `preview_complete: false` 카드에 대한 `DISMISS` 중,
그 조문이 골든 결정 조문이었던 건수. **0이어야 한다.**

### 6-3. 원문 발췌가 컨텍스트에 들어가는 범위

발췌는 이미 스코프 안 문서의 본문이고, READ가 주는 것과 같은 자료다.
반출 경계는 `store.manifest['export_allowed']`와 `RequestContext`가 그대로
관리한다. 새 경로가 생기지 않는다.

---

## 7. 작업 순서

1. ADR 선점 (`adr_structure.py new`)
2. 가설·성공 기준·평가셋 동결 → `artifacts/design-before-implementation.json`
3. C1 구현 + 계약 테스트 (발췌는 `quote_store`에 들어가지 않음을 검사하는 테스트 포함)
4. C2 구현 + 계약 테스트
5. C3 구현 + 축소 발동 기록 테스트
6. 후보 snapshot·register·freeze (표준 절차, 운영 registry 자동 선택 금지)
7. 51문항 E2E 실행 → `artifacts/runs/`
8. ADR-0462와 같은 채점기로 의미정답 채점
9. `adr_structure.py validate --final` + `graph`
10. 결과 기록. **MAIN 승격은 이 ADR 범위 밖이다** (out-of-sample 아님, `decision_eligible=false`)

---

## 8. 이 다음에 올 것 (별도 ADR)

이번 작업에서 의도적으로 뺀 것들이다. 순서는 이 실험 결과가 정한다.

- **참조 자동 승격**: 해결된 참조를 후보 풀에 직접 넣고 `candidate_order`의
  `priority` 자리를 쓰게 한다 (자리는 이미 있다)
- **FTS 구간화**: `fulltext_rank`를 구간(1–10, 11–30, 31–100)으로 바꾸고
  구간 안에서 `concept_hits`로 정렬한다. "BM25는 참고 도구"의 코드적 표현
- **보드 32 + `board_offset` 리셋 제거** (`page()`는 이미 `limit<=32` 허용)
- **종합 단계 수치 보존 계약**: 채택 인용의 수치 토큰이 finding에 없으면 거부.
  현재 수치 지표 15개 중 8개가 채택 인용에 있었으나 최종 답변에는 3개만 남았다
- **도구 표면 축소**: 실행에서 0회인 도구 9개가 스키마를 부풀린다
