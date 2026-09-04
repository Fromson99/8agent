from scripts.rag_governing_anchor_answer_ab import panel_evidence


def test_panel_evidence_preserves_panel_order_and_original_rows(monkeypatch):
    evidence = [{"id": "E1", "value": 1}, {"id": "E2", "value": 2}]

    def fake_panel(_question, _evidence, *, max_candidates):
        assert max_candidates == 2
        return [{"evidence_id": "E2"}, {"evidence_id": "E1"}]

    monkeypatch.setattr(
        "scripts.rag_governing_anchor_answer_ab.governing_anchor_panel", fake_panel)
    selected, panel = panel_evidence("질문", evidence, 2)
    assert [row["id"] for row in selected] == ["E2", "E1"]
    assert panel == [{"evidence_id": "E2"}, {"evidence_id": "E1"}]
