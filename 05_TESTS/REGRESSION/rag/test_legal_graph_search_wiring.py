from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from lawrag.core.legal_graph import (
    COMPILER_CONTRACT_VERSION,
    SCHEMA_VERSION,
    canonical_json_text,
    content_sha256,
    stable_id,
)
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index
from lawrag.core.rag import legal_graph_closure, legal_graph_store
from lawrag.api import legalclosure_presenter


AUTHORITY = "a" * 64
SOURCE_HASHES = {
    "fixtures/legal-graph-search-wiring.json": content_sha256({
        "fixture": "legal-graph-search-wiring",
        "version": 1,
    }),
}
SOURCE_AGGREGATE = content_sha256(SOURCE_HASHES)
GENERATION_DIGEST = content_sha256({
    "schema_version": SCHEMA_VERSION,
    "compiler_contract": COMPILER_CONTRACT_VERSION,
    "projection_policy": "provision-card-v1.1",
    "authority_generation": AUTHORITY,
    "source_hashes": SOURCE_HASHES,
})
GENERATION = f"lgv1-{GENERATION_DIGEST[:24]}"


def _endpoint(ref_id: str, doc_id: str, node: int, label: str) -> dict:
    return {
        "kind": "STRUCTURAL_UNIT",
        "precision": "EXACT_UNIT",
        "ref_id": ref_id,
        "label": label,
        "selector": {
            "document_id": doc_id,
            "node_id": node,
            "coordinate": label,
        },
    }


def _row(row_type: str, row_id: str, layer: str, **fields) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": GENERATION,
        "authority_generation": AUTHORITY,
        "layer": layer,
        "row_type": row_type,
        "id": row_id,
        **fields,
    }


def _write_gzip_jsonl(path: Path, rows: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            for row in rows:
                handle.write((canonical_json_text(row) + "\n").encode("utf-8"))
    payload = path.read_bytes()
    return {
        "path": str(path.name),
        "logical_path": str(path.name).removesuffix(".gz"),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "rows": len(rows),
        "format": "jsonl",
        "compression": "gzip",
        "row_type": rows[0]["row_type"],
    }


def _sidecar(root: Path) -> dict[str, str]:
    generation_root = root / "generations" / GENERATION
    law_article = stable_id("unit", "law-article")
    law_item = stable_id("unit", "law-item")
    decree_article = stable_id("unit", "decree-article")
    assertion_id = stable_id("relation", "delegation")
    closure_id = stable_id("closure", "delegation")
    law_card = stable_id("card", "law")
    decree_card = stable_id("card", "decree")
    source = _endpoint(
        law_item, "law-doc", 2, "제2조제6호나목 대통령령으로 정하는 주요주주"
    )
    target = _endpoint(decree_article, "decree-doc", 10, "제4조 주요주주의 범위")
    assertion = _row(
        "relation_assertion",
        assertion_id,
        "canonical",
        predicate="LEGISLATIVE_DELEGATION",
        family="LEGISLATIVE_LINK",
        source=source,
        target=target,
        claim_status="ACCEPTED",
        evidence_ids=[],
        resolution="EXACT_SOURCE_BACKED",
        review_state="SOURCE_BACKED",
        legacy_kind="DELEGATES_TO",
    )
    closure = _row(
        "closure_projection",
        closure_id,
        "projection",
        relation_assertion_id=assertion_id,
        source_article_root_id=law_article,
        closure_mode="REQUIRED_WHEN_ACTIVATED",
        activation_policy="query_conditional_future_policy",
        runtime_wired=False,
    )

    def card(card_id: str, endpoint: dict, member_id: str, outgoing=(), incoming=()):
        return _row(
            "provision_card",
            card_id,
            "projection",
            article_root=endpoint,
            article_root_id=member_id,
            structural_unit_id=member_id,
            facets={
                "definition_observation_ids": [],
                "frame_observation_ids": [],
                "legacy_rule_assertion_ids": [],
                "relation_assertion_ids": [],
                "requirement_observation_ids": [],
                "unresolved_relation_ids": [],
            },
            relation_ports={
                "outgoing_projection_ids": list(outgoing),
                "incoming_projection_ids": list(incoming),
            },
            runtime_wired=False,
        )

    law_endpoint = _endpoint(law_article, "law-doc", 1, "제2조 정의")
    rows = {
        "canonical/relation_assertions.jsonl.gz": [assertion],
        "projections/closure_projections.jsonl.gz": [closure],
        "projections/provision_cards.jsonl.gz": [
            card(law_card, law_endpoint, law_article, outgoing=(closure_id,)),
            card(decree_card, target, decree_article, incoming=(closure_id,)),
        ],
    }
    artifacts = {}
    for relative, values in rows.items():
        metadata = _write_gzip_jsonl(generation_root / relative, values)
        metadata["path"] = relative
        metadata["logical_path"] = relative.removesuffix(".gz")
        artifacts[relative] = metadata
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compiler_contract": COMPILER_CONTRACT_VERSION,
        "generation_id": GENERATION,
        "authority_generation": AUTHORITY,
        "authority_as_of": "20260828",
        "source_hashes": SOURCE_HASHES,
        "source_aggregate_sha256": SOURCE_AGGREGATE,
        "projection_policy": "provision-card-v1.1",
        "runtime_wired": False,
        "artifacts": artifacts,
    }
    manifest["content_sha256"] = content_sha256(manifest)
    content = manifest["content_sha256"]
    (generation_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    validation = generation_root / "validation"
    validation.mkdir()
    (validation / "summary.json").write_text(json.dumps({
        "schema_version": "legal-graph-validation-v1",
        "generation_id": GENERATION,
        "ok": True,
        "error_count": 0,
    }), encoding="utf-8")
    pointer = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": GENERATION,
        "authority_generation": AUTHORITY,
        "content_sha256": content,
        "projection_policy": "provision-card-v1.1",
        "runtime_wired": False,
        "manifest": f"generations/{GENERATION}/manifest.json",
    }
    (root / "CURRENT.json").write_text(
        json.dumps(pointer, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return {
        "law_article": law_article,
        "law_item": law_item,
        "decree_article": decree_article,
        "assertion": assertion_id,
        "closure": closure_id,
    }


def _index(*, authority: str = AUTHORITY) -> Index:
    law = ("law-doc", {"name": "지배구조법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1, "surface": "제2조",
             "title": "정의", "page": 1, "span": [0, 2]},
            {"id": 2, "parent": 1, "level": 2, "surface": "나.",
             "title": "", "page": 1, "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "page": 1, "text": "제2조(정의)", "kind": "text"},
            {"idx": 1, "page": 1,
             "text": "나. 중요한 경영사항에 사실상의 영향력을 행사하는 주주로서 "
                     "대통령령으로 정하는 주요주주", "kind": "text"},
        ],
    })
    decree = ("decree-doc", {"name": "지배구조법 시행령", "kind": "law"}, {
        "nodes": [
            {"id": 10, "parent": None, "level": 1, "surface": "제4조",
             "title": "주요주주의 범위", "page": 1, "span": [0, 1]},
        ],
        "blocks": [
            {"idx": 0, "page": 1,
             "text": "제4조(주요주주의 범위) 법 제2조제6호나목에서 대통령령으로 "
                     "정하는 자란 이사 과반수를 선임한 주주 등을 말한다.",
             "kind": "text"},
        ],
    })
    return Index.from_docs(
        [law, decree],
        canonical_doc_ids={"law-doc", "decree-doc"},
        authority_generation=authority,
        authority_as_of="20260828",
    )


def _floor(idx: Index) -> list[Section]:
    view = idx.docs["law-doc"]
    return [Section(
        n=1,
        doc_id="law-doc",
        doc=view.name,
        node=1,
        path=view.path(1),
        page=1,
        kind="법률좌표폐쇄",
        matched="baseline",
        text=view.section_text(view.by_id[1]),
    )]


def test_verified_loader_pins_generation_and_reuses_cache(tmp_path) -> None:
    ids = _sidecar(tmp_path)
    idx = _index()
    legal_graph_store.reset_cache()
    first = legal_graph_store.current_for(idx, root=tmp_path)
    second = legal_graph_store.current_for(idx, root=tmp_path)

    assert first.status == "loaded" and first.snapshot is not None
    assert second.status == "cache_hit" and second.snapshot is first.snapshot
    edges = first.snapshot.incident(("law-doc", 1))
    assert [edge.projection_id for edge in edges] == [ids["closure"]]
    assert first.snapshot.runtime_wired_in_artifact is False


def test_loader_rejects_authority_or_hash_and_publishes_no_partial_snapshot(
    tmp_path,
) -> None:
    _sidecar(tmp_path)
    legal_graph_store.reset_cache()
    stale = legal_graph_store.current_for(_index(authority="c" * 64), root=tmp_path)
    assert stale.status == "stale" and stale.snapshot is None

    artifact = (
        tmp_path / "generations" / GENERATION
        / "projections" / "closure_projections.jsonl.gz"
    )
    artifact.write_bytes(artifact.read_bytes() + b"corrupt")
    legal_graph_store.reset_cache()
    invalid = legal_graph_store.current_for(_index(), root=tmp_path)
    assert invalid.status == "invalid" and invalid.snapshot is None
    assert "byte count mismatch" in invalid.reasons[0]


def test_classification_question_activates_exact_lower_unit_delegation(tmp_path) -> None:
    _sidecar(tmp_path)
    idx = _index()
    legal_graph_store.reset_cache()
    snapshot = legal_graph_store.current_for(idx, root=tmp_path).snapshot
    assert snapshot is not None

    additions, meta = legal_graph_closure.plan_coordinates(
        idx,
        "투자계약상 동의권을 가진 투자자가 주요주주에 해당하는지",
        [("law-doc", 1)],
        snapshot=snapshot,
    )
    assert [row["coordinate"] for row in additions] == [("decree-doc", 10)]
    assert meta["active_family_ids"] == ["CLASSIFICATION"]
    assert meta["reason_counts"]["activated"] == 1
    assert meta["policy"]["baseline_is_immutable_floor"] is True


def test_bare_delegation_does_not_conflate_legislative_delegation(tmp_path) -> None:
    _sidecar(tmp_path)
    idx = _index()
    legal_graph_store.reset_cache()
    snapshot = legal_graph_store.current_for(idx, root=tmp_path).snapshot
    additions, meta = legal_graph_closure.plan_coordinates(
        idx, "위임 범위는 무엇인가", [("law-doc", 1)], snapshot=snapshot
    )
    assert additions == []
    assert "DELEGATION" in meta["active_family_ids"]
    assert meta["reason_counts"]["rejected_legislative_ambiguity"] == 1


def test_section_extension_is_add_only_bounded_and_carries_edge_trace(tmp_path) -> None:
    _sidecar(tmp_path)
    idx = _index()
    floor = _floor(idx)
    legal_graph_store.reset_cache()
    out, meta = legal_graph_closure.extend_sections(
        idx,
        "투자자가 주요주주에 해당하는지",
        floor,
        root=tmp_path,
        cap=20,
    )
    assert [(row.doc_id, row.node) for row in out] == [
        ("law-doc", 1), ("decree-doc", 10),
    ]
    assert out[0] is floor[0]
    assert out[1].is_companion and out[1].kind.startswith("참조")
    assert out[1].edges[0]["relation"] == "LEGISLATIVE_DELEGATION"
    assert meta["added_count"] == 1 and meta["after_count"] == 2

    capped, capped_meta = legal_graph_closure.extend_sections(
        idx,
        "투자자가 주요주주에 해당하는지",
        floor,
        root=tmp_path,
        cap=1,
    )
    assert capped == floor
    assert capped_meta["status"] == "no_residual_slots"


def test_missing_sidecar_fails_open_to_identical_floor(tmp_path) -> None:
    idx = _index()
    floor = _floor(idx)
    legal_graph_store.reset_cache()
    out, meta = legal_graph_closure.extend_sections(
        idx, "주요주주에 해당하는지", floor, root=tmp_path
    )
    assert out == floor
    assert meta["status"] == "fallback"
    assert meta["fallback"] == "baseline_preserved"
    assert meta["load"]["status"] == "missing"


def test_presenter_exposes_graph_generation_and_ladder_stage() -> None:
    public = legalclosure_presenter.public_meta({
        "primary": {}, "assertion": {}, "keyword": {},
        "legal_graph": {
            "enabled": True,
            "status": "expanded",
            "generation_id": GENERATION,
            "added_count": 1,
        },
    })
    assert public["legal_graph"]["generation_id"] == GENERATION
    ladder = legalclosure_presenter.ladder(public, 2)
    graph = next(row for row in ladder if row["stage"] == "Legal Graph 조건부 폐쇄")
    assert graph["count"] == 1 and "expanded" in graph["note"]
