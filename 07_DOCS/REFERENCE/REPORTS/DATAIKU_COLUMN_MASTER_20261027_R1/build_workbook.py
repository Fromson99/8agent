"""Create the user's two-sheet column-master format from the shipped Oracle DDL.

Read-only against product code and databases. TOBE names are review proposals.
"""
from pathlib import Path
from copy import copy
import argparse
import hashlib
import json
import math
import re
import unicodedata
import zipfile

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1'
PACKAGE = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_stateless_20261027_r1/DATAIKU_COMPUTE_RECIPES_20261027_R1.zip'
TEMPLATE = HERE / 'reference_template.xlsx'
if not TEMPLATE.exists():
    attachment = next(Path('/tmp/codex-remote-attachments/01a17c40-75ca-7793-85d3-5c9be009037e').glob('*/*.xlsx'))
    TEMPLATE.write_bytes(attachment.read_bytes())
OUTNAME = '삼성증권_AI기반PI대표과제_법규_골드컬럼마스터_검토초안_20261027.xlsx'
ORDER = ['document', 'source_unit', 'block_payload', 'asset_part', 'source_release', 'query_release', 'query_row', 'query_active', 'query_state']

# name, business definition, source, process, registration classification
TABLES = {
 'document': ('법규문서판본내역', '법령·내규 문서의 이름과 원본 정보, 데이터 구축 세대를 관리한다. 같은 문서도 구축 세대가 다르면 별도 행으로 보관한다.', '없음 (법제처 등 외규 및 현업 업로드 내규 원본 파일을 구조화하여 적재)', '원본 파일을 구조화한 뒤 문서 식별자·문서명·원본 해시를 데이터 구축 세대와 함께 적재한다.', '1차 등록 후보'),
 'source_unit': ('법규문서구조내역', '문서를 편·장·절·조·항·호·목 등의 단위로 나누고 상위 단위와의 관계를 관리한다. 문서의 목차와 조문 위치를 찾는 데 쓴다.', '없음 (원본 파일의 구조화 결과). 문서 정보는 LGL_DOC_VER_S와 연결', '구조화한 문서에서 각 단위의 식별자와 상위 단위 식별자를 추출해 적재한다.', '1차 등록 후보'),
 'block_payload': ('법규문서본문내역', '답변의 근거로 읽고 인용하는 원문 본문을 조각별로 보관한다. 본문이 속한 문서·구조 단위와 원본 해시를 함께 관리한다.', '없음 (원본 파일의 구조화 결과). LGL_DOC_VER_S·LGL_DOC_UNIT_S와 연결', '구조화한 문서에서 본문을 분리하고, 문서·구조 단위·원본 해시·본문 중복 생략 표시를 함께 적재한다.', '1차 등록 후보'),
 'asset_part': ('법규파일분할보관내역', '색인·용어집 등 파일 자산을 조각으로 나눠 보관한다. 조각의 크기와 해시를 이용해 원래 파일을 정확히 복구할 수 있는지 확인한다.', '없음 (구축한 색인·용어집 등의 파일 자산을 분할하여 적재)', '파일을 최대 1MiB 조각으로 나누고 압축·Base64 변환한 뒤 원본 크기와 전체·조각 해시를 저장한다.', '골드 제외 검토'),
 'source_release': ('법규원문게시내역', '검증이 끝난 원문 데이터와 관련 파일을 하나의 게시본으로 묶어 관리한다. 어느 데이터 구축 세대와 파일을 함께 사용해야 하는지 확인하는 데 쓴다.', 'LGL_DOC_VER_S·LGL_DOC_UNIT_S·LGL_DOC_BLK_S·LGL_FILE_PART_S의 적재·검증 결과', '원문과 파일의 적재·재조회 검증이 끝나면 세대·파일 목록을 게시 명세로 묶어 저장한다.', '2차 추가 검토 후보'),
 'query_release': ('법규조회게시내역', '조회에 사용할 원문 게시본과 검색 자료의 종류·건수·해시를 관리한다. 한 번의 질문에서 같은 버전의 자료를 사용하도록 묶는다.', 'LGL_SRC_PBLS_S 및 LGL_SRCH_ROW_S의 생성·검증 결과', '조회 자료의 검증 결과와 원문 게시본을 하나의 명세로 묶고 게시 식별자를 계산해 저장한다.', '2차 추가 검토 후보'),
 'query_row': ('법규검색관계내역', '문서 구조·용어·정의·명시 참조와 검색에 필요한 자료를 종류별로 보관한다. 문서나 검색어를 기준으로 필요한 자료만 찾는 데 쓴다.', '구조화 원문과 구축한 목차·검색·용어집 자료. LGL_SRCH_PBLS_S와 게시 식별자로 연결', '원문·목차·검색·용어집 자료를 조회 종류별 행으로 만들고 검색키·관계키·내용 해시를 붙여 적재한다.', '1차 등록 후보'),
 'query_active': ('법규조회채널내역', '조회 채널별로 현재 사용할 조회 게시본을 관리한다. 변경 순번을 함께 확인해 동시에 다른 게시본으로 바꾸는 충돌을 막는다.', 'LGL_SRCH_PBLS_S의 완료 게시본과 채널 선택 요청', '완료 게시본을 확인한 뒤 기존 게시본·변경 순번이 예상과 같을 때만 채널 선택을 갱신한다.', '2차 추가 검토 후보'),
 'query_state': ('에이전트실행상태내역', '요청·대화 범위별 실행 상태와 변경 순번을 보관한다. 중간 상태를 다시 읽거나 동시 수정 여부를 확인하는 데 쓴다.', '연결된 에이전트 실행·재개 소비자의 상태 저장 요청', '상태 키별 내용을 JSON으로 저장하고 변경 순번과 해시를 함께 갱신한다. 현재 원문 배치는 이 표에 쓰지 않는다.', '골드 대상 제외'),
}

# Current physical column -> proposed name, logical name, concise definition.
COLS = {
 'DATA_VER_ID': ('DATA_VER_ID', '데이터구축세대ID', '같은 원문·목차·용어집 조합으로 구축한 데이터 묶음의 식별자. 법령의 개정번호나 시행일과는 다르다.'),
 'DOC_ID': ('DOC_ID', '법규문서ID', '데이터 구축 세대 안에서 문서를 구분하는 식별자. 문서·구조·본문을 연결하는 데 쓴다.'),
 'DOC_NM': ('DOC_NAME', '법규문서명', '법령 또는 내규 문서의 이름. 원문에 있는 이름을 보관한다.'),
 'SRC_DATA_HASH_VAL': ('SRC_DATA_HASH_VALU', '원본자료해시값', '본문이나 문서 정보가 참조하는 원본 자료의 해시값. 원본이 바뀌었는지 확인하는 데 쓴다.'),
 'DOC_JSON_CN': ('DOC_JSON_CTNT', '문서JSON내용', '문서의 판본·출처 등 부가 정보를 JSON으로 저장한 내용.'),
 'UNIT_ID': ('UNIT_ID', '문서구조단위ID', '문서 안의 조문·항·호 등 구조 단위를 구분하는 식별자. 데이터 구축 세대와 문서 식별자를 함께 사용한다.'),
 'PRNT_UNIT_ID': ('PRNT_UNIT_ID', '상위구조단위ID', '같은 문서에서 바로 위에 있는 구조 단위의 식별자. 상위 단위가 없으면 NULL이다.'),
 'UNIT_JSON_CN': ('UNIT_JSON_CTNT', '구조단위JSON내용', '조문 번호·제목·위치 등 구조 단위의 부가 정보를 JSON으로 저장한 내용.'),
 'BLK_ID': ('BLK_ID', '원문본문조각ID', '문서 안에서 원문 본문 조각을 구분하는 식별자. 데이터 구축 세대와 문서 식별자를 함께 사용한다.'),
 'BLK_TXT_CN': ('BLK_TXT_CTNT', '원문본문내용', '답변의 근거로 읽고 인용하는 원문 본문. 생성한 요약이나 답변이 아니다.'),
 'BLK_JSON_CN': ('BLK_JSON_CTNT', '본문조각JSON내용', '본문 조각의 위치·출처 등 부가 정보를 JSON으로 저장한 내용. 중복 본문을 생략한 경우 별도 본문 열과 함께 읽는다.'),
 'JSON_TXT_OMIT_YN': ('JSON_TXT_OMIT_YN', 'JSON본문생략여부', 'JSON 안의 중복 본문을 생략했는지 표시한다. 현재 1은 생략, 0은 미생략이며 NULL도 보존한다. 원문 본문 자체가 없다는 뜻은 아니다.'),
 'FILE_HASH_VAL': ('FILE_HASH_VALU', '파일해시값', '조각으로 나누기 전 전체 파일의 SHA-256 해시값. 여러 조각을 같은 파일로 묶는 데 쓴다.'),
 'PART_SEQ_NO': ('PART_SEQ_NO', '파일분할순번', '파일을 순서대로 나눈 조각의 순번. 0부터 시작한다.'),
 'ORG_BYTE_CNT': ('ORGL_BYTE_CONT', '원본조각바이트수', '압축하기 전 원본 조각의 크기. 단위는 바이트이며 한 조각은 최대 1,048,576바이트다.'),
 'PART_HASH_VAL': ('PART_HASH_VALU', '파일조각해시값', '압축하기 전 원본 조각의 SHA-256 해시값. 조각을 복구한 뒤 내용이 같은지 확인하는 데 쓴다.'),
 'PART_B64_CN': ('PART_B64_CTNT', '파일조각인코딩내용', '파일 조각을 압축한 뒤 Base64 문자열로 바꾼 내용. 사람이 읽는 문서 본문이 아니다.'),
 'SRC_PBLS_ID': ('SRC_PBLS_ID', '원문게시ID', '검증이 끝난 원문·파일 묶음의 게시본을 구분하는 식별자.'),
 'PBLS_JSON_CN': ('PBLS_JSON_CTNT', '원문게시JSON내용', '원문 게시본에 포함된 데이터 구축 세대·파일 목록·검색 설정을 JSON으로 저장한 내용.'),
 'REG_DTM': ('REG_DATE_TIME', '원문게시등록일시', '원문 게시 행이 DB에 등록된 일시. 현재 시간대 정보도 함께 저장한다.'),
 'SRCH_PBLS_ID': ('SRCH_PBLS_ID', '조회게시ID', '조회에 사용할 원문과 검색 자료 묶음의 식별자. 조회 행과 채널을 같은 게시본에 연결한다.'),
 'MNFST_JSON_CN': ('MNFST_JSON_CTNT', '조회명세JSON내용', '조회 게시본의 원문 세대·자료 종류·건수·해시를 JSON으로 저장한 내용.'),
 'ROW_KIND_CD': ('ROW_KIND_VALU', '조회자료유형값', '조회 행이 문서 구조·용어·정의·참조 등 어느 종류인지 구분하는 값. 게시 명세에 선언된 종류를 사용한다.'),
 'ROW_ID': ('ROW_ID', '조회자료행ID', '같은 조회 종류 안에서 행을 구분하는 식별자. 조회 게시 식별자·자료 유형과 함께 고유해진다.'),
 'SRCH_KEY_ID': ('SRCH_KEY_VALU', '검색키값', '용어의 표기나 식별자로 자료를 찾는 검색키. 긴 값은 호출 경로에 따라 해시로 바뀌며 전체 값은 JSON에 보관한다.'),
 'OWNR_REF_ID': ('OWNR_REF_ID', '소속참조ID', '조회 자료가 속한 구조 단위·정의·참조 등을 찾는 식별자. DB 스키마나 사용자 계정을 뜻하지 않는다.'),
 'TGT_REF_ID': ('TGT_REF_ID', '대상참조ID', '관계의 대상이나 상위 단위를 찾는 식별자. 자료 유형에 따라 가리키는 대상이 다르다.'),
 'ROW_HASH_VAL': ('ROW_HASH_VALU', '조회자료행해시값', '조회 행의 종류·식별자·문서·검색키·JSON 내용을 함께 계산한 해시값. JSON 본문만의 해시와 다르다.'),
 'ROW_JSON_CN': ('ROW_JSON_CTNT', '조회자료JSON내용', '원문 좌표·용어·정의 등 조회 자료의 내용을 JSON으로 저장한 값. 자료 유형별로 내부 항목이 다르다.'),
 'CHNL_NM': ('CHNL_NAME', '조회채널명', '현재 사용할 조회 게시본을 선택하는 채널의 이름.'),
 'CHG_SEQ_NO': ('CHG_SEQ_NO', '변경순번', '채널이나 실행 상태를 바꿀 때마다 증가하는 순번. 1부터 시작하며 동시 수정 충돌을 확인하는 데 쓴다.'),
 'SCOPE_HASH_VAL': ('SCOPE_HASH_VALU', '상태범위해시값', '실행 상태가 속한 요청·대화 범위를 구분하는 해시값. 이 값만으로 접근권한이 부여되지는 않는다.'),
 'ST_KEY_ID': ('STAS_KEY_ID', '실행상태키ID', '같은 요청·대화 범위 안에서 개별 상태를 찾는 식별자.'),
 'ST_HASH_VAL': ('STAS_HASH_VALU', '실행상태해시값', '상태의 범위·키·변경 순번·내용을 함께 계산한 해시값. 상태가 바뀌었는지 확인하는 데 쓴다.'),
 'ST_JSON_CN': ('STAS_JSON_CTNT', '실행상태JSON내용', '실행 중 저장한 작은 상태 객체의 JSON 내용. 전체 원문이나 승인된 법률 지식을 보관하는 열이 아니다.'),
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def descfield(desc, prefix):
    return next((s.split(':', 1)[1].strip() for s in desc.splitlines() if s.startswith(prefix + ':')), '')

def owner(mapping, key):
    return mapping['profiles']['dev_silver']['owner_by_role'][mapping['tables'][key]['role']]

def constraints(mapping, key, old):
    t = mapping['tables'][key]
    c = t['columns'][old]
    parts = ['NULL 허용' if c['nullable'] else 'NOT NULL']
    if old in t['pk']:
        parts.append('PK(' + ', '.join(t['columns'][x]['name'] for x in t['pk']) + ')')
    for check in t['checks']:
        if old not in check['columns']:
            continue
        if check['kind'] == 'is_json':
            parts.append('CHECK(' + c['name'] + ' IS JSON)')
        elif check['kind'] == 'revision':
            parts.append('CHECK(' + c['name'] + ' >= 1)')
        else:
            parts.append('CHECK(PART_SEQ_NO >= 0 AND ORG_BYTE_CNT > 0 AND ORG_BYTE_CNT <= 1048576)')
    for fk in t['foreign_keys']:
        if old in fk['columns']:
            target = mapping['tables'][fk['target']]
            parts.append('FK(' + owner(mapping, fk['target']) + '.' + target['name'] + '.' + target['columns'][fk['target_columns'][0]]['name'] + ')')
    if c['default']:
        parts.append('DEFAULT ' + c['default'])
    return '\n'.join(parts)

def review(c):
    n = c['name']
    new = COLS[n][0]
    check = '표준단어·용어·도메인·인포타입 대조 필요.'
    change = ('작성 반영 — 명칭 후보 ' + n + ' → ' + new + '. DB 미반영.' if new != n else '현행 유지안 — 표준 승인 미확인.')
    typ = c['type']
    if n == 'JSON_TXT_OMIT_YN':
        check = '첨부 예시의 여부형은 CHAR(1). 현재는 NUMBER(1), 0·1·NULL이며 DDL 값 CHECK 없음.'
        change = '미반영 — CHAR(1) 후보. 1→Y·0→N·NULL 유지, 입출력 변환과 CHECK(Y·N) 설계 후 적용.'
        typ = 'CHAR(1)'
    elif n == 'REG_DTM':
        check = '첨부는 TIMESTAMP(6). 현재 시간대 포함이므로 표준 타입·기준 시간대·변환 규칙 확인 필요.'
        change = '일부 작성 반영 — 일시명 후보. 타입은 시간대 보존을 위해 현행 유지안; DB 미반영.'
    elif n == 'DOC_ID':
        check = '첨부도 문서ID의 기존 용어·타입 불일치를 지적함. 우리 값은 UUID 고정이 아니며 512 BYTE를 사용.'
        change = '미반영 — 법규문서ID 후보와 등록 용어 대조. VARCHAR2(36) 등으로 임의 축소하지 않음.'
    elif n == 'DOC_NM':
        check = '문서명은 현재 CLOB. 첨부의 NAME 약어를 후보로 적용하되 표준 인포타입·최대 길이 확인 필요.'
    elif n == 'ROW_KIND_CD':
        check = '현재 문자열 종류값. 전사 승인 코드인지 미확인하여 유형값 후보로 작성; 실제 값 변경 없음.'
    elif n == 'SRCH_KEY_ID':
        check = '식별자 외 용어 표기도 포함하므로 검색키값 후보. 한글·BYTE 길이 및 긴 키 처리 확인 필요.'
    elif n.endswith('_ID'):
        check += ' ID 예외와 기존 용어의 길이·타입 일치 여부 확인.'
    elif 'HASH' in n:
        check += ' HASH 단어 등록 및 값(VALU) 도메인 확인.'
    elif typ == 'CLOB':
        check += ' 내용(CTNT) 도메인과 CLOB 인포타입 확인.'
    return typ, check, change

def korean(c):
    # Actual stored representation. JSON generated by json_body uses ASCII escapes.
    n = c['name']
    raw = {'DOC_ID', 'UNIT_ID', 'PRNT_UNIT_ID', 'BLK_ID', 'DOC_NM', 'DOC_JSON_CN', 'UNIT_JSON_CN', 'BLK_TXT_CN', 'BLK_JSON_CN', 'SRCH_KEY_ID', 'OWNR_REF_ID', 'TGT_REF_ID'}
    return 'Y' if n in raw else 'N'

def text_width(value):
    return sum(2 if unicodedata.east_asian_width(x) in ('W', 'F') else 1 for x in str(value))

def format_sheet(ws, widths, header_style=None):
    ws.freeze_panes = 'D2' if ws.title in ('테이블', '컬럼') else 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.zoomScale = 85
    ws.sheet_view.showGridLines = False
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for c in ws[1]:
        if header_style is None:
            c.fill = PatternFill('solid', fgColor='222222')
            c.font = Font(name='맑은 고딕', size=11, bold=True, color='FFFFFF')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[1].height = 42
    edge = Side(style='thin', color='D9D9D9')
    for row in ws.iter_rows(min_row=2):
        maxlines = 1
        for c in row:
            c.font = Font(name='맑은 고딕', size=11, color='222222')
            c.alignment = Alignment(vertical='center', wrap_text=True)
            c.border = Border(left=edge, right=edge, top=edge, bottom=edge)
            width = widths[c.column - 1] - 2
            lines = sum(max(1, math.ceil(text_width(p) / max(1, width))) for p in str(c.value or '').split('\n'))
            maxlines = max(maxlines, lines)
        ws.row_dimensions[row[0].row].height = min(240, max(61, maxlines * 18 + 18))
    ws.print_options.horizontalCentered = True
    ws.print_title_rows = '1:1'
    ws.print_area = ws.dimensions
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = '법규 테이블·컬럼 마스터 | 검토 초안 | 2026-10-27'
    ws.oddFooter.right.text = '&P / &N'

def build(agent):
    mapping = yaml.safe_load((BASE / 'physical_mapping.yaml').read_text())
    w = openpyxl.load_workbook(TEMPLATE)
    template_headers = {s.title: [c.value for c in s[1]] for s in w}
    template_styles = {s.title: [copy(c._style) for c in s[1]] for s in w}
    for s in w:
        s.delete_rows(2, s.max_row)
    t_sheet, c_sheet = w['테이블'], w['컬럼']
    unknown_agent = agent == '확인 필요'
    prefix = 'IDD_XXX_' if unknown_agent else 'IDD_' + agent + '_'
    candidates = {k: prefix + mapping['tables'][k]['name'][:-2] for k in ORDER}
    constraints_count = {'pk': 0, 'check': 0, 'fk': 0, 'index': 0}
    for k in ORDER:
        t = mapping['tables'][k]
        name, definition, source, process, status = TABLES[k]
        isgold = t['role'] in ('gold_knowledge', 'gold_support')
        tb = candidates[k] if isgold else t['name']
        table_change = '미반영 — IDD_과제번호_테이블명 후보; 개발계 SIDDS·_S는 유지. 운영 명명·스키마 승인 필요.' if isgold else ('별도 관리 — 복구용 파일 보관 표. 골드 제외 여부·보관 위치 검토; 현행명 유지안.' if k == 'asset_part' else '골드 대상 제외 — 에이전트 실행 상태이므로 SIDDA·_A 유지. 골드 명명 규칙을 일괄 적용하지 않음.')
        if isgold and unknown_agent:
            table_change += ' XXX는 미확정 과제번호 자리표시자.'
        t_sheet.append([agent, owner(mapping, k), t['name'], tb, name, definition, source, table_change])
        tr = t_sheet.max_row
        t_sheet.cell(tr, 3).comment = Comment('현재 = 2026-10-27 전달 SQL과 실제 패키지 매핑의 정의. 현장 DB 메타데이터 조회 결과가 아닙니다.\n근거: ' + str((BASE / '01_CREATE_TABLES.sql').relative_to(ROOT)), 'Codex')
        t_sheet.cell(tr, 5).comment = Comment('업무 설명을 위한 한글명 후보. 표준용어 승인 미확인.\n현재 COMMENT 논리명: ' + descfield(t['description'], '논리명(미승인 후보)'), 'Codex')
        t_sheet.cell(tr, 6).comment = Comment(t['description'], '기존 SQL 설명')
        for typ, key in [('pk', 'pk'), ('check', 'checks'), ('fk', 'foreign_keys'), ('index', 'indexes')]:
            constraints_count[typ] += (1 if typ == 'pk' else len(t[key]))
        for seq, (old, c) in enumerate(t['columns'].items(), 1):
            proposed, logical, definition = COLS[c['name']]
            typ, check, change = review(c)
            if k == 'query_row' and c['name'] == 'DOC_ID':
                definition = '조회 자료가 속한 문서의 식별자. 문서별 조회 권한을 제한하는 데 쓰며, 공통 용어집처럼 문서에 속하지 않는 행은 NULL일 수 있다.'
            c_sheet.append([agent, owner(mapping, k), t['name'], c['name'], seq, c['type'], proposed, logical, typ, check, change, constraints(mapping, k, old), 'Y' if old in t['pk'] else None, definition, korean(c)])
            cr = c_sheet.max_row
            c_sheet.cell(cr, 4).comment = Comment('현재 정의의 논리 키: ' + old + '\n' + str((BASE / 'physical_mapping.yaml').relative_to(ROOT)) + '\n' + c['description'], '정의 근거')
            c_sheet.cell(cr, 8).comment = Comment('이번 검토안의 한글명이며 승인 표준용어가 아닙니다. 현재 COMMENT 논리명: ' + descfield(c['description'], '논리명(미승인 후보)'), 'Codex')
            c_sheet.cell(cr, 12).comment = Comment('현재 DDL 제약만 표시합니다. 복합 PK는 한 묶음입니다. 기재하지 않은 FK·CHECK·DEFAULT는 추가하지 않았습니다.\n기존 코드 허용값: ' + descfield(c['description'], '허용값·코드·범위'), '제약 해석')
            c_sheet.cell(cr, 15).comment = Comment('Y: 한글이 저장될 수 있어 한글 길이 검토 필요. 실제 전체 값 실측 결과는 아닙니다.\nN: 현재 생성 계약상 숫자·영문·해시·Base64·ASCII 직렬화입니다. 게시/조회/상태 JSON의 한글은 \\u 이스케이프로 저장하며 해석한 내용에는 한글이 있을 수 있습니다.', '한글 포함 기준')

    summary = w.create_sheet('검토요약')
    summary.append(['항목', '판정', '현재 확인한 내용', '첨부와 맞추려면 / 작성 원칙'])
    summary_rows = [
      ('종합', '부분 부합', '전달 SQL의 9테이블·46컬럼을 작성했다. 첨부의 작성 양식은 반영했지만 표준 명명·타입 승인은 남아 있다.', '이 파일은 검토 초안이다. TOBE와 반영내용은 문서 작성 상태이며 DB 변경 완료를 뜻하지 않는다.'),
      ('비교 기준', '확인', '최신 계산 전용 전달 ZIP의 DDL·매핑이 10월27일 개발계 SQL·매핑과 바이트 단위로 같다.', '기존 10월23일 SIDDA·무접미사 초안 대신 SIDDS·_S / SIDDA·_A를 현재 정의로 사용했다.'),
      ('에이전트번호', '확인 필요' if unknown_agent else '사용자 확인', agent, '첨부 파일명은 A02, 시트 본문은 B02다. 우리 과제번호로 복사하지 않았다. XXX는 미확정 번호의 자리표시자다.' if unknown_agent else '사용자가 확인한 과제번호를 모든 해당 행과 IDD 접두 후보에 반영했다.'),
      ('현재 스키마', '개발계 반영 정의', '실버 SIDDS 8개·41컬럼, 에이전트 SIDDA 1개·5컬럼. AIDP는 연결 이름이다.', '첨부의 SIDDG를 현재 스키마로 복사하지 않았다. 운영 골드 owner는 별도 승인·설정이 필요하다.'),
      ('골드 등록 범위', '후보 구분', '지식 4개·27컬럼, 지원 3개·9컬럼, 파일 보관 1개·5컬럼, 실행 상태 1개·5컬럼.', '골드 후보는 지식·지원 7개·36컬럼. 지원 3개는 추가 검토, 보관 표는 제외 검토, 실행 상태는 에이전트에 유지한다.'),
      ('테이블 명명', '미부합 / 후보 작성', '현재 LGL_*_S / LGL_*_A. 첨부는 IDD_B02_* 형식의 변경안을 사용한다.', '골드 후보 7개의 IDD_과제번호_* 이름을 제안했다. 첨부 자체의 번호 자릿수·접미사 규칙도 확인 필요로 적혀 있다.'),
      ('컬럼 표준용어', '미확인 / 후보 작성', '현재 NM·CN·VAL·CNT·DTM 등의 약어. 첨부에는 NAME·CTNT·VALU·CONT·DATE_TIME 등이 있다.', '첨부의 서술·약어 방식을 참고해 후보를 작성했다. 사전에서 실제 등록된 단어·용어·도메인·인포타입을 대조해야 확정할 수 있다.'),
      ('문자열 타입·길이', '일부 부합', 'NVARCHAR 없음. VARCHAR2 BYTE와 CLOB 사용. 문서ID는 512 BYTE, 문서명은 CLOB이다.', '첨부의 문서ID 36자 등으로 일괄 축소하지 않는다. 한글 가능 열의 최대 바이트와 승인 인포타입을 확인한다.'),
      ('여부형', '변경 검토', 'JSON_TXT_OMIT_YN은 NUMBER(1), 코드에서 0·1·NULL을 검사한다. DDL 값 CHECK는 없다.', 'CHAR(1)은 제안만 했다. 1→Y·0→N·NULL 유지 변환, writer/reader·CHECK 변경이 함께 필요하다.'),
      ('일시형', '현행 유지 검토', 'REG_DTM은 TIMESTAMP WITH TIME ZONE, 기본값 SYSTIMESTAMP다. DB 시간대를 한국 시간으로 확인하지 않았다.', '첨부 TIMESTAMP(6)로 바로 바꾸면 시간대 정보가 사라진다. 기준 시간대·변환·정밀도 확인 후 결정한다.'),
      ('제약조건', 'DDL 대조', 'PK 9개(구성 컬럼 18개), 명시 CHECK 6개, FK 1개, 추가 조회 인덱스 4개. NOT NULL 컬럼 32개.', '유일한 물리 FK는 조회채널→조회게시다. 문서·구조·본문의 논리적 연결을 물리 FK로 잘못 표시하지 않았다.'),
      ('JSON 제약', '일부 존재', '조회게시·조회행·실행상태 JSON에 IS JSON CHECK가 있다. 문서·구조·본문·원문게시 JSON에는 없다.', '검토사항을 현재 제약으로 복사하지 않는다. JSON 내부 계약과 값 검증은 해당 적재·조회 코드에서 별도로 확인한다.'),
      ('한글 포함 표시', '코드 계약 기준', '원문·문서명·검색키·일부 ID는 한글 가능. 게시·조회·상태 JSON은 현재 ASCII 이스케이프 직렬화다.', 'Y는 한글 가능 여부이며 전체 DB 실측이 아니다. N인 JSON도 해석한 값에는 한글이 있을 수 있다. 셀 메모 참조.'),
      ('적재·조회 소비자', '범위 구분', '원문 배치는 7테이블에 적재한다. 조회채널과 실행상태는 구조 검사 대상이며 배치가 자동 쓰기·활성화하지 않는다.', '실제 RAG 조회 매핑 전환·권한·채널 선택 및 에이전트 상태 소비자 연결은 별도 현장 확인이 필요하다.'),
      ('온톨로지·숏컷·위키', '이번 DDL 범위 밖', '이번 9테이블에 전용 물리 테이블 정의가 포함되어 있지 않다. 현재 원문 배치의 적재 대상도 아니다.', 'S3 작업 JSON·검토·승인·SQL 적재 및 소비자 연결은 별도다. 검색 관계행이나 실행상태 표를 전용 온톨로지 표로 표시하지 않는다.'),
      ('현장 상태·승인', '이번 작업 미확인', '사내 DB 카탈로그·행 수·메타 신청번호·승인번호를 조회하지 않았다. 제품 코드·DB·MAIN을 변경하지 않았다.', '전달 SQL 기준의 현재 정의와 현장 생성·적재 완료는 구분한다. 메타 신청·승인·DBA 생성·적재 증거를 단계별로 보완한다.'),
      ('파일 구성', '작성 완료', '테이블·컬럼은 첨부와 동일한 열 이름·순서다. 문장을 업무 의미와 용도 중심으로 작성했다.', 'Bizmeta는 기존 작성 규약의 보완 자료, 작성근거는 사용 파일·해시·실제 소비자 추적 자료다. 상세 설명과 허용값은 셀 메모에 보존했다.'),
    ]
    for row in summary_rows:
        summary.append(row)

    biz = w.create_sheet('Bizmeta')
    biz.append(['No.', '에이전트번호', '스키마', '테이블명', '데이터논리명', '데이터출처', '데이터유형', '데이터 가공 프로세스 설명', '생성시각', '골드 등록 구분', '신청·승인·생성 상태', '현행 적재·사용 범위'])
    for i, k in enumerate(ORDER, 1):
        t = mapping['tables'][k]
        name, definition, source, process, status = TABLES[k]
        schedule = '데이터 구축·게시 완료 시. 외규 일일·내규 업로드 후 갱신은 목표이며 현장 배치 시각 미확정.'
        use = '원문 배치 적재 대상. 적재 후 재조회 검증; 실제 현장 완료는 별도 확인.'
        if k == 'query_active':
            schedule = '명시적으로 조회 게시본을 선택·변경할 때.'
            use = '원문 배치는 구조만 검사. 자동 채널 활성화 없음.'
        elif k == 'query_state':
            schedule = '연결된 소비자가 실행 상태를 저장·변경할 때.'
            use = '원문 배치는 구조만 검사. 실제 상태 소비자 연결·이행은 별도 확인.'
        elif k == 'asset_part':
            use = '원문 배치 적재 대상. 복구용 보관이며 GENOS에서 전체 자료를 상시 복원하는 목표 구조가 아님.'
        biz.append([i, agent, owner(mapping, k), t['name'], name, source, 'MASTER' if k in ('query_active', 'query_state') else 'SNAPSHOT', process, schedule, status, '명칭 후보 / 메타 신청·승인·DBA 생성·현장 적재 증거 미확인', use])

    evidence = w.create_sheet('작성근거')
    evidence.append(['구분', '파일·코드 위치', '확인 내용', 'SHA-256 / 상태'])
    evidence.append(['첨부 양식', '삼성증권_AI기반PI대표과제_골드컬럼마스터_A02_초안.xlsx (원본 보존명: reference_template.xlsx)', '테이블 8열·컬럼 15열의 이름·순서·기본 서식 및 서술 방식 참고. 본문 B02·ELS 자료는 복사하지 않음.', sha(TEMPLATE.read_bytes())])
    sources = [
        (BASE / '01_CREATE_TABLES.sql', '현재 물리 테이블·순번·타입·NULL·PK·CHECK·FK·기본값·인덱스'),
        (BASE / 'physical_mapping.yaml', 'dev_silver 실제 owner·테이블·컬럼 매핑과 업무 설명. prod_gold 비활성'),
        (BASE / '02_COMMENTS.sql', '기존 논리명·업무 의미·허용값·산식·출처; 상세 셀 메모로 보존'),
        (PACKAGE, 'client/physical_mapping.yaml 및 01_CREATE_TABLES.sql이 위 원본과 동일함을 확인'),
        (ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_stateless_20261027_r1/build.py', '최신 전달본이 기존 분리 레이어 레시피 패키지와 매핑을 재사용'),
        (ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_stateless_20261027_r1/live_runner.py', '7표 쓰기 대상, query_active·query_state는 검사 대상'),
        (ROOT / '02_BACKEND/semantic_runtime/physical_mapping.py', '매핑의 타입·식별자·PK·FK·CHECK 계약 및 DDL 생성'),
        (ROOT / '02_BACKEND/semantic_runtime/oracle_dp_io.py', '원문 ID·본문·0/1/NULL 표시·바이트 길이 검증'),
        (ROOT / '02_BACKEND/semantic_runtime/oracle_query_catalog.py', '조회 종류·검색키·게시·채널·ASCII JSON 직렬화'),
        (ROOT / '02_BACKEND/semantic_runtime/oracle_dp_assets.py', '분할 파일·원문 게시·해시·ASCII JSON 직렬화'),
        (ROOT / '00_SYSTEM/ARCHITECTURE.md', '저장 책임·개발계 정정·메타 등록과 타입 규약'),
        (ROOT / '07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md', '테이블 목록·Bizmeta·등록 대상·컬럼 정의 작성 기준'),
    ]
    for path, what in sources:
        evidence.append(['저장소 근거', str(path.relative_to(ROOT)), what, sha(path.read_bytes())])
    evidence.append(['판정 범위', '2026-10-27 로컬 저장소·전달 패키지 기준', '현장 DB·메타마이너를 조회하거나 DDL을 실행하지 않음.', 'DB·제품 코드·MAIN 변경 없음'])

    format_sheet(t_sheet, [12, 10, 26, 31, 28, 62, 46, 62], template_styles['테이블'])
    format_sheet(c_sheet, [12, 10, 26, 25, 8, 25, 26, 24, 25, 48, 52, 44, 6, 58, 12], template_styles['컬럼'])
    format_sheet(summary, [24, 25, 82, 88])
    format_sheet(biz, [6, 12, 10, 26, 28, 48, 14, 66, 52, 24, 44, 58])
    format_sheet(evidence, [18, 88, 88, 70])
    for ws in (t_sheet, c_sheet):
        for i, style in enumerate(template_styles[ws.title], 1):
            ws.cell(1, i)._style = copy(style)
            ws.cell(1, i).font = copy(ws.cell(1, i).font)
        for row in ws.iter_rows(min_row=2):
            for col in ([1, 2] if ws is t_sheet else [1, 2, 5, 13, 15]):
                row[col - 1].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        change_col = 8 if ws is t_sheet else 11
        for row in range(2, ws.max_row + 1):
            cell = ws.cell(row, change_col)
            cell.fill = PatternFill('solid', fgColor='F4CCCC' if str(cell.value).startswith('미반영') else 'FFF2CC')
    for row in range(2, c_sheet.max_row + 1):
        if c_sheet.cell(row, 6).value != c_sheet.cell(row, 9).value:
            c_sheet.cell(row, 9).fill = PatternFill('solid', fgColor='FFF2CC')
    for ws in (t_sheet, c_sheet):
        ws.cell(1, 2).comment = Comment('현재 전달 SQL의 개발계 owner. 운영 골드 스키마 승인 상태와 별도입니다.', '작성 기준')
    c_sheet['I1'].comment = Comment('TOBE 타입은 검토 후보. 현재 타입을 우선 보존하며 변경 조건은 검토내용·반영내용에 기재합니다.', '작성 기준')
    c_sheet['L1'].comment = Comment('현재 DDL 제약입니다. 제안 타입을 아직 적용하지 않았으므로 TOBE 제약으로 해석하지 마세요.', '작성 기준')
    t_sheet['D1'].comment = Comment('골드 후보만 IDD_과제번호_* 변경안을 작성했습니다. 미승인 이름이며 현행 개발 테이블을 개명하지 않았습니다.', '작성 기준')
    w.properties.title = '법규 테이블·컬럼 마스터 검토 초안'
    w.properties.subject = '현재 전달 SQL 9테이블·46컬럼과 사용자 첨부 양식 대조'
    w.properties.creator = 'Codex'
    w.properties.description = '현재 정의와 변경 후보를 구분. 표준용어·메타·현장 DB 승인 미확인.'
    w.active = 0
    output = HERE / OUTNAME
    w.save(output)
    return output, mapping, template_headers, constraints_count

def validate(output, mapping, headers, counts):
    w = openpyxl.load_workbook(output)
    assert [c.value for c in w['테이블'][1]] == headers['테이블']
    assert [c.value for c in w['컬럼'][1]] == headers['컬럼']
    assert w['테이블'].max_row == 10 and w['컬럼'].max_row == 47
    assert w['Bizmeta'].max_row == 10
    ddl = (BASE / '01_CREATE_TABLES.sql').read_text()
    parsed = {}
    for match in re.finditer(r'CREATE TABLE (\w+)\.(\w+) \(\n(.*?)\n\);', ddl, re.S):
        schema, table, body = match.groups()
        cols, pk = [], []
        for line in body.splitlines():
            line = line.strip().rstrip(',')
            if line.startswith('CONSTRAINT'):
                p = re.search(r'PRIMARY KEY \(([^)]+)\)', line)
                if p:
                    pk = p[1].split(',')
                continue
            name, typ = line.split(' ', 1)
            nullable = 'NOT NULL' not in typ
            typ = typ.replace(' NOT NULL', '')
            default = None
            if ' DEFAULT ' in typ:
                typ, default = typ.split(' DEFAULT ')
            cols.append((name, typ, nullable, default))
        parsed[(schema, table)] = (cols, pk, body)
    rows = list(w['컬럼'].iter_rows(min_row=2, values_only=True))
    seen = set()
    for row in rows:
        _, schema, table, name, seq, typ, proposed, logical, totyp, check, change, con, pk, definition, hangul = row
        identity = (schema, table, name)
        assert identity not in seen
        seen.add(identity)
        cols, keys, body = parsed[(schema, table)]
        dc = cols[seq - 1]
        assert (name, typ) == dc[:2]
        assert ('NOT NULL' in con) == (not dc[2])
        assert ('DEFAULT ' + dc[3] in con) if dc[3] else ('DEFAULT ' not in con)
        assert (pk == 'Y') == (name in keys)
        assert re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', proposed)
        assert logical and ' ' not in logical and definition and check and change
        assert len(logical.encode('utf-8')) <= 30, logical
        assert hangul in ('Y', 'N')
    assert len(seen) == sum(len(x[0]) for x in parsed.values()) == 46
    assert counts == {'pk': 9, 'check': 6, 'fk': 1, 'index': 4}
    all_text = '\n'.join(str(c.value or '') for ws in w for row in ws for c in row)
    for marker in ('ELS_QA_DOCUMENT_G', 'ELS_QA_SPEC_FIELD_G', 'ELS_QA_VDB_CHUNK_G'):
        assert marker not in all_text
    assert all(c.data_type != 'f' for ws in w for row in ws for c in row)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
    with zipfile.ZipFile(PACKAGE) as z:
        assert z.read('client/physical_mapping.yaml') == (BASE / 'physical_mapping.yaml').read_bytes()
        assert z.read('01_CREATE_TABLES.sql') == (BASE / '01_CREATE_TABLES.sql').read_bytes()
    result = {
        'status': 'PASS', 'workbook': output.name, 'sha256': sha(output.read_bytes()),
        'bytes': output.stat().st_size, 'sheet_names': w.sheetnames,
        'table_count': 9, 'column_count': 46, 'constraints': counts,
        'same_headers_as_template': True, 'all_current_columns_match_ddl': True,
        'latest_package_ddl_mapping_equal': True, 'template_sha256': sha(TEMPLATE.read_bytes()),
        'mapping_sha256': sha((BASE / 'physical_mapping.yaml').read_bytes()),
        'ddl_sha256': sha((BASE / '01_CREATE_TABLES.sql').read_bytes()),
        'database_access': False, 'product_code_modified': False,
        'metadata_approval_verified': False, 'field_creation_verified': False,
    }
    (HERE / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', default='확인 필요')
    args = parser.parse_args()
    output, mapping, headers, counts = build(args.agent)
    validate(output, mapping, headers, counts)
