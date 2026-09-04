"""법률 관계의 단일 생성·소비 계약.

본문 참조, 법제처 위임, 정의 적용, 위반-제재, 부칙 시점 관계를 같은
``SectionRelation``으로 접는다. 제품 검색과 domain graph 빌더가 이 모듈을 함께
사용하므로, 그래프에는 있지만 검색은 못 걷거나 검색에서만 즉석 생성되는 관계를
없애는 것이 목적이다.

모든 관계는 실제 문서·구역 좌표와 원천을 보존한다. LLM이 새 좌표를 만들지 않으며,
미해결 인용은 기존 ``Index.cross_refs()``의 PendingReference 경로에 그대로 남는다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lawrag.core.domain_graph import requirements as requirement_spans
from lawrag.core.rag import definitions, delegation, tags
from lawrag.core.rag.content_snapshot import (
    ArtifactProvenance,
    ContentSnapshot,
    ContentSnapshotError,
    artifact_provenance_receipt,
    current_content_snapshot,
)
from lawrag.core.rag.index import Index, norm


_ARTICLE = re.compile(r"^제\s*\d+(?:-\d+)?조(?:의\s*\d+)?$")

REFERENCE_KINDS = {
    "준용": "INCORPORATES",
    "배제": "EXCLUDES",
    "의제": "DEEMS",
    "수임": "RECEIVES_FROM",
    "근거": "BASED_ON",
    "인용": "REFERENCES",
}

DISPLAY = {
    "REFERENCES": "인용",
    "BASED_ON": "근거",
    "INCORPORATES": "준용",
    "EXCLUDES": "배제",
    "DEEMS": "의제",
    "RECEIVES_FROM": "수임",
    "DELEGATES_TO": "위임",
    "USES_DEFINITION": "정의적용",
    "VIOLATION_SANCTIONED_BY": "제재",
    "HAS_EXCEPTION": "예외",
    "EFFECTIVE_FOR": "시행일",
    "APPLIES_TO": "적용례",
    "TRANSITION_FOR": "경과조치",
    "AMENDS": "개정",
}

# 누락되면 법적 결론이 달라지거나 조문의 직접 완결성이 깨지는 관계다. 일반 인용과
# 이웃 조문은 여기에 넣지 않는다.
MANDATORY_KINDS = frozenset({
    "BASED_ON", "INCORPORATES", "EXCLUDES", "DEEMS", "RECEIVES_FROM",
    "DELEGATES_TO", "USES_DEFINITION", "VIOLATION_SANCTIONED_BY",
    "HAS_EXCEPTION", "EFFECTIVE_FOR", "APPLIES_TO", "TRANSITION_FOR",
})

_TEMPORAL_KINDS = {
    "시행일": "EFFECTIVE_FOR",
    "적용례": "APPLIES_TO",
    "경과조치": "TRANSITION_FOR",
    "개정·폐지": "AMENDS",
}


@dataclass
class SectionRelation:
    kind: str
    src_doc: str
    src_node: object
    dst_doc: str
    dst_node: object
    props: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple:
        return self.kind, self.src_doc, self.src_node, self.dst_doc, self.dst_node

    @property
    def mandatory(self) -> bool:
        return self.kind in MANDATORY_KINDS

    @property
    def label(self) -> str:
        return DISPLAY.get(self.kind, self.kind)

    def explanation(self, *, reverse: bool = False) -> str:
        surface = str(self.props.get("surface") or self.props.get("link") or "").strip()
        source = "·".join(self.props.get("provenance") or ())
        direction = "역방향" if reverse else "순방향"
        tail = f" — '{surface}'" if surface else ""
        via = f" ({source})" if source else ""
        return f"{self.label} {direction}{tail}{via}"


@dataclass(frozen=True)
class RequirementRecord:
    doc_id: str
    node: object
    article: object
    block: object
    kind: str
    surface: str
    start: int
    end: int
    trigger: str
    trigger_start: int
    trigger_end: int
    content_provenance: ArtifactProvenance | None = None


@dataclass(frozen=True)
class GraphRelation:
    """Section 외 Document endpoint까지 허용하는 그래프 전용 관계."""
    kind: str
    src_kind: str
    src_doc: str
    src_node: object | None
    dst_kind: str
    dst_doc: str
    dst_node: object | None
    props: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TemporalFact:
    doc_id: str
    kind: str
    value: str
    content_provenance: ArtifactProvenance | None = None


@dataclass
class RelationBundle:
    sections: tuple[SectionRelation, ...]
    requirements: tuple[RequirementRecord, ...] = ()
    graph: tuple[GraphRelation, ...] = ()
    temporal: tuple[TemporalFact, ...] = ()
    outgoing: dict[tuple[str, object], tuple[SectionRelation, ...]] = field(
        default_factory=dict)
    incoming: dict[tuple[str, object], tuple[SectionRelation, ...]] = field(
        default_factory=dict)
    content_snapshot: ContentSnapshot | None = None

    def incident(self, doc_id: str, node: object) \
            -> tuple[tuple[SectionRelation, ...], tuple[SectionRelation, ...]]:
        return (self.outgoing.get((doc_id, node), ()),
                self.incoming.get((doc_id, node), ()))


def article_root(view, node: object) -> object:
    cur = view.by_id.get(node)
    seen = set()
    while cur is not None and cur.get("id") not in seen:
        seen.add(cur.get("id"))
        if _ARTICLE.fullmatch(str(cur.get("surface") or "").strip()):
            return cur.get("id")
        cur = view.by_id.get(cur.get("parent"))
    return node


def _provenance(value: str | Iterable[str]) -> list[str]:
    values = [value] if isinstance(value, str) else list(value)
    return list(dict.fromkeys(str(item) for item in values if str(item)))


def _snapshot(index: Index) -> ContentSnapshot | None:
    value = getattr(index, "content_snapshot", None)
    process = current_content_snapshot()
    if (value is not None and process is not None
            and value.content_snapshot_sha256 != process.content_snapshot_sha256):
        raise ContentSnapshotError("relation index and process snapshots disagree")
    return value if value is not None else process


def _artifact(index: Index, doc_id: str) -> ArtifactProvenance | None:
    view = index.docs.get(doc_id)
    value = ((getattr(view, "content_provenance", None)
              or getattr(view, "artifact_provenance", None))
             if view is not None else None)
    snapshot = _snapshot(index)
    if snapshot is not None and doc_id:
        expected = snapshot.provenance_for_document(doc_id)
        if value is not None and value != expected:
            raise ContentSnapshotError(
                "relation artifact provenance disagrees with content snapshot")
        return expected
    return value


def _edge_props(index: Index, props: dict, src_doc: str, dst_doc: str) -> dict:
    """Attach endpoint artifacts without overloading discovery provenance."""

    value = dict(props)
    endpoints = {}
    for role, doc_id in (("source", src_doc), ("target", dst_doc)):
        receipt = artifact_provenance_receipt(_artifact(index, doc_id))
        if receipt is not None:
            endpoints[role] = receipt
    if endpoints:
        value["content_provenance"] = endpoints
    return value


def _put(edges: dict[tuple, SectionRelation], row: SectionRelation) -> None:
    old = edges.get(row.key)
    row.props["provenance"] = _provenance(row.props.get("provenance") or ())
    if old is None:
        edges[row.key] = row
        return
    old.props["provenance"] = _provenance([
        *(old.props.get("provenance") or ()), *(row.props.get("provenance") or ())])
    evidence = list(old.props.get("evidence") or ())
    candidate = {k: v for k, v in row.props.items() if k != "evidence"}
    if candidate not in evidence:
        evidence.append(candidate)
    if evidence:
        old.props["evidence"] = evidence


def _section_relation(index: Index, kind: str, src_doc: str, src_node: object,
                      dst_doc: str, dst_node: object, props: dict) \
        -> SectionRelation | None:
    sv, dv = index.docs.get(src_doc), index.docs.get(dst_doc)
    if (sv is None or dv is None or src_node not in sv.by_id
            or dst_node not in dv.by_id
            or not index.relation_allowed(src_doc, dst_doc)):
        return None
    return SectionRelation(
        kind, src_doc, article_root(sv, src_node),
        dst_doc, article_root(dv, dst_node),
        _edge_props(index, props, src_doc, dst_doc))


def _reference_rows(index: Index) -> list[tuple[str, dict, bool]]:
    rows = []
    for doc_id, values in index.ref_edges().items():
        rows.extend((doc_id, row, False) for row in values)
    rows.extend((row.get("src_doc", ""), row, True)
                for row in index.cross_ref_edges())
    return rows


def _requirements(index: Index) -> tuple[RequirementRecord, ...]:
    out, seen = [], set()
    for doc_id, view in index.docs.items():
        for block in view.blocks:
            text = str(block.get("text") or "")
            if not text:
                continue
            owner = block.get("node")
            if owner is None:
                owner = (view.owner(block.get("idx")) or {}).get("id")
            if owner not in view.by_id:
                continue
            article = article_root(view, owner)
            for span in requirement_spans.extract(text):
                key = (doc_id, owner, block.get("idx"), span.kind,
                       span.start, span.end, span.trigger_start, span.trigger_end)
                if key in seen:
                    continue
                seen.add(key)
                out.append(RequirementRecord(
                    doc_id, owner, article, block.get("idx"), span.kind,
                    span.surface, span.start, span.end, span.trigger,
                    span.trigger_start, span.trigger_end,
                    _artifact(index, doc_id)))
    return tuple(out)


def _definition_relations(index: Index, doc_id: str,
                          article: object) -> tuple[SectionRelation, ...]:
    view = index.docs.get(doc_id)
    if view is None or article not in view.by_id:
        return ()
    out = []
    for definition in definitions.terms_in(view, article, cap=64):
        row = _section_relation(
            index, "USES_DEFINITION", doc_id, article,
            doc_id, definition.get("node"), {
                "term": definition.get("term", ""),
                "definition_kind": definition.get("kind", ""),
                "scope": definition.get("scope", ""),
                "scope_root": definition.get("scope_root"),
                "block": definition.get("block"),
                "provenance": ["source_text:definition", "deterministic:scope"],
                "authority": "source_text", "confidence": "exact-term-in-scope",
                "status": "resolved",
            })
        if row:
            out.append(row)
    return tuple(out)


def _document_graph(index: Index, law_index_file: Path | None) \
        -> tuple[tuple[GraphRelation, ...], tuple[TemporalFact, ...]]:
    graph: list[GraphRelation] = []
    seen = set()

    def put(row: GraphRelation) -> None:
        if not index.relation_allowed(row.src_doc, row.dst_doc):
            return
        key = (row.kind, row.src_kind, row.src_doc, row.src_node,
               row.dst_kind, row.dst_doc, row.dst_node)
        if key not in seen:
            seen.add(key)
            graph.append(row)

    if law_index_file is not None and law_index_file.is_file():
        try:
            blob = json.loads(law_index_file.read_text(encoding="utf-8"))
        except Exception:
            blob = {}
        for family in blob.get("families", []):
            stack: list[tuple[int, str]] = []
            for member in family.get("members", []):
                doc_id = member.get("doc_id")
                if not doc_id or doc_id not in index.docs:
                    continue
                depth = int(member.get("depth") or 0)
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                if stack:
                    parent = stack[-1][1]
                    base_props = {
                        "provenance": "law.go.kr:lsStmd",
                        "family": family.get("root", ""),
                    }
                    put(GraphRelation("IMPLEMENTED_BY", "document", parent, None,
                                      "document", doc_id, None,
                                      _edge_props(index, base_props, parent, doc_id)))
                    put(GraphRelation("ISSUED_UNDER", "document", doc_id, None,
                                      "document", parent, None,
                                      _edge_props(index, base_props, doc_id, parent)))
                stack.append((depth, doc_id))

    # 같은 series가 있으면 그것이 우선이고, 없을 때만 같은 문서명의 구판·현행을 잇는다.
    groups: dict[str, list[tuple[str, object]]] = {}
    for doc_id, view in index.docs.items():
        key = f"series:{view.series}" if view.series else f"name:{norm(view.name)}"
        groups.setdefault(key, []).append((doc_id, view))
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        ordered = sorted(rows, key=lambda item: (
            item[1].is_current, item[1].enforce, item[1].revised,
            item[1].version, item[0]))
        for (old_id, _old), (new_id, _new) in zip(ordered, ordered[1:]):
            base_props = {
                "provenance": "structure:version_metadata", "series": key,
            }
            put(GraphRelation("SUPERSEDES", "document", new_id, None,
                              "document", old_id, None,
                              _edge_props(index, base_props, new_id, old_id)))
            put(GraphRelation("SUPERSEDED_BY", "document", old_id, None,
                              "document", new_id, None,
                              _edge_props(index, base_props, old_id, new_id)))

    temporal = []
    for doc_id, view in index.docs.items():
        if view.enforce:
            temporal.append(TemporalFact(
                doc_id, "VALID_FROM", view.enforce, _artifact(index, doc_id)))
        if view.revised:
            temporal.append(TemporalFact(
                doc_id, "REVISED_ON", view.revised, _artifact(index, doc_id)))
    return tuple(graph), tuple(temporal)


def build(index: Index, *, delegation_file: str | Path | None = None,
          law_index_file: str | Path | None = None,
          include_requirements: bool = False,
          include_definition_edges: bool | None = None,
          use_cache: bool = True) -> RelationBundle:
    """현재 Index에서 확정 관계 번들을 만든다.

    ``delegation_file``과 ``law_index_file``을 명시하면 빌더의 data directory가 정본이다.
    인자를 생략한 제품 런타임은 기존 환경 경로를 사용한다.
    """
    if include_definition_edges is None:
        include_definition_edges = bool(include_requirements)
    cache_key = (str(Path(delegation_file).resolve()) if delegation_file else "runtime",
                 str(Path(law_index_file).resolve()) if law_index_file else "",
                 bool(include_requirements), bool(include_definition_edges))
    cache = getattr(index, "_unified_relation_cache", None)
    if use_cache and isinstance(cache, dict) and cache_key in cache:
        return cache[cache_key]

    edges: dict[tuple, SectionRelation] = {}
    reference_rows = _reference_rows(index)

    for src_doc, raw, cross in reference_rows:
        dst_doc = raw.get("dst_doc") or src_doc
        rel = str(raw.get("rel") or "인용")
        row = _section_relation(
            index, REFERENCE_KINDS.get(rel, "REFERENCES"), src_doc, raw.get("src"),
            dst_doc, raw.get("dst"), {
                **{k: v for k, v in raw.items()
                   if k not in {"src", "dst", "src_doc", "dst_doc"}},
                "relation": rel, "cross_document": cross,
                "provenance": ["source_text:reference", str(raw.get("via") or "deterministic")],
                "authority": "source_text", "confidence": "exact-coordinate",
                "status": "resolved",
            })
        if row:
            _put(edges, row)

        # 부칙의 정형 종류를 일반 참조와 별도의 시점 관계로 보존한다.
        view = index.docs.get(src_doc)
        temporal_kind = _TEMPORAL_KINDS.get(
            view.addendum_kind(raw.get("src")) if view else "")
        if temporal_kind:
            temporal = _section_relation(
                index, temporal_kind, src_doc, raw.get("src"), dst_doc, raw.get("dst"), {
                    "surface": raw.get("surface", ""), "block": raw.get("block"),
                    "provenance": ["source_text:addendum", "structure:addendum_kind"],
                    "authority": "source_text", "confidence": "exact-coordinate",
                    "status": "resolved",
                })
            if temporal:
                _put(edges, temporal)

    # 공식 위임. 조 좌표가 없는 위임행정규칙은 반대 방향의 수임 문면이 같은
    # 출발 조를 정확히 가리킬 때만 조문 간선으로 닫고, 아니면 그래프의 문서 포인터로 남긴다.
    graph_extra: list[GraphRelation] = []
    dpath = Path(delegation_file) if delegation_file is not None else None
    delegated = delegation.adjacency(dpath, include_document_targets=True)
    from lawrag.core.rag import verdicts as verdicts_mod
    for (src_doc, src_node), rows in delegated.items():
        if src_doc not in index.docs or src_node not in index.docs[src_doc].by_id:
            continue
        src_root = article_root(index.docs[src_doc], src_node)
        for raw in rows:
            dst_doc, dst_node = raw.get("doc_id"), raw.get("node")
            candidates = []
            if dst_node is None and dst_doc in index.docs:
                for ref_src_doc, ref, _cross in reference_rows:
                    ref_dst_doc = ref.get("dst_doc") or ref_src_doc
                    if (ref_src_doc != dst_doc or ref_dst_doc != src_doc
                            or str(ref.get("rel") or "") != "수임"):
                        continue
                    if article_root(index.docs[src_doc], ref.get("dst")) == src_root:
                        candidates.append(ref.get("src"))
            else:
                candidates = [dst_node]
            if candidates:
                for candidate in dict.fromkeys(candidates):
                    if verdicts_mod.is_suppressed(
                            src_doc, src_node, dst_doc, candidate):
                        continue
                    row = _section_relation(
                        index, "DELEGATES_TO", src_doc, src_node, dst_doc, candidate, {
                            **{k: v for k, v in raw.items() if k not in {"doc_id", "node"}},
                            "provenance": [raw.get("provenance", "law.go.kr:lsDelegated"),
                                           *( ["source_text:receiving"] if dst_node is None else [])],
                            "authority": "official", "confidence": "exact-coordinate",
                            "status": "resolved",
                        })
                    if row:
                        _put(edges, row)
            elif (dst_doc in index.docs
                  and index.relation_allowed(src_doc, dst_doc)):
                graph_extra.append(GraphRelation(
                    "DELEGATES_TO_DOCUMENT", "section", src_doc, src_root,
                    "document", dst_doc, None, _edge_props(index, {
                        **{k: v for k, v in raw.items() if k not in {"doc_id", "node"}},
                        "provenance": raw.get("provenance", "law.go.kr:lsDelegated"),
                        "status": "document-target",
                    }, src_doc, dst_doc)))

    # 전체 정의 적용 간선은 graph build에서 물질화한다. 제품 런타임은 incident()가
    # 선택된 조문 하나에 대해서만 같은 생성기를 호출해 첫 질의에 전 코퍼스를 훑지 않는다.
    if include_definition_edges:
        for doc_id, view in index.docs.items():
            articles = [node.get("id") for node in view.nodes
                        if _ARTICLE.fullmatch(str(node.get("surface") or "").strip())]
            for article in articles:
                for row in _definition_relations(index, doc_id, article):
                    _put(edges, row)

    # 위반 조문을 인용하는 벌칙·행정제재·민사구제 조문을 역방향 companion으로 잇는다.
    for src_doc, raw, _cross in reference_rows:
        dst_doc = raw.get("dst_doc") or src_doc
        sv, dv = index.docs.get(src_doc), index.docs.get(dst_doc)
        if sv is None or dv is None:
            continue
        src_root, dst_root = article_root(sv, raw.get("src")), article_root(dv, raw.get("dst"))
        if (not tags.is_sanction(sv, src_root)
                or not tags.has_condition(dv, dst_root, ("의무", "금지"))):
            continue
        row = _section_relation(
            index, "VIOLATION_SANCTIONED_BY", dst_doc, dst_root, src_doc, src_root, {
                "surface": raw.get("surface", ""), "block": raw.get("block"),
                "sanction_kind": tags.sanction_kind(sv, src_root),
                "provenance": ["source_text:reference", "deterministic:sanction_tag"],
                "authority": "source_text", "confidence": "exact-reference",
                "status": "resolved",
            })
        if row:
            _put(edges, row)

    requirement_rows = _requirements(index) if include_requirements else ()
    for req in requirement_rows:
        if req.kind != "EXCEPTION" or req.node == req.article:
            continue
        row = _section_relation(
            index, "HAS_EXCEPTION", req.doc_id, req.article, req.doc_id, req.node, {
                "surface": req.surface, "trigger": req.trigger, "block": req.block,
                "provenance": ["source_text:requirement", "deterministic:closed-cue"],
                "authority": "source_text", "confidence": "exact-span",
                "status": "resolved",
            })
        if row:
            # article_root 정규화로 자기 간선이 된 경우는 Requirement node 쪽에만 보존한다.
            if (row.src_doc, row.src_node) != (row.dst_doc, row.dst_node):
                _put(edges, row)

    if law_index_file is not None:
        law_path = Path(law_index_file)
    elif index.content_snapshot is not None:
        law_path = index.content_snapshot.semantic_path("law_index.json")
    else:
        law_path = None
    document_graph, temporal_facts = _document_graph(index, law_path)
    section_rows = tuple(sorted(edges.values(), key=lambda row: (
        row.src_doc, str(row.src_node), row.kind, row.dst_doc, str(row.dst_node))))
    outgoing: dict[tuple[str, object], list[SectionRelation]] = {}
    incoming: dict[tuple[str, object], list[SectionRelation]] = {}
    for row in section_rows:
        outgoing.setdefault((row.src_doc, row.src_node), []).append(row)
        incoming.setdefault((row.dst_doc, row.dst_node), []).append(row)
    # This final guard also covers future graph producers that are appended
    # outside ``_document_graph.put``.  The SourceSet policy is therefore a
    # bundle invariant, not an implementation detail of one relation source.
    graph_rows = tuple(
        row for row in (*document_graph, *graph_extra)
        if index.relation_allowed(row.src_doc, row.dst_doc)
    )
    bundle = RelationBundle(
        sections=section_rows, requirements=tuple(requirement_rows),
        graph=graph_rows, temporal=temporal_facts,
        outgoing={key: tuple(value) for key, value in outgoing.items()},
        incoming={key: tuple(value) for key, value in incoming.items()},
        content_snapshot=_snapshot(index),
    )
    if use_cache:
        if not isinstance(cache, dict):
            cache = {}
            setattr(index, "_unified_relation_cache", cache)
        cache[cache_key] = bundle
    return bundle


def incident(index: Index, doc_id: str, node: object) \
        -> tuple[tuple[SectionRelation, ...], tuple[SectionRelation, ...]]:
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return (), ()
    root = article_root(view, node)
    outgoing, incoming = build(index).incident(doc_id, root)
    # 정의 적용은 선택된 조문에서만 지연 계산한다. 그래프 빌더의 전량 생성과 정확히
    # 같은 함수라 관계 의미는 갈리지 않고 계산 범위만 다르다.
    definition_rows = _definition_relations(index, doc_id, root)
    if definition_rows:
        merged = {row.key: row for row in outgoing}
        for row in definition_rows:
            merged.setdefault(row.key, row)
        outgoing = tuple(merged.values())
    return outgoing, incoming
