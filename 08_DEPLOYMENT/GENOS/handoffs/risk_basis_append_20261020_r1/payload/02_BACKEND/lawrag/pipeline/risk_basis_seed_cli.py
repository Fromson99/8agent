"""GENOS/Dataiku batch entry for the four fixed risk-rule connections."""
from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import time

from semantic_runtime.basis_links.contracts import require, digest
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.oracle_dp_io import SQL, atomic_json
from . import risk_basis_seed as seed
from . import risk_basis_sql as db


@contextmanager
def opened(config, output, local_generation=None):
    """Reuse exactly the GENOS query release/channel and RAG visibility rules."""
    if local_generation:
        from semantic_runtime.storage import Store
        store = Store(local_generation)
        try:
            yield store, None
        finally:
            store.close()
        return
    if config.get("backend", "genos") == "dataiku":
        import dataiku
        from .oracle_query_dataiku import DataikuClient
        name = config["dataiku_connection"]
        client = DataikuClient(dataiku.SQLExecutor2(connection=name), name, dataiku.default_project_key())
        connection_binding, _ = client.identity()
    else:
        from semantic_runtime.oracle_dp import client_from_environment
        from semantic_runtime.oracle_query_service import environment_binding
        client = client_from_environment()
        connection_binding = environment_binding()
    # A batch journal is an operator artifact, not a serving source cache.
    sql = SQL(client, journal=output / "sql-events.jsonl", binding=connection_binding,
              max_calls=config.get("max_sql_calls", 10000), seconds=config.get("seconds", 1800))
    # Retain the first deadline on resume. A new invocation is not a fresh budget.
    state_path = output / "budget.json"
    limits = {"max_calls": sql.max_calls, "seconds": config.get("seconds", 1800)}
    if state_path.exists():
        old = json.loads(state_path.read_text())
        require(old["connection_binding"] == connection_binding and old["limits"] == limits,
                "RISK_SEED_RESUME", "접속 대상/예산이 이전 실행과 다릅니다.", 409)
        deadline = old["deadline_at"]
    else:
        deadline = time.time() + limits["seconds"]
        atomic_json(state_path, {"connection_binding": connection_binding, "limits": limits,
                                 "deadline_at": deadline})
    sql.deadline = time.monotonic() + max(0, deadline - time.time())
    from semantic_runtime.oracle_query_catalog import select_release
    from semantic_runtime.oracle_query import Snapshot
    from semantic_runtime.oracle_query_request import _request
    from semantic_runtime.oracle_query_store import Store
    release = config.get("query_release_id") or os.environ.get("DP_QUERY_RELEASE_ID", "").strip() or None
    channel = config.get("query_channel") or os.environ.get("DP_QUERY_CHANNEL", "").strip() or (None if release else "main")
    selected = select_release(sql, release_id=release, channel=channel)
    manifest = selected["manifest"]
    source = Snapshot.open(sql, manifest["source_release_id"])
    require(manifest["dataset_version"] == source.dataset_version and manifest["source_manifest"] == source.manifest,
            "RISK_SEED_SOURCE_BINDING", "Oracle 원문·조회 릴리스가 일치하지 않습니다.", 409)
    allowed = set(source.manifest["scope"]["document_version_ids"]) - source.excluded
    store = Store(_request(sql, selected["release_id"], selected["revision"], source, manifest, allowed))
    store._risk_seed_channel = channel
    try:
        store.selection.require_latest()
        yield store, sql
    finally:
        store.close()


def verify(value, store, who, reader, *, revoked=False):
    seed.check_plan(value, store, who)
    checked_rows = None
    if isinstance(reader, db.OracleReader):
        operation = value["operation_id"] + (":revoke" if revoked else "")
        receipt = reader.batch_receipt(operation)
        require(receipt == {"plan_hash": value["plan_hash"], "operation_id": value["operation_id"],
                            "new_link_ids": value["new_link_ids"], "action": "revoke" if revoked else "append"},
                "RISK_SEED_RECEIPT", "배치 commit receipt가 없습니다. 원본 계획과 SQL 이벤트를 확인하십시오.", 409)
        expected = json.loads(json.dumps(value["rows"]))
        if revoked:
            for table, rows in value["rollback_rows"].items():
                if table == "basis_head":
                    expected[table] = rows
                else:
                    expected[table].extend(rows)
        checked_rows = reader.verify_rows(expected)
    states = []
    for ident in value["new_link_ids"]:
        link = reader.head(ident)
        require(link is not None and link["status"] == ("REVOKED" if revoked else "APPROVED"),
                "RISK_SEED_VERIFY", "연결 상태가 예상과 다릅니다.", 409)
        require(link["revision"] == (3 if revoked else 2) and link["team_id"] == who["team_id"],
                "RISK_SEED_VERIFY", "연결 revision/팀이 변경됐습니다.", 409)
        stored = reader.binding(ident, link["revision"], store.manifest["generation_id"])
        require(stored is not None, "RISK_SEED_VERIFY", "현재 세대 연결 위치가 없습니다.", 409)
        source = SourcePort(store)
        for end in stored["internal"] + stored["external"]:
            source.verify(end, value["principal"])
        states.append({"link_id": ident, "revision": link["revision"], "status": link["status"]})
    if revoked:
        return {"status": "REVOKED_VERIFIED", "links": states, "lifecycle_rows_verified": checked_rows}
    service = Service(reader, SourcePort(store))
    snap = snapshot(service, value["principal"], [value["internal_document_id"]])
    wanted = set(value["new_link_ids"] + value["reused_link_ids"])
    snap["items"] = [x for x in snap["items"] if x["link"]["link_id"] in wanted]
    snap["snapshot_hash"] = digest({k: v for k, v in snap.items() if k != "snapshot_hash"})
    selected = targets(service, value["principal"], snap)
    expected = {e["endpoint_hash"] for row in value["resolved"] for e in row["external"]}
    require({r["endpoint"]["endpoint_hash"] for r in selected} == expected,
            "RISK_SEED_RESOLVER", "DB 연결의 외규 회수 범위가 다릅니다.", 409)
    return {"status": "APPEND_VERIFIED", "links": states, "resolver_endpoint_count": len(selected),
            "lifecycle_rows_verified": checked_rows,
            "rag_factory_deployment_verified": False, "index_rebuild": False}


def execute(action, config, output, *, local_generation=None, plan_file=None):
    import fcntl
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".operation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            require(False, "RISK_SEED_BUSY", "같은 작업 폴더의 실행이 진행 중입니다.", 409)
        return _execute(action, config, output, local_generation=local_generation, plan_file=plan_file)


def _execute(action, config, output, *, local_generation=None, plan_file=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    mapping = db.tables(config.get("table_map", db.DEFAULT_TABLES))
    who = config["principal"]
    # This configuration belongs to the authenticated batch operator, not a chat request.
    from semantic_runtime.basis_links.contracts import principal
    principal(who, review=True)
    require(who["user_id"] != "SET_OPERATOR_ID", "RISK_SEED_OPERATOR",
            "config.json의 principal.user_id에 현장 실행자 ID를 지정하십시오.", 403)
    if action == "schema":
        path = output / "OPTIONAL_BASIS_SCHEMA.sql"
        path.write_text(db.schema_sql(mapping), encoding="utf-8")
        return {"status": "DDL_EXPORTED_NOT_EXECUTED", "file": str(path)}
    with opened(config, output, local_generation) as (store, sql):
        if action in ("inspect", "plan"):
            report = seed.inventory(store, who)
            atomic_json(output / "documents.json", report)
            # Missing/ambiguous targets preserve the inventory and perform no writes.
            resolved = seed.resolve(store, who)
            atomic_json(output / "resolved.json", resolved)
        if action == "inspect":
            return {"status": "RESOLVED", "internal_document_id": resolved["internal_document_id"],
                    "links": len(resolved["links"]), "binding": report["binding"]}
        if action == "plan":
            target = output / "plan.json"
            if target.exists():
                value = json.loads(target.read_text())
                seed.check_plan(value, store, who)
                require(value["table_map"] == mapping, "RISK_SEED_RESUME", "테이블 맵이 변경됐습니다.", 409)
                return {"status": "PLAN_REUSED", "plan_hash": value["plan_hash"], "database_writes": 0}
            require(sql is not None, "RISK_SEED_ORACLE_ONLY", "현장용 SQL 계획은 실제 Oracle 원문에서 생성합니다.")
            schema = db.check_schema(sql, mapping)
            atomic_json(output / "schema-check.json", schema)
            reader = db.OracleReader(sql, mapping)
            value = seed.plan(store, who, batch_id=config["batch_id"], existing=reader.links(who["team_id"]))
            old = reader.batch_receipt(value["operation_id"])
            require(old is None, "RISK_SEED_EXISTING_BATCH", "이미 적용한 배치입니다. 기존 plan.json으로 verify 하십시오.", 409)
            value = db.seal(value, mapping, db.source_guards(store, value), store.oracle_request.records.manifest)
            # Build all scripts before atomically publishing the plan.
            append = db.transaction(value)
            rollback = db.transaction(value, revoke=True)
            atomic_json(output / "append.binds.json", append["binds"])
            (output / "append.statement.sql").write_text(append["statement"], encoding="utf-8")
            (output / "APPEND_ONLY.sql").write_text(append["standalone"], encoding="utf-8")
            (output / "REVOKE_THIS_BATCH.sql").write_text(rollback["standalone"], encoding="utf-8")
            atomic_json(target, value)
            return {"status": "PLAN_READY", "plan_hash": value["plan_hash"],
                    "new_links": len(value["new_link_ids"]), "reused_links": len(value["reused_link_ids"]),
                    "database_writes": 0, "sql_file": str(output / "APPEND_ONLY.sql")}
        require(action in ("apply", "verify", "revoke", "verify-revoked"), "RISK_SEED_ACTION", "지원하지 않는 명령")
        require(sql is not None, "RISK_SEED_ORACLE_ONLY", "Oracle 실행만 지원합니다.")
        value = json.loads(Path(plan_file or output / "plan.json").read_text())
        seed.check_plan(value, store, who)
        require(value["table_map"] == mapping, "RISK_SEED_TABLES", "계획과 실행 테이블 맵이 다릅니다.", 409)
        db.check_schema(sql, mapping)
        reader = db.OracleReader(sql, mapping)
        if action in ("apply", "revoke"):
            operation = value["operation_id"] + (":revoke" if action == "revoke" else "")
            previous = reader.batch_receipt(operation)
            if previous is not None:
                result = verify(value, store, who, reader, revoked=action == "revoke")
                result["reconciled_without_write"] = True
                atomic_json(output / ("receipt-" + action + ".json"), result)
                return result
            compiled = db.transaction(value, revoke=action == "revoke")
            # Exactly one physical mutation. Failure/unknown outcome is retained;
            # verify before any repeat; exact SQL is idempotent.
            atomic_json(output / ("intent-" + action + "-" + str(time.time_ns()) + ".json"), {"plan_hash": value["plan_hash"],
                        "statement_hash": digest(compiled["statement"]), "status": "STARTED"})
            sql.request(compiled["statement"], compiled["binds"], write=True)
        result = verify(value, store, who, reader, revoked=action in ("revoke", "verify-revoked"))
        atomic_json(output / ("receipt-" + action + ".json"), result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("schema", "inspect", "plan", "apply", "verify", "revoke", "verify-revoked"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--local-generation", type=Path, help="Read-only local inspect; Oracle DML unavailable")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    try:
        result = execute(args.action, config, args.output, local_generation=args.local_generation, plan_file=args.plan_file)
    except Exception as exc:
        # Do not print database credentials or SQL/CLOB bodies from driver errors.
        record = {"status": "FAILED_OR_UNCONFIRMED", "action": args.action,
                  "error_type": type(exc).__name__, "error_code": getattr(exc, "code", None),
                  "message": str(exc) if hasattr(exc, "code") else "저장된 SQL 상태·현장 로그 확인 필요",
                  "next": "쓰기 요청 실패이면 같은 계획의 verify로 확인; 원본 계획과 SQL 이벤트 보존"}
        import traceback
        record["trace"] = [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                           for frame in traceback.extract_tb(exc.__traceback__)]
        atomic_json(args.output / ("failure-" + args.action + "-" + str(time.time_ns()) + ".json"), record)
        print(json.dumps(record, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
