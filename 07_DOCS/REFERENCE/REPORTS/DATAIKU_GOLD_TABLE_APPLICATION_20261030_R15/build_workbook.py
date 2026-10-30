"""Build copy-ready table applications from photo names and preserved R14 contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

ROOT = Path('/home/jin/8-AGENT')
OUT = Path(__file__).resolve().parent
BASE = ROOT / '07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_DOMAIN_CORRECTION_20261029_R14'
MAP = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_r14_photos.json'
PHOTOS = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-column-mapping/input-transcription.json'

# Independently read from the six retained source photographs, including logical names.
PHOTO_LOGICAL = {
    'MNFST_HASH_VALU': '명세해시값', 'RGLT_DOC_ID': '규정문서ID',
    'RGLT_DOC_NAME': '규정문서명', 'DOC_HASH_VALU': '문서해시값',
    'DOC_ADDN_IFMN_CTNT': '문서부가정보내용', 'STRC_UNIT_ID': '구조단위ID',
    'UPPR_STRC_UNIT_ID': '상위구조단위ID', 'STRC_UNIT_ADDN_IFMN_CTNT': '구조단위부가정보내용',
    'BODY_SLC_ID': '본문조각ID', 'BODY_CTNT': '본문내용',
    'BODY_SLC_ADDN_IFMN_CTNT': '본문조각부가정보내용',
    'ADDN_IFMN_UN_APPN_YN': '부가정보미지정여부',
    'BODY_POST_HASH_VALU': '본문게시해시값', 'BODY_POST_IFMN_CTNT': '본문게시정보내용',
    'RGSN_AITM': '등록일시', 'RFRN_POST_HASH_VALU': '조회게시해시값',
    'RFRN_POST_IFMN_CTNT': '조회게시정보내용', 'RFRN_DTA_TYPE_VALU': '조회자료유형값',
    'RFRN_DTA_ID': '조회자료ID', 'RFRN_DTA_IDNF_CTNT': '조회자료식별내용',
    'BLNG_DTA_IDNF_CTNT': '소속자료식별내용', 'TAGT_DTA_IDNF_CTNT': '대상자료식별내용',
    'SRCH_DATA_HASH_VALU': '조회자료해시값', 'SRCH_DATA_CTNT': '조회자료내용',
    'RFRN_CHNL_NAME': '조회채널명', 'CHAN_ORD': '변경번호',
    'ONTL_POST_ID': '온톨로지게시ID', 'CNCP_GROP_ID': '개념그룹ID',
    'WORK_VER_NO': '작업버전번호', 'POST_CTNT_HASH_VALU': '게시내용해시값',
    'POST_KNWL_CTNT': '게시지식내용', 'DOC_LCT_HASH_VALU': '문서위치해시값',
    'VCTR_POST_ID': '벡터게시ID', 'VCTR_POST_IFMN_CTNT': '벡터게시정보내용',
    'VCTR_SEG_ID': '벡터구간ID', 'BODY_UNIT_ID': '본문단위ID',
    'VCTR_DTLS_IFMN_CTNT': '벡터상세정보내용', 'EMBD_VCTR': '임베딩벡터',
}
INDEX_PURPOSE = {
    ('DOC_UNIT', 1): ('상하위구조조회', '같은 문서 판본에서 상위 구조 단위에 속한 하위 구조 단위를 조회한다.'),
    ('DOC_BLK', 1): ('구조별본문조회', '같은 문서 판본과 구조 단위에 속한 본문 조각을 조회한다.'),
    ('SRC_POST', 1): ('명세별게시조회', '같은 데이터 구성 명세로 생성된 본문 게시본을 조회한다.'),
    ('SRCH_ROW', 1): ('자료식별조회', '조회 게시본과 자료 유형 안에서 자료 식별내용에 해당하는 자료를 조회한다.'),
    ('SRCH_ROW', 2): ('소속자료조회', '조회 게시본과 자료 유형 안에서 소속자료를 기준으로 연결 관계를 조회한다.'),
    ('SRCH_ROW', 3): ('대상자료조회', '조회 게시본과 자료 유형 안에서 대상자료를 기준으로 연결 관계를 조회한다.'),
    ('SRCH_ROW', 4): ('문서별자료조회', '조회 게시본과 자료 유형 안에서 규정문서ID별 조회자료를 조회한다.'),
    ('ONTL_POST', 1): ('그룹버전조회', '개념그룹과 작업버전번호별 온톨로지 게시본을 조회한다.'),
    ('ONTL_HEAD', 1): ('게시별선택조회', '특정 온톨로지 게시본을 현재 선택한 개념그룹을 조회한다.'),
    ('ONTL_ANC', 1): ('원문연결조회', '특정 문서 위치에 연결된 온톨로지 게시본을 조회한다.'),
    ('VCTR_ITEM', 1): ('문서본문벡터조회', '벡터 게시본 안에서 규정문서와 본문 단위별 벡터 구간을 조회한다.'),
}
NAVY, TEAL, PALE, INK = '17365D', '147D92', 'EDF4FA', '23374D'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header(ws, row, labels):
    for col, value in enumerate(labels, 1):
        c = ws.cell(row, col, value)
        c.font = Font(name='맑은 고딕', size=10, bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=NAVY)
        c.alignment = Alignment(vertical='center', wrap_text=True)
    ws.row_dimensions[row].height = 32


def style(ws, widths, data_start=2):
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 85
    ws.freeze_panes = f'C{data_start}'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_properties.outlinePr.summaryRight = False
    ws.sheet_properties.tabColor = TEAL
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=data_start):
        max_lines = 1
        for c in row:
            c.font = Font(name='맑은 고딕', size=10, color=INK)
            c.alignment = Alignment(vertical='center', wrap_text=True)
            c.fill = PatternFill('solid', fgColor='FFFFFF' if c.row % 2 else PALE)
            c.border = Border(bottom=Side(style='hair', color='DCE4ED'))
            if isinstance(c.value, str):
                c.number_format = '@'
                visual = sum(2 if ord(ch) > 127 else 1 for ch in c.value)
                max_lines = max(max_lines, (visual // max(8, int(widths[c.column-1])-2)) + 1)
        ws.row_dimensions[row[0].row].height = max(30, min(112, 17 * max_lines + 10))
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_options.horizontalCentered = True
    ws.print_title_rows = f'1:{data_start-1}'
    ws.oddFooter.center.text = '사진 기준 컬럼 · 테이블 신청 R15'
    ws.oddFooter.right.text = '&P / &N'


def grid(wb, title, labels, rows, widths):
    ws = wb.create_sheet(title)
    header(ws, 1, labels)
    for row in rows:
        ws.append(row)
    style(ws, widths)
    t = Table(displayName=f'Data{len(wb.worksheets)}', ref=ws.dimensions)
    t.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    ws.add_table(t)
    return ws


def main(variant):
    physical = json.loads(MAP.read_text())
    baseline = json.loads((BASE / 'MODEL.json').read_text())
    transcription = json.loads(PHOTOS.read_text())
    photo_receipts = []
    for source in transcription['source_photos']:
        p = Path(source['path'])
        assert sha(p) == source['sha256']
        photo_receipts.append(source)
    old_tables = {t['suffix']: t for t in baseline['tables']}
    terms, tables = {}, []
    for key, mapped in physical['tables'].items():
        old = old_tables[key]
        old_cols = {c['name']: c for c in old['columns']}
        assert set(mapped['columns']) == set(old_cols)
        assert mapped['primary_key'] == [c['name'] for c in sorted(old['columns'], key=lambda c: c['pk']) if c['pk']]
        assert mapped['indexes'] == old['indexes']
        t = {'key': key, 'name': mapped['name'].replace('_B03_', f'_{variant}_'),
             'logical': old['logical'], 'definition': old['definition'], 'short': old['short'], 'columns': []}
        for pos, (legacy, c) in enumerate(mapped['columns'].items(), 1):
            prior = old_cols[legacy]
            assert (c['type'], c['required'], c['default']) == (prior['type'], prior['required'], prior['default'])
            terms.setdefault(c['name'], {'name': c['name'], 'logical': PHOTO_LOGICAL[c['name']],
                                        'type': c['type'], 'definition': prior['definition'], 'tables': []})
            term = terms[c['name']]
            assert term['type'] == c['type']
            term['tables'].append(t['name'])
            t['columns'].append({**c, 'legacy': legacy, 'logical': term['logical'],
                                 'definition': term['definition'], 'dtype': prior['dtype'], 'size': prior['size'],
                                 'pk': prior['pk'], 'position': pos})
        t['pk'] = [mapped['columns'][c]['name'] for c in mapped['primary_key']]
        t['indexes'] = [[mapped['columns'][c]['name'] for c in ix] for ix in mapped['indexes']]
        tables.append(t)
    assert len(tables) == 13 and sum(len(t['columns']) for t in tables) == 60
    assert set(terms) == set(PHOTO_LOGICAL) and len(terms) == 38
    assert sum(len(t['indexes']) for t in tables) == 11

    wb = Workbook()
    guide = wb.active
    guide.title = '00_사용안내'
    guide_rows = [
        ['법률에이전트 골드 테이블 신청', f'{variant} · 사진 기준 컬럼 · R15 · 2026-10-30'],
        ['신청 범위', '테이블 13개 / 컬럼 60행(고유 38개) / PK 13개 / 일반 인덱스 11개 / 파티션 미사용'],
        ['이전 파일 대체', '테이블 신청에는 기존 R14 대신 이 R15 파일을 사용한다. 사진의 최종 논리명·물리명·타입을 반영했다.'],
        ['빠른 복사', '01~08 시트: 1행은 제목, 2행부터 값이다. 테이블명으로 필터한 뒤 필요한 셀만 복사한다. 데이터 영역은 병합·수식 없이 값으로 작성했다.'],
        ['테이블별 입력', 'T01~T13 시트: 테이블 기본정보 → 컬럼정보 → 인덱스정보 → PK 구성컬럼 → 파티션정보 순서로 배치했다.'],
        ['컬럼 기준', '사용자가 신청 완료했다고 알려준 사진 6장의 논리명·물리명·타입을 기준으로 한다. 컬럼 정의는 사진 내용과 대조한 기존 정의를 사용한다.'],
        ['테이블·PK·인덱스 기준', '사진에 없는 테이블명·논리명·정의·PK·필수·기본값·일반 인덱스는 R14 모델/DDL을 유지했다. 인덱스 논리명과 용도 설명은 신청용으로 작성했다.'],
        ['인덱스 입력', '03_인덱스의 24행 = PK용 X0 13개 + 일반 X1~X4 11개. PK 등록 시 X0가 자동 생성되는 화면이면 X0를 일반 인덱스로 중복 등록하지 않는다.'],
        ['파티션 입력', '기존 DDL에 파티션 절이 없어 13개 모두 파티션여부=N(미사용)이다. 방식·키·경계·주기·파티션명은 해당 없음으로 비워 두었다.'],
        ['미제공 현장값', '현장 스키마(owner), 테이블스페이스, 기관 인포타입 코드 및 테이블 명명 승인 여부는 제공되지 않아 임의 입력하지 않았다. 현장 입력값으로 지정한다.'],
        ['타입 입력', '문자 길이는 BYTE다. NUMBER(30,0)·TIMESTAMP(6) WITH TIME ZONE·VECTOR(*,FLOAT32)는 전체 데이터타입 표기를 그대로 사용한다.'],
        ['명칭과 값 의미', '부가정보미지정여부는 사진 등록명을 사용하며 정의도 사진대로 유지했다: Y=본문 중복내용 생략, N=미생략, NULL=미지정.'],
        ['현재 문서의 범위', '테이블 신청 입력자료이다. 현장 DB 생성·인덱스 생성·성능 검증 결과를 뜻하지 않는다. 물리 FK와 벡터 전용 인덱스는 기존 DDL에 없어 추가하지 않았다.'],
        ['파일 선택', f'{variant} 명명안이다. B03/B05는 동일 모델의 대체 명명안이며 두 벌의 데이터 생성 지시가 아니다.'],
    ]
    for row in guide_rows: guide.append(row)
    style(guide, [31, 120], data_start=2)
    header(guide, 1, guide_rows[0])
    guide.freeze_panes = 'B2'
    guide.column_dimensions['C'].width = 36
    guide.column_dimensions['D'].width = 15

    table_rows, col_rows, index_rows, ix_col_rows, pk_rows, partition_rows = [], [], [], [], [], []
    table_index_rows = {}
    for t in tables:
        name, logic = t['name'], t['logical']
        pk_name = f'X0_{name}'
        table_rows.append([name, logic, t['definition'], len(t['columns']), pk_name, ', '.join(t['pk']), 'N', len(t['indexes'])])
        for c in t['columns']:
            col_rows.append([name, logic, c['position'], c['name'], c['logical'], c['definition'], c['type'],
                             c['dtype'], c['size'], 'N' if c['required'] else 'Y', 'Y' if c['pk'] else 'N',
                             c['pk'] or None, c['default']])
        local_indexes = []
        for number, keys in enumerate([t['pk']] + t['indexes']):
            ix_name = f'X{number}_{name}'
            label, definition = ('기본키', '기본키 구성컬럼의 유일성과 필수값을 보장하여 행을 식별한다.') if number == 0 else INDEX_PURPOSE[(t['key'], number)]
            registration = 'PK 등록 연계(자동 생성 시 중복 등록 제외)' if number == 0 else '일반 인덱스 등록'
            local = [ix_name, logic + label, 'B-TREE', 'Y' if number == 0 else 'N', 'Y' if number == 0 else 'N', ', '.join(keys), 'ASC', 'N', registration, definition]
            local_indexes.append(local)
            index_rows.append([name, logic] + local)
            for order, col in enumerate(keys, 1):
                ix_col_rows.append([name, ix_name, order, col, terms[col]['logical'], 'ASC', 'Y' if number == 0 else 'N'])
        table_index_rows[name] = local_indexes
        for order, col in enumerate(t['pk'], 1):
            pk_rows.append([name, logic, pk_name, order, col, terms[col]['logical'], 'N', pk_name])
        partition_rows.append([name, logic, 'N', '미사용', None, None, None, None, None, '기존 R14 DDL에 PARTITION BY 절 없음'])

    grid(wb, '01_테이블', ['테이블물리명','테이블논리명','테이블정의','컬럼수','PK명','PK구성컬럼(순서)','파티션여부','추가일반인덱스수'], table_rows, [33,24,86,10,37,68,12,19])
    grid(wb, '02_컬럼', ['테이블물리명','테이블논리명','컬럼순서','컬럼물리명','컬럼논리명','컬럼정의','전체데이터타입','데이터타입','길이_정밀도','NULL허용','PK여부','PK순서','기본값'], col_rows, [33,24,10,32,26,80,31,14,29,11,9,9,19])
    grid(wb, '03_인덱스', ['테이블물리명','테이블논리명','인덱스물리명','인덱스논리명','인덱스유형','유일여부','PK용여부','구성컬럼(순서)','정렬','파티션여부','등록방법','인덱스정의'], index_rows, [33,24,37,35,13,10,10,85,9,12,42,70])
    grid(wb, '04_인덱스컬럼', ['테이블물리명','인덱스물리명','컬럼순서','컬럼물리명','컬럼논리명','정렬','PK용여부'], ix_col_rows, [33,37,12,33,27,10,12])
    grid(wb, '05_PK', ['테이블물리명','테이블논리명','PK제약조건명','PK컬럼순서','컬럼물리명','컬럼논리명','NULL허용','PK인덱스명'], pk_rows, [33,24,37,13,33,27,12,37])
    grid(wb, '06_파티션', ['테이블물리명','테이블논리명','파티션여부','파티션정보','파티션방식','파티션키','파티션명','경계값','생성주기','작성근거'], partition_rows, [33,24,12,16,16,20,20,22,16,60])
    grid(wb, '07_등록용어38', ['컬럼물리명','컬럼논리명','전체데이터타입','컬럼정의','사용테이블수','사용테이블'],
         [[x['name'],x['logical'],x['type'],x['definition'],len(x['tables']),', '.join(x['tables'])] for x in terms.values()], [33,27,32,82,15,78])
    changes = []
    for old, new in transcription['renames_from_repository_r14'].items():
        prior = next(c for t in baseline['tables'] for c in t['columns'] if c['name'] == old)
        changes.append([old,new,prior['logical'],terms[new]['logical'],len(terms[new]['tables']), '사진 6장 최종 표기'])
    grid(wb, '08_사진명칭대조', ['이전물리명','사진물리명','이전논리명','사진논리명','반영컬럼행수','근거'], changes, [33,33,28,28,17,28])

    header(guide, 16, ['테이블별 입력 바로가기','테이블물리명','테이블논리명','컬럼수'])
    for i, t in enumerate(tables, 1):
        title = f'T{i:02d}_{t["short"]}'
        ws = wb.create_sheet(title)
        values = [['항목','복사할 값'], ['테이블물리명',t['name']], ['테이블논리명',t['logical']],
                  ['테이블정의',t['definition']], ['PK제약조건명',f'X0_{t["name"]}'],
                  ['PK구성컬럼(순서)',', '.join(t['pk'])], ['파티션여부','N']]
        for row in values: ws.append(row)
        col_header = ['컬럼순서','컬럼물리명','컬럼논리명','전체데이터타입','길이_정밀도','NULL허용','PK여부','PK순서','기본값','컬럼정의']
        header(ws, 9, col_header)
        for r, c in enumerate(t['columns'], 10):
            vals = [c['position'],c['name'],c['logical'],c['type'],c['size'],'N' if c['required'] else 'Y','Y' if c['pk'] else 'N',c['pk'] or None,c['default'],c['definition']]
            for n, value in enumerate(vals,1): ws.cell(r,n,value)
        index_start = 12 + len(t['columns'])
        ih = ['인덱스물리명','인덱스논리명','인덱스유형','유일여부','PK용여부','구성컬럼(순서)','정렬','파티션여부','등록방법','인덱스정의']
        header(ws,index_start,ih)
        for r, row in enumerate(table_index_rows[t['name']],index_start+1):
            for n, value in enumerate(row,1): ws.cell(r,n,value)
        pk_start = index_start + len(table_index_rows[t['name']]) + 3
        header(ws,pk_start,['PK제약조건명','PK컬럼순서','컬럼물리명','컬럼논리명','NULL허용'])
        for r, col in enumerate(t['pk'],pk_start+1):
            for n, value in enumerate([f'X0_{t["name"]}',r-pk_start,col,terms[col]['logical'],'N'],1): ws.cell(r,n,value)
        part_start = pk_start + len(t['pk']) + 3
        header(ws,part_start,['파티션여부','파티션정보','파티션방식','파티션키','파티션명','경계값','생성주기'])
        ws.cell(part_start+1,1,'N'); ws.cell(part_start+1,2,'미사용')
        style(ws,[38,37,28,32,29,62,10,12,42,82])
        for r, h in [(1,values[0]),(9,col_header),(index_start,ih),(pk_start,['PK제약조건명','PK컬럼순서','컬럼물리명','컬럼논리명','NULL허용']),(part_start,['파티션여부','파티션정보','파티션방식','파티션키','파티션명','경계값','생성주기'])]: header(ws,r,h)
        # Only the descriptive display cell is merged. All application grids remain unmerged.
        ws.merge_cells('B4:J4')
        ws.row_dimensions[4].height = 42
        ws.merge_cells('B6:J6')
        ws.row_dimensions[6].height = 30
        ws.freeze_panes = 'C10'
        ws.auto_filter.ref = f'A9:J{9+len(t["columns"])}'
        ws.print_title_rows = '1:9'
        guide.cell(16+i,1,title).hyperlink = f"#'{title}'!A1"
        guide.cell(16+i,1).font = Font(name='맑은 고딕',color='0563C1',underline='single',size=10)
        guide.cell(16+i,2,t['name']); guide.cell(16+i,3,t['logical']); guide.cell(16+i,4,len(t['columns']))
        guide.row_dimensions[16+i].height = 28
    guide.cell(31,1,'정본 근거')
    guide.cell(31,2,'사진 6장 / mapping_r14_photos.json / R14 MODEL.json / R14 GOLD_B03_DDL_REVIEW.sql')
    guide.cell(32,1,'매핑 SHA256')
    guide.cell(32,2,sha(MAP))
    guide.cell(33,1,'사진 확인')
    guide.cell(33,2,'사진 6장 원본을 다시 열어 논리명·물리명·타입과 대조했고 기존 기록의 SHA256과 일치했다.')
    guide.row_dimensions[33].height=35
    guide['B12'].comment = Comment('명칭은 사진 승인 표기를 보존하며 의미를 임의로 변경하지 않았습니다.', '작성 근거')
    wb.properties.creator = '8-AGENT'
    wb.properties.title = f'법률에이전트 {variant} 테이블 신청 R15'
    wb.properties.subject = '사진 최종 컬럼명 기반 테이블·컬럼·인덱스·PK·파티션 입력자료'
    filename = f'법률에이전트_{variant}_테이블신청_사진확정컬럼_R15.xlsx'
    target = OUT / filename
    wb.save(target)

    # Validate the serialized workbook against the source contracts, not just row counts.
    check = load_workbook(target, data_only=False)
    assert len(check.worksheets) == 22
    expected = {'01_테이블':table_rows, '02_컬럼':col_rows, '03_인덱스':index_rows,
                '04_인덱스컬럼':ix_col_rows, '05_PK':pk_rows, '06_파티션':partition_rows}
    for sheet, rows in expected.items():
        actual = list(check[sheet].values)[1:]
        assert actual == [tuple(row) for row in rows], sheet
        assert not check[sheet].merged_cells.ranges
    assert len(index_rows) == 24 and len({r[2] for r in pk_rows}) == 13
    for t in tables:
        for ix in [t['pk']] + t['indexes']:
            assert all(col in {c['name'] for c in t['columns']} for col in ix)
        assert all(c['required'] for c in t['columns'] if c['pk'])
    old_names = set(transcription['renames_from_repository_r14'])
    for ws in check:
        for row in ws:
            for c in row:
                assert c.data_type != 'f'
                if ws.title != '08_사진명칭대조' and isinstance(c.value,str):
                    assert not (set(re.findall(r'[A-Z][A-Z0-9_]*',c.value)) & old_names), (ws.title,c.coordinate,c.value)
    assert all(row[2] == 'N' and all(v is None for v in row[4:9]) for row in partition_rows)
    receipt = {'status':'PASS_WORKBOOK_SOURCE_AND_SERIALIZATION_CHECK', 'variant':variant,
               'file':str(target), 'bytes':target.stat().st_size, 'sha256':sha(target),
               'tables':13,'column_occurrences':60,'unique_columns':38,'pk_constraints':13,
               'pk_column_rows':len(pk_rows),'regular_indexes':11,'indexes_including_pk':24,
               'index_column_rows':len(ix_col_rows),'partitioned_tables':0,'sheets':len(check.worksheets),
               'photo_sources':photo_receipts,
               'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in [MAP,BASE/'MODEL.json',BASE/'GOLD_B03_DDL_REVIEW.sql',PHOTOS]],
               'checks':['60 physical names/types/nullability/defaults and PK/index order matched to mapping',
                         '38 photo logical names reread from original images', '13 table definitions preserved from R14',
                         '24 index references and 13 PK constraints resolve to renamed columns',
                         'no legacy physical names outside explicit comparison sheet',
                         'serialized XLSX reopened with exact grid-value comparison; no formulas',
                         'copy grids have no merged cells; partition N and unused fields empty'],
               'limits':['No native Excel rendering performed','No field DB creation or application-screen submission performed']}
    (OUT/f'VALIDATION_{variant}.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (OUT/'PHOTO_LOGICAL_NAMES.json').write_text(json.dumps(PHOTO_LOGICAL,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['photo_sources','sources','checks','limits']},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['B03','B05'], default='B03')
    main(parser.parse_args().variant)
