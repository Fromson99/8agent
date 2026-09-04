"""Verified, generation-pinned reader for the immutable Legal Graph sidecar.

The product search path consumes only the three runtime projections it needs.
Rows are streamed into compact slot dataclasses; raw JSON dictionaries are not
kept in memory.  A new snapshot is published only after the pointer, manifest,
validation receipt, artifact hashes, row counts, schema, and authority
generation all agree.

This module never mutates ``CURRENT.json`` or a generation.  Effective runtime
wiring belongs to the engine switch / MAIN promotion layer.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import AbstractSet, Any, Iterable, Mapping

from lawrag.core.legal_graph import (
    COMPILER_CONTRACT_VERSION,
    RowType,
    SCHEMA_VERSION,
    SchemaValidationError,
    content_sha256,
    validate_manifest,
    validate_row,
)
from lawrag.core.rag.index import Index
from lawrag.platform.paths import data_path
CURRENT_FILE = "CURRENT.json"
SUPPORTED_PROJECTION_POLICIES = frozenset({
    "provision-card-v1.1",
    "semantic-card-v2",
    "semantic-card-v2.1",
})
SUPPORTED_ACTIVATION_POLICY = "query_conditional_future_policy"
SUPPORTED_COMPILER_CONTRACTS = frozenset({
    "legal-graph-compiler-v1",
    "legal-graph-compiler-v2",
    COMPILER_CONTRACT_VERSION,
})
NEGATIVE_CACHE_TTL_SECONDS = 5.0
MAX_NEGATIVE_CACHE_ENTRIES = 64

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^lgv1-[0-9a-f]{24}$")
_ARTIFACT_TYPES = MappingProxyType({
    "canonical/relation_assertions.jsonl.gz": RowType.RELATION_ASSERTION,
    "projections/closure_projections.jsonl.gz": RowType.CLOSURE_PROJECTION,
    "projections/provision_cards.jsonl.gz": RowType.PROVISION_CARD,
    "projections/semantic_cards.jsonl.gz": RowType.SEMANTIC_CARD,
})
_CARD_FACET_FIELDS = frozenset({
    "definition_observation_ids",
    "frame_observation_ids",
    "requirement_observation_ids",
    "legacy_rule_assertion_ids",
    "relation_assertion_ids",
    "unresolved_relation_ids",
})
_CARD_FACET_FIELDS_ORDERED = tuple(sorted(_CARD_FACET_FIELDS))
_CARD_PORT_FIELDS = frozenset({
    "outgoing_projection_ids",
    "incoming_projection_ids",
})

Coordinate = tuple[str, object]


class LegalGraphLoadError(RuntimeError):
    """A candidate snapshot failed closed before publication."""


@dataclass(frozen=True, slots=True)
class EndpointLite:
    kind: str
    precision: str
    ref_id: str
    document_id: str
    node_id: int | str | None
    block_id: int | str | None
    start: int | None
    end: int | None
    quote_sha256: str
    coordinate: str
    label: str

    @classmethod
    def from_row(cls, value: Mapping[str, Any], *, field: str) -> "EndpointLite":
        selector = value.get("selector")
        if not isinstance(selector, Mapping):
            raise LegalGraphLoadError(f"{field}.selector is missing")
        document_id = str(selector.get("document_id") or "")
        if not document_id:
            raise LegalGraphLoadError(f"{field}.selector.document_id is missing")
        return cls(
            kind=str(value.get("kind") or ""),
            precision=str(value.get("precision") or ""),
            ref_id=str(value.get("ref_id") or ""),
            document_id=document_id,
            node_id=selector.get("node_id"),
            block_id=selector.get("block_id"),
            start=selector.get("start"),
            end=selector.get("end"),
            quote_sha256=str(selector.get("quote_sha256") or ""),
            coordinate=str(selector.get("coordinate") or ""),
            label=str(value.get("label") or ""),
        )


@dataclass(frozen=True, slots=True)
class EdgeLite:
    projection_id: str
    assertion_id: str
    predicate: str
    family: str
    mode: str
    resolution: str
    review_state: str
    legacy_kind: str
    source: EndpointLite
    target: EndpointLite


@dataclass(frozen=True, slots=True)
class ArticlePorts:
    member_id: str
    endpoint: EndpointLite
    outgoing: tuple[str, ...]
    incoming: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticCardLite:
    card_id: str
    entity_id: str
    semantic_type: str
    source: EndpointLite
    article_root: EndpointLite
    family_ids: tuple[str, ...]
    terms: tuple[str, ...]
    assertion_ids: tuple[str, ...]
    coverage_keys: tuple[str, ...]
    relation_predicate: str
    label: str
    card_status: str = "SEMANTIC_READY"


@dataclass(frozen=True, slots=True)
class LegalGraphSnapshot:
    root: Path
    generation_id: str
    authority_generation: str
    content_sha256: str
    projection_policy: str
    pointer_sha256: str
    runtime_wired_in_artifact: bool
    ports_by_article: Mapping[Coordinate, ArticlePorts]
    edge_by_projection_id: Mapping[str, EdgeLite]
    loaded_rows: int
    load_ms: float
    semantic_cards: tuple[SemanticCardLite, ...] = ()
    semantic_postings: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    semantic_by_article: Mapping[Coordinate, tuple[int, ...]] = field(default_factory=dict)

    def incident(
        self,
        coordinate: Coordinate,
        *,
        direction: str = "outgoing",
    ) -> tuple[EdgeLite, ...]:
        ports = self.ports_by_article.get(coordinate)
        if ports is None:
            return ()
        if direction == "outgoing":
            projection_ids = ports.outgoing
        elif direction == "incoming":
            projection_ids = ports.incoming
        else:
            raise ValueError(f"unsupported Legal Graph direction: {direction}")
        return tuple(
            edge for projection_id in projection_ids
            if (edge := self.edge_by_projection_id.get(projection_id)) is not None
        )

    def semantic_candidates(
        self,
        terms: Iterable[str],
        *,
        family_ids: AbstractSet[str] | None = None,
        min_term_matches: int = 1,
    ) -> tuple[SemanticCardLite, ...]:
        counts: dict[int, int] = {}
        for term in terms:
            for index in self.semantic_postings.get(str(term).casefold(), ()):
                counts[index] = counts.get(index, 0) + 1
        threshold = max(1, int(min_term_matches))
        indexes = sorted(
            index for index, count in counts.items() if count >= threshold
        )
        if not indexes and threshold > 1:
            indexes = sorted(counts)
        cards = []
        for index in indexes:
            card = self.semantic_cards[index]
            if family_ids and not family_ids.intersection(card.family_ids):
                continue
            cards.append(card)
        return tuple(cards)

    def semantics_for_article(self, coordinate: Coordinate) -> tuple[SemanticCardLite, ...]:
        return tuple(
            self.semantic_cards[index]
            for index in self.semantic_by_article.get(coordinate, ())
        )


@dataclass(frozen=True, slots=True)
class LegalGraphLoadResult:
    snapshot: LegalGraphSnapshot | None
    status: str
    reasons: tuple[str, ...] = ()
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        snapshot = self.snapshot
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "generation_id": snapshot.generation_id if snapshot else "",
            "authority_generation": snapshot.authority_generation if snapshot else "",
            "content_sha256": snapshot.content_sha256 if snapshot else "",
            "projection_policy": snapshot.projection_policy if snapshot else "",
            "runtime_wired_in_artifact": (
                snapshot.runtime_wired_in_artifact if snapshot else False
            ),
            "loaded_rows": snapshot.loaded_rows if snapshot else 0,
            "semantic_cards": len(snapshot.semantic_cards) if snapshot else 0,
            "cold_load_ms": round(snapshot.load_ms, 3) if snapshot else None,
        }


CacheKey = tuple[str, str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class _LoadOutcome:
    snapshot: LegalGraphSnapshot | None
    status: str
    reasons: tuple[str, ...]


@dataclass(slots=True)
class _LoadFlight:
    event: threading.Event
    epoch: int
    outcome: _LoadOutcome | None = None


@dataclass(frozen=True, slots=True)
class _NegativeEntry:
    expires_at: float
    outcome: _LoadOutcome


_cache_lock = threading.RLock()
_cache_key: CacheKey | None = None
_cache_snapshot: LegalGraphSnapshot | None = None
_inflight: dict[CacheKey, _LoadFlight] = {}
_negative_cache: dict[CacheKey, _NegativeEntry] = {}
_cache_epoch = 0


def graph_root() -> Path:
    return Path(os.environ.get("LEGAL_GRAPH_STORE") or data_path("legal_graph"))


def _graph_root_for_index(index: Index, root: Path | None) -> Path:
    """Resolve the graph only through the active content authority.

    In legacy mode the historical explicit/environment path remains valid.  A
    SourceSet-bound index, however, must consume the release-proved semantic
    artifact and must not be redirected by ``LEGAL_GRAPH_STORE`` or by a
    caller-supplied ambient directory.
    """

    content_snapshot = index.content_snapshot
    if content_snapshot is None:
        return (root or graph_root()).resolve()
    expected = content_snapshot.runtime_artifact_path("semantics.content").resolve()
    if root is not None and Path(root).resolve() != expected:
        raise LegalGraphLoadError(
            "explicit Legal Graph root conflicts with the content snapshot"
        )
    if not expected.is_dir():
        raise LegalGraphLoadError(
            "release semantic artifact is not a Legal Graph directory"
        )
    return expected


def reset_cache() -> None:
    """Clear the process cache.  Intended for tests and explicit reload tools."""
    global _cache_epoch, _cache_key, _cache_snapshot
    with _cache_lock:
        _cache_epoch += 1
        _cache_key = None
        _cache_snapshot = None
        _negative_cache.clear()
        # Existing owners and their existing waiters still complete safely,
        # but calls made after reset start a new flight and old epochs cannot
        # republish into the cleared process cache.
        _inflight.clear()


def current_for(index: Index, *, root: Path | None = None) -> LegalGraphLoadResult:
    """Return the current verified snapshot, or an explicit fail-open result."""
    global _cache_key, _cache_snapshot
    started = time.perf_counter()
    try:
        base = _graph_root_for_index(index, root)
        pointer_path = base / CURRENT_FILE
        pointer_bytes = pointer_path.read_bytes()
        pointer = _json_bytes(pointer_bytes, source=str(pointer_path))
        pointer_sha = hashlib.sha256(pointer_bytes).hexdigest()
        _validate_pointer(pointer)
        authority = str(pointer["authority_generation"])
        if not index.authority_generation:
            raise LegalGraphLoadError("index authority generation is unavailable")
        if authority != index.authority_generation:
            elapsed = (time.perf_counter() - started) * 1000
            return LegalGraphLoadResult(
                None,
                "stale",
                (f"authority_generation:{authority}!={index.authority_generation}",),
                elapsed,
            )
        content_snapshot = index.content_snapshot
        if (
            content_snapshot is not None
            and str(pointer["generation_id"])
            != content_snapshot.semantic_generation
        ):
            return _timed_result(
                started,
                None,
                "stale",
                (
                    "semantic_generation:"
                    f"{pointer['generation_id']}!="
                    f"{content_snapshot.semantic_generation}",
                ),
            )
        key = (
            str(base),
            str(pointer["generation_id"]),
            str(pointer["content_sha256"]),
            authority,
            pointer_sha,
            (
                content_snapshot.content_snapshot_sha256
                if content_snapshot is not None else ""
            ),
        )
        with _cache_lock:
            if _cache_key == key and _cache_snapshot is not None:
                return _timed_result(
                    started, _cache_snapshot, "cache_hit", ()
                )
            now = time.monotonic()
            _prune_negative_cache(now)
            negative = _negative_cache.get(key)
            if negative is not None:
                return _timed_result(
                    started,
                    None,
                    negative.outcome.status,
                    (*negative.outcome.reasons, "negative_cache_hit"),
                )
            flight = _inflight.get(key)
            owner = flight is None
            if owner:
                flight = _LoadFlight(threading.Event(), _cache_epoch)
                _inflight[key] = flight

        if not owner:
            # Loads for other pointer keys continue independently.  Callers for
            # this exact immutable pointer wait for one verifier and reuse its
            # result, including a bounded failure result.
            assert flight is not None
            flight.event.wait()
            outcome = flight.outcome
            if outcome is None:
                raise LegalGraphLoadError(
                    "single-flight owner exited without publishing an outcome"
                )
            if outcome.snapshot is not None:
                return _timed_result(
                    started, outcome.snapshot, "cache_hit", ("single_flight_wait",)
                )
            return _timed_result(
                started,
                None,
                outcome.status,
                (*outcome.reasons, "negative_cache_hit", "single_flight_wait"),
            )

        assert flight is not None
        outcome: _LoadOutcome | None = None
        try:
            snapshot = _load_snapshot(base, pointer, pointer_sha)
            # Do not publish a mixed snapshot if CURRENT changed during the
            # cold load.  The second read deliberately binds publication to
            # the same pointer bytes used to derive the cache key.
            if hashlib.sha256(pointer_path.read_bytes()).hexdigest() != pointer_sha:
                raise LegalGraphLoadError("CURRENT.json changed during snapshot load")
            outcome = _LoadOutcome(snapshot, "loaded", ())
        except Exception as exc:
            outcome = _LoadOutcome(
                None, "invalid", (f"{type(exc).__name__}:{exc}",)
            )
        finally:
            # Always release same-key waiters, including if a BaseException
            # interrupts the owner.  BaseException itself is not swallowed.
            if outcome is None:
                outcome = _LoadOutcome(
                    None,
                    "invalid",
                    ("LegalGraphLoadError:single-flight owner interrupted",),
                )
            with _cache_lock:
                if flight.epoch == _cache_epoch:
                    if outcome.snapshot is not None:
                        _cache_key = key
                        _cache_snapshot = outcome.snapshot
                        _negative_cache.pop(key, None)
                    else:
                        _remember_negative(key, outcome)
                flight.outcome = outcome
                if _inflight.get(key) is flight:
                    _inflight.pop(key, None)
                flight.event.set()
        return _timed_result(
            started, outcome.snapshot, outcome.status, outcome.reasons
        )
    except FileNotFoundError as exc:
        return _timed_result(started, None, "missing", (str(exc),))
    except Exception as exc:
        return _timed_result(
            started, None, "invalid", (f"{type(exc).__name__}:{exc}",)
        )


def _timed_result(
    started: float,
    snapshot: LegalGraphSnapshot | None,
    status: str,
    reasons: tuple[str, ...],
) -> LegalGraphLoadResult:
    return LegalGraphLoadResult(
        snapshot, status, reasons, (time.perf_counter() - started) * 1000
    )


def _prune_negative_cache(now: float) -> None:
    expired = [key for key, entry in _negative_cache.items()
               if entry.expires_at <= now]
    for key in expired:
        _negative_cache.pop(key, None)


def _remember_negative(key: CacheKey, outcome: _LoadOutcome) -> None:
    now = time.monotonic()
    _prune_negative_cache(now)
    if len(_negative_cache) >= MAX_NEGATIVE_CACHE_ENTRIES:
        oldest = min(
            _negative_cache,
            key=lambda candidate: _negative_cache[candidate].expires_at,
        )
        _negative_cache.pop(oldest, None)
    _negative_cache[key] = _NegativeEntry(
        now + NEGATIVE_CACHE_TTL_SECONDS, outcome
    )


def _validate_pointer(pointer: Mapping[str, Any]) -> None:
    if pointer.get("schema_version") != SCHEMA_VERSION:
        raise LegalGraphLoadError("CURRENT schema_version mismatch")
    for field in (
        "generation_id", "authority_generation", "content_sha256",
        "projection_policy", "manifest",
    ):
        if not isinstance(pointer.get(field), str) or not str(pointer[field]).strip():
            raise LegalGraphLoadError(f"CURRENT {field} is missing")
    if not _GENERATION_RE.fullmatch(str(pointer["generation_id"])):
        raise LegalGraphLoadError("CURRENT generation_id is malformed")
    for field in ("authority_generation", "content_sha256"):
        if not _SHA256_RE.fullmatch(str(pointer[field])):
            raise LegalGraphLoadError(f"CURRENT {field} is not a SHA-256 digest")
    if pointer["projection_policy"] not in SUPPORTED_PROJECTION_POLICIES:
        raise LegalGraphLoadError(
            f"unsupported projection policy: {pointer['projection_policy']}"
        )
    expected_manifest = (
        f"generations/{pointer['generation_id']}/manifest.json"
    )
    if pointer["manifest"] != expected_manifest:
        raise LegalGraphLoadError(
            f"CURRENT manifest must be {expected_manifest!r}"
        )
    if not isinstance(pointer.get("runtime_wired"), bool):
        raise LegalGraphLoadError("CURRENT runtime_wired must be boolean")


def _safe_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise LegalGraphLoadError(f"unsafe Legal Graph path: {relative!r}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise LegalGraphLoadError(f"Legal Graph path escapes root: {relative!r}")
    return target


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _json_bytes(payload: bytes, *, source: str) -> dict[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LegalGraphLoadError(f"invalid JSON {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise LegalGraphLoadError(f"JSON object required: {source}")
    return value


def _json_file(path: Path) -> dict[str, Any]:
    return _json_bytes(path.read_bytes(), source=str(path))


def _validate_manifest_contract(manifest: Mapping[str, Any]) -> None:
    try:
        validate_manifest(manifest)
    except SchemaValidationError as exc:
        raise LegalGraphLoadError(f"manifest schema invalid: {exc}") from exc

    compiler_contract = manifest.get("compiler_contract")
    if compiler_contract not in SUPPORTED_COMPILER_CONTRACTS:
        raise LegalGraphLoadError(
            f"unsupported compiler contract: {compiler_contract!r}"
        )
    if manifest.get("projection_policy") not in SUPPORTED_PROJECTION_POLICIES:
        raise LegalGraphLoadError("manifest projection policy is unsupported")
    if not isinstance(manifest.get("runtime_wired"), bool):
        raise LegalGraphLoadError("manifest runtime_wired must be boolean")

    source_hashes = manifest.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise LegalGraphLoadError("manifest source_hashes must be non-empty")
    for source_name, digest in source_hashes.items():
        if not isinstance(source_name, str) or not source_name:
            raise LegalGraphLoadError("manifest source_hashes has an invalid key")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise LegalGraphLoadError(
                f"manifest source hash is invalid: {source_name!r}"
            )
    aggregate = content_sha256(source_hashes)
    if manifest.get("source_aggregate_sha256") != aggregate:
        raise LegalGraphLoadError("manifest source aggregate digest mismatch")

    generation_digest = content_sha256({
        "schema_version": SCHEMA_VERSION,
        "compiler_contract": compiler_contract,
        "projection_policy": manifest.get("projection_policy"),
        "authority_generation": manifest.get("authority_generation"),
        "source_hashes": source_hashes,
    })
    expected_generation = f"lgv1-{generation_digest[:24]}"
    if manifest.get("generation_id") != expected_generation:
        raise LegalGraphLoadError(
            "manifest generation_id does not match compiler inputs"
        )

    content_payload = dict(manifest)
    supplied_content = content_payload.pop("content_sha256", None)
    expected_content = content_sha256(content_payload)
    if supplied_content != expected_content:
        raise LegalGraphLoadError("manifest content_sha256 mismatch")


def _load_snapshot(
    root: Path,
    pointer: Mapping[str, Any],
    pointer_sha: str,
) -> LegalGraphSnapshot:
    started = time.perf_counter()
    manifest_path = _safe_path(root, str(pointer["manifest"]))
    manifest = _json_file(manifest_path)
    _validate_manifest_contract(manifest)
    for field in (
        "generation_id", "authority_generation", "content_sha256",
        "projection_policy", "schema_version", "runtime_wired",
    ):
        if manifest.get(field) != pointer.get(field):
            raise LegalGraphLoadError(f"pointer/manifest mismatch: {field}")

    validation = _json_file(manifest_path.parent / "validation" / "summary.json")
    if (
        validation.get("schema_version") != "legal-graph-validation-v1"
        or validation.get("generation_id") != manifest["generation_id"]
        or validation.get("ok") is not True
        or validation.get("error_count") != 0
    ):
        raise LegalGraphLoadError("generation validation receipt is not clean")

    assertions_path = "canonical/relation_assertions.jsonl.gz"
    closures_path = "projections/closure_projections.jsonl.gz"
    cards_path = "projections/provision_cards.jsonl.gz"

    # Cards identify the current article-root reachability boundary.  Parse
    # and verify them first so later passes instantiate endpoint/edge objects
    # only for projections that runtime can actually traverse.
    ports_by_article: dict[Coordinate, ArticlePorts] = {}
    card_ids: set[str] = set()
    required_projection_ids: set[str] = set()
    card_count = 0
    for row in _artifact_rows(
        manifest_path.parent,
        manifest,
        cards_path,
        expected_type=_ARTIFACT_TYPES[cards_path],
    ):
        card_id = str(row["id"])
        if card_id in card_ids:
            raise LegalGraphLoadError(f"duplicate provision card id: {card_id}")
        card_ids.add(card_id)
        endpoint = EndpointLite.from_row(row["article_root"], field="article_root")
        if endpoint.node_id is None:
            raise LegalGraphLoadError("provision card article root has no node_id")
        facets = row.get("facets")
        if not isinstance(facets, Mapping):
            raise LegalGraphLoadError("provision card facets is missing")
        if set(facets) != _CARD_FACET_FIELDS:
            raise LegalGraphLoadError("provision card facet fields mismatch")
        for field in _CARD_FACET_FIELDS_ORDERED:
            _validate_sorted_id_list(
                facets.get(field), field=f"facets.{field}", card_id=card_id
            )
        ports = row.get("relation_ports")
        if not isinstance(ports, Mapping):
            raise LegalGraphLoadError("provision card relation_ports is missing")
        if set(ports) != _CARD_PORT_FIELDS:
            raise LegalGraphLoadError("provision card relation port fields mismatch")
        outgoing_values = _sorted_id_list(
            ports.get("outgoing_projection_ids"),
            field="relation_ports.outgoing_projection_ids",
            card_id=card_id,
        )
        incoming_values = _sorted_id_list(
            ports.get("incoming_projection_ids"),
            field="relation_ports.incoming_projection_ids",
            card_id=card_id,
        )
        required_projection_ids.update(outgoing_values)
        required_projection_ids.update(incoming_values)
        member_id = row.get("structural_unit_id") or row.get("article_root_id")
        if not isinstance(member_id, str) or not member_id:
            raise LegalGraphLoadError(
                f"provision card member id is missing: {card_id}"
            )
        coordinate = (endpoint.document_id, endpoint.node_id)
        if coordinate in ports_by_article:
            raise LegalGraphLoadError(f"duplicate provision card coordinate: {coordinate}")
        ports_by_article[coordinate] = ArticlePorts(
            member_id=member_id,
            endpoint=endpoint,
            outgoing=outgoing_values,
            incoming=incoming_values,
        )
        card_count += 1

    semantic_cards: list[SemanticCardLite] = []
    semantic_postings: dict[str, list[int]] = {}
    semantic_by_article: dict[Coordinate, list[int]] = {}
    semantic_count = 0
    if str(manifest.get("projection_policy") or "").startswith("semantic-card-v2"):
        semantic_path = "projections/semantic_cards.jsonl.gz"
        seen_semantic_ids: set[str] = set()
        for row in _artifact_rows(
            manifest_path.parent,
            manifest,
            semantic_path,
            expected_type=_ARTIFACT_TYPES[semantic_path],
        ):
            card_id = str(row["id"])
            if card_id in seen_semantic_ids:
                raise LegalGraphLoadError(f"duplicate semantic card id: {card_id}")
            seen_semantic_ids.add(card_id)
            source = EndpointLite.from_row(row["source"], field="source")
            article_root = EndpointLite.from_row(
                row["article_root"], field="article_root"
            )
            if source.node_id is None or article_root.node_id is None:
                raise LegalGraphLoadError("semantic card requires source and article nodes")
            article_coordinate = (article_root.document_id, article_root.node_id)
            if article_coordinate not in ports_by_article:
                raise LegalGraphLoadError(
                    f"semantic card article root has no ProvisionCard: {article_coordinate}"
                )
            family_ids = _sorted_id_list(
                row.get("family_ids"), field="family_ids", card_id=card_id
            )
            terms = _sorted_id_list(
                row.get("terms"), field="terms", card_id=card_id
            )
            assertion_ids = _sorted_id_list(
                row.get("assertion_ids"), field="assertion_ids", card_id=card_id
            )
            coverage_keys = _sorted_id_list(
                row.get("coverage_keys"), field="coverage_keys", card_id=card_id
            )
            card = SemanticCardLite(
                card_id=card_id,
                entity_id=str(row.get("entity_id") or ""),
                semantic_type=str(row.get("semantic_type") or ""),
                source=source,
                article_root=article_root,
                family_ids=family_ids,
                terms=terms,
                assertion_ids=assertion_ids,
                coverage_keys=coverage_keys,
                relation_predicate=str(row.get("relation_predicate") or ""),
                label=str(row.get("label") or ""),
                card_status=str(row.get("card_status") or "SEMANTIC_READY"),
            )
            card_index = len(semantic_cards)
            semantic_cards.append(card)
            semantic_by_article.setdefault(article_coordinate, []).append(card_index)
            for term in terms:
                semantic_postings.setdefault(term.casefold(), []).append(card_index)
            semantic_count += 1

    retained_closures: dict[str, tuple[str, str]] = {}
    unresolved_assertion_ids: set[str] = set()
    seen_projection_ids: set[str] = set()
    edge_count = 0
    for row in _artifact_rows(
        manifest_path.parent,
        manifest,
        closures_path,
        expected_type=_ARTIFACT_TYPES[closures_path],
        validate_ids=required_projection_ids,
    ):
        if row.get("activation_policy") != SUPPORTED_ACTIVATION_POLICY:
            raise LegalGraphLoadError(
                f"unsupported activation policy: {row.get('activation_policy')!r}"
            )
        projection_id = str(row["id"])
        if projection_id in seen_projection_ids:
            raise LegalGraphLoadError(
                f"duplicate closure projection id: {projection_id}"
            )
        seen_projection_ids.add(projection_id)
        assertion_id = str(row["relation_assertion_id"])
        unresolved_assertion_ids.add(assertion_id)
        # validate_row already checked the ClosureMode enum; do not construct
        # it a second time for every projection.
        mode = str(row["closure_mode"])
        if projection_id in required_projection_ids:
            retained_closures[projection_id] = (assertion_id, mode)
        edge_count += 1

    missing_projections = required_projection_ids - seen_projection_ids
    if missing_projections:
        raise LegalGraphLoadError(
            "provision card references missing projection: "
            f"{min(missing_projections)}"
        )
    del seen_projection_ids, required_projection_ids

    closures_by_assertion: dict[str, list[tuple[str, str]]] = {}
    for projection_id, (assertion_id, mode) in retained_closures.items():
        closures_by_assertion.setdefault(assertion_id, []).append(
            (projection_id, mode)
        )
    del retained_closures

    edges: dict[str, EdgeLite] = {}
    seen_assertion_ids: set[str] = set()
    assertion_count = 0
    for row in _artifact_rows(
        manifest_path.parent,
        manifest,
        assertions_path,
        expected_type=_ARTIFACT_TYPES[assertions_path],
        validate_ids=closures_by_assertion.keys(),
    ):
        assertion_id = str(row["id"])
        if assertion_id in seen_assertion_ids:
            raise LegalGraphLoadError(
                f"duplicate relation assertion id: {assertion_id}"
            )
        seen_assertion_ids.add(assertion_id)
        unresolved_assertion_ids.discard(assertion_id)
        edge_specs = closures_by_assertion.pop(assertion_id, None)
        if edge_specs:
            source = EndpointLite.from_row(row["source"], field="source")
            target = EndpointLite.from_row(row["target"], field="target")
            predicate = str(row["predicate"])
            family = str(row["family"])
            resolution = str(row.get("resolution") or "")
            review_state = str(row.get("review_state") or "")
            legacy_kind = str(row.get("legacy_kind") or "")
            for projection_id, mode in edge_specs:
                edges[projection_id] = EdgeLite(
                    projection_id=projection_id,
                    assertion_id=assertion_id,
                    predicate=predicate,
                    family=family,
                    mode=mode,
                    resolution=resolution,
                    review_state=review_state,
                    legacy_kind=legacy_kind,
                    source=source,
                    target=target,
                )
        assertion_count += 1

    if unresolved_assertion_ids:
        raise LegalGraphLoadError(
            "closure references missing assertion: "
            f"{min(unresolved_assertion_ids)}"
        )
    if closures_by_assertion:
        raise LegalGraphLoadError(
            "closure references missing retained assertion: "
            f"{min(closures_by_assertion)}"
        )
    del seen_assertion_ids, unresolved_assertion_ids, closures_by_assertion

    # Canonicalize independently decoded card IDs to the EdgeLite ID objects.
    ports_by_article = {
        coordinate: ArticlePorts(
            member_id=ports.member_id,
            endpoint=ports.endpoint,
            outgoing=tuple(edges[value].projection_id for value in ports.outgoing),
            incoming=tuple(edges[value].projection_id for value in ports.incoming),
        )
        for coordinate, ports in ports_by_article.items()
    }

    load_ms = (time.perf_counter() - started) * 1000
    return LegalGraphSnapshot(
        root=manifest_path.parent,
        generation_id=str(manifest["generation_id"]),
        authority_generation=str(manifest["authority_generation"]),
        content_sha256=str(manifest["content_sha256"]),
        projection_policy=str(manifest["projection_policy"]),
        pointer_sha256=pointer_sha,
        runtime_wired_in_artifact=bool(manifest.get("runtime_wired", False)),
        ports_by_article=MappingProxyType(ports_by_article),
        edge_by_projection_id=MappingProxyType(edges),
        semantic_cards=tuple(semantic_cards),
        semantic_postings=MappingProxyType({
            term: tuple(indexes)
            for term, indexes in semantic_postings.items()
        }),
        semantic_by_article=MappingProxyType({
            coordinate: tuple(indexes)
            for coordinate, indexes in semantic_by_article.items()
        }),
        loaded_rows=assertion_count + edge_count + card_count + semantic_count,
        load_ms=load_ms,
    )


def _validate_sorted_id_list(value: Any, *, field: str, card_id: str) -> None:
    if not isinstance(value, list):
        raise LegalGraphLoadError(
            f"provision card {card_id} {field} must be a string list"
        )
    previous: str | None = None
    for item in value:
        if not isinstance(item, str) or not item:
            raise LegalGraphLoadError(
                f"provision card {card_id} {field} must be a string list"
            )
        if previous is not None and item <= previous:
            reason = "contains duplicate IDs" if item == previous else "is not sorted"
            raise LegalGraphLoadError(
                f"provision card {card_id} {field} {reason}"
            )
        previous = item


def _sorted_id_list(value: Any, *, field: str, card_id: str) -> tuple[str, ...]:
    _validate_sorted_id_list(value, field=field, card_id=card_id)
    assert isinstance(value, list)
    return tuple(value)


def _artifact_rows(
    generation_root: Path,
    manifest: Mapping[str, Any],
    relative: str,
    *,
    expected_type: RowType,
    validate_ids: AbstractSet[str] | None = None,
) -> Iterable[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    metadata = artifacts.get(relative) if isinstance(artifacts, Mapping) else None
    if not isinstance(metadata, Mapping):
        raise LegalGraphLoadError(f"manifest artifact missing: {relative}")
    _validate_artifact_metadata(
        relative, metadata=metadata, expected_type=expected_type
    )
    path = _safe_path(generation_root, relative)
    expected_bytes = int(metadata["bytes"])
    expected_rows = int(metadata["rows"])
    expected_generation = manifest["generation_id"]
    expected_authority = manifest["authority_generation"]
    row_validator = validate_row
    count = 0
    with path.open("rb") as handle:
        packed = handle.read()
    # Hash and parse this immutable in-memory byte snapshot.  The physical
    # artifact is opened once, so a path replacement after verification cannot
    # change the bytes fed to gzip/JSON.  Peak transient storage is bounded by
    # the largest compressed runtime artifact (currently about 28 MiB).
    if len(packed) != expected_bytes:
        raise LegalGraphLoadError(f"artifact byte count mismatch: {relative}")
    if hashlib.sha256(packed).hexdigest() != metadata["sha256"]:
        raise LegalGraphLoadError(f"artifact sha256 mismatch: {relative}")
    try:
        with gzip.GzipFile(
            filename="", mode="rb", fileobj=io.BytesIO(packed)
        ) as decoded:
            for line_no, payload in enumerate(decoded, 1):
                if not payload or payload.isspace():
                    continue
                row = _json_row(
                    payload, relative=relative, line_no=line_no
                )
                if row.get("generation_id") != expected_generation:
                    raise LegalGraphLoadError(
                        f"row generation mismatch: {relative}:{line_no}"
                    )
                if row.get("authority_generation") != expected_authority:
                    raise LegalGraphLoadError(
                        f"row authority mismatch: {relative}:{line_no}"
                    )
                if row.get("schema_version") != SCHEMA_VERSION:
                    raise LegalGraphLoadError(
                        f"row schema mismatch: {relative}:{line_no}"
                    )
                if row.get("row_type") != expected_type.value:
                    raise LegalGraphLoadError(
                        f"row type mismatch: {relative}:{line_no}"
                    )
                # Artifact hash, compiler-bound manifest, envelope, row count,
                # and duplicate checks cover audit-only rows.  Run the full
                # canonical validator on every row admitted to the runtime
                # object graph; cards are all admitted, while non-current
                # closures/assertions are deliberately never materialized.
                if validate_ids is None or str(row.get("id") or "") in validate_ids:
                    try:
                        row_validator(row, expected_type=expected_type)
                    except SchemaValidationError as exc:
                        raise LegalGraphLoadError(
                            f"row schema invalid {relative}:{line_no}: {exc}"
                        ) from exc
                count += 1
                yield row
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise LegalGraphLoadError(
            f"invalid gzip artifact {relative}: {exc}"
        ) from exc
    if count != expected_rows:
        raise LegalGraphLoadError(
            f"artifact row count mismatch: {relative} ({count}!={expected_rows})"
        )


def _json_row(
    payload: bytes, *, relative: str, line_no: int
) -> dict[str, Any]:
    """Decode one hot-path row; semantic duplicate IDs are checked by loaders."""
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegalGraphLoadError(
            f"invalid JSON {relative}:{line_no}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise LegalGraphLoadError(
            f"JSON object required: {relative}:{line_no}"
        )
    return value


def _validate_artifact_metadata(
    relative: str,
    *,
    metadata: Mapping[str, Any],
    expected_type: RowType,
) -> None:
    expected = {
        "path": relative,
        "logical_path": relative.removesuffix(".gz"),
        "format": "jsonl",
        "compression": "gzip",
        "row_type": expected_type.value,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise LegalGraphLoadError(
                f"artifact metadata mismatch {relative}: {field}"
            )
    for field in ("bytes", "rows"):
        value = metadata.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise LegalGraphLoadError(
                f"artifact metadata invalid {relative}: {field}"
            )
    digest = metadata.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise LegalGraphLoadError(
            f"artifact metadata invalid {relative}: sha256"
        )
