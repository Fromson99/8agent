#!/usr/bin/env python3
"""ADR-0123: deterministically regrade ADR-0121 final-present coordinates."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0123-deterministic-retrieval-regrade-golden-61"
PARENT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0121-claimwise-nondestructive-legal-compiler-golden-61"
PARENT_ARTIFACTS = PARENT / "artifacts"
PARENT_RUN = PARENT_ARTIFACTS / "run-001.json"
PARENT_SEAL = PARENT_ARTIFACTS / "product-capture-seal-run-001.json"
PARENT_PUBLIC = PARENT_ARTIFACTS / "public-questions-run-001.json"
PARENT_SCORING = PARENT_ARTIFACTS / "scoring-fixture-run-001.json"
PARENT_LEDGER = PARENT_ARTIFACTS / "retrieval-stage-ledger-run-001.json"
PARENT_CAPTURES = PARENT_ARTIFACTS / "product-captures/run-001"
RUN_PATH = ADR / "artifacts/run-001.json"
MANIFEST_PATH = ADR / "실험/manifest.json"
ARTIFACT_MANIFEST_PATH = ADR / "artifacts/manifest.json"

SOURCE_ARM = "claimwise-nondestructive-v2"
EXPECTED_HASHES = {
    PARENT_RUN: "ca19df11109c034c8d18ce52aea0c635ef41836cd1dd90de5a07852f65e2870c",
    PARENT_SEAL: "0474cd37239fef8b54fa50f0cf534679e772d34d3b952100003aced1a4cd8db6",
    PARENT_SCORING: "cee5da071c65ee7bb59db908896d9eed57ea0767b6d5a7e2e40a4cb63d80f4a2",
    PARENT_LEDGER: "0e60ff091e1f0751c337efd14122d3ee4c3ac6198be912a1f8ae74333d48090c",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf-8")


def _self_hash(value: Mapping[str, Any]) -> str:
    payload = {key: child for key, child in value.items() if key != "artifact_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _replace_question_scaffold(path: Path, text: str) -> None:
    if not path.exists():
        raise RuntimeError(f"generated question scaffold is missing: {path}")
    current = path.read_text(encoding="utf-8")
    if "TODO" not in current or not current.startswith("# 질문 "):
        raise RuntimeError(f"refusing to overwrite non-scaffold question: {path}")
    path.write_text(text, encoding="utf-8")


def _artifact(path: Path, description: str) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "description": description,
        "contains_raw_prompts_and_outputs": False,
    }


def _coord_text(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "- 없음"
    return "\n".join(
        f"- `{row['doc_id']}:{row['node']}`"
        + (f" — {row.get('law')} {row.get('article')}" if row.get("law") else "")
        for row in rows
    )


def _question_markdown(
    public: Mapping[str, Any], score: Mapping[str, Any],
    inherited: Mapping[str, Any], fresh: Mapping[str, Any],
    presented: list[Mapping[str, Any]], capture_path: Path, capture_sha: str,
) -> str:
    outcome = "통과" if fresh["all_expected_present"] else "누락"
    return f"""# {public['case_id']} 결정론적 필수 조문 회수 재채점

## 1. 실행 메타

- run: `run-001`
- source: `ADR-0121-experiment-v1/{SOURCE_ARM}`
- source capture: `{capture_path.relative_to(ROOT)}`
- source capture SHA-256: `{capture_sha}`
- 제품 호출: `0`
- judge 호출: `0`
- 채점 규칙: `expected_articles subset_of final_present_coordinates`

## 2. 사용자 질문 원문

{public['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

이 재채점은 기준답변 문장을 사용하지 않는다. 기대 조문 좌표만 offline에서 사용한다.

## 4. 제품 입력을 구성한 원값

제품 입력과 retrieval은 ADR-0121의 봉인 capture를 변경 없이 상속했다. 새 제품·중간 LLM
호출은 없다. 채점 대상은 stage ledger의 마지막 `present` 집합뿐이다.

- final presented: `{fresh['presented_count']}`개
- stage capture SHA-256: `{fresh['stage_capture_sha256']}`

### 회수·탈락 단계 원장 — run·arm별

- inherited ledger: `{PARENT_LEDGER.relative_to(ROOT)}`
- inherited ledger SHA-256: `{EXPECTED_HASHES[PARENT_LEDGER]}`
- stage: final `present`
- gold visible to product: `false`
- gold는 봉인된 제품 선택 완료 뒤 offline에서만 결합했다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

새 호출 없음. 원 호출 payload는 위 source capture hash로 계보 연결한다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

없음.

## 7. 채점 호출과 반복 판정

- judge 호출 없음. 아래 결과는 단일 결정론 set-containment 판정이다.
- 판정: **{outcome}**
- 기대 조문 hit: `{fresh['expected_hit_count']}/{fresh['expected_total']}`
- required companion: `{fresh['companion_hit_count']}/{fresh['companion_total']}`
- inherited 결과와 exact equality: `{fresh['matches_inherited']}`

### 기대 조문

{_coord_text(list(score['gold_articles']))}

### 누락 기대 조문

{_coord_text(list(fresh['missing_expected']))}

### 최종 제시 좌표

{_coord_text(presented)}

## 8. 사례 최종 판정

- baseline(inherited): `{inherited['gold_hits']}/{inherited['gold_total']}`, all=`{inherited['all_gold_hit']}`
- deterministic-retrieval-only: `{fresh['expected_hit_count']}/{fresh['expected_total']}`, all=`{fresh['all_expected_present']}`
- failure type: `{'none' if fresh['all_expected_present'] else 'retrieval_miss'}`
"""


def _experiment_index(
    run_artifact: Mapping[str, Any], manifest: Mapping[str, Any],
) -> str:
    rows = []
    by_id = {str(row["case_id"]): row for row in run_artifact["rows"]}
    for question in manifest["questions"]:
        row = by_id[str(question["case_id"])]
        fresh = row["deterministic"]
        mark = "통과" if fresh["all_expected_present"] else "누락"
        rows.append(
            f"| {int(question['number']):03d} | `{question['case_id']}` | `run-001` | "
            f"`{fresh['expected_hit_count']}/{fresh['expected_total']}` {mark} | "
            f"exact-match | `{row['failure_type']}` | "
            f"[{question['file']}]({question['file']}) |"
        )
    return """# ADR-0123 실험 질문 인덱스

> ADR-0121의 봉인 제품 결과를 재사용하며 새 제품·중간·judge LLM 호출은 없다.

## 작업 선점

- owner: `Codex-root`
- scope: Golden 61 final-present expected-article deterministic regrade
- scope key: `deterministic-retrieval-regrade-golden-61`
- created at: `{created}`
- status: `in_progress`

## 계보

- experiment ID: `ADR-0123-experiment-v1`
- branch: `retrieval-regrade`
- parent arm: `ADR-0121-experiment-v1/claimwise-nondestructive-v2`
- 변경 가설: final-present set containment로 LLM 없이 회수 성능을 안정적으로 재현한다.

## 병합

- merge: 해당 없음

## 다른 ADR과의 관계

- 관련 ADR: 없음

## Arm

| arm ID | 역할 | 직접 부모 | 바뀐 것 | 고정한 것 |
|---|---|---|---|---|
| `baseline` | baseline | ADR-0121 candidate | 저장된 retrieval 집계 | 61문항·90좌표·final present |
| `deterministic-retrieval-only` | candidate | baseline | raw capture set-containment 재계산 | source hash·case order·좌표 단위 |

## 질문 인덱스

| 번호 | case ID | run | arm별 판정 | paired 분류 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
{rows}

## 집계

- phase: `audit`
- in-sample: `true`
- run 상태: `run-001 / complete`
- 조문 recall: `77/90` (85.56%)
- 질문 완전회수: `50/61` (81.97%)
- fresh/inherited exact match: `61/61`
- judge 호출·불일치: `0 / 0`

## 단계별 회수·탈락 집계

| run | arm | stage | kind | 후보 before→after | gold before→after | gold gain/loss | micro recall | 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---|
| `run-001` | `deterministic-retrieval-only` | `present` | inherited | 1,708→1,708 | 77→77 | 0/0 | 85.56% | ADR-0121 ledger 상속 |

질문별 exact 좌표와 누락 receipt는 각 질문 파일에, 기계 판독 집계는
[run-001.json](../artifacts/run-001.json)에 있다.
""".format(
        created=manifest["reservation"]["created_at"],
        rows="\n".join(rows),
    )


def run() -> dict[str, Any]:
    started = time.perf_counter()
    for path, expected in EXPECTED_HASHES.items():
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"frozen source hash mismatch: {path}: {actual}")
    if RUN_PATH.exists():
        raise RuntimeError(f"completed output exists: {RUN_PATH}")

    # Importing this wrapper installs the exact ADR-0121 arm/stage identity in
    # the shared deterministic grader.  No provider is constructed or called.
    from scripts import rag_claimwise_nondestructive_compiler_golden_61 as source

    base = source.base
    parent_run = _read(PARENT_RUN)
    public = _read(PARENT_PUBLIC)
    scoring = _read(PARENT_SCORING)
    manifest = _read(MANIFEST_PATH)
    parent_by_id = {str(row["case_id"]): row for row in parent_run["rows"]}
    score_by_id = {str(row["case_id"]): row for row in scoring["cases"]}
    manifest_questions = {str(row["case_id"]): row for row in manifest["questions"]}

    if [row["case_id"] for row in public["cases"]] != [row["case_id"] for row in scoring["cases"]]:
        raise RuntimeError("public/scoring case order mismatch")

    rows: list[dict[str, Any]] = []
    question_paths: list[Path] = []
    for public_case in public["cases"]:
        case_id = str(public_case["case_id"])
        capture_path = PARENT_CAPTURES / f"{case_id}.json"
        capture_sha = _sha256(capture_path)
        capture = _read(capture_path)
        score = score_by_id[case_id]
        inherited = parent_by_id[case_id]["arms"][SOURCE_ARM]
        fresh_all = base.grade_retrieval_only_case(capture, score)
        fresh = deepcopy(fresh_all["arms"][SOURCE_ARM])
        stage_capture = capture["arms"][SOURCE_ARM]["retrieval"]["stage_capture"]
        presented = deepcopy(stage_capture["stages"][-1]["after"])
        fresh["stage_capture_sha256"] = stage_capture["capture_sha256"]
        fresh["presented_coordinates"] = presented
        fresh["matches_inherited"] = all((
            fresh["expected_hit_count"] == inherited["gold_hits"],
            fresh["expected_total"] == inherited["gold_total"],
            fresh["all_expected_present"] == inherited["all_gold_hit"],
            fresh["companion_hit_count"] == inherited["companion_hits"],
            fresh["companion_total"] == inherited["companion_total"],
            fresh["all_companions_present"] == inherited["all_companions_hit"],
            fresh["presented_count"] == inherited["presented_count"],
        ))
        if not fresh["matches_inherited"]:
            raise RuntimeError(f"fresh/inherited mismatch: {case_id}")
        row = {
            "number": int(public_case["number"]),
            "case_id": case_id,
            "suite": str(public_case["suite"]),
            "question": str(public_case["question"]),
            "source_capture_path": str(capture_path.relative_to(ROOT)),
            "source_capture_sha256": capture_sha,
            "inherited": {
                "gold_hits": int(inherited["gold_hits"]),
                "gold_total": int(inherited["gold_total"]),
                "all_gold_hit": bool(inherited["all_gold_hit"]),
                "companion_hits": int(inherited["companion_hits"]),
                "companion_total": int(inherited["companion_total"]),
                "all_companions_hit": bool(inherited["all_companions_hit"]),
                "presented_count": int(inherited["presented_count"]),
            },
            "deterministic": fresh,
            "failure_type": "none" if fresh["all_expected_present"] else "retrieval_miss",
        }
        rows.append(row)
        question_row = manifest_questions[case_id]
        question_path = ADR / "실험" / str(question_row["file"])
        _replace_question_scaffold(question_path, _question_markdown(
            public_case, score, row["inherited"], fresh, presented,
            capture_path, capture_sha,
        ))
        question_paths.append(question_path)

    hits = sum(row["deterministic"]["expected_hit_count"] for row in rows)
    total = sum(row["deterministic"]["expected_total"] for row in rows)
    all_cases = sum(row["deterministic"]["all_expected_present"] for row in rows)
    companion_hits = sum(row["deterministic"]["companion_hit_count"] for row in rows)
    companion_total = sum(row["deterministic"]["companion_total"] for row in rows)
    presented_total = sum(row["deterministic"]["presented_count"] for row in rows)
    corpus_total = int(parent_run["summary"]["corpus_article_roots"])

    slice_counts: dict[int, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "hits": 0, "expected": 0, "all_expected_cases": 0}
    )
    hit_pattern = Counter()
    for row in rows:
        fresh = row["deterministic"]
        bucket = slice_counts[int(fresh["expected_total"])]
        bucket["cases"] += 1
        bucket["hits"] += int(fresh["expected_hit_count"])
        bucket["expected"] += int(fresh["expected_total"])
        bucket["all_expected_cases"] += int(fresh["all_expected_present"])
        hit_pattern[f"{fresh['expected_hit_count']}/{fresh['expected_total']}"] += 1

    summary = {
        "cases": len(rows),
        "expected_hits": hits,
        "expected_total": total,
        "golden_recall": round(hits / total, 6),
        "all_expected_cases": all_cases,
        "all_expected_case_rate": round(all_cases / len(rows), 6),
        "retrieval_miss_cases": len(rows) - all_cases,
        "companion_hits": companion_hits,
        "companion_total": companion_total,
        "companion_recall": round(companion_hits / companion_total, 6),
        "presented_total": presented_total,
        "presented_mean": round(presented_total / len(rows), 6),
        "corpus_article_roots": corpus_total,
        "selectivity": round((presented_total / len(rows)) / corpus_total, 10),
        "by_expected_article_count": {
            str(key): {
                **value,
                "recall": round(value["hits"] / value["expected"], 6),
                "all_expected_case_rate": round(
                    value["all_expected_cases"] / value["cases"], 6
                ),
            }
            for key, value in sorted(slice_counts.items())
        },
        "by_hit_pattern": dict(sorted(hit_pattern.items())),
        "missing_cases": [
            {
                "case_id": row["case_id"],
                "hits": row["deterministic"]["expected_hit_count"],
                "total": row["deterministic"]["expected_total"],
                "missing_expected": row["deterministic"]["missing_expected"],
            }
            for row in rows if not row["deterministic"]["all_expected_present"]
        ],
        "fresh_inherited_exact_match_cases": sum(
            row["deterministic"]["matches_inherited"] for row in rows
        ),
        "provider_calls": 0,
        "judge_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    declared = parent_run["summary"]["by_arm"][SOURCE_ARM]
    frozen_criteria = {
        "all_61_cases": len(rows) == 61,
        "all_90_expected_coordinates": total == 90,
        "zero_provider_calls": summary["provider_calls"] == 0,
        "zero_judge_calls": summary["judge_calls"] == 0,
        "all_cases_match_inherited": summary["fresh_inherited_exact_match_cases"] == 61,
        "aggregate_hits_match_inherited": hits == int(declared["decisive_gold_hits"]),
        "aggregate_total_matches_inherited": total == int(declared["decisive_gold_total"]),
        "all_expected_cases_match_inherited": all_cases == int(declared["all_gold_cases"]),
        "companions_match_inherited": (
            companion_hits == int(declared["required_companion_hits"])
            and companion_total == int(declared["required_companion_total"])
        ),
    }
    frozen_criteria["all_frozen_criteria_met"] = all(frozen_criteria.values())
    if not frozen_criteria["all_frozen_criteria_met"]:
        raise RuntimeError(f"frozen criteria failed: {frozen_criteria}")

    run_artifact = {
        "schema_version": "adr-0123-deterministic-retrieval-regrade-v1",
        "adr_id": "ADR-0123",
        "experiment_id": "ADR-0123-experiment-v1",
        "run_id": "run-001",
        "source": {
            "adr_id": "ADR-0121",
            "experiment_id": "ADR-0121-experiment-v1",
            "arm_id": SOURCE_ARM,
            "run_path": str(PARENT_RUN.relative_to(ROOT)),
            "run_sha256": EXPECTED_HASHES[PARENT_RUN],
            "seal_path": str(PARENT_SEAL.relative_to(ROOT)),
            "seal_sha256": EXPECTED_HASHES[PARENT_SEAL],
            "scoring_path": str(PARENT_SCORING.relative_to(ROOT)),
            "scoring_sha256": EXPECTED_HASHES[PARENT_SCORING],
            "ledger_path": str(PARENT_LEDGER.relative_to(ROOT)),
            "ledger_sha256": EXPECTED_HASHES[PARENT_LEDGER],
        },
        "grading_rule": "expected_articles subset_of final_present_coordinates",
        "llm_calls": [],
        "summary": summary,
        "frozen_criteria": frozen_criteria,
        "rows": rows,
        "completed_at": _now(),
    }
    run_artifact["artifact_sha256"] = _self_hash(run_artifact)
    _write_new(RUN_PATH, run_artifact)

    manifest["runs"][0].update({"status": "complete", "sha256": _sha256(RUN_PATH)})
    manifest["retrieval_accounting"].update({
        "corpus_total": corpus_total,
        "before_filter": {"deterministic-retrieval-only": presented_total},
        "after_filter": {"deterministic-retrieval-only": presented_total},
        "presented_total": {"deterministic-retrieval-only": presented_total},
        "presented_mean": {"deterministic-retrieval-only": summary["presented_mean"]},
        "presented_p50": {"deterministic-retrieval-only": 28},
        "presented_p95": {"deterministic-retrieval-only": 28},
        "golden_recall": {"deterministic-retrieval-only": summary["golden_recall"]},
        "selectivity": {"deterministic-retrieval-only": summary["selectivity"]},
    })
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            "baseline": {
                "expected_hits": int(declared["decisive_gold_hits"]),
                "expected_total": int(declared["decisive_gold_total"]),
                "all_expected_cases": int(declared["all_gold_cases"]),
            },
            "deterministic-retrieval-only": summary,
        },
        "comparisons": [{
            "candidate_vs_baseline": {
                "per_case_exact_matches": summary["fresh_inherited_exact_match_cases"],
                "aggregate_delta_hits": hits - int(declared["decisive_gold_hits"]),
                "aggregate_delta_all_cases": all_cases - int(declared["all_gold_cases"]),
            }
        }],
        "judge_disagreements": 0,
        "usage": {"provider_calls": 0, "judge_calls": 0},
        "latency": {"deterministic_regrade_ms": summary["elapsed_ms"]},
        "error_taxonomy": [{
            "type": "retrieval_miss",
            "count": summary["retrieval_miss_cases"],
            "denominator": len(rows),
        }],
    }
    for question in manifest["questions"]:
        path = ADR / "실험" / str(question["file"])
        question["sha256"] = _sha256(path)
    MANIFEST_PATH.write_bytes(_canonical_bytes(manifest))

    artifact_files = [
        _artifact(RUN_PATH, "Deterministic Golden 61 retrieval regrade aggregate and per-case rows"),
        _artifact(PARENT_RUN, "Frozen parent run used for inherited comparison"),
        _artifact(PARENT_SEAL, "Frozen parent product seal"),
        _artifact(PARENT_SCORING, "Frozen expected-article scoring fixture"),
        _artifact(PARENT_LEDGER, "Inherited retrieval-stage ledger"),
    ]
    artifact_files.extend(
        _artifact(path, f"Question-level deterministic retrieval regrade {path.stem}")
        for path in question_paths
    )
    artifact_manifest = {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0123",
        "created_at": manifest["reservation"]["created_at"],
        "files": artifact_files,
    }
    ARTIFACT_MANIFEST_PATH.write_bytes(_canonical_bytes(artifact_manifest))
    return run_artifact


def repair_records() -> dict[str, Any]:
    """Repair standard headings/hashes without replaying the frozen regrade."""

    run_artifact = _read(RUN_PATH)
    public = _read(PARENT_PUBLIC)
    scoring = _read(PARENT_SCORING)
    manifest = _read(MANIFEST_PATH)
    public_by_id = {str(row["case_id"]): row for row in public["cases"]}
    score_by_id = {str(row["case_id"]): row for row in scoring["cases"]}
    run_by_id = {str(row["case_id"]): row for row in run_artifact["rows"]}
    question_paths: list[Path] = []
    for question in manifest["questions"]:
        case_id = str(question["case_id"])
        row = run_by_id[case_id]
        capture_path = ROOT / str(row["source_capture_path"])
        target = ADR / "실험" / str(question["file"])
        target.write_text(_question_markdown(
            public_by_id[case_id], score_by_id[case_id], row["inherited"],
            row["deterministic"], row["deterministic"]["presented_coordinates"],
            capture_path, str(row["source_capture_sha256"]),
        ), encoding="utf-8")
        question["sha256"] = _sha256(target)
        question_paths.append(target)
    (ADR / "실험/README.md").write_text(
        _experiment_index(run_artifact, manifest), encoding="utf-8"
    )
    MANIFEST_PATH.write_bytes(_canonical_bytes(manifest))

    failed = sorted((ADR / "artifacts/failed-attempts").glob("*/receipt.json"))
    files = [
        _artifact(RUN_PATH, "Deterministic Golden 61 retrieval regrade aggregate and per-case rows"),
        _artifact(Path(__file__), "ADR-0123 deterministic regrade runner"),
        _artifact(PARENT_RUN, "Frozen parent run used for inherited comparison"),
        _artifact(PARENT_SEAL, "Frozen parent product seal"),
        _artifact(PARENT_SCORING, "Frozen expected-article scoring fixture"),
        _artifact(PARENT_LEDGER, "Inherited retrieval-stage ledger"),
    ]
    files.extend(_artifact(path, f"Preserved failed attempt {path.parent.name}") for path in failed)
    files.extend(
        _artifact(path, f"Question-level deterministic retrieval regrade {path.stem}")
        for path in question_paths
    )
    artifact_manifest = {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0123",
        "created_at": manifest["reservation"]["created_at"],
        "files": files,
    }
    ARTIFACT_MANIFEST_PATH.write_bytes(_canonical_bytes(artifact_manifest))
    return {
        "questions_repaired": len(question_paths),
        "failed_attempt_receipts_preserved": len(failed),
        "provider_calls": 0,
        "judge_calls": 0,
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--repair-records"]:
        print(json.dumps(repair_records(), ensure_ascii=False, indent=2))
    elif sys.argv[1:]:
        raise SystemExit(f"unsupported arguments: {sys.argv[1:]}")
    else:
        print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
