"""SQLite property graph 저장소.

SQLite는 임시 구현 세부사항이다. 공개 계약은 nodes/edges와 kind/props이고,
이 네 필드는 Neo4j label/relationship/property로 손실 없이 옮길 수 있다.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .model import Edge, Node, lexeme_id


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    props TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_kind_label ON nodes(kind, label);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    src TEXT NOT NULL REFERENCES nodes(id),
    dst TEXT NOT NULL REFERENCES nodes(id),
    props TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_edges_src_kind ON edges(src, kind);
CREATE INDEX IF NOT EXISTS idx_edges_dst_kind ON edges(dst, kind);
CREATE TABLE IF NOT EXISTS build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _unpack(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    out["props"] = json.loads(out.get("props") or "{}")
    return out


class GraphStore:
    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        if readonly:
            self.conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path)
            self.conn.executescript(SCHEMA)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.conn:
            yield

    def put_node(self, node: Node) -> None:
        self.conn.execute(
            "INSERT INTO nodes(id,kind,label,props) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,label=excluded.label,props=excluded.props",
            (node.id, node.kind, node.label,
             json.dumps(node.props, ensure_ascii=False, sort_keys=True, default=str)),
        )

    def put_edge(self, edge: Edge) -> None:
        self.conn.execute(
            "INSERT INTO edges(id,kind,src,dst,props) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,src=excluded.src,dst=excluded.dst,props=excluded.props",
            (edge.id, edge.kind, edge.src, edge.dst,
             json.dumps(edge.props, ensure_ascii=False, sort_keys=True, default=str)),
        )

    def set_meta(self, key: str, value: object) -> None:
        self.conn.execute(
            "INSERT INTO build_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)),
        )

    def get_node(self, node_id: str) -> dict | None:
        return _unpack(self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone())

    def neighbors(self, node_id: str, *, direction: str = "out",
                  kinds: tuple[str, ...] = ()) -> list[dict]:
        column = "src" if direction == "out" else "dst"
        sql, params = f"SELECT * FROM edges WHERE {column}=?", [node_id]
        if kinds:
            sql += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
            params.extend(kinds)
        rows = []
        for row in self.conn.execute(sql, params):
            item = dict(row)
            item["props"] = json.loads(item.get("props") or "{}")
            rows.append(item)
        return rows

    def resolve(self, surface: str, *, doc_id: str = "") -> list[dict]:
        """표면형 하나가 가리키는 개념/문서좌표를 provenance와 함께 돌려준다."""
        lid = lexeme_id(surface)
        found: dict[tuple[str, str], dict] = {}
        for edge in self.neighbors(lid, kinds=("NORMALIZES_TO", "DENOTES")):
            if doc_id and edge["props"].get("doc_id") not in (None, "", doc_id):
                continue
            target = self.get_node(edge["dst"])
            if target:
                key = (edge["kind"], target["id"])
                if key not in found:
                    found[key] = {"relation": edge["kind"], "edge": edge["props"],
                                  "evidence": [edge["props"]], "target": target}
                elif edge["props"] not in found[key]["evidence"]:
                    found[key]["evidence"].append(edge["props"])
        return list(found.values())

    def counts(self) -> dict:
        nodes = {r["kind"]: r["n"] for r in self.conn.execute(
            "SELECT kind,COUNT(*) AS n FROM nodes GROUP BY kind ORDER BY kind")}
        edges = {r["kind"]: r["n"] for r in self.conn.execute(
            "SELECT kind,COUNT(*) AS n FROM edges GROUP BY kind ORDER BY kind")}
        return {"nodes": nodes, "edges": edges}

    def export_jsonl(self, directory: str | Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "nodes.jsonl").open("w", encoding="utf-8") as f:
            for row in self.conn.execute("SELECT * FROM nodes ORDER BY id"):
                f.write(json.dumps(_unpack(row), ensure_ascii=False, sort_keys=True) + "\n")
        with (directory / "edges.jsonl").open("w", encoding="utf-8") as f:
            for row in self.conn.execute("SELECT * FROM edges ORDER BY id"):
                item = dict(row)
                item["props"] = json.loads(item.get("props") or "{}")
                f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
