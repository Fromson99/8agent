# 로직 아키텍처 — trust_reconciler

> 목표는 두 단계다.
> **1단계** 계약서의 A섹션과 설명서의 B섹션이 *실제로 동일한 사안인가*
> **2단계** 그 섹션 안의 세부 요소 값이 *실제로 일치하는가*
>
> 이 문서는 그 두 단계를 어떤 구조로 구현했고, 왜 그렇게 정했는지를 실측 근거와 함께 적는다.

---

## 0. 한 장 조감도

```
                       ┌──────────────── 사용자가 선언하는 것 ────────────────┐
                       │ config/tag_schema.json   무엇을 태깅할 것인가        │
                       │   sections[]             메인 요소 (섹션의 의미)     │
                       │   sections[].elements[]  세부 요소 (그 안의 값)      │
                       │ config/glossary.json     용어집 (사용자 추가 + LLM)  │
                       │ config/mapping_table.json 표기 체계 매핑             │
                       └───────────────────┬─────────────────────────────────┘
                                           │ 주입
 ┌──────────┐                    ┌─────────▼─────────┐
 │ 계약서    │──파일────────────▶│ P1  파싱           │──▶ ParsedDocument
 │ pdf/docx  │                    │  docling          │      blocks[] (text/list_item/
 └──────────┘                    │  + pdfplumber 보완 │       section_header/table)
 ┌──────────┐                    │  [LLM 없음]       │      + 페이지·좌표·self_ref
 │ 설명서    │──파일────────────▶│                   │──▶ ParsedDocument
 └──────────┘                    └─────────┬─────────┘
                                           ▼
                                 ┌───────────────────┐
                                 │ P2  태깅           │──▶ TaggedDocument
                                 │  블록 → 메인 태그  │      sections[] = 같은 태그가 붙은
                                 │  섹션 → 세부 요소  │                   연속 블록 묶음
                                 │  [LLM]            │      elements[] = typed value
                                 └─────────┬─────────┘      + 스키마/용어집 추가 제안
                                           ▼
                        ┌──────────────────────────────────┐
                        │ P3  1단계 — 섹션 대응             │
                        │  ① 용어 겹침으로 후보 축소 [코드] │──▶ SectionPair[]
                        │  ② 애매한 쌍만 판정      [LLM]   │
                        └──────────────────┬───────────────┘
                                           ▼
                        ┌──────────────────────────────────┐
                        │ P4  2단계 — 값 비교               │
                        │  ① 구조화된 값끼리 비교   [코드]  │──▶ ElementComparison[]
                        │  ② 코드가 못 정한 것만   [LLM]   │
                        └──────────────────┬───────────────┘
                                           ▼
                    ┌───────────────────────────────────────┐
                    │ P5  완결성(설명서 단독) + 리포트 [코드] │
                    └──────────────────┬────────────────────┘
                                       ▼
                     report.json (SCS 연동) / report.md (메일 본문)
```

---

## 1. 왜 정규표현식을 전부 제거했나 — 실측 근거

이전 구현은 조항 경계·금액·기간·기준일을 전부 정규식으로 뽑았다.
dataset 9종(3,460줄)에 전수조사를 돌린 결과가 설계를 바꿨다.

| 대상 | 실측 | 진단 |
|---|---|---|
| 금액 파서 | 442건 중 **356건(80.5%) 오탐** | `「소득세법」 제14조제3항제6호` 의 '조'를 4조원(4,000,000,000,000)으로 읽음 |
| 기준일 추출 | 9종 중 **4종(44%)만 성공** | 회사마다 표기가 달라 패턴을 늘려도 다음 문서에서 깨짐 |
| 기준일 패턴 6개 중 3개 | **0회 매칭** | 근거 없이 상상해서 넣은 것 |
| `제N편/장/절` 패턴 | **0회 매칭** | dataset 에 없는 문법을 넣음 |
| 조항 제목 인식 | 유안타 계약서에서 시각 신호 **0** | 제목이 본문과 동일 (10pt, 같은 폰트, 같은 들여쓰기) |

패턴 하나를 고치면 다음 회사 문서에서 또 깨진다. 이건 패턴의 문제가 아니라 **접근의 문제**였다.

### 대체 원칙 — 추출은 LLM, 비교는 코드

```
문자 ──[LLM]──▶ 구조화된 값 ──[코드]──▶ 판정
"연 0.5%"      {"value":0.5,           match / mismatch / uncertain
               "per_annum":true}
```

LLM 은 `제14조제3항`을 금액으로 착각하지 않는다. 반대로 `36개월 == 3년` 같은 판정은
코드가 해야 재현 가능하고 감사할 수 있다. 그 경계가 [units.py](first-agent/trust_reconciler/units.py) 다.

### 회귀 방지

[test_pipeline.py](first-agent/trust_reconciler/tests/test_pipeline.py) 의 `test_no_regex_in_production_code` 가
프로덕션 코드에 `import re` 나 `re.compile` 이 다시 들어오면 실패한다. **현재 0건.**

---

## 2. P1 파싱 — 도클링이 하는 일과 하지 않는 일

```
parsers.parse(file, doc_role)
  │
  ├─ .pdf  ─▶ docling (do_ocr=False, do_table_structure=True)
  │            texts  → DocBlock(kind=text|list_item|section_header)
  │            tables → DocBlock(kind=table, 셀 구조 보존)
  │            머리말/꼬리말은 버린다 (페이지마다 반복되어 태깅을 방해)
  │            표가 0개면 ─▶ pdfplumber 로 보완
  ├─ .docx ─▶ zipfile + XML, w:pStyle 로 제목 판정 (문자열 연산)
  └─ .md/.txt ─▶ '#' 헤딩, '|' 표 (str 메서드)
```

### 도클링 설정 근거 (실측)

| 설정 | 근거 |
|---|---|
| `do_ocr=False` | 텍스트 레이어가 있는 PDF 에 OCR 을 돌리니 **39초 → 6초**, 그리고 꼬리말에 `A 是 ! sxuanties (Korea)` 같은 쓰레기가 생겼다. 텍스트가 안 나오는 문서만 OCR 로 재시도한다. |
| `do_table_structure=True` | 계약서의 실제 값은 별지 세부내역서(표)에 있다. |
| pdfplumber 보완 | 유안타 계약서에서 도클링 `tables=0` — 별지1을 놓쳤다. pdfplumber 가 5개를 복구했다. |

### 도클링이 해 주지 못하는 것

| 문서 | `section_header` | `tables` |
|---|---|---|
| 유안타 계약서 | 33개 조항 중 **6개** | **0** (pdfplumber 가 5개 보완) |
| 하나은행 ISA | 78 | 2 |
| 부산은행 설명서 | 11 | 7 |

유안타 계약서는 조항 제목이 본문과 시각적으로 완전히 동일해서 **원본에 계층 정보가 없다.**
어떤 레이아웃 모델도 조항 경계를 그어 줄 수 없다.

**그래서 섹션 경계를 파서에 기대지 않는다.**

---

## 3. P2 태깅 — 섹션은 여기서 만들어진다

```
섹션 = 같은 메인 태그가 붙은 "연속" 블록들
```

이 정의가 계층 문제를 우회한다. 사용자가 지적한 `3.2.1 지급시기` vs `4.1.1 지급시기` 문제 —
제목이 같아도 태깅은 **본문 내용**을 보므로 하나는 `trust_fee`, 다른 하나는
`early_termination_fee` 가 된다. 계층 복원이 필요 없다.

```
for 블록 배치(60개씩):
    llm.tag_blocks({blocks, schema.sections, glossary})
        → assignments[]          블록 → 태그, 확신도, 근거
        → suggestions[]          선언에 없지만 대사할 가치가 있는 사안
        → glossary_suggestions[] 새로 발견한 용어 표현

연속 블록 묶기 → TaggedSection[]
    · 떨어진 같은 태그는 합치지 않는다.
      제11조의 보수율과 별지1의 보수율을 뭉치면 출처를 잃는다. 1:N 대응은 P3 가 처리.
    · 확신도는 구간 내 최댓값 (한 블록이라도 분명하면 그 섹션은 분명하다)

섹션마다:
    llm.extract_elements({text, schema.elements, value_types, glossary})
        → typed value
```

### 사용자 선언 스키마 — 2계층

```jsonc
{
  "sections": [{                          // ← 메인 요소: 1단계 대상
    "id": "trust_fee", "display": "신탁보수",
    "scope": "both",
    "required_in_statement": "always",    // 또는 {"product_type_in": ["ELS편입"]}
    "hints": ["신탁보수", "기본보수", "보수율"],
    "confusable_with": ["front_end_fee", "early_termination_fee"],
    "elements": [                         // ← 세부 요소: 2단계 대상
      {"id": "rate",    "value_type": "percent", "key": true},
      {"id": "formula", "value_type": "formula", "key": true},
      {"id": "timing",  "value_type": "text"}
    ]
  }]
}
```

- `hints` 는 참고일 뿐 정답이 아니다. 없어도 태깅되고, 있으면 정확도가 오른다.
- `key: true` 인 요소의 불일치는 심각도 **high**.
- 프론트에서 사용자가 고른 태그만 보려면 `--tags trust_fee,trust_period`.
- **선언에 없는데 문서에 있는 것**은 버리지 않고 리포트의 "스키마 추가 제안"에 올린다.

---

## 4. P3 1단계 — "실제로 동일한 부분인가"

```
① 후보 축소 [코드]  ── 전수 조합을 피한다
     같은 태그이거나 용어를 공유하는 조합만 후보
     섹션이 각각 40개면 전수는 1,600쌍 — LLM 에 다 물을 수 없다

② 통과 규칙 [코드]
     같은 태그 + 양쪽 확신도 ≥ 0.85  →  LLM 확인 없이 ok (비용 절감)
     그 외                            →  LLM 판정

③ llm.pair_sections({candidates, glossary})
     same / confidence / evidence
     confidence < 0.70 → flag="uncertain" (사람 확인 대상)
     1:N 대응 지원 (계약서 여러 조항 ↔ 설명서 한 문단)

④ 짝을 못 찾은 섹션도 남긴다 → flag="contract_only" / "statement_only"
     단, scope 가 statement_only 인 태그(연계·제휴 등)는 정상이므로 제외
```

용어집이 여기서 비용을 통제한다. 용어가 하나도 안 겹치는 조합은 애초에 LLM 을 안 부른다.

---

## 5. P4 2단계 — "실제로 값이 일치하는가"

```
대응된 섹션 쌍 안에서, 같은 element_id 끼리:

units.compare(value_type, 계약서 data, 설명서 data, mapping)
   │
   ├─ match     ──▶ 끝
   ├─ mismatch  ──▶ 끝
   └─ uncertain ──▶ llm.compare_values(...)   ← text/formula/enum/ref 만
                       └ 섹션 대응이 불확실하면 mismatch 를 uncertain 으로 강등
```

### 타입별 비교 (전부 dict 접근, 문자열 재파싱 없음)

| value_type | 비교 방식 | 예 |
|---|---|---|
| `duration` | 총 개월로 환산 | `{"years":3}` == `{"months":36}` |
| `percent` | 값 + 연환산 여부. 값이 같아도 연율 표기가 다르면 **uncertain** | `연 0.5%` vs `0.5%` |
| `money` | 정수 + 통화 | `{"amount":100000000}` |
| `date` | ISO 문자열 | `2024-06-03` |
| `boolean` | 참/거짓 | 예금자보호 여부 |
| `enum` | mapping_table 로 코드 통일 | `2등급` == `높은위험` → `G2` |
| `formula` | 피연산자·연산자 **다중집합** | 순서가 달라도 같은 산식 |
| `ref` | 항상 uncertain | 양쪽 다 "별지1 참조"면 값을 본 게 아니다 |
| `text` | 완전일치 아니면 LLM | |

### 안전장치 — 강등 규칙

**잘못 짝지은 두 섹션을 비교하면 반드시 "불일치"가 나온다.**
그 불일치를 그대로 리포트하면 담당자가 없는 문제를 쫓는다.
그래서 `pair.flag == "uncertain"` 이면 mismatch 를 uncertain 으로 내린다.

---

## 6. LLM 호출 지점 — 5개, 전부 JSON 계약

| 호출 | 언제 | 프롬프트 |
|---|---|---|
| `doc_meta` | 발행사·기준일·상품유형 (정규식 44% → LLM) | `prompts/doc_meta.txt` |
| `tag_blocks` | 블록 → 메인 태그 (= 섹션 형성) | `prompts/tag_blocks.txt` |
| `extract_elements` | 섹션 → 세부 요소 typed value | `prompts/extract_elements.txt` |
| `pair_sections` | 1단계 대응 판정 | `prompts/pair_sections.txt` |
| `compare_values` | 2단계, 코드가 못 정한 것만 | `prompts/compare_values.txt` |

모든 프롬프트가 **"확신이 없으면 uncertain, 추측 금지"** 를 명시한다.
금융 도메인에서는 틀린 확신보다 정직한 uncertain 이 낫다.

### 재현성 — 스냅샷

LLM 은 같은 입력에 다른 답을 낼 수 있다. "어제는 일치, 오늘은 불일치"는 감사 사고다.

```
키 = sha256(호출종류 + 프롬프트 내용 + 입력 페이로드 전체)

1회차  키가 있을 때 실행 → snapshots/<case>.json 에 전부 기록
2회차  스냅샷 재생 → 결과 고정, API 키 없이도 동일 리포트
감사   사람이 스냅샷 JSON 을 고치면 그게 정답이 된다
```

프롬프트를 수정하면 지문(fingerprint)이 달라져 자동으로 재호출된다 — 낡은 판정이 남지 않는다.

**스냅샷에 없고 키도 없으면 `LLMUnavailable` 로 명확히 멈춘다.**
가짜 판정을 지어내 리포트에 싣지 않는다.

---

## 7. 용어집 — 사용자 추가 + LLM 추천

```jsonc
{ "canonical": "trust_fee", "display": "신탁보수", "value_type": "percent",
  "surfaces": ["신탁보수", "기본보수", "보수율", "운용보수"],
  "confusable_with": ["front_end_fee", "early_termination_fee"],
  "source": "user" }        // user 우선 | llm 제안 | seed 초기값
```

- P2 태깅 중 LLM 이 새 표현을 발견하면 `source: "llm"` 으로 파일에 쌓인다.
- 리포트의 "용어집 추가 제안"에 올라오고, 사람이 `source` 를 `user` 로 바꾸면 확정.
- **`source: "user"` 항목은 LLM 이 절대 덮어쓰지 못한다.**
- P3 후보 축소에 쓰여 LLM 호출 수를 줄인다.

---

## 8. 파일 구성

```
trust_reconciler/
  textkit.py       유니코드·공백·JSON 추출  (str 메서드 + unicodedata, regex 없음)
  docmodel.py      DocBlock / TaggedSection / SectionPair / ElementComparison / Report
  parsers.py       P1 — docling + pdfplumber 보완 + docx/txt
  pipeline.py      P2 태깅 · P3 1단계 · P4 2단계
  units.py         구조화된 값 비교 (2단계의 판정 엔진)
  glossary.py      용어집 로드·조회·LLM 제안 흡수
  cache.py         스냅샷 저장소 (재현성)
  report.py        완결성 검증 + 리포트(JSON/마크다운)
  main.py          오케스트레이션 + CLI
  llm/client.py    Anthropic / Snapshot / Recording 백엔드
  llm/prompts/     5종
  config/
    tag_schema.json     ← 사용자 선언 (메인·세부 2계층)
    glossary.json       ← 사용자 추가 + LLM 추천
    mapping_table.json  ← 표기 체계 매핑
```

---

## 9. 현재 상태와 남은 것

**동작 확인됨**
- P1 파싱: PDF(도클링) / DOCX / MD / TXT 4형식, dataset 9종
- units / glossary / textkit / cache / report: 61개 테스트 통과
- 정규식 0건 (회귀 테스트로 고정)

**API 키가 필요한 부분**
- P2~P4 는 LLM 호출이 있어야 실제로 돈다. 현재 스냅샷이 비어 있으므로
  `ANTHROPIC_API_KEY` 를 설정하고 한 번 실행해야 `snapshots/` 가 채워진다.
- 테스트는 FakeClient(테스트 더블)로 로직을 검증한다. 프로덕션 코드에는
  "LLM 흉내내는 휴리스틱"을 두지 않았다 — 가짜 판정이 리포트에 실리면 안 되기 때문이다.

**아직 안 한 것**
- 실물 문서에 대한 태깅 품질 측정 (키가 있어야 가능)
- 변경대비표 시나리오 (`authority="change_table"` 스위치만 있음)
- 메일·SCS 연동 (`main.deliver()` 페이로드 스텁만)
