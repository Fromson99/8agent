from __future__ import annotations

from copy import deepcopy

from scripts import rag_proof_basis_exchange_golden_61 as runner


def _parent_row() -> dict:
    coordinate = {
        "rank": 1,
        "doc_id": "doc",
        "node": 7,
        "doc": "법령",
        "path": "제1조",
        "origin": "test",
    }
    return {
        "number": 1,
        "case_id": "case-1",
        "suite": "suite",
        "question": "질문",
        "input_state": {"terms": ["용어"]},
        "gold_results": [{"doc_id": "secret", "node": 99}],
        "paired": {"secret": True},
        "arms": {
            "baseline": {
                "selected": [coordinate],
                "gold_results": [{"secret": True}],
            },
            "recall-first-union": {
                "selected": [coordinate],
                "internal_pool": [coordinate],
                "gold_results": [{"secret": True}],
            },
        },
    }


def test_safe_projection_whitelists_retrieval_state_only():
    value = runner.safe_projection(_parent_row())

    assert value["case_id"] == "case-1"
    assert value["incumbent"][0]["doc_id"] == "doc"
    assert runner._contains_banned_key(value) is False
    assert "arms" not in value
    assert "gold_results" not in value
    assert "paired" not in value


def test_gold_canary_does_not_change_product_projection():
    left = _parent_row()
    right = deepcopy(left)
    right["gold_results"] = [{"doc_id": "changed", "node": -1}]
    right["paired"] = {"changed": "yes"}
    right["arms"]["baseline"]["gold_results"] = [{"changed": True}]
    right["arms"]["recall-first-union"]["gold_results"] = [
        {"changed": True}]

    assert runner.safe_projection(left) == runner.safe_projection(right)
    assert runner._json_sha(runner.safe_projection(left)) == runner._json_sha(
        runner.safe_projection(right))
