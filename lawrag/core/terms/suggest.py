"""신규 용어 추천 — 질의 로그의 특이 키워드 탐지 (사용자 결정 2026-08-10).

벡터 기본 검색에서 질의는 전부 진단 튜플에 남는다. 이 배치는 그 로그의
명사구를 꺼내, **이미 아는 것**(활성·잠정·tombstone)과 임베딩 코사인으로
대조해 갈래를 나눈다:

    기각 계열(tombstone 과 유사 ≥ NEAR)   → 버림 — 이미 사람이 거절한 부류
    기존 용어와 유사 ≥ NEAR               → 별칭 후보로 추천 (최근접 용어 명시)
    어디에도 안 가까움(특이)               → 신규 용어로 추천

추천은 **잠정 등재**다 — 색인에는 활성만 실리므로 검색을 오염시키지 않고,
검수 큐에 올라 사람의 승인을 기다린다. 비공허성은 여기서도 문이다:
문서에 실제로 닿지 않는 표현은 추천하지 않는다(질의에만 있는 말은
별칭 승격 루프(Phase 3)의 몫이지 용어 추출의 몫이 아니다).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import store_path, terms_path
from lawrag.core.terms.candidates import STOP_SOLO, _MARKER
from lawrag.core.terms.transcribe import _load_docs, _load_terms, _save_terms, norm

NEAR = 0.90             # 이 이상이면 "같은 부류" — 실측 조정 대상
MIN_LEN = 2
MAX_PHRASES_PER_QUERY = 6


# ---------------------------------------------------------------- 명사구
def _phrases(kiwi, query: str) -> list[str]:
    """질의의 최대 명사 연쇄 — 후보 생성(candidates.py)과 같은 품사 규칙."""
    out = []
    try:
        toks = kiwi.tokenize(query)
    except Exception:
        return out
    run: list = []
    for t in list(toks) + [None]:
        if t is not None and t.tag in ("NNG", "NNP", "SL"):
            run.append(t)
            continue
        if run:
            s0, s1 = run[0].start, run[-1].start + run[-1].len
            sfc = query[s0:s1].strip()
            k = norm(sfc)
            if (len(k) >= MIN_LEN and not _MARKER.fullmatch(k)
                    and not (len(run) == 1 and run[0].form in STOP_SOLO)
                    and re.search(r"[가-힣A-Za-z]", k)):
                out.append(sfc)
            run = []
    return out[:MAX_PHRASES_PER_QUERY]


def _reachable(views, key: str) -> int:
    """비공허성 — 문서 블록 본문에 정규형으로 닿는가. 닿는 블록 수."""
    n = 0
    for v in views:
        for b in v.blocks:
            if key in norm(b.get("text") or ""):
                n += 1
    return n


# ---------------------------------------------------------------- 본체
def run(store: Optional[Path] = None, glossary: Optional[Path] = None,
        min_count: int = 1, limit_queries: int = 500) -> dict:
    import numpy as np

    from lawrag.core import embedding
    from lawrag.core.rag import tuples
    from kiwipiepy import Kiwi

    glossary = glossary or (store.parent / "glossary.json" if store
                            else terms_path())
    existing = _load_terms(glossary)
    known_keys: set[str] = set()
    active_surfaces: list[str] = []
    dead_surfaces: list[str] = []
    for t in existing.values():
        for sfc in t.get("surfaces", [t.get("term", "")]):
            known_keys.add(norm(sfc))
            if t.get("status") == "tombstone":
                dead_surfaces.append(sfc)
            elif t.get("status") in (None, "활성"):
                active_surfaces.append(sfc)

    # 질의 로그 → 미지의 명사구 카운트
    kiwi = Kiwi()
    counts: dict[str, dict] = {}
    for rec in tuples.read(limit=limit_queries):
        for sfc in _phrases(kiwi, rec.get("질의", "")):
            key = norm(sfc)
            if key in known_keys:
                continue
            row = counts.setdefault(key, {"surface": sfc, "n": 0})
            row["n"] += 1
    cand = {k: v for k, v in counts.items() if v["n"] >= min_count}
    if not cand:
        return {"suggested": [], "alias_hints": [], "skipped": []}

    # 결정론 게이트 — 등재와 같은 문이다 (문이 둘이면 규칙이 갈린다):
    #   파편   승인 용어의 부분 문자열("설명"⊂"설명의무")은 새 용어가 아니다.
    #          역방향(더 긴 복합어)은 정당한 신조어일 수 있어 통과시킨다.
    #   비공허 문서에 닿지 않으면 추천하지 않는다.
    #   변별력 게이트의 lift 컷 재사용 — 어디에나 있는 말은 질의에서 와도 일반어다.
    from lawrag.core.terms.gate import _lift_cut

    views = _load_docs(store)
    total_blocks = max(sum(len(v.blocks) for v in views), 1)
    active_norms = {norm(s) for s in active_surfaces}
    reachable = {}
    skipped_gate = []
    for k, v in cand.items():
        frag_of = next((a for a in active_norms if k != a and k in a), None)
        if frag_of:
            skipped_gate.append({"surface": v["surface"],
                                 "이유": f"파편: 승인 용어 '{frag_of}' 의 일부"})
            continue
        hit = _reachable(views, k)
        if not hit:
            skipped_gate.append({"surface": v["surface"], "이유": "비공허성"})
            continue
        ratio = hit / total_blocks
        cut = _lift_cut(k)
        if ratio > cut:
            skipped_gate.append({"surface": v["surface"],
                                 "이유": f"변별력: 블록 {ratio:.0%} (컷 {cut:.0%})"})
            continue
        reachable[k] = {**v, "blocks": hit}
    if not reachable:
        return {"suggested": [], "alias_hints": [], "skipped": skipped_gate}

    # 임베딩 대조 — 활성/기각과의 최근접
    keys = list(reachable)
    texts = [reachable[k]["surface"] for k in keys]
    q_vec = embedding.encode(texts)
    if q_vec is None:
        raise RuntimeError("임베딩 모델을 부르지 못했습니다")
    act_vec = embedding.encode(active_surfaces) if active_surfaces else None
    dead_vec = embedding.encode(dead_surfaces) if dead_surfaces else None

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    suggested, alias_hints, skipped = [], [], list(skipped_gate)
    for i, k in enumerate(keys):
        row = reachable[k]
        sim_dead, near_dead = 0.0, ""
        if dead_vec is not None and len(dead_vec):
            sims = dead_vec @ q_vec[i]
            j = int(np.argmax(sims))
            sim_dead, near_dead = float(sims[j]), dead_surfaces[j]
        sim_act, near_act = 0.0, ""
        if act_vec is not None and len(act_vec):
            sims = act_vec @ q_vec[i]
            j = int(np.argmax(sims))
            sim_act, near_act = float(sims[j]), active_surfaces[j]

        if sim_dead >= NEAR and sim_dead >= sim_act:
            skipped.append({"surface": row["surface"],
                            "이유": f"기각 계열 '{near_dead}' 유사 {sim_dead:.2f}"})
            continue
        kind = "별칭후보" if sim_act >= NEAR else "신규"
        note = (f"[질의 추천·{kind}] 질의 {row['n']}회 · 문서 {row['blocks']}블록"
                + (f" · 최근접 '{near_act}' {sim_act:.2f}" if near_act else ""))
        existing[k] = {"term": row["surface"], "key": k,
                       "surfaces": [row["surface"]], "note": note[:200],
                       "source": "질의루프", "status": "잠정",
                       "confidence": "medium", "created": now,
                       "hits": 0, "misses": 0, "occurrences": []}
        (alias_hints if kind == "별칭후보" else suggested).append(
            {"surface": row["surface"], "note": note})

    if suggested or alias_hints:
        _save_terms(glossary, existing)
    return {"suggested": suggested, "alias_hints": alias_hints,
            "skipped": skipped, "store": str(glossary)}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m lawrag.core.terms suggest",
        description="질의 로그의 특이 키워드 → 신규 용어·별칭 추천 (잠정 등재 → 검수 큐)")
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--glossary", type=Path, default=None)
    ap.add_argument("--min-count", type=int, default=1,
                    help="질의 등장 최소 횟수 — 로그가 쌓이면 올린다")
    args = ap.parse_args(argv)
    rep = run(args.store, args.glossary, min_count=args.min_count)
    print(f"신규 추천 {len(rep['suggested'])} · 별칭 후보 {len(rep['alias_hints'])} · "
          f"제외 {len(rep['skipped'])}")
    for r in rep["suggested"][:10]:
        print(f"  신규: {r['surface']} — {r['note']}")
    for r in rep["alias_hints"][:10]:
        print(f"  별칭: {r['surface']} — {r['note']}")
    for r in rep["skipped"][:5]:
        print(f"  제외: {r['surface']} — {r['이유']}")
    return 0
