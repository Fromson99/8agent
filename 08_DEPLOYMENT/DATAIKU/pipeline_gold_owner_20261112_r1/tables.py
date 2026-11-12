"""파이프라인에 필요한 Oracle 표 — 확인 SQL·생성 DDL·시험 복사본 DDL·main 채널 SQL을 만든다.

- 표 정의 원본: 00_SYSTEM/ORACLE/gold_b003_r5.json (운영 Gold 등록과 같음, 13표).
- CREATE 문장은 R7 적재기(gold_io.Contract)가 검사하는 정의를 그 함수로 그대로 만든다 — 만든 표가 적재기 검사를 통과한다.
- Dataiku SQL 노트북 규칙: [번호] 한 개씩 별도 Query, 문장 끝 ; 없음, PL/SQL 없음.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('align_build', ROOT / '09_ARTIFACTS/AUDITS/20261110-dev-gold-align/build.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

AGENT_OWNER = 'SIDDA'
PIPE = ('SIDDA', 'LGL_PIPE_RESULT_A')
PIPE_COLS = [('JOB_ID', 'VARCHAR2(32 BYTE)', True), ('SEQ_NO', 'NUMBER(12,0)', True),
             ('BIND_HASH', 'VARCHAR2(64 BYTE)', True), ('DATA_HASH', 'VARCHAR2(64 BYTE)', True),
             ('BYTE_CNT', 'NUMBER(14,0)', True), ('PART_CNT', 'NUMBER(12,0)', True), ('BODY_B64', 'CLOB', False)]
PIPE_DDL = ("CREATE TABLE SIDDA.LGL_PIPE_RESULT_A (JOB_ID VARCHAR2(32 BYTE) NOT NULL, SEQ_NO NUMBER(12) NOT NULL, "
            "BIND_HASH VARCHAR2(64 BYTE) NOT NULL, DATA_HASH VARCHAR2(64 BYTE) NOT NULL, BYTE_CNT NUMBER(14) NOT NULL, "
            "PART_CNT NUMBER(12) NOT NULL, BODY_B64 CLOB, PRIMARY KEY (JOB_ID, SEQ_NO), "
            "CHECK (BYTE_CNT > 0 AND ((SEQ_NO = 0 AND PART_CNT > 0) OR (SEQ_NO > 0 AND PART_CNT = 0))))")


def contract(owner, prefix):
    """R7 적재기의 대상 정의와 DDL 함수."""
    tmp = Path(tempfile.mkdtemp(prefix='r7-flow-'))
    with zipfile.ZipFile(HERE / 'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip') as z:
        z.extractall(tmp)
    sys.path[:0] = [str(tmp), str(tmp / 'engine')]
    from prod_config import target
    import gold_io
    tgt = target({'TARGET_MODE': 'GOLD', 'GOLD_OWNER': owner, 'TABLE_PREFIX': prefix})
    path = tmp / ('contract-%s-%s.json' % (owner, prefix))
    path.write_text(json.dumps(tgt))
    return gold_io.Contract(path)


def render(items):
    return '\n'.join('-- [%s] %s\n%s\n' % (i, d, s) for i, d, s in items)


def create_statements(owner, prefix, tag):
    c = contract(owner, prefix)
    out = []
    for key in B.ORDER:
        out.append(('%s%02d' % (tag, len(out) + 1), c.table(key) + ' 만들기', c.ddl(key)))
        for ddl in c.indexes(key):
            out.append(('%s%02d' % (tag, len(out) + 1), ddl.split(' ON ')[0].replace('CREATE INDEX ', '') + ' 인덱스', ddl))
    return c, out


def pipe_check():
    parts = ' UNION ALL '.join("SELECT %s C,%s T,%s R FROM DUAL" % (B.q(n), B.q(t), B.q('N' if r else 'Y'))
                               for n, t, r in PIPE_COLS)
    return ("WITH E AS (" + parts + "), A AS (SELECT COLUMN_NAME C, DATA_TYPE||CASE WHEN DATA_TYPE='VARCHAR2' "
            "THEN '('||DATA_LENGTH||' '||DECODE(CHAR_USED,'B','BYTE','CHAR')||')' WHEN DATA_TYPE='NUMBER' "
            "THEN '('||DATA_PRECISION||','||DATA_SCALE||')' END T, NULLABLE R FROM ALL_TAB_COLUMNS "
            "WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_PIPE_RESULT_A') "
            "SELECT NVL(E.C,A.C) COLUMN_NAME, E.T EXP_TYPE, A.T ACT_TYPE, E.R EXP_NULL, A.R ACT_NULL "
            "FROM E FULL OUTER JOIN A ON E.C=A.C WHERE E.C IS NULL OR A.C IS NULL OR E.T<>A.T OR E.R<>A.R ORDER BY 1")


def check_statements(owner):
    gold = [(owner, B.GOLD[k]['name']) for k in B.ORDER]
    agents = [(AGENT_OWNER, a[1]) for a in B.AGENT.values()] + [PIPE]
    exist = ("SELECT OWNER, TABLE_NAME, NUM_ROWS FROM ALL_TABLES WHERE ("
             + B.in_list(gold + agents).format(col='TABLE_NAME') + ") ORDER BY 1,2")
    privs = ("SELECT TABLE_SCHEMA, TABLE_NAME, LISTAGG(PRIVILEGE, ',') WITHIN GROUP (ORDER BY PRIVILEGE) PRIVILEGES "
             "FROM ALL_TAB_PRIVS WHERE GRANTEE=USER AND ("
             + B.in_list(gold + agents).format(col='TABLE_NAME').replace('OWNER=', 'TABLE_SCHEMA=')
             + ") GROUP BY TABLE_SCHEMA, TABLE_NAME ORDER BY 1,2")
    anyp = ("SELECT PRIVILEGE FROM SESSION_PRIVS WHERE PRIVILEGE IN ('SELECT ANY TABLE','INSERT ANY TABLE',"
            "'UPDATE ANY TABLE','DELETE ANY TABLE','CREATE ANY TABLE','CREATE ANY INDEX','ANALYZE ANY') ORDER BY 1")
    return [
        ('Q01', '지금 접속 계정 — 이 계정이 Dataiku 적재 계정(EXPECTED_DB_USER)이어야 함',
         "SELECT USER AS LOGIN, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB, SYS_CONTEXT('USERENV','CON_NAME') AS PDB FROM DUAL"),
        ('Q02', '표 18개 — Gold 13(%s) + Agent 중간표 1 + 서빙 기록 4 (SIDDA). 18행이면 다 있음' % owner, exist),
        ('Q03', 'Gold 13·서빙 기록 4 컬럼이 기준(gold_b003_r5)과 다른 곳 — 0행이어야 함', B.verify_columns_sql(owner, AGENT_OWNER)),
        ('Q04', 'PK·인덱스 이름과 컬럼이 기준과 다른 곳 — 0행이어야 함 (적재기는 X1~X4_ 인덱스 이름으로 찾음)',
         B.verify_keys_sql(owner, AGENT_OWNER)),
        ('Q05', 'Agent 중간표 SIDDA.LGL_PIPE_RESULT_A 컬럼이 기준과 다른 곳 — 0행이어야 함', pipe_check()),
        ('Q06', '이 계정이 직접 받은 표 권한 (역할로 받은 권한은 안 나옴 — Q07도 볼 것)', privs),
        ('Q07', '이 계정의 ANY 권한 (있으면 Q06에 없어도 됨)', anyp),
    ]


def main_channel(owner, prefix, serving):
    t = owner + '.' + prefix + 'SRCH_CHNL'
    return [
        ('M01', '지금 채널 확인', 'SELECT RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO FROM %s ORDER BY RFRN_CHNL_NAME' % t),
        ('M02', 'main 추가 — 지금 서빙 채널과 같은 세대를 가리킴 (이미 있으면 0행)',
         "INSERT INTO %s (RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO) SELECT 'main', RFRN_POST_HASH_VALU, 1 FROM %s "
         "WHERE RFRN_CHNL_NAME = '%s' AND NOT EXISTS (SELECT 1 FROM %s WHERE RFRN_CHNL_NAME = 'main')" % (t, t, serving, t)),
        ('M03', '저장', 'COMMIT'),
        ('M04', "확인 — main 과 %s 가 같은 RFRN_POST_HASH_VALU 이면 완료" % serving,
         'SELECT RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO FROM %s ORDER BY RFRN_CHNL_NAME' % t),
    ]


def write(name, head, items):
    text = head + '\n' + render(items)
    if any(s.rstrip().endswith(';') for _, _, s in items):
        raise SystemExit('세미콜론으로 끝나는 문장: ' + name)
    (HERE / name).write_text(text, encoding='utf-8')
    return len(items)


ROLE = {  # 표 → (누가 쓰나, 누가 읽나)
    'DOC_VER': ('03_LOAD', '서빙·증분'), 'DOC_UNIT': ('03_LOAD', '서빙·증분'), 'DOC_BLK': ('03_LOAD', '서빙·증분'),
    'SRC_POST': ('03_LOAD', '서빙·증분'), 'SRCH_POST': ('03_LOAD', '서빙·증분'), 'SRCH_ROW': ('03_LOAD', '서빙'),
    'SRCH_CHNL': ('03_LOAD(세대 채널)·증분(main 교체)', '서빙'), 'ONTL_POST': ('온톨로지 게시', '서빙(켰을 때)'),
    'ONTL_HEAD': ('온톨로지 게시', '서빙(켰을 때)'), 'ONTL_ANC': ('온톨로지 게시', '서빙(켰을 때)'),
    'VCTR_POST': ('03_LOAD', '서빙·증분'), 'VCTR_ITEM': ('03_LOAD', '서빙'), 'VCTR_HEAD': ('증분 activate·벡터 활성화 SQL', '서빙'),
}


def logical_names():
    import openpyxl
    path = next((ROOT / '07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R19').glob('*.xlsx'))
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for key, sheet in zip(B.ORDER, wb.sheetnames[1:]):
        rows = list(wb[sheet].iter_rows(values_only=True))
        title = rows[0][0].split('   ', 1)[1].strip()
        definition = rows[2][1]
        start = next(i for i, r in enumerate(rows) if r[0] == '논리명') + 1
        cols = []
        for r in rows[start:]:
            if not r[0] or not r[1] or str(r[0]).startswith(('0', '1')) and '인덱스' in str(r[0]):
                break
            cols.append((r[0], r[7]))
        if len(cols) != len(B.GOLD[key]['columns']):
            raise SystemExit('R19 컬럼 수 다름: ' + key)
        out[key] = (sheet[3:], title, definition, cols)
    return out


def design_doc():
    names = logical_names()
    L = ['# 파이프라인 Oracle 표 설계 R1 (2026-11-12)', '',
         '정의 원본: `00_SYSTEM/ORACLE/gold_b003_r5.json`(운영 Gold 등록과 같음, 타입·필수·키). 한글 이름·정의: R19 정의서.',
         '개발계·운영 표 이름은 같고 소유자만 다르다. 생성 DDL은 적재기 검사 함수와 같은 규칙으로 만든 `CREATE_GOLD_TABLES_SIDDG_R1.txt`.', '',
         '## 1. 흐름에서 쓰는 표', '',
         '| 층 | 표 | 한글 이름 | 개발계 소유자 | 운영 소유자 | 쓰는 곳 | 읽는 곳 |', '|---|---|---|---|---|---|---|',
         '| Agent | LGL_PIPE_RESULT_A | GENOS 처리 결과 조각 | SIDDA | SIDDA | GENOS(ORDS) | 02_WAIT·03_LOAD, 증분이 적재 뒤 삭제 |']
    for key in B.ORDER:
        L.append('| Gold | %s | %s | SIDDS | SIDDG | %s | %s |' % (B.GOLD[key]['name'], names[key][1], *ROLE[key]))
    L.append('| 서빙 기록 | LGL_AGT_RUN_A·REC_A·BODY_A, LGL_EXEC_ST_A | 질문 기록·상태 | SIDDA | SIDDA | 코드서빙 | 코드서빙 (파이프라인은 안 씀) |')
    L += ['', '증분 처리는 새 표를 쓰지 않는다. 상태·업데이트 기록(최근 3개)은 Dataiku 관리 폴더 JSON.', '',
          '## 2. 권한', '',
          '| 계정 | 표 | 권한 | 왜 |', '|---|---|---|---|',
          '| GENOS ORDS 계정(개발계 BAIP04APP) | SIDDA.LGL_PIPE_RESULT_A | SELECT, INSERT | 결과 조각 저장 |',
          '| Dataiku 계정(PIDD2APP) | SIDDA.LGL_PIPE_RESULT_A | SELECT, DELETE | 결과 읽기, 증분이 적재 끝난 결과 지우기 |',
          '| Dataiku 계정 | Gold 13표 | SELECT, INSERT | 03_LOAD |',
          '| Dataiku 계정 | Gold SRCH_CHNL (증분), SRCH_ROW·VCTR_ITEM·VCTR_HEAD·SRCH_CHNL (R7f) | UPDATE | 증분 activate의 채널 교체, 판본 선택 보완 R7f의 번호 교체 |',
          '| Dataiku 계정 | Gold 13표 | DELETE | 증분 옛 세대 정리(지금+이전 2개만 남김) |',
          '| 코드서빙 ORDS 계정 | Gold 13표 SELECT, 서빙 기록 4표 SELECT·INSERT·UPDATE·DELETE | | 질문 처리 |', '',
          '## 3. Gold 13표 상세', '']
    for key in B.ORDER:
        t = B.GOLD[key]
        sheet, title, definition, cols = names[key]
        L += ['### %s — %s' % (t['name'], title), '', definition or '', '',
              '| 논리명 | 물리명 | 타입 | 필수 | 기본값 | PK |', '|---|---|---|---|---|---|']
        pk = [t['columns'][c]['name'] for c in t['primary_key']]
        for (logical, _), col in zip(cols, t['columns'].values()):
            L.append('| %s | %s | %s | %s | %s | %s |' % (logical, col['name'], col['type'], 'Y' if col['required'] else '',
                                                        col['default'] or '', pk.index(col['name']) + 1 if col['name'] in pk else ''))
        L.append('')
        L.append('- PK `X0_%s` (%s)' % (t['name'], ', '.join(pk)))
        for i, idx in enumerate(t['indexes'], 1):
            L.append('- 인덱스 `X%d_%s` (%s)' % (i, t['name'], ', '.join(t['columns'][c]['name'] for c in idx)))
        L.append('')
    L += ['## 4. Agent 중간표 SIDDA.LGL_PIPE_RESULT_A', '',
          'GENOS가 구조화·색인 결과(result.zip)를 72,000바이트 조각으로 나눠 base64로 넣는다. 순번 0번 행이 "다 넣었음" 표시(전체 해시·조각 수).',
          '조각은 바꾸지 않는다(UPDATE 없음). Dataiku가 조각을 이어 붙여 해시를 확인한 뒤 Gold로 올린다.', '',
          '| 컬럼 | 타입 | 필수 | 뜻 |', '|---|---|---|---|',
          '| JOB_ID | VARCHAR2(32 BYTE) | Y | GENOS 작업 번호 (PK 1) |', '| SEQ_NO | NUMBER(12) | Y | 조각 순번, 0 = 완료 표시 (PK 2) |',
          '| BIND_HASH | VARCHAR2(64 BYTE) | Y | 입력 ZIP·코드 결속 해시 |', '| DATA_HASH | VARCHAR2(64 BYTE) | Y | 조각(0번은 전체) 해시 |',
          '| BYTE_CNT | NUMBER(14) | Y | 조각(0번은 전체) 바이트 수 |', '| PART_CNT | NUMBER(12) | Y | 0번 행만 조각 수, 나머지 0 |',
          '| BODY_B64 | CLOB | | 조각 내용 base64 (0번은 비움) |', '',
          'CHECK: `BYTE_CNT > 0 AND ((SEQ_NO = 0 AND PART_CNT > 0) OR (SEQ_NO > 0 AND PART_CNT = 0))`', '']
    (HERE / '테이블_설계_R1.md').write_text('\n'.join(L), encoding='utf-8')


def main():
    design_doc()
    counts = {}
    for owner, env in (('SIDDS', '개발계'), ('SIDDG', '운영계')):
        counts['CHECK_TABLES_%s_R1.txt' % owner] = write(
            'CHECK_TABLES_%s_R1.txt' % owner,
            '-- %s 파이프라인 표 확인 R1 (읽기 전용, SELECT만). Dataiku SQL 노트북에서 [번호] 한 개씩 별도 Query로, ; 없이 실행.\n'
            '-- Gold 소유자 %s(프로젝트 변수 LGL_GOLD_OWNER와 같아야 함), Agent 중간표·서빙 기록 SIDDA.\n' % (env, owner),
            check_statements(owner))
    _, gold = create_statements('SIDDG', 'IDD_B003_LGL_', 'G')
    counts['CREATE_GOLD_TABLES_SIDDG_R1.txt'] = write(
        'CREATE_GOLD_TABLES_SIDDG_R1.txt',
        '-- Gold 13표 생성 DDL (DBA 요청용, 운영 등록 IDD_B003과 같은 정의). 이미 있으면 실행하지 않는다.\n'
        '-- 운영 Gold는 메타 등록 → DBA 생성 절차. 소유자만 다르게 쓰려면 tables.py로 다시 만든다.\n'
        '-- 인덱스 이름 X0_~X4_<표>는 적재기가 이 이름으로 찾는다(바꾸면 INDEX_COLUMNS_MISMATCH·RESUME_INDEX_MISSING).\n',
        gold)
    counts['CREATE_AGENT_STAGE_R1.txt'] = write(
        'CREATE_AGENT_STAGE_R1.txt',
        '-- Agent 중간표 SIDDA.LGL_PIPE_RESULT_A (GENOS가 구조화·색인 결과를 조각으로 넣는 표). 없을 때만, SIDDA 소유자 또는 DBA가 실행.\n'
        '-- 권한: GENOS ORDS 계정 SELECT, INSERT / Dataiku 계정 SELECT, DELETE (DELETE는 증분이 적재 끝난 결과를 지울 때).\n',
        [('A01', 'Agent 중간표 만들기', PIPE_DDL)])
    _, test = create_statements('SIDDS', 'TST_B003_LGL_', 'T')
    counts['CREATE_TEST_COPY_SIDDS_R1.txt'] = write(
        'CREATE_TEST_COPY_SIDDS_R1.txt',
        '-- 증분 실험용 Gold 시험 복사본 13표 (구조만, 데이터 0). SIDDS.TST_B003_LGL_* — 운영 이름 표는 건드리지 않는다.\n'
        '-- 실험 동안 프로젝트 변수 LGL_GOLD_TABLE_PREFIX=TST_B003_LGL_ (LGL_GOLD_OWNER=SIDDS 그대로). 끝나면 변수를 지우고 DROP_TEST_COPY_SIDDS_R1.txt.\n',
        test)
    counts['DROP_TEST_COPY_SIDDS_R1.txt'] = write(
        'DROP_TEST_COPY_SIDDS_R1.txt',
        '-- 시험 복사본 지우기. TST_B003_LGL_ 표만. 운영 이름 IDD_B003_LGL_ 표는 여기 없다.\n',
        [('D%02d' % (i + 1), 'SIDDS.TST_B003_LGL_' + k + ' 지우기', 'DROP TABLE SIDDS.TST_B003_LGL_' + k + ' PURGE')
         for i, k in enumerate(B.ORDER)])
    counts['MAIN_CHANNEL_SIDDS_R1.txt'] = write(
        'MAIN_CHANNEL_SIDDS_R1.txt',
        '-- 개발계 서빙 채널을 main 으로 (DEV_MAIN_CHANNEL_R1의 Gold 이름판, CHAN_ORD→CHAN_NO).\n'
        '-- 왜: 지금 서빙 채널 g19_7c1f… 는 적재기가 세대마다 자동으로 만드는 이름이라 증분이 세대를 바꾸고 되돌릴 때 적재기와 부딪힌다.\n'
        '-- main 한 줄만 추가한다(기존 행 그대로). 그다음 코드서빙 DP_QUERY_CHANNEL=main 으로 바꾸고 재기동, 질문 하나로 확인.\n'
        "-- 되돌리기: DELETE FROM SIDDS.IDD_B003_LGL_SRCH_CHNL WHERE RFRN_CHNL_NAME = 'main' → COMMIT → DP_QUERY_CHANNEL 원래 값으로.\n",
        main_channel('SIDDS', 'IDD_B003_LGL_', 'g19_7c1f8f4931c8be61b914f5bc'))
    t = 'SIDDS.TST_B003_LGL_SRCH_CHNL'
    counts['MAIN_CHANNEL_TEST_COPY_R1.txt'] = write(
        'MAIN_CHANNEL_TEST_COPY_R1.txt',
        '-- 시험 복사본에 기준 세대를 적재한 뒤 main 채널 만들기. 기준 세대 하나만 적재한 상태(g19_ 채널 1개)에서만 추가된다.\n'
        '-- g19_ 채널이 2개 이상이면 0행 — 어느 세대인지 M01로 보고 직접 정한다.\n',
        [('M01', '지금 채널 확인 — g19_ 한 줄이어야 함', 'SELECT RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO FROM %s ORDER BY RFRN_CHNL_NAME' % t),
         ('M02', 'main 추가 (g19_ 채널이 딱 1개이고 main이 없을 때만)',
          "INSERT INTO %s (RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO) SELECT 'main', RFRN_POST_HASH_VALU, 1 FROM %s "
          "WHERE RFRN_CHNL_NAME LIKE 'g19\\_%%' ESCAPE '\\' AND NOT EXISTS (SELECT 1 FROM %s WHERE RFRN_CHNL_NAME = 'main') "
          "AND (SELECT COUNT(*) FROM %s WHERE RFRN_CHNL_NAME LIKE 'g19\\_%%' ESCAPE '\\') = 1" % (t, t, t, t)),
         ('M03', '저장', 'COMMIT'),
         ('M04', '확인 — main 과 g19_ 줄이 같은 RFRN_POST_HASH_VALU', 'SELECT RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO FROM %s ORDER BY RFRN_CHNL_NAME' % t)])
    test_tables = ['SIDDS.TST_B003_LGL_' + k for k in B.ORDER]
    counts['GRANT_TEST_COPY_SIDDS_R1.txt'] = write(
        'GRANT_TEST_COPY_SIDDS_R1.txt',
        '-- 증분 실험 권한 (SIDDS 소유자 또는 DBA가 실행). 시험 복사본 13표 + 기존 Agent 중간표 삭제 권한.\n'
        '-- 받는 계정 PIDD2APP = Dataiku AIDP 연결 계정(03_LOAD·증분 셀이 쓰는 계정). 다르면 바꿔서 실행.\n',
        [('G%02d' % (i + 1), t + ' 읽기·쓰기', 'GRANT SELECT, INSERT, UPDATE, DELETE ON ' + t + ' TO PIDD2APP')
         for i, t in enumerate(test_tables)]
        + [('G14', 'Agent 중간표 — 증분이 적재 끝난 결과 조각을 지움 (SELECT는 이미 있음)',
            'GRANT DELETE ON SIDDA.LGL_PIPE_RESULT_A TO PIDD2APP')])
    gold_tables = ['SIDDS.' + B.GOLD[k]['name'] for k in B.ORDER]
    counts['GRANT_GOLD_INCREMENT_SIDDS_R1.txt'] = write(
        'GRANT_GOLD_INCREMENT_SIDDS_R1.txt',
        '-- (나중에) 실험이 끝나고 실제 개발계 Gold(IDD_B003)에 증분을 붙일 때만. 지금 실험에는 필요 없다.\n'
        '-- 03_LOAD가 새 세대를 넣고(INSERT), 증분이 main 채널을 바꾸고(UPDATE) 옛 세대를 지운다(DELETE).\n',
        [('H%02d' % (i + 1), t, 'GRANT SELECT, INSERT, UPDATE, DELETE ON ' + t + ' TO PIDD2APP')
         for i, t in enumerate(gold_tables)])
    check = check_statements('SIDDS')
    check = [(i, d.replace('Gold 13', '시험 복사본 13').replace('IDD_B003', 'TST_B003'),
              q.replace('IDD_B003_LGL_', 'TST_B003_LGL_')) for i, d, q in check]
    counts['CHECK_TEST_COPY_SIDDS_R1.txt'] = write(
        'CHECK_TEST_COPY_SIDDS_R1.txt',
        '-- 시험 복사본 확인 (읽기 전용). CREATE_TEST_COPY·GRANT 다음에 실행. Q02 18행, Q03~Q05 0행, Q06에 13표 SELECT,INSERT,UPDATE,DELETE.\n',
        check)
    print(json.dumps(counts, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
