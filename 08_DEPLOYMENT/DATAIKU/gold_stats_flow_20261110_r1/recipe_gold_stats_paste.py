# GOLD 통계 갱신 (R7f 뒤에 1번 실행). 데이터는 바꾸지 않는다.
import dataiku

CONNECTION = 'AIDP'
SQLS = [
    "BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname=>'SIDDG', tabname=>'IDD_B003_LGL_SRCH_ROW', cascade=>TRUE, degree=>4, no_invalidate=>FALSE); END;",
    "BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname=>'SIDDG', tabname=>'IDD_B003_LGL_VCTR_ITEM', cascade=>TRUE, degree=>4, no_invalidate=>FALSE); END;",
]
CHECK = """SELECT TABLE_NAME, NUM_ROWS, TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED
FROM ALL_TAB_STATISTICS WHERE OWNER='SIDDG'
AND TABLE_NAME IN ('IDD_B003_LGL_SRCH_ROW','IDD_B003_LGL_VCTR_ITEM') AND PARTITION_NAME IS NULL"""
DONE = """SELECT JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL_VER
FROM SIDDG.IDD_B003_LGL_SRCH_CHNL c JOIN SIDDG.IDD_B003_LGL_SRCH_POST p ON p.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU"""

ex = dataiku.SQLExecutor2(connection=CONNECTION)
sel = ex.query_to_df(DONE)
print('R7f 상태:', sel.to_dict('records'), flush=True)
if len(sel) != 1 or sel.iloc[0, 0] != 'filename-search-selection-v2':
    raise RuntimeError('R7f가 아직 안 끝났습니다. GOLD_SELECTION_FIX_R7 먼저 끝내세요.')
print('갱신 전:', ex.query_to_df(CHECK).to_dict('records'), flush=True)
for sql in SQLS:
    print('실행:', sql, flush=True)
    ex.query_to_df('SELECT 1 AS OK FROM DUAL', pre_queries=[sql], post_queries=['COMMIT'])
    print('끝', flush=True)
print('갱신 후:', ex.query_to_df(CHECK).to_dict('records'), flush=True)
