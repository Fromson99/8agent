#!/usr/bin/env python3
"""Finalize ADR-0130 deterministic A/B/C evidence experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_evidence_slot_nondropping_golden_61 as run  # noqa: E402


ADR = run.ADR
ART = ADR / "artifacts"
REPORT = ART / "run-001.json"
LEDGER = ART / "retrieval-stage-ledger-run-001.json"
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
        "path": str(path.relative_to(ROOT)), "sha256": sha(path),
        "bytes": path.stat().st_size, "description": description,
        "contains_raw_prompts_and_outputs": raw,
    }


def confusion(report: Mapping[str, Any], arm: str, case_id: str, key: str) -> Mapping[str, Any]:
    row = next(item for item in report["evidence"][arm]["case_rows"] if item["case_id"] == case_id)
    return row[key]


def question_text(number, case_id, question, reference, capture_path, report):
    rows = []
    detail = {}
    for arm in run.ARMS:
        p = confusion(report, arm, case_id, "presented")
        b = confusion(report, arm, case_id, "bound")
        d = confusion(report, arm, case_id, "declared")
        rows.append(f"| `{arm}` | {p['tp']}/{p['required']} | {b['tp']}/{b['required']} | {d['tp']}/{d['required']} |")
        detail[arm] = {"presented": p, "bound": b, "declared": d}
    return f"""# 질문 {number:03d} — {case_id}

## 1. 실행 메타

- ADR: `ADR-0130`
- run: `run-001`
- 평가: 조문 집합 결정론 평가, judge 0회
- 제품 원본: `{capture_path.relative_to(ROOT)}` (`{sha(capture_path)}`)

## 2. 사용자 질문 원문

```text
{question}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{reference}
```

## 4. 제품 입력을 구성한 원값

- A는 ADR-0129/0118 봉인 기준선, B/C는 봉인 compiler 결과에 새 slot answer만 호출했다.
- 실제 system/user/schema/provider 원응답은 위 제품 원본에 SHA-256으로 결속해 보존한다.

### 회수·탈락 단계 원장 — run·arm별

- 전체 원장: `{LEDGER.relative_to(ROOT)}` (`{sha(LEDGER)}`)

## 5. 제품 모델 호출 — run·arm별 실제 원문

- A: 재호출 없음, 부모 영수증 상속
- B/C: `claude-haiku-4-5-20251001` slot answer 각 1회
- 생략 없는 원문과 응답은 1.1GB 봉인 capture에 보존한다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

- 새 중간 호출 없음. ADR-0129의 hash-sealed initial/final compiler 원출력을 재사용했다.

## 7. 채점 호출과 반복 판정

- semantic judge 호출: 0
- v3 필수 조문과 presented/bound/declared 좌표의 집합 포함 관계만 계산했다.

## 8. 사례 최종 판정

| arm | presented TP/required | slot-bound TP/required | declared TP/required |
|---|---:|---:|---:|
{chr(10).join(rows)}

```json
{json.dumps(detail, ensure_ascii=False, indent=2)}
```
"""


def decisive_metrics(captures, scoring):
    score = {str(row["case_id"]): row for row in scoring["cases"]}
    output = {}
    for arm in run.ARMS:
        counts, hits, total = [], 0, 0
        for capture in captures:
            after = capture["arms"][arm]["retrieval"]["stage_capture"]["stages"][-1]["after"]
            selected = {(str(row["doc_id"]), int(row["node"])) for row in after}
            required = {(str(row["doc_id"]), int(row["node"])) for row in score[capture["case_id"]]["gold_articles"]}
            counts.append(len(selected)); hits += len(selected & required); total += len(required)
        ordered = sorted(counts)
        output[arm] = {
            "presented_total": sum(counts), "presented_mean": statistics.mean(counts),
            "presented_p50": statistics.median(counts),
            "presented_p95": ordered[round((len(ordered) - 1) * .95)],
            "golden_recall": hits / total,
            "selectivity": statistics.mean(counts) / 16506,
        }
    return output


def main() -> int:
    report = read(REPORT); public = read(PUBLIC); scoring = read(SCORING)
    manifest = read(MANIFEST); seal = read(SEAL)
    score = {str(row["case_id"]): row for row in scoring["cases"]}
    receipts = {str(row["case_id"]): row for row in seal["case_receipts"]}
    captures = []
    question_files = []
    table = []
    for row in manifest["questions"]:
        case_id = str(row["case_id"])
        path = ART / "product-captures/run-001" / f"{case_id}.json"
        if sha(path) != receipts[case_id]["sha256"]:
            raise RuntimeError(f"capture hash mismatch: {case_id}")
        capture = read(path); captures.append(capture)
        target = ADR / "실험" / row["file"]
        write(target, question_text(
            int(row["number"]), case_id, capture["question"],
            score[case_id]["reference_answer"], path, report,
        ))
        row["sha256"] = sha(target); question_files.append(target)
        values = [confusion(report, arm, case_id, "declared")["tp"] for arm in run.ARMS]
        required = confusion(report, run.BASELINE_ARM, case_id, "declared")["required"]
        table.append(f"| {row['number']:03d} | `{case_id}` | {values[0]}/{required} | {values[1]}/{required} | {values[2]}/{required} | [{row['file']}]({row['file']}) |")

    index = f"""# ADR-0130 실험 질문 인덱스

> required evidence-slot non-dropping A/B/C, Golden61 v3, semantic judge 0회.

## 작업 선점

- owner: `Codex-root`
- status: `completed`

## 계보

- ADR-0118 baseline + ADR-0129 bounded targeted retrieval
- 최종 선택: `ADR-0118-experiment-v1/integrated-atomic-claim-v4b`

## Arm 집계

| arm | presented TP/116 | bound TP/116 | declared TP/116 | 완전사용 |
|---|---:|---:|---:|---:|
{chr(10).join(f"| {arm} | {report['evidence'][arm]['presented']['groups']['all']['tp']} | {report['evidence'][arm]['bound']['groups']['all']['tp']} | {report['evidence'][arm]['declared']['groups']['all']['tp']} | {report['evidence'][arm]['declared']['groups']['all']['complete_cases']}/61 |" for arm in run.ARMS)}

## 질문 인덱스

| 번호 | case | baseline | slot-only | slot-targeted | 파일 |
|---:|---|---:|---:|---:|---|
{chr(10).join(table)}
"""
    write(INDEX, index)
    decisive = decisive_metrics(captures, scoring)
    active = next(item for item in manifest["runs"] if item["id"] == run.RUN_ID)
    active.update({"status": "complete", "sha256": sha(REPORT)})
    manifest["retrieval_accounting"].update({
        "before_filter": {arm: decisive[arm]["presented_total"] for arm in run.ARMS},
        "after_filter": {arm: decisive[arm]["presented_total"] for arm in run.ARMS},
        **{key: {arm: decisive[arm][key] for arm in run.ARMS} for key in (
            "presented_total", "presented_mean", "presented_p50", "presented_p95",
            "golden_recall", "selectivity",
        )},
    })
    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = sha(LEDGER)
    manifest["results"] = {
        "status": "complete", "evaluation_mode": report["evaluation_mode"],
        "selected_structure": report["selected_structure"],
        "by_arm": {arm: {
            "runtime": report["runtime"][arm],
            "presented": report["evidence"][arm]["presented"],
            "bound": report["evidence"][arm]["bound"],
            "declared": report["evidence"][arm]["declared"],
        } for arm in run.ARMS},
        "comparisons": report["paired"], "criteria": report["criteria"],
        "judge_disagreements": None,
        "usage": {arm: report["runtime"][arm]["inclusive_usage"] for arm in run.ARMS},
        "latency": {arm: {
            "p50_ms": report["runtime"][arm]["product_p50_ms"],
            "p95_ms": report["runtime"][arm]["product_p95_ms"],
        } for arm in run.ARMS},
        "error_taxonomy": [{
            "type": "upstream_slot_underselection",
            "baseline_declared_tp": 67, "slot_only_tp": 35, "slot_targeted_tp": 39,
        }],
    }
    write(MANIFEST, manifest)
    files = [
        entry(PUBLIC, "gold-free public questions"), entry(SCORING, "offline scoring fixture"),
        entry(SEAL, "sealed product captures"), entry(REPORT, "deterministic A/B/C evidence report"),
        entry(LEDGER, "retrieval-stage-ledger-v1"), entry(Path(__file__), "ADR-0130 deterministic finalizer"),
    ]
    files.extend(entry(path, f"question result {path.stem}") for path in question_files)
    files.extend(entry(ART / "product-captures/run-001" / f"{case_id}.json", f"sealed product capture {case_id}", True) for case_id in receipts)
    write(ARTIFACT_MANIFEST, {
        "schema_version": "adr-artifacts-v1", "adr_id": run.ADR_ID,
        "created_at": read(ARTIFACT_MANIFEST).get("created_at"), "files": files,
    })
    print(json.dumps({
        "status": "complete", "questions": len(question_files),
        "selected_structure": report["selected_structure"], "judge_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
