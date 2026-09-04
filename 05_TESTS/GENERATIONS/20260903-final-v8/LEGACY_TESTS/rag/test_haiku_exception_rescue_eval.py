from scripts import rag_haiku_exception_rescue_eval as evaluate


def _record(pass_name, target):
    return {
        "case_no": "cm-x", "pass_name": pass_name,
        "fingerprint": ("EXCEPTION_TO", "source", target),
        "relation": {"relation_type": "EXCEPTION_TO"},
        "inventory": [], "source_path": "제2조", "target_path": target,
    }


def test_aggregate_separates_union_and_two_pass_consensus():
    result = evaluate.aggregate([
        _record("r1", "제1조"), _record("r2", "제1조"),
        _record("r1", "제3조"),
    ], ["r1", "r2"])
    assert result["union_count"] == 2
    assert result["stable_count"] == 1
    assert result["stable"][0]["target_path"] == "제1조"


def test_case_identity_prevents_cross_case_false_consensus():
    left = _record("r1", "제1조")
    right = _record("r2", "제1조")
    right["case_no"] = "cm-y"
    result = evaluate.aggregate([left, right], ["r1", "r2"])
    assert result["union_count"] == 2
    assert result["stable_count"] == 0
