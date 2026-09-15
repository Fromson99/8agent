#!/usr/bin/env python3
"""ADR-0067: frozen LegalClosure state에서 single-boundary feedback을 비교한다."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from scripts import rag_proof_guided_span_golden_61 as base


MODEL = "claude-haiku-4-5-20251001"
ADR_ID = "ADR-0067"
RUN_ID = "run-001"
ARMS = ("baseline", "proof-boundary-feedback")
CAP = 20
POOL_CAP = 48
MAX_PRODUCT_CALLS = 2
MAX_EXTERNAL_ACTIONS = 1
MAX_ADMISSIONS = 3

PARENT_FROZEN_SHA256 = base.PARENT_FROZEN_SHA256
PARENT_RUN_SHA256 = base.PARENT_RUN_SHA256
PARENT_MANIFEST_SHA256 = base.PARENT_MANIFEST_SHA256
DIRECT_PARENT_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0065-uncertainty-aware-semantic-bindings/실험/manifest.json"
)
DIRECT_PARENT_MANIFEST_SHA256 = (
    "2f72b2ab89a6e2703740707a50f3ae7ad98b163838d521e9d494274d9c0169c2"
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, round((len(ordered) - 1) * ratio)))]


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    path = adr / "실험/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    if (not DIRECT_PARENT_MANIFEST.is_file()
            or _sha(DIRECT_PARENT_MANIFEST) != DIRECT_PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0067 direct parent manifest/hash mismatch")
    parents = (manifest.get("lineage") or {}).get("parents") or []
    parent = next((item for item in parents
                   if item.get("experiment_id") == "ADR-0065-experiment-v1"
                   and item.get("arm_id") == "uncertainty-aware-bindings"), None)
    if (parent is None
            or parent.get("manifest_sha256")
            != DIRECT_PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0067 parent lineage mismatch")
    arm_ids = {item.get("id") for item in
               (manifest.get("design") or {}).get("arms") or ()}
    if set(ARMS) - arm_ids:
        raise ValueError("ADR-0067 arm mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if any(item.get("model") != MODEL or item.get("class") != "product"
           for item in calls):
        raise ValueError("all ADR-0067 LLM roles must use product Haiku")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0067 must freeze 61 questions")
    if require_frozen:
        if not (manifest.get("design") or {}).get(
                "criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before first call")
        if ((manifest.get("dataset") or {}).get("sha256")
                != PARENT_FROZEN_SHA256):
            raise ValueError("frozen dataset SHA mismatch")
        run = next((item for item in manifest.get("runs") or ()
                    if item.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        runner = Path(__file__).resolve()
        impl = Path(__import__("lawrag").__file__).resolve().parent / "core/rag/proof_boundary_feedback.py"
        if run.get("runner_sha256") != _sha(runner):
            raise ValueError("runner SHA is not frozen")
        expected_impl = (run.get("implementation_sha256") or {}).get(
            "lawrag/core/rag/proof_boundary_feedback.py")
        if expected_impl != _sha(impl):
            raise ValueError("implementation SHA is not frozen")
    return manifest


def _candidate_arm(index, case: dict, baseline: dict, initial: list,
                   observed: list, terms: tuple[str, ...], llm) -> dict:
    from lawrag.core.rag import proof_boundary_feedback

    recording = base.RecordingLLM(llm)
    started = time.perf_counter()
    runtime_error = ""
    meta: dict = {}
    try:
        candidate, raw_meta = proof_boundary_feedback.run(
            index, case["question"], recording, list(initial), list(observed),
            terms, deepcopy(baseline["retrieval_meta"]),
            cap=CAP, pool_cap=POOL_CAP)
        meta = dict(raw_meta or {})
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        candidate = list(initial)
        meta = {
            "enabled": True, "ran": True,
            "strategy": "proof-boundary-feedback",
            "status": "error", "reason": "runtime_error",
            "runtime_error": runtime_error,
            "hard_deletes": 0, "rejected": [],
            "actions": [], "admitted": [], "promoted": [],
            "evidence_pool": [base._branch_dump(row) for row in observed],
        }
    incremental_wall_ms = (time.perf_counter() - started) * 1000
    selected = base._selected(candidate)
    pool = base._coordinate_records(index, meta.get("evidence_pool") or [])
    gold, all_hit, pool_all_hit = base._grade(case, selected, pool)
    incremental_usage = base._usage(
        recording.audit, runtime_error=runtime_error)
    effective_usage = base._sum_usage(
        baseline["provider_usage"], incremental_usage)
    append_only = base._append_only_audit(
        baseline["internal_pool"], selected, pool, meta)
    fingerprints = base._fingerprint_audit(meta)
    return {
        "arm": "proof-boundary-feedback",
        "selected": selected, "selected_count": len(selected),
        "internal_pool": pool, "internal_pool_count": len(pool),
        "gold_results": gold, "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": meta,
        "llm_calls": recording.audit,
        "reused_initial_llm_calls_ref": "arms.baseline.llm_calls",
        "provider_usage": effective_usage,
        "incremental_provider_usage": incremental_usage,
        "wall_ms": round(baseline["wall_ms"] + incremental_wall_ms, 3),
        "incremental_wall_ms": round(incremental_wall_ms, 3),
        "append_only_audit": append_only,
        "fingerprint_audit": fingerprints,
        "runtime_error": runtime_error,
    }


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    values = [row["arms"][arm] for row in rows]
    scored = [gold for row in values for gold in row["gold_results"]
              if gold["scorable"]]
    case_rows = [row for row in values if row["case_all_gold_hit"] is not None]
    pool_case_rows = [row for row in values
                      if row["case_all_gold_internal_pool_hit"] is not None]
    selected_counts = [row["selected_count"] for row in values]
    pool_counts = [row["internal_pool_count"] for row in values]
    walls = [row["wall_ms"] for row in values]
    usage_keys = ("calls", "input_tokens", "output_tokens", "duration_ms",
                  "errors", "provider_errors", "recovered_errors",
                  "unrecovered_errors")
    usage = {key: sum(int((row.get("provider_usage") or {}).get(key, 0))
                      for row in values) for key in usage_keys}
    incremental = {
        key: sum(int((row.get("incremental_provider_usage") or {})
                     .get(key, 0)) for row in values)
        for key in usage_keys}
    hits = sum(bool(gold["hit"]) for gold in scored)
    pool_hits = sum(bool(gold["internal_pool_hit"]) for gold in scored)
    return {
        "scorable_cases": len(case_rows),
        "case_all_gold_hits": sum(bool(row["case_all_gold_hit"])
                                  for row in case_rows),
        "case_all_gold_recall_at_20": round(
            sum(bool(row["case_all_gold_hit"]) for row in case_rows)
            / len(case_rows), 6) if case_rows else 0,
        "case_all_gold_internal_pool_hits": sum(
            bool(row["case_all_gold_internal_pool_hit"])
            for row in pool_case_rows),
        "gold_article_instances": len(scored),
        "gold_article_hits": hits,
        "article_instance_recall_at_20": round(hits / len(scored), 6)
        if scored else 0,
        "internal_pool_gold_hits": pool_hits,
        "internal_pool_recall": round(pool_hits / len(scored), 6)
        if scored else 0,
        "selected_mean": round(statistics.mean(selected_counts), 3)
        if selected_counts else 0,
        "selected_p50": statistics.median(selected_counts)
        if selected_counts else 0,
        "selected_p95": _percentile(selected_counts, .95),
        "internal_pool_mean": round(statistics.mean(pool_counts), 3)
        if pool_counts else 0,
        "internal_pool_p50": statistics.median(pool_counts)
        if pool_counts else 0,
        "internal_pool_p95": _percentile(pool_counts, .95),
        "mean_selectivity": round(statistics.mean(selected_counts) / corpus, 8)
        if selected_counts and corpus else 0,
        "internal_pool_selectivity": round(
            statistics.mean(pool_counts) / corpus, 8)
        if pool_counts and corpus else 0,
        "wall_ms_p50": round(statistics.median(walls), 3) if walls else 0,
        "wall_ms_p95": round(_percentile(walls, .95), 3),
        "provider_usage": usage,
        "incremental_provider_usage": incremental,
    }


def _action_count(meta: dict, *, external_only: bool = False) -> int:
    count = 0
    for action in meta.get("actions") or ():
        if action.get("skipped"):
            continue
        if external_only and action.get("kind") in {"stop", "inspect_seen"}:
            continue
        count += 1
    return count


def _admission_valid(meta: dict) -> bool:
    admitted = {
        (row.get("doc_id"), row.get("node"))
        for row in meta.get("admitted") or ()}
    promoted = {
        (row.get("doc_id"), row.get("node"))
        for row in meta.get("promoted") or ()}
    accepted = {
        tuple(row.get("coordinate") or ())
        for row in ((meta.get("verification") or {})
                    .get("accepted_evidence") or ())}
    return (promoted <= admitted <= accepted
            and len(admitted) <= MAX_ADMISSIONS)


def _summary(rows: list[dict], corpus: int) -> dict:
    result = {
        "cases": len(rows), "corpus_article_roots": corpus,
        "arms": {arm: _arm_summary(rows, arm, corpus) for arm in ARMS},
        "paired_selected_articles": base._status_counts(
            rows, "selected_articles"),
        "paired_internal_pool_articles": base._status_counts(
            rows, "internal_pool_articles"),
        "paired_cases": base._status_counts(rows, "case_all_gold"),
        "paired_internal_pool_cases": base._status_counts(
            rows, "case_all_gold_internal_pool"),
        "suites": {},
    }
    for suite in sorted({row["suite"] for row in rows}):
        suite_rows = [row for row in rows if row["suite"] == suite]
        result["suites"][suite] = {
            "cases": len(suite_rows),
            "arms": {arm: _arm_summary(suite_rows, arm, corpus)
                     for arm in ARMS},
            "paired_selected_articles": base._status_counts(
                suite_rows, "selected_articles"),
            "paired_cases": base._status_counts(
                suite_rows, "case_all_gold"),
        }
    baseline = result["arms"]["baseline"]
    candidate = result["arms"]["proof-boundary-feedback"]
    incremental_inputs = candidate["incremental_provider_usage"]["input_tokens"]
    result["criteria"] = {
        "candidate_only_articles_at_least_2": (
            result["paired_selected_articles"]["candidate_only"] >= 2),
        "selected_article_regression_zero": (
            result["paired_selected_articles"]["baseline_only"] == 0),
        "selected_case_regression_zero": (
            result["paired_cases"]["baseline_only"] == 0),
        "append_only_zero_violations": all(
            row["arms"]["proof-boundary-feedback"]
            ["append_only_audit"]["passed"] for row in rows),
        "external_action_at_most_1_per_case": all(
            _action_count(row["arms"]["proof-boundary-feedback"]
                          ["retrieval_meta"], external_only=True)
            <= MAX_EXTERNAL_ACTIONS for row in rows),
        "product_calls_at_most_2_per_case": all(
            row["arms"]["proof-boundary-feedback"]
            ["incremental_provider_usage"]["calls"] <= MAX_PRODUCT_CALLS
            for row in rows),
        "duplicate_fingerprints_zero": all(
            row["arms"]["proof-boundary-feedback"]
            ["fingerprint_audit"]["duplicate_count"] == 0 for row in rows),
        "provider_and_runtime_errors_zero": (
            candidate["incremental_provider_usage"]["errors"] == 0),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "internal_pool_cap_48": all(
            row["arms"]["proof-boundary-feedback"]["internal_pool_count"]
            <= POOL_CAP for row in rows),
        "admission_at_most_3_and_grounded": all(
            _admission_valid(row["arms"]["proof-boundary-feedback"]
                             ["retrieval_meta"]) for row in rows),
        "estimated_latency_p95_at_most_2x": (
            candidate["wall_ms_p95"] <= baseline["wall_ms_p95"] * 2
            if baseline["wall_ms_p95"] else False),
        "incremental_input_mean_at_most_60000": (
            incremental_inputs / len(rows) <= 60_000 if rows else False),
    }
    result["target_pass"] = bool(rows) and all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict, input_state: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["proof-boundary-feedback"]
    grading = {
        "baseline": baseline["gold_results"],
        "proof-boundary-feedback": candidate["gold_results"],
        "paired": row["paired"],
    }
    return f"""# ADR-0067 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `{RUN_ID}`
- arm: `baseline`, `proof-boundary-feedback`
- model: `{MODEL}`
- initial state SHA-256: `{row['initial_state_sha256']}`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

채점 전용이며 제품 입력에는 공개하지 않았다.

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps(input_state, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline

ADR-0064의 frozen baseline payload를 재사용했다.

```json
{json.dumps(baseline.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

### proof-boundary-feedback

```json
{json.dumps(candidate.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

support gate와 admission verifier의 system, user, schema, provider 원응답과 structured output은
위 candidate 호출 목록에 호출 순서대로 보존했다.

## 7. 채점 호출과 반복 판정

judge LLM 없이 `doc_id + article root node` exact match로 채점했다.

```json
{json.dumps(grading, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

```json
{json.dumps({
    'candidate_meta': candidate['retrieval_meta'],
    'append_only_audit': candidate['append_only_audit'],
    'fingerprint_audit': candidate['fingerprint_audit'],
    'usage': candidate['incremental_provider_usage'],
    'latency_ms': candidate['incremental_wall_ms'],
}, ensure_ascii=False, indent=2)}
```
"""


def _save(out: Path, rows: list[dict], corpus: int) -> None:
    result = {
        "schema_version": "proof-boundary-feedback-golden-61-run-v1",
        "adr_id": ADR_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(base.PARENT_FROZEN.relative_to(ROOT)),
            "frozen_sha256": PARENT_FROZEN_SHA256,
            "parent_run_path": str(base.PARENT_RUN.relative_to(ROOT)),
            "parent_run_sha256": PARENT_RUN_SHA256,
            "parent_manifest_path": str(base.PARENT_MANIFEST.relative_to(ROOT)),
            "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
            "direct_parent": (
                "ADR-0065-experiment-v1/uncertainty-aware-bindings"),
            "direct_parent_manifest_sha256": DIRECT_PARENT_MANIFEST_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": _sha(
            Path(__import__("lawrag").__file__).resolve().parent / "core/rag/proof_boundary_feedback.py"),
        "model_policy": {
            "product_model": MODEL, "judge": None,
            "temperature": "provider default / omitted",
        },
        "contract": {
            "selected_cap": CAP,
            "internal_pool_cap": POOL_CAP,
            "max_product_calls": MAX_PRODUCT_CALLS,
            "max_external_actions": MAX_EXTERNAL_ACTIONS,
            "max_admissions": MAX_ADMISSIONS,
            "initial_state": "ADR-0064 baseline exact reuse",
            "gold_hidden_from_product": True,
            "basis_exchange": False,
        },
        "summary": _summary(rows, corpus),
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def _validate_resume(blob: dict) -> list[dict]:
    if blob.get("schema_version") != (
            "proof-boundary-feedback-golden-61-run-v1"):
        raise ValueError("resume artifact schema mismatch")
    lineage = blob.get("source_lineage") or {}
    if (lineage.get("frozen_sha256") != PARENT_FROZEN_SHA256
            or lineage.get("parent_run_sha256") != PARENT_RUN_SHA256):
        raise ValueError("resume parent lineage mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume requires exact runner SHA")
    rows = list(blob.get("rows") or ())
    ids = [row.get("case_id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("resume artifact contains duplicate cases")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out
    frozen, parent_run, _parent_manifest = base._load_parent()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod

    index = index_mod.current().scoped(None)
    corpus = base._article_roots(index)
    parent_by_case = {row["case_id"]: row for row in parent_run["rows"]}
    prepared = {}
    for case in frozen["cases"]:
        parent = parent_by_case[case["id"]]["arms"]["baseline"]
        terms = base._terms(parent.get("retrieval_meta") or {})
        initial = base._initial_branches(index, parent, terms)
        observed = base._observed_branches(index, parent, initial, terms)
        prepared[case["id"]] = (parent, terms, initial, observed)

    if args.validate_only:
        print(json.dumps({
            "valid": True,
            "cases": len(frozen["cases"]),
            "gold_total": 85,
            "gold_scorable": 83,
            "corpus_article_roots": corpus,
            "observed_total": sum(len(value[3])
                                  for value in prepared.values()),
            "llm_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 0

    from lawrag.core import llm as llm_mod

    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError("configured product LLM is unavailable")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")

    rows = []
    if args.resume and out.exists():
        rows = _validate_resume(json.loads(out.read_text(encoding="utf-8")))
    completed = {row["case_id"] for row in rows}
    for case in frozen["cases"]:
        if case["id"] in completed:
            continue
        parent, terms, initial, observed = prepared[case["id"]]
        baseline = base._baseline_arm(index, case, parent, observed)
        input_state = {
            "question": case["question"],
            "initial": [base._branch_dump(row) for row in initial],
            "observed": [base._branch_dump(row) for row in observed],
            "terms": list(terms),
            "initial_meta": baseline["retrieval_meta"],
            "cap": CAP,
            "pool_cap": POOL_CAP,
            "max_product_calls": MAX_PRODUCT_CALLS,
            "max_external_actions": MAX_EXTERNAL_ACTIONS,
        }
        candidate = _candidate_arm(
            index, case, baseline, initial, observed, terms, real)
        row = {
            "number": case["number"],
            "case_id": case["id"],
            "suite": case["suite"],
            "question": case["question"],
            "initial_state_sha256": base._json_sha(input_state),
            "input_state": input_state,
            "arms": {
                "baseline": baseline,
                "proof-boundary-feedback": candidate,
            },
            "paired": base._paired(baseline, candidate),
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, input_state), encoding="utf-8")
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _save(out, rows, corpus)
        base_hits = sum(g["hit"] for g in baseline["gold_results"]
                        if g["scorable"])
        cand_hits = sum(g["hit"] for g in candidate["gold_results"]
                        if g["scorable"])
        total = sum(g["scorable"] for g in baseline["gold_results"])
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"baseline={base_hits}/{total} candidate={cand_hits}/{total} "
            f"calls={candidate['incremental_provider_usage']['calls']} "
            f"status={candidate['retrieval_meta'].get('status')}",
            flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
