# 문서 구조화 & 정합성 검증 플랫폼

금융 문서(신탁계약서·투자설명서·법령·녹취 전사)를 **구조로 만들고**, 그 구조 위에서
**업무 검증**을 돌리는 시스템이다.

```
문서 ─▶ [ core: 파싱 → 구조화 ] ─▶ doc.json ─▶ [ agents: 서비스 로직 ] ─▶ 리포트
         결정론이 기본                공통 그릇        값 대조 · 행위 점검
```

`core` 는 신탁계약서도 금소법도 모른다. 도메인 지식은 전부 `agents/` 아래 **데이터
파일**에 있다. 그래서 새 업무를 붙이는 일은 새 코드가 아니라 새 폴더 + 새 데이터다.

**➜ 처음이라면 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 부터.** 무엇을 하고 어떤
기제로 되어 있는지를 한 편으로 설명한다.

**➜ 법령 RAG 를 만진다면 [docs/LEGAL_DOMAIN.md](docs/LEGAL_DOMAIN.md) 필독.** 법령의
위계·계층·연결관계(위임·수임·준용·배제…)와 실측으로 배운 함정을 정리했다 —
이 도메인 문법이 곧 검색 품질이다.

---

## 5분 안에 돌려 보기

### 1) 구조 해석 검수 화면 (컨테이너, 준비물 없음)

용어집도 형식도 없이 PDF 를 넣으면 계층 구조를 복원해 원본 위에 겹쳐 보여 준다.

```bash
docker compose up -d --build        # 첫 빌드는 docling 모델을 굽느라 몇 분 걸린다
open http://localhost:5566          # 구조 해석 검수
open http://localhost:5566/agent6/  # 체크리스트 ↔ 법령 근거 연결
```

화면 사용법과 환경변수는 [deploy/structure/README.md](deploy/structure/README.md).

### 2) 로컬 CLI

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q

# 지금 무엇을 처리할 수 있는가
.venv/bin/python -m core.cli routes

# 형식 없이 구조만 — 처음 보는 문서
.venv/bin/python -m core.structure.cli interpret 문서.pdf

# 등록된 문서 종류 → doc.json (LLM 없음, 결정론)
.venv/bin/python -m core.cli structurize 문서.pdf -o doc.json
```

### 3) 에이전트

```bash
# agent1 — 계약서 ↔ 투자설명서 값 대사 (파일 두 개 in, 리포트 out)
.venv/bin/python agents/agent1/src/cli.py run \
    --contract   agents/agent1/data/golden/contract_filled.pdf \
    --prospectus agents/agent1/data/B1055656A.pdf \
    -o agents/agent1/output/agent1.report.json

# agent6 — 녹취 전사 하나로 체크리스트 30항목 점검 (ANTHROPIC_API_KEY 필요)
.venv/bin/python -m agents.agent6.src.cli run --transcript 전사.json -o out/
```

LLM 키는 저장소 루트 `.env` 의 `ANTHROPIC_API_KEY` 를 읽는다(컨테이너는 환경변수로 주입).

---

## 무엇이 어디에 있나

| 폴더 | 역할 | 문서 |
|---|---|---|
| [core/](core/) | 파싱 → 구조화. 문서 종류를 모르는 범용 층 | [core/README.md](core/README.md) |
| [core/structure/](core/structure/) | 구분자만 보고 계층을 복원하는 구조 해석기 | [docs/structure_interpreter_SPEC.md](docs/structure_interpreter_SPEC.md) |
| [agents/agent1/](agents/agent1/) | 신탁계약서 ↔ 투자설명서 **값** 대조 | [agents/agent1/README.md](agents/agent1/README.md) |
| [agents/agent6/](agents/agent6/) | 녹취 체크리스트 점검 — 판정기가 LLM | [agents/agent6/README.md](agents/agent6/README.md) |
| [api/](api/) | FastAPI. `structure_app`(기본 5566) · `app`(레거시 5555) | [api/README.md](api/README.md) |
| [deploy/](deploy/) | 컨테이너 이미지 두 종 | [deploy/structure/README.md](deploy/structure/README.md) |
| [docs/](docs/) | 아키텍처 + SPEC 4종 + QA 질문지 | ↓ |
| [tests/](tests/) | core · agent1 · agent6 · architecture | |
| [archive/](archive/) · `first-agent/` | v1·v0 보존. 기본 이미지에는 안 들어간다 | |

**문서**

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **여기서 시작.** 역할과 기제를 한 편으로 |
| [docs/SPEC.md](docs/SPEC.md) | 플랫폼 규격의 정본. 다른 문서가 §번호로 이걸 가리킨다 |
| [docs/AGENT1_SPEC.md](docs/AGENT1_SPEC.md) · [docs/AGENT6_SPEC.md](docs/AGENT6_SPEC.md) | 에이전트별 지시사항서 |
| [docs/structure_interpreter_SPEC.md](docs/structure_interpreter_SPEC.md) | 구조 해석기 규격 |
| [docs/QA_SESSION.md](docs/QA_SESSION.md) | 요구사항과 구현의 간극 — 확인이 필요한 것 |

---

## 설계의 뼈대 세 줄

자세한 것은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1.

**1. stochastic 을 컴파일 타임에 가둔다.** LLM 은 형식을 만들 때 한 번만 쓰고, 매 문서를
처리하는 런타임에서는 `core/llm.py` 가 import 조차 되지 않는다. 같은 문서를 두 번
구조화하면 JSON 이 동일하다.

**2. 등록부가 처리 규칙을 정한다.** `core/router.py` 는 형식·용어집 경로를 인자로 받지
않는다. 호출자는 `doc_type` 만 말할 수 있고 `core/registry.yaml` 이 나머지를 정한다 —
같은 doc_type 은 누가 부르든 같은 규칙으로 처리된다. 이 강제는
[tests/architecture/](tests/architecture/) 가 AST 로 지킨다.

**3. 조용한 실패를 금지한다.** 형식이 안 맞는 문서를 그럴듯한 JSON 으로 내보내는 것이
가장 위험한 실패다. 적합도 미달이면 확정하지 않고 **격리**하고, 애매한 판정은
auto-pass/fail 하지 않고 `NEEDS_REVIEW` 로 뺀다.

---

## 현재 상태

| | 결과 |
|---|---|
| 테스트 | 384개 중 **378 passed** (아래 참조) |
| 구조화 — 빈 템플릿 `ss2207` | section 97, 제1~32조 전부, 별지1·별지2, 잔여 0, 게이트 81% |
| 구조화 — 체결본 | section 97, fact 17, 잔여 0, 게이트 **98%** |
| 구조 해석 — 금소법 | 조 후보 251 → 77건 (번호 1~69 연속) |
| 구조 해석 — 표준투자권유준칙 | 조 후보 206 → 0건 (인용만 있는 문서 — 정확한 판정) |
| 비교 (골든 쌍) | rule 12개 → 전부 한 행, 일치 4 / 불일치 5 / 미매핑 1 / 보류 2 |
| 런타임 결정론 | 같은 문서 두 번 구조화 → JSON 동일 |

포맷 차이는 MATCH 로 흡수된다 — `금 1억원정 (₩100,000,000)` ≡ `100,000,000원`,
`24.6.3 ~ 27.6.2` ≡ `2024년 6월 3일부터 2027년 6월 2일까지`. 진짜 불일치(지급주기
`매월`↔`분기`, 중도해지수수료 요율)는 정확히 잡힌다.

**남은 것** — 전체 목록은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §6.

- **투자설명서 형식 부합률 53%** → 격리. `tests/agent1/test_golden.py` 5건이 이것 때문에
  실패한다. 형식이 실물 66p 투자설명서를 아직 못 따라간다.
- **컴파일의 LLM 경로를 실행하지 않았다.** 현재 형식은 규칙 기반 초안(`--no-llm`)이고
  신뢰도 `low` 로 표기돼 있다.
- **스탬프된 값이 인쇄 문구 뒤에 붙는다** · **체크박스 √ 검출 미구현** ·
  **홀드아웃 샘플 부족** · **골든 쌍의 값은 합성**.

---

## 주의 — 이 브랜치는 내부 전용

`dev` 브랜치는 내부 저장소(`infoczAI/agent8`) 전용이며 **원본 은행 문서**를 포함한다
(`first-agent/dataset/`, `agents/*/data/`, `agents/agent6/corpus/raw/`).
공개 저장소로 push 하거나 merge 하지 말 것. 자세한 것은 [.gitignore](.gitignore) 머리말.
