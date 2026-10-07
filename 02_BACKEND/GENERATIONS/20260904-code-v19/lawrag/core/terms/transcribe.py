"""Tier 1 전사 — 문서 저자들이 이미 만들어 둔 정의 구조물을 회수한다.

발명 비용 0, 오류 최소 (ontology_kg §3.3). 한국어 정의 구문은 패턴 수가
매우 적다:

    인용정의   "금융투자업"이란 … / "X"라 함은 …      (따옴표가 경계를 준다)
    정의       X이란 …를 말한다                        (따옴표 없음 — 정의 조항
                                                        구획 안이면 high, 밖이면 medium)
    이하별칭   금융소비자 보호에 관한 법률(이하 "법"이라 한다)
               → 별칭은 저자가 스코프까지 명시한 것 — 문서 스코프로 등재
    괄호약어   안전밸브(PSV)                            (괄호 안이 영문 약어일 때만 —
                                                        `제2조(정의)` 는 마커지 별칭이 아니다)

산출은 두 갈래다: 감사용 원본(var/out/terms/tier1.jsonl)과, 게이트(표면형 충돌
검사)를 통과한 등재분(glossary.json). LLM 출력이 아니어도 등재 전 검사는
같다 — 등재의 문은 하나여야 한다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import DocView, store_path, terms_path
from lawrag.platform.paths import runtime_path

OUT_DIR = runtime_path("out", "terms")

# 묶음 키 — lawrag/api/routers/glossary.py 의 norm 과 같은 규칙(공백만 지운다).
# casefold 를 하지 않는 것도 같다 — 저 파일의 키와 섞이므로 규칙이 갈리면 안 된다.
def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


# ---------------------------------------------------------------- 정규식
# 정의 표기 패턴의 정본은 lawrag/core/defpatterns 다 — 검색 런타임(rag/definitions)과
# 함께 쓰는 무상태 자산이라 중립 지대에 있다(격리: rag 는 terms 를 import 못 한다).
# 여기서 재수출하므로 terms 안 소비자(gate·suggest·build)는 그대로다.
from lawrag.core.defpatterns import (  # noqa: F401 — 재수출
    _DEICTIC, _Q_OPEN, _Q_CLOSE, RE_BARE, RE_QUOTED, RE_YIHA)

# 안전밸브(PSV) — 괄호 안이 **전부 대문자 약어**일 때만. `제2조(정의)` 같은
# 마커·제목 괄호, `선물(Futures)` 같은 영문 번역은 별칭이 아니다.
RE_ABBR = re.compile(
    r'([가-힣][가-힣0-9·]{1,19})\s*\(\s*([A-Z]{2,6})\s*\)')
# 신용등급(AAA·BB+)은 약어가 아니다 — 같은 글자의 반복 + 부호.
RE_RATING = re.compile(r'([A-Z])\1+[+-]?$')

# 정의 조항 구획 — 제목이 이 모양이면 그 마디 전체가 정의 역할이다(§3.3).
RE_DEF_TITLE = re.compile(r'정의\s*\)?\s*$|\(\s*정의\s*\)')


def _sentence(text: str, start: int, end: int, cap: int = 160) -> str:
    """매치 주변을 문장 경계로 넓힌 발췌 — 검수 화면이 근거를 읽을 수 있어야 한다."""
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    tail = text.find("다.", end)
    right = tail + 2 if 0 <= tail < end + 200 else min(end + 80, len(text))
    return text[left:right].strip()[:cap]


# ---------------------------------------------------------------- 추출
def _load_docs(store: Optional[Path] = None) -> list[DocView]:
    """구조화 산출(result.json)에서 조회 창을 세운다 — lawrag/core/rag/index.load 와
    같은 순회. 값 기반 함수(extract)를 따로 두어 시험은 저장소 없이 돈다."""
    store = store or store_path()
    out: list[DocView] = []
    if not store.exists():
        return out
    for d in sorted(store.iterdir()):
        rj, mj = d / "result.json", d / "meta.json"
        if not (rj.exists() and mj.exists()):
            continue
        try:
            out.append(DocView.build(d.name,
                                     json.loads(mj.read_text(encoding="utf-8")),
                                     json.loads(rj.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def _def_nodes(v: DocView) -> set:
    """정의 역할 구획의 마디 id — 제목에 '(정의)' 가 있는 마디와 그 자손."""
    roots = {n.get("id") for n in v.nodes
             if RE_DEF_TITLE.search((n.get("title") or "").strip())}
    if not roots:
        return roots
    out = set(roots)
    changed = True
    while changed:
        changed = False
        for n in v.nodes:
            if n.get("id") not in out and n.get("parent") in out:
                out.add(n.get("id"))
                changed = True
    return out


def extract_doc(v: DocView) -> list[dict]:
    """문서 하나에서 정의·별칭을 전사한다. 행 하나가 발견 하나다."""
    rows: list[dict] = []
    def_nodes = _def_nodes(v)

    def coord(b: dict) -> dict:
        n = v.owner(b.get("idx")) or {}
        return {"doc_id": v.doc_id, "doc": v.name, "node": n.get("id"),
                "block": b.get("idx"), "page": b.get("page"),
                "bbox": b.get("rect"), "path": v.path(n.get("id")),
                "in_def_section": n.get("id") in def_nodes}

    def push(term: str, alias: Optional[str], pattern: str, conf: str,
             b: dict, s: int, e: int, text: str) -> None:
        term = (term or "").strip(" ·-—…·")
        if len(norm(term)) < 2:
            return
        if alias is not None and len(norm(alias)) < 2:
            alias = None
        rows.append({"용어": term, "별칭": (alias or "").strip() or None,
                     "패턴": pattern, "confidence": conf,
                     "발췌": _sentence(text, s, e), **coord(b)})

    for b in v.blocks:
        text = b.get("text") or ""
        if len(text) < 4:
            continue
        in_def = (v.owner(b.get("idx")) or {}).get("id") in def_nodes

        for m in RE_QUOTED.finditer(text):
            push(m.group(1), None, "인용정의", "high", b, m.start(), m.end(), text)
        for m in RE_BARE.finditer(text):
            # 인용정의가 같은 자리를 이미 잡았으면 중복이다(따옴표 안을 다시 잡음).
            if any(r["block"] == b.get("idx") and r["패턴"] == "인용정의"
                   and norm(r["용어"]) in norm(m.group(1)) for r in rows):
                continue
            push(m.group(1), None, "정의", "high" if in_def else "medium",
                 b, m.start(1), m.end(), text)
        for m in RE_YIHA.finditer(text):
            # 등재 대상은 **별칭 쪽**이다 — 저자가 "이하 X라 한다"로 스코프까지
            # 명시한 그 X 가 자산이고, 앞의 본용어 캡처는 문장 파편이기 일쑤다
            # (실측: "의 장", "은 주식회사 …"). 본용어 문맥은 발췌에 남는다.
            alias = (m.group(3) or "").strip()
            if alias.startswith(_DEICTIC):
                continue
            push(alias, None, "이하별칭", "high", b, m.start(), m.end(), text)
        for m in RE_ABBR.finditer(text):
            if re.match(r"^제\d", m.group(1)):          # 조문 마커의 괄호다
                continue
            if RE_RATING.fullmatch(m.group(2)):         # AAA·BB+ 는 신용등급이다
                continue
            # 한글 쪽 캡처는 어절 경계에서 잘릴 수 있다("응답서비스"→"답서비스").
            # 정밀도를 장담 못 하므로 medium — 잠정 등재로 들어가 검수를 기다린다.
            push(m.group(1), m.group(2), "괄호약어", "medium",
                 b, m.start(), m.end(), text)
    return rows


def extract(store: Optional[Path] = None) -> list[dict]:
    rows: list[dict] = []
    for v in _load_docs(store):
        rows.extend(extract_doc(v))
    return rows


# ---------------------------------------------------------------- 등재
def _load_terms(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {t["key"]: t for t in raw.get("terms", [])}
    except Exception:
        return {}


def _save_terms(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"terms": sorted(rows.values(), key=lambda r: r["key"])},
        ensure_ascii=False, indent=2), encoding="utf-8")


def register(rows: list[dict], terms_file: Optional[Path] = None) -> dict:
    """전사 결과를 용어층(glossary.json)에 등재한다.

    게이트는 표면형 충돌 검사다: 어떤 표면형(별칭 포함)의 정규형이 **다른**
    용어의 키와 겹치면 그 표면형은 싣지 않는다 — 모순 병합은 인덱스 오염이다.
    이미 있는 용어(수기 포함)와 키가 같으면 새 용어가 아니라 증거가 는다.
    """
    terms_file = terms_file or terms_path()
    existing = _load_terms(terms_file)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 발견을 용어(키)별로 모은다
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(norm(r["용어"]), []).append(r)

    # 표면형 → 키 지도 (충돌 검사용). 기존 파일의 표면형이 우선한다.
    surface_owner: dict[str, str] = {}
    for key, t in existing.items():
        for sfc in t.get("surfaces", []):
            surface_owner.setdefault(norm(sfc), key)

    added, updated, conflicts = [], [], []
    for key, found in grouped.items():
        term = found[0]["용어"]
        confs = {r["confidence"] for r in found}
        conf = "high" if "high" in confs else "medium"
        surfaces = [term] + sorted({r["별칭"] for r in found if r["별칭"]})
        occ = []
        seen: set[tuple] = set()
        for r in found:
            k = (r["doc_id"], r["block"])
            if k in seen:
                continue
            seen.add(k)
            occ.append({"doc_id": r["doc_id"], "doc": r["doc"], "node": r["node"],
                        "surface": term, "page": r["page"], "block": r["block"],
                        "text": r["발췌"][:120], "bbox": r["bbox"],
                        "via": "정의", "path": r["path"]})

        row = existing.get(key)
        if row is None:
            row = {"term": term, "key": key, "surfaces": [], "note": "",
                   "source": "tier1", "status": "활성" if conf == "high" else "잠정",
                   "confidence": conf, "created": now,
                   "hits": 0, "misses": 0, "occurrences": []}
            existing[key] = row
            added.append(term)
        else:
            updated.append(term)
        if not row.get("note"):
            row["note"] = f"정의: {found[0]['발췌']}"

        for sfc in surfaces:
            skey = norm(sfc)
            owner = surface_owner.get(skey)
            if owner is not None and owner != key:
                conflicts.append({"surface": sfc, "용어": term, "기존": owner})
                continue
            surface_owner[skey] = key
            if sfc not in row["surfaces"]:
                row["surfaces"].append(sfc)

        have = {(o.get("doc_id"), o.get("block"), o.get("via"))
                for o in row["occurrences"]}
        for o in occ:
            if (o["doc_id"], o["block"], o["via"]) not in have:
                row["occurrences"].append(o)
        row["scope"] = {"docs": sorted({o.get("doc_id")
                                        for o in row["occurrences"]
                                        if o.get("doc_id")})}

    _save_terms(terms_file, existing)
    return {"added": added, "updated": updated, "conflicts": conflicts,
            "total": len(existing), "store": str(terms_file)}


# ---------------------------------------------------------------- CLI
def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m lawrag.core.terms transcribe",
        description="Tier 1 전사 — 정의조항·정의술어·괄호별칭을 정규식으로 회수")
    ap.add_argument("--store", type=Path, default=None,
                    help="구조화 산출 저장소 (기본: STRUCTURE_STORE)")
    ap.add_argument("--glossary", type=Path, default=None,
                    help="등재할 용어 파일 (기본: GLOSSARY_STORE)")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "tier1.jsonl",
                    help="감사용 원본 jsonl")
    ap.add_argument("--dry-run", action="store_true", help="등재하지 않고 추출만")
    args = ap.parse_args(argv)

    rows = extract(args.store)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_pattern: dict[str, int] = {}
    for r in rows:
        by_pattern[r["패턴"]] = by_pattern.get(r["패턴"], 0) + 1
    print(f"전사 {len(rows)}건  {by_pattern}  → {args.out}")

    if args.dry_run:
        print("dry-run — 등재하지 않음")
        return 0
    # --store 를 지정했으면 용어 파일도 그 옆이다(glossary.json 자리 규약).
    # 스토어 따로 용어 파일 따로면 좌표가 서로 다른 문서 집합을 가리키게 된다.
    glossary = args.glossary or (args.store.parent / "glossary.json"
                                 if args.store else None)
    rep = register(rows, glossary)
    print(f"등재 신규 {len(rep['added'])} · 갱신 {len(rep['updated'])} · "
          f"충돌 제외 {len(rep['conflicts'])} → {rep['store']}")
    for c in rep["conflicts"][:10]:
        print(f"  충돌: {c['surface']!r} ({c['용어']}) — 기존 키 {c['기존']!r} 와 겹침")
    return 0
