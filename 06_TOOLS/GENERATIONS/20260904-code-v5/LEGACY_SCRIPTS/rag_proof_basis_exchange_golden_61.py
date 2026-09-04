#!/usr/bin/env python3
"""ADR-0073: proof-cell basis completion/exchange over ADR-0068 pool."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
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

from lawrag.core.rag import legal_coordinates, proof_basis_exchange
from lawrag.core.rag import termexplore


ADR_ID = "ADR-0073"
RUN_ID = "run-001"
ARMS = ("baseline", "verified-add-only", "proof-basis-exchange")
CAP = 20
POOL_CAP = 96

PARENT_68_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/실험/manifest.json")
PARENT_68_MANIFEST_SHA256 = (
    "889255d1753ab9e1b9817fbcf5e7bc2af8eac29c4e7ab0019908ef1dda7d0779")
PARENT_68_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/artifacts/run-001.json")
PARENT_68_RUN_SHA256 = (
    "d751f88febc98a1537083dd5a4e93ebc2cfc40b40137a451fa359badc648d38b")
PARENT_72_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0072-provider-compatible-span-id-selector/실험/manifest.json")
PARENT_72_MANIFEST_SHA256 = (
    "f68429a86fede8b7ef7843359081042a7e414cce50134f13c6a1000006db03f2")
PARENT_72_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0072-provider-compatible-span-id-selector/artifacts/run-001.json")
PARENT_72_RUN_SHA256 = (
    "b081aff537efec908aba659b2a718a191c55c59664f4fd83dd20d8dc36a26e66")
FROZEN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0064-feedback-explore-golden-61/artifacts/frozen-cases.json")
FROZEN_SHA256 = (
    "393ced7e9428aea5d6cbc7ed3383fe10dda199da1cc1bf7fcf0fd57edff9b0cb")
IMPLEMENTATIONS = (
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/proof_basis_exchange.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/grounded_witness.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/legal_coordinates.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/relations.py",
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
    return {
        "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "duration_ms": 0, "errors": 0,
    }


def _article_roots(index) -> int:
    return sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
    )


def _load_sources() -> tuple[dict, dict]:
    expected = (
        (PARENT_68_MANIFEST, PARENT_68_MANIFEST_SHA256),
        (PARENT_68_RUN, PARENT_68_RUN_SHA256),
        (PARENT_72_MANIFEST, PARENT_72_MANIFEST_SHA256),
        (PARENT_72_RUN, PARENT_72_RUN_SHA256),
        (FROZEN, FROZEN_SHA256),
    )
    for path, digest in expected:
        actual = _sha(path)
        if actual != digest:
            raise ValueError(f"frozen source hash mismatch: {path}: {actual}")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_68_RUN.read_text(encoding="utf-8"))
    if len(frozen.get("cases") or ()) != 61 or len(parent.get("rows") or ()) != 61:
        raise ValueError("ADR-0073 requires the frozen 61-case lineage")
    return frozen, parent


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest_path = adr / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    parents = (manifest.get("lineage") or {}).get("parents") or []
    expected_parents = {
        ("ADR-0068-experiment-v1", "recall-first-union"):
            ("forked_from", PARENT_68_MANIFEST_SHA256),
        ("ADR-0072-experiment-v1", "verified-span-id-selector"):
            ("extends", PARENT_72_MANIFEST_SHA256),
    }
    actual_parents = {
        (row.get("experiment_id"), row.get("arm_id")):
            (row.get("relation"), row.get("manifest_sha256"))
        for row in parents
    }
    if actual_parents != expected_parents:
        raise ValueError("ADR-0073 parent lineage mismatch")
    arm_ids = {row.get("id") for row in
               (manifest.get("design") or {}).get("arms") or ()}
    if arm_ids != set(ARMS):
        raise ValueError("ADR-0073 arm mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
        raise ValueError("ADR-0073 performs no LLM calls")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0073 must freeze 61 questions")
    dataset = manifest.get("dataset") or {}
    if (dataset.get("sha256") != FROZEN_SHA256
            or dataset.get("parent_run_sha256") != PARENT_68_RUN_SHA256
            or dataset.get("span_contract_run_sha256") != PARENT_72_RUN_SHA256):
        raise ValueError("ADR-0073 dataset lineage mismatch")
    if require_frozen:
        design = manifest.get("design") or {}
        if not design.get("criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        run = next((row for row in manifest.get("runs") or ()
                    if row.get("id") == RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        expected_hashes = run.get("implementation_sha256") or {}
        for path in IMPLEMENTATIONS:
            relative = str(path.relative_to(ROOT))
            if expected_hashes.get(relative) != _sha(path):
                raise ValueError(f"implementation SHA is not frozen: {relative}")
    return manifest


def safe_projection(parent_row: dict) -> dict:
    """Whitelist the only parent fields that may reach the selector."""
    baseline = (parent_row.get("arms") or {}).get("baseline") or {}
    candidate = (parent_row.get("arms") or {}).get("recall-first-union") or {}
    value = {
        "number": parent_row.get("number"),
        "case_id": parent_row.get("case_id"),
        "suite": parent_row.get("suite"),
        "question": parent_row.get("question"),
        "terms": list((parent_row.get("input_state") or {}).get("terms") or ()),
        "baseline_core": deepcopy(baseline.get("selected") or []),
        "incumbent": deepcopy(candidate.get("selected") or []),
        "evidence_pool": deepcopy(candidate.get("internal_pool") or []),
        "cap": CAP,
        "pool_cap": POOL_CAP,
    }
    if _contains_banned_key(value):
        raise AssertionError("gold field crossed the product projection boundary")
    return value


def _contains_banned_key(value: object) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & _BANNED_PRODUCT_KEYS) or any(
            _contains_banned_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_banned_key(item) for item in value)
    return False


def _restore(index, values: list[dict], terms: tuple[str, ...], *,
             origin: str) -> list[termexplore.TermBranch]:
    out: list[termexplore.TermBranch] = []
    seen: set[tuple[str, object]] = set()
    for value in values:
        doc_id = str(value.get("doc_id") or "")
        node = value.get("node")
        branch = legal_coordinates.article_branch(
            index, doc_id, node, terms,
            origin=str(value.get("origin") or origin),
            reason=str(value.get("path") or ""))
        if branch is None:
            raise ValueError(f"cannot restore parent coordinate: {doc_id}:{node}")
        view = index.docs.get(doc_id)
        canonical = (doc_id, legal_coordinates.article_root(view, node)) \
            if view is not None and node in view.by_id else (doc_id, node)
        if branch.coordinate != canonical:
            raise ValueError(
                f"parent coordinate rebound forbidden: {doc_id}:{node} "
                f"-> {branch.doc_id}:{branch.node}")
        branch = replace(
            branch,
            mandatory=bool(value.get("mandatory", branch.mandatory)),
            mandatory_reason=str(value.get("mandatory_reason")
                                 or branch.mandatory_reason),
            source_doc_id=str(value.get("source_doc_id")
                              or branch.source_doc_id),
            source_node=(value.get("source_node")
                         if value.get("source_node") is not None
                         else branch.source_node),
        )
        if branch.coordinate not in seen:
            seen.add(branch.coordinate)
            out.append(branch)
    return out


def _selected(rows: list[termexplore.TermBranch]) -> list[dict]:
    return [{
        "rank": rank,
        "doc_id": row.doc_id,
        "node": row.node,
        "doc": row.doc,
        "path": row.path,
        "origin": row.origin,
        "mandatory": bool(row.mandatory),
        "mandatory_reason": row.mandatory_reason,
    } for rank, row in enumerate(rows, 1)]


def _pool(rows: list[termexplore.TermBranch]) -> list[dict]:
    return [{
        "rank": rank,
        "doc_id": row.doc_id,
        "node": row.node,
        "doc": row.doc,
        "path": row.path,
        "origin": row.origin,
        "mandatory": bool(row.mandatory),
    } for rank, row in enumerate(rows, 1)]


def _grade(case: dict, selected: list[dict], pool: list[dict]) \
        -> tuple[list[dict], bool | None, bool | None]:
    selected_ranks = {
        (str(row["doc_id"]), row["node"]): row["rank"] for row in selected}
    pool_ranks = {
        (str(row["doc_id"]), row["node"]): row["rank"] for row in pool}
    results = []
    for item in case.get("expected_articles") or ():
        scorable = (item.get("corpus_status") == "present"
                    and item.get("node") is not None)
        key = (str(item.get("doc_id") or ""), item.get("node"))
        rank = selected_ranks.get(key) if scorable else None
        pool_rank = pool_ranks.get(key) if scorable else None
        results.append({
            **item,
            "scorable": scorable,
            "hit": rank is not None if scorable else None,
            "rank": rank,
            "internal_pool_hit": pool_rank is not None if scorable else None,
            "internal_pool_rank": pool_rank,
        })
    scored = [item for item in results if item["scorable"]]
    if not scored:
        return results, None, None
    return (results, all(item["hit"] for item in scored),
            all(item["internal_pool_hit"] for item in scored))


def _baseline_arm(case: dict, parent_arm: dict) -> dict:
    selected = deepcopy(parent_arm.get("selected") or [])
    pool = deepcopy(parent_arm.get("internal_pool") or [])
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    stored = [(row.get("doc_id"), row.get("node"), row.get("hit"),
               row.get("internal_pool_hit"))
              for row in parent_arm.get("gold_results") or ()
              if row.get("scorable")]
    actual = [(row.get("doc_id"), row.get("node"), row.get("hit"),
               row.get("internal_pool_hit"))
              for row in gold if row.get("scorable")]
    if stored != actual:
        raise ValueError(f"{case['id']}: ADR-0068 grading replay mismatch")
    return {
        "arm": "baseline",
        "source": "ADR-0068/run-001/recall-first-union exact replay",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": {
            "strategy": "ADR-0068 exact artifact replay",
            "parent_state_sha256": _json_sha(parent_arm),
        },
        "llm_calls": [],
        "provider_usage": _zero_usage(),
        "incremental_provider_usage": _zero_usage(),
        "wall_ms": 0.0,
        "runtime_error": "",
    }


def _select_arm(index, projection: dict, *, allow_exchange: bool) -> dict:
    terms = tuple(str(value) for value in projection.get("terms") or ())
    incumbent = _restore(
        index, projection["incumbent"], terms, origin="ADR-0068-selected")
    pool_rows = _restore(
        index, projection["evidence_pool"], terms, origin="ADR-0068-pool")
    core = _restore(
        index, projection["baseline_core"], terms, origin="ADR-0068-baseline-core")
    started = time.perf_counter()
    runtime_error = ""
    try:
        selected_rows, meta = proof_basis_exchange.run(
            index, projection["question"], incumbent, pool_rows, core,
            cap=CAP, allow_exchange=allow_exchange)
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        selected_rows = incumbent
        meta = {
            "enabled": True,
            "ran": True,
            "status": "error",
            "reason": "runtime_error",
            "runtime_error": runtime_error,
            "registry_errors": [runtime_error],
            "canonical_source_witnesses_valid": False,
            "componentwise_non_decreasing": False,
            "unique_witness_losses": [],
            "promoted": [],
            "evicted": [],
            "gold_fields_received": False,
            "llm_calls": 0,
        }
    wall_ms = (time.perf_counter() - started) * 1000
    canonical_pool, pool_errors = proof_basis_exchange.canonicalize(index, pool_rows)
    if pool_errors:
        meta.setdefault("registry_errors", []).extend(pool_errors)
    return {
        "selected_rows": selected_rows,
        "pool_rows": canonical_pool,
        "meta": meta,
        "wall_ms": round(wall_ms, 3),
        "runtime_error": runtime_error,
    }


def _grade_selection(case: dict, arm_id: str, raw: dict) -> dict:
    selected = _selected(raw["selected_rows"])
    pool = _pool(raw["pool_rows"])
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    return {
        "arm": arm_id,
        "source": "ADR-0068 frozen pool / ADR-0073 deterministic replay",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": raw["meta"],
        "llm_calls": [],
        "provider_usage": _zero_usage(),
        "incremental_provider_usage": _zero_usage(),
        "wall_ms": raw["wall_ms"],
        "runtime_error": raw["runtime_error"],
    }


def _paired(left: dict, right: dict) -> dict:
    selected = []
    pool = []
    for a, b in zip(left["gold_results"], right["gold_results"]):
        if not a["scorable"]:
            status = pool_status = "unscorable"
        else:
            status = ("both" if a["hit"] and b["hit"] else
                      "candidate_only" if b["hit"] else
                      "baseline_only" if a["hit"] else "neither")
            pool_status = (
                "both" if a["internal_pool_hit"] and b["internal_pool_hit"] else
                "candidate_only" if b["internal_pool_hit"] else
                "baseline_only" if a["internal_pool_hit"] else "neither")
        identity = {
            "doc_id": a.get("doc_id"), "node": a.get("node"),
            "law": a.get("law"), "article": a.get("article"),
        }
        selected.append({**identity, "status": status})
        pool.append({**identity, "status": pool_status})
    case_status = (
        "unscorable" if left["case_all_gold_hit"] is None else
        "both" if left["case_all_gold_hit"] and right["case_all_gold_hit"] else
        "candidate_only" if right["case_all_gold_hit"] else
        "baseline_only" if left["case_all_gold_hit"] else "neither")
    return {
        "selected_articles": selected,
        "internal_pool_articles": pool,
        "case_all_gold": case_status,
    }


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    values = [row["arms"][arm] for row in rows]
    scored = [gold for value in values for gold in value["gold_results"]
              if gold["scorable"]]
    cases = [value for value in values if value["case_all_gold_hit"] is not None]
    pool_cases = [value for value in values
                  if value["case_all_gold_internal_pool_hit"] is not None]
    selected_counts = [value["selected_count"] for value in values]
    pool_counts = [value["internal_pool_count"] for value in values]
    walls = [float(value.get("wall_ms") or 0) for value in values]
    hits = sum(bool(gold["hit"]) for gold in scored)
    pool_hits = sum(bool(gold["internal_pool_hit"]) for gold in scored)
    return {
        "scorable_cases": len(cases),
        "case_all_gold_hits": sum(bool(value["case_all_gold_hit"])
                                  for value in cases),
        "case_all_gold_internal_pool_hits": sum(
            bool(value["case_all_gold_internal_pool_hit"])
            for value in pool_cases),
        "gold_article_instances": len(scored),
        "gold_article_hits": hits,
        "article_instance_recall_at_20": round(hits / len(scored), 6)
        if scored else 0,
        "internal_pool_gold_hits": pool_hits,
        "internal_pool_recall": round(pool_hits / len(scored), 6)
        if scored else 0,
        "selected_mean": round(statistics.mean(selected_counts), 3),
        "selected_p50": statistics.median(selected_counts),
        "selected_p95": _percentile(selected_counts, .95),
        "internal_pool_mean": round(statistics.mean(pool_counts), 3),
        "internal_pool_p50": statistics.median(pool_counts),
        "internal_pool_p95": _percentile(pool_counts, .95),
        "mean_selectivity": round(statistics.mean(selected_counts) / corpus, 8),
        "internal_pool_selectivity": round(
            statistics.mean(pool_counts) / corpus, 8),
        "wall_ms_p50": round(statistics.median(walls), 3),
        "wall_ms_p95": round(_percentile(walls, .95), 3),
        "provider_usage": _zero_usage(),
    }


def _comparison(rows: list[dict], left: str, right: str) -> dict:
    article_status = [item["status"] for row in rows
                      for item in row["paired"][f"{left}__{right}"][
                          "selected_articles"]]
    case_status = [row["paired"][f"{left}__{right}"]["case_all_gold"]
                   for row in rows]
    return {
        "baseline_arm": left,
        "candidate_arm": right,
        "candidate_only_articles": article_status.count("candidate_only"),
        "baseline_only_articles": article_status.count("baseline_only"),
        "both_articles": article_status.count("both"),
        "neither_articles": article_status.count("neither"),
        "candidate_only_cases": case_status.count("candidate_only"),
        "baseline_only_cases": case_status.count("baseline_only"),
        "both_cases": case_status.count("both"),
        "neither_cases": case_status.count("neither"),
    }


def _summary(rows: list[dict], corpus: int) -> dict:
    arms = {arm: _arm_summary(rows, arm, corpus) for arm in ARMS}
    comparisons = [
        _comparison(rows, "baseline", "verified-add-only"),
        _comparison(rows, "baseline", "proof-basis-exchange"),
        _comparison(rows, "verified-add-only", "proof-basis-exchange"),
    ]
    primary = comparisons[1]
    candidate_meta = [row["arms"]["proof-basis-exchange"]["retrieval_meta"]
                      for row in rows]
    criteria = {
        "candidate_gold_hits_at_least_68": (
            arms["proof-basis-exchange"]["gold_article_hits"] >= 68),
        "candidate_all_gold_cases_at_least_48": (
            arms["proof-basis-exchange"]["case_all_gold_hits"] >= 48),
        "baseline_article_regression_zero": (
            primary["baseline_only_articles"] == 0),
        "baseline_case_regression_zero": primary["baseline_only_cases"] == 0,
        "canonical_pool_gold_ceiling_preserved": (
            arms["proof-basis-exchange"]["internal_pool_gold_hits"] == 68),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "selected_subset_of_pool": all(
            bool(meta.get("selected_subset_of_pool")) for meta in candidate_meta),
        "canonical_source_witnesses_valid": all(
            bool(meta.get("canonical_source_witnesses_valid"))
            for meta in candidate_meta),
        "componentwise_non_decreasing": all(
            bool(meta.get("componentwise_non_decreasing"))
            and not meta.get("unique_witness_losses")
            for meta in candidate_meta),
        "gold_boundary_clean": all(
            meta.get("gold_fields_received") is False for meta in candidate_meta),
        "runtime_and_registry_errors_zero": all(
            not row["arms"]["proof-basis-exchange"].get("runtime_error")
            and not meta.get("registry_errors")
            for row, meta in zip(rows, candidate_meta)),
        "llm_calls_zero": all(meta.get("llm_calls") == 0
                              for meta in candidate_meta),
        "incremental_latency_p95_at_most_1000ms": (
            arms["proof-basis-exchange"]["wall_ms_p95"] <= 1000),
    }
    actions = [action for meta in candidate_meta
               for action in meta.get("actions") or ()]
    return {
        "cases": len(rows),
        "corpus_article_roots": corpus,
        "arms": arms,
        "comparisons": comparisons,
        "proof_accounting": {
            "actions": len(actions),
            "exchanges": sum(bool(action.get("evicted")) for action in actions),
            "vacancy_additions": sum(not action.get("evicted")
                                     for action in actions),
            "canonical_source_receipts": sum(
                len(meta.get("selected_receipts") or ()) for meta in candidate_meta),
            "lost_cells": sum(len(action.get("lost_cells") or ())
                              for action in actions),
            "llm_calls": 0,
        },
        "criteria": criteria,
        "target_pass": all(criteria.values()),
    }


def _question_markdown(case: dict, row: dict, projection: dict) -> str:
    baseline = row["arms"]["baseline"]
    control = row["arms"]["verified-add-only"]
    candidate = row["arms"]["proof-basis-exchange"]
    return f"""# ADR-0073 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `run-001`
- arms: `baseline`, `verified-add-only`, `proof-basis-exchange`
- phase: `probe/in_sample`
- LLM 호출: 없음
- parent: `ADR-0068-experiment-v1/recall-first-union`
- span authority contract: `ADR-0072-experiment-v1/verified-span-id-selector`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, selector 입력 비공개

{case.get('reference_answer') or '(기준답변 없음)'}

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력 원값 — whitelist projection

`gold_results`, `paired`, `expected_articles`, `reference_answer`는 아래 입력에 없다.

```json
{json.dumps(projection, ensure_ascii=False, indent=2)}
```

## 5. LLM·provider 호출

없음. canonical span/hash, typed edge menu, lattice dominance와 eviction은 서버가 결정론적으로 계산했다.

## 6. Baseline exact replay

```json
{json.dumps({'selected': baseline['selected'], 'gold_results': baseline['gold_results']}, ensure_ascii=False, indent=2)}
```

## 7. Verified add-only 출력

```json
{json.dumps({'selected': control['selected'], 'retrieval_meta': control['retrieval_meta'], 'gold_results': control['gold_results']}, ensure_ascii=False, indent=2)}
```

## 8. Proof basis exchange 출력

```json
{json.dumps({'selected': candidate['selected'], 'retrieval_meta': candidate['retrieval_meta'], 'gold_results': candidate['gold_results']}, ensure_ascii=False, indent=2)}
```

## 9. Paired 판정

```json
{json.dumps(row['paired'], ensure_ascii=False, indent=2)}
```

## 10. 사례 판정

- baseline all-gold: `{baseline['case_all_gold_hit']}`
- verified-add-only all-gold: `{control['case_all_gold_hit']}`
- proof-basis-exchange all-gold: `{candidate['case_all_gold_hit']}`
- runtime error: `{candidate.get('runtime_error') or '없음'}`
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
        "schema_version": "proof-basis-exchange-golden-61-run-v1",
        "adr_id": ADR_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(FROZEN.relative_to(ROOT)),
            "frozen_sha256": FROZEN_SHA256,
            "parent_68_manifest_sha256": PARENT_68_MANIFEST_SHA256,
            "parent_68_run_path": str(PARENT_68_RUN.relative_to(ROOT)),
            "parent_68_run_sha256": PARENT_68_RUN_SHA256,
            "parent_72_manifest_sha256": PARENT_72_MANIFEST_SHA256,
            "parent_72_run_path": str(PARENT_72_RUN.relative_to(ROOT)),
            "parent_72_run_sha256": PARENT_72_RUN_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": {
            str(path.relative_to(ROOT)): _sha(path) for path in IMPLEMENTATIONS},
        "model_policy": {
            "llm_calls": [],
            "judge": None,
            "deterministic_grader": "exact canonical article coordinate",
        },
        "contract": {
            "selected_cap": CAP,
            "parent_pool_cap": POOL_CAP,
            "article_root_normalization": True,
            "server_owned_span_ids": True,
            "typed_edge_ids": True,
            "free_form_quotes": False,
            "llm_eviction_authority": False,
            "gold_hidden_from_selector": True,
            "max_admissions": proof_basis_exchange.ADMISSION_MAX,
            "max_exchanges": proof_basis_exchange.EXCHANGE_MAX,
        },
        "summary": _summary(rows, corpus),
        "rows": rows,
    }


def _validate_resume(blob: dict, projections: list[dict]) -> list[dict]:
    if blob.get("schema_version") != "proof-basis-exchange-golden-61-run-v1":
        raise ValueError("resume artifact schema mismatch")
    if blob.get("adr_id") != ADR_ID or blob.get("run_id") != RUN_ID:
        raise ValueError("resume ADR/run mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume runner SHA mismatch")
    expected_impl = {str(path.relative_to(ROOT)): _sha(path)
                     for path in IMPLEMENTATIONS}
    if blob.get("implementation_sha256") != expected_impl:
        raise ValueError("resume implementation SHA mismatch")
    lineage = blob.get("source_lineage") or {}
    if (lineage.get("frozen_sha256") != FROZEN_SHA256
            or lineage.get("parent_68_run_sha256") != PARENT_68_RUN_SHA256
            or lineage.get("parent_72_run_sha256") != PARENT_72_RUN_SHA256):
        raise ValueError("resume source lineage mismatch")
    rows = list(blob.get("rows") or ())
    ids = [row.get("case_id") for row in rows]
    expected_ids = [row["case_id"] for row in projections[:len(rows)]]
    if ids != expected_ids or len(ids) != len(set(ids)):
        raise ValueError("resume rows are not an exact frozen prefix")
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
    frozen, parent = _load_sources()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod
    index = index_mod.current().scoped(None)
    corpus = _article_roots(index)
    parent_by_case = {row["case_id"]: row for row in parent["rows"]}
    projections = []
    for case in frozen["cases"]:
        parent_row = parent_by_case.get(case["id"])
        if parent_row is None or parent_row.get("question") != case["question"]:
            raise ValueError(f"parent case mismatch: {case['id']}")
        projections.append(safe_projection(parent_row))

    if args.validate_only:
        canonical_pool_total = 0
        raw_pool_total = 0
        for projection in projections:
            terms = tuple(projection["terms"])
            raw_pool_total += len(projection["evidence_pool"])
            pool_rows = _restore(
                index, projection["evidence_pool"], terms, origin="validate-pool")
            canonical_pool_total += len(pool_rows)
        print(json.dumps({
            "valid": True,
            "cases": len(projections),
            "gold_total": 85,
            "gold_scorable": 83,
            "corpus_article_roots": corpus,
            "raw_parent_pool_coordinates": raw_pool_total,
            "canonical_parent_pool_coordinates": canonical_pool_total,
            "llm_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 0

    if out.exists() and not args.resume:
        raise FileExistsError(
            f"refusing to overwrite completed/partial artifact without --resume: {out}")
    rows: list[dict] = []
    if args.resume and out.exists():
        rows = _validate_resume(
            json.loads(out.read_text(encoding="utf-8")), projections)
    completed = {row["case_id"] for row in rows}
    for case, projection in zip(frozen["cases"], projections):
        if case["id"] in completed:
            continue
        parent_row = parent_by_case[case["id"]]
        baseline = _baseline_arm(
            case, parent_row["arms"]["recall-first-union"])
        control_raw = _select_arm(index, projection, allow_exchange=False)
        candidate_raw = _select_arm(index, projection, allow_exchange=True)
        control = _grade_selection(
            case, "verified-add-only", control_raw)
        candidate = _grade_selection(
            case, "proof-basis-exchange", candidate_raw)
        arms = {
            "baseline": baseline,
            "verified-add-only": control,
            "proof-basis-exchange": candidate,
        }
        paired = {
            "baseline__verified-add-only": _paired(baseline, control),
            "baseline__proof-basis-exchange": _paired(baseline, candidate),
            "verified-add-only__proof-basis-exchange": _paired(control, candidate),
        }
        row = {
            "number": case["number"],
            "case_id": case["id"],
            "suite": case["suite"],
            "question": case["question"],
            "input_state_sha256": _json_sha(projection),
            "product_input_keys": sorted(projection),
            "arms": arms,
            "paired": paired,
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, projection), encoding="utf-8")
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _atomic_save(out, _artifact(rows, corpus))
        hits = {
            arm: sum(bool(gold["hit"]) for gold in arms[arm]["gold_results"]
                     if gold["scorable"])
            for arm in ARMS
        }
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"baseline={hits['baseline']} add={hits['verified-add-only']} "
            f"exchange={hits['proof-basis-exchange']} "
            f"selected={candidate['selected_count']} "
            f"actions={len(candidate['retrieval_meta'].get('actions') or ())} "
            f"status={candidate['retrieval_meta'].get('status')}",
            flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
