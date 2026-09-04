#!/usr/bin/env python3
"""ADR-0127: replay sealed answers against Golden61 v3 evidence roles.

No retrieval, product model, or judge is invoked.  The script compares three
projections of the already sealed ADR-0121 evidence:

* baseline: every final-present article;
* answer-declared-used-v3: sections named by answer.evidence_ids;
* answer-surface-cited-v3: final sections explicitly named in answer text.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/ADR-0127-answer-cited-evidence-v3-regrade"
PARENT = ROOT / "docs/adr/ADR-0121-claimwise-nondestructive-legal-compiler-golden-61"
PARENT_ARTIFACTS = PARENT / "artifacts"
PARENT_SEAL = PARENT_ARTIFACTS / "product-capture-seal-run-001.json"
PARENT_LEDGER = PARENT_ARTIFACTS / "retrieval-stage-ledger-run-001.json"
PARENT_CAPTURES = PARENT_ARTIFACTS / "product-captures/run-001"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
MANIFEST_PATH = ADR / "실험/manifest.json"
RUN_PATH = ADR / "artifacts/run-001.json"
ARTIFACT_MANIFEST_PATH = ADR / "artifacts/manifest.json"
INDEX_PATH = ADR / "실험/README.md"

SOURCE_ARMS = ("baseline", "claimwise-nondestructive-v2")
PROJECTIONS = ("baseline", "answer-declared-used-v3", "answer-surface-cited-v3")
EXPECTED_HASHES = {
    PARENT_SEAL: "0474cd37239fef8b54fa50f0cf534679e772d34d3b952100003aced1a4cd8db6",
    PARENT_LEDGER: "0e60ff091e1f0751c337efd14122d3ee4c3ac6198be912a1f8ae74333d48090c",
    CM_V3: "5e3227561a31123ccb77a3c55f0ca0d88b542d9b6ecac20aab26f812949eb169",
    FSC_V3: "2495c89ebca9ff11839bfd809aa848c385f113dd9954f0109e78da5c7bb4ba7f",
}
ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")


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
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _self_hash(value: Mapping[str, Any]) -> str:
    payload = {key: child for key, child in value.items() if key != "artifact_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _replace_scaffold(path: Path, text: str) -> None:
    current = path.read_text(encoding="utf-8")
    if not current.startswith("# 질문 ") or "TODO" not in current:
        raise RuntimeError(f"refusing to overwrite non-scaffold question: {path}")
    path.write_text(text, encoding="utf-8")


def _identity(row: Mapping[str, Any]) -> str:
    return f"{row['doc_id']}:{row['node']}"


def _article_from_path(path: str) -> str:
    matches = list(ARTICLE_RE.finditer(path))
    if not matches:
        return ""
    match = matches[-1]
    return f"제{match.group(1)}조" + (f"의{match.group(2)}" if match.group(2) else "")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _section_candidate_id(section: Mapping[str, Any]) -> str:
    legal_meta = section.get("legal_meta")
    if not isinstance(legal_meta, Mapping):
        return ""
    integrated = legal_meta.get("integrated_research")
    if not isinstance(integrated, Mapping):
        return ""
    return str(integrated.get("candidate_id") or "")


def _surface_selected(answer: str, sections: Iterable[Mapping[str, Any]]) -> tuple[set[str], list[str]]:
    compact_answer = _compact(answer)
    selected: set[str] = set()
    matched_tokens: set[str] = set()
    for section in sections:
        law = _compact(str(section.get("doc") or ""))
        article = _compact(_article_from_path(str(section.get("path") or "")))
        if not law or not article:
            continue
        token = law + article
        if token in compact_answer:
            selected.add(_identity(section))
            matched_tokens.add(article)
    mentioned = {
        f"제{match.group(1)}조" + (f"의{match.group(2)}" if match.group(2) else "")
        for match in ARTICLE_RE.finditer(answer or "")
    }
    return selected, sorted(mentioned - matched_tokens)


def _gold_cases() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    cm = _read(CM_V3)
    fsc = _read(FSC_V3)
    for case in cm["cases"]:
        present = list(case["evidence_articles"])
        result[str(case["id"])] = {
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "present": present,
            "external": [],
        }
    for case in fsc["cases"]:
        present = list(case["current_evidence_articles"])
        result[str(case["id"])] = {
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "present": present,
            "external": list(case.get("required_external_evidence") or []),
        }
    return result


def _metrics(selected: set[str], gold: Mapping[str, Any], role_by_identity: Mapping[str, str]) -> dict[str, Any]:
    corpus_gold = set(role_by_identity)
    hit = selected & corpus_gold
    distractor = selected - corpus_gold
    external = list(gold["external"])
    full_total = len(corpus_gold) + len(external)
    precision = len(hit) / len(selected) if selected else 0.0
    corpus_recall = len(hit) / len(corpus_gold) if corpus_gold else 0.0
    full_recall = len(hit) / full_total if full_total else 0.0
    f2 = (5 * precision * corpus_recall / (4 * precision + corpus_recall)) if (precision or corpus_recall) else 0.0
    role_total = Counter(role_by_identity.values())
    role_hits = Counter(role_by_identity[item] for item in hit)
    return {
        "selected": sorted(selected),
        "selected_count": len(selected),
        "corpus_gold_hits": len(hit),
        "corpus_gold_total": len(corpus_gold),
        "full_gold_hits": len(hit),
        "full_gold_total": full_total,
        "precision": round(precision, 8),
        "corpus_recall": round(corpus_recall, 8),
        "full_recall": round(full_recall, 8),
        "f2": round(f2, 8),
        "corpus_complete": corpus_gold <= selected,
        "full_complete": not external and corpus_gold <= selected,
        "used_non_gold": sorted(distractor),
        "missing_corpus_gold": sorted(corpus_gold - selected),
        "external_missing": [f"{row['law']} {row['article']}" for row in external],
        "role_hits": dict(sorted(role_hits.items())),
        "role_totals": dict(sorted(role_total.items())),
    }


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))
    return float(ordered[index])


def _aggregate(rows: list[Mapping[str, Any]], source_arm: str, projection: str) -> dict[str, Any]:
    parts = [row["source_arms"][source_arm]["projections"][projection] for row in rows]
    selected_counts = [int(part["selected_count"]) for part in parts]
    hits = sum(int(part["corpus_gold_hits"]) for part in parts)
    corpus_total = sum(int(part["corpus_gold_total"]) for part in parts)
    full_total = sum(int(part["full_gold_total"]) for part in parts)
    selected_total = sum(selected_counts)
    precision = hits / selected_total if selected_total else 0.0
    corpus_recall = hits / corpus_total if corpus_total else 0.0
    full_recall = hits / full_total if full_total else 0.0
    f2 = (5 * precision * corpus_recall / (4 * precision + corpus_recall)) if (precision or corpus_recall) else 0.0
    role_hits: Counter[str] = Counter()
    role_totals: Counter[str] = Counter()
    for part in parts:
        role_hits.update(part["role_hits"])
        role_totals.update(part["role_totals"])
    return {
        "cases": len(parts),
        "selected_total": selected_total,
        "selected_mean": round(statistics.mean(selected_counts), 6),
        "selected_p50": _percentile(selected_counts, 0.50),
        "selected_p95": _percentile(selected_counts, 0.95),
        "empty_cases": sum(count == 0 for count in selected_counts),
        "corpus_gold_hits": hits,
        "corpus_gold_total": corpus_total,
        "full_gold_hits": hits,
        "full_gold_total": full_total,
        "micro_precision": round(precision, 8),
        "corpus_micro_recall": round(corpus_recall, 8),
        "full_micro_recall": round(full_recall, 8),
        "micro_f2": round(f2, 8),
        "corpus_complete_cases": sum(bool(part["corpus_complete"]) for part in parts),
        "full_complete_cases": sum(bool(part["full_complete"]) for part in parts),
        "used_non_gold_total": sum(len(part["used_non_gold"]) for part in parts),
        "role_recall": {
            role: {
                "hits": int(role_hits[role]),
                "total": int(total),
                "recall": round(role_hits[role] / total, 8),
            }
            for role, total in sorted(role_totals.items())
        },
    }


def _question_markdown(row: Mapping[str, Any]) -> str:
    lines = [
        f"# {row['case_id']} 답변 사용 근거 v3 재채점",
        "",
        "## 1. 실행 메타",
        "",
        "- run: `run-001`",
        "- 제품·검색·judge·LLM 호출: `0`",
        f"- source capture: `{row['source_capture_path']}`",
        f"- source capture SHA-256: `{row['source_capture_sha256']}`",
        "",
        "## 2. 사용자 질문 원문",
        "",
        str(row["question"]),
        "",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개",
        "",
        "기준답변 문장은 판정에 사용하지 않고 v3 article-root 역할 좌표만 사용했다.",
        "",
        "## 4. 제품 입력을 구성한 원값",
        "",
        "ADR-0121 봉인 final-present와 답변을 변경 없이 상속했다.",
        "",
        "### 회수·탈락 단계 원장 — run·arm별",
        "",
        f"- 상속 원장: `{PARENT_LEDGER.relative_to(ROOT)}`",
        f"- 상속 원장 SHA-256: `{EXPECTED_HASHES[PARENT_LEDGER]}`",
        "- 아래 단계는 새 검색이 아니라 같은 봉인 결과에 대한 결정론적 투영이다.",
        "",
        "| source answer arm | stage | before→after | gold before→after | 탈락 이유 |",
        "|---|---|---:|---:|---|",
    ]
    for source_arm in SOURCE_ARMS:
        arm = row["source_arms"][source_arm]
        presented = arm["projections"]["baseline"]
        declared = arm["projections"]["answer-declared-used-v3"]
        surface = arm["projections"]["answer-surface-cited-v3"]
        lines.extend([
            f"| `{source_arm}` | final-present → answer-declared-used | "
            f"{presented['selected_count']}→{declared['selected_count']} | "
            f"{presented['corpus_gold_hits']}→{declared['corpus_gold_hits']} | "
            "`answer.evidence_ids`에 선언되지 않은 좌표 |",
            f"| `{source_arm}` | final-present → answer-surface-cited | "
            f"{presented['selected_count']}→{surface['selected_count']} | "
            f"{presented['corpus_gold_hits']}→{surface['corpus_gold_hits']} | "
            "답변 본문에 법명+조문이 함께 명시되지 않은 좌표 |",
        ])
    lines.extend([
        "",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문",
        "",
        "새 호출 없음. 원 호출은 source capture hash로 연결한다.",
        "",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
        "",
        "새 호출 없음.",
        "",
        "## 7. 채점 호출과 반복 판정",
        "",
        "단일 결정론 좌표 집합 비교이며 새 judge 호출은 없다.",
        "",
        "| source answer arm | projection | hit/corpus | precision | recall | F2 | corpus complete | selected |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ])
    for source_arm in SOURCE_ARMS:
        arm = row["source_arms"][source_arm]
        for projection in PROJECTIONS:
            part = arm["projections"][projection]
            lines.append(
                f"| `{source_arm}` | `{projection}` | {part['corpus_gold_hits']}/{part['corpus_gold_total']} | "
                f"{part['precision']:.4f} | {part['corpus_recall']:.4f} | {part['f2']:.4f} | "
                f"{part['corpus_complete']} | {part['selected_count']} |"
            )
        if arm["unresolved_declared_evidence_ids"]:
            lines.append(f"\n- `{source_arm}` unresolved declared IDs: `{arm['unresolved_declared_evidence_ids']}`")
        if arm["unresolved_surface_articles"]:
            lines.append(f"- `{source_arm}` unresolved surface articles: `{arm['unresolved_surface_articles']}`")
    lines.extend([
        "",
        "## 8. 사례 최종 판정",
        "",
        "이 파일은 답변 정오가 아니라 검색→답변 사이의 근거 사용 효율을 판정한다.",
        "빈 사용 집합도 제외하지 않고 0점·불완전으로 보존한다.",
        "",
    ])
    return "\n".join(lines)


def repair_records() -> None:
    """Repair generated record formatting without rerunning the experiment."""
    run_artifact = _read(RUN_PATH)
    manifest = _read(MANIFEST_PATH)
    question_paths: list[Path] = []
    for row in run_artifact["rows"]:
        path = ADR / "실험" / row["question_file"]
        path.write_text(_question_markdown(row), encoding="utf-8")
        question_paths.append(path)
    INDEX_PATH.write_text(_experiment_index(run_artifact), encoding="utf-8")
    for question in manifest["questions"]:
        question["sha256"] = _sha256(ADR / "실험" / question["file"])
    MANIFEST_PATH.write_bytes(_canonical_bytes(manifest))
    files = [
        _artifact(RUN_PATH, "Golden61 v3 answer evidence utilization deterministic regrade"),
        _artifact(Path(__file__), "ADR-0127 deterministic regrade runner"),
        _artifact(PARENT_SEAL, "Frozen ADR-0121 product capture seal"),
        _artifact(PARENT_LEDGER, "Inherited ADR-0121 retrieval stage ledger"),
        _artifact(CM_V3, "Golden61 CM v3 minimal-sufficient evidence"),
        _artifact(FSC_V3, "Golden61 FSC v3 minimal-sufficient evidence"),
    ]
    files.extend(_artifact(path, f"Question-level answer evidence regrade {path.stem}") for path in question_paths)
    ARTIFACT_MANIFEST_PATH.write_bytes(_canonical_bytes({
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0127",
        "created_at": manifest["reservation"]["created_at"],
        "files": files,
    }))


def _experiment_index(run: Mapping[str, Any]) -> str:
    rows = []
    for row in run["rows"]:
        declared = row["source_arms"]["baseline"]["projections"]["answer-declared-used-v3"]
        rows.append(
            f"| {row['number']:03d} | `{row['case_id']}` | "
            f"{declared['corpus_gold_hits']}/{declared['corpus_gold_total']} | "
            f"{declared['precision']:.3f} | {declared['corpus_recall']:.3f} | "
            f"[{row['question_file']}]({row['question_file']}) |"
        )
    return """# ADR-0127 실험 질문 인덱스

> ADR-0121 봉인 답변과 retrieval을 Golden61 v3 역할 골든으로 재채점했다. 새 호출은 없다.

## 질문 인덱스

| 번호 | case ID | declared hit/total | precision | recall | 파일 |
|---:|---|---:|---:|---:|---|
{rows}

## 집계

- run: `run-001 / complete`
- 제품·검색·judge·LLM 호출: `0`
- full 분모: `119`, corpus-resolvable 분모: `116`, 문항 분모: `61`
- 상세 집계: [run-001.json](../artifacts/run-001.json)
""".format(rows="\n".join(rows))


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
    for path, expected in EXPECTED_HASHES.items():
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"frozen source hash mismatch: {path}: {actual} != {expected}")
    if RUN_PATH.exists():
        raise RuntimeError(f"completed output exists: {RUN_PATH}")

    seal = _read(PARENT_SEAL)
    manifest = _read(MANIFEST_PATH)
    gold_by_id = _gold_cases()
    question_by_id = {str(row["case_id"]): row for row in manifest["questions"]}
    rows: list[dict[str, Any]] = []
    all_declared_unresolved: list[dict[str, Any]] = []
    ambiguous_ids: list[dict[str, Any]] = []

    for receipt in seal["case_receipts"]:
        case_id = str(receipt["case_id"])
        capture_path = ROOT / str(receipt["path"])
        capture_sha = _sha256(capture_path)
        if capture_sha != str(receipt["sha256"]):
            raise RuntimeError(f"capture hash mismatch: {case_id}")
        capture = _read(capture_path)
        gold = gold_by_id[case_id]
        role_by_identity = {_identity(item): str(item["evidence_role_v3"]) for item in gold["present"]}
        case_row: dict[str, Any] = {
            "number": int(receipt["number"]),
            "case_id": case_id,
            "suite": str(receipt["suite"]),
            "question": str(capture["question"]),
            "source_capture_path": str(capture_path.relative_to(ROOT)),
            "source_capture_sha256": capture_sha,
            "question_file": str(question_by_id[case_id]["file"]),
            "gold": {
                "corpus_present": [
                    {"identity": _identity(item), "law": item["law"], "article": item["article"], "role": item["evidence_role_v3"]}
                    for item in gold["present"]
                ],
                "external_missing": [
                    {"law": item["law"], "article": item["article"], "role": item["evidence_role_v3"]}
                    for item in gold["external"]
                ],
            },
            "source_arms": {},
        }
        for source_arm in SOURCE_ARMS:
            source = capture["arms"][source_arm]
            sections = list(source["retrieval"]["sections"])
            presented = {_identity(section) for section in sections}
            id_map: dict[str, str] = {}
            for section in sections:
                candidate_id = _section_candidate_id(section)
                if not candidate_id:
                    continue
                identity = _identity(section)
                prior = id_map.setdefault(candidate_id, identity)
                if prior != identity:
                    ambiguous_ids.append({"case_id": case_id, "source_arm": source_arm, "evidence_id": candidate_id, "identities": sorted({prior, identity})})
            declared_ids = {str(item) for item in (source["answer"].get("evidence_ids") or [])}
            unresolved_declared = sorted(declared_ids - set(id_map))
            declared = {id_map[item] for item in declared_ids if item in id_map}
            surface, unresolved_surface = _surface_selected(str(source["answer"].get("answer") or ""), sections)
            if unresolved_declared:
                all_declared_unresolved.append({"case_id": case_id, "source_arm": source_arm, "ids": unresolved_declared})
            projections = {
                "baseline": _metrics(presented, gold, role_by_identity),
                "answer-declared-used-v3": _metrics(declared, gold, role_by_identity),
                "answer-surface-cited-v3": _metrics(surface, gold, role_by_identity),
            }
            retrieved_gold = presented & set(role_by_identity)
            for projection in ("answer-declared-used-v3", "answer-surface-cited-v3"):
                selected_gold = set(projections[projection]["selected"]) & set(role_by_identity)
                projections[projection]["retrieved_gold_unused"] = sorted(retrieved_gold - selected_gold)
                projections[projection]["gold_usage_rate"] = round(len(selected_gold) / len(retrieved_gold), 8) if retrieved_gold else 0.0
            case_row["source_arms"][source_arm] = {
                "answerable": bool(source["answer"].get("answerable")),
                "answer_text": str(source["answer"].get("answer") or ""),
                "declared_evidence_ids": sorted(declared_ids),
                "unresolved_declared_evidence_ids": unresolved_declared,
                "unresolved_surface_articles": unresolved_surface,
                "projections": projections,
            }
        rows.append(case_row)

    rows.sort(key=lambda item: int(item["number"]))
    if len(rows) != 61 or set(gold_by_id) != {row["case_id"] for row in rows}:
        raise RuntimeError("Golden61 case set mismatch")
    if ambiguous_ids or all_declared_unresolved:
        raise RuntimeError(f"declared evidence IDs do not uniquely resolve: ambiguous={ambiguous_ids}, unresolved={all_declared_unresolved}")

    summaries = {
        source_arm: {projection: _aggregate(rows, source_arm, projection) for projection in PROJECTIONS}
        for source_arm in SOURCE_ARMS
    }
    criteria: dict[str, Any] = {"by_source_arm": {}}
    for source_arm in SOURCE_ARMS:
        presented = summaries[source_arm]["baseline"]
        declared = summaries[source_arm]["answer-declared-used-v3"]
        reduction = 1 - declared["selected_total"] / presented["selected_total"]
        recall_retention = declared["corpus_micro_recall"] / presented["corpus_micro_recall"] if presented["corpus_micro_recall"] else 0.0
        main_delta = declared["role_recall"]["MAIN"]["recall"] - presented["role_recall"]["MAIN"]["recall"]
        checks = {
            "selected_reduction_at_least_50pct": reduction >= 0.50,
            "recall_retention_at_least_90pct": recall_retention >= 0.90,
            "main_recall_drop_at_most_5pp": main_delta >= -0.05,
            "f2_noninferior": declared["micro_f2"] >= presented["micro_f2"],
            "selected_reduction": round(reduction, 8),
            "recall_retention": round(recall_retention, 8),
            "main_recall_delta": round(main_delta, 8),
        }
        checks["all_primary_checks_met"] = all(value for key, value in checks.items() if key.endswith(("50pct", "90pct", "5pp", "noninferior")))
        criteria["by_source_arm"][source_arm] = checks
    criteria["all_source_arms_met"] = all(item["all_primary_checks_met"] for item in criteria["by_source_arm"].values())
    criteria["fixed_denominators"] = {
        "cases": len(rows),
        "corpus_resolvable": summaries["baseline"]["baseline"]["corpus_gold_total"],
        "full": summaries["baseline"]["baseline"]["full_gold_total"],
    }
    if criteria["fixed_denominators"] != {"cases": 61, "corpus_resolvable": 116, "full": 119}:
        raise RuntimeError(f"unexpected fixed denominators: {criteria['fixed_denominators']}")

    run_artifact: dict[str, Any] = {
        "schema_version": "answer-cited-evidence-v3-regrade-v1",
        "adr_id": "ADR-0127",
        "experiment_id": "ADR-0127-experiment-v1",
        "run_id": "run-001",
        "source": {str(path.relative_to(ROOT)): digest for path, digest in EXPECTED_HASHES.items()},
        "method": "sealed deterministic coordinate projection; no provider or judge calls",
        "llm_calls": [],
        "summaries": summaries,
        "frozen_criteria": criteria,
        "rows": rows,
        "provider_calls": 0,
        "judge_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "completed_at": _now(),
    }
    run_artifact["artifact_sha256"] = _self_hash(run_artifact)
    _write_new(RUN_PATH, run_artifact)

    question_paths: list[Path] = []
    for row in rows:
        path = ADR / "실험" / row["question_file"]
        _replace_scaffold(path, _question_markdown(row))
        question_paths.append(path)
    INDEX_PATH.write_text(_experiment_index(run_artifact), encoding="utf-8")

    manifest["runs"][0].update({"status": "complete", "sha256": _sha256(RUN_PATH)})
    for question in manifest["questions"]:
        question["sha256"] = _sha256(ADR / "실험" / question["file"])
    baseline_summary = summaries["baseline"]["baseline"]
    manifest["retrieval_accounting"].update({
        "corpus_total": 16506,
        "before_filter": {arm: summaries["baseline"][arm]["selected_total"] for arm in PROJECTIONS},
        "after_filter": {arm: summaries["baseline"][arm]["selected_total"] for arm in PROJECTIONS},
        "presented_total": {arm: summaries["baseline"][arm]["selected_total"] for arm in PROJECTIONS},
        "presented_mean": {arm: summaries["baseline"][arm]["selected_mean"] for arm in PROJECTIONS},
        "presented_p50": {arm: summaries["baseline"][arm]["selected_p50"] for arm in PROJECTIONS},
        "presented_p95": {arm: summaries["baseline"][arm]["selected_p95"] for arm in PROJECTIONS},
        "golden_recall": {arm: summaries["baseline"][arm]["corpus_micro_recall"] for arm in PROJECTIONS},
        "selectivity": {arm: round((summaries["baseline"][arm]["selected_mean"] / 16506), 10) for arm in PROJECTIONS},
    })
    manifest["results"] = {
        "status": "complete",
        "by_arm": summaries,
        "comparisons": [{"declared_used_vs_presented": criteria}],
        "judge_disagreements": 0,
        "usage": {"product_calls": 0, "retrieval_calls": 0, "judge_calls": 0, "tokens": 0},
        "latency": {"deterministic_regrade_ms": run_artifact["elapsed_ms"]},
        "error_taxonomy": [
            {"type": "retrieved_gold_but_unused", "count": sum(len(row["source_arms"]["baseline"]["projections"]["answer-declared-used-v3"]["retrieved_gold_unused"]) for row in rows), "denominator": baseline_summary["corpus_gold_hits"]},
            {"type": "used_non_gold", "count": summaries["baseline"]["answer-declared-used-v3"]["used_non_gold_total"], "denominator": summaries["baseline"]["answer-declared-used-v3"]["selected_total"]},
        ],
    }
    MANIFEST_PATH.write_bytes(_canonical_bytes(manifest))

    files = [
        _artifact(RUN_PATH, "Golden61 v3 answer evidence utilization deterministic regrade"),
        _artifact(Path(__file__), "ADR-0127 deterministic regrade runner"),
        _artifact(PARENT_SEAL, "Frozen ADR-0121 product capture seal"),
        _artifact(PARENT_LEDGER, "Inherited ADR-0121 retrieval stage ledger"),
        _artifact(CM_V3, "Golden61 CM v3 minimal-sufficient evidence"),
        _artifact(FSC_V3, "Golden61 FSC v3 minimal-sufficient evidence"),
    ]
    files.extend(_artifact(path, f"Question-level answer evidence regrade {path.stem}") for path in question_paths)
    ARTIFACT_MANIFEST_PATH.write_bytes(_canonical_bytes({
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0127",
        "created_at": manifest["reservation"]["created_at"],
        "files": files,
    }))
    return run_artifact


if __name__ == "__main__":
    if sys.argv[1:] == ["--repair-records"]:
        repair_records()
        print("repaired ADR-0127 records without rerunning the experiment")
    elif sys.argv[1:]:
        raise SystemExit(f"unsupported arguments: {sys.argv[1:]}")
    else:
        print(json.dumps(run()["summaries"], ensure_ascii=False, indent=2))
