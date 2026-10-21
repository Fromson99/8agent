# Dataiku: Webapps > New webapp > Code webapp > Streamlit
# Paste this entire file into the webapp's Python editor.
# The configured code environment must contain streamlit and pandas.
import logging
import re
import time
import uuid

import dataiku
import streamlit as st

DEFAULT_CONNECTION = "AIDP"
MAX_ROWS = 20
MAX_COLUMNS = 40
TEXT_CHARS = 300

st.set_page_config(page_title="Oracle 조회 테스트", layout="wide")
st.title("Dataiku · Oracle 조회 테스트")
st.caption("연결 확인 → 테이블 목록 → 데이터 미리보기 / 읽기 전용")
logger = logging.getLogger("streamlit_oracle_test")


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    # Identifiers come from Oracle metadata; preserve their exact spelling.
    return '"' + str(value).replace('"', '""') + '"'


def query(label, sql):
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        with st.spinner(label + " 중…"):
            executor = dataiku.SQLExecutor2(connection=connection)
            result = executor.query_to_df(
                sql, infer_from_schema=True, parse_dates=False
            )
    except Exception as exc:
        # Terminal UI boundary: SQLExecutor2 backend exceptions vary by DSS.
        # Preserve the cause in backend logs, never retry or return empty success.
        logger.exception("SQL_FAILED request=%s stage=%s", request_id, label)
        codes = sorted(set(re.findall(r"ORA-\d{5}", str(exc))))
        suffix = " / " + ", ".join(codes) if codes else ""
        st.error(f"{label} 실패 · 확인 번호 {request_id}{suffix}")
        st.info("Webapp의 백엔드 로그에서 확인 번호를 검색하세요. 설정 확인 후 버튼으로 다시 실행할 수 있습니다.")
        st.stop()
    logger.info("SQL_OK request=%s stage=%s rows=%s", request_id, label, len(result))
    st.caption(f"{label}: {len(result)}행 반환 · {time.monotonic() - started:.2f}초")
    return result


connection = st.sidebar.text_input("Dataiku Oracle 연결 이름", DEFAULT_CONNECTION).strip()
schema = st.sidebar.text_input("스키마 — 비우면 현재 스키마", "").strip().upper()
prefix = st.sidebar.text_input("테이블 이름 시작 글자 — 선택", "").strip().upper()
st.sidebar.caption("DB 접속 비밀번호는 Dataiku에 등록된 연결 설정을 사용합니다.")

if not connection:
    st.info("Oracle 연결 이름을 입력하세요.")
    st.stop()
if schema and not re.fullmatch(r"[A-Z][A-Z0-9_$#]{0,127}", schema):
    st.error("스키마는 일반 Oracle 이름으로 입력하세요. 예: AIDP")
    st.stop()
if prefix and not re.fullmatch(r"[A-Z0-9_$#]{1,128}", prefix):
    st.error("테이블 시작 글자는 영문·숫자·밑줄·$·#로 입력하세요.")
    st.stop()

binding = (connection, schema, prefix)
if st.session_state.get("oracle_smoke_binding") != binding:
    st.session_state["oracle_smoke_binding"] = binding
    st.session_state.pop("oracle_smoke_catalog", None)

if st.button("1. Oracle 연결 확인"):
    info = query("연결 확인", """
        SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS DB_USER,
               SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS CURRENT_SCHEMA,
               TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS DB_TIME
        FROM DUAL
    """)
    st.success("Oracle 연결 성공")
    st.dataframe(info, use_container_width=True, hide_index=True)

if st.button("2. 테이블 목록 불러오기"):
    # Clear the old catalogue before the call so a failed refresh cannot reuse it.
    st.session_state.pop("oracle_smoke_catalog", None)
    owner_sql = literal(schema) if schema else "SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
    prefix_sql = ""
    if prefix:
        prefix_sql = f" AND SUBSTR(TABLE_NAME, 1, {len(prefix)}) = {literal(prefix)}"
    tables = query("테이블 목록", f"""
        SELECT OWNER, TABLE_NAME FROM (
            SELECT OWNER, TABLE_NAME FROM ALL_TABLES
            WHERE OWNER = {owner_sql}{prefix_sql}
            ORDER BY TABLE_NAME
        ) WHERE ROWNUM <= 201
    """)
    st.session_state["oracle_smoke_catalog"] = tables

tables = st.session_state.get("oracle_smoke_catalog")
if tables is None:
    st.info("테이블 목록 불러오기를 누르세요.")
    st.stop()
if tables.empty:
    st.info("이 조건에서 표시할 테이블이 없습니다. 스키마·시작 글자·접근 권한을 확인하세요.")
    st.stop()
if len(tables) > 200:
    st.warning("목록은 처음 200개만 표시합니다. 시작 글자로 범위를 줄일 수 있습니다.")

options = list(tables.iloc[:200][["OWNER", "TABLE_NAME"]].itertuples(index=False, name=None))
with st.form("oracle_preview"):
    owner, table = st.selectbox("테이블 선택", options, format_func=lambda item: ".".join(item))
    row_limit = st.number_input("조회 행 수", min_value=1, max_value=MAX_ROWS, value=10, step=1)
    submitted = st.form_submit_button("3. 선택한 테이블 조회", type="primary")

if submitted:
    columns = query("열 정보", f"""
        SELECT COLUMN_NAME, DATA_TYPE FROM (
            SELECT COLUMN_NAME, DATA_TYPE FROM ALL_TAB_COLUMNS
            WHERE OWNER = {literal(owner)} AND TABLE_NAME = {literal(table)}
            ORDER BY COLUMN_ID
        ) WHERE ROWNUM <= {MAX_COLUMNS + 1}
    """)
    if columns.empty:
        st.warning("열 정보를 확보하지 못했습니다. 테이블 목록과 접근 권한을 다시 확인하세요.")
        st.stop()
    if len(columns) > MAX_COLUMNS:
        st.warning(f"앞 {MAX_COLUMNS}개 열만 미리봅니다.")
    expressions, skipped = [], []
    for name, dtype in columns.iloc[:MAX_COLUMNS].itertuples(index=False, name=None):
        col = identifier(name)
        if dtype in {"CLOB", "NCLOB"}:
            expressions.append(f"DBMS_LOB.SUBSTR({col}, {TEXT_CHARS}, 1) AS {col}")
        elif dtype in {"CHAR", "VARCHAR2", "NCHAR", "NVARCHAR2"}:
            expressions.append(f"SUBSTR({col}, 1, {TEXT_CHARS}) AS {col}")
        elif dtype in {"NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE", "DATE"} or dtype.startswith("TIMESTAMP"):
            expressions.append(col)
        else:
            skipped.append(f"{name} ({dtype})")
    if skipped:
        st.caption("이번 미리보기에서 제외한 형식: " + ", ".join(skipped))
    if not expressions:
        st.warning("이 테이블의 앞부분에는 미리보기를 지원하는 열이 없습니다.")
        st.stop()
    sql = (
        f"SELECT {', '.join(expressions)} FROM {identifier(owner)}.{identifier(table)} "
        f"WHERE ROWNUM <= {int(row_limit)}"
    )
    rows = query("데이터 조회", sql)
    st.success(f"{owner}.{table} · {len(rows)}행 조회 완료")
    st.caption(f"순서가 지정되지 않은 일부 행입니다. 문자열·본문은 앞 {TEXT_CHARS}자만 표시합니다.")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    with st.expander("실행한 조회 SQL"):
        st.code(sql, language="sql")
