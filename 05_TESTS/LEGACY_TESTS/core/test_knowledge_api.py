"""컴파일 지식 그래프 뷰 API는 원본 그래프를 바꾸지 않고 타입 관계만 제한해 낸다."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("fastapi", reason="FastAPI 필요")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lawrag.api.routers import knowledge
from lawrag.core.domain_graph.model import Edge, Node
from lawrag.core.domain_graph.store import GraphStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "graph.sqlite"
    with GraphStore(path) as store:
        for node in (
            Node("lexeme:explain", "Lexeme", "설명의무", {"knowledge_grade": 2}),
            Node("concept:explain", "Concept", "설명의무",
                 {"knowledge_grade": 1, "concept_type": "domain_term"}),
            Node("assertion:duty", "Assertion", "설명하여야 한다",
                 {"knowledge_grade": 2}),
            Node("section:19", "Section", "제19조(설명의무)",
                 {"doc_id": "finance", "node": 19, "knowledge_grade": 3}),
            Node("concept:noise", "Concept", "다른 개념"),
        ):
            store.put_node(node)
        for edge in (
            Edge("edge:normal", "NORMALIZES_TO", "lexeme:explain", "concept:explain"),
            Edge("edge:predicate", "PREDICATE", "assertion:duty", "concept:explain"),
            Edge("edge:support", "SUPPORTED_BY", "assertion:duty", "section:19"),
            # 실험·불확정 간선은 UI 계약에서 제외한다.
            Edge("edge:maybe", "MAY_REFER_TO", "concept:explain", "concept:noise"),
        ):
            store.put_edge(edge)
        store.set_meta("built_at", "2026-08-25T00:00:00Z")
        store.conn.commit()
    monkeypatch.setenv("DOMAIN_GRAPH_DB", str(path))
    app = FastAPI()
    app.include_router(knowledge.router)
    return TestClient(app)


def test_summary_exposes_four_layers(client):
    payload = client.get("/v1/knowledge/summary").json()
    assert payload["total_nodes"] == 5
    assert payload["total_edges"] == 4
    assert payload["layers"] == {
        "meaning": 3, "rule": 1, "source": 1, "evidence": 0,
    }


def test_search_returns_exact_concept_first_with_degree(client):
    response = client.get("/v1/knowledge/search", params={"q": "설명의무"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["id"] == "concept:explain"
    assert result["degree"] == 3  # 불확정 간선도 원본 그래프 degree에는 정직하게 포함


def test_neighborhood_keeps_typed_chain_and_drops_uncertain_edge(client):
    response = client.get("/v1/knowledge/neighborhood", params={
        "id": "concept:explain", "depth": 2, "limit": 40,
    })
    assert response.status_code == 200
    payload = response.json()
    assert {n["id"] for n in payload["nodes"]} == {
        "concept:explain", "lexeme:explain", "assertion:duty", "section:19",
    }
    assert {e["kind"] for e in payload["edges"]} == {
        "NORMALIZES_TO", "PREDICATE", "SUPPORTED_BY",
    }


def test_missing_graph_and_missing_node_are_explicit(client, monkeypatch, tmp_path):
    missing = tmp_path / "missing.sqlite"
    monkeypatch.setenv("DOMAIN_GRAPH_DB", str(missing))
    assert client.get("/v1/knowledge/summary").status_code == 404
    monkeypatch.setenv("DOMAIN_GRAPH_DB", str(tmp_path / "graph.sqlite"))
    assert client.get("/v1/knowledge/neighborhood", params={
        "id": "concept:missing", "limit": 20,
    }).status_code == 404
