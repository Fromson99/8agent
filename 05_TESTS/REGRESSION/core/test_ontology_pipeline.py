from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lawrag.api.routers import pipeline as pipeline_router
from lawrag.core import batch as batch_mod
from lawrag.core.legal_graph import stable_id, validate_row
from lawrag.core.legal_graph.compiler import (
    _Collector,
    _compile_structure,
    segment_clause_spans,
)
from lawrag.core.rag.index import Index
from lawrag.ontology import contract_report, lifecycle_snapshot, load_catalog, validate_catalog
from lawrag.ontology import lifecycle as lifecycle_mod
from lawrag.ontology.lifecycle import definition_projection_status


ROOT = Path(__file__).resolve().parents[3]


def _empty_lineup() -> dict:
    return {
        "documents": 0,
        "stages": {
            stage: {"pending": 0, "total": 0, "detail": [], "note": "ready"}
            for stage in batch_mod.STAGES
        },
    }


def test_lifecycle_catalog_covers_every_runner_stage_once_in_order():
    catalog = load_catalog()
    validate_catalog(catalog, runner_stages=batch_mod.STAGES)
    mapped = [
        stage["runner_stage"]
        for stage in catalog["stages"]
        if stage.get("runner_stage")
    ]
    assert mapped == list(batch_mod.STAGES)
    assert set(batch_mod.AUTO_STAGES) < set(batch_mod.STAGES)
    assert {"legal_graph", "definition_projections"}.isdisjoint(batch_mod.AUTO_STAGES)
    assert all(stage["auto_promote"] is False for stage in catalog["stages"])


def test_lifecycle_snapshot_is_the_five_user_phases():
    snapshot = lifecycle_snapshot(_empty_lineup())
    assert [phase["id"] for phase in snapshot["phases"]] == [
        "input", "extract", "transform", "use", "restructure"
    ]
    assert snapshot["stages"]["legal-graph"]["runner_stage"] == "legal_graph"
    assert snapshot["stages"]["release"]["status"] == "gated"
    assert snapshot["manual_stages"] == ["release", "feedback"]


def test_machine_contracts_validate_without_projection_records(tmp_path):
    projection_root = tmp_path / "definitions"
    projection_root.mkdir()
    report = contract_report(projection_root=projection_root)
    assert report["ok"], report
    assert report["checks"][-1]["records"] == 0


def test_definition_projection_store_reports_invalid_records(tmp_path):
    projection_root = tmp_path / "definitions"
    projection_root.mkdir()
    example = json.loads(
        (ROOT / "01_DATA/CONTRACTS/definition-projection-v1.example.json").read_text("utf-8")
    )
    (projection_root / "valid.json").write_text(
        json.dumps(example, ensure_ascii=False), encoding="utf-8"
    )
    invalid = dict(example)
    invalid["status"] = "READY"
    invalid["completeness"] = dict(example["completeness"])
    invalid["completeness"]["verification_receipt_sha256"] = None
    (projection_root / "invalid.json").write_text(
        json.dumps(invalid, ensure_ascii=False), encoding="utf-8"
    )
    status = definition_projection_status(projection_root)
    assert status["total"] == 2 and status["valid"] == 1 and status["invalid"] == 1
    assert status["detail"][0]["file"] == "invalid.json"


def test_definition_main_binding_reads_canonical_main_state(monkeypatch):
    from lawrag.platform import main_promotion

    monkeypatch.setattr(
        main_promotion,
        "load_state",
        lambda: {
            "runtime_profile": "ontology-rag-v1",
            "generation": 3,
            "active_promotion_id": "main-test",
            "switches": {"legalclosure_main": True},
        },
    )
    status = lifecycle_mod._definition_main_binding()
    assert status == {
        "runtime_wired": True,
        "runtime_profile": "ontology-rag-v1",
        "main_generation": 3,
        "main_promotion_id": "main-test",
        "main_status": "MAIN 배선됨 (ontology-rag-v1 · gen 3)",
    }


def test_clause_span_split_preserves_exact_source_offsets():
    text = "제10조(정의) 이 법에서 A란 등록한 자를 말한다. 다만, 국가기관은 제외한다."
    spans = segment_clause_spans(text)
    values = [(text[start:end], kind) for start, end, kind in spans]
    assert values == [
        ("제10조(정의) 이 법에서 A란 등록한 자를 말한다.", "CLAUSE"),
        ("다만, 국가기관은 제외한다.", "PROVISO"),
    ]
    assert all(text[start:end] == value for (start, end, _), (value, _) in zip(spans, values))


def test_clause_span_split_handles_concatenated_korean_sentences():
    text = "첫 번째 의무를 이행하여야 한다.두 번째 의무도 이행하여야 한다."
    assert [text[start:end] for start, end, _ in segment_clause_spans(text)] == [
        "첫 번째 의무를 이행하여야 한다.",
        "두 번째 의무도 이행하여야 한다.",
    ]


def test_clause_span_compiler_reads_body_blocks_and_preserves_unit_parentage(tmp_path):
    result = {
        "nodes": [
            {
                "id": 1,
                "parent": None,
                "level": 0,
                "family": "kr_article",
                "surface": "제10조",
                "title": "정의",
                "block": 0,
                "span": [0, 2],
                "coordinate_key": "body:제10조",
            },
            {
                "id": 2,
                "parent": 1,
                "level": 1,
                "family": "circled",
                "surface": "①",
                "title": "",
                "block": 2,
                "span": [2, 3],
                "coordinate_key": "body:제10조제1항",
            },
        ],
        "blocks": [
            {"idx": 0, "node": 1, "text": "제10조(정의)"},
            {"idx": 1, "node": 1, "text": "이 법에서 등록기관이란 허가받은 자를 말한다."},
            {"idx": 2, "node": 2, "text": "① 등록기관은 장부를 보존하여야 한다."},
        ],
    }
    index = Index.from_docs(
        [("doc-1", {"name": "예시 법률", "kind": "law", "status": "현행"}, result)],
        authority_generation="a" * 64,
        apply_structure_fixes=False,
    )
    collector = _Collector(tmp_path, "generation-test", "a" * 64)
    _compile_structure(collector, index, {"doc-1"})

    spans = collector.rows["canonical/clause_spans.jsonl"]
    assert [(row["block_id"], row["text"]) for row in spans] == [
        (1, "이 법에서 등록기관이란 허가받은 자를 말한다."),
        (2, "① 등록기관은 장부를 보존하여야 한다."),
    ]
    units = {row["node_id"]: row for row in collector.rows["canonical/structural_units.jsonl"]}
    spans_by_node = {row["node_id"]: row for row in spans}
    assert units[2]["parent_id"] == units[1]["id"]
    assert spans_by_node[2]["structural_unit_id"] == units[2]["id"]
    assert spans_by_node[2]["article_root_id"] == units[1]["id"]
    assert all(
        result["blocks"][row["block_id"]]["text"][row["start"]:row["end"]]
        == row["text"]
        for row in spans
    )


def test_clause_span_row_binds_unit_offsets_and_text_hash():
    text = "다만, 국가기관은 제외한다."
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    row = {
        "schema_version": "legal-graph-v1",
        "generation_id": "generation-test",
        "authority_generation": "a" * 64,
        "layer": "canonical",
        "row_type": "clause_span",
        "id": stable_id("clause_span", "test-1"),
        "structural_unit_id": stable_id("unit", "test-1"),
        "start": 0,
        "end": len(text),
        "text": text,
        "text_sha256": digest,
        "span_kind": "PROVISO",
        "selector": {
            "document_id": "doc-1",
            "node_id": 2,
            "block_id": 1,
            "start": 0,
            "end": len(text),
            "quote_sha256": digest,
            "coordinate": "제10조제1항",
        },
    }
    assert validate_row(row) is row


def test_api_exposes_lifecycle_and_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(batch_mod, "lineup", _empty_lineup)
    app = FastAPI()
    app.include_router(pipeline_router.router)
    client = TestClient(app)
    lineup = client.get("/v1/pipeline/lineup")
    assert lineup.status_code == 200
    assert [phase["id"] for phase in lineup.json()["lifecycle"]["phases"]] == [
        "input", "extract", "transform", "use", "restructure"
    ]
    response = client.post("/v1/pipeline/run", json={"stages": ["legal_graph"]})
    assert response.status_code == 409
    assert "confirm_explicit" in response.json()["detail"]
