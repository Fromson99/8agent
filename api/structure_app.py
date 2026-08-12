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

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
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

# ------------------------------------------------------------------ 예열
# 임베딩 모델 적재와 색인 로드는 프로세스 수명 동안 딱 한 번이다 —
# core/embedding.py 의 `_model` 전역과 core/rag 의 mtime 캐시가 이미 잡아
# 둔다. 문제는 그 한 번을 **첫 사용자가** 물었다는 것이다: 재기동 직후 첫
# 질의가 11초(실측 모델 적재 10.8초 · 검색 색인 0.4초 · 벡터 색인 36ms).
#
# 기동 때 미리 문다. uvicorn 의 "startup complete" 가 그만큼 늦어지고, 늦어지는
# 동안은 포트가 응답하지 않는다 — 이게 곧 준비 신호다(로드밸런서·healthcheck 가
# 덜 익은 프로세스로 트래픽을 보내지 못한다).
#
# 워커를 늘리면 워커마다 2GB 를 다시 문다 — serve.sh 가 단일 프로세스인 이유다.
# STRUCTURE_PREHEAT=0 이면 건너뛴다(시험·모델 없는 슬림 이미지).
PREHEAT: dict = {"done": False, "steps": {}}


def _preheat() -> None:
    """무거운 것을 순서대로 만져 캐시에 앉힌다. 한 단이 실패해도 다음 단은
    돈다 — 예열 실패는 '그 비용을 첫 요청이 문다'일 뿐 기동 실패가 아니다."""
    steps = PREHEAT["steps"]

    def step(name: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            note = fn()
        except Exception as exc:
            steps[name] = f"{type(exc).__name__}: {exc}"
            log.warning("예열 '%s' 실패 — 그 비용은 첫 요청이 문다: %s", name, exc)
        else:
            steps[name] = note or round((time.perf_counter() - t0) * 1000)
            log.info("예열 '%s' — %s", name, steps[name])

    def search_index():
        from core.rag import index as index_mod
        index_mod.current()

    def vector_index():
        from core.rag import vector as vector_mod
        if vector_mod.current() is None:
            return "색인 없음 — 벡터 단은 빠진다"

    def embed_model():
        from core import embedding
        if not embedding.available():
            return "모델 없음 — 벡터 단은 빠진다"
        if embedding.encode_one("예열") is None:
            return "인코딩 실패 — 벡터 단은 빠진다"

    step("검색 색인", search_index)
    step("벡터 색인", vector_index)
    step("임베딩 모델", embed_model)
    PREHEAT["done"] = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("STRUCTURE_PREHEAT", "1") == "0":
        log.info("예열 생략 — STRUCTURE_PREHEAT=0")
    else:
        t0 = time.perf_counter()
        # to_thread — 동기 적재를 코루틴 안에서 그대로 하면 그 십여 초 동안
        # 이벤트 루프가 통째로 멈춘다. 기동 중이라 할 일이 없더라도, 루프를
        # 붙잡지 않는 편이 시그널 처리(Ctrl-C·SIGTERM)에 안전하다.
        await asyncio.to_thread(_preheat)
        log.info("예열 완료 — %.1f초", time.perf_counter() - t0)
    yield


app = FastAPI(title="구조 해석 검수", version="1.0.0", description=__doc__,
              lifespan=lifespan)

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
    # 예열 결과는 status 를 흔들지 않는다 — 예열이 빗나가도 서비스는 돈다
    # (느려질 뿐이다). 어느 단이 몇 ms 였는지가 콜드 스타트를 되짚는 근거다.
    out: dict = {"status": "ok", "store": str(structure_router.STORE),
                 "preheat": PREHEAT, "deps": {}}
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
