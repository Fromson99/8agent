#!/usr/bin/env python3
"""ADR-0055: 정답 조문 전체 입력에서 격리 답변 모델 상한을 비교한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM, load_env


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0055-gold-article-open-model-ceiling"
ART = ADR / "artifacts"
EXP = ADR / "실험"
SOURCE = (ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0048-legal-reasoning-causal-portfolio"
          / "artifacts/frozen-cases.json")
QWEN_MODEL = "qwen/qwen3.8-27b"
JUDGE_MODEL = "claude-opus-5"
MODELS = [
    {"arm_id": "baseline", "model": QWEN_MODEL, "provider": "openrouter"},
    {"arm_id": "claude-fable-5", "model": "claude-fable-5", "provider": "anthropic"},
    {"arm_id": "claude-haiku-4-5", "model": "claude-haiku-4-5-20251001", "provider": "anthropic"},
    {"arm_id": "claude-opus-4-5", "model": "claude-opus-4-5-20251101", "provider": "anthropic"},
    {"arm_id": "claude-opus-4-6", "model": "claude-opus-4-6", "provider": "anthropic"},
    {"arm_id": "claude-opus-4-7", "model": "claude-opus-4-7", "provider": "anthropic"},
    {"arm_id": "claude-opus-4-8", "model": "claude-opus-4-8", "provider": "anthropic"},
    {"arm_id": "claude-opus-5", "model": "claude-opus-5", "provider": "anthropic"},
    {"arm_id": "claude-sonnet-4-5", "model": "claude-sonnet-4-5-20250929", "provider": "anthropic"},
    {"arm_id": "claude-sonnet-4-6", "model": "claude-sonnet-4-6", "provider": "anthropic"},
    {"arm_id": "claude-sonnet-5", "model": "claude-sonnet-5", "provider": "anthropic"},
]
JUDGE_SYSTEM = (
    "너는 법률 E2E 답변 채점자다. [기준답변]은 현업 원문에서 사람이 확정한 정답이다. "
    "[시스템 답변]이 그 답의 결론을 명확히 지지하고 모순하지 않으면 correct=true다. "
    "질문의 부정형 표현이나 첫 '예/아니오'가 아니라 답변 전체의 법률 내용을 본다. "
    "논리적 이중부정을 반드시 정규화한다. 예: '제척하지 않으면 안 된다'는 '제척해야 한다'와 같고, "
    "'알리지 않아도 되나요? 아니오'는 '알려야 한다'와 같다. 기대 명제를 지지한 뒤 관련된 추가 "
    "의무·예외를 설명해도 기준답변과 모순하지 않으면 정답이다. 기준답변이 수치·기간·계산식·요건·"
    "예외를 직접 묻는다면 그 핵심 세부사항까지 맞아야 materially_complete=true다. 결론이 맞아도 "
    "질문이 요구한 핵심 세부사항을 빠뜨리면 correct=false다. 더 정확한 조건·예외를 설명하는 것은 "
    "정답이다. 근거가 없다고 회피하거나 반대로 말하거나 다른 규범만 답하거나 중요한 수치·기간을 "
    "틀리면 false다. 채점 순서: (1) 기준답변을 최소 필수명제로 분해하고, (2) 시스템 답변이 각 "
    "명제를 지지하는지 확인하고, (3) 반대 결론이나 중요한 수치·조건·예외 오류가 있는지 확인한다. "
    "기준답변보다 상세하다는 이유만으로 감점하지 마라. 모든 판정은 제공된 질문·기준답변·시스템 "
    "답변만으로 한다. 모델 이름은 제공되지 않으며 추측하지 마라."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "conclusion_correct": {"type": "boolean"},
        "materially_complete": {"type": "boolean"},
        "no_material_error": {"type": "boolean"},
        "reason": {"type": "string"},
        "missing_points": {"type": "array", "items": {"type": "string"}},
        "failure_type": {
            "type": "string",
            "enum": [
                "none", "governing_rule_selection", "scope_actor_mismatch",
                "condition_exception", "numeric_temporal", "authority_or_version",
                "definition_resolution", "required_issue_omission",
                "unsupported_inference", "judge_or_gold_error", "other",
            ],
        },
    },
    "required": ["correct", "conclusion_correct", "materially_complete",
                 "no_material_error", "reason", "missing_points", "failure_type"],
    "additionalProperties": False,
}
LOCK = threading.Lock()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def model_inventory() -> dict[str, Any]:
    load_env()
    or_key = os.environ.get("OPEN_ROUTER") or os.environ.get("OPENROUTER_API_KEY", "")
    headers = {"Authorization": f"Bearer {or_key}"}
    raw_or = requests.get("https://openrouter.ai/api/v1/models", headers=headers,
                          timeout=30).json()["data"]
    a_headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
    }
    raw_a = requests.get("https://api.anthropic.com/v1/models?limit=100",
                         headers=a_headers, timeout=30).json()["data"]
    wanted_or = {QWEN_MODEL}
    wanted_a = {m["model"] for m in MODELS if m["provider"] == "anthropic"}
    return {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": (
            "OpenRouter 운영 기본 qwen/qwen3.8-27b 1종 + 구성된 Anthropic API "
            "/v1/models가 반환한 활성 Claude 모델 전수; aliases와 OpenRouter batch/fast "
            "변형은 제외"
        ),
        "openrouter": [
            {k: row.get(k) for k in ("id", "name", "created", "context_length", "pricing")}
            for row in raw_or if row.get("id") in wanted_or
        ],
        "anthropic": [
            {k: row.get(k) for k in ("id", "display_name", "created_at", "type")}
            for row in raw_a if row.get("id") in wanted_a
        ],
        "arms": MODELS,
    }


def prepare() -> None:
    source = read_json(SOURCE)
    cases = []
    for row in source["cases"]:
        gold = row["variants"]["gold_only"]
        request = gold["request"]
        if "[기준답변]" in request["system"] or "[기준답변]" in request["user"]:
            raise RuntimeError(f"reference leak in {row['case_no']}")
        cases.append({
            "case_id": row["case_no"],
            "question": row["question"],
            "reference_answer": row["reference_answer"],
            "reference_answer_visibility": "offline_evaluator_only",
            "gold_evidence": row["gold_evidence"],
            "product_request": {
                "system": request["system"],
                "user": request["user"],
                "schema": request["schema"],
                "max_tokens": request["max_tokens"],
                "effort": None,
                "temperature": {
                    "openrouter": 0,
                    "anthropic": "provider_default",
                },
            },
        })
    frozen = {
        "schema_version": "open-model-ceiling-frozen-v1",
        "selection_rule": "ADR-0048 causal portfolio 8건의 gold_only 입력 전수",
        "in_sample": True,
        "decision_eligible": False,
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha(SOURCE),
        "case_count": len(cases),
        "models": MODELS,
        "judge": JUDGE_MODEL,
        "judge_repeats": 1,
        "provider_error_retry": 1,
        "candidate_order": "case index만큼 model order를 rotate",
        "judge_order": "seed 5501 deterministic shuffle; model identity blind",
        "cases": cases,
    }
    write_json(ART / "frozen-cases.json", frozen)
    inventory = model_inventory()
    if {row["id"] for row in inventory["openrouter"]} != {QWEN_MODEL}:
        raise RuntimeError("Qwen model inventory mismatch")
    if {row["id"] for row in inventory["anthropic"]} != {
            m["model"] for m in MODELS if m["provider"] == "anthropic"}:
        raise RuntimeError("Anthropic model inventory mismatch")
    write_json(ART / "model-inventory.json", inventory)
    print(json.dumps({
        "frozen_cases_sha256": sha(ART / "frozen-cases.json"),
        "model_inventory_sha256": sha(ART / "model-inventory.json"),
        "cases": len(cases), "models": len(MODELS),
    }, ensure_ascii=False, indent=2))


def clients() -> dict[str, LLM]:
    result: dict[str, LLM] = {}
    for spec in MODELS:
        os.environ["LLM_BACKEND"] = spec["provider"]
        result[spec["arm_id"]] = LLM(model=spec["model"])
    os.environ["LLM_BACKEND"] = "anthropic"
    return result


def call_with_retry(client: LLM, *, kind: str, system: str, user: str,
                    schema: dict, max_tokens: int, effort: str | None) -> dict[str, Any]:
    attempts = []
    parsed = None
    for _ in range(2):
        before = len(client.log)
        parsed = client.structured(kind=kind, system=system, user=user, schema=schema,
                                   max_tokens=max_tokens, effort=effort)
        attempts.extend(ex.dump() for ex in client.log[before:])
        if parsed is not None:
            break
    return {"parsed": parsed, "attempts": attempts,
            "error": None if parsed is not None else attempts[-1].get("error", "unknown")}


def run_answers(workers: int) -> None:
    frozen = read_json(ART / "frozen-cases.json")
    out_path = ART / "product-results.json"
    out = read_json(out_path, {
        "schema_version": "open-model-ceiling-products-v1",
        "run_id": "run-001", "results": {},
    })
    llms = clients()

    def one_model(spec: dict[str, str]) -> str:
        arm = spec["arm_id"]
        client = llms[arm]
        order = list(range(len(frozen["cases"])))
        shift = MODELS.index(spec) % len(order)
        order = order[shift:] + order[:shift]
        for idx in order:
            case = frozen["cases"][idx]
            key = f"{case['case_id']}::{arm}"
            with LOCK:
                if key in out["results"]:
                    continue
            req = case["product_request"]
            result = call_with_retry(
                client, kind=f"adr0055.{case['case_id']}.{arm}",
                system=req["system"], user=req["user"], schema=req["schema"],
                max_tokens=req["max_tokens"], effort=None)
            row = {
                "case_id": case["case_id"], "arm_id": arm,
                "model": spec["model"], "provider": spec["provider"],
                "request": req, "output": result["parsed"],
                "provider_exchanges": result["attempts"], "error": result["error"],
            }
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
        return arm

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_model, spec) for spec in MODELS]
        for future in as_completed(futures):
            print(f"answer arm complete: {future.result()}", flush=True)


def judge_user(question: str, reference: str, answer: str) -> str:
    return (f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
            f"[시스템 답변]\n{answer}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def run_judges(workers: int) -> None:
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "product-results.json")
    out_path = ART / "judged-results.json"
    out = read_json(out_path, {
        "schema_version": "open-model-ceiling-judges-v1",
        "run_id": "run-001", "judge_model": JUDGE_MODEL, "results": {},
    })
    cases = {row["case_id"]: row for row in frozen["cases"]}
    keys = sorted(products["results"])
    random.Random(5501).shuffle(keys)
    buckets = [keys[i::workers] for i in range(workers)]

    def one_bucket(bucket: list[str], worker_no: int) -> int:
        os.environ["LLM_BACKEND"] = "anthropic"
        client = LLM(model=JUDGE_MODEL)
        count = 0
        for key in bucket:
            product = products["results"][key]
            with LOCK:
                if key in out["results"]:
                    continue
            if product["error"] or not product["output"]:
                row = {"case_id": product["case_id"], "arm_id": product["arm_id"],
                       "model": product["model"], "judge_model": JUDGE_MODEL,
                       "request": None, "output": None,
                       "provider_exchanges": [], "error": "product_call_failed"}
            else:
                case = cases[product["case_id"]]
                user = judge_user(case["question"], case["reference_answer"],
                                  product["output"]["answer"])
                result = call_with_retry(
                    client, kind=f"adr0055.judge.{product['case_id']}.{product['arm_id']}",
                    system=JUDGE_SYSTEM, user=user, schema=JUDGE_SCHEMA,
                    max_tokens=1800, effort="low")
                row = {
                    "case_id": product["case_id"], "arm_id": product["arm_id"],
                    "model": product["model"], "judge_model": JUDGE_MODEL,
                    "request": {"system": JUDGE_SYSTEM, "user": user,
                                "schema": JUDGE_SCHEMA, "max_tokens": 1800,
                                "effort": "low"},
                    "output": result["parsed"],
                    "provider_exchanges": result["attempts"], "error": result["error"],
                }
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
            count += 1
        print(f"judge worker {worker_no} complete: {count}", flush=True)
        return count

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, i) for i, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def exchange_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = [ex for row in rows for ex in row.get("provider_exchanges", [])]
    successful = [ex for ex in exchanges if not ex.get("error")]
    durations = [int(ex.get("dur_ms", 0)) for ex in successful]
    return {
        "calls": len(exchanges),
        "successful_calls": len(successful),
        "errors": sum(bool(ex.get("error")) for ex in exchanges),
        "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0))
                            for ex in exchanges),
        "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0))
                             for ex in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def render_questions(frozen: dict, products: dict, judged: dict) -> None:
    for number, case in enumerate(frozen["cases"], 1):
        lines = [
            f"# ADR-0055 질문 {number:03d}: {case['case_id']}", "",
            "## 실행 메타", "",
            "- run: `run-001`", "- phase: `probe/in_sample`",
            "- 비교 class: `offline_benchmark_candidate`", "- judge: `claude-opus-5`", "",
            "## 사용자 질문 원문", "", case["question"], "",
            "## 기준답변 — 채점 전용, 답변 모델 입력 비공개", "",
            case["reference_answer"], "",
            "## 동결 제품 입력", "", "### system", "", "```text",
            case["product_request"]["system"], "```", "", "### user", "",
            "```text", case["product_request"]["user"], "```", "",
            "### schema", "", "```json",
            json.dumps(case["product_request"]["schema"], ensure_ascii=False, indent=2),
            "```", "",
        ]
        for spec in MODELS:
            key = f"{case['case_id']}::{spec['arm_id']}"
            p = products["results"][key]
            j = judged["results"][key]
            lines.extend([
                f"## arm `{spec['arm_id']}` — `{spec['model']}`", "",
                "### 답변 provider 원기록", "", "```json",
                json.dumps(p, ensure_ascii=False, indent=2), "```", "",
                "### Opus 채점 원기록", "", "```json",
                json.dumps(j, ensure_ascii=False, indent=2), "```", "",
                "### 사례 판정", "",
                f"- correct: `{(j.get('output') or {}).get('correct')}`",
                f"- failure_type: `{(j.get('output') or {}).get('failure_type', 'call_error')}`",
                "",
            ])
        (EXP / f"질문-{number:03d}-{case['case_id']}.md").write_text(
            "\n".join(lines) + "\n", "utf-8")


def finalize() -> None:
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "product-results.json")
    judged = read_json(ART / "judged-results.json")
    by_arm: dict[str, Any] = {}
    for spec in MODELS:
        prows = [row for row in products["results"].values()
                 if row["arm_id"] == spec["arm_id"]]
        jrows = [row for row in judged["results"].values()
                 if row["arm_id"] == spec["arm_id"]]
        valid = [row for row in jrows if row.get("output") is not None]
        correct = sum(bool(row["output"].get("correct")) for row in valid)
        by_arm[spec["arm_id"]] = {
            "model": spec["model"], "provider": spec["provider"],
            "correct": correct, "total": len(frozen["cases"]),
            "judged": len(valid), "accuracy": round(correct / len(frozen["cases"]), 4),
            "product_errors": sum(bool(row.get("error")) for row in prows),
            "judge_errors": sum(bool(row.get("error")) for row in jrows),
            "product_usage": exchange_usage(prows),
            "judge_usage": exchange_usage(jrows),
            "failure_types": {},
        }
        for row in valid:
            ft = row["output"].get("failure_type", "other")
            by_arm[spec["arm_id"]]["failure_types"][ft] = (
                by_arm[spec["arm_id"]]["failure_types"].get(ft, 0) + 1)
    baseline = {row["case_id"]: bool((row.get("output") or {}).get("correct"))
                for row in judged["results"].values() if row["arm_id"] == "baseline"}
    comparisons = {}
    for spec in MODELS[1:]:
        rows = {row["case_id"]: bool((row.get("output") or {}).get("correct"))
                for row in judged["results"].values()
                if row["arm_id"] == spec["arm_id"]}
        counts = {"candidate_only": 0, "baseline_only_regression": 0,
                  "both_correct": 0, "both_wrong": 0}
        for case_id in baseline:
            b, c = baseline[case_id], rows[case_id]
            key = ("both_correct" if b and c else
                   "baseline_only_regression" if b else
                   "candidate_only" if c else "both_wrong")
            counts[key] += 1
        counts["delta"] = counts["candidate_only"] - counts["baseline_only_regression"]
        comparisons[spec["arm_id"]] = counts
    summary = {
        "schema_version": "open-model-ceiling-summary-v1",
        "run_id": "run-001", "definition": (
            "OPEN 모델 성능 = 정답 조문 전체만 포함한 동결 입력에서 Opus 5가 판정한 정답률"
        ),
        "cases": len(frozen["cases"]), "models": len(MODELS),
        "by_arm": by_arm, "comparisons_vs_qwen": comparisons,
        "judge_disagreements": None,
        "limitations": [
            "ADR-0048에서 반복 사용된 인샘플 hard8",
            "Opus 5 단일 judge이며 사람 확정 재감사 없음",
            "Opus 5 답변 arm은 동일 계열 judge의 self-preference 가능",
            "법령·기준답변 버전 재검증 없음",
        ],
    }
    write_json(ART / "summary.json", summary)
    render_questions(frozen, products, judged)
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
