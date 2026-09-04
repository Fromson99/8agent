"""답변 후단의 문언 대조형 verifier/repair 실험.

운영 ``answer.synthesize``에는 연결하지 않는다. 검색 결과와 기존 초안을 고정한 채
후단 교정이 의미 정확도를 올리는지 재생할 수 있도록 격리한 모듈이다.
"""

from __future__ import annotations

import json
from typing import Any


ERROR_TYPES = (
    "conclusion",
    "condition",
    "exception",
    "modality",
    "quantity_formula",
    "temporal",
    "scope",
    "omission",
    "irrelevant_basis",
    "unsupported_inference",
)


REPAIR_SYSTEM = """너는 법률 답변의 최종 문언 검증자다.
질문, 검색으로 회수된 법령 원문, 기존 초안을 받는다. 외부 지식과 기준답변은 없다.
목표는 더 그럴듯한 글이 아니라 원문에 맞는 결론·조건·예외를 완전하게 답하는 것이다.

검증 순서:
1. 먼저 질문이 요구하는 결론과 세부 항목을 원자적으로 나눈다.
2. 초안을 보지 않은 것처럼 원문에서 각 항목의 직접 근거를 찾는다.
3. 주체, 대상 행위, 의무 양태(하여야/할 수 있다), 수치와 산식, 기준 시점,
   본문·단서·예외·재예외, 준용·배제 관계를 각각 확인한다.
4. 그 독립 판단과 초안을 대조한다. 초안의 일부가 맞아도 요청 항목이 빠졌거나 핵심
   수치·조건 하나가 틀리면 repair다.

문언 규칙:
- '각각', '또는', '및', '중 적은/큰 금액', 괄호, 단서의 연결 범위를 보존한다.
- 서로 다른 항·호, 법령, 시장, 회사 유형, 기준일을 섞지 않는다.
- 일반 규정과 특별 규정이 함께 있으면 어떤 요건에서 어느 규정이 적용되는지 밝힌다.
- 원문에 직접 답이 있으면 불필요하게 판단 불가로 회피하지 않는다.
- 반대로 회수 원문에 용어가 없다는 이유만으로 법체계 전체에 규정이 없다고 단정하지
  않는다. 열거가 질문 범위를 완전히 닫거나 원문이 직접 부정할 때만 부재를 확정한다.
- 초안이 '별도 조정 규정 없음' 또는 '직접 규정 미확인'이라고 답한 경우, 일반 산식이
  경제적으로 비슷한 효과를 낸다는 추론만으로 명시 규정이 있다고 뒤집지 않는다.
  질문이 말한 조정·차감·예외를 원문이 직접 규정해야 긍정으로 고칠 수 있다.
- 문서의 개정·신설일과 조문 내용상의 기간을 혼동하지 않는다.
- 검색 결과에는 무관한 구역도 섞일 수 있다. 질문의 대상 법령·조문과 다른 근거를
  중심 근거로 쓰지 않는다.
- 질문이 명시적으로 요구하지 않은 관련 규정까지 덧붙이지 않는다. 초안이 질문의
  결론과 요청 세부를 충족했다면, 단지 더 자세히 쓸 수 있다는 이유로 omission이나
  repair를 선택하지 않는다.

action 계약:
- keep: 모든 요청 항목의 결론과 핵심 세부가 원문에 맞다. 이때 초안을 그대로 보존한다.
- repair: 결론, 조건, 예외, 수치·산식, 시점, 범위, 강행성 또는 핵심 누락을 고친다.
- insufficient: 원문만으로 결론을 확정할 수 없다. 무엇이 확인되고 무엇이 비는지 답한다.

각 check의 evidence_ids와 support_ids는 제공된 E번호만 사용한다. corrected_answer는
결론을 먼저 쓰고 필요한 근거 설명을 이어 쓰되, E번호나 '컨텍스트'라는 내부 표현은
사용하지 않는다. 초안의 오류를 사용자에게 설명하지 말고 바로잡힌 답만 쓴다.
checks는 질문이 요구한 항목만 최대 8개, finding과 reason은 각각 짧은 한 문장으로 쓴다.
corrected_answer는 원칙적으로 1,500자 이내로 작성한다."""


REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["satisfied", "contradicted", "unknown",
                                 "not_applicable"],
                    },
                    "finding": {"type": "string"},
                    "evidence_ids": {
                        "type": "array", "items": {"type": "string"},
                    },
                },
                "required": ["item", "status", "finding", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "draft_errors": {
            "type": "array",
            "items": {"type": "string", "enum": list(ERROR_TYPES)},
        },
        "action": {
            "type": "string", "enum": ["keep", "repair", "insufficient"],
        },
        "reason": {"type": "string"},
        "support_ids": {
            "type": "array", "items": {"type": "string"},
        },
        "corrected_answer": {"type": "string"},
    },
    "required": ["checks", "draft_errors", "action", "reason",
                 "support_ids", "corrected_answer"],
    "additionalProperties": False,
}


def _evidence_payload(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{
        "id": str(row.get("id") or ""),
        "document": str(row.get("document") or ""),
        "path": str(row.get("path") or ""),
        "role": str(row.get("role") or ""),
        "text": str(row.get("original_text") or ""),
    } for row in evidence]


def _claims_direct_rule_absence(text: str) -> bool:
    compact = " ".join(str(text or "").split())
    subjects = ("명시적 규정", "명문 규정", "직접 규정", "직접 명시")
    negatives = ("없", "미확인", "확인되지", "찾을 수 없")
    return any(subject in compact for subject in subjects) and any(
        negative in compact for negative in negatives)


def should_preserve_interpretive_qualification(draft: str,
                                               corrected: str) -> bool:
    """문언 해석이라는 유보를 후단이 확정 결론으로 바꾸는 것을 막는다."""
    qualified = ("것으로 해석됩니다", "라고 해석됩니다", "로 해석됩니다",
                 "해석될 수 있습니다", "문언상")
    source = " ".join(str(draft or "").split())
    target = " ".join(str(corrected or "").split())
    return any(value in source for value in qualified) and not any(
        value in target for value in qualified)


def verify_and_repair(llm, question: str, evidence: list[dict[str, Any]],
                      draft: str, *, model: str | None = None,
                      effort: str = "medium") -> dict[str, Any]:
    """초안을 검증·교정하고 닫힌 evidence id guard를 적용한다.

    호출 실패, 빈 교정문, 근거 id 위조는 보수적으로 기존 초안을 유지한다.
    ``keep``도 모델이 재작성한 문장이 아니라 입력 초안을 그대로 반환한다.
    """
    valid_ids = {str(row.get("id") or "") for row in evidence}
    user = (
        f"[질문]\n{question}\n\n"
        "[회수 원문]\n"
        + json.dumps(_evidence_payload(evidence), ensure_ascii=False)
        + f"\n\n[기존 초안 — 위 원문 독립 판단 후 마지막에 대조]\n{draft}"
    )
    raw = llm.structured(
        "rag.answer.final_verifier_repair.experimental",
        REPAIR_SYSTEM,
        user,
        REPAIR_SCHEMA,
        max_tokens=8000,
        effort=effort,
        model=model,
    )
    if raw is None:
        return {
            "action": "keep", "answer": draft, "raw": None,
            "guard": "llm_failed_keep_draft",
        }

    out = dict(raw)
    action = str(out.get("action") or "keep")
    support_ids = list(dict.fromkeys(
        str(value) for value in out.get("support_ids") or []
        if str(value) in valid_ids
    ))
    invalid_ids = sorted({
        str(value) for value in out.get("support_ids") or []
        if str(value) not in valid_ids
    })
    checks = []
    for row in out.get("checks") or []:
        item = dict(row)
        item["evidence_ids"] = list(dict.fromkeys(
            str(value) for value in row.get("evidence_ids") or []
            if str(value) in valid_ids
        ))
        checks.append(item)
    out["checks"] = checks
    out["support_ids"] = support_ids

    corrected = str(out.get("corrected_answer") or "").strip()
    unresolved = any(str(row.get("status")) == "unknown" for row in checks)
    if (action != "keep" and unresolved
            and _claims_direct_rule_absence(draft)):
        action, answer, guard = "keep", draft, "unresolved_absence_keep_draft"
    elif (action != "keep"
          and should_preserve_interpretive_qualification(draft, corrected)):
        action, answer, guard = (
            "keep", draft, "interpretive_qualification_keep_draft")
    elif action == "keep":
        answer, guard = draft, "keep_exact_draft"
    elif not corrected:
        action, answer, guard = "keep", draft, "empty_repair_keep_draft"
    elif invalid_ids or (evidence and not support_ids):
        action, answer, guard = "keep", draft, "invalid_support_keep_draft"
    else:
        answer, guard = corrected, "accepted_repair"
    out["action"] = action
    return {
        "action": action,
        "answer": answer,
        "raw": out,
        "guard": guard,
        "invalid_support_ids": invalid_ids,
    }
