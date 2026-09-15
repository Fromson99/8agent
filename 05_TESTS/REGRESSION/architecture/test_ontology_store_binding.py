from pathlib import Path


REPO = Path(__file__).resolve().parents[3]


def test_sealed_service_binds_ontology_stores_to_semantic_release() -> None:
    source = (REPO / "service.py").read_text(encoding="utf-8")
    assert '"RAG_LEGAL_GRAPH_STORE": semantic_root / "legal_graph"' in source
    assert '"RAG_DEFINITION_PROJECTION_STORE": (' in source
    assert 'semantic_root / "PROJECTIONS" / "DEFINITIONS"' in source
