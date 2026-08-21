"""1급 Concept/Assertion을 기존 RAG의 첫 진입 채널로 연결한다."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from lawrag.core.domain_graph import oql
from lawrag.core.domain_graph.alignment import ConceptAligner
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag.answer import SECTION_CHARS, Section
from lawrag.core.rag.index import ROOT, Index, store_path


log = logging.getLogger("lawrag.core.rag.conceptfirst")
ENTRY_CAP = 4
_GENERIC_RELATION = re.compile(r"관계|관련성|연관성")


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _assertion_allowed(question: str, alignment, assertion) -> bool:
    """승인 Concept가 하나 겹쳤다는 이유만으로 모든 Assertion을 열지 않는다.

    OQL은 구조적으로 정확해도 질문의 술어가 다르면 의미상 오답이다. 따라서 active
    Assertion에 승인된 query cue가 있거나, predicate Concept가 실제 후보로 잡혔거나,
    사용자가 둘 이상의 Concept 사이의 일반 관계를 물은 경우만 근거를 연다. 자연어는
    여기서 게이트로만 쓰이고 OQL/SQL 파라미터에는 들어가지 않는다.
    """
    selected = {c.concept_id for c in alignment.selected}
    predicates = set(assertion.roles.get("PREDICATE") or ())
    if selected & predicates:
        return True
    packed = _pack(question)
    if any(_pack(cue) in packed for cue in assertion.query_cues if _pack(cue)):
        return True
    return (alignment.intent == "RELATION_BETWEEN_CONCEPTS"
            and len(selected) >= 2 and bool(_GENERIC_RELATION.search(question)))


def _data_dir() -> Path:
    # 서비스는 STRUCTURE_STORE를 명시한다. 저장소에서 모듈만 실행할 때 index의
    # 역사적 기본 var/out/... parent가 존재해도 실제 정본은 data/다.
    if os.environ.get("STRUCTURE_STORE"):
        return store_path().parent
    return ROOT / "data"


def graph_path() -> Path:
    return Path(os.environ.get("RAG_DOMAIN_GRAPH",
                               _data_dir() / "domain_graph" / "graph.sqlite"))


def registry_path() -> Path:
    return Path(os.environ.get("RAG_CONCEPT_REGISTRY",
                               _data_dir() / "domain_graph" / "canonical.json"))


def retrieve(index: Index, question: str, *, llm=None,
             cap: int = ENTRY_CAP) -> tuple[list[Section], dict]:
    """질문 → Concept 정렬 → OQL → 근거 Section. 빈손이면 하위 사다리가 받는다."""
    meta = {"alignment": {}, "oql": None, "hits": [], "fallback": ""}
    gp, rp = graph_path(), registry_path()
    if not gp.is_file() or not rp.is_file():
        meta["fallback"] = "1급 그래프 또는 레지스트리 없음"
        return [], meta
    try:
        registry = Tier1Registry.load(rp)
    except (ValueError, OSError) as exc:
        log.error("1급 레지스트리 거부 — %s", exc)
        meta["fallback"] = "1급 레지스트리 검증 실패"
        return [], meta
    if not registry.active_concepts:
        meta["fallback"] = "active Concept 없음"
        return [], meta

    alignment = ConceptAligner(registry).align(question, llm=llm)
    meta["alignment"] = alignment.as_dict()
    if alignment.ambiguous:
        meta["fallback"] = "Concept 정렬 중의성 — 하위 사다리로 하강"
        return [], meta
    request = oql.plan(alignment)
    if request is None:
        meta["fallback"] = "Concept 정렬 불충분"
        return [], meta
    try:
        with GraphStore(gp, readonly=True) as store:
            result = oql.execute(store, registry, request)
    except (ValueError, OSError) as exc:
        log.error("OQL 실행 거부 — %s", exc)
        meta["fallback"] = "OQL 검증 또는 실행 실패"
        return [], meta
    meta["oql"] = {"pattern": result["pattern"], "params": result["params"],
                   "count": result["count"]}

    sections, seen = [], set()
    labels = " · ".join(c.label for c in alignment.selected)
    assertions = {a.id: a for a in registry.active_assertions}
    for row in result["rows"]:
        aid = str(row.get("assertion_id") or "")
        assertion = assertions.get(aid.removeprefix("assertion:"))
        if assertion is not None and not _assertion_allowed(question, alignment, assertion):
            continue
        for source in row.get("sources", []):
            doc_id, node = source.get("doc_id"), source.get("node")
            if not index.in_scope(doc_id) or (doc_id, node) in seen:
                continue
            view = index.docs.get(doc_id)
            section = view.by_id.get(node) if view else None
            if view is None or section is None:
                continue
            from lawrag.core.rag import verdicts as verdicts_mod
            if verdicts_mod.is_entry_blocked(doc_id, node):
                continue
            seen.add((doc_id, node))
            sections.append(Section(
                n=0, doc_id=doc_id, doc=view.name, node=node,
                path=view.path(node) or view.name, page=section.get("page"),
                kind="Concept", matched=f"1급 OQL {result['pattern']} — {labels}"[:160],
                text=view.section_outline(section, cap=SECTION_CHARS),
            ))
            meta["hits"].append({
                "assertion_id": row.get("assertion_id"), "doc_id": doc_id,
                "node": node, "confidence": row.get("confidence"),
                "roles": row.get("roles"),
            })
            if len(sections) >= cap:
                break
        if len(sections) >= cap:
            break
    if not sections:
        meta["fallback"] = "질문 술어와 맞는 active Assertion 근거 없음"
    return sections, meta
