# 설계 — SPEC.md 기반 재설계

> SPEC.md(지시사항서)와 `trust_contract_chunks_sample.json`(정본)을 기준으로 다시 설계한 문서.
> 기존 `first-agent/trust_reconciler` 구현과의 차이, 재사용/폐기 판단, 그리고
> 실측 데이터로 판정한 설계 쟁점을 담는다.

---

## 0. SPEC 과 기존 구현의 차이

| | 기존 (`trust_reconciler`) | SPEC.md |
|---|---|---|
| 태깅 방식 | LLM 이 선언된 태그 중 선택 | **규칙 기반 결정론**. LLM 은 `--llm-roles` 뒤 옵션 |
| 정규표현식 | 전면 금지 (실측으로 제거) | **핵심 도구** (§7 에 패턴 명시) |
| 태그 구조 | `sections[] → elements[]` 트리 | **직교 2축 facet**: `role` × `topic` |
| 정답 기준 | 계약서 전체 | **별지1 필드 집합만** (본문 조항은 규칙이지 값이 아님) |
| 비교 방식 | 큰 요소 대응 → 세부 요소 비교 | **양쪽을 Fact table 로 투영 후 대조** (직접 비교 금지) |
| 필드 매핑 | 태그 일치 | normalize → exact → `aliases.yaml` → UNMAPPED |
| 판정 | match / mismatch / uncertain | **5종**: MATCH / VALUE_MISMATCH / MISSING_IN_SUMMARY / UNMAPPED / NEEDS_REVIEW |
| 산출물 | `report.json` | `{stem}.chunks.json` + `{stem}.reconcile.json` |
| 청킹 | 블록 → 태그 섹션 | Docling HybridChunker, 256–512 토큰, 조 경계 불가침 |

가장 큰 방향 전환은 두 가지다.

1. **"LLM 이 의미를 판정한다" → "규칙이 의미를 판정하고 LLM 은 보조"**
2. **"두 문서를 맞대 본다" → "각각 Fact 로 투영한 뒤 표에서 대조한다"**

---

## 1. 설계 쟁점 — 정규표현식을 다시 쓰는 것이 맞는가

기존 구현에서 나는 정규식을 **전부 제거**했다. 근거는 dataset 9종(3,460줄) 전수조사였다.
SPEC §7 은 정규식을 핵심 도구로 쓴다. 정면으로 충돌하는 것처럼 보인다.

그런데 내 감사 데이터를 다시 보면 **충돌이 아니다.** 무너진 패턴과 견고한 패턴이 갈린다.

### 견고했던 패턴 — SPEC 이 쓰라는 것들

| 패턴 | 매칭 | 오탐 | 문서 커버리지 |
|---|---:|---:|---|
| `^제N조(제목)` 조 헤더 | 352건 | **1건 (0.3%)** | 7/9 |
| 항 번호 `①②③` | 424건 | — | 7/9 |
| 호 번호 `1. 2.` | 262건 | — | **9/9** |
| `[별지N]` / `[별표N]` | 33건 | — | 7/9 |
| 상호참조 `제N조` | 612건 | — | 8/9 |

조 헤더 정규식의 오탐 1건은 `"제8조 제1항 또는 제2항에서 정한 신탁보수와…"` 처럼
**줄 첫머리에 온 조항 인용**이었다. 인용 배제 규칙 하나로 잡힌다.

### 무너진 패턴 — SPEC 이 정규식으로 하지 말라는 것들

| 패턴 | 결과 |
|---|---|
| 금액 파서 | 442건 중 **356건(80.5%) 오탐**. `「소득세법」 제14조제3항제6호` 의 '조'를 4조원으로 읽음 |
| 기준일 추출 | 9종 중 **4종(44%)만 성공**. 6개 패턴 중 3개는 0회 매칭 |
| 시각 신호 제목 판정 | 유안타 계약서에서 신호 0 (제목이 본문과 동일 서식) |

### 결론 — 경계선

```
구조·참조 인식   조 / 항 / 호 / 별지 / 상호참조     → 정규식.  오탐 0.3%
값 파싱·정규화   금액 / 기간 / 날짜 / 비율          → 정규식 금지. 타입별 파서 + LLM 보조
문서 메타        발행사 / 기준일 / 상품유형          → LLM (정규식 44%)
값 비교          Fact 대 Fact                       → 코드 결정론 (§B7 비교기)
```

**기존 구현의 "정규식 전면 금지"는 과잉 반응이었다.**
값 파서가 무너진 것을 구조 파서까지 확대 적용했다. SPEC 의 분리가 옳고, 내 감사 데이터가 그것을 뒷받침한다.

다만 회귀 테스트는 유지한다 — 방향만 바꾼다.
`정규식 0건` 검사 대신, **값 파싱 경로에 정규식이 들어오면 실패**하는 검사로 바꾼다.
(`fact.py` / `comparators.py` 는 정규식 금지, `structure.py` / `tag_rules.py` 는 허용)

---

## 2. 데이터 모델 — 직교 2축 facet

정본 `trust_contract_chunks_sample.json` 구조를 그대로 재현한다.

```
Chunk
  chunk_id            body-a15-p1 | app1-field-amount
  role                약관본문 | 별지1_입력 | 별지2_변경        ← 축 1: 문서 파트
  topic               중도해지(제15조)                          ← 축 2: 의미 (조 앵커)
  level               조 | 항 | 호 | 필드 | 표
  article             제15조
  article_title       중도해지
  clause              ① (선택)
  heading_path        [파트, 조, 항]
  refs                [제3조, 제12조, 별지1]
  cross_ref_explicit  계약서제15조 (별지 전용)
  provenance          {page, bbox}
  text                원문
  items[]             호 리스트 (선택)
  options[]           체크박스 그리드 (선택)
  table_options[]     다단 조건 표 (선택)
  value_template      "금 ______ 원정" (선택)
```

**왜 트리가 아니라 2축인가**: 같은 `topic`(예: 신탁금액(제2조))이 본문에도 별지1에도 나타나며
`role`만 다르다. 트리로 만들면 같은 개념이 두 갈래로 찢어진다.
2축이면 `topic` 하나로 본문 규정과 별지 값이 자연히 묶인다 —
이것이 Part B 에서 "값(별지1) ↔ 규칙(본문)" 을 연결하는 축이 된다.

이 구조는 내가 앞서 도입한 `role`(provision/value/explanation) 개념과 같은 문제의식이고,
SPEC 쪽이 더 정확하다. 별지 표의 `계약서제N조` 열이 **문서 자체에 명시된 링크**라
추론이 아니라 읽기만 하면 되기 때문이다.

---

## 3. Part A — PDF → chunks.json

```
T1 Parse         PyMuPDF 로 born-digital 판별 → Docling 변환 (OCR off)
   [결정론]      elements[] {type, text, page, bbox, reading_order}
                 별지 표는 셀 구조 보존. 실패 시 페이지 단위로 폴백 기록
                     ↓
T2 Part split    [별지1] / [별지2] 마커로 본문·별지1·별지2 분리 → role 확정
   [정규식]
                     ↓
T3 Structure     조 → 항 → 호 트리 복원, heading_path 생성
   [정규식]      조 헤더: ^제(\d+)조\(([^)]+)\)   ← 인용 배제 규칙 포함
                 항: 원문자 U+2460~U+2473
                 호: ^\s*(\d+)\.\s
                     ↓
T4 Chunk         본문: 조 단위 기본, 긴 조는 항 단위 (조 경계 불가침)
                 별지: 표/필드/체크박스 단위
                 HybridChunker 로 256–512 토큰 정제
                     ↓
T5 Tag           role ← 파트
   [규칙]        article / article_title / topic ← 조 헤더 (결정론적 조합)
                 level ← 파싱 위치
                 refs ← 정규식 추출 후 실재 조/별지로 resolve
                 별지 cross_ref_explicit ← 표 우측 `계약서제N조` 셀
                     ↓
T6 LLM (선택)    --llm-roles 플래그. 고정 enum + structured output.
   [기본 off]    세부 의미역 보강만. 기본 비활성.
                     ↓
T7 Emit          pydantic 검증 → {stem}.chunks.json
```

### 도클링 설정 — 실측 근거 (기존 구현에서 확보)

| 설정 | 근거 |
|---|---|
| `do_ocr=False` | 텍스트 레이어 있는 PDF 에 OCR → 39초 → 6초, 꼬리말에 `A 是 ! sxuanties (Korea)` 쓰레기 |
| `do_table_structure=True` | 계약서 값은 별지 표에 있다 |
| pdfplumber 폴백 | 유안타 계약서에서 도클링 `tables=0` (별지1 놓침). pdfplumber 가 5개 복구 |

SPEC §5 는 별지 표가 약하면 PP-StructureV3 폴백을 제안한다.
pdfplumber 폴백이 이미 작동하므로 **1차는 pdfplumber, 그래도 실패하면 PP-StructureV3** 순서로 둔다.

### 알려진 난점

- 도클링 `section_header` 인식률이 낮다 (유안타 33개 조항 중 6개).
  → **문제되지 않는다.** T3 는 시각 신호가 아니라 텍스트 정규식으로 조 헤더를 잡는다.
- 병합 셀 별지 표: 셀 구조가 깨지면 실패 로그 + 해당 페이지만 폴백 (SPEC §7).

---

## 4. Part B — chunks.json + 요약서 → reconcile.json

```
                 계약서 chunks.json                 요약서 PDF
                 (role=별지1_입력 만)                     │
                        │                          T9 요약서 파서
                        │                          (Docling 재사용 + 규칙, 흔들리는 곳만 LLM)
                        ▼                                ▼
                 T8 Fact 추출 ─────────────────────── T8 Fact 추출   ← 같은 레이어 재사용
                 Fact{field_name, topic, value_type, value, raw, source}
                        │                                │
                        └──────────┬─────────────────────┘
                                   ▼
                        T10 필드 매핑
                        normalize → exact → aliases.yaml → UNMAPPED
                                   ▼
                        T11 값 비교기 (value_type 별)
                        number / date / date_range / percent /
                        range_tiers / option_set / account_no / text
                                   ▼
                        T12 Reconciliation 엔진
                        **별지1 Fact 를 기준으로 순회** (방향성: 계약서 = 정답)
                                   ▼
                        T13 {stem}.reconcile.json
```

### 왜 직접 비교하지 않고 Fact 로 투영하나 (§B3-1)

기존 구현은 "계약서 섹션 ↔ 설명서 섹션"을 직접 맞댔다. 그 결과:
- 설명서의 `신탁보수` 한 문단이 계약서의 `선취보수`·`중도해지수수료` 섹션과도 쌍을 이뤄
  **가짜 불일치 3건**이 났다 (21쌍 → 태그별 묶기로 14쌍으로 줄여 부분 해결).

Fact 로 투영하면 이 문제가 구조적으로 사라진다. 비교는 `{field → 값}` 표에서만 일어나고,
문서 레이아웃이 개입하지 않는다.

### 판정 5종과 그 이유 (§B8)

| verdict | 뜻 | 사람이 취할 조치 |
|---|---|---|
| `MATCH` | 매핑됐고 값 일치 | 없음 |
| `VALUE_MISMATCH` | 매핑됐으나 값 다름 | **요약서 수정** |
| `MISSING_IN_SUMMARY` | 별지1엔 있으나 요약서에 없음 | **요약서에 추가** |
| `UNMAPPED` | 이름으로도 alias 로도 못 찾음 | `aliases.yaml` 보강 |
| `NEEDS_REVIEW` | 추출·매핑이 애매 | 담당자 판단 |

`VALUE_MISMATCH` 와 `MISSING_IN_SUMMARY` 를 뭉개면 조치가 달라지므로 반드시 구분한다.
`UNMAPPED` 는 시스템 결함(별칭 부족)이지 문서 결함이 아니다 — 이것도 구분한다.

### 오탐 vs 미탐 (§B3-4)

> 오탐은 줄이되 진짜 불일치는 절대 놓치지 않는다. 상충하면 후자를 우선한다.

구현상 의미: 애매하면 `MATCH` 로 넘기지 않고 `NEEDS_REVIEW` 로 뺀다.
`NEEDS_REVIEW` 가 늘어나는 것은 허용, 놓침은 불허.

---

## 5. 기존 자산 재사용 판단

| 자산 | 처리 | 이유 |
|---|---|---|
| `parsers.py` 도클링 어댑터 | **재사용** | OCR off / table on / pdfplumber 폴백이 실측으로 검증됨 |
| `textkit.py` | **재사용** | 유니코드·공백 정규화, 괄호 세기 JSON 추출 |
| `units.py` | **확장 후 재사용** → `comparators.py` | duration/percent/money/date/enum/formula/boolean 이미 있음. `range_tiers`, `option_set`, `account_no`, `date_range` 추가 |
| `cache.py` 스냅샷 | **재사용** | `--llm-roles` 켤 때 재현성 |
| `env.py` | **재사용** | `.env` 로더 |
| `glossary.py` + `config/glossary.json` | **교체** → `config/aliases.yaml` | SPEC §B6 포맷 (별지1 정규필드 → 요약서 별칭들, 다대일) |
| `config/tag_schema.json` | **폐기** | facet 2축 + 조 헤더 규칙으로 대체. 선언이 필요없어짐 |
| `pipeline.py` (LLM 태깅) | **폐기** | 규칙 기반 태깅으로 대체 |
| `docmodel.py` | **재작성** | Chunk 스키마 (pydantic) |
| `report.py` | **재작성** | reconcile 리포트 스키마 (§B9) |
| `frontend/` 뷰어 | **개조 후 유지** | 화면 구성을 chunks / facts / reconcile 로 교체. 레일·팔레트·컴포넌트는 그대로 |

### 저장소 구조

```
trust-parser/
  data/
    ss2207_special_trust.pdf             ← 없음 (§7 참조)
    trust_contract_chunks_sample.json    ← 정본 (있음)
    golden_pairs/                        ← 없음 (§7 참조)
  config/
    aliases.yaml
  src/
    schema.py          pydantic 모델 (Chunk, Fact, ReconcileRow)
    parse_stage.py     T1  도클링 + born-digital 판별   [기존 parsers.py 이식]
    structure.py       T2-T3 파트 분리 + 조/항/호 트리   [정규식 허용 구역]
    chunk.py           T4  청킹 + HybridChunker
    tag_rules.py       T5  규칙 태깅                     [정규식 허용 구역]
    tag_llm.py         T6  (선택) LLM 세부 역할
    emit.py            T7  검증·직렬화
    fact.py            T8  Fact 추출 (양쪽 공용)         [정규식 금지 구역]
    summary_parse.py   T9  요약서 파서
    mapping.py         T10 필드 매핑
    comparators.py     T11 value_type 별 비교기          [정규식 금지 구역]
    reconcile.py       T12 정합성 엔진
    reconcile_emit.py  T13 리포트 출력
    cli.py
  tests/
    test_golden.py            §9  Part A 완료기준
    test_reconcile_golden.py  §B11 Part B 완료기준
    test_no_regex_in_value_layer.py   경계선 회귀 테스트
```

---

## 6. LLM 사용 지점 — 기본 off

SPEC 은 LLM 을 최소화한다. 기존 구현(문서 해석 전부 LLM)에서 크게 줄어든다.

| 지점 | 기본 | 근거 |
|---|---|---|
| T6 세부 의미역 태깅 | **off** | role/topic/refs 는 조 헤더·정규식으로 결정론적으로 나옴 |
| T9 요약서 값 추출 | **부분 on** | 요약서는 "어느 정도 고정된 양식". 규칙 우선, 흔들리는 곳만 |
| 최종 판정 | **금지** | §B3-3, §B11-5. 자릿수 누락·환각 위험 |

LLM 을 쓰는 경우 `cache.py` 스냅샷으로 고정해 재현성을 지킨다.

---

## 7. 막힌 것 — 입력 데이터

SPEC 의 완료 기준을 **지금 검증할 수 없다.**

| 필요한 것 | 상태 |
|---|---|
| `ss2207_special_trust.pdf` (Part A 1차 테스트 입력) | **없음** |
| 값이 채워진 (체결 계약서, 요약서) 골든 쌍 (Part B) | **없음** |
| `trust_contract_chunks_sample.json` (정본) | 있음 |
| `first-agent/dataset/` 실물 9종 | 있음 — 단, **전부 빈 템플릿**이고 요약서와 짝이 아님 |

영향:
- §9 완료기준 3·4·5 (정본 6개 레코드 구조 일치, 제15조① refs, 별지1 링크) → 검증 불가
- §B11 전부 → 검증 불가

우회 방안:
1. **Part A 구조 검증은 dataset 으로 가능하다.** 유안타·미래에셋·KB·하나 계약서로
   조/항/호 인식률, 별지 링크 추출률을 측정할 수 있다. 정본과의 구조 일치만 못 본다.
2. **골든 쌍은 합성으로 만들 수 있다.** 기존 `case_a` 픽스처를 만든 방식대로,
   값이 채워진 체결본 + 짝이 되는 요약서를 작성한다. 다만 이건 실물 검증이 아니다.

---

## 8. 착수 순서

```
0. 스캐폴딩 + pydantic 스키마 (정본 JSON 구조 그대로)
1. T1  도클링 파싱  [기존 parsers.py 이식]        → dataset 4종으로 즉시 확인
2. T2  파트 분리                                  → 별지1/별지2 경계 정확도 측정
3. T3  조/항/호 트리                              → 조 누락 0 확인
4. T5  규칙 태깅 (T4 앞에 둠 — 태그가 청킹 경계를 정함)
5. T4  청킹 + 토큰 예산
6. T7  검증·출력 → chunks.json
   ── 여기서 Part A 완료. 정본 대조는 입력 PDF 확보 후.
7. T8  Fact 레이어  [기존 units.py 확장]
8. T11 비교기 (단위 테스트 먼저)
9. T10 매핑 + aliases.yaml
10. T9 요약서 파서
11. T12-13 엔진 + 리포트
12. 프론트 개조
```

T5 를 T4 앞에 둔 것은 SPEC 순서와 다르다. 조 헤더 태깅이 끝나야
"조 경계를 넘지 않는 청킹"(§9-2)을 보장할 수 있기 때문이다.
