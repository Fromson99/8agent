"""선택 근거 사이의 명시적 법률 연결을 색인 좌표로 재구성한다.

검색 점수나 문장 유사도가 아니라 실제 조문 참조 간선만 conclusion eligibility로
승격한다. 운영 배선 전 shadow 실험용이다.
"""

from __future__ import annotations

from collections import defaultdict, deque
import re
from typing import Any


_ARTICLE_SURFACE = re.compile(r"^제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?$")
_ARTICLE_MENTION = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_ARTICLE_PREFIX = re.compile(r"^\s*제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?\s*")
_CONCLUSION_RELATIONS = frozenset({"배제", "준용", "위임", "수임", "근거", "정의"})
_STRUCTURAL_ORIGINS = frozenset({"exact-structural", "assertion-tree"})
_LEXICAL_ORIGINS = frozenset({"keyword-bm25", "normative-reference-verifier"})
_EDGE_ROWS_CACHE: tuple[Any, list[dict[str, Any]]] | None = None


def _packed(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def enclosing_article(view, node: Any):
    current = view.by_id.get(node)
    while current is not None:
        surface = str(current.get("surface") or "").strip()
        if current.get("family") == "kr_article" or _ARTICLE_SURFACE.fullmatch(surface):
            return current.get("id")
        current = view.by_id.get(current.get("parent"))
    return None


def _edge_rows(index) -> list[dict[str, Any]]:
    global _EDGE_ROWS_CACHE
    if _EDGE_ROWS_CACHE is not None and _EDGE_ROWS_CACHE[0] is index:
        return _EDGE_ROWS_CACHE[1]
    rows = []
    for doc_id, edges in index.ref_edges().items():
        view = index.docs.get(doc_id)
        for edge in edges:
            relation = str(edge.get("rel") or "인용")
            if relation == "인용" and view is not None:
                article = enclosing_article(view, edge.get("src"))
                title = str((view.by_id.get(article) or {}).get("title") or "")
                if "준용" in title:
                    relation = "준용"
            rows.append({
                "src_doc": str(doc_id), "src": edge.get("src"),
                "dst_doc": str(doc_id), "dst": edge.get("dst"),
                "relation": relation,
                "surface": str(edge.get("surface") or ""),
            })
    # cross_from은 문서별 조회라 중복 없이 출발 문서에서 한 번씩 모은다.
    for doc_id in index.docs:
        for edge in index.cross_from(doc_id):
            rows.append({
                "src_doc": str(doc_id), "src": edge.get("src"),
                "dst_doc": str(edge.get("dst_doc") or ""),
                "dst": edge.get("dst"),
                "relation": str(edge.get("rel") or "인용"),
                "surface": str(edge.get("surface") or ""),
            })
    unique = {}
    for row in rows:
        key = (row["src_doc"], row["src"], row["dst_doc"], row["dst"],
               row["relation"], row["surface"])
        unique[key] = row
    result = list(unique.values())
    _EDGE_ROWS_CACHE = (index, result)
    return result


def _article_title(path: str) -> str:
    tail = str(path or "").split("▸")[-1]
    tail = re.sub(r"<[^>]*>", "", tail)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", _ARTICLE_PREFIX.sub("", tail)).casefold()


def _title_alignment(question: str, path: str) -> float:
    """질문 문맥이 조문 제목의 2-gram을 얼마나 덮는지 본다.

    어린 법령 표제("선임" 등)는 과대 승격을 막기 위해 제외한다.
    """
    title = _article_title(path)
    if len(title) < 4:
        return 0.0
    packed_question = re.sub(
        r"[^0-9A-Za-z가-힣]", "", str(question or "")).casefold()
    question_grams = {packed_question[i:i + 2]
                      for i in range(max(0, len(packed_question) - 1))}
    title_grams = {title[i:i + 2] for i in range(len(title) - 1)}
    return len(question_grams & title_grams) / len(title_grams) if title_grams else 0.0


def typed_connections(index, question: str,
                      evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """E번호별 연결 타입과 결론 승격 가능성을 반환한다."""
    coordinate_to_evidence: dict[tuple[str, Any], str] = {}
    rows_by_id = {}
    for row in evidence:
        evidence_id = str(row.get("id") or "")
        doc_id = str(row.get("doc_id") or "")
        view = index.docs.get(doc_id)
        article = enclosing_article(view, row.get("node")) if view is not None else None
        if article is not None:
            coordinate_to_evidence[(doc_id, article)] = evidence_id
        rows_by_id[evidence_id] = row

    links = []
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for edge in _edge_rows(index):
        src_view = index.docs.get(edge["src_doc"])
        dst_view = index.docs.get(edge["dst_doc"])
        if src_view is None or dst_view is None:
            continue
        src_article = enclosing_article(src_view, edge["src"])
        dst_article = enclosing_article(dst_view, edge["dst"])
        src_id = coordinate_to_evidence.get((edge["src_doc"], src_article))
        dst_id = coordinate_to_evidence.get((edge["dst_doc"], dst_article))
        if not src_id or not dst_id or src_id == dst_id:
            continue
        link = {"from": src_id, "to": dst_id,
                "relation": edge["relation"], "surface": edge["surface"]}
        links.append(link)
        adjacency[src_id].append((dst_id, link))
        reverse = {**link, "direction": "reverse"}
        adjacency[dst_id].append((src_id, reverse))

    question_packed = _packed(question)
    question_articles = {_packed(match.group(0))
                         for match in _ARTICLE_MENTION.finditer(question)}
    seed = str(evidence[0].get("id") or "E1") if evidence else ""
    paths: dict[str, list[dict[str, Any]]] = {seed: []} if seed else {}
    queue = deque([(seed, [])]) if seed else deque()
    while queue:
        current, path = queue.popleft()
        if len(path) >= 2:
            continue
        for target, link in adjacency.get(current, []):
            if target in paths:
                continue
            next_path = path + [link]
            paths[target] = next_path
            queue.append((target, next_path))

    out = {}
    for position, (evidence_id, row) in enumerate(rows_by_id.items(), 1):
        document = str(row.get("document") or "")
        path_text = str(row.get("path") or "")
        explicit_document = bool(_packed(document)
                                 and _packed(document) in question_packed)
        explicit_article = bool(question_articles & {
            _packed(match.group(0)) for match in _ARTICLE_MENTION.finditer(path_text)})
        path = paths.get(evidence_id, [])
        direct = path if len(path) == 1 else []
        direct_relations = {str(link.get("relation") or "") for link in direct}
        incident = [link for link in links
                    if evidence_id in {link["from"], link["to"]}]
        incident_relations = {str(link.get("relation") or "") for link in incident}
        explicit_target = explicit_document and (explicit_article or not question_articles)
        eligible = (position == 1 or explicit_target
                    or bool(direct_relations & _CONCLUSION_RELATIONS))
        if position == 1:
            role = "seed_governing_candidate"
        elif explicit_target:
            role = "question_explicit_target"
        elif direct_relations & _CONCLUSION_RELATIONS:
            role = "direct_typed_companion"
        elif direct:
            role = "direct_untyped_reference"
        elif path:
            role = "indirect_reference_context"
        elif incident_relations & _CONCLUSION_RELATIONS:
            role = "selected_pair_typed_context"
        elif incident:
            role = "selected_pair_reference_context"
        elif "supplemental-closure" in str(row.get("role") or ""):
            role = "supplemental_context"
        else:
            role = "parallel_search_context"
        origin = str(row.get("role") or "")
        title_alignment = _title_alignment(question, path_text)
        support_reasons = []
        if role == "direct_untyped_reference":
            support_reasons.append("direct_citation")
        if origin in _STRUCTURAL_ORIGINS:
            support_reasons.append("structural_retrieval")
        if origin in _LEXICAL_ORIGINS and title_alignment >= 0.7:
            support_reasons.append("issue_title_alignment")
        support_eligible = eligible or bool(support_reasons)
        if eligible:
            evidence_tier = "A_governing"
        elif support_eligible:
            evidence_tier = "B_candidate_support"
        else:
            evidence_tier = "C_context_only"
        out[evidence_id] = {
            "connection_role": role,
            "conclusion_eligible": eligible,
            "support_eligible": support_eligible,
            "evidence_tier": evidence_tier,
            "support_reasons": support_reasons,
            "title_alignment": round(title_alignment, 4),
            "explicit_target": explicit_target,
            "path_from_seed": path,
            "direct_relations": sorted(direct_relations),
            "incident_relations": sorted(incident_relations),
            "all_incident_links": incident,
        }
    return out


def attach_typed_connections(index, question: str,
                             evidence: list[dict[str, Any]]) \
        -> list[dict[str, Any]]:
    typed = typed_connections(index, question, evidence)
    out = []
    for row in evidence:
        copy = dict(row)
        copy["typed_connection"] = typed.get(str(row.get("id") or ""), {
            "connection_role": "unclassified_context",
            "conclusion_eligible": False,
            "support_eligible": False,
            "evidence_tier": "C_context_only",
            "support_reasons": [], "title_alignment": 0.0,
            "path_from_seed": [], "direct_relations": [],
            "incident_relations": [],
            "all_incident_links": [],
        })
        out.append(copy)
    return out
