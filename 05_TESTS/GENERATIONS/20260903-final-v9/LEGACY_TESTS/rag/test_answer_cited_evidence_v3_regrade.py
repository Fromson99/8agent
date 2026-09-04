from scripts import rag_answer_cited_evidence_v3_regrade as subject


def test_empty_projection_is_not_rewarded():
    gold = {"external": []}
    result = subject._metrics(set(), gold, {"doc:1": "MAIN"})

    assert result["precision"] == 0.0
    assert result["corpus_recall"] == 0.0
    assert result["f2"] == 0.0
    assert result["corpus_complete"] is False


def test_surface_projection_requires_explicit_law_and_article():
    sections = [{
        "doc": "테스트법",
        "doc_id": "doc",
        "node": 1,
        "path": "제1장 ▸ 제3조 기준",
    }]

    selected, unresolved = subject._surface_selected("테스트법 제3조에 따른다.", sections)
    assert selected == {"doc:1"}
    assert unresolved == []

    selected, unresolved = subject._surface_selected("제3조에 따른다.", sections)
    assert selected == set()
    assert unresolved == ["제3조"]


def test_completed_run_uses_fixed_denominators_and_no_calls():
    run = subject._read(subject.RUN_PATH)

    assert run["frozen_criteria"]["fixed_denominators"] == {
        "cases": 61,
        "corpus_resolvable": 116,
        "full": 119,
    }
    assert run["provider_calls"] == 0
    assert run["judge_calls"] == 0
    assert run["llm_calls"] == []
    assert len(run["rows"]) == 61


def test_declared_use_reduces_evidence_but_fails_recall_gate():
    run = subject._read(subject.RUN_PATH)
    summary = run["summaries"]["baseline"]
    criteria = run["frozen_criteria"]["by_source_arm"]["baseline"]

    assert summary["baseline"]["selected_total"] == 1708
    assert summary["answer-declared-used-v3"]["selected_total"] == 139
    assert criteria["selected_reduction_at_least_50pct"] is True
    assert criteria["recall_retention_at_least_90pct"] is False
    assert criteria["main_recall_drop_at_most_5pp"] is False
    assert criteria["all_primary_checks_met"] is False
