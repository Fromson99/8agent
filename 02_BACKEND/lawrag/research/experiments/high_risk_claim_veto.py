"""Haiku 답변의 고위험 법률 명제만 원문과 대조하는 shadow veto.

답변을 다시 쓰지 않는다. 수치·기간·양태·예외·기관 권한·시점 명제가 회수 원문과
명백히 반대일 때만 veto하고, 근거가 부족하거나 해석이 필요한 경우 uncertain으로
남긴다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lawrag.research.experiments.haiku_legal_compiler import build_clause_cards
from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL


_HIGH_RISK = re.compile(
    r"\d|100분의|개월|일 이내|년 이내|하여야|해야|할 수 있|할 수 없|"
    r"적용하지|제외|예외|다만|주주총회|이사회|감사위원회|감사|부터|까지"
)


VETO_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "claim_type": {"type": "string", "enum": [
                    "numeric_condition", "temporal", "modality", "exception",
                    "institutional_authority", "scope", "other_high_risk"]},
                "answer_quote": {"type": "string"},
                "normalized_claim": {"type": "string"},
                "source_status": {"type": "string", "enum": [
                    "supports", "contradicts", "insufficient"]},
                "source_quote_ids": {
                    "type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
            "required": ["claim_id", "claim_type", "answer_quote",
                         "normalized_claim", "source_status",
                         "source_quote_ids", "reason"],
            "additionalProperties": False,
        }},
        "decision": {"type": "string", "enum": ["pass", "veto", "uncertain"]},
        "decision_reason": {"type": "string"},
    },
    "required": ["claims", "decision", "decision_reason"],
    "additionalProperties": False,
}


VETO_SYSTEM = """너는 한국 법률 답변의 고위험 명제 감사관이다. 답변을 고치거나 더
좋은 해석을 제안하지 말고, 답변에 실제로 쓰인 다음 명제만 회수 원문과 대조한다.

- 조건에 묶인 수치·비율·기간·기한
- 의무/재량/금지의 양태
- 본문·단서·예외·적용 제외
- 주주총회·이사회·감사·감사위원회 등 기관 권한
- 적용 시장·문서·주체·대상·시점

판정 규칙:
1. answer_quote는 답변의 정확한 연속 문자열이어야 한다.
2. source_quote_ids의 원문이 같은 주체·행위·대상·조건에서 답변과 명백히 반대일
   때만 contradicts다. 원문 누락, 일반 법률지식, 더 나은 해석, 설명 부족은
   contradicts가 아니라 insufficient다.
3. 수치만 같고 조건이 다르거나, 조건은 같지만 수치가 뒤바뀌면 contradicts다.
4. '하여야 한다'를 '할 수 있다'로, 명시적 예외를 일반 원칙으로 바꾼 경우도
   contradicts다.
5. 회수 원문이 해석상 불명확하거나 서로 충돌하면 insufficient로 둔다.
6. 하나라도 직접 모순이면 veto, 직접 모순은 없지만 중요한 명제가 insufficient면
   uncertain, 나머지는 pass다. 누락만으로 veto하지 않는다.
7. clause cards 밖의 지식을 사용하지 않는다."""


def validate_veto(raw: dict[str, Any] | None, answer: str,
                  cards: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["veto_failed"]}
    quote_ids = {str(row.get("quote_id") or "") for row in cards}
    contradictions = 0
    insufficient = 0
    seen = set()
    for claim in raw.get("claims") or []:
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id or claim_id in seen:
            errors.append("invalid_or_duplicate_claim_id")
        seen.add(claim_id)
        answer_quote = str(claim.get("answer_quote") or "")
        if not answer_quote or answer_quote not in answer:
            errors.append(f"{claim_id}:answer_quote_not_found")
        sources = [str(value) for value in claim.get("source_quote_ids") or []]
        if any(value not in quote_ids for value in sources):
            errors.append(f"{claim_id}:invalid_source_quote")
        status = str(claim.get("source_status") or "")
        if status == "contradicts":
            contradictions += 1
            if not sources:
                errors.append(f"{claim_id}:contradiction_without_source")
        elif status == "insufficient":
            insufficient += 1
    decision = str(raw.get("decision") or "")
    expected = "veto" if contradictions else "uncertain" if insufficient else "pass"
    if decision != expected:
        errors.append(f"decision_mismatch:{decision}!={expected}")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)),
            "contradictions": contradictions, "insufficient": insufficient,
            "expected_decision": expected}


def audit_answer(llm, question: str, answer: str,
                 evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not _HIGH_RISK.search(answer):
        return {"decision": "pass", "guard": "no_high_risk_surface",
                "claims": [], "cards": [],
                "validation": {"valid": True, "errors": []}}
    cards = build_clause_cards(question, evidence, max_cards=56, max_per_evidence=7)
    user = (f"[질문]\n{question}\n\n[감사할 답변]\n{answer}\n\n"
            f"[clause cards]\n{json.dumps(cards, ensure_ascii=False)}")
    raw = llm.structured(
        "rag.answer.haiku.high_risk_claim_veto.experimental",
        VETO_SYSTEM, user, VETO_SCHEMA, max_tokens=4000,
        effort="low", model=HAIKU_MODEL)
    validation = validate_veto(raw, answer, cards)
    if not validation["valid"]:
        decision = "uncertain"
        guard = "invalid_veto_audit"
    else:
        decision = str(raw.get("decision") or "uncertain")
        guard = "validated_veto_audit"
    return {"decision": decision, "guard": guard,
            "claims": list((raw or {}).get("claims") or []),
            "raw": raw, "cards": cards, "validation": validation}
