"""원문 quote ID와 닫힌 결론만 고르는 Haiku 법률 판단 shadow 파이프라인."""

from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_compiler import build_clause_cards
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL
from scripts.rag_deterministic_critical_value_audit import (
    audit_answer as audit_critical_values,
    extract_values,
)


SLOTS = (
    "authority", "conclusion", "actor", "action_or_object", "condition",
    "exception", "quantity", "temporal",
)
CONCLUSIONS = ("APPLIES", "DOES_NOT_APPLY", "CONDITIONAL", "INSUFFICIENT")
MODALITIES = ("MUST", "MAY", "MUST_NOT", "NO_DIRECT_RULE")
QUANTIFIERS = ("EACH", "AGGREGATE", "ANY", "ALL", "MIN", "MAX", "NONE")

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = frozenset({
    "경우", "따라", "대한", "관한", "관련", "한다", "있다", "없다", "규정",
    "질문", "업무", "문맥", "어떻게", "무엇", "여부", "해당",
})
_EXCEPTION = re.compile(
    r"다만|에도 불구하고|그러하지 아니|적용하지 아니|제외|면제|특례")
_CONDITION = re.compile(r"경우|때에는|요건|조건|해당하면|전제로|한정")
_TEMPORAL = re.compile(r"언제|기간|기한|시점|시행|신설|개정|부터|까지|이내|이전|이후")
_QUANTITY_QUESTION = re.compile(
    r"\d|얼마|몇\s*(?:명|인|개|회|일|개월|년)|비율|한도|금액|산정|계산|합산|각각")
_ACTOR_QUESTION = re.compile(
    r"누가|주체|회사|법인|상장주선인|이사|감사|위원|주주|발행인|투자자|벤처금융")
_MODALITY_PATTERNS = {
    "MUST_NOT": re.compile(r"할\s*수\s*없|하여서는\s*아니|금지"),
    "MAY": re.compile(r"할\s*수\s*있"),
    "MUST": re.compile(r"하여야|해야\s*한다|의무"),
}
_QUANTIFIER_PATTERNS = {
    "EACH": re.compile(r"각각"),
    "AGGREGATE": re.compile(r"합산|합계"),
    "ANY": re.compile(r"어느\s+하나|또는"),
    "ALL": re.compile(r"모두|전부|및"),
    "MIN": re.compile(r"중\s+(?:적은|작은)|최소"),
    "MAX": re.compile(r"중\s+(?:큰|많은)|최대"),
}
_COMPARATORS = {
    "GE": re.compile(r"이상"), "GT": re.compile(r"초과"),
    "LE": re.compile(r"이하"), "LT": re.compile(r"미만"),
}


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "slots": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "slot": {"type": "string", "enum": list(SLOTS)},
                "status": {"type": "string", "enum": ["supported", "unsupported"]},
                "quote_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["slot", "status", "quote_ids"],
            "additionalProperties": False,
        }},
        "conclusion": {"type": "string", "enum": list(CONCLUSIONS)},
        "modality": {"type": "string", "enum": list(MODALITIES)},
        "quantifier_relation": {"type": "string", "enum": list(QUANTIFIERS)},
        "decision_quote_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["slots", "conclusion", "modality", "quantifier_relation",
                 "decision_quote_ids"],
    "additionalProperties": False,
}


PLAN_SYSTEM = """너는 한국 법률 원문에서 판단에 필요한 quote ID만 고르는 선택기다.
법률 명제나 답변 문장을 새로 쓰지 않는다.

규칙:
1. requested slots 각각을 supported/unsupported로 판정하고, supported이면 직접
   증명하는 quote ID를 최대 2개만 고른다. 비슷한 주제라는 이유로 고르지 않는다.
2. conclusion·modality·quantifier_relation은 제공된 enum에서만 고른다.
3. 질문의 시장·문서·주체·행위·대상·조건이 quote와 같아야 결론 근거가 된다.
4. 본문, 단서, 예외, 재예외를 분리해 읽고 `각각/합산`, `또는/모두`,
   `이상/초과/이하/미만`, `하여야/할 수 있다/할 수 없다`를 바꾸지 않는다.
5. Wiki, 일반 법률지식, 사례 ID, 카드 밖 문언을 사용하지 않는다.
6. 직접 결론 근거가 없으면 INSUFFICIENT/NO_DIRECT_RULE로 둔다.
7. decision_quote_ids도 실제 카드 ID만 최대 3개 고른다."""


RENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"type": "string"},
        "support_quote_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answerable", "answer", "support_quote_ids"],
    "additionalProperties": False,
}


RENDER_SYSTEM = """너는 검증된 quote와 닫힌 법률 판단만 간결한 한국어 답변으로
렌더링한다. 결론부터 쓰고, 질문이 요구한 조건·예외·수치·기간만 붙인다.
quote에 없는 값, 날짜, 주체, 예외, 조문을 추가하지 않는다. 원문의 각각/합산,
또는/모두, 이상/초과/이하/미만, 의무/재량/금지를 그대로 보존한다.
내부 quote ID는 답변 문장에 쓰지 않는다. support_quote_ids는 사용한 카드만 고른다."""


def required_slots(question: str) -> list[str]:
    text = str(question or "")
    required = ["authority", "conclusion", "action_or_object"]
    if _ACTOR_QUESTION.search(text):
        required.append("actor")
    if _CONDITION.search(text) or re.search(r"요건|면제|예외|제외|특례", text):
        required.append("condition")
    if re.search(r"면제|예외|제외|특례|적용하지", text):
        required.append("exception")
    if _QUANTITY_QUESTION.search(text):
        required.append("quantity")
    if _TEMPORAL.search(text):
        required.append("temporal")
    return [slot for slot in SLOTS if slot in required]


def operator_ast(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for card in cards:
        text = str(card.get("text") or "")
        out[str(card.get("quote_id") or "")] = {
            "modalities": [name for name, pattern in _MODALITY_PATTERNS.items()
                           if pattern.search(text)],
            "quantifiers": [name for name, pattern in _QUANTIFIER_PATTERNS.items()
                            if pattern.search(text)],
            "comparators": [name for name, pattern in _COMPARATORS.items()
                            if pattern.search(text)],
            "exception": bool(_EXCEPTION.search(text)),
            "condition": bool(_CONDITION.search(text)),
            "values": extract_values(text),
        }
    return out


def closed_value_candidates(question: str, cards: list[dict[str, Any]]) -> list[dict]:
    rows = [{**row, "source": "question"} for row in extract_values(question)]
    for card in cards:
        rows.extend({**row, "source": str(card.get("quote_id") or "")}
                    for row in extract_values(str(card.get("text") or "")))
    seen = set()
    return [row for row in rows
            if not (row["canonical"] in seen or seen.add(row["canonical"]))]


def _plan_slots(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out = {}
    for row in (raw or {}).get("slots") or []:
        slot = str(row.get("slot") or "")
        if slot in SLOTS and slot not in out:
            out[slot] = {
                "slot": slot, "status": str(row.get("status") or ""),
                "quote_ids": sorted(dict.fromkeys(
                    str(value) for value in row.get("quote_ids") or [])),
            }
    return out


def validate_plan(raw: dict[str, Any] | None, cards: list[dict[str, Any]],
                  requested: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["missing_plan"]}
    errors = []
    valid_ids = {str(card.get("quote_id") or "") for card in cards}
    slots = _plan_slots(raw)
    for slot in requested:
        if slot not in slots:
            errors.append(f"missing_slot:{slot}")
            continue
        row = slots[slot]
        ids = row["quote_ids"]
        if len(ids) > 2:
            errors.append(f"too_many_quotes:{slot}")
        if any(value not in valid_ids for value in ids):
            errors.append(f"invalid_quote:{slot}")
        if row["status"] == "supported" and not ids:
            errors.append(f"unsupported_contract:{slot}")
        if row["status"] == "unsupported" and ids:
            errors.append(f"unsupported_has_quotes:{slot}")
        if row["status"] not in {"supported", "unsupported"}:
            errors.append(f"invalid_status:{slot}")
    decision_ids = [str(value) for value in raw.get("decision_quote_ids") or []]
    if len(decision_ids) > 3:
        errors.append("too_many_decision_quotes")
    if any(value not in valid_ids for value in decision_ids):
        errors.append("invalid_decision_quote")
    if str(raw.get("conclusion") or "") != "INSUFFICIENT" and not decision_ids:
        errors.append("decision_missing_quote")
    if str(raw.get("conclusion") or "") not in CONCLUSIONS:
        errors.append("invalid_conclusion")
    if str(raw.get("modality") or "") not in MODALITIES:
        errors.append("invalid_modality")
    if str(raw.get("quantifier_relation") or "") not in QUANTIFIERS:
        errors.append("invalid_quantifier")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)),
            "slots": slots}


def _fingerprint_slot(row: dict[str, Any] | None) -> tuple:
    return (str((row or {}).get("status") or ""),
            tuple(sorted(str(value) for value in (row or {}).get("quote_ids") or [])))


def disagreements(first: dict[str, Any], second: dict[str, Any],
                  requested: list[str]) -> dict[str, Any]:
    a, b = _plan_slots(first), _plan_slots(second)
    slots = [slot for slot in requested
             if _fingerprint_slot(a.get(slot)) != _fingerprint_slot(b.get(slot))]
    decision_fields = [field for field in
                       ("conclusion", "modality", "quantifier_relation",
                        "decision_quote_ids")
                       if ((tuple(sorted(first.get(field) or []))
                            if field == "decision_quote_ids" else first.get(field))
                           != (tuple(sorted(second.get(field) or []))
                               if field == "decision_quote_ids" else second.get(field)))]
    return {"slots": slots, "decision_fields": decision_fields,
            "needs_tiebreak": bool(slots or decision_fields)}


def reconcile(first: dict[str, Any], second: dict[str, Any],
              third: dict[str, Any] | None, requested: list[str]) -> dict[str, Any]:
    dispute = disagreements(first, second, requested)
    a, b, c = _plan_slots(first), _plan_slots(second), _plan_slots(third)
    rows = []
    for slot in requested:
        if slot in dispute["slots"]:
            chosen = c.get(slot)
        else:
            chosen = a.get(slot) if _fingerprint_slot(a.get(slot)) == \
                _fingerprint_slot(b.get(slot)) else None
        if chosen:
            rows.append(chosen)
    out = {"slots": rows}
    for field in ("conclusion", "modality", "quantifier_relation",
                  "decision_quote_ids"):
        if field in dispute["decision_fields"]:
            out[field] = (third or {}).get(field)
        else:
            out[field] = first.get(field)
    return out


def _tokens(text: str) -> set[str]:
    return {token for token in _WORD.findall(text) if token not in _STOP}


def explicit_conflicts(cards: list[dict[str, Any]], selected_ids: set[str]) -> list[dict]:
    """같은 조문·높은 어휘 중첩·정반대 양태가 모두 있을 때만 표시한다."""
    selected = [card for card in cards
                if str(card.get("quote_id") or "") in selected_ids]
    out = []
    for pos, left in enumerate(selected):
        lt = _tokens(str(left.get("text") or ""))
        lm = set(operator_ast([left])[str(left.get("quote_id"))]["modalities"])
        for right in selected[pos + 1:]:
            if (str(left.get("document") or "") != str(right.get("document") or "")
                    or str(left.get("path") or "") != str(right.get("path") or "")):
                continue
            rt = _tokens(str(right.get("text") or ""))
            rm = set(operator_ast([right])[str(right.get("quote_id"))]["modalities"])
            overlap = len(lt & rt) / max(1, min(len(lt), len(rt)))
            opposite = ("MUST_NOT" in lm and bool(rm & {"MUST", "MAY"})) or \
                ("MUST_NOT" in rm and bool(lm & {"MUST", "MAY"}))
            if opposite and overlap >= 0.75:
                out.append({"left": left["quote_id"], "right": right["quote_id"],
                            "token_overlap": round(overlap, 4),
                            "reason": "same_scope_opposite_modality"})
    return out


def minimal_quote_cover(plan: dict[str, Any], requested: list[str],
                        cards: list[dict[str, Any]]) -> list[str]:
    slots = _plan_slots(plan)
    coverage: dict[str, set[str]] = defaultdict(set)
    for slot in requested:
        for quote_id in (slots.get(slot) or {}).get("quote_ids") or []:
            coverage[quote_id].add(slot)
    uncovered = {slot for slot in requested
                 if (slots.get(slot) or {}).get("status") == "supported"}
    chosen = []
    while uncovered:
        candidates = [(len(values & uncovered), quote_id)
                      for quote_id, values in coverage.items() if values & uncovered]
        if not candidates:
            break
        _count, quote_id = max(candidates, key=lambda value: (value[0], value[1]))
        chosen.append(quote_id)
        uncovered -= coverage[quote_id]
    for quote_id in plan.get("decision_quote_ids") or []:
        if quote_id not in chosen:
            chosen.append(str(quote_id))
    # 독립 단서 줄이면 바로 앞 원문 줄을 함께 보존한다.
    by_id = {str(card.get("quote_id") or ""): card for card in cards}
    for quote_id in list(chosen):
        card = by_id.get(quote_id) or {}
        if _EXCEPTION.search(str(card.get("text") or "")) and ":L" in quote_id:
            prefix, raw = quote_id.rsplit(":L", 1)
            if raw.isdigit() and int(raw) > 1:
                previous = f"{prefix}:L{int(raw) - 1}"
                if previous in by_id and previous not in chosen:
                    chosen.append(previous)
    return chosen[:10]


def certificate(plan: dict[str, Any], requested: list[str],
                cards: list[dict[str, Any]]) -> dict[str, Any]:
    slots = _plan_slots(plan)
    selected_ids = set(minimal_quote_cover(plan, requested, cards))
    ast = operator_ast(cards)
    rows = []
    for slot in requested:
        row = slots.get(slot) or {"status": "unsupported", "quote_ids": []}
        rows.append({"slot": slot, "required": True,
                     "status": row.get("status"),
                     "quote_ids": list(row.get("quote_ids") or [])})
    errors = []
    missing = [row["slot"] for row in rows if row["status"] != "supported"]
    if missing:
        errors.append("missing_required_slots:" + ",".join(missing))
    selected_ast = [ast.get(value) or {} for value in selected_ids]
    modality = str(plan.get("modality") or "")
    available_modalities = {value for row in selected_ast
                            for value in row.get("modalities") or []}
    if modality == "NO_DIRECT_RULE":
        if plan.get("conclusion") != "INSUFFICIENT":
            errors.append("no_direct_rule_without_insufficient")
    elif modality not in available_modalities:
        errors.append("modality_not_in_selected_quotes")
    quantifier = str(plan.get("quantifier_relation") or "NONE")
    available_quantifiers = {value for row in selected_ast
                             for value in row.get("quantifiers") or []}
    if quantifier != "NONE" and quantifier not in available_quantifiers:
        errors.append("quantifier_not_in_selected_quotes")
    conflicts = explicit_conflicts(cards, selected_ids)
    if conflicts:
        errors.append("unresolved_explicit_conflict")
    return {"valid": not errors, "errors": errors, "slots": rows,
            "selected_quote_ids": sorted(selected_ids), "conflicts": conflicts,
            "available_modalities": sorted(available_modalities),
            "available_quantifiers": sorted(available_quantifiers)}


def select_plan(llm, question: str, cards: list[dict[str, Any]],
                requested: list[str], ast: dict[str, Any], *, pass_name: str,
                disputed: dict[str, Any] | None = None) -> dict[str, Any] | None:
    focus = ""
    if disputed:
        focus = ("\n\n[재판정 범위]\n다음 불일치만 다시 판정하되 schema의 다른 "
                 "필드도 유효하게 채운다: " + json.dumps(disputed, ensure_ascii=False))
    user = (f"[질문]\n{question}\n\n[requested slots]\n"
            f"{json.dumps(requested, ensure_ascii=False)}\n\n[결정론 연산자 AST]\n"
            f"{json.dumps(ast, ensure_ascii=False)}\n\n[원문 quote cards]\n"
            f"{json.dumps(cards, ensure_ascii=False)}{focus}")
    return llm.structured(
        f"rag.answer.haiku.quote_decision.{pass_name}.experimental",
        PLAN_SYSTEM, user, PLAN_SCHEMA, max_tokens=2600,
        effort="low", model=HAIKU_MODEL)


def render_answer(llm, question: str, plan: dict[str, Any], cert: dict[str, Any],
                  cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = set(cert.get("selected_quote_ids") or [])
    selected = [card for card in cards
                if str(card.get("quote_id") or "") in wanted]
    user = (f"[질문]\n{question}\n\n[검증된 닫힌 판단]\n"
            f"{json.dumps(plan, ensure_ascii=False)}\n\n[증거 충족 certificate]\n"
            f"{json.dumps(cert, ensure_ascii=False)}\n\n[사용 가능한 원문 quote]\n"
            f"{json.dumps(selected, ensure_ascii=False)}")
    return llm.structured(
        "rag.answer.haiku.quote_decision.render.experimental",
        RENDER_SYSTEM, user, RENDER_SCHEMA, max_tokens=2200,
        effort="low", model=HAIKU_MODEL)


def quote_decision_answer(llm, question: str, evidence: list[dict[str, Any]],
                          fallback: str) -> dict[str, Any]:
    requested = required_slots(question)
    cards = build_clause_cards(question, evidence, max_cards=56, max_per_evidence=7)
    ast = operator_ast(cards)
    values = closed_value_candidates(question, cards)
    first = select_plan(llm, question, cards, requested, ast, pass_name="pass1")
    second = select_plan(llm, question, cards, requested, ast, pass_name="pass2")
    first_validation = validate_plan(first, cards, requested)
    second_validation = validate_plan(second, cards, requested)
    dispute = disagreements(first or {}, second or {}, requested)
    third = None
    if first_validation["valid"] and second_validation["valid"] \
            and dispute["needs_tiebreak"]:
        third = select_plan(llm, question, cards, requested, ast,
                            pass_name="tiebreak", disputed=dispute)
    final_plan = reconcile(first or {}, second or {}, third, requested)
    final_validation = validate_plan(final_plan, cards, requested)
    cert = certificate(final_plan, requested, cards) if final_validation["valid"] else {
        "valid": False, "errors": ["invalid_final_plan"], "selected_quote_ids": []}
    base = {
        "requested_slots": requested, "cards": cards, "operator_ast": ast,
        "closed_value_candidates": values, "pass1": first, "pass2": second,
        "tiebreak": third, "disagreements": dispute, "final_plan": final_plan,
        "validations": {"pass1": first_validation, "pass2": second_validation,
                        "final": final_validation}, "certificate": cert,
        "plan_calls": 2 + int(third is not None),
        "always_three_calls_saved": int(third is None),
    }
    if not final_validation["valid"] or not cert.get("valid"):
        return {**base, "action": "keep", "guard": "invalid_or_incomplete_plan",
                "answer": fallback, "raw_candidate_answer": ""}
    raw = render_answer(llm, question, final_plan, cert, cards)
    selected_ids = set(cert.get("selected_quote_ids") or [])
    support = [str(value) for value in (raw or {}).get("support_quote_ids") or []]
    answer = str((raw or {}).get("answer") or "").strip()
    render_errors = []
    if not (raw or {}).get("answerable") or not answer:
        render_errors.append("not_answerable")
    if not support or any(value not in selected_ids for value in support):
        render_errors.append("invalid_render_support")
    selected_text = "\n".join(str(card.get("text") or "") for card in cards
                              if str(card.get("quote_id") or "") in selected_ids)
    critical = audit_critical_values(question, answer, selected_text) if answer else {
        "flagged": True, "unsupported_values": [], "unsupported_operators": [],
        "unsupported_modalities": []}
    if critical.get("flagged"):
        render_errors.append("unsupported_critical_surface")
    accepted = not render_errors
    return {
        **base, "render": raw, "render_errors": render_errors,
        "critical_value_audit": critical,
        "action": "replace" if accepted else "keep",
        "guard": "validated_quote_decision" if accepted else "invalid_render",
        "answer": answer if accepted else fallback,
        "raw_candidate_answer": answer,
    }


__all__ = [
    "HAIKU_MODEL", "PLAN_SCHEMA", "RENDER_SCHEMA", "required_slots",
    "operator_ast", "closed_value_candidates", "validate_plan", "disagreements",
    "reconcile", "minimal_quote_cover", "explicit_conflicts", "certificate",
    "quote_decision_answer",
]
