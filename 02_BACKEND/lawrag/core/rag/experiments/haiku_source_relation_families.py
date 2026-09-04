"""법률 기능별로 분리한 Haiku 원문 증명형 관계 추출 shadow 모듈."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL
from lawrag.core.rag.experiments.haiku_source_relations import (
    RELATION_SCHEMA,
    RELATION_SYSTEM,
    build_relation_cards,
    validate_relations,
)


RELATION_FAMILIES: dict[str, tuple[str, ...]] = {
    "scope_and_actor": ("APPLIES_TO_MARKET", "GOVERNS_ACTOR"),
    "normative_link": ("EXCEPTION_TO", "IMPLEMENTS"),
    "semantic_and_temporal": ("DEFINED_BY", "CURRENT_VERSION_OF"),
}

FAMILY_GUIDANCE = {
    "scope_and_actor": """이번 호출에서는 적용 시장과 규율 주체만 전수 조사한다.
문서가 직접 특정하는 시장과, 조문 문장의 문법상 의무·권한·절차 주체를 각각 찾는다.
단순 언급 대상·수범자의 상대방·문서 제목으로 추정한 주체는 만들지 않는다.""",
    "normative_link": """이번 호출에서는 조문 사이의 규범 연결만 전수 조사한다.
명시적 조문 표면형과 예외/배제 또는 위임/세부사항 문언을 동시에 확인한다.
다른 법률의 준수·참조, 같은 주제, 사실상 보충 관계는 만들지 않는다.""",
    "semantic_and_temporal": """이번 호출에서는 정의 연결과 실제 버전 연결만 전수 조사한다.
정의는 source의 정확한 용어 사용과 target의 같은 용어 정의문을 함께 인용한다.
버전은 같은 문서·조문 좌표의 서로 다른 실제 메타데이터가 모두 있을 때만 만든다.""",
}


def family_schema(family: str) -> dict[str, Any]:
    """공통 필드 계약을 보존하면서 relation_type만 family에 닫는다."""
    if family not in RELATION_FAMILIES:
        raise ValueError(f"unknown relation family: {family}")
    schema = deepcopy(RELATION_SCHEMA)
    relation = schema["properties"]["relations"]["items"]
    relation["properties"]["relation_type"]["enum"] = list(
        RELATION_FAMILIES[family])
    return schema


def family_system(family: str) -> str:
    if family not in RELATION_FAMILIES:
        raise ValueError(f"unknown relation family: {family}")
    allowed = ", ".join(RELATION_FAMILIES[family])
    return (
        RELATION_SYSTEM
        + "\n\n[이번 호출의 닫힌 관계군]\n"
        + FAMILY_GUIDANCE[family]
        + f"\n허용 relation_type은 {allowed}뿐이다. 다른 관계는 출력하지 않는다."
    )


def compile_relation_family(llm, inventory: list[dict[str, Any]],
                            cards: list[dict[str, Any]], family: str) \
        -> dict[str, Any]:
    """질문이나 사례 식별자 없이 한 관계군만 Haiku로 컴파일한다."""
    user = ("[evidence inventory]\n"
            f"{json.dumps(inventory, ensure_ascii=False)}\n\n[quote cards]\n"
            f"{json.dumps(cards, ensure_ascii=False)}")
    raw = llm.structured(
        f"rag.data.haiku.source_relation_family.{family}.experimental",
        family_system(family), user, family_schema(family), max_tokens=6000,
        effort="low", model=HAIKU_MODEL)
    validation = validate_relations(raw, inventory, cards)
    return {"family": family, "raw": raw, "validation": validation}


def compile_source_relation_families(
        llm, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """세 관계군을 독립 호출하고 공통 deterministic guard 뒤에 합친다."""
    inventory, cards = build_relation_cards(evidence)
    results = [compile_relation_family(llm, inventory, cards, family)
               for family in RELATION_FAMILIES]
    published = [relation for result in results
                 for relation in result["validation"]["published"]]
    rejected = [relation for result in results
                for relation in result["validation"]["rejected"]]
    unresolved = [value for result in results
                  for value in (result.get("raw") or {}).get("unresolved") or []]
    return {
        "inventory": inventory,
        "cards": cards,
        "family_results": results,
        "published": published,
        "rejected": rejected,
        "unresolved": unresolved,
    }
