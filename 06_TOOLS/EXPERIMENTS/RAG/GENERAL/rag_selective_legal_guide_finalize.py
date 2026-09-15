#!/usr/bin/env python3
"""Finalize ADR-0132 selective legal-guide Golden61 experiment."""

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

from scripts import rag_selective_legal_guide_golden_61 as run  # noqa: E402


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


def confusion(report, arm, case_id):
    row = next(item for item in report["evidence"][arm]["case_rows"] if item["case_id"] == case_id)
    return row["declared"]


def question_text(number, case_id, capture_path, reference, report):
    capture = read(capture_path)
    raw = confusion(report, run.RAW_ARM, case_id)
    full = confusion(report, run.FULL_ARM, case_id)
    candidate = confusion(report, run.CANDIDATE_ARM, case_id)
    product = capture["arms"][run.CANDIDATE_ARM]
    call = product["provider_calls"][0]
    output = product["answer"]
    guide = product["retrieval"]["meta"]["guide"]
    return f"""# 질문 {number:03d} — {case_id}

## 1. 실행 메타

- ADR/run/arm: `ADR-0132/run-001/{run.CANDIDATE_ARM}`
- 모델: `claude-haiku-4-5-20251001`, 새 제품 호출 1회
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
- 가이드는 ADR-0118 sealed compiler packet에서 non-CONTEXT exact-quote unit만 결정론적으로
  투영했으며 후보를 추가·삭제·재정렬하지 않았다.
- guide 요약: issues `{len(guide['issues'])}`, units `{len(guide['units'])}`,
  typed links `{len(guide['legal_links'])}`, unresolved issues `{len(guide['unresolved_issues'])}`.
- 실제 28개 전문, guide, E ID map, system/user/schema/provider 원응답은 위 sealed capture의
  `arms.{run.CANDIDATE_ARM}.provider_calls[0]`에 보존했다.
- 입력 SHA-256: `{product['retrieval']['meta']['input_sha256']}`
- 부모 회수 원장: `{run.prior.PARENT_ADR.relative_to(ROOT)}/artifacts/retrieval-stage-ledger-run-002.json`

### 회수·탈락 단계 원장 — run·arm별

- 세 arm 모두 부모의 최종 28개를 그대로 상속했다.
- 새 회수·탈락·점수 변경은 0이며 가이드도 후보 집합을 바꾸지 않았다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

### System

```text
{call['system']}
```

### User·schema·provider 원응답

대용량 exact payload는 위 sealed JSON에 원문 그대로 보존한다. structured output과 검증 결과는
다음과 같다.

```json
{json.dumps(output, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

새 중간 호출은 없다. 선별 가이드는 ADR-0118의 이미 봉인된 compiler packet에서 코드로
투영했다. 부모 compiler 원문은 ADR-0118 질문 capture에 보존되어 있다.

## 7. 채점 호출과 반복 판정

- semantic judge 호출: 0
- 제품 seal 이후 v3 필수 조문과 answer-declared E ID 좌표 집합만 비교했다.

## 8. 사례 최종 판정

| arm | TP | FP | FN | complete |
|---|---:|---:|---:|---:|
| raw parent | {raw['tp']} | {raw['fp']} | {raw['fn']} | {str(raw['complete']).lower()} |
| full compiler parent | {full['tp']} | {full['fp']} | {full['fn']} | {str(full['complete']).lower()} |
| selective guide | {candidate['tp']} | {candidate['fp']} | {candidate['fn']} | {str(candidate['complete']).lower()} |
"""


def main() -> int:
    report = read(REPORT)
    manifest = read(MANIFEST)
    seal = read(SEAL)
    scoring = read(SCORING)
    scores = {str(row["case_id"]): row for row in scoring["cases"]}
    receipts = {str(row["case_id"]): row for row in seal["case_receipts"]}
    question_files: list[Path] = []
    table: list[str] = []
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
        raw = confusion(report, run.RAW_ARM, case_id)
        full = confusion(report, run.FULL_ARM, case_id)
        candidate = confusion(report, run.CANDIDATE_ARM, case_id)
        table.append(
            f"| {row['number']:03d} | `{case_id}` | {raw['tp']}/{raw['required']} | "
            f"{full['tp']}/{full['required']} | {candidate['tp']}/{candidate['required']} | "
            f"{candidate['fp']} | [{row['file']}]({row['file']}) |"
        )

    metrics = {
        arm: report["evidence"][arm]["declared"]["groups"]["all"] for arm in run.ARMS
    }
    index = f"""# ADR-0132 실험 질문 인덱스

> 동일 28개 원문에서 raw, full compiler, selective guide의 answer-declared evidence를
> Golden61 v3로 결정론 비교했다. semantic judge는 호출하지 않았다.

## 집계

| arm | TP/116 | FP | FN | precision | recall | F1 | complete |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw parent | {metrics[run.RAW_ARM]['tp']} | {metrics[run.RAW_ARM]['fp']} | {metrics[run.RAW_ARM]['fn']} | {metrics[run.RAW_ARM]['precision']:.2%} | {metrics[run.RAW_ARM]['recall']:.2%} | {metrics[run.RAW_ARM]['f1']:.2%} | {metrics[run.RAW_ARM]['complete_cases']}/61 |
| full compiler | {metrics[run.FULL_ARM]['tp']} | {metrics[run.FULL_ARM]['fp']} | {metrics[run.FULL_ARM]['fn']} | {metrics[run.FULL_ARM]['precision']:.2%} | {metrics[run.FULL_ARM]['recall']:.2%} | {metrics[run.FULL_ARM]['f1']:.2%} | {metrics[run.FULL_ARM]['complete_cases']}/61 |
| selective guide | {metrics[run.CANDIDATE_ARM]['tp']} | {metrics[run.CANDIDATE_ARM]['fp']} | {metrics[run.CANDIDATE_ARM]['fn']} | {metrics[run.CANDIDATE_ARM]['precision']:.2%} | {metrics[run.CANDIDATE_ARM]['recall']:.2%} | {metrics[run.CANDIDATE_ARM]['f1']:.2%} | {metrics[run.CANDIDATE_ARM]['complete_cases']}/61 |

## Paired complete

- vs full candidate-only: {', '.join(report['paired']['vs_full_compiler']['gained'])}
- vs full parent-only: {', '.join(report['paired']['vs_full_compiler']['lost'])}
- vs raw candidate-only: {', '.join(report['paired']['vs_raw']['gained'])}
- vs raw parent-only: {', '.join(report['paired']['vs_raw']['lost'])}

## 질문 인덱스

| 번호 | case | raw TP/required | full TP/required | selective TP/required | selective FP | 파일 |
|---:|---|---:|---:|---:|---:|---|
{chr(10).join(table)}
"""
    write(INDEX, index)

    active = next(item for item in manifest["runs"] if item["id"] == run.RUN_ID)
    active.update({"status": "complete", "artifact_path": str(REPORT.relative_to(ROOT)), "sha256": sha(REPORT)})
    runtime = report["runtime"][run.CANDIDATE_ARM]
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
            run.RAW_ARM: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "provider_duration_ms": 0, "errors": 0},
            run.FULL_ARM: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "provider_duration_ms": 0, "errors": 0},
            run.CANDIDATE_ARM: runtime["usage"],
        },
        "latency": {
            run.RAW_ARM: {"p50_ms": 0, "p95_ms": 0, "sealed_parent_reuse": True},
            run.FULL_ARM: {"p50_ms": 0, "p95_ms": 0, "sealed_parent_reuse": True},
            run.CANDIDATE_ARM: {"p50_ms": runtime["provider_p50_ms"], "p95_ms": runtime["provider_p95_ms"]},
        },
        "error_taxonomy": [
            {"type": "governing_rule_selection", "full_parent_only_complete": report["paired"]["vs_full_compiler"]["lost"]},
            {"type": "over_selection", "candidate_fp": metrics[run.CANDIDATE_ARM]["fp"], "full_fp": metrics[run.FULL_ARM]["fp"], "raw_fp": metrics[run.RAW_ARM]["fp"]},
            {"type": "closed_id_violation", "count": runtime["invalid_evidence_ids"]},
            {"type": "selection_trace_span_violation", "question_span": runtime["question_span_violations"], "quote": runtime["quote_violations"]},
            {"type": "legal_link_unavailable", "count": runtime["guide_legal_links"]},
        ],
    }
    write(MANIFEST, manifest)

    files = [
        entry(PUBLIC, "gold-free public questions"),
        entry(SCORING, "offline scoring fixture"),
        entry(SEAL, "61-case product capture seal"),
        entry(REPORT, "deterministic evidence confusion report"),
        entry(ROOT / "06_TOOLS/EXPERIMENTS/RAG/RETRIEVAL/rag_selective_legal_guide_golden_61.py", "ADR-0132 runner"),
        entry(ROOT / "06_TOOLS/EXPERIMENTS/RAG/GENERAL/rag_selective_legal_guide_finalize.py", "ADR-0132 finalizer"),
        entry(Path(__import__("lawrag").__file__).resolve().parent / "core/rag/selective_legal_guide.py", "selective non-binding legal guide"),
        entry(ROOT / "05_TESTS/REGRESSION/rag/test_selective_legal_guide.py", "focused selective guide tests"),
        entry(run.prior.PARENT_ADR / "artifacts/retrieval-stage-ledger-run-002.json", "inherited ADR-0118 retrieval-stage ledger"),
    ]
    files.extend(entry(path, f"question result {path.stem}") for path in question_files)
    files.extend(
        entry(ART / "product-captures/run-001" / f"{case_id}.json", f"sealed selective-guide capture {case_id}", True)
        for case_id in receipts
    )
    write(ARTIFACT_MANIFEST, {
        "schema_version": "adr-artifacts-v1",
        "adr_id": run.ADR_ID,
        "created_at": read(ARTIFACT_MANIFEST).get("created_at"),
        "files": files,
    })
    print(json.dumps({
        "status": "complete", "questions": len(question_files),
        "selected_structure": report["selected_structure"], "judge_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
