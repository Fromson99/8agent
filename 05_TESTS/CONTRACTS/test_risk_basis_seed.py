"""Fixed-link append contracts: real selected photo originals, no model calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from lawrag.pipeline import risk_basis_seed as seed
from lawrag.pipeline import risk_basis_sql as sql
from lawrag.pipeline.risk_basis_sql import verify
from semantic_runtime.basis_links.contracts import BasisError, digest
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.storage import Store

ROOT = Path(__file__).resolve().parents[2]
PHOTO = ROOT / "01_DATA/TERM_RELEASES/risk-photo-0951-r2/named-documents/generation"
WHO = {"user_id": "contract-operator", "team_id": "risk_team", "document_ids": [], "basis_review": True}


@pytest.fixture
def store():
    if not PHOTO.exists():
        pytest.skip("fixed photo source fixture not installed")
    value = Store(PHOTO)
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def planned(store):
    return seed.plan(store, WHO, batch_id="contract")


def install_memory(repo, rows):
    with repo.transaction():
        for table, values in rows.items():
            for row in values:
                columns = list(row)
                repo.db.execute("INSERT INTO " + table + " (" + ",".join(columns) + ") VALUES (" +
                                ",".join("?" for _ in columns) + ")", tuple(row[c] for c in columns))


def oracle_fixture(value):
    """Synthetic Oracle publication pin solely for generated-SQL contract tests."""
    value = deepcopy(value)
    manifest = {"schema_version": "oracle-query-test-only", "status": "COMPLETE"}
    value["source_binding"].update(backend="oracle", query_release_id=digest(manifest),
                                  query_channel="contract", query_pointer_revision=2)
    guards = [{"table": "SIDDA.LEGAL_SRC_DOCUMENT_A", "kind": "document",
               "row": {"DATASET_VERSION": "a"*64, "DOCUMENT_ID": "test-only",
                       "NAME": "실제 아님 O'Hara & 예시", "SOURCE_ARTIFACT_SHA256": "b"*64,
                       "SOURCE_JSON": "{}"}}]
    return sql.seal(value, sql.DEFAULT_TABLES, guards, manifest)


def test_existing_selected_photo_resolves_only_four_reviewed_links(store, planned):
    assert len(planned["resolved"]) == 4
    assert len(planned["new_link_ids"]) == 4
    assert planned["resolver_endpoint_count"] == 7
    assert len({e["document_id"] for l in planned["resolved"] for e in l["internal"]}) == 1
    assert sum(len(l["external"]) for l in planned["resolved"]) == 8
    assert not planned["index_rebuild"] and not planned["legal_quality_certified"]
    assert seed.check_plan(planned, store, WHO)["internal_document_id"] == planned["internal_document_id"]


def test_real_source_plan_rows_are_consumed_by_existing_service_and_resolver(store, planned):
    repo = seed.memory_repository()
    try:
        install_memory(repo, planned["rows"])
        result = verify(planned, store, WHO, repo)
        assert result["status"] == "APPEND_VERIFIED"
        assert result["resolver_endpoint_count"] == 7
        histories = [repo.history(i) for i in planned["new_link_ids"]]
        assert all([r["status"] for r in h["revisions"]] == ["PROPOSED", "APPROVED"] for h in histories)
        assert all(h["events"][0].get("actor") == WHO["user_id"] for h in histories)
    finally:
        repo.close()


def test_real_basis_api_lists_imported_rows_and_rejects_stale_review(store, planned, tmp_path):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from semantic_runtime.basis_links.api import install
    repo = seed.memory_repository()
    install_memory(repo, planned["rows"])
    @contextmanager
    def factory():
        thread_store = Store(PHOTO)
        thread_repo = seed.memory_repository()
        install_memory(thread_repo, planned["rows"])
        try:
            yield Service(thread_repo, SourcePort(thread_store))
        finally:
            thread_repo.close()
            thread_store.close()
    app = FastAPI()
    install(app, SimpleNamespace(), tmp_path, {"mode": "oracle-query"},
            identity_resolver=lambda request: planned["principal"], factory=factory)
    try:
        client = TestClient(app)
        response = client.get("/v1/basis-links", params={"internal_document_id": planned["internal_document_id"]})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 4
        assert all(r["link"]["status"] == "APPROVED" for r in response.json()["items"])
        row = response.json()["items"][0]
        failed = client.post("/v1/basis-links/reviews", json={
            "request_id": "stale-contract", "action": "revoke", "reason": "test stale",
            "items": [{"link_id": row["link"]["link_id"], "revision": 1, "view_hash": row["view_hash"]}]})
        assert failed.status_code == 200 and failed.json()["status"] == "partial"
        assert failed.json()["items"][0]["error_code"] == "BASIS_STALE_VIEW"
        assert repo.head(row["link"]["link_id"])["status"] == "APPROVED"
    finally:
        repo.close()


def test_same_mapping_different_batch_labels_have_same_operation_guard(store, planned):
    other = seed.plan(store, WHO, batch_id="another-operator-label")
    assert other["operation_id"] == planned["operation_id"]
    assert other["new_link_ids"] != planned["new_link_ids"]


def test_existing_approved_link_is_reused_and_not_reapproved(store, planned):
    existing = [json.loads(r["payload"]) for r in planned["rows"]["basis_revision"] if r["revision"] == 2]
    result = seed.plan(store, WHO, batch_id="reuse", existing=existing)
    assert result["new_link_ids"] == []
    assert set(result["reused_link_ids"]) == set(planned["new_link_ids"])
    assert all(not v for v in result["rows"].values())
    compiled = sql.transaction(oracle_fixture(result))
    assert len(result["reused_link_pins"]) == 4
    assert compiled["statement"].count("'RISK_SEED_REUSED_CHANGED'") == 8
    assert compiled["statement"].count("FOR UPDATE WAIT 5") == 5


@pytest.mark.parametrize("status", ["REVOKED", "REJECTED", "PROPOSED"])
def test_existing_rejected_or_unapproved_is_not_resurrected(store, planned, status):
    old = json.loads(planned["rows"]["basis_revision"][1]["payload"])
    old["status"] = status
    with pytest.raises(BasisError, match="자동 변경"):
        seed.plan(store, WHO, batch_id="conflict", existing=[old])


def test_missing_document_does_not_guess_another_rule(store, monkeypatch):
    original = seed.inventory
    def filtered(*a):
        report = original(*a)
        report["documents"] = [d for d in report["documents"] if d["side"] != "internal"]
        return report
    monkeypatch.setattr(seed, "inventory", filtered)
    with pytest.raises(BasisError) as error:
        seed.resolve(store, WHO)
    assert error.value.code == "RISK_SEED_MISSING"


def test_multiple_visible_versions_stop_without_max_date_choice(store, monkeypatch):
    original = seed.inventory
    def duplicate(*a):
        report = original(*a)
        internal = next(d for d in report["documents"] if d["side"] == "internal")
        report["documents"].append({**internal, "document_id": "another-version"})
        return report
    monkeypatch.setattr(seed, "inventory", duplicate)
    with pytest.raises(BasisError) as error:
        seed.resolve(store, WHO)
    assert error.value.code == "RISK_SEED_AMBIGUOUS"


def test_rag_latest_selection_is_required(store, monkeypatch):
    monkeypatch.setattr(store.selection, "require_latest", lambda: (_ for _ in ()).throw(ValueError("latest missing")))
    with pytest.raises(ValueError, match="latest missing"):
        seed.resolve(store, WHO)


def test_narrowed_authorized_document_scope_cannot_pick_external_or_internal(store):
    who = {**WHO, "document_ids": ["c9b5b42627710637"]}
    with pytest.raises(BasisError) as error:
        seed.resolve(store, who)
    assert error.value.code == "RISK_SEED_MISSING"


def test_no_review_authority_prevents_plan(store):
    with pytest.raises(BasisError) as error:
        seed.plan(store, {**WHO, "basis_review": False}, batch_id="denied")
    assert error.value.code == "BASIS_REVIEW_DENIED"


def test_content_anchor_change_does_not_silently_link(store, monkeypatch):
    original = SourcePort.endpoint
    def changed(self, selection, who, side):
        end = original(self, selection, who, side)
        if side == "internal" and end["unit_id"] == "42":
            for span in end["spans"]:
                span["text"] = span["text"].replace("1,000%", "2,000%")
        return end
    monkeypatch.setattr(SourcePort, "endpoint", changed)
    with pytest.raises(BasisError) as error:
        seed.resolve(store, WHO)
    assert error.value.code == "RISK_SEED_CONTENT_CHANGED"


def test_plan_tamper_principal_or_selection_change_rejected(store, planned, monkeypatch):
    changed = deepcopy(planned)
    changed["new_link_ids"] = []
    with pytest.raises(BasisError) as error:
        seed.check_plan(changed, store, WHO)
    assert error.value.code == "RISK_SEED_PLAN_HASH"
    with pytest.raises(BasisError):
        seed.check_plan(planned, store, {**WHO, "user_id": "other"})
    monkeypatch.setattr(store.selection, "fingerprint", "changed")
    with pytest.raises(ValueError, match="source generation changed"):
        seed.check_plan(planned, store, WHO)


def test_rollback_appends_revision_and_preserves_prior_history(store, planned):
    repo = seed.memory_repository()
    try:
        install_memory(repo, planned["rows"])
        with repo.transaction():
            for row in planned["rollback_rows"]["basis_head"]:
                repo.db.execute("UPDATE basis_head SET revision=? WHERE link_id=? AND revision=?",
                                (row["revision"], row["link_id"], row["revision"]-1))
        install_memory(repo, {k: v if k != "basis_head" else [] for k, v in planned["rollback_rows"].items()})
        assert verify(planned, store, WHO, repo, revoked=True)["status"] == "REVOKED_VERIFIED"
        assert all(len(repo.history(i)["revisions"]) == 3 for i in planned["new_link_ids"])
    finally:
        repo.close()


def test_exported_sql_is_additive_idempotent_and_carries_source_and_filter_guards(planned):
    value = oracle_fixture(planned)
    compiled = sql.transaction(value)
    text = compiled["statement"]
    assert "DELETE " not in text and "TRUNCATE " not in text
    assert "UPDATE " not in text.replace("FOR UPDATE WAIT 5", "")
    assert "FOR UPDATE WAIT 5" in text
    assert "RISK_SEED_SELECTION_CHANGED" in text and "RISK_SEED_SOURCE_CHANGED" in text
    assert "RISK_SEED_ROW_CONFLICT" in text and "RISK_SEED_BATCH_CONFLICT" in text
    assert text.endswith("COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;")
    assert "IF n=0 THEN INSERT" in text
    standalone = compiled["standalone"]
    assert "O''Hara &" in standalone and "SET DEFINE OFF" in standalone
    assert ":v1" not in standalone
    for table in ("LEGAL_SRC_DOCUMENT_A", "LEGAL_QUERY_ROW_A", "LEGAL_QUERY_ACTIVE_A"):
        assert not re_search_write(standalone, table)


def re_search_write(text, table):
    import re
    return re.search(r"(?:INSERT INTO|UPDATE|DELETE FROM)\s+\w+\." + table, text)


def test_sql_revoke_uses_revision_cas_without_deletion(planned):
    compiled = sql.transaction(oracle_fixture(planned), revoke=True)
    assert "UPDATE SIDDA.LEGAL_BASIS_HEAD_A SET REVISION=" in compiled["statement"]
    assert "AND REVISION=" in compiled["statement"]
    assert "DELETE" not in compiled["statement"]


def test_local_only_plan_cannot_be_exported_as_real_oracle_update(planned):
    value = oracle_fixture(planned)
    value["source_binding"]["backend"] = "sqlite-local-validation"
    value["plan_hash"] = digest({k: v for k, v in value.items() if k != "plan_hash"})
    with pytest.raises(BasisError) as error:
        sql.transaction(value)
    assert error.value.code == "RISK_SEED_ORACLE_ONLY"


def test_oracle_reader_contract_with_existing_lifecycle_payloads(store, planned):
    """SQL read boundary double; not an Oracle engine certification."""
    import re
    repo = seed.memory_repository()
    install_memory(repo, planned["rows"])
    repo.db.create_function("TO_CLOB", 1, lambda x: x)
    repo.db.create_function("LOB_LENGTH", 1, lambda x: len(x.encode("utf-16-le"))//2)
    class ReaderBoundary:
        def query(self, statement, binds=(), limit=100):
            for logical, actual in sql.DEFAULT_TABLES.items():
                statement = statement.replace(actual, logical)
            statement = statement.replace("DBMS_LOB.GETLENGTH", "LOB_LENGTH")
            statement = re.sub(r"FETCH FIRST (\d+) ROWS ONLY", r"LIMIT \1", statement)
            values = {name: value for name, value, _ in binds}
            result = repo.db.execute(statement, values)
            return [{k.upper(): v for k, v in dict(row).items()} for row in result]
    reader = sql.OracleReader(ReaderBoundary(), sql.DEFAULT_TABLES)
    try:
        assert len(reader.links("risk_team")) == 4
        assert reader.verify_rows(planned["rows"]) == sum(map(len, planned["rows"].values()))
        service = Service(reader, SourcePort(store))
        from semantic_runtime.basis_links.resolver import snapshot, targets
        graph = snapshot(service, planned["principal"], [planned["internal_document_id"]])
        assert len(targets(service, planned["principal"], graph)) == 7
        ident = planned["new_link_ids"][0]
        repo.db.execute("UPDATE basis_revision SET payload='{}' WHERE link_id=? AND revision=2", (ident,))
        with pytest.raises(BasisError) as error:
            reader.head(ident)
        assert error.value.code == "BASIS_INTEGRITY"
    finally:
        repo.close()


@pytest.mark.parametrize("replacement", ["SIDDA.LEGAL_SRC_DOCUMENT_A", "SIDDA.LEGAL_QUERY_ROW_A", "A.B;DROP TABLE X"])
def test_table_map_cannot_target_source_index_or_inject_sql(replacement):
    value = dict(sql.DEFAULT_TABLES)
    value["basis_head"] = replacement
    with pytest.raises(BasisError):
        sql.tables(value)
