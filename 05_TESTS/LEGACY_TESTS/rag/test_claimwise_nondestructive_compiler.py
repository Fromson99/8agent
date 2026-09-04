from __future__ import annotations

from copy import deepcopy

from lawrag.core.rag import claimwise_nondestructive_compiler as compiler
from lawrag.core.rag.legal_proposition_compiler import EvidenceSpan


QUESTION = "금융회사는 심사업무를 위탁할 수 있는가?"
BASELINE_TEXT = "금융회사는 심사업무를 자유롭게 위탁할 수 있다. 별도 조건은 없다."
QUOTE = "금융회사는 승인을 받은 경우에만 심사업무를 위탁할 수 있다."
EVIDENCE = (
    EvidenceSpan("EV-1", "DOC", 10, "업무위탁규정", "제10조", QUOTE),
)
PACKET = {
    "claims": [{
        "claim_id": "R1", "evidence_id": "EV-1", "quote": QUOTE,
        "proposition": QUOTE, "role": "CONDITION",
    }],
    "missing": [{"coverage_key": "role:I1:LEGAL_EFFECT"}],
    "search_plan": [{"coverage_key": "role:I1:LEGAL_EFFECT"}],
}
BASELINE = {
    "answer": BASELINE_TEXT,
    "answerable": True,
    "conclusion_strength": "DIRECT",
    "error": "",
    "evidence_ids": ["research-1"],
    "gate_violation": False,
    "refs": [],
    "wiki": [],
}


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return deepcopy(self.outputs.pop(0))


def _claim(state: str, *, quote: str = QUOTE, evidence_id: str = "EV-1"):
    grounds = [] if state == "MISSING" else [{
        "evidence_id": evidence_id, "source_quote": quote,
    }]
    return {
        "claim_id": "C1",
        "answer_span": "금융회사는 심사업무를 자유롭게 위탁할 수 있다.",
        "state": state,
        "grounds": grounds,
    }


def _run(outputs, *, packet=PACKET, baseline=BASELINE):
    llm = FakeLLM(outputs)
    answer, meta = compiler.compile_claimwise_answer(
        QUESTION, baseline, EVIDENCE, packet, llm=llm,
    )
    return answer, meta, llm


def test_supported_claim_preserves_baseline_exactly() -> None:
    answer, meta, llm = _run([{"claims": [_claim("SUPPORTED")]}])
    assert answer["answer"] == BASELINE_TEXT
    assert meta["baseline_preserved_exactly"] is True
    assert meta["supported_count"] == 1
    assert len(llm.calls) == 1


def test_missing_claim_never_blocks_or_calls_merger() -> None:
    answer, meta, llm = _run([{"claims": [_claim("MISSING")]}])
    assert answer["answerable"] is True
    assert answer["gate_violation"] is False
    assert answer["answer"] == BASELINE_TEXT
    assert meta["global_block_count"] == 0
    assert meta["missing_count"] == 1
    assert len(llm.calls) == 1


def test_conditional_claim_can_patch_only_exact_target() -> None:
    replacement = f"법문은 ‘{QUOTE}’라고 정하므로 승인 조건을 확인해야 한다."
    answer, meta, _ = _run([
        {"claims": [_claim("CONDITIONAL")]},
        {"patches": [{
            "claim_id": "C1", "replacement_text": replacement,
            "evidence_ids": ["EV-1"],
        }]},
    ])
    assert answer["answer"] == replacement + " 별도 조건은 없다."
    assert meta["patch_count"] == 1
    assert answer["conclusion_strength"] == "QUALIFIED"


def test_conflicted_claim_can_patch() -> None:
    replacement = f"기존 결론과 달리 ‘{QUOTE}’라는 제한이 있다."
    answer, meta, _ = _run([
        {"claims": [_claim("CONFLICTED")]},
        {"patches": [{
            "claim_id": "C1", "replacement_text": replacement,
            "evidence_ids": ["EV-1"],
        }]},
    ])
    assert replacement in answer["answer"]
    assert meta["conflicted_count"] == 1


def test_invalid_evidence_id_is_dropped_and_audited() -> None:
    answer, meta, llm = _run([{
        "claims": [_claim("CONFLICTED", evidence_id="EV-MADE-UP")],
    }])
    assert answer["answer"] == BASELINE_TEXT
    assert meta["validation"]["closed_evidence_violations"] == ["C1"]
    assert len(llm.calls) == 1


def test_nonexact_quote_is_dropped_and_audited() -> None:
    answer, meta, _ = _run([{
        "claims": [_claim("CONDITIONAL", quote="없는 인용")],
    }])
    assert answer["answer"] == BASELINE_TEXT
    assert meta["validation"]["exact_quote_violations"] == ["C1"]


def test_nonexact_answer_span_is_dropped() -> None:
    row = _claim("CONFLICTED")
    row["answer_span"] = "답변에 없는 문장"
    answer, meta, _ = _run([{"claims": [row]}])
    assert answer["answer"] == BASELINE_TEXT
    assert meta["validation"]["answer_span_violations"] == ["C1"]


def test_missing_with_ground_is_invalid() -> None:
    row = _claim("MISSING")
    row["grounds"] = [{"evidence_id": "EV-1", "source_quote": QUOTE}]
    _, meta, _ = _run([{"claims": [row]}])
    assert meta["validation"]["state_ground_violations"] == ["C1"]


def test_patch_must_include_exact_ground_quote() -> None:
    answer, meta, _ = _run([
        {"claims": [_claim("CONDITIONAL")]},
        {"patches": [{
            "claim_id": "C1", "replacement_text": "승인이 필요할 수 있다.",
            "evidence_ids": ["EV-1"],
        }]},
    ])
    assert answer["answer"] == BASELINE_TEXT
    assert meta["validation"]["replacement_ground_violations"] == ["C1"]


def test_patch_cannot_target_supported_or_missing_claim() -> None:
    answer, meta, llm = _run([{"claims": [_claim("SUPPORTED")]}])
    assert len(llm.calls) == 1
    assert answer["answer"] == BASELINE_TEXT
    assert meta["patch_count"] == 0


def test_empty_compiler_menu_is_fail_open_without_llm_call() -> None:
    answer, meta, llm = _run([], packet={"claims": [], "search_plan": []})
    assert answer == BASELINE
    assert meta["global_block_count"] == 0
    assert len(llm.calls) == 0


def test_raw_claim_count_is_capped() -> None:
    rows = []
    for number in range(20):
        rows.append({
            "claim_id": f"C{number}",
            "answer_span": BASELINE_TEXT,
            "state": "SUPPORTED",
            "grounds": [{"evidence_id": "EV-1", "source_quote": QUOTE}],
        })
    _, meta, _ = _run([{"claims": rows}])
    assert meta["claim_count"] == 1  # overlap guard is stricter than the cap
    assert len(meta["validation"]["overlap_violations"]) == 11


def test_product_calls_pin_haiku() -> None:
    _, _, llm = _run([{"claims": [_claim("SUPPORTED")]}])
    assert llm.calls[0][1]["model"] == "claude-haiku-4-5-20251001"


def test_schema_uses_closed_evidence_ids() -> None:
    schema = compiler._audit_schema(["EV-1", "EV-2"])
    enum = schema["properties"]["claims"]["items"]["properties"]["grounds"][
        "items"
    ]["properties"]["evidence_id"]["enum"]
    assert enum == ["EV-1", "EV-2"]


def test_stage_plan_preserves_identity_and_has_one_filter() -> None:
    baseline = compiler.stage_specs("baseline")
    candidate = compiler.stage_specs(compiler.PROFILE)
    assert [row[1] for row in baseline] == ["source", "retrieve", "present"]
    assert [row[1] for row in candidate].count("filter") == 1
    assert candidate[-1][1] == "present"


def test_input_objects_are_not_mutated() -> None:
    baseline = deepcopy(BASELINE)
    packet = deepcopy(PACKET)
    _run([{"claims": [_claim("SUPPORTED")]}], packet=packet, baseline=baseline)
    assert baseline == BASELINE
    assert packet == PACKET
