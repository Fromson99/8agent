#!/usr/bin/env python3
"""Run the frozen FSC hard holdout through current LegalClosure at cap 20."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
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
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core import llm as llm_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legalclosure_runtime  # noqa: E402


MODEL = "claude-haiku-4-5-20251001"
ARTICLE_LEAK = re.compile(r"제\s*\d+\s*조")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _corpus_article_roots(index) -> int:
    total = 0
    for view in index.docs.values():
        for node_id, node in view.by_id.items():
            if node.get("family") != "kr_article":
                continue
            if "부칙" in (view.path(node_id) or ""):
                continue
            total += 1
    return total


def _validate_suite(suite_path: Path, suite: dict, expected_sha: str, index) -> None:
    actual_sha = _sha256(suite_path)
    if actual_sha != expected_sha:
        raise ValueError(f"suite SHA mismatch: expected {expected_sha}, got {actual_sha}")
    cases = list(suite.get("cases") or [])
    if len(cases) != 10:
        raise ValueError(f"expected 10 cases, got {len(cases)}")
    gold_count = sum(len(case.get("expected_articles") or []) for case in cases)
    if gold_count != 15:
        raise ValueError(f"expected 15 gold article instances, got {gold_count}")
    for case in cases:
        question = str(case.get("question") or "")
        if ARTICLE_LEAK.search(question):
            raise ValueError(f"article number leaked in question: {case['id']}")
        source = ROOT / str(case["source_file"])
        if not source.is_file() or _sha256(source) != case["source_sha256"]:
            raise ValueError(f"source provenance mismatch: {case['id']}")
        for gold in case.get("expected_articles") or []:
            doc_id = str(gold["doc_id"])
            node_id = int(gold["node"])
            view = index.docs.get(doc_id)
            if view is None or node_id not in view.by_id:
                raise ValueError(f"gold coordinate missing: {case['id']} {doc_id}:{node_id}")
            node = view.by_id[node_id]
            if node.get("family") != "kr_article" or "부칙" in (view.path(node_id) or ""):
                raise ValueError(f"gold is not a current article root: {case['id']} {doc_id}:{node_id}")


def _question_markdown(case: dict, row: dict) -> str:
    calls = json.dumps(row["llm_calls"], ensure_ascii=False, indent=2)
    raw = json.dumps({
        "suite": "data/review/fsc_hard_retrieval_v1.json",
        "source_file": case["source_file"],
        "source_sha256": case["source_sha256"],
        "expected_articles": case["expected_articles"],
        "retrieval_cap": 20,
        "shortcut_enabled": False,
    }, ensure_ascii=False, indent=2)
    selected = json.dumps(row["selected"], ensure_ascii=False, indent=2)
    grading = json.dumps({
        "gold_results": row["gold_results"],
        "case_all_gold_hit": row["case_all_gold_hit"],
        "first_gold_rank": row["first_gold_rank"],
        "reciprocal_rank": row["reciprocal_rank"],
    }, ensure_ascii=False, indent=2)
    return f"""# ADR-0061 질문 {row['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `run-001`
- arm: `baseline`
- phase: `holdout/out_of_sample`
- product model: `{MODEL}`
- retrieval cap: `20`
- shortcut: `disabled`
- latency: `{row['latency_ms']:.3f} ms`

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

{case['reference_answer']}

## 4. 제품 입력을 구성한 원값

```json
{raw}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{calls}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

별도 중간 모델은 없다. 위 제품 호출 목록에 primary selector와 assertion selector의 실제 교환을 호출 순서대로 보존했다.

## 7. 채점 호출과 반복 판정

judge 호출은 없다. `doc_id + article root node` exact match로 결정론적으로 채점했다.

```json
{grading}
```

## 8. 사례 최종 판정

- all gold in top 20: `{str(row['case_all_gold_hit']).lower()}`
- selected count: `{row['selected_count']}`

```json
{selected}
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    suite_path = args.suite if args.suite.is_absolute() else ROOT / args.suite
    adr_path = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    manifest_path = adr_path / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    index = index_mod.current().scoped(None)
    expected_sha = str(manifest["dataset"]["sha256"])
    _validate_suite(suite_path, suite, expected_sha, index)
    corpus_articles = _corpus_article_roots(index)
    if args.validate_only:
        print(json.dumps({
            "valid": True,
            "suite_sha256": expected_sha,
            "cases": len(suite["cases"]),
            "gold_article_instances": sum(
                len(case["expected_articles"]) for case in suite["cases"]),
            "corpus_article_roots": corpus_articles,
        }, ensure_ascii=False, indent=2))
        return 0

    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError("configured product LLM is unavailable")
    llm = llm_mod.LLM(model=MODEL)
    if getattr(llm, "model", "") != MODEL:
        raise RuntimeError(f"product model policy mismatch: {getattr(llm, 'model', '')}")

    rows = []
    for number, case in enumerate(suite["cases"], 1):
        before_calls = len(llm.log)
        started = time.perf_counter()
        sections, meta = legalclosure_runtime.retrieve(
            index,
            case["question"],
            llm=llm,
            assertion_llm=llm,
            cap=20,
            shortcut_enabled=False,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        calls = [exchange.dump() for exchange in llm.log[before_calls:]]
        selected = []
        ranks = {}
        for rank, section in enumerate(sections, 1):
            item = asdict(section)
            item["rank"] = rank
            selected.append(item)
            ranks[(section.doc_id, int(section.node))] = rank
        gold_results = []
        for gold in case["expected_articles"]:
            key = (str(gold["doc_id"]), int(gold["node"]))
            rank = ranks.get(key)
            gold_results.append({**gold, "hit": rank is not None, "rank": rank})
        first_gold_rank = min(
            (item["rank"] for item in gold_results if item["rank"] is not None),
            default=None,
        )
        row = {
            "number": number,
            "case_id": case["id"],
            "question": case["question"],
            "source_file": case["source_file"],
            "latency_ms": round(latency_ms, 3),
            "selected_count": len(selected),
            "selected": selected,
            "gold_results": gold_results,
            "case_all_gold_hit": all(item["hit"] for item in gold_results),
            "first_gold_rank": first_gold_rank,
            "reciprocal_rank": round(1 / first_gold_rank, 6) if first_gold_rank else 0.0,
            "llm_calls": calls,
            "usage": {
                "calls": len(calls),
                "input_tokens": sum(call.get("usage", {}).get("input_tokens", 0) for call in calls),
                "output_tokens": sum(call.get("usage", {}).get("output_tokens", 0) for call in calls),
                "errors": sum(bool(call.get("error")) for call in calls),
            },
            "retrieval_meta": meta,
        }
        rows.append(row)
        hits = sum(item["hit"] for item in gold_results)
        print(f"[{number}/10] {case['id']} gold {hits}/{len(gold_results)} selected {len(selected)} {latency_ms / 1000:.2f}s", flush=True)

    case_hits = sum(row["case_all_gold_hit"] for row in rows)
    article_total = sum(len(row["gold_results"]) for row in rows)
    article_hits = sum(item["hit"] for row in rows for item in row["gold_results"])
    selected_counts = [row["selected_count"] for row in rows]
    latencies = [row["latency_ms"] for row in rows]
    mean_selected = statistics.mean(selected_counts)
    summary = {
        "cases": len(rows),
        "case_all_gold_hits": case_hits,
        "case_all_gold_recall_at_20": round(case_hits / len(rows), 6),
        "gold_article_instances": article_total,
        "gold_article_hits": article_hits,
        "article_instance_recall_at_20": round(article_hits / article_total, 6),
        "mrr_at_20": round(statistics.mean(row["reciprocal_rank"] for row in rows), 6),
        "selected_mean": round(mean_selected, 3),
        "selected_p50": round(statistics.median(selected_counts), 3),
        "selected_p95": round(_percentile(selected_counts, 0.95), 3),
        "selected_max": max(selected_counts),
        "corpus_article_roots": corpus_articles,
        "mean_selectivity": round(mean_selected / corpus_articles, 8),
        "latency_ms_p50": round(statistics.median(latencies), 3),
        "latency_ms_p95": round(_percentile(latencies, 0.95), 3),
        "llm_calls": sum(row["usage"]["calls"] for row in rows),
        "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
        "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
        "llm_errors": sum(row["usage"]["errors"] for row in rows),
        "target_pass": case_hits >= 9 and article_hits >= 14,
        "strong_pass": case_hits == 10 and article_hits == 15,
    }
    result = {
        "schema_version": "fsc-hard-top20-run-v1",
        "adr_id": "ADR-0061",
        "run_id": "run-001",
        "arm_id": "baseline",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "suite": str(suite_path.relative_to(ROOT)),
        "suite_sha256": _sha256(suite_path),
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "model_policy": {
            "product_model": MODEL,
            "assertion_model": MODEL,
            "judge": None,
        },
        "contract": suite["task_contract"],
        "summary": summary,
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    question_dir = adr_path / "실험"
    for case, row in zip(suite["cases"], rows):
        question_path = question_dir / f"질문-{row['number']:03d}-{case['id']}.md"
        question_path.write_text(_question_markdown(case, row), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
