"""현재 RAG 파생물을 하나의 provenance-preserving 지식 그래프로 조립한다."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lawrag.core.rag import definitions, relations, tags
from lawrag.core.rag.index import Index, store_path, terms_path

from .canonical import CanonicalRegistry
from .model import Edge, Node, lexeme_id, normalize_surface, stable_id
from .store import GraphStore
from .tier1 import Tier1Registry
from .uncertainty import claim_metadata, graph_contract


SLOTS = {
    "actor": "HAS_ACTOR",
    "act": "HAS_ACTION",
    "target": "HAS_TARGET",
    "object": "HAS_OBJECT",
}

REQUIREMENT_KINDS = {
    "CONDITION": "HAS_CONDITION",
    "EXCEPTION": "HAS_EXCEPTION",
    "TIME": "HAS_TIME_CONSTRAINT",
    "QUANTITY": "HAS_QUANTITATIVE_CONSTRAINT",
    "METHOD": "HAS_METHOD",
    "EFFECT": "HAS_EFFECT",
}

REQUIREMENT_CANDIDATE_KINDS = {
    "CONDITION": "MAY_CONDITION_OF",
    "EXCEPTION": "MAY_EXCEPTION_TO",
    "TIME": "MAY_TIME_LIMIT_OF",
    "QUANTITY": "MAY_QUANTITY_LIMIT_OF",
    "METHOD": "MAY_METHOD_OF",
    "EFFECT": "MAY_EFFECT_OF",
}

def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not row.get("empty"):
            out.append(row)
    return out


def document_id(doc_id: str) -> str:
    return f"document:{doc_id}"


def section_id(doc_id: str, node_id: object) -> str:
    return f"section:{doc_id}:{node_id}"


def block_id(doc_id: str, block_idx: object) -> str:
    return f"block:{doc_id}:{block_idx}"


def _ordinal(node: dict) -> int | None:
    value = node.get("ordinal")
    if isinstance(value, list) and value and isinstance(value[-1], int):
        return value[-1]
    if isinstance(value, int):
        return value
    return None


def compact_locator(view, node: dict) -> str:
    """제1조 + ③ + 2. + 가. → 제1조제3항제2호가목."""
    chain, seen = [], set()
    cur = node
    while cur is not None and cur.get("id") not in seen:
        seen.add(cur.get("id"))
        chain.append(cur)
        cur = view.by_id.get(cur.get("parent"))
    parts = []
    for item in reversed(chain):
        surface = (item.get("surface") or "").strip()
        family = str(item.get("family") or "")
        order = _ordinal(item)
        if re.fullmatch(r"제\d+(?:-\d+)?조(?:의\d+)?", surface):
            parts.append(surface)
        elif family == "circled" and order is not None:
            parts.append(f"제{order}항")
        elif family.startswith("dot_number") and order is not None:
            parts.append(f"제{order}호")
        elif re.fullmatch(r"[가-힣][.)]", surface):
            parts.append(f"{surface[0]}목")
    return "".join(parts)


class GraphBuilder:
    """여러 파생 파일을 합치되 원천 파일은 건드리지 않는 재생성 가능한 빌더."""

    def __init__(self, index: Index, *, data_dir: str | Path | None = None,
                 registry: CanonicalRegistry | None = None,
                 glossary_path: str | Path | None = None):
        self.index = index
        self.data_dir = Path(data_dir or store_path().parent)
        self.glossary_path = Path(glossary_path or terms_path())
        self.registry = registry or CanonicalRegistry.load(
            registry_path=self.data_dir / "domain_graph" / "canonical.json",
            glossary_path=self.glossary_path,
        )
        self.tier1 = Tier1Registry.load(
            self.data_dir / "domain_graph" / "canonical.json")
        self.store: GraphStore
        self.node_ids: set[str] = set()
        self.stats = {"documents": 0, "sections": 0, "blocks": 0, "frames": 0,
                      "mentions": 0, "relations": 0, "requirements": 0,
                      "requirement_candidate_bindings": 0,
                      "references": 0, "unresolved_references": 0}
        self.frames_by_source: dict[tuple[str, object], list[str]] = {}
        self.requirements_by_source: dict[tuple[str, object], list[tuple[str, str]]] = {}

    def _node(self, node: Node) -> str:
        self.store.put_node(node)
        self.node_ids.add(node.id)
        return node.id

    def _edge(self, kind: str, src: str, dst: str, *, key: object = "",
              props: dict | None = None) -> None:
        if src in self.node_ids and dst in self.node_ids:
            self.store.put_edge(Edge.make(kind, src, dst, key=key, props=props))

    def _lexeme(self, surface: str, *, doc_id: str = "") -> str | None:
        surface = str(surface or "").strip()
        if not normalize_surface(surface):
            return None
        lid = lexeme_id(surface)
        self._node(Node(lid, "Lexeme", surface, {
            "normalized": normalize_surface(surface), "knowledge_grade": 2,
        }))
        for concept in self.registry.match(surface, doc_id=doc_id):
            self._node(concept.node())
            scope_key = doc_id if concept.scope_docs else ""
            self._edge("NORMALIZES_TO", lid, concept.id,
                       key=(concept.id, scope_key), props={
                "source": concept.source,
                "status": concept.status,
                "confidence": concept.confidence,
                "doc_id": scope_key,
            })
        return lid

    def _mention(self, owner: str, surface: str, *, source: str, role: str,
                 doc_id: str, node_id: object, occurrence: object) -> str | None:
        surface = str(surface or "").strip()
        lid = self._lexeme(surface, doc_id=doc_id)
        if lid is None:
            return None
        mid = stable_id("mention", source, owner, role, occurrence, surface)
        self._node(Node(mid, "Mention", surface, {
            "surface": surface, "source": source, "role": role,
            "doc_id": doc_id, "node": node_id, "knowledge_grade": 3,
        }))
        self._edge("HAS_MENTION", owner, mid, key=(source, role, occurrence))
        self._edge("HAS_LEXEME", mid, lid, props={"role": role})
        self.stats["mentions"] += 1
        return mid

    def _locator(self, target: str, surface: str, *, doc_id: str, role: str) -> None:
        lid = self._lexeme(surface, doc_id=doc_id)
        if lid:
            self._edge("DENOTES", lid, target, key=(doc_id, role, target), props={
                "doc_id": doc_id, "role": role,
            })

    def build(self, output: str | Path, *, doc_ids: Iterable[str] | None = None,
              include_blocks: bool = True, include_derived: bool = True) -> dict:
        output = Path(output)
        self.node_ids = set()
        self.stats = {"documents": 0, "sections": 0, "blocks": 0, "frames": 0,
                      "mentions": 0, "relations": 0, "requirements": 0,
                      "requirement_candidate_bindings": 0,
                      "references": 0, "unresolved_references": 0}
        self.frames_by_source = {}
        self.requirements_by_source = {}
        # 기본 그래프는 authority/default scope의 현행 진입판만 발행한다. 구판과
        # 회신 당시 역사 스냅샷은 structure에 보존하되 현재 관계망에 섞지 않는다.
        selected = set(doc_ids or self.index.scoped(None).entry_docs)
        selected &= set(self.index.docs)
        tmp = output.with_name(f".{output.name}.building")
        if tmp.exists():
            tmp.unlink()
        self.store = GraphStore(tmp)
        try:
            with self.store.transaction():
                for concept in self.registry.entries:
                    self._node(concept.node())
                for did in sorted(selected):
                    self._build_document(did, include_blocks=include_blocks,
                                         include_derived=include_derived)
                self._aliases(selected)
                if include_derived:
                    relation_bundle = relations.build(
                        self.index,
                        delegation_file=self.data_dir / "delegation.json",
                        law_index_file=self.data_dir / "law_index.json",
                        include_requirements=True, use_cache=False)
                    self._relations(selected, relation_bundle)
                    self._pending_references(selected)
                    self._requirements(selected, relation_bundle)
                    self._graph_relations(selected, relation_bundle)
                    self._glossary_occurrences(selected)
                # 1급은 모든 파생물보다 마지막에 발행한다. 같은 Concept가 glossary
                # 파생(2급)에도 있으면 ``put_node``가 뒤의 값을 정본으로 삼기 때문에,
                # 예전 순서에서는 승인된 1급 3,218개가 후속 _lexeme 호출에 의해 다시
                # 2급 props로 덮였다. 마지막 발행은 단순 우선순위가 아니라
                # "승인 정본이 파생물을 이긴다"는 등급 불변식이다.
                self._tier1_knowledge(selected)
                self.store.set_meta("schema_version", 1)
                self.store.set_meta("uncertainty_contract", graph_contract())
                self.store.set_meta("built_at", datetime.now(timezone.utc).isoformat())
                self.store.set_meta("authority_generation", self.index.authority_generation)
                self.store.set_meta("authority_as_of", self.index.authority_as_of)
                self.store.set_meta("canonical_documents",
                                    sorted(self.index.canonical_doc_ids or ()))
                self.store.set_meta("documents", sorted(selected))
                self.store.set_meta("stats", self.stats)
            counts = self.store.counts()
        finally:
            self.store.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, output)
        return {**self.stats, "counts": counts, "output": str(output)}

    def _tier1_knowledge(self, selected: set[str]) -> None:
        """검증·승인된 항목만 1급 label/edge로 발행한다."""
        active = self.tier1.active_concepts
        # 먼저 모든 표면형을 만든다. _lexeme는 registry matching 과정에서 Concept
        # 노드를 다시 쓸 수 있으므로, 정본 Concept 발행은 표면형 생성이 전부 끝난
        # 뒤 별도 pass에서 해야 review_state가 겹친 alias 때문에 사라지지 않는다.
        surface_ids_by_concept = {
            concept.id: [self._lexeme(surface) for surface in concept.surfaces]
            for concept in active.values()
        }
        for concept in active.values():
            self._node(Node(concept.id, "Concept", concept.label, {
                "concept_type": concept.type, "status": concept.status,
                "knowledge_grade": 1, "aliases": list(concept.aliases),
                "definitions": list(concept.definitions), "examples": list(concept.examples),
                "negative_aliases": list(concept.negative_aliases),
                "scope_docs": list(concept.scope_docs), "version": concept.version,
                "approved_by": concept.approved_by, "source": "tier1_registry",
                **claim_metadata(
                    evidence_type=concept.evidence_type or "registry_declaration",
                    claim_status="active", approved_by=concept.approved_by,
                    explicit_review_state=concept.review_state),
            }))
        for concept in active.values():
            for lid in surface_ids_by_concept[concept.id]:
                if lid:
                    self._edge("NORMALIZES_TO", lid, concept.id,
                               key=(concept.id, "tier1"), props={
                                   "source": "tier1_registry", "status": "active",
                                   "knowledge_grade": 1,
                                   **claim_metadata(
                                       evidence_type="registry_surface_mapping",
                                       claim_status="active",
                                       approved_by=concept.approved_by,
                                       explicit_review_state=concept.review_state),
                               })
        for relation in self.tier1.active_relations:
            self._edge(relation.type, relation.src, relation.dst, key=relation.id, props={
                "registry_id": relation.id, "status": relation.status,
                "knowledge_grade": 1, "confidence": relation.confidence,
                "approved_by": relation.approved_by, "evidence": list(relation.evidence),
                **claim_metadata(
                    evidence_type=relation.evidence_type or "cited_semantic_relation",
                    claim_status="active", approved_by=relation.approved_by,
                    explicit_review_state=relation.review_state,
                    confidence=relation.confidence),
            })
        for assertion in self.tier1.active_assertions:
            doc_id, node = assertion.source["doc_id"], assertion.source["node"]
            source = section_id(doc_id, node)
            if doc_id not in selected or source not in self.node_ids:
                continue
            aid = assertion.id if assertion.id.startswith("assertion:") \
                else f"assertion:{assertion.id}"
            self._node(Node(aid, "Assertion", assertion.note or assertion.id, {
                "registry_id": assertion.id, "status": assertion.status,
                "knowledge_grade": 1, "confidence": assertion.confidence,
                "approved_by": assertion.approved_by, "version": assertion.version,
                "source": assertion.source, "query_cues": list(assertion.query_cues),
                **claim_metadata(
                    evidence_type=assertion.evidence_type or "assertion_source_coordinate",
                    claim_status="active", approved_by=assertion.approved_by,
                    explicit_review_state=assertion.review_state,
                    confidence=assertion.confidence),
            }))
            for role, concept_ids in assertion.roles.items():
                for pos, cid in enumerate(concept_ids):
                    self._edge(role, aid, cid, key=(role, pos))
            self._edge("SUPPORTED_BY", aid, source, props={"source": assertion.source})
            frame_id = str(assertion.source.get("frame_id") or "")
            if frame_id and frame_id in self.node_ids:
                # 이 간선은 의미 일치 주장이 아니라 생성 계보만 표현한다.
                self._edge("DERIVED_FROM_FRAME", aid, frame_id,
                           key=assertion.id, props=claim_metadata(
                               evidence_type="recorded_frame_lineage",
                               claim_status="observed",
                               approved_by=assertion.approved_by,
                               explicit_review_state=assertion.review_state,
                               consumer_policy="lineage_only"))
                source_key = (doc_id, node)
                alternatives = len(self.frames_by_source.get(source_key, ()))
                if alternatives != 1:
                    continue
                for rid, requirement_kind in self.requirements_by_source.get(source_key, ()):
                    self._edge(
                        REQUIREMENT_CANDIDATE_KINDS[requirement_kind], rid, aid,
                        key=(assertion.id, requirement_kind),
                        props=self._requirement_binding_props(
                            doc_id, node, frame_id, alternatives,
                            target_kind="Assertion"))
                    self.stats["requirement_candidate_bindings"] += 1

    def _build_document(self, doc_id: str, *, include_blocks: bool,
                        include_derived: bool) -> None:
        view = self.index.docs[doc_id]
        did = self._node(Node(document_id(doc_id), "Document", view.name, {
            "doc_id": doc_id, "name": view.name, "kind": view.kind,
            "scope_kind": view.scope_kind, "folder": view.folder, "status": view.status,
            "series": view.series, "version": view.version,
            "enforce": view.enforce, "revised": view.revised,
        }))
        self.stats["documents"] += 1
        self._locator(did, view.name, doc_id=doc_id, role="document_name")

        for node in view.nodes:
            nid = section_id(doc_id, node.get("id"))
            label = view.path(node.get("id")) or (node.get("title") or node.get("surface") or "")
            props = {k: v for k, v in node.items() if k not in {"attachments", "extent"}}
            props.update({"doc_id": doc_id, "path": view.path(node.get("id")),
                          "compact_locator": compact_locator(view, node)})
            self._node(Node(nid, "Section", label, props))
            self._edge("HAS_SECTION", did, nid, key=node.get("id"))
            self.stats["sections"] += 1
        for node in view.nodes:
            nid = section_id(doc_id, node.get("id"))
            parent = node.get("parent")
            if parent is not None:
                self._edge("PARENT_OF", section_id(doc_id, parent), nid)
            surfaces = [
                ((node.get("surface") or "") + " " + (node.get("title") or "")).strip(),
                node.get("title") or "", view.path(node.get("id")),
                compact_locator(view, node),
            ]
            compact = compact_locator(view, node)
            if compact:
                surfaces.append(f"{view.name} {compact}")
            for surface in dict.fromkeys(s for s in surfaces if str(s).strip()):
                self._locator(nid, str(surface), doc_id=doc_id, role="section_locator")

        if include_blocks:
            for block in view.blocks:
                bid = self._node(Node(block_id(doc_id, block.get("idx")), "TextBlock",
                                      (block.get("text") or "")[:120], {
                    **block, "doc_id": doc_id,
                }))
                owner = block.get("node")
                if owner is None:
                    found = view.owner(block.get("idx"))
                    owner = found.get("id") if found else None
                if owner is not None:
                    self._edge("CONTAINS_BLOCK", section_id(doc_id, owner), bid,
                               key=block.get("idx"))
                self.stats["blocks"] += 1

        if not include_derived:
            return
        self._frames(doc_id, view)
        self._definitions(doc_id, view)
        self._taxonomy(doc_id)
        self._tags_and_quantities(doc_id, view)

    def _frames(self, doc_id: str, view) -> None:
        rows = _read_jsonl(self.data_dir / "frames" / f"{doc_id}.jsonl")
        for ordinal, row in enumerate(rows):
            node = row.get("node")
            if node is None or node not in view.by_id:
                continue
            fid = self._node(Node(stable_id("frame", doc_id, row.get("jo"), node, ordinal),
                                  "Frame", row.get("act") or row.get("actor") or "frame", {
                "doc_id": doc_id, "jo": row.get("jo"), "node": node,
                "mode": row.get("mode", ""), "function": row.get("function", ""),
                "proviso": bool(row.get("proviso")), "extractor": "llm",
            }))
            sid = section_id(doc_id, node)
            self.frames_by_source.setdefault((doc_id, node), []).append(fid)
            self._edge("HAS_FRAME", sid, fid, key=ordinal)
            jo = row.get("jo")
            if jo in view.by_id and jo != node:
                self._edge("IN_ARTICLE", fid, section_id(doc_id, jo))
            for field, relation in SLOTS.items():
                mid = self._mention(fid, row.get(field, ""), source="frame", role=field,
                                    doc_id=doc_id, node_id=node, occurrence=ordinal)
                if mid:
                    self._edge(relation, fid, mid, key=field)
            for axis in ("mode", "function"):
                value = str(row.get(axis) or "").strip()
                if value:
                    cid = self._node(Node(stable_id("frame_class", axis, value),
                                          "FrameClass", value, {"axis": axis}))
                    self._edge("HAS_CLASS", fid, cid, key=axis, props={"axis": axis})
            self.stats["frames"] += 1

    def _definitions(self, doc_id: str, view) -> None:
        for ordinal, row in enumerate(definitions.defs(view)):
            node = row.get("node")
            if node not in view.by_id:
                continue
            sid = section_id(doc_id, node)
            mid = self._mention(sid, row.get("term", ""), source="definition",
                                role="defined_term", doc_id=doc_id,
                                node_id=node, occurrence=ordinal)
            if mid:
                lid = lexeme_id(row["term"])
                self._edge("DEFINES", sid, lid, key=(node, ordinal), props={
                    "kind": row.get("kind", ""), "scope": row.get("scope", ""),
                    "scope_root": row.get("scope_root"), "jo": row.get("jo"),
                    "mention": mid,
                })

    def _taxonomy(self, doc_id: str) -> None:
        rows = _read_jsonl(self.data_dir / "taxonomy" / f"{doc_id}.jsonl")
        for ordinal, row in enumerate(rows):
            node = row.get("node")
            owner = section_id(doc_id, node)
            if owner not in self.node_ids:
                continue
            term_mention = self._mention(
                owner, row.get("term", ""), source="taxonomy", role="taxonomy_term",
                doc_id=doc_id, node_id=node, occurrence=(ordinal, "term"))
            term = lexeme_id(row.get("term", "")) if term_mention else None
            if not term:
                continue
            provenance = {"doc_id": doc_id, "node": row.get("node"),
                          "jo": row.get("jo"), "source": "taxonomy_llm",
                          "term_mention": term_mention}
            for idx, surface in enumerate(row.get("hyponyms", [])):
                mention = self._mention(
                    owner, surface, source="taxonomy", role="hyponym",
                    doc_id=doc_id, node_id=node, occurrence=(ordinal, "hypo", idx))
                if mention:
                    child = lexeme_id(surface)
                    self._edge("IS_A", child, term, key=(ordinal, idx, "hypo"),
                               props={**provenance, "relation_mention": mention})
            for idx, surface in enumerate(row.get("hypernyms", [])):
                mention = self._mention(
                    owner, surface, source="taxonomy", role="hypernym",
                    doc_id=doc_id, node_id=node, occurrence=(ordinal, "hyper", idx))
                if mention:
                    parent = lexeme_id(surface)
                    self._edge("IS_A", term, parent, key=(ordinal, idx, "hyper"),
                               props={**provenance, "relation_mention": mention})

    def _tags_and_quantities(self, doc_id: str, view) -> None:
        for node in view.nodes:
            sid = section_id(doc_id, node.get("id"))
            marks = tags.node_marks(view, node.get("id"))
            for mark in marks:
                tid = self._node(Node(stable_id("tag", mark), "Tag", mark, {}))
                self._edge("HAS_TAG", sid, tid, key=mark)
            span = node.get("span") or [0, 0]
            # 큰 장·편에서 자손의 수치를 중복 복제하지 않는다.
            if "정량" not in marks or max(0, span[1] - span[0]) > 16:
                continue
            for ordinal, rule in enumerate(tags.quant_rules(view, node.get("id"))):
                qid = self._node(Node(stable_id("quantity", doc_id, node.get("id"), ordinal,
                                                rule.get("표기")), "Quantity",
                                      rule.get("표기", ""), {**rule, "doc_id": doc_id,
                                                               "node": node.get("id")}))
                self._edge("HAS_QUANTITY", sid, qid, key=ordinal)
                if rule.get("기준"):
                    base = self._lexeme(rule["기준"], doc_id=doc_id)
                    if base:
                        self._edge("MEASURES", qid, base)

    def _aliases(self, selected: set[str]) -> None:
        aliases = _read_json(self.data_dir / "aliases.json", {})
        docs_by_name = {v.name: did for did, v in self.index.docs.items() if did in selected}
        for alias, official in aliases.items():
            doc_id = docs_by_name.get(official)
            if not doc_id:
                continue
            aid = self._lexeme(alias, doc_id=doc_id)
            oid = self._lexeme(official, doc_id=doc_id)
            if aid and oid:
                self._edge("ALIAS_OF", aid, oid, key=doc_id, props={"source": "aliases"})
                self._edge("DENOTES", aid, document_id(doc_id), key=(doc_id, "alias"),
                           props={"doc_id": doc_id, "role": "document_alias"})

    def _relation_edge(self, edge: relations.SectionRelation) -> None:
        src = section_id(edge.src_doc, edge.src_node)
        dst = section_id(edge.dst_doc, edge.dst_node)
        if src not in self.node_ids or dst not in self.node_ids:
            return
        props = {**edge.props, "relation_kind": edge.kind,
                 "src_doc": edge.src_doc, "src_node": edge.src_node,
                 "dst_doc": edge.dst_doc, "dst_node": edge.dst_node}
        self._edge(edge.kind, src, dst, key=edge.key, props=props)
        surface = str(edge.props.get("surface") or edge.props.get("link") or "").strip()
        if surface:
            lid = self._lexeme(surface, doc_id=edge.src_doc)
            if lid:
                self._edge("USES_LOCATOR", src, lid,
                           key=(edge.props.get("block"), surface, edge.kind))
                self._edge("DENOTES", lid, dst,
                           key=(edge.src_doc, edge.dst_doc, dst, edge.kind), props={
                    "doc_id": edge.dst_doc, "role": "relation_locator",
                    "source_doc": edge.src_doc, "relation_kind": edge.kind,
                })
        self.stats["relations"] += 1
        if edge.kind in set(relations.REFERENCE_KINDS.values()):
            self.stats["references"] += 1

    def _relations(self, selected: set[str], bundle: relations.RelationBundle) -> None:
        for edge in bundle.sections:
            if edge.src_doc in selected and edge.dst_doc in selected:
                self._relation_edge(edge)

    def _pending_references(self, selected: set[str]) -> None:
        _resolved, pending = self.index.cross_refs()
        for ordinal, row in enumerate(pending):
            src_doc = row.get("src_doc")
            src = section_id(src_doc, row.get("src"))
            if src_doc not in selected or src not in self.node_ids:
                continue
            pid = self._node(Node(stable_id("pending_ref", src_doc, row.get("src"), ordinal,
                                            row.get("surface")), "PendingReference",
                                  row.get("surface", ""), {
                "src_doc": src_doc, "src": row.get("src"), "surface": row.get("surface", ""),
                "hint": row.get("hint", ""), "relation": row.get("rel", "인용"),
            }))
            self._edge("HAS_UNRESOLVED_REFERENCE", src, pid, key=ordinal)
            for cidx, candidate in enumerate(row.get("candidates", [])):
                target = section_id(candidate.get("doc_id"), candidate.get("node"))
                self._edge("MAY_REFER_TO", pid, target, key=cidx, props={
                    k: v for k, v in candidate.items() if k not in {"doc_id", "node"}
                })
            self.stats["unresolved_references"] += 1

    def _requirements(self, selected: set[str], bundle: relations.RelationBundle) -> None:
        for row in bundle.requirements:
            if row.doc_id not in selected:
                continue
            owner, article = (section_id(row.doc_id, row.node),
                              section_id(row.doc_id, row.article))
            if owner not in self.node_ids or article not in self.node_ids:
                continue
            source_key = (row.doc_id, row.node)
            frames = self.frames_by_source.get(source_key, ())
            rid = self._node(Node(
                stable_id("requirement", row.doc_id, row.block, row.kind,
                          row.start, row.end, row.trigger_start, row.trigger_end),
                "Requirement", row.trigger, {
                    "doc_id": row.doc_id, "node": row.node, "article": row.article,
                    "block": row.block, "kind": row.kind, "surface": row.surface,
                    "start": row.start, "end": row.end, "trigger": row.trigger,
                    "trigger_start": row.trigger_start, "trigger_end": row.trigger_end,
                    "provenance": "source_text:exact_span",
                    "grounding_status": "exact_span",
                    **claim_metadata(
                        evidence_type="rule_extracted_exact_source_span",
                        claim_status="candidate",
                        consumer_policy="corroborate",
                        confidence_status="unscored",
                        possible_errors=[
                            "source_parser_error", "span_boundary_error",
                            "requirement_kind_misclassification",
                        ],
                        binding_status=("unique_same_node_candidate"
                                        if len(frames) == 1 else
                                        "ambiguous_same_node_candidates"
                                        if frames else "no_same_node_frame"),
                        binding_candidate_count=len(frames)),
                }))
            self._edge("HAS_REQUIREMENT", owner, rid,
                       key=(row.block, row.kind, row.start, row.end))
            self._edge(REQUIREMENT_KINDS.get(row.kind, "HAS_REQUIREMENT"),
                       article, rid,
                       key=(row.block, row.kind, row.trigger_start, row.trigger_end))
            self._edge("QUALIFIES", rid, article,
                       key=(row.block, row.kind, row.trigger_start))
            self.requirements_by_source.setdefault(source_key, []).append((rid, row.kind))
            # 복수 Frame 중 하나를 임의 선택하거나 모두 연결하면 후보라는 라벨이
            # 있어도 탐색 폭증과 잘못된 결속을 만든다. 유일한 same-node Frame만
            # MAY_* 후보로 내고, 나머지는 Requirement props에 모호성만 보존한다.
            for frame_id in frames if len(frames) == 1 else ():
                self._edge(
                    REQUIREMENT_CANDIDATE_KINDS[row.kind], rid, frame_id,
                    key=(row.block, row.kind, row.trigger_start, frame_id),
                    props=self._requirement_binding_props(
                        row.doc_id, row.node, frame_id, len(frames),
                        target_kind="Frame"))
                self.stats["requirement_candidate_bindings"] += 1
            self.stats["requirements"] += 1

    @staticmethod
    def _requirement_binding_props(doc_id: str, node: object, frame_id: str,
                                   alternatives: int, *, target_kind: str) -> dict:
        """같은 source node라는 사실과 의미 결속 후보를 분리해 기록한다."""
        return claim_metadata(
            evidence_type="same_source_node_proximity",
            claim_status="candidate", consumer_policy="candidate_only",
            confidence_status="unscored", doc_id=doc_id, node=node,
            via_frame=frame_id, target_kind=target_kind,
            alternative_frames=alternatives,
            possible_errors=[
                "wrong_frame_attachment", "shared_clause_scope",
                "parser_or_llm_extraction_error",
            ])

    def _graph_relations(self, selected: set[str],
                         bundle: relations.RelationBundle) -> None:
        def endpoint(kind: str, doc_id: str, node: object | None) -> str:
            return (document_id(doc_id) if kind == "document"
                    else section_id(doc_id, node))

        for row in bundle.graph:
            if row.src_doc not in selected or row.dst_doc not in selected:
                continue
            src = endpoint(row.src_kind, row.src_doc, row.src_node)
            dst = endpoint(row.dst_kind, row.dst_doc, row.dst_node)
            self._edge(row.kind, src, dst,
                       key=(row.src_kind, row.src_doc, row.src_node,
                            row.dst_kind, row.dst_doc, row.dst_node),
                       props=row.props)
        for fact in bundle.temporal:
            if fact.doc_id not in selected:
                continue
            did = document_id(fact.doc_id)
            date_id = self._node(Node(
                stable_id("date", fact.value), "DateValue", fact.value,
                {"value": fact.value, "precision": "day" if len(fact.value) == 8 else "raw"}))
            self._edge(fact.kind, did, date_id, key=(fact.kind, fact.value), props={
                "provenance": "structure:document_metadata"})

    def _glossary_occurrences(self, selected: set[str]) -> None:
        blob = _read_json(self.glossary_path, {"terms": []})
        for tidx, term in enumerate(blob.get("terms", [])):
            if term.get("status") not in (None, "활성", "active"):
                continue
            canonical = term.get("term", "")
            for oidx, occ in enumerate(term.get("occurrences", [])):
                doc_id, node = occ.get("doc_id"), occ.get("node")
                if doc_id not in selected or node not in self.index.docs[doc_id].by_id:
                    continue
                sid = section_id(doc_id, node)
                surface = occ.get("surface") or canonical
                mid = self._mention(sid, surface, source="glossary", role="term_occurrence",
                                    doc_id=doc_id, node_id=node, occurrence=(tidx, oidx))
                if mid:
                    lid = lexeme_id(surface)
                    self._edge("MENTIONS_TERM", sid, lid, key=(tidx, oidx), props={
                        "mention": mid, "via": occ.get("via", ""),
                        "block": occ.get("block"), "page": occ.get("page"),
                    })
