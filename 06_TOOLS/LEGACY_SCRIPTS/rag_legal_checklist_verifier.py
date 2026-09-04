#!/usr/bin/env python3
"""ADR-0052: shadow-evaluate an accumulating legal-answer checklist."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import concurrent.futures
import copy
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
from lawrag.core.rag.legal_answer_checklists import (  # noqa: E402
    aggregate_verdict,
    checklist_version,
    load_items,
    render_cards,
    route_items,
    verifier_schema,
)
from scripts.adr_structure import HAIKU_MODEL  # noqa: E402


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0052-legal-checklist-verifier"
SOURCE = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0049-legal-minimal-pairs/artifacts/judged-results.json"
ITEM_DIR = ROOT / "01_DATA/legal_answer_checklists/items"
FROZEN = ADR / "artifacts/frozen-answers.json"
RESULTS = ADR / "artifacts/verifier-results.json"
DIAGNOSTICS = ADR / "artifacts/posthoc-diagnostics.json"
ARMS = ("baseline", "free-verifier", "core-checklist", "routed-checklist")
CALL_ARMS = ARMS[1:]

FREE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT", "UNCLEAR"]},
        "answer_quote": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "error_types": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "answer_quote", "evidence_ids", "error_types", "reason"],
    "additionalProperties": False,
}

COMMON_SYSTEM = """너는 회수된 법률 근거와 이미 생성된 답변 사이의 정합성만 검사하는 그림자 검증기다.
골든 답, 외부지식, 상식은 사용하지 않는다. 오직 [질문], [회수 근거], [검증 대상 답변]만 사용한다.
답을 다시 쓰거나 고치지 말고 ACCEPT, REJECT, UNCLEAR 중 하나로 분류한다.
ACCEPT는 답변의 명시적 결론과 핵심 이유가 질문의 행위자·행위·객체·시점, 근거의 조건·단서·예외·수치·법률효과와 모두 일치할 때만 선택한다.
구체적 모순이나 근거와 반대인 결론은 REJECT다. 필요한 근거나 사실이 없어 확인할 수 없으면 REJECT를 추측하지 말고 UNCLEAR다.
answer_quote는 판정의 직접 대상인 답변 원문 일부를 그대로 복사하고, evidence_ids는 실제 회수 근거 ID만 쓴다."""

CHECKLIST_SYSTEM = COMMON_SYSTEM + """
아래 [검사 카드] 각각을 독립적으로 판정한다. 카드 문구와 예시는 검사 방법일 뿐 법적 근거가 아니다.
법률 명제의 참·거짓은 반드시 [회수 근거]로만 판단한다. 적용되지 않는 카드는 NOT_APPLICABLE로 둔다.
각 reason은 한 문장 80자 이내, answer_quote는 필요한 최소 구절로 작성한다.
recommended_verdict는 참고값이며 최종 판정은 코드가 각 카드 결과를 결정론적으로 집계한다."""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(exchange: Any) -> dict[str, Any]:
    value = exchange.dump()
    value["parsed"] = exchange.parsed
    return value


def call(llm: LLM, name: str, system: str, user: str,
         schema: dict[str, Any]) -> dict[str, Any]:
    exchanges: list[dict[str, Any]] = []
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(name, system, user, schema, max_tokens=6000,
                               effort="medium", model=HAIKU_MODEL)
        exchanges.extend(dump_exchange(ex) for ex in llm.log[start:])
        if isinstance(value, dict):
            return {
                "request": {"call_name": name, "system": system, "user": user,
                            "schema": schema, "model": HAIKU_MODEL},
                "output": dict(value), "exchanges": exchanges, "error": "",
            }
    return {
        "request": {"call_name": name, "system": system, "user": user,
                    "schema": schema, "model": HAIKU_MODEL},
        "output": None, "exchanges": exchanges,
        "error": "structured output failed after 3 attempts",
    }


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    rows = []
    for row in evidence:
        label = " / ".join(str(row.get(key) or "") for key in ("document", "node", "role"))
        rows.append(f"[{row.get('id')}] {label}\n{row.get('original_text') or ''}")
    return "\n\n".join(rows)


def user_prompt(row: dict[str, Any], *, cards: str | None = None) -> str:
    card_block = f"\n\n[검사 카드]\n{cards}" if cards is not None else ""
    return (f"[질문]\n{row['question']}\n\n[회수 근거]\n{evidence_text(row['evidence'])}"
            f"\n\n[검증 대상 답변]\nanswerable={row['answerable']}\n{row['answer']}"
            f"{card_block}")


def free_aggregate(raw: dict[str, Any] | None, *, answer: str,
                   evidence_ids: list[str]) -> tuple[str, list[str]]:
    if not isinstance(raw, dict):
        return "UNCLEAR", ["verifier_output_missing"]
    verdict = str(raw.get("verdict") or "")
    errors = []
    if verdict not in {"ACCEPT", "REJECT", "UNCLEAR"}:
        errors.append("invalid_verdict")
    quote = str(raw.get("answer_quote") or "").strip()
    if quote and quote not in answer:
        errors.append("answer_quote_not_found")
    valid = set(evidence_ids)
    cited = raw.get("evidence_ids")
    if not isinstance(cited, list) or any(str(value) not in valid for value in cited):
        errors.append("invalid_evidence_id")
    return ("UNCLEAR" if errors else verdict), errors


def freeze_answers() -> list[dict[str, Any]]:
    blob = json.loads(SOURCE.read_text("utf-8"))
    rows = []
    for source_row in blob["rows"]:
        for source_arm, value in source_row["arms"].items():
            output = value["output"]
            grade = value["judge"]["output"]
            rows.append({
                "id": f"chk-{source_row['id'].removeprefix('mp-')}-{source_arm}",
                "source_id": source_row["id"], "source_arm": source_arm,
                "pair_id": source_row["pair_id"], "side": source_row["side"],
                "question": source_row["question"],
                "answer": str(output.get("answer") or ""),
                "answerable": bool(output.get("answerable")),
                "evidence": copy.deepcopy(value["evidence"]),
                "truth_correct": bool(grade.get("correct")),
                "truth_reason": grade.get("reason"),
                "truth_source": "ADR-0049 frozen claude-opus-5 semantic judge",
            })
    rows.sort(key=lambda row: row["id"])
    return rows


def prepare() -> None:
    rows = freeze_answers()
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({
        "schema_version": "legal-checklist-frozen-v1",
        "source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha(SOURCE),
        "checklist_version": checklist_version(ITEM_DIR),
        "checklist_files": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)}
                            for path in sorted(ITEM_DIR.glob("LC-*.yaml"))],
        "construction": "ADR-0049의 8문항×3 answer arms를 재생성 없이 전수 동결; truth는 검증기 입력에서 제외",
        "rows": rows,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")

    path = ADR / "실험/manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0052-legal-checklist-verifier-v1"
    manifest["lineage"]["hypothesis_delta"] = (
        "답변을 수정하지 않는 법률 체크리스트 검증기가 자유형 검증기보다 오답을 더 잘 적발하면서 정답을 보존하는지 분리한다."
    )
    manifest["design"].update({
        "hypothesis": "Haiku의 오답은 일반적인 재검토 지시보다 법률좌표·권위·조건·예외·수치 경계를 독립 카드로 검사할 때 더 잘 적발된다.",
        "primary_metric": "오답 flag율과 정답 ACCEPT율의 산술평균인 balanced accuracy; accept precision 보조",
        "success_criteria": "routed-checklist 오답 flag율 >=80%, 정답 ACCEPT율 >=75%, balanced accuracy가 free-verifier보다 10%p 이상, 호출 오류 0",
        "failure_criteria": "어느 성공선이든 미달, 또는 정확한 답 4건 이상을 REJECT/UNCLEAR 처리",
        "criteria_frozen_before_run": True,
        "arms": [
            {"id": "baseline", "role": "baseline", "derived_from": ["ADR-0049-legal-minimal-pairs-v1/condition-matrix"],
             "changes": "검증 없이 모든 답 ACCEPT", "controls": "같은 24개 동결 답변과 frozen Opus truth"},
            {"id": "free-verifier", "role": "control", "derived_from": ["baseline"],
             "changes": "Haiku 자유형 정합성 검증, checklist 없음", "controls": "같은 질문·답변·근거·모델·1회"},
            {"id": "core-checklist", "role": "candidate", "derived_from": ["free-verifier"],
             "changes": "LC-001~005 공통 카드와 결정론 집계", "controls": "같은 질문·답변·근거·모델·1회"},
            {"id": "routed-checklist", "role": "candidate", "derived_from": ["core-checklist"],
             "changes": "공통 카드 + 질문·근거 keyword로 LC-101~107 선택", "controls": "같은 질문·답변·근거·모델·1회"},
        ],
    })
    manifest["runs"] = [
        {
            "id": "run-000", "purpose": "audit", "parent_run_id": None,
            "arm_ids": ["core-checklist", "routed-checklist"],
            "selection_rule": "실행 순서상 최초 rows; schema preflight 실패로 성능 표본에서 제외",
            "status": "invalid",
            "artifact_path": "docs/adr/ADR-0052-legal-checklist-verifier/artifacts/aborted-run-000.json",
            "sha256": sha(ADR / "artifacts/aborted-run-000.json"),
        },
        {
            "id": "run-001", "purpose": "audit", "parent_run_id": "run-000",
            "arm_ids": list(CALL_ARMS),
            "selection_rule": "run-000 schema 수정 후 최초 rows; 출력 토큰 절단으로 성능 표본에서 제외",
            "status": "invalid",
            "artifact_path": "docs/adr/ADR-0052-legal-checklist-verifier/artifacts/aborted-run-001.json",
            "sha256": sha(ADR / "artifacts/aborted-run-001.json"),
        },
        {
            "id": "run-002", "purpose": "primary", "parent_run_id": "run-001",
            "arm_ids": list(ARMS),
            "selection_rule": "ADR-0049 8문항×3 answer arms의 24개 답변 전수; 결과 확인 전 동결",
            "status": "planned", "artifact_path": str(RESULTS.relative_to(ROOT)),
            "sha256": "PENDING",
        },
    ]
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "free-verifier", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "checklist-verifier", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
    ]
    manifest["dataset"].update({
        "name": "ADR-0049 frozen legal minimal-pair answers",
        "version": "v1 / 24 answers / 13 correct + 11 wrong",
        "frozen_source": str(FROZEN.relative_to(ROOT)), "sha256": sha(FROZEN),
        "legal_version_checked": False, "reference_version_checked": False,
    })
    presented = [len(row["evidence"]) for row in rows]
    manifest["retrieval_accounting"].update({
        "changed": False, "corpus_total": 17370, "before_filter": 17370,
        "after_filter": sum(presented), "presented_total": sum(presented),
        "presented_mean": round(statistics.mean(presented), 3),
        "presented_p50": statistics.median(presented), "presented_p95": max(presented),
        "golden_recall": "inherited frozen evidence; not remeasured",
        "selectivity": round(statistics.mean(presented) / 17370, 8),
        "not_applicable_reason": "회수 재실행·변경 없이 ADR-0049의 answer별 evidence를 그대로 검증기에 제시",
    })
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared rows={len(rows)} correct={sum(r['truth_correct'] for r in rows)} "
          f"wrong={sum(not r['truth_correct'] for r in rows)} sha={sha(FROZEN)}")


def verify_one(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    all_items = load_items(ITEM_DIR)
    core = [item for item in all_items if item.scope == "core"]
    routed = route_items(row["question"], row["evidence"], all_items)
    result = copy.deepcopy(row)
    result["arms"] = {"baseline": {"verdict": "ACCEPT", "guard_errors": [],
                                     "selected_item_ids": [], "call": None}}
    rotation = int(hashlib.sha256(row["id"].encode()).hexdigest()[:8], 16) % len(CALL_ARMS)
    order = list(CALL_ARMS[rotation:] + CALL_ARMS[:rotation])
    for arm in order:
        if arm == "free-verifier":
            value = call(local.llm, f"adr51.{row['id']}.free", COMMON_SYSTEM,
                         user_prompt(row), FREE_SCHEMA)
            verdict, errors = free_aggregate(value["output"], answer=row["answer"],
                                             evidence_ids=[e["id"] for e in row["evidence"]])
            selected = []
            item_rows = []
        else:
            selected_items = core if arm == "core-checklist" else routed
            value = call(local.llm, f"adr51.{row['id']}.{arm}", CHECKLIST_SYSTEM,
                         user_prompt(row, cards=render_cards(selected_items)),
                         verifier_schema(item.id for item in selected_items))
            aggregate = aggregate_verdict(selected_items, value["output"], answer=row["answer"],
                                          evidence_ids=[e["id"] for e in row["evidence"]])
            verdict, errors = aggregate.verdict, list(aggregate.guard_errors)
            selected = [item.id for item in selected_items]
            item_rows = list(aggregate.item_rows)
        result["arms"][arm] = {
            "verdict": verdict, "guard_errors": errors,
            "selected_item_ids": selected, "item_rows": item_rows, "call": value,
        }
    result["call_order"] = order
    return result


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * ratio + 0.999999))]


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"by_arm": {}, "paired_vs_free": {}}
    correct_total = sum(row["truth_correct"] for row in rows)
    wrong_total = len(rows) - correct_total
    for arm in ARMS:
        correct_accept = sum(row["truth_correct"] and row["arms"][arm]["verdict"] == "ACCEPT" for row in rows)
        wrong_flag = sum((not row["truth_correct"]) and row["arms"][arm]["verdict"] != "ACCEPT" for row in rows)
        accepted = sum(row["arms"][arm]["verdict"] == "ACCEPT" for row in rows)
        calls = [ex for row in rows if row["arms"][arm].get("call")
                 for ex in row["arms"][arm]["call"]["exchanges"]]
        durations = [int(ex.get("dur_ms") or 0) for ex in calls]
        ca_rate = correct_accept / correct_total
        wf_rate = wrong_flag / wrong_total
        output["by_arm"][arm] = {
            "correct_accept": correct_accept, "correct_total": correct_total,
            "correct_accept_rate": round(ca_rate, 4),
            "wrong_flag": wrong_flag, "wrong_total": wrong_total,
            "wrong_flag_rate": round(wf_rate, 4),
            "balanced_accuracy": round((ca_rate + wf_rate) / 2, 4),
            "accepted": accepted,
            "accept_precision": round(correct_accept / accepted, 4) if accepted else None,
            "reject": sum(row["arms"][arm]["verdict"] == "REJECT" for row in rows),
            "unclear": sum(row["arms"][arm]["verdict"] == "UNCLEAR" for row in rows),
            "classification_correct": correct_accept + wrong_flag,
            "calls": len(calls),
            "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in calls),
            "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in calls),
            "latency_p50_ms": int(statistics.median(durations)) if durations else 0,
            "latency_p95_ms": percentile(durations, .95),
            "call_errors": sum(bool(row["arms"][arm].get("call") and row["arms"][arm]["call"].get("error")) for row in rows),
        }
    for arm in ("core-checklist", "routed-checklist"):
        values = {"candidate_only_correct": 0, "free_only_correct": 0,
                  "both_correct": 0, "both_wrong": 0}
        for row in rows:
            expected_accept = row["truth_correct"]
            free_ok = (row["arms"]["free-verifier"]["verdict"] == "ACCEPT") == expected_accept
            cand_ok = (row["arms"][arm]["verdict"] == "ACCEPT") == expected_accept
            key = ("both_correct" if free_ok and cand_ok else
                   "free_only_correct" if free_ok else
                   "candidate_only_correct" if cand_ok else "both_wrong")
            values[key] += 1
        output["paired_vs_free"][arm] = values
    return output


def posthoc_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain the frozen result; never replaces the prespecified metrics."""
    guard_errors: Counter[str] = Counter()
    routed_counts: Counter[int] = Counter()
    item_votes: dict[str, Counter[str]] = defaultdict(Counter)
    quote_relaxed: dict[str, Any] = {}
    for row in rows:
        routed_counts[len(row["arms"]["routed-checklist"]["selected_item_ids"])] += 1
        for arm in ("core-checklist", "routed-checklist"):
            guard_errors.update(row["arms"][arm]["guard_errors"])
            for item in row["arms"][arm]["item_rows"]:
                key = f"{arm}/{item['id']}/truth_{str(row['truth_correct']).lower()}"
                item_votes[key][item["verdict"]] += 1
    for arm in ("core-checklist", "routed-checklist"):
        relaxed = []
        for row in rows:
            selected = set(row["arms"][arm]["selected_item_ids"])
            raw = row["arms"][arm]["call"]["output"]
            values = raw.get("items", []) if isinstance(raw, dict) else []
            seen = [value.get("id") for value in values]
            structurally_bad = (len(seen) != len(set(seen)) or set(seen) != selected)
            verdicts = [value.get("verdict") for value in values]
            if structurally_bad:
                verdict = "UNCLEAR"
            elif "FAIL" in verdicts:
                verdict = "REJECT"
            elif "UNCLEAR" in verdicts:
                verdict = "UNCLEAR"
            else:
                verdict = "ACCEPT"
            relaxed.append((row["truth_correct"], verdict))
        correct_accept = sum(truth and verdict == "ACCEPT" for truth, verdict in relaxed)
        wrong_flag = sum((not truth) and verdict != "ACCEPT" for truth, verdict in relaxed)
        accepted = sum(verdict == "ACCEPT" for _, verdict in relaxed)
        quote_relaxed[arm] = {
            "label": "POSTHOC sensitivity only; answer_quote exact-match guard ignored",
            "correct_accept": correct_accept, "correct_total": 13,
            "wrong_flag": wrong_flag, "wrong_total": 11,
            "correct_accept_rate": round(correct_accept / 13, 4),
            "wrong_flag_rate": round(wrong_flag / 11, 4),
            "balanced_accuracy": round(((correct_accept / 13) + (wrong_flag / 11)) / 2, 4),
            "accept_precision": round(correct_accept / accepted, 4) if accepted else None,
            "verdict_counts": dict(Counter(verdict for _, verdict in relaxed)),
        }
    return {
        "schema_version": "legal-checklist-posthoc-v1",
        "not_prespecified": True,
        "must_not_determine_adoption": True,
        "guard_errors": dict(guard_errors.most_common()),
        "routed_selected_item_count": {str(key): value for key, value in sorted(routed_counts.items())},
        "item_votes": {key: dict(value) for key, value in sorted(item_votes.items())},
        "quote_guard_relaxed_sensitivity": quote_relaxed,
        "interpretation": [
            "Exact substring validation of model-authored answer_quote dominated fail-closed UNCLEAR outcomes.",
            "Routed keyword triggers selected all 12 items for 16/24 rows, so routing was insufficiently selective.",
            "The relaxed analysis reuses the same outputs and is diagnostic, not a new eligible arm.",
        ],
    }


def run(workers: int) -> None:
    rows = json.loads(FROZEN.read_text("utf-8"))["rows"]
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(verify_one, row, local): row for row in rows}
        for number, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            result = future.result()
            output.append(result)
            print(f"[{number}/{len(rows)}] {result['id']} verified", flush=True)
    output.sort(key=lambda row: row["id"])
    summary = metrics(output)
    RESULTS.write_text(json.dumps({"schema_version": "legal-checklist-results-v1",
                                  "summary": summary, "rows": output},
                                 ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    calls = {arm: row["arms"][arm] for arm in ARMS}
    verdicts = "\n".join(
        f"| {arm} | {row['arms'][arm]['verdict']} | {', '.join(row['arms'][arm].get('selected_item_ids') or []) or '-'} | "
        f"{', '.join(row['arms'][arm].get('guard_errors') or []) or '-'} |"
        for arm in ARMS
    )
    return f"""# 질문 {number:03d} — {row['id']}

## 1. 실행 메타

- ADR: `ADR-0052`
- experiment: `ADR-0052-legal-checklist-verifier-v1`
- source: `{row['source_id']}` / answer arm `{row['source_arm']}`
- 제품 검증 모델: `{HAIKU_MODEL}`; 반복 1회
- 원본 상태: 질문·근거·답변·Opus truth 모두 ADR-0049 exact frozen

## 2. 사용자 질문 원문

```text
{row['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

새 채점 호출은 하지 않았다. ADR-0049에서 동결한 의미 판정은 다음과 같다.

```json
{json.dumps({'correct': row['truth_correct'], 'reason': row['truth_reason'], 'source': row['truth_source']}, ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

### 검증 대상 답변 원문

```text
answerable={row['answerable']}
{row['answer']}
```

### 검증기에 제시한 회수 근거 원값

```json
{json.dumps(row['evidence'], ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(calls, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
{json.dumps({'free_verifier': calls['free-verifier']['call'], 'core_checklist': calls['core-checklist']['call'], 'routed_checklist': calls['routed-checklist']['call']}, ensure_ascii=False, indent=2)}
```

## 7. 채점 호출과 반복 판정

```json
{json.dumps({'new_judge_calls': [], 'frozen_truth': {'correct': row['truth_correct'], 'reason': row['truth_reason']}, 'repeats': 1}, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| arm | verdict | 적용 checklist | guard error |
|---|---|---|---|
{verdicts}

- 분류 정답 조건: 원 답변이 정답이면 `ACCEPT`, 오답이면 `REJECT` 또는 `UNCLEAR`
- 검증기는 답변을 수정하지 않았으며 메인 제품 경로에도 연결되지 않았다.
"""


def write_docs(rows: list[dict[str, Any]], totals: dict[str, Any],
               diagnostics: dict[str, Any]) -> None:
    score_rows = []
    for arm in ARMS:
        value = totals["by_arm"][arm]
        score_rows.append(
            f"| `{arm}` | {value['wrong_flag']}/{value['wrong_total']} ({value['wrong_flag_rate']:.1%}) | "
            f"{value['correct_accept']}/{value['correct_total']} ({value['correct_accept_rate']:.1%}) | "
            f"{value['balanced_accuracy']:.1%} | {value['accept_precision'] if value['accept_precision'] is not None else '-'} | "
            f"{value['input_tokens']} | {value['latency_p50_ms']}/{value['latency_p95_ms']} ms |"
        )
    routed = totals["by_arm"]["routed-checklist"]
    free = totals["by_arm"]["free-verifier"]
    success = (routed["wrong_flag_rate"] >= .8 and routed["correct_accept_rate"] >= .75 and
               routed["balanced_accuracy"] >= free["balanced_accuracy"] + .1 and
               routed["call_errors"] == 0)
    failures = []
    for row in rows:
        arm = row["arms"]["routed-checklist"]
        prediction_ok = (arm["verdict"] == "ACCEPT") == row["truth_correct"]
        if not prediction_ok:
            failures.append(f"| `{row['id']}` | {row['truth_correct']} | {arm['verdict']} | "
                            f"{', '.join(arm['selected_item_ids'])} |")
    failure_rows = "\n".join(failures) or "| - | - | - | - |"
    readme = f"""---
adr_id: ADR-0052
title: 누적형 법률 체크리스트 검증기
status: Rejected
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0052: 누적형 법률 체크리스트 검증기

## 1. 결정 요약

법률 체크리스트를 데이터 원장과 그림자 검증기로 구현했다. 사전 성공 기준은 **{'충족' if success else '미충족'}**했으며, 이 exact gate 배선은 기각하고 메인 배선은 변경하지 않는다.

## 2. 문제와 변경 전 구조

정답 조문이 회수돼도 결론·조건·예외를 잘못 포섭하는 답이 남는다. 과거 자유형 verifier와 repair는 안정적 개선을 보이지 않았으므로, 답을 고치지 않고 오류 유형을 독립 카드로 확인하는 구조를 시험했다.

## 3. 가설과 사전 판정 기준

### 가설

일반적인 재검토 지시보다 법률좌표·권위·조건·예외·수치 경계를 독립 카드로 검사하면 오답을 더 잘 적발하면서 정답을 보존한다.

### 성공 기준

routed-checklist 오답 flag율 80% 이상, 정답 ACCEPT율 75% 이상, balanced accuracy가 free-verifier보다 10%p 이상, 호출 오류 0.

### 반증 기준

어느 성공선이든 미달하거나 정확한 답 4건 이상을 flag하면 실패다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | 모두 ACCEPT | 동결 truth | 무검증 기준 |
| free-verifier | 일반 법률 정합성 검토 | 질문·답·근거·Haiku | checklist 자체의 효과 분리 |
| core-checklist | 공통 LC-001~005 | 동일 | 보편 카드 효과 |
| routed-checklist | 공통 + keyword 선택 LC-101~107 | 동일 | 쟁점별 카드 효과 |

## 5. 데이터·모델·재현성

- ADR-0049의 8개 최소대조 질문 × 3개 생성 arm = 24개 기존 답변을 재생성 없이 동결했다.
- 원 답변 truth는 기존 단일 Opus 의미 판정 13 correct / 11 wrong이며 검증 프롬프트에는 제공하지 않았다.
- 모든 새 검증 호출은 `{HAIKU_MODEL}` 1회다. 새 evaluator 호출은 없다.
- checklist는 `trial-v1`; 사례별 basis는 모델 프롬프트에서 제외해 라벨 누수를 막았다.

## 6. 결과

| arm | 오답 flag율 | 정답 ACCEPT율 | balanced accuracy | accept precision | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(score_rows)}

free 대비 paired 결과: `{json.dumps(totals['paired_vs_free'], ensure_ascii=False)}`

## 7. 사례별 오류 분석

아래는 routed-checklist가 truth 분류와 달랐던 사례다.

| case | 원 답변 정답 | verifier | 적용 카드 |
|---|---:|---|---|
{failure_rows}

질문별 정확한 입력·출력·카드 판정은 [실험 인덱스](실험/README.md)에 보존했다.

### 사후 원인 진단 — 공식 성공 판정에서 제외

- exact `answer_quote` 불일치가 총 {sum(diagnostics['guard_errors'].values())}건의 guard error를 만들었다. 가장 많은 항목은 `{next(iter(diagnostics['guard_errors']))}` {next(iter(diagnostics['guard_errors'].values()))}건이다.
- keyword router는 24건 중 {diagnostics['routed_selected_item_count'].get('12', 0)}건에 12개 카드를 전부 선택했다. 현재 trigger가 넓어 실질적인 가지치기가 부족하다.
- quote exact-match만 제외한 민감도에서 routed는 정답 {diagnostics['quote_guard_relaxed_sensitivity']['routed-checklist']['correct_accept']}/13 수용, 오답 {diagnostics['quote_guard_relaxed_sensitivity']['routed-checklist']['wrong_flag']}/11 flag, balanced accuracy {diagnostics['quote_guard_relaxed_sensitivity']['routed-checklist']['balanced_accuracy']:.1%}였다. 이는 결과를 본 뒤 계산한 post-hoc 값이며 채택 근거가 아니다.

## 8. 비용·지연·회수 규모

- corpus 17,370 조문 root. 회수는 변경하지 않았고 ADR-0049의 frozen evidence를 그대로 사용했다.
- 답변당 제시 근거 수와 선택률은 [실험 manifest](실험/manifest.json)에 기록했다.
- verifier arm별 토큰과 p50/p95는 결과 표에 기록했다.

## 9. 해석

balanced accuracy는 오답 적발과 정답 보존을 같은 비중으로 본다. UNCLEAR도 사용자에게 오답을 그대로 통과시키지 않는 flag로 계산했지만, 실제 운영에서는 사람 검토 비용이므로 REJECT와 별도 집계했다.

## 10. 한계와 일반화 가능 범위

체크리스트가 유래한 ADR-0049 답변을 다시 본 인샘플 probe다. 4개 법률 쟁점, 24개 답변뿐이며 truth도 사람 확정이 아니라 기존 Opus 1회 판정이다. 미사용 법률 주제 holdout과 반복 실행 없이는 제품 채택 근거가 아니다.

## 11. 운영 결정·롤백 조건

메인 배선은 유지한다. registry·라우터·fail-closed 집계기는 진단 부품으로만 보존한다. 후속 holdout에서 정답 ACCEPT율 75% 미만이거나 free 대비 개선이 사라지면 trial 항목을 승격하지 않는다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_legal_checklist_verifier.py prepare
.venv/bin/python scripts/rag_legal_checklist_verifier.py run --workers 2
.venv/bin/python scripts/rag_legal_checklist_verifier.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0052-legal-checklist-verifier --final
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
"""
    (ADR / "README.md").write_text(readme, "utf-8")


def finalize() -> None:
    blob = json.loads(RESULTS.read_text("utf-8"))
    rows, totals = blob["rows"], blob["summary"]
    diagnostics = posthoc_diagnostics(rows)
    DIAGNOSTICS.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    qmap = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows, 1):
        target = ADR / "실험" / qmap[row["id"]]["file"]
        target.write_text(question_md(row, number), "utf-8")
        qmap[row["id"]]["sha256"] = sha(target)
    primary_run = next(run for run in manifest["runs"] if run["id"] == "run-002")
    primary_run.update({"status": "complete", "sha256": sha(RESULTS)})
    manifest["results"] = {
        "status": "complete", "by_arm": totals["by_arm"],
        "comparisons": totals["paired_vs_free"], "judge_disagreements": None,
        "usage": {arm: {key: value[key] for key in ("calls", "input_tokens", "output_tokens")}
                  for arm, value in totals["by_arm"].items()},
        "latency": {arm: {"p50_ms": value["latency_p50_ms"], "p95_ms": value["latency_p95_ms"]}
                    for arm, value in totals["by_arm"].items()},
        "error_taxonomy": ["scope", "authority", "condition_exception", "internal_consistency",
                           "completeness", "numeric_boundary", "cross_reference", "temporal"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows, totals, diagnostics)
    index = ["# ADR-0052 질문 인덱스", "", "| 번호 | source | answer arm | truth | 파일 |",
             "|---:|---|---|---:|---|"]
    for number, row in enumerate(rows, 1):
        file = qmap[row["id"]]["file"]
        index.append(f"| {number:03d} | `{row['source_id']}` | `{row['source_arm']}` | "
                     f"{row['truth_correct']} | [{file}]({file}) |")
    index.extend(["", "- truth는 검증기 입력에서 제외했다.",
                  "- 모든 새 LLM 호출은 Haiku이며 checklist는 답변을 수정하지 않는다."])
    (ADR / "실험/README.md").write_text("\n".join(index) + "\n", "utf-8")
    files = []
    for path, role in ((FROZEN, "frozen answers and truth"), (RESULTS, "verifier outputs"),
                       (DIAGNOSTICS, "posthoc diagnostics"),
                       (ADR / "artifacts/aborted-run-000.json", "invalid schema preflight"),
                       (ADR / "artifacts/aborted-run-001.json", "invalid token preflight"),
                       (Path(__file__), "runner"), (ROOT / "01_DATA/legal_answer_checklists/ledger.jsonl", "checklist ledger")):
        files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                      "bytes": path.stat().st_size, "role": role})
    for path in sorted(ITEM_DIR.glob("LC-*.yaml")):
        files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                      "bytes": path.stat().st_size, "role": "checklist item"})
    (ADR / "artifacts/manifest.json").write_text(json.dumps({
        "schema_version": "adr-artifacts-v1", "adr_id": "ADR-0052", "files": files,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run(args.workers)
    else:
        finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
