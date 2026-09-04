#!/usr/bin/env python3
"""Build the frozen 10-case semantic-operation-seed challenge suite.

The builder is deterministic and lineage-preserving.  It changes only the
runtime question; reference answers and expected article coordinates are copied
from hash-frozen real CM/FSC cases.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
ADR_ID = "ADR-0085"
EXPERIMENT_ID = "ADR-0085-experiment-v1"
RUN_ID = "run-001"
MANIFEST = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0085-semantic-operation-seed-golden-10/실험/manifest.json"
ARTIFACT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0085-semantic-operation-seed-golden-10/artifacts/run-001.json"
OUTPUT = ROOT / "01_DATA/review/semantic_operation_seed_v1.json"
CM_PATH = ROOT / "01_DATA/review/cm_core_e2e_v1.json"
FSC_PATH = ROOT / "01_DATA/review/fsc_hard_retrieval_v1.json"
CM_SHA256 = "d3e4f658d8c9abb06244557b669d37d63b0e6fcc879059506e3b462619bcc18d"
FSC_SHA256 = "4373659368de7a81b7e9ee48233c8b317d863db4e5c4827f4346d09281b3d7f8"
COMBINED_SHA256 = "05936e4bee0ae42a90c3d20a83ff40af2bb5b47895f1702d2716b18dd82f203e"
ARTICLE_RE = re.compile(r"(?<![0-9A-Za-z가-힣])제\s*\d+(?:\s*-\s*\d+)?\s*(?:조(?:의\s*\d+)?|항|호)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _combined_source_sha256() -> str:
    return hashlib.sha256(CM_PATH.read_bytes() + b"\0" + FSC_PATH.read_bytes()).hexdigest()


def _load_sources() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    actual = {
        "cm": _sha256(CM_PATH),
        "fsc-hard": _sha256(FSC_PATH),
        "combined": _combined_source_sha256(),
    }
    expected = {"cm": CM_SHA256, "fsc-hard": FSC_SHA256, "combined": COMBINED_SHA256}
    if actual != expected:
        raise ValueError(f"frozen source hash mismatch: expected={expected} actual={actual}")
    rows: dict[str, dict[str, Any]] = {}
    for dataset, path in (("cm", CM_PATH), ("fsc-hard", FSC_PATH)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("cases") or ():
            row = copy.deepcopy(raw)
            case_id = str(row.get("id") or "")
            if not case_id or case_id in rows:
                raise ValueError(f"invalid or duplicate source case id: {case_id!r}")
            row["_source_dataset"] = dataset
            rows[case_id] = row
    return rows, actual


def _authority_evidence(question: str, expected_articles: Sequence[Mapping[str, Any]]) -> list[str]:
    evidence = [match.group(0) for match in ARTICLE_RE.finditer(question)]
    for article in expected_articles:
        law = str(article.get("law") or "")
        if law and law in question:
            evidence.append(law)
    return list(dict.fromkeys(evidence))


def _coordinate_receipt(expected_articles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    receipt: list[dict[str, Any]] = []
    for expected in expected_articles:
        doc_id = str(expected.get("doc_id") or "")
        node_id = str(expected.get("node") or "")
        result_path = ROOT / "01_DATA/structure" / doc_id / "result.json"
        meta_path = result_path.with_name("meta.json")
        if not result_path.is_file() or not meta_path.is_file():
            raise ValueError(f"missing structure coordinate document: {doc_id}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        matches = [node for node in result.get("nodes") or () if str(node.get("id")) == node_id]
        if len(matches) != 1:
            raise ValueError(f"coordinate node mismatch: {doc_id}/{node_id}")
        node = matches[0]
        if str(node.get("surface") or "") != str(expected.get("article") or ""):
            raise ValueError(
                f"coordinate article mismatch: {doc_id}/{node_id}: "
                f"{node.get('surface')!r} != {expected.get('article')!r}"
            )
        if str(meta.get("name") or "") != str(expected.get("law") or ""):
            raise ValueError(
                f"coordinate law mismatch: {doc_id}: "
                f"{meta.get('name')!r} != {expected.get('law')!r}"
            )
        receipt.append(
            {
                "law": expected["law"],
                "article": expected["article"],
                "doc_id": doc_id,
                "node": node_id,
                "status": "exact",
            }
        )
    return receipt


def _validate_manifest(path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    if not expected_sha256 or expected_sha256 == "PENDING":
        raise ValueError("a frozen manifest SHA-256 is required")
    actual_sha = _sha256(path)
    if actual_sha != expected_sha256:
        raise ValueError(f"manifest hash mismatch: expected={expected_sha256} actual={actual_sha}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("ADR or experiment id mismatch")
    design = manifest.get("design") or {}
    contract = design.get("construction_contract") or {}
    if design.get("criteria_frozen_before_run") is not True:
        raise ValueError("criteria are not frozen")
    if contract.get("schema_version") != "semantic-operation-seed-golden-v1":
        raise ValueError("construction contract mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
        raise ValueError("this builder must declare zero LLM calls")
    stage = (manifest.get("retrieval_accounting") or {}).get("stage_ledger") or {}
    if stage.get("mode") != "not_applicable":
        raise ValueError("retrieval stage mode must be not_applicable")
    run = next((row for row in manifest.get("runs") or () if row.get("id") == RUN_ID), None)
    if not run or run.get("status") not in {"planned", "running", "complete"}:
        raise ValueError("run-001 is not executable")
    if run.get("runner_sha256") != _sha256(Path(__file__).resolve()):
        raise ValueError("runner hash mismatch")
    frozen_tests = run.get("test_sha256") or {}
    if not frozen_tests or "PENDING" in frozen_tests.values():
        raise ValueError("test hash gate is missing")
    for relative, digest in frozen_tests.items():
        candidate = (ROOT / str(relative)).resolve()
        if ROOT != candidate and ROOT not in candidate.parents:
            raise ValueError("test hash path escapes repository")
        if not candidate.is_file() or _sha256(candidate) != digest:
            raise ValueError(f"test hash mismatch: {relative}")
    return manifest, actual_sha


def build_suite(manifest: Mapping[str, Any], *, manifest_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sources, source_hashes = _load_sources()
    contract = ((manifest.get("design") or {}).get("construction_contract") or {})
    specs = list(contract.get("fixed_cases") or ())
    if len(specs) != 10:
        raise ValueError(f"fixed case count mismatch: {len(specs)}")
    source_ids = [str(spec.get("source_id") or "") for spec in specs]
    if source_ids != [
        "cm-008", "cm-012", "cm-015", "cm-021", "cm-024",
        "cm-038", "cm-048", "cm-050", "cm-051", "fsc-hard-003",
    ]:
        raise ValueError(f"source selection/order drift: {source_ids}")

    cases: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for spec in specs:
        case_id = str(spec["id"])
        source_id = str(spec["source_id"])
        question = str(spec["question"])
        canonical_terms = [str(value) for value in spec.get("canonical_terms") or ()]
        source = sources.get(source_id)
        if source is None:
            raise ValueError(f"missing source case: {source_id}")
        expected_articles = copy.deepcopy(source.get("expected_articles") or [])
        if not expected_articles:
            raise ValueError(f"source case has no expected articles: {source_id}")
        authority_evidence = _authority_evidence(question, expected_articles)
        canonical_evidence = [term for term in canonical_terms if term and term in question]
        if authority_evidence or canonical_evidence:
            raise ValueError(
                f"surface leakage in {case_id}: authority={authority_evidence} "
                f"canonical={canonical_evidence}"
            )
        if "업무 문맥" in question or not question.endswith("?") or len(question) < 30:
            raise ValueError(f"question is not a standalone runtime prompt: {case_id}")
        coordinate_receipt = _coordinate_receipt(expected_articles)
        source_dataset = str(source["_source_dataset"])
        source_path = CM_PATH if source_dataset == "cm" else FSC_PATH
        source_question = str(source.get("source_question") or source.get("question") or "")
        reference_answer = str(source.get("reference_answer") or "")
        if not reference_answer:
            raise ValueError(f"missing source reference answer: {source_id}")
        source_reference_sha = str(source.get("reference_sha256") or "") or _text_sha256(
            source_question + "\n" + reference_answer
        )
        axes = copy.deepcopy(source.get("axes") or {})
        axes.update(
            {
                "difficulty": "hard",
                "surface_signal": "runtime_latent_only",
                "legal_operation": "semantic_operation_seed",
                "provenance": "actual_case_fact_preserving_transform",
                "in_sample": True,
            }
        )
        case = {
            "id": case_id,
            "question": question,
            "reference_answer": reference_answer,
            "reference_answer_sha256": _text_sha256(reference_answer),
            "expected_articles": expected_articles,
            "axes": axes,
            "surface_audit": {
                "authority_evidence": authority_evidence,
                "canonical_terms": canonical_terms,
                "canonical_term_evidence": canonical_evidence,
                "authority_absent": True,
                "canonical_operation_term_absent": True,
                "requires_semantic_operation_seed": True,
            },
            "provenance": {
                "source_dataset": source_dataset,
                "source_path": str(source_path.relative_to(ROOT)),
                "source_sha256": source_hashes[source_dataset],
                "source_case_id": source_id,
                "source_question": source_question,
                "source_runtime_question": str(source.get("question") or source_question),
                "source_reference_sha256": source_reference_sha,
                "source_file": source.get("source_file"),
                "source_file_sha256": source.get("source_sha256"),
                "source_record": source.get("source_record"),
                "transformation": "fact_preserving_plain_language_remove_authority_and_canonical_operation_terms",
                "transformed_fields": ["question"],
                "inherited_fields": ["reference_answer", "expected_articles"],
            },
        }
        cases.append(case)
        audit_rows.append(
            {
                "case_id": case_id,
                "source_case_id": source_id,
                "source_dataset": source_dataset,
                "question": question,
                "authority_leaks": authority_evidence,
                "canonical_term_leaks": canonical_evidence,
                "reference_answer_inherited": case["reference_answer"] == source["reference_answer"],
                "expected_articles_inherited": case["expected_articles"] == source["expected_articles"],
                "coordinate_receipt": coordinate_receipt,
            }
        )

    ids = [case["id"] for case in cases]
    questions = [case["question"] for case in cases]
    if len(set(ids)) != 10 or len(set(questions)) != 10:
        raise ValueError("case ids or questions are not unique")
    expected_count = sum(len(case["expected_articles"]) for case in cases)
    if expected_count != 14:
        raise ValueError(f"expected article denominator mismatch: {expected_count}")
    source_quota = {
        "cm": sum(case["provenance"]["source_dataset"] == "cm" for case in cases),
        "fsc-hard": sum(case["provenance"]["source_dataset"] == "fsc-hard" for case in cases),
    }
    if source_quota != {"cm": 9, "fsc-hard": 1}:
        raise ValueError(f"source quota mismatch: {source_quota}")

    suite: dict[str, Any] = {
        "schema_version": "semantic-operation-seed-golden-v1",
        "version": "2026-08-27",
        "name": "Semantic Operation Seed Runtime Latent Challenge 10",
        "role": "in_sample_challenge",
        "frozen": True,
        "created_at": "2026-08-27",
        "source": {
            "construction_adr": ADR_ID,
            "manifest_path": str(MANIFEST.relative_to(ROOT)),
            "manifest_sha256": manifest_sha256,
            "combined_source_sha256": source_hashes["combined"],
            "sources": [
                {"path": str(CM_PATH.relative_to(ROOT)), "sha256": source_hashes["cm"], "selected_cases": 9},
                {"path": str(FSC_PATH.relative_to(ROOT)), "sha256": source_hashes["fsc-hard"], "selected_cases": 1},
            ],
        },
        "counts": {
            "cases": 10,
            "cm_actual_work_cases": 9,
            "fsc_actual_reply_cases": 1,
            "expected_articles": 14,
            "corpus_exact_coordinates": 14,
        },
        "task_contract": copy.deepcopy(contract.get("evaluation_visibility") or {}),
        "surface_contract": {
            "label": "runtime_latent_only",
            "definition": contract.get("latent_definition"),
            "authority_rule": contract.get("authority_rule"),
            "canonical_term_rule": contract.get("canonical_term_rule"),
            "standalone_rule": contract.get("standalone_rule"),
        },
        "grading": {
            "reference_and_expected_articles_are_grading_only": True,
            "performance_not_measured_in_construction_adr": True,
            "future_evaluation_requires_separate_adr": True,
        },
        "cases": cases,
    }
    audit: dict[str, Any] = {
        "schema_version": "semantic-operation-seed-golden-build-audit-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "manifest_sha256": manifest_sha256,
        "source_hashes": source_hashes,
        "summary": {
            "cases": 10,
            "source_quota": source_quota,
            "expected_articles": expected_count,
            "exact_coordinates": sum(len(row["coordinate_receipt"]) for row in audit_rows),
            "authority_leaks": sum(len(row["authority_leaks"]) for row in audit_rows),
            "canonical_term_leaks": sum(len(row["canonical_term_leaks"]) for row in audit_rows),
            "reference_answers_inherited": sum(row["reference_answer_inherited"] for row in audit_rows),
            "expected_article_sets_inherited": sum(row["expected_articles_inherited"] for row in audit_rows),
            "llm_calls": 0,
            "retrieval_calls": 0,
            "main_wiring": "unchanged",
        },
        "suite_content_sha256": _json_digest(suite),
        "rows": audit_rows,
    }
    audit["artifact_content_sha256"] = _json_digest(audit)
    return suite, audit


def _payload(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write(path: Path, payload: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    manifest, manifest_sha = _validate_manifest(args.manifest.resolve(), args.manifest_sha256)
    suite, audit = build_suite(manifest, manifest_sha256=manifest_sha)
    suite_payload = _payload(suite)
    audit_payload = _payload(audit)
    result = {
        "status": "valid" if args.validate_only else "complete",
        "suite_sha256": hashlib.sha256(suite_payload).hexdigest(),
        "suite_bytes": len(suite_payload),
        "artifact_sha256": hashlib.sha256(audit_payload).hexdigest(),
        "artifact_bytes": len(audit_payload),
        "summary": audit["summary"],
    }
    if not args.validate_only:
        _write(args.output.resolve(), suite_payload)
        _write(args.artifact.resolve(), audit_payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
