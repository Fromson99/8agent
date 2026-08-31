from __future__ import annotations

import inspect
from types import SimpleNamespace

from lawrag.core.rag import issue_role_atomic_entailment_research as compiler
from lawrag.core.rag import legalclosure_runtime
from lawrag.core.rag.legal_research_state import CandidateProvenance


QUESTION = "회사는 허가를 받아야 하는가"
EVIDENCE_ID = compiler.legacy._candidate_id(("DOC", 10))


def _menu():
    return [{
        "evidence_id": EVIDENCE_ID,
        "coordinate": ["DOC", 10],
        "document": "법률",
        "path": "제10조",
        "scope_id": "DOMAIN:TEST",
        "origins": ["SYSTEM_PRIOR"],
        "branch": "rule",
        "coverage_keys": [],
        "matched": ["허가"],
        "span": {"start": 0, "end": 20, "excerpt": "회사는 허가를 받아야 한다."},
    }]


def _raw(*, strength="DIRECT_TEXT", quote="허가를 받아야 한다"):
    return {
        "issues": [{
            "issue_id": "I1",
            "question_span": "허가를 받아야 하는가",
            "required_roles": ["GOVERNING_RULE"],
            "requirements": [{
                "requirement_id": "R1",
                "kind": "governing_rule",
                "question_span": "허가를 받아야 하는가",
            }],
        }],
        "units": [{
            "unit_id": "U1", "evidence_id": EVIDENCE_ID,
            "scope_id": "DOMAIN:TEST", "issue_ids": ["I1"],
            "role": "GOVERNING_RULE", "quote": quote,
        }],
        "entailments": [{
            "requirement_id": "R1", "unit_id": "U1", "strength": strength,
        }],
        "answer_mode": "DIRECT_RULE",
        "reason": "test",
    }


def test_question_and_source_spans_are_closed_and_direct_is_recomputed():
    raw = _raw(quote="없는 문언")
    raw["issues"][0]["question_span"] = "질문에 없는 쟁점"
    packet = compiler._sanitize_packet(raw, _menu(), QUESTION)
    assert packet["issues"][0]["issue_id"] == "I1"
    assert packet["units"] == []
    assert packet["answer_mode"] == "INSUFFICIENT"
    assert packet["direct_gate_allowed"] is False


def test_direct_requires_every_requirement_and_governing_unit():
    direct = compiler._sanitize_packet(_raw(), _menu(), QUESTION)
    assert direct["answer_mode"] == "DIRECT_RULE"
    assert direct["missing_requirements"] == []
    inferred = compiler._sanitize_packet(
        _raw(strength="NEEDS_INFERENCE"), _menu(), QUESTION
    )
    assert inferred["answer_mode"] == "CONDITIONAL_APPLICATION"
    assert inferred["missing_requirements"] == ["R1"]


def test_atomic_prune_never_leaves_claim_or_entailment_without_evidence():
    packet = compiler._sanitize_packet(_raw(), _menu(), QUESTION)
    pruned = compiler._prune_packet_atomic(packet, [])
    assert pruned["units"] == []
    assert pruned["claims"] == []
    assert pruned["entailments"] == []
    assert pruned["answer_mode"] == "INSUFFICIENT"


def test_issue_role_quota_preserves_compiled_governing_cell_under_cap():
    packet = compiler._sanitize_packet(_raw(), _menu(), QUESTION)
    coordinate = ("DOC", 10)
    candidate = SimpleNamespace(
        origins={CandidateProvenance.SYSTEM_PRIOR}, coverage_keys=set(),
        score=1.0, source_order=0,
    )
    selected, pruned = compiler._atomic_quota_select(
        QUESTION, packet, [coordinate], set(), {coordinate: candidate},
        {coordinate: (0, 20, "회사는 허가를 받아야 한다.")},
        frozenset(), {coordinate: "DOMAIN:TEST"}, cap=1,
    )
    assert selected == [coordinate]
    assert pruned["quota"]["missing"] == []
    assert {row["evidence_id"] for row in pruned["claims"]} == {EVIDENCE_ID}
    assert len(selected) <= 1


def test_runtime_default_stays_legacy_and_v3_requires_explicit_profile():
    parameter = inspect.signature(legalclosure_runtime.retrieve).parameters[
        "integrated_profile"
    ]
    assert parameter.default == "legacy"
    source = inspect.getsource(legalclosure_runtime.retrieve)
    assert 'integrated_profile == "issue-role-atomic-entailment-v3"' in source
