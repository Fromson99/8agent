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

_cache: dict[tuple[str, bool], tuple[int, dict]] = {}


def delegation_path() -> Path:
    from lawrag.runtime.content_snapshot import current_content_snapshot

    snapshot = current_content_snapshot()
    if snapshot is not None:
        return snapshot.semantic_path("delegation.json")
    return Path(os.environ.get("RAG_DELEGATION_STORE",
                               store_path().parent / "delegation.json"))


def adjacency(path: str | Path | None = None, *,
              include_document_targets: bool = False) -> dict:
    """(doc_id, 조 node) → 나가는 공식 위임 인접 리스트.

    ``path``를 받는 이유는 그래프 빌더와 제품 런타임이 같은 전사 파일을 명시적으로
    소비하게 하기 위해서다. 과거 빌더는 자신의 ``data_dir``를 알고도 전역 env/default를
    다시 해석해, 실제 ``data/delegation.json`` 대신 빈 경로를 읽을 수 있었다.

    법제처가 위임행정규칙의 대상 조문을 주지 않은 행도 ``include_document_targets``가
    켜지면 ``node=None``인 문서 수준 포인터로 보존한다. 기존 조문 확장 호출자는 기본값을
    사용하므로 좌표가 완성된 간선만 계속 받는다.
    """
    p = Path(path) if path is not None else delegation_path()
    if not p.exists():
        return {}
    mt = p.stat().st_mtime_ns
    cache_key = (str(p.resolve()), bool(include_document_targets))
    cached = _cache.get(cache_key)
    if cached is not None and cached[0] == mt:
        return cached[1]
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
        if not (s.get("doc_id") and s.get("node") is not None and d.get("doc_id")):
            continue                    # 출발 좌표나 대상 문서가 없으면 걷지 못한다
        if d.get("node") is None and not include_document_targets:
            continue
        row = {
            "doc_id": d["doc_id"], "node": d.get("node"), "kind": e["kind"],
            "link": e.get("link", ""), "name": d.get("name", ""),
            "jo": d.get("jo") or "", "src_anchor": s.get("anchor"),
            "provenance": "law.go.kr:lsDelegated"}
        bucket = out.setdefault((s["doc_id"], s["node"]), [])
        key = (row["doc_id"], row["node"], row["kind"], row["link"])
        if any((old["doc_id"], old.get("node"), old["kind"], old.get("link", "")) == key
               for old in bucket):
            continue
        bucket.append(row)
        n += 1
    _cache[cache_key] = (mt, out)
    log.info("위임 인접 리스트 — 출발 조 %d, 간선 %d (%s)", len(out), n, p.name)
    return out
