#!/usr/bin/env python3
"""동결 v1을 ADR-0082 원장에서 복원하고 현재 마이그레이션본을 v2로 분리한다."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.legal_generation import atomic_json

CM_V1_HASH = "d3e4f658d8c9abb06244557b669d37d63b0e6fcc879059506e3b462619bcc18d"
FSC_V1_HASH = "4373659368de7a81b7e9ee48233c8b317d863db4e5c4827f4346d09281b3d7f8"


def _ordered_gold(row: dict) -> dict:
    return {key: row[key] for key in (
        "law", "article", "doc_id", "document_revision", "document_enforcement",
        "node", "corpus_status") if key in row}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    review = ROOT / "01_DATA/review"
    cm_v1, fsc_v1 = review / "cm_core_e2e_v1.json", review / "fsc_hard_retrieval_v1.json"
    cm_v2, fsc_v2 = review / "cm_core_e2e_v2.json", review / "fsc_hard_retrieval_v2.json"
    cm = json.loads(cm_v1.read_text(encoding="utf-8"))
    fsc = json.loads(fsc_v1.read_text(encoding="utf-8"))
    if cm.get("schema_version") != 3 or fsc.get("schema_version") != 2:
        raise RuntimeError("현재 v1 경로에 migration 결과가 없어 분리할 수 없음")
    atomic_json(cm_v2, cm)
    atomic_json(fsc_v2, fsc)

    audit = json.loads((ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0082-golden-corpus-integrity-audit/artifacts/run-004.json")
                       .read_text(encoding="utf-8"))
    old: dict[str, list[tuple[int, dict]]] = {}
    frozen_material = {row["case_id"]: row["frozen_material"] for row in audit["cases"]}
    for row in audit["gold_coordinates"]:
        old.setdefault(row["case_id"], []).append((int(row["ordinal"]), _ordered_gold(row["gold"])))

    cm["schema_version"], cm["version"], cm["name"] = 2, 1, "cm-field-core-e2e-v1"
    cm.pop("supersedes", None)
    cm.pop("evidence_contract", None)
    for key in ("decisive_article_instances", "required_companion_instances",
                "auxiliary_evidence_items"):
        cm["counts"].pop(key, None)
    cm["grading"]["retrieval"] = "expected_articles의 법령·조문 좌표 회수"
    cm["grading"].pop("companion_closure", None)
    cm["grading"].pop("auxiliary", None)
    for case in cm["cases"]:
        case["expected_articles"] = [row for _n, row in sorted(old[case["id"]])]
        case.pop("required_companions", None)
        case.pop("auxiliary_evidence", None)
        case["material"] = frozen_material[case["id"]]
        case["axes"]["material"] = frozen_material[case["id"]]

    fsc["schema_version"], fsc["version"], fsc["name"] = 1, 1, "fsc-hard-retrieval-v1"
    fsc.pop("supersedes", None)
    fsc.pop("temporal_contract", None)
    for key in ("current_article_instances", "answer_time_article_instances", "historical_documents"):
        fsc["counts"].pop(key, None)
    policy = fsc["selection_policy"]
    rebuilt = {}
    for key, value in policy.items():
        if key == "difficulty_requirements":
            rebuilt["exclude_temporally_drifted_coordinates"] = True
        if key != "temporal_drift_explicitly_split":
            rebuilt[key] = value
    fsc["selection_policy"] = rebuilt
    fsc["grading"]["match_key"] = "doc_id + article root node"
    fsc["grading"].pop("historical_provenance", None)
    for case in fsc["cases"]:
        case["expected_articles"] = [row for _n, row in sorted(old[case["id"]])]
        for key in ("answer_as_of", "answer_time_articles", "current_as_of", "current_articles"):
            case.pop(key, None)

    atomic_json(cm_v1, cm)
    atomic_json(fsc_v1, fsc)
    actual = {"cm": _hash(cm_v1), "fsc": _hash(fsc_v1)}
    expected = {"cm": CM_V1_HASH, "fsc": FSC_V1_HASH}
    if actual != expected:
        raise RuntimeError(f"v1 hash 복원 실패: expected={expected} actual={actual}")
    print(json.dumps({"v1": actual, "v2": {"cm": _hash(cm_v2), "fsc": _hash(fsc_v2)}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
