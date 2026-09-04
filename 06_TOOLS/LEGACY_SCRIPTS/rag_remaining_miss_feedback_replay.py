#!/usr/bin/env python3
"""ADR-0096 replay the live feedback helper over every remaining V2 miss."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for key, relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "01_DATA/law_index.json"),
    ("RAG_ENGINE_RULES", "01_DATA/rules/engine.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.api.routers import rag  # noqa: E402
from lawrag.core.rag import index as index_mod, switches  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0096"
EXPERIMENT_ID = "ADR-0096-experiment-v1"
RUN_ID = "run-001"
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0096-remaining-miss-feedback-loop-replay"
ARMS = ("baseline", "remaining-miss-feedback-replay")
STAGES = {
    "baseline": ["frozen-present", "present"],
    "remaining-miss-feedback-replay": [
        "frozen-present", "feedback-gate", "governing-hypothesis-resolve",
        "source-evidence-validate", "present",
    ],
}
MUTABLE_IMPLEMENTATION = {"lawrag/api/routers/rag.py"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_merkle(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(value for value in path.rglob("*") if value.is_file()):
        digest.update(
            f"{_sha(item)}  {item.relative_to(ROOT).as_posix()}\n".encode())
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def _merge(*groups: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return list(dict.fromkeys(value for group in groups for value in group))


def _resolved(audit: dict) -> list[tuple[str, int]]:
    out = []
    for card in audit.get("cards") or ():
        for hypothesis in card.get("hypotheses") or ():
            row = hypothesis.get("resolution") or {}
            if row.get("reason") == "resolved":
                coordinate = (str(row["doc_id"]), int(row["node"]))
                if coordinate not in out:
                    out.append(coordinate)
    return out


def _closure_reason(recovery: dict) -> str:
    cards = recovery.get("audit", {}).get("cards") or []
    if recovery.get("selected"):
        return "validated_suggestion"
    if not cards:
        return "no_issue_card"
    if not recovery.get("audit", {}).get("predicate_families"):
        return "predicate_family_missing"
    if not any(card.get("actor_roles") for card in cards):
        return "actor_role_not_bound_to_card_trigger"
    if not any(card.get("gate_open") for card in cards):
        return "actor_predicate_gate_closed"
    hypotheses = [hypothesis for card in cards
                  for hypothesis in (card.get("hypotheses") or [])]
    if not any((row.get("resolution") or {}).get("reason") == "resolved"
               for row in hypotheses):
        return "provision_not_resolved"
    if not any((row.get("validation") or {}).get("accepted")
               for row in hypotheses):
        return "source_evidence_rejected"
    return "validated_but_excluded_or_duplicate"


def _execute(index, public: dict, arm: str) -> dict:
    started = time.perf_counter()
    floor = list(public["present"])
    recorder = ledger.StageLedgerRecorder(
        public["case_id"], arm,
        ledger.index_article_root_canonicalizer(index))
    recorder.record_stage("frozen-present", "source", floor)
    recovery = None
    resolved: list[tuple[str, int]] = []
    validated: list[tuple[str, int]] = []
    if arm == "baseline":
        final = floor
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("frozen-present",))
        reason = "baseline"
    else:
        recorder.record_stage(
            "feedback-gate", "select", floor,
            parent_stage_ids=("frozen-present",))
        recovery = rag._role_predicate_feedback_recovery(index, {
            "질의": public["question"],
            "context": [{"doc_id": doc_id, "node": node}
                        for doc_id, node in floor],
        })
        resolved = _resolved(recovery.get("audit") or {})
        hypotheses = _merge(floor, resolved)
        recorder.record_stage(
            "governing-hypothesis-resolve", "retrieve", hypotheses,
            parent_stage_ids=("feedback-gate",))
        validated = [(str(row["doc_id"]), int(row["node"]))
                     for row in recovery.get("selected") or ()]
        source_validated = _merge(floor, validated)
        recorder.record_stage(
            "source-evidence-validate", "filter", source_validated,
            parent_stage_ids=("governing-hypothesis-resolve",),
            discard_reasons={
                coordinate: "source_evidence_rejected"
                for coordinate in set(hypotheses) - set(source_validated)
            })
        final = source_validated
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("source-evidence-validate",))
        reason = _closure_reason(recovery)
    return {
        "case_id": public["case_id"], "number": public["number"],
        "suite": public["suite"], "arm_id": arm,
        "capture": recorder.capture(),
        "input": {"question": public["question"], "verdict": "오답",
                  "expected": None, "stored_context": [list(row) for row in floor]},
        "recovery": recovery,
        "closure_reason": reason,
        "resolved_coordinates": [list(row) for row in resolved],
        "validated_coordinates": [list(row) for row in validated],
        "final_coordinates": [list(row) for row in final],
        "added_coordinates": [list(row) for row in final if row not in set(floor)],
        "baseline_preserved": all(row in final for row in floor),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "gold_visible_to_candidate": False,
    }


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1,
                             round((len(ordered) - 1) * ratio))])


def _question_markdown(public: dict, rows: list[dict], gold: list[tuple[str, int]]) -> str:
    baseline = next(row for row in rows if row["arm_id"] == "baseline")
    candidate = next(row for row in rows
                     if row["arm_id"] == "remaining-miss-feedback-replay")
    missing = [row for row in gold if row not in set(public["present"])]
    return "\n".join([
        f"# {public['case_id']} — remaining-miss feedback replay", "",
        "## 1. 실행 메타", "", f"- case ID: `{public['case_id']}`",
        f"- run: `{RUN_ID}`", "- arms: `baseline`, `remaining-miss-feedback-replay`",
        "- feedback: `verdict=오답`, expected 위치 없음", "- 제품·중간·judge LLM: 0회", "",
        "## 2. 사용자 질문 원문", "", public["question"], "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "",
        "서술형 기준답변은 후보에 전달하지 않았다. 후보 봉인 뒤 결합한 current gold와 missing:", "",
        "```json", json.dumps({"gold": [list(row) for row in gold],
                                "missing_before_feedback": [list(row) for row in missing]},
                               ensure_ascii=False, indent=2), "```", "",
        "## 4. 제품 입력을 구성한 원값", "",
        f"- stored present: {len(public['present'])}",
        "- 허용: question, bare-negative, spot metadata, exact source article, current generation",
        "- 금지: gold, reference answer, missing coordinates, card body, general lexical search", "",
        "### 회수·탈락 단계 원장 — run·arm별", "",
        "정본: `../artifacts/retrieval-stage-ledger-run-001.json`의 동일 case.", "",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문", "", "해당 없음. 제품 LLM 0회.", "",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "", "`[]`", "",
        "## 7. 채점 호출과 반복 판정", "", "후보 snapshot을 봉인한 뒤 current gold exact join 1회.", "",
        "## 8. 사례 최종 판정", "",
        "| arm | gold | final union | added | baseline 보존 | latency ms |",
        "|---|---:|---:|---:|---|---:|",
        f"| baseline | {baseline['gold_hits']}/{baseline['gold_total']} | {len(baseline['final_coordinates'])} | 0 | true | {baseline['elapsed_ms']:.3f} |",
        f"| remaining-miss-feedback-replay | {candidate['gold_hits']}/{candidate['gold_total']} | {len(candidate['final_coordinates'])} | {len(candidate['added_coordinates'])} | {str(candidate['baseline_preserved']).lower()} | {candidate['elapsed_ms']:.3f} |",
        "", f"- 직접 폐쇄 원인: `{candidate['closure_reason']}`", "",
        "Gold-free API recovery audit:", "", "```json",
        json.dumps(candidate["recovery"], ensure_ascii=False, indent=2), "```", "",
    ])


def main() -> None:
    lock_path = ADR / "artifacts/input-lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    expected_lock = "d09bb34dd281d997ecb766d7b17de877b499c59a7f0a8f4c37be34e0c783534d"
    if _sha(lock_path) != expected_lock:
        raise ValueError("input lock hash mismatch")
    for source in lock["sources"]:
        if source["path"] in MUTABLE_IMPLEMENTATION:
            continue
        if _sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    for relative, expected in lock["directory_merkle"].items():
        if _directory_merkle(ROOT / relative) != expected:
            raise ValueError(f"directory merkle mismatch: {relative}")

    parent = json.loads((ROOT / lock["sources"][0]["path"]).read_text("utf-8"))
    cm = json.loads((ROOT / lock["sources"][3]["path"]).read_text("utf-8"))
    fsc = json.loads((ROOT / lock["sources"][4]["path"]).read_text("utf-8"))
    questions = {str(row["id"]): str(row["question"])
                 for dataset in (cm, fsc) for row in dataset["cases"]}
    selected_ids = lock["selection"]["case_ids"]
    source_rows = {row["case_id"]: row for row in parent["rows"]
                   if row["arm_id"] == "role-predicate-router"}
    public_cases = [{
        "case_id": case_id, "number": number,
        "suite": "fsc" if case_id.startswith("fsc-") else "cm",
        "question": questions[case_id],
        "present": [(str(doc), int(node)) for doc, node
                    in source_rows[case_id]["final_coordinates"]],
    } for number, case_id in enumerate(selected_ids, 1)]
    if len(public_cases) != 16:
        raise ValueError("frozen selection must contain 16 cases")

    index = index_mod.current()
    if not switches.is_on("role_predicate_feedback_recovery"):
        raise ValueError("current feedback recovery user override is not enabled")
    product_rows = [_execute(index, public, arm)
                    for public in public_cases for arm in ARMS]

    gold_by_case: dict[str, list[tuple[str, int]]] = {}
    graded = []
    for public in public_cases:
        gold = [(str(row["doc_id"]), int(row["node"]))
                for row in source_rows[public["case_id"]]["grade"]["gold_identities"]]
        gold_by_case[public["case_id"]] = gold
        for arm in ARMS:
            row = next(value for value in product_rows
                       if value["case_id"] == public["case_id"]
                       and value["arm_id"] == arm)
            grade = ledger.grade_capture(
                row["capture"], gold,
                canonicalizer=ledger.index_article_root_canonicalizer(index))
            ledger.validate_graded_ledger(grade, expected_stage_ids=STAGES[arm])
            row["grade"] = grade
            row["gold_hits"] = grade["stages"][-1]["gold_after"]
            row["gold_total"] = len(gold)
            graded.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    ledger_path = ADR / "artifacts/retrieval-stage-ledger-run-001.json"
    _write_json(ledger_path, experiment_ledger)

    summaries = {}
    for arm in ARMS:
        rows = [row for row in product_rows if row["arm_id"] == arm]
        counts = [len(row["final_coordinates"]) for row in rows]
        times = [row["elapsed_ms"] for row in rows]
        hits, total = sum(row["gold_hits"] for row in rows), sum(row["gold_total"] for row in rows)
        summaries[arm] = {
            "cases": len(rows), "gold_hits": hits, "gold_total": total,
            "golden_recall": hits / total, "presented_total": sum(counts),
            "presented_mean": statistics.mean(counts),
            "presented_p50": statistics.median(counts),
            "presented_p95": _percentile(counts, .95),
            "selectivity": statistics.mean(counts) / 16506,
            "elapsed_ms_p50": statistics.median(times),
            "elapsed_ms_p95": _percentile(times, .95),
            "baseline_coordinates_lost": sum(not row["baseline_preserved"] for row in rows),
            "activated_cases": sum(bool(row["added_coordinates"]) for row in rows),
            "added_total": sum(len(row["added_coordinates"]) for row in rows),
        }
    candidates = [row for row in product_rows
                  if row["arm_id"] == "remaining-miss-feedback-replay"]
    additions = sum(len(row["added_coordinates"]) for row in candidates)
    new_gold = sum(len(set(map(tuple, row["added_coordinates"]))
                       & set(gold_by_case[row["case_id"]])) for row in candidates)
    reasons = {}
    for row in candidates:
        reasons[row["closure_reason"]] = reasons.get(row["closure_reason"], 0) + 1
    summaries["remaining-miss-feedback-replay"].update({
        "new_gold_in_additions": new_gold,
        "addition_precision": new_gold / additions if additions else 0.0,
        "closure_reason_counts": reasons,
        "general_lexical_search_calls": sum(
            (row.get("recovery") or {}).get("audit", {}).get(
                "general_lexical_search_calls", 0) for row in candidates),
        "forbidden_fields_used": sorted({value for row in candidates
            for value in ((row.get("recovery") or {}).get("audit", {}).get(
                "forbidden_fields_used") or [])}),
    })
    paired = {"candidate_only": 0, "baseline_only": 0, "both": 0, "neither": 0}
    for public in public_cases:
        base = set(map(tuple, next(row for row in product_rows
            if row["case_id"] == public["case_id"] and row["arm_id"] == "baseline")["final_coordinates"]))
        candidate = set(map(tuple, next(row for row in product_rows
            if row["case_id"] == public["case_id"] and row["arm_id"] == "remaining-miss-feedback-replay")["final_coordinates"]))
        for coordinate in gold_by_case[public["case_id"]]:
            b, c = coordinate in base, coordinate in candidate
            paired["both" if b and c else "baseline_only" if b else
                   "candidate_only" if c else "neither"] += 1

    run_value = {
        "schema_version": "adr-0096-run-v1", "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_lock_sha256": expected_lock, "llm_calls": 0,
        "gold_visible_to_candidate": False, "computed_post_selection": True,
        "corpus_article_roots": 16506, "selection": lock["selection"],
        "summary": summaries, "paired": paired, "rows": product_rows,
        "stage_ledger": {"path": str(ledger_path.relative_to(ROOT)),
                         "sha256": _sha(ledger_path)},
        "code_hashes": {
            path: _sha(ROOT / path) for path in (
                "lawrag/api/routers/rag.py", "lawrag/core/rag/companion_recovery.py",
                "scripts/rag_remaining_miss_feedback_replay.py")},
    }
    run_path = ADR / "artifacts/run-001.json"
    _write_json(run_path, run_value)
    for public in public_cases:
        rows = [row for row in product_rows if row["case_id"] == public["case_id"]]
        path = ADR / "실험" / f"질문-{public['number']:03d}-{public['case_id']}.md"
        path.write_text(
            _question_markdown(public, rows, gold_by_case[public["case_id"]]),
            encoding="utf-8")
    print(json.dumps({"run": str(run_path.relative_to(ROOT)),
                      "summary": summaries, "paired": paired},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
