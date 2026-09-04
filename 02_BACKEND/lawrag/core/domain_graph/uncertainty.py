"""도메인 그래프의 불확실성 계약.

``active``는 소비 가능한 상태일 뿐 사실임을 뜻하지 않는다. 원문 파싱, 규칙 기반
추출, LLM 파생, 일괄 승인과 개별 검토는 모두 틀릴 수 있으므로 생성 방식과 검토
수준을 서로 다른 필드로 보존한다.
"""

from __future__ import annotations

from typing import Any


CONTRACT_VERSION = 1
UNCERTAINTY_POLICY = "may_be_wrong"


def review_state(*, approved_by: str = "", explicit: str = "",
                 status: str = "") -> str:
    """승인 주체를 과장하지 않는 닫힌 검토 상태로 정규화한다."""
    if explicit:
        return explicit
    approved_by = str(approved_by or "").strip()
    if approved_by == "user:force-all":
        return "batch_accepted"
    if approved_by.startswith("llm:"):
        return "model_reviewed"
    if approved_by:
        # 이름에 user가 들어 있어도 실제 개별 검토 여부는 알 수 없다.
        return "declared_approved"
    if status in ("rejected", "deprecated"):
        return status
    return "unreviewed"


def claim_metadata(*, evidence_type: str, claim_status: str = "candidate",
                   approved_by: str = "", explicit_review_state: str = "",
                   confidence: Any = None, consumer_policy: str = "corroborate",
                   **extra: Any) -> dict[str, Any]:
    """모든 의미 주장에 붙이는 최소 공통 메타데이터를 만든다.

    confidence가 없다는 사실도 정보이므로 임의의 기본 점수를 만들지 않는다.
    """
    out: dict[str, Any] = {
        "uncertainty_contract": CONTRACT_VERSION,
        "uncertainty_policy": UNCERTAINTY_POLICY,
        "claim_status": claim_status,
        "review_state": review_state(
            approved_by=approved_by, explicit=explicit_review_state,
            status=claim_status),
        "evidence_type": evidence_type,
        "consumer_policy": consumer_policy,
    }
    if confidence not in (None, ""):
        out["confidence"] = confidence
    out.update(extra)
    return out


def graph_contract() -> dict[str, Any]:
    """DB 전체에 한 번 기록하는 기본 해석 계약."""
    return {
        "version": CONTRACT_VERSION,
        "default_policy": UNCERTAINTY_POLICY,
        "active_means": "eligible_for_consumption_not_truth",
        "confidence_means": "source_specific_estimate_not_probability_of_truth",
        "review_states": [
            "unreviewed", "batch_accepted", "model_reviewed",
            "declared_approved", "human_verified", "rejected", "deprecated",
        ],
        "consumer_rule": (
            "semantic claims require corroboration; MAY_* edges must never be "
            "treated as dispositive legal authority"
        ),
    }
