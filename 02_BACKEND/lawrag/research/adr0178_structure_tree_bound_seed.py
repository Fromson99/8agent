"""Research-only runner for ADR-0178's frozen publication-seed candidate."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from lawrag.platform.active_data import active_structure_path


WORKSPACE = Path(__file__).resolve().parents[3]
CANDIDATE = (
    WORKSPACE
    / "02_BACKEND/lawrag/research/candidates/adr_0178/structure-tree-bound-seed"
    / "revisions/rev-001/snapshot/02_BACKEND/lawrag/datasets/publisher.py"
)


def main() -> int:
    spec = importlib.util.spec_from_file_location("adr0178_candidate_publisher", CANDIDATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate: {CANDIDATE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    structure = active_structure_path(WORKSPACE)
    print(json.dumps({
        "schema_version": "adr0178-candidate-validation-v1",
        "structure_tree_sha256": module.hash_tree(structure),
        "structure_file_count": sum(1 for path in structure.rglob("*") if path.is_file()),
        "external_calls": {"llm": 0, "embedding": 0, "network": 0},
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
