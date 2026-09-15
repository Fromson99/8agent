from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from lawrag.ontology import definition_projection as candidate

REPO = Path(__file__).resolve().parents[3]


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def graph_fixture(
    tmp_path: Path,
    *,
    collision: bool = False,
    shadow: bool = False,
) -> tuple[Path, str]:
    root = tmp_path / "graph"
    generation_id = "lgv1-test-generation"
    generation = root / "generations" / generation_id
    authority = "authority:test-generation"
    source = {
        "kind": "STRUCTURAL_UNIT",
        "ref_id": "unit:test-article",
        "label": "제1조 정의",
        "precision": "EXACT_UNIT",
        "selector": {"document_id": "doc-test", "node_id": 1, "coordinate": "body:제1조"},
    }
    term = {
        "id": "term_sense:test-security",
        "term": "적격증권",
        "aliases": ["적격 대상 증권"],
        "claim_status": "ACCEPTED",
        "entity_id": "entity:test-security",
        "evidence_ids": ["evidence:test-definition"],
        "scope": source,
    }
    rule = {
        "id": "rule:test-definition",
        "semantic_type": "DEFINITION_SENSE",
        "claim_status": "ACCEPTED",
        "entity_id": "entity:test-security",
        "evidence_ids": ["evidence:test-definition"],
        "source": source,
    }
    evidence = {
        "id": "evidence:test-definition",
        "quote_text": "적격 대상 증권(이하 적격증권이라 한다)",
        "source": {**source, "selector": {**source["selector"], "start": 0, "end": 24}},
    }
    span = {
        "id": "clause_span:test-definition",
        "document_id": "doc-test",
        "node_id": 1,
        "text": evidence["quote_text"],
    }
    instrument = {"id": "instrument:test-v1", "document_id": "doc-test"}
    semantic_card = {
        "id": "semantic_card:test-definition",
        "entity_id": "entity:test-security",
        "source": source,
    }
    bundle = {
        "id": "rule_bundle:test-definition",
        "member_ids": [term["id"], rule["id"]],
    }
    terms = [term]
    rules = [rule]
    evidences = [evidence]
    semantic_cards = [semantic_card]
    bundles = [bundle]
    if collision:
        second_term = {
            **term,
            "id": "term_sense:test-collision",
            "aliases": [],
            "entity_id": "entity:test-collision",
            "evidence_ids": ["evidence:test-collision"],
        }
        second_rule = {
            **rule,
            "id": "rule:test-collision",
            "entity_id": "entity:test-collision",
            "evidence_ids": ["evidence:test-collision"],
        }
        second_evidence = {
            **evidence,
            "id": "evidence:test-collision",
            "quote_text": "다른 법적 의미의 적격증권",
        }
        second_card = {
            **semantic_card,
            "id": "semantic_card:test-collision",
            "entity_id": "entity:test-collision",
        }
        second_bundle = {
            "id": "rule_bundle:test-collision",
            "member_ids": [second_term["id"], second_rule["id"]],
        }
        terms.append(second_term)
        rules.append(second_rule)
        evidences.append(second_evidence)
        semantic_cards.append(second_card)
        bundles.append(second_bundle)
    if shadow:
        shadow_term = {
            **term,
            "id": "term_sense:test-short-shadow",
            "term": "증권",
            "aliases": [],
            "entity_id": "entity:test-short-shadow",
            "evidence_ids": ["evidence:test-short-shadow"],
        }
        shadow_rule = {
            **rule,
            "id": "rule:test-short-shadow",
            "entity_id": "entity:test-short-shadow",
            "evidence_ids": ["evidence:test-short-shadow"],
        }
        shadow_evidence = {
            **evidence,
            "id": "evidence:test-short-shadow",
            "quote_text": "증권이란 법적 개념을 말한다",
        }
        shadow_card = {
            **semantic_card,
            "id": "semantic_card:test-short-shadow",
            "entity_id": "entity:test-short-shadow",
        }
        shadow_bundle = {
            "id": "rule_bundle:test-short-shadow",
            "member_ids": [shadow_term["id"], shadow_rule["id"]],
        }
        terms.append(shadow_term)
        rules.append(shadow_rule)
        evidences.append(shadow_evidence)
        semantic_cards.append(shadow_card)
        bundles.append(shadow_bundle)
    row_sets = {
        "canonical/term_senses.jsonl": terms,
        "canonical/rule_assertions.jsonl": rules,
        "canonical/relation_assertions.jsonl": [],
        "canonical/evidence.jsonl": evidences,
        "canonical/clause_spans.jsonl": [span],
        "canonical/instruments.jsonl": [instrument],
        "projections/semantic_cards.jsonl": semantic_cards,
        "projections/rule_bundle_projections.jsonl": bundles,
    }
    artifacts = {}
    for logical, rows in row_sets.items():
        stored = logical + ".gz"
        path = generation / stored
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        artifacts[stored] = {
            "path": stored,
            "logical_path": logical,
            "compression": "gzip",
            "rows": len(rows),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = {
        "generation_id": generation_id,
        "authority_generation": authority,
        "authority_as_of": "20260904",
        "source_aggregate_sha256": "a" * 64,
        "artifacts": artifacts,
    }
    manifest["content_sha256"] = canonical_sha(manifest)
    write_json(generation / "manifest.json", manifest)
    write_json(generation / "validation/summary.json", {"ok": True, "generation_id": generation_id})
    write_json(root / "CURRENT.json", {
        "generation_id": generation_id,
        "manifest": f"generations/{generation_id}/manifest.json",
        "content_sha256": manifest["content_sha256"],
    })
    return root, generation_id


def schema_path() -> Path:
    return REPO / "00_SYSTEM/SCHEMAS/definition-projection-v1.schema.json"


def test_compile_verify_and_reuse(tmp_path: Path) -> None:
    graph, graph_generation = graph_fixture(tmp_path)
    output = tmp_path / "definitions"
    first = candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    second = candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    assert first["total"] == first["ready"] == 1
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["generation_id"] == first["generation_id"]
    assert candidate.DefinitionProjectionStore(output).verify(
        expected_graph_generation=graph_generation
    )["invalid"] == 0


def test_lookup_match_and_fail_closed_boundaries(tmp_path: Path) -> None:
    graph, graph_generation = graph_fixture(tmp_path)
    output = tmp_path / "definitions"
    candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    store = candidate.DefinitionProjectionStore(output)
    found = store.lookup("적격증권이 무엇인가?")
    projection_id = found["candidates"][0]["projection_id"]
    assert store.evaluate(
        projection_id, {"candidate-term": "적격 대상 증권"}, graph_generation=graph_generation
    )["outcome"] == "MATCH"
    assert store.evaluate(projection_id, {}, graph_generation=graph_generation) == {
        "outcome": "UNKNOWN", "reason": "MISSING_FACT", "fallback": "TRAVERSE_CANONICAL"
    }
    assert store.evaluate(
        projection_id, {"candidate-term": "적격증권"}, graph_generation="stale"
    ) == {"outcome": "UNKNOWN", "reason": "STALE_GENERATION", "fallback": "TRAVERSE_CANONICAL"}
    assert store.evaluate(
        projection_id, {"candidate-term": "의미상 비슷한 증권"}, graph_generation=graph_generation
    )["outcome"] == "UNKNOWN"


def test_tampered_artifact_is_rejected(tmp_path: Path) -> None:
    graph, _ = graph_fixture(tmp_path)
    output = tmp_path / "definitions"
    result = candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    records = output / "generations" / result["generation_id"] / "records.jsonl"
    records.write_text(records.read_text() + "\n")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        candidate.DefinitionProjectionStore(output).verify()


def test_ambiguous_surface_is_withheld_and_audited(tmp_path: Path) -> None:
    graph, graph_generation = graph_fixture(tmp_path, collision=True)
    output = tmp_path / "definitions"
    result = candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    verified = candidate.DefinitionProjectionStore(output).verify(
        expected_graph_generation=graph_generation
    )
    assert result["ready"] == verified["ready"] == 1
    assert verified["ambiguous_surfaces_withheld"] == 1
    assert verified["excluded_terms_withheld"] == 1
    assert candidate.DefinitionProjectionStore(output).lookup("적격증권이란?")["candidates"] == []
    assert len(candidate.DefinitionProjectionStore(output).lookup("적격 대상 증권이란?")["candidates"]) == 1


def test_longer_ambiguous_surface_blocks_shorter_ready_shadow(tmp_path: Path) -> None:
    graph, graph_generation = graph_fixture(tmp_path, collision=True, shadow=True)
    output = tmp_path / "definitions"
    result = candidate.compile_definition_projections(
        graph_root=graph, output_root=output, schema_path=schema_path()
    )
    store = candidate.DefinitionProjectionStore(output)
    verified = store.verify(expected_graph_generation=graph_generation)
    assert result["ready"] == verified["ready"] == 2
    guarded = store.lookup("적격증권이란?")
    assert guarded["candidates"] == []
    assert guarded["reason"] == "AMBIGUOUS_SURFACE"
    assert guarded["ambiguous_surfaces"] == ["적격증권"]
    unique = store.lookup("적격 대상 증권이란?")
    assert unique["candidates"][0]["matched_surface"] == "적격대상증권"
