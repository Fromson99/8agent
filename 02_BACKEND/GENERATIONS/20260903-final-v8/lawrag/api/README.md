# api/ — FastAPI

앱은 하나다: `lawrag/api/structure_app.py` (기본 5566). 구조 해석 검수·형식·용어집·
법령 RAG·법적 검토·해석례·계보·골든·로그 라우터와 정적 화면(`lawrag/api/viewer/`)을 싣는다.
`lawrag/api/ops.py` 는 폐쇄망 운반(스냅샷·아웃박스·재생)이고, 저장소 뿌리의 `service.py`
가 GenOS 코드 서빙 진입점이다.

```bash
scripts/serve.sh                     # .venv/bin/uvicorn lawrag.api.structure_app:app --port 5566
curl localhost:5566/health
open  http://localhost:5566/docs     # Swagger
```

**반드시 저장소 루트에서 실행한다** — 라우터가 `core/`·`lawrag/agents/agent6` 를 상대 경로로 본다.

| 경로 | 무엇 |
|---|---|
| `/v1/structure/*` | 문서 올리기·구조 해석·재해석·페이지 그림 |
| `/v1/formats/*` · `/v1/glossary/*` | 형식 컴파일·바인딩·용어 검수 |
| `/v1/rag/*` | 검색·질의응답·규칙·판정 지문 |
| `/v1/review` | 법적 검토 (요건별 충족표) |
| `/v1/expc/*` · `/v1/golden/*` · `/v1/lineage/*` · `/v1/logs/*` | 해석례·골든·계보·로그 |
| `/v1/agent6/*` | 체크리스트 ↔ 법령 근거 |
| `/v1/ops/*` | 스냅샷·아웃박스 (docs/OPS_TRANSPORT.md) |

환경변수는 `scripts/serve.sh` 머리와 [docs/OPS_TRANSPORT.md](../../docs/OPS_TRANSPORT.md) §env.

`POST /v1/rag/ask`의 기본 회수기는 `LegalClosure`다. `mode`를 생략하거나
`legalclosure`로 보내면 정확 구조→proof shortcut 또는 Assertion 트리→균등 BM25→
직접 관계 폐쇄→규범기능 참조 검증을 최대 20조문으로 합친다. 각 context에는 원문
조건·예외·기간·수량 span과 법원성·시점 검증 메타가 붙는다. 이전 기본은 삭제하지 않고
`legacy-vector`·`legacy-auto`로
보관한다. 운영 스위치 `legalclosure_main`을 끄면 기본 요청이 legacy-vector로
롤백되며 응답 `retriever.status`가 이를 표시한다.

승인 shortcut 저장소는 `RAG_ASSERTION_SHORTCUT_STORE`로 지정한다. 파일이 없거나
canonical fingerprint가 다르거나 경로가 중의면 자동으로 기존 Assertion 트리를 실행한다.
저장소는 `schema_version: 1`, `approval.approved_by`, `approval.approved_at`과 모든 target·
required Assertion을 덮는 G1/G2/G3 source proof가 있어야 한다. 실패 상태는 응답의
`legalclosure.assertion.shortcut.store`에 남는다.

```json
{"question": "자기주식 소각의무가 있나요?", "mode": "legalclosure"}
```

레거시 `lawrag/api/app.py`(5555, trust-parser v1 + first-agent v0)는 2026-08-18 에 지웠다 —
git 이력에 있다.
