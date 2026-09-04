#!/usr/bin/env python3
"""ADR-0071: select only preverified source span IDs over golden 61."""

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

from scripts import rag_claim_citation_selector_golden_61 as parent_runner


base = parent_runner.base
MODEL = "claude-haiku-4-5-20251001"
ADR_ID = "ADR-0071"
RUN_ID = "run-001"
ARMS = ("baseline", "verified-span-id-selector")
CAP = 20
POOL_CAP = 48
MAX_CALLS_TOTAL = 9
MAX_NON_GOLD_PROMOTIONS = 2
MAX_TOTAL_PROMOTIONS = 3
PARENT_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0070-claim-citation-relevance-selector/"
    "artifacts/run-001.json")
PARENT_RUN_SHA256 = (
    "8e7b82850fd78b27058f900021f6023d0d8f27efa8ed58ffa4eb00c7f521d8e4")
PARENT_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0070-claim-citation-relevance-selector/"
    "실험/manifest.json")
PARENT_MANIFEST_SHA256 = (
    "f85f64b79edb35416715fc48e212b3f9f27081f0d91448d2d79e6779de7d2165")
IMPLEMENTATION = Path(__import__("lawrag").__file__).resolve().parent / "core/rag/verified_span_selector.py"


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
    frozen, _run, _manifest = parent_runner._load_sources()
    for path, expected in (
        (PARENT_RUN, PARENT_RUN_SHA256),
        (PARENT_MANIFEST, PARENT_MANIFEST_SHA256),
    ):
        if not path.is_file() or _sha(path) != expected:
            raise ValueError(f"parent lineage mismatch: {path}")
    run = json.loads(PARENT_RUN.read_text("utf-8"))
    manifest = json.loads(PARENT_MANIFEST.read_text("utf-8"))
    if len(run.get("rows") or ()) != 61:
        raise ValueError("ADR-0070 parent must contain 61 rows")
    if (manifest.get("results") or {}).get("status") != "complete":
        raise ValueError("ADR-0070 parent is incomplete")
    return frozen, run, manifest


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest = json.loads((adr / "실험/manifest.json").read_text("utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    parent = next(iter((manifest.get("lineage") or {}).get("parents") or ()), {})
    if (parent.get("experiment_id") != "ADR-0070-experiment-v1"
            or parent.get("arm_id") != "claim-citation-relevance-selector"
            or parent.get("manifest_sha256") != PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0071 parent lineage mismatch")
    arm_ids = {item.get("id") for item in
               (manifest.get("design") or {}).get("arms") or ()}
    if set(ARMS) - arm_ids:
        raise ValueError("ADR-0071 arm mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if calls != [{
        "role": "verified_span_selector", "class": "product",
        "model": MODEL, "repeats": 1,
        "temperature": "provider_default_omitted",
    }]:
        raise ValueError("ADR-0071 LLM policy mismatch")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0071 must freeze 61 questions")
    if require_frozen:
        if not (manifest.get("design") or {}).get(
                "criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        if ((manifest.get("dataset") or {}).get("sha256")
                != base.PARENT_FROZEN_SHA256):
            raise ValueError("frozen dataset SHA mismatch")
        run = next((item for item in manifest.get("runs") or ()
                    if item.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        expected = (run.get("implementation_sha256") or {}).get(
            "lawrag/core/rag/verified_span_selector.py")
        if expected != _sha(IMPLEMENTATION):
            raise ValueError("implementation SHA is not frozen")
    return manifest


def _restore_rows(index, records: list[dict], terms: tuple[str, ...],
                  origin: str) -> list:
    return parent_runner._restore_rows(index, records, terms, origin)


def _baseline_arm(index, case: dict, parent: dict) -> dict:
    selected = deepcopy(parent.get("selected") or [])
    pool = base._coordinate_records(index, parent.get("internal_pool") or [])
    gold, all_hit, pool_all_hit = base._grade(case, selected, pool)
    stored = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in parent.get("gold_results") or () if row.get("scorable")]
    actual = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in gold if row.get("scorable")]
    if stored != actual:
        raise ValueError(f"{case['id']}: parent grading mismatch")
    return {
        "arm": "baseline",
        "source": "ADR-0070/run-001/claim-citation-relevance-selector",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": deepcopy(parent.get("retrieval_meta") or {}),
        "llm_calls": deepcopy(parent.get("llm_calls") or {}),
        "provider_usage": deepcopy(parent.get("provider_usage") or {}),
        "incremental_provider_usage": _zero_usage(),
        "wall_ms": float(parent.get("wall_ms") or 0),
        "parent_state_sha256": base._json_sha(parent),
        "runtime_error": "",
    }


def _candidate_arm(index, case: dict, baseline: dict, incumbent: list,
                   pool_rows: list, registry: list, target_claim: str, llm) -> dict:
    from lawrag.core.rag import verified_span_selector

    recording = base.RecordingLLM(llm)
    started = time.perf_counter()
    runtime_error = ""
    try:
        selected, meta = verified_span_selector.run(
            index, case["question"], recording, list(incumbent),
            list(pool_rows), list(registry), target_claim,
            cap=CAP, pool_cap=POOL_CAP)
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        selected = list(incumbent)
        meta = {
            "enabled": True, "ran": True, "status": "error",
            "reason": "runtime_error", "runtime_error": runtime_error,
            "hard_deletes": 0, "rejected": [], "promoted": [],
            "verified_spans": [], "validation_errors": [],
            "evidence_pool": [base._branch_dump(row) for row in pool_rows],
        }
    incremental_ms = (time.perf_counter() - started) * 1000
    selected_records = base._selected(selected)
    pool = base._coordinate_records(index, meta.get("evidence_pool") or [])
    gold, all_hit, pool_all_hit = base._grade(case, selected_records, pool)
    usage = base._usage(recording.audit, runtime_error=runtime_error)
    effective = base._sum_usage(baseline.get("provider_usage") or {}, usage)
    append_only = base._append_only_audit(
        base._coordinate_records(index, [base._branch_dump(row)
                                         for row in pool_rows]),
        selected_records, pool, meta)
    promoted = {(row.get("doc_id"), row.get("node"))
                for row in meta.get("promoted") or ()}
    accepted_rows = ((meta.get("selector_output") or {}).get("accepted") or ())
    accepted = {tuple(row.get("coordinate") or ()) for row in accepted_rows}
    span_integrity = True
    for item in accepted_rows:
        row = next((value for value in registry
                    if value.coordinate == tuple(item.get("coordinate") or ())), None)
        if row is None:
            span_integrity = False
            continue
        source = verified_span_selector._source(index, row)
        start, end = int(item.get("start", -1)), int(item.get("end", -1))
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if not (0 <= start <= end <= len(source)
                and source[start:end] == item.get("text")
                and digest == item.get("source_sha256")):
            span_integrity = False
    requested = ((meta.get("selector_output") or {}).get("requested") or {})
    schema_only = (
        isinstance(requested, dict)
        and set(requested) <= {"selected_span_ids", "remaining_gap"}
        and isinstance(requested.get("selected_span_ids", []), list)
    )
    selector_audit = {
        "promoted_subset_of_accepted_spans": promoted <= accepted,
        "server_span_integrity": span_integrity,
        "model_output_span_ids_only": schema_only,
        "promoted_count": len(promoted),
        "presented_span_count": len(meta.get("verified_spans") or ()),
        "validation_error_count": len(meta.get("validation_errors") or ()),
        "passed": promoted <= accepted and span_integrity and schema_only,
    }
    return {
        "arm": "verified-span-id-selector",
        "selected": selected_records,
        "selected_count": len(selected_records),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": meta,
        "llm_calls": recording.audit,
        "reused_parent_llm_calls_ref": "arms.baseline.llm_calls",
        "provider_usage": effective,
        "incremental_provider_usage": usage,
        "wall_ms": round(float(baseline.get("wall_ms") or 0)
                         + incremental_ms, 3),
        "incremental_wall_ms": round(incremental_ms, 3),
        "append_only_audit": append_only,
        "selector_audit": selector_audit,
        "runtime_error": runtime_error,
    }


def _promotion_stats(rows: list[dict], arm: str) -> dict:
    return parent_runner._promotion_stats(rows, arm)


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
        "promotions": {arm: _promotion_stats(rows, arm) for arm in ARMS},
    }
    baseline = result["arms"]["baseline"]
    candidate = result["arms"]["verified-span-id-selector"]
    calls = candidate["incremental_provider_usage"]["calls"]
    inputs = candidate["incremental_provider_usage"]["input_tokens"]
    baseline_noise = result["promotions"]["baseline"]["non_gold"]
    candidate_promotions = result["promotions"]["verified-span-id-selector"]
    candidate_noise = candidate_promotions["non_gold"]
    fsc = next((row for row in rows if row["case_id"] == "fsc-hard-003"), None)
    fsc_gold = [] if fsc is None else [
        item for item in fsc["arms"]["verified-span-id-selector"]
        ["gold_results"] if item.get("scorable") and item.get("article") == "제24조"]
    presented_spans = [
        row["arms"]["verified-span-id-selector"]["selector_audit"]
        ["presented_span_count"] for row in rows
        if row["arms"]["verified-span-id-selector"]
        ["incremental_provider_usage"]["calls"]
    ]
    baseline_contract_errors = sum(
        len(row["arms"]["baseline"]["retrieval_meta"].get(
            "validation_errors") or ()) for row in rows)
    candidate_contract_errors = sum(
        row["arms"]["verified-span-id-selector"]["selector_audit"]
        ["validation_error_count"] for row in rows)
    result["span_accounting"] = {
        "calls": len(presented_spans),
        "presented_total": sum(presented_spans),
        "presented_mean": round(statistics.mean(presented_spans), 3)
        if presented_spans else 0,
        "presented_p50": _percentile(presented_spans, .50),
        "presented_p95": _percentile(presented_spans, .95),
        "baseline_contract_errors": baseline_contract_errors,
        "candidate_contract_errors": candidate_contract_errors,
    }
    result["criteria"] = {
        "candidate_gold_at_least_66_of_83": (
            candidate["gold_article_hits"] >= 66),
        "selected_article_regression_zero": (
            result["paired_selected_articles"]["baseline_only"] == 0),
        "selected_case_regression_zero": (
            result["paired_cases"]["baseline_only"] == 0),
        "non_gold_promotions_not_worse_than_parent_2": (
            candidate_noise <= min(MAX_NON_GOLD_PROMOTIONS, baseline_noise)),
        "total_promotions_at_most_3": (
            candidate_promotions["total"] <= MAX_TOTAL_PROMOTIONS),
        "fsc_hard_003_article_24_retained": (
            len(fsc_gold) == 1 and bool(fsc_gold[0].get("hit"))),
        "append_only_zero_violations": all(
            row["arms"]["verified-span-id-selector"]
            ["append_only_audit"]["passed"] for row in rows),
        "selector_promotions_server_grounded": all(
            row["arms"]["verified-span-id-selector"]
            ["selector_audit"]["passed"] for row in rows),
        "span_id_validation_errors_zero": candidate_contract_errors == 0,
        "model_output_span_ids_only": all(
            row["arms"]["verified-span-id-selector"]
            ["selector_audit"]["model_output_span_ids_only"] for row in rows),
        "product_calls_total_at_most_9": calls <= MAX_CALLS_TOTAL,
        "product_calls_at_most_1_per_case": all(
            row["arms"]["verified-span-id-selector"]
            ["incremental_provider_usage"]["calls"] <= 1 for row in rows),
        "provider_and_runtime_errors_zero": (
            candidate["incremental_provider_usage"]["errors"] == 0),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "internal_pool_cap_48": all(
            row["arms"]["verified-span-id-selector"]
            ["internal_pool_count"] <= POOL_CAP for row in rows),
        "estimated_total_latency_p95_at_most_1_1x": (
            candidate["wall_ms_p95"] <= baseline["wall_ms_p95"] * 1.1
            if baseline["wall_ms_p95"] else False),
        "incremental_input_mean_per_call_at_most_30000": (
            inputs / calls <= 30_000 if calls else False),
    }
    result["target_pass"] = bool(rows) and all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict, input_state: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["verified-span-id-selector"]
    grading = {
        "baseline": baseline["gold_results"],
        "verified-span-id-selector": candidate["gold_results"],
        "paired": row["paired"],
    }
    return f"""# ADR-0071 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `{RUN_ID}`
- arm: `baseline`, `verified-span-id-selector`
- model: `{MODEL}`
- initial state SHA-256: `{row['initial_state_sha256']}`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

채점 전용이며 selector 입력에는 공개하지 않았다.

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps(input_state, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline — 부모 ADR-0070에서 재사용한 실제 selector 호출

```json
{json.dumps(baseline.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

### verified-span-id-selector

```json
{json.dumps(candidate.get('llm_calls') or [], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — selector

candidate 호출 목록에 system, user, 동적 span_id enum schema, provider 원응답, structured
output, usage와 지연을 보존했다. 별도 repair/judge 호출은 없다.

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
    'selector_audit': candidate['selector_audit'],
    'usage': candidate['incremental_provider_usage'],
    'latency_ms': candidate['incremental_wall_ms'],
}, ensure_ascii=False, indent=2)}
```
"""


def _save(out: Path, rows: list[dict], corpus: int) -> None:
    payload = {
        "schema_version": "verified-span-selector-golden-61-run-v1",
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
            "direct_parent": (
                "ADR-0070-experiment-v1/claim-citation-relevance-selector"),
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": _sha(IMPLEMENTATION),
        "model_policy": {"product_model": MODEL, "judge": None},
        "contract": {
            "selected_cap": CAP,
            "internal_pool_cap": POOL_CAP,
            "max_product_calls_total": MAX_CALLS_TOTAL,
            "gold_hidden_from_selector": True,
            "basis_exchange": False,
            "source_registry_append_only": True,
            "model_may_emit_free_quote": False,
            "model_may_emit_coordinate": False,
            "selection_schema": "dynamic_preverified_span_id_enum",
        },
        "summary": _summary(rows, corpus),
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


def _validate_resume(blob: dict) -> list[dict]:
    if blob.get("schema_version") != "verified-span-selector-golden-61-run-v1":
        raise ValueError("resume artifact schema mismatch")
    lineage = blob.get("source_lineage") or {}
    if (lineage.get("parent_run_sha256") != PARENT_RUN_SHA256
            or lineage.get("frozen_sha256") != base.PARENT_FROZEN_SHA256):
        raise ValueError("resume lineage mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume requires exact runner SHA")
    rows = list(blob.get("rows") or ())
    if len({row.get("case_id") for row in rows}) != len(rows):
        raise ValueError("duplicate resume cases")
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
    frozen, parent_run, _parent_manifest = _load_sources()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod

    index = index_mod.current().scoped(None)
    corpus = base._article_roots(index)
    parent_by_case = {row["case_id"]: row for row in parent_run["rows"]}
    prepared = {}
    for case in frozen["cases"]:
        row = parent_by_case[case["id"]]
        parent = row["arms"]["claim-citation-relevance-selector"]
        state = row["input_state"]
        terms = tuple(state.get("terms") or ())
        incumbent = _restore_rows(
            index, state.get("parent_selected") or [], terms,
            "adr0070-incumbent")
        pool = _restore_rows(
            index, state.get("parent_evidence_pool") or [], terms,
            "adr0070-evidence-pool")
        registry = _restore_rows(
            index, state.get("source_registry_candidates") or [], terms,
            "source-registry")
        target = str(state.get("target_claim") or case["question"])
        prepared[case["id"]] = (
            parent, terms, incumbent, pool, registry, target)

    if args.validate_only:
        callable_cases = sum(bool(value[4]) and len(value[2]) < CAP
                             for value in prepared.values())
        print(json.dumps({
            "valid": True,
            "cases": len(frozen["cases"]),
            "gold_total": 85,
            "gold_scorable": 83,
            "corpus_article_roots": corpus,
            "registry_candidates": sum(len(value[4])
                                       for value in prepared.values()),
            "planned_selector_calls": callable_cases,
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
        rows = _validate_resume(json.loads(out.read_text("utf-8")))
    completed = {row["case_id"] for row in rows}
    for case in frozen["cases"]:
        if case["id"] in completed:
            continue
        parent, terms, incumbent, pool, registry, target = prepared[case["id"]]
        baseline = _baseline_arm(index, case, parent)
        input_state = {
            "question": case["question"],
            "parent_selected": [base._branch_dump(row) for row in incumbent],
            "parent_evidence_pool": [base._branch_dump(row) for row in pool],
            "source_registry_candidates": [base._branch_dump(row)
                                             for row in registry],
            "target_claim": target,
            "terms": list(terms),
            "selected_cap": CAP,
            "pool_cap": POOL_CAP,
            "span_contract": {
                "source_window_chars": 2400,
                "span_chars": 520,
                "spans_per_source_max": 6,
                "model_output": "selected_span_ids_only",
            },
        }
        candidate = _candidate_arm(
            index, case, baseline, incumbent, pool, registry, target, real)
        row = {
            "number": case["number"],
            "case_id": case["id"],
            "suite": case["suite"],
            "question": case["question"],
            "initial_state_sha256": base._json_sha(input_state),
            "input_state": input_state,
            "arms": {
                "baseline": baseline,
                "verified-span-id-selector": candidate,
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
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"registry={len(registry)} "
            f"spans={candidate['selector_audit']['presented_span_count']} "
            f"selected={len(candidate['retrieval_meta'].get('promoted') or [])} "
            f"calls={candidate['incremental_provider_usage']['calls']}",
            flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
