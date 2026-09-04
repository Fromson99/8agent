from lawrag.core.domain_graph.freshness import audit
from lawrag.core.domain_graph.tier1 import (
    Tier1Assertion,
    Tier1Concept,
    Tier1Registry,
)
from lawrag.core.rag.index import Index


def _doc(name, status, articles):
    nodes, blocks = [], []
    for pos, surface in enumerate(articles, 1):
        nodes.append({"id": pos, "parent": None, "level": 1,
                      "family": "kr_article", "surface": surface,
                      "title": "", "span": [pos - 1, pos]})
        blocks.append({"idx": pos - 1, "node": pos, "kind": "text",
                       "text": surface})
    return {"name": name, "status": status}, {"nodes": nodes, "blocks": blocks}


def test_freshness_marks_brand_new_current_article_without_assertion():
    old_meta, old_result = _doc("시험법", "구판", ["제1조"])
    new_meta, new_result = _doc("시험법", "현행", ["제1조", "제2조"])
    index = Index.from_docs([
        ("old", old_meta, old_result), ("new", new_meta, new_result),
    ])
    concepts = {
        "concept:act": Tier1Concept(
            "concept:act", "행위", "action", "active", approved_by="test"),
    }
    registry = Tier1Registry(concepts=concepts, assertions=[
        Tier1Assertion(
            "assertion:old", "active", {"PREDICATE": ("concept:act",)},
            {"doc_id": "old", "node": 1}, approved_by="test"),
    ])

    report = audit(index, registry)

    assert report["current_articles"] == 2
    assert report["represented_articles"] == 1
    assert report["new_articles_missing"] == 1
    assert report["refresh_targets"] == [{
        "doc_id": "new", "document": "시험법", "article": "제2조", "node": 2,
        "reason": "new-article-assertion-missing",
    }]
    assert report["stale_assertion_sources"] == 1
