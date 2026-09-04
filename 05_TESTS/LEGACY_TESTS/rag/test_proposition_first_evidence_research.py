from __future__ import annotations

from types import SimpleNamespace

from lawrag.core.rag import answer
from lawrag.core.rag import proposition_first_evidence_research as compiler


def _section(candidate_id="research-candidate-1"):
    return answer.Section(
        n=1,
        doc_id="DOC",
        doc="테스트 규정",
        node=1,
        path="제1조",
        page=1,
        kind="본문",
        matched="허가",
        text="회사는 허가를 받아야 한다.",
        legal_meta={
            "integrated_research": {
                "candidate_id": candidate_id,
                "scope_id": "INSTRUMENT:DOC",
            }
        },
    )


def test_evidence_reuses_final_section_candidate_id():
    evidence = compiler.evidence_from_sections([_section()])
    assert evidence[0].evidence_id == "research-candidate-1"


def test_missing_targets_are_role_prioritized_and_bounded():
    result = SimpleNamespace(coverage=(
        {"issue_id": "I1", "required_role": "DEFINITION", "state": "MISSING"},
        {"issue_id": "I1", "required_role": "LEGAL_EFFECT", "state": "MISSING"},
        {"issue_id": "I1", "required_role": "EXCEPTION", "state": "MISSING"},
    ))
    targets = compiler._missing_targets(result)
    assert [row["required_role"] for row in targets] == ["LEGAL_EFFECT", "DEFINITION"]


class _AnswerLLM:
    def structured(self, *args, **kwargs):
        del args, kwargs
        return {
            "answer": "회사는 허가를 받아야 합니다.",
            "answerable": True,
            "conclusion_strength": "DIRECT",
            "evidence_ids": ["research-candidate-1"],
            "issue_results": [{
                "issue_id": "I1",
                "conclusion": "허가가 필요합니다.",
                "conclusion_strength": "DIRECT",
                "evidence_ids": ["research-candidate-1"],
                "unresolved_requirements": [],
            }],
        }


def test_missing_role_is_claim_local_and_never_globally_blocks_answer():
    section = _section()
    packet = {
        "schema_version": compiler.PROFILE,
        "answer_mode": "ADVISORY",
        "selected_evidence_ids": ["research-candidate-1"],
        "issues": [{"issue_id": "I1", "question_span": "허가"}],
        "claims": [{
            "claim_id": "R1",
            "evidence_id": "research-candidate-1",
            "issue_ids": ["I1"],
            "role": "GOVERNING_RULE",
            "proposition": "허가를 받아야 한다",
            "quote": "허가를 받아야 한다",
        }],
        "coverage": [],
        "missing": [{
            "issue_id": "I1",
            "coverage_key": "role:I1:EXCEPTION",
            "required_role": "EXCEPTION",
            "state": "MISSING",
        }],
    }
    section.legal_meta["legal_compilation"] = packet
    result = compiler.synthesize_answer(_AnswerLLM(), "회사는 허가를 받아야 하는가", [section])
    assert result.answerable is True
    assert result.answer
    assert result.issue_results[0]["conclusion_strength"] == "CONDITIONAL"
    assert result.issue_results[0]["unresolved_requirements"] == ["EXCEPTION"]
    assert result.gate_violation is True


def test_answer_evidence_outside_issue_claim_is_removed_without_global_block():
    section = _section()
    packet = {
        "schema_version": compiler.PROFILE,
        "answer_mode": "ADVISORY",
        "selected_evidence_ids": ["research-candidate-1"],
        "issues": [{"issue_id": "I1", "question_span": "허가"}],
        "claims": [],
        "coverage": [],
        "missing": [],
    }
    section.legal_meta["legal_compilation"] = packet
    result = compiler.synthesize_answer(_AnswerLLM(), "회사는 허가를 받아야 하는가", [section])
    assert result.answerable is True
    assert result.answer
    assert result.issue_results[0]["evidence_ids"] == []
    assert result.gate_violation is True
