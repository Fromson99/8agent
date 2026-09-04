"""AGENT6 근거 연결 편집 API — 체크리스트 항목 ↔ 법령 조항의 선을 사람이 잇고 끊는다.

    GET    /v1/agent6/graph              코퍼스·구조·체크리스트·연결선 한 덩어리
    GET    /v1/agent6/doc/{doc_id}       그 코퍼스의 구역 트리만
    POST   /v1/agent6/links              연결 추가 (항목 YAML 의 basis 에 한 줄)
    DELETE /v1/agent6/links              연결 절단
    GET    /v1/agent6/search             구역 본문 검색 (연결할 조항 찾기)

## 왜 UI 가 필요한가

`basis` 좌표를 손으로 적으면 두 가지가 자주 틀린다 — **없는 좌표를 적는 것**과
**여러 곳에 걸리는 좌표를 적는 것**이다. 실측(2026-08-06)에서 30개 항목 중 6개가
후자로 활성화 차단 상태였다. 어느 쪽이든 사람은 구조화된 문서를 눈으로 보지 못한 채
좌표를 상상해서 적었기 때문이다.

그래서 이 API 는 **구조화 산출물을 그대로 펴서** 보여 주고, 사람이 고른 구역의
`section_id` 를 그대로 basis 에 적는다. 상상할 자리가 없다.

## 쓰기는 항목 YAML 이 정본이다

연결을 별도 DB 에 두면 체크리스트 파일과 어긋난다. 이 API 는 `checklist/items/*.yaml`
을 직접 고친다 — 그 파일이 판정 파이프라인이 읽는 정본이고, git 이 변경 이력을 남긴다.
대신 **주석과 순서를 보존**하기 위해 통째로 다시 쓰지 않고 `basis:` 블록만 갈아 끼운다.

## 연결을 바꾼 뒤에는 코퍼스를 다시 빌드해야 한다

발췌(`corpus/excerpts/`)는 basis 좌표를 보고 물질화된다. 선을 이었다고 발췌가 저절로
생기지 않는다. 응답의 `needs_rebuild` 가 그 사실을 알린다 — 조용히 반쪽 상태로 두지
않기 위한 것이다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/agent6", tags=["agent6"])

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "lawrag" / "agents" / "agent6"
ITEMS_DIR = AGENT / "checklist" / "items"
CORPUS = Path(os.environ.get("AGENT6_CORPUS_DIR", AGENT / "corpus"))
STRUCTURED = CORPUS / "structured"
MANIFEST = CORPUS / "manifest.json"


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def _manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _corpora() -> list[dict]:
    """코퍼스 목록. 구조화가 끝난 것만 트리를 펼 수 있다."""
    man = _manifest()
    rows = []
    for c in man.get("corpora", []):
        doc_json = STRUCTURED / f"{c['id']}.doc.json"
        rows.append({
            "id": c["id"], "title": c.get("title", c["id"]),
            "doc_type": c.get("doc_type", ""), "edition": c.get("edition", ""),
            "status": c.get("status", ""), "verification": c.get("verification", ""),
            "sections": c.get("sections", 0),
            "structured": doc_json.exists(),
            "wanted_by": c.get("wanted_by", []),
        })
    # manifest 에 없어도 구조화 산출이 있으면 보여 준다 — 코어에서 갓 구조화한 문서를
    # 체크리스트에 붙이려면 목록에 떠야 한다.
    known = {r["id"] for r in rows}
    for p in sorted(STRUCTURED.glob("*.doc.json")):
        did = p.name[: -len(".doc.json")]
        if did not in known:
            rows.append({"id": did, "title": did, "doc_type": "", "edition": "",
                         "status": "UNREGISTERED", "verification": "",
                         "sections": 0, "structured": True, "wanted_by": []})
    return rows


def _tree(doc_id: str) -> list[dict]:
    """구역 트리 — core 구조화 산출(doc.json)을 그대로 편다.

    `children` 은 구조화기가 만든 간선이다. 여기서 계층을 다시 유추하지 않는다.
    """
    p = STRUCTURED / f"{doc_id}.doc.json"
    if not p.exists():
        raise HTTPException(404, f"구조화 산출이 없습니다: {doc_id}")
    doc = json.loads(p.read_text(encoding="utf-8"))
    parent: dict[str, Optional[str]] = {}
    for s in doc.get("sections", []):
        for c in s.get("children", []):
            parent[c] = s["section_id"]
    out = []
    for s in doc.get("sections", []):
        marker = s.get("marker", {})
        body = [i.get("text", "") for i in s.get("content", [])
                if i.get("type") != "table" and i.get("text")]
        out.append({
            "section_id": s["section_id"],
            "label": (s.get("path") or [s["section_id"]])[-1],
            "title": marker.get("title") or marker.get("term") or "",
            "kind": marker.get("kind", ""),
            "level": len(s.get("path") or []) - 1,
            "parent": parent.get(s["section_id"]),
            "children": s.get("children", []),
            "pages": s.get("page_range", []),
            "preview": " ".join(body)[:260],
            "chars": sum(len(b) for b in body),
        })
    return out


def _items() -> list[dict]:
    """체크리스트 항목 + 각 항목이 건 basis 좌표."""
    import yaml

    rows = []
    for p in sorted(ITEMS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        basis = []
        for b in raw.get("basis") or []:
            basis.append({"doc": b.get("doc", ""), "section": b.get("section"),
                          "term": b.get("term"), "note": b.get("note", "")})
        rows.append({
            "id": raw.get("id", p.stem), "name": raw.get("name", ""),
            "type": raw.get("type", ""), "when": str(raw.get("when", "always")),
            "enabled": raw.get("enabled", True),
            "definition": (raw.get("operational_definition") or "").strip()[:400],
            "basis": basis, "file": p.name,
        })
    return rows


def _links(items: list[dict]) -> list[dict]:
    """항목 ↔ 좌표 연결선. manifest 의 해소 결과를 그대로 얹는다."""
    man = _manifest()
    by_coord = {b["coord"]: b for b in man.get("basis", [])}
    out = []
    for it in items:
        for i, b in enumerate(it["basis"]):
            coord = b["doc"]
            if b.get("section"):
                coord = f"{coord}/{b['section']}"
            if b.get("term"):
                coord = f"{coord}#{b['term']}"
            row = by_coord.get(coord, {})
            out.append({
                "item": it["id"], "index": i, "coord": coord,
                "doc": b["doc"], "section": b.get("section"), "term": b.get("term"),
                "note": b.get("note", ""),
                "status": row.get("status", "UNKNOWN"),
                "resolved": row.get("resolved"),
                "section_id": row.get("section_id"),
                "citation": row.get("citation", ""),
                "candidates": [c.get("section_id") for c in
                               (row.get("anchor") or {}).get("candidates", [])],
                "reason": row.get("reason") or "",
            })
    return out


@router.get("/graph", summary="코퍼스·체크리스트·연결선")
def graph(doc: Optional[str] = Query(None, description="이 코퍼스의 트리도 함께")):
    items = _items()
    payload: dict[str, Any] = {
        "corpora": _corpora(), "items": items, "links": _links(items),
        "blocked": _manifest().get("blocked_items", {}),
    }
    if doc:
        payload["tree"] = {doc: _tree(doc)}
    return payload


@router.get("/doc/{doc_id}", summary="구역 트리")
def doc_tree(doc_id: str):
    return {"doc": doc_id, "sections": _tree(doc_id)}


@router.get("/search", summary="구역 본문 검색")
def search(q: str = Query(..., min_length=2), doc: Optional[str] = None,
           limit: int = 40):
    """연결할 조항을 글자로 찾는다. **런타임 판정 경로가 아니다** — 편집 화면 전용이다."""
    hits = []
    docs = [doc] if doc else [c["id"] for c in _corpora() if c["structured"]]
    needle = q.replace(" ", "")
    for did in docs:
        try:
            secs = _tree(did)
        except HTTPException:
            continue
        for s in secs:
            hay = (s["title"] + s["preview"]).replace(" ", "")
            if needle in hay:
                hits.append({"doc": did, **s})
                if len(hits) >= limit:
                    return {"query": q, "hits": hits, "truncated": True}
    return {"query": q, "hits": hits, "truncated": False}


# ---------------------------------------------------------------------------
# 쓰기 — 항목 YAML 의 basis 블록만 갈아 끼운다
# ---------------------------------------------------------------------------

class LinkEdit(BaseModel):
    item: str                                  # 체크리스트 항목 id (A-01 …)
    doc: str                                   # 코퍼스 id (KSB …)
    section: Optional[str] = None              # section_id (제21조/제1호)
    term: Optional[str] = None                 # 용어 앵커
    note: str = ""


_BASIS_BLOCK = re.compile(r"^basis:\n(?:[ \t]+.*\n|\n)*", re.MULTILINE)


def _item_path(item_id: str) -> Path:
    p = ITEMS_DIR / f"{item_id}.yaml"
    if not p.exists():
        raise HTTPException(404, f"항목이 없습니다: {item_id}")
    return p


def _fmt_basis(rows: list[dict]) -> str:
    """basis 블록을 YAML 로. 항목 파일의 기존 표기(한 줄 매핑)를 그대로 따른다."""
    if not rows:
        return "basis: []\n"
    out = ["basis:"]
    for b in rows:
        parts = [f"doc: {b['doc']}"]
        if b.get("section"):
            parts.append(f'section: "{b["section"]}"')
        if b.get("term"):
            parts.append(f"term: {b['term']}")
        if b.get("note"):
            note = str(b["note"]).replace('"', "'")
            parts.append(f'note: "{note}"')
        out.append("  - { " + ", ".join(parts) + " }")
    return "\n".join(out) + "\n"


def _read_basis(path: Path) -> list[dict]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(raw.get("basis") or [])


def _write_basis(path: Path, rows: list[dict]) -> None:
    """`basis:` 블록만 갈아 끼운다 — 나머지 주석·순서는 그대로 둔다.

    통째로 재직렬화하면 항목 파일의 `note:` 서술과 주석이 전부 사라진다. 그 서술이
    "왜 이 근거인가"를 담고 있어서 사람이 다음에 볼 때 판단의 근거가 된다.
    """
    text = path.read_text(encoding="utf-8")
    block = _fmt_basis(rows)
    if _BASIS_BLOCK.search(text):
        text = _BASIS_BLOCK.sub(block, text, count=1)
    else:
        # basis 가 아직 없는 항목 — operational_definition 앞에 끼운다
        anchor = text.find("operational_definition:")
        text = (text[:anchor] + block + text[anchor:]) if anchor >= 0 else text + block
    path.write_text(text, encoding="utf-8")


def _same(a: dict, b: LinkEdit) -> bool:
    return (a.get("doc") == b.doc and (a.get("section") or None) == (b.section or None)
            and (a.get("term") or None) == (b.term or None))


@router.post("/links", summary="연결 추가")
def add_link(edit: LinkEdit):
    if not edit.section and not edit.term:
        raise HTTPException(400, "section 또는 term 중 하나는 있어야 합니다 — "
                                 "코퍼스 id 만으로는 어디를 인용할지 알 수 없습니다")
    path = _item_path(edit.item)
    rows = _read_basis(path)
    if any(_same(r, edit) for r in rows):
        raise HTTPException(409, "이미 연결돼 있습니다")
    rows.append({"doc": edit.doc, "section": edit.section, "term": edit.term,
                 "note": edit.note})
    _write_basis(path, rows)
    return {"ok": True, "item": edit.item, "basis": _read_basis(path),
            "needs_rebuild": True,
            "note": "발췌를 물질화하려면 corpus_build 를 다시 돌려야 합니다"}


@router.delete("/links", summary="연결 절단")
def cut_link(edit: LinkEdit):
    path = _item_path(edit.item)
    rows = _read_basis(path)
    kept = [r for r in rows if not _same(r, edit)]
    if len(kept) == len(rows):
        raise HTTPException(404, "그런 연결이 없습니다")
    _write_basis(path, kept)
    return {"ok": True, "item": edit.item, "basis": kept, "needs_rebuild": True}


# ---------------------------------------------------------------------------
# 점검 실행 — 전사를 넣으면 체크리스트 + 연결된 근거로 판정한다
# ---------------------------------------------------------------------------
#
# 화면에서 STT 전사를 붙여 넣으면 그대로 §5 파이프라인을 탄다. 여기서 새로 만드는
# 것은 없다 — `cli.run_pipeline` 이 정본이고 이 엔드포인트는 **입출력만 바꾼다.**
# 두 경로가 다른 코드를 타면 "CLI 에서는 되는데 화면에서는 안 된다" 가 생긴다.
#
# 모델은 하이쿠를 기본으로 둔다. 이 판정은 **가르는 일**이지 짓는 일이 아니고,
# 근거 발췌·운영정의가 프롬프트에 이미 실려 있어 모델이 지어낼 자리가 좁다.

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"


class RunRequest(BaseModel):
    transcript: str                     # STT 전사 — JSON 또는 평문
    meta: Optional[dict] = None         # 상품·고객 메타 (없으면 조건부 항목이 보수 활성)
    consistency: int = 1                # 자기일관성 회차. 화면에서는 1 이 기본(빠르다)
    model: str = DEFAULT_JUDGE_MODEL
    basis_policy: str = "warn"


@router.post("/run", summary="전사 점검 — 체크리스트 + 연결된 근거로 판정")
def run_check(req: RunRequest):
    """전사를 받아 리포트를 돌려준다. 산출물은 임시 디렉터리에 쓰고 지운다."""
    import tempfile

    from lawrag.agents.agent6.src import aggregate as agg_mod
    from lawrag.agents.agent6.src import cli as cli_mod

    text = (req.transcript or "").strip()
    if not text:
        raise HTTPException(400, "전사가 비어 있습니다")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # JSON 이면 .json, 아니면 평문 .txt 로 떨군다 — 로더가 확장자로 가른다.
        suffix = ".json" if text.lstrip().startswith(("{", "[")) else ".txt"
        tp = d / f"transcript{suffix}"
        tp.write_text(text, encoding="utf-8")
        try:
            res = cli_mod.run_pipeline(
                tp, meta=req.meta, out_dir=d / "out",
                llm_mode="live", consistency=max(1, req.consistency),
                model=req.model, basis_policy=req.basis_policy,
                append_queue=False, history=False)
        except Exception as exc:
            raise HTTPException(500, f"점검에 실패했습니다: {type(exc).__name__}: {exc}")

        rep = res.report
        judged = res.judged
        audit = judged.basis_audit or {}
        t = judged.llm_totals or {}
        rows = [{
            "id": r.id, "name": r.name, "type": r.type, "verdict": r.verdict,
            "route": r.route, "confidence": r.confidence,
            "evidence": [{"utterance": e.utterance, "quote": e.quote,
                          "speaker": getattr(e, "speaker", "")}
                         for e in (r.evidence or [])],
            "reason": r.reason, "basis": [b for b in (r.basis or [])],
        } for r in rep.items]
        return {
            "overall": rep.overall,
            "counts": {v: sum(1 for r in rep.items if r.verdict == v)
                       for v in {r.verdict for r in rep.items}},
            "routes": agg_mod.route_counts(rep.items),
            "items": rows,
            "guidance": (d / "out" / "guidance.md").read_text(encoding="utf-8")
                        if (d / "out" / "guidance.md").exists() else "",
            "checked": res.checked,
            "unavailable": sorted(judged.unavailable or []),
            "context": {"batches": audit.get("batches", 0),
                        "items": audit.get("items", 0),
                        "with_basis_text": audit.get("with_basis_text", 0),
                        "chars": audit.get("chars", 0)},
            "llm": {"model": req.model, "calls": judged.calls,
                    "input_tokens": t.get("input_tokens", 0),
                    "output_tokens": t.get("output_tokens", 0),
                    "errors": t.get("errors", 0),
                    "seconds": round(judged.seconds, 1)},
            "warnings": list(rep.warnings or []),
        }
