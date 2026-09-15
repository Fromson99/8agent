from scripts.rag_haiku_source_relations_consensus_materialize import materialize


def test_materialize_revalidates_and_keeps_support_metadata():
    inventory = [{
        "evidence_id": "E1", "document": "A법", "path": "제1조",
        "document_revision": "1", "document_enforcement": "1",
        "document_current": True,
    }]
    relation = {
        "case_no": "cm-001", "relation_id": "R1",
        "relation_type": "GOVERNS_ACTOR", "source_id": "E1", "target_id": "",
        "target_value": "회사의 대표자", "defined_term": "",
        "quote_ids": ["E1:L1"], "evidence_statement": "주체", "confidence": "high",
        "proof_quotes": [{"quote_id": "E1:L1", "evidence_id": "E1",
                          "kind": "source", "text": "회사의 대표자는 신고한다."}],
        "validation_errors": [], "source_path": "제1조", "target_path": "",
    }
    consensus = {
        "all_contract_checks_pass": True, "inputs": ["p1", "p2"],
        "exact": {"consensus_relations": [{
            "support_count": 2, "passes": ["p1", "p2"],
            "representative": relation,
        }]},
    }
    template = {"rows": [{
        "case_no": "cm-001", "inventory": inventory,
        "product_input_sha256": "abc",
    }]}
    result = materialize(consensus, template)
    published = result["rows"][0]["published"]
    assert result["summary"]["published_relations"] == 1
    assert published[0]["consensus_support_count"] == 2
    assert published[0]["proof_quotes"][0]["text"] == "회사의 대표자는 신고한다."
