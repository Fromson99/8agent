# Dataiku Python 레시피 · Gold 판본 보완(R7f) 뒤 통계 갱신 R1 (플로우용, 2026-11-10)
# 기존 플로우: gold_selection_input → [GOLD_SELECTION_FIX_R7] → gold_selection_noop
# 이 레시피:   gold_selection_noop → [GOLD_STATS_R1] → gold_stats_noop   (입력·출력 폴더는 순서 연결용, 읽기·쓰기 0)
# 하는 일: R7f가 번호 컬럼을 바꾼 검색 행·벡터 행 표의 옵티마이저 통계를 다시 모은다(DBMS_STATS.GATHER_TABLE_STATS).
#   표 데이터는 바꾸지 않는다. 새 통계는 바로 적용되도록 no_invalidate=>FALSE(이미 만들어진 실행 계획을 다시 세우게 함).
# 실행 모드는 프로젝트 변수 GOLD_STATS_MODE: APPLY(기본, 확인 후 통계 갱신) / CHECK(지금 통계만 보여 줌)
# 연결·계정·owner는 R7f와 같은 프로젝트 변수 GOLD_FIX_ORACLE_CONNECTION / GOLD_FIX_EXPECTED_DB_USER / GOLD_FIX_GOLD_OWNER 를 쓴다.
SETTINGS = {
    'MODE': 'APPLY',
    'ORACLE_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'GOLD_OWNER': 'SIDDG',
    'TABLE_PREFIX': 'IDD_B003_LGL_',
    'TABLES': ['SRCH_ROW', 'VCTR_ITEM'],   # R7f가 UPDATE한 큰 표(SRCH_ROW 60,971,724행 · VCTR_ITEM 140,182행)
    'DEGREE': 4,                           # 병렬도. DBA가 정한 값이 있으면 프로젝트 변수 GOLD_STATS_DEGREE
}

import json
import re
import time
import dataiku

try:
    _VARS = dataiku.get_custom_variables()
except Exception:
    _VARS = {}
for _k in ('ORACLE_CONNECTION', 'EXPECTED_DB_USER', 'GOLD_OWNER'):
    _v = _VARS.get('GOLD_FIX_'+_k)
    if isinstance(_v, str) and _v.strip(): SETTINGS[_k] = _v.strip()
if isinstance(_VARS.get('GOLD_STATS_MODE'), str) and _VARS['GOLD_STATS_MODE'].strip():
    SETTINGS['MODE'] = _VARS['GOLD_STATS_MODE'].strip().upper()
if str(_VARS.get('GOLD_STATS_DEGREE', '')).strip():
    SETTINGS['DEGREE'] = int(str(_VARS['GOLD_STATS_DEGREE']).strip())

SEL_V2 = 'filename-search-selection-v2'
VERSION = 'gold-stats-flow-20261110-r1'


class Stop(RuntimeError):
    pass


def log(phase, **fields):
    print(json.dumps(dict(phase=phase, at=time.strftime('%H:%M:%S'), **fields), ensure_ascii=False, default=str), flush=True)


class DB:
    """R7f와 같은 방식: 읽기는 query_to_df, 쓰기는 pre_queries의 PL/SQL 블록."""
    def __init__(self, connection):
        self.ex = dataiku.SQLExecutor2(connection=connection)

    def query(self, sql):
        frame = self.ex.query_to_df(sql, infer_from_schema=True, parse_dates=False)
        frame = frame.astype(object).where(frame.notna(), None)
        return [{str(k).upper(): (v.item() if hasattr(v, 'item') else v) for k, v in r.items()}
                for r in frame.to_dict(orient='records')]

    def block(self, sql):
        frame = self.ex.query_to_df('SELECT 1 AS OK FROM DUAL', pre_queries=[sql], post_queries=['COMMIT'])
        if len(frame) != 1 or int(frame.iloc[0]['OK']) != 1: raise Stop('WRITE_RESPONSE_UNCONFIRMED')


def lit(text):
    return "'"+text.replace("'", "''")+"'"


def stats(db, owner, tables):
    names = ','.join(lit(t) for t in tables)
    rows = db.query('SELECT TABLE_NAME, NUM_ROWS, BLOCKS, STALE_STATS, STATTYPE_LOCKED, '
                    "TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED "
                    'FROM ALL_TAB_STATISTICS WHERE OWNER='+lit(owner)+' AND TABLE_NAME IN ('+names+') '
                    'AND PARTITION_NAME IS NULL ORDER BY TABLE_NAME')
    idx = db.query('SELECT TABLE_NAME, INDEX_NAME, NUM_ROWS, LEAF_BLOCKS, DISTINCT_KEYS, '
                   "TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED "
                   'FROM ALL_IND_STATISTICS WHERE TABLE_OWNER='+lit(owner)+' AND TABLE_NAME IN ('+names+') '
                   'AND PARTITION_NAME IS NULL ORDER BY TABLE_NAME, INDEX_NAME')
    return rows, idx


def main():
    s = SETTINGS
    if s['MODE'] not in ('CHECK', 'APPLY'): raise Stop('MODE_MUST_BE_CHECK_OR_APPLY')
    for name in ('GOLD_OWNER', 'EXPECTED_DB_USER'):
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', s[name]): raise Stop('INVALID:'+name)
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,20}', s['TABLE_PREFIX']): raise Stop('INVALID:TABLE_PREFIX')
    if type(s['DEGREE']) is not int or not 1 <= s['DEGREE'] <= 32: raise Stop('INVALID:DEGREE')
    owner = s['GOLD_OWNER']
    tables = [s['TABLE_PREFIX']+t for t in s['TABLES']]
    for t in tables:
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', t): raise Stop('INVALID:TABLE')
    db = DB(s['ORACLE_CONNECTION'])
    log('START', version=VERSION, mode=s['MODE'], connection=s['ORACLE_CONNECTION'], owner=owner, tables=tables, degree=s['DEGREE'])

    # 1) 접속 계정 확인
    user = db.query('SELECT USER AS U FROM DUAL')[0]['U']
    if user != s['EXPECTED_DB_USER']: raise Stop('UNEXPECTED_DB_USER:'+str(user))

    # 2) R7f가 끝났는지 확인(채널이 v2 판본 선택 게시본을 가리켜야 한다). 진행 중에 통계를 모으면 다시 낡는다.
    head = db.query('SELECT c.CHAN_NO, '
                    "JSON_VALUE(p.RFRN_POST_IFMN_CTNT,'$.search_selection.schema_version') AS SEL_VER "
                    'FROM '+owner+'.'+s['TABLE_PREFIX']+'SRCH_CHNL c JOIN '+owner+'.'+s['TABLE_PREFIX']+'SRCH_POST p '
                    'ON p.RFRN_POST_HASH_VALU=c.RFRN_POST_HASH_VALU')
    log('CHANNEL', rows=head)
    if len(head) != 1 or head[0]['SEL_VER'] != SEL_V2:
        raise Stop('R7F_NOT_FINISHED: 채널이 판본 선택 v2 게시본을 가리키지 않습니다. GOLD_SELECTION_FIX_R7 을 먼저 끝내세요.')

    # 3) 지금 통계
    before, before_idx = stats(db, owner, tables)
    log('STATS_BEFORE', tables=before, indexes=before_idx)
    if len(before) != len(tables): raise Stop('TABLE_NOT_VISIBLE: '+str([r['TABLE_NAME'] for r in before]))
    locked = [r['TABLE_NAME'] for r in before if r['STATTYPE_LOCKED']]
    if locked: raise Stop('STATS_LOCKED: '+str(locked)+' — DBA가 잠근 통계입니다. DBA에 문의하세요.')

    # 4) 권한: Gold owner 본인이거나 ANALYZE ANY 가 있어야 다른 owner 표의 통계를 모을 수 있다
    privs = {r['PRIVILEGE'] for r in db.query('SELECT PRIVILEGE FROM SESSION_PRIVS')}
    allowed = user == owner or 'ANALYZE ANY' in privs
    statements = ["BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname=>"+lit(owner)+", tabname=>"+lit(t)+
                  ", cascade=>TRUE, degree=>"+str(s['DEGREE'])+", no_invalidate=>FALSE); END;" for t in tables]
    if not allowed:
        log('PRIVILEGE_REQUIRED', user=user, need='ANALYZE ANY (또는 DBA가 아래 문장을 직접 실행)', dba_statements=statements)
        raise Stop('PRIVILEGE_REQUIRED: '+user+' 계정에 ANALYZE ANY 가 없습니다. 로그의 dba_statements 를 DBA에 요청하세요.')
    if s['MODE'] == 'CHECK':
        log('CHECK_DONE', would_run=statements); return

    # 5) 통계 갱신(표마다 한 번, 큰 표는 수십 분 걸릴 수 있다)
    for t, sql in zip(tables, statements):
        t0 = time.time()
        log('GATHER_START', table=t)
        db.block(sql)
        log('GATHER_DONE', table=t, seconds=round(time.time()-t0, 1))

    # 6) 확인: 마지막 분석 시각이 이번 실행 뒤로 바뀌었는지
    after, after_idx = stats(db, owner, tables)
    log('STATS_AFTER', tables=after, indexes=after_idx)
    old = {r['TABLE_NAME']: r['LAST_ANALYZED'] for r in before}
    unchanged = [r['TABLE_NAME'] for r in after if r['LAST_ANALYZED'] is None or r['LAST_ANALYZED'] == old.get(r['TABLE_NAME'])]
    if unchanged: raise Stop('STATS_NOT_UPDATED: '+str(unchanged))
    log('APPLIED', tables=[{k: r[k] for k in ('TABLE_NAME', 'NUM_ROWS', 'LAST_ANALYZED', 'STALE_STATS')} for r in after])


main()
