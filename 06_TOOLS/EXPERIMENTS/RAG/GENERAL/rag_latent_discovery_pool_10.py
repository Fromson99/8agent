#!/usr/bin/env python3
"""Run ADR-0087 latent discovery-pool recall with an exact v4 stage ledger."""

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
from typing import Any, Mapping, Sequence


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

from lawrag.core import llm as llm_mod  # noqa: E402
from lawrag.core.rag import conceptfirst, index as index_mod  # noqa: E402
from lawrag.core.rag import latent_discovery_pool as discovery  # noqa: E402
from lawrag.runtime import retrieval_stage_ledger as stage_ledger  # noqa: E402


ADR_ID = "ADR-0087"
EXPERIMENT_ID = "ADR-0087-experiment-v1"
RUN_ID = "run-001"
MODEL = "claude-haiku-4-5-20251001"
ARMS = ("baseline", "semantic-seed-lattice", "seed-residual-discovery")
DATASET = ROOT / "01_DATA/review/semantic_operation_seed_v2.json"
DATASET_SHA256 = "1b8a91241a437dd16a9311351956f2481cb0dc3efc45399386acf93b269f01ee"
DEFAULT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0087-latent-discovery-pool-stage-ledger"
STAGE_LEDGER_NAME = "run-001-stage-ledger.json"
RUN_ARTIFACT_NAME = "run-001.json"
IMPLEMENTATION = Path(__import__("lawrag").__file__).resolve().parent / "core/rag/latent_discovery_pool.py"
TESTS = (
    ROOT / "05_TESTS/REGRESSION/rag/test_latent_discovery_pool.py",
    ROOT / "05_TESTS/REGRESSION/rag/test_latent_discovery_pool_runner.py",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _payload(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write(path: Path, payload: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _percentile(values: Sequence[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return float(ordered[position])


def _article_roots(index) -> int:
    return sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
        if index.in_scope(view.doc_id)
    )


def _audit_call(kind, system, user, schema, max_tokens, effort, model,
                result, exchange) -> dict[str, Any]:
    provider = exchange.dump() if exchange is not None else {}
    return {
        "kind": kind,
        "system": system,
        "user": user,
        "schema": schema,
        "max_tokens": max_tokens,
        "effort": effort,
        "requested_model": model or MODEL,
        "provider": provider,
        "structured_output": deepcopy(result),
    }


class RecordingLLM:
    def __init__(self, real):
        self.real = real
        self.model = real.model
        self.log = real.log
        self.audit: list[dict[str, Any]] = []

    def structured(self, kind, system, user, schema, max_tokens=16000,
                   effort="high", images=None, model=None):
        before = len(self.real.log)
        result = self.real.structured(
            kind,
            system,
            user,
            schema,
            max_tokens=max_tokens,
            effort=effort,
            images=images,
            model=model,
        )
        exchange = self.real.log[before] if len(self.real.log) > before else None
        self.audit.append(_audit_call(
            kind, system, user, schema, max_tokens, effort, model, result, exchange))
        return result


def _load_dataset() -> dict[str, Any]:
    if _sha(DATASET) != DATASET_SHA256:
        raise ValueError("frozen semantic-operation-seed dataset hash mismatch")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = list(dataset.get("cases") or ())
    ids = [str(case.get("id") or "") for case in cases]
    if ids != [f"seed-latent-{pos:03d}" for pos in range(1, 11)]:
        raise ValueError(f"frozen case order mismatch: {ids}")
    gold_total = sum(
        item.get("corpus_status") == "present"
        for case in cases for item in case.get("expected_articles") or ()
    )
    if gold_total != 14:
        raise ValueError(f"expected 14 corpus-present gold articles, got {gold_total}")
    return dataset


def _validate_manifest(adr: Path, expected_manifest_sha256: str, *,
                       require_hash_gate: bool) -> dict[str, Any]:
    manifest_path = adr / "실험/manifest.json"
    actual_manifest_sha = _sha(manifest_path)
    if actual_manifest_sha != expected_manifest_sha256:
        raise ValueError(
            f"manifest hash mismatch: expected={expected_manifest_sha256} "
            f"actual={actual_manifest_sha}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("ADR/experiment id mismatch")
    if manifest.get("phase") != "probe" or manifest.get("in_sample") is not True:
        raise ValueError("ADR-0087 must remain an in-sample probe")
    design = manifest.get("design") or {}
    if design.get("criteria_frozen_before_run") is not True:
        raise ValueError("criteria are not frozen")
    if (design.get("discovery_contract") or {}).get("pool_cap") != discovery.POOL_CAP:
        raise ValueError("pool cap contract mismatch")
    arm_ids = [row.get("id") for row in design.get("arms") or ()]
    if arm_ids != list(ARMS):
        raise ValueError(f"arm order mismatch: {arm_ids}")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if calls != [
        {"role":"baseline_term_plan","class":"product","model":MODEL,
         "repeats":1,"temperature":"provider_default_omitted"},
        {"role":"semantic_seed_lattice_planner","class":"product","model":MODEL,
         "repeats":1,"temperature":"provider_default_omitted"},
    ]:
        raise ValueError("LLM policy mismatch")
    dataset = manifest.get("dataset") or {}
    if dataset.get("sha256") != DATASET_SHA256 or dataset.get("corpus_present_gold_articles") != 14:
        raise ValueError("dataset lineage mismatch")
    accounting = manifest.get("retrieval_accounting") or {}
    if accounting.get("changed") is not True or (accounting.get("stage_ledger") or {}).get("mode") != "measured":
        raise ValueError("retrieval stage ledger must be measured")
    stage_plan = (design.get("retrieval_stage_plan") or {}).get("stages_by_arm") or {}
    if set(stage_plan) != set(ARMS):
        raise ValueError("stage plan arms mismatch")
    run = next((row for row in manifest.get("runs") or () if row.get("id") == RUN_ID), None)
    if not run or run.get("status") not in {"planned", "running", "complete"}:
        raise ValueError("run-001 is not executable")
    if require_hash_gate:
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner hash mismatch")
        expected_impl = (run.get("implementation_sha256") or {}).get(
            str(IMPLEMENTATION.relative_to(ROOT)))
        if expected_impl != _sha(IMPLEMENTATION):
            raise ValueError("implementation hash mismatch")
        expected_tests = run.get("test_sha256") or {}
        for path in TESTS:
            relative = str(path.relative_to(ROOT))
            if expected_tests.get(relative) != _sha(path):
                raise ValueError(f"test hash mismatch: {relative}")
    return manifest


def _gold_coordinates(case: Mapping[str, Any]) -> list[tuple[str, int]]:
    return [
        (str(item["doc_id"]), int(item["node"]))
        for item in case.get("expected_articles") or ()
        if item.get("corpus_status") == "present"
    ]


def _call_usage(calls: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out = {
        "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "duration_ms": 0, "provider_errors": 0,
    }
    for call in calls:
        provider = call.get("provider") or {}
        usage = provider.get("usage") or {}
        out["calls"] += 1
        out["input_tokens"] += int(usage.get("input_tokens") or usage.get("input") or 0)
        out["output_tokens"] += int(usage.get("output_tokens") or usage.get("output") or 0)
        out["duration_ms"] += int(provider.get("dur_ms") or 0)
        out["provider_errors"] += bool(provider.get("error"))
    return out


def _final_stage(graded: Mapping[str, Any]) -> Mapping[str, Any]:
    stages = list(graded.get("stages") or ())
    if not stages or stages[-1].get("kind") != "present":
        raise ValueError("graded ledger has no final present stage")
    return stages[-1]


def _stage_rows_for_markdown(graded: Mapping[str, Any]) -> str:
    lines = [
        "| stage | kind | candidates before→after | added/discarded | gold before→after | gold gain/loss | recall |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for stage in graded.get("stages") or ():
        recall = stage.get("golden_recall")
        lines.append(
            f"| `{stage['stage_id']}` | {stage['kind']} | "
            f"{stage['before_count']}→{stage['after_count']} | "
            f"+{stage['added_count']}/-{stage['discarded_count']} | "
            f"{stage['gold_before']}→{stage['gold_after']} | "
            f"+{stage['gold_added']}/-{stage['gold_discarded']} | "
            f"{(f'{recall:.4f}' if recall is not None else 'n/a')} |"
        )
    return "\n".join(lines)


def _question_markdown(case: Mapping[str, Any], row: Mapping[str, Any], *,
                       number: int, executed_at: str) -> str:
    parts = [
        f"# ADR-0087 질문 {number:03d}: {case['id']}",
        "",
        "## 실행 메타",
        "",
        f"- case ID: `{case['id']}`",
        f"- run: `{RUN_ID}`",
        f"- 실행 시각: `{executed_at}`",
        f"- 제품 모델: `{MODEL}`",
        "- arm 순서: `" + " → ".join(row["execution_order"]) + "`",
        "- gold 결합: 후보 snapshot 완료 뒤 offline exact grading",
        "",
        "## 사용자 질문 원문",
        "",
        str(case["question"]),
        "",
        "## 기준답변 — 채점 전용, 제품 입력 비공개",
        "",
        str(case.get("reference_answer") or ""),
        "",
        "## 기대 조문 — 채점 전용, 제품 입력 비공개",
        "",
        "```json",
        json.dumps(case.get("expected_articles") or [], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 제품 planner 호출 원문",
        "",
    ]
    for label in ("baseline", "semantic-seed-lattice"):
        parts.extend([
            f"### {label}",
            "",
            "```json",
            json.dumps(row["planner_calls"][label], ensure_ascii=False, indent=2),
            "```",
            "",
        ])
    parts.extend(["## 제품 retrieval trace", ""])
    for arm in ARMS:
        parts.extend([
            f"### {arm}", "", "```json",
            json.dumps(row["traces"][arm], ensure_ascii=False, indent=2),
            "```", "", "### 단계별 후보·gold 원장", "",
            _stage_rows_for_markdown(row["graded_ledgers"][arm]), "",
        ])
    parts.extend([
        "## 사례 판정", "",
        "```json",
        json.dumps(row["case_result"], ensure_ascii=False, indent=2),
        "```", "",
        "의미 judge와 최종답변 호출은 없다. `reference_answer`는 제품 호출에 전달되지 않았다.",
        "",
    ])
    return "\n".join(parts)


def run(adr: Path, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = _load_dataset()
    index = index_mod.current().scoped(None)
    registry = conceptfirst.load_registry(conceptfirst.registry_path())
    canonicalizer = stage_ledger.index_article_root_canonicalizer(index)
    real = llm_mod.LLM(model=MODEL)
    executed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    graded_ledgers: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    usage_total = {
        "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "duration_ms": 0, "provider_errors": 0,
    }

    for number, case in enumerate(dataset["cases"], start=1):
        started = time.perf_counter()
        question = str(case["question"])
        baseline_recorder = RecordingLLM(real)
        semantic_recorder = RecordingLLM(real)
        if number % 2:
            execution_order = ["baseline", "semantic-seed-lattice", "seed-residual-discovery(replay)"]
            baseline = discovery.baseline_plan(baseline_recorder, question)
            semantic = discovery.semantic_plan(semantic_recorder, question)
        else:
            execution_order = ["semantic-seed-lattice", "seed-residual-discovery(replay)", "baseline"]
            semantic = discovery.semantic_plan(semantic_recorder, question)
            baseline = discovery.baseline_plan(baseline_recorder, question)

        captures: dict[str, dict[str, Any]] = {}
        traces: dict[str, dict[str, Any]] = {}
        captures["baseline"], traces["baseline"] = discovery.run_simple_arm(
            index, case["id"], question, baseline, registry,
            arm_id="baseline", prefix="b")
        captures["semantic-seed-lattice"], traces["semantic-seed-lattice"] = \
            discovery.run_simple_arm(
                index, case["id"], question, semantic, registry,
                arm_id="semantic-seed-lattice", prefix="s")
        captures["seed-residual-discovery"], traces["seed-residual-discovery"] = \
            discovery.run_residual_arm(
                index, case["id"], question, semantic, registry)

        gold = _gold_coordinates(case)
        graded = {
            arm: stage_ledger.grade_capture(captures[arm], gold, canonicalizer=canonicalizer)
            for arm in ARMS
        }
        graded_ledgers.extend(graded.values())
        final = {arm: _final_stage(graded[arm]) for arm in ARMS}
        case_result = {
            arm: {
                "gold_after": final[arm]["gold_after"],
                "gold_total": final[arm]["gold_total"],
                "golden_recall": final[arm]["golden_recall"],
                "pool_count": final[arm]["after_count"],
                "all_gold": final[arm]["gold_after"] == final[arm]["gold_total"],
            }
            for arm in ARMS
        }
        calls = {
            "baseline": baseline_recorder.audit,
            "semantic-seed-lattice": semantic_recorder.audit,
        }
        case_usage = _call_usage([*baseline_recorder.audit, *semantic_recorder.audit])
        for key in usage_total:
            usage_total[key] += case_usage[key]
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        latencies.append(elapsed_ms)
        row = {
            "case_id": case["id"],
            "question": question,
            "execution_order": execution_order,
            "planner_calls": calls,
            "traces": traces,
            "graded_ledgers": graded,
            "case_result": case_result,
            "usage": case_usage,
            "latency_ms": elapsed_ms,
        }
        rows.append(row)
        question_path = adr / "실험" / f"질문-{number:03d}-{case['id']}.md"
        _write(question_path, _question_markdown(
            case, row, number=number, executed_at=executed_at).encode("utf-8"))
        print(json.dumps({
            "progress": f"{number}/10", "case_id": case["id"],
            "result": case_result, "latency_ms": elapsed_ms,
        }, ensure_ascii=False), flush=True)

    stage_plan = (manifest["design"]["retrieval_stage_plan"]["stages_by_arm"])
    declared = {
        arm: [stage["stage_id"] for stage in stage_plan[arm]]
        for arm in ARMS
    }
    run_ledger = stage_ledger.build_run_artifact(RUN_ID, graded_ledgers, declared)
    experiment_ledger = stage_ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    stage_path = adr / "artifacts" / STAGE_LEDGER_NAME
    stage_sha, stage_bytes = _write(stage_path, _payload(experiment_ledger))

    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row["case_result"][arm] for row in rows]
        gold_after = sum(row["gold_after"] for row in arm_rows)
        gold_total = sum(row["gold_total"] for row in arm_rows)
        pools = [row["pool_count"] for row in arm_rows]
        by_arm[arm] = {
            "gold_after": gold_after,
            "gold_total": gold_total,
            "golden_recall": gold_after / gold_total,
            "all_gold_cases": sum(row["all_gold"] for row in arm_rows),
            "cases": len(arm_rows),
            "presented_total": sum(pools),
            "presented_mean": statistics.mean(pools),
            "presented_p50": statistics.median(pools),
            "presented_p95": _percentile(pools, 0.95),
            "selectivity": statistics.mean(pools) / _article_roots(index),
        }
    comparisons = []
    for candidate in ARMS[1:]:
        candidate_only = baseline_only = both = neither = 0
        for row in rows:
            base = row["case_result"]["baseline"]["all_gold"]
            cand = row["case_result"][candidate]["all_gold"]
            if cand and not base:
                candidate_only += 1
            elif base and not cand:
                baseline_only += 1
            elif base and cand:
                both += 1
            else:
                neither += 1
        comparisons.append({
            "baseline": "baseline", "candidate": candidate,
            "candidate_only_all_gold_cases": candidate_only,
            "baseline_only_all_gold_cases": baseline_only,
            "both_all_gold_cases": both,
            "neither_all_gold_cases": neither,
            "article_recall_delta": (
                by_arm[candidate]["gold_after"] - by_arm["baseline"]["gold_after"]),
        })
    summary = {
        "corpus_total": _article_roots(index),
        "by_arm": by_arm,
        "comparisons": comparisons,
        "target": {
            "required_gold_after": 14,
            "observed_gold_after": by_arm["seed-residual-discovery"]["gold_after"],
            "pass": by_arm["seed-residual-discovery"]["gold_after"] == 14,
        },
        "usage": usage_total,
        "latency": {
            "case_p50_ms": statistics.median(latencies),
            "case_p95_ms": _percentile(latencies, 0.95),
            "case_max_ms": max(latencies),
        },
        "provider_runtime_errors": usage_total["provider_errors"],
    }
    report: dict[str, Any] = {
        "schema_version": "latent-discovery-pool-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "executed_at": executed_at,
        "model": MODEL,
        "dataset": {
            "path": str(DATASET.relative_to(ROOT)),
            "sha256": DATASET_SHA256,
        },
        "gold_visible_to_product": False,
        "computed_post_selection": True,
        "final_answer_calls": 0,
        "main_wiring": "unchanged",
        "stage_ledger": {
            "path": str(stage_path.relative_to(ROOT)),
            "sha256": stage_sha,
            "bytes": stage_bytes,
            "content_sha256": experiment_ledger["artifact_sha256"],
        },
        "summary": summary,
        "rows": rows,
    }
    report["artifact_content_sha256"] = _json_sha(report)
    return report, experiment_ledger


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, default=DEFAULT_ADR)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    adr = args.adr.resolve()
    manifest = _validate_manifest(
        adr, args.manifest_sha256, require_hash_gate=True)
    dataset = _load_dataset()
    if args.validate_only:
        print(json.dumps({
            "status": "valid", "cases": len(dataset["cases"]),
            "gold_articles": 14, "model": MODEL,
            "runner_sha256": _sha(Path(__file__).resolve()),
            "implementation_sha256": _sha(IMPLEMENTATION),
            "tests": {str(path.relative_to(ROOT)): _sha(path) for path in TESTS},
        }, ensure_ascii=False, sort_keys=True))
        return 0
    report, _experiment_ledger = run(adr, manifest)
    output = adr / "artifacts" / RUN_ARTIFACT_NAME
    digest, size = _write(output, _payload(report))
    print(json.dumps({
        "status": "complete", "path": str(output.relative_to(ROOT)),
        "sha256": digest, "bytes": size, "summary": report["summary"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
