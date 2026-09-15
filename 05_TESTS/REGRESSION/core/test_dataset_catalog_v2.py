from __future__ import annotations

import pytest

from lawrag.datasets.catalog import (
    DatasetContractError,
    DatasetRegistry,
    compose_source_set,
    package_from_mapping,
)


def _package(
    package_id: str,
    *,
    dataset_id: str,
    logical_id: str,
    digest: str,
    origin: str = "public_external",
    security: str = "public",
    representation: str = "real",
    export_allowed: bool = True,
    execution_site: str = "outside",
):
    return package_from_mapping(
        {
            "schema_version": "dataset-package-v2",
            "package_id": package_id,
            "dataset_id": dataset_id,
            "version_id": "v1",
            "variant_id": representation,
            "generation_id": f"gen-{package_id}",
            "source_origin": origin,
            "security_class": security,
            "representation": representation,
            "authority": "authoritative",
            "export_policy": {"allowed": export_allowed},
            "build": {
                "build_id": f"build-{package_id}",
                "execution_site": execution_site,
                "code_revision": "abc123",
                "compiler_profile": "semantic-v1",
                "capabilities": ["structure", "semantic"],
            },
            "artifacts": [
                {
                    "logical_id": logical_id,
                    "role": "semantic",
                    "path": f"SEMANTIC/{logical_id}.jsonl",
                    "sha256": digest,
                }
            ],
        }
    )


def _source_set(*members, policy="error", cross_dataset_relations=False):
    return {
        "schema_version": "source-set-v1",
        "source_set_id": "genos-production",
        "generation_id": "release-1",
        "conflict_policy": policy,
        "cross_dataset_relations": cross_dataset_relations,
        "members": [
            {"package_id": package_id, "priority": priority}
            for package_id, priority in members
        ],
    }


def test_external_and_genos_internal_packages_share_one_composition_contract():
    outside = _package(
        "public-law", dataset_id="public-law", logical_id="law-26", digest="a" * 64
    )
    internal = _package(
        "company-rules",
        dataset_id="company-rules",
        logical_id="policy-7",
        digest="b" * 64,
        origin="restricted_internal",
        security="restricted",
        export_allowed=False,
        execution_site="genos",
    )

    view = compose_source_set(
        _source_set(("public-law", 10), ("company-rules", 20)),
        [outside, internal],
    )

    assert len(view.packages) == 2
    assert len(view.artifacts) == 2
    assert view.export_allowed is False
    assert {row["execution_site"] for row in view.receipt()["packages"]} == {
        "outside",
        "genos",
    }
    assert len(view.source_set_sha256) == 64


def test_registry_opens_an_explicit_multi_package_source_set():
    outside = _package(
        "public-law", dataset_id="public-law", logical_id="law-26", digest="a" * 64
    )
    internal = _package(
        "company-rules",
        dataset_id="company-rules",
        logical_id="policy-7",
        digest="b" * 64,
        origin="restricted_internal",
        security="restricted",
        export_allowed=False,
        execution_site="genos",
    )
    registry = DatasetRegistry([outside, internal])

    view = registry.open(
        _source_set(("public-law", 10), ("company-rules", 20))
    )

    assert {package.package_id for package in view.packages} == {
        "public-law",
        "company-rules",
    }
    assert [row["package_id"] for row in registry.receipt()] == [
        "company-rules",
        "public-law",
    ]


def test_cross_dataset_relation_policy_is_part_of_the_source_set_identity():
    package = _package(
        "public-law", dataset_id="public-law", logical_id="law-26", digest="a" * 64
    )

    disabled = compose_source_set(
        _source_set(("public-law", 10), cross_dataset_relations=False), [package]
    )
    enabled = compose_source_set(
        _source_set(("public-law", 10), cross_dataset_relations=True), [package]
    )

    assert disabled.cross_dataset_relations is False
    assert enabled.cross_dataset_relations is True
    assert disabled.source_set_sha256 != enabled.source_set_sha256


def test_different_content_for_same_logical_artifact_fails_closed_by_default():
    first = _package("first", dataset_id="law-a", logical_id="same", digest="a" * 64)
    second = _package("second", dataset_id="law-b", logical_id="same", digest="b" * 64)

    with pytest.raises(DatasetContractError, match="conflicting logical artifact"):
        compose_source_set(_source_set(("first", 10), ("second", 20)), [first, second])


def test_explicit_priority_resolves_conflict_and_keeps_all_provenance():
    first = _package("first", dataset_id="law-a", logical_id="same", digest="a" * 64)
    second = _package("second", dataset_id="law-b", logical_id="same", digest="b" * 64)

    view = compose_source_set(
        _source_set(("first", 10), ("second", 20), policy="explicit_priority"),
        [first, second],
    )

    resolved = view.resolve("same", "semantic")
    assert len(resolved) == 1
    assert resolved[0].selected.package_id == "second"
    assert resolved[0].contributors == ("first", "second")
    assert len(view.conflicts) == 1
    assert view.conflicts[0]["selected_package_ids"] == ["second"]
    assert view.conflicts[0]["candidates"][0]["priority"] == 20


def test_real_and_mock_variants_cannot_be_activated_together():
    real = _package("real-pack", dataset_id="company", logical_id="policy", digest="a" * 64)
    mock = _package(
        "mock-pack",
        dataset_id="company",
        logical_id="policy-mock",
        digest="b" * 64,
        representation="mock",
    )

    with pytest.raises(DatasetContractError, match="real/mock variants"):
        compose_source_set(
            _source_set(("real-pack", 10), ("mock-pack", 10)), [real, mock]
        )


def test_restricted_package_cannot_claim_export_permission():
    with pytest.raises(DatasetContractError, match="restricted package"):
        _package(
            "leaky",
            dataset_id="internal",
            logical_id="secret",
            digest="a" * 64,
            security="restricted",
            export_allowed=True,
        )


def test_direct_composition_rejects_one_package_id_with_multiple_manifests():
    first = _package("same-id", dataset_id="law-a", logical_id="aa", digest="a" * 64)
    second = _package("same-id", dataset_id="law-a", logical_id="bb", digest="b" * 64)

    with pytest.raises(DatasetContractError, match="multiple manifests"):
        compose_source_set(_source_set(("same-id", 10)), [first, second])


def test_python_parser_rejects_fields_outside_the_json_contract():
    package = _package("clean", dataset_id="law-a", logical_id="aa", digest="a" * 64)
    source_set = _source_set(("clean", 10))
    source_set["silent_policy"] = "must-not-be-ignored"

    with pytest.raises(DatasetContractError, match="unknown source set fields"):
        compose_source_set(source_set, [package])
