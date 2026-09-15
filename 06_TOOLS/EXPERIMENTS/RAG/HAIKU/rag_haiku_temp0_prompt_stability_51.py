#!/usr/bin/env python3
"""Run ADR-0060: two Haiku prompts, temperature 0, three repeats on cm-core-51."""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from scripts import rag_open_model_ceiling_51 as parent  # noqa: E402


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0060-haiku-temp0-prompt-stability-51"
ART = ADR / "artifacts"
EXP = ADR / "실험"
PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0058-haiku-prompt-atom-ablation-51"
PARENT_ART = PARENT_ADR / "artifacts"
MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-opus-5"
ARMS = ["baseline", "minimal-core-temp0"]
PARENT_ARM = {"baseline": "baseline", "minimal-core-temp0": "minimal-core"}
REPEATS = (1, 2, 3)
LOCK = threading.Lock()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temporary.replace(path)


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))]


def exchange_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = [exchange for row in rows for exchange in row.get("provider_exchanges", [])]
    successful = [exchange for exchange in exchanges if not exchange.get("error")]
    durations = [int(exchange.get("dur_ms", 0)) for exchange in successful]
    return {
        "calls": len(exchanges),
        "successful_calls": len(successful),
        "errors": sum(bool(exchange.get("error")) for exchange in exchanges),
        "input_tokens": sum(int((exchange.get("usage") or {}).get("input_tokens", 0)) for exchange in exchanges),
        "output_tokens": sum(int((exchange.get("usage") or {}).get("output_tokens", 0)) for exchange in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def prepare() -> None:
    source_path = PARENT_ART / "frozen-cases.json"
    source = json.loads(source_path.read_text("utf-8"))
    cases = []
    prompt_rows = []
    request_hashes: dict[str, list[str]] = {arm: [] for arm in ARMS}
    for arm in ARMS:
        parent_arm = PARENT_ARM[arm]
        systems = {case["product_requests"][parent_arm]["system"] for case in source["cases"]}
        if len(systems) != 1:
            raise RuntimeError(f"parent prompt drift: {parent_arm}")
        system = systems.pop()
        prompt_rows.append({
            "arm_id": arm,
            "parent_arm": f"ADR-0058-experiment-v1/{parent_arm}",
            "system": system,
            "system_sha256": parent.text_sha(system),
            "temperature": 0,
        })
    expected_hashes = {
        "baseline": "d8cc978253ec42c800891f0cdfabae9471888b50419398129625c093e282a028",
        "minimal-core-temp0": "ef0dd294b13200eaee4190689e0e8fd957749625a950e481d3b9db63fdb89b2d",
    }
    if {row["arm_id"]: row["system_sha256"] for row in prompt_rows} != expected_hashes:
        raise RuntimeError("ADR-0058 parent prompt hash drift")

    for source_case in source["cases"]:
        requests = {}
        for arm in ARMS:
            request = dict(source_case["product_requests"][PARENT_ARM[arm]])
            request["temperature"] = 0
            requests[arm] = request
            request_hashes[arm].append(parent.text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)))
        cases.append({
            "case_id": source_case["case_id"],
            "question": source_case["question"],
            "reference_answer": source_case["reference_answer"],
            "reference_answer_visibility": "offline_evaluator_only",
            "expected_articles": source_case["expected_articles"],
            "gold_evidence": source_case["gold_evidence"],
            "product_requests": requests,
        })
    for row in prompt_rows:
        row["request_hashes_sha256"] = parent.text_sha("\n".join(request_hashes[row["arm_id"]]))

    frozen = {
        "schema_version": "haiku-temp0-prompt-stability-51-frozen-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": "ADR-0058 frozen cm-core 51건 전수; 70 expected article; 제외 없음",
        "in_sample": True,
        "decision_eligible": False,
        "parent_frozen_source": str(source_path.relative_to(ROOT)),
        "parent_frozen_sha256": parent.sha(source_path),
        "case_count": len(cases),
        "expected_article_instances": sum(len(case["gold_evidence"]) for case in cases),
        "arms": ARMS,
        "product_model": MODEL,
        "product_repeats": 3,
        "temperature": 0,
        "max_tokens": 12000,
        "effort": None,
        "judge_model": JUDGE_MODEL,
        "judge_protocol": (
            "Opus first vote for all 306 outputs; if correct or conclusion_correct differs among "
            "the six outputs in a case, add two blind votes to all six; majority is final"
        ),
        "provider_error_retry": 1,
        "cases": cases,
    }
    if len(cases) != 51 or frozen["expected_article_instances"] != 70:
        raise RuntimeError("suite size drift")
    if any("[기준답변]" in request["user"] for case in cases for request in case["product_requests"].values()):
        raise RuntimeError("reference answer leak")

    write_json(ART / "prompt-matrix.json", {
        "schema_version": "haiku-temp0-prompt-matrix-v1",
        "arms": prompt_rows,
        "repeats": list(REPEATS),
        "schedule_seed": 6001,
    })
    write_json(ART / "frozen-cases.json", frozen)
    write_json(ART / "coverage-preflight.json", {
        "cases": 51,
        "arms": 2,
        "repeats": 3,
        "planned_product_calls": 306,
        "planned_first_judge_calls": 306,
        "maximum_conditional_rejudge_calls": 612,
        "expected_article_instances": 70,
        "wiki_context_cases": 0,
        "reference_answer_leaks": 0,
        "parent_frozen_sha256": frozen["parent_frozen_sha256"],
    })
    manifest_path = EXP / "manifest.json"
    manifest = parent.read_json(manifest_path)
    manifest["dataset"]["sha256"] = parent.sha(ART / "frozen-cases.json")
    write_json(manifest_path, manifest)
    print(json.dumps({
        "frozen_cases_sha256": parent.sha(ART / "frozen-cases.json"),
        "prompt_matrix_sha256": parent.sha(ART / "prompt-matrix.json"),
        "coverage_preflight_sha256": parent.sha(ART / "coverage-preflight.json"),
        "planned_product_calls": 306,
    }, ensure_ascii=False, indent=2))


def call_temp0_with_retry(client: LLM, *, kind: str, request: dict[str, Any]) -> dict[str, Any]:
    attempts = []
    parsed = None
    error = None
    for attempt_no in (1, 2):
        started = time.perf_counter()
        first_token_ms = 0
        raw = ""
        stop = ""
        usage: dict[str, int] = {}
        attempt_error = ""
        try:
            config = {"format": {"type": "json_schema", "schema": request["schema"]}}
            with client._client.messages.stream(  # noqa: SLF001 - exact experimental payload
                model=MODEL,
                max_tokens=request["max_tokens"],
                temperature=0,
                system=request["system"],
                output_config=config,
                messages=[{"role": "user", "content": request["user"]}],
            ) as stream:
                for chunk in stream.text_stream:
                    if not raw and chunk:
                        first_token_ms = int((time.perf_counter() - started) * 1000)
                    raw += chunk
                response = stream.get_final_message()
            stop = response.stop_reason or ""
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            if stop in ("refusal", "max_tokens"):
                attempt_error = f"stop_reason={stop}"
            else:
                parsed = json.loads(raw)
        except Exception as exc:  # provider and parse failures are captured verbatim
            attempt_error = f"{type(exc).__name__}: {exc}"
        attempts.append({
            "attempt_no": attempt_no,
            "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": MODEL,
            "provider": "anthropic",
            "request_parameters": {
                "temperature": 0,
                "max_tokens": request["max_tokens"],
                "effort": request.get("effort"),
                "output_config": {"format": {"type": "json_schema", "schema": request["schema"]}},
            },
            "usage": usage,
            "stop_reason": stop,
            "dur_ms": int((time.perf_counter() - started) * 1000),
            "ttft_ms": first_token_ms,
            "system": request["system"],
            "user": request["user"],
            "raw_response": raw,
            "error": attempt_error,
        })
        if parsed is not None and not attempt_error:
            error = None
            break
        error = attempt_error
    return {"parsed": parsed, "attempts": attempts, "error": error}


def run_answers(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = parent.read_json(ART / "frozen-cases.json")
    output_path = ART / "product-results.json"
    output = parent.read_json(output_path, {
        "schema_version": "haiku-temp0-products-v1",
        "run_id": "run-001",
        "schedule_seed": 6001,
        "results": {},
    })
    jobs = [
        (case["case_id"], arm, repeat)
        for case in frozen["cases"] for arm in ARMS for repeat in REPEATS
        if f"{case['case_id']}::{arm}::r{repeat}" not in output["results"]
    ]
    random.Random(6001).shuffle(jobs)
    buckets = [jobs[index::workers] for index in range(workers)]
    cases = {case["case_id"]: case for case in frozen["cases"]}
    clients = [LLM(model=MODEL) for _ in range(workers)]
    completed = 0

    def one_bucket(bucket: list[tuple[str, str, int]], worker_no: int) -> None:
        nonlocal completed
        client = clients[worker_no]
        for case_id, arm, repeat in bucket:
            key = f"{case_id}::{arm}::r{repeat}"
            request = cases[case_id]["product_requests"][arm]
            result = call_temp0_with_retry(
                client,
                kind=f"adr0060.{case_id}.{arm}.r{repeat}",
                request=request,
            )
            row = {
                "case_id": case_id,
                "arm_id": arm,
                "repeat": repeat,
                "model": MODEL,
                "provider": "anthropic",
                "temperature": 0,
                "request": request,
                "request_sha256": parent.text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)),
                "output": result["parsed"],
                "provider_exchanges": result["attempts"],
                "error": result["error"],
            }
            with LOCK:
                output["results"][key] = row
                write_json(output_path, output)
                completed += 1
                done = completed
                total = len(jobs)
            if done % 20 == 0 or done == total:
                print(f"answers: {done}/{total} pending jobs; stored {len(output['results'])}/306", flush=True)

    if not jobs:
        print("answers: no pending jobs", flush=True)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, index) for index, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()
    print(f"answers complete: {len(output['results'])}/306", flush=True)


def judge_request(case: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": parent.JUDGE_SYSTEM,
        "user": parent.judge_user(case["question"], case["reference_answer"], product["output"]["answer"]),
        "schema": parent.JUDGE_SCHEMA,
        "max_tokens": 1800,
        "effort": "low",
    }


def _run_judge_jobs(jobs: list[tuple[str, int]], workers: int, stage: str) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = parent.read_json(ART / "frozen-cases.json")
    products = parent.read_json(ART / "product-results.json")
    cases = {case["case_id"]: case for case in frozen["cases"]}
    output_path = ART / "judged-results.json"
    output = parent.read_json(output_path, {
        "schema_version": "haiku-temp0-judges-v1",
        "run_id": "run-001",
        "judge_model": JUDGE_MODEL,
        "results": {},
        "conditional_cases": [],
    })
    random.Random(6002 if stage == "first" else 6003).shuffle(jobs)
    buckets = [jobs[index::workers] for index in range(workers)]
    clients = [LLM(model=JUDGE_MODEL) for _ in range(workers)]
    completed = 0

    def one_bucket(bucket: list[tuple[str, int]], worker_no: int) -> None:
        nonlocal completed
        client = clients[worker_no]
        for key, vote_no in bucket:
            product = products["results"][key]
            case_id = product["case_id"]
            if product.get("error") or not product.get("output"):
                vote = {"vote_no": vote_no, "request": None, "output": None, "provider_exchanges": [], "error": "product_call_failed"}
            else:
                request = judge_request(cases[case_id], product)
                result = parent.call_with_retry(
                    client,
                    kind=f"adr0060.judge.v{vote_no}.{key}",
                    system=request["system"],
                    user=request["user"],
                    schema=request["schema"],
                    max_tokens=request["max_tokens"],
                    effort=request["effort"],
                )
                vote = {
                    "vote_no": vote_no,
                    "request": request,
                    "output": result["parsed"],
                    "provider_exchanges": result["attempts"],
                    "error": result["error"],
                }
            with LOCK:
                row = output["results"].setdefault(key, {
                    "case_id": product["case_id"],
                    "arm_id": product["arm_id"],
                    "repeat": product["repeat"],
                    "product_model": MODEL,
                    "judge_model": JUDGE_MODEL,
                    "votes": [],
                })
                row["votes"].append(vote)
                row["votes"].sort(key=lambda item: item["vote_no"])
                write_json(output_path, output)
                completed += 1
                done = completed
                total = len(jobs)
            if done % 20 == 0 or done == total:
                print(f"judge {stage}: {done}/{total}", flush=True)

    if not jobs:
        print(f"judge {stage}: no pending jobs", flush=True)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, index) for index, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()


def run_judge_first(workers: int) -> None:
    products = parent.read_json(ART / "product-results.json")
    if len(products.get("results", {})) != 306:
        raise RuntimeError("first judge requires 306 product rows")
    judged = parent.read_json(ART / "judged-results.json", {"results": {}})
    jobs = []
    for key in sorted(products["results"]):
        votes = judged.get("results", {}).get(key, {}).get("votes", [])
        if not any(vote.get("vote_no") == 1 for vote in votes):
            jobs.append((key, 1))
    _run_judge_jobs(jobs, workers, "first")


def first_vote(row: dict[str, Any]) -> dict[str, Any] | None:
    vote = next((item for item in row.get("votes", []) if item.get("vote_no") == 1), None)
    return vote.get("output") if vote else None


def run_judge_conditional(workers: int) -> None:
    output_path = ART / "judged-results.json"
    judged = parent.read_json(output_path)
    if len(judged.get("results", {})) != 306:
        raise RuntimeError("conditional judge requires 306 first-vote rows")
    conditional_cases = []
    for number in range(1, 52):
        case_id = f"cm-{number:03d}"
        outputs = [
            first_vote(judged["results"][f"{case_id}::{arm}::r{repeat}"])
            for arm in ARMS for repeat in REPEATS
        ]
        if any(item is None for item in outputs):
            conditional_cases.append(case_id)
            continue
        correct = {bool(item.get("correct")) for item in outputs}
        conclusions = {bool(item.get("conclusion_correct")) for item in outputs}
        if len(correct) > 1 or len(conclusions) > 1:
            conditional_cases.append(case_id)
    judged["conditional_cases"] = conditional_cases
    write_json(output_path, judged)
    jobs = []
    for case_id in conditional_cases:
        for arm in ARMS:
            for repeat in REPEATS:
                key = f"{case_id}::{arm}::r{repeat}"
                existing = judged["results"][key]["votes"]
                for vote_no in (2, 3):
                    if not any(vote.get("vote_no") == vote_no for vote in existing):
                        jobs.append((key, vote_no))
    print(f"conditional cases: {len(conditional_cases)}/51; pending votes: {len(jobs)}", flush=True)
    _run_judge_jobs(jobs, workers, "conditional")


def majority(values: list[bool]) -> bool:
    return sum(values) >= (len(values) // 2 + 1)


def final_judgment(row: dict[str, Any], needs_three: bool) -> dict[str, Any]:
    votes = [vote for vote in row.get("votes", []) if vote.get("output") is not None]
    expected = 3 if needs_three else 1
    if len(votes) != expected:
        raise RuntimeError(f"invalid vote count: {row['case_id']} {row['arm_id']} r{row['repeat']} {len(votes)}/{expected}")
    correct_values = [bool(vote["output"].get("correct")) for vote in votes]
    conclusion_values = [bool(vote["output"].get("conclusion_correct")) for vote in votes]
    correct = majority(correct_values)
    conclusion_correct = majority(conclusion_values)
    matching = [vote["output"] for vote in votes if bool(vote["output"].get("correct")) == correct]
    representative = matching[-1]
    failure_type = Counter(output.get("failure_type", "other") for output in matching).most_common(1)[0][0]
    return {
        "correct": correct,
        "conclusion_correct": conclusion_correct,
        "materially_complete": representative.get("materially_complete"),
        "no_material_error": representative.get("no_material_error"),
        "failure_type": failure_type,
        "reason": representative.get("reason"),
        "missing_points": representative.get("missing_points", []),
        "vote_count": expected,
        "correct_votes": sum(correct_values),
        "conclusion_correct_votes": sum(conclusion_values),
        "correct_disagreement": len(set(correct_values)) > 1,
        "conclusion_disagreement": len(set(conclusion_values)) > 1,
    }


def paired_counts(case_stability: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    counts = {"candidate_only": 0, "baseline_only_regression": 0, "both_correct": 0, "both_wrong": 0}
    for values in case_stability.values():
        baseline = values["baseline"]["all_three_correct"]
        candidate = values["minimal-core-temp0"]["all_three_correct"]
        key = "both_correct" if baseline and candidate else "baseline_only_regression" if baseline else "candidate_only" if candidate else "both_wrong"
        counts[key] += 1
    counts["delta"] = counts["candidate_only"] - counts["baseline_only_regression"]
    return counts


def render_questions(
    frozen: dict[str, Any],
    products: dict[str, Any],
    judged: dict[str, Any],
    finals: dict[str, dict[str, Any]],
    case_stability: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    questions = []
    conditional = set(judged.get("conditional_cases", []))
    for number, case in enumerate(frozen["cases"], 1):
        case_id = case["case_id"]
        lines = [
            f"# ADR-0060 질문 {number:03d}: {case_id}", "",
            "## 1. 실행 메타", "", "- run: `run-001`", "- phase: `probe/in_sample`",
            f"- conditional 3-vote: `{case_id in conditional}`", "- product: `claude-haiku-4-5-20251001`",
            "- product temperature: `0`", "- product repeats: `3`", "- judge: `claude-opus-5`", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", case["reference_answer"], "",
            "## 4. 제품 입력을 구성한 원값", "",
        ]
        for arm in ARMS:
            lines.extend([f"### arm `{arm}`", "", "```json", json.dumps(case["product_requests"][arm], ensure_ascii=False, indent=2), "```", ""])
        lines.extend(["## 5. 제품 모델 호출 — run·arm별 실제 원문", ""])
        for arm in ARMS:
            for repeat in REPEATS:
                key = f"{case_id}::{arm}::r{repeat}"
                lines.extend([f"### `{arm}` repeat {repeat}", "", "```json", json.dumps(products["results"][key], ensure_ascii=False, indent=2), "```", ""])
        lines.extend(["## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "", "없음. frozen gold article 전문을 두 prompt의 Haiku에 직접 제공했다.", "", "## 7. 채점 호출과 반복 판정", ""])
        for arm in ARMS:
            for repeat in REPEATS:
                key = f"{case_id}::{arm}::r{repeat}"
                lines.extend([f"### `{arm}` repeat {repeat}", "", "```json", json.dumps({"votes": judged["results"][key]["votes"], "final": finals[key]}, ensure_ascii=False, indent=2), "```", ""])
        lines.extend(["## 8. 사례 최종 판정", "", "| arm | repeat correct | all 3 correct | correctness stable | conclusion stable | answerable stable | exact output |", "|---|---|---:|---:|---:|---:|---:|"])
        for arm in ARMS:
            row = case_stability[case_id][arm]
            lines.append(f"| `{arm}` | `{row['repeat_correct']}` | `{row['all_three_correct']}` | `{row['correctness_stable']}` | `{row['conclusion_stable']}` | `{row['answerable_stable']}` | `{row['exact_output_stable']}` |")
        lines.append("")
        path = EXP / f"질문-{number:03d}-{case_id}.md"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        questions.append({"number": number, "case_id": case_id, "file": path.name, "sha256": parent.sha(path)})
    return questions


def finalize() -> None:
    frozen = parent.read_json(ART / "frozen-cases.json")
    products = parent.read_json(ART / "product-results.json")
    judged = parent.read_json(ART / "judged-results.json")
    if len(products.get("results", {})) != 306 or len(judged.get("results", {})) != 306:
        raise RuntimeError("finalize requires 306 product and judge rows")
    conditional = set(judged.get("conditional_cases", []))
    finals = {key: final_judgment(row, row["case_id"] in conditional) for key, row in judged["results"].items()}

    case_stability: dict[str, dict[str, dict[str, Any]]] = {}
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_products = [row for row in products["results"].values() if row["arm_id"] == arm]
        arm_judged = [row for row in judged["results"].values() if row["arm_id"] == arm]
        repeat_scores = {}
        for repeat in REPEATS:
            repeat_scores[f"r{repeat}"] = sum(finals[f"cm-{number:03d}::{arm}::r{repeat}"]["correct"] for number in range(1, 52))
        pooled = []
        stable_correct_cases = []
        stable_wrong_cases = []
        correctness_flip_cases = []
        conclusion_flip_cases = []
        answerable_flip_cases = []
        exact_output_stable_cases = []
        for number in range(1, 52):
            case_id = f"cm-{number:03d}"
            keys = [f"{case_id}::{arm}::r{repeat}" for repeat in REPEATS]
            case_finals = [finals[key] for key in keys]
            case_products = [products["results"][key] for key in keys]
            correct_values = [row["correct"] for row in case_finals]
            conclusion_values = [row["conclusion_correct"] for row in case_finals]
            answerable_values = [(row.get("output") or {}).get("answerable") for row in case_products]
            canonical_outputs = [json.dumps(row.get("output"), ensure_ascii=False, sort_keys=True) for row in case_products]
            stability = {
                "repeat_correct": correct_values,
                "all_three_correct": all(correct_values),
                "all_three_wrong": not any(correct_values),
                "correctness_stable": len(set(correct_values)) == 1,
                "conclusion_stable": len(set(conclusion_values)) == 1,
                "answerable_stable": len(set(answerable_values)) == 1,
                "exact_output_stable": len(set(canonical_outputs)) == 1,
            }
            case_stability.setdefault(case_id, {})[arm] = stability
            pooled.extend(correct_values)
            if stability["all_three_correct"]:
                stable_correct_cases.append(case_id)
            if stability["all_three_wrong"]:
                stable_wrong_cases.append(case_id)
            if not stability["correctness_stable"]:
                correctness_flip_cases.append(case_id)
            if not stability["conclusion_stable"]:
                conclusion_flip_cases.append(case_id)
            if not stability["answerable_stable"]:
                answerable_flip_cases.append(case_id)
            if stability["exact_output_stable"]:
                exact_output_stable_cases.append(case_id)
        votes = [vote for row in arm_judged for vote in row["votes"]]
        failure_types = Counter(finals[key]["failure_type"] for key in finals if f"::{arm}::" in key)
        by_arm[arm] = {
            "repeat_correct": repeat_scores,
            "pooled_correct": sum(pooled),
            "pooled_total": 153,
            "pooled_accuracy": round(sum(pooled) / 153, 4),
            "stable_correct": len(stable_correct_cases),
            "stable_correct_cases": stable_correct_cases,
            "stable_wrong": len(stable_wrong_cases),
            "stable_wrong_cases": stable_wrong_cases,
            "correctness_flip_count": len(correctness_flip_cases),
            "correctness_flip_cases": correctness_flip_cases,
            "conclusion_flip_count": len(conclusion_flip_cases),
            "conclusion_flip_cases": conclusion_flip_cases,
            "answerable_flip_count": len(answerable_flip_cases),
            "answerable_flip_cases": answerable_flip_cases,
            "exact_output_stable_count": len(exact_output_stable_cases),
            "exact_output_stable_cases": exact_output_stable_cases,
            "product_errors": sum(bool(row.get("error")) for row in arm_products),
            "judge_vote_errors": sum(bool(vote.get("error")) for vote in votes),
            "judge_correct_disagreements": sum(finals[key]["correct_disagreement"] for key in finals if f"::{arm}::" in key),
            "judge_conclusion_disagreements": sum(finals[key]["conclusion_disagreement"] for key in finals if f"::{arm}::" in key),
            "failure_types": dict(sorted(failure_types.items())),
            "product_usage": exchange_usage(arm_products),
            "judge_usage": exchange_usage(votes),
        }

    comparison = paired_counts(case_stability)
    baseline_p95 = by_arm["baseline"]["product_usage"]["p95_ms"] or 0
    candidate_p95 = by_arm["minimal-core-temp0"]["product_usage"]["p95_ms"] or 0
    semantic_determinism = all(by_arm[arm]["conclusion_flip_count"] == 0 for arm in ARMS)
    candidate_promising = (
        comparison["delta"] >= 3
        and comparison["baseline_only_regression"] <= 2
        and by_arm["minimal-core-temp0"]["conclusion_flip_count"] <= by_arm["baseline"]["conclusion_flip_count"]
        and (baseline_p95 == 0 or candidate_p95 <= baseline_p95 * 1.5)
    )
    summary = {
        "schema_version": "haiku-temp0-prompt-stability-summary-v1",
        "run_id": "run-001",
        "primary_metric": "three-of-three stable-correct / 51",
        "cases": 51,
        "arms": 2,
        "product_repeats": 3,
        "temperature": 0,
        "product_rows": 306,
        "conditional_cases": sorted(conditional),
        "conditional_case_count": len(conditional),
        "judge_vote_rows": sum(len(row["votes"]) for row in judged["results"].values()),
        "by_arm": by_arm,
        "stable_correct_comparison": comparison,
        "hypotheses": {
            "semantic_determinism_zero_conclusion_flips": semantic_determinism,
            "minimal_core_stable_correct_delta_at_least_3": comparison["delta"] >= 3,
            "minimal_core_stable_regressions_at_most_2": comparison["baseline_only_regression"] <= 2,
            "minimal_core_promising": candidate_promising,
        },
        "limitations": [
            "반복 사용된 in-sample cm-core-51 gold-only 집합이며 운영 채택 근거가 아니다.",
            "모든 사례가 answerable이므로 불완전 근거와 unanswerable 안전성을 평가하지 못한다.",
            "conclusion_correct 안정성은 Opus 의미 판정에 의존하며 독립 인간 판정이 아니다.",
            "temperature 0의 효과 자체는 provider-default 동시 대조군 없이 잔여 변동만 측정한다.",
        ],
    }
    write_json(ART / "summary.json", summary)
    questions = render_questions(frozen, products, judged, finals, case_stability)

    manifest_path = EXP / "manifest.json"
    manifest = parent.read_json(manifest_path)
    manifest["runs"][0].update({
        "status": "complete",
        "artifact_path": str((ART / "summary.json").relative_to(ROOT)),
        "sha256": parent.sha(ART / "summary.json"),
    })
    manifest["results"] = {
        "status": "complete",
        "by_arm": by_arm,
        "comparisons": [{"baseline_arm": "baseline", "candidate_arm": "minimal-core-temp0", **comparison}],
        "judge_disagreements": sum(row["judge_correct_disagreements"] for row in by_arm.values()),
        "usage": {"product_rows": 306, "judge_vote_rows": summary["judge_vote_rows"]},
        "latency": {arm: row["product_usage"] for arm, row in by_arm.items()},
        "error_taxonomy": sorted({failure for row in by_arm.values() for failure in row["failure_types"]}),
        "assessments": {"semantic_determinism": semantic_determinism, "minimal_core_promising": candidate_promising},
    }
    manifest["questions"] = questions
    write_json(manifest_path, manifest)

    index = [
        "# ADR-0060 실험 질문 인덱스", "", "- run: `run-001 / complete`",
        "- product: `claude-haiku-4-5-20251001`, temperature `0`, repeat `3`",
        f"- conditional 3-vote cases: `{len(conditional)}/51`", "",
        "| arm | repeat correct | pooled | stable-correct | correctness flip | conclusion flip | exact-output stable |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        row = by_arm[arm]
        index.append(f"| `{arm}` | `{row['repeat_correct']}` | {row['pooled_correct']}/153 | {row['stable_correct']}/51 | {row['correctness_flip_count']} | {row['conclusion_flip_count']} | {row['exact_output_stable_count']}/51 |")
    index.extend(["", "## 질문", ""])
    index.extend(f"- [{row['case_id']}]({row['file']}) — `{row['sha256']}`" for row in questions)
    (EXP / "README.md").write_text("\n".join(index) + "\n", "utf-8")

    artifact_files = [
        ("coverage-preflight.json", "Frozen suite and call-count preflight", False),
        ("frozen-cases.json", "51 cases x 2 prompts with evaluator-only references", True),
        ("prompt-matrix.json", "Exact parent prompts, temperature and request lineage", True),
        ("product-results.json", "306 Haiku temperature-0 calls with raw provider exchanges", True),
        ("judged-results.json", "Opus first and conditional rejudge raw calls", True),
        ("summary.json", "Repeat accuracy, stability, paired, usage and hypothesis aggregates", False),
    ]
    write_json(ART / "manifest.json", {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0060",
        "files": [{
            "path": str((ART / name).relative_to(ROOT)),
            "sha256": parent.sha(ART / name),
            "bytes": (ART / name).stat().st_size,
            "description": description,
            "contains_raw_prompts_and_outputs": raw,
        } for name, description, raw in artifact_files],
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "answers", "judge-first", "judge-conditional", "finalize"])
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "answers":
        run_answers(args.workers)
    elif args.command == "judge-first":
        run_judge_first(args.workers)
    elif args.command == "judge-conditional":
        run_judge_conditional(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
