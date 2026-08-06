"""신탁계약 정합성 검증 API — 두 엔진을 한 서비스로.

    uvicorn api.app:app --host 0.0.0.0 --port 5555

    /health               의존성·엔진 상태 (GenOS 헬스체크)
    /chat/stream          GenOS 채팅 연동 (SSE)
    /docs                 Swagger UI (그대로 눌러 보면 된다)
    /v1/parser/*          trust-parser — 온톨로지 기반 결정론 엔진
    /v1/agent/*           first-agent  — LLM 해석 파이프라인
    /v1/jobs/*            무거운 작업 폴링
    /v1/structure/*       구조 해석기 — 트리 + 좌표(검수 화면이 읽는다)
    /structure/           구조 해석 검수 화면 (PDF 위 오버레이)
    /viewer/              기존 정적 뷰어 (SERVE_VIEWER=0 으로 끌 수 있다)

설계 원칙 하나만 옮겨 놓는다: **최종 판정은 코드 결정론**이다.
LLM 은 해석에만 관여하고, 애매하면 auto-pass/fail 하지 않고 NEEDS_REVIEW 로 뺀다.
이 API 도 그 판정을 다시 쓰거나 요약하지 않고 있는 그대로 낸다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import engines, settings
from .documents import STORE as DOCS
from .jobs import STORE
from .routers import agent as agent_router
from .routers import agent6 as agent6_router
from .routers import chat as chat_router
from .routers import jobs as jobs_router
from .routers import parser as parser_router
from .routers import structure as structure_router

app = FastAPI(
    title="신탁계약 정합성 검증 API",
    version="1.0.0",
    description=__doc__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /chat/stream 은 API_TOKEN 뒤에 두지 않는다 — GenOS 워크플로우가 내부망에서
# `x-request-from: internal` 헤더로 부르는 경로이고, 플랫폼 규약에 Bearer 가 없다.
# 공개망에 노출한다면 네트워크 계층(사설망·방화벽)에서 막아야 한다.
app.include_router(chat_router.router)
app.include_router(parser_router.router)
app.include_router(agent_router.router)
app.include_router(jobs_router.router)
app.include_router(structure_router.router)
app.include_router(agent6_router.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """예상 못 한 예외도 JSON 으로. 호출자가 HTML 오류 페이지를 파싱할 일은 없어야 한다."""
    return JSONResponse(
        {"detail": {"message": f"{type(exc).__name__}: {exc}", "path": request.url.path}},
        status_code=500)


@app.get("/", tags=["meta"], summary="서비스 소개")
def index():
    return {
        "service": "trust-contract-reconciliation",
        "docs": "/docs",
        # 사람이 여는 화면. 여기 없으면 URL 을 아는 사람만 들어갈 수 있다.
        "ui": {
            "구조 해석 검수": "/structure/   — PDF → 구조 트리·표·그림 (core)",
            "AGENT6 근거 연결": "/agent6/     — 체크리스트 ↔ 법령 조항 잇기/끊기",
        },
        "genos": {"chat": "POST /chat/stream", "health": "GET /health",
                  "protocol": "SSE — token / reasoning_token / agentFlowExecutedData / "
                              "error / result"},
        "engines": {
            "trust-parser": {
                "설명": "온톨로지 기반 결정론 엔진. 임베딩·정규식 값 파싱 없음.",
                "endpoints": ["POST /v1/parser/parse", "POST /v1/parser/reconcile",
                              "POST /v1/parser/reconcile/json", "POST /v1/parser/query",
                              "GET /v1/parser/ontology", "GET /v1/parser/fields"],
            },
            "first-agent": {
                "설명": "문서 해석을 LLM 이 하는 대사 파이프라인. 스냅샷으로 재현성 확보.",
                "endpoints": ["GET /v1/agent/status", "GET /v1/agent/tags",
                              "POST /v1/agent/reconcile", "POST /v1/agent/bundle"],
            },
        },
        "jobs": ["GET /v1/jobs", "GET /v1/jobs/{id}", "GET /v1/jobs/{id}/wait",
                 "DELETE /v1/jobs/{id}"],
    }


@app.get("/health", tags=["meta"], summary="의존성·엔진 상태")
def health():
    out: dict = {"status": "ok", "jobs": STORE.stats(),
                 "documents": len(DOCS.list()),
                 "docling": engines.has_docling(),
                 "anthropic_api_key": engines.has_anthropic_key()}
    try:
        onto = engines.ontology()
        out["parser"] = {"ok": True, "doc_type": onto.doc_type,
                         "version": onto.version, "fields": len(onto.fields),
                         "shapes": len(onto.shapes), "axioms": len(onto.axioms_from_text)}
    except Exception as exc:
        out["status"] = "degraded"
        out["parser"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        schema = engines.agent("main").load_json("tag_schema.json")
        out["agent"] = {"ok": True, "tags": len(schema.get("sections", []))}
    except Exception as exc:
        out["status"] = "degraded"
        out["agent"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not out["docling"]:
        out["note"] = ("docling 미설치 — PDF 파싱 엔드포인트만 503 입니다. "
                       "대사·질의는 정상 동작합니다.")
    return out


# ---------------------------------------------------------------------------
# 기존 정적 뷰어 — cli.py serve 가 하던 일을 그대로 얹는다
# ---------------------------------------------------------------------------

# 구조 해석 검수 화면 — PDF 를 서버가 PNG 로 렌더하므로 CDN·번들 의존이 없다.
_AGENT6_VIEWER = Path(__file__).resolve().parent / "viewer" / "agent6"
if _AGENT6_VIEWER.exists():
    app.mount("/agent6", StaticFiles(directory=str(_AGENT6_VIEWER), html=True),
              name="agent6-viewer")

_STRUCTURE_VIEWER = Path(__file__).resolve().parent / "viewer" / "structure"
if _STRUCTURE_VIEWER.is_dir():
    app.mount("/structure", StaticFiles(directory=str(_STRUCTURE_VIEWER), html=True),
              name="structure-viewer")

_VIEWER_DIR = settings.PARSER_ROOT / "viewer"
_bundle_cache: dict = {}

if settings.SERVE_VIEWER and _VIEWER_DIR.is_dir():
    app.mount("/viewer", StaticFiles(directory=str(_VIEWER_DIR), html=True), name="viewer")

    @app.get("/out/viewer.json", include_in_schema=False)
    def viewer_bundle(refresh: bool = Query(False)):
        """뷰어가 읽는 번들. 대사 리포트는 저장본을 읽지 않고 **다시 돌린다** —
        결정론이라 재현되고, 새 필드가 옛 파일에 없어도 화면이 최신을 보여준다."""
        if refresh or "payload" not in _bundle_cache:
            cli = engines.parser("cli")
            _bundle_cache["payload"] = cli._viewer_payload(
                engines.ontology(), settings.PARSER_ROOT)
        return _bundle_cache["payload"]

    @app.get("/api/query", include_in_schema=False)      # noqa: F811 — 뷰어 호환 경로
    def viewer_query(q: str = "", doc: int = 0):
        """뷰어 호환 경로. /v1/parser/query 와 같은 함수를 부른다."""
        payload = viewer_bundle()
        docs = payload.get("docs") or []
        if not docs:
            return {"error": "번들에 문서가 없습니다 — out/*.chunks.json 을 먼저 만드세요"}
        cli = engines.parser("cli")
        try:
            return cli._run_query(docs[max(0, min(doc, len(docs) - 1))], q,
                                  engines.ontology())
        except Exception as exc:                     # 뷰어가 죽지 않게 한다
            return {"error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":                    # python -m api.app 로도 뜬다
    import os

    import uvicorn

    uvicorn.run("api.app:app", host="0.0.0.0", port=int(os.getenv("PORT", "5555")))
