from lawrag.core.rag.experiments.haiku_claim_edges import (
    claim_fingerprint,
    consensus_claims,
    deterministic_modality,
    entailment_matrix,
    validate_alignment,
    validate_claim_decisions,
    validate_closed_line_decisions,
)


def _cards():
    return [{"card_id": "E1:L1", "quote_id": "E1:L1", "evidence_id": "E1",
             "document": "A법", "path": "제1조", "text": "회사는 신고하여야 한다."}]


def _decision(**changes):
    row = {"card_id": "E1:L1", "verdict": "CLAIM", "claim_kind": "DUTY",
           "actor": "회사", "predicate": "신고하여야 한다", "object": "",
           "modality": "MUST", "conditions": [], "exceptions": [],
           "quantities": [], "temporals": [], "effect": "", "confidence": "high"}
    row.update(changes)
    return row


def test_claim_guard_publishes_only_exact_high_confidence_slots():
    result = validate_claim_decisions([{"decisions": [_decision()]}], _cards())
    assert result["complete_decision_contract"]
    assert len(result["published"]) == 1
    bad = validate_claim_decisions([{"decisions": [_decision(actor="사업자")]}], _cards())
    assert not bad["published"]
    assert "actor_not_exact_substring" in bad["rejected"][0]["validation_errors"]


def test_missing_card_decision_fails_complete_contract():
    result = validate_claim_decisions([{"decisions": []}], _cards())
    assert not result["complete_decision_contract"]
    assert result["missing_card_ids"] == ["E1:L1"]


def test_consensus_requires_same_claim_slots_not_just_same_card():
    one = validate_claim_decisions([{"decisions": [_decision()]}], _cards())
    two = validate_claim_decisions([{"decisions": [_decision(modality="NEUTRAL")]}], _cards())
    assert claim_fingerprint(one["published"][0]) != claim_fingerprint(two["published"][0])
    assert not consensus_claims([one, two])
    assert len(consensus_claims([one, one])) == 1


def test_alignment_must_decide_every_claim_and_matrix_keeps_slots():
    claim = {**validate_claim_decisions(
        [{"decisions": [_decision()]}], _cards())["published"][0], "claim_id": "CC001"}
    aligned = validate_alignment({"requested_slots": ["CONCLUSION", "AUTHORITY"],
        "decisions": [{"claim_id": "CC001", "verdict": "RELEVANT",
                       "slots": ["CONCLUSION"], "reason": "직접 의무",
                       "confidence": "high"}]}, [claim])
    assert aligned["valid"]
    matrix = entailment_matrix([claim], aligned)
    assert matrix["covered_slots"] == ["CONCLUSION"]
    assert matrix["uncovered_slots"] == ["AUTHORITY"]


def test_closed_line_claim_keeps_deterministic_full_source_span():
    raw = {"decisions": [{"card_id": "E1:L1", "verdict": "NORMATIVE",
                           "claim_kind": "DUTY", "confidence": "high"}]}
    result = validate_closed_line_decisions([raw], _cards())
    assert result["complete_decision_contract"]
    assert result["published"][0]["predicate"] == "회사는 신고하여야 한다."
    assert result["published"][0]["modality"] == "MUST"


def test_deterministic_modality_prefers_prohibition_over_permission_surface():
    assert deterministic_modality("신청할 수 없다") == "MUST_NOT"
