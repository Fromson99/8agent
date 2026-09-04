"""선택된 법률 좌표에서 규범기능상 필요한 고유 참조를 검증한다."""

from __future__ import annotations

from dataclasses import replace
import re

from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag.index import Index


_REFERENCE_FUNCTION = re.compile(r"위임|준용")
_GENERIC_REFERENCE_TERMS = frozenset({
    "업무", "문맥", "있는가", "있는", "결정", "결정을", "가능", "여부",
})


def article_outgoing(index: Index, branch: coordinates.Branch):
    """branch 조문 본문에서 실제로 나가는 확정 참조의 조문 root를 반환한다."""
    view = index.docs.get(branch.doc_id)
    if view is None or branch.node not in view.by_id:
        return
    root = coordinates.article_root(view, branch.node)
    span = view.by_id[root].get("span") or [0, 0]
    lo, hi = span[0], max(span[1], span[0] + 1)
    for edge in index.ref_edges().get(branch.doc_id, ()):
        if edge.get("src") != root and not (
                edge.get("block") is not None and lo <= edge["block"] < hi):
            continue
        target = coordinates.article_root(view, edge.get("dst"))
        if target in view.by_id:
            yield branch.doc_id, target, edge
    # 전역 20,502개를 seed마다 순회하지 않고 Index의 문서별 adjacency를 사용한다.
    for edge in index.cross_from(branch.doc_id):
        if edge.get("src") != root:
            continue
        target_view = index.docs.get(edge.get("dst_doc"))
        target = edge.get("dst")
        if target_view is None or target not in target_view.by_id:
            continue
        yield edge["dst_doc"], coordinates.article_root(target_view, target), edge


def requirement_rescue(index: Index, question: str,
                       assertion: list[coordinates.Branch],
                       terms: tuple[str, ...], *, cap: int,
                       question_terms: tuple[str, ...]) \
        -> tuple[list[coordinates.Branch], dict]:
    """준용·위임 질문에서 선택된 준용조가 가리킨 고유 표제 조문만 보충한다."""
    audit = {"eligible": False, "candidates": [], "selected": [],
             "fallback": ""}
    if cap <= 0 or not _REFERENCE_FUNCTION.search(question or ""):
        audit["fallback"] = "question_has_no_delegation_or_incorporation_function"
        return [], audit
    query_terms = tuple(dict.fromkeys(
        term for term in (*terms, *question_terms)
        if term not in _GENERIC_REFERENCE_TERMS
        and len(coordinates.packed(term)) >= 2))
    scored = {}
    for seed in assertion:
        source_view = index.docs[seed.doc_id]
        source_root = coordinates.article_root(source_view, seed.node)
        source_raw = source_view.by_id[source_root]
        source_heading = " ".join(filter(None, (
            str(source_raw.get("surface") or "").strip(),
            str(source_raw.get("title") or "").strip(),
        )))
        if "준용" not in source_heading:
            continue
        audit["eligible"] = True
        for doc_id, node, edge in article_outgoing(index, seed):
            view = index.docs[doc_id]
            raw = view.by_id[node]
            heading = " ".join(filter(None, (
                str(raw.get("surface") or "").strip(),
                str(raw.get("title") or "").strip(),
            )))
            matched = tuple(term for term in query_terms
                            if coordinates.contains_phrase(heading, term))
            if not matched:
                continue
            key = (doc_id, node)
            score = (max(len(coordinates.packed(term)) for term in matched),
                     len(matched))
            previous = scored.get(key)
            if previous is None or score > previous[0]:
                scored[key] = (score, seed, edge, heading, matched)
    ranked = sorted(scored.items(), key=lambda item: (
        -item[1][0][0], -item[1][0][1],
        index.docs[item[0][0]].name, item[1][3]))
    audit["candidates"] = [{
        "doc_id": doc_id, "node": node, "doc": index.docs[doc_id].name,
        "path": index.docs[doc_id].path(node), "heading": data[3],
        "matched": list(data[4]), "score": list(data[0]),
    } for (doc_id, node), data in ranked]
    if not ranked:
        audit["fallback"] = "no_referenced_heading_matches_question"
        return [], audit
    top_score = ranked[0][1][0]
    tied = [row for row in ranked if row[1][0] == top_score]
    if len(tied) != 1:
        audit["fallback"] = "ambiguous_top_referenced_headings"
        return [], audit
    (doc_id, node), (_score, seed, edge, _heading, matched) = tied[0]
    row = coordinates.article_branch(
        index, doc_id, node, terms, origin="normative-reference-verifier",
        reason=f"{index.docs[seed.doc_id].path(seed.node)}의 준용 → "
               f"{edge.get('surface') or index.docs[doc_id].path(node)}; "
               f"표제 일치={','.join(matched)}")
    if row is None:
        audit["fallback"] = "target_out_of_scope_or_missing"
        return [], audit
    row = replace(row, mandatory=True, mandatory_reason="verified-incorporation-reference",
                  source_doc_id=seed.doc_id, source_node=seed.node)
    audit["selected"] = [{"doc_id": row.doc_id, "node": row.node,
                           "doc": row.doc, "path": row.path}]
    return [row][:cap], audit
