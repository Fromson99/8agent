"""결정론적 법률 조문쌍을 Haiku가 판정하는 shadow 관계 컴파일러."""

from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any

from lawrag.core.rag.experiments.haiku_legal_methods import (
    HAIKU_MODEL, provenance_path,
)


PAIR_RELATIONS = ("IMPLEMENTS", "DEFINED_BY", "CURRENT_VERSION_OF", "EXCEPTION_TO")
MAX_PAIRS_PER_RELATION = 24
MAX_PAIRS_PER_CASE = 64
MAX_PAIRS_PER_CALL = 24

_ARTICLE = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_QUOTED_DEFINITION = re.compile(
    r'["“](?P<term>[^"”]{2,80})["”]\s*(?:이란|란|은|는)?.{0,260}?'
    r'(?:말한다|뜻한다|정의한다)'
)
_PLAIN_DEFINITION = re.compile(
    r'(?P<term>[가-힣A-Za-z0-9ㆍ·\s]{2,40}?)(?:이란|란)\s*.{0,260}?'
    r'(?:말한다|뜻한다|정의한다)'
)
_EXCEPTION_AFTER_MENTION = re.compile(
    r'(?:에도\s*불구하고|(?:을|를|은|는)?\s*(?:적용|준용).{0,24}?'
    r'(?:하지\s*아니|아니한다|배제))'
)


PAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "pair_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["RELATION", "NONE"]},
                "quote_ids": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["pair_id", "verdict", "quote_ids", "reason", "confidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


PAIR_SYSTEM = """너는 닫힌 법률 조문쌍의 관계만 판정한다. 질문에 답하지 않는다.
각 candidate의 proof_quotes만 증거로 사용하고 외부 지식이나 누락된 원문을 추측하지 않는다.
모든 pair_id를 정확히 한 번씩 RELATION 또는 NONE으로 판정한다.

관계 기준:
- IMPLEMENTS: source가 하위 규범으로서 target 상위 조문의 명시적 위임어구를 구체화한다.
  다른 법률을 단순 준수·인용하거나 벌칙에서 위반 조문을 참조하는 것은 NONE이다.
- DEFINED_BY: source가 defined_term을 독립된 동일 용어로 사용하고 target이 그 용어를
  문법상 명시적으로 정의한다. 긴 복합어 내부의 부분문자열 일치는 NONE이다.
- CURRENT_VERSION_OF: source와 target이 동일 문서·동일 조문이고 실제 revision 또는
  enforcement 메타데이터가 다르며 source=current, target=current가 아닐 때만 관계다.
  편·장·절의 신설/개정 표시는 버전 증거가 아니다.
- EXCEPTION_TO: source가 target 조문을 명시적으로 지칭하면서 그 target 규율의 적용을
  배제하거나 예외를 정한다. 자체 문장 내부의 단서나 대상 제외만으로는 NONE이다.

RELATION 판정은 confidence=high이고 해당 candidate에 제시된 quote_id만 사용해야 한다.
source 종류의 quote_id는 모두 인용한다. metadata quote_id는 문서 계층 판단에 필요할 때 인용한다.
증거가 조금이라도 부족하면 NONE으로 판정한다."""


def _packed(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def _article_keys(value: Any) -> set[str]:
    return {_packed(match.group(0)) for match in _ARTICLE.finditer(str(value or ""))}


def _exact_term(term: str, text: str) -> bool:
    """조사 결합만 허용하고 복합어 내부 부분문자열은 배제한다."""
    needle = str(term or "").strip()
    value = str(text or "")
    if not needle:
        return False
    for match in re.finditer(re.escape(needle), value):
        before = value[match.start() - 1] if match.start() else ""
        if before and re.match(r"[0-9A-Za-z가-힣]", before):
            continue
        after = value[match.end():]
        if not after or not re.match(r"[0-9A-Za-z가-힣]", after[0]):
            return True
        for particle in ("에서는", "으로는", "에게는", "에는", "이란", "에서", "으로",
                         "에게", "은", "는", "이", "가", "을", "를", "의", "에",
                         "와", "과", "도", "만", "란"):
            if after.startswith(particle):
                tail = after[len(particle):]
                if not tail or not re.match(r"[0-9A-Za-z가-힣]", tail[0]):
                    return True
    return False


def _document_level(document: str) -> int:
    packed = _packed(document)
    if "시행세칙" in packed or packed.endswith("세칙"):
        return 3
    if "시행규칙" in packed:
        return 2
    if "시행령" in packed:
        return 1
    return 0


def _same_lineage(source_document: str, target_document: str) -> bool:
    source, target = _packed(source_document), _packed(target_document)
    if not source or not target:
        return False
    suffixes = ("시행세칙", "세칙", "시행규칙", "시행령")
    source_base = source
    for suffix in suffixes:
        if source_base.endswith(suffix):
            source_base = source_base[:-len(suffix)]
            break
    return source_base == target or source.startswith(target)


def _global_definition_path(path: str) -> bool:
    """다른 조문이 재사용할 수 있는 명시적 정의조문만 global로 본다."""
    return bool(re.search(r"(?:^|▸)\s*제\s*\d+(?:의\s*\d+)?조\s+정의(?:\s|$)",
                          str(path or "")))


def _explicit_delegation_after_mention(value: str) -> bool:
    """해당 조문 언급에 직접 붙은 위임 정의만 인정한다."""
    text = str(value or "")[:140]
    marker = re.search(r"에서\s*[\"“]|위임(?:한|된|받은|하는)", text)
    if not marker:
        return False
    prefix = text[:marker.start()]
    return not re.search(r"이하|에\s*따라|에\s*따른|경우|대상", prefix)


def _metadata(row: dict[str, Any]) -> str:
    clean_path = provenance_path(str(row.get("path") or ""))[0]
    return (f"document={row.get('document', '')} | path={clean_path} | "
            f"revision={row.get('document_revision', '')} | "
            f"enforcement={row.get('document_enforcement', '')} | "
            f"current={bool(row.get('document_current', True))}")


def _source_heading(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("▸") or bool(re.fullmatch(
        r"제\s*\d+(?:의\s*\d+)?조\s*\([^)]*\)", text))


def _evidence_views(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    views = []
    for position, row in enumerate(evidence, 1):
        evidence_id = str(row.get("id") or f"E{position}")
        lines = [" ".join(line.split()) for line in
                 str(row.get("original_text") or "").splitlines() if line.strip()]
        views.append({
            "id": evidence_id,
            "document": str(row.get("document") or ""),
            "path": provenance_path(str(row.get("path") or ""))[0],
            "revision": str(row.get("document_revision") or ""),
            "enforcement": str(row.get("document_enforcement") or ""),
            "current": bool(row.get("document_current", True)),
            "meta": _metadata(row),
            "lines": lines,
        })
    return views


def _quote(evidence_id: str, quote_id: str, kind: str, text: str) -> dict[str, str]:
    return {"quote_id": quote_id, "evidence_id": evidence_id,
            "kind": kind, "text": text[:1600]}


def _line_quote(view: dict[str, Any], index: int, focus: str = "") -> dict[str, str]:
    text = view["lines"][index]
    if len(text) > 900:
        found = text.find(focus) if focus else -1
        start = max(0, found - 250) if found >= 0 else 0
        text = text[start:start + 900]
    return _quote(view["id"], f"{view['id']}:L{index + 1}", "source", text)


def _meta_quote(view: dict[str, Any]) -> dict[str, str]:
    return _quote(view["id"], f"{view['id']}:META", "metadata", view["meta"])


def _pair(relation_type: str, source: dict[str, Any], target: dict[str, Any],
          quotes: list[dict[str, str]], *, defined_term: str = "",
          basis: str = "") -> dict[str, Any]:
    return {
        "relation_type": relation_type,
        "source_id": source["id"],
        "target_id": target["id"],
        "defined_term": defined_term,
        "proof_quotes": quotes,
        "deterministic_basis": basis,
    }


def build_closed_pairs(evidence: list[dict[str, Any]], *,
                       max_pairs_per_relation: int = MAX_PAIRS_PER_RELATION,
                       max_pairs_per_case: int = MAX_PAIRS_PER_CASE) -> dict[str, Any]:
    """원문 표면형만으로 닫힌 candidate pair를 만들고 cap 초과를 폐기한다."""
    views = _evidence_views(evidence)
    article_targets: dict[str, list[dict[str, Any]]] = {}
    for view in views:
        for key in _article_keys(view["path"]):
            article_targets.setdefault(key, []).append(view)

    candidates: list[dict[str, Any]] = []
    # Explicit normative links: the source line itself must cite the target article.
    for source in views:
        for line_index, line in enumerate(source["lines"]):
            mention_matches = list(_ARTICLE.finditer(line))
            if not mention_matches:
                continue
            for mention_position, mention in enumerate(mention_matches):
                key = _packed(mention.group(0))
                next_start = (mention_matches[mention_position + 1].start()
                              if mention_position + 1 < len(mention_matches)
                              else len(line))
                after_mention = line[mention.end():min(next_start, mention.end() + 220)]
                for target in article_targets.get(key, []):
                    if target["id"] == source["id"]:
                        continue
                    article_focus = mention.group(0)
                    common_quotes = [_meta_quote(source),
                                     _line_quote(source, line_index, article_focus),
                                     _meta_quote(target)]
                    if (_explicit_delegation_after_mention(after_mention)
                            and _document_level(source["document"])
                            > _document_level(target["document"])
                            and _same_lineage(source["document"], target["document"])):
                        candidates.append(_pair(
                            "IMPLEMENTS", source, target, common_quotes,
                            basis="explicit_article_mention+delegation_surface+document_lineage"))
                    if _EXCEPTION_AFTER_MENTION.search(after_mention[:100]):
                        candidates.append(_pair(
                            "EXCEPTION_TO", source, target, common_quotes,
                            basis="explicit_article_mention+exception_surface"))

    # Definition targets are extracted first, then paired only with exact use elsewhere.
    definitions: list[tuple[dict[str, Any], int, str]] = []
    for target in views:
        for line_index, line in enumerate(target["lines"]):
            found: list[str] = []
            found.extend(match.group("term").strip()
                         for match in _QUOTED_DEFINITION.finditer(line))
            found.extend(match.group("term").strip()
                         for match in _PLAIN_DEFINITION.finditer(line))
            for term in dict.fromkeys(value for value in found if 2 <= len(value) <= 80):
                definitions.append((target, line_index, term))
    for target, target_line_index, term in definitions:
        definition_line = target["lines"][target_line_index]
        anchor_articles = _article_keys(definition_line)
        for source in views:
            if source["id"] == target["id"]:
                continue
            global_definition = (_global_definition_path(target["path"])
                                 and (_packed(source["document"])
                                      == _packed(target["document"])
                                      or _same_lineage(source["document"],
                                                       target["document"])))
            anchored_definition = (
                bool(anchor_articles & _article_keys(source["path"]))
                and _document_level(target["document"])
                > _document_level(source["document"])
                and _same_lineage(target["document"], source["document"]))
            if not (global_definition or anchored_definition):
                continue
            for source_line_index, line in enumerate(source["lines"]):
                if _source_heading(line):
                    continue
                if not _exact_term(term, line):
                    continue
                candidates.append(_pair(
                    "DEFINED_BY", source, target,
                    [_meta_quote(source), _line_quote(source, source_line_index, term),
                     _meta_quote(target), _line_quote(target, target_line_index, term)],
                    defined_term=term,
                    basis=("exact_term_use+global_definition_article"
                           if global_definition else
                           "exact_term_use+definition_anchor_article")))
                break

    # Actual version pairs require two independently identified article records.
    for source in views:
        for target in views:
            if source["id"] == target["id"] or not source["current"] or target["current"]:
                continue
            source_coordinate = (_packed(source["document"]), _article_keys(source["path"]))
            target_coordinate = (_packed(target["document"]), _article_keys(target["path"]))
            if source_coordinate != target_coordinate or not source_coordinate[1]:
                continue
            source_version = (source["revision"], source["enforcement"])
            target_version = (target["revision"], target["enforcement"])
            if (not any(source_version) or not any(target_version)
                    or source_version == target_version):
                continue
            candidates.append(_pair(
                "CURRENT_VERSION_OF", source, target,
                [_meta_quote(source), _meta_quote(target)],
                basis="same_document_article+distinct_actual_version_metadata"))

    # Deterministic deduplication and fail-closed caps.
    deduped, seen = [], set()
    for candidate in candidates:
        key = (candidate["relation_type"], candidate["source_id"],
               candidate["target_id"], _packed(candidate["defined_term"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    deduped.sort(key=lambda row: (
        PAIR_RELATIONS.index(row["relation_type"]), row["source_id"],
        row["target_id"], _packed(row["defined_term"])))

    kept, overflow = [], []
    per_relation: Counter[str] = Counter()
    for candidate in deduped:
        relation_type = candidate["relation_type"]
        if (len(kept) >= max_pairs_per_case
                or per_relation[relation_type] >= max_pairs_per_relation):
            overflow.append({**candidate, "drop_reason": "pair_cap_fail_closed"})
            continue
        candidate = {**candidate, "pair_id": f"P{len(kept) + 1:03d}"}
        kept.append(candidate)
        per_relation[relation_type] += 1
    return {
        "pairs": kept,
        "overflow": overflow,
        "raw_candidate_count": len(deduped),
        "pair_count": len(kept),
        "overflow_count": len(overflow),
        "counts": dict(sorted(per_relation.items())),
        "caps": {"per_relation": max_pairs_per_relation,
                 "per_case": max_pairs_per_case},
    }


def validate_pair_decisions(pair_build: dict[str, Any],
                            raw: dict[str, Any] | None) -> dict[str, Any]:
    pairs = {row["pair_id"]: row for row in pair_build.get("pairs") or []}
    decisions = list((raw or {}).get("decisions") or [])
    grouped: dict[str, list[dict[str, Any]]] = {}
    extra = []
    for decision in decisions:
        pair_id = str(decision.get("pair_id") or "")
        if pair_id not in pairs:
            extra.append({**decision, "validation_errors": ["unknown_pair_id"]})
        else:
            grouped.setdefault(pair_id, []).append(decision)

    published, rejected = [], []
    for pair_id, pair in pairs.items():
        values = grouped.get(pair_id) or []
        errors = []
        if len(values) != 1:
            errors.append("missing_or_duplicate_decision")
            decision = values[0] if values else {}
        else:
            decision = values[0]
        verdict = str(decision.get("verdict") or "")
        allowed_quote_ids = {row["quote_id"] for row in pair["proof_quotes"]}
        mandatory_quote_ids = {row["quote_id"] for row in pair["proof_quotes"]
                               if row.get("kind") == "source"}
        if not mandatory_quote_ids:
            mandatory_quote_ids = set(allowed_quote_ids)
        used_quote_ids = {str(value) for value in decision.get("quote_ids") or []}
        if not used_quote_ids or not used_quote_ids.issubset(allowed_quote_ids):
            errors.append("invalid_or_missing_proof_quote")
        if verdict == "RELATION":
            if str(decision.get("confidence") or "") != "high":
                errors.append("relation_confidence_not_high")
            if not mandatory_quote_ids.issubset(used_quote_ids):
                errors.append("relation_did_not_use_all_mandatory_quotes")
        elif verdict != "NONE":
            errors.append("invalid_verdict")
        row = {**pair, "decision": decision,
               "validation_errors": list(dict.fromkeys(errors))}
        if verdict == "RELATION" and not errors:
            published.append(row)
        else:
            if not errors and verdict == "NONE":
                row["rejection_reason"] = "model_adjudicated_none"
            rejected.append(row)
    rejected.extend(extra)
    return {
        "published": published,
        "rejected": rejected,
        "published_count": len(published),
        "rejected_count": len(rejected),
        "extra_decision_count": len(extra),
        "complete_decision_contract": not extra and all(
            len(grouped.get(pair_id) or []) == 1 for pair_id in pairs),
    }


def compile_pair_first_relations(llm, evidence: list[dict[str, Any]], **caps) \
        -> dict[str, Any]:
    pair_build = build_closed_pairs(evidence, **caps)
    if not pair_build["pairs"]:
        return {"pair_build": pair_build, "raw": {"decisions": []},
                "validation": validate_pair_decisions(pair_build, {"decisions": []}),
                "llm_called": False}
    # Relation-homogeneous batches keep each closed adjudication within output limits.
    batches, decisions = [], []
    for relation_type in PAIR_RELATIONS:
        relation_pairs = [pair for pair in pair_build["pairs"]
                          if pair["relation_type"] == relation_type]
        for offset in range(0, len(relation_pairs), MAX_PAIRS_PER_CALL):
            batch = relation_pairs[offset:offset + MAX_PAIRS_PER_CALL]
            # The product prompt contains only closed pairs and their proof quotes.
            user = "[closed candidate pairs]\n" + json.dumps(batch, ensure_ascii=False)
            batch_raw = llm.structured(
                f"rag.data.haiku.pair_first_relations.{relation_type.lower()}.experimental",
                PAIR_SYSTEM, user, PAIR_SCHEMA, max_tokens=6000,
                effort="low", model=HAIKU_MODEL)
            batch_decisions = list((batch_raw or {}).get("decisions") or [])
            decisions.extend(batch_decisions)
            batches.append({"relation_type": relation_type,
                            "pair_ids": [pair["pair_id"] for pair in batch],
                            "raw": batch_raw})
    raw = {"decisions": decisions}
    return {"pair_build": pair_build, "raw": raw,
            "validation": validate_pair_decisions(pair_build, raw),
            "batches": batches, "llm_called": True}
