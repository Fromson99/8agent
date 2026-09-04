from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from lawrag.core.legal_graph.ids import canonical_json_text, stable_id
from lawrag.core.legal_graph.validation import validate_generation


SCHEMA = "legal-graph-v1"
AUTHORITY = "a" * 64
GENERATION = "generation-test-001"


def _sid(prefix: str, name: str) -> str:
    return stable_id(prefix, name)


def _selector(node: int, *, span: bool = False, quote: str = "위임된 기준") -> dict:
    result = {"document_id": "doc-1", "node_id": node, "coordinate": "제1조제1항"}
    if span:
        result.update({
            "block_id": 0,
            "start": 0,
            "end": len(quote),
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        })
    return result


def _endpoint(ref_id: str, node: int, *, span: bool = False) -> dict:
    return {
        "kind": "STRUCTURAL_UNIT",
        "precision": "EXACT_SPAN" if span else "EXACT_UNIT",
        "ref_id": ref_id,
        "selector": _selector(node, span=span),
    }


def _envelope(row_type: str, row_id: str, **fields) -> dict:
    layer = (
        "canonical" if row_type in {"structural_unit", "evidence", "relation_assertion"}
        else "observation" if row_type in {"relation_observation", "unresolved_relation"}
        else "projection"
    )
    return {
        "schema_version": SCHEMA,
        "generation_id": GENERATION,
        "authority_generation": AUTHORITY,
        "layer": layer,
        "row_type": row_type,
        "id": row_id,
        **fields,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(canonical_json_text(row) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def _write_generation(root: Path) -> dict[str, str]:
    article_id = _sid("unit", "article")
    paragraph_id = _sid("unit", "paragraph")
    evidence_id = _sid("evidence", "delegation")
    observation_id = _sid("observation", "delegation")
    assertion_id = _sid("relation", "delegation")
    card_id = _sid("card", "article")
    closure_id = _sid("closure", "delegation")
    compatibility_id = _sid("compat", "derived")
    oracle_id = _sid("compat", "oracle")

    article = _envelope(
        "structural_unit",
        article_id,
        document_id="doc-1",
        node_id=1,
        unit_kind="article",
        article_root_id=article_id,
        selector={"document_id": "doc-1", "node_id": 1, "coordinate": "제1조"},
        current=True,
    )
    paragraph = _envelope(
        "structural_unit",
        paragraph_id,
        document_id="doc-1",
        node_id=2,
        unit_kind="항",
        parent_id=article_id,
        article_root_id=article_id,
        selector=_selector(2),
        current=True,
    )
    evidence = _envelope(
        "evidence",
        evidence_id,
        kind="SOURCE_TEXT",
        source=_endpoint(paragraph_id, 2, span=True),
        quote_text="위임된 기준",
        method="synthetic-test",
    )
    relation = _envelope(
        "relation_assertion",
        assertion_id,
        predicate="LEGISLATIVE_DELEGATION",
        family="LEGISLATIVE_LINK",
        source=_endpoint(paragraph_id, 2),
        target=_endpoint(article_id, 1),
        claim_status="ACCEPTED",
        evidence_ids=[evidence_id],
        source_observation_ids=[observation_id],
        resolution="RESOLVED",
        review_state="DETERMINISTIC",
    )
    relation_input = _envelope(
        "relation_observation",
        observation_id,
        source=_endpoint(paragraph_id, 2),
        target=_endpoint(article_id, 1),
        claim_status="CANDIDATE",
        source_kind="delegation",
        source_row_key="delegation:1",
        terminal_disposition="MAPPED",
        assertion_ids=[assertion_id],
    )
    card = _envelope(
        "provision_card",
        card_id,
        article_root=_endpoint(article_id, 1),
        article_root_id=article_id,
        structural_unit_id=article_id,
        facets={
            "definition_observation_ids": [],
            "frame_observation_ids": [],
            "requirement_observation_ids": [],
            "legacy_rule_assertion_ids": [],
            "relation_assertion_ids": [assertion_id],
            "unresolved_relation_ids": [],
        },
        relation_ports={
            "outgoing_projection_ids": [closure_id],
            "incoming_projection_ids": [closure_id],
        },
        coverage={
            "definitions": 0,
            "frames": 0,
            "requirements": 0,
            "legacy_rule_assertions": 0,
            "accepted_relations": 1,
            "unresolved_relations": 0,
            "outgoing_relations": 1,
            "incoming_relations": 1,
            "frame_status": "NOT_EXTRACTED",
            "semantic_status": "ENRICHED",
        },
    )
    closure = _envelope(
        "closure_projection",
        closure_id,
        relation_assertion_id=assertion_id,
        source_article_root_id=article_id,
        closure_mode="REQUIRED_WHEN_ACTIVATED",
        runtime_wired=False,
    )
    legacy_key = {"doc_id": "doc-1", "node": 1, "kind": "DELEGATES_TO"}
    provenance = {"source_kind": "delegation", "source_row_key": "delegation:1"}
    compatibility = _envelope(
        "compatibility",
        compatibility_id,
        compatibility_kind="legacy_section_relation",
        legacy_key=legacy_key,
        mandatory=True,
        provenance=provenance,
        assertion_ids=[assertion_id],
    )
    oracle = _envelope(
        "compatibility",
        oracle_id,
        compatibility_kind="legacy_section_relation_oracle",
        legacy_key=legacy_key,
        mandatory=True,
        provenance=provenance,
        assertion_ids=[assertion_id],
    )
    artifacts: dict[str, list[dict] | dict] = {
        "canonical/structural_units.jsonl": [article, paragraph],
        "canonical/evidence.jsonl": [evidence],
        "canonical/relation_assertions.jsonl": [relation],
        "observations/relation_inputs.jsonl": [relation_input],
        "observations/unresolved_relations.jsonl": [],
        "projections/provision_cards.jsonl": [card],
        "projections/relation_compatibility.jsonl": [compatibility],
        "projections/legacy_section_relations.jsonl": [oracle],
        "projections/closure_projections.jsonl": [closure],
        "source_accounting.json": {
            "schema_version": SCHEMA,
            "generation_id": GENERATION,
            "sources": {
                "delegation": {
                    "input_rows": 1,
                    "terminal_counts": {
                        "mapped": 1, "support_only": 0, "unresolved": 0,
                        "suppressed": 0, "out_of_contract": 0, "parse_error": 0,
                    },
                    "terminal_ids": {
                        "mapped": [observation_id], "support_only": [], "unresolved": [],
                        "suppressed": [], "out_of_contract": [], "parse_error": [],
                    },
                }
            },
            "totals": {
                "input_rows": 1,
                "terminal_counts": {
                    "mapped": 1, "support_only": 0, "unresolved": 0,
                    "suppressed": 0, "out_of_contract": 0, "parse_error": 0,
                },
            },
        },
    }
    metadata = {}
    for relative, value in artifacts.items():
        path = root / relative
        if relative.endswith(".jsonl"):
            assert isinstance(value, list)
            _write_jsonl(path, value)
            rows = len(value)
            artifact_format = "jsonl"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canonical_json_text(value) + "\n", encoding="utf-8")
            rows = 1
            artifact_format = "json"
        payload = path.read_bytes()
        metadata[relative] = {
            "format": artifact_format,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "rows": rows,
        }
    manifest = {
        "schema_version": SCHEMA,
        "compiler_contract": "legal-graph-compiler-v1",
        "generation_id": GENERATION,
        "authority_generation": AUTHORITY,
        "authority_as_of": "20260827",
        "runtime_wired": False,
        "artifacts": metadata,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "article": article_id,
        "paragraph": paragraph_id,
        "assertion": assertion_id,
        "observation": observation_id,
    }


def _refresh_manifest_artifact(root: Path, relative: str) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (root / relative).read_bytes()
    manifest["artifacts"][relative]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["artifacts"][relative]["bytes"] = len(payload)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_structure_source(root: Path, text: str = "위임된 기준") -> Path:
    store = root / "source-structure"
    document = store / "doc-1"
    document.mkdir(parents=True)
    (document / "result.json").write_text(
        json.dumps({"blocks": [{"idx": 0, "text": text}]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return store


def test_stable_ids_lower_endpoint_and_card_validate(tmp_path: Path):
    ids = _write_generation(tmp_path)
    source_store = _write_structure_source(tmp_path)
    assert stable_id("unit", {"b": 2, "a": 1}) == stable_id("unit", {"a": 1, "b": 2})

    report = validate_generation(tmp_path, structure_store=source_store)

    assert report.ok, report.to_dict()
    assert report.generation_id == GENERATION
    assert report.checked_artifacts == 10
    assert report.checked_rows == 10
    relation = json.loads((tmp_path / "canonical/relation_assertions.jsonl").read_text(encoding="utf-8"))
    assert relation["source"]["ref_id"] == ids["paragraph"]
    assert relation["source"]["selector"]["node_id"] == 2


def test_exact_span_is_rechecked_against_structure_source(tmp_path: Path):
    _write_generation(tmp_path)
    source_store = _write_structure_source(tmp_path, "변조된 원문")

    report = validate_generation(tmp_path, structure_store=source_store)

    assert not report.ok
    assert any(issue.code == "source_span.quote_hash" for issue in report.errors)


def test_artifact_hash_and_bytes_failure_is_detected(tmp_path: Path):
    _write_generation(tmp_path)
    path = tmp_path / "canonical/structural_units.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = validate_generation(tmp_path)

    assert not report.ok
    codes = {issue.code for issue in report.errors}
    assert {"artifact.hash_mismatch", "artifact.bytes_mismatch"} <= codes


def test_dangling_endpoint_and_quote_hash_are_detected(tmp_path: Path):
    _write_generation(tmp_path)
    relation_path = tmp_path / "canonical/relation_assertions.jsonl"
    relation = json.loads(relation_path.read_text(encoding="utf-8"))
    relation["target"]["ref_id"] = _sid("unit", "missing")
    _write_jsonl(relation_path, [relation])
    _refresh_manifest_artifact(tmp_path, "canonical/relation_assertions.jsonl")
    evidence_path = tmp_path / "canonical/evidence.jsonl"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["quote_text"] = "변조된 인용"
    _write_jsonl(evidence_path, [evidence])
    _refresh_manifest_artifact(tmp_path, "canonical/evidence.jsonl")

    report = validate_generation(tmp_path)

    codes = {issue.code for issue in report.errors}
    assert "endpoint.dangling" in codes
    assert "row.schema" in codes


def test_terminal_accounting_has_no_silent_drop(tmp_path: Path):
    _write_generation(tmp_path)
    accounting_path = tmp_path / "source_accounting.json"
    accounting = json.loads(accounting_path.read_text(encoding="utf-8"))
    accounting["sources"]["delegation"]["terminal_ids"]["mapped"] = []
    accounting_path.write_text(canonical_json_text(accounting) + "\n", encoding="utf-8")
    _refresh_manifest_artifact(tmp_path, "source_accounting.json")

    first = validate_generation(tmp_path)
    second = validate_generation(tmp_path)

    assert not first.ok
    assert any(issue.code == "accounting.terminal_ids" for issue in first.errors)
    assert first.to_dict() == second.to_dict()


def test_compatibility_fold_must_match_oracle(tmp_path: Path):
    _write_generation(tmp_path)
    path = tmp_path / "projections/relation_compatibility.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["provenance"] = {"source_kind": "changed"}
    _write_jsonl(path, [row])
    _refresh_manifest_artifact(tmp_path, "projections/relation_compatibility.jsonl")

    report = validate_generation(tmp_path)

    assert not report.ok
    assert any(issue.code == "compatibility.fold_value_mismatch" for issue in report.errors)


def test_card_ports_facets_and_coverage_are_recomputed(tmp_path: Path):
    _write_generation(tmp_path)
    path = tmp_path / "projections/provision_cards.jsonl"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["relation_ports"]["incoming_projection_ids"] = []
    card["facets"]["frame_observation_ids"] = [_sid("observation", "missing-frame")]
    card["coverage"]["accepted_relations"] = 0
    _write_jsonl(path, [card])
    _refresh_manifest_artifact(tmp_path, "projections/provision_cards.jsonl")

    report = validate_generation(tmp_path)

    codes = {issue.code for issue in report.errors}
    assert {"card.fold_mismatch", "card.facet_dangling", "card.coverage_mismatch"} <= codes


def test_validate_cli_returns_nonzero_for_invalid_generation(tmp_path: Path):
    _write_generation(tmp_path)
    path = tmp_path / "canonical/structural_units.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_legal_graph_v1.py"),
            "validate",
            "--generation",
            str(tmp_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["ok"] is False
