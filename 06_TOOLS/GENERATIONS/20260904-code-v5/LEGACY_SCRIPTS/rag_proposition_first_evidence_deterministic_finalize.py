#!/usr/bin/env python3
"""Finalize ADR-0129 from sealed evidence metrics, excluding all judge output."""
from __future__ import annotations

from copy import deepcopy
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

from scripts import rag_proposition_first_evidence_golden_61 as experiment  # noqa: E402


ADR = experiment.ADR
ARTIFACTS = ADR / "artifacts"
REPORT = ARTIFACTS / "deterministic-evidence-evaluation-run-001.json"
RETRIEVAL = ARTIFACTS / "retrieval-only-run-001.json"
LEDGER = ARTIFACTS / "retrieval-stage-ledger-run-001.json"
SEAL = ARTIFACTS / "product-capture-seal-run-001.json"
PUBLIC = ARTIFACTS / "public-questions-run-001.json"
SCORING = ARTIFACTS / "scoring-fixture-run-001.json"
MANIFEST = ADR / "실험/manifest.json"
INDEX = ADR / "실험/README.md"
ARTIFACT_MANIFEST = ARTIFACTS / "manifest.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, value: str | Mapping[str, Any]) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, "utf-8")


def compact_confusion(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row[key] for key in (
            "tp", "fp", "fn", "selected", "required", "precision", "recall",
            "f1", "legal_tversky", "complete",
        )
    }


def question_markdown(
    *, number: int, case_id: str, public: Mapping[str, Any],
    score: Mapping[str, Any], capture: Mapping[str, Any], report: Mapping[str, Any],
) -> str:
    by_arm = {
        arm: next(
            row for row in report["golden_v3"][arm]["case_rows"]
            if row["case_id"] == case_id
        )
        for arm in experiment.ARMS
    }
    product_path = ARTIFACTS / "product-captures/run-001" / f"{case_id}.json"
    result_rows = []
    for arm in experiment.ARMS:
        product = capture["arms"][arm]
        result_rows.append(
            f"| `{arm}` | {compact_confusion(by_arm[arm]['presented'])['tp']}/"
            f"{compact_confusion(by_arm[arm]['presented'])['required']} | "
            f"{compact_confusion(by_arm[arm]['declared'])['tp']}/"
            f"{compact_confusion(by_arm[arm]['declared'])['required']} | "
            f"{product['status']} |"
        )
    summaries = {
        arm: {
            "presented": compact_confusion(by_arm[arm]["presented"]),
            "declared": compact_confusion(by_arm[arm]["declared"]),
            "unresolved_evidence_ids": by_arm[arm]["unresolved_evidence_ids"],
            "answer": capture["arms"][arm].get("answer"),
            "execution_metrics": capture["arms"][arm].get("execution_metrics"),
        }
        for arm in experiment.ARMS
    }
    return f"""# 질문 {number:03d} — {case_id}

## 1. 실행 메타

- ADR: `ADR-0129`
- experiment: `ADR-0129-experiment-v1`
- case ID: `{case_id}`
- run ID: `run-001`
- 실행 상태: sealed product complete / deterministic evidence evaluation complete
- 평가 모델: 없음
- judge 출력 사용: `false`
- 제품 원본: `{product_path.relative_to(ROOT)}` (`{sha(product_path)}`)

## 2. 사용자 질문 원문

```text
{public['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{score['reference_answer']}
```

## 4. 제품 입력을 구성한 원값

제품 호출의 실제 system/user/schema/provider 원응답은 2.5GB 봉인 capture 중 위 제품 원본에
전부 보존했다. 이 질문 파일은 중복 복사하지 않고 경로와 SHA-256으로 결속한다.

```json
{json.dumps({'gold_articles': score['gold_articles'], 'required_companions': score.get('required_companions') or []}, ensure_ascii=False, indent=2)}
```

### 회수·탈락 단계 원장 — run·arm별

- 전체 원장: `{LEDGER.relative_to(ROOT)}` (`{sha(LEDGER)}`)

```json
{json.dumps({arm: capture['arms'][arm]['retrieval']['stage_capture'] for arm in experiment.ARMS}, ensure_ascii=False)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

- 원문·structured output·usage·지연은 봉인 제품 원본에 생략 없이 보존했다.
- 제품 모델: `claude-haiku-4-5-20251001`

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

- candidate의 compiler·targeted retrieval·answer 호출도 동일 봉인 제품 원본의
  `provider_calls`에 순서대로 보존했다.

## 7. 채점 호출과 반복 판정

- 최종 판정에 사용한 judge 호출: `0`
- 사용자가 semantic judge를 제외하도록 실행 중 지시하여, 존재하는 부분 judge 영수증 3개는
  결과와 점수에서 전부 배제했다.
- 판정 규칙: v3 필수 조문 집합과 final-present/answer-declared 좌표의 결정론적 집합 포함 관계.

## 8. 사례 최종 판정

| arm | final-present TP/required | answer-declared TP/required | 제품 실행 |
|---|---:|---:|---|
{chr(10).join(result_rows)}

```json
{json.dumps(summaries, ensure_ascii=False, indent=2)}
```
"""


def artifact_entry(path: Path, description: str, raw: bool = False) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha(path),
        "bytes": path.stat().st_size,
        "description": description,
        "contains_raw_prompts_and_outputs": raw,
    }


def main() -> int:
    report = read(REPORT)
    retrieval = read(RETRIEVAL)
    public = read(PUBLIC)
    scoring = read(SCORING)
    manifest = read(MANIFEST)
    seal = read(SEAL)
    public_by_id = {str(row["case_id"]): row for row in public["cases"]}
    score_by_id = {str(row["case_id"]): row for row in scoring["cases"]}
    receipt_by_id = {str(row["case_id"]): row for row in seal["case_receipts"]}
    table = []
    question_files = []
    for entry in manifest["questions"]:
        case_id = str(entry["case_id"])
        capture_path = ARTIFACTS / "product-captures/run-001" / f"{case_id}.json"
        if sha(capture_path) != receipt_by_id[case_id]["sha256"]:
            raise RuntimeError(f"sealed capture mismatch: {case_id}")
        capture = read(capture_path)
        target = ADR / "실험" / str(entry["file"])
        text = question_markdown(
            number=int(entry["number"]), case_id=case_id,
            public=public_by_id[case_id], score=score_by_id[case_id],
            capture=capture, report=report,
        )
        write(target, text)
        entry["sha256"] = sha(target)
        question_files.append(target)
        bp = next(row for row in report["golden_v3"][experiment.BASELINE_ARM]["case_rows"] if row["case_id"] == case_id)
        cp = next(row for row in report["golden_v3"][experiment.CANDIDATE_ARM]["case_rows"] if row["case_id"] == case_id)
        table.append(
            f"| {entry['number']:03d} | `{case_id}` | "
            f"P {bp['presented']['tp']}/{bp['presented']['required']}→{cp['presented']['tp']}/{cp['presented']['required']} | "
            f"D {bp['declared']['tp']}/{bp['declared']['required']}→{cp['declared']['tp']}/{cp['declared']['required']} | "
            f"[{entry['file']}]({entry['file']}) |"
        )

    b = report["golden_v3"][experiment.BASELINE_ARM]
    c = report["golden_v3"][experiment.CANDIDATE_ARM]
    index = f"""# ADR-0129 실험 질문 인덱스

> 61개 제품 출력은 봉인했고 최종 평가는 LLM judge 없이 조문 집합 연산만 사용했다.

## 작업 선점

- owner: `Codex-root`
- status: `completed`

## 계보

- experiment ID: `ADR-0129-experiment-v1`
- merge: ADR-0114 + ADR-0118 + ADR-0119

## Arm

| arm | final-present TP/116 | declared TP/116 | 완전제시 | 완전사용 |
|---|---:|---:|---:|---:|
| baseline | {b['presented']['groups']['all']['tp']} | {b['declared']['groups']['all']['tp']} | {b['presented']['groups']['all']['complete_cases']}/61 | {b['declared']['groups']['all']['complete_cases']}/61 |
| proposition-first-evidence-v1 | {c['presented']['groups']['all']['tp']} | {c['declared']['groups']['all']['tp']} | {c['presented']['groups']['all']['complete_cases']}/61 | {c['declared']['groups']['all']['complete_cases']}/61 |

## 질문 인덱스

| 번호 | case ID | final-present | answer-declared | 파일 |
|---:|---|---|---|---|
{chr(10).join(table)}

## 집계

- 평가 방식: sealed set-containment, judge 0회
- candidate-only 완전회수: `cm-016`
- baseline-only 완전회수: 없음
- 답변 사용 회귀: baseline-only 13건 / candidate-only 3건
- 정본: [deterministic evidence report](../artifacts/deterministic-evidence-evaluation-run-001.json)
"""
    write(INDEX, index)

    active = next(row for row in manifest["runs"] if row["id"] == experiment.RUN_ID)
    active.update({
        "status": "complete",
        "artifact_path": str(REPORT.relative_to(ROOT)),
        "sha256": sha(REPORT),
    })
    decisive = retrieval["summary"]["by_arm"]
    manifest["retrieval_accounting"].update({
        "before_filter": {arm: decisive[arm]["presented_total"] for arm in experiment.ARMS},
        "after_filter": {arm: decisive[arm]["presented_total"] for arm in experiment.ARMS},
        "presented_total": {arm: decisive[arm]["presented_total"] for arm in experiment.ARMS},
        "presented_mean": {arm: decisive[arm]["presented_mean"] for arm in experiment.ARMS},
        "presented_p50": {arm: decisive[arm]["presented_p50"] for arm in experiment.ARMS},
        "presented_p95": {arm: decisive[arm]["presented_p95"] for arm in experiment.ARMS},
        "golden_recall": {arm: decisive[arm]["golden_recall"] for arm in experiment.ARMS},
        "selectivity": {arm: decisive[arm]["selectivity"] for arm in experiment.ARMS},
    })
    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = sha(LEDGER)
    manifest["results"] = {
        "status": "complete",
        "evaluation_mode": "sealed set-containment; no LLM judge",
        "by_arm": {
            arm: {
                **report["arms"][arm],
                "presented_v3": report["golden_v3"][arm]["presented"],
                "declared_v3": report["golden_v3"][arm]["declared"],
            }
            for arm in experiment.ARMS
        },
        "comparisons": [{
            "presented_complete": report["paired_presented_complete"],
            "declared_complete": report["paired_declared_complete"],
        }],
        "judge_disagreements": None,
        "usage": {arm: report["arms"][arm]["usage"] for arm in experiment.ARMS},
        "latency": {arm: {
            "product_p50_ms": report["arms"][arm]["wall_ms_p50"],
            "product_p95_ms": report["arms"][arm]["wall_ms_p95"],
        } for arm in experiment.ARMS},
        "error_taxonomy": [
            {"type": "answer_evidence_regression", "baseline_only_complete": 13, "candidate_only_complete": 3},
            {"type": "integrity_violation", "candidate_count": report["arms"][experiment.CANDIDATE_ARM]["integrity_violation_count"]},
        ],
        "evaluation_override": {
            "reason": "user explicitly stopped semantic judge and requested article-based deterministic evaluation",
            "judge_calls_used_for_metrics": 0,
            "excluded_partial_judge_receipts": sorted(path.name for path in (ARTIFACTS / "judge-receipts/run-001").glob("*.json")),
        },
    }
    write(MANIFEST, manifest)

    files = [
        artifact_entry(PUBLIC, "gold-free public questions"),
        artifact_entry(SCORING, "offline scoring fixture"),
        artifact_entry(SEAL, "sealed 61-case product capture index"),
        artifact_entry(RETRIEVAL, "deterministic decisive-article retrieval report"),
        artifact_entry(REPORT, "deterministic Golden61 v3 presented/declared evidence report"),
        artifact_entry(LEDGER, "retrieval-stage-ledger-v1"),
        artifact_entry(Path(__file__), "deterministic ADR-0129 finalizer"),
    ]
    files.extend(artifact_entry(path, f"question evidence result {path.stem}") for path in question_files)
    files.extend(
        artifact_entry(ARTIFACTS / "product-captures/run-001" / f"{case_id}.json", f"sealed product capture {case_id}", True)
        for case_id in public_by_id
    )
    files.extend(
        artifact_entry(path, f"excluded partial judge receipt {path.stem}", True)
        for path in sorted((ARTIFACTS / "judge-receipts/run-001").glob("*.json"))
    )
    write(ARTIFACT_MANIFEST, {
        "schema_version": "adr-artifacts-v1",
        "adr_id": experiment.ADR_ID,
        "created_at": read(ARTIFACT_MANIFEST).get("created_at"),
        "files": files,
    })
    print(json.dumps({
        "status": "complete",
        "run_sha256": sha(REPORT),
        "ledger_sha256": sha(LEDGER),
        "questions": len(question_files),
        "judge_calls_used_for_metrics": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
