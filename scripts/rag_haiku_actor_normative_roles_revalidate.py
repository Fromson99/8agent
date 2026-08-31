#!/usr/bin/env python3
"""기존 Haiku actor-role 후보를 추가 LLM 호출 없이 최신 fail-closed 규칙으로 재검증한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.experiments.haiku_actor_normative_roles import (  # noqa: E402
    validate_actor_roles,
)
from scripts.rag_haiku_actor_normative_roles_eval import (  # noqa: E402
    _posthoc_utility, summarize,
)


def revalidate(artifact: dict, retrieval: dict) -> dict:
    rows = []
    for original in artifact.get("rows") or []:
        menu = list(original.get("menu") or [])
        closed = {str(item.get("relation_ref") or ""): item for item in menu}
        candidates = []
        for item in list(original.get("published") or []) + list(original.get("rejected") or []):
            candidates.append({key: value for key, value in item.items()
                               if key not in {"proof_quote", "validation_errors"}})
        validation = validate_actor_roles({"roles": candidates,
                                           "unresolved_refs": original.get("unresolved_refs") or []},
                                          closed)
        rows.append({**original, "published": validation["published"],
                     "rejected": validation["rejected"],
                     "unresolved_refs": validation["unresolved_refs"],
                     "missing_refs": validation["missing_refs"],
                     "invalid_unresolved_refs": validation["invalid_unresolved_refs"],
                     "coverage_count": validation["coverage_count"]})
    return {**artifact,
            "experiment": "haiku-actor-normative-role-shadow-strict-revalidation-v1",
            "revalidated_from": artifact.get("experiment"),
            "summary": summarize(rows),
            "posthoc_utility": _posthoc_utility(rows, retrieval),
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = revalidate(json.loads(args.input.read_text("utf-8")),
                        json.loads(args.retrieval.read_text("utf-8")))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps({"summary": result["summary"],
                      "posthoc_utility": result["posthoc_utility"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
