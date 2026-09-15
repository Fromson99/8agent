# 8-AGENT

법률 문서를 구조화하고 조문·관계·의미 그래프를 함께 회수하는 RAG 시스템이다.
저장소는 영구 `v2-only`이며 lowercase legacy 실행 루트는 사용하지 않는다.

## 실행

```bash
cd /home/jin/8-AGENT
06_TOOLS/check_wsl_dev_environment.sh
06_TOOLS/serve.sh
```

기본 주소는 `http://localhost:5566`이다. launcher는
[WORKSPACE.json](00_SYSTEM/WORKSPACE.json)의 lifecycle activation을 읽고 final receipt에
결속된 정확한 backend generation과 [01_DATA](01_DATA)를 사용한다.

## 구조

| 루트 | 역할 |
|---|---|
| [00_SYSTEM](00_SYSTEM) | workspace schema, activation·retirement·migration receipt |
| [01_DATA](01_DATA) | 원문 구조, 색인, 벡터, 관계, 운영 데이터 |
| [02_BACKEND](02_BACKEND) | receipt-bound Python backend generations |
| [03_FRONTEND](03_FRONTEND) | 웹 UI |
| [04_EXPERIMENTS](04_EXPERIMENTS) | ADR, benchmark, 실험 산출물 |
| [05_TESTS](05_TESTS) | 영구 smoke와 보존된 회귀 테스트 generations |
| [06_TOOLS](06_TOOLS) | 안정 launcher와 receipt-bound 도구 runner |
| [07_DOCS](07_DOCS) | 설계·운영 문서 |
| [08_DEPLOYMENT](08_DEPLOYMENT) | GenOS·온사이트 배포 설정과 runbook |
| [09_ARTIFACTS](09_ARTIFACTS) | 생성 보고서·매체 |
| [90_RUNTIME](90_RUNTIME) | 로그·출력·캐시 |
| [99_ARCHIVE](99_ARCHIVE) | 보존 자료 |

## 도구·테스트

```bash
.venv/bin/python 06_TOOLS/run_tool.py genos_preflight.py source --json
.venv/bin/python 06_TOOLS/run_tool.py code_ship.py list
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q
```

GenOS 상세 문서는 [GENOS_DEPLOY.md](07_DOCS/REFERENCE/OPERATIONS/GENOS_DEPLOY.md), 시스템 구조는
[ARCH_SYSTEM.md](07_DOCS/REFERENCE/ARCHITECTURE/ARCH_SYSTEM.md), 법률 도메인 규칙은
[LEGAL_DOMAIN.md](07_DOCS/REFERENCE/ARCHITECTURE/LEGAL_DOMAIN.md)를 본다.

## 운영 원칙

- runtime 경로는 logical root 또는 active final receipt에서 해석한다.
- 외부 제작 데이터와 내부 데이터는 provenance로 구분하되 같은 catalog에서 조합한다.
- RAG MAIN 변경은 완료·채택된 out-of-sample ADR과 별도 promotion receipt가 있어야 한다.
- 제품 LLM 역할은 `claude-haiku-4-5-20251001`만 사용한다.
- 원문·제한 데이터·비밀값을 외부 공개 저장소로 반출하지 않는다.
