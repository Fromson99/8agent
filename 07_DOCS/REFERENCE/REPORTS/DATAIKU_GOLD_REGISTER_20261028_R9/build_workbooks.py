"""R9 registration documents: explicit names and reusable business definitions."""
from pathlib import Path
from copy import copy
import hashlib
import json
import re
import zipfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'DATAIKU_GOLD_REGISTER_20261028_R8'
FONT = '/mnt/c/Windows/Fonts/malgun.ttf'
BOLD = '/mnt/c/Windows/Fonts/malgunbd.ttf'
MEASURE = ImageFont.truetype(FONT, 15)
HEADERS = ['순번', '논리명(한글)', '물리명(영문)', '도메인명', '수식어 단어',
           '데이터 타입', '길이 / 정밀도', 'PK 순서', '필수', '제약조건',
           '컬럼정의', '문자열 한글 포함 여부']
WIDTHS = [5, 27, 31, 10, 24, 21, 18, 8, 6, 53, 83, 16]

# One definition for each shared term. Table-specific usage is in the entity definition.
DEFINITIONS = {
    'MNFST_HASH_VALU': '데이터 구성 명세의 내용에 해시 함수를 적용하여 산출한 값이다. 데이터 구성 정보의 동일 여부와 변경 여부를 확인하는 데 사용한다.',
    'DOC_ID': '관리 범위 안에서 문서 한 건을 다른 문서와 구분하기 위해 부여한 식별자이다. 문서 관련 정보를 연결하고 해당 문서를 조회하는 기준으로 사용한다.',
    'DOC_NAME': '문서의 내용이나 목적을 나타내기 위해 부여한 이름 또는 제목이다. 문서 목록과 조회 결과에서 해당 문서를 알아볼 수 있도록 표시하는 데 사용한다.',
    'DOC_HASH_VALU': '원본 문서의 전체 내용에 해시 함수를 적용하여 산출한 값이다. 원본 문서의 동일 여부와 내용 변경 여부를 확인하는 데 사용한다.',
    'DOC_ADDN_IFMN_CTNT': '문서의 출처, 작성 주체, 분류 등 문서를 부가적으로 설명하는 내용이다. 문서의 기본 정보만으로 표현하기 어려운 상세 속성을 관리하는 데 사용한다.',
    'STRC_UNIT_ID': '문서를 구성하는 장, 절, 항목 등의 개별 구조 단위를 구분하기 위해 부여한 식별자이다. 문서 내부의 계층과 위치 정보를 연결하는 데 사용한다.',
    'UPPR_STRC_UNIT_ID': '문서의 계층 구조에서 해당 구조 단위의 바로 위 단계에 있는 구조 단위의 식별자이다. 구조 단위 간 상하위 관계를 관리하는 데 사용한다.',
    'STRC_UNIT_ADDN_IFMN_CTNT': '문서 구조 단위의 종류, 제목, 순서, 위치 등을 부가적으로 설명하는 내용이다. 구조 단위의 상세 속성을 관리하고 문서 구성을 파악하는 데 사용한다.',
    'BODY_SLC_ID': '문서 본문을 나누어 관리하는 개별 조각을 구분하기 위해 부여한 식별자이다. 필요한 본문 구간을 조회하고 관련 정보와 연결하는 데 사용한다.',
    'BODY_CTNT': '문서의 본문을 구성하는 실제 글의 내용이다. 문서 전체 또는 나누어 관리하는 본문 구간의 내용을 확인하고 조회하는 데 사용한다.',
    'BODY_SLC_ADDN_IFMN_CTNT': '본문 조각의 위치, 순서, 출처 등을 부가적으로 설명하는 내용이다. 개별 본문 조각의 상세 속성을 관리하고 문서 내 위치를 파악하는 데 사용한다.',
    'ADD_INFO_TEXT_OMIT_YN': '본문 조각의 부가정보에서 본문과 중복되는 내용을 생략했는지를 나타내는 값이다. Y는 생략, N은 미생략을 의미하며 값이 없으면 미지정 상태이다.',
    'DOC_POST_HASH_VALU': '원문 게시본의 구성 정보에 해시 함수를 적용하여 산출한 값이다. 함께 게시된 원문 자료의 구성을 구분하고 동일 여부를 확인하는 데 사용한다.',
    'DOC_POST_IFMN_CTNT': '원문 게시본에 포함된 자료의 구성, 범위, 버전 등 게시 관련 정보를 설명하는 내용이다. 함께 사용할 원문 자료를 확인하고 관리하는 데 사용한다.',
    'RGSN_AITM': '대상 정보가 시스템에 등록된 날짜와 시각이다. 등록 시점을 확인하고 정보의 생성 순서 및 관리 이력을 파악하는 데 사용한다.',
    'RFRN_POST_HASH_VALU': '조회용으로 게시한 자료의 구성 정보에 해시 함수를 적용하여 산출한 값이다. 조회에 함께 사용할 자료 구성을 구분하고 동일 여부를 확인하는 데 사용한다.',
    'RFRN_POST_IFMN_CTNT': '조회용 게시본에 포함된 자료의 구성, 범위, 버전 등 게시 관련 정보를 설명하는 내용이다. 조회에 사용할 자료의 구성을 확인하고 관리하는 데 사용한다.',
    'RFRN_DTA_TYPE_VALU': '조회자료의 성격이나 용도에 따라 구분한 유형을 나타내는 값이다. 자료를 유형별로 분류하고 유형에 맞는 조회 및 처리 기준을 적용하는 데 사용한다.',
    'RFRN_DTA_ID': '관리 범위 안에서 개별 조회자료를 다른 자료와 구분하기 위해 부여한 식별자이다. 해당 자료를 조회하고 관련 정보와 연결하는 기준으로 사용한다.',
    'RFRN_DTA_IDNF_CTNT': '조회자료를 찾거나 구별하는 기준으로 사용하는 이름, 용어, 식별값 등의 내용이다. 조회 조건과 자료를 대응시키고 필요한 자료를 검색하는 데 사용한다.',
    'BLNG_DTA_IDNF_CTNT': '조회자료가 소속되거나 관계의 출발점이 되는 자료를 구별하기 위한 내용이다. 자료의 소속을 확인하고 관계가 시작되는 대상을 조회하는 데 사용한다.',
    'TAGT_DTA_IDNF_CTNT': '조회자료와 연결된 관계의 대상 자료를 구별하기 위한 내용이다. 관계가 가리키는 자료를 확인하고 관련 자료를 조회하는 데 사용한다.',
    'SRCH_DATA_HASH_VALU': '조회자료의 유형, 식별정보 및 상세 내용에 해시 함수를 적용하여 산출한 값이다. 개별 조회자료의 동일 여부와 내용 변경 여부를 확인하는 데 사용한다.',
    'SRCH_DATA_CTNT': '조회자료의 주요 내용과 상세 속성을 담은 정보이다. 자료 유형에 따라 필요한 내용을 확인하고 자료 간 관계를 조회하는 데 사용한다.',
    'RFRN_CHNL_NAME': '조회에 사용할 자료를 선택하는 논리적 경로의 이름이다. 이용 목적이나 제공 범위에 따라 조회 경로를 구분하고 사용할 자료를 연결하는 데 사용한다.',
    'CHAN_NO': '대상 정보가 변경될 때 변경 순서를 구분하기 위해 증가시키는 번호이다. 변경 전후의 상태를 식별하고 동시에 발생한 수정 요청의 충돌을 확인하는 데 사용한다.',
    'ONT_PBLS_ID': '개념과 개념 간 관계를 정리한 온톨로지의 개별 게시본을 구분하기 위해 부여한 식별자이다. 게시된 지식을 조회하고 관련 정보와 연결하는 데 사용한다.',
    'CNCP_GROP_ID': '서로 관련된 개념을 하나의 관리 단위로 묶은 그룹을 구분하기 위해 부여한 식별자이다. 같은 그룹에 속한 개념과 관련 정보를 연결하는 데 사용한다.',
    'WORK_VER_NO': '작업 대상의 수정 단계에 따라 서로 다른 버전을 구분하기 위해 부여한 번호이다. 작업 내용의 변경 순서를 확인하고 특정 시점의 작업본을 식별하는 데 사용한다.',
    'POST_CTNT_HASH_VALU': '게시 대상의 전체 내용에 해시 함수를 적용하여 산출한 값이다. 게시 내용의 동일 여부와 게시 이후 내용의 변경 여부를 확인하는 데 사용한다.',
    'POST_KNWL_CTNT': '공유하거나 활용할 수 있도록 게시한 지식의 내용이다. 개념, 개념 간 관계, 적용 조건, 근거 등 지식을 이해하고 재사용하는 데 필요한 정보를 담는다.',
    'DOC_LCT_HASH_VALU': '문서 식별정보, 문서 판본 식별정보 및 구조 단위 식별정보의 조합에 해시 함수를 적용하여 산출한 값이다. 특정 판본의 문서 내 위치를 구분하는 데 사용한다.',
}

TABLE_DEFINITIONS = [
    '데이터 구성 버전별로 문서의 식별정보, 이름, 내용 확인값 및 부가정보를 관리하는 엔티티이다. 한 건은 특정 데이터 구성 버전에 포함된 문서 한 건을 의미한다.',
    '문서의 개별 구조 단위와 구조 단위 간 상하위 관계를 관리하는 엔티티이다. 한 건은 특정 데이터 구성 버전의 문서에 속한 구조 단위 한 건을 의미한다.',
    '문서 본문을 조각별로 나누어 내용과 위치 정보를 관리하는 엔티티이다. 한 건은 특정 데이터 구성 버전의 문서에 속한 본문 조각 한 건을 의미한다.',
    '함께 사용할 원문 자료를 게시본 단위로 묶어 구성 정보와 등록 시점을 관리하는 엔티티이다. 한 건은 원문 자료의 게시본 한 건을 의미한다.',
    '조회에 함께 사용할 자료의 구성을 게시본 단위로 관리하는 엔티티이다. 한 건은 조회자료의 범위와 구성을 정한 게시본 한 건을 의미한다.',
    '조회에 필요한 자료와 자료 간 검색 및 연결 관계를 관리하는 엔티티이다. 한 건은 특정 조회 게시본의 자료 유형에 속한 조회자료 한 건을 의미한다.',
    '조회 경로별로 사용할 게시본과 변경 순서를 관리하는 엔티티이다. 한 건은 조회 경로 한 건과 해당 경로에서 사용할 게시본의 연결을 의미한다.',
    '개념과 개념 간 관계를 정리한 지식을 게시본 단위로 관리하는 엔티티이다. 한 건은 개념그룹의 특정 작업 버전을 바탕으로 게시한 지식 한 건을 의미한다.',
    '개념그룹별로 현재 사용할 온톨로지 게시본과 선택 상태의 변경 순서를 관리하는 엔티티이다. 한 건은 개념그룹 한 건의 게시본 선택 상태를 의미한다.',
    '원문 문서의 특정 판본과 위치를 게시된 지식에 연결하는 엔티티이다. 한 건은 지식 게시본 한 건과 원문 위치 한 곳의 연결 관계를 의미한다.',
]
FORBIDDEN = re.compile(r'json|clob|varchar|sha-?256|manifest\.|ensure_ascii|NULL|SYSTIMESTAMP|Dataiku|GENOS|Oracle|SQLite|LLM|RAG|B0[35]|법령|법률|내규|조문|에이전트|프로젝트|생성기|직렬화|서버', re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value, pixels, font=MEASURE):
    lines = []
    for paragraph in str(value or '').split('\n'):
        line = ''
        for char in paragraph:
            if line and font.getlength(line + char) > pixels:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines


def style_table(sheet, header_row, last, widths):
    for col, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(col)].width = width
    for row in sheet.iter_rows(min_row=header_row, max_row=last, max_col=len(widths)):
        maxlines = 1
        for cell in row:
            is_header = cell.row == header_row
            cell.font = Font(name='맑은 고딕', size=10, bold=is_header or cell.column in (2, 3), color='FFFFFF' if is_header else '21374E')
            cell.fill = PatternFill('solid', fgColor='244B60' if is_header else 'F0F5F7' if cell.row % 2 == 0 else 'FFFFFF')
            cell.alignment = Alignment(vertical='center', wrap_text=True, horizontal='center' if cell.column == 1 else 'left')
            cell.border = Border(bottom=Side(style='thin', color='D8E0E8'), right=Side(style='hair', color='E4E9EF'))
            maxlines = max(maxlines, len(wrap(cell.value, widths[cell.column - 1] * 7 - 22)))
        sheet.row_dimensions[row[0].row].height = max(48 if row[0].row == header_row else 72, maxlines * 16 + 20)


def create_list(workbook, records, agent):
    sheet = workbook.create_sheet('00_테이블목록', 0)
    sheet.merge_cells('A1:D1')
    sheet['A1'] = '엔티티명 · 테이블명 목록'
    sheet['A1'].font = Font(name='맑은 고딕', size=20, bold=True, color='FFFFFF')
    sheet['A1'].fill = PatternFill('solid', fgColor='21374E')
    sheet.row_dimensions[1].height = 40
    sheet.merge_cells('A2:D2')
    sheet['A2'] = '엔티티명: 논리 모델의 한글명 | 테이블명: 물리 모델의 영문명'
    sheet.merge_cells('A3:D3')
    sheet['A3'] = '컬럼 논리명: 한글 용어명 | 컬럼 물리명: 영문 컬럼명'
    sheet.merge_cells('A4:D4')
    sheet['A4'] = f'{agent} · R9 · 명칭 대응 및 업무 정의 | 엔티티명을 누르면 상세 컬럼 시트로 이동합니다.'
    for r in (2, 3, 4):
        sheet.cell(r, 1).font = Font(name='맑은 고딕', size=11, color='455F72')
        sheet.cell(r, 1).alignment = Alignment(vertical='center', wrap_text=True)
        sheet.row_dimensions[r].height = 28
    headers = ['순번', '엔티티명(논리명·한글)', '테이블명(물리명·영문)', '엔티티 정의']
    for c, val in enumerate(headers, 1):
        sheet.cell(6, c, val)
    for idx, record in enumerate(records, 1):
        for c, val in enumerate((idx, record['entity'], record['table'], record['definition']), 1):
            sheet.cell(6 + idx, c, val)
        sheet.cell(6 + idx, 2).hyperlink = f"#'{record['sheet']}'!A1"
    style_table(sheet, 6, 16, [6, 30, 40, 105])
    table = Table(displayName=f'ENTITY_LIST_{agent}', ref='A6:D16')
    table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    sheet.add_table(table)
    sheet.freeze_panes = 'D7'
    sheet.sheet_view.zoomScale = 80
    sheet.print_area = 'A1:D16'
    sheet.print_title_rows = '1:6'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.oddFooter.left.text = f'{agent} · 골드 등록용 R9'


def build(agent):
    source = PREVIOUS / f'법률에이전트_{agent}_골드등록용_테이블별_R8.xlsx'
    before_hash = sha(source)
    workbook = load_workbook(source)
    records, changes = [], []
    for number, sheet in enumerate(workbook, 1):
        entity = sheet['A1'].value
        table = re.search(r'IDD_\w+', sheet['A2'].value)[0]
        records.append(dict(sheet=sheet.title, entity=entity, table=table, definition=TABLE_DEFINITIONS[number - 1]))
        data_rows = [row[0].row for row in sheet.iter_rows(min_row=7) if isinstance(row[0].value, int)]
        last = max(data_rows)
        for row in sheet:
            for cell in row:
                if cell.__class__.__name__ == 'MergedCell':
                    continue
                cell.comment = None
                if cell.row > last:
                    cell.value = None
        sheet['A1'] = '엔티티명(논리명·한글): ' + entity
        sheet['A2'] = '테이블명(물리명·영문): ' + table
        sheet['H2'] = agent + ' · 골드 등록용 R9'
        sheet['A3'] = '엔티티 정의: ' + TABLE_DEFINITIONS[number - 1]
        sheet['A4'] = '논리명=한글 용어명 · 물리명=영문 컬럼명 | 길이: BYTE 기준 · 필수: Y/N · 한글 포함: Y/N/해당 없음'
        sheet.row_dimensions[1].height = 40
        sheet.row_dimensions[2].height = 30
        sheet.row_dimensions[3].height = 40
        sheet.row_dimensions[4].height = 30
        for c, val in enumerate(HEADERS, 1):
            sheet.cell(6, c, val)
        for rownum in data_rows:
            physical = sheet.cell(rownum, 3).value
            old = sheet.cell(rownum, 11).value
            sheet.cell(rownum, 11, DEFINITIONS[physical])
            changes.append(dict(sheet=sheet.title, entity=entity, table=table, logical=sheet.cell(rownum, 2).value,
                                physical=physical, previous_definition=old, definition=DEFINITIONS[physical]))
        style_table(sheet, 6, last, WIDTHS)
        for existing_table in sheet.tables.values():
            for item, name in zip(existing_table.tableColumns, HEADERS):
                item.name = name
        sheet.print_area = f'A1:L{last}'
        sheet.oddFooter.left.text = f'{agent} · 골드 등록용 R9'
        sheet.oddFooter.right.text = '정의서 작성본'
    create_list(workbook, records, agent)
    workbook.active = 0
    for sheet in workbook:
        sheet.sheet_view.tabSelected = False
    workbook.worksheets[0].sheet_view.tabSelected = True
    workbook.properties.title = f'{agent} 테이블·엔티티·컬럼 정의서 R9'
    workbook.properties.description = '엔티티명과 테이블명, 컬럼 논리명과 물리명을 명시하고 공통 업무 의미를 중심으로 정의한 등록용 문서.'
    output = HERE / f'법률에이전트_{agent}_골드등록용_테이블별_R9.xlsx'
    workbook.save(output)
    assert sha(source) == before_hash
    return output, source, records, changes


def validate(output, source, records):
    workbook, previous = load_workbook(output), load_workbook(source)
    assert len(workbook.sheetnames) == 11
    assert workbook.sheetnames[1:] == previous.sheetnames
    count, constraints, common, seen, fk_count, check_count = 0, 0, {}, set(), 0, 0
    list_sheet = workbook['00_테이블목록']
    for index, prior in enumerate(previous, 1):
        sheet = workbook[prior.title]
        record = records[index - 1]
        assert sheet['A1'].value.endswith(record['entity'])
        assert sheet['A2'].value.endswith(record['table'])
        assert list_sheet.cell(index + 6, 2).value == record['entity']
        assert list_sheet.cell(index + 6, 3).value == record['table']
        assert not FORBIDDEN.search(record['definition'])
        assert len(record['entity'].encode()) <= 30 and len(record['table'].encode()) <= 30
        assert [sheet.cell(6, c).value for c in range(1, 13)] == HEADERS
        for old in prior.iter_rows(min_row=7, max_col=12):
            if not isinstance(old[0].value, int):
                continue
            row = old[0].row
            values = [sheet.cell(row, c).value for c in range(1, 13)]
            # Every structural field, name, type, length, null, constraint and flag is unchanged from R8.
            for c in list(range(1, 11)) + [12]:
                assert sheet.cell(row, c).value == prior.cell(row, c).value, (sheet.title, row, c)
                constraints += 1
            physical, definition = values[2], values[10]
            assert definition == DEFINITIONS[physical]
            assert definition != old[10].value
            assert not FORBIDDEN.search(definition), (physical, definition)
            assert 45 <= len(definition) <= 180
            assert len(values[1].encode()) <= 30 and len(physical.encode()) <= 30
            if physical in common:
                assert common[physical] == (values[1], definition)
            common[physical] = (values[1], definition)
            seen.add(physical)
            fk_count += int('FK →' in values[9])
            check_count += int('CHECK (' in values[9])
            count += 1
        for table in sheet.tables.values():
            assert [c.name for c in table.tableColumns] == HEADERS
    assert count == 49 and seen == set(DEFINITIONS) and len(common) == 32
    assert fk_count == 3 and check_count == 6
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                assert cell.comment is None
                assert cell.data_type != 'f'
                # The existing DB constraint is the sole remaining storage-format reference.
                if isinstance(cell.value, str) and re.search('json', cell.value, re.I):
                    assert cell.column == 10 and ' IS JSON)' in cell.value
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any(name.lower().endswith(('.js', '.jsx', '.mjs', '.cjs', '.bin')) for name in archive.namelist())
    return dict(status='PASS_DOCUMENT_CONSISTENCY',tables=10,columns=49,common_terms=32,
                entity_table_name_pairs=10,definitions_rewritten=49,entity_definitions_rewritten=10,
                structural_fields_unchanged=constraints,foreign_keys_preserved=fk_count,checks_preserved=check_count,
                shared_definitions_identical=True,implementation_terms_in_definitions=0,
                names_within30bytes=True,original_preserved=True,standard_approval_claimed=False,
                database_updated=False,native_excel_render=False)


def preview(output, sheetname):
    sheet = load_workbook(output)[sheetname]
    overview = sheetname == '00_테이블목록'
    cols = [1, 2, 3, 4] if overview else [2, 3, 6, 7, 11]
    widths = [65, 260, 330, 920] if overview else [225, 285, 160, 150, 780]
    last = 16 if overview else max(row[0].row for row in sheet.iter_rows(min_row=7) if isinstance(row[0].value, int))
    data = [[sheet.cell(row, col).value for col in cols] for row in range(6, last + 1)]
    regular = ImageFont.truetype(FONT, 18)
    bold = ImageFont.truetype(BOLD, 18)
    heights = [max(62, max(len(wrap(val, widths[i] - 24, bold if n == 0 else regular)) for i, val in enumerate(row)) * 27 + 24) for n, row in enumerate(data)]
    image = Image.new('RGB', (sum(widths) + 48, sum(heights) + 150), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((24, 20), 'R9 | ' + sheet['A1'].value, font=ImageFont.truetype(BOLD, 27), fill='#21374E')
    draw.text((24, 65), sheet['A2'].value, font=regular, fill='#455F72')
    y = 115
    for n, row in enumerate(data):
        x = 24
        for i, val in enumerate(row):
            draw.rectangle((x, y, x + widths[i], y + heights[n]), fill='#244B60' if n == 0 else '#F0F5F7' if n % 2 == 0 else 'white', outline='#D8E0E8')
            for line_no, line in enumerate(wrap(val, widths[i] - 24, bold if n == 0 else regular)):
                draw.text((x + 12, y + 12 + line_no * 27), line, font=bold if n == 0 else regular, fill='white' if n == 0 else '#21374E')
            x += widths[i]
        y += heights[n]
    image.save(HERE / (sheetname + '_검토미리보기.png'))


def main():
    results = []
    outputs = []
    for agent in ('B03', 'B05'):
        output, source, records, changes = build(agent)
        result = validate(output, source, records)
        results.append(dict(file=output.name,bytes=output.stat().st_size,sha256=sha(output),source_sha256=sha(source),validation=result))
        outputs.append(output)
        (HERE / f'CHANGE_AUDIT_{agent}.json').write_text(json.dumps(dict(tables=records,columns=changes),ensure_ascii=False,indent=2) + '\n')
    first, second = [load_workbook(path) for path in outputs]
    compared = 0
    for left, right in zip(first, second):
        for rows in zip(left, right):
            for a, b in zip(*rows):
                norm = lambda value: value.replace('B03', 'BXX').replace('B05', 'BXX') if isinstance(value, str) else value
                assert norm(a.value) == norm(b.value), (left.title, a.coordinate)
                compared += 1
    report = dict(files=results,agent_parity_cells=compared)
    (HERE / 'VALIDATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for name in ('00_테이블목록', '03_원문본문', '06_검색관계'):
        preview(outputs[0], name)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
