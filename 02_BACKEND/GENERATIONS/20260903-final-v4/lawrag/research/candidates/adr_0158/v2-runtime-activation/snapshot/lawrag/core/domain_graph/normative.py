"""법률 규범의 닫힌 양태·기능 축.

Frame 추출기가 이미 판정한 ``mode``와 ``function``을 참고 메타데이터에만
남기지 않고 Tier-1 Concept/Assertion 역할로 올리기 위한 정본 사양이다. 이 축은
질문과 조문의 주제어를 대신하지 않는다. ``소각``·``자기주식`` 같은 내용 Concept이
Assertion을 연 뒤, 의무/허용 또는 근거/제한의 법적 기능을 구별하는 facet이다.
"""

from __future__ import annotations

import re


FACET_ROLE_BY_AXIS = {"mode": "MODALITY", "function": "FUNCTION"}
FACET_TYPES = frozenset({"modality", "norm_function"})


NORMATIVE_CONCEPTS: dict[str, dict[str, dict]] = {
    "mode": {
        "의무": {
            "id": "concept:norm.modality.obligation",
            "label": "의무",
            "type": "modality",
            "aliases": [
                "하여야 한다", "해야 한다", "하여야 하는가", "해야 하는가",
                "의무가 있다", "의무인가", "필수", "반드시",
            ],
        },
        "금지": {
            "id": "concept:norm.modality.prohibition",
            "label": "금지",
            "type": "modality",
            "aliases": [
                "하여서는 아니 된다", "해서는 안 된다", "할 수 없다",
                "금지되는가", "하면 안 되는가",
            ],
        },
        "허용": {
            "id": "concept:norm.modality.permission",
            "label": "허용",
            "type": "modality",
            "aliases": [
                "할 수 있다", "할 수 있는가", "가능하다", "가능한가",
                "허용되는가", "선택인가",
            ],
        },
        "절차": {
            "id": "concept:norm.modality.procedure",
            "label": "절차 문형",
            "type": "modality",
            "aliases": ["절차를 거쳐", "승인을 받아", "인가를 받아", "심의를 거쳐"],
        },
        "위임": {
            "id": "concept:norm.modality.delegation",
            "label": "위임 문형",
            "type": "modality",
            "aliases": ["위임한다", "위임할 수 있다", "대통령령으로 정한다"],
        },
        "간주": {
            "id": "concept:norm.modality.deeming",
            "label": "간주",
            "type": "modality",
            "aliases": ["로 본다", "으로 본다", "간주한다", "추정한다"],
        },
        "정의": {
            "id": "concept:norm.modality.definition",
            "label": "정의 문형",
            "type": "modality",
            "aliases": ["이란", "뜻한다", "말한다", "정의한다"],
        },
        "기타": {
            "id": "concept:norm.modality.other",
            "label": "기타 문형",
            "type": "modality",
            "aliases": [],
        },
    },
    "function": {
        "근거·권한": {
            "id": "concept:norm.function.authority",
            "label": "근거·권한",
            "type": "norm_function",
            "aliases": ["법적 근거", "권한", "결정 권한", "어느 기관이 결정"],
        },
        "제한": {
            "id": "concept:norm.function.restriction",
            "label": "제한",
            "type": "norm_function",
            "aliases": ["제한되는가", "금지 근거", "제한 요건"],
        },
        "절차": {
            "id": "concept:norm.function.procedure",
            "label": "절차",
            "type": "norm_function",
            "aliases": ["절차", "신고 절차", "제출 절차", "승인 절차"],
        },
        "위임": {
            "id": "concept:norm.function.delegation",
            "label": "위임",
            "type": "norm_function",
            "aliases": ["위임", "위임할 수 있는가", "수임", "위임 근거"],
        },
        "정의": {
            "id": "concept:norm.function.definition",
            "label": "정의",
            "type": "norm_function",
            "aliases": ["정의", "무엇을 말하는가", "의미", "뜻"],
        },
        "효과": {
            "id": "concept:norm.function.effect",
            "label": "법률효과",
            "type": "norm_function",
            "aliases": ["법률효과", "효과", "혜택", "산입되는가", "포함되는가"],
        },
        "기타": {
            "id": "concept:norm.function.other",
            "label": "기타 규범기능",
            "type": "norm_function",
            "aliases": [],
        },
    },
}


def concept_spec(axis: str, value: object) -> dict | None:
    """Frame의 닫힌 분류값에 해당하는 정본 Concept 사양."""
    return NORMATIVE_CONCEPTS.get(str(axis), {}).get(str(value or "").strip())


def concept_id_for(axis: str, value: object) -> str:
    spec = concept_spec(axis, value)
    return str(spec["id"]) if spec else ""


def all_specs() -> tuple[dict, ...]:
    return tuple(spec for values in NORMATIVE_CONCEPTS.values()
                 for spec in values.values())


def query_mentions_comparison(question: str) -> bool:
    packed = re.sub(r"\s+", "", question or "")
    return any(value in packed for value in (
        "인가", "아닌가", "구분", "차이", "비교", "각각", "여부",
    ))


def promote_registry_blob(blob: dict, *, approved_by: str) -> dict:
    """이미 승인된 Frame 분류를 canonical 역할 간선으로 결정론적으로 승격한다.

    새 법률 의미를 추론하지 않는다. active Assertion의 ``candidate_basis``에 이미
    보존된 닫힌 ``mode/function`` 값만 같은 닫힌 Concept에 연결한다.
    """
    concepts = blob.setdefault("concepts", [])
    existing = {
        str(row.get("id") or "") if str(row.get("id") or "").startswith("concept:")
        else f"concept:{row.get('id')}"
        for row in concepts if row.get("id")
    }
    added_concepts = 0
    for spec in all_specs():
        cid = str(spec["id"])
        if cid in existing:
            continue
        concepts.append({
            "id": cid.removeprefix("concept:"),
            "label": spec["label"], "type": spec["type"],
            "aliases": list(spec.get("aliases") or ()),
            "version": 1, "status": "active", "approved_by": approved_by,
            "candidate_basis": {
                "knowledge_grade": 1, "source": "normative_closed_axis",
            },
        })
        existing.add(cid)
        added_concepts += 1

    updated_assertions = 0
    role_edges = {role: 0 for role in FACET_ROLE_BY_AXIS.values()}
    for assertion in blob.get("assertions") or []:
        if assertion.get("status") != "active":
            continue
        basis = assertion.get("candidate_basis") or {}
        roles = assertion.setdefault("roles", {})
        changed = False
        for axis, role in FACET_ROLE_BY_AXIS.items():
            cid = concept_id_for(axis, basis.get(axis))
            if not cid or roles.get(role) == [cid]:
                continue
            roles[role] = [cid]
            role_edges[role] += 1
            changed = True
        if changed:
            updated_assertions += 1
    return {
        "added_concepts": added_concepts,
        "updated_assertions": updated_assertions,
        "role_edges": role_edges,
    }


def promote_candidate_blob(blob: dict, *, approved_by: str) -> dict:
    """후속 재승인에서도 facet이 사라지지 않도록 후보 원장을 같이 이관한다."""
    concepts = blob.setdefault("concepts", [])
    existing = {
        str(row.get("id") or "") if str(row.get("id") or "").startswith("concept:")
        else f"concept:{row.get('id')}"
        for row in concepts if row.get("id")
    }
    added_concepts = 0
    for spec in all_specs():
        cid = str(spec["id"])
        if cid in existing:
            continue
        concepts.append({
            "id": cid.removeprefix("concept:"),
            "label": spec["label"], "type": spec["type"],
            "aliases": list(spec.get("aliases") or ()),
            "version": 1, "candidate_status": "approved",
            "candidate_basis": {
                "knowledge_grade": 1, "source": "normative_closed_axis",
            },
            "approval": {
                "decision": "approve", "confidence": "high",
                "reason": "사용자가 승인한 닫힌 규범 facet",
                "validation": "통과", "by": approved_by,
            },
        })
        existing.add(cid)
        added_concepts += 1

    updated_assertions = 0
    role_edges = {role: 0 for role in FACET_ROLE_BY_AXIS.values()}
    for assertion in blob.get("assertions") or []:
        basis = assertion.get("candidate_basis") or {}
        roles = assertion.setdefault("roles", {})
        changed = False
        for axis, role in FACET_ROLE_BY_AXIS.items():
            cid = concept_id_for(axis, basis.get(axis))
            if not cid or roles.get(role) == [cid]:
                continue
            roles[role] = [cid]
            role_edges[role] += 1
            changed = True
        if changed:
            updated_assertions += 1
    return {
        "added_concepts": added_concepts,
        "updated_assertions": updated_assertions,
        "role_edges": role_edges,
    }
