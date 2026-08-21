import json

from lawrag.core.domain_graph.builder import GraphBuilder, section_id
from lawrag.core.domain_graph.canonical import CanonicalRegistry
from lawrag.core.domain_graph.model import lexeme_id
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.rag.index import Index


def _index():
    nodes = [
        {"id": 1, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제1조", "title": "투자설명서의 교부", "ordinal": [1],
         "page": 1, "block": 0, "span": [0, 3]},
        {"id": 2, "parent": 1, "level": 1, "family": "circled",
         "surface": "③", "title": "", "ordinal": [3],
         "page": 1, "block": 1, "span": [1, 3]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "제1조(투자설명서의 교부)", "kind": "text", "node": 1},
        {"idx": 1, "page": 1, "text": "③ 증권의 발행인 또는 금융투자업자는 일반청약자에게", "kind": "text", "node": 2},
        {"idx": 2, "page": 1, "text": "투자설명서를 전자우편으로 발송하여야 한다.", "kind": "text", "node": 2},
    ]
    return Index.from_docs([("sample", {"name": "증권발행규정", "kind": "law"},
                             {"nodes": nodes, "blocks": blocks})])


def test_graph_preserves_mentions_and_resolves_coordinates(tmp_path, monkeypatch):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "sample.jsonl").write_text(json.dumps({
        "jo": 1, "node": 2,
        "actor": "증권의 발행인 또는 금융투자업자",
        "act": "전자우편으로 발송", "target": "일반청약자",
        "object": "투자 설명서", "mode": "의무", "function": "절차",
        "proviso": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text(json.dumps({"terms": [{
        "term": "투자설명서", "key": "투자설명서",
        "surfaces": ["투자설명서", "투자 설명서"], "status": "활성",
        "confidence": "high", "occurrences": [{
            "doc_id": "sample", "node": 2, "surface": "투자설명서",
            "block": 2, "page": 1, "via": "정의",
        }],
    }]}, ensure_ascii=False), encoding="utf-8")
    delegation = tmp_path / "delegation.json"
    delegation.write_text('{"edges": []}', encoding="utf-8")
    monkeypatch.setenv("RAG_DELEGATION_STORE", str(delegation))

    registry = CanonicalRegistry.load(glossary_path=glossary)
    db = tmp_path / "graph.sqlite"
    result = GraphBuilder(_index(), data_dir=tmp_path, registry=registry,
                          glossary_path=glossary).build(db)

    assert result["frames"] == 1
    with GraphStore(db, readonly=True) as store:
        coordinate = store.resolve("제1조제3항", doc_id="sample")
        assert any(x["target"]["id"] == section_id("sample", 2) for x in coordinate)

        object_hits = store.resolve("투자 설명서", doc_id="sample")
        concepts = [x for x in object_hits if x["relation"] == "NORMALIZES_TO"]
        assert len(concepts) == 1
        assert concepts[0]["target"]["label"] == "투자설명서"

        incoming = store.neighbors(lexeme_id("투자 설명서"), direction="in",
                                   kinds=("HAS_LEXEME",))
        mention_labels = {store.get_node(edge["src"])["label"] for edge in incoming}
        assert "투자 설명서" in mention_labels

        section_edges = store.neighbors(section_id("sample", 2))
        assert any(edge["kind"] == "HAS_FRAME" for edge in section_edges)
        assert any(edge["kind"] == "HAS_MENTION" for edge in section_edges)


def test_unregistered_frame_value_stays_lexeme_not_concept(tmp_path, monkeypatch):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "sample.jsonl").write_text(json.dumps({
        "jo": 1, "node": 2, "actor": "금융투자업자", "act": "임의 표현",
        "target": "", "object": "", "mode": "의무", "function": "절차",
        "proviso": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    delegation = tmp_path / "delegation.json"
    delegation.write_text('{"edges": []}', encoding="utf-8")
    monkeypatch.setenv("RAG_DELEGATION_STORE", str(delegation))

    db = tmp_path / "graph.sqlite"
    GraphBuilder(_index(), data_dir=tmp_path,
                 registry=CanonicalRegistry(), glossary_path=glossary).build(db)
    with GraphStore(db, readonly=True) as store:
        assert store.get_node(lexeme_id("임의 표현"))["kind"] == "Lexeme"
        assert store.resolve("임의 표현") == []
