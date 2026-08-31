from lawrag.core.domain_graph import requirements


def test_extracts_condition_exception_time_quantity_method_and_effect_with_offsets():
    text = ("회사는 취득한 날부터 1년 이내에 주주총회의 승인을 받아 처분할 수 있다. "
            "다만, 대통령령으로 정하는 경우에는 그러하지 아니하다.")
    rows = requirements.extract(text)
    kinds = {row.kind for row in rows}

    assert {"CONDITION", "EXCEPTION", "TIME", "QUANTITY", "METHOD", "EFFECT"} <= kinds
    for row in rows:
        assert text[row.start:row.end] == row.surface
        assert text[row.trigger_start:row.trigger_end] == row.trigger


def test_does_not_generate_requirement_without_closed_cue():
    assert requirements.extract("회사는 자기주식을 보유한다.") == ()


def test_question_requested_kinds_are_closed_and_deterministic():
    kinds = requirements.requested_kinds(
        "몇 년 이내에 누구에게 어떤 방법으로 신고해야 하는가?")

    assert kinds == ("TIME", "QUANTITY", "METHOD")

