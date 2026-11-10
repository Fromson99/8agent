"""증분 실행기(dataiku_flow) 로컬 Oracle 끝까지 점검 — 새 표 없이 Gold(개발계 G19) 13표 + 관리 폴더 JSON.

실제로 도는 것: dataiku_flow.Flow 의 decide·publish·activate·rollback·cleanup, release_ops SQL(채널 CAS·
VCTR_HEAD·묶음 삭제·Agent 정리), Gold에서 지금 판본 구조 읽기, 구조화 결과 비교·판단, 전체 원문 조립, 기록 3개.
대역: R6(GENOS 구조화·Agent·03 적재)만 — 이미 있는 실제 GENOS 구조화 결과(result.json)로 세대를 만들어
같은 이름·컬럼의 표(R6 코드 ZIP의 개발계 DEV_1 정의로 임시 계정에 생성)에 넣는다. Dataiku SQL은
PL/SQL 블록 + COMMIT 대역. 임시 계정은 끝나면 지운다.

시나리오 (지배구조법 제19913호 → 제21065호 실제 구조화, 재무팀·리스크팀 두 폴더에 같은 파일)
  G0 기준 세대, 서빙 채널 = g19_<G0> (개발계처럼 적재기 채널 이름 그대로)
  1일: 지배구조법 21065 + 잘린 상법 + 내규 v2 → 승인 2·보류 1 → G1, 두 팀 폴더 모두 교체
  2일: 내규 v3 → G2      3일: 내규 v4 → G3 → G0 정리(서빙 채널 행은 남음)
  되돌리기 3번: G3→G2(채널), G2→G1(채널), G1→G0(지워져서 다시 만들어 게시)

사용: .venv/bin/python 06_TOOLS/maintenance/check_increment_flow_oracle.py --out <결과.json>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.increment import history  # noqa: E402
from lawrag.increment.corpus import write_zip  # noqa: E402
from lawrag.increment.dataiku_flow import Flow, Params, Stop  # noqa: E402
from lawrag.increment.release_ops import (DataikuSql, Names, channel, generation, privilege_check,  # noqa: E402
                                          releases)

CONTAINER, DSN = "a8-legal-mapped-20261023", "127.0.0.1:11524/FREEPDB1"
R6_ZIP = ROOT / "08_DEPLOYMENT/DATAIKU/agent_layer_zip_20261105_r6/DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip"
STRUCT = ROOT / "01_DATA/PACKAGES/EXTERNAL/ontology-operational-8def52ccda54d7b0/gen-8def52ccda54d7b01cce8a4a/ARTIFACTS/STRUCTURE"
GOV_OLD, GOV_NEW = "1ab2b728e6280db5", "c4b33879c7dc5554"
OTHER = "c9b5b42627710637"           # 금융투자업규정 (행정규칙) 실제 구조화 결과
GOV_NAME = "금융회사의 지배구조에 관한 법률"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def system_password() -> str:
    info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
    for item in info["Config"]["Env"]:
        if item.startswith(("ORACLE_PWD=", "ORACLE_PASSWORD=")):
            return item.split("=", 1)[1]
    raise SystemExit("system 비밀번호 없음")


class FakeExecutor:
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
            rows = [dict(zip(names, [v.read() if hasattr(v, "read") else v for v in row])) for row in cursor.fetchall()]
            for statement in post_queries or []:
                if statement.strip().upper() == "COMMIT":
                    self.conn.commit()
                else:
                    cursor.execute(statement)
        except Exception:
            self.conn.rollback()
            raise
        return pandas.DataFrame(rows, columns=names)


def r6_names(owner: str, code_dir: Path) -> tuple[Names, object]:
    sys.path[:0] = [str(code_dir), str(code_dir / "engine")]
    from prod_config import target
    import gold_io
    tgt = target({"TARGET_MODE": "DEV_1"})
    for t in tgt["tables"].values():
        t["owner"] = owner
    path = code_dir / "check-contract.json"
    path.write_text(json.dumps(tgt))
    return Names(tgt), gold_io.Contract(path)


# ------------------------------------------------------------------ 구조화 결과 (실제 + 합성)

def real(h):
    d = STRUCT / h
    return (d / "source.xml").read_bytes(), json.loads((d / "result.json").read_text(encoding="utf-8"))


def truncated(result: dict, keep_articles: int = 3) -> dict:
    """앞쪽 조문 몇 개만 남긴 잘린 구조 (파일이 잘려 온 경우)."""
    nodes, blocks = result["nodes"], result["blocks"]
    arts = [n for n in nodes if n["family"] == "kr_article" and n.get("coordinate_scope") == "body"]
    cut = arts[keep_articles]["block"]
    keep_blocks = [b for b in blocks if b["idx"] < cut]
    keep_ids = {b["node"] for b in keep_blocks} | {n["id"] for n in nodes if n["block"] < cut}
    out_nodes = []
    for n in nodes:
        if n["id"] in keep_ids:
            n = dict(n, span=[n["span"][0], min(n["span"][1], cut)])
            if n["parent"] is not None and n["parent"] not in keep_ids:
                n["parent"] = None
            out_nodes.append(n)
    return {"nodes": out_nodes, "blocks": keep_blocks}


def rule_tree(article3: str) -> dict:
    nodes, blocks = [], []

    def node(family, surface, title, lines, parent=None, scope=None):
        nid = len(nodes)
        n = {"id": nid, "parent": parent, "level": 0 if parent is None else 1, "family": family,
             "surface": surface, "title": title, "block": len(blocks), "span": [len(blocks), len(blocks)]}
        if scope:
            n["coordinate_scope"] = scope
        nodes.append(n)
        for line in lines:
            blocks.append({"idx": len(blocks), "text": line, "kind": "text", "node": nid})
        n["span"][1] = len(blocks)
        return nid
    ch = node("kr_장", "제1장", "제1장 총칙", ["제1장 총칙"])
    node("kr_article", "제1조", "목적", ["제1조(목적) 이 기준은 내부통제에 관한 사항을 정한다."], ch, "body")
    node("kr_article", "제2조", "적용", ["제2조(적용) 이 기준은 모든 임직원에게 적용한다."], ch, "body")
    node("kr_article", "제3조", "보고", [article3], ch, "body")
    nodes[ch]["span"][1] = len(blocks)
    bu = node("buchik", "부칙", "부칙", ["부칙"])
    node("kr_article", "부칙", "부칙 <제1호, 20250101>", ["부칙 <제1호, 20250101>", "이 기준은 2025년 1월 1일부터 시행한다."], bu, "addendum")
    nodes[bu]["span"][1] = len(blocks)
    return {"nodes": nodes, "blocks": blocks}


# ------------------------------------------------------------------ R6 대역

class FakeR6:
    """GENOS 구조화·Agent·03 적재 대역. 원문 sha → 구조화 결과는 등록해 둔 것을 쓴다."""

    def __init__(self, conn, contract, inputs: history.LocalStore, agent_table: str):
        self.conn, self.c, self.inputs, self.agent_table = conn, contract, inputs, agent_table
        self.results: dict[str, dict] = {}
        self.trials: dict[str, dict] = {}
        self.calls = []

    def register(self, data: bytes, result: dict, name: str):
        self.results[sha(data)] = {"result": result, "name": name}

    def _files(self, zip_name, zip_sha):
        raw = self.inputs.get(zip_name)
        assert raw is not None and sha(raw) == zip_sha, "입력 ZIP 해시"
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return {e.filename: z.read(e) for e in z.infolist() if not e.is_dir()}

    def step(self, op, trial, zip_name, zip_sha):
        self.calls.append((op, trial))
        t = self.trials.setdefault(trial, {"job": secrets.token_hex(16), "zip": (zip_name, zip_sha)})
        assert t["zip"] == (zip_name, zip_sha), "같은 trial에 다른 입력"
        if op == "submit":
            cur = self.conn.cursor()
            for i in range(3):                            # Agent 결과 조각 흉내
                cur.execute(f"INSERT INTO {self.agent_table} (JOB_ID, SEQ_NO) VALUES (:j, :s)", j=t["job"], s=i)
            self.conn.commit()
        elif op == "load":
            t["report"] = self.load(self._files(zip_name, zip_sha))
        return {"job": t["job"]}

    def job(self, trial, zip_name, zip_sha):
        return self.trials[trial]["job"]

    def restore_generation(self, trial, zip_name, zip_sha, dest: Path):
        files = self._files(zip_name, zip_sha)
        gen = dest / "restored/generation"
        gen.mkdir(parents=True)
        db = sqlite3.connect(gen / "store.sqlite")
        db.executescript("CREATE TABLE document(document_id,name,source_artifact_sha256,json);"
                         "CREATE TABLE source_unit(document_id,unit_id,parent_id,json);"
                         "CREATE TABLE source_block(document_id,block_id,unit_id,text,source_artifact_sha256,json);")
        for member, data in files.items():
            r = self.results.get(sha(data))
            if r is None:
                continue
            did = sha(data)[:16]
            db.execute("INSERT INTO document VALUES (?,?,?,?)", (did, r["name"], sha(data), "{}"))
            for n in r["result"]["nodes"]:
                db.execute("INSERT INTO source_unit VALUES (?,?,?,?)", (did, str(n["id"]), n.get("parent"), json.dumps(n, ensure_ascii=False)))
            for b in r["result"]["blocks"]:
                meta = {k: v for k, v in b.items() if k != "text"}
                db.execute("INSERT INTO source_block VALUES (?,?,?,?,?,?)",
                           (did, str(b["idx"]), b.get("node"), b["text"], sha(data), json.dumps(meta, ensure_ascii=False)))
        db.commit()
        db.close()
        return gen, self.trials[trial]["job"]

    def report(self, trial, zip_name, zip_sha):
        return self.trials[trial]["report"]

    def load(self, files: dict) -> dict:
        """세대 하나를 13표에 넣는다 (VCTR_HEAD 없이, 적재기 자기 채널 g19_ 행 포함) — 03 흉내."""
        docs = {}
        for member, data in sorted(files.items()):
            r = self.results.get(sha(data))
            if r is not None:
                docs[sha(data)[:16]] = (data, r)
        ids = sorted(docs)
        dataset = sha(("ds|" + ",".join(ids)).encode())
        source = sha(("src|" + dataset).encode())
        query = sha(("q|" + dataset).encode())
        vpost = "v" + sha(("vec|" + query).encode())[:31]
        cur = self.conn.cursor()
        T, C = self.c.table, self.c.col
        exists = cur.execute(f"SELECT COUNT(*) FROM {T('SRCH_POST')} WHERE {C('SRCH_POST','RFRN_POST_HASH_VALU')}=:q", q=query).fetchone()[0]
        exists += cur.execute(f"SELECT COUNT(*) FROM {T('SRCH_CHNL')} WHERE {C('SRCH_CHNL','RFRN_CHNL_NAME')}=:c", c="g19_" + query[:24]).fetchone()[0]
        if exists:                                        # 실제 적재기: EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT
            raise RuntimeError("EXISTING_RELEASE")
        for did, (data, r) in docs.items():
            cur.execute(f"INSERT INTO {T('DOC_VER')} ({C('DOC_VER','MNFST_HASH_VALU')},{C('DOC_VER','DOC_ID')},{C('DOC_VER','DOC_NAME')},{C('DOC_VER','DOC_HASH_VALU')}) VALUES (:a,:b,:c,:d)",
                        a=dataset, b=did, c=r["name"], d=sha(data))
            for n in r["result"]["nodes"]:
                cur.execute(f"INSERT INTO {T('DOC_UNIT')} ({C('DOC_UNIT','MNFST_HASH_VALU')},{C('DOC_UNIT','DOC_ID')},{C('DOC_UNIT','STRC_UNIT_ID')},{C('DOC_UNIT','UPPR_STRC_UNIT_ID')},{C('DOC_UNIT','STRC_UNIT_ADDN_IFMN_CTNT')}) VALUES (:a,:b,:c,:d,:e)",
                            a=dataset, b=did, c=str(n["id"]), d=None if n.get("parent") is None else str(n["parent"]), e=json.dumps(n, ensure_ascii=False))
            for b in r["result"]["blocks"]:
                meta = {k: v for k, v in b.items() if k != "text"}
                cur.execute(f"INSERT INTO {T('DOC_BLK')} ({C('DOC_BLK','MNFST_HASH_VALU')},{C('DOC_BLK','DOC_ID')},{C('DOC_BLK','BODY_SLC_ID')},{C('DOC_BLK','STRC_UNIT_ID')},{C('DOC_BLK','BODY_CTNT')},{C('DOC_BLK','DOC_HASH_VALU')},{C('DOC_BLK','BODY_SLC_ADDN_IFMN_CTNT')}) VALUES (:a,:b,:c,:d,:e,:f,:g)",
                            a=dataset, b=did, c=str(b["idx"]), d=None if b.get("node") is None else str(b["node"]), e=b["text"], f=sha(data), g=json.dumps(meta, ensure_ascii=False))
            for k in range(2):
                cur.execute(f"INSERT INTO {T('SRCH_ROW')} ({C('SRCH_ROW','RFRN_POST_HASH_VALU')},{C('SRCH_ROW','RFRN_DTA_TYPE_VALU')},{C('SRCH_ROW','RFRN_DTA_ID')},{C('SRCH_ROW','DOC_ID')}) VALUES (:a,'unit',:b,:c)",
                            a=query, b=f"{did}:{k}", c=did)
            cur.execute(f"INSERT INTO {T('VCTR_ITEM')} ({C('VCTR_ITEM','VCTR_POST_ID')},{C('VCTR_ITEM','VCTR_SEG_ID')},{C('VCTR_ITEM','DOC_ID')}) VALUES (:a,:b,:c)",
                        a=vpost, b=did + ":0", c=did)
        cur.execute(f"INSERT INTO {T('SRC_POST')} ({C('SRC_POST','DOC_POST_HASH_VALU')},{C('SRC_POST','MNFST_HASH_VALU')},{C('SRC_POST','DOC_POST_IFMN_CTNT')}) VALUES (:a,:b,:c)",
                    a=source, b=dataset, c=json.dumps({"dataset_version": dataset}))
        cur.execute(f"INSERT INTO {T('SRCH_POST')} ({C('SRCH_POST','RFRN_POST_HASH_VALU')},{C('SRCH_POST','RFRN_POST_IFMN_CTNT')}) VALUES (:a,:b)",
                    a=query, b=json.dumps({"status": "COMPLETE", "source_release_id": source, "dataset_version": dataset,
                                           "source_manifest": {"scope": {"document_version_ids": ids}}}))
        cur.execute(f"INSERT INTO {T('SRCH_CHNL')} ({C('SRCH_CHNL','RFRN_CHNL_NAME')},{C('SRCH_CHNL','RFRN_POST_HASH_VALU')},{C('SRCH_CHNL','CHAN_NO')}) VALUES (:a,:b,1)",
                    a="g19_" + query[:24], b=query)
        cur.execute(f"INSERT INTO {T('VCTR_POST')} ({C('VCTR_POST','VCTR_POST_ID')},{C('VCTR_POST','VCTR_POST_IFMN_CTNT')}) VALUES (:a,:b)", a=vpost,
                    b=json.dumps({"manifest": {"query_id": query}, "completion": {"status": "READY"}}))
        self.conn.commit()
        return {"status": "DEV_LOADED", "target_layer": "Silver", "checks": True, "query_release_id": query,
                "source_release_id": source, "vector": {"publication_id": vpost}, "counts": {"DOC_VER": len(docs)}}


def required_columns_only(contract, key):
    """시험 표는 대역이 채우는 컬럼만 NOT NULL을 지킨다 (실제 정의의 나머지 필수 컬럼은 NULL 허용으로)."""
    t = contract.tables[key]
    fields = [c["name"] + " " + c["type"] for c in t["columns"].values()]
    fields.append("CONSTRAINT X0_" + t["name"] + " PRIMARY KEY (" + ",".join(contract.col(key, n) for n in t["primary_key"]) + ")")
    return "CREATE TABLE " + contract.table(key) + " (" + ",".join(fields) + ")"


def count_rows(cur, names: Names, query_id: str) -> dict:
    return {k: cur.execute(f"SELECT COUNT(*) FROM {names.t(k)} WHERE {names.c(k, 'RFRN_POST_HASH_VALU')}=:q", q=query_id).fetchone()[0]
            for k in ("SRCH_ROW", "SRCH_POST", "VCTR_HEAD")}


def main(argv=None) -> int:
    import oracledb
    oracledb.defaults.fetch_lobs = False
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    checks: dict = {}
    admin = oracledb.connect(dsn=DSN, user="system", password=system_password())
    user = "A8_INCF_" + secrets.token_hex(4).upper()
    password = "P" + secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix="increment-flow-") as tmp:
        tmp = Path(tmp)
        code = tmp / "r6"
        with zipfile.ZipFile(R6_ZIP) as z:
            z.extractall(code)
        names, contract = r6_names(user, code)
        c = admin.cursor()
        c.execute(f'CREATE USER {user} IDENTIFIED BY "{password}" DEFAULT TABLESPACE USERS QUOTA 256M ON USERS')
        c.execute(f"GRANT CREATE SESSION, CREATE TABLE TO {user}")
        try:
            conn = oracledb.connect(dsn=DSN, user=user, password=password)
            cur = conn.cursor()
            for key in ("DOC_VER", "DOC_UNIT", "DOC_BLK", "SRC_POST", "SRCH_POST", "SRCH_ROW", "SRCH_CHNL",
                        "VCTR_POST", "VCTR_ITEM", "VCTR_HEAD"):
                cur.execute(required_columns_only(contract, key))
            agent_table = f"{user}.LGL_PIPE_RESULT_A"
            cur.execute(f"CREATE TABLE {agent_table} (JOB_ID VARCHAR2(32) NOT NULL, SEQ_NO NUMBER(12) NOT NULL, "
                        f"PRIMARY KEY (JOB_ID, SEQ_NO))")
            db = DataikuSql(FakeExecutor(conn))
            owner_check = privilege_check(db, names, agent_table=agent_table)
            assert owner_check["ok"], owner_check
            other = "A8_INCG_" + secrets.token_hex(4).upper()
            c.execute(f'CREATE USER {other} IDENTIFIED BY "{password}"')
            c.execute(f"GRANT CREATE SESSION TO {other}")
            try:
                conn2 = oracledb.connect(dsn=DSN, user=other, password=password)
                denied = privilege_check(DataikuSql(FakeExecutor(conn2)), names, agent_table=agent_table)
                c.execute(f"GRANT DELETE ON {names.t('SRCH_ROW')} TO {other}")
                partial = privilege_check(DataikuSql(FakeExecutor(conn2)), names, agent_table=agent_table)
                conn2.close()
            finally:
                c.execute(f"DROP USER {other} CASCADE")
            assert not denied["ok"] and all(not r["ok"] for r in denied["checks"])
            assert [r["check"] for r in partial["checks"] if r["ok"]] == ["DELETE SRCH_ROW"]
            checks["privilege_check"] = {"owner": owner_check["ok"], "no_grant": denied["checks"][0]["oracle"],
                                         "one_grant_ok": [r["check"] for r in partial["checks"] if r["ok"]]}
            store, drop, inputs = (history.LocalStore(tmp / n) for n in ("state", "drop", "input"))
            r6 = FakeR6(conn, contract, inputs, agent_table)

            gov_old, gov_old_r = real(GOV_OLD)
            gov_new, gov_new_r = real(GOV_NEW)
            other, other_r = real(OTHER)
            rule = {v: (f"PK-docx-v{v}".encode(), rule_tree(f"제3조(보고) 위반 사실은 {v}영업일 이내에 보고한다."))
                    for v in (1, 2, 3, 4)}
            r6.register(gov_old, gov_old_r, f"external > financial_team > law > {GOV_NAME}")
            r6.register(gov_new, gov_new_r, f"external > financial_team > law > {GOV_NAME}")
            r6.register(other, other_r, "external > financial_team > law > 금융투자업규정")
            cut = other.replace(b"<", b"<", 1) + b"\n<!-- cut -->"
            r6.register(cut, truncated(other_r), "external > financial_team > law > 금융투자업규정")
            for v, (data, tree) in rule.items():
                r6.register(data, tree, "internal > risk_team > 내부통제기준")

            base = {f"external/financial_team/law/{GOV_NAME}/{GOV_NAME} 본문.xml": gov_old,
                    f"external/risk_team/law/{GOV_NAME}/{GOV_NAME} 본문.xml": gov_old,
                    "external/financial_team/law/금융투자업규정/금융투자업규정 본문.xml": other,
                    "internal/risk_team/내부통제기준_20250101.docx": rule[1][0]}
            base_zip = write_zip(base)
            inputs.put("BASE.zip", base_zip)
            g0 = r6.load(base)["query_release_id"]
            bad = Flow(store=store, drop=drop, inputs=inputs, db=db, agent_db=db, names=names, r6=r6,
                       params=Params(channel="g19_" + g0[:24], base_zip_name="BASE.zip"), log=lambda m: None)
            try:
                bad.status()
                raise AssertionError("g19_ 서빙 채널을 막지 않음")
            except Stop as exc:
                assert "SERVING_CHANNEL_IS_LOADER_CHANNEL" in str(exc)
            checks["loader_channel_as_serving_refused"] = True
            cur.execute(f"INSERT INTO {names.t('SRCH_CHNL')} ({names.c('SRCH_CHNL','RFRN_CHNL_NAME')},"
                        f"{names.c('SRCH_CHNL','RFRN_POST_HASH_VALU')},{names.c('SRCH_CHNL','CHAN_NO')}) "
                        f"SELECT 'main', {names.c('SRCH_CHNL','RFRN_POST_HASH_VALU')}, 1 FROM {names.t('SRCH_CHNL')} "
                        f"WHERE {names.c('SRCH_CHNL','RFRN_CHNL_NAME')}=:c", c="g19_" + g0[:24])
            conn.commit()
            serving = "main"
            params = Params(channel=serving, base_zip_name="BASE.zip", today="20260110", agent_table=agent_table,
                            prune_batch=3)
            flow = Flow(store=store, drop=drop, inputs=inputs, db=db, agent_db=db, names=names, r6=r6, params=params,
                        log=lambda m: None)
            checks["status_before"] = flow.status()["base_zip"]["ok"]

            # ---- 1일
            drop.put(f"external/financial_team/law/{GOV_NAME}/{GOV_NAME} 본문.xml", gov_new)
            drop.put("cut/금융투자업규정 본문.xml", cut)
            drop.put("internal/risk_team/내부통제기준_20260101.docx", rule[2][0])
            d1 = flow.decide("d1")
            dec = store.get_json("runs/d1/decide.json")
            by = {e["file"]: e for e in dec["entries"]}
            checks["d1_summary"] = d1["summary"]
            assert by[f"{GOV_NAME} 본문.xml"]["decision"] == "APPROVED", by[f"{GOV_NAME} 본문.xml"]
            assert by["금융투자업규정 본문.xml"]["decision"] == "HOLD", by["금융투자업규정 본문.xml"]["decision"]
            assert by["내부통제기준_20260101.docx"]["decision"] == "APPROVED"
            assert [x for x in by[f"{GOV_NAME} 본문.xml"]["changes"] if x["new"] == "26"]
            cmp_job = r6.trials["inc-d1-cmp"]["job"]
            assert cur.execute(f"SELECT COUNT(*) FROM {agent_table} WHERE JOB_ID=:j", j=cmp_job).fetchone()[0] == 0
            assert inputs.get("INCREMENT_d1_CMP.zip") is None
            checks["d1_compare_agent_rows_deleted"] = True
            again = flow.decide("d1b")
            assert again["summary"].get("ALREADY") == 1 and again["summary"].get("APPROVED") == 2   # 보류는 다시 안 봄
            assert not [t for t in r6.trials if t == "inc-d1b-cmp"]                                  # 구조화 재사용
            checks["d1_rerun_reuses_structure"] = True

            p1 = flow.publish("d1")
            g1 = p1["query_release_id"]
            assert channel(db, names, serving)["query_id"] == g0                  # 게시만으로는 서빙 안 바뀜
            a1 = flow.activate("d1")
            assert channel(db, names, serving)["query_id"] == g1
            assert generation(db, names, g1).vector_post_id                      # VCTR_HEAD 생김
            assert cur.execute(f"SELECT COUNT(*) FROM {agent_table}").fetchone()[0] == 0
            with zipfile.ZipFile(io.BytesIO(inputs.get(p1 and store.get_json('runs/d1/publish.json')['zip']['name']))) as z:
                full = {e.filename: z.read(e) for e in z.infolist()}
            assert full[f"external/financial_team/law/{GOV_NAME}/{GOV_NAME} 본문.xml"] == gov_new
            assert full[f"external/risk_team/law/{GOV_NAME}/{GOV_NAME} 본문.xml"] == gov_new      # 두 팀 폴더 동시
            assert full["external/financial_team/law/금융투자업규정/금융투자업규정 본문.xml"] == other    # 보류 문서 유지
            assert "internal/risk_team/내부통제기준_20260101.docx" in full and "internal/risk_team/내부통제기준_20250101.docx" not in full
            u1 = history.updates(store)[-1]
            assert len(u1["old_files"]) == 3 and u1["channel_before"]["query_id"] == g0
            checks["d1_activate"] = {"update": a1["update"], "prune": a1["prune"]}

            gens = [g0, g1]
            g0_keys = next(r for r in releases(db, names) if r["query_id"] == g0)
            for day, v in ((2, 3), (3, 4)):
                drop.delete("internal/risk_team/" + [p for p in drop.list("internal/") if p.endswith(".docx")][0].split("/")[-1])
                drop.put(f"internal/risk_team/내부통제기준_2026010{day}.docx", rule[v][0])
                flow.decide(f"d{day}")
                flow.publish(f"d{day}")
                out = flow.activate(f"d{day}")
                gens.append(store.get_json(f"runs/d{day}/publish.json")["report"]["query_release_id"])
                checks[f"d{day}_prune"] = out["prune"]
            g2, g3 = gens[2], gens[3]
            alive = {r["query_id"] for r in releases(db, names)}
            assert alive == {g1, g2, g3}, alive                                   # 지금 + 이전 2개만
            assert all(v == 0 for v in count_rows(cur, names, g0).values())
            left = {}
            for key, col, val in (("DOC_VER", "MNFST_HASH_VALU", g0_keys["dataset_version"]),
                                  ("DOC_UNIT", "MNFST_HASH_VALU", g0_keys["dataset_version"]),
                                  ("DOC_BLK", "MNFST_HASH_VALU", g0_keys["dataset_version"]),
                                  ("SRC_POST", "DOC_POST_HASH_VALU", g0_keys["source_release_id"]),
                                  ("VCTR_POST", "VCTR_POST_ID", g0_keys["vector_post_id"]),
                                  ("VCTR_ITEM", "VCTR_POST_ID", g0_keys["vector_post_id"]),
                                  ("SRCH_CHNL", "RFRN_POST_HASH_VALU", g0)):
                left[key] = cur.execute(f"SELECT COUNT(*) FROM {names.t(key)} WHERE {names.c(key, col)}=:v", v=val).fetchone()[0]
            assert not any(left.values()), left
            checks["g0_rows_left_after_prune"] = left
            assert cur.execute(f"SELECT COUNT(*) FROM {names.t('DOC_VER')}").fetchone()[0] == 9   # 3세대 × 3문서
            assert channel(db, names, serving)["query_id"] == g3                  # 서빙 채널 행은 그대로
            assert len(history.updates(store)) == 3
            checks["three_generations_kept_and_g0_pruned"] = True

            # ---- 되돌리기
            r1 = flow.rollback("rb1")
            assert r1["method"] == "CHANNEL" and channel(db, names, serving)["query_id"] == g2
            r2 = flow.rollback("rb2")
            assert r2["method"] == "CHANNEL" and channel(db, names, serving)["query_id"] == g1
            r3 = flow.rollback("rb3")
            assert r3["method"] == "REBUILD" and channel(db, names, serving)["query_id"] == g0   # 같은 내용 → 같은 세대 ID
            assert generation(db, names, g0).vector_post_id
            with zipfile.ZipFile(io.BytesIO(inputs.get(history.state(store)["corpus"]["name"]))) as z:
                restored = {e.filename: z.read(e) for e in z.infolist()}
            assert restored == base, sorted(set(restored) ^ set(base))
            checks["rollback_three_steps"] = [r1["method"], r2["method"], r3["method"]]
            try:
                flow.rollback("rb4")
                raise AssertionError("기록 없는 되돌리기가 됨")
            except Stop:
                pass
            status = flow.status()
            assert status["base_zip"]["ok"]
            checks["status_after"] = {"documents": status["documents"], "updates": [u["status"] for u in status["updates"]]}
            checks["r6_calls"] = len(r6.calls)
            checks["result"] = "PASS"
        finally:
            for conn_ in (locals().get("conn"),):
                try:
                    conn_ and conn_.close()
                except Exception:
                    pass
            c.execute(f"DROP USER {user} CASCADE")
            checks["temporary_user_dropped"] = user
    Path(args.out).write_text(json.dumps(checks, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
