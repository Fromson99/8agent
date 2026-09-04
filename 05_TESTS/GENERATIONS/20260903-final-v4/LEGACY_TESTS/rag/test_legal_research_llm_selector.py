from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from threading import Barrier, Lock

import pytest

from lawrag.core.rag.legal_instrument_routing import (
    ClosedRouteMenuViolation,
    InstrumentRouteCursor,
    InstrumentRouteMenuItem,
    InstrumentRoutePage,
    route_decision_schema,
)
from lawrag.core.rag.legal_research_atlas import (
    InstrumentRecord,
    InstrumentRole,
    NormLayer,
)
from lawrag.core.rag.legal_research_controller import (
    CandidatePage,
    ClosedMenuViolation,
    ExhaustionPolicy,
    PageMode,
)
from lawrag.core.rag.legal_research_llm_selector import (
    ANTHROPIC_SCHEMA_PROFILE,
    HAIKU_MODEL,
    HaikuInstrumentRouteSelector,
    LegalResearchLLMError,
    QWEN_NATIVE_SCHEMA_PROFILE,
    QWEN_REDUCED_SCHEMA_PROFILE,
    StructuredOutputProfile,
    ThreadLocalStructuredRecorder,
    onsite_qwen_profile,
    branches_from_query_plan,
    build_article_model_request,
    parse_article_page_decision,
    parse_instrument_route_decision,
    plan_question,
    selector_profile_from_environment,
)


class _FakeExchange:
    def __init__(self, kind, system, user, result, *, model=HAIKU_MODEL, error=""):
        self.model = model
        self._value = {
            "kind": kind,
            "at": "2026-08-29T00:00:00+00:00",
            "model": model,
            "usage": {"input_tokens": 101, "output_tokens": 17},
            "stop_reason": "end_turn",
            "images": 0,
            "dur_ms": 19,
            "ttft_ms": 7,
            "system": system,
            "user": user,
            "raw_response": json.dumps(result, ensure_ascii=False),
            "error": error,
        }

    def dump(self):
        return deepcopy(self._value)


class _FakeLLM:
    backend = "anthropic"
    model = HAIKU_MODEL
    transport_max_retries = 0

    def __init__(
        self, response, *, barrier=None, model=HAIKU_MODEL, retries=0,
        backend="anthropic",
    ):
        self.response = deepcopy(response)
        self.barrier = barrier
        self.backend = backend
        self.model = model
        self.transport_max_retries = retries
        self.log = []
        self.calls = []

    def structured(
        self, kind, system, user, schema, max_tokens=16000, effort="high",
        images=None, model=None,
    ):
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        self.calls.append({
            "kind": kind,
            "system": system,
            "user": user,
            "schema": deepcopy(schema),
            "max_tokens": max_tokens,
            "effort": effort,
            "images": images,
            "model": model,
        })
        result = deepcopy(self.response)
        self.log.append(_FakeExchange(
            kind, system, user, result, model=self.model,
        ))
        return result


@dataclass(frozen=True)
class _Unit:
    id: str
    instrument_id: str
    node_id: object
    parent_node_id: object | None
    path: str
    label: str
    kind: str
    has_children: bool

    @property
    def coordinate(self):
        return f"{self.instrument_id}:{self.node_id}"

    def to_dict(self):
        return {
            "id": self.id,
            "instrument_id": self.instrument_id,
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "path": self.path,
            "label": self.label,
            "kind": self.kind,
            "has_children": self.has_children,
            "coordinate": self.coordinate,
        }


def _instrument(instrument_id: str, name: str) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=instrument_id,
        name=name,
        source_kind="law",
        norm_layer=NormLayer.STATUTE,
        default_role=InstrumentRole.PRIMARY_ACT,
        series_key=name,
        status="현행",
        enforce="2026-01-01",
        revised="2025-12-01",
        version="test",
        node_count=1,
        article_count=1,
        body_article_count=1,
        nonbody_article_count=0,
    )


def _instrument_page() -> InstrumentRoutePage:
    items = tuple(
        InstrumentRouteMenuItem(
            menu_id=f"menu-{index}",
            instrument=_instrument(f"law-{index}", name),
            profile=None,
            routing_score=0,
            routing_signals=(),
        )
        for index, name in enumerate(("금융법", "감독규정"), 1)
    )
    return InstrumentRoutePage(
        page_id="IRW1:Bthreshold:O0:abc",
        wave=1,
        branch_id="threshold",
        issue_axis="THRESHOLD",
        cursor=InstrumentRouteCursor("threshold", 0, 2, "abcdef"),
        next_cursor=None,
        items=items,
        ordered_route_so_far=(),
    )


def _article_page(*items: _Unit) -> CandidatePage:
    return CandidatePage(
        page_id="W1:Bthreshold:Ilaw-1:PROOT:O0",
        wave=1,
        branch_id="threshold",
        issue_axis="THRESHOLD",
        instrument_role="IMPLEMENTATION_DETAIL",
        exhaustion_policy=ExhaustionPolicy.TARGETED_ROUTE,
        mode=PageMode.HIERARCHY,
        instrument_id="law-1",
        parent_node_id=None,
        offset=0,
        page_size=max(1, len(items)),
        items=tuple(items),
        has_more=False,
        required_coverage=("threshold-rule",),
        satisfied_coverage=(),
    )


def test_recorder_uses_one_client_per_thread_and_preserves_exact_receipts() -> None:
    barrier = Barrier(2)
    instances = []
    instances_lock = Lock()

    def factory():
        client = _FakeLLM({"ok": True}, barrier=barrier)
        with instances_lock:
            instances.append(client)
        return client

    recorder = ThreadLocalStructuredRecorder(factory)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    def one(value):
        return recorder.structured(
            "rag.test.thread-local",
            "system-exact",
            f"user-{value}",
            schema,
            max_tokens=77,
            effort=None,
            model=HAIKU_MODEL,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(one, (1, 2))) == [{"ok": True}, {"ok": True}]

    assert len(instances) == 2
    assert [len(instance.log) for instance in instances] == [1, 1]
    assert len(recorder.audit) == 2
    for receipt in recorder.audit:
        assert receipt["backend"] == "anthropic"
        assert receipt["requested_model"] == HAIKU_MODEL
        assert receipt["provider_model"] == HAIKU_MODEL
        assert receipt["transport_max_retries"] == 0
        assert receipt["request"]["system"] == "system-exact"
        assert receipt["request"]["schema"] == schema
        assert receipt["request"]["max_tokens"] == 77
        assert receipt["provider"]["raw_response"] == '{"ok": true}'
        assert receipt["provider"]["usage"] == {
            "input_tokens": 101, "output_tokens": 17,
        }
        assert receipt["provider"]["ttft_ms"] == 7
        assert receipt["provider"]["dur_ms"] == 19
        assert receipt["provider"]["error"] == ""
        assert receipt["structured_output"] == {"ok": True}
        assert receipt["wrapper_error"] == ""
        assert len(receipt["request_sha256"]) == 64


@pytest.mark.parametrize(
    ("model", "retries", "message"),
    (("wrong-model", 0, "model must"), (HAIKU_MODEL, 2, "max_retries")),
)
def test_recorder_fails_before_call_on_transport_policy_drift(
    model, retries, message,
) -> None:
    recorder = ThreadLocalStructuredRecorder(
        lambda: _FakeLLM({}, model=model, retries=retries),
    )
    with pytest.raises(LegalResearchLLMError, match=message):
        recorder.structured("kind", "system", "user", {})
    assert recorder.audit == []


def test_recorder_projects_numeric_bounds_recursively_and_receipts_sent_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "fallback_rank": {
                "type": "integer",
                "minimum": 0,
                "maximum": 999,
                "description": "local validation retains the range",
            },
            "scores": {
                "type": "array",
                "description": "normalized scores",
                "uniqueItems": True,
                "items": {
                    "anyOf": [
                        {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        {"type": "null"},
                    ],
                },
            },
            "minimum": {"type": "string"},
        },
        "required": ["fallback_rank", "scores", "minimum"],
        "additionalProperties": False,
    }
    original = deepcopy(schema)
    client = _FakeLLM({"fallback_rank": 0, "scores": [], "minimum": "kept"})
    recorder = ThreadLocalStructuredRecorder(lambda: client)

    recorder.structured("rag.test.schema-projection", "system", "user", schema)

    sent = client.calls[0]["schema"]
    assert sent["properties"]["fallback_rank"] == {
        "type": "integer",
        "description": (
            "local validation retains the range\n\n"
            "{minimum: 0, maximum: 999}"
        ),
    }
    assert sent["properties"]["scores"]["items"]["anyOf"] == [
        {
            "type": "number",
            "description": "{minimum: 0.0, maximum: 1.0}",
        },
        {"type": "null"},
    ]
    assert "uniqueItems" not in sent["properties"]["scores"]
    assert sent["properties"]["scores"]["description"] == (
        "normalized scores\n\n{uniqueItems: True}"
    )
    assert sent["properties"]["minimum"] == {"type": "string"}
    assert recorder.audit[0]["request"]["schema"] == sent
    assert recorder.audit[0]["canonical_schema"] == original
    assert recorder.audit[0]["schema_profile"] == ANTHROPIC_SCHEMA_PROFILE
    assert schema == original


@pytest.mark.parametrize(
    ("profile", "constraints_remain"),
    (
        (
            StructuredOutputProfile(
                backend="genos", model="qwen-onsite",
                schema_profile=QWEN_NATIVE_SCHEMA_PROFILE,
            ),
            True,
        ),
        (onsite_qwen_profile("qwen-onsite", reduced_schema=True), False),
    ),
)
def test_qwen_profiles_preserve_canonical_validation_contract(
    profile, constraints_remain,
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "selected_ids": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
                "maxItems": 0,
                "description": "No eligible IDs exist; return an empty array.",
            },
        },
        "required": ["selected_ids"],
        "additionalProperties": False,
    }
    original = deepcopy(schema)
    client = _FakeLLM(
        {"selected_ids": []}, model="qwen-onsite", backend="genos",
    )
    recorder = ThreadLocalStructuredRecorder(
        lambda: client, profile=profile,
    )

    assert recorder.structured(
        "rag.test.qwen-schema", "system", "user", schema,
        model="qwen-onsite",
    ) == {"selected_ids": []}

    sent = client.calls[0]["schema"]["properties"]["selected_ids"]
    assert ("maxItems" in sent) is constraints_remain
    assert ("uniqueItems" in sent) is constraints_remain
    if not constraints_remain:
        assert "maxItems: 0" in sent["description"]
        assert "uniqueItems: True" in sent["description"]
    receipt = recorder.audit[0]
    assert receipt["backend"] == "genos"
    assert receipt["requested_model"] == "qwen-onsite"
    assert receipt["provider_model"] == "qwen-onsite"
    assert receipt["schema_profile"] == profile.schema_profile
    assert receipt["canonical_schema"] == original
    assert receipt["outbound_schema"] == client.calls[0]["schema"]
    assert schema == original


def test_qwen_profile_rejects_backend_and_model_drift_before_provider_call() -> None:
    wrong_backend = _FakeLLM(
        {}, model="qwen-onsite", backend="anthropic",
    )
    recorder = ThreadLocalStructuredRecorder(
        lambda: wrong_backend, profile=onsite_qwen_profile("qwen-onsite"),
    )
    with pytest.raises(LegalResearchLLMError, match="backend must be genos"):
        recorder.structured("kind", "system", "user", {})
    assert wrong_backend.calls == []

    client = _FakeLLM({}, model="qwen-onsite", backend="genos")
    recorder = ThreadLocalStructuredRecorder(
        lambda: client, profile=onsite_qwen_profile("qwen-onsite"),
    )
    with pytest.raises(LegalResearchLLMError, match="profiled selector model"):
        recorder.structured(
            "kind", "system", "user", {}, model=HAIKU_MODEL,
        )
    assert client.calls == []


def test_environment_selects_reduced_onsite_qwen_profile(monkeypatch) -> None:
    from lawrag.core import llm as llm_mod

    monkeypatch.setattr(llm_mod, "load_env", lambda: None)
    monkeypatch.setattr(llm_mod, "backend", lambda: "genos")
    monkeypatch.setenv("GENOS_LLM_MODEL", "qwen-onsite")
    monkeypatch.delenv("GENOS_LLM_SCHEMA_PROFILE", raising=False)

    profile = selector_profile_from_environment()
    assert profile.backend == "genos"
    assert profile.model == "qwen-onsite"
    assert profile.schema_profile == QWEN_REDUCED_SCHEMA_PROFILE


def test_instrument_parser_is_type_strict_and_requires_every_disposition() -> None:
    page = _instrument_page()
    valid = {
        "page_id": page.page_id,
        "choices": [{"menu_id": "menu-1", "fallback_rank": 0}],
        "rejected_menu_ids": ["menu-2"],
        "route_complete": True,
        "rationale": "금융법부터 확인",
    }
    parsed = parse_instrument_route_decision(page, valid)
    assert parsed.choices[0].menu_id == "menu-1"

    string_bool = deepcopy(valid)
    string_bool["route_complete"] = "false"
    with pytest.raises(TypeError, match="boolean"):
        parse_instrument_route_decision(page, string_bool)

    bool_rank = deepcopy(valid)
    bool_rank["choices"][0]["fallback_rank"] = True
    with pytest.raises(TypeError, match="integer"):
        parse_instrument_route_decision(page, bool_rank)

    for rank in (-1, 1000):
        out_of_range = deepcopy(valid)
        out_of_range["choices"][0]["fallback_rank"] = rank
        with pytest.raises(ClosedRouteMenuViolation, match="between 0 and 999"):
            parse_instrument_route_decision(page, out_of_range)

    duplicate_choice = deepcopy(valid)
    duplicate_choice["choices"].append(deepcopy(duplicate_choice["choices"][0]))
    with pytest.raises(ClosedRouteMenuViolation, match="duplicate selected menu IDs"):
        parse_instrument_route_decision(page, duplicate_choice)

    omitted = deepcopy(valid)
    omitted["rejected_menu_ids"] = []
    with pytest.raises(ClosedRouteMenuViolation, match="explicit disposition"):
        parse_instrument_route_decision(page, omitted)

    invented = deepcopy(valid)
    invented["rejected_menu_ids"] = ["invented"]
    with pytest.raises(ClosedRouteMenuViolation, match="outside the closed page"):
        parse_instrument_route_decision(page, invented)

    continued = replace(
        page,
        next_cursor=InstrumentRouteCursor("threshold", 2, 2, "abcdef"),
    )
    continued_value = deepcopy(valid)
    continued_value["page_id"] = continued.page_id
    continued_decision = parse_instrument_route_decision(continued, continued_value)
    assert continued_decision.route_complete is True
    assert continued.next_cursor is not None


def test_empty_instrument_route_schema_has_no_fake_menu_id() -> None:
    page = replace(_instrument_page(), items=())
    schema = route_decision_schema(page)
    rendered = json.dumps(schema, ensure_ascii=False)
    assert "__NO_INSTRUMENT__" not in rendered
    assert schema["properties"]["choices"]["maxItems"] == 0
    assert schema["properties"]["rejected_menu_ids"]["maxItems"] == 0


def test_article_parser_rejects_duplicate_coverage_omission_and_unknown_id() -> None:
    container = _Unit(
        "nav:chapter", "law-1", 10, None, "제3장", "제3장 업무",
        "CONTAINER", True,
    )
    article = _Unit(
        "nav:article", "law-1", 15, 10, "제3장/제15조", "제15조",
        "ARTICLE", False,
    )
    page = _article_page(container, article)
    valid = {
        "page_id": page.page_id,
        "selected_ids": [article.id],
        "descend_ids": [container.id],
        "defer_ids": [],
        "rejected_ids": [],
        "coverage": [{"id": article.id, "keys": ["threshold-rule"]}],
        "route_complete": False,
        "rationale": "관련 조문",
    }
    parsed = parse_article_page_decision(page, valid)
    assert parsed.selected_ids == (article.id,)

    duplicate_coverage = deepcopy(valid)
    duplicate_coverage["coverage"].append(deepcopy(duplicate_coverage["coverage"][0]))
    with pytest.raises(ClosedMenuViolation, match="duplicate coverage row"):
        parse_article_page_decision(page, duplicate_coverage)

    omitted = deepcopy(valid)
    omitted["descend_ids"] = []
    with pytest.raises(ClosedMenuViolation, match="explicit disposition"):
        parse_article_page_decision(page, omitted)

    unknown = deepcopy(valid)
    unknown["selected_ids"] = ["invented"]
    with pytest.raises(ClosedMenuViolation, match="unknown IDs"):
        parse_article_page_decision(page, unknown)

    string_bool = deepcopy(valid)
    string_bool["route_complete"] = "false"
    with pytest.raises(TypeError, match="boolean"):
        parse_article_page_decision(page, string_bool)

    deferred_complete = deepcopy(valid)
    deferred_complete["selected_ids"] = []
    deferred_complete["defer_ids"] = [article.id]
    deferred_complete["coverage"] = []
    deferred_complete["route_complete"] = True
    with pytest.raises(ClosedMenuViolation, match="deferred items"):
        parse_article_page_decision(page, deferred_complete)


def test_structural_only_page_uses_empty_arrays_without_fake_legal_ids() -> None:
    container = _Unit(
        "nav:chapter", "law-1", 10, None, "제3장", "제3장 업무",
        "CONTAINER", True,
    )
    page = _article_page(container)
    request = build_article_model_request(
        "업무 범위를 확인", page, {}, lambda _instrument, _node: "",
    )
    serialized_schema = json.dumps(request.schema, ensure_ascii=False)
    assert "__NO_VALID_ID__" not in serialized_schema
    assert "__NO_COVERAGE_KEY__" not in serialized_schema
    assert request.schema["properties"]["selected_ids"]["maxItems"] == 0
    assert request.schema["properties"]["coverage"]["maxItems"] == 0

    valid = {
        "page_id": page.page_id,
        "selected_ids": [],
        "descend_ids": [container.id],
        "defer_ids": [],
        "rejected_ids": [],
        "coverage": [],
        "route_complete": False,
        "rationale": "하위 구조를 확인",
    }
    parsed = parse_article_page_decision(page, valid)
    assert parsed.selected_ids == ()
    assert parsed.coverage_by_id == {}

    invented = deepcopy(valid)
    invented["selected_ids"] = ["__NO_VALID_ID__"]
    with pytest.raises(ClosedMenuViolation, match="unknown IDs"):
        parse_article_page_decision(page, invented)

    invented_coverage = deepcopy(valid)
    invented_coverage["coverage"] = [
        {"id": "__NO_VALID_ID__", "keys": ["threshold-rule"]},
    ]
    with pytest.raises(ClosedMenuViolation, match="selected evidence"):
        parse_article_page_decision(page, invented_coverage)


def test_query_plan_branches_are_capped_and_cannot_smuggle_gold_instruments() -> None:
    plan = {
        "family_hypotheses": [
            {"family_id": family, "reason": "candidate"}
            for family in (
                "THRESHOLD", "DELEGATION", "EXCEPTION", "TEMPORAL", "AUTHORITY",
            )
        ],
        "mentions": [{
            "surface": "100분의 10", "start": 8, "end": 15, "role": "QUANTITY",
        }],
        "predicate_hypotheses": [],
        "expansion_terms": {
            "exact": ["계열회사"], "fulltext": [], "vector": [],
        },
        "preferred_instrument_ids": ["gold-law"],
        "gold_coordinates": ["gold-law:15"],
        "reference_answer": "비공개 정답",
    }
    before = tuple(branch.to_dict() for branch in branches_from_query_plan(plan))
    assert len(before) == 4
    assert [row["issue_axis"] for row in before] == [
        "THRESHOLD", "DELEGATION", "EXCEPTION", "TEMPORAL",
    ]
    assert all(row["preferred_instrument_ids"] == [] for row in before)
    assert all(row["preferred_roles"] for row in before)
    assert all("gold-law" not in row["topic_hints"] for row in before)

    mutated = deepcopy(plan)
    mutated["gold_coordinates"] = ["another-secret-law:999"]
    mutated["reference_answer"] = "정반대 정답"
    mutated["preferred_instrument_ids"] = ["another-secret-law"]
    after = tuple(branch.to_dict() for branch in branches_from_query_plan(mutated))
    assert after == before


def test_article_request_finds_late_literal_with_exact_bounded_source_offsets() -> None:
    literal = "100분의 10"
    text = "가" * 2300 + " 주관회사는 계열회사 보유분의 " + literal + "을 확인한다. " + "나" * 1400
    literal_start = text.index(literal)
    article = _Unit(
        "nav:article-15", "law-1", 15, 10,
        "인수업무규정/제3장/제15조", "제15조 주식의 인수",
        "ARTICLE", False,
    )
    page = _article_page(article)
    plan = {
        "family_hypotheses": [{"family_id": "THRESHOLD", "reason": "수치"}],
        "predicate_hypotheses": [],
        "mentions": [],
        "expansion_terms": {
            "exact": [literal, "계열회사", "주관회사"],
            "fulltext": [],
            "vector": [],
        },
        "raw_output": {"gold_coordinates": ["secret:1"]},
        "gold_coordinates": ["secret:1"],
    }
    calls = []

    def resolver(instrument_id, node_id):
        calls.append((instrument_id, node_id))
        return text

    request = build_article_model_request(
        "주관회사의 계열회사 보유분 100분의 10 기준은?",
        page,
        plan,
        resolver,
    )
    payload = json.loads(request.user)
    item = payload["article_page"]["items"][0]
    source = item["source"]
    assert calls == [("law-1", 15)]
    assert item["coordinate"] == "law-1:15"
    assert item["path"] == "인수업무규정/제3장/제15조"
    assert source["text_length"] == len(text)
    assert source["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert text not in request.user
    assert sum(len(row["text"]) for row in source["evidence_windows"]) < len(text)

    match = next(
        match
        for window in source["evidence_windows"]
        for match in window["matched_terms"]
        if match["query_term"] == literal
    )
    assert match["start"] == literal_start
    assert match["end"] == literal_start + len(literal)
    containing = next(
        window for window in source["evidence_windows"]
        if window["char_start"] <= literal_start < window["char_end"]
    )
    assert containing["text"] == text[
        containing["char_start"]:containing["char_end"]
    ]

    mutated = deepcopy(plan)
    mutated["gold_coordinates"] = ["other-secret:999"]
    mutated["raw_output"] = {"reference_answer": "mutated gold"}
    second = build_article_model_request(
        "주관회사의 계열회사 보유분 100분의 10 기준은?",
        page,
        mutated,
        resolver,
    )
    assert second.to_dict() == request.to_dict()


def test_question_plan_and_instrument_selector_share_recorded_structured_contract() -> None:
    plan_output = {
        "mentions": [],
        "family_hypotheses": [{"family_id": "THRESHOLD", "reason": "수치"}],
        "predicate_hypotheses": [],
        "exact_terms": ["100분의 10"],
        "fulltext_queries": [],
        "vector_queries": [],
    }
    plan_client = _FakeLLM(plan_output)
    recorder = ThreadLocalStructuredRecorder(lambda: plan_client)
    plan = plan_question(recorder, "100분의 10 기준은?")
    assert plan["family_hypotheses"][0]["family_id"] == "THRESHOLD"
    assert recorder.audit[0]["kind"] == "rag.query_grounding.plan"
    assert recorder.audit[0]["requested_model"] == HAIKU_MODEL

    page = _instrument_page()
    route_output = {
        "page_id": page.page_id,
        "choices": [{"menu_id": "menu-1", "fallback_rank": 0}],
        "rejected_menu_ids": ["menu-2"],
        "route_complete": True,
        "rationale": "first law",
    }
    route_client = _FakeLLM(route_output)
    route_recorder = ThreadLocalStructuredRecorder(lambda: route_client)
    decision = HaikuInstrumentRouteSelector(route_recorder).select("질문", page)
    assert decision.choices[0].menu_id == "menu-1"
    assert route_recorder.audit[0]["kind"] == "rag.legal_research.instrument_route"
    sent_schema = route_client.calls[0]["schema"]
    rank_schema = sent_schema["properties"]["choices"]["items"]["properties"][
        "fallback_rank"
    ]
    assert rank_schema == {
        "type": "integer",
        "description": "{minimum: 0, maximum: 999}",
    }
    assert route_recorder.audit[0]["request"]["schema"] == sent_schema
