"""Schema-constrained query grounding for Legal Graph retrieval.

This module deliberately keeps three different claims apart:

* ``QueryMention`` is an exact span in the user's question.
* expansion terms are query-time hypotheses and never canonical identities.
* a canonical binding may name only a query-local wrapper whose
  ``canonical_id`` is an approved Tier-1 Concept ID with role provenance.
* an evidence selection may name only an ephemeral article-coordinate ID
  materialized from the current corpus by reverse, full-text, or vector
  retrieval.  Evidence coordinates never masquerade as canonical values.

The LLM plans search and reads a closed candidate menu.  Deterministic code
anchors spans, rejects menu-external IDs, checks coarse family/predicate
signatures, and leaves unresolved items unresolved.  The module does not write
the canonical graph and does not produce a legal conclusion.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Iterable, Mapping, Protocol, Sequence

from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.legal_graph import RelationPredicate, stable_id
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import lexicon as lexicon_mod
from lawrag.core.rag import recover, vector as vector_mod
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_graph_store import LegalGraphSnapshot


Coordinate = tuple[str, object]
GROUNDING_MODEL = "claude-haiku-4-5-20251001"

FAMILY_IDS = (
    "FORMULA", "THRESHOLD", "TEMPORAL", "FILING_DOCUMENT", "AUTHORITY",
    "LEGAL_BASIS", "CLASSIFICATION", "DELEGATION", "EXCEPTION",
    "ENTRUSTMENT", "NEGATIVE_AUTHORITY",
)
PREDICATE_IDS = tuple(predicate.value for predicate in RelationPredicate)
MENTION_ROLES = (
    "SOURCE_ACTOR", "TARGET_ACTOR", "ACTION", "OBJECT", "LEGAL_EFFECT",
    "CONDITION", "QUANTITY", "TEMPORAL", "DOCUMENT", "LEGAL_REFERENCE",
    "OTHER",
)
CONFIDENCE_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

ROLE_TO_LEXICON_FIELD = {
    "SOURCE_ACTOR": "actor",
    "TARGET_ACTOR": "target",
    "ACTION": "act",
    "OBJECT": "object",
}

# Query roles and Tier-1 Assertion roles are deliberately not the same enum.
# This is a compatibility table, not an identity conversion.
ROLE_TO_TIER1_ROLES = {
    "SOURCE_ACTOR": {"ACTOR"},
    "TARGET_ACTOR": {"TARGET"},
    "ACTION": {"PREDICATE"},
    "OBJECT": {"OBJECT"},
    "LEGAL_EFFECT": {"EFFECT"},
    "CONDITION": {"CONDITION"},
    "QUANTITY": {"OBJECT", "CONDITION"},
    "TEMPORAL": {"CONDITION"},
    "DOCUMENT": {"OBJECT"},
}

ROLE_TO_CONCEPT_TYPES = {
    "SOURCE_ACTOR": {"entity", "person_role", "organization_role"},
    "TARGET_ACTOR": {"entity", "person_role", "organization_role"},
    "ACTION": {"action", "method", "procedure_stage", "legal_operation"},
    "OBJECT": {"entity", "document", "artifact", "domain_term"},
    "LEGAL_EFFECT": {"legal_effect", "sanction", "legal_status"},
    "CONDITION": {"condition", "modality", "applicability"},
    "QUANTITY": {"quantity"},
    "TEMPORAL": {"temporal_constraint"},
    "DOCUMENT": {"document", "artifact"},
}

FAMILY_SEMANTIC_TYPES = {
    "FORMULA": {"FORMULA_EXPRESSION", "QUANTITY_CONSTRAINT", "DEFINITION_SENSE"},
    "THRESHOLD": {"QUANTITY_CONSTRAINT", "CLASSIFICATION_CRITERION", "EXCEPTION_ASSERTION"},
    "TEMPORAL": {"TEMPORAL_CONSTRAINT", "EXCEPTION_ASSERTION"},
    "FILING_DOCUMENT": {"DOCUMENT_REQUIREMENT", "CLASSIFICATION_CRITERION"},
    "AUTHORITY": {"AUTHORITY_ALLOCATION", "CLASSIFICATION_CRITERION"},
    "LEGAL_BASIS": set(),
    "CLASSIFICATION": {"CLASSIFICATION_CRITERION", "DEFINITION_SENSE"},
    "DELEGATION": {"AUTHORITY_ALLOCATION", "CLASSIFICATION_CRITERION"},
    "EXCEPTION": {"EXCEPTION_ASSERTION", "CLASSIFICATION_CRITERION"},
    "ENTRUSTMENT": {"AUTHORITY_ALLOCATION", "CLASSIFICATION_CRITERION", "DOCUMENT_REQUIREMENT"},
    "NEGATIVE_AUTHORITY": {"AUTHORITY_ALLOCATION", "EXCEPTION_ASSERTION"},
}

PLAN_SYSTEM = """너는 법률 검색용 질의 계획기다. 법률 결론을 내리지 말고 검색 가설만 만든다.

규칙:
1. mentions에는 질문에 실제로 연속해서 존재하는 표현만 그대로 적고 Python [start,end) 위치를 함께 적는다. 바꿔 쓰거나 없는 말을 만들지 않는다.
2. family_hypotheses와 predicate_hypotheses는 제공된 enum에서 복수 후보를 고른다. 하나로 억지 확정하지 않는다.
3. exact_terms, fulltext_queries, vector_queries는 검색 확장용 가설이다. 이것들은 사용자가 직접 말한 값이나 canonical DB 값이 아니다.
4. exact_terms에는 짧은 법정용어 후보, fulltext_queries에는 법문에 나올 법한 1~2개 문장, vector_queries에는 의미가 분명한 짧은 구를 둔다.
5. 모르면 빈 배열을 반환한다. 조문 번호·기관·법률관계를 지어내지 않는다."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "surface": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "role": {"type": "string", "enum": list(MENTION_ROLES)},
                },
                "required": ["surface", "start", "end", "role"],
                "additionalProperties": False,
            },
        },
        "family_hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "family_id": {"type": "string", "enum": list(FAMILY_IDS)},
                    "reason": {"type": "string"},
                },
                "required": ["family_id", "reason"],
                "additionalProperties": False,
            },
        },
        "predicate_hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "predicate": {"type": "string", "enum": list(PREDICATE_IDS)},
                    "reason": {"type": "string"},
                },
                "required": ["predicate", "reason"],
                "additionalProperties": False,
            },
        },
        "exact_terms": {"type": "array", "items": {"type": "string"}},
        "fulltext_queries": {"type": "array", "items": {"type": "string"}},
        "vector_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "mentions", "family_hypotheses", "predicate_hypotheses",
        "exact_terms", "fulltext_queries", "vector_queries",
    ],
    "additionalProperties": False,
}

BIND_SYSTEM = """너는 법률 검색의 closed-candidate binder다. 질문, 원문 span, 검색 가설,
그리고 현재 DB에서 실제로 회수한 후보 메뉴를 받는다. 메뉴의 TIER1_CONCEPT는 승인된
정규 개념 해석, TIER1_ASSERTION은 둘 이상의 원문 mention이 같은 승인 Assertion에서
만난 규칙, EVIDENCE_COORDINATE는 조문 근거 후보일 뿐 정규 actor/action/object 값이 아니다.

규칙:
1. candidate_id는 메뉴에 있는 ID만 고른다. 새 ID·조문·기관·법률용어를 만들지 않는다.
2. concept_bindings는 원문 mention의 정규 해석만, assertion_selections와 evidence_selections는 판단 시작점이나 필수 공동근거만 고른다. 후자의 합계는 최대 4개다.
3. SIGNATURE_INCOMPATIBLE 후보는 고르지 않는다. SIGNATURE_UNVERIFIED는 원문·법문 의미가 직접 맞을 때만 고른다.
4. TIER1_CONCEPT 후보는 mention/role이 후보 자체에 고정되어 있으므로 candidate_id만 고른다. 역할을 새로 쓰지 않는다.
5. TIER1_ASSERTION과 EVIDENCE_COORDINATE를 서로 다른 배열에서 고른다. Concept만 골랐다고 그 모든 출현 조문을 근거로 선택하지 않는다.
6. 원문에 결론이 직접 없으면 법적 결론을 만들지 말고 unresolved_mention_ids에 남긴다.
7. 맞는 후보가 없으면 selections를 빈 배열로 둔다."""


class StructuredLLM(Protocol):
    def structured(
        self,
        kind: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
        effort: str | None = "high",
        images: list[str] | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None: ...


@dataclass
class _CandidateAccumulator:
    coordinate: Coordinate
    channels: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)
    matched: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    origin_nodes: dict[str, set[Coordinate]] = field(
        default_factory=lambda: defaultdict(set)
    )

    def add(
        self,
        channel: str,
        score: float,
        terms: Iterable[str],
        origin: Coordinate | None = None,
    ) -> None:
        self.channels.add(channel)
        self.scores[channel] = max(float(score), self.scores.get(channel, 0.0))
        self.matched[channel].update(str(term) for term in terms if str(term).strip())
        if origin is not None:
            self.origin_nodes[channel].add(origin)


@dataclass
class _CanonicalAccumulator:
    concept_id: str
    mention_id: str
    mention_role: str
    assertion_role: str
    channels: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)
    matched: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(
        self,
        channel: str,
        score: float,
        terms: Iterable[str],
        mention: Mapping[str, Any],
    ) -> None:
        self.channels.add(channel)
        self.scores[channel] = max(float(score), self.scores.get(channel, 0.0))
        self.matched[channel].update(str(term) for term in terms if str(term).strip())


def _pack(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _canonical_catalog(
    index: Index,
    registry: Tier1Registry,
) -> dict[str, Any]:
    """Build the approved Concept lookup once per registry/index generation."""

    cache_key = (id(index.docs), index.authority_generation)
    cached = getattr(registry, "_query_grounding_catalog", None)
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == cache_key:
        return cached[1]

    by_surface: dict[str, list[tuple[str, str]]] = defaultdict(list)
    roles: dict[str, set[str]] = defaultdict(set)
    assertion_ids: dict[str, set[str]] = defaultdict(set)
    raw_coordinates: dict[str, set[Coordinate]] = defaultdict(set)
    assertion_ids_by_role: dict[tuple[str, str], set[str]] = defaultdict(set)
    coordinates_by_role: dict[tuple[str, str], set[Coordinate]] = defaultdict(set)
    for assertion in registry.active_assertions:
        source = assertion.source or {}
        coordinate = _article_coordinate(
            index, str(source.get("doc_id") or ""), source.get("node"),
        )
        for role, concept_ids in assertion.roles.items():
            normalized_role = str(role).upper()
            for concept_id in concept_ids:
                roles[concept_id].add(normalized_role)
                assertion_ids[concept_id].add(assertion.id)
                assertion_ids_by_role[(concept_id, normalized_role)].add(assertion.id)
                if coordinate is not None:
                    raw_coordinates[concept_id].add(coordinate)
                    coordinates_by_role[(concept_id, normalized_role)].add(coordinate)

    surfaces_by_concept: dict[str, tuple[str, ...]] = {}
    for concept_id, concept in registry.active_concepts.items():
        surfaces = tuple(dict.fromkeys(
            surface for surface in concept.surfaces if _pack(surface)
        ))
        surfaces_by_concept[concept_id] = surfaces
        for surface in surfaces:
            by_surface[_pack(surface)].append((concept_id, surface))

    value = {
        "by_surface": dict(by_surface),
        "surfaces_by_concept": surfaces_by_concept,
        "roles": {key: set(rows) for key, rows in roles.items()},
        "assertion_ids": {key: set(rows) for key, rows in assertion_ids.items()},
        "coordinates": {key: set(rows) for key, rows in raw_coordinates.items()},
        "assertion_ids_by_role": {
            key: set(rows) for key, rows in assertion_ids_by_role.items()
        },
        "coordinates_by_role": {
            key: set(rows) for key, rows in coordinates_by_role.items()
        },
    }
    setattr(registry, "_query_grounding_catalog", (cache_key, value))
    return value


def _canonical_role_compatible(
    mention_role: str,
    concept_roles: set[str],
    concept_type: str,
) -> bool:
    if mention_role == "OTHER":
        return True
    allowed_roles = ROLE_TO_TIER1_ROLES.get(mention_role, set())
    allowed_types = ROLE_TO_CONCEPT_TYPES.get(mention_role, set())
    return bool(allowed_roles.intersection(concept_roles) or concept_type in allowed_types)


def _clean_values(value: object, *, cap: int, limit: int = 160) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    output = []
    seen = set()
    for raw in value:
        item = re.sub(r"\s+", " ", str(raw or "")).strip()[:limit]
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= cap:
            break
    return output


def anchor_mentions(
    question: str,
    raw_mentions: Iterable[Mapping[str, Any]],
    *,
    cap: int = 16,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Anchor model-proposed surfaces to exact question offsets.

    A value absent from the question is retained only in the rejection audit;
    it can never become a QueryMention.
    """

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for raw in raw_mentions:
        surface = re.sub(r"\s+", " ", str(raw.get("surface") or "")).strip()
        role = str(raw.get("role") or "OTHER")
        if role not in MENTION_ROLES:
            role = "OTHER"
        if not surface:
            continue
        raw_start, raw_end = raw.get("start"), raw.get("end")
        exact_offset = (
            isinstance(raw_start, int) and isinstance(raw_end, int)
            and 0 <= raw_start < raw_end <= len(question)
            and question[raw_start:raw_end] == surface
        )
        if exact_offset:
            start = int(raw_start)
        else:
            positions = [
                match.start() for match in re.finditer(re.escape(surface), question)
            ]
            if len(positions) != 1:
                rejected.append({
                    "surface": surface,
                    "role": role,
                    "reason": (
                        "surface_not_in_question" if not positions
                        else "ambiguous_surface_offset"
                    ),
                })
                continue
            start = positions[0]
        if start < 0:
            rejected.append({
                "surface": surface,
                "role": role,
                "reason": "surface_not_in_question",
            })
            continue
        end = start + len(surface)
        key = (start, end, role)
        if key in seen:
            continue
        seen.add(key)
        mention_id = stable_id("query_mention", question, start, end, role, surface)
        accepted.append({
            "id": mention_id,
            "surface": surface,
            "start": start,
            "end": end,
            "role": role,
            "source": "QUESTION_SPAN",
            "offset_recovered": not exact_offset,
        })
        if len(accepted) >= cap:
            break
    return accepted, rejected


def sanitize_plan(question: str, raw: Mapping[str, Any] | None) -> dict[str, Any]:
    value = dict(raw or {})
    mentions, rejected = anchor_mentions(
        question,
        (row for row in value.get("mentions") or () if isinstance(row, Mapping)),
    )
    families = []
    seen_families = set()
    for row in value.get("family_hypotheses") or ():
        if not isinstance(row, Mapping):
            continue
        family_id = str(row.get("family_id") or "")
        if family_id not in FAMILY_IDS or family_id in seen_families:
            continue
        seen_families.add(family_id)
        families.append({
            "family_id": family_id,
            "reason": str(row.get("reason") or "")[:240],
        })
        if len(families) >= 4:
            break
    predicates = []
    seen_predicates = set()
    for row in value.get("predicate_hypotheses") or ():
        if not isinstance(row, Mapping):
            continue
        predicate = str(row.get("predicate") or "")
        if predicate not in PREDICATE_IDS or predicate in seen_predicates:
            continue
        seen_predicates.add(predicate)
        predicates.append({
            "predicate": predicate,
            "reason": str(row.get("reason") or "")[:240],
        })
        if len(predicates) >= 8:
            break
    return {
        "mentions": mentions,
        "rejected_mentions": rejected,
        "family_hypotheses": families,
        "predicate_hypotheses": predicates,
        "expansion_terms": {
            "exact": _clean_values(value.get("exact_terms"), cap=10, limit=60),
            "fulltext": _clean_values(value.get("fulltext_queries"), cap=3, limit=220),
            "vector": _clean_values(value.get("vector_queries"), cap=3, limit=160),
        },
    }


def plan_query(
    llm: StructuredLLM,
    question: str,
    *,
    model: str = GROUNDING_MODEL,
) -> dict[str, Any]:
    raw = llm.structured(
        "rag.query_grounding.plan",
        PLAN_SYSTEM,
        f"[질문]\n{question}",
        PLAN_SCHEMA,
        max_tokens=1800,
        effort=None,
        model=model,
    )
    plan = sanitize_plan(question, raw)
    plan["raw_output"] = raw
    return plan


def _article_coordinate(index: Index, doc_id: str, node: object) -> Coordinate | None:
    view = index.docs.get(str(doc_id))
    if view is None or not index.in_scope(str(doc_id)) or node not in view.by_id:
        return None
    return str(doc_id), coordinates.article_root(view, node)


def _add_candidate(
    accumulators: dict[Coordinate, _CandidateAccumulator],
    index: Index,
    doc_id: str,
    node: object,
    channel: str,
    score: float,
    terms: Iterable[str],
) -> None:
    coordinate = _article_coordinate(index, doc_id, node)
    if coordinate is None:
        return
    accumulators.setdefault(
        coordinate, _CandidateAccumulator(coordinate),
    ).add(channel, score, terms, (str(doc_id), node))


def _signature_status(
    family_ids: set[str],
    predicates: set[str],
    semantic_types: set[str],
    plan: Mapping[str, Any],
) -> str:
    planned_families = {
        str(row.get("family_id")) for row in plan.get("family_hypotheses") or ()
    }
    planned_predicates = {
        str(row.get("predicate")) for row in plan.get("predicate_hypotheses") or ()
    }
    if planned_families.intersection(family_ids):
        return "SIGNATURE_COMPATIBLE"
    if planned_predicates.intersection(predicates):
        return "SIGNATURE_COMPATIBLE"
    allowed_types = {
        semantic_type
        for family_id in planned_families
        for semantic_type in FAMILY_SEMANTIC_TYPES.get(family_id, set())
    }
    if allowed_types.intersection(semantic_types):
        return "SIGNATURE_COMPATIBLE"
    # Absence of an overlap is not proof of incompatibility.  Semantic cards
    # are intentionally incomplete (many articles are STRUCTURE_ONLY), so this
    # layer may positively verify a match but cannot safely negate one.
    return "SIGNATURE_UNVERIFIED"


def _materialize_candidate(
    index: Index,
    snapshot: LegalGraphSnapshot,
    accumulator: _CandidateAccumulator,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    doc_id, node = accumulator.coordinate
    view = index.docs[doc_id]
    cards = snapshot.semantics_for_article(accumulator.coordinate)
    verified_cards = tuple(
        card for card in cards if card.card_status == "SEMANTIC_READY"
    )
    semantic_types = {
        card.semantic_type for card in verified_cards
    }
    family_ids = {family for card in verified_cards for family in card.family_ids}
    predicates = {
        card.relation_predicate for card in verified_cards if card.relation_predicate
    }
    for direction in ("outgoing", "incoming"):
        try:
            predicates.update(
                edge.predicate for edge in snapshot.incident(
                    accumulator.coordinate, direction=direction,
                )
            )
        except (KeyError, ValueError):
            continue
    terms = {term for card in verified_cards for term in card.terms}
    coverage = {key for card in verified_cards for key in card.coverage_keys}
    labels = [card.label for card in cards if card.label]
    body = view.section_text(view.by_id[node], cap=720)
    path = view.path(node)
    hit_excerpts = []
    for channel, origins in sorted(accumulator.origin_nodes.items()):
        for origin_doc_id, origin_node in sorted(
            origins, key=lambda value: (value[0], str(value[1])),
        )[:3]:
            origin_view = index.docs.get(origin_doc_id)
            if origin_view is None or origin_node not in origin_view.by_id:
                continue
            hit_excerpts.append({
                "channel": channel,
                "origin_coordinate": [origin_doc_id, origin_node],
                "origin_path": origin_view.path(origin_node),
                "text": origin_view.section_text(
                    origin_view.by_id[origin_node], cap=420,
                ),
            })
    channel_score = max(accumulator.scores.values(), default=0.0)
    channel_score += max(0, len(accumulator.channels) - 1) * 8.0
    status = _signature_status(family_ids, predicates, semantic_types, plan)
    if status == "SIGNATURE_COMPATIBLE":
        channel_score += 18.0
    elif status == "SIGNATURE_INCOMPATIBLE":
        channel_score -= 18.0
    return {
        "id": stable_id("evidence_candidate", doc_id, node),
        "candidate_kind": "EVIDENCE_COORDINATE",
        "coordinate": [doc_id, node],
        "coordinates": [[doc_id, node]],
        "doc": view.name,
        "path": path,
        "label": (labels[0] if labels else body)[:360],
        "preview": body[:720],
        "hit_excerpts": hit_excerpts[:8],
        "channels": sorted(accumulator.channels),
        "channel_scores": dict(sorted(accumulator.scores.items())),
        "score": round(channel_score, 6),
        "matched": {
            channel: sorted(values)
            for channel, values in sorted(accumulator.matched.items())
        },
        "semantic_types": sorted(semantic_types),
        "family_ids": sorted(family_ids),
        "predicates": sorted(predicates),
        "coverage_keys": sorted(coverage),
        "terms": sorted(terms)[:24],
        "card_ids": sorted(card.card_id for card in verified_cards)[:24],
        "signature_status": status,
    }


def _generate_canonical_candidates(
    index: Index,
    registry: Tier1Registry,
    plan: Mapping[str, Any],
    evidence_accumulators: Mapping[Coordinate, _CandidateAccumulator],
    *,
    cap: int = 48,
    include_vector: bool = True,
) -> list[dict[str, Any]]:
    """Materialize role-provenanced Tier-1 Concept wrapper candidates."""

    catalog = _canonical_catalog(index, registry)
    by_surface: Mapping[str, list[tuple[str, str]]] = catalog["by_surface"]
    roles_by_concept: Mapping[str, set[str]] = catalog["roles"]
    accumulators: dict[tuple[str, str, str], _CanonicalAccumulator] = {}

    def add_candidate(
        concept_id: str,
        channel: str,
        score: float,
        terms: Iterable[str],
        mention: Mapping[str, Any],
    ) -> None:
        concept = registry.active_concepts.get(concept_id)
        if concept is None:
            return
        concept_roles = set(roles_by_concept.get(concept_id, set()))
        mention_id = str(mention.get("id") or "")
        mention_role = str(mention.get("role") or "OTHER")
        compatible_roles = sorted(
            concept_roles.intersection(ROLE_TO_TIER1_ROLES.get(mention_role, set()))
        )
        if not mention_id or not compatible_roles:
            return
        for assertion_role in compatible_roles:
            key = (mention_id, concept_id, assertion_role)
            accumulators.setdefault(
                key,
                _CanonicalAccumulator(
                    concept_id, mention_id, mention_role, assertion_role,
                ),
            ).add(channel, score, terms, mention)

    mentions = list(plan.get("mentions") or ())
    for mention in mentions:
        surface = str(mention.get("surface") or "")
        for concept_id, matched in by_surface.get(_pack(surface), ()):
            add_candidate(
                concept_id, "reverse", 125.0, [surface, matched], mention,
            )

    # Role-filtered vector candidates: the vector population is the approved
    # canonical surfaces compatible with that exact question mention.
    compiled = spanparts.cached_term_lexicon() if include_vector else None
    if compiled is not None:
        for mention in mentions:
            mention_role = str(mention.get("role") or "OTHER")
            allowed_terms = {
                _pack(surface)
                for concept_id, surfaces in catalog["surfaces_by_concept"].items()
                if (concept := registry.active_concepts.get(concept_id)) is not None
                and set(roles_by_concept.get(concept_id, set())).intersection(
                    ROLE_TO_TIER1_ROLES.get(mention_role, set())
                )
                for surface in surfaces
            }
            if not allowed_terms:
                continue
            rows = compiled.neighbors_many_filtered(
                [str(mention.get("surface") or "")],
                allowed_terms,
                k=10,
                min_cos=0.52,
            )[0]
            for neighbor in rows:
                matched_key = _pack(neighbor.get("term"))
                for concept_id, matched in by_surface.get(matched_key, ()):
                    add_candidate(
                        concept_id,
                        "vector",
                        88.0 * float(neighbor.get("cos") or 0.0),
                        [mention.get("surface") or "", matched],
                        mention,
                    )

    materialized = []
    for (_mention_id, concept_id, assertion_role), accumulator in accumulators.items():
        concept = registry.active_concepts[concept_id]
        concept_roles = set(roles_by_concept.get(concept_id, set()))
        role_key = (concept_id, assertion_role)
        raw_coordinates = set(catalog["coordinates_by_role"].get(role_key, set()))
        ranked_coordinates = sorted(
            raw_coordinates,
            key=lambda value: (
                -max(
                    evidence_accumulators.get(
                        value, _CandidateAccumulator(value),
                    ).scores.values(),
                    default=0.0,
                ),
                value[0],
                str(value[1]),
            ),
        )[:12]
        if not ranked_coordinates:
            # A canonical Concept can be valid for explanation yet unusable as
            # a retrieval landing.  Do not put such a dead end in this menu.
            continue
        paths = []
        for doc_id, node in ranked_coordinates[:4]:
            view = index.docs.get(doc_id)
            if view is not None and node in view.by_id:
                paths.append({
                    "coordinate": [doc_id, node],
                    "doc": view.name,
                    "path": view.path(node),
                })
        materialized.append({
            "id": stable_id(
                "tier1_concept_candidate",
                accumulator.mention_id,
                concept_id,
                assertion_role,
            ),
            "candidate_kind": "TIER1_CONCEPT",
            "canonical_id": concept_id,
            "coordinate": list(ranked_coordinates[0]),
            "coordinates": [list(value) for value in ranked_coordinates],
            "doc": paths[0]["doc"] if paths else "",
            "path": paths[0]["path"] if paths else "",
            "label": concept.label,
            "preview": (concept.definitions[0] if concept.definitions else "")[:720],
            "concept_type": concept.type,
            "canonical_roles": sorted(concept_roles),
            "assertion_role": assertion_role,
            "allowed_mention_roles": [accumulator.mention_role],
            "source_mention_ids": [accumulator.mention_id],
            "assertion_ids": sorted(
                catalog["assertion_ids_by_role"].get(role_key, set())
            )[:24],
            "coordinate_previews": paths,
            "channels": sorted(accumulator.channels),
            "channel_scores": dict(sorted(accumulator.scores.items())),
            "score": round(max(accumulator.scores.values(), default=0.0) + 10.0, 6),
            "matched": {
                channel: sorted(values)
                for channel, values in sorted(accumulator.matched.items())
            },
            "semantic_types": [],
            "family_ids": [],
            "predicates": [],
            "coverage_keys": [],
            "terms": list(catalog["surfaces_by_concept"].get(concept_id, ()))[:24],
            "card_ids": [],
            "signature_status": "SIGNATURE_COMPATIBLE",
        })
    materialized.sort(key=lambda row: (-float(row["score"]), row["id"]))
    return materialized[:cap]


def _generate_assertion_candidates(
    index: Index,
    registry: Tier1Registry,
    canonical_candidates: Sequence[Mapping[str, Any]],
    *,
    cap: int = 24,
) -> list[dict[str, Any]]:
    """Create an assertion menu only when at least two mentions co-ground."""

    by_assertion: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in canonical_candidates:
        for assertion_id in row.get("assertion_ids") or ():
            if assertion_id in registry.active_assertions_by_id:
                by_assertion[str(assertion_id)].append(row)

    output = []
    for assertion_id, rows in by_assertion.items():
        mention_ids = {
            str(mention_id)
            for row in rows for mention_id in row.get("source_mention_ids") or ()
        }
        if len(mention_ids) < 2:
            continue
        assertion = registry.active_assertions_by_id[assertion_id]
        source = assertion.source or {}
        coordinate = _article_coordinate(
            index, str(source.get("doc_id") or ""), source.get("node"),
        )
        if coordinate is None:
            continue
        best_bindings: dict[tuple[str, str], Mapping[str, Any]] = {}
        for row in rows:
            mention_id = str((row.get("source_mention_ids") or [""])[0])
            role = str(row.get("assertion_role") or "")
            key = (mention_id, role)
            current = best_bindings.get(key)
            if current is None or float(row.get("score") or 0.0) > float(
                current.get("score") or 0.0
            ):
                best_bindings[key] = row
        bindings = [{
            "mention_id": mention_id,
            "query_role": str((row.get("allowed_mention_roles") or [""])[0]),
            "assertion_role": role,
            "concept_candidate_id": row["id"],
            "canonical_concept_id": row["canonical_id"],
            "label": row["label"],
        } for (mention_id, role), row in sorted(best_bindings.items())]
        if len({row["mention_id"] for row in bindings}) < 2:
            continue
        doc_id, node = coordinate
        view = index.docs[doc_id]
        body = view.section_text(view.by_id[node], cap=720)
        channels = sorted({
            channel for row in rows for channel in row.get("channels") or ()
        })
        score = sum(sorted(
            (float(row.get("score") or 0.0) for row in best_bindings.values()),
            reverse=True,
        )[:4]) / max(1, min(4, len(best_bindings)))
        output.append({
            "id": stable_id("tier1_assertion_candidate", assertion_id, bindings),
            "candidate_kind": "TIER1_ASSERTION",
            "canonical_id": assertion_id,
            "coordinate": [doc_id, node],
            "coordinates": [[doc_id, node]],
            "doc": view.name,
            "path": view.path(node),
            "label": assertion.note or body[:360],
            "preview": body[:720],
            "source_mention_ids": sorted(mention_ids),
            "role_bindings": bindings,
            "channels": channels,
            "channel_scores": {},
            "score": round(score + 15.0, 6),
            "matched": {},
            "semantic_types": [],
            "family_ids": [],
            "predicates": [],
            "coverage_keys": [],
            "terms": [],
            "card_ids": [],
            "assertion_ids": [assertion_id],
            "signature_status": "SIGNATURE_COMPATIBLE",
        })
    output.sort(key=lambda row: (-float(row["score"]), row["id"]))
    return output[:cap]


def _bounded_queries(question: str, values: Iterable[str], cap: int) -> list[str]:
    return _clean_values([question, *values], cap=cap, limit=220)


def _index_reverse_exact(
    index: Index, query: str, *, cap: int = 16,
) -> list[tuple[str, list[tuple[str, object]]]]:
    """Resolve exact DB surfaces without constructing the embedding lexicon.

    ``Index.entries`` already contains current title and approved glossary
    surfaces with their source coordinates.  The integrated add-only arm uses
    this lightweight reverse channel because the shared baseline has already
    paid for full-text/vector retrieval.  Longer nested surfaces win exactly
    as in :meth:`Lexicon.exact`.
    """

    packed_query = _pack(query)
    hits = [
        entry for entry in index.entries
        if len(str(entry.key or "")) >= 2
        and str(entry.key).casefold() in packed_query
    ]
    hits.sort(key=lambda entry: (-len(str(entry.key)), str(entry.key), entry.target))
    output: list[tuple[str, list[tuple[str, object]]]] = []
    covered: list[str] = []
    seen_targets: set[str] = set()
    for entry in hits:
        key = str(entry.key).casefold()
        if entry.target in seen_targets or any(key in parent for parent in covered):
            continue
        if entry.kind == "용어":
            coordinates = [
                (str(row.get("doc_id") or ""), row.get("node"))
                for row in (entry.occurrences or ())[:8]
                if str(row.get("doc_id") or "") and row.get("node") is not None
            ]
        else:
            coordinates = (
                [(str(entry.doc_id), entry.node)]
                if entry.doc_id and entry.node is not None else []
            )
        if not coordinates:
            continue
        seen_targets.add(entry.target)
        covered.append(key)
        output.append((str(entry.value), coordinates))
        if len(output) >= cap:
            break
    return output


def generate_candidates(
    index: Index,
    snapshot: LegalGraphSnapshot,
    registry: Tier1Registry | None,
    question: str,
    plan: Mapping[str, Any],
    *,
    menu_cap: int = 36,
    include_vector: bool = True,
    include_fulltext: bool = True,
    include_canonical: bool = True,
    use_index_reverse: bool = False,
) -> dict[str, Any]:
    """Generate a bounded, provenance-preserving candidate menu."""

    started = time.perf_counter()
    accumulators: dict[Coordinate, _CandidateAccumulator] = {}
    channel_errors: list[dict[str, str]] = []
    if include_canonical and registry is None:
        raise ValueError("canonical grounding requires a Tier1 registry")
    # The full grounding route retains the historical corpus lexicon.  The
    # integrated incremental route can use current Index entries directly and
    # avoid rebuilding definitions/embeddings that it never presents.
    lx = None if use_index_reverse else lexicon_mod.current(index)
    expansion = plan.get("expansion_terms") or {}

    reverse_queries = _bounded_queries(
        question,
        [
            *(expansion.get("exact") or ()),
            *(mention.get("surface") for mention in plan.get("mentions") or ()),
        ],
        16,
    )
    for query in reverse_queries:
        if use_index_reverse:
            reverse_hits = [
                {"term": surface, "coords": coordinates}
                for surface, coordinates in _index_reverse_exact(
                    index, query, cap=16,
                )
            ]
        else:
            reverse_hits = lx.exact(query, cap=16) if lx is not None else []
        for rank, hit in enumerate(reverse_hits, 1):
            for doc_id, node in hit.get("coords") or ():
                _add_candidate(
                    accumulators, index, doc_id, node, "reverse",
                    110.0 - rank, [query, hit.get("term") or ""],
                )

    fulltext_queries = (
        _bounded_queries(question, expansion.get("fulltext") or (), 4)
        if include_fulltext else []
    )
    for query in fulltext_queries:
        rows, _meta = recover.rung_fulltext(index, query)
        for rank, row in enumerate(rows[:24], 1):
            _add_candidate(
                accumulators, index, row.get("doc_id"), row.get("node"),
                "fulltext", 78.0 - rank, [query, row.get("why") or ""],
            )

    vector_queries = (
        _bounded_queries(question, expansion.get("vector") or (), 4)
        if include_vector else []
    )
    if include_vector:
        for query in vector_queries:
            try:
                rows = vector_mod.search(query, topk=16, doc_ids=index.scope, minimum=0.34)
            except Exception as exc:
                from lawrag.runtime.content_snapshot import ContentSnapshotError

                if isinstance(exc, ContentSnapshotError):
                    raise
                channel_errors.append({
                    "channel": "vector",
                    "query": query,
                    "error": f"{type(exc).__name__}: {exc}"[:400],
                })
                rows = []
            for doc_id, node, cosine in rows:
                _add_candidate(
                    accumulators, index, doc_id, node, "vector",
                    72.0 * float(cosine), [query],
                )
        for mention in plan.get("mentions") or ():
            field = ROLE_TO_LEXICON_FIELD.get(str(mention.get("role") or ""))
            if not field:
                continue
            try:
                neighbors = lx.neighbors(
                    str(mention.get("surface") or ""), field=field, k=8, min_cos=0.60,
                ) if lx is not None else []
            except Exception as exc:
                channel_errors.append({
                    "channel": "lexicon_vector",
                    "query": str(mention.get("surface") or ""),
                    "error": f"{type(exc).__name__}: {exc}"[:400],
                })
                neighbors = []
            for neighbor in neighbors:
                for doc_id, node in neighbor.get("coords") or ():
                    _add_candidate(
                        accumulators, index, doc_id, node, "vector",
                        68.0 * float(neighbor.get("cos") or 0.0),
                        [mention.get("surface") or "", neighbor.get("term") or ""],
                    )

    evidence_candidates = [
        _materialize_candidate(index, snapshot, accumulator, plan)
        for accumulator in accumulators.values()
    ]
    evidence_candidates.sort(key=lambda row: (-float(row["score"]), row["id"]))
    canonical_candidates = (
        _generate_canonical_candidates(
            index, registry, plan, accumulators,
            include_vector=include_vector,
        )
        if include_canonical and registry is not None else []
    )
    assertion_candidates = (
        _generate_assertion_candidates(index, registry, canonical_candidates)
        if include_canonical and registry is not None else []
    )
    materialized = [
        *canonical_candidates, *assertion_candidates, *evidence_candidates,
    ]
    materialized.sort(key=lambda row: (-float(row["score"]), row["id"]))

    menu: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    canonical_cap = min(len(canonical_candidates), max(1, menu_cap // 4))
    for row in canonical_candidates[:canonical_cap]:
        selected_ids.add(row["id"])
        menu.append(row)
    assertion_cap = min(len(assertion_candidates), max(1, menu_cap // 6))
    for row in assertion_candidates[:assertion_cap]:
        selected_ids.add(row["id"])
        menu.append(row)
    remaining = max(0, menu_cap - len(menu))
    per_channel_cap = max(1, remaining // 3)
    for channel in ("reverse", "fulltext", "vector"):
        added = 0
        ranked_channel = sorted(
            (item for item in evidence_candidates if channel in item["channels"]),
            key=lambda item: (
                -float((item.get("channel_scores") or {}).get(channel, 0.0)),
                item["id"],
            ),
        )
        for row in ranked_channel:
            if row["id"] in selected_ids:
                continue
            selected_ids.add(row["id"])
            menu.append(row)
            added += 1
            if added >= per_channel_cap:
                break
    for row in materialized:
        if len(menu) >= menu_cap:
            break
        if row["id"] in selected_ids:
            continue
        selected_ids.add(row["id"])
        menu.append(row)
    menu.sort(key=lambda row: (-float(row["score"]), row["id"]))
    channel_coordinates = {
        channel: [list(value) for value in sorted({
            tuple(coordinate)
            for row in materialized if channel in row["channels"]
            for coordinate in row.get("coordinates") or [row["coordinate"]]
        }, key=lambda value: (str(value[0]), str(value[1])))]
        for channel in ("reverse", "fulltext", "vector")
    }
    return {
        "menu": menu[:menu_cap],
        "all_candidates": materialized,
        "canonical_candidates": canonical_candidates,
        "assertion_candidates": assertion_candidates,
        "evidence_candidates": evidence_candidates,
        "channel_coordinates": channel_coordinates,
        "reverse_queries": reverse_queries,
        "fulltext_queries": fulltext_queries,
        "vector_queries": vector_queries,
        "lexicon_cache": (
            dict(lx.cache_stats) if lx is not None
            else {"mode": "INDEX_ENTRIES_EXACT", "compiled": False}
        ),
        "channel_errors": channel_errors,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def binding_schema(
    menu: Sequence[Mapping[str, Any]] | Sequence[str],
    mention_ids: Sequence[str] = (),
) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = (
        [{"id": value, "candidate_kind": "EVIDENCE_COORDINATE"} for value in menu]
        if menu and isinstance(menu[0], str)
        else list(menu)  # type: ignore[arg-type]
    )

    def ids(kind: str) -> list[str]:
        return [str(row["id"]) for row in rows if row.get("candidate_kind") == kind]

    concept_ids = ids("TIER1_CONCEPT")
    assertion_ids = ids("TIER1_ASSERTION")
    evidence_ids = ids("EVIDENCE_COORDINATE")

    def selection_array(candidate_ids: Sequence[str], cap: int) -> dict[str, Any]:
        candidate_schema: dict[str, Any] = {"type": "string"}
        if candidate_ids:
            candidate_schema["enum"] = list(candidate_ids)
        result: dict[str, Any] = {
            "type": "array",
            "maxItems": cap,
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": candidate_schema,
                    "confidence": {
                        "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["candidate_id", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
        if not candidate_ids:
            result["maxItems"] = 0
            result["description"] = (
                "No candidates of this kind exist; return an empty array."
            )
        return result

    mention_schema: dict[str, Any] = {"type": "string"}
    unresolved_schema: dict[str, Any] = {
        "type": "array", "items": mention_schema,
    }
    if mention_ids:
        mention_schema["enum"] = list(mention_ids)
    else:
        unresolved_schema["maxItems"] = 0
        unresolved_schema["description"] = (
            "No anchored mentions exist; return an empty array."
        )
    return {
        "type": "object",
        "properties": {
            "concept_bindings": selection_array(concept_ids, 8),
            "assertion_selections": selection_array(assertion_ids, 4),
            "evidence_selections": selection_array(evidence_ids, 4),
            "unresolved_mention_ids": unresolved_schema,
        },
        "required": [
            "concept_bindings", "assertion_selections",
            "evidence_selections", "unresolved_mention_ids",
        ],
        "additionalProperties": False,
    }


def validate_bindings(
    raw: Mapping[str, Any] | None,
    menu: Sequence[Mapping[str, Any]],
    mentions: Sequence[Mapping[str, Any]],
    *,
    registry: Tier1Registry | None = None,
    selection_cap: int = 4,
) -> dict[str, Any]:
    all_by_id = {str(row.get("id")): dict(row) for row in menu}
    by_kind = {
        kind: {
            candidate_id: row for candidate_id, row in all_by_id.items()
            if row.get("candidate_kind") == kind
        }
        for kind in ("TIER1_CONCEPT", "TIER1_ASSERTION", "EVIDENCE_COORDINATE")
    }
    mention_ids = {str(row.get("id")) for row in mentions}
    raw_value = dict(raw or {})
    concept_bindings: list[dict[str, Any]] = []
    assertion_selections: list[dict[str, Any]] = []
    evidence_selections: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def reject(candidate_id: str, expected_kind: str, reason: str | None = None) -> None:
        actual = all_by_id.get(candidate_id, {}).get("candidate_kind")
        rejected.append({
            "candidate_id": candidate_id,
            "expected_kind": expected_kind,
            "actual_kind": actual,
            "reason": reason or (
                "candidate_kind_mismatch" if actual else "candidate_not_in_closed_menu"
            ),
        })

    def parse_rows(field: str, kind: str, cap: int) -> list[dict[str, Any]]:
        parsed = []
        for raw_row in raw_value.get(field) or ():
            if not isinstance(raw_row, Mapping):
                continue
            candidate_id = str(raw_row.get("candidate_id") or "")
            key = (kind, candidate_id)
            if key in seen:
                continue
            seen.add(key)
            candidate = by_kind[kind].get(candidate_id)
            if candidate is None:
                reject(candidate_id, kind)
                continue
            parsed.append({
                "candidate_id": candidate_id,
                "candidate_kind": kind,
                "canonical_id": candidate.get("canonical_id"),
                "coordinate": list(candidate["coordinate"]),
                "coordinates": [
                    list(value) for value in (
                        candidate.get("coordinates") or [candidate["coordinate"]]
                    )
                ],
                "mention_ids": [
                    value for value in candidate.get("source_mention_ids") or ()
                    if value in mention_ids
                ],
                "confidence": (
                    str(raw_row.get("confidence"))
                    if str(raw_row.get("confidence")) in CONFIDENCE_ORDER else "LOW"
                ),
                "reason": str(raw_row.get("reason") or "")[:400],
                "signature_status": candidate.get("signature_status"),
                "candidate_score": candidate.get("score"),
            })
            if len(parsed) >= cap:
                break
        return parsed

    for row in parse_rows("concept_bindings", "TIER1_CONCEPT", 8):
        candidate = all_by_id[row["candidate_id"]]
        canonical_id = str(candidate.get("canonical_id") or "")
        assertion_role = str(candidate.get("assertion_role") or "")
        if not row["mention_ids"]:
            reject(row["candidate_id"], "TIER1_CONCEPT", "missing_anchored_mention")
            continue
        if registry is not None:
            if canonical_id not in registry.active_concepts:
                reject(row["candidate_id"], "TIER1_CONCEPT", "unknown_canonical_id")
                continue
            valid_provenance = any(
                canonical_id in assertion.roles.get(assertion_role, ())
                for assertion_id in candidate.get("assertion_ids") or ()
                if (assertion := registry.active_assertions_by_id.get(
                    str(assertion_id)
                )) is not None
            )
            if not valid_provenance:
                reject(row["candidate_id"], "TIER1_CONCEPT", "role_provenance_mismatch")
                continue
        row["assertion_role"] = assertion_role
        concept_bindings.append(row)

    for row in parse_rows("assertion_selections", "TIER1_ASSERTION", 4):
        candidate = all_by_id[row["candidate_id"]]
        canonical_id = str(candidate.get("canonical_id") or "")
        if registry is not None:
            assertion = registry.active_assertions_by_id.get(canonical_id)
            if assertion is None:
                reject(row["candidate_id"], "TIER1_ASSERTION", "unknown_canonical_id")
                continue
            role_bindings = candidate.get("role_bindings") or ()
            valid = all(
                str(binding.get("canonical_concept_id") or "")
                in assertion.roles.get(str(binding.get("assertion_role") or ""), ())
                for binding in role_bindings
            )
            if not valid:
                reject(row["candidate_id"], "TIER1_ASSERTION", "role_provenance_mismatch")
                continue
        assertion_selections.append(row)

    for row in parse_rows("evidence_selections", "EVIDENCE_COORDINATE", 4):
        if row.get("signature_status") == "SIGNATURE_INCOMPATIBLE":
            reject(
                row["candidate_id"], "EVIDENCE_COORDINATE",
                "predicate_family_signature_incompatible",
            )
            continue
        evidence_selections.append(row)

    seed_candidates = [*assertion_selections, *evidence_selections]
    seed_candidates.sort(key=lambda row: (
        -CONFIDENCE_ORDER.get(str(row["confidence"]), 0),
        -float(row.get("candidate_score") or 0.0),
        row["candidate_id"],
    ))
    for row in seed_candidates[selection_cap:]:
        reject(row["candidate_id"], row["candidate_kind"], "selection_cap_exceeded")
    validated = seed_candidates[:selection_cap]
    validated_ids = {row["candidate_id"] for row in validated}
    assertion_selections = [
        row for row in assertion_selections if row["candidate_id"] in validated_ids
    ]
    evidence_selections = [
        row for row in evidence_selections if row["candidate_id"] in validated_ids
    ]
    covered_mentions = {
        mention_id
        for row in [*concept_bindings, *assertion_selections]
        for mention_id in row.get("mention_ids") or ()
    }
    raw_unresolved = {
        value for value in _clean_values(
            raw_value.get("unresolved_mention_ids"), cap=32, limit=120,
        ) if value in mention_ids
    }
    unresolved = sorted(raw_unresolved | (mention_ids - covered_mentions))
    return {
        "raw_output": raw,
        "concept_bindings": concept_bindings,
        "assertion_selections": assertion_selections,
        "evidence_selections": evidence_selections,
        "bound": [*assertion_selections, *evidence_selections],
        "validated": validated,
        "rejected": rejected,
        "unresolved_mention_ids": unresolved,
        "menu_external_id_count": sum(
            row["reason"] == "candidate_not_in_closed_menu" for row in rejected
        ),
        "signature_rejection_count": sum(
            row["reason"] in {
                "predicate_family_signature_incompatible",
                "missing_anchored_mention",
                "role_provenance_mismatch",
            }
            for row in rejected
        ),
        "cross_menu_rejection_count": sum(
            row["reason"] == "candidate_kind_mismatch" for row in rejected
        ),
        "canonical_unknown_id_count": sum(
            row["reason"] == "unknown_canonical_id" for row in rejected
        ),
    }


def bind_candidates(
    llm: StructuredLLM,
    registry: Tier1Registry,
    question: str,
    plan: Mapping[str, Any],
    candidates: Mapping[str, Any],
    *,
    model: str = GROUNDING_MODEL,
) -> dict[str, Any]:
    menu = list(candidates.get("menu") or ())
    compact_menu = [{
        "candidate_id": row["id"],
        "candidate_kind": row["candidate_kind"],
        "canonical_id": row.get("canonical_id"),
        "coordinate": row["coordinate"],
        "coordinate_count": len(row.get("coordinates") or ()),
        "doc": row["doc"],
        "path": row["path"],
        "label": row["label"],
        "preview": (
            ((row.get("hit_excerpts") or [{}])[0].get("text") or "")
            or row["preview"]
        )[:420],
        "hit_excerpts": (row.get("hit_excerpts") or [])[:3],
        "channels": row["channels"],
        "semantic_types": row["semantic_types"],
        "family_ids": row["family_ids"],
        "predicates": row["predicates"],
        "concept_type": row.get("concept_type"),
        "canonical_roles": row.get("canonical_roles") or [],
        "source_mention_ids": row.get("source_mention_ids") or [],
        "allowed_mention_roles": row.get("allowed_mention_roles") or [],
        "assertion_role": row.get("assertion_role"),
        "role_bindings": row.get("role_bindings") or [],
        "signature_status": row["signature_status"],
    } for row in menu]
    payload = {
        "question": question,
        "mentions": plan.get("mentions") or [],
        "family_hypotheses": plan.get("family_hypotheses") or [],
        "predicate_hypotheses": plan.get("predicate_hypotheses") or [],
        "candidates": compact_menu,
    }
    schema = binding_schema(
        menu,
        [str(row["id"]) for row in plan.get("mentions") or ()],
    )
    raw = llm.structured(
        "rag.query_grounding.bind",
        BIND_SYSTEM,
        json.dumps(payload, ensure_ascii=False, indent=2),
        schema,
        max_tokens=2600,
        effort=None,
        model=model,
    )
    return validate_bindings(
        raw, menu, plan.get("mentions") or (), registry=registry,
    )


def ground_query(
    llm: StructuredLLM,
    index: Index,
    snapshot: LegalGraphSnapshot,
    registry: Tier1Registry,
    question: str,
    *,
    menu_cap: int = 36,
    model: str = GROUNDING_MODEL,
) -> dict[str, Any]:
    started = time.perf_counter()
    planning_started = time.perf_counter()
    plan = plan_query(llm, question, model=model)
    planning_ms = (time.perf_counter() - planning_started) * 1000
    candidates = generate_candidates(
        index, snapshot, registry, question, plan, menu_cap=menu_cap,
    )
    binding_started = time.perf_counter()
    binding = bind_candidates(
        llm, registry, question, plan, candidates, model=model,
    )
    binding_ms = (time.perf_counter() - binding_started) * 1000
    bound_coordinates = list(dict.fromkeys(
        tuple(coordinate)
        for row in binding["bound"]
        for coordinate in row.get("coordinates") or [row["coordinate"]]
    ))
    validated_coordinates = list(dict.fromkeys(
        tuple(coordinate)
        for row in binding["validated"]
        for coordinate in row.get("coordinates") or [row["coordinate"]]
    ))
    canonical_ids = set(registry.active_concepts) | set(
        registry.active_assertions_by_id
    )
    accepted_canonical_ids = {
        str(row.get("canonical_id") or "")
        for row in [
            *binding["concept_bindings"], *binding["assertion_selections"],
        ]
        if row.get("canonical_id")
    }
    return {
        "schema_version": "query-grounding-plan-v2",
        "question": question,
        "plan": plan,
        "candidates": candidates,
        "binding": binding,
        "bound_coordinates": [list(value) for value in bound_coordinates],
        "validated_coordinates": [list(value) for value in validated_coordinates],
        "validation": {
            "anchored_mentions": len(plan["mentions"]),
            "rejected_unanchored_mentions": len(plan["rejected_mentions"]),
            "menu_external_id_count": binding["menu_external_id_count"],
            "signature_rejection_count": binding["signature_rejection_count"],
            "cross_menu_rejection_count": binding["cross_menu_rejection_count"],
            "canonical_unknown_id_count": binding["canonical_unknown_id_count"],
            "canonical_generated_id_count": len(
                accepted_canonical_ids - canonical_ids
            ),
        },
        "latency_ms": {
            "planner_api_wall": round(planning_ms, 3),
            "candidate_generation": float(candidates["elapsed_ms"]),
            "binder_api_wall": round(binding_ms, 3),
            "total": round((time.perf_counter() - started) * 1000, 3),
        },
    }


def insert_grounded_seeds(
    parent_coordinates: Iterable[Coordinate],
    grounded_coordinates: Iterable[Coordinate],
    *,
    protected_prefix: int = 12,
    seed_cap: int = 4,
) -> list[Coordinate]:
    """Insert new grounded seeds after the immutable parent prefix."""

    parent = list(dict.fromkeys(tuple(value) for value in parent_coordinates))
    parent_set = set(parent)
    grounded = []
    for value in grounded_coordinates:
        coordinate = tuple(value)
        if coordinate in parent_set or coordinate in grounded:
            continue
        grounded.append(coordinate)
        if len(grounded) >= max(0, int(seed_cap)):
            break
    split = min(max(0, int(protected_prefix)), len(parent))
    return [*parent[:split], *grounded, *parent[split:]]
