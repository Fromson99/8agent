#!/usr/bin/env python3
"""ADR-0103 deterministic 16-case semantic-entity search replay.

Candidate selection receives only the question and the frozen ADR-0101 final
coordinates.  Decisive gold is joined only after all product captures have
been sealed.  No product or evaluator model is called.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
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

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legal_graph_store, legal_semantic_search  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0103"
EXPERIMENT_ID = "ADR-0103-experiment-v1"
RUN_ID = "run-007"
ARMS = ("baseline", "semantic-pipeline")
CASE_IDS = (
    "cm-004", "cm-008", "cm-011", "cm-016", "cm-025", "cm-030",
    "cm-031", "cm-033", "cm-039", "cm-043", "cm-048", "cm-049",
    "cm-050", "fsc-hard-004", "fsc-hard-006", "fsc-hard-009",
)
STAGES = {
    "baseline": ["baseline-source", "baseline-present"],
    "semantic-pipeline": [
        "candidate-source", "semantic-landing", "candidate-union",
        "typed-closure", "bundle-rerank", "candidate-present",
    ],
}
SOURCES = {
    "input_lock": ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0091-legalclosure-v2-article-reachability-ledger/artifacts/input-lock.json",
    "parent_run": ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0101-legal-graph-runtime-consumer-hardening/artifacts/run-001.json",
    "cm": ROOT / "01_DATA/review/cm_core_e2e_v2.json",
    "fsc": ROOT / "01_DATA/review/fsc_hard_retrieval_v2.json",
}
EXPECTED = {
    "input_lock": "7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452",
    "parent_run": "9bed6f51820ea12f633e9c5cf849ccb98041e8101aa222b9d05b11f9d8d4e91c",
    "cm": "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    "fsc": "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
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


def _coordinates(values) -> list[tuple[str, int]]:
    result = []
    for value in values:
        if isinstance(value, dict):
            result.append((str(value["doc_id"]), int(value["node"])))
        else:
            result.append((str(value[0]), int(value[1])))
    return list(dict.fromkeys(result))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _public_and_gold() -> tuple[list[dict], dict[str, list[tuple[str, int]]]]:
    lock = json.loads(SOURCES["input_lock"].read_text("utf-8"))
    parent = json.loads(SOURCES["parent_run"].read_text("utf-8"))
    locked = {str(row["id"]): row for row in lock["cases"]}
    baseline = {
        str(row["case_id"]): _coordinates(row["final_coordinates"])
        for row in parent["rows"]
        if row["arm_id"] == "hardened-graph-closure"
    }
    public, gold = [], {}
    for number, case_id in enumerate(CASE_IDS, 1):
        row = locked[case_id]
        public.append({
            "case_id": case_id,
            "number": number,
            "suite": str(row["suite"]),
            "question": str(row["question"]),
            "baseline": baseline[case_id],
        })
        gold[case_id] = _coordinates([
            value for value in row["gold_articles"]
            if value.get("corpus_status") == "present"
        ])
    return public, gold


def _discard_reasons(before, after, default: str):
    after_set = set(after)
    return [(coordinate, default) for coordinate in before if coordinate not in after_set]


def _execute(case: dict, arm: str, index, snapshot) -> dict:
    started = time.perf_counter()
    source = list(case["baseline"])
    recorder = ledger.StageLedgerRecorder(
        case["case_id"], arm, ledger.identity_canonicalizer,
    )
    if arm == "baseline":
        final = source
        recorder.record_stage("baseline-source", "source", source)
        recorder.record_stage(
            "baseline-present", "present", final,
            parent_stage_ids=("baseline-source",),
        )
        meta = {
            "status": "frozen-parent", "active_family_ids": [],
            "legal_assessments": [], "stages": {},
        }
    else:
        recorder.record_stage("candidate-source", "source", source)
        selected, meta = legal_semantic_search.plan_semantic_coordinates(
            index, case["question"], source, snapshot=snapshot, cap=20,
        )
        final = _coordinates([row["coordinate"] for row in selected])
        stages = {
            key: _coordinates(value)
            for key, value in (meta.get("stages") or {}).items()
        }
        landing_union = list(dict.fromkeys(
            source + stages.get("semantic-landing", [])
        ))
        recorder.record_stage(
            "semantic-landing", "retrieve", landing_union,
            parent_stage_ids=("candidate-source",),
        )
        union = stages.get("candidate-union", landing_union)
        recorder.record_stage(
            "candidate-union", "union", union,
            parent_stage_ids=("candidate-source", "semantic-landing"),
        )
        closure = stages.get("typed-closure", union)
        recorder.record_stage(
            "typed-closure", "expand", closure,
            parent_stage_ids=("candidate-union",),
            discard_reasons=_discard_reasons(
                union, closure, "not_in_typed_closure_candidate_set",
            ),
        )
        recorder.record_stage(
            "bundle-rerank", "rerank", final,
            parent_stage_ids=("typed-closure",),
            discard_reasons=_discard_reasons(
                closure, final, "not_selected_by_bounded_bundle_rerank",
            ),
        )
        recorder.record_stage(
            "candidate-present", "present", final,
            parent_stage_ids=("bundle-rerank",),
        )
    return {
        "case_id": case["case_id"],
        "number": case["number"],
        "suite": case["suite"],
        "question": case["question"],
        "arm_id": arm,
        "capture": recorder.capture(),
        "source_coordinates": [list(value) for value in source],
        "final_coordinates": [list(value) for value in final],
        "added_coordinates": [list(value) for value in final if value not in set(source)],
        "lost_source_coordinates": [
            list(value) for value in source if value not in set(final)
        ],
        "search": meta,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "planning_elapsed_ms": float(meta.get("elapsed_ms") or 0.0),
        "gold_visible_to_candidate": False,
    }


def _question_markdown(case: dict, rows: list[dict], gold) -> str:
    baseline = next(row for row in rows if row["arm_id"] == "baseline")
    candidate = next(row for row in rows if row["arm_id"] == "semantic-pipeline")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        row["arm_id"]: {
            "source_coordinates": row["source_coordinates"],
            "final_coordinates": row["final_coordinates"],
            "gold_hits": row["gold_hits"],
            "gold_total": row["gold_total"],
            "elapsed_ms": row["elapsed_ms"],
            "planning_elapsed_ms": row["planning_elapsed_ms"],
        }
        for row in rows
    }
    return f"""# 질문 {case['number']:03d} — {case['case_id']}

## 1. 실행 메타

- ADR/experiment/run: `{ADR_ID}` / `{EXPERIMENT_ID}` / `{RUN_ID}`
- 실행 시각(UTC): `{now}`
- 원본 상태: `exact`
- 실행 arm: `baseline`, `semantic-pipeline`
- 제품·중간·채점 LLM 호출: `[]`
- gold visible to candidate: `false`

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```json
{json.dumps([list(value) for value in gold], ensure_ascii=False)}
```

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

```json
{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
[]
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

```json
{{"mode":"deterministic exact-coordinate grader","judge_calls":[]}}
```

## 8. 사례 최종 판정

- 원장: `artifacts/retrieval-stage-ledger-{RUN_ID}.json`
- baseline: `{baseline['gold_hits']}/{baseline['gold_total']}`
- semantic-pipeline: `{candidate['gold_hits']}/{candidate['gold_total']}`
- 신규 정답 좌표: `{candidate['candidate_only']}`
- 회귀 좌표: `{candidate['baseline_only']}`
- LegalAssessment: `{len(candidate['search'].get('legal_assessments') or [])}`건
"""


def run(adr: Path, graph_root: Path) -> dict:
    started = time.perf_counter()
    for key, path in SOURCES.items():
        actual = _sha(path)
        if actual != EXPECTED[key]:
            raise ValueError(f"frozen source hash mismatch: {key} {actual}")
    public_cases, gold_by_case = _public_and_gold()
    index = index_mod.Index.load()
    legal_graph_store.reset_cache()
    load = legal_graph_store.current_for(index, root=graph_root)
    if load.snapshot is None:
        raise ValueError(f"Legal Graph snapshot unavailable: {load.as_dict()}")
    snapshot = load.snapshot

    product_rows = [
        _execute(case, arm, index, snapshot)
        for case in public_cases for arm in ARMS
    ]
    # Product selection is sealed.  Gold joins only below this line.
    graded = []
    base_by_case = {
        row["case_id"]: row for row in product_rows if row["arm_id"] == "baseline"
    }
    for row in product_rows:
        gold = gold_by_case[row["case_id"]]
        grade = ledger.grade_capture(
            row["capture"], gold, canonicalizer=ledger.identity_canonicalizer,
        )
        ledger.validate_graded_ledger(
            grade, expected_stage_ids=STAGES[row["arm_id"]],
        )
        row["grade"] = grade
        row["gold_hits"] = grade["stages"][-1]["gold_after"]
        row["gold_total"] = len(gold)
        baseline_set = {
            tuple(value) for value in base_by_case[row["case_id"]]["final_coordinates"]
        }
        final_set = {tuple(value) for value in row["final_coordinates"]}
        row["candidate_only"] = [
            list(value) for value in gold
            if value not in baseline_set and value in final_set
        ]
        row["baseline_only"] = [
            list(value) for value in gold
            if value in baseline_set and value not in final_set
        ]
        graded.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger],
    )
    ledger_path = adr / f"artifacts/retrieval-stage-ledger-{RUN_ID}.json"
    _write(ledger_path, experiment_ledger)

    by_arm_rows = {
        arm: [row for row in product_rows if row["arm_id"] == arm]
        for arm in ARMS
    }
    by_arm = {}
    for arm, rows in by_arm_rows.items():
        hits = sum(row["gold_hits"] for row in rows)
        total = sum(row["gold_total"] for row in rows)
        planning = [row["planning_elapsed_ms"] for row in rows]
        by_arm[arm] = {
            "cases": len(rows),
            "gold_hits": hits,
            "gold_total": total,
            "golden_recall": hits / total,
            "all_gold_cases": sum(
                row["gold_hits"] == row["gold_total"] for row in rows
            ),
            "presented_total": sum(len(row["final_coordinates"]) for row in rows),
            "presented_max": max(len(row["final_coordinates"]) for row in rows),
            "added_total": sum(len(row["added_coordinates"]) for row in rows),
            "source_lost_total": sum(
                len(row["lost_source_coordinates"]) for row in rows
            ),
            "planning_p50_ms": statistics.median(planning),
            "planning_p95_ms": _percentile(planning, 0.95),
            "cap_20_passed": all(
                len(row["final_coordinates"]) <= 20 for row in rows
            ),
        }

    candidate_rows = by_arm_rows["semantic-pipeline"]
    semantic_counts = json.loads(
        (graph_root / "generations" / snapshot.generation_id / "manifest.json")
        .read_text("utf-8")
    )["counts"]["semantic_entities_by_type"]
    paired = {
        "candidate_only": sum(len(row["candidate_only"]) for row in candidate_rows),
        "baseline_only": sum(len(row["baseline_only"]) for row in candidate_rows),
    }
    paired["both"] = by_arm["baseline"]["gold_hits"] - paired["baseline_only"]
    paired["neither"] = (
        by_arm["baseline"]["gold_total"] - paired["both"]
        - paired["baseline_only"] - paired["candidate_only"]
    )
    reason_counts = Counter()
    assessment_count = 0
    for row in candidate_rows:
        reason_counts.update(row["search"].get("reason_counts") or {})
        assessment_count += len(row["search"].get("legal_assessments") or [])
    success_checks = {
        "candidate_at_least_20_of_29": by_arm["semantic-pipeline"]["gold_hits"] >= 20,
        "net_gain_at_least_8": (
            by_arm["semantic-pipeline"]["gold_hits"]
            - by_arm["baseline"]["gold_hits"] >= 8
        ),
        "baseline_hit_loss_zero": paired["baseline_only"] == 0,
        "cap_20": by_arm["semantic-pipeline"]["cap_20_passed"],
        "all_16_family_active": sum(
            bool(row["search"].get("active_family_ids")) for row in candidate_rows
        ) == 16,
        "all_eight_semantic_types_materialized": (
            len(semantic_counts) == 8 and all(semantic_counts.values())
        ),
        "planning_p95_at_most_50ms": (
            by_arm["semantic-pipeline"]["planning_p95_ms"] <= 50
        ),
        "llm_zero": True,
        "gold_hidden": all(row["gold_visible_to_candidate"] is False for row in product_rows),
    }
    summary = {
        "graph_generation": snapshot.generation_id,
        "graph_content_sha256": snapshot.content_sha256,
        "graph_cards": len(snapshot.ports_by_article),
        "semantic_cards": len(snapshot.semantic_cards),
        "semantic_entities_by_type": semantic_counts,
        "cold_load_ms": snapshot.load_ms,
        "by_arm": by_arm,
        "paired": paired,
        "active_family_cases": sum(
            bool(row["search"].get("active_family_ids")) for row in candidate_rows
        ),
        "assessment_count": assessment_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "success_checks": success_checks,
        "passed": all(success_checks.values()),
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    run_value = {
        "schema_version": "adr-0103-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_hashes": {key: _sha(path) for key, path in SOURCES.items()},
        "graph_pointer_sha256": _sha(graph_root / "CURRENT.json"),
        "graph_manifest_sha256": _sha(
            graph_root / "generations" / snapshot.generation_id / "manifest.json"
        ),
        "computed_post_selection": True,
        "gold_visible_to_candidate": False,
        "product_calls": 0,
        "judge_calls": 0,
        "load": load.as_dict(),
        "summary": summary,
        "rows": product_rows,
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": _sha(ledger_path),
        },
    }
    run_path = adr / f"artifacts/{RUN_ID}.json"
    _write(run_path, run_value)

    rows_by_case = {
        case["case_id"]: [
            row for row in product_rows if row["case_id"] == case["case_id"]
        ]
        for case in public_cases
    }
    for case in public_cases:
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['case_id']}.md"
        )
        question_path.write_text(
            _question_markdown(
                case, rows_by_case[case["case_id"]], gold_by_case[case["case_id"]],
            ),
            encoding="utf-8",
        )
    return {"run": str(run_path), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adr", type=Path,
        default=ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0103-legal-semantic-entity-search-pipeline",
    )
    parser.add_argument(
        "--graph-root", type=Path,
        default=ROOT / "tmp/adr0103-build-a",
    )
    args = parser.parse_args()
    print(json.dumps(
        run(args.adr.resolve(), args.graph_root.resolve()),
        ensure_ascii=False, sort_keys=True,
    ))


if __name__ == "__main__":
    main()
