"""Native child failures after real fixture reads, through service consumers."""
import asyncio
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

R = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load("transport_original_fixture", R / "06_TOOLS/EXPERIMENTS/adr_0936/test_generalized.py")
tree = fixtures.tree


def application(tmp_path, tree, failure):
    from semantic_runtime.legal_agent.errors import TransportError

    class Transport(fixtures.General):
        def __init__(self):
            super().__init__()
            self.attempts = []

        def send_once(self, *, body, ticket):
            view = json.loads(body["messages"][1]["content"])["view"]
            stage = view.get("source_stage", view["phase"])
            self.attempts.append(stage)
            if stage.startswith("source-law-sources-"):
                if failure == "429":
                    raise TransportError("synthetic upstream pool limit", retryable=True, unknown=False,
                                         response={"status_code": 429, "retry_after": "1", "body_json": {"error": {"code": 429}}})
                if failure == "unknown":
                    raise TransportError("synthetic unknown transport", retryable=True, unknown=True)
            return super().send_once(body=body, ticket=ticket)

    app, _ = fixtures.prior.app_for(tmp_path, tree)
    transport = Transport()
    app.state.pipeline.term_agent.transport = transport
    return app, transport


@pytest.mark.parametrize("failure", ["429", "unknown"])
def test_failed_child_reads_reach_actual_service_saved_duplicate_and_restart(tmp_path, tree, failure):
    app, transport = application(tmp_path, tree, failure)
    code = Path(os.environ["WORKFLOW_TEST_CODE_ROOT"])
    service = load("transport_original_service", code / "service.py")
    service._APP = app
    service._BINDING = {"mode": "isolated-candidate-test"}
    request = {"API_TYPE": "RAG_ASK", **fixtures.prior.BODY}
    response = asyncio.run(service.service({}, request))
    assert response["status"] == 200, response
    value = response["body"]
    root = app.state.workflow_runtime.root / value["run_id"]
    assert value["status"] == "partial", value
    budgets = {}
    for side in ("internal", "external"):
        child = value["rag_results"][side]
        assert child["status"] == "failed" and child["error_code"]
        assert child["answer"] is None and child["continuation"] is None
        assert child["bundle"]["export_mode"] == "READ_ORIGINALS"
        assert child["bundle"]["claims"] == [] and not child["bundle"]["semantic_quality_certified"]
        path = next(root.glob("children/" + side + "/legal-agent/runs/*/*/journal.sqlite"))
        with sqlite3.connect(path) as db:
            ids = {row[0] for row in db.execute("SELECT evidence_id FROM evidence_unit")}
            assert ids and ids == set(child["evidence_ids"])
            assert db.execute("SELECT status FROM run").fetchone()[0] == "FAILED"
            attempts = db.execute("SELECT count(*) FROM model_attempt").fetchone()[0]
            assert attempts == (2 if failure == "429" else 1)
            budgets[side] = dict(zip(("attempts", "deadline"), (attempts, db.execute("SELECT deadline_at FROM run").fetchone()[0])))
    count = len(transport.attempts)
    duplicate = asyncio.run(service.service({}, request))
    saved = asyncio.run(service.service({}, {"API_TYPE": "WORKFLOW_STATUS",
        "run_id": value["run_id"], "session_id": request["session_id"]}))
    assert duplicate["body"]["answer"] == saved["body"]["answer"] == value["answer"]
    assert len(transport.attempts) == count
    # New app objects reopen the same durable runtime; no model work is repeated.
    app2, transport2 = application(tmp_path, tree, failure)
    service._APP = app2
    again = asyncio.run(service.service({}, request))
    assert again["body"]["answer"] == value["answer"], again
    assert transport2.attempts == []
    for side, expected in budgets.items():
        path = next(root.glob("children/" + side + "/legal-agent/runs/*/*/journal.sqlite"))
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM model_attempt").fetchone()[0] == expected["attempts"]
            assert db.execute("SELECT deadline_at FROM run").fetchone()[0] == expected["deadline"]


@pytest.mark.parametrize("mutation", ["evidence", "binding", "export", "status"])
def test_saved_failed_read_export_tampering_is_rejected(tmp_path, tree, mutation):
    app, transport = application(tmp_path, tree, "unknown")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/rag/ask", json=fixtures.prior.BODY)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["rag_results"]["external"]["evidence_ids"]
        root = app.state.workflow_runtime.root / value["run_id"]
        path = next(root.glob("children/external/legal-agent/runs/*/*/journal.sqlite"))
        if mutation in ("evidence", "binding"):
            with sqlite3.connect(path) as db:
                if mutation == "binding":
                    with pytest.raises(sqlite3.IntegrityError, match="immutable request binding"):
                        db.execute("UPDATE run SET binding_json='{}'")
                    return
                else:
                    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='evidence_span'").fetchall():
                        db.execute('DROP TRIGGER "' + name + '"')
                    db.execute("UPDATE evidence_span SET text='forged'")
        else:
            with sqlite3.connect(root / "journal.sqlite") as db:
                if mutation == "export":
                    db.execute("UPDATE workflow_child_export SET bundle_json='{}'")
                else:
                    row = db.execute("SELECT call_id,result_json FROM workflow_call WHERE kind='rag' LIMIT 1").fetchone()
                    result = json.loads(row[1])
                    result["status"] = "completed"
                    from semantic_runtime.contracts import digest
                    db.execute("UPDATE workflow_call SET result_json=?,result_hash=? WHERE call_id=?",
                               (json.dumps(result), digest(result), row[0]))
        count = len(transport.attempts)
        again = client.post("/v1/rag/ask", json=fixtures.prior.BODY)
        assert again.status_code in (409, 500), again.text
        assert len(transport.attempts) == count


def test_resume_between_failed_read_export_and_parent_commit_preserves_calls(tmp_path, tree, monkeypatch):
    from semantic_runtime import workflow_rag
    app, transport = application(tmp_path, tree, "unknown")
    original = workflow_rag.execute
    calls = []

    def interrupt(*args, **kwargs):
        value = original(*args, **kwargs)
        assert value["evidence_ids"]
        calls.append(len(transport.attempts))
        if len(calls) == 1:
            raise KeyboardInterrupt("after failed child's original export, before parent receipt")
        return value

    monkeypatch.setattr(workflow_rag, "execute", interrupt)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute(
            {**fixtures.prior.BODY, "workflow_id": "risk_team_compare_workflow"}, fixtures.prior.prior._base.PRINCIPAL)
    path = next(app.state.workflow_runtime.root.glob("*/journal.sqlite"))
    with sqlite3.connect(path) as db:
        revision = db.execute("SELECT revision FROM workflow_state").fetchone()[0]
        deadline = db.execute("SELECT deadline_at FROM run").fetchone()[0]
    with TestClient(app) as client:
        result = client.post("/v1/workflows/resume", json={
            "run_id": path.parent.name, "session_id": "s", "expected_revision": revision})
        assert result.status_code == 200, result.text
        assert result.json()["rag_results"]["internal"]["evidence_ids"]
    assert calls[1] == calls[0]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT deadline_at FROM run").fetchone()[0] == deadline


def test_resume_after_failure_receipt_before_export_does_not_create_new_child(tmp_path, tree, monkeypatch):
    from semantic_runtime import workflow_evidence
    app, transport = application(tmp_path, tree, "unknown")
    original = workflow_evidence.compile_read_bundle
    seen = []

    def interrupt(*args, **kwargs):
        seen.append(args[0].run()["run_id"])
        if len(seen) == 1:
            raise KeyboardInterrupt("failure durable; originals not yet exported")
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow_evidence, "compile_read_bundle", interrupt)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute(
            {**fixtures.prior.BODY, "workflow_id": "risk_team_compare_workflow"}, fixtures.prior.prior._base.PRINCIPAL)
    path = next(app.state.workflow_runtime.root.glob("*/journal.sqlite"))
    with sqlite3.connect(path) as db:
        revision = db.execute("SELECT revision FROM workflow_state").fetchone()[0]
    with TestClient(app) as client:
        result = client.post("/v1/workflows/resume", json={
            "run_id": path.parent.name, "session_id": "s", "expected_revision": revision})
        assert result.status_code == 200, result.text
        assert result.json()["rag_results"]["internal"]["evidence_ids"]
    assert seen[0] == seen[1]
    journals = list(path.parent.glob("children/internal/legal-agent/runs/*/*/journal.sqlite"))
    assert len(journals) == 1
    with sqlite3.connect(journals[0]) as db:
        assert db.execute("SELECT count(*) FROM model_attempt").fetchone()[0] == 1


@pytest.mark.parametrize("mutation", ["none", "hash", "action", "side", "binding", "legacy", "duplicate"])
def test_failure_receipt_requires_exact_original_call_binding(mutation):
    from types import SimpleNamespace as S
    from semantic_runtime.contracts import digest
    from semantic_runtime.workflow_rag import failed_child_receipt
    from semantic_runtime.legal_agent.errors import ContractError
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE event(seq INTEGER PRIMARY KEY,kind TEXT,payload_json TEXT,payload_hash TEXT)")
    action = {"operation": "ask_rag", "side": "external", "args": {"question": "Q", "previous": None}}
    receipt = {"schema_version": "workflow-child-failure-v1", "call_id": "call", "side": "external",
               "action_hash": digest(action), "parent_binding_hash": "bound",
               "error_code": "MODEL_TRANSPORT_ERROR", "export_reads": True}
    if mutation == "action":
        receipt["action_hash"] = "changed"
    if mutation == "side":
        receipt["side"] = "internal"
    if mutation == "binding":
        receipt["parent_binding_hash"] = "different"
    if mutation == "legacy":
        receipt.pop("schema_version")
    values = ("WORKFLOW_CHILD_FAILED", json.dumps(receipt), "wrong" if mutation == "hash" else digest(receipt))
    db.execute("INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)", values)
    if mutation == "duplicate":
        db.execute("INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)", values)
    port = S(session=S(repo=S(db=db), context=S(binding_hash="bound")))
    try:
        if mutation == "none":
            assert failed_child_receipt(port, action, "call") == receipt
        else:
            with pytest.raises(ContractError):
                failed_child_receipt(port, action, "call")
    finally:
        db.close()
