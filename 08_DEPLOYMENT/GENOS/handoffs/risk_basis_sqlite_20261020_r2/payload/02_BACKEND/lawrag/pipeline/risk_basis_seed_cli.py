"""Append fixed risk links to basis_batch's existing shared SQLite authority."""
from contextlib import contextmanager
import argparse
import fcntl
import getpass
import hashlib
import json
from pathlib import Path
import sys
import time

from semantic_runtime.basis_links.contracts import require
from semantic_runtime.storage import Store
from semantic_runtime.team_scope import select_documents
from semantic_runtime.state_sqlite import network_storage
from .basis_batch import atomic
from . import risk_basis_seed as fixed
from . import risk_basis_sqlite as db


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings(root):
    path = Path(root).resolve() / "00_SYSTEM/GENOS_SERVING_PATHS.json"
    value = json.loads(path.read_text())
    generation, runtime = Path(value["generation"]), Path(value["runtime"])
    require(generation.is_absolute() and runtime.is_absolute(),
            "RISK_SQLITE_PATH", "기존 GENOS 설정의 절대 generation/runtime 경로가 필요합니다.")
    authority = runtime / "basis-links/authority.sqlite"
    marker = runtime / "basis-links/SQLITE_ENABLED.json"
    require(not any(p.is_symlink() for p in (path, *path.parents, marker, *marker.parents)),
            "RISK_SQLITE_PATH", "설정·관계 경로의 symlink는 허용하지 않습니다.")
    require(network_storage(runtime), "RISK_SQLITE_SHARED",
            "최근 배치와 같은 외부 NFS/CIFS runtime이어야 합니다.", 409)
    require(marker.is_file() and json.loads(marker.read_text()) ==
            {"schema_version": "basis-shared-sqlite-v1", "database": "authority.sqlite"},
            "RISK_SQLITE_MARKER", "최근 배치의 기존 SQLite 연결 설정이 필요합니다.", 409)
    require(authority.is_file(), "RISK_SQLITE_AUTHORITY", "기존 authority.sqlite가 없습니다. 새 DB로 대체하지 않습니다.", 409)
    return {"config": str(path), "config_sha256": file_sha(path), "generation": str(generation.resolve()),
            "runtime": str(runtime.resolve()), "authority": str(authority.resolve()),
            "marker_sha256": file_sha(marker)}


@contextmanager
def opened(root, operator):
    context = settings(root)
    store = Store(context["generation"])
    try:
        who = {"user_id": operator, "team_id": "risk_team", "basis_review": True,
               "document_ids": sorted(select_documents(store, "risk_team"))}
        yield store, who, context
    finally:
        store.close()


def event(output, status, **fields):
    with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": time.time(), "status": status, **fields}, ensure_ascii=False) + "\n")
        stream.flush()


def execute(action, store, who, context, output, *, context_check=lambda: None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".operation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            require(False, "RISK_SQLITE_BUSY", "같은 출력 폴더에서 실행 중입니다.", 409)
        event(output, "STARTED", action=action, authority=context["authority"])
        path = output / "plan.json"
        with db.authority(context["authority"]) as repo:
            if action in ("inspect", "plan"):
                atomic(output / "documents.json", fixed.inventory(store, who))
                atomic(output / "resolved.json", fixed.resolve(store, who))
            if action == "inspect":
                return {"status": "INSPECTED", "authority": context["authority"], "writes": 0}
            if action == "plan":
                if path.exists():
                    value = json.loads(path.read_text())
                    db.check_plan(value, store, who, context)
                    return {"status": "PLAN_REUSED", "plan_hash": value["plan_hash"], "writes": 0}
                value = db.make_plan(store, who, repo, context)
                for name, reverse in (("APPEND_ONLY.sql", False), ("REVERT_THIS_BATCH.sql", True)):
                    (output / name).write_text(db.sql(value, revert=reverse), encoding="utf-8")
                context_check()
                atomic(path, value)
                result = {"status": "PLAN_READY", "authority": context["authority"], "writes": 0,
                          "actions": [{"mapping": a["mapping"], "action": a["action"], "link_id": a["link_id"]}
                                      for a in value["actions"]], "plan_hash": value["plan_hash"]}
                atomic(output / "plan-summary.json", result)
                event(output, "PLAN_READY", plan_hash=value["plan_hash"])
                return result
            value = json.loads(path.read_text())
            db.check_plan(value, store, who, context)
            reverse = action in ("revoke", "verify-revoked")
            if action in ("verify", "verify-revoked"):
                result = db.verify(value, store, who, repo, context, reverted=reverse)
                atomic(output / ("receipt-" + action + ".json"), result)
                return result
        require(action in ("apply", "revoke"), "RISK_SQLITE_ACTION", "지원하지 않는 명령")
        script = db.sql(value, revert=reverse)
        sql_path = output / ("REVERT_THIS_BATCH.sql" if reverse else "APPEND_ONLY.sql")
        require(sql_path.read_text() == script, "RISK_SQLITE_SQL_HASH", "출력 SQL이 계획과 다릅니다.", 409)
        def before_commit():
            context_check()
            db.check_plan(value, store, who, context)
        with db.authority(context["authority"], write=True) as repo:
            before_commit()
            event(output, "WRITE_INTENT", action=action, plan_hash=value["plan_hash"])
            db.execute_sql(repo, script, before_commit)
            result = db.verify(value, store, who, repo, context, reverted=reverse)
        atomic(output / ("receipt-" + action + ".json"), result)
        event(output, result["status"], action=action, plan_hash=value["plan_hash"])
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "plan", "apply", "verify", "revoke", "verify-revoked"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator", default=getpass.getuser())
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        with opened(args.root, args.operator) as (store, who, context):
            def check():
                require(settings(args.root) == context, "RISK_SQLITE_CONTEXT", "설정 또는 저장 경로가 변경됐습니다.", 409)
            result = execute(args.action, store, who, context, args.output, context_check=check)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        import traceback
        record = {"status": "FAILED_OR_UNCONFIRMED", "action": args.action,
                  "error_type": type(exc).__name__, "code": getattr(exc, "code", None), "message": str(exc),
                  "trace": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                            for f in traceback.extract_tb(exc.__traceback__)],
                  "next": "쓰기 결과가 불명확하면 같은 plan.json의 verify로 확인. 계획·이력은 보존."}
        atomic(args.output / ("failure-" + str(time.time_ns()) + ".json"), record)
        event(args.output, "FAILED_OR_UNCONFIRMED", action=args.action, error_type=type(exc).__name__)
        print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
