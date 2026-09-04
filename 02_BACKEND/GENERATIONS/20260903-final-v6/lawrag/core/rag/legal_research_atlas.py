"""Deterministic legal-instrument inventory and hierarchy navigation.

The atlas is deliberately narrower than a search index.  It answers three
questions without ranking or legal inference:

* which *current* instruments exist in the loaded :class:`~.index.Index`;
* which norm layer each instrument belongs to; and
* how to walk from an instrument through structural containers to article
  roots without flattening the whole corpus into one global candidate list.

``InstrumentProfile`` is a separate, optional LLM observation layer.  It is a
routing hint, not a canonical legal fact.  The compiler receives a closed menu
of instrument and navigation IDs, calls only the product-model allowlist
model, and deterministically drops every ID outside that menu.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import quote

from lawrag.core.legal_coordinate import parse_label
from lawrag.core.rag.index import DocView, Index


PROFILE_MODEL = "claude-haiku-4-5-20251001"


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class NormLayer(_StrEnum):
    """Formal/source layer derived only from current corpus metadata."""

    STATUTE = "STATUTE"
    ENFORCEMENT_DECREE = "ENFORCEMENT_DECREE"
    ENFORCEMENT_RULE = "ENFORCEMENT_RULE"
    ADMINISTRATIVE_RULE = "ADMINISTRATIVE_RULE"
    SUPERVISORY_REGULATION = "SUPERVISORY_REGULATION"
    IMPLEMENTING_RULE = "IMPLEMENTING_RULE"
    SELF_REGULATORY_RULE = "SELF_REGULATORY_RULE"
    INTERNAL_RULE = "INTERNAL_RULE"
    FORM_OR_MODEL = "FORM_OR_MODEL"
    REVIEW_MATERIAL = "REVIEW_MATERIAL"
    OTHER = "OTHER"


class InstrumentRole(_StrEnum):
    """Routing role, not a statement of legal force or priority."""

    PRIMARY_ACT = "PRIMARY_ACT"
    CROSS_CUTTING_ACT = "CROSS_CUTTING_ACT"
    DELEGATED_LEGISLATION = "DELEGATED_LEGISLATION"
    SUPERVISORY_RULE = "SUPERVISORY_RULE"
    IMPLEMENTATION_DETAIL = "IMPLEMENTATION_DETAIL"
    SELF_REGULATORY_RULE = "SELF_REGULATORY_RULE"
    INTERNAL_RULE = "INTERNAL_RULE"
    FORM_OR_GUIDANCE = "FORM_OR_GUIDANCE"
    FACT_SOURCE = "FACT_SOURCE"
    OTHER = "OTHER"


class NavigationKind(_StrEnum):
    CONTAINER = "CONTAINER"
    ARTICLE = "ARTICLE"


_LAYER_ORDER = {
    NormLayer.STATUTE: 10,
    NormLayer.ENFORCEMENT_DECREE: 20,
    NormLayer.ENFORCEMENT_RULE: 30,
    NormLayer.ADMINISTRATIVE_RULE: 40,
    NormLayer.SUPERVISORY_REGULATION: 41,
    NormLayer.IMPLEMENTING_RULE: 50,
    NormLayer.SELF_REGULATORY_RULE: 60,
    NormLayer.INTERNAL_RULE: 70,
    NormLayer.FORM_OR_MODEL: 80,
    NormLayer.REVIEW_MATERIAL: 90,
    NormLayer.OTHER: 100,
}

_DEFINITION = re.compile(r"정의|용어")
_LEADING_PAREN_TITLE = re.compile(r"^\s*\([^)]*\)\s*")
_WHOLE_ARTICLE_DELETED = re.compile(
    r"^\s*(?:<\s*)?삭제(?:\s+[^>\n]*)?(?:\s*>)?"
    r"(?:\s*<\s*[^>]+\s*>)?\s*[.]?\s*$"
)


@dataclass(frozen=True)
class InstrumentRecord:
    instrument_id: str
    name: str
    source_kind: str
    norm_layer: NormLayer
    default_role: InstrumentRole
    series_key: str
    status: str
    enforce: str
    revised: str
    version: str
    node_count: int
    article_count: int
    body_article_count: int = 0
    nonbody_article_count: int = 0

    @property
    def id(self) -> str:
        return self.instrument_id

    @property
    def instrument_role(self) -> InstrumentRole:
        return self.default_role

    @property
    def layer_rank(self) -> int:
        return _LAYER_ORDER[self.norm_layer]

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "name": self.name,
            "source_kind": self.source_kind,
            "norm_layer": self.norm_layer.value,
            "default_role": self.default_role.value,
            "series_key": self.series_key,
            "status": self.status,
            "enforce": self.enforce,
            "revised": self.revised,
            "version": self.version,
            "node_count": self.node_count,
            "article_count": self.article_count,
            "body_article_count": self.body_article_count,
            "nonbody_article_count": self.nonbody_article_count,
        }


@dataclass(frozen=True)
class NavigationUnit:
    """One closed-menu step in an instrument hierarchy.

    Article roots are leaves by design.  Paragraph, subparagraph, and item
    nodes remain available through the underlying ``DocView`` once the article
    is selected, but they do not multiply the research navigation frontier.
    """

    id: str
    instrument_id: str
    node_id: object
    parent_node_id: object | None
    path: str
    label: str
    kind: NavigationKind
    has_children: bool
    coordinate_scope: str = "body"
    is_default_route: bool = True
    status: str = "ACTIVE_OR_UNDETERMINED"
    preview: str = ""

    @property
    def coordinate(self) -> str:
        return f"{self.instrument_id}:{self.node_id}"

    @property
    def coordinate_tuple(self) -> tuple[str, object]:
        return self.instrument_id, self.node_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "instrument_id": self.instrument_id,
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "coordinate": self.coordinate,
            "path": self.path,
            "label": self.label,
            "kind": self.kind.value,
            "has_children": self.has_children,
            "coordinate_scope": self.coordinate_scope,
            "is_default_route": self.is_default_route,
            "status": self.status,
            "preview": self.preview,
        }


@dataclass(frozen=True)
class InstrumentProfile:
    """LLM-compiled routing observation over closed corpus identifiers."""

    instrument_id: str
    roles: tuple[InstrumentRole, ...]
    entry_point_ids: tuple[str, ...]
    definition_point_ids: tuple[str, ...]
    topic_tags: tuple[str, ...]
    scope_note: str
    rationale: str
    model: str = PROFILE_MODEL
    status: str = "LLM_ROUTING_HINT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "roles": [role.value for role in self.roles],
            "entry_point_ids": list(self.entry_point_ids),
            "definition_point_ids": list(self.definition_point_ids),
            "topic_tags": list(self.topic_tags),
            "scope_note": self.scope_note,
            "rationale": self.rationale,
            "model": self.model,
            "status": self.status,
        }


@dataclass(frozen=True)
class ProfileRejection:
    instrument_id: str
    field: str
    value: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "field": self.field,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProfileCompilation:
    profiles: tuple[InstrumentProfile, ...]
    missing_instrument_ids: tuple[str, ...]
    rejections: tuple[ProfileRejection, ...]
    raw_output: Mapping[str, Any] | None
    model: str = PROFILE_MODEL

    @property
    def rejected_external_id_count(self) -> int:
        return sum(
            rejection.reason
            in {
                "instrument_not_in_closed_menu",
                "entry_point_not_in_closed_menu",
                "entry_point_owner_mismatch",
            }
            for rejection in self.rejections
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profiles": [profile.to_dict() for profile in self.profiles],
            "missing_instrument_ids": list(self.missing_instrument_ids),
            "rejections": [row.to_dict() for row in self.rejections],
            "raw_output": dict(self.raw_output) if self.raw_output is not None else None,
            "model": self.model,
            "rejected_external_id_count": self.rejected_external_id_count,
        }


class ClosedIdentifierError(ValueError):
    """The caller attempted to put a non-corpus identifier in the menu."""


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


def _is_article(view: DocView, node: Mapping[str, Any]) -> bool:
    """Recognize corpus article roots without promoting synthetic labels.

    ``family=kr_article`` is the strongest ingestion signal and is retained in
    addenda/annexes.  The coordinate parser is a fallback only in the ordinary
    body scope; otherwise a label that merely *looks* like ``제N조`` could turn
    a repeated/synthetic structure node into a canonical article root.
    """

    parsed = parse_label(str(node.get("surface") or ""))
    if parsed is None or parsed.unit != "조":
        # Some sources label an addendum wrapper itself as ``kr_article``.
        # Requiring a parsed 조 coordinate prevents ``부칙`` from becoming a
        # leaf that hides all of its real 제N조 children.
        return False
    return bool(
        str(node.get("family") or "") == "kr_article"
        or view.coordinate_scope(node.get("id")) == "body"
    )


def _node_preview(view: DocView, node: Mapping[str, Any], cap: int = 240) -> str:
    return re.sub(r"\s+", " ", view.section_text(dict(node), cap=cap)).strip()


def _article_status(
    view: DocView,
    node: Mapping[str, Any],
    preview: str,
) -> str:
    """Mark only a wholly deleted article; a deleted paragraph is not enough."""

    remainder = preview
    surface = str(node.get("surface") or "").strip()
    if surface and remainder.startswith(surface):
        remainder = remainder[len(surface):]
    remainder = _LEADING_PAREN_TITLE.sub("", remainder, count=1)
    title = str(node.get("title") or "").strip()
    if title and remainder.startswith(title):
        remainder = remainder[len(title):]
    return "DELETED" if _WHOLE_ARTICLE_DELETED.fullmatch(remainder) else \
        "ACTIVE_OR_UNDETERMINED"


def _node_menu_id(instrument_id: str, node_id: object) -> str:
    encoded = quote(
        json.dumps(
            node_id,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
        safe="",
    )
    return f"nav:{instrument_id}:{encoded}"


def _node_label(node: Mapping[str, Any]) -> str:
    surface = str(node.get("surface") or "").strip()
    title = str(node.get("title") or "").strip()
    if surface and title and surface not in title:
        return f"{surface} {title}"
    return title or surface


def _series_key(view: DocView) -> str:
    if view.series.strip():
        return view.series.strip()
    name = re.sub(r"\s+", "", view.name)
    for suffix in ("시행세칙", "시행규칙", "시행령"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def classify_instrument(view: DocView) -> tuple[NormLayer, InstrumentRole]:
    """Classify by stable source metadata and document name, without an LLM."""

    kind = view.kind.strip().casefold()
    compact_name = re.sub(r"\s+", "", view.name)

    if kind == "law":
        if compact_name.endswith("시행령"):
            return NormLayer.ENFORCEMENT_DECREE, InstrumentRole.DELEGATED_LEGISLATION
        if compact_name.endswith("시행규칙"):
            return NormLayer.ENFORCEMENT_RULE, InstrumentRole.IMPLEMENTATION_DETAIL
        return NormLayer.STATUTE, InstrumentRole.PRIMARY_ACT

    if kind == "admrul":
        if "시행세칙" in compact_name:
            return NormLayer.IMPLEMENTING_RULE, InstrumentRole.IMPLEMENTATION_DETAIL
        if "감독규정" in compact_name:
            return NormLayer.SUPERVISORY_REGULATION, InstrumentRole.SUPERVISORY_RULE
        return NormLayer.ADMINISTRATIVE_RULE, InstrumentRole.SUPERVISORY_RULE

    if kind in {"kofia-rule", "krx-rule"}:
        return NormLayer.SELF_REGULATORY_RULE, InstrumentRole.SELF_REGULATORY_RULE
    if kind == "internal":
        return NormLayer.INTERNAL_RULE, InstrumentRole.INTERNAL_RULE
    if kind in {"krx-form", "klca-model"} or kind.endswith("-form"):
        return NormLayer.FORM_OR_MODEL, InstrumentRole.FORM_OR_GUIDANCE
    if kind in {"review-request", "case-material"}:
        return NormLayer.REVIEW_MATERIAL, InstrumentRole.FACT_SOURCE
    return NormLayer.OTHER, InstrumentRole.OTHER


def _record(instrument_id: str, view: DocView) -> InstrumentRecord:
    layer, role = classify_instrument(view)
    article_nodes = [node for node in view.nodes if _is_article(view, node)]
    body_count = sum(
        view.coordinate_scope(node.get("id")) == "body" for node in article_nodes
    )
    return InstrumentRecord(
        instrument_id=instrument_id,
        name=view.name,
        source_kind=view.kind,
        norm_layer=layer,
        default_role=role,
        series_key=_series_key(view),
        status=view.status or "현행",
        enforce=view.enforce,
        revised=view.revised,
        version=view.version,
        node_count=len(view.nodes),
        article_count=len(article_nodes),
        body_article_count=body_count,
        nonbody_article_count=len(article_nodes) - body_count,
    )


def _current_index(index: Index) -> Index:
    # ``scoped(None)`` is the Index contract for the canonical/current entry
    # generation: old internal versions and non-canonical law generations are
    # excluded, while ``docs`` remains available for coordinate dereference.
    return index.scoped(None)


def build_inventory(index: Index) -> tuple[InstrumentRecord, ...]:
    """Return a stable inventory of the Index's canonical/current documents."""

    current = _current_index(index)
    rows = [_record(instrument_id, view)
            for instrument_id, view in current.entry_docs.items()]
    rows.sort(key=lambda row: (row.layer_rank, row.name, row.instrument_id))
    return tuple(rows)


class LegalResearchAtlas:
    """Read-only current-instrument inventory plus article-root navigator."""

    def __init__(self, index: Index):
        self._index = _current_index(index)
        self._views: dict[str, DocView] = dict(self._index.entry_docs)
        self._instruments = build_inventory(index)
        self._instrument_by_id = {
            record.instrument_id: record for record in self._instruments
        }
        self._unit_by_coordinate: dict[tuple[str, object], NavigationUnit] = {}
        self._unit_by_menu_id: dict[str, NavigationUnit] = {}
        self._children: dict[
            tuple[str, object | None], tuple[NavigationUnit, ...]
        ] = {}
        self._units: dict[str, tuple[NavigationUnit, ...]] = {}
        self._articles: dict[str, tuple[NavigationUnit, ...]] = {}
        # Query-independent normalized label/preview text is compiled while
        # the generation-pinned atlas is admitted.  Re-normalizing all 17k+
        # article previews for every branch was pure repeated work.
        self._article_search_rows: dict[
            str, tuple[tuple[NavigationUnit, str], ...]
        ] = {}
        self._build_navigation()

    @classmethod
    def from_index(cls, index: Index) -> "LegalResearchAtlas":
        return cls(index)

    @property
    def current_index(self) -> Index:
        return self._index

    @property
    def instruments(self) -> tuple[InstrumentRecord, ...]:
        return self._instruments

    @property
    def current_document_ids(self) -> tuple[str, ...]:
        return tuple(record.instrument_id for record in self._instruments)

    def instrument(self, instrument_id: str) -> InstrumentRecord | None:
        return self._instrument_by_id.get(str(instrument_id))

    def related_instruments(self, instrument_id: str) -> tuple[InstrumentRecord, ...]:
        record = self.instrument(instrument_id)
        if record is None:
            return ()
        return tuple(
            candidate for candidate in self._instruments
            if candidate.series_key == record.series_key
        )

    def _build_navigation(self) -> None:
        for record in self._instruments:
            instrument_id = record.instrument_id
            view = self._views[instrument_id]
            node_by_id = view.by_id
            article_ids = {
                node.get("id") for node in view.nodes if _is_article(view, node)
            }

            # Only article roots and their ancestors belong to the research
            # navigator.  Sub-article units are evidence materialized after an
            # article selection, not additional hierarchy choices.
            navigable_ids = set(article_ids)
            for article_id in article_ids:
                current = node_by_id.get(article_id)
                seen: set[object] = set()
                while current is not None:
                    parent = current.get("parent")
                    if (
                        parent is None
                        or parent == current.get("id")
                        or parent in seen
                    ):
                        break
                    seen.add(parent)
                    if parent not in node_by_id:
                        break
                    navigable_ids.add(parent)
                    current = node_by_id.get(parent)

            raw_children: dict[object | None, list[object]] = defaultdict(list)
            ordered_ids: list[object] = []
            seen_ids: set[object] = set()
            for node in view.nodes:
                node_id = node.get("id")
                if node_id not in navigable_ids or node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                ordered_ids.append(node_id)
                parent = node.get("parent")
                if parent == node_id or parent not in navigable_ids:
                    parent = None
                raw_children[parent].append(node_id)

            for child_ids in raw_children.values():
                child_ids.sort(key=lambda child_id: (
                    ((node_by_id.get(child_id) or {}).get("span") or [10**12])[0],
                    repr(child_id),
                ))

            units: list[NavigationUnit] = []
            for node_id in ordered_ids:
                node = node_by_id[node_id]
                kind = (
                    NavigationKind.ARTICLE
                    if node_id in article_ids else NavigationKind.CONTAINER
                )
                parent = node.get("parent")
                if parent == node_id or parent not in navigable_ids:
                    parent = None
                coordinate_scope = view.coordinate_scope(node_id) or "body"
                preview = _node_preview(view, node)
                unit = NavigationUnit(
                    id=_node_menu_id(instrument_id, node_id),
                    instrument_id=instrument_id,
                    node_id=node_id,
                    parent_node_id=parent,
                    path=view.path(node_id),
                    label=_node_label(node),
                    kind=kind,
                    has_children=(
                        kind is NavigationKind.CONTAINER
                        and bool(raw_children.get(node_id))
                    ),
                    coordinate_scope=coordinate_scope,
                    is_default_route=coordinate_scope == "body",
                    status=(
                        _article_status(view, node, preview)
                        if kind is NavigationKind.ARTICLE
                        else "STRUCTURAL_CONTAINER"
                    ),
                    preview=preview,
                )
                units.append(unit)
                self._unit_by_coordinate[(instrument_id, node_id)] = unit
                self._unit_by_menu_id[unit.id] = unit

            by_node = {unit.node_id: unit for unit in units}
            for parent, child_ids in raw_children.items():
                self._children[(instrument_id, parent)] = tuple(
                    by_node[node_id] for node_id in child_ids if node_id in by_node
                )
            self._units[instrument_id] = tuple(units)
            self._articles[instrument_id] = tuple(
                unit for unit in units if unit.kind is NavigationKind.ARTICLE
            )
            self._article_search_rows[instrument_id] = tuple(
                (
                    unit,
                    re.sub(
                        r"\s+", "", f"{unit.label} {unit.preview}"
                    ).casefold(),
                )
                for unit in self._articles[instrument_id]
            )

    def unit(
        self, instrument_id: str, node_id: object
    ) -> NavigationUnit | None:
        return self._unit_by_coordinate.get((str(instrument_id), node_id))

    def resolve_menu_id(self, menu_id: str) -> NavigationUnit | None:
        return self._unit_by_menu_id.get(str(menu_id))

    def all_units(self, instrument_id: str) -> tuple[NavigationUnit, ...]:
        return self._units.get(str(instrument_id), ())

    def article_units(self, instrument_id: str) -> tuple[NavigationUnit, ...]:
        return self._articles.get(str(instrument_id), ())

    def article_search_rows(
        self, instrument_id: str,
    ) -> tuple[tuple[NavigationUnit, str], ...]:
        """Return generation-compiled normalized label/preview search rows."""

        return self._article_search_rows.get(str(instrument_id), ())

    def children(
        self,
        instrument_id: str,
        parent_node_id: object | None,
    ) -> tuple[NavigationUnit, ...]:
        instrument_id = str(instrument_id)
        if instrument_id not in self._instrument_by_id:
            return ()
        if parent_node_id is not None:
            parent = self.unit(instrument_id, parent_node_id)
            if parent is None or parent.kind is NavigationKind.ARTICLE:
                return ()
        return self._children.get((instrument_id, parent_node_id), ())

    def is_ancestor(
        self,
        instrument_id: str,
        ancestor_node_id: object,
        descendant_node_id: object,
    ) -> bool:
        """Return strict ancestry; a node is not its own ancestor."""

        instrument_id = str(instrument_id)
        view = self._views.get(instrument_id)
        if (
            view is None
            or ancestor_node_id == descendant_node_id
            or ancestor_node_id not in view.by_id
            or descendant_node_id not in view.by_id
        ):
            return False
        current = view.by_id.get(descendant_node_id)
        seen: set[object] = set()
        while current is not None:
            parent = current.get("parent")
            if parent is None or parent in seen:
                return False
            if parent == ancestor_node_id:
                return True
            seen.add(parent)
            current = view.by_id.get(parent)
        return False

    def definition_units(self, instrument_id: str) -> tuple[NavigationUnit, ...]:
        return tuple(
            unit for unit in self.article_units(instrument_id)
            if _DEFINITION.search(unit.label)
        )

    def profile_entry_candidates(
        self, instrument_id: str
    ) -> tuple[NavigationUnit, ...]:
        """Small closed menu: top hierarchy rungs plus explicit definition articles."""

        rows = [*self.children(instrument_id, None),
                *self.definition_units(instrument_id)]
        seen: set[str] = set()
        return tuple(
            row for row in rows
            if not (row.id in seen or seen.add(row.id))
        )

    def to_inventory_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "legal-research-atlas-v1",
            "authority_generation": self._index.authority_generation,
            "authority_as_of": self._index.authority_as_of,
            "current_document_count": len(self._instruments),
            "instruments": [record.to_dict() for record in self._instruments],
        }


def build_atlas(index: Index) -> LegalResearchAtlas:
    return LegalResearchAtlas.from_index(index)


PROFILE_SYSTEM = """너는 금융규제 법률 리서치용 법령 지도를 만드는 라우터다.
법률 결론을 내리지 말고, 제공된 실제 법령과 실제 목차 ID만 이용해 각 법령의 전형적
역할과 탐색 시작점을 표시한다.

규칙:
1. instrument_id와 entry/definition point ID는 메뉴에 있는 값만 그대로 고른다.
2. 역할은 제공된 enum에서 고른다. 법적 효력의 우열이나 위임의 적법성을 추정하지 않는다.
3. 정의조는 definition_point_ids에, 일반 탐색 시작점은 entry_point_ids에 둔다.
4. 이름과 목차만으로 모르는 내용은 scope_note에 모른다고 적고 조문 내용을 만들지 않는다.
5. 이 출력은 검색 라우팅 힌트이며 법적 결론이나 정본 분류가 아니다."""


def _closed_entry_map(
    atlas: LegalResearchAtlas,
    instrument_ids: Sequence[str],
    candidate_unit_ids: Mapping[str, Sequence[str]] | None,
) -> dict[str, tuple[str, ...]]:
    requested = set(instrument_ids)
    if candidate_unit_ids is not None:
        unknown_keys = set(map(str, candidate_unit_ids)) - requested
        if unknown_keys:
            raise ClosedIdentifierError(
                f"entry-point map contains unrequested instruments: {sorted(unknown_keys)}"
            )

    result: dict[str, tuple[str, ...]] = {}
    for instrument_id in instrument_ids:
        values = (
            candidate_unit_ids.get(instrument_id, ())
            if candidate_unit_ids is not None
            else tuple(
                unit.id for unit in atlas.profile_entry_candidates(instrument_id)
            )
        )
        accepted: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            value = str(raw_value)
            if value in seen:
                continue
            unit = atlas.resolve_menu_id(value)
            if unit is None:
                raise ClosedIdentifierError(f"unknown navigation ID: {value}")
            if unit.instrument_id != instrument_id:
                raise ClosedIdentifierError(
                    f"navigation ID {value} does not belong to {instrument_id}"
                )
            seen.add(value)
            accepted.append(value)
        result[instrument_id] = tuple(accepted)
    return result


def profile_schema(
    instrument_ids: Sequence[str],
    closed_entry_ids: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    instrument_values = list(instrument_ids)
    entry_values = list(dict.fromkeys(
        entry_id
        for instrument_id in instrument_ids
        for entry_id in closed_entry_ids.get(instrument_id, ())
    ))
    instrument_schema: dict[str, Any] = {"type": "string"}
    if instrument_values:
        instrument_schema["enum"] = instrument_values
    entry_id_schema: dict[str, Any] = {"type": "string"}
    if entry_values:
        entry_id_schema["enum"] = entry_values
    entry_array_schema: dict[str, Any] = {
        "type": "array",
        "items": entry_id_schema,
        "uniqueItems": True,
    }
    if not entry_values:
        entry_array_schema["maxItems"] = 0
        entry_array_schema["description"] = (
            "No eligible entry-point IDs exist; return an empty array."
        )
    role_enum = [role.value for role in InstrumentRole]
    profiles_schema: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "instrument_id": instrument_schema,
                "roles": {
                    "type": "array",
                    "items": {"type": "string", "enum": role_enum},
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": True,
                },
                "entry_point_ids": deepcopy(entry_array_schema),
                "definition_point_ids": deepcopy(entry_array_schema),
                "topic_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
                "scope_note": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": [
                "instrument_id", "roles", "entry_point_ids",
                "definition_point_ids", "topic_tags", "scope_note",
                "rationale",
            ],
            "additionalProperties": False,
        },
    }
    if not instrument_values:
        profiles_schema["maxItems"] = 0
        profiles_schema["description"] = (
            "No legal instruments were provided; return an empty array."
        )
    return {
        "type": "object",
        "properties": {
            "profiles": profiles_schema,
        },
        "required": ["profiles"],
        "additionalProperties": False,
    }


def _clean_text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def sanitize_profile_output(
    atlas: LegalResearchAtlas,
    raw_output: Mapping[str, Any] | None,
    instrument_ids: Sequence[str],
    closed_entry_ids: Mapping[str, Sequence[str]],
    *,
    model: str = PROFILE_MODEL,
) -> ProfileCompilation:
    """Accept only requested instruments and their exact navigation IDs."""

    requested = tuple(dict.fromkeys(map(str, instrument_ids)))
    requested_set = set(requested)
    allowed = {
        instrument_id: set(map(str, closed_entry_ids.get(instrument_id, ())))
        for instrument_id in requested
    }
    valid_roles = {role.value: role for role in InstrumentRole}
    definition_ids = {
        instrument_id: {
            unit.id for unit in atlas.definition_units(instrument_id)
        }
        for instrument_id in requested
    }
    profiles: list[InstrumentProfile] = []
    rejections: list[ProfileRejection] = []
    seen_instruments: set[str] = set()

    rows = raw_output.get("profiles") if isinstance(raw_output, Mapping) else ()
    for raw_row in rows or ():
        if not isinstance(raw_row, Mapping):
            rejections.append(ProfileRejection("", "profiles", "", "row_not_object"))
            continue
        instrument_id = str(raw_row.get("instrument_id") or "")
        if instrument_id not in requested_set:
            rejections.append(ProfileRejection(
                instrument_id, "instrument_id", instrument_id,
                "instrument_not_in_closed_menu",
            ))
            continue
        if instrument_id in seen_instruments:
            rejections.append(ProfileRejection(
                instrument_id, "instrument_id", instrument_id,
                "duplicate_instrument_profile",
            ))
            continue

        roles: list[InstrumentRole] = []
        seen_roles: set[InstrumentRole] = set()
        for raw_role in raw_row.get("roles") or ():
            role = valid_roles.get(str(raw_role))
            if role is None:
                rejections.append(ProfileRejection(
                    instrument_id, "roles", str(raw_role), "unknown_role",
                ))
                continue
            if role not in seen_roles:
                seen_roles.add(role)
                roles.append(role)
            if len(roles) >= 4:
                break
        if not roles:
            rejections.append(ProfileRejection(
                instrument_id, "roles", "", "missing_valid_role",
            ))
            continue

        def points(field: str, definitions_only: bool = False) -> tuple[str, ...]:
            accepted: list[str] = []
            seen: set[str] = set()
            for raw_id in raw_row.get(field) or ():
                entry_id = str(raw_id)
                if entry_id in seen:
                    continue
                seen.add(entry_id)
                unit = atlas.resolve_menu_id(entry_id)
                if entry_id not in allowed[instrument_id] or unit is None:
                    rejections.append(ProfileRejection(
                        instrument_id, field, entry_id,
                        "entry_point_not_in_closed_menu",
                    ))
                    continue
                if unit.instrument_id != instrument_id:
                    rejections.append(ProfileRejection(
                        instrument_id, field, entry_id,
                        "entry_point_owner_mismatch",
                    ))
                    continue
                if definitions_only and entry_id not in definition_ids[instrument_id]:
                    rejections.append(ProfileRejection(
                        instrument_id, field, entry_id,
                        "not_a_definition_article",
                    ))
                    continue
                accepted.append(entry_id)
            return tuple(accepted)

        topic_tags: list[str] = []
        seen_tags: set[str] = set()
        for value in raw_row.get("topic_tags") or ():
            tag = _clean_text(value, 60)
            if tag and tag not in seen_tags:
                seen_tags.add(tag)
                topic_tags.append(tag)
            if len(topic_tags) >= 8:
                break

        seen_instruments.add(instrument_id)
        profiles.append(InstrumentProfile(
            instrument_id=instrument_id,
            roles=tuple(roles),
            entry_point_ids=points("entry_point_ids"),
            definition_point_ids=points(
                "definition_point_ids", definitions_only=True,
            ),
            topic_tags=tuple(topic_tags),
            scope_note=_clean_text(raw_row.get("scope_note"), 600),
            rationale=_clean_text(raw_row.get("rationale"), 600),
            model=model,
        ))

    profiles.sort(key=lambda row: requested.index(row.instrument_id))
    missing = tuple(
        instrument_id for instrument_id in requested
        if instrument_id not in seen_instruments
    )
    preserved_raw = dict(raw_output) if isinstance(raw_output, Mapping) else None
    return ProfileCompilation(
        profiles=tuple(profiles),
        missing_instrument_ids=missing,
        rejections=tuple(rejections),
        raw_output=preserved_raw,
        model=model,
    )


def compile_instrument_profiles(
    llm: StructuredLLM,
    atlas: LegalResearchAtlas,
    instrument_ids: Sequence[str],
    *,
    domain_context: str = "대한민국 금융규제",
    candidate_unit_ids: Mapping[str, Sequence[str]] | None = None,
    model: str = PROFILE_MODEL,
) -> ProfileCompilation:
    """Compile optional routing profiles through a closed-ID model call.

    The default remains ``PROFILE_MODEL``.  An isolated onsite deployment may
    bind the same closed-ID contract to its Qwen model; unknown caller IDs fail
    before the call and unknown provider IDs remain rejection receipts.
    """

    requested = tuple(dict.fromkeys(map(str, instrument_ids)))
    unknown = [
        instrument_id for instrument_id in requested
        if atlas.instrument(instrument_id) is None
    ]
    if unknown:
        raise ClosedIdentifierError(f"unknown instrument IDs: {unknown}")
    closed_entries = _closed_entry_map(atlas, requested, candidate_unit_ids)
    if not requested:
        return ProfileCompilation((), (), (), None, model=model)

    payload = {
        "domain_context": _clean_text(domain_context, 500),
        "instruments": [],
    }
    for instrument_id in requested:
        record = atlas.instrument(instrument_id)
        assert record is not None
        payload["instruments"].append({
            **record.to_dict(),
            "entry_point_menu": [
                atlas.resolve_menu_id(entry_id).to_dict()
                for entry_id in closed_entries[instrument_id]
                if atlas.resolve_menu_id(entry_id) is not None
            ],
        })

    raw = llm.structured(
        "rag.legal_research_atlas.profile",
        PROFILE_SYSTEM,
        json.dumps(payload, ensure_ascii=False, indent=2),
        profile_schema(requested, closed_entries),
        max_tokens=3200,
        effort=None,
        model=model,
    )
    return sanitize_profile_output(
        atlas, raw, requested, closed_entries, model=model,
    )


__all__ = [
    "PROFILE_MODEL",
    "ClosedIdentifierError",
    "InstrumentProfile",
    "InstrumentRecord",
    "InstrumentRole",
    "LegalResearchAtlas",
    "NavigationKind",
    "NavigationUnit",
    "NormLayer",
    "ProfileCompilation",
    "ProfileRejection",
    "StructuredLLM",
    "build_atlas",
    "build_inventory",
    "classify_instrument",
    "compile_instrument_profiles",
    "profile_schema",
    "sanitize_profile_output",
]
