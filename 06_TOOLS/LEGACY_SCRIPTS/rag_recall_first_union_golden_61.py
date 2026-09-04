#!/usr/bin/env python3
"""ADR-0068: recall-first orthogonal union over frozen LegalClosure state."""

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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key, _relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from scripts import rag_proof_boundary_feedback_golden_61 as previous


base = previous.base
MODEL = "claude-haiku-4-5-20251001"
ADR_ID = "ADR-0068"
RUN_ID = "run-001"
ARMS = ("baseline", "recall-first-union")
CAP = 20
POOL_CAP = 96
MAX_PRODUCT_CALLS = 2
MAX_ROUTES = 5
MAX_PROMOTIONS = 4

PARENT_FROZEN_SHA256 = previous.PARENT_FROZEN_SHA256
PARENT_RUN_SHA256 = previous.PARENT_RUN_SHA256
PARENT_MANIFEST_SHA256 = previous.PARENT_MANIFEST_SHA256
DIRECT_PARENT_MANIFEST = (
    ROOT / "docs/adr/ADR-0067-proof-boundary-feedback/실험/manifest.json")
DIRECT_PARENT_MANIFEST_SHA256 = (
    "8e5b66f56ac6616313c926400044242914e9fb7a863934dcbbc8b1e2141fb13a")


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
    manifest = json.loads((adr / "실험/manifest.json").read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    if (_sha(DIRECT_PARENT_MANIFEST) != DIRECT_PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0068 direct parent manifest/hash mismatch")
    parents = (manifest.get("lineage") or {}).get("parents") or []
    parent = next((item for item in parents
                   if item.get("experiment_id") == "ADR-0067-experiment-v1"
                   and item.get("arm_id") == "proof-boundary-feedback"), None)
    if (parent is None or parent.get("relation") != "supersedes"
            or parent.get("manifest_sha256") != DIRECT_PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0068 parent lineage mismatch")
    arm_ids = {item.get("id") for item in
               (manifest.get("design") or {}).get("arms") or ()}
    if set(ARMS) - arm_ids:
        raise ValueError("ADR-0068 arm mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if any(item.get("model") != MODEL or item.get("class") != "product"
           for item in calls):
        raise ValueError("all ADR-0068 LLM roles must use product Haiku")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0068 must freeze 61 questions")
    if require_frozen:
        if not (manifest.get("design") or {}).get("criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before first call")
        if (manifest.get("dataset") or {}).get("sha256") != PARENT_FROZEN_SHA256:
            raise ValueError("frozen dataset SHA mismatch")
        run = next((item for item in manifest.get("runs") or ()
                    if item.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        impl = ROOT / "lawrag/core/rag/recall_first_feedback.py"
        expected = (run.get("implementation_sha256") or {}).get(
            "lawrag/core/rag/recall_first_feedback.py")
        if expected != _sha(impl):
            raise ValueError("implementation SHA is not frozen")
    return manifest


def _candidate_arm(index, case: dict, baseline: dict, initial: list,
                   observed: list, terms: tuple[str, ...], llm) -> dict:
    from lawrag.core.rag import recall_first_feedback

    recording = base.RecordingLLM(llm)
    started = time.perf_counter()
    runtime_error = ""
    meta: dict = {}
    try:
        candidate, raw_meta = recall_first_feedback.run(
            index, case["question"], recording, list(initial), list(observed),
            terms, deepcopy(baseline["retrieval_meta"]),
            cap=CAP, pool_cap=POOL_CAP)
        meta = dict(raw_meta or {})
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        candidate = list(initial)
        meta = {
            "enabled": True, "ran": True,
            "strategy": "recall-first-orthogonal-union",
            "status": "error", "reason": "runtime_error",
            "runtime_error": runtime_error, "hard_deletes": 0,
            "rejected": [], "actions": [], "retained": [],
            "verified_evidence": [], "promoted": [],
            "evidence_pool": [base._branch_dump(row) for row in observed],
        }
    incremental_wall_ms = (time.perf_counter() - started) * 1000
    selected = base._selected(candidate)
    pool = base._coordinate_records(index, meta.get("evidence_pool") or [])
    gold, all_hit, pool_all_hit = base._grade(case, selected, pool)
    incremental_usage = base._usage(recording.audit, runtime_error=runtime_error)
    effective_usage = base._sum_usage(
        baseline["provider_usage"], incremental_usage)
    return {
        "arm": "recall-first-union",
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
        "append_only_audit": base._append_only_audit(
            baseline["internal_pool"], selected, pool, meta),
        "fingerprint_audit": base._fingerprint_audit(meta),
        "runtime_error": runtime_error,
    }


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    return previous._arm_summary(rows, arm, corpus)


def _retention_valid(meta: dict) -> bool:
    retained = {(x.get("doc_id"), x.get("node"))
                for x in meta.get("retained") or ()}
    pool = {(x.get("doc_id"), x.get("node"))
            for x in meta.get("evidence_pool") or ()}
    promoted = {(x.get("doc_id"), x.get("node"))
                for x in meta.get("promoted") or ()}
    verified = {tuple(x.get("coordinate") or ())
                for x in meta.get("verified_evidence") or ()}
    return (retained <= pool and promoted <= retained and promoted <= verified
            and len(promoted) <= MAX_PROMOTIONS
            and len(retained) == int(meta.get("union_candidate_count") or 0))


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
        subset = [row for row in rows if row["suite"] == suite]
        result["suites"][suite] = {
            "cases": len(subset),
            "arms": {arm: _arm_summary(subset, arm, corpus) for arm in ARMS},
            "paired_selected_articles": base._status_counts(
                subset, "selected_articles"),
            "paired_internal_pool_articles": base._status_counts(
                subset, "internal_pool_articles"),
        }
    baseline = result["arms"]["baseline"]
    candidate = result["arms"]["recall-first-union"]
    incremental = candidate["incremental_provider_usage"]
    result["criteria"] = {
        "selected_gold_at_least_80_of_83": candidate["gold_article_hits"] >= 80,
        "pool_gold_at_least_82_of_83": candidate["internal_pool_gold_hits"] >= 82,
        "selected_article_regression_zero": (
            result["paired_selected_articles"]["baseline_only"] == 0),
        "selected_case_regression_zero": (
            result["paired_cases"]["baseline_only"] == 0),
        "pool_append_only_zero_violations": all(
            row["arms"]["recall-first-union"]["append_only_audit"]["passed"]
            for row in rows),
        "all_five_routes_visited": all(
            len((row["arms"]["recall-first-union"]["retrieval_meta"]
                 .get("coverage_ledger") or {}).get("visited_routes") or ())
            == MAX_ROUTES for row in rows),
        "product_calls_at_most_2_per_case": all(
            row["arms"]["recall-first-union"]
            ["incremental_provider_usage"]["calls"] <= MAX_PRODUCT_CALLS
            for row in rows),
        "duplicate_fingerprints_zero": all(
            row["arms"]["recall-first-union"]
            ["fingerprint_audit"]["duplicate_count"] == 0 for row in rows),
        "provider_and_runtime_errors_zero": incremental["errors"] == 0,
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "pool_cap_96": all(
            row["arms"]["recall-first-union"]["internal_pool_count"] <= POOL_CAP
            for row in rows),
        "grounded_retention_and_verified_promotion": all(
            _retention_valid(row["arms"]["recall-first-union"]["retrieval_meta"])
            for row in rows),
        "estimated_latency_p95_at_most_2x": (
            candidate["wall_ms_p95"] <= baseline["wall_ms_p95"] * 2
            if baseline["wall_ms_p95"] else False),
        "incremental_input_mean_at_most_100000": (
            incremental["input_tokens"] / len(rows) <= 100_000 if rows else False),
    }
    result["target_pass"] = bool(rows) and all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict, input_state: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["recall-first-union"]
    grading = {"baseline": baseline["gold_results"],
               "recall-first-union": candidate["gold_results"],
               "paired": row["paired"]}
    return f"""# ADR-0068 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `{RUN_ID}`
- arm: `baseline`, `recall-first-union`
- model: `{MODEL}`
- initial state SHA-256: `{row['initial_state_sha256']}`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps(input_state, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline

ADR-0064 frozen baseline payload를 재사용했다.

```json
{json.dumps(baseline.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

### recall-first-union

```json
{json.dumps(candidate.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

planner와 evidence selector의 system, user, schema, provider 원응답과 structured output을
위 candidate 호출 목록에 순서대로 보존했다.

## 7. 채점 호출과 반복 판정

judge LLM 없이 `doc_id + article root node` exact match로 채점했다.

```json
{json.dumps(grading, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

```json
{json.dumps({'candidate_meta': candidate['retrieval_meta'],
             'append_only_audit': candidate['append_only_audit'],
             'fingerprint_audit': candidate['fingerprint_audit'],
             'usage': candidate['incremental_provider_usage'],
             'latency_ms': candidate['incremental_wall_ms']},
            ensure_ascii=False, indent=2)}
```
"""


def _save(out: Path, rows: list[dict], corpus: int) -> None:
    result = {
        "schema_version": "recall-first-union-golden-61-run-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(base.PARENT_FROZEN.relative_to(ROOT)),
            "frozen_sha256": PARENT_FROZEN_SHA256,
            "parent_run_path": str(base.PARENT_RUN.relative_to(ROOT)),
            "parent_run_sha256": PARENT_RUN_SHA256,
            "direct_parent": "ADR-0067-experiment-v1/proof-boundary-feedback",
            "direct_parent_manifest_sha256": DIRECT_PARENT_MANIFEST_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": _sha(
            ROOT / "lawrag/core/rag/recall_first_feedback.py"),
        "model_policy": {"product_model": MODEL, "judge": None,
                         "temperature": "provider default / omitted"},
        "contract": {
            "selected_cap": CAP, "internal_pool_cap": POOL_CAP,
            "max_product_calls": MAX_PRODUCT_CALLS,
            "route_portfolio": list(__import__(
                "lawrag.core.rag.recall_first_feedback", fromlist=["ROUTE_KINDS"])
                .ROUTE_KINDS),
            "max_promotions": MAX_PROMOTIONS,
            "initial_state": "ADR-0064 baseline exact reuse",
            "gold_hidden_from_product": True,
            "basis_exchange": "up to four non-mandatory incumbent tail rows",
        },
        "summary": _summary(rows, corpus), "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def _validate_resume(blob: dict) -> list[dict]:
    if blob.get("schema_version") != "recall-first-union-golden-61-run-v1":
        raise ValueError("resume artifact schema mismatch")
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
        print(json.dumps({"valid": True, "cases": len(frozen["cases"]),
                          "gold_total": 85, "gold_scorable": 83,
                          "corpus_article_roots": corpus,
                          "observed_total": sum(len(x[3]) for x in prepared.values()),
                          "llm_calls": 0}, ensure_ascii=False, indent=2))
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
            "terms": list(terms), "initial_meta": baseline["retrieval_meta"],
            "cap": CAP, "pool_cap": POOL_CAP,
            "max_product_calls": MAX_PRODUCT_CALLS,
            "routes": MAX_ROUTES, "max_promotions": MAX_PROMOTIONS,
        }
        candidate = _candidate_arm(
            index, case, baseline, initial, observed, terms, real)
        row = {
            "number": case["number"], "case_id": case["id"],
            "suite": case["suite"], "question": case["question"],
            "initial_state_sha256": base._json_sha(input_state),
            "input_state": input_state,
            "arms": {"baseline": baseline, "recall-first-union": candidate},
            "paired": base._paired(baseline, candidate),
        }
        (adr / "실험" / f"질문-{case['number']:03d}-{case['id']}.md").write_text(
            _question_markdown(case, row, input_state), encoding="utf-8")
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _save(out, rows, corpus)
        bh = sum(g["hit"] for g in baseline["gold_results"] if g["scorable"])
        ch = sum(g["hit"] for g in candidate["gold_results"] if g["scorable"])
        ph = sum(g["internal_pool_hit"] for g in candidate["gold_results"]
                 if g["scorable"])
        total = sum(g["scorable"] for g in baseline["gold_results"])
        print(f"[{case['number']:02d}/61] {case['id']} baseline={bh}/{total} "
              f"candidate={ch}/{total} pool={ph}/{total} "
              f"calls={candidate['incremental_provider_usage']['calls']} "
              f"status={candidate['retrieval_meta'].get('status')}", flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
