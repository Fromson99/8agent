from scripts import rag_source_registry_admission_golden_61 as runner


def test_zero_usage_has_complete_accounting_keys():
    usage = runner._zero_usage()

    assert usage["calls"] == 0
    assert usage["errors"] == 0
    assert usage["input_tokens"] == 0


def test_percentile_is_bounded():
    assert runner._percentile([], .95) == 0
    assert runner._percentile([1, 2, 3], .95) == 3
