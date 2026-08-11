"""형식(구조화 틀) API — 컴파일 국면을 UI 로 끌어올린 것.

    GET  /v1/formats                 등록된 형식 목록 + 폴더/문서 바인딩
    POST /v1/formats/compile         올라온 문서들로 형식 유도 → 등록부 등재
    GET  /v1/formats/bindings        바인딩 전부
    PUT  /v1/formats/bindings        폴더/문서 → doc_type 연결 (null 이면 해제)
    GET/PUT /v1/formats/canvas       연결 화면의 배치와 미완성 초안

## 무엇을 하는 API 인가

CLI 의 `core.cli compile` 이 하던 일 — 샘플 파싱 → 마커 체계 유도 → 적용 미리보기
→ 홀드아웃 검증 → 형식 저장 → registry 등재 — 를 **이미 올라온 문서**로 한다.
샘플을 다시 올릴 필요가 없다: 뷰어 스토어의 원본과 파싱 캐시를 그대로 쓴다.

## 바인딩의 의미

"이 폴더(또는 이 문서)는 이 구조화 틀을 쓴다"는 연결이다. 바인딩된 문서의
해석(업로드·재해석)은 유도(S0~S6)가 아니라 형식 마커의 결정론 구조화로 돈다.
문서 바인딩이 폴더 바인딩보다 우선한다. 정본은 스토어 옆 `format_bindings.json`
— 문서를 지워도 바인딩 규칙은 남는다(glossary.json 과 같은 자리 규약).

## 용어집 없이 컴파일한다

유도에 쓰던 용어 출현 마킹은 유형별 용어집의 일이었는데, 용어는 전역으로 가는
방향이라 여기서는 **빈 용어집**으로 유도한다 — 마커 체계(regex_markers)만 만들고,
용어형 마커·fact 는 만들지 않는다. router.assets() 도 용어집 없는 route 를 받는다.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/formats", tags=["formats"])

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STORE = Path(os.environ.get("STRUCTURE_STORE", ROOT / "out" / "structure" / "viewer"))
# UI 컴파일이 만든 형식 파일이 놓이는 곳 — 스토어가 아니라 저장소 안이다.
# 형식은 문서 데이터가 아니라 **처리 규칙**이라 registry 가 ROOT 상대경로로 가리킨다.
FORMATS_DIR = Path(os.environ.get("FORMATS_DIR", ROOT / "out" / "structure" / "formats"))
BINDINGS_FILE = Path(os.environ.get("FORMAT_BINDINGS",
                                    STORE.parent / "format_bindings.json"))
CANVAS_FILE = Path(os.environ.get("FORMAT_CANVAS",
                                  STORE.parent / "format_canvas.json"))

# 홀드아웃 몫 — 샘플이 이만큼을 남길 수 있을 때만 뗀다(§2.5: 5개면 3+2)
HOLDOUT_FROM = 4


# ---------------------------------------------------------------------------
# 바인딩 저장소 — {"folders": {이름: doc_type}, "docs": {doc_id: doc_type}}
# ---------------------------------------------------------------------------

def load_bindings() -> dict:
    if BINDINGS_FILE.exists():
        try:
            d = json.loads(BINDINGS_FILE.read_text(encoding="utf-8"))
            return {"folders": dict(d.get("folders", {})),
                    "docs": dict(d.get("docs", {}))}
        except (OSError, json.JSONDecodeError):
            pass
    return {"folders": {}, "docs": {}}


def _save_bindings(b: dict) -> None:
    BINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BINDINGS_FILE.write_text(json.dumps(b, ensure_ascii=False, indent=1),
                             encoding="utf-8")


def binding_for(doc_id: str, folder: str = "") -> Optional[str]:
    """이 문서에 연결된 doc_type. 문서 바인딩이 폴더 바인딩보다 우선한다."""
    b = load_bindings()
    return b["docs"].get(doc_id) or (b["folders"].get(folder) if folder else None)


# ---------------------------------------------------------------------------
# 스토어의 원본 문서 → 컴파일 샘플
# ---------------------------------------------------------------------------

_ORIGINALS = ("source.hwp", "source.hwpx", "source.docx", "source.pdf")

# 원본 형식마다 **파서가 실을 수 있는 신호가 다르다.** 마커(글자)는 어디서나 같지만
# 제목 신호와 지면 좌표는 형식이 정한다 — 섞어서 유도하면 한쪽에서만 도는 형식이 된다.
#
#   pdf   레이아웃 모델의 제목 표시 + 타이포그래피(크기·굵기·간격) + 좌표
#   docx  Word 스타일의 진짜 제목 계층(level). 좌표는 없다(리플로우).
#   hwp   md 변환분 — 제목 선언도 좌표도 없다. **마커만** 남는다.
#
# 그래서 `require_heading` 마커(제목 위치에서만 인정)는 hwp 에서 영영 발화하지 않는다.
KIND_SIGNALS = {
    "pdf": "제목 표시 · 타이포그래피 · 지면 좌표",
    "docx": "제목 계층(Word 스타일) · 좌표 없음",
    "hwp": "마커만 (제목 신호·좌표 없음)",
    "hwpx": "마커만 (제목 신호·좌표 없음)",
    "lawxml": "태그 계층 — 구조화 틀을 쓰지 않는다",
}
# 제목 신호가 오는 형식. 섞임 경고는 이 축으로 가른다(좌표는 구조 판정에 안 쓰인다).
HEADING_KINDS = {"pdf", "docx"}


def _doc_meta(doc_id: str) -> dict:
    p = STORE / doc_id / "meta.json"
    if not p.exists():
        raise HTTPException(404, f"문서를 찾을 수 없습니다: {doc_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _kind_of(doc_id: str) -> str:
    """원본 형식 — structure 라우터의 판단을 그대로 쓴다(두 곳이 갈리면 안 된다)."""
    from api.routers.structure import _source_kind

    return _doc_meta(doc_id).get("source_kind") or _source_kind(STORE / doc_id)


def _original_of(doc_id: str) -> Path:
    d = STORE / doc_id
    for name in _ORIGINALS:
        if (d / name).exists():
            return d / name
    raise HTTPException(400, f"문서 {doc_id} 에 원본 파일이 없습니다")


def _parsed_of(doc_id: str):
    """파싱 결과 — 캐시(parse.json)가 있으면 도클링을 다시 돌리지 않는다."""
    from core import parse_adapter

    cache = STORE / doc_id / "parse.json"
    if cache.exists():
        try:
            return parse_adapter.result_from_dump(
                json.loads(cache.read_text(encoding="utf-8")))
        except Exception:
            pass
    return parse_adapter.parse(_original_of(doc_id))


def _docs_in_folder(folder: str) -> list[str]:
    out = []
    for d in sorted(STORE.iterdir()) if STORE.exists() else []:
        m = d / "meta.json"
        if not m.exists():
            continue
        try:
            meta = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (meta.get("folder") or "") == folder:
            out.append(d.name)
    return out


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

@router.get("", summary="등록된 형식 목록 + 바인딩")
def formats():
    from core import router as core_router

    core_router.load.cache_clear()          # UI 등재 직후에도 목록이 새것이어야 한다
    reg = core_router.load()
    routes = []
    for r in reg.routes:
        fp = r.format_path()
        routes.append({
            "doc_type": r.doc_type, "parser": r.parser, "owner": r.owner,
            "threshold": r.threshold, "note": r.note,
            "format": r.format, "ready": bool(fp and fp.exists()),
            "glossary": r.glossary,
        })
    return {"routes": routes, "bindings": load_bindings(),
            # 원본 형식마다 파서가 싣는 신호 — 화면이 배지 툴팁에 그대로 쓴다
            "kind_signals": KIND_SIGNALS}


# ---------------------------------------------------------------------------
# 컴파일 — 올라온 문서들로 형식을 만들고 등록부에 올린다
# ---------------------------------------------------------------------------

class CompileBody(BaseModel):
    doc_type: str
    folder: Optional[str] = None            # 편의 — folders 에 합친다
    folders: list[str] = []                 # 이 폴더들의 문서 전부를 샘플로
    doc_ids: list[str] = []                 # 낱개 문서 (폴더와 합집합)
    use_llm: bool = False
    threshold: float = 0.60
    overwrite: bool = False                 # 같은 doc_type 이 있으면 갈아끼울지
    # 성공하면 연결한 폴더·문서를 이 틀에 바인딩한다. 캔버스에서 이어 놓고 실행하는
    # 손짓이 곧 "이 폴더(문서)는 이 틀을 쓴다" 이므로 기본이 켜짐이다.
    bind: bool = True

    def all_folders(self) -> list[str]:
        return list(dict.fromkeys(
            ([self.folder] if self.folder else []) + list(self.folders)))


def _slug(doc_type: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", doc_type).strip("_")
    return s or "format"


def _register_route(doc_type: str, format_rel: str, threshold: float,
                    overwrite: bool) -> None:
    """registry.yaml 에 route 를 올린다 — 등록부가 유일한 결정자라는 규약 그대로.

    파일 전체를 yaml 로 재직렬화하지 않는다 — 그러면 등록부의 **주석이 전부
    날아간다**(detect 를 왜 좁혔는지 같은 실측 기록이 주석에 산다). 대신 UI 등재분은
    경계 주석으로 감싼 블록을 파일 끝에 붙이고, 갈아끼울 때는 그 블록만 바꾼다.
    사람이 손으로 등록한 route 는 UI 가 건드리지 않는다 — 409 로 거부한다.
    """
    import yaml

    from core import router as core_router

    # 등록부의 자리는 core.router 가 안다 — 여기서 경로를 또 적으면 두 곳이 갈린다.
    reg_path = Path(core_router.DEFAULT_REGISTRY)
    text = reg_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    existing = next((r for r in data.get("routes", [])
                     if r.get("doc_type") == doc_type), None)

    begin = f"# --- ui-compiled: {doc_type} ---"
    end = f"# --- /ui-compiled: {doc_type} ---"
    if existing is not None:
        if not overwrite:
            raise HTTPException(409, f"doc_type '{doc_type}' 은 이미 등록되어 있습니다 — "
                                     f"overwrite 를 켜면 형식을 갈아끼웁니다")
        if begin not in text:
            raise HTTPException(409, f"doc_type '{doc_type}' 은 사람이 등록한 route "
                                     f"입니다 — UI 가 덮어쓰지 않습니다. "
                                     f"core/registry.yaml 을 직접 고치세요")
        text = re.sub(rf"[ \t]*{re.escape(begin)}\n(?:.*\n)*?[ \t]*{re.escape(end)}\n?",
                      "", text)

    # 기존 route 항목의 들여쓰기에 맞춘다 — 한 시퀀스의 항목은 들여쓰기가 같아야 한다
    m = re.search(r"^([ \t]*)- doc_type:", text, re.M)
    indent = m.group(1) if m else "  "
    entry = {"doc_type": doc_type, "parser": "auto", "format": format_rel,
             "threshold": threshold, "owner": "ui",
             "note": f"UI 컴파일 {datetime.now(timezone.utc).date().isoformat()}"}
    dumped = yaml.safe_dump([entry], allow_unicode=True, sort_keys=False)
    block = "".join(f"{indent}{ln}\n" for ln in
                    [begin, *dumped.rstrip("\n").splitlines(), end])
    reg_path.write_text(text.rstrip("\n") + "\n\n" + block, encoding="utf-8")

    from core import router as core_router
    core_router.load.cache_clear()


@router.post("/compile", summary="올라온 문서들로 형식 유도 → 등록부 등재")
def compile_format(body: CompileBody):
    from core import fitness_gate, format_induce, format_model, structurize
    from core.glossary import Glossary

    doc_type = body.doc_type.strip()
    if not doc_type:
        raise HTTPException(400, "doc_type 이름이 필요합니다")

    folders = body.all_folders()
    doc_ids = list(dict.fromkeys(
        [d for f in folders for d in _docs_in_folder(f)] + body.doc_ids))
    if not doc_ids:
        raise HTTPException(400, "샘플 문서가 없습니다 — 폴더나 문서를 이어 주세요")

    samples, skipped = [], []
    for did in doc_ids:
        kind = _kind_of(did)
        if kind == "lawxml":
            # 태그가 곧 구조다. 게다가 여기 있는 source.pdf 는 검수용 **합성 지면**이라
            # 그걸 파싱하면 원문이 아니라 우리가 찍은 그림을 배우게 된다.
            skipped.append({"doc_id": did, "kind": kind,
                            "reason": "법령 XML — 태그 계층을 그대로 쓰므로 틀이 필요 없습니다"})
            continue
        try:
            src = _original_of(did)
            parsed = _parsed_of(did)
        except HTTPException:
            skipped.append({"doc_id": did, "kind": kind, "reason": "원본/파싱 결과가 없습니다"})
            continue
        samples.append((did, str(src), parsed, kind))
    if len(samples) < 2:
        raise HTTPException(400, f"샘플이 {len(samples)}개뿐입니다 — 같은 유형 문서 "
                                 f"2개 이상이 필요합니다 (권장 3~5개)"
                                 + (f". 제외됨: {[s['reason'] for s in skipped]}"
                                    if skipped else ""))

    # 형식 섞임 — 막지는 않는다(같은 양식이 pdf 와 hwp 로 오는 일이 실제로 있다).
    # 다만 **무엇이 달라지는지** 말한다: 제목 신호가 없는 hwp 로는 require_heading
    # 마커가 서지 않고, pdf 만으로 유도한 형식이 hwp 에서 덜 잘릴 수 있다.
    kinds = sorted({k for *_, k in samples})
    kind_warnings: list[str] = []
    if len(kinds) > 1:
        kind_warnings.append(
            "샘플의 원본 형식이 섞였습니다 (" + ", ".join(
                f"{k}: {KIND_SIGNALS.get(k, '?')}" for k in kinds) + "). "
            "형식마다 파서가 싣는 신호가 달라, 한쪽에서만 도는 규칙이 만들어질 수 있습니다 — "
            "적용 결과의 문서별 점수를 함께 보세요")

    # 유도용 / 홀드아웃 분리 — 유도에 쓴 샘플에서 잘 도는 것은 당연하다(§2.5)
    #
    # 형식이 섞였으면 **신호가 적은 쪽을 홀드아웃으로** 민다. pdf 로 유도하고 pdf 로
    # 검증하면 hwp 에서 무너지는 형식이 그대로 통과한다 — 검증의 뜻이 없어진다.
    samples.sort(key=lambda s: s[3] in HEADING_KINDS, reverse=True)
    n_hold = len(samples) // 3 if len(samples) >= HOLDOUT_FROM else 0
    train, hold = (samples[:-n_hold], samples[-n_hold:]) if n_hold else (samples, [])

    g = Glossary(version=1, doc_type=doc_type, terms={})
    train_pairs = [(path, parsed) for _, path, parsed, _ in train]

    llm_totals = None
    if body.use_llm:
        from core.llm import LLM
        llm = LLM()
        induction = format_induce.induce(train_pairs, g, llm, doc_type)
        llm_totals = llm.totals()
    else:
        induction = format_induce.draft_without_llm(train_pairs, g, doc_type)

    fmt = induction.fmt
    if fmt is None:
        raise HTTPException(422, "형식을 만들지 못했습니다: "
                                 + "; ".join(induction.warnings[:3]))

    # 적용 미리보기 — 추상 패턴이 아니라 결과를 보여준다(§2.4-a).
    # 형식(kind)을 함께 실어 "hwp 만 점수가 낮다" 를 화면에서 읽을 수 있게 한다.
    applied = []
    for did, path, parsed, kind in samples:
        doc = structurize.run(parsed, fmt, g)
        fit = fitness_gate.apply(doc, fmt, len(parsed.elements), body.threshold)
        applied.append({"doc_id": did, "name": _doc_meta(did).get("name", Path(path).name),
                       "kind": kind,
                       "held_out": any(did == h[0] for h in hold),
                       "sections": len(doc.sections), "residual": len(doc.residual),
                       "score": round(fit.score, 3), "passed": fit.passed})

    # 제목 신호가 필요한 마커가 있는데 그 신호가 없는 형식이 섞였으면 이름을 대고 알린다.
    # 이 조합은 조용히 덜 잘리므로(마커가 안 서면 구역이 안 열린다) 반드시 말해야 한다.
    heads = [m.id for m in fmt.regex_markers if getattr(m, "require_heading", False)]
    blind = sorted({k for *_, k in samples if k not in HEADING_KINDS})
    if heads and blind:
        kind_warnings.append(
            f"마커 {heads} 는 제목 위치에서만 인정되는데, {blind} 원본에는 제목 신호가 "
            f"없습니다 — 그 문서에서는 이 마커가 발화하지 않습니다")

    holdout_failed = [a for a in applied if a["held_out"] and not a["passed"]]
    if not hold:
        fmt.confidence = "low"              # 홀드아웃 없이 확정 — 신뢰도 낮음 (§2.1)
    if holdout_failed:
        raise HTTPException(422, json.dumps({
            "error": "홀드아웃 검증 실패 — 형식을 확정하지 않았습니다",
            "failed": holdout_failed, "applied": applied}, ensure_ascii=False))

    FORMATS_DIR.mkdir(parents=True, exist_ok=True)
    out = FORMATS_DIR / f"{_slug(doc_type)}.format.json"
    format_model.save(fmt, out)
    # registry 의 format 은 저장소 루트 기준 상대경로다. 밖에 있으면(시험용 FORMATS_DIR)
    # `../..` 로 거슬러 쓰지 않고 절대경로를 적는다 — 읽는 쪽이 헷갈리지 않게.
    format_rel = (os.path.relpath(out, ROOT) if out.resolve().is_relative_to(ROOT)
                  else str(out.resolve()))
    _register_route(doc_type, format_rel, body.threshold, body.overwrite)

    bound_docs: list[str] = []
    if body.bind:
        b = load_bindings()
        for f in folders:
            b["folders"][f] = doc_type
        # 폴더째 이어진 문서는 폴더 바인딩이 이미 덮는다 — 낱개로 이은 것만 예외로 건다
        in_folders = {d for f in folders for d in _docs_in_folder(f)}
        bound_docs = [d for d in body.doc_ids if d not in in_folders]
        for d in bound_docs:
            b["docs"][d] = doc_type
        _save_bindings(b)

    return {
        "doc_type": doc_type, "format": format_rel,
        "confidence": fmt.confidence,
        "markers": [{"id": m.id, "level": m.level, "pattern": m.pattern}
                    for m in fmt.by_level()],
        "applied": applied, "skipped": skipped,
        "kinds": kinds,
        "holdout": bool(hold), "warnings": kind_warnings + induction.warnings,
        "llm": llm_totals,
        "doc_ids": doc_ids,
        "bound_folders": folders if body.bind else [],
        "bound_docs": bound_docs,
        # 하위호환 — 홈 화면이 단일 폴더 이름을 읽는다
        "bound_folder": (folders[0] if (folders and body.bind) else None),
    }


# ---------------------------------------------------------------------------
# 바인딩 — 폴더/문서 → doc_type
# ---------------------------------------------------------------------------

class BindBody(BaseModel):
    scope: str                              # "folder" | "doc"
    key: str                                # 폴더 이름 또는 doc_id
    doc_type: Optional[str] = None          # null 이면 해제


@router.get("/bindings", summary="폴더/문서 바인딩 전부")
def bindings():
    return load_bindings()


# ---------------------------------------------------------------------------
# 캔버스 — 사람이 손으로 이어 놓은 그림 (자리 + 아직 만들지 않은 틀)
# ---------------------------------------------------------------------------
# 연결 자체의 정본은 bindings 다. 여기 남는 것은 **화면의 기억**이다:
#   pos     노드를 어디에 뒀나 (없으면 화면이 자동 배치한다)
#   drafts  아직 컴파일하지 않은 틀과, 거기 이어 둔 폴더·문서
# 초안을 저장하지 않으면 새로고침 한 번에 이어 놓은 것이 다 날아간다.

class Canvas(BaseModel):
    pos: dict[str, list[float]] = {}
    drafts: list[dict] = []


@router.get("/canvas", summary="캔버스 배치 + 미완성 초안")
def canvas():
    if CANVAS_FILE.exists():
        try:
            d = json.loads(CANVAS_FILE.read_text(encoding="utf-8"))
            return {"pos": dict(d.get("pos", {})), "drafts": list(d.get("drafts", []))}
        except (OSError, json.JSONDecodeError):
            pass
    return {"pos": {}, "drafts": []}


@router.put("/canvas", summary="캔버스 배치 저장 (통째로 교체)")
def save_canvas(body: Canvas):
    CANVAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANVAS_FILE.write_text(
        json.dumps(body.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return body.model_dump()


@router.put("/bindings", summary="폴더/문서 → 형식 연결 (doc_type=null 로 해제)")
def bind(body: BindBody):
    if body.scope not in ("folder", "doc"):
        raise HTTPException(400, "scope 는 folder 또는 doc 입니다")
    if body.scope == "doc" and body.doc_type and _kind_of(body.key) == "lawxml":
        # 이으면 검수용 **합성 지면**을 원문 삼아 다시 자르게 된다 — 태그로 세운
        # 구조가 추론 결과로 바뀐다. 형식이 곧 구조인 문서라 틀을 얹지 않는다.
        raise HTTPException(400, "법령 XML 문서는 태그 계층이 곧 구조라 틀을 붙이지 "
                                 "않습니다 (붙이면 원문이 아니라 합성 지면을 자르게 됩니다)")
    if body.doc_type:
        from core import router as core_router
        core_router.load.cache_clear()
        if body.doc_type not in core_router.load().doc_types():
            raise HTTPException(404, f"doc_type '{body.doc_type}' 은 등록부에 없습니다 — "
                                     f"먼저 형식을 컴파일해 등재하세요")
    b = load_bindings()
    table = b["folders"] if body.scope == "folder" else b["docs"]
    if body.doc_type:
        table[body.key] = body.doc_type
    else:
        table.pop(body.key, None)
    _save_bindings(b)
    return b
