from types import SimpleNamespace

import yaml

from scripts import concept_golden


def _spec():
    return yaml.safe_load(concept_golden.DEFAULT.read_text(encoding="utf-8"))


def _holdout_spec():
    path = concept_golden.ROOT / "data" / "bench" / "concept_holdout.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _blind_spec():
    path = concept_golden.ROOT / "data" / "bench" / "concept_blind.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_concept_golden_has_50_valid_axis_complete_cases():
    spec = _spec()

    assert concept_golden._validate_spec(spec) == []
    assert len(spec["cases"]) == 50
    assert sum(case["expect_hit"] for case in spec["cases"]) == 25
    assert sum(case.get("live_llm") is True for case in spec["cases"]) == 10


def test_concept_holdout_has_50_disjoint_balanced_cases():
    golden = _spec()
    holdout = _holdout_spec()

    assert concept_golden._validate_spec(holdout) == []
    assert len(holdout["cases"]) == 50
    assert sum(case["expect_hit"] for case in holdout["cases"]) == 25
    assert {case["question"] for case in golden["cases"]}.isdisjoint(
        case["question"] for case in holdout["cases"]
    )

    golden_sources = {
        source
        for case in golden["cases"] if case["expect_hit"]
        for source in concept_golden._expected_sources(case)
    }
    holdout_sources = {
        source
        for case in holdout["cases"] if case["expect_hit"]
        for source in concept_golden._expected_sources(case)
    }
    assert len(holdout_sources) == 25
    assert golden_sources.isdisjoint(holdout_sources)


def test_concept_blind_has_50_cases_disjoint_from_both_development_sets():
    specs = [_spec(), _holdout_spec(), _blind_spec()]
    blind = specs[-1]

    assert concept_golden._validate_spec(blind) == []
    assert len(blind["cases"]) == 50
    assert sum(case["expect_hit"] for case in blind["cases"]) == 25

    question_sets = [
        {case["question"] for case in spec["cases"]}
        for spec in specs
    ]
    assert question_sets[2].isdisjoint(question_sets[0])
    assert question_sets[2].isdisjoint(question_sets[1])

    source_sets = [
        {
            source
            for case in spec["cases"] if case["expect_hit"]
            for source in concept_golden._expected_sources(case)
        }
        for spec in specs
    ]
    assert len(source_sets[2]) == 25
    assert source_sets[2].isdisjoint(source_sets[0])
    assert source_sets[2].isdisjoint(source_sets[1])


def test_axis_rows_report_pass_and_entry_counts():
    spec = _spec()
    cases = spec["cases"][:2]
    results = {
        cases[0]["id"]: {"passed": True, "hit": True},
        cases[1]["id"]: {"passed": False, "hit": False},
    }

    rows = concept_golden._axis_rows(cases, results, spec["axis_order"])
    outcome = {(row["value"], row["passed"], row["hits"], row["total"])
               for row in rows if row["axis"] == "outcome"}
    assert outcome == {("positive", 1, 1, 2)}


def test_check_accepts_exact_multiple_source_set():
    case = {
        "expect_hit": True,
        "expect_sources": [
            {"doc_id": "d1", "node": 1},
            {"doc_id": "d1", "node": 2},
        ],
    }
    sections = [
        SimpleNamespace(doc_id="d1", node=2),
        SimpleNamespace(doc_id="d1", node=1),
    ]

    assert concept_golden._check(case, sections, {}) == []
