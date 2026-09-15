from scripts.rag_source_relation_reference_edge_audit import classify_reference_support


def test_formal_reception_edge_proves_implementation():
    assert classify_reference_support([{"rel": "수임"}]) == "formal_reception_proven"


def test_ordinary_reference_does_not_prove_implementation():
    assert classify_reference_support([{"rel": "근거"}]) == (
        "reference_but_not_implementation")
    assert classify_reference_support([{"rel": "인용"}]) == (
        "reference_but_not_implementation")


def test_missing_edge_stays_unproven():
    assert classify_reference_support([]) == "no_matching_reference_edge"
