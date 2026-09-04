"""Versioned legal-system routing catalog and Legal Graph card cache.

The catalog is deliberately a *routing* snapshot, not an additional source of
law.  It locks the complete current :class:`LegalResearchAtlas` inventory,
the official ``law_index.json`` generation and the Legal Graph generation.
Runtime profiles are reconstructed from those closed sources and compared
with the catalog fingerprints before a single routing hint is exposed.

The second half of this module is a lazy, process-local access layer over the
already compiled Legal Graph provision/semantic cards.  It reuses the graph's
article-root coordinates and terms instead of creating another LLM-derived
semantic store.  A routing hit from this cache remains a search hint; it is
not verified evidence and cannot satisfy legal-behaviour coverage by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .legal_graph_store import (
    LegalGraphSnapshot as RuntimeLegalGraphSnapshot,
    current_for as current_legal_graph,
)
from .legal_research_atlas import LegalResearchAtlas, NavigationUnit
from lawrag.platform.paths import data_path, repository_root


ROOT = repository_root()
DEFAULT_CATALOG_PATH = data_path("legal_system", "legal-system-map-v1.json")
DEFAULT_LAW_INDEX_PATH = data_path("law_index.json")
DEFAULT_LEGAL_GRAPH_ROOT = data_path("legal_graph")

CATALOG_SCHEMA_VERSION = "legal-system-map-v1"
SEMANTIC_CACHE_SCHEMA_VERSION = "legal-system-semantic-cache-v1"
_LEGAL_GRAPH_SCHEMA_VERSION = "legal-graph-v1"
_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9%]+")
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")


class LegalSystemMapError(RuntimeError):
    """A versioned legal-system routing snapshot cannot be trusted."""


class AuthorityGenerationMismatchError(LegalSystemMapError):
    """The catalog, corpus, law index, or graph use different generations."""


class EffectiveDateMismatchError(LegalSystemMapError):
    """At least one current instrument has a different effective date."""


class ClosedCatalogMismatchError(LegalSystemMapError):
    """The catalog does not cover exactly the current closed atlas IDs."""


class SemanticCardCacheError(LegalSystemMapError):
    """The current Legal Graph card projection cannot be safely reused."""


def _norm(value: object) -> str:
    return _SPACE.sub("", str(value or "")).casefold()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _value_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegalSystemMapError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LegalSystemMapError(f"{label} must be a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise SemanticCardCacheError(
            f"Legal Graph artifact escapes generation root: {relative!r}"
        ) from exc
    return candidate


@dataclass(frozen=True, slots=True)
class LawFamilyMembership:
    root: str
    depth: int

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "depth": self.depth}


@dataclass(frozen=True, slots=True)
class LegalInstrumentSystemProfile:
    """Closed-corpus routing metadata reconstructed from authoritative inputs."""

    instrument_id: str
    name: str
    source_kind: str
    norm_layer: str
    default_role: str
    series_key: str
    status: str
    effective_date: str
    revised_date: str
    version: str
    purpose: str
    purpose_source: str
    law_families: tuple[LawFamilyMembership, ...]

    def fingerprint_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "name": self.name,
            "source_kind": self.source_kind,
            "norm_layer": self.norm_layer,
            "default_role": self.default_role,
            "series_key": self.series_key,
            "status": self.status,
            "effective_date": self.effective_date,
            "revised_date": self.revised_date,
            "version": self.version,
            "purpose_sha256": hashlib.sha256(
                self.purpose.encode("utf-8")
            ).hexdigest(),
            "purpose_source": self.purpose_source,
            "law_families": [row.to_dict() for row in self.law_families],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.fingerprint_dict(),
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class LegalIssueFamily:
    family_id: str
    triggers: tuple[str, ...]
    instrument_ids: tuple[str, ...]
    issue_axes: tuple[str, ...]
    weight: int

    def matches(self, routing_context: str, issue_axis: str) -> bool:
        axis = str(issue_axis or "").upper()
        context = _norm(routing_context)
        return axis in self.issue_axes and any(
            _norm(trigger) in context for trigger in self.triggers
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "triggers": list(self.triggers),
            "instrument_ids": list(self.instrument_ids),
            "issue_axes": list(self.issue_axes),
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class LegalGraphSnapshot:
    generation_id: str
    content_sha256: str
    projection_policy: str
    current_sha256: str
    manifest_sha256: str
    provision_cards_path: str
    provision_cards_sha256: str
    provision_cards_rows: int
    semantic_cards_path: str
    semantic_cards_sha256: str
    semantic_cards_rows: int


@dataclass(frozen=True, slots=True)
class LegalSystemMap:
    schema_version: str
    catalog_version: str
    authority_generation: str
    authority_as_of: str
    law_index_sha256: str
    expected_document_ids: tuple[str, ...]
    effective_dates_sha256: str
    profiles_sha256: str
    profiles: tuple[LegalInstrumentSystemProfile, ...]
    issue_families: tuple[LegalIssueFamily, ...]
    legal_graph: LegalGraphSnapshot

    @property
    def profile_by_id(self) -> Mapping[str, LegalInstrumentSystemProfile]:
        return MappingProxyType({row.instrument_id: row for row in self.profiles})

    def profile(self, instrument_id: str) -> LegalInstrumentSystemProfile | None:
        key = str(instrument_id)
        for row in self.profiles:
            if row.instrument_id == key:
                return row
        return None

    def matching_issue_families(
        self, routing_context: str, issue_axis: str
    ) -> tuple[LegalIssueFamily, ...]:
        return tuple(
            family for family in self.issue_families
            if family.matches(routing_context, issue_axis)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "catalog_version": self.catalog_version,
            "authority_generation": self.authority_generation,
            "authority_as_of": self.authority_as_of,
            "law_index_sha256": self.law_index_sha256,
            "expected_document_ids": list(self.expected_document_ids),
            "effective_dates_sha256": self.effective_dates_sha256,
            "profiles_sha256": self.profiles_sha256,
            "profiles": [row.to_dict() for row in self.profiles],
            "issue_families": [row.to_dict() for row in self.issue_families],
        }


def _law_family_memberships(
    law_index: Mapping[str, Any],
) -> dict[str, tuple[LawFamilyMembership, ...]]:
    by_id: dict[str, list[LawFamilyMembership]] = {}
    for family in law_index.get("families") or ():
        if not isinstance(family, Mapping):
            continue
        root = str(family.get("root") or "").strip()
        if not root:
            continue
        for member in family.get("members") or ():
            if not isinstance(member, Mapping) or not member.get("held"):
                continue
            document_id = str(member.get("doc_id") or "").strip()
            depth = member.get("depth")
            if not document_id or isinstance(depth, bool) or not isinstance(depth, int):
                continue
            by_id.setdefault(document_id, []).append(
                LawFamilyMembership(root=root, depth=depth)
            )
    return {
        document_id: tuple(sorted(rows, key=lambda row: (row.root, row.depth)))
        for document_id, rows in by_id.items()
    }


def _corpus_purpose(atlas: LegalResearchAtlas, instrument_id: str) -> str:
    view = atlas.current_index.entry_docs.get(instrument_id)
    if view is None:
        return ""
    for unit in atlas.article_units(instrument_id):
        if "목적" not in unit.label:
            continue
        node = view.by_id.get(unit.node_id)
        if node is None:
            continue
        return str(view.section_text(dict(node), cap=4096) or "").strip()
    return ""


def derive_instrument_profiles(
    atlas: LegalResearchAtlas,
    law_index: Mapping[str, Any],
) -> tuple[LegalInstrumentSystemProfile, ...]:
    """Build one deterministic profile for every current atlas instrument."""

    law_docs: dict[str, Mapping[str, Any]] = {}
    for row in law_index.get("docs") or ():
        if not isinstance(row, Mapping):
            continue
        document_id = str(row.get("doc_id") or "").strip()
        if document_id:
            law_docs[document_id] = row
    memberships = _law_family_memberships(law_index)
    profiles: list[LegalInstrumentSystemProfile] = []
    seen: set[str] = set()
    for record in atlas.instruments:
        if record.instrument_id in seen:
            raise ClosedCatalogMismatchError(
                f"duplicate current instrument ID: {record.instrument_id}"
            )
        seen.add(record.instrument_id)
        law_doc = law_docs.get(record.instrument_id)
        if law_doc is not None:
            purpose = str(law_doc.get("purpose") or "").strip()
            purpose_source = "LAW_INDEX"
        else:
            purpose = _corpus_purpose(atlas, record.instrument_id)
            purpose_source = "CORPUS_PURPOSE_ARTICLE" if purpose else "UNAVAILABLE"
        profiles.append(LegalInstrumentSystemProfile(
            instrument_id=record.instrument_id,
            name=record.name,
            source_kind=record.source_kind,
            norm_layer=record.norm_layer.value,
            default_role=record.default_role.value,
            series_key=record.series_key,
            status=record.status,
            effective_date=record.enforce,
            revised_date=record.revised,
            version=record.version,
            purpose=purpose,
            purpose_source=purpose_source,
            law_families=memberships.get(record.instrument_id, ()),
        ))
    return tuple(sorted(profiles, key=lambda row: row.instrument_id))


def profile_snapshot_hashes(
    profiles: Sequence[LegalInstrumentSystemProfile],
) -> tuple[str, str]:
    effective_dates = [
        [row.instrument_id, row.effective_date] for row in profiles
    ]
    profile_rows = [row.fingerprint_dict() for row in profiles]
    return _value_sha256(effective_dates), _value_sha256(profile_rows)


def _parse_issue_families(
    values: object,
    *,
    closed_ids: frozenset[str],
) -> tuple[LegalIssueFamily, ...]:
    if not isinstance(values, list):
        raise LegalSystemMapError("catalog.issue_families must be a list")
    rows: list[LegalIssueFamily] = []
    seen: set[str] = set()
    for index, raw in enumerate(values):
        if not isinstance(raw, Mapping):
            raise LegalSystemMapError(
                f"catalog.issue_families[{index}] must be an object"
            )
        family_id = str(raw.get("family_id") or "").strip()
        triggers = tuple(str(value).strip() for value in raw.get("triggers") or ())
        instrument_ids = tuple(
            str(value).strip() for value in raw.get("instrument_ids") or ()
        )
        issue_axes = tuple(
            str(value).strip().upper() for value in raw.get("issue_axes") or ()
        )
        weight = raw.get("weight")
        if (
            not family_id or family_id in seen or not triggers or not instrument_ids
            or not issue_axes or isinstance(weight, bool) or not isinstance(weight, int)
            or weight <= 0
        ):
            raise LegalSystemMapError(
                f"malformed catalog issue family at index {index}: {family_id!r}"
            )
        external = sorted(set(instrument_ids) - closed_ids)
        if external:
            raise ClosedCatalogMismatchError(
                f"issue family {family_id} contains non-current IDs: {external}"
            )
        seen.add(family_id)
        rows.append(LegalIssueFamily(
            family_id=family_id,
            triggers=tuple(dict.fromkeys(triggers)),
            instrument_ids=tuple(dict.fromkeys(instrument_ids)),
            issue_axes=tuple(dict.fromkeys(issue_axes)),
            weight=weight,
        ))
    return tuple(rows)


def _graph_snapshot(raw: Mapping[str, Any]) -> LegalGraphSnapshot:
    required_strings = (
        "generation_id", "content_sha256", "projection_policy",
        "current_sha256", "manifest_sha256", "provision_cards_path",
        "provision_cards_sha256", "semantic_cards_path", "semantic_cards_sha256",
    )
    for field in required_strings:
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise LegalSystemMapError(f"catalog.legal_graph.{field} is required")
    for field in (
        "content_sha256", "current_sha256", "manifest_sha256",
        "provision_cards_sha256", "semantic_cards_sha256",
    ):
        if not _SAFE_HEX.fullmatch(str(raw[field])):
            raise LegalSystemMapError(f"catalog.legal_graph.{field} is not SHA-256")
    provision_rows = raw.get("provision_cards_rows")
    semantic_rows = raw.get("semantic_cards_rows")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (provision_rows, semantic_rows)
    ):
        raise LegalSystemMapError("catalog Legal Graph row counts must be positive")
    return LegalGraphSnapshot(
        generation_id=str(raw["generation_id"]),
        content_sha256=str(raw["content_sha256"]),
        projection_policy=str(raw["projection_policy"]),
        current_sha256=str(raw["current_sha256"]),
        manifest_sha256=str(raw["manifest_sha256"]),
        provision_cards_path=str(raw["provision_cards_path"]),
        provision_cards_sha256=str(raw["provision_cards_sha256"]),
        provision_cards_rows=int(provision_rows),
        semantic_cards_path=str(raw["semantic_cards_path"]),
        semantic_cards_sha256=str(raw["semantic_cards_sha256"]),
        semantic_cards_rows=int(semantic_rows),
    )


def _validate_graph_header(
    *,
    graph_root: Path,
    graph: LegalGraphSnapshot,
    authority_generation: str,
    authority_as_of: str,
) -> None:
    current_path = graph_root / "CURRENT.json"
    current, current_hash = _read_json(current_path, label="Legal Graph CURRENT")
    if current_hash != graph.current_sha256:
        raise AuthorityGenerationMismatchError(
            "Legal Graph CURRENT hash differs from legal-system catalog"
        )
    if (
        current.get("schema_version") != _LEGAL_GRAPH_SCHEMA_VERSION
        or current.get("generation_id") != graph.generation_id
        or current.get("content_sha256") != graph.content_sha256
    ):
        raise AuthorityGenerationMismatchError(
            "Legal Graph CURRENT generation differs from legal-system catalog"
        )
    manifest_rel = str(current.get("manifest") or "")
    manifest_path = _safe_artifact_path(graph_root, manifest_rel)
    manifest, manifest_hash = _read_json(
        manifest_path, label="Legal Graph manifest"
    )
    if manifest_hash != graph.manifest_sha256:
        raise AuthorityGenerationMismatchError(
            "Legal Graph manifest hash differs from legal-system catalog"
        )
    if (
        manifest.get("schema_version") != _LEGAL_GRAPH_SCHEMA_VERSION
        or manifest.get("generation_id") != graph.generation_id
        or manifest.get("authority_generation") != authority_generation
        or str(manifest.get("authority_as_of") or "") != authority_as_of
        or manifest.get("content_sha256") != graph.content_sha256
        or manifest.get("projection_policy") != graph.projection_policy
    ):
        raise AuthorityGenerationMismatchError(
            "Legal Graph manifest authority or projection policy mismatch"
        )
    artifacts = manifest.get("artifacts") or {}
    expected = {
        graph.provision_cards_path: (
            graph.provision_cards_sha256, graph.provision_cards_rows
        ),
        graph.semantic_cards_path: (
            graph.semantic_cards_sha256, graph.semantic_cards_rows
        ),
    }
    for relative, (sha256, rows) in expected.items():
        metadata = artifacts.get(relative)
        if not isinstance(metadata, Mapping):
            raise SemanticCardCacheError(
                f"Legal Graph manifest lacks required artifact: {relative}"
            )
        if metadata.get("sha256") != sha256 or metadata.get("rows") != rows:
            raise SemanticCardCacheError(
                f"Legal Graph artifact metadata mismatch: {relative}"
            )


def load_legal_system_map(
    atlas: LegalResearchAtlas,
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    law_index_path: Path = DEFAULT_LAW_INDEX_PATH,
    legal_graph_root: Path = DEFAULT_LEGAL_GRAPH_ROOT,
    validate_graph: bool = True,
) -> LegalSystemMap:
    """Load and fully validate the current versioned routing catalog.

    Validation is intentionally fail-closed.  A new corpus, effective date,
    authority generation, law-family map, purpose text, or graph generation
    requires a newly versioned catalog rather than a silent best-effort merge.
    """

    catalog, _catalog_hash = _read_json(catalog_path, label="legal-system catalog")
    law_index, law_index_hash = _read_json(law_index_path, label="law index")
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise LegalSystemMapError(
            f"catalog schema must be {CATALOG_SCHEMA_VERSION!r}"
        )
    if law_index.get("schema_version") != "legal-authority-generation-v1":
        raise AuthorityGenerationMismatchError(
            "law index is not a legal-authority-generation-v1 snapshot"
        )
    authority_generation = str(catalog.get("authority_generation") or "")
    authority_as_of = str(catalog.get("authority_as_of") or "")
    current_generation = str(
        getattr(atlas.current_index, "authority_generation", "") or ""
    )
    current_as_of = str(getattr(atlas.current_index, "authority_as_of", "") or "")
    if not authority_generation or not authority_as_of:
        raise AuthorityGenerationMismatchError(
            "catalog authority generation and as-of are required"
        )
    if (
        current_generation != authority_generation
        or current_as_of != authority_as_of
        or str(law_index.get("generation_id") or "") != authority_generation
        or str(law_index.get("as_of") or "") != authority_as_of
        or str(catalog.get("law_index_sha256") or "") != law_index_hash
    ):
        raise AuthorityGenerationMismatchError(
            "atlas, law index, and legal-system catalog authority mismatch"
        )

    expected_ids = tuple(str(value) for value in catalog.get("document_ids") or ())
    if not expected_ids or expected_ids != tuple(sorted(set(expected_ids))):
        raise ClosedCatalogMismatchError(
            "catalog.document_ids must be a sorted unique closed inventory"
        )
    actual_ids = tuple(sorted(atlas.current_document_ids))
    if expected_ids != actual_ids:
        missing = sorted(set(actual_ids) - set(expected_ids))
        stale = sorted(set(expected_ids) - set(actual_ids))
        raise ClosedCatalogMismatchError(
            f"catalog/current atlas mismatch: missing={missing}, stale={stale}"
        )
    profiles = derive_instrument_profiles(atlas, law_index)
    effective_hash, profiles_hash = profile_snapshot_hashes(profiles)
    if str(catalog.get("effective_dates_sha256") or "") != effective_hash:
        raise EffectiveDateMismatchError(
            "current instrument effective-date snapshot differs from catalog"
        )
    if str(catalog.get("profiles_sha256") or "") != profiles_hash:
        raise ClosedCatalogMismatchError(
            "current instrument name/layer/role/purpose/family snapshot differs from catalog"
        )
    closed_ids = frozenset(expected_ids)
    issue_families = _parse_issue_families(
        catalog.get("issue_families"), closed_ids=closed_ids
    )
    graph = _graph_snapshot(catalog.get("legal_graph") or {})
    if validate_graph:
        _validate_graph_header(
            graph_root=legal_graph_root,
            graph=graph,
            authority_generation=authority_generation,
            authority_as_of=authority_as_of,
        )
    return LegalSystemMap(
        schema_version=CATALOG_SCHEMA_VERSION,
        catalog_version=str(catalog.get("catalog_version") or ""),
        authority_generation=authority_generation,
        authority_as_of=authority_as_of,
        law_index_sha256=law_index_hash,
        expected_document_ids=expected_ids,
        effective_dates_sha256=effective_hash,
        profiles_sha256=profiles_hash,
        profiles=profiles,
        issue_families=issue_families,
        legal_graph=graph,
    )


@dataclass(frozen=True, slots=True)
class SemanticArticleCard:
    """Article-root aggregate of existing Legal Graph projection rows."""

    instrument_id: str
    node_id: object
    provision_card_id: str
    article_root_id: str
    article_label: str
    semantic_card_ids: tuple[str, ...]
    family_ids: tuple[str, ...]
    semantic_types: tuple[str, ...]
    relation_predicates: tuple[str, ...]
    coverage_keys: tuple[str, ...]
    terms: tuple[str, ...]
    search_text: str
    semantic_ready: bool

    @property
    def coordinate(self) -> tuple[str, object]:
        return self.instrument_id, self.node_id

    def matches(self, value: object) -> bool:
        normalized = _norm(value)
        if not normalized:
            return False
        if normalized in self.search_text:
            return True
        tokens = tuple(_norm(token) for token in _TOKEN.findall(str(value or "")))
        return bool(tokens) and all(token in self.search_text for token in tokens)


class LegalGraphSemanticCardIndex:
    """Generation-checked façade over the existing Legal Graph process cache.

    ``legal_graph_store`` already owns the verified immutable snapshot,
    semantic term postings and single-flight process cache.  This façade does
    not parse or duplicate the 176k semantic rows.  It only aggregates an
    article card when that article is actually inspected by entry routing.
    """

    def __init__(
        self,
        atlas: LegalResearchAtlas,
        system_map: LegalSystemMap,
        *,
        legal_graph_root: Path = DEFAULT_LEGAL_GRAPH_ROOT,
    ) -> None:
        self.atlas = atlas
        self.system_map = system_map
        self.legal_graph_root = legal_graph_root
        if (
            str(getattr(atlas.current_index, "authority_generation", "") or "")
            != system_map.authority_generation
            or str(getattr(atlas.current_index, "authority_as_of", "") or "")
            != system_map.authority_as_of
        ):
            raise AuthorityGenerationMismatchError(
                "semantic-card cache atlas authority differs from legal-system map"
            )
        _validate_graph_header(
            graph_root=legal_graph_root,
            graph=system_map.legal_graph,
            authority_generation=system_map.authority_generation,
            authority_as_of=system_map.authority_as_of,
        )
        self._snapshot: RuntimeLegalGraphSnapshot | None = None
        self._article_cache: dict[
            tuple[str, object], SemanticArticleCard
        ] = {}

    def _ensure_snapshot(self) -> RuntimeLegalGraphSnapshot:
        if self._snapshot is not None:
            return self._snapshot
        result = current_legal_graph(
            self.atlas.current_index, root=self.legal_graph_root
        )
        snapshot = result.snapshot
        if snapshot is None:
            raise SemanticCardCacheError(
                "current Legal Graph snapshot failed closed: "
                f"status={result.status}, reasons={list(result.reasons)}"
            )
        graph = self.system_map.legal_graph
        if (
            snapshot.generation_id != graph.generation_id
            or snapshot.authority_generation != self.system_map.authority_generation
            or snapshot.content_sha256 != graph.content_sha256
            or snapshot.projection_policy != graph.projection_policy
            or len(snapshot.ports_by_article) != graph.provision_cards_rows
            or len(snapshot.semantic_cards) != graph.semantic_cards_rows
        ):
            raise SemanticCardCacheError(
                "verified Legal Graph snapshot differs from legal-system catalog"
            )
        current_coordinates = {
            (unit.instrument_id, unit.node_id)
            for instrument_id in self.system_map.expected_document_ids
            for unit in self.atlas.article_units(instrument_id)
        }
        if set(snapshot.ports_by_article) != current_coordinates:
            raise SemanticCardCacheError(
                "Legal Graph ProvisionCards do not cover exactly the current atlas"
            )
        self._snapshot = snapshot
        return snapshot

    def _aggregate(
        self, coordinate: tuple[str, object]
    ) -> SemanticArticleCard | None:
        cached = self._article_cache.get(coordinate)
        if cached is not None:
            return cached
        snapshot = self._ensure_snapshot()
        ports = snapshot.ports_by_article.get(coordinate)
        if ports is None:
            return None
        semantic_rows = snapshot.semantics_for_article(coordinate)
        terms = tuple(sorted({term for row in semantic_rows for term in row.terms}))
        labels = tuple(
            dict.fromkeys(row.label for row in semantic_rows if row.label)
        )[:12]
        card = SemanticArticleCard(
            instrument_id=str(coordinate[0]),
            node_id=coordinate[1],
            provision_card_id="",
            article_root_id=ports.member_id,
            article_label=ports.endpoint.label,
            semantic_card_ids=tuple(row.card_id for row in semantic_rows),
            family_ids=tuple(sorted({
                value for row in semantic_rows for value in row.family_ids
            })),
            semantic_types=tuple(sorted({
                row.semantic_type for row in semantic_rows if row.semantic_type
            })),
            relation_predicates=tuple(sorted({
                row.relation_predicate
                for row in semantic_rows if row.relation_predicate
            })),
            coverage_keys=tuple(sorted({
                value for row in semantic_rows for value in row.coverage_keys
            })),
            terms=terms,
            search_text=_norm(" ".join((ports.endpoint.label, *labels, *terms))),
            semantic_ready=any(
                row.card_status == "SEMANTIC_READY" for row in semantic_rows
            ),
        )
        self._article_cache[coordinate] = card
        return card

    def preload(self) -> int:
        """Materialize and validate the cache; return current article count."""

        return len(self._ensure_snapshot().ports_by_article)

    def get(
        self, instrument_id: str, node_id: object
    ) -> SemanticArticleCard | None:
        return self._aggregate((str(instrument_id), node_id))

    def for_navigation(self, unit: NavigationUnit) -> SemanticArticleCard | None:
        return self.get(unit.instrument_id, unit.node_id)

    def for_document(self, instrument_id: str) -> tuple[SemanticArticleCard, ...]:
        document_id = str(instrument_id)
        snapshot = self._ensure_snapshot()
        coordinates = sorted(
            (
                coordinate for coordinate in snapshot.ports_by_article
                if coordinate[0] == document_id
            ),
            key=lambda row: repr(row[1]),
        )
        return tuple(
            card for coordinate in coordinates
            if (card := self._aggregate(coordinate)) is not None
        )

    def search(
        self,
        terms: Sequence[str],
        *,
        instrument_ids: Sequence[str] | None = None,
        limit: int = 100,
    ) -> tuple[SemanticArticleCard, ...]:
        """Return an AND intersection of precompiled card-term postings."""

        return tuple(
            card
            for coordinate in self.search_coordinates(
                terms, instrument_ids=instrument_ids, limit=limit,
            )
            if (card := self._aggregate(coordinate)) is not None
        )

    def search_coordinates(
        self,
        terms: Sequence[str],
        *,
        instrument_ids: Sequence[str] | None = None,
        limit: int = 100,
    ) -> tuple[tuple[str, object], ...]:
        """Return posting coordinates without materializing semantic cards.

        Legal-system routing needs only closed article IDs.  Deferring card
        aggregation avoids repeatedly collecting labels, terms and coverage
        for hundreds of provisional entry points that will not survive the
        bounded law/article menu.
        """

        normalized = tuple(dict.fromkeys(
            _norm(term) for term in terms if len(_norm(term)) >= 2
        ))
        if not normalized or limit < 1:
            return ()
        snapshot = self._ensure_snapshot()
        candidate_sets = [
            set(snapshot.semantic_postings.get(term, ())) for term in normalized
        ]
        if any(not values for values in candidate_sets):
            return ()
        card_indexes = set.intersection(*candidate_sets)
        coordinates = {
            (
                snapshot.semantic_cards[index].article_root.document_id,
                snapshot.semantic_cards[index].article_root.node_id,
            )
            for index in card_indexes
        }
        allowed = set(str(value) for value in instrument_ids or ())
        if allowed:
            coordinates = {row for row in coordinates if row[0] in allowed}
        return tuple(
            sorted(
                coordinates, key=lambda row: (row[0], repr(row[1]))
            )[:limit]
        )


def build_legal_system_catalog_snapshot(
    atlas: LegalResearchAtlas,
    seed_catalog: Mapping[str, Any],
    *,
    catalog_version: str | None = None,
    law_index_path: Path = DEFAULT_LAW_INDEX_PATH,
    legal_graph_root: Path = DEFAULT_LEGAL_GRAPH_ROOT,
) -> dict[str, Any]:
    """Deterministically rebuild generated catalog fields from current data.

    ``issue_families`` is the intentionally human-maintained seed.  Every
    other field is regenerated from the closed atlas, law-index and current
    Legal Graph.  Stale/external IDs in that seed fail instead of being
    silently discarded.
    """

    law_index, law_hash = _read_json(law_index_path, label="law index")
    authority_generation = str(
        getattr(atlas.current_index, "authority_generation", "") or ""
    )
    authority_as_of = str(getattr(atlas.current_index, "authority_as_of", "") or "")
    if (
        law_index.get("schema_version") != "legal-authority-generation-v1"
        or str(law_index.get("generation_id") or "") != authority_generation
        or str(law_index.get("as_of") or "") != authority_as_of
    ):
        raise AuthorityGenerationMismatchError(
            "cannot build catalog from mismatched atlas/law-index authority"
        )
    profiles = derive_instrument_profiles(atlas, law_index)
    document_ids = tuple(row.instrument_id for row in profiles)
    effective_hash, profiles_hash = profile_snapshot_hashes(profiles)
    seed_families = seed_catalog.get("issue_families")
    parsed_families = _parse_issue_families(
        seed_families, closed_ids=frozenset(document_ids)
    )

    current_path = legal_graph_root / "CURRENT.json"
    current, current_hash = _read_json(current_path, label="Legal Graph CURRENT")
    if (
        current.get("schema_version") != _LEGAL_GRAPH_SCHEMA_VERSION
        or current.get("authority_generation") != authority_generation
    ):
        raise AuthorityGenerationMismatchError(
            "cannot build catalog from mismatched Legal Graph CURRENT authority"
        )
    manifest_path = _safe_artifact_path(
        legal_graph_root, str(current.get("manifest") or "")
    )
    manifest, manifest_hash = _read_json(
        manifest_path, label="Legal Graph manifest"
    )
    if (
        manifest.get("schema_version") != _LEGAL_GRAPH_SCHEMA_VERSION
        or manifest.get("generation_id") != current.get("generation_id")
        or manifest.get("authority_generation") != authority_generation
        or str(manifest.get("authority_as_of") or "") != authority_as_of
        or manifest.get("content_sha256") != current.get("content_sha256")
        or manifest.get("projection_policy") != current.get("projection_policy")
    ):
        raise AuthorityGenerationMismatchError(
            "cannot build catalog from mismatched Legal Graph manifest"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise SemanticCardCacheError("Legal Graph manifest artifacts are missing")

    def projection(row_type: str) -> tuple[str, Mapping[str, Any]]:
        matches = [
            (str(path), metadata)
            for path, metadata in artifacts.items()
            if isinstance(metadata, Mapping) and metadata.get("row_type") == row_type
        ]
        if len(matches) != 1:
            raise SemanticCardCacheError(
                f"Legal Graph must contain exactly one {row_type} artifact"
            )
        return matches[0]

    provision_path, provision_meta = projection("provision_card")
    semantic_path, semantic_meta = projection("semantic_card")
    snapshot = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": str(
            catalog_version
            if catalog_version is not None
            else seed_catalog.get("catalog_version") or ""
        ),
        "authority_generation": authority_generation,
        "authority_as_of": authority_as_of,
        "law_index_sha256": law_hash,
        "document_ids": list(document_ids),
        "effective_dates_sha256": effective_hash,
        "profiles_sha256": profiles_hash,
        "issue_families": [row.to_dict() for row in parsed_families],
        "legal_graph": {
            "generation_id": str(current.get("generation_id") or ""),
            "content_sha256": str(current.get("content_sha256") or ""),
            "projection_policy": str(current.get("projection_policy") or ""),
            "current_sha256": current_hash,
            "manifest_sha256": manifest_hash,
            "provision_cards_path": provision_path,
            "provision_cards_sha256": str(provision_meta.get("sha256") or ""),
            "provision_cards_rows": provision_meta.get("rows"),
            "semantic_cards_path": semantic_path,
            "semantic_cards_sha256": str(semantic_meta.get("sha256") or ""),
            "semantic_cards_rows": semantic_meta.get("rows"),
        },
    }
    # Reuse the same local parsers before returning data that a CLI may write.
    _graph_snapshot(snapshot["legal_graph"])
    return snapshot


def legal_system_catalog_diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a compact deterministic receipt of catalog snapshot changes."""

    old_ids = set(str(value) for value in before.get("document_ids") or ())
    new_ids = set(str(value) for value in after.get("document_ids") or ())
    tracked = (
        "schema_version", "catalog_version", "authority_generation",
        "authority_as_of", "law_index_sha256", "effective_dates_sha256",
        "profiles_sha256",
    )
    changed_fields = [
        field for field in tracked if before.get(field) != after.get(field)
    ]
    before_graph = before.get("legal_graph") or {}
    after_graph = after.get("legal_graph") or {}
    graph_changed_fields = sorted(
        key for key in set(before_graph) | set(after_graph)
        if before_graph.get(key) != after_graph.get(key)
    ) if isinstance(before_graph, Mapping) and isinstance(after_graph, Mapping) else [
        "legal_graph"
    ]
    before_families = before.get("issue_families") or ()
    after_families = after.get("issue_families") or ()
    return {
        "changed": before != after,
        "changed_fields": changed_fields,
        "graph_changed_fields": graph_changed_fields,
        "added_document_ids": sorted(new_ids - old_ids),
        "removed_document_ids": sorted(old_ids - new_ids),
        "issue_families_changed": before_families != after_families,
        "before_value_sha256": _value_sha256(before),
        "after_value_sha256": _value_sha256(after),
    }


@dataclass(frozen=True, slots=True)
class LegalSystemEntryRuntime:
    """Validated current-index façade for map and semantic entry planning."""

    atlas: LegalResearchAtlas
    system_map: LegalSystemMap
    semantic_cards: LegalGraphSemanticCardIndex | None

    def planner(self, **kwargs: Any):
        # Local import avoids a module cycle: legal_system_entry consumes this
        # map/cache module, while the façade is only a convenience constructor.
        from .legal_system_entry import LegalSystemEntryPlanner

        return LegalSystemEntryPlanner(
            self.atlas,
            system_map=self.system_map,
            semantic_card_index=self.semantic_cards,
            **kwargs,
        )

    def plan(
        self,
        question: str,
        query_plan: Mapping[str, Any],
        branches: Sequence[Any],
        **planner_kwargs: Any,
    ) -> tuple[Any, ...]:
        return self.planner(**planner_kwargs).plan(
            question, query_plan, branches
        )


def load_legal_system_runtime(
    index: Any,
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    law_index_path: Path = DEFAULT_LAW_INDEX_PATH,
    legal_graph_root: Path = DEFAULT_LEGAL_GRAPH_ROOT,
    semantic_cards: bool = True,
) -> LegalSystemEntryRuntime:
    """Construct the fail-closed legal-system entry façade from a current Index."""

    atlas = LegalResearchAtlas.from_index(index)
    system_map = load_legal_system_map(
        atlas,
        catalog_path=catalog_path,
        law_index_path=law_index_path,
        legal_graph_root=legal_graph_root,
    )
    card_index = (
        LegalGraphSemanticCardIndex(
            atlas, system_map, legal_graph_root=legal_graph_root
        )
        if semantic_cards else None
    )
    return LegalSystemEntryRuntime(atlas, system_map, card_index)


__all__ = [
    "CATALOG_SCHEMA_VERSION", "SEMANTIC_CACHE_SCHEMA_VERSION",
    "DEFAULT_CATALOG_PATH", "DEFAULT_LAW_INDEX_PATH", "DEFAULT_LEGAL_GRAPH_ROOT",
    "LegalSystemMapError", "AuthorityGenerationMismatchError",
    "EffectiveDateMismatchError", "ClosedCatalogMismatchError",
    "SemanticCardCacheError", "LawFamilyMembership",
    "LegalInstrumentSystemProfile", "LegalIssueFamily", "LegalGraphSnapshot",
    "LegalSystemMap", "SemanticArticleCard", "LegalGraphSemanticCardIndex",
    "LegalSystemEntryRuntime", "load_legal_system_runtime",
    "derive_instrument_profiles", "profile_snapshot_hashes", "load_legal_system_map",
    "build_legal_system_catalog_snapshot", "legal_system_catalog_diff",
]
