#!/usr/bin/env python3
"""ADR-0128 deterministic legal-evidence objective replay."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lawrag.core.rag.evidence_confusion import (
    EvidenceConfusion,
    aggregate_evidence_confusions,
    difficulty_balanced_score,
)


ADR = ROOT / "docs/adr/ADR-0128-legal-evidence-confusion-objective"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
MANIFEST_PATH = ADR / "실험/manifest.json"
RUN_PATH = ADR / "artifacts/run-001.json"
ARTIFACT_MANIFEST_PATH = ADR / "artifacts/manifest.json"
INDEX_PATH = ADR / "실험/README.md"
CORPUS_SIZE = 16_506

SOURCES = (
    {
        "source_ref": "ADR-0115-experiment-v1/coverage-preserving-compiler",
        "arm": "coverage-preserving-compiler",
        "seal": ROOT / "docs/adr/ADR-0115-coverage-preserving-legal-compiler-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "fe49f8def6944d85c7e72794de86817b54c5ed4139c74bd317f19060be847d53",
    },
    {
        "source_ref": "ADR-0116-experiment-v1/scope-entailment-bundle-v2",
        "arm": "scope-entailment-bundle-v2",
        "seal": ROOT / "docs/adr/ADR-0116-scope-entailment-bundle-compiler-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "03aa953eb2ad687cb4dd5bc262ef2263a0a7616b27815fa6d8471ce9d86d98d3",
    },
    {
        "source_ref": "ADR-0117-experiment-v1/issue-role-atomic-entailment-v3",
        "arm": "issue-role-atomic-entailment-v3",
        "seal": ROOT / "docs/adr/ADR-0117-issue-role-atomic-entailment-compiler-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "821dcf96de83cdea48d47a4bfbf8fd9e8e40f09b5020a929002a18aa879f6f3b",
    },
    {
        "source_ref": "ADR-0118-experiment-v1/integrated-atomic-claim-v4b",
        "arm": "integrated-atomic-claim-v4b",
        "seal": ROOT / "docs/adr/ADR-0118-integrated-atomic-claim-compiler-golden-61/artifacts/product-capture-seal-run-002.json",
        "sha256": "2b50d2b2e13bbc96cf144ec8b93a6d0ccf16bf3fe4b34011f4b019c7d4ba3ba4",
    },
    {
        "source_ref": "ADR-0120-experiment-v1/proposition-assessment-shadow-v1",
        "arm": "proposition-assessment-shadow-v1",
        "seal": ROOT / "docs/adr/ADR-0120-proposition-assessment-shadow-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "6628618299762522170179ab1abec4c59f2d39bc82264349df9c83489722ed2f",
    },
    {
        "source_ref": "ADR-0121-experiment-v1/baseline",
        "arm": "baseline",
        "seal": ROOT / "docs/adr/ADR-0121-claimwise-nondestructive-legal-compiler-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "0474cd37239fef8b54fa50f0cf534679e772d34d3b952100003aced1a4cd8db6",
    },
    {
        "source_ref": "ADR-0121-experiment-v1/claimwise-nondestructive-v2",
        "arm": "claimwise-nondestructive-v2",
        "seal": ROOT / "docs/adr/ADR-0121-claimwise-nondestructive-legal-compiler-golden-61/artifacts/product-capture-seal-run-001.json",
        "sha256": "0474cd37239fef8b54fa50f0cf534679e772d34d3b952100003aced1a4cd8db6",
    },
)
EXPECTED_GOLD_HASHES = {
    CM_V3: "5e3227561a31123ccb77a3c55f0ca0d88b542d9b6ecac20aab26f812949eb169",
    FSC_V3: "2495c89ebca9ff11839bfd809aa848c385f113dd9954f0109e78da5c7bb4ba7f",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _self_hash(value: Mapping[str, Any]) -> str:
    payload = {key: child for key, child in value.items() if key != "artifact_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _identity(row: Mapping[str, Any]) -> str:
    return f"{row['doc_id']}:{row['node']}"


def _candidate_id(section: Mapping[str, Any]) -> str:
    meta = section.get("legal_meta")
    if not isinstance(meta, Mapping):
        return ""
    integrated = meta.get("integrated_research")
    if not isinstance(integrated, Mapping):
        return ""
    return str(integrated.get("candidate_id") or "")


def _gold_cases() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for suite, path, evidence_key in (
        ("core", CM_V3, "evidence_articles"),
        ("hard", FSC_V3, "current_evidence_articles"),
    ):
        for case in _read(path)["cases"]:
            present = list(case[evidence_key])
            result[str(case["id"])] = {
                "question": str(case["question"]),
                "suite": suite,
                "present": present,
                "required": {_identity(item) for item in present},
                "roles": sorted({str(item["evidence_role_v3"]) for item in present}),
                "external": list(case.get("required_external_evidence") or []),
            }
    return result


def _resolve_answer_evidence(capture: Mapping[str, Any], arm: str) -> tuple[set[str], list[str], list[str]]:
    source = capture["arms"][arm]
    sections = list(source["retrieval"]["sections"])
    id_map: dict[str, str] = {}
    ambiguous: set[str] = set()
    for section in sections:
        candidate_id = _candidate_id(section)
        if not candidate_id:
            continue
        identity = _identity(section)
        prior = id_map.setdefault(candidate_id, identity)
        if prior != identity:
            ambiguous.add(candidate_id)
    declared = {str(item) for item in (source["answer"].get("evidence_ids") or [])}
    unresolved = sorted(declared - set(id_map))
    selected = {id_map[item] for item in declared if item in id_map and item not in ambiguous}
    return selected, unresolved, sorted(ambiguous & declared)


def _source_rows(source: Mapping[str, Any], gold: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    seal = _read(Path(source["seal"]))
    rows: list[dict[str, Any]] = []
    for receipt in seal["case_receipts"]:
        case_id = str(receipt["case_id"])
        capture_path = ROOT / str(receipt["path"])
        if _sha256(capture_path) != str(receipt["sha256"]):
            raise RuntimeError(f"capture hash mismatch: {source['source_ref']} {case_id}")
        capture = _read(capture_path)
        selected, unresolved, ambiguous = _resolve_answer_evidence(capture, str(source["arm"]))
        case_gold = gold[case_id]
        confusion = EvidenceConfusion.from_sets(
            case_gold["required"], selected, universe_size=CORPUS_SIZE
        )
        rows.append({
            "case_id": case_id,
            "suite": case_gold["suite"],
            "question": case_gold["question"],
            "required_identities": sorted(case_gold["required"]),
            "required_roles": case_gold["roles"],
            "external_required_count": len(case_gold["external"]),
            "selected_identities": sorted(selected),
            "confusion": confusion.to_dict(),
            "lineage_valid": not unresolved and not ambiguous,
            "unresolved_evidence_ids": unresolved,
            "ambiguous_evidence_ids": ambiguous,
            "source_capture_path": str(capture_path.relative_to(ROOT)),
            "source_capture_sha256": str(receipt["sha256"]),
        })
    rows.sort(key=lambda item: item["case_id"])
    if len(rows) != 61 or {row["case_id"] for row in rows} != set(gold):
        raise RuntimeError(f"Golden61 mismatch for {source['source_ref']}")
    return rows


def _confusion(row: Mapping[str, Any]) -> EvidenceConfusion:
    data = row["confusion"]
    return EvidenceConfusion(tp=int(data["tp"]), fp=int(data["fp"]), fn=int(data["fn"]), tn=int(data["tn"]))


def _summarize(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for name, subset in (
        ("all", rows),
        ("core", [row for row in rows if row["suite"] == "core"]),
        ("hard", [row for row in rows if row["suite"] == "hard"]),
        ("single_required", [row for row in rows if len(row["required_identities"]) == 1]),
        ("multi_required", [row for row in rows if len(row["required_identities"]) >= 2]),
        ("role_complex", [row for row in rows if set(row["required_roles"]) != {"MAIN"}]),
    ):
        if subset:
            groups[name] = aggregate_evidence_confusions([_confusion(row) for row in subset])
    balanced = difficulty_balanced_score({"core": groups["core"], "hard": groups["hard"]})
    all_group = groups["all"]
    eligible = (
        float(all_group["recall"]) >= 0.80
        and float(groups["hard"]["recall"]) >= 0.70
        and float(all_group["complete_rate"]) >= 0.70
    )
    selected_counts = [int(row["confusion"]["selected"]) for row in rows]
    return {
        "groups": groups,
        "difficulty_balanced_score": balanced,
        "eligibility": {
            "overall_recall_at_least_0_80": float(all_group["recall"]) >= 0.80,
            "hard_recall_at_least_0_70": float(groups["hard"]["recall"]) >= 0.70,
            "complete_rate_at_least_0_70": float(all_group["complete_rate"]) >= 0.70,
            "eligible": eligible,
        },
        "selected_mean": round(statistics.mean(selected_counts), 6),
        "selected_p50": float(statistics.median(selected_counts)),
        "selected_p95": float(sorted(selected_counts)[int(0.95 * (len(selected_counts) - 1))]),
        "empty_cases": sum(count == 0 for count in selected_counts),
    }


def _synthetic_checks() -> dict[str, bool]:
    exact = EvidenceConfusion(2, 0, 0, 10)
    extra = EvidenceConfusion(2, 1, 0, 9)
    missing = EvidenceConfusion(1, 0, 1, 10)
    empty = EvidenceConfusion(0, 0, 2, 10)
    changed_tn = EvidenceConfusion(2, 0, 0, 1_000_000)
    return {
        "exact_is_one": exact.tversky() == 1.0,
        "extra_lowers_score": exact.tversky() > extra.tversky(),
        "missing_lowers_score": exact.tversky() > missing.tversky(),
        "missing_costs_more_than_extra": extra.tversky() > missing.tversky(),
        "empty_is_zero": empty.tversky() == 0.0,
        "tn_does_not_change_score": exact.tversky() == changed_tn.tversky(),
    }


def _question_markdown(case_id: str, gold: Mapping[str, Any], source_rows: Mapping[str, Mapping[str, Any]]) -> str:
    lines = [
        f"# {case_id} 법률근거 혼동행렬",
        "",
        "## 1. 실행 메타",
        "",
        "- run: `run-001`",
        "- 제품·검색·judge·LLM 호출: `0`",
        f"- 난도 suite: `{gold['suite']}`",
        "",
        "## 2. 사용자 질문 원문",
        "",
        str(gold["question"]),
        "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개",
        "",
        "기준답변 문장은 사용하지 않고 Golden61 v3 필요 article-root 좌표만 사용했다.",
        "",
        "## 4. 제품 입력을 구성한 원값",
        "",
        f"- corpus-resolvable 필요 조문: `{sorted(gold['required'])}`",
        f"- 역할: `{gold['roles']}`",
        f"- corpus 외부 필요 조문 수: `{len(gold['external'])}`",
        "",
        "### 회수·탈락 단계 원장 — run·arm별",
        "",
        "새 회수·탈락은 없다. 각 부모의 봉인 답변 `evidence_ids`를 동일 v3 gold에 투영했다.",
        "",
        "| source ADR arm | selected | TP | FP | FN | TN | precision | recall | legal Tversky | complete |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for source_ref in sorted(source_rows):
        row = source_rows[source_ref]
        if not row["lineage_valid"]:
            lines.append(f"| `{source_ref}` | INVALID | - | - | - | - | - | - | - | false |")
        else:
            matrix = row["confusion"]
            lines.append(
                f"| `{source_ref}` | {matrix['selected']} | {matrix['tp']} | {matrix['fp']} | "
                f"{matrix['fn']} | {matrix['tn']} | {matrix['precision']:.4f} | "
                f"{matrix['recall']:.4f} | {matrix['legal_tversky']:.4f} | {matrix['complete']} |"
            )
    lines.extend([
        "",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문",
        "",
        "새 호출 없음. 각 행의 source capture path와 SHA-256은 run artifact에 기록했다.",
        "",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
        "",
        "새 호출 없음.",
        "",
        "## 7. 채점 호출과 반복 판정",
        "",
        "결정론적 집합 연산 1회이며 judge 호출은 없다.",
        "",
        "## 8. 사례 최종 판정",
        "",
        "FN=0이면 필요한 조문을 전부 포함한 complete, FP=FN=0이면 exact다. 빈 집합도 0점으로 포함한다.",
        "",
    ])
    return "\n".join(lines)


def _experiment_index(run: Mapping[str, Any]) -> str:
    lines = [
        "# ADR-0128 질문 인덱스",
        "",
        "> Golden61 v3 필요 조문과 봉인 최종답변 선언 조문의 질문별 혼동행렬. 새 호출은 없다.",
        "",
        "| 번호 | case | 난도 | 파일 |",
        "|---:|---|---|---|",
    ]
    for number, case_id in enumerate(run["case_ids"], 1):
        suite = "hard" if case_id.startswith("fsc-hard-") else "core"
        filename = f"질문-{number:03d}-{case_id}.md"
        lines.append(f"| {number:03d} | `{case_id}` | `{suite}` | [{filename}]({filename}) |")
    lines.extend(["", "- 상세 집계: [run-001.json](../artifacts/run-001.json)", ""])
    return "\n".join(lines)


def _artifact(path: Path, description: str) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "description": description,
        "contains_raw_prompts_and_outputs": False,
    }


def run() -> dict[str, Any]:
    started = time.perf_counter()
    if RUN_PATH.exists():
        raise RuntimeError(f"completed output exists: {RUN_PATH}")
    for path, expected in EXPECTED_GOLD_HASHES.items():
        if _sha256(path) != expected:
            raise RuntimeError(f"frozen gold hash mismatch: {path}")
    for source in SOURCES:
        if _sha256(Path(source["seal"])) != source["sha256"]:
            raise RuntimeError(f"frozen seal hash mismatch: {source['source_ref']}")

    gold = _gold_cases()
    by_source: dict[str, Any] = {}
    rows_by_case: dict[str, dict[str, Any]] = {case_id: {} for case_id in gold}
    for source in SOURCES:
        rows = _source_rows(source, gold)
        source_ref = str(source["source_ref"])
        lineage_errors = [
            {
                "case_id": row["case_id"],
                "unresolved_evidence_ids": row["unresolved_evidence_ids"],
                "ambiguous_evidence_ids": row["ambiguous_evidence_ids"],
            }
            for row in rows
            if not row["lineage_valid"]
        ]
        by_source[source_ref] = {
            "seal_path": str(Path(source["seal"]).relative_to(ROOT)),
            "seal_sha256": source["sha256"],
            "status": "invalid_evidence_lineage" if lineage_errors else "complete",
            "summary": None if lineage_errors else _summarize(rows),
            "lineage_errors": lineage_errors,
            "rows": rows,
        }
        for row in rows:
            rows_by_case[row["case_id"]][source_ref] = row

    valid_sources = [ref for ref, value in by_source.items() if value["status"] == "complete"]
    rankings = {
        "naive_micro_f1": sorted(
            valid_sources,
            key=lambda ref: (-float(by_source[ref]["summary"]["groups"]["all"]["f1"]), ref),
        ),
        "difficulty_balanced_legal": sorted(
            valid_sources,
            key=lambda ref: (-float(by_source[ref]["summary"]["difficulty_balanced_score"]), ref),
        ),
    }
    checks = _synthetic_checks()
    if not all(checks.values()):
        raise RuntimeError(f"synthetic objective checks failed: {checks}")

    run_artifact: dict[str, Any] = {
        "schema_version": "legal-evidence-confusion-objective-v1",
        "adr_id": "ADR-0128",
        "experiment_id": "ADR-0128-experiment-v1",
        "run_id": "run-001",
        "formula": {
            "confusion": "TP=|A∩G|; FP=|A-G|; FN=|G-A|; TN=16506-|A∪G|",
            "legal_tversky": "TP/(TP+0.25*FP+1.0*FN)",
            "group_score": "100*(0.45*micro_tversky+0.35*macro_tversky+0.20*complete_case_rate)",
            "difficulty_balanced": "0.5*core_group_score+0.5*hard_group_score",
            "tn_used_in_score": False,
        },
        "fixed_denominators": {"cases": 61, "core": 51, "hard": 10, "corpus_gold": 116, "full_gold": 119, "corpus_size": CORPUS_SIZE},
        "synthetic_checks": checks,
        "sources": by_source,
        "rankings": rankings,
        "case_ids": sorted(gold),
        "provider_calls": 0,
        "judge_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "completed_at": _now(),
    }
    run_artifact["artifact_sha256"] = _self_hash(run_artifact)
    _write_new(RUN_PATH, run_artifact)

    manifest = _read(MANIFEST_PATH)
    question_paths: list[Path] = []
    for question in manifest["questions"]:
        case_id = str(question["case_id"])
        path = ADR / "실험" / str(question["file"])
        current = path.read_text(encoding="utf-8")
        if "TODO" not in current:
            raise RuntimeError(f"refusing to overwrite non-scaffold: {path}")
        path.write_text(_question_markdown(case_id, gold[case_id], rows_by_case[case_id]), encoding="utf-8")
        question["sha256"] = _sha256(path)
        question_paths.append(path)
    INDEX_PATH.write_text(_experiment_index(run_artifact), encoding="utf-8")
    manifest["runs"][0].update({"status": "complete", "sha256": _sha256(RUN_PATH)})
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            ref: {"status": value["status"], "summary": value["summary"], "lineage_errors": value["lineage_errors"]}
            for ref, value in by_source.items()
        },
        "comparisons": [{"rankings": rankings}],
        "judge_disagreements": 0,
        "usage": {"product_calls": 0, "retrieval_calls": 0, "judge_calls": 0, "tokens": 0},
        "latency": {"deterministic_regrade_ms": run_artifact["elapsed_ms"]},
        "error_taxonomy": [
            {"type": "required_issue_omission", "measure": "FN", "denominator": 116},
            {"type": "unsupported_inference", "measure": "FP", "denominator": "selected answer evidence"},
            {"type": "evidence_lineage_invalid", "source_count": sum(value["status"] != "complete" for value in by_source.values())},
        ],
    }
    MANIFEST_PATH.write_bytes(_canonical_bytes(manifest))

    files = [
        _artifact(RUN_PATH, "ADR-0128 confusion matrix and difficulty-balanced leaderboard"),
        _artifact(Path(__file__), "ADR-0128 deterministic runner"),
    ]
    files.extend(_artifact(path, f"Question confusion matrix {path.stem}") for path in question_paths)
    for source in SOURCES:
        files.append(_artifact(Path(source["seal"]), f"Frozen source seal {source['source_ref']}"))
    files.extend(_artifact(path, "Golden61 v3 evidence fixture") for path in EXPECTED_GOLD_HASHES)
    ARTIFACT_MANIFEST_PATH.write_bytes(_canonical_bytes({
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0128",
        "created_at": manifest["reservation"]["created_at"],
        "files": files,
    }))
    return run_artifact


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit(f"unsupported arguments: {sys.argv[1:]}")
    result = run()
    print(json.dumps({ref: {"status": value["status"], "summary": value["summary"]} for ref, value in result["sources"].items()}, ensure_ascii=False, indent=2))
