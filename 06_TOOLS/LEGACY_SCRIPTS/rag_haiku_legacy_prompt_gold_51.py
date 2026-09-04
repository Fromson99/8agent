#!/usr/bin/env python3
"""ADR-0057: Haiku legacy product prompt replay on frozen gold-only 51 cases."""

from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from scripts import rag_open_model_ceiling_51 as parent  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0057-haiku-legacy-prompt-gold-51"
ART = ADR / "artifacts"
EXP = ADR / "실험"
PARENT_ADR = ROOT / "docs/adr/ADR-0056-cm-core-51-open-model-ceiling"
PARENT_ART = PARENT_ADR / "artifacts"
MODEL = "claude-haiku-4-5-20251001"
ARM = "legacy-prompt"
JUDGE_MODEL = parent.JUDGE_MODEL
LOCK = threading.Lock()

LEGACY_SYSTEM = (
    "너는 문서 질의응답 보조자다. [컨텍스트]는 구조화된 문서들에서 이번 질의로 회수된 "
    "구역들이다 — 이것**만** 근거로 한국어로 답한다.\n"
    "지켜야 할 규칙(위반은 곧 오답):\n"
    "① 수치·조항·명칭은 컨텍스트에 실제로 있을 때만 인용한다. 없으면 일반 지식으로 "
    "채우지 말고 '회수된 자료에는 없다'고만 밝힌다. '자료에 없다'고 말한 뒤 일반 수치를 "
    "이어 붙이지 마라(자기모순).\n"
    "② 컨텍스트가 부족해도 '문서에 없다'고 단정하지 마라 — 그것은 '이번 검색으로는 "
    "회수되지 않았다'는 뜻일 뿐이다.\n"
    "③ 회수된 구역은 검색 표본이지 전체가 아니다 — '총 N개뿐' 같은 전수 단정 금지.\n"
    "④ 출처 목록은 코드가 이번 최종 컨텍스트의 실제 좌표에서 확정한다. refs나 문서 좌표를 "
    "출력하지 말고, 답변 문장만 작성한다. 컨텍스트 밖의 문서·조항을 새로 만들어 인용하지 마라.\n"
    "⑤ 결론을 먼저 1~3문장으로, 그 뒤에 근거 설명. 컨텍스트에 답이 없으면 answerable 을 "
    "false 로 두고, 어떤 자료가 있으면 답할 수 있는지만 안내한다.\n"
    "⑥ [해석 맥락 — 지식 위키]가 있으면 그것은 축적된 해석 지식(법제처 해석례 요약 등)에서 "
    "온 **배경**이다 — 답의 방향(문턱이 좁은지, 준용이 어디까지 가는지)을 잡는 데 쓰되, "
    "refs 에는 넣지 말고 수치·조항 인용의 근거로도 쓰지 마라. 위키와 [컨텍스트]의 조문이 "
    "어긋나면 조문이 이긴다."
)


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


def prepare() -> None:
    source = parent.read_json(PARENT_ART / "frozen-cases.json")
    cases = []
    for row in source["cases"]:
        request = dict(row["product_request"])
        if "[해석 맥락 — 지식 위키]" in request["user"]:
            raise RuntimeError(f"unexpected wiki context: {row['case_id']}")
        request["system"] = LEGACY_SYSTEM
        # Prompt-only isolation: preserve ADR-0056 output cap, effort, schema, and user input.
        cases.append({**row, "product_request": request})
    frozen = {
        "schema_version": "haiku-legacy-prompt-gold-51-frozen-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": "ADR-0056 frozen cm-core 51건 전수; user/schema/evidence 고정; system만 legacy로 교체",
        "in_sample": True,
        "decision_eligible": False,
        "parent_frozen_source": str((PARENT_ART / "frozen-cases.json").relative_to(ROOT)),
        "parent_frozen_sha256": parent.sha(PARENT_ART / "frozen-cases.json"),
        "parent_summary_sha256": parent.sha(PARENT_ART / "summary.json"),
        "case_count": len(cases),
        "expected_article_instances": sum(len(row["gold_evidence"]) for row in cases),
        "model": MODEL,
        "judge": JUDGE_MODEL,
        "judge_repeats": 1,
        "provider_error_retry": 1,
        "answer_schedule": "4 deterministic case-index lanes",
        "judge_order": "seed 5701 deterministic shuffle; model identity blind",
        "isolated_change": {
            "field": "product_request.system",
            "current_system_sha256": parent.text_sha(source["cases"][0]["product_request"]["system"]),
            "legacy_system_sha256": parent.text_sha(LEGACY_SYSTEM),
            "wiki_context": False,
            "max_tokens": cases[0]["product_request"]["max_tokens"],
            "effort": cases[0]["product_request"]["effort"],
        },
        "cases": cases,
    }
    if len(cases) != 51 or frozen["expected_article_instances"] != 70:
        raise RuntimeError("parent suite size drift")
    parent.write_json(ART / "frozen-cases.json", frozen)
    parent.write_json(ART / "coverage-preflight.json", {
        "cases": 51,
        "expected_article_instances": 70,
        "wiki_context_cases": 0,
        "reference_answer_leaks": 0,
        "legacy_system_sha256": parent.text_sha(LEGACY_SYSTEM),
        "parent_frozen_sha256": frozen["parent_frozen_sha256"],
    })
    print(json.dumps({
        "frozen_cases_sha256": parent.sha(ART / "frozen-cases.json"),
        "coverage_sha256": parent.sha(ART / "coverage-preflight.json"),
        **frozen["isolated_change"],
    }, ensure_ascii=False, indent=2))


def run_answers(lanes: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = parent.read_json(ART / "frozen-cases.json")
    out_path = ART / "product-results.json"
    out = parent.read_json(out_path, {
        "schema_version": "haiku-legacy-prompt-gold-51-products-v1",
        "run_id": "run-001",
        "results": {},
    })
    clients = [LLM(model=MODEL) for _ in range(lanes)]

    def one_lane(lane: int) -> int:
        client = clients[lane]
        count = 0
        for idx in range(lane, len(frozen["cases"]), lanes):
            case = frozen["cases"][idx]
            key = case["case_id"]
            with LOCK:
                if key in out["results"]:
                    continue
            req = case["product_request"]
            result = parent.call_with_retry(
                client,
                kind=f"adr0057.{key}.{ARM}",
                system=req["system"],
                user=req["user"],
                schema=req["schema"],
                max_tokens=req["max_tokens"],
                effort=req["effort"],
            )
            row = {
                "case_id": key,
                "arm_id": ARM,
                "model": MODEL,
                "provider": "anthropic",
                "request_sha256": parent.text_sha(json.dumps(req, ensure_ascii=False, sort_keys=True)),
                "output": result["parsed"],
                "provider_exchanges": result["attempts"],
                "error": result["error"],
            }
            with LOCK:
                out["results"][key] = row
                parent.write_json(out_path, out)
            count += 1
            print(f"answer {len(out['results'])}/51: {key}", flush=True)
        return count

    with ThreadPoolExecutor(max_workers=lanes) as pool:
        futures = [pool.submit(one_lane, lane) for lane in range(lanes)]
        for future in as_completed(futures):
            future.result()
    print(f"answers complete: {len(out['results'])}/51", flush=True)


def run_judges(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = parent.read_json(ART / "frozen-cases.json")
    products = parent.read_json(ART / "product-results.json")
    cases = {row["case_id"]: row for row in frozen["cases"]}
    out_path = ART / "judged-results.json"
    out = parent.read_json(out_path, {
        "schema_version": "haiku-legacy-prompt-gold-51-judges-v1",
        "run_id": "run-001",
        "judge_model": JUDGE_MODEL,
        "results": {},
    })
    keys = sorted(products["results"])
    random.Random(5701).shuffle(keys)
    buckets = [keys[i::workers] for i in range(workers)]
    clients = [LLM(model=JUDGE_MODEL) for _ in range(workers)]

    def one_bucket(bucket: list[str], worker_no: int) -> int:
        client = clients[worker_no]
        count = 0
        for key in bucket:
            with LOCK:
                if key in out["results"]:
                    continue
            product = products["results"][key]
            if product["error"] or not product["output"]:
                row = {
                    "case_id": key,
                    "arm_id": ARM,
                    "model": MODEL,
                    "judge_model": JUDGE_MODEL,
                    "request": None,
                    "output": None,
                    "provider_exchanges": [],
                    "error": "product_call_failed",
                }
            else:
                case = cases[key]
                user = parent.judge_user(case["question"], case["reference_answer"], product["output"]["answer"])
                result = parent.call_with_retry(
                    client,
                    kind=f"adr0057.judge.{key}.{ARM}",
                    system=parent.JUDGE_SYSTEM,
                    user=user,
                    schema=parent.JUDGE_SCHEMA,
                    max_tokens=1800,
                    effort="low",
                )
                row = {
                    "case_id": key,
                    "arm_id": ARM,
                    "model": MODEL,
                    "judge_model": JUDGE_MODEL,
                    "request": {
                        "system": parent.JUDGE_SYSTEM,
                        "user": user,
                        "schema": parent.JUDGE_SCHEMA,
                        "max_tokens": 1800,
                        "effort": "low",
                    },
                    "output": result["parsed"],
                    "provider_exchanges": result["attempts"],
                    "error": result["error"],
                }
            with LOCK:
                out["results"][key] = row
                parent.write_json(out_path, out)
            count += 1
            print(f"judge {len(out['results'])}/51: {key}", flush=True)
        return count

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, i) for i, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()
    print(f"judges complete: {len(out['results'])}/51", flush=True)


def render_questions(frozen: dict, products: dict, judged: dict, parent_products: dict, parent_judged: dict) -> list[dict]:
    questions = []
    EXP.mkdir(parents=True, exist_ok=True)
    for number, case in enumerate(frozen["cases"], 1):
        case_id = case["case_id"]
        baseline_key = f"{case_id}::claude-haiku-4-5"
        lines = [
            f"# ADR-0057 질문 {number:03d}: {case_id}", "",
            "## 1. 실행 메타", "", "- run: `run-001`", "- phase: `probe/in_sample`",
            "- candidate: product `claude-haiku-4-5-20251001`", "- judge: offline `claude-opus-5`",
            "- baseline: ADR-0056 `claude-haiku-4-5` 저장 결과", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", case["reference_answer"], "",
            "## 4. 제품 입력을 구성한 원값", "", "### candidate system", "", "```text",
            case["product_request"]["system"], "```", "", "### user", "", "```text",
            case["product_request"]["user"], "```", "", "### schema", "", "```json",
            json.dumps(case["product_request"]["schema"], ensure_ascii=False, indent=2), "```", "",
            "## 5. 제품 모델 호출 — run·arm별 실제 원문", "", "### baseline — ADR-0056 저장 호출", "", "```json",
            json.dumps(parent_products["results"][baseline_key], ensure_ascii=False, indent=2), "```", "",
            "### legacy-prompt — ADR-0057 실제 호출", "", "```json",
            json.dumps(products["results"][case_id], ensure_ascii=False, indent=2), "```", "",
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "", "없음. frozen gold article 전문을 Haiku에 직접 제공했다.", "",
            "## 7. 채점 호출과 반복 판정", "", "### baseline — ADR-0056 저장 Opus 5 판정", "", "```json",
            json.dumps(parent_judged["results"][baseline_key], ensure_ascii=False, indent=2), "```", "",
            "### legacy-prompt — ADR-0057 실제 Opus 5 판정", "", "```json",
            json.dumps(judged["results"][case_id], ensure_ascii=False, indent=2), "```", "",
            "## 8. 사례 최종 판정", "", "| arm | correct | failure_type |", "|---|---:|---|",
            f"| `baseline` | `{(parent_judged['results'][baseline_key].get('output') or {}).get('correct')}` | `{(parent_judged['results'][baseline_key].get('output') or {}).get('failure_type', 'call_error')}` |",
            f"| `legacy-prompt` | `{(judged['results'][case_id].get('output') or {}).get('correct')}` | `{(judged['results'][case_id].get('output') or {}).get('failure_type', 'call_error')}` |",
            "",
        ]
        path = EXP / f"질문-{number:03d}-{case_id}.md"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        questions.append({"number": number, "case_id": case_id, "file": path.name, "sha256": parent.sha(path)})
    return questions


def finalize() -> None:
    frozen = parent.read_json(ART / "frozen-cases.json")
    products = parent.read_json(ART / "product-results.json")
    judged = parent.read_json(ART / "judged-results.json")
    parent_products = parent.read_json(PARENT_ART / "product-results.json")
    parent_judged = parent.read_json(PARENT_ART / "judged-results.json")
    if len(products["results"]) != 51 or len(judged["results"]) != 51:
        raise RuntimeError("cannot finalize before 51 product and judge rows")

    baseline = {}
    candidate = {}
    for case in frozen["cases"]:
        case_id = case["case_id"]
        baseline[case_id] = bool((parent_judged["results"][f"{case_id}::claude-haiku-4-5"].get("output") or {}).get("correct"))
        candidate[case_id] = bool((judged["results"][case_id].get("output") or {}).get("correct"))
    paired = {"candidate_only": 0, "baseline_only_regression": 0, "both_correct": 0, "both_wrong": 0}
    for case_id in baseline:
        b, c = baseline[case_id], candidate[case_id]
        key = "both_correct" if b and c else "baseline_only_regression" if b else "candidate_only" if c else "both_wrong"
        paired[key] += 1
    paired["delta"] = paired["candidate_only"] - paired["baseline_only_regression"]

    candidate_rows = list(products["results"].values())
    judge_rows = list(judged["results"].values())
    failure_types: dict[str, int] = {}
    for row in judge_rows:
        ft = (row.get("output") or {}).get("failure_type", "call_error")
        failure_types[ft] = failure_types.get(ft, 0) + 1
    summary = {
        "schema_version": "haiku-legacy-prompt-gold-51-summary-v1",
        "run_id": "run-001",
        "primary_metric": "Opus 5 single blind judge correct / 51",
        "isolated_change": frozen["isolated_change"],
        "baseline": {
            "source": "ADR-0056-experiment-v1/claude-haiku-4-5",
            "correct": sum(baseline.values()),
            "total": 51,
            "accuracy": round(sum(baseline.values()) / 51, 4),
            "wrong_cases": [case_id for case_id, value in baseline.items() if not value],
        },
        "legacy_prompt": {
            "correct": sum(candidate.values()),
            "total": 51,
            "accuracy": round(sum(candidate.values()) / 51, 4),
            "wrong_cases": [case_id for case_id, value in candidate.items() if not value],
            "product_errors": sum(bool(row.get("error")) for row in candidate_rows),
            "judge_errors": sum(bool(row.get("error")) for row in judge_rows),
            "product_usage": exchange_usage(candidate_rows),
            "judge_usage": exchange_usage(judge_rows),
            "failure_types": failure_types,
        },
        "paired": paired,
        "hypothesis": {
            "material_drop_threshold": "legacy-prompt <= 40/51",
            "supported": sum(candidate.values()) <= 40,
        },
        "limitations": [
            "반복 사용된 in-sample cm-core-51이며 운영 채택 근거가 아니다.",
            "Opus 5 단일 judge이고 사람 확정 재감사가 없다.",
            "과거 gold_only의 Wiki-on 및 max_tokens=4000/effort=high는 재현하지 않고 system prompt만 격리했다.",
            "baseline은 ADR-0056 저장 결과를 재사용하여 생성 시점 변동성을 통제하지 못한다.",
        ],
    }
    parent.write_json(ART / "summary.json", summary)
    questions = render_questions(frozen, products, judged, parent_products, parent_judged)
    manifest_path = EXP / "manifest.json"
    manifest = parent.read_json(manifest_path)
    manifest["runs"][0].update({"status": "complete", "artifact_path": str((ART / "summary.json").relative_to(ROOT)), "sha256": parent.sha(ART / "summary.json")})
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            "baseline": summary["baseline"],
            "legacy-prompt": summary["legacy_prompt"],
        },
        "comparisons": [{"baseline_arm": "baseline", "candidate_arm": ARM, **paired}],
        "judge_disagreements": None,
        "usage": {"product": summary["legacy_prompt"]["product_usage"], "judge": summary["legacy_prompt"]["judge_usage"]},
        "latency": {"legacy-prompt": summary["legacy_prompt"]["product_usage"]},
        "error_taxonomy": sorted(failure_types),
    }
    manifest["questions"] = questions
    parent.write_json(manifest_path, manifest)

    index = ["# ADR-0057 실험 기록", "", "- run: `run-001`", "- candidate: legacy system prompt × Haiku × 51건", "- baseline: ADR-0056 저장 Haiku 결과", ""]
    index.extend(f"- [{row['case_id']}]({row['file']}) — `{row['sha256']}`" for row in questions)
    (EXP / "README.md").write_text("\n".join(index) + "\n", "utf-8")

    artifact_files = [
        ("coverage-preflight.json", "51건·70조문과 prompt-only 격리 사전검사", False),
        ("frozen-cases.json", "동결된 legacy prompt 제품 입력과 evaluator-only 기준답변", True),
        ("product-results.json", "Haiku 51개 답변 호출 원기록", True),
        ("judged-results.json", "Opus 5 blind judge 51개 원기록", True),
        ("summary.json", "paired 성능·사용량·오류 집계", False),
    ]
    parent.write_json(ART / "manifest.json", {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0057",
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
    parser.add_argument("command", choices=["prepare", "answers", "judge", "finalize"])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--lanes", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "answers":
        run_answers(args.lanes)
    elif args.command == "judge":
        run_judges(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
