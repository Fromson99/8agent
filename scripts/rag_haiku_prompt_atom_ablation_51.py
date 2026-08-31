#!/usr/bin/env python3
"""Prepare, execute, judge, and finalize ADR-0058's frozen prompt matrix."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from scripts import rag_open_model_ceiling_51 as parent  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0058-haiku-prompt-atom-ablation-51"
ART = ADR / "artifacts"
PARENT_ART = ROOT / "docs/adr/ADR-0056-cm-core-51-open-model-ceiling/artifacts"
MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-opus-5"
EXP = ADR / "실험"
LOCK = threading.Lock()

ARMS = [
    "baseline",
    "neutral-context",
    "no-grounding",
    "no-conclusion-first",
    "no-completeness",
    "no-ref-hygiene",
    "no-abstention-gate",
    "minimal-core",
    "coverage-first",
    "evidence-checklist",
    "context-first-question-last",
]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(path)


def prompt_variants(current: str) -> dict[str, str]:
    lines = current.splitlines()
    if len(lines) != 7 or not lines[1].startswith("지켜야 할 규칙"):
        raise RuntimeError(f"unexpected ADR-0056 prompt shape: {len(lines)} lines")
    intro, header, grounding, conclusion, completeness, refs, abstention = lines
    variants = {
        "baseline": current,
        "neutral-context": "\n".join([
            intro.replace("이번 질문에 해당하는 정답 조문의 전문", "이번 질문과 관련하여 제공된 조문의 전문"),
            header, grounding, conclusion, completeness, refs, abstention,
        ]),
        "no-grounding": "\n".join([intro, header, conclusion, completeness, refs, abstention]),
        "no-conclusion-first": "\n".join([intro, header, grounding, completeness, refs, abstention]),
        "no-completeness": "\n".join([intro, header, grounding, conclusion, refs, abstention]),
        "no-ref-hygiene": "\n".join([intro, header, grounding, conclusion, completeness, abstention]),
        "no-abstention-gate": "\n".join([intro, header, grounding, conclusion, completeness, refs]),
        "minimal-core": (
            "너는 문서 질의응답 보조자다. 제공된 조문만 근거로 질문에 한국어로 직접 답하라.\n"
            "질문이 요구한 결론·수치·기간·요건·예외를 빠뜨리지 마라. 조문만으로 답할 수 "
            "없을 때만 answerable=false로 하라."
        ),
        # Same clauses, only priority/order changes: coverage -> grounding -> abstention -> composition -> hygiene.
        "coverage-first": "\n".join([intro, header, completeness, grounding, abstention, conclusion, refs]),
        "evidence-checklist": "\n".join([
            intro, header, grounding, conclusion, completeness, refs, abstention,
            "⑥ 답변을 작성하기 전에 질문이 요구한 결론, 수치·기간, 적용요건, 예외와 관련 각 호를 "
            "컨텍스트에서 각각 확인한다. 확인 과정은 출력하지 말고 최종 답변에 빠짐없이 반영한다.",
        ]),
        "context-first-question-last": current,
    }
    if list(variants) != ARMS:
        raise RuntimeError("arm order drift")
    if parent.text_sha(variants["baseline"]) != "d8cc978253ec42c800891f0cdfabae9471888b50419398129625c093e282a028":
        raise RuntimeError("ADR-0056 baseline prompt hash drift")
    return variants


def context_first(user: str) -> str:
    question_marker = "[질문]\n"
    context_marker = "\n\n[컨텍스트]\n"
    if not user.startswith(question_marker) or context_marker not in user:
        raise RuntimeError("unexpected parent user prompt shape")
    question, context = user[len(question_marker):].split(context_marker, 1)
    return f"[컨텍스트]\n{context}\n\n[질문]\n{question}"


def prepare() -> None:
    source = json.loads((PARENT_ART / "frozen-cases.json").read_text("utf-8"))
    current = source["cases"][0]["product_request"]["system"]
    variants = prompt_variants(current)
    cases = []
    request_hashes: dict[str, list[str]] = {arm: [] for arm in ARMS}
    for row in source["cases"]:
        if row["product_request"]["system"] != current:
            raise RuntimeError(f"parent system drift: {row['case_id']}")
        requests = {}
        for arm in ARMS:
            request = dict(row["product_request"])
            request["system"] = variants[arm]
            if arm == "context-first-question-last":
                request["user"] = context_first(request["user"])
            requests[arm] = request
            request_hashes[arm].append(parent.text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)))
        cases.append({
            "case_id": row["case_id"],
            "question": row["question"],
            "reference_answer": row["reference_answer"],
            "reference_answer_visibility": "offline_evaluator_only",
            "expected_articles": row["expected_articles"],
            "gold_evidence": row["gold_evidence"],
            "product_requests": requests,
        })

    matrix = {
        "schema_version": "haiku-prompt-atom-matrix-v1",
        "arms": [{
            "arm_id": arm,
            "system": variants[arm],
            "system_sha256": parent.text_sha(variants[arm]),
            "user_layout": "context_then_question" if arm == "context-first-question-last" else "question_then_context",
            "request_hashes_sha256": parent.text_sha("\n".join(request_hashes[arm])),
        } for arm in ARMS],
    }
    frozen = {
        "schema_version": "haiku-prompt-atom-ablation-51-frozen-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": "ADR-0056 cm-core 51건 전수; 70 expected article; 제외 없음",
        "in_sample": True,
        "decision_eligible": False,
        "parent_frozen_source": str((PARENT_ART / "frozen-cases.json").relative_to(ROOT)),
        "parent_frozen_sha256": parent.sha(PARENT_ART / "frozen-cases.json"),
        "case_count": len(cases),
        "expected_article_instances": sum(len(row["gold_evidence"]) for row in cases),
        "arms": ARMS,
        "product_model": MODEL,
        "judge_model": JUDGE_MODEL,
        "product_repeats": 1,
        "judge_protocol": (
            "Opus 5 first vote for all 561 outputs; if any arm differs from baseline on a case, "
            "two additional blind votes for all 11 outputs in that case; majority is final"
        ),
        "provider_error_retry": 1,
        "max_tokens": 12000,
        "effort": None,
        "temperature": "anthropic_provider_default",
        "cases": cases,
    }
    if len(cases) != 51 or frozen["expected_article_instances"] != 70:
        raise RuntimeError("suite size drift")
    if any("[기준답변]" in request["user"] for case in cases for request in case["product_requests"].values()):
        raise RuntimeError("reference answer leak")
    write_json(ART / "prompt-matrix.json", matrix)
    write_json(ART / "frozen-cases.json", frozen)
    write_json(ART / "coverage-preflight.json", {
        "cases": 51,
        "arms": len(ARMS),
        "planned_product_calls": 51 * len(ARMS),
        "planned_first_judge_calls": 51 * len(ARMS),
        "maximum_conditional_rejudge_calls": 51 * len(ARMS) * 2,
        "expected_article_instances": 70,
        "wiki_context_cases": 0,
        "reference_answer_leaks": 0,
        "parent_frozen_sha256": frozen["parent_frozen_sha256"],
    })
    print(json.dumps({
        "frozen_cases_sha256": parent.sha(ART / "frozen-cases.json"),
        "prompt_matrix_sha256": parent.sha(ART / "prompt-matrix.json"),
        "coverage_preflight_sha256": parent.sha(ART / "coverage-preflight.json"),
        "cases": 51,
        "arms": len(ARMS),
        "planned_product_calls": 51 * len(ARMS),
        "planned_first_judge_calls": 51 * len(ARMS),
    }, ensure_ascii=False, indent=2))


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))]


def exchange_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = [ex for row in rows for ex in row.get("provider_exchanges", [])]
    successful = [ex for ex in exchanges if not ex.get("error")]
    durations = [int(ex.get("dur_ms", 0)) for ex in successful]
    return {
        "calls": len(exchanges),
        "successful_calls": len(successful),
        "errors": sum(bool(ex.get("error")) for ex in exchanges),
        "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in exchanges),
        "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def run_answers(workers: int, lanes: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = json.loads((ART / "frozen-cases.json").read_text("utf-8"))
    out_path = ART / "product-results.json"
    out = parent.read_json(out_path, {
        "schema_version": "haiku-prompt-atom-products-v1",
        "run_id": "run-001",
        "results": {},
    })
    clients = {arm: [LLM(model=MODEL) for _ in range(lanes)] for arm in ARMS}

    def one_lane(arm: str, lane: int) -> int:
        client = clients[arm][lane]
        count = 0
        for index in range(lane, len(frozen["cases"]), lanes):
            case = frozen["cases"][index]
            key = f"{case['case_id']}::{arm}"
            with LOCK:
                if key in out["results"]:
                    continue
            request = case["product_requests"][arm]
            result = parent.call_with_retry(
                client,
                kind=f"adr0058.{case['case_id']}.{arm}",
                system=request["system"],
                user=request["user"],
                schema=request["schema"],
                max_tokens=request["max_tokens"],
                effort=request["effort"],
            )
            row = {
                "case_id": case["case_id"],
                "arm_id": arm,
                "model": MODEL,
                "provider": "anthropic",
                "request_sha256": parent.text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)),
                "output": result["parsed"],
                "provider_exchanges": result["attempts"],
                "error": result["error"],
            }
            with LOCK:
                out["results"][key] = row
                parent.write_json(out_path, out)
                size = len(out["results"])
            count += 1
            if size % 20 == 0 or size == 561:
                print(f"answers: {size}/561", flush=True)
        return count

    jobs = [(arm, lane) for arm in ARMS for lane in range(lanes)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_lane, arm, lane) for arm, lane in jobs]
        for future in as_completed(futures):
            future.result()
    print(f"answers complete: {len(out['results'])}/561", flush=True)


def judge_request(case: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    user = parent.judge_user(case["question"], case["reference_answer"], product["output"]["answer"])
    return {
        "system": parent.JUDGE_SYSTEM,
        "user": user,
        "schema": parent.JUDGE_SCHEMA,
        "max_tokens": 1800,
        "effort": "low",
    }


def _run_vote_jobs(jobs: list[tuple[str, int]], workers: int, stage: str) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = json.loads((ART / "frozen-cases.json").read_text("utf-8"))
    products = parent.read_json(ART / "product-results.json")
    cases = {row["case_id"]: row for row in frozen["cases"]}
    out_path = ART / "judged-results.json"
    out = parent.read_json(out_path, {
        "schema_version": "haiku-prompt-atom-judges-v1",
        "run_id": "run-001",
        "judge_model": JUDGE_MODEL,
        "results": {},
        "conditional_cases": [],
    })
    random.Random(5801 if stage == "first" else 5802).shuffle(jobs)
    buckets = [jobs[index::workers] for index in range(workers)]
    clients = [LLM(model=JUDGE_MODEL) for _ in range(workers)]
    completed = 0

    def one_bucket(bucket: list[tuple[str, int]], worker_no: int) -> int:
        nonlocal completed
        client = clients[worker_no]
        count = 0
        for key, vote_no in bucket:
            product = products["results"][key]
            case_id, arm = key.split("::", 1)
            with LOCK:
                existing = out["results"].get(key, {}).get("votes", [])
                if any(vote.get("vote_no") == vote_no for vote in existing):
                    continue
            if product.get("error") or not product.get("output"):
                vote = {
                    "vote_no": vote_no,
                    "request": None,
                    "output": None,
                    "provider_exchanges": [],
                    "error": "product_call_failed",
                }
            else:
                request = judge_request(cases[case_id], product)
                result = parent.call_with_retry(
                    client,
                    kind=f"adr0058.judge.v{vote_no}.{case_id}.{arm}",
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
                row = out["results"].setdefault(key, {
                    "case_id": case_id,
                    "arm_id": arm,
                    "model": MODEL,
                    "judge_model": JUDGE_MODEL,
                    "votes": [],
                })
                row["votes"].append(vote)
                row["votes"].sort(key=lambda item: item["vote_no"])
                parent.write_json(out_path, out)
                completed += 1
                done = completed
            count += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"judge {stage}: {done}/{len(jobs)}", flush=True)
        return count

    if not jobs:
        print(f"judge {stage}: no pending jobs", flush=True)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, index) for index, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()


def run_judge_first(workers: int) -> None:
    products = parent.read_json(ART / "product-results.json")
    if len(products.get("results", {})) != 561:
        raise RuntimeError("first judge requires 561 product rows")
    judged = parent.read_json(ART / "judged-results.json", {"results": {}})
    jobs = []
    for key in sorted(products["results"]):
        votes = judged.get("results", {}).get(key, {}).get("votes", [])
        if not any(vote.get("vote_no") == 1 for vote in votes):
            jobs.append((key, 1))
    _run_vote_jobs(jobs, workers, "first")


def first_vote_correct(row: dict[str, Any]) -> bool | None:
    vote = next((vote for vote in row.get("votes", []) if vote.get("vote_no") == 1), None)
    if not vote or not vote.get("output"):
        return None
    return bool(vote["output"].get("correct"))


def run_judge_conditional(workers: int) -> None:
    judged_path = ART / "judged-results.json"
    judged = parent.read_json(judged_path)
    if len(judged.get("results", {})) != 561:
        raise RuntimeError("conditional judge requires 561 first-vote rows")
    conditional_cases = []
    for number in range(1, 52):
        case_id = f"cm-{number:03d}"
        baseline = first_vote_correct(judged["results"][f"{case_id}::baseline"])
        values = [first_vote_correct(judged["results"][f"{case_id}::{arm}"]) for arm in ARMS]
        if baseline is None or any(value is None or value != baseline for value in values):
            conditional_cases.append(case_id)
    judged["conditional_cases"] = conditional_cases
    parent.write_json(judged_path, judged)
    jobs = []
    for case_id in conditional_cases:
        for arm in ARMS:
            key = f"{case_id}::{arm}"
            existing = judged["results"][key].get("votes", [])
            for vote_no in (2, 3):
                if not any(vote.get("vote_no") == vote_no for vote in existing):
                    jobs.append((key, vote_no))
    print(f"conditional cases: {len(conditional_cases)}/51; pending votes: {len(jobs)}", flush=True)
    _run_vote_jobs(jobs, workers, "conditional")


def final_judgment(row: dict[str, Any], needs_three: bool) -> dict[str, Any]:
    votes = [vote for vote in row.get("votes", []) if vote.get("output") is not None]
    expected = 3 if needs_three else 1
    if len(votes) != expected:
        raise RuntimeError(f"invalid vote count: {row['case_id']} {row['arm_id']} {len(votes)}/{expected}")
    decisions = [bool(vote["output"].get("correct")) for vote in votes]
    correct = sum(decisions) >= (expected // 2 + 1)
    matching = [vote["output"] for vote in votes if bool(vote["output"].get("correct")) == correct]
    failure_types = [output.get("failure_type", "other") for output in matching]
    failure_type = Counter(failure_types).most_common(1)[0][0]
    representative = matching[-1]
    return {
        "correct": correct,
        "conclusion_correct": representative.get("conclusion_correct"),
        "materially_complete": representative.get("materially_complete"),
        "no_material_error": representative.get("no_material_error"),
        "failure_type": failure_type,
        "reason": representative.get("reason"),
        "missing_points": representative.get("missing_points", []),
        "vote_count": expected,
        "correct_votes": sum(decisions),
        "disagreement": len(set(decisions)) > 1,
    }


def mcnemar_exact(candidate_only: int, baseline_only: int) -> float:
    discordant = candidate_only + baseline_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(0, min(candidate_only, baseline_only) + 1))
    return min(1.0, 2.0 * tail / (2 ** discordant))


def holm_adjust(raw: dict[str, float]) -> dict[str, float]:
    ordered = sorted(raw.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (arm, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (total - rank)))
        adjusted[arm] = running
    return adjusted


def render_questions(
    frozen: dict[str, Any],
    products: dict[str, Any],
    judged: dict[str, Any],
    finals: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    EXP.mkdir(parents=True, exist_ok=True)
    questions = []
    conditional = set(judged.get("conditional_cases", []))
    for number, case in enumerate(frozen["cases"], 1):
        case_id = case["case_id"]
        lines = [
            f"# ADR-0058 질문 {number:03d}: {case_id}", "",
            "## 1. 실행 메타", "", "- run: `run-001`", "- phase: `probe/in_sample`",
            f"- conditional 3-vote: `{case_id in conditional}`", "- product: `claude-haiku-4-5-20251001`",
            "- judge: `claude-opus-5`", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", case["reference_answer"], "",
            "## 4. 제품 입력을 구성한 원값", "",
        ]
        for arm in ARMS:
            lines.extend([
                f"### arm `{arm}`", "", "```json",
                json.dumps(case["product_requests"][arm], ensure_ascii=False, indent=2), "```", "",
            ])
        lines.extend(["## 5. 제품 모델 호출 — run·arm별 실제 원문", ""])
        for arm in ARMS:
            key = f"{case_id}::{arm}"
            lines.extend([
                f"### arm `{arm}`", "", "```json",
                json.dumps(products["results"][key], ensure_ascii=False, indent=2), "```", "",
            ])
        lines.extend([
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
            "없음. 동일한 frozen gold article 전문을 각 prompt arm의 Haiku에 직접 제공했다.", "",
            "## 7. 채점 호출과 반복 판정", "",
        ])
        for arm in ARMS:
            key = f"{case_id}::{arm}"
            lines.extend([
                f"### arm `{arm}`", "", "```json",
                json.dumps({"votes": judged["results"][key]["votes"], "final": finals[key]}, ensure_ascii=False, indent=2),
                "```", "",
            ])
        lines.extend([
            "## 8. 사례 최종 판정", "", "| arm | correct | votes | failure_type |", "|---|---:|---:|---|",
        ])
        for arm in ARMS:
            final = finals[f"{case_id}::{arm}"]
            lines.append(f"| `{arm}` | `{final['correct']}` | `{final['correct_votes']}/{final['vote_count']}` | `{final['failure_type']}` |")
        lines.append("")
        path = EXP / f"질문-{number:03d}-{case_id}.md"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        questions.append({"number": number, "case_id": case_id, "file": path.name, "sha256": parent.sha(path)})
    return questions


def finalize() -> None:
    frozen = json.loads((ART / "frozen-cases.json").read_text("utf-8"))
    products = parent.read_json(ART / "product-results.json")
    judged = parent.read_json(ART / "judged-results.json")
    if len(products.get("results", {})) != 561 or len(judged.get("results", {})) != 561:
        raise RuntimeError("finalize requires 561 product and judge rows")
    conditional = set(judged.get("conditional_cases", []))
    finals = {
        key: final_judgment(row, row["case_id"] in conditional)
        for key, row in judged["results"].items()
    }
    by_arm: dict[str, Any] = {}
    case_scores: dict[str, dict[str, bool]] = {}
    for arm in ARMS:
        prows = [products["results"][f"cm-{number:03d}::{arm}"] for number in range(1, 52)]
        jrows = [judged["results"][f"cm-{number:03d}::{arm}"] for number in range(1, 52)]
        judgments = [finals[f"cm-{number:03d}::{arm}"] for number in range(1, 52)]
        correct = sum(item["correct"] for item in judgments)
        failures = Counter(item["failure_type"] for item in judgments)
        votes = [vote for row in jrows for vote in row["votes"]]
        by_arm[arm] = {
            "correct": correct,
            "total": 51,
            "accuracy": round(correct / 51, 4),
            "wrong_cases": [f"cm-{number:03d}" for number, item in enumerate(judgments, 1) if not item["correct"]],
            "answerable_false": sum((row.get("output") or {}).get("answerable") is False for row in prows),
            "product_errors": sum(bool(row.get("error")) for row in prows),
            "judge_vote_errors": sum(bool(vote.get("error")) for vote in votes),
            "judge_disagreements": sum(item["disagreement"] for item in judgments),
            "failure_types": dict(sorted(failures.items())),
            "product_usage": exchange_usage(prows),
            "judge_usage": exchange_usage(votes),
        }
        for number, item in enumerate(judgments, 1):
            case_scores.setdefault(f"cm-{number:03d}", {})[arm] = item["correct"]

    baseline = case_scores
    comparisons: dict[str, Any] = {}
    raw_p: dict[str, float] = {}
    for arm in ARMS[1:]:
        counts = {"candidate_only": 0, "baseline_only_regression": 0, "both_correct": 0, "both_wrong": 0}
        for case_id, values in baseline.items():
            base, candidate = values["baseline"], values[arm]
            key = "both_correct" if base and candidate else "baseline_only_regression" if base else "candidate_only" if candidate else "both_wrong"
            counts[key] += 1
        counts["delta"] = counts["candidate_only"] - counts["baseline_only_regression"]
        raw_p[arm] = mcnemar_exact(counts["candidate_only"], counts["baseline_only_regression"])
        comparisons[arm] = counts
    adjusted = holm_adjust(raw_p)
    for arm in comparisons:
        comparisons[arm]["mcnemar_exact_p"] = round(raw_p[arm], 6)
        comparisons[arm]["holm_adjusted_p"] = round(adjusted[arm], 6)

    unstable_cases = [case_id for case_id, values in case_scores.items() if len(set(values.values())) > 1]
    baseline_unsupported = by_arm["baseline"]["failure_types"].get("unsupported_inference", 0)
    assessments = {}
    removal_arms = ["no-grounding", "no-conclusion-first", "no-completeness", "no-ref-hygiene", "no-abstention-gate"]
    for arm in removal_arms:
        pair = comparisons[arm]
        unsupported = by_arm[arm]["failure_types"].get("unsupported_inference", 0)
        if pair["delta"] <= -3:
            assessment = "removed_atom_beneficial"
        elif pair["delta"] >= 3 and pair["baseline_only_regression"] <= 2 and unsupported <= baseline_unsupported:
            assessment = "removed_atom_harmful"
        else:
            assessment = "neutral_or_unstable"
        assessments[arm] = assessment
    for arm in ["minimal-core", "coverage-first", "evidence-checklist", "context-first-question-last"]:
        pair = comparisons[arm]
        baseline_p95 = by_arm["baseline"]["product_usage"]["p95_ms"] or 0
        arm_p95 = by_arm[arm]["product_usage"]["p95_ms"] or 0
        assessments[arm] = (
            "promising" if pair["delta"] >= 3 and pair["baseline_only_regression"] <= 2
            and (baseline_p95 == 0 or arm_p95 <= baseline_p95 * 1.5) else "not_promising"
        )
    assessments["neutral-context"] = (
        "oracle_framing_contributes" if comparisons["neutral-context"]["delta"] <= -2 else "oracle_framing_not_material"
    )

    summary = {
        "schema_version": "haiku-prompt-atom-summary-v1",
        "run_id": "run-001",
        "primary_metric": "Opus 5 conditional-majority correct / 51",
        "cases": 51,
        "arms": 11,
        "product_rows": 561,
        "conditional_cases": sorted(conditional),
        "conditional_case_count": len(conditional),
        "judge_vote_rows": sum(len(row["votes"]) for row in judged["results"].values()),
        "by_arm": by_arm,
        "comparisons_vs_baseline": comparisons,
        "assessments": assessments,
        "prompt_sensitivity": {
            "best_correct": max(row["correct"] for row in by_arm.values()),
            "worst_correct": min(row["correct"] for row in by_arm.values()),
            "spread_cases": max(row["correct"] for row in by_arm.values()) - min(row["correct"] for row in by_arm.values()),
            "unstable_case_count": len(unstable_cases),
            "unstable_cases": unstable_cases,
        },
        "hypotheses": {
            "completeness_removal_drops_at_least_3": comparisons["no-completeness"]["delta"] <= -3,
            "neutral_context_drops_at_least_2": comparisons["neutral-context"]["delta"] <= -2,
            "some_existing_atom_removal_improves_at_least_2": any(comparisons[arm]["delta"] >= 2 for arm in ["no-grounding", "no-conclusion-first", "no-ref-hygiene", "no-abstention-gate"]),
            "evidence_or_question_last_improves_at_least_3_with_at_most_2_regressions": any(
                comparisons[arm]["delta"] >= 3 and comparisons[arm]["baseline_only_regression"] <= 2
                for arm in ["evidence-checklist", "context-first-question-last"]
            ),
        },
        "limitations": [
            "반복 사용된 in-sample cm-core-51 gold-only 집합이며 운영 채택 근거가 아니다.",
            "모든 사례가 answerable이므로 불완전 근거와 unanswerable 안전성을 평가하지 못한다.",
            "동일 Opus 5 반복 다수결은 독립 인간 판정이 아니다.",
            "OAT ablation은 prompt 원자 간 상호작용을 식별하지 못한다.",
            "정답 조문 oracle framing은 실제 RAG 운영 prompt에 사용할 수 없다.",
        ],
    }
    parent.write_json(ART / "summary.json", summary)
    questions = render_questions(frozen, products, judged, finals)

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
        "comparisons": [{"baseline_arm": "baseline", "candidate_arm": arm, **row} for arm, row in comparisons.items()],
        "judge_disagreements": sum(row["judge_disagreements"] for row in by_arm.values()),
        "usage": {
            "product_rows": 561,
            "judge_vote_rows": summary["judge_vote_rows"],
        },
        "latency": {arm: row["product_usage"] for arm, row in by_arm.items()},
        "error_taxonomy": sorted({failure for row in by_arm.values() for failure in row["failure_types"]}),
        "assessments": assessments,
    }
    manifest["questions"] = questions
    parent.write_json(manifest_path, manifest)

    index = [
        "# ADR-0058 실험 질문 인덱스", "", f"- run: `run-001 / complete`",
        f"- conditional 3-vote cases: `{len(conditional)}/51`", "",
        "| arm | correct/51 | delta |", "|---|---:|---:|",
    ]
    index.extend(
        f"| `{arm}` | {by_arm[arm]['correct']}/51 | {'-' if arm == 'baseline' else comparisons[arm]['delta']} |"
        for arm in ARMS
    )
    index.extend(["", "## 질문", ""])
    index.extend(f"- [{row['case_id']}]({row['file']}) — `{row['sha256']}`" for row in questions)
    (EXP / "README.md").write_text("\n".join(index) + "\n", "utf-8")

    artifact_files = [
        ("coverage-preflight.json", "Frozen suite and call-count preflight", False),
        ("frozen-cases.json", "51 cases x 11 exact product requests and evaluator-only references", True),
        ("prompt-matrix.json", "Exact prompt variants and request lineage", True),
        ("literature-review.md", "Primary research review frozen before run", False),
        ("product-results.json", "561 Haiku product calls with raw provider exchanges", True),
        ("judged-results.json", "Opus first and conditional rejudge raw calls", True),
        ("summary.json", "Arm, paired, usage, latency and hypothesis aggregates", False),
    ]
    parent.write_json(ART / "manifest.json", {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0058",
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
    parser.add_argument("--lanes", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "answers":
        run_answers(args.workers, args.lanes)
    elif args.command == "judge-first":
        run_judge_first(args.workers)
    elif args.command == "judge-conditional":
        run_judge_conditional(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
