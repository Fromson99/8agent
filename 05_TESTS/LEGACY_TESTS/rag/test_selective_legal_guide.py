from lawrag.core.rag import selective_legal_guide as guide


def sections():
    return [
        {
            "doc": "규정", "doc_id": "d1", "node": 1,
            "path": "제1조", "page": 1,
            "text": "기본 요건을 정한다.",
            "edges": [],
        },
        {
            "doc": "세칙", "doc_id": "d2", "node": 2,
            "path": "제2조", "page": 2,
            "text": "구체적인 예외 요건을 정한다.",
            "edges": [],
        },
    ]


def packet():
    return {
        "issues": [{"issue_id": "I1", "question_span": "예외 요건"}],
        "units": [
            {
                "evidence_id": "R1", "issue_ids": ["I1"],
                "role": "GOVERNING_RULE", "quote": "기본 요건을 정한다.",
            },
            {
                "evidence_id": "R2", "issue_ids": [],
                "role": "CONTEXT", "quote": "구체적인 예외 요건을 정한다.",
            },
            {
                "evidence_id": "R2", "issue_ids": ["I1"],
                "role": "EXCEPTION", "quote": "원문에 없는 문장",
            },
        ],
    }


def test_guide_keeps_only_exact_non_context_soft_units():
    value = guide.build_guide(
        "예외 요건은 무엇인가", sections(), packet(), {"R1": "E01", "R2": "E02"},
    )
    assert value["issues"] == [{"issue_id": "I1", "question_span": "예외 요건"}]
    assert value["units"] == [{
        "evidence_id": "E01", "issue_ids": ["I1"],
        "role": "GOVERNING_RULE", "quote": "기본 요건을 정한다.",
    }]
    assert value["unresolved_issues"] == []
    assert value["non_binding"] is True


def test_request_preserves_all_raw_sections_and_closed_ids():
    value = guide.build_request(
        "예외 요건은 무엇인가", sections(), packet(), {"R1": "E01", "R2": "E02"},
    )
    assert value["evidence_count"] == 2
    assert list(value["evidence_id_map"]) == ["E01", "E02"]
    assert "[선별 법률 가이드]" in value["user"]
    assert "구체적인 예외 요건을 정한다." in value["user"]


def test_output_keeps_valid_id_but_reports_non_exact_trace():
    output = {
        "answer": "답", "answerable": True,
        "selections": [{
            "evidence_id": "E01", "question_span": "없는 질문",
            "legal_role": "GOVERNING_RULE", "supporting_quote": "없는 인용",
            "why_needed": "필요", "dependency_ids": ["E02", "E99"],
        }],
        "rejected_near_matches": [{"evidence_id": "E02", "reason": "근접"}],
    }
    result = guide.validate_output(output, "예외 요건은 무엇인가", guide.raw.evidence_rows(sections()))
    assert result["evidence_ids"] == ["E01"]
    assert result["invalid_evidence_ids"] == ["E99"]
    assert result["question_span_violations"] == 1
    assert result["quote_violations"] == 1
    assert result["dependency_violations"] == 1
    assert result["valid"] is False


def test_answerable_requires_selection():
    output = {
        "answer": "답", "answerable": True,
        "selections": [], "rejected_near_matches": [],
    }
    result = guide.validate_output(output, "질문", guide.raw.evidence_rows(sections()))
    assert result["valid"] is False
    assert "without evidence" in result["error"]
