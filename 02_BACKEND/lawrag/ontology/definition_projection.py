"""Deterministic, collision-isolating DefinitionProjection compiler.

This research candidate consumes one independently validated Legal Graph
generation.  It never invents a legal class: v1 closes only the lexical
``canonical term or declared alias`` dimension and routes every other case
back to Canonical traversal.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


COMPILER = "lawrag-definition-compiler"
COMPILER_VERSION = "v2"
SCHEMA_VERSION = "definition-projection-v1"
STORE_SCHEMA = "definition-projection-store-v1"
PRECEDENCE = [
    "scope", "missing_facts", "exceptions", "exclusions", "necessary", "sufficient"
]
FALLBACK_ON = [
    "OUT_OF_SCOPE", "MISSING_FACT", "CONFLICT", "STALE_GENERATION", "NO_RULE_MATCH"
]


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


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(_canonical_bytes(dict(row)).decode("utf-8") + "\n")


def normalize_lexeme(value: object) -> str:
    """NFKC/casefold normalization used by both compiler and runtime."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def _safe_child(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    return target


@dataclass(frozen=True)
class GraphSnapshot:
    root: Path
    generation: Path
    pointer: dict[str, Any]
    manifest: dict[str, Any]

    @classmethod
    def open(cls, root: str | Path) -> "GraphSnapshot":
        base = Path(root)
        pointer = json.loads((base / "CURRENT.json").read_text("utf-8"))
        manifest_path = _safe_child(base, str(pointer.get("manifest") or ""))
        manifest = json.loads(manifest_path.read_text("utf-8"))
        generation_id = str(manifest.get("generation_id") or "")
        if generation_id != str(pointer.get("generation_id") or ""):
            raise ValueError("Legal Graph CURRENT/manifest generation mismatch")
        content = dict(manifest)
        claimed = str(content.pop("content_sha256", ""))
        if not claimed or claimed != _value_sha256(content):
            raise ValueError("Legal Graph manifest content_sha256 mismatch")
        if claimed != str(pointer.get("content_sha256") or ""):
            raise ValueError("Legal Graph CURRENT content_sha256 mismatch")
        validation = json.loads((manifest_path.parent / "validation/summary.json").read_text("utf-8"))
        if validation.get("ok") is not True or validation.get("generation_id") != generation_id:
            raise ValueError("Legal Graph independent validation receipt missing or failed")
        for metadata in (manifest.get("artifacts") or {}).values():
            if not isinstance(metadata, Mapping):
                raise ValueError("Legal Graph artifact metadata is invalid")
            artifact = _safe_child(manifest_path.parent, str(metadata.get("path") or ""))
            if _file_sha256(artifact) != metadata.get("sha256"):
                raise ValueError(f"Legal Graph artifact hash mismatch: {artifact.name}")
        return cls(base, manifest_path.parent, pointer, manifest)

    def rows(self, logical_path: str) -> list[dict[str, Any]]:
        matches = [
            metadata
            for metadata in (self.manifest.get("artifacts") or {}).values()
            if isinstance(metadata, Mapping)
            and logical_path in {metadata.get("logical_path"), metadata.get("path")}
        ]
        if len(matches) != 1:
            raise ValueError(f"Legal Graph artifact not unique: {logical_path}")
        metadata = matches[0]
        path = _safe_child(self.generation, str(metadata["path"]))
        opener = gzip.open if metadata.get("compression") == "gzip" else Path.open
        if opener is gzip.open:
            handle = gzip.open(path, "rt", encoding="utf-8")
        else:
            handle = path.open("r", encoding="utf-8")
        with handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        if len(rows) != int(metadata.get("rows") or 0):
            raise ValueError(f"Legal Graph row count mismatch: {logical_path}")
        return rows


def _logical_time(as_of: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(as_of))
    if len(digits) != 8:
        raise ValueError(f"authority_as_of is not YYYYMMDD: {as_of!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}T00:00:00Z"


def _scope_date(as_of: str) -> str:
    return _logical_time(as_of)[:10]


def _ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(row["id"]) for row in rows if row.get("id")})


def _selector(row: Mapping[str, Any]) -> Mapping[str, Any]:
    source = row.get("source") or row.get("scope") or {}
    return source.get("selector") or {}


def _same_location(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    a, b = _selector(left), _selector(right)
    return bool(
        a.get("document_id")
        and a.get("document_id") == b.get("document_id")
        and a.get("node_id") == b.get("node_id")
    )


def _record_sha256(record: Mapping[str, Any]) -> str:
    unsigned = json.loads(json.dumps(record, ensure_ascii=False))
    unsigned["derivation"]["record_sha256"] = "0" * 64
    return _value_sha256(unsigned)


def _validate_schema(schema_path: Path, record: Mapping[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:  # pragma: no cover - declared dependency in the repository
        return [f"jsonschema unavailable: {exc}"]
    schema = json.loads(schema_path.read_text("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path))
    ]


def _source_projection_lineage(
    term: Mapping[str, Any],
    semantic_cards: list[dict[str, Any]],
    rule_bundles: list[dict[str, Any]],
) -> dict[str, list[str]]:
    entity_id = str(term.get("entity_id") or "")
    term_id = str(term["id"])
    cards = [
        row for row in semantic_cards
        if row.get("entity_id") == entity_id or _same_location(row, term)
    ]
    bundles = [row for row in rule_bundles if term_id in (row.get("member_ids") or [])]
    return {
        "semantic_card_ids": _ids(cards),
        "rule_bundle_projection_ids": _ids(bundles),
    }


def _group(rows: Iterable[Mapping[str, Any]], key) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        value = key(row)
        if value not in {None, "", ("", None)}:
            grouped.setdefault(value, []).append(dict(row))
    return grouped


def _merge_rows(*groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id = {
        str(row["id"]): dict(row)
        for group in groups
        for row in group
        if row.get("id")
    }
    return [by_id[row_id] for row_id in sorted(by_id)]


def compile_definition_projections(
    *,
    graph_root: str | Path,
    output_root: str | Path,
    schema_path: str | Path,
    publish_current: bool = True,
) -> dict[str, Any]:
    """Compile and atomically publish one immutable definition generation."""
    graph = GraphSnapshot.open(graph_root)
    terms = graph.rows("canonical/term_senses.jsonl")
    rules = graph.rows("canonical/rule_assertions.jsonl")
    relations = graph.rows("canonical/relation_assertions.jsonl")
    evidence = graph.rows("canonical/evidence.jsonl")
    clause_spans = graph.rows("canonical/clause_spans.jsonl")
    instruments = graph.rows("canonical/instruments.jsonl")
    semantic_cards = graph.rows("projections/semantic_cards.jsonl")
    rule_bundles = graph.rows("projections/rule_bundle_projections.jsonl")

    evidence_by_id = {str(row["id"]): row for row in evidence}
    definition_rules_by_entity = _group(
        (
            row for row in rules
            if row.get("semantic_type") == "DEFINITION_SENSE"
            and row.get("claim_status") == "ACCEPTED"
        ),
        lambda row: str(row.get("entity_id") or ""),
    )
    spans_by_location = _group(
        clause_spans,
        lambda row: (str(row.get("document_id") or ""), row.get("node_id")),
    )
    instruments_by_document = _group(
        instruments, lambda row: str(row.get("document_id") or "")
    )
    relations_by_entity: dict[str, list[dict[str, Any]]] = {}
    relations_by_evidence: dict[str, list[dict[str, Any]]] = {}
    relations_by_location = _group(
        relations,
        lambda row: (
            str(_selector(row).get("document_id") or ""),
            _selector(row).get("node_id"),
        ),
    )
    for row in relations:
        for ref in (
            str((row.get("source") or {}).get("ref_id") or ""),
            str((row.get("target") or {}).get("ref_id") or ""),
        ):
            if ref:
                relations_by_entity.setdefault(ref, []).append(row)
        for evidence_id in row.get("evidence_ids") or []:
            relations_by_evidence.setdefault(str(evidence_id), []).append(row)
    cards_by_entity = _group(
        semantic_cards, lambda row: str(row.get("entity_id") or "")
    )
    cards_by_location = _group(
        semantic_cards,
        lambda row: (
            str(_selector(row).get("document_id") or ""),
            _selector(row).get("node_id"),
        ),
    )
    bundles_by_term: dict[str, list[dict[str, Any]]] = {}
    for row in rule_bundles:
        for member_id in row.get("member_ids") or []:
            bundles_by_term.setdefault(str(member_id), []).append(row)
    accepted = sorted(
        (row for row in terms if row.get("claim_status") == "ACCEPTED"),
        key=lambda row: str(row["id"]),
    )
    if not accepted:
        raise ValueError("no ACCEPTED term_sense rows to compile")

    surface_owners: dict[str, set[str]] = {}
    surface_values: dict[str, set[str]] = {}
    for term in accepted:
        for surface in [term.get("term"), *(term.get("aliases") or [])]:
            normalized = normalize_lexeme(surface)
            if not normalized:
                continue
            surface_owners.setdefault(normalized, set()).add(str(term["id"]))
            surface_values.setdefault(normalized, set()).add(str(surface))
    collision_rows = [
        {
            "normalized_surface": surface,
            "source_values": sorted(surface_values[surface]),
            "owner_term_sense_ids": sorted(owners),
            "reason": "MULTIPLE_TERM_SENSE_OWNERS",
            "serving_status": "WITHHELD",
        }
        for surface, owners in sorted(surface_owners.items())
        if len(owners) > 1
    ]
    ambiguous_surfaces = {row["normalized_surface"] for row in collision_rows}
    unique_surfaces_by_term: dict[str, list[str]] = {}
    excluded_terms: list[dict[str, Any]] = []
    for term in accepted:
        term_id = str(term["id"])
        all_surfaces = sorted({
            normalize_lexeme(value)
            for value in [term.get("term"), *(term.get("aliases") or [])]
            if normalize_lexeme(value)
        })
        unique = [surface for surface in all_surfaces if surface not in ambiguous_surfaces]
        if unique:
            unique_surfaces_by_term[term_id] = unique
        else:
            excluded_terms.append({
                "term_sense_id": term_id,
                "entity_id": str(term.get("entity_id") or ""),
                "term": str(term.get("term") or ""),
                "aliases": sorted(str(value) for value in (term.get("aliases") or [])),
                "ambiguous_surfaces": all_surfaces,
                "reason": "NO_GLOBALLY_UNIQUE_SURFACE",
                "serving_status": "WITHHELD",
            })
    accepted = [row for row in accepted if str(row["id"]) in unique_surfaces_by_term]
    if not accepted:
        raise ValueError("no globally unambiguous ACCEPTED term_sense rows to compile")
    normalized_owner = {
        surface: next(iter(surface_owners[surface]))
        for surface in sorted(surface_owners)
        if surface not in ambiguous_surfaces
    }

    authority_generation = str(graph.manifest.get("authority_generation") or "")
    graph_generation = str(graph.manifest.get("generation_id") or "")
    as_of = str(graph.manifest.get("authority_as_of") or "")
    compiled_at = _logical_time(as_of)
    source_set_sha256 = str(graph.manifest.get("source_aggregate_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_set_sha256):
        raise ValueError("Legal Graph source_aggregate_sha256 is missing")
    schema = Path(schema_path)
    records: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []

    for term in accepted:
        term_id = str(term["id"])
        entity_id = str(term.get("entity_id") or "")
        definition_rules = definition_rules_by_entity.get(entity_id, [])
        if not definition_rules:
            raise ValueError(f"term sense lacks an accepted DEFINITION_SENSE rule: {term_id}")
        evidence_ids = sorted({
            str(item)
            for row in [term, *definition_rules]
            for item in (row.get("evidence_ids") or [])
        })
        if not evidence_ids or any(item not in evidence_by_id for item in evidence_ids):
            raise ValueError(f"term sense evidence is unresolved: {term_id}")
        doc_id = str((_selector(term)).get("document_id") or "")
        node_id = (_selector(term)).get("node_id")
        location = (doc_id, node_id)
        matching_spans = spans_by_location.get(location, [])
        if not matching_spans:
            raise ValueError(f"term sense lacks exact ClauseSpan lineage: {term_id}")
        matching_relations = _merge_rows(
            relations_by_entity.get(entity_id, []),
            *(relations_by_evidence.get(item, []) for item in evidence_ids),
            relations_by_location.get(location, []),
        )
        matching_instruments = instruments_by_document.get(doc_id, [])
        if not matching_instruments:
            raise ValueError(f"term sense instrument version is unresolved: {term_id}")
        lineage = {
            "semantic_card_ids": _ids(_merge_rows(
                cards_by_entity.get(entity_id, []),
                cards_by_location.get(location, []),
            )),
            "rule_bundle_projection_ids": _ids(bundles_by_term.get(term_id, [])),
        }
        if not lineage["semantic_card_ids"] or not lineage["rule_bundle_projection_ids"]:
            raise ValueError(f"term sense lacks source Projection lineage: {term_id}")

        surfaces = unique_surfaces_by_term[term_id]
        basis_ids = sorted({term_id, *_ids(definition_rules)})
        canonical_inputs = {
            "term_sense_ids": [term_id],
            "semantic_clause_ids": _ids(definition_rules),
            "rule_ids": _ids(definition_rules),
            "proviso_ids": [],
            "relation_ids": _ids(matching_relations),
            "clause_span_ids": _ids(matching_spans),
            "evidence_ids": evidence_ids,
        }
        canonical_material = {
            "graph_content_sha256": graph.manifest["content_sha256"],
            "term_sense": term,
            "rules": definition_rules,
            "relations": matching_relations,
            "clause_spans": matching_spans,
            "evidence": [evidence_by_id[item] for item in evidence_ids],
            "instruments": matching_instruments,
            "source_projections": lineage,
        }
        canonical_input_sha256 = _value_sha256(canonical_material)
        counterexamples = {
            "normalization": "NFKC+casefold+alnum",
            "owned_surfaces": sorted(normalized_owner.items()),
            "collisions": [
                row for row in collision_rows
                if term_id in row["owner_term_sense_ids"]
            ],
            "open_dimensions": ["semantic-equivalence", "legal-fact-classification"],
        }
        counterexample_sha256 = _value_sha256(counterexamples)
        projection_id = f"definition:{hashlib.sha256(term_id.encode()).hexdigest()[:24]}:v1"
        receipt = {
            "schema_version": "definition-verification-receipt-v1",
            "projection_id": projection_id,
            "graph_generation": graph_generation,
            "canonical_input_sha256": canonical_input_sha256,
            "counterexample_set_sha256": counterexample_sha256,
            "checks": {
                "accepted_term_sense": True,
                "accepted_definition_rule": True,
                "canonical_ids_resolved": True,
                "evidence_nonempty": True,
                "clause_span_nonempty": True,
                "source_projection_lineage_nonempty": True,
                "normalized_aliases_unambiguous": True,
                "open_dimensions_fail_closed": True,
            },
        }
        receipt_sha256 = _value_sha256(receipt)
        primary_evidence = evidence_by_id[evidence_ids[0]]
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "projection_id": projection_id,
            "description": f"{term['term']}: {primary_evidence.get('quote_text') or term['term']}",
            "projection_kind": "concept_membership",
            "concept_id": entity_id,
            "term_sense_id": term_id,
            "status": "READY",
            "scope": {
                "source_set_sha256": source_set_sha256,
                "authority_generation": authority_generation,
                "semantic_generation": graph_generation,
                "as_of": _scope_date(as_of),
                "jurisdictions": ["kr"],
                "instrument_version_ids": _ids(matching_instruments),
                "audiences": ["public"],
            },
            "required_facts": [{
                "key": "candidate-term",
                "value_type": "string",
                "required_for_decision": True,
                "description": "Canonical 용어 또는 해당 term sense에 선언된 별칭",
            }],
            "decision_contract": {
                "necessary_conditions": [],
                "sufficient_condition_sets": [{
                    "id": f"condition-set:{projection_id.split(':')[1]}",
                    "all": [{
                        "fact": "candidate-term",
                        "operator": "in",
                        "value": surfaces,
                        "canonical_basis_ids": basis_ids,
                    }],
                }],
                "exclusions": [],
                "exceptions": [],
                "precedence": PRECEDENCE,
                "default_outcome": "UNKNOWN",
                "missing_fact_outcome": "UNKNOWN",
            },
            "canonical_inputs": canonical_inputs,
            "completeness": {
                "decision_space": "PARTIAL",
                "verification_status": "VERIFIED",
                "closed_dimensions": ["canonical-term-or-alias"],
                "open_dimensions": ["semantic-equivalence", "legal-fact-classification"],
                "counterexample_set_sha256": counterexample_sha256,
                "verification_receipt_sha256": receipt_sha256,
            },
            "fallback": {"on": FALLBACK_ON, "action": "TRAVERSE_CANONICAL"},
            "security": {"security_class": "public", "export_allowed": True},
            "derivation": {
                "compiler": COMPILER,
                "compiler_version": COMPILER_VERSION,
                "compiled_at": compiled_at,
                "canonical_input_sha256": canonical_input_sha256,
                "record_sha256": "0" * 64,
            },
        }
        record["derivation"]["record_sha256"] = _record_sha256(record)
        errors = _validate_schema(schema, record)
        if errors:
            raise ValueError(f"DefinitionProjection schema failure {projection_id}: {errors[:3]}")
        records.append(record)
        receipts.append(receipt)
        lineage_rows.append({
            "projection_id": projection_id,
            "term": term["term"],
            "aliases": term.get("aliases") or [],
            "canonical_inputs": canonical_inputs,
            "source_projections": lineage,
            "canonical_input_sha256": canonical_input_sha256,
        })

    records.sort(key=lambda row: row["projection_id"])
    receipts.sort(key=lambda row: row["projection_id"])
    lineage_rows.sort(key=lambda row: row["projection_id"])
    generation_seed = {
        "compiler": f"{COMPILER}:{COMPILER_VERSION}",
        "graph_content_sha256": graph.manifest["content_sha256"],
        "record_sha256s": [row["derivation"]["record_sha256"] for row in records],
        "collision_audit_sha256": _value_sha256(collision_rows),
        "excluded_terms_sha256": _value_sha256(excluded_terms),
    }
    generation_id = f"defv2-{_value_sha256(generation_seed)[:24]}"
    root = Path(output_root)
    final = root / "generations" / generation_id
    if final.is_dir():
        store = DefinitionProjectionStore(root)
        checked = store.verify(expected_graph_generation=graph_generation)
        if publish_current:
            store.publish(generation_id)
        return {**checked, "reused": True}

    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{generation_id}-", dir=root))
    try:
        (staging / "records").mkdir(parents=True)
        for record in records:
            _write_json(staging / "records" / f"{record['projection_id'].split(':')[1]}.json", record)
        _write_jsonl(staging / "records.jsonl", records)
        _write_jsonl(staging / "verification/receipts.jsonl", receipts)
        _write_jsonl(staging / "lineage/source_projections.jsonl", lineage_rows)
        _write_jsonl(staging / "audit/ambiguous_surfaces.jsonl", collision_rows)
        _write_jsonl(staging / "audit/excluded_terms.jsonl", excluded_terms)
        lexical_rows = [
            {
                "projection_id": row["projection_id"],
                "term_sense_id": row["term_sense_id"],
                "surfaces": row["decision_contract"]["sufficient_condition_sets"][0]["all"][0]["value"],
            }
            for row in records
        ]
        _write_json(staging / "index/lexical.json", {
            "schema_version": "definition-lexical-index-v1",
            "normalization": "NFKC+casefold+alnum",
            "records": lexical_rows,
        })
        artifact_paths = [
            path for path in staging.rglob("*") if path.is_file() and path.name != "manifest.json"
        ]
        artifacts = {
            str(path.relative_to(staging)): {
                "path": str(path.relative_to(staging)),
                "sha256": _file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(artifact_paths)
        }
        manifest = {
            "schema_version": STORE_SCHEMA,
            "generation_id": generation_id,
            "compiler": COMPILER,
            "compiler_version": COMPILER_VERSION,
            "compiled_at": compiled_at,
            "source_graph_generation": graph_generation,
            "source_graph_content_sha256": graph.manifest["content_sha256"],
            "authority_generation": authority_generation,
            "authority_as_of": as_of,
            "source_set_sha256": source_set_sha256,
            "source_term_count": len(accepted) + len(excluded_terms),
            "projection_count": len(records),
            "ready_count": sum(row["status"] == "READY" for row in records),
            "ambiguous_surface_count": len(collision_rows),
            "excluded_term_count": len(excluded_terms),
            "artifacts": artifacts,
        }
        manifest["content_sha256"] = _value_sha256(manifest)
        _write_json(staging / "manifest.json", manifest)
        validation = {
            "schema_version": "definition-projection-validation-v1",
            "generation_id": generation_id,
            "ok": True,
            "checked_records": len(records),
            "schema_valid": len(records),
            "ready": len(records),
            "ambiguous_surfaces_withheld": len(collision_rows),
            "excluded_terms_withheld": len(excluded_terms),
            "multi_owner_ready_surfaces": 0,
            "canonical_references_resolved": True,
            "artifact_hashes_verified": True,
        }
        _write_json(staging / "validation/summary.json", validation)
        # Validation is itself part of the immutable generation manifest.
        validation_path = staging / "validation/summary.json"
        manifest["artifacts"]["validation/summary.json"] = {
            "path": "validation/summary.json",
            "sha256": _file_sha256(validation_path),
            "bytes": validation_path.stat().st_size,
        }
        content = dict(manifest)
        content.pop("content_sha256", None)
        manifest["content_sha256"] = _value_sha256(content)
        _write_json(staging / "manifest.json", manifest)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    store = DefinitionProjectionStore(root)
    if publish_current:
        store.publish(generation_id)
    checked = store.verify(expected_graph_generation=graph_generation)
    return {**checked, "reused": False}


class DefinitionProjectionStore:
    """Hash-verifying reader and deterministic lexical runtime."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def publish(self, generation_id: str) -> None:
        generation = _safe_child(self.root, f"generations/{generation_id}")
        manifest = json.loads((generation / "manifest.json").read_text("utf-8"))
        pointer = {
            "schema_version": "definition-projection-current-v1",
            "generation_id": generation_id,
            "manifest": f"generations/{generation_id}/manifest.json",
            "content_sha256": manifest["content_sha256"],
        }
        _write_json(self.root / "CURRENT.json", pointer)

    def _open(self) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        pointer = json.loads((self.root / "CURRENT.json").read_text("utf-8"))
        manifest_path = _safe_child(self.root, str(pointer.get("manifest") or ""))
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if pointer.get("generation_id") != manifest.get("generation_id"):
            raise ValueError("DefinitionProjection CURRENT/manifest generation mismatch")
        content = dict(manifest)
        claimed = str(content.pop("content_sha256", ""))
        if claimed != _value_sha256(content) or claimed != pointer.get("content_sha256"):
            raise ValueError("DefinitionProjection manifest content hash mismatch")
        return pointer, manifest_path.parent, manifest

    def records(self) -> list[dict[str, Any]]:
        _, generation, manifest = self._open()
        return self._verified_jsonl(generation, manifest, "records.jsonl")

    @staticmethod
    def _verified_jsonl(
        generation: Path,
        manifest: Mapping[str, Any],
        relative: str,
    ) -> list[dict[str, Any]]:
        metadata = (manifest.get("artifacts") or {}).get(relative)
        if not isinstance(metadata, Mapping):
            raise ValueError(f"DefinitionProjection artifact missing: {relative}")
        path = _safe_child(generation, str(metadata.get("path") or relative))
        if _file_sha256(path) != metadata.get("sha256"):
            raise ValueError(f"DefinitionProjection artifact hash mismatch: {relative}")
        rows = [
            json.loads(line)
            for line in path.read_text("utf-8").splitlines()
            if line
        ]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"DefinitionProjection artifact rows must be objects: {relative}")
        return rows

    def verify(self, *, expected_graph_generation: str | None = None) -> dict[str, Any]:
        _, generation, manifest = self._open()
        if expected_graph_generation and manifest.get("source_graph_generation") != expected_graph_generation:
            raise ValueError("DefinitionProjection source graph generation mismatch")
        for relative, metadata in (manifest.get("artifacts") or {}).items():
            path = _safe_child(generation, str(metadata.get("path") or relative))
            if _file_sha256(path) != metadata.get("sha256"):
                raise ValueError(f"DefinitionProjection artifact hash mismatch: {relative}")
        rows = self.records()
        if len(rows) != manifest.get("projection_count"):
            raise ValueError("DefinitionProjection record count mismatch")
        ready_surface_owners: dict[str, set[str]] = {}
        for row in rows:
            if _record_sha256(row) != row.get("derivation", {}).get("record_sha256"):
                raise ValueError(f"DefinitionProjection record hash mismatch: {row.get('projection_id')}")
            condition = row["decision_contract"]["sufficient_condition_sets"][0]["all"][0]
            for surface in condition["value"]:
                ready_surface_owners.setdefault(str(surface), set()).add(str(row["projection_id"]))
        multi_owner = {
            surface: sorted(owners)
            for surface, owners in ready_surface_owners.items()
            if len(owners) > 1
        }
        if multi_owner:
            raise ValueError(f"ambiguous READY surfaces: {sorted(multi_owner)}")
        receipts = {
            row["projection_id"]: row
            for row in (
                json.loads(line)
                for line in (generation / "verification/receipts.jsonl").read_text("utf-8").splitlines()
                if line
            )
        }
        for row in rows:
            receipt = receipts.get(row["projection_id"])
            if receipt is None or _value_sha256(receipt) != row["completeness"].get("verification_receipt_sha256"):
                raise ValueError(f"DefinitionProjection receipt mismatch: {row['projection_id']}")
        collision_rows = [
            json.loads(line)
            for line in (generation / "audit/ambiguous_surfaces.jsonl").read_text("utf-8").splitlines()
            if line
        ]
        excluded_terms = [
            json.loads(line)
            for line in (generation / "audit/excluded_terms.jsonl").read_text("utf-8").splitlines()
            if line
        ]
        if len(collision_rows) != int(manifest.get("ambiguous_surface_count") or 0):
            raise ValueError("DefinitionProjection ambiguous surface audit count mismatch")
        if len(excluded_terms) != int(manifest.get("excluded_term_count") or 0):
            raise ValueError("DefinitionProjection excluded term audit count mismatch")
        ambiguous = {str(row["normalized_surface"]) for row in collision_rows}
        leaked = sorted(ambiguous.intersection(ready_surface_owners))
        if leaked:
            raise ValueError(f"withheld ambiguous surfaces leaked into READY records: {leaked}")
        return {
            "generation_id": manifest["generation_id"],
            "content_sha256": manifest["content_sha256"],
            "source_graph_generation": manifest["source_graph_generation"],
            "total": len(rows),
            "valid": len(rows),
            "invalid": 0,
            "ready": sum(row.get("status") == "READY" for row in rows),
            "ambiguous_surfaces_withheld": len(collision_rows),
            "excluded_terms_withheld": len(excluded_terms),
            "multi_owner_ready_surfaces": 0,
            "runtime_wired": False,
        }

    def lookup(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        normalized_query = normalize_lexeme(query)
        _, generation, manifest = self._open()
        records = self._verified_jsonl(generation, manifest, "records.jsonl")
        collision_rows = self._verified_jsonl(
            generation,
            manifest,
            "audit/ambiguous_surfaces.jsonl",
        )
        matches: list[tuple[int, str, str]] = []
        for row in records:
            condition = row["decision_contract"]["sufficient_condition_sets"][0]["all"][0]
            for surface in condition["value"]:
                if surface and surface in normalized_query:
                    matches.append((len(surface), row["projection_id"], surface))
        matches.sort(key=lambda item: (-item[0], item[1], item[2]))
        ambiguous_matches = sorted(
            {
                str(row.get("normalized_surface") or "")
                for row in collision_rows
                if row.get("normalized_surface")
                and str(row["normalized_surface"]) in normalized_query
            },
            key=lambda value: (-len(value), value),
        )
        longest_ready = matches[0][0] if matches else -1
        if ambiguous_matches and len(ambiguous_matches[0]) >= longest_ready:
            return {
                "query": query,
                "normalized_query": normalized_query,
                "candidates": [],
                "fallback": "TRAVERSE_CANONICAL",
                "reason": "AMBIGUOUS_SURFACE",
                "ambiguous_surfaces": [
                    value
                    for value in ambiguous_matches
                    if len(value) == len(ambiguous_matches[0])
                ],
            }
        seen: set[str] = set()
        selected = []
        for length, projection_id, surface in matches:
            if projection_id in seen:
                continue
            seen.add(projection_id)
            selected.append({
                "projection_id": projection_id,
                "matched_surface": surface,
                "normalized_length": length,
            })
            if len(selected) >= max(0, limit):
                break
        return {
            "query": query,
            "normalized_query": normalized_query,
            "candidates": selected,
            "fallback": None if selected else "TRAVERSE_CANONICAL",
            "reason": None if selected else "NO_RULE_MATCH",
        }

    def evaluate(
        self,
        projection_id: str,
        facts: Mapping[str, Any],
        *,
        graph_generation: str,
        as_of: str | None = None,
        jurisdiction: str = "kr",
    ) -> dict[str, Any]:
        _, _, manifest = self._open()
        fallback = "TRAVERSE_CANONICAL"
        if graph_generation != manifest.get("source_graph_generation"):
            return {"outcome": "UNKNOWN", "reason": "STALE_GENERATION", "fallback": fallback}
        record = next((row for row in self.records() if row["projection_id"] == projection_id), None)
        if record is None:
            return {"outcome": "UNKNOWN", "reason": "NO_RULE_MATCH", "fallback": fallback}
        scope = record["scope"]
        if jurisdiction not in scope["jurisdictions"] or (as_of and as_of != scope["as_of"]):
            return {"outcome": "UNKNOWN", "reason": "OUT_OF_SCOPE", "fallback": fallback}
        if "candidate-term" not in facts or facts.get("candidate-term") is None:
            return {"outcome": "UNKNOWN", "reason": "MISSING_FACT", "fallback": fallback}
        candidate = normalize_lexeme(facts["candidate-term"])
        allowed = record["decision_contract"]["sufficient_condition_sets"][0]["all"][0]["value"]
        if candidate in allowed:
            return {
                "outcome": "MATCH",
                "reason": "SUFFICIENT_CONDITION",
                "fallback": None,
                "canonical_inputs": record["canonical_inputs"],
            }
        return {"outcome": "UNKNOWN", "reason": "NO_RULE_MATCH", "fallback": fallback}


def default_schema_path() -> Path:
    explicit = os.environ.get("DEFINITION_PROJECTION_SCHEMA")
    if explicit:
        return Path(explicit)
    from lawrag.platform.paths import repository_root

    return repository_root() / "00_SYSTEM/SCHEMAS/definition-projection-v1.schema.json"
