# AGENT1 지시사항서 — 신탁계약서 ↔ 투자설명서 정합성 검증 에이전트

> 이 문서는 Claude Code가 단독으로 Agent1을 구현할 수 있도록 작성된 자립형 스펙이다.
> 시스템 전체 설계는 `SPEC.md`(v2)에 있으며, Agent1은 그 아키텍처의 **첫 구현 대상**이다.
> 동봉 테스트 데이터: `agents/agent1/data/samples/ss2207_special_trust.pdf`(특정금전신탁
> 계약서, 빈 템플릿), `agents/agent1/data/B1055656A.pdf`(삼성 투자설명서, 66p),
> 골든 쌍 `agents/agent1/data/golden/{contract_filled.pdf, prospectus.md}`.
> PDF는 모두 born-digital(텍스트 레이어 있음, OCR 금지).
>
> **구현 현황 주의**: 이 문서의 §3·§4(lookup 3단 추출)는 **설계 의도**이고, 실제 구현은
> 다른 길을 갔다 — `lookup()`으로 값 하나를 집어내는 대신 **section으로 범위를 좁혀 증거
> 표를 만들고 판정을 LLM에 맡기는 구성**(`src/scope.py` + `src/judge.py`)이다. 규칙 기반
> 결정론 경로는 코어의 `core/reconcile.py`로 남아 있고 `src/service.py::verify()`가 그것을
> 부른다. 두 경로 모두 §5의 라우터 위에서 돈다. 절마다 어느 쪽 이야기인지 표기했다.

---

## 1. Agent1의 정의 — 한 문장

**Agent1 = `lookup(문서, section, 용어) → {value, raw, source}` 프리미티브 두 번 호출 + 결정론 비교기.**

```
lookup(계약서,  "별지1/신탁계약 세부내역", 신탁보수)  → {1.5, "연 1.5%", p5}
lookup(설명서,  "제2부/13.보수 및 수수료", 신탁보수)  → {?,   "...",     p35}
        ↓ value_type 비교기 (코드, LLM 판정 금지)
        ↓ 판정 + 양쪽 출처 인용 리포트
```

비교 rule 파일(§6)은 lookup 쌍의 목록이고, 엔진은 정답(계약서) 쪽 rule을 순회하며
lookup 2회 + 비교 1회를 반복한다. **`lookup`이 Agent1의 전부이며, 이후 다른 태스크
(검색·요약 생성)도 같은 함수를 재사용한다** — 범용 프리미티브로 설계할 것.

**문서는 라우터에서 온다 (SPEC §00).** Agent1은 자기 형식·용어집 파일을 고르지 않는다.
말할 수 있는 것은 doc_type뿐이고, 무엇으로 처리할지는 `core/registry.yaml`이 정한다.

```python
from core import router
routed = router.route(path, doc_type="특정금전신탁")   # 경로를 넘길 자리가 없다
```

`src/service.py`가 이 호출을 감싸며(`structurize_contract` / `structurize_prospectus`), 그
파일에는 **자산 경로가 없다.** 형식을 바꾸고 싶으면 등록부를 고쳐야 하고, 그 변경은 이
에이전트만이 아니라 모든 호출자에게 동시에 적용된다. 이 규율은 `tests/architecture/
test_no_bypass.py`가 코드로 지킨다(에이전트 코드에서 `core.format_model.load` ·
`core.glossary.load` · `core.parse_adapter.parse` 호출과 자산 경로 리터럴을 금지).

핵심 원칙 (SPEC.md 계승):
- **런타임 결정론**: 같은 입력 → 같은 출력. 결정론 경로(`core/reconcile.py`)에는 LLM이 없다.
- **비교·판정에 LLM 금지**: 판정은 `==`(타입 비교기)가 한다.
  → **구현에서 이 원칙은 agent1 파이프라인에 한해 의도적으로 뒤집혔다(사용자 결정).**
  `src/judge.py`가 좁혀진 증거 표를 보고 값을 고르고 판정한다. 대신 출처 위조를 막는
  장치를 뒀다: LLM은 `e-012` 같은 **증거 ID로만** 근거를 가리킬 수 있고, 코드가 그 ID를
  실제 page/bbox/cell로 되돌린다. 없는 ID를 대면 그 행은 `NEEDS_REVIEW`로 강등된다.
  SPEC.md §4.1의 결정론 엔진은 그대로 살아 있고 `service.verify()`가 쓴다.
- **section이 모호성을 제거한다**: "총보수"는 설명서에 여러 번 등장(8p 요약박스·35p 표…).
  section 좌표가 있어야 어느 것인지 결정된다. 용어 단독 검색 금지.
- **실패는 좌표 단위로 국소화**: 한 rule의 실패는 그 행만 영향받는다.

---

## 2. 입력 자산

### 2.1 용어집 2개 (`agents/agent1/glossary/`)

**`doc_type`은 등록부(`core/registry.yaml`)·형식 파일과 글자까지 같아야 한다** — 세 곳이
어긋나면 라우터가 `RouteAssetMissing`으로 거부한다(SPEC §00.2.1). 계약서 쪽 값은
**`특정금전신탁`**이다(`특정금전신탁계약서`가 아니다).

```yaml
# glossary/trust_contract.glossary.yaml  (계약서용 — 실물에서 발췌, 전체 16 용어)
version: 1
doc_type: 특정금전신탁
terms:
  신탁계약 세부내역: { kind: [section, fact] }
  신탁자금 운용방법: { kind: [section, fact], value_type: option_set, aliases: [운용방법, 운용대상, 편입자산] }
  세부 운용지시:     { kind: [section, fact], aliases: [투자전략] }
  기타 특약사항:     { kind: [section] }
  변경계약서:        { kind: [section] }
  계좌번호:  { kind: [fact], value_type: account_no, aliases: [신탁계좌번호] }
  신탁금액:  { kind: [fact], value_type: number, aliases: [투자금액, 신탁원금, 투자원금, 가입금액] }
  신탁기간:  { kind: [fact], value_type: date_range, aliases: [투자기간, 계약기간, 신탁계약기간] }
  기본보수:  { kind: [fact], value_type: percent, aliases: [신탁보수, 보수율, 운용보수] }
  수익보수:  { kind: [fact], value_type: percent, aliases: [성과보수, 초과성과보수] }
  # … 운용내역 통지여부 · 지급주기 · 지급기간 · 원금지급비율 · 지급계좌 · 중도해지수수료
```

계약서의 보수는 **기본보수와 수익보수로 갈린다** — 실물 별지1이 그렇게 적혀 있다.
`신탁보수`는 기본보수의 alias로 흡수됐다.

```yaml
# glossary/prospectus.glossary.yaml  (설명서용 — 실물 B1055656A.pdf 측정 기반, 12 용어)
version: 1
doc_type: 투자설명서
terms:
  요약정보:                    { kind: [section] }
  보수 및 수수료에 관한 사항:    { kind: [section] }
  집합투자기구의 명칭:          { kind: [section, fact] }
  집합투자기구의 신탁계약기간:   { kind: [section, fact], aliases: [신탁계약기간] }
  총 보수:      { kind: [fact], value_type: percent, aliases: [총보수] }
  신탁업자보수:  { kind: [fact], value_type: percent, aliases: [신탁업자 보수, 신탁보수] }
  판매수수료:    { kind: [fact], value_type: percent, aliases: [선취판매수수료, 후취판매수수료] }
  환매수수료:    { kind: [fact], value_type: range_tiers, aliases: [중도해지수수료] }
  # … 집합투자업자보수 · 판매회사보수 · 일반사무관리회사보수 · 기타비용
```

### 2.2 형식 파일 2개 (`agents/agent1/formats/`)

Agent1에서는 **수기 작성 허용** (LLM 형식 유도는 플랫폼 스펙 T4 — Agent1 범위 밖).
형식 파일도 doc_type이 등록부·용어집과 같아야 하며, 라우터가 route를 통해 싣는다.

```json
// formats/trust_contract.format.json  (doc_type "특정금전신탁", v1 — 조/항/호/별지)
// formats/prospectus.format.json      (doc_type "투자설명서", v2 — 실측으로 고친 판)
{
  "doc_type": "투자설명서",
  "format_version": 2,
  "compiled_from": ["B1055656A.pdf"],
  "regex_markers": [
    { "id": "부",   "pattern": "^제(\\d+)부\\.\\s*(.+)$", "level": 0,
      "groups": ["no","title"], "label": "제{no}부",
      "_note": "마침표가 목차(p2~4 '제1부 모집…')를 배제한다 — 본문(p12~)만 잡힌다" },
    { "id": "항목", "pattern": "^(\\d{1,2})\\.\\s+([^\\d\\s].*)$", "level": 1,
      "groups": ["no","title"], "parent": "부", "label": "{no}. {title}",
      "_note": "4자리 연도(2011. 2.18)와 요율(0.30)을 배제하려 자릿수·공백·비숫자 시작을 강제" }
  ],
  "term_markers": [ { "term": "요약정보", "level": 0 } ],
  "hierarchy": ["문서", "부|요약정보", "항목"],
  "default_section": "표지",
  "confidence": "medium"
}
```

순진한 `^(\d+)\.\s*(.+)`는 같은 페이지의 연혁 날짜와 요율까지 삼킨다. 위 패턴은 본문
p12~66에서 **38건 적중·오탐 0**으로 측정됐다. 세목(`가.`) 마커는 실물에서 필요하지 않아
채택하지 않았다 — 감이 아니라 측정으로 결정한다.

### 2.3 비교 rule 파일 (`agents/agent1/tasks/`) — **두 개다. 스키마가 다르다.**

두 실행 경로가 각자 자기 규칙 파일을 읽는다. 헷갈리면 엉뚱한 파일을 고치게 되므로 먼저 갈라 둔다.

| 파일 | 읽는 쪽 | 스키마 | 판정 |
|---|---|---|---|
| `reconcile_trust_vs_prospectus.yaml` | `core/reconcile.py`(`load_task` → `TaskSpec`), `service.verify()` | `source_of_truth`·`target`이 **문자열**, rule의 `source`·`target` **둘 다 필수** | 결정론(비교기) |
| `agent1_trust_vs_prospectus.yaml` | `src/pipeline.py`(`yaml.safe_load`) | `source_of_truth: {doc_type: …}` 중첩, `target: null` 허용, `id`·`row_anchor` 추가 | LLM 판정 |

**`agent1_trust_vs_prospectus.yaml`은 `core/reconcile.py`로 로드되지 않는다** — `TaskSpec`이
중첩 매핑과 `target: null`을 받지 않아 검증에서 실패한다. 이 파일은 pipeline 전용이다.

```yaml
# tasks/agent1_trust_vs_prospectus.yaml  (LLM 판정 파이프라인용, rule 6개)
source_of_truth: { doc_type: 특정금전신탁 }
target: { doc_type: 투자설명서 }
rules:
  - id: r-fee
    source: { section: "별지1/신탁계약 세부내역", term: 기본보수 }
    target:
      section_any_of: ["제2부/13. 보수 및 수수료에 관한 사항"]
      term: 총 보수
      row_anchor: "수수료선취-오프라인(A)"   # 이 값으로 셀을 뽑지 않는다 — 고른 행을 대조만 한다
  - id: r-redeem
    source: { section: "별지1/신탁계약 세부내역", term: 중도해지수수료 }
    target: { section_any_of: ["제2부/13. 보수 및 수수료에 관한 사항"], term: 환매수수료 }
  - id: r-account
    source: { section: "별지1/신탁계약 세부내역", term: 계좌번호 }
    target: null          # 설명서에 대응 개념 없음 → NOT_APPLICABLE 한 행
```

```yaml
# tasks/reconcile_trust_vs_prospectus.yaml  (core 결정론 엔진용, rule 12개)
source_of_truth: 특정금전신탁      # 문자열이다 — 중첩 매핑을 쓰면 로드가 실패한다
target: 투자설명서
rules:
  - source: { section: "별지1/신탁계약 세부내역", term: 신탁금액 }
    target: { section_any_of: ["계약 개요", "투자조건"], term: 신탁금액 }
```

`target: null`은 "정답에는 있으나 대상 문서에 개념 자체가 없는 필드"의 명시적 선언이다.
조용한 스킵이 아니라 `NOT_APPLICABLE` 한 행으로 리포트에 남긴다. **이 선언은 pipeline
경로에만 구현돼 있다**(`pipeline.run`이 `target is None`을 보고 행을 만든다).
`core/reconcile.py`에는 **미구현**이며, 지금 스키마로는 표현할 수도 없다 — 코어 엔진에
필요해지면 `Rule.target`을 Optional로 바꾸고 `NOT_APPLICABLE`을 `VERDICTS`에 더해야 한다.

---

## 3. lookup 프리미티브 — 인터페이스

> **구현 현황: 이 인터페이스는 코드에 없다.** `lookup.py`도 `LookupResult`도 만들어지지
> 않았고, 대신 `src/scope.py`가 **범위 좁히기 + 증거 표**를, `src/judge.py`가 **고르기와
> 판정**을 맡는다. 값 하나를 규칙으로 집어내려 들면 문서마다 임계값이 늘어난다는 것이
> 실측의 결론이었다(값 꼬리 길이 상한·라벨 전용 줄 처리·셀이 용어로 시작하는가…).
> 아래 요구 중 **살아남은 것**은 그대로 지켜진다:
> - 좌표로 범위를 좁힌 뒤에만 값을 고른다(용어 단독 검색 금지).
> - 후보가 여럿이고 값이 다르면 **임의 선택 금지** — 실측에서 판정자가 A/B/C 클래스 세
>   후보를 모두 인용하고 하나를 고르지 않았다(→ `NEEDS_REVIEW`).
> - `method`는 리포트까지 전달된다(감사 추적).
> 좌표 정밀도는 **문서 → 구역 → 쪽 → 표 행 → bbox**까지이며, 행 안의 열은 아직 판정자가 읽는다.

```python
def lookup(doc: StructuredDoc, section_path: str, term: str) -> LookupResult:
    """
    StructuredDoc: 구조화된 문서(§5의 *.doc.json 로드 결과)
    section_path: "별지1/신탁계약 세부내역" 형태. 접두 매칭 허용(하위 section 포함).
    term: 용어집의 정규 용어명. aliases로도 매칭.
    """

@dataclass
class LookupResult:
    status: Literal["FOUND", "NOT_FOUND", "AMBIGUOUS", "NEEDS_REVIEW"]
    value: Any | None            # value_type으로 정규화된 타입값
    raw: str | None              # 원문 그대로
    source: Source | None        # {page, bbox|cell}
    method: str                  # "field" | "table_anchor" | "llm" — 감사용
    candidates: list | None      # AMBIGUOUS일 때 후보들
```

- 같은 section 안에서 용어가 복수 매칭되고 값이 서로 다르면 `AMBIGUOUS` — 임의 선택 금지.
- `method` 필드는 필수: 어느 추출 경로로 얻었는지 리포트까지 전달한다(감사 추적).

---

## 4. lookup 내부 — 3단 추출 (문서 장르 무관, 인터페이스 동일)

> **구현 현황: 미구현.** 아래 3단 추출 대신 §3의 좁히기+판정 구성이 들어갔다. 다만
> **2단의 병합 헤더 forward-fill은 필요가 없어졌다** — docling이 `table.data.table_cells`로
> 논리 셀과 span을 그대로 주므로 부모 라벨(`지급비율(연간,%)`)이 한 셀로 오고 덮는 열을
> 스스로 알려준다(§5의 파서 기준선 비교 참조). **레이아웃 박스 감지**의 근거였던 p8
> 요약박스 문제는 현재 구성에서는 표를 통째로 증거 표에 실어 판정자가 읽는 것으로 갈음한다
> (실물 66쪽 설명서의 표 73개 중 80%가 5행 이하 — 앵커로 찍을 크기가 아니라 통째로 넣을 크기다).

**1단 — 필드/텍스트 매칭 (결정론).** section의 content에서 용어(+aliases) mention을 찾고,
같은 행(표) 또는 인접 텍스트에서 value_type 파서가 값을 뽑는다. 계약서 별지1 같은 양식형에 주효.

**2단 — 표 앵커 탐색 (결정론, 실측 검증 완료).** fact가 표 안에 있을 때. 알고리즘:

```python
# 병합 2단 헤더 처리 — B1055656A p35 표에서 검증됨 (아래 골든 값 §8 참조)
parent, child = table[0], table[1]          # 헤더 2행
filled, cur = [], ""
for c in parent:                            # 부모 라벨 forward-fill (colspan 복원)
    if c and c.strip(): cur = c.replace("\n","")
    filled.append(cur)
headers = [f"{p}/{(c or '').strip()}".strip("/") if (c and c.strip()) else p
           for p, c in zip(filled, child)]
# 행 앵커: 첫 열에서 row_term 부분일치 → 열 앵커: headers에서 col_term 부분일치 → 셀 반환
```

- 헤더가 1행인 표는 child 단계 생략. 헤더 행 수는 "첫 데이터 행 이전의 비수치 행"으로 판정.
- **레이아웃 박스 감지 (실측에서 발견된 규칙)**: 추출된 표의 빈 셀 비율이 임계(기본 70%) 초과
  또는 열 수가 비정상(기본 15열 초과)이면 표가 아니라 레이아웃 박스로 판정 → 표 앵커를 포기하고
  셀 텍스트를 이어붙여 1단(텍스트 매칭)으로 강등. (B1055656A p8 요약박스가 27×30 희소 격자로
  과분할되는 실측 사례가 이 규칙의 근거다.)

**3단 — LLM 보조 추출 (폴백, 플래그 `--llm-fallback` 기본 off).** 1·2단 실패 시 해당 section
텍스트(또는 표 셀 그리드)만 LLM에 주고 "용어 X의 값을 추출하고 근거 스팬을 인용하라"를 시킨다.
structured output, 낮은 temperature. **스팬 인용이 없으면 결과를 버리고 NEEDS_REVIEW.**
추출값은 다시 value_type 파서를 통과해야 한다(LLM이 준 숫자를 그대로 믿지 않는다).

---

## 5. 파싱·구조화 (SPEC.md §3 축약 적용)

- **파서: docling.** 코어의 `core/parse_adapter.py`가 docling을 부르고(`_converter` /
  `docling_version()`), born-digital 판정은 PyMuPDF(`fitz`)가 한다. Agent1은 파서를 고르지
  않는다 — 등록부의 route가 `parser: auto`(= `core.parse_adapter:parse`)를 지정하고, 그
  어댑터가 확장자로 pdf(docling)와 md/txt를 가른다.
  **교체 근거(스펙이 요구한 기준선 비교, p35 보수표로 실측)**: 골든 값(A클래스 총보수 0.62,
  C 1.32, 신탁업자보수 0.02)은 pdfplumber·docling 둘 다 맞혔고, **병합 2단 헤더에서 갈렸다** —
  pdfplumber는 문자열 격자라 forward-fill이 필요했지만 docling은 논리 셀 + span을 주므로
  필요 없다. 브랜드가 아니라 이 기준선 비교로 결정했다.
- born-digital 확인 후 텍스트 레이어 사용. OCR 금지(아니면 경고와 함께 OCR로 내려간다).
- 구조화: 형식 파일의 regex_markers + term_markers로 section 트리 → 각 요소를 최심 section에 배정
  → `output/{stem}.doc.json` (스키마는 SPEC.md §00.4·§3.2: sections + facts + fitness).
  **이 전부를 `router.route()` 한 번이 한다** — 파싱·구조화·채점이 배차의 일부다.
- 적합도 게이트(SPEC.md §3.4): `service.verify()`는 기본이 **격리**다(게이트 미달 문서는
  대조하지 않고 예외를 올린다. `allow_quarantined=True`로만 강제). 구조화만 하는 경로
  (`structurize_contract` 등)는 경고 수준으로 두고 `fitness`를 결과에 싣는다.

---

## 6. 비교 엔진

정답(source) rule 순회. rule마다:

1. `src = lookup(계약서, rule.source.section, rule.source.term)`
2. `rule.target is null` → 판정 `NOT_APPLICABLE`, 다음 rule로.
3. `tgt = lookup(설명서, rule.target.section_any_of 순차 시도, rule.target.term)`
4. 판정표:

| src.status | tgt.status | 판정 |
|---|---|---|
| FOUND | FOUND | 비교기 실행 → `MATCH` / `VALUE_MISMATCH` |
| FOUND | NOT_FOUND | `MISSING_IN_TARGET` |
| FOUND | AMBIGUOUS/NEEDS_REVIEW | `NEEDS_REVIEW` |
| NOT_FOUND/AMBIGUOUS | (무관) | `SOURCE_EXTRACTION_FAILED` ← **정답 쪽 실패는 별도 등급** |

**신뢰 비대칭**: 정답(계약서) lookup 실패는 검증 결과가 아니라 시스템 경고다. target 실패
(`MISSING_IN_TARGET`)는 그 자체가 유효한 검증 결과다. 둘을 같은 코드로 뭉개지 않는다.

비교기는 SPEC.md §3.3의 value_type별 규칙 그대로: number(Decimal 동일성), percent(표기 정규화),
date_range(끝점별), range_tiers(구간-요율 쌍 집합), account_no, option_set, text.
구현은 `core/normalize.py`의 `PARSERS`/`COMPARATORS`이며 단위 테스트는 `tests/core/test_core.py`.

**리포트 스키마: SPEC.md §4.1**(`core/reconcile.py`의 `Report`/`Row`) — 행마다 `term`,
`value_type`, `verdict`, `note`, 그리고 양쪽의 `{section_id, value, raw, ref}`. 리포트 수준에는
`stats`(판정별 개수)와 `gate`(양쪽 문서의 적합도)가 붙는다.
LLM 판정 경로의 리포트는 `src/pipeline.py`의 `Report`이며 여기에 `method`·`source_refs`·
`target_refs`(증거 ID → page/bbox/cell)·`model`·`usage`·`scopes`가 더 붙는다 — `scopes`가
통째로 실리므로 **어느 증거가 판정자에게 넘어갔는지 사후 감사**가 된다.
**모든 rule이 정확히 한 행씩** 나타난다 — NOT_APPLICABLE, SOURCE_EXTRACTION_FAILED 포함.

두 경로의 판정 어휘가 다르다는 점에 주의:
- `core/reconcile.py`: `MATCH · VALUE_MISMATCH · MISSING_IN_TARGET · UNMAPPED · NEEDS_REVIEW`
  (위 판정표의 `SOURCE_EXTRACTION_FAILED` 자리는 `NEEDS_REVIEW`가 맡는다).
- `src/judge.py`: 위 판정표 그대로 `MATCH · VALUE_MISMATCH · MISSING_IN_TARGET ·
  SOURCE_EXTRACTION_FAILED · NOT_APPLICABLE · NEEDS_REVIEW`.

---

## 7. 구현 작업 (빌드 오더)

T-A1.1~T-A1.4는 **에이전트가 아니라 코어에 구현됐다** — Agent1 전용 사본을 만들지 않고
`core/`의 부품을 쓴다(SPEC §6: 새 에이전트 = 새 폴더 + 새 데이터 파일이지 새 코드가 아니다).

- **T-A1.1 스키마·용어집·형식 로더** — `core/glossary.py` · `core/format_model.py` ·
  `core/reconcile.py`(TaskSpec) · `core/structurize.py`(doc.json). **[구현됨]**
- **T-A1.2 파서 어댑터** — `core/parse_adapter.py`(docling + PyMuPDF born-digital 판정).
  실측: 계약서 제1~32조 전부, 설명서 제1~6부 헤더 검출. **[구현됨, §5의 기준선 비교로 docling 채택]**
- **T-A1.3 구조화기** — `core/structurize.py`. 검증: §8-1(`tests/agent1/test_golden.py`). **[구현됨]**
- **T-A1.4 value_type 파서** — `core/normalize.py` 8종 + `tests/core/test_core.py`. **[구현됨]**
- **T-A1.5 범위 좁히기(구 lookup 1·2단)** — `src/scope.py`: 좌표로 좁혀 증거 표를 만들고
  증거 ID ↔ 출처 대응표를 남긴다. 표 앵커는 값을 뽑는 도구가 아니라 **행 검증기**로만 쓴다
  (`judge.verify_row_anchor`). **[구현됨 — §3·§4의 lookup 인터페이스와는 다른 형태]**
- **T-A1.6 비교 엔진 + 리포트** — 결정론 경로 `core/reconcile.py` + `src/service.py::verify()`
  **[구현됨]**, LLM 판정 경로 `src/judge.py` + `src/pipeline.py` **[구현됨]**.
- **T-A1.7 (선택) LLM 폴백** — 3단 폴백 형태로는 **[미구현]**. LLM은 폴백이 아니라 판정
  단계에 상시 들어와 있다(§1).
- **T-A1.8 골든 테스트 일체** — `tests/agent1/{test_golden.py, test_anchor.py}`. **[구현됨]**
  변이 테스트(§8-4)는 **[미구현]**.

## 8. 완료 기준 (골든 — 실측값 기반)

**8-1 구조화 (두 실물 PDF):**
- 계약서: 본문 제1~32조 + 별지1·별지2가 section으로 존재. "별지1/신탁계약 세부내역" section에 표 content 존재.
- 설명서: 제1~6부 + "요약정보" section 존재. "제2부/13. 보수 및 수수료에 관한 사항" section이
  p35 표들을 content로 가짐. 같은 문서 2회 구조화 시 doc.json 동일(결정론).

**8-2 값 골든 (B1055656A.pdf — 실측에서 확정된 값):**
```
"제2부/13. 보수 및 수수료에 관한 사항" (p35 표)
  행 "수수료선취-오프라인(A)"   총 보수 0.62 · 신탁업자보수 0.02
  행 "수수료후취-오프라인(B)"   총 보수 1.02
  행 "수수료미징구-오프라인(C)" 총 보수 1.32
  환매수수료 → "90일 미만 이익금의 100분의 70" (range_tiers)
```
클래스 구분이 필요한 rule은 `row_anchor`(§2.3)로 어느 행을 볼지 지정한다. **앵커로 셀을
직접 찍지 않는다** — 같은 표에 `총 보수` / `동종유형 총 보수` / `총 보수·비용` / `합성 총
보수·비용`이 함께 있어 부분일치가 흔하고, 앵커가 틀려도 그럴듯한 값 하나가 나올 뿐 신호가
없다. 앵커는 판정자에게 "이 행만 본다"고 알려주고, **고른 행이 그 행인지 코드가 대조**한다
(`tests/agent1/test_anchor.py`). 어긋나면 확정 판정을 보류로 강등한다.

**8-3 엔진 (골든 쌍):** `ss2207`은 빈 템플릿이라 값이 없다. **합성 픽스처를 만드는 대신
값이 채워진 실물 쌍이 확보됐다** — `data/golden/contract_filled.pdf`(체결본) +
`data/golden/prospectus.md`(요약서). `tests/agent1/test_golden.py`가 이 쌍으로 결정론 엔진을 검증:
- 태스크의 rule 전부가 리포트에 정확히 한 행씩(용어 중복 없음).
- 표기 차이는 `MATCH`(`금 1억원정` ≡ `100,000,000원`, `24.6.3` ≡ `2024-06-03`).
- 실제 불일치는 잡힌다(계약서 `매월` vs 요약서 `분기` → `VALUE_MISMATCH`).
- `MATCH`/`VALUE_MISMATCH` 행에는 양쪽 `ref`(출처)가 있다. 판정은 선언된 어휘 안에서만 나온다.

**8-4 변이 테스트: [미구현].** 골든 쌍을 훼손해 판정을 강제로 발화시키는 하네스는 아직 없다.

**8-5 결정론:** 구조화는 결정론이다(`test_structuring_is_deterministic` — 같은 PDF 2회
구조화 시 doc.json 동일). 결정론 비교 경로(`service.verify()`)도 마찬가지다.
**LLM 판정 경로(`pipeline.run`)는 이 기준을 만족하지 않는다** — 같은 입력을 두 번 돌리면
판정 문구가 달라질 수 있다. 바이트 동일 요구는 결정론 경로에만 적용한다.

## 9. 저장소 구조

```
agents/agent1/
  glossary/   trust_contract.glossary.yaml, prospectus.glossary.yaml     ← route 자산
  formats/    trust_contract.format.json, prospectus.format.json          ← route 자산
  tasks/      reconcile_trust_vs_prospectus.yaml   (core 결정론 엔진용)
              agent1_trust_vs_prospectus.yaml      (LLM 판정 파이프라인용)
  data/       B1055656A.pdf
              samples/ss2207_special_trust.pdf
              golden/{contract_filled.pdf, prospectus.md}
  src/        service.py   코어 조립 — 라우터 호출·게이트·verify (자산 경로 없음)
              scope.py     범위 좁히기 + 증거 표 (결정론)
              judge.py     LLM 판정 + 증거 ID → 출처 되돌리기
              pipeline.py  파일 두 개 → 리포트
              cli.py
  output/     {stem}.doc.json, agent1.report.json, *.reconcile.json
  README.md   실행 실측 기록 (판정 결과·비용·한계)

tests/agent1/ test_golden.py, test_anchor.py        ← 테스트는 저장소 루트에 모여 있다
```

형식·용어집은 이 폴더에 있지만 **연결은 `core/registry.yaml`이 한다**(§1). 파서·형식·용어집을
이 폴더의 코드가 고르지 않는다는 것이 요점이다.

CLI:
```bash
python agents/agent1/src/cli.py run --contract <pdf> --prospectus <pdf> [--rules <yaml>] [-o report.json]
python agents/agent1/src/cli.py scope <문서> --kind contract|prospectus --section "별지1/…" [--term …]
```
`scope`는 LLM 없이 **무엇이 판정자에게 넘어가는지**만 보여 준다.

## 10. 범위 밖 (Agent1 이후)
- LLM 형식 유도(컴파일 국면 자동화) — 플랫폼 T4
- 적합도 게이트의 격리·재컴파일 루프, 형식 버전 관리
- 검색 소비자, 체크박스 √ 검출, 스캔 OCR
