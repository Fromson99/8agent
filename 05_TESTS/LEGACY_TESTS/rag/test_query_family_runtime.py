from __future__ import annotations

from lawrag.core.legal_graph import stable_id, validate_row
from lawrag.core.rag.query_family_runtime import (
    AnswerStatus,
    ExpansionResult,
    FamilyHypothesis,
    FeedbackCorrection,
    FeedbackFamilyMiner,
    QueryFamilyDefinition,
    QueryFamilyRegistry,
    QueryFamilyRuntime,
    SearchCandidate,
    UNKNOWN_FAMILY,
    diagnose_feedback,
    extract_query_frame,
)


AUTHORITY = "a" * 64


def _candidate(name: str, *supports: str, origin: str = "test") -> SearchCandidate:
    unit_id = stable_id("unit", name)
    return SearchCandidate(
        member_id=unit_id,
        endpoint={
            "kind": "STRUCTURAL_UNIT",
            "precision": "EXACT_UNIT",
            "ref_id": unit_id,
            "selector": {
                "document_id": "doc-test",
                "node_id": len(name),
                "coordinate": f"제{len(name)}조",
            },
        },
        origin=origin,
        supports=tuple(supports),
    )


class _Adapter:
    def __init__(self, *, universal=(), family=(), closure=(), fallback=()) -> None:
        self.universal = tuple(universal)
        self.family = tuple(family)
        self.closure = tuple(closure)
        self.fallback = tuple(fallback)
        self.calls: list[str] = []

    def universal_search(self, frame):
        self.calls.append("universal")
        return self.universal

    def family_search(self, frame, hypothesis, incumbent):
        self.calls.append(f"family:{hypothesis.family_id}")
        return self.family

    def expand_closure(self, frame, predicates, incumbent, family_ids):
        self.calls.append("closure")
        return ExpansionResult(candidates=self.closure)

    def fallback_search(self, frame, routes, missing_coverage, incumbent):
        self.calls.append("fallback")
        return self.fallback


def test_registry_is_multilabel_and_always_keeps_unknown() -> None:
    frame = extract_query_frame(
        "3개월 보유기간이 예외적으로 6개월로 연장되는 경우는?",
        authority_generation=AUTHORITY,
    )
    hypotheses = QueryFamilyRuntime().registry.classify(frame)
    family_ids = {item.family_id for item in hypotheses}
    assert {"TEMPORAL", "EXCEPTION", UNKNOWN_FAMILY} <= family_ids


def test_new_family_can_be_registered_from_data_without_router_code_change() -> None:
    registry = QueryFamilyRegistry()
    registry.register(QueryFamilyDefinition.from_dict({
        "family_id": "ROUNDING_METHOD",
        "version": 1,
        "axes": ["COMPUTATION", "ROUNDING"],
        "trigger_phrases": ["반올림", "절사"],
        "required_coverage": ["rounding_rule"],
        "closure_predicates": ["COMPUTES_VALUE", "REFERENCES"],
    }))
    frame = extract_query_frame(
        "법정 산식의 소수점은 반올림하나요?",
        authority_generation=AUTHORITY,
    )
    hypotheses = registry.classify(frame)
    assert hypotheses[0].family_id == "ROUNDING_METHOD"
    assert hypotheses[-1].family_id == UNKNOWN_FAMILY


def test_unknown_family_still_runs_universal_retrieval_and_can_answer() -> None:
    governing = _candidate("governing", "governing_rule")
    adapter = _Adapter(universal=(governing,))
    result = QueryFamilyRuntime(registry=QueryFamilyRegistry()).run(
        "새롭고 등록되지 않은 법률 질문 유형",
        adapter,
        authority_generation=AUTHORITY,
    )
    assert adapter.calls[0] == "universal"
    assert result.hypotheses[0].family_id == UNKNOWN_FAMILY
    assert result.answer_status == AnswerStatus.SUPPORTED
    assert [item.member_id for item in result.candidates] == [governing.member_id]


def test_wrong_family_never_deletes_universal_floor_and_fallback_completes() -> None:
    registry = QueryFamilyRegistry((QueryFamilyDefinition.from_dict({
        "family_id": "FORMULA",
        "version": 1,
        "axes": ["COMPUTATION"],
        "trigger_phrases": ["계산"],
        "required_coverage": ["formula"],
        "closure_predicates": ["COMPUTES_VALUE"],
    }),))
    governing = _candidate("governing", "governing_rule", origin="universal")
    noisy = _candidate("noise", origin="wrong-family")
    formula = _candidate("formula", "formula", origin="fallback")
    adapter = _Adapter(
        universal=(governing,), family=(noisy,), fallback=(formula,),
    )
    result = QueryFamilyRuntime(registry=registry).run(
        "계산 기준을 알려줘",
        adapter,
        authority_generation=AUTHORITY,
    )
    assert adapter.calls == ["universal", "family:FORMULA", "closure", "fallback"]
    assert result.candidates[0].member_id == governing.member_id
    assert result.answer_status == AnswerStatus.SUPPORTED
    assert all(not event["discarded"] for event in result.trace_events[1:])


def test_runtime_rows_validate_against_legal_graph_v1() -> None:
    governing = _candidate("governing", "governing_rule")
    result = QueryFamilyRuntime(registry=QueryFamilyRegistry()).run(
        "등록되지 않은 유형",
        _Adapter(universal=(governing,)),
        generation_id="runtime-test",
        authority_generation=AUTHORITY,
    )
    for row in result.rows:
        validate_row(row)
    assert {row["row_type"] for row in result.rows} >= {
        "query_frame", "landing", "decision_bundle", "retrieval_trace",
    }


def test_feedback_is_observation_and_repeated_unknown_gaps_make_shadow_proposal() -> None:
    result = QueryFamilyRuntime(registry=QueryFamilyRegistry()).run(
        "전혀 새로운 쟁점 유형 A",
        _Adapter(),
        authority_generation=AUTHORITY,
    )
    first = diagnose_feedback(
        result,
        FeedbackCorrection(expected_coordinates=("어떤 법 제1조",), note="정답 조문 누락"),
        authority_generation=AUTHORITY,
    )
    # A second correction with the same frame shape clusters with the first.
    second_result = QueryFamilyRuntime(registry=QueryFamilyRegistry()).run(
        "전혀 새로운 쟁점 유형 B",
        _Adapter(),
        authority_generation=AUTHORITY,
    )
    second = diagnose_feedback(
        second_result,
        FeedbackCorrection(expected_coordinates=("다른 법 제2조",), note="정답 조문 누락"),
        authority_generation=AUTHORITY,
    )
    assert first.first_loss == "S1_QUERY_FAMILY_GAP"
    assert first.observation_row["layer"] == "observation"
    assert first.observation_row["terminal_disposition"] == "OBSERVED_NOT_PROMOTED"

    miner = FeedbackFamilyMiner()
    miner.add(first)
    miner.add(second)
    proposals = miner.proposals(min_examples=2)
    assert len(proposals) == 1
    assert proposals[0].status == "CANDIDATE"
    assert proposals[0].to_dict()["activation"] == "SHADOW_ONLY"
