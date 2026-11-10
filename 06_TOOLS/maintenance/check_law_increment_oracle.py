"""로컬 Oracle에서 증분 테이블 DDL과 전체 흐름을 실제로 검증한다 (임시 계정, 끝나면 삭제).

두 경로를 모두 돈다.
- python-oracledb 연결 (OracleDatabase)
- Dataiku SQLExecutor2 흉내 (DataikuDatabase): 쓰기를 PL/SQL 블록 하나로 pre_queries에 넣고 COMMIT.
  실제 Dataiku가 아니라 같은 문자열을 같은 Oracle에 실행하는 대역이다.

사용: .venv/bin/python 06_TOOLS/maintenance/check_law_increment_oracle.py --out <json>
로컬 컨테이너 a8-legal-mapped-20261023 (127.0.0.1:11524/FREEPDB1)의 system 비밀번호를 docker 환경에서 읽는다.
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))

import oracledb  # noqa: E402

from lawrag.increment.db import DataikuDatabase, OracleDatabase  # noqa: E402
from lawrag.increment.lawgo_parse import parse_lawgo_xml  # noqa: E402
from lawrag.increment.schema import TABLES, oracle_comments  # noqa: E402
from lawrag.increment.service import ChannelSwitch, IncrementError, IncrementService  # noqa: E402

DSN = "127.0.0.1:11524/FREEPDB1"
CONTAINER = "a8-legal-mapped-20261023"
REAL = ROOT / "01_DATA/PACKAGES/EXTERNAL/ontology-operational-8def52ccda54d7b0/gen-8def52ccda54d7b01cce8a4a/ARTIFACTS/STRUCTURE"
GOVERNANCE = ["240dac7491eec3f8", "1ab2b728e6280db5", "c4b33879c7dc5554"]
EFINANCE = ["dc75a9dab2d74863", "342cfff1766f3631"]


def system_password() -> str:
    info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
    if info["Config"]["Labels"].get("a8.task") != "legal-mapped-20261023":
        raise SystemExit("예상한 로컬 시험 컨테이너가 아니다")
    return dict(x.split("=", 1) for x in info["Config"]["Env"])["ORACLE_PASSWORD"]


class FakeExecutor:
    """dataiku.SQLExecutor2.query_to_df 대역 — pre_queries → sql → post_queries를 한 연결에서 실행."""

    def __init__(self, conn):
        self.conn = conn
        self.blocks = 0

    def query_to_df(self, sql, pre_queries=None, post_queries=None, **_):
        import pandas
        cursor = self.conn.cursor()
        try:
            for statement in pre_queries or []:
                cursor.execute(statement)
                self.blocks += 1
            cursor.execute(sql)
            names = [d[0] for d in cursor.description]
            rows = [dict(zip(names, [v.read() if hasattr(v, "read") else v for v in row]))
                    for row in cursor.fetchall()]
            for statement in post_queries or []:
                if statement.strip().upper() == "COMMIT":
                    self.conn.commit()
                else:
                    cursor.execute(statement)
        except Exception:
            self.conn.rollback()
            raise
        return pandas.DataFrame(rows, columns=names)


def load(h):
    return parse_lawgo_xml((REAL / h / "source.xml").read_bytes())


def flow(service: IncrementService, checks: dict, label: str) -> None:
    started = time.time()
    for h in GOVERNANCE:
        result = service.ingest(load(h), source_name=h)
        assert result.state == "PREVIEW", (h, result.state, result.gate.get("stop_reason"))
        service.approve(result.load_id, user="checker", preview_digest=result.preview_hash, acknowledge=True)
        service.prepare_index(result.load_id, external=("GOLD",))
        try:
            service.activate(result.load_id, user="checker")
            raise AssertionError("GOLD 미준비인데 활성화됨")
        except IncrementError:
            pass
        service.mark_index(result.load_id, "GOLD", status="READY", count=1, ref="local-check")
        service.activate(result.load_id, user="checker")
    rows = {d: len(service.articles_as_of("LAW:012338", d)) for d in ("20231001", "20240801", "20260301")}
    checks[f"{label}_governance_as_of_counts"] = rows
    assert rows == {"20231001": 51, "20240801": 57, "20260301": 58}, rows
    a26 = [r for r in service.articles_as_of("LAW:012338", "20251231") if r["ARTC_KEY_VALU"] == "26"][0]
    assert a26["ENFC_END_DT"] == "20260101" and "기획재정부" in a26["ARTC_CTNT"]
    a26n = [r for r in service.articles_as_of("LAW:012338", "20260102") if r["ARTC_KEY_VALU"] == "26"][0]
    assert "재정경제부" in a26n["ARTC_CTNT"] and a26n["ENFC_END_DT"] is None
    checks[f"{label}_article26_closed_and_reopened"] = True
    again = service.ingest(load(GOVERNANCE[-1]))
    assert again.reused and again.state == "ACTIVATED"
    checks[f"{label}_rerun_reused"] = True

    first = service.ingest(load(EFINANCE[0]))
    assert service.auto_apply(first.load_id)["decision"] == "APPROVED"        # 사람 승인 대신 게이트 판단
    checks[f"{label}_auto_apply_approved"] = True
    service.prepare_index(first.load_id, external=())
    service.activate(first.load_id, user="checker")
    second = service.ingest(load(EFINANCE[1]))
    assert second.gate["counts"]["ADD"] == 3 and second.gate["counts"]["AMEND"] == 3, second.gate["counts"]
    service.approve(second.load_id, user="checker", preview_digest=second.preview_hash, acknowledge=True)
    service.prepare_index(second.load_id, external=())
    before = [r["ARTC_KEY_VALU"] for r in service.articles_as_of("ADMRUL:21828", "20260801")]
    channel_table = f"{service.owner}.IDD_B003_LGL_SRCH_CHNL"
    wrong = ChannelSwitch(channel_table, "check", "post-a", "post-b", expected_no=99)
    try:
        service.activate(second.load_id, user="checker", channel=wrong)
        raise AssertionError("채널 CAS가 틀렸는데 활성화됨")
    except IncrementError:
        pass
    assert service.job(second.load_id)["PRCS_STTS_CD"] == "INDEXING"
    assert [r["ARTC_KEY_VALU"] for r in service.articles_as_of("ADMRUL:21828", "20260801")] == before
    checks[f"{label}_channel_cas_failure_rolled_back"] = True
    service.activate(second.load_id, user="checker",
                     channel=ChannelSwitch(channel_table, "check", "post-a", "post-b", expected_no=1))
    after = {r["ARTC_KEY_VALU"]: r for r in service.articles_as_of("ADMRUL:21828", "20260801")}
    future = {r["ARTC_KEY_VALU"] for r in service.articles_as_of("ADMRUL:21828", "20261001")}
    assert "56의8" not in after and {"56의8", "56의9"} <= future     # 부칙 예외 2026-10-01 시행 예정
    checks[f"{label}_future_articles_preloaded"] = True
    channel = service.db.query(f"SELECT RFRN_POST_HASH_VALU, CHAN_NO FROM {channel_table} "
                               f"WHERE RFRN_CHNL_NAME='check'")[0]
    assert channel == {"RFRN_POST_HASH_VALU": "post-b", "CHAN_NO": 2}, channel
    checks[f"{label}_channel_switched_in_activation"] = True
    rolled = service.rollback(second.load_id, user="checker", reason="되돌리기 점검",
                              channel=ChannelSwitch(channel_table, "check", "post-b", "post-a", expected_no=2))
    assert rolled["state"] == "ROLLED_BACK"
    assert [r["ARTC_KEY_VALU"] for r in service.articles_as_of("ADMRUL:21828", "20260801")] == before
    assert not {"56의8", "56의9"} & {r["ARTC_KEY_VALU"] for r in service.articles_as_of("ADMRUL:21828", "20261001")}
    channel = service.db.query(f"SELECT RFRN_POST_HASH_VALU, CHAN_NO FROM {channel_table} "
                               f"WHERE RFRN_CHNL_NAME='check'")[0]
    assert channel == {"RFRN_POST_HASH_VALU": "post-a", "CHAN_NO": 3}, channel
    checks[f"{label}_rollback_restored_previous_version_and_channel"] = True
    checks[f"{label}_seconds"] = round(time.time() - started, 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    admin = oracledb.connect(dsn=DSN, user="system", password=system_password())
    users, connections = [], []
    checks: dict = {"dsn": DSN}
    try:
        for label in ("oracledb", "dataiku_block"):
            user = "A8_INC_" + secrets.token_hex(4).upper()
            password = secrets.token_hex(16)
            with admin.cursor() as c:
                c.execute(f'CREATE USER {user} IDENTIFIED BY "{password}" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
                c.execute(f"GRANT CREATE SESSION, CREATE TABLE TO {user}")
            users.append(user)
            conn = oracledb.connect(dsn=DSN, user=user, password=password)
            connections.append(conn)
            db = OracleDatabase(conn) if label == "oracledb" else DataikuDatabase(FakeExecutor(conn))
            service = IncrementService(db, owner=user, today="20261106")
            service.create_schema()
            if label == "oracledb":
                with db.transaction() as tx:
                    for statement in oracle_comments(user):
                        tx.execute(statement)
            with db.transaction() as tx:
                tx.execute(f"CREATE TABLE {user}.IDD_B003_LGL_SRCH_CHNL (RFRN_CHNL_NAME VARCHAR2(100 BYTE) NOT NULL, "
                           f"RFRN_POST_HASH_VALU VARCHAR2(100 BYTE) NOT NULL, CHAN_NO NUMBER(30,0) NOT NULL, "
                           f"CONSTRAINT PK_CHK_CHNL PRIMARY KEY (RFRN_CHNL_NAME))")
            with db.transaction() as tx:
                tx.execute(f"INSERT INTO {user}.IDD_B003_LGL_SRCH_CHNL VALUES ('check', 'post-a', 1)")
            with admin.cursor() as c:
                c.execute("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER=:o ORDER BY 1", o=user)
                tables = [r[0] for r in c.fetchall()]
                c.execute("SELECT COUNT(*) FROM ALL_TAB_COLUMNS WHERE OWNER=:o AND TABLE_NAME LIKE 'IDD_B003_LGL_%' "
                          "AND TABLE_NAME<>'IDD_B003_LGL_SRCH_CHNL'", o=user)
                columns = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM ALL_INDEXES WHERE OWNER=:o", o=user)
                indexes = c.fetchone()[0]
            expected = sorted(t.name for t in TABLES) + ["IDD_B003_LGL_SRCH_CHNL"]
            assert sorted(tables) == sorted(expected), tables
            assert columns == sum(len(t.columns) for t in TABLES), columns
            checks[f"{label}_tables"] = len(tables) - 1
            checks[f"{label}_columns"] = columns
            checks[f"{label}_indexes_incl_pk_lob"] = indexes
            flow(service, checks, label)
            if label == "dataiku_block":
                checks["dataiku_plsql_blocks_executed"] = db.executor.blocks
            with admin.cursor() as c:
                c.execute("SELECT SUM(BYTES) FROM DBA_SEGMENTS WHERE OWNER=:o", o=user)
                checks[f"{label}_segment_bytes"] = int(c.fetchone()[0] or 0)
        checks["result"] = "PASS"
    except Exception as exc:
        checks["result"] = f"FAIL: {type(exc).__name__}: {exc}"
        raise
    finally:
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass
        with admin.cursor() as c:
            for user in users:
                c.execute(f"DROP USER {user} CASCADE")
        checks["temporary_users_dropped"] = users
        Path(args.out).write_text(json.dumps(checks, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(checks, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
