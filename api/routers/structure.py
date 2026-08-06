"""구조 해석기 검수 API — 해석 결과를 원본 PDF 위에 되돌려 보여 주기 위한 것.

    POST /v1/structure/documents        PDF 업로드 → 해석 → doc_id
    GET  /v1/structure/documents        올라온 문서 목록
    GET  /v1/structure/{doc_id}         검수 payload (트리 + 블록 + 좌표)
    GET  /v1/structure/{doc_id}/page/N  페이지 이미지 (PNG)
    GET  /v1/structure/{doc_id}/pdf     원본 PDF
    DELETE /v1/structure/{doc_id}

    GET/POST/DELETE /v1/structure/rules/custom   사람이 등록하는 표면 패턴 (SPEC §6)
    GET  /v1/structure/rules/signals             관리소 등록 현황

## 페이지를 서버에서 PNG 로 렌더하는 이유

PDF.js 를 붙이면 뷰어가 CDN 이나 번들에 묶인다. 이 서비스는 **컨테이너 안에서 망 없이**
돌아야 하고, PyMuPDF 는 파싱 때문에 이미 들어와 있다. 그래서 서버가 페이지를 그려
주고 화면은 `<img>` 위에 `<div>` 를 얹기만 한다. 의존성이 늘지 않고 오프라인에서 돈다.

## 좌표를 비율로 주는 이유

`core.structure.viewer` 가 bbox 를 0~1 로 정규화해 준다. 화면이 어떤 배율로 이미지를
받든 그대로 곱하면 되고, 서버는 화면 배율을 몰라도 된다.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/structure", tags=["structure"])

ROOT = Path(__file__).resolve().parents[2]
STORE = Path(os.environ.get("STRUCTURE_STORE", ROOT / "out" / "structure" / "viewer"))
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "40"))
RENDER_SCALE = float(os.environ.get("STRUCTURE_RENDER_SCALE", "2.0"))


def _dir(doc_id: str) -> Path:
    """저장 경로. `..` 같은 걸 넣어도 밖으로 못 나가게 id 를 강제한다."""
    if not doc_id or not all(c.isalnum() or c in "-_" for c in doc_id):
        raise HTTPException(400, "doc_id 형식이 올바르지 않습니다")
    return STORE / doc_id


def _meta(d: Path) -> dict:
    p = d / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _parse_cached(pdf: Path, cache: Path):
    """파싱은 **한 번만** 한다. 비싼 것은 docling 모델 추론이고 해석(S0~S5)은 싸다.

    규칙을 고치고 다시 해석할 때마다 몇 분씩 기다리게 하지 않으려고 가른다.
    캐시가 깨졌으면 조용히 다시 파싱한다 — 낡은 형식 때문에 문서를 못 열면 안 된다.
    """
    from core import parse_adapter

    if cache.exists():
        try:
            return parse_adapter.result_from_dump(json.loads(cache.read_text("utf-8")))
        except Exception:
            pass
    parsed = parse_adapter.parse(pdf)
    cache.write_text(json.dumps(parse_adapter.result_to_dump(parsed), ensure_ascii=False),
                     encoding="utf-8")
    return parsed


def _interpret(pdf: Path, cache: Optional[Path] = None, **kw) -> dict:
    from core.structure import pipeline, viewer
    from core.structure.model import Block

    parsed = _parse_cached(pdf, cache or pdf.parent / "parse.json")
    blocks = Block.from_elements(parsed.elements)
    result = pipeline.interpret(blocks, doc=pdf.name, pdf_path=str(pdf), **kw)
    data = viewer.payload(result, blocks, pdf_path=pdf, elements=parsed.elements,
                          images=parsed.images)
    data["parser_warnings"] = parsed.warnings
    return data


def _hint_kwargs(root, families, ladder, order) -> dict:
    """사람이 넣는 힌트(§7)를 `pipeline.interpret` 인자로. 업로드와 재해석이 같은 것을
    받아야 하므로 한 곳에 둔다 — 두 곳에 있으면 한쪽만 고쳐져 결과가 갈린다."""
    kw: dict = {"root": root or None}
    if families:
        kw["families"] = [x.strip() for x in families.split(",") if x.strip()]
    if ladder:
        kw["ladder_hint"] = [[y.strip() for y in g.split(",") if y.strip()]
                             for g in ladder.split(";") if g.strip()]
    if order:
        pairs = []
        for x in order.split(","):
            a, _, b = x.partition(">")
            if b:
                pairs.append((a.strip(), b.strip()))
        kw["partial_order"] = pairs
    return kw


@router.post("/documents", summary="PDF 업로드 → 구조 해석")
async def upload(
    file: UploadFile = File(...),
    root: Optional[str] = Form(None),
    families: Optional[str] = Form(None, description="쉼표 구분 (예: dot_number,roman)"),
    ladder: Optional[str] = Form(None, description="층마다 세미콜론, 같은 층은 쉼표"),
    order: Optional[str] = Form(None, description="'A>B' 를 쉼표로 (예: kr_장>kr_절)"),
    use_llm: bool = Form(False, description="잔여를 배치 1콜로 해소"),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 만 받습니다")
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"파일이 {MAX_MB}MB 를 넘습니다")

    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    d = _dir(doc_id)
    d.mkdir(parents=True, exist_ok=True)
    pdf = d / "source.pdf"
    pdf.write_bytes(raw)

    kw = _hint_kwargs(root, families, ladder, order)
    if use_llm:
        from core.llm import LLM
        kw["llm"] = LLM()

    try:
        data = _interpret(pdf, **kw)
    except Exception as exc:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(500, f"해석에 실패했습니다: {type(exc).__name__}: {exc}")

    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "doc_id": doc_id, "name": file.filename, "bytes": len(raw),
        "pages": len(data["pages"]), "score": data["fitness"]["score"],
        "passed": data["fitness"]["passed"], "tier": data["fitness"]["tier"],
        "used_llm": bool(use_llm),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, **_meta(d)}


@router.post("/{doc_id}/reinterpret", summary="같은 문서를 현재 규칙으로 다시 해석")
def reinterpret(doc_id: str, use_llm: bool = Form(False),
                root: Optional[str] = Form(None),
                families: Optional[str] = Form(None),
                ladder: Optional[str] = Form(None),
                order: Optional[str] = Form(None)):
    """규칙을 고친 뒤 **파싱을 건너뛰고** 해석만 다시 돌린다.

    등록한 표면 패턴(`/rules/custom`)이나 힌트를 바꿔도 다시 올릴 필요가 없다.
    파싱 결과는 `parse.json` 에 굳어 있고 docling 을 다시 부르지 않는다 — 이 갈래가
    없으면 규칙 한 줄 고칠 때마다 몇 분을 기다리게 된다.
    """
    import time

    d = _dir(doc_id)
    pdf = d / "source.pdf"
    if not pdf.exists():
        raise HTTPException(404, f"문서를 찾을 수 없습니다: {doc_id}")

    cache = d / "parse.json"
    cached = cache.exists()          # 없으면 docling 을 다시 돌린다 — 몇 분이 걸린다
    before = _meta(d)
    kw = _hint_kwargs(root, families, ladder, order)
    if use_llm:
        from core.llm import LLM
        kw["llm"] = LLM()
    t0 = time.monotonic()
    try:
        data = _interpret(pdf, cache=cache, **kw)
    except Exception as exc:
        raise HTTPException(500, f"재해석에 실패했습니다: {type(exc).__name__}: {exc}")
    took = round(time.monotonic() - t0, 1)

    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta = _meta(d)
    st = data.get("stats", {})
    meta.update({"score": data["fitness"]["score"], "passed": data["fitness"]["passed"],
                 "tier": data["fitness"]["tier"], "used_llm": bool(use_llm),
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    # 무엇이 바뀌었는지 **숫자로** 돌려준다. "돌긴 돌았는데 뭐가 달라졌는지 모르겠다"
    # 가 가장 나쁘다 — 규칙을 고쳐도 효과를 볼 수 없으면 고칠 이유가 없어진다.
    return {
        "doc_id": doc_id, "reinterpreted": True, **meta,
        "took_sec": took,
        "parse_cached": cached,
        "parse_note": ("파싱 캐시를 썼습니다(docling 생략)" if cached
                       else "파싱 캐시가 없어 docling 을 다시 돌렸습니다 — 다음부터는 빠릅니다"),
        "before": {"score": before.get("score"), "tier": before.get("tier")},
        "delta": {
            "score": round(data["fitness"]["score"] - (before.get("score") or 0), 3),
            "activated": st.get("activated"), "candidates": st.get("candidates"),
            "coverage": st.get("coverage"), "unlocked": st.get("unlocked"),
            "thin_suspects": st.get("thin_suspects"),
        },
    }


@router.get("/documents", summary="올라온 문서 목록")
def documents():
    STORE.mkdir(parents=True, exist_ok=True)
    out = [_meta(d) for d in sorted(STORE.iterdir()) if d.is_dir() and _meta(d)]
    return {"documents": sorted(out, key=lambda m: m.get("at", ""), reverse=True)}


@router.get("/{doc_id}", summary="검수 payload (트리 + 블록 + 좌표)")
def result(doc_id: str):
    p = _dir(doc_id) / "result.json"
    if not p.exists():
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{doc_id}/pdf", summary="원본 PDF")
def source(doc_id: str):
    p = _dir(doc_id) / "source.pdf"
    if not p.exists():
        raise HTTPException(404, f"'{doc_id}' 의 원본이 없습니다")
    return FileResponse(p, media_type="application/pdf")


@router.get("/{doc_id}/page/{page}", summary="페이지 이미지 (PNG)")
def page_image(doc_id: str, page: int,
               scale: float = Query(RENDER_SCALE, ge=0.5, le=4.0)):
    import fitz

    src = _dir(doc_id) / "source.pdf"
    if not src.exists():
        raise HTTPException(404, f"'{doc_id}' 의 원본이 없습니다")

    cache = _dir(doc_id) / "pages" / f"{page}@{scale:g}.png"
    if cache.exists():
        return FileResponse(cache, media_type="image/png")

    doc = fitz.open(str(src))
    try:
        if not 1 <= page <= doc.page_count:
            raise HTTPException(404, f"{page} 쪽이 없습니다 (전체 {doc.page_count}쪽)")
        pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(scale, scale))
        png = pix.tobytes("png")
    finally:
        doc.close()

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(png)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# 사람이 등록하는 표면 패턴 (SPEC §6) — 화면에서 바로 어휘를 넓힌다
# ---------------------------------------------------------------------------

class Rule(BaseModel):
    id: str
    family: Optional[str] = None
    surface: Optional[str] = None
    pattern: str
    groups: list[str] = []
    ordinal_from: list[str] = []
    lang: str = "any"
    note: str = ""


@router.get("/rules/custom", summary="등록된 표면 패턴 목록", tags=["rules"])
def list_rules():
    from core.structure.proposers import custom
    return {"dir": str(custom.DEFAULT_DIR), "rules": custom.describe()}


@router.post("/rules/custom", summary="표면 패턴 등록", tags=["rules"])
def add_rule(rule: Rule):
    """`level`·`rank` 는 받지 않는다 — 계층은 문서가 유도한다(SPEC §6)."""
    import yaml
    from core.structure.proposers import custom

    try:
        data = custom.validate(rule.model_dump(exclude_none=True))
    except custom.RuleError as exc:
        raise HTTPException(400, str(exc))

    d = Path(custom.DEFAULT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{data['id']}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # 시험 적중 — 규칙이 실제로 무엇을 잡는지 등록 즉시 보여 준다.
    import re
    rx = re.compile(data["pattern"])
    samples = [s for s in (rule.note or "").splitlines() if rx.search(s)]
    return {"saved": data["id"], "rule": data, "matched_in_note": samples}


@router.delete("/rules/custom/{rule_id}", summary="표면 패턴 삭제", tags=["rules"])
def remove_rule(rule_id: str):
    from core.structure.proposers import custom
    p = Path(custom.DEFAULT_DIR) / f"{rule_id}.yaml"
    if not p.exists():
        raise HTTPException(404, f"규칙 '{rule_id}' 가 없습니다")
    p.unlink()
    return {"deleted": rule_id}


@router.get("/rules/signals", summary="관리소 등록 현황", tags=["rules"])
def signals():
    from core.structure import registry
    reg = registry.default()
    return {"signals": [{"id": s.id, "role": s.role, "lang": s.lang,
                         "family": s.family, "surface": s.surface}
                        for r in registry.ROLES for s in reg.by_role(r)]}


def _module_patterns(module) -> list[dict]:
    """모듈 안의 컴파일된 정규표현식을 이름과 함께 꺼낸다.

    제안자마다 패턴 상수 이름이 달라(`_FULL`, `_MULTI`, `_UPPER` …) 규약을 새로
    강요하는 대신 우리 모듈을 들여다본다. 화면에 **무엇을 잡는 규칙인지** 그대로
    보여 주기 위한 것이고, 해석 경로는 이 함수를 쓰지 않는다.
    """
    import re as _re
    out = []
    for name, val in sorted(vars(module).items()):
        if isinstance(val, _re.Pattern):
            out.append({"name": name.lstrip("_").lower(), "pattern": val.pattern})
    return out


@router.get("/rules/all", summary="시스템에 들어간 규칙 전부", tags=["rules"])
def all_rules():
    """제안자·가드·계열 정합·전역 증거·점수·사용자 규칙을 한 덩어리로.

    화면이 "지금 이 시스템이 무엇으로 판단하는가"를 통째로 보여 줄 수 있게 한다.
    """
    from core.structure import lexicon as lex_mod
    from core.structure import registry, scoring
    from core.structure.family import anchor, run, succession
    from core.structure.global_inner import nesting, ordinal
    from core.structure.global_outer import indent, ladder, reg_score
    from core.structure.proposers import custom

    reg = registry.default()
    lex = lex_mod.default()

    def sig(s, extra=None):
        d = {"id": s.id, "lang": s.lang, "family": s.family, "surface": s.surface,
             "doc": (s.module.__doc__ or "").strip().split("\n")[0]}
        d.update(extra or {})
        return d

    return {
        "proposers": [sig(s, {"patterns": _module_patterns(s.module)})
                      for s in reg.by_role("proposer")],
        "guards": [sig(s) for s in reg.by_role("local_guard")],
        "family_coherence": [
            {"id": m.ID, "surface": m.SURFACE,
             "doc": (m.__doc__ or "").strip().split("\n")[0]}
            for m in (anchor, run, succession)],
        "global": [
            {"id": "indent", "stage": "S3", "surface": indent.SURFACE,
             "params": {"MIN_GAP": indent.MIN_GAP, "MAX_SPREAD": indent.MAX_SPREAD}},
            {"id": "reset_alignment", "stage": "S3", "surface": "리셋이 상위 경계에 맞나",
             "params": {"MIN_RESET_TOTAL": scoring.MIN_RESET_TOTAL}},
            {"id": "coverage", "stage": "S3", "surface": "상위 구간 중 몇 할이 하위를 품나",
             "params": {"MIN_COVERAGE": ladder.MIN_COVERAGE}},
            {"id": "nesting_evidence", "stage": "S3", "surface": "두 출현 사이에 끼는가",
             "params": {"MIN_NESTING_RATIO": scoring.MIN_NESTING_RATIO}},
            {"id": "reg_score", "stage": "S3", "surface": reg_score.SURFACE,
             "params": {"REG_SCORE_MIN": scoring.REG_SCORE_MIN}},
            {"id": "nesting", "stage": "S4", "surface": "계층성 — 얕은 레벨이 열려 있나",
             "params": {}},
            {"id": "ordinal", "stage": "S4", "surface": "서수 단조",
             "params": {"ORDINAL_REGRESS": scoring.ORDINAL_REGRESS,
                        "ORDINAL_GAP": scoring.ORDINAL_GAP}},
        ],
        "scoring": {
            "국소 가드 (S1)": {
                "블록 여는 자리": scoring.BLOCK_OPEN,
                "블록 중간": scoring.BLOCK_MID,
                "괄호/인라인 내부": scoring.BLOCK_INLINE,
                "조사 깨끗": scoring.PARTICLE_CLEAN,
                "조사 부착": scoring.PARTICLE_ATTACHED,
                "참조 서술어 근접": scoring.PARTICLE_REFERENT,
                "완전형": scoring.CONSTRUCTION_FULL,
                "파편": scoring.CONSTRUCTION_FRAGMENT,
            },
            "DP 전이 벌점 (S4)": {
                "중첩 위반": "FORBID",
                "서수 역행": scoring.ORDINAL_REGRESS,
                "서수 건너뜀": scoring.ORDINAL_GAP,
                "새 레벨 도입": scoring.LEVEL_NOVELTY,
            },
            "게이트 (S5)": {
                "적합도 임계 T": scoring.FITNESS_T,
                "순환 절단 벌점": scoring.PENALTY_CYCLE,
                "순서 미정 벌점": scoring.PENALTY_UNORDERED,
                "미등재 벌점": scoring.PENALTY_UNREGISTERED,
            },
            "잔여 (S5)": {
                "신호 모순 기준 s": scoring.CONFLICT_S,
                "빠진 번호로 볼 거리": scoring.DOUBT_DISTANCE,
                "근소차 마진": scoring.RESIDUAL_MARGIN,
            },
            "계열 정합 (S2)": {
                "연속 단위 최소 길이": run.MIN_CHAIN,
                "가지 표기 시작 번호": succession.FIRST_BRANCH,
            },
        },
        "lexicon": {
            "조사": lex.josa.forms,
            "연쇄 참조": lex.josa._raw_chained,
            "참조 서술어": lex.predicates.words,
            "서수 체계": sorted(lex.numerals.scales),
        },
        "custom": custom.describe(),
    }


@router.delete("/{doc_id}", summary="문서 삭제")
def remove(doc_id: str):
    d = _dir(doc_id)
    if not d.exists():
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    shutil.rmtree(d, ignore_errors=True)
    return {"deleted": doc_id}
