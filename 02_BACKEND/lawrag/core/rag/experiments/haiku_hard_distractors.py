"""Haiku 법률 hard-distractor 내성 실험의 순수 조립 부품.

운영 검색이나 답변 배선을 바꾸지 않는다. 동결 회수 결과를 다음 통제 조건으로
재배열한다: 골든만, 무작위 잡음, 법률형 hard distractor 앞/뒤, 보조근거, 전체.
후보 역할 자체는 Haiku가 별도 실험 호출에서 판정한다.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL


LABELS = ("SUPPORTIVE", "HARD_DISTRACTOR", "EASY_IRRELEVANT")
SUBTYPES = (
    "SAME_TOPIC_OTHER_RULE",
    "OTHER_MARKET",
    "OTHER_ACTOR",
    "OTHER_TIME_VERSION",
    "GENERAL_SPECIAL_MISMATCH",
    "CONDITION_EXCEPTION_CONFUSION",
    "AUTHORITY_PROCEDURE_CONFUSION",
    "TERMINOLOGY_OVERLAP",
    "OTHER",
    "NONE",
)
VARIANTS = (
    "gold_only",
    "random_noise_after",
    "hard_after",
    "hard_before",
    "supportive_after",
    "full_original",
)

CLASSIFIER_SYSTEM = (
    "너는 법률 RAG의 방해근거를 분류하는 감사자다. 모든 판단은 제공된 원문만으로 "
    "한다. [골든 직접근거]는 질문의 정답 조문 좌표이고, [후보]는 같은 검색에서 "
    "함께 회수됐지만 골든 좌표가 아닌 구역이다. 후보 각각을 정확히 한 역할로 "
    "분류한다.\n"
    "SUPPORTIVE: 골든의 적용조건·예외·정의·위임·산식 등으로, 빼면 답이 법적으로 "
    "불완전하거나 틀릴 실질적 가능성이 있다. 단순히 같은 주제인 것은 부족하다.\n"
    "HARD_DISTRACTOR: 질문과 표면상 매우 관련 있어 답변 모델이 지배규범으로 "
    "오인할 수 있지만, 시장·행위자·시점·법규범 단계·일반/특별·권한/절차 등이 "
    "달라 현재 질문의 직접 결론 근거는 아니다.\n"
    "EASY_IRRELEVANT: 위 둘이 아니며 답에 실질적으로 필요하지 않은 잡음이다.\n"
    "risk는 오답 유도 위험 0~3이다. 골든 문구와 후보 문구를 비교하고, 관련성만 "
    "높다는 이유로 SUPPORTIVE를 주지 마라. 후보 ID를 빠뜨리거나 새로 만들지 마라."
)


def classifier_schema(candidate_ids: Iterable[str]) -> dict:
    ids = list(candidate_ids)
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "label": {"type": "string", "enum": list(LABELS)},
                        "subtype": {"type": "string", "enum": list(SUBTYPES)},
                        # Anthropic structured output의 지원 JSON Schema 부분집합에는
                        # integer minimum/maximum이 없다. 범위는 prompt와 후처리로 강제한다.
                        "risk": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "label", "subtype", "risk", "reason"],
                    "additionalProperties": False,
                },
            },
            "case_note": {"type": "string"},
        },
        "required": ["rows", "case_note"],
        "additionalProperties": False,
    }


def _render_evidence(rows: Iterable[dict]) -> str:
    blocks = []
    for row in rows:
        blocks.append(
            f"[{row.get('id')}] source={row.get('experiment_source', 'SAME_RETRIEVAL')} "
            f"{row.get('document')} ▸ {row.get('path')}\n"
            f"{row.get('original_text', '')}"
        )
    return "\n\n".join(blocks)


def classifier_user(question: str, gold: list[dict], candidates: list[dict]) -> str:
    return (
        f"[질문]\n{question}\n\n"
        f"[골든 직접근거]\n{_render_evidence(gold)}\n\n"
        f"[분류할 후보]\n{_render_evidence(candidates)}\n\n"
        "후보를 모두 한 번씩 분류하라. reason은 후보당 2문장 이내로 쓴다."
    )


def normalize_labels(candidates: list[dict], output: dict | None) -> list[dict]:
    """중복·누락·스키마 이탈을 보수적으로 정규화한다."""
    allowed = {str(row.get("id")): row for row in candidates}
    seen: dict[str, dict] = {}
    for value in (output or {}).get("rows") or []:
        evidence_id = str(value.get("id") or "")
        if evidence_id not in allowed or evidence_id in seen:
            continue
        label = str(value.get("label") or "")
        subtype = str(value.get("subtype") or "")
        seen[evidence_id] = {
            "id": evidence_id,
            "label": label if label in LABELS else "EASY_IRRELEVANT",
            "subtype": subtype if subtype in SUBTYPES else "OTHER",
            "risk": max(0, min(3, int(value.get("risk") or 0))),
            "reason": str(value.get("reason") or "")[:800],
            "classifier_missing": False,
        }
    rows = []
    for candidate in candidates:
        evidence_id = str(candidate.get("id"))
        rows.append(seen.get(evidence_id) or {
            "id": evidence_id,
            "label": "EASY_IRRELEVANT",
            "subtype": "OTHER",
            "risk": 0,
            "reason": "Haiku 분류 출력에서 누락되어 보수적으로 잡음 처리",
            "classifier_missing": True,
        })
    return rows


def ranked_ids(labels: list[dict], label: str, limit: int = 3) -> list[str]:
    positions = {str(row.get("id")): pos for pos, row in enumerate(labels)}
    selected = [row for row in labels if row.get("label") == label]
    selected.sort(key=lambda row: (-int(row.get("risk") or 0),
                                   positions[str(row.get("id"))]))
    return [str(row["id"]) for row in selected[:limit]]


def deterministic_random_ids(case_id: str, pool: list[dict], limit: int = 3) -> list[str]:
    """실험 재현을 위한 해시 순서. 같은 사례의 후보는 호출자가 pool에서 뺀다."""
    ranked = sorted(
        pool,
        key=lambda row: hashlib.sha256(
            f"{case_id}|{row.get('pool_id', row.get('id'))}".encode("utf-8")
        ).hexdigest(),
    )
    return [str(row.get("pool_id", row.get("id"))) for row in ranked[:limit]]


def build_variants(gold: list[dict], candidates: list[dict], labels: list[dict],
                   random_rows: list[dict], limit: int = 3) -> dict[str, list[dict]]:
    by_id = {str(row.get("id")): row for row in candidates}
    hard = [by_id[value] for value in ranked_ids(labels, "HARD_DISTRACTOR", limit)
            if value in by_id]
    supportive = [by_id[value] for value in ranked_ids(labels, "SUPPORTIVE", limit)
                  if value in by_id]
    full = sorted(list(gold) + list(candidates),
                  key=lambda row: int(row.get("experiment_order") or 10**9))
    return {
        "gold_only": list(gold),
        "random_noise_after": list(gold) + list(random_rows[:limit]),
        "hard_after": list(gold) + hard,
        "hard_before": hard + list(gold),
        "supportive_after": list(gold) + supportive,
        "full_original": full,
    }


def injected_count(variant: str, rows: list[dict], gold_count: int) -> int:
    if variant == "full_original":
        return max(0, len(rows) - gold_count)
    return max(0, len(rows) - gold_count)


__all__ = [
    "CLASSIFIER_SYSTEM", "HAIKU_MODEL", "LABELS", "SUBTYPES", "VARIANTS",
    "build_variants", "classifier_schema", "classifier_user",
    "deterministic_random_ids", "injected_count", "normalize_labels", "ranked_ids",
]
