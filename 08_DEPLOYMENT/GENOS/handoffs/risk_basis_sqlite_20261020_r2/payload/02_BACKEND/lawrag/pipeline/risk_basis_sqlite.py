"""Four fixed risk links in the SAME SQLite authority used by basis_batch."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from semantic_runtime.basis_links.contracts import digest, require, principal, encoded
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.integration import selection
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.state_sqlite import readonly, connect
from . import risk_basis_seed as fixed

SCHEMA = "risk-basis-shared-sqlite-v2"
TABLES = ("basis_head", "basis_revision", "basis_binding", "basis_event", "basis_receipt",
          "basis_lineage", "basis_migration", "basis_view_head", "basis_document_lookup")
KEYS = {"basis_head": ("link_id",), "basis_revision": ("link_id", "revision"),
        "basis_binding": ("binding_id",), "basis_event": ("event_id",),
        "basis_receipt": ("receipt_id",), "basis_lineage": ("version_id",),
        "basis_migration": ("migration_id",), "basis_view_head": ("session_key",),
        "basis_document_lookup": ("document_id", "link_id")}


def key(link):
    return digest({side: sorted(digest(selection(e)) for e in link[side])
                   for side in ("internal", "external")})


@contextmanager
def authority(path, *, write=False):
    """Never initialize an empty DB or copy/rebuild the corpus."""
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            "RISK_SQLITE_AUTHORITY", "최근 배치와 같은 기존 authority.sqlite가 필요합니다.", 409)
    repo = object.__new__(Repository)
    repo.db = connect(path) if write else readonly(path)
    repo.db.row_factory = sqlite3.Row
    repo.sqlite_document_lookup = True
    try:
        names = {r[0] for r in repo.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(set(TABLES) <= names and "basis_lookup_version" in names,
                "RISK_SQLITE_SCHEMA", "최근 내규 배치의 관계 원장 스키마가 필요합니다.", 409)
        require(repo.db.execute("SELECT 1 FROM basis_lookup_version WHERE version=1").fetchone(),
                "RISK_SQLITE_SCHEMA", "관계 조회 색인 버전이 다릅니다.", 409)
        yield repo
    finally:
        repo.close()


def cohort(repo, team, did):
    return [dict(r) for r in repo.db.execute(
        "SELECT h.link_id,h.team_id,h.revision,r.hash FROM basis_head h "
        "JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision "
        "JOIN basis_document_lookup d ON d.link_id=h.link_id "
        "WHERE h.team_id=? AND d.document_id=? ORDER BY h.link_id", (team, did))]


def _rows(repo):
    return {t: [dict(r) for r in repo.db.execute("SELECT * FROM " + t)] for t in TABLES}


def _delta(before, after):
    return {t: [r for r in after[t] if r not in before[t]] for t in TABLES}


def _copy_link(source, stage, ident):
    # Only matched relation histories, not the whole authority/source DB.
    for table in ("basis_head", "basis_revision", "basis_binding", "basis_event", "basis_document_lookup"):
        for row in source.db.execute("SELECT * FROM " + table + " WHERE link_id=?", (ident,)):
            row = dict(row)
            stage.db.execute("INSERT INTO " + table + " (" + ",".join(row) + ") VALUES (" +
                             ",".join("?" for _ in row) + ")", tuple(row.values()))


def make_plan(store, who, repo, context):
    principal(who, review=True)
    selected = fixed.resolve(store, who)
    did = selected["internal_document_id"]
    metadata = json.loads(store.db.execute("SELECT json FROM document WHERE document_id=?", (did,)).fetchone()[0])
    require(metadata.get("document_metadata", {}).get("is_latest") is True,
            "RISK_SQLITE_LATEST", "최근 배치의 최신 내규 조건을 통과해야 합니다.", 409)
    scoped = selected["principal"]
    require(not getattr(store, "is_oracle_query", False), "RISK_SQLITE_ONLY", "SQLite 원문 세대만 지원합니다.")
    operation = digest([SCHEMA, who["team_id"], selected["inventory"]["binding"], context])
    require(repo.receipt("risk-sqlite:" + operation, operation) is None,
            "RISK_SQLITE_EXISTING_PLAN", "이미 적용한 묶음입니다. 원래 plan.json으로 verify 하십시오.", 409)
    original_cohort = cohort(repo, who["team_id"], did)
    views = Service(repo, SourcePort(store)).list(scoped, did)["items"]
    stage = fixed.memory_repository()
    stage.sqlite_document_lookup = True
    actions = []
    try:
        for mapping in selected["links"]:
            matched = [v for v in views if v["link"]["kind"] == "BASIS"
                       and v["link"].get("perspective", "CURRENT_BASIS") == "CURRENT_BASIS"
                       and key(v["binding"] or v["link"]) == key(mapping)]
            require(len(matched) <= 1, "RISK_SQLITE_DUPLICATES",
                    mapping["key"] + ": 이미 같은 관계가 여러 건입니다. 자동 병합하지 않습니다.", 409)
            item = matched[0] if matched else None
            if item:
                old = item["link"]
                require(old["status"] in ("APPROVED", "PROPOSED"), "RISK_SQLITE_REVIEW_CONFLICT",
                        "반려·취소한 동일 관계는 자동 복구하지 않습니다: " + old["link_id"], 409)
                require(item["binding"] and item["binding"]["status"] == "current",
                        "RISK_SQLITE_BINDING", "기존 관계의 현재 판본 위치 확인이 필요합니다.", 409)
                for side in ("internal", "external"):
                    for end in item["binding"][side]:
                        SourcePort(store).verify(end, scoped)
                _copy_link(repo, stage, old["link_id"])
                actions.append({"mapping": mapping["key"], "action": "reuse" if old["status"] == "APPROVED" else "approve_existing",
                                "link_id": old["link_id"], "before": deepcopy(old), "view_hash": item["view_hash"]})
            else:
                actions.append({"mapping": mapping["key"], "action": "create"})
        before = _rows(stage)
        service = Service(stage, SourcePort(store))
        for action, mapping in zip(actions, selected["links"]):
            if action["action"] == "reuse":
                continue
            request = "risk-sqlite:" + operation + ":" + mapping["key"]
            if action["action"] == "create":
                row = service.propose(scoped, {
                    "request_id": request, "internal": mapping["internal"], "external": mapping["external"],
                    "kind": "BASIS", "reason": "사용자가 지정한 위험관리기준시행세칙의 검토 연결 4건 중 하나",
                    "provenance": {"type": "USER_SELECTION", "policy": fixed.POLICY,
                                   "explicit_reference_visible": mapping["explicit_reference"],
                                   "legal_quality_certified": False}})
                action["link_id"], revision, view = row["link"]["link_id"], 1, row["view_hash"]
            else:
                revision, view = action["before"]["revision"], action["view_hash"]
            result = service.review(scoped, {
                "request_id": request + ":approve", "action": "approve",
                "reason": "사용자 지정 4건 연결 승인; 기존 발견 및 revision 이력 보존",
                "items": [{"link_id": action["link_id"], "revision": revision, "view_hash": view}]})
            require(result["status"] == "completed", "RISK_SQLITE_STAGE", "승인 행 조립 실패", 409)
        applied = _rows(stage)
        for action in actions:
            action["after"] = stage.head(action["link_id"])
        for action in actions:
            if action["action"] == "reuse":
                continue
            view = next(v for v in service.list(scoped)["items"] if v["link"]["link_id"] == action["link_id"])
            req = "risk-sqlite:" + operation + ":revert:" + action["mapping"]
            if action["action"] == "create":
                result = service.review(scoped, {"request_id": req, "action": "revoke", "reason": "이번 신규 연결만 취소",
                    "items": [{"link_id": action["link_id"], "revision": view["link"]["revision"], "view_hash": view["view_hash"]}]})
                require(result["status"] == "completed", "RISK_SQLITE_STAGE", "취소 행 조립 실패", 409)
            else:
                old = action["before"]
                service.propose(scoped, {"request_id": req, "link_id": old["link_id"],
                    "expected_revision": view["link"]["revision"], "view_hash": view["view_hash"],
                    "internal": [selection(e) for e in view["binding"]["internal"]],
                    "external": [selection(e) for e in view["binding"]["external"]],
                    "kind": old["kind"], "perspective": old.get("perspective", "CURRENT_BASIS"),
                    "reason": old["reason"], "provenance": old["provenance"]})
            action["reverted"] = stage.head(action["link_id"])
        require(cohort(repo, who["team_id"], did) == original_cohort,
                "RISK_SQLITE_CHANGED", "계획 중 기존 관계가 바뀌었습니다. 새 계획이 필요합니다.", 409)
        value = {"schema": SCHEMA, "operation_id": operation, "source_binding": selected["inventory"]["binding"],
                 "context": context, "principal": scoped, "internal_document_id": did,
                 "resolved": selected["links"], "cohort_before": original_cohort, "actions": actions,
                 "rows": _delta(before, applied), "revert_rows": _delta(applied, _rows(stage)),
                 "source_reindex": False, "legal_quality_certified": False}
        value["plan_hash"] = digest(value)
        return value
    finally:
        stage.close()


def check_plan(value, store, who, context):
    require(value.get("schema") == SCHEMA and value.get("plan_hash") ==
            digest({k: v for k, v in value.items() if k != "plan_hash"}),
            "RISK_SQLITE_PLAN_HASH", "SQLite 계획이 다르거나 변조되었습니다.", 409)
    principal(who, review=True)
    require(value["context"] == context and
            all(value["principal"][k] == who[k] for k in ("team_id", "user_id")),
            "RISK_SQLITE_CONTEXT", "원문 경로·공유 runtime·실행 주체가 변경됐습니다.", 409)
    require(fixed.binding(store) == value["source_binding"] and
            fixed.resolve(store, who)["links"] == value["resolved"],
            "RISK_SQLITE_SOURCE_CHANGED", "원문 또는 RAG 판본 필터가 변경됐습니다.", 409)


def literal(value):
    if value is None:
        return "NULL"
    if type(value) is int:
        return str(value)
    require(isinstance(value, str) and "\x00" not in value, "RISK_SQLITE_LITERAL", "지원하지 않는 SQL 값")
    return "'" + value.replace("'", "''") + "'"


def sql(value, *, revert=False):
    """Standalone SQLite statements; apply CLI verifies source pins before COMMIT."""
    require(value["plan_hash"] == digest({k: v for k, v in value.items() if k != "plan_hash"}),
            "RISK_SQLITE_PLAN_HASH", "계획 해시 불일치")
    rid = "risk-sqlite:" + value["operation_id"] + (":revert" if revert else "")
    receipt = {"plan_hash": value["plan_hash"], "action": "revert" if revert else "apply",
               "link_ids": [x["link_id"] for x in value["actions"]]}
    done = "(SELECT count(*) FROM basis_receipt WHERE receipt_id=" + literal(rid) + ")=1"
    lines = ["-- SQLite ONLY. Execute with the supplied apply/revoke verifier and plan.json.",
             "-- Plan SHA256: " + value["plan_hash"], "BEGIN IMMEDIATE;",
             "CREATE TEMP TABLE risk_seed_guard(ok INTEGER CHECK(ok=1));"]

    def guard(condition, allow_done=True):
        lines.append("INSERT INTO risk_seed_guard VALUES(CASE WHEN (" +
                     ((done + ") OR (") if allow_done else "") + condition + ") THEN 1 ELSE 0 END);")

    # An existing receipt must match exactly. An unknown plan never becomes a no-op.
    guard("NOT (" + done + ") OR EXISTS(SELECT 1 FROM basis_receipt WHERE receipt_id=" + literal(rid) +
          " AND input_hash=" + literal(value["operation_id"]) + " AND hash=" + literal(digest(receipt)) +
          " AND payload=" + literal(encoded(receipt)) + ")", allow_done=False)
    if revert:
        guard("EXISTS(SELECT 1 FROM basis_receipt WHERE receipt_id=" + literal("risk-sqlite:" + value["operation_id"]) +
              " AND input_hash=" + literal(value["operation_id"]) + ")")
        expected = [a["after"] for a in value["actions"] if a["action"] != "reuse"]
        for row in expected:
            guard("EXISTS(SELECT 1 FROM basis_head h JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision "
                  "WHERE h.link_id=" + literal(row["link_id"]) + " AND h.revision=" + str(row["revision"]) +
                  " AND h.team_id=" + literal(row["team_id"]) + " AND r.hash=" + literal(digest(row)) + ")")
    else:
        where = "h.team_id=" + literal(value["principal"]["team_id"]) + " AND d.document_id=" + literal(value["internal_document_id"])
        base = " FROM basis_head h JOIN basis_document_lookup d ON d.link_id=h.link_id JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision WHERE " + where
        guard("(SELECT count(*)" + base + ")=" + str(len(value["cohort_before"])))
        for row in value["cohort_before"]:
            guard("EXISTS(SELECT 1" + base + " AND h.link_id=" + literal(row["link_id"]) +
                  " AND h.revision=" + str(row["revision"]) + " AND r.hash=" + literal(row["hash"]) + ")")
    dataset = value["revert_rows"] if revert else value["rows"]
    for table in TABLES:
        for row in dataset[table]:
            cols = list(row)
            if table == "basis_head":
                action = next(a for a in value["actions"] if a["link_id"] == row["link_id"])
                old = action["after"] if revert else action.get("before")
                if old:
                    lines.append("UPDATE basis_head SET revision=" + str(row["revision"]) +
                                 " WHERE link_id=" + literal(row["link_id"]) + " AND revision=" + str(old["revision"]) +
                                 " AND NOT (" + done + ");")
                else:
                    lines.append("INSERT INTO basis_head (" + ",".join(cols) + ") SELECT " +
                                 ",".join(literal(row[c]) for c in cols) + " WHERE NOT (" + done + ");")
            else:
                lines.append("INSERT INTO " + table + " (" + ",".join(cols) + ") SELECT " +
                             ",".join(literal(row[c]) for c in cols) + " WHERE NOT (" + done + ");")
    lines.append("INSERT INTO basis_receipt(receipt_id,input_hash,payload,hash) SELECT " +
                 ",".join(literal(x) for x in (rid, value["operation_id"], encoded(receipt), digest(receipt))) +
                 " WHERE NOT (" + done + ");")
    lines += ["DROP TABLE risk_seed_guard;", "COMMIT;"]
    return "\n".join(lines) + "\n"


def execute_sql(repo, script, before_commit):
    """One transaction, no retries. Source/state validation precedes COMMIT."""
    buffer = ""
    try:
        for line in script.splitlines(keepends=True):
            buffer += line
            if sqlite3.complete_statement(buffer):
                if buffer.strip().upper() == "COMMIT;":
                    before_commit()
                repo.db.execute(buffer)
                buffer = ""
        require(not buffer.strip(), "RISK_SQLITE_SQL", "불완전 SQL 문")
    except BaseException:
        repo.db.rollback()
        raise


def verify(value, store, who, repo, context, *, reverted=False):
    check_plan(value, store, who, context)
    rid = "risk-sqlite:" + value["operation_id"] + (":revert" if reverted else "")
    expected_receipt = {"plan_hash": value["plan_hash"], "action": "revert" if reverted else "apply",
                        "link_ids": [a["link_id"] for a in value["actions"]]}
    require(repo.receipt(rid, value["operation_id"]) == expected_receipt,
            "RISK_SQLITE_RECEIPT", "원래 계획의 commit receipt를 확인하지 못했습니다.", 409)
    checked = []
    for action in value["actions"]:
        expected = action.get("reverted", action["after"]) if reverted else action["after"]
        require(repo.head(action["link_id"]) == expected, "RISK_SQLITE_STATE",
                "관계 상태가 계획 이후 변경됐습니다: " + action["link_id"], 409)
        binding = repo.binding(expected["link_id"], expected["revision"], store.manifest["generation_id"])
        require(binding is not None, "RISK_SQLITE_BINDING", "현재 판본 위치가 없습니다.", 409)
        for side in ("internal", "external"):
            for end in binding[side]:
                SourcePort(store).verify(end, value["principal"])
        checked.append({"link_id": expected["link_id"], "revision": expected["revision"], "status": expected["status"]})
    result = {"status": "REVERT_VERIFIED" if reverted else "APPEND_VERIFIED",
              "authority": context["authority"], "links": checked, "source_reindex": False}
    if not reverted:
        service = Service(repo, SourcePort(store))
        snap = snapshot(service, value["principal"], [value["internal_document_id"]])
        wanted = {a["link_id"] for a in value["actions"]}
        snap["items"] = [x for x in snap["items"] if x["link"]["link_id"] in wanted]
        snap["snapshot_hash"] = digest({k: v for k, v in snap.items() if k != "snapshot_hash"})
        found = targets(service, value["principal"], snap)
        require({e["endpoint"]["endpoint_hash"] for e in found} ==
                {e["endpoint_hash"] for link in value["resolved"] for e in link["external"]},
                "RISK_SQLITE_RESOLVER", "기존 대사 소비자의 외규 회수 범위가 다릅니다.", 409)
        result["external_endpoint_count"] = len(found)
    return result
