"""구조 해석 검수 서비스 — 이것만 띄우는 경량 앱.

    uvicorn api.structure_app:app --host 0.0.0.0 --port 5566

    /                     검수 화면
    /health               상태
    /v1/structure/*       API
    /docs                 Swagger

이 저장소의 앱은 이것 하나다 (레거시 `api.app` — trust-parser·first-agent — 은
2026-08-18 에 삭제). `scripts/serve.sh` 가 호스트에서 uvicorn 으로 띄운다.
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

from lawrag.platform.paths import repository_root

ROOT = repository_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core import logbook                                  # noqa: E402

logbook.setup("structure")
log = logging.getLogger("lawrag.api.structure")
SEALED_SERVING = os.environ.get("LAWRAG_SERVING_SEALED", "").strip().lower() in {
    "1", "true", "yes", "on",
}

from lawrag.api.routers import structure as structure_router     # noqa: E402

# AGENT6 근거 연결 화면. `agents/` 가 이미지에 없으면 임포트가 실패하므로 선택으로 둔다 —
# 구조 해석만 쓰는 이미지에서 이것 때문에 기동이 막히면 안 된다.
try:
    from lawrag.api.routers import agent6 as agent6_router      # noqa: E402
except Exception:                                        # pragma: no cover
    agent6_router = None

# 같은 이유로 선택이다 — rag 는 lawrag/core/rag 를, glossary 는 문서 스토어를 전제한다.
# 이 패키지들이 빠진 슬림 이미지에서 검수 화면까지 같이 죽으면 안 된다.
try:
    from lawrag.api.routers import glossary as glossary_router  # noqa: E402
except Exception:                                        # pragma: no cover
    glossary_router = None
try:
    from lawrag.api.routers import rag as rag_router            # noqa: E402
except Exception:                                        # pragma: no cover
    if SEALED_SERVING:
        raise
    rag_router = None
try:
    from lawrag.api.routers import general_search as general_search_router  # noqa: E402
except Exception:                                        # pragma: no cover
    general_search_router = None
try:
    from lawrag.api.routers import knowledge as knowledge_router  # noqa: E402
except Exception:                                        # pragma: no cover
    knowledge_router = None

# ------------------------------------------------------------------ 예열
# 임베딩 모델 적재와 색인 로드는 프로세스 수명 동안 딱 한 번이다 —
# lawrag/core/embedding.py 의 `_model` 전역과 lawrag/core/rag 의 mtime 캐시가 이미 잡아
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

    def step(name: str, fn, *, integrity_critical: bool = False) -> None:
        t0 = time.perf_counter()
        try:
            note = fn()
        except Exception as exc:
            steps[name] = f"{type(exc).__name__}: {exc}"
            if SEALED_SERVING and integrity_critical:
                raise
            log.warning("예열 '%s' 실패 — 그 비용은 첫 요청이 문다: %s", name, exc)
        else:
            steps[name] = note or round((time.perf_counter() - t0) * 1000)
            log.info("예열 '%s' — %s", name, steps[name])

    def search_index():
        from lawrag.core.rag import index as index_mod
        index_mod.current()

    def vector_index():
        from lawrag.core.rag import vector as vector_mod
        if vector_mod.current() is None:
            return "색인 없음 — 벡터 단은 빠진다"

    def embed_model():
        from lawrag.core import embedding
        if not embedding.available():
            return "모델 없음 — 벡터 단은 빠진다"
        if embedding.encode_one("예열") is None:
            return "인코딩 실패 — 벡터 단은 빠진다"

    step("검색 색인", search_index, integrity_critical=True)
    step("벡터 색인", vector_index, integrity_critical=True)
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

_SEALED_GET = frozenset({
    "/health", "/v1/rag/search", "/v1/rag/links/summary",
    "/v1/rag/section", "/v1/rag/scopes", "/v1/rag/nodes",
})
_SEALED_POST = frozenset({"/v1/rag/ask"})


@app.middleware("http")
async def sealed_query_only(request: Request, call_next):
    """The activated release is a serving plane, never an authoring plane."""

    if SEALED_SERVING:
        allowed = (
            request.method == "GET" and request.url.path in _SEALED_GET
        ) or (
            request.method == "POST" and request.url.path in _SEALED_POST
        )
        if not allowed:
            return JSONResponse(
                {"detail": "active release is sealed and query-only"},
                status_code=403,
            )
    return await call_next(request)

app.include_router(structure_router.router)

# 형식(구조화 틀) 컴파일·바인딩 — 컴파일 국면을 UI 로 끌어올린 것
from lawrag.api.routers import formats as formats_router         # noqa: E402

app.include_router(formats_router.router)
if agent6_router is not None:
    app.include_router(agent6_router.router)
if glossary_router is not None:
    app.include_router(glossary_router.router)
if rag_router is not None:
    app.include_router(rag_router.router)
if general_search_router is not None:
    app.include_router(general_search_router.router)
if knowledge_router is not None:
    app.include_router(knowledge_router.router)

# 로그 조회 — core 만 전제하므로 선택이 아니다.
from lawrag.api.routers import logs as logs_router               # noqa: E402

app.include_router(logs_router.router)

# 법령해석례 열람 — data/expc 색인·위키를 읽기만 한다. 표준 라이브러리만
# 전제하므로 선택이 아니다 (색인이 없으면 라우터가 404 로 말한다).
from lawrag.api.routers import expc as expc_router               # noqa: E402

app.include_router(expc_router.router)

# 계보 원장 — 수집→변환→구조화→연결 낙차 (docs/LINEAGE.md). 읽기 전용 파생
# 뷰라 core 만 전제한다 — 선택이 아니다.
from lawrag.api.routers import lineage as lineage_router         # noqa: E402

app.include_router(lineage_router.router)

# 배치 파이프라인 — 라인업·딸깍·진행 (lawrag/core/batch.py). 모델이 없으면 그
# 단계만 건너뛰므로 core 만 전제한다 — 선택이 아니다.
from lawrag.api.routers import pipeline as pipeline_router       # noqa: E402

app.include_router(pipeline_router.router)

# 격리 실험 코드와 var/eval 산출물 카탈로그 — 실행·변경 없이 읽기만 한다.
from lawrag.api.routers import experiments as experiments_router  # noqa: E402

app.include_router(experiments_router.router)

# 법적 검토 — 사실을 요건에 대는 층 (docs/REVIEW.md). rag 회수 위에 얹히므로
# rag 라우터와 같은 조건에서만 선다(LLM·색인 전제).
if rag_router is not None:
    try:
        from lawrag.api.routers import review as review_router    # noqa: E402

        app.include_router(review_router.router)
    except Exception:                                      # pragma: no cover
        log.exception("검토 라우터 적재 실패 — 나머지 화면은 그대로 뜬다")

# 골든 태깅 — 사람이 화면에서 정답 조문을 직접 짚는다 (docs/RETRIEVAL.md).
# 정규식 자로는 결정 근거와 전제 인용을 못 가른다 — 그 일을 사람이 한다.
try:
    from lawrag.api.routers import golden as golden_router        # noqa: E402

    app.include_router(golden_router.router)
except Exception:                                          # pragma: no cover
    log.exception("골든 태깅 라우터 적재 실패 — 나머지 화면은 그대로 뜬다")

# 망분리 운반 — 스냅샷·아웃박스·재생. 이게 죽어도 검수 화면은 떠야 한다.
# `from api import ops` 가 아니라 점표기다 — 시험이 sys.modules 에서 모듈을
# 지워도 부모 패키지 속성에 낡은 모듈이 남아, from 형태는 그걸 집어온다.
if not SEALED_SERVING:
    try:
        import lawrag.api.ops as ops_mod                          # noqa: E402

        ops_mod.install(app)
    except Exception as exc:                              # pragma: no cover
        log.warning("ops 설치 실패 — 운반 기능 없이 기동: %s", exc)


# 접근 로그 — API 는 INFO, 정적은 DEBUG, 2초↑ WARNING.
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
    if SEALED_SERVING:
        from lawrag.core.rag import switches as switches_mod
        from lawrag.runtime.content_snapshot import (
            current_content_snapshot,
            current_retrieval_runtime_receipt,
        )

        if switches_mod.is_on("sourceset_content_snapshot"):
            snapshot = current_content_snapshot(required=True)
            assert snapshot is not None
            out["content_snapshot"] = snapshot.compact_receipt()
            out["retrieval_runtime"] = current_retrieval_runtime_receipt(
                required=True
            )
    for name in ("fitz", "docling"):
        try:
            __import__(name)
            out["deps"][name] = "ok"
        except Exception as exc:
            out["deps"][name] = f"{type(exc).__name__}: {exc}"
            out["status"] = "degraded"
    try:
        from lawrag.core.structure import registry
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


# 공용 UI — 여덟 화면이 공유하는 토큰·상단바·이동 묶음. 화면들이 절대 경로
# (`/ui/ui.css`)로 부르므로 루트 마운트보다 **먼저** 붙어 있어야 한다.
_SHARED_VIEWER = Path(__file__).resolve().parent / "viewer" / "shared"
if _SHARED_VIEWER.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_SHARED_VIEWER)), name="shared-ui")

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

_KNOWLEDGE_VIEWER = Path(__file__).resolve().parent / "viewer" / "knowledge"
if _KNOWLEDGE_VIEWER.is_dir() and knowledge_router is not None:
    app.mount("/knowledge", StaticFiles(directory=str(_KNOWLEDGE_VIEWER), html=True),
              name="knowledge-viewer")

_RAG_VIEWER = Path(__file__).resolve().parent / "viewer" / "rag"
if _RAG_VIEWER.is_dir() and rag_router is not None:
    app.mount("/rag", StaticFiles(directory=str(_RAG_VIEWER), html=True),
              name="rag-viewer")

# 공리 루프 — 규칙의 생애(잠정→규칙→정착)와 적중 원장 검수 (RULE_LOOP.md §7-4)
_RULES_VIEWER = Path(__file__).resolve().parent / "viewer" / "rules"
if _RULES_VIEWER.is_dir() and rag_router is not None:
    app.mount("/rules", StaticFiles(directory=str(_RULES_VIEWER), html=True),
              name="rules-viewer")

# 승인 진화 루프 — 사람 판정 receipt가 실패×효과 군집과 닫힌 변이축을 거쳐
# replay/holdout/shadow/사람 승인으로 향하는 읽기 전용 감독 화면.
_EVOLUTION_VIEWER = Path(__file__).resolve().parent / "viewer" / "evolution"
if _EVOLUTION_VIEWER.is_dir() and rag_router is not None:
    app.mount("/evolution", StaticFiles(directory=str(_EVOLUTION_VIEWER), html=True),
              name="evolution-viewer")

# 법령해석례 — 위키(맥락)와 사례(원문) 두 판 (docs/expc.md)
_EXPC_VIEWER = Path(__file__).resolve().parent / "viewer" / "expc"
if _EXPC_VIEWER.is_dir():
    app.mount("/expc", StaticFiles(directory=str(_EXPC_VIEWER), html=True),
              name="expc-viewer")

# 골든 태깅 화면 — 정답 조문을 항·호까지 짚는다
_GOLDEN_VIEWER = Path(__file__).resolve().parent / "viewer" / "golden"
if _GOLDEN_VIEWER.is_dir():
    app.mount("/golden", StaticFiles(directory=str(_GOLDEN_VIEWER), html=True),
              name="golden-viewer")

_EXPERIMENTS_VIEWER = Path(__file__).resolve().parent / "viewer" / "experiments"
if _EXPERIMENTS_VIEWER.is_dir():
    app.mount("/experiments", StaticFiles(directory=str(_EXPERIMENTS_VIEWER), html=True),
              name="experiments-viewer")

_LOGS_VIEWER = Path(__file__).resolve().parent / "viewer" / "logs"
if _LOGS_VIEWER.is_dir():
    app.mount("/logs", StaticFiles(directory=str(_LOGS_VIEWER), html=True),
              name="logs-viewer")

# 계보 원장 — 수집→변환→구조화→연결 낙차 감독 (docs/LINEAGE.md)
_LINEAGE_VIEWER = Path(__file__).resolve().parent / "viewer" / "lineage"
if _LINEAGE_VIEWER.is_dir():
    app.mount("/lineage", StaticFiles(directory=str(_LINEAGE_VIEWER), html=True),
              name="lineage-viewer")

# 배치 파이프라인 — 라인업 표 · 딸깍 · 진행 막대
_PIPELINE_VIEWER = Path(__file__).resolve().parent / "viewer" / "pipeline"
if _PIPELINE_VIEWER.is_dir():
    app.mount("/pipeline", StaticFiles(directory=str(_PIPELINE_VIEWER), html=True),
              name="pipeline-viewer")

_VIEWER = Path(__file__).resolve().parent / "viewer" / "structure"
if _VIEWER.is_dir():
    # 검수 화면은 `/structure` 에 — 용어집·참조 연결 화면의 딥링크가
    # `/structure/?doc=…` 로 온다.
    app.mount("/structure", StaticFiles(directory=str(_VIEWER), html=True),
              name="structure-viewer")

# 첫 화면은 **문서·데이터 관리**다 — 업로드·이름·삭제·재해석과 각 화면 현황.
# 예전 딥링크(`/?doc=…`)는 홈이 `/structure/?doc=…` 로 넘겨 준다.
# `/home` 별칭도 준다.
_HOME = Path(__file__).resolve().parent / "viewer" / "home"
if _HOME.is_dir():
    app.mount("/home", StaticFiles(directory=str(_HOME), html=True), name="home-viewer")
_ROOT_VIEWER = _HOME if _HOME.is_dir() else _VIEWER
if _ROOT_VIEWER.is_dir():
    app.mount("/", StaticFiles(directory=str(_ROOT_VIEWER), html=True), name="viewer")
