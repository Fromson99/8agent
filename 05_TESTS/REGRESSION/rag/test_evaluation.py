from copy import deepcopy
from pathlib import Path

from lawrag.core.rag import evaluation


def _case(cid, expect_hit, expected=(), **axes):
    case = {"id": cid, "question": cid, "expect_hit": expect_hit,
            "axes": {"outcome": "positive" if expect_hit else "negative",
                     "challenge": axes.get("challenge", "plain")}}
    if expected:
        case["expect_sources"] = [
            {"doc_id": doc_id, "node": node} for doc_id, node in expected]
    return case


def _row(case, got=(), errors=(), **usage):
    return evaluation.result_row(case, got_sources=got, errors=list(errors),
                                 hit=bool(got), usage=usage)


def test_summary_separates_recall_blocking_source_and_axis_cost():
    positive = _case("p", True, (("d", "1"),), challenge="paraphrase")
    negative = _case("n", False, challenge="wrong_predicate")
    rows = [
        _row(positive, (("d", "1"),), calls=2, input_tokens=100,
             output_tokens=10, duration_ms=90, ttft_ms=20),
        _row(negative, (), calls=1, input_tokens=40, output_tokens=5,
             duration_ms=30, ttft_ms=10),
    ]

    summary = evaluation.summarize(rows, ["outcome", "challenge"],
                                   shadow={"total": 207, "bad": []})
    metrics = summary["metrics"]
    assert metrics["positive_recall"] == 1.0
    assert metrics["negative_block_rate"] == 1.0
    assert metrics["source_accuracy"] == 1.0
    assert metrics["shadow_clean_rate"] == 1.0
    assert metrics["input_tokens_per_case"] == 70.0
    assert metrics["duration_ms_p95"] == 90.0
    assert {row["value"] for row in summary["axes"]
            if row["axis"] == "challenge"} == {"paraphrase", "wrong_predicate"}


def test_runtime_context_counts_capture_caps_truncation_and_channels():
    case = _case("p", True, (("d", "1"),))
    row = evaluation.result_row(
        case, got_sources=(("d", "1"),), errors=[], hit=True,
        runtime={"final_contexts": 19, "context_chars": 42_000,
                 "truncated_sections": 2, "shared_cap_overflow": True,
                 "channel_counts": {"vector": 4, "doc_companion": 7}})

    summary = evaluation.summarize([row], ["outcome"])
    metrics = summary["metrics"]

    assert metrics["final_contexts_p95"] == 19.0
    assert metrics["context_chars_max"] == 42_000
    assert metrics["shared_cap_overflow_rate"] == 1.0
    assert metrics["truncated_section_rate"] == round(2 / 19, 6)
    assert metrics["channel_totals"] == {"doc_companion": 7, "vector": 4}
    slices = {(item["axis"], item["value"])
              for item in summary["operational_axes"]}
    assert {("entry_channel", "vector"), ("entry_channel", "doc_companion"),
            ("context_count", "13+"), ("context_chars", "24k-72k"),
            ("cap_overflow", "yes"), ("truncation", "yes")} <= slices


def test_unexpected_source_is_explicit_contamination():
    case = _case("p", True, (("right", "1"),))
    row = _row(case, (("wrong", "2"),), errors=("source mismatch",))

    assert row["source_correct"] is False
    assert row["contaminated"] is True
    assert row["unexpected_sources"] == [{"doc_id": "wrong", "node": "2"}]


def _manifest(rows, sha="same"):
    return {
        "schema_version": 1,
        "run": {"label": "run"},
        "suite": {"sha256": sha, "case_ids": [row["id"] for row in rows]},
        "controls": {"fingerprint": "abc"},
        "summary": evaluation.summarize(rows, ["outcome"]),
    }


def test_compare_blocks_safety_or_quality_regression_but_reports_cost():
    p = _case("p", True, (("d", "1"),))
    n = _case("n", False)
    base = _manifest([_row(p, (("d", "1"),), input_tokens=100), _row(n)])
    candidate = _manifest([
        _row(p, (("d", "1"),), input_tokens=200),
        _row(n, (("noise", "9"),), errors=("hit=True",), input_tokens=200),
    ])

    report = evaluation.compare_manifests(base, candidate)

    assert report["verdict"] == "regressed"
    assert {row["measure"] for row in report["regressions"]} >= {
        "negative_block_rate", "contamination_rate",
    }
    assert any(row["measure"] == "input_tokens_per_case"
               for row in report["warnings"])


def test_compare_rejects_different_suite_or_case_set():
    case = _case("p", True, (("d", "1"),))
    base = _manifest([_row(case, (("d", "1"),))], sha="a")
    candidate = deepcopy(base)
    candidate["suite"]["sha256"] = "b"

    report = evaluation.compare_manifests(base, candidate)

    assert report["verdict"] == "invalid"
    assert report["incompatible"] == ["suite_sha256"]


def test_build_manifest_binds_suite_and_control_fingerprints(tmp_path):
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text("name: mini\naxis_order: [outcome]\n", encoding="utf-8")
    case = _case("p", True, (("d", "1"),))
    row = _row(case, (("d", "1"),))

    manifest = evaluation.build_manifest(
        suite_path=suite_path, suite={"name": "mini", "axis_order": ["outcome"]},
        rows=[row], mode="deterministic", run_label="base")

    assert manifest["suite"]["sha256"] == evaluation.suite_sha256(suite_path)
    assert manifest["controls"]["fingerprint"]
    assert manifest["controls"]["audit"]
    assert {row["key"] for row in manifest["methods"]} >= {
        "blind_first_run", "source_shadow", "one_variable_ablation",
        "repeated_trials",
    }
    assert {row["key"] for row in manifest["axes"]} >= {
        "scope", "entry_channel", "context_count", "cap_overflow", "truncation",
        "issue_state", "retrieval_state", "basis_state",
    }


def test_review_manifest_measures_direction_basis_retrieval_and_stray(tmp_path):
    source = tmp_path / "review.json"
    source.write_text("{}", encoding="utf-8")
    rows = [
        {"case_no": "a", "label": "A", "mode": "A", "material": "전부",
         "text_kind": "질의요지", "direction": "긍정", "want_arts": 2,
         "got_arts": 2, "basis_hit": 2, "basis_n": 2, "basis_stray": 0,
         "want_arts_list": ["법 제1조", "법 제2조"], "issues": 1,
         "norms": 3, "sec": 1.2},
        {"case_no": "b", "label": "B", "mode": "B", "material": "전부",
         "text_kind": "구어", "direction": "조건부", "want_arts": 2,
         "got_arts": 1, "basis_hit": 1, "basis_n": 2, "basis_stray": 1,
         "want_arts_list": ["법 제3조", "법 제4조"], "issues": 0,
         "norms": 6, "sec": 2.4},
    ]

    manifest = evaluation.build_review_manifest(
        source_path=source, source_rows=rows,
        labels={"a": "긍정", "b": "부정"}, run_label="review")
    metrics = manifest["summary"]["metrics"]

    assert metrics["direction_accuracy"] == 0.5
    assert metrics["direction_basis_rate"] == 0.5
    assert metrics["article_recall"] == 0.75
    assert metrics["basis_recall"] == 0.75
    assert metrics["basis_stray_rate"] == 0.25
    assert metrics["abstain_rate"] == 0.5
    assert metrics["issue_fire_rate"] == 0.5
    assert metrics["semantic_cases"] == 0
    assert manifest["suite"]["axis_order"] == [
        "mode", "material", "text_kind", "direction_gold"]
    issue_slices = {row["value"]: row for row in manifest["summary"]["operational_axes"]
                    if row["axis"] == "issue_state"}
    assert issue_slices["fired"]["direction_accuracy"] == 1.0
    assert issue_slices["empty"]["direction_accuracy"] == 0.0


def test_direct_e2e_manifest_preserves_semantic_and_channel_coverage(tmp_path):
    source = tmp_path / "ask.raw.json"
    source.write_text("{}", encoding="utf-8")
    rows = [{
        "case_no": "a", "direction": "긍정", "m_gold": "긍정",
        "m_n": 1, "m_ret": 1, "m_basis": 1, "basis_n": 1,
        "want_arts_list": ["d node=1"], "semantic_correct": True,
        "semantic_reason": "기대 명제를 지지함",
        "norms": 1,
        "runtime": {"channel_counts": {"concept": 1, "vector": 4}},
    }]
    manifest = evaluation.build_review_manifest(
        source_path=source, source_rows=rows, labels={},
        source_flow="ask", source_suite={"name": "ask-e2e", "flows": {"ask": {
            "required_channels": ["concept", "memory", "vector"],
            "required_stages": ["retrieval", "answer_synthesis"]}}})
    metrics = manifest["summary"]["metrics"]

    assert metrics["semantic_accuracy"] == 1.0
    assert metrics["semantic_basis_rate"] == 1.0
    assert metrics["direction_accuracy"] == 0.0
    assert metrics["pass_rate"] == 1.0
    assert metrics["required_channel_coverage"] == round(2 / 3, 6)
    assert metrics["required_stage_coverage"] == 0.5
    assert manifest["summary"]["channel_coverage"]["missing"] == ["memory"]
    assert manifest["summary"]["stage_coverage"]["missing"] == ["answer_synthesis"]
    assert manifest["run"]["mode"] == "ask"
    assert manifest["results"][0]["semantic_reason"] == "기대 명제를 지지함"


def test_review_suite_hash_changes_when_question_mode_changes(tmp_path):
    source = tmp_path / "review.json"
    source.write_text("{}", encoding="utf-8")
    row = {"case_no": "a", "direction": "긍정", "want_arts": 1,
           "got_arts": 1, "basis_hit": 1, "basis_n": 1,
           "want_arts_list": ["법 제1조"], "mode": "A"}
    base = evaluation.build_review_manifest(
        source_path=source, source_rows=[row], labels={"a": "긍정"})
    changed = evaluation.build_review_manifest(
        source_path=source, source_rows=[{**row, "mode": "B"}],
        labels={"a": "긍정"})

    assert evaluation.compare_manifests(base, changed)["verdict"] == "invalid"


def test_one_variable_ablation_gate_uses_engine_switch_snapshot(tmp_path, monkeypatch):
    import json
    from lawrag.core.rag import switches

    engine = tmp_path / "engine.json"
    engine.write_text('{"switches": {}}', encoding="utf-8")
    monkeypatch.setenv("RAG_ENGINE_RULES", str(engine))
    switches._cache["mtime"] = None
    suite = tmp_path / "suite.yaml"
    suite.write_text("name: mini\naxis_order: [outcome]\n", encoding="utf-8")
    case = _case("p", True, (("d", "1"),))
    row = _row(case, (("d", "1"),))
    base = evaluation.build_manifest(
        suite_path=suite, suite={"name": "mini", "axis_order": ["outcome"]},
        rows=[row], mode="deterministic", run_label="base")

    engine.write_text(json.dumps({"switches": {"doc_companion": False}}),
                      encoding="utf-8")
    switches._cache["mtime"] = None
    candidate = evaluation.build_manifest(
        suite_path=suite, suite={"name": "mini", "axis_order": ["outcome"]},
        rows=[row], mode="deterministic", run_label="without-doc-companion")
    report = evaluation.compare_manifests(base, candidate, require_one_change=True)

    assert report["compatible"] is True
    assert report["configuration_diff"] == [{
        "kind": "switch", "key": "doc_companion", "before": True, "after": False}]

    engine.write_text(json.dumps({"switches": {
        "doc_companion": False, "keyword_entry": False}}), encoding="utf-8")
    switches._cache["mtime"] = None
    two_changes = evaluation.build_manifest(
        suite_path=suite, suite={"name": "mini", "axis_order": ["outcome"]},
        rows=[row], mode="deterministic")
    invalid = evaluation.compare_manifests(base, two_changes,
                                           require_one_change=True)
    assert invalid["verdict"] == "invalid"
    assert invalid["incompatible"] == ["one_variable_configuration"]


def test_query_guide_variant_is_a_first_class_one_variable_change(tmp_path):
    source = tmp_path / "ask.raw.json"
    source.write_text("{}", encoding="utf-8")
    row = {"case_no": "a", "direction": "긍정", "m_n": 1, "m_ret": 1,
           "m_basis": 1, "basis_n": 1, "semantic_correct": True,
           "runtime": {"final_contexts": 1}}
    base = evaluation.build_review_manifest(
        source_path=source, source_rows=[row], labels={}, source_flow="ask",
        source_suite={"name": "same"}, source_variant={"query_guide": "0"})
    candidate = evaluation.build_review_manifest(
        source_path=source, source_rows=[row], labels={}, source_flow="ask",
        source_suite={"name": "same"}, source_variant={"query_guide": "1"})

    report = evaluation.compare_manifests(base, candidate, require_one_change=True)

    assert report["compatible"] is True
    assert report["configuration_diff"] == [{
        "kind": "variant", "key": "query_guide", "before": "0", "after": "1",
    }]


def test_search_benchmark_comparison_uses_positive_coordinates_and_costs():
    def report(guide, *, calls, p95, contexts=12):
        return {
            "schema_version": 1, "kind": "rag_search_benchmark",
            "variant": {"query_guide": guide},
            "controls": {"fingerprint": "same"},
            "summary": {
                "cases": 1, "positive_case_source_recall": 1.0,
                "positive_coordinate_recall": 1.0,
                "structured_entry_coordinate_recall": 1.0,
                "positive_expected_share_of_context": 0.25,
                "legacy_negative_structured_lock_rate": 0.0,
                "final_contexts": {"mean": contexts},
                "latency_ms": {"p50": p95 / 2, "p95": p95, "max": p95},
                "usage": {"calls": calls, "input_tokens": 100,
                          "output_tokens": 10, "duration_ms": p95, "errors": 0},
            },
            "rows": [{
                "id": "p", "question": "q", "expect_hit": True,
                "expected_sources": [["d", "1"]],
                "final_sources": [["d", "1"]],
                "query_guide": {"enabled": guide == "1", "selected_ids": ["QG1"]},
            }],
        }

    compared = evaluation.compare_search_benchmarks(
        report("0", calls=2, p95=1000),
        report("1", calls=1, p95=800, contexts=10),
        require_one_change=True)

    assert compared["verdict"] == "mixed_more_efficient"
    assert compared["compatible"] is True
    assert compared["quality_regression_cases"] == []
    assert compared["deltas"]["calls_per_case"] == -1.0
    assert compared["deltas"]["latency_ms_p95"] == -200.0
    assert compared["guide"]["selected_cases"] == 1
