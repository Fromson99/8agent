"""GENOS response names are diagnostics; payload, durable state and external pins remain checked."""
import asyncio
import importlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.model_contract import validate_response_model
from test_legal_agent_double_harness import BINDING, DOMAIN, PROFILE, WireTransport, proposal, wire, work
from test_workflow_failed_originals import fixtures, load, tree

GENOS = {**BINDING, "provider": "genos", "adapter_version": "genos-single-send-v1"}


class RawTransport(WireTransport):
    binding = GENOS

    def send_once(self, *, body, ticket):
        self.calls.append(body)
        return self.responses.pop(0)


def response(value, model):
    result = wire(value)
    if model is None:
        result["body_json"].pop("model")
    else:
        result["body_json"]["model"] = model
    return result


@pytest.mark.parametrize("model,status", [
    (BINDING["model"], "match"), ("server-alias", "different"), (None, "missing"), (7, "invalid"),
])
def test_genos_gateway_preserves_raw_response_and_records_both_ids(work, model, status):
    raw = response(proposal(), model)
    transport = RawTransport([raw])
    gateway = ModelGateway(work, work.context, {**PROFILE, "model_binding": GENOS}, DOMAIN, transport)
    result = gateway.generate("investigate", work.save_view("investigate", {}, []), "InvestigateDecision")
    assert result == proposal()
    assert len(transport.calls) == 1
    saved = work.db.execute("SELECT response_json,receipt_json FROM model_attempt").fetchone()
    assert json.loads(saved[0]) == raw
    receipt = json.loads(saved[1])
    assert receipt["requested_model"] == GENOS["model"]
    assert receipt["actual_response_model"] == (model if isinstance(model, str) else None)
    assert receipt["response_model_status"] == status
    assert receipt["response_model_policy"] == "genos-serving-model-metadata-v1"


@pytest.mark.parametrize("binding", [
    BINDING, {**GENOS, "provider": "openrouter"}, {**GENOS, "trust_zone": "external"},
    {**GENOS, "adapter_version": "other-adapter"},
])
@pytest.mark.parametrize("model", ["server-alias", None])
def test_other_bindings_keep_exact_model_contract(binding, model):
    with pytest.raises(ContractError, match="actual response model"):
        validate_response_model(binding, response(proposal(), model)["body_json"])


@pytest.mark.parametrize("repaired", [True, False])
def test_genos_metadata_does_not_bypass_bounded_payload_repair(work, repaired):
    transport = RawTransport([response("{", "server-alias"),
                              response(proposal() if repaired else "{", None)])
    profile = {**PROFILE, "model_binding": GENOS, "max_schema_repairs": 1}
    gateway = ModelGateway(work, work.context, profile, DOMAIN, transport)
    view = work.save_view("investigate", {}, [])
    if repaired:
        assert gateway.generate("investigate", view, "InvestigateDecision") == proposal()
    else:
        with pytest.raises(ProposalError):
            gateway.generate("investigate", view, "InvestigateDecision")
    assert len(transport.calls) == 2


def application(tmp_path, tree, model):
    class Transport(fixtures.General):
        binding = GENOS

        def send_once(self, *, body, ticket):
            result = super().send_once(body=body, ticket=ticket)
            if model is None:
                result["body_json"].pop("model", None)
            else:
                result["body_json"]["model"] = model
            return result

    app, _ = fixtures.prior.app_for(tmp_path, tree)
    transport = Transport()
    app.state.pipeline.term_agent.transport = transport
    app.state.pipeline.term_agent.profile["model_binding"] = GENOS
    app.state.workflow_runtime.services.profile["model_binding"] = GENOS
    return app, transport


@pytest.mark.parametrize("model", ["server-alias", None])
def test_actual_service_parent_children_saved_duplicate_and_restart(tmp_path, tree, model):
    app, transport = application(tmp_path, tree, model)
    root = Path(os.environ["WORKFLOW_TEST_CODE_ROOT"])
    service = load("genos_metadata_test_service", root / "service.py")
    service._APP = app
    service._BINDING = {"mode": "isolated-candidate-test"}
    request = {"API_TYPE": "RAG_ASK", **fixtures.prior.BODY}
    first = asyncio.run(service.service({}, request))
    assert first["status"] == 200, first
    value = first["body"]
    assert value["status"] == "completed", value
    assert value["comparison_items"]["items"] and value["evidence_refs"]
    for side in ("internal", "external"):
        assert value["rag_results"][side]["evidence_ids"]
    count = len(transport.views)
    again = asyncio.run(service.service({}, request))
    saved = asyncio.run(service.service({}, {"API_TYPE": "WORKFLOW_STATUS",
        "run_id": value["run_id"], "session_id": request["session_id"]}))
    assert again["body"]["answer"] == saved["body"]["answer"] == value["answer"]
    assert len(transport.views) == count
    app.state.pipeline.store.close()
    app2, transport2 = application(tmp_path, tree, model)
    service._APP = app2
    restored = asyncio.run(service.service({}, request))
    assert restored["body"]["answer"] == value["answer"]
    assert transport2.views == []
    app2.state.pipeline.store.close()


@pytest.mark.parametrize("model", ["server-alias", None])
@pytest.mark.parametrize("tamper", [False, True])
def test_recovered_response_keeps_hash_deadline_and_no_duplicate_call(tmp_path, tree, monkeypatch, model, tamper):
    app, transport = application(tmp_path, tree, model)
    runtime = app.state.workflow_runtime
    module = importlib.import_module(runtime.__class__.__module__.rsplit(".", 1)[0] + ".repository")
    original = module.Repository.finish

    def crash(self, ident, result):
        if ident.startswith("model:"):
            raise KeyboardInterrupt("received before workflow checkpoint")
        return original(self, ident, result)

    principal = {"user_id": "u", "team_id": "risk_team", "document_ids": ["inside", "outside"]}
    monkeypatch.setattr(module.Repository, "finish", crash)
    with pytest.raises(KeyboardInterrupt):
        runtime.execute({**fixtures.prior.BODY, "workflow_id": "risk_team_compare_workflow"}, principal)
    monkeypatch.setattr(module.Repository, "finish", original)
    journal = next(runtime.root.glob("*/journal.sqlite"))
    with sqlite3.connect(journal) as db:
        revision = db.execute("SELECT revision FROM workflow_state").fetchone()[0]
        deadline = db.execute("SELECT deadline_at FROM run").fetchone()[0]
        if tamper:
            db.execute("UPDATE model_attempt SET response_json='{}'")
    count = len(transport.views)
    with TestClient(app, raise_server_exceptions=False) as client:
        resumed = client.post("/v1/workflows/resume", json={
            "run_id": journal.parent.name, "session_id": "s", "expected_revision": revision})
    if tamper:
        assert "WORKFLOW_MODEL_RESPONSE_INTEGRITY" in resumed.text, resumed.text
        assert len(transport.views) == count
    else:
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "completed", resumed.text
        assert sum(stage == "workflow-intake" for stage, _ in transport.views) == 1
    with sqlite3.connect(journal) as db:
        assert db.execute("SELECT deadline_at FROM run").fetchone()[0] == deadline
    app.state.pipeline.store.close()
