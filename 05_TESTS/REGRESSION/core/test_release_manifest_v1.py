from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from lawrag.datasets.catalog import compose_source_set, package_from_mapping
from lawrag.platform.release import (
    ReleaseContractError,
    activation_plan_from_mapping,
    release_from_mapping,
    validate_activation_plan,
    validate_release_bindings,
    validate_release_for_source_set,
)


def _view(*, restricted: bool = False):
    package = package_from_mapping(
        {
            "schema_version": "dataset-package-v2",
            "package_id": "company-rules" if restricted else "public-law",
            "dataset_id": "company-rules" if restricted else "public-law",
            "version_id": "v1",
            "variant_id": "real",
            "generation_id": "package-gen-1",
            "source_origin": (
                "restricted_internal" if restricted else "public_external"
            ),
            "security_class": "restricted" if restricted else "public",
            "representation": "real",
            "authority": "authoritative",
            "export_policy": {"allowed": not restricted},
            "build": {
                "build_id": "build-1",
                "execution_site": "genos" if restricted else "outside",
                "code_revision": "abc123",
                "compiler_profile": "semantic-v1",
                "capabilities": ["structure", "semantic"],
            },
            "artifacts": [
                {
                    "logical_id": "law-26",
                    "role": "semantic",
                    "path": "SEMANTIC/law-26.jsonl",
                    "sha256": "1" * 64,
                }
            ],
        }
    )
    return compose_source_set(
        {
            "schema_version": "source-set-v1",
            "source_set_id": "production-set",
            "generation_id": "source-gen-1",
            "conflict_policy": "error",
            "members": [{"package_id": package.package_id, "priority": 10}],
        },
        [package],
    )


def _manifest(view):
    return {
        "schema_version": "release-manifest-v1",
        "release_id": "genos-release-1",
        "target": "genos",
        "layout_version": "v1",
        "created_at": "2026-09-02T00:00:00Z",
        "code": {"revision": "c" * 40, "package_sha256": "2" * 64},
        "main": {
            "pipeline_id": "legalclosure-v2",
            "runtime_profile": "legalclosure-v2",
            "generation": 0,
            "state_sha256": "3" * 64,
            "promotion_receipt_sha256": None,
        },
        "source_set": {
            "id": view.source_set_id,
            "generation_id": view.generation_id,
            "sha256": view.source_set_sha256,
            "export_allowed": view.export_allowed,
        },
        "semantics": {
            "generation_id": "semantic-gen-1",
            "authority_generation": "authority-gen-1",
            "content_sha256": "4" * 64,
            "source_set_sha256": view.source_set_sha256,
            "runtime_wired": True,
        },
        "indexes": [
            {
                "kind": "lexical",
                "artifact_id": "lexical-production-1",
                "artifact_sha256": "5" * 64,
                "source_set_sha256": view.source_set_sha256,
                "semantic_generation": "semantic-gen-1",
                "build_fingerprint": "d" * 64,
            },
            {
                "kind": "vector",
                "artifact_id": "vector-production-1",
                "artifact_sha256": "6" * 64,
                "source_set_sha256": view.source_set_sha256,
                "semantic_generation": "semantic-gen-1",
                "build_fingerprint": "e" * 64,
                "embedding_model_fingerprint": "f" * 64,
            },
        ],
    }


def _activation_plan(release, *, current_pointer=None):
    current_generation = 0 if current_pointer is None else current_pointer["generation"]
    current_hash = None
    current_release = None
    if current_pointer is not None:
        current_hash = hashlib.sha256(
            json.dumps(
                current_pointer,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        current_release = current_pointer["release_id"]
    return {
        "schema_version": "release-activation-plan-v1",
        "activation_id": "activate-release-1",
        "target": release.target,
        "created_at": "2026-09-02T00:05:00Z",
        "release_id": release.release_id,
        "release_manifest_sha256": release.manifest_sha256,
        "expected_active_generation": current_generation,
        "expected_active_pointer_sha256": current_hash,
        "rollback_release_id": current_release,
        "validation_receipts": [
            {"kind": kind, "receipt_id": f"{kind}-check-1", "sha256": char * 64}
            for kind, char in zip(
                ("schema", "hash", "acl", "smoke", "provenance"),
                ("7", "8", "9", "a", "b"),
                strict=True,
            )
        ],
    }


def test_release_binds_code_main_source_semantics_and_indexes():
    view = _view()
    release = release_from_mapping(_manifest(view))

    validate_release_for_source_set(release, view)

    assert len(release.manifest_sha256) == 64
    assert release.receipt()["source_set_sha256"] == view.source_set_sha256
    assert release.receipt()["indexes"]["lexical"]["build_fingerprint"] == "d" * 64
    assert release.receipt()["indexes"]["vector"][
        "embedding_model_fingerprint"
    ] == "f" * 64


def test_release_rejects_an_index_from_another_source_set():
    view = _view()
    blob = _manifest(view)
    blob["indexes"][1]["source_set_sha256"] = "c" * 64

    with pytest.raises(ReleaseContractError, match="another source set"):
        release_from_mapping(blob)


def test_release_rejects_vector_index_without_embedding_fingerprint():
    view = _view()
    blob = _manifest(view)
    del blob["indexes"][1]["embedding_model_fingerprint"]

    with pytest.raises(ReleaseContractError, match="embedding_model_fingerprint"):
        release_from_mapping(blob)


def test_release_rejects_semantics_that_are_not_runtime_wired():
    view = _view()
    blob = _manifest(view)
    blob["semantics"]["runtime_wired"] = False

    with pytest.raises(ReleaseContractError, match="runtime_wired"):
        release_from_mapping(blob)


def test_release_rejects_missing_validation_gate():
    view = _view()
    release = release_from_mapping(_manifest(view))
    blob = _activation_plan(release)
    blob["validation_receipts"] = blob["validation_receipts"][:-1]

    with pytest.raises(ReleaseContractError, match="provenance"):
        activation_plan_from_mapping(blob)


def test_release_cannot_claim_a_restricted_source_set_is_exportable():
    restricted = _view(restricted=True)
    public = _view(restricted=False)
    blob = _manifest(restricted)
    blob["source_set"]["export_allowed"] = True
    release = release_from_mapping(blob)

    with pytest.raises(ReleaseContractError, match="export_allowed"):
        validate_release_for_source_set(release, restricted)

    # A structurally valid release is still locked to one exact view.
    with pytest.raises(ReleaseContractError, match="sha256"):
        validate_release_for_source_set(release, public)


def test_declared_manifest_hash_must_match_canonical_content():
    view = _view()
    blob = deepcopy(_manifest(view))
    blob["manifest_sha256"] = "f" * 64

    with pytest.raises(ReleaseContractError, match="manifest_sha256 mismatch"):
        release_from_mapping(blob)


def test_release_cross_checks_installed_main_semantics_and_indexes():
    view = _view()
    blob = _manifest(view)
    main_state = {
        "schema_version": "main-rag-pipeline-v1",
        "pipeline_id": "legalclosure-v2",
        "runtime_profile": "legalclosure-v2",
        "generation": 0,
        "active_promotion_id": None,
        "active_promotions": [],
        "switches": {},
        "code_artifacts": [],
        "updated_at": None,
    }
    blob["main"]["state_sha256"] = hashlib.sha256(
        json.dumps(
            main_state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    release = release_from_mapping(blob)
    semantic_snapshot = {
        "generation_id": release.semantics.generation_id,
        "authority_generation": release.semantics.authority_generation,
        "content_sha256": release.semantics.content_sha256,
        "source_set_sha256": release.semantics.source_set_sha256,
        "runtime_wired": True,
    }
    index_snapshots = {
        index.kind: {
            "artifact_id": index.artifact_id,
            "artifact_sha256": index.artifact_sha256,
            "source_set_sha256": index.source_set_sha256,
            "semantic_generation": index.semantic_generation,
            "build_fingerprint": index.build_fingerprint,
            "embedding_model_fingerprint": index.embedding_model_fingerprint,
        }
        for index in release.indexes
    }

    validate_release_bindings(
        release,
        view=view,
        main_state=main_state,
        main_promotion_receipt_sha256=None,
        main_promotion_plan_sha256=None,
        semantic_snapshot=semantic_snapshot,
        index_snapshots=index_snapshots,
    )

    index_snapshots["vector"] = {
        **index_snapshots["vector"],
        "embedding_model_fingerprint": "0" * 64,
    }
    with pytest.raises(ReleaseContractError, match="embedding_model_fingerprint"):
        validate_release_bindings(
            release,
            view=view,
            main_state=main_state,
            main_promotion_receipt_sha256=None,
            main_promotion_plan_sha256=None,
            semantic_snapshot=semantic_snapshot,
            index_snapshots=index_snapshots,
        )


def test_activation_plan_is_bound_to_release_and_current_pointer():
    release = release_from_mapping(_manifest(_view()))
    current = {
        "schema_version": "active-release-v1",
        "generation": 3,
        "release_id": "genos-release-0",
        "release_manifest_sha256": "0" * 64,
    }
    plan = activation_plan_from_mapping(
        _activation_plan(release, current_pointer=current)
    )

    validate_activation_plan(plan, release, current_pointer=current)

    changed = {**current, "generation": 4}
    with pytest.raises(ReleaseContractError, match="stale or incompatible"):
        validate_activation_plan(plan, release, current_pointer=changed)
