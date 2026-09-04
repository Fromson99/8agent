"""문서 인제스트 — 모든 형식이 이 한 문으로 들어와 구조화 스토어에 닿는다.

경로 선언(lawrag/core/lineage.py ROUTES)이 계보 원장이 보는 "무엇이 요구되나"라면,
여기는 그 실행부 — "실제로 어떻게 가나"다. 형식 계열마다 핸들러 하나:

    xml    lawxml 결정적 이관 — data/corpus/law 수집분이면 별표 md 자동 연결
    pdf    원본이 곧 지면 — 유도(S0~S6) 또는 형식 바인딩 해석
    hwp    parse_adapter + 합성 지면(synthpdf) → pdf 와 같은 해석
    docx   hwp 와 같은 길 + docxstyle 엔진(Word 스타일 통짜) 선택 가능

업로드 API(lawrag/api/routers/structure.py)와 CLI(lawrag/pipeline/ingest_lawxml.py)가 전부 이 모듈을
부른다 — 형식 분기가 HTTP 핸들러에 박혀 있으면 배치(코퍼스 일괄 인제스트)가
같은 길을 탈 수 없어서다. 새 형식이 오면 lineage.ROUTES 에 선언 한 줄 +
여기 핸들러 하나가 전부다. 규약 테스트가 두 어휘의 일치를 지킨다.

경로(store)는 인자로 받는다 — env 해석은 호출부가 한 번만 한다. 형식
바인딩(틀 연결)은 api 가 소유하는 저장소라 조회 함수(binding_of)로 주입받는다
— core 가 api 를 임포트하는 역방향을 만들지 않기 위해서다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent.parent

# 확장자 → 계열. 계열 어휘는 lineage.ROUTES(경로 선언)와 같아야 한다 —
# tests/core/test_ingest.py 의 규약 테스트가 어긋남을 잡는다.
EXT_FAMILY = {".xml": "xml", ".pdf": "pdf", ".hwp": "hwp", ".hwpx": "hwp",
              ".docx": "docx", ".html": "html"}


def family_of(filename: str) -> Optional[str]:
    """파일 이름 → 형식 계열. 모르는 확장자는 None — 조용히 아는 척하지 않는다."""
    return EXT_FAMILY.get(Path((filename or "").lower()).suffix)


# ---------------------------------------------------------------- 공용 저장 규약


def register_folder(store: Path, name: str) -> None:
    """폴더 등록부(store/folders.json) — 라벨을 쓰는 모든 경로가 부른다.
    문서가 다 빠져나가도 폴더가 사라지지 않아야 '만들어 둔 폴더'로 느껴진다."""
    if not name:
        return
    p = store / "folders.json"
    try:
        names = [str(x) for x in
                 json.loads(p.read_text(encoding="utf-8")).get("folders", [])]
    except Exception:
        names = []
    if name not in names:
        store.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"folders": sorted({*names, name})},
                                ensure_ascii=False, indent=1), encoding="utf-8")


def source_kind(d: Path) -> str:
    """이 문서가 어떤 원본에서 왔나. meta 에 없으면 남아 있는 원본 파일로 되짚는다
    (형식을 적기 전에 올라온 문서도 화면에서 갈려 보이게)."""
    for ext in ("xml", "hwpx", "hwp", "docx"):
        if (d / f"source.{ext}").exists():
            return "lawxml" if ext == "xml" else ext
    return "pdf" if (d / "source.pdf").exists() else ""


# 저장된 결과가 **무엇으로 잘렸는지** — 연결이 바뀌었는지 알려면 이게 있어야 한다.
#   induce            유도(S0~S6)
#   lawxml            태그 계층
#   docxstyle         Word 스타일 통짜 신뢰 (사람이 엔진으로 고른 문서만)
#   format:<유형>@v<n> 형식 파일 (버전까지 — 틀을 다시 컴파일하면 결과가 낡는다)
def structured_by(data: dict, kind: str) -> str:
    if kind == "lawxml":
        return "lawxml"
    if data.get("engine") == "docxstyle":
        return "docxstyle"
    bound = data.get("bound_doc_type")
    if not bound:
        return "induce"
    return f"format:{bound}@v{data.get('format_version', 1)}"


def ledger_path(store: Path) -> Path:
    """fingerprint 원장 — glossary.json 과 같은 자리 규약(문서 스토어 옆).
    이 파일이 없으면 관측이 늘 1회라 tier 가 warm 에 고정된다 — 재현빈도 기반
    frame 동결(§7)은 관측이 프로세스를 넘어 쌓여야 성립한다."""
    return Path(os.environ.get("STRUCTURE_LEDGER", store.parent / "structure_ledger.json"))


# -------------------------------------------------------------------- 해석 공용


def parse_cached(pdf: Path, cache: Path):
    """파싱은 **한 번만** 한다. 비싼 것은 docling 모델 추론이고 해석(S0~S5)은 싸다.

    규칙을 고치고 다시 해석할 때마다 몇 분씩 기다리게 하지 않으려고 가른다.
    캐시가 깨졌으면 조용히 다시 파싱한다 — 낡은 형식 때문에 문서를 못 열면 안 된다.
    """
    from lawrag.core import parse_adapter, typography

    if cache.exists():
        try:
            parsed = parse_adapter.result_from_dump(json.loads(cache.read_text("utf-8")))
            # 캐시가 굳은 뒤에 생긴 축을 채운다 — 들여쓰기 증거가 보는 '글자가
            # 실제로 시작하는 x'. 없으면 선행 공백으로 들여쓴 층을 구별 못 한다.
            typography.ensure_text_x(pdf, parsed.elements)
            return parsed
        except Exception:
            pass
    parsed = parse_adapter.parse(pdf)
    cache.write_text(json.dumps(parse_adapter.result_to_dump(parsed), ensure_ascii=False),
                     encoding="utf-8")
    return parsed


def hint_kwargs(root, families, ladder, order) -> dict:
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


def _interpret_with_format(parsed, pdf: Path, name: str, doc_type: str) -> dict:
    """바인딩된 문서 — 유도(S0~S6) 대신 **형식 마커의 결정론 구조화**로 해석한다.

    유도 경로와 같은 판정(structurize + fitness 게이트)을 쓰고, 화면 payload 로는
    from_format 이 모양을 옮긴다. 유형이 틀렸으면 게이트 점수가 낮게 나온다 —
    그것이 "미리 만든 틀에 맞냐 틀리냐"의 답이다.
    """
    from lawrag.core import fitness_gate, structurize
    from lawrag.core import router as core_router
    from lawrag.core.structure import from_format, viewer

    core_router.load.cache_clear()          # UI 등재 직후의 형식도 보여야 한다
    r = core_router.load().get(doc_type)
    g, fmt = core_router.assets(r)
    doc = structurize.run(parsed, fmt, g)
    fit = fitness_gate.apply(doc, fmt, len(parsed.elements), r.threshold)
    result, blocks = from_format.result_from_document(parsed, doc, fit,
                                                      doc_type=doc_type)
    data = viewer.payload(result, blocks, pdf_path=pdf, elements=parsed.elements,
                          images=parsed.images)
    if name:
        data["doc"] = name
    data["parser_warnings"] = parsed.warnings
    data["parser"] = parsed.parser
    data["bound_doc_type"] = doc_type
    # 형식 버전 — 틀을 다시 컴파일하면 이 값이 올라가고, 저장된 결과는 낡은 것이 된다
    data["format_version"] = fmt.format_version
    return data


def interpret_doc(pdf: Path, *, store: Path, cache: Optional[Path] = None,
                  doc_id: str = "", name: str = "", folder: str = "",
                  engine: str = "",
                  binding_of: Optional[Callable[[str, str], Optional[str]]] = None,
                  **kw) -> dict:
    """지면 있는 문서(pdf·합성 pdf)의 해석 — 업로드·재해석·규칙 시험이 공유한다."""
    from lawrag.core.structure import fingerprint as fp_mod
    from lawrag.core.structure import pipeline, viewer
    from lawrag.core.structure.model import Block

    parsed = parse_cached(pdf, cache or pdf.parent / "parse.json")
    kind = source_kind(pdf.parent)

    # 스타일 통짜 경로 — 사람이 엔진으로 명시했다. 명시 선택이 연결(binding)보다
    # 세다. docx 전용: PDF 는 레이아웃 모델이 level 을 전부 1로 평면화해 "평면
    # 트리가 높은 점수로 통과" 하는 거짓 양성이 나고, hwp 는 신호 자체가 없다.
    if engine == "docxstyle":
        if kind != "docx":
            raise ValueError(
                f"docxstyle 엔진은 docx 문서에만 쓸 수 있습니다 (이 문서: {kind or '?'})"
                " — Word 스타일 레벨은 docx 만 싣는 신호입니다")
        from lawrag.core.structure import from_styles, viewer as viewer_mod
        result, blocks = from_styles.result_from_styles(parsed, doc=doc_id or pdf.name)
        data = viewer_mod.payload(result, blocks, pdf_path=pdf,
                                  elements=parsed.elements, images=parsed.images)
        if name:
            data["doc"] = name
        data["parser_warnings"] = parsed.warnings
        data["parser"] = parsed.parser
        data["engine"] = "docxstyle"
        data["source_kind"] = kind
        return data

    # 형식 바인딩(문서 > 폴더)이 있으면 유도가 아니라 형식 경로다
    bound = binding_of(doc_id, folder) if (binding_of and doc_id) else None
    if bound:
        data = _interpret_with_format(parsed, pdf, name, bound)
        data["source_kind"] = kind
        return data

    blocks = Block.from_elements(parsed.elements)
    # fingerprint 원장은 doc_id 로 관측한다 — 저장 파일명은 전부 source.pdf 라
    # 이름으로 세면 모든 문서가 한 항목으로 뭉개진다. 이름이 바뀌어도 doc_id 는 남는다.
    ledger = fp_mod.Ledger.load(ledger_path(store))
    result = pipeline.interpret(blocks, doc=doc_id or pdf.name, pdf_path=str(pdf),
                                ledger=ledger, **kw)
    if result.stats.get("may_freeze"):
        ledger.freeze(result.fingerprint, doc_id or pdf.name)
    ledger.save()
    data = viewer.payload(result, blocks, pdf_path=pdf, elements=parsed.elements,
                          images=parsed.images)
    if name:
        data["doc"] = name          # 화면 헤더용 — doc_id·source.pdf 가 아니라 문서 이름
    data["parser_warnings"] = parsed.warnings
    data["source_kind"] = kind
    data["parser"] = parsed.parser
    return data


def prepare_converted(d: Path, raw: bytes, suffix: str) -> Path:
    """HWP·DOCX 준비 — 원본 보존, 파싱, 합성 지면, 파싱 캐시.

    지면 좌표가 없는 형식이라 synthpdf 가 지면을 만들어 준다(lawxml 과 같은 길).
    좌표는 요소에 심겨 parse.json 으로 저장되므로, 재해석(reinterpret)이 캐시에서
    요소를 되살려도 오버레이가 그대로 성립한다. interpret_doc 은 이 캐시를 읽으므로
    docling 이 합성 PDF 를 다시 파싱하는 일은 없다.
    """
    from lawrag.core import parse_adapter
    from lawrag.core.structure import synthpdf

    src = d / f"source{suffix}"
    src.write_bytes(raw)                       # 원본 보존 — 재변환·감사용
    parsed = parse_adapter.parse(src)
    pdf_bytes = synthpdf.paginate(parsed.elements)   # 요소에 page·bbox 를 심는다
    pdf = d / "source.pdf"
    pdf.write_bytes(pdf_bytes)
    (d / "parse.json").write_text(
        json.dumps(parse_adapter.result_to_dump(parsed), ensure_ascii=False),
        encoding="utf-8")
    return pdf


# --------------------------------------------------------------- xml (lawxml)


def annex_md_map(item: dict | None) -> dict[str, str]:
    """manifest 항목의 별표서식 첨부 → {"별표 14의1": 사이드카 md 본문}.

    사이드카(.md)는 lawrag/core/hwp5_md.py(hwp5)·lawrag/core/hwpx_md.py(hwpx) 가 만든다.
    없는 별표는 XML 별표내용으로 남는다 — 연결은 있는 것만, 조용한 누락 없이
    호출부가 개수를 보고한다.
    """
    if not item:
        return {}
    pat = re.compile(r"^\[(별표|별지|별첨|서식|부록)\s*(\d+(?:의\d+)?)\]")
    out: dict[str, str] = {}
    for a in item.get("attachments", []):
        m = pat.match(a.get("title") or "")
        if not m or not a.get("file"):
            continue
        sidecar = ROOT / (a["file"] + ".md")
        if sidecar.exists():
            out[f"{m.group(1)} {m.group(2)}"] = sidecar.read_text(encoding="utf-8")
    return out


def find_manifest_item(raw: bytes) -> dict | None:
    """업로드된 XML 이 data/corpus/law 수집분이면 그 manifest 항목을 찾는다.

    화면 업로드는 어느 규정인지 스스로 말하지 않는다 — 본문 sha256 이 수집분과
    일치하면 같은 문서다 (개정판이면 해시가 달라 안 잡히고, 별표 md 연결 없이
    XML 별표내용으로 들어간다 — 그때는 collect→convert 후 재인제스트가 맞다).
    """
    mp = ROOT / "data" / "corpus" / "law" / "manifest.json"
    if not mp.exists():
        return None
    sha = hashlib.sha256(raw).hexdigest()
    for item in json.loads(mp.read_text("utf-8"))["items"]:
        shas = {item.get("body_sha256")}
        shas.update(a.get("sha256") for a in item.get("attachments", [])
                    if a.get("role") == "body")
        if sha in shas:
            return item
    return None


def ingest_lawxml_bytes(raw: bytes, name: str, store: Path, folder: str = "",
                        extra_meta: dict | None = None,
                        manifest_item: dict | None = None) -> dict:
    """본문 XML 바이트 → 스토어 등록. CLI 와 업로드 API 가 공유하는 유일한 경로."""
    from lawrag.core.structure import lawxml, viewer

    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    if manifest_item is None:
        manifest_item = find_manifest_item(raw)
    annex_md = annex_md_map(manifest_item)

    d = store / doc_id
    extra_meta = dict(extra_meta or {})
    # 수집 순서로 현행을 정하지 않는다. 공식 manifest의 canonical 본문 집합이
    # legal_generation.synchronize_structure에서 같은 계열 전체의 지위를 확정한다.
    # 단독 업로드는 검증 전 문서이므로 검색 진입점에서 현행인 척하지 않는다.
    if extra_meta.get("kind") in {"law", "admrul"}:
        extra_meta.setdefault("status", "미확정")
        extra_meta.setdefault("canonical", False)
        extra_meta.setdefault("series", name)
    prev = {}
    if (d / "meta.json").exists():      # 재업로드 — 사람이 고친 이름·폴더를 지킨다
        try:
            prev = json.loads((d / "meta.json").read_text("utf-8"))
        except Exception:
            prev = {}
    name = prev.get("name") or name

    result, blocks, pdf_bytes, info = lawxml.build(raw.decode("utf-8"), name,
                                                   annex_md=annex_md)

    d.mkdir(parents=True, exist_ok=True)
    (d / "source.xml").write_bytes(raw)
    pdf = d / "source.pdf"
    pdf.write_bytes(pdf_bytes)

    data = viewer.payload(result, blocks, pdf_path=pdf)
    viewer.annotate_coordinate_scopes(data["nodes"], str(extra_meta.get("kind") or ""))
    data["doc"] = name
    data["parser_warnings"] = []
    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    meta = {
        "doc_id": doc_id, "name": name, "bytes": len(raw),
        "pages": len(data["pages"]), "score": data["fitness"]["score"],
        "passed": data["fitness"]["passed"], "tier": data["fitness"]["tier"],
        "fingerprint": data.get("fingerprint", {}).get("key"),
        "used_llm": False, "source_kind": "lawxml",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **extra_meta,
    }
    if folder:
        meta["folder"] = folder
    elif prev.get("folder"):
        meta["folder"] = prev["folder"]
    if meta.get("folder"):
        register_folder(store, meta["folder"])
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # 컨테이너(다른 uid)가 페이지 캐시를 이 디렉토리에 쓴다 — 쓰기를 열어 둔다.
    # 상대편 uid 소유 항목(pages/ 캐시)은 chmod 가 안 되므로 조용히 건너뛴다.
    for p in (d, *d.iterdir()):
        try:
            os.chmod(p, 0o666 if p.is_file() else 0o777)
        except PermissionError:
            pass

    units = data["stats"]["units"]
    return {"doc_id": doc_id, "name": name, "pages": meta["pages"],
            "nodes": len(data["nodes"]), "blocks": len(data["blocks"]),
            "units": units, "annex_md": data["stats"].get("annex_md_used", 0),
            "annex_have": len(annex_md), "meta": meta}


def ingest_rulehtml_bytes(raw: bytes, name: str, store: Path, folder: str = "",
                          extra_meta: dict | None = None,
                          site: str = "krx") -> dict:
    """조문 HTML 바이트 → 스토어 등록 — lawxml 과 같은 결정적 이관 규약.

    doc_id 는 HTML 바이트의 sha256 앞 16자리 — manifest 의 body_html_sha256 과
    결정적으로 이어진다(전문 HWP 가 아니라 이 HTML 이 구조화의 본문이다).
    별표·서식은 HTML 에 없다 — HWP 첨부의 몫으로 남는다.
    """
    from lawrag.core.structure import rulehtml, viewer

    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    d = store / doc_id
    prev = {}
    if (d / "meta.json").exists():      # 재유입 — 사람이 고친 이름·폴더를 지킨다
        try:
            prev = json.loads((d / "meta.json").read_text("utf-8"))
        except Exception:
            prev = {}
    name = prev.get("name") or name

    result, blocks, pdf_bytes = rulehtml.build(
        raw.decode("utf-8", errors="replace"), name, site=site)

    d.mkdir(parents=True, exist_ok=True)
    (d / "source.html").write_bytes(raw)
    pdf = d / "source.pdf"
    pdf.write_bytes(pdf_bytes)

    data = viewer.payload(result, blocks, pdf_path=pdf)
    viewer.annotate_coordinate_scopes(data["nodes"], str((extra_meta or {}).get("kind") or ""))
    data["doc"] = name
    data["parser_warnings"] = []
    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    meta = {
        "doc_id": doc_id, "name": name, "bytes": len(raw),
        "pages": len(data["pages"]), "score": data["fitness"]["score"],
        "passed": data["fitness"]["passed"], "tier": data["fitness"]["tier"],
        "fingerprint": data.get("fingerprint", {}).get("key"),
        "used_llm": False, "source_kind": "rulehtml", "site": site,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra_meta or {}),
    }
    if folder:
        meta["folder"] = folder
    elif prev.get("folder"):
        meta["folder"] = prev["folder"]
    if meta.get("folder"):
        register_folder(store, meta["folder"])
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    for p in (d, *d.iterdir()):         # 컨테이너 페이지 캐시 쓰기 허용 (lawxml 과 동일)
        try:
            os.chmod(p, 0o666 if p.is_file() else 0o777)
        except PermissionError:
            pass

    return {"doc_id": doc_id, "name": name, "pages": meta["pages"],
            "nodes": len(data["nodes"]), "blocks": len(data["blocks"]),
            "units": data["stats"]["units"], "meta": meta}


# ------------------------------------------------------------------------ 문


def ingest(raw: bytes, filename: str, *, store: Path, name: str = "",
           folder: str = "", use_llm: bool = False, engine: str = "",
           hints: Optional[dict] = None,
           binding_of: Optional[Callable[[str, str], Optional[str]]] = None,
           extra_meta: Optional[dict] = None,
           manifest_item: Optional[dict] = None,
           raw_via: str = "upload") -> dict:
    """문서 하나를 형식에 맞는 길로 구조화 스토어에 넣는다 — 유일한 문.

    반환은 {"doc_id", "meta"} (+xml 은 "detail" 에 이관 요약). 사용자가 고칠 수
    있는 실패(모르는 형식·위장 포맷·엔진-형식 불일치)는 ValueError 로 올린다 —
    HTTP 로 옮기는 일은 호출부(라우터) 몫이다.

    원본은 스토어(파생층) 밖 **raw 층(data/corpus)** 에도 한 번 남는다 — 어느
    manifest 에도 없는 sha 면 corpus/uploads/ 에 사본 + 등록 한 줄
    (lawrag/core/rawstore.py). 수집 manifest 에서 온 것은 이미 raw 라 안 남긴다.
    등록 실패는 구조화를 막지 않는다(fail-open, 로그).
    """
    family = family_of(filename)
    if family is None:
        raise ValueError("PDF·HWP(X)·DOCX 또는 법령 본문 XML·조문 HTML 만 받습니다")
    name = name or Path(filename).stem
    try:
        from lawrag.core import rawstore
        rawstore.ensure(raw, filename, name=name, kind=str((extra_meta or {}).get("kind") or ""),
                        folder=(folder or "").strip(), via=raw_via,
                        corpus=rawstore.corpus_for(store))
    except Exception:                                   # pragma: no cover
        import logging
        logging.getLogger("lawrag.core.ingest").exception("raw 등록 실패 — 구조화는 계속")

    if family == "xml":
        r = ingest_lawxml_bytes(raw, name, store, (folder or "").strip(),
                                extra_meta=extra_meta, manifest_item=manifest_item)
        return {"doc_id": r["doc_id"], "meta": r["meta"], "detail": r}

    if family == "html":
        r = ingest_rulehtml_bytes(raw, name, store, (folder or "").strip(),
                                  extra_meta=extra_meta)
        return {"doc_id": r["doc_id"], "meta": r["meta"], "detail": r}

    eng = "docxstyle" if engine == "docxstyle" else ""
    doc_id = hashlib.sha256(raw).hexdigest()[:16]
    d = store / doc_id
    prev = {}
    if (d / "meta.json").exists():      # 같은 내용 재유입 — 사람이 고친 이름·폴더를 지킨다
        try:
            prev = json.loads((d / "meta.json").read_text("utf-8"))
        except Exception:
            prev = {}
    d.mkdir(parents=True, exist_ok=True)

    kw = dict(hints or {})
    if use_llm:
        from lawrag.core.llm import LLM
        kw["llm"] = LLM()

    eff_folder = (folder or "").strip() or (prev.get("folder") or "")
    try:
        if family in ("hwp", "docx"):
            pdf = prepare_converted(d, raw, Path(filename.lower()).suffix)
        else:
            pdf = d / "source.pdf"
            pdf.write_bytes(raw)
        data = interpret_doc(pdf, store=store, doc_id=doc_id, folder=eff_folder,
                             name=prev.get("name") or name, engine=eng,
                             binding_of=binding_of, **kw)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise

    from lawrag.core.structure import viewer as viewer_mod
    viewer_mod.annotate_coordinate_scopes(data["nodes"], str((extra_meta or {}).get("kind") or ""))
    (d / "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    kind = source_kind(d)
    meta = {
        # 사람이 바꾼 이름이 파일명보다 먼저다 — 재유입이 관리를 되돌리면 안 된다.
        "doc_id": doc_id, "name": prev.get("name") or name, "bytes": len(raw),
        "source_kind": kind,
        "structured_by": structured_by(data, kind),
        "pages": len(data["pages"]), "score": data["fitness"]["score"],
        "passed": data["fitness"]["passed"], "tier": data["fitness"]["tier"],
        "fingerprint": data.get("fingerprint", {}).get("key"),
        "fingerprint_count": data.get("stats", {}).get("fingerprint_count"),
        "used_llm": bool(use_llm),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra_meta or {}),
    }
    if eng:
        meta["engine"] = eng      # 사람의 엔진 선택 — 재해석·신선도 판정이 따라간다
    new_folder = (folder or "").strip()
    if new_folder:
        meta["folder"] = new_folder[:80]
    elif prev.get("folder"):
        meta["folder"] = prev["folder"]
    if meta.get("folder"):
        register_folder(store, meta["folder"])
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, "meta": meta}
