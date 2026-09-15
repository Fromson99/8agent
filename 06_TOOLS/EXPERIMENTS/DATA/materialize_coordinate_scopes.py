#!/usr/bin/env python3
"""기존 structure result.json에 legal-coordinate-v2를 결정론적으로 물질화한다."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.legal_generation import atomic_json
from lawrag.core.structure.viewer import annotate_coordinate_scopes


def migrate(store: Path) -> dict:
    documents = article_nodes = changed = 0
    scopes: Counter[str] = Counter()
    duplicate_body = []
    duplicate_keys = []
    for directory in sorted(store.iterdir() if store.is_dir() else ()):
        result_path, meta_path = directory / "result.json", directory / "meta.json"
        if not result_path.is_file() or not meta_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        nodes = result.get("nodes") or []
        had_schema = result.get("coordinate_schema_version") == "legal-coordinate-v2"
        before = [(n.get("coordinate_scope"), n.get("coordinate_key"),
                   n.get("legal_coordinate")) for n in nodes]
        annotate_coordinate_scopes(nodes, str(meta.get("kind") or ""))
        after = [(n.get("coordinate_scope"), n.get("coordinate_key"),
                  n.get("legal_coordinate")) for n in nodes]
        result["coordinate_schema_version"] = "legal-coordinate-v2"
        if before != after or not had_schema:
            changed += 1
        atomic_json(result_path, result, indent=None)
        documents += 1
        body_surfaces: Counter[str] = Counter()
        keys: Counter[str] = Counter()
        for node in nodes:
            if not node.get("coordinate_scope"):
                continue
            coordinate = node.get("legal_coordinate") or {}
            if coordinate.get("unit") == "조" and not coordinate.get("chain"):
                article_nodes += 1
            scopes[node["coordinate_scope"]] += 1
            keys[str(node["coordinate_key"])] += 1
            if (node["coordinate_scope"] == "body"
                    and coordinate.get("unit") == "조"
                    and not coordinate.get("chain")):
                body_surfaces[str(coordinate.get("surface") or "")] += 1
        if any(n > 1 for n in body_surfaces.values()):
            duplicate_body.append(directory.name)
        if any(n > 1 for n in keys.values()):
            duplicate_keys.append(directory.name)
    if duplicate_body or duplicate_keys:
        raise RuntimeError({"duplicate_body": duplicate_body,
                            "duplicate_coordinate_keys": duplicate_keys})
    return {"documents": documents, "changed": changed,
            "article_nodes": article_nodes, "scopes": dict(scopes),
            "duplicate_body_documents": 0, "duplicate_coordinate_keys": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=Path("01_DATA/structure"))
    args = parser.parse_args()
    print(json.dumps(migrate(args.store), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
