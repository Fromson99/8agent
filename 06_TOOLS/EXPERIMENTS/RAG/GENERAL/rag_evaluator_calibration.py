#!/usr/bin/env python3
"""Calibrate offline semantic evaluators on 32 frozen gold/full answers."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
from typing import Any


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM  # noqa: E402
from scripts.adr_structure import (  # noqa: E402
    HAIKU_MODEL,
    OPUS_MODEL,
    SONNET_MODEL,
    scaffold_adr,
)


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0047-offline-evaluator-calibration"
SOURCE = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_hard_distractor_wrong16_v1.json"
REGRADE = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_hard_distractor_regrade3_v1.json"
PARENT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0046-role-separated-evaluator-model-policy/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-items.json"
OUTPUT = ADR / "artifacts/calibration-results.json"
MODELS = (SONNET_MODEL, OPUS_MODEL)

SYSTEM = (
    "너는 제품 경로와 완전히 격리된 법률 답변 의미 채점자다. [기준답변]은 현업이 "
    "확정한 정답이며 제품에는 제공되지 않았다. [시스템 답변]이 질문에 대해 기준답변의 "
    "결론, 적용 대상, 필수 조건·예외, 수치·기간을 모두 충족하고 모순하지 않을 때만 "
    "correct=true다. 첫 예/아니오보다 답변 전체를 보고 이중부정을 정규화한다. 결론이 "
    "맞아도 질문이 요구한 핵심 조건·예외·수치·기간을 빠뜨리면 false다. 기준답변 자체가 "
    "현행 근거와 충돌하거나 질문에 답하지 않는 것으로 의심될 때만 gold_drift_suspected=true로 "
    "표시하되 임의로 새 법률지식을 정답에 추가하지 않는다. 짧고 검증 가능한 이유를 쓴다."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "conclusion_correct": {"type": "boolean"},
        "materially_complete": {"type": "boolean"},
        "no_material_error": {"type": "boolean"},
        "gold_drift_suspected": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
        "missing_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["correct", "conclusion_correct", "materially_complete",
                 "no_material_error", "gold_drift_suspected", "confidence", "reason",
                 "missing_points"],
    "additionalProperties": False,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _user(item: dict[str, Any]) -> str:
    return (
        f"[질문]\n{item['question']}\n\n[기준답변]\n{item['reference_answer']}\n\n"
        f"[시스템 답변]\n{item['answer']}\n\n"
        "기준답변과 시스템 답변의 표현 유사성이 아니라 법률 명제의 동일성을 판정한다."
    )


def _items() -> list[dict[str, Any]]:
    source = json.loads(SOURCE.read_text("utf-8"))
    regrade_blob = json.loads(REGRADE.read_text("utf-8"))
    regrades = {
        str(row["case_no"]): row
        for row in regrade_blob.get("rows", [])
        if row.get("run_name") == SOURCE.stem
    }
    items: list[dict[str, Any]] = []
    for row in sorted(source["rows"], key=lambda value: value["case_no"]):
        case_no = str(row["case_no"])
        for variant in ("gold_only", "full_original"):
            value = row["variants"][variant]
            answer = str((value.get("output") or {}).get("answer") or "")
            three = (regrades.get(case_no, {}).get("grades", {}).get(variant) or {})
            item_id = f"cal-{case_no.replace('-', '')}-{variant.replace('_', '-')}"
            items.append({
                "id": item_id,
                "case_no": case_no,
                "variant": variant,
                "question": row["question"],
                "reference_answer": row["reference_answer"],
                "answer": answer,
                "source_initial_haiku": bool(value["grade"]["correct"]),
                "haiku_three_vote": three.get("correct"),
                "source_path": str(SOURCE.relative_to(ROOT)),
                "source_sha256": _sha(SOURCE),
            })
    return items


def prepare() -> None:
    items = _items()
    if not ADR.exists():
        scaffold_adr(
            ROOT / "07_DOCS/REFERENCE/adr", 47, "offline-evaluator-calibration",
            "오프라인 의미 채점 모델 교정", "probe", [row["id"] for row in items],
            branch_id="evaluator-calibration",
            candidate_arms=["sonnet-single", "opus-single", "sonnet-opus-cascade"],
            parent_manifest=PARENT, parent_arm="role-separated", parent_relation="extends",
            judge_model=OPUS_MODEL,
        )
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({
        "schema_version": "offline-evaluator-calibration-items-v1",
        "selection_rule": "ADR-0039 wrong16의 gold_only/full_original 32개 답변 전수",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": _sha(SOURCE),
        "items": items,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["design"].update({
        "hypothesis": "Sonnet 또는 Opus 단일 채점이 Haiku 채점 불일치 검토량과 호출 수를 줄인다.",
        "primary_metric": "모델 간 판정 일치·불일치, known conflict 검출, 호출당 지연",
        "success_criteria": "32개 전수 무오류, cm-036 명백 충돌 false-pass 0, 강한 모델 간 불일치 전수 보존",
        "failure_criteria": "호출 오류 또는 알려진 명백 충돌을 강한 모델이 모두 정답 처리",
        "criteria_frozen_before_run": True,
    })
    manifest["dataset"].update({
        "name": "ADR-0039 frozen gold/full semantic answers",
        "version": "wrong16-v1 / 32 answers",
        "frozen_source": str(FROZEN.relative_to(ROOT)),
        "sha256": _sha(FROZEN),
        "legal_version_checked": False,
        "reference_version_checked": False,
    })
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "sonnet-judge", "class": "offline_evaluator", "model": SONNET_MODEL,
         "repeats": 1},
        {"role": "opus-judge", "class": "offline_evaluator", "model": OPUS_MODEL,
         "repeats": 1},
    ]
    manifest["runs"][0].update({
        "arm_ids": ["baseline", "sonnet-single", "opus-single", "sonnet-opus-cascade"],
        "selection_rule": "동결 16건의 gold-only/full 답변 32개 전수; 답변 재생성 없음",
        "artifact_path": str(OUTPUT.relative_to(ROOT)),
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {ADR} with {len(items)} frozen items; sha256={_sha(FROZEN)}")


def _dump_exchange(exchange: Any) -> dict[str, Any]:
    value = exchange.dump()
    value["parsed"] = exchange.parsed
    return value


def _grade_item(item: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=SONNET_MODEL)
    llm: LLM = local.llm
    results: dict[str, Any] = {}
    for model in MODELS:
        exchanges: list[dict[str, Any]] = []
        parsed: dict[str, Any] | None = None
        for _attempt in range(3):
            start = len(llm.log)
            value = llm.structured(
                "eval.answer.semantic.calibration", SYSTEM, _user(item), SCHEMA,
                max_tokens=1200, effort="medium", model=model)
            exchanges.extend(_dump_exchange(ex) for ex in llm.log[start:])
            if value and "correct" in value:
                parsed = dict(value)
                break
        if parsed is None:
            last_error = exchanges[-1].get("error") if exchanges else "no exchange"
            raise RuntimeError(f"{model} failed after 3 attempts: {last_error}")
        results[model] = {"grade": dict(parsed or {}), "exchanges": exchanges}
    sonnet = results[SONNET_MODEL]["grade"]
    use_opus = sonnet.get("confidence") != "high" or sonnet.get("gold_drift_suspected") is True
    results["cascade"] = {
        "used_model": OPUS_MODEL if use_opus else SONNET_MODEL,
        "escalated": use_opus,
        "grade": results[OPUS_MODEL if use_opus else SONNET_MODEL]["grade"],
    }
    return {**item, "judges": results}


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * q), len(ordered) - 1)]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    good = [row for row in rows if not row.get("error")]
    labels: dict[str, list[bool]] = {
        "haiku_initial": [bool(row["source_initial_haiku"]) for row in good],
        "haiku_three_vote": [bool(row["haiku_three_vote"]) for row in good],
        "sonnet": [bool(row["judges"][SONNET_MODEL]["grade"]["correct"]) for row in good],
        "opus": [bool(row["judges"][OPUS_MODEL]["grade"]["correct"]) for row in good],
        "cascade": [bool(row["judges"]["cascade"]["grade"]["correct"]) for row in good],
    }
    pairs = {}
    names = list(labels)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            pairs[f"{left}__{right}"] = sum(a == b for a, b in zip(labels[left], labels[right]))
    model_usage = {}
    for model in MODELS:
        exchanges = [ex for row in good for ex in row["judges"][model]["exchanges"]]
        durations = [int(ex.get("dur_ms") or 0) for ex in exchanges]
        model_usage[model] = {
            "calls": len(exchanges),
            "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in exchanges),
            "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in exchanges),
            "duration_ms_total": sum(durations),
            "duration_ms_mean": round(statistics.mean(durations), 1) if durations else None,
            "duration_ms_p50": _percentile(durations, .5),
            "duration_ms_p95": _percentile(durations, .95),
            "errors": sum(bool(ex.get("error")) for ex in exchanges),
        }
    return {
        "items": len(rows), "completed": len(good), "errors": len(rows) - len(good),
        "correct_counts": {name: sum(values) for name, values in labels.items()},
        "pair_agreement_counts": pairs,
        "sonnet_opus_disagreements": sum(a != b for a, b in zip(labels["sonnet"], labels["opus"])),
        "cascade_escalations": sum(row["judges"]["cascade"]["escalated"] for row in good),
        "model_usage": model_usage,
    }


def _question_markdown(row: dict[str, Any], number: int) -> str:
    judges = row["judges"]
    return f"""# 질문 {number:03d} — {row['id']}

## 1. 실행 메타

- ADR: `ADR-0047`
- experiment: `ADR-0047-evaluator-calibration-v1`
- case ID: `{row['case_no']}` / `{row['variant']}`
- run ID: `run-001`
- 원본 상태: `exact`
- 제품 호출: 없음 — 저장 답변 재사용
- 오프라인 평가 모델: `{SONNET_MODEL}`, `{OPUS_MODEL}`

## 2. 사용자 질문 원문

```text
{row['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{row['reference_answer']}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps({'source': row['source_path'], 'source_sha256': row['source_sha256'], 'variant': row['variant']}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

제품 재호출 없음. 아래 동결 답변을 모든 evaluator arm에 동일하게 사용했다.

```text
{row['answer']}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

### 공통 system

```text
{SYSTEM}
```

### 공통 user

```text
{_user(row)}
```

### schema

```json
{json.dumps(SCHEMA, ensure_ascii=False, indent=2)}
```

### Sonnet provider 원응답

```json
{json.dumps(judges[SONNET_MODEL], ensure_ascii=False, indent=2)}
```

### Opus provider 원응답

```json
{json.dumps(judges[OPUS_MODEL], ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| arm | correct | confidence | 비고 |
|---|---:|---|---|
| Haiku initial | {row['source_initial_haiku']} | 미기록 | 기존 원장 |
| Haiku 3-vote | {row['haiku_three_vote']} | 다수결 | 기존 재감사 |
| Sonnet single | {judges[SONNET_MODEL]['grade'].get('correct')} | {judges[SONNET_MODEL]['grade'].get('confidence')} | offline |
| Opus single | {judges[OPUS_MODEL]['grade'].get('correct')} | {judges[OPUS_MODEL]['grade'].get('confidence')} | offline |
| cascade | {judges['cascade']['grade'].get('correct')} | {judges['cascade']['grade'].get('confidence')} | escalated={judges['cascade']['escalated']} |

- 사람 확정 판정: 없음 — 모델 채택 근거로 사용할 수 없음
- 실패 유형: `judge_or_gold_error` 검토 대상
"""


def run(workers: int) -> None:
    if not ADR.exists() or not FROZEN.exists():
        raise RuntimeError("run prepare first")
    items = json.loads(FROZEN.read_text("utf-8"))["items"]
    local = threading.local()
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_grade_item, item, local): item for item in items}
        for index, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            item = future_map[future]
            try:
                row = future.result()
                marks = (row["judges"][SONNET_MODEL]["grade"].get("correct"),
                         row["judges"][OPUS_MODEL]["grade"].get("correct"))
                print(f"[{index:02d}/{len(items)}] {item['id']} sonnet={marks[0]} opus={marks[1]}",
                      flush=True)
            except Exception as exc:  # preserve failed item in the immutable run
                row = {**item, "error": f"{type(exc).__name__}: {exc}"}
                print(f"[{index:02d}/{len(items)}] {item['id']} ERROR {row['error']}", flush=True)
            rows.append(row)
            rows.sort(key=lambda value: value["id"])
            OUTPUT.write_text(json.dumps({
                "schema_version": "offline-evaluator-calibration-results-v1",
                "contract": {"answers_frozen": True, "product_calls": 0,
                             "offline_models": list(MODELS), "human_labels_available": False},
                "summary": _summary(rows), "rows": rows,
            }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if any(row.get("error") for row in rows):
        raise RuntimeError("calibration contains failed calls")
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    questions = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows, 1):
        target = ADR / "실험" / questions[row["id"]]["file"]
        target.write_text(_question_markdown(row, number), "utf-8")
        questions[row["id"]]["sha256"] = _sha(target)
    summary = _summary(rows)
    manifest["runs"][0].update({"status": "complete", "sha256": _sha(OUTPUT)})
    manifest["results"] = {
        "status": "complete",
        "by_arm": summary["correct_counts"],
        "comparisons": summary["pair_agreement_counts"],
        "judge_disagreements": summary["sonnet_opus_disagreements"],
        "usage": summary["model_usage"],
        "latency": {model: {k: v for k, v in usage.items() if "duration" in k}
                    for model, usage in summary["model_usage"].items()},
        "error_taxonomy": ["judge_or_gold_error", "human_calibration_missing"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_experiment_index() -> None:
    blob = json.loads(OUTPUT.read_text("utf-8"))
    rows = blob["rows"]
    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8"))
    files = {row["case_id"]: row["file"] for row in manifest["questions"]}
    table = []
    for number, row in enumerate(rows, 1):
        sonnet = bool(row["judges"][SONNET_MODEL]["grade"]["correct"])
        opus = bool(row["judges"][OPUS_MODEL]["grade"]["correct"])
        paired = "일치" if sonnet == opus else "불일치"
        failure = "-" if sonnet == opus else "judge_or_gold_error"
        filename = files[row["id"]]
        table.append(
            f"| {number:03d} | `{row['id']}` | `run-002` | "
            f"H3={row['haiku_three_vote']} / S={sonnet} / O={opus} | {paired} | "
            f"{failure} | [{filename}]({filename}) |")
    summary = blob["summary"]
    text = f"""# ADR-0047 실험 질문 인덱스

> 32개 동결 답변의 실제 Sonnet·Opus 채점 입력, 출력과 판정을 보존한다.

## 계보

- experiment ID: `ADR-0047-evaluator-calibration-v1`
- branch: `evaluator-calibration`
- parent arm: `ADR-0046-model-policy-audit-v1/role-separated`
- 변경 가설: 강한 단일 offline judge가 Haiku 반복 호출을 대체할 수 있는지 측정한다.

## Arm

| arm ID | 역할 | 직접 부모 | 바뀐 것 | 고정한 것 |
|---|---|---|---|---|
| `baseline` | baseline | 정책 parent | 기존 Haiku 최초·3표 | 동결 질문·골든·답변 |
| `sonnet-single` | candidate | baseline | Sonnet 단일 | 동일 prompt·schema |
| `opus-single` | candidate | baseline | Opus 단일 | 동일 prompt·schema |
| `sonnet-opus-cascade` | candidate | baseline | Sonnet confidence 조건부 Opus | 저장된 두 판정 |

## 질문 인덱스

| 번호 | case/answer | run | arm별 판정 | S/O | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
{chr(10).join(table)}

## 집계

- phase: `probe`, in-sample: `true`, decision eligible: `false`
- run-001: invalid — provider overload와 실패 승격 결함
- run-002: complete — {summary['completed']}/{summary['items']}, 오류 {summary['errors']}
- correct=true: Haiku3 {summary['correct_counts']['haiku_three_vote']}, Sonnet {summary['correct_counts']['sonnet']}, Opus {summary['correct_counts']['opus']}
- Sonnet–Opus 일치: {summary['pair_agreement_counts']['sonnet__opus']}/{summary['items']}
- Sonnet–Opus 불일치: {summary['sonnet_opus_disagreements']}
- cascade escalation: {summary['cascade_escalations']}/{summary['items']}

기계 판독본은 [manifest.json](manifest.json), 원시 결과는
[calibration-results.json](../artifacts/calibration-results.json)에 있다.
"""
    (ADR / "실험/README.md").write_text(text, "utf-8")
    print(ADR / "실험/README.md")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    execute = sub.add_parser("run")
    execute.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    sub.add_parser("finalize-docs")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run(args.workers)
    else:
        write_experiment_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
