"""증분 실험을 Gold 시험 복사본(TST_B003_LGL_*)에서 — 로컬 Oracle 끝까지 점검.

개발계에서 할 실험의 순서를 그대로 밟는다 (전달 SQL 파일을 소유자만 바꿔 그대로 실행):
  1. 지금 Gold(IDD_B003_LGL_*, 실제 제약 그대로) = 서빙 중인 세대 G0 + main 채널   ← 개발계 SIDDS 상태 흉내
  2. CREATE_TEST_COPY: 같은 정의의 빈 시험 복사본 13표 (데이터 복사 없음)
  3. 시험 복사본에 작은 기준 세대 적재 (R7 03_LOAD를 LGL_GOLD_TABLE_PREFIX=TST_B003_LGL_로 돌린 것의 대역)
     + MAIN_CHANNEL SQL로 main 채널
  4. 증분 실행기(dataiku_flow.Flow)를 시험 복사본 이름으로: 1일(승인 2·보류 1) → 2·3일 → 세대 3개만 남김 → 되돌리기 3번
  5. 처음부터 끝까지 원래 Gold 표는 한 행도 안 바뀜, DROP_TEST_COPY로 복사본만 지움
대역: R6/R7(GENOS 구조화·Agent·03 적재)만 — 실제 GENOS 구조화 결과(result.json)로 세대를 만든다.

사용: .venv/bin/python 06_TOOLS/maintenance/check_increment_gold_copy_oracle.py --out <결과.json> [--container a8-agent-zip-r7]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import secrets
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))
PKG = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1"
_spec = importlib.util.spec_from_file_location("inc_flow_check", Path(__file__).with_name("check_increment_flow_oracle.py"))
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)

from lawrag.increment import history  # noqa: E402
from lawrag.increment.corpus import write_zip  # noqa: E402
from lawrag.increment.dataiku_flow import Flow, Params, Stop  # noqa: E402
from lawrag.increment.release_ops import DataikuSql, Names, channel, generation, privilege_check, releases  # noqa: E402

KEYS = ("DOC_VER", "DOC_UNIT", "DOC_BLK", "SRC_POST", "SRCH_POST", "SRCH_ROW", "SRCH_CHNL",
        "ONTL_POST", "ONTL_HEAD", "ONTL_ANC", "VCTR_POST", "VCTR_ITEM", "VCTR_HEAD")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def delivered(name: str, old_owner: str, owner: str) -> list[str]:
    text = (PKG / name).read_text(encoding="utf-8")
    return [b.split("\n", 1)[1].strip().replace(old_owner + ".", owner + ".") for b in text.split("-- [")[1:]]


class GoldFakeR6(OLD.FakeR6):
    """03 적재 대역 — Gold 필수 컬럼(검색 행 내용·벡터·벡터 설명)까지 채워 실제 제약을 통과한다."""

    def step(self, op, trial, zip_name, zip_sha):
        """Agent 결과 조각 흉내 — 실제 중간표의 필수 컬럼·CHECK 제약을 지킨다 (조각 2개 + READY 0번)."""
        self.calls.append((op, trial))
        t = self.trials.setdefault(trial, {"job": secrets.token_hex(16), "zip": (zip_name, zip_sha)})
        assert t["zip"] == (zip_name, zip_sha), "같은 trial에 다른 입력"
        if op == "submit":
            cur = self.conn.cursor()
            for seq, parts in ((1, 0), (2, 0), (0, 2)):
                cur.execute(f"INSERT INTO {self.agent_table} (JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT,BODY_B64) "
                            "VALUES (:j,:s,:b,:d,10,:p,:body)", j=t["job"], s=seq, b="0" * 64, d="1" * 64, p=parts,
                            body=None if seq == 0 else "QUJD")
            self.conn.commit()
        elif op == "load":
            t["report"] = self.load(self._files(zip_name, zip_sha))
        return {"job": t["job"]}

    def load(self, files: dict, contract=None) -> dict:
        c = contract or self.c
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
        T, C = c.table, c.col
        exists = cur.execute(f"SELECT COUNT(*) FROM {T('SRCH_POST')} WHERE {C('SRCH_POST','RFRN_POST_HASH_VALU')}=:q", q=query).fetchone()[0]
        exists += cur.execute(f"SELECT COUNT(*) FROM {T('SRCH_CHNL')} WHERE {C('SRCH_CHNL','RFRN_CHNL_NAME')}=:c", c="g19_" + query[:24]).fetchone()[0]
        if exists:
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
                cur.execute(f"INSERT INTO {T('SRCH_ROW')} ({C('SRCH_ROW','RFRN_POST_HASH_VALU')},{C('SRCH_ROW','RFRN_DTA_TYPE_VALU')},{C('SRCH_ROW','RFRN_DTA_ID')},{C('SRCH_ROW','DOC_ID')},{C('SRCH_ROW','SRCH_DATA_HASH_VALU')},{C('SRCH_ROW','SRCH_DATA_CTNT')}) VALUES (:a,'unit',:b,:c,:h,:t)",
                            a=query, b=f"{did}:{k}", c=did, h=sha(f"{did}:{k}".encode()), t=json.dumps({"unit": k}))
            cur.execute(f"INSERT INTO {T('VCTR_ITEM')} ({C('VCTR_ITEM','VCTR_POST_ID')},{C('VCTR_ITEM','VCTR_SEG_ID')},{C('VCTR_ITEM','DOC_ID')},{C('VCTR_ITEM','SRC_UNIT_ID')},{C('VCTR_ITEM','VCTR_META_CTNT')},{C('VCTR_ITEM','EMBD_VCTR_VALU')}) VALUES (:a,:b,:c,:u,:m,TO_VECTOR('[0.5,0.25,0.125]',3,FLOAT32))",
                        a=vpost, b=did + ":0", c=did, u=did + ":0", m="{}")
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
        return {"status": "GOLD_LOADED", "target_layer": "Gold", "checks": True, "query_release_id": query,
                "source_release_id": source, "vector": {"publication_id": vpost}, "counts": {"DOC_VER": len(docs)}}


def contract(code_dir: Path, owner: str, prefix: str):
    sys.path[:0] = [str(code_dir), str(code_dir / "engine")]
    from prod_config import target
    import gold_io
    tgt = target({"TARGET_MODE": "GOLD", "GOLD_OWNER": owner, "TABLE_PREFIX": prefix})
    path = code_dir / f"contract-{prefix}.json"
    path.write_text(json.dumps(tgt))
    return Names(tgt), gold_io.Contract(path)


def snapshot(cur, names: Names) -> dict:
    """표마다 행 수 + 모든 컬럼(LOB 제외) 내용 해시 — 원래 Gold가 안 바뀌었는지 비교용."""
    out = {}
    for key in KEYS:
        t = names.tables[key]
        cols = [c["name"] for c in t["columns"].values() if c["type"] not in ("CLOB",) and not c["type"].startswith("VECTOR")]
        rows = cur.execute(f"SELECT {','.join(cols)} FROM {names.t(key)} ORDER BY {','.join(cols)}").fetchall()
        out[key] = {"rows": len(rows), "sha": sha(json.dumps([[str(v) for v in r] for r in rows]).encode())}
    return out


def main(argv=None) -> int:
    import oracledb
    oracledb.defaults.fetch_lobs = False
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--container", default="a8-agent-zip-r7")
    args = ap.parse_args(argv)
    info = json.loads(subprocess.check_output(["docker", "inspect", args.container]))[0]
    env = dict(x.split("=", 1) for x in info["Config"]["Env"])
    port = info["NetworkSettings"]["Ports"]["1521/tcp"][0]
    assert port["HostIp"] == "127.0.0.1"
    dsn = f"127.0.0.1:{port['HostPort']}/FREEPDB1"
    admin = oracledb.connect(dsn=dsn, user="system", password=env["ORACLE_PASSWORD"])
    user = "A8_INCG_" + secrets.token_hex(4).upper()
    password = "P" + secrets.token_hex(12)
    checks: dict = {"oracle": admin.version}
    with tempfile.TemporaryDirectory(prefix="increment-gold-copy-") as tmp:
        tmp = Path(tmp)
        code = tmp / "r7"
        with zipfile.ZipFile(PKG / "DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip") as z:
            z.extractall(code)
        gold_names, gold_c = contract(code, user, "IDD_B003_LGL_")
        test_names, test_c = contract(code, user, "TST_B003_LGL_")
        c = admin.cursor()
        c.execute(f'CREATE USER {user} IDENTIFIED BY "{password}" DEFAULT TABLESPACE USERS QUOTA 256M ON USERS')
        c.execute(f"GRANT CREATE SESSION, CREATE TABLE TO {user}")
        try:
            conn = oracledb.connect(dsn=dsn, user=user, password=password)
            cur = conn.cursor()
            # 1. 지금 Gold (운영 정의 그대로) + Agent 중간표
            for stmt in delivered("CREATE_GOLD_TABLES_SIDDG_R1.txt", "SIDDG", user):
                cur.execute(stmt)
            agent_table = f"{user}.LGL_PIPE_RESULT_A"
            cur.execute(delivered("CREATE_AGENT_STAGE_R1.txt", "SIDDA", user)[0])
            db = DataikuSql(OLD.FakeExecutor(conn))
            store, drop, inputs = (history.LocalStore(tmp / n) for n in ("state", "drop", "input"))
            r6 = GoldFakeR6(conn, test_c, inputs, agent_table)
            gov_old, gov_old_r = OLD.real(OLD.GOV_OLD)
            gov_new, gov_new_r = OLD.real(OLD.GOV_NEW)
            other, other_r = OLD.real(OLD.OTHER)
            rule = {v: (f"PK-docx-v{v}".encode(), OLD.rule_tree(f"제3조(보고) 위반 사실은 {v}영업일 이내에 보고한다."))
                    for v in (1, 2, 3, 4)}
            name = OLD.GOV_NAME
            r6.register(gov_old, gov_old_r, f"external > financial_team > law > {name}")
            r6.register(gov_new, gov_new_r, f"external > financial_team > law > {name}")
            r6.register(other, other_r, "external > financial_team > law > 금융투자업규정")
            cut = other + b"\n<!-- cut -->"
            r6.register(cut, OLD.truncated(other_r), "external > financial_team > law > 금융투자업규정")
            for v, (data, tree) in rule.items():
                r6.register(data, tree, "internal > risk_team > 내부통제기준")
            base = {f"external/financial_team/law/{name}/{name} 본문.xml": gov_old,
                    f"external/risk_team/law/{name}/{name} 본문.xml": gov_old,
                    "external/financial_team/law/금융투자업규정/금융투자업규정 본문.xml": other,
                    "internal/risk_team/내부통제기준_20250101.docx": rule[1][0]}
            inputs.put("BASE.zip", write_zip(base))
            g0 = r6.load(base, contract=gold_c)["query_release_id"]
            for stmt in delivered("MAIN_CHANNEL_SIDDS_R1.txt", "SIDDS", user):
                cur.execute(stmt.replace("g19_7c1f8f4931c8be61b914f5bc", "g19_" + g0[:24]))
            conn.commit()
            assert channel(db, gold_names, "main")["query_id"] == g0
            gold_before = snapshot(cur, gold_names)
            checks["gold_before"] = {k: v["rows"] for k, v in gold_before.items()}

            # 2. 시험 복사본 (구조만)
            copy_sql = delivered("CREATE_TEST_COPY_SIDDS_R1.txt", "SIDDS", user)
            for stmt in copy_sql:
                cur.execute(stmt)
            for key in KEYS:                                  # 적재기와 같은 구조 검사
                test_c.preflight(db, key)
            assert not any(v["rows"] for v in snapshot(cur, test_names).values())
            checks["test_copy_created_empty_and_passes_loader_preflight"] = len(copy_sql)
            owner_check = privilege_check(db, test_names, agent_table=agent_table)
            assert owner_check["ok"], owner_check
            checks["privilege_check_on_copy"] = [r["check"] for r in owner_check["checks"]]

            # 3. 시험 복사본에 기준 세대 + main
            t0 = r6.load(base)["query_release_id"]
            assert t0 == g0                                   # 같은 원문 → 같은 세대 번호 (다른 표)
            for stmt in delivered("MAIN_CHANNEL_SIDDS_R1.txt", "SIDDS", user):
                cur.execute(stmt.replace("IDD_B003_LGL_", "TST_B003_LGL_").replace("g19_7c1f8f4931c8be61b914f5bc", "g19_" + t0[:24]))
            conn.commit()
            serving = "main"
            params = Params(channel=serving, base_zip_name="BASE.zip", today="20260110", agent_table=agent_table, prune_batch=3)
            flow = Flow(store=store, drop=drop, inputs=inputs, db=db, agent_db=db, names=test_names, r6=r6, params=params,
                        log=lambda m: None)
            assert flow.status()["base_zip"]["ok"]

            # 4. 1일
            drop.put(f"external/financial_team/law/{name}/{name} 본문.xml", gov_new)
            drop.put("cut/금융투자업규정 본문.xml", cut)
            drop.put("internal/risk_team/내부통제기준_20260101.docx", rule[2][0])
            d1 = flow.decide("d1")
            by = {e["file"]: e for e in store.get_json("runs/d1/decide.json")["entries"]}
            assert by[f"{name} 본문.xml"]["decision"] == "APPROVED"
            assert by["금융투자업규정 본문.xml"]["decision"] == "HOLD"
            assert by["내부통제기준_20260101.docx"]["decision"] == "APPROVED"
            assert [x for x in by[f"{name} 본문.xml"]["changes"] if x["new"] == "26"]
            checks["d1_summary"] = d1["summary"]
            p1 = flow.publish("d1")
            g1 = p1["query_release_id"]
            assert channel(db, test_names, serving)["query_id"] == t0
            flow.activate("d1")
            assert channel(db, test_names, serving)["query_id"] == g1
            assert generation(db, test_names, g1).vector_post_id
            assert cur.execute(f"SELECT COUNT(*) FROM {agent_table}").fetchone()[0] == 0
            gens = [t0, g1]
            for day, v in ((2, 3), (3, 4)):
                drop.delete("internal/risk_team/" + [p for p in drop.list("internal/") if p.endswith(".docx")][0].split("/")[-1])
                drop.put(f"internal/risk_team/내부통제기준_2026010{day}.docx", rule[v][0])
                flow.decide(f"d{day}")
                flow.publish(f"d{day}")
                out = flow.activate(f"d{day}")
                gens.append(store.get_json(f"runs/d{day}/publish.json")["report"]["query_release_id"])
                checks[f"d{day}_prune"] = out["prune"]
            assert {r["query_id"] for r in releases(db, test_names)} == {gens[1], gens[2], gens[3]}
            assert all(v == 0 for v in OLD.count_rows(cur, test_names, t0).values())
            checks["copy_keeps_three_generations"] = True
            r1, r2, r3 = flow.rollback("rb1"), flow.rollback("rb2"), flow.rollback("rb3")
            assert [r1["method"], r2["method"], r3["method"]] == ["CHANNEL", "CHANNEL", "REBUILD"]
            assert channel(db, test_names, serving)["query_id"] == t0
            checks["copy_rollback_three_steps"] = [r1["method"], r2["method"], r3["method"]]
            checks["r6_calls"] = len(r6.calls)

            # 5. 원래 Gold는 처음과 같다 → 복사본 지우기 → 그래도 같다
            assert snapshot(cur, gold_names) == gold_before
            assert channel(db, gold_names, "main")["query_id"] == g0
            checks["original_gold_unchanged_during_experiment"] = True
            for stmt in delivered("DROP_TEST_COPY_SIDDS_R1.txt", "SIDDS", user):
                cur.execute(stmt)
            left = cur.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME LIKE 'TST\\_B003%' ESCAPE '\\'").fetchone()[0]
            assert left == 0 and snapshot(cur, gold_names) == gold_before
            checks["drop_test_copy_leaves_gold"] = True
            checks["result"] = "PASS"
        finally:
            try:
                conn.close()
            except Exception:
                pass
            c.execute(f"DROP USER {user} CASCADE")
            checks["temporary_user_dropped"] = user
    Path(args.out).write_text(json.dumps(checks, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
