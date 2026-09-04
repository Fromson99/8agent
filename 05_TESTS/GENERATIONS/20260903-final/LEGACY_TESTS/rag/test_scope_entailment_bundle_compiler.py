from __future__ import annotations

import inspect
from types import SimpleNamespace

from lawrag.core.rag import legalclosure_runtime
from lawrag.core.rag import scope_entailment_bundle_research as compiler
from lawrag.core.rag.legal_research_state import CandidateProvenance


def _menu(scope: str = "MARKET:KOSDAQ"):
    return [{
        "evidence_id": "E-DOC-10",
        "coordinate": ["DOC", 10],
        "document": "코스닥시장 상장규정",
        "path": "제10조",
        "scope_id": scope,
        "origins": ["SYSTEM_PRIOR"],
        "branch": "rule",
        "coverage_keys": [],
        "matched": ["허가"],
        "span": {"start": 0, "end": 20, "excerpt": "회사는 허가를 받아야 한다."},
    }]


def _raw(*, scope: str = "MARKET:KOSDAQ", quote: str = "허가를 받아야 한다"):
    return {
        "selected_scope_ids": [scope],
        "quotes": [{
            "quote_id": "Q1", "evidence_id": "E-DOC-10",
            "scope_id": scope, "role": "GOVERNING_RULE", "quote": quote,
        }],
        "required_elements": [],
        "elements": [],
        "answer_mode": "DIRECT_RULE",
        "missing_elements": [],
        "reason": "test",
    }


def test_exact_quote_and_scope_are_closed_and_direct_is_downgraded():
    raw = _raw(quote="허가 없이 가능하다")
    packet = compiler._sanitize_packet(
        raw, _menu(), explicit_scopes={"MARKET:KOSDAQ"}
    )
    assert packet["quotes"] == []
    assert packet["answer_mode"] == "INSUFFICIENT"
    assert packet["direct_gate_allowed"] is False
    assert packet["invalid_quote_count"] == 1


def test_other_explicit_market_is_rejected_but_common_domain_is_allowed():
    wrong = compiler._sanitize_packet(
        _raw(scope="MARKET:KOSPI"),
        _menu(scope="MARKET:KOSPI"),
        explicit_scopes={"MARKET:KOSDAQ"},
    )
    assert wrong["quotes"] == []

    common = compiler._sanitize_packet(
        _raw(scope="DOMAIN:CAPITAL_MARKETS"),
        _menu(scope="DOMAIN:CAPITAL_MARKETS"),
        explicit_scopes={"MARKET:KOSDAQ"},
    )
    assert len(common["quotes"]) == 1


def test_direct_requires_all_core_decision_elements_on_exact_quotes():
    raw = _raw()
    raw["elements"] = [
        {"element": element, "evidence_id": "E-DOC-10", "quote": "허가를 받아야 한다"}
        for element in ("governing_rule", "actor_scope", "operative_effect")
    ]
    packet = compiler._sanitize_packet(raw, _menu())
    assert packet["missing_elements"] == []
    assert packet["answer_mode"] == "DIRECT_RULE"
    assert packet["direct_gate_allowed"] is True
    assert all(row["quote"] == row["proposition"] for row in packet["claims"])


def test_protected_bundle_prioritizes_explicit_scope_and_lexical_match():
    coordinates = [("A", 1), ("B", 2), ("C", 3)]
    candidates = {
        coordinate: SimpleNamespace(
            origins={CandidateProvenance.SEMANTIC_ENTRY}, coverage_keys=set(),
            score=10.0, source_order=number,
        )
        for number, coordinate in enumerate(coordinates)
    }
    spans = {
        ("A", 1): (0, 10, "무관한 규정"),
        ("B", 2): (0, 10, "계열회사 100분의 10"),
        ("C", 3): (0, 10, "계열회사"),
    }
    scopes = {
        ("A", 1): "DOMAIN:OTHER",
        ("B", 2): "MARKET:KOSDAQ",
        ("C", 3): "MARKET:KOSPI",
    }
    protected = compiler._protected_bundle(
        "코스닥 계열회사 100분의 10", coordinates, set(), candidates, spans,
        frozenset({"MARKET:KOSDAQ"}), scopes,
    )
    assert protected[0] == ("B", 2)


def test_runtime_profile_label_is_metadata_not_a_module_router():
    parameter = inspect.signature(legalclosure_runtime.retrieve).parameters[
        "integrated_profile"
    ]
    assert parameter.default == "legacy"
    injected = inspect.signature(legalclosure_runtime.retrieve).parameters[
        "research_profile"
    ]
    assert injected.default is None
    source = inspect.getsource(legalclosure_runtime.retrieve)
    assert "scope_entailment_bundle_research" not in source
