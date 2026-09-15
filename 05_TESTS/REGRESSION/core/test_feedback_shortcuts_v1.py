from __future__ import annotations

import json

import pytest

from lawrag.feedback.shortcuts import (
    ShortcutContractError,
    ShortcutResolutionContext,
    build_signature,
    load_shortcuts,
    select_shortcut,
    shortcut_from_mapping,
)


def _signature(*, semantic_generation="semantic-1"):
    return build_signature(
        source_set_sha256="a" * 64,
        authority_generation="authority-1",
        semantic_generation=semantic_generation,
        scopes=["코스닥시장"],
        actors=["재무적 투자자"],
        actions=["취득"],
        conditions=["제3자 배정"],
        requested_outputs=["의무보유기간"],
    )


def _shortcut(signature, shortcut_id="shortcut-1", status="REVIEWED"):
    return shortcut_from_mapping(
        {
            "schema_version": "query-shortcut-v1",
            "shortcut_id": shortcut_id,
            "status": status,
            "signature_sha256": signature.sha256,
            "source_set_sha256": signature.source_set_sha256,
            "authority_generation": signature.authority_generation,
            "semantic_generation": signature.semantic_generation,
            "landings": [
                {"kind": "RULE", "id": "rule:26-1-3"},
                {"kind": "PROVISO", "id": "proviso:26-1-3-p1"},
            ],
            "feedback_event_ids": ["feedback:cm-003"],
            "evidence_receipt_sha256": "b" * 64,
            "bundle_sha256": "c" * 64,
            "revision": 1,
            "previous_record_sha256": None,
        }
    )


def _context(shortcut):
    return ShortcutResolutionContext.build(
        visible_landings={(landing.kind, landing.id) for landing in shortcut.landings},
        evidence_receipt_sha256s={shortcut.evidence_receipt_sha256},
    )


def test_signature_normalizes_surface_spacing_without_losing_generation():
    first = _signature()
    second = build_signature(
        source_set_sha256="a" * 64,
        authority_generation="authority-1",
        semantic_generation="semantic-1",
        scopes=" 코스닥 시장 ",
        actors="재무적투자자",
        actions="취 득",
        conditions="제3자배정",
        requested_outputs="의무보유 기간",
    )

    assert first.sha256 == second.sha256


def test_candidate_shortcut_never_changes_runtime_selection():
    signature = _signature()
    shortcut = _shortcut(signature, status="CANDIDATE")

    assert select_shortcut([shortcut], signature, context=_context(shortcut)) is None


def test_reviewed_shortcut_is_exact_and_generation_locked():
    signature = _signature()
    shortcut = _shortcut(signature)

    assert select_shortcut([shortcut], signature, context=_context(shortcut)) == shortcut
    assert (
        select_shortcut(
            [shortcut],
            _signature(semantic_generation="semantic-2"),
            context=_context(shortcut),
        )
        is None
    )


def test_multiple_reviewed_shortcuts_for_same_signature_fail_closed():
    signature = _signature()
    first = _shortcut(signature, "shortcut-1")
    second = _shortcut(signature, "shortcut-2")

    with pytest.raises(ShortcutContractError, match="ambiguous reviewed shortcuts"):
        select_shortcut(
            [first, second],
            signature,
            context=_context(first),
        )


def test_shortcut_cannot_bypass_current_landing_visibility_or_evidence():
    signature = _signature()
    shortcut = _shortcut(signature)
    empty = ShortcutResolutionContext.build(
        visible_landings=[], evidence_receipt_sha256s=[]
    )

    with pytest.raises(ShortcutContractError, match="missing or not visible"):
        select_shortcut([shortcut], signature, context=empty)

    no_evidence = ShortcutResolutionContext.build(
        visible_landings={
            (landing.kind, landing.id) for landing in shortcut.landings
        },
        evidence_receipt_sha256s=[],
    )
    with pytest.raises(ShortcutContractError, match="evidence receipt"):
        select_shortcut([shortcut], signature, context=no_evidence)


def test_signature_requires_meaningful_query_axes():
    with pytest.raises(ShortcutContractError, match="at least one semantic axis"):
        build_signature(
            source_set_sha256="a" * 64,
            authority_generation="authority-1",
            semantic_generation="semantic-1",
        )


def test_append_only_revisions_fold_candidate_to_reviewed(tmp_path):
    signature = _signature()
    candidate_blob = {
        "schema_version": "query-shortcut-v1",
        "shortcut_id": "shortcut-chain",
        "status": "CANDIDATE",
        "signature_sha256": signature.sha256,
        "source_set_sha256": signature.source_set_sha256,
        "authority_generation": signature.authority_generation,
        "semantic_generation": signature.semantic_generation,
        "landings": [{"kind": "RULE", "id": "rule:26-1-3"}],
        "feedback_event_ids": [],
        "evidence_receipt_sha256": "b" * 64,
        "bundle_sha256": None,
        "revision": 1,
        "previous_record_sha256": None,
    }
    candidate = shortcut_from_mapping(candidate_blob)
    reviewed_blob = {
        **candidate_blob,
        "status": "REVIEWED",
        "feedback_event_ids": ["feedback:cm-003"],
        "revision": 2,
        "previous_record_sha256": candidate.record_sha256,
    }
    store = tmp_path / "shortcuts.jsonl"
    store.write_text(
        "\n".join(json.dumps(row) for row in (candidate_blob, reviewed_blob)) + "\n",
        "utf-8",
    )

    loaded = load_shortcuts(store)

    assert len(loaded) == 1
    assert loaded[0].status == "REVIEWED"
    assert loaded[0].revision == 2
