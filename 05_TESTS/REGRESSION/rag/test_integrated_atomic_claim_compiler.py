from __future__ import annotations

import inspect

from lawrag.core.rag import answer
from lawrag.research.legacy_rag import integrated_atomic_claim_research as compiler


QUESTION = "코스닥시장에서 회사는 허가를 받아야 하는가"


def _menu(scope="MARKET:KOSDAQ"):
    return [{
        "evidence_id": "E1", "coordinate": ["DOC", 1], "document": "규정",
        "path": "제1조", "scope_id": scope,
        "excerpt": "회사는 허가를 받아야 한다.",
    }]


def _raw(scope_quote="허가를 받아야 한다"):
    return {
        "issues": [{"issue_id": "I1", "question_span": "허가를 받아야 하는가"}],
        "units": [{
            "unit_id": "U1", "evidence_id": "E1", "issue_ids": ["I1"],
            "role": "GOVERNING_RULE", "quote": scope_quote,
        }],
        "reason": "test",
    }


def test_soft_compiler_closes_question_span_quote_and_ids():
    packet = compiler._sanitize(_raw(), QUESTION, _menu())
    assert packet["issues"] == [{
        "issue_id": "I1", "question_span": "허가를 받아야 하는가"
    }]
    assert packet["units"][0]["quote"] == "허가를 받아야 한다"
    assert packet["claims"][0]["proposition"] == packet["claims"][0]["quote"]
    assert packet["selected_evidence_ids"] == ["E1"]


def test_invalid_soft_unit_does_not_remove_evidence_and_gets_context_binding():
    packet = compiler._sanitize(_raw("없는 문언"), QUESTION, _menu())
    assert packet["invalid_unit_count"] == 1
    assert len(packet["units"]) == 1
    assert packet["units"][0]["origin"] == "deterministic-context"
    assert packet["selected_evidence_ids"] == ["E1"]


def test_explicit_market_rejects_other_market_claim_without_scope_violation():
    packet = compiler._sanitize(_raw(), QUESTION, _menu("MARKET:KOSPI"))
    assert packet["units"] == []
    assert packet["selected_evidence_ids"] == []
    assert packet["scope_rejection_count"] == 1


class _AnswerLLM:
    def __init__(self, evidence_id="E1"):
        self.evidence_id = evidence_id
        self.log = []

    def structured(self, *args, **kwargs):
        del args, kwargs
        return {
            "answer": "허가를 받아야 합니다.", "answerable": True,
            "conclusion_strength": "DIRECT", "evidence_ids": [self.evidence_id],
        }


def _section():
    compilation = {
        "schema_version": "integrated-atomic-claim-evidence-v4",
        "answer_mode": "ADVISORY", "direct_rule_answer_allowed": True,
        "selected_evidence_ids": ["E1"],
        "issues": [{"issue_id": "I1", "question_span": "허가"}],
        "units": [{
            "unit_id": "U1", "evidence_id": "E1", "scope_id": "DOMAIN:TEST",
            "issue_ids": ["I1"], "role": "GOVERNING_RULE", "quote": "허가",
        }],
        "claims": [{
            "claim_id": "U1", "evidence_id": "E1", "scope_id": "DOMAIN:TEST",
            "issue_ids": ["I1"], "role": "GOVERNING_RULE",
            "proposition": "허가", "quote": "허가",
        }],
    }
    return answer.Section(
        n=1, doc_id="DOC", doc="규정", node=1, path="제1조", page=1,
        kind="본문", matched="허가", text="회사는 허가를 받아야 한다.",
        legal_meta={"legal_compilation": compilation},
    )


def test_v4_advisory_mode_does_not_block_supported_direct_answer():
    result = answer.synthesize(_AnswerLLM(), QUESTION, [_section()])
    assert result.answerable is True
    assert result.conclusion_strength == "DIRECT"
    assert result.gate_violation is False


def test_v4_still_blocks_evidence_id_outside_atomic_claim_set():
    result = answer.synthesize(_AnswerLLM("E-UNKNOWN"), QUESTION, [_section()])
    assert result.answerable is False
    assert result.gate_violation is True


def test_compiler_output_budget_is_explicit_and_reproducible():
    parameter = inspect.signature(compiler.attach_compilation).parameters["max_tokens"]
    assert parameter.default == 4000
