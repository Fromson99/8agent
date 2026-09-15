"""Verified, additive DefinitionProjection adapter for LegalClosure.

This candidate never replaces source retrieval and never emits a legal conclusion.
It opens one immutable DefinitionProjection/Legal Graph pair, resolves a matched
projection's ClauseSpan coordinates, and appends those source sections to the
LegalClosure floor.  Every verification or quality failure returns the exact floor.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping

from lawrag.core.rag import answer
from lawrag.platform.paths import data_path
from lawrag.runtime.components import legalclosure_v2


PROFILE_ID = "ontology-rag-v1"
BLOCKING_SEVERITIES = {"ERROR", "CRITICAL"}
BLOCKING_STATES = {"OPEN", "CONFIRMED"}
_KNOWLEDGE_CACHE_LOCK = RLock()
_KNOWLEDGE_CACHE: dict[
    tuple[str, str, str, str],
    tuple[
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        set[str],
        dict[str, Any],
    ],
] = {}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _value_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    if not relative:
        raise ValueError("empty artifact path")
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"artifact is not a regular file: {relative}")
    return target


def _normal(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in text if character.isalnum())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _artifact_path(
    generation: Path,
    manifest: Mapping[str, Any],
    logical_path: str,
) -> tuple[Path, Mapping[str, Any]]:
    matches = [
        item
        for key, item in (manifest.get("artifacts") or {}).items()
        if isinstance(item, Mapping)
        and logical_path in {
            str(key), str(item.get("logical_path") or ""), str(item.get("path") or "")
        }
    ]
    if len(matches) != 1:
        raise ValueError(f"artifact is not unique: {logical_path}")
    metadata = matches[0]
    return _safe_child(generation, str(metadata.get("path") or "")), metadata


def _rows(
    generation: Path,
    manifest: Mapping[str, Any],
    logical_path: str,
) -> list[dict[str, Any]]:
    path, metadata = _artifact_path(generation, manifest, logical_path)
    if metadata.get("compression") == "gzip" or path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    else:
        rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    expected = metadata.get("rows")
    if expected is not None and len(rows) != int(expected):
        raise ValueError(f"artifact row count mismatch: {logical_path}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"artifact rows must be objects: {logical_path}")
    return rows


def _open_release(root: Path, label: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    pointer = _read_json(_safe_child(root, "CURRENT.json"))
    manifest_path = _safe_child(root, str(pointer.get("manifest") or ""))
    manifest = _read_json(manifest_path)
    if pointer.get("generation_id") != manifest.get("generation_id"):
        raise ValueError(f"{label} CURRENT/manifest generation mismatch")
    unsigned = dict(manifest)
    claimed = str(unsigned.pop("content_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", claimed):
        raise ValueError(f"{label} content hash missing")
    if claimed != _value_sha256(unsigned) or claimed != pointer.get("content_sha256"):
        raise ValueError(f"{label} content hash mismatch")
    generation = manifest_path.parent
    for key, metadata in (manifest.get("artifacts") or {}).items():
        if not isinstance(metadata, Mapping):
            raise ValueError(f"{label} artifact metadata invalid: {key}")
        artifact = _safe_child(generation, str(metadata.get("path") or key))
        if _file_sha256(artifact) != metadata.get("sha256"):
            raise ValueError(f"{label} artifact hash mismatch: {key}")
    validation = _read_json(_safe_child(generation, "validation/summary.json"))
    if validation.get("ok") is not True:
        raise ValueError(f"{label} validation receipt failed")
    if validation.get("generation_id") != manifest.get("generation_id"):
        raise ValueError(f"{label} validation generation mismatch")
    return generation, manifest, pointer


def _record_sha256(record: Mapping[str, Any]) -> str:
    unsigned = deepcopy(dict(record))
    unsigned.setdefault("derivation", {})["record_sha256"] = "0" * 64
    return _value_sha256(unsigned)


def _open_knowledge(
    definition_root: Path,
    graph_root: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    set[str],
    dict[str, Any],
]:
    graph_generation, graph_manifest, _ = _open_release(graph_root, "Legal Graph")
    definition_generation, definition_manifest, _ = _open_release(
        definition_root, "DefinitionProjection"
    )
    graph_id = str(graph_manifest.get("generation_id") or "")
    if definition_manifest.get("source_graph_generation") != graph_id:
        raise ValueError("DefinitionProjection source graph generation mismatch")
    records = _rows(definition_generation, definition_manifest, "records.jsonl")
    if len(records) != int(definition_manifest.get("projection_count") or -1):
        raise ValueError("DefinitionProjection record count mismatch")
    for record in records:
        claimed = record.get("derivation", {}).get("record_sha256")
        if claimed != _record_sha256(record):
            raise ValueError(
                f"DefinitionProjection record hash mismatch: {record.get('projection_id')}"
            )
    receipts = {
        str(row.get("projection_id") or ""): row
        for row in _rows(
            definition_generation,
            definition_manifest,
            "verification/receipts.jsonl",
        )
    }
    for record in records:
        projection_id = str(record.get("projection_id") or "")
        receipt = receipts.get(projection_id)
        expected = record.get("completeness", {}).get("verification_receipt_sha256")
        if receipt is None or _value_sha256(receipt) != expected:
            raise ValueError(f"DefinitionProjection receipt mismatch: {projection_id}")
    spans = {
        str(row.get("id") or ""): row
        for row in _rows(graph_generation, graph_manifest, "canonical/clause_spans.jsonl")
    }
    ambiguous_surfaces = {
        str(row.get("normalized_surface") or "")
        for row in _rows(
            definition_generation,
            definition_manifest,
            "audit/ambiguous_surfaces.jsonl",
        )
        if row.get("normalized_surface")
    }
    trace = {
        "definition_generation": definition_manifest["generation_id"],
        "definition_content_sha256": definition_manifest["content_sha256"],
        "graph_generation": graph_id,
        "graph_content_sha256": graph_manifest["content_sha256"],
    }
    return records, spans, ambiguous_surfaces, trace


def _knowledge_cache_key(
    definition_root: Path,
    graph_root: Path,
) -> tuple[str, str, str, str]:
    """Bind cached knowledge to exact roots and exact CURRENT pointer bytes."""
    definitions = definition_root.resolve()
    graph = graph_root.resolve()
    return (
        str(definitions),
        _file_sha256(_safe_child(definitions, "CURRENT.json")),
        str(graph),
        _file_sha256(_safe_child(graph, "CURRENT.json")),
    )


def _clear_knowledge_cache() -> None:
    """Clear process-local verified knowledge; used by tests and reload hooks."""
    with _KNOWLEDGE_CACHE_LOCK:
        _KNOWLEDGE_CACHE.clear()


def _cached_knowledge(
    definition_root: Path,
    graph_root: Path,
) -> tuple[
    tuple[
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        set[str],
        dict[str, Any],
    ],
    bool,
    str,
]:
    with _KNOWLEDGE_CACHE_LOCK:
        key = _knowledge_cache_key(definition_root, graph_root)
        cached = _KNOWLEDGE_CACHE.get(key)
        if cached is not None:
            return cached, True, _value_sha256(list(key))
        opened = _open_knowledge(definition_root, graph_root)
        if _knowledge_cache_key(definition_root, graph_root) != key:
            raise ValueError("ontology CURRENT pointer changed during verified open")
        # One active pair is sufficient. Pointer rollback recreates the same key
        # and is reverified after any intervening generation evicts this entry.
        _KNOWLEDGE_CACHE.clear()
        _KNOWLEDGE_CACHE[key] = opened
        return opened, False, _value_sha256(list(key))


def _resolve_store_paths(
    definition_root: str | Path | None,
    legal_graph_root: str | Path | None,
) -> tuple[Path, Path, str]:
    sources: list[str] = []
    if definition_root:
        definitions = Path(definition_root)
        sources.append("argument")
    elif os.environ.get("RAG_DEFINITION_PROJECTION_STORE"):
        definitions = Path(os.environ["RAG_DEFINITION_PROJECTION_STORE"])
        sources.append("environment")
    else:
        definitions = data_path("PROJECTIONS", "DEFINITIONS")
        sources.append("workspace-default")
    if legal_graph_root:
        graph = Path(legal_graph_root)
        sources.append("argument")
    elif os.environ.get("RAG_LEGAL_GRAPH_STORE"):
        graph = Path(os.environ["RAG_LEGAL_GRAPH_STORE"])
        sources.append("environment")
    else:
        graph = data_path("legal_graph")
        sources.append("workspace-default")
    binding = sources[0] if len(set(sources)) == 1 else "mixed:" + "+".join(sources)
    return definitions, graph, binding


def _surfaces(record: Mapping[str, Any]) -> list[str]:
    values: set[str] = set()
    for condition_set in record.get("decision_contract", {}).get(
        "sufficient_condition_sets", []
    ):
        for condition in condition_set.get("all", []):
            raw = condition.get("value", [])
            if isinstance(raw, str):
                raw = [raw]
            values.update(_normal(item) for item in raw if _normal(item))
    return sorted(values, key=lambda value: (-len(value), value))


def _lookup(
    records: Iterable[Mapping[str, Any]],
    question: str,
    ambiguous_surfaces: Iterable[str],
) -> tuple[dict[str, Any] | None, str, str, str]:
    query = _normal(question)
    matches: list[tuple[int, str, str, Mapping[str, Any]]] = []
    for record in records:
        for surface in _surfaces(record):
            if surface in query:
                matches.append((len(surface), str(record.get("projection_id")), surface, record))
    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
    ambiguous_matches = sorted(
        {
            surface
            for raw in ambiguous_surfaces
            if (surface := _normal(raw)) and surface in query
        },
        key=lambda value: (-len(value), value),
    )
    longest_ready = matches[0][0] if matches else -1
    if ambiguous_matches and len(ambiguous_matches[0]) >= longest_ready:
        longest = len(ambiguous_matches[0])
        detail = ",".join(
            value for value in ambiguous_matches if len(value) == longest
        )
        return None, "", "AMBIGUOUS_SURFACE", detail
    if not matches:
        return None, "", "NO_RULE_MATCH", ""
    return deepcopy(dict(matches[0][3])), matches[0][2], "", ""


def _quality_rows(path: Path | None) -> tuple[list[dict[str, Any]], str]:
    if path is None:
        return [], "not-configured"
    if not path.is_file() or path.is_symlink():
        raise ValueError("configured quality observation ledger is missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("issues") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("quality observation ledger must contain an issues list")
    return rows, "verified"


def _eligibility_errors(
    record: Mapping[str, Any],
    graph_generation: str,
    quality: Iterable[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if record.get("status") != "READY":
        errors.append("NOT_READY")
    if record.get("completeness", {}).get("verification_status") != "VERIFIED":
        errors.append("UNVERIFIED_COMPLETENESS")
    inputs = record.get("canonical_inputs", {})
    if not inputs.get("clause_span_ids") or not inputs.get("evidence_ids"):
        errors.append("MISSING_CANONICAL_EVIDENCE")
    if record.get("scope", {}).get("semantic_generation") != graph_generation:
        errors.append("STALE_GENERATION")
    projection_id = record.get("projection_id")
    document_ids = set(record.get("scope", {}).get("instrument_version_ids") or [])
    for issue in quality:
        target = issue.get("target") or {}
        applies = target.get("record_id") == projection_id
        applies = applies or target.get("document_id") in document_ids
        if (
            applies
            and issue.get("state") in BLOCKING_STATES
            and issue.get("severity") in BLOCKING_SEVERITIES
        ):
            errors.append("BLOCKING_QUALITY_ISSUE")
    return sorted(set(errors))


def _fallback(
    sections: list[Any],
    meta: Mapping[str, Any],
    *,
    reason: str,
    detail: str = "",
    trace: Mapping[str, Any] | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    result = deepcopy(dict(meta))
    result.setdefault("runtime", {})["effective_profile"] = PROFILE_ID
    result["ontology_rag"] = {
        "schema_version": "ontology-rag-runtime-trace-v1",
        "profile_id": PROFILE_ID,
        "status": "fallback",
        "reason": reason,
        "detail": detail[:500],
        "fallback": "TRAVERSE_CANONICAL",
        "baseline_count": len(sections),
        "final_count": len(sections),
        "added_count": 0,
        "added_coordinates": [],
        "baseline_floor_preserved": True,
        "direct_conclusion_allowed": False,
    }
    if trace:
        result["ontology_rag"].update(deepcopy(dict(trace)))
    return sections, result


def retrieve(
    index,
    question: str,
    *,
    definition_root: str | Path | None = None,
    legal_graph_root: str | Path | None = None,
    quality_path: str | Path | None = None,
    definition_cap: int = 8,
    baseline_result=None,
    **kwargs,
):
    """Return LegalClosure sections plus verified DefinitionProjection evidence."""
    if baseline_result is None:
        floor, baseline_meta = legalclosure_v2.retrieve(index, question, **kwargs)
    else:
        try:
            floor_value, meta_value = baseline_result
            floor = deepcopy(list(floor_value))
            baseline_meta = deepcopy(dict(meta_value))
        except (TypeError, ValueError) as exc:
            raise ValueError("baseline_result must be a (sections, metadata) pair") from exc
    floor_coordinates = [(section.doc_id, section.node) for section in floor]
    quality_value = quality_path or os.environ.get("RAG_KNOWLEDGE_QUALITY_STORE")
    try:
        definitions, graph, store_binding = _resolve_store_paths(
            definition_root,
            legal_graph_root,
        )
    except Exception as exc:
        return _fallback(
            floor,
            baseline_meta,
            reason="STORE_NOT_CONFIGURED",
            detail=f"{type(exc).__name__}: {exc}",
        )
    try:
        (
            (records, spans, ambiguous_surfaces, generation_trace),
            cache_hit,
            cache_key_sha256,
        ) = _cached_knowledge(
            definitions,
            graph,
        )
        operational_trace = {
            **generation_trace,
            "store_binding": store_binding,
            "knowledge_cache": "hit" if cache_hit else "miss",
            "knowledge_cache_key_sha256": cache_key_sha256,
        }
        record, matched_surface, lookup_reason, lookup_detail = _lookup(
            records,
            question,
            ambiguous_surfaces,
        )
        if record is None:
            return _fallback(
                floor,
                baseline_meta,
                reason=lookup_reason,
                detail=lookup_detail,
                trace=operational_trace,
            )
        quality, quality_status = _quality_rows(Path(quality_value) if quality_value else None)
        errors = _eligibility_errors(record, generation_trace["graph_generation"], quality)
        if errors:
            return _fallback(
                floor,
                baseline_meta,
                reason=errors[0],
                detail=",".join(errors),
                trace=operational_trace,
            )
        clause_span_ids = list(record["canonical_inputs"]["clause_span_ids"])
        coordinates: list[dict[str, Any]] = []
        for clause_span_id in clause_span_ids:
            span = spans.get(str(clause_span_id))
            if not span:
                raise ValueError(f"unresolved ClauseSpan: {clause_span_id}")
            doc_id, node_id = span.get("document_id"), span.get("node_id")
            if not isinstance(doc_id, str) or not isinstance(node_id, int):
                raise ValueError(f"invalid ClauseSpan selector: {clause_span_id}")
            coordinates.append(
                {
                    "doc_id": doc_id,
                    "node": node_id,
                    "via": PROFILE_ID,
                    "why": str(record.get("projection_id") or ""),
                }
            )
        requested = {(item["doc_id"], item["node"]) for item in coordinates}
        resolved = answer.sections_from_coords(index, coordinates)
        resolved = [
            section for section in resolved
            if (section.doc_id, section.node) in requested
        ]
        if requested - {(section.doc_id, section.node) for section in resolved}:
            raise ValueError("one or more ClauseSpan coordinates do not resolve in Index")
        known = set(floor_coordinates)
        added = []
        for section in resolved:
            coordinate = (section.doc_id, section.node)
            if coordinate in known:
                continue
            known.add(coordinate)
            added.append(section)
            if len(added) >= max(0, int(definition_cap)):
                break
        sections = [*floor, *added]
        for number, section in enumerate(sections, 1):
            section.n = number
        final_coordinates = [(section.doc_id, section.node) for section in sections]
        if final_coordinates[: len(floor_coordinates)] != floor_coordinates:
            raise ValueError("baseline floor changed during additive expansion")
        meta = deepcopy(dict(baseline_meta))
        meta.setdefault("runtime", {})["effective_profile"] = PROFILE_ID
        meta["ontology_rag"] = {
            "schema_version": "ontology-rag-runtime-trace-v1",
            "profile_id": PROFILE_ID,
            "status": "used",
            "reason": "VERIFIED_DEFINITION_MATCH",
            "fallback": None,
            "projection_id": record["projection_id"],
            "matched_surface": matched_surface,
            "clause_span_ids": clause_span_ids,
            "canonical_evidence_ids": list(record["canonical_inputs"]["evidence_ids"]),
            "rule_ids": list(record["canonical_inputs"].get("rule_ids") or []),
            "baseline_count": len(floor),
            "final_count": len(sections),
            "added_count": len(added),
            "added_coordinates": [
                {"doc_id": section.doc_id, "node": section.node} for section in added
            ],
            "baseline_floor_preserved": True,
            "direct_conclusion_allowed": False,
            "quality_status": quality_status,
            **operational_trace,
        }
        if added:
            meta["strategy"] = f"{meta.get('strategy') or 'legalclosure'}+{PROFILE_ID}"
            selected = meta.setdefault("selected", [])
            selected_coordinates = {
                (item.get("doc_id"), item.get("node")) for item in selected
            }
            for section in added:
                coordinate = (section.doc_id, section.node)
                if coordinate not in selected_coordinates:
                    selected.append(
                        {
                            "doc_id": section.doc_id,
                            "node": section.node,
                            "doc": section.doc,
                            "path": section.path,
                            "origin": PROFILE_ID,
                            "projection_id": record["projection_id"],
                        }
                    )
        return sections, meta
    except Exception as exc:
        return _fallback(
            floor,
            baseline_meta,
            reason="VERIFICATION_FAILED",
            detail=f"{type(exc).__name__}: {exc}",
        )
