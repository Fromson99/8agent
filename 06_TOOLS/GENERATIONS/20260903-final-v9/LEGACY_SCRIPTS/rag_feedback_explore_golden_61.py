#!/usr/bin/env python3
"""ADR-0064: CM 51 + FSC hard 10에서 LegalClosure feedback OFF/ON 비교."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key, _relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core import llm as llm_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legalclosure_runtime  # noqa: E402


MODEL = "claude-haiku-4-5-20251001"
CM_SOURCE = ROOT / "data/review/cm_core_e2e_v1.json"
FSC_SOURCE = ROOT / "data/review/fsc_hard_retrieval_v1.json"
FROZEN_NAME = "frozen-cases.json"
ARMS = ("baseline", "feedback-explore")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * ratio))]


def _article_roots(index) -> int:
    return sum(
        node.get("family") == "kr_article"
        and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values()
        for node_id, node in view.by_id.items()
    )


def freeze(adr: Path) -> Path:
    index = index_mod.current().scoped(None)
    sources = [("cm-core-51", CM_SOURCE), ("fsc-hard-10", FSC_SOURCE)]
    cases = []
    for suite_name, path in sources:
        blob = json.loads(path.read_text(encoding="utf-8"))
        for source_case in blob.get("cases") or ():
            expected = []
            for gold in source_case.get("expected_articles") or ():
                doc_id = str(gold.get("doc_id") or "")
                corpus_status = str(gold.get("corpus_status") or "present")
                node = int(gold["node"]) if gold.get("node") is not None else None
                if corpus_status == "present":
                    view = index.docs.get(doc_id)
                    if view is None or node not in view.by_id:
                        raise ValueError(
                            f"missing gold: {source_case['id']} {doc_id}:{node}")
                expected.append({
                    "law": gold.get("law"), "article": gold.get("article"),
                    "doc_id": doc_id, "node": node,
                    "corpus_status": corpus_status,
                    "document_revision": gold.get("document_revision"),
                    "document_enforcement": gold.get("document_enforcement"),
                })
            cases.append({
                "number": len(cases) + 1,
                "id": source_case["id"], "suite": suite_name,
                "question": source_case["question"],
                "reference_answer": source_case.get("reference_answer", ""),
                "expected_articles": expected,
                "source_case_sha256": hashlib.sha256(json.dumps(
                    source_case, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
            })
    total = sum(len(c["expected_articles"]) for c in cases)
    scorable = sum(
        item["corpus_status"] == "present" and item["node"] is not None
        for c in cases for item in c["expected_articles"])
    if len(cases) != 61 or total != 85 or scorable != 83:
        raise ValueError("expected 61 cases / 85 total / 83 scorable instances")
    frozen = {
        "schema_version": "feedback-explore-golden-61-frozen-v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": "cm-core 51 전수 + fsc-hard 10 전수; 제외 없음",
        "sources": [{"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
                    for _name, path in sources],
        "cases": cases,
    }
    path = adr / "artifacts" / FROZEN_NAME
    path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _audit_call(kind, system, user, schema, max_tokens, effort, model,
                result, exchange, *, replayed_from="") -> dict:
    return {
        "kind": kind, "system": system, "user": user, "schema": schema,
        "max_tokens": max_tokens, "effort": effort,
        "requested_model": model or MODEL,
        "provider": exchange.dump() if exchange is not None else {},
        "structured_output": result,
        "replayed": bool(replayed_from), "replayed_from": replayed_from,
    }


class RecordingLLM:
    def __init__(self, real):
        self.real = real
        self.model = real.model
        self.audit: list[dict] = []
        self.log = real.log

    def structured(self, kind, system, user, schema, max_tokens=16000,
                   effort="high", images=None, model=None):
        before = len(self.real.log)
        result = self.real.structured(
            kind, system, user, schema, max_tokens=max_tokens, effort=effort,
            images=images, model=model)
        exchange = self.real.log[before] if len(self.real.log) > before else None
        self.audit.append(_audit_call(
            kind, system, user, schema, max_tokens, effort, model, result, exchange))
        return result


@dataclass
class ReplayExchange:
    kind: str
    system: str
    user: str
    raw_response: str
    parsed: object
    model: str = MODEL
    usage: dict = None
    stop_reason: str = "replayed"
    at: str = ""
    error: str = ""
    images: int = 0
    dur_ms: int = 0
    ttft_ms: int = 0

    def __post_init__(self):
        if self.usage is None:
            self.usage = {}

    def dump(self) -> dict:
        return {
            "kind": self.kind, "at": self.at, "model": self.model,
            "usage": self.usage, "stop_reason": self.stop_reason,
            "images": self.images, "dur_ms": self.dur_ms,
            "ttft_ms": self.ttft_ms, "system": self.system,
            "user": self.user, "raw_response": self.raw_response,
            "error": self.error,
        }


class ReplayInitialLLM:
    """baseline 초기 출력을 재생하고 feedback 호출만 실제 Haiku로 보낸다."""

    def __init__(self, real, shared: list[dict], case_id: str):
        self.real = real
        self.model = real.model
        self.shared = shared
        self.case_id = case_id
        self.cursor = 0
        self.audit: list[dict] = []
        self.log: list[object] = []

    def structured(self, kind, system, user, schema, max_tokens=16000,
                   effort="high", images=None, model=None):
        if kind == "rag.legalclosure.feedback":
            before = len(self.real.log)
            result = self.real.structured(
                kind, system, user, schema, max_tokens=max_tokens, effort=effort,
                images=images, model=model)
            exchange = self.real.log[before] if len(self.real.log) > before else None
            if exchange is not None:
                self.log.append(exchange)
            self.audit.append(_audit_call(
                kind, system, user, schema, max_tokens, effort, model,
                result, exchange))
            return result
        if self.cursor >= len(self.shared):
            raise RuntimeError(f"{self.case_id}: unexpected shared call {kind}")
        source = self.shared[self.cursor]
        self.cursor += 1
        if (source["kind"] != kind or source["system"] != system
                or source["user"] != user or source["schema"] != schema):
            raise RuntimeError(
                f"{self.case_id}: replay mismatch {source['kind']} != {kind}")
        provider = source.get("provider") or {}
        result = deepcopy(source.get("structured_output"))
        exchange = ReplayExchange(
            kind, system, user, str(provider.get("raw_response") or ""), result,
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.log.append(exchange)
        self.audit.append(_audit_call(
            kind, system, user, schema, max_tokens, effort, model, result,
            exchange, replayed_from=f"{self.case_id}/baseline"))
        return result

    def assert_consumed(self):
        if self.cursor != len(self.shared):
            raise RuntimeError(
                f"{self.case_id}: replay consumed {self.cursor}/{len(self.shared)}")


def _selected(sections) -> list[dict]:
    return [{
        "rank": rank, "doc_id": row.doc_id, "node": int(row.node),
        "doc": row.doc, "path": row.path, "origin": row.matched,
    } for rank, row in enumerate(sections, 1)]


def _grade(case: dict, selected: list[dict]) -> tuple[list[dict], bool]:
    ranks = {(row["doc_id"], row["node"]): row["rank"] for row in selected}
    gold = []
    for item in case["expected_articles"]:
        scorable = item.get("corpus_status") == "present" and item.get("node") is not None
        rank = ranks.get((item["doc_id"], item["node"])) if scorable else None
        gold.append({**item, "scorable": scorable,
                     "hit": rank is not None if scorable else None, "rank": rank})
    scored = [item for item in gold if item["scorable"]]
    return gold, all(item["hit"] for item in scored) if scored else None


def _usage(calls: list[dict], *, actual_only: bool = False) -> dict:
    values = [row for row in calls if not actual_only or not row.get("replayed")]
    return {
        "calls": len(values),
        "input_tokens": sum(int((row.get("provider") or {}).get(
            "usage", {}).get("input_tokens", 0)) for row in values),
        "output_tokens": sum(int((row.get("provider") or {}).get(
            "usage", {}).get("output_tokens", 0)) for row in values),
        "duration_ms": sum(int((row.get("provider") or {}).get("dur_ms", 0))
                           for row in values),
        "errors": sum(bool((row.get("provider") or {}).get("error"))
                      for row in values),
    }


def _arm_row(case: dict, arm: str, sections, meta, calls, wall_ms) -> dict:
    selected = _selected(sections)
    gold, all_hit = _grade(case, selected)
    return {
        "arm": arm, "selected": selected, "selected_count": len(selected),
        "gold_results": gold, "case_all_gold_hit": all_hit,
        "retrieval_meta": meta, "llm_calls": calls,
        "provider_usage": _usage(calls, actual_only=True),
        "wall_ms": round(wall_ms, 3),
    }


def _paired(baseline: dict, candidate: dict) -> dict:
    pairs = []
    for left, right in zip(baseline["gold_results"], candidate["gold_results"]):
        status = ("unscorable" if not left["scorable"] else
                  "both" if left["hit"] and right["hit"] else
                  "candidate_only" if right["hit"] else
                  "baseline_only" if left["hit"] else "neither")
        pairs.append({"doc_id": left["doc_id"], "node": left["node"],
                      "law": left["law"], "article": left["article"],
                      "status": status})
    case_status = ("unscorable" if baseline["case_all_gold_hit"] is None else
        "both" if baseline["case_all_gold_hit"] and candidate["case_all_gold_hit"] else
        "candidate_only" if candidate["case_all_gold_hit"] else
        "baseline_only" if baseline["case_all_gold_hit"] else "neither")
    return {"articles": pairs, "case_all_gold": case_status}


def _summary(rows: list[dict], corpus: int) -> dict:
    result = {"cases": len(rows), "corpus_article_roots": corpus, "arms": {}}
    for arm in ARMS:
        values = [row["arms"][arm] for row in rows]
        scored = [gold for row in values for gold in row["gold_results"]
                  if gold["scorable"]]
        total = len(scored)
        hits = sum(gold["hit"] for gold in scored)
        scored_cases = [row for row in values
                        if row["case_all_gold_hit"] is not None]
        counts = [row["selected_count"] for row in values]
        walls = [row["wall_ms"] for row in values]
        incremental_usage = {key: sum(row["provider_usage"][key] for row in values)
                 for key in ("calls", "input_tokens", "output_tokens",
                             "duration_ms", "errors")}
        if arm == "feedback-explore":
            shared_usage = {key: sum(row["arms"]["baseline"]["provider_usage"][key]
                                     for row in rows) for key in incremental_usage}
            usage = {key: shared_usage[key] + incremental_usage[key]
                     for key in incremental_usage}
        else:
            usage = incremental_usage
        result["arms"][arm] = {
            "scorable_cases": len(scored_cases),
            "case_all_gold_hits": sum(row["case_all_gold_hit"] for row in scored_cases),
            "case_all_gold_recall_at_20": round(
                sum(row["case_all_gold_hit"] for row in scored_cases) / len(scored_cases), 6)
                if scored_cases else 0,
            "gold_article_instances": total, "gold_article_hits": hits,
            "article_instance_recall_at_20": round(hits / total, 6) if total else 0,
            "selected_mean": round(statistics.mean(counts), 3) if counts else 0,
            "selected_p50": statistics.median(counts) if counts else 0,
            "selected_p95": _percentile(counts, .95),
            "mean_selectivity": round(statistics.mean(counts) / corpus, 8)
            if counts and corpus else 0,
            "wall_ms_p50": round(statistics.median(walls), 3) if walls else 0,
            "wall_ms_p95": round(_percentile(walls, .95), 3),
            "provider_usage": usage,
            "incremental_provider_usage": incremental_usage,
        }
    article_status = [item["status"] for row in rows
                      for item in row["paired"]["articles"]]
    case_status = [row["paired"]["case_all_gold"] for row in rows]
    result["paired_articles"] = {
        key: article_status.count(key)
        for key in ("candidate_only", "baseline_only", "both", "neither",
                    "unscorable")}
    result["paired_cases"] = {
        key: case_status.count(key)
        for key in ("candidate_only", "baseline_only", "both", "neither",
                    "unscorable")}
    baseline_p95 = result["arms"]["baseline"]["wall_ms_p95"]
    candidate_p95 = result["arms"]["feedback-explore"]["wall_ms_p95"]
    result["criteria"] = {
        "candidate_article_gain_at_least_2": (
            result["paired_articles"]["candidate_only"] >= 2),
        "article_regression_zero": result["paired_articles"]["baseline_only"] == 0,
        "case_regression_zero": result["paired_cases"]["baseline_only"] == 0,
        "cap_20": all(v["selected_count"] <= 20 for row in rows
                      for v in row["arms"].values()),
        "feedback_errors_zero": result["arms"]["feedback-explore"][
            "incremental_provider_usage"]["errors"] == 0,
        "feedback_calls_at_most_3_per_case": all(
            row["arms"]["feedback-explore"]["provider_usage"]["calls"] <= 3
            for row in rows),
        "estimated_latency_p95_at_most_3x": (
            candidate_p95 <= baseline_p95 * 3 if baseline_p95 else False),
    }
    result["target_pass"] = all(result["criteria"].values())
    return result


def _question_markdown(case: dict, row: dict) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"]["feedback-explore"]
    return f"""# ADR-0064 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- run: `run-001`
- arms: `baseline`, `feedback-explore`
- phase: `probe/in_sample`
- product model: `{MODEL}`
- retrieval cap: `20`
- shared initial calls: candidate에서 baseline structured output exact replay

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

{case['reference_answer']}

## 4. 제품 입력을 구성한 비정답 원값

```json
{json.dumps({'suite': case['suite'], 'cap': 20, 'shortcut_enabled': False, 'feedback_enabled_by_arm': {'baseline': False, 'feedback-explore': True}}, ensure_ascii=False, indent=2)}
```

## 5. run·arm별 제품 호출

### baseline

```json
{json.dumps(baseline['llm_calls'], ensure_ascii=False, indent=2)}
```

### feedback-explore

```json
{json.dumps(candidate['llm_calls'], ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출

위 호출 목록에 초기 selector와 feedback 충분성 판정·탐색 조정자의 system, user,
schema, provider 원응답, structured output을 호출 순서대로 보존했다.

## 7. 채점

judge LLM은 없다. 기준답변은 제품에 비공개이며 `doc_id + article root node` exact match로 채점했다.

```json
{json.dumps({'baseline': baseline['gold_results'], 'feedback-explore': candidate['gold_results'], 'paired': row['paired']}, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

```json
{json.dumps({'baseline_selected': baseline['selected'], 'feedback_selected': candidate['selected'], 'feedback_meta': candidate['retrieval_meta'].get('feedback_loop')}, ensure_ascii=False, indent=2)}
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    if args.freeze_only:
        path = freeze(adr)
        print(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": _sha(path)},
                         ensure_ascii=False, indent=2))
        return 0
    frozen_path = adr / "artifacts" / FROZEN_NAME
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    manifest = json.loads((adr / "실험/manifest.json").read_text(encoding="utf-8"))
    if _sha(frozen_path) != manifest["dataset"]["sha256"]:
        raise ValueError("frozen dataset SHA mismatch")
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out
    index = index_mod.current().scoped(None)
    corpus = _article_roots(index)
    rows = []
    if args.resume and out.exists():
        rows = json.loads(out.read_text(encoding="utf-8")).get("rows") or []
    completed = {row["case_id"] for row in rows}
    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError("configured product LLM is unavailable")
    real = llm_mod.LLM(model=MODEL)
    if real.model != MODEL:
        raise RuntimeError(f"model policy mismatch: {real.model}")
    for case in frozen["cases"]:
        if case["id"] in completed:
            continue
        baseline_llm = RecordingLLM(real)
        started = time.perf_counter()
        base_sections, base_meta = legalclosure_runtime.retrieve(
            index, case["question"], llm=baseline_llm,
            assertion_llm=baseline_llm, cap=20, shortcut_enabled=False,
            feedback_enabled=False)
        base_ms = (time.perf_counter() - started) * 1000
        baseline = _arm_row(
            case, "baseline", base_sections, base_meta,
            baseline_llm.audit, base_ms)

        replay = ReplayInitialLLM(real, baseline_llm.audit, case["id"])
        started = time.perf_counter()
        cand_sections, cand_meta = legalclosure_runtime.retrieve(
            index, case["question"], llm=replay, assertion_llm=replay,
            cap=20, shortcut_enabled=False, feedback_enabled=True)
        candidate_incremental_ms = (time.perf_counter() - started) * 1000
        replay.assert_consumed()
        shared_provider_ms = baseline["provider_usage"]["duration_ms"]
        candidate = _arm_row(
            case, "feedback-explore", cand_sections, cand_meta,
            replay.audit, candidate_incremental_ms + shared_provider_ms)
        candidate["replay_path_wall_ms"] = round(
            candidate_incremental_ms, 3)
        row = {
            "number": case["number"], "case_id": case["id"],
            "suite": case["suite"], "question": case["question"],
            "arms": {"baseline": baseline, "feedback-explore": candidate},
            "paired": _paired(baseline, candidate),
        }
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        result = {
            "schema_version": "feedback-explore-golden-61-run-v1",
            "adr_id": "ADR-0064", "run_id": "run-001",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "frozen_dataset": str(frozen_path.relative_to(ROOT)),
            "frozen_sha256": _sha(frozen_path),
            "runner": str(Path(__file__).resolve().relative_to(ROOT)),
            "runner_sha256": _sha(Path(__file__).resolve()),
            "model_policy": {"product_model": MODEL, "judge": None,
                             "temperature": "provider default / omitted"},
            "summary": _summary(rows, corpus), "rows": rows,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        question = adr / "실험" / f"질문-{case['number']:03d}-{case['id']}.md"
        question.write_text(_question_markdown(case, row), encoding="utf-8")
        b_hits = sum(g["hit"] for g in baseline["gold_results"] if g["scorable"])
        c_hits = sum(g["hit"] for g in candidate["gold_results"] if g["scorable"])
        total_scored = sum(g["scorable"] for g in baseline["gold_results"])
        print(f"[{case['number']:02d}/61] {case['id']} "
              f"baseline={b_hits}/{total_scored} "
              f"feedback={c_hits}/{total_scored} "
              f"feedback_steps={(cand_meta.get('feedback_loop') or {}).get('steps', 0)}",
              flush=True)
    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
