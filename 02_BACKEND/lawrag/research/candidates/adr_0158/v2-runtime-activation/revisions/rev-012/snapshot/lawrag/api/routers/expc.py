"""법령해석례 열람 API — /expc/ 화면이 읽는다.

    GET /v1/expc/summary          현황 — 사례 수·법령별 분포·위키 아티클 수
    GET /v1/expc/cases            목록 (q·law·org·year 필터, 몸통 없이 가볍게)
    GET /v1/expc/cases/{serial}   사례 하나 전체 (질의요지·회답·이유)
    GET /v1/expc/wiki             위키 인덱스 — index.md 원문 + 아티클 목록
    GET /v1/expc/wiki/{slug}      아티클 마크다운 원문 (slug = 주제/이름)

전부 읽기 전용이다. 정본은 두 층이다: 사례는 data/corpus/expc(수집 정본)를 정리한
data/expc/index.json (lawrag/pipeline/ingest_expc.py), 위키는 data/wiki/ — llm-wiki 정본
형태(raw/ 불변층 + wiki/<주제>/<아티클>.md, index.md 는 표 형식)를 그대로
따른다 (docs/expc.md §위키). 여기는 파일을 읽어 줄 뿐 해석하지 않는다 —
검색도 부분일치다 (질의응답의 검색과 겹치지 않는다).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/v1/expc", tags=["expc"])

ROOT = Path(__file__).resolve().parents[3]
STORE = Path(os.environ.get("EXPC_STORE") or ROOT / "data" / "expc")
WIKI_STORE = Path(os.environ.get("WIKI_STORE") or ROOT / "data" / "wiki")

_SEG_RE = re.compile(r"^[\w.\-가-힣]+$")      # 경로 탈출 차단 — 조각 단위 검사
_CASE_LINK_RE = re.compile(r"#case/(\d+)")
# index.md 표 행: | [제목](주제/파일.md) | 요약 | 날짜 |
_INDEX_ROW_RE = re.compile(
    r"^\|\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+\.md)\)\s*\|"
    r"\s*(?P<summary>[^|]*)\|\s*(?P<updated>[^|]*)\|", re.M)

_cache: dict = {"mtime": None, "index": None}


def _index() -> dict:
    """index.json — mtime 이 같으면 다시 읽지 않는다."""
    p = STORE / "index.json"
    if not p.is_file():
        raise HTTPException(404, "색인이 없습니다 — lawrag/pipeline/ingest_expc.py 를 먼저 돌리세요")
    mtime = p.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["index"] = json.loads(p.read_text("utf-8"))
        _cache["mtime"] = mtime
    return _cache["index"]


def _wiki_dir() -> Path:
    return WIKI_STORE / "wiki"


def _wiki_articles() -> list[dict]:
    """아티클 목록 — index.md 표가 정본이라 그 행을 판다 (llm-wiki 규약)."""
    idx = _wiki_dir() / "index.md"
    if not idx.is_file():
        return []
    out = []
    for m in _INDEX_ROW_RE.finditer(idx.read_text("utf-8")):
        title = m.group("title").strip()
        if title == "Article":                      # 표 머리행
            continue
        out.append({"slug": m.group("file").removesuffix(".md"),
                    "title": title,
                    "summary": m.group("summary").strip(),
                    "updated": m.group("updated").strip()})
    return out


def _case_mentions(serial: str) -> list[dict]:
    """이 사례를 인용한 아티클들 — 위키 본문의 #case/<일련번호> 링크 역방향."""
    d = _wiki_dir()
    if not d.is_dir():
        return []
    titles = {a["slug"]: a["title"] for a in _wiki_articles()}
    out = []
    for p in sorted(d.glob("*/*.md")):
        if serial in _CASE_LINK_RE.findall(p.read_text("utf-8")):
            slug = f"{p.parent.name}/{p.stem}"
            out.append({"slug": slug, "title": titles.get(slug, p.stem)})
    return out


def _light(c: dict) -> dict:
    """목록용 — 몸통(질의요지·회답·이유)을 뺀 행."""
    return {k: c[k] for k in ("serial", "case_no", "label", "decided",
                              "req_org", "ans_org", "laws")}


@router.get("/summary", summary="현황 — 사례·법령 분포·위키·생애 대기")
def summary():
    idx = _index()
    wiki = _wiki_articles()
    # 생애 권고가 '유지'가 아닌 아티클 수 — 상단바 배지가 읽는다 (손 대기 큐).
    pending = 0
    try:
        from lawrag.core.rag import wikilife
        pending = sum(1 for v in wikilife.report().values()
                      if v.get("권고") != "유지")
    except Exception:                                  # pragma: no cover
        pass
    return {"built_at": idx.get("built_at"), "source": idx.get("source"),
            "stats": idx.get("stats", {}), "wiki_articles": len(wiki),
            "wiki_pending": pending}


@router.get("/cases", summary="사례 목록 — 부분일치 필터")
def cases(q: str = Query("", description="안건명·질의요지·회답·이유 부분 일치"),
          law: str = Query("", description="관련 법령 명칭 완전 일치"),
          org: str = Query("", description="질의기관 완전 일치"),
          year: str = Query("", description="해석 연도 (YYYY)"),
          limit: int = Query(500, ge=1, le=2000),
          full: bool = Query(False, description="몸통(질의요지·회답·이유) 포함")):
    rows = _index().get("cases", [])
    if law:
        rows = [c for c in rows if law in c["laws"]]
    if org:
        rows = [c for c in rows if c["req_org"] == org]
    if year:
        rows = [c for c in rows if c["decided"].startswith(year)]
    if q:
        needle = q.lower()
        rows = [c for c in rows
                if needle in " ".join((c["label"], c["issue"], c["answer"],
                                       c["reason"])).lower()]
    shape = (lambda c: c) if full else _light
    return {"cases": [shape(c) for c in rows[:limit]], "total": len(rows)}


@router.get("/cases/{serial}", summary="사례 하나 — 질의요지·회답·이유 전체")
def case(serial: str):
    for c in _index().get("cases", []):
        if c["serial"] == serial:
            return {**c, "articles": _case_mentions(serial)}
    raise HTTPException(404, f"사례가 없습니다: {serial}")


@router.get("/wiki", summary="위키 인덱스 — 아티클 목록·생애 보고서·index.md 원문")
def wiki():
    idx = _wiki_dir() / "index.md"
    articles = _wiki_articles()
    # 생애 보고서(4기준·권고) — core.rag 가 없는 슬림 배포에선 배지만 빠진다.
    try:
        from lawrag.core.rag import wikilife
        life = wikilife.report()
        for a in articles:
            if a["slug"] in life:
                a["life"] = life[a["slug"]]
    except Exception:                                  # pragma: no cover
        pass
    return {"articles": articles,
            "index_md": idx.read_text("utf-8") if idx.is_file() else ""}


@router.get("/wiki/{slug:path}", summary="아티클 마크다운 원문 (slug = 주제/이름)")
def wiki_article(slug: str):
    parts = slug.split("/")
    if len(parts) > 2 or not all(_SEG_RE.fullmatch(s) for s in parts):
        raise HTTPException(400, "주제/이름 형태만 받습니다 — 경로 탈출은 안 됩니다")
    p = _wiki_dir().joinpath(*parts).with_suffix(".md")
    if not p.is_file():
        raise HTTPException(404, f"아티클이 없습니다: {slug}")
    return {"slug": slug, "markdown": p.read_text("utf-8")}
