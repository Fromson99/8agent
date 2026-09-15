#!/usr/bin/env python3
"""ADR-0052: run full/gate/proof-chain only on frozen hard and ambiguous cases."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import re
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
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.research.experiments.legal_applicability_graph import (  # noqa: E402
    ApplicabilityOntology,
)
from scripts.adr_structure import HAIKU_MODEL, OPUS_MODEL, scaffold_adr  # noqa: E402
from scripts.rag_evaluator_calibration import SYSTEM as JUDGE_SYSTEM  # noqa: E402
from scripts import rag_legal_proof_chain_selector as base  # noqa: E402


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0052-proof-chain-hard-ambiguous"
SUITE = ROOT / "01_DATA/review/cm_core_e2e_v1.json"
RETRIEVAL = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legalclosure_stage_ablation_51.json"
CANONICAL = ROOT / "01_DATA/domain_graph/canonical.json"
WRONG16 = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_hard_distractor_wrong16_v1.json"
OPUS_REGRADE = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legal_answer_repair_opus5_medium_51.json"
CALIBRATION = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0047-offline-evaluator-calibration/artifacts/calibration-results.json"
RELATION_SOURCES = (
    ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_source_relations_probe10_consensus2of3.json",
    ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_source_relations_holdout12_consensus2of2.json",
    ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_source_relations_unseen29_consensus_materialized.json",
)
PARENT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0051-fail-open-proof-chain-selector/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-cases.json"
AUDIT = ADR / "artifacts/selector-audit.json"
PRODUCT = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
ARMS = base.ARMS
CORPUS = base.CORPUS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_rows(path: Path) -> list[dict[str, Any]]:
    return list(json.loads(path.read_text("utf-8")).get("rows") or [])


def hard_ambiguous_ids() -> tuple[list[str], dict[str, list[str]]]:
    hard = {str(row["case_no"]) for row in case_rows(WRONG16)}
    regrade_mismatch = {
        str(row["case_no"])
        for row in case_rows(OPUS_REGRADE)
        if bool(row.get("baseline_recorded_semantic_correct"))
        != bool(row.get("baseline_semantic_correct"))
    }
    evaluator_disagreement = set()
    for row in case_rows(CALIBRATION):
        judges = row.get("judges") or {}
        sonnet = ((judges.get("claude-sonnet-5") or {}).get("grade") or {}).get("correct")
        opus = ((judges.get("claude-opus-5") or {}).get("grade") or {}).get("correct")
        if sonnet is not None and opus is not None and bool(sonnet) != bool(opus):
            evaluator_disagreement.add(str(row["case_no"]))
    return sorted(hard | regrade_mismatch | evaluator_disagreement), {
        "representative_main_wrong": sorted(hard),
        "recorded_vs_opus_regrade_disagreement": sorted(regrade_mismatch),
        "sonnet_vs_opus_disagreement": sorted(evaluator_disagreement),
    }


def relation_map() -> dict[str, dict[str, Any]]:
    result = {}
    for path in RELATION_SOURCES:
        for row in case_rows(path):
            case_no = str(row["case_no"])
            if case_no in result:
                raise RuntimeError(f"duplicate relation source case: {case_no}")
            result[case_no] = row
    if len(result) != 51:
        raise RuntimeError(f"relation partition is not 51 cases: {len(result)}")
    return result


def normalized_path(value: str) -> str:
    return re.sub(r"<[^>]*>|\[[^\]]*\]", "", str(value or "")).replace(" ", "")


def freeze_cases() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    ids, reasons = hard_ambiguous_ids()
    suite = json.loads(SUITE.read_text("utf-8"))
    suite_by_id = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieval_by_id = {str(row["case_no"]): row for row in case_rows(RETRIEVAL)}
    relations = relation_map()
    cases = []
    for case_no in ids:
        case = suite_by_id[case_no]
        selected = ((((retrieval_by_id[case_no].get("variants") or {})
                     .get("control_d_then_verifier") or {}).get("selected") or []))
        source = relations[case_no]
        # Relation E numbers are valid only when the frozen inventory and selected order agree.
        inventory = source.get("inventory") or []
        if len(inventory) != len(selected):
            raise RuntimeError(f"relation inventory length mismatch: {case_no}")
        for position, (relation_item, selected_item) in enumerate(zip(inventory, selected), 1):
            if str(relation_item.get("evidence_id")) != f"E{position}":
                raise RuntimeError(f"relation evidence order mismatch: {case_no}/E{position}")
            if (str(relation_item.get("document") or "")
                    != str(selected_item.get("document") or selected_item.get("doc") or "")
                    or normalized_path(relation_item.get("path"))
                    != normalized_path(selected_item.get("path"))):
                raise RuntimeError(f"relation coordinate mismatch: {case_no}/E{position}")
        cases.append({
            "case_no": case_no,
            "question": case.get("question"),
            "reference_answer": case.get("reference_answer"),
            "selected": selected,
            "source_relations": source.get("published") or [],
            "relation_inventory": inventory,
            "selection_reasons": [name for name, values in reasons.items() if case_no in values],
        })
    return cases, reasons


def prepare() -> None:
    cases, reasons = freeze_cases()
    if not ADR.exists():
        scaffold_adr(
            ROOT / "07_DOCS/REFERENCE/adr", 52, "proof-chain-hard-ambiguous",
            "기존 오답·애매 사례 proof-chain stress test", "probe",
            [row["case_no"] for row in cases],
            branch_id="hard-ambiguous-stress",
            candidate_arms=["applicability-gate", "proof-chain"],
            parent_manifest=PARENT, parent_arm="proof-chain", parent_relation="retests",
            judge_model=OPUS_MODEL,
        )
    sources = (SUITE, RETRIEVAL, CANONICAL, WRONG16, OPUS_REGRADE, CALIBRATION, *RELATION_SOURCES)
    FROZEN.write_text(json.dumps({
        "schema_version": "hard-ambiguous-frozen-v1",
        "selection_rule": (
            "대표 MAIN 35/51의 wrong16 ∪ recorded-vs-Opus regrade disagreement ∪ "
            "Sonnet-vs-Opus calibration disagreement; 중복 제거 17건"
        ),
        "selection_sets": reasons,
        "missing_source_limit": (
            "ADR에 기록된 37/51 두 번째 MAIN 실행은 원본 machine artifact가 없어 "
            "case-level selection에 사용하지 않음"
        ),
        "sources": {str(path.relative_to(ROOT)): sha(path) for path in sources},
        "cases": cases,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")

    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0052-proof-chain-hard-ambiguous-v1"
    manifest["lineage"]["hypothesis_delta"] = (
        "쉬운 answer-holdout 13건이 아니라 대표 MAIN 오답과 재채점 애매 사례 17건에서 "
        "동일 selector의 실패 복구력을 직접 측정한다."
    )
    manifest["design"].update({
        "hypothesis": (
            "회수 골든을 가진 기존 오답은 지배조문 우선순위와 관계 폐쇄 문제 비중이 높아, "
            "proof-chain이 full context보다 hard-set 정답을 실질적으로 복구한다."
        ),
        "primary_metric": "Opus 의미 정답/17 및 full 대비 candidate-only·regression",
        "success_criteria": (
            "proof-chain이 full 대비 candidate-only 4건 이상, regression 1건 이하, "
            "net +3 이상, golden article recall 손실 0, 제품 오류 0"
        ),
        "failure_criteria": "candidate-only 3건 이하, regression 2건 이상, net +2 이하, 또는 recall 손실",
        "criteria_frozen_before_run": True,
    })
    changes = {
        "baseline": ("full-context: 동결 회수 조문 전부·원래 순서", "질문·원문·정의·Wiki·Haiku·Opus judge 고정"),
        "applicability-gate": ("conclusion_candidate만 제시", "proof 우선순위·closure 없음"),
        "proof-chain": ("query-aligned source 관계와 실제 조문 구조간선으로 순서화·closure", "gold 비공개·관계 부재 시 full fallback"),
    }
    for arm in manifest["design"]["arms"]:
        arm["changes"], arm["controls"] = changes[str(arm["id"])]
        arm["runtime_id"] = "full-context" if arm["id"] == "baseline" else arm["id"]
    manifest["dataset"].update({
        "name": "cm-core representative MAIN wrong + reproducible ambiguity",
        "version": "hard-ambiguous-v1 / 17 cases",
        "frozen_source": str(FROZEN.relative_to(ROOT)), "sha256": sha(FROZEN),
        "legal_version_checked": False, "reference_version_checked": False,
    })
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    manifest["runs"][0].update({
        "arm_ids": ["baseline", "applicability-gate", "proof-chain"],
        "selection_rule": "사전 동결 hard+ambiguous 17건 × 3 arms contemporaneous; order rotated",
        "artifact_path": str(JUDGED.relative_to(ROOT)),
    })
    counts = [len(row["selected"]) for row in cases]
    manifest["retrieval_accounting"].update({
        "changed": True, "corpus_total": CORPUS, "before_filter": CORPUS,
        "after_filter": sum(counts), "presented_total": "pending by arm",
        "presented_mean": round(statistics.mean(counts), 3),
        "presented_p50": statistics.median(counts), "presented_p95": base.percentile(counts, .95),
        "golden_recall": "pending offline audit", "selectivity": "pending by arm",
        "not_applicable_reason": "upstream retrieval frozen; every final keep/drop is audited",
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {len(cases)} hard+ambiguous cases: {[row['case_no'] for row in cases]}")


def selector_audit() -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, json.loads(CANONICAL.read_text("utf-8")))
    audited = [base.audit_case(case, index, ontology) for case in cases]
    summary: dict[str, Any] = {
        "cases": len(audited),
        "activated_cases": sum(row["proof_receipt"]["coverage"] for row in audited),
        "fallback_cases": sum(not row["proof_receipt"]["coverage"] for row in audited),
        "by_arm": {},
    }
    for arm in ARMS:
        counts = [row["arms"][arm]["selected_count"] for row in audited]
        hits = sum(row["arms"][arm]["gold_hits"] for row in audited)
        total = sum(row["expected_total"] for row in audited)
        summary["by_arm"][arm] = {
            "presented_total": sum(counts), "presented_mean": round(statistics.mean(counts), 3),
            "presented_p50": statistics.median(counts), "presented_p95": base.percentile(counts, .95),
            "gold_hits": hits, "gold_total": total,
            "gold_recall": round(hits / total, 4) if total else 0,
            "mean_corpus_selectivity": round(statistics.mean(counts) / CORPUS, 8),
        }
    AUDIT.write_text(json.dumps({
        "schema_version": "hard-ambiguous-selector-audit-v1",
        "contract": {"llm_calls": 0, "gold_visible_to_selector": False, "main_wiring_changed": False},
        "summary": summary, "rows": audited,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def generate(workers: int) -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]
    audits = {row["case_no"]: row for row in json.loads(AUDIT.read_text("utf-8"))["rows"]}
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, json.loads(CANONICAL.read_text("utf-8")))
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {
            pool.submit(base.generate_case, case, audits[case["case_no"]], index, ontology, local): case
            for case in cases
        }
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            row = future.result()
            output.append(row)
            print(f"[{position:02d}/{len(cases)}] {row['case_no']} generated", flush=True)
    output.sort(key=lambda row: row["case_no"])
    PRODUCT.write_text(json.dumps({
        "schema_version": "hard-ambiguous-product-v1",
        "contract": {"product_model": HAIKU_MODEL, "gold_visible_to_product": False, "main_wiring_changed": False},
        "rows": output,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def judge_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=OPUS_MODEL)
    llm: LLM = local.llm
    mapping, order = base.judge_mapping(row["case_no"])
    blocks = []
    for arm in order:
        label = mapping[arm]
        value = row["arms"][arm]
        blocks.append(f"[시스템 답변 {label}]\nanswerable={value['answerable']}\n{value['answer']}")
    user = (
        f"[질문]\n{row['question']}\n\n[기준답변]\n{row['reference_answer']}\n\n"
        + "\n\n".join(blocks)
        + "\n\n각 시스템 답변을 독립적으로, 법률 명제의 동일성 기준으로 판정한다."
    )
    exchanges = []
    parsed = None
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(
            f"adr52.{row['case_no']}.judge", JUDGE_SYSTEM, user, base.PAIR_JUDGE_SCHEMA,
            max_tokens=2600, effort="medium", model=OPUS_MODEL,
        )
        exchanges.extend(base.dump_exchange(item) for item in llm.log[start:])
        if isinstance(value, dict) and all(label in value for label in ("A", "B", "C")):
            parsed = value
            break
    if parsed is None:
        raise RuntimeError(f"judge failed: {row['case_no']}")
    result = copy.deepcopy(row)
    result["judge"] = {
        "model": OPUS_MODEL, "mapping": mapping,
        "request": {"system": JUDGE_SYSTEM, "user": user, "schema": base.PAIR_JUDGE_SCHEMA},
        "output": parsed, "exchanges": exchanges, "usage": base.usage(exchanges),
        "by_arm": {arm: parsed[label] for arm, label in mapping.items()},
    }
    return result


def judge(workers: int) -> None:
    source = json.loads(PRODUCT.read_text("utf-8"))["rows"]
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_case, row, local): row for row in source}
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            row = future.result()
            output.append(row)
            marks = " ".join(f"{arm}={'○' if row['judge']['by_arm'][arm]['correct'] else '✗'}" for arm in ARMS)
            print(f"[{position:02d}/{len(source)}] {row['case_no']} {marks}", flush=True)
    output.sort(key=lambda row: row["case_no"])
    summary = base.summarize(output)
    JUDGED.write_text(json.dumps({
        "schema_version": "hard-ambiguous-judged-v1", "summary": summary, "rows": output,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    product = [{
        "arm": arm, "model": row["arms"][arm]["model"],
        "request_contract": row["arms"][arm]["request_contract"],
        "exchanges": row["arms"][arm]["exchanges"],
        "structured_output": {"answer": row["arms"][arm]["answer"], "answerable": row["arms"][arm]["answerable"]},
    } for arm in ARMS]
    decisions = "\n".join(
        f"| run-001 | {arm} | {row['judge']['by_arm'][arm]['correct']} | "
        f"{str(row['judge']['by_arm'][arm]['reason']).replace('|', '/')} | "
        f"{base.failure_type(row['judge']['by_arm'][arm])} |"
        for arm in ARMS
    )
    raw = {
        "corpus_total": CORPUS,
        "selection_reasons": next(item["selection_reasons"] for item in json.loads(FROZEN.read_text("utf-8"))["cases"] if item["case_no"] == row["case_no"]),
        "proof_receipt": row["proof_receipt"],
        "arms": {
            arm: {
                "selected_ids": row["arms"][arm]["selected_ids"],
                "evidence": row["arms"][arm]["evidence"],
                "definition_appendix": row["arms"][arm]["definition_appendix"],
                "wiki": row["arms"][arm]["wiki"],
            } for arm in ARMS
        },
    }
    return f"""# 질문 {number:03d} — {row['case_no']}

## 1. 실행 메타

- ADR: `ADR-0052`; experiment: `ADR-0052-proof-chain-hard-ambiguous-v1`; run: `run-001`
- 원본 상태: 제품·채점 exchange `exact`; 동결 좌표의 원문은 현재 corpus에서 재구성
- 제품 `{HAIKU_MODEL}`; 격리 평가 `{OPUS_MODEL}`; main wiring unchanged
- 제품 arm 순서: `{', '.join(row['product_order'])}`

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
{json.dumps(raw, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(product, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

```json
{json.dumps(row['judge'], ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{decisions}

- hard/ambiguous stress test이며 전체 51건 정확도로 환산하지 않는다.
"""


def write_docs(rows_: list[dict[str, Any]], result: dict[str, Any], audit: dict[str, Any]) -> None:
    pair = result["paired_vs_full"]["proof-chain"]
    gate_pair = result["paired_vs_full"]["applicability-gate"]
    recall_equal = audit["summary"]["by_arm"]["proof-chain"]["gold_hits"] == audit["summary"]["by_arm"]["full-context"]["gold_hits"]
    success = pair["candidate_only"] >= 4 and pair["baseline_only_regression"] <= 1 and pair["delta"] >= 3 and recall_equal
    status = "Accepted" if success else "Rejected"
    arm_rows = []
    for arm in ARMS:
        score = result["by_arm"][arm]
        ret = audit["summary"]["by_arm"][arm]
        arm_rows.append(
            f"| {arm} | {score['correct']}/17 ({score['accuracy']:.1%}) | {ret['presented_mean']} | "
            f"{ret['gold_hits']}/{ret['gold_total']} | {score['usage']['input_tokens']} |"
        )
    matrix = "\n".join(
        f"| `{row['case_no']}` | {row['judge']['by_arm']['full-context']['correct']} | "
        f"{row['judge']['by_arm']['applicability-gate']['correct']} | "
        f"{row['judge']['by_arm']['proof-chain']['correct']} | {row['proof_receipt']['strategy']} |"
        for row in rows_
    )
    text = f"""---
adr_id: ADR-0052
title: 기존 오답·애매 사례 proof-chain stress test
status: {status}
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0052: 기존 오답·애매 사례 proof-chain stress test

## 1. 결정 요약

대표 MAIN 오답 16건과 재현 가능한 애매 사례 1건의 합집합 17건에서만 full/gate/proof-chain을 비교했다. {'사전 복구 기준을 충족했지만 인샘플 stress test이므로 메인 배선은 보류한다.' if success else '사전 복구 기준을 충족하지 못해 현재 selector를 메인에 배선하지 않는다.'}

## 2. 문제와 변경 전 구조

ADR-0051의 13건은 hard wrong을 제외한 비교적 쉬운 집합이었다. 실제 병목을 보려면 기존에 틀렸거나 판정이 흔들린 사례만 분리해야 한다.

## 3. 가설과 사전 판정 기준

### 가설

회수 골든을 가진 기존 오답은 지배조문 우선순위·관계 폐쇄 문제 비중이 높아 proof-chain으로 복구할 수 있다.

### 성공 기준

full 대비 신규정답 4건 이상, 회귀 1건 이하, net +3 이상, golden article recall 손실 0.

### 반증 기준

신규정답 3건 이하, 회귀 2건 이상, net +2 이하 또는 recall 손실.

## 4. 실험 설계

| arm | 변경 | 고정 조건 |
|---|---|---|
| full-context | 회수 조문 전부·원래 순서 | 질문·원문·정의·Wiki·Haiku |
| applicability-gate | conclusion candidate만 | proof closure 없음 |
| proof-chain | query-aligned 관계·실제 구조간선으로 closure와 순서화 | gold 비공개·관계 부재 시 full fallback |

## 5. 데이터·모델·재현성

대표 35/51 MAIN 원장의 wrong16, recorded-vs-Opus 재채점 불일치, Sonnet-vs-Opus 교정 불일치의 합집합이다. 두 번째 37/51 실행은 원본 JSON이 없어 case 선택에는 사용하지 않았다. 제품은 전부 Haiku, 채점만 격리 Opus다.

## 6. 결과

| arm | 의미 정답 | 평균 제시 조문 | golden recall | 입력 토큰 |
|---|---:|---:|---:|---:|
{chr(10).join(arm_rows)}

- proof 대 full: 신규 {pair['candidate_only']}, 회귀 {pair['baseline_only_regression']}, 둘 다 정답 {pair['both_correct']}, 둘 다 오답 {pair['both_wrong']}, net {pair['delta']:+d}.
- gate 대 full: 신규 {gate_pair['candidate_only']}, 회귀 {gate_pair['baseline_only_regression']}, net {gate_pair['delta']:+d}.

## 7. 사례별 오류 분석

| case | full | gate | proof | 전략 |
|---|---:|---:|---:|---|
{matrix}

질문별 원문은 [실험 인덱스](실험/README.md)에 있다.

## 8. 비용·지연·회수 규모

corpus 조문 root {CORPUS:,}개 중 full 평균 {audit['summary']['by_arm']['full-context']['presented_mean']}개, proof 평균 {audit['summary']['by_arm']['proof-chain']['presented_mean']}개를 제시했다. arm별 토큰과 selectivity는 manifest·selector audit에 기록했다.

## 9. 해석

이 집합의 절대 정확도는 일부러 어려운 문제만 모은 stress score다. MAIN 51건 정확도로 환산하지 않고, 기존 실패 복구와 회귀의 방향만 해석한다.

## 10. 한계와 일반화 가능 범위

동일 benchmark를 반복 사용한 인샘플 집합이며 37/51 실행의 case-level 원본이 없다. 단회 Haiku 생성과 Opus judge 변동도 남는다.

## 11. 운영 결정·롤백 조건

main wiring은 변경하지 않았다. 성공하더라도 51건 전수 동시 반복에서 비열등성을 확인해야 운영 후보가 된다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_legal_proof_chain_hardset.py prepare
.venv/bin/python scripts/rag_legal_proof_chain_hardset.py audit
.venv/bin/python scripts/rag_legal_proof_chain_hardset.py generate --workers 2
.venv/bin/python scripts/rag_legal_proof_chain_hardset.py judge --workers 1
.venv/bin/python scripts/rag_legal_proof_chain_hardset.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0052-proof-chain-hard-ambiguous --final
```

- [질문별 기록](실험/README.md)
- [원시 산출물](artifacts/manifest.json)
"""
    (ADR / "README.md").write_text(text, "utf-8")
    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8"))
    files = {row["case_id"]: row["file"] for row in manifest["questions"]}
    lines = [
        "# ADR-0052 질문 인덱스", "",
        "| 번호 | case | full | gate | proof | 파일 |", "|---:|---|---:|---:|---:|---|",
    ]
    for number, row in enumerate(rows_, 1):
        grade = row["judge"]["by_arm"]
        lines.append(
            f"| {number:03d} | `{row['case_no']}` | {grade['full-context']['correct']} | "
            f"{grade['applicability-gate']['correct']} | {grade['proof-chain']['correct']} | "
            f"[{files[row['case_no']]}]({files[row['case_no']]}) |"
        )
    lines.extend(["", "- hard/ambiguous stress subset; not a 51-case accuracy estimate.", "- exact prompts/outputs preserved; main wiring unchanged."])
    (ADR / "실험/README.md").write_text("\n".join(lines) + "\n", "utf-8")


def finalize() -> None:
    judged = json.loads(JUDGED.read_text("utf-8"))
    audit = json.loads(AUDIT.read_text("utf-8"))
    rows_ = judged["rows"]
    result = judged["summary"]
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    qmap = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows_, 1):
        path = ADR / "실험" / qmap[row["case_no"]]["file"]
        path.write_text(question_md(row, number), "utf-8")
        qmap[row["case_no"]]["sha256"] = sha(path)
    retrieval = audit["summary"]["by_arm"]
    manifest["retrieval_accounting"].update({
        "after_filter": retrieval["proof-chain"]["presented_total"],
        "presented_total": {arm: retrieval[arm]["presented_total"] for arm in ARMS},
        "presented_mean": {arm: retrieval[arm]["presented_mean"] for arm in ARMS},
        "presented_p50": {arm: retrieval[arm]["presented_p50"] for arm in ARMS},
        "presented_p95": {arm: retrieval[arm]["presented_p95"] for arm in ARMS},
        "golden_recall": {arm: f"{retrieval[arm]['gold_hits']}/{retrieval[arm]['gold_total']}" for arm in ARMS},
        "selectivity": {arm: retrieval[arm]["mean_corpus_selectivity"] for arm in ARMS},
    })
    manifest["runs"][0].update({"status": "complete", "sha256": sha(JUDGED)})
    manifest["results"] = {
        "status": "complete", "by_arm": {arm: result["by_arm"][arm]["correct"] for arm in ARMS},
        "comparisons": result["paired_vs_full"], "judge_disagreements": None,
        "usage": {arm: result["by_arm"][arm]["usage"] for arm in ARMS} | {"offline_evaluator": result["judge_usage"]},
        "latency": {arm: {"p50": result["by_arm"][arm]["wall_ms_p50"], "p95": result["by_arm"][arm]["wall_ms_p95"]} for arm in ARMS},
        "error_taxonomy": ["governing_rule_selection", "scope_actor_mismatch", "condition_exception", "definition_resolution", "numeric_temporal", "judge_or_gold_error"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows_, result, audit)
    files = []
    for path, role in ((FROZEN, "frozen"), (AUDIT, "selector-audit"), (PRODUCT, "product"), (JUDGED, "judged"), (Path(__file__), "runner")):
        files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size, "role": role})
    (ADR / "artifacts/manifest.json").write_text(json.dumps({
        "schema_version": "adr-artifacts-v1", "adr_id": "ADR-0052", "files": files,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("audit")
    gen = sub.add_parser("generate")
    gen.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    judge_parser = sub.add_parser("judge")
    judge_parser.add_argument("--workers", type=int, choices=range(1, 3), default=1)
    sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "audit":
        selector_audit()
    elif args.command == "generate":
        generate(args.workers)
    elif args.command == "judge":
        judge(args.workers)
    else:
        finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
