from __future__ import annotations

from lawrag.core.rag import raw_evidence_selection as raw


def _rows(count: int = 2):
    return [
        {
            "doc": f"문서 {number}",
            "doc_id": f"doc-{number}",
            "node": number,
            "path": f"제{number}조",
            "page": number,
            "text": f"제{number}조 원문",
            "legal_meta": {"legal_compilation": {"claims": ["금지"]}},
            "definition_context": [{"term": "금지"}],
            "kind": "검색 점수",
        }
        for number in range(1, count + 1)
    ]


def test_request_contains_only_raw_coordinate_and_text_fields():
    request = raw.build_request("질문", _rows())
    assert request["evidence_count"] == 2
    assert request["evidence_id_map"] == {
        "E01": {"doc_id": "doc-1", "node": 1},
        "E02": {"doc_id": "doc-2", "node": 2},
    }
    assert "legal_compilation" not in request["user"]
    assert "definition_context" not in request["user"]
    assert "검색 점수" not in request["user"]


def test_duplicate_coordinate_is_rejected():
    rows = _rows()
    rows[1]["doc_id"] = rows[0]["doc_id"]
    rows[1]["node"] = rows[0]["node"]
    try:
        raw.build_request("질문", rows)
    except ValueError as exc:
        assert "duplicate evidence coordinate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("duplicate coordinate was accepted")


def test_output_is_closed_to_presented_ids():
    mapping = raw.build_request("질문", _rows())["evidence_id_map"]
    result = raw.validate_output(
        {"answer": "답", "answerable": True, "evidence_ids": ["E02", "E99"]},
        mapping,
    )
    assert result["evidence_ids"] == ["E02"]
    assert result["invalid_evidence_ids"] == ["E99"]
    assert result["valid"] is False


def test_answerable_requires_at_least_one_evidence_id():
    mapping = raw.build_request("질문", _rows())["evidence_id_map"]
    result = raw.validate_output(
        {"answer": "답", "answerable": True, "evidence_ids": []}, mapping,
    )
    assert result["valid"] is False
    assert "without evidence" in result["error"]
