#!/usr/bin/env python3
"""ADR-0059: 고정 prompt에서 비골든 조문이 Haiku 판단을 뒤집는 경로를 측정한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from lawrag.core.rag import answer, index as index_mod  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402
from scripts.rag_open_model_ceiling import JUDGE_SCHEMA, JUDGE_SYSTEM  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0059-extra-article-interference-50"
ART = ADR / "artifacts"
SOURCE_GOLD = (ROOT / "docs/adr/ADR-0056-cm-core-51-open-model-ceiling"
               / "artifacts/frozen-cases.json")
SOURCE_RETRIEVAL = ROOT / "var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json"
VARIANT = "control_d_then_verifier"
PRODUCT_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-opus-5"
FROZEN_SHA256 = "0290f150a26bb5d6b03c0f2e09dff8377ed048c040c48ac54f34e44bf53bce53"
EXCLUDED = {"cm-030"}
ORIGINS = ("exact-structural", "keyword-bm25", "assertion-tree",
           "supplemental-closure")
ARMS = (
    "gold-only",
    "gold-plus-exact-structural",
    "gold-plus-keyword-bm25",
    "gold-plus-assertion-tree",
    "gold-plus-supplemental-closure",
    "gold-plus-all-tail",
    "retrieval-order",
)
LOCK = threading.Lock()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def compact(value: str) -> str:
    return "".join(str(value or "").split())


def item_is_gold(item: dict, expected: list[dict]) -> bool:
    """기존 69/70 회수율과 같은 법령명+path 조문 좌표로 판정한다."""
    segments = str(item.get("path") or "").split(" ▸ ")
    for row in expected:
        article = str(row.get("article") or "")
        if compact(item.get("doc")) != compact(row.get("law")):
            continue
        if any(segment == article or segment.startswith(article + " ")
               for segment in segments):
            return True
    return False


def gold_items(case: dict) -> list[dict]:
    return [{
        "item_id": f"G{position}",
        "class": "gold",
        "origin": "expected-article",
        "doc_id": row.get("doc_id"),
        "node": row.get("node"),
        "doc": row.get("law"),
        "path": row.get("path"),
        "text": row.get("text"),
        "chars": len(str(row.get("text") or "")),
        "sha256": hashlib.sha256(str(row.get("text") or "").encode()).hexdigest(),
    } for position, row in enumerate(case["gold_evidence"], 1)]


def extra_items(index, selected: list[dict], expected: list[dict]) -> list[dict]:
    extras = [row for row in selected if not item_is_gold(row, expected)]
    evidence = reconstruct_evidence(index, extras)
    if len(evidence) != len(extras):
        raise RuntimeError(f"extra reconstruction mismatch: {len(extras)} != {len(evidence)}")
    out = []
    for position, (source, body) in enumerate(zip(extras, evidence), 1):
        text = str(body.get("original_text") or "")
        out.append({
            "item_id": f"X{position:02d}",
            "class": "extra",
            "origin": source.get("origin"),
            "retrieval_position": selected.index(source) + 1,
            "doc_id": source.get("doc_id"),
            "node": source.get("node"),
            "doc": source.get("doc"),
            "path": source.get("path"),
            "text": text,
            "chars": len(text),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        })
    return out


def render_user(question: str, items: list[dict]) -> str:
    blocks = []
    for position, row in enumerate(items, 1):
        blocks.append(f"[{position}] {row['doc']} ▸ {row['path']}\n{row['text']}")
    return f"[질문]\n{question}\n\n[컨텍스트]\n" + "\n\n".join(blocks)


def request(question: str, items: list[dict]) -> dict:
    user = render_user(question, items)
    return {
        "system": answer.ANSWER_SYSTEM,
        "user": user,
        "schema": answer.ANSWER_SCHEMA,
        "max_tokens": 4000,
        "effort": "high",
        "temperature": "anthropic_provider_default",
        "item_ids": [row["item_id"] for row in items],
        "request_sha256": hashlib.sha256(
            json.dumps({"system": answer.ANSWER_SYSTEM, "user": user,
                        "schema": answer.ANSWER_SCHEMA, "max_tokens": 4000,
                        "effort": "high"}, ensure_ascii=False,
                       sort_keys=True).encode()).hexdigest(),
    }


def prepare() -> None:
    gold_source = read_json(SOURCE_GOLD)
    retrieval_source = read_json(SOURCE_RETRIEVAL)
    retrieval = {row["case_no"]: row for row in retrieval_source["rows"]}
    index = index_mod.current().scoped(None)
    cases = []
    origin_counts = Counter()
    for case in gold_source["cases"]:
        case_id = case["case_id"]
        if case_id in EXCLUDED:
            continue
        selected = retrieval[case_id]["variants"][VARIANT]["selected"]
        gold = gold_items(case)
        extras = extra_items(index, selected, case["expected_articles"])
        origin_counts.update(row["origin"] for row in extras)
        by_origin = {origin: [row for row in extras if row["origin"] == origin]
                     for origin in ORIGINS}
        unknown = sorted(set(row["origin"] for row in extras) - set(ORIGINS))
        if unknown:
            raise RuntimeError(f"unregistered extra origins in {case_id}: {unknown}")

        # 골든을 앞에 고정해 content/load 효과를 보고, retrieval-order는 위치 효과를 본다.
        arm_items = {
            "gold-only": gold,
            **{f"gold-plus-{origin}": gold + by_origin[origin]
               for origin in ORIGINS},
            "gold-plus-all-tail": gold + extras,
        }
        retrieval_order = []
        unused_gold = list(gold)
        extra_by_position = {row["retrieval_position"]: row for row in extras}
        for position, source in enumerate(selected, 1):
            if position in extra_by_position:
                retrieval_order.append(extra_by_position[position])
            elif unused_gold:
                retrieval_order.append(unused_gold.pop(0))
        retrieval_order.extend(unused_gold)  # cm-031처럼 검색이 gold를 놓친 경우만 후단 보충
        arm_items["retrieval-order"] = retrieval_order
        if set(arm_items) != set(ARMS):
            raise RuntimeError(f"arm mismatch in {case_id}")
        requests = {arm: request(case["question"], arm_items[arm]) for arm in ARMS}
        if any("[기준답변]" in req["system"] or "[기준답변]" in req["user"]
               for req in requests.values()):
            raise RuntimeError(f"reference leak in {case_id}")
        cases.append({
            "case_id": case_id,
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "reference_answer_visibility": "offline_evaluator_only",
            "expected_articles": case["expected_articles"],
            "gold_items": gold,
            "extra_items": extras,
            "retrieval_selected_count": len(selected),
            "retrieval_gold_count": len(selected) - len(extras),
            "requests": requests,
        })
    frozen = {
        "schema_version": "extra-article-interference-frozen-v1",
        "selection_rule": "ADR-0056 cm-core 51 전수에서 사용자 지정 cm-030만 제외",
        "case_count": len(cases),
        "excluded_cases": sorted(EXCLUDED),
        "in_sample": True,
        "decision_eligible": False,
        "product_model": PRODUCT_MODEL,
        "judge_model": JUDGE_MODEL,
        "product_prompt_source": "lawrag.core.rag.answer.ANSWER_SYSTEM",
        "wiki_context": "off; 모든 arm에 미제공",
        "source_gold": str(SOURCE_GOLD.relative_to(ROOT)),
        "source_gold_sha256": sha(SOURCE_GOLD),
        "source_retrieval": str(SOURCE_RETRIEVAL.relative_to(ROOT)),
        "source_retrieval_sha256": sha(SOURCE_RETRIEVAL),
        "retrieval_variant": VARIANT,
        "arms": list(ARMS),
        "origins": list(ORIGINS),
        "origin_counts": dict(origin_counts),
        "product_repeats": 1,
        "judge_rule": "first vote all; any arm differs from gold-only => all 7 arms get votes 2,3",
        "provider_error_retry": 1,
        "cases": cases,
    }
    write_json(ART / "frozen-cases.json", frozen)
    print(json.dumps({
        "frozen_cases_sha256": sha(ART / "frozen-cases.json"),
        "case_count": len(cases),
        "gold_presentations": sum(len(row["gold_items"]) for row in cases),
        "extra_presentations": sum(len(row["extra_items"]) for row in cases),
        "origin_counts": dict(origin_counts),
    }, ensure_ascii=False, indent=2))


def call_with_retry(client: LLM, *, kind: str, system: str, user: str,
                    schema: dict, max_tokens: int, effort: str | None) -> dict:
    parsed = None
    exchanges = []
    for _ in range(2):
        before = len(client.log)
        parsed = client.structured(kind=kind, system=system, user=user, schema=schema,
                                   max_tokens=max_tokens, effort=effort)
        exchanges.extend(row.dump() for row in client.log[before:])
        if parsed is not None:
            break
    return {"parsed": parsed, "provider_exchanges": exchanges,
            "error": None if parsed is not None else
            (exchanges[-1].get("error") if exchanges else "no_exchange")}


def run_products(workers: int) -> None:
    if sha(ART / "frozen-cases.json") != FROZEN_SHA256:
        raise RuntimeError("frozen-cases hash drift")
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = read_json(ART / "frozen-cases.json")
    out_path = ART / "stage1-products.json"
    out = read_json(out_path, {"schema_version": "stage1-products-v1", "results": {}})
    tasks = [(case, arm) for case in frozen["cases"] for arm in ARMS]
    random.Random(5901).shuffle(tasks)
    buckets = [tasks[i::workers] for i in range(workers)]

    def bucket(rows: list[tuple[dict, str]], worker: int) -> int:
        client = LLM(model=PRODUCT_MODEL)
        done = 0
        for case, arm in rows:
            key = f"{case['case_id']}::{arm}"
            with LOCK:
                if key in out["results"]:
                    continue
            req = case["requests"][arm]
            result = call_with_retry(
                client, kind=f"adr0059.stage1.{case['case_id']}.{arm}",
                system=req["system"], user=req["user"], schema=req["schema"],
                max_tokens=req["max_tokens"], effort=req["effort"])
            row = {"case_id": case["case_id"], "arm_id": arm,
                   "model": PRODUCT_MODEL, "request": req,
                   "output": result["parsed"],
                   "provider_exchanges": result["provider_exchanges"],
                   "error": result["error"]}
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
            done += 1
        print(f"product worker {worker}: {done}", flush=True)
        return done

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(bucket, rows, i) for i, rows in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()


def judge_user(case: dict, product: dict) -> str:
    return (f"[질문]\n{case['question']}\n\n[기준답변]\n{case['reference_answer']}\n\n"
            f"[시스템 답변]\n{product['output']['answer']}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def run_judges(workers: int) -> None:
    if sha(ART / "frozen-cases.json") != FROZEN_SHA256:
        raise RuntimeError("frozen-cases hash drift")
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "stage1-products.json")
    cases = {row["case_id"]: row for row in frozen["cases"]}
    out_path = ART / "stage1-judges.json"
    out = read_json(out_path, {"schema_version": "stage1-judges-v1", "results": {}})

    def run_tasks(tasks: list[tuple[str, int]], seed: int) -> None:
        random.Random(seed).shuffle(tasks)
        buckets = [tasks[i::workers] for i in range(workers)]

        def bucket(rows: list[tuple[str, int]], worker: int) -> int:
            client = LLM(model=JUDGE_MODEL)
            done = 0
            for product_key, vote in rows:
                key = f"{product_key}::v{vote}"
                with LOCK:
                    if key in out["results"]:
                        continue
                product = products["results"][product_key]
                if product.get("error") or not product.get("output"):
                    row = {"case_id": product["case_id"], "arm_id": product["arm_id"],
                           "vote": vote, "output": None, "provider_exchanges": [],
                           "error": "product_call_failed"}
                else:
                    case = cases[product["case_id"]]
                    user = judge_user(case, product)
                    result = call_with_retry(
                        client, kind=f"adr0059.judge.{product['case_id']}.{product['arm_id']}.v{vote}",
                        system=JUDGE_SYSTEM, user=user, schema=JUDGE_SCHEMA,
                        max_tokens=1800, effort="low")
                    row = {"case_id": product["case_id"], "arm_id": product["arm_id"],
                           "vote": vote, "judge_model": JUDGE_MODEL,
                           "request": {"system": JUDGE_SYSTEM, "user": user,
                                       "schema": JUDGE_SCHEMA, "max_tokens": 1800,
                                       "effort": "low"},
                           "output": result["parsed"],
                           "provider_exchanges": result["provider_exchanges"],
                           "error": result["error"]}
                with LOCK:
                    out["results"][key] = row
                    write_json(out_path, out)
                done += 1
            print(f"judge worker {worker}: {done}", flush=True)
            return done

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(bucket, rows, i) for i, rows in enumerate(buckets)]
            for future in as_completed(futures):
                future.result()

    first = [(key, 1) for key in sorted(products["results"])]
    run_tasks(first, 5902)
    discordant = []
    for case_id in cases:
        baseline = (out["results"].get(f"{case_id}::gold-only::v1", {}).get("output") or {}).get("correct")
        values = [(out["results"].get(f"{case_id}::{arm}::v1", {}).get("output") or {}).get("correct")
                  for arm in ARMS]
        if baseline is not None and any(value is not None and value != baseline for value in values):
            discordant.append(case_id)
    repeats = [(f"{case_id}::{arm}", vote) for case_id in discordant
               for arm in ARMS for vote in (2, 3)]
    run_tasks(repeats, 5903)


def majority(judges: dict, case_id: str, arm: str) -> bool | None:
    votes = []
    for vote in (1, 2, 3):
        row = judges["results"].get(f"{case_id}::{arm}::v{vote}")
        value = ((row or {}).get("output") or {}).get("correct")
        if value is not None:
            votes.append(bool(value))
    if not votes:
        return None
    return sum(votes) >= (len(votes) // 2 + 1)


def usage(rows: list[dict]) -> dict:
    exchanges = [exchange for row in rows for exchange in row.get("provider_exchanges", [])]
    durations = [int(exchange.get("dur_ms") or 0) for exchange in exchanges
                 if not exchange.get("error")]
    return {
        "calls": len(exchanges),
        "errors": sum(bool(exchange.get("error")) for exchange in exchanges),
        "input_tokens": sum(int((exchange.get("usage") or {}).get("input_tokens") or 0)
                            for exchange in exchanges),
        "output_tokens": sum(int((exchange.get("usage") or {}).get("output_tokens") or 0)
                             for exchange in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": sorted(durations)[min(len(durations) - 1,
                                        round((len(durations) - 1) * .95))]
        if durations else None,
    }


def analyze() -> None:
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "stage1-products.json")
    judges = read_json(ART / "stage1-judges.json")
    rows = []
    for case in frozen["cases"]:
        values = {arm: majority(judges, case["case_id"], arm) for arm in ARMS}
        rows.append({
            "case_id": case["case_id"],
            "correct": values,
            "content_regression": values["gold-only"] is True and
                                  values["gold-plus-all-tail"] is False,
            "content_rescue": values["gold-only"] is False and
                              values["gold-plus-all-tail"] is True,
            "order_regression": values["gold-plus-all-tail"] is True and
                                values["retrieval-order"] is False,
            "extra_count": len(case["extra_items"]),
            "origin_counts": dict(Counter(row["origin"] for row in case["extra_items"])),
        })
    by_arm = {}
    for arm in ARMS:
        valid = [row["correct"][arm] for row in rows if row["correct"][arm] is not None]
        base_only = sum(row["correct"]["gold-only"] is True and row["correct"][arm] is False
                        for row in rows)
        arm_only = sum(row["correct"]["gold-only"] is False and row["correct"][arm] is True
                       for row in rows)
        by_arm[arm] = {"correct": sum(valid), "total": len(valid),
                       "accuracy": round(sum(valid) / len(valid), 4) if valid else None,
                       "delta_vs_gold_only": arm_only - base_only,
                       "gold_only_only_correct": base_only,
                       "arm_only_correct": arm_only}
    summary = {
        "schema_version": "extra-article-interference-stage1-summary-v1",
        "by_arm": by_arm,
        "content_regressions": [row["case_id"] for row in rows if row["content_regression"]],
        "content_rescues": [row["case_id"] for row in rows if row["content_rescue"]],
        "order_regressions": [row["case_id"] for row in rows if row["order_regression"]],
        "rows": rows,
        "usage": {
            "product": usage(list(products["results"].values())),
            "judge": usage(list(judges["results"].values())),
        },
    }
    write_json(ART / "stage1-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def prepare_stage2() -> None:
    if sha(ART / "frozen-cases.json") != FROZEN_SHA256:
        raise RuntimeError("frozen-cases hash drift")
    frozen = read_json(ART / "frozen-cases.json")
    stage1 = read_json(ART / "stage1-summary.json")
    cases = {row["case_id"]: row for row in frozen["cases"]}
    stage1_rows = {row["case_id"]: row for row in stage1["rows"]}
    tasks = []
    selection = []
    for case_id in stage1["content_regressions"]:
        case = cases[case_id]
        row = stage1_rows[case_id]
        harmful_origins = [origin for origin in ORIGINS
                           if row["correct"].get(f"gold-plus-{origin}") is False]
        candidates = [extra for extra in case["extra_items"]
                      if not harmful_origins or extra["origin"] in harmful_origins]
        selection.append({"case_id": case_id, "harmful_origins": harmful_origins,
                          "candidate_item_ids": [extra["item_id"] for extra in candidates]})
        for extra in candidates:
            variants = {
                "gold-plus-single-extra": case["gold_items"] + [extra],
                "gold-plus-all-minus-single-extra": case["gold_items"] + [
                    row for row in case["extra_items"] if row["item_id"] != extra["item_id"]],
            }
            for arm, items in variants.items():
                tasks.append({
                    "task_id": f"{case_id}::{extra['item_id']}::{arm}",
                    "case_id": case_id,
                    "candidate": extra,
                    "arm_id": arm,
                    "request": request(case["question"], items),
                })
    out = {
        "schema_version": "extra-article-interference-stage2-frozen-v1",
        "selection_rule": ("run-001 majority gold-only=true/all-tail=false; "
                           "회귀 origin arm이 있으면 그 origin extra, 없으면 all extra"),
        "stage1_summary_sha256": sha(ART / "stage1-summary.json"),
        "selection": selection,
        "task_count": len(tasks),
        "tasks": tasks,
    }
    write_json(ART / "stage2-frozen.json", out)
    print(json.dumps({"sha256": sha(ART / "stage2-frozen.json"),
                      "task_count": len(tasks), "selection": selection},
                     ensure_ascii=False, indent=2))


def run_stage2_products(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    stage2 = read_json(ART / "stage2-frozen.json")
    out_path = ART / "stage2-products.json"
    out = read_json(out_path, {"schema_version": "stage2-products-v1", "results": {}})
    tasks = list(stage2["tasks"])
    random.Random(5921).shuffle(tasks)
    buckets = [tasks[i::workers] for i in range(workers)]

    def bucket(rows: list[dict], worker: int) -> int:
        client = LLM(model=PRODUCT_MODEL)
        done = 0
        for task in rows:
            key = task["task_id"]
            with LOCK:
                if key in out["results"]:
                    continue
            req = task["request"]
            result = call_with_retry(
                client, kind=f"adr0059.stage2.{task['case_id']}.{task['candidate']['item_id']}.{task['arm_id']}",
                system=req["system"], user=req["user"], schema=req["schema"],
                max_tokens=req["max_tokens"], effort=req["effort"])
            row = {**task, "model": PRODUCT_MODEL, "output": result["parsed"],
                   "provider_exchanges": result["provider_exchanges"],
                   "error": result["error"]}
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
            done += 1
        print(f"stage2 product worker {worker}: {done}", flush=True)
        return done

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(bucket, rows, i) for i, rows in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()


def run_stage2_judges(workers: int) -> None:
    load_env()
    os.environ["LLM_BACKEND"] = "anthropic"
    frozen = read_json(ART / "frozen-cases.json")
    cases = {row["case_id"]: row for row in frozen["cases"]}
    products = read_json(ART / "stage2-products.json")
    out_path = ART / "stage2-judges.json"
    out = read_json(out_path, {"schema_version": "stage2-judges-v1", "results": {}})

    def run_tasks(tasks: list[tuple[str, int]], seed: int) -> None:
        random.Random(seed).shuffle(tasks)
        buckets = [tasks[i::workers] for i in range(workers)]

        def bucket(rows: list[tuple[str, int]], worker: int) -> int:
            client = LLM(model=JUDGE_MODEL)
            done = 0
            for product_key, vote in rows:
                key = f"{product_key}::v{vote}"
                with LOCK:
                    if key in out["results"]:
                        continue
                product = products["results"][product_key]
                if product.get("error") or not product.get("output"):
                    row = {"task_id": product_key, "vote": vote, "output": None,
                           "provider_exchanges": [], "error": "product_call_failed"}
                else:
                    case = cases[product["case_id"]]
                    user = judge_user(case, product)
                    result = call_with_retry(
                        client, kind=f"adr0059.stage2.judge.{product['case_id']}.{product['candidate']['item_id']}.{product['arm_id']}.v{vote}",
                        system=JUDGE_SYSTEM, user=user, schema=JUDGE_SCHEMA,
                        max_tokens=1800, effort="low")
                    row = {"task_id": product_key, "case_id": product["case_id"],
                           "candidate_item_id": product["candidate"]["item_id"],
                           "arm_id": product["arm_id"], "vote": vote,
                           "judge_model": JUDGE_MODEL,
                           "request": {"system": JUDGE_SYSTEM, "user": user,
                                       "schema": JUDGE_SCHEMA, "max_tokens": 1800,
                                       "effort": "low"},
                           "output": result["parsed"],
                           "provider_exchanges": result["provider_exchanges"],
                           "error": result["error"]}
                with LOCK:
                    out["results"][key] = row
                    write_json(out_path, out)
                done += 1
            print(f"stage2 judge worker {worker}: {done}", flush=True)
            return done

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(bucket, rows, i) for i, rows in enumerate(buckets)]
            for future in as_completed(futures):
                future.result()

    first = [(key, 1) for key in sorted(products["results"])]
    run_tasks(first, 5922)
    pairs = {}
    for key, product in products["results"].items():
        pair = (product["case_id"], product["candidate"]["item_id"])
        pairs.setdefault(pair, []).append(key)
    discordant = []
    for pair, keys in pairs.items():
        votes = [((out["results"].get(f"{key}::v1") or {}).get("output") or {}).get("correct")
                 for key in keys]
        if len(votes) == 2 and None not in votes and votes[0] != votes[1]:
            discordant.extend(keys)
    repeats = [(key, vote) for key in discordant for vote in (2, 3)]
    run_tasks(repeats, 5923)


def stage2_majority(judges: dict, task_id: str) -> bool | None:
    values = []
    for vote in (1, 2, 3):
        row = judges["results"].get(f"{task_id}::v{vote}")
        value = ((row or {}).get("output") or {}).get("correct")
        if value is not None:
            values.append(bool(value))
    return (sum(values) >= len(values) // 2 + 1) if values else None


def analyze_stage2() -> None:
    frozen = read_json(ART / "stage2-frozen.json")
    products = read_json(ART / "stage2-products.json")
    judges = read_json(ART / "stage2-judges.json")
    grouped = {}
    for task in frozen["tasks"]:
        key = (task["case_id"], task["candidate"]["item_id"])
        row = grouped.setdefault(key, {"case_id": task["case_id"],
                                      "candidate": task["candidate"], "correct": {}})
        row["correct"][task["arm_id"]] = stage2_majority(judges, task["task_id"])
        product = products["results"][task["task_id"]]
        row.setdefault("answers", {})[task["arm_id"]] = (product.get("output") or {}).get("answer")
    rows = []
    for row in grouped.values():
        single = row["correct"].get("gold-plus-single-extra")
        minus = row["correct"].get("gold-plus-all-minus-single-extra")
        row["sufficient_harm"] = single is False
        row["necessary_harm"] = minus is True
        rows.append(row)
    cases = {}
    for row in rows:
        case = cases.setdefault(row["case_id"], {"case_id": row["case_id"],
                                                "candidate_count": 0,
                                                "sufficient": [], "necessary": []})
        case["candidate_count"] += 1
        if row["sufficient_harm"]:
            case["sufficient"].append(row["candidate"]["item_id"])
        if row["necessary_harm"]:
            case["necessary"].append(row["candidate"]["item_id"])
    attributed = [row for row in cases.values() if row["sufficient"] or row["necessary"]]
    summary = {
        "schema_version": "extra-article-interference-stage2-summary-v1",
        "case_count": len(cases),
        "candidate_count": len(rows),
        "attributed_cases": len(attributed),
        "attribution_coverage": round(len(attributed) / len(cases), 4) if cases else None,
        "sufficient_article_count": sum(row["sufficient_harm"] for row in rows),
        "necessary_article_count": sum(row["necessary_harm"] for row in rows),
        "cases": list(cases.values()),
        "rows": rows,
        "usage": {"product": usage(list(products["results"].values())),
                  "judge": usage(list(judges["results"].values()))},
    }
    write_json(ART / "stage2-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "products", "judges", "analyze",
                                            "prepare-stage2", "stage2-products",
                                            "stage2-judges", "stage2-analyze"))
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    {"prepare": prepare, "products": lambda: run_products(args.workers),
     "judges": lambda: run_judges(args.workers), "analyze": analyze,
     "prepare-stage2": prepare_stage2,
     "stage2-products": lambda: run_stage2_products(args.workers),
     "stage2-judges": lambda: run_stage2_judges(args.workers),
     "stage2-analyze": analyze_stage2}[args.command]()


if __name__ == "__main__":
    main()
