"""Actual SQLite SQL and existing batch/RAG consumer; no LLM/network calls."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from lawrag.pipeline import risk_basis_seed as fixed, risk_basis_sqlite as db
from semantic_runtime.basis_links.contracts import BasisError
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.storage import Store

ROOT = Path(__file__).resolve().parents[2]
# R2's direct-write CLI is retired. Preserve its historical tests against the
# sealed R2 bytes; the current seed-risk entrypoint only stages JSON.
import importlib.util
_spec = importlib.util.spec_from_file_location("lawrag.pipeline._sealed_risk_sqlite_r2_cli",
    ROOT / "08_DEPLOYMENT/GENOS/handoffs/risk_basis_sqlite_20261020_r2/payload/02_BACKEND/lawrag/pipeline/risk_basis_seed_cli.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)
PHOTO = ROOT / "01_DATA/TERM_RELEASES/risk-photo-0951-r2/named-documents/generation"
WHO = {"user_id": "contract-user", "team_id": "risk_team", "document_ids": [], "basis_review": True}


@pytest.fixture
def env(tmp_path):
    store = Store(PHOTO)
    runtime = tmp_path / "runtime"
    path = runtime / "basis-links/authority.sqlite"
    Repository(path).close()
    marker = path.parent / "SQLITE_ENABLED.json"
    marker.write_text(json.dumps({"schema_version": "basis-shared-sqlite-v1", "database": "authority.sqlite"}))
    context = {"authority": str(path), "generation": str(PHOTO), "runtime": str(runtime), "fixture": True}
    output = tmp_path / "job"
    try:
        yield SimpleNamespace(store=store, path=path, context=context, output=output, root=tmp_path)
    finally:
        store.close()


def run(env, action, **kwargs):
    return cli.execute(action, env.store, WHO, env.context, env.output, **kwargs)


def state(env):
    with db.authority(env.path) as repo:
        return {t: [dict(r) for r in repo.db.execute("SELECT * FROM " + t)] for t in db.TABLES}


def populate(env, count=4, status="PROPOSED"):
    mappings = fixed.resolve(env.store, WHO)
    ids = []
    with db.authority(env.path, write=True) as repo:
        service = Service(repo, SourcePort(env.store))
        for i, link in enumerate(mappings["links"][:count]):
            result = service.propose(mappings["principal"], {
                "request_id": "existing-batch-" + str(i), "kind": "BASIS", "reason": "기존 배치의 발견",
                "internal": link["internal"], "external": link["external"],
                "provenance": {"type": "MODEL_OBSERVATION", "method": "BATCH_DISCOVERY_V1",
                               "retrieval_role": "UNREVIEWED_CANDIDATE"}})
            ids.append(result["link"]["link_id"])
            if status != "PROPOSED":
                action = {"APPROVED": "approve", "REJECTED": "reject", "REVOKED": "revoke"}[status]
                result = service.review(mappings["principal"], {"request_id": "existing-review-" + str(i),
                    "action": action, "reason": "기존 검토", "items": [{"link_id": ids[-1], "revision": 1,
                                                                    "view_hash": result["view_hash"]}]})
                assert result["status"] == "completed"
    return ids


def plan_value(env):
    return json.loads((env.output / "plan.json").read_text())


def test_plan_reads_existing_authority_without_writing_or_reindex(env):
    before = state(env)
    assert run(env, "inspect")["authority"] == str(env.path)
    result = run(env, "plan")
    assert result["writes"] == 0 and len(result["actions"]) == 4
    assert state(env) == before
    sql = (env.output / "APPEND_ONLY.sql").read_text()
    assert "BEGIN IMMEDIATE" in sql and "ORACLE" not in sql and "LEGAL_SRC_" not in sql
    assert "CREATE TABLE" not in sql and "DELETE FROM" not in sql


def test_new_links_actual_sql_idempotence_and_revert(env):
    run(env, "plan")
    assert run(env, "apply")["external_endpoint_count"] == 7
    applied = state(env)
    assert len(applied["basis_head"]) == 4 and len(applied["basis_revision"]) == 8
    assert run(env, "apply")["status"] == "APPEND_VERIFIED"
    assert state(env) == applied
    assert run(env, "verify")["external_endpoint_count"] == 7
    assert run(env, "revoke")["status"] == "REVERT_VERIFIED"
    reverted = state(env)
    assert all(x["revision"] == 3 for x in reverted["basis_head"])
    assert len(reverted["basis_revision"]) == 12
    run(env, "revoke")
    assert state(env) == reverted


@pytest.mark.parametrize("count", [1, 4])
def test_batch_proposals_keep_ids_and_history_then_restore_proposed(env, count):
    previous = populate(env, count=count)
    result = run(env, "plan")
    assert sum(a["action"] == "approve_existing" for a in result["actions"]) == count
    run(env, "apply")
    with db.authority(env.path) as repo:
        for ident in previous:
            assert repo.head(ident)["status"] == "APPROVED"
            assert [r["status"] for r in repo.history(ident)["revisions"]] == ["PROPOSED", "APPROVED"]
            assert repo.head(ident)["provenance"]["method"] == "BATCH_DISCOVERY_V1"
    run(env, "revoke")
    with db.authority(env.path) as repo:
        for ident in previous:
            assert repo.head(ident)["status"] == "PROPOSED" and repo.head(ident)["revision"] == 3
            assert len(repo.history(ident)["revisions"]) == 3


def test_preapproved_exact_relations_reused_without_new_heads(env):
    previous = populate(env, status="APPROVED")
    before = state(env)
    result = run(env, "plan")
    assert all(a["action"] == "reuse" for a in result["actions"])
    run(env, "apply")
    assert state(env)["basis_head"] == before["basis_head"]
    assert state(env)["basis_revision"] == before["basis_revision"]
    assert {a["link_id"] for a in result["actions"]} == set(previous)


@pytest.mark.parametrize("status", ["REJECTED", "REVOKED"])
def test_rejected_and_revoked_are_not_revived(env, status):
    populate(env, count=1, status=status)
    before = state(env)
    with pytest.raises(BasisError, match="반려·취소"):
        run(env, "plan")
    assert state(env) == before


def test_multiple_exact_candidates_are_not_silently_merged(env):
    populate(env, count=1)
    resolved = fixed.resolve(env.store, WHO)
    with db.authority(env.path, write=True) as repo:
        Service(repo, SourcePort(env.store)).propose(resolved["principal"], {
            "request_id": "another-old-batch", "kind": "BASIS", "reason": "별도 후보",
            "internal": resolved["links"][0]["internal"], "external": resolved["links"][0]["external"]})
    with pytest.raises(BasisError, match="여러 건"):
        run(env, "plan")
    assert len(state(env)["basis_head"]) == 2


def test_other_external_paths_are_preserved(env):
    resolved = fixed.resolve(env.store, WHO)
    with db.authority(env.path, write=True) as repo:
        old = Service(repo, SourcePort(env.store)).propose(resolved["principal"], {
            "request_id": "other-external", "kind": "RELATED", "reason": "별도 외규 후보",
            "internal": resolved["links"][0]["internal"], "external": resolved["links"][2]["external"]})["link"]
    run(env, "plan")
    run(env, "apply")
    with db.authority(env.path) as repo:
        assert len(repo.links("risk_team")) == 5
        assert repo.head(old["link_id"]) == old


def test_new_candidate_between_plan_and_apply_rolls_back_all_rows(env):
    run(env, "plan")
    populate(env, count=1)
    before = state(env)
    with pytest.raises(sqlite3.IntegrityError):
        run(env, "apply")
    assert state(env) == before


def test_two_plans_cannot_commit_duplicate_fixed_links(env):
    run(env, "plan")
    other = env.root / "other-job"
    cli.execute("plan", env.store, WHO, env.context, other)
    run(env, "apply")
    before = state(env)
    with pytest.raises(sqlite3.IntegrityError):
        cli.execute("apply", env.store, WHO, env.context, other)
    assert state(env) == before


def test_failed_precommit_check_rolls_back_all_new_history(env):
    run(env, "plan")
    before = state(env)
    calls = []
    def changed():
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("selection changed before commit")
    with pytest.raises(ValueError, match="selection changed"):
        run(env, "apply", context_check=changed)
    assert state(env) == before


def test_actual_sql_failure_mid_transaction_rolls_back(env):
    run(env, "plan")
    script = (env.output / "APPEND_ONLY.sql").read_text().replace("COMMIT;", "INSERT INTO no_such_table VALUES(1);\nCOMMIT;")
    before = state(env)
    with db.authority(env.path, write=True) as repo, pytest.raises(sqlite3.OperationalError):
        db.execute_sql(repo, script, lambda: None)
    assert state(env) == before


def test_lost_local_receipt_recovers_from_db_without_reinsertion(env):
    run(env, "plan")
    run(env, "apply")
    (env.output / "receipt-apply.json").unlink()
    before = state(env)
    run(env, "verify")
    run(env, "apply")
    assert state(env) == before


@pytest.mark.parametrize("kind", ["sql", "plan", "principal", "context", "selection"])
def test_tamper_or_binding_change_prevents_write(env, kind, monkeypatch):
    run(env, "plan")
    before = state(env)
    if kind == "sql":
        path = env.output / "APPEND_ONLY.sql"
        path.write_text(path.read_text() + "-- edited\n")
    elif kind == "plan":
        value = plan_value(env)
        value["operation_id"] = "edited"
        (env.output / "plan.json").write_text(json.dumps(value))
    elif kind == "context":
        env.context = {**env.context, "fixture": "changed"}
    elif kind == "selection":
        monkeypatch.setattr(env.store.selection, "fingerprint", "changed")
    with pytest.raises((BasisError, ValueError)):
        if kind == "principal":
            cli.execute("apply", env.store, {**WHO, "user_id": "other"}, env.context, env.output)
        else:
            run(env, "apply")
    assert state(env) == before


def test_revert_refuses_later_user_review_and_preserves_every_row(env):
    run(env, "plan")
    run(env, "apply")
    value = plan_value(env)
    with db.authority(env.path, write=True) as repo:
        service = Service(repo, SourcePort(env.store))
        row = service.list(value["principal"])["items"][0]
        service.review(value["principal"], {"request_id": "later-user-review", "action": "reject",
            "reason": "후속 검토", "items": [{"link_id": row["link"]["link_id"], "revision": row["link"]["revision"],
                                             "view_hash": row["view_hash"]}]})
    before = state(env)
    with pytest.raises(sqlite3.IntegrityError):
        run(env, "revoke")
    assert state(env) == before


def test_missing_authority_never_creates_empty_database(tmp_path):
    path = tmp_path / "authority.sqlite"
    with pytest.raises(BasisError):
        with db.authority(path, write=True):
            pass
    assert not path.exists()


def test_existing_configuration_uses_same_generation_and_authority(env, monkeypatch):
    folder = env.root / "00_SYSTEM"
    folder.mkdir()
    (folder / "GENOS_SERVING_PATHS.json").write_text(json.dumps({
        "generation": str(PHOTO), "runtime": env.context["runtime"]}))
    monkeypatch.setattr(cli, "network_storage", lambda path: True)  # local fixture only
    selected = cli.settings(env.root)
    assert selected["authority"] == str(env.path)
    assert selected["generation"] == str(PHOTO)
    with cli.opened(env.root, WHO["user_id"]) as (store, who, context):
        assert context["authority"] == selected["authority"]
        assert fixed.resolve(store, who)["internal_document_id"] == "7a3907e193ec6c14"
    monkeypatch.setattr(cli, "network_storage", lambda path: False)
    with pytest.raises(BasisError, match="NFS"):
        cli.settings(env.root)


def test_shared_sqlite_api_and_rag_resolver_consume_committed_rows(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from semantic_runtime.basis_links.api import install
    run(env, "plan")
    run(env, "apply")
    value = plan_value(env)
    @contextmanager
    def factory():
        with db.authority(env.path, write=True) as repo:
            local = Store(PHOTO)
            try:
                yield Service(repo, SourcePort(local))
            finally:
                local.close()
    app = FastAPI()
    install(app, SimpleNamespace(), env.root, {"mode": "genos"},
            identity_resolver=lambda request: value["principal"], factory=factory)
    response = TestClient(app).get("/v1/basis-links", params={"internal_document_id": value["internal_document_id"]})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 4
    assert all(row["link"]["status"] == "APPROVED" for row in response.json()["items"])
    assert run(env, "verify")["external_endpoint_count"] == 7


def test_cli_reads_config_and_commits_to_same_sqlite(env, monkeypatch, capsys):
    folder = env.root / "00_SYSTEM"
    folder.mkdir()
    (folder / "GENOS_SERVING_PATHS.json").write_text(json.dumps({
        "generation": str(PHOTO), "runtime": env.context["runtime"]}))
    monkeypatch.setattr(cli, "network_storage", lambda path: True)  # local filesystem fixture
    source_before = fixed.binding(env.store)
    for action in ("inspect", "plan", "apply", "verify", "apply", "revoke", "verify-revoked"):
        assert cli.main([action, "--root", str(env.root), "--output", str(env.output),
                         "--operator", WHO["user_id"]]) == 0
    value = plan_value(env)
    assert value["context"]["authority"] == str(env.path)
    assert value["source_binding"]["backend"] == "sqlite"
    assert all(r["revision"] == 3 for r in state(env)["basis_head"])
    assert fixed.binding(env.store) == source_before
    assert "REVERT_VERIFIED" in capsys.readouterr().out
