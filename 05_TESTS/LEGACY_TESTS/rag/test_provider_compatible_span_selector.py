from lawrag.core.rag import provider_compatible_span_selector as selector


def test_schema_keeps_enum_without_unsupported_array_keywords():
    schema = selector._schema(["S01", "S02"])
    selected = schema["properties"]["selected_span_ids"]

    assert selected["items"]["enum"] == ["S01", "S02"]
    assert "maxItems" not in selected
    assert "uniqueItems" not in selected


def test_server_validator_still_caps_and_deduplicates():
    row1 = object()
    row2 = object()
    by_id = {
        "S01": {"span_id": "S01", "coordinate": ["d", 1], "row": row1},
        "S02": {"span_id": "S02", "coordinate": ["d", 1], "row": row1},
        "S03": {"span_id": "S03", "coordinate": ["d", 2], "row": row2},
    }

    accepted, errors = selector.base._validate(
        ["S01", "S01", "S02", "S03"], by_id)

    assert errors == []
    assert [item["span_id"] for item in accepted] == ["S01", "S03"]
