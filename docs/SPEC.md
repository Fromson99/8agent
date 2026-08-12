# 지시사항서 — 용어집 기반 문서 구조화 & 정합성 검증 시스템 (v2)

> 이 문서는 Claude Code가 단독으로 구현할 수 있도록 작성된 자립형 스펙이다.
> 배경 대화 없이 이 문서만으로 작업을 시작할 수 있어야 한다.
> v1을 대체한다. **v1 스펙 문서는 이 저장소에 없다** — v1 코드가 `archive/trust-parser-v1/`에 보존돼 있고(`api/`의 `/v1/parser/*` 엔진이 아직 그것을 부른다), v1의 설계는 그 코드와 `archive/trust-parser-v1/README.md`로만 남아 있다. v1의 부품(파서·fact·비교기·검증 게이트) 개념은 계승하되, 시스템의 중심을 **사용자 용어집(glossary) + 형식 컴파일 워크플로**로 재편했다.

---

## 00. 코어 아키텍처 — 코어는 라우터다 (8개 Agent 공통 지도)

> 이 절이 전체 프로젝트의 최상위 규칙이다. 모든 Agent(1~8)와 모든 파싱 로직은 이 구도 안에서 개발된다.

### 00.1 구도

```
문서 입력
   ↓
[코어 = 라우터]  ← registry(등록부)를 보고 판별·배차만 한다
   ↓
파싱 로직들 (조/항/호 계열 · 부/항목/세목 계열 · 발화턴 계열 · …)
   ↓ 각자 생산 — 단, 출력 계약(doc.json 스키마) 준수
doc.json (공통 그릇: sections + facts + fitness)
   ↓
공용 라이브러리 (lookup · value_type 비교기 · 적합도 게이트)
   ↓
Agent 1~8 (소비자 — 라이브러리를 조립해 태스크 수행)
```

네 층의 책임은 이것뿐이며, 서로의 책임을 침범하지 않는다:
- **코어(라우터)**: 문서가 오면 registry로 판별하고 해당 파싱 로직에 배차한다. 그 외 아무것도 하지 않는다.
- **파싱 로직**: 배차받은 문서를 자기 방식(인식기+형식+용어집)으로 구조화하되, 출력은 반드시 doc.json 스키마를 통과시킨다.
- **공용 라이브러리**: doc.json만 읽는다. 어느 로직이 만들었는지 모른다(추상화 누수 금지).
- **Agent**: 라우터에 "이 파일, 이 doc_type"을 요청하고 doc.json을 받아 소비한다. 파서·라우터 내부를 모른다.

### 00.2 등록부 (registry) — "미리 정의"의 실체

새 문서 유형 지원 = **코드 수정이 아니라 route 등록**이다. 실물은 `core/registry.yaml`이며, 아래는 그 파일에서 route 3개를 그대로 옮긴 것이다(현재 등록 6개).

```yaml
version: 1

# 파싱 로직 플러그인 — ID → "모듈:함수". 코어가 importlib로 풀어 쓴다.
# 이 표를 **데이터로** 읽기 때문에 코어 코드에는 doc_type 분기가 없다.
parsers:
  auto:       core.parse_adapter:parse            # 확장자로 갈라 준다 (pdf=docling, md/txt)
  transcript: agents.agent6.src.transcript:parse  # 발화턴 계열 (STT 전사 JSON)

routes:
  - doc_type: 특정금전신탁            # ← 형식·용어집의 doc_type과 글자까지 같아야 한다
    parser: auto
    format:   agents/agent1/formats/trust_contract.format.json
    glossary: agents/agent1/glossary/trust_contract.glossary.yaml
    threshold: 0.70                  # 이 유형의 적합도 임계 (§3.4)
    owner: agent1                    # 등록한 에이전트 (감사용)

  - doc_type: 금소법
    parser: auto
    format:   agents/agent6/formats/statute.format.json
    glossary: agents/agent6/glossary/statute.glossary.yaml
    threshold: 0.60
    owner: agent6

  - doc_type: STT전사
    parser: transcript
    format:   agents/agent6/formats/transcript.format.json
    glossary: agents/agent6/glossary/transcript.glossary.yaml
    threshold: 0.50
    owner: agent6
```

현재 등록된 6개: **특정금전신탁 · 투자설명서**(owner agent1), **금소법 · 금소법시행령 · 표준투자권유준칙 · STT전사**(owner agent6).

registry는 곧 **시스템의 문서 처리 능력 목록**이다 — "지금 무엇을 처리할 수 있는가"의 답이 이 파일 하나다. 사람이 보는 표는 `python -m core.cli routes`(= `router.describe()`)가 낸다: 유형별 parser·owner·임계·자산 존재 여부, 자산이 없어 배차되지 않는 유형까지.

### 00.2.1 강제 — 에이전트는 doc_type만 말할 수 있다

등록부가 있어도 에이전트가 자기 형식 파일을 직접 실으면 강제는 없는 것과 같다. 그래서 **`core/router.py`가 유일한 진입점이고, 그 함수는 형식·용어집 경로를 인자로 받지 않는다.**

```python
from core import router

routed = router.route(path, doc_type="특정금전신탁")   # doc_type 은 호출자가 말한다
routed = router.require(path, doc_type=...)            # 격리 문서를 거부한다 (태스크용)

routed.doc          # core.structurize.Document (doc.json, §00.4)
routed.fitness      # core.fitness_gate.Fitness (.passed / .score / .warnings)
routed.route        # Route (doc_type/parser/format/glossary/threshold/owner)
routed.parsed       # core.parse_adapter.ParseResult
routed.quarantined  # 게이트 미달 여부
```

`format=`, `glossary=` 인자가 아예 없다는 것이 요점이다. 호출자가 말할 수 있는 것은 doc_type뿐이고 무엇으로 처리할지는 registry가 정한다 — 따라서 **같은 doc_type 문서는 누가 호출하든 같은 규칙으로 처리된다.** 예전처럼 에이전트마다 `--format` 경로를 손으로 넘기면 agent1과 agent6이 같은 문서를 다르게 자를 수 있었고, 아무도 그것을 막지 못했다.

세 겹으로 막는다:

1. **인자 부재** — 위와 같이 route()에 자산을 넘길 자리가 없다.
2. **doc_type 3중 일치 검사** — route 적재 시 registry의 `doc_type`, 형식 파일의 `doc_type`, 용어집의 `doc_type`이 셋 다 같은지 확인하고, 하나라도 다르면 `RouteAssetMissing`으로 거부한다(`router._assets`). 어긋난 자산은 조용히 굴러가다 엉뚱한 문서를 그럴듯하게 구조화하므로 적재 시점에 막는다.
3. **우회 금지 테스트** — `tests/architecture/test_no_bypass.py`가 `agents/` 아래 모든 소스를 AST로 훑어 `core.glossary.load` / `core.format_model.load` / `core.parse_adapter.parse` 호출과 `*.format.json` · `*.glossary.yaml` 경로 리터럴을 금지한다. 예외는 컴파일 국면 도구만, 이유를 적어 허용 목록에 올린다.

오류는 전부 시끄럽다: `RoutingError`와 하위 `UnregisteredDocType`(등록부에 없는 유형 — 비슷한 이름을 제안한다) / `RouteAssetMissing`(자산 부재·doc_type 불일치).

새 코드에서 `format_model.load(...)` / `glossary.load(...)`를 직접 부르지 않는다. 예외는 컴파일 국면 도구인 `core/cli.py compile`과 `core/format_induce.py`뿐이다 — 아직 등록부에 없는 유형을 다루기 때문이다.

### 00.3 doc_type 은 호출자가 말한다

자동 판별(detect 규칙)은 **뺐다.** 사용자가 유형에 맞게 넣는 운영이라 "무슨 유형인지 추측"하는 층이 할 일이 없고, "그 유형이 맞긴 한가"는 구조화 뒤 적합도 게이트가 정량으로 판정한다(임계 미달 = 격리, §3.4). 추측하는 층을 두면 그 오판이 게이트 점수로 가려진다.

유형을 **모르는** 문서는 라우터가 아니라 구조 해석기로 들어간다(§4) — 형식 파일 없이 문서에서 구조를 유도하고, 같은 모양이 반복 관측되면 그 문서군의 형식을 만든다(§00.6).

3중 일치 검사에서 용어집은 **선택**이다. route에 용어집이 없으면 전역 용어집(`core.glossary.load_global`, 화면이 관리하는 `glossary.json`)을 쓴다 — 용어는 유형별이 아니라 시스템 전체의 것이라는 방향이다.

### 00.4 출력 계약 — doc.json 스키마

doc.json 스키마는 코어의 기능이 아니라 **라우터와 파싱 로직 사이의 계약서**다. 등록 조건은 단 하나: 출력이 이 스키마를 통과할 것. 실물은 `core/structurize.py`의 `Document.dump()`가 만든다.

```
{ doc_type, format_version, source_file, generated_at,
  sections: [{ section_id, marker, path, page_range, content, children }],  # 트리 (깊이 무제한)
  facts:    [{ fact_id, term, section_id, value_type, value, raw, source,
               needs_review?, note? }],
  fitness:  { score, passed, warnings, detail } }
```

트리 링크는 `children`(하위 section_id 목록)이고, 어느 section에도 안 속한 요소는 `Document.residual`(요소 index 목록)로 남아 게이트가 센다 — 잔여는 dump에 실리지 않고 `fitness.detail`에 점수로 반영된다.

문서 고유의 특수 정보는 스키마 확장이 아니라 기존 그릇 안에 담는다 — 구역 특성은 `marker`에, 특수 내용물은 `content`에(표=셀 그리드, 체크박스=options), 새 값 유형은 `value_type` enum 추가로, 품질 정보는 `fitness.warnings`에.

### 00.4.1 입력 형식 — 흐름은 여기서 갈린다

마커(글자)는 어느 형식에서나 같지만, **파서가 실어 주는 신호는 형식이 정한다.** 이걸 감추면 "같은 틀인데 어떤 문서만 덜 잘린다"가 원인 없이 나타난다.

| 형식 | 파서 | 싣는 신호 | 지면 |
|---|---|---|---|
| `pdf` | docling (레이아웃+TableFormer, born-digital이면 OCR off) | 제목 표시 · 타이포그래피(크기·굵기·간격) · 좌표 | 원본 |
| `docx` | docling msword_backend (추론 없음) | Word 스타일의 **진짜 제목 계층**(level) | 없음 → 합성 |
| `hwp` | pyhwp → md (`convert.py`) | **마커만** — 제목 선언도 좌표도 없다 | 없음 → 합성 |
| `hwpx` | OWPML 직독 (`core.hwpx_md`) | 마커만 | 없음 → 합성 |
| `xml` (법령 본문) | `core.structure.lawxml` | 태그 계층이 곧 구조 (추론 0, 적합도 1.0) | 없음 → 합성 |

- 확장자를 믿지 않는다 — 매직바이트로 가른다(`.hwp` 탈을 쓴 pdf·hwpx는 이름을 대고 거부).
- 구형 Word(`.doc`)는 읽는 파서가 없다. hwp5와 OLE 매직이 같아 확장자로 먼저 갈라 ".docx로 다시 저장" 처방을 낸다.
- 지면이 없는 형식은 `core.structure.synthpdf`가 A4 합성 지면에 흘려 찍고 **좌표를 요소에 되심는다** — 이후는 PDF와 완전히 같은 길(검수 오버레이·페이지 PNG·재해석)이다.
- 실무 함정: `require_heading` 마커(제목 위치에서만 인정)는 제목 신호가 없는 hwp에서 **영영 발화하지 않는다.** 형식을 섞어 유도하면 한쪽에서만 도는 규칙이 되므로, 컴파일이 섞임을 경고하고 신호가 적은 쪽을 홀드아웃으로 민다.

### 00.4.2 구조화 두 경로와 그 연결

같은 파싱 결과(`ParseResult`) 위에 구조화 경로가 둘이다.

- **형식 경로**(§3) — 유형을 아는 문서. registry의 형식 파일 마커로 결정론 구조화 + 적합도 게이트. 라우터(`router.route`)와 검수 화면이 같이 쓴다.
- **유도 경로**(§4 구조 해석기) — 유형을 모르는 문서. 형식 없이 S0~S6으로 구조를 유도하고, 같은 fingerprint가 재현되면 frame을 동결한다.

무엇으로 자를지는 **연결(binding)**이 정한다: 폴더 → 틀이 기본 단위이고, 특이한 문서 하나는 문서 → 틀로 예외를 건다(문서 연결이 폴더 연결을 이긴다). 정본은 문서 스토어 옆 `format_bindings.json`이고, 화면은 `/bindings/`(구조화 연결 캔버스)다. 연결이 없으면 유도 경로로 간다.

연결·틀의 수명 규칙:

- 문서 삭제·폴더 이름 변경·폴더 삭제는 **연결을 함께 옮기거나 지운다.** 안 따라가면 조용히 끊기거나(이름 변경), 같은 이름의 폴더를 다시 만들 때 죽은 틀이 되살아난다.
- 저장된 결과에는 무엇으로 잘렸는지 남는다(`structured_by`: `induce` / `lawxml` / `format:<유형>@v<n>`). 지금 규칙과 다르면 **낡은 결과**로 표시하고 다시 해석하게 한다 — 연결을 바꿔도 결과는 자동으로 갱신되지 않는다.
- 틀을 다시 컴파일하면 `format_version`이 오르고, 그 틀로 잘린 문서는 모두 낡음으로 잡힌다.
- 법령 XML은 태그가 곧 구조라 틀을 붙이지 않는다(붙이면 원문이 아니라 검수용 합성 지면을 자르게 된다). 컴파일 샘플에서도 제외된다.

### 00.4.3 형식 만들기 — 컴파일 국면을 화면에서

CLI(`core.cli compile`)와 같은 절차를 이미 올라온 문서로 돌린다(`POST /v1/formats/compile`): 샘플 파싱(캐시 재사용) → 마커 체계 유도(규칙 기본, LLM 선택) → 적용 미리보기 → 홀드아웃 검증(샘플 4개↑) → 형식 저장 → registry 등재 → 연결. 등재는 registry.yaml에 `# --- ui-compiled: <유형> ---` 블록으로 덧붙인다 — 파일을 통째로 재직렬화하면 실측 기록이 담긴 주석이 전부 날아가기 때문이다. 사람이 손으로 등록한 route는 UI가 덮어쓰지도 지우지도 않는다.

### 00.5 거버넌스 — 8개 Agent 병렬 개발 규칙

- **route 추가 = 자유** (Agent 팀 권한). 절차: 샘플 3~5개 확보 → 인식기 결정(재사용/변형/신규) → 용어집 작성 → 형식 파일 확정(홀드아웃 검증) → 게이트 정의(이 유형의 "완전성" 기준) → registry 등록.
- **출력 계약(doc.json 스키마) 변경 = 코어 오너 승인** (드물어야 정상, 목표 0~2회). 판정 질문: *"이 정보가 모든 문서 종류에서 의미를 갖는가?"* 아니면 스키마가 아니라 marker/content/facts로. 승인 시 스키마 버전을 올리고 **전체 Agent의 골든 테스트를 재실행**한다.
- **의존 방향 단방향**: 파싱 로직은 코어 규격을 import하고, 코어는 로직을 registry로만 안다. 코어·공용 라이브러리에 `if doc_type == …` 분기가 생기면 해당 로직은 어댑터로 추방한다.
- **신규 route 온보딩 완료 기준**: 기존 모든 doc_type의 골든 테스트가 그대로 통과한다(새 유형 추가가 기존 유형을 못 건드렸다는 회귀 증명).

### 00.6 Agent ↔ 코어 관계

Agent 개발 절차: 필요한 문서 유형이 registry에 있는지 확인 → 없으면 route 등록(00.5 절차) → Agent 로직 작성(공용 라이브러리 조립). **Agent가 코어·타 로직 코드를 수정하는 일은 없다.** 실증된 예 — Agent1: route 2개(특정금전신탁·투자설명서) 소비, 범위 좁히기 + 대조. Agent6: route 4개 등록(금소법·금소법시행령·표준투자권유준칙·STT전사), 전사는 `router.require`로 받고 규정 코퍼스는 같은 라우터로 구조화해 발췌를 물질화한 뒤 컨텍스트 조립+LLM 판정. 나머지 Agent도 동일 패턴: registry에서 route 조합 선택 → 라이브러리 조립.

---

## 0. 시스템 한눈에 보기

두 개의 국면(phase)으로 동작한다.

**컴파일 국면 (문서 종류당 1회, LLM 사용):**
사용자가 용어집을 등록한다 → 샘플 문서를 파싱한다 → LLM이 (용어집 + Docling 판단을 힌트로 받아) 문서 전체를 보며 section 구분 로직을 만든다 — 반복 마커는 정규표현식으로, 용어형 마커는 용어 매칭으로 — 그리고 미등록 section 용어 후보를 역제안한다 → 사용자가 후보를 section용/fact용으로 판정한다 → **최종 틀(형식, format)** 확정.

**런타임 국면 (매 문서, LLM 없이 결정론):**
새 문서 → 확정된 형식(정규표현식 + section 용어 매칭)으로 구조화 → section별로 데이터(텍스트/표) 적재 → JSON 저장 → 태스크(비교·검색 등)가 이 JSON을 소비.

핵심 원칙:
1. **stochastic은 컴파일 타임에 가둔다.** LLM은 형식을 만들 때 한 번만. 런타임은 결정론.
2. **인식 방법은 마커의 성질이 정한다.** 반복 마커(제N조, ①, [별지N])는 정규표현식. 비반복 마커("신탁계약 세부내역" 같은 제목 문자열)는 section 용어 매칭. 반복하지 않는 것에 정규표현식을 억지로 만들지 않는다.
3. **용어는 이원(二元)이다.** section 용어는 구역 경계가 될 수 있는 용어(문단/구역 레벨), fact 용어는 값을 담는 용어(문장 레벨). 하나의 용어가 둘 다일 수 있다(예: "신탁계약 세부내역"은 section이면서 fact 문장 안에도 등장).
4. **저장은 단순하게.** RDB 없음. 문서당 JSON 파일 하나.

---

## 1. 용어집 (Glossary)

### 1.1 개념

사용자가 시스템에 주는 최우선 입력. 파일: `glossary/{doc_type}.glossary.yaml`

- **section 용어**: 문서의 구역(section) 경계로 쓰일 수 있는 용어. section은 문단/구역 레벨 개념이다. 예: "신탁계약 세부내역", "세부 운용지시", "기타 특약사항".
- **fact 용어**: 값이 붙는 내용 용어. fact는 문장 레벨 개념이다. 예: "신탁금액", "신탁보수", "계좌번호".
- 한 용어가 **양쪽 모두**에 속할 수 있다. "신탁계약 세부내역"은 별지1의 section 제목이면서, 본문 문장("… [별지1] 신탁계약 세부내역에 기재된 …") 안에 fact-레벨 mention으로도 등장한다. 이 경우 `kind: [section, fact]`.

### 1.2 파일 포맷

```yaml
# glossary/trust_contract.glossary.yaml
version: 1
doc_type: 특정금전신탁

terms:
  신탁계약 세부내역: { kind: [section, fact] }
  세부 운용지시:     { kind: [section] }
  기타 특약사항:     { kind: [section] }
  신탁자금 운용방법:  { kind: [section, fact] }
  신탁금액:  { kind: [fact], value_type: number, aliases: [투자금액, 신탁원금] }
  신탁기간:  { kind: [fact], value_type: date_range, aliases: [투자기간, 계약기간] }
  신탁보수:  { kind: [fact], value_type: percent, aliases: [보수율, 운용보수] }
  중도해지수수료: { kind: [fact], value_type: range_tiers, aliases: [해지수수료] }
  계좌번호:  { kind: [fact], value_type: account_no }
```

- `value_type`은 fact 용어에만: `number | date | date_range | percent | range_tiers | option_set | account_no | text` (기본 text).
- `aliases`: 다른 문서(예: 투자설명서)에서 같은 의미로 쓰이는 표면형. 다대일.
- 용어집은 살아있는 파일이다 — 컴파일 국면의 후보 승격(§2.4)과 운영 중 추가로 자란다.

### 1.3 mention vs section-marker 구별 (동일 문자열 문제)

"신탁계약 세부내역"이라는 글자는 (a) 별지1의 제목(section 경계)으로도, (b) 본문 문장 속 참조(fact-레벨 mention)로도 나타난다. 구별은 **레이아웃 신호**로 한다: Docling이 heading/제목형 요소로 분류한 위치 + 줄 단독 출현이면 section 경계, paragraph 내부 출현이면 mention. 애매한 소수는 컴파일 시 LLM이 판단하고 형식에 고정한다. 런타임에는 이 판단이 형식에 이미 박혀 있으므로 재판단이 없다.

---

## 2. 컴파일 국면 — 형식(format) 만들기

### 2.1 입력

- 같은 종류의 샘플 문서 3~5개 (1개만 있으면 1개로 진행하되 형식 신뢰도를 낮음으로 표기)
- 용어집 (§1)

### 2.2 파싱 (Docling)

각 샘플을 Docling으로 변환: 요소 리스트 `{index(reading_order), type, text|table, page, bbox, meta}`. born-digital 전제이므로 OCR 금지(텍스트 레이어 사용 — `is_born_digital()`로 확인하고, 아니면 경고와 함께 OCR로 내려간다). 표는 셀 구조 보존. Docling 버전은 `parse_adapter.docling_version()`이 파싱 결과에 기록한다.

구현(`core/parse_adapter.py`)에서 확정된 세 가지 — v1에서 잃었던 자리다:
- **읽기 순서**는 `doc.iterate_items()`로 얻는다. `doc.texts`/`doc.tables`를 이어붙이면 표가 전부 문서 끝으로 밀린다. 머리말/꼬리말 레이어(FURNITURE)도 함께 받는다 — 실측에서 `[별지1]`이 page_header로 분류됐고, 그것을 못 받으면 별지1 구역을 통째로 놓친다.
- **표의 논리 셀**은 `table.data.table_cells`(span 정보 보존)를 쓴다. `table.data.grid`는 병합 셀을 덮는 칸마다 복제한다.
- **리스트 마커**는 되붙인다. docling이 `1. `을 `marker`로 떼어내므로 `text`만 쓰면 호 번호가 사라져 `^\d+\.` 정규식이 영영 안 맞는다.

**파서는 플러그인이다.** 이 docling 어댑터는 registry의 `parsers.auto`(= `core.parse_adapter:parse`)일 뿐이고, route가 자기 `parser` ID로 무엇을 쓸지 고른다. 페이지·bbox가 없는 문서(예: STT 전사)는 다른 플러그인(`parsers.transcript`)이 처리하며, 그 문서 고유의 출처(발화 타임스탬프 등)는 스키마 확장 없이 `Element.meta`에 담는다.

**주의 — Docling의 heading 분류는 참고 신호이지 진리가 아니다.** 레이아웃 모델은 학습 분포(주로 서구권 논문·보고서) 밖 문서에서 오분류할 수 있다. 최종 판단은 §2.3에서 텍스트 패턴·용어집과 교차해 LLM이 내리고, 형식에 고정된다.

### 2.3 LLM 형식 유도 (문서 종류당 1회)

LLM에게 다음을 제공한다:
1. 샘플 문서의 파싱 결과 (요소 리스트, Docling의 type 판단 포함)
2. 용어집 — **파싱 결과 내 용어집 용어의 출현 위치를 사전에 문자열 매칭으로 표시(마킹)해서** 전달한다. LLM이 용어를 새로 찾게 하지 말고, 표시된 출현을 해석하게 한다.

LLM의 임무 (structured output, 낮은 temperature):
- **반복 마커 → 정규표현식 생성.** 제N조, ①②③, N., [별지N] 처럼 번호가 바뀌며 반복되는 마커를 찾아 정규표현식으로 만든다. 여러 샘플에서 공통으로 성립하는 패턴만 채택(한 샘플의 우연 배제).
- **용어형 마커 → section 경계 지정.** 용어집의 section 용어가 heading 위치에 나타난 곳을 section 경계로 확정한다. **정규표현식을 만들지 않는다** — 용어 문자열 매칭으로 충분하며, 비반복 문자열에 패턴을 억지로 씌우면 취약해진다.
- **section 계층 조립.** 정규표현식 마커와 용어형 마커로 나뉜 구역들의 포함 관계(문서 → 대구역 → 조 → 항)를 트리로 제안한다.
- **미등록 section 용어 후보 역제안.** 등록되지 않았는데 구역 경계로 보이며 정규표현식으로 보기 애매한 문자열(예: "신탁자금 운용방법" 소제목이 미등록이었다면)을 후보 목록으로 반환한다. 각 후보에 근거(위치, 반복 여부, heading 신호)를 첨부한다.

### 2.4 사용자 확정

시스템이 사용자에게 보여주는 것: (a) 유도된 형식을 샘플에 **적용한 결과**(어떻게 잘리는지 — 추상 패턴이 아니라 결과를 보여준다), (b) 미등록 후보 목록.

사용자가 하는 일:
- 적용 결과 확인/수정 (인식 작업 — 구조를 서술하게 하지 않는다)
- 각 후보를 판정: **section 용어로 승격 / fact 용어로 등록 / 무시**. 승격분은 용어집에 기록된다.

확정되면 **형식 파일** `formats/{doc_type}.format.json` 생성:

```json
{
  "doc_type": "특정금전신탁",
  "format_version": 1,
  "compiled_from": ["sample1.pdf", "sample2.pdf", "sample3.pdf"],
  "regex_markers": [
    { "id": "조",   "pattern": "^제(\\d+)조\\(([^)]+)\\)", "level": 1, "groups": ["no", "title"] },
    { "id": "항",   "pattern": "^([①-⑳])", "level": 2, "parent": "조" },
    { "id": "호",   "pattern": "^\\s*(\\d+)\\.\\s", "level": 3, "parent": "항" },
    { "id": "별지", "pattern": "^\\[별지(\\d+)\\]", "level": 0, "groups": ["no"] }
  ],
  "term_markers": [
    { "term": "신탁계약 세부내역", "level": 1, "under": "별지1" },
    { "term": "신탁자금 운용방법", "level": 2, "under": "별지1" },
    { "term": "세부 운용지시",     "level": 2, "under": "별지1" },
    { "term": "기타 특약사항",     "level": 2, "under": "별지1" }
  ],
  "hierarchy": ["문서", "별지|본문", "조|용어section", "항", "호"]
}
```

### 2.5 컴파일 검증 (형식 오추출 방어 1)

형식 유도에 쓰지 않은 **홀드아웃 샘플**에 형식을 적용해 검증한다(샘플 5개면 3개로 유도, 2개로 검증). 검증 항목: 조 개수·연속성, section 경계 수, 용어집 fact 용어의 검출 수, 어느 section에도 안 속한 잔여 비율. 실패 시 형식을 확정하지 않고 사용자에게 불일치 지점을 보고한다.

---

## 3. 런타임 국면 — 결정론 구조화

### 3.1 파이프라인 (매 문서, LLM 없음)

1. **파싱**: Docling → 요소 리스트 (§2.2와 동일 설정)
2. **section 분할**: 형식 파일의 `regex_markers` + `term_markers`(heading 위치의 용어 매칭)로 요소들을 section 트리에 배정. 모든 요소는 정확히 하나의 최심(deepest) section에 속한다.
3. **데이터 적재**: 각 section에 내용을 담는다 — 텍스트면 텍스트로, 표면 셀 구조 보존한 표로.
4. **fact 추출**: 각 section 내에서 용어집의 fact 용어를 매칭하고, `value_type` 파서로 값을 정규화한다(§3.3).
5. **적합도 게이트** (§3.4) 통과 시 JSON 저장.

### 3.2 저장 — 문서당 JSON 하나 (RDB 없음)

`output/{stem}.doc.json`:

```json
{
  "doc_type": "특정금전신탁",
  "format_version": 1,
  "source_file": "contract_123.pdf",
  "generated_at": "2026-08-05T02:11:07+00:00",
  "sections": [
    {
      "section_id": "본문/제2조",
      "marker": { "kind": "regex", "id": "조", "no": 2, "title": "신탁금액" },
      "path": ["문서", "본문", "제2조(신탁금액)"],
      "page_range": [1, 1],
      "content": [
        { "type": "text", "text": "① 이 신탁의 신탁금액은 [별지1]신탁계약 세부내역에 기재된 금액으로 한다.", "page": 1 }
      ],
      "children": ["본문/제2조/①", "본문/제2조/②", "본문/제2조/③"]
    },
    {
      "section_id": "별지1/신탁계약 세부내역",
      "marker": { "kind": "term", "term": "신탁계약 세부내역" },
      "path": ["문서", "별지1", "신탁계약 세부내역"],
      "page_range": [5, 5],
      "content": [
        { "type": "table", "cells": "…셀 구조 보존…", "page": 5 }
      ],
      "children": []
    }
  ],
  "facts": [
    {
      "fact_id": "f-001",
      "term": "신탁금액",
      "section_id": "별지1/신탁계약 세부내역",
      "value_type": "number",
      "value": 100000000,
      "raw": "금 1억원정 (₩100,000,000)",
      "source": { "page": 5, "bbox": [182, 214, 460, 238] }
    }
  ],
  "fitness": { "score": 0.97, "passed": true, "warnings": [],
               "detail": { "parts": { "marker_density": 1.0, "ordinal_continuity": 1.0,
                                      "residual": 1.0 } } }
}
```

- `sections`: 형식이 자른 구역 트리. section마다 마커 종류(regex/term), 경로, 내용(텍스트/표), 출처.
- `facts`: 용어집 fact 용어의 출현과 정규화된 값. 항상 소속 `section_id`를 가진다 — **"어떤 섹션의 어떤 용어"가 모든 downstream 태스크의 기본 좌표다.**

### 3.3 값 정규화 (value_type 파서)

fact의 `value`는 원문이 아니라 파싱된 타입값이다. 비교·계산은 항상 `value`로, 표시·감사는 `raw`+`source`로.

| value_type | 정규화 규칙 |
|---|---|
| number | 억·만·원, ₩, 콤마 해석 → Decimal |
| date / date_range | 한국어 날짜 표기 → ISO. range는 {start, end} |
| percent | "연 1.5%", "1.50" → Decimal |
| range_tiers | 다단 조건 → [{cond, rate}] 리스트 |
| option_set | 체크된 항목의 집합 |
| account_no | 구분자 제거 문자열 |

정규화 실패 시 value=null, `needs_review: true`로 남긴다 — 조용히 버리지 않는다.

### 3.4 적합도 게이트 (형식 오추출 방어 2)

매 문서 구조화 후 채점한다. **형식 부합만** 재는 세 축이다(합 1.0):

| 항목 | 가중치 | 재는 것 |
|---|---|---|
| `marker_density` | 0.35 | 형식이 선언한 마커가 실제로 검출됐는가 |
| `ordinal_continuity` | 0.35 | 번호가 이어지는가 (제1조~제32조 중간이 비지 않았는가) |
| `residual` | 0.30 | 형식이 설명하지 못한 잔여(기본 구역 질량)가 적은가 |

임계 미달이면 **처리 결과를 확정하지 않고 격리** — "이 문서는 형식 v1과 N%만 부합. 다른 양식이거나 양식이 개정되었을 수 있음." 조용한 실패 금지.

용어집 fact 검출률(`fact_coverage`)은 뺐다: 용어가 유형별 용어집이 아니라 전역으로 가면 "이 유형이라면 이 용어들이 잡혀야 한다"는 기대치 자체가 성립하지 않는다. 값 정규화에 실패한 fact(`needs_review`)는 채점과 무관하게 경고로 알린다 — 판정 근거로 쓰이기 전에 사람이 봐야 하는 상태다.

### 3.5 형식 버전 관리 (형식 오추출 방어 3)

격리 문서가 누적되며 특정 시점 이후 집중되면 양식 개정 신호다. 격리 문서들을 새 샘플로 재컴파일(§2)하고 `format_version`을 올린다. 문서 JSON에 사용된 형식 버전이 기록되므로 소급 추적이 가능하다.

---

## 4. 태스크 계층 — JSON을 소비하는 로직들

모든 태스크는 `*.doc.json`만 읽는다. 파서·LLM에 접근하지 않는다.

### 4.1 정합성 비교 (신탁계약서 ↔ 투자설명서)

비교는 **"어떤 문서의 어떤 section에 있는 어떤 용어" ↔ "다른 문서의 어떤 section의 내용"** 을 잇는 매핑 규칙으로 정의된다. 파일: `tasks/reconcile_{pair}.yaml` (실물: `agents/agent1/tasks/reconcile_trust_vs_prospectus.yaml`). 스키마는 `core/reconcile.py`의 `TaskSpec`이다.

```yaml
# agents/agent1/tasks/reconcile_trust_vs_prospectus.yaml
source_of_truth: 특정금전신탁          # 정답 문서의 doc_type — **문자열이다**(중첩 매핑 아님)
target: 투자설명서                     # 대상 문서의 doc_type — 문자열
rules:
  - source: { section: "별지1/신탁계약 세부내역", term: 신탁금액 }
    target: { section_any_of: ["계약 개요", "투자조건"], term: 신탁금액 }  # alias로 투자금액 등도 매칭
  - source: { section: "별지1/신탁계약 세부내역", term: 기본보수 }
    target: { section_any_of: ["보수 및 수수료"], term: 기본보수 }
  - source: { section: "별지1/신탁계약 세부내역", term: 중도해지수수료 }
    target: { section_any_of: ["보수 및 수수료", "중도해지수수료", "환매"], term: 중도해지수수료 }
```

스키마 제약 — 어기면 `TaskSpec` 검증에서 로드가 실패한다:
- `source_of_truth` · `target`은 **문자열**(doc_type)이다. `{doc_type: …}` 같은 중첩 매핑은 받지 않는다.
- rule의 `source` · `target`은 **둘 다 필수**이며 각각 `term`이 있어야 한다. `target: null`(대응 개념 없음 → `NOT_APPLICABLE`)은 이 엔진에 **미구현**이다. 그 선언이 필요한 태스크는 §4.1 엔진이 아니라 agent1의 LLM 판정 파이프라인이 쓴다(AGENT1_SPEC §2.3).
- section 지정은 `section`(완전 경로) 또는 `section_any_of`(경로 성분 목록) 중 하나. `section_any_of`는 `section_id`를 `/`로 쪼갠 성분 중 하나와 일치하면 적중이다.
- 표면형 차이(투자금액 ↔ 신탁금액)는 각 문서 용어집의 aliases가 이미 흡수했으므로 rule에는 **정규 용어명만** 쓴다.

엔진 동작 (정답 기준 순회, `reconcile.run(source_doc, target_doc, task)`):
1. 각 rule의 source에서 fact를 찾는다 (facts에서 section_id+term 조회). 같은 용어가 본문 문장에서도 잡히므로 값 정규화에 성공한 fact를 먼저 고른다.
2. target 문서에서 대응 fact를 찾는다 — 지정된 section들 안에서.
3. `value_type` 비교기로 값 대조 (§3.3의 타입값끼리, 결정론).
4. 판정 5종: `MATCH / VALUE_MISMATCH / MISSING_IN_TARGET / UNMAPPED / NEEDS_REVIEW`.
   - 정답 쪽에 값이 없으면 → `NEEDS_REVIEW`(대조 기준 자체가 없다).
   - 대상 문서에 용어는 있는데 지정 section에 없으면 → `MISSING_IN_TARGET`, 용어 자체가 없으면 → `UNMAPPED`(용어집 aliases 보강 신호).
5. 리포트 행마다 양쪽 `raw`+`ref`(doc/page/bbox) 인용. 리포트에는 행 외에 `stats`(판정별 개수)와 `gate`(양쪽 문서의 적합도)가 함께 실린다.

원칙: source(정답)의 rule은 전부 리포트에 한 행씩 나타난다 — 누락·미매핑도 행으로. LLM은 판정에 개입하지 않는다.

CLI: `python -m core.cli reconcile <source.doc.json> <target.doc.json> --task <yaml>`.

### 4.2 검색 (선택 소비자)

임베딩 없음. 질의 → 용어집 매칭(aliases 포함)으로 term 확정 → facts 직조회(값 질문) 또는 section 필터+키워드(해석 질문) → section의 `path`·`content`로 답과 출처 제시. 한국어 키워드 매칭은 형태소 분석기(예: kiwipiepy) 사용.

**현황: 미구현**(T12, 선택). 저장소에 검색 소비자 모듈은 없다. kiwipiepy도 현재 환경에 설치돼 있지 않다 — 형태소 의존 코드는 없을 때 문자 정규화로 자동 강등하고 그 사실을 산출물에 남긴다(선례: `agents/agent6/src/preprocess.py`의 `Normalizer`).

---

## 5. 구현 작업 (빌드 오더)

상태 표기: **[구현됨]** = 코드가 저장소에 있고 테스트가 돈다, **[미구현]** = 아직 없다.

- **T0. 라우터·등록부·doc.json 계약** — §00 전부. `core/registry.yaml`(등록부 + 파서 플러그인 표), `core/router.py`(유일한 진입점: `route` / `require` / `describe`, 명시·자동 두 모드, doc_type 3중 일치 검사), `core/structurize.py`의 `Document.dump()`(출력 계약), `tests/architecture/test_no_bypass.py`(우회 금지). **[구현됨]** — T1~T12는 이 계약 위에서 조립된다. 이 항목이 없으면 §00은 실행할 수 없는 지시였다.
- **T1. 용어집 로더** — glossary YAML 파싱·검증 (pydantic). kind 이원화, value_type, aliases. `core/glossary.py` **[구현됨]**
- **T2. 파싱 어댑터** — Docling 호출·요소 정규화. 버전 기록. `core/parse_adapter.py` **[구현됨]**
- **T3. 용어 마킹기** — 파싱 결과에 용어집 용어 출현을 표시 (컴파일 국면의 LLM 입력 준비). `core/term_marker.py` **[구현됨]**
- **T4. LLM 형식 유도기** — §2.3. structured output 스키마 = 형식 파일 스키마 + 후보 목록. `core/format_induce.py` **[구현됨]**
- **T5. 확정 인터페이스** — CLI: 적용 결과 미리보기(`--preview`), 후보 승격(`--promote 이름:section|fact`), 용어집·형식 파일 기록. `core/cli.py compile` **[구현됨]**
- **T6. 홀드아웃 검증기** — §2.5. `core/holdout_check.py` **[구현됨]**
- **T7. 런타임 구조화기** — §3.1-3.2. regex_markers+term_markers로 section 트리, 내용 적재, JSON 출력. `core/structurize.py` **[구현됨]**
- **T8. 값 정규화기** — §3.3 타입별 파서 8종 + 비교기. `core/normalize.py` **[구현됨]**
- **T9. 적합도 게이트** — §3.4 채점·격리. `core/fitness_gate.py` **[구현됨]**
- **T10. 비교 엔진** — §4.1. rule 로더 + 정답 기준 순회 + 타입 비교기 + 리포트. `core/reconcile.py` **[구현됨]**
- **T11. 골든 테스트** — 실물 자산이 이미 저장소에 있다: `agents/agent1/data/samples/ss2207_special_trust.pdf`(빈 템플릿 — 구조화 검증용)와 **값이 채워진 쌍** `agents/agent1/data/golden/{contract_filled.pdf, prospectus.md}`(비교 검증용). 테스트는 `tests/core/`(빠른 회귀, docling 불필요) · `tests/agent1/`(실물 PDF 골든) · `tests/agent6/`(코퍼스 빌드·when DSL) · `tests/architecture/`(우회 금지). **[구현됨]**
  변이 테스트(골든 쌍을 의도적으로 훼손해 정확히 해당 판정이 나는지)는 **[미구현]** — 현재는 실물 쌍에 이미 존재하는 불일치를 고정 검증한다(`tests/agent1/test_golden.py::test_real_mismatch_is_caught`).
- **T12. (선택) 검색 소비자** — §4.2. **[미구현]**

증분 개발: 각 태스크마다 샘플 PDF로 즉시 검증 후 진행.

## 6. 저장소 구조

**핵심 규칙: 코어는 범용, 도메인 지식은 에이전트 폴더의 데이터 파일에.** 새 에이전트 = 새 폴더 + 새 데이터 파일이지 새 코드가 아니다.

```
core/                          범용 모듈. 문서 종류·에이전트를 모른다
  registry.yaml           T0  등록부 (route + 파서 플러그인 표)
  router.py               T0  유일한 진입점 (route / require / describe)
  glossary.py             T1  용어집 로더 (section/fact 이원)
  parse_adapter.py        T2  docling·markdown → 요소 리스트
  term_marker.py          T3  용어 출현 표시 (mention vs section-marker)
  format_model.py             형식 파일 스키마
  format_induce.py        T4  LLM 형식 유도 (컴파일 전용)
  holdout_check.py        T6  홀드아웃 검증
  structurize.py          T7  런타임 구조화 (LLM 없음) — doc.json 계약
  normalize.py            T8  값 정규화 + 비교기
  fitness_gate.py         T9  적합도 게이트 (격리)
  reconcile.py            T10 비교 엔진
  llm.py                      LLM 래퍼
  cli.py                      범용 CLI (compile / structurize / routes / reconcile / inspect)
  reading_order.py            읽기 순서 복원 (다단 조판)
  structure/                  구조 해석기 — 범용 계층구조 인식 (docs/structure_interpreter_SPEC.md)
    proposers/ guards/        구분자 계열 제안자 · 지역 가드
    global_outer/ global_inner/  레벨 사다리 · 트리 조립
    family/ lexicon/          계열 응집 · 언어 자원(조사·수사 yaml)
    pipeline.py registry.py scoring.py resolve.py viewer.py cli.py

agents/agent1/                 신탁계약서 ↔ 투자설명서 대사 (AGENT1_SPEC.md)
  glossary/*.glossary.yaml     사용자 최우선 입력 (§1)
  formats/*.format.json        컴파일 산출물 (§2.4)
  tasks/                       reconcile_trust_vs_prospectus.yaml (core 엔진용, §4.1)
                               agent1_trust_vs_prospectus.yaml    (LLM 판정 파이프라인용)
  data/samples · data/golden
  src/  service.py(코어 조립) · scope.py · judge.py · pipeline.py · cli.py
  output/{stem}.doc.json · *.report.json

agents/agent6/                 녹취 체크리스트 점검 (AGENT6_SPEC.md)
  checklist/items/*.yaml       항목 스펙 30개
  corpus/{raw,structured,excerpts} · manifest.json
  formats/ · glossary/         법령·준칙·전사 route 자산
  src/  corpus_build.py · preprocess.py · context_asm.py · judge.py · basis.py
        aggregate.py · report.py · harvest.py · llm_cache.py
        when.py · transcript.py · schema.py · cli.py
  output/report.json · guidance.md · review_queue.jsonl   (생성물 — gitignore)

api/                           FastAPI. app.py(레거시 두 엔진) · structure_app.py(구조 해석기)
deploy/structure/              기본 서비스 이미지 — 루트 docker-compose.yml 이 이걸 쓴다
deploy/api/                    레거시 2엔진 이미지 + 자체 compose
docs/                          SPEC.md · AGENT1_SPEC.md · AGENT6_SPEC.md
                               structure_interpreter_SPEC.md
tests/  core · agent1 · agent6 · architecture
archive/trust-parser-v1/       v1(온톨로지 기반) 보존. api/app.py 가 이것을 참조한다
first-agent/                   v0(LLM 해석) 보존. api/app.py 의 /v1/agent/* 엔진.
                               기본 서비스 이미지에는 들어가지 않는다(.dockerignore)
```

## 7. 완료 기준

1. **컴파일**: 샘플 3개+홀드아웃 2개로 특정금전신탁 형식이 유도·검증되고, "제N조/①/N./[별지N]"은 regex_markers로, "신탁계약 세부내역" 등은 term_markers로 분리돼 있다(비반복 문자열에 정규표현식 없음). 미등록 후보가 근거와 함께 제시된다.
2. **런타임 결정론**: 같은 문서를 두 번 구조화하면 JSON이 동일하다(LLM 미개입).
3. **구조화**: `ss2207_special_trust.pdf`에서 본문 제1~32조 전부와 별지1/별지2가 section으로 존재하고, 모든 요소가 정확히 하나의 최심 section에 속하며, 어느 section에도 안 속한 잔여가 게이트에 보고된다.
4. **fact**: 용어집의 fact 용어가 section 좌표와 함께 추출되고, 값 정규화가 타입별 단위 테스트를 통과한다 ("금 1억원" ≡ 100,000,000 등).
5. **비교**: 골든 쌍에서 rule 전부가 리포트에 한 행씩 나타나고(누락·미매핑 포함), 변이 주입 시 정확히 해당 판정이 발화하며, 포맷 차이는 MATCH로 처리된다. 판정 로직에 LLM 없음.
6. **게이트**: 형식과 다른 문서(예: 타사 계약서)를 넣으면 격리되고 부합률이 보고된다.

## 8. 범위 밖 (v3 후보)

- 스캔 PDF OCR (born-digital 전제)
- 체결본 체크박스 √ 검출·손글씨 인식
- 임베딩 검색 채널 (필요 시 §4.2에 추가 채널로)
- 형식 자동 재컴파일 (v2는 수동 트리거)
- 파생값 재계산·기본값 추론 등 추론 기능 (개념은 유효, 구현은 미래. v1 구현이 `archive/trust-parser-v1/src/derive.py`에 남아 있다 — v1 스펙 문서는 저장소에 없다)