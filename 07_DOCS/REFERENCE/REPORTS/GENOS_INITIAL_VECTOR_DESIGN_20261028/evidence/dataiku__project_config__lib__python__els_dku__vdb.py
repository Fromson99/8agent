# -*- coding: utf-8 -*-
"""벡터 행(els_qa.vdb/1) → 임베딩 → 오라클 벡터 표(짧은 이름 vdb_chunk — 위치는 환경별 매핑). **문서 한 건 = 트랜잭션 하나.**

## 무엇인가

레시피 `compute_ELS_QA_VDB_EMBED` 가 부르는 라이브러리다. 코드서빙이 돌려준 벡터용 청크
(전처리 레시피가 문서마다 한 행으로 남긴 것)를 LLM Mesh 로 임베딩해 벡터 표에 쓴다.

    표 준비      없으면 vdb_schema.json 의 DDL 로 만들고, 열 · VECTOR 타입이 정의와 같은지 본다
       ↓
    문서마다
       RDB 와 대조 ── RDB 가 먼저다. 이 문서가 RDB 에서 active 이고, 본문 · 표 청크 수가
                      RDB 문서 행에 적힌 수(TXT_CHNK_CONT · TABLE_CHNK_CONT)와 같아야 쓴다.
                      청크 ID · 내용 해시는 전처리 레시피가 적재 묶음과 이미 맞춰 봤다
       ↓
       임베딩      ── 같은 청크 ID · 내용 해시 · 모델의 벡터가 표에 있으면 그것을 다시 쓰고,
                      나머지만 64개씩 LLM Mesh 에 보낸다
       ↓
       쓰기        ── 이 문서 행을 지우고 다시 넣은 뒤, 같은 상품 · 문서유형의 다른 문서 행을
                      지운다(RDB 는 옛 판을 superseded 로 내리지만 벡터 표에는 남기 때문). COMMIT
       ↓
       다시 읽어 대조 ── 행 수 · 내용 해시 · 모델 · 차원 · 원문 길이

같은 입력을 몇 번 돌려도 결과가 같다 — 문서 단위로 지우고 다시 넣고, 바뀌지 않은 청크는
다시 임베딩하지 않는다(내부망 embed-chunks 플러그인의 smart_sync 와 같은 판단).

## 왜 벡터를 글자로 넣나

SQLExecutor2 에는 바인드 변수가 없어서 벡터도 `TO_VECTOR('[0.1,…]')` 글자로 넣는다. 1024차원
float32 를 글자로 쓰면 한 행이 약 12KB 라 문장 한도(64KB) 안에서 몇 행씩 INSERT ALL 로 묶는다.
리터럴 한 조각은 4000바이트가 한계라 벡터 글자도 TO_CLOB 조각으로 잇는다. 본문이 커서 한 행이
한도를 넘으면 본문 앞 조각만 넣고 나머지는 같은 트랜잭션 안에서 `UPDATE … || TO_CLOB(…)` 로 잇는다.

`dataiku` 패키지는 DSS 안에만 있어서 import 를 함수 안으로 미뤘다.
`tests/test_dataiku_pipeline.py` 가 가짜 실행기 · 가짜 LLM Mesh 로 검증한다.
"""
from __future__ import print_function

import hashlib
import io
import json
import math
import os
import traceback

from els_dku.load import guarded, split_pieces
from els_dku.sql import KST_NOW, MAX_STMT_BYTES, check_datasets, lit, lit_clob, qualified, require_bound

FORMAT = "els_qa.vdb/1"
# Dataiku 데이터셋 이름 — 환경과 무관하게 고정. 실제 표 이름은 데이터셋 설정에 환경마다 들어간다.
DATASET = "ELS_QA_VDB_CHUNK"
# 내부망 AT03_PPL_TEST embed-chunks 플러그인과 같은 모델 · 묶음 크기.
LLM_ID = "openai:genos-embedding:embedding-kure-v1"
BATCH = 64
CHUNK_TYPES = ("text", "table", "spec_card")
# 벡터 행(els_qa.vdb/1 — 전처리 레시피가 만든다)의 키 → 벡터 표 열(vdb_schema.py). 행의 키는 표 열 이름이 바뀌기
# 전 이름 그대로 두고, 표에 닿는 자리(_values · 다시 읽기)에서만 이 대응으로 옮긴다.
ROW_COLUMN = (("chunk_id", "CHNK_ID"), ("document_id", "DOC_ID"), ("product_code", "PRDT_CODE"),
              ("document_type", "DOC_TYPE"), ("chunk_index", "CHNK_SEQ_NO"), ("chunk_type", "CHNK_TYPE"),
              ("section_path", "TTL_PATH_CTNT"), ("section_kind", "SECTION_KIND"), ("page_no", "PAGE_NO"),
              ("text", "EMBD_TXT_CTNT"), ("display_text", "DISPLAY_TXT_CTNT"),
              ("chunk_metadata_json", "CHNK_META_CTNT"), ("chunk_content_hash", "CHNK_CTNT_HASH"))
ROW_KEYS = tuple(k for k, _ in ROW_COLUMN)
# 표에 넣는 열 순서(_values 와 같은 순서). CRTN_DATE_TIME 은 기본값(한국 시간)에 맡긴다.
INSERT_COLUMNS = tuple(c for _, c in ROW_COLUMN) + (
    "EMBD_MDL_NAME", "EMBD_DMSN_CONT", "EMBD_DATE_TIME", "ORIG_CTNT_HASH", "EMBD_BTCH_EXE_ID", "EMBD_VCTR")
# 임베딩 일시(EMBD_DATE_TIME)를 글자로 꺼냈다 다시 넣을 때의 모양. 열이 시간대 없는 한국 시간
# TIMESTAMP(6) 이라 시간대 칸이 없다 — 꺼낸 값을 그대로 TO_TIMESTAMP 로 되돌린다.
TS_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF6'
# 문장 하나에 담는 크기 — 감싸는 PL/SQL · 행 수 확인 몫을 남긴다(load.py 와 같은 값).
ROW_BUDGET = MAX_STMT_BYTES - 1500
# 한 행이 한도를 넘을 때 INSERT 에 싣는 본문 앞 조각과, 뒤에 이어 붙이는 조각의 크기.
FIRST_PIECE_BYTES = 16000
APPEND_PIECE_BYTES = int(ROW_BUDGET * 0.9)
MAX_INSERT_ALL_COLUMNS = 999

# 표 만들기가 막혔을 때 오라클 오류 번호 → 사람이 할 일
HINTS = {
    "ORA-00902": "VECTOR 타입이 없다 — 오라클 23ai 이상이어야 한다. DB 판을 확인할 것",
    "ORA-01031": "표를 만들 권한이 없다 — 이 스키마의 CREATE TABLE 권한을 신청하거나 DBA 가 "
                 "dataiku/ddl/ELS_QA_VDB.sql 로 만들 것",
    "ORA-01950": "테이블스페이스 할당량이 없다 — QUOTA 를 신청할 것",
    "ORA-00942": "표를 지울 권한이 없다 — DBA 가 DROP TABLE 한 뒤 다시 빌드할 것",
}


class VdbError(RuntimeError):
    """벡터 행 · 표 모양 · RDB 대조가 맞지 않는다 — 쓰기 전에 멈춘다."""


# ══ 표 정의 ════════════════════════════════════════════════════
def load_spec():
    """build_project.py 가 02 의 vdb_schema.py 에서 만든 표 정의(생성물)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vdb_schema.json")
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


class VdbTables(object):
    """스키마가 붙은 벡터 표 이름과 정의 — 환경에 묶인 표 정의(build_project.py --env)로 만든다."""

    def __init__(self, spec=None):
        spec = spec or load_spec()
        self.env = require_bound(spec, "벡터 표 정의")
        table = spec["tables"][0]
        self.schema = table["schema"]
        self.table = table["name"]
        self.connection = table["connection"]
        self.name = qualified(self.schema, self.table)
        self.columns = [c for c, _ in table["columns"]]
        self.vector_columns = list(table["vector_columns"])
        self.dim = int(spec["dim"])
        self.ddl = [table["ddl"]] + list(table["indexes"])
        self.comments = list(table.get("comments") or [])


def locate(project_key=None, spec=None):
    """(VdbTables, SQLExecutor2) — 설치한 벡터 표 정의대로. 데이터셋 설정이 다르면 멈춘다."""
    import dataiku

    spec = spec or load_spec()
    t = VdbTables(spec)
    project = dataiku.api_client().get_project(project_key or dataiku.default_project_key())
    check_datasets(project, spec["tables"])
    print("벡터 표 커넥션=%s 표 %s" % (t.connection, t.name))
    return t, dataiku.SQLExecutor2(connection=t.connection)


def mesh_embedder(llm_id=LLM_ID, project_key=None):
    """LLM Mesh 임베딩 → (글자 목록 → 벡터 목록) 함수."""
    import dataiku

    project = dataiku.api_client().get_project(project_key or dataiku.default_project_key())
    llm = project.get_llm(llm_id)

    def embed(texts):
        query = llm.new_embeddings()
        for text in texts:
            query.add_text(text)
        return [list(v) for v in query.execute().get_embeddings()]
    return embed


# ══ 표 준비 ════════════════════════════════════════════════════
def _value(row, column):
    for name, v in row.items():
        if str(name).upper() == column:
            return v
    return None


def _first_line(exc):
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:500]


def _hint(exc):
    text = str(exc)
    for code, hint in HINTS.items():
        if code in text:
            return " — " + hint
    return ""


def _shape(runner, t, owner):
    """[(열, 타입)] — 표에 실제로 있는 모양."""
    return [(str(_value(r, "COLUMN_NAME")).upper(), str(_value(r, "DATA_TYPE")).upper())
            for r in runner.read("SELECT COLUMN_NAME, DATA_TYPE FROM ALL_TAB_COLUMNS WHERE OWNER = %s AND "
                                 "TABLE_NAME = %s ORDER BY COLUMN_ID" % (owner, lit(t.table))) or []]


def _shape_problem(t, got):
    if [c for c, _ in got] != t.columns:
        return "%s 열이 정의와 다르다 — 있음 %s · 정의 %s" % (t.name, [c for c, _ in got], t.columns)
    vectors = [c for c, ty in got if ty == "VECTOR"]
    if vectors != t.vector_columns:
        return "%s 의 VECTOR 열 %s (정의 %s)" % (t.name, vectors, t.vector_columns)
    return ""


def _create(runner, t):
    try:
        runner.write(t.ddl)
    except Exception as exc:                  # noqa: BLE001 — 원문 첫 줄과 할 일을 남긴다
        raise VdbError("벡터 표 %s 를 만들지 못했다: %s%s" % (t.name, _first_line(exc), _hint(exc)))


def ensure_table(runner, t):
    """없으면 만들고, 열 · VECTOR 타입이 정의와 같은지 본다. → 한 일("" · "created" · "recreated").

    ```text
    표가 있나?
     ├─ NO  → 만든다
     └─ YES → 모양이 정의와 같나?
               ├─ YES → 그대로 쓴다
               └─ NO  → 비어 있나?
                         ├─ YES → 지우고 새 정의로 다시 만든다 (옛 정의로 먼저 만들어 둔 준비용 표)
                         └─ NO  → 멈춘다 (데이터가 든 표는 사람이 옮긴다)
    ```
    """
    owner = lit(t.schema) if t.schema else "SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
    rows = runner.read("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = %s AND TABLE_NAME IN (%s)"
                       % (owner, lit(t.table))) or []
    done = ""
    if not rows:
        _create(runner, t)
        done = "created"
    problem = _shape_problem(t, _shape(runner, t, owner))
    if problem and not done:
        count = runner.read("SELECT COUNT(*) AS N FROM %s" % t.name) or []
        n = int(_plain(_value(count[0], "N")) or 0) if count else 0
        if n:
            raise VdbError("%s — 행이 %d개 있어 지우지 않는다. 옮긴 뒤 DROP TABLE 하고 다시 빌드할 것" % (problem, n))
        try:
            runner.write(["DROP TABLE %s PURGE" % t.name])
        except Exception as exc:              # noqa: BLE001
            raise VdbError("%s — 빈 표라 다시 만들려 했지만 지우지 못했다: %s%s" % (
                problem, _first_line(exc), _hint(exc)))
        _create(runner, t)
        done = "recreated"
        problem = _shape_problem(t, _shape(runner, t, owner))
    if problem:
        raise VdbError(problem)
    return done


def apply_comments(runner, t):
    """표 · 열 설명(COMMENT ON)을 건다 — 새로 만든 표도, 이미 있던 표도 매 실행마다. → 못 건 사유("" 면 걸었다).

    실제 표 이름이 30바이트로 줄어 있어 논리명 · 정의를 DB 에 남긴다(정본은 02 의 vdb_schema.py).
    COMMENT 는 덮어쓰기라 몇 번 걸어도 결과가 같다. 임베딩에 필요한 것이 아니므로 못 걸어도 멈추지 않는다.
    """
    if not t.comments:
        return ""
    try:
        runner.write(t.comments)
    except Exception as exc:                  # noqa: BLE001 — 사유를 로그에 남기고 계속
        return "%s: %s" % (t.name, _first_line(exc))
    return ""


# ══ 벡터 행 검사 ══════════════════════════════════════════════
def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_doc(doc):
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise VdbError("벡터 행 형식이 %s 가 아니다" % FORMAT)
    did = doc.get("document_id")
    rows = doc.get("rows")
    if not did or not isinstance(rows, list) or not rows:
        raise VdbError("document_id 나 rows 가 비었다")
    seen = set()
    for i, row in enumerate(rows):
        if set(row) != set(ROW_KEYS):
            raise VdbError("rows[%d] 열 — 빠짐 %s · 남음 %s" % (
                i, sorted(set(ROW_KEYS) - set(row)), sorted(set(row) - set(ROW_KEYS))))
        if row["document_id"] != did or row["product_code"] != doc.get("product_code") \
                or row["document_type"] != doc.get("document_type"):
            raise VdbError("rows[%d] 의 문서 · 상품 · 문서유형이 문서와 다르다" % i)
        if row["chunk_type"] not in CHUNK_TYPES:
            raise VdbError("rows[%d] 청크 종류 %r" % (i, row["chunk_type"]))
        if not row["text"]:
            raise VdbError("rows[%d] 임베딩할 글자가 비었다" % i)
        if row["chunk_id"] in seen:
            raise VdbError("청크 ID 가 겹친다: %s" % row["chunk_id"])
        seen.add(row["chunk_id"])
        if row["chunk_content_hash"] != sha256(row["text"]):
            raise VdbError("rows[%d] 내용 해시가 글자와 다르다" % i)
        if row["page_no"] is not None and (not isinstance(row["page_no"], int) or row["page_no"] <= 0):
            raise VdbError("rows[%d] 쪽 번호 %r — 없으면 null, 있으면 1 이상" % (i, row["page_no"]))


def _plain(value):
    if hasattr(value, "read"):
        value = value.read()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float):
        if value != value:
            return None
        if value == int(value):
            return int(value)
    return value


def read_rdb(runner, rdb, did):
    """문서 행 또는 None — RDB 적재 표에서. 조각은 RDB 에 없고 적재 때 센 수만 문서 행에 있다."""
    docs = runner.read("SELECT DOC_ID, PRDT_CODE, DOC_TYPE, STAS, TXT_CHNK_CONT, TABLE_CHNK_CONT "
                       "FROM %s WHERE DOC_ID = %s ORDER BY DOC_ID" % (rdb.name["document"], lit(did))) or []
    return dict((k.upper(), _plain(v)) for k, v in docs[0].items()) if docs else None


def compare_rdb(doc, rdb_doc):
    """벡터 행 ↔ RDB 문서 행. 어긋난 설명 목록(비면 통과).

    청크 ID · 내용 해시는 전처리 레시피가 같은 응답의 적재 묶음과 맞춰 봤다(`preprocess.vdb_doc`).
    여기서는 그 묶음이 RDB 에 들어간 것과 같은 판인지를 본문 · 표 청크 수로 확인한다.
    """
    did = doc["document_id"]
    if rdb_doc is None:
        return ["RDB 에 문서 %s 가 없다 — 적재(compute_ELS_QA_LOAD)가 먼저다" % did]
    problems = []
    if (rdb_doc.get("PRDT_CODE"), rdb_doc.get("DOC_TYPE")) != (doc["product_code"], doc["document_type"]):
        problems.append("RDB 의 상품 · 문서유형 %s/%s ≠ %s/%s" % (
            rdb_doc.get("PRDT_CODE"), rdb_doc.get("DOC_TYPE"), doc["product_code"], doc["document_type"]))
    for kind, col in (("text", "TXT_CHNK_CONT"), ("table", "TABLE_CHNK_CONT")):
        n = sum(1 for r in doc["rows"] if r["chunk_type"] == kind)
        if n != rdb_doc.get(col):
            problems.append("%s 청크 %d개 — RDB %s 는 %s" % (kind, n, col, rdb_doc.get(col)))
    return problems


# ══ 임베딩 ═════════════════════════════════════════════════════
def read_existing(runner, t, did):
    """{CHNK_ID: {hash, model, embedded_at, run_id, vector}} — 다시 쓸 수 있는 지난 벡터."""
    rows = runner.read(
        "SELECT CHNK_ID, CHNK_CTNT_HASH, EMBD_MDL_NAME, TO_CHAR(EMBD_DATE_TIME, '%s') AS EMBD_DATE_TIME, "
        "EMBD_BTCH_EXE_ID, FROM_VECTOR(EMBD_VCTR RETURNING CLOB) AS EMBD_VCTR FROM %s WHERE DOC_ID = %s"
        % (TS_FORMAT.replace("'", "''"), t.name, lit(did))) or []
    out = {}
    for r in rows:
        r = dict((k.upper(), _plain(v)) for k, v in r.items())
        out[r["CHNK_ID"]] = {"hash": r["CHNK_CTNT_HASH"], "model": r["EMBD_MDL_NAME"],
                             "embedded_at": r["EMBD_DATE_TIME"], "run_id": r["EMBD_BTCH_EXE_ID"],
                             "vector": r["EMBD_VCTR"]}
    return out


def vector_text(vector, dim):
    if len(vector) != dim:
        raise VdbError("임베딩 차원이 %d 이다(기대 %d) — 모델 설정을 확인할 것" % (len(vector), dim))
    values = []
    for v in vector:
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            raise VdbError("임베딩에 NaN · 무한대가 있다")
        values.append("%.8g" % v)
    return "[" + ",".join(values) + "]"


def embed_missing(doc, existing, embedder, model, dim, batch=BATCH):
    """{청크 ID: (벡터 글자, 지난 EMBD_DATE_TIME 또는 None, 지난 EMBD_BTCH_EXE_ID 또는 None)}, 새로 임베딩한 수."""
    out, todo = {}, []
    for row in doc["rows"]:
        old = existing.get(row["chunk_id"])
        if old and old["hash"] == row["chunk_content_hash"] and old["model"] == model and old["vector"]:
            out[row["chunk_id"]] = (old["vector"], old["embedded_at"], old["run_id"])
        else:
            todo.append(row)
    for start in range(0, len(todo), batch):
        part = todo[start:start + batch]
        vectors = embedder([r["text"] for r in part])
        if len(vectors) != len(part):
            raise VdbError("임베딩 %d개를 보냈는데 %d개가 왔다" % (len(part), len(vectors)))
        for row, vector in zip(part, vectors):
            out[row["chunk_id"]] = (vector_text(vector, dim), None, None)
    return out, len(todo)


# ══ 문장 만들기 ════════════════════════════════════════════════
def _size(text):
    return len(text.encode("utf-8"))


def _num(value):
    return "NULL" if value is None else repr(int(value))


def _values(t, row, vector, model, run_id, text=None, display=None):
    """한 행의 값 리터럴(INSERT_COLUMNS 순서). text · display 를 주면 그 글자로 바꿔 넣는다."""
    literal, embedded_at, old_run = vector
    # 다시 쓰는 벡터는 지난 임베딩 일시를, 새 벡터는 지금 한국 시간을 남긴다.
    stamp = ("TO_TIMESTAMP(%s, %s)" % (lit(embedded_at), lit(TS_FORMAT))) if embedded_at else KST_NOW
    return [
        lit(row["chunk_id"]), lit(row["document_id"]), lit(row["product_code"]), lit(row["document_type"]),
        _num(row["chunk_index"]), lit(row["chunk_type"]),
        lit((row["section_path"] or "")[:1024] or None), lit(row["section_kind"]), _num(row["page_no"]),
        lit_clob(row["text"] if text is None else text),
        lit_clob(row["display_text"] if display is None else display),
        lit_clob(row["chunk_metadata_json"]), lit(row["chunk_content_hash"]), lit(model), _num(t.dim),
        stamp, lit(row["chunk_content_hash"]), lit(old_run or run_id),
        "TO_VECTOR(%s, %d, FLOAT32)" % (lit_clob(literal), t.dim),
    ]


def _oversized(t, row, vector, model, run_id):
    """한 행이 한도를 넘는다 — 본문 앞 조각만 넣고, 나머지는 같은 트랜잭션에서 이어 붙인다."""
    texts = split_pieces(row["text"], FIRST_PIECE_BYTES)
    first, rest = texts[0], split_pieces("".join(texts[1:]), APPEND_PIECE_BYTES) if len(texts) > 1 else []
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (t.name, ", ".join(INSERT_COLUMNS), ", ".join(
        _values(t, row, vector, model, run_id, text=first, display="")))
    if _size(sql) > ROW_BUDGET:
        raise VdbError("청크 %s 는 본문을 줄여도 한 문장에 안 들어간다(메타가 크다)" % row["chunk_id"])
    out = [guarded(sql, 1, "벡터 %s" % row["chunk_id"])]
    where = "WHERE CHNK_ID = %s" % lit(row["chunk_id"])
    for piece in rest:
        out.append(guarded("UPDATE %s SET EMBD_TXT_CTNT = EMBD_TXT_CTNT || %s %s" % (t.name, lit_clob(piece), where),
                           1, "벡터 %s EMBD_TXT_CTNT" % row["chunk_id"]))
    for i, piece in enumerate(split_pieces(row["display_text"] or "", APPEND_PIECE_BYTES)):
        head = "DISPLAY_TXT_CTNT || " if i else ""
        out.append(guarded("UPDATE %s SET DISPLAY_TXT_CTNT = %s%s %s" % (t.name, head, lit_clob(piece), where),
                           1, "벡터 %s DISPLAY_TXT_CTNT" % row["chunk_id"]))
    return out


def insert_rows(t, rows, vectors, model, run_id):
    head = "INTO %s (%s) VALUES " % (t.name, ", ".join(INSERT_COLUMNS))
    per_stmt = MAX_INSERT_ALL_COLUMNS // len(INSERT_COLUMNS)
    out, batch, used = [], [], 0

    def flush():
        if batch:
            out.append(guarded("INSERT ALL\n%s\nSELECT 1 FROM DUAL" % "\n".join(batch), len(batch), DATASET))
            del batch[:]

    for row in rows:
        fragment = head + "(%s)" % ", ".join(_values(t, row, vectors[row["chunk_id"]], model, run_id))
        n = _size(fragment) + 1
        if n > ROW_BUDGET - 100:
            flush()
            used = 0
            out += _oversized(t, row, vectors[row["chunk_id"]], model, run_id)
            continue
        if batch and (used + n > ROW_BUDGET - 100 or len(batch) >= per_stmt):
            flush()
            used = 0
        batch.append(fragment)
        used += n
    flush()
    return out


def plan_document(t, doc, vectors, model, run_id):
    """문서 한 건을 쓰는 문장(한 트랜잭션): 지우기 → 넣기 → 같은 상품 · 문서유형의 옛 문서 지우기."""
    did = lit(doc["document_id"])
    stmts = [guarded("DELETE FROM %s WHERE DOC_ID = %s" % (t.name, did))]
    stmts += insert_rows(t, doc["rows"], vectors, model, run_id)
    stmts.append(guarded("DELETE FROM %s WHERE PRDT_CODE = %s AND DOC_TYPE = %s AND DOC_ID <> %s" % (
        t.name, lit(doc["product_code"]), lit(doc["document_type"]), did)))
    return stmts


# ══ 다시 읽기 · 대조 ═══════════════════════════════════════════
def verify_document(runner, t, doc, model):
    rows = runner.read("SELECT CHNK_ID, CHNK_CTNT_HASH, EMBD_MDL_NAME, "
                       "VECTOR_DIMENSION_COUNT(EMBD_VCTR) AS DIM, EMBD_TXT_CTNT, DISPLAY_TXT_CTNT FROM %s "
                       "WHERE DOC_ID = %s" % (t.name, lit(doc["document_id"]))) or []
    got = dict((_plain(_value(r, "CHNK_ID")), dict((k.upper(), _plain(v)) for k, v in r.items())) for r in rows)
    problems = []
    want = dict((r["chunk_id"], r) for r in doc["rows"])
    if sorted(got) != sorted(want):
        return ["벡터 행 %d개 (기대 %d개)" % (len(got), len(want))]
    for cid in sorted(want):
        g, w = got[cid], want[cid]
        text = g["EMBD_TXT_CTNT"] or ""
        if g["CHNK_CTNT_HASH"] != w["chunk_content_hash"] or sha256(text) != w["chunk_content_hash"]:
            problems.append("벡터 %s EMBD_TXT_CTNT 다름 (길이 %d, 기대 %d)" % (cid, len(text), len(w["text"])))
        elif (g["DISPLAY_TXT_CTNT"] or None) != (w["display_text"] or None):
            problems.append("벡터 %s DISPLAY_TXT_CTNT 다름" % cid)
        elif g["EMBD_MDL_NAME"] != model or g["DIM"] != t.dim:
            problems.append("벡터 %s 모델 · 차원 %s/%s" % (cid, g["EMBD_MDL_NAME"], g["DIM"]))
        if problems:
            break
    others = runner.read("SELECT COUNT(*) AS N FROM %s WHERE PRDT_CODE = %s AND DOC_TYPE = %s AND DOC_ID <> %s"
                         % (t.name, lit(doc["product_code"]), lit(doc["document_type"]), lit(doc["document_id"])))
    n = _plain(_value(others[0], "N")) if others else 0
    if n:
        problems.append("같은 상품 · 문서유형의 옛 문서 행이 %s개 남았다" % n)
    return problems


# ══ 실행 ═══════════════════════════════════════════════════════
LOG_COLUMNS = ["RUN_AT", "BUNDLE_ID", "DOCUMENT_ID", "ROWS", "EMBEDDED", "REUSED", "REMOVED_OLD",
               "STATEMENTS", "OUTCOME", "DETAIL"]


def _count_others(runner, t, doc):
    rows = runner.read("SELECT COUNT(*) AS N FROM %s WHERE PRDT_CODE = %s AND DOC_TYPE = %s AND DOC_ID <> %s"
                       % (t.name, lit(doc["product_code"]), lit(doc["document_type"]), lit(doc["document_id"])))
    return int(_plain(_value(rows[0], "N")) or 0) if rows else 0


def write_document(runner, t, rdb_runner, rdb, doc, embedder, model, run_id):
    """문서 한 건 → 요약 dict. RDB 가 superseded 면 {"skipped": 사유}. 어긋나면 VdbError."""
    check_doc(doc)
    rdb_doc = read_rdb(rdb_runner, rdb, doc["document_id"])
    if rdb_doc is not None and rdb_doc.get("STAS") == "superseded":
        # 더 새 판이 RDB 에 active 로 있다 — 이 판을 쓰면 새 판의 벡터를 옛 판 정리로 지운다.
        return {"skipped": "RDB 에서 superseded — 더 새 판이 있어 쓰지 않는다"}
    problems = compare_rdb(doc, rdb_doc)
    if rdb_doc is not None and rdb_doc.get("STAS") != "active":
        problems.append("RDB 상태가 %s 다(active 만 쓴다)" % rdb_doc.get("STAS"))
    if problems:
        raise VdbError("; ".join(problems))
    existing = read_existing(runner, t, doc["document_id"])
    vectors, embedded = embed_missing(doc, existing, embedder, model, t.dim)
    removed = _count_others(runner, t, doc)
    stmts = plan_document(t, doc, vectors, model, run_id)
    runner.write(stmts)
    problems = verify_document(runner, t, doc, model)
    if problems:
        raise VdbError("; ".join(problems[:8]))
    return {"rows": len(doc["rows"]), "embedded": embedded, "reused": len(doc["rows"]) - embedded,
            "removed_old": removed, "statements": len(stmts), "bytes_sent": sum(_size(s) for s in stmts)}


def run_embed(runner, t, rdb_runner, rdb, records, embedder, model=LLM_ID, run_at="", run_id=""):
    """ELS_QA_VDB_INPUT 의 행들 → 로그 행들. 한 건이 실패해도 나머지는 계속 쓴다(각자 한 트랜잭션)."""
    def row_of(**kw):
        row = dict.fromkeys(LOG_COLUMNS, "")
        row.update(RUN_AT=run_at, **kw)
        return row

    done = ensure_table(runner, t)
    log = []
    if done == "created":
        log.append(row_of(OUTCOME="INFO", DETAIL="벡터 표 생성: %s" % t.name))
    elif done == "recreated":
        log.append(row_of(OUTCOME="INFO", DETAIL="벡터 표 다시 만듦: %s — 열이 옛 정의라 비어 있는 표를 지우고 새로 만들었다" % t.name))
    problem = apply_comments(runner, t)
    if problem:
        log.append(row_of(OUTCOME="INFO", DETAIL="표 · 열 설명(COMMENT)을 못 걸었다 — 임베딩은 계속한다: %s" % problem))
    for record in records:
        row = row_of(BUNDLE_ID=str(record.get("BUNDLE_ID") or ""), DOCUMENT_ID=str(record.get("DOCUMENT_ID") or ""))
        try:
            doc = json.loads(record["VDB_JSON"])
            row["DOCUMENT_ID"] = doc.get("document_id") or row["DOCUMENT_ID"]
            s = write_document(runner, t, rdb_runner, rdb, doc, embedder, model, run_id or run_at)
            if "skipped" in s:
                row.update(OUTCOME="SKIP", DETAIL=s["skipped"])
            else:
                row.update(ROWS=s["rows"], EMBEDDED=s["embedded"], REUSED=s["reused"],
                           REMOVED_OLD=s["removed_old"], STATEMENTS=s["statements"], OUTCOME="PASS",
                           DETAIL="%d문장 %d바이트" % (s["statements"], s["bytes_sent"]))
        except Exception as exc:              # noqa: BLE001 — 한 건 실패를 로그에 남기고 다음으로
            row.update(OUTCOME="FAIL", DETAIL=_first_line(exc))
            traceback.print_exc()
        print("%-5s %s %s" % (row["OUTCOME"], row["BUNDLE_ID"], row["DETAIL"]))
        log.append(row)
    if not records:
        log.append(row_of(OUTCOME="INFO", DETAIL="ELS_QA_VDB_INPUT 가 비었다 — 쓸 문서 없음"))
    return log


# ══ RDB 와의 정합성 보정 ═══════════════════════════════════════
def reconcile(runner, t, rdb_runner, rdb, max_ratio=0.5, run_at=""):
    """RDB 에서 active 가 아닌 문서의 벡터를 지운다 → 로그 행들. active 문서의 벡터는 건드리지 않는다.

    문서가 내려가거나(superseded) 교체됐는데 벡터가 남는 경우를 정리한다. 두 판이 겹쳐 처리되면 서로의
    미커밋 쓰기를 못 보고 옛 판의 벡터가 남을 수 있고(제약이 못 막는다), 검색은 상품코드로만 거르므로
    그 청크가 근거로 올라올 수 있다. 반대로 active 인데 벡터가 없는 문서는 여기서 만들지 않는다 —
    다음 전처리가 `known_documents` 로 알아보고(벡터가 없으면 건너뛰지 않는다) 다시 보낸다. 로그로만 알린다.

    **지우는 순서가 곧 안전장치다.** 같은 시각에 다른 실행이 새 문서를 쓰는 중일 수 있어서 ①벡터 표의
    문서 목록을 먼저 읽고 ②그 뒤에 RDB 의 active 목록을 읽는다. 새 문서의 벡터는 RDB 에 active 로
    커밋된 뒤에야 들어가므로, ①에 보인 문서는 ②에서도 active 로 보인다(거꾸로 읽으면 방금 만든 벡터를
    고아로 오해한다). 지우기 직전에 그 문서의 RDB 상태를 한 번 더 읽는다. 아래는 아무것도 지우지 않는다.

      · RDB 에 active 문서가 하나도 없는데 벡터가 있다(RDB 를 잘못 읽은 것일 수 있다)
      · 지울 문서가 벡터 표 문서의 `max_ratio` 를 넘는다(한꺼번에 사라지면 조회가 의심스럽다)
    """
    def row_of(outcome, detail, **kw):
        row = dict.fromkeys(LOG_COLUMNS, "")
        row.update(RUN_AT=run_at, OUTCOME=outcome, DETAIL=detail, **kw)
        return row

    if max_ratio <= 0:
        return [row_of("INFO", "정합성 보정이 꺼져 있다(ELS_PRUNE_MAX_RATIO=0)")]
    try:
        have = sorted(set(str(_value(r, "DOC_ID")) for r in runner.read("SELECT DISTINCT DOC_ID FROM %s" % t.name) or []))
        active = set(str(_value(r, "DOC_ID")) for r in rdb_runner.read(
            "SELECT DOC_ID FROM %s WHERE STAS = 'active'" % rdb.name["document"]) or [])
    except Exception as exc:                  # noqa: BLE001 — 못 읽으면 지우지 않는다
        return [row_of("WARN", "정합성 보정을 건너뛴다 — 목록을 못 읽었다: %s" % _first_line(exc))]
    out = []
    missing = sorted(active - set(have))
    if missing:
        out.append(row_of("INFO", "벡터가 없는 active 문서 %d건 — 다음 전처리가 다시 보낸다: %s"
                          % (len(missing), ", ".join(missing[:5]))))
    orphans = [d for d in have if d not in active]
    if not orphans:
        return out
    if not active:
        return out + [row_of("INFO", "RDB 에 active 문서가 없는데 벡터 문서가 %d건 있어 지우지 않는다 — RDB 를 확인할 것"
                             % len(have))]
    if float(len(orphans)) / len(have) > max_ratio:
        return out + [row_of("INFO", "벡터 문서 %d건 중 %d건이 active 가 아니라 중단한다(상한 %d%%) — 맞으면 "
                             "벡터 표와 RDB 를 확인하고, 맞으면 ELS_PRUNE_MAX_RATIO 를 올릴 것" % (len(have), len(orphans),
                                                                                    int(max_ratio * 100)))]
    for did in orphans:
        row = row_of("REMOVE", "", DOCUMENT_ID=did)
        try:
            now = read_rdb(rdb_runner, rdb, did)
            if now is not None and now.get("STAS") == "active":
                continue                      # 그 사이 active 가 됐다 — 새로 쓰는 중이다
            runner.write([guarded("DELETE FROM %s WHERE DOC_ID = %s" % (t.name, lit(did)))])
            left = runner.read("SELECT COUNT(*) AS N FROM %s WHERE DOC_ID = %s" % (t.name, lit(did)))
            if left and int(_plain(_value(left[0], "N")) or 0):
                raise VdbError("벡터 행이 지워지지 않았다")
            row["DETAIL"] = "RDB 에서 active 가 아닌 문서(%s)의 벡터를 지웠다" % (
                "문서 없음" if now is None else now.get("STAS"))
        except Exception as exc:              # noqa: BLE001 — 한 건 실패를 로그에 남기고 다음으로
            row.update(OUTCOME="FAIL", DETAIL=_first_line(exc))
            traceback.print_exc()
        print("%-6s %s %s" % (row["OUTCOME"], did, row["DETAIL"]))
        out.append(row)
    return out
