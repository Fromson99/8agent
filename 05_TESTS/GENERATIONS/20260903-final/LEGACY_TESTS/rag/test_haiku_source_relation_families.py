from lawrag.core.rag.experiments import haiku_source_relation_families as families


class FakeLLM:
    def __init__(self):
        self.calls = []

    def structured(self, label, system, user, schema, **kwargs):
        self.calls.append({"label": label, "system": system, "user": user,
                           "schema": schema, **kwargs})
        return {"relations": [], "unresolved": []}


def _evidence():
    return [{
        "id": "E1", "document": "코스닥시장 상장규정", "path": "제1조 목적",
        "original_text": "제1조 목적\n코스닥시장의 질서를 유지한다.",
        "document_revision": "20260101", "document_enforcement": "20260101",
        "document_current": True,
    }]


def test_families_cover_each_relation_exactly_once():
    flattened = [relation for values in families.RELATION_FAMILIES.values()
                 for relation in values]
    assert len(flattened) == len(set(flattened)) == 6


def test_family_schema_closes_relation_type_enum():
    schema = families.family_schema("normative_link")
    enum = schema["properties"]["relations"]["items"]["properties"][
        "relation_type"]["enum"]
    assert enum == ["EXCEPTION_TO", "IMPLEMENTS"]


def test_family_compiler_uses_only_haiku_and_no_case_question_fields():
    llm = FakeLLM()
    result = families.compile_source_relation_families(llm, _evidence())
    assert len(llm.calls) == 3
    assert all(call["model"] == "claude-haiku-4-5-20251001"
               for call in llm.calls)
    assert all(call["max_tokens"] == 6000 for call in llm.calls)
    assert all("case_id" not in call["user"] and "question" not in call["user"]
               and "gold" not in call["user"] and "reference" not in call["user"]
               for call in llm.calls)
    assert not result["published"] and not result["rejected"]


def test_unknown_family_is_rejected_before_llm_call():
    try:
        families.family_schema("unknown")
    except ValueError as exc:
        assert "unknown relation family" in str(exc)
    else:
        raise AssertionError("unknown family accepted")
