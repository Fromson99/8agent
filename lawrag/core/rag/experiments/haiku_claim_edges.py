"""원문 clause card를 닫힌 후보로 판정하는 Haiku claim-edge shadow compiler."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_compiler import build_clause_cards
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL, evidence_payload


CLAIM_KINDS = (
    "DUTY", "PROHIBITION", "PERMISSION", "DEEMING", "DEFINITION",
    "CONDITION", "EFFECT", "PROCEDURE", "OTHER",
)
MODALITIES = ("MUST", "MUST_NOT", "MAY", "DEEMED", "CONDITIONAL", "NEUTRAL")
MATRIX_SLOTS = (
    "CONCLUSION", "CONDITION", "EXCEPTION", "QUANTITY", "TEMPORAL", "AUTHORITY",
)
MAX_CARDS = 36
CARDS_PER_CALL = 12


CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["CLAIM", "NONE"]},
                "claim_kind": {"type": "string", "enum": list(CLAIM_KINDS)},
                "actor": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "modality": {"type": "string", "enum": list(MODALITIES)},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "exceptions": {"type": "array", "items": {"type": "string"}},
                "quantities": {"type": "array", "items": {"type": "string"}},
                "temporals": {"type": "array", "items": {"type": "string"}},
                "effect": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": [
                "card_id", "verdict", "claim_kind", "actor", "predicate", "object",
                "modality", "conditions", "exceptions", "quantities", "temporals",
                "effect", "confidence",
            ],
            "additionalProperties": False,
        }},
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


CLAIM_SYSTEM = """너는 닫힌 한국 법률 원문 card를 구조화한다. 질문에 답하지 않는다.
각 card_id를 정확히 한 번 CLAIM 또는 NONE으로 판정한다.

CLAIM은 원문 자체가 주체의 의무·금지·허용·간주·정의·요건·절차·법적 효과 중 하나를
규정할 때만 선택한다. 표제, 연혁, 단순 인용 목록, 불완전한 문장만 있으면 NONE이다.
모든 문자열 슬롯은 해당 card의 text에 실제로 연속하여 존재하는 가장 짧은 원문을
그대로 복사한다. 추론·바꿔쓰기·외부지식은 금지한다. 해당 슬롯이 없으면 빈 문자열
또는 빈 배열로 둔다. CLAIM이면 predicate와 confidence=high가 필수다.

modality:
- MUST: 하여야 한다/의무
- MUST_NOT: 금지/할 수 없다/적용하지 않는다
- MAY: 할 수 있다/재량
- DEEMED: 본다/간주한다
- CONDITIONAL: 요건·경우·전제만 규정
- NEUTRAL: 정의·절차·효과이나 위 양태가 없음"""


ALIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "requested_slots": {"type": "array", "items": {
            "type": "string", "enum": list(MATRIX_SLOTS)}},
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["RELEVANT", "IRRELEVANT"]},
                "slots": {"type": "array", "items": {
                    "type": "string", "enum": list(MATRIX_SLOTS)}},
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["claim_id", "verdict", "slots", "reason", "confidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["requested_slots", "decisions"],
    "additionalProperties": False,
}


ALIGN_SYSTEM = """너는 질문과 원문 claim의 적용 관련성만 판정한다.
각 claim_id를 정확히 한 번 RELEVANT 또는 IRRELEVANT로 판정한다.
문서·시장·주체·행위·대상·시점이 질문과 맞고 요청 결론의 직접 요건, 예외, 수치,
기간, 권한 또는 효과를 제공할 때만 RELEVANT다. 단어 하나만 겹치거나 주변 배경이면
IRRELEVANT다. 원문 claim을 확장하거나 질문의 사실을 새로 만들지 않는다.
질문이 요구하는 requested_slots도 표시한다."""


RENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"type": "string"},
        "used_claim_ids": {"type": "array", "items": {"type": "string"}},
        "uncovered_slots": {"type": "array", "items": {
            "type": "string", "enum": list(MATRIX_SLOTS)}},
    },
    "required": ["answerable", "answer", "used_claim_ids", "uncovered_slots"],
    "additionalProperties": False,
}


RENDER_SYSTEM = """너는 전체 법률 원문과 검증된 entailment matrix로 답한다.
질문에 결론부터 답하고 필요한 조건·예외·수치·기간·기관권한을 정확히 붙인다.
matrix는 관련 원문을 찾는 색인이지 새로운 법규가 아니다. 최종 답은 반드시 제공된
전체 evidence 원문과 일치해야 한다. MUST/MUST_NOT/MAY, 이상/초과/이하/미만,
각각/합산, 본문/단서/예외를 바꾸지 않는다. requested slot이 원문에 없으면 추측하지
말고 uncovered_slots에 남긴다. 내부 claim_id는 답변 문장에 쓰지 않는다."""


CLOSED_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["NORMATIVE", "NONE"]},
                "claim_kind": {"type": "string", "enum": list(CLAIM_KINDS)},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["card_id", "verdict", "claim_kind", "confidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


CLOSED_LINE_SYSTEM = """너는 닫힌 법률 원문 line 후보의 역할만 판정한다.
각 card_id를 정확히 한 번 NORMATIVE 또는 NONE으로 판정한다.
NORMATIVE는 해당 line 자체가 의무·금지·허용·간주·정의·요건·예외·절차·법적효과를
완결적으로 규정할 때만 선택한다. 표제, 연혁, 단순 조문 인용, 문장이 중간에서 끊긴
경우는 NONE이다. 원문 span을 다시 만들거나 바꿔 쓰지 않는다. NORMATIVE는
confidence=high일 때만 허용한다."""


_DET_VALUE = re.compile(
    r"(?:100\s*분의\s*\d+(?:\.\d+)?|\d+(?:,\d{3})*(?:\.\d+)?\s*"
    r"(?:%|퍼센트|조원|억원|만원|원|개월|시간|년|일|명|인|회|주|배))"
    r"\s*(?:이상|이하|초과|미만)?"
)
_DET_TEMPORAL = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:년|개월|일|시간)\s*(?:이상|이하|초과|미만|이내)?|"
    r"(?:19|20)\d{2}\s*년(?:\s*\d{1,2}\s*월)?(?:\s*\d{1,2}\s*일)?)"
)


def deterministic_modality(text: str) -> str:
    if re.search(r"할\s*수\s*없|하여서는\s*아니|금지|적용하지\s*아니", text):
        return "MUST_NOT"
    if re.search(r"하여야|해야\s*한다|의무", text):
        return "MUST"
    if re.search(r"할\s*수\s*있", text):
        return "MAY"
    if re.search(r"(?:으로|로)\s*본다|간주", text):
        return "DEEMED"
    if re.search(r"경우|요건|한정", text):
        return "CONDITIONAL"
    return "NEUTRAL"


def validate_closed_line_decisions(raw_parts: list[dict | None], cards: list[dict]) -> dict:
    by_id = {row["card_id"]: row for row in cards}
    seen, published, rejected = set(), [], []
    for raw in raw_parts:
        if not isinstance(raw, dict):
            rejected.append({"reason": "missing_model_response"})
            continue
        for decision in raw.get("decisions") or []:
            card_id = str(decision.get("card_id") or "")
            errors = []
            if card_id not in by_id:
                errors.append("unknown_card_id")
            if card_id in seen:
                errors.append("duplicate_card_id")
            seen.add(card_id)
            if decision.get("verdict") != "NORMATIVE":
                errors.append("none_decision")
            if decision.get("verdict") == "NORMATIVE" and decision.get("confidence") != "high":
                errors.append("normative_not_high_confidence")
            if errors:
                rejected.append({"card_id": card_id, "decision": decision,
                                 "validation_errors": errors})
                continue
            card = by_id[card_id]
            text = str(card.get("text") or "")
            condition = [text] if re.search(r"경우|요건|한정", text) else []
            exception = [text] if re.search(
                r"다만|에도\s*불구하고|제외|그러하지\s*아니", text) else []
            values = [match.group(0).strip() for match in _DET_VALUE.finditer(text)]
            temporals = [match.group(0).strip() for match in _DET_TEMPORAL.finditer(text)]
            published.append({
                "claim_id": f"C{len(published) + 1:03d}", "quote_id": card_id,
                "evidence_id": card.get("evidence_id"), "document": card.get("document"),
                "path": card.get("path"), "claim_kind": decision.get("claim_kind"),
                "actor": "", "predicate": text, "object": "",
                "modality": deterministic_modality(text),
                "conditions": condition, "exceptions": exception,
                "quantities": values, "temporals": temporals, "effect": "",
                "confidence": "high", "source_text": text,
                "validation_errors": [], "deterministic_full_line_span": True,
            })
    missing = sorted(set(by_id) - seen)
    rejected.extend({"card_id": card_id, "reason": "missing_decision"}
                    for card_id in missing)
    return {"published": published, "rejected": rejected,
            "complete_decision_contract": not missing and all(
                raw is not None for raw in raw_parts), "missing_card_ids": missing}


def compile_closed_line_claims(llm, evidence: list[dict[str, Any]], *,
                               max_cards: int = MAX_CARDS) -> dict:
    cards = claim_cards(evidence, max_cards=max_cards)
    raw_parts = []
    for position in range(0, len(cards), CARDS_PER_CALL):
        batch = cards[position:position + CARDS_PER_CALL]
        raw_parts.append(llm.structured(
            "rag.answer.haiku.closed_line_claims.experimental", CLOSED_LINE_SYSTEM,
            json.dumps({"cards": batch}, ensure_ascii=False), CLOSED_LINE_SCHEMA,
            max_tokens=2500, effort="low", model=HAIKU_MODEL))
    return {"cards": cards, "product_input_sha256": input_hash(cards),
            "raw_parts": raw_parts, **validate_closed_line_decisions(raw_parts, cards)}


def _packed(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def claim_cards(evidence: list[dict[str, Any]], *, max_cards: int = MAX_CARDS) -> list[dict]:
    cards = build_clause_cards("", evidence, max_cards=max_cards, max_per_evidence=5)
    return [{
        "card_id": str(card["quote_id"]),
        "quote_id": str(card["quote_id"]),
        "evidence_id": str(card["evidence_id"]),
        "document": str(card.get("document") or ""),
        "path": str(card.get("path") or ""),
        "text": str(card.get("text") or ""),
    } for card in cards]


def input_hash(cards: list[dict]) -> str:
    safe = [{"card_id": row["card_id"], "text": row["text"]} for row in cards]
    return hashlib.sha256(json.dumps(
        safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _substring(value: str, text: str) -> bool:
    return not value or value in text


def validate_claim_decisions(raw_parts: list[dict | None], cards: list[dict]) -> dict:
    by_id = {row["card_id"]: row for row in cards}
    seen: set[str] = set()
    published, rejected = [], []
    for raw in raw_parts:
        if not isinstance(raw, dict):
            rejected.append({"reason": "missing_model_response"})
            continue
        for decision in raw.get("decisions") or []:
            card_id = str(decision.get("card_id") or "")
            errors = []
            if card_id not in by_id:
                errors.append("unknown_card_id")
            if card_id in seen:
                errors.append("duplicate_card_id")
            seen.add(card_id)
            card = by_id.get(card_id) or {}
            text = str(card.get("text") or "")
            if decision.get("verdict") == "CLAIM":
                if decision.get("confidence") != "high":
                    errors.append("claim_not_high_confidence")
                if not str(decision.get("predicate") or ""):
                    errors.append("missing_predicate")
                scalar_keys = ("actor", "predicate", "object", "effect")
                list_keys = ("conditions", "exceptions", "quantities", "temporals")
                for key in scalar_keys:
                    if not _substring(str(decision.get(key) or ""), text):
                        errors.append(f"{key}_not_exact_substring")
                for key in list_keys:
                    if any(not _substring(str(value), text)
                           for value in decision.get(key) or []):
                        errors.append(f"{key}_not_exact_substring")
            if decision.get("verdict") != "CLAIM":
                errors.append("none_decision")
            if errors:
                rejected.append({"card_id": card_id, "decision": decision,
                                 "validation_errors": errors})
                continue
            claim = {
                **{key: value for key, value in decision.items() if key != "verdict"},
                "claim_id": f"C{len(published) + 1:03d}",
                "quote_id": card_id,
                "evidence_id": card.get("evidence_id"),
                "document": card.get("document"), "path": card.get("path"),
                "source_text": text,
                "validation_errors": [],
            }
            published.append(claim)
    missing = sorted(set(by_id) - seen)
    rejected.extend({"card_id": card_id, "reason": "missing_decision"}
                    for card_id in missing)
    return {
        "published": published, "rejected": rejected,
        "complete_decision_contract": not missing and all(raw is not None for raw in raw_parts),
        "missing_card_ids": missing,
    }


def compile_claim_edges(llm, evidence: list[dict[str, Any]], *, max_cards: int = MAX_CARDS) \
        -> dict:
    cards = claim_cards(evidence, max_cards=max_cards)
    raw_parts = []
    for position in range(0, len(cards), CARDS_PER_CALL):
        batch = cards[position:position + CARDS_PER_CALL]
        raw = llm.structured(
            "rag.answer.haiku.claim_edges.experimental", CLAIM_SYSTEM,
            json.dumps({"cards": batch}, ensure_ascii=False), CLAIM_SCHEMA,
            max_tokens=5000, effort="low", model=HAIKU_MODEL)
        raw_parts.append(raw)
    validated = validate_claim_decisions(raw_parts, cards)
    return {"cards": cards, "product_input_sha256": input_hash(cards),
            "raw_parts": raw_parts, **validated}


def claim_fingerprint(claim: dict) -> str:
    payload = [
        claim.get("quote_id"), claim.get("claim_kind"), claim.get("modality"),
        _packed(claim.get("actor")), _packed(claim.get("predicate")),
        _packed(claim.get("object")),
        sorted(_packed(value) for value in claim.get("conditions") or []),
        sorted(_packed(value) for value in claim.get("exceptions") or []),
        sorted(_packed(value) for value in claim.get("quantities") or []),
        sorted(_packed(value) for value in claim.get("temporals") or []),
        _packed(claim.get("effect")),
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def consensus_claims(passes: list[dict], *, support: int = 2) -> list[dict]:
    buckets: dict[str, list[tuple[int, dict]]] = {}
    for pass_no, row in enumerate(passes, 1):
        for claim in row.get("published") or []:
            buckets.setdefault(claim_fingerprint(claim), []).append((pass_no, claim))
    out = []
    for fingerprint, values in buckets.items():
        pass_ids = sorted({pass_no for pass_no, _claim in values})
        if len(pass_ids) < support:
            continue
        representative = dict(values[0][1])
        representative["claim_id"] = f"CC{len(out) + 1:03d}"
        representative["consensus_support"] = len(pass_ids)
        representative["consensus_passes"] = pass_ids
        representative["fingerprint"] = fingerprint
        out.append(representative)
    return out


def validate_alignment(raw: dict | None, claims: list[dict]) -> dict:
    ids = {str(claim.get("claim_id") or "") for claim in claims}
    if not isinstance(raw, dict):
        return {"valid": False, "requested_slots": [], "relevant": [],
                "errors": ["missing_alignment_response"]}
    seen, relevant, errors = set(), [], []
    for decision in raw.get("decisions") or []:
        claim_id = str(decision.get("claim_id") or "")
        if claim_id not in ids:
            errors.append("unknown_claim_id")
        if claim_id in seen:
            errors.append("duplicate_claim_id")
        seen.add(claim_id)
        if (decision.get("verdict") == "RELEVANT"
                and decision.get("confidence") in {"high", "medium"}):
            relevant.append(decision)
    if seen != ids:
        errors.append("incomplete_claim_decisions")
    requested = [slot for slot in raw.get("requested_slots") or []
                 if slot in MATRIX_SLOTS]
    return {"valid": not errors, "requested_slots": list(dict.fromkeys(requested)),
            "relevant": relevant, "errors": list(dict.fromkeys(errors))}


def align_claims(llm, question: str, claims: list[dict]) -> dict:
    safe_claims = [{key: claim.get(key) for key in (
        "claim_id", "document", "path", "claim_kind", "actor", "predicate",
        "object", "modality", "conditions", "exceptions", "quantities",
        "temporals", "effect", "source_text")}
        for claim in claims]
    raw = llm.structured(
        "rag.answer.haiku.claim_alignment.experimental", ALIGN_SYSTEM,
        json.dumps({"question": question, "claims": safe_claims}, ensure_ascii=False),
        ALIGN_SCHEMA, max_tokens=4000, effort="low", model=HAIKU_MODEL)
    return {"raw": raw, **validate_alignment(raw, claims)}


def entailment_matrix(claims: list[dict], alignment: dict) -> dict:
    by_id = {str(claim.get("claim_id") or ""): claim for claim in claims}
    slots: dict[str, list[dict]] = {slot: [] for slot in MATRIX_SLOTS}
    for decision in alignment.get("relevant") or []:
        claim = by_id.get(str(decision.get("claim_id") or ""))
        if claim is None:
            continue
        row = {key: claim.get(key) for key in (
            "claim_id", "document", "path", "claim_kind", "actor", "predicate",
            "object", "modality", "conditions", "exceptions", "quantities",
            "temporals", "effect", "source_text")}
        for slot in decision.get("slots") or []:
            if slot in slots:
                slots[slot].append(row)
    requested = list(alignment.get("requested_slots") or [])
    return {
        "requested_slots": requested,
        "slots": slots,
        "covered_slots": [slot for slot in requested if slots.get(slot)],
        "uncovered_slots": [slot for slot in requested if not slots.get(slot)],
        "relevant_claim_count": len({row["claim_id"] for values in slots.values()
                                     for row in values}),
    }


def render_matrix_answer(llm, question: str, evidence: list[dict], matrix: dict) -> dict:
    raw = llm.structured(
        "rag.answer.haiku.claim_matrix_render.experimental", RENDER_SYSTEM,
        json.dumps({"question": question, "entailment_matrix": matrix,
                    "full_evidence": evidence_payload(evidence)}, ensure_ascii=False),
        RENDER_SCHEMA, max_tokens=4000, effort="low", model=HAIKU_MODEL)
    valid_ids = {row.get("claim_id") for values in (matrix.get("slots") or {}).values()
                 for row in values}
    answer = str((raw or {}).get("answer") or "").strip()
    used = [str(value) for value in (raw or {}).get("used_claim_ids") or []]
    errors = []
    if not isinstance(raw, dict):
        errors.append("missing_render_response")
    if not answer:
        errors.append("empty_answer")
    if any(value not in valid_ids for value in used):
        errors.append("unknown_used_claim")
    if bool((raw or {}).get("answerable")) and not used:
        errors.append("answerable_without_claim")
    return {"raw": raw, "answer": answer, "valid": not errors, "errors": errors}


def stability_summary(rows_by_case: dict[str, list[dict]]) -> dict:
    intersection_total = union_total = 0
    modalities = Counter()
    case_jaccards = []
    for passes in rows_by_case.values():
        sets = [{claim_fingerprint(claim) for claim in row.get("published") or []}
                for row in passes]
        union = set().union(*sets) if sets else set()
        intersection = set.intersection(*sets) if sets else set()
        intersection_total += len(intersection); union_total += len(union)
        case_jaccards.append(len(intersection) / len(union) if union else 1.0)
        for claim in consensus_claims(passes):
            modalities[str(claim.get("modality") or "")] += 1
    return {
        "intersection": intersection_total, "union": union_total,
        "jaccard": round(intersection_total / union_total, 4) if union_total else 1.0,
        "mean_case_jaccard": round(sum(case_jaccards) / len(case_jaccards), 4)
        if case_jaccards else 1.0,
        "consensus_modalities": dict(sorted(modalities.items())),
    }
