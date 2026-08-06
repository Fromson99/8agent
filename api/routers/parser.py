"""trust-parser — 온톨로지 기반 결정론 엔진.

    POST /v1/parser/parse           PDF → chunks.json          (도클링 필요, 무겁다)
    POST /v1/parser/reconcile       chunks + 요약서 → 리포트
    POST /v1/parser/reconcile/json  위와 같되 파일 업로드 없이 JSON 으로
    POST /v1/parser/query           질의 → fact 조회 또는 청크 검색
    GET  /v1/parser/documents       파싱해 둔 문서 목록 (채팅이 참조하는 것과 같은 보관소)
    GET  /v1/parser/ontology        현재 온톨로지 전문
    GET  /v1/parser/fields          별지1 필드 목록 (질의·대사에 쓸 이름 확인용)

파싱만 도클링이 필요하다. 대사·질의는 순수 파이썬이라 가벼운 이미지에서도 돈다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import engines, http, settings, uploads
from ..documents import STORE as DOCS

router = APIRouter(prefix="/v1/parser", tags=["trust-parser"],
                   dependencies=[Depends(http.require_token)])

NO_DOCLING = ("docling 이 설치되어 있지 않습니다. PDF 파싱은 이 엔드포인트에서만 필요합니다 — "
              "requirements.txt 로 설치하거나, 이미 만들어 둔 chunks.json 을 "
              "/v1/parser/reconcile · /v1/parser/query 에 바로 넣으세요.")


def _need_docling() -> None:
    if not engines.has_docling():
        raise HTTPException(503, detail={"message": NO_DOCLING})


# ---------------------------------------------------------------------------
# Part A — 파싱
# ---------------------------------------------------------------------------

@router.post("/parse", summary="PDF → chunks.json (Part A)")
async def parse(
    file: UploadFile = File(..., description="계약서 PDF/DOCX/PPTX/HTML"),
    name: Optional[str] = Form(None, description="document 필드에 쓸 이름"),
    llm_roles: bool = Form(False, description="T6 세부 의미역 태깅 (ANTHROPIC_API_KEY 필요)"),
    llm_axioms: bool = Form(False, description="T17 공리 후보 추출 (ANTHROPIC_API_KEY 필요)"),
    llm_limit: Optional[int] = Form(None, description="LLM 에 넘길 청크 수 상한 (비용 통제)"),
    wait: float = Form(0, description="이 초만큼 기다렸다 결과가 있으면 동봉"),
):
    _need_docling()
    workdir = uploads.new_workdir("parse")
    pdf = await uploads.save(file, workdir, settings.DOC_SUFFIXES, "contract.pdf")

    def run(job) -> dict:
        emit = engines.parser("emit")
        onto = engines.ontology()
        job.log(f"파싱 시작 {pdf.name}")
        doc, violations, meta = emit.run(str(pdf), onto, name)
        job.log(f"조 {meta['articles']}개 · 청크 {meta['chunks']}개 · "
                f"위반 {meta['violations']['total']}건")
        dumped = doc.dump()
        # 파싱하자마자 보관소에 넣는다 — 채팅(`/chat/stream`)이 곧바로 이 문서를 물어볼 수 있다
        registered = DOCS.register(name or pdf.stem, dumped, source="upload")
        job.log(f"문서 등록 doc_id={registered.doc_id}")
        out: dict[str, Any] = {
            "doc_id": registered.doc_id,
            "document": dumped,
            "meta": meta,
            "violations": [v.as_dict() for v in violations],
        }
        if llm_roles or llm_axioms:
            out["llm"] = _llm_enrich(job, doc, onto, llm_roles, llm_axioms, llm_limit)
        return out

    return http.submit("parser", "parser.parse", run, workdir=workdir,
                       params={"file": pdf.name, "llm_roles": llm_roles,
                               "llm_axioms": llm_axioms},
                       wait=http.clamp_wait(wait))


def _llm_enrich(job, doc, onto, roles_on: bool, axioms_on: bool,
                limit: Optional[int]) -> dict:
    """T6/T17 — CLI 의 `--llm-roles` / `--llm-axioms` 와 같은 경로."""
    llm_client = engines.parser("llm_client")
    llm = llm_client.LLM()
    info: dict[str, Any] = {"model": llm.model}
    if roles_on:
        roles, warns = engines.parser("tag_llm").enrich(doc.chunks, onto, llm, limit)
        info["roles"] = roles
        info["role_warnings"] = warns
        job.log(f"T6 의미역 {len(roles)}개")
    if axioms_on:
        ax = engines.parser("axiom_extract")
        axioms, warns = ax.extract(doc.chunks, onto, llm, limit)
        # 전부 approved=false 다 — 사람이 검토해 온톨로지에 직접 반영한다(자동 적용 안 함)
        info["axioms"] = axioms
        info["axiom_warnings"] = warns
        info["axioms_yaml"] = ax.to_yaml_block(axioms)
        job.log(f"T17 공리 후보 {len(axioms)}건")
    info["totals"] = llm.totals()
    return info


# ---------------------------------------------------------------------------
# Part B — 정합성 대사
# ---------------------------------------------------------------------------

def _reconcile(contract: Path, summary: Path,
               names: Optional[tuple[str, str]] = None) -> dict:
    reconcile = engines.parser("reconcile")
    reconcile_emit = engines.parser("reconcile_emit")
    onto = engines.ontology()
    report = reconcile.run(contract, summary, onto)
    # 리포트가 들고 있는 건 임시 경로다. 호출자가 준 이름으로 되돌린다 —
    # 서버 내부 경로를 응답에 흘리지 않고, 감사 기록에 남는 이름이 원본과 맞는다.
    report.contract, report.summary = names or (contract.name, summary.name)
    return {"report": report.model_dump(mode="json"),
            "text": reconcile_emit.to_text(report),
            "stats": report.stats}


@router.post("/reconcile", summary="chunks.json + 요약서 → 정합성 리포트 (Part B)")
async def reconcile_upload(
    contract: UploadFile = File(..., description="체결 계약서의 chunks.json"),
    summary: Optional[UploadFile] = File(None, description="투자요약서 (pdf/md/txt)"),
    summary_text: Optional[str] = Form(None, description="요약서를 마크다운 문자열로 직접"),
    wait: float = Form(30, description="마크다운 요약서는 보통 이 안에 끝난다"),
):
    if summary is None and not summary_text:
        raise HTTPException(400, detail={
            "message": "summary 파일 또는 summary_text 중 하나는 있어야 합니다"})

    workdir = uploads.new_workdir("reconcile")
    c_path = await uploads.save(contract, workdir, settings.CHUNKS_SUFFIXES, "contract.chunks.json")
    if summary is not None:
        s_path = await uploads.save(summary, workdir, settings.SUMMARY_SUFFIXES, "summary.md")
        if s_path.suffix.lower() == ".pdf":
            _need_docling()      # PDF 요약서는 Part A 파싱 스택을 재사용한다
    else:
        s_path = uploads.write_text(summary_text or "", workdir, "summary.md")

    def run(job) -> dict:
        job.log(f"대사 {c_path.name} ↔ {s_path.name}")
        out = _reconcile(c_path, s_path)
        job.log(" · ".join(f"{k} {v}" for k, v in out["stats"].items()))
        return out

    return http.submit("parser", "parser.reconcile", run, workdir=workdir,
                       params={"contract": c_path.name, "summary": s_path.name},
                       wait=http.clamp_wait(wait))


class ReconcileJson(BaseModel):
    """파일 업로드 없이 JSON 만으로 — 에이전트끼리 붙일 때 이쪽이 편하다."""
    contract_chunks: dict = Field(..., description="chunks.json 내용 그대로")
    summary_markdown: str = Field(..., description="투자요약서 마크다운 (표 또는 `라벨: 값` 줄)")


@router.post("/reconcile/json", summary="대사 — JSON 입출력 (동기, 도클링 불필요)")
def reconcile_json(body: ReconcileJson):
    workdir = uploads.new_workdir("reconcile-json")
    try:
        c = uploads.write_text(json.dumps(body.contract_chunks, ensure_ascii=False),
                               workdir, "contract.chunks.json")
        s = uploads.write_text(body.summary_markdown, workdir, "summary.md")
        return _reconcile(c, s, names=("(inline contract_chunks)", "(inline summary_markdown)"))
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Part D — 질의
# ---------------------------------------------------------------------------

class QueryBody(BaseModel):
    question: str = Field(..., min_length=1)
    chunks: Optional[dict] = Field(None, description="chunks.json 내용 그대로")
    doc_id: Optional[str] = Field(None, description="보관소에 등록된 문서 id (chunks 대신)")


@router.post("/query", summary="질의 → fact 조회 또는 청크 검색 (Part D, 동기)")
def query(body: QueryBody):
    """뷰어(`cli serve` 의 /api/query)와 **같은 함수**를 부른다.

    화면과 API 가 다른 답을 내면 그 자체가 사고라, 경로를 하나로 둔다.
    임베딩이 없어 매 단계가 설명 가능하다 — 응답의 `route.path` 가 그 경로다.
    """
    chunks = body.chunks
    if chunks is None:
        if not body.doc_id:
            raise HTTPException(400, detail={"message": "chunks 또는 doc_id 중 하나가 필요합니다"})
        doc = DOCS.get(body.doc_id)
        if doc is None:
            raise HTTPException(404, detail={"message": f"문서를 찾을 수 없습니다: {body.doc_id}"})
        chunks = doc.chunks

    cli = engines.parser("cli")
    onto = engines.ontology()
    out = cli._run_query(chunks, body.question, onto)
    if "error" in out:
        raise HTTPException(422, detail=out)
    return out


# ---------------------------------------------------------------------------
# 문서 보관소 — 채팅과 같은 것을 본다
# ---------------------------------------------------------------------------

@router.get("/documents", summary="파싱해 둔 문서 목록")
def documents():
    return {"documents": [d.summary() for d in DOCS.list()]}


@router.post("/documents", summary="chunks.json 을 직접 등록 (파싱 없이)")
async def add_document(
    file: UploadFile = File(..., description="chunks.json"),
    name: Optional[str] = Form(None),
):
    workdir = uploads.new_workdir("doc")
    try:
        p = await uploads.save(file, workdir, settings.CHUNKS_SUFFIXES, "document.chunks.json")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "chunks" not in data:
            raise HTTPException(422, detail={"message": "chunks 배열이 있는 chunks.json 이 아닙니다"})
        return DOCS.register(name or p.stem, data, source="upload").summary()
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


@router.post("/documents/rescan", summary="디스크의 chunks.json 다시 훑기")
def rescan_documents():
    return {"disk_documents": DOCS.rescan(),
            "documents": [d.summary() for d in DOCS.list()]}


@router.delete("/documents/{doc_id}", summary="문서 폐기")
def delete_document(doc_id: str):
    if not DOCS.delete(doc_id):
        raise HTTPException(404, detail={"message": f"문서를 찾을 수 없습니다: {doc_id}"})
    return {"deleted": doc_id}


# ---------------------------------------------------------------------------
# 온톨로지
# ---------------------------------------------------------------------------

@router.get("/ontology", summary="현재 온톨로지 전문 (제약 계층)")
def ontology():
    return engines.ontology().model_dump(mode="json", exclude_none=True)


@router.get("/fields", summary="별지1 필드 목록 — 질의·대사에서 쓸 이름")
def fields():
    onto = engines.ontology()
    return {"doc_type": onto.doc_type,
            "fields": [{"name": n,
                        "value_type": getattr(s, "value_type", None),
                        "article": getattr(s, "article", None),
                        "derived": getattr(s, "derived", None),
                        "cq": getattr(s, "cq", None)}
                       for n, s in onto.fields.items()]}
