#!/usr/bin/env python3
"""ADR-0095 deterministic replay of the opt-in feedback API recovery helper."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "data/law_index.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.api.routers import rag  # noqa: E402
from lawrag.core.rag import index as index_mod, switches  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0095-feedback-api-role-predicate-recovery"
RUN_ID = "run-002"
PARENT_RUN = ROOT / (
    "docs/adr/ADR-0094-role-predicate-governing-law-feedback-router/"
    "artifacts/run-002.json")
FSC = ROOT / "data/review/fsc_hard_retrieval_v2.json"
MUTABLE_WIRING_PATHS = {
    "lawrag/api/routers/rag.py",
    "lawrag/core/rag/switches.py",
    "lawrag/api/viewer/rag/app.js",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    lock_path = ADR / "artifacts/input-lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    expected_lock = "1b810511e1ab1571253c898a80c3ae200b81e9a83837241fedf1c54de32ec0f0"
    if _sha(lock_path) != expected_lock:
        raise ValueError("input lock hash mismatch")
    for source in lock["sources"]:
        if source["path"] in MUTABLE_WIRING_PATHS:
            continue
        if _sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"frozen source hash mismatch: {source['path']}")

    parent = json.loads(PARENT_RUN.read_text("utf-8"))
    fsc = json.loads(FSC.read_text("utf-8"))
    source_case = next(row for row in fsc["cases"] if row["id"] == "fsc-hard-003")
    baseline = next(row for row in parent["rows"]
                    if row["case_id"] == "fsc-hard-003" and row["arm_id"] == "baseline")
    public_input = {
        "질의": source_case["question"],
        "context": [{"doc_id": doc_id, "node": int(node)}
                    for doc_id, node in baseline["final_coordinates"]],
    }

    index = index_mod.current()
    started = time.perf_counter()
    recovery = rag._role_predicate_feedback_recovery(index, public_input)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    capture = {
        "question": public_input["질의"],
        "feedback": {"verdict": "오답", "expected": None, "note": ""},
        "baseline_coordinates": [
            [row["doc_id"], row["node"]] for row in public_input["context"]],
        "recovery": recovery,
        "gold_visible_to_candidate": False,
    }

    # Exact gold is joined only after the candidate response is fully captured.
    expected = {(str(row["doc_id"]), int(row["node"]))
                for row in source_case["current_articles"]}
    selected = {(str(row["doc_id"]), int(row["node"]))
                for row in recovery["selected"]}
    grade = {
        "expected": [list(value) for value in sorted(expected)],
        "selected": [list(value) for value in sorted(selected)],
        "exact_hits": len(expected & selected),
        "exact_total": len(expected),
        "unexpected": [list(value) for value in sorted(selected - expected)],
        "passed": expected <= selected and not (selected - expected),
    }
    switch_row = next(row for row in switches.REGISTRY
                      if row["key"] == "role_predicate_feedback_recovery")
    artifact = {
        "schema_version": "adr-run-v1",
        "adr_id": "ADR-0095",
        "experiment_id": "ADR-0095-experiment-v1",
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_lock_sha256": expected_lock,
        "arm_id": "feedback-api-opt-in",
        "capture": capture,
        "grade": grade,
        "controls": {
            "switch_default": switch_row.get("기본"),
            "main_retrieval_changed": False,
            "prior_answer_replaced": False,
            "addition_cap": recovery.get("audit", {}).get("caps", {}).get("additions"),
            "general_lexical_search_calls": recovery.get("audit", {}).get(
                "general_lexical_search_calls"),
            "forbidden_fields_used": recovery.get("audit", {}).get(
                "forbidden_fields_used"),
        },
        "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0},
        "latency": {"elapsed_ms": elapsed_ms},
        "code_hashes": {
            path: _sha(ROOT / path) for path in sorted(MUTABLE_WIRING_PATHS | {
                "lawrag/core/rag/companion_recovery.py",
                "scripts/rag_feedback_api_wiring_probe.py",
                "tests/rag/test_feedback_api_recovery.py",
            })
        },
    }
    output = ADR / f"artifacts/{RUN_ID}.json"
    output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "artifact": str(output.relative_to(ROOT)),
        "exact_hits": grade["exact_hits"],
        "exact_total": grade["exact_total"],
        "unexpected": len(grade["unexpected"]),
        "switch_default": switch_row.get("기본"),
        "elapsed_ms": elapsed_ms,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
