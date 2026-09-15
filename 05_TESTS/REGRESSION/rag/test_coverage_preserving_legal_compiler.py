from __future__ import annotations

import inspect

from lawrag.core.rag import answer
from lawrag.research.legacy_rag import coverage_preserving_research as compiler
from lawrag.core.rag import legalclosure_runtime


def _menu():
    return [{
        "evidence_id": "E-DOC-10",
        "coordinate": ["DOC", 10],
        "document": "테스트법",
        "path": "제10조",
        "origins": ["SYSTEM_PRIOR"],
        "branch": "rule",
        "coverage_keys": [],
        "matched": ["허가"],
        "span": {"start": 0, "end": 20, "excerpt": "회사는 허가를 받아야 한다."},
    }]


def _section(mode: str) -> answer.Section:
    packet = {
        "schema_version": "coverage-preserving-evidence-packet-v1",
        "answer_mode": mode,
        "direct_rule_answer_allowed": mode == "DIRECT_RULE",
        "selected_evidence_ids": ["E-DOC-10"],
        "claims": [{
            "claim_id": "C1",
            "evidence_id": "E-DOC-10",
            "role": "GOVERNING_RULE",
            "proposition": "허가가 필요하다.",
            "quote": "허가를 받아야 한다",
        }],
        "coverage": [],
        "missing": ([{"coverage_key": "사실관계", "search_terms": ["업무 내용"]}]
                    if mode != "DIRECT_RULE" else []),
        "reason": "test",
    }
    return answer.Section(
        n=1, doc_id="DOC", doc="테스트법", node=10, path="제10조",
        page=None, kind="본문", matched="허가",
        text="회사는 허가를 받아야 한다.",
        legal_meta={"legal_compilation": packet},
    )


class _AnswerLLM:
    def __init__(self, payload):
        self.payload = payload
        self.log = []

    def structured(self, kind, system, user, schema, **kwargs):
        assert kind == "rag.answer"
        assert "법률 evidence compiler" in system
        assert "E-DOC-10" in user
        assert "conclusion_strength" in schema["properties"]
        return dict(self.payload)


def test_packet_sanitizer_is_closed_id_and_exact_quote_only():
    raw = {
        "selected_ids": ["E-NOT-IN-CORPUS", "E-DOC-10"],
        "claims": [
            {
                "claim_id": "C1", "evidence_id": "E-DOC-10",
                "role": "GOVERNING_RULE", "proposition": "허가 필요",
                "quote": "허가를 받아야 한다",
            },
            {
                "claim_id": "C2", "evidence_id": "E-NOT-IN-CORPUS",
                "role": "GOVERNING_RULE", "proposition": "환각",
                "quote": "없는 원문",
            },
            {
                "claim_id": "C3", "evidence_id": "E-DOC-10",
                "role": "GOVERNING_RULE", "proposition": "변조",
                "quote": "허가 없이 해도 된다",
            },
        ],
        "coverage": [],
        "answer_mode": "DIRECT_RULE",
        "missing": [],
        "reason": "",
    }
    packet = compiler._sanitize_packet(raw, _menu(), {})
    assert packet["selected_ids"] == ["E-DOC-10"]
    assert [row["claim_id"] for row in packet["claims"]] == ["C1"]
    assert packet["invalid_claim_count"] == 2


def test_source_span_centers_a_late_article_match():
    text = "머리" * 1000 + "100분의 10과 계열회사 보유분" + "꼬리" * 1000
    start, end, excerpt = compiler._source_span(
        text, "계열회사 보유분 100분의 10인가?", ("계열회사",)
    )
    assert start > 800
    assert end - start <= compiler.SPAN_CHARS
    assert "계열회사" in excerpt


def test_answer_gate_coerces_direct_conclusion_when_only_conditional_is_allowed():
    llm = _AnswerLLM({
        "answer": "가능합니다.",
        "answerable": True,
        "conclusion_strength": "DIRECT",
        "evidence_ids": ["E-DOC-10"],
    })
    result = answer.synthesize(llm, "가능한가?", [_section("CONDITIONAL_APPLICATION")])
    assert result.answerable is False
    assert result.conclusion_strength == "INSUFFICIENT"
    assert result.gate_violation is True
    assert "단정할 수 없습니다" in result.answer


def test_answer_gate_accepts_direct_closed_evidence():
    llm = _AnswerLLM({
        "answer": "법문상 허가가 필요합니다.",
        "answerable": True,
        "conclusion_strength": "DIRECT",
        "evidence_ids": ["E-DOC-10"],
    })
    result = answer.synthesize(llm, "허가가 필요한가?", [_section("DIRECT_RULE")])
    assert result.answerable is True
    assert result.evidence_ids == ["E-DOC-10"]
    assert result.gate_violation is False


def test_runtime_profile_is_explicit_and_legacy_by_default():
    parameter = inspect.signature(legalclosure_runtime.retrieve).parameters[
        "integrated_profile"
    ]
    assert parameter.default == "legacy"
