"""구조 해석 검수 서비스 — 이것만 띄우는 경량 앱.

    uvicorn api.structure_app:app --host 0.0.0.0 --port 5566

    /                     검수 화면
    /health               상태
    /v1/structure/*       API
    /docs                 Swagger

`api.app` 은 두 레거시 엔진(trust-parser·first-agent)을 함께 싣는다. 그쪽은 이 저장소에서
`archive/` 로 빠졌고, 검수 화면은 `core.structure` 만 있으면 돌아간다. 그래서 컨테이너는
이 앱을 띄운다 — 이미지가 작아지고, 레거시 경로가 없어도 기동한다.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import logbook                                  # noqa: E402

logbook.setup("structure")
log = logging.getLogger("api.structure")

from api.routers import structure as structure_router     # noqa: E402

# AGENT6 근거 연결 화면. `agents/` 가 이미지에 없으면 임포트가 실패하므로 선택으로 둔다 —
# 구조 해석만 쓰는 이미지에서 이것 때문에 기동이 막히면 안 된다.
try:
    from api.routers import agent6 as agent6_router      # noqa: E402
except Exception:                                        # pragma: no cover
    agent6_router = None

# 같은 이유로 선택이다 — rag 는 core/rag 를, glossary 는 문서 스토어를 전제한다.
# 이 패키지들이 빠진 슬림 이미지에서 검수 화면까지 같이 죽으면 안 된다.
try:
    from api.routers import glossary as glossary_router  # noqa: E402
except Exception:                                        # pragma: no cover
    glossary_router = None
try:
    from api.routers import rag as rag_router            # noqa: E402
except Exception:                                        # pragma: no cover
    rag_router = None

app = FastAPI(title="구조 해석 검수", version="1.0.0", description=__doc__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(structure_router.router)

# 형식(구조화 틀) 컴파일·바인딩 — 컴파일 국면을 UI 로 끌어올린 것
from api.routers import formats as formats_router         # noqa: E402

app.include_router(formats_router.router)
if agent6_router is not None:
    app.include_router(agent6_router.router)
if glossary_router is not None:
    app.include_router(glossary_router.router)
if rag_router is not None:
    app.include_router(rag_router.router)

# 로그 조회 — core 만 전제하므로 선택이 아니다.
from api.routers import logs as logs_router               # noqa: E402

app.include_router(logs_router.router)


# 접근 로그 — api.app 과 같은 규약: API 는 INFO, 정적은 DEBUG, 2초↑ WARNING.
_API_PREFIXES = ("/v1/", "/health")


@app.middleware("http")
async def access_log(request: Request, call_next):
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("%s %s → 예외 (%.0fms)", request.method,
                      request.url.path, (time.perf_counter() - t0) * 1000)
        raise
    dur = (time.perf_counter() - t0) * 1000
    path = request.url.path
    level = (logging.WARNING if dur > 2000
             else logging.INFO if path.startswith(_API_PREFIXES)
             else logging.DEBUG)
    log.log(level, "%s %s → %d (%.0fms)", request.method,
            path + (f"?{request.url.query}" if request.url.query else ""),
            response.status_code, dur)
    return response


@app.get("/health", tags=["health"])
def health():
    """의존성이 실제로 임포트되는지까지 본다 — 기동만 되고 첫 요청에서 죽는 것을 막는다."""
    out: dict = {"status": "ok", "store": str(structure_router.STORE), "deps": {}}
    for name in ("fitz", "docling"):
        try:
            __import__(name)
            out["deps"][name] = "ok"
        except Exception as exc:
            out["deps"][name] = f"{type(exc).__name__}: {exc}"
            out["status"] = "degraded"
    try:
        from core.structure import registry
        reg = registry.default()
        out["signals"] = {r: len(reg.by_role(r)) for r in registry.ROLES}
    except Exception as exc:
        out["status"] = "degraded"
        out["signals"] = f"{type(exc).__name__}: {exc}"
    return out


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("처리되지 않은 예외 — %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": {"message": f"{type(exc).__name__}: {exc}", "path": request.url.path}},
        status_code=500)


_GLOSSARY_VIEWER = Path(__file__).resolve().parent / "viewer" / "glossary"
if _GLOSSARY_VIEWER.is_dir():
    app.mount("/glossary", StaticFiles(directory=str(_GLOSSARY_VIEWER), html=True),
              name="glossary-viewer")

_AGENT6_VIEWER = Path(__file__).resolve().parent / "viewer" / "agent6"
if _AGENT6_VIEWER.is_dir() and agent6_router is not None:
    # 루트(`/`) 마운트보다 **먼저** 붙여야 한다 — 루트가 먼저 붙으면 모든 경로를
    # 먹어서 `/agent6/` 가 구조 뷰어의 404 로 떨어진다.
    app.mount("/agent6", StaticFiles(directory=str(_AGENT6_VIEWER), html=True),
              name="agent6-viewer")

_BINDINGS_VIEWER = Path(__file__).resolve().parent / "viewer" / "bindings"
if _BINDINGS_VIEWER.is_dir():
    # 구조화 연결 — 폴더·문서를 구조화 틀에 손으로 잇는 캔버스
    app.mount("/bindings", StaticFiles(directory=str(_BINDINGS_VIEWER), html=True),
              name="bindings-viewer")

_LINKS_VIEWER = Path(__file__).resolve().parent / "viewer" / "links"
if _LINKS_VIEWER.is_dir():
    app.mount("/links", StaticFiles(directory=str(_LINKS_VIEWER), html=True),
              name="links-viewer")

_RAG_VIEWER = Path(__file__).resolve().parent / "viewer" / "rag"
if _RAG_VIEWER.is_dir() and rag_router is not None:
    app.mount("/rag", StaticFiles(directory=str(_RAG_VIEWER), html=True),
              name="rag-viewer")

_LOGS_VIEWER = Path(__file__).resolve().parent / "viewer" / "logs"
if _LOGS_VIEWER.is_dir():
    app.mount("/logs", StaticFiles(directory=str(_LOGS_VIEWER), html=True),
              name="logs-viewer")

_VIEWER = Path(__file__).resolve().parent / "viewer" / "structure"
if _VIEWER.is_dir():
    # 검수 화면은 `/structure` 에 — 용어집·참조 연결 화면의 딥링크가
    # `/structure/?doc=…` 로 온다 (api.app 도 같은 자리에 붙는다).
    app.mount("/structure", StaticFiles(directory=str(_VIEWER), html=True),
              name="structure-viewer")

# 첫 화면은 **문서·데이터 관리**다 — 업로드·이름·삭제·재해석과 각 화면 현황.
# 예전 딥링크(`/?doc=…`)는 홈이 `/structure/?doc=…` 로 넘겨 준다.
# `/home` 별칭도 준다 — api.app 은 루트가 JSON 소개라 그쪽에선 이 주소뿐이다.
_HOME = Path(__file__).resolve().parent / "viewer" / "home"
if _HOME.is_dir():
    app.mount("/home", StaticFiles(directory=str(_HOME), html=True), name="home-viewer")
_ROOT_VIEWER = _HOME if _HOME.is_dir() else _VIEWER
if _ROOT_VIEWER.is_dir():
    app.mount("/", StaticFiles(directory=str(_ROOT_VIEWER), html=True), name="viewer")
