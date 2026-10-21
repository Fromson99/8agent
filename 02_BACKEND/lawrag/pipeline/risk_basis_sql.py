"""Additive Oracle statements for the existing basis-link lifecycle tables.

Source/index/release/ACTIVE rows are only read. One transaction per batch.
Same exact rows are a no-op; any conflicting head/history/receipt aborts.
"""
import json
import re

from semantic_runtime.basis_links.contracts import digest, require
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.oracle import TABLES
from semantic_runtime.oracle_dp_assets import clob_text
from semantic_runtime.oracle_dp_io import TABLES as SOURCE_TABLES, COLUMNS, KEYS, CLOBS

COLS = {
    "basis_head": ("link_id", "team_id", "revision"),
    "basis_revision": ("link_id", "revision", "payload", "hash"),
    "basis_binding": ("binding_id", "link_id", "revision", "generation", "payload", "hash"),
    "basis_event": ("event_id", "link_id", "payload", "hash"),
    "basis_receipt": ("receipt_id", "input_hash", "payload", "hash"),
    "basis_lineage": ("version_id", "family_id", "payload", "hash"),
    "basis_migration": ("migration_id", "payload", "hash"),
    "basis_view_head": ("session_key", "payload", "hash"),
}
PK = {k: (v[0],) for k, v in COLS.items()}
PK["basis_revision"] = ("link_id", "revision")
DEFAULT_TABLES = {k: "SIDDA.LEGAL_" + k.upper() + "_A" for k in TABLES}


def tables(value):
    require(isinstance(value, dict) and set(value) == set(TABLES), "RISK_SEED_TABLES", "원장 테이블 맵 8개가 필요합니다.")
    require(len(set(value.values())) == len(TABLES) and all(
        isinstance(v, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}\.[A-Z][A-Z0-9_]{0,29}", v)
        for v in value.values()), "RISK_SEED_TABLES", "승인된 OWNER.TABLE 이름이 필요합니다.")
    require(not any(v.split(".")[1] in SOURCE_TABLES.values() or
                    v.split(".")[1].startswith(("LEGAL_QUERY_", "LEGAL_RAG_")) for v in value.values()),
            "RISK_SEED_TABLES", "원문·색인·릴리스 테이블을 관계 원장으로 사용할 수 없습니다.")
    return value


def schema_sql(table_map):
    """Explicit DBA artifact only. Never executed by inspect/plan/apply."""
    from semantic_runtime.basis_links.oracle import ddl
    table_map = tables(table_map)
    simple = {k: v.split(".")[1] for k, v in table_map.items()}
    text = ddl(simple)
    for k in TABLES:
        text = text.replace("CREATE TABLE " + simple[k] + " ", "CREATE TABLE " + table_map[k] + " ")
    return "-- OPTIONAL: only missing basis tables; review existing schema first.\n" + text + "\n"


def check_schema(sql, table_map):
    report = {}
    for logical, actual in tables(table_map).items():
        owner, name = actual.split(".")
        bind = [("owner", owner, "VARCHAR2"), ("name", name, "VARCHAR2")]
        cols = sql.query("SELECT COLUMN_NAME,DATA_TYPE FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME=:name ORDER BY COLUMN_ID", bind, limit=100)
        found = {r["COLUMN_NAME"].lower(): r["DATA_TYPE"] for r in cols}
        require(set(found) == set(COLS[logical]), "RISK_SEED_SCHEMA",
                actual + ": 기존 원장 스키마 확인 필요. 별도 DDL을 검토하십시오.", 409)
        for column, dtype in found.items():
            expected = "CLOB" if column == "payload" else "NUMBER" if column == "revision" else "VARCHAR2"
            require(dtype == expected, "RISK_SEED_SCHEMA", actual + "." + column + ": 타입 불일치", 409)
        keys = sql.query("SELECT c.COLUMN_NAME,c.POSITION FROM ALL_CONS_COLUMNS c JOIN ALL_CONSTRAINTS k ON c.OWNER=k.OWNER AND c.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.OWNER=:owner AND k.TABLE_NAME=:name AND k.CONSTRAINT_TYPE='P' AND k.STATUS='ENABLED' ORDER BY c.POSITION", bind, limit=100)
        require(tuple(r["COLUMN_NAME"].lower() for r in keys) == PK[logical],
                "RISK_SEED_SCHEMA", actual + ": PK 확인 필요", 409)
        if logical == "basis_binding":
            unique = sql.query("SELECT c.CONSTRAINT_NAME,c.COLUMN_NAME,c.POSITION FROM ALL_CONS_COLUMNS c JOIN ALL_CONSTRAINTS k ON c.OWNER=k.OWNER AND c.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.OWNER=:owner AND k.TABLE_NAME=:name AND k.CONSTRAINT_TYPE='U' AND k.STATUS='ENABLED' ORDER BY c.CONSTRAINT_NAME,c.POSITION", bind, limit=100)
            groups = {}
            for row in unique:
                groups.setdefault(row["CONSTRAINT_NAME"], []).append(row["COLUMN_NAME"].lower())
            require(["link_id", "revision", "generation"] in groups.values(),
                    "RISK_SEED_SCHEMA", actual + ": 판본별 binding UNIQUE 확인 필요", 409)
        report[logical] = "verified"
    return report


class OracleReader:
    """Read the same authority rows used by Service/resolver, with no mutation."""
    decoded = staticmethod(Repository.decoded)

    def __init__(self, sql, table_map):
        self.sql, self.tables = sql, tables(table_map)

    def _row(self, table, where, binds):
        actual = self.tables[table]
        # Hash in the CLOB predicate prevents splicing concurrent versions.
        meta = self.sql.query(f"SELECT HASH FROM {actual} WHERE {where}", binds, limit=1)
        if not meta:
            return None
        pin = meta[0]["HASH"]
        body = clob_text(self.sql, actual, "PAYLOAD", where + " AND HASH=:row_hash",
                         [*binds, ("row_hash", pin, "VARCHAR2")])
        require(body is not None, "RISK_SEED_READ_CHANGED", "읽는 동안 원장 행이 변경됐습니다.", 409)
        return self.decoded({"payload": body, "hash": pin})

    def head(self, ident):
        rows = self.sql.query(f"SELECT REVISION FROM {self.tables['basis_head']} WHERE LINK_ID=:id",
                              [("id", ident, "VARCHAR2")], limit=1)
        if not rows:
            return None
        return self._row("basis_revision", "LINK_ID=:id AND REVISION=:rev",
                         [("id", ident, "VARCHAR2"), ("rev", rows[0]["REVISION"], "NUMBER")])

    def links(self, team):
        found, after = [], ""
        while True:
            rows = self.sql.query(f"SELECT LINK_ID FROM {self.tables['basis_head']} WHERE TEAM_ID=:team AND LINK_ID>:after_id ORDER BY LINK_ID FETCH FIRST 100 ROWS ONLY",
                                  [("team", team, "VARCHAR2"), ("after_id", after or " ", "VARCHAR2")], limit=100)
            for row in rows:
                item = self.head(row["LINK_ID"])
                require(item is not None and item["team_id"] == team, "RISK_SEED_READ_CHANGED", "원장 head 불일치", 409)
                found.append(item)
            if len(rows) < 100:
                return found
            after = rows[-1]["LINK_ID"]

    def links_for_document(self, team, document_id):
        # Service still checks the current generation binding and ACL. Retain
        # historical heads here because their current binding can name a new ID.
        return self.links(team)

    def binding(self, ident, revision, generation):
        return self._row("basis_binding", "LINK_ID=:id AND REVISION=:rev AND GENERATION=:gen",
                         [("id", ident, "VARCHAR2"), ("rev", revision, "NUMBER"),
                          ("gen", generation, "VARCHAR2")])

    def lineage(self, version):
        return self._row("basis_lineage", "VERSION_ID=:version", [("version", version, "VARCHAR2")])

    def batch_receipt(self, operation):
        return self._row("basis_receipt", "RECEIPT_ID=:id",
                         [("id", "risk-seed:" + operation, "VARCHAR2")])

    def verify_rows(self, expected):
        checked = 0
        for table, values in expected.items():
            for row in values:
                args = [(c, row[c], "NUMBER" if c == "revision" else "VARCHAR2") for c in PK[table]]
                where = " AND ".join(c + "=:" + c for c in PK[table])
                columns = [c for c in COLS[table] if c != "payload"]
                result = self.sql.query(f"SELECT {','.join(columns)} FROM {self.tables[table]} WHERE {where}", args, limit=1)
                require(len(result) == 1 and {k.lower(): v for k, v in result[0].items()} ==
                        {c: row[c] for c in columns}, "RISK_SEED_VERIFY_ROWS", "원장 행/메타데이터가 계획과 다릅니다.", 409)
                if "payload" in row:
                    require(self._row(table, where, args) == json.loads(row["payload"]),
                            "RISK_SEED_VERIFY_ROWS", "원장 payload가 계획과 다릅니다.", 409)
                checked += 1
        return checked


def source_guards(store, value):
    """Only exact selected Oracle rows; originals remain immutable."""
    require(getattr(store, "is_oracle_query", False), "RISK_SEED_ORACLE_ONLY", "실제 Oracle 원문 확인 후 SQL을 생성합니다.")
    reader = store.oracle_request.sources
    result, seen = [], set()
    for link in value["resolved"]:
        for end in link["internal"] + link["external"]:
            did = end["document_id"]
            keys = [("document", None), ("source_unit", end["unit_id"])]
            keys.extend(("block_payload", p["block_id"]) for p in end["spans"])
            for kind, key in keys:
                identity = (did, kind, key)
                if identity in seen:
                    continue
                seen.add(identity)
                column = "UNIT_ID" if kind == "source_unit" else "BLOCK_ID"
                extra = "" if key is None else " AND " + column + "=:selected_key"
                binds = [] if key is None else [("selected_key", key, "VARCHAR2")]
                row = reader._rows(kind, did, extra, binds, limit=1)
                require(len(row) == 1, "RISK_SEED_SOURCE_MISSING", "SQL에 결속할 원문 행을 찾을 수 없습니다.", 409)
                result.append({"table": "SIDDA." + SOURCE_TABLES[kind], "kind": kind, "row": row[0]})
    return result


def seal(value, table_map, guards, query_manifest):
    value = json.loads(json.dumps(value))
    value.pop("plan_hash")
    value["table_map"] = tables(table_map)
    value["source_guards"] = guards
    from semantic_runtime.oracle_query_catalog import json_body
    value["query_manifest_json"] = json_body(query_manifest)
    require(digest(query_manifest) == value["source_binding"]["query_release_id"],
            "RISK_SEED_QUERY_RELEASE", "조회 manifest 결속 불일치", 409)
    require(bool(guards), "RISK_SEED_SOURCE_GUARDS", "Oracle 원문 확인 조건이 필요합니다.")
    value["plan_hash"] = digest(value)
    return value


def transaction(value, *, revoke=False):
    """Return executable bind SQL and matching standalone SQL, without IO."""
    require(digest({k: v for k, v in value.items() if k != "plan_hash"}) == value["plan_hash"],
            "RISK_SEED_PLAN_HASH", "계획 해시 불일치", 409)
    mapping = tables(value["table_map"])
    require(value["source_binding"]["backend"] == "oracle" and value["source_guards"],
            "RISK_SEED_ORACLE_ONLY", "로컬 검사용 계획을 Oracle에 적용할 수 없습니다.")
    statements, binds = ["DECLARE n NUMBER; BEGIN"], []

    def arg(value, kind="VARCHAR2"):
        name = "v" + str(len(binds))
        binds.append((name, value, kind))
        return ":" + name

    def same(column, data, kind):
        token = arg(data, kind)
        return column + " IS NULL" if data is None else (
            f"DBMS_LOB.COMPARE({column},{token})=0" if kind == "CLOB" else column + "=" + token)

    # NULL predicates do not bind unused NULL values (the JDBC renderer rejects them).
    def eq(column, data, kind="VARCHAR2"):
        return column + " IS NULL" if data is None else same(column, data, kind)

    # The selected immutable query release fixes the RAG version filter.
    from semantic_runtime.oracle_query_catalog import RELEASE, ACTIVE
    qid = arg(value["source_binding"]["query_release_id"])
    manifest = arg(value["query_manifest_json"], "CLOB")
    statements += [f"SELECT COUNT(*) INTO n FROM {RELEASE} WHERE RELEASE_ID={qid} AND DBMS_LOB.COMPARE(MANIFEST_JSON,{manifest})=0;",
                   "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20071,'RISK_SEED_QUERY_RELEASE'); END IF;"]
    selected = value["source_binding"]
    if selected.get("query_channel"):
        channel, revision = arg(selected["query_channel"]), arg(selected["query_pointer_revision"], "NUMBER")
        statements += [
            # Lock only the pointer during this short transaction. Do not
            # change it; reject a concurrent cutover instead of binding a stale filter.
            f"SELECT REVISION INTO n FROM {ACTIVE} WHERE CHANNEL={channel} AND RELEASE_ID={qid} FOR UPDATE WAIT 5;",
            f"IF n<>{revision} THEN RAISE_APPLICATION_ERROR(-20075,'RISK_SEED_SELECTION_CHANGED'); END IF;"]
    for guard in value["source_guards"]:
        kind, row = guard["kind"], guard["row"]
        require(guard["table"] == "SIDDA." + SOURCE_TABLES[kind] and set(row) == set(COLUMNS[kind]),
                "RISK_SEED_SOURCE_GUARDS", "허용된 원문 조건만 사용할 수 있습니다.")
        where = " AND ".join(eq(c, row[c], "CLOB" if c in CLOBS else "NUMBER" if type(row[c]) is int else "VARCHAR2")
                             for c in COLUMNS[kind])
        statements += [f"SELECT COUNT(*) INTO n FROM {guard['table']} WHERE {where};",
                       "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20072,'RISK_SEED_SOURCE_CHANGED'); END IF;"]
    if not revoke:
        for pin in sorted(value["reused_link_pins"], key=lambda p: p["link_id"]):
            ident, revision = arg(pin["link_id"]), arg(pin["revision"], "NUMBER")
            team, row_hash = arg(pin["team_id"]), arg(pin["payload_hash"])
            statements += [
                f"SELECT REVISION INTO n FROM {mapping['basis_head']} WHERE LINK_ID={ident} AND TEAM_ID={team} FOR UPDATE WAIT 5;",
                f"IF n<>{revision} THEN RAISE_APPLICATION_ERROR(-20076,'RISK_SEED_REUSED_CHANGED'); END IF;",
                f"SELECT COUNT(*) INTO n FROM {mapping['basis_revision']} WHERE LINK_ID={ident} AND REVISION={revision} AND HASH={row_hash};",
                "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20076,'RISK_SEED_REUSED_CHANGED'); END IF;"]
    dataset = value["rollback_rows"] if revoke else value["rows"]
    for table in TABLES:
        actual = mapping[table]
        for row in dataset[table]:
            require(set(row) == set(COLS[table]), "RISK_SEED_ROW", "원장 행 스키마 불일치")
            normalized = dict(row)
            if "payload" in row:
                payload = json.loads(row["payload"])
                require(digest(payload) == row["hash"], "RISK_SEED_ROW_HASH", "원장 payload 해시 불일치", 409)
                normalized["payload"] = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            tokens = {c: arg(normalized[c], "CLOB" if c == "payload" else "NUMBER" if c == "revision" else "VARCHAR2")
                      for c in COLS[table]}
            key = " AND ".join(c + "=" + tokens[c] for c in PK[table])
            matches = " AND ".join(f"DBMS_LOB.COMPARE({c},{tokens[c]})=0" if c == "payload" else
                                   f"({c}={tokens[c]} OR ({c} IS NULL AND {tokens[c]} IS NULL))"
                                   for c in COLS[table])
            if revoke and table == "basis_head":
                previous = arg(row["revision"] - 1, "NUMBER")
                statements.append(f"UPDATE {actual} SET REVISION={tokens['revision']} WHERE {key} AND TEAM_ID={tokens['team_id']} AND REVISION={previous};")
            else:
                statements += [f"SELECT COUNT(*) INTO n FROM {actual} WHERE {key};",
                               f"IF n=0 THEN INSERT INTO {actual} ({','.join(COLS[table])}) VALUES ({','.join(tokens.values())}); END IF;"]
            statements += [f"SELECT COUNT(*) INTO n FROM {actual} WHERE {key} AND {matches};",
                           "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20073,'RISK_SEED_ROW_CONFLICT'); END IF;"]
    # Stable batch receipt rejects a newly generated, conflicting plan even if
    # its random link IDs differ. Existing identical packages are idempotent.
    receipt = {"plan_hash": value["plan_hash"], "operation_id": value["operation_id"],
               "new_link_ids": value["new_link_ids"], "action": "revoke" if revoke else "append"}
    rid = "risk-seed:" + value["operation_id"] + (":revoke" if revoke else "")
    identity, ih, body, rh = (arg(rid), arg(value["plan_hash"]),
                            arg(json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")), "CLOB"),
                            arg(digest(receipt)))
    actual = mapping["basis_receipt"]
    statements += [
        f"SELECT COUNT(*) INTO n FROM {actual} WHERE RECEIPT_ID={identity};",
        f"IF n=0 THEN INSERT INTO {actual} (RECEIPT_ID,INPUT_HASH,PAYLOAD,HASH) VALUES({identity},{ih},{body},{rh}); END IF;",
        f"SELECT COUNT(*) INTO n FROM {actual} WHERE RECEIPT_ID={identity} AND INPUT_HASH={ih} AND HASH={rh} AND DBMS_LOB.COMPARE(PAYLOAD,{body})=0;",
        "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20074,'RISK_SEED_BATCH_CONFLICT'); END IF;",
        "COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;"]
    sql = "\n".join(statements)
    # Reuse the maintained, escaping-aware JDBC renderer for portable CLOB SQL.
    from .oracle_query_dataiku import render
    standalone = "-- Generated from reviewed plan " + value["plan_hash"] + "\nSET DEFINE OFF\nWHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK\n" + render(sql, binds, write=True) + "\n/\n"
    return {"statement": sql, "binds": binds, "standalone": standalone}


# Retained R1 staging verification for historical contract tests; not the R2 CLI.
def verify(value, store, who, reader, *, revoked=False):
    from . import risk_basis_seed as seed
    from . import risk_basis_sql as db
    from semantic_runtime.basis_links.service import Service
    from semantic_runtime.basis_links.sources import SourcePort
    from semantic_runtime.basis_links.resolver import snapshot, targets
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


