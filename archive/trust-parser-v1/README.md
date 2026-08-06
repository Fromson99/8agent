# trust-parser — 온톨로지 기반 문서 파싱 & 정합성 검증

SPEC.md 구현. 두 계층으로 나뉜다.

- **인스턴스 계층 (범용)** — 문서에서 값·관계·출처를 뽑은 fact. 도메인 지식이 없다.
- **제약 계층 (도메인 온톨로지)** — 그 fact 를 검증·해석하는 선언적 공리. **코드가 아니라 데이터.**

새 문서 종류 대응 = `ontology/*.yaml` 교체이지 코드 수정이 아니다.

## 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Part A — PDF → chunks.json
.venv/bin/python src/cli.py parse data/ss2207_special_trust.pdf -o out/ss2207.chunks.json

# Part B — chunks.json + 요약서 → reconcile.json
.venv/bin/python src/cli.py reconcile \
    data/golden_pairs/acct_001/contract.chunks.json \
    data/golden_pairs/acct_001/summary.md \
    -o out/acct_001.reconcile.json

# Part D — 질의 (임베딩 없음, 매 단계 설명 가능)
.venv/bin/python src/cli.py query out/ss2207.chunks.json "중도해지는 어떻게 하나요?"
.venv/bin/python src/cli.py query \
    data/golden_pairs/acct_001/contract.chunks.json "신탁금액이 얼마인가요?"

# 뷰어 — 파싱·온톨로지·대사·질의를 브라우저에서 (빌드 도구 불필요)
.venv/bin/python src/cli.py serve            # http://127.0.0.1:8000

.venv/bin/python -m pytest tests -q
```

도클링은 최초 실행 시 레이아웃 모델을 내려받는다(네트워크 필요).
오프라인이면 `~/.cache/huggingface` 를 미리 채워 두면 된다.

## 현재 상태 (ss2207_special_trust.pdf 기준)

| | 결과 |
|---|---|
| 파트 분리 | 약관본문 103 / 별지1_입력 82 / 별지2_변경 29 요소 |
| 조 복원 | **제1~32조 전부**, 누락·중복 0 |
| 청크 | 79개 |
| shape 위반 | **error 0**, warning 2 |
| 정본 대조 (§9-3) | **8/8** |
| 골든 정합성 (§B11) | **13/13 verdict 일치** |
| 테스트 | **95 passed** |

warning 2건은 「금융소비자 보호에 관한 법률」 **제46·47조** — 외부 법령 참조라
계약서 본문에 존재하지 않는 것이 정상이다. §9-7 이 "미해소 참조는 경고"로 규정한 그대로다.

## 모듈

```
ontology/trust_contract.ontology.yaml   ← 도메인 지식 전부 (제약 계층)
src/
  ontology.py        T14  로더 + 무결성 검사
  schema.py          T0   pydantic 모델 (facet-v1)
  recognizers.py     §7   구조 인식 어댑터 — 원문 → fact
  parse_stage.py     T1   born-digital 판별 + docling
  structure.py       T2-3 파트 분리 + 조/항/호 트리
  chunk.py           T4   청킹 (조 경계 불가침)
  tag_rules.py       T5   온톨로지 구동 태깅
  validate.py        T16  shape 검증
  emit.py            T7   직렬화
  fact.py            T8   Fact 레이어 (양쪽 공용)
  summary_parse.py   T9   요약서 파서
  mapping.py         T10  필드 매핑
  comparators.py     T11  value_type 별 비교기
  derive.py          §B7  파생식 해석 — 온톨로지 `derived` 를 계산 (대사·질의 공용)
  reconcile.py       T12  정합성 엔진
  reconcile_emit.py  T13  리포트
  query_router.py    T21  질의 정규화·분류 (Part D)
  fact_query.py      T22  fact 직조회 — 값 질문은 여기서 끝난다
  chunk_search.py    T23  facet 필터 + 렉시컬 + refs 확장 + small-to-big
  bootstrap.py            VLM 1차 스캔 → 온톨로지 초안 제안
viewer/                   정적 뷰어 (index.html + app.js) — npm 없음
tests/mutations/mutate.py T19  변이 정의 (테스트 자산 — src 에 두지 않는다)
```

## 설계에서 지킨 경계

**인식(recognition) ≠ 제약(constraint)** — §7
원문을 먹어 fact 를 만들면 recognizer(코드), 이미 뽑힌 fact 를 검사하면 제약(온톨로지).
어떤 recognizer 를 쓸지는 온톨로지가 고른다(`structure.조.recognizer: korean_article`).

**정규식은 구조 인식에만** — dataset 9종(3,460줄) 전수조사 근거
조 헤더 `^제N조(제목)` 352건 매칭에 오탐 1건(0.3%), 항 424건, 호 262건(9/9 문서).
반면 값 파싱에 쓰면 무너진다 — 금액 파서 오탐 80%, 기준일 추출 성공률 44%.
그래서 `comparators.py`·`fact.py` 는 문자 스캔으로 파싱하고 정규식을 쓰지 않는다.

**청킹 단위는 온톨로지가 정한다 — 토큰 예산은 폐기** — §D1, §C6
임베딩을 쓰지 않으므로 청크 크기 제약이 사라졌다. `structure.조.chunk: primary`,
`structure.항.chunk: split_if_long`, `structure.호.chunk: inline` 이 유일한 기준이며
코드에는 토큰 상수가 없다. §9-6 의 완료 기준도 "상한 이하"가 아니라
**"모든 경계가 의미 경계와 일치"** 로 바뀌었다(문장 중간 절단 금지).

**검색에 벡터 인덱스가 없다** — §D1~D3
`facet 필터 → 렉시컬 점수 → refs 1-hop → small-to-big` 네 단계 모두 재현 가능하고
왜 걸렸는지 출력한다. 형태소 분석기가 없어 조사가 붙은 어절은 접두 관계로 잇고
부분일치는 감점한다(`중도해지는` ↔ `중도해지`).
값 질문은 검색을 타지 않고 fact 표에서 바로 답한다 — `만기일` 처럼 문서에 없는 값은
`신탁기간.end` 로 **계산**해 근거와 함께 낸다.

**제약에는 근거와 출처가 붙는다** — §C12
필드마다 `cq`(어느 competency question 때문에 존재하는가)와
`provenance`(누가·언제·무엇을 근거로 승인했는가)를 단다. CQ 에 쓰이지 않는 제약은 만들지 않고,
리포트는 제약별 발화 횟수를 집계해 오래 침묵한 제약을 드러낸다.

**최종 판정은 코드 결정론** — §B3-3, §B11-5
LLM 은 판정에 관여하지 않는다. 애매하면 auto-pass/fail 하지 않고 `NEEDS_REVIEW` 로 뺀다.

**정답 문서 기준 순회** — §B3-2
요약서를 훑는 게 아니라 별지1 필드를 하나씩 돌며 요약서에 올바르게 있는지 본다.
누락·미매핑도 반드시 한 행으로 남긴다(조용한 스킵 금지).

## 구현하며 실측으로 드러난 것

1. **도클링이 `[별지1]` 을 `page_header` 로 분류한다.** 머리말을 버렸더니 별지1 파트를
   통째로 놓쳤다. → 파싱 단계는 버리지 않고 `furniture` 로 **표시만** 하고,
   무엇을 무시할지는 온톨로지를 아는 `structure.py` 가 정한다.
2. **병합 셀이 가로로 복제된다.** 체결본 골든 PDF 에서 7열 표의 값이 2~6열에 반복됐다.
   → `chunk._dedupe_row` 가 접는다.
3. **체크박스 그리드가 열 단위로 흩어진다.** 운용방법 1~24 가 24개 이상 요소로 쪼개지고
   중간에 주석이 낀다. → 연속 구간을 모으고 같은 필드끼리 병합한다.
4. **`금 일억원정 (₩100,000,000)` 을 2억으로 읽었다.** 같은 금액을 한글·아라비아로 두 번
   적는 서식 때문이다. → 콤마 표기가 있으면 그것만 쓴다.
5. **한국어 수사는 중첩된다.** `5천만` = 5 × 1000 × 10000. 단순 누적은 100,015,000 을 낸다.
   → 작은 단위는 그룹에 더하고 큰 단위(만·억·조)에서 그룹째 곱한다.
6. **도클링이 표를 요소 목록 맨 끝에 몰아서 낸다.** 별지1 의 표가 `[별지2]` 마커
   **뒤에** 도착한다. 파트를 읽기 순서로 흘리면 별지1 표가 통째로 별지2 로 새고,
   값이 표 안에 있는 체결본에서는 별지1 필드가 0 개가 된다. 빈 템플릿은 값이
   텍스트 요소로도 나와서 이 구멍이 가려졌다 — 테스트 89 개를 전부 통과했다.
   → 귀속을 지면 위치(page, y)로 바꿨다. 읽기 순서는 파트 **안에서만** 지킨다.
7. **파트 마커는 길이로 못 거른다.** `[별지1]에 기재된 금액` 같은 짧은 본문 참조가
   경계로 오인된다. → 마커로 **시작하고** 뒤가 제목 한 토막인 줄만 경계로 본다.
8. **변이 테스트가 죽은 제약을 찾아냈다.** 성과보수 요율을 15% → 12% 로 훼손했는데
   판정이 `MATCH` 그대로였다. `(연 3%)를 초과하는 이익 × (15)%` 에서 앞의 기준수익률만
   읽고 있었기 때문이다. → 한 값 안의 **모든** 비율을 순서대로 비교하도록 고쳤다.
   골든 쌍만으로는 영원히 안 드러났을 구멍이다(§C12.4 가 요구하는 이유).

## 남은 것

- **체크박스 √ 마크 검출** — 텍스트만으로는 불안정하다. 도클�이 √ 를 라벨과 분리해
  표 끝에 몰아넣는다. 좌표 기반 판정이 필요하며 §10 이 v2 로 미룬 항목이다.
  현재 `option_set` 비교는 골든 쌍의 `chunks.json`(체크 상태가 명시된 것)에서만 정확하다.
- **T6/T17 LLM 단계** — 구현했고 기본 off 다(`--llm-roles`, `--llm-axioms`).
- **CQ5(운용방법 → 위험고지)** — 추론 페이즈(§C11-3) 항목으로 아직 미구현이다.
  현재 리포트의 CQ 발화 집계에도 잡히지 않는다.
- **별지2 심층 파싱** — §10 범위 밖(표 골격까지만).
- **골든 쌍의 값은 합성이다.** 정합성 로직은 검증되지만 실제 문서에서의 추출 정확도는 아니다.
- **체결본 PDF → 별지1 값 추출은 아직 부분적이다.** 파트 귀속을 고친 뒤
  `contract_filled.pdf` 를 실제로 파싱해 대사하면 14 필드 중 4 개가 MATCH 다(고치기 전 0개).
  남은 실패는 파트가 아니라 **표 한 행 안의 라벨-값 페어링**이다.
  · 한 행에 두 필드가 같이 온다 — `[신탁보수 | 기본보수 | … | 수익보수 | …]` 를 아직 못 쪼갠다.
  · 스탬프된 값이 인쇄 문구 뒤에 붙는다 — `20 년 월 일부터 … 6 3 27 6 2`.
    좌표로 span 을 끼워 넣어야 하며, √ 검출(위 항목)과 같은 기계장치가 필요하다.
  대사 엔진·비교기 쪽이 아니라 recognizer 쪽 과제다.
