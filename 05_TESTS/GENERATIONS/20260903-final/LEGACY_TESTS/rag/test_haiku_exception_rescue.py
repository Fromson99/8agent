from lawrag.core.rag.experiments import haiku_exception_rescue as rescue


class FakeLLM:
    def __init__(self):
        self.calls = []

    def structured(self, label, system, user, schema, **kwargs):
        self.calls.append({"label": label, "system": system, "user": user,
                           "schema": schema, **kwargs})
        return {"relations": [], "unresolved": []}


def _inventory():
    return [
        {"evidence_id": "E1", "document": "A법", "path": "제1조 원칙",
         "document_revision": "", "document_enforcement": "",
         "document_current": True},
        {"evidence_id": "E2", "document": "A법", "path": "제2조 예외",
         "document_revision": "", "document_enforcement": "",
         "document_current": True},
    ]


def _candidate(quote_ids):
    return {"relations": [{
        "relation_id": "R1", "relation_type": "EXCEPTION_TO",
        "source_id": "E2", "target_id": "E1", "target_value": "제1조 원칙",
        "defined_term": "", "quote_ids": quote_ids,
        "evidence_statement": "제1조 적용 예외", "confidence": "high",
    }], "unresolved": []}


def test_schema_allows_only_exception_to():
    enum = rescue.exception_schema()["properties"]["relations"]["items"][
        "properties"]["relation_type"]["enum"]
    assert enum == ["EXCEPTION_TO"]


def test_target_and_exception_must_cooccur_in_same_quote():
    cards = [
        {"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
         "text": "제1조를 참조한다."},
        {"quote_id": "E2:L2", "evidence_id": "E2", "kind": "source",
         "text": "다만 별도 절차를 따른다."},
    ]
    result = rescue.validate_exception_rescue(
        _candidate(["E2:L1", "E2:L2"]), _inventory(), cards)
    assert result["published_count"] == 0
    assert "target_and_exception_not_in_same_quote" in (
        result["rejected"][0]["validation_errors"])


def test_explicit_same_quote_exception_is_published():
    cards = [{"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
              "text": "제1조에도 불구하고 이 경우에는 적용하지 아니한다."}]
    result = rescue.validate_exception_rescue(
        _candidate(["E2:L1"]), _inventory(), cards)
    assert result["published_count"] == 1


def test_compiler_uses_haiku_without_question_or_case_fields():
    llm = FakeLLM()
    evidence = [
        {"id": "E1", "document": "A법", "path": "제1조",
         "original_text": "제1조 목적\n목적을 정한다."},
        {"id": "E2", "document": "A법", "path": "제2조",
         "original_text": "제2조 예외\n제1조에도 불구하고 적용하지 아니한다."},
    ]
    rescue.compile_exception_rescue(llm, evidence)
    call = llm.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["max_tokens"] == 2500
    assert all(value not in call["user"]
               for value in ("case_id", "question", "gold", "reference"))


def test_candidate_menu_requires_article_and_signal_in_same_quote():
    inventory = _inventory()
    cards = [
        {"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
         "text": "제1조를 참조한다."},
        {"quote_id": "E2:L2", "evidence_id": "E2", "kind": "source",
         "text": "다만 별도 절차를 따른다."},
        {"quote_id": "E2:L3", "evidence_id": "E2", "kind": "source",
         "text": "제1조에도 불구하고 적용하지 아니한다."},
    ]
    candidates = rescue.build_exception_candidates(inventory, cards)
    assert len(candidates) == 1
    assert candidates[0]["quote_id"] == "E2:L3"


def test_weak_citation_plus_unrelated_daman_is_not_candidate():
    cards = [{"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
              "text": "제1조에 따라 신고한다. 다만 소규모 회사는 제외한다."}]
    assert rescue.build_exception_candidates(_inventory(), cards) == []


def test_closed_menu_canonicalizes_redundant_target_value():
    cards = [{"quote_id": "E2:L1", "evidence_id": "E2", "kind": "source",
              "text": "제1조에도 불구하고 적용하지 아니한다."}]
    candidate = _candidate(["E2:L1"])
    candidate["relations"][0]["target_value"] = ""
    result = rescue.validate_exception_rescue(
        candidate, _inventory(), cards,
        rescue.build_exception_candidates(_inventory(), cards))
    assert result["published_count"] == 1
    assert result["published"][0]["target_value"] == "제1조 원칙"
