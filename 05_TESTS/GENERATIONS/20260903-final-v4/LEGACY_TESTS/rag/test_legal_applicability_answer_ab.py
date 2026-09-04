from scripts.rag_legal_applicability_answer_ab import gated_evidence


class _Ontology:
    pass


def test_gated_evidence_keeps_only_conclusion_candidates(monkeypatch):
    evidence = [{"id": "E1"}, {"id": "E2"}]

    def classify(_question, rows, _ontology):
        assert rows is evidence
        return [
            {"id": "E1", "applicability": {"conclusion_candidate": False}},
            {"id": "E2", "applicability": {"conclusion_candidate": True}},
        ]

    monkeypatch.setattr(
        "scripts.rag_legal_applicability_answer_ab.classify_applicability", classify)
    assert gated_evidence("질문", evidence, _Ontology()) == [
        {"id": "E2", "applicability": {"conclusion_candidate": True}}]
