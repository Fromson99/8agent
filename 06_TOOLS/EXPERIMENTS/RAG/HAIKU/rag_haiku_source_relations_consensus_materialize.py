#!/usr/bin/env python3
"""consensus 관계를 현재 validator로 재검증한 일반 relation artifact로 만든다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.research.experiments.haiku_source_relations import validate_relations  # noqa: E402


def materialize(consensus: dict, template: dict, *, normalized: bool = False) -> dict:
    branch = consensus["normalized" if normalized else "exact"]
    selected = branch.get("consensus_relations") or []
    by_case = {}
    for item in selected:
        relation = dict(item.get("representative") or {})
        case_no = str(relation.pop("case_no", ""))
        relation.pop("source_path", None)
        relation.pop("target_path", None)
        relation["consensus_support_count"] = int(item.get("support_count") or 0)
        relation["consensus_passes"] = list(item.get("passes") or [])
        by_case.setdefault(case_no, []).append(relation)

    rows = []
    type_counts = Counter()
    for template_row in template.get("rows") or []:
        case_no = str(template_row.get("case_no") or "")
        inventory = list(template_row.get("inventory") or [])
        published, rejected = [], []
        for relation in by_case.get(case_no, []):
            candidate = {key: value for key, value in relation.items()
                         if key not in {"proof_quotes", "validation_errors",
                                       "consensus_support_count", "consensus_passes"}}
            cards = list(relation.get("proof_quotes") or [])
            validation = validate_relations({"relations": [candidate]}, inventory, cards)
            if validation["published"]:
                value = {
                    **validation["published"][0],
                    "consensus_support_count": relation["consensus_support_count"],
                    "consensus_passes": relation["consensus_passes"],
                }
                published.append(value)
                type_counts[str(value.get("relation_type") or "")] += 1
            else:
                rejected.extend(validation["rejected"])
        rows.append({
            "case_no": case_no, "model": HAIKU_MODEL,
            "product_input_sha256": template_row.get("product_input_sha256"),
            "inventory": inventory, "published": published, "rejected": rejected,
            "usage": {}, "wall_ms": 0,
        })
    return {
        "experiment": "haiku-source-relations-consensus-materialized-v1",
        "contract": {
            "all_models": HAIKU_MODEL,
            "source_artifact_contracts_valid": bool(
                consensus.get("all_contract_checks_pass")),
            "question_in_product_input": False,
            "gold_in_product_input": False,
            "reference_answer_in_product_input": False,
            "current_validator_reapplied": True,
            "main_wiring_changed": False, "canonical_changed": False,
        },
        "source_consensus": consensus.get("inputs") or [],
        "summary": {
            "cases": len(rows), "published_relations": sum(
                len(row["published"]) for row in rows),
            "rejected_relations": sum(len(row["rejected"]) for row in rows),
            "published_relation_types": dict(sorted(type_counts.items())),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--consensus", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--normalized", action="store_true")
    args = parser.parse_args()
    result = materialize(
        json.loads(args.consensus.read_text("utf-8")),
        json.loads(args.template.read_text("utf-8")), normalized=args.normalized)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0 if result["summary"]["rejected_relations"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
