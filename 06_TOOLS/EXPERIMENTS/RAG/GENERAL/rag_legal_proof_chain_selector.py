#!/usr/bin/env python3
"""ADR-0051: fail-open legal proof-chain selector on an answer-holdout slice."""

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


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM  # noqa: E402
from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legalclosure  # noqa: E402
from lawrag.research.experiments.governing_anchor_selector import (  # noqa: E402
    governing_anchor_panel,
)
from lawrag.research.experiments.legal_applicability_graph import (  # noqa: E402
    ApplicabilityOntology,
    classify_applicability,
)
from lawrag.research.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts.adr_structure import HAIKU_MODEL, OPUS_MODEL, scaffold_adr  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402
from scripts.rag_evaluator_calibration import (  # noqa: E402
    SCHEMA as SINGLE_JUDGE_SCHEMA,
    SYSTEM as JUDGE_SYSTEM,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0051-fail-open-proof-chain-selector"
SUITE = ROOT / "01_DATA/review/cm_core_e2e_v1.json"
RETRIEVAL = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legalclosure_stage_ablation_51.json"
CANONICAL = ROOT / "01_DATA/domain_graph/canonical.json"
RELATIONS = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_source_relations_unseen29_consensus_materialized.json"
WRONG16 = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_haiku_hard_distractor_wrong16_v1.json"
PRIOR_RELATION_ANSWERS = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_source_relation_annotation_answer_abc_unseen29.json"
PRIOR_APPLICABILITY_ANSWERS = ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legal_applicability_answer_ab_dev17.json"
PARENT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0050-exact-retrieval-provenance/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-cases.json"
SELECTOR_AUDIT = ADR / "artifacts/selector-audit.json"
PRODUCT = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
CORPUS = 17_370
ARMS = ("full-context", "applicability-gate", "proof-chain")
STRUCTURAL_SOURCE_RELATIONS = {
    "EXCEPTION_TO", "IMPLEMENTS", "DEFINED_BY", "CURRENT_VERSION_OF",
}
STRUCTURAL_TYPED_RELATIONS = {"배제", "준용", "위임", "수임", "근거", "정의", "의제"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(exchange: Any) -> dict[str, Any]:
    value = exchange.dump()
    value["parsed"] = exchange.parsed
    return value


def packed(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def percentile(values: list[int], proportion: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * proportion), len(ordered) - 1)]


def usage(exchanges: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.get("usage") or {}).get("input_tokens", 0)) for row in exchanges),
        "output_tokens": sum(int((row.get("usage") or {}).get("output_tokens", 0)) for row in exchanges),
        "duration_ms": sum(int(row.get("dur_ms") or 0) for row in exchanges),
        "errors": sum(bool(row.get("error")) for row in exchanges),
    }


def rows(blob: dict[str, Any]) -> list[dict[str, Any]]:
    return list(blob.get("rows") or [])


def case_ids(path: Path) -> set[str]:
    return {str(row["case_no"]) for row in rows(json.loads(path.read_text("utf-8")))}


def frozen_cases() -> list[dict[str, Any]]:
    """Select every relation-source case unseen by the two closest answer experiments."""
    suite = json.loads(SUITE.read_text("utf-8"))
    suite_by_id = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieval = json.loads(RETRIEVAL.read_text("utf-8"))
    retrieval_by_id = {str(row["case_no"]): row for row in rows(retrieval)}
    relation_blob = json.loads(RELATIONS.read_text("utf-8"))
    relation_by_id = {str(row["case_no"]): row for row in rows(relation_blob)}
    excluded = case_ids(WRONG16) | case_ids(PRIOR_RELATION_ANSWERS) | case_ids(PRIOR_APPLICABILITY_ANSWERS)
    eligible = sorted(set(relation_by_id) - excluded)
    out = []
    for case_id in eligible:
        case = suite_by_id[case_id]
        source = retrieval_by_id[case_id]
        selected = (((source.get("variants") or {}).get("control_d_then_verifier") or {}).get("selected") or [])
        out.append({
            "case_no": case_id,
            "question": case.get("question"),
            "reference_answer": case.get("reference_answer"),
            "selected": selected,
            "source_relations": relation_by_id[case_id].get("published") or [],
            "relation_inventory": relation_by_id[case_id].get("inventory") or [],
        })
    return out


def relation_certificates(question: str, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept only source-proved relations whose scope value is explicit in the question."""
    q = packed(question)
    certs = []
    for row in relations:
        relation = str(row.get("relation_type") or "")
        target = packed(str(row.get("target_value") or ""))
        accepted = False
        reason = ""
        if relation == "GOVERNS_ACTOR" and len(target) >= 2 and target in q:
            accepted, reason = True, "actor_explicit_in_question"
        elif relation == "APPLIES_TO_MARKET":
            market = str(row.get("target_value") or "").upper()
            if market == "KOSDAQ" and "코스닥" in q:
                accepted, reason = True, "kosdaq_explicit_in_question"
            elif market == "KOSPI" and ("코스피" in q or "유가증권시장" in q):
                accepted, reason = True, "kospi_explicit_in_question"
        elif relation in STRUCTURAL_SOURCE_RELATIONS:
            accepted, reason = True, "source_proved_structural_relation"
        if accepted:
            certs.append({
                "relation_id": row.get("relation_id"),
                "relation_type": relation,
                "source_id": str(row.get("source_id") or ""),
                "target_id": str(row.get("target_id") or ""),
                "target_value": row.get("target_value"),
                "reason": reason,
                "proof_quotes": row.get("proof_quotes") or [],
            })
    return certs


def proof_chain_select(
    question: str,
    classified: list[dict[str, Any]],
    source_relations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select an ordered proof bundle; absence of proof always falls back to full context."""
    by_id = {str(row.get("id") or ""): row for row in classified}
    original_ids = [str(row.get("id") or "") for row in classified]
    base_ids = [
        evidence_id for evidence_id in original_ids
        if ((by_id[evidence_id].get("applicability") or {}).get("conclusion_candidate"))
    ]
    certificates = relation_certificates(question, source_relations)
    certified_ids = {
        value for cert in certificates for value in (cert["source_id"], cert["target_id"])
        if value in by_id
    }

    companion_ids: set[str] = set()
    typed_links: dict[tuple[str, str, str], dict[str, Any]] = {}
    base_set = set(base_ids)
    for evidence_id in base_ids:
        connection = by_id[evidence_id].get("typed_connection") or {}
        for link in connection.get("all_incident_links") or []:
            relation = str(link.get("relation") or "")
            if relation not in STRUCTURAL_TYPED_RELATIONS:
                continue
            source = str(link.get("from") or "")
            target = str(link.get("to") or "")
            typed_links[(source, target, relation)] = dict(link)
            if source in base_set and target in by_id:
                companion_ids.add(target)
            if target in base_set and source in by_id:
                companion_ids.add(source)

    for cert in certificates:
        if cert["relation_type"] not in STRUCTURAL_SOURCE_RELATIONS:
            continue
        for evidence_id in (cert["source_id"], cert["target_id"]):
            if evidence_id in by_id:
                companion_ids.add(evidence_id)

    coverage = bool(certified_ids or typed_links)
    panel = governing_anchor_panel(question, classified, max_candidates=8)
    panel_ids = [str(row["evidence_id"]) for row in panel]
    if not coverage:
        receipt = {
            "strategy": "fail-open-full-context",
            "coverage": False,
            "reason": "no query-aligned source certificate and no explicit structural edge",
            "base_ids": base_ids,
            "certificates": certificates,
            "certified_ids": [],
            "typed_structural_links": [],
            "companion_ids": [],
            "anchor_panel": panel,
            "selected_ids": original_ids,
            "dropped": [],
        }
        return list(classified), receipt

    keep = base_set | companion_ids | certified_ids
    ordered_ids: list[str] = []
    for group in (
        [value for value in panel_ids if value in certified_ids],
        [value for value in panel_ids if value in keep],
        [value for value in original_ids if value in companion_ids],
        [value for value in original_ids if value in keep],
    ):
        for evidence_id in group:
            if evidence_id not in ordered_ids:
                ordered_ids.append(evidence_id)
    dropped = []
    for evidence_id in original_ids:
        if evidence_id in keep:
            continue
        applicability = by_id[evidence_id].get("applicability") or {}
        dropped.append({
            "evidence_id": evidence_id,
            "document": by_id[evidence_id].get("document"),
            "path": by_id[evidence_id].get("path"),
            "status": applicability.get("status"),
            "hard_conflict": applicability.get("hard_conflict"),
            "reason": "not conclusion candidate and not proof-connected companion",
        })
    receipt = {
        "strategy": "query-certified-proof-chain",
        "coverage": True,
        "reason": "query-aligned source certificate or explicit structural edge present",
        "base_ids": base_ids,
        "certificates": certificates,
        "certified_ids": sorted(certified_ids),
        "typed_structural_links": list(typed_links.values()),
        "companion_ids": sorted(companion_ids),
        "anchor_panel": panel,
        "selected_ids": ordered_ids,
        "dropped": dropped,
    }
    return [by_id[evidence_id] for evidence_id in ordered_ids], receipt


def section_bundle(index: Any, question: str, evidence: list[dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    sections = _sections(evidence)
    appendix = legalclosure._attach_definition_context(
        index, question, sections, eligible_doc_ids={row.doc_id for row in sections})
    return sections, appendix


def audit_case(
    case: dict[str, Any], index: Any, ontology: ApplicabilityOntology,
) -> dict[str, Any]:
    evidence = reconstruct_evidence(index, list(case["selected"]))
    evidence = attach_typed_connections(index, str(case["question"]), evidence)
    classified = classify_applicability(str(case["question"]), evidence, ontology)
    gate = [row for row in classified if (row.get("applicability") or {}).get("conclusion_candidate")]
    proof, receipt = proof_chain_select(str(case["question"]), classified, list(case["source_relations"]))
    expected = _expected_article_coords({"gold_evidence": case.get("gold_evidence") or []})
    # The suite case, not the selector, supplies gold during offline audit.
    if not expected:
        suite = json.loads(SUITE.read_text("utf-8"))
        suite_case = next(row for row in suite.get("cases") or [] if str(row["id"]) == case["case_no"])
        expected = _expected_article_coords(suite_case)

    def public(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{
            "id": row.get("id"), "doc_id": row.get("doc_id"), "node": row.get("node"),
            "document": row.get("document"), "path": row.get("path"), "role": row.get("role"),
            "relation_reason": row.get("relation_reason"), "applicability": row.get("applicability"),
            "typed_connection": row.get("typed_connection"),
        } for row in rows_]

    variants = {
        "full-context": classified,
        "applicability-gate": gate,
        "proof-chain": proof,
    }
    return {
        "case_no": case["case_no"],
        "question": case["question"],
        "expected_total": len(expected),
        "proof_receipt": receipt,
        "arms": {
            arm: {
                "selected_count": len(values),
                "gold_hits": len(expected & _coords([{"doc": row.get("document"), "path": row.get("path")} for row in values])),
                "evidence": public(values),
            }
            for arm, values in variants.items()
        },
    }


def prepare() -> None:
    cases = frozen_cases()
    if not ADR.exists():
        scaffold_adr(
            ROOT / "07_DOCS/REFERENCE/adr", 51, "fail-open-proof-chain-selector",
            "실패-개방형 법률 증명사슬 selector", "probe",
            [row["case_no"] for row in cases],
            branch_id="fail-open-proof-chain",
            candidate_arms=["applicability-gate", "proof-chain"],
            parent_manifest=PARENT, parent_arm="exact-provenance", parent_relation="extends",
            judge_model=OPUS_MODEL,
        )
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({
        "schema_version": "proof-chain-frozen-v1",
        "selection_rule": (
            "source-relation unseen29 중 ADR-0039 wrong16, 기존 relation-answer 5건, "
            "applicability-answer dev17의 합집합을 제외한 13건 전수"
        ),
        "excluded_sources": [
            str(WRONG16.relative_to(ROOT)), str(PRIOR_RELATION_ANSWERS.relative_to(ROOT)),
            str(PRIOR_APPLICABILITY_ANSWERS.relative_to(ROOT)),
        ],
        "sources": {
            str(path.relative_to(ROOT)): sha(path)
            for path in (SUITE, RETRIEVAL, CANONICAL, RELATIONS, WRONG16,
                         PRIOR_RELATION_ANSWERS, PRIOR_APPLICABILITY_ANSWERS)
        },
        "cases": cases,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")

    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0051-fail-open-proof-chain-selector-v1"
    manifest["lineage"]["hypothesis_delta"] = (
        "검색 provenance를 답변 prompt에 설명하는 대신, 원문 증명형 actor·시장 관계와 "
        "명시 조문 참조를 selector에서 사용하고 관계 증명이 없으면 full context로 되돌린다."
    )
    manifest["design"].update({
        "hypothesis": (
            "Haiku 오답의 일부는 회수된 조문 중 지배 actor·시장과 구조적으로 연결된 조문을 "
            "앞세우지 못해 생기며, 증명된 관계에서만 가지치기하고 나머지는 fail-open 하면 "
            "전체 문맥 대비 회귀 없이 정확도가 오른다."
        ),
        "primary_metric": "Opus 의미 정답/13, proof-chain 대 full-context paired 신규정답·회귀",
        "success_criteria": (
            "proof-chain이 full-context 대비 신규정답 2건 이상, 회귀 0건, golden article recall 손실 0, "
            "제품 오류 0"
        ),
        "failure_criteria": "신규정답 1건 이하, 회귀 1건 이상, 또는 golden article recall 손실",
        "criteria_frozen_before_run": True,
    })
    arm_changes = {
        "baseline": (
            "full-context: 동결 최종 회수 조문 전부를 원래 순서로 제시",
            "질문·원문·정의부록·Wiki·Haiku·Opus judge 고정",
        ),
        "applicability-gate": (
            "ontology/typed applicability의 conclusion_candidate만 제시",
            "proof 관계 우선순위와 fail-open 없음; 나머지 조건 동일",
        ),
        "proof-chain": (
            "질문과 원문으로 증명된 GOVERNS_ACTOR/APPLIES_TO_MARKET 및 명시 구조간선으로 묶고 우선순위화; 증명 부재 시 full fallback",
            "관계 생성 재호출 없음, gold 비공개, 최종 답변 prompt 형식은 baseline과 동일",
        ),
    }
    for arm in manifest["design"]["arms"]:
        manifest_id = str(arm["id"])
        logical_id = "full-context" if manifest_id == "baseline" else manifest_id
        arm["changes"], arm["controls"] = arm_changes[manifest_id]
        arm["runtime_id"] = logical_id
    manifest["dataset"].update({
        "name": "closest-answer-experiment holdout within reused cm-core-51",
        "version": "proof-chain-frozen-v1 / 13 cases",
        "frozen_source": str(FROZEN.relative_to(ROOT)),
        "sha256": sha(FROZEN),
        "legal_version_checked": False,
        "reference_version_checked": False,
    })
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    manifest["runs"][0].update({
        "arm_ids": ["baseline", "applicability-gate", "proof-chain"],
        "selection_rule": "사전 동결 13건 × 3 arms contemporaneous Haiku generation; arm order rotated by case number",
        "artifact_path": str(JUDGED.relative_to(ROOT)),
    })
    counts = [len(case["selected"]) for case in cases]
    manifest["retrieval_accounting"].update({
        "changed": True, "corpus_total": CORPUS, "before_filter": CORPUS,
        "after_filter": sum(counts), "presented_total": "pending by arm",
        "presented_mean": round(statistics.mean(counts), 3),
        "presented_p50": statistics.median(counts), "presented_p95": percentile(counts, .95),
        "golden_recall": "pending offline audit", "selectivity": "pending by arm",
        "not_applicable_reason": "upstream retrieval is frozen; selector audit records every kept/dropped final candidate",
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {ADR} with {len(cases)} cases; frozen={sha(FROZEN)}")


def selector_audit() -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, json.loads(CANONICAL.read_text("utf-8")))
    audited = [audit_case(case, index, ontology) for case in cases]
    summary = {
        "cases": len(audited),
        "activated_cases": sum(row["proof_receipt"]["coverage"] for row in audited),
        "fallback_cases": sum(not row["proof_receipt"]["coverage"] for row in audited),
        "by_arm": {},
    }
    for arm in ARMS:
        values = [row["arms"][arm]["selected_count"] for row in audited]
        hits = sum(row["arms"][arm]["gold_hits"] for row in audited)
        total = sum(row["expected_total"] for row in audited)
        summary["by_arm"][arm] = {
            "presented_total": sum(values), "presented_mean": round(statistics.mean(values), 3),
            "presented_p50": statistics.median(values), "presented_p95": percentile(values, .95),
            "gold_hits": hits, "gold_total": total,
            "gold_recall": round(hits / total, 4) if total else 0,
            "mean_corpus_selectivity": round(statistics.mean(values) / CORPUS, 8),
        }
    SELECTOR_AUDIT.write_text(json.dumps({
        "schema_version": "proof-chain-selector-audit-v1",
        "contract": {"llm_calls": 0, "gold_visible_to_selector": False, "main_wiring_changed": False},
        "summary": summary, "rows": audited,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def product_call(llm: LLM, case_no: str, arm: str, question: str, sections: list[Any]) -> dict[str, Any]:
    start = len(llm.log)
    started = time.perf_counter()
    answer = answer_mod.synthesize(llm, question, sections, spots=[])
    wall_ms = round((time.perf_counter() - started) * 1000)
    exchanges = [dump_exchange(row) for row in llm.log[start:]]
    if answer.error or not answer.answer:
        raise RuntimeError(answer.error or f"empty {case_no}/{arm} answer")
    return {
        "model": HAIKU_MODEL,
        "answer": answer.answer,
        "answerable": answer.answerable,
        "refs": answer.refs,
        "wiki": answer.wiki,
        "request_contract": {"schema": answer_mod.ANSWER_SCHEMA, "call": "rag.answer"},
        "exchanges": exchanges,
        "usage": usage(exchanges),
        "wall_ms": wall_ms,
    }


def generate_case(
    case: dict[str, Any], audit: dict[str, Any], index: Any,
    ontology: ApplicabilityOntology, local: threading.local,
) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    llm: LLM = local.llm
    question = str(case["question"])
    full = reconstruct_evidence(index, list(case["selected"]))
    full = attach_typed_connections(index, question, full)
    classified = classify_applicability(question, full, ontology)
    gate = [row for row in classified if (row.get("applicability") or {}).get("conclusion_candidate")]
    proof, receipt = proof_chain_select(question, classified, list(case["source_relations"]))
    evidence_by_arm = {"full-context": classified, "applicability-gate": gate, "proof-chain": proof}
    rotate = int(case["case_no"].split("-")[-1]) % len(ARMS)
    order = ARMS[rotate:] + ARMS[:rotate]
    arm_results: dict[str, Any] = {}
    for arm in order:
        sections, appendix = section_bundle(index, question, evidence_by_arm[arm])
        result = product_call(llm, case["case_no"], arm, question, sections)
        result.update({
            "selected_count": len(evidence_by_arm[arm]),
            "selected_ids": [row.get("id") for row in evidence_by_arm[arm]],
            "evidence": [{
                "id": row.get("id"), "doc_id": row.get("doc_id"), "node": row.get("node"),
                "document": row.get("document"), "path": row.get("path"), "role": row.get("role"),
                "relation_reason": row.get("relation_reason"), "original_text": row.get("original_text"),
                "applicability": row.get("applicability"), "typed_connection": row.get("typed_connection"),
            } for row in evidence_by_arm[arm]],
            "definition_appendix": appendix,
        })
        arm_results[arm] = result
    return {
        "case_no": case["case_no"], "question": question,
        "reference_answer": case["reference_answer"], "product_order": list(order),
        "proof_receipt": receipt, "selector_audit": audit, "arms": arm_results,
    }


def generate(workers: int) -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]
    audits = {row["case_no"]: row for row in json.loads(SELECTOR_AUDIT.read_text("utf-8"))["rows"]}
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, json.loads(CANONICAL.read_text("utf-8")))
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(generate_case, case, audits[case["case_no"]], index, ontology, local): case for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result()
            output.append(item)
            print(f"[{position:02d}/{len(cases)}] {item['case_no']} generated", flush=True)
    output.sort(key=lambda row: row["case_no"])
    PRODUCT.write_text(json.dumps({
        "schema_version": "proof-chain-product-v1",
        "contract": {"product_model": HAIKU_MODEL, "gold_visible_to_product": False, "main_wiring_changed": False},
        "rows": output,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


GRADE_FIELDS = copy.deepcopy(SINGLE_JUDGE_SCHEMA["properties"])
GRADE_REQUIRED = list(SINGLE_JUDGE_SCHEMA["required"])
PAIR_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        label: {
            "type": "object", "properties": copy.deepcopy(GRADE_FIELDS),
            "required": GRADE_REQUIRED, "additionalProperties": False,
        }
        for label in ("A", "B", "C")
    },
    "required": ["A", "B", "C"], "additionalProperties": False,
}


def judge_mapping(case_no: str) -> tuple[dict[str, str], list[str]]:
    rotate = int(case_no.split("-")[-1]) % len(ARMS)
    ordered = list(ARMS[rotate:] + ARMS[:rotate])
    mapping = {arm: label for arm, label in zip(ordered, ("A", "B", "C"))}
    return mapping, ordered


def judge_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=OPUS_MODEL)
    llm: LLM = local.llm
    mapping, order = judge_mapping(row["case_no"])
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
            f"adr51.{row['case_no']}.judge", JUDGE_SYSTEM, user, PAIR_JUDGE_SCHEMA,
            max_tokens=2600, effort="medium", model=OPUS_MODEL,
        )
        exchanges.extend(dump_exchange(item) for item in llm.log[start:])
        if isinstance(value, dict) and all(label in value for label in ("A", "B", "C")):
            parsed = value
            break
    if parsed is None:
        raise RuntimeError(f"judge failed for {row['case_no']}")
    result = copy.deepcopy(row)
    result["judge"] = {
        "model": OPUS_MODEL, "mapping": mapping,
        "request": {"system": JUDGE_SYSTEM, "user": user, "schema": PAIR_JUDGE_SCHEMA},
        "output": parsed, "exchanges": exchanges, "usage": usage(exchanges),
        "by_arm": {arm: parsed[label] for arm, label in mapping.items()},
    }
    return result


def paired(rows_: list[dict[str, Any]], candidate: str) -> dict[str, int]:
    base = [bool(row["judge"]["by_arm"]["full-context"]["correct"]) for row in rows_]
    cand = [bool(row["judge"]["by_arm"][candidate]["correct"]) for row in rows_]
    return {
        "candidate_only": sum(y and not x for x, y in zip(base, cand)),
        "baseline_only_regression": sum(x and not y for x, y in zip(base, cand)),
        "both_correct": sum(x and y for x, y in zip(base, cand)),
        "both_wrong": sum(not x and not y for x, y in zip(base, cand)),
        "delta": sum(cand) - sum(base),
    }


def summarize(rows_: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm = {}
    for arm in ARMS:
        correct = sum(bool(row["judge"]["by_arm"][arm]["correct"]) for row in rows_)
        exchanges = [item for row in rows_ for item in row["arms"][arm]["exchanges"]]
        walls = [int(row["arms"][arm]["wall_ms"]) for row in rows_]
        counts = [int(row["arms"][arm]["selected_count"]) for row in rows_]
        by_arm[arm] = {
            "correct": correct, "total": len(rows_), "accuracy": round(correct / len(rows_), 4),
            "selected_total": sum(counts), "selected_mean": round(statistics.mean(counts), 3),
            "usage": usage(exchanges), "wall_ms_p50": percentile(walls, .5),
            "wall_ms_p95": percentile(walls, .95),
        }
    judge_exchanges = [item for row in rows_ for item in row["judge"]["exchanges"]]
    return {
        "by_arm": by_arm,
        "paired_vs_full": {
            "applicability-gate": paired(rows_, "applicability-gate"),
            "proof-chain": paired(rows_, "proof-chain"),
        },
        "judge_usage": usage(judge_exchanges),
        "gold_drift_suspected": {
            arm: [row["case_no"] for row in rows_ if row["judge"]["by_arm"][arm].get("gold_drift_suspected")]
            for arm in ARMS
        },
    }


def judge(workers: int) -> None:
    source = json.loads(PRODUCT.read_text("utf-8"))["rows"]
    local = threading.local()
    output = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_case, row, local): row for row in source}
        for position, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result()
            output.append(item)
            marks = " ".join(
                f"{arm}={'○' if item['judge']['by_arm'][arm]['correct'] else '✗'}" for arm in ARMS)
            print(f"[{position:02d}/{len(source)}] {item['case_no']} {marks}", flush=True)
    output.sort(key=lambda row: row["case_no"])
    summary = summarize(output)
    JUDGED.write_text(json.dumps({
        "schema_version": "proof-chain-judged-v1", "summary": summary, "rows": output,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def failure_type(grade: dict[str, Any]) -> str:
    if grade.get("correct"):
        return "-"
    if grade.get("gold_drift_suspected"):
        return "judge_or_gold_error"
    text = packed(str(grade.get("reason") or "") + " " + " ".join(grade.get("missing_points") or []))
    if "정의" in text:
        return "definition_resolution"
    if any(value in text for value in ("예외", "조건", "요건")):
        return "condition_exception"
    if any(value in text for value in ("대상", "주체", "적용범위")):
        return "scope_actor_mismatch"
    if any(value in text for value in ("수치", "기간", "시점")):
        return "numeric_temporal"
    return "governing_rule_selection"


def question_markdown(row: dict[str, Any], number: int) -> str:
    decisions = []
    for arm in ARMS:
        grade = row["judge"]["by_arm"][arm]
        decisions.append(
            f"| run-001 | {arm} | {grade.get('correct')} | {str(grade.get('reason') or '').replace('|', '/')} | {failure_type(grade)} |"
        )
    raw_inputs = {
        "corpus_total": CORPUS,
        "upstream_selected": row["selector_audit"]["arms"]["full-context"]["evidence"],
        "proof_receipt": row["proof_receipt"],
        "arm_evidence_and_definitions": {
            arm: {
                "selected_ids": row["arms"][arm]["selected_ids"],
                "evidence": row["arms"][arm]["evidence"],
                "definition_appendix": row["arms"][arm]["definition_appendix"],
                "wiki": row["arms"][arm]["wiki"],
            }
            for arm in ARMS
        },
    }
    product_calls = [{
        "arm": arm, "model": row["arms"][arm]["model"],
        "request_contract": row["arms"][arm]["request_contract"],
        "exchanges": row["arms"][arm]["exchanges"],
        "structured_output": {"answer": row["arms"][arm]["answer"], "answerable": row["arms"][arm]["answerable"]},
    } for arm in ARMS]
    return f"""# 질문 {number:03d} — {row['case_no']}

## 1. 실행 메타

- ADR: `ADR-0051`; experiment: `ADR-0051-fail-open-proof-chain-selector-v1`; case: `{row['case_no']}`; run: `run-001`
- 원본 상태: 제품·채점 호출 `exact`; selector 입력은 동결 좌표에서 현재 corpus 원문을 재구성
- 제품 모델: `{HAIKU_MODEL}`; 격리 평가 모델: `{OPUS_MODEL}`
- 제품 arm 실행 순서: `{', '.join(row['product_order'])}`

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
{json.dumps(raw_inputs, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(product_calls, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

- selector는 결정론이며 LLM 호출이 없다. 관계가 증명되지 않은 사례는 `fail-open-full-context`로 복귀했다.

## 7. 채점 호출과 반복 판정

```json
{json.dumps(row['judge'], ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{chr(10).join(decisions)}

- proof-chain 활성화: `{row['proof_receipt']['coverage']}`
- 선택 비교: full `{row['arms']['full-context']['selected_count']}` / gate `{row['arms']['applicability-gate']['selected_count']}` / proof `{row['arms']['proof-chain']['selected_count']}`
- 사람 직접원인 확정: 없음; 위 실패 유형은 Opus 사유의 결정론적 분류
"""


def write_docs(rows_: list[dict[str, Any]], result: dict[str, Any], audit: dict[str, Any]) -> None:
    matrix = "\n".join(
        f"| `{row['case_no']}` | {row['judge']['by_arm']['full-context']['correct']} | "
        f"{row['judge']['by_arm']['applicability-gate']['correct']} | "
        f"{row['judge']['by_arm']['proof-chain']['correct']} | "
        f"{row['proof_receipt']['strategy']} |"
        for row in rows_
    )
    arm_rows = []
    for arm in ARMS:
        score = result["by_arm"][arm]
        retrieve = audit["summary"]["by_arm"][arm]
        arm_rows.append(
            f"| {arm} | {score['correct']}/{score['total']} ({score['accuracy']:.1%}) | "
            f"{retrieve['presented_mean']} | {retrieve['gold_hits']}/{retrieve['gold_total']} | "
            f"{score['usage']['input_tokens']} | {score['wall_ms_p50']} / {score['wall_ms_p95']} ms |"
        )
    proof_pair = result["paired_vs_full"]["proof-chain"]
    gate_pair = result["paired_vs_full"]["applicability-gate"]
    success = (
        proof_pair["candidate_only"] >= 2
        and proof_pair["baseline_only_regression"] == 0
        and audit["summary"]["by_arm"]["proof-chain"]["gold_hits"]
        == audit["summary"]["by_arm"]["full-context"]["gold_hits"]
    )
    status = "Accepted" if success else "Rejected"
    decision = (
        "사전 성공선을 충족했지만 재사용 benchmark probe이므로 메인 배선은 보류한다."
        if success else "사전 성공선을 충족하지 못해 메인 배선에 넣지 않는다."
    )
    text = f"""---
adr_id: ADR-0051
title: 실패-개방형 법률 증명사슬 selector
status: {status}
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0051: 실패-개방형 법률 증명사슬 selector

## 1. 결정 요약

{decision} 제품 답변은 전부 Haiku, 채점은 제품과 격리된 Opus 단일 호출이다.

## 2. 문제와 변경 전 구조

조문을 평균 10여 개까지 줄여도 Haiku가 검색 경로 설명만으로 지배규범을 고르지 못했다. 정의·예외 관계가 없다는 이유로 근거를 삭제하면 cm-031 같은 보조조문 회귀 위험도 있다.

## 3. 가설과 사전 판정 기준

### 가설

질문에 명시된 actor·시장과 원문 증명형 관계, 실제 조문 참조가 있을 때만 지배 근거를 앞세우고, 관계 증명이 없으면 full context로 돌아가면 회귀 없이 정확도가 오른다.

### 성공 기준

proof-chain 대 full-context 신규정답 2건 이상, 회귀 0건, golden article recall 손실 0, 제품 오류 0.

### 반증 기준

신규정답 1건 이하, 회귀 1건 이상 또는 golden article recall 손실.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| full-context | 동결 최종 회수 전부·원래 순서 | 질문·원문·정의·Wiki·Haiku | 기준 |
| applicability-gate | conclusion candidate만 보존 | 관계 우선순위·fallback 없음 | 단순 가지치기 대조 |
| proof-chain | query-aligned 원문 관계와 명시 구조간선으로 우선순위화; 증명 부재 시 full fallback | gold 비공개·답변 prompt 형식 동일 | 실패-개방형 selector |

## 5. 데이터·모델·재현성

가장 가까운 relation-answer 및 applicability-answer 실험에서 답변을 생성하지 않은 13건 전수다. 다만 전체 cm-core-51은 이전 개발에 반복 사용되었으므로 `probe/in_sample`이며 일반화 판정용 holdout은 아니다.

## 6. 결과

| arm | 의미 정답 | 평균 제시 조문 | golden article recall | 입력 토큰 | 답변 p50 / p95 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(arm_rows)}

- proof-chain 대 full: 신규정답 {proof_pair['candidate_only']}, 회귀 {proof_pair['baseline_only_regression']}, 둘 다 정답 {proof_pair['both_correct']}, 둘 다 오답 {proof_pair['both_wrong']}, delta {proof_pair['delta']:+d}.
- applicability gate 대 full: 신규정답 {gate_pair['candidate_only']}, 회귀 {gate_pair['baseline_only_regression']}, delta {gate_pair['delta']:+d}.
- proof-chain 활성 {audit['summary']['activated_cases']}/13, 관계 증명 부재로 full fallback {audit['summary']['fallback_cases']}/13.

## 7. 사례별 오류 분석

| case | full | gate | proof | proof 전략 |
|---|---:|---:|---:|---|
{matrix}

사례별 실제 prompt·응답·채점 원문과 탈락 이유는 [실험 인덱스](실험/README.md)에 보존했다.

## 8. 비용·지연·회수 규모

전체 corpus는 조문 root {CORPUS:,}개다. upstream full-context 평균은 {audit['summary']['by_arm']['full-context']['presented_mean']}개({audit['summary']['by_arm']['full-context']['mean_corpus_selectivity']:.4%}), proof-chain 평균은 {audit['summary']['by_arm']['proof-chain']['presented_mean']}개({audit['summary']['by_arm']['proof-chain']['mean_corpus_selectivity']:.4%})다. 필터 전·후·실제 제시 수는 `selector-audit.json`의 사례별 receipt에 모두 기록했다.

## 9. 해석

관계가 없는 것을 무관함으로 해석하지 않는 것이 핵심이다. proof-chain의 성능과 paired 이동으로 actor/scope 관계가 실제 답변 선택에 도움이 되는지 판단한다. 정의·예외·준용 관계가 이 13건에 희소하므로 이번 결과는 완전한 법률 proof graph가 아니라 actor/scope 인증 단계의 검증이다.

## 10. 한계와 일반화 가능 범위

13건 소표본이며 동일 51건 benchmark에서 갈라낸 answer-holdout이다. 질문과 기준답변 자체는 프로젝트 개발 과정에서 알려져 있어 외부 일반화 성능으로 볼 수 없다. Opus 판정도 사람 truth가 아니며 gold drift 의심 사례는 별도 표시했다.

## 11. 운영 결정·롤백 조건

메인 배선은 변경하지 않았다. 외부 신규 질문 holdout에서 같은 성공선과 법령 버전 검사를 통과하기 전에는 운영 승격하지 않는다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_legal_proof_chain_selector.py prepare
.venv/bin/python scripts/rag_legal_proof_chain_selector.py audit
.venv/bin/python scripts/rag_legal_proof_chain_selector.py generate --workers 2
.venv/bin/python scripts/rag_legal_proof_chain_selector.py judge --workers 1
.venv/bin/python scripts/rag_legal_proof_chain_selector.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0051-fail-open-proof-chain-selector --final
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문별 기록: [실험/README.md](실험/README.md)
"""
    (ADR / "README.md").write_text(text, "utf-8")

    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8"))
    files = {row["case_id"]: row["file"] for row in manifest["questions"]}
    lines = [
        "# ADR-0051 질문 인덱스", "",
        "| 번호 | case | full | gate | proof | 활성 | 파일 |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for number, row in enumerate(rows_, 1):
        grades = row["judge"]["by_arm"]
        lines.append(
            f"| {number:03d} | `{row['case_no']}` | {grades['full-context']['correct']} | "
            f"{grades['applicability-gate']['correct']} | {grades['proof-chain']['correct']} | "
            f"{row['proof_receipt']['coverage']} | [{files[row['case_no']]}]({files[row['case_no']]}) |"
        )
    lines.extend([
        "", "- 제품 입력·출력은 exact exchange로, selector 결정은 proof receipt로 보존했다.",
        "- phase=probe, in_sample=true, decision_eligible=false, main wiring unchanged.",
    ])
    (ADR / "실험/README.md").write_text("\n".join(lines) + "\n", "utf-8")


def finalize() -> None:
    blob = json.loads(JUDGED.read_text("utf-8"))
    rows_ = blob["rows"]
    result = blob["summary"]
    audit = json.loads(SELECTOR_AUDIT.read_text("utf-8"))
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    qmap = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows_, 1):
        path = ADR / "실험" / qmap[row["case_no"]]["file"]
        path.write_text(question_markdown(row, number), "utf-8")
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
        "status": "complete",
        "by_arm": {arm: result["by_arm"][arm]["correct"] for arm in ARMS},
        "comparisons": result["paired_vs_full"],
        "judge_disagreements": None,
        "usage": {arm: result["by_arm"][arm]["usage"] for arm in ARMS} | {"offline_evaluator": result["judge_usage"]},
        "latency": {arm: {"p50": result["by_arm"][arm]["wall_ms_p50"], "p95": result["by_arm"][arm]["wall_ms_p95"]} for arm in ARMS},
        "error_taxonomy": [
            "governing_rule_selection", "scope_actor_mismatch", "condition_exception",
            "definition_resolution", "numeric_temporal", "judge_or_gold_error",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows_, result, audit)
    artifact_files = []
    for path, role in (
        (FROZEN, "frozen"), (SELECTOR_AUDIT, "selector-audit"),
        (PRODUCT, "product"), (JUDGED, "judged"), (Path(__file__), "runner"),
    ):
        artifact_files.append({
            "path": str(path.relative_to(ROOT)), "sha256": sha(path),
            "bytes": path.stat().st_size, "role": role,
        })
    (ADR / "artifacts/manifest.json").write_text(json.dumps({
        "schema_version": "adr-artifacts-v1", "adr_id": "ADR-0051", "files": artifact_files,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("audit")
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
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
