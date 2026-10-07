"""법률 질문의 회수 채널을 조문 좌표에서 닫는 운영 기본 검색기.

정확 원문/명시 좌표, canonical Assertion 트리, 검색어 BM25를 각각 실행한 뒤
모든 결과를 조 단위로 접는다. BM25는 답을 정하지 않고 Assertion이 놓친 표현의
좌표만 보충한다. 마지막으로 선택된 조문에서 직접 참조를 한 층 열어 상위법·하위
규정·예외 조문이 따로 떨어지는 것을 막는다.
"""
from __future__ import annotations

from dataclasses import replace
import re
import time

from lawrag.core.domain_graph import spanparts
from lawrag.core.rag import (
    assertionfirst,
    definitions,
    general_search,
    retrieval_feedback,
    switches,
    termexplore,
)
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import legal_evidence, legal_references
from lawrag.core.rag.answer import Section
from lawrag.runtime.content_snapshot import (
    ArtifactProvenance,
    ContentSnapshot,
    ContentSnapshotError,
    artifact_provenance_receipt,
    current_content_snapshot,
)
from lawrag.core.rag.index import Index


PRIMARY_CAP = 12
ASSERTION_CAP = 8
KEYWORD_ARTICLES_MAX = 8
KEYWORD_BLOCKS_PER_TERM = 40
CLOSURE_MAX = 6
_PARTICLE_SUFFIXES = (
    "으로부터", "에게서", "에서는", "으로", "에서", "에게", "까지", "부터",
    "처럼", "보다", "과", "와", "의", "을", "를", "이", "가", "은", "는",
    "에", "로",
)


def _snapshot(index: Index) -> ContentSnapshot | None:
    value = getattr(index, "content_snapshot", None)
    process = current_content_snapshot()
    if (value is not None and process is not None
            and value.content_snapshot_sha256 != process.content_snapshot_sha256):
        raise ContentSnapshotError("LegalClosure index and process snapshots disagree")
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
                "LegalClosure artifact provenance disagrees with content snapshot")
        return expected
    return value


def enrich_content_provenance(index: Index, value) -> None:
    """Add artifact receipts to every coordinate-bearing public audit row.

    LegalClosure metadata contains many nested candidate/lifecycle tables.  A
    single traversal prevents a newly added channel from silently dropping the
    SourceSet identity.  Existing semantic ``provenance`` keys are untouched.
    """

    if isinstance(value, (list, tuple)):
        for child in value:
            enrich_content_provenance(index, child)
        return
    if not isinstance(value, dict):
        return
    for child in list(value.values()):
        enrich_content_provenance(index, child)
    if "content_provenance" in value:
        return
    endpoints = []
    for role, key in (
            ("source", "source_doc_id"), ("source", "src_doc_id"),
            ("source", "src_doc"), ("target", "doc_id"),
            ("target", "dst_doc_id"), ("target", "dst_doc")):
        doc_id = str(value.get(key) or "")
        if doc_id and doc_id in index.docs and (role, doc_id) not in endpoints:
            endpoints.append((role, doc_id))
    if not endpoints:
        return
    receipts = {
        role: receipt for role, doc_id in endpoints
        if (receipt := artifact_provenance_receipt(_artifact(index, doc_id))) is not None
    }
    if not receipts:
        return
    value["content_provenance"] = (
        next(iter(receipts.values()))
        if len(receipts) == 1 and endpoints[0][0] == "target" else receipts)


def _question_terms(question: str) -> tuple[str, ...]:
    """질문 어절과 조사 제거형을 함께 돌려 법률 합성명사의 끝 조사를 접는다."""
    out = []
    for token in general_search.fallback_keywords(question):
        if token not in out:
            out.append(token)
        for suffix in _PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                stem = token[:-len(suffix)]
                if stem not in out:
                    out.append(stem)
                break
    return tuple(out)


def _context_terms(question: str) -> tuple[str, ...]:
    """평가/업무 입력이 명시한 ``업무 문맥``만 결정론적 보충어로 읽는다."""
    match = re.search(r"업무\s*문맥\s*:\s*([^\n)]+)", question or "")
    if not match:
        return ()
    return tuple(term for term in _question_terms(match.group(1))
                 if term not in {"업무", "문맥", "및", "또는"})


def question_terms(question: str) -> tuple[str, ...]:
    """법률 질문의 원문 어절·조사 제거형을 반환하는 공개 API."""
    return _question_terms(question)


def context_terms(question: str) -> tuple[str, ...]:
    """명시된 업무 문맥 구간의 결정론적 보충어를 반환하는 공개 API."""
    return _context_terms(question)


def _without_definition_articles(index: Index, question: str, rows) \
        -> tuple[list, list[dict]]:
    """일반 질문의 최종 근거 경쟁에서 정의 조를 분리한다.

    뜻을 직접 묻는 질문만 예외다. 필터는 각 채널을 merge하기 전에 적용하므로 정의
    조가 차지하던 슬롯은 뒤의 실체·절차·예외 조문이 자연스럽게 채울 수 있다.
    """
    values = list(rows or [])
    if definitions.is_definition_question(question):
        return values, []
    kept, dropped = [], []
    for row in values:
        view = index.docs.get(row.doc_id)
        if view is None or not definitions.is_definition_node(view, row.node):
            kept.append(row)
            continue
        dropped.append({
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "origin": row.origin,
        })
    return kept, dropped


def _attach_definition_context(index: Index, question: str,
                               sections: list[Section], *, per_doc: int = 3,
                               documents_max: int = 2,
                               eligible_doc_ids: set[str] | None = None) -> list[dict]:
    """지배 규정 후보에만 정의 부록을 붙이고 공개 audit 행을 반환한다.

    검색 결과에 등장한 모든 문서는 정의 대상이 아니다. 질문에 명시된 규정과 최우선
    선택 문서만 지배 규정 후보로 보고 최대 두 문서로 제한한다. 나머지 보조·예외·참조
    문서의 정의까지 열면 정의 자체가 다시 과회수가 된다(ADR-0038 v1: 1,623개).
    """
    if definitions.is_definition_question(question):
        return []
    by_doc: dict[str, list[int]] = {}
    for section in sections:
        if (section.node is not None
                and (eligible_doc_ids is None or section.doc_id in eligible_doc_ids)):
            by_doc.setdefault(section.doc_id, []).append(section.node)
    if not by_doc:
        return []
    packed_question = re.sub(r"\s+", "", question or "")
    explicit = [doc_id for doc_id in by_doc
                if re.sub(r"\s+", "", index.docs[doc_id].name) in packed_question]
    priority = list(explicit)
    if (sections and sections[0].doc_id in by_doc
            and sections[0].doc_id not in priority):
        priority.append(sections[0].doc_id)
    # 최우선 문서가 정의 제거 대상이 아니면, 제거 대상 중 최종 순서가 가장
    # 앞선 문서를 대체 규정으로 쓴다.
    for section in sections:
        if section.doc_id in by_doc and section.doc_id not in priority:
            priority.append(section.doc_id)
    priority = priority[:max(0, documents_max)]
    audit = []
    for doc_id in priority:
        node_ids = by_doc[doc_id]
        view = index.docs.get(doc_id)
        if view is None:
            continue
        # 같은 규정에서 뒤에 붙은 보조·예외 조문까지 정의 후보 표면을 만들면
        # 현재 쟁점과 무관한 지역 정의가 다시 섞인다. 규정별 최우선 좌표 하나만
        # 본문 표면으로 쓰고, 질문에 직접 나온 정의어는 context_entries가 별도로
        # 계속 잡는다.
        first_node = list(dict.fromkeys(node_ids))[:1]
        rows = definitions.context_entries(
            view, question, first_node, cap=per_doc)
        if not rows:
            continue
        target = next(section for section in sections if section.doc_id == doc_id)
        target.definition_context.extend(rows)
        audit.extend(rows)
    return audit


def _keyword_articles(index: Index, question: str, keywords: tuple[str, ...]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    # OR 상위 N을 먼저 자르면 ``면제`` 같은 일반 조건어가 N개를 모두 차지해
    # ``내부회계관리제도`` 같은 대상어의 결과가 조문 집계 전에 사라진다. 검색어별
    # 동일 quota를 받은 뒤 조문에서 합쳐 대상/조건 어느 한쪽의 독식을 막는다.
    results = [general_search.search_keywords(
        index, [keyword], question=question, limit=KEYWORD_BLOCKS_PER_TERM,
        per_document=4, extractor="legal-closure-balanced")
        for keyword in keywords]
    hits, hit_seen, unmatched = [], set(), []
    for result in results:
        unmatched.extend(value for value in result.unmatched
                         if value not in unmatched)
        for hit in result.hits:
            key = (hit.doc_id, hit.block, hit.node)
            if key in hit_seen:
                continue
            hit_seen.add(key)
            hits.append(hit)
    grouped: dict[tuple[str, object], dict] = {}
    hit_audit = []
    wants_form = any(token in question for token in (
        "서식", "서류", "첨부", "제출", "보고서", "신청서"))
    for hit in hits:
        view = index.docs.get(hit.doc_id)
        if view is None or hit.node not in view.by_id:
            hit_audit.append({
                "doc_id": hit.doc_id, "node": hit.node,
                "block": hit.block, "score": float(hit.score),
                "matched": list(hit.matched), "accepted": False,
                "reason_code": "no_node_hit",
            })
            continue
        root = coordinates.article_root(view, hit.node)
        path = view.path(root) or ""
        if not termexplore._ARTICLE.fullmatch(
                str(view.by_id[root].get("surface") or "").strip()):
            hit_audit.append({
                "doc_id": hit.doc_id, "node": hit.node, "article_node": root,
                "block": hit.block, "score": float(hit.score),
                "matched": list(hit.matched), "accepted": False,
                "reason_code": "node_not_article",
            })
            continue
        if (not wants_form
                and (view.scope_kind == "서식" or "별표·서식" in path)):
            hit_audit.append({
                "doc_id": hit.doc_id, "node": hit.node, "article_node": root,
                "block": hit.block, "score": float(hit.score),
                "matched": list(hit.matched), "accepted": False,
                "reason_code": "form_filtered",
            })
            continue
        hit_audit.append({
            "doc_id": hit.doc_id, "node": hit.node, "article_node": root,
            "block": hit.block, "score": float(hit.score),
            "matched": list(hit.matched), "accepted": True,
            "reason_code": "generated",
        })
        key = (hit.doc_id, root)
        row = grouped.setdefault(key, {"max": 0.0, "sum": 0.0,
                                       "matched": set(), "blocks": 0})
        row["max"] = max(row["max"], float(hit.score))
        row["sum"] += float(hit.score)
        row["matched"].update(hit.matched)
        row["blocks"] += 1
    for (doc_id, node), row in grouped.items():
        body = coordinates.subtree_text(index.docs[doc_id], node, cap=None)
        exact = [keyword for keyword in keywords
                 if coordinates.contains_phrase(body, keyword)]
        row["exact"] = exact
        row["longest_exact"] = max(
            (len(termexplore._pack(keyword)) for keyword in exact), default=0)
    def rank(item):
        relevance = ((-item[1]["max"], -len(item[1]["matched"]))
                     if wants_form else
                     (-item[1]["longest_exact"], -len(item[1]["exact"]),
                      -len(item[1]["matched"]), -item[1]["max"]))
        return (*relevance, -item[1]["sum"], index.docs[item[0][0]].name,
                index.docs[item[0][0]].path(item[0][1]))

    ranked = sorted(grouped.items(), key=rank)
    branches = []
    public = []
    ranked_public = []
    for rank_no, ((doc_id, node), score) in enumerate(ranked, 1):
        ranked_public.append({
            "rank": rank_no, "doc_id": doc_id, "node": node,
            "doc": index.docs[doc_id].name, "path": index.docs[doc_id].path(node),
            "max_score": round(score["max"], 4),
            "sum_score": round(score["sum"], 4),
            "matched": sorted(score["matched"]), "blocks": score["blocks"],
            "exact": list(score["exact"]),
            "longest_exact": score["longest_exact"],
            "selected": rank_no <= KEYWORD_ARTICLES_MAX,
            "reason_code": ("selected" if rank_no <= KEYWORD_ARTICLES_MAX
                            else "article_cap_dropped"),
        })
    for (doc_id, node), score in ranked[:KEYWORD_ARTICLES_MAX]:
        row = coordinates.article_branch(
            index, doc_id, node, keywords, origin="keyword-bm25",
            reason=(f"BM25 max={score['max']:.4f}; "
                    f"matched={','.join(sorted(score['matched']))}"))
        if row is None:
            continue
        branches.append(row)
        public.append({
            "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "max_score": round(score["max"], 4),
            "sum_score": round(score["sum"], 4),
            "matched": sorted(score["matched"]), "blocks": score["blocks"],
            "exact": list(score["exact"]),
            "longest_exact": score["longest_exact"],
        })
    return branches, {
        "keywords": list(keywords), "unmatched": unmatched,
        "wants_form": wants_form,
        "block_hits": len(hits), "raw_hit_attempts": hit_audit,
        "ranked_article_candidates": ranked_public,
        "article_candidates": public,
    }


def _assertion_channel(index: Index, question: str, registry, *, llm,
                       shortcut_index=None) -> tuple[list[Section], dict]:
    """승인 proof shortcut이 완성되면 B1 LLM 트리를 건너뛰고, 아니면 그대로 실행한다."""
    if shortcut_index is not None and shortcut_index.entries:
        anchors = spanparts.resolve_structure(index, question)
        scope, _ = assertionfirst.structure_scope(index, anchors)
        hits = assertionfirst.current(registry).search(index, question, scope=scope)
        shortcut_hits = shortcut_index.lookup(
            [hit.assertion_id for hit in hits], cap=ASSERTION_CAP,
            require_unambiguous=True, require_query_signature=True)
        if shortcut_hits:
            sections = []
            selected = []
            for hit in shortcut_hits:
                doc_id, node = hit.target
                view = index.docs.get(doc_id)
                if view is None or node not in view.by_id:
                    continue
                sections.append(Section(
                    n=0, doc_id=doc_id, doc=view.name, node=node,
                    path=view.path(node) or view.name,
                    page=view.by_id[node].get("page"), kind="Assertion증명단축",
                    matched="proof-carrying compiled shortcut",
                    text=coordinates.subtree_text(view, node, cap=None),
                    content_provenance=_artifact(index, doc_id)))
                selected.append({"doc_id": doc_id, "node": node, "doc": view.name,
                                 "path": view.path(node) or view.name,
                                 "signals": list(hit.matched_assertions)})
            if sections:
                return sections, {
                    "strategy": "assertion_proof_shortcut",
                    "shortcut": {"used": True, "entry_ids": list(dict.fromkeys(
                        hit.entry_id for hit in shortcut_hits)),
                        "targets": len(sections)},
                    "selected": selected,
                }
    sections, meta = assertionfirst.retrieve(
        index, question, registry, llm=llm, cap=ASSERTION_CAP)
    meta["shortcut"] = {"used": False, "fallback": "no_approved_unambiguous_match"}
    return sections, meta


def _supplemental_closure(index: Index,
                          seeds: list[termexplore.TermBranch],
                          terms: tuple[str, ...]) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """각 seed의 직접 관계를 따로 열어 앞 seed 하나가 확장 상한을 독식하지 않게 한다."""
    out, seen, audits, deferred, lifecycle = [], set(), [], [], []
    for seed_no, seed in enumerate(seeds):
        expanded, meta = termexplore.expand_structural(
            index, [seed], terms, cap=12)
        audits.append({"seed": {"doc_id": seed.doc_id, "node": seed.node,
                                "doc": seed.doc, "path": seed.path},
                       "structural": meta,
                       "unified_relations": {
                           "enabled": True,
                           "source": "relations.RelationBundle",
                           "via": "termexplore.expand_structural",
                       }})
        if not expanded:
            lifecycle.append({
                "source_doc_id": seed.doc_id, "source_node": seed.node,
                "decision": "failed", "reason_code": "no_outgoing_relation",
            })
        local, local_seen = [], set()
        for expanded_row in expanded:
            row = coordinates.article_branch(
                index, expanded_row.doc_id, expanded_row.node, terms,
                origin=expanded_row.origin,
                reason=expanded_row.relation_reason)
            if row is None:
                lifecycle.append({
                    "doc_id": expanded_row.doc_id, "node": expanded_row.node,
                    "source_doc_id": seed.doc_id, "source_node": seed.node,
                    "decision": "failed", "reason_code": "node_not_article",
                    "mandatory": expanded_row.mandatory,
                    "origin": expanded_row.origin,
                })
                continue
            if not expanded_row.mandatory and not row.terms:
                lifecycle.append({
                    "doc_id": row.doc_id, "node": row.node,
                    "source_doc_id": seed.doc_id, "source_node": seed.node,
                    "decision": "rejected",
                    "reason_code": "relation_query_mismatch",
                    "mandatory": False, "origin": row.origin,
                })
                continue
            row = replace(row, mandatory=expanded_row.mandatory,
                          mandatory_reason=expanded_row.mandatory_reason,
                          source_doc_id=seed.doc_id, source_node=seed.node)
            if row.coordinate in local_seen:
                lifecycle.append({
                    "doc_id": row.doc_id, "node": row.node,
                    "source_doc_id": seed.doc_id, "source_node": seed.node,
                    "decision": "merged", "reason_code": "deduplicated",
                    "mandatory": row.mandatory, "origin": row.origin,
                })
                continue
            local_seen.add(row.coordinate)
            local.append(row)
        local.sort(key=lambda row: (
            not row.mandatory, -len(row.terms), row.doc, row.path))
        head = 4 if seed_no == 0 else 1
        for row in local[:head]:
            if row.coordinate not in seen:
                seen.add(row.coordinate)
                out.append(row)
            else:
                lifecycle.append({
                    "doc_id": row.doc_id, "node": row.node,
                    "source_doc_id": seed.doc_id, "source_node": seed.node,
                    "decision": "merged", "reason_code": "deduplicated",
                    "mandatory": row.mandatory, "origin": row.origin,
                })
        deferred.extend(local[head:])
    deferred.sort(key=lambda row: (
        not row.mandatory, -len(row.terms), row.doc, row.path))
    for row in deferred:
        if row.coordinate not in seen:
            seen.add(row.coordinate)
            out.append(row)
        else:
            lifecycle.append({
                "doc_id": row.doc_id, "node": row.node,
                "source_doc_id": row.source_doc_id,
                "source_node": row.source_node,
                "decision": "merged", "reason_code": "deduplicated",
                "mandatory": row.mandatory, "origin": row.origin,
            })
    selected_coordinates = {row.coordinate for row in out[:CLOSURE_MAX]}
    candidate_rows = []
    for rank_no, row in enumerate(out, 1):
        selected = row.coordinate in selected_coordinates
        candidate_rows.append({
            "rank": rank_no, "doc_id": row.doc_id, "node": row.node,
            "doc": row.doc, "path": row.path, "origin": row.origin,
            "source_doc_id": row.source_doc_id,
            "source_node": row.source_node,
            "mandatory": row.mandatory,
            "selected": selected,
            "reason_code": "selected" if selected else "relation_cap_dropped",
        })
    return out[:CLOSURE_MAX], {
        "seed_count": len(seeds), "per_seed": audits,
        "candidate_rows": candidate_rows,
        "lifecycle": lifecycle,
        "candidate_count": len(out),
        "selected_count": min(len(out), CLOSURE_MAX),
    }


def _merge_with_required(cap: int,
                         preferred: list[termexplore.TermBranch],
                         required: list[termexplore.TermBranch],
                         *rest: list[termexplore.TermBranch]) \
        -> list[termexplore.TermBranch]:
    """필수 동반 좌표의 슬롯을 예약하면서 주 후보의 표시 순서를 보존한다."""
    limit = max(1, int(cap))
    required_unique = coordinates.merge(limit, required)
    required_coordinates = {row.coordinate for row in required_unique}
    regular, regular_coordinates = [], set()
    for group in (preferred, *rest):
        for row in group:
            if row.coordinate in required_coordinates:
                continue
            if row.coordinate not in regular_coordinates:
                regular.append(row)
                regular_coordinates.add(row.coordinate)
    regular = regular[:max(0, limit - len(required_unique))]
    # 질문의 직접 착지를 앞에 두고 필수 companion을 뒤에 붙이되, 둘 다 상한
    # 안에 남긴다. 나머지 보충 후보는 그 뒤의 잔여 슬롯만 쓴다.
    return coordinates.merge(limit, regular, required_unique)


def _coordinate_rows(rows) -> list[tuple[str, object]]:
    return [(row["doc_id"], row["node"]) if isinstance(row, dict)
            else (row.doc_id, row.node) for row in (rows or ())]


def _trace_reachability(trace, *, primary_meta, primary_channel,
                        assertion_meta, assertion_channel,
                        keyword_meta, keyword_channel,
                        expansion_meta, closure_channel,
                        reference_meta, reference_channel,
                        definition_dropped, selected) -> dict | None:
    """Attach a gold-free, behavior-neutral lifecycle trace to one retrieval."""
    if trace is None:
        return None

    canonical_set = lambda values: {trace.canonical(value) for value in values}

    trace.stage("query-source", "source", [])

    a_raw_rows = primary_meta.get("review_candidates") or [
        {"doc_id": row.doc_id, "node": row.node} for row in primary_channel]
    a_raw = _coordinate_rows(a_raw_rows)
    trace.stage("a-exact-retrieve", "retrieve", a_raw,
                parent_stage_ids=("query-source",))
    a_selected = _coordinate_rows(primary_channel)
    a_selected_set = canonical_set(a_selected)
    trace.stage(
        "a-exact-select", "select", a_selected,
        parent_stage_ids=("a-exact-retrieve",),
        discard_reasons={coordinate: "optional_review_dropped"
                         for coordinate in canonical_set(a_raw) - a_selected_set})

    for term in primary_meta.get("term_plan", {}).get("rejected") or ():
        trace.event("A_EXACT", "term-validation", "rejected",
                    "term_not_in_question", trigger_type="term",
                    trigger_value=term)
    for term in primary_meta.get("term_plan", {}).get(
            "rejected_operation_terms") or ():
        trace.event("A_EXACT", "operation-grounding", "rejected",
                    "operation_term_ungrounded", trigger_type="operation_term",
                    trigger_value=term)
    for locator in primary_meta.get("structure", {}).get(
            "unresolved_locators") or ():
        trace.event("A_EXACT", "explicit-structure", "failed",
                    "explicit_reference_unresolved", trigger_type="locator",
                    trigger_value=locator)
    selected_docs = {row["doc_id"] for row in
                     primary_meta.get("selected_documents") or ()}
    for row in primary_meta.get("routed_candidates") or ():
        accepted = row["doc_id"] in selected_docs
        trace.event(
            "A_EXACT", "document-routing",
            "selected" if accepted else "rejected",
            "selected" if accepted else "document_not_selected",
            raw_coordinate=(row["doc_id"], row["node"]),
            trigger_type="matched_terms", trigger_value=row.get("terms") or ())
    for rank, row in enumerate(a_raw_rows, 1):
        coordinate = (row["doc_id"], row["node"])
        accepted = trace.canonical(coordinate) in a_selected_set
        trace.event(
            "A_EXACT", "body-review", "selected" if accepted else "rejected",
            "selected" if accepted else "optional_review_dropped",
            raw_coordinate=coordinate, rank=rank,
            mandatory=bool(row.get("mandatory")),
            trigger_type="origin", trigger_value=row.get("origin") or "")

    b_raw_rows = assertion_meta.get("candidate_range_rows") or [
        {"doc_id": row.doc_id, "node": row.node} for row in assertion_channel]
    b_raw = _coordinate_rows(b_raw_rows)
    trace.stage("b-assertion-retrieve", "retrieve", b_raw,
                parent_stage_ids=("query-source",))
    b_selected = _coordinate_rows(assertion_channel)
    b_selected_set = canonical_set(b_selected)
    trace.stage(
        "b-assertion-select", "select", b_selected,
        parent_stage_ids=("b-assertion-retrieve",),
        discard_reasons={coordinate: "assertion_not_selected"
                         for coordinate in canonical_set(b_raw) - b_selected_set})
    for row in assertion_meta.get("assertion_hit_rows") or ():
        trace.event(
            "B_ASSERTION", "assertion-hit",
            "selected" if row.get("routed") else "rejected",
            "selected" if row.get("routed") else "wrong_document_family",
            raw_coordinate=(row["doc_id"], row["node"]),
            trigger_type="assertion_id", trigger_value=row.get("assertion_id"),
            score=float(row.get("strength") or 0))
    for rank, row in enumerate(b_raw_rows, 1):
        coordinate = (row["doc_id"], row["node"])
        accepted = trace.canonical(coordinate) in b_selected_set
        trace.event(
            "B_ASSERTION", "provision-selection",
            "selected" if accepted else "rejected",
            "selected" if accepted else "article_not_selected",
            raw_coordinate=coordinate, rank=rank,
            score=float(row.get("strength") or 0),
            trigger_type="signals", trigger_value=row.get("signals") or ())
    if not b_raw:
        fallback = assertion_meta.get("fallback") or ""
        trace.event(
            "B_ASSERTION", "assertion-retrieval", "failed",
            "no_assertion_match" if "canonical" in fallback else "tree_route_failed",
            trigger_type="fallback", trigger_value=fallback)

    c_ranked = keyword_meta.get("ranked_article_candidates") or [
        {"doc_id": row.doc_id, "node": row.node, "rank": pos,
         "selected": True, "reason_code": "selected"}
        for pos, row in enumerate(keyword_channel, 1)]
    c_raw = _coordinate_rows(c_ranked)
    trace.stage("c-keyword-retrieve", "retrieve", c_raw,
                parent_stage_ids=("query-source",))
    c_selected = _coordinate_rows(keyword_channel)
    c_selected_set = canonical_set(c_selected)
    trace.stage(
        "c-keyword-select", "select", c_selected,
        parent_stage_ids=("c-keyword-retrieve",),
        discard_reasons={coordinate: "article_cap_dropped"
                         for coordinate in canonical_set(c_raw) - c_selected_set})
    for row in keyword_meta.get("raw_hit_attempts") or ():
        raw = ((row["doc_id"], row["node"])
               if row.get("node") is not None else None)
        article = ((row["doc_id"], row["article_node"])
                   if row.get("article_node") is not None else None)
        trace.event(
            "C_BM25", "block-hit",
            "generated" if row.get("accepted") else "rejected",
            row.get("reason_code") or "generated",
            raw_coordinate=raw, article_coordinate=article,
            trigger_type="matched_terms", trigger_value=row.get("matched") or (),
            score=float(row.get("score") or 0),
            detail={"block": row.get("block")})
    for row in c_ranked:
        trace.event(
            "C_BM25", "article-ranking",
            "selected" if row.get("selected") else "rejected",
            row.get("reason_code") or "article_cap_dropped",
            raw_coordinate=(row["doc_id"], row["node"]),
            rank=int(row.get("rank") or 0),
            score=float(row.get("max_score") or 0),
            trigger_type="matched_terms", trigger_value=row.get("matched") or ())
    if not c_raw:
        trace.event("C_BM25", "keyword-retrieval", "failed",
                    "no_node_hit", trigger_type="keywords",
                    trigger_value=keyword_meta.get("keywords") or ())

    abc = list(dict.fromkeys((*a_selected, *b_selected, *c_selected)))
    trace.stage("abc-union", "union", abc, parent_stage_ids=(
        "a-exact-select", "b-assertion-select", "c-keyword-select"))

    d_candidates = expansion_meta.get("candidate_rows") or [
        {"doc_id": row.doc_id, "node": row.node, "selected": True,
         "reason_code": "selected"} for row in closure_channel]
    d_raw_only = _coordinate_rows(d_candidates)
    d_raw = list(dict.fromkeys((*abc, *d_raw_only)))
    trace.stage("d-relation-retrieve", "expand", d_raw,
                parent_stage_ids=("abc-union",))
    d_selected_only = _coordinate_rows(closure_channel)
    d_selected = list(dict.fromkeys((*abc, *d_selected_only)))
    trace.stage(
        "d-relation-select", "select", d_selected,
        parent_stage_ids=("d-relation-retrieve",),
        discard_reasons={coordinate: "relation_cap_dropped"
                         for coordinate in canonical_set(d_raw)
                         - canonical_set(d_selected)})
    for row in expansion_meta.get("lifecycle") or ():
        coordinate = ((row.get("doc_id"), row.get("node"))
                      if row.get("doc_id") and row.get("node") is not None else None)
        source = ((row.get("source_doc_id"), row.get("source_node"))
                  if row.get("source_doc_id") and row.get("source_node") is not None
                  else None)
        trace.event(
            "D_CLOSURE", "relation-expansion", row.get("decision") or "failed",
            row.get("reason_code") or "relation_unresolved",
            raw_coordinate=coordinate, source_coordinate=source,
            mandatory=bool(row.get("mandatory")),
            trigger_type="origin", trigger_value=row.get("origin") or "")
    for row in d_candidates:
        source = ((row.get("source_doc_id"), row.get("source_node"))
                  if row.get("source_doc_id") and row.get("source_node") is not None
                  else None)
        trace.event(
            "D_CLOSURE", "relation-selection",
            "selected" if row.get("selected") else "rejected",
            row.get("reason_code") or "relation_cap_dropped",
            raw_coordinate=(row["doc_id"], row["node"]),
            source_coordinate=source, rank=int(row.get("rank") or 0),
            mandatory=bool(row.get("mandatory")),
            trigger_type="origin", trigger_value=row.get("origin") or "")

    rescue_only = _coordinate_rows(reference_channel)
    rescue_after = list(dict.fromkeys((*d_selected, *rescue_only)))
    trace.stage("reference-rescue-expand", "expand", rescue_after,
                parent_stage_ids=("d-relation-select",))
    rescue_selected = canonical_set(rescue_only)
    for rank, row in enumerate(reference_meta.get("candidates") or (), 1):
        coordinate = (row["doc_id"], row["node"])
        accepted = trace.canonical(coordinate) in rescue_selected
        trace.event(
            "REFERENCE_RESCUE", "reference-verification",
            "selected" if accepted else "rejected",
            "selected" if accepted else (
                "reference_ambiguous" if "ambiguous" in str(
                    reference_meta.get("fallback") or "") else "reference_no_match"),
            raw_coordinate=coordinate, rank=rank,
            trigger_type="matched_terms", trigger_value=row.get("matched") or ())
    if not rescue_only:
        fallback = reference_meta.get("fallback") or ""
        trace.event(
            "REFERENCE_RESCUE", "reference-verification", "skipped",
            "reference_ambiguous" if "ambiguous" in fallback else (
                "no_remaining_slot" if "slot" in fallback else "not_applicable"),
            trigger_type="fallback", trigger_value=fallback)

    final_coordinates = _coordinate_rows(selected)
    definition_coordinates = canonical_set(
        (row["doc_id"], row["node"]) for row in definition_dropped)
    parent = canonical_set(rescue_after)
    final_set = canonical_set(final_coordinates)
    trace.stage(
        "required-merge-select", "select", final_coordinates,
        parent_stage_ids=("reference-rescue-expand",),
        discard_reasons={coordinate: (
            "definition_compacted" if coordinate in definition_coordinates
            else "final_cap_dropped") for coordinate in parent - final_set})
    for rank, coordinate in enumerate(rescue_after, 1):
        accepted = trace.canonical(coordinate) in final_set
        trace.event(
            "MERGE", "required-merge", "selected" if accepted else "rejected",
            "selected" if accepted else (
                "definition_compacted" if trace.canonical(coordinate)
                in definition_coordinates
                else "final_cap_dropped"),
            raw_coordinate=coordinate, rank=rank)

    trace.stage("scope-filter", "filter", final_coordinates,
                parent_stage_ids=("required-merge-select",))
    trace.stage("present", "present", final_coordinates,
                parent_stage_ids=("scope-filter",))
    for rank, coordinate in enumerate(final_coordinates, 1):
        trace.event("PRESENT", "context-presentation", "selected", "selected",
                    raw_coordinate=coordinate, rank=rank)
    return trace.capture()


def retrieve(index: Index, question: str, registry, *, llm,
             assertion_llm=None, cap: int = 20, shortcut_index=None,
             feedback_enabled: bool = False, reachability_trace=None) \
        -> tuple[list[Section], dict]:
    """LegalClosure v2 채널을 실행하고 조문 중복을 제거한 최대 ``cap``개를 반환한다."""
    # API가 씌운 사용자 scope가 있으면 보존한다. scope가 없는 직접 호출만
    # 기본 현행 범위(구판 제외)로 접는다.
    index = index if index.scope is not None else index.scoped(None)
    full_index = index
    primary_sections, primary_meta = termexplore.retrieve(
        index, question, llm=llm, cap=PRIMARY_CAP)
    terms = tuple(primary_meta.get("term_plan", {}).get("used_terms") or ())
    primary = coordinates.branches_from_sections(
        index, primary_sections, terms, origin="exact-structural")

    assertion_sections, assertion_meta = _assertion_channel(
        full_index, question, registry, llm=assertion_llm or llm,
        shortcut_index=shortcut_index)
    assertion = coordinates.branches_from_sections(
        index, assertion_sections, terms, origin="assertion-tree")

    keyword_plan = general_search.extract_keywords(None, question)
    # 질문 원문 검증을 통과한 1차 용어를 항상 보존하고, 검색어 모델 출력은
    # 보충만 한다. 생성 결과의 작은 변동이 이미 확인된 anchor를 지우면 안 된다.
    keywords = tuple(dict.fromkeys((
        *terms, *_context_terms(question))))
    keyword, keyword_meta = _keyword_articles(index, question, keywords)

    primary_channel = list(primary)
    assertion_channel = list(assertion)
    keyword_channel = list(keyword)

    # 직접 참조 중 질문/검색어가 실제로 다시 맞는 조문과 법적 필수 관계를 먼저
    # 보존한다. 단순 인접·우연한 인용은 이 단계에서 상한을 차지하지 않는다.
    closure, expansion_meta = _supplemental_closure(
        index, coordinates.merge(
            PRIMARY_CAP + ASSERTION_CAP + KEYWORD_ARTICLES_MAX,
            primary, assertion, keyword),
        tuple(dict.fromkeys((*terms, *keywords))))
    closure_channel = list(closure)

    definition_compaction_on = switches.is_on("legalclosure_definition_compaction")
    definition_dropped = []
    if definition_compaction_on:
        primary, dropped = _without_definition_articles(index, question, primary)
        definition_dropped.extend(dropped)
        assertion, dropped = _without_definition_articles(index, question, assertion)
        definition_dropped.extend(dropped)
        keyword, dropped = _without_definition_articles(index, question, keyword)
        definition_dropped.extend(dropped)
        closure, dropped = _without_definition_articles(index, question, closure)
        definition_dropped.extend(dropped)

    reference_rescue, reference_rescue_meta = legal_references.requirement_rescue(
        index, question, assertion, tuple(dict.fromkeys((*terms, *keywords))),
        cap=max(0, cap - len(coordinates.merge(
            cap, primary, assertion, keyword, closure))),
        question_terms=_question_terms(question))
    if definition_compaction_on:
        reference_rescue, dropped = _without_definition_articles(
            index, question, reference_rescue)
        definition_dropped.extend(dropped)

    # 정확/명시 결과와 Assertion 기준선을 먼저 보존한다. 남는 슬롯만 BM25와
    # 직접 관계 폐쇄로 채워 보충 채널이 기준선 정답을 밀어내지 못하게 한다.
    mandatory_closure = [row for row in closure if row.mandatory]
    optional_closure = [row for row in closure if not row.mandatory]
    selected = _merge_with_required(
        cap, coordinates.merge(cap, primary, assertion, keyword),
        mandatory_closure, optional_closure, reference_rescue)

    feedback_meta = {"enabled": False, "ran": False}
    if feedback_enabled:
        selected, feedback_meta = retrieval_feedback.run(
            index, question, llm, selected,
            tuple(dict.fromkeys((*terms, *keywords))), cap=cap)
        if definition_compaction_on:
            selected, dropped = _without_definition_articles(
                index, question, selected)
            definition_dropped.extend(dropped)
        # 새 점프 착지도 같은 법적 closure 규칙을 거쳐야 최초 회수와 재탐색의
        # 의미가 달라지지 않는다. 특히 점프로 본법만 잡은 경우 시행령을 닫는다.
        feedback_closure, feedback_expansion = _supplemental_closure(
            index, selected, tuple(dict.fromkeys((*terms, *keywords))))
        if definition_compaction_on:
            feedback_closure, dropped = _without_definition_articles(
                index, question, feedback_closure)
            definition_dropped.extend(dropped)
        feedback_required = [row for row in feedback_closure if row.mandatory]
        feedback_optional = [row for row in feedback_closure if not row.mandatory]
        selected = _merge_with_required(
            cap, selected, feedback_required, feedback_optional)
        feedback_meta["post_closure"] = feedback_expansion
    trace_started = time.perf_counter()
    reachability_capture = _trace_reachability(
        reachability_trace,
        primary_meta=primary_meta, primary_channel=primary_channel,
        assertion_meta=assertion_meta, assertion_channel=assertion_channel,
        keyword_meta=keyword_meta, keyword_channel=keyword_channel,
        expansion_meta=expansion_meta, closure_channel=closure_channel,
        reference_meta=reference_rescue_meta,
        reference_channel=reference_rescue,
        definition_dropped=definition_dropped, selected=selected)
    reachability_elapsed_ms = round(
        (time.perf_counter() - trace_started) * 1000, 3)
    text_cache = {}
    annotations = legal_evidence.annotate(
        index, question, selected, text_cache=text_cache)
    annotations_by_coordinate = {
        (row["doc_id"], row["node"]): row for row in annotations["rows"]}
    sections = [Section(
        n=0, doc_id=row.doc_id, doc=row.doc, node=row.node,
        path=row.path, page=index.docs[row.doc_id].by_id[row.node].get("page"),
        kind="법률좌표폐쇄", matched=row.origin,
        text=text_cache[row.coordinate],
        ref_src=({"doc_id": row.source_doc_id, "node": row.source_node,
                  "via": "legalclosure"}
                 if row.source_doc_id else None),
        legal_meta=annotations_by_coordinate.get(row.coordinate, {}),
        content_provenance=_artifact(index, row.doc_id),
    ) for row in selected]
    definition_context = (_attach_definition_context(
        index, question, sections,
        # 정의 부록은 새 정의 확장이 아니다. 실제 회수 채널에서 정의 조를
        # 제거한 문서에만 그 압축 대체재를 돌려준다.
        eligible_doc_ids={row["doc_id"] for row in definition_dropped})
        if definition_compaction_on else [])
    meta = {
        "strategy": "exact+assertion+keyword+unified-relation-closure",
        "cap": cap, "primary": primary_meta,
        "assertion": assertion_meta,
        "keyword_plan": keyword_plan.as_dict(), "keyword": keyword_meta,
        "expansion": expansion_meta,
        "feedback_loop": feedback_meta,
        "reference_verifier": reference_rescue_meta,
        "legal_annotations": annotations,
        "definition_context": {
            "enabled": definition_compaction_on,
            "direct_definition_question": definitions.is_definition_question(question),
            "dropped": definition_dropped,
            "dropped_count": len(definition_dropped),
            "appendix": definition_context,
            "appendix_count": len(definition_context),
        },
        "closure": [{"doc_id": row.doc_id, "node": row.node,
                     "doc": row.doc, "path": row.path,
                     "mandatory": row.mandatory, "terms": list(row.terms)}
                    for row in closure],
        "selected": [{"doc_id": row.doc_id, "node": row.node,
                      "doc": row.doc, "path": row.path,
                      "origin": row.origin} for row in selected],
        "article_reachability": reachability_capture,
        "article_reachability_elapsed_ms": reachability_elapsed_ms,
    }
    enrich_content_provenance(index, meta)
    content_snapshot = _snapshot(index)
    if content_snapshot is not None:
        meta["content_snapshot"] = content_snapshot.compact_receipt()
    return sections, meta
