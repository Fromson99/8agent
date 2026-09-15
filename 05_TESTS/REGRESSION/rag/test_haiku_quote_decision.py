from lawrag.research.experiments import haiku_quote_decision as quote


CARDS = [
    {"quote_id": "E1:L1", "document": "법", "path": "제1조",
     "text": "회사는 각각 100분의 10에 해당하는 금액을 지급하여야 한다."},
    {"quote_id": "E1:L2", "document": "법", "path": "제1조",
     "text": "다만, 면제되는 경우에는 그러하지 아니하다."},
]


def _plan(ids=None):
    ids = ids or ["E1:L1"]
    return {
        "slots": [
            {"slot": "authority", "status": "supported", "quote_ids": ids},
            {"slot": "conclusion", "status": "supported", "quote_ids": ids},
            {"slot": "action_or_object", "status": "supported", "quote_ids": ids},
            {"slot": "quantity", "status": "supported", "quote_ids": ids},
        ],
        "conclusion": "APPLIES", "modality": "MUST",
        "quantifier_relation": "EACH", "decision_quote_ids": ids,
    }


def test_required_slots_are_question_driven():
    slots = quote.required_slots("회사가 각각 100분의 10을 내야 하는가?")
    assert {"authority", "conclusion", "actor", "action_or_object", "quantity"} \
        <= set(slots)
    assert "temporal" not in slots


def test_operator_ast_and_closed_values_preserve_legal_operators():
    ast = quote.operator_ast(CARDS)
    assert ast["E1:L1"]["modalities"] == ["MUST"]
    assert "EACH" in ast["E1:L1"]["quantifiers"]
    assert ast["E1:L2"]["exception"] is True
    assert any(row["canonical"] == "10%:EQ"
               for row in quote.closed_value_candidates("", CARDS))


def test_plan_guard_rejects_unknown_quote_and_missing_support():
    requested = ["authority", "conclusion", "action_or_object", "quantity"]
    assert quote.validate_plan(_plan(), CARDS, requested)["valid"]
    bad = _plan(["UNKNOWN"])
    assert not quote.validate_plan(bad, CARDS, requested)["valid"]


def test_disagreement_router_only_marks_changed_slots():
    requested = ["authority", "conclusion", "action_or_object", "quantity"]
    first, second = _plan(), _plan()
    assert not quote.disagreements(first, second, requested)["needs_tiebreak"]
    second["slots"][-1] = {"slot": "quantity", "status": "unsupported",
                            "quote_ids": []}
    assert quote.disagreements(first, second, requested)["slots"] == ["quantity"]


def test_minimal_cover_and_certificate():
    requested = ["authority", "conclusion", "action_or_object", "quantity"]
    cover = quote.minimal_quote_cover(_plan(), requested, CARDS)
    assert cover == ["E1:L1"]
    cert = quote.certificate(_plan(), requested, CARDS)
    assert cert["valid"]
    assert cert["available_modalities"] == ["MUST"]


def test_explicit_conflict_filter_is_narrow():
    assert quote.explicit_conflicts(CARDS, {"E1:L1", "E1:L2"}) == []
    conflict_cards = [
        {"quote_id": "A", "document": "법", "path": "제1조",
         "text": "회사는 정관에 따라 보유 주식을 양도하여야 한다."},
        {"quote_id": "B", "document": "법", "path": "제1조",
         "text": "회사는 정관에 따라 보유 주식을 양도할 수 없다."},
    ]
    assert quote.explicit_conflicts(conflict_cards, {"A", "B"})
