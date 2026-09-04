#!/usr/bin/env python3
"""ADR-0100: Opus 5 question-only final-answer benchmark over Golden 61."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from scripts.rag_open_model_ceiling import JUDGE_SCHEMA, JUDGE_SYSTEM  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0100-opus-question-only-golden-61"
ART = ADR / "artifacts"
EXP = ADR / "실험"
MANIFEST = EXP / "manifest.json"
CM = ROOT / "data/review/cm_core_e2e_v2.json"
FSC = ROOT / "data/review/fsc_hard_retrieval_v2.json"
ANSWER_MODEL = "claude-opus-5"
JUDGE_MODELS = ("claude-sonnet-5", "claude-opus-5")
ANSWER_MAX_TOKENS = 8000
JUDGE_MAX_TOKENS = 1800
EXPECTED_SOURCE_HASHES = {
    "data/review/cm_core_e2e_v2.json":
        "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    "data/review/fsc_hard_retrieval_v2.json":
        "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
}
EXPECTED_COMBINED_HASH = (
    "fd8ce72cab5cb29ceef718706ef6b502a800714b7884add8123f1d40745b1863"
)
LOCK = threading.Lock()
LOCAL = threading.local()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temporary.replace(path)


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def combined_source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def verify_sources() -> None:
    for relative, expected in EXPECTED_SOURCE_HASHES.items():
        actual = sha(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"frozen source drift: {relative} {actual} != {expected}")
    combined = combined_source_hash([CM, FSC])
    if combined != EXPECTED_COMBINED_HASH:
        raise RuntimeError(f"combined source drift: {combined}")


def prepare() -> None:
    verify_sources()
    sources = [("cm", CM), ("fsc-hard", FSC)]
    products: list[dict[str, Any]] = []
    judges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for suite, path in sources:
        source = read_json(path)
        for case in source["cases"]:
            case_id = str(case["id"])
            if case_id in seen:
                raise RuntimeError(f"duplicate case ID: {case_id}")
            seen.add(case_id)
            question = str(case["question"])
            request = {
                "model": ANSWER_MODEL,
                "messages": [{"role": "user", "content": question}],
                "schema": None,
                "tools": [],
                "max_tokens": ANSWER_MAX_TOKENS,
                "temperature": "provider_default",
                "effort": "provider_default",
            }
            serialized = json.dumps(request, ensure_ascii=False)
            if "기준답변" in serialized or str(case["reference_answer"]) in serialized:
                raise RuntimeError(f"reference answer leaked into product input: {case_id}")
            products.append({
                "number": len(products) + 1,
                "case_id": case_id,
                "suite": suite,
                "question": question,
                "request": request,
                "request_sha256": text_sha(json.dumps(
                    request, ensure_ascii=False, sort_keys=True)),
            })
            judges.append({
                "number": len(judges) + 1,
                "case_id": case_id,
                "suite": suite,
                "question": question,
                "reference_answer": str(case["reference_answer"]),
                "reference_answer_visibility": "offline_evaluator_only",
                "reference_sha256": case.get("reference_sha256")
                    or text_sha(str(case["reference_answer"])),
                "answer_as_of": case.get("answer_as_of"),
            })
    if len(products) != 61 or len(judges) != 61:
        raise RuntimeError(f"unexpected case count: {len(products)}")

    frozen_at = now()
    write_json(ART / "frozen-product-inputs.json", {
        "schema_version": "opus-question-only-golden-61-products-v1",
        "frozen_at": frozen_at,
        "selection_rule": "CM v2 51건 + FSC hard v2 10건 전수; 제외 없음",
        "case_count": 61,
        "candidate_model_allowlist": [ANSWER_MODEL],
        "benchmark_class": "offline_benchmark_candidate",
        "isolation": {
            "may_change_product_answer": False,
            "may_enter_product_context": False,
            "judge_only_use": True,
        },
        "cases": products,
    })
    write_json(ART / "frozen-judge-inputs.json", {
        "schema_version": "opus-question-only-golden-61-judges-v1",
        "frozen_at": frozen_at,
        "case_count": 61,
        "judge_models": list(JUDGE_MODELS),
        "judge_repeats": 1,
        "model_identity_blind": True,
        "cases": judges,
    })
    write_json(ART / "dataset-lock.json", {
        "schema_version": "opus-question-only-golden-61-dataset-lock-v1",
        "frozen_at": frozen_at,
        "sources": [
            {"path": relative, "sha256": expected,
             "cases": 51 if "cm_core" in relative else 10}
            for relative, expected in EXPECTED_SOURCE_HASHES.items()
        ],
        "combined_hash_algorithm": "sha256(length_u64_be || bytes, in source order)",
        "combined_sha256": EXPECTED_COMBINED_HASH,
        "legal_version_checked": True,
        "reference_version_checked": True,
    })
    print(json.dumps({
        "cases": 61,
        "product_inputs_sha256": sha(ART / "frozen-product-inputs.json"),
        "judge_inputs_sha256": sha(ART / "frozen-judge-inputs.json"),
        "dataset_lock_sha256": sha(ART / "dataset-lock.json"),
    }, ensure_ascii=False, indent=2))


def answer_client():
    import anthropic

    client = getattr(LOCAL, "answer_client", None)
    if client is None:
        client = anthropic.Anthropic(timeout=180.0)
        LOCAL.answer_client = client
    return client


def call_answer(case: dict[str, Any]) -> dict[str, Any]:
    request = case["request"]
    attempts: list[dict[str, Any]] = []
    answer = ""
    error = ""
    for attempt_no in range(1, 3):
        started = time.perf_counter()
        exchange: dict[str, Any] = {
            "attempt": attempt_no,
            "at": now(),
            "request": request,
            "provider_response": None,
            "dur_ms": 0,
            "error": "",
        }
        try:
            response = answer_client().messages.create(
                model=ANSWER_MODEL,
                max_tokens=ANSWER_MAX_TOKENS,
                messages=request["messages"],
            )
            raw = response.model_dump(mode="json")
            answer = "\n".join(
                str(block.get("text") or "")
                for block in raw.get("content", [])
                if block.get("type") == "text"
            ).strip()
            exchange["provider_response"] = raw
            if not answer:
                error = "empty_text_response"
                exchange["error"] = error
            elif raw.get("stop_reason") == "max_tokens":
                error = "max_tokens"
                exchange["error"] = error
            else:
                error = ""
        except Exception as exc:  # provider failure is part of the immutable run record
            error = f"{type(exc).__name__}: {exc}"
            exchange["error"] = error
        finally:
            exchange["dur_ms"] = int((time.perf_counter() - started) * 1000)
            attempts.append(exchange)
        if not error:
            break
    return {
        "case_id": case["case_id"],
        "arm_id": "opus-question-only",
        "class": "offline_benchmark_candidate",
        "model": ANSWER_MODEL,
        "request_sha256": case["request_sha256"],
        "answer": answer,
        "attempts": attempts,
        "error": error or None,
    }


def run_answers(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required")
    verify_sources()
    frozen = read_json(ART / "frozen-product-inputs.json")
    if not frozen or len(frozen.get("cases", [])) != 61:
        raise RuntimeError("run prepare first")
    path = ART / "answer-results.json"
    output = read_json(path, {
        "schema_version": "opus-question-only-golden-61-answer-results-v1",
        "run_id": "run-001",
        "model": ANSWER_MODEL,
        "results": {},
    })
    pending = [case for case in frozen["cases"]
               if case["case_id"] not in output["results"]]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(call_answer, case): case["case_id"] for case in pending}
        for future in as_completed(futures):
            row = future.result()
            with LOCK:
                output["results"][row["case_id"]] = row
                write_json(path, output)
                done = len(output["results"])
            print(f"answer {done}/61 {row['case_id']} error={row['error']}", flush=True)
    print(f"answers complete: {len(output['results'])}/61", flush=True)


def judge_user(question: str, reference: str, answer: str) -> str:
    return (
        f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
        f"[시스템 답변]\n{answer}\n\n"
        "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다."
    )


def judge_client(model: str) -> LLM:
    clients = getattr(LOCAL, "judge_clients", None)
    if clients is None:
        clients = {}
        LOCAL.judge_clients = clients
    if model not in clients:
        clients[model] = LLM(model=model)
    return clients[model]


def call_judge(task: tuple[dict[str, Any], dict[str, Any], str]) -> dict[str, Any]:
    case, answer_row, model = task
    user = judge_user(case["question"], case["reference_answer"], answer_row["answer"])
    request = {
        "system": JUDGE_SYSTEM,
        "user": user,
        "schema": JUDGE_SCHEMA,
        "max_tokens": JUDGE_MAX_TOKENS,
        "effort": "low",
    }
    client = judge_client(model)
    exchanges: list[dict[str, Any]] = []
    parsed = None
    error = ""
    for attempt_no in range(1, 3):
        before = len(client.log)
        parsed = client.structured(
            kind=f"adr0100.judge.{model}.{case['case_id']}",
            system=JUDGE_SYSTEM,
            user=user,
            schema=JUDGE_SCHEMA,
            max_tokens=JUDGE_MAX_TOKENS,
            effort="low",
        )
        attempts = [exchange.dump() for exchange in client.log[before:]]
        for exchange in attempts:
            exchange["attempt"] = attempt_no
        exchanges.extend(attempts)
        error = "" if parsed is not None else (
            attempts[-1].get("error") if attempts else "unknown judge error")
        if parsed is not None:
            break
    return {
        "case_id": case["case_id"],
        "arm_id": "opus-question-only",
        "judge_model": model,
        "request": request,
        "output": parsed,
        "provider_exchanges": exchanges,
        "error": error or None,
    }


def run_judges(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    verify_sources()
    answers = read_json(ART / "answer-results.json")
    frozen = read_json(ART / "frozen-judge-inputs.json")
    if not answers or len(answers.get("results", {})) != 61:
        raise RuntimeError("61 answers are required")
    if any(row.get("error") or not row.get("answer")
           for row in answers["results"].values()):
        raise RuntimeError("answer errors remain; do not judge an incomplete run")
    path = ART / "judge-results.json"
    output = read_json(path, {
        "schema_version": "opus-question-only-golden-61-judge-results-v1",
        "run_id": "run-001",
        "judge_models": list(JUDGE_MODELS),
        "results": {},
    })
    tasks = []
    for case in frozen["cases"]:
        for model in JUDGE_MODELS:
            key = f"{case['case_id']}::{model}"
            if key not in output["results"]:
                tasks.append((case, answers["results"][case["case_id"]], model))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(call_judge, task): (task[0]["case_id"], task[2])
                   for task in tasks}
        for future in as_completed(futures):
            row = future.result()
            key = f"{row['case_id']}::{row['judge_model']}"
            with LOCK:
                output["results"][key] = row
                write_json(path, output)
                done = len(output["results"])
            print(f"judge {done}/122 {key} error={row['error']}", flush=True)
    print(f"judges complete: {len(output['results'])}/122", flush=True)


def answer_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = [attempt for row in rows for attempt in row.get("attempts", [])]
    successful = [attempt for attempt in attempts if not attempt.get("error")]
    durations = [int(attempt.get("dur_ms", 0)) for attempt in successful]
    usages = [((attempt.get("provider_response") or {}).get("usage") or {})
              for attempt in successful]
    return {
        "calls": len(attempts),
        "successful_calls": len(successful),
        "errors": sum(bool(attempt.get("error")) for attempt in attempts),
        "input_tokens": sum(int(usage.get("input_tokens", 0)) for usage in usages),
        "output_tokens": sum(int(usage.get("output_tokens", 0)) for usage in usages),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def judge_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = [exchange for row in rows
                 for exchange in row.get("provider_exchanges", [])]
    successful = [exchange for exchange in exchanges if not exchange.get("error")]
    durations = [int(exchange.get("dur_ms", 0)) for exchange in successful]
    return {
        "calls": len(exchanges),
        "successful_calls": len(successful),
        "errors": sum(bool(exchange.get("error")) for exchange in exchanges),
        "input_tokens": sum(int((exchange.get("usage") or {}).get("input_tokens", 0))
                            for exchange in exchanges),
        "output_tokens": sum(int((exchange.get("usage") or {}).get("output_tokens", 0))
                             for exchange in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def consensus_case(case: dict[str, Any], judges: dict[str, Any]) -> dict[str, Any]:
    outputs = {
        model: judges["results"][f"{case['case_id']}::{model}"]["output"]
        for model in JUDGE_MODELS
    }
    correctness = {model: bool(output["correct"]) for model, output in outputs.items()}
    strict = all(correctness.values())
    any_correct = any(correctness.values())
    disagreement = len(set(correctness.values())) > 1
    if disagreement:
        failure_type = "judge_or_gold_error"
    elif strict:
        failure_type = "none"
    else:
        types = [str(output.get("failure_type") or "other")
                 for output in outputs.values()]
        failure_type = types[0] if len(set(types)) == 1 else "other"
    return {
        "case_id": case["case_id"],
        "suite": case["suite"],
        "judge_correct": correctness,
        "strict_consensus_correct": strict,
        "any_judge_correct": any_correct,
        "judge_disagreement": disagreement,
        "consensus_conclusion_correct": all(
            bool(output["conclusion_correct"]) for output in outputs.values()),
        "consensus_materially_complete": all(
            bool(output["materially_complete"]) for output in outputs.values()),
        "consensus_no_material_error": all(
            bool(output["no_material_error"]) for output in outputs.values()),
        "failure_type": failure_type,
    }


def render_questions(
    product_cases: list[dict[str, Any]],
    judge_cases: dict[str, dict[str, Any]],
    answers: dict[str, Any],
    judges: dict[str, Any],
    consensus: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    EXP.mkdir(parents=True, exist_ok=True)
    question_rows = []
    for case in product_cases:
        case_id = case["case_id"]
        judge_case = judge_cases[case_id]
        answer_row = answers["results"][case_id]
        verdict = consensus[case_id]
        lines = [
            f"# ADR-0100 질문 {case['number']:03d}: {case_id}", "",
            "## 1. 실행 메타", "",
            "- run: `run-001`", "- phase: `probe/in_sample`",
            "- candidate class: `offline_benchmark_candidate`",
            f"- answer model: `{ANSWER_MODEL}`", "- retrieval: `not_applicable`", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "",
            judge_case["reference_answer"], "",
            "## 4. 제품 입력을 구성한 원값", "",
            "검색 좌표·조문·정의·Wiki·관계·필터 결과 없음. 아래 요청만 전송했다.", "",
            "```json", json.dumps(case["request"], ensure_ascii=False, indent=2), "```", "",
            "### 회수·탈락 단계 원장 — run·arm별", "",
            "해당 없음. 모든 arm에서 retrieval 후보 집합을 만들지 않았다.", "",
            "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
            "### baseline — deterministic abstention", "",
            "모델 호출 없음. 빈 답이며 정의상 `correct=false`다.", "",
            "### opus-question-only", "", "```json",
            json.dumps(answer_row, ensure_ascii=False, indent=2), "```", "",
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
            "없음. router/compiler/verifier/repair를 호출하지 않았다.", "",
            "## 7. 채점 호출과 반복 판정", "",
        ]
        for model in JUDGE_MODELS:
            row = judges["results"][f"{case_id}::{model}"]
            lines.extend([f"### `{model}`", "", "```json",
                          json.dumps(row, ensure_ascii=False, indent=2), "```", ""])
        lines.extend([
            "## 8. 사례 최종 판정", "",
            "```json", json.dumps(verdict, ensure_ascii=False, indent=2), "```", "",
            f"paired 분류: `{'candidate_only' if verdict['strict_consensus_correct'] else 'both_wrong'}`", "",
        ])
        path = EXP / f"질문-{case['number']:03d}-{case_id}.md"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        question_rows.append({
            "number": case["number"], "case_id": case_id,
            "file": path.name, "sha256": sha(path),
        })
    return question_rows


def render_experiment_index(
    product_cases: list[dict[str, Any]],
    consensus: dict[str, dict[str, Any]],
) -> None:
    lines = [
        "# ADR-0100 실험 질문 인덱스", "",
        "- run: `run-001`", "- 61건 전수 × Opus 5 question-only",
        "- judge: Sonnet 5 + Opus 5 independent", "- retrieval: not applicable", "",
        "| 번호 | case | strict | Sonnet | Opus | disagreement | failure | 파일 |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for case in product_cases:
        verdict = consensus[case["case_id"]]
        lines.append(
            f"| {case['number']:03d} | `{case['case_id']}` | "
            f"{str(verdict['strict_consensus_correct']).lower()} | "
            f"{str(verdict['judge_correct']['claude-sonnet-5']).lower()} | "
            f"{str(verdict['judge_correct']['claude-opus-5']).lower()} | "
            f"{str(verdict['judge_disagreement']).lower()} | "
            f"`{verdict['failure_type']}` | "
            f"[기록](질문-{case['number']:03d}-{case['case_id']}.md) |"
        )
    (EXP / "README.md").write_text("\n".join(lines) + "\n", "utf-8")


def finalize() -> None:
    verify_sources()
    products = read_json(ART / "frozen-product-inputs.json")
    judge_inputs = read_json(ART / "frozen-judge-inputs.json")
    answers = read_json(ART / "answer-results.json")
    judges = read_json(ART / "judge-results.json")
    if len((answers or {}).get("results", {})) != 61:
        raise RuntimeError("cannot finalize without 61 answers")
    if len((judges or {}).get("results", {})) != 122:
        raise RuntimeError("cannot finalize without 122 judge rows")
    if any(row.get("error") or row.get("output") is None
           for row in judges["results"].values()):
        raise RuntimeError("judge errors remain")

    judge_case_map = {case["case_id"]: case for case in judge_inputs["cases"]}
    rows = [consensus_case(case, judges) for case in products["cases"]]
    consensus = {row["case_id"]: row for row in rows}
    strict = sum(row["strict_consensus_correct"] for row in rows)
    any_correct = sum(row["any_judge_correct"] for row in rows)
    disagreements = sum(row["judge_disagreement"] for row in rows)
    by_judge = {
        model: sum(row["judge_correct"][model] for row in rows)
        for model in JUDGE_MODELS
    }
    quality_axes = {
        "conclusion_correct": sum(row["consensus_conclusion_correct"] for row in rows),
        "materially_complete": sum(row["consensus_materially_complete"] for row in rows),
        "no_material_error": sum(row["consensus_no_material_error"] for row in rows),
    }
    failure_types: dict[str, int] = {}
    for row in rows:
        failure_types[row["failure_type"]] = failure_types.get(row["failure_type"], 0) + 1
    by_suite = {}
    for suite in ("cm", "fsc-hard"):
        suite_rows = [row for row in rows if row["suite"] == suite]
        suite_correct = sum(row["strict_consensus_correct"] for row in suite_rows)
        by_suite[suite] = {
            "correct": suite_correct,
            "total": len(suite_rows),
            "accuracy": round(suite_correct / len(suite_rows), 4),
        }
    answer_rows = list(answers["results"].values())
    answer_stats = answer_usage(answer_rows)
    judge_stats = {
        model: judge_usage([row for row in judges["results"].values()
                            if row["judge_model"] == model])
        for model in JUDGE_MODELS
    }
    execution_complete = (
        len(answer_rows) == 61
        and all(stats["successful_calls"] >= 61 for stats in judge_stats.values())
    )
    success = (
        strict >= 43 and disagreements <= 6 and execution_complete
        and (answer_stats["p95_ms"] or 10**9) <= 60_000
    )
    summary = {
        "schema_version": "opus-question-only-golden-61-summary-v1",
        "run_id": "run-001",
        "definition": "질문 원문만 받은 Opus 5 답변의 dual-judge strict consensus 정확도",
        "cases": 61,
        "strict_consensus_correct": strict,
        "strict_consensus_accuracy": round(strict / 61, 4),
        "any_judge_correct_upper_bound": any_correct,
        "any_judge_accuracy_upper_bound": round(any_correct / 61, 4),
        "by_judge_correct": by_judge,
        "judge_disagreements": disagreements,
        "quality_axes_strict_consensus": quality_axes,
        "by_suite": by_suite,
        "failure_types": failure_types,
        "paired_vs_abstention": {
            "candidate_only": strict,
            "baseline_only_regression": 0,
            "both_correct": 0,
            "both_wrong": 61 - strict,
            "delta": strict,
        },
        "criteria": {
            "strict_at_least_43": strict >= 43,
            "disagreements_at_most_6": disagreements <= 6,
            "execution_complete": execution_complete,
            "answer_p95_at_most_60000_ms":
                (answer_stats["p95_ms"] or 10**9) <= 60_000,
            "supported": success,
        },
        "usage": {"answer": answer_stats, "judges": judge_stats},
        "case_results": rows,
        "limitations": [
            "CM/FSC 61건은 저장소에서 반복 사용된 내부 골든이며 외부 holdout이 아니다.",
            "LLM judge 두 개의 합의는 사람 확정 정확도가 아니며 불일치는 구간으로 보존한다.",
            "Opus 5가 답변과 한 judge를 겸하므로 Opus judge에는 self-preference 가능성이 있다.",
            "질문 원문만 제공했으므로 법령 시행시점·회사 내부규정 등 비공개 지식은 원천적으로 알 수 없다.",
        ],
    }
    write_json(ART / "summary.json", summary)
    write_json(ART / "disagreement-review-queue.json", {
        "schema_version": "opus-question-only-golden-61-disagreement-queue-v1",
        "cases": [row for row in rows if row["judge_disagreement"]],
    })
    question_rows = render_questions(
        products["cases"], judge_case_map, answers, judges, consensus)
    render_experiment_index(products["cases"], consensus)

    manifest = read_json(MANIFEST)
    manifest["runs"][0].update({
        "status": "complete",
        "artifact_path": str((ART / "summary.json").relative_to(ROOT)),
        "sha256": sha(ART / "summary.json"),
    })
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            "baseline": {"correct": 0, "total": 61, "accuracy": 0.0},
            "opus-question-only": {
                "correct": strict, "total": 61,
                "accuracy": round(strict / 61, 4),
                "by_judge_correct": by_judge,
                "any_judge_correct_upper_bound": any_correct,
                "quality_axes_strict_consensus": quality_axes,
                "by_suite": by_suite,
            },
        },
        "comparisons": [{
            "baseline_arm": "baseline",
            "candidate_arm": "opus-question-only",
            **summary["paired_vs_abstention"],
        }],
        "judge_disagreements": disagreements,
        "usage": summary["usage"],
        "latency": {"opus-question-only": answer_stats},
        "error_taxonomy": sorted(failure_types),
    }
    manifest["questions"] = question_rows
    write_json(MANIFEST, manifest)

    artifact_names = [
        ("dataset-lock.json", "동결 데이터셋 path·hash·버전 계약", False),
        ("frozen-product-inputs.json", "기준답변과 물리 분리한 61개 질문-only 요청", True),
        ("frozen-judge-inputs.json", "offline evaluator 전용 기준답변", True),
        ("answer-results.json", "Opus 5 일반 텍스트 답변과 provider 원응답", True),
        ("judge-results.json", "Sonnet 5·Opus 5 독립 채점 원응답", True),
        ("disagreement-review-queue.json", "judge 불일치 검토 queue", False),
        ("summary.json", "정확도·완전성·오류·토큰·지연 집계", False),
    ]
    write_json(ART / "manifest.json", {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0100",
        "files": [
            {"path": str((ART / name).relative_to(ROOT)),
             "sha256": sha(ART / name), "bytes": (ART / name).stat().st_size,
             "description": description,
             "contains_raw_prompts_and_outputs": raw}
            for name, description, raw in artifact_names
        ],
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "answers", "judge", "finalize"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "answers":
        run_answers(args.workers)
    elif args.command == "judge":
        run_judges(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
