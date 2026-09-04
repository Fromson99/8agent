from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.domain_graph.uncertainty import claim_metadata, review_state


def test_review_state_never_equates_batch_acceptance_with_human_verification():
    assert review_state(approved_by="user:force-all") == "batch_accepted"
    assert review_state(approved_by="llm:reviewer") == "model_reviewed"
    assert review_state(approved_by="user:someone") == "declared_approved"
    assert review_state(explicit="human_verified") == "human_verified"


def test_candidate_metadata_does_not_invent_confidence():
    props = claim_metadata(
        evidence_type="same_source_node_proximity",
        claim_status="candidate", consumer_policy="candidate_only")

    assert "confidence" not in props
    assert props["review_state"] == "unreviewed"
    assert props["uncertainty_policy"] == "may_be_wrong"


def test_extended_concept_types_remain_strict_but_loadable(tmp_path):
    canonical = tmp_path / "canonical.json"
    canonical.write_text(
        '{"schema_version":1,"concepts":['
        '{"id":"debt_workout","label":"채무조정",'
        '"type":"legal_operation","status":"active",'
        '"approved_by":"user:test","review_state":"declared_approved"}'
        '],"relations":[],"assertions":[]}', encoding="utf-8")

    concept = Tier1Registry.load(canonical).active_concepts[
        "concept:debt_workout"]
    assert concept.type == "legal_operation"
    assert concept.review_state == "declared_approved"
