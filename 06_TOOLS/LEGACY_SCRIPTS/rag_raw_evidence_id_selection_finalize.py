#!/usr/bin/env python3
"""Finalize ADR-0131 deterministic raw evidence-ID selection experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_raw_evidence_id_selection_golden_61 as run  # noqa: E402


ADR = run.ADR
ART = ADR / "artifacts"
REPORT = ART / "run-001.json"
SEAL = ART / "product-capture-seal-run-001.json"
PUBLIC = ART / "public-questions-run-001.json"
SCORING = ART / "scoring-fixture-run-001.json"
MANIFEST = ADR / "실험/manifest.json"
INDEX = ADR / "실험/README.md"
ARTIFACT_MANIFEST = ART / "manifest.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def write(path: Path, value: str | Mapping[str, Any]) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, "utf-8")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entry(path: Path, description: str, raw: bool = False) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": sha(path),
        "bytes": path.stat().st_size,
        "description": description,
        "contains_raw_prompts_and_outputs": raw,
    }


def confusion(report, arm, case_id, key):
    row = next(item for item in report["evidence"][arm]["case_rows"] if item["case_id"] == case_id)
    return row[key]


def question_text(number, case_id, capture_path, reference, report):
    capture = read(capture_path)
    baseline = confusion(report, run.BASELINE_ARM, case_id, "declared")
    candidate = confusion(report, run.CANDIDATE_ARM, case_id, "declared")
    product = capture["arms"][run.CANDIDATE_ARM]
    call = product["provider_calls"][0]
    output = product["answer"]
    return f"""# 질문 {number:03d} — {case_id}

## 1. 실행 메타

- ADR/run/arm: `ADR-0131/run-001/{run.CANDIDATE_ARM}`
- 모델: `claude-haiku-4-5-20251001`, 제품 호출 1회
- 평가: Golden61 v3 조문 집합 결정론 평가, semantic judge 0회
- product capture 상태: `sealed exact`
- 제품 원본: `{capture_path.relative_to(ROOT)}` (`{sha(capture_path)}`)

## 2. 사용자 질문 원문

```text
{capture['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{reference}
```

## 4. 제품 입력을 구성한 원값

- ADR-0118 run-002의 동일 좌표·순서·본문 28개를 사용했다.
- compiler, Wiki, issue, role, claim, coverage, score, 검색 경위와 정의 부록은 입력하지 않았다.
- 실제 28개 전문, E ID map, system/user/schema는 위 sealed capture의
  `arms.{run.CANDIDATE_ARM}.provider_calls[0]`에 생략 없이 보존했다.
- 입력 SHA-256: `{product['retrieval']['meta']['input_sha256']}`
- 부모 회수 원장: `{run.PARENT_ADR.relative_to(ROOT)}/artifacts/retrieval-stage-ledger-run-002.json`

### 회수·탈락 단계 원장 — run·arm별

- candidate는 부모 arm의 회수 결과 28개를 좌표·순서·본문 그대로 상속했다.
- 새 회수, 탈락, 점수 변경은 없으며 상속 원장과 SHA-256은 위 부모 회수 원장 및 sealed
  capture에 보존했다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

### System

```text
{call['system']}
```

### User·schema·provider 원응답

53MB의 61개 capture 안에 exact payload로 보존한다. 이 질문의 원본 경로와 hash는 위 실행
메타에 있으며, structured output은 다음과 같다.

```json
{json.dumps(output, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

없음. 봉인된 28개를 그대로 사용했으며 새 호출은 위 최종 답변 1회뿐이다.

## 7. 채점 호출과 반복 판정

- semantic judge 호출: 0
- 제품 seal을 닫은 뒤 v3 필수 조문과 answer-declared ID가 가리킨 좌표의 집합만 비교했다.

## 8. 사례 최종 판정

| arm | TP | FP | FN | complete |
|---|---:|---:|---:|---:|
| baseline | {baseline['tp']} | {baseline['fp']} | {baseline['fn']} | {str(baseline['complete']).lower()} |
| raw direct | {candidate['tp']} | {candidate['fp']} | {candidate['fn']} | {str(candidate['complete']).lower()} |
"""


def main() -> int:
    report = read(REPORT)
    manifest = read(MANIFEST)
    seal = read(SEAL)
    scoring = read(SCORING)
    scores = {str(row["case_id"]): row for row in scoring["cases"]}
    receipts = {str(row["case_id"]): row for row in seal["case_receipts"]}
    question_files = []
    table = []
    for row in manifest["questions"]:
        case_id = str(row["case_id"])
        capture_path = ART / "product-captures/run-001" / f"{case_id}.json"
        if sha(capture_path) != receipts[case_id]["sha256"]:
            raise RuntimeError(f"capture hash mismatch: {case_id}")
        target = ADR / "실험" / row["file"]
        write(target, question_text(
            int(row["number"]), case_id, capture_path,
            scores[case_id]["reference_answer"], report,
        ))
        row["sha256"] = sha(target)
        question_files.append(target)
        baseline = confusion(report, run.BASELINE_ARM, case_id, "declared")
        candidate = confusion(report, run.CANDIDATE_ARM, case_id, "declared")
        table.append(
            f"| {row['number']:03d} | `{case_id}` | {baseline['tp']}/{baseline['required']} | "
            f"{candidate['tp']}/{candidate['required']} | {candidate['fp']} | "
            f"[{row['file']}]({row['file']}) |"
        )

    base_all = report["evidence"][run.BASELINE_ARM]["declared"]["groups"]["all"]
    cand_all = report["evidence"][run.CANDIDATE_ARM]["declared"]["groups"]["all"]
    index = f"""# ADR-0131 실험 질문 인덱스

> 동일 28개 원문에서 compiler 없이 Haiku가 답변과 사용 evidence ID를 직접 선언한 Golden61
> v3 probe. semantic judge는 호출하지 않았다.

## 집계

| arm | TP/116 | FP | FN | precision | recall | complete |
|---|---:|---:|---:|---:|---:|---:|
| baseline | {base_all['tp']} | {base_all['fp']} | {base_all['fn']} | {base_all['precision']:.2%} | {base_all['recall']:.2%} | {base_all['complete_cases']}/61 |
| raw direct | {cand_all['tp']} | {cand_all['fp']} | {cand_all['fn']} | {cand_all['precision']:.2%} | {cand_all['recall']:.2%} | {cand_all['complete_cases']}/61 |

## Paired complete

- candidate-only: {', '.join(report['paired']['gained'])}
- baseline-only: {', '.join(report['paired']['lost'])}

## 질문 인덱스

| 번호 | case | baseline TP/required | raw TP/required | raw FP | 파일 |
|---:|---|---:|---:|---:|---|
{chr(10).join(table)}
"""
    write(INDEX, index)

    active = next(item for item in manifest["runs"] if item["id"] == run.RUN_ID)
    active.update({"status": "complete", "sha256": sha(REPORT)})
    manifest["results"] = {
        "status": "complete",
        "evaluation_mode": report["evaluation_mode"],
        "selected_structure": report["selected_structure"],
        "by_arm": {
            arm: {
                "runtime": report["runtime"][arm],
                "presented": report["evidence"][arm]["presented"],
                "declared": report["evidence"][arm]["declared"],
            }
            for arm in run.ARMS
        },
        "comparisons": report["paired"],
        "criteria": report["criteria"],
        "judge_disagreements": 0,
        "usage": {
            run.BASELINE_ARM: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "provider_duration_ms": 0, "errors": 0},
            run.CANDIDATE_ARM: report["runtime"][run.CANDIDATE_ARM]["usage"],
        },
        "latency": {
            run.BASELINE_ARM: {"p50_ms": 0, "p95_ms": 0, "sealed_parent_reuse": True},
            run.CANDIDATE_ARM: {
                "p50_ms": report["runtime"][run.CANDIDATE_ARM]["provider_p50_ms"],
                "p95_ms": report["runtime"][run.CANDIDATE_ARM]["provider_p95_ms"],
            },
        },
        "error_taxonomy": [
            {"type": "governing_rule_selection", "baseline_only_complete": report["paired"]["lost"]},
            {"type": "closed_id_violation", "count": report["runtime"][run.CANDIDATE_ARM]["invalid_evidence_ids"], "case_id": "cm-023", "invalid_id": "E31"},
            {"type": "hard_set_regression", "baseline_recall": 0.66666667, "candidate_recall": 0.61111111},
        ],
    }
    write(MANIFEST, manifest)

    files = [
        entry(PUBLIC, "gold-free public questions"),
        entry(SCORING, "offline scoring fixture"),
        entry(SEAL, "61-case product capture seal"),
        entry(REPORT, "deterministic evidence confusion report"),
        entry(ROOT / "06_TOOLS/LEGACY_SCRIPTS/rag_raw_evidence_id_selection_golden_61.py", "ADR-0131 runner"),
        entry(ROOT / "06_TOOLS/LEGACY_SCRIPTS/rag_raw_evidence_id_selection_finalize.py", "ADR-0131 finalizer"),
        entry(Path(__import__("lawrag").__file__).resolve().parent / "core/rag/raw_evidence_selection.py", "compiler-free raw selector"),
        entry(ROOT / "05_TESTS/LEGACY_TESTS/rag/test_raw_evidence_selection.py", "focused raw selector tests"),
        entry(run.PARENT_ADR / "artifacts/retrieval-stage-ledger-run-002.json", "inherited ADR-0118 retrieval-stage ledger"),
    ]
    files.extend(entry(path, f"question result {path.stem}") for path in question_files)
    files.extend(
        entry(ART / "product-captures/run-001" / f"{case_id}.json", f"sealed raw product capture {case_id}", True)
        for case_id in receipts
    )
    write(ARTIFACT_MANIFEST, {
        "schema_version": "adr-artifacts-v1",
        "adr_id": run.ADR_ID,
        "created_at": read(ARTIFACT_MANIFEST).get("created_at"),
        "files": files,
    })
    print(json.dumps({
        "status": "complete",
        "questions": len(question_files),
        "selected_structure": report["selected_structure"],
        "judge_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
