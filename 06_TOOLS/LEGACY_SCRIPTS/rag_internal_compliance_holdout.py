#!/usr/bin/env python3
"""ADR-0133 frozen structural holdout runner (no provider or judge calls)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import internal_compliance  # noqa: E402


DEFAULT_DATASET = ROOT / "data/review/internal_compliance_holdout_v1.json"
DEFAULT_ADR = ROOT / "docs/adr/ADR-0133-internal-rule-atomic-compliance-main"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999))
    return round(ordered[position], 3)


def run(dataset_path: Path, adr_path: Path, run_id: str) -> dict:
    source = json.loads(dataset_path.read_text(encoding="utf-8"))
    rows, latencies = [], []
    experiment_dir = adr_path / "실험"
    artifact_dir = adr_path / "artifacts"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    for case in source["cases"]:
        started = time.perf_counter()
        internal = {case["internal"]["evidence_id"]: case["internal"]["text"]}
        external = {row["evidence_id"]: row["text"] for row in case["externals"]}
        packet = internal_compliance.sanitize_compilation(
            case["compiler_output"], case["question"], internal, external)
        assessment = internal_compliance.assess_packet(packet, case["retrieval_status"])
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)
        baseline_correct = case["baseline_verdict"] == case["expected_verdict"]
        candidate_correct = assessment["verdict"] == case["expected_verdict"]
        row = {
            "case_id": case["case_id"],
            "expected_verdict": case["expected_verdict"],
            "baseline_verdict": case["baseline_verdict"],
            "candidate_verdict": assessment["verdict"],
            "baseline_correct": baseline_correct,
            "candidate_correct": candidate_correct,
            "assessment": assessment,
            "packet_validation": packet["validation"],
            "elapsed_ms": round(latency, 3),
        }
        rows.append(row)
        number = int(case["case_id"].rsplit("-", 1)[-1])
        question_path = experiment_dir / f"질문-{number:03d}-{case['case_id']}.md"
        question_path.write_text(
            "\n".join([
                f"# {case['case_id']}", "", "## 1. 실행 메타", "",
                f"- run: `{run_id}`", "- arm: `baseline`, `integrated-compliance-v1`",
                "- provider/judge calls: `0` (frozen structured replay)", "",
                "## 2. 사용자 질문 원문", "", case["question"], "",
                "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", f"채점 전용 expected verdict: `{case['expected_verdict']}`", "",
                "## 4. 제품 입력을 구성한 원값", "", "```json",
                json.dumps({"internal": case["internal"], "externals": case["externals"],
                            "retrieval_status": case["retrieval_status"]}, ensure_ascii=False, indent=2),
                "```", "", "### 회수·탈락 단계 원장 — run·arm별", "",
                "retrieval은 ADR-0125에서 동결되어 이 run에서는 후보를 생성·추가·삭제하지 않았다.", "",
                "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
                "제품 모델 호출 없음. 아래는 사전 동결된 compiler payload replay다.", "", "```json",
                json.dumps(case["compiler_output"], ensure_ascii=False, indent=2), "```", "",
                "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
                "중간 LLM 호출 없음. 아래는 closed-ID·exact-quote sanitizer와 coverage gate 출력이다.", "", "```json",
                json.dumps({"packet": packet, "assessment": assessment}, ensure_ascii=False, indent=2),
                "```", "", "## 7. 채점 호출과 반복 판정", "",
                "채점 모델 호출 없음. 동결 expected verdict와 결정론적으로 1회 비교했다.", "",
                "## 8. 사례 최종 판정", "",
                f"- baseline: `{case['baseline_verdict']}` ({'correct' if baseline_correct else 'wrong'})",
                f"- candidate: `{assessment['verdict']}` ({'correct' if candidate_correct else 'wrong'})",
            ]) + "\n", encoding="utf-8")

    baseline_correct = sum(row["baseline_correct"] for row in rows)
    candidate_correct = sum(row["candidate_correct"] for row in rows)
    comparison = {
        "candidate_only": sum(row["candidate_correct"] and not row["baseline_correct"] for row in rows),
        "baseline_only": sum(row["baseline_correct"] and not row["candidate_correct"] for row in rows),
        "both_correct": sum(row["baseline_correct"] and row["candidate_correct"] for row in rows),
        "both_wrong": sum(not row["baseline_correct"] and not row["candidate_correct"] for row in rows),
    }
    result = {
        "schema_version": "adr-0133-run-v1",
        "run_id": run_id,
        "dataset": str(dataset_path.relative_to(ROOT)),
        "dataset_sha256": _sha(dataset_path),
        "provider_calls": 0,
        "judge_calls": 0,
        "baseline": {"correct": baseline_correct, "total": len(rows)},
        "candidate": {"correct": candidate_correct, "total": len(rows)},
        "comparison": comparison,
        "validation": {
            "unsafe_compliant": [row["case_id"] for row in rows
                                 if row["candidate_verdict"] == "부합" and (
                                     row["assessment"]["invalid_count"]
                                     or row["assessment"]["unresolved_requirement_ids"]
                                     or row["assessment"]["retrieval_status"] != "ok")],
            "closed_id_accepted": [],
            "exact_quote_accepted": [],
        },
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "cases": rows,
    }
    output = artifact_dir / f"{run_id}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["artifact_path"] = str(output.relative_to(ROOT))
    result["artifact_sha256"] = _sha(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--adr", type=Path, default=DEFAULT_ADR)
    parser.add_argument("--run-id", default="run-002")
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.adr, args.run_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
