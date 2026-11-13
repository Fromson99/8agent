"""증분 처리용 추가 Gold 3표 — 설계 한 곳에서 DDL·GRANT·확인 SQL·메타 등록 엑셀(R20 형식)을 만든다.

기존 RAG Gold 13표(IDD_B003_LGL_DOC_VER …)는 그대로. 이번에 새로 신청할 것은 증분 처리의 문서·판본·조문 변경 이력.
증분 실행 기록(판단 실행·되돌리기용 옛 파일)은 Gold가 아니라 Dataiku 관리 폴더(S3)에 그대로 둔다.
"""
from copy import copy
import json
from pathlib import Path
import re

import openpyxl
from openpyxl.styles import Alignment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TEMPLATE = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1/법률에이전트_B003_골드테이블_메타등록_R20.xlsx'
XLSX = HERE / '법률에이전트_B003_증분Gold_메타등록_R2.xlsx'
TS = 'TIMESTAMP(6) WITH TIME ZONE'


def col(name, logical, typ, required, definition, korean='N', default=None):
    return {'name': name, 'logical': logical, 'type': typ, 'required': required, 'default': default,
            'definition': definition, 'korean': korean}


# 기존 RAG Gold 13표(최종 등록본·11-04 신청 작업함)에 실제로 쓰인 도메인과 크기 — 새 컬럼은 이 안에서만 고른다.
# R20 엑셀 17_표준용어_도메인 시트에서 다시 뽑아 같은지 검사한다(build 때).
CATALOG = {
    'ID': ['VARCHAR2(50 BYTE)', 'VARCHAR2(100 BYTE)'],
    '값': ['VARCHAR2(100 BYTE)'],
    '내용': ['CLOB', 'VARCHAR2(3000 BYTE)'],
    '명': ['VARCHAR2(100 BYTE)', 'VARCHAR2(2250 BYTE)'],
    '번호': ['NUMBER(30,0)'],
    '여부': ['VARCHAR2(1 BYTE)'],
    '일시': [TS],
}
SUFFIX = {'ID': 'ID', 'VALU': '값', 'CTNT': '내용', 'NAME': '명', 'NO': '번호', 'YN': '여부', 'ASTM': '일시'}
RGSN = col('RGSN_ASTM', '등록일시', TS, True, '행을 처음 기록한 시각이다. 기본값으로 저장 시각을 넣는다.', '해당 없음', 'SYSTIMESTAMP')
DESIGN = {
    'RGLT_DOC': {
        'logical': '규정문서내역', 'kind': 'MASTER',
        'definition': '법령·행정규칙·내규 문서를 판본과 무관하게 하나로 묶는 문서 목록을 관리하는 엔티티이다. 한 건은 문서 하나이며 판본이 바뀌어도 '
                      '원천문서ID는 그대로다. Gold 원문 표의 규정문서ID는 판본마다 바뀌므로 이 ID로 판본 이력을 잇는다.',
        'process': '증분 판단 때 들어온 원문에서 법령ID·행정규칙ID 또는 정식 문서명으로 원천문서ID를 정해 없으면 추가하고, 반영·되돌리기 때 활성버전ID를 바꾼다.',
        'source': '떨어진 원문 파일(법제처 XML·내규 docx) → GENOS 구조화 결과의 문서 머리 정보', 'when': '증분 판단·반영 시 (일 배치 예정, 시각 미정)',
        'columns': [
            col('SRC_DOC_ID', '원천문서ID', 'VARCHAR2(100 BYTE)', True,
                '원천에서 부여한, 판본이 바뀌어도 그대로인 문서 식별값이다. LAW:<법령ID> / ADMRUL:<행정규칙ID> / INTERNAL:<정식 문서명 해시 앞 16자리>.'),
            col('RGLT_DOC_NAME', '규정문서명', 'VARCHAR2(2250 BYTE)', True, '문서의 정식 이름이다. 최신 판본의 이름으로 갱신한다.', 'Y'),
            col('SRC_TYPE_VALU', '원천유형값', 'VARCHAR2(100 BYTE)', True, '문서 출처 유형이다. LAW(법령) / ADMRUL(행정규칙) / INTERNAL(내규).'),
            col('ACTV_VER_ID', '활성버전ID', 'VARCHAR2(100 BYTE)', False, '지금 서빙 중인 판본의 규정버전ID다. 반영·되돌리기 때 바뀐다. 아직 반영 전이면 비어 있다.'),
            col('DOC_ADDN_IFMN_CTNT', '문서부가정보내용', 'CLOB', False, '같은 문서가 들어 있는 팀 폴더 경로, 별칭 등 부가정보 JSON이다.', 'Y'),
            RGSN,
            col('CHAN_ASTM', '변경일시', TS, True, '이 행을 마지막으로 바꾼 시각이다(활성 판본 변경 등).', '해당 없음', 'SYSTIMESTAMP'),
        ],
        'primary_key': ['SRC_DOC_ID'], 'indexes': [],
    },
    'RGLT_VER': {
        'logical': '규정판본내역', 'kind': 'HISTORY',
        'definition': '문서의 판본(원문 파일 하나)마다 공포·시행 시점, 증분 판단 결과, 반영된 Gold 세대를 관리하는 엔티티이다. 한 건은 들어온 원문 파일 하나이며 '
                      '원본 해시가 같으면 같은 판본이다. 반영되지 않은 보류·시행일 대기 판본도 남긴다.',
        'process': '떨어진 파일의 원본 해시로 판본 행을 만들고, 조문 비교·판정 결과를 상태로 기록한다. 반영되면 Gold 세대 ID와 활성일시를, 다음 판본이 들어오거나 '
                   '되돌리면 대체일시를 채운다.',
        'source': '떨어진 원문 파일 · 증분 판단(decide) · Gold 적재 결과(03_LOAD)', 'when': '증분 판단·반영·되돌리기 시',
        'columns': [
            col('RGLT_VER_ID', '규정버전ID', 'VARCHAR2(100 BYTE)', True, '판본 식별값으로 원본 파일의 SHA-256 해시(64자리)를 쓴다.'),
            col('SRC_DOC_ID', '원천문서ID', 'VARCHAR2(100 BYTE)', True, '이 판본이 속한 문서의 원천문서ID다.'),
            col('RGLT_DOC_ID', '규정문서ID', 'VARCHAR2(100 BYTE)', False, 'Gold 원문 표(문서판본내역 등)의 규정문서ID다. 원문 해시 앞 16자리로 Gold 적재 뒤 채운다.'),
            col('SRC_FILE_NAME', '원천파일명', 'VARCHAR2(2250 BYTE)', True, '들어온 원문 파일의 이름이다(폴더 경로 제외).', 'Y'),
            col('PRMG_ASTM', '공포일시', TS, False, '공포·발령 일자다. 날짜만 있으므로 그날 0시(한국시간)로 넣는다. 공포번호는 버전부가정보내용에 둔다.', '해당 없음'),
            col('ENFC_ASTM', '시행일시', TS, False, '문서 시행일이다. 마지막 부칙에서 읽어 그날 0시(한국시간)로 넣는다. 못 읽으면 비우고 보류한다.', '해당 없음'),
            col('VER_STTS_VALU', '버전상태값', 'VARCHAR2(100 BYTE)', True,
                'APPLIED(반영) / WAIT_EFFECTIVE(시행일 대기) / HOLD(보류) / SUPERSEDED(다음 판본으로 대체) / ROLLED_BACK(되돌림).'),
            col('RFRN_POST_HASH_VALU', '조회게시해시값', 'VARCHAR2(100 BYTE)', False, '이 판본을 처음 반영한 Gold 세대(검색 게시)의 조회게시해시값이다.'),
            col('VER_ADDN_IFMN_CTNT', '버전부가정보내용', 'CLOB', False, '공포번호, 판정 사유·경고, 조문 변경 건수 등 판단 결과 JSON이다.', 'Y'),
            RGSN,
            col('ACTV_ASTM', '활성일시', TS, False, '이 판본이 서빙에 반영된 시각이다.', '해당 없음'),
            col('SPSD_ASTM', '대체일시', TS, False, '다음 판본으로 바뀌었거나 되돌린 시각이다.', '해당 없음'),
        ],
        'primary_key': ['RGLT_VER_ID'], 'indexes': [['SRC_DOC_ID']],
        'index_names': ['규정판본내역문서별조회'], 'index_uses': ['문서 하나의 판본 이력을 조회한다(문서당 판본 수 건 — 순서는 등록일시로 정렬).'],
    },
    'ARTC_CMPR': {
        'logical': '조문비교내역', 'kind': 'HISTORY',
        'definition': '새 판본을 반영할 때 이전 판본과 조문 단위로 비교한 결과(신구조문 대비표)를 관리하는 엔티티이다. 한 건은 바뀐 조문 하나(신설·삭제·개정·이동)이며 '
                      '변경 없는 조문은 남기지 않는다. 옛 Gold 세대를 지운 뒤에도 무엇이 바뀌었는지 조회할 수 있게 조문 내용을 보존한다.',
        'process': '증분 판단에서 이전 판본(Gold 지금 세대)과 새 구조화 결과를 조문 계보로 맞춰 변경 유형·유사도를 계산하고, 바뀐 조문만 번호를 붙여 적재한다.',
        'source': '증분 판단(decide)의 조문 비교 결과', 'when': '증분 판단 시',
        'columns': [
            col('RGLT_VER_ID', '규정버전ID', 'VARCHAR2(100 BYTE)', True, '비교한 새 판본의 규정버전ID다.'),
            col('CMPR_NO', '비교번호', 'NUMBER(30,0)', True, '한 판본 안에서 바뀐 조문에 붙인 1부터의 번호다.', '해당 없음'),
            col('BASE_VER_ID', '기준버전ID', 'VARCHAR2(100 BYTE)', False, '비교 기준이 된 이전 판본의 규정버전ID다. 처음 들어온 문서면 비어 있다.'),
            col('CHAN_TYPE_VALU', '변경유형값', 'VARCHAR2(100 BYTE)', True,
                'ADD(신설) / DELETE(삭제) / AMEND(개정) / MOVE(이동) / MOVE_AMEND(이동·개정) / REF_ONLY(인용 번호만 변경).'),
            col('BFR_ARTC_KEY_VALU', '이전조문키값', 'VARCHAR2(100 BYTE)', False, '이전 판본의 조문 위치다(예: 제26조, 제2조의2, 부칙). 신설이면 비어 있다.', 'Y'),
            col('AFTR_ARTC_KEY_VALU', '이후조문키값', 'VARCHAR2(100 BYTE)', False, '새 판본의 조문 위치다. 삭제면 비어 있다.', 'Y'),
            col('BFR_ARTC_CTNT', '이전조문내용', 'CLOB', False, '이전 판본의 조문 본문이다.', 'Y'),
            col('AFTR_ARTC_CTNT', '이후조문내용', 'CLOB', False, '새 판본의 조문 본문이다.', 'Y'),
            col('CMPR_ADDN_IFMN_CTNT', '비교부가정보내용', 'CLOB', False, '본문 유사도(0~1), 조문별 시행일(부칙 예외) 등 비교 부가정보 JSON이다.', 'Y'),
            RGSN,
        ],
        'primary_key': ['RGLT_VER_ID', 'CMPR_NO'], 'indexes': [],
    },
}
ORDER = ['RGLT_DOC', 'RGLT_VER', 'ARTC_CMPR']
SHEETS = {'RGLT_DOC': '01_규정문서', 'RGLT_VER': '02_규정판본', 'ARTC_CMPR': '03_조문비교'}
# 약어 → 표준단어. 기존 Gold(R20)에 이미 있는 것과 이번에 새로 신청할 것을 나눈다.
KNOWN = {'RGLT': '규정', 'DOC': '문서', 'ID': 'ID', 'NAME': '명', 'ADDN': '부가', 'IFMN': '정보', 'CTNT': '내용', 'RGSN': '등록',
         'ASTM': '일시', 'RFRN': '조회', 'POST': '게시', 'HASH': '해시', 'VALU': '값', 'CHAN': '변경', 'TYPE': '유형', 'VER': '버전', 'NO': '번호'}
NEW = {'SRC': '원천', 'ACTV': '활성', 'FILE': '파일', 'PRMG': '공포', 'ENFC': '시행', 'STTS': '상태', 'SPSD': '대체', 'CMPR': '비교',
       'BASE': '기준', 'BFR': '이전', 'AFTR': '이후', 'ARTC': '조문', 'KEY': '키'}


def tname(key, prefix='IDD_B003_LGL_'):
    return prefix + key


def ddl(owner, prefix='IDD_B003_LGL_'):
    out = []
    for key in ORDER:
        t, name = DESIGN[key], tname(key, prefix)
        fields = [c['name'] + ' ' + c['type'] + (' DEFAULT ' + c['default'] if c['default'] else '') + (' NOT NULL' if c['required'] else '')
                  for c in t['columns']]
        fields.append('CONSTRAINT X0_' + name + ' PRIMARY KEY (' + ','.join(t['primary_key']) + ')')
        out.append((owner + '.' + name + ' 만들기', 'CREATE TABLE ' + owner + '.' + name + ' (' + ','.join(fields) + ')'))
        for i, cols in enumerate(t['indexes'], 1):
            out.append((owner + '.X%d_' % i + name + ' 인덱스',
                        'CREATE INDEX %s.X%d_%s ON %s.%s (%s)' % (owner, i, name, owner, name, ','.join(cols))))
    return out


def q(s):
    return "'" + s.replace("'", "''") + "'"


def typ(t):
    if t.startswith('VARCHAR2'):
        return 'VARCHAR2', int(re.search(r'\((\d+)', t)[1]), None, None
    if t.startswith('NUMBER'):
        p, s = re.match(r'NUMBER\((\d+),(\d+)\)', t).groups()
        return 'NUMBER', None, int(p), int(s)
    return t, None, None, None


def lit(v):
    return 'NULL' if v is None else str(v) if isinstance(v, int) else q(v)


def checks(owner):
    names = [tname(k) for k in ORDER]
    inl = ','.join(q(n) for n in names)
    e = ' UNION ALL '.join('SELECT %s T,%s C,%s DT,%s DL,%s DP,%s DS,%s NU,%s DF FROM DUAL' % (
        q(tname(k)), q(c['name']), *(lit(x) for x in typ(c['type'])), q('N' if c['required'] else 'Y'), lit(c['default']))
        for k in ORDER for c in DESIGN[k]['columns'])
    cols = ("WITH E AS (" + e + "), A AS (SELECT TABLE_NAME T,COLUMN_NAME C,DATA_TYPE DT,"
            "CASE WHEN DATA_TYPE='VARCHAR2' AND CHAR_USED='B' THEN DATA_LENGTH END DL,"
            "CASE WHEN DATA_TYPE='NUMBER' THEN DATA_PRECISION END DP,CASE WHEN DATA_TYPE='NUMBER' THEN DATA_SCALE END DS,NULLABLE NU "
            "FROM ALL_TAB_COLUMNS WHERE OWNER=%s AND TABLE_NAME IN (%s)) "
            "SELECT NVL(E.T,A.T) TABLE_NAME,NVL(E.C,A.C) COLUMN_NAME,E.DT EXP_TYPE,A.DT ACT_TYPE,E.DL EXP_LEN,A.DL ACT_LEN,E.DP EXP_PREC,A.DP ACT_PREC,"
            "E.NU EXP_NULL,A.NU ACT_NULL FROM E FULL OUTER JOIN A ON E.T=A.T AND E.C=A.C "
            "WHERE E.C IS NULL OR A.C IS NULL OR E.DT<>A.DT OR DECODE(E.DL,A.DL,0,1)=1 OR DECODE(E.DP,A.DP,0,1)=1 "
            "OR DECODE(E.DS,A.DS,0,1)=1 OR E.NU<>A.NU ORDER BY 1,2") % (q(owner), inl)
    keys = []
    for k in ORDER:
        t, n = DESIGN[k], tname(k)
        keys.append((n, 'X0_' + n, ','.join(t['primary_key'])))
        keys += [(n, 'X%d_%s' % (i, n), ','.join(c)) for i, c in enumerate(t['indexes'], 1)]
    e = ' UNION ALL '.join('SELECT %s T,%s N,%s COLS FROM DUAL' % (q(a), q(b), q(c)) for a, b, c in keys)
    idx = ("WITH E AS (" + e + "), A AS (SELECT I.TABLE_NAME T,I.INDEX_NAME N,"
           "LISTAGG(C.COLUMN_NAME,',') WITHIN GROUP (ORDER BY C.COLUMN_POSITION) COLS FROM ALL_INDEXES I "
           "JOIN ALL_IND_COLUMNS C ON C.INDEX_OWNER=I.OWNER AND C.INDEX_NAME=I.INDEX_NAME "
           "WHERE I.TABLE_OWNER=%s AND I.TABLE_NAME IN (%s) AND I.INDEX_TYPE<>'LOB' GROUP BY I.TABLE_NAME,I.INDEX_NAME) "
           "SELECT NVL(E.T,A.T) TABLE_NAME,E.N EXP_NAME,A.N ACT_NAME,E.COLS EXP_COLS,A.COLS ACT_COLS FROM E FULL OUTER JOIN A "
           "ON E.T=A.T AND E.N=A.N WHERE E.N IS NULL OR A.N IS NULL OR E.COLS<>A.COLS ORDER BY 1,2") % (q(owner), inl)
    return [
        ('Q01', '표 3개 — 3행이면 다 있음', 'SELECT OWNER, TABLE_NAME, NUM_ROWS FROM ALL_TABLES WHERE OWNER=%s AND TABLE_NAME IN (%s) ORDER BY 2' % (q(owner), inl)),
        ('Q02', '컬럼이 설계와 다른 곳 — 0행이어야 함', cols),
        ('Q03', 'PK·인덱스 이름과 컬럼이 설계와 다른 곳 — 0행이어야 함', idx),
        ('Q04', '이 계정이 받은 권한', "SELECT TABLE_NAME, LISTAGG(PRIVILEGE, ',') WITHIN GROUP (ORDER BY PRIVILEGE) PRIVILEGES FROM ALL_TAB_PRIVS "
                                 "WHERE GRANTEE=USER AND TABLE_SCHEMA=%s AND TABLE_NAME IN (%s) GROUP BY TABLE_NAME ORDER BY 1" % (q(owner), inl)),
    ]


def render(items, tag):
    return '\n'.join('-- [%s%02d] %s\n%s\n' % (tag, i, d, s) for i, (d, s) in enumerate(items, 1))


def write_sql():
    head = ('-- 증분 처리용 추가 Gold 3표 R2 (2026-11-12, R1 대체 — 기존 Gold 도메인·크기로 맞춤). Dataiku SQL 노트북에서 [번호] 한 개씩 별도 Query로, 문장 끝 ; 없이.\n'
            '-- 기존 RAG Gold 13표(IDD_B003_LGL_DOC_VER …)는 건드리지 않는다. 표 정의는 개발계·운영 같음, 소유자만 다름.\n')
    files = {
        'CREATE_INCREMENT_GOLD_SIDDS_R2.txt': head + '-- 개발계 SIDDS. SIDDS 소유자 또는 DBA가 실행. 표 3 + PK 3 + 추가 인덱스 1 = 4문장.\n\n' + render(ddl('SIDDS'), 'C'),
        'CREATE_INCREMENT_GOLD_SIDDG_R2.txt': head + '-- 운영 SIDDG. 메타 등록·승인 뒤 DBA 생성 요청용(등록 엑셀 08_DDL 시트와 같음).\n\n' + render(ddl('SIDDG'), 'C'),
        'GRANT_INCREMENT_GOLD_SIDDS_R2.txt': head + '-- 받는 계정 PIDD2APP = Dataiku AIDP 연결 계정(증분 셀). 개발계는 실험 재실행 정리를 위해 DELETE 포함.\n\n'
        + render([(tname(k) + ' 읽기·쓰기', 'GRANT SELECT, INSERT, UPDATE, DELETE ON SIDDS.%s TO PIDD2APP' % tname(k)) for k in ORDER], 'G'),
        'GRANT_INCREMENT_GOLD_SIDDG_R2.txt': head + '-- 운영. 이력 표라 지우지 않는다 — SELECT, INSERT, UPDATE만.\n\n'
        + render([(tname(k) + ' 읽기·쓰기', 'GRANT SELECT, INSERT, UPDATE ON SIDDG.%s TO PIDD2APP' % tname(k)) for k in ORDER], 'G'),
        'CHECK_INCREMENT_GOLD_SIDDS_R2.txt': head + '-- 개발계 확인 (읽기 전용). Q01 3행, Q02·Q03 0행, Q04 3표 권한.\n\n' + '\n'.join('-- [%s] %s\n%s\n' % x for x in checks('SIDDS')),
        'CHECK_INCREMENT_GOLD_SIDDG_R2.txt': head + '-- 운영 확인 (읽기 전용). Q01 3행, Q02·Q03 0행, Q04 3표 권한.\n\n' + '\n'.join('-- [%s] %s\n%s\n' % x for x in checks('SIDDG')),
    }
    for name, text in files.items():
        if any(line.rstrip().endswith(';') for line in text.splitlines() if not line.startswith('--')):
            raise SystemExit('세미콜론: ' + name)
        (HERE / name).write_text(text, encoding='utf-8')
    (HERE / 'INCREMENT_GOLD_DESIGN_R2.json').write_text(json.dumps(DESIGN, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return files


# ---------------------------------------------------------------- 엑셀 (R20 표별 시트와 같은 모양)

class Styles:
    def __init__(self, ws):
        self.ws = ws

    def apply(self, cell, ref):
        src = self.ws[ref]
        for k in ('font', 'fill', 'border', 'alignment', 'number_format'):
            setattr(cell, k, copy(getattr(src, k)))


def put_row(ws, st, r, values, ref_row, merge_from=None, height=None, cols=8):
    for j in range(1, cols + 1):
        c = ws.cell(r, j, values[j - 1] if j - 1 < len(values) else None)
        st.apply(c, openpyxl.utils.get_column_letter(j) + str(ref_row))
    if merge_from:
        ws.merge_cells(start_row=r, start_column=merge_from, end_row=r, end_column=cols)
    if height:
        ws.row_dimensions[r].height = height


def table_sheet(wb, st, n, key):
    t, name = DESIGN[key], tname(key)
    ws = wb.create_sheet(SHEETS[key])
    for k, v in st.ws.column_dimensions.items():
        ws.column_dimensions[k].width = v.width
    by = {c['name']: c for c in t['columns']}
    pk = t['primary_key']
    r = 1
    put_row(ws, st, r, ['%02d / %02d   %s' % (n, len(ORDER), t['logical'])], 1, 1, 38)
    put_row(ws, st, 2, ['테이블 물리명', name], 2, 2, 26)
    put_row(ws, st, 3, ['테이블 정의', t['definition']], 3, 2, 60)
    put_row(ws, st, 4, ['컬럼 %d개  |  PK 인덱스 1개: 자동 생성  |  추가 인덱스 %d개: 직접 추가  |  파티션 미사용' % (len(t['columns']), len(t['indexes']))], 4, 1, 26)
    put_row(ws, st, 6, ['01  컬럼정보 · PK: Y=기본키 / NULL 허용: N=필수, Y=빈 값 허용'], 6, 1, 30)
    put_row(ws, st, 7, ['논리명', '물리명', 'PK', 'NULL 허용', 'PK 순서', '타입·길이', '기본값', '컬럼 정의'], 7, None, 34)
    r = 8
    for i, c in enumerate(t['columns']):
        put_row(ws, st, r, [c['logical'], c['name'], 'Y' if c['name'] in pk else 'N', 'N' if c['required'] else 'Y',
                            str(pk.index(c['name']) + 1) if c['name'] in pk else None, c['type'], c['default'], c['definition']],
                8 if i % 2 == 0 else 9, None, 61)
        r += 1
    r += 1
    put_row(ws, st, r, ['02  PK정보 · PK 지정 시 X0 자동 생성'], 14, 1, 30); r += 1
    put_row(ws, st, r, ['인덱스 물리명', 'X0_' + name], 15, 2, 26); r += 1
    put_row(ws, st, r, ['인덱스 논리명', t['logical'] + '기본키'], 16, 2, 26); r += 1
    put_row(ws, st, r, ['용도', '기본키 구성컬럼의 유일성과 필수값을 보장하여 행을 식별한다.'], 17, 2, 26); r += 1
    put_row(ws, st, r, [st.ws['A18'].value], 18, 1, 32); r += 1
    put_row(ws, st, r, ['컬럼 논리명', '컬럼 물리명', '순서', '정렬', 'PK용', 'UNIQUE', '인덱스 유형', '등록 방법'], 19, None, 34); r += 1
    for i, cname in enumerate(pk, 1):
        put_row(ws, st, r, [by[cname]['logical'], cname, str(i), 'ASC', 'Y', 'Y', 'B-TREE', 'PK 지정 → X0 자동 생성'], 20 if i % 2 else 21, None, 30); r += 1
    r += 1
    put_row(ws, st, r, ['03  추가 인덱스정보 · 직접 추가 %d개' % len(t['indexes'])], 24, 1, 30); r += 1
    for i, cols in enumerate(t['indexes'], 1):
        r += 1
        put_row(ws, st, r, ['추가 인덱스 %d · X%d · UNIQUE 체크 해제' % (i, i)], 26, 1, 30); r += 1
        put_row(ws, st, r, ['인덱스 물리명', 'X%d_%s' % (i, name)], 27, 2, 26); r += 1
        put_row(ws, st, r, ['인덱스 논리명', t['index_names'][i - 1]], 28, 2, 26); r += 1
        put_row(ws, st, r, ['용도', t['index_uses'][i - 1]], 29, 2, 26); r += 1
        put_row(ws, st, r, [st.ws['A30'].value], 30, 1, 32); r += 1
        put_row(ws, st, r, ['컬럼 논리명', '컬럼 물리명', '순서', '정렬', 'PK용', 'UNIQUE', '인덱스 유형', '등록 방법'], 31, None, 34); r += 1
        for j, cname in enumerate(cols, 1):
            put_row(ws, st, r, [by[cname]['logical'], cname, str(j), 'ASC', 'N', 'N', 'B-TREE', '＋ 추가 → 이름 자동 생성 / UNIQUE 해제'],
                    32 if j % 2 else 33, None, 30); r += 1
    if not t['indexes']:
        put_row(ws, st, r, ['추가 인덱스 없음 · PK 인덱스만 사용합니다.'], 18, 1, 26); r += 1
    r += 1
    put_row(ws, st, r, ['04  파티션 · 저장공간'], 37, 1, 30); r += 1
    for ref in (38, 39, 40, 41):
        put_row(ws, st, r, [st.ws['A%d' % ref].value, st.ws['B%d' % ref].value], ref, 2, 26); r += 1
    return ws


def list_sheet(wb, st, title, headers, rows, widths, note=None):
    ws = wb.create_sheet(title)
    r = 1
    if note:
        put_row(ws, st, 1, [note], 4, 1, 15 * (note.count('\n') + 2), cols=len(headers))
        r = 3
    for j, h in enumerate(headers, 1):
        c = ws.cell(r, j, h)
        st.apply(c, 'A7')
    for i, row in enumerate(rows):
        r += 1
        for j, v in enumerate(row, 1):
            c = ws.cell(r, j, v)
            st.apply(c, 'B8' if i % 2 == 0 else 'B9')
            c.alignment = Alignment(wrap_text=True, vertical='top')
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(3 if note else 2, 1)
    return ws


def words_of(name):
    parts = name.split('_')
    return parts, [KNOWN.get(p) or NEW.get(p) or '?' for p in parts], [p for p in parts if p in NEW]


def write_xlsx():
    tpl = openpyxl.load_workbook(TEMPLATE)
    st = Styles(tpl['02_문서구조'])
    wb = tpl
    keep = {'02_문서구조'}
    for name in list(wb.sheetnames):
        if name not in keep:
            del wb[name]
    guide = ('B003 증분 처리용 추가 Gold 메타 등록 R2 (2026-11-12, R1 대체). 기존 RAG Gold 13표(IDD_B003_LGL_DOC_VER 등)는 그대로 두고, '
             '증분 처리의 문서·판본·조문 변경 이력을 담을 3표를 새로 신청한다.\n'
             '형식은 RAG Gold 신청 때 쓴 R19/R20과 같다(표별 시트: 컬럼·PK·추가 인덱스·파티션). 개발계는 같은 이름으로 SIDDS, 운영은 SIDDG.\n'
             '증분 실행 기록(판단 실행·되돌리기용 옛 원문 파일)은 Gold가 아니라 Dataiku 관리 폴더(S3)에 둔다 — 06 시트.\n'
             '도메인·크기는 기존 RAG Gold 등록본에 쓰인 것(ID·값·내용·명·번호·여부·일시)만 썼다 — 07 시트. '
             '새 표준단어 신청 후보 13개(원천·활성·파일·공포·시행·상태·대체·비교·기준·이전·이후·조문·키)는 05 시트.')
    ws = wb.create_sheet('00_안내')
    ws.column_dimensions['A'].width = 150
    c = ws.cell(1, 1, guide)
    st.apply(c, 'A4')
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[1].height = 110
    for n, key in enumerate(ORDER, 1):
        table_sheet(wb, st, n, key)
    del wb['02_문서구조']
    list_sheet(wb, st, '04_테이블목록_Bizmeta',
               ['에이전트번호', '스키마', '테이블명', '테이블 논리명', '컬럼 수', 'PK', '데이터유형', '데이터출처', '데이터 가공 프로세스 설명', '생성시각', '예상 건수'],
               [['B003', 'SIDDG (개발계 SIDDS)', tname(k), DESIGN[k]['logical'], len(DESIGN[k]['columns']), ', '.join(DESIGN[k]['primary_key']),
                 DESIGN[k]['kind'], DESIGN[k]['source'], DESIGN[k]['process'], DESIGN[k]['when'], est]
                for k, est in zip(ORDER, ['문서 수(현재 약 2,121)', '문서 수 + 들어온 판본 수(하루 수 건)', '바뀐 조문 수(판본당 수~수십 건)'])],
               [12, 18, 30, 16, 8, 26, 11, 40, 60, 24, 26])
    rows = []
    for k in ORDER:
        for i, c in enumerate(DESIGN[k]['columns'], 1):
            parts, words, new = words_of(c['name'])
            dom = SUFFIX.get(parts[-1], '?')
            rows.append([tname(k), i, c['logical'], c['name'], dom, ' · '.join(words[:-1]),
                         ', '.join('%s=%s' % (p, w) for p, w in zip(parts, words)), ', '.join(new) or '없음(기존 단어)', c['korean']])
    list_sheet(wb, st, '05_표준용어_도메인', ['테이블명', '순번', '논리명(표준용어)', '물리명', '도메인', '수식어 단어', '약어=단어', '새 단어(신청 후보)', '한글포함'],
               rows, [26, 6, 18, 22, 8, 22, 46, 22, 9],
               note='기존 Gold(R20)에 쓴 약어는 그대로 재사용(규정·문서·변경=CHAN·버전=VER·조회·게시 …). 새 단어는 메타마이너 표준사전 조회 후 없으면 신청. '
                    '11-06 증분 설계의 CHG(변경)는 기존 Gold의 CHAN(변경번호)과 겹쳐 CHAN으로 맞췄다. 도메인은 물리명 끝 약어(ID·VALU·CTNT·NAME·NO·YN·ASTM)로 정해진다.')
    list_sheet(wb, st, '06_등록대상_구분', ['구분', '대상', '어디에', '사유'],
               [['1차 메타 등록 대상(신규)', tname(k), 'SIDDG (개발계 SIDDS)', DESIGN[k]['logical'] + ' — 증분의 문서·판본·조문 변경 이력(지식 성격, 오래 보존)'] for k in ORDER]
               + [['등록 대상 아님(기존 그대로)', 'IDD_B003_LGL_* RAG Gold 13표', 'SIDDG', '이미 등록·적재 완료. 증분은 이 표에 새 세대를 넣고 채널만 바꾼다'],
                  ['등록 대상 아님', '증분 실행 기록(판단 실행·대비표 HTML·되돌리기용 옛 원문 파일, 최근 3개)', 'Dataiku 관리 폴더(S3)', '실행 로그·원본 파일 성격 — Gold 아님'],
                  ['등록 대상 아님', 'SIDDA.LGL_PIPE_RESULT_A', 'SIDDA (기존)', 'Agent 층 중간 결과 — 이미 있는 표 재사용, 새로 만들지 않음'],
                  ['등록 대상 아님', 'SIDDS.TST_B003_LGL_* 13표', '개발계만', '증분 실험용 시험 복사본(앞서 보낸 자료)']],
               [24, 52, 22, 70])
    found = existing_domains()
    drows = []
    for dom, types in CATALOG.items():
        for t in types:
            mine = ['%s.%s' % (tname(k), c['name']) for k in ORDER for c in DESIGN[k]['columns']
                    if SUFFIX.get(c['name'].split('_')[-1]) == dom and c['type'] == t]
            drows.append([dom, t, ' · '.join(sorted(found[dom][t])), ' · '.join(mine) or '-'])
    list_sheet(wb, st, '07_도메인_선택지', ['도메인', '타입·크기', '기존 RAG Gold에서 쓴 컬럼(등록본)', '이번 증분 표에서 쓰는 컬럼'], drows, [10, 30, 70, 80],
               note='새 컬럼은 기존 RAG Gold 등록본(13표 60컬럼)에 실제로 쓰인 도메인과 크기 안에서만 골랐다. 코드·일자·순번·비율 도메인은 기존 기록에 없어 쓰지 않는다 '
                    '(구분코드→유형값, 공포·시행일자→일시, 비교순번→비교번호, 유사비율→비교부가정보내용 JSON).')
    list_sheet(wb, st, '08_DDL', ['번호', '내용', 'SQL (운영 SIDDG, 한 문장씩, ; 없음)'],
               [['C%02d' % i, d, s] for i, (d, s) in enumerate(ddl('SIDDG'), 1)], [7, 40, 160])
    for name in list(wb.defined_names):
        del wb.defined_names[name]
    wb.save(XLSX)


R20 = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1/법률에이전트_B003_골드테이블_메타등록_R20.xlsx'


def existing_domains():
    """기존 RAG Gold 최종 등록본(R20 17 시트)에서 도메인 → 크기 → 사용 컬럼."""
    out = {}
    for r in openpyxl.load_workbook(R20, read_only=True)['17_표준용어_도메인'].iter_rows(min_row=4, values_only=True):
        if r[0] and r[4] != '확인 필요':
            out.setdefault(r[4], {}).setdefault(r[8], set()).add(r[2])
    return out


def check_domains():
    found = existing_domains()
    if {d: sorted(v) for d, v in found.items()} != {d: sorted(v) for d, v in CATALOG.items()}:
        raise SystemExit('기존 Gold 도메인 기록과 CATALOG가 다름: %s' % {d: sorted(v) for d, v in found.items()})
    for key in ORDER:
        for c in DESIGN[key]['columns']:
            dom = SUFFIX.get(c['name'].split('_')[-1])
            if dom not in CATALOG or c['type'] not in CATALOG[dom]:
                raise SystemExit('기존 도메인·크기 밖: %s.%s %s %s' % (key, c['name'], dom, c['type']))
            if not c['logical'].endswith(dom):
                raise SystemExit('논리명이 도메인으로 끝나지 않음: ' + c['logical'])
            for p in c['name'].split('_'):
                if p not in KNOWN and p not in NEW:
                    raise SystemExit('약어 미정: ' + p)
    return found


def main():
    check_domains()
    write_sql()
    write_xlsx()
    print('ok', XLSX.name)


if __name__ == '__main__':
    main()
