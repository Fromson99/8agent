"""Generation-locked retrieval shortcuts created from reviewed feedback.

A shortcut remembers verified landings, never a final legal answer.  It is only
eligible when the query signature and every source/authority/semantic generation
match exactly.  Feedback-created candidates are inert until reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "query-shortcut-v2"
LEGACY_SCHEMA_VERSION = "query-shortcut-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,191}$")
_STATUSES = frozenset({"CANDIDATE", "REVIEWED", "PINNED", "STALE", "REJECTED"})
_USABLE = frozenset({"REVIEWED", "PINNED"})
_KINDS = frozenset({"STRUCTURAL_UNIT", "SEMANTIC_CLAUSE", "RULE", "PROVISO", "RELATION"})
_AXES = (
    "scopes",
    "actors",
    "actions",
    "objects",
    "conditions",
    "requested_outputs",
)
_TRANSITIONS = {
    "CANDIDATE": frozenset({"REVIEWED", "REJECTED"}),
    "REVIEWED": frozenset({"PINNED", "STALE", "REJECTED"}),
    "PINNED": frozenset({"STALE"}),
    "STALE": frozenset(),
    "REJECTED": frozenset(),
}


class ShortcutContractError(ValueError):
    """A shortcut is ambiguous, ungrounded, or unsafe to reuse."""


def _normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    rows = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    return tuple(sorted({_normalize(row) for row in rows if _normalize(row)}))


def _sha(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _hash(value: object, field: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise ShortcutContractError(f"{field} must be sha256")
    return text


def _identifier(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not _ID.fullmatch(text):
        raise ShortcutContractError(f"invalid {field}: {text!r}")
    return text


def _reject_unknown(blob: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(blob) - allowed)
    if unknown:
        raise ShortcutContractError(
            "unknown shortcut fields: " + ", ".join(str(value) for value in unknown)
        )


@dataclass(frozen=True)
class QuerySignature:
    source_set_sha256: str
    authority_generation: str
    semantic_generation: str
    axes: Mapping[str, tuple[str, ...]]
    sha256: str
    content_snapshot_sha256: str | None = None

    def payload(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "source_set_sha256": self.source_set_sha256,
            "authority_generation": self.authority_generation,
            "semantic_generation": self.semantic_generation,
            "axes": {name: list(self.axes[name]) for name in _AXES},
        }
        if self.content_snapshot_sha256 is not None:
            value["content_snapshot_sha256"] = self.content_snapshot_sha256
        return value


@dataclass(frozen=True)
class Landing:
    kind: str
    id: str


@dataclass(frozen=True)
class Shortcut:
    shortcut_id: str
    status: str
    signature_sha256: str
    source_set_sha256: str
    authority_generation: str
    semantic_generation: str
    landings: tuple[Landing, ...]
    feedback_event_ids: tuple[str, ...]
    evidence_receipt_sha256: str
    bundle_sha256: str | None
    revision: int
    previous_record_sha256: str | None
    record_sha256: str
    content_snapshot_sha256: str | None = None

    def usable_for(self, signature: QuerySignature) -> bool:
        return (
            self.status in _USABLE
            and self.signature_sha256 == signature.sha256
            and self.source_set_sha256 == signature.source_set_sha256
            and self.authority_generation == signature.authority_generation
            and self.semantic_generation == signature.semantic_generation
            and self.content_snapshot_sha256 == signature.content_snapshot_sha256
        )


@dataclass(frozen=True)
class ShortcutResolutionContext:
    """Current visible graph surface and installed evidence receipts.

    ``visible_landings`` is already access-filtered for the caller, so selecting
    a shortcut cannot bypass document or tenant ACL checks.
    """

    visible_landings: frozenset[tuple[str, str]]
    evidence_receipt_sha256s: frozenset[str]
    content_snapshot_sha256: str | None = None

    @classmethod
    def build(
        cls,
        *,
        visible_landings: Iterable[tuple[str, str]],
        evidence_receipt_sha256s: Iterable[str],
        content_snapshot_sha256: str | None = None,
    ) -> "ShortcutResolutionContext":
        landings = frozenset((str(kind), str(target_id)) for kind, target_id in visible_landings)
        for kind, target_id in landings:
            if kind not in _KINDS or not _ID.fullmatch(target_id):
                raise ShortcutContractError(
                    f"invalid visible shortcut landing: {(kind, target_id)!r}"
                )
        receipts = frozenset(
            _hash(value, "evidence_receipt_sha256")
            for value in evidence_receipt_sha256s
        )
        snapshot = (
            None
            if content_snapshot_sha256 is None
            else _hash(content_snapshot_sha256, "content_snapshot_sha256")
        )
        return cls(landings, receipts, snapshot)


def build_signature(
    *,
    source_set_sha256: str,
    authority_generation: str,
    semantic_generation: str,
    content_snapshot_sha256: str | None = None,
    scopes: object = (),
    actors: object = (),
    actions: object = (),
    objects: object = (),
    conditions: object = (),
    requested_outputs: object = (),
) -> QuerySignature:
    axes = {
        "scopes": _values(scopes),
        "actors": _values(actors),
        "actions": _values(actions),
        "objects": _values(objects),
        "conditions": _values(conditions),
        "requested_outputs": _values(requested_outputs),
    }
    if not any(axes.values()):
        raise ShortcutContractError("query signature requires at least one semantic axis")
    signature = QuerySignature(
        source_set_sha256=_hash(source_set_sha256, "source_set_sha256"),
        authority_generation=_identifier(
            authority_generation, "authority_generation"
        ),
        semantic_generation=_identifier(
            semantic_generation, "semantic_generation"
        ),
        axes=axes,
        sha256="",
        content_snapshot_sha256=(
            None
            if content_snapshot_sha256 is None
            else _hash(content_snapshot_sha256, "content_snapshot_sha256")
        ),
    )
    return QuerySignature(**{**signature.__dict__, "sha256": _sha(signature.payload())})


def shortcut_from_mapping(blob: Mapping[str, Any]) -> Shortcut:
    schema_version = blob.get("schema_version")
    if schema_version not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise ShortcutContractError(
            f"unsupported shortcut schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "shortcut_id",
                "status",
                "signature_sha256",
                "source_set_sha256",
                "authority_generation",
                "semantic_generation",
                "landings",
                "feedback_event_ids",
                "evidence_receipt_sha256",
                "bundle_sha256",
                "revision",
                "previous_record_sha256",
                "record_sha256",
                "content_snapshot_sha256",
            }
        ),
    )
    if schema_version == SCHEMA_VERSION:
        missing_hash_fields = {
            "previous_record_sha256",
            "record_sha256",
        } - set(blob)
        if missing_hash_fields:
            raise ShortcutContractError(
                "query-shortcut-v2 requires hash-chain fields: "
                + ", ".join(sorted(missing_hash_fields))
            )
    shortcut_id = _identifier(blob.get("shortcut_id"), "shortcut_id")
    status = str(blob.get("status") or "")
    if status not in _STATUSES:
        raise ShortcutContractError(f"invalid shortcut status: {status!r}")
    landings: list[Landing] = []
    seen: set[tuple[str, str]] = set()
    rows = blob.get("landings")
    if not isinstance(rows, list) or not rows:
        raise ShortcutContractError("shortcut landings must be a non-empty list")
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ShortcutContractError(f"landings[{position}] must be an object")
        kind = str(row.get("kind") or "")
        target_id = str(row.get("id") or "")
        if set(row) - {"kind", "id"}:
            raise ShortcutContractError(
                f"unknown landing fields at position {position}"
            )
        if kind not in _KINDS or not _ID.fullmatch(target_id):
            raise ShortcutContractError(f"invalid landing at position {position}")
        key = kind, target_id
        if key in seen:
            raise ShortcutContractError(f"duplicate landing: {key}")
        seen.add(key)
        landings.append(Landing(kind, target_id))
    raw_feedback_ids = blob.get("feedback_event_ids")
    if not isinstance(raw_feedback_ids, list):
        raise ShortcutContractError("feedback_event_ids must be a list")
    feedback_ids = tuple(
        _identifier(value, "feedback_event_id") for value in raw_feedback_ids
    )
    if len(feedback_ids) != len(set(feedback_ids)):
        raise ShortcutContractError("feedback_event_ids must be unique")
    if status in _USABLE and not feedback_ids:
        raise ShortcutContractError("reviewed shortcut requires feedback provenance")
    bundle = blob.get("bundle_sha256")
    if bundle is not None:
        bundle = _hash(bundle, "bundle_sha256")
    authority_generation = _identifier(
        blob.get("authority_generation"), "authority_generation"
    )
    semantic_generation = _identifier(
        blob.get("semantic_generation"), "semantic_generation"
    )
    raw_snapshot = blob.get("content_snapshot_sha256")
    if schema_version == SCHEMA_VERSION and raw_snapshot is None:
        raise ShortcutContractError(
            "query-shortcut-v2 requires content_snapshot_sha256"
        )
    content_snapshot = (
        None
        if raw_snapshot is None
        else _hash(raw_snapshot, "content_snapshot_sha256")
    )
    revision = blob.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ShortcutContractError("shortcut revision must be a positive integer")
    raw_previous = blob.get("previous_record_sha256")
    previous = None if raw_previous is None else _hash(
        raw_previous, "previous_record_sha256"
    )
    if revision == 1 and previous is not None:
        raise ShortcutContractError("revision 1 cannot have a previous record")
    if revision > 1 and previous is None:
        raise ShortcutContractError("later shortcut revision requires previous record hash")
    normalized = dict(blob)
    normalized.pop("record_sha256", None)
    record_sha256 = _sha(normalized)
    declared = blob.get("record_sha256")
    if schema_version == SCHEMA_VERSION:
        _hash(declared, "record_sha256")
    if declared is not None and declared != record_sha256:
        raise ShortcutContractError("shortcut record_sha256 mismatch")
    return Shortcut(
        shortcut_id=shortcut_id,
        status=status,
        signature_sha256=_hash(blob.get("signature_sha256"), "signature_sha256"),
        source_set_sha256=_hash(blob.get("source_set_sha256"), "source_set_sha256"),
        authority_generation=authority_generation,
        semantic_generation=semantic_generation,
        landings=tuple(landings),
        feedback_event_ids=feedback_ids,
        evidence_receipt_sha256=_hash(
            blob.get("evidence_receipt_sha256"), "evidence_receipt_sha256"
        ),
        bundle_sha256=bundle,
        revision=revision,
        previous_record_sha256=previous,
        record_sha256=record_sha256,
        content_snapshot_sha256=content_snapshot,
    )


def load_shortcuts(path: str | Path) -> tuple[Shortcut, ...]:
    """Read and fold hash-linked append-only shortcut revision streams."""

    source = Path(path)
    latest: dict[str, Shortcut] = {}
    order: list[str] = []
    try:
        lines = source.read_text("utf-8").splitlines()
    except OSError as exc:
        raise ShortcutContractError(f"cannot read shortcut store {source}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            blob = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ShortcutContractError(
                f"invalid shortcut JSON at line {line_number}: {exc}"
            ) from exc
        if not isinstance(blob, Mapping):
            raise ShortcutContractError(f"shortcut line {line_number} must be an object")
        shortcut = shortcut_from_mapping(blob)
        previous = latest.get(shortcut.shortcut_id)
        if previous is None:
            if shortcut.revision != 1 or shortcut.previous_record_sha256 is not None:
                raise ShortcutContractError(
                    f"shortcut history must start at revision 1: {shortcut.shortcut_id}"
                )
            order.append(shortcut.shortcut_id)
        else:
            if shortcut.revision != previous.revision + 1:
                raise ShortcutContractError(
                    f"non-consecutive shortcut revision: {shortcut.shortcut_id}"
                )
            if shortcut.previous_record_sha256 != previous.record_sha256:
                raise ShortcutContractError(
                    f"shortcut previous record hash mismatch: {shortcut.shortcut_id}"
                )
            if shortcut.status not in _TRANSITIONS[previous.status]:
                raise ShortcutContractError(
                    f"invalid shortcut status transition: "
                    f"{previous.status} -> {shortcut.status}"
                )
            if (
                shortcut.signature_sha256 != previous.signature_sha256
                or shortcut.source_set_sha256 != previous.source_set_sha256
                or shortcut.authority_generation != previous.authority_generation
                or shortcut.semantic_generation != previous.semantic_generation
                or shortcut.content_snapshot_sha256 != previous.content_snapshot_sha256
            ):
                raise ShortcutContractError(
                    f"shortcut identity changed across revisions: {shortcut.shortcut_id}"
                )
        latest[shortcut.shortcut_id] = shortcut
    return tuple(latest[shortcut_id] for shortcut_id in order)


def select_shortcut(
    shortcuts: Iterable[Shortcut],
    signature: QuerySignature,
    *,
    context: ShortcutResolutionContext,
) -> Shortcut | None:
    """Return one exact reviewed shortcut; ambiguity fails closed."""

    matches = [shortcut for shortcut in shortcuts if shortcut.usable_for(signature)]
    if not matches:
        return None
    pinned = [shortcut for shortcut in matches if shortcut.status == "PINNED"]
    pool = pinned or matches
    if len(pool) != 1:
        raise ShortcutContractError(
            f"ambiguous reviewed shortcuts for signature {signature.sha256}"
        )
    selected = pool[0]
    if selected.content_snapshot_sha256 != context.content_snapshot_sha256:
        raise ShortcutContractError(
            "shortcut content snapshot is stale or not installed"
        )
    missing = [
        (landing.kind, landing.id)
        for landing in selected.landings
        if (landing.kind, landing.id) not in context.visible_landings
    ]
    if missing:
        raise ShortcutContractError(
            f"shortcut landing is missing or not visible: {missing}"
        )
    if selected.evidence_receipt_sha256 not in context.evidence_receipt_sha256s:
        raise ShortcutContractError(
            "shortcut evidence receipt is not installed or visible"
        )
    return selected
