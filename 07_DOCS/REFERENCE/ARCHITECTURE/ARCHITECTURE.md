# 아키텍처 — 무엇을 하고, 어떤 기제로 되어 있는가

> **2026-08-18 주의** — 이 문서는 lawrag/core/agents 초기 구도(2026-08-06)를 설명한다. 그 뒤 agent1·deploy(컨테이너)·archive/first-agent 코드는 삭제됐고(문서만 [archive/](../ARCHIVE/)), 뿌리 CLI 는 `pipeline/` 로 갔다. 현행 구조는 [ARCH_SYSTEM.md](ARCH_SYSTEM.md)·README 의 트리를 보라.
>
> 처음 오는 사람을 위한 문서. **왜 이렇게 생겼는지**를 먼저 말하고, 그 다음에 부품을 짚는다.
> 실행 방법은 [../README.md](../README.md), 규격의 정본은 [SPEC.md](SPEC.md) 에 있다.

---

## 0. 한 문장

**문서를 구조로 만드는 층(`core/`)과 그 구조 위에서 업무를 보는 층(`agents/`)이 분리돼 있다.**

`core` 는 신탁계약서도 금소법도 모른다. "구분자로 계층을 표현하는 문서"만 안다.
도메인 지식(어떤 용어가 중요한가, 무엇과 무엇을 대조하는가)은 전부 `agents/` 아래
**데이터 파일**에 있다. 그래서 새 업무를 붙이는 일은 새 코드가 아니라 새 폴더 + 새 데이터다.

```
문서 ─▶ [ core: 파싱 → 구조화 ] ─▶ doc.json ─▶ [ agents: 서비스 로직 ] ─▶ 리포트
         결정론이 기본                공통 그릇        판정·대조·점검
```

---

## 1. 가장 중요한 설계 결정 세 가지

이 셋만 이해하면 나머지는 따라온다.

### 1-1. stochastic 을 컴파일 타임에 가둔다

LLM 은 **형식을 만들 때 한 번**만 쓰고, 매 문서를 처리하는 런타임에서는 쓰지 않는다.

| | 컴파일 국면 | 런타임 국면 |
|---|---|---|
| 언제 | 문서 **종류당 1회** | **매 문서** |
| LLM | 쓴다 (형식 유도) | 안 쓴다 — `lawrag/core/llm.py` 가 import 조차 안 된다 |
| 산출 | `*.format.json` (마커 선언) | `*.doc.json` (구조 + 값) |
| 성질 | 사람이 확정한다 | 같은 입력 → 같은 출력 (바이트 동일) |

왜: 매 문서마다 LLM 이 개입하면 같은 계약서가 어제와 오늘 다르게 잘린다. 금융 문서
검증에서 그건 기능이 아니라 결함이다. 형식이라는 **고정된 산출물**을 사이에 끼워
넣어 비결정성을 한 지점에 묶어 둔다.

예외는 둘뿐이고, 둘 다 **결정론이 먼저 다 하고 남은 것만** 본다:
- 구조 해석기의 잔여 해소(S5b) — 문서당 **배치 1콜**, 대개 0콜
- agent6 의 판정 — 대조 대상이 값이 아니라 **행위**라서 `==` 로 잴 수 없다

### 1-2. 등록부가 처리 규칙을 정한다 — 에이전트가 아니라

`lawrag/core/registry.yaml` 한 파일이 "지금 무엇을 처리할 수 있는가"의 답이다.
그리고 `lawrag/core/router.py` 는 **형식·용어집 경로를 인자로 받지 않는다.**

```python
routed = router.route("계약서.pdf", doc_type="특정금전신탁")
doc = routed.doc          # doc.json
```

호출자는 `doc_type` 만 말할 수 있다. 무엇으로 파싱하고 어떤 형식으로 자를지는 등록부가
정한다. 따라서 **같은 doc_type 은 누가 부르든 같은 규칙으로 처리된다.**

이전에는 에이전트마다 `--format` 경로를 손으로 넘겼고, agent1 과 agent6 이 같은 문서를
다르게 자를 수 있었다. 리뷰로 막을 수 있는 실수가 아니라서 — 한 줄이고, 그럴듯하고,
조용하다 — [tests/architecture/test_no_bypass.py](../../../05_TESTS/REGRESSION/architecture/test_no_bypass.py)
가 `agents/` 아래 소스를 **AST 로 훑어** 우회를 문법 수준에서 막는다.

금지되는 것은 자산을 *고르는 것*이지 읽는 것이 아니다:

    core.glossary.load / core.format_model.load    처리 규칙을 직접 고름   ✗
    core.parse_adapter.parse                       파서를 직접 고름        ✗
    "*.format.json" 경로 리터럴                     경로를 코드가 짚음      ✗
    router.assets(routed.route)                    등록부가 준 것을 읽음    ✓

### 1-3. 조용한 실패를 금지한다

이 시스템에서 가장 위험한 실패는 오류가 아니라 **형식이 안 맞는 문서를 그럴듯한
JSON 으로 내보내는 것**이다. 아무도 이상하다고 생각하지 않기 때문이다. 그래서 층마다
게이트가 있고, 미달이면 결과를 확정하지 않는다.

| 게이트 | 무엇을 막는가 | 미달 시 |
|---|---|---|
| 홀드아웃 검증 (`lawrag/core/holdout_check.py`) | 샘플에만 맞는 형식 | 형식을 확정하지 않는다 |
| 적합도 게이트 (`lawrag/core/fitness_gate.py`) | 다른 양식·개정된 양식 | **격리** — "형식 v2 와 53%만 부합" |
| 검수 payload (`lawrag/core/review.py`) | 형식이 못 먹은 자리 | 사람에게 보인다 |
| 판정 (`lawrag/core/reconcile.py`) | 애매한 대조 | auto-pass/fail 금지, `NEEDS_REVIEW` |

적합도 채점은 네 항목의 가중합이다 — 마커 밀도 0.25 / 번호 연속성 0.25 /
fact 커버리지 0.30 / 잔여 0.20. 기본 임계는 0.70 이고 doc_type 마다 등록부에서 바꾼다.

---

## 2. core — 문서를 구조로

`core/` 안에는 성격이 다른 두 갈래가 있다. 헷갈리기 쉬운 지점이라 먼저 가른다.

| | **용어집·형식 기반** (`core/*.py`) | **구조 해석기** (`lawrag/core/structure/`) |
|---|---|---|
| 무엇을 아는가 | 이 문서 종류의 용어·마커를 **미리 안다** | 아무것도 모른다. 구분자만 본다 |
| 준비물 | glossary + format (컴파일 필요) | 없음 — 문서를 그냥 넣는다 |
| 산출 | `doc.json` (sections + **facts** + fitness) | 구조 트리 + 재현용 frame |
| 쓰는 곳 | agent1 값 대조, agent6 route | 검수 화면, 법령·약관 등 미등록 문서 |
| 언제 쓰나 | 양식이 고정된 문서를 반복 처리할 때 | 처음 보는 문서의 계층을 알고 싶을 때 |

### 2-1. 용어집·형식 기반 파이프라인

```
컴파일 (문서 종류당 1회, LLM)
  glossary.py      T1  용어집 로더 — 사용자가 주는 최우선 입력
       ↓                (section 용어 / fact 용어 이원)
  parse_adapter.py T2  docling·markdown → 정규화된 요소 리스트
       ↓                (+ reading_order T2b · typography T2c · grid_recover T2c)
  term_marker.py   T3  용어 출현 표시 — mention 인가 section 경계인가
       ↓
  format_induce.py T4  LLM 형식 유도 → *.format.json
       ↓
  holdout_check.py T6  홀드아웃 검증 → 사람이 확정

런타임 (매 문서, LLM 없음)
  router.py        T0  등록부를 보고 배차            ← 에이전트가 부르는 유일한 문
       ↓
  parse_adapter.py T2  문서 → 요소 리스트
       ↓
  structurize.py   T7  형식으로 section 트리 + fact  ← 규칙 세 개가 전부
       ↓
  fitness_gate.py  T9  적합도 채점 → 통과 or 격리
       ↓
  doc.json
```

**구조화 규칙은 세 개다** (`structurize.py`):

1. 요소가 **regex 마커**에 적중하면 그 레벨에 새 section 을 연다
2. 요소가 제목 위치의 **용어형 마커**면 그 레벨에 새 section 을 연다
3. 어느 것도 아니면 **가장 깊은 열린 section 의 내용**이 된다

세 번째가 "모든 요소는 정확히 하나의 최심 section 에 속한다"를 보장한다.
본문을 판별하는 게 아니라 **나머지로 정의**하는 것이 핵심이다 — "이게 본문이다"라고
말해 주는 공통 특징은 없지만 별지 경계는 명시적이고 유일하다. 확실한 쪽만 positive 로
잡고 나머지를 기본 구역에 담는다.

**인식 방법은 마커의 성질이 정한다.** 번호가 바뀌며 반복되는 것(`제N조`·`①`·`[별지N]`)만
정규표현식이고, 비반복 제목("신탁계약 세부내역")은 **용어 매칭**이다. 비반복 문자열에
정규표현식을 억지로 씌우면 취약해진다.

### 2-2. 구조 해석기 (`lawrag/core/structure/`)

용어집도 형식도 없이, **구분자만 보고** 계층을 복원한다. 법령·약관처럼 양식이 제각각인
문서를 처음 만났을 때 쓴다. 파이프라인은 고정이고 **신호는 plug-in** 이다.

```
S0 발화 탐지     제안자들이 후보를 낸다 (판단 0, 순수 수집)
S1 국소 채점     가드가 후보 하나하나를 깎는다
S2 계열 정합     사다리 없이 계열 안에서 구조 / 인용을 가른다
S3 레벨 유도     정제된 후보로 레벨 사다리를 만든다
S4 전역 선택     DP 로 트리 확정
S5 게이트        정상 / cold 라우팅 / 잔여 LLM 배치 1콜(S5b) / VLM 제목(S5c)
S6 저장 분기     문서 결과는 항상, frame 등재는 재현 게이트 통과 시에만
```

**S2 가 사다리보다 앞에 있는 것이 이 설계의 핵심**이다. 초판은 레벨을 먼저 정하고
서수로 후보를 걸렀는데, 조(條)처럼 **제목과 같은 글자로 인용되는** 계열은 가드가
인용을 정확히 깎아낼수록 등재 비율이 떨어져 탈락했다. 탈락 → 레벨 없음 → 스코프 없음
→ 제55조와 제51조가 만나지 못함 → 서수 규칙이 영영 발동하지 않음.

서수 비교는 **같은 계열 안에서만** 일어나므로 레벨이 필요 없다 — 초판이 전제한 의존이
실제로는 없었다. 순서를 바꾼 뒤 실측: 금소법 조 251건 → 77건(번호 1~69 연속),
준칙 조 206건 → 0건(인용만 있는 문서라 정확한 판정).

신호는 `registry.py` 가 **role 로 등록만** 한다. 제안자나 가드를 추가해도
`pipeline.py` 는 바뀌지 않는다.

| role | 위치 | 예 |
|---|---|---|
| proposer | `proposers/` | `제N조` · `①` · `1.1` · `가.` · `Ⅰ` · `[별지N]` · 사람이 등록한 패턴 |
| local_guard | `guards/` | 조사(`제19조**에**`는 인용) · construction · 블록 위치 |
| family_coherence | `family/` | 연속 단위(run) · 다음 번호 규칙 · 위치 정당성 |
| global_outer | `global_outer/` | 레벨 사다리 · 들여쓰기 · 형식 일관성 |
| global_inner | `global_inner/` | 계층성 · 서수 단조 |

어휘(조사·수사·인용 술어)는 코드가 아니라 `lexicon/*.yaml` 에 있다. 조사 하나 더하는
일이 파이썬을 고치는 일이 되면 어휘가 자라지 않는다.

### 2-3. doc.json — 공통 그릇

두 갈래든 어느 쪽이든, 아래로 내려가는 계약은 하나다.

```jsonc
{
  "doc_type": "특정금전신탁",
  "format_version": "v2",
  "source_file": "contract_filled.pdf",
  "generated_at": "…",
  "sections": [ { "section_id": "…", "marker": {…}, "path": [...],
                  "level": 2, "content": [...], "children": [...], "parent": "…" } ],
  "facts":    [ { "term": "신탁보수", "value": …, "section_id": "…",
                  "provenance": { "page": 3, "bbox": [...] } } ],
  "fitness":  { "score": 0.98, "breakdown": {...} },
  "residual": [...],              // 있을 때만
  "unmatched_headings": [...]     // 있을 때만
}
```

**"어떤 섹션의 어떤 용어"가 모든 downstream 태스크의 기본 좌표다.** fact 는 자기가
속한 `section_id` 를 반드시 들고 다니고, 화면에 되돌릴 수 있도록 page/bbox 도 갖는다.

---

## 3. agents — 구조 위의 서비스 로직

에이전트는 core 부품을 **조립만** 한다. 각자 폴더 구성이 같다.

```
lawrag/agents/agentN/
  glossary/*.glossary.yaml    용어 등록          ← 도메인 지식
  formats/*.format.json       마커 선언          ← 컴파일 산출물
  tasks/*.yaml   (agent1)     대사 규칙
  checklist/     (agent6)     항목 스펙 30개
  data/corpus/        (agent6)     근거 규정 원문 → 구조화 → 발췌
  data/                       샘플·골든
  output/                     생성물 (gitignore — CLI 로 재생성)
  src/                        조립 코드만
```

### agent1 — 신탁계약서 ↔ 투자설명서 **값** 대조

입력은 파일 두 개, 출력은 대사 리포트다. 자세한 것은
[archive/AGENT1_SPEC.md](../ARCHIVE/AGENT1_SPEC.md).

```
① 파싱·구조화   결정론   두 문서 → section 트리 + fact
② 범위 좁히기   결정론   rule 이 지정한 section 만 꺼내 **증거 표** (ID 부착)
③ 판정         LLM     증거 표를 보고 값 대조. 근거는 **증거 ID 로만** 가리킨다
④ 출처 되돌리기 결정론   증거 ID → page/bbox/cell. 없는 ID → 판정 무효화
```

③ 이 LLM 인데도 안전한 이유는 ④ 다. LLM 은 자유 텍스트로 근거를 쓸 수 없고 **미리
부여된 증거 ID** 만 가리킬 수 있다. 존재하지 않는 ID 를 쓰면 그 판정은 코드가 버린다.
지어낸 근거가 리포트에 실릴 경로가 없다.

판정은 5종이다 — `MATCH` / `VALUE_MISMATCH` / `MISSING_IN_SUMMARY` / `UNMAPPED` /
`NEEDS_REVIEW`. 정답 문서의 rule 은 **전부 한 행씩** 리포트에 나온다. 누락도 미매핑도
행으로 남는다(조용한 스킵 금지).

포맷 차이는 MATCH 로 흡수된다 — `금 1억원정 (₩100,000,000)` ≡ `100,000,000원`,
`24.6.3 ~ 27.6.2` ≡ `2024년 6월 3일부터 2027년 6월 2일까지`.

### agent6 — 녹취 체크리스트 점검 (불완전판매 Zero)

STT 전사 하나를 받아 30개 항목을 점검한다. 자세한 것은
[lawrag/agents/agent6/README.md](../../../02_BACKEND/lawrag/agents/agent6/README.md).

**판정기가 `==` 가 아니라 LLM 인 것**이 agent1 과의 차이다. 검증 대상이 값이 아니라
**행위**이기 때문이다 — "설명의무를 이행했는가"는 문자열 매칭으로 잴 수 없다.

```
preprocess   전사를 펴고, meta(나이·상품)로 활성 항목을 확정 (`when` DSL)
context_asm  항목마다: 운영정의 + **미리 연결한 근거 규정 발췌** + few_shot + 전사 전문
judge        LLM 단독 판정 + 자기일관성 k회 (기본 3)
aggregate    파생 항목 · 라우팅 · 리포트 행
report       report.json · guidance.md · review_queue.jsonl
```

핵심 기제는 **근거 연결**이다. 항목마다 법령·준칙의 어느 조항을 근거로 볼지 미리 이어
두고(`basis`), 그 조항의 실제 원문 발췌를 프롬프트에 넣는다. 근거 없이 판정하면
LLM 이 법을 상상한다. 연결은 `/agent6/` 화면에서 사람이 잇고, 그 결과는 별도 DB 가
아니라 **항목 YAML 자체**에 쓰인다 — 그게 판정 파이프라인이 읽는 정본이고 git 이 이력을
남긴다. 코퍼스 원문도 같은 라우터를 타고 구조화된다(법령이라고 다른 파이프라인이 아니다).

**LLM 없이는 점검할 수 없다.** 예전에는 키가 없으면 문자열 매칭으로 강등해 끝까지
돌았지만, 그 판정기가 사실상 아무것도 잡지 못한다는 것이 적대적 검증에서 드러나
없앴다. 지금은 키가 없으면 그 실행은 **점검 실패**(종료코드 3)다. 테스트가 키 없이 도는
길은 녹화 재생(`--llm-mode replay`)뿐이다.

---

## 4. api — 서비스로 내보내기

두 개의 앱이 있다. **기본은 `structure_app`** 이다.

| | `lawrag/api/structure_app.py` (5566) | `lawrag/api/app.py` (5555) |
|---|---|---|
| 무엇 | 구조 해석 검수 + agent6 근거 연결 | 레거시 두 엔진 (v1 파서 · v0 LLM) |
| 필요한 것 | `core/` + agent6 자산 | `archive/trust-parser-v1/` + `first-agent/` |
| 실행 | `scripts/serve.sh` (호스트 uvicorn) | (2026-08-18 삭제) |

주요 엔드포인트:

```
POST   /v1/structure/documents              PDF 업로드 → 구조 해석
GET    /v1/structure/{doc_id}               검수 payload (트리 + 블록 + 좌표)
GET    /v1/structure/{doc_id}/page/{page}   페이지 PNG (서버 렌더)
POST   /v1/structure/{doc_id}/reinterpret   현재 규칙으로 다시 해석
POST   /v1/structure/rules/custom           표면 패턴 등록 (사람이 어휘를 추가하는 자리)
GET    /v1/agent6/graph                     코퍼스·체크리스트·연결선
POST   /v1/agent6/links                     근거 연결 추가 (항목 YAML 에 기록)
```

**페이지를 서버가 PNG 로 렌더한다.** PDF.js 를 붙이면 CDN·번들에 묶이는데, PyMuPDF 는
파싱 때문에 이미 있다. 이렇게 하면 망 없이 컨테이너 안에서 돈다. 좌표는 0~1 비율로
주므로 화면 배율이 바뀌어도 서버가 배율을 몰라도 된다.

---

## 5. 저장소 지도

```
core/               범용. 문서 종류·에이전트를 모른다
  registry.yaml     등록부 — "지금 무엇을 처리할 수 있는가"의 답
  router.py         유일한 진입점
  structure/        구조 해석기 (proposers · guards · family · global_* · lexicon)
lawrag/agents/agent1/      신탁계약서 ↔ 투자설명서 값 대조
lawrag/agents/agent6/      녹취 체크리스트 점검
api/                FastAPI — structure_app(기본) · app(레거시)
docs/               SPEC + 이 문서 (옛 스펙·QA 질문지는 docs/archive/)
tests/              core · agent1 · agent6 · architecture
archive/            v1(온톨로지 기반) 보존
first-agent/        v0(LLM 해석) 보존 — 기본 이미지에는 안 들어간다
```

**새 에이전트 = 새 폴더 + 새 데이터 파일이지 새 코드가 아니다.**
새 문서 유형 지원 = 코드 수정이 아니라 `registry.yaml` 에 route 등록이다.

---

## 6. 지금 되는 것 / 안 되는 것

측정 기준은 실물 문서다. 추정이 아니다.

| | 결과 |
|---|---|
| 테스트 | 384개 중 **378 passed** (아래 "남은 것" 참조) |
| 구조화 — 빈 템플릿 `ss2207` | section 97, 제1~32조 전부, 별지1·별지2, 잔여 0, 게이트 81% |
| 구조화 — 체결본 | section 97, fact 17, 잔여 0, 게이트 **98%** |
| 구조 해석 — 금소법 | 조 후보 251건 → 77건 (번호 1~69 연속) |
| 구조 해석 — 표준투자권유준칙 | 조 후보 206건 → 0건 (인용만 있는 문서 — 정확한 판정) |
| 런타임 결정론 | 같은 문서 두 번 구조화 → JSON 동일 |

**남은 것**

- **투자설명서 형식 부합률 53%** → 격리. `tests/agent1/test_golden.py` 의 5건이 이것
  때문에 실패한다. 형식이 실물 66p 투자설명서를 아직 못 따라간다.
- **컴파일의 LLM 경로를 실행하지 않았다.** 현재 형식은 규칙 기반 초안(`--no-llm`)이고
  신뢰도가 `low` 로 표기돼 있다. 스키마와 코드는 준비돼 있지만 실제 호출로 검증하지 않았다.
- **스탬프된 값이 인쇄 문구 뒤에 붙는다.** 체결본의 신탁기간이 `20 년 월 일부터 … 6 3 27 6 2`
  로 온다. 좌표로 span 을 끼워 넣어야 한다.
- **체크박스 √ 검출** 미구현. 운용방법 그리드가 24개 조각으로 흩어진다.
- **홀드아웃 샘플이 두 종류뿐**이라 형식 신뢰도가 낮다(규격은 3+2 를 요구).
- **골든 쌍의 값은 합성이다.** 비교 로직은 검증되지만 실물 추출 정확도는 아니다.
- 요구사항 대비 간극(핵심상품설명서·변경대비표·메일 채널)은 [archive/QA_SESSION-agent1.md](../ARCHIVE/QA_SESSION-agent1.md) 참조.

---

## 7. 읽는 순서 제안

1. 이 문서
2. [../README.md](../README.md) — 5분 안에 돌려 보기
3. 맡은 쪽 하나
   - 구조 해석기 → [structure_interpreter_SPEC.md](STRUCTURE_INTERPRETER_SPEC.md)
   - 값 대조 → [../agents/agent1/README.md](../ARCHIVE/AGENT1_SPEC.md) → [archive/AGENT1_SPEC.md](../ARCHIVE/AGENT1_SPEC.md)
   - 녹취 점검 → [../agents/agent6/README.md](../../../02_BACKEND/lawrag/agents/agent6/README.md) → [AGENT6_SPEC.md](AGENT6_SPEC.md)
4. [SPEC.md](SPEC.md) — 플랫폼 규격의 정본. 위 문서들이 §번호로 이걸 가리킨다
