"""Haiku로 명시적 EXCEPTION_TO만 표적 복구하는 shadow 컴파일러."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL
from lawrag.core.rag.experiments.haiku_source_relations import (
    RELATION_SCHEMA, build_relation_cards, validate_relations,
)


EXCEPTION_SYSTEM = """너는 한국 법률 원문의 닫힌 후보 메뉴에서 EXCEPTION_TO만 판정한다.
질문에 답하지 말고 메뉴 밖의 source, target, quote를 만들지 않는다.

EXCEPTION_TO는 source의 적용요건·효과가 명시적으로 인용된 target 조문의 일반 규율을
배제하거나 변경하는 관계다. 다음은 관계가 아니다.
- target의 단서를 시행령에서 정의·구체화하는 위임 관계
- 단순 인용, 절차상 참조, 같은 주제, 다른 대상에 붙은 단서
- source가 target 규율을 그대로 반복하거나 준수하게 하는 경우

각 후보의 source_text를 문법적으로 판정한다. 실제 예외일 때만 relation을 출력한다.
source_id/target_id/quote_ids는 후보 그대로, target_value는 target_path 그대로 쓴다.
defined_term은 빈 문자열, confidence는 확실하면 high, 애매하면 medium이다.
허용 relation_type은 EXCEPTION_TO 하나뿐이고 같은 source-target은 한 번만 출력한다."""


def exception_schema() -> dict[str, Any]:
    schema = deepcopy(RELATION_SCHEMA)
    schema["properties"]["relations"]["items"]["properties"][
        "relation_type"]["enum"] = ["EXCEPTION_TO"]
    return schema


def _packed(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def _article_surface(value: str) -> set[str]:
    return {_packed(match.group(0)) for match in re.finditer(
        r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?", str(value or ""))}


_EXCEPTION_SIGNAL = re.compile(
    r"적용하지\s*아니|제외|예외|에도\s*불구하고|다만|단서|그러하지\s*아니")


def _explicit_target_override(article: str, text: str) -> bool:
    """인용 target 자체가 override 문언의 목적어인 강한 방향성만 인정한다."""
    packed = _packed(text)
    return bool(article and re.search(
        re.escape(article)
        + r".{0,80}(?:에도불구하고|을적용하지아니|를적용하지아니|"
          r"은적용하지아니|는적용하지아니)",
        packed,
    ))


def build_exception_candidates(inventory: list[dict[str, Any]],
                               cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """동일 quote의 조문 표면형과 예외 신호로 recall-oriented 닫힌 메뉴를 만든다."""
    candidates, seen = [], set()
    by_article: dict[str, list[dict[str, Any]]] = {}
    for target in inventory:
        for article in _article_surface(target.get("path")):
            by_article.setdefault(article, []).append(target)
    for card in cards:
        if card.get("kind") != "source":
            continue
        text = str(card.get("text") or "")
        if not _EXCEPTION_SIGNAL.search(text):
            continue
        source_id = str(card.get("evidence_id") or "")
        for article in _article_surface(text):
            if not _explicit_target_override(article, text):
                continue
            for target in by_article.get(article, []):
                target_id = str(target.get("evidence_id") or "")
                key = (source_id, target_id, str(card.get("quote_id") or ""))
                if source_id == target_id or key in seen:
                    continue
                seen.add(key)
                source = next((row for row in inventory
                               if row.get("evidence_id") == source_id), {})
                candidates.append({
                    "candidate_id": f"C{len(candidates) + 1}",
                    "source_id": source_id,
                    "source_document": str(source.get("document") or ""),
                    "source_path": str(source.get("path") or ""),
                    "target_id": target_id,
                    "target_document": str(target.get("document") or ""),
                    "target_path": str(target.get("path") or ""),
                    "quote_id": str(card.get("quote_id") or ""),
                    "source_text": text,
                })
    return candidates


def validate_exception_rescue(raw: dict[str, Any] | None,
                              inventory: list[dict[str, Any]],
                              cards: list[dict[str, Any]],
                              candidates: list[dict[str, Any]] | None = None) \
        -> dict[str, Any]:
    """공통 proof guard 뒤에 target과 예외 문언의 quote 단위 공기성을 요구한다."""
    normalized_raw = deepcopy(raw or {"relations": [], "unresolved": []})
    for relation in normalized_raw.get("relations") or []:
        match = next((candidate for candidate in candidates or []
                      if candidate["source_id"] == relation.get("source_id")
                      and candidate["target_id"] == relation.get("target_id")
                      and candidate["quote_id"] in relation.get("quote_ids", [])), None)
        if match:
            relation["target_value"] = match["target_path"]
    base = validate_relations(normalized_raw, inventory, cards)
    by_id = {row["evidence_id"]: row for row in inventory}
    published, rejected = [], list(base["rejected"])
    for relation in base["published"]:
        errors = []
        if relation.get("relation_type") != "EXCEPTION_TO":
            errors.append("non_exception_relation")
        target = by_id.get(str(relation.get("target_id") or "")) or {}
        target_articles = _article_surface(target.get("path"))
        source_quotes = [row for row in relation.get("proof_quotes") or []
                         if row.get("evidence_id") == relation.get("source_id")
                         and row.get("kind") == "source"]
        same_quote = []
        for quote in source_quotes:
            text = str(quote.get("text") or "")
            if (target_articles & _article_surface(text)
                    and re.search(r"적용하지\s*아니|제외|예외|에도\s*불구하고|다만", text)):
                same_quote.append(quote)
        if not same_quote:
            errors.append("target_and_exception_not_in_same_quote")
        target_value = _packed(relation.get("target_value"))
        if _packed(target.get("path")) != target_value:
            errors.append("target_value_path_mismatch")
        if candidates is not None and not any(
                candidate["source_id"] == relation.get("source_id")
                and candidate["target_id"] == relation.get("target_id")
                and candidate["quote_id"] in relation.get("quote_ids", [])
                for candidate in candidates):
            errors.append("relation_not_in_candidate_menu")
        if errors:
            rejected.append({**relation, "validation_errors": errors})
        else:
            published.append(relation)
    return {
        "published": published,
        "rejected": rejected,
        "candidate_count": len(published) + len(rejected),
        "published_count": len(published),
        "rejected_count": len(rejected),
        "valid": not rejected,
    }


def compile_exception_rescue(llm, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    inventory, cards = build_relation_cards(evidence)
    candidates = build_exception_candidates(inventory, cards)
    user = "[closed exception candidate menu]\n" + json.dumps(
        candidates, ensure_ascii=False)
    if not candidates:
        raw = {"relations": [], "unresolved": []}
        validation = validate_exception_rescue(raw, inventory, cards, candidates)
        return {"inventory": inventory, "cards": cards, "candidates": candidates,
                "product_input": user, "raw": raw, "validation": validation}
    raw = llm.structured(
        "rag.data.haiku.exception_to_targeted_rescue.experimental",
        EXCEPTION_SYSTEM, user, exception_schema(), max_tokens=2500,
        effort="low", model=HAIKU_MODEL)
    validation = validate_exception_rescue(raw, inventory, cards, candidates)
    return {"inventory": inventory, "cards": cards, "candidates": candidates,
            "product_input": user, "raw": raw, "validation": validation}
