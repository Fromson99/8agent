from lawrag.core.rag.experiments import haiku_pair_first_relations as pair_first


def _row(evidence_id, document, path, text, **metadata):
    return {"id": evidence_id, "document": document, "path": path,
            "original_text": text, **metadata}


def test_builds_implements_only_for_lower_norm_and_explicit_article():
    evidence = [
        _row("E1", "A법", "제8조 운영", "제8조(운영) 필요한 사항은 대통령령으로 정한다."),
        _row("E2", "A법 시행령", "제9조 운영", '법 제8조에서 "대통령령으로 정하는 사항"이란 다음을 말한다.'),
        _row("E3", "B법", "제8조 다른 규율", "제8조(다른 규율)"),
    ]
    built = pair_first.build_closed_pairs(evidence)
    pairs = [row for row in built["pairs"] if row["relation_type"] == "IMPLEMENTS"]
    assert [(row["source_id"], row["target_id"]) for row in pairs] == [("E2", "E1")]


def test_definition_pair_requires_exact_term_not_compound_substring():
    evidence = [
        _row("E1", "A법", "제1조 정의", '이 법에서 "상장"이란 거래소 등록을 말한다.'),
        _row("E2", "A법", "제2조", "상장은 신고하여야 한다."),
        _row("E3", "A법", "제3조", "신규상장은 심사한다."),
    ]
    pairs = [row for row in pair_first.build_closed_pairs(evidence)["pairs"]
             if row["relation_type"] == "DEFINED_BY"]
    assert [(row["source_id"], row["target_id"], row["defined_term"])
            for row in pairs] == [("E2", "E1", "상장")]


def test_local_definition_requires_its_explicit_parent_article_anchor():
    evidence = [
        _row("E1", "A규정", "제26조 의무", "세칙으로 정하는 경우에는 면제한다."),
        _row("E2", "A규정", "제27조 다른 의무", "세칙으로 정하는 경우에는 신고한다."),
        _row("E3", "A규정 시행세칙", "제23조 예외",
             '규정 제26조에서 "세칙으로 정하는 경우"란 다음을 말한다.'),
    ]
    pairs = [row for row in pair_first.build_closed_pairs(evidence)["pairs"]
             if row["relation_type"] == "DEFINED_BY"]
    assert [(row["source_id"], row["target_id"]) for row in pairs] == [("E1", "E3")]


def test_exception_surface_must_be_attached_to_the_target_article():
    evidence = [
        _row("E1", "A법", "제10조", "제20조의 대상인 회사는 제외한다."),
        _row("E2", "A법", "제20조", "대상 회사"),
        _row("E3", "A법", "제30조", "제20조는 이 조에 적용하지 아니한다."),
    ]
    pairs = [row for row in pair_first.build_closed_pairs(evidence)["pairs"]
             if row["relation_type"] == "EXCEPTION_TO"]
    assert [(row["source_id"], row["target_id"]) for row in pairs] == [("E3", "E2")]


def test_definition_does_not_treat_path_or_article_heading_as_term_use():
    evidence = [
        _row("E1", "A법", "제1조 정의", '"상장"이란 거래 자격을 말한다.'),
        _row("E2", "A법", "제2조 상장", "▸ 제1장 상장\n제2조(상장)"),
    ]
    pairs = [row for row in pair_first.build_closed_pairs(evidence)["pairs"]
             if row["relation_type"] == "DEFINED_BY"]
    assert pairs == []


def test_simple_reference_where_defined_is_not_implementation():
    evidence = [
        _row("E1", "A규정", "제27조", "경영권 변동"),
        _row("E2", "A규정 시행세칙", "제12조",
             "제27조에서 정하는 바에 따라 경영권이 변동되는 경우 신고한다."),
    ]
    pairs = [row for row in pair_first.build_closed_pairs(evidence)["pairs"]
             if row["relation_type"] == "IMPLEMENTS"]
    assert pairs == []


def test_version_pair_needs_current_to_noncurrent_and_distinct_metadata():
    evidence = [
        _row("E1", "A법", "제1조", "현행", document_revision="2024-01-01",
             document_enforcement="2024-02-01", document_current=True),
        _row("E2", "A법", "제1조", "구버전", document_revision="2020-01-01",
             document_enforcement="2020-02-01", document_current=False),
        _row("E3", "A법", "제2조", "구버전", document_revision="2020-01-01",
             document_enforcement="2020-02-01", document_current=False),
    ]
    pairs = pair_first.build_closed_pairs(evidence)["pairs"]
    versions = [row for row in pairs if row["relation_type"] == "CURRENT_VERSION_OF"]
    assert [(row["source_id"], row["target_id"]) for row in versions] == [("E1", "E2")]


def test_validation_fails_closed_on_omitted_or_partial_proof():
    pair_build = {"pairs": [{
        "pair_id": "P001", "relation_type": "DEFINED_BY",
        "source_id": "E2", "target_id": "E1", "defined_term": "상장",
        "deterministic_basis": "test",
        "proof_quotes": [
            {"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source", "text": "상장은"},
            {"quote_id": "E1:L1", "evidence_id": "E1", "kind": "source", "text": "상장이란"},
        ],
    }]}
    omitted = pair_first.validate_pair_decisions(pair_build, {"decisions": []})
    assert omitted["published_count"] == 0
    partial = pair_first.validate_pair_decisions(pair_build, {"decisions": [{
        "pair_id": "P001", "verdict": "RELATION", "quote_ids": ["E2:L1"],
        "reason": "부분 증거", "confidence": "high",
    }]})
    assert partial["published_count"] == 0
    assert "relation_did_not_use_all_mandatory_quotes" in partial["rejected"][0]["validation_errors"]


def test_model_and_pair_caps_are_fixed():
    assert pair_first.HAIKU_MODEL == "claude-haiku-4-5-20251001"
    assert pair_first.MAX_PAIRS_PER_RELATION == 24
    assert pair_first.MAX_PAIRS_PER_CASE == 64
    assert pair_first.MAX_PAIRS_PER_CALL == 24
