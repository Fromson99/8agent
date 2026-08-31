from types import SimpleNamespace

from lawrag.core.domain_graph import grounding


def test_exact_surface_keeps_source_offsets():
    source = "금융위원회는 자료의 제출을 요구할 수 있다."
    result = grounding.grade_surface("금융위원회", source, role="ACTOR")

    assert result.grade == "G3"
    assert result.method == "exact"
    assert result.spans[0].text == "금융위원회"
    assert source[result.spans[0].start:result.spans[0].end] == "금융위원회"


def test_spacing_and_punctuation_only_difference_is_normalized():
    result = grounding.grade_surface(
        "자료의 제출", "자료의·제출을 요구할 수 있다.", role="OBJECT")

    assert result.grade == "G2"
    assert result.method == "normalized"
    assert result.spans


def test_action_may_skip_parenthetical_insertion():
    source = "자료를 제공(공유를 포함한다. 이하 같다)할 수 있다."
    result = grounding.grade_surface(
        "자료를 제공할 수 있다", source, role="PREDICATE")

    assert result.grade == "G1"
    assert result.method == "parenthetical_gap"
    assert len(result.spans) >= 2


def test_noun_role_cannot_join_across_parenthetical_insertion():
    source = "금융(관계 기관을 포함한다)위원회는 요구할 수 있다."
    result = grounding.grade_surface("금융위원회", source, role="ACTOR")

    assert result.grade == "G0"


def test_enumerated_object_is_multiple_ordered_source_spans():
    source = ("다음 각 호의 사항은 이사회가 결정한다. "
              "1. 처분할 주식의 종류와 수 2. 처분가액과 납입기일 "
              "3. 처분할 상대방 및 처분방법")
    value = ("처분할 주식의 종류와 수, 처분가액과 납입기일, "
             "처분할 상대방 및 처분방법")
    result = grounding.grade_surface(value, source, role="OBJECT")

    assert result.grade == "G1"
    assert result.method == "enumeration_spans"
    assert len(result.spans) >= 3


def test_assertion_uses_evidence_surface_not_canonical_label():
    assertion = SimpleNamespace(source={
        "candidate_basis": {"raw_slots": {
            "HAS_ACTOR": "국세청장",
            "HAS_ACTION": "제공하여야",
            "HAS_OBJECT": "과세정보",
        }}
    })
    matches = grounding.grade_assertion(
        assertion, "국세청장은 과세정보를 제공하여야 한다.")

    assert set(matches) == {"ACTOR", "PREDICATE", "OBJECT"}
    assert grounding.eligible(matches, "grounded")


def test_condition_preserving_profile_rejects_one_ungrounded_slot():
    assertion = SimpleNamespace(source={
        "candidate_basis": {"raw_slots": {
            "HAS_ACTOR": "금융감독원",
            "HAS_ACTION": "요구할 수 있다",
            "HAS_OBJECT": "자료의 제출",
        }}
    })
    matches = grounding.grade_assertion(
        assertion, "금융위원회는 자료의 제출을 요구할 수 있다.")

    assert matches["ACTOR"].grade == "G0"
    assert not grounding.eligible(matches, "grounded")
    assert grounding.eligible(matches, "predicate_pair")


def test_same_document_wrong_source_is_not_local_grounding():
    nodes = [(1, "금융위원회는 요구할 수 있다."),
             (2, "금융감독원은 검사할 수 있다.")]

    assert grounding.found_in_other_node("금융감독원", nodes, exclude_node=1)
    assert not grounding.found_in_other_node("금융위원회", nodes, exclude_node=1)
