"""Deterministic compiler for the immutable ``legal-graph-v1`` sidecar.

The compiler is intentionally outside the product retrieval path.  It reads the
existing authorities and derived registries, preserves their lineage, and emits
canonical/observation/projection layers without changing any legacy source.
"""

from __future__ import annotations

import gzip
import gc
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from lawrag.core.legal_coordinate import find_coordinates, parse_label
from lawrag.core.rag import definitions, relations
from lawrag.core.rag.index import Index

from . import (
    COMPILER_CONTRACT_VERSION,
    DEFAULT_CLOSURE_POLICY,
    LEGACY_KIND_TO_PREDICATE,
    SCHEMA_VERSION,
    ClaimStatus,
    ClosureMode,
    Endpoint,
    EndpointKind,
    Evidence,
    EvidenceKind,
    Precision,
    RelationFamily,
    RelationPredicate,
    SemanticEntityType,
    Selector,
    canonical_json_text,
    content_sha256,
    sha256_hex,
    stable_id,
)


_ARTICLE = relations._ARTICLE
PROJECTION_POLICY_VERSION = "semantic-card-v2.1"
_TERMINALS = ("mapped", "support_only", "unresolved", "suppressed",
              "out_of_contract", "parse_error")
_JSONL_ARTIFACTS = (
    "canonical/instruments.jsonl",
    "canonical/structural_units.jsonl",
    "canonical/legacy_concepts.jsonl",
    "canonical/legacy_assertions.jsonl",
    "canonical/legacy_taxonomy.jsonl",
    "canonical/evidence.jsonl",
    "canonical/legal_entities.jsonl",
    "canonical/term_senses.jsonl",
    "canonical/rule_assertions.jsonl",
    "canonical/requirements.jsonl",
    "canonical/assessments.jsonl",
    "canonical/relation_assertions.jsonl",
    "observations/source_inventory.jsonl",
    "observations/definitions.jsonl",
    "observations/definition_aliases.jsonl",
    "observations/frames.jsonl",
    "observations/requirements.jsonl",
    "observations/glossary_terms.jsonl",
    "observations/relation_inputs.jsonl",
    "observations/unresolved_relations.jsonl",
    "observations/observation_assertion_links.jsonl",
    "projections/provision_cards.jsonl",
    "projections/legacy_section_relations.jsonl",
    "projections/relation_compatibility.jsonl",
    "projections/closure_projections.jsonl",
    "projections/semantic_cards.jsonl",
    "projections/rule_bundle_projections.jsonl",
)

_SEMANTIC_TOKEN = re.compile(r"[A-Za-z0-9가-힣]+")
_SEMANTIC_NOISE = frozenset({
    "경우", "해당", "따라", "따른", "정하는", "한다", "있다", "없다",
    "법률", "법령", "규정", "조문", "그밖에", "이하", "이상", "관련",
})
_KOREAN_SUFFIXES = (
    "으로부터", "에게서", "으로서", "에서는", "에게", "에서", "으로",
    "까지", "부터", "에는", "에도", "이라", "라고", "하며", "하여",
    "한다", "되는", "하는", "의", "가", "이", "은", "는", "을", "를",
    "에", "와", "과", "로",
)
_FORMULA_SIGNAL = re.compile(r"산정|계산|산식|공식|합계|금액|비율|나눈|곱한|뺀|더한|차감|괴리율")
_DOCUMENT_SIGNAL = re.compile(r"제출|첨부|신고서|보고서|재무제표|서류|계약서|감사보고서|검토보고서")
_EXCEPTION_SIGNAL = re.compile(r"다만|예외|제외|제한|아니한\s*경우|그러하지\s*아니")
_AUTHORITY_SIGNAL = re.compile(r"권한|결의|결정|선임|해임|승인|의결|위임|위탁|지정|명령")
_TIME_SIGNAL = re.compile(r"(?:\d+|일|월|년)\s*(?:일|개월|월|년)|기한|기간|이내|이후|이전|부터|까지")
_QUANTITY_SIGNAL = re.compile(r"\d|퍼센트|%|분의|금액|수량|횟수|이상|이하|초과|미만")

_SEMANTIC_CONTRACT = {
    SemanticEntityType.FORMULA_EXPRESSION: (
        "FORMULA", RelationPredicate.COMPUTES_VALUE, "formula", "COMPUTE",
    ),
    SemanticEntityType.QUANTITY_CONSTRAINT: (
        "THRESHOLD", RelationPredicate.TRIGGERS_WHEN_THRESHOLD_MET,
        "threshold_rule", "QUANTITY",
    ),
    SemanticEntityType.TEMPORAL_CONSTRAINT: (
        "TEMPORAL", RelationPredicate.EFFECTIVE_FOR, "temporal_rule", "TIME",
    ),
    SemanticEntityType.DOCUMENT_REQUIREMENT: (
        "FILING_DOCUMENT", RelationPredicate.REQUIRES_SUBMISSION_OF,
        "document_rule", "DOCUMENT",
    ),
    SemanticEntityType.AUTHORITY_ALLOCATION: (
        "AUTHORITY", RelationPredicate.ALLOCATES_AUTHORITY,
        "authority_holder", "AUTHORITY",
    ),
    SemanticEntityType.CLASSIFICATION_CRITERION: (
        "CLASSIFICATION", RelationPredicate.SETS_CLASSIFICATION_CRITERIA_FOR,
        "classification_criteria", "CLASSIFICATION",
    ),
    SemanticEntityType.EXCEPTION_ASSERTION: (
        "EXCEPTION", RelationPredicate.EXCEPTION_TO, "exception_rule", "EXCEPTION",
    ),
    SemanticEntityType.DEFINITION_SENSE: (
        "CLASSIFICATION", RelationPredicate.DEFINES,
        "classification_criteria", "DEFINITION",
    ),
}


@dataclass(frozen=True)
class BuildConfig:
    structure_store: Path = Path("01_DATA/structure")
    law_index_file: Path = Path("01_DATA/law_index.json")
    delegation_file: Path = Path("01_DATA/delegation.json")
    canonical_file: Path = Path("01_DATA/domain_graph/canonical.json")
    frames_store: Path = Path("01_DATA/frames")
    glossary_file: Path = Path("01_DATA/glossary.json")
    links_file: Path = Path("01_DATA/links.json")
    output_root: Path = Path("01_DATA/legal_graph")
    publish_current: bool = True

    def resolved(self) -> "BuildConfig":
        return BuildConfig(**{
            name: (Path(value).resolve() if name != "publish_current" else value)
            for name, value in self.__dict__.items()
        })


@dataclass(frozen=True)
class BuildResult:
    generation_id: str
    generation_path: Path
    manifest_path: Path
    content_sha256: str
    reused: bool
    current_path: Path | None


def _json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _tree_hash(path: Path, patterns: tuple[str, ...] = ("*",)) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    if path.is_file():
        files = [path]
        base = path.parent
    elif path.is_dir():
        base = path
        for pattern in patterns:
            files.extend(item for item in path.rglob(pattern) if item.is_file())
        files = sorted(set(files), key=lambda item: item.relative_to(base).as_posix())
    else:
        raise FileNotFoundError(path)
    for item in files:
        rel = item.relative_to(base).as_posix().encode("utf-8")
        payload = item.read_bytes()
        digest.update(len(rel).to_bytes(8, "big")); digest.update(rel)
        digest.update(len(payload).to_bytes(8, "big")); digest.update(payload)
    return digest.hexdigest()


def _source_hashes(config: BuildConfig) -> dict[str, str]:
    return {
        "structure": _tree_hash(config.structure_store, ("meta.json", "result.json")),
        "law_index": _tree_hash(config.law_index_file),
        "delegation": _tree_hash(config.delegation_file),
        "canonical": _tree_hash(config.canonical_file),
        "frames": _tree_hash(config.frames_store, ("*.jsonl",)),
        "glossary": _tree_hash(config.glossary_file),
        "links": _tree_hash(config.links_file),
    }


def _load_index(config: BuildConfig) -> Index:
    """Load every Index input from the paths frozen in ``BuildConfig``."""
    docs: list[tuple[str, dict, dict]] = []
    for directory in sorted(config.structure_store.iterdir()):
        result_path, meta_path = directory / "result.json", directory / "meta.json"
        if result_path.is_file() and meta_path.is_file():
            docs.append((directory.name, _json(meta_path), _json(result_path)))
    glossary = _json(config.glossary_file)
    links = _json(config.links_file)
    authority = _json(config.law_index_file)
    canonical_ids = set(authority.get("canonical_document_ids") or [])
    meta_by_id = {doc_id: meta for doc_id, meta, _ in docs}
    missing = canonical_ids - set(meta_by_id)
    if missing:
        raise RuntimeError(f"law_index canonical structure missing: {sorted(missing)}")
    generation = str(authority.get("generation_id") or "")
    bad = [doc_id for doc_id in sorted(canonical_ids)
           if (meta_by_id[doc_id].get("authority_generation") != generation
               or meta_by_id[doc_id].get("status") != "현행"
               or not meta_by_id[doc_id].get("canonical"))]
    if bad:
        raise RuntimeError(f"law_index/meta authority generation mismatch: {bad}")
    return Index.from_docs(
        docs, glossary.get("terms") or [], links.get("links") or [],
        links.get("rel_fixes") or [], canonical_doc_ids=canonical_ids,
        authority_generation=generation, authority_as_of=str(authority.get("as_of") or ""),
    )


def _base(row_type: str, row_id: str, layer: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "row_type": row_type,
            "layer": layer, "id": row_id}


def _unit_id(doc_id: str, node_id: object) -> str:
    return stable_id("unit", doc_id, node_id)


def _article_root_or_none(view, node_id: object) -> object | None:
    root = relations.article_root(view, node_id)
    node = view.by_id.get(root)
    if node is None or not _ARTICLE.fullmatch(str(node.get("surface") or "").strip()):
        return None
    return root


def _instrument_id(doc_id: str) -> str:
    return stable_id("instrument", doc_id)


def _selector(doc_id: str, node_id: object | None, *, coordinate: str = "",
              quote: str | None = None, block_id: object | None = None,
              start: int | None = None, end: int | None = None) -> Selector:
    return Selector(
        document_id=doc_id,
        node_id=node_id if isinstance(node_id, int) else None,
        block_id=block_id if isinstance(block_id, (int, str)) else None,
        start=start,
        end=end,
        coordinate=coordinate or None,
        quote_sha256=sha256_hex(quote) if quote is not None else None,
    )


def _endpoint(index: Index, doc_id: str, node_id: object | None,
              precision: Precision = Precision.EXACT_UNIT) -> Endpoint:
    view = index.docs.get(doc_id)
    node = view.by_id.get(node_id) if view is not None else None
    if node is None:
        if view is not None and node_id is None:
            return Endpoint(EndpointKind.DOCUMENT, Precision.DOCUMENT_ONLY,
                            ref_id=_instrument_id(doc_id),
                            selector=_selector(doc_id, None), label=view.name)
        return Endpoint(EndpointKind.UNRESOLVED, Precision.UNRESOLVED,
                        selector=_selector(doc_id, None), label=str(node_id or ""))
    coordinate = str(node.get("coordinate_key") or view.path(node_id))
    return Endpoint(EndpointKind.STRUCTURAL_UNIT, precision,
                    ref_id=_unit_id(doc_id, node_id),
                    selector=_selector(doc_id, node_id, coordinate=coordinate),
                    label=view.path(node_id))


def _block_quote(index: Index, doc_id: str, node_id: object,
                 block_id: object | None = None) -> str:
    view = index.docs[doc_id]
    block = view.block_by_idx.get(block_id)
    if block is None:
        node = view.by_id.get(node_id) or {}
        block = view.block_by_idx.get(node.get("block"))
    return str((block or {}).get("text") or "")


class _Collector:
    def __init__(self, root: Path, generation_id: str, authority_generation: str):
        self.root = root
        self.generation_id = generation_id
        self.authority_generation = authority_generation
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self._positions: dict[str, dict[str, int]] = {}

    def add(self, path: str, row: Mapping[str, Any]) -> None:
        value = dict(row)
        value.setdefault("layer", ("canonical" if path.startswith("canonical/")
                                   else "projection" if path.startswith("projections/")
                                   else "observation"))
        value.setdefault("generation_id", self.generation_id)
        value.setdefault("authority_generation", self.authority_generation)
        bucket = self.rows.setdefault(path, [])
        row_id = str(value.get("id") or "")
        positions = self._positions.setdefault(path, {})
        position = positions.get(row_id) if row_id else None
        if position is not None:
            old = bucket[position]
            if path.startswith("canonical/"):
                if value.get("row_type") == "relation_assertion":
                    for field in ("evidence_ids", "source_observation_ids"):
                        old[field] = sorted(set([*(old.get(field) or []), *(value.get(field) or [])]))
                    return
                if old != value:
                    raise RuntimeError(f"canonical id collision in {path}: {value.get('id')}")
                return
            if old != value:
                raise RuntimeError(f"row id collision in {path}: {value.get('id')}")
            return
        if row_id:
            positions[row_id] = len(bucket)
        bucket.append(value)

    def get(self, path: str, row_id: str) -> dict[str, Any] | None:
        position = self._positions.get(path, {}).get(row_id)
        if position is None:
            return None
        return self.rows[path][position]

    def write(self) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}
        for relpath in _JSONL_ARTIFACTS:
            self.rows.setdefault(relpath, [])
        for relpath in sorted(self.rows):
            rows = sorted(self.rows[relpath], key=lambda row: (
                str(row.get("id") or ""), canonical_json_text(row)))
            stored_relpath = relpath + ".gz" if relpath.endswith(".jsonl") else relpath
            target = self.root / stored_relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            if relpath.endswith(".jsonl"):
                with target.open("wb") as raw_handle:
                    with gzip.GzipFile(
                        filename="", mode="wb", fileobj=raw_handle,
                        compresslevel=3, mtime=0,
                    ) as handle:
                        for row in rows:
                            handle.write((canonical_json_text(row) + "\n").encode("utf-8"))
            else:
                with target.open("wb") as handle:
                    for row in rows:
                        handle.write((canonical_json_text(row) + "\n").encode("utf-8"))
            types = sorted({str(row.get("row_type") or "") for row in rows})
            payload = target.read_bytes()
            artifacts[stored_relpath] = {
                "path": stored_relpath, "logical_path": relpath,
                "sha256": sha256_hex(payload), "bytes": len(payload),
                "rows": len(rows), "format": "jsonl",
                "compression": "gzip" if relpath.endswith(".jsonl") else "none",
                **({"row_type": types[0]} if len(types) == 1 and types[0] else {}),
            }
        return artifacts


def _children(view, parent: object) -> list[dict[str, Any]]:
    cache = getattr(view, "_legal_graph_children_cache", None)
    if cache is None:
        cache = {}
        for node in view.nodes:
            cache.setdefault(node.get("parent"), []).append(node)
        for values in cache.values():
            values.sort(key=lambda node: (node.get("span") or [10**9])[0])
        setattr(view, "_legal_graph_children_cache", cache)
    return cache.get(parent, [])


def _article_nodes(view) -> dict[str, list[dict[str, Any]]]:
    cache = getattr(view, "_legal_graph_article_cache", None)
    if cache is None:
        cache = {}
        for node in view.nodes:
            parsed = parse_label(str(node.get("surface") or ""))
            if parsed is not None and parsed.unit == "조":
                cache.setdefault(parsed.canonical_surface(), []).append(node)
        setattr(view, "_legal_graph_article_cache", cache)
    return cache


def _resolve_anchor(index: Index, doc_id: str, anchor: str,
                    fallback_node: object | None) -> tuple[object | None, bool]:
    """Resolve an official lower-unit anchor against the actual structure tree."""
    view = index.docs.get(doc_id)
    if view is None:
        return None, False
    occurrences = find_coordinates(str(anchor or ""))
    if not occurrences:
        node = fallback_node if fallback_node in view.by_id else None
        return node, node is not None and not str(anchor or "").strip()
    coordinate = occurrences[0].coordinate
    if coordinate.unit != "조":
        return (fallback_node if fallback_node in view.by_id else None), False
    article_surface = coordinate.replace_chain(()).canonical_surface()
    candidates = _article_nodes(view).get(article_surface, [])
    if not candidates:
        return (fallback_node if fallback_node in view.by_id else None), False
    current = candidates[0]
    for unit, ordinal in coordinate.chain:
        matches = []
        for child in _children(view, current.get("id")):
            parsed = parse_label(str(child.get("surface") or ""))
            if parsed is None:
                continue
            # Numbered dot items are parsed as 호 and Hangul dots as 목.
            if parsed.n == ordinal and (unit is None or parsed.unit == unit):
                matches.append(child)
        if not matches:
            return (fallback_node if fallback_node in view.by_id else current.get("id")), False
        current = matches[0]
    return current.get("id"), True


def _family(predicate: RelationPredicate) -> RelationFamily:
    from . import RELATION_FAMILY_BY_PREDICATE
    return RELATION_FAMILY_BY_PREDICATE[predicate]


def _legacy_key(kind: str, src_doc: str, src_node: object,
                dst_doc: str, dst_node: object) -> str:
    return canonical_json_text([kind, src_doc, src_node, dst_doc, dst_node])


def _evidence(collector: _Collector, index: Index, doc_id: str, node_id: object,
              *, block_id: object | None, kind: EvidenceKind, method: str,
              props: Mapping[str, Any]) -> str:
    quote = _block_quote(index, doc_id, node_id, block_id)
    source = _endpoint(index, doc_id, node_id)
    if quote:
        view = index.docs[doc_id]
        block = view.block_by_idx.get(block_id)
        if block is None:
            block_id = (view.by_id.get(node_id) or {}).get("block")
        selector = _selector(doc_id, node_id,
                             coordinate=(source.selector.coordinate if source.selector else ""),
                             quote=quote, block_id=block_id, start=0, end=len(quote))
        source = Endpoint(source.kind, Precision.EXACT_SPAN,
                          source.ref_id, selector, source.label)
    eid = stable_id("evidence", kind.value, doc_id, node_id, block_id, method, props, quote)
    row = Evidence(eid, kind, source, quote_text=quote or None,
                   method=method, props=dict(props)).to_dict()
    collector.add("canonical/evidence.jsonl", row)
    return eid


def _relation_assertion(collector: _Collector, index: Index, predicate: RelationPredicate,
                        src_doc: str, src_node: object, dst_doc: str, dst_node: object,
                        evidence_ids: list[str], observation_ids: list[str], *,
                        precision: Precision = Precision.EXACT_UNIT,
                        resolution: str = "EXACT_SOURCE_BACKED",
                        legacy_kind: str = "", props: Mapping[str, Any] | None = None) -> dict:
    source = _endpoint(index, src_doc, src_node, precision)
    target = _endpoint(index, dst_doc, dst_node, precision)
    aid = stable_id("relation", predicate.value, source.to_dict(), target.to_dict(), resolution)
    row = {
        **_base("relation_assertion", aid, "canonical"),
        "predicate": predicate.value, "family": _family(predicate).value,
        "source": source.to_dict(), "target": target.to_dict(),
        "claim_status": ClaimStatus.ACCEPTED.value,
        "evidence_ids": sorted(set(evidence_ids)),
        "source_observation_ids": sorted(set(observation_ids)),
        "resolution": resolution,
        "review_state": "SOURCE_BACKED" if precision != Precision.ARTICLE_FALLBACK
                        else "COMPATIBILITY_FALLBACK",
        "legacy_kind": legacy_kind,
        "props": dict(props or {}),
    }
    collector.add("canonical/relation_assertions.jsonl", row)
    return row


def _compile_structure(collector: _Collector, index: Index,
                       current_docs: set[str]) -> tuple[dict[tuple[str, object], str], list[dict]]:
    units: dict[tuple[str, object], str] = {}
    cards: list[dict] = []
    for doc_id, view in sorted(index.docs.items()):
        iid = _instrument_id(doc_id)
        collector.add("canonical/instruments.jsonl", {
            **_base("instrument", iid, "canonical"), "document_id": doc_id,
            "name": view.name, "kind": view.kind, "status": view.status or "현행",
            "series": view.series, "version": view.version, "enforce": view.enforce,
            "revised": view.revised, "current": doc_id in current_docs,
            "authority_generation": index.authority_generation,
        })
        for node in view.nodes:
            node_id = node.get("id")
            uid = _unit_id(doc_id, node_id); units[(doc_id, node_id)] = uid
            root = _article_root_or_none(view, node_id)
            root_id = _unit_id(doc_id, root) if root in view.by_id else None
            parent = node.get("parent")
            collector.add("canonical/structural_units.jsonl", {
                **_base("structural_unit", uid, "canonical"),
                "document_id": doc_id, "node_id": node_id,
                "instrument_id": iid, "unit_kind": str(node.get("family") or "unknown"),
                "parent_id": _unit_id(doc_id, parent) if parent in view.by_id else None,
                "article_root_id": root_id,
                "selector": _selector(doc_id, node_id,
                                      coordinate=str(node.get("coordinate_key") or view.path(node_id))).to_dict(),
                "surface": str(node.get("surface") or ""),
                "title": str(node.get("title") or ""), "family": str(node.get("family") or ""),
                "level": int(node.get("level") or 0), "span": list(node.get("span") or [0, 0]),
                "current": doc_id in current_docs,
                "authority_generation": index.authority_generation,
            })
            if doc_id in current_docs and _ARTICLE.fullmatch(str(node.get("surface") or "").strip()):
                endpoint = _endpoint(index, doc_id, node_id)
                card = {
                    **_base("provision_card", stable_id("card", uid), "projection"),
                    "article_root": endpoint.to_dict(), "article_root_id": uid,
                    "structural_unit_id": uid, "facets": {}, "coverage": {
                        "definitions": 0, "frames": 0, "requirements": 0,
                        "accepted_relations": 0, "unresolved_relations": 0,
                    }, "runtime_wired": False,
                }
                cards.append(card)
    return units, cards


def _compile_source_inventory(collector: _Collector, config: BuildConfig,
                              source_hashes: Mapping[str, str]) -> None:
    roots = {
        "law_index": config.law_index_file,
        "delegation": config.delegation_file,
        "canonical": config.canonical_file,
        "glossary": config.glossary_file,
        "links": config.links_file,
    }
    for source_kind, path in sorted(roots.items()):
        collector.add("observations/source_inventory.jsonl", {
            **_base("source_inventory", stable_id("source", source_kind, str(path)), "observation"),
            "source_kind": source_kind, "source_path": str(path),
            "source_sha256": source_hashes[source_kind],
        })
    for directory in sorted(config.structure_store.iterdir()):
        if not (directory / "meta.json").is_file() or not (directory / "result.json").is_file():
            continue
        collector.add("observations/source_inventory.jsonl", {
            **_base("source_inventory", stable_id("source", "structure", directory.name), "observation"),
            "source_kind": "structure", "source_path": str(directory),
            "source_sha256": _tree_hash(directory, ("meta.json", "result.json")),
        })
    for path in sorted(config.frames_store.glob("*.jsonl")):
        collector.add("observations/source_inventory.jsonl", {
            **_base("source_inventory", stable_id("source", "frames", path.name), "observation"),
            "source_kind": "frames", "source_path": str(path),
            "source_sha256": _tree_hash(path),
        })


def _compile_legacy(collector: _Collector, canonical: Mapping[str, Any], index: Index) -> None:
    def concept_ref(value: object) -> str:
        ref = str(value or "")
        return ref[len("concept:"):] if ref.startswith("concept:") else ref

    for concept in canonical.get("concepts", []):
        legacy_id = str(concept.get("id") or "")
        collector.add("canonical/legacy_concepts.jsonl", {
            **_base("legacy_concept", stable_id("legacy_concept", legacy_id), "canonical"),
            "legacy_id": legacy_id, "label": str(concept.get("label") or ""),
            "entity_type": str(concept.get("type") or "domain_term"),
            "claim_status": ClaimStatus.LEGACY_BACKED.value,
            "review_state": "NEEDS_TYPED_REVIEW" if concept.get("type") == "domain_term"
                            else "LEGACY_APPROVED",
            "legacy_payload": concept,
        })
    for assertion in canonical.get("assertions", []):
        legacy_id = str(assertion.get("id") or "")
        src = assertion.get("source") or {}
        endpoint = _endpoint(index, str(src.get("doc_id") or ""), src.get("node"))
        collector.add("canonical/legacy_assertions.jsonl", {
            **_base("legacy_assertion", stable_id("legacy_assertion", legacy_id), "canonical"),
            "legacy_id": legacy_id, "source": endpoint.to_dict(),
            "roles": assertion.get("roles") or {}, "claim_status": ClaimStatus.LEGACY_BACKED.value,
            "review_state": "LEGACY_UNIT_GROUNDED" if endpoint.precision != Precision.UNRESOLVED
                            else "NEEDS_SOURCE_REVIEW",
            "evidence_ids": [], "legacy_payload": assertion,
        })
    for taxonomy in canonical.get("relations", []):
        legacy_id = str(taxonomy.get("id") or "")
        collector.add("canonical/legacy_taxonomy.jsonl", {
            **_base("legacy_taxonomy", stable_id("legacy_taxonomy", legacy_id), "canonical"),
            "legacy_id": legacy_id, "relation_type": str(taxonomy.get("type") or ""),
            "source_legacy_id": concept_ref(taxonomy.get("src")),
            "target_legacy_id": concept_ref(taxonomy.get("dst")),
            "claim_status": ClaimStatus.LEGACY_BACKED.value,
            "review_state": "LEGACY_APPROVED", "legacy_payload": taxonomy,
        })


def _observation(collector: _Collector, path: str, source_kind: str,
                 source_row_key: str, payload: Mapping[str, Any], terminal: str,
                 *, assertion_ids: Iterable[str] = (), reason: str = "",
                 row_type: str = "observation",
                 source: Mapping[str, Any] | None = None,
                 target: Mapping[str, Any] | None = None) -> dict:
    oid = stable_id("observation", source_kind, source_row_key, payload)
    row = {
        **_base(row_type, oid, "observation"), "source_kind": source_kind,
        "source_row_key": source_row_key, "payload": dict(payload),
        "claim_status": ClaimStatus.CANDIDATE.value,
        "terminal_disposition": terminal,
        "assertion_ids": sorted(set(assertion_ids)), "reason": reason,
    }
    if row_type == "observation":
        row["observation_kind"] = source_kind
    if source is not None:
        row["source"] = dict(source)
    if target is not None:
        row["target"] = dict(target)
    collector.add(path, row)
    return row


def _link_observation(collector: _Collector, observation_id: str,
                      assertion_id: str) -> None:
    row = collector.get("observations/relation_inputs.jsonl", observation_id)
    if row is not None:
        row["assertion_ids"] = sorted(set([*(row.get("assertion_ids") or []), assertion_id]))
    collector.add("observations/observation_assertion_links.jsonl", {
        **_base("observation_assertion_link",
                stable_id("obs_link", observation_id, assertion_id), "observation"),
        "observation_id": observation_id, "assertion_id": assertion_id,
        "link_kind": "ACCEPTED_AS",
    })


def _mark_unresolved(collector: _Collector, observation_id: str,
                     unresolved_id: str) -> None:
    row = collector.get("observations/relation_inputs.jsonl", observation_id)
    if row is not None:
        row["unresolved_id"] = unresolved_id


def _compile_candidate_observations(collector: _Collector, config: BuildConfig,
                                    index: Index, bundle) -> dict[str, dict[str, Any]]:
    accounting: dict[str, dict[str, Any]] = {}

    def account(source: str, rows: list[dict], disposition: str = "support_only") -> None:
        ids = [row["id"] for row in rows]
        accounting[source] = {
            "input_rows": len(rows),
            "terminal_counts": {kind: len(rows) if kind == disposition else 0
                                for kind in _TERMINALS},
            "terminal_ids": {kind: ids if kind == disposition else []
                             for kind in _TERMINALS},
            "accepted_ids": [], "unresolved_ids": [], "candidate_ids": ids,
            "accepted_assertion_ids": [],
        }

    definition_rows = []
    for doc_id, view in sorted(index.docs.items()):
        for order, item in enumerate(definitions.defs(view)):
            payload = {"doc_id": doc_id, **item}
            definition_rows.append(_observation(
                collector, "observations/definitions.jsonl", "definitions",
                f"{doc_id}:{order}:{content_sha256(payload)}", payload, "support_only",
                row_type="definition_observation",
                source=_endpoint(index, doc_id, item.get("node")).to_dict()))
        for order, item in enumerate(definitions._alias_edges(view)):
            payload = {"doc_id": doc_id, "alias": True, **item}
            definition_rows.append(_observation(
                collector, "observations/definition_aliases.jsonl", "definitions",
                f"{doc_id}:{order}:{content_sha256(payload)}", payload, "support_only",
                row_type="definition_observation",
                source=_endpoint(index, doc_id, item.get("node")).to_dict()))
    account("definitions", definition_rows)

    frame_rows = []
    for path in sorted(config.frames_store.glob("*.jsonl")):
        doc_id = path.stem
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            payload = {"doc_id": doc_id, "line": line_no, **json.loads(line)}
            frame_rows.append(_observation(
                collector, "observations/frames.jsonl", "frames",
                f"{doc_id}:{line_no}", payload, "support_only",
                row_type="frame_observation",
                source=_endpoint(index, doc_id, payload.get("node")).to_dict()))
    account("frames", frame_rows)

    requirement_rows = []
    for order, req in enumerate(bundle.requirements):
        payload = {name: getattr(req, name) for name in req.__dataclass_fields__}
        requirement_rows.append(_observation(
            collector, "observations/requirements.jsonl", "requirements",
            f"{order}:{content_sha256(payload)}", payload, "support_only",
            row_type="requirement_observation",
            source=_endpoint(index, req.doc_id, req.node).to_dict()))
    account("requirements", requirement_rows)

    glossary_rows = []
    for order, term in enumerate((_json(config.glossary_file).get("terms") or [])):
        glossary_rows.append(_observation(
            collector, "observations/glossary_terms.jsonl", "glossary",
            f"{order}:{content_sha256(term)}", term, "support_only",
            row_type="observation"))
    account("glossary", glossary_rows)
    return accounting


def _semantic_text(payload: Mapping[str, Any]) -> str:
    values = [
        payload.get("term"), payload.get("to"), payload.get("from"),
        payload.get("surface"), payload.get("source"), payload.get("actor"),
        payload.get("act"), payload.get("object"), payload.get("target"),
    ]
    return " ".join(str(value).strip() for value in values if str(value or "").strip())


def _semantic_terms(*values: object) -> list[str]:
    terms: set[str] = set()
    for value in values:
        for raw_token in _SEMANTIC_TOKEN.findall(str(value or "")):
            token = raw_token.casefold()
            if len(token) < 2 or token in _SEMANTIC_NOISE:
                continue
            terms.add(token)
            for suffix in _KOREAN_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                    base = token[:-len(suffix)]
                    if base not in _SEMANTIC_NOISE:
                        terms.add(base)
                    break
    return sorted(terms)


def _semantic_types(row: Mapping[str, Any]) -> tuple[SemanticEntityType, ...]:
    payload = row.get("payload") or {}
    text = _semantic_text(payload)
    row_type = str(row.get("row_type") or "")
    found: list[SemanticEntityType] = []
    if row_type == "definition_observation":
        found.append(SemanticEntityType.DEFINITION_SENSE)
        if (
            str(payload.get("kind") or "") in {"인용정의", "정의", "별칭"}
            or "란" in text
            or "말한다" in text
            or "해당" in text
        ):
            found.append(SemanticEntityType.CLASSIFICATION_CRITERION)
    elif row_type == "requirement_observation":
        kind = str(payload.get("kind") or "").upper()
        if kind == "TIME":
            found.append(SemanticEntityType.TEMPORAL_CONSTRAINT)
        if kind == "QUANTITY":
            found.append(SemanticEntityType.QUANTITY_CONSTRAINT)
        if kind == "CONDITION":
            found.append(SemanticEntityType.CLASSIFICATION_CRITERION)
        if kind == "EXCEPTION" or _EXCEPTION_SIGNAL.search(text):
            found.append(SemanticEntityType.EXCEPTION_ASSERTION)
        if _FORMULA_SIGNAL.search(text):
            found.append(SemanticEntityType.FORMULA_EXPRESSION)
        if _DOCUMENT_SIGNAL.search(text):
            found.append(SemanticEntityType.DOCUMENT_REQUIREMENT)
    elif row_type == "frame_observation":
        function = str(payload.get("function") or "")
        if function == "근거·권한" or _AUTHORITY_SIGNAL.search(text):
            found.append(SemanticEntityType.AUTHORITY_ALLOCATION)
        if _DOCUMENT_SIGNAL.search(text):
            found.append(SemanticEntityType.DOCUMENT_REQUIREMENT)
        if _EXCEPTION_SIGNAL.search(text):
            found.append(SemanticEntityType.EXCEPTION_ASSERTION)
    return tuple(dict.fromkeys(found))


def _structure_family_hints(text: str) -> list[str]:
    """Cheap search hints for a source-only lower-unit card.

    These are routing facets, not canonical legal assertions.  The card keeps
    ``card_status=STRUCTURE_ONLY`` so retrieval cannot mistake a lexical hint
    for a source-backed semantic entity.
    """
    families = {"CLASSIFICATION"}
    if _FORMULA_SIGNAL.search(text):
        families.add("FORMULA")
    if _DOCUMENT_SIGNAL.search(text):
        families.add("FILING_DOCUMENT")
    if _EXCEPTION_SIGNAL.search(text):
        families.add("EXCEPTION")
    if _AUTHORITY_SIGNAL.search(text):
        families.add("AUTHORITY")
    if _TIME_SIGNAL.search(text):
        families.add("TEMPORAL")
    if _QUANTITY_SIGNAL.search(text):
        families.add("THRESHOLD")
    if "위탁" in text or "재위탁" in text:
        families.add("ENTRUSTMENT")
    return sorted(families)


def _semantic_target(entity_id: str, source: Endpoint, label: str) -> Endpoint:
    return Endpoint(
        EndpointKind.LEGAL_ENTITY,
        source.precision,
        ref_id=entity_id,
        selector=source.selector,
        label=label[:240],
    )


def _semantic_relation_assertion(
    collector: _Collector,
    *,
    source: Endpoint,
    target: Endpoint,
    predicate: RelationPredicate,
    evidence_ids: Iterable[str],
    observation_ids: Iterable[str],
    semantic_type: SemanticEntityType,
) -> dict[str, Any]:
    assertion_id = stable_id(
        "relation", predicate.value, source.to_dict(), target.to_dict(),
        "SEMANTIC_SOURCE_BACKED",
    )
    row = {
        **_base("relation_assertion", assertion_id, "canonical"),
        "predicate": predicate.value,
        "family": _family(predicate).value,
        "source": source.to_dict(),
        "target": target.to_dict(),
        "claim_status": ClaimStatus.ACCEPTED.value,
        "evidence_ids": sorted(set(evidence_ids)),
        "source_observation_ids": sorted(set(observation_ids)),
        "resolution": "SEMANTIC_SOURCE_BACKED",
        "review_state": "DETERMINISTIC_SOURCE_BACKED",
        "legacy_kind": "",
        "props": {
            "semantic_relation": True,
            "semantic_type": semantic_type.value,
            "closure_projection": False,
        },
    }
    collector.add("canonical/relation_assertions.jsonl", row)
    return row


def _link_semantic_observation(
    collector: _Collector,
    observation_path: str,
    observation_id: str,
    assertion_id: str,
) -> None:
    row = collector.get(observation_path, observation_id)
    if row is None:
        raise RuntimeError(f"semantic observation missing: {observation_path}:{observation_id}")
    row["terminal_disposition"] = "mapped"
    row["reason"] = "typed_semantic_assertion_materialized"
    row["assertion_ids"] = sorted(set([
        *(row.get("assertion_ids") or []), assertion_id,
    ]))
    collector.add("observations/observation_assertion_links.jsonl", {
        **_base(
            "observation_assertion_link",
            stable_id("obs_link", observation_id, assertion_id),
            "observation",
        ),
        "observation_id": observation_id,
        "assertion_id": assertion_id,
        "link_kind": "MATERIALIZED_AS_TYPED_SEMANTIC_ASSERTION",
    })


def _refresh_semantic_accounting(
    accounting: dict[str, dict[str, Any]],
    collector: _Collector,
) -> None:
    sources = {
        "definitions": (
            "observations/definitions.jsonl",
            "observations/definition_aliases.jsonl",
        ),
        "frames": ("observations/frames.jsonl",),
        "requirements": ("observations/requirements.jsonl",),
    }
    for source_kind, paths in sources.items():
        rows = [row for path in paths for row in collector.rows.get(path, [])]
        terminal_ids = {
            terminal: sorted(
                str(row["id"]) for row in rows
                if row.get("terminal_disposition") == terminal
            )
            for terminal in _TERMINALS
        }
        accepted_assertions = sorted({
            assertion_id
            for row in rows
            for assertion_id in row.get("assertion_ids") or []
        })
        accounting[source_kind] = {
            "input_rows": len(rows),
            "terminal_counts": {
                terminal: len(terminal_ids[terminal]) for terminal in _TERMINALS
            },
            "terminal_ids": terminal_ids,
            "accepted_ids": terminal_ids["mapped"],
            "unresolved_ids": terminal_ids["unresolved"],
            "candidate_ids": terminal_ids["support_only"],
            "accepted_assertion_ids": accepted_assertions,
        }


def _compile_semantic_entities(
    collector: _Collector,
    index: Index,
    current_docs: set[str],
    accounting: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Promote deterministic observation shapes into typed, searchable rows."""
    observation_paths = (
        "observations/definitions.jsonl",
        "observations/definition_aliases.jsonl",
        "observations/requirements.jsonl",
        "observations/frames.jsonl",
    )
    specs: dict[tuple[str, str, object, str], dict[str, Any]] = {}
    for path in observation_paths:
        for row in collector.rows.get(path, []):
            source_map = row.get("source") or {}
            selector = source_map.get("selector") or {}
            doc_id = str(selector.get("document_id") or "")
            node_id = selector.get("node_id")
            if doc_id not in current_docs or doc_id not in index.docs:
                continue
            if node_id not in index.docs[doc_id].by_id:
                continue
            article_root = _article_root_or_none(index.docs[doc_id], node_id)
            if article_root is None:
                continue
            payload = row.get("payload") or {}
            for semantic_type in _semantic_types(row):
                anchor = (
                    str(payload.get("term") or payload.get("to") or "").strip()
                    if semantic_type in {
                        SemanticEntityType.DEFINITION_SENSE,
                        SemanticEntityType.CLASSIFICATION_CRITERION,
                    }
                    else ""
                )
                key = (semantic_type.value, doc_id, node_id, anchor)
                spec = specs.setdefault(key, {
                    "semantic_type": semantic_type,
                    "doc_id": doc_id,
                    "node_id": node_id,
                    "article_root": article_root,
                    "anchor": anchor,
                    "observation_rows": [],
                    "observation_paths": {},
                    "texts": [],
                })
                spec["observation_rows"].append(row)
                spec["observation_paths"][str(row["id"])] = path
                spec["texts"].append(_semantic_text(payload))

    bundle_members: dict[tuple[str, object], set[str]] = {}
    counts = {semantic_type.value: 0 for semantic_type in SemanticEntityType}
    for key in sorted(specs, key=canonical_json_text):
        spec = specs[key]
        semantic_type: SemanticEntityType = spec["semantic_type"]
        doc_id, node_id = spec["doc_id"], spec["node_id"]
        view = index.docs[doc_id]
        node = view.by_id[node_id]
        source = _endpoint(index, doc_id, node_id)
        article_root = spec["article_root"]
        article_endpoint = _endpoint(index, doc_id, article_root)
        family_id, predicate, coverage_key, operator = _SEMANTIC_CONTRACT[semantic_type]
        label = spec["anchor"] or next(
            (text for text in spec["texts"] if text),
            str(node.get("title") or node.get("surface") or view.path(node_id)),
        )
        entity_id = stable_id(
            "entity", semantic_type.value, doc_id, node_id, spec["anchor"],
        )
        observation_ids = sorted({
            str(row["id"]) for row in spec["observation_rows"]
        })
        evidence_id = _evidence(
            collector, index, doc_id, node_id, block_id=node.get("block"),
            kind=EvidenceKind.SOURCE_TEXT,
            method="typed-semantic-observation-v2",
            props={"semantic_type": semantic_type.value},
        )
        terms = _semantic_terms(
            label, *spec["texts"], view.name, view.path(node_id),
        )
        entity_row = {
            **_base("legal_entity", entity_id, "canonical"),
            "entity_type": semantic_type.value,
            "label": label[:600],
            "source": source.to_dict(),
            "article_root": article_endpoint.to_dict(),
            "claim_status": ClaimStatus.ACCEPTED.value,
            "evidence_ids": [evidence_id],
            "observation_ids": observation_ids,
            "family_ids": [family_id],
            "terms": terms,
            "props": {"operator": operator, "coverage_key": coverage_key},
        }
        collector.add("canonical/legal_entities.jsonl", entity_row)

        target = _semantic_target(entity_id, source, label)
        relation = _semantic_relation_assertion(
            collector,
            source=source,
            target=target,
            predicate=predicate,
            evidence_ids=[evidence_id],
            observation_ids=observation_ids,
            semantic_type=semantic_type,
        )
        rule_id = stable_id("rule", semantic_type.value, entity_id)
        rule_row = {
            **_base("rule_assertion", rule_id, "canonical"),
            "claim_status": ClaimStatus.ACCEPTED.value,
            "source": source.to_dict(),
            "evidence_ids": [evidence_id],
            "entity_id": entity_id,
            "semantic_type": semantic_type.value,
            "predicate": predicate.value,
            "roles": {
                "SUBJECT": {"ref_id": source.ref_id},
                "OBJECT": {"entity_id": entity_id},
            },
            "observation_ids": observation_ids,
        }
        collector.add("canonical/rule_assertions.jsonl", rule_row)
        assertion_ids = [relation["id"], rule_id]

        if semantic_type == SemanticEntityType.DEFINITION_SENSE:
            term = spec["anchor"] or label
            term_sense_id = stable_id("term_sense", doc_id, node_id, term)
            collector.add("canonical/term_senses.jsonl", {
                **_base("term_sense", term_sense_id, "canonical"),
                "term": term,
                "scope": source.to_dict(),
                "evidence_ids": [evidence_id],
                "entity_id": entity_id,
                "claim_status": ClaimStatus.ACCEPTED.value,
                "aliases": sorted({
                    str((row.get("payload") or {}).get("from") or "")
                    for row in spec["observation_rows"]
                    if str((row.get("payload") or {}).get("from") or "")
                }),
            })
            assertion_ids.append(term_sense_id)
        else:
            requirement_id = stable_id("requirement", rule_id, operator)
            collector.add("canonical/requirements.jsonl", {
                **_base("requirement", requirement_id, "canonical"),
                "rule_assertion_id": rule_id,
                "operator": operator,
                "semantic_entity_id": entity_id,
                "source": source.to_dict(),
                "evidence_ids": [evidence_id],
                "observation_ids": observation_ids,
                "claim_status": ClaimStatus.ACCEPTED.value,
            })
            assertion_ids.append(requirement_id)

        for observation_id in observation_ids:
            _link_semantic_observation(
                collector,
                spec["observation_paths"][observation_id],
                observation_id,
                relation["id"],
            )

        card_id = stable_id("semantic_card", entity_id)
        collector.add("projections/semantic_cards.jsonl", {
            **_base("semantic_card", card_id, "projection"),
            "source": source.to_dict(),
            "article_root": article_endpoint.to_dict(),
            "entity_id": entity_id,
            "semantic_type": semantic_type.value,
            "card_status": "SEMANTIC_READY",
            "family_ids": [family_id],
            "terms": terms,
            "assertion_ids": sorted(set(assertion_ids)),
            "coverage_keys": [coverage_key],
            "relation_predicate": predicate.value,
            "observation_ids": observation_ids,
            "label": label[:600],
            "runtime_wired": False,
        })
        members = bundle_members.setdefault((doc_id, article_root), set())
        members.update([entity_id, *assertion_ids])
        counts[semantic_type.value] += 1

    # Every current 조·항·호·목 receives a sparse landing card.  This is a
    # source-text projection only: it creates no legal entity or assertion and
    # therefore cannot manufacture legal meaning when observation extraction
    # has no output for a provision (for example a short 준용 clause).
    for doc_id in sorted(current_docs):
        view = index.docs.get(doc_id)
        if view is None:
            continue
        for node in sorted(view.nodes, key=lambda value: canonical_json_text([
            value.get("id"), value.get("level"), value.get("span"),
        ])):
            node_id = node.get("id")
            if node_id not in view.by_id:
                continue
            article_root = _article_root_or_none(view, node_id)
            if article_root is None:
                continue
            source = _endpoint(index, doc_id, node_id)
            article_endpoint = _endpoint(index, doc_id, article_root)
            body = view.section_text(node, cap=1600)
            path = view.path(node_id)
            label = body.strip() or str(
                node.get("title") or node.get("surface") or path
            )
            terms = _semantic_terms(view.name, path, label)
            if not terms:
                continue
            family_ids = _structure_family_hints(" ".join((path, label)))
            collector.add("projections/semantic_cards.jsonl", {
                **_base(
                    "semantic_card",
                    stable_id("semantic_card", "structure", doc_id, node_id),
                    "projection",
                ),
                "source": source.to_dict(),
                "article_root": article_endpoint.to_dict(),
                "entity_id": "",
                "semantic_type": "STRUCTURE_ONLY",
                "card_status": "STRUCTURE_ONLY",
                "family_ids": family_ids,
                "terms": terms,
                "assertion_ids": [],
                "coverage_keys": ["structure"],
                "relation_predicate": "",
                "observation_ids": [],
                "label": label[:600],
                "runtime_wired": False,
            })

    for coordinate, member_ids in sorted(bundle_members.items()):
        doc_id, article_root = coordinate
        rule_ids = sorted(item for item in member_ids if item.startswith("rule:"))
        if not rule_ids:
            continue
        collector.add("projections/rule_bundle_projections.jsonl", {
            **_base(
                "rule_bundle_projection",
                stable_id("rule_bundle", doc_id, article_root, sorted(member_ids)),
                "projection",
            ),
            "root_rule_id": rule_ids[0],
            "member_ids": sorted(member_ids),
            "article_root": _endpoint(index, doc_id, article_root).to_dict(),
            "runtime_wired": False,
        })
    _refresh_semantic_accounting(accounting, collector)
    return counts


def _compile_reference_relations(collector: _Collector, index: Index,
                                 assertion_by_fold: dict[str, list[str]]) -> tuple[dict, list[dict]]:
    raw_rows: list[tuple[str, dict, bool]] = []
    for doc_id, rows in index.ref_edges().items():
        raw_rows.extend((doc_id, row, False) for row in rows)
    raw_rows.extend((str(row.get("src_doc") or ""), row, True)
                    for row in index.cross_ref_edges())
    raw_rows.sort(key=lambda item: canonical_json_text([item[0], item[1], item[2]]))
    accepted_obs: list[str] = []; unresolved_obs: list[str] = []
    accepted_assertions: list[str] = []; obs_links: list[dict] = []
    for order, (src_doc, raw, cross) in enumerate(raw_rows):
        dst_doc = str(raw.get("dst_doc") or src_doc)
        src_node, dst_node = raw.get("src"), raw.get("dst")
        source_key = f"{order}:{content_sha256([src_doc, raw, cross])}"
        source_endpoint = (
            _endpoint(index, src_doc, src_node).to_dict()
            if src_doc in index.docs and src_node in index.docs[src_doc].by_id
            else None
        )
        target_endpoint = (
            _endpoint(index, dst_doc, dst_node).to_dict()
            if dst_doc in index.docs and dst_node in index.docs[dst_doc].by_id
            else None
        )
        valid = (src_doc in index.docs and src_node in index.docs[src_doc].by_id
                 and dst_doc in index.docs and dst_node in index.docs[dst_doc].by_id)
        if not valid:
            obs = _observation(collector, "observations/relation_inputs.jsonl",
                               "references", source_key, {"src_doc": src_doc, "cross": cross, **raw},
                               "unresolved", reason="endpoint_not_found", row_type="observation",
                               source=source_endpoint, target=target_endpoint)
            unresolved_obs.append(obs["id"])
            unresolved_id = stable_id("unresolved", obs["id"])
            _mark_unresolved(collector, obs["id"], unresolved_id)
            collector.add("observations/unresolved_relations.jsonl", {
                **_base("unresolved_relation", unresolved_id, "observation"),
                "legacy_id": source_key, "observation_id": obs["id"],
                "reason": "endpoint_not_found", "claim_status": ClaimStatus.UNRESOLVED.value,
                "source_kind": "references", "terminal_disposition": "unresolved",
            })
            continue
        rel = str(raw.get("rel") or "인용")
        legacy_kind = relations.REFERENCE_KINDS.get(rel, "REFERENCES")
        predicate = LEGACY_KIND_TO_PREDICATE[legacy_kind]
        obs = _observation(collector, "observations/relation_inputs.jsonl", "references",
                           source_key, {"src_doc": src_doc, "cross": cross, **raw}, "mapped",
                           row_type="observation")
        eid = _evidence(collector, index, src_doc, src_node, block_id=raw.get("block"),
                        kind=EvidenceKind.SOURCE_TEXT, method="reference-parser",
                        props={"relation": rel, "cross_document": cross})
        assertion = _relation_assertion(
            collector, index, predicate, src_doc, src_node, dst_doc, dst_node,
            [eid], [obs["id"]], legacy_kind=legacy_kind,
            props={k: v for k, v in raw.items() if k not in {"src", "dst"}})
        _link_observation(collector, obs["id"], assertion["id"])
        accepted_obs.append(obs["id"]); accepted_assertions.append(assertion["id"])
        src_root = relations.article_root(index.docs[src_doc], src_node)
        dst_root = relations.article_root(index.docs[dst_doc], dst_node)
        fold = _legacy_key(legacy_kind, src_doc, src_root, dst_doc, dst_root)
        assertion_by_fold.setdefault(fold, []).append(assertion["id"])
    # Link rows are emitted at acceptance time by ``_link_observation``.
    return ({"input_rows": len(raw_rows),
             "terminal_counts": {kind: ({"mapped": len(accepted_obs),
                                         "unresolved": len(unresolved_obs)}.get(kind, 0))
                                 for kind in _TERMINALS},
             "terminal_ids": {kind: ({"mapped": accepted_obs,
                                      "unresolved": unresolved_obs}.get(kind, []))
                              for kind in _TERMINALS},
             "accepted_ids": accepted_obs, "unresolved_ids": unresolved_obs,
             "candidate_ids": [], "accepted_assertion_ids": accepted_assertions}, raw_rows)


def _delegation_predicate(index: Index, edge: Mapping[str, Any]) -> RelationPredicate:
    kind = str(edge.get("kind") or "")
    if kind == "위임행정규칙":
        return RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE
    src = edge.get("src") or {}
    view = index.docs.get(str(src.get("doc_id") or ""))
    if kind == "시행규칙" and view is not None and view.kind not in {"law", "법률"}:
        return RelationPredicate.LEGISLATIVE_REDELEGATION
    return RelationPredicate.LEGISLATIVE_DELEGATION


def _compile_delegations(collector: _Collector, index: Index, delegation_blob: Mapping[str, Any],
                         assertion_by_fold: dict[str, list[str]],
                         allowed_folds: set[str]) -> dict:
    rows = list(delegation_blob.get("edges") or [])
    terminal_ids: dict[str, list[str]] = {kind: [] for kind in _TERMINALS}
    accepted_assertions: list[str] = []
    for order, edge in enumerate(rows):
        src, dst = edge.get("src") or {}, edge.get("dst") or {}
        src_doc, dst_doc = str(src.get("doc_id") or ""), str(dst.get("doc_id") or "")
        src_node, anchor_exact = _resolve_anchor(
            index, src_doc, str(src.get("anchor") or ""), src.get("node"))
        dst_node = dst.get("node")
        source_endpoint = (
            _endpoint(index, src_doc, src_node).to_dict()
            if src_doc in index.docs and src_node in index.docs[src_doc].by_id
            else None
        )
        target_endpoint = (
            _endpoint(index, dst_doc, dst_node).to_dict()
            if dst_doc in index.docs and dst_node in index.docs[dst_doc].by_id
            else None
        )
        source_key = f"{order}:{content_sha256(edge)}"
        payload = {**edge, "resolved_src_node": src_node, "resolved_dst_node": dst_node,
                   "anchor_resolution": "exact" if anchor_exact else "partial_or_fallback"}
        if str(edge.get("kind") or "") not in {"시행령", "시행규칙", "위임행정규칙"}:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "out_of_contract", row_type="observation",
                               reason="not_a_legislative_delegation_kind")
            terminal_ids["out_of_contract"].append(obs["id"])
            continue
        if not src_doc or not dst_doc:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "parse_error", row_type="observation",
                               reason="missing_document_identifier")
            terminal_ids["parse_error"].append(obs["id"])
            continue
        if (src_doc not in index.docs or src_node not in index.docs[src_doc].by_id
                or dst_doc not in index.docs):
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "unresolved", reason="endpoint_not_found",
                               row_type="observation", source=source_endpoint,
                               target=target_endpoint)
            terminal_ids["unresolved"].append(obs["id"])
            unresolved_id = stable_id("unresolved", obs["id"])
            _mark_unresolved(collector, obs["id"], unresolved_id)
            collector.add("observations/unresolved_relations.jsonl", {
                **_base("unresolved_relation", unresolved_id, "observation"),
                "legacy_id": source_key, "observation_id": obs["id"],
                "reason": "endpoint_not_found", "claim_status": ClaimStatus.UNRESOLVED.value,
                "source_kind": "delegation", "terminal_disposition": "unresolved",
            })
            continue
        if dst_node is None:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "support_only",
                               reason="document_target_has_no_exact_provision",
                               row_type="observation")
            terminal_ids["support_only"].append(obs["id"])
            continue
        if dst_node not in index.docs[dst_doc].by_id:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "unresolved", reason="target_unit_not_found",
                               row_type="observation", source=source_endpoint,
                               target=target_endpoint)
            terminal_ids["unresolved"].append(obs["id"])
            unresolved_id = stable_id("unresolved", obs["id"])
            _mark_unresolved(collector, obs["id"], unresolved_id)
            collector.add("observations/unresolved_relations.jsonl", {
                **_base("unresolved_relation", unresolved_id, "observation"),
                "legacy_id": source_key, "observation_id": obs["id"],
                "reason": "target_unit_not_found", "claim_status": ClaimStatus.UNRESOLVED.value,
                "source_kind": "delegation", "terminal_disposition": "unresolved",
            })
            continue
        if not anchor_exact:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "support_only", row_type="observation",
                               reason="official_anchor_not_fully_resolved_to_lower_unit")
            terminal_ids["support_only"].append(obs["id"])
            continue
        src_root = relations.article_root(index.docs[src_doc], src_node)
        dst_root = relations.article_root(index.docs[dst_doc], dst_node)
        fold_key = _legacy_key("DELEGATES_TO", src_doc, src_root, dst_doc, dst_root)
        if fold_key not in allowed_folds:
            obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                               source_key, payload, "suppressed", row_type="observation",
                               reason="not_present_in_current_relation_bundle")
            terminal_ids["suppressed"].append(obs["id"])
            continue
        obs = _observation(collector, "observations/relation_inputs.jsonl", "delegation",
                           source_key, payload, "mapped", row_type="observation")
        eid = _evidence(collector, index, src_doc, src_node, block_id=None,
                        kind=EvidenceKind.OFFICIAL_LINK, method="law.go.kr:lsDelegated",
                        props={"kind": edge.get("kind"), "link": edge.get("link", ""),
                               "anchor": src.get("anchor", "")})
        assertion = _relation_assertion(
            collector, index, _delegation_predicate(index, edge),
            src_doc, src_node, dst_doc, dst_node, [eid], [obs["id"]],
            legacy_kind="DELEGATES_TO", props={"official_edge": edge})
        _link_observation(collector, obs["id"], assertion["id"])
        terminal_ids["mapped"].append(obs["id"]); accepted_assertions.append(assertion["id"])
        assertion_by_fold.setdefault(
            _legacy_key("DELEGATES_TO", src_doc, src_root, dst_doc, dst_root), []).append(assertion["id"])
    return {"input_rows": len(rows),
            "terminal_counts": {kind: len(terminal_ids[kind]) for kind in _TERMINALS},
            "terminal_ids": terminal_ids,
            "accepted_ids": terminal_ids["mapped"],
            "unresolved_ids": [item for kind in _TERMINALS if kind != "mapped"
                               for item in terminal_ids[kind]],
            "candidate_ids": [], "accepted_assertion_ids": accepted_assertions}


def _compile_legacy_projection(collector: _Collector, index: Index, bundle,
                               assertion_by_fold: dict[str, list[str]]) -> dict[str, Any]:
    fallback_observations: list[str] = []
    fallback_assertions: list[str] = []
    for row in bundle.sections:
        legacy_key = _legacy_key(row.kind, row.src_doc, row.src_node,
                                 row.dst_doc, row.dst_node)
        provenance = row.props.get("provenance") or []
        assertion_ids = sorted(set(assertion_by_fold.get(legacy_key, [])))
        if not assertion_ids:
            obs = _observation(
                collector, "observations/relation_inputs.jsonl", "legacy_bundle_fallback",
                legacy_key, {"legacy_key": legacy_key, "kind": row.kind,
                             "src_doc": row.src_doc, "src_node": row.src_node,
                             "dst_doc": row.dst_doc, "dst_node": row.dst_node,
                             "props": row.props}, "mapped", row_type="observation",
                reason="compatibility_assertion_for_uncovered_legacy_fold")
            predicate = LEGACY_KIND_TO_PREDICATE.get(row.kind, RelationPredicate.REFERENCES)
            eid = _evidence(collector, index, row.src_doc, row.src_node,
                            block_id=row.props.get("block"),
                            kind=EvidenceKind.DETERMINISTIC_DERIVATION,
                            method="legacy-relation-bundle-compatibility",
                            props={"legacy_key": legacy_key, "provenance": provenance})
            source_is_article = bool(_ARTICLE.fullmatch(str(
                (index.docs[row.src_doc].by_id.get(row.src_node) or {}).get("surface") or "").strip()))
            target_is_article = bool(_ARTICLE.fullmatch(str(
                (index.docs[row.dst_doc].by_id.get(row.dst_node) or {}).get("surface") or "").strip()))
            fallback_precision = (Precision.ARTICLE_FALLBACK
                                  if source_is_article and target_is_article
                                  else Precision.EXACT_UNIT)
            assertion = _relation_assertion(
                collector, index, predicate, row.src_doc, row.src_node,
                row.dst_doc, row.dst_node, [eid], [obs["id"]],
                precision=fallback_precision,
                resolution=("ARTICLE_FALLBACK" if fallback_precision == Precision.ARTICLE_FALLBACK
                            else "LEGACY_UNIT_FALLBACK"),
                legacy_kind=row.kind,
                props={"legacy_key": legacy_key, "legacy_props": row.props})
            assertion_ids = [assertion["id"]]
            assertion_by_fold[legacy_key] = assertion_ids
            _link_observation(collector, obs["id"], assertion["id"])
            fallback_observations.append(obs["id"])
            fallback_assertions.append(assertion["id"])
        oracle = {
            **_base("legacy_relation_view", stable_id("legacy_oracle", legacy_key), "projection"),
            "relation_assertion_id": assertion_ids[0], "legacy_kind": row.kind,
            "legacy_key": legacy_key, "kind": row.kind,
            "src_doc": row.src_doc, "src_node": row.src_node,
            "dst_doc": row.dst_doc, "dst_node": row.dst_node,
            "mandatory": row.mandatory, "provenance": provenance, "props": row.props,
        }
        collector.add("projections/legacy_section_relations.jsonl", oracle)
        compatibility_id = stable_id("compatibility", legacy_key, assertion_ids)
        collector.add("projections/relation_compatibility.jsonl", {
            **_base("compatibility", compatibility_id, "projection"),
            "compatibility_kind": "LEGACY_SECTION_FOLD",
            "fold_key": legacy_key, "legacy_key": legacy_key, "legacy_kind": row.kind,
            "assertion_ids": assertion_ids, "mandatory": row.mandatory,
            "provenance": provenance, "runtime_wired": False,
        })
        for assertion_id in assertion_ids:
            closure_predicate = LEGACY_KIND_TO_PREDICATE.get(
                row.kind, RelationPredicate.REFERENCES)
            collector.add("projections/closure_projections.jsonl", {
                **_base("closure_projection",
                        stable_id("closure", legacy_key, assertion_id), "projection"),
                "relation_assertion_id": assertion_id,
                "source_article_root_id": _unit_id(row.src_doc, row.src_node),
                "legacy_key": legacy_key,
                "closure_mode": (
                    ClosureMode.REQUIRED_WHEN_ACTIVATED.value
                    if row.mandatory
                    else DEFAULT_CLOSURE_POLICY[closure_predicate].value
                ),
                "legacy_mandatory": row.mandatory,
                "activation_policy": "query_conditional_future_policy",
                "runtime_wired": False,
            })
    return {
        "input_rows": len(fallback_observations),
        "terminal_counts": {kind: len(fallback_observations) if kind == "mapped" else 0
                            for kind in _TERMINALS},
        "terminal_ids": {kind: fallback_observations if kind == "mapped" else []
                         for kind in _TERMINALS},
        "accepted_ids": fallback_observations, "unresolved_ids": [], "candidate_ids": [],
        "accepted_assertion_ids": fallback_assertions,
    }


def _update_cards(collector: _Collector, cards: list[dict]) -> None:
    unit_to_root = {
        str(row["id"]): str(row.get("article_root_id") or "")
        for row in collector.rows.get("canonical/structural_units.jsonl", [])
    }
    cards_by_root = {str(card["article_root_id"]): card for card in cards}
    frame_docs = {
        str((row.get("source") or {}).get("selector", {}).get("document_id") or "")
        for row in collector.rows.get("observations/frames.jsonl", [])
    }

    for card in cards:
        card["facets"] = {
            "definition_observation_ids": [],
            "frame_observation_ids": [],
            "requirement_observation_ids": [],
            "legacy_rule_assertion_ids": [],
            "relation_assertion_ids": [],
            "unresolved_relation_ids": [],
        }
        card["relation_ports"] = {
            "outgoing_projection_ids": [],
            "incoming_projection_ids": [],
        }

    def attach(path: str, facet: str) -> None:
        for row in collector.rows.get(path, []):
            ref_id = str((row.get("source") or {}).get("ref_id") or "")
            root_id = unit_to_root.get(ref_id, "")
            card = cards_by_root.get(root_id)
            if card is not None:
                card["facets"][facet].append(str(row["id"]))

    attach("observations/definitions.jsonl", "definition_observation_ids")
    attach("observations/definition_aliases.jsonl", "definition_observation_ids")
    attach("observations/frames.jsonl", "frame_observation_ids")
    attach("observations/requirements.jsonl", "requirement_observation_ids")
    attach("canonical/legacy_assertions.jsonl", "legacy_rule_assertion_ids")

    relation_inputs = {
        str(row["id"]): row
        for row in collector.rows.get("observations/relation_inputs.jsonl", [])
    }
    for unresolved in collector.rows.get("observations/unresolved_relations.jsonl", []):
        observation = relation_inputs.get(str(unresolved.get("observation_id") or ""))
        source = (observation or {}).get("source") or {}
        if source.get("precision") not in {
            Precision.EXACT_SPAN.value,
            Precision.EXACT_UNIT.value,
        }:
            continue
        ref_id = str(source.get("ref_id") or "")
        card = cards_by_root.get(unit_to_root.get(ref_id, ""))
        if card is not None:
            card["facets"]["unresolved_relation_ids"].append(str(unresolved["id"]))

    assertions = {
        str(row["id"]): row
        for row in collector.rows.get("canonical/relation_assertions.jsonl", [])
    }
    for projection in collector.rows.get("projections/closure_projections.jsonl", []):
        assertion_id = str(projection.get("relation_assertion_id") or "")
        assertion = assertions.get(assertion_id)
        if assertion is None:
            continue
        source_ref = str((assertion.get("source") or {}).get("ref_id") or "")
        target_ref = str((assertion.get("target") or {}).get("ref_id") or "")
        source_card = cards_by_root.get(unit_to_root.get(source_ref, ""))
        target_card = cards_by_root.get(unit_to_root.get(target_ref, ""))
        projection_id = str(projection["id"])
        if source_card is not None:
            source_card["relation_ports"]["outgoing_projection_ids"].append(projection_id)
            source_card["facets"]["relation_assertion_ids"].append(assertion_id)
        if target_card is not None:
            target_card["relation_ports"]["incoming_projection_ids"].append(projection_id)
            target_card["facets"]["relation_assertion_ids"].append(assertion_id)

    for card in cards:
        for values in card["facets"].values():
            values[:] = sorted(set(values))
        for values in card["relation_ports"].values():
            values[:] = sorted(set(values))
        coverage = card["coverage"]
        coverage["definitions"] = len(card["facets"]["definition_observation_ids"])
        coverage["frames"] = len(card["facets"]["frame_observation_ids"])
        coverage["requirements"] = len(card["facets"]["requirement_observation_ids"])
        coverage["legacy_rule_assertions"] = len(
            card["facets"]["legacy_rule_assertion_ids"])
        coverage["accepted_relations"] = len(card["facets"]["relation_assertion_ids"])
        coverage["unresolved_relations"] = len(
            card["facets"]["unresolved_relation_ids"])
        coverage["outgoing_relations"] = len(
            card["relation_ports"]["outgoing_projection_ids"])
        coverage["incoming_relations"] = len(
            card["relation_ports"]["incoming_projection_ids"])
        doc_id = str(card["article_root"]["selector"]["document_id"])
        coverage["frame_status"] = "AVAILABLE" if doc_id in frame_docs else "NOT_EXTRACTED"
        coverage["semantic_status"] = (
            "ENRICHED" if any(coverage[name] for name in (
                "definitions", "frames", "requirements",
                "legacy_rule_assertions", "accepted_relations")) else "SPARSE"
        )
        collector.add("projections/provision_cards.jsonl", card)


def _write_json_artifact(root: Path, relpath: str, value: Mapping[str, Any],
                         artifacts: dict[str, dict[str, Any]]) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json_text(value) + "\n").encode("utf-8")
    target.write_bytes(payload)
    artifacts[relpath] = {"path": relpath, "sha256": sha256_hex(payload),
                          "bytes": len(payload), "rows": 1, "format": "json"}


def _same_generation(existing: Path, staging: Path, manifest: Mapping[str, Any]) -> bool:
    old_manifest = existing / "manifest.json"
    if not old_manifest.is_file():
        return False
    try:
        old = _json(old_manifest)
    except Exception:
        return False
    if old != manifest:
        return False
    for relpath, meta in manifest.get("artifacts", {}).items():
        path = existing / relpath
        if not path.is_file() or sha256_hex(path.read_bytes()) != meta.get("sha256"):
            return False
    return True


def build_generation(config: BuildConfig | None = None) -> BuildResult:
    """Compile and atomically publish one immutable sidecar generation."""
    config = (config or BuildConfig()).resolved()
    hashes = _source_hashes(config)
    law_index = _json(config.law_index_file)
    authority_generation = str(law_index.get("generation_id") or "")
    authority_as_of = str(law_index.get("as_of") or "")
    generation_digest = content_sha256({
        "schema_version": SCHEMA_VERSION,
        "compiler_contract": COMPILER_CONTRACT_VERSION,
        "projection_policy": PROJECTION_POLICY_VERSION,
        "authority_generation": authority_generation,
        "source_hashes": hashes,
    })
    generation_id = f"lgv1-{generation_digest[:24]}"
    generations = config.output_root / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{generation_id}.", dir=generations))
    try:
        index = _load_index(config)
        if index.authority_generation != authority_generation:
            raise RuntimeError("Index authority generation does not match explicit law_index")
        current_docs = set(index.default_scope() or index.docs)
        collector = _Collector(staging, generation_id, authority_generation)
        _compile_source_inventory(collector, config, hashes)
        _units, cards = _compile_structure(collector, index, current_docs)
        canonical = _json(config.canonical_file)
        _compile_legacy(collector, canonical, index)
        bundle = relations.build(
            index, delegation_file=config.delegation_file,
            law_index_file=config.law_index_file, include_requirements=True,
            include_definition_edges=True, use_cache=False)
        accounting = _compile_candidate_observations(collector, config, index, bundle)
        semantic_counts = _compile_semantic_entities(
            collector, index, current_docs, accounting,
        )
        assertion_by_fold: dict[str, list[str]] = {}
        accounting["references"], _raw_refs = _compile_reference_relations(
            collector, index, assertion_by_fold)
        allowed_delegation_folds = {
            _legacy_key(row.kind, row.src_doc, row.src_node, row.dst_doc, row.dst_node)
            for row in bundle.sections if row.kind == "DELEGATES_TO"
        }
        accounting["delegation"] = _compile_delegations(
            collector, index, _json(config.delegation_file), assertion_by_fold,
            allowed_delegation_folds)
        accounting["legacy_bundle_fallback"] = _compile_legacy_projection(
            collector, index, bundle, assertion_by_fold)
        _update_cards(collector, cards)
        artifacts = collector.write()

        source_accounting = {
            "schema_version": SCHEMA_VERSION, "generation_id": generation_id,
            "authority_generation": authority_generation,
            "sources": accounting,
            "totals": {
                "input_rows": sum(row["input_rows"] for row in accounting.values()),
                "terminal_counts": {
                    kind: sum(row["terminal_counts"].get(kind, 0)
                              for row in accounting.values())
                    for kind in _TERMINALS
                },
            },
        }
        _write_json_artifact(staging, "source_accounting.json", source_accounting, artifacts)
        manifest = {
            "schema_version": SCHEMA_VERSION, "generation_id": generation_id,
            "authority_generation": authority_generation, "authority_as_of": authority_as_of,
            "compiler_contract": COMPILER_CONTRACT_VERSION,
            "projection_policy": PROJECTION_POLICY_VERSION,
            "runtime_wired": False,
            "source_hashes": hashes, "source_aggregate_sha256": content_sha256(hashes),
            "artifacts": dict(sorted(artifacts.items())),
            "counts": {
                "documents": len(index.docs),
                "current_documents": len(current_docs),
                "structural_units": sum(len(view.nodes) for view in index.docs.values()),
                "current_article_roots": len(cards),
                "semantic_entities": sum(semantic_counts.values()),
                "semantic_entities_by_type": dict(sorted(semantic_counts.items())),
                "semantic_cards_by_status": dict(sorted(Counter(
                    str(row.get("card_status") or "SEMANTIC_READY")
                    for row in collector.rows.get(
                        "projections/semantic_cards.jsonl", []
                    )
                ).items())),
            },
        }
        manifest["content_sha256"] = content_sha256(manifest)
        (staging / "manifest.json").write_text(
            canonical_json_text(manifest) + "\n", encoding="utf-8", newline="\n")

        # Validation deliberately reparses the emitted sidecar rather than
        # trusting compiler memory.  Release that compiler object graph first
        # so full-corpus publication does not retain both copies at once.
        del collector, bundle, canonical, assertion_by_fold, allowed_delegation_folds
        del _units, _raw_refs
        del cards, index, accounting, source_accounting, semantic_counts
        gc.collect()

        from .validation import validate_generation
        validation_report = validate_generation(
            staging, structure_store=config.structure_store, write_summary=True)
        validation_report.raise_for_errors()

        final = generations / generation_id
        reused = False
        if final.exists():
            if not _same_generation(final, staging, manifest):
                raise RuntimeError(f"immutable generation conflict: {final}")
            reused = True
            shutil.rmtree(staging)
        else:
            os.replace(staging, final)
        current_path: Path | None = None
        if config.publish_current:
            pointer = {
                "schema_version": SCHEMA_VERSION, "generation_id": generation_id,
                "authority_generation": authority_generation,
                "projection_policy": PROJECTION_POLICY_VERSION,
                "manifest": f"generations/{generation_id}/manifest.json",
                "content_sha256": manifest["content_sha256"], "runtime_wired": False,
            }
            config.output_root.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".CURRENT.", suffix=".json",
                                             dir=config.output_root)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(canonical_json_text(pointer) + "\n")
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(temp_name, config.output_root / "CURRENT.json")
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            current_path = config.output_root / "CURRENT.json"
        return BuildResult(generation_id, final, final / "manifest.json",
                           str(manifest["content_sha256"]), reused, current_path)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


__all__ = [
    "COMPILER_CONTRACT_VERSION", "PROJECTION_POLICY_VERSION",
    "BuildConfig", "BuildResult", "build_generation",
]
