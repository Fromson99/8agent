#!/usr/bin/env python3
"""ADR-0091: trace and grade every LegalClosure v2 article landing on V2 Golden."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any


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
from lawrag.core.rag import (  # noqa: E402
    article_reachability,
    index as index_mod,
    legalclosure_runtime,
    switches,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger  # noqa: E402


ADR_ID = "ADR-0091"
EXPERIMENT_ID = "ADR-0091-experiment-v1"
ARM_ID = "traced-v2"
RUN_ID = "run-001"
MODEL = "claude-haiku-4-5-20251001"
CM = ROOT / "01_DATA/review/cm_core_e2e_v2.json"
FSC = ROOT / "01_DATA/review/fsc_hard_retrieval_v2.json"
SOURCE_HASHES = {
    str(CM.relative_to(ROOT)): "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    str(FSC.relative_to(ROOT)): "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
}
HISTORICAL_BASELINE = {
    "source": "ADR-0088 corrected ADR-0064 baseline",
    "cases": 61,
    "case_all_gold_hits": 48,
    "decisive_article_hits": 72,
    "decisive_article_instances": 90,
    "decisive_article_recall_at_20": 0.8,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2,
                         sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       round((len(ordered) - 1) * ratio))]


def _article_roots(index) -> int:
    return sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items())


def _gold_rows(case: dict, suite: str) -> list[dict]:
    rows = ((case.get("current_articles") or case.get("expected_articles") or [])
            if suite == "fsc-hard-10"
            else (case.get("expected_articles") or []))
    return [{
        "law": row.get("law"),
        "article": row.get("article"),
        "doc_id": str(row["doc_id"]),
        "node": int(row["node"]),
        "corpus_status": row.get("corpus_status"),
        "evidence_role": row.get("evidence_role"),
        "authority_as_of": row.get("authority_as_of"),
        "coordinate_scope": row.get("coordinate_scope"),
        "coordinate_key": row.get("coordinate_key"),
    } for row in rows
        if row.get("corpus_status") == "present"
        and row.get("evidence_role") == "decisive"
        and row.get("node") is not None]


def freeze(adr: Path) -> Path:
    cases = []
    for suite, path in (("cm-core-51", CM), ("fsc-hard-10", FSC)):
        if _sha(path) != SOURCE_HASHES[str(path.relative_to(ROOT))]:
            raise ValueError(f"source hash mismatch: {path}")
        source = json.loads(path.read_text(encoding="utf-8"))
        for case in source["cases"]:
            cases.append({
                "number": len(cases) + 1,
                "id": case["id"],
                "suite": suite,
                "question": case["question"],
                "reference_answer": case.get("reference_answer") or "",
                "gold_articles": _gold_rows(case, suite),
                "source_case_sha256": _json_sha(case),
                "material": case.get("material"),
                "mode": case.get("mode"),
                "answer_as_of": case.get("answer_as_of"),
                "current_as_of": case.get("current_as_of"),
            })
    gold_total = sum(len(case["gold_articles"]) for case in cases)
    if len(cases) != 61 or gold_total != 90:
        raise ValueError(
            f"expected V2 Golden 61 cases / 90 decisive articles, got "
            f"{len(cases)} / {gold_total}")
    value = {
        "schema_version": "legalclosure-v2-reachability-frozen-v1",
        "created_at": _now(),
        "selection_rule": "CM v2 51건 + FSC hard retrieval v2 10건 전수; 제외 없음",
        "gold_contract": "current decisive canonical article-root; product-hidden",
        "sources": [{"path": path, "sha256": digest}
                    for path, digest in SOURCE_HASHES.items()],
        "cases": cases,
        "counts": {"cases": len(cases), "decisive_articles": gold_total},
    }
    output = adr / "artifacts/input-lock.json"
    _write(output, value)
    return output


def _audit_call(kind, system, user, schema, max_tokens, effort, model,
                result, exchange) -> dict:
    return {
        "kind": kind,
        "system": system,
        "user": user,
        "schema": schema,
        "max_tokens": max_tokens,
        "effort": effort,
        "requested_model": model or MODEL,
        "provider": exchange.dump() if exchange is not None else {},
        "structured_output": result,
    }


class RecordingLLM:
    def __init__(self, real):
        self.real = real
        self.model = MODEL
        self.log = real.log
        self.audit: list[dict] = []

    def structured(self, kind, system, user, schema, max_tokens=16000,
                   effort="high", images=None, model=None):
        requested = model or MODEL
        if requested != MODEL:
            raise RuntimeError(f"product model policy mismatch: {requested}")
        before = len(self.real.log)
        result = self.real.structured(
            kind, system, user, schema, max_tokens=max_tokens,
            effort=effort, images=images, model=MODEL)
        exchange = self.real.log[before] if len(self.real.log) > before else None
        if exchange is None or exchange.model != MODEL:
            raise RuntimeError(
                f"provider model policy mismatch: {getattr(exchange, 'model', None)}")
        self.audit.append(_audit_call(
            kind, system, user, schema, max_tokens, effort, requested,
            result, exchange))
        return result


def _usage(calls: list[dict]) -> dict:
    return {
        "calls": len(calls),
        "input_tokens": sum(int((row.get("provider") or {}).get(
            "usage", {}).get("input_tokens", 0)) for row in calls),
        "output_tokens": sum(int((row.get("provider") or {}).get(
            "usage", {}).get("output_tokens", 0)) for row in calls),
        "provider_duration_ms": sum(int((row.get("provider") or {}).get(
            "dur_ms", 0)) for row in calls),
        "errors": sum(bool((row.get("provider") or {}).get("error"))
                      for row in calls),
    }


def _selected(sections) -> list[dict]:
    return [{
        "rank": rank,
        "doc_id": row.doc_id,
        "node": int(row.node),
        "doc": row.doc,
        "path": row.path,
        "origin": row.matched,
        "ref_src": row.ref_src,
    } for rank, row in enumerate(sections, 1)]


def _case_row(case: dict, sections, meta: dict, calls: list[dict],
              wall_ms: float) -> dict:
    metadata = deepcopy(meta)
    capture = metadata.pop("article_reachability")
    graded = article_reachability.grade_capture(
        capture, [(row["doc_id"], row["node"])
                  for row in case["gold_articles"]])
    selected = _selected(sections)
    present = {(row["doc_id"], row["node"]) for row in selected}
    gold_results = [{**gold, "hit": (gold["doc_id"], gold["node"]) in present,
                     "rank": next((row["rank"] for row in selected
                                   if row["doc_id"] == gold["doc_id"]
                                   and row["node"] == gold["node"]), None)}
                    for gold in case["gold_articles"]]
    return {
        "number": case["number"],
        "case_id": case["id"],
        "suite": case["suite"],
        "question": case["question"],
        "selected": selected,
        "selected_count": len(selected),
        "gold_results": gold_results,
        "case_all_gold_hit": all(row["hit"] for row in gold_results),
        "product_capture": capture,
        "graded_trace": graded,
        "retrieval_meta": metadata,
        "llm_calls": calls,
        "provider_usage": _usage(calls),
        "wall_ms": round(wall_ms, 3),
        "trace_elapsed_ms": float(meta.get("article_reachability_elapsed_ms") or 0),
    }


def _summary(rows: list[dict], corpus_total: int) -> dict:
    gold = [item for row in rows for item in row["gold_results"]]
    hits = sum(item["hit"] for item in gold)
    all_gold_hits = sum(row["case_all_gold_hit"] for row in rows)
    selected_counts = [row["selected_count"] for row in rows]
    walls = [row["wall_ms"] for row in rows]
    trace_times = [row["trace_elapsed_ms"] for row in rows]
    usage = {key: sum(row["provider_usage"][key] for row in rows)
             for key in ("calls", "input_tokens", "output_tokens",
                         "provider_duration_ms", "errors")}
    channels: dict[str, dict[str, int]] = {}
    for channel in ("A_EXACT", "B_ASSERTION", "C_BM25", "D_CLOSURE",
                    "REFERENCE_RESCUE"):
        values = [row["graded_trace"]["channels"][channel] for row in rows]
        channels[channel] = {
            key: sum(int(value[key]) for value in values)
            for key in ("raw_candidates", "selected_candidates",
                        "raw_gold_hits", "selected_gold_hits",
                        "first_touch", "unique_contribution")}
    fates = Counter(fate["fate"] for row in rows
                    for fate in row["graded_trace"]["article_fates"])
    event_reasons = Counter(event["reason_code"] for row in rows
                            for event in row["product_capture"]["events"])
    return {
        "cases": len(rows),
        "gold_article_instances": len(gold),
        "gold_article_hits": hits,
        "article_instance_recall_at_20": round(hits / len(gold), 6) if gold else 0,
        "case_all_gold_hits": all_gold_hits,
        "case_all_gold_recall_at_20": round(all_gold_hits / len(rows), 6)
        if rows else 0,
        "corpus_article_roots": corpus_total,
        "presented_total": sum(selected_counts),
        "presented_mean": round(statistics.mean(selected_counts), 6)
        if selected_counts else 0,
        "presented_p50": statistics.median(selected_counts)
        if selected_counts else 0,
        "presented_p95": _percentile(selected_counts, .95),
        "selectivity": round(statistics.mean(selected_counts) / corpus_total, 10)
        if selected_counts and corpus_total else 0,
        "wall_ms_p50": round(statistics.median(walls), 3) if walls else 0,
        "wall_ms_p95": round(_percentile(walls, .95), 3),
        "trace_ms_p50": round(statistics.median(trace_times), 3)
        if trace_times else 0,
        "trace_ms_p95": round(_percentile(trace_times, .95), 3),
        "provider_usage": usage,
        "channels": channels,
        "gold_fates": dict(sorted(fates.items())),
        "event_reason_counts": dict(sorted(event_reasons.items())),
        "criteria": {
            "all_61_cases_recorded": len(rows) == 61,
            "gold_hidden_from_product": all(
                row["product_capture"]["gold_visible_to_product"] is False
                for row in rows),
            "provider_errors_zero": usage["errors"] == 0,
            "product_model_haiku_only": all(
                call["requested_model"] == MODEL
                and (call["provider"] or {}).get("model") == MODEL
                for row in rows for call in row["llm_calls"]),
            "trace_p95_within_budget": (
                _percentile(trace_times, .95) <= 250
                or (_percentile(walls, .95) > 0
                    and _percentile(trace_times, .95)
                    <= _percentile(walls, .95) * 0.05)),
            "cap_20": all(value <= 20 for value in selected_counts),
        },
    }


def _stage_table(graded: dict) -> str:
    lines = [
        "| stage | kind | before | added | discarded | after | gold before→after | recall |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for stage in graded["stage_ledger"]["stages"]:
        recall = stage.get("golden_recall")
        lines.append(
            f"| `{stage['stage_id']}` | {stage['kind']} | "
            f"{stage['before_count']} | {stage['added_count']} | "
            f"{stage['discarded_count']} | {stage['after_count']} | "
            f"{stage['gold_before']}→{stage['gold_after']} | "
            f"{recall if recall is not None else 'n/a'} |")
    return "\n".join(lines)


def _question_markdown(case: dict, row: dict, ledger_path: str) -> str:
    verdict = "맞음" if row["case_all_gold_hit"] else "틀림"
    return f"""# {case['id']} — LegalClosure v2 조항 도달 추적

## 1. 실행 메타

- case ID: `{case['id']}`
- run / arm: `{RUN_ID}` / `{ARM_ID}`
- suite: `{case['suite']}`
- 제품 모델: `{MODEL}`
- 판정: **{verdict}**

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

이 절의 기준답변과 gold 좌표는 제품 검색 호출이 끝난 뒤 exact grader만 읽었다.

```text
{case['reference_answer']}
```

```json
{json.dumps(case['gold_articles'], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

- stage ledger: `{ledger_path}`
- 제품 검색에는 질문 원문만 전달했으며 reference answer와 gold 좌표는 전달하지 않았다.

### 회수·탈락 단계 원장 — run·arm별

{_stage_table(row['graded_trace'])}

#### Gold-free product capture 전체

```json
{json.dumps(row['product_capture'], ensure_ascii=False, indent=2)}
```

#### 선택 조문과 retrieval meta

```json
{json.dumps({'selected': row['selected'], 'retrieval_meta': row['retrieval_meta']}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(row['llm_calls'], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

LegalClosure의 term/document/body 선택과 Assertion tree 선택은 위 5절의 호출 원문에
역할별로 모두 보존했다. 별도 repair나 답변 생성 호출은 실행하지 않았다.

## 7. 채점 호출과 반복 판정

LLM judge 호출은 없다. 검색 종료 뒤 canonical `(doc_id, article-root node)` exact join을
한 번 수행했다.

```json
{json.dumps({'gold_results': row['gold_results'], 'graded_trace': row['graded_trace']}, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

- all-gold 판정: **{verdict}**
- 최종 제시 조문 수: `{row['selected_count']}`
- 종단 지연: `{row['wall_ms']}` ms
- trace 계측 지연: `{row['trace_elapsed_ms']}` ms
- gold fate: `{json.dumps(row['graded_trace']['failure_counts'], ensure_ascii=False)}`
"""


def _report_markdown(summary: dict) -> str:
    channel_lines = [
        "| 채널 | raw 후보 | 선택 후보 | raw gold | 선택 gold | first-touch | 단독 기여 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for channel, row in summary["channels"].items():
        channel_lines.append(
            f"| {channel} | {row['raw_candidates']} | {row['selected_candidates']} | "
            f"{row['raw_gold_hits']} | {row['selected_gold_hits']} | "
            f"{row['first_touch']} | {row['unique_contribution']} |")
    return f"""# LegalClosure v2 V2 Golden 조항 도달 보고서

- 질문: {summary['cases']}건
- decisive gold: {summary['gold_article_hits']}/{summary['gold_article_instances']}
- article recall@20: {summary['article_instance_recall_at_20']}
- all-gold case recall@20: {summary['case_all_gold_hits']}/{summary['cases']} ({summary['case_all_gold_recall_at_20']})
- 지연 p50/p95: {summary['wall_ms_p50']} / {summary['wall_ms_p95']} ms
- trace p50/p95: {summary['trace_ms_p50']} / {summary['trace_ms_p95']} ms

## 채널 기여

{chr(10).join(channel_lines)}

## Gold 생명주기

```json
{json.dumps(summary['gold_fates'], ensure_ascii=False, indent=2)}
```

## 표준 실패·결정 사유

```json
{json.dumps(summary['event_reason_counts'], ensure_ascii=False, indent=2)}
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0,
                        help="diagnostic only; forbidden for the frozen primary run")
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    if args.freeze_only:
        output = freeze(adr)
        print(json.dumps({"path": str(output.relative_to(ROOT)),
                          "sha256": _sha(output)}, ensure_ascii=False))
        return 0

    manifest_path = adr / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen_path = adr / "artifacts/input-lock.json"
    if _sha(frozen_path) != manifest["dataset"]["sha256"]:
        raise ValueError("frozen V2 Golden input-lock SHA mismatch")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if args.limit:
        raise ValueError("primary frozen run forbids post-freeze sampling")

    index = index_mod.current().scoped(None)
    corpus_total = _article_roots(index)
    out = adr / "artifacts/run-001.json"
    rows = []
    if args.resume and out.exists():
        rows = json.loads(out.read_text(encoding="utf-8")).get("rows") or []
    completed = {row["case_id"] for row in rows}

    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError(f"configured product LLM is unavailable: {llm_mod.MISSING_HINT}")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")

    ledger_relative = str((adr / "artifacts/retrieval-stage-ledger-run-001.json")
                          .relative_to(ROOT))
    for case in frozen["cases"]:
        if case["id"] in completed:
            continue
        recording = RecordingLLM(real)
        trace = article_reachability.ArticleReachabilityTrace(
            index, case["id"], ARM_ID)
        started = time.perf_counter()
        sections, meta = legalclosure_runtime.retrieve(
            index, case["question"], llm=recording,
            assertion_llm=recording, cap=20,
            shortcut_enabled=False, feedback_enabled=False,
            reachability_trace=trace)
        wall_ms = (time.perf_counter() - started) * 1000
        row = _case_row(case, sections, meta, recording.audit, wall_ms)
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        partial = {
            "schema_version": "legalclosure-v2-reachability-run-v1",
            "adr_id": ADR_ID,
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "created_at": _now(),
            "complete": len(rows) == 61,
            "input_lock": str(frozen_path.relative_to(ROOT)),
            "input_lock_sha256": _sha(frozen_path),
            "runner": str(Path(__file__).resolve().relative_to(ROOT)),
            "runner_sha256": _sha(Path(__file__).resolve()),
            "model_policy": {"product_model": MODEL, "judge": None},
            "switches": switches.snapshot(),
            "historical_baseline": HISTORICAL_BASELINE,
            "summary": _summary(rows, corpus_total),
            "rows": rows,
        }
        _write(out, partial)
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        question_path.write_text(
            _question_markdown(case, row, ledger_relative), encoding="utf-8")
        hits = sum(item["hit"] for item in row["gold_results"])
        print(f"[{case['number']:02d}/61] {case['id']} "
              f"gold={hits}/{len(row['gold_results'])} "
              f"selected={row['selected_count']} calls={len(recording.audit)} "
              f"wall={row['wall_ms']:.0f}ms", flush=True)

    if len(rows) != 61:
        raise RuntimeError(f"incomplete run: {len(rows)}/61")
    declared = [row["stage_id"] for row in manifest["design"]
                ["retrieval_stage_plan"]["stages_by_arm"][ARM_ID]]
    run_ledger = retrieval_stage_ledger.build_run_artifact(
        RUN_ID, [row["graded_trace"]["stage_ledger"] for row in rows],
        {ARM_ID: declared})
    experiment_ledger = retrieval_stage_ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-001.json"
    _write(ledger_path, experiment_ledger)

    summary = _summary(rows, corpus_total)
    final = json.loads(out.read_text(encoding="utf-8"))
    final["summary"] = summary
    final["complete"] = True
    final["stage_ledger"] = {
        "path": str(ledger_path.relative_to(ROOT)),
        "sha256": _sha(ledger_path),
        "artifact_sha256": experiment_ledger["artifact_sha256"],
    }
    _write(out, final)
    _write(adr / "artifacts/channel-metrics.json", summary["channels"])
    _write(adr / "artifacts/failure-metrics.json", {
        "gold_fates": summary["gold_fates"],
        "event_reason_counts": summary["event_reason_counts"],
    })
    report = adr / "artifacts/reachability-report.md"
    report.write_text(_report_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
