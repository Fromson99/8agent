# 문서 구조화 & 정합성 검증 플랫폼

금융 문서(신탁계약서·투자설명서·법령·녹취 전사)를 **구조로 만들고**, 그 구조 위에서
**업무 검증**을 돌리는 시스템이다.

```
문서 ─▶ [ core: 파싱 → 구조화 ] ─▶ doc.json ─▶ [ agents: 서비스 로직 ] ─▶ 리포트
         결정론이 기본                공통 그릇        값 대조 · 행위 점검
```

`core` 는 신탁계약서도 금소법도 모른다. 도메인 지식은 전부 `agents/` 아래 **데이터
파일**에 있다. 그래서 새 업무를 붙이는 일은 새 코드가 아니라 새 폴더 + 새 데이터다.

**➜ 법령 RAG 가 목적이면 [docs/ARCH_SYSTEM.md](docs/ARCH_SYSTEM.md) 부터.** 구조 해석기·agents 구도는
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 무엇을 하고 어떤
기제로 되어 있는지를 한 편으로 설명한다.

**➜ 법령 RAG 를 만진다면 [docs/LEGAL_DOMAIN.md](docs/LEGAL_DOMAIN.md) 필독.** 법령의
위계·계층·연결관계(위임·수임·준용·배제…)와 실측으로 배운 함정을 정리했다 —
이 도메인 문법이 곧 검색 품질이다.

---

## 5분 안에 돌려 보기

### 1) 서버 (호스트 직접 실행 — 컨테이너 안 쓴다)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # ANTHROPIC_API_KEY (개발망) 또는 GENOS_LLM_URL·GENOS_LLM_KEY (GenOS)
scripts/serve.sh                # uvicorn api.structure_app:app  → http://localhost:5566
open http://localhost:5566          # 구조 해석 검수
open http://localhost:5566/rag/     # 법령 질의응답
open http://localhost:5566/agent6/  # 체크리스트 ↔ 법령 근거 연결
```

반영 경로는 `scripts/serve.sh` 재시작 하나다. 폐쇄망(GenOS) 배포·데이터 반입은
[docs/OPS_TRANSPORT.md](docs/OPS_TRANSPORT.md).

### 2) 로컬 CLI

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q

# 지금 무엇을 처리할 수 있는가
.venv/bin/python -m lawrag.core.cli routes

# 형식 없이 구조만 — 처음 보는 문서
.venv/bin/python -m lawrag.core.structure.cli interpret 문서.pdf

# 등록된 문서 종류 → doc.json (LLM 없음, 결정론)
.venv/bin/python -m lawrag.core.cli structurize 문서.pdf -o doc.json
```

### 3) 에이전트

```bash
# agent6 — 녹취 전사 하나로 체크리스트 30항목 점검 (LLM 필요)
.venv/bin/python -m agents.agent6.src.cli run --transcript 전사.json -o out/
```

LLM 은 저장소 루트 `.env` 를 읽는다 — `ANTHROPIC_API_KEY`(개발망) 또는 `GENOS_LLM_URL`·`GENOS_LLM_KEY`(GenOS 서빙, [docs/OPS_TRANSPORT.md](docs/OPS_TRANSPORT.md) §LLM).

---

## 무엇이 어디에 있나

뿌리는 일곱이다 — 진입점 하나, 코드 하나, 도구, 테스트, 문서, 상태, 휘발.

```
8-AGENT/
├── service.py        GenOS 코드 서빙 진입점 — 계약상 저장소 뿌리에 있어야 한다
├── lawrag/           코드 전부 (파이썬 패키지 하나)
│   ├── api/          FastAPI 앱 하나(structure_app, 5566) · viewer/ 정적 화면 · ops(폐쇄망 운반)
│   ├── core/         structure/(구조 해석) rag/(회수·질의) casereview/(검토) terms/(용어) + 파싱·인제스트·llm·embedding
│   ├── sources/      수집 어댑터 — kofia · fss · krx · lawgo · expc · prec · cite
│   ├── pipeline/     수집→변환→인제스트→위키 트리아지 CLI 12개  (`python -m lawrag.pipeline.<이름>`)
│   └── agents/agent6/  녹취 체크리스트 ↔ 법령 근거 (앱이 라우터·화면을 싣는다)
├── scripts/          운영·평가 도구 — serve.sh · data_ship.sh · 골든·벤치·트레이스·도판
├── tests/            core · rag · casereview · law_crawler · agent6 · architecture
├── docs/             문서 (+ tasks/ 작업 지시, archive/ 옛 스펙, examples/ 과제3·5 예시)
├── data/             남는 상태 — structure/ embeddings/ wiki/ review/ bench/ corpus/(수집 원본, 미추적) …
└── var/              휘발 — logs/ out/ (전부 .gitignore)
```

| 위치 | 무엇 | 문서 |
|---|---|---|
| [lawrag/core/](lawrag/core/) | 파싱 → 구조화. 문서 종류를 모르는 범용 층 | [lawrag/core/README.md](lawrag/core/README.md) |
| [lawrag/core/structure/](lawrag/core/structure/) | 구분자만 보고 계층을 복원하는 구조 해석기 | [docs/structure_interpreter_SPEC.md](docs/structure_interpreter_SPEC.md) |
| [lawrag/core/rag/](lawrag/core/rag/) · [lawrag/core/casereview/](lawrag/core/casereview/) | 법령 회수·질의응답 · 법적 검토 | [docs/ARCH_SYSTEM.md](docs/ARCH_SYSTEM.md) · [docs/REVIEW.md](docs/REVIEW.md) |
| [lawrag/pipeline/](lawrag/pipeline/) · [lawrag/sources/](lawrag/sources/) | 수집·변환·인제스트 단계와 소스별 어댑터 | [lawrag/pipeline/__init__.py](lawrag/pipeline/__init__.py) · [docs/adapter_design.md](docs/adapter_design.md) |
| [lawrag/agents/agent6/](lawrag/agents/agent6/) | 녹취 체크리스트 점검 — 판정기가 LLM | [lawrag/agents/agent6/README.md](lawrag/agents/agent6/README.md) |
| [lawrag/api/](lawrag/api/) | FastAPI `structure_app` (5566) + GenOS 운반 `ops` | [lawrag/api/README.md](lawrag/api/README.md) |
| [scripts/](scripts/) | 서버 기동·데이터 반입·골든·벤치 도구 | [docs/OPS_TRANSPORT.md](docs/OPS_TRANSPORT.md) |
| [data/](data/) | 서버 상태 — 무엇이 git 에 있고 무엇을 메일로 나르나 | [data/README.md](data/README.md) |
| [tests/](tests/) | core · rag · casereview · law_crawler · agent6 · architecture | |
| [docs/archive/](docs/archive/) | v0·v1·agent1 시절 문서 (코드는 git 이력에) | |

**문서** — 두 시대가 겹쳐 있다. 법령 RAG 를 만지면 위 묶음, 구조 해석기·agent6 을 만지면 아래 묶음.

| 법령 RAG (현행) | |
|---|---|
| [docs/ARCH_SYSTEM.md](docs/ARCH_SYSTEM.md) | **여기서 시작.** 수집·질의 두 단계와 질의응답 경로 |
| [docs/RAG_DOMAIN.md](docs/RAG_DOMAIN.md) | 법 도메인 사실 열둘이 시스템 어디에 박혔나 |
| [docs/LEGAL_DOMAIN.md](docs/LEGAL_DOMAIN.md) | 법령의 위계·계층·간선, 실측으로 배운 함정 |
| [docs/TAGS.md](docs/TAGS.md) | 조문 성격 태그층 — 외부 설계 검토와 구현 기록 |
| [docs/expc.md](docs/expc.md) | 해석례 수집·색인·llm-wiki (해석 지식은 원문과 다른 층) |
| [docs/REVIEW.md](docs/REVIEW.md) · [docs/RULE_LOOP.md](docs/RULE_LOOP.md) | 사실→쟁점→규범→포섭→결론 검토 뼈대 · 자가 규칙 루프 |
| [docs/GOLDEN.md](docs/GOLDEN.md) · [docs/RETRIEVAL.md](docs/RETRIEVAL.md) | 골든 셋 채점 규칙과 회차 실측 · 회수를 재는 자 |
| [docs/LINEAGE.md](docs/LINEAGE.md) · [docs/OPS_TRANSPORT.md](docs/OPS_TRANSPORT.md) | 문서 계보 원장 · 폐쇄망 운반 |
| [docs/NOTION_ARCHITECTURE.md](docs/NOTION_ARCHITECTURE.md) | 2026-08-17 실측 종합 스냅샷 (노션 임포트용) |
| [docs/site_survey.md](docs/site_survey.md) · [docs/access_profile.md](docs/access_profile.md) · [docs/adapter_design.md](docs/adapter_design.md) | 규정 수집기 — 사이트 조사·접속 프로파일·어댑터 설계 |

| 구조 해석기 · agents (초기 구도) | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | core/agents 분리 구도(초기)의 역할과 기제 |
| [docs/SPEC.md](docs/SPEC.md) | 플랫폼 규격의 정본. lawrag/core/structure 가 §번호로 이걸 가리킨다 |
| [docs/AGENT6_SPEC.md](docs/AGENT6_SPEC.md) | agent6 지시사항서 |
| [docs/structure_interpreter_SPEC.md](docs/structure_interpreter_SPEC.md) | 구조 해석기 규격 |
| [docs/archive/](docs/archive/) | (보존) agent1 스펙·QA 질문지·v1 설계 — 코드는 2026-08-18 삭제, git 이력에 있다 |

---

## 설계의 뼈대 세 줄

자세한 것은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1.

**1. stochastic 을 컴파일 타임에 가둔다.** LLM 은 형식을 만들 때 한 번만 쓰고, 매 문서를
처리하는 런타임에서는 `lawrag/core/llm.py` 가 import 조차 되지 않는다. 같은 문서를 두 번
구조화하면 JSON 이 동일하다.

**2. 등록부가 처리 규칙을 정한다.** `lawrag/core/router.py` 는 형식·용어집 경로를 인자로 받지
않는다. 호출자는 `doc_type` 만 말할 수 있고 `lawrag/core/registry.yaml` 이 나머지를 정한다 —
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

- **컴파일의 LLM 경로를 실행하지 않았다.** 현재 형식은 규칙 기반 초안(`--no-llm`)이고
  신뢰도 `low` 로 표기돼 있다.
- **스탬프된 값이 인쇄 문구 뒤에 붙는다** · **체크박스 √ 검출 미구현** ·
  **홀드아웃 샘플 부족** · **골든 쌍의 값은 합성**.

---

## 주의 — 이 브랜치는 내부 전용

`dev` 브랜치는 내부 저장소(`infoczAI/agent8`) 전용이며 **원본 은행 문서**를 포함한다
(`lawrag/agents/agent6/corpus/raw/`).
공개 저장소로 push 하거나 merge 하지 말 것. 자세한 것은 [.gitignore](.gitignore) 머리말.
