"""Freeze the holdout design, candidate identity, and all inputs before calls."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
CAND = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10"
RUNNER = ROOT / "06_TOOLS/EXPERIMENTS/adr_0482/run_holdout.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def stages():
    return [
        {"stage_id": "discovered", "kind": "source", "parent_stage_ids": []},
        {"stage_id": "read", "kind": "retrieve", "parent_stage_ids": ["discovered"]},
        {"stage_id": "presented", "kind": "present", "parent_stage_ids": ["read"]},
        {"stage_id": "selected", "kind": "select", "parent_stage_ids": ["presented"]},
        {"stage_id": "answer", "kind": "present", "parent_stage_ids": ["selected"]},
    ]


def main():
    target = ADR / "artifacts/frozen-design.json"
    if target.exists():
        raise RuntimeError("Design already frozen")
    manifest = json.loads((ADR / "실험/manifest.json").read_text())
    product = json.loads((ADR / "product-cases.json").read_text())
    generation = ROOT / product["generation"]
    source = json.loads((generation / "manifest.json").read_text())
    candidate = json.loads((CAND / "candidate.json").read_text())
    revision = next(row for row in candidate["revisions"] if row["revision_id"] == "rev-001")
    paths = [
        ADR / "PLAN.md", ADR / "product-cases.json", ADR / "gold-cases.json",
        CAND / "candidate.json", generation / "manifest.json",
        ROOT / "00_SYSTEM/EXPERIMENT_MODEL_POLICY.json", ROOT / "00_SYSTEM/PIPELINE.json",
        RUNNER, ROOT / "02_BACKEND/lawrag/research/experiment_client.py",
    ]
    design = {
        "schema_version": "adr0482-frozen-design-v1",
        "model": "gemini-3.1-flash-lite",
        "arms": ["baseline", "source-first"],
        "selection_rule": "All ten sealed FSC hard cases; no exclusions.",
        "success_criteria": {
            "candidate_correct_min": 7,
            "paired_delta_min": 2,
            "regressions_max": 1,
            "candidate_gold_presented_recall_min": 0.8,
            "errors_per_arm_max": 1,
            "calls_per_case_max": 14,
            "wall_seconds_per_case_max": 300,
            "gold_leakage_max": 0,
        },
        "limits": {"model_calls_per_case_arm": 14, "tool_actions": 56, "wall_seconds": 300, "context_chars": 60000, "output_tokens": 2800},
        "order": "case ID; even index baseline first, odd source-first first",
        "stage_plan": {"baseline": stages(), "source-first": stages()},
        "source_store_sha256": source["store_sha256"],
        "scope_document_count": len(product["public_scope_document_ids"]),
        "gold_forbidden_until": "artifacts/run-001/results.json exists and contains all 20 product executions",
        "file_hashes": {str(path.relative_to(ROOT)): sha(path) for path in paths},
    }
    write(target, design)
    manifest["lineage"]["hypothesis_delta"] = "Replace document-navigation-v1 with the latest frozen source-first legal RAG on a CM-independent FSC hard holdout."
    manifest["design"].update(
        hypothesis="Source-first improves semantic correctness by at least 2/10 without more than one regression and preserves decisive-source recall.",
        primary_metric="Blind paired semantic correctness on all ten FSC hard cases",
        success_criteria=json.dumps(design["success_criteria"], ensure_ascii=False, sort_keys=True),
        failure_criteria="Any frozen threshold missed, gold leakage, stale hash, or budget breach.",
        criteria_frozen_before_run=True,
    )
    manifest["design"]["arms"][0].update(
        changes="Frozen document-navigation-v1 baseline.",
        controls="Same source-first snapshot base, generation, scope, Gemini model, limits and questions.",
    )
    manifest["design"]["arms"][1].update(
        changes="Frozen source-first action-feedback and bounded-linked-evidence path.",
        controls="Same snapshot base, generation, scope, Gemini model, limits and questions; no reviewed per-case coordinates.",
    )
    manifest["design"]["retrieval_stage_plan"]["stages_by_arm"] = design["stage_plan"]
    manifest["design"]["code_isolation"].update(
        mode="candidate_snapshot",
        reason=None,
        candidates=[{
            "candidate_id": "source-first-fsc-hard10",
            "experiment_id": manifest["experiment_id"],
            "arm_id": "source-first",
            "run_ids": ["run-001"],
            "manifest_path": str((CAND / "candidate.json").relative_to(ROOT)),
            "manifest_sha256": sha(CAND / "candidate.json"),
            "revision_id": revision["revision_id"],
            "revision_sha256": revision["revision_sha256"],
            "runner_path": str(RUNNER.relative_to(ROOT)),
            "runner_sha256": sha(RUNNER),
        }],
    )
    manifest["runs"][0].update(
        selection_rule=design["selection_rule"],
        artifact_path="04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout/artifacts/run-001/results.json",
    )
    manifest["dataset"].update(
        name="FSC hard-10 CM-independent holdout",
        version="adr0114-sealed-fsc-hard10",
        frozen_source=str((ADR / "product-cases.json").relative_to(ROOT)),
        sha256=sha(ADR / "product-cases.json"),
        legal_version_checked=False,
        reference_version_checked=True,
    )
    manifest["retrieval_accounting"].update(changed=True, not_applicable_reason=None)
    manifest["retrieval_accounting"]["stage_ledger"].update(mode="measured", not_applicable_reason=None)
    write(ADR / "실험/manifest.json", manifest)
    print("Design frozen before product or judge calls")


if __name__ == "__main__":
    main()
