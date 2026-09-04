from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
FROZEN = (
    Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0148/condition-slot-validator/"
    "revisions/rev-001/snapshot/lawrag/core/domain_graph/requirements.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("adr0148_test_candidate", FROZEN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _evidence(module, evidence_id, source, quote, predicates):
    start = source.index(quote)
    return module.SlotEvidence(
        evidence_id, source, start, start + len(quote), quote,
        tuple(predicates), True,
    )


def test_direct_predicate_evidence_keeps_true():
    module = _module()
    source = "투자기간이 2년 미만이다"
    result = module.validate_condition_slots(
        [module.ConditionSlot("duration", "duration_under_two_years", "true",
                              ("E1",), "direct")],
        [_evidence(module, "E1", source, "2년 미만",
                   ("duration_under_two_years",))],
    )
    assert result["slots"][0]["status"] == "true"
    assert result["violations"] == []


def test_different_predicate_is_downgraded_without_bridge():
    module = _module()
    source = "제3자배정으로 취득했다"
    result = module.validate_condition_slots(
        [module.ConditionSlot("method", "non_offering_or_sale_method", "true",
                              ("E1",), "guessed equivalence")],
        [_evidence(module, "E1", source, "제3자배정",
                   ("third_party_allotment",))],
    )
    assert result["slots"][0]["status"] == "unknown"
    assert result["violations"][0]["reasons"] == [
        "unsupported_cross_predicate_inference"
    ]


def test_verified_definition_bridge_allows_cross_predicate_support():
    module = _module()
    fact = "질문의 재무적투자자"
    definition = "재무적투자자를 전문투자자로 정의한다"
    result = module.validate_condition_slots(
        [module.ConditionSlot("actor", "professional_investor", "true",
                              ("E-fact",), "definition")],
        [
            _evidence(module, "E-fact", fact, "재무적투자자",
                      ("financial_investor",)),
            _evidence(module, "E-def", definition, definition,
                      ("financial_investor",)),
        ],
        [module.PredicateBridge(
            "B1", "DEFINES", "financial_investor", "professional_investor",
            ("E-def",), True,
        )],
    )
    assert result["slots"][0]["status"] == "true"


def test_asserted_false_also_requires_evidence():
    module = _module()
    result = module.validate_condition_slots(
        [module.ConditionSlot("exception", "company_exception", "false", (),
                              "not in question")],
        [],
    )
    assert result["slots"][0]["status"] == "unknown"
    assert "missing_evidence" in result["violations"][0]["reasons"]
