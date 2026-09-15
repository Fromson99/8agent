from lawrag.core.rag.assertion_shortcuts import (
    ShortcutEntry,
    ShortcutIndex,
    ShortcutProof,
    load_runtime,
)
from lawrag.research.experiments.typed_assertion_shortcuts import (
    TypedShortcutEntry,
    TypedShortcutIndex,
)


def _entry(trace="cm-001"):
    proofs = (
        ShortcutProof(
            "assertion:a", ("doc", 10), {"PREDICATE": {"grade": "G3"}}),
        ShortcutProof(
            "assertion:b", ("doc", 10), {"OBJECT": {"grade": "G3"}}),
    )
    return ShortcutEntry(
        required_assertions=("assertion:a", "assertion:b"),
        targets=(("doc", 10),), proofs=proofs,
        corpus_fingerprint="corpus-v1",
        query_assertions=("assertion:a", "assertion:b"), source_trace=trace)


def test_lookup_uses_structured_assertion_ids_not_question_text():
    index = ShortcutIndex([_entry()])

    hits = index.lookup(["assertion:x", "assertion:b", "assertion:a"])

    assert [hit.target for hit in hits] == [("doc", 10)]
    assert hits[0].matched_assertions == ("assertion:a", "assertion:b")


def test_incomplete_proof_does_not_open_shortcut():
    index = ShortcutIndex([_entry()])

    assert index.lookup(["assertion:a"]) == []


def test_cross_question_audit_can_exclude_own_trace():
    index = ShortcutIndex([_entry()])

    assert index.lookup(
        ["assertion:a", "assertion:b"], exclude_traces={"cm-001"}) == []


def test_ambiguous_compiled_routes_fall_back_instead_of_filling_cap():
    first = _entry("cm-001")
    second = ShortcutEntry(
        required_assertions=("assertion:a", "assertion:b"),
        targets=(("other", 20),), proofs=first.proofs,
        corpus_fingerprint="corpus-v1", source_trace="cm-002")
    index = ShortcutIndex([first, second])

    assert index.lookup(
        ["assertion:a", "assertion:b"], require_unambiguous=True) == []


def test_extracted_assertion_signature_identifies_compiled_route():
    first = ShortcutEntry(
        required_assertions=("assertion:a",), targets=(("doc", 10),),
        proofs=_entry().proofs, corpus_fingerprint="corpus-v1",
        query_assertions=("assertion:top", "assertion:a"), source_trace="cm-001")
    index = ShortcutIndex([first])

    assert index.lookup(
        ["assertion:top", "assertion:a"], require_query_signature=True)
    assert index.lookup(
        ["assertion:other", "assertion:a"], require_query_signature=True) == []


def test_typed_shortcut_requires_all_canonical_role_parts():
    proof = _entry().proofs
    entry = TypedShortcutEntry(
        required_parts=("ACTOR:concept:company", "PREDICATE:concept:dispose"),
        targets=(("doc", 10),), proofs=proof, corpus_fingerprint="v1")
    index = TypedShortcutIndex([entry])

    assert index.lookup([
        "PREDICATE:concept:dispose", "ACTOR:concept:company"])
    assert index.lookup(["PREDICATE:concept:dispose"]) == []


def test_runtime_loader_rejects_stale_corpus_and_accepts_current_proof(tmp_path):
    path = tmp_path / "shortcuts.json"
    row = _entry().as_dict()
    row["query_assertions"] = ["assertion:a", "assertion:b"]
    blob = {
        "schema_version": 1,
        "approval": {"approved_by": "reviewer", "approved_at": "2026-08-25"},
        "entries": [row],
    }
    path.write_text(__import__("json").dumps(blob), encoding="utf-8")

    stale = load_runtime(corpus_fingerprint="stale", path=path)
    ready = load_runtime(corpus_fingerprint="corpus-v1", path=path)
    assert stale.status == "stale" and not stale.entries
    assert ready.status == "ready" and len(ready.entries) == 1


def test_runtime_loader_rejects_unapproved_or_incomplete_proof(tmp_path):
    import json

    path = tmp_path / "shortcuts.json"
    row = _entry().as_dict()
    row["query_assertions"] = ["assertion:a", "assertion:b"]
    path.write_text(json.dumps({"schema_version": 1, "entries": [row]}),
                    encoding="utf-8")
    assert load_runtime(corpus_fingerprint="corpus-v1", path=path).status == "rejected"

    row["proofs"] = []
    path.write_text(json.dumps({
        "schema_version": 1,
        "approval": {"approved_by": "reviewer", "approved_at": "2026-08-25"},
        "entries": [row],
    }), encoding="utf-8")
    result = load_runtime(corpus_fingerprint="corpus-v1", path=path)
    assert result.status == "rejected"
    assert "entry_0:incomplete_route" in result.reasons
