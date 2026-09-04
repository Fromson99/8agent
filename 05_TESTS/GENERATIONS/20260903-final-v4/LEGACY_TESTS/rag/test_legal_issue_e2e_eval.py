from types import SimpleNamespace

from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence, summarize


class FakeView:
    name = "테스트법"
    by_id = {7: {"id": 7}}

    @staticmethod
    def path(node):
        return "제7조 시험"


def test_reconstruct_evidence_accepts_json_string_node(monkeypatch):
    from lawrag.core.rag import exploration

    monkeypatch.setattr(
        exploration, "subtree_text",
        lambda view, node, cap: f"본문-{node}-{cap}")
    index = SimpleNamespace(docs={"doc-1": FakeView()})

    evidence = reconstruct_evidence(index, [{
        "doc_id": "doc-1", "node": "7", "origin": "exact",
    }])

    assert evidence == [{
        "id": "E1", "doc_id": "doc-1", "node": 7,
        "document": "테스트법", "path": "제7조 시험", "role": "exact",
        "relation_reason": "", "original_text": "본문-7-None",
    }]


def test_summary_separates_system_and_semantic_evaluator_cost():
    rows = [{
        "case_no": "x", "retrieval_case_hit": True,
        "basis_case_hit": True, "basis_gold_hits": 1, "gold_total": 1,
        "semantic_correct": True,
        "semantic_grade": {"conclusion_correct": True,
                           "materially_complete": True,
                           "no_material_error": True},
        "frame": {"question_type": "rule_explanation"},
        "verdict": "entailed", "evidence": [{"id": "E1"}],
        "usage": {"calls": 2, "input_tokens": 20, "output_tokens": 2,
                  "duration_ms": 200, "errors": 0},
        "semantic_usage": {"calls": 1, "input_tokens": 10,
                           "output_tokens": 1, "duration_ms": 100,
                           "errors": 0},
        "retrieval_wall_ms": 1000, "product_wall_ms": 200,
        "wall_ms": 300,
    }]
    retrieval = {"calls": 8, "input_tokens": 80, "output_tokens": 8,
                 "duration_ms": 800, "errors": 0,
                 "selected_hits": 1, "gold": 1}

    result = summarize(rows, retrieval)

    assert result["answer"]["semantic_correct"] == 1
    assert result["cost"]["system_end_to_end"]["calls"] == 10
    assert result["cost"]["semantic_evaluator_excluded_from_system"]["calls"] == 1
    assert result["latency"]["system_end_to_end_wall_ms_p50"] == 1200
