"""법률 질문의 명제 구조화와 근거 한정 3값 판정.

현재 운영 RAG에는 배선하지 않은 실험 모듈이다. 검색 전에는 질문만으로 IssueFrame을
만들고, 검색 뒤에는 실제 조문 원문만으로 그 명제가 지지되는지 판정한다. 조문에 어떤
단어가 없다는 사실을 곧바로 반대 결론으로 바꾸지 않도록 `not_determined`를 독립된
결과로 유지하는 것이 목적이다.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


INTERPRETERS = (
    "literal",
    "definition_scope",
    "subsumption",
    "exception",
    "temporal",
    "delegation_hierarchy",
    "cross_statute",
    "sanction_strict",
    "evidence_sufficiency",
)

INTERPRETER_RULES = {
    "literal": "문언의 주체·행위·목적어·의무양태·법적 효과를 원문 표현대로 비교한다.",
    "definition_scope": (
        "정의 문언이 있으면 그 정의의 관할(이 법·이 편·이 장)을 확인하고, 정의가 "
        "없으면 다른 개념과 임의로 동일시하지 않는다."),
    "subsumption": (
        "질문 사실 또는 개념이 조문 요건에 포함되는지 연결 고리를 각각 확인하고, "
        "중간 연결이 비면 not_determined로 둔다."),
    "exception": (
        "원칙과 예외·단서를 분리하고 예외의 모든 적용 조건과 시간 범위를 보존한다."),
    "temporal": (
        "시행일·개정일·부칙·경과조치와 기준 시점을 확인하고 서로 다른 시점을 섞지 않는다."),
    "delegation_hierarchy": (
        "상위법의 위임 근거·범위와 하위 규정의 내용을 분리하고 위임 범위를 넘겨 읽지 않는다."),
    "cross_statute": (
        "다른 법령의 용어·효과를 가져오려면 명시적 준용·정의 또는 체계적 연결 근거를 요구한다."),
    "sanction_strict": (
        "형벌·과태료·제재의 주체와 구성요건은 엄격히 읽고 불리한 유추를 하지 않는다."),
    "evidence_sufficiency": (
        "검색된 원문에 질문 용어가 없다는 사실과 법체계 전체에 요건이 없다는 결론을 구별한다."),
}

FRAME_SYSTEM = """너는 법률 질문을 검색 가능한 판단 문제로 바꾸는 쟁점 구조화기다.
아직 조문을 보지 않았으므로 질문에 없는 법령명·법적 사실·중간 개념을 만들지 않는다.
답을 내리지 말고 질문자가 확인하려는 명제를 평서문으로 보존한다.

분해 규칙:
1. proposition은 질문의 긍정·부정·의무 양태를 바꾸지 않은 검증 대상 문장이다.
2. known_facts에는 질문에 명시된 사실만 둔다.
3. disputed_relations에는 결론을 위해 증명해야 하는 개념 관계만 둔다.
4. decision_terms에는 판단에서 서로 연결해야 하는 질문 속 핵심 표현을 글자 그대로
   복사한다. 질문에 없는 표현은 넣지 않는다.
5. candidate_interpreters는 후보이며 복수 선택할 수 있다. 질문만으로 확정하지 않는다.
6. retrieval_needs에는 어떤 종류의 직접 규정·정의·예외·관련법이 필요한지만 적고
   구체적인 법령명이나 결론을 추측하지 않는다."""

FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "question_type": {
            "type": "string",
            "enum": ["proposition_verification", "rule_explanation",
                     "scope_classification", "procedure", "other"],
        },
        "proposition": {"type": "string"},
        "subject": {"type": "string"},
        "requested_legal_effect": {"type": "string"},
        "known_facts": {"type": "array", "items": {"type": "string"}},
        "disputed_relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "left": {"type": "string"},
                    "relation": {"type": "string"},
                    "right": {"type": "string"},
                },
                "required": ["left", "relation", "right"],
                "additionalProperties": False,
            },
        },
        "decision_terms": {"type": "array", "items": {"type": "string"}},
        "candidate_interpreters": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTERPRETERS)},
        },
        "retrieval_needs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_type", "proposition", "subject",
                 "requested_legal_effect", "known_facts", "disputed_relations",
                 "decision_terms", "candidate_interpreters", "retrieval_needs"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = """너는 질문 명제와 제공된 법령 원문의 논리적 관계만 판정한다.
외부 지식이나 관행을 사용하지 말고 evidence 목록 밖의 법을 알고 있다고 가정하지 않는다.

판정 규칙:
1. proposition_verification은 원문이 명제를 직접 지지하면 entailed, 반대 내용을 직접
   규정하면 contradicted, 어느 쪽도 아니거나 개념 연결이 비면 not_determined다.
2. rule_explanation은 원문이 질문이 요구한 기준과 조건을 직접 제공하면 entailed,
   질문의 전제를 직접 부정하면 contradicted, 기준이 빠지면 not_determined다.
3. 질문 용어가 원문에 없다는 사실은 contradicted의 근거가 아니다.
4. 서로 다른 법률 용어를 정의·준용·연결 근거 없이 동일하다고 보지 않는다.
5. contradicted에는 명제의 반대 내용을 담은 원문 span id가 반드시 필요하다.
6. rule_findings에는 원문을 다시 쓰지 말고 제공된 span_id를 선택한다. 인용문은 코드가
   span id로 원문에서 복원한다.
7. controlling_evidence_ids에는 결론을 직접 규율하는 근거만 넣는다.
8. 연결 근거가 없으면 missing_links에 무엇이 더 필요한지 적고 결론을 예/아니오로
   확장하지 않는다."""

JUDGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["entailed", "contradicted", "not_determined"],
        },
        "controlling_evidence_ids": {
            "type": "array", "items": {"type": "string"},
        },
        "rule_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "span_id": {"type": "string"},
                    "relation_to_proposition": {
                        "type": "string",
                        "enum": ["supports", "contradicts", "context"],
                    },
                },
                "required": ["statement", "evidence_id", "span_id",
                             "relation_to_proposition"],
                "additionalProperties": False,
            },
        },
        "missing_links": {"type": "array", "items": {"type": "string"}},
        "rejected_inferences": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["verdict", "controlling_evidence_ids", "rule_findings",
                 "missing_links", "rejected_inferences", "explanation"],
    "additionalProperties": False,
}


TYPED_FRAME_SYSTEM = """너는 법률 질문을 답변 유형과 원문 확인 항목으로 분해한다.
아직 조문을 보지 않았으므로 답을 추측하거나 질문에 없는 법령·요건을 만들지 않는다.

question_type 계약:
- proposition_verification: 어떤 명제가 맞는지, 의무가 있는지, 허용되는지 검증
- rule_explanation: 기준·요건·기간·계산식·예외·개정 내용을 설명
- scope_classification: 둘 이상의 범주·기간·기관 중 어디에 속하는지 분류
- procedure: 누가 무엇을 어디에 언제 어떤 순서로 하는지 설명

answer_requirements에는 답변에서 원문으로 채워야 하는 항목을 원자적으로 적는다.
질문에 수치·기간·계산 기준·예외·복수 대안이 있으면 각각 별도 항목으로 보존한다.
explicit_alternatives에는 질문이 비교하거나 선택하도록 명시한 후보만 넣는다.
safety_sensitive_relations에는 서로 같은 개념인지, 포함되는지, 다른 법의 개념을
가져와야 하는지처럼 원문 밖 연결을 추측하면 위험한 관계만 적는다."""

TYPED_FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "question_type": {
            "type": "string",
            "enum": ["proposition_verification", "rule_explanation",
                     "scope_classification", "procedure"],
        },
        "proposition": {"type": "string"},
        "decision_terms": {"type": "array", "items": {"type": "string"}},
        "candidate_interpreters": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTERPRETERS)},
        },
        "answer_requirements": {"type": "array", "items": {"type": "string"}},
        "explicit_alternatives": {"type": "array", "items": {"type": "string"}},
        "safety_sensitive_relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "left": {"type": "string"},
                    "relation": {"type": "string"},
                    "right": {"type": "string"},
                },
                "required": ["left", "relation", "right"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["question_type", "proposition", "decision_terms",
                 "candidate_interpreters", "answer_requirements",
                 "explicit_alternatives", "safety_sensitive_relations"],
    "additionalProperties": False,
}

TYPED_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["answered", "partial", "not_determined"],
        },
        "conclusion": {"type": "string"},
        "answer": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "string"},
                    "statement": {"type": "string"},
                    "evidence_id": {"type": "string"},
                    "span_id": {"type": "string"},
                },
                "required": ["requirement_id", "statement", "evidence_id",
                             "span_id"],
                "additionalProperties": False,
            },
        },
        "missing_requirement_ids": {
            "type": "array", "items": {"type": "string"},
        },
        "rejected_inferences": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "conclusion", "answer", "findings",
                 "missing_requirement_ids", "rejected_inferences"],
    "additionalProperties": False,
}

TYPED_ANSWER_COMMON = """너는 제공된 법령 원문만으로 답하는 법률 답변기다.
외부 지식이나 evidence 밖의 조문을 사용하지 않는다. findings에는 제공된
requirement_id와 evidence/span id만 선택한다. 원문 인용문은 다시 쓰지 않는다.

공통 규칙:
1. 질문의 결론을 첫 문장에 직접 답하고, 그 뒤 요건과 근거를 설명한다.
2. 수치·기간·계산식·예외·시간 범위는 원문에 있는 내용을 빠뜨리거나 합치지 않는다.
3. 검색 결과는 법체계 전체가 아니다. 원문에 표현이 없다는 이유로 반대 결론을 내리지 않는다.
4. 답 일부만 확인되면 확인된 부분을 구체적으로 답하고 status=partial로 둔다.
5. 원문으로 아무 요구사항도 채울 수 없을 때만 status=not_determined로 둔다.
6. answer는 사용자에게 바로 보여 줄 완결된 한국어 답변이어야 한다."""

TYPED_ANSWER_RULES = {
    "rule_explanation": """[규칙 설명 계약]
- 각 answer requirement에 대응하는 기준·요건·수치·기간·예외를 findings로 채운다.
- '규정되어 있다'로 끝내지 말고 질문이 묻는 실제 기준을 설명한다.
- 원칙과 예외, 서로 다른 기준일이나 계산 요소를 별도 문장으로 보존한다.""",
    "scope_classification": """[범위 분류 계약]
- explicit alternatives가 있으면 각 후보가 적용되는지 비교한 뒤 최종 범주를 밝힌다.
- '각각', '또는', 단서, 제외 문언을 보존하고 합산·개별 또는 포함·제외를 뒤집지 않는다.
- 원문이 직접 분류하는 경우 불필요한 정의 요구로 유보하지 않는다. 다만 원문 밖 개념의
  동치나 포함 관계가 필요하면 그 부분만 partial 또는 not_determined로 둔다.""",
    "procedure": """[절차 계약]
- 행위자, 행위, 상대방·제출처, 기한, 순서, 예외를 원문에 나온 범위에서 단계별로 쓴다.
- 제출처나 주체가 회수되지 않았으면 다른 절차 내용으로 대체하지 않는다.""",
}

DRAFT_REVIEW_SYSTEM = """너는 기존 법률 답변 초안을 원문에 맞게 보존·수정하는 검토자다.
draft는 증거가 아니라 수정 대상이다. evidence 밖의 사실·조문·수치를 남기지 않는다.

1. 초안이 원문과 맞고 질문에 직접 답하면 표현을 불필요하게 바꾸거나 유보하지 않는다.
2. requirements를 기준으로 결론, 수치, 기간, 계산 기준, 예외를 확인해 빠진 핵심만 보충한다.
3. 원문이 일부만 답하면 확인된 부분은 구체적으로 남기고 status=partial로 둔다.
4. 질문 용어가 원문에 없다는 사실만으로 '아니다', '의무가 없다', '허용되지 않는다'고
   결론내리지 않는다.
5. 명제 검증에서 서로 다른 법률 개념의 동치·포함 관계가 결론에 필요하면 정의·준용·직접
   연결 문언을 요구한다. 연결이 없으면 그 명제를 확정하지 않는다.
6. 반대로 원문이 질문의 요건·효과를 직접 규정하면 형식적인 정의 부족을 이유로 유보하지 않는다.
7. findings에는 requirement_id와 evidence/span id만 쓰고 인용문을 만들지 않는다.
8. answer는 검토 설명이 아니라 사용자에게 바로 보여 줄 최종 한국어 답변이다."""


def structure_question(llm, question: str) -> dict[str, Any] | None:
    out = llm.structured(
        "rag.legal_issue_frame", FRAME_SYSTEM, f"[질문]\n{question}",
        FRAME_SCHEMA, max_tokens=1400, effort="low")
    if out is None:
        return None
    packed_question = _pack(question)
    out["decision_terms"] = list(dict.fromkeys(
        str(value).strip() for value in out.get("decision_terms") or []
        if len(_pack(value)) >= 2 and _pack(value) in packed_question
    ))
    # 질문 형식의 명시 신호는 LLM 분류보다 우선한다. "어떻게"는 규칙 설명,
    # "반드시/이어야 하는가"는 명제 검증이다. 나머지는 모델 판정을 유지한다.
    packed = _pack(question)
    if "어떻게" in question:
        out["question_type"] = "rule_explanation"
    elif ("이어야하는가" in packed or "반드시" in question
          or "해야하는가" in packed):
        out["question_type"] = "proposition_verification"
    return out


def structure_question_typed(llm, question: str) -> dict[str, Any] | None:
    """후속 실험용: 답변 유형과 원문으로 채울 항목을 한 번에 만든다."""
    out = llm.structured(
        "rag.legal_issue_typed_frame", TYPED_FRAME_SYSTEM, f"[질문]\n{question}",
        TYPED_FRAME_SCHEMA, max_tokens=1800, effort="low")
    if out is None:
        return None
    packed_question = _pack(question)
    out["decision_terms"] = list(dict.fromkeys(
        str(value).strip() for value in out.get("decision_terms") or []
        if len(_pack(value)) >= 2 and _pack(value) in packed_question
    ))
    requirements = list(dict.fromkeys(
        str(value).strip() for value in out.get("answer_requirements") or []
        if str(value).strip()
    ))
    if not requirements:
        requirements = ["질문에 직접 답하는 법적 기준 또는 결론"]
    out["answer_requirements"] = requirements[:8]
    out["requirement_cards"] = [
        {"id": f"R{position}", "requirement": value}
        for position, value in enumerate(out["answer_requirements"], 1)
    ]
    packed = _pack(question)
    if "어떻게" in question:
        out["question_type"] = "rule_explanation"
    elif "어디에이행" in packed:
        out["question_type"] = "procedure"
    elif any(signal in packed for signal in (
            "어디에해당", "중어디", "어느것이", "어느기관인가",
            "어느기관이결정", "포함되는가", "몇명인가", "합산기준")):
        out["question_type"] = "scope_classification"
    return out


def answer_evidence_by_type(llm, frame: dict[str, Any],
                            evidence: list[dict[str, Any]]) \
        -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """명제는 3값 guard, 나머지는 유형별 완전성 계약으로 답한다."""
    if frame.get("question_type") == "proposition_verification":
        raw = judge_evidence(llm, frame, evidence)
        return raw, verify_judgment(raw, evidence, frame)

    question_type = str(frame.get("question_type") or "rule_explanation")
    system = TYPED_ANSWER_COMMON + "\n\n" + TYPED_ANSWER_RULES.get(
        question_type, TYPED_ANSWER_RULES["rule_explanation"])
    methods = "\n".join(
        f"- {row['name']}: {row['rule']}"
        for row in interpreter_instructions(frame)
    )
    if methods:
        system += "\n\n[활성 해석 규칙]\n" + methods
    payload = {
        "question_type": question_type,
        "proposition": frame.get("proposition"),
        "requirements": frame.get("requirement_cards") or [],
        "explicit_alternatives": frame.get("explicit_alternatives") or [],
        "safety_sensitive_relations": frame.get("safety_sensitive_relations") or [],
        "evidence": prepare_evidence(evidence),
    }
    raw = llm.structured(
        f"rag.legal_issue_{question_type}_answer", system,
        json.dumps(payload, ensure_ascii=False, indent=2),
        TYPED_ANSWER_SCHEMA, max_tokens=4000, effort="high")
    return raw, verify_typed_answer(raw, frame, evidence)


def verify_typed_answer(answer: dict[str, Any] | None,
                        frame: dict[str, Any],
                        evidence: list[dict[str, Any]]) \
        -> dict[str, Any] | None:
    """유형별 답변의 requirement/evidence/span을 닫힌 목록으로 검증한다."""
    if answer is None:
        return None
    out = copy.deepcopy(answer)
    prepared = prepare_evidence(evidence)
    evidence_ids = {str(row.get("id")) for row in prepared}
    spans = {
        str(span.get("id")): (str(row.get("id")), str(span.get("text") or ""))
        for row in prepared for span in row.get("spans") or []
    }
    requirement_ids = {
        str(row.get("id")) for row in frame.get("requirement_cards") or []
    }
    findings = []
    for row in out.get("findings") or []:
        requirement_id = str(row.get("requirement_id") or "")
        evidence_id = str(row.get("evidence_id") or "")
        span_id = str(row.get("span_id") or "")
        resolved = spans.get(span_id)
        if (requirement_id not in requirement_ids
                or evidence_id not in evidence_ids
                or resolved is None or resolved[0] != evidence_id):
            continue
        findings.append({**row, "quote": resolved[1]})
    out["findings"] = findings
    covered = {str(row["requirement_id"]) for row in findings}
    missing = [value for value in requirement_ids if value not in covered]
    missing += [str(value) for value in out.get("missing_requirement_ids") or []
                if str(value) in requirement_ids and str(value) not in covered]
    out["missing_requirement_ids"] = sorted(set(missing))
    status = str(out.get("status") or "not_determined")
    if not findings:
        status = "not_determined"
    elif status == "not_determined" or out["missing_requirement_ids"]:
        status = "partial"
    elif status not in {"answered", "partial"}:
        status = "partial"
    out["status"] = status
    out["covered_requirement_ids"] = sorted(covered)
    return out


def review_draft_by_type(llm, frame: dict[str, Any],
                         evidence: list[dict[str, Any]], draft: str) \
        -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """기존 합성 초안을 질문 유형별 요구사항과 닫힌 원문으로 교정한다."""
    question_type = str(frame.get("question_type") or "rule_explanation")
    system = DRAFT_REVIEW_SYSTEM + "\n\n" + TYPED_ANSWER_RULES.get(
        question_type, TYPED_ANSWER_RULES["rule_explanation"])
    payload = {
        "question_type": question_type,
        "proposition": frame.get("proposition"),
        "requirements": frame.get("requirement_cards") or [],
        "explicit_alternatives": frame.get("explicit_alternatives") or [],
        "safety_sensitive_relations": frame.get("safety_sensitive_relations") or [],
        "draft": str(draft or ""),
        "evidence": prepare_evidence(evidence),
    }
    raw = llm.structured(
        f"rag.legal_issue_{question_type}_draft_review", system,
        json.dumps(payload, ensure_ascii=False, indent=2),
        TYPED_ANSWER_SCHEMA, max_tokens=4000, effort="high")
    checked = verify_typed_answer(raw, frame, evidence)
    return raw, guard_reviewed_proposition(checked, frame, evidence)


def guard_reviewed_proposition(result: dict[str, Any] | None,
                               frame: dict[str, Any],
                               evidence: list[dict[str, Any]]) \
        -> dict[str, Any] | None:
    """원문의 침묵을 부정 결론으로 바꾼 전형적 문장만 결정론적으로 차단한다."""
    if (result is None
            or frame.get("question_type") != "proposition_verification"
            or result.get("status") == "not_determined"):
        return result
    evidence_text = _pack(" ".join(
        str(row.get("original_text") or "") for row in evidence))
    missing_terms = [
        str(term) for term in frame.get("decision_terms") or []
        if _pack(term) not in evidence_text
    ]
    answer = _pack(str(result.get("answer") or ""))
    # 두 패턴은 oracle에서 실제 관찰한 닫힌세계 오류의 문장 구조다.
    # 단순한 조건부 부정("5% 미만이면 발생하지 않는다")까지 막지 않는다.
    absence_to_negative = bool(
        re.search(r"(?:명시|규정)(?:하|되어|되어있)?지않.{0,50}(?:필요(?:가)?없|아니)", answer)
        or re.search(r"(?:명시|규정)(?:하|되어|되어있)?지않으므로", answer)
        or ("조정되지않" in answer and "조정" in missing_terms)
        or re.search(r"규정(?:이)?없.{0,40}(?:따라서|그러므로).{0,40}(?:아니|없)", answer)
    )
    decision_terms = [str(term) for term in frame.get("decision_terms") or []]
    all_decision_terms_absent = bool(
        decision_terms and len(missing_terms) == len(decision_terms)
        and result.get("status") == "answered"
    )
    if not missing_terms or not (absence_to_negative or all_decision_terms_absent):
        result["guard_downgraded"] = False
        result["guard_missing_decision_terms"] = missing_terms
        return result
    out = copy.deepcopy(result)
    out["status"] = "not_determined"
    out["guard_downgraded"] = True
    out["guard_missing_decision_terms"] = missing_terms
    rejected = list(out.get("rejected_inferences") or [])
    rejected.append(
        "원문에 질문 핵심 용어가 없는데 개념 연결 없이 확정 결론으로 확장한 초안")
    out["rejected_inferences"] = list(dict.fromkeys(rejected))
    return out


def render_reviewed_answer(frame: dict[str, Any], result: dict[str, Any] | None) -> str:
    """검증된 초안 수정본. partial의 한계 설명은 검토자가 답 안에 직접 쓴다."""
    proposition = str(frame.get("proposition") or "질문 사항")
    if not result or result.get("status") == "not_determined":
        answer = f"이번에 회수된 근거만으로는 ‘{proposition}’을 확정할 수 없습니다."
        findings = (result or {}).get("findings") or []
        if findings:
            quote = str(findings[0].get("quote") or "").strip()
            evidence_id = str(findings[0].get("evidence_id") or "").strip()
            if quote:
                answer += f" 확인된 문언은 [{evidence_id}] ‘{quote[:3000]}’입니다."
        missing = list((result or {}).get("guard_missing_decision_terms") or [])
        if missing:
            answer += (" 다만 질문 핵심 표현("
                       + ", ".join(map(str, missing))
                       + ")과 위 문언의 법적 개념 사이 연결 근거가 더 필요합니다.")
        return answer
    return str(result.get("answer") or result.get("conclusion") or "").strip()


def render_typed_answer(frame: dict[str, Any], result: dict[str, Any] | None) -> str:
    """유형별 답변을 렌더링하되 명제 검증은 기존 보수 경계를 유지한다."""
    if frame.get("question_type") == "proposition_verification":
        return render_answer(frame, result)
    proposition = str(frame.get("proposition") or "질문 사항")
    if not result or result.get("status") == "not_determined":
        return f"이번에 회수된 근거만으로는 ‘{proposition}’에 답할 수 없습니다."
    answer = str(result.get("answer") or result.get("conclusion") or "").strip()
    if result.get("status") != "partial":
        return answer
    cards = {str(row.get("id")): str(row.get("requirement"))
             for row in frame.get("requirement_cards") or []}
    missing = [cards[value] for value in result.get("missing_requirement_ids") or []
               if value in cards]
    caveat = (" 다만 이번에 회수된 근거만으로 확인되지 않은 사항은 "
              + "; ".join(missing) + "입니다.") if missing else ""
    return answer + caveat


def interpreter_instructions(frame: dict[str, Any]) -> list[dict[str, str]]:
    """IssueFrame이 선택한 닫힌 해석기만 실행 규칙으로 만든다."""
    out = []
    for name in frame.get("candidate_interpreters") or []:
        key = str(name)
        if key in INTERPRETER_RULES and not any(row["name"] == key for row in out):
            out.append({"name": key, "rule": INTERPRETER_RULES[key]})
    return out


def prepare_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """조·항 원문에 닫힌 span id를 붙인다.

    현재 oracle의 근거 단위가 이미 항 단위이므로 한 항을 한 span으로 둔다. 나중에
    호·목 또는 문장 경계가 구조 스토어에 생기면 이 함수의 분할만 더 세밀하게 한다.
    """
    out = []
    for row in evidence:
        evidence_id = str(row.get("id") or "")
        body = str(row.get("original_text") or "")
        prepared = {key: value for key, value in row.items()
                    if key != "original_text"}
        prepared["spans"] = [{"id": f"{evidence_id}:S1", "text": body}]
        out.append(prepared)
    return out


def judge_evidence(llm, frame: dict[str, Any], evidence: list[dict[str, Any]]) \
        -> dict[str, Any] | None:
    active = interpreter_instructions(frame)
    methods = "\n".join(f"- {row['name']}: {row['rule']}" for row in active)
    system = JUDGE_SYSTEM
    if methods:
        system += "\n\n[이번 질문에서 활성화된 해석기]\n" + methods
    payload = {"issue_frame": frame, "active_interpreters": active,
               "evidence": prepare_evidence(evidence)}
    return llm.structured(
        "rag.legal_issue_judge", system,
        json.dumps(payload, ensure_ascii=False, indent=2),
        JUDGMENT_SCHEMA, max_tokens=2000, effort="low")


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def verify_judgment(judgment: dict[str, Any] | None,
                    evidence: list[dict[str, Any]],
                    frame: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """닫힌 evidence/span id를 검사하고 인용문을 원문에서 복원한다."""
    if judgment is None:
        return None
    out = copy.deepcopy(judgment)
    prepared = prepare_evidence(evidence)
    bodies = {str(row.get("id")): row for row in prepared}
    spans = {
        str(span.get("id")): (str(row.get("id")), str(span.get("text") or ""))
        for row in prepared for span in row.get("spans") or []
    }
    valid_findings = []
    for row in out.get("rule_findings") or []:
        evidence_id = str(row.get("evidence_id") or "")
        span_id = str(row.get("span_id") or "")
        if not evidence_id or evidence_id not in bodies:
            continue
        resolved = spans.get(span_id)
        if resolved is None or resolved[0] != evidence_id:
            continue
        valid_findings.append({**row, "quote": resolved[1]})
    out["rule_findings"] = valid_findings
    out["controlling_evidence_ids"] = list(dict.fromkeys(
        str(value) for value in out.get("controlling_evidence_ids") or []
        if str(value) in bodies
    ))

    verdict = str(out.get("verdict") or "not_determined")
    relation_needed = "supports" if verdict == "entailed" else (
        "contradicts" if verdict == "contradicted" else "")
    if relation_needed and not any(
            row.get("relation_to_proposition") == relation_needed
            for row in valid_findings):
        out["verdict"] = "not_determined"
        links = list(out.get("missing_links") or [])
        links.append("판정 극성을 뒷받침하는 검증 가능한 원문 span")
        out["missing_links"] = list(dict.fromkeys(links))
        out["guard_downgraded"] = True
    else:
        out["verdict"] = verdict if verdict in {
            "entailed", "contradicted", "not_determined"} else "not_determined"
        out["guard_downgraded"] = False

    # supports/contradicts 라벨은 모델 판단이므로 그 자체로 증명이 아니다. 해당
    # 극성으로 사용한 원문 span에 질문의 핵심 표현이 모두 있어야 최소 연결이 선다.
    # 질문에 있던 문자열만 허용된 decision_terms라 검색 결과의 침묵을 부정으로
    # 오해하는 cm-036 유형을 결정론적으로 차단한다.
    if (out["verdict"] in {"entailed", "contradicted"} and frame
            and frame.get("question_type") == "proposition_verification"):
        relation = "supports" if out["verdict"] == "entailed" else "contradicts"
        polar_text = _pack(" ".join(
            str(row.get("quote") or "") for row in valid_findings
            if row.get("relation_to_proposition") == relation
        ))
        missing_terms = [
            str(term) for term in frame.get("decision_terms") or []
            if _pack(term) not in polar_text
        ]
        if missing_terms:
            out["verdict"] = "not_determined"
            links = list(out.get("missing_links") or [])
            links.append(
                "원문 span에 없는 질문 핵심 용어와 조문 용어의 법적 연결 근거: "
                + ", ".join(missing_terms))
            out["missing_links"] = list(dict.fromkeys(links))
            out["guard_downgraded"] = True
            out["guard_missing_decision_terms"] = missing_terms
        else:
            out["guard_missing_decision_terms"] = []
    return out


def render_answer(frame: dict[str, Any], judgment: dict[str, Any] | None) -> str:
    """not_determined를 예/아니오로 바꾸지 않는 보수적 답변 렌더러."""
    proposition = str(frame.get("proposition") or "질문 명제")
    if not judgment:
        return f"제공된 근거만으로는 ‘{proposition}’을 판단할 수 없습니다."
    verdict = judgment.get("verdict")
    if verdict != "not_determined":
        return str(judgment.get("explanation") or "").strip()

    findings = judgment.get("rule_findings") or []
    observed = ""
    if findings:
        quote = str(findings[0].get("quote") or "").strip()
        evidence_id = str(findings[0].get("evidence_id") or "").strip()
        if quote:
            observed = f" 확인된 문언은 [{evidence_id}] ‘{quote}’입니다."
    missing = [str(value).strip() for value in judgment.get("missing_links") or []
               if str(value).strip()]
    need = f" 추가로 확인할 사항은 {'; '.join(missing)}입니다." if missing else ""
    return (f"제공된 근거만으로는 ‘{proposition}’을 확정할 수 없습니다."
            f"{observed}{need}")
