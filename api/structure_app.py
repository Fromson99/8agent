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

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routers import structure as structure_router     # noqa: E402

# AGENT6 근거 연결 화면. `agents/` 가 이미지에 없으면 임포트가 실패하므로 선택으로 둔다 —
# 구조 해석만 쓰는 이미지에서 이것 때문에 기동이 막히면 안 된다.
try:
    from api.routers import agent6 as agent6_router      # noqa: E402
except Exception:                                        # pragma: no cover
    agent6_router = None

app = FastAPI(title="구조 해석 검수", version="1.0.0", description=__doc__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(structure_router.router)
if agent6_router is not None:
    app.include_router(agent6_router.router)


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
    return JSONResponse(
        {"detail": {"message": f"{type(exc).__name__}: {exc}", "path": request.url.path}},
        status_code=500)


_AGENT6_VIEWER = Path(__file__).resolve().parent / "viewer" / "agent6"
if _AGENT6_VIEWER.is_dir() and agent6_router is not None:
    # 루트(`/`) 마운트보다 **먼저** 붙여야 한다 — 루트가 먼저 붙으면 모든 경로를
    # 먹어서 `/agent6/` 가 구조 뷰어의 404 로 떨어진다.
    app.mount("/agent6", StaticFiles(directory=str(_AGENT6_VIEWER), html=True),
              name="agent6-viewer")

_VIEWER = Path(__file__).resolve().parent / "viewer" / "structure"
if _VIEWER.is_dir():
    # 루트에 붙인다 — 컨테이너를 열면 바로 화면이 뜬다.
    app.mount("/", StaticFiles(directory=str(_VIEWER), html=True), name="viewer")
