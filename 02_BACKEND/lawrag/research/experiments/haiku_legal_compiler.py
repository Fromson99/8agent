"""Haiku 전용 법률 명제 컴파일러 shadow 실험.

검색 결과를 답변 모델에 평평하게 주지 않고, 결정론 근거 카드와 좌표가 붙은
법률 명제표로 먼저 컴파일한다. 골든이나 사례별 규칙을 사용하지 않으며 운영
배선에는 연결하지 않는다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lawrag.core.domain_graph import requirements
from lawrag.research.experiments.haiku_legal_methods import (
    HAIKU_MODEL,
    authority_kind,
    provenance_path,
)
from lawrag.research.experiments.legal_answer_repair import (
    _claims_direct_rule_absence,
    should_preserve_interpretive_qualification,
)


_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_ARTICLE = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_SUBUNIT = re.compile(r"제\s*\d+\s*(?:항|호|목)")
_CRITICAL = re.compile(
    r"다만|단서|에도 불구하고|적용하지 아니|제외|그러하지 아니|준용|"
    r"세칙으로 정하는|대통령령으로 정하는|총리령으로 정하는|부령으로 정하는|"
    r"에서 [\"'“「『].{0,40}[\"'”」』](?:이란|란)|"
    r"각각|어느 하나|중 (?:적은|큰)|하여야|해야|할 수 있|할 수 없"
)
_DATE = re.compile(r"(?:19|20)\d{2}\s*(?:[.년-]\s*\d{1,2})?")
_QUANTITY = re.compile(
    r"\d+(?:\.\d+)?\s*(?:퍼센트|%|원|만원|억원|조원|명|인|회|개|주|일|개월|년)"
    r"|100분의\s*\d+|\d+분의\s*\d+|과반수"
)
_STOP = frozenset({
    "관한", "관련", "경우", "내용", "규정", "질문", "업무", "문맥", "대한",
    "따른", "있는", "하는", "어떻게", "무엇", "기준", "해당", "여부",
})


def _packed(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _WORD.findall(str(value or ""))
            if token not in _STOP}


def _units(value: str) -> set[str]:
    return {_packed(match.group(0)) for pattern in (_ARTICLE, _SUBUNIT)
            for match in pattern.finditer(str(value or ""))}


def _document_family(value: str) -> str:
    return re.sub(r"(?:시행령|시행규칙|시행세칙)$", "", _packed(value))


def _line_role(line: str) -> str:
    if re.search(r"다만|단서|에도 불구하고|적용하지 아니|제외|그러하지 아니", line):
        return "exception"
    if re.search(r"에서 [\"'“「『].{0,40}[\"'”」』](?:이란|란)|뜻은|정의", line):
        return "definition"
    if re.search(r"준용|대통령령으로 정하는|총리령으로 정하는|부령으로 정하는|"
                 r"세칙으로 정하는", line):
        return "delegation_or_reference"
    if _DATE.search(line) or re.search(r"시행일|경과조치|부터|까지|이내|이전|이후", line):
        return "temporal"
    if _QUANTITY.search(line) or re.search(r"산식|계산|합계|곱한|나눈|적은 금액|큰 금액", line):
        return "calculation"
    if re.search(r"신고|제출|승인|결의|통지|공시|첨부", line):
        return "procedure"
    if re.search(r"무효|취소|책임|과태료|벌금|효력|로 본다|으로 본다", line):
        return "effect"
    return "rule"


def _score(question: str, row: dict[str, Any], line: str, position: int) -> int:
    question_tokens = _tokens(question)
    question_units = _units(question)
    score = 3 * len(question_tokens & _tokens(line))
    score += 10 * len(question_units & _units(line))
    if _packed(str(row.get("document") or "")) in _packed(question):
        score += 4
    if _CRITICAL.search(line):
        score += 4
    if requirements.extract(line):
        score += 2
    if _QUANTITY.search(line) and re.search(r"얼마|몇|비율|한도|산정|계산|금액", question):
        score += 5
    if _DATE.search(line) and re.search(r"언제|기간|기한|시행|신설|개정|기준일", question):
        score += 5
    if position < 3:
        score += 2
    return score


def evidence_inventory(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for position, row in enumerate(evidence, 1):
        path, ancestor_history = provenance_path(str(row.get("path") or ""))
        out.append({
            "evidence_id": str(row.get("id") or f"E{position}"),
            "position": position,
            "document": str(row.get("document") or ""),
            "document_family": _document_family(str(row.get("document") or "")),
            "authority_kind": authority_kind(str(row.get("document") or "")),
            "path": path,
            "ancestor_heading_history": ancestor_history,
            "role": str(row.get("role") or ""),
            "document_revision": str(row.get("document_revision") or ""),
            "document_enforcement": str(row.get("document_enforcement") or ""),
            "document_current": bool(row.get("document_current", True)),
            "chars": len(str(row.get("original_text") or "")),
            "typed_connection": dict(row.get("typed_connection") or {
                "connection_role": "unclassified_context",
                "conclusion_eligible": False,
            }),
        })
    return out


def build_clause_cards(question: str, evidence: list[dict[str, Any]], *,
                       max_cards: int = 56, max_per_evidence: int = 7) \
        -> list[dict[str, Any]]:
    """전 조문 표제는 inventory에 두고, 판단 문언은 줄·이웃 단위 카드로 만든다."""
    candidates: list[tuple[int, int, int, dict[str, Any]]] = []
    mandatory: set[str] = set()
    primary_mandatory: set[str] = set()
    for evidence_position, row in enumerate(evidence, 1):
        evidence_id = str(row.get("id") or f"E{evidence_position}")
        lines = [line.rstrip() for line in str(row.get("original_text") or "").splitlines()
                 if line.strip()]
        if not lines:
            continue
        anchors = []
        scored: dict[int, int] = {}
        for line_position, line in enumerate(lines):
            score = _score(question, row, line, evidence_position - 1)
            scored[line_position] = score
            if score:
                anchors.append((score, line_position))
        if not anchors:
            anchors = [(1, 0)]
        selected: dict[int, int] = {}
        for score, line_position in sorted(
                anchors, key=lambda value: (-value[0], value[1]))[:max_per_evidence]:
            for neighbor in range(max(0, line_position - 1),
                                  min(len(lines), line_position + 2)):
                selected[neighbor] = max(selected.get(neighbor, 0),
                                         score - abs(neighbor - line_position))
        # 첫 착지 조문은 짧으면 전체 구조를 보존한다. 항·호 하나가 밀리면
        # 본문/단서/열거 관계가 끊겨 법적 의미가 바뀐다.
        if evidence_position == 1 and len(lines) <= 24:
            for line_position in range(len(lines)):
                selected[line_position] = max(selected.get(line_position, 0),
                                              scored.get(line_position, 0), 8)
                quote_id = f"{evidence_id}:L{line_position + 1}"
                mandatory.add(quote_id)
                primary_mandatory.add(quote_id)
        # 질문 관련 단서·배제·준용 줄은 뒤따르는 호를 같은 블록으로 보존한다.
        for score, line_position in anchors:
            if score < 7 or not _CRITICAL.search(lines[line_position]):
                continue
            for child in range(line_position,
                               min(len(lines), line_position + 7)):
                if child > line_position and re.match(r"\s*[①-⑳]", lines[child]):
                    break
                selected[child] = max(selected.get(child, 0),
                                      score - min(3, child - line_position))
                mandatory.add(f"{evidence_id}:L{child + 1}")
        # D 채널은 골든 조문이 아니어도 답 문맥에 필요한 반례가 있으므로 최고
        # 관련 절을 소수 보존한다. 전체 subtree를 강제로 싣지는 않는다.
        if "supplemental-closure" in str(row.get("role") or ""):
            for score, line_position in sorted(
                    anchors, key=lambda value: (-value[0], value[1]))[:3]:
                selected[line_position] = max(selected.get(line_position, 0), score)
                mandatory.add(f"{evidence_id}:L{line_position + 1}")
        for line_position, score in selected.items():
            clean_path = provenance_path(str(row.get("path") or ""))[0]
            # subtree 첫 줄은 경로를 되풀이하며 상위 장·절 연혁을 포함할 수 있다.
            # 해당 조문 연혁으로 오인되지 않게 정규화한 경로로 교체한다.
            raw_line = clean_path if line_position == 0 else lines[line_position]
            line = " ".join(raw_line.split())[:900]
            card = {
                "quote_id": f"{evidence_id}:L{line_position + 1}",
                "evidence_id": evidence_id,
                "document": str(row.get("document") or ""),
                "path": clean_path,
                "deterministic_role": _line_role(line),
                "references": sorted(_units(line)),
                "requirement_kinds": sorted({
                    span.kind for span in requirements.extract(line)}),
                "connection_role": str((row.get("typed_connection") or {}).get(
                    "connection_role") or "unclassified_context"),
                "conclusion_eligible": bool((row.get("typed_connection") or {}).get(
                    "conclusion_eligible")),
                "support_eligible": bool((row.get("typed_connection") or {}).get(
                    "support_eligible")),
                "evidence_tier": str((row.get("typed_connection") or {}).get(
                    "evidence_tier") or "C_context_only"),
                "text": line,
            }
            candidates.append((score, evidence_position, line_position, card))

    # 전체 조문은 inventory에 이미 남아 있다. clause 예산은 강제 보존 블록과
    # 전역 관련도에 집중해 핵심 원문이 무관 조문의 대표 카드에 밀리지 않게 한다.
    chosen: dict[str, tuple[int, int, int, dict[str, Any]]] = {}
    primary = [candidate for candidate in candidates
               if candidate[3]["quote_id"] in primary_mandatory]
    for candidate in sorted(primary, key=lambda value: (value[1], value[2])):
        if len(chosen) >= max_cards:
            break
        chosen[candidate[3]["quote_id"]] = candidate
    forced = [candidate for candidate in candidates
              if candidate[3]["quote_id"] in mandatory
              and candidate[3]["quote_id"] not in chosen]
    for candidate in sorted(forced, key=lambda value: (-value[0], value[1], value[2])):
        if len(chosen) >= max_cards:
            break
        chosen[candidate[3]["quote_id"]] = candidate
    for candidate in sorted(candidates, key=lambda value: (-value[0], value[1], value[2])):
        if len(chosen) >= max_cards:
            break
        chosen.setdefault(candidate[3]["quote_id"], candidate)
    ordered = sorted(chosen.values(), key=lambda value: (-value[0], value[1], value[2]))
    return [{**card, "priority": score} for score, _ep, _lp, card in ordered]


COMPILER_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "object",
            "properties": {
                "documents": {"type": "array", "items": {"type": "string"}},
                "subjects": {"type": "array", "items": {"type": "string"}},
                "acts_or_objects": {"type": "array", "items": {"type": "string"}},
                "time": {"type": "string"},
                "requested_output": {"type": "string"},
            },
            "required": ["documents", "subjects", "acts_or_objects", "time",
                         "requested_output"],
            "additionalProperties": False,
        },
        "requested_items": {"type": "array", "items": {"type": "string"}},
        "rules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "role": {"type": "string", "enum": [
                    "governing", "definition", "condition", "exception",
                    "delegation_or_reference", "temporal", "calculation",
                    "procedure", "effect", "context"]},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "modality": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "quote_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["rule_id", "role", "subject", "predicate", "object",
                         "conditions", "modality", "evidence_ids", "quote_ids"],
            "additionalProperties": False,
        }},
        "application": {
            "type": "object",
            "properties": {
                "matched_rules": {"type": "array", "items": {"type": "string"}},
                "exceptions_applied": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string",
                           "enum": ["supported", "conditional", "insufficient"]},
                "conclusion": {"type": "string"},
                "support_quote_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["matched_rules", "exceptions_applied", "unresolved", "status",
                         "conclusion", "support_quote_ids"],
            "additionalProperties": False,
        },
        "conflicts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scope", "requested_items", "rules", "application", "conflicts"],
    "additionalProperties": False,
}


COMPILER_SYSTEM = """너는 한국 법률 원문을 좌표가 붙은 명제표로 컴파일한다.
답변 문장을 쓰지 말고 다음 순서로 판단한다.

1. 질문의 문서·시장·주체·행위·대상·시점과 요청 항목을 고정한다.
2. inventory는 전체 회수 목록이고 clause cards는 그중 판단 문언이다. 높은 검색
   순위가 법적 우선순위는 아니다. evidence_tier와 아래 정책에 따라 증거를
   사용한다. direct_typed_companion는 표시된 관계 범위 안에서만 적용한다.
3. 지배규범과 정의, 요건, 본문·단서·예외·재예외, 위임·준용, 시점, 산식,
   절차, 효과를 분리한다. 특별규정과 명시적 배제는 일반규정보다 먼저 적용한다.
4. '하여야 한다/할 수 있다', '각각/합산', '또는/모두', '중 적은/큰 금액',
   이상/초과/이하/미만을 바꾸지 않는다.
5. 조문에 열거된 주체의 자격을 비슷한 업무용어만으로 확장하지 않는다. 포섭 근거가
   없으면 unresolved에 남긴다. 반대로 원문이 직접 답하면 불필요하게 회피하지 않는다.
6. ancestor_heading_history는 상위 편·장·절·관의 연혁이지 해당 조문 연혁이 아니다.
7. 모든 rule과 conclusion은 실제 quote_id를 가져야 한다. 카드에 없는 문언이나
   일반 법률지식은 만들지 않는다."""


STRICT_EVIDENCE_POLICY = """[evidence policy: strict]
A_governing만 context 이외 rule과 matched_rules·conclusion의 법적 근거로 쓴다.
B_candidate_support와 C_context_only는 context rule만 만든다."""


THREE_TIER_EVIDENCE_POLICY = """[evidence policy: three-tier shadow]
A_governing은 명시적 간선이나 질문 지정으로 연결된 지배규범 후보다.
B_candidate_support는 인용·구조·조문 제목이 쟁점과 맞는 검토 후보다. B는 카드
원문의 주체·행위·대상·시점이 질문과 직접 일치할 때만 rule과 결론에 쓴다.
제목이나 유사 용어만 맞으면 context로 남긴다. B는 명시적 배제·단서·준용 문언 없이
A의 요건이나 예외를 바꾸거나 시장·문서·주체 범위를 확장하지 못한다.
C_context_only는 context rule만 만든다."""


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


RENDER_SYSTEM = """너는 검증된 법률 명제표만으로 최종 답변을 작성한다.
질문이 요구한 항목에 결론부터 답하고, 조건·예외·수치·기간·산식이 요청되면 빠짐없이
쓴다. 명제표의 unresolved를 임의로 메우지 않는다. supported면 명확히 결론 내리고,
conditional이면 필요한 조건을 정확히 붙이며, insufficient일 때만 부족한 연결을
짧게 밝힌다. 표 밖의 조문·수치·사실을 추가하지 말고 내부 quote_id는 답변 문장에
쓰지 않는다."""


def validate_compilation(compiled: dict[str, Any] | None,
                         inventory: list[dict[str, Any]],
                         cards: list[dict[str, Any]], *,
                         evidence_policy: str = "strict") -> dict[str, Any]:
    errors = []
    if not isinstance(compiled, dict):
        return {"valid": False, "errors": ["compiler_failed"]}
    evidence_ids = {row["evidence_id"] for row in inventory}
    eligibility_key = ("support_eligible" if evidence_policy == "three-tier"
                       else "conclusion_eligible")
    eligibility = {
        row["evidence_id"]: bool((row.get("typed_connection") or {}).get(
            eligibility_key)) for row in inventory}
    quote_ids = {row["quote_id"] for row in cards}
    rule_ids = set()
    for rule in compiled.get("rules") or []:
        rid = str(rule.get("rule_id") or "")
        if not rid or rid in rule_ids:
            errors.append("invalid_or_duplicate_rule_id")
        rule_ids.add(rid)
        if not rule.get("quote_ids"):
            errors.append(f"{rid}:missing_quote")
        if any(str(value) not in quote_ids for value in rule.get("quote_ids") or []):
            errors.append(f"{rid}:invalid_quote")
        if any(str(value) not in evidence_ids for value in rule.get("evidence_ids") or []):
            errors.append(f"{rid}:invalid_evidence")
        used = [str(value) for value in rule.get("evidence_ids") or []]
        if (rule.get("role") != "context" and used
                and not any(eligibility.get(value, False) for value in used)):
            errors.append(f"{rid}:ineligible_context_promoted")
    application = compiled.get("application") or {}
    if any(str(value) not in rule_ids for value in application.get("matched_rules") or []):
        errors.append("application_invalid_rule")
    if (application.get("status") != "insufficient"
            and not application.get("support_quote_ids")):
        errors.append("application_missing_quote")
    if any(str(value) not in quote_ids
           for value in application.get("support_quote_ids") or []):
        errors.append("application_invalid_quote")
    card_eligibility = {row["quote_id"]: bool(row.get(eligibility_key))
                        for row in cards}
    used_quotes = [str(value) for value in application.get("support_quote_ids") or []]
    if used_quotes and not any(card_eligibility.get(value, False)
                               for value in used_quotes):
        errors.append("application_only_ineligible_context")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors))}


def compile_legal_propositions(llm, question: str,
                               evidence: list[dict[str, Any]], *,
                               evidence_policy: str = "strict") -> dict[str, Any]:
    if evidence_policy not in {"strict", "three-tier"}:
        raise ValueError(f"unknown evidence policy: {evidence_policy}")
    inventory = evidence_inventory(evidence)
    cards = build_clause_cards(question, evidence)
    safe_inventory = []
    for row in inventory:
        safe = dict(row)
        safe["ancestor_heading_history"] = (
            ["상위 경로 연혁 존재—해당 조문 신설·개정일이 아님"]
            if row.get("ancestor_heading_history") else [])
        safe_inventory.append(safe)
    user = (f"[질문]\n{question}\n\n[전체 회수 inventory]\n"
            f"{json.dumps(safe_inventory, ensure_ascii=False)}\n\n[clause cards]\n"
            f"{json.dumps(cards, ensure_ascii=False)}")
    policy_prompt = (THREE_TIER_EVIDENCE_POLICY
                     if evidence_policy == "three-tier"
                     else STRICT_EVIDENCE_POLICY)
    compiled = llm.structured(
        "rag.answer.haiku.legal_proposition_compile.experimental",
        f"{COMPILER_SYSTEM}\n\n{policy_prompt}", user, COMPILER_SCHEMA, max_tokens=5000,
        effort="low", model=HAIKU_MODEL)
    validation = validate_compilation(
        compiled, inventory, cards, evidence_policy=evidence_policy)
    return {"inventory": inventory, "cards": cards, "compiled": compiled,
            "validation": validation, "evidence_policy": evidence_policy}


def render_compilation(llm, question: str, bundle: dict[str, Any],
                       fallback: str) -> dict[str, Any]:
    if not (bundle.get("validation") or {}).get("valid"):
        return {"action": "keep", "answer": fallback,
                "guard": "invalid_compilation", **bundle}
    compiled = bundle["compiled"]
    application = compiled.get("application") or {}
    # shadow 교정은 보수적으로만 연다. 모델이 스스로 미해결 쟁점이나 충돌을
    # 기록했다면 status 라벨을 supported로 잘못 올렸더라도 기존 답을 보존한다.
    if (application.get("status") != "supported"
            or application.get("unresolved")
            or compiled.get("conflicts")):
        return {"action": "keep", "answer": fallback,
                "guard": "unresolved_or_conflicted", **bundle}
    wanted = set()
    for rule in compiled.get("rules") or []:
        wanted.update(str(value) for value in rule.get("quote_ids") or [])
    wanted.update(str(value) for value in
                  (compiled.get("application") or {}).get("support_quote_ids") or [])
    support_cards = [row for row in bundle["cards"] if row["quote_id"] in wanted]
    user = (f"[질문]\n{question}\n\n[검증된 법률 명제표]\n"
            f"{json.dumps(compiled, ensure_ascii=False)}\n\n[인용 원문 카드]\n"
            f"{json.dumps(support_cards, ensure_ascii=False)}")
    raw = llm.structured(
        "rag.answer.haiku.legal_proposition_render.experimental",
        RENDER_SYSTEM, user, RENDER_SCHEMA, max_tokens=3000,
        effort="low", model=HAIKU_MODEL)
    valid_quotes = {row["quote_id"] for row in support_cards}
    answer = str((raw or {}).get("answer") or "").strip()
    support = [str(value) for value in (raw or {}).get("support_quote_ids") or []
               if str(value) in valid_quotes]
    accepted = bool((raw or {}).get("answerable")) and bool(answer) and bool(support)
    if accepted and should_preserve_interpretive_qualification(fallback, answer):
        return {"action": "keep", "answer": fallback,
                "guard": "preserve_interpretive_qualification",
                "render": raw, **bundle}
    if (accepted and _claims_direct_rule_absence(fallback)
            and not _claims_direct_rule_absence(answer)):
        return {"action": "keep", "answer": fallback,
                "guard": "preserve_direct_rule_absence",
                "render": raw, **bundle}
    return {
        "action": "repair" if accepted else "keep",
        "answer": answer if accepted else fallback,
        "guard": "accepted_compilation" if accepted else "invalid_render",
        "render": raw, **bundle,
    }


def compiled_answer(llm, question: str, evidence: list[dict[str, Any]],
                    fallback: str, *, evidence_policy: str = "strict") \
        -> dict[str, Any]:
    bundle = compile_legal_propositions(
        llm, question, evidence, evidence_policy=evidence_policy)
    return render_compilation(llm, question, bundle, fallback)
