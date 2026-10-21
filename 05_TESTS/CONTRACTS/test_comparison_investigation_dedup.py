"""Real API / durable ledger regressions with synthetic originals and model replies."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient
import test_internal_concept_comparison as fixture
from test_legal_agent_double_harness import wire
from test_research_state_owner import setup_task, ledger_with_need
from semantic_runtime.research_state import ResearchLedger, acquisition_key, evidence_basis
from semantic_runtime.legal_agent.law_navigation import Investigation, search_key
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.contracts import digest

tree = fixture.tree


def record(name, value):
    if os.environ.get("TEST_DIAGNOSTICS_DIR"):
        p = Path(os.environ["TEST_DIAGNOSTICS_DIR"]) / (name + ".json")
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class Repeating(fixture.Transport):
    def __init__(self, recover):
        super().__init__()
        self.recover = recover
        self.selected = []
        self.identity = None

    def send_once(self, *, body, ticket):
        view = json.loads(body["messages"][1]["content"])["view"]
        stage = view.get("source_stage", view["phase"])
        if (stage.startswith("source-law-sources-")
                and view.get("workflow_task", {}).get("source_category") == "internal"):
            self.views.append((stage, deepcopy(view)))
            if self.recover and view.get("repair_contract"):
                return wire({"target_id": None, "query": None, "reason": "확보 원문과 미확인 내용 반환"})
            choices = [a for a in view["actions"] if a["action"] == "SEARCH_STRUCTURE"]
            if self.identity is not None:
                choices = [a for a in choices if a["identity"] == self.identity]
            assert choices
            action = choices[0]
            self.identity = deepcopy(action["identity"])
            self.selected.append({"stage": stage, "identity": self.identity,
                                  "repair": bool(view.get("repair_contract"))})
            return wire({"target_id": action["id"], "query": "승인", "reason": "합성 중복 제안"})
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize("recover", [True, False])
def test_api_repeated_search_is_never_executed_twice_and_originals_survive(tmp_path, tree, recover):
    app, _ = fixture.application(tmp_path, tree)
    transport = Repeating(recover)
    app.state.pipeline.term_agent.transport = transport
    with TestClient(app) as client:
        response = client.post("/v1/rag/ask", json=fixture.fixture.prior.BODY)
        assert response.status_code == 200, response.text
        value = response.json()
        root = app.state.workflow_runtime.root / value["run_id"]
        journal = next(root.glob("children/internal/legal-agent/runs/*/*/journal.sqlite"))
        with sqlite3.connect(journal) as db:
            searches = [json.loads(v) for v, in db.execute(
                "SELECT payload_json FROM event WHERE kind='LAW_STRUCTURE_DIRECTORY'")]
        assert len(searches) == 1
        assert value["rag_results"]["internal"]["evidence_ids"]
        assert value["comparison_table"]["rows"][0]["internal"]
        assert len(transport.selected) == (2 if recover else 3)
        before = len(transport.views)
        duplicate = client.post("/v1/rag/ask", json=fixture.fixture.prior.BODY).json()
        saved = client.get("/v1/workflows/runs/" + value["run_id"],
                           params={"session_id": "s"}).json()
        assert duplicate["answer"] == saved["answer"] == value["answer"]
        assert len(transport.views) == before
        record("repeat-" + str(recover), {
            "executed_searches": len(searches), "proposals": transport.selected,
            "model_calls": before, "duplicate_added_calls": len(transport.views)-before,
            "originals_preserved": True, "status": value["status"]})


class EmptyPlan(fixture.Transport):
    def __init__(self):
        super().__init__()
        self.plans = []

    def send_once(self, *, body, ticket):
        view = json.loads(body["messages"][1]["content"])["view"]
        stage = view.get("source_stage", view["phase"])
        response = super().send_once(body=body, ticket=ticket)
        if stage == "workflow-items":
            value = json.loads(response["body_json"]["choices"][0]["message"]["content"])
            for item in value["items"]:
                item["next_tasks"] = []
                if "external" in item:
                    item["external"].update(status="PARTIAL", missing="예외 조건 원문 미확보")
            self.plans.append(deepcopy(value))
            return wire(value)
        return response


def test_api_missing_without_explicit_plan_is_reported_without_followup(tmp_path, tree):
    app, _ = fixture.application(tmp_path, tree)
    transport = EmptyPlan()
    app.state.pipeline.term_agent.transport = transport
    with TestClient(app) as client:
        response = client.post("/v1/rag/ask", json=fixture.fixture.prior.BODY)
        assert response.status_code == 200, response.text
        value = response.json()
    root = app.state.workflow_runtime.root / value["run_id"]
    with sqlite3.connect(root / "journal.sqlite") as db:
        state = json.loads(db.execute("SELECT checkpoint_json FROM workflow_state").fetchone()[0])
    board = state["task_board"]
    assert board["round"] == 0 and board["tasks"] == {}
    assert all(n["status"] == "OPEN" for n in board["research_needs"].values())
    assert "예외 조건 원문 미확보" in value["answer"]["text"]
    assert all(not i["next_tasks"] for p in transport.plans for i in p["items"])
    assert value["rag_results"]["external"]["evidence_ids"]
    record("no-implicit-search", {"followups": board["round"], "needs": board["research_needs"],
                                "originals_preserved": True, "status": value["status"]})


@pytest.mark.parametrize("kind", ["RESEARCH", "SEARCH_BODY", "SEARCH_STRUCTURE"])
def test_common_search_guard_rejects_duplicate_and_accepts_new_query(kind):
    action = {"action": kind, "identity": {"document_id": "d", "unit_id": "u"}}
    actions = {"T": action}
    p = {"query_keys": [search_key(["승인"])], "query_surface_history": [["승인"]],
         "body_search_history": [digest([action["identity"], search_key(["승인"])])],
         "structure_search_history": [{"document_id": "d", "queries": ["승인"]}]}
    inv = S(p=p, policy={"structure_first": True, "search_rounds": 8}, search_rounds_used=lambda: 1)
    value = {"next_action": kind, "targets": ["T"], "queries": ["승인"], "structure_filter": None}
    with pytest.raises(ProposalError, match="unchanged"):
        Investigation.validate_search_operation(inv, value, actions)
    Investigation.validate_search_operation(inv, {**value, "queries": ["보고"]}, actions)
    if kind != "RESEARCH":
        other = {"T": {**action, "identity": {"document_id": "different", "unit_id": "u"}}}
        Investigation.validate_search_operation(inv, value, other)


def test_structure_query_spacing_does_not_reopen_search():
    inv = S(p={"structure_search_history": [{"document_id": "d", "queries": ["승인 기준"]}]},
            policy={"search_rounds": 8})
    value = {"next_action": "SEARCH_STRUCTURE", "targets": ["T"],
             "queries": ["  승인   기준 "], "structure_filter": None}
    with pytest.raises(ProposalError, match="unchanged"):
        Investigation.validate_search_operation(inv, value, {"T": {"identity": {"document_id": "d"}}})


def test_quote_changes_do_not_create_new_evidence_or_search_after_restart():
    ledger, first = ledger_with_need()
    ledger.begin(first, {"request_id": "old", "evidence_ids": ["E1"]})
    ledger.finish(first, {"request_id": "searched", "evidence_ids": ["E1"],
                         "investigation_return": {}}, True)
    ledger = ResearchLedger(json.loads(json.dumps(ledger.board)))
    row = {"status": "PARTIAL", "missing": "같은 조건 원문 미확보를 다시 설명",
           "text": "확인한 부분", "citations": [{"evidence": "E1", "quote": "원"}], "dependencies": []}
    assert evidence_basis(row) == evidence_basis({**row, "citations": [{"evidence": "E1", "quote": "원문"}]})
    ledger.reconcile({"id": "i", "external_task": "조건 확인"}, "condition", "external",
                     row, "review-2", [], lambda _: pytest.fail("implicit task"))
    assert not ledger.pending() and ledger.used_followups == 1
    assert ledger.needs()[0]["status"] == "OPEN"
    assert evidence_basis(row) != evidence_basis({**row, "citations": [{"evidence": "E2", "quote": "원"}]})
    # An explicitly requested different original remains a valid pending task.
    task, proposal = setup_task()
    task.update(operation="read_node", allowed_operations=["read_node"],
                target_locator={"document_id": "new", "unit_id": "2", "source_id": "s2"})
    ident = ledger.register(task, proposal, True)
    assert not ledger.reuse(ledger.board["tasks"][ident])
    assert ledger.board["tasks"][ident]["status"] == "PENDING"


def test_same_exact_read_is_reused_despite_new_field_and_wording():
    ledger, first = ledger_with_need()
    task = first["task"]
    task.update(operation="read_node", target_locator={"document_id": "d", "unit_id": "u", "source_id": "s"})
    first.update(status="COMPLETE", acquisition_key=acquisition_key(task), result_request_id="prior")
    second = deepcopy(task)
    second.update(requested_fields=["exceptions"], missing_target="표현 변경")
    _, proposal = setup_task()
    ident = ledger.register(second, proposal, True)
    assert ledger.reuse(ledger.board["tasks"][ident])
    assert ledger.used_followups == 0
