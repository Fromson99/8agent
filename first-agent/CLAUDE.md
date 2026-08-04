# 1번 과제 아키텍처 설계 — 신탁계약서 ↔ 핵심상품설명서 대사

> **이 문서의 용도**: Claude Code에 전달하여 PoC 구현에 착수하기 위한 아키텍처 명세.
> 사람이 보는 개념도가 아니라, 모듈 경계 / 데이터 계약(스키마) / 처리 순서 / 인터페이스를 구현 가능한 수준으로 규정한다.
>
> **범위**: 신규 계약 시나리오(계약서 ↔ 상품설명서 대사)의 PoC. 변경대비표 시나리오는 확장 지점만 표시.

---

## 0. 설계 원칙 (RFP 제약 반영)

1. **모듈별 개발 + Agent to Agent 호환** (RFP 요구) — 각 단계를 독립 모듈로, 입출력을 JSON 계약으로 고정. 단계 교체·재사용 가능하게.
2. **RAG 미사용** — 벡터 검색 없음. LLM은 "항목 추출"과 "의미 동등성 판정"에만 사용. 나머지는 결정론적(deterministic) 코드.
3. **외부 솔루션 반입 불가** — PoC는 표준 라이브러리 + LLM API 호출로만. 특정 벤더 솔루션 의존 금지.
4. **정답 문서 개념 고정** — 신규 계약: 계약서가 정답(source of truth). 변경: 변경대비표가 정답. `authority` 파라미터로 주입.
5. **검증 두 종류 분리** — (a) 완결성(설명서 단독 필수항목 존재) / (b) 정합성(양 문서 값 일치). 별도 모듈, 별도 리포트.
6. **모든 판정에 근거·확신도** — 각 대사 결과에 출처 위치(문서·조항)와 confidence를 남겨 사람이 검증 가능하게 (금융 도메인 필수).

---

## 1. 파이프라인 개요 (모듈 흐름)

```
[계약서 파일] [설명서 파일] [필수항목 정의(주입)]
        │           │              │
        ▼           ▼              │
   ┌─────────────────────┐         │
   │ M1. Ingest & Parse  │  문서 → 정규화된 블록(텍스트/표/참조)
   └─────────────────────┘         │
        │                          │
        ▼                          │
   ┌─────────────────────┐         │
   │ M2. Item Extractor  │  각 문서에서 항목 단위로 값 추출
   │   (참조 해석 포함)   │  (LLM + 규칙)
   └─────────────────────┘         │
        │                          │
        ├──────────────┬───────────┘
        ▼              ▼
   ┌──────────┐  ┌──────────────────┐
   │ M3. 완결성 │  │ M4. Item Matcher  │  계약서항목 ↔ 설명서항목 대응
   │ 검증(a)   │  │  (의미 매칭, 1:N) │
   └──────────┘  └──────────────────┘
        │              │
        │              ▼
        │        ┌──────────────────┐
        │        │ M5. Reconciler    │  매칭쌍의 값 일치/불일치 판정
        │        │  (정규화+동등성)   │  (규칙 → LLM 폴백)
        │        └──────────────────┘
        │              │
        ▼              ▼
   ┌─────────────────────────────┐
   │ M6. Report Builder          │  완결성 + 정합성 통합 리포트
   └─────────────────────────────┘
        │
        ▼
   [불일치/미비 리포트 (JSON + 사람용 요약)]
```

---

## 2. 모듈 명세

각 모듈은 순수 함수처럼 `입력 JSON → 출력 JSON`. 상태 없음. 개별 테스트 가능.

### M1. Ingest & Parse
- **책임**: 파일(PDF/DOCX)을 구조화된 블록으로 변환. 표는 표 구조 유지, 조항 번호·별지/별표 태깅.
- **입력**: 파일 경로, `doc_role`("contract" | "product_statement")
- **출력**: `ParsedDoc` (§3.1)
- **처리**:
  - PDF → 텍스트 + 표 추출 (표는 셀 구조 보존 — 케이스 5 대응)
  - 조항/별지/별표 경계 식별 → 각 블록에 `location` 부여
  - 표는 `blocks[].type="table"`, 서술은 `type="prose"`로 구분
- **비-LLM** (파싱은 결정론적). 표 추출 실패 시 flag.

### M2. Item Extractor
- **책임**: `ParsedDoc`에서 "항목(item)" 단위로 값을 뽑음. 참조 해석 포함.
- **입력**: `ParsedDoc`, `item_catalog`(추출 대상 항목 정의, §3.4)
- **출력**: `ExtractedItem[]` (§3.2)
- **처리**:
  - 각 catalog 항목에 대해 문서에서 관련 블록 탐색
  - **참조 해석 (케이스 3)**: "별표2에 기재된 대로" 발견 시 해당 별표 블록으로 연결해 실제 값 추출
  - **1:N 수집 (케이스 2)**: 한 항목이 여러 블록에 흩어지면 `source_locations[]`에 모두 기록
  - **표/서술 양쪽 (케이스 5)**: 표 셀과 서술 문장 모두에서 후보 수집
  - 값을 못 찾으면 `status="not_found"` (누락 후보)
- **LLM 사용**: 값 추출·정규화 시. 프롬프트에 catalog 항목 정의 주입 → 확장 가능(사용자 지적 반영).
- **확장성**: `item_catalog`를 외부 주입 → 13개 외 항목 추가 가능. 사용자가 항목 미지정 시 catalog의 `auto_detect=true` 항목을 LLM이 문서에서 자동 발굴.

### M3. 완결성 검증 (Completeness) — 검증 (a)
- **책임**: 설명서에 필수 항목이 다 있는가.
- **입력**: 설명서의 `ExtractedItem[]`, `required_rules`(§3.5)
- **출력**: `CompletenessResult[]` (§3.6)
- **처리**:
  - 각 필수 항목의 존재 여부 확인
  - **조건부 필수 (케이스 9)**: `required_rules`가 상품유형(`product_type`)에 따라 필수 여부 결정 → 조건 불충족 시 "해당없음"으로 처리(오탐 방지)
- **비-LLM** (규칙 기반). 상품유형 판정만 LLM 보조 가능.

### M4. Item Matcher
- **책임**: 계약서 항목 ↔ 설명서 항목의 대응 관계 결정.
- **입력**: 계약서 `ExtractedItem[]`, 설명서 `ExtractedItem[]`
- **출력**: `MatchPair[]` (§3.3)
- **처리**:
  - catalog의 `canonical_key`로 1차 매칭 (결정론적)
  - key로 안 잡히는 것은 **의미 매칭 (케이스 1)**: LLM이 의미 대응 판단
  - **false match 방지 (케이스 4)**: 매칭에 `confidence` 부여, 문맥 근거 기록. 낮으면 "매칭 불확실"로 사람 확인 대상
  - **1:N (케이스 2)**: 한 설명서 항목에 계약서 여러 항목이 대응 가능 → `contract_items[]` 배열
- **LLM 사용**: canonical_key 미매칭 항목의 의미 대응 판단.

### M5. Reconciler
- **책임**: 매칭된 쌍의 값이 일치하는가 판정.
- **입력**: `MatchPair[]`
- **출력**: `ReconcileResult[]` (§3.7)
- **처리**:
  - **정규화 후 비교 (케이스 1)**: "3년"="36개월", "0.5%"="연 0.5%", 날짜 형식 통일 → 규칙 기반 정규화 먼저
  - 정규화로 동등하면 `match`
  - 규칙으로 판정 불가 시 **LLM 의미 동등성 판정 (케이스 6 수식/조건부, 케이스 7 표기체계)**
  - **표기 체계 매핑 (케이스 7)**: 위험등급 등은 `mapping_table` 주입받아 정규화
  - 결과: `match` | `mismatch` | `uncertain`, 각 사유·근거·confidence 기록
- **LLM 사용**: 규칙 폴백 시에만.

### M6. Report Builder
- **책임**: 완결성 + 정합성 결과를 통합 리포트로.
- **입력**: `CompletenessResult[]`, `ReconcileResult[]`, `MatchPair[]`(미매칭 포함)
- **출력**: `Report` (§3.8) — JSON + 사람용 마크다운 요약
- **처리**:
  - 불일치·누락·불확실을 심각도(severity)별 분류
  - **버전 경고 (케이스 10)**: 두 문서 기준일 상이 시 상단 경고
  - 각 항목에 출처 위치 링크(문서·조항) 첨부

---

## 3. 데이터 계약 (JSON 스키마)

모듈 간 인터페이스. 이 스키마를 고정하면 모듈 독립 개발·교체 가능.

### 3.1 ParsedDoc
```json
{
  "doc_id": "string",
  "doc_role": "contract | product_statement",
  "doc_meta": { "issuer": "string|null", "version_date": "YYYY-MM-DD|null", "product_type": "string|null" },
  "blocks": [
    {
      "block_id": "string",
      "type": "prose | table | reference",
      "location": { "section": "제8조|별지1|별표2|...", "page": 3 },
      "text": "string (prose일 때)",
      "table": [["헤더","..."],["셀","..."]],
      "ref_target": "별표2 (reference일 때)"
    }
  ],
  "parse_warnings": ["표 추출 실패: 별지1", "..."]
}
```

### 3.2 ExtractedItem
```json
{
  "item_id": "string",
  "canonical_key": "trust_period | trust_fee | invest_target | ...",
  "raw_label": "문서에 실제 쓰인 라벨 (예: 신탁기간)",
  "value_raw": "3년",
  "value_normalized": { "kind": "duration|percent|money|date|enum|formula|text", "value": "P3Y" },
  "status": "found | not_found | ambiguous",
  "source_locations": [ { "block_id": "b12", "section": "별지1" } ],
  "confidence": 0.0,
  "notes": "참조 해석: 별표2에서 값 확보"
}
```

### 3.3 MatchPair
```json
{
  "pair_id": "string",
  "canonical_key": "trust_fee",
  "contract_items": ["c_item_5", "c_item_11"],   // 1:N (케이스 2)
  "statement_items": ["s_item_3"],
  "match_method": "canonical_key | semantic",
  "match_confidence": 0.0,
  "match_evidence": "문맥 근거 요약",
  "flag": "ok | uncertain_match"                  // 케이스 4
}
```

### 3.4 item_catalog (주입 — 추출 대상 정의)
```json
{
  "items": [
    {
      "canonical_key": "trust_period",
      "display_name": "신탁기간",
      "aliases": ["신탁기간","계약기간","만기"],
      "value_kind": "duration",
      "auto_detect": true,          // 사용자 미지정 시 LLM 자동 발굴 허용
      "extraction_hint": "별지 세부내역서 우선"
    }
  ]
}
```
> 13개 필수항목 + 계약서 별지 항목을 초기 catalog로. `aliases`·`auto_detect`로 확장성·유연매칭 지원.

### 3.5 required_rules (주입 — 완결성 규칙)
```json
{
  "rules": [
    { "canonical_key": "early_redemption", "required_when": { "product_type_in": ["ELS편입","파생편입"] } },  // 케이스 9
    { "canonical_key": "deposit_protection", "required_when": "always" }
  ]
}
```

### 3.6 CompletenessResult
```json
{ "canonical_key": "청약철회권", "present": true, "required": true, "verdict": "ok | missing | not_applicable", "location": {...} }
```

### 3.7 ReconcileResult
```json
{
  "pair_id": "string",
  "canonical_key": "trust_fee",
  "contract_value": "연 0.5%",
  "statement_value": "0.5%/년",
  "verdict": "match | mismatch | uncertain",
  "method": "normalized_rule | llm_semantic | mapping_table",
  "reason": "정규화 후 동일",
  "confidence": 0.0,
  "evidence": { "contract": {...loc}, "statement": {...loc} }
}
```

### 3.8 Report
```json
{
  "summary": { "total_items": 0, "match": 0, "mismatch": 0, "uncertain": 0, "missing": 0 },
  "warnings": ["버전 불일치: 계약서 2024-01 vs 설명서 2021-09"],   // 케이스 10
  "findings": [ { "type": "mismatch|missing|uncertain", "canonical_key": "...", "detail": {...}, "severity": "high|med|low" } ],
  "authority": "contract"
}
```

---

## 4. 케이스 → 모듈 배치 (추적 매트릭스)

| 케이스 | 처리 모듈 | 방식 |
|---|---|---|
| 1 의미 매칭 | M4, M5 | LLM 의미 매칭 + 정규화 |
| 2 1:N 분산 | M2, M4 | source_locations[], contract_items[] |
| 3 참조 지정 | M2 | ref_target 해석 |
| 4 false match | M4 | match_confidence + flag |
| 5 표 vs 서술 | M1, M2 | block type 구분, 양쪽 추출 |
| 6 수식·조건부 | M5 | value_kind=formula, LLM 동등성 |
| 7 표기 체계 | M5 | mapping_table 주입 |
| 8 외부 필수항목 | M2 catalog, M3 rules | 주입 파라미터 |
| 9 조건부 필수 | M3 | required_when 규칙 |
| 10 버전 불일치 | M1, M6 | version_date 비교 → 경고 |

---

## 5. 처리 순서 (의사코드)

```python
def reconcile(contract_file, statement_file, item_catalog, required_rules, mapping_table, authority="contract"):
    c_doc = M1_parse(contract_file, "contract")
    s_doc = M1_parse(statement_file, "product_statement")

    c_items = M2_extract(c_doc, item_catalog)
    s_items = M2_extract(s_doc, item_catalog)

    completeness = M3_completeness(s_items, required_rules, product_type=s_doc.doc_meta.product_type)

    pairs = M4_match(c_items, s_items)              # canonical_key → semantic fallback
    reconciled = M5_reconcile(pairs, mapping_table) # normalize → llm fallback

    report = M6_report(completeness, reconciled, pairs, c_doc, s_doc, authority)
    return report
```

---

## 6. LLM 사용 지점 (명확히 격리)

RAG 없음. LLM은 아래 3곳에서만 호출. 각 호출은 입출력 JSON 고정 → 교체·모킹 가능.

1. **M2 값 추출 보조**: 블록에서 특정 항목 값을 구조화 추출 (프롬프트에 catalog 주입)
2. **M4 의미 매칭**: canonical_key로 안 잡힌 항목쌍의 대응 여부 판단
3. **M5 의미 동등성**: 규칙 정규화로 판정 못한 값쌍의 동등 여부 판단 (수식·표기체계 등)

> 나머지(파싱·규칙 정규화·완결성·리포트)는 전부 결정론적 코드. → 테스트 용이, 비용 최소, 재현 가능.

---

## 7. PoC 구현 스코프 (Claude Code 착수용)

**포함 (PoC)**
- M1~M6 전체, 신규 계약 시나리오
- item_catalog 초기값: 13개 필수 + 계약서 별지 항목(신탁금액·기간·수익자·보수·중도해지수수료·투자대상)
- 입력: 텍스트/PDF 2개
- 출력: JSON 리포트 + 마크다운 요약
- 테스트 케이스 3종: (a) 정상 일치 (b) 값 1개 불일치 (c) 항목 누락

**제외 (확장 지점만 표시)**
- 변경대비표 시나리오 → `authority="change_table"` 스위치 + M4/M5 재사용으로 확장
- SCS 연동, 메일 전달 → 인터페이스 스텁만
- 실제 mapping_table(위험등급) → 최소 샘플만

**확장 포인트 (주석으로 표시할 것)**
- Agent to Agent: 각 모듈을 독립 호출 가능한 함수/엔드포인트로 → 5번 과제(리스크 규정) 등과 도구 공유 대비
- catalog·rules·mapping을 코드가 아니라 설정 파일(JSON)로 → 현업이 항목 추가 가능

---

## 8. 디렉토리 구조 (제안)

```
trust_reconciler/
  main.py                 # reconcile() 오케스트레이션
  modules/
    m1_parse.py
    m2_extract.py
    m3_completeness.py
    m4_match.py
    m5_reconcile.py
    m6_report.py
  llm/
    client.py             # LLM 호출 래퍼 (모킹 가능)
    prompts/
      extract.txt
      match.txt
      equivalence.txt
  config/
    item_catalog.json     # 추출 항목 정의 (확장 가능)
    required_rules.json    # 완결성 규칙
    mapping_table.json     # 표기체계 매핑
  schemas/                # 3장 JSON 스키마 (pydantic 등)
  tests/
    fixtures/             # 계약서/설명서 샘플 + 3종 케이스
    test_each_module.py
```