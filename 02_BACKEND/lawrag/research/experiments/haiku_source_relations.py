"""Haiku가 원문 quote에서 증명형 법률 관계 후보를 컴파일하는 shadow 모듈."""

from __future__ import annotations

import json
import re
from typing import Any

from lawrag.research.experiments.haiku_legal_methods import (
    HAIKU_MODEL, provenance_path,
)


RELATION_TYPES = (
    "APPLIES_TO_MARKET", "GOVERNS_ACTOR", "EXCEPTION_TO", "IMPLEMENTS",
    "DEFINED_BY", "CURRENT_VERSION_OF",
)
_ARTICLE = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_RELATION_SIGNAL = re.compile(
    r"코스닥|유가증권시장|코넥스|상장주선인|회사의\s*대표자|이사|감사|"
    r"적용하지\s*아니|제외|예외|다만|에도\s*불구하고|준용|에서\s*정하는|"
    r"시행령으로\s*정하는|세칙으로\s*정하는|이란|뜻은|말한다|정의|"
    r"개정|시행|현행"
)
_DEFINITION = re.compile(r"이란|뜻은|뜻한다|말한다|정의")
_MARKETS = frozenset({"KOSDAQ", "KOSPI", "KONEX"})
_ARTICLE_RELATIONS = frozenset({
    "EXCEPTION_TO", "IMPLEMENTS", "DEFINED_BY", "CURRENT_VERSION_OF",
})


RELATION_SCHEMA = {
    "type": "object",
    "properties": {
        "relations": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "relation_id": {"type": "string"},
                "relation_type": {"type": "string", "enum": list(RELATION_TYPES)},
                "source_id": {"type": "string",
                              "description": "항상 source 조문의 evidence ID(E#)"},
                "target_id": {"type": "string",
                              "description": "article 관계만 target evidence ID(E#); 시장/actor 관계는 빈 문자열"},
                "target_value": {"type": "string",
                                 "description": "시장 관계는 KOSDAQ/KOSPI/KONEX, actor 관계는 원문 actor, article 관계는 target 조문명"},
                "defined_term": {"type": "string"},
                "quote_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_statement": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium"]},
            },
            "required": ["relation_id", "relation_type", "source_id", "target_id",
                         "target_value", "defined_term", "quote_ids",
                         "evidence_statement", "confidence"],
            "additionalProperties": False,
        }},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["relations", "unresolved"],
    "additionalProperties": False,
}


RELATION_SYSTEM = """너는 한국 법률 원문에서 재사용 가능한 관계 후보만 컴파일한다.
질문에 답하지 말고 닫힌 evidence ID와 quote ID만 사용한다.

허용 관계와 방향:
- article --APPLIES_TO_MARKET--> KOSDAQ/KOSPI/KONEX
- article --GOVERNS_ACTOR--> 원문에 실제 등장하는 actor 문자열
- exception article --EXCEPTION_TO--> governed article
- lower/detail article --IMPLEMENTS--> delegated/parent article
- using article --DEFINED_BY--> definition article, defined_term 필수
- current article --CURRENT_VERSION_OF--> prior article version

증명 규칙:
1. 모든 관계는 실제 quote_id가 있어야 한다. 문서명·경로·버전은 META quote다.
2. GOVERNS_ACTOR는 본문 quote에 actor가 정확히 등장하고 그 조문의 의무·권한·절차의
   주체여야 한다. 문서 제목만으로 actor를 만들지 않는다.
3. EXCEPTION_TO는 source 본문이 target 조문을 명시적으로 가리키면서 적용 배제·단서·
   예외를 정해야 한다. 같은 주제나 비슷한 '예외'라는 이유만으로 만들지 않는다.
4. IMPLEMENTS는 source가 target 조문의 위임·수임·세부사항을 정한다는 명시 문언과
   target 조문 표면형이 있어야 한다.
5. DEFINED_BY는 source가 용어를 사용하고 target이 같은 용어를 명시적으로 정의해야
   한다. source/target 양쪽 quote를 넣는다.
6. CURRENT_VERSION_OF는 같은 문서·조문 좌표의 서로 다른 실제 버전이 메뉴에 모두
   있고 revision/enforcement 메타데이터가 다를 때만 만든다. 상위 편·장·절의
   <신설/개정> 표시는 조문 버전 증거가 아니다.
7. APPLIES_TO_MARKET은 문서명이나 본문이 시장을 직접 특정할 때만 만든다.
8. 관계가 불명확하거나 target이 메뉴에 없으면 unresolved에 남기고 relation을
   만들지 않는다. 일반 법률지식과 추측은 금지한다.
9. publish 후보는 confidence=high만 사용한다. 문서명이나 인용문만으로 범위를
   확장해야 하는 경우에는 medium으로 두어 검증기가 보류할 수 있게 한다.
10. IMPLEMENTS는 같은 법령 계열의 상·하위 문서 관계가 metadata 문서명으로
    확인되어야 한다. 다른 법률을 준수·인용하는 관계를 IMPLEMENTS로 만들지 않는다."""


RELATION_SYSTEM += """

필드 계약(절대 서로 바꾸지 않는다):
| relation_type | source_id | target_id | target_value | defined_term |
| APPLIES_TO_MARKET | E# | 반드시 빈 문자열 | KOSDAQ/KOSPI/KONEX 중 하나 | 빈 문자열 |
| GOVERNS_ACTOR | E# | 반드시 빈 문자열 | quote에 그대로 있는 actor 문자열 | 빈 문자열 |
| EXCEPTION_TO | E# | target E# | target 조문명 | 빈 문자열 |
| IMPLEMENTS | E# | target E# | target 조문명 | 빈 문자열 |
| DEFINED_BY | E# | target E# | target 조문명 | 정의되는 정확한 용어 |
| CURRENT_VERSION_OF | E# | target E# | target 조문명 | 빈 문자열 |

시장명·actor·의무 내용은 target_id에 절대 넣지 않는다. GOVERNS_ACTOR의
target_value는 행위자의 의무 내용이 아니라 반드시 actor 자체다.
예: 회사의 대표자가 원문 주체이면 target_id="", target_value="회사의 대표자".
예: 코스닥시장 문서이면 target_id="", target_value="KOSDAQ"."""


def _packed(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def build_relation_cards(evidence: list[dict[str, Any]], *,
                         max_lines_per_evidence: int = 18) \
        -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory, cards = [], []
    for position, row in enumerate(evidence, 1):
        evidence_id = str(row.get("id") or f"E{position}")
        clean_path = provenance_path(str(row.get("path") or ""))[0]
        metadata = {
            "evidence_id": evidence_id,
            "document": str(row.get("document") or ""),
            "path": clean_path,
            "document_revision": str(row.get("document_revision") or ""),
            "document_enforcement": str(row.get("document_enforcement") or ""),
            "document_current": bool(row.get("document_current", True)),
        }
        inventory.append(metadata)
        cards.append({
            "quote_id": f"{evidence_id}:META", "evidence_id": evidence_id,
            "kind": "metadata",
            "text": (f"document={metadata['document']} | path={clean_path} | "
                     f"revision={metadata['document_revision']} | "
                     f"enforcement={metadata['document_enforcement']} | "
                     f"current={metadata['document_current']}"),
        })
        lines = [" ".join(line.split()) for line in
                 str(row.get("original_text") or "").splitlines() if line.strip()]
        selected = set(range(min(5, len(lines))))
        selected.update(index for index, line in enumerate(lines)
                        if _RELATION_SIGNAL.search(line))
        for index in sorted(selected)[:max_lines_per_evidence]:
            text = clean_path if index == 0 else lines[index]
            cards.append({
                "quote_id": f"{evidence_id}:L{index + 1}",
                "evidence_id": evidence_id, "kind": "source",
                "text": text[:1200],
            })
    return inventory, cards


def _article_mentions(value: str) -> set[str]:
    return {_packed(match.group(0)) for match in _ARTICLE.finditer(str(value or ""))}


def _explicitly_defines(term: str, text: str) -> bool:
    """용어가 정의 문언의 문법상 주어인 경우만 인정한다."""
    packed_term = _packed(term)
    packed_text = _packed(text)
    if not packed_term or not packed_text:
        return False
    return bool(re.search(
        re.escape(packed_term) + r"(?:이란|란|은|는).{0,240}(?:말한다|뜻한다|정의한다)",
        packed_text,
    ))


def _uses_exact_term(term: str, text: str) -> bool:
    """복합어 내부 부분문자열은 용어 사용으로 보지 않고 조사 결합만 허용한다."""
    value = str(text or "")
    needle = str(term or "").strip()
    if not value or not needle:
        return False
    for match in re.finditer(re.escape(needle), value):
        before = value[match.start() - 1] if match.start() else ""
        if before and re.match(r"[0-9A-Za-z가-힣]", before):
            continue
        after = value[match.end():]
        if not after or not re.match(r"[0-9A-Za-z가-힣]", after[0]):
            return True
        for particle in ("에서는", "으로는", "에게는", "이란", "에서", "으로",
                         "에게", "은", "는", "이", "가", "을", "를", "의", "에",
                         "와", "과", "도", "만", "란"):
            if after.startswith(particle):
                tail = after[len(particle):]
                if not tail or not re.match(r"[0-9A-Za-z가-힣]", tail[0]):
                    return True
    return False


def _implementation_lineage(source: dict[str, Any],
                            target: dict[str, Any]) -> bool:
    """동일 문서 또는 이름이 보존된 명시적 하위 법령만 formal implementation이다."""
    source_document = _packed(source.get("document"))
    target_document = _packed(target.get("document"))
    return bool(source_document and target_document
                and source_document.startswith(target_document))


def validate_relations(raw: dict[str, Any] | None,
                       inventory: list[dict[str, Any]],
                       cards: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = {row["evidence_id"]: row for row in inventory}
    quotes = {row["quote_id"]: row for row in cards}
    published, rejected = [], []
    seen_ids = set()
    for relation in list((raw or {}).get("relations") or []):
        errors = []
        relation_id = str(relation.get("relation_id") or "")
        relation_type = str(relation.get("relation_type") or "")
        source_id = str(relation.get("source_id") or "")
        target_id = str(relation.get("target_id") or "")
        target_value = str(relation.get("target_value") or "").strip()
        defined_term = str(relation.get("defined_term") or "").strip()
        quote_ids = [str(value) for value in relation.get("quote_ids") or []]
        if str(relation.get("confidence") or "") != "high":
            errors.append("confidence_not_high")
        if not relation_id or relation_id in seen_ids:
            errors.append("invalid_or_duplicate_relation_id")
        seen_ids.add(relation_id)
        if relation_type not in RELATION_TYPES:
            errors.append("invalid_relation_type")
        if source_id not in evidence:
            errors.append("invalid_source")
        if not quote_ids:
            errors.append("missing_quote")
        if any(value not in quotes for value in quote_ids):
            errors.append("invalid_quote")
        if quote_ids and not any(
                (quotes.get(value) or {}).get("evidence_id") == source_id
                for value in quote_ids):
            errors.append("missing_source_quote")

        quote_rows = [quotes[value] for value in quote_ids if value in quotes]
        quote_text = " ".join(str(row.get("text") or "") for row in quote_rows)
        source_text = " ".join(str(row.get("text") or "") for row in quote_rows
                               if row.get("evidence_id") == source_id
                               and row.get("kind") == "source")
        if relation_type in _ARTICLE_RELATIONS:
            if target_id not in evidence or target_id == source_id:
                errors.append("invalid_article_target")
        elif target_id:
            errors.append("unexpected_article_target")

        if relation_type == "APPLIES_TO_MARKET":
            if target_value not in _MARKETS:
                errors.append("invalid_market")
            surface = {"KOSDAQ": "코스닥", "KOSPI": "유가증권시장",
                       "KONEX": "코넥스"}.get(target_value, "")
            if surface and _packed(surface) not in _packed(quote_text):
                errors.append("market_not_in_evidence")
        elif relation_type == "GOVERNS_ACTOR":
            if not target_value or _packed(target_value) not in _packed(source_text):
                errors.append("actor_not_in_source")
        elif relation_type in {"EXCEPTION_TO", "IMPLEMENTS"} and target_id in evidence:
            target_articles = _article_mentions(evidence[target_id]["path"])
            if not target_articles or not (target_articles & _article_mentions(source_text)):
                errors.append("target_article_not_cited_by_source")
            if relation_type == "EXCEPTION_TO" and not re.search(
                    r"적용하지\s*아니|제외|예외|다만|에도\s*불구하고", source_text):
                errors.append("exception_language_missing")
            if relation_type == "IMPLEMENTS" and not re.search(
                    r"에서\s*정하는|시행령으로\s*정하는|세칙으로\s*정하는|위임|수임",
                    source_text):
                errors.append("implementation_language_missing")
            if relation_type == "IMPLEMENTS" and not _implementation_lineage(
                    evidence.get(source_id) or {}, evidence.get(target_id) or {}):
                errors.append("implementation_document_lineage_unproven")
        elif relation_type == "DEFINED_BY" and target_id in evidence:
            target_text = " ".join(str(row.get("text") or "") for row in quote_rows
                                   if row.get("evidence_id") == target_id
                                   and row.get("kind") == "source")
            if not defined_term:
                errors.append("defined_term_missing")
            elif (not _uses_exact_term(defined_term, source_text)
                  or _packed(defined_term) not in _packed(target_text)):
                errors.append("defined_term_not_in_both_sources")
            if not _explicitly_defines(defined_term, target_text):
                errors.append("definition_language_missing")
        elif relation_type == "CURRENT_VERSION_OF" and target_id in evidence:
            source = evidence.get(source_id) or {}
            target = evidence.get(target_id) or {}
            if (_packed(source.get("document")) != _packed(target.get("document"))
                    or _article_mentions(source.get("path"))
                    != _article_mentions(target.get("path"))):
                errors.append("version_coordinate_mismatch")
            if (not source.get("document_current")
                    or source.get("document_revision") == target.get("document_revision")):
                errors.append("version_metadata_not_distinct")

        row = {
            **relation,
            "proof_quotes": [
                {"quote_id": value,
                 "evidence_id": str((quotes.get(value) or {}).get("evidence_id") or ""),
                 "kind": str((quotes.get(value) or {}).get("kind") or ""),
                 "text": str((quotes.get(value) or {}).get("text") or "")}
                for value in quote_ids if value in quotes
            ],
            "validation_errors": list(dict.fromkeys(errors)),
        }
        if errors:
            rejected.append(row)
        else:
            published.append(row)
    return {
        "published": published,
        "rejected": rejected,
        "valid": not rejected,
        "candidate_count": len(published) + len(rejected),
        "published_count": len(published),
        "rejected_count": len(rejected),
    }


def compile_source_relations(llm, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    inventory, cards = build_relation_cards(evidence)
    user = ("[evidence inventory]\n"
            f"{json.dumps(inventory, ensure_ascii=False)}\n\n[quote cards]\n"
            f"{json.dumps(cards, ensure_ascii=False)}")
    raw = llm.structured(
        "rag.data.haiku.source_proven_relations.experimental",
        RELATION_SYSTEM, user, RELATION_SCHEMA, max_tokens=6000,
        effort="low", model=HAIKU_MODEL)
    if raw is None:
        raise RuntimeError("Haiku source relation structured output missing")
    validation = validate_relations(raw, inventory, cards)
    return {"inventory": inventory, "cards": cards, "raw": raw,
            "validation": validation}
