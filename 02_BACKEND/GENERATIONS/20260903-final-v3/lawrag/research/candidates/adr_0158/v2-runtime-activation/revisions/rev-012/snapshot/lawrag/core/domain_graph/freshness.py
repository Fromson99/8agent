"""현행 법령 조문과 canonical Assertion 출처의 개정 정합성 진단."""

from __future__ import annotations

import re

from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag.index import Index


_ARTICLE = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")


def _article_root(view, node: object) -> object | None:
    current = view.by_id.get(node)
    seen = set()
    while current is not None and current.get("id") not in seen:
        seen.add(current.get("id"))
        if _ARTICLE.fullmatch(str(current.get("surface") or "").strip()):
            return current.get("id")
        current = view.by_id.get(current.get("parent"))
    return None


def _articles(view) -> dict[str, object]:
    out = {}
    for node in view.nodes:
        surface = str(node.get("surface") or "").strip()
        if _ARTICLE.fullmatch(surface) and "부칙" not in (view.path(node.get("id")) or ""):
            out.setdefault(surface, node.get("id"))
    return out


def audit(index: Index, registry: Tier1Registry, *, detail_limit: int = 100) -> dict:
    """신설·현행 조문 중 Assertion 출처가 없는 좌표와 구판 출처를 센다.

    동일 법령명·동일 조 번호는 legalclosure가 현행본으로 재결합할 수 있으므로
    ``represented``로 본다. 현행본에만 생긴 새 조 번호는 별도 refresh 대상으로
    남긴다.
    """
    current_index = index.scoped(None)
    current_docs = current_index.entry_docs
    current_ids = set(current_docs)
    old_articles: dict[str, set[str]] = {}
    for doc_id, view in index.docs.items():
        if doc_id not in current_ids:
            old_articles.setdefault(view.name, set()).update(_articles(view))

    represented: set[tuple[str, str]] = set()
    stale_sources = 0
    orphaned_sources = 0
    for assertion in registry.active_assertions:
        doc_id = str(assertion.source.get("doc_id") or "")
        node = assertion.source.get("node")
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            orphaned_sources += 1
            continue
        root = _article_root(view, node)
        if root is None:
            orphaned_sources += 1
            continue
        surface = str(view.by_id[root].get("surface") or "").strip()
        represented.add((view.name, surface))
        if doc_id not in current_ids:
            stale_sources += 1

    missing, new_missing = [], []
    unrepresented_documents = set()
    current_article_count = 0
    for doc_id, view in current_docs.items():
        for surface, node in _articles(view).items():
            current_article_count += 1
            if (view.name, surface) in represented:
                continue
            item = {
                "doc_id": doc_id, "document": view.name,
                "article": surface, "node": node,
                "reason": "canonical-assertion-missing",
            }
            missing.append(item)
            if view.name in old_articles and surface not in old_articles[view.name]:
                new_missing.append({**item, "reason": "new-article-assertion-missing"})
            elif view.name not in old_articles:
                unrepresented_documents.add(view.name)

    return {
        "current_documents": len(current_docs),
        "current_articles": current_article_count,
        "represented_articles": current_article_count - len(missing),
        "missing_articles": len(missing),
        "new_articles_missing": len(new_missing),
        "unrepresented_documents": len(unrepresented_documents),
        "stale_assertion_sources": stale_sources,
        "orphaned_assertion_sources": orphaned_sources,
        "refresh_targets": new_missing[:max(0, int(detail_limit))],
        "missing_sample": missing[:max(0, int(detail_limit))],
    }
