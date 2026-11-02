"""Local Oracle + fake Mesh. Never contacts Dataiku or a model service."""
import importlib.util
import json
import math
from pathlib import Path
import secrets
import subprocess
import sys
import types

import oracledb
import pandas as pd
import pytest

path = Path(__file__).parents[1] / "embedding_smoke.py"
spec = importlib.util.spec_from_file_location("embedding_smoke", path)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def sources():
    return [{"DATA_VER_ID": "a"*64, "DOC_ID": "doc'001", "UNIT_ID": "00"+str(i),
             "BLK_ID": "000"+str(i), "SRC_DATA_HASH_VAL": "b"*64,
             "SAMPLE_TEXT": "상법 원문 '시험' "*60} for i in range(3)]


def dense():
    return [[math.sin(i+j+1) for i in range(1024)] for j in range(3)]


@pytest.fixture(scope="module")
def database():
    info = json.loads(subprocess.check_output(["docker", "inspect", "a8-legal-mapped-20261023"]))[0]
    assert info["Config"]["Labels"]["a8.task"] == "legal-mapped-20261023"
    password = dict(s.split("=", 1) for s in info["Config"]["Env"])["ORACLE_PASSWORD"]
    admin = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user="system", password=password)
    user, pw = "A8_ES_"+secrets.token_hex(4).upper(), secrets.token_hex(20)
    with admin.cursor() as c:
        c.execute(f'CREATE USER {user} IDENTIFIED BY "{pw}" DEFAULT TABLESPACE USERS QUOTA 4M ON USERS')
        c.execute(f"GRANT CREATE SESSION,CREATE TABLE TO {user}")
    conn = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user=user, password=pw)
    try:
        with conn.cursor() as c:
            c.execute("CREATE TABLE LGL_VCTR_SET_S (PUB_ID VARCHAR2(64) PRIMARY KEY,PAYLOAD_JSON CLOB NOT NULL,CHECK(PAYLOAD_JSON IS JSON WITH UNIQUE KEYS))")
            c.execute("CREATE TABLE LGL_VCTR_ITEM_S (PUB_ID VARCHAR2(64),SEG_ID VARCHAR2(64),META_JSON CLOB NOT NULL,EMBEDDING VECTOR(*,FLOAT32) NOT NULL,PRIMARY KEY(PUB_ID,SEG_ID),FOREIGN KEY(PUB_ID) REFERENCES LGL_VCTR_SET_S(PUB_ID),CHECK(META_JSON IS JSON WITH UNIQUE KEYS))")
            c.execute("CREATE UNIQUE INDEX LVM_SET_ACT ON LGL_VCTR_SET_S(CASE WHEN JSON_VALUE(PAYLOAD_JSON,'$.active_revision' RETURNING NUMBER ERROR ON ERROR NULL ON EMPTY) IS NOT NULL THEN JSON_VALUE(PAYLOAD_JSON,'$.manifest.query_id' RETURNING VARCHAR2(64) ERROR ON ERROR) END)")
            c.execute("CREATE INDEX LVM_ITEM_DOC ON LGL_VCTR_ITEM_S(PUB_ID,JSON_VALUE(META_JSON,'$.document_id' RETURNING VARCHAR2(512) ERROR ON ERROR),JSON_VALUE(META_JSON,'$.source_id' RETURNING VARCHAR2(512) ERROR ON ERROR))")
            c.execute("CREATE TABLE LGL_DOC_BLK_S (DATA_VER_ID VARCHAR2(64),DOC_ID VARCHAR2(64),UNIT_ID VARCHAR2(64),BLK_ID VARCHAR2(64),SRC_DATA_HASH_VAL VARCHAR2(64),BLK_TXT_CN CLOB)")
            for row in sources():
                c.execute("INSERT INTO LGL_DOC_BLK_S VALUES(:1,:2,:3,:4,:5,:6)", list(row.values()))
            c.execute("INSERT INTO LGL_VCTR_SET_S VALUES(:1,:2)", ['e'*64, '{"original":"preserved"}'])
        conn.commit()
        yield conn, user
    finally:
        conn.close()
        with admin.cursor() as c:
            c.execute("DROP USER "+user+" CASCADE")
        admin.close()


def counts(conn):
    with conn.cursor() as c:
        c.execute("SELECT (SELECT COUNT(*) FROM LGL_VCTR_SET_S),(SELECT COUNT(*) FROM LGL_VCTR_ITEM_S) FROM DUAL")
        return c.fetchone()


def test_native_roundtrip_with_real_json_indexes_and_dense_clob(database):
    conn, user = database
    sql = smoke.roundtrip_sql(user, "c"*64, sources(), smoke.checked_vectors(dense()))
    assert len(sql) > 32767 and "COMMIT" not in sql
    with conn.cursor() as c:
        c.execute(sql)
    assert counts(conn) == (1, 0)


def test_native_late_insert_failure_rolls_back_parent_and_two_children(database):
    conn, user = database
    sql = smoke.roundtrip_sql(user, "d"*64, sources(), smoke.checked_vectors(dense()))
    sql = sql.replace("VALUES('"+'d'*64+"','2',", "VALUES('"+'d'*64+"','0',")
    with conn.cursor() as c, pytest.raises(oracledb.DatabaseError, match="ORA-00001"):
        c.execute(sql)
    assert counts(conn) == (1, 0)


def test_native_wrong_distance_assertion_rolls_back(database):
    conn, user = database
    sql = smoke.roundtrip_sql(user, "f"*64, sources(), smoke.checked_vectors(dense()))
    sql = sql.replace("ABS(d-(0))", "ABS(d-(1))", 1)
    assert "ABS(d-(1))" in sql
    with conn.cursor() as c, pytest.raises(oracledb.DatabaseError, match="ORA-20032"):
        c.execute(sql)
    assert counts(conn) == (1, 0)


@pytest.mark.parametrize("kind", ["count", "dim", "nan", "zero", "bool"])
def test_bad_model_output_rejected(kind):
    values = dense()
    if kind == "count": values.pop()
    if kind == "dim": values[0].pop()
    if kind == "nan": values[0][0] = float("nan")
    if kind == "zero": values[0] = [0.0]*1024
    if kind == "bool": values[0][0] = True
    with pytest.raises(ValueError):
        smoke.checked_vectors(values)


def fake_dataiku(monkeypatch, database, *, timeout=False, empty=False):
    conn, user = database
    state = {"calls": 0, "texts": [], "sql": []}
    class Executor:
        def query_to_df(self, sql, pre_queries=(), **kwargs):
            state["sql"].append(sql)
            with conn.cursor() as c:
                for statement in pre_queries:
                    state["sql"].append(statement)
                    c.execute(statement)
                c.execute(sql)
                names = [d[0] for d in c.description]
                rows = [[v.read() if hasattr(v, "read") else v for v in row] for row in c.fetchall()]
            if empty and "DBMS_LOB.SUBSTR" in sql:
                rows = []
            return pd.DataFrame(rows, columns=names)
    class Batch:
        def add_text(self, text): state["texts"].append(text)
        def execute(self):
            state["calls"] += 1
            if timeout: raise TimeoutError("not a real endpoint")
            return types.SimpleNamespace(get_embeddings=dense)
    project = types.SimpleNamespace(
        list_llms=lambda **kw: [types.SimpleNamespace(id=smoke.MODEL_ID)],
        get_llm=lambda model: types.SimpleNamespace(new_embeddings=Batch))
    fake = types.SimpleNamespace(get_custom_variables=lambda: {}, SQLExecutor2=lambda **kw: Executor(),
                                api_client=lambda: types.SimpleNamespace(get_default_project=lambda: project))
    monkeypatch.setitem(sys.modules, "dataiku", fake)
    monkeypatch.setattr(smoke, "OWNER", user)
    return state


def test_full_cell_fake_mesh_actual_oracle_and_repeat_guard(database, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    state = fake_dataiku(monkeypatch, database)
    result = smoke.run()
    assert result["status"] == "PASS"
    assert result["dimensions"] == 1024 and result["remaining_test_rows"] == 0
    assert state["calls"] == 1 and len(state["texts"]) == 3
    assert result["oracle_cosine_pairs_checked"] == 9
    smoke.run()
    assert state["calls"] == 1
    assert counts(database[0]) == (1, 0)


def test_unknown_model_not_retried(database, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    state = fake_dataiku(monkeypatch, database, timeout=True)
    result = smoke.run()
    assert result["status"] == "UNKNOWN" and result["failed_stage"] == "EMBEDDING_EXECUTE"
    smoke.run()
    assert state["calls"] == 1
    assert not any("INSERT INTO" in s for s in state["sql"])


def test_empty_source_calls_no_model(database, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    state = fake_dataiku(monkeypatch, database, empty=True)
    result = smoke.run()
    assert result["status"] == "FAILED" and state["calls"] == 0
    assert not any("INSERT INTO" in s for s in state["sql"])
