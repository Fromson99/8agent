"""Read-only, bounded views over the compiled legal property graph.

The UI never downloads the billion-byte SQLite graph. It receives a typed,
bounded neighborhood so Concept, Assertion and source evidence remain distinct.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query


ROOT = Path(__file__).resolve().parents[3]
router = APIRouter(prefix="/v1/knowledge", tags=["knowledge-graph"])

NODE_KINDS = frozenset({
    "Concept", "Assertion", "Document", "Section", "Lexeme", "Frame",
    "TextBlock", "Mention", "Quantity", "Tag", "FrameClass",
    "PendingReference",
})
SEMANTIC_EDGES = frozenset({
    "NORMALIZES_TO", "DENOTES", "IS_A", "EQUIVALENT_TO", "REALIZES",
    "SATISFIES", "OPPOSITE_OF", "ACTOR", "PREDICATE", "OBJECT", "TARGET",
    "METHOD", "MODALITY", "CONDITION", "EFFECT", "SUBJECT", "FUNCTION",
    "EXCEPTION", "SUPPORTED_BY", "REFERENCES", "DEFINES", "ALIAS_OF",
    "DEEMS", "EXCLUDES", "INCORPORATES", "RECEIVES_FROM", "BASED_ON",
    "HAS_SECTION", "PARENT_OF", "HAS_FRAME", "HAS_ACTION", "HAS_OBJECT",
    "HAS_ACTOR", "HAS_TARGET", "HAS_QUANTITY", "MEASURES", "IN_ARTICLE",
    "HAS_TAG", "HAS_CLASS", "MENTIONS_TERM", "CONTAINS_BLOCK",
    "HAS_MENTION", "HAS_LEXEME", "USES_LOCATOR", "HAS_UNRESOLVED_REFERENCE",
})
EDGE_PRIORITY = {
    "IS_A": 0, "EQUIVALENT_TO": 0, "REALIZES": 0, "SATISFIES": 0,
    "OPPOSITE_OF": 0, "ACTOR": 1, "PREDICATE": 1, "OBJECT": 1,
    "TARGET": 1, "METHOD": 1, "MODALITY": 1, "CONDITION": 1,
    "EFFECT": 1, "FUNCTION": 1, "EXCEPTION": 1, "SUPPORTED_BY": 2,
    "DEFINES": 2, "REFERENCES": 2, "DEEMS": 2, "EXCLUDES": 2,
    "INCORPORATES": 2, "NORMALIZES_TO": 3, "DENOTES": 3,
    "CONTAINS_BLOCK": 4, "HAS_MENTION": 4, "HAS_LEXEME": 4,
}


def _path() -> Path:
    return Path(os.environ.get("DOMAIN_GRAPH_DB") or
                ROOT / "data" / "domain_graph" / "graph.sqlite")


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    path = _path()
    if not path.is_file():
        raise HTTPException(404, "컴파일된 domain graph가 없습니다")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _json(value: object) -> dict:
    try:
        return json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _trim(value: object, length: int = 240) -> object:
    if isinstance(value, str):
        return value if len(value) <= length else value[:length] + "…"
    if isinstance(value, list):
        return [_trim(v, 120) for v in value[:12]]
    if isinstance(value, dict):
        return {str(k): _trim(v, 160) for k, v in list(value.items())[:20]}
    return value


def _node(row: sqlite3.Row | dict, degree: int | None = None) -> dict:
    data = dict(row)
    props = _trim(_json(data.get("props")))
    out = {"id": data["id"], "kind": data["kind"],
           "label": data.get("label") or data["id"], "props": props}
    if degree is not None:
        out["degree"] = degree
    return out


def _edge(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    return {"id": data["id"], "kind": data["kind"], "src": data["src"],
            "dst": data["dst"], "props": _trim(_json(data.get("props")), 160)}


@router.get("/summary", summary="컴파일된 법률 지식 그래프 규모와 레이어")
def summary():
    with _db() as conn:
        nodes = {row["kind"]: row["n"] for row in conn.execute(
            "SELECT kind,COUNT(*) n FROM nodes GROUP BY kind ORDER BY n DESC")}
        edges = {row["kind"]: row["n"] for row in conn.execute(
            "SELECT kind,COUNT(*) n FROM edges GROUP BY kind ORDER BY n DESC")}
        meta = {row["key"]: _json(row["value"]) for row in conn.execute(
            "SELECT key,value FROM build_meta")}
    layers = {
        "meaning": sum(nodes.get(k, 0) for k in ("Lexeme", "Concept")),
        "rule": sum(nodes.get(k, 0) for k in ("Assertion", "Frame", "FrameClass")),
        "source": sum(nodes.get(k, 0) for k in ("Document", "Section", "TextBlock")),
        "evidence": sum(nodes.get(k, 0) for k in ("Mention", "Quantity", "Tag")),
    }
    return {"nodes": nodes, "edges": edges, "layers": layers,
            "total_nodes": sum(nodes.values()), "total_edges": sum(edges.values()),
            "meta": meta}


@router.get("/search", summary="Concept·Assertion·문서 노드 검색")
def search(q: str = Query("", max_length=120),
           kinds: str = Query("Concept,Assertion,Document", max_length=160),
           limit: int = Query(24, ge=1, le=50)):
    selected = [x.strip() for x in kinds.split(",") if x.strip() in NODE_KINDS]
    if not selected:
        selected = ["Concept", "Assertion", "Document"]
    marks = ",".join("?" for _ in selected)
    q = q.strip()
    params: list[object] = list(selected)
    where = f"n.kind IN ({marks})"
    if q:
        where += " AND (n.label LIKE ? OR n.id=?)"
        params.extend((f"%{q}%", q))
        order = "CASE WHEN n.label=? THEN 0 WHEN n.label LIKE ? THEN 1 ELSE 2 END,LENGTH(n.label),n.label"
        params.extend((q, f"{q}%"))
    else:
        preferred = ("설명의무", "의무", "금지", "허용", "정의", "위임", "소각", "자기주식")
        pm = ",".join("?" for _ in preferred)
        where += f" AND n.label IN ({pm})"
        params.extend(preferred)
        order = f"CASE n.label " + " ".join(
            f"WHEN ? THEN {i}" for i, _ in enumerate(preferred)) + " ELSE 99 END"
        params.extend(preferred)
    params.append(limit)
    sql = f"""
        SELECT n.*,
          (SELECT COUNT(*) FROM edges eo WHERE eo.src=n.id) +
          (SELECT COUNT(*) FROM edges ei WHERE ei.dst=n.id) degree
        FROM nodes n WHERE {where} ORDER BY {order} LIMIT ?
    """
    with _db() as conn:
        rows = [_node(row, int(row["degree"])) for row in conn.execute(sql, params)]
    return {"query": q, "results": rows}


def _neighbor_edges(conn: sqlite3.Connection, node_id: str, limit: int) -> list[dict]:
    # LIMIT 뒤에서 타입을 거르면 대량의 MAY_REFER_TO가 앞을 차지해 정작
    # Assertion 역할 간선이 사라질 수 있다. 허용 타입과 우선순위를 SQL 안에 둔다.
    kinds = sorted(SEMANTIC_EDGES)
    marks = ",".join("?" for _ in kinds)
    priority = "CASE kind " + " ".join(
        f"WHEN '{kind}' THEN {rank}" for kind, rank in EDGE_PRIORITY.items()
    ) + " ELSE 8 END"
    rows = conn.execute(
        f"SELECT * FROM edges WHERE (src=? OR dst=?) AND kind IN ({marks}) "
        f"ORDER BY {priority},kind,id LIMIT ?",
        (node_id, node_id, *kinds, limit),
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/neighborhood", summary="타이핑된 bounded property-graph 이웃")
def neighborhood(node_id: str = Query(..., alias="id", min_length=3, max_length=180),
                 depth: int = Query(2, ge=1, le=3),
                 limit: int = Query(180, ge=20, le=320)):
    with _db() as conn:
        center = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if center is None:
            raise HTTPException(404, "그래프 노드를 찾지 못했습니다")
        nodes: dict[str, dict] = {node_id: _node(center)}
        edges: dict[str, dict] = {}
        frontier = [node_id]
        truncated = False
        for level in range(depth):
            if not frontier or len(nodes) >= limit:
                break
            next_frontier: list[str] = []
            per_node = min(64 if level == 0 else 16,
                           max(6, (limit - len(nodes)) // max(1, len(frontier))))
            for current in frontier[:32]:
                for item in _neighbor_edges(conn, current, per_node):
                    other = item["dst"] if item["src"] == current else item["src"]
                    if other not in nodes:
                        if len(nodes) >= limit:
                            truncated = True
                            break
                        row = conn.execute("SELECT * FROM nodes WHERE id=?", (other,)).fetchone()
                        if row is None or row["kind"] not in NODE_KINDS:
                            continue
                        nodes[other] = _node(row)
                        next_frontier.append(other)
                    edges[item["id"]] = _edge(item)
                if len(nodes) >= limit:
                    break
            frontier = next_frontier
        degrees: dict[str, int] = {nid: 0 for nid in nodes}
        for item in edges.values():
            if item["src"] in degrees:
                degrees[item["src"]] += 1
            if item["dst"] in degrees:
                degrees[item["dst"]] += 1
        for nid, value in degrees.items():
            nodes[nid]["degree"] = value
    return {"center": node_id, "nodes": list(nodes.values()),
            "edges": list(edges.values()), "truncated": truncated,
            "depth": depth, "limit": limit}
