from lawrag.research.experiments import haiku_source_relations as relations
from scripts.rag_haiku_source_relations_eval import summarize


def _inventory():
    return [
        {"evidence_id": "E1", "document": "A법", "path": "제1조 원칙",
         "document_revision": "20260101", "document_enforcement": "20260101",
         "document_current": True},
        {"evidence_id": "E2", "document": "A법", "path": "제2조 예외",
         "document_revision": "20260101", "document_enforcement": "20260101",
         "document_current": True},
    ]


def _cards():
    return [
        {"quote_id": "E1:META", "evidence_id": "E1", "kind": "metadata",
         "text": "document=코스닥시장 상장규정 | path=제1조 원칙"},
        {"quote_id": "E1:L1", "evidence_id": "E1", "kind": "source",
         "text": "회사의 대표자는 제1조의 의무를 이행하여야 한다."},
        {"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
         "text": "제1조에도 불구하고 이 조의 경우에는 적용하지 아니한다."},
    ]


def _relation(relation_type, **values):
    return {
        "relation_id": "R1", "relation_type": relation_type,
        "source_id": values.get("source_id", "E1"),
        "target_id": values.get("target_id", ""),
        "target_value": values.get("target_value", ""),
        "defined_term": values.get("defined_term", ""),
        "quote_ids": values.get("quote_ids", ["E1:L1"]),
        "evidence_statement": "원문 증명", "confidence": "high",
    }


def test_actor_relation_requires_actor_in_source_quote():
    good = _relation("GOVERNS_ACTOR", target_value="회사의 대표자")
    bad = _relation("GOVERNS_ACTOR", target_value="감사위원회")
    assert relations.validate_relations(
        {"relations": [good]}, _inventory(), _cards())["published_count"] == 1
    result = relations.validate_relations(
        {"relations": [bad]}, _inventory(), _cards())
    assert result["rejected_count"] == 1
    assert "actor_not_in_source" in result["rejected"][0]["validation_errors"]


def test_exception_relation_requires_explicit_target_article_and_language():
    good = _relation(
        "EXCEPTION_TO", source_id="E2", target_id="E1",
        quote_ids=["E2:L1"])
    result = relations.validate_relations(
        {"relations": [good]}, _inventory(), _cards())
    assert result["published_count"] == 1
    bad_cards = [dict(row) for row in _cards()]
    bad_cards[-1]["text"] = "제2조는 별도 절차를 정한다."
    result = relations.validate_relations(
        {"relations": [good]}, _inventory(), bad_cards)
    assert result["rejected_count"] == 1


def test_current_version_requires_distinct_real_version_metadata():
    candidate = _relation(
        "CURRENT_VERSION_OF", source_id="E1", target_id="E2",
        quote_ids=["E1:META"])
    result = relations.validate_relations(
        {"relations": [candidate]}, _inventory(), _cards())
    assert result["rejected_count"] == 1
    assert "version_coordinate_mismatch" in result["rejected"][0]["validation_errors"]


def test_defined_by_requires_term_to_be_definition_subject():
    inventory = _inventory()
    cards = _cards() + [
        {"quote_id": "E2:L2", "evidence_id": "E2", "kind": "source",
         "text": '"회사"란 주식회사 중 주권상장법인을 포함하는 자를 말한다.'},
        {"quote_id": "E1:L2", "evidence_id": "E1", "kind": "source",
         "text": "주권상장법인은 신고하여야 한다."},
    ]
    false_relation = _relation(
        "DEFINED_BY", source_id="E1", target_id="E2",
        target_value="제2조 정의", defined_term="주권상장법인",
        quote_ids=["E1:L2", "E2:L2"])
    result = relations.validate_relations(
        {"relations": [false_relation]}, inventory, cards)
    assert result["rejected_count"] == 1
    assert "definition_language_missing" in result["rejected"][0]["validation_errors"]


def test_defined_by_accepts_explicit_term_definition():
    inventory = _inventory()
    cards = _cards() + [
        {"quote_id": "E2:L2", "evidence_id": "E2", "kind": "source",
         "text": '"주권상장법인"이란 법률에 따른 주권상장법인을 말한다.'},
        {"quote_id": "E1:L2", "evidence_id": "E1", "kind": "source",
         "text": "주권상장법인은 신고하여야 한다."},
    ]
    relation = _relation(
        "DEFINED_BY", source_id="E1", target_id="E2",
        target_value="제2조 정의", defined_term="주권상장법인",
        quote_ids=["E1:L2", "E2:L2"])
    result = relations.validate_relations(
        {"relations": [relation]}, inventory, cards)
    assert result["published_count"] == 1


def test_medium_confidence_candidate_is_not_published():
    candidate = _relation("GOVERNS_ACTOR", target_value="회사의 대표자")
    candidate["confidence"] = "medium"
    result = relations.validate_relations(
        {"relations": [candidate]}, _inventory(), _cards())
    assert result["rejected_count"] == 1
    assert "confidence_not_high" in result["rejected"][0]["validation_errors"]


def test_implements_requires_proven_document_lineage():
    inventory = _inventory()
    inventory[1]["document"] = "B법"
    candidate = _relation(
        "IMPLEMENTS", source_id="E2", target_id="E1",
        quote_ids=["E2:L1"])
    cards = _cards()
    cards[-1]["text"] = "제1조에서 세칙으로 정하는 사항을 정한다."
    result = relations.validate_relations(
        {"relations": [candidate]}, inventory, cards)
    assert result["rejected_count"] == 1
    assert "implementation_document_lineage_unproven" in (
        result["rejected"][0]["validation_errors"])


def test_published_relation_embeds_exact_proof_quote():
    candidate = _relation("GOVERNS_ACTOR", target_value="회사의 대표자")
    result = relations.validate_relations(
        {"relations": [candidate]}, _inventory(), _cards())
    assert result["published"][0]["proof_quotes"] == [{
        "quote_id": "E1:L1", "evidence_id": "E1", "kind": "source",
        "text": "회사의 대표자는 제1조의 의무를 이행하여야 한다.",
    }]


def test_defined_by_rejects_term_found_only_inside_compound_word():
    inventory = _inventory()
    cards = _cards() + [
        {"quote_id": "E1:L2", "evidence_id": "E1", "kind": "source",
         "text": "신규상장을 신청하여야 한다."},
        {"quote_id": "E2:L2", "evidence_id": "E2", "kind": "source",
         "text": '"상장"이란 거래 자격을 부여하는 것을 말한다.'},
    ]
    candidate = _relation(
        "DEFINED_BY", source_id="E1", target_id="E2",
        target_value="제2조 정의", defined_term="상장",
        quote_ids=["E1:L2", "E2:L2"])
    result = relations.validate_relations(
        {"relations": [candidate]}, inventory, cards)
    assert result["rejected_count"] == 1
    assert "defined_term_not_in_both_sources" in (
        result["rejected"][0]["validation_errors"])


def test_subset_summary_does_not_fail_absent_sentinel_case():
    summary = summarize([{
        "case_no": "cm-001", "model": relations.HAIKU_MODEL,
        "published": [], "rejected": [], "usage": {}, "wall_ms": 1,
    }])
    assert summary["sentinel_cases_present"] == []
    assert summary["criteria"]["cm036_internal_control_actor_created"] is True
    assert summary["all_pre_registered_criteria_pass"] is True


def test_compiler_fails_loudly_when_structured_output_is_missing():
    class Missing:
        def structured(self, *args, **kwargs):
            return None

    try:
        relations.compile_source_relations(Missing(), [])
    except RuntimeError as exc:
        assert "structured output missing" in str(exc)
    else:
        raise AssertionError("missing structured output must not become an empty relation set")


def test_relation_compiler_model_is_haiku():
    assert relations.HAIKU_MODEL == "claude-haiku-4-5-20251001"
