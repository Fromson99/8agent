import json

from lawrag.core.domain_graph.builder import GraphBuilder, document_id, section_id
from lawrag.core.domain_graph.canonical import CanonicalRegistry
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.domain_graph import cli
from lawrag.core.rag import relations
from lawrag.core.rag.index import Index


def _index():
    law_nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "정의", "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "제출의무", "span": [1, 2]},
        {"id": 30, "parent": None, "level": 0, "surface": "부칙",
         "title": "", "span": [2, 4]},
        {"id": 31, "parent": 30, "level": 1, "surface": "제1조",
         "title": "적용례", "span": [3, 4]},
        {"id": 4, "parent": None, "level": 1, "surface": "제4조",
         "title": "과징금", "span": [4, 5]},
    ]
    law_blocks = [
        {"idx": 0, "node": 1, "text": '이 법에서 "사업자"란 등록한 회사를 말한다.'},
        {"idx": 1, "node": 2,
         "text": "사업자는 10일 이내에 서면으로 자료를 제출하여야 한다."},
        {"idx": 2, "node": 30, "text": "부칙"},
        {"idx": 3, "node": 31, "text": "제2조는 이 법 시행 후 제출부터 적용한다."},
        {"idx": 4, "node": 4,
         "text": "제2조를 위반한 자에게는 과징금을 부과할 수 있다."},
    ]
    decree_nodes = [{"id": 10, "parent": None, "level": 1,
                     "surface": "제10조", "title": "제출방법", "span": [0, 1]}]
    decree_blocks = [{"idx": 0, "node": 10,
                      "text": "법 제2조에 따른 제출방법은 전자문서로 한다."}]
    return Index.from_docs([
        ("law", {"name": "시험법", "kind": "law", "enforce": "20260101",
                 "revised": "20251201"},
         {"nodes": law_nodes, "blocks": law_blocks}),
        ("decree", {"name": "시험법 시행령", "kind": "law", "enforce": "20260101"},
         {"nodes": decree_nodes, "blocks": decree_blocks}),
    ])


def _write_inputs(tmp_path):
    (tmp_path / "delegation.json").write_text(json.dumps({"edges": [{
        "kind": "시행령",
        "src": {"doc_id": "law", "node": 2, "name": "시험법", "jo": "제2조"},
        "dst": {"doc_id": "decree", "node": 10,
                "name": "시험법 시행령", "jo": "제10조"},
        "link": "대통령령으로 정하는 제출방법",
    }]}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "law_index.json").write_text(json.dumps({"families": [{
        "root": "시험법", "members": [
            {"name": "시험법", "doc_id": "law", "held": True, "depth": 0},
            {"name": "시험법 시행령", "doc_id": "decree", "held": True, "depth": 1},
        ],
    }]}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "glossary.json").write_text('{"terms": []}', encoding="utf-8")


def test_bundle_unifies_reference_delegation_definition_sanction_and_time(tmp_path):
    _write_inputs(tmp_path)
    bundle = relations.build(
        _index(), delegation_file=tmp_path / "delegation.json",
        law_index_file=tmp_path / "law_index.json",
        include_requirements=True, use_cache=False)
    coordinates = {(row.kind, row.src_doc, row.src_node, row.dst_doc, row.dst_node)
                   for row in bundle.sections}

    assert ("DELEGATES_TO", "law", 2, "decree", 10) in coordinates
    assert ("USES_DEFINITION", "law", 2, "law", 1) in coordinates
    assert ("VIOLATION_SANCTIONED_BY", "law", 2, "law", 4) in coordinates
    assert ("APPLIES_TO", "law", 31, "law", 2) in coordinates
    assert {row.kind for row in bundle.requirements if row.node == 2} >= {
        "TIME", "QUANTITY", "METHOD"}
    assert any(row.kind == "IMPLEMENTED_BY" and row.src_doc == "law"
               and row.dst_doc == "decree" for row in bundle.graph)
    assert ("law", "VALID_FROM", "20260101") in {
        (row.doc_id, row.kind, row.value) for row in bundle.temporal}


def test_graph_builder_materializes_the_same_bundle(tmp_path):
    _write_inputs(tmp_path)
    db = tmp_path / "graph.sqlite"
    GraphBuilder(
        _index(), data_dir=tmp_path, registry=CanonicalRegistry(),
        glossary_path=tmp_path / "glossary.json").build(db)

    with GraphStore(db, readonly=True) as store:
        duty_edges = store.neighbors(section_id("law", 2))
        assert {row["kind"] for row in duty_edges} >= {
            "DELEGATES_TO", "USES_DEFINITION", "VIOLATION_SANCTIONED_BY",
            "HAS_REQUIREMENT",
        }
        assert any(row["kind"] == "IMPLEMENTED_BY"
                   and row["dst"] == document_id("decree")
                   for row in store.neighbors(document_id("law")))
        assert any(row["kind"] == "VALID_FROM"
                   for row in store.neighbors(document_id("law")))
        assert store.counts()["nodes"]["Requirement"] > 0


def test_graph_cli_loads_saved_links_from_the_same_data_directory(tmp_path, monkeypatch):
    seen = {}

    class FakeIndex:
        @staticmethod
        def load(**kwargs):
            seen.update(kwargs)
            return object()

    class FakeRegistry:
        @staticmethod
        def load(**_kwargs):
            return object()

    class FakeBuilder:
        def __init__(self, *_args, **_kwargs):
            pass

        def build(self, *_args, **_kwargs):
            return {"ok": True}

    monkeypatch.setattr(cli, "Index", FakeIndex)
    monkeypatch.setattr(cli, "CanonicalRegistry", FakeRegistry)
    monkeypatch.setattr(cli, "GraphBuilder", FakeBuilder)
    cli.main([
        "build", "--output", str(tmp_path / "graph.sqlite"),
        "--structure", str(tmp_path / "structure"),
        "--glossary", str(tmp_path / "glossary.json"),
        "--data-dir", str(tmp_path), "--canonical", str(tmp_path / "canonical.json"),
    ])

    assert seen["links_file"] == tmp_path / "links.json"
