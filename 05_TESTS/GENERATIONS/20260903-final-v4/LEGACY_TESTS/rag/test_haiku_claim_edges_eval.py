from scripts.rag_haiku_claim_edges_eval import summarize


def test_summary_reports_repeat_stability_and_contracts():
    claim = {"claim_id": "C001", "quote_id": "E1:L1", "claim_kind": "DUTY",
             "modality": "MUST", "actor": "회사", "predicate": "신고한다",
             "object": "", "conditions": [], "exceptions": [], "quantities": [],
             "temporals": [], "effect": ""}
    passes = [{"model": "claude-haiku-4-5-20251001", "cards": [{}],
               "published": [claim], "rejected": [], "usage": {"calls": 1},
               "complete_decision_contract": True, "product_input_sha256": "same"},
              {"model": "claude-haiku-4-5-20251001", "cards": [{}],
               "published": [claim], "rejected": [], "usage": {"calls": 1},
               "complete_decision_contract": True, "product_input_sha256": "same"}]
    result = summarize([{"case_no": "cm-001", "passes": passes}])
    assert result["consensus_claims"] == 1
    assert result["stability"]["jaccard"] == 1.0
    assert result["complete_decision_contracts"] == 2
