from __future__ import annotations

import json
from pathlib import Path

from lawrag.core.rag import internal_compliance


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
DATASET = ROOT / "01_DATA" / "review" / "internal_compliance_holdout_v1.json"


def test_frozen_holdout_candidate_is_exact_and_fail_closed():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    results = []
    unsafe_compliant = []
    for case in data["cases"]:
        internal = {case["internal"]["evidence_id"]: case["internal"]["text"]}
        external = {row["evidence_id"]: row["text"] for row in case["externals"]}
        packet = internal_compliance.sanitize_compilation(
            case["compiler_output"], case["question"], internal, external)
        assessment = internal_compliance.assess_packet(
            packet, case["retrieval_status"])
        results.append(assessment["verdict"] == case["expected_verdict"])
        if assessment["verdict"] == "부합" and (
                assessment["invalid_count"]
                or assessment["unresolved_requirement_ids"]
                or assessment["retrieval_status"] != "ok"):
            unsafe_compliant.append(case["case_id"])
    assert len(results) == 12 and all(results)
    assert unsafe_compliant == []


def test_closed_id_and_exact_quote_violations_block_compliance():
    raw = {
        "issues": [{"issue_id": "I1", "question_span": "승인"}],
        "internal_units": [{"claim_id": "N1", "evidence_id": "N:n:1",
                            "issue_ids": ["I1"], "role": "PROCEDURE",
                            "quote": "사전 승인을 받는다"}],
        "requirements": [{"requirement_id": "R1", "evidence_id": "E:fake:9",
                          "issue_ids": ["I1"], "role": "PROCEDURE",
                          "effect": "PROCEDURE", "quote": "사전 승인을 받는다"}],
        "bindings": [{"requirement_id": "R1", "internal_claim_ids": ["N1"],
                      "status": "SATISFIED", "reason": "동일"}],
    }
    packet = internal_compliance.sanitize_compilation(
        raw, "승인 절차", {"N:n:1": "사전 승인을 받는다."},
        {"E:o:1": "사전 승인을 받는다."})
    assessment = internal_compliance.assess_packet(packet, "ok")
    assert packet["validation"]["closed_id_violations"] == ["E:fake:9"]
    assert assessment["verdict"] == "재검토"
    assert assessment["coverage_closed"] is False


def test_context_is_preserved_but_never_counts_as_coverage():
    raw = {
        "issues": [{"issue_id": "I1", "question_span": "정의"}],
        "internal_units": [],
        "requirements": [{"requirement_id": "R1", "evidence_id": "E:o:1",
                          "issue_ids": ["I1"], "role": "CONTEXT",
                          "effect": "CONTEXT", "quote": "용어의 뜻"}],
        "bindings": [],
    }
    packet = internal_compliance.sanitize_compilation(
        raw, "정의 확인", {"N:n:1": "내규"}, {"E:o:1": "용어의 뜻"})
    assessment = internal_compliance.assess_packet(packet, "ok")
    assert packet["selected_evidence_ids"] == ["E:o:1"]
    assert packet["substantive_requirement_ids"] == []
    assert assessment["verdict"] == "재검토"

