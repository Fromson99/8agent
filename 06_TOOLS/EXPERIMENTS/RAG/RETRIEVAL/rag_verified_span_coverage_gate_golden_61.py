#!/usr/bin/env python3
"""ADR-0078: verified-span coverage gate and bounded routed exploration."""

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

from lawrag.core.rag import verified_span_coverage_gate as gate
from scripts import rag_proof_basis_exchange_golden_61 as basis_runner
from scripts import rag_verified_span_selector_golden_61 as span_runner


base = span_runner.base
ADR_ID = "ADR-0078"
RUN_ID = "run-001"
MODEL = "claude-haiku-4-5-20251001"
ARMS = ("baseline", "coverage-gate-only", "coverage-routed-explore")
CAP = 20

FROZEN = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0064-feedback-explore-golden-61/artifacts/frozen-cases.json"
FROZEN_SHA256 = "393ced7e9428aea5d6cbc7ed3383fe10dda199da1cc1bf7fcf0fd57edff9b0cb"
PARENT_72_MANIFEST = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0072-provider-compatible-span-id-selector/실험/manifest.json"
PARENT_72_MANIFEST_SHA256 = "f68429a86fede8b7ef7843359081042a7e414cce50134f13c6a1000006db03f2"
PARENT_72_RUN = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0072-provider-compatible-span-id-selector/artifacts/run-001.json"
PARENT_72_RUN_SHA256 = "b081aff537efec908aba659b2a718a191c55c59664f4fd83dd20d8dc36a26e66"
PARENT_68_MANIFEST = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/실험/manifest.json"
PARENT_68_MANIFEST_SHA256 = "889255d1753ab9e1b9817fbcf5e7bc2af8eac29c4e7ab0019908ef1dda7d0779"
PARENT_68_RUN = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/artifacts/run-001.json"
PARENT_68_RUN_SHA256 = "d751f88febc98a1537083dd5a4e93ebc2cfc40b40137a451fa359badc648d38b"
PARENT_73_MANIFEST = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0073-proof-contribution-basis-exchange/실험/manifest.json"
PARENT_73_MANIFEST_SHA256 = "21ca70dc6bcf8dfdee130c9f58bd71f891c8a0010a2aed13c2c40b22bc0098c6"
PARENT_74_MANIFEST = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0074-missing-gold-reachability-audit/실험/manifest.json"
PARENT_74_MANIFEST_SHA256 = "5cb8fd12a8316faa0b23eae79536a91abb66a146f776165c73fb698b3cdb8c33"
IMPLEMENTATIONS = (
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/verified_span_coverage_gate.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/provider_compatible_span_selector.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/verified_span_selector.py",
)

_BANNED_PRODUCT_KEYS = frozenset({
    "gold_results", "paired", "expected_articles", "reference_answer",
    "case_all_gold_hit", "case_all_gold_internal_pool_hit",
})


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, round((len(ordered) - 1) * ratio)))]


def _zero_usage() -> dict:
    return {key: 0 for key in (
        "calls", "input_tokens", "output_tokens", "duration_ms", "errors",
        "provider_errors", "recovered_errors", "unrecovered_errors")}


def _contains_banned_key(value: object) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & _BANNED_PRODUCT_KEYS) or any(
            _contains_banned_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_banned_key(item) for item in value)
    return False


def _load_sources() -> tuple[dict, dict, dict]:
    expected = (
        (FROZEN, FROZEN_SHA256),
        (PARENT_72_MANIFEST, PARENT_72_MANIFEST_SHA256),
        (PARENT_72_RUN, PARENT_72_RUN_SHA256),
        (PARENT_68_MANIFEST, PARENT_68_MANIFEST_SHA256),
        (PARENT_68_RUN, PARENT_68_RUN_SHA256),
        (PARENT_73_MANIFEST, PARENT_73_MANIFEST_SHA256),
        (PARENT_74_MANIFEST, PARENT_74_MANIFEST_SHA256),
    )
    for path, digest in expected:
        actual = _sha(path)
        if actual != digest:
            raise ValueError(f"frozen source hash mismatch: {path}: {actual}")
    frozen = json.loads(FROZEN.read_text("utf-8"))
    run72 = json.loads(PARENT_72_RUN.read_text("utf-8"))
    run68 = json.loads(PARENT_68_RUN.read_text("utf-8"))
    if not (len(frozen.get("cases") or ()) == len(run72.get("rows") or ())
            == len(run68.get("rows") or ()) == 61):
        raise ValueError("ADR-0078 requires exact frozen 61-case lineage")
    return frozen, run72, run68


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest = json.loads((adr / "실험/manifest.json").read_text("utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    expected_parents = {
        ("ADR-0072-experiment-v1", "verified-span-id-selector"):
            ("merged_from", PARENT_72_MANIFEST_SHA256),
        ("ADR-0068-experiment-v1", "recall-first-union"):
            ("merged_from", PARENT_68_MANIFEST_SHA256),
    }
    actual_parents = {
        (row.get("experiment_id"), row.get("arm_id")):
            (row.get("relation"), row.get("manifest_sha256"))
        for row in (manifest.get("lineage") or {}).get("parents") or ()
    }
    if actual_parents != expected_parents:
        raise ValueError("ADR-0078 parent lineage mismatch")
    arm_ids = {row.get("id") for row in
               (manifest.get("design") or {}).get("arms") or ()}
    if arm_ids != set(ARMS):
        raise ValueError("ADR-0078 arm mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if calls != [
        {"role": "verified_span_coverage_gate", "class": "product",
         "model": MODEL, "repeats": 1,
         "temperature": "provider_default_omitted"},
        {"role": "routed_verified_span_selector", "class": "product",
         "model": MODEL, "repeats": "conditional_at_most_1",
         "temperature": "provider_default_omitted"},
    ]:
        raise ValueError("ADR-0078 LLM policy mismatch")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0078 must freeze 61 questions")
    if require_frozen:
        if not (manifest.get("design") or {}).get("criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        dataset = manifest.get("dataset") or {}
        if (dataset.get("sha256") != FROZEN_SHA256
                or dataset.get("parent_72_run_sha256") != PARENT_72_RUN_SHA256
                or dataset.get("route_pool_run_sha256") != PARENT_68_RUN_SHA256):
            raise ValueError("ADR-0078 frozen dataset lineage mismatch")
        run = next((row for row in manifest.get("runs") or ()
                    if row.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        hashes = run.get("implementation_sha256") or {}
        for path in IMPLEMENTATIONS:
            relative = str(path.relative_to(ROOT))
            if hashes.get(relative) != _sha(path):
                raise ValueError(f"implementation SHA is not frozen: {relative}")
    return manifest


def _safe_projection(row72: dict, row68: dict) -> dict:
    arm72 = row72["arms"]["verified-span-id-selector"]
    arm68 = row68["arms"]["recall-first-union"]
    state68 = row68.get("input_state") or {}
    value = {
        "number": row72["number"],
        "case_id": row72["case_id"],
        "suite": row72["suite"],
        "question": row72["question"],
        "terms": list(state68.get("terms") or ()),
        "incumbent": deepcopy(arm72.get("selected") or []),
        "route_pool": deepcopy(arm68.get("internal_pool") or []),
        "selected_cap": CAP,
        "gate_contract": {
            "output": "decision + supporting_span_ids + gap_type + route",
            "coordinates_or_free_search_text": False,
            "routes": list(gate.ROUTES),
            "one_route_max": True,
        },
    }
    if _contains_banned_key(value):
        raise AssertionError("gold field crossed product projection boundary")
    return value


def _restore(index, records: list[dict], terms: tuple[str, ...], origin: str):
    return basis_runner._restore(index, records, terms, origin=origin)


def _baseline_arm(case: dict, parent_arm: dict, pool_records: list[dict]) -> dict:
    selected = deepcopy(parent_arm.get("selected") or [])
    pool = deepcopy(pool_records)
    gold, all_hit, pool_all_hit = basis_runner._grade(case, selected, pool)
    stored = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in parent_arm.get("gold_results") or ()
              if row.get("scorable")]
    actual = [(row.get("doc_id"), row.get("node"), row.get("hit"))
              for row in gold if row.get("scorable")]
    if stored != actual:
        raise ValueError(f"{case['id']}: ADR-0072 grading replay mismatch")
    return {
        "arm": "baseline",
        "source": "ADR-0072/run-001/verified-span-id-selector exact replay",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": deepcopy(parent_arm.get("retrieval_meta") or {}),
        "llm_calls": deepcopy(parent_arm.get("llm_calls") or []),
        "provider_usage": deepcopy(parent_arm.get("provider_usage") or {}),
        "incremental_provider_usage": _zero_usage(),
        "wall_ms": float(parent_arm.get("wall_ms") or 0),
        "runtime_error": "",
    }


def _make_arm(case: dict, arm_id: str, baseline: dict, selected_rows,
              pool_rows, meta: dict, calls: list[dict], incremental_ms: float,
              runtime_error: str) -> dict:
    selected = basis_runner._selected(list(selected_rows))
    pool = basis_runner._pool(list(pool_rows))
    gold, all_hit, pool_all_hit = basis_runner._grade(case, selected, pool)
    usage = base._usage(calls, runtime_error=runtime_error)
    return {
        "arm": arm_id,
        "source": "ADR-0072 incumbent + ADR-0068 frozen route pool",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": meta,
        "llm_calls": calls,
        "provider_usage": base._sum_usage(
            baseline.get("provider_usage") or {}, usage),
        "incremental_provider_usage": usage,
        "wall_ms": round(float(baseline.get("wall_ms") or 0) + incremental_ms, 3),
        "incremental_wall_ms": round(incremental_ms, 3),
        "runtime_error": runtime_error,
    }


def _run_case(index, case: dict, projection: dict, baseline: dict, real):
    terms = tuple(projection["terms"])
    incumbent = _restore(index, projection["incumbent"], terms, "adr0072-incumbent")
    route_pool = _restore(index, projection["route_pool"], terms, "adr0068-route-pool")
    recording = base.RecordingLLM(real)
    started = time.perf_counter()
    runtime_error = ""
    try:
        decision, gate_meta = gate.judge(
            index, case["question"], recording, incumbent)
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        decision = {
            "decision": "insufficient", "supporting_span_ids": [],
            "supporting_spans": [], "gap_type": "other", "route": "none",
            "missing": ["coverage gate runtime error"], "reason": runtime_error,
        }
        gate_meta = {"ran": True, "verified_spans": [],
                     "presented_span_count": 0,
                     "validation_errors": [runtime_error]}
    gate_ms = (time.perf_counter() - started) * 1000
    gate_calls = list(recording.audit)
    gate_only = _make_arm(
        case, "coverage-gate-only", baseline, incumbent, route_pool,
        {"decision": decision, "gate": gate_meta, "selected_mutated": False},
        gate_calls, gate_ms, runtime_error)

    explore_recording = base.RecordingLLM(real)
    explore_started = time.perf_counter()
    explore_error = ""
    try:
        explored, explore_meta = gate.explore(
            index, case["question"], explore_recording, incumbent,
            route_pool, decision, cap=CAP)
    except Exception as exc:
        explore_error = f"{type(exc).__name__}: {exc}"
        explored = incumbent
        explore_meta = {
            "ran": True, "reason": "runtime_error", "decision": decision,
            "route": decision.get("route"), "route_candidates": [],
            "promoted": [], "hard_deletes": 0, "baseline_preserved": True,
            "validation_errors": [explore_error],
        }
    explore_ms = (time.perf_counter() - explore_started) * 1000
    all_calls = [*gate_calls, *explore_recording.audit]
    meta = {"decision": decision, "gate": gate_meta, "explore": explore_meta}
    candidate = _make_arm(
        case, "coverage-routed-explore", baseline, explored, route_pool,
        meta, all_calls, gate_ms + explore_ms,
        "; ".join(filter(None, (runtime_error, explore_error))))
    base_coords = {(row["doc_id"], row["node"]) for row in baseline["selected"]}
    candidate_coords = {(row["doc_id"], row["node"]) for row in candidate["selected"]}
    pool_coords = {(row["doc_id"], row["node"]) for row in candidate["internal_pool"]}
    candidate["append_only_audit"] = {
        "baseline_subset_of_candidate": base_coords <= candidate_coords,
        "candidate_subset_of_pool": candidate_coords <= pool_coords,
        "hard_deletes_zero": not (base_coords - candidate_coords),
        "passed": (base_coords <= candidate_coords
                   and candidate_coords <= pool_coords),
    }
    return gate_only, candidate


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    values = [row["arms"][arm] for row in rows]
    scored = [gold for value in values for gold in value["gold_results"]
              if gold["scorable"]]
    cases = [value for value in values if value["case_all_gold_hit"] is not None]
    counts = [value["selected_count"] for value in values]
    pool_counts = [value["internal_pool_count"] for value in values]
    walls = [float(value.get("wall_ms") or 0) for value in values]
    usage = _zero_usage()
    for value in values:
        usage = base._sum_usage(
            usage, value.get("incremental_provider_usage") or {})
    hits = sum(bool(item["hit"]) for item in scored)
    pool_hits = sum(bool(item["internal_pool_hit"]) for item in scored)
    return {
        "scorable_cases": len(cases),
        "case_all_gold_hits": sum(bool(value["case_all_gold_hit"])
                                  for value in cases),
        "gold_article_instances": len(scored),
        "gold_article_hits": hits,
        "article_instance_recall_at_20": round(hits / len(scored), 6),
        "internal_pool_gold_hits": pool_hits,
        "internal_pool_recall": round(pool_hits / len(scored), 6),
        "selected_mean": round(statistics.mean(counts), 3),
        "selected_p50": statistics.median(counts),
        "selected_p95": _percentile(counts, .95),
        "internal_pool_mean": round(statistics.mean(pool_counts), 3),
        "internal_pool_p50": statistics.median(pool_counts),
        "internal_pool_p95": _percentile(pool_counts, .95),
        "selectivity": round(statistics.mean(counts) / corpus, 8),
        "wall_ms_p50": round(statistics.median(walls), 3),
        "wall_ms_p95": round(_percentile(walls, .95), 3),
        "incremental_provider_usage": usage,
    }


def _comparison(rows: list[dict], left: str, right: str) -> dict:
    article = [item["status"] for row in rows
               for item in row["paired"][f"{left}__{right}"]["selected_articles"]]
    cases = [row["paired"][f"{left}__{right}"]["case_all_gold"] for row in rows]
    return {
        "baseline_arm": left, "candidate_arm": right,
        "candidate_only_articles": article.count("candidate_only"),
        "baseline_only_articles": article.count("baseline_only"),
        "both_articles": article.count("both"),
        "neither_articles": article.count("neither"),
        "candidate_only_cases": cases.count("candidate_only"),
        "baseline_only_cases": cases.count("baseline_only"),
        "both_cases": cases.count("both"),
        "neither_cases": cases.count("neither"),
    }


def _gate_diagnostics(rows: list[dict]) -> dict:
    reachable_with_slot = 0
    explored_reachable_with_slot = 0
    false_explore = 0
    explore_cases = 0
    productive_cases = 0
    promotions = 0
    gold_promotions = 0
    routes: dict[str, int] = {}
    gate_contract_errors = selector_contract_errors = 0
    presented = []
    for row in rows:
        baseline = row["arms"]["baseline"]
        candidate = row["arms"]["coverage-routed-explore"]
        decision = candidate["retrieval_meta"]["decision"]
        route = decision.get("route") or "none"
        routes[route] = routes.get(route, 0) + 1
        explored = decision.get("decision") == "explore"
        explore_cases += int(explored)
        false_explore += int(bool(baseline["case_all_gold_hit"]) and explored)
        missing = [gold for gold in baseline["gold_results"]
                   if gold.get("scorable") and not gold.get("hit")]
        reachable = any(gold.get("internal_pool_hit") for gold in missing)
        has_slot = baseline["selected_count"] < CAP
        if missing and reachable and has_slot:
            reachable_with_slot += 1
            explored_reachable_with_slot += int(explored)
        paired = row["paired"]["baseline__coverage-routed-explore"]
        gains = sum(item["status"] == "candidate_only"
                    for item in paired["selected_articles"])
        productive_cases += int(gains > 0)
        base_coords = {(item["doc_id"], item["node"])
                       for item in baseline["selected"]}
        promoted = [item for item in candidate["selected"]
                    if (item["doc_id"], item["node"]) not in base_coords]
        promotions += len(promoted)
        gold_coords = {(item["doc_id"], item["node"])
                       for item in candidate["gold_results"]
                       if item.get("scorable")}
        gold_promotions += sum((item["doc_id"], item["node"]) in gold_coords
                               for item in promoted)
        gate_meta = candidate["retrieval_meta"]["gate"]
        presented.append(int(gate_meta.get("presented_span_count") or 0))
        gate_contract_errors += len(gate_meta.get("validation_errors") or ())
        explore_meta = candidate["retrieval_meta"]["explore"]
        selector_contract_errors += len(
            explore_meta.get("validation_errors") or ())
    return {
        "reachable_missing_cases_with_slot": reachable_with_slot,
        "explored_reachable_missing_cases_with_slot": explored_reachable_with_slot,
        "reachable_explore_recall": round(
            explored_reachable_with_slot / reachable_with_slot, 6)
            if reachable_with_slot else None,
        "false_explore_cases": false_explore,
        "explore_cases": explore_cases,
        "productive_explore_cases": productive_cases,
        "routes": routes,
        "promotions": promotions,
        "gold_promotions": gold_promotions,
        "non_gold_promotions": promotions - gold_promotions,
        "promotion_precision": round(gold_promotions / promotions, 6)
            if promotions else None,
        "gate_contract_errors": gate_contract_errors,
        "selector_contract_errors": selector_contract_errors,
        "presented_spans_total": sum(presented),
        "presented_spans_mean": round(statistics.mean(presented), 3),
        "presented_spans_p50": _percentile(presented, .5),
        "presented_spans_p95": _percentile(presented, .95),
    }


def _summary(rows: list[dict], corpus: int) -> dict:
    arms = {arm: _arm_summary(rows, arm, corpus) for arm in ARMS}
    comparisons = [
        _comparison(rows, "baseline", "coverage-gate-only"),
        _comparison(rows, "baseline", "coverage-routed-explore"),
        _comparison(rows, "coverage-gate-only", "coverage-routed-explore"),
    ]
    primary = comparisons[1]
    diagnostics = _gate_diagnostics(rows)
    usage = arms["coverage-routed-explore"]["incremental_provider_usage"]
    criteria = {
        "candidate_gold_hits_at_least_67_of_83":
            arms["coverage-routed-explore"]["gold_article_hits"] >= 67,
        "baseline_article_regression_zero":
            primary["baseline_only_articles"] == 0,
        "baseline_case_regression_zero": primary["baseline_only_cases"] == 0,
        "productive_explore_cases_at_least_1":
            diagnostics["productive_explore_cases"] >= 1,
        "reachable_explore_recall_at_least_half":
            (diagnostics["reachable_explore_recall"] or 0) >= .5,
        "false_explore_cases_at_most_7":
            diagnostics["false_explore_cases"] <= 7,
        "non_gold_promotions_at_most_3":
            diagnostics["non_gold_promotions"] <= 3,
        "gate_and_selector_contract_errors_zero":
            diagnostics["gate_contract_errors"] == 0
            and diagnostics["selector_contract_errors"] == 0,
        "append_only_and_cap_20": all(
            row["arms"]["coverage-routed-explore"]["append_only_audit"]["passed"]
            and row["arms"]["coverage-routed-explore"]["selected_count"] <= CAP
            for row in rows),
        "product_calls_at_most_2_per_case": all(
            row["arms"]["coverage-routed-explore"]
            ["incremental_provider_usage"]["calls"] <= 2 for row in rows),
        "provider_and_runtime_errors_zero": usage["errors"] == 0,
        "incremental_input_mean_at_most_25000_per_call":
            (usage["input_tokens"] / usage["calls"] <= 25_000)
            if usage["calls"] else False,
        "estimated_total_latency_p95_at_most_1_35x":
            arms["coverage-routed-explore"]["wall_ms_p95"]
            <= arms["baseline"]["wall_ms_p95"] * 1.35,
    }
    return {
        "cases": len(rows), "corpus_article_roots": corpus,
        "arms": arms, "comparisons": comparisons,
        "gate_diagnostics": diagnostics,
        "criteria": criteria,
        "target_pass": bool(rows) and all(criteria.values()),
    }


def _question_markdown(case: dict, row: dict, projection: dict) -> str:
    baseline = row["arms"]["baseline"]
    gate_only = row["arms"]["coverage-gate-only"]
    candidate = row["arms"]["coverage-routed-explore"]
    return f"""# ADR-0078 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `run-001`
- arms: `baseline`, `coverage-gate-only`, `coverage-routed-explore`
- model: `{MODEL}`
- product input SHA-256: `{row['input_state_sha256']}`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

{case.get('reference_answer') or '(기준답변 없음)'}

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력 원값 — whitelist projection

`gold_results`, `expected_articles`, `reference_answer`, `paired`는 아래 제품 입력에 없다.

```json
{json.dumps(projection, ensure_ascii=False, indent=2)}
```

## 5. Baseline exact replay

```json
{json.dumps({'selected': baseline['selected'], 'gold_results': baseline['gold_results']}, ensure_ascii=False, indent=2)}
```

## 6. Coverage gate 제품 호출

system, user, 동적 V span enum schema, provider 원응답, structured output, usage와 지연 원문이다.

```json
{json.dumps(gate_only['llm_calls'], ensure_ascii=False, indent=2)}
```

## 7. Gate-only 판정

```json
{json.dumps(gate_only['retrieval_meta'], ensure_ascii=False, indent=2)}
```

## 8. Routed explore와 verified-span selector 제품 호출

gate 호출을 포함하며, 두 번째 항목이 있으면 선택된 route의 S span selector 호출이다.

```json
{json.dumps(candidate['llm_calls'], ensure_ascii=False, indent=2)}
```

## 9. Routed explore 결과

```json
{json.dumps({'selected': candidate['selected'], 'retrieval_meta': candidate['retrieval_meta'], 'append_only_audit': candidate['append_only_audit']}, ensure_ascii=False, indent=2)}
```

## 10. 결정론적 exact 채점과 paired 판정

```json
{json.dumps({'gold_results': {arm: row['arms'][arm]['gold_results'] for arm in ARMS}, 'paired': row['paired']}, ensure_ascii=False, indent=2)}
```
"""


def _atomic_save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    os.replace(temporary, path)


def _artifact(rows: list[dict], corpus: int) -> dict:
    return {
        "schema_version": "verified-span-coverage-gate-golden-61-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(FROZEN.relative_to(ROOT)),
            "frozen_sha256": FROZEN_SHA256,
            "parent_72_run_sha256": PARENT_72_RUN_SHA256,
            "route_pool_68_run_sha256": PARENT_68_RUN_SHA256,
            "parent_73_manifest_sha256": PARENT_73_MANIFEST_SHA256,
            "parent_74_manifest_sha256": PARENT_74_MANIFEST_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": {
            str(path.relative_to(ROOT)): _sha(path) for path in IMPLEMENTATIONS},
        "model_policy": {"product_model": MODEL, "judge": None},
        "contract": {
            "selected_cap": CAP, "one_gate_call_per_case": True,
            "one_route_max": True, "one_selector_call_max": True,
            "server_owned_current_span_ids": True,
            "server_owned_candidate_span_ids": True,
            "free_coordinates": False, "free_citations": False,
            "free_search_query": False, "append_only": True,
            "gold_hidden_from_product_roles": True,
        },
        "summary": _summary(rows, corpus), "rows": rows,
    }


def _validate_resume(blob: dict, projections: list[dict]) -> list[dict]:
    if blob.get("schema_version") != "verified-span-coverage-gate-golden-61-v1":
        raise ValueError("resume artifact schema mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume runner SHA mismatch")
    expected_impl = {str(path.relative_to(ROOT)): _sha(path)
                     for path in IMPLEMENTATIONS}
    if blob.get("implementation_sha256") != expected_impl:
        raise ValueError("resume implementation SHA mismatch")
    rows = list(blob.get("rows") or ())
    if [row.get("case_id") for row in rows] != [
            row["case_id"] for row in projections[:len(rows)]]:
        raise ValueError("resume rows are not exact frozen prefix")
    for row, projection in zip(rows, projections):
        if row.get("input_state_sha256") != _json_sha(projection):
            raise ValueError(f"resume input mismatch: {row.get('case_id')}")
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
    frozen, run72, run68 = _load_sources()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod
    index = index_mod.current().scoped(None)
    corpus = basis_runner._article_roots(index)
    by72 = {row["case_id"]: row for row in run72["rows"]}
    by68 = {row["case_id"]: row for row in run68["rows"]}
    projections = [
        _safe_projection(by72[case["id"]], by68[case["id"]])
        for case in frozen["cases"]
    ]

    if args.validate_only:
        reachable_with_slot = 0
        for case, projection in zip(frozen["cases"], projections):
            baseline = _baseline_arm(
                case, by72[case["id"]]["arms"]["verified-span-id-selector"],
                projection["route_pool"])
            missing = [item for item in baseline["gold_results"]
                       if item.get("scorable") and not item.get("hit")]
            if (baseline["selected_count"] < CAP
                    and any(item.get("internal_pool_hit") for item in missing)):
                reachable_with_slot += 1
        print(json.dumps({
            "valid": True, "cases": 61, "gold_total": 85,
            "gold_scorable": 83, "baseline_gold_hits": 66,
            "route_pool_gold_ceiling": 68,
            "reachable_missing_cases_with_slot": reachable_with_slot,
            "planned_gate_calls": 61, "max_selector_calls": 61,
            "corpus_article_roots": corpus,
        }, ensure_ascii=False, indent=2))
        return 0

    from lawrag.core import llm as llm_mod
    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError("configured product LLM is unavailable")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")

    if out.exists() and not args.resume:
        raise FileExistsError(
            f"refusing to overwrite artifact without --resume: {out}")
    rows = []
    if args.resume and out.exists():
        rows = _validate_resume(json.loads(out.read_text("utf-8")), projections)
    completed = {row["case_id"] for row in rows}
    for case, projection in zip(frozen["cases"], projections):
        if case["id"] in completed:
            continue
        parent = by72[case["id"]]["arms"]["verified-span-id-selector"]
        baseline = _baseline_arm(case, parent, projection["route_pool"])
        gate_only, candidate = _run_case(
            index, case, projection, baseline, real)
        arms = {
            "baseline": baseline,
            "coverage-gate-only": gate_only,
            "coverage-routed-explore": candidate,
        }
        paired = {
            "baseline__coverage-gate-only":
                basis_runner._paired(baseline, gate_only),
            "baseline__coverage-routed-explore":
                basis_runner._paired(baseline, candidate),
            "coverage-gate-only__coverage-routed-explore":
                basis_runner._paired(gate_only, candidate),
        }
        row = {
            "number": case["number"], "case_id": case["id"],
            "suite": case["suite"], "question": case["question"],
            "input_state_sha256": _json_sha(projection),
            "product_input_keys": sorted(projection),
            "arms": arms, "paired": paired,
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, projection), encoding="utf-8")
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _atomic_save(out, _artifact(rows, corpus))
        decision = candidate["retrieval_meta"]["decision"]
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"decision={decision.get('decision')} route={decision.get('route')} "
            f"promoted={len(candidate['retrieval_meta']['explore'].get('promoted') or [])} "
            f"calls={candidate['incremental_provider_usage']['calls']}",
            flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
