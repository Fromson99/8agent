import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "docs/adr/ADR-0128-legal-evidence-confusion-objective/artifacts/run-001.json"


def test_run_has_fixed_denominators_and_no_calls() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    assert run["fixed_denominators"] == {
        "cases": 61,
        "core": 51,
        "hard": 10,
        "corpus_gold": 116,
        "full_gold": 119,
        "corpus_size": 16506,
    }
    assert run["provider_calls"] == 0
    assert run["judge_calls"] == 0
    assert all(run["synthetic_checks"].values())


def test_best_rank_is_tied_but_no_source_is_eligible() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    ranking = run["rankings"]["difficulty_balanced_legal"]
    scores = [run["sources"][ref]["summary"]["difficulty_balanced_score"] for ref in ranking]
    assert scores[:3] == [52.63897, 52.63897, 52.63897]
    assert all(not run["sources"][ref]["summary"]["eligibility"]["eligible"] for ref in ranking)


def test_invalid_lineage_is_excluded_instead_of_silently_scored() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    source = run["sources"]["ADR-0120-experiment-v1/proposition-assessment-shadow-v1"]
    assert source["status"] == "invalid_evidence_lineage"
    assert source["summary"] is None
    assert len(source["lineage_errors"]) == 23
    assert "ADR-0120-experiment-v1/proposition-assessment-shadow-v1" not in run["rankings"]["difficulty_balanced_legal"]

