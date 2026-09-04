"""Gold-blind legal-system and article entry routing.

This module turns a structured question plan into two bounded, closed-corpus
menus.  It does not decide the legal merits:

* instruments are ranked from their name, norm role, versioned purpose and
  closed legal-system family profile;
* articles inside each instrument reuse current-generation Legal Graph
  semantic cards, with current source text only as a compatibility fallback;
* structured actor/action/object/quantity matches are retained separately so a
  numeric collision cannot masquerade as a governing rule.

All returned identifiers already exist in :class:`LegalResearchAtlas`.  The
ranking is therefore a recall-oriented entry layer, not an authority source.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .legal_instrument_routing import InstrumentRouteBranch
from .legal_research_atlas import LegalResearchAtlas, NavigationUnit
from .legal_system_map import (
    LegalGraphSemanticCardIndex,
    LegalSystemMap,
    load_legal_system_map,
)


_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9%]+")
_NUMBER = re.compile(r"(?:\d+\s*분의\s*\d+|\d+(?:\.\d+)?\s*%)")
_LOW_INFORMATION = {
    "경우", "관련", "기준", "규정", "법률", "업무", "사항", "여부", "가능",
    "외부", "기관", "처리", "방법", "범위", "요건", "행위",
}
_ROLE_WEIGHTS = {
    "SOURCE_ACTOR": 34,
    "TARGET_ACTOR": 30,
    "ACTION": 38,
    "OBJECT": 38,
    "QUANTITY": 90,
    "LEGAL_REFERENCE": 105,
    "CONDITION": 28,
    "EXCEPTION": 28,
}
_AXIS_TERMS: dict[str, tuple[str, ...]] = {
    "FORMULA": ("비율", "산정", "계산", "합산", "분의", "%"),
    "THRESHOLD": ("이상", "이하", "초과", "미만", "분의", "%"),
    "AUTHORITY": ("권한", "이사회", "승인", "의결", "결정"),
    "DELEGATION": ("위탁", "수탁", "재위탁", "위임", "대리"),
    "CLASSIFICATION": ("구분", "분류", "해당", "정의", "범위"),
    "LEGAL_BASIS": ("근거", "따라", "준용", "적용", "규정"),
    "EXCEPTION": ("다만", "제외", "불구하고", "예외"),
    "NEGATIVE_AUTHORITY": ("금지", "제한", "하여서는 아니", "할 수 없다"),
}

_AUTO_SEMANTIC_INDEX = object()
_LAW_FAMILY_ANCHOR_BOOST = 420.0
_LAW_FAMILY_DEPTH_PENALTY = 40.0


def _norm(value: object) -> str:
    return _SPACE.sub("", str(value or "")).lower()


def _tokens(value: object) -> tuple[str, ...]:
    rows: list[str] = []
    for token in _TOKEN.findall(str(value or "")):
        normalized = _norm(token)
        if len(normalized) < 2 or normalized in _LOW_INFORMATION:
            continue
        rows.append(normalized)
    return tuple(dict.fromkeys(rows))


@dataclass(frozen=True, slots=True)
class QuerySignal:
    surface: str
    normalized: str
    role: str
    weight: int


@dataclass(frozen=True, slots=True)
class ArticleEntryScore:
    unit: NavigationUnit
    score: float
    matched_roles: tuple[str, ...]
    matched_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.unit.id,
            "instrument_id": self.unit.instrument_id,
            "node_id": self.unit.node_id,
            "path": self.unit.path,
            "label": self.unit.label,
            "score": round(self.score, 3),
            "matched_roles": list(self.matched_roles),
            "matched_signals": list(self.matched_signals),
        }


@dataclass(frozen=True, slots=True)
class InstrumentEntryScore:
    instrument_id: str
    score: float
    entry_points: tuple[ArticleEntryScore, ...]
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "score": round(self.score, 3),
            "signals": list(self.signals),
            "entry_points": [row.to_dict() for row in self.entry_points],
        }


@dataclass(frozen=True, slots=True)
class BranchEntryPlan:
    branch_id: str
    issue_axis: str
    instruments: tuple[InstrumentEntryScore, ...]

    @property
    def preferred_instrument_ids(self) -> tuple[str, ...]:
        return tuple(row.instrument_id for row in self.instruments)

    @property
    def entry_point_ids_by_instrument(self) -> dict[str, tuple[str, ...]]:
        return {
            row.instrument_id: tuple(point.unit.id for point in row.entry_points)
            for row in self.instruments
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "issue_axis": self.issue_axis,
            "instruments": [row.to_dict() for row in self.instruments],
        }


class LegalSystemEntryPlanner:
    """Build bounded law and article entry menus from current corpus text."""

    def __init__(
        self,
        atlas: LegalResearchAtlas,
        *,
        instrument_limit: int = 8,
        entry_limit: int = 12,
        system_map: LegalSystemMap | None = None,
        semantic_card_index: LegalGraphSemanticCardIndex | None | object = (
            _AUTO_SEMANTIC_INDEX
        ),
    ) -> None:
        if instrument_limit < 1 or entry_limit < 1:
            raise ValueError("entry planner limits must be positive")
        self.atlas = atlas
        self.instrument_limit = instrument_limit
        self.entry_limit = entry_limit
        # No best-effort fallback is allowed here.  A stale authority/effective
        # date/catalog must stop routing before hints from another generation
        # can enter the product context.
        self.system_map = system_map or load_legal_system_map(atlas)
        if semantic_card_index is _AUTO_SEMANTIC_INDEX:
            self.semantic_card_index: LegalGraphSemanticCardIndex | None = (
                LegalGraphSemanticCardIndex(atlas, self.system_map)
            )
        else:
            self.semantic_card_index = semantic_card_index  # type: ignore[assignment]
        self._text_cache: dict[str, str] = {}
        self._posting_coordinate_cache: dict[
            str, tuple[tuple[str, object], ...]
        ] = {}

    def _article_text(self, unit: NavigationUnit) -> str:
        cached = self._text_cache.get(unit.id)
        if cached is not None:
            return cached
        if self.semantic_card_index is not None:
            card = self.semantic_card_index.for_navigation(unit)
            if card is not None and card.search_text:
                # This is the existing Legal Graph projection, not newly
                # generated content.  It is used only for entry ranking.
                self._text_cache[unit.id] = card.search_text
                return card.search_text
        view = self.atlas.current_index.entry_docs.get(unit.instrument_id)
        node = view.by_id.get(unit.node_id) if view is not None else None
        text = str(view.section_text(dict(node), cap=10**9) or "") if node else ""
        self._text_cache[unit.id] = text
        return text

    @staticmethod
    def query_signals(
        query_plan: Mapping[str, Any], branch: InstrumentRouteBranch,
    ) -> tuple[QuerySignal, ...]:
        signals: list[QuerySignal] = []
        for row in query_plan.get("mentions") or ():
            if not isinstance(row, Mapping):
                continue
            surface = str(row.get("surface") or "").strip()
            role = str(row.get("role") or "OTHER").upper()
            normalized = _norm(surface)
            if len(normalized) >= 2:
                signals.append(QuerySignal(
                    surface, normalized, role, _ROLE_WEIGHTS.get(role, 22)
                ))
        exact = (query_plan.get("expansion_terms") or {}).get("exact") or ()
        for value in (*branch.topic_hints, *exact):
            surface = str(value).strip()
            normalized = _norm(surface)
            if len(normalized) >= 2:
                signals.append(QuerySignal(surface, normalized, "TOPIC", 16))
            for token in _tokens(surface):
                signals.append(QuerySignal(token, token, "TOKEN", 6))
        for term in _AXIS_TERMS.get(branch.issue_axis.upper(), ()):
            signals.append(QuerySignal(term, _norm(term), "AXIS", 11))
        unique: dict[tuple[str, str], QuerySignal] = {}
        for signal in signals:
            key = (signal.normalized, signal.role)
            previous = unique.get(key)
            if previous is None or signal.weight > previous.weight:
                unique[key] = signal
        return tuple(unique.values())

    def _score_article(
        self,
        unit: NavigationUnit,
        signals: Sequence[QuerySignal],
        issue_axis: str,
        semantic_signal_keys: frozenset[tuple[str, str]] = frozenset(),
    ) -> ArticleEntryScore:
        # A semantic posting is already positive evidence that the exact
        # closed-corpus term belongs to this article.  Do not aggregate every
        # provisional SemanticArticleCard merely to rediscover that match.
        # When no semantic index exists (small/offline fallback), retain the
        # current-source body compatibility path.
        body = self._article_text(unit) if self.semantic_card_index is None else ""
        haystack = _norm(f"{unit.label} {unit.preview} {body}")
        score = 0.0
        roles: set[str] = set()
        hits: list[str] = []
        for signal in signals:
            if (
                signal.normalized not in haystack
                and (signal.normalized, signal.role) not in semantic_signal_keys
            ):
                continue
            multiplier = 1.0
            if signal.role in {"SOURCE_ACTOR", "TARGET_ACTOR", "ACTION", "OBJECT"}:
                multiplier = 1.35
            elif signal.role == "QUANTITY":
                multiplier = 1.8
            elif signal.role == "LEGAL_REFERENCE":
                multiplier = 0.4
            score += signal.weight * multiplier
            roles.add(signal.role)
            if signal.role not in {"TOKEN", "TOPIC"} or len(signal.normalized) >= 4:
                hits.append(f"{signal.role}:{signal.surface}")
        # A combination of dimensions is more probative than repeated words.
        semantic_roles = roles & {
            "SOURCE_ACTOR", "TARGET_ACTOR", "ACTION", "OBJECT", "QUANTITY",
            "CONDITION", "EXCEPTION",
        }
        score += max(0, len(semantic_roles) - 1) * 42
        if "QUANTITY" in semantic_roles and len(semantic_roles) == 1:
            score -= 95
        if issue_axis.upper() in {"DELEGATION", "AUTHORITY"}:
            if "위탁" in haystack or "위임" in haystack:
                score += 24
        if "정의" in unit.label and issue_axis.upper() == "CLASSIFICATION":
            score += 35
        return ArticleEntryScore(
            unit=unit,
            score=score,
            matched_roles=tuple(sorted(roles)),
            matched_signals=tuple(dict.fromkeys(hits))[:24],
        )

    def plan_branch(
        self,
        question: str,
        query_plan: Mapping[str, Any],
        branch: InstrumentRouteBranch,
    ) -> BranchEntryPlan:
        signals = self.query_signals(query_plan, branch)
        question_norm = _norm(question)
        routing_context = _norm(
            " ".join((question, *(signal.surface for signal in signals)))
        )
        ranked: list[InstrumentEntryScore] = []
        preferred_role_values = {role.value for role in branch.preferred_roles}
        family_rows = self.system_map.matching_issue_families(
            routing_context, branch.issue_axis
        )
        family_ids = {
            instrument_id
            for family in family_rows
            for instrument_id in family.instrument_ids
        }

        # Use the existing semantic postings as the hierarchy's entry index.
        # Scoring every body of every article (17k+) on each question defeats
        # the law -> article hierarchy and made the deterministic router take
        # tens of seconds.  Individual terms are OR branches; AND is reserved
        # for the later evidence compiler.
        semantic_units: dict[str, dict[object, NavigationUnit]] = {}
        semantic_signal_keys: dict[
            tuple[str, object], set[tuple[str, str]]
        ] = {}
        if self.semantic_card_index is not None:
            search_terms: list[tuple[str, QuerySignal]] = []
            seen_search_terms: set[tuple[str, str, str]] = set()
            for signal in sorted(signals, key=lambda row: -row.weight):
                if signal.role == "TOKEN" and len(signal.normalized) < 4:
                    continue
                for term in (signal.surface, *_tokens(signal.surface)):
                    key = (_norm(term), signal.normalized, signal.role)
                    if len(key[0]) >= 2 and key not in seen_search_terms:
                        seen_search_terms.add(key)
                        search_terms.append((term, signal))
                if len(search_terms) >= 12:
                    break
            for term, source_signal in search_terms[:12]:
                coordinate_search = getattr(
                    self.semantic_card_index, "search_coordinates", None
                )
                if callable(coordinate_search):
                    term_key = _norm(term)
                    coordinates = self._posting_coordinate_cache.get(term_key)
                    if coordinates is None:
                        coordinates = coordinate_search((term,), limit=96)
                        self._posting_coordinate_cache[term_key] = coordinates
                else:
                    coordinates = tuple(
                        (card.instrument_id, card.node_id)
                        for card in self.semantic_card_index.search(
                            (term,), limit=96
                        )
                    )
                for instrument_id, node_id in coordinates:
                    unit = self.atlas.unit(instrument_id, node_id)
                    if unit is not None:
                        bucket = semantic_units.setdefault(instrument_id, {})
                        if (
                            unit.node_id not in bucket
                            and len(bucket) >= max(24, self.entry_limit * 2)
                        ):
                            continue
                        bucket[
                            unit.node_id
                        ] = unit
                        semantic_signal_keys.setdefault(
                            (instrument_id, unit.node_id), set()
                        ).add((source_signal.normalized, source_signal.role))

        coarse: list[tuple[float, str, list[str]]] = []
        cheap_units: dict[str, list[NavigationUnit]] = {}
        preferred_ids = set(branch.preferred_instrument_ids)
        profiles_by_id = self.system_map.profile_by_id
        anchor_depths_by_root: dict[str, list[int]] = {}
        anchor_ids: set[str] = set()
        for instrument in self.atlas.instruments:
            name_norm = _norm(instrument.name)
            if not (
                (name_norm and name_norm in question_norm)
                or instrument.instrument_id in preferred_ids
            ):
                continue
            profile = profiles_by_id.get(instrument.instrument_id)
            if profile is None or not profile.law_families:
                continue
            anchor_ids.add(instrument.instrument_id)
            for membership in profile.law_families:
                anchor_depths_by_root.setdefault(membership.root, []).append(
                    membership.depth
                )

        family_hint_by_id: dict[str, tuple[float, str]] = {}
        for instrument in self.atlas.instruments:
            if instrument.instrument_id in anchor_ids:
                continue
            profile = profiles_by_id.get(instrument.instrument_id)
            if profile is None:
                continue
            matches: list[tuple[float, str, int]] = []
            for membership in profile.law_families:
                anchor_depths = anchor_depths_by_root.get(membership.root)
                if not anchor_depths:
                    continue
                distance = min(
                    abs(membership.depth - anchor_depth)
                    for anchor_depth in anchor_depths
                )
                boost = max(
                    0.0,
                    _LAW_FAMILY_ANCHOR_BOOST - _LAW_FAMILY_DEPTH_PENALTY * distance,
                )
                if boost > 0:
                    matches.append((boost, membership.root, distance))
            if matches:
                boost, root, distance = sorted(
                    matches, key=lambda row: (-row[0], row[1], row[2])
                )[0]
                family_hint_by_id[instrument.instrument_id] = (
                    boost,
                    f"HELD_LAW_FAMILY_ROUTING_HINT:{root}:DISTANCE:{distance}",
                )
        for instrument in self.atlas.instruments:
            name_norm = _norm(instrument.name)
            law_name_hit = bool(name_norm and name_norm in question_norm)
            score = 0.0
            route_signals: list[str] = []
            if law_name_hit:
                score += 900
                route_signals.append("EXPLICIT_INSTRUMENT_NAME")
            if instrument.instrument_id in preferred_ids:
                score += 700
                route_signals.append("CLOSED_PREFERRED_INSTRUMENT")
            family_hint = family_hint_by_id.get(instrument.instrument_id)
            if family_hint is not None:
                score += family_hint[0]
                route_signals.append(family_hint[1])
            if instrument.instrument_id in family_ids:
                for family in family_rows:
                    if instrument.instrument_id in family.instrument_ids:
                        score += family.weight
                        route_signals.append(
                            f"LEGAL_SYSTEM_FAMILY:{family.family_id}"
                        )
            if instrument.instrument_id in semantic_units:
                score += 180 + min(120, 8 * len(semantic_units[instrument.instrument_id]))
                route_signals.append("SEMANTIC_POSTING_MATCH")
            profile = self.system_map.profile(instrument.instrument_id)
            if profile is not None and profile.purpose:
                purpose_norm = _norm(profile.purpose)
                purpose_hits = tuple(
                    signal for signal in signals
                    if signal.role != "TOKEN" and signal.normalized in purpose_norm
                )
                if purpose_hits:
                    score += min(
                        90.0,
                        sum(max(5.0, signal.weight * 0.35)
                            for signal in purpose_hits),
                    )
                    route_signals.append("PURPOSE_MATCH")
            if instrument.default_role.value in preferred_role_values:
                score += 18
                route_signals.append(f"ROLE:{instrument.default_role.value}")

            # Cheap label/preview scan is allowed globally; full article text
            # is opened only for the bounded instruments and coordinates below.
            label_hits: list[NavigationUnit] = []
            compiled_rows = getattr(self.atlas, "article_search_rows", None)
            search_rows = (
                compiled_rows(instrument.instrument_id)
                if callable(compiled_rows)
                else tuple(
                    (unit, _norm(f"{unit.label} {unit.preview}"))
                    for unit in self.atlas.article_units(instrument.instrument_id)
                )
            )
            for unit, haystack in search_rows:
                if any(
                    signal.normalized in haystack
                    for signal in signals
                    if signal.role != "TOKEN" or len(signal.normalized) >= 4
                ):
                    label_hits.append(unit)
                    if len(label_hits) >= 24:
                        break
            if label_hits:
                cheap_units[instrument.instrument_id] = label_hits
                score += 55 + min(45, 3 * len(label_hits))
                route_signals.append("ARTICLE_LABEL_MATCH")
            coarse.append((score, instrument.instrument_id, route_signals))

        coarse.sort(key=lambda row: (-row[0], row[1]))
        if len(self.atlas.instruments) <= max(32, self.instrument_limit * 4):
            candidate_ids = {instrument.instrument_id for instrument in self.atlas.instruments}
        else:
            strong = [row for row in coarse if row[0] > 18]
            candidate_ids = {
                row[1] for row in (strong or coarse)[: max(16, self.instrument_limit * 3)]
            }
        coarse_by_id = {instrument_id: (score, route_signals)
                        for score, instrument_id, route_signals in coarse}

        for instrument in self.atlas.instruments:
            if instrument.instrument_id not in candidate_ids:
                continue
            unit_by_id: dict[object, NavigationUnit] = {}
            unit_by_id.update(semantic_units.get(instrument.instrument_id, {}))
            for unit in cheap_units.get(instrument.instrument_id, ()):
                unit_by_id.setdefault(unit.node_id, unit)
            if not unit_by_id:
                for unit in self.atlas.article_units(instrument.instrument_id)[:4]:
                    unit_by_id[unit.node_id] = unit
            article_scores = [
                self._score_article(
                    unit,
                    signals,
                    branch.issue_axis,
                    frozenset(semantic_signal_keys.get(
                        (instrument.instrument_id, unit.node_id), ()
                    )),
                )
                for unit in unit_by_id.values()
            ]
            article_scores.sort(
                key=lambda row: (-row.score, row.unit.path, row.unit.id)
            )
            positive = tuple(row for row in article_scores if row.score > 0)
            coarse_score, route_signals = coarse_by_id[instrument.instrument_id]
            score = coarse_score + sum(
                row.score * weight
                for row, weight in zip(positive[:3], (1.0, 0.35, 0.15))
            )
            if positive:
                route_signals.append(
                    f"BEST_ARTICLE_SCORE:{round(positive[0].score, 3)}"
                )
            if score <= 0:
                continue
            ranked.append(InstrumentEntryScore(
                instrument_id=instrument.instrument_id,
                score=score,
                entry_points=positive[: self.entry_limit],
                signals=tuple(route_signals),
            ))
        ranked.sort(key=lambda row: (-row.score, row.instrument_id))
        return BranchEntryPlan(
            branch_id=branch.branch_id,
            issue_axis=branch.issue_axis,
            instruments=tuple(ranked[: self.instrument_limit]),
        )

    def plan(
        self,
        question: str,
        query_plan: Mapping[str, Any],
        branches: Sequence[InstrumentRouteBranch],
    ) -> tuple[BranchEntryPlan, ...]:
        return tuple(
            self.plan_branch(question, query_plan, branch) for branch in branches
        )


def apply_instrument_priors(
    branches: Sequence[InstrumentRouteBranch],
    plans: Sequence[BranchEntryPlan],
) -> tuple[InstrumentRouteBranch, ...]:
    """Return branch copies whose preferred IDs come only from the closed atlas."""

    by_id = {plan.branch_id: plan for plan in plans}
    rows: list[InstrumentRouteBranch] = []
    for branch in branches:
        plan = by_id.get(branch.branch_id)
        preferred = plan.preferred_instrument_ids if plan is not None else ()
        rows.append(InstrumentRouteBranch(
            branch_id=branch.branch_id,
            issue_axis=branch.issue_axis,
            preferred_roles=branch.preferred_roles,
            topic_hints=branch.topic_hints,
            preferred_instrument_ids=tuple(dict.fromkeys(
                (*preferred, *branch.preferred_instrument_ids)
            )),
            required=branch.required,
        ))
    return tuple(rows)


def scope_alignment(
    query_plan: Mapping[str, Any], text: str,
) -> dict[str, Any]:
    """Report structured semantic overlap without making a legal conclusion."""

    haystack = _norm(text)
    matched: dict[str, list[str]] = {}
    requested: dict[str, list[str]] = {}
    for row in query_plan.get("mentions") or ():
        if not isinstance(row, Mapping):
            continue
        role = str(row.get("role") or "OTHER").upper()
        surface = str(row.get("surface") or "").strip()
        normalized = _norm(surface)
        if len(normalized) < 2:
            continue
        requested.setdefault(role, []).append(surface)
        if normalized in haystack:
            matched.setdefault(role, []).append(surface)
    semantic = {"SOURCE_ACTOR", "TARGET_ACTOR", "ACTION", "OBJECT"}
    quantity_requested = bool(requested.get("QUANTITY"))
    quantity_matched = bool(matched.get("QUANTITY"))
    nonnumeric_roles = semantic & set(matched)
    numeric_only = quantity_matched and not nonnumeric_roles
    public_delegate = bool(
        re.search(r"(?:금융위원회|금융감독원장|정부|장관).{0,45}(?:위탁|위임)", text)
    )
    private_actor_requested = any(
        any(marker in _norm(value) for marker in ("회사", "업자", "법인"))
        for value in requested.get("SOURCE_ACTOR", ())
    )
    wrong_actor_delegation = public_delegate and private_actor_requested and not bool(
        matched.get("SOURCE_ACTOR")
    )
    aligned = not numeric_only and not wrong_actor_delegation and bool(
        nonnumeric_roles or (not semantic.intersection(requested) and quantity_matched)
    )
    return {
        "requested": requested,
        "matched": matched,
        "numeric_only": numeric_only,
        "wrong_actor_delegation": wrong_actor_delegation,
        "aligned": aligned,
    }
