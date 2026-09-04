#!/usr/bin/env python3
"""ADR-0069: replay ADR-0067 actions with coordinate-first admission."""

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

from scripts import rag_proof_guided_span_golden_61 as base


ADR_ID = "ADR-0069"
RUN_ID = "run-001"
ARMS = ("baseline", "source-registry-admission")
CAP = 20
POOL_CAP = 48
MAX_ADMISSIONS = 3
PARENT_RUN = (
    ROOT / "docs/adr/ADR-0067-proof-boundary-feedback/artifacts/run-001.json")
PARENT_RUN_SHA256 = (
    "d62dd2fa84d081498ad053a3900a7777ce0c85600399cb9c913bf3583442c52f")
PARENT_MANIFEST = (
    ROOT / "docs/adr/ADR-0067-proof-boundary-feedback/실험/manifest.json")
PARENT_MANIFEST_SHA256 = (
    "8e5b66f56ac6616313c926400044242914e9fb7a863934dcbbc8b1e2141fb13a")
IMPLEMENTATION = ROOT / "lawrag/core/rag/source_registry_admission.py"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zero_usage() -> dict:
    return {key: 0 for key in (
        "calls", "input_tokens", "output_tokens", "duration_ms", "errors",
        "provider_errors", "recovered_errors", "unrecovered_errors")}


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, round((len(ordered) - 1) * ratio)))]


def _load_sources() -> tuple[dict, dict, dict]:
    frozen, _adr64_run, _adr64_manifest = base._load_parent()
    for path, expected in (
        (PARENT_RUN, PARENT_RUN_SHA256),
        (PARENT_MANIFEST, PARENT_MANIFEST_SHA256),
    ):
        if not path.is_file() or _sha(path) != expected:
            raise ValueError(f"parent lineage mismatch: {path}")
    run = json.loads(PARENT_RUN.read_text(encoding="utf-8"))
    manifest = json.loads(PARENT_MANIFEST.read_text(encoding="utf-8"))
    if len(run.get("rows") or ()) != 61:
        raise ValueError("ADR-0067 parent must contain 61 rows")
    if (manifest.get("results") or {}).get("status") != "complete":
        raise ValueError("ADR-0067 parent experiment is incomplete")
    arm_ids = {row.get("id") for row in
               (manifest.get("design") or {}).get("arms") or ()}
    if "proof-boundary-feedback" not in arm_ids:
        raise ValueError("ADR-0067 parent arm is missing")
    return frozen, run, manifest


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest = json.loads((adr / "실험/manifest.json").read_text("utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    parent = next(iter((manifest.get("lineage") or {}).get("parents") or ()), {})
    if (parent.get("experiment_id") != "ADR-0067-experiment-v1"
            or parent.get("arm_id") != "proof-boundary-feedback"
            or parent.get("manifest_sha256") != PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0069 parent lineage mismatch")
    arms = {item.get("id") for item in
            (manifest.get("design") or {}).get("arms") or ()}
    if set(ARMS) - arms:
        raise ValueError("ADR-0069 arm mismatch")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0069 must freeze 61 questions")
    if require_frozen:
        design = manifest.get("design") or {}
        if not design.get("criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        if ((manifest.get("dataset") or {}).get("sha256")
                != base.PARENT_FROZEN_SHA256):
            raise ValueError("frozen dataset SHA mismatch")
        run = next((row for row in manifest.get("runs") or ()
                    if row.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        expected = (run.get("implementation_sha256") or {}).get(
            "lawrag/core/rag/source_registry_admission.py")
        if expected != _sha(IMPLEMENTATION):
            raise ValueError("implementation SHA is not frozen")
        if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
            raise ValueError("ADR-0069 performs no new LLM calls")
    return manifest


def _restore_rows(index, records: list[dict], terms: tuple[str, ...],
                  origin: str) -> list:
    out, seen = [], set()
    for record in records:
        row = base._restore_branch(
            index, dict(record), terms, default_origin=origin)
        if row.coordinate not in seen:
            out.append(row)
            seen.add(row.coordinate)
    return out


def _baseline_arm(index, case: dict, parent: dict,
                  selected_rows: list, pool_rows: list) -> dict:
    selected = base._selected(selected_rows)
    pool = base._coordinate_records(index, [base._branch_dump(row)
                                             for row in pool_rows])
    gold, all_hit, pool_all_hit = base._grade(case, selected, pool)
    stored = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in parent.get("gold_results") or () if row.get("scorable")]
    actual = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in gold if row.get("scorable")]
    if stored != actual:
        raise ValueError(f"{case['id']}: ADR-0067 grading mismatch")
    return {
        "arm": "baseline",
        "source": "ADR-0067/run-001/proof-boundary-feedback",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": deepcopy(parent.get("retrieval_meta") or {}),
        "llm_calls": deepcopy(parent.get("llm_calls") or []),
        "provider_usage": deepcopy(parent.get("provider_usage") or {}),
        "incremental_provider_usage": deepcopy(
            parent.get("incremental_provider_usage") or _zero_usage()),
        "wall_ms": float(parent.get("wall_ms") or 0),
        "parent_state_sha256": base._json_sha(parent),
        "runtime_error": "",
    }


def _candidate_arm(index, case: dict, baseline: dict, selected_rows: list,
                   pool_rows: list, planner_rows: list, terms: tuple[str, ...],
                   action: dict | None) -> dict:
    from lawrag.core.rag import source_registry_admission

    started = time.perf_counter()
    runtime_error = ""
    try:
        selected, meta = source_registry_admission.run(
            index, case["question"], list(selected_rows), list(pool_rows),
            list(planner_rows), terms, deepcopy(action), cap=CAP,
            pool_cap=POOL_CAP, admission_max=MAX_ADMISSIONS)
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        selected = list(selected_rows)
        meta = {
            "enabled": True, "ran": True, "status": "error",
            "reason": "runtime_error", "runtime_error": runtime_error,
            "hard_deletes": 0, "rejected": [], "actions": [],
            "registry_receipts": [], "admitted": [], "promoted": [],
            "evidence_pool": [base._branch_dump(row) for row in pool_rows],
        }
    incremental_ms = (time.perf_counter() - started) * 1000
    selected_records = base._selected(selected)
    pool = base._coordinate_records(index, meta.get("evidence_pool") or [])
    gold, all_hit, pool_all_hit = base._grade(case, selected_records, pool)
    usage = _zero_usage()
    append_only = base._append_only_audit(
        baseline["internal_pool"], selected_records, pool, meta)
    receipts = meta.get("registry_receipts") or []
    admitted = {(row.get("doc_id"), row.get("node"))
                for row in meta.get("admitted") or ()}
    verified = {tuple(row.get("coordinate") or ()) for row in receipts
                if row.get("status") == "verified"}
    registry_audit = {
        "admitted_subset_of_verified": admitted <= verified,
        "admitted_count": len(admitted),
        "verified_count": len(verified),
        "passed": admitted <= verified and len(admitted) <= MAX_ADMISSIONS,
    }
    return {
        "arm": "source-registry-admission",
        "selected": selected_records,
        "selected_count": len(selected_records),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": meta,
        "llm_calls": [],
        "reused_parent_llm_calls_ref": "arms.baseline.llm_calls",
        "provider_usage": deepcopy(baseline.get("provider_usage") or {}),
        "incremental_provider_usage": usage,
        "wall_ms": round(float(baseline.get("wall_ms") or 0)
                         + incremental_ms, 3),
        "incremental_wall_ms": round(incremental_ms, 3),
        "append_only_audit": append_only,
        "registry_audit": registry_audit,
        "runtime_error": runtime_error,
    }


def _summary(rows: list[dict], corpus: int) -> dict:
    result = {
        "cases": len(rows),
        "corpus_article_roots": corpus,
        "arms": {arm: base._arm_summary(rows, arm, corpus) for arm in ARMS},
        "paired_selected_articles": base._status_counts(
            rows, "selected_articles"),
        "paired_internal_pool_articles": base._status_counts(
            rows, "internal_pool_articles"),
        "paired_cases": base._status_counts(rows, "case_all_gold"),
        "paired_internal_pool_cases": base._status_counts(
            rows, "case_all_gold_internal_pool"),
    }
    baseline = result["arms"]["baseline"]
    candidate = result["arms"]["source-registry-admission"]
    increments = [row["arms"]["source-registry-admission"]
                  ["incremental_wall_ms"] for row in rows]
    raw = sum((row["arms"]["source-registry-admission"]
               ["retrieval_meta"].get("raw_candidate_count") or 0)
              for row in rows)
    admitted = sum(len(row["arms"]["source-registry-admission"]
                       ["retrieval_meta"].get("admitted") or ())
                   for row in rows)
    promoted = sum(len(row["arms"]["source-registry-admission"]
                       ["retrieval_meta"].get("promoted") or ())
                   for row in rows)
    result["source_registry"] = {
        "raw_candidates": raw,
        "admitted": admitted,
        "promoted": promoted,
        "incremental_wall_ms_p50": round(statistics.median(increments), 3)
        if increments else 0,
        "incremental_wall_ms_p95": round(_percentile(increments, .95), 3),
    }
    result["operational_reference"] = {
        "adr0064_feedback_off_hits": 64,
        "candidate_hits": candidate["gold_article_hits"],
        "cumulative_gain": candidate["gold_article_hits"] - 64,
    }
    result["criteria"] = {
        "candidate_only_articles_at_least_1": (
            result["paired_selected_articles"]["candidate_only"] >= 1),
        "selected_article_regression_zero": (
            result["paired_selected_articles"]["baseline_only"] == 0),
        "selected_case_regression_zero": (
            result["paired_cases"]["baseline_only"] == 0),
        "operational_reference_cumulative_gain_at_least_2": (
            candidate["gold_article_hits"] - 64 >= 2),
        "append_only_zero_violations": all(
            row["arms"]["source-registry-admission"]
            ["append_only_audit"]["passed"] for row in rows),
        "registry_admission_valid": all(
            row["arms"]["source-registry-admission"]
            ["registry_audit"]["passed"] for row in rows),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "internal_pool_cap_48": all(
            row["arms"]["source-registry-admission"]
            ["internal_pool_count"] <= POOL_CAP for row in rows),
        "new_llm_calls_zero": all(
            row["arms"]["source-registry-admission"]
            ["incremental_provider_usage"]["calls"] == 0 for row in rows),
        "provider_and_runtime_errors_zero": all(
            not row["arms"]["source-registry-admission"]["runtime_error"]
            for row in rows),
        "estimated_total_latency_p95_at_most_1_1x": (
            candidate["wall_ms_p95"] <= baseline["wall_ms_p95"] * 1.1
            if baseline["wall_ms_p95"] else False),
    }
    result["target_pass"] = bool(rows) and all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict, input_state: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["source-registry-admission"]
    grading = {
        "baseline": baseline["gold_results"],
        "source-registry-admission": candidate["gold_results"],
        "paired": row["paired"],
    }
    return f"""# ADR-0069 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `{RUN_ID}`
- arm: `baseline`, `source-registry-admission`
- parent state: `ADR-0067/run-001/proof-boundary-feedback`
- new LLM calls: `0`
- initial state SHA-256: `{row['initial_state_sha256']}`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

채점 전용이며 retrieval/controller 입력에는 공개하지 않았다.

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps(input_state, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline — 부모 ADR에서 재사용한 실제 호출

```json
{json.dumps(baseline.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

### source-registry-admission — 신규 호출 없음

```json
[]
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

신규 호출은 없다. 후보 arm은 위 baseline의 실제 planner action을 고정 재생하고 admission만
결정론적 corpus 좌표·원문 hash 검사로 교체했다.

## 7. 채점 호출과 반복 판정

judge LLM 없이 `doc_id + article root node` exact match로 1회 채점했다.

```json
{json.dumps(grading, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

```json
{json.dumps({
    'candidate_meta': candidate['retrieval_meta'],
    'append_only_audit': candidate['append_only_audit'],
    'registry_audit': candidate['registry_audit'],
    'usage': candidate['incremental_provider_usage'],
    'latency_ms': candidate['incremental_wall_ms'],
}, ensure_ascii=False, indent=2)}
```
"""


def _save(out: Path, rows: list[dict], corpus: int) -> None:
    payload = {
        "schema_version": "source-registry-admission-golden-61-run-v1",
        "adr_id": ADR_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(base.PARENT_FROZEN.relative_to(ROOT)),
            "frozen_sha256": base.PARENT_FROZEN_SHA256,
            "parent_run_path": str(PARENT_RUN.relative_to(ROOT)),
            "parent_run_sha256": PARENT_RUN_SHA256,
            "parent_manifest_path": str(PARENT_MANIFEST.relative_to(ROOT)),
            "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
            "direct_parent": "ADR-0067-experiment-v1/proof-boundary-feedback",
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": _sha(IMPLEMENTATION),
        "model_policy": {
            "new_llm_calls": 0,
            "reused_parent_product_model": "claude-haiku-4-5-20251001",
            "judge": None,
        },
        "contract": {
            "selected_cap": CAP,
            "internal_pool_cap": POOL_CAP,
            "max_admissions": MAX_ADMISSIONS,
            "parent_action_replay": True,
            "gold_hidden_from_controller": True,
            "basis_exchange": False,
        },
        "summary": _summary(rows, corpus),
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out
    frozen, parent_run, _parent_manifest = _load_sources()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod

    index = index_mod.current().scoped(None)
    corpus = base._article_roots(index)
    parent_by_case = {row["case_id"]: row for row in parent_run["rows"]}
    prepared = {}
    for case in frozen["cases"]:
        row = parent_by_case[case["id"]]
        parent_baseline = row["arms"]["baseline"]
        parent_candidate = row["arms"]["proof-boundary-feedback"]
        terms = base._terms(parent_baseline.get("retrieval_meta") or {})
        selected = _restore_rows(
            index, parent_candidate.get("selected") or [], terms,
            "adr0067-selected")
        pool = _restore_rows(
            index, parent_candidate.get("internal_pool") or [], terms,
            "adr0067-pool")
        planner = _restore_rows(
            index, parent_baseline.get("internal_pool") or [], terms,
            "adr0067-planner-pool")
        actions = ((parent_candidate.get("retrieval_meta") or {})
                   .get("actions") or [])
        prepared[case["id"]] = (
            parent_candidate, terms, selected, pool, planner,
            deepcopy(actions[0]) if actions else None)

    if args.validate_only:
        print(json.dumps({
            "valid": True,
            "cases": len(frozen["cases"]),
            "gold_total": 85,
            "gold_scorable": 83,
            "corpus_article_roots": corpus,
            "new_llm_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 0

    rows = []
    for case in frozen["cases"]:
        parent, terms, selected, pool, planner, action = prepared[case["id"]]
        baseline = _baseline_arm(index, case, parent, selected, pool)
        input_state = {
            "question": case["question"],
            "parent_selected": [base._branch_dump(row) for row in selected],
            "parent_evidence_pool": [base._branch_dump(row) for row in pool],
            "planner_pool": [base._branch_dump(row) for row in planner],
            "frozen_parent_action": action,
            "terms": list(terms),
            "selected_cap": CAP,
            "pool_cap": POOL_CAP,
            "admission_cap": MAX_ADMISSIONS,
        }
        candidate = _candidate_arm(
            index, case, baseline, selected, pool, planner, terms, action)
        row = {
            "number": case["number"],
            "case_id": case["id"],
            "suite": case["suite"],
            "question": case["question"],
            "initial_state_sha256": base._json_sha(input_state),
            "input_state": input_state,
            "arms": {
                "baseline": baseline,
                "source-registry-admission": candidate,
            },
            "paired": base._paired(baseline, candidate),
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, input_state), encoding="utf-8")
        rows.append(row)
        _save(out, rows, corpus)
        base_hits = sum(bool(g["hit"]) for g in baseline["gold_results"]
                        if g["scorable"])
        candidate_hits = sum(bool(g["hit"]) for g in candidate["gold_results"]
                             if g["scorable"])
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"baseline={base_hits} candidate={candidate_hits} "
            f"raw={candidate['retrieval_meta'].get('raw_candidate_count', 0)} "
            f"promoted={len(candidate['retrieval_meta'].get('promoted') or [])}",
            flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
