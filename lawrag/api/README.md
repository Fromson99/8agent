# api/ — FastAPI

앱은 하나다: `lawrag/api/structure_app.py` (기본 5566). 구조 해석 검수·형식·용어집·
법령 RAG·법적 검토·해석례·계보·골든·로그 라우터와 정적 화면(`lawrag/api/viewer/`)을 싣는다.
`lawrag/api/ops.py` 는 폐쇄망 운반(스냅샷·아웃박스·재생)이고, 저장소 뿌리의 `service.py`
가 GenOS 코드 서빙 진입점이다.

```bash
scripts/serve.sh                     # .venv/bin/uvicorn api.structure_app:app --port 5566
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

레거시 `lawrag/api/app.py`(5555, trust-parser v1 + first-agent v0)는 2026-08-18 에 지웠다 —
git 이력에 있다.
