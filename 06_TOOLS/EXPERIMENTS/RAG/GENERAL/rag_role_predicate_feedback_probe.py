#!/usr/bin/env python3
"""ADR-0094 deterministic role/predicate governing-law feedback probe."""
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
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import companion_recovery, index as index_mod  # noqa: E402
from lawrag.runtime import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0094"
EXPERIMENT_ID = "ADR-0094-experiment-v1"
RUN_ID = "run-002"
ARMS = ("baseline", "role-predicate-router")
STAGES = {
    "baseline": ["frozen-present", "present"],
    "role-predicate-router": [
        "frozen-present", "role-predicate-gate",
        "governing-hypothesis-resolve", "source-evidence-validate",
        "official-companion-expand", "present",
    ],
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_merkle(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(value for value in path.rglob("*") if value.is_file()):
        file_hash = _sha(item)
        # Match `sha256sum` lines from the frozen shell command.
        relative = item.relative_to(ROOT).as_posix()
        digest.update(f"{file_hash}  {relative}\n".encode("utf-8"))
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _coords(values: list[dict]) -> list[tuple[str, int]]:
    return [(str(value["doc_id"]), int(value["node"])) for value in values]


def _stage_after(source_row: dict, stage_id: str) -> list[tuple[str, int]]:
    stages = source_row["graded_trace"]["stage_ledger"]["stages"]
    stage = next(value for value in stages if value["stage_id"] == stage_id)
    return _coords(stage["after"])


def _questions(*datasets: dict) -> dict[str, str]:
    return {
        str(row["id"]): str(row["question"])
        for dataset in datasets for row in dataset["cases"]
    }


def _merge(
    floor: list[tuple[str, int]], additions: list[tuple[str, int]], cap: int,
) -> list[tuple[str, int]]:
    out = list(dict.fromkeys(floor))
    seen = set(out)
    for coordinate in additions:
        if coordinate in seen:
            continue
        if len(out) >= cap:
            break
        seen.add(coordinate)
        out.append(coordinate)
    return out


def _resolved_coordinates(meta: dict) -> list[tuple[str, int]]:
    out = []
    for card in meta.get("cards") or ():
        for hypothesis in card.get("hypotheses") or ():
            row = hypothesis.get("resolution") or {}
            if row.get("reason") == "resolved":
                coordinate = (str(row["doc_id"]), int(row["node"]))
                if coordinate not in out:
                    out.append(coordinate)
    return out


def _execute(index, public: dict, arm: str, preferred_document_ids: list[str]) -> dict:
    started = time.perf_counter()
    floor = list(public["present"])
    recorder = ledger.StageLedgerRecorder(
        public["case_id"], arm,
        ledger.index_article_root_canonicalizer(index))
    recorder.record_stage("frozen-present", "source", floor)
    audit = {"llm_calls": 0, "answer_incorrect": True, "location_hint": None}
    resolved: list[tuple[str, int]] = []
    validated: list[tuple[str, int]] = []
    if arm == "baseline":
        final = floor
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("frozen-present",))
    else:
        recorder.record_stage(
            "role-predicate-gate", "select", floor,
            parent_stage_ids=("frozen-present",))
        branches, meta = companion_recovery.role_predicate_governing_feedback(
            index, public["question"], answer_incorrect=True, exclude=floor,
            preferred_document_ids=preferred_document_ids,
            card_limit=2, addition_cap=4)
        no_feedback, no_feedback_meta = (
            companion_recovery.role_predicate_governing_feedback(
                index, public["question"], answer_incorrect=False,
                exclude=floor, preferred_document_ids=preferred_document_ids,
                card_limit=2, addition_cap=4))
        if no_feedback or no_feedback_meta.get("ran") is not False:
            raise AssertionError("router must remain closed without negative feedback")
        resolved = _resolved_coordinates(meta)
        validated = [row.coordinate for row in branches]
        hypotheses = _merge(floor, resolved, cap=len(floor) + len(resolved))
        recorder.record_stage(
            "governing-hypothesis-resolve", "retrieve", hypotheses,
            parent_stage_ids=("role-predicate-gate",))
        source_validated = _merge(
            floor, validated, cap=len(floor) + len(validated))
        recorder.record_stage(
            "source-evidence-validate", "filter", source_validated,
            parent_stage_ids=("governing-hypothesis-resolve",),
            discard_reasons={
                coordinate: "source_evidence_rejected"
                for coordinate in set(hypotheses) - set(source_validated)
            })
        bundle = source_validated
        recorder.record_stage(
            "official-companion-expand", "expand", bundle,
            parent_stage_ids=("source-evidence-validate",))
        final = _merge(floor, validated, cap=20)
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("official-companion-expand",),
            discard_reasons={
                coordinate: "final_cap_dropped"
                for coordinate in set(bundle) - set(final)
            })
        audit["router"] = meta
        audit["no_feedback_check"] = no_feedback_meta
    capture = recorder.capture()
    return {
        "case_id": public["case_id"],
        "number": public["number"],
        "suite": public["suite"],
        "arm_id": arm,
        "capture": capture,
        "audit": audit,
        "resolved_coordinates": [list(value) for value in resolved],
        "validated_coordinates": [list(value) for value in validated],
        "final_coordinates": [list(value) for value in final],
        "added_coordinates": [list(value) for value in final if value not in set(floor)],
        "baseline_preserved": all(value in final for value in floor),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "gold_visible_to_candidate": False,
    }


def _percentile(values: list[int | float], ratio: float) -> float:
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))])


def _question_markdown(public: dict, rows: list[dict], gold: list[tuple[str, int]]) -> str:
    baseline = next(row for row in rows if row["arm_id"] == "baseline")
    router = next(row for row in rows if row["arm_id"] == "role-predicate-router")
    return "\n".join([
        f"# {public['case_id']} — role-predicate feedback router", "",
        "## 1. 실행 메타", "",
        f"- case ID: `{public['case_id']}`",
        f"- run: `{RUN_ID}`",
        "- arms: `baseline`, `role-predicate-router`",
        "- feedback: `answer_incorrect=true`, location hint 없음",
        "- 제품·중간·judge LLM: 0회", "",
        "## 2. 사용자 질문 원문", "", public["question"], "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "",
        "서술형 기준답변은 candidate에 전달하지 않았다. 사후 exact gold 좌표:", "",
        "```json", json.dumps([
            {"doc_id": doc_id, "node": node} for doc_id, node in gold
        ], ensure_ascii=False, indent=2), "```", "",
        "## 4. 제품 입력을 구성한 원값", "",
        f"- baseline present: {len(public['present'])}",
        "- 허용: question, bare-negative, spot metadata, exact provision source",
        "- 금지: card body, gold, reference answer, general lexical search", "",
        "### 회수·탈락 단계 원장 — run·arm별", "",
        "정본은 `../artifacts/retrieval-stage-ledger-run-001.json`의 동일 case에 있다.", "",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
        "해당 없음. 제품 LLM 호출 0회.", "",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
        "`[]`", "",
        "## 7. 채점 호출과 반복 판정", "",
        "후보 봉인 뒤 canonical exact join을 1회 수행했다.", "",
        "## 8. 사례 최종 판정", "",
        "| arm | gold | final | added | baseline 보존 | latency ms |",
        "|---|---:|---:|---:|---|---:|",
        f"| baseline | {baseline['gold_hits']}/{baseline['gold_total']} | "
        f"{len(baseline['final_coordinates'])} | 0 | true | {baseline['elapsed_ms']:.3f} |",
        f"| role-predicate-router | {router['gold_hits']}/{router['gold_total']} | "
        f"{len(router['final_coordinates'])} | {len(router['added_coordinates'])} | "
        f"{str(router['baseline_preserved']).lower()} | {router['elapsed_ms']:.3f} |",
        "", "Router gold-free audit:", "", "```json",
        json.dumps(router["audit"], ensure_ascii=False, indent=2), "```", "",
    ])


def run(adr: Path) -> None:
    lock_path = adr / "artifacts/input-lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    expected_lock = "b2b6dba473dc7f9d6cd8e03ab152f3842ab9eb4f9a18099acf81a4ea561cbf48"
    if _sha(lock_path) != expected_lock:
        raise ValueError("input lock hash mismatch")
    for source in lock["sources"]:
        if _sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    for relative, expected in lock["directory_merkle"].items():
        if relative == "algorithm":
            continue
        if _directory_merkle(ROOT / relative) != expected:
            raise ValueError(f"directory merkle mismatch: {relative}")

    source_run = json.loads((ROOT / lock["sources"][0]["path"]).read_text("utf-8"))
    cm = json.loads((ROOT / lock["sources"][1]["path"]).read_text("utf-8"))
    fsc = json.loads((ROOT / lock["sources"][2]["path"]).read_text("utf-8"))
    delegation = json.loads((ROOT / lock["sources"][5]["path"]).read_text("utf-8"))
    preferred_document_ids = [
        str(value) for value in delegation["canonical_document_ids"]]
    question_by_case = _questions(cm, fsc)
    public_cases = [{
        "case_id": str(row["case_id"]),
        "number": int(row["number"]),
        "suite": str(row["suite"]),
        "question": question_by_case[str(row["case_id"])],
        "present": _stage_after(row, "present"),
    } for row in source_run["rows"]]
    if len(public_cases) != 61:
        raise ValueError("frozen case count mismatch")

    index = index_mod.current()
    product_rows = [
        _execute(index, public, arm, preferred_document_ids)
        for public in public_cases for arm in ARMS
    ]

    source_by_case = {row["case_id"]: row for row in source_run["rows"]}
    graded = []
    gold_by_case = {}
    for public in public_cases:
        gold = [
            (str(row["doc_id"]), int(row["node"]))
            for row in source_by_case[public["case_id"]]["gold_results"]
        ]
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
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-002.json"
    _write_json(ledger_path, experiment_ledger)

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
            "presented_total": sum(counts),
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
    candidate_rows = [row for row in product_rows if row["arm_id"] == "role-predicate-router"]
    new_gold = 0
    additions = 0
    activated_additions = []
    for row in candidate_rows:
        added = set(map(tuple, row["added_coordinates"]))
        additions += len(added)
        new_gold += len(added & set(gold_by_case[row["case_id"]]))
        if added:
            activated_additions.append(len(added))
    summaries["role-predicate-router"].update({
        "new_gold_in_additions": new_gold,
        "addition_precision": new_gold / additions if additions else 0.0,
        "added_per_activated_case_p95": (
            _percentile(activated_additions, .95) if activated_additions else 0.0),
        "no_feedback_open_count": 0,
        "general_lexical_search_calls": 0,
    })
    primary = next(row for row in candidate_rows if row["case_id"] == "fsc-hard-003")
    primary_gold = set(gold_by_case["fsc-hard-003"])
    summaries["primary_fsc_hard_003"] = {
        "resolved_hits": len(set(map(tuple, primary["resolved_coordinates"])) & primary_gold),
        "validated_hits": len(set(map(tuple, primary["validated_coordinates"])) & primary_gold),
        "final_hits": len(set(map(tuple, primary["final_coordinates"])) & primary_gold),
        "gold_total": len(primary_gold),
    }
    paired = {"candidate_only": 0, "baseline_only": 0, "both": 0, "neither": 0}
    for public in public_cases:
        base = set(map(tuple, next(row for row in product_rows
            if row["case_id"] == public["case_id"] and row["arm_id"] == "baseline")["final_coordinates"]))
        candidate = set(map(tuple, next(row for row in product_rows
            if row["case_id"] == public["case_id"] and row["arm_id"] == "role-predicate-router")["final_coordinates"]))
        for coordinate in gold_by_case[public["case_id"]]:
            b, c = coordinate in base, coordinate in candidate
            key = "both" if b and c else "baseline_only" if b else (
                "candidate_only" if c else "neither")
            paired[key] += 1

    run_value = {
        "schema_version": "adr-0094-run-v1", "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_lock_sha256": expected_lock, "llm_calls": 0,
        "gold_visible_to_candidate": False, "computed_post_selection": True,
        "corpus_article_roots": 16506, "summary": summaries,
        "paired": paired, "rows": product_rows,
        "stage_ledger": {"path": str(ledger_path.relative_to(ROOT)),
                         "sha256": _sha(ledger_path)},
    }
    run_path = adr / "artifacts/run-002.json"
    _write_json(run_path, run_value)

    experiment_dir = adr / "실험"
    for public in public_cases:
        rows = [row for row in product_rows if row["case_id"] == public["case_id"]]
        path = experiment_dir / f"질문-{public['number']:03d}-{public['case_id']}.md"
        path.write_text(
            _question_markdown(public, rows, gold_by_case[public["case_id"]]),
            encoding="utf-8")
    print(json.dumps({"run": str(run_path), "summary": summaries,
                      "paired": paired}, ensure_ascii=False, indent=2))


def main() -> None:
    run(ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0094-role-predicate-governing-law-feedback-router")


if __name__ == "__main__":
    main()
