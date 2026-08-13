"""구조 해석기 검수 API — 해석 결과를 원본 PDF 위에 되돌려 보여 주기 위한 것.

    POST /v1/structure/documents        PDF·HWP·DOCX·법령XML 업로드 → 해석 → doc_id
                                        (HWP·DOCX 는 합성 지면(synthpdf) 위에 선다)
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


import re

# 문서 id 는 업로드가 만드는 sha256 앞 16자리뿐이다. 이 모양이 아니면 문서가
# 아니다 — 느슨하게 받으면 `custom` 같은 형제 디렉토리가 삭제 API 의 rmtree
# 반경에 들어간다(등록한 규칙 전부가 문서 하나 지우는 손짓에 날아간다).
_DOC_ID = re.compile(r"^[0-9a-f]{16}$")

# 형식 분기·해석·저장 규약은 core.ingest 가 쥔다 — 코드단 일원화(docs/LINEAGE.md).
# 업로드 API 와 CLI(ingest_lawxml.py)가 같은 문을 지나야 배치 인제스트가 이
# 라우터 없이도 같은 결과를 낸다. 아래 별칭은 라우터 안 호출부와 바깥 임포트
# (api/ops.py·formats·시험)가 쓰는 얇은 문이다.
from core import ingest as ingest_mod  # noqa: E402

_source_kind = ingest_mod.source_kind
_structured_by = ingest_mod.structured_by
_parse_cached = ingest_mod.parse_cached
_hint_kwargs = ingest_mod.hint_kwargs


def _ledger_path() -> Path:
    return ingest_mod.ledger_path(STORE)


def _interpret(pdf: Path, **kw) -> dict:
    """core.ingest.interpret_doc — 이 라우터가 쥔 스토어·틀 연결 조회만 얹는다."""
    from api.routers.formats import binding_for
    return ingest_mod.interpret_doc(pdf, store=STORE, binding_of=binding_for, **kw)


def _dir(doc_id: str) -> Path:
    """저장 경로. 경로 탈출만 막는 게 아니라 **문서 id 의 모양**을 강제한다."""
    if not doc_id or not _DOC_ID.fullmatch(doc_id):
        raise HTTPException(400, "doc_id 형식이 올바르지 않습니다")
    return STORE / doc_id


# 원본 파일 형식 — 흐름이 여기서 갈린다(아래 표는 화면·컴파일이 함께 읽는다).
#
#   pdf    지면 좌표·타이포그래피가 원본에 있다. 레이아웃 모델이 제목을 표시한다.
#   docx   좌표는 없지만(리플로우) Word 스타일의 **진짜 제목 계층**이 온다.
#   hwp    좌표도 제목 선언도 없다 — md 로 변환되어 마커(글자)만 남는다.
#   lawxml 태그 계층을 그대로 옮긴 것. 구조화 틀을 붙이지 않는다(형식이 곧 구조다).
#
# 이걸 감추면 "같은 틀인데 어떤 문서만 덜 잘린다" 가 원인 없이 나타난다 —
# 예: require_heading 마커는 제목 신호가 없는 hwp 에서 영영 발화하지 않는다.
SOURCE_KINDS = ("pdf", "hwp", "hwpx", "docx", "lawxml")


def _meta(d: Path) -> dict:
    p = d / "meta.json"
    if not p.exists():
        return {}
    m = json.loads(p.read_text(encoding="utf-8"))
    if not m.get("source_kind"):
        kind = _source_kind(d)
        if kind:
            m["source_kind"] = kind
    return m


def _expected_structured_by(doc_id: str, meta: dict) -> str:
    """지금 규칙이라면 어떤 것으로 잘려야 하나 — 저장된 것과 다르면 낡은 결과다."""
    if (meta.get("source_kind") or "") == "lawxml":
        return "lawxml"
    # 사람이 엔진을 고른 문서는 그 선택이 규칙이다 — 연결(binding)보다 세다.
    if meta.get("engine") == "docxstyle":
        return "docxstyle"
    from api.routers.formats import binding_for, format_version_of

    bound = binding_for(doc_id, meta.get("folder") or "")
    if not bound:
        return "induce"
    return f"format:{bound}@v{format_version_of(bound)}"


def _with_freshness(doc_id: str, meta: dict) -> dict:
    """meta 에 '다시 해석해야 하는가' 를 얹는다. 저장하지 않고 볼 때마다 계산한다 —
    연결은 문서 밖에서 바뀌므로 굳혀 두면 그 순간부터 거짓말이 된다."""
    want = _expected_structured_by(doc_id, meta)
    # 기록이 없는 옛 문서는 **유도(또는 태그)**로 잘린 것이다 — 형식 연결은 이 표시가
    # 생긴 뒤에야 가능해졌으므로, 없다는 것 자체가 "형식으로 자르지 않았다" 는 뜻이다.
    have = meta.get("structured_by") or (
        "lawxml" if (meta.get("source_kind") or "") == "lawxml" else "induce")
    m = dict(meta, structured_by=have, expected_structured_by=want)
    if have != want:
        m["stale"] = True
        m["stale_reason"] = f"저장된 결과는 {have} 인데 지금 규칙은 {want} 입니다"
    return m


@router.post("/documents", summary="PDF·HWP·DOCX·법령XML 업로드 → 구조 해석")
async def upload(
    file: UploadFile = File(...),
    root: Optional[str] = Form(None),
    families: Optional[str] = Form(None, description="쉼표 구분 (예: dot_number,roman)"),
    ladder: Optional[str] = Form(None, description="층마다 세미콜론, 같은 층은 쉼표"),
    order: Optional[str] = Form(None, description="'A>B' 를 쉼표로 (예: kr_장>kr_절)"),
    use_llm: bool = Form(False, description="잔여를 배치 1콜로 해소"),
    folder: Optional[str] = Form(None, description="묶어 둘 폴더 라벨 (예: 법령문서)"),
    engine: Optional[str] = Form(None, description="빈값=유도/형식 · docxstyle=Word 스타일 통짜(docx 전용)"),
):
    eng = (engine or "").strip()
    if eng not in ("", "auto", "induce", "docxstyle"):
        raise HTTPException(400, f"모르는 엔진입니다: {eng} (가능: docxstyle)")
    eng = "docxstyle" if eng == "docxstyle" else ""
    lower = (file.filename or "").lower()
    if lower.endswith(".doc"):
        raise HTTPException(400, "구형 Word(.doc)는 읽지 못합니다 — "
                                 ".docx 로 다시 저장해 올려 주세요")
    family = ingest_mod.family_of(lower)
    if family is None:
        raise HTTPException(400, "PDF·HWP(X)·DOCX 또는 법령 본문 XML 만 받습니다")
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"파일이 {MAX_MB}MB 를 넘습니다")

    # 표시 이름 — XML 은 파일명의 " 본문" 꼬리를 뗀다(law.go.kr 내려받기 규약).
    # 나머지는 파일명 그대로 — 사람이 화면에서 고친 이름은 core 가 지킨다.
    name = file.filename or "문서"
    if family == "xml":
        stem = Path(name).stem
        name = re.sub(r"\s*본문$", "", stem) or stem

    from api.routers.formats import binding_for
    try:
        r = ingest_mod.ingest(
            raw, file.filename or name, store=STORE, name=name,
            folder=(folder or "").strip(), use_llm=use_llm, engine=eng,
            hints=_hint_kwargs(root, families, ladder, order),
            binding_of=binding_for)
    except ValueError as exc:            # 위장 포맷 등 — 사용자가 고칠 수 있는 실패
        raise HTTPException(400, f"법령 본문 XML 이 아닙니다: {exc}"
                            if family == "xml" else str(exc))
    except Exception as exc:
        raise HTTPException(500, f"해석에 실패했습니다: {type(exc).__name__}: {exc}")
    return {"doc_id": r["doc_id"], **_meta(_dir(r["doc_id"]))}


@router.post("/{doc_id}/reinterpret", summary="같은 문서를 현재 규칙으로 다시 해석")
def reinterpret(doc_id: str, use_llm: bool = Form(False),
                root: Optional[str] = Form(None),
                families: Optional[str] = Form(None),
                ladder: Optional[str] = Form(None),
                order: Optional[str] = Form(None),
                engine: Optional[str] = Form(
                    None, description="없음=저장된 선택 유지 · induce=유도로 복귀 · "
                                      "docxstyle=Word 스타일 통짜(docx 전용)")):
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
    # 엔진 — 안 주면 저장된 선택 유지, 명시하면 그것으로 바꾼다(빈 문자열·induce 는 복귀)
    if engine is None:
        eng = before.get("engine") or ""
    else:
        e = engine.strip()
        if e not in ("", "auto", "induce", "docxstyle"):
            raise HTTPException(400, f"모르는 엔진입니다: {e} (가능: docxstyle)")
        eng = "docxstyle" if e == "docxstyle" else ""
    kw = _hint_kwargs(root, families, ladder, order)
    if use_llm:
        from core.llm import LLM
        kw["llm"] = LLM()
    t0 = time.monotonic()
    try:
        data = _interpret(pdf, cache=cache, doc_id=doc_id,
                          folder=before.get("folder") or "",
                          name=before.get("name") or "", engine=eng, **kw)
    except ValueError as exc:        # 엔진-형식 불일치 등 — 사용자가 고칠 수 있는 실패
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"재해석에 실패했습니다: {type(exc).__name__}: {exc}")
    took = round(time.monotonic() - t0, 1)

    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta = _meta(d)
    if eng:
        meta["engine"] = eng
    else:
        meta.pop("engine", None)     # 유도로 복귀 — 선택을 지워야 신선도 판정이 안 낡는다
    st = data.get("stats", {})
    meta.update({"score": data["fitness"]["score"], "passed": data["fitness"]["passed"],
                 "tier": data["fitness"]["tier"], "used_llm": bool(use_llm),
                 "structured_by": _structured_by(data, meta.get("source_kind") or ""),
                 "fingerprint": data.get("fingerprint", {}).get("key"),
                 "fingerprint_count": st.get("fingerprint_count"),
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
            # VLM 이 시간의 대부분을 쓴다 — 어디에 썼는지 보이게 한다
            "vlm_sec": st.get("vlm_sec"), "vlm_pages": st.get("vlm_pages"),
            "vlm_asked": st.get("vlm_asked"), "vlm_deduped": st.get("vlm_deduped"),
            "vlm_headings": st.get("vlm_headings"),
        },
    }


@router.get("/documents", summary="올라온 문서 목록")
def documents():
    STORE.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(STORE.iterdir()):
        if not d.is_dir():
            continue
        m = _meta(d)
        if not m:
            continue
        # 파싱 캐시 유무 — 없으면 다시 해석이 docling 재파싱이라 **분 단위**다.
        # 화면이 그 사실을 미리 말해 줄 수 있어야 한다(§9 예열).
        # 법령 XML 은 애초에 파싱을 하지 않는다(태그 직행) — 예열이라는 개념이 없으므로
        # 캐시 없음을 흠으로 보이면 안 된다.
        m["parse_cached"] = (m.get("source_kind") == "lawxml"
                             or (d / "parse.json").exists())
        out.append(_with_freshness(d.name, m))
    return {"documents": sorted(out, key=lambda m: m.get("at", ""), reverse=True)}


# ---------------------------------------------------------------------------
# 폴더 — 문서를 묶는 라벨. 라벨만으로는 **빈 폴더**가 존재할 수 없어서
# (폴더 = 문서 meta 의 folder 값의 합집합) 등록부 파일 하나를 곁에 둔다.
# "폴더를 먼저 만들고 문서를 넣는" 손짓이 되려면 빈 폴더가 서야 한다.
# ---------------------------------------------------------------------------

class Folder(BaseModel):
    name: str


def _folders_file() -> Path:
    return STORE / "folders.json"          # 문서 스토어와 함께 이동·백업된다


def _load_folder_names() -> list[str]:
    p = _folders_file()
    if not p.exists():
        return []
    try:
        return [str(x) for x in json.loads(p.read_text(encoding="utf-8")).get("folders", [])]
    except Exception:
        return []


def _save_folder_names(names) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    _folders_file().write_text(json.dumps({"folders": sorted(set(names))},
                                          ensure_ascii=False, indent=1), encoding="utf-8")


def _register_folder(name: str) -> None:
    """라벨을 쓰는 모든 경로(업로드·PATCH)가 부른다 — 문서가 다 빠져나가도
    폴더가 사라지지 않아야 '만들어 둔 폴더'로 느껴진다. 구현은 core.ingest 에
    하나만 있다 — 인제스트 경로(xml 포함)와 같은 등록부를 써야 해서다."""
    ingest_mod.register_folder(STORE, name)


def _folder_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(400, "폴더 이름이 비었습니다")
    if len(name) > 80:
        raise HTTPException(400, "폴더 이름이 너무 깁니다 (80자 이내)")
    return name


@router.get("/folders", summary="폴더 목록 — 빈 폴더 포함")
def folders():
    STORE.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for d in STORE.iterdir():
        if d.is_dir():
            f = _meta(d).get("folder")
            if f:
                counts[f] = counts.get(f, 0) + 1
    names = sorted(set(_load_folder_names()) | set(counts))
    return {"folders": [{"name": n, "docs": counts.get(n, 0)} for n in names]}


@router.post("/folders", summary="폴더 만들기 — 비어 있어도 남는다")
def add_folder(body: Folder):
    name = _folder_name(body.name)
    _register_folder(name)
    return {"created": name}


@router.patch("/folders/{name}", summary="폴더 이름 변경 — 든 문서 전부의 라벨을 바꾼다")
def rename_folder(name: str, body: Folder):
    new = _folder_name(body.name)
    moved = 0
    if new != name and STORE.exists():
        for d in STORE.iterdir():
            if not d.is_dir():
                continue
            meta = _meta(d)
            if meta.get("folder") == name:
                meta["folder"] = new
                (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                             encoding="utf-8")
                moved += 1
    _save_folder_names([n for n in _load_folder_names() if n != name] + [new])
    # 구조화 틀 연결은 폴더 **이름**으로 걸린다 — 따라가지 않으면 조용히 끊긴다.
    from api.routers.formats import rename_folder_binding

    rename_folder_binding(name, new)
    return {"renamed": name, "to": new, "docs": moved}


@router.delete("/folders/{name}", summary="폴더 삭제 — 문서는 지우지 않고 미분류로")
def remove_folder(name: str):
    unfiled = 0
    if STORE.exists():
        for d in STORE.iterdir():
            if not d.is_dir():
                continue
            meta = _meta(d)
            if meta.get("folder") == name:
                meta.pop("folder", None)
                (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                             encoding="utf-8")
                unfiled += 1
    _save_folder_names([n for n in _load_folder_names() if n != name])
    # 연결도 지운다 — 남기면 같은 이름으로 폴더를 다시 만들 때 죽은 줄 알았던 틀이
    # 되살아난다(사람은 새 폴더를 만들었다고 생각하는데 옛 규칙이 적용된다).
    from api.routers.formats import forget_folder

    forget_folder(name)
    return {"deleted": name, "docs_unfiled": unfiled}


@router.get("/ledger", summary="fingerprint 원장 — 문서군별 관측·동결 현황")
def ledger_status():
    """어떤 문서군(fingerprint)이 몇 번 재현됐고 어떤 frame 이 동결됐는지.
    /{doc_id} 보다 먼저 등록되어야 한다 — 'ledger' 는 문서 id 가 아니다."""
    from core.structure import fingerprint as fp_mod

    led = fp_mod.Ledger.load(_ledger_path())
    names = {}
    if STORE.exists():
        for d in STORE.iterdir():
            if d.is_dir():
                m = _meta(d)
                if m.get("doc_id"):
                    names[m["doc_id"]] = m.get("name", d.name)
    rows = []
    for key, count in sorted(led.counts.items(), key=lambda kv: -kv[1]):
        rows.append({"key": key, "count": count,
                     "docs": [{"doc_id": x, "name": names.get(x, x)}
                              for x in led.docs.get(key, [])],
                     "frozen": key in led.frames,
                     "freeze_at": fp_mod.FREEZE_AT})
    return {"fingerprints": rows, "frames": len(led.frames),
            "store": str(_ledger_path())}


@router.get("/{doc_id}", summary="검수 payload (트리 + 블록 + 좌표)")
def result(doc_id: str):
    p = _dir(doc_id) / "result.json"
    if not p.exists():
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    data = json.loads(p.read_text(encoding="utf-8"))
    # 계층 사후 교정을 겹쳐 읽는다 — RAG 색인과 같은 트리를 봐야 검수가 된다
    from core import structure_fixes
    data["nodes"] = structure_fixes.apply(doc_id, data.get("nodes", []))
    return data


# --------------------------------------------------- 규칙 시험 (제안 → 전후 비교)
# custom 규칙은 **문서를 안 가린다** — 하나를 등록하면 코퍼스의 해석이 함께
# 바뀐다. 그래서 시험은 한 문서 점수가 아니라 **영향받는 문서 전부**의 점수로
# 본다. 영향 범위는 정확히 "PDF 추론 경로로 해석된 문서"다:
#
#   parse.json 있음   docling 이 파싱한 문서 — 제안자·DP 가 계층을 만든다.
#                     custom 규칙이 여기에 든다. 재해석은 캐시라 몇 초.
#   parse.json 없음   lawxml·XML 인제스트 문서 — 계층이 원천 태그에서 왔다.
#                     제안자가 안 돌아 규칙과 무관하고, **재해석하면 합성 PDF 를
#                     docling 이 다시 추론해 원천 태그 구조가 사라진다.**
#                     그래서 이 갈래는 절대 재해석하지 않는다(데이터 파괴).
def _rule_scope() -> list[str]:
    """규칙 시험이 다시 해석해도 되는 문서 — 파싱 캐시가 있는 것만.

    docxstyle 엔진으로 고정한 문서도 뺀다 — 제안자가 안 돌아 규칙과 무관하고,
    유도로 재해석하면 사람이 고른 엔진 선택을 짓밟는다.
    """
    root = STORE
    if not root.exists():
        return []
    return [d.name for d in sorted(root.iterdir())
            if (d / "parse.json").exists() and (d / "source.pdf").exists()
            and _meta(d).get("engine") != "docxstyle"]


def _reinterpret_doc(doc_id: str) -> dict:
    """캐시 기반 재해석 하나 — 점수만 돌려준다. 실패는 삼키지 않는다."""
    d = _dir(doc_id)
    before = _meta(d)
    data = _interpret(d / "source.pdf", cache=d / "parse.json", doc_id=doc_id,
                      folder=before.get("folder") or "", name=before.get("name") or "",
                      engine=before.get("engine") or "")
    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False),
                                   encoding="utf-8")
    meta = _meta(d)
    meta.update({"score": data["fitness"]["score"], "passed": data["fitness"]["passed"],
                 "tier": data["fitness"]["tier"],
                 "structured_by": _structured_by(data, meta.get("source_kind") or ""),
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, "name": meta.get("name", doc_id),
            "before": before.get("score"), "after": data["fitness"]["score"],
            "tier": data["fitness"]["tier"],
            "nodes": len(data.get("nodes", []))}


RULE_SYSTEM = (
    "너는 문서 구조 해석기의 **표면 어휘** 설계자다. 계층이 잘못 잡힌 블록들을 "
    "받는다. 그 블록들의 머리에 있는 **표면 패턴**(번호·기호 표기)을 정규표현식 "
    "규칙 하나로 적어라. 해석기는 이 패턴으로 그 줄이 '번호가 붙은 항목'임을 "
    "알아보고, 계층은 문서가 스스로 유도한다.\n"
    "지켜야 할 것:\n"
    "  · pattern 은 반드시 ^ 로 시작한다 — 앵커가 없으면 문장 한복판의 인용까지 "
    "삼킨다.\n"
    "  · **표면만** 담는다. level·rank·parent 를 넣지 마라 — 계층은 어휘의 몫이 "
    "아니다.\n"
    "  · 서수가 되는 숫자·글자는 캡처 그룹으로 잡고 그 이름을 groups 와 "
    "ordinal_from 에 적는다(보통 이름 하나: no).\n"
    "  · 이미 흔한 표기(1. · 가. · ① · 1) · (1))는 해석기가 이미 안다. **새 표기**만 "
    "적어라. 새 표기가 없으면 pattern 을 빈 문자열로 두고 why 에 이유를 적는다.\n"
    '반드시 이 JSON 만: {"id","family","surface","pattern","groups":[…],'
    '"ordinal_from":[…],"why"}'
)

RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "family": {"type": "string"},
        "surface": {"type": "string"},
        "pattern": {"type": "string"},
        "groups": {"type": "array", "items": {"type": "string"}},
        "ordinal_from": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
    },
    "required": ["id", "family", "surface", "pattern", "groups",
                 "ordinal_from", "why"],
    "additionalProperties": False,
}


class RuleTry(BaseModel):
    """오파싱 구역을 지목해 규칙을 제안·시험한다 — blocks 는 그 자리의 블록 idx."""
    blocks: list[int]
    note: str = ""


@router.post("/{doc_id}/rules/try", summary="LLM 규칙 제안 → 등록 → 코퍼스 전후 비교",
             tags=["rules"])
def rules_try(doc_id: str, body: RuleTry):
    """제안한 규칙을 **실제로 등록하고** 영향 범위를 다시 해석해 전후를 잰다.
    되돌릴 수 있어야 시험이므로 rule_id 를 함께 낸다 — /rules/decide 가 받는다.
    lawxml 문서는 범위 밖이다(재해석이 원천 태그를 파괴한다)."""
    import yaml

    from core.llm import LLM
    from core.structure.proposers import custom

    d = _dir(doc_id)
    p = d / "result.json"
    if not p.exists():
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    if not (d / "parse.json").exists():
        raise HTTPException(400, "이 문서는 XML 인제스트 산출이라 표면 규칙이 "
                                 "닿지 않습니다 — 계층 교정으로 고치세요")
    data = json.loads(p.read_text(encoding="utf-8"))
    by_idx = {b.get("idx"): b for b in data.get("blocks", [])}
    owner = {}
    for n in data.get("nodes", []):
        s = n.get("span") or [0, 0]
        for b in range(s[0], max(s[1], s[0] + 1)):
            cur = owner.get(b)
            if cur is None or n.get("level", 0) > cur.get("level", 0):
                owner[b] = n
    view = []
    for i in body.blocks[:40]:
        b = by_idx.get(i)
        if b is None:
            continue
        n = owner.get(i) or {}
        view.append({"idx": i, "본문": (b.get("text") or "")[:200],
                     "지금_층": n.get("level"), "지금_표면": n.get("surface")})
    if not view:
        raise HTTPException(400, "지목한 블록을 찾지 못했습니다")

    out = LLM().structured(
        "structure.rule", RULE_SYSTEM,
        json.dumps({"블록들": view, "메모": body.note}, ensure_ascii=False),
        RULE_SCHEMA, max_tokens=1200, effort="low")
    if out is None:
        raise HTTPException(502, "규칙 제안에 실패했습니다 (LLM 응답 없음)")
    if not (out.get("pattern") or "").strip():
        return {"proposed": False, "why": out.get("why", ""),
                "note": "새 표면 표기가 없다는 판단입니다 — 계층 교정으로 고치세요"}
    try:
        rule = custom.validate(out)
    except custom.RuleError as exc:
        # 한 번은 스스로 고치게 한다 — 무엇을 어겼는지 그대로 돌려준다.
        # 실측에서 가장 흔한 실패가 "groups 는 1개인데 캡처 그룹이 0개" 였다.
        fixed = LLM().structured(
            "structure.rule", RULE_SYSTEM,
            json.dumps({"블록들": view, "메모": body.note,
                        "직전_제안": out,
                        "규약_위반": str(exc),
                        "지시": "위반을 고쳐 같은 형식으로 다시 답하라. "
                                "groups 에 적은 이름 수와 패턴의 캡처 그룹 수는 같아야 한다."},
                       ensure_ascii=False),
            RULE_SCHEMA, max_tokens=1200, effort="low")
        try:
            if fixed is None:
                raise custom.RuleError(str(exc))
            rule = custom.validate(fixed)
        except custom.RuleError as exc2:
            # 여기서 끝내면 막다른 길이다 — 제안 자체를 돌려줘 손으로 고칠 수 있게 한다.
            raise HTTPException(422, detail={
                "message": f"제안된 규칙이 규약을 어깁니다: {exc2}",
                "proposal": fixed or out,
                "how": "패턴을 손보아 '내가 등록한 패턴' 으로 직접 등록할 수 있습니다"})

    scope = _rule_scope()
    before = {s: _meta(_dir(s)).get("score") for s in scope}
    rule_path = Path(custom.DEFAULT_DIR) / f"{rule['id']}.yaml"
    if rule_path.exists():
        raise HTTPException(409, f"같은 id 의 규칙이 이미 있습니다: {rule['id']}")
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(yaml.safe_dump(rule, allow_unicode=True, sort_keys=False),
                         encoding="utf-8")
    try:
        rows = [_reinterpret_doc(s) for s in scope]
    except Exception as exc:                       # 시험이 깨지면 규칙을 남기지 않는다
        rule_path.unlink(missing_ok=True)
        for s in scope:
            try:
                _reinterpret_doc(s)
            except Exception:
                pass
        raise HTTPException(500, f"시험 재해석에 실패해 규칙을 되돌렸습니다: {exc}")

    worse = [r for r in rows if (r["after"] or 0) < (before.get(r["doc_id"]) or 0)]
    better = [r for r in rows if (r["after"] or 0) > (before.get(r["doc_id"]) or 0)]
    return {"proposed": True, "rule": rule, "rule_id": rule["id"],
            "why": out.get("why", ""),
            "scope": rows, "better": len(better), "worse": len(worse),
            "skipped": [s for s in _all_doc_ids() if s not in scope],
            "verdict": ("좋아졌습니다" if better and not worse
                        else "나빠진 문서가 있습니다" if worse
                        else "점수 변화 없음 — 계층만 바뀌었는지 확인하세요"),
            "next": "유지하려면 /rules/decide 에 유지, 되돌리려면 롤백을 보내세요"}


def _all_doc_ids() -> list[str]:
    root = STORE
    return [d.name for d in sorted(root.iterdir())
            if (d / "result.json").exists()] if root.exists() else []


class RuleDecide(BaseModel):
    rule_id: str
    action: str                        # "유지" | "롤백"


@router.post("/rules/decide", summary="시험한 규칙을 유지하거나 롤백", tags=["rules"])
def rules_decide(body: RuleDecide):
    """롤백은 규칙 파일을 지우고 범위를 다시 해석해 **원래 산출로 되돌린다**
    (파싱 캐시가 있어 결정론적으로 같은 결과가 나온다)."""
    from core.structure.proposers import custom

    if body.action not in ("유지", "롤백"):
        raise HTTPException(400, "action 은 '유지' 또는 '롤백'이어야 합니다")
    p = Path(custom.DEFAULT_DIR) / f"{body.rule_id}.yaml"
    if body.action == "유지":
        if not p.exists():
            raise HTTPException(404, f"규칙이 없습니다: {body.rule_id}")
        return {"kept": body.rule_id}
    if p.exists():
        p.unlink()
    rows = [_reinterpret_doc(s) for s in _rule_scope()]
    return {"rolled_back": body.rule_id, "scope": rows}


# ------------------------------------------------------------ 계층 사후 교정
class HierarchyFix(BaseModel):
    """마디 하나를 다른 부모 밑으로 — 화면의 들여쓰기/내어쓰기가 그대로 보낸다.
    parent=null 이면 뿌리로 올린다. level 은 서버가 부모에서 다시 센다."""
    node: int
    parent: Optional[int] = None
    note: str = ""


def _nodes_of(doc_id: str) -> list[dict]:
    p = _dir(doc_id) / "result.json"
    if not p.exists():
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    return json.loads(p.read_text(encoding="utf-8")).get("nodes", [])


@router.get("/{doc_id}/hierarchy", summary="이 문서의 계층 교정 목록", tags=["rules"])
def hierarchy_list(doc_id: str):
    from core import structure_fixes
    return {"doc_id": doc_id, "fixes": list(structure_fixes.for_doc(doc_id).values())}


@router.post("/{doc_id}/hierarchy/fix", summary="마디의 부모를 옮긴다", tags=["rules"])
def hierarchy_fix(doc_id: str, body: HierarchyFix):
    """재해석해도 살아남는 좌표 수정이다(result.json 은 안 건드린다).
    고리를 만드는 이동은 거부한다 — 트리가 아니게 된다."""
    from core import structure_fixes

    raw = _nodes_of(doc_id)
    by_id = {n.get("id"): n for n in raw}
    if body.node not in by_id:
        raise HTTPException(400, f"마디가 없습니다: {body.node}")
    if body.parent is not None and body.parent not in by_id:
        raise HTTPException(400, f"부모 마디가 없습니다: {body.parent}")
    cur = structure_fixes.apply(doc_id, raw)          # 지금 보이는 트리 기준으로 검사
    by_parent = {n.get("id"): n.get("parent") for n in cur}
    if structure_fixes._would_cycle(by_parent, body.node, body.parent):
        raise HTTPException(400, "그 자리로 옮기면 계층에 고리가 생깁니다")
    before = {"parent": by_parent.get(body.node)}
    structure_fixes.record(doc_id, body.node, body.parent, before, body.note)
    fixed = {n.get("id"): n for n in structure_fixes.apply(doc_id, raw)}
    n = fixed.get(body.node) or {}
    return {"saved": True, "node": body.node, "parent": body.parent,
            "level": n.get("level"), "before": before}


HFIX_SYSTEM = (
    "너는 문서 구조 검수자다. 한 구역의 **계층 트리**(마디마다 id·부모·층·라벨·"
    "본문 첫머리)를 받는다. 사람이 원문을 읽으면 명백한데 기계가 틀리게 붙인 "
    "마디를 찾아, 그 마디의 **부모를 어디로 옮겨야 하는지** 답한다.\n"
    "판단 근거는 **본문의 뜻과 번호 흐름**이다:\n"
    "  · 번호가 이어지는 항목들(6) 7) 8)…)은 같은 부모 밑에 나란히 있어야 한다. "
    "중간에 다른 계열(가. 나. 다.)이 끼어들어 끊겼다면 그게 어긋난 자리다.\n"
    "  · 앞 항목의 내용을 이어받아 세부를 말하는 항목은 그 앞 항목의 자식이다.\n"
    "  · 다단 조판·페이지 넘김으로 읽기 순서가 엉킨 경우가 흔하다 — 순서가 아니라 "
    "**번호와 뜻**으로 판단하라.\n"
    "  · 확실한 것만 적어라. 애매하면 비운다. 고칠 게 없으면 fixes 를 빈 배열로.\n"
    "  · parent 는 받은 목록 안의 id 이거나, 이 구역 자신의 id 여야 한다.\n"
    '반드시 이 JSON 만: {"fixes":[{"node":<id>,"parent":<id>,"why":"한 줄 근거"}]}'
)

HFIX_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "node": {"type": "integer"},
                "parent": {"type": "integer"},
                "why": {"type": "string"},
            },
            "required": ["node", "parent", "why"],
            "additionalProperties": False}},
    },
    "required": ["fixes"],
    "additionalProperties": False,
}


class HierarchySuggest(BaseModel):
    """이 구역의 계층을 LLM 이 훑어 교정 후보를 낸다. 적용은 사람이 한다."""
    node: int
    depth: int = 3                     # 훑을 자손 깊이
    limit: int = 60                    # 한 번에 보는 마디 수 — 프롬프트 폭주 방지


@router.post("/{doc_id}/hierarchy/suggest",
             summary="LLM 계층 교정 제안 — 적용은 사람이 (제안자/검증자 분리)",
             tags=["rules"])
def hierarchy_suggest(doc_id: str, body: HierarchySuggest):
    """제안만 낸다 — **아무것도 바꾸지 않는다**. 화면이 후보를 보여 주고,
    사람이 고른 것만 /hierarchy/fix 로 적용한다(한 건씩 되돌릴 수 있다).

    규칙 시험과 달리 파급이 없다: 교정은 이 문서의 이 마디 좌표뿐이라
    코퍼스를 다시 해석할 일도, lawxml 을 건드릴 일도 없다 — XML 인제스트
    문서에서도 그대로 쓸 수 있는 이유다."""
    from core import structure_fixes
    from core.llm import LLM

    raw = _nodes_of(doc_id)
    nodes = structure_fixes.apply(doc_id, raw)        # 지금 보이는 트리로 묻는다
    by_id = {n.get("id"): n for n in nodes}
    if body.node not in by_id:
        raise HTTPException(400, f"마디가 없습니다: {body.node}")
    blocks = {b.get("idx"): b for b in
              json.loads((_dir(doc_id) / "result.json").read_text(encoding="utf-8"))
              .get("blocks", [])}
    kids: dict = {}
    for n in nodes:
        kids.setdefault(n.get("parent"), []).append(n)

    view: list[dict] = []
    frontier = [(body.node, 0)]
    while frontier and len(view) < body.limit:
        nid, d = frontier.pop(0)
        for k in kids.get(nid, []):
            if len(view) >= body.limit:
                break
            b = blocks.get((k.get("span") or [0, 0])[0]) or {}
            view.append({"id": k.get("id"), "부모": k.get("parent"),
                         "층": k.get("level"),
                         "라벨": (k.get("surface") or k.get("title") or "").strip(),
                         "본문": (b.get("text") or "")[:120]})
            if d + 1 < body.depth:
                frontier.append((k.get("id"), d + 1))
    if not view:
        return {"fixes": [], "note": "자손이 없어 볼 계층이 없습니다"}

    out = LLM().structured(
        "structure.hierarchy", HFIX_SYSTEM,
        json.dumps({"구역": {"id": body.node,
                             "경로": " ▸ ".join(
                                 filter(None, [(by_id[body.node].get("surface") or
                                                by_id[body.node].get("title") or "")]))},
                    "마디들": view}, ensure_ascii=False),
        HFIX_SCHEMA, max_tokens=2000, effort="low")
    if out is None:
        raise HTTPException(502, "계층 제안에 실패했습니다 (LLM 응답 없음)")

    seen_ids = {v["id"] for v in view}
    by_parent = {n.get("id"): n.get("parent") for n in nodes}
    fixes = []
    for f in out.get("fixes", []):
        nid, par = f.get("node"), f.get("parent")
        # 닫힌 후보 — 훑어 보여 준 마디 밖은 받지 않는다. 좌표는 코드가 검증한다.
        if nid not in seen_ids or (par not in seen_ids and par != body.node):
            continue
        if nid == par or by_parent.get(nid) == par:
            continue                              # 제자리 — 고칠 게 없다
        if structure_fixes._would_cycle(by_parent, nid, par):
            continue
        cur, new = by_id.get(nid) or {}, by_id.get(par) or {}
        fixes.append({
            "node": nid, "parent": par, "why": (f.get("why") or "")[:200],
            "label": (cur.get("surface") or cur.get("title") or "").strip(),
            "now_parent": by_parent.get(nid),
            "now_parent_label": ((by_id.get(by_parent.get(nid)) or {}).get("surface")
                                 or "").strip(),
            "parent_label": (new.get("surface") or new.get("title") or "").strip(),
        })
    return {"doc_id": doc_id, "node": body.node, "scanned": len(view),
            "fixes": fixes,
            "note": "제안일 뿐 아무것도 바뀌지 않았습니다 — 적용은 /hierarchy/fix"}


@router.delete("/{doc_id}/hierarchy/fix/{node}", summary="계층 교정 되돌리기", tags=["rules"])
def hierarchy_unfix(doc_id: str, node: int):
    from core import structure_fixes
    n = structure_fixes.remove(doc_id, node)
    if not n:
        raise HTTPException(404, "그 마디의 교정이 없습니다")
    return {"removed": n}


@router.post("/{doc_id}/parse", summary="파싱 캐시 만들기 — docling 을 미리 돌려 캐시를 만든다")
def warm_parse(doc_id: str):
    """다시 해석이 **분 단위**가 되는 유일한 원인(파싱 캐시 없음)을 미리 없앤다.

    옛 문서에는 `parse.json` 이 없어 재해석이 docling 을 다시 돌린다(실측 48초).
    연결을 바꾸고 여러 문서를 한꺼번에 다시 해석할 때 그 비용이 한 번에 몰리는데,
    화면이 이 갈래로 **하나씩 진행률을 보이며** 예열하면 어디서 오래 걸리는지 보인다.
    이미 캐시가 있으면 아무 일도 하지 않는다(멱등).
    """
    import time

    d = _dir(doc_id)
    pdf = d / "source.pdf"
    if not pdf.exists():
        raise HTTPException(404, f"문서를 찾을 수 없습니다: {doc_id}")
    cache = d / "parse.json"
    if cache.exists():
        return {"doc_id": doc_id, "cached": True, "took_sec": 0.0}
    t0 = time.monotonic()
    try:
        parsed = _parse_cached(pdf, cache)
    except Exception as exc:
        raise HTTPException(500, f"파싱에 실패했습니다: {type(exc).__name__}: {exc}")
    return {"doc_id": doc_id, "cached": False,
            "took_sec": round(time.monotonic() - t0, 1),
            "elements": len(parsed.elements)}


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
    # 이 문서에 걸린 예외 연결과 캔버스 자리도 함께 지운다 — 남기면 죽은 id 가 표에
    # 남고, 같은 파일을 다시 올리면(같은 sha → 같은 doc_id) 옛 연결이 되살아난다.
    from api.routers.formats import forget_doc

    forget_doc(doc_id)
    return {"deleted": doc_id}


class Patch(BaseModel):
    name: Optional[str] = None
    folder: Optional[str] = None


@router.patch("/{doc_id}", summary="문서 이름·폴더 변경")
def patch_doc(doc_id: str, body: Patch):
    """표시 이름과 폴더만 바꾼다 — 내용 해시(doc_id)와 해석 결과는 그대로다.

    이름·폴더의 정본은 meta.json 하나다. 용어집·참조 화면·RAG 색인이 전부
    여기서 읽으므로(색인은 mtime 로 스스로 새로 선다) 다른 파일은 손대지 않는다.
    폴더는 **라벨**이다 — 디스크의 파일은 움직이지 않는다. 옮기다 깨질 것이
    없고, 폴더를 지워도 문서는 남는다. 빈 문자열이면 폴더에서 뺀다.
    """
    if body.name is None and body.folder is None:
        raise HTTPException(400, "바꿀 것이 없습니다 — name 이나 folder 를 주세요")
    d = _dir(doc_id)
    meta = _meta(d)
    if not meta:
        raise HTTPException(404, f"'{doc_id}' 를 찾을 수 없습니다")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "이름이 비었습니다")
        if len(name) > 200:
            raise HTTPException(400, "이름이 너무 깁니다 (200자 이내)")
        meta["name"] = name
    if body.folder is not None:
        folder = body.folder.strip()
        if len(folder) > 80:
            raise HTTPException(400, "폴더 이름이 너무 깁니다 (80자 이내)")
        if folder:
            meta["folder"] = folder
            _register_folder(folder)
        else:
            meta.pop("folder", None)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, **meta}
