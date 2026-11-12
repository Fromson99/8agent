"""Gold(개발계 SIDDS·운영 SIDDG, 같은 IDD_B003 표) 세대 읽기 · 활성화 · 옛 세대 정리 · Agent 결과 정리.

새 표 없이 기존 13표만 쓴다. 세대 하나 = 검색 게시(query release) 하나:
  SRCH_CHNL(채널) → SRCH_POST(검색 게시 JSON: status·source_release_id·dataset_version)
  → SRC_POST(원문 게시) → DOC_VER/DOC_UNIT/DOC_BLK(데이터셋 판본별 문서·구조·본문)
  SRCH_ROW(검색 행, 검색 게시별) · VCTR_HEAD(검색 게시 → 벡터 게시) · VCTR_POST/VCTR_ITEM(벡터 게시별)

표·컬럼 이름은 수신 파이프라인 적재기와 같은 대상 정의(prod_config.target, GOLD)를 쓴다 — 개발계 SIDDS·운영 SIDDG의
IDD_B003_LGL_* (소유자는 프로젝트 변수 LGL_GOLD_OWNER). 이름이 어긋날 수 없다.

DB는 두 함수만 쓴다: query(sql) → [{대문자 컬럼: 값}], write(plsql 블록) → 한 트랜잭션 COMMIT.
SQL 안의 값은 해시·ID·채널명뿐이라 영숫자 검사 뒤 문자열 리터럴로 넣는다 (원문 텍스트 0).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_SAFE = re.compile(r"^[A-Za-z0-9_:.\-]{1,200}$")
_TABLE_KEYS = ("DOC_VER", "DOC_UNIT", "DOC_BLK", "SRC_POST", "SRCH_POST", "SRCH_ROW", "SRCH_CHNL",
               "VCTR_POST", "VCTR_ITEM", "VCTR_HEAD")


class ReleaseError(RuntimeError):
    pass


def lit(value) -> str:
    text = str(value)
    if not _SAFE.match(text):
        raise ReleaseError(f"SQL 값 형식 거절: {text[:40]!r}")
    return "'" + text + "'"


def _text(value) -> str:
    if value is None:
        return ""
    return value.read() if hasattr(value, "read") else str(value)


class Names:
    """prod_config.target(...) 결과 → 표·컬럼 물리명."""

    def __init__(self, target: dict):
        self.tables = target["tables"]
        missing = [k for k in _TABLE_KEYS if k not in self.tables]
        if missing:
            raise ReleaseError(f"대상 정의에 표 없음: {missing}")

    def t(self, key: str) -> str:
        table = self.tables[key]
        return f"{table['owner']}.{table['name']}"

    def c(self, key: str, logical: str) -> str:
        return self.tables[key]["columns"][logical]["name"]


@dataclass
class Generation:
    query_id: str
    source_release_id: str
    dataset_version: str
    vector_post_id: str
    documents: list[str]

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# ------------------------------------------------------------------ 읽기

def channel(db, n: Names, name: str) -> dict:
    rows = db.query(f"SELECT {n.c('SRCH_CHNL','RFRN_POST_HASH_VALU')} AS POST, {n.c('SRCH_CHNL','CHAN_NO')} AS NO "
                    f"FROM {n.t('SRCH_CHNL')} WHERE {n.c('SRCH_CHNL','RFRN_CHNL_NAME')}={lit(name)}")
    if len(rows) != 1:
        raise ReleaseError(f"채널 {name} 행이 {len(rows)}개")
    return {"name": name, "query_id": rows[0]["POST"], "chan_no": int(rows[0]["NO"])}


def generation(db, n: Names, query_id: str) -> Generation:
    rows = db.query(f"SELECT {n.c('SRCH_POST','RFRN_POST_IFMN_CTNT')} AS BODY FROM {n.t('SRCH_POST')} "
                    f"WHERE {n.c('SRCH_POST','RFRN_POST_HASH_VALU')}={lit(query_id)}")
    if len(rows) != 1:
        raise ReleaseError(f"검색 게시 {query_id[:16]} 행이 {len(rows)}개")
    info = json.loads(_text(rows[0]["BODY"]))
    if info.get("status") != "COMPLETE":
        raise ReleaseError(f"검색 게시 {query_id[:16]} 상태 {info.get('status')}")
    heads = db.query(f"SELECT {n.c('VCTR_HEAD','VCTR_POST_ID')} AS VP FROM {n.t('VCTR_HEAD')} "
                     f"WHERE {n.c('VCTR_HEAD','RFRN_POST_HASH_VALU')}={lit(query_id)}")
    documents = sorted(((info.get("source_manifest") or {}).get("scope") or {}).get("document_version_ids") or [])
    return Generation(query_id, info.get("source_release_id", ""), info.get("dataset_version", ""),
                      heads[0]["VP"] if len(heads) == 1 else "", documents)


def documents(db, n: Names, dataset_version: str) -> list[dict]:
    rows = db.query(f"SELECT {n.c('DOC_VER','DOC_ID')} AS ID, {n.c('DOC_VER','DOC_NAME')} AS NAME, "
                    f"{n.c('DOC_VER','DOC_HASH_VALU')} AS SHA FROM {n.t('DOC_VER')} "
                    f"WHERE {n.c('DOC_VER','MNFST_HASH_VALU')}={lit(dataset_version)} ORDER BY 1")
    return [{"doc_id": r["ID"], "name": _text(r["NAME"]), "sha256": r["SHA"] or ""} for r in rows]


def structure(db, n: Names, dataset_version: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    """Gold 문서 한 개 → 구조화 result.json과 같은 nodes·blocks."""
    units = db.query(f"SELECT {n.c('DOC_UNIT','STRC_UNIT_ADDN_IFMN_CTNT')} AS J FROM {n.t('DOC_UNIT')} "
                     f"WHERE {n.c('DOC_UNIT','MNFST_HASH_VALU')}={lit(dataset_version)} "
                     f"AND {n.c('DOC_UNIT','DOC_ID')}={lit(doc_id)}")
    blocks = db.query(f"SELECT {n.c('DOC_BLK','BODY_SLC_ID')} AS ID, {n.c('DOC_BLK','STRC_UNIT_ID')} AS U, "
                      f"{n.c('DOC_BLK','BODY_CTNT')} AS T, {n.c('DOC_BLK','BODY_SLC_ADDN_IFMN_CTNT')} AS J "
                      f"FROM {n.t('DOC_BLK')} WHERE {n.c('DOC_BLK','MNFST_HASH_VALU')}={lit(dataset_version)} "
                      f"AND {n.c('DOC_BLK','DOC_ID')}={lit(doc_id)}")
    nodes = [json.loads(_text(r["J"])) for r in units]
    out = []
    for r in blocks:
        meta = json.loads(_text(r["J"])) if r["J"] else {}
        out.append({**meta, "idx": int(r["ID"]), "text": _text(r["T"]),
                    "node": int(r["U"]) if r["U"] not in (None, "") else meta.get("node"),
                    "kind": meta.get("kind", "text")})
    return nodes, sorted(out, key=lambda b: b["idx"])


# ------------------------------------------------------------------ 활성화

def activate_sql(n: Names, *, channel_name: str, old_query: str, chan_no: int, new_query: str,
                 vector_post_id: str) -> str:
    """새 세대로 전환: 검색 게시 COMPLETE·벡터 게시 존재 확인 → VCTR_HEAD(없으면 추가, 있으면 같아야 함)
    → 채널 CAS. 하나라도 어긋나면 블록 전체가 실패해 아무것도 바뀌지 않는다."""
    if type(chan_no) is not int:
        raise ReleaseError("채널 변경번호는 정수")
    post, info = n.c('SRCH_POST', 'RFRN_POST_HASH_VALU'), n.c('SRCH_POST', 'RFRN_POST_IFMN_CTNT')
    vh_q, vh_v, vh_n = (n.c('VCTR_HEAD', 'RFRN_POST_HASH_VALU'), n.c('VCTR_HEAD', 'VCTR_POST_ID'),
                        n.c('VCTR_HEAD', 'CHAN_NO'))
    ch_name, ch_post, ch_no = (n.c('SRCH_CHNL', 'RFRN_CHNL_NAME'), n.c('SRCH_CHNL', 'RFRN_POST_HASH_VALU'),
                               n.c('SRCH_CHNL', 'CHAN_NO'))
    vp = n.c('VCTR_POST', 'VCTR_POST_ID')
    return f"""DECLARE
  n NUMBER;
  existing VARCHAR2(200);
BEGIN
  SELECT COUNT(*) INTO n FROM {n.t('SRCH_POST')} WHERE {post}={lit(new_query)}
    AND JSON_VALUE({info}, '$.status' RETURNING VARCHAR2(40))='COMPLETE';
  IF n <> 1 THEN RAISE_APPLICATION_ERROR(-20911, 'INCREMENT_NEW_RELEASE_NOT_COMPLETE'); END IF;
  SELECT COUNT(*) INTO n FROM {n.t('VCTR_POST')} WHERE {vp}={lit(vector_post_id)};
  IF n <> 1 THEN RAISE_APPLICATION_ERROR(-20912, 'INCREMENT_VECTOR_POST_MISSING'); END IF;
  SELECT COUNT(*), MAX({vh_v}) INTO n, existing FROM {n.t('VCTR_HEAD')} WHERE {vh_q}={lit(new_query)};
  IF n = 0 THEN
    INSERT INTO {n.t('VCTR_HEAD')} ({vh_q}, {vh_v}, {vh_n}) VALUES ({lit(new_query)}, {lit(vector_post_id)}, 1);
  ELSIF existing <> {lit(vector_post_id)} THEN
    RAISE_APPLICATION_ERROR(-20913, 'INCREMENT_VECTOR_HEAD_OTHER_POST');
  END IF;
  UPDATE {n.t('SRCH_CHNL')} SET {ch_post}={lit(new_query)}, {ch_no}={ch_no}+1
    WHERE {ch_name}={lit(channel_name)} AND {ch_post}={lit(old_query)} AND {ch_no}={chan_no};
  IF SQL%ROWCOUNT <> 1 THEN RAISE_APPLICATION_ERROR(-20914, 'INCREMENT_CHANNEL_CAS'); END IF;
END;"""


def switch(db, n: Names, *, channel_name: str, expected_query: str, new_query: str, vector_post_id: str) -> dict:
    before = channel(db, n, channel_name)
    if before["query_id"] != expected_query:
        raise ReleaseError(f"채널 {channel_name}이 예상과 다른 세대를 가리킴 ({before['query_id'][:16]})")
    db.write(activate_sql(n, channel_name=channel_name, old_query=expected_query, chan_no=before["chan_no"],
                          new_query=new_query, vector_post_id=vector_post_id))
    after = channel(db, n, channel_name)
    if after["query_id"] != new_query or after["chan_no"] != before["chan_no"] + 1:
        raise ReleaseError("채널 전환 재확인 실패")
    head = generation(db, n, new_query)
    if head.vector_post_id != vector_post_id:
        raise ReleaseError("벡터 게시 행 재확인 실패")
    return {"before": before, "after": after}


# ------------------------------------------------------------------ 옛 세대 정리

def releases(db, n: Names) -> list[dict]:
    """DB에 있는 모든 검색 게시와 그 원문·데이터셋·벡터 게시, 그것을 가리키는 채널."""
    out = []
    for r in db.query(f"SELECT {n.c('SRCH_POST','RFRN_POST_HASH_VALU')} AS Q, "
                      f"JSON_VALUE({n.c('SRCH_POST','RFRN_POST_IFMN_CTNT')}, '$.source_release_id' RETURNING VARCHAR2(100)) AS S, "
                      f"JSON_VALUE({n.c('SRCH_POST','RFRN_POST_IFMN_CTNT')}, '$.dataset_version' RETURNING VARCHAR2(100)) AS D "
                      f"FROM {n.t('SRCH_POST')}"):
        out.append({"query_id": r["Q"], "source_release_id": r["S"] or "", "dataset_version": r["D"] or ""})
    heads = {r["Q"]: r["V"] for r in db.query(
        f"SELECT {n.c('VCTR_HEAD','RFRN_POST_HASH_VALU')} AS Q, {n.c('VCTR_HEAD','VCTR_POST_ID')} AS V "
        f"FROM {n.t('VCTR_HEAD')}")}
    # 03 적재 뒤 전환 전에 멈춘 세대는 VCTR_HEAD가 없다 — 벡터 게시 내용의 manifest.query_id로 찾는다
    for r in db.query(f"SELECT {n.c('VCTR_POST','VCTR_POST_ID')} AS V, "
                      f"JSON_VALUE({n.c('VCTR_POST','VCTR_POST_IFMN_CTNT')}, '$.manifest.query_id' RETURNING VARCHAR2(100)) AS Q "
                      f"FROM {n.t('VCTR_POST')}"):
        if r["Q"] and r["Q"] not in heads:
            heads[r["Q"]] = r["V"]
    chans: dict[str, list[str]] = {}
    for r in db.query(f"SELECT {n.c('SRCH_CHNL','RFRN_CHNL_NAME')} AS C, {n.c('SRCH_CHNL','RFRN_POST_HASH_VALU')} AS Q "
                      f"FROM {n.t('SRCH_CHNL')}"):
        chans.setdefault(r["Q"], []).append(r["C"])
    for r in out:
        r["vector_post_id"] = heads.get(r["query_id"], "")
        r["channels"] = sorted(chans.get(r["query_id"], []))
    return out


def own_channel(query_id: str, prefix: str = "g19_") -> str:
    """R6 적재기가 세대마다 만드는 자기 채널 이름."""
    return prefix + query_id[:24]


def prune_plan(all_releases: list[dict], keep_queries: list[str]) -> dict:
    """keep 밖 세대 중 지울 것과 그 키.
    - 어떤 채널이든 그 세대를 가리키는데 그 채널이 세대 자신의 g19_ 채널이 아니면 지우지 않는다
      (개발계는 서빙 채널이 g19_7c1f… 같은 적재기 채널 이름 그대로다 — 전환 뒤엔 다른 세대를 가리킴).
    - 세대 자신의 g19_ 채널 행은 '이름 + 그 세대를 가리킴' 둘 다 맞을 때만 지운다.
    - 데이터셋·원문 게시·벡터 게시가 남길 세대와 겹치면 그 부분은 남긴다."""
    keep = set(keep_queries)
    protected, remove = [], []
    for r in all_releases:
        if r["query_id"] in keep:
            continue
        foreign = [c for c in r["channels"] if c != own_channel(r["query_id"])]
        (protected if foreign else remove).append(r)
    alive = [r for r in all_releases if r["query_id"] in keep] + protected
    used = {k: {r[k] for r in alive if r[k]} for k in ("source_release_id", "dataset_version", "vector_post_id")}
    plan = []
    for r in sorted(remove, key=lambda x: x["query_id"]):
        plan.append({"query_id": r["query_id"],
                     "own_channel": own_channel(r["query_id"]) if own_channel(r["query_id"]) in r["channels"] else "",
                     "source_release_id": r["source_release_id"] if r["source_release_id"] not in used["source_release_id"] else "",
                     "dataset_version": r["dataset_version"] if r["dataset_version"] not in used["dataset_version"] else "",
                     "vector_post_id": r["vector_post_id"] if r["vector_post_id"] not in used["vector_post_id"] else ""})
        for k in used:                         # 같은 키를 두 번 지우는 계획을 만들지 않는다
            if r[k]:
                used[k].add(r[k])
    return {"keep": sorted(keep), "protected": [r["query_id"] for r in protected], "remove": plan}


def _steps(n: Names, item: dict) -> list[tuple[str, str]]:
    """(표, WHERE 조건) — 서빙이 먼저 못 찾게 채널·게시부터, 큰 행 묶음은 그 뒤에."""
    q = item["query_id"]
    steps = []
    if item["own_channel"]:
        steps.append(("SRCH_CHNL", f"{n.c('SRCH_CHNL','RFRN_CHNL_NAME')}={lit(item['own_channel'])} "
                                   f"AND {n.c('SRCH_CHNL','RFRN_POST_HASH_VALU')}={lit(q)}"))
    steps += [("VCTR_HEAD", f"{n.c('VCTR_HEAD','RFRN_POST_HASH_VALU')}={lit(q)}"),
              ("SRCH_POST", f"{n.c('SRCH_POST','RFRN_POST_HASH_VALU')}={lit(q)}"),
              ("SRCH_ROW", f"{n.c('SRCH_ROW','RFRN_POST_HASH_VALU')}={lit(q)}")]
    if item["vector_post_id"]:
        v = lit(item["vector_post_id"])
        steps += [("VCTR_ITEM", f"{n.c('VCTR_ITEM','VCTR_POST_ID')}={v}"),
                  ("VCTR_POST", f"{n.c('VCTR_POST','VCTR_POST_ID')}={v}")]
    if item["source_release_id"]:
        steps.append(("SRC_POST", f"{n.c('SRC_POST','DOC_POST_HASH_VALU')}={lit(item['source_release_id'])}"))
    if item["dataset_version"]:
        d = lit(item["dataset_version"])
        steps += [(k, f"{n.c(k,'MNFST_HASH_VALU')}={d}") for k in ("DOC_BLK", "DOC_UNIT", "DOC_VER")]
    return [(n.t(k), where) for k, where in steps]


def prune(db, n: Names, plan: dict, *, batch: int = 50000, journal=None, max_batches: int | None = None) -> dict:
    """계획대로 묶음 삭제. 묶음마다 COMMIT, 끊겨도 같은 계획으로 다시 부르면 이어서 지운다
    (이미 지운 키는 0행이라 그냥 넘어간다). journal(event)로 진행을 남긴다."""
    if type(batch) is not int or not 1 <= batch <= 500000:
        raise ReleaseError("삭제 묶음 크기")
    done = {"deleted": {}, "batches": 0, "complete": False}
    for item in plan["remove"]:
        for table, where in _steps(n, item):
            while True:
                rows = db.query(f"SELECT COUNT(*) AS N FROM {table} WHERE {where} AND ROWNUM<=1")
                if int(rows[0]["N"]) == 0:
                    break
                if max_batches is not None and done["batches"] >= max_batches:
                    return done
                db.write(f"BEGIN DELETE FROM {table} WHERE {where} AND ROWNUM<={batch}; END;")
                done["batches"] += 1
                key = f"{table}:{item['query_id'][:16]}"
                done["deleted"][key] = done["deleted"].get(key, 0) + 1
                if journal:
                    journal({"table": table, "query_id": item["query_id"], "batch": done["batches"]})
    done["complete"] = True
    return done


# ------------------------------------------------------------------ Agent 결과 정리

AGENT_TABLE = "SIDDA.LGL_PIPE_RESULT_A"


def agent_cleanup(db, job_id: str, *, table: str = AGENT_TABLE, batch: int = 2000) -> int:
    """Gold 적재 확인 뒤 그 작업의 Agent 결과 조각을 지운다. 지운 묶음 수를 돌려준다."""
    if not re.fullmatch(r"[0-9a-f]{32}", job_id or ""):
        raise ReleaseError("Agent 작업 ID 형식")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*", table):
        raise ReleaseError("Agent 표 이름")
    rounds = 0
    while int(db.query(f"SELECT COUNT(*) AS N FROM {table} WHERE JOB_ID={lit(job_id)} AND ROWNUM<=1")[0]["N"]):
        db.write(f"BEGIN DELETE FROM {table} WHERE JOB_ID={lit(job_id)} AND ROWNUM<={batch}; END;")
        rounds += 1
    return rounds


# ------------------------------------------------------------------ Dataiku 연결

class DataikuSql:
    """dataiku.SQLExecutor2 → query/write. write는 PL/SQL 블록 하나 + COMMIT (R6 적재기와 같은 방식)."""

    def __init__(self, executor):
        self.executor = executor

    def query(self, sql: str) -> list[dict]:
        frame = self.executor.query_to_df(sql)
        frame.columns = [str(c).upper() for c in frame.columns]
        records = frame.to_dict("records")
        return [{k: (None if v != v else v) if isinstance(v, float) else v for k, v in r.items()} for r in records]

    def write(self, block: str) -> None:
        frame = self.executor.query_to_df("SELECT 1 AS OK FROM DUAL", pre_queries=[block], post_queries=["COMMIT"])
        if len(frame) != 1:
            raise ReleaseError("쓰기 응답 확인 실패")


# ------------------------------------------------------------------ 권한 확인 (아무 행도 안 바뀜)

WRITE_TABLES = ("DOC_VER", "DOC_UNIT", "DOC_BLK", "SRC_POST", "SRCH_POST", "SRCH_ROW", "SRCH_CHNL",
                "VCTR_POST", "VCTR_ITEM", "VCTR_HEAD")


def privilege_check(db, n: Names, *, agent_table: str = AGENT_TABLE, agent_db=None) -> dict:
    """증분에 필요한 쓰기 권한을 WHERE 1=0 문장으로 확인한다 — 행은 하나도 바뀌지 않는다.
    필요: 13표 중 세대 표 10개 DELETE(옛 세대 정리), SRCH_CHNL UPDATE·VCTR_HEAD INSERT(전환),
    Agent 결과 표 DELETE(적재 뒤 정리). 실패하면 Oracle 오류 번호(ORA-01031 권한 없음, ORA-00942 표 없음/권한)."""
    checks = [(f"DELETE {k}", n.t(k), f"DELETE FROM {n.t(k)} WHERE 1=0") for k in WRITE_TABLES]
    checks += [("UPDATE SRCH_CHNL", n.t("SRCH_CHNL"),
                f"UPDATE {n.t('SRCH_CHNL')} SET {n.c('SRCH_CHNL','CHAN_NO')}={n.c('SRCH_CHNL','CHAN_NO')} WHERE 1=0"),
               ("INSERT VCTR_HEAD", n.t("VCTR_HEAD"),
                f"INSERT INTO {n.t('VCTR_HEAD')} SELECT * FROM {n.t('VCTR_HEAD')} WHERE 1=0"),
               ("DELETE AGENT", agent_table, f"DELETE FROM {agent_table} WHERE 1=0")]
    out = []
    for label, table, sql in checks:
        try:
            (agent_db or db if label == "DELETE AGENT" else db).write(f"BEGIN {sql}; END;")
            out.append({"check": label, "table": table, "ok": True})
        except Exception as exc:                      # 실행기 예외 문구에서 ORA 번호만 남긴다
            codes = sorted(set(re.findall(r"ORA-\d{5}", str(exc))))
            out.append({"check": label, "table": table, "ok": False, "oracle": codes or [type(exc).__name__]})
    return {"ok": all(r["ok"] for r in out), "checks": out}
