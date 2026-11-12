"""B003 골드 메타 등록 R20 — R19 최종 신청 엑셀(서식 그대로)에 현재 정의를 반영하고 등록 절차 시트를 더한다.

현재 정의 = 00_SYSTEM/ORACLE/gold_b003_r5.json (운영 적재기 R5·서버 매핑·11-04 메타 신청 작업함 화면과 같음).
R19 대비 바꾸는 것: 표·인덱스 이름 IDD_B03_→IDD_B003_, 컬럼명 5곳, 길이·타입 9곳(데이터 값 변경 없음).
더하는 시트: 안내, 활용테이블목록, Bizmeta, 메타등록대상, 표준용어·도메인, R19 대비 변경, 신청 화면 대조, DDL.
"""
from copy import copy
import json
from pathlib import Path
import re

import openpyxl
from openpyxl.styles import Alignment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R19 = ROOT / '07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R19/법률에이전트_B03_골드테이블_최종통합_R19.xlsx'
OUT = HERE / '법률에이전트_B003_골드테이블_메타등록_R20.xlsx'
GOLD = json.loads((ROOT / '00_SYSTEM/ORACLE/gold_b003_r5.json').read_text())['tables']
R14 = {t['suffix']: t for t in json.loads((ROOT / '07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_DOMAIN_CORRECTION_20261029_R14/MODEL.json').read_text())['tables']}
SHOT = json.loads((ROOT / '09_ARTIFACTS/AUDITS/20261106-gold-first-deployment-schema/registration_transcription.json').read_text())['tables']
DDL = (ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1/CREATE_GOLD_TABLES_SIDDG_R1.txt').read_text()
ORDER = ['DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST', 'SRCH_ROW', 'SRCH_CHNL',
         'ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC', 'VCTR_POST', 'VCTR_ITEM', 'VCTR_HEAD']
RENAME = {'RGSN_AITM': 'RGSN_ASTM', 'SRCH_DATA_HASH_VALU': 'RFRN_DTA_HASH_VALU',
          'SRCH_DATA_CTNT': 'RFRN_DTA_CTNT', 'CHAN_ORD': 'CHAN_NO'}
RETYPE = {('RGLT_DOC_ID', 'VARCHAR2(50 BYTE)'): 'VARCHAR2(100 BYTE)',
          ('BODY_UNIT_ID', 'VARCHAR2(50 BYTE)'): 'VARCHAR2(100 BYTE)',
          ('ADDN_IFMN_UN_APPN_YN', 'CHAR(1 BYTE)'): 'VARCHAR2(1 BYTE)'}
CHANGES = [  # (구분, 대상, R19, R20, 근거)
    ('표 이름', '13표 · 인덱스 X0~X4', 'IDD_B03_LGL_*', 'IDD_B003_LGL_*', '2026-11-04 사용자 "숫자는 003" — 메타 신청 작업함과 같은 이름'),
    ('길이', 'RGLT_DOC_ID (DOC_VER·DOC_UNIT·DOC_BLK·SRCH_ROW·ONTL_ANC·VCTR_ITEM)', 'VARCHAR2(50 BYTE)', 'VARCHAR2(100 BYTE)', '2026-11-04 규정문서ID 100 BYTE (ID 도메인 100 재사용)'),
    ('타입', 'DOC_BLK.ADDN_IFMN_UN_APPN_YN', 'CHAR(1 BYTE)', 'VARCHAR2(1 BYTE)', '2026-11-05 운영 등록 정의(R5) — 여부 도메인 VARCHAR2'),
    ('컬럼명', 'SRC_POST 등록일시', 'RGSN_AITM', 'RGSN_ASTM', '2026-11-04 사용자 정정(표준 약어)'),
    ('컬럼명', 'SRCH_ROW 조회자료해시값', 'SRCH_DATA_HASH_VALU', 'RFRN_DTA_HASH_VALU', '2026-11-04 사용자 정정 RFRN, 2026-11-05 운영 R5 DTA'),
    ('컬럼명', 'SRCH_ROW 조회자료내용', 'SRCH_DATA_CTNT', 'RFRN_DTA_CTNT', '같은 변경'),
    ('컬럼명', 'SRCH_CHNL·ONTL_HEAD·VCTR_HEAD 변경번호', 'CHAN_ORD', 'CHAN_NO', '2026-11-04 사용자 정정(번호 도메인)'),
    ('길이', 'VCTR_ITEM.BODY_UNIT_ID', 'VARCHAR2(50 BYTE)', 'VARCHAR2(100 BYTE)', '2026-11-05 운영 등록 화면 길이 100'),
]
ABBR_DOMAIN = {'VALU': '값', 'ID': 'ID', 'CTNT': '내용', 'NAME': '명', 'NO': '번호', 'YN': '여부', 'ASTM': '일시'}
EXTRA_WORDS = {'규정', '벡터', '게시', '구간', '본문', '단위', '임베딩', '상세', '미', '지정', '변경', '조회', '자료', '채널', '등록'}


def sheet_rows(ws):
    """컬럼표 행: 헤더 '논리명' 다음부터 빈 행 전까지."""
    rows = list(ws.iter_rows())
    out = []
    for i, r in enumerate(rows):
        if r[0].value == '논리명' and r[1].value == '물리명':
            for rr in rows[i + 1:]:
                if not rr[0].value or not rr[1].value or str(rr[0].value)[:2].isdigit():
                    break
                out.append(rr)
    return out


def update_r19(wb):
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    v = c.value.replace('IDD_B03_', 'IDD_B003_')
                    for a, b in RENAME.items():
                        v = re.sub(r'\b' + a + r'\b', b, v)
                    c.value = v
        for row in ws.iter_rows():
            if len(row) > 5 and (row[1].value, row[5].value) in RETYPE and row[0].value not in ('컬럼 논리명',):
                row[5].value = RETYPE[(row[1].value, row[5].value)]
    ws = wb['00_전체_한시트']
    ws['A1'] = 'B003 골드 메타 등록 R20 · 컬럼 / PK / 인덱스 최종 통합'


def style_from(ws, ref):
    c = ws[ref]
    return dict(font=copy(c.font), fill=copy(c.fill), border=copy(c.border), alignment=copy(c.alignment))


def add_sheet(wb, title, headers, rows, widths, head, body, note=None, index=None):
    ws = wb.create_sheet(title, index) if index is not None else wb.create_sheet(title)
    r = 1
    if note:
        ws.cell(1, 1, note).font = copy(head['font'])
        ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical='top')
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.row_dimensions[1].height = 15 * max(1, note.count('\n') + 1)
        r = 3
    header_row = r
    for j, h in enumerate(headers, 1):
        c = ws.cell(r, j, h)
        for k, v in head.items():
            setattr(c, k, copy(v))
    for row in rows:
        r += 1
        for j, v in enumerate(row, 1):
            c = ws.cell(r, j, v)
            for k, s in body.items():
                setattr(c, k, copy(s))
            c.alignment = Alignment(wrap_text=True, vertical='top')
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
    if rows:
        ws.freeze_panes = ws.cell(header_row + 1, 1)
    return ws


def segment(text, words):
    """논리명 앞부분을 표준단어로 나눈다(긴 단어 먼저). 못 나누면 None."""
    out, i = [], 0
    while i < len(text):
        for n in range(len(text) - i, 0, -1):
            if text[i:i + n] in words:
                out.append(text[i:i + n])
                i += n
                break
        else:
            return None
    return out


def standard_rows(logical):
    words = set(EXTRA_WORDS)
    for t in R14.values():
        for c in t['columns']:
            words |= {w.strip() for w in c['words'].split('·') if w.strip()}
    # R14에 붙여 쓴 항목(조회게시해시·벡터게시정보 등)은 단어가 아니다 — 다른 단어로 나뉘면 뺀다
    words = {w for w in words if not (lambda s: s and len(s) > 1)(segment(w, words - {w}))} - {'미지정'}
    rows, unresolved = [], []
    for key in ORDER:
        t = GOLD[key]
        r14 = {c['name']: c for c in R14[key]['columns']}
        for n, (lk, col) in enumerate(t['columns'].items(), 1):
            name = logical[key][n - 1]
            parts = col['name'].split('_')
            domain = ABBR_DOMAIN.get(parts[-1], '')
            stem = name[:-len(domain)] if domain and name.endswith(domain) else name
            seg = segment(stem, words)
            if domain and seg and len(seg) == len(parts) - 1:
                abbr = ', '.join('%s=%s' % (a, w) for a, w in zip(parts, seg + [domain]))
            else:
                abbr = '확인 필요'
                unresolved.append(col['name'])
            old = r14[lk]
            note = '' if old['logical'] == name else 'R14 논리명 %s → %s' % (old['logical'], name)
            if not domain:
                note = (note + ' / ' if note else '') + '도메인 접미어 없음(벡터 값) — 벡터 도메인 신청 여부 확인'
            rows.append([t['name'], n, name, col['name'], domain or '확인 필요', ' · '.join(seg) if seg else '확인 필요',
                         abbr, old['korean'], col['type'], note])
    return rows, unresolved


def main():
    wb = openpyxl.load_workbook(R19)
    update_r19(wb)
    base = wb['00_전체_한시트']
    head, body = style_from(base, 'A4'), style_from(base, 'B5')
    logical, defs = {}, {}
    for key, sheet in zip(ORDER, wb.sheetnames[1:14]):
        ws = wb[sheet]
        rows = sheet_rows(ws)
        logical[key] = [r[0].value for r in rows]
        defs[key] = (ws.title[3:], ws['B3'].value)
    names = {k: re.sub(r'^\d+ / 13\s+', '', wb[s]['A1'].value) for k, s in zip(ORDER, wb.sheetnames[1:14])}

    flow = 'S3 원문 ZIP → GENOS 구조화·색인 → SIDDA.LGL_PIPE_RESULT_A → Dataiku 03_LOAD'
    source = {k: flow for k in ORDER}
    source.update(VCTR_POST=flow + ' (임베딩: Dataiku 모델 연결)', VCTR_ITEM=flow + ' (임베딩: Dataiku 모델 연결)',
                  VCTR_HEAD='증분 반영(activate)·벡터 활성화 SQL', SRCH_CHNL='03_LOAD(세대 채널) · 증분 반영(main 교체)',
                  ONTL_POST='승인한 온톨로지 작업 JSON(Dataiku S3) → 게시', ONTL_HEAD='온톨로지 게시', ONTL_ANC='온톨로지 게시')
    when = {k: '원문 반영 시 03_LOAD (증분: 일 배치 예정, 시각 미정)' for k in ORDER}
    when.update(SRCH_CHNL='증분 반영 시', VCTR_HEAD='증분 반영 시', ONTL_POST='온톨로지 승인·게시 시',
                ONTL_HEAD='온톨로지 승인·게시 시', ONTL_ANC='온톨로지 승인·게시 시')

    guide = ('B003 골드 메타 등록 R20 (2026-11-12). 운영 메타 등록(메타데이터 거버넌스 > 신청관리 > 모델 신청)에 쓰는 정의서.\n'
             '기준: 00_SYSTEM/ORACLE/gold_b003_r5.json = 운영 적재기 R5 = 서버 매핑. 11-04 신청 작업함 13건(11-06 사진 27장)과 이름·순서·PK·타입·길이·NULL 같음(차이 2곳은 신청화면대조 시트).\n'
             'R19(10-30) 형식을 그대로 두고 내용만 현재 정의로 바꿨다. 데이터 값이 바뀌는 변경은 없다(이름·길이 확대·CHAR→VARCHAR2).\n'
             '시트: 00_전체_한시트·01~13 표별(컬럼/PK/인덱스/파티션) · 14 활용테이블목록 · 15 Bizmeta · 16 메타등록대상 · 17 표준용어·도메인 · 18 R19대비변경 · 19 신청화면대조 · 20 DDL\n'
             '노란 칸 없음: 이 파일은 채워 넣는 양식이 아니라 등록할 값 자체다. 소유자(스키마)는 운영 SIDDG, 개발계는 같은 이름으로 SIDDS.')
    add_sheet(wb, '안내', ['항목'], [], [160], head, body, note=guide, index=0).delete_rows(3)

    add_sheet(wb, '14_활용테이블목록', ['에이전트번호', '스키마', '테이블명', '골드레이어 후보 테이블', '비고'],
              [['B003', 'SIDDG', GOLD[k]['name'], 'Y (1차 메타 등록 대상)', names[k] + ' · 코드서빙(질문)이 읽음, B005 앱도 같은 표 조회'] for k in ORDER]
              + [['B003', 'SIDDA', 'LGL_PIPE_RESULT_A', 'N', '에이전트 레이어 — GENOS 처리 결과 조각, Gold 적재 뒤 삭제'],
                 ['B003', 'SIDDA', 'LGL_AGT_RUN_A · LGL_AGT_REC_A · LGL_AGT_BODY_A · LGL_EXEC_ST_A', 'N', '에이전트 레이어 — 질문 기록·상태'],
                 ['B003', 'SIDDS(개발계만)', 'TST_B003_LGL_* 13표', 'N', '개발계 증분 실험용 시험 복사본, 운영 없음']],
              [12, 16, 52, 22, 60], head, body)
    add_sheet(wb, '15_Bizmeta', ['No.', '에이전트번호', '스키마', '테이블명', '데이터논리명', '데이터출처', '데이터유형', '데이터 가공 프로세스 설명', '생성시각'],
              [[i, 'B003', 'SIDDG', GOLD[k]['name'], '%s — %s' % (names[k], defs[k][1]), source[k], R14[k]['kind'], R14[k]['process'], when[k]]
               for i, k in enumerate(ORDER, 1)],
              [6, 10, 9, 28, 60, 40, 12, 60, 28], head, body,
              note='데이터유형: 불변 게시본·판본별 자료=SNAPSHOT, 지금 선택(채널·현재 게시)=MASTER (R14 판정 그대로). 생성시각의 증분 배치 시각은 미정.')
    add_sheet(wb, '16_메타등록대상', ['구분', '스키마', '테이블', '사유'],
              [['1차 메타 등록 대상', 'SIDDG', GOLD[k]['name'], 'Gold — 원문·검색·온톨로지·벡터 게시 자료'] for k in ORDER]
              + [['등록 대상 아님', 'SIDDA', 'LGL_PIPE_RESULT_A, LGL_AGT_*_A, LGL_EXEC_ST_A', '에이전트 레이어(처리 중간 결과·질문 기록). 운영 별도 등록 필요 여부는 확인 필요'],
                 ['등록 대상 아님', 'SIDDS', 'TST_B003_LGL_*', '개발계 시험 복사본']],
              [20, 10, 48, 70], head, body)
    std, unresolved = standard_rows(logical)
    add_sheet(wb, '17_표준용어_도메인', ['테이블명', '순번', '논리명(표준용어)', '물리명', '도메인', '수식어 단어', '약어=단어', '한글포함', '타입·길이', '비고'],
              std, [26, 6, 22, 26, 9, 26, 46, 9, 22, 46], head, body,
              note='표준단어·도메인은 R14(10-29) 판정을 따르고, 그 뒤 바뀐 이름은 같은 단어 사전으로 다시 나눴다. 약어=단어는 물리명 조각과 단어를 순서대로 맞춘 것 — 메타마이너 표준사전 조회로 최종 확인.')
    add_sheet(wb, '18_R19대비변경', ['구분', '대상', 'R19', 'R20', '근거'], [list(c) for c in CHANGES], [10, 52, 22, 22, 60], head, body,
              note='R19(2026-10-30) → R20. 모두 이름 변경·길이 확대·CHAR→VARCHAR2라 기존 데이터 값은 그대로다. 개발계는 2026-11-10 같은 정의로 바꿨다(17/0/0).')
    shot = [['SRC_POST.RGSN_ASTM 타입', 'TIMESTAMP(6) WITH TIME ZONE, 기본값 SYSTIMESTAMP, NOT NULL', 'TIMESTAMP(자리수 공란), 기본값 없음, NOT NULL',
             '둘 다 동작(적재기가 실제 메타를 읽어 기본값이 없으면 SYSTIMESTAMP를 직접 넣음). 등록 정의를 하나로 정해 신청'],
            ['인덱스 11개 파티션', '비파티션(N)', 'partitioned=LOCAL 표시', '비파티션 표에는 LOCAL 인덱스를 만들 수 없음(ORA-14016). 파티션 정보 탭 확인 필요'],
            ['그 밖 13표 60컬럼·인덱스 11개', '이름·순서·PK·타입·길이·NULL', '같음', '11-06 사진 27장 대조']]
    add_sheet(wb, '19_신청화면대조', ['항목', 'R20', '11-04 신청 작업함 화면', '판단'], shot, [26, 44, 40, 70], head, body,
              note='메타데이터 거버넌스 신청관리 > 모델 신청 > 요청서작업함 13건(2026-11-04 10:42~12:08 작업, 11-06 사진). 09_ARTIFACTS/AUDITS/20261106-gold-first-deployment-schema')
    ddl_rows = []
    for blk in DDL.split('-- [')[1:]:
        label, sql = blk.split('\n', 1)
        ddl_rows.append([label.split(']')[0], label.split('] ', 1)[1], sql.strip()])
    add_sheet(wb, '20_DDL', ['번호', '내용', 'SQL (한 문장씩, ; 없음)'], ddl_rows, [7, 40, 160], head, body,
              note='DBA 생성 요청용. 소유자 SIDDG. 인덱스 이름 X0~X4_<표>는 적재기가 이 이름으로 찾으므로 바꾸지 않는다. 08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1/CREATE_GOLD_TABLES_SIDDG_R1.txt와 같다.')
    wb.save(OUT)
    print(OUT.name, 'unresolved', unresolved)


if __name__ == '__main__':
    main()
