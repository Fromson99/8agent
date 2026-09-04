#!/usr/bin/env python3
"""ADR-0049: legal condition/exception minimal-pair evaluation."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM  # noqa: E402
from scripts.adr_structure import HAIKU_MODEL, OPUS_MODEL, scaffold_adr  # noqa: E402
from scripts.rag_evaluator_calibration import SCHEMA as JUDGE_SCHEMA, SYSTEM as JUDGE_SYSTEM  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0049-legal-minimal-pairs"
SOURCE = ROOT / "var/eval/e2e/cm_core_haiku_hard_distractor_wrong16_v1.json"
PARENT = ROOT / "docs/adr/ADR-0048-legal-reasoning-causal-portfolio/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-pairs.json"
PRODUCT = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
CORPUS = 17_370
ARMS = ("baseline-full", "gold-only", "condition-matrix")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "answerable": {"type": "boolean"}},
    "required": ["answer", "answerable"],
    "additionalProperties": False,
}

PAIR_SPECS = [
    {
        "pair_id": "exception-investor",
        "source_case": "cm-003",
        "decisive_fact": "벤처금융·전문투자자 해당 여부",
        "members": [
            {
                "id": "mp-investor-yes",
                "side": "exception_true",
                "question": "벤처금융 또는 전문투자자가 상장예비심사 신청일 전 1년 이내에 제3자배정으로 취득했고 투자기간이 2년 미만이며 제4호의 10% 한도 안인 주식은 제3호와 제4호 중 어디에 해당하는가? (업무 문맥: 코스닥 신규상장 의무보유)",
                "reference_answer": "시행세칙 제23조 제4항 제2호에 따라 제3호 단서의 예외로 제외되고, 주어진 제4호 요건을 충족하므로 제4호가 적용된다.",
            },
            {
                "id": "mp-investor-no",
                "side": "exception_false",
                "question": "벤처금융 또는 전문투자자에 해당하지 않는 일반 법인이 상장예비심사 신청일 전 1년 이내에 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가? (업무 문맥: 코스닥 신규상장 의무보유)",
                "reference_answer": "벤처금융·전문투자자 예외가 적용되지 않으므로 제3호가 적용되고, 제4호는 적용되지 않는다.",
            },
        ],
    },
    {
        "pair_id": "ipo-issuer-status",
        "source_case": "cm-030",
        "decisive_fact": "상장 전 일반 발행인인지, 이미 주권상장법인인지",
        "members": [
            {
                "id": "mp-ipo-unlisted",
                "side": "scope_false",
                "question": "금융기관이 아니고 아직 주권상장법인도 아닌 발행인이 1분기 재무제표 확정 후 IPO 증권신고서를 제출하면 1분기 검토보고서를 첨부하여야 하는가?",
                "reference_answer": "아니다. 분기감사·분기검토보고서 의무는 금융기관·주권상장법인에 한정되므로 상장 전 일반 발행인에게는 적용되지 않는다. 다만 상장 목적 모집·매출에서 반기재무제표 확정 후에는 반기감사·검토보고서를 첨부한다.",
            },
            {
                "id": "mp-ipo-listed",
                "side": "scope_true",
                "question": "이미 주권상장법인인 발행인이 1분기 재무제표 확정 후 지분증권 증권신고서를 제출하면 1분기 검토보고서를 첨부하여야 하는가?",
                "reference_answer": "그렇다. 제2-4조 제5항 제3호 라목의 주권상장법인이 분기재무제표 확정 후 신고서를 제출하는 경우에 해당하므로 분기감사보고서 또는 분기검토보고서를 첨부한다.",
            },
        ],
    },
    {
        "pair_id": "capital-threshold",
        "source_case": "cm-041",
        "decisive_fact": "자본금 총액 10억원 미만 여부",
        "members": [
            {
                "id": "mp-capital-9",
                "side": "exception_true",
                "question": "자본금 총액이 9억원인 주식회사는 이사를 반드시 3명 이상 두어야 하는가?",
                "reference_answer": "아니다. 자본금 총액이 10억원 미만인 회사는 상법 제383조 제1항 단서에 따라 이사를 1명 또는 2명으로 할 수 있다.",
            },
            {
                "id": "mp-capital-10",
                "side": "exception_false",
                "question": "자본금 총액이 정확히 10억원인 주식회사는 이사를 3명 이상 두어야 하는가?",
                "reference_answer": "그렇다. '10억원 미만' 예외에 해당하지 않으므로 상법 제383조 제1항 본문에 따라 이사를 3명 이상 두어야 한다.",
            },
        ],
    },
    {
        "pair_id": "norm-vs-checklist",
        "source_case": "cm-012",
        "decisive_fact": "법규상 제정기한인지, 실사 체크리스트 기재항목인지",
        "members": [
            {
                "id": "mp-rule-deadline",
                "side": "norm_absent",
                "question": "상장규정 또는 시행세칙에 상장신청인의 사내규정을 언제까지 제정해야 한다고 특정한 조문이 있는가?",
                "reference_answer": "확인된 상장규정·시행세칙에는 사내규정의 제정 기한을 특정한 조문이 없다. 운영 이력 관련 서술은 실무 체크리스트·해설 수준과 구분해야 한다.",
            },
            {
                "id": "mp-checklist-field",
                "side": "checklist_present",
                "question": "기업실사 체크리스트에는 임원 보수나 이해관계자 거래 관련 사내규정의 제정시기를 기재하는 항목이 있는가?",
                "reference_answer": "그렇다. 회수된 기업실사 체크리스트 작성 가이드는 해당 사내규정의 제정시기를 기재하도록 한다. 다만 이는 법규가 특정 제정기한을 정한 것과는 다르다.",
            },
        ],
    },
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(ex: Any) -> dict[str, Any]:
    value = ex.dump()
    value["parsed"] = ex.parsed
    return value


def replace_question(user: str, question: str) -> str:
    prefix, marker, rest = user.partition("[컨텍스트]")
    if not marker:
        raise ValueError("request has no [컨텍스트] marker")
    return f"[질문]\n{question}\n\n[컨텍스트]{rest}"


def call(llm: LLM, name: str, system: str, user: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
    exchanges: list[dict[str, Any]] = []
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(name, system, user, schema, max_tokens=1800, effort="medium", model=model)
        exchanges.extend(dump_exchange(ex) for ex in llm.log[start:])
        if isinstance(value, dict):
            return {"request": {"call_name": name, "system": system, "user": user, "schema": schema, "model": model},
                    "output": dict(value), "exchanges": exchanges}
    raise RuntimeError(f"{name} failed after 3 attempts")


def prepare() -> None:
    source = json.loads(SOURCE.read_text("utf-8"))
    source_rows = {str(row["case_no"]): row for row in source["rows"]}
    members = [member for pair in PAIR_SPECS for member in pair["members"]]
    if not ADR.exists():
        scaffold_adr(
            ROOT / "docs/adr", 49, "legal-minimal-pairs", "법률 조건·예외 최소대조쌍",
            "probe", [member["id"] for member in members], branch_id="minimal-pairs",
            candidate_arms=["gold-only", "condition-matrix"],
            parent_manifest=PARENT, parent_arm="ladder-gold", parent_relation="extends",
            judge_model=OPUS_MODEL,
        )
    frozen = copy.deepcopy(PAIR_SPECS)
    for pair in frozen:
        row = source_rows[pair["source_case"]]
        pair["source_coordinates"] = {
            variant: [{k: ev.get(k) for k in ("id", "doc_id", "node", "document", "path", "role", "relation_reason", "original_text")}
                      for ev in row["variants"][variant]["evidence"]]
            for variant in ("full_original", "gold_only")
        }
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({
        "schema_version": "legal-minimal-pairs-v1",
        "construction": "원 조문과 ADR-0039 기준답변에서 결정적 사실 하나만 반전한 수동 고정 쌍",
        "source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha(SOURCE), "pairs": frozen,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")

    path = ADR / "실험/manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0049-legal-minimal-pairs-v1"
    manifest["lineage"]["hypothesis_delta"] = "사실 하나가 규정의 actor·예외·문턱·권위를 바꾸면 Haiku 결론도 쌍으로 정확히 뒤집혀야 한다."
    manifest["design"].update({
        "hypothesis": "Haiku의 주된 실패는 조건을 추출하지 못하는 것이 아니라 조건 변화가 법률효과를 바꾸는 포섭 단계에 있다.",
        "primary_metric": "arm별 pair pass/4(양쪽 모두 의미 정답), individual correct/8 보조",
        "success_criteria": "condition-matrix가 baseline 대비 pair pass +1 이상, individual regression 0, 8문항 오류 0",
        "failure_criteria": "pair pass 개선 없음, 어느 한 쌍에서 한쪽만 맞아 결론 반전 실패, 또는 baseline 정답 회귀",
        "criteria_frozen_before_run": True,
    })
    for arm in manifest["design"]["arms"]:
        if arm["id"] == "baseline":
            arm["id"] = "baseline-full"
            arm["changes"] = "원 full context와 Wiki"
        elif arm["id"] == "gold-only":
            arm["changes"] = "골든 조문만"
        else:
            arm["changes"] = "골든 조문 + actor/조건/예외/효과 대조 guard"
        arm["derived_from"] = ["baseline-full" if ref == "baseline" else ref for ref in arm.get("derived_from", [])]
        arm["controls"] = "같은 최소대조 질문·Haiku·Opus judge; decisive fact 외 쌍 내 문맥 고정"
    manifest["dataset"].update({"name": "legal condition minimal pairs", "version": "v1 / 4 pairs / 8 questions",
                                "frozen_source": str(FROZEN.relative_to(ROOT)), "sha256": sha(FROZEN),
                                "legal_version_checked": False, "reference_version_checked": False})
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    manifest["runs"][0].update({"arm_ids": list(ARMS), "selection_rule": "사전 수동 고정 4쌍 8문항 × 3 arms 전수",
                                  "artifact_path": str(JUDGED.relative_to(ROOT))})
    full_counts = [len(source_rows[pair["source_case"]]["variants"]["full_original"]["evidence"]) for pair in PAIR_SPECS for _ in pair["members"]]
    manifest["retrieval_accounting"].update({
        "changed": True, "corpus_total": CORPUS, "before_filter": CORPUS,
        "after_filter": sum(full_counts), "presented_total": sum(full_counts),
        "presented_mean": round(statistics.mean(full_counts), 3), "presented_p50": statistics.median(full_counts),
        "presented_p95": max(full_counts), "golden_recall": "8/8 constructed questions",
        "selectivity": round(statistics.mean(full_counts) / CORPUS, 8),
        "not_applicable_reason": "실제 검색 재실행 없이 동결 evidence bundle을 질문만 최소 변경",
    })
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {ADR}; pairs=4 questions=8 sha={sha(FROZEN)}")


def generate_item(member: dict[str, Any], pair: dict[str, Any], source_row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    llm: LLM = local.llm
    result = {**member, "pair_id": pair["pair_id"], "decisive_fact": pair["decisive_fact"], "source_case": pair["source_case"], "arms": {}}
    for arm, variant in (("baseline-full", "full_original"), ("gold-only", "gold_only")):
        source = source_row["variants"][variant]
        user = replace_question(source["request"]["user"], member["question"])
        value = call(llm, f"adr49.{member['id']}.{arm}", source["request"]["system"], user, ANSWER_SCHEMA, HAIKU_MODEL)
        value.update({"evidence": source["evidence"], "generation_calls": 1})
        result["arms"][arm] = value
    source = source_row["variants"]["gold_only"]
    system = source["request"]["system"] + (
        "\n⑦ 답변 전에 내부적으로 규칙을 actor, trigger, 필수조건, 예외, 법률효과로 분해한다. "
        "질문의 사실을 각 항목에 true/false/unknown으로 대입하고, 결정적 사실 하나가 반대이면 결론도 그 법률효과에 맞게 뒤집는다. "
        "조문에 없는 요건을 만들지 말고 최종 출력에는 결론과 근거만 쓴다."
    )
    user = replace_question(source["request"]["user"], member["question"])
    guarded = call(llm, f"adr49.{member['id']}.condition_matrix", system, user, ANSWER_SCHEMA, HAIKU_MODEL)
    guarded.update({"evidence": source["evidence"], "generation_calls": 1})
    result["arms"]["condition-matrix"] = guarded
    return result


def generate(workers: int) -> None:
    frozen = json.loads(FROZEN.read_text("utf-8"))["pairs"]
    source = json.loads(SOURCE.read_text("utf-8"))
    rows = {str(row["case_no"]): row for row in source["rows"]}
    local = threading.local()
    jobspec = [(member, pair, rows[pair["source_case"]]) for pair in frozen for member in pair["members"]]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(generate_item, *spec, local): spec[0] for spec in jobspec}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result()
            print(f"[{i}/8] {item['id']} generated", flush=True)
            results.append(item)
    results.sort(key=lambda row: row["id"])
    PRODUCT.write_text(json.dumps({"schema_version": "minimal-pair-product-v1", "rows": results}, ensure_ascii=False, indent=2) + "\n", "utf-8")


def judge_item(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=OPUS_MODEL)
    result = copy.deepcopy(row)
    for arm in ARMS:
        answer = result["arms"][arm]["output"]
        user = (f"[질문]\n{row['question']}\n\n[기준답변]\n{row['reference_answer']}\n\n"
                f"[시스템 답변]\nanswerable={answer.get('answerable')}\n{answer.get('answer', '')}\n\n"
                "최소대조쌍의 반대편 답변은 보지 말고 이 문항의 결정적 조건과 법률효과가 정확한지 판정한다.")
        result["arms"][arm]["judge"] = call(local.llm, f"adr49.{row['id']}.{arm}.judge", JUDGE_SYSTEM, user, JUDGE_SCHEMA, OPUS_MODEL)
    return result


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"by_arm": {}, "pair_details": {}}
    pairs = sorted({row["pair_id"] for row in rows})
    for arm in ARMS:
        correct = {row["id"]: bool(row["arms"][arm]["judge"]["output"].get("correct")) for row in rows}
        detail = {}
        for pair in pairs:
            ids = [row["id"] for row in rows if row["pair_id"] == pair]
            detail[pair] = {"members": {item: correct[item] for item in ids}, "pair_pass": all(correct[item] for item in ids)}
        calls = [ex for row in rows for ex in row["arms"][arm]["exchanges"]]
        result["by_arm"][arm] = {
            "individual_correct": sum(correct.values()), "individual_total": len(correct),
            "pair_pass": sum(value["pair_pass"] for value in detail.values()), "pair_total": len(detail),
            "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in calls),
            "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in calls),
            "calls": len(calls),
        }
        result["pair_details"][arm] = detail
    return result


def judge(workers: int) -> None:
    rows = json.loads(PRODUCT.read_text("utf-8"))["rows"]
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_item, row, local): row for row in rows}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result()
            print(f"[{i}/8] {item['id']} judged", flush=True)
            output.append(item)
    output.sort(key=lambda row: row["id"])
    JUDGED.write_text(json.dumps({"schema_version": "minimal-pair-judged-v1", "summary": summary(output), "rows": output}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary(output), ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    calls = []
    judges = []
    decisions = []
    for arm in ARMS:
        value = row["arms"][arm]
        calls.append({"arm": arm, "request": value["request"], "output": value["output"], "exchanges": value["exchanges"]})
        judges.append({"arm": arm, **value["judge"]})
        grade = value["judge"]["output"]
        decisions.append(f"| run-001 | {arm} | {grade.get('correct')} | {grade.get('reason')} | {'-' if grade.get('correct') else 'condition_exception'} |")
    return f"""# 질문 {number:03d} — {row['id']}

## 1. 실행 메타

- ADR: `ADR-0049`
- experiment: `ADR-0049-legal-minimal-pairs-v1`
- case ID: `{row['id']}` / pair `{row['pair_id']}` / side `{row['side']}`
- run ID: `run-001`
- 원본 상태: 질문·기준답변은 수동 constructed, evidence·호출은 exact
- 제품 모델: `{HAIKU_MODEL}`; 오프라인 평가: `{OPUS_MODEL}`

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
{json.dumps({'source_case': row['source_case'], 'decisive_fact': row['decisive_fact'], 'evidence_by_arm': {arm: row['arms'][arm]['evidence'] for arm in ARMS}, 'corpus_article_roots': CORPUS}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(calls, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

```json
{json.dumps(judges, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{chr(10).join(decisions)}

- 사전 지정 비교: 같은 pair의 반대 side와 함께 맞아야 pair pass
- 공통 실패 유형: `condition_exception`
- 사람이 확인한 직접 원인: 없음 — constructed reference와 Opus 판정
- 다음 분기: holdout pair 재구성
"""


def finalize() -> None:
    blob = json.loads(JUDGED.read_text("utf-8"))
    rows, totals = blob["rows"], blob["summary"]
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    qmap = {q["case_id"]: q for q in manifest["questions"]}
    for number, row in enumerate(rows, 1):
        target = ADR / "실험" / qmap[row["id"]]["file"]
        target.write_text(question_md(row, number), "utf-8")
        qmap[row["id"]]["sha256"] = sha(target)
    manifest["runs"][0].update({"status": "complete", "sha256": sha(JUDGED)})
    manifest["results"] = {"status": "complete", "by_arm": totals["by_arm"], "comparisons": totals["pair_details"],
                           "judge_disagreements": None, "usage": {arm: {k: v for k, v in value.items() if k in {'calls','input_tokens','output_tokens'}} for arm, value in totals["by_arm"].items()},
                           "latency": {}, "error_taxonomy": ["condition_exception", "scope_actor_mismatch", "authority_or_version"]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows, totals)
    files = []
    for path, role in ((FROZEN, "frozen pairs"), (PRODUCT, "product outputs"), (JUDGED, "judged outputs"), (Path(__file__), "runner")):
        files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size, "role": role})
    (ADR / "artifacts/manifest.json").write_text(json.dumps({"schema_version": "adr-artifacts-v1", "adr_id": "ADR-0049", "files": files}, ensure_ascii=False, indent=2) + "\n", "utf-8")


def write_docs(rows: list[dict[str, Any]], totals: dict[str, Any]) -> None:
    score_rows = "\n".join(f"| `{arm}` | {totals['by_arm'][arm]['individual_correct']}/8 | {totals['by_arm'][arm]['pair_pass']}/4 | {totals['by_arm'][arm]['input_tokens']} |" for arm in ARMS)
    pair_rows = []
    for pair in PAIR_SPECS:
        flags = []
        for arm in ARMS:
            value = totals["pair_details"][arm][pair["pair_id"]]
            flags.append(f"{arm}={'PASS' if value['pair_pass'] else 'FAIL'}")
        pair_rows.append(f"| `{pair['pair_id']}` | {pair['decisive_fact']} | {' / '.join(flags)} |")
    readme = f"""---
adr_id: ADR-0049
title: 법률 조건·예외 최소대조쌍
status: Proposed
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0049: 법률 조건·예외 최소대조쌍

## 1. 결정 요약

결정적 사실 하나만 바꾼 4쌍에서 양쪽을 모두 맞히는지 측정했다. 결과는 아래와 같으며 메인 배선은 변경하지 않는다.

## 2. 문제와 변경 전 구조

단일 질문 정확도는 우연히 맞아도 법률 조건 변화에 민감한지 보여주지 않는다. actor, 예외, 수치 문턱, 자료 권위 하나를 반전한 쌍이 필요했다.

## 3. 가설과 사전 판정 기준

### 가설

Haiku는 조건을 읽어도 그 변화가 법률효과를 뒤집는 포섭에서 실패한다.

### 성공 기준

condition-matrix가 baseline보다 pair pass를 1쌍 이상 높이고 개별 회귀가 없어야 한다.

### 반증 기준

pair pass 개선이 없거나 기존 정답을 회귀하면 전역 guard로 채택하지 않는다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline-full | full 동결 근거 | 최소대조 질문 | 현 구조 |
| gold-only | 골든 조문만 | 질문·모델 | 잡음 제거 |
| condition-matrix | gold + actor/조건/예외/효과 guard | 질문·모델 | 결론 반전 강제 |

## 5. 데이터·모델·재현성

- 4쌍 8문항을 원 조문과 기준답변에서 수동 구성해 실행 전 동결했다.
- 제품 `{HAIKU_MODEL}`, evaluator `{OPUS_MODEL}` 단일 호출.
- 기준답변은 evaluator에만 제공했다.

## 6. 결과

| arm | 개별 정답 | pair pass | 제품 입력 토큰 |
|---|---:|---:|---:|
{score_rows}

## 7. 사례별 오류 분석

| pair | 결정적 사실 | arm별 pair 판정 |
|---|---|---|
{chr(10).join(pair_rows)}

질문별 실제 입출력과 judge 이유는 [실험 인덱스](실험/README.md)에 있다.

## 8. 비용·지연·회수 규모

- corpus 조문 root {CORPUS:,}개; 검색 재실행 없이 동결 bundle을 사용했다.
- arm별 제시 수와 선택률은 [manifest](실험/manifest.json)에 기록했다.

## 9. 해석

pair pass가 개별 정답보다 핵심이다. 한쪽만 맞힌 쌍은 문언을 암기했을 뿐 결정적 조건에 따라 법률효과를 안정적으로 전환하지 못한 것이다.

## 10. 한계와 일반화 가능 범위

기존 오답을 본 뒤 구성한 인샘플 수동 문항이다. 네 쌍뿐이고 Opus 판정은 사람 확정 라벨이 아니다.

## 11. 운영 결정·롤백 조건

메인 배선은 유지한다. 성공선을 넘더라도 새로운 법률 주제의 holdout pair 전에는 채택하지 않는다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_legal_minimal_pairs.py prepare
.venv/bin/python scripts/rag_legal_minimal_pairs.py generate --workers 2
.venv/bin/python scripts/rag_legal_minimal_pairs.py judge --workers 1
.venv/bin/python scripts/rag_legal_minimal_pairs.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0049-legal-minimal-pairs --final
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 hash: [실험/manifest.json](실험/manifest.json)
"""
    (ADR / "README.md").write_text(readme, "utf-8")
    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8"))
    files = {q["case_id"]: q["file"] for q in manifest["questions"]}
    lines = ["# ADR-0049 질문 인덱스", "", "| 번호 | pair | side | 질문 | 파일 |", "|---:|---|---|---|---|"]
    for i, row in enumerate(rows, 1):
        lines.append(f"| {i:03d} | `{row['pair_id']}` | `{row['side']}` | {row['question']} | [{files[row['id']]}]({files[row['id']]}) |")
    lines.extend(["", "- 4쌍 모두 두 side를 함께 맞혀야 pair pass다.", "- phase=probe, in_sample=true, decision_eligible=false."])
    (ADR / "실험/README.md").write_text("\n".join(lines) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    gen = sub.add_parser("generate"); gen.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    grd = sub.add_parser("judge"); grd.add_argument("--workers", type=int, choices=range(1, 3), default=1)
    sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.command == "generate": generate(args.workers)
    elif args.command == "judge": judge(args.workers)
    else: finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
