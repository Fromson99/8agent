# core — 문서를 구조로

**이 폴더는 신탁계약서도 금소법도 모른다.** "구분자로 계층을 표현하는 문서"만 안다.
도메인 지식은 전부 `agents/` 아래 데이터 파일에 있다.

전체 그림은 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), 규격의 정본은
[../docs/SPEC.md](../docs/SPEC.md).

---

## 두 갈래를 먼저 가른다

`core/` 안에는 성격이 다른 두 파이프라인이 있다. 처음 보면 가장 헷갈리는 지점이다.

| | **용어집·형식 기반** (`core/*.py`) | **구조 해석기** (`core/structure/`) |
|---|---|---|
| 무엇을 아는가 | 이 문서 종류의 용어·마커를 **미리 안다** | 아무것도 모른다. 구분자만 본다 |
| 준비물 | glossary + format (컴파일 필요) | 없음 — 문서를 그냥 넣는다 |
| 산출 | `doc.json` (sections + **facts** + fitness) | 구조 트리 + 재현용 frame |
| 언제 | 양식이 고정된 문서를 반복 처리 | 처음 보는 문서의 계층을 알고 싶을 때 |
| 쓰는 곳 | agent1 값 대조, agent6 코퍼스 빌드 | 검수 화면(`/`), 미등록 문서 |

---

## 1. 진입점 — 여기만 통한다

```python
from core import router
routed = router.route("계약서.pdf", doc_type="특정금전신탁")
doc = routed.doc          # doc.json
```

`route()` 는 **형식·용어집 경로를 인자로 받지 않는다.** 호출자는 `doc_type` 만 말할 수
있고, 무엇으로 처리할지는 `registry.yaml` 이 정한다. 그래서 같은 doc_type 은 누가 부르든
같은 규칙으로 처리된다. 이 강제는
[../tests/architecture/test_no_bypass.py](../tests/architecture/test_no_bypass.py) 가
`agents/` 소스를 AST 로 훑어 지킨다.

`registry.yaml` 한 파일이 "지금 무엇을 처리할 수 있는가"의 답이다. 새 문서 유형 지원 =
코드 수정이 아니라 **route 등록**이다.

```yaml
routes:
  - doc_type: 특정금전신탁
    detect:   { extension: .pdf, content_any: ["특정금전신탁", "[별지1]"] }
    parser:   auto                                       # parsers 표의 플러그인 ID
    format:   agents/agent1/formats/trust_contract.format.json
    glossary: agents/agent1/glossary/trust_contract.glossary.yaml
    threshold: 0.70
    owner:    agent1
```

판별은 두 모드다. **명시 모드**(기본)는 호출자가 doc_type 을 준다. **자동 모드**는
detect 규칙으로 고르되, 두 route 에 걸치거나 어디에도 안 걸리면 **추측하지 않고
시끄럽게 거부**한다.

```bash
.venv/bin/python -m core.cli routes        # 등록부 보기
```

---

## 2. 모듈 지도

### 컴파일 국면 (문서 종류당 1회, LLM 쓴다)

| 모듈 | T | 역할 |
|---|---|---|
| `glossary.py` | T1 | 용어집 로더. 사용자가 주는 최우선 입력 (section 용어 / fact 용어 이원) |
| `parse_adapter.py` | T2 | docling·markdown → 정규화된 요소 리스트 |
| `term_marker.py` | T3 | 용어 출현 표시 — **mention 인가 section 경계인가** |
| `format_induce.py` | T4 | LLM 형식 유도 → `*.format.json` |
| `holdout_check.py` | T6 | 홀드아웃 검증. 샘플에만 맞는 형식을 걸러낸다 |
| `format_model.py` | | 형식 파일 스키마 |
| `llm.py` | | LLM 래퍼. **런타임에서는 import 조차 되지 않는다** |

### 런타임 국면 (매 문서, LLM 없다)

| 모듈 | T | 역할 |
|---|---|---|
| `router.py` | T0 | 등록부를 보고 판별·배차 |
| `parse_adapter.py` | T2 | 문서 → 요소 리스트 |
| `reading_order.py` | T2b | 양식 페이지에서 뒤섞여 온 요소를 좌표로 다시 세운다 |
| `typography.py` | T2c | 글자의 크기·굵기·간격을 요소에 붙인다 |
| `grid_recover.py` | T2c | 표로 인식되지 못한 격자를 **좌표만** 받아 되찾는다 |
| `structurize.py` | T7 | 형식으로 section 트리 + fact — **규칙 세 개가 전부** |
| `normalize.py` | T8 | 값 정규화 + 타입별 비교기 |
| `fitness_gate.py` | T9 | 적합도 채점 → 통과 or **격리** |
| `review.py` | | 격리된 문서에서 "어디를 못 먹었는가"를 사람에게 |
| `reconcile.py` | T10 | 비교 엔진 — 정답 문서 기준 순회 |
| `cli.py` | | 범용 CLI |

### 구조 해석기 (`core/structure/`)

| | 역할 |
|---|---|
| `pipeline.py` | 본체 S0~S6. **신호를 관리소로만 보므로 신호를 늘려도 안 바뀐다** |
| `registry.py` | 관리소 — 신호를 role 로 등록만 한다 |
| `proposers/` | 후보를 낸다 — `제N조` · `①` · `1.1` · `가.` · `Ⅰ` · `[별지N]` · `custom` |
| `guards/` | 후보를 깎는다 — 조사(`제19조에`는 인용) · construction · 블록 위치 |
| `family/` | 계열 정합 — 연속 단위(run) · 다음 번호 규칙 · 위치 정당성 |
| `global_outer/` | 레벨을 **정한다** — 사다리 · 들여쓰기 · 형식 일관성 |
| `global_inner/` | 후보를 **거른다** — 계층성 · 서수 단조 |
| `dp.py` | 전역 선택 (DP → 트리) |
| `scoring.py` | 수치 상수. **파이프라인 전체가 여기에 매달린다** |
| `lexicon.py` + `lexicon/*.yaml` | 조사·수사·인용 술어를 **용어처럼** 파일로 |
| `resolve.py` | S5b 잔여 해소 — 문서당 **배치 1콜**, 잔여 0이면 0콜 |
| `vlm_heading.py` | S5c 마커 없는 큰 글씨 제목을 VLM 으로 |
| `title.py` | 구역의 **이름** 찾기 |
| `fingerprint.py` | 재현 판정 키 + 저장 분기 |
| `viewer.py` | 해석 결과 → 검수 화면 payload |

---

## 3. 알아 둘 설계 결정 다섯

### 3-1. 구조화 규칙은 세 개다 (`structurize.py`)

1. 요소가 **regex 마커**에 적중하면 그 레벨에 새 section 을 연다
2. 요소가 제목 위치의 **용어형 마커**면 그 레벨에 새 section 을 연다
3. 어느 것도 아니면 **가장 깊은 열린 section 의 내용**이 된다

세 번째가 "모든 요소는 정확히 하나의 최심 section 에 속한다"를 보장한다.
**본문을 판별하지 않고 나머지로 정의한다** — "이게 본문이다"라고 말해 주는 공통 특징은
없지만 별지 경계는 명시적이고 유일하다.

### 3-2. 인식 방법은 마커의 성질이 정한다

번호가 바뀌며 반복되는 것(`제N조`·`①`·`[별지N]`)만 정규표현식. 비반복 제목
("신탁계약 세부내역")은 **용어 매칭**이고 정규표현식을 만들지 않는다. 억지로 씌우면
취약해진다.

### 3-3. mention 을 값으로 읽지 않는다

같은 글자가 구역 경계로도, 문장 속 참조로도 나타난다. `[별지1]` 은 경계이고
`[별지1]신탁계약 세부내역의 위탁자와 …` 는 문장이다. 구별은 레이아웃 신호로 한다.
fact 도 **라벨-값 모양**에서만 뽑는다 — 안 그러면 `[별지1]` 의 1 을 신탁금액 1원으로
읽는다(실측).

### 3-4. 계열 정합(S2)이 사다리(S3)보다 앞에 있다

초판은 레벨을 먼저 정하고 서수로 후보를 걸렀다. 그 순서에서는 조(條)처럼 **제목과 같은
글자로 인용되는** 계열이, 가드가 인용을 정확히 깎아낼수록 등재 비율이 떨어져 탈락했다.
탈락 → 레벨 없음 → 스코프 없음 → 제55조와 제51조가 만나지 못함 → 서수 규칙 미발동.

서수 비교는 **같은 계열 안에서만** 일어나므로 레벨이 필요 없다 — 초판이 전제한 의존이
실제로는 없었다. 순서를 바꾼 실측: 금소법 조 251 → 77건(번호 1~69 연속),
준칙 조 206 → 0건(인용만 있는 문서라 정확한 판정).

### 3-5. 조용한 실패 금지

형식이 안 맞는 문서를 그럴듯한 JSON 으로 내보내는 것이 이 시스템의 최악의 실패다.
적합도는 네 항목의 가중합(마커밀도 .25 / 번호연속성 .25 / fact커버리지 .30 / 잔여 .20),
기본 임계 0.70, doc_type 마다 등록부에서 조정. 미달이면 확정하지 않고 **격리**한다:

    이 문서는 형식 v2 와 53%만 부합합니다 — 다른 양식이거나 양식이 개정되었을 수 있습니다

격리는 막다른 골목이 아니다. `review.py` 가 **어디를 못 먹었는지**(잔여 · 미적중 제목)를
페이지·좌표와 함께 실어 화면이 PDF 위에 겹쳐 보이게 한다.

---

## 4. 실측으로 드러난 것 (같은 실수를 반복하지 않기 위해)

1. **`iterate_items()` 는 기본이 body 레이어뿐이다.** `[별지1]` 이 page_header(furniture)로
   분류돼 있어 별지1 구역을 통째로 놓쳤다. → furniture 를 포함해 받고, 무엇을 무시할지는
   형식(마커)이 정한다.
2. **docling 은 `1. ` 을 `marker` 로 떼어내 `text` 에서 지운다.** `text` 만 쓰면 호 번호가
   사라져 `^\d+\.` 가 영영 안 맞는다. → marker 를 되붙인다.
3. **`'①'.isdigit()` 는 True 다.** 원문자도 Numeric_Type=Digit 이라 `int()` 가 터진다.
   → 번호 연속성 검사는 아스키 숫자만 본다.
4. **한글 수사가 문장을 숫자로 만든다.** "기타특약사**항**에 기재"의 '사'를 4 로 읽었다.
   → 수사는 **수 단위와 함께일 때만** 수로 인정한다.
5. **문장이 라벨로 오인된다.** "신탁보수를 선취한 경우에는 …"이 신탁보수 값으로 잡혔다.
   → 구분자가 있거나 뒤가 짧을 때만 값으로 본다. 값은 짧고 문장은 길다.
6. **깊은 마커가 먼저 오면 트리가 흔들린다.** 문서가 `제1조` 로 시작하면 조가 문서 최상위가
   되어 머리글 한 줄 유무로 section_id 가 달라진다. → 기본 구역을 항상 먼저 연다.
7. **표는 논리 셀로 읽는다.** `table.data.grid` 는 병합 셀을 덮는 칸마다 복제한다
   (colspan=5 면 같은 값이 5번). `table_cells` 는 span 과 열 위치를 가져서 한 행에 필드가
   둘이어도 가른다.
8. **글자 크기 임계로 제목을 못 잡는다.** 실측이 뒤집혀 있다 — 신한은행 신규가입신청서에서
   1.263배가 heading 이고 3.748배는 아니었다. → 크기는 후보를 **고르는** 데만 쓰고
   판정은 VLM 에 맡긴다(S5c).

---

## 5. CLI

```bash
.venv/bin/python -m core.cli routes                    # 등록부 — 지금 무엇을 처리할 수 있나
.venv/bin/python -m core.cli inspect  <문서> --glossary G.yaml     # 파싱 결과만 보기
.venv/bin/python -m core.cli structurize <문서> -o doc.json        # 등록부가 배차, LLM 없음
.venv/bin/python -m core.cli review   <문서>           # 격리 문서 진단
.venv/bin/python -m core.cli reconcile A.json B.json --task T.yaml
.venv/bin/python -m core.cli compile  --glossary G.yaml --samples *.pdf --holdout H.pdf -o F.json
#   --no-llm 을 붙이면 규칙 기반 초안만 (오프라인 대비책)

# 구조 해석기 (형식·용어집 없이)
.venv/bin/python -m core.structure.cli interpret <문서>...
.venv/bin/python -m core.structure.cli signals              # 관리소 등록 현황
```
