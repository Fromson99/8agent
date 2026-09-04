from __future__ import annotations

from types import SimpleNamespace

from lawrag.core.rag.legal_instrument_routing import InstrumentRouteBranch
from lawrag.core.rag.legal_research_atlas import (
    InstrumentRecord,
    InstrumentRole,
    NavigationKind,
    NavigationUnit,
    NormLayer,
)
from lawrag.core.rag.legal_system_entry import (
    LegalSystemEntryPlanner,
    scope_alignment,
)


def _plan(*mentions):
    return {"mentions": [
        {"role": role, "surface": surface}
        for role, surface in mentions
    ]}


def test_quantity_alone_is_not_semantic_scope_alignment() -> None:
    plan = _plan(
        ("SOURCE_ACTOR", "주관회사"),
        ("OBJECT", "계열회사 보유분"),
        ("QUANTITY", "100분의 10"),
    )
    result = scope_alignment(plan, "금융회사가 100분의 10 이상 보유한 경우")
    assert result["numeric_only"] is True
    assert result["aligned"] is False


def test_quantity_plus_actor_and_object_is_aligned() -> None:
    plan = _plan(
        ("SOURCE_ACTOR", "주관회사"),
        ("OBJECT", "계열회사 보유분"),
        ("QUANTITY", "100분의 10"),
    )
    result = scope_alignment(
        plan,
        "주관회사가 계열회사 보유분을 100분의 10으로 산정한다.",
    )
    assert result["numeric_only"] is False
    assert result["aligned"] is True


def test_public_authority_delegation_does_not_match_private_outsourcing_actor() -> None:
    plan = _plan(
        ("SOURCE_ACTOR", "금융투자업자"),
        ("ACTION", "외부 기관에 위탁"),
        ("OBJECT", "고객 심사업무"),
    )
    result = scope_alignment(
        plan,
        "금융위원회는 감독 업무를 금융감독원장에게 위탁할 수 있다.",
    )
    assert result["wrong_actor_delegation"] is True
    assert result["aligned"] is False


class _View:
    def __init__(self, text):
        self.by_id = {1: {"id": 1, "text": text}}

    def section_text(self, node, cap):
        return node["text"][:cap]


class _Atlas:
    def __init__(self):
        names = (
            ("credit", "신용정보의 이용 및 보호에 관한 법률"),
            ("privacy", "개인정보 보호법"),
            ("unrelated", "외국환거래법"),
        )
        self.instruments = tuple(
            InstrumentRecord(
                instrument_id=instrument_id,
                name=name,
                source_kind="law",
                norm_layer=NormLayer.STATUTE,
                default_role=InstrumentRole.PRIMARY_ACT,
                series_key=name,
                status="현행",
                enforce="",
                revised="",
                version="",
                node_count=1,
                article_count=1,
            )
            for instrument_id, name in names
        )
        self._articles = {
            instrument_id: (NavigationUnit(
                id=f"nav:{instrument_id}:1",
                instrument_id=instrument_id,
                node_id=1,
                parent_node_id=None,
                path="제1조",
                label="제1조 목적",
                kind=NavigationKind.ARTICLE,
                has_children=False,
            ),)
            for instrument_id, _name in names
        }
        self.current_index = SimpleNamespace(entry_docs={
            instrument_id: _View("일반적인 목적 조문")
            for instrument_id, _name in names
        })

    def article_units(self, instrument_id):
        return self._articles[instrument_id]


class _SystemMap:
    def profile(self, instrument_id):
        return SimpleNamespace(purpose="")

    def matching_issue_families(self, routing_context, issue_axis):
        if issue_axis == "DELEGATION" and "신용정보" in routing_context:
            return (SimpleNamespace(
                family_id="INFORMATION_PROTECTION_SERIES",
                instrument_ids=("credit", "privacy"),
                weight=620,
            ),)
        return ()


def test_legal_system_family_routes_credit_question_to_privacy_series() -> None:
    planner = LegalSystemEntryPlanner(
        _Atlas(),
        instrument_limit=3,
        entry_limit=1,
        system_map=_SystemMap(),
        semantic_card_index=None,
    )
    branch = InstrumentRouteBranch(
        branch_id="b",
        issue_axis="DELEGATION",
        preferred_roles=(InstrumentRole.PRIMARY_ACT,),
        topic_hints=("신용정보 처리위탁",),
    )
    result = planner.plan_branch(
        "신용정보 처리업무를 외부에 위탁할 수 있나",
        {"mentions": [{"role": "OBJECT", "surface": "신용정보"}]},
        branch,
    )
    ids = result.preferred_instrument_ids
    assert ids.index("credit") < ids.index("unrelated")
    assert ids.index("privacy") < ids.index("unrelated")
    privacy = next(row for row in result.instruments if row.instrument_id == "privacy")
    assert "LEGAL_SYSTEM_FAMILY:INFORMATION_PROTECTION_SERIES" in privacy.signals
