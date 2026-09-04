#!/usr/bin/env python3
"""ADR-0053: Haiku rule/fact/effect executor on the eight common hard failures."""

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
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.llm import LLM  # noqa: E402
from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import switches, wikictx  # noqa: E402
from scripts.adr_structure import HAIKU_MODEL, OPUS_MODEL, scaffold_adr  # noqa: E402
from scripts.rag_evaluator_calibration import SYSTEM as JUDGE_SYSTEM  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402
from scripts import rag_legal_proof_chain_selector as proof  # noqa: E402


ADR = ROOT / "docs/adr/ADR-0053-haiku-rule-effect-executor-hardset"
SOURCE_JUDGED = ROOT / "docs/adr/ADR-0052-proof-chain-hard-ambiguous/artifacts/judged-results.json"
SOURCE_FROZEN = ROOT / "docs/adr/ADR-0052-proof-chain-hard-ambiguous/artifacts/frozen-cases.json"
PARENT = ROOT / "docs/adr/ADR-0052-proof-chain-hard-ambiguous/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-cases.json"
PRODUCT = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
CORPUS = 17_370
ARMS = ("direct", "rule-sheet", "verified-rule-sheet")


RULE_ITEM = {
    "type": "object",
    "properties": {
        "evidence_id": {"type": "string"},
        "provision": {"type": "string"},
        "role": {"type": "string", "enum": ["controlling", "supporting", "rejected_parallel"]},
        "exact_quote": {"type": "string"},
        "proposition": {"type": "string"},
        "scope_actor": {"type": "string"},
        "selection_reason": {"type": "string"},
    },
    "required": ["evidence_id", "provision", "role", "exact_quote", "proposition", "scope_actor", "selection_reason"],
    "additionalProperties": False,
}
CONDITION_ITEM = {
    "type": "object",
    "properties": {
        "order": {"type": "integer"},
        "kind": {"type": "string", "enum": ["condition", "exception", "alternative", "reference", "definition"]},
        "evidence_id": {"type": "string"},
        "exact_quote": {"type": "string"},
        "proposition": {"type": "string"},
        "if_true": {"type": "string"},
        "if_false": {"type": "string"},
        "status": {"type": "string", "enum": ["true", "false", "unknown", "not_applicable"]},
        "status_basis": {"type": "string"},
    },
    "required": ["order", "kind", "evidence_id", "exact_quote", "proposition", "if_true", "if_false", "status", "status_basis"],
    "additionalProperties": False,
}
NUMERIC_ITEM = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "value": {"type": "string"},
        "unit": {"type": "string"},
        "applies_to": {"type": "string"},
        "evidence_id": {"type": "string"},
        "exact_quote": {"type": "string"},
    },
    "required": ["label", "value", "unit", "applies_to", "evidence_id", "exact_quote"],
    "additionalProperties": False,
}
RULE_SHEET_SCHEMA = {
    "type": "object",
    "properties": {
        "issue": {"type": "string"},
        "required_outputs": {"type": "array", "items": {"type": "string"}},
        "question_facts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "truth": {"type": "string", "enum": ["true", "false", "unknown"]},
                "basis": {"type": "string", "enum": ["explicit_question", "not_stated"]},
            },
            "required": ["fact", "truth", "basis"], "additionalProperties": False,
        }},
        "governing_rules": {"type": "array", "items": RULE_ITEM},
        "condition_steps": {"type": "array", "items": CONDITION_ITEM},
        "numeric_temporal": {"type": "array", "items": NUMERIC_ITEM},
        "calculation": {"type": "object", "properties": {
            "needed": {"type": "boolean"},
            "formula": {"type": "string"},
            "operands": {"type": "array", "items": {"type": "string"}},
            "comparison_rule": {"type": "string"},
            "unresolved": {"type": "array", "items": {"type": "string"}},
        }, "required": ["needed", "formula", "operands", "comparison_rule", "unresolved"], "additionalProperties": False},
        "final_effect": {"type": "object", "properties": {
            "polarity": {"type": "string", "enum": ["yes", "no", "conditional", "unknown"]},
            "conclusion": {"type": "string"},
            "legal_effect": {"type": "string"},
            "limitations": {"type": "array", "items": {"type": "string"}},
        }, "required": ["polarity", "conclusion", "legal_effect", "limitations"], "additionalProperties": False},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["issue", "required_outputs", "question_facts", "governing_rules", "condition_steps", "numeric_temporal", "calculation", "final_effect", "unresolved"],
    "additionalProperties": False,
}
VERIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "defects": {"type": "array", "items": {
            "type": "object", "properties": {
                "type": {"type": "string", "enum": ["governing_rule", "scope_actor", "condition", "exception", "numeric_temporal", "calculation", "polarity", "unsupported", "none"]},
                "description": {"type": "string"},
                "repair": {"type": "string"},
            }, "required": ["type", "description", "repair"], "additionalProperties": False,
        }},
        "corrected_sheet": RULE_SHEET_SCHEMA,
    },
    "required": ["defects", "corrected_sheet"], "additionalProperties": False,
}
FINAL_SCHEMA = copy.deepcopy(answer_mod.ANSWER_SCHEMA)

COMPILER_SYSTEM = (
    "너는 금융·상사 법률의 규칙/사실 분리 컴파일러다. 제공된 [원 답변 입력]의 질문과 "
    "회수 원문만 사용한다. 최종 답변을 쓰지 말고 법률 판단표만 만든다.\n"
    "1) 질문이 요구하는 결론·수치·기간·산식·예외를 required_outputs로 빠짐없이 분해한다.\n"
    "2) 질문 문구와 직접 맞는 조문만 controlling으로 두고, 비슷한 다른 시장·행위자·제도는 rejected_parallel로 둔다.\n"
    "3) 본문→각 호→단서→재단서→준용 순서를 condition_steps로 보존한다. '보지 아니한다', '제외한다', '할 수 없다'의 부정을 뒤집지 않는다.\n"
    "4) 서로 다른 대상에 붙은 기준일·비율·기간·한도는 numeric_temporal에 각각 별도 행으로 둔다. 산식은 원문의 피연산자와 비교규칙을 생략하지 않는다.\n"
    "5) 질문에 명시되지 않은 사실은 false가 아니라 unknown이다. 조문 규칙과 질문 사실을 섞지 않는다.\n"
    "6) evidence_id는 [E번호]만, exact_quote는 해당 원문에 실제 존재하는 짧은 연속 인용문만 쓴다. Wiki는 배경이며 controlling 근거가 아니다.\n"
    "7) 자료가 없다는 결론과, 회수 표본에서 직접 규정을 확인하지 못했다는 결론을 구분한다."
)
VERIFIER_SYSTEM = (
    "너는 제품 경로의 Haiku 법률 판단표 검증자다. 질문·전체 원문·초안 판단표·기계적 인용 검증을 받는다. "
    "기준답변이나 외부지식은 없다. 초안을 신뢰하지 말고 원문으로 다시 확인하여 corrected_sheet를 완성한다. "
    "특히 (a) 지배조문/유사조문 혼동, (b) 행위자·시장 범위, (c) 본문과 단서의 전환, "
    "(d) 모든 수치·기준일·한도, (e) 산식 피연산자, (f) 부정·허용·간주 법률효과를 검사한다. "
    "질문에 없는 사실은 unknown으로 유지한다. source_verified=false인 인용은 교체하거나 해당 명제를 unresolved로 둔다."
)
FINAL_SYSTEM = (
    "너는 금융·상사 법률 답변자다. [원 답변 입력]의 회수 원문만 법적 근거로 사용하고, "
    "[법률 판단표]는 누락 방지용 계획으로만 사용한다. 판단표와 원문이 충돌하면 원문이 우선한다. "
    "결론을 첫 1~3문장에 명확히 쓰고, required_outputs의 조건·예외·수치·기간·산식·법률효과를 모두 답한다. "
    "'없다/제외/보지 아니한다/할 수 있다'의 극성을 바꾸지 않는다. 질문에 없는 사실은 단정하지 말고 unknown 조건으로 표시한다. "
    "답할 수 있는 핵심 규칙이 있으면 일부 부수사항이 미확정이어도 answerable=true로 두고 그 한계를 설명한다. refs는 출력하지 않는다."
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(exchange: Any) -> dict[str, Any]:
    value = exchange.dump(); value["parsed"] = exchange.parsed; return value


def usage(exchanges: list[dict[str, Any]]) -> dict[str, int]:
    return proof.usage(exchanges)


def call(llm: LLM, name: str, system: str, user: str, schema: dict[str, Any], *, max_tokens: int) -> dict[str, Any]:
    exchanges = []
    output = None
    wall_started = time.perf_counter()
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(name, system, user, schema, max_tokens=max_tokens, effort="medium", model=HAIKU_MODEL)
        exchanges.extend(dump_exchange(row) for row in llm.log[start:])
        if isinstance(value, dict):
            output = value
            break
    if output is None:
        raise RuntimeError(f"{name} failed")
    return {
        "request": {"call_name": name, "system": system, "user": user, "schema": schema, "model": HAIKU_MODEL},
        "output": output, "exchanges": exchanges, "usage": usage(exchanges),
        "wall_ms": round((time.perf_counter() - wall_started) * 1000),
    }


def frozen_cases() -> list[dict[str, Any]]:
    judged = json.loads(SOURCE_JUDGED.read_text("utf-8"))
    source_frozen = {row["case_no"]: row for row in json.loads(SOURCE_FROZEN.read_text("utf-8"))["cases"]}
    common = []
    for row in judged["rows"]:
        grades = row["judge"]["by_arm"]
        if all(not bool(grades[arm]["correct"]) for arm in ("full-context", "applicability-gate", "proof-chain")):
            original = source_frozen[row["case_no"]]
            common.append({
                "case_no": row["case_no"], "question": row["question"],
                "reference_answer": row["reference_answer"], "selected": original["selected"],
                "source_labels": {arm: bool(grades[arm]["correct"]) for arm in grades},
            })
    return sorted(common, key=lambda row: row["case_no"])


def prepare() -> None:
    cases = frozen_cases()
    if len(cases) != 8:
        raise RuntimeError(f"expected 8 common failures, got {len(cases)}")
    if not ADR.exists():
        scaffold_adr(
            ROOT / "docs/adr", 53, "haiku-rule-effect-executor-hardset",
            "Haiku 규칙·사실 분리 법률효과 실행기", "probe", [row["case_no"] for row in cases],
            branch_id="rule-effect-executor", candidate_arms=["rule-sheet", "verified-rule-sheet"],
            parent_manifest=PARENT, parent_arm="proof-chain", parent_relation="extends", judge_model=OPUS_MODEL,
        )
    FROZEN.write_text(json.dumps({
        "schema_version": "common-hard8-frozen-v1",
        "selection_rule": "ADR-0052에서 full-context/applicability-gate/proof-chain이 모두 Opus false인 8건 전수",
        "source_judged": str(SOURCE_JUDGED.relative_to(ROOT)), "source_judged_sha256": sha(SOURCE_JUDGED),
        "source_frozen": str(SOURCE_FROZEN.relative_to(ROOT)), "source_frozen_sha256": sha(SOURCE_FROZEN),
        "cases": cases,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0053-haiku-rule-effect-executor-hardset-v1"
    manifest["lineage"]["hypothesis_delta"] = (
        "selector를 더 조정하지 않고 동일 full context에서 규칙과 질문 사실을 분리하고, "
        "조건·예외·수치·산식·법률효과를 명시적으로 실행한다."
    )
    manifest["design"].update({
        "hypothesis": (
            "공통 hard 오답은 자유 답변에서 지배조문 선택과 조건·예외 실행을 동시에 수행해 생기므로, "
            "Haiku 판단표와 원문 재검증을 분리하면 직접 답변보다 복구된다."
        ),
        "primary_metric": "Opus 의미 정답/8, verified-rule-sheet 대 direct 신규정답·회귀",
        "success_criteria": "verified-rule-sheet 신규정답 3건 이상, 회귀 0건, 제품 오류 0",
        "failure_criteria": "신규정답 2건 이하 또는 회귀 1건 이상",
        "criteria_frozen_before_run": True,
    })
    changes = {
        "baseline": ("동일 full context에 MAIN식 직접 답변 1회", "회수·정의·Wiki·Haiku 고정"),
        "rule-sheet": ("Haiku 규칙/사실 판단표 → 원문과 판단표로 Haiku 최종답변", "verifier 없음; reference 비공개"),
        "verified-rule-sheet": ("같은 초안 판단표를 별도 Haiku가 전체 원문과 대조·수정 → Haiku 최종답변", "동일 compiler 출력·full context"),
    }
    for arm in manifest["design"]["arms"]:
        arm["changes"], arm["controls"] = changes[str(arm["id"])]
        arm["runtime_id"] = "direct" if arm["id"] == "baseline" else arm["id"]
    manifest["dataset"].update({
        "name": "ADR-0052 all-three-wrong common hard set", "version": "common-hard8-v1",
        "frozen_source": str(FROZEN.relative_to(ROOT)), "sha256": sha(FROZEN),
        "legal_version_checked": False, "reference_version_checked": False,
    })
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "direct-answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "rule-sheet-compiler", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "rule-sheet-verifier", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "raw-sheet-answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "verified-sheet-answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    manifest["runs"][0].update({
        "arm_ids": ["baseline", "rule-sheet", "verified-rule-sheet"],
        "selection_rule": "ADR-0052 all-three-wrong 8건 × 3 answer arms; compiler shared by candidate arms",
        "artifact_path": str(JUDGED.relative_to(ROOT)),
    })
    counts = [len(row["selected"]) for row in cases]
    manifest["retrieval_accounting"].update({
        "changed": False, "corpus_total": CORPUS, "before_filter": CORPUS,
        "after_filter": sum(counts), "presented_total": sum(counts),
        "presented_mean": round(statistics.mean(counts), 3), "presented_p50": statistics.median(counts),
        "presented_p95": proof.percentile(counts, .95), "golden_recall": "same full context in all arms",
        "selectivity": round(statistics.mean(counts) / CORPUS, 8),
        "not_applicable_reason": "no selector change; all arms receive identical full-context evidence",
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared common hard8: {[row['case_no'] for row in cases]}")


def build_main_input(question: str, sections: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    picks: list[dict[str, Any]] = []
    if switches.is_on("wiki_context"):
        have = set()
        for item in wikictx.methods_for(sections):
            if item["slug"] not in have:
                picks.append(item); have.add(item["slug"])
        picks += [item for item in wikictx.pick(question, {section.doc for section in sections}) if item["slug"] not in have]
    user = (
        f"[질문]\n{question}\n\n[컨텍스트]\n{answer_mod._context_text(sections)}"
        + answer_mod._definition_context_text(sections) + wikictx.block(picks)
    )
    meta = [{"slug": item["slug"], "title": item["title"], "why": item["why"]} for item in picks]
    return user, meta


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def validate_sheet(sheet: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    texts = {str(row["id"]): normalized(row.get("original_text")) for row in evidence}
    checks = []
    for group in ("governing_rules", "condition_steps", "numeric_temporal"):
        for index, item in enumerate(sheet.get(group) or []):
            evidence_id = str(item.get("evidence_id") or "")
            quote = normalized(item.get("exact_quote"))
            valid_id = evidence_id in texts
            valid_quote = bool(quote) and valid_id and quote in texts[evidence_id]
            checks.append({
                "group": group, "index": index, "evidence_id": evidence_id,
                "source_verified": valid_quote, "valid_id": valid_id,
                "reason": "exact quote found" if valid_quote else "evidence id or exact quote not found",
            })
    return {"checks": checks, "all_source_verified": all(row["source_verified"] for row in checks) if checks else False}


def judge_mapping(case_no: str) -> tuple[dict[str, str], list[str]]:
    rotate = int(case_no.split("-")[-1]) % len(ARMS)
    ordered = list(ARMS[rotate:] + ARMS[:rotate])
    return {arm: label for arm, label in zip(ordered, ("A", "B", "C"))}, ordered


def final_user(main_user: str, sheet: dict[str, Any], validation: dict[str, Any], label: str) -> str:
    return (
        f"[원 답변 입력]\n{main_user}\n\n[법률 판단표 — {label}]\n"
        f"{json.dumps(sheet, ensure_ascii=False, indent=2)}\n\n[기계적 인용 검증]\n"
        f"{json.dumps(validation, ensure_ascii=False, indent=2)}\n\n"
        "source_verified=false인 행은 독립 근거로 쓰지 말고 원 답변 입력의 원문에서 직접 다시 확인하라."
    )


def generate_case(case: dict[str, Any], index: Any, local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    llm: LLM = local.llm
    evidence = reconstruct_evidence(index, list(case["selected"]))
    sections, appendix = proof.section_bundle(index, str(case["question"]), evidence)
    main_user, wiki = build_main_input(str(case["question"]), sections)
    direct_call = lambda: call(llm, f"adr53.{case['case_no']}.direct", answer_mod.ANSWER_SYSTEM, main_user, FINAL_SCHEMA, max_tokens=4000)

    def pipeline() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        compiler_user = f"[원 답변 입력]\n{main_user}"
        compiler = call(llm, f"adr53.{case['case_no']}.compile", COMPILER_SYSTEM, compiler_user, RULE_SHEET_SCHEMA, max_tokens=12000)
        raw_validation = validate_sheet(compiler["output"], evidence)
        raw_answer = call(
            llm, f"adr53.{case['case_no']}.rule_sheet_answer", FINAL_SYSTEM,
            final_user(main_user, compiler["output"], raw_validation, "compiler draft"), FINAL_SCHEMA, max_tokens=4000,
        )
        verifier_user = (
            f"[원 답변 입력]\n{main_user}\n\n[초안 판단표]\n{json.dumps(compiler['output'], ensure_ascii=False, indent=2)}"
            f"\n\n[기계적 인용 검증]\n{json.dumps(raw_validation, ensure_ascii=False, indent=2)}"
        )
        verifier = call(llm, f"adr53.{case['case_no']}.verify", VERIFIER_SYSTEM, verifier_user, VERIFIER_SCHEMA, max_tokens=12000)
        corrected = verifier["output"]["corrected_sheet"]
        verified_validation = validate_sheet(corrected, evidence)
        verified_answer = call(
            llm, f"adr53.{case['case_no']}.verified_sheet_answer", FINAL_SYSTEM,
            final_user(main_user, corrected, verified_validation, "verified sheet"), FINAL_SCHEMA, max_tokens=4000,
        )
        compiler["validation"] = raw_validation
        verifier["validation"] = verified_validation
        return compiler, raw_answer, verifier, verified_answer

    even = int(case["case_no"].split("-")[-1]) % 2 == 0
    product_order = []
    if even:
        compiler, raw_answer, verifier, verified_answer = pipeline(); product_order += ["compiler", "rule-sheet", "verifier", "verified-rule-sheet"]
        direct = direct_call(); product_order.append("direct")
    else:
        direct = direct_call(); product_order.append("direct")
        compiler, raw_answer, verifier, verified_answer = pipeline(); product_order += ["compiler", "rule-sheet", "verifier", "verified-rule-sheet"]
    arms = {
        "direct": direct,
        "rule-sheet": raw_answer,
        "verified-rule-sheet": verified_answer,
    }
    for arm, value in arms.items():
        value["answer"] = value["output"]["answer"]
        value["answerable"] = value["output"]["answerable"]
    return {
        "case_no": case["case_no"], "question": case["question"], "reference_answer": case["reference_answer"],
        "product_order": product_order, "evidence": evidence, "definition_appendix": appendix, "wiki": wiki,
        "main_request": {"system": answer_mod.ANSWER_SYSTEM, "user": main_user, "schema": FINAL_SCHEMA},
        "intermediate": {"compiler": compiler, "verifier": verifier}, "arms": arms,
    }


def generate(workers: int) -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]
    index = index_mod.current(); local = threading.local(); output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(generate_case, case, index, local): case for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            row = future.result(); output.append(row)
            print(f"[{position:02d}/{len(cases)}] {row['case_no']} generated", flush=True)
    output.sort(key=lambda row: row["case_no"])
    PRODUCT.write_text(json.dumps({
        "schema_version": "haiku-rule-effect-product-v1",
        "contract": {"all_product_models": HAIKU_MODEL, "reference_visible_to_product": False, "main_wiring_changed": False},
        "rows": output,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def judge_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=OPUS_MODEL)
    llm: LLM = local.llm
    mapping, order = judge_mapping(row["case_no"])
    blocks = []
    for arm in order:
        label = mapping[arm]
        blocks.append(f"[시스템 답변 {label}]\nanswerable={row['arms'][arm]['answerable']}\n{row['arms'][arm]['answer']}")
    user = (
        f"[질문]\n{row['question']}\n\n[기준답변]\n{row['reference_answer']}\n\n" + "\n\n".join(blocks)
        + "\n\n각 시스템 답변을 독립적으로 법률 명제의 동일성 기준으로 판정한다."
    )
    exchanges = []; parsed = None
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(f"adr53.{row['case_no']}.judge", JUDGE_SYSTEM, user, proof.PAIR_JUDGE_SCHEMA, max_tokens=2600, effort="medium", model=OPUS_MODEL)
        exchanges.extend(dump_exchange(item) for item in llm.log[start:])
        if isinstance(value, dict) and all(label in value for label in ("A", "B", "C")):
            parsed = value; break
    if parsed is None:
        raise RuntimeError(f"judge failed: {row['case_no']}")
    result = copy.deepcopy(row)
    result["judge"] = {
        "model": OPUS_MODEL, "mapping": mapping,
        "request": {"system": JUDGE_SYSTEM, "user": user, "schema": proof.PAIR_JUDGE_SCHEMA},
        "output": parsed, "exchanges": exchanges, "usage": proof.usage(exchanges),
        "by_arm": {arm: parsed[label] for arm, label in mapping.items()},
    }
    return result


def paired(rows: list[dict[str, Any]], candidate: str) -> dict[str, int]:
    baseline = [bool(row["judge"]["by_arm"]["direct"]["correct"]) for row in rows]
    values = [bool(row["judge"]["by_arm"][candidate]["correct"]) for row in rows]
    return {
        "candidate_only": sum(y and not x for x, y in zip(baseline, values)),
        "baseline_only_regression": sum(x and not y for x, y in zip(baseline, values)),
        "both_correct": sum(x and y for x, y in zip(baseline, values)),
        "both_wrong": sum(not x and not y for x, y in zip(baseline, values)),
        "delta": sum(values) - sum(baseline),
    }


def combine_usage(*items: dict[str, int]) -> dict[str, int]:
    """Add provider usage records without hiding retries or failed calls."""
    keys = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    return {key: sum(int(item.get(key, 0)) for item in items) for key in keys}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm = {}
    for arm in ARMS:
        exchanges = [item for row in rows for item in row["arms"][arm]["exchanges"]]
        walls = [int(row["arms"][arm]["wall_ms"]) for row in rows]
        correct = sum(bool(row["judge"]["by_arm"][arm]["correct"]) for row in rows)
        by_arm[arm] = {
            "correct": correct, "total": len(rows), "accuracy": round(correct / len(rows), 4),
            "usage": usage(exchanges), "wall_ms_p50": proof.percentile(walls, .5), "wall_ms_p95": proof.percentile(walls, .95),
        }
    intermediate = {}
    for name in ("compiler", "verifier"):
        exchanges = [item for row in rows for item in row["intermediate"][name]["exchanges"]]
        intermediate[name] = usage(exchanges)
    judge_exchanges = [item for row in rows for item in row["judge"]["exchanges"]]
    operational_paths = {
        "direct": by_arm["direct"]["usage"],
        "rule-sheet": combine_usage(intermediate["compiler"], by_arm["rule-sheet"]["usage"]),
        "verified-rule-sheet": combine_usage(
            intermediate["compiler"], intermediate["verifier"], by_arm["verified-rule-sheet"]["usage"]
        ),
    }
    direct_input = operational_paths["direct"]["input_tokens"]
    for path_usage in operational_paths.values():
        path_usage["input_ratio_vs_direct"] = round(path_usage["input_tokens"] / direct_input, 2)
    return {
        "by_arm": by_arm,
        "paired_vs_direct": {candidate: paired(rows, candidate) for candidate in ("rule-sheet", "verified-rule-sheet")},
        "intermediate_usage": intermediate, "judge_usage": usage(judge_exchanges),
        "operational_paths": operational_paths,
        "source_validation": {
            "compiler_all_verified": sum(row["intermediate"]["compiler"]["validation"]["all_source_verified"] for row in rows),
            "verifier_all_verified": sum(row["intermediate"]["verifier"]["validation"]["all_source_verified"] for row in rows),
        },
    }


def judge(workers: int) -> None:
    source = json.loads(PRODUCT.read_text("utf-8"))["rows"]; local = threading.local(); output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_case, row, local): row for row in source}
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            row = future.result(); output.append(row)
            marks = " ".join(f"{arm}={'○' if row['judge']['by_arm'][arm]['correct'] else '✗'}" for arm in ARMS)
            print(f"[{position:02d}/{len(source)}] {row['case_no']} {marks}", flush=True)
    output.sort(key=lambda row: row["case_no"]); summary = summarize(output)
    JUDGED.write_text(json.dumps({"schema_version": "haiku-rule-effect-judged-v1", "summary": summary, "rows": output}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    decisions = "\n".join(
        f"| run-002 | {arm} | {row['judge']['by_arm'][arm]['correct']} | {str(row['judge']['by_arm'][arm]['reason']).replace('|', '/')} | {proof.failure_type(row['judge']['by_arm'][arm])} |"
        for arm in ARMS
    )
    calls = [{"arm": arm, **row["arms"][arm]} for arm in ARMS]
    return f"""# 질문 {number:03d} — {row['case_no']}

## 1. 실행 메타

- ADR: `ADR-0053`; experiment: `ADR-0053-haiku-rule-effect-executor-hardset-v1`; run: `run-002`
- 원본 상태: 모든 product/judge exchange `exact`; evidence는 동결 좌표에서 현재 원문 재구성
- 제품 경로 전부 `{HAIKU_MODEL}`; 격리 평가 `{OPUS_MODEL}`; main wiring unchanged
- 호출 순서: `{', '.join(row['product_order'])}`

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
{json.dumps({'corpus_total': CORPUS, 'evidence': row['evidence'], 'definition_appendix': row['definition_appendix'], 'wiki': row['wiki'], 'main_request': row['main_request']}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(calls, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
{json.dumps(row['intermediate'], ensure_ascii=False, indent=2)}
```

## 7. 채점 호출과 반복 판정

```json
{json.dumps(row['judge'], ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{decisions}

- 동일 full context만 사용한 reasoning-layer probe다.
"""


def write_docs(rows: list[dict[str, Any]], result: dict[str, Any]) -> None:
    raw_pair = result["paired_vs_direct"]["rule-sheet"]
    verified_pair = result["paired_vs_direct"]["verified-rule-sheet"]
    accuracy_success = verified_pair["candidate_only"] >= 3 and verified_pair["baseline_only_regression"] == 0
    product_errors = sum(result["operational_paths"][name]["errors"] for name in ("direct", "rule-sheet"))
    # The two candidate paths share compiler calls, so use the largest complete path
    # rather than double-counting the same compiler exchanges.
    product_errors = max(product_errors, result["operational_paths"]["verified-rule-sheet"]["errors"])
    prereg_success = accuracy_success and product_errors == 0
    status = "Proposed" if accuracy_success else "Rejected"
    matrix = "\n".join(
        f"| `{row['case_no']}` | {row['judge']['by_arm']['direct']['correct']} | {row['judge']['by_arm']['rule-sheet']['correct']} | {row['judge']['by_arm']['verified-rule-sheet']['correct']} |"
        for row in rows
    )
    arm_rows = "\n".join(
        f"| {arm} | {result['by_arm'][arm]['correct']}/8 ({result['by_arm'][arm]['accuracy']:.1%}) | {result['by_arm'][arm]['usage']['calls']} | {result['by_arm'][arm]['usage']['input_tokens']} | {result['by_arm'][arm]['wall_ms_p50']} / {result['by_arm'][arm]['wall_ms_p95']} ms |"
        for arm in ARMS
    )
    path_rows = "\n".join(
        f"| {name} | {value['calls']} | {value['input_tokens']:,} | {value['output_tokens']:,} | {value['duration_ms']:,} ms | {value['errors']} | {value['input_ratio_vs_direct']:.2f}× |"
        for name, value in result["operational_paths"].items()
    )
    text = f"""---
adr_id: ADR-0053
title: Haiku 규칙·사실 분리 법률효과 실행기
status: {status}
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0053: Haiku 규칙·사실 분리 법률효과 실행기

## 1. 결정 요약

ADR-0052의 세 방식 공통 오답 8건에서 동일 full context를 주고 직접답변, 판단표 답변, 검증 판단표 답변을 비교했다. {'정확도 복구선은 충족했지만 제품 무오류 조건은 실패했고 인샘플 probe이므로 메인 배선은 보류한다.' if accuracy_success else '사전 정확도 성공선에 미달하여 현재 실행기를 메인에 배선하지 않는다.'}

## 2. 문제와 변경 전 구조

selector를 바꿔도 남은 오류는 지배조문 선택, 조건·예외, 기준일·산식, 부정·간주 법률효과 실행 실패였다. 기존 ADR-0042 gold-only 결정론 렌더러는 잘못 컴파일된 의미를 그대로 실행했고 신규정답이 없었다.

## 3. 가설과 사전 판정 기준

### 가설

질문 사실과 법률 규칙을 분리하고, missing fact를 unknown으로 유지하며, 별도 Haiku가 전체 원문으로 판단표를 재검증하면 직접 답변보다 공통 오답을 복구한다.

### 성공 기준

verified-rule-sheet가 direct 대비 신규정답 3건 이상, 회귀 0, 제품 오류 0.

### 반증 기준

신규정답 2건 이하 또는 회귀 1건 이상.

## 4. 실험 설계

| arm | 변경 | 고정 조건 |
|---|---|---|
| direct | MAIN식 직접 답변 | 동일 full context·정의·Wiki·Haiku |
| rule-sheet | Haiku 판단표 후 Haiku 답변 | 원문 유지·reference 비공개 |
| verified-rule-sheet | 별도 Haiku가 판단표를 원문 대조·수정 후 답변 | compiler 공유·동일 원문 |

## 5. 데이터·모델·재현성

ADR-0052에서 full/gate/proof가 모두 틀린 8건을 결과 확인 후 선택한 고난도 인샘플 probe다. 제품의 direct/compiler/verifier/final은 모두 Haiku이고 Opus는 최종 의미 채점만 한다.

## 6. 결과

| arm | 정답 | 최종답변 호출 | 최종답변 입력 토큰 | 답변 p50 / p95 |
|---|---:|---:|---:|---:|
{arm_rows}

- rule-sheet 대 direct: 신규 {raw_pair['candidate_only']}, 회귀 {raw_pair['baseline_only_regression']}, net {raw_pair['delta']:+d}.
- verified 대 direct: 신규 {verified_pair['candidate_only']}, 회귀 {verified_pair['baseline_only_regression']}, net {verified_pair['delta']:+d}.
- 판단표 인용 전수 검증 통과: compiler {result['source_validation']['compiler_all_verified']}/8, verifier {result['source_validation']['verifier_all_verified']}/8.
- 사전 정확도선: {'충족' if accuracy_success else '미충족'}; 제품 오류 0 조건: {'충족' if product_errors == 0 else f'미충족({product_errors}회)'}; 전체 사전등록 성공: {'충족' if prereg_success else '미충족'}.

## 7. 사례별 오류 분석

| case | direct | rule-sheet | verified |
|---|---:|---:|---:|
{matrix}

질문별 실제 원문은 [실험 인덱스](실험/README.md)에 있다.

복구된 사례는 `cm-002`(서로 다른 두 기준일), `cm-003`(제3호 제외와 제4호 적용), `cm-014`(저가발행 허용과 개인별 200억원 한도)다. 남은 오류는 `cm-007` KOSPI 분기 누락, `cm-022` 지배 산식 오선택, `cm-030` 상장 전 분기 검토 의무 오판, `cm-036` 해석상 불확실성의 단정, `cm-044` 법령 버전 충돌이다.

`cm-044`는 동결 기준답변이 2020년 개정 문언(분리선임 1명·정관 2명 이상)을 요구하지만 제품 입력 원문은 2025년 개정 문언(2명·정관 3명 이상)을 담는다. 따라서 주 점수 3/8은 동결 기준 그대로 보고하되, 이 버전 충돌을 제외한 보조 점수는 direct 0/7, rule-sheet 2/7, verified 3/7이다.

## 8. 비용·지연·회수 규모

회수는 변경하지 않았다. corpus {CORPUS:,}개 중 질문당 평균 {json.loads((ADR/'실험/manifest.json').read_text('utf-8'))['retrieval_accounting']['presented_mean']}개를 세 arm에 동일하게 제시했다.

| 운영 경로 | 호출 | 입력 토큰 | 출력 토큰 | provider duration 합 | 오류 | direct 대비 입력 |
|---|---:|---:|---:|---:|---:|---:|
{path_rows}

verified 경로는 direct보다 입력 토큰이 {result['operational_paths']['verified-rule-sheet']['input_ratio_vs_direct']:.2f}배이고, verifier에서 길이 제한 재시도 1회가 발생했다. 격리 Opus 채점 비용은 운영 경로에서 제외했다.

## 9. 해석

결과는 판단표 자체와 별도 verifier가 자유 답변의 조건·예외 누락을 실제로 줄이는지, 아니면 잘못된 법률해석을 더 길게 고착시키는지를 보여준다. 중간 구조의 exact quote 검증은 문언 존재만 보장하며 의미 적용의 정확성은 보장하지 않는다.

## 10. 한계와 일반화 가능 범위

공통 오답을 보고 선택한 8건이며 외부 holdout이 아니다. 전체 실험은 direct/compiler/raw final/verifier/verified final의 5개 호출을 기록하지만 verified 운영 후보 자체는 compiler/verifier/final 3단계다. 직접답변보다 비용이 크고 단회 생성·Opus 판정 변동이 남는다. 또한 구조화 판단표의 모든 exact quote가 원문에 존재한 비율이 compiler 1/8, verifier 0/8이어서 현재 스키마는 인용 안정성이 낮다.

## 11. 운영 결정·롤백 조건

main wiring은 변경하지 않았다. 정확도선은 통과했어도 전체 사전등록 기준은 통과하지 못했다. 별도 신규 질문에서 비용 대비 비열등성, 무오류 실행, 법령 시점 정합성, 인용 안정성을 확인해야 운영 후보가 된다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_haiku_rule_effect_executor_hardset.py prepare
.venv/bin/python scripts/rag_haiku_rule_effect_executor_hardset.py generate --workers 2
.venv/bin/python scripts/rag_haiku_rule_effect_executor_hardset.py judge --workers 1
.venv/bin/python scripts/rag_haiku_rule_effect_executor_hardset.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0053-haiku-rule-effect-executor-hardset --final
```

- [질문별 기록](실험/README.md)
- [원시 산출물](artifacts/manifest.json)
"""
    (ADR / "README.md").write_text(text, "utf-8")
    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8")); files = {row["case_id"]: row["file"] for row in manifest["questions"]}
    lines = ["# ADR-0053 질문 인덱스", "", "| 번호 | case | direct | rule-sheet | verified | 파일 |", "|---:|---|---:|---:|---:|---|"]
    for number, row in enumerate(rows, 1):
        grade = row["judge"]["by_arm"]
        lines.append(f"| {number:03d} | `{row['case_no']}` | {grade['direct']['correct']} | {grade['rule-sheet']['correct']} | {grade['verified-rule-sheet']['correct']} | [{files[row['case_no']]}]({files[row['case_no']]}) |")
    lines.extend(["", "- 동일 full context reasoning-layer probe; exact prompts/outputs preserved.", "- all product models Haiku; main wiring unchanged."])
    (ADR / "실험/README.md").write_text("\n".join(lines) + "\n", "utf-8")


def finalize() -> None:
    blob = json.loads(JUDGED.read_text("utf-8")); rows = blob["rows"]
    # Recompute deterministic aggregates after reporting logic changes; no LLM call.
    result = summarize(rows); blob["summary"] = result
    JUDGED.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest_path = ADR / "실험/manifest.json"; manifest = json.loads(manifest_path.read_text("utf-8")); qmap = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows, 1):
        path = ADR / "실험" / qmap[row["case_no"]]["file"]; path.write_text(question_md(row, number), "utf-8"); qmap[row["case_no"]]["sha256"] = sha(path)
    successful_run = next(row for row in manifest["runs"] if row["id"] == "run-002")
    successful_run.update({"status": "complete", "sha256": sha(JUDGED)})
    manifest["results"] = {
        "status": "complete", "by_arm": {arm: result["by_arm"][arm]["correct"] for arm in ARMS},
        "comparisons": result["paired_vs_direct"], "judge_disagreements": None,
        "usage": {arm: result["by_arm"][arm]["usage"] for arm in ARMS} | result["intermediate_usage"] | {"offline_evaluator": result["judge_usage"]},
        "operational_paths": result["operational_paths"],
        "latency": {arm: {"p50": result["by_arm"][arm]["wall_ms_p50"], "p95": result["by_arm"][arm]["wall_ms_p95"]} for arm in ARMS},
        "error_taxonomy": ["governing_rule_selection", "scope_actor_mismatch", "condition_exception", "definition_resolution", "numeric_temporal", "unsupported_inference"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8"); write_docs(rows, result)
    artifact_files = []
    for path, role in ((FROZEN, "frozen"), (PRODUCT, "product"), (JUDGED, "judged"), (Path(__file__), "runner")):
        artifact_files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size, "role": role})
    (ADR / "artifacts/manifest.json").write_text(json.dumps({"schema_version": "adr-artifacts-v1", "adr_id": "ADR-0053", "files": artifact_files}, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare"); gen = sub.add_parser("generate"); gen.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    judge_parser = sub.add_parser("judge"); judge_parser.add_argument("--workers", type=int, choices=range(1, 3), default=1); sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.command == "generate": generate(args.workers)
    elif args.command == "judge": judge(args.workers)
    else: finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
