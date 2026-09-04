#!/usr/bin/env python3
"""ADR-0092 deterministic two-case add-only recovery probe."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "data/law_index.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import companion_recovery, index as index_mod  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0092"
EXPERIMENT_ID = "ADR-0092-experiment-v1"
RUN_ID = "run-001"
ARMS = (
    "baseline", "delegation-second-hop", "governing-axis-feedback", "combined")
STAGES = {
    "baseline": ["query-source", "baseline-load", "present"],
    "delegation-second-hop": [
        "query-source", "baseline-load", "delegation-second-hop-expand", "present"],
    "governing-axis-feedback": [
        "query-source", "baseline-load", "governing-axis-retrieve",
        "governing-companion-expand", "present"],
    "combined": [
        "query-source", "baseline-load", "delegation-second-hop-expand",
        "governing-axis-retrieve", "governing-companion-expand", "present"],
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def _coords(rows) -> list[tuple[str, int]]:
    return [(str(row.doc_id), int(row.node)) for row in rows]


def _present(recorder, parent: str, before, after) -> None:
    after_set = set(after)
    recorder.record_stage(
        "present", "present", after,
        parent_stage_ids=(parent,),
        discard_reasons={coordinate: "final_cap_dropped"
                         for coordinate in set(before) - after_set},
    )


def _execute(index, case: dict, arm: str) -> dict:
    """Gold-free candidate execution; case must not contain a gold field."""
    started = time.perf_counter()
    question = case["question"]
    floor = [(str(doc), int(node)) for doc, node in case["baseline_present"]]
    d_seeds = [(str(doc), int(node)) for doc, node in case["d_selected_only"]]
    canonicalize = ledger.index_article_root_canonicalizer(index)
    recorder = ledger.StageLedgerRecorder(case["case_id"], arm, canonicalize)
    recorder.record_stage("query-source", "source", [])
    recorder.record_stage(
        "baseline-load", "retrieve", floor, parent_stage_ids=("query-source",))
    current = list(floor)
    audit = {"baseline_floor": [list(row) for row in floor], "llm_calls": 0}

    if arm in {"delegation-second-hop", "combined"}:
        delegation, delegation_meta = companion_recovery.bounded_delegation_hop(
            index, d_seeds, question, exclude=current, cap=2)
        delegation_coordinates = _coords(delegation)
        current = companion_recovery.add_only_coordinates(
            current, delegation_coordinates, cap=25)
        recorder.record_stage(
            "delegation-second-hop-expand", "expand", current,
            parent_stage_ids=("baseline-load",))
        audit["delegation"] = delegation_meta

    if arm in {"governing-axis-feedback", "combined"}:
        governing, governing_meta = companion_recovery.governing_axis_feedback(
            index, question, answer_incorrect=True, exclude=current,
            direct_cap=3, companion_cap=2)
        direct = [row for row in governing
                  if row.origin == "governing-axis-negative-feedback"]
        companions = [row for row in governing
                      if row.origin == "bounded-delegation-second-hop"]
        direct_coordinates = _coords(direct)
        companion_coordinates = _coords(companions)
        prior = ("delegation-second-hop-expand"
                 if arm == "combined" else "baseline-load")
        current = companion_recovery.add_only_coordinates(
            current, direct_coordinates, cap=25)
        recorder.record_stage(
            "governing-axis-retrieve", "retrieve", current,
            parent_stage_ids=(prior,))
        current = companion_recovery.add_only_coordinates(
            current, companion_coordinates, cap=25)
        recorder.record_stage(
            "governing-companion-expand", "expand", current,
            parent_stage_ids=("governing-axis-retrieve",))
        audit["governing_feedback"] = governing_meta

    final = companion_recovery.add_only_coordinates(floor, current[len(floor):], cap=20)
    parent = ({"baseline": "baseline-load",
               "delegation-second-hop": "delegation-second-hop-expand",
               "governing-axis-feedback": "governing-companion-expand",
               "combined": "governing-companion-expand"})[arm]
    _present(recorder, parent, current, final)
    capture = recorder.capture()
    return {
        "arm_id": arm,
        "case_id": case["case_id"],
        "capture": capture,
        "audit": audit,
        "final_coordinates": [list(row) for row in final],
        "added_coordinates": [list(row) for row in final if row not in set(floor)],
        "baseline_preserved": all(row in final for row in floor),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _corpus_articles(index) -> int:
    return sum(
        node.get("family") == "kr_article" and "부칙" not in (view.path(node_id) or "")
        for view in index.docs.values() for node_id, node in view.by_id.items())


def run(adr: Path) -> None:
    lock_path = adr / "artifacts/input-lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    if _sha(lock_path) != "10f79bf6494b7586c061c8b3f9bae961565dfbd50ba57a7ea80bbb7bbaddb991":
        raise ValueError("input lock hash mismatch")
    for source in lock["sources"]:
        if _sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")

    index = index_mod.current()
    if not index.docs:
        raise RuntimeError("structure index is empty")
    product_rows = []
    for case in lock["cases"]:
        public_case = {key: case[key] for key in (
            "case_id", "question", "baseline_present", "d_selected_only")}
        for arm in ARMS:
            product_rows.append(_execute(index, public_case, arm))

    # Gold joins only after all candidate captures have been sealed.
    gold_by_case = {
        case["case_id"]: [(row["doc_id"], int(row["node"])) for row in case["gold"]]
        for case in lock["cases"]
    }
    graded = []
    for row in product_rows:
        grade = ledger.grade_capture(
            row["capture"], gold_by_case[row["case_id"]],
            canonicalizer=ledger.index_article_root_canonicalizer(index))
        ledger.validate_graded_ledger(grade, expected_stage_ids=STAGES[row["arm_id"]])
        row["grade"] = grade
        final = grade["stages"][-1]
        row["gold_hits"] = final["gold_after"]
        row["gold_total"] = final["gold_total"]
        row["all_gold_hit"] = final["gold_after"] == final["gold_total"]
        graded.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-001.json"
    _write(ledger_path, experiment_ledger)

    corpus_total = _corpus_articles(index)
    summaries = {}
    for arm in ARMS:
        rows = [row for row in product_rows if row["arm_id"] == arm]
        counts = [len(row["final_coordinates"]) for row in rows]
        times = [row["elapsed_ms"] for row in rows]
        hits = sum(row["gold_hits"] for row in rows)
        total = sum(row["gold_total"] for row in rows)
        summaries[arm] = {
            "cases": len(rows), "gold_hits": hits, "gold_total": total,
            "golden_recall": hits / total,
            "all_gold_cases": sum(row["all_gold_hit"] for row in rows),
            "baseline_coordinates_lost": sum(not row["baseline_preserved"] for row in rows),
            "presented_total": sum(counts), "presented_mean": statistics.mean(counts),
            "presented_p50": statistics.median(counts),
            "presented_p95": _percentile(counts, .95),
            "selectivity": statistics.mean(counts) / corpus_total,
            "elapsed_ms_p50": statistics.median(times),
            "elapsed_ms_p95": _percentile(times, .95),
            "max_added": max(len(row["added_coordinates"]) for row in rows),
        }
    baseline_finals = {
        row["case_id"]: set(map(tuple, row["final_coordinates"]))
        for row in product_rows if row["arm_id"] == "baseline"
    }
    paired = {}
    for arm in ARMS[1:]:
        outcomes = {"candidate_only": 0, "baseline_only": 0,
                    "both": 0, "neither": 0}
        for row in [value for value in product_rows if value["arm_id"] == arm]:
            candidate = set(map(tuple, row["final_coordinates"]))
            baseline = baseline_finals[row["case_id"]]
            for gold in gold_by_case[row["case_id"]]:
                b, c = gold in baseline, gold in candidate
                key = "both" if b and c else "baseline_only" if b else \
                    "candidate_only" if c else "neither"
                outcomes[key] += 1
        paired[arm] = outcomes

    run_value = {
        "schema_version": "adr-0092-run-v1", "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_lock_sha256": _sha(lock_path), "llm_calls": 0,
        "gold_visible_to_candidate": False, "computed_post_selection": True,
        "corpus_article_roots": corpus_total, "rows": product_rows,
        "summary": summaries, "paired": paired,
        "stage_ledger": {"path": str(ledger_path.relative_to(ROOT)),
                         "sha256": _sha(ledger_path)},
    }
    run_path = adr / "artifacts/run-001.json"
    _write(run_path, run_value)

    for case in lock["cases"]:
        case_rows = [row for row in product_rows if row["case_id"] == case["case_id"]]
        lines = [
            f"# {case['case_id']} — ADR-0092 제한형 복구 probe", "",
            "## 1. 실행 메타", "",
            f"- case ID: `{case['case_id']}`", f"- run: `{RUN_ID}`",
            f"- arms: {', '.join(f'`{arm}`' for arm in ARMS)}",
            "- 실행 형식: 결정론 exact-coordinate probe; LLM 호출 0회", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "",
            "기준답변 대신 decisive canonical 좌표만 exact grader에 제공했다. "
            "모든 candidate capture 봉인 뒤에만 결합했다.", "",
            "```json", json.dumps(case["gold"], ensure_ascii=False, indent=2), "```", "",
            "## 4. 제품 입력을 구성한 원값", "",
            f"- baseline present: `{len(case['baseline_present'])}` coordinates",
            f"- D selected-only seeds: `{len(case['d_selected_only'])}` coordinates",
            "- feedback: `answer_incorrect=true`; 법령명·조문 위치 힌트 없음", "",
            "## Arm 결과", "",
            "| arm | final | gold | added | baseline 보존 | latency ms |",
            "|---|---:|---:|---:|---|---:|",
        ]
        for row in case_rows:
            lines.append(
                f"| `{row['arm_id']}` | {len(row['final_coordinates'])} | "
                f"{row['gold_hits']}/{row['gold_total']} | {len(row['added_coordinates'])} | "
                f"{row['baseline_preserved']} | {row['elapsed_ms']:.3f} |")
        lines.extend(["", "### 회수·탈락 단계 원장 — run·arm별", ""])
        for row in case_rows:
            lines.extend([
                f"### {row['arm_id']}", "", "```json",
                json.dumps({
                    "capture": row["capture"], "audit": row["audit"],
                    "final_coordinates": row["final_coordinates"],
                    "added_coordinates": row["added_coordinates"],
                }, ensure_ascii=False, indent=2), "```", "",
            ])
        lines.extend([
                      "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
                      "해당 없음. 제품 LLM 호출은 0회다.", "",
                      "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
                      "해당 없음. 중간 LLM 호출은 0회다.", "",
                      "## 7. 채점 호출과 반복 판정", "",
                      "LLM judge 없이 canonical exact join을 1회 수행했다.", "",
                      "```json",
                      json.dumps({row["arm_id"]: row["grade"] for row in case_rows},
                                 ensure_ascii=False, indent=2), "```", ""])
        best = max(case_rows, key=lambda row: row["gold_hits"])
        lines.extend([
            "## 8. 사례 최종 판정", "",
            f"최고 arm `{best['arm_id']}`은 decisive 좌표 "
            f"{best['gold_hits']}/{best['gold_total']}를 제시했다. "
            f"baseline 좌표 보존은 `{best['baseline_preserved']}`다.", "",
        ])
        qpath = adr / "실험" / f"질문-{case['number']:03d}-{case['case_id']}.md"
        qpath.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"run": str(run_path), "summary": summaries,
                      "paired": paired}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adr", type=Path, default=ROOT / "docs/adr/ADR-0092-bounded-companion-hop-governing-feedback")
    args = parser.parse_args()
    run(args.adr.resolve())


if __name__ == "__main__":
    main()
