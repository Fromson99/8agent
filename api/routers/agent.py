"""first-agent — LLM 이 문서를 해석하는 대사 파이프라인.

    GET  /v1/agent/status     LLM 키·스냅샷 상태 (호출 전에 확인)
    GET  /v1/agent/tags       대사 대상 태그 목록 (프론트 선택값 = tags 파라미터)
    POST /v1/agent/reconcile  계약서 + 핵심상품설명서 → 리포트(JSON + 마크다운)
    POST /v1/agent/bundle     위 + 중간 산출물 전부 (블록·태깅·페어링·스냅샷 통계)

## 두 가지 실행 모드

    llm_backend=auto      키가 있으면 실제 호출 + 스냅샷 기록, 없으면 스냅샷 재생
    llm_backend=snapshot  항상 기록본 재생 — 키 없이 같은 리포트가 재현된다

금융 대사에서 "어제는 일치, 오늘은 불일치"는 그 자체가 사고다. 스냅샷은 그걸 막는 장치라
서버에서도 그대로 쓴다. 다만 스냅샷 파일은 **공유 상태**라 이 라우터의 작업은
워커 1개로 직렬 실행된다(settings.AGENT_WORKERS).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import engines, http, settings, uploads

router = APIRouter(prefix="/v1/agent", tags=["first-agent"],
                   dependencies=[Depends(http.require_token)])

AGENT_SUFFIXES = {".pdf", ".docx", ".pptx", ".html", ".htm", ".txt", ".md"}


def _snapshot_path() -> Path:
    return Path(settings.SNAPSHOT_PATH or (settings.AGENT_ROOT / "snapshots" / "run.json"))


def _tags(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


@router.get("/status", summary="LLM 키·스냅샷 상태")
def status():
    snap = _snapshot_path()
    entries = 0
    if snap.exists():
        try:
            import json
            entries = len(json.loads(snap.read_text(encoding="utf-8")).get("entries", {}))
        except Exception:
            entries = -1                  # 읽히지 않는 스냅샷 — 있다는 사실만 알린다
    has_key = engines.has_anthropic_key()
    return {
        "anthropic_api_key": has_key,
        "snapshot": {"path": str(snap), "exists": snap.exists(), "entries": entries},
        "runnable": has_key or entries > 0,
        "note": ("키도 스냅샷도 없으면 이 파이프라인은 돌지 않습니다 — "
                 "문서 해석을 전부 LLM 에 맡기는 설계라 둘 중 하나가 필요합니다."),
    }


@router.get("/tags", summary="대사 대상 태그 목록")
def tags():
    main = engines.agent("main")
    schema = main.load_json("tag_schema.json")
    return {"version": schema.get("version"),
            "sections": [{"id": s.get("id"), "name": s.get("name") or s.get("label"),
                          "elements": [e.get("id") for e in s.get("elements", [])]}
                         for s in schema.get("sections", [])]}


async def _prepare(contract: UploadFile, statement: UploadFile) -> tuple[Path, Path, Path]:
    workdir = uploads.new_workdir("agent")
    c = await uploads.save(contract, workdir, AGENT_SUFFIXES, "contract.pdf")
    s = await uploads.save(statement, workdir, AGENT_SUFFIXES, "statement.pdf")
    if {c.suffix.lower(), s.suffix.lower()} - {".txt", ".md"} and not engines.has_docling():
        raise HTTPException(503, detail={
            "message": "docling 이 없어 PDF/DOCX 를 읽을 수 없습니다 (txt·md 는 가능)"})
    return workdir, c, s


@router.post("/reconcile", summary="계약서 ↔ 핵심상품설명서 대사")
async def reconcile(
    contract: UploadFile = File(..., description="신탁계약서"),
    statement: UploadFile = File(..., description="핵심상품설명서"),
    tags: Optional[str] = Form(None, description="이번에 볼 태그만 쉼표로 (기본: 전부)"),
    authority: str = Form("contract", description="contract | change_table"),
    llm_backend: str = Form("auto", description="auto | anthropic | snapshot"),
    verify_all_pairs: bool = Form(False, description="태그가 같은 쌍도 재확인 (정확↑ 비용↑)"),
    save_glossary: bool = Form(False, description="LLM 이 제안한 용어를 파일에 저장"),
    wait: float = Form(0, description="LLM 호출이라 보통 분 단위 — 기본은 폴링"),
):
    if authority not in ("contract", "change_table"):
        raise HTTPException(400, detail={"message": "authority 는 contract 또는 change_table"})
    if llm_backend not in ("auto", "anthropic", "snapshot"):
        raise HTTPException(400, detail={"message": "llm_backend 는 auto|anthropic|snapshot"})

    workdir, c, s = await _prepare(contract, statement)
    tag_list = _tags(tags)

    def run(job) -> dict:
        main = engines.agent("main")
        reporting = engines.agent("report")
        docmodel = engines.agent("docmodel")
        job.log(f"대사 시작 {c.name} ↔ {s.name}  backend={llm_backend}")
        try:
            rep = main.reconcile(
                str(c), str(s), tags=tag_list, authority=authority,
                llm_backend=llm_backend, snapshot=str(_snapshot_path()),
                verify_all_pairs=verify_all_pairs, save_glossary=save_glossary)
        except _unavailable() as exc:
            raise RuntimeError(f"{exc} {_hint(llm_backend)}") from exc
        job.log(" · ".join(f"{k} {v}" for k, v in rep.summary.items()))
        return {"summary": rep.summary,
                "report": docmodel.to_jsonable(rep),
                "markdown": reporting.to_markdown(rep)}

    return http.submit("agent", "agent.reconcile", run, workdir=workdir,
                       params={"contract": c.name, "statement": s.name,
                               "tags": tag_list, "backend": llm_backend},
                       wait=http.clamp_wait(wait))


@router.post("/bundle", summary="대사 + 중간 산출물 전부 (뷰어용)")
async def bundle(
    contract: UploadFile = File(...),
    statement: UploadFile = File(...),
    tags: Optional[str] = Form(None),
    authority: str = Form("contract"),
    llm_backend: str = Form("auto"),
    verify_all_pairs: bool = Form(False),
    wait: float = Form(0),
):
    workdir, c, s = await _prepare(contract, statement)
    tag_list = _tags(tags)

    def run(job) -> dict:
        main = engines.agent("main")
        job.log(f"번들 생성 {c.name} ↔ {s.name}")
        try:
            return main.build_bundle(
                str(c), str(s), tags=tag_list, authority=authority,
                llm_backend=llm_backend, snapshot=str(_snapshot_path()),
                verify_all_pairs=verify_all_pairs)
        except _unavailable() as exc:
            raise RuntimeError(f"{exc} {_hint(llm_backend)}") from exc

    return http.submit("agent", "agent.bundle", run, workdir=workdir,
                       params={"contract": c.name, "statement": s.name, "tags": tag_list},
                       wait=http.clamp_wait(wait))


def _hint(backend: str) -> str:
    """왜 못 돌았는지에 맞는 다음 수를 알려준다 — 이미 쓴 방법을 다시 권하지 않는다."""
    if backend == "snapshot":
        return ("— 이 스냅샷에는 해당 호출 기록이 없습니다. ANTHROPIC_API_KEY 를 설정하고 "
                "llm_backend=auto 로 한 번 돌리면 기록이 쌓입니다.")
    return "— ANTHROPIC_API_KEY 를 설정하거나, 기록본이 있으면 llm_backend=snapshot 을 쓰세요."


def _unavailable() -> type:
    """LLMUnavailable 을 지연 조회한다 — 임포트가 실패해도 서버는 떠 있어야 한다."""
    try:
        return engines.agent("llm.client").LLMUnavailable
    except Exception:
        return RuntimeError
