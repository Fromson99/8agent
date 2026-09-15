#!/usr/bin/env python3
"""Regrade immutable ADR outputs against CM/FSC v2 without rerunning retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from workspace_paths import resolve_stored_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
CM = ROOT / "01_DATA/review/cm_core_e2e_v2.json"
FSC = ROOT / "01_DATA/review/fsc_hard_retrieval_v2.json"
INPUT_LOCK = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0088-corrected-golden-impact-regrade/artifacts/input-lock.json"
DEFAULT_OUTPUT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0088-corrected-golden-impact-regrade/artifacts/run-001.json"

RETRIEVAL_ARTIFACTS = {
    "ADR-0061": "docs/adr/ADR-0061-fsc-hard-top20-retrieval/artifacts/run-001.json",
    "ADR-0064": "docs/adr/ADR-0064-feedback-explore-golden-61/artifacts/run-001.json",
    "ADR-0066": "docs/adr/ADR-0066-proof-guided-span-feedback/artifacts/run-007.json",
    "ADR-0067": "docs/adr/ADR-0067-proof-boundary-feedback/artifacts/run-001.json",
    "ADR-0068": "docs/adr/ADR-0068-recall-first-orthogonal-union/artifacts/run-001.json",
    "ADR-0069": "docs/adr/ADR-0069-source-registry-admission/artifacts/run-001.json",
    "ADR-0070": "docs/adr/ADR-0070-claim-citation-relevance-selector/artifacts/run-001.json",
    "ADR-0071": "docs/adr/ADR-0071-verified-span-id-selector/artifacts/run-001.json",
    "ADR-0072": "docs/adr/ADR-0072-provider-compatible-span-id-selector/artifacts/run-001.json",
    "ADR-0073": "docs/adr/ADR-0073-proof-contribution-basis-exchange/artifacts/run-001.json",
    "ADR-0076": "docs/adr/ADR-0076-bounded-global-augmenting-basis/artifacts/run-001.json",
    "ADR-0078": "docs/adr/ADR-0078-verified-span-coverage-explore-gate/artifacts/run-002.json",
}

ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _article_from_selected(item: dict[str, Any]) -> str | None:
    for field in ("article", "path", "text", "body"):
        matches = ARTICLE_RE.findall(str(item.get(field) or ""))
        if matches:
            return _norm(matches[-1])
    return None


def _coord_from_selected(item: dict[str, Any]) -> tuple[str, str] | None:
    law = _norm(item.get("doc") or item.get("law"))
    article = _article_from_selected(item)
    if not law or not article:
        return None
    return law, article


def _gold_coord(item: dict[str, Any]) -> tuple[str, str]:
    return _norm(item["law"]), _norm(item["article"])


def _gold_cases() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cm = _load(CM)
    fsc = _load(FSC)
    cases: dict[str, dict[str, Any]] = {}
    for case in cm["cases"]:
        cases[case["id"]] = {
            "dataset": "cm",
            "decisive": case["expected_articles"],
            "companions": case.get("required_companions", []),
            "answer_time": [],
        }
    for case in fsc["cases"]:
        cases[case["id"]] = {
            "dataset": "fsc",
            "decisive": case["current_articles"],
            "companions": [],
            "answer_time": case["answer_time_articles"],
        }
    contract = {
        "cases": len(cases),
        "decisive_instances": sum(len(v["decisive"]) for v in cases.values()),
        "companion_instances": sum(len(v["companions"]) for v in cases.values()),
        "answer_time_instances": sum(len(v["answer_time"]) for v in cases.values()),
    }
    return cases, contract


def _selected_by_arm(row: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if "arms" not in row:
        return {"baseline": list(row.get("selected", []))}
    result: dict[str, list[dict[str, Any]]] = {}
    for arm, payload in row["arms"].items():
        result[arm] = list(payload.get("selected", []))
    return result


def _score_artifact(adr_id: str, path: Path, gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    data = _load(path)
    arm_rows: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}
    for row in data["rows"]:
        case_id = row["case_id"]
        if case_id not in gold:
            continue
        for arm, selected in _selected_by_arm(row).items():
            arm_rows.setdefault(arm, []).append((case_id, selected[:20]))

    arms: dict[str, Any] = {}
    for arm, rows in arm_rows.items():
        article_total = article_hits = case_hits = 0
        companion_total = companion_hits = 0
        answer_time_total = answer_time_hits = 0
        misses: list[dict[str, Any]] = []
        for case_id, selected in rows:
            selected_coords = {c for item in selected if (c := _coord_from_selected(item))}
            selected_versions = {
                (_norm(item.get("doc") or item.get("law")), _article_from_selected(item), str(item.get("doc_id") or ""))
                for item in selected
                if _article_from_selected(item)
            }
            decisive = gold[case_id]["decisive"]
            decisive_coords = [_gold_coord(item) for item in decisive]
            hit_flags = [coord in selected_coords for coord in decisive_coords]
            article_total += len(hit_flags)
            article_hits += sum(hit_flags)
            case_hits += int(all(hit_flags))
            for item, hit in zip(decisive, hit_flags):
                if not hit:
                    misses.append({"case_id": case_id, "law": item["law"], "article": item["article"]})

            companions = gold[case_id]["companions"]
            companion_total += len(companions)
            companion_hits += sum(_gold_coord(item) in selected_coords for item in companions)

            answer_time = gold[case_id]["answer_time"]
            answer_time_total += len(answer_time)
            answer_time_hits += sum(
                (_norm(item["law"]), _norm(item["article"]), str(item["doc_id"])) in selected_versions
                for item in answer_time
            )

        cases = len(rows)
        arms[arm] = {
            "cases": cases,
            "case_all_gold_hits": case_hits,
            "case_all_gold_recall_at_20": round(case_hits / cases, 6) if cases else None,
            "decisive_article_hits": article_hits,
            "decisive_article_instances": article_total,
            "decisive_article_recall_at_20": round(article_hits / article_total, 6) if article_total else None,
            "required_companion_hits": companion_hits,
            "required_companion_instances": companion_total,
            "required_companion_recall_at_20": round(companion_hits / companion_total, 6) if companion_total else None,
            "answer_time_exact_version_hits": answer_time_hits,
            "answer_time_instances": answer_time_total,
            "answer_time_exact_version_recall_at_20": round(answer_time_hits / answer_time_total, 6) if answer_time_total else None,
            "misses": misses,
        }
    return {
        "adr_id": adr_id,
        "source_artifact": str(path.relative_to(ROOT)),
        "source_sha256": _sha(path),
        "original_summary": data.get("summary", {}),
        "arms": arms,
    }


def _strata_regrade(gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    path = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0083-golden-question-surface-strata/artifacts/run-001.json"
    data = _load(path)
    result: dict[str, Any] = {"source_artifact": str(path.relative_to(ROOT)), "source_sha256": _sha(path)}
    for view in ("source_question_view", "runtime_question_view"):
        counts: dict[str, dict[str, int]] = {}
        for row in data["rows"]:
            label = row[view]["label"]
            bucket = counts.setdefault(label, {"cases": 0, "decisive_instances": 0})
            bucket["cases"] += 1
            bucket["decisive_instances"] += len(gold[row["case_id"]]["decisive"])
        result[view] = counts
    return result


def _semantic_seed_audit(gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    path = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0085-semantic-operation-seed-golden-10/artifacts/run-001.json"
    data = _load(path)
    semantic_matches = exact_matches = 0
    stale: list[dict[str, Any]] = []
    for row in data["rows"]:
        case_id = row["source_case_id"]
        current = gold[case_id]["decisive"]
        by_coord = {_gold_coord(item): item for item in current}
        for receipt in row["coordinate_receipt"]:
            coord = _gold_coord(receipt)
            target = by_coord.get(coord)
            if target is None:
                stale.append({"case_id": case_id, "coordinate": list(coord), "reason": "semantic-coordinate-removed"})
                continue
            semantic_matches += 1
            if str(receipt.get("doc_id")) == str(target.get("doc_id")) and str(receipt.get("node")) == str(target.get("node")):
                exact_matches += 1
            else:
                stale.append({
                    "case_id": case_id,
                    "law": target["law"],
                    "article": target["article"],
                    "old_doc_id": receipt.get("doc_id"),
                    "old_node": receipt.get("node"),
                    "current_doc_id": target.get("doc_id"),
                    "current_node": target.get("node"),
                    "reason": "same-legal-coordinate-stale-document-version",
                })
    return {
        "source_artifact": str(path.relative_to(ROOT)),
        "source_sha256": _sha(path),
        "coordinates": sum(len(row["coordinate_receipt"]) for row in data["rows"]),
        "semantic_coordinate_matches": semantic_matches,
        "exact_current_doc_node_matches": exact_matches,
        "stale_coordinates": stale,
    }


def build() -> dict[str, Any]:
    lock = _load(INPUT_LOCK)
    if _sha(CM) != lock["golden"][0]["sha256"] or _sha(FSC) != lock["golden"][1]["sha256"]:
        raise RuntimeError("golden source hash changed after freeze")
    for record in lock["impacted_adrs"]:
        if _sha(resolve_stored_path(ROOT, record["artifact"])) != record["sha256"]:
            raise RuntimeError(f"frozen ADR artifact changed: {record['artifact']}")

    gold, denominator = _gold_cases()
    retrieval = [
        _score_artifact(adr_id, resolve_stored_path(ROOT, rel), gold)
        for adr_id, rel in RETRIEVAL_ARTIFACTS.items()
    ]
    impact = [
        {"adr_id": "ADR-0056", "status": "retained", "reason": "reference answers and answer judgments are unchanged; only article-coordinate metadata changed"},
        {"adr_id": "ADR-0061", "status": "retained-with-temporal-qualification", "reason": "current-coordinate FSC recall is regraded; answer-time legal-version recall is a separate metric"},
        *[
            {"adr_id": adr, "status": "numerically-corrected", "reason": "decisive denominator changes from 83 to 90"}
            for adr in ("ADR-0064", "ADR-0066", "ADR-0067", "ADR-0068", "ADR-0069", "ADR-0070", "ADR-0071", "ADR-0072", "ADR-0073", "ADR-0076", "ADR-0078")
        ],
        {"adr_id": "ADR-0074", "status": "invalidated-requires-rerun", "reason": "the audited missing-gold set was derived from the obsolete 83-instance denominator"},
        {"adr_id": "ADR-0082", "status": "superseded", "reason": "its findings are implemented and corrected by ADR-0086"},
        {"adr_id": "ADR-0083", "status": "numerically-corrected", "reason": "case labels remain valid but per-stratum gold-instance denominators change"},
        {"adr_id": "ADR-0084", "status": "superseded", "reason": "its falsified future-effective criterion is corrected by ADR-0086"},
        {"adr_id": "ADR-0085", "status": "coordinate-corrected", "reason": "semantic expected set is unchanged, while one Commercial Act doc/node receipt is stale"},
    ]
    if len({item["adr_id"] for item in impact}) != 18:
        raise AssertionError("impact ledger must classify 18 unique ADRs")
    if denominator != {"cases": 61, "decisive_instances": 90, "companion_instances": 22, "answer_time_instances": 15}:
        raise AssertionError(f"unexpected corrected denominator: {denominator}")
    return {
        "schema_version": "corrected-legal-gold-regrade-v1",
        "adr_id": "ADR-0088",
        "run_id": "run-001",
        "input_lock": str(INPUT_LOCK.relative_to(ROOT)),
        "input_lock_sha256": _sha(INPUT_LOCK),
        "llm_calls": 0,
        "retrieval_calls": 0,
        "grading_contract": lock["matching_contract"],
        "corrected_denominator": denominator,
        "impact_ledger": impact,
        "retrieval_regrades": retrieval,
        "strata_regrade": _strata_regrade(gold),
        "semantic_seed_audit": _semantic_seed_audit(gold),
        "immutability": {
            "cm_v1_sha256": _sha(ROOT / "01_DATA/review/cm_core_e2e_v1.json"),
            "fsc_v1_sha256": _sha(ROOT / "01_DATA/review/fsc_hard_retrieval_v1.json"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "impact_adrs": len(result["impact_ledger"]),
        "retrieval_regrades": len(result["retrieval_regrades"]),
        "denominator": result["corrected_denominator"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
