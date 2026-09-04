#!/usr/bin/env python3
"""Run the frozen legal-reasoning portfolio requested in ADR-0048.

The product path is Haiku-only.  Opus is used only after answers are frozen, as
an isolated semantic evaluator.  Existing baseline arms are replayed from the
ADR-0039 ledger and therefore do not make product calls.
"""

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
from scripts.rag_evaluator_calibration import (  # noqa: E402
    SCHEMA as JUDGE_SCHEMA,
    SYSTEM as JUDGE_SYSTEM,
)


ADR = ROOT / "docs/adr/ADR-0048-legal-reasoning-causal-portfolio"
SOURCE = ROOT / "var/eval/e2e/cm_core_haiku_hard_distractor_wrong16_v1.json"
FUNNEL = ROOT / "var/eval/e2e/cm_core_retrieval_selectivity_funnel_51.json"
PARENT = ROOT / "docs/adr/ADR-0047-offline-evaluator-calibration/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-cases.json"
GENERATED = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
PREFLIGHT = ADR / "artifacts/run-001-preflight-failures.json"
MIXED_RUN = ADR / "artifacts/run-002-mixed-replay-results.json"
SELECTED = ("cm-003", "cm-012", "cm-024", "cm-030", "cm-036", "cm-041", "cm-044", "cm-051")
CORPUS_ARTICLES = 17_370

ARMS = (
    "baseline-full",
    "ladder-gold",
    "ladder-gold-definition",
    "ladder-gold-supportive",
    "rule-fact-split",
    "wiki-none",
    "wiki-related",
    "wiki-placebo",
    "authority-unlabeled",
    "authority-labeled",
    "selective-unknown",
    "retrieval-trace",
)

REUSED = {
    "baseline-full": "full_original",
    "ladder-gold": "gold_only",
    "ladder-gold-supportive": "supportive_after",
    "wiki-related": "full_original",
    "authority-unlabeled": "hard_after",
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "answerable": {"type": "boolean"}},
    "required": ["answer", "answerable"],
    "additionalProperties": False,
}
RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "issue": {"type": "string"},
        "governing_rules": {"type": "array", "items": {"type": "string"}},
        "actors": {"type": "array", "items": {"type": "string"}},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "exceptions": {"type": "array", "items": {"type": "string"}},
        "legal_effect": {"type": "array", "items": {"type": "string"}},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["issue", "governing_rules", "actors", "conditions", "exceptions", "legal_effect", "unresolved"],
    "additionalProperties": False,
}
FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "actors": {"type": "array", "items": {"type": "string"}},
        "acts": {"type": "array", "items": {"type": "string"}},
        "times": {"type": "array", "items": {"type": "string"}},
        "amounts": {"type": "array", "items": {"type": "string"}},
        "stated_conditions": {"type": "array", "items": {"type": "string"}},
        "unknown_facts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["actors", "acts", "times", "amounts", "stated_conditions", "unknown_facts"],
    "additionalProperties": False,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(exchange: Any) -> dict[str, Any]:
    value = exchange.dump()
    value["parsed"] = exchange.parsed
    return value


def split_user(user: str) -> tuple[str, str, str]:
    """Return question, context-without-wiki, and exact wiki tail."""
    marker = "\n\n[해석 맥락 — 지식 위키]"
    body, sep, wiki = user.partition(marker)
    question = body.partition("[컨텍스트]")[0].strip()
    return question, body, (sep + wiki if sep else "")


def classifier_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((row.get("classifier") or {}).get("output") or {}).get("rows") or [])


def render_evidence_card(evidence: dict[str, Any], heading: str) -> str:
    return (
        f"\n\n[{heading}]\n"
        f"문서: {evidence.get('document', '')}\n"
        f"경로: {evidence.get('path', '')}\n"
        f"원문:\n{evidence.get('original_text', '')}"
    )


def definition_cards(row: dict[str, Any]) -> tuple[str, list[str]]:
    full = row["variants"]["full_original"]["evidence"]
    by_id = {str(e.get("id")): e for e in full}
    picked: list[dict[str, Any]] = []
    for audit in classifier_rows(row):
        ev = by_id.get(str(audit.get("id")))
        hay = " ".join((str(audit.get("reason", "")), str((ev or {}).get("path", ""))))
        if ev and audit.get("label") == "SUPPORTIVE" and "정의" in hay:
            picked.append(ev)
    # Some legal issues have no separate definition article.  Keep the arm
    # deterministic and record the fallback rather than inventing a card.
    picked = picked[:2]
    cards = "".join(render_evidence_card(ev, f"연결 정의 카드 {i}") for i, ev in enumerate(picked, 1))
    return cards, [str(ev.get("id")) for ev in picked]


def audit_trace(row: dict[str, Any]) -> str:
    full_ids = {str(e.get("id")) for e in row["variants"]["full_original"]["evidence"]}
    lines = [
        "[검색·선별 과정 — 재구성 감사 trace; 법적 근거가 아님]",
        f"- 현재 조문 root 전체: {CORPUS_ARTICLES:,}개",
        f"- 원 실행 최종 제시: {len(full_ids)}개 ({len(full_ids) / CORPUS_ARTICLES:.4%})",
        "- presented 여부는 원 실행 증거목록에서 확인했다.",
        "- label/risk/reason은 원 실행 뒤 Haiku가 만든 사후 오답감사 분류다. 당시 selector의 실제 탈락 사유가 아니다.",
    ]
    for audit in classifier_rows(row):
        aid = str(audit.get("id"))
        lines.append(
            f"- {aid}: presented={str(aid in full_ids).lower()}, "
            f"audit_label={audit.get('label')}, risk={audit.get('risk')}, "
            f"audit_reason={audit.get('reason')}"
        )
    lines.extend([
        "- 기록에 없는 전체 탈락 후보와 탈락 사유는 unknown이다.",
        "사용 규칙: 이 trace 자체를 법적 근거나 결론으로 인용하지 말고, 제시된 조문 중 지배규범·정의·예외를 구분하는 주의표시로만 사용한다.",
    ])
    return "\n".join(lines)


def authority_labels(row: dict[str, Any]) -> str:
    hard_ids = {str(e.get("id")) for e in row["variants"]["hard_after"]["evidence"]}
    lines = ["[권위·적용범위 감사표 — 사후 분류; 조문 원문이 우선]"]
    for audit in classifier_rows(row):
        if str(audit.get("id")) in hard_ids:
            lines.append(
                f"- {audit.get('id')}: {audit.get('label')} / {audit.get('subtype')} / "
                f"risk={audit.get('risk')} / {audit.get('reason')}"
            )
    lines.append("규칙: 같은 주제라는 이유만으로 낮은 권위·다른 actor·시장·시점의 규정을 지배규범으로 삼지 않는다.")
    return "\n".join(lines)


def frozen_cases() -> list[dict[str, Any]]:
    source = json.loads(SOURCE.read_text("utf-8"))
    by_case = {str(row["case_no"]): row for row in source["rows"]}
    return [copy.deepcopy(by_case[case]) for case in SELECTED]


def prepare() -> None:
    rows = frozen_cases()
    if not ADR.exists():
        scaffold_adr(
            ROOT / "docs/adr", 48, "legal-reasoning-causal-portfolio",
            "법률 추론 원인분리 포트폴리오", "probe", list(SELECTED),
            branch_id="legal-reasoning-causal",
            candidate_arms=list(ARMS[1:]),
            parent_manifest=PARENT,
            parent_arm="opus-single",
            parent_relation="extends",
            judge_model=OPUS_MODEL,
        )
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({
        "schema_version": "legal-reasoning-causal-frozen-v1",
        "selection_rule": (
            "ADR-0039 wrong16에서 exception, authority, numeric, actor/scope, conclusion-conflict, "
            "version, reference-closure 오류군을 실행 전 8건으로 층화 고정"
        ),
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha(SOURCE),
        "funnel_source": str(FUNNEL.relative_to(ROOT)),
        "funnel_sha256": sha(FUNNEL),
        "cases": rows,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")

    path = ADR / "실험/manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0048-legal-reasoning-causal-v1"
    manifest["lineage"]["hypothesis_delta"] = (
        "회수된 조문이 있어도 잡음·정의/예외·포섭 결합·Wiki·권위·불확실성 처리 때문에 답이 틀리는 원인을 분리한다."
    )
    manifest["design"].update({
        "hypothesis": (
            "오답의 주원인은 단일 회수 실패가 아니라 지배규범 선택, 조건·예외 포섭, 무관 Wiki와 권위 충돌이며 "
            "검색 trace 또는 단계 분리가 일부 오류군만 선택적으로 줄인다."
        ),
        "primary_metric": "Opus single 의미 정답/8, baseline 대비 paired 신규정답·회귀; 유보 arm은 coverage와 selective accuracy 병기",
        "success_criteria": (
            "각 후보 arm이 baseline 8건에서 신규정답 2건 이상이고 회귀 0건이거나, 원인분리 진단에서 사전 예상 방향의 단조성이 확인됨; "
            "모든 제품·중간 생성은 Haiku, 평가만 Opus; 호출 오류 0"
        ),
        "failure_criteria": (
            "신규정답 1건 이하, 회귀 발생, 4-arm 근거 사다리 비단조, placebo가 관련 Wiki와 동등 이상, 또는 trace가 원인표를 근거로 오인"
        ),
        "criteria_frozen_before_run": True,
    })
    changes = {
        "baseline": "저장 full_original 답변 재사용",
        "baseline-full": "저장 full_original 답변 재사용",
        "ladder-gold": "골든 조문만 제시한 저장 답변",
        "ladder-gold-definition": "골든 조문에 매칭된 정의 카드만 추가",
        "ladder-gold-supportive": "골든+supportive closure 저장 답변",
        "rule-fact-split": "규칙 추출과 사실 추출을 별도 Haiku 호출 후 포섭",
        "wiki-none": "full context에서 Wiki 제거",
        "wiki-related": "원래 관련도 미확정 Wiki 유지",
        "wiki-placebo": "다음 사건 Wiki로 교체",
        "authority-unlabeled": "골든+유사 hard distractor, 표지 없음",
        "authority-labeled": "같은 bundle에 권위·actor·시장 사후 감사표 추가",
        "selective-unknown": "필수 조건 미확인이면 answerable=false 허용",
        "retrieval-trace": "검색 규모·제시 여부·사후 audit 사유를 구분한 trace 추가",
    }
    for arm in manifest["design"]["arms"]:
        arm_id = str(arm["id"])
        arm["changes"] = changes[arm_id]
        arm["controls"] = "같은 질문·기준답변·Haiku 제품 모델·Opus 단일 judge; 명시된 입력 구성만 변경"
    manifest["dataset"].update({
        "name": "ADR-0039 wrong16 stratified causal probe",
        "version": "wrong16-v1 / frozen 8",
        "frozen_source": str(FROZEN.relative_to(ROOT)),
        "sha256": sha(FROZEN),
        "legal_version_checked": False,
        "reference_version_checked": False,
    })
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "answer-and-intermediate", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    # The generic scaffold calls the control arm ``baseline``.  This portfolio
    # names it explicitly because several other arms are also stored replays.
    for arm in manifest["design"]["arms"]:
        if arm["id"] == "baseline":
            arm["id"] = "baseline-full"
        arm["derived_from"] = ["baseline-full" if ref == "baseline" else ref
                               for ref in arm.get("derived_from", [])]
    manifest["runs"][0].update({
        "arm_ids": list(ARMS),
        "selection_rule": "동결 8건 전수 × 12 arms; 결과 확인 전 arm·prompt·criteria 고정",
        "artifact_path": str(JUDGED.relative_to(ROOT)),
    })
    # Preserve a code-level preflight failure as an immutable run.  This path
    # is reached only before any provider call because the failure happened
    # while splitting the first prompt.
    if GENERATED.exists():
        prior = json.loads(GENERATED.read_text("utf-8"))
        if prior.get("rows") and all(item.get("error") for item in prior["rows"]):
            PREFLIGHT.write_bytes(GENERATED.read_bytes())
            manifest["runs"][0].update({
                "status": "invalid",
                "artifact_path": str(PREFLIGHT.relative_to(ROOT)),
                "sha256": sha(PREFLIGHT),
                "selection_rule": "동결 8건 전수 preflight; prompt split 전 지역변수 shadowing으로 provider 호출 0",
            })
            if not any(run.get("id") == "run-002" for run in manifest["runs"]):
                manifest["runs"].append({
                    "id": "run-002", "purpose": "repeat", "parent_run_id": "run-001",
                    "arm_ids": list(ARMS),
                    "selection_rule": "동일 동결 8건 × 12 arms; 지역변수 shadowing 수정 후 재실행",
                    "status": "planned", "artifact_path": str(JUDGED.relative_to(ROOT)),
                    "sha256": "PENDING",
                })
    manifest["retrieval_accounting"].update({
        "changed": True,
        "corpus_total": CORPUS_ARTICLES,
        "before_filter": CORPUS_ARTICLES,
        "after_filter": sum(len(row["variants"]["full_original"]["evidence"]) for row in rows),
        "presented_total": sum(len(row["variants"]["full_original"]["evidence"]) for row in rows),
        "presented_mean": round(statistics.mean(len(row["variants"]["full_original"]["evidence"]) for row in rows), 3),
        "presented_p50": statistics.median(len(row["variants"]["full_original"]["evidence"]) for row in rows),
        "presented_p95": max(len(row["variants"]["full_original"]["evidence"]) for row in rows),
        "golden_recall": "8/8 diagnostic subset",
        "selectivity": round(sum(len(row["variants"]["full_original"]["evidence"]) for row in rows) / (len(rows) * CORPUS_ARTICLES), 8),
        "not_applicable_reason": "arm별 제시량은 결과 artifact의 retrieval_by_arm에 별도 기록",
    })
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {ADR}; frozen={len(rows)} sha256={sha(FROZEN)}")


def call_structured(llm: LLM, call_name: str, system: str, user: str, schema: dict[str, Any], *, model: str) -> dict[str, Any]:
    exchanges: list[dict[str, Any]] = []
    parsed: dict[str, Any] | None = None
    for _ in range(3):
        start = len(llm.log)
        value = llm.structured(call_name, system, user, schema, max_tokens=1800, effort="medium", model=model)
        exchanges.extend(dump_exchange(ex) for ex in llm.log[start:])
        if isinstance(value, dict):
            parsed = dict(value)
            break
    if parsed is None:
        raise RuntimeError(f"{call_name} failed after 3 attempts")
    return {"request": {"call_name": call_name, "system": system, "user": user, "schema": schema, "model": model},
            "output": parsed, "exchanges": exchanges}


def variant_replay(row: dict[str, Any], variant: str) -> dict[str, Any]:
    value = row["variants"][variant]
    return {
        "source": "stored-replay",
        "source_variant": variant,
        "evidence": value.get("evidence", []),
        "request": value.get("request", {}),
        "output": value.get("output", {}),
        "exchanges": value.get("raw_exchanges", []),
        "generation_calls": 0,
    }


def generate_case(row: dict[str, Any], placebo_wiki: str, local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    llm: LLM = local.llm
    case = str(row["case_no"])
    full = row["variants"]["full_original"]
    gold = row["variants"]["gold_only"]
    hard = row["variants"]["hard_after"]
    question_part, full_no_wiki, full_wiki = split_user(full["request"]["user"])
    _, gold_no_wiki, gold_wiki = split_user(gold["request"]["user"])
    arms: dict[str, Any] = {arm: variant_replay(row, variant) for arm, variant in REUSED.items()}

    cards, card_ids = definition_cards(row)
    definition_user = gold_no_wiki + cards + gold_wiki
    arms["ladder-gold-definition"] = call_structured(
        llm, f"adr48.{case}.ladder_gold_definition", gold["request"]["system"],
        definition_user, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["ladder-gold-definition"].update({"source": "generated", "evidence": gold["evidence"], "definition_card_ids": card_ids, "generation_calls": 1})

    rule_system = (
        "너는 법률 규칙 컴파일러다. 질문은 쟁점 식별에만 쓰고 사실관계의 결론을 내리지 않는다. "
        "제시된 조문에서 지배규범, actor, 요건, 예외, 법률효과를 분리한다. 다른 actor·시장·시점·낮은 권위의 자료는 지배규범과 구분한다."
    )
    rule_call = call_structured(llm, f"adr48.{case}.rule_compile", rule_system, full_no_wiki, RULE_SCHEMA, model=HAIKU_MODEL)
    fact_system = (
        "너는 사실 추출기다. 법률지식을 사용하거나 결론을 내리지 말고 질문에 명시된 actor, 행위, 시점, 금액, 조건과 빠진 사실만 구조화한다."
    )
    fact_call = call_structured(llm, f"adr48.{case}.fact_extract", fact_system, question_part, FACT_SCHEMA, model=HAIKU_MODEL)
    split_system = full["request"]["system"] + (
        "\n⑦ 아래 [규칙 컴파일]과 [사실 추출]을 먼저 대조한다. actor·조건·예외별로 사실을 포섭하고, "
        "빠진 사실을 임의로 true/false로 만들지 않는다. 원 조문과 중간 JSON이 충돌하면 원 조문이 우선한다."
    )
    subsumption_user = full["request"]["user"] + "\n\n[규칙 컴파일]\n" + json.dumps(rule_call["output"], ensure_ascii=False, indent=2) + "\n\n[사실 추출]\n" + json.dumps(fact_call["output"], ensure_ascii=False, indent=2)
    final_call = call_structured(llm, f"adr48.{case}.rule_fact_answer", split_system, subsumption_user, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["rule-fact-split"] = {**final_call, "source": "generated", "evidence": full["evidence"], "intermediate_calls": [rule_call, fact_call], "generation_calls": 3}

    arms["wiki-none"] = call_structured(llm, f"adr48.{case}.wiki_none", full["request"]["system"], full_no_wiki, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["wiki-none"].update({"source": "generated", "evidence": full["evidence"], "generation_calls": 1})
    placebo_user = full_no_wiki + placebo_wiki
    arms["wiki-placebo"] = call_structured(llm, f"adr48.{case}.wiki_placebo", full["request"]["system"], placebo_user, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["wiki-placebo"].update({"source": "generated", "evidence": full["evidence"], "placebo_from_next_case": True, "generation_calls": 1})

    labeled_system = hard["request"]["system"] + "\n⑦ [권위·적용범위 감사표]는 사후 분류이며 원문을 대체하지 않는다. 지배규범 선택 때만 검증표로 사용한다."
    labeled_user = hard["request"]["user"] + "\n\n" + authority_labels(row)
    arms["authority-labeled"] = call_structured(llm, f"adr48.{case}.authority_labeled", labeled_system, labeled_user, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["authority-labeled"].update({"source": "generated", "evidence": hard["evidence"], "generation_calls": 1})

    selective_system = full["request"]["system"] + (
        "\n⑦ 결론 전 필수 actor·조건·예외·시점·수치를 내부적으로 true/false/unknown으로 점검한다. "
        "질문 결론에 필요한 항목이 unknown이면 추측하지 말고 answerable=false로 두며, 무엇이 부족한지만 답한다. "
        "근거가 충분하면 평소처럼 결론을 답한다."
    )
    arms["selective-unknown"] = call_structured(llm, f"adr48.{case}.selective_unknown", selective_system, full["request"]["user"], ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["selective-unknown"].update({"source": "generated", "evidence": full["evidence"], "generation_calls": 1})

    trace_system = full["request"]["system"] + "\n⑦ [검색·선별 과정]은 근거가 아닌 provenance다. unknown 탈락 사유를 추정하지 않는다."
    trace_user = full["request"]["user"] + "\n\n" + audit_trace(row)
    arms["retrieval-trace"] = call_structured(llm, f"adr48.{case}.retrieval_trace", trace_system, trace_user, ANSWER_SCHEMA, model=HAIKU_MODEL)
    arms["retrieval-trace"].update({"source": "generated", "evidence": full["evidence"], "trace_status": "mixed: presented exact; audit reasons reconstructed", "generation_calls": 1})
    return {"case_no": case, "question": row["question"], "reference_answer": row["reference_answer"], "arms": arms}


def generate(workers: int) -> None:
    if not FROZEN.exists():
        raise RuntimeError("run prepare first")
    rows = json.loads(FROZEN.read_text("utf-8"))["cases"]
    wikis = [split_user(row["variants"]["full_original"]["request"]["user"])[2] for row in rows]
    local = threading.local()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(generate_case, row, wikis[(i + 1) % len(rows)], local): row for i, row in enumerate(rows)}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            source = jobs[future]
            try:
                result = future.result()
                print(f"[{i}/{len(rows)}] {result['case_no']} generated", flush=True)
            except Exception as exc:
                result = {"case_no": source["case_no"], "question": source["question"], "reference_answer": source["reference_answer"], "error": f"{type(exc).__name__}: {exc}"}
                print(f"[{i}/{len(rows)}] {source['case_no']} ERROR {exc}", flush=True)
            results.append(result)
            results.sort(key=lambda value: value["case_no"])
            GENERATED.write_text(json.dumps({"schema_version": "legal-reasoning-product-results-v1", "rows": results}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if any(row.get("error") for row in results):
        raise RuntimeError("product generation has errors")
    print(f"wrote {GENERATED} sha256={sha(GENERATED)}")


def refresh_control_case(row: dict[str, Any], source_row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    """Regenerate every formerly stored control in the same execution window."""
    if not hasattr(local, "llm"):
        local.llm = LLM(model=HAIKU_MODEL)
    llm: LLM = local.llm
    case = str(row["case_no"])
    refreshed = copy.deepcopy(row)
    unique = {
        "baseline-full": "full_original",
        "ladder-gold": "gold_only",
        "ladder-gold-supportive": "supportive_after",
        "authority-unlabeled": "hard_after",
    }
    for arm, variant in unique.items():
        source = source_row["variants"][variant]
        request = source["request"]
        call = call_structured(
            llm, f"adr48.{case}.{arm}.contemporaneous", request["system"],
            request["user"], request.get("schema") or ANSWER_SCHEMA, model=HAIKU_MODEL)
        call.update({"source": "generated-contemporaneous-control", "source_variant": variant,
                     "evidence": source.get("evidence", []), "generation_calls": 1})
        refreshed["arms"][arm] = call
    # wiki-related is definitionally the same input as baseline-full.  Alias the
    # exact call instead of paying for a second stochastic duplicate.
    refreshed["arms"]["wiki-related"] = copy.deepcopy(refreshed["arms"]["baseline-full"])
    refreshed["arms"]["wiki-related"]["aliased_to"] = "baseline-full"
    return refreshed


def refresh_controls(workers: int) -> None:
    if not JUDGED.exists():
        raise RuntimeError("run the mixed replay judge before refresh-controls")
    MIXED_RUN.write_bytes(JUDGED.read_bytes())
    prior = json.loads(JUDGED.read_text("utf-8"))["rows"]
    sources = {str(row["case_no"]): row for row in json.loads(FROZEN.read_text("utf-8"))["cases"]}
    local = threading.local()
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(refresh_control_case, row, sources[row["case_no"]], local): row for row in prior}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = jobs[future]
            result = future.result()
            print(f"[{i}/{len(prior)}] {item['case_no']} controls refreshed", flush=True)
            rows.append(result)
    rows.sort(key=lambda value: value["case_no"])
    GENERATED.write_text(json.dumps({
        "schema_version": "legal-reasoning-product-results-v2",
        "run_id": "run-003", "rows": rows,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    run2 = next(run for run in manifest["runs"] if run["id"] == "run-002")
    run2.update({
        "status": "invalid", "artifact_path": str(MIXED_RUN.relative_to(ROOT)),
        "sha256": sha(MIXED_RUN),
        "selection_rule": "저장 control과 신규 candidate의 생성 시점이 달라 Haiku 변동이 섞인 비교; 원시 결과 보존",
    })
    if not any(run.get("id") == "run-003" for run in manifest["runs"]):
        manifest["runs"].append({
            "id": "run-003", "purpose": "repeat", "parent_run_id": "run-002",
            "arm_ids": list(ARMS),
            "selection_rule": "동결 8건; stored control 4종을 동일 실행창에서 Haiku 재생성, wiki-related는 baseline exact alias",
            "status": "planned", "artifact_path": str(JUDGED.relative_to(ROOT)), "sha256": "PENDING",
        })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"wrote contemporaneous controls {GENERATED}")


def judge_user(row: dict[str, Any], arm: str) -> str:
    answer = str(row["arms"][arm]["output"].get("answer", ""))
    answerable = row["arms"][arm]["output"].get("answerable")
    return (
        f"[질문]\n{row['question']}\n\n[기준답변]\n{row['reference_answer']}\n\n"
        f"[시스템 답변]\nanswerable={answerable}\n{answer}\n\n"
        "기준답변과 시스템 답변의 표현 유사성이 아니라 법률 명제의 동일성을 판정한다. "
        "answerable=false도 질문에 답할 충분한 근거가 있었는데 유보했다면 correct=false다."
    )


def judge_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"):
        local.llm = LLM(model=OPUS_MODEL)
    llm: LLM = local.llm
    judged = copy.deepcopy(row)
    for arm in ARMS:
        if isinstance(judged["arms"][arm].get("judge"), dict):
            continue
        if arm == "wiki-related" and judged["arms"][arm].get("aliased_to") == "baseline-full":
            judged["arms"][arm]["judge"] = copy.deepcopy(judged["arms"]["baseline-full"]["judge"])
            judged["arms"][arm]["judge"]["aliased_to"] = "baseline-full"
            continue
        call = call_structured(llm, f"adr48.{row['case_no']}.{arm}.judge", JUDGE_SYSTEM, judge_user(row, arm), JUDGE_SCHEMA, model=OPUS_MODEL)
        judged["arms"][arm]["judge"] = call
    return judged


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(round((len(values) - 1) * q), len(values) - 1)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        values = [row["arms"][arm] for row in rows]
        correct = [bool(value["judge"]["output"].get("correct")) for value in values]
        answerable = [bool(value["output"].get("answerable")) for value in values]
        product_ex = [ex for value in values for ex in value.get("exchanges", [])]
        for value in values:
            for call in value.get("intermediate_calls", []):
                product_ex.extend(call.get("exchanges", []))
        judge_ex = [ex for value in values for ex in value["judge"].get("exchanges", [])]
        durations = [int(ex.get("dur_ms") or 0) for ex in product_ex]
        by_arm[arm] = {
            "correct": sum(correct), "total": len(correct),
            "answerable": sum(answerable), "abstained": len(answerable) - sum(answerable),
            "selective_correct_answered": sum(c and a for c, a in zip(correct, answerable)),
            "presented_total": sum(len(value.get("evidence", [])) for value in values),
            "presented_mean": round(statistics.mean(len(value.get("evidence", [])) for value in values), 3),
            "selectivity": round(statistics.mean(len(value.get("evidence", [])) for value in values) / CORPUS_ARTICLES, 8),
            "run_product_calls": sum(int(value.get("generation_calls", 0)) for value in values),
            "recorded_product_exchanges": len(product_ex),
            "product_input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in product_ex),
            "product_output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in product_ex),
            "product_p50_ms": percentile(durations, .5), "product_p95_ms": percentile(durations, .95),
            "judge_calls": len(judge_ex),
        }
    baseline = [bool(row["arms"]["baseline-full"]["judge"]["output"].get("correct")) for row in rows]
    pairs = {}
    for arm in ARMS[1:]:
        candidate = [bool(row["arms"][arm]["judge"]["output"].get("correct")) for row in rows]
        pairs[arm] = {
            "new_correct": sum(c and not b for b, c in zip(baseline, candidate)),
            "regression": sum(b and not c for b, c in zip(baseline, candidate)),
            "both_correct": sum(b and c for b, c in zip(baseline, candidate)),
            "both_wrong": sum(not b and not c for b, c in zip(baseline, candidate)),
        }
    return {"cases": len(rows), "by_arm": by_arm, "paired_vs_baseline": pairs}


def judge(workers: int) -> None:
    if not GENERATED.exists():
        raise RuntimeError("run generate first")
    source = json.loads(GENERATED.read_text("utf-8"))["rows"]
    local = threading.local()
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_case, row, local): row for row in source}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = jobs[future]
            try:
                row = future.result()
                score = sum(bool(row["arms"][arm]["judge"]["output"].get("correct")) for arm in ARMS)
                print(f"[{i}/{len(source)}] {row['case_no']} judged {score}/{len(ARMS)}", flush=True)
            except Exception as exc:
                row = {"case_no": item["case_no"], "error": f"{type(exc).__name__}: {exc}"}
                print(f"[{i}/{len(source)}] {item['case_no']} ERROR {exc}", flush=True)
            rows.append(row)
            rows.sort(key=lambda value: value["case_no"])
            JUDGED.write_text(json.dumps({"schema_version": "legal-reasoning-judged-v1", "summary": summarize([x for x in rows if not x.get('error')]), "rows": rows}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if any(row.get("error") for row in rows):
        raise RuntimeError("judge has errors")
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    arm_blocks = []
    mid = []
    judge_blocks = []
    decisions = []
    for arm in ARMS:
        value = row["arms"][arm]
        req = value.get("request", {})
        arm_blocks.append(
            f"### run-003 / {arm} / system\n\n```text\n{req.get('system', '')}\n```\n\n"
            f"### run-003 / {arm} / user\n\n```text\n{req.get('user', '')}\n```\n\n"
            f"### run-003 / {arm} / schema·tool\n\n```json\n{json.dumps(req.get('schema'), ensure_ascii=False, indent=2)}\n```\n\n"
            f"### run-003 / {arm} / provider 원응답·structured output·usage·지연\n\n```json\n"
            f"{json.dumps({'source': value.get('source'), 'source_variant': value.get('source_variant'), 'output': value.get('output'), 'exchanges': value.get('exchanges', [])}, ensure_ascii=False, indent=2)}\n```"
        )
        mid.extend({"arm": arm, **call} for call in value.get("intermediate_calls", []))
        judge_blocks.append({"arm": arm, **value["judge"]})
        grade = value["judge"]["output"]
        failure = "-" if grade.get("correct") else "legal_reasoning_or_context"
        decisions.append(f"| run-003 | {arm} | {grade.get('correct')} | {grade.get('reason', '')} | {failure} |")
    exact = {arm: [{k: ev.get(k) for k in ("id", "doc_id", "node", "document", "path", "role", "relation_reason", "original_text")} for ev in row["arms"][arm].get("evidence", [])] for arm in ARMS}
    return f"""# 질문 {number:03d} — {row['case_no']}

## 1. 실행 메타

- ADR: `ADR-0048`
- experiment: `ADR-0048-legal-reasoning-causal-v1`
- case ID: `{row['case_no']}`
- run ID: `run-003`
- 원본 상태: 저장 arm은 `exact`, 새 trace의 제시 여부는 `exact`, 탈락 사유는 `reconstructed`
- 제품·중간 호출 모델: `{HAIKU_MODEL}`
- 오프라인 평가 모델: `{OPUS_MODEL}`
- 실행 arm: {', '.join(f'`{arm}`' for arm in ARMS)}

## 2. 사용자 질문 원문

```text
{row['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{row['reference_answer']}
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps({'corpus_total_article_roots': CORPUS_ARTICLES, 'presented_by_arm': {arm: len(row['arms'][arm].get('evidence', [])) for arm in ARMS}, 'dropped_reason_status': '원 selector 전수 로그 없음; 일부 synthetic audit 후보의 사후 Haiku 분류만 존재'}, ensure_ascii=False, indent=2)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

```json
{json.dumps(exact, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

{chr(10).join(arm_blocks)}

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
{json.dumps(mid, ensure_ascii=False, indent=2)}
```

## 7. 채점 호출과 반복 판정

### judge system/user — 기준답변 포함

```json
{json.dumps([{'arm': arm, 'system': row['arms'][arm]['judge']['request']['system'], 'user': row['arms'][arm]['judge']['request']['user'], 'schema': JUDGE_SCHEMA} for arm in ARMS], ensure_ascii=False, indent=2)}
```

### judge 원응답과 최종 다수결

```json
{json.dumps(judge_blocks, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{chr(10).join(decisions)}

- 사전 지정 비교쌍의 신규 정답·회귀: 집계 manifest 참조
- 공통 실패 유형: `governing_rule_selection`, `scope_actor_mismatch`, `condition_exception`, `numeric_temporal`, `authority_or_version`, `definition_resolution`, `unsupported_inference` 중 judge reason에 따라 사람 재검토 필요
- 사람이 확인한 직접 원인: 없음 — 모델 판정 기반 probe
- 다음 분기에서 검증할 가설: holdout과 최소대조쌍에서 arm별 인과효과 재검증
"""


def finalize() -> None:
    blob = json.loads(JUDGED.read_text("utf-8"))
    rows = blob["rows"]
    summary = summarize(rows)
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    qmap = {row["case_id"]: row for row in manifest["questions"]}
    for number, row in enumerate(rows, 1):
        target = ADR / "실험" / qmap[row["case_no"]]["file"]
        target.write_text(question_md(row, number), "utf-8")
        qmap[row["case_no"]]["sha256"] = sha(target)
    active_run = next(run for run in manifest["runs"] if run["id"] == "run-003")
    active_run.update({"status": "complete", "sha256": sha(JUDGED)})
    manifest["results"] = {
        "status": "complete", "by_arm": summary["by_arm"],
        "comparisons": summary["paired_vs_baseline"], "judge_disagreements": None,
        "usage": {arm: {k: v for k, v in values.items() if "tokens" in k or "calls" in k or "exchanges" in k} for arm, values in summary["by_arm"].items()},
        "latency": {arm: {"p50_ms": values["product_p50_ms"], "p95_ms": values["product_p95_ms"]} for arm, values in summary["by_arm"].items()},
        "error_taxonomy": ["governing_rule_selection", "scope_actor_mismatch", "condition_exception", "numeric_temporal", "authority_or_version", "definition_resolution", "unsupported_inference", "judge_or_gold_error"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows, summary)
    write_artifact_manifest()
    print(f"finalized {ADR}")


def write_docs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    by = summary["by_arm"]
    pairs = summary["paired_vs_baseline"]
    result_rows = "\n".join(
        f"| `{arm}` | {by[arm]['correct']}/8 | {by[arm]['correct']/8:.1%} | "
        f"{by[arm]['correct']-by['baseline-full']['correct']:+d} | {by[arm]['product_input_tokens']} | "
        f"{by[arm]['product_p50_ms']}/{by[arm]['product_p95_ms']} ms |" for arm in ARMS)
    case_family = {
        "cm-003": "제3호 단서→제4호 예외 포섭",
        "cm-012": "규정과 실무 체크리스트 권위 구분",
        "cm-024": "산식·수치",
        "cm-030": "정의조의 적용대상→첨부의무 연결",
        "cm-036": "상근이사와 등기이사 개념 동일성",
        "cm-041": "단일 조문 내 자본금 예외",
        "cm-044": "법령·골든 시점 drift",
        "cm-051": "준용조문과 조합 특례 누락",
    }
    case_rows = []
    for row in rows:
        winners = [arm for arm in ARMS if row["arms"][arm]["judge"]["output"].get("correct")]
        case_rows.append(
            f"| `{row['case_no']}` | {case_family[row['case_no']]} | "
            f"{len(winners)}/{len(ARMS)} | {', '.join(f'`{arm}`' for arm in winners) or '없음'} |"
        )
    readme = f"""---
adr_id: ADR-0048
title: 법률 추론 원인분리 포트폴리오
status: Proposed
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0048: 법률 추론 원인분리 포트폴리오

## 1. 결정 요약

동결 오답군 8건에서 12개 arm을 비교했다. `gold-only`만 사전 성공선인 baseline 대비
신규정답 2·회귀 0을 충족했지만, 이미 같은 51건을 본 인샘플이고 보조 조문이 필요한
`cm-031` 반례가 있어 메인 배선은 변경하지 않는다. 검색 trace·권위 표지·정의 카드는
개선이 없었고, 규칙/사실 분리와 선택적 유보는 각각 +2/−1로 회귀했다.

## 2. 문제와 변경 전 구조

전체 51건 회수 recall은 높지만 최종 의미 정답은 변동했다. 같은 조문을 보고도 지배규범, actor, 조건·예외, 권위와 Wiki 잡음을 잘못 처리하는지 분리할 필요가 있다.

## 3. 가설과 사전 판정 기준

### 가설

오답은 단일 회수 실패보다 복수 원인이며, 근거 사다리·규칙/사실 분리·Wiki placebo·권위 표지·유보·검색 trace가 서로 다른 오류군에 선택적으로 작동한다.

### 성공 기준

후보 arm은 baseline 대비 신규정답 2건 이상·회귀 0건이거나 사전 예상한 진단 단조성을 보여야 한다. 모든 생성은 Haiku, 채점만 격리된 Opus 단일 호출이다.

### 반증 기준

신규정답 1건 이하, 회귀 발생, placebo가 관련 Wiki 이상, 또는 trace가 사후 분류를 법적 근거로 오인하면 일반 후보로 채택하지 않는다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline-full | 저장 full context | 질문·골든·모델 | 기준 |
| ladder 3종 | gold / gold+정의 / gold+supportive | 답변 prompt | 잡음·정의·closure 분리 |
| rule-fact-split | 규칙·사실 별도 컴파일 | 최종 원문 포함 | 포섭 결합 부담 측정 |
| Wiki A/B/C | 없음/원본/placebo | full 조문 | 법률지식 vs 토큰 효과 |
| authority A/B | hard bundle 표지 없음/있음 | 같은 bundle | 권위·범위 충돌 |
| selective-unknown | 필수조건 unknown 유보 | full 조문 | 선택적 신뢰도 |
| retrieval-trace | exact 제시+reconstructed 감사 사유 | full 조문 | 검색 provenance 효과 |

## 5. 데이터·모델·재현성

- ADR-0039 wrong16에서 오류군별 8건을 결과 확인 전에 동결했다.
- 제품·중간: `{HAIKU_MODEL}`; 오프라인 judge: `{OPUS_MODEL}`.
- 기준답변은 judge에만 제공했다. 법령·골든 현행성은 별도 재검증하지 않았다.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
{result_rows}

paired 신규정답·회귀는 [manifest](실험/manifest.json)에 전수 기록했다.

- 근거 사다리: full `2/8` → gold `4/8` → gold+정의 `2/8` → gold+supportive `3/8`.
  단조적이지 않다. 잡음 제거 이득은 있으나 정의·보조자료를 단순 추가하면 다시 악화됐다.
- 규칙·사실 분리: `3/8`, baseline 대비 신규정답 2·회귀 1. 호출은 사례당 3회다.
- Wiki: 원본 `2/8`, 제거 `1/8`, 다른 사건 placebo `1/8`. 1건 차이여서 법률지식 효과를 입증하지 못했다.
- 권위 표지: 표지 없음 `2/8`, 표지 있음 `2/8`. 정답 집합도 동일했다.
- 선택적 유보: `3/8`, 신규정답 2·회귀 1, coverage 5/8. 안전한 전역 guard가 아니다.
- 검색 trace: `2/8`, baseline과 정답 집합 동일. 입력 토큰만 약 7.1% 늘었다.

## 7. 사례별 오류 분석

| 사례 | 주된 법률 난점 | 정답 arm/12 | 정답 arm |
|---|---|---:|---|
{chr(10).join(case_rows)}

`cm-030`은 12개 arm 전부가 적용대상 한정을 결론으로 연결하지 못했다. `cm-044`도 전부
실패했지만 여러 judge가 2025년 개정에 따른 골든 drift 가능성을 표시했으므로 제품 오류와
골든 오류를 분리해야 한다. 질문별 실제 system/user/schema/provider 원응답과 judge 이유는
[실험 인덱스](실험/README.md)에 있다. 사람 확정 직접원인은 아직 없으므로 judge reason을
사실로 승격하지 않는다.

## 8. 비용·지연·회수 규모

- 조문 root 전체: {CORPUS_ARTICLES:,}개.
- baseline 제시: {by['baseline-full']['presented_total']}개/8건, 평균 {by['baseline-full']['presented_mean']}개, 평균 선택률 {by['baseline-full']['selectivity']:.4%}.
- arm별 제시량·토큰·호출·지연은 manifest에 있다.
- 원 selector의 전수 탈락 사유는 보존되지 않았다. trace는 제시 여부 exact, 사후 위험 분류 reconstructed다.

## 9. 해석

가장 강한 신호는 **잡음이 일부 사례를 망친다**는 것이다. 그러나 gold-only가 항상 안전한
것은 아니다. 정의 카드는 `cm-003`의 관련 정의를 넣고도 예외 포섭을 못 고쳤고,
`cm-051`은 오히려 제4항 보조 특례가 있을 때만 맞았다. 따라서 필요한 것은 전역 삭제가
아니라, 지배규범에 연결된 정의·예외·준용 목적지만 남기는 법적 closure 선택이다.

Wiki 원본이 제거/placebo보다 1건 높지만 8건 단회로는 지식 효과를 입증하지 못한다.
검색 trace는 효과가 없었다. 특히 trace의 탈락 사유가 사후 Haiku 분류이므로, 실제 selector
설명을 제공한 실험으로 해석하면 안 된다. 권위 관계도 텍스트 표지만으로는 Haiku의 결론을
바꾸지 못했다.

## 10. 한계와 일반화 가능 범위

동일 오답군을 반복 관찰한 8건 인샘플 probe다. Opus judge도 사람 라벨이 아니며 `cm-044` 같은 골든 version drift 가능성이 있다. holdout 전 운영 근거가 아니다.

## 11. 운영 결정·롤백 조건

메인 배선은 유지한다. `gold-only`는 holdout 비교 기준으로만 올리고 전역 배선 후보로 삼지
않는다. 다음 분기는 `cm-030`, `cm-003`, `cm-051`의 조건 하나만 바꾼 최소대조쌍으로,
법적 closure가 결론을 올바르게 뒤집는지 검증한다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py prepare
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py generate --workers 2
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py judge --workers 1
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py refresh-controls --workers 2
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py judge --workers 1
.venv/bin/python scripts/rag_legal_reasoning_portfolio.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0048-legal-reasoning-causal-portfolio --final
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
"""
    (ADR / "README.md").write_text(readme, "utf-8")
    lines = ["# ADR-0048 실험 질문 인덱스", "", "| 번호 | case | baseline | 최고 arm 정답 수 | 파일 |", "|---:|---|---:|---:|---|"]
    manifest = json.loads((ADR / "실험/manifest.json").read_text("utf-8"))
    files = {q["case_id"]: q["file"] for q in manifest["questions"]}
    for i, row in enumerate(rows, 1):
        base = row["arms"]["baseline-full"]["judge"]["output"]["correct"]
        score = sum(bool(row["arms"][arm]["judge"]["output"]["correct"]) for arm in ARMS)
        lines.append(f"| {i:03d} | `{row['case_no']}` | {base} | {score}/{len(ARMS)} | [{files[row['case_no']]}]({files[row['case_no']]}) |")
    lines.extend(["", "- 각 질문 파일은 모든 arm의 원문 입력·출력과 Opus 판정을 생략 없이 보존한다.", "- phase=probe, in_sample=true, decision_eligible=false."])
    (ADR / "실험/README.md").write_text("\n".join(lines) + "\n", "utf-8")


def write_artifact_manifest() -> None:
    files = []
    for path, role in ((FROZEN, "frozen dataset"), (PREFLIGHT, "invalid run-001"),
                       (MIXED_RUN, "invalid run-002"), (GENERATED, "product outputs"),
                       (JUDGED, "judged outputs"), (Path(__file__), "runner")):
        files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size, "role": role})
    (ADR / "artifacts/manifest.json").write_text(json.dumps({"schema_version": "adr-artifacts-v1", "adr_id": "ADR-0048", "files": files}, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    gen = sub.add_parser("generate")
    gen.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    grd = sub.add_parser("judge")
    grd.add_argument("--workers", type=int, choices=range(1, 3), default=1)
    refresh = sub.add_parser("refresh-controls")
    refresh.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "generate":
        generate(args.workers)
    elif args.command == "judge":
        judge(args.workers)
    elif args.command == "refresh-controls":
        refresh_controls(args.workers)
    else:
        finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
