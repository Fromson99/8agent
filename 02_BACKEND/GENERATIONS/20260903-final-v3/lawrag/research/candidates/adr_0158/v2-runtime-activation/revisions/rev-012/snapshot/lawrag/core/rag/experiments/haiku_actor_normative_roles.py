"""Haiku가 증명된 GOVERNS_ACTOR를 상호 배타적 규범 역할로 분해한다.

질문이나 골든 없이 관계 artifact에 이미 내장된 원문 proof quote만 소비하는
shadow 컴파일러다. 운영 graph나 기존 관계 컴파일러에는 연결하지 않는다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL


ACTOR_ROLES = (
    "OBLIGOR",
    "POWER_HOLDER",
    "RIGHT_HOLDER",
    "BENEFICIARY",
    "CONDITION_ACTOR",
    "PROCEDURAL_OBJECT",
    "STATUS_SUBJECT",
    "UNCERTAIN",
)

_ROLE_SIGNALS = {
    "OBLIGOR": re.compile(
        r"하여야|해야|[가-힣]{1,12}(?:아야|어야|여야)\s*한다|"
        r"할\s*수\s*없|아니\s*된다|하여서는\s*아니|하지\s*아니|금지|의무|책임|"
        r"제출|신고|납부|보유|준수|이행|갖추어야|선임하여야"
    ),
    "POWER_HOLDER": re.compile(
        r"할\s*수\s*있|권한|승인|인가|허가|명령|결정|지정|선정|"
        r"정할\s*수|요구할\s*수|제외할\s*수|면제할\s*수"
    ),
    "RIGHT_HOLDER": re.compile(
        r"권리|청구할\s*수|신청할\s*수|요청할\s*수|열람할\s*수|"
        r"행사할\s*수|받을\s*수|선택할\s*수|동의"
    ),
    "BENEFICIARY": re.compile(
        r"지급받|보상받|배상받|수령|귀속|혜택|보호받|면제되|감면|"
        r"배당받|교부받|공제|과세하지\s*아니|이익을\s*얻"
    ),
    "CONDITION_ACTOR": re.compile(
        r"발행|양도|취득|증여|출자|거래|행사함으로써|보유하고\s*있는|"
        r"포기|함으로써|발생"
    ),
    "PROCEDURAL_OBJECT": re.compile(
        r"대상|적용|심사|조사|검사|처분|제외|포함|선정|지정|등록|"
        r"상장|평가|산정|의무보유|상장일부터|보유기간"
    ),
    "STATUS_SUBJECT": re.compile(
        r"해당|말한다|본다|간주|자격|요건|인\s*자|인\s*경우|"
        r"로\s*한다|으로\s*한다|구성|임원|주주"
    ),
}
_ANY_SIGNAL = re.compile(
    "|".join(f"(?:{pattern.pattern})" for pattern in _ROLE_SIGNALS.values())
)
_EXPLICIT_DEONTIC = re.compile(
    r"하여야|해야|[가-힣]{1,12}(?:아야|어야|여야)\s*한다|"
    r"할\s*수\s*없|하여서는\s*아니|책임"
)


ROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "roles": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "relation_ref": {"type": "string"},
                "actor_surface": {"type": "string"},
                "role": {"type": "string", "enum": list(ACTOR_ROLES)},
                "quote_id": {"type": "string"},
                "modality_surface": {
                    "type": "string",
                    "description": "같은 quote에서 그대로 복사한 규범 양태 문구",
                },
                "rationale": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium"]},
            },
            "required": [
                "relation_ref", "actor_surface", "role", "quote_id",
                "modality_surface", "rationale", "confidence",
            ],
            "additionalProperties": False,
        }},
        "unresolved_refs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["roles", "unresolved_refs"],
    "additionalProperties": False,
}


ROLE_SYSTEM = """너는 한국 법률 원문에 이미 증명된 GOVERNS_ACTOR 관계를 하나의
규범 역할로 정규화한다. 질문에 답하지 말고 제공된 actor와 proof quote만 사용한다.

역할은 다음 우선순위로 상호 배타적으로 하나만 고른다.
1. OBLIGOR: actor 자신에게 작위·부작위·제출·보유·책임 의무가 부과된다.
2. POWER_HOLDER: actor가 타인의 법적 지위나 절차를 결정·승인·명령·지정하거나
   법이 준 재량을 행사한다. 단순히 신청할 수 있는 사인의 권리와 구별한다.
3. RIGHT_HOLDER: actor가 청구·신청·열람·선택 등 자기 이익을 위한 권리를 행사한다.
4. BENEFICIARY: actor가 권리를 직접 행사하는 주체라기보다 지급·보호·감면 등의
   수익을 수동적으로 받는다.
5. CONDITION_ACTOR: actor의 발행·취득·양도·출자 등 행위가 다른 법률효과를
   발생시키는 구성요건 사실이지만, 그 행위 자체가 명령·금지되지는 않는다.
6. PROCEDURAL_OBJECT: actor가 심사·평가·적용·의무보유·상장·조사·처분 등 규율의
   대상이다. 조문이 actor 자신의 행위를 명령하는 경우에는 OBLIGOR가 우선한다.
7. STATUS_SUBJECT: 조문이 actor의 정의·자격·구성·신분만 정하고 행위 규범은 없다.
8. UNCERTAIN: 한 quote에서 역할이 갈리거나 actor와 규범 양태의 문법적 연결을
   확정할 수 없다.

증명 계약:
- actor_surface는 입력 actor를 글자 하나도 바꾸지 않고 복사한다.
- quote_id는 해당 관계에 내장된 proof quote 중 하나만 쓴다.
- modality_surface는 같은 quote에서 actor의 역할을 증명하는 **짧은 연속 부분문자열**
  (권장 2~20어절)을 공백·괄호·조사·문장부호까지 정확히 복사한다. 원문 문장을
  요약하거나 어미를 바꾸거나 원문에 없는 '의무', '권한' 같은 말을 보태지 않는다.
- actor와 modality가 같은 quote에서 문법적으로 연결되지 않으면 unresolved_refs로
  보낸다. 근거가 약하면 관계를 억지로 분류하지 않는다.
- confidence=high만 publish 대상이다."""


ROLE_SYSTEM += """

경계 사례 규칙:
- '위원 중 1명 이상은 전문가이어야 한다', '3명 이상의 이사로 구성한다'는 사람이나
  기관의 행위 의무가 아니라 구성·자격 요건이므로 STATUS_SUBJECT다.
- 'actor: 상장일부터 6개월'처럼 콜론 뒤 기간만 정한 목록은 actor의 명시적 작위
  의무가 아니다. actor나 그 보유물이 규율 대상이면 PROCEDURAL_OBJECT다.
- actor가 발행·취득·포기한 **경우**를 과세·증여 등 다른 법률효과의 요건으로 삼을
  때만 CONDITION_ACTOR다. 단지 예외 문장에 '경우'가 있다는 이유로 고르지 않는다.
- 'A가 B를 선임하여야 한다'에서 A는 OBLIGOR, B는 PROCEDURAL_OBJECT다."""


def build_actor_role_input(relations: list[dict[str, Any]]) \
        -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """GOVERNS_ACTOR와 내장 proof quote만 닫힌 메뉴로 만든다."""
    menu: list[dict[str, Any]] = []
    closed: dict[str, dict[str, Any]] = {}
    for position, relation in enumerate(relations, 1):
        if str(relation.get("relation_type") or "") != "GOVERNS_ACTOR":
            continue
        relation_ref = f"A{position}"
        proof_quotes = [{
            "quote_id": str(quote.get("quote_id") or ""),
            "evidence_id": str(quote.get("evidence_id") or ""),
            "kind": str(quote.get("kind") or ""),
            "text": str(quote.get("text") or ""),
        } for quote in relation.get("proof_quotes") or []]
        row = {
            "relation_ref": relation_ref,
            "relation_type": "GOVERNS_ACTOR",
            "source_id": str(relation.get("source_id") or ""),
            "actor_surface": str(relation.get("target_value") or ""),
            "proof_quotes": proof_quotes,
        }
        menu.append(row)
        closed[relation_ref] = row
    return menu, closed


def _surface_distance(text: str, actor: str, modality: str) -> int | None:
    actor_positions = [match.start() for match in re.finditer(re.escape(actor), text)]
    modality_positions = [match.start() for match in re.finditer(
        re.escape(modality), text)]
    if not actor_positions or not modality_positions:
        return None
    return min(abs(left - right) for left in actor_positions for right in modality_positions)


def _actor_grammar_roles(text: str, actor: str) -> set[str]:
    """actor 직후 조사로 동일 quote 안의 주어/객체 역할 충돌만 보수적으로 잡는다."""
    found: set[str] = set()
    for match in re.finditer(re.escape(actor), text):
        suffix = text[match.end():match.end() + 12].lstrip()
        if suffix.startswith(("은", "는", "이", "가")):
            found.add("subject")
        if suffix.startswith(("을", "를", "에게", "에", "와", "과", "의")):
            found.add("object")
    return found


def validate_actor_roles(raw: dict[str, Any] | None,
                         closed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    published, rejected = [], []
    seen: set[str] = set()
    for candidate in list((raw or {}).get("roles") or []):
        errors: list[str] = []
        relation_ref = str(candidate.get("relation_ref") or "")
        actor = str(candidate.get("actor_surface") or "")
        role = str(candidate.get("role") or "")
        quote_id = str(candidate.get("quote_id") or "")
        modality = str(candidate.get("modality_surface") or "")
        source = closed.get(relation_ref)
        if relation_ref in seen:
            errors.append("duplicate_relation_ref")
        seen.add(relation_ref)
        if source is None:
            errors.append("relation_ref_not_in_closed_menu")
        if str(candidate.get("confidence") or "") != "high":
            errors.append("confidence_not_high")
        if role not in ACTOR_ROLES:
            errors.append("invalid_role")
        if source is not None and actor != source["actor_surface"]:
            errors.append("actor_surface_not_exact")
        quotes = {str(row.get("quote_id") or ""): row
                  for row in (source or {}).get("proof_quotes") or []}
        quote = quotes.get(quote_id)
        if quote is None:
            errors.append("quote_not_in_relation_proof")
        quote_text = str((quote or {}).get("text") or "")
        if not actor or actor not in quote_text:
            errors.append("actor_not_exact_in_quote")
        if (not modality or modality == actor or modality not in quote_text):
            errors.append("modality_not_exact_in_quote")
        distance = _surface_distance(quote_text, actor, modality)
        if distance is None or distance > 1200:
            errors.append("actor_modality_not_local")
        signal = _ANY_SIGNAL if role == "UNCERTAIN" else _ROLE_SIGNALS.get(role)
        if signal is None or not signal.search(modality):
            errors.append("modality_incompatible_with_role")
        grammar_roles = _actor_grammar_roles(quote_text, actor) if actor else set()
        if len(grammar_roles) > 1 and role != "UNCERTAIN":
            errors.append("actor_has_multiple_grammatical_roles")
        if (role == "PROCEDURAL_OBJECT" and "subject" in grammar_roles
                and _EXPLICIT_DEONTIC.search(modality)):
            errors.append("active_deontic_subject_mislabeled_as_object")
        if (role == "OBLIGOR"
                and re.search(r"(?:명|분의\s*\d|위원|이사).{0,100}(?:이어야|구성)",
                              modality)
                and not re.search(
                    r"제출|신고|보유|선임|설치|이행|심사|보고|비치|해지|"
                    r"제정|운영|날인|서명|매도|배상|책임", modality)):
            errors.append("status_requirement_mislabeled_as_obligor")
        row = {**candidate,
               "proof_quote": ({"quote_id": quote_id,
                                "evidence_id": str((quote or {}).get("evidence_id") or ""),
                                "kind": str((quote or {}).get("kind") or ""),
                                "text": quote_text} if quote else None),
               "validation_errors": list(dict.fromkeys(errors))}
        (rejected if errors else published).append(row)
    unresolved = [str(value) for value in (raw or {}).get("unresolved_refs") or []]
    missing = sorted(set(closed) - seen - set(unresolved))
    invalid_unresolved = sorted(set(unresolved) - set(closed))
    return {
        "published": published,
        "rejected": rejected,
        "unresolved_refs": unresolved,
        "missing_refs": missing,
        "invalid_unresolved_refs": invalid_unresolved,
        "published_count": len(published),
        "rejected_count": len(rejected),
        "coverage_count": len(seen | (set(unresolved) & set(closed))),
    }


def compile_actor_roles(llm, relations: list[dict[str, Any]]) -> dict[str, Any]:
    menu, closed = build_actor_role_input(relations)
    user = "[closed actor relations]\n" + json.dumps(menu, ensure_ascii=False)
    raw = llm.structured(
        "rag.data.haiku.actor_normative_roles.experimental",
        ROLE_SYSTEM, user, ROLE_SCHEMA, max_tokens=5000,
        effort="low", model=HAIKU_MODEL,
    )
    return {
        "menu": menu,
        "raw": raw,
        "validation": validate_actor_roles(raw, closed),
    }
