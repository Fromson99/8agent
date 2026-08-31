import json

from scripts import rag_proof_guided_span_golden_61 as runner


def test_trailing_comma_repair_never_changes_commas_inside_strings():
    raw = '{"literal":"keep,}","rows":[1,2,],}'

    repaired, count = runner._repair_trailing_commas(raw)

    assert count == 2
    assert json.loads(repaired) == {"literal": "keep,}", "rows": [1, 2]}


def test_usage_separates_recovered_from_unrecovered_provider_errors():
    calls = [{
        "provider": {"error": "JSONDecodeError: trailing comma", "usage": {}},
        "deterministic_repair": {"kind": "trailing_comma", "success": True},
    }]

    usage = runner._usage(calls)

    assert usage["errors"] == 1
    assert usage["provider_errors"] == 1
    assert usage["recovered_errors"] == 1
    assert usage["unrecovered_errors"] == 0
