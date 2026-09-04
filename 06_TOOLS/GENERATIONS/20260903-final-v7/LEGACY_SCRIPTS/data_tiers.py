#!/usr/bin/env python3
"""Inventory production law-XML lineage and evaluation/mock data separately."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VECTOR_MARKERS = ("embedding", "vectors", ".npz", "qdrant")


def _record(path: Path, *, role: str, provenance: str) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "role": role,
        "provenance": provenance,
    }


def _files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
    elif path.is_dir():
        yield from (item for item in sorted(path.rglob("*")) if item.is_file())


def _summarize(rows: list[dict]) -> dict:
    paths = sorted({row["path"] for row in rows})
    by_path = {row["path"]: row for row in rows}
    return {
        "file_count": len(paths),
        "bytes": sum(int(by_path[path]["bytes"]) for path in paths),
        "files": [by_path[path] for path in paths],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_inventory() -> dict:
    law_manifest_path = DATA / "corpus" / "law" / "manifest.json"
    raw_rows: list[dict] = [_record(
        law_manifest_path, role="source_manifest", provenance="law.go.kr"
    )]
    current_body_doc_ids: set[str] = set()
    historical_body_doc_ids: set[str] = set()
    for base, historical in (
        (DATA / "corpus" / "law", False),
        (DATA / "corpus" / "law_history", True),
    ):
        for path in sorted(base.rglob("*.xml")) if base.is_dir() else ():
            relation = "relations" in path.relative_to(base).parts
            if relation:
                raw_rows.append(_record(
                    path, role="law_relation_xml", provenance="law.go.kr"
                ))
                continue
            digest = _sha256(path)
            row = _record(
                path,
                role="historical_law_xml_body" if historical else "law_xml_body",
                provenance="law.go.kr",
            )
            row["sha256"] = digest
            row["doc_id"] = digest[:16]
            raw_rows.append(row)
            if historical:
                historical_body_doc_ids.add(row["doc_id"])
            else:
                current_body_doc_ids.add(row["doc_id"])

    structure_rows: list[dict] = []
    structure_doc_ids: set[str] = set()
    for directory in sorted((DATA / "structure").glob("*")):
        meta_path = directory / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        if meta.get("source_kind") != "lawxml":
            continue
        doc_id = str(meta.get("doc_id") or directory.name)
        structure_doc_ids.add(doc_id)
        for name in ("meta.json", "result.json", "source.xml"):
            path = directory / name
            if path.is_file():
                row = _record(path, role="lawxml_structure", provenance=doc_id)
                row["doc_id"] = doc_id
                structure_rows.append(row)

    connected_rows: list[dict] = []
    for relative, role in (
        ("data/delegation.json", "legal_relation_edges"),
        ("data/law_index.json", "law_document_index"),
        ("data/aliases.json", "law_aliases"),
    ):
        path = ROOT / relative
        if path.is_file():
            connected_rows.append(_record(
                path, role=role, provenance="lawxml-derived"
            ))
    for base_name, role in (("frames", "law_frame"), ("taxonomy", "law_taxonomy")):
        base = DATA / base_name
        for path in _files(base):
            if any(doc_id in path.name for doc_id in structure_doc_ids):
                connected_rows.append(_record(
                    path, role=role, provenance=path.stem.split(".")[0]
                ))

    evaluation_rows: list[dict] = []
    for relative, role in (
        ("data/bench", "benchmark_dataset"),
        ("data/review", "golden_or_review_dataset"),
        ("tests/fixtures", "test_fixture"),
        ("tests/agent6/fixtures", "agent6_test_fixture"),
        ("docs/examples", "example_or_synthetic_document"),
    ):
        for path in _files(ROOT / relative):
            evaluation_rows.append(_record(path, role=role, provenance="evaluation"))

    excluded_vectors = []
    for relative in ("data/embeddings", "data/lexicon"):
        for path in _files(ROOT / relative):
            lowered = path.as_posix().lower()
            if relative.endswith("embeddings") or any(
                marker in lowered for marker in VECTOR_MARKERS
            ):
                excluded_vectors.append(_record(
                    path, role="vector_or_model_specific_index", provenance="regenerable"
                ))

    mixed_rows = []
    for relative, role in (
        ("data/domain_graph", "mixed_domain_graph"),
        ("data/legal_graph", "mixed_legal_graph_generation"),
        ("data/glossary.json", "mixed_curated_glossary"),
        ("data/wiki", "authoritative_interpretation_and_curated_wiki"),
        ("data/rules", "human_curated_runtime_rules"),
        ("data/corpus/expc", "external_authoritative_interpretation"),
        ("data/corpus/fsc", "external_authoritative_fsc"),
        ("data/corpus/prec", "external_authoritative_precedent"),
        ("data/corpus/kofia", "external_self_regulation"),
        ("data/corpus/krx", "external_exchange_rules"),
        ("data/corpus/internal", "internal_authoritative_rules"),
    ):
        for path in _files(ROOT / relative):
            mixed_rows.append(_record(path, role=role, provenance="not-mock-not-pure-lawxml"))

    grouped_rows = (
        raw_rows + structure_rows + connected_rows + evaluation_rows
        + excluded_vectors + mixed_rows
    )
    assigned_paths = {row["path"] for row in grouped_rows}
    remaining_rows = []
    for path in _files(DATA):
        relative = path.relative_to(ROOT).as_posix()
        if relative in assigned_paths:
            continue
        remaining_rows.append(_record(
            path,
            role="operational_generated_or_unresolved",
            provenance="requires-path-specific-retention-policy",
        ))

    all_data_paths = {
        path.relative_to(ROOT).as_posix() for path in _files(DATA)
    }
    classified_paths = assigned_paths | {row["path"] for row in remaining_rows}
    classified_data_paths = classified_paths & all_data_paths
    path_counts = Counter(row["path"] for row in grouped_rows + remaining_rows)
    duplicates = sorted(path for path, count in path_counts.items() if count > 1)

    inventory = {
        "schema_version": "data-tier-inventory-v1",
        "source_manifest": "data/corpus/law/manifest.json",
        "source_manifest_sha256": hashlib.sha256(
            law_manifest_path.read_bytes()).hexdigest(),
        "classification": {
            "production_lawxml_raw": _summarize(raw_rows),
            "production_lawxml_structure": _summarize(structure_rows),
            "production_connected_non_vector": _summarize(connected_rows),
            "evaluation_mock_or_fixture": _summarize(evaluation_rows),
            "excluded_vectors": _summarize(excluded_vectors),
            "separate_authoritative_or_mixed": _summarize(mixed_rows),
            "separate_operational_generated_or_unresolved": _summarize(
                remaining_rows
            ),
        },
        "coverage": {
            "data_files_total": len(all_data_paths),
            "data_files_classified": len(classified_data_paths),
            "unclassified_data_files": sorted(
                all_data_paths - classified_data_paths
            ),
            "multiply_classified_data_files": duplicates,
            "current_law_xml_body_doc_ids": len(current_body_doc_ids),
            "historical_law_xml_body_doc_ids": len(historical_body_doc_ids),
            "lawxml_structure_doc_ids": len(structure_doc_ids),
            "current_body_without_structure": sorted(
                current_body_doc_ids - structure_doc_ids
            ),
            "historical_body_without_structure": sorted(
                historical_body_doc_ids - structure_doc_ids
            ),
            "structure_without_current_or_historical_body": sorted(
                structure_doc_ids - current_body_doc_ids - historical_body_doc_ids
            ),
        },
        "two_bucket_complete": False,
        "two_bucket_gap": (
            "wiki, 해석례·판례, 거래소·협회 규정, 내규, 사람 승인 rules 및 혼합 graph는 "
            "법 XML 파생도 실험용 mock도 아니므로 별도 authoritative/curated tier가 필요하다."
        ),
    }
    return inventory


def validate(inventory: dict) -> list[str]:
    errors = []
    production = []
    for key in (
        "production_lawxml_raw", "production_lawxml_structure",
        "production_connected_non_vector",
    ):
        production.extend(inventory["classification"][key]["files"])
    for row in production:
        lowered = row["path"].lower()
        if any(marker in lowered for marker in VECTOR_MARKERS):
            errors.append(f"vector leaked into production non-vector tier: {row['path']}")
    if inventory["coverage"]["current_body_without_structure"]:
        errors.append("law XML bodies without structure: " + ", ".join(
            inventory["coverage"]["current_body_without_structure"]))
    if inventory["coverage"]["unclassified_data_files"]:
        errors.append("unclassified data files remain")
    if inventory["coverage"]["multiply_classified_data_files"]:
        errors.append("data files appear in multiple tiers")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    inventory = build_inventory()
    text = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, "utf-8")
    else:
        print(text, end="")
    errors = validate(inventory)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
