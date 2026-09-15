#!/usr/bin/env python3
"""동일 입력의 Haiku 관계 산출물을 재검증하고 다중-pass 합의를 감사한다."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import itertools
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Callable


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.research.experiments.haiku_source_relations import (  # noqa: E402
    validate_relations,
)


def normalize_surface(value: str) -> str:
    """공백·문장부호·Unicode 차이만 접어 의미적 actor 합병을 피한다."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", normalized)


def _coordinate(item: dict[str, Any]) -> tuple[str, ...]:
    return (
        normalize_surface(item.get("document", "")),
        normalize_surface(item.get("path", "")),
        str(item.get("document_revision") or ""),
        str(item.get("document_enforcement") or ""),
        str(bool(item.get("document_current", True))),
    )


def relation_fingerprint(relation: dict[str, Any],
                         inventory: list[dict[str, Any]], *,
                         normalized: bool = False) -> tuple[str, ...]:
    by_id = {str(row.get("evidence_id") or ""): row for row in inventory}
    source = _coordinate(by_id.get(str(relation.get("source_id") or ""), {}))
    target_id = str(relation.get("target_id") or "")
    target = _coordinate(by_id.get(target_id, {})) if target_id else ("",) * 5
    surface: Callable[[str], str] = normalize_surface if normalized else str
    return (
        str(relation.get("relation_type") or ""),
        *source,
        *target,
        surface(str(relation.get("target_value") or "").strip()),
        surface(str(relation.get("defined_term") or "").strip()),
    )


def _proof_cards(relation: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for quote in relation.get("proof_quotes") or []:
        cards.append({
            "quote_id": str(quote.get("quote_id") or ""),
            "evidence_id": str(quote.get("evidence_id") or ""),
            "kind": str(quote.get("kind") or ""),
            "text": str(quote.get("text") or ""),
        })
    return cards


def revalidate_candidate(relation: dict[str, Any],
                         inventory: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = {key: value for key, value in relation.items()
                 if key not in {"proof_quotes", "validation_errors"}}
    return validate_relations(
        {"relations": [candidate]}, inventory, _proof_cards(relation))


def _path(row: dict[str, Any], evidence_id: str) -> str:
    return str(next((item.get("path") for item in row.get("inventory") or []
                     if item.get("evidence_id") == evidence_id), ""))


def sentinel_results(relations: list[dict[str, Any]]) -> dict[str, bool]:
    false_exception = any(
        rel.get("case_no") == "cm-009"
        and rel.get("relation_type") == "EXCEPTION_TO"
        and "제16조" in rel.get("source_path", "")
        and "제13조" in rel.get("target_path", "")
        for rel in relations)
    cm036_actor = any(
        rel.get("case_no") == "cm-036"
        and rel.get("relation_type") == "GOVERNS_ACTOR"
        and "제8조" in rel.get("source_path", "")
        and any(value in str(rel.get("target_value") or "")
                for value in ("대표자", "상근이사", "업무를 집행"))
        for rel in relations)
    fake_version = any(
        rel.get("case_no") == "cm-045"
        and rel.get("relation_type") == "CURRENT_VERSION_OF"
        for rel in relations)
    return {
        "cm009_no_false_exception_16_to_13": not false_exception,
        "cm036_internal_control_actor_created": cm036_actor,
        "cm045_no_fake_current_version_relation": not fake_version,
    }


def _json_fingerprint(value: tuple[str, ...]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _aggregate(pass_rows: list[dict[str, Any]], *, normalized: bool,
               threshold: int) -> dict[str, Any]:
    appearances: dict[tuple[str, ...], dict[str, Any]] = {}
    per_pass: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for row in pass_rows:
        pass_name = row["pass_name"]
        fingerprint = relation_fingerprint(
            row["relation"], row["inventory"], normalized=normalized)
        per_pass[pass_name].add(fingerprint)
        item = appearances.setdefault(fingerprint, {
            "fingerprint": fingerprint, "passes": set(), "cases": set(),
            "representatives": [],
        })
        item["passes"].add(pass_name)
        item["cases"].add(row["case_no"])
        representative = {
            "case_no": row["case_no"], **row["relation"],
            "source_path": _path(row, str(row["relation"].get("source_id") or "")),
            "target_path": _path(row, str(row["relation"].get("target_id") or "")),
        }
        item["representatives"].append(representative)

    pass_names = sorted(per_pass)
    policies = {
        "union": [item for item in appearances.values() if item["passes"]],
        f"consensus_{threshold}_of_{len(pass_names)}": [
            item for item in appearances.values() if len(item["passes"]) >= threshold],
        "intersection": [item for item in appearances.values()
                         if len(item["passes"]) == len(pass_names)],
    }
    policy_summary = {}
    for name, values in policies.items():
        representatives = [item["representatives"][0] for item in values]
        all_occurrences = [representative for item in values
                           for representative in item["representatives"]]
        policy_summary[name] = {
            "unique_relations": len(values),
            "relation_types": dict(sorted(Counter(
                rel.get("relation_type", "") for rel in representatives).items())),
            "sentinels": sentinel_results(all_occurrences),
        }

    pairs = []
    for left, right in itertools.combinations(pass_names, 2):
        union = per_pass[left] | per_pass[right]
        intersection = per_pass[left] & per_pass[right]
        pairs.append({
            "left": left, "right": right,
            "left_count": len(per_pass[left]), "right_count": len(per_pass[right]),
            "intersection": len(intersection), "union": len(union),
            "jaccard": round(len(intersection) / len(union), 6) if union else 1.0,
        })

    type_stability = {}
    relation_types = sorted({fingerprint[0] for fingerprint in appearances})
    for relation_type in relation_types:
        typed = [item for key, item in appearances.items()
                 if key[0] == relation_type]
        histogram = Counter(len(item["passes"]) for item in typed)
        type_stability[relation_type] = {
            "union": len(typed),
            f"support_at_least_{threshold}": sum(
                count for support, count in histogram.items() if support >= threshold),
            "intersection": histogram.get(len(pass_names), 0),
            "support_histogram": {str(key): value
                                  for key, value in sorted(histogram.items())},
        }

    consensus_rows = []
    consensus_name = f"consensus_{threshold}_of_{len(pass_names)}"
    for item in policies[consensus_name]:
        consensus_rows.append({
            "fingerprint": _json_fingerprint(item["fingerprint"]),
            "support_count": len(item["passes"]),
            "passes": sorted(item["passes"]), "cases": sorted(item["cases"]),
            "representative": item["representatives"][0],
        })
    return {
        "policies": policy_summary,
        "pairwise_jaccard": pairs,
        "type_stability": type_stability,
        "consensus_relations": consensus_rows,
    }


def audit_artifacts(paths: list[Path], *, threshold: int = 2) -> dict[str, Any]:
    if len(paths) < 2:
        raise ValueError("at least two pass artifacts are required")
    if not 2 <= threshold <= len(paths):
        raise ValueError("consensus threshold must be between 2 and N")
    artifacts = [(path.stem, json.loads(path.read_text("utf-8"))) for path in paths]
    hashes: dict[str, dict[str, str]] = defaultdict(dict)
    pass_rows, pass_audits = [], []
    total_usage = Counter()
    all_cases = set()
    contract_ok = True
    row_models_haiku = True
    for pass_name, artifact in artifacts:
        contract = artifact.get("contract") or {}
        contract_ok = contract_ok and (
            contract.get("all_models") == HAIKU_MODEL
            and contract.get("question_in_product_input") is False
            and contract.get("gold_in_product_input") is False
            and contract.get("reference_answer_in_product_input") is False)
        audit = Counter()
        for row in artifact.get("rows") or []:
            row_models_haiku = row_models_haiku and row.get("model") == HAIKU_MODEL
            case_no = str(row.get("case_no") or "")
            all_cases.add(case_no)
            hashes[case_no][pass_name] = str(row.get("product_input_sha256") or "")
            audit["artifact_published"] += len(row.get("published") or [])
            audit["artifact_rejected"] += len(row.get("rejected") or [])
            for relation in [*(row.get("published") or []),
                             *(row.get("rejected") or [])]:
                audit["candidates_revalidated"] += 1
                validation = revalidate_candidate(
                    relation, list(row.get("inventory") or []))
                if validation["published"]:
                    audit["current_validator_published"] += 1
                    pass_rows.append({
                        "pass_name": pass_name, "case_no": case_no,
                        "inventory": list(row.get("inventory") or []),
                        "relation": validation["published"][0],
                    })
                else:
                    audit["current_validator_rejected"] += 1
        usage = dict(((artifact.get("summary") or {}).get("usage") or {}))
        for name in ("calls", "input_tokens", "output_tokens", "duration_ms", "errors"):
            total_usage[name] += int(usage.get(name) or 0)
        pass_audits.append({"pass_name": pass_name, **dict(audit), "usage": usage})

    input_hashes_match = all(
        len(values) == len(paths) and len(set(values.values())) == 1
        and bool(next(iter(values.values()), ""))
        for case_no, values in hashes.items() if case_no)
    same_case_set = all(
        {str(row.get("case_no") or "") for row in artifact.get("rows") or []}
        == all_cases for _, artifact in artifacts)
    exact = _aggregate(pass_rows, normalized=False, threshold=threshold)
    normalized = _aggregate(pass_rows, normalized=True, threshold=threshold)
    contract_checks_pass = bool(
        contract_ok and row_models_haiku and same_case_set and input_hashes_match)
    return {
        "experiment": "haiku-source-relations-multipass-consensus-v1",
        "contract": {
            "all_models": HAIKU_MODEL,
            "source_artifact_contracts_valid": contract_ok,
            "all_row_models_haiku": row_models_haiku,
            "same_case_set": same_case_set,
            "same_product_input_sha256_per_case": input_hashes_match,
            "current_validator_reapplied": True,
            "main_wiring_changed": False,
            "canonical_changed": False,
        },
        "all_contract_checks_pass": contract_checks_pass,
        "inputs": [str(path) for path in paths],
        "passes": len(paths), "consensus_threshold": threshold,
        "case_hashes": {case: values for case, values in sorted(hashes.items())},
        "pass_audits": pass_audits,
        "total_usage": dict(total_usage),
        "exact": exact, "normalized": normalized,
        "normalization_effect": {
            policy: {
                "exact": exact["policies"][policy]["unique_relations"],
                "normalized": normalized["policies"][policy]["unique_relations"],
            }
            for policy in exact["policies"]
        },
        "recommended_storage_policy": {
            "stable": f"support={len(paths)}/{len(paths)}",
            "corroborated": (f"support={threshold}..{len(paths) - 1}/{len(paths)}"
                              if threshold < len(paths) else "same as stable"),
            "shadow_only": f"support<{threshold}/{len(paths)}",
            "union_publish": False,
            "reason": ("union의 단일-pass 관계는 재현성이 없고, intersection은 "
                       "EXCEPTION_TO와 IMPLEMENTS를 모두 잃는다."),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=2)
    args = parser.parse_args()
    result = audit_artifacts(args.inputs, threshold=args.threshold)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        "utf-8")
    summary = {
        "contract": result["contract"],
        "pass_audits": result["pass_audits"],
        "exact_policies": result["exact"]["policies"],
        "normalized_policies": result["normalized"]["policies"],
        "exact_pairwise": result["exact"]["pairwise_jaccard"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if result["all_contract_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
