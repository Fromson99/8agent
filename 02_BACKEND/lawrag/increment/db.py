"""DB 어댑터 — 같은 SQL 문장을 SQLite·Oracle(python-oracledb)·Dataiku SQLExecutor2로 실행한다.

규약
- 바인드는 `:이름`. 시각은 SQL 안의 `{now}`를 어댑터가 바꾼다.
- 쓰기는 `with db.transaction() as tx:` 안에서만 한다. 블록이 끝나야 커밋, 예외면 전부 롤백.
- `tx.execute(sql, binds, expect=n)`은 영향 행 수가 n이 아니면 CasError로 전체를 되돌린다.
  상태 전이·포인터 교체의 경합 방지는 이 조건부 UPDATE로 한다.
- Dataiku는 트랜잭션 안의 문장을 하나의 PL/SQL 블록으로 묶어 `pre_queries`로 보내고
  `COMMIT`한다 (기존 운영 Gold 적재기와 같은 방식). 값은 SQL 리터럴 대신 UTF-8 16진수로
  넣어 원문 따옴표·백슬래시가 SQL 해석에 들어가지 않게 한다. 트랜잭션 안에서는 읽지 않는다.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

_BIND = re.compile(r"'(?:''|[^'])*'|:([A-Za-z][A-Za-z0-9_]*)")
_DDL = re.compile(r"^\s*(CREATE|ALTER|DROP|COMMENT)\s", re.IGNORECASE)


class CasError(RuntimeError):
    """조건부 갱신 실패 — 다른 실행이 먼저 상태를 바꿨거나 기준 판본이 바뀌었다."""


class _SqliteTx:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def execute(self, sql: str, binds: dict | None = None, *, expect: int | None = None) -> None:
        cursor = self.conn.execute(sql.replace("{now}", "strftime('%Y-%m-%dT%H:%M:%f+09:00','now','+9 hours')"),
                                   binds or {})
        if expect is not None and cursor.rowcount != expect:
            raise CasError(f"expected {expect} rows, got {cursor.rowcount}: {sql.split()[0]} {sql.split()[1]}")


class SqliteDatabase:
    dialect = "sqlite"

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row

    def query(self, sql: str, binds: dict | None = None) -> list[dict]:
        rows = self.conn.execute(sql.replace("{now}", "CURRENT_TIMESTAMP"), binds or {}).fetchall()
        return [dict(r) for r in rows]

    @contextmanager
    def transaction(self) -> Iterator[_SqliteTx]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield _SqliteTx(self.conn)
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")


def _prefixed(sql: str, binds: dict | None) -> tuple[str, dict]:
    """바인드 이름에 b_ 접두어를 붙인다. :user·:file 같은 Oracle 예약어 바인드는 ORA-01745로 거절된다."""
    text = _BIND.sub(lambda m: m.group(0) if m.group(1) is None else ":b_" + m.group(1),
                     sql.replace("{now}", "SYSTIMESTAMP"))
    return text, {"b_" + k: v for k, v in (binds or {}).items()}


class _OracleTx:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql: str, binds: dict | None = None, *, expect: int | None = None) -> None:
        import oracledb
        cursor = self.conn.cursor()
        text, binds = _prefixed(sql, binds)
        sizes = {k: oracledb.DB_TYPE_CLOB for k, v in binds.items() if isinstance(v, str) and len(v) > 1000}
        if sizes:
            cursor.setinputsizes(**sizes)
        cursor.execute(text, binds)
        if expect is not None and cursor.rowcount != expect:
            raise CasError(f"expected {expect} rows, got {cursor.rowcount}: {sql.split()[0]} {sql.split()[1]}")


class OracleDatabase:
    """python-oracledb 연결 (로컬 Oracle 검증·oracledb가 있는 실행 환경)."""
    dialect = "oracle"

    def __init__(self, conn):
        import oracledb
        self.conn = conn
        self.conn.autocommit = False

        def handler(cursor, metadata):
            if metadata.type_code is oracledb.DB_TYPE_CLOB:
                return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
            return None
        self.conn.outputtypehandler = handler

    def query(self, sql: str, binds: dict | None = None) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(*_prefixed(sql, binds))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    @contextmanager
    def transaction(self) -> Iterator[_OracleTx]:
        try:
            yield _OracleTx(self.conn)
        except BaseException:
            self.conn.rollback()
            raise
        self.conn.commit()


# ------------------------------------------------------------------ Dataiku

_CHUNK = 1800       # UTF-8 바이트 — 16진수 3600자, SQL 리터럴 4000자 한도 아래


def _utf8_chunks(value: str) -> Iterator[bytes]:
    raw = value.encode("utf-8")
    start = 0
    while start < len(raw):
        end = min(start + _CHUNK, len(raw))
        while end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1
        yield raw[start:end]
        start = end


def _hex(raw: bytes) -> str:
    return "UTL_I18N.RAW_TO_CHAR(HEXTORAW('" + raw.hex().upper() + "'),'AL32UTF8')"


def render_literal(value: Any) -> str:
    """읽기용 바인드 → SQL 식. 4000바이트 넘는 문자열은 읽기 조건에 쓰지 않는다."""
    if value is None:
        return "NULL"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return repr(value)
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 4000:
            raise ValueError("DATAIKU_READ_BIND_TOO_LONG")
        chunks = list(_utf8_chunks(value))
        return "(" + " || ".join(_hex(c) for c in chunks) + ")" if chunks else "NULL"
    raise ValueError(f"DATAIKU_UNSUPPORTED_BIND:{type(value).__name__}")


def _substitute(sql: str, values: dict[str, str]) -> str:
    def replace(match):
        name = match.group(1)
        if name is None:
            return match.group(0)
        if name not in values:
            raise ValueError("DATAIKU_BIND_MISSING:" + name)
        return values[name]
    return _BIND.sub(replace, sql)


class _DataikuTx:
    def __init__(self):
        self.declarations: list[str] = []
        self.body: list[str] = []
        self.lob = 0

    def execute(self, sql: str, binds: dict | None = None, *, expect: int | None = None) -> None:
        if _DDL.match(sql):
            # PL/SQL 블록 안의 DDL은 EXECUTE IMMEDIATE로만 실행된다 (DDL은 암묵 커밋 — 스키마 생성 전용)
            if binds or "~'" in sql:
                raise ValueError("DATAIKU_DDL_UNSUPPORTED")
            self.body.append(f"EXECUTE IMMEDIATE q'~{sql}~';")
            return
        values: dict[str, str] = {}
        for name, value in (binds or {}).items():
            if isinstance(value, str) and len(value.encode("utf-8")) > 3000:
                self.lob += 1
                var = f"inc_lob_{self.lob}"
                self.declarations.append(f"{var} CLOB;")
                self.body.append(f"DBMS_LOB.CREATETEMPORARY({var}, TRUE, DBMS_LOB.CALL);")
                for chunk in _utf8_chunks(value):
                    self.body.append(f"DBMS_LOB.APPEND({var}, TO_CLOB({_hex(chunk)}));")
                values[name] = var
            else:
                values[name] = render_literal(value)
        self.body.append(_substitute(sql.replace("{now}", "SYSTIMESTAMP"), values) + ";")
        if expect is not None:
            self.body.append(f"IF SQL%ROWCOUNT <> {int(expect)} THEN "
                             f"RAISE_APPLICATION_ERROR(-20901, 'INCREMENT_CAS'); END IF;")

    def block(self) -> str:
        declare = ("DECLARE\n" + "\n".join(self.declarations) + "\n") if self.declarations else ""
        return declare + "BEGIN\n" + "\n".join(self.body) + "\nEND;"


class DataikuDatabase:
    """dataiku.SQLExecutor2(connection=...) 위의 어댑터.

    읽기: query_to_df. 쓰기: 트랜잭션 전체를 PL/SQL 블록 하나로 pre_queries에 넣고 COMMIT.
    블록 안 오류는 Oracle이 블록 전체를 되돌리고(문장 단위 원자성), post COMMIT은 실행되지 않는다.
    """
    dialect = "oracle"

    def __init__(self, executor):
        self.executor = executor

    def query(self, sql: str, binds: dict | None = None) -> list[dict]:
        values = {k: render_literal(v) for k, v in (binds or {}).items()}
        frame = self.executor.query_to_df(_substitute(sql.replace("{now}", "SYSTIMESTAMP"), values),
                                          infer_from_schema=True, parse_dates=False)
        rows = frame.to_dict("records")
        return [{k.upper(): (None if _is_nan(v) else v) for k, v in row.items()} for row in rows]

    @contextmanager
    def transaction(self) -> Iterator[_DataikuTx]:
        tx = _DataikuTx()
        yield tx
        if not tx.body:
            return
        frame = self.executor.query_to_df("SELECT 1 AS OK FROM DUAL", pre_queries=[tx.block()],
                                          post_queries=["COMMIT"])
        if len(frame) != 1:
            raise RuntimeError("DATAIKU_WRITE_UNCONFIRMED")


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and value != value
