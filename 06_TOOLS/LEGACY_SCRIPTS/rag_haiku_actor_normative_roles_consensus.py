#!/usr/bin/env python3
"""동일 최종 입력의 actor 규범 역할 두 pass 재현성과 교집합 utility를 감사한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from scripts.rag_haiku_actor_normative_roles_eval import _posthoc_utility  # noqa: E402


def _key(row: dict, item: dict) -> tuple[str, str, str]:
    return (str(row.get("source_artifact") or ""),
            str(row.get("case_no") or ""),
            str(item.get("relation_ref") or ""))


def audit(left: dict, right: dict, retrieval: dict) -> dict:
    left_rows = {(row.get("source_artifact"), row.get("case_no")): row
                 for row in left.get("rows") or []}
    right_rows = {(row.get("source_artifact"), row.get("case_no")): row
                  for row in right.get("rows") or []}
    batches = sorted(set(left_rows) | set(right_rows))
    hashes_match = all(
        (left_rows.get(batch) or {}).get("product_input_sha256")
        == (right_rows.get(batch) or {}).get("product_input_sha256")
        for batch in batches)
    left_roles = {_key(row, item): item for row in left_rows.values()
                  for item in row.get("published") or []}
    right_roles = {_key(row, item): item for row in right_rows.values()
                   for item in row.get("published") or []}
    both = set(left_roles) & set(right_roles)
    same = {key for key in both
            if left_roles[key].get("role") == right_roles[key].get("role")}
    different = both - same
    union = set(left_roles) | set(right_roles)
    consensus_rows = []
    for batch in batches:
        base = left_rows.get(batch) or right_rows[batch]
        published = []
        for item in base.get("menu") or []:
            key = (str(batch[0]), str(batch[1]), str(item.get("relation_ref") or ""))
            if key in same:
                published.append(left_roles[key])
        consensus_rows.append({
            "source_artifact": batch[0], "case_no": batch[1],
            "menu": base.get("menu") or [], "published": published,
        })
    return {
        "experiment": "haiku-actor-normative-role-consensus-audit-v1",
        "contract": {
            "all_models": HAIKU_MODEL, "same_product_input_hashes": hashes_match,
            "question_and_gold_used_only_for_posthoc_utility": True,
            "main_wiring_changed": False, "canonical_changed": False,
        },
        "stability": {
            "input_actor_relations": sum(len(row.get("menu") or [])
                                         for row in left_rows.values()),
            "left_published": len(left_roles), "right_published": len(right_roles),
            "published_union": len(union), "published_intersection": len(both),
            "publication_jaccard": round(len(both) / len(union), 4) if union else 1,
            "same_role_in_both": len(same), "different_role_in_both": len(different),
            "role_agreement_given_both_published": round(
                len(same) / len(both), 4) if both else 1,
            "consensus_role_distribution": dict(sorted(Counter(
                str(left_roles[key].get("role") or "") for key in same).items())),
            "role_disagreements": [{
                "source_artifact": key[0], "case_no": key[1],
                "relation_ref": key[2],
                "actor_surface": left_roles[key].get("actor_surface"),
                "left_role": left_roles[key].get("role"),
                "right_role": right_roles[key].get("role"),
            } for key in sorted(different)],
        },
        "consensus_posthoc_utility": _posthoc_utility(consensus_rows, retrieval),
        "consensus_rows": consensus_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.left.read_text("utf-8")),
                   json.loads(args.right.read_text("utf-8")),
                   json.loads(args.retrieval.read_text("utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps({"stability": result["stability"],
                      "consensus_posthoc_utility": result["consensus_posthoc_utility"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
