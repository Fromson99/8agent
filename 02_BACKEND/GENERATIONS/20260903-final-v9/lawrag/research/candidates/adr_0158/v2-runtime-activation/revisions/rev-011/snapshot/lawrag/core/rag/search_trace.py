"""Append-only, request-local trace primitives for legal retrieval.

This module deliberately depends on the Python standard library only.  It is
safe for low-level retrievers to import: importing it must not pull in the RAG
index, vector runtime, or any retrieval implementation and create a cycle.

``SearchTrace`` is an event log.  Coordinates are never deleted and there is
no reject/remove API.  Seeing the same coordinate through another channel
appends a provenance event while the number of observed coordinates remains
unchanged.  Selection and deferral are also events; their current projections
can change without erasing their history.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math
from typing import Any
import uuid


Coordinate = tuple[str, object]


def _json_safe(value: Any) -> Any:
    """Return a deterministic JSON value or fail on an unstable object.

    ``repr`` is intentionally not used as a fallback: object reprs frequently
    contain memory addresses, which would make fingerprints process-dependent.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and infinity are not valid trace values")
        return value
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("trace mapping keys must be strings")
            out[key] = _json_safe(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_json_safe(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False))
    raise TypeError(
        f"unsupported trace value {type(value).__module__}."
        f"{type(value).__qualname__}")


def canonical_json(value: Any) -> str:
    """Serialize ``value`` using the repository's stable trace representation."""
    return json.dumps(
        _json_safe(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)


def stable_fingerprint(value: Any, *, namespace: str = "") -> str:
    """Return a namespaced SHA-256 over canonical JSON.

    The namespace is inside the hashed envelope, so identical data used as a
    query, operator, edge, or coordinate cannot accidentally share an ID.
    """
    envelope = {"namespace": str(namespace), "value": _json_safe(value)}
    digest = hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _coordinate(value: Coordinate | Iterable[object]) -> Coordinate:
    try:
        doc_id, node = tuple(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("coordinate must contain exactly (doc_id, node)") from exc
    doc = str(doc_id or "").strip()
    if not doc:
        raise ValueError("coordinate doc_id is empty")
    # Validate now so no later summary/fingerprint can fail unexpectedly.
    _json_safe(node)
    return doc, node


def coordinate_fingerprint(coordinate: Coordinate | Iterable[object]) -> str:
    doc_id, node = _coordinate(coordinate)
    return stable_fingerprint(
        {"doc_id": doc_id, "node": _json_safe(node)}, namespace="coordinate")


@dataclass(frozen=True)
class TraceEvent:
    """One immutable event in a :class:`SearchTrace`.

    Payload is stored as canonical JSON.  The ``payload`` property returns a
    fresh object, preventing callers from mutating the already-recorded event.
    """

    seq: int
    kind: str
    call_id: str
    coordinate: Coordinate | None
    _payload_json: str

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._payload_json)
        return value if isinstance(value, dict) else {"value": value}

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "call_id": self.call_id,
            "coordinate": ([_json_safe(self.coordinate[0]),
                            _json_safe(self.coordinate[1])]
                           if self.coordinate is not None else None),
            "payload": self.payload,
        }


class SearchTrace:
    """Append-only retrieval history for one question.

    The class keeps small monotone indexes for fast duplicate detection.  They
    are projections of ``events`` and never remove an entry.
    """

    def __init__(self, question: str, *, corpus_fingerprint: str = "",
                 trace_id: str | None = None,
                 content_snapshot: Any = None) -> None:
        from lawrag.core.rag.content_snapshot import (
            ContentSnapshotError,
            current_content_snapshot,
        )
        process_snapshot = current_content_snapshot()
        if content_snapshot is None:
            # Keep the module import graph stdlib-only.  The optional runtime
            # identity is resolved lazily only when a trace is instantiated.
            content_snapshot = process_snapshot
        elif process_snapshot is not None:
            supplied_hash = str(
                getattr(content_snapshot, "content_snapshot_sha256", "")
                or (content_snapshot.get("content_snapshot_sha256")
                    if isinstance(content_snapshot, Mapping) else ""))
            if not supplied_hash:
                raise ContentSnapshotError("trace snapshot identity is incomplete")
            if supplied_hash != process_snapshot.content_snapshot_sha256:
                raise ContentSnapshotError(
                    "trace and process content snapshots disagree")
        self.trace_id = str(trace_id or uuid.uuid4().hex)
        self.question = str(question or "")
        self.corpus_fingerprint = str(corpus_fingerprint or "")
        self._content_snapshot_source = content_snapshot
        receipt = None
        if content_snapshot is not None:
            if hasattr(content_snapshot, "compact_receipt"):
                receipt = content_snapshot.compact_receipt()
            elif isinstance(content_snapshot, Mapping):
                receipt = dict(content_snapshot)
            else:
                raise TypeError("content_snapshot must provide compact_receipt()")
        # Canonical round-trip makes a caller-owned mapping immutable here.
        self._content_snapshot_json = (
            canonical_json(receipt) if receipt is not None else "")
        self._events: list[TraceEvent] = []
        self._coordinates: dict[str, Coordinate] = {}

    def _artifact_receipt(self, doc_id: str) -> dict[str, Any] | None:
        snapshot = self._content_snapshot_source
        if snapshot is None:
            return None
        if hasattr(snapshot, "provenance_for_document"):
            artifact = snapshot.provenance_for_document(doc_id)
            if hasattr(artifact, "receipt"):
                return _json_safe(artifact.receipt())
        if isinstance(snapshot, Mapping):
            if "artifacts" not in snapshot:
                raise ValueError(
                    "compact content snapshot cannot supply trace provenance")
            matches = [
                row for row in snapshot.get("artifacts", ())
                if isinstance(row, Mapping) and row.get("document_id") == doc_id
            ]
            if len(matches) > 1:
                raise ValueError(f"ambiguous content provenance: {doc_id}")
            if matches:
                return _json_safe(dict(matches[0]))
            raise ValueError(f"unmapped trace document: {doc_id}")
        return None

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        """Immutable view of all recorded events in insertion order."""
        return tuple(self._events)

    def _append(self, kind: str, *, call_id: str = "",
                coordinate: Coordinate | None = None,
                payload: Mapping[str, Any] | None = None) -> TraceEvent:
        name = str(kind or "").strip()
        if not name:
            raise ValueError("trace event kind is empty")
        normalized_coordinate = (_coordinate(coordinate)
                                 if coordinate is not None else None)
        payload_value = dict(payload or {})
        if normalized_coordinate is not None:
            provenance = self._artifact_receipt(normalized_coordinate[0])
            if provenance is not None:
                supplied = payload_value.get("content_provenance")
                if supplied is not None and supplied != provenance:
                    raise ValueError("trace content_provenance disagrees with snapshot")
                payload_value["content_provenance"] = provenance
        payload_json = canonical_json(payload_value)
        event = TraceEvent(
            seq=len(self._events) + 1,
            kind=name,
            call_id=str(call_id or ""),
            coordinate=normalized_coordinate,
            _payload_json=payload_json,
        )
        self._events.append(event)
        return event

    def observe_coordinate(self, coordinate: Coordinate | Iterable[object], *,
                           origin: str, observation_depth: int = 0,
                           call_id: str = "",
                           metadata: Mapping[str, Any] | None = None) -> str:
        """Append an observation and return the coordinate fingerprint.

        Re-observation records ``coordinate_rediscovered``.  It never creates a
        second coordinate ledger row and never changes an earlier event.
        """
        if (isinstance(observation_depth, bool)
                or not isinstance(observation_depth, int)
                or observation_depth < 0):
            raise ValueError("observation_depth must be a non-negative integer")
        source = str(origin or "").strip()
        if not source:
            raise ValueError("coordinate origin is empty")
        normalized = _coordinate(coordinate)
        fingerprint = coordinate_fingerprint(normalized)
        first = fingerprint not in self._coordinates
        if first:
            self._coordinates[fingerprint] = normalized
        self._append(
            "coordinate_observed" if first else "coordinate_rediscovered",
            call_id=call_id,
            coordinate=normalized,
            payload={
                "coordinate_fingerprint": fingerprint,
                "origin": source,
                "observation_depth": observation_depth,
                "metadata": dict(metadata or {}),
            },
        )
        return fingerprint

    def observe_coordinates(self, coordinates: Iterable[Coordinate], *,
                            origin: str, observation_depth: int = 0,
                            call_id: str = "",
                            metadata: Mapping[str, Any] | None = None) \
            -> tuple[str, ...]:
        return tuple(self.observe_coordinate(
            coordinate, origin=origin, observation_depth=observation_depth,
            call_id=call_id, metadata=metadata) for coordinate in coordinates)

    def _known_coordinates(self, coordinates: Iterable[Coordinate]) \
            -> list[tuple[Coordinate, str]]:
        out: list[tuple[Coordinate, str]] = []
        seen: set[str] = set()
        for raw in coordinates:
            coordinate = _coordinate(raw)
            fingerprint = coordinate_fingerprint(coordinate)
            if fingerprint not in self._coordinates:
                raise KeyError(f"coordinate was not observed: {coordinate!r}")
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            out.append((coordinate, fingerprint))
        return out

    def mark_selected(self, coordinates: Iterable[Coordinate], *, stage: str,
                      call_id: str = "", reason: str = "") -> None:
        """Append selection events without erasing prior deferred history."""
        for coordinate, fingerprint in self._known_coordinates(coordinates):
            self._append(
                "coordinate_selected", call_id=call_id, coordinate=coordinate,
                payload={"coordinate_fingerprint": fingerprint,
                         "stage": str(stage or ""), "reason": str(reason or "")})

    def mark_deferred(self, coordinates: Iterable[Coordinate], *, stage: str,
                      call_id: str = "", reason: str = "") -> None:
        """Append deferral events; the coordinate remains in the ledger."""
        for coordinate, fingerprint in self._known_coordinates(coordinates):
            self._append(
                "coordinate_deferred", call_id=call_id, coordinate=coordinate,
                payload={"coordinate_fingerprint": fingerprint,
                         "stage": str(stage or ""), "reason": str(reason or "")})

    def mark_inspected(self, coordinate: Coordinate, *, facet_ids: Iterable[str],
                       observation_depth: int, call_id: str = "",
                       metadata: Mapping[str, Any] | None = None) -> None:
        """Record a deeper reading of an existing coordinate."""
        normalized, fingerprint = self._known_coordinates([coordinate])[0]
        if (isinstance(observation_depth, bool)
                or not isinstance(observation_depth, int)
                or observation_depth < 0):
            raise ValueError("observation_depth must be a non-negative integer")
        facets = list(dict.fromkeys(
            str(value).strip() for value in facet_ids if str(value).strip()))
        self._append(
            "coordinate_inspected", call_id=call_id, coordinate=normalized,
            payload={
                "coordinate_fingerprint": fingerprint,
                "facet_ids": facets,
                "observation_depth": observation_depth,
                "metadata": dict(metadata or {}),
            })

    def record_query(self, query: str, *, role: str = "",
                     parameters: Mapping[str, Any] | None = None,
                     call_id: str = "") -> str:
        value = {
            "query": str(query or ""),
            "role": str(role or ""),
            "parameters": dict(parameters or {}),
        }
        fingerprint = stable_fingerprint(value, namespace="query")
        self._append("query_recorded", call_id=call_id,
                     payload={**value, "fingerprint": fingerprint})
        return fingerprint

    def record_operator(self, operator: str, *, query_fingerprint: str = "",
                        seeds: Iterable[Coordinate] = (), scope: Any = None,
                        parameters: Mapping[str, Any] | None = None,
                        call_id: str = "") -> str:
        seed_rows = [
            {"doc_id": coordinate[0], "node": _json_safe(coordinate[1])}
            for coordinate in (_coordinate(seed) for seed in seeds)
        ]
        value = {
            "operator": str(operator or ""),
            "query_fingerprint": str(query_fingerprint or ""),
            "seeds": seed_rows,
            "scope": _json_safe(scope),
            "parameters": dict(parameters or {}),
        }
        fingerprint = stable_fingerprint(value, namespace="operator")
        self._append("operator_recorded", call_id=call_id,
                     payload={**value, "fingerprint": fingerprint})
        return fingerprint

    def record_edge(self, source: Coordinate, target: Coordinate, *,
                    relation: str, direction: str,
                    provenance: str | Iterable[str] = (),
                    state: str = "observed", call_id: str = "",
                    metadata: Mapping[str, Any] | None = None) -> str:
        src, dst = _coordinate(source), _coordinate(target)
        values = ([provenance] if isinstance(provenance, str)
                  else list(provenance))
        provenance_rows = sorted(set(
            str(value).strip() for value in values if str(value).strip()))
        identity = {
            "source": {"doc_id": src[0], "node": _json_safe(src[1])},
            "target": {"doc_id": dst[0], "node": _json_safe(dst[1])},
            "relation": str(relation or ""),
            "direction": str(direction or ""),
            "provenance": provenance_rows,
        }
        content_provenance = {}
        for role, coordinate in (("source", src), ("target", dst)):
            receipt = self._artifact_receipt(coordinate[0])
            if receipt is not None:
                content_provenance[role] = receipt
        if content_provenance:
            identity["content_provenance"] = content_provenance
        fingerprint = stable_fingerprint(identity, namespace="edge")
        self._append(
            "edge_recorded", call_id=call_id,
            payload={**identity, "fingerprint": fingerprint,
                     "state": str(state or "observed"),
                     "metadata": dict(metadata or {})})
        return fingerprint

    def _fingerprints(self, event_kind: str) -> frozenset[str]:
        return frozenset(
            str(event.payload.get("fingerprint")) for event in self._events
            if event.kind == event_kind and event.payload.get("fingerprint"))

    def query_fingerprints(self) -> frozenset[str]:
        return self._fingerprints("query_recorded")

    def operator_fingerprints(self) -> frozenset[str]:
        return self._fingerprints("operator_recorded")

    def edge_fingerprints(self) -> frozenset[str]:
        return self._fingerprints("edge_recorded")

    def seen_coordinates(self) -> frozenset[Coordinate]:
        return frozenset(self._coordinates.values())

    def coordinate_ledger(self) -> list[dict[str, Any]]:
        """Materialize the coordinate projection without mutating the log."""
        rows: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in self._events:
            if event.coordinate is None:
                continue
            payload = event.payload
            fingerprint = str(payload.get("coordinate_fingerprint") or
                              coordinate_fingerprint(event.coordinate))
            row = rows.get(fingerprint)
            if row is None:
                row = {
                    "coordinate_fingerprint": fingerprint,
                    "coordinate": [_json_safe(event.coordinate[0]),
                                   _json_safe(event.coordinate[1])],
                    "origins": [],
                    "observation_count": 0,
                    "observation_depths": [],
                    "inspected_facets": [],
                    "status": "observed",
                    "status_history": [],
                }
                rows[fingerprint] = row
                order.append(fingerprint)
            if (payload.get("content_provenance") is not None
                    and "content_provenance" not in row):
                row["content_provenance"] = payload["content_provenance"]
            if event.kind in {"coordinate_observed", "coordinate_rediscovered"}:
                origin = str(payload.get("origin") or "")
                if origin and origin not in row["origins"]:
                    row["origins"].append(origin)
                row["observation_count"] += 1
                row["observation_depths"].append(
                    int(payload.get("observation_depth") or 0))
            elif event.kind == "coordinate_inspected":
                for facet in payload.get("facet_ids") or []:
                    if facet not in row["inspected_facets"]:
                        row["inspected_facets"].append(facet)
                row["observation_depths"].append(
                    int(payload.get("observation_depth") or 0))
            elif event.kind == "coordinate_selected":
                row["status"] = "selected"
                row["status_history"].append({
                    "status": "selected", "seq": event.seq,
                    "stage": payload.get("stage") or "",
                    "reason": payload.get("reason") or "",
                })
            elif event.kind == "coordinate_deferred":
                row["status"] = "deferred"
                row["status_history"].append({
                    "status": "deferred", "seq": event.seq,
                    "stage": payload.get("stage") or "",
                    "reason": payload.get("reason") or "",
                })
        for row in rows.values():
            depths = row.pop("observation_depths")
            row["min_observation_depth"] = min(depths) if depths else None
            row["max_observation_depth"] = max(depths) if depths else None
        return [rows[fingerprint] for fingerprint in order]

    def summary(self) -> dict[str, Any]:
        """Return a compact structure accepted by strict ``json.dumps``."""
        ledger = self.coordinate_ledger()
        kind_counts = Counter(event.kind for event in self._events)
        origin_coordinates: dict[str, set[str]] = {}
        origin_events: Counter[str] = Counter()
        depth_events: Counter[int] = Counter()
        edge_states: Counter[str] = Counter()
        for event in self._events:
            payload = event.payload
            if event.kind in {"coordinate_observed", "coordinate_rediscovered"}:
                origin = str(payload.get("origin") or "")
                fingerprint = str(payload.get("coordinate_fingerprint") or "")
                if origin:
                    origin_events[origin] += 1
                    origin_coordinates.setdefault(origin, set()).add(fingerprint)
                depth_events[int(payload.get("observation_depth") or 0)] += 1
            elif event.kind == "coordinate_inspected":
                depth_events[int(payload.get("observation_depth") or 0)] += 1
            elif event.kind == "edge_recorded":
                edge_states[str(payload.get("state") or "observed")] += 1
        status_counts = Counter(row["status"] for row in ledger)
        out = {
            "trace_id": self.trace_id,
            "question": self.question,
            "corpus_fingerprint": self.corpus_fingerprint,
            "event_count": len(self._events),
            "event_kinds": dict(sorted(kind_counts.items())),
            "observed_coordinates": len(ledger),
            "rediscovery_events": kind_counts.get("coordinate_rediscovered", 0),
            "selected_coordinates": status_counts.get("selected", 0),
            "deferred_coordinates": status_counts.get("deferred", 0),
            "origins": {key: len(value) for key, value in sorted(
                origin_coordinates.items())},
            "origin_events": dict(sorted(origin_events.items())),
            "observation_depth_events": {
                str(key): value for key, value in sorted(depth_events.items())},
            "queries": {
                "events": kind_counts.get("query_recorded", 0),
                "unique": len(self.query_fingerprints()),
            },
            "operators": {
                "events": kind_counts.get("operator_recorded", 0),
                "unique": len(self.operator_fingerprints()),
            },
            "edges": {
                "events": kind_counts.get("edge_recorded", 0),
                "unique": len(self.edge_fingerprints()),
                "states": dict(sorted(edge_states.items())),
            },
        }
        if self._content_snapshot_json:
            out["content_snapshot"] = json.loads(self._content_snapshot_json)
            document_ids = {coordinate[0]
                            for coordinate in self._coordinates.values()}
            for event in self._events:
                if event.kind != "edge_recorded":
                    continue
                payload = event.payload
                for endpoint in (payload.get("source"), payload.get("target")):
                    if isinstance(endpoint, Mapping) and endpoint.get("doc_id"):
                        document_ids.add(str(endpoint["doc_id"]))
            provenance = {
                doc_id: receipt
                for doc_id in sorted(document_ids)
                if (receipt := self._artifact_receipt(doc_id)) is not None
            }
            if provenance:
                out["content_provenance"] = provenance
        # Assert the public contract here, close to the boundary where it matters.
        json.dumps(out, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return out


__all__ = [
    "Coordinate",
    "SearchTrace",
    "TraceEvent",
    "canonical_json",
    "coordinate_fingerprint",
    "stable_fingerprint",
]
