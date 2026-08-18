"""위임 간선 로더 — data/delegation.json 을 검색이 걷는 인접 리스트로.

lawnet 이 전사해 둔 간선 중 **양끝이 스토어 좌표(doc_id·node)로 해소된 위임
계열**만 싣는다. 인용법령은 여기서 뺀다 — 문면 인용은 refs.py 가 이미 잡고,
위임("대통령령으로 정하는")만이 문면에 좌표가 없어 이 데이터가 유일한 길이다.

vector.py 와 같은 규율: 파일이 없으면 조용히 빈손 — 검색 사다리는 언제나 돈다.
파일이 바뀌면(mtime) 다시 싣는다.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import store_path

log = logging.getLogger("lawrag.core.rag.delegation")

KINDS = ("시행령", "시행규칙", "위임행정규칙")   # 위임 계열 — 확장이 거의 항상 옳다

_cache: dict = {"mtime": None, "out": {}}


def delegation_path() -> Path:
    return Path(os.environ.get("RAG_DELEGATION_STORE",
                               store_path().parent / "delegation.json"))


def adjacency() -> dict:
    """(doc_id, 조 node) -> [{doc_id, node, kind, link, name, jo}] — 나가는 위임."""
    p = delegation_path()
    if not p.exists():
        return {}
    mt = p.stat().st_mtime_ns
    if _cache["mtime"] == mt:
        return _cache["out"]
    out: dict[tuple, list[dict]] = {}
    try:
        edges = json.loads(p.read_text(encoding="utf-8")).get("edges", [])
    except Exception:
        log.warning("위임 간선 파일을 읽지 못했습니다 — %s", p)
        return {}
    n = 0
    for e in edges:
        if e.get("kind") not in KINDS:
            continue
        s, d = e.get("src") or {}, e.get("dst") or {}
        if not (s.get("doc_id") and s.get("node") is not None
                and d.get("doc_id") and d.get("node") is not None):
            continue                    # 한쪽이 미보유·미해소 — 걷지 못한다
        out.setdefault((s["doc_id"], s["node"]), []).append({
            "doc_id": d["doc_id"], "node": d["node"], "kind": e["kind"],
            "link": e.get("link", ""), "name": d.get("name", ""),
            "jo": d.get("jo") or ""})
        n += 1
    _cache.update(mtime=mt, out=out)
    log.info("위임 인접 리스트 — 출발 조 %d, 간선 %d (%s)", len(out), n, p.name)
    return out
