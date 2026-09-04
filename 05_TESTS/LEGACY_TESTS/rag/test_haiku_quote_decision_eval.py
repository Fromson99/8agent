from scripts import rag_haiku_quote_decision_eval as evaluate


def test_holdout_is_preregistered_order():
    assert len(evaluate.HOLDOUT12) == 12
    assert evaluate.HOLDOUT12[0] == "cm-022"
    assert evaluate.HOLDOUT12[-1] == "cm-027"


def test_summary_reports_router_and_guard_metrics():
    rows = [{
        "action": "replace", "guard": "validated_quote_decision",
        "validations": {"final": {"valid": True}},
        "certificate": {"valid": True}, "tiebreak": None,
        "always_three_calls_saved": 1,
        "critical_value_audit": {"flagged": False, "unsupported_values": []},
        "usage": {"calls": 3, "input_tokens": 10, "output_tokens": 2,
                  "duration_ms": 5, "errors": 0}, "wall_ms": 7,
    }]
    summary = evaluate.summarize(rows)
    assert summary["valid_certificates"] == 1
    assert summary["always_three_plan_calls_saved"] == 1
    assert summary["product_usage"]["calls"] == 3
