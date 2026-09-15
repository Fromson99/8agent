from types import SimpleNamespace

from lawrag.core.rag import answer as answer_mod
from scripts import rag_export_wrong_final_prompt_io as export


def test_build_product_request_matches_answer_prompt_shape(monkeypatch):
    monkeypatch.setattr(export.switches, "is_on", lambda _key: False)
    section = answer_mod.Section(
        n=1, doc_id="d", doc="문서", node=1, path="제1조", page=None,
        kind="구조적용어탐색", matched="exact", text="원문 그대로")
    request = export.build_product_request("질문 그대로", [section], spots=[])
    assert request["system"] == answer_mod.ANSWER_SYSTEM
    assert request["user"] == "[질문]\n질문 그대로\n\n[컨텍스트]\n[1] 문서 ▸ 제1조\n원문 그대로"
    assert request["schema"] == answer_mod.ANSWER_SCHEMA
    assert request["max_tokens"] == 4000
    assert request["effort"] == "high"


def test_case_markdown_preserves_full_prompt_and_output():
    row = {
        "case_no": "cm-x", "model": "haiku", "question": "질문",
        "reference_answer": "기준", "semantic_grade": {"correct": False},
        "selected_evidence": [], "original_usage": {},
        "final_product_request": {
            "call_name": "rag.answer", "system": "SYS", "user": "USER",
            "schema": {"type": "object"}, "max_tokens": 4000, "effort": "high",
            "wiki_context_on": False,
        },
        "original_product_output": {"answer": "OUTPUT", "answerable": True},
        "hashes": {"system_sha256": "s", "user_sha256": "u"},
    }
    text = export.case_markdown(row)
    assert "SYS" in text and "USER" in text and "OUTPUT" in text
    assert "생략 없음" in text


def test_dynamic_fence_does_not_truncate_embedded_markdown():
    value = "앞\n```python\nprint(1)\n```\n뒤"
    fenced = export._fence(value)
    assert value in fenced
    assert fenced.startswith("````text")
