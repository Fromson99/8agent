"""Independent, streaming validation for an immutable ``legal-graph-v1`` generation.

The compiler deliberately is not imported here.  Publication may call
``validate_generation`` on a staging directory and replace ``CURRENT.json`` only
when the returned report is successful.
"""

from __future__ import annotations

import hashlib
import gzip
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .ids import canonical_json_text
from .model import (
    ClaimStatus,
    ClosureMode,
    COMPILER_CONTRACT_VERSION,
    Endpoint,
    Precision,
    RowType,
    SCHEMA_VERSION,
    SchemaValidationError,
    validate_manifest,
    validate_row,
)


_REQUIRED_ARTIFACTS_V1 = frozenset({
    "canonical/structural_units.jsonl",
    "canonical/evidence.jsonl",
    "canonical/relation_assertions.jsonl",
    "observations/relation_inputs.jsonl",
    "observations/unresolved_relations.jsonl",
    "projections/provision_cards.jsonl",
    "projections/relation_compatibility.jsonl",
    "projections/legacy_section_relations.jsonl",
    "projections/closure_projections.jsonl",
    "source_accounting.json",
})
_REQUIRED_ARTIFACTS_V2 = frozenset({
    "canonical/structural_units.jsonl",
    "canonical/evidence.jsonl",
    "canonical/legal_entities.jsonl",
    "canonical/term_senses.jsonl",
    "canonical/rule_assertions.jsonl",
    "canonical/requirements.jsonl",
    "canonical/assessments.jsonl",
    "canonical/relation_assertions.jsonl",
    "observations/relation_inputs.jsonl",
    "observations/unresolved_relations.jsonl",
    "projections/provision_cards.jsonl",
    "projections/relation_compatibility.jsonl",
    "projections/legacy_section_relations.jsonl",
    "projections/closure_projections.jsonl",
    "projections/semantic_cards.jsonl",
    "projections/rule_bundle_projections.jsonl",
    "source_accounting.json",
})
_TERMINAL_DISPOSITIONS = (
    "mapped",
    "support_only",
    "unresolved",
    "suppressed",
    "out_of_contract",
    "parse_error",
)
_REQUIRED_MODES = frozenset({ClosureMode.REQUIRED_WHEN_ACTIVATED.value})
_ARTICLE_SURFACE = re.compile(r"^제\s*\d+(?:-\d+)?조(?:의\s*\d+)?$")


@dataclass(frozen=True, order=True)
class ValidationIssue:
    """One deterministic validation finding."""

    code: str
    path: str
    row: int = 0
    record_id: str = ""
    message: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.row:
            result["row"] = self.row
        if self.record_id:
            result["record_id"] = self.record_id
        return result


@dataclass(frozen=True)
class ValidationReport:
    """Stable return value used by the publisher and the command-line wrapper."""

    ok: bool
    generation_id: str
    checked_artifacts: int
    checked_rows: int
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "legal-graph-validation-v1",
            "ok": self.ok,
            "generation_id": self.generation_id,
            "checked_artifacts": self.checked_artifacts,
            "checked_rows": self.checked_rows,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }

    def raise_for_errors(self) -> "ValidationReport":
        if not self.ok:
            first = self.errors[0] if self.errors else None
            detail = f"{first.code}: {first.message}" if first else "unknown validation error"
            counts = ", ".join(
                f"{code}={count}" for code, count in sorted(
                    Counter(issue.code for issue in self.errors).items())
            )
            raise ValueError(
                f"legal graph generation is invalid ({len(self.errors)} errors: {counts}): {detail}"
            )
        return self


class _State:
    def __init__(self, root: Path, manifest: Mapping[str, Any], structure_store: Path | None):
        self.root = root
        self.manifest = manifest
        self.generation_id = str(manifest.get("generation_id") or "")
        self.authority_generation = str(manifest.get("authority_generation") or "")
        self.structure_store = structure_store
        self.source_blocks: dict[str, dict[str, str] | None] = {}
        self.rows_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_id: dict[str, tuple[str, int, dict[str, Any]]] = {}
        self.by_type: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.errors: list[ValidationIssue] = []
        self.warnings: list[ValidationIssue] = []
        self.checked_artifacts = 0
        self.checked_rows = 0

    def issue(
        self,
        code: str,
        message: str,
        *,
        path: str = "manifest.json",
        row: int = 0,
        record_id: str = "",
        warning: bool = False,
    ) -> None:
        issue = ValidationIssue(
            code=code,
            path=path,
            row=row,
            record_id=record_id,
            message=message,
            severity="warning" if warning else "error",
        )
        (self.warnings if warning else self.errors).append(issue)


def _inside(root: Path, relative: str) -> Path | None:
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _json_rows(path: Path, artifact_format: str,
               compression: str = "none") -> Iterable[tuple[int, Any]]:
    if artifact_format == "jsonl":
        handle_context = (gzip.open(path, "rt", encoding="utf-8")
                          if compression == "gzip"
                          else path.open("r", encoding="utf-8"))
        with handle_context as handle:
            row_number = 0
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row_number += 1
                try:
                    yield row_number, json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"line {line_number}: {exc.msg}") from exc
        return
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"line {exc.lineno}: {exc.msg}") from exc
    if isinstance(value, list):
        for number, row in enumerate(value, 1):
            yield number, row
    else:
        yield 1, value


def _artifact_format(relative: str, metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("format") or ("jsonl" if relative.endswith(".jsonl") else "json"))


def _logical_path(relative: str, metadata: Mapping[str, Any]) -> str:
    logical = str(metadata.get("logical_path") or "")
    if logical:
        return logical
    return relative[:-3] if relative.endswith(".gz") else relative


def _load_artifacts(state: _State) -> None:
    artifacts = state.manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        artifacts = state.manifest.get("files")
    if not isinstance(artifacts, Mapping):
        return
    logical_artifacts = {
        _logical_path(relative, metadata)
        for relative, metadata in artifacts.items()
        if isinstance(relative, str) and isinstance(metadata, Mapping)
    }
    required = (
        _REQUIRED_ARTIFACTS_V1
        if state.manifest.get("compiler_contract") == "legal-graph-compiler-v1"
        else _REQUIRED_ARTIFACTS_V2
    )
    missing_contract = sorted(required - logical_artifacts)
    for relative in missing_contract:
        state.issue("artifact.missing_contract", f"required artifact is absent: {relative}")

    for relative, raw_metadata in sorted(artifacts.items()):
        if not isinstance(relative, str) or not isinstance(raw_metadata, Mapping):
            continue  # validate_manifest reports the shape error.
        logical_relative = _logical_path(relative, raw_metadata)
        path = _inside(state.root, relative)
        if path is None:
            state.issue("artifact.unsafe_path", f"unsafe artifact path: {relative!r}")
            continue
        if not path.is_file():
            state.issue("artifact.missing", "manifest artifact does not exist", path=relative)
            continue
        state.checked_artifacts += 1
        actual_hash, actual_bytes = _digest(path)
        if actual_hash != raw_metadata.get("sha256"):
            state.issue(
                "artifact.hash_mismatch",
                f"expected {raw_metadata.get('sha256')}, got {actual_hash}",
                path=relative,
            )
        if actual_bytes != raw_metadata.get("bytes"):
            state.issue(
                "artifact.bytes_mismatch",
                f"expected {raw_metadata.get('bytes')}, got {actual_bytes}",
                path=relative,
            )
        artifact_format = _artifact_format(relative, raw_metadata)
        compression = str(raw_metadata.get("compression") or "none")
        if compression not in {"none", "gzip"}:
            state.issue("artifact.compression", f"unsupported compression: {compression}", path=relative)
            continue
        actual_rows = 0
        try:
            for row_number, raw_row in _json_rows(path, artifact_format, compression):
                actual_rows += 1
                state.checked_rows += 1
                if artifact_format == "json":
                    if isinstance(raw_row, dict):
                        state.rows_by_path[logical_relative].append(raw_row)
                    else:
                        state.issue("row.not_object", "JSON root must be an object", path=relative)
                    continue
                if not isinstance(raw_row, dict):
                    state.issue("row.not_object", "row must be a JSON object", path=relative, row=row_number)
                    continue
                row = raw_row
                record_id = str(row.get("id") or "")
                state.rows_by_path[logical_relative].append(row)
                try:
                    validate_row(row)
                except (SchemaValidationError, ValueError, TypeError) as exc:
                    state.issue(
                        "row.schema",
                        str(exc),
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
                row_generation = row.get("generation_id")
                if row_generation != state.generation_id:
                    state.issue(
                        "generation.row_mismatch",
                        f"row generation {row_generation!r} != manifest generation {state.generation_id!r}",
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
                authority = row.get("authority_generation")
                if authority != state.authority_generation:
                    state.issue(
                        "generation.authority_mismatch",
                        f"row authority generation {authority!r} != manifest authority generation",
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
                if record_id:
                    previous = state.by_id.get(record_id)
                    if previous is not None:
                        state.issue(
                            "id.duplicate",
                            f"already used at {previous[0]} row {previous[1]}",
                            path=relative,
                            row=row_number,
                            record_id=record_id,
                        )
                    else:
                        state.by_id[record_id] = (relative, row_number, row)
                    state.by_type[str(row.get("row_type") or "")][record_id] = row
                if row.get("runtime_wired") is not None and row.get("runtime_wired") is not False:
                    state.issue(
                        "runtime.wired",
                        "published row runtime_wired must be false",
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
                if row.get("layer") == "runtime":
                    state.issue(
                        "runtime.materialized",
                        "immutable sidecar cannot contain runtime-layer rows",
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
                if _is_candidate(row) and _is_required(row):
                    state.issue(
                        "candidate.required",
                        "candidate/rejected/unresolved observations can never be required",
                        path=relative,
                        row=row_number,
                        record_id=record_id,
                    )
        except (OSError, UnicodeError, ValueError) as exc:
            state.issue("artifact.parse", str(exc), path=relative)
        if actual_rows != raw_metadata.get("rows"):
            state.issue(
                "artifact.rows_mismatch",
                f"expected {raw_metadata.get('rows')}, got {actual_rows}",
                path=relative,
            )


def _is_candidate(row: Mapping[str, Any]) -> bool:
    status = str(row.get("claim_status") or row.get("status") or "").upper()
    return status in {
        ClaimStatus.CANDIDATE.value,
        ClaimStatus.REJECTED.value,
        ClaimStatus.UNRESOLVED.value,
    }


def _is_required(row: Mapping[str, Any]) -> bool:
    return row.get("required") is True or row.get("mandatory") is True


def _selector_key(selector: Mapping[str, Any]) -> tuple[str, str]:
    return str(selector.get("document_id") or ""), str(selector.get("node_id") or "")


def _iter_endpoints(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if "kind" in value and "precision" in value:
            yield value
            return
        for item in value.values():
            yield from _iter_endpoints(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_endpoints(item)


def _validate_structure_and_endpoints(state: _State) -> tuple[set[str], set[str]]:
    structural = state.by_type.get(RowType.STRUCTURAL_UNIT.value, {})
    unit_by_selector: dict[tuple[str, str], str] = {}
    article_roots: set[str] = set()
    current_articles: set[str] = set()
    for unit_id, row in structural.items():
        path, number, _ = state.by_id[unit_id]
        key = (str(row.get("document_id") or ""), str(row.get("node_id") or ""))
        if key in unit_by_selector:
            state.issue("structure.selector_duplicate", f"same document/node as {unit_by_selector[key]}", path=path, row=number, record_id=unit_id)
        else:
            unit_by_selector[key] = unit_id
        parent_id = row.get("parent_id")
        if parent_id is not None and parent_id not in structural:
            state.issue("structure.parent_dangling", f"unknown parent_id {parent_id!r}", path=path, row=number, record_id=unit_id)
        article_root_id = row.get("article_root_id")
        normalized_kind = str(row.get("unit_kind") or "").strip().casefold()
        is_article = (
            normalized_kind in {"article", "조", "article_root"}
            or bool(_ARTICLE_SURFACE.fullmatch(str(row.get("surface") or "").strip()))
        )
        if is_article:
            article_roots.add(unit_id)
            if row.get("current") is True:
                current_articles.add(unit_id)
        if article_root_id is not None and article_root_id not in structural:
            state.issue("structure.article_root_dangling", f"unknown article_root_id {article_root_id!r}", path=path, row=number, record_id=unit_id)
        selector = row.get("selector")
        if isinstance(selector, Mapping) and _selector_key(selector) != key:
            state.issue("structure.selector_mismatch", "selector does not equal structural document/node", path=path, row=number, record_id=unit_id)

    exact_span_seen = False
    for record_id, (path, number, row) in state.by_id.items():
        for endpoint in _iter_endpoints(row):
            try:
                parsed = Endpoint.from_dict(endpoint)
            except SchemaValidationError:
                continue  # local schema issue already reported.
            if parsed.precision == Precision.UNRESOLVED:
                if str(row.get("row_type")) in {RowType.RELATION_ASSERTION.value, RowType.RULE_ASSERTION.value}:
                    state.issue("endpoint.canonical_unresolved", "canonical assertion endpoint is unresolved", path=path, row=number, record_id=record_id)
                continue
            ref_id = parsed.ref_id or ""
            if ref_id not in state.by_id:
                state.issue("endpoint.dangling", f"unknown endpoint ref_id {ref_id!r}", path=path, row=number, record_id=record_id)
            selector = parsed.selector.to_dict() if parsed.selector is not None else None
            if parsed.precision == Precision.EXACT_SPAN and selector is not None:
                exact_span_seen = True
                _validate_source_span(state, selector, path, number, record_id)
            if selector is not None and selector.get("node_id") is not None:
                key = _selector_key(selector)
                matched = unit_by_selector.get(key)
                if matched is None:
                    state.issue("selector.dangling", f"no structural unit for {key[0]} node {key[1]}", path=path, row=number, record_id=record_id)
                elif parsed.precision in {Precision.EXACT_UNIT, Precision.ARTICLE_FALLBACK, Precision.EXACT_SPAN} and ref_id in structural and matched != ref_id:
                    state.issue("selector.ref_mismatch", f"selector resolves to {matched}, endpoint ref_id is {ref_id}", path=path, row=number, record_id=record_id)
                if parsed.precision == Precision.ARTICLE_FALLBACK and ref_id not in article_roots:
                    state.issue("selector.not_article_root", "ARTICLE_FALLBACK endpoint does not reference an article root", path=path, row=number, record_id=record_id)
    for unit_id, row in structural.items():
        article_root_id = row.get("article_root_id")
        if article_root_id is not None and article_root_id not in article_roots:
            path, number, _ = state.by_id[unit_id]
            state.issue("structure.not_article_root", f"article_root_id {article_root_id!r} is not an article", path=path, row=number, record_id=unit_id)
    if exact_span_seen and state.structure_store is None:
        state.issue(
            "source_quote_not_rechecked",
            "EXACT_SPAN hashes were internally checked but no structure_store was supplied",
            path="manifest.json",
            warning=True,
        )
    return article_roots, current_articles


def _source_blocks(state: _State, document_id: str) -> dict[str, str] | None:
    if document_id in state.source_blocks:
        return state.source_blocks[document_id]
    if state.structure_store is None:
        state.source_blocks[document_id] = None
        return None
    path = state.structure_store / document_id / "result.json"
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
        blocks = {
            str(block.get("idx")): str(block.get("text") or "")
            for block in root.get("blocks") or []
            if isinstance(block, Mapping) and block.get("idx") is not None
        }
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError) as exc:
        state.issue("source_store.read", str(exc), path=str(path))
        blocks = None
    state.source_blocks[document_id] = blocks
    return blocks


def _validate_source_span(
    state: _State,
    selector: Mapping[str, Any],
    path: str,
    row: int,
    record_id: str,
) -> None:
    blocks = _source_blocks(state, str(selector.get("document_id") or ""))
    if blocks is None:
        return
    block_id = str(selector.get("block_id"))
    text = blocks.get(block_id)
    if text is None:
        state.issue("source_span.block_dangling", f"unknown source block {block_id}", path=path, row=row, record_id=record_id)
        return
    start, end = selector.get("start"), selector.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or end > len(text):
        state.issue("source_span.bounds", f"span {start}:{end} exceeds source block length {len(text)}", path=path, row=row, record_id=record_id)
        return
    actual = hashlib.sha256(text[start:end].encode("utf-8")).hexdigest()
    if actual != selector.get("quote_sha256"):
        state.issue("source_span.quote_hash", "source substring does not match selector.quote_sha256", path=path, row=row, record_id=record_id)


def _ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _validate_assertions(state: _State) -> None:
    evidence = state.by_type.get(RowType.EVIDENCE.value, {})
    relation_assertions = state.by_type.get(RowType.RELATION_ASSERTION.value, {})
    observation_ids = {
        record_id
        for row_type, rows in state.by_type.items()
        if row_type in {
            RowType.OBSERVATION.value,
            RowType.DEFINITION_OBSERVATION.value,
            RowType.FRAME_OBSERVATION.value,
            RowType.REQUIREMENT_OBSERVATION.value,
            RowType.RELATION_OBSERVATION.value,
            RowType.RELATION_CANDIDATE.value,
        }
        for record_id in rows
    }
    for assertion_id, row in relation_assertions.items():
        path, number, _ = state.by_id[assertion_id]
        evidence_ids = _ids(row.get("evidence_ids"))
        if not evidence_ids:
            state.issue("assertion.evidence_empty", "accepted relation assertion requires evidence", path=path, row=number, record_id=assertion_id)
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                state.issue("assertion.evidence_dangling", f"unknown evidence_id {evidence_id!r}", path=path, row=number, record_id=assertion_id)
        resolution = str(row.get("resolution") or "").upper()
        if not resolution or resolution in {"UNRESOLVED", "REJECTED", "PARSE_ERROR"}:
            state.issue("assertion.resolution", "relation assertion must have a resolved terminal resolution", path=path, row=number, record_id=assertion_id)
        observation_refs = _ids(row.get("source_observation_ids"))
        compatibility_fallback = (
            resolution == "ARTICLE_FALLBACK"
            and row.get("review_state") == "COMPATIBILITY_FALLBACK"
            and bool((row.get("props") or {}).get("legacy_key") or row.get("legacy_key"))
            and any(
                evidence.get(evidence_id, {}).get("kind") == "DETERMINISTIC_DERIVATION"
                for evidence_id in evidence_ids
            )
        )
        if not observation_refs and not compatibility_fallback:
            state.issue("assertion.observation_empty", "relation assertion must retain source observation lineage", path=path, row=number, record_id=assertion_id)
        for observation_id in observation_refs:
            if observation_id not in observation_ids:
                state.issue("assertion.observation_dangling", f"unknown source observation {observation_id!r}", path=path, row=number, record_id=assertion_id)

    entity_ids = set(state.by_type.get(RowType.LEGAL_ENTITY.value, {}))
    entity_ids.update(state.by_type.get(RowType.LEGAL_ENTITY_REVISION.value, {}))
    entity_ids.update(state.by_type.get(RowType.SEMANTIC_CONCEPT.value, {}))
    entity_ids.update(state.by_type.get(RowType.LEGACY_CONCEPT.value, {}))
    legacy_concepts = {
        str(row.get("legacy_id") or "")
        for row in state.by_type.get(RowType.LEGACY_CONCEPT.value, {}).values()
    }
    for row_type in (RowType.RULE_ASSERTION.value, RowType.LEGACY_ASSERTION.value):
        for assertion_id, row in state.by_type.get(row_type, {}).items():
            path, number, _ = state.by_id[assertion_id]
            roles = row.get("roles")
            if roles is None:
                continue
            for entity_id in _role_entity_ids(roles):
                if entity_id not in entity_ids:
                    state.issue("assertion.role_entity_dangling", f"unknown role entity {entity_id!r}", path=path, row=number, record_id=assertion_id)
            if row_type == RowType.LEGACY_ASSERTION.value and isinstance(roles, Mapping):
                for role, legacy_id in roles.items():
                    if isinstance(legacy_id, str) and legacy_id not in legacy_concepts:
                        state.issue("assertion.legacy_role_dangling", f"role {role!r} refers to unknown legacy concept {legacy_id!r}", path=path, row=number, record_id=assertion_id)

    rule_assertions = state.by_type.get(RowType.RULE_ASSERTION.value, {})
    for assertion_id, row in rule_assertions.items():
        path, number, _ = state.by_id[assertion_id]
        evidence_ids = _ids(row.get("evidence_ids"))
        if not evidence_ids:
            state.issue(
                "rule_assertion.evidence_empty",
                "accepted rule assertion requires evidence",
                path=path, row=number, record_id=assertion_id,
            )
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                state.issue(
                    "rule_assertion.evidence_dangling",
                    f"unknown evidence_id {evidence_id!r}",
                    path=path, row=number, record_id=assertion_id,
                )

    legal_entities = state.by_type.get(RowType.LEGAL_ENTITY.value, {})
    term_senses = state.by_type.get(RowType.TERM_SENSE.value, {})
    for term_sense_id, row in term_senses.items():
        path, number, _ = state.by_id[term_sense_id]
        entity_id = str(row.get("entity_id") or "")
        if entity_id not in legal_entities:
            state.issue(
                "term_sense.entity_dangling",
                f"unknown semantic entity {entity_id!r}",
                path=path, row=number, record_id=term_sense_id,
            )
        for evidence_id in _ids(row.get("evidence_ids")):
            if evidence_id not in evidence:
                state.issue(
                    "term_sense.evidence_dangling",
                    f"unknown evidence_id {evidence_id!r}",
                    path=path, row=number, record_id=term_sense_id,
                )

    for requirement_id, row in state.by_type.get(RowType.REQUIREMENT.value, {}).items():
        path, number, _ = state.by_id[requirement_id]
        if str(row.get("rule_assertion_id") or "") not in rule_assertions:
            state.issue(
                "requirement.rule_dangling",
                "requirement refers to an unknown rule assertion",
                path=path, row=number, record_id=requirement_id,
            )
        if str(row.get("semantic_entity_id") or "") not in legal_entities:
            state.issue(
                "requirement.entity_dangling",
                "requirement refers to an unknown semantic entity",
                path=path, row=number, record_id=requirement_id,
            )
        for evidence_id in _ids(row.get("evidence_ids")):
            if evidence_id not in evidence:
                state.issue(
                    "requirement.evidence_dangling",
                    f"unknown evidence_id {evidence_id!r}",
                    path=path, row=number, record_id=requirement_id,
                )

    for taxonomy_id, row in state.by_type.get(RowType.LEGACY_TAXONOMY.value, {}).items():
        path, number, _ = state.by_id[taxonomy_id]
        for field in ("source_legacy_id", "target_legacy_id"):
            legacy_id = str(row.get(field) or "")
            if legacy_id not in legacy_concepts:
                state.issue("taxonomy.legacy_concept_dangling", f"{field} refers to unknown legacy concept {legacy_id!r}", path=path, row=number, record_id=taxonomy_id)


def _role_entity_ids(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"entity_id", "concept_id", "term_sense_id"} and isinstance(item, str):
                yield item
            else:
                yield from _role_entity_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from _role_entity_ids(item)


def _card_root(row: Mapping[str, Any]) -> str:
    root = row.get("article_root")
    if isinstance(root, Mapping):
        return str(root.get("ref_id") or "")
    return str(row.get("article_root_id") or row.get("structural_unit_id") or "")


def _validate_projections(state: _State, current_articles: set[str]) -> None:
    relation_assertions = state.by_type.get(RowType.RELATION_ASSERTION.value, {})
    structural = state.by_type.get(RowType.STRUCTURAL_UNIT.value, {})
    unit_to_root = {
        unit_id: str(row.get("article_root_id") or "")
        for unit_id, row in structural.items()
    }
    cards = state.rows_by_path.get("projections/provision_cards.jsonl", [])
    card_counts: dict[str, int] = defaultdict(int)
    cards_by_root: dict[str, Mapping[str, Any]] = {}
    for row in cards:
        root_id = _card_root(row)
        card_counts[root_id] += 1
        cards_by_root[root_id] = row
    for root_id in sorted(current_articles):
        if card_counts.get(root_id) != 1:
            state.issue("card.current_article_cardinality", f"current article must have exactly one card, got {card_counts.get(root_id, 0)}", path="projections/provision_cards.jsonl", record_id=root_id)
    for root_id in sorted(set(card_counts) - current_articles):
        if root_id:
            state.issue("card.noncurrent", "card does not point to a current article root", path="projections/provision_cards.jsonl", record_id=root_id)

    closure_rows = state.rows_by_path.get("projections/closure_projections.jsonl", [])
    closure_modes: dict[str, set[str]] = defaultdict(set)
    closure_by_id: dict[str, Mapping[str, Any]] = {}
    projected_assertions: set[str] = set()
    for row in closure_rows:
        projection_id = str(row.get("id") or "")
        closure_by_id[projection_id] = row
        assertion_ids = _ids(row.get("assertion_ids")) or _ids(row.get("relation_assertion_id"))
        if not assertion_ids:
            state.issue("projection.assertion_empty", "closure projection has no assertion", path="projections/closure_projections.jsonl", record_id=str(row.get("id") or ""))
        mode = str(row.get("closure_mode") or row.get("mode") or "")
        for assertion_id in assertion_ids:
            projected_assertions.add(assertion_id)
            if assertion_id not in relation_assertions:
                state.issue("projection.assertion_dangling", f"unknown relation assertion {assertion_id!r}", path="projections/closure_projections.jsonl", record_id=str(row.get("id") or ""))
            closure_modes[assertion_id].add(mode)
            assertion = relation_assertions.get(assertion_id) or {}
            source_ref = str((assertion.get("source") or {}).get("ref_id") or "")
            source_root = unit_to_root.get(source_ref, "")
            declared_root = str(row.get("source_article_root_id") or "")
            if source_root and declared_root != source_root:
                state.issue(
                    "projection.source_root_mismatch",
                    f"closure source_article_root_id {declared_root!r} != folded source {source_root!r}",
                    path="projections/closure_projections.jsonl",
                    record_id=projection_id,
                )
        if row.get("runtime_wired") is not False:
            state.issue("runtime.wired", "closure projection must be published with runtime_wired=false", path="projections/closure_projections.jsonl", record_id=str(row.get("id") or ""))

    for assertion_id, assertion in relation_assertions.items():
        source_ref = str((assertion.get("source") or {}).get("ref_id") or "")
        target_ref = str((assertion.get("target") or {}).get("ref_id") or "")
        semantic_relation = (
            str((assertion.get("target") or {}).get("kind") or "")
            == "LEGAL_ENTITY"
            and bool((assertion.get("props") or {}).get("semantic_relation"))
        )
        if (
            unit_to_root.get(source_ref, "") in cards_by_root
            or unit_to_root.get(target_ref, "") in cards_by_root
        ) and assertion_id not in projected_assertions and not semantic_relation:
            state.issue(
                "projection.assertion_missing",
                "accepted relation incident to a current article has no closure projection",
                path="projections/closure_projections.jsonl",
                record_id=assertion_id,
            )

    compatibility = state.rows_by_path.get("projections/relation_compatibility.jsonl", [])
    for row in compatibility:
        assertion_ids = _ids(row.get("assertion_ids")) or _ids(row.get("relation_assertion_id"))
        for assertion_id in assertion_ids:
            if assertion_id not in relation_assertions:
                state.issue("compatibility.assertion_dangling", f"unknown relation assertion {assertion_id!r}", path="projections/relation_compatibility.jsonl", record_id=str(row.get("id") or ""))
            if row.get("mandatory") is True and not (closure_modes.get(assertion_id, set()) & _REQUIRED_MODES):
                state.issue("compatibility.mandatory_parity", f"mandatory legacy row lacks REQUIRED_WHEN_ACTIVATED closure for {assertion_id}", path="projections/relation_compatibility.jsonl", record_id=str(row.get("id") or ""))

    for path, rows in state.rows_by_path.items():
        if not path.startswith("projections/") or path in {
            "projections/provision_cards.jsonl",
            "projections/closure_projections.jsonl",
            "projections/relation_compatibility.jsonl",
            "projections/semantic_cards.jsonl",
            "projections/rule_bundle_projections.jsonl",
        }:
            continue
        for row in rows:
            if "relation_assertion_id" not in row and "assertion_ids" not in row:
                continue
            assertion_ids = _ids(row.get("assertion_ids")) or _ids(row.get("relation_assertion_id"))
            if not assertion_ids:
                state.issue("projection.assertion_empty", "projection relation assertion reference is empty", path=path, record_id=str(row.get("id") or ""))
            for assertion_id in assertion_ids:
                if assertion_id not in relation_assertions:
                    state.issue("projection.assertion_dangling", f"unknown relation assertion {assertion_id!r}", path=path, record_id=str(row.get("id") or ""))

    links_path = "observations/observation_assertion_links.jsonl"
    if links_path in state.rows_by_path:
        actual_pairs = {
            (str(row.get("observation_id") or ""), str(row.get("assertion_id") or ""))
            for row in state.rows_by_path[links_path]
        }
        expected_pairs = {
            (observation_id, assertion_id)
            for assertion_id, assertion in relation_assertions.items()
            for observation_id in _ids(assertion.get("source_observation_ids"))
        }
        if actual_pairs != expected_pairs:
            state.issue(
                "projection.observation_link_coverage",
                f"observation/assertion link pairs differ: missing={len(expected_pairs - actual_pairs)}, extra={len(actual_pairs - expected_pairs)}",
                path=links_path,
            )

    _validate_card_contents(
        state,
        cards_by_root=cards_by_root,
        unit_to_root=unit_to_root,
        relation_assertions=relation_assertions,
        closure_by_id=closure_by_id,
    )
    _validate_semantic_projections(
        state,
        current_articles=current_articles,
        structural=structural,
    )


def _string_list(
    state: _State,
    value: Any,
    *,
    path: str,
    card_id: str,
    field: str,
) -> tuple[list[str], set[str]]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        state.issue("card.list_shape", f"{field} must be a string list", path=path, record_id=card_id)
        return [], set()
    value_set = set(value)
    if len(value) != len(value_set):
        state.issue("card.list_duplicate", f"{field} contains duplicate IDs", path=path, record_id=card_id)
    if value != sorted(value):
        state.issue("card.list_order", f"{field} must be deterministically sorted", path=path, record_id=card_id)
    return value, value_set


def _validate_semantic_projections(
    state: _State,
    *,
    current_articles: set[str],
    structural: Mapping[str, Mapping[str, Any]],
) -> None:
    path = "projections/semantic_cards.jsonl"
    legal_entities = state.by_type.get(RowType.LEGAL_ENTITY.value, {})
    member_ids = set(legal_entities)
    for row_type in (
        RowType.TERM_SENSE,
        RowType.RULE_ASSERTION,
        RowType.RELATION_ASSERTION,
        RowType.REQUIREMENT,
    ):
        member_ids.update(state.by_type.get(row_type.value, {}))
    entity_card_count: Counter[str] = Counter()
    for row in state.rows_by_path.get(path, []):
        card_id = str(row.get("id") or "")
        entity_id = str(row.get("entity_id") or "")
        structure_only = row.get("card_status") == "STRUCTURE_ONLY"
        if not structure_only:
            entity_card_count[entity_id] += 1
        if not structure_only and entity_id not in legal_entities:
            state.issue(
                "semantic_card.entity_dangling",
                f"unknown semantic entity {entity_id!r}",
                path=path, record_id=card_id,
            )
        source_ref = str((row.get("source") or {}).get("ref_id") or "")
        if source_ref not in structural:
            state.issue(
                "semantic_card.source_dangling",
                f"unknown structural source {source_ref!r}",
                path=path, record_id=card_id,
            )
        article_ref = str((row.get("article_root") or {}).get("ref_id") or "")
        if article_ref not in current_articles:
            state.issue(
                "semantic_card.article_not_current",
                f"semantic card article root is not current: {article_ref!r}",
                path=path, record_id=card_id,
            )
        for member_id in _ids(row.get("assertion_ids")):
            if member_id not in member_ids:
                state.issue(
                    "semantic_card.member_dangling",
                    f"unknown semantic member {member_id!r}",
                    path=path, record_id=card_id,
                )
    for entity_id in sorted(legal_entities):
        if entity_card_count.get(entity_id) != 1:
            state.issue(
                "semantic_card.entity_cardinality",
                f"semantic entity must have exactly one card, got {entity_card_count.get(entity_id, 0)}",
                path=path, record_id=entity_id,
            )

    bundle_path = "projections/rule_bundle_projections.jsonl"
    rule_assertions = state.by_type.get(RowType.RULE_ASSERTION.value, {})
    for row in state.rows_by_path.get(bundle_path, []):
        bundle_id = str(row.get("id") or "")
        if str(row.get("root_rule_id") or "") not in rule_assertions:
            state.issue(
                "rule_bundle.root_dangling",
                "rule bundle root is not a rule assertion",
                path=bundle_path, record_id=bundle_id,
            )
        for member_id in _ids(row.get("member_ids")):
            if member_id not in member_ids:
                state.issue(
                    "rule_bundle.member_dangling",
                    f"unknown semantic member {member_id!r}",
                    path=bundle_path, record_id=bundle_id,
                )


def _validate_card_contents(
    state: _State,
    *,
    cards_by_root: Mapping[str, Mapping[str, Any]],
    unit_to_root: Mapping[str, str],
    relation_assertions: Mapping[str, Mapping[str, Any]],
    closure_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    path = "projections/provision_cards.jsonl"
    expected: dict[str, dict[str, set[str]]] = {
        root_id: {
            "definition_observation_ids": set(),
            "frame_observation_ids": set(),
            "requirement_observation_ids": set(),
            "legacy_rule_assertion_ids": set(),
            "relation_assertion_ids": set(),
            "unresolved_relation_ids": set(),
            "outgoing_projection_ids": set(),
            "incoming_projection_ids": set(),
        }
        for root_id in cards_by_root
    }
    facet_sources = (
        ("observations/definitions.jsonl", "definition_observation_ids"),
        ("observations/definition_aliases.jsonl", "definition_observation_ids"),
        ("observations/frames.jsonl", "frame_observation_ids"),
        ("observations/requirements.jsonl", "requirement_observation_ids"),
        ("canonical/legacy_assertions.jsonl", "legacy_rule_assertion_ids"),
    )
    frame_docs: set[str] = set()
    for source_path, facet in facet_sources:
        for row in state.rows_by_path.get(source_path, []):
            source = row.get("source") or {}
            ref_id = str(source.get("ref_id") or "")
            root_id = unit_to_root.get(ref_id, "")
            if root_id in expected:
                expected[root_id][facet].add(str(row.get("id") or ""))
            if source_path == "observations/frames.jsonl":
                frame_docs.add(str((source.get("selector") or {}).get("document_id") or ""))

    for projection_id, projection in closure_by_id.items():
        assertion_id = str(projection.get("relation_assertion_id") or "")
        assertion = relation_assertions.get(assertion_id)
        if assertion is None:
            continue
        source_root = unit_to_root.get(str((assertion.get("source") or {}).get("ref_id") or ""), "")
        target_root = unit_to_root.get(str((assertion.get("target") or {}).get("ref_id") or ""), "")
        if source_root in expected:
            expected[source_root]["outgoing_projection_ids"].add(projection_id)
            expected[source_root]["relation_assertion_ids"].add(assertion_id)
        if target_root in expected:
            expected[target_root]["incoming_projection_ids"].add(projection_id)
            expected[target_root]["relation_assertion_ids"].add(assertion_id)

    for unresolved in state.rows_by_path.get("observations/unresolved_relations.jsonl", []):
        observation_id = str(unresolved.get("observation_id") or "")
        observation_entry = state.by_id.get(observation_id)
        observation = observation_entry[2] if observation_entry is not None else {}
        source = observation.get("source") or {}
        if str(source.get("precision") or "") not in {"EXACT_SPAN", "EXACT_UNIT"}:
            continue
        root_id = unit_to_root.get(str(source.get("ref_id") or ""), "")
        if root_id in expected:
            expected[root_id]["unresolved_relation_ids"].add(str(unresolved.get("id") or ""))

    facet_id_sets = {
        "definition_observation_ids": set(state.by_type.get(RowType.DEFINITION_OBSERVATION.value, {})),
        "frame_observation_ids": set(state.by_type.get(RowType.FRAME_OBSERVATION.value, {})),
        "requirement_observation_ids": set(state.by_type.get(RowType.REQUIREMENT_OBSERVATION.value, {})),
        "legacy_rule_assertion_ids": set(state.by_type.get(RowType.LEGACY_ASSERTION.value, {})),
        "relation_assertion_ids": set(relation_assertions),
        "unresolved_relation_ids": set(state.by_type.get(RowType.UNRESOLVED_RELATION.value, {})),
    }
    closure_ids = set(closure_by_id)
    coverage_fields = {
        "definitions": "definition_observation_ids",
        "frames": "frame_observation_ids",
        "requirements": "requirement_observation_ids",
        "legacy_rule_assertions": "legacy_rule_assertion_ids",
        "accepted_relations": "relation_assertion_ids",
        "unresolved_relations": "unresolved_relation_ids",
        "outgoing_relations": "outgoing_projection_ids",
        "incoming_relations": "incoming_projection_ids",
    }
    for root_id, card in cards_by_root.items():
        card_id = str(card.get("id") or "")
        facets = card.get("facets")
        ports = card.get("relation_ports")
        coverage = card.get("coverage")
        if not isinstance(facets, Mapping) or not isinstance(ports, Mapping) or not isinstance(coverage, Mapping):
            state.issue("card.shape", "facets, relation_ports, and coverage must be objects", path=path, record_id=card_id)
            continue
        actual: dict[str, list[str]] = {}
        actual_sets: dict[str, set[str]] = {}
        for field in facet_id_sets:
            actual[field], actual_sets[field] = _string_list(
                state, facets.get(field), path=path, card_id=card_id,
                field=f"facets.{field}")
            dangling = actual_sets[field] - facet_id_sets[field]
            if dangling:
                state.issue("card.facet_dangling", f"facets.{field} has {len(dangling)} dangling IDs", path=path, record_id=card_id)
        for field in ("outgoing_projection_ids", "incoming_projection_ids"):
            actual[field], actual_sets[field] = _string_list(
                state, ports.get(field), path=path, card_id=card_id,
                field=f"relation_ports.{field}")
            dangling = actual_sets[field] - closure_ids
            if dangling:
                state.issue("card.port_dangling", f"relation_ports.{field} has {len(dangling)} dangling IDs", path=path, record_id=card_id)
        for field, expected_ids in expected[root_id].items():
            if actual_sets.get(field, set()) != expected_ids:
                state.issue("card.fold_mismatch", f"{field} does not equal article-root folded source data", path=path, record_id=card_id)
        for count_field, id_field in coverage_fields.items():
            if coverage.get(count_field) != len(actual.get(id_field, [])):
                state.issue("card.coverage_mismatch", f"coverage.{count_field} does not equal {id_field} count", path=path, record_id=card_id)
        document_id = str(((card.get("article_root") or {}).get("selector") or {}).get("document_id") or "")
        expected_frame_status = "AVAILABLE" if document_id in frame_docs else "NOT_EXTRACTED"
        if coverage.get("frame_status") != expected_frame_status:
            state.issue("card.frame_status", f"frame_status must be {expected_frame_status}", path=path, record_id=card_id)
        enriched = any(coverage.get(name, 0) for name in (
            "definitions", "frames", "requirements", "legacy_rule_assertions", "accepted_relations",
        ))
        if coverage.get("semantic_status") != ("ENRICHED" if enriched else "SPARSE"):
            state.issue("card.semantic_status", "semantic_status does not match populated facets", path=path, record_id=card_id)


def _legacy_key(row: Mapping[str, Any]) -> str:
    return canonical_json_text(row.get("legacy_key"))


def _legacy_projection_map(rows: Iterable[Mapping[str, Any]], state: _State, path: str) -> dict[str, tuple[Any, str]]:
    result: dict[str, tuple[Any, str]] = {}
    for row in rows:
        key = _legacy_key(row)
        record_id = str(row.get("id") or "")
        if row.get("legacy_key") is None:
            state.issue("compatibility.legacy_key_missing", "legacy_key is required", path=path, record_id=record_id)
        elif key in result:
            state.issue("compatibility.legacy_key_duplicate", "legacy_key must be unique", path=path, record_id=record_id)
        result[key] = (row.get("mandatory"), canonical_json_text(row.get("provenance")))
    return result


def _load_expected_rows(path: Path) -> list[dict[str, Any]]:
    compressed = path.suffix == ".gz"
    artifact_format = "jsonl" if compressed or path.suffix == ".jsonl" else "json"
    return [row for _, row in _json_rows(
        path, artifact_format, "gzip" if compressed else "none")
        if isinstance(row, dict)]


def _validate_compatibility(state: _State, expected_path: Path | None) -> None:
    derived_path = "projections/relation_compatibility.jsonl"
    oracle_path = "projections/legacy_section_relations.jsonl"
    derived = _legacy_projection_map(state.rows_by_path.get(derived_path, []), state, derived_path)
    if expected_path is None:
        oracle_rows = state.rows_by_path.get(oracle_path, [])
    else:
        try:
            oracle_rows = _load_expected_rows(expected_path)
        except (OSError, UnicodeError, ValueError) as exc:
            state.issue("compatibility.oracle_parse", str(exc), path=str(expected_path))
            return
    oracle = _legacy_projection_map(oracle_rows, state, oracle_path if expected_path is None else str(expected_path))
    missing = sorted(set(oracle) - set(derived))
    extra = sorted(set(derived) - set(oracle))
    for key in missing:
        state.issue("compatibility.fold_missing", f"legacy key absent from derived fold: {key}", path=derived_path)
    for key in extra:
        state.issue("compatibility.fold_extra", f"derived fold has no legacy oracle row: {key}", path=derived_path)
    for key in sorted(set(derived) & set(oracle)):
        if derived[key] != oracle[key]:
            state.issue("compatibility.fold_value_mismatch", f"mandatory/provenance mismatch for {key}", path=derived_path)


def _terminal(row: Mapping[str, Any]) -> str:
    return str(row.get("terminal_disposition") or row.get("disposition") or "").strip().casefold()


def _validate_source_accounting(state: _State) -> None:
    relation_inputs = state.rows_by_path.get("observations/relation_inputs.jsonl", [])
    unresolved_rows = state.rows_by_path.get("observations/unresolved_relations.jsonl", [])
    unresolved_by_id = {str(row.get("id") or ""): row for row in unresolved_rows}
    unresolved_by_observation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unresolved_rows:
        unresolved_by_observation[str(row.get("observation_id") or "")].append(row)
    input_by_id = {str(row.get("id") or ""): row for row in relation_inputs}
    observation_rows: list[dict[str, Any]] = []
    for path, rows in state.rows_by_path.items():
        if not path.startswith("observations/") or path in {
            "observations/unresolved_relations.jsonl",
            "observations/observation_assertion_links.jsonl",
        }:
            continue
        observation_rows.extend(row for row in rows if "terminal_disposition" in row)
    grouped: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {disposition: set() for disposition in _TERMINAL_DISPOSITIONS}
    )
    relation_assertions = state.by_type.get(RowType.RELATION_ASSERTION.value, {})
    for row in observation_rows:
        input_id = str(row.get("id") or "")
        source_kind = str(row.get("source_kind") or "")
        disposition = _terminal(row)
        if not source_kind:
            state.issue("accounting.source_kind", "accounted observation requires source_kind", path="source_accounting.json", record_id=input_id)
        if disposition not in _TERMINAL_DISPOSITIONS:
            state.issue("accounting.disposition", f"invalid terminal disposition {disposition!r}", path="source_accounting.json", record_id=input_id)
            continue
        grouped[source_kind][disposition].add(input_id)

    for input_id, row in input_by_id.items():
        assertion_ids = _ids(row.get("assertion_ids"))
        disposition = _terminal(row)
        outcomes = unresolved_by_observation.get(input_id, [])
        if disposition == "mapped":
            if not assertion_ids or outcomes:
                state.issue("accounting.mapped_shape", "mapped input requires assertions and no unresolved row", path="observations/relation_inputs.jsonl", record_id=input_id)
            for assertion_id in assertion_ids:
                assertion = relation_assertions.get(assertion_id)
                if assertion is None:
                    state.issue("accounting.assertion_dangling", f"unknown mapped assertion {assertion_id!r}", path="observations/relation_inputs.jsonl", record_id=input_id)
                elif input_id not in _ids(assertion.get("source_observation_ids")):
                    state.issue("accounting.assertion_backref", f"assertion {assertion_id} omits source observation back-reference", path="observations/relation_inputs.jsonl", record_id=input_id)
        elif disposition == "support_only":
            if outcomes:
                state.issue("accounting.support_shape", "support_only input cannot have unresolved row", path="observations/relation_inputs.jsonl", record_id=input_id)
            for assertion_id in assertion_ids:
                if assertion_id not in relation_assertions:
                    state.issue("accounting.assertion_dangling", f"unknown support assertion {assertion_id!r}", path="observations/relation_inputs.jsonl", record_id=input_id)
        elif disposition == "unresolved":
            if assertion_ids or len(outcomes) != 1:
                state.issue("accounting.unresolved_shape", "unresolved input requires exactly one unresolved row and no assertion", path="observations/relation_inputs.jsonl", record_id=input_id)
        elif disposition in {"suppressed", "out_of_contract", "parse_error"}:
            if assertion_ids or outcomes:
                state.issue("accounting.nonmapping_shape", f"{disposition} input cannot carry assertion or unresolved outcome", path="observations/relation_inputs.jsonl", record_id=input_id)
    for unresolved_id, row in unresolved_by_id.items():
        observation_id = str(row.get("observation_id") or "")
        source = input_by_id.get(observation_id)
        if source is None or _terminal(source) != "unresolved":
            state.issue("accounting.unresolved_orphan", "unresolved row is not the terminal row of one input", path="observations/unresolved_relations.jsonl", record_id=unresolved_id)

    accounting_rows = state.rows_by_path.get("source_accounting.json", [])
    if len(accounting_rows) != 1:
        state.issue("accounting.root", "source_accounting.json must contain one object", path="source_accounting.json")
        return
    root = accounting_rows[0]
    sources = root.get("sources")
    if not isinstance(sources, Mapping):
        state.issue("accounting.sources", "sources must be an object", path="source_accounting.json")
        return
    expected_kinds = set(grouped)
    if set(map(str, sources)) != expected_kinds:
        state.issue("accounting.source_partition", f"source kinds differ: expected {sorted(expected_kinds)}, got {sorted(map(str, sources))}", path="source_accounting.json")
    total_input = 0
    total_counts = {disposition: 0 for disposition in _TERMINAL_DISPOSITIONS}
    for source_kind in sorted(expected_kinds | set(map(str, sources))):
        source = sources.get(source_kind)
        if not isinstance(source, Mapping):
            continue
        exact = grouped[source_kind]
        expected_input = sum(len(ids) for ids in exact.values())
        if source.get("input_rows") != expected_input:
            state.issue("accounting.input_count", f"{source_kind}: expected {expected_input}, got {source.get('input_rows')}", path="source_accounting.json")
        terminal_counts = source.get("terminal_counts")
        terminal_ids = source.get("terminal_ids")
        if not isinstance(terminal_counts, Mapping) or set(terminal_counts) != set(_TERMINAL_DISPOSITIONS):
            state.issue("accounting.terminal_counts", f"{source_kind}: terminal_counts must contain exactly six dispositions", path="source_accounting.json")
        elif any(terminal_counts.get(disposition) != len(exact[disposition]) for disposition in _TERMINAL_DISPOSITIONS):
            state.issue("accounting.terminal_counts", f"{source_kind}: terminal_counts do not match exact partition", path="source_accounting.json")
        if not isinstance(terminal_ids, Mapping) or set(terminal_ids) != set(_TERMINAL_DISPOSITIONS):
            state.issue("accounting.terminal_ids", f"{source_kind}: terminal_ids must contain exactly six dispositions", path="source_accounting.json")
        elif any(set(_ids(terminal_ids.get(disposition))) != exact[disposition] for disposition in _TERMINAL_DISPOSITIONS):
            state.issue("accounting.terminal_ids", f"{source_kind}: terminal_ids do not match exact observation IDs", path="source_accounting.json")
        total_input += expected_input
        for disposition in _TERMINAL_DISPOSITIONS:
            total_counts[disposition] += len(exact[disposition])
    totals = root.get("totals") or {}
    if (
        not isinstance(totals, Mapping)
        or totals.get("input_rows") != total_input
        or totals.get("terminal_counts") != total_counts
    ):
        state.issue("accounting.totals", "totals do not equal the exact source partitions", path="source_accounting.json")


def _validate_source_inventory(state: _State) -> None:
    path = "observations/source_inventory.jsonl"
    if path not in state.rows_by_path:
        return
    rows = state.rows_by_path[path]
    kinds: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_paths: set[str] = set()
    for row in rows:
        record_id = str(row.get("id") or "")
        source_kind = str(row.get("source_kind") or "")
        source_path = str(row.get("source_path") or "")
        source_hash = str(row.get("source_sha256") or "")
        kinds[source_kind].append(row)
        if source_path in seen_paths:
            state.issue("inventory.path_duplicate", f"duplicate source_path {source_path!r}", path=path, record_id=record_id)
        seen_paths.add(source_path)
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            state.issue("inventory.hash", "source_sha256 must be a lowercase SHA-256", path=path, record_id=record_id)
    manifest_hashes = state.manifest.get("source_hashes")
    if not isinstance(manifest_hashes, Mapping):
        state.issue("inventory.manifest_hashes", "manifest.source_hashes must be an object when inventory is present", path="manifest.json")
        return
    if set(map(str, manifest_hashes)) != set(kinds):
        state.issue("inventory.kind_coverage", f"inventory kinds differ from manifest source_hashes: inventory={sorted(kinds)}, manifest={sorted(map(str, manifest_hashes))}", path=path)
    for source_kind in ("law_index", "delegation", "canonical", "glossary", "links"):
        rows_for_kind = kinds.get(source_kind, [])
        if len(rows_for_kind) == 1 and rows_for_kind[0].get("source_sha256") != manifest_hashes.get(source_kind):
            state.issue("inventory.manifest_hash_mismatch", f"{source_kind} inventory hash differs from manifest", path=path, record_id=str(rows_for_kind[0].get("id") or ""))


def _validate_schema_contract(state: _State) -> None:
    path = "schema_contract.json"
    rows = state.rows_by_path.get(path)
    if rows is None:
        return
    if len(rows) != 1:
        state.issue("schema_contract.root", "schema_contract.json must contain one object", path=path)
        return
    contract = rows[0]
    if contract.get("schema_version") != SCHEMA_VERSION:
        state.issue("schema_contract.schema", f"schema_version must be {SCHEMA_VERSION!r}", path=path)
    expected_contract = state.manifest.get("compiler_contract")
    if contract.get("compiler_contract") != expected_contract:
        state.issue(
            "schema_contract.compiler",
            f"compiler_contract must equal manifest value {expected_contract!r}",
            path=path,
        )
    if contract.get("runtime_wired") is not False:
        state.issue("runtime.wired", "schema contract runtime_wired must be false", path=path)


def _write_report(path: Path, report: ValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_generation(
    generation_dir: str | Path,
    *,
    expected_legacy_relations: str | Path | None = None,
    structure_store: str | Path | None = None,
    write_summary: bool = False,
) -> ValidationReport:
    """Stream and cross-check one generation without consulting compiler state.

    ``expected_legacy_relations`` is optional because published generations carry
    the serialized legacy oracle as an immutable artifact.  It is useful for a
    pre-publication CLI audit against an independently supplied JSON/JSONL oracle.
    """

    root = Path(generation_dir).resolve()
    manifest_path = root / "manifest.json"
    bootstrap_errors: list[ValidationIssue] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issue = ValidationIssue("manifest.read", "manifest.json", message=str(exc))
        return ValidationReport(False, "", 0, 0, (issue,))
    try:
        validate_manifest(manifest)
    except (SchemaValidationError, ValueError, TypeError) as exc:
        bootstrap_errors.append(ValidationIssue("manifest.schema", "manifest.json", message=str(exc)))
    if manifest.get("runtime_wired") is not False:
        bootstrap_errors.append(ValidationIssue("runtime.wired", "manifest.json", message="manifest.runtime_wired must be false"))
    if manifest.get("compiler_contract") not in {
        "legal-graph-compiler-v1", "legal-graph-compiler-v2",
        COMPILER_CONTRACT_VERSION,
    }:
        bootstrap_errors.append(ValidationIssue(
            "manifest.compiler_contract",
            "manifest.json",
            message=("unsupported compiler_contract: "
                     f"{manifest.get('compiler_contract')!r}"),
        ))

    source_store = Path(structure_store).resolve() if structure_store is not None else None
    state = _State(root, manifest, source_store)
    state.errors.extend(bootstrap_errors)
    _load_artifacts(state)
    _, current_articles = _validate_structure_and_endpoints(state)
    _validate_assertions(state)
    _validate_projections(state, current_articles)
    expected_path = Path(expected_legacy_relations).resolve() if expected_legacy_relations is not None else None
    _validate_compatibility(state, expected_path)
    _validate_source_accounting(state)
    _validate_source_inventory(state)
    _validate_schema_contract(state)
    errors = tuple(sorted(state.errors))
    warnings = tuple(sorted(state.warnings))
    report = ValidationReport(
        ok=not errors,
        generation_id=state.generation_id,
        checked_artifacts=state.checked_artifacts,
        checked_rows=state.checked_rows,
        errors=errors,
        warnings=warnings,
    )
    if write_summary:
        _write_report(root / "validation" / "summary.json", report)
    return report
