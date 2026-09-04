from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import rag_bounded_global_augmenting_basis_golden_61 as runner


def _coordinate(rank: int = 1) -> dict:
    return {
        "rank": rank,
        "doc_id": "doc",
        "node": rank,
        "doc": "법령",
        "path": f"제{rank}조",
        "origin": "test",
    }


def _parent_68_row() -> dict:
    coordinate = _coordinate()
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


def _gold(*, hit: bool = True) -> dict:
    return {
        "doc_id": "doc",
        "node": 1,
        "law": "법령",
        "article": "제1조",
        "corpus_status": "present",
        "scorable": True,
        "hit": hit,
        "rank": 1 if hit else None,
        "internal_pool_hit": True,
        "internal_pool_rank": 1,
    }


def test_frozen_source_hashes_match_the_declared_lineage():
    assert runner._sha(runner.FROZEN) == runner.FROZEN_SHA256
    assert runner._sha(runner.PARENT_68_RUN) == runner.PARENT_68_RUN_SHA256
    assert (runner._sha(runner.PARENT_73_MANIFEST)
            == runner.PARENT_73_MANIFEST_SHA256)
    assert runner._sha(runner.PARENT_73_RUN) == runner.PARENT_73_RUN_SHA256


def test_safe_projection_whitelists_only_pre_greedy_retrieval_state():
    value = runner.safe_projection(_parent_68_row())

    assert set(value) == {
        "number", "case_id", "suite", "question", "terms",
        "baseline_core", "incumbent", "evidence_pool", "cap", "pool_cap",
    }
    assert value["case_id"] == "case-1"
    assert value["incumbent"][0]["doc_id"] == "doc"
    assert runner._contains_banned_key(value) is False


def test_gold_canary_cannot_change_the_selector_projection():
    left = _parent_68_row()
    right = deepcopy(left)
    right["gold_results"] = [{"doc_id": "changed", "node": -1}]
    right["paired"] = {"changed": "yes"}
    right["arms"]["baseline"]["gold_results"] = [{"changed": True}]
    right["arms"]["recall-first-union"]["gold_results"] = [
        {"changed": True}]

    assert runner.safe_projection(left) == runner.safe_projection(right)
    assert runner._json_sha(runner.safe_projection(left)) == runner._json_sha(
        runner.safe_projection(right))


def test_bundle_preflight_counts_the_minimum_eviction_frontier():
    value = runner._bundle_preflight_counts(
        pool_count=23,
        incumbent_count=20,
        selected_floor_count=1,
    )

    assert value["nonincumbent_ground"] == 3
    assert value["evictable_upper_bound"] == 19
    assert value["by_additions"] == {
        "1": {"evictions": 1, "structural_bundle_upper_bound": 57},
        "2": {"evictions": 2, "structural_bundle_upper_bound": 513},
        "3": {"evictions": 3, "structural_bundle_upper_bound": 969},
    }
    assert value["structural_bundle_upper_bound"] == 1539


def test_validate_only_report_never_invokes_selector_or_grader(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("performance path entered validate-only")

    monkeypatch.setattr(runner.proof_basis_augmenting, "run", forbidden)
    monkeypatch.setattr(runner, "_grade", forbidden)
    monkeypatch.setattr(
        runner,
        "_preflight_projection",
        lambda _index, projection: {
            "case_id": projection["case_id"],
            "canonical_pool": 3,
            "canonical_incumbent": 2,
            "canonical_core": 1,
            "nonincumbent_ground": 1,
            "structural_bundle_upper_bound": 7,
        },
    )
    projections = [{"case_id": "a", "evidence_pool": [1, 2, 3]}]

    report = runner._validate_only_report(
        object(), projections, corpus=12019)

    assert report["cases"] == 1
    assert report["canonical_parent_pool_coordinates"] == 3
    assert report["structural_bundle_upper_bound_total"] == 7
    assert report["solver_calls"] == 0
    assert report["grader_calls"] == 0
    assert report["llm_calls"] == 0


def test_candidate_uses_bundle_four_and_receives_no_gold(monkeypatch):
    incumbent = [SimpleNamespace(coordinate=("doc", 1))]
    pool = [
        SimpleNamespace(coordinate=("doc", 1)),
        SimpleNamespace(coordinate=("doc", 2)),
    ]
    core = [SimpleNamespace(coordinate=("doc", 1))]

    def restore(_index, _values, _terms, *, origin):
        if origin == "ADR-0068-selected":
            return incumbent
        if origin == "ADR-0068-pool":
            return pool
        assert origin == "ADR-0068-baseline-core"
        return core

    captured = {}

    def select(index, question, got_incumbent, got_pool, got_core, **kwargs):
        captured.update({
            "index": index,
            "question": question,
            "incumbent": got_incumbent,
            "pool": got_pool,
            "core": got_core,
            "kwargs": kwargs,
        })
        return got_incumbent, {
            "status": "complete",
            "registry_errors": [],
            "gold_fields_received": False,
            "llm_calls": 0,
        }

    monkeypatch.setattr(runner, "_restore", restore)
    monkeypatch.setattr(runner.proof_basis_augmenting, "run", select)
    monkeypatch.setattr(
        runner.proof_basis_augmenting,
        "canonicalize",
        lambda _index, rows: (list(rows), []),
    )
    projection = {
        "number": 1,
        "case_id": "case-1",
        "suite": "suite",
        "question": "질문",
        "terms": ["용어"],
        "baseline_core": [_coordinate()],
        "incumbent": [_coordinate()],
        "evidence_pool": [_coordinate()],
        "cap": 20,
        "pool_cap": 96,
    }

    result = runner._select_candidate(object(), projection)

    assert captured["question"] == "질문"
    assert captured["incumbent"] is incumbent
    assert captured["pool"] is pool
    assert captured["core"] is core
    assert captured["kwargs"] == {"cap": 20, "bundle_max": 4}
    assert result["selected_rows"] is incumbent
    assert runner._contains_banned_key(projection) is False


def test_baseline_replay_regrades_but_preserves_parent_receipts(monkeypatch):
    gold = _gold()
    monkeypatch.setattr(
        runner,
        "_grade",
        lambda _case, _selected, _pool: ([gold], True, True),
    )
    parent = {
        "arm": "proof-basis-exchange",
        "selected": [_coordinate()],
        "selected_count": 1,
        "internal_pool": [_coordinate()],
        "internal_pool_count": 1,
        "gold_results": [gold],
        "case_all_gold_hit": True,
        "case_all_gold_internal_pool_hit": True,
        "retrieval_meta": {"actions": [{"reason": "parent-receipt"}]},
        "llm_calls": [],
        "provider_usage": {"calls": 0},
        "wall_ms": 12.5,
        "runtime_error": "",
    }

    value = runner._baseline_arm({"id": "case-1"}, parent)

    assert value["arm"] == "baseline"
    assert value["replay_of"] == (
        "ADR-0073/run-001/proof-basis-exchange")
    assert value["retrieval_meta"] == parent["retrieval_meta"]
    assert value["gold_results"] == [gold]


def test_question_record_has_exactly_the_eight_standard_headings():
    baseline = {
        "selected": [_coordinate()],
        "retrieval_meta": {"actions": []},
        "provider_usage": runner._zero_usage(),
        "wall_ms": 0.0,
        "gold_results": [_gold()],
        "case_all_gold_hit": True,
        "runtime_error": "",
    }
    candidate = {
        **deepcopy(baseline),
        "retrieval_meta": {
            "actions": [],
            "candidate_audit": {"admissible_candidate_ids": []},
        },
    }
    pair_key = f"baseline__{runner.ARMS[1]}"
    row = {
        "executed_at": "2026-08-27T00:00:00.000+00:00",
        "arms": {"baseline": baseline, runner.ARMS[1]: candidate},
        "paired": {
            pair_key: {
                "case_all_gold": "both",
                "selected_articles": [{"status": "both"}],
            },
        },
    }
    case = {
        "number": 1,
        "id": "case-1",
        "question": "실제 질문",
        "reference_answer": "채점 전용 답",
        "expected_articles": [{"doc_id": "doc", "node": 1}],
    }

    text = runner._question_markdown(
        case, row, {"case_id": "case-1"}, corpus=12019)
    headings = [line for line in text.splitlines() if line.startswith("## ")]

    assert headings == [
        "## 1. 실행 메타",
        "## 2. 사용자 질문 원문",
        "## 3. 기준답변 — 채점 전용, 제품 입력 비공개",
        "## 4. 제품 입력을 구성한 원값",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
        "## 7. 채점 호출과 반복 판정",
        "## 8. 사례 최종 판정",
    ]
    assert "TODO" not in text
    assert "실제 질문" in text
    assert "채점 전용 답" in text


def test_resume_requires_an_exact_frozen_prefix():
    projections = [{"case_id": "a"}, {"case_id": "b"}]
    blob = {
        "schema_version": (
            "bounded-global-augmenting-basis-golden-61-run-v1"),
        "adr_id": runner.ADR_ID,
        "run_id": runner.RUN_ID,
        "runner_sha256": runner._sha(runner.Path(runner.__file__).resolve()),
        "implementation_sha256": {
            str(path.relative_to(runner.ROOT)): runner._sha(path)
            for path in runner.IMPLEMENTATIONS
        },
        "source_lineage": {
            "frozen_sha256": runner.FROZEN_SHA256,
            "parent_68_run_sha256": runner.PARENT_68_RUN_SHA256,
            "parent_73_manifest_sha256": runner.PARENT_73_MANIFEST_SHA256,
            "parent_73_run_sha256": runner.PARENT_73_RUN_SHA256,
        },
        "rows": [{
            "case_id": "b",
            "input_state_sha256": runner._json_sha(projections[1]),
        }],
    }

    with pytest.raises(ValueError, match="exact frozen prefix"):
        runner._validate_resume(blob, projections)
