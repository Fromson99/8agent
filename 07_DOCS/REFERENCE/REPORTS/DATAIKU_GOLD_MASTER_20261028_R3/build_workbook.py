"""Read-only schema consolidation into the supplied two-sheet Excel format.

Run with repository Python. Generates review documents only; no DB or model calls.
"""
from pathlib import Path
from collections import OrderedDict, Counter
from copy import copy
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import zipfile

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REF = HERE.parent / 'DATAIKU_COLUMN_MASTER_20261027_R1'
BASE = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1'
ONT = ROOT / '08_DEPLOYMENT/DATAIKU/ontology_workflow_20261028_r1'
TEMPLATE = REF / 'reference_template.xlsx'
spec = importlib.util.spec_from_file_location('previous', REF / 'build_workbook.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
MAPPING = yaml.safe_load((BASE / 'physical_mapping.yaml').read_text())
GOLD_KEYS = [k for k in previous.ORDER if MAPPING['tables'][k]['role'] in ('gold_knowledge', 'gold_support')]
FONT_PATH = '/mnt/c/Windows/Fonts/malgun.ttf'
FONT_BOLD_PATH = '/mnt/c/Windows/Fonts/malgunbd.ttf'
FONT = ImageFont.truetype(FONT_PATH, 15)
FONT_BOLD = ImageFont.truetype(FONT_BOLD_PATH, 15)
OUT = HERE / '법률에이전트_3번5번_골드테이블컬럼마스터_20261028_R3.xlsx'

# Explicit proposed terms. These are not asserted to be approved dictionary entries.
# physical, Korean term, constituent words, domain
TERMS = {
 'DATA_VER_ID': ('DATA_VER_ID', '데이터구축세대ID', '데이터+구축+세대+ID', 'ID'),
 'DOC_ID': ('LGL_DOC_ID', '법규문서ID', '법규+문서+ID', 'ID'),
 'DOC_NM': ('LGL_DOC_NAME_CTNT', '법규문서명내용', '법규+문서+명+내용', '내용'),
 'SRC_DATA_HASH_VAL': ('SRC_DATA_HASH_VALU', '원본자료해시값', '원본+자료+해시+값', '값'),
 'DOC_JSON_CN': ('LGL_DOC_JSON_CTNT', '법규문서JSON내용', '법규+문서+JSON+내용', '내용'),
 'UNIT_ID': ('LGL_UNIT_ID', '법규구조단위ID', '법규+구조+단위+ID', 'ID'),
 'PRNT_UNIT_ID': ('PRNT_LGL_UNIT_ID', '상위법규구조단위ID', '상위+법규+구조+단위+ID', 'ID'),
 'UNIT_JSON_CN': ('LGL_UNIT_JSON_CTNT', '법규구조JSON내용', '법규+구조+JSON+내용', '내용'),
 'BLK_ID': ('LGL_BLK_ID', '법규본문조각ID', '법규+본문+조각+ID', 'ID'),
 'BLK_TXT_CN': ('LGL_TEXT_CTNT', '법규원문내용', '법규+원문+내용', '내용'),
 'BLK_JSON_CN': ('LGL_BLK_JSON_CTNT', '본문조각JSON내용', '본문+조각+JSON+내용', '내용'),
 'JSON_TXT_OMIT_YN': ('JSON_TXT_OMIT_YN', 'JSON본문생략여부', 'JSON+본문+생략+여부', '여부'),
 'SRC_PBLS_ID': ('SRC_PBLS_ID', '원문게시ID', '원문+게시+ID', 'ID'),
 'PBLS_JSON_CN': ('SRC_PBLS_JSON_CTNT', '원문게시JSON내용', '원문+게시+JSON+내용', '내용'),
 'REG_DTM': ('SRC_PBLS_REG_DATE_TIME', '원문게시등록일시', '원문+게시+등록+일시', '일시'),
 'SRCH_PBLS_ID': ('SRCH_PBLS_ID', '법규조회게시ID', '법규+조회+게시+ID', 'ID'),
 'ROW_KIND_CD': ('LGL_ROW_KIND_VALU', '법규조회유형값', '법규+조회+유형+값', '값'),
 'ROW_ID': ('LGL_ROW_ID', '법규조회행ID', '법규+조회+행+ID', 'ID'),
 'SRCH_KEY_ID': ('LGL_SRCH_KEY_VALU', '법규검색키값', '법규+검색+키+값', '값'),
 'OWNR_REF_ID': ('LGL_OWNR_REF_ID', '법규소속참조ID', '법규+소속+참조+ID', 'ID'),
 'TGT_REF_ID': ('LGL_TGT_REF_ID', '법규대상참조ID', '법규+대상+참조+ID', 'ID'),
 'ROW_HASH_VAL': ('LGL_ROW_HASH_VALU', '법규조회행해시값', '법규+조회+행+해시+값', '값'),
 'ROW_JSON_CN': ('LGL_ROW_JSON_CTNT', '법규조회JSON내용', '법규+조회+JSON+내용', '내용'),
 'MNFST_JSON_CN': ('SRCH_MNFST_JSON_CTNT', '조회명세JSON내용', '조회+명세+JSON+내용', '내용'),
 'CHNL_NM': ('LGL_CHNL_NAME', '법규조회채널명', '법규+조회+채널+명', '명'),
 'CHG_SEQ_NO': ('SRCH_CHG_SEQ_NO', '조회변경순번', '조회+변경+순번', '순번'),
 'PUB_ID': ('ONT_PBLS_ID', '온톨로지게시ID', '온톨로지+게시+ID', 'ID'),
 'BNDL_ID': ('ONT_BNDL_ID', '온톨로지묶음ID', '온톨로지+묶음+ID', 'ID'),
 'REV_NO': ('ONT_WORK_VER_NO', '지식작업판본번호', '지식+작업+판본+번호', '번호'),
 'PKG_HASH_VAL': ('ONT_PKG_HASH_VALU', '지식게시해시값', '지식+게시+해시+값', '값'),
 'PKG_JSON_CN': ('ONT_PKG_JSON_CTNT', '지식게시JSON내용', '지식+게시+JSON+내용', '내용'),
 'ANC_HASH_VAL': ('SRC_ANCHOR_HASH_VALU', '원문좌표해시값', '원문+좌표+해시+값', '값'),
 'SRC_VER_ID': ('SRC_VER_ID', '원문판본ID', '원문+판본+ID', 'ID'),
}

ONT_DESC = {
 'publication': ('법규온톨로지게시내역', '검토·승인한 개념 묶음의 조건·산정·효과·예외와 원문 근거를 사전에 조립한 게시본으로 보관한다. 같은 묶음의 새 승인 판본도 이전 게시본을 덮어쓰지 않는다.', 'Dataiku S3 승인 작업 JSON·승인 영수증·검증한 법규 원문', '원문과 승인 판본·해시를 재검증하고 사전 조립 JSON과 게시 ID를 저장한다. 원문 좌표 색인·활성 선택·감사 기록과 한 트랜잭션으로 게시한다.', 'SNAPSHOT'),
 'head': ('법규온톨로지선택내역', '개념 묶음마다 현재 사용할 온톨로지 게시본과 변경 순번을 관리한다. 게시 중지 시 게시 ID를 NULL로 두며, 이전 게시본과 감사 이력은 보존한다.', '승인된 온톨로지 게시본과 게시·중지·롤백 요청', '현재 변경 순번을 확인한 뒤 게시 ID를 바꾸고 순번을 증가시킨다. 이미 시작한 RAG 요청의 선택본은 중간에 바꾸지 않는다.', 'MASTER'),
 'anchor': ('법규원문지식연결내역', '문서·원문 판본·구조 단위에 연결된 온톨로지 게시본을 찾는 색인이다. 질문 번호를 중심 키로 삼지 않으며, 조회자가 허용받은 원문 범위를 확인한다.', '온톨로지 게시 JSON의 provisions.anchor와 검증된 원문 좌표', '게시본의 원문 좌표별 해시를 계산해 게시 ID와 함께 적재한다. 활성 게시본과 조인하여 원문 도착 시 필요한 묶음만 조회한다.', 'SNAPSHOT'),
}
ONT_COL_DEF = {
 'PUB_ID': '승인 판본의 온톨로지 게시본을 구분하는 해시형 식별자. 묶음 ID·작업 판본·승인 영수증·게시 내용 해시로 계산하며 원문 게시 ID와 구분한다.',
 'BNDL_ID': '같은 개념 묶음을 여러 작업 판본과 게시본에 걸쳐 연결하는 식별자. 현재 생성기는 cb- 접두어를 사용하며 저장 계약은 84 BYTE다.',
 'REV_NO': '게시본을 만들 때 승인받은 작업 판본의 번호. 문자열 원문 판본 ID 및 활성 선택의 변경 순번과 다르다. 기존 게시 DDL에는 양수 CHECK가 없으며 작업 승인 경로에서 검사한다.',
 'PKG_HASH_VAL': '사전 조립 시나리오와 원문 좌표를 담은 게시 payload의 정규화 내용 해시. 단순 CLOB 저장 문자열 바이트를 다시 해시한 값으로 대체하지 않는다.',
 'PKG_JSON_CN': '승인 개념 묶음·조건·산정·결과·예외·미확인·근거 좌표와 사전 조립 시나리오를 담은 JSON. 법률 수치 계산 실행 결과나 개별 질문의 정답 묶음이 아니다.',
 'ANC_HASH_VAL': '문서 ID·원문 판본·구조 단위 ID의 세 항목을 정규화 JSON으로 해시한 조회키. 표시명·본문 해시는 이 키에 포함하지 않고 게시 JSON과 원문 대조에서 별도 검증한다. 이미지 bbox 좌표와 다르다.',
 'DOC_ID': '온톨로지 근거가 속한 법규 문서 식별자. 원문 테이블의 문서 ID와 같은 값이며 조회 권한 확인에 사용한다.',
 'SRC_VER_ID': '온톨로지 근거 원문의 판본 식별값. 현재 수집 경로는 원본자료 해시를 넣는다. 데이터 구축 세대 ID와 다른 값이며 현행 512 BYTE 계약을 유지한다.',
 'UNIT_ID': '온톨로지 근거가 속한 원문 조항 등의 구조 단위 식별자. 원문 테이블의 구조 단위 ID와 같은 값이며 세대·문서·판본 검증을 함께 수행한다.',
 'CHG_SEQ_NO': '개념 묶음의 활성 게시 선택을 바꿀 때 증가하는 순번. 초기 0을 허용하며 게시·중지·롤백 시 증가한다. 원문 조회 채널의 1 이상 순번과 구분한다.',
}

FEEDBACK = [
 ('F01', '01:47–03:53', '공통 재사용 가능한 표준단어를 조합하고 용어는 도메인으로 종결', '49개 컬럼의 수식어+도메인 구성을 표준용어검토에 작성. ID·값·내용·여부·일시·명·순번·번호로 종결.', '전체 컬럼', '표 작성 반영; 사전 등록 여부는 확인 전'),
 ('F02', '04:07–06:50', '키·항목 같은 수식어로 끝내지 않고 기존 도메인·인포타입 우선', '검색키는 법규검색키값, 해시는 원본자료해시값·원문좌표해시값 등으로 구체화. 기존 타입과 맞는 인포타입을 우선 조회.', 'SRCH_KEY_ID·각 HASH 열', '이름 반영; 승인 인포타입 조회 필요'),
 ('F03', '07:25–08:47', '문자값·숫자값처럼 범용 이름을 피하고 업무 의미 상세화', '조회자료유형값→법규조회유형값, 소속참조ID→법규소속참조ID 등으로 용도 명시.', '표준용어검토', '표 작성 반영'),
 ('F04', '08:47–11:10', '기존 코드의 값·길이까지 같을 때 재사용; 다르면 업무 수식어로 구분', 'ROW_KIND_CD는 전사 승인 코드 확인 전 법규조회유형값으로 제안. 실제 종류 문자열은 보존하며 코드 재번호화 없음.', 'LGL_SRCH_ROW_S.ROW_KIND_CD', '코드 표준 확인 전'),
 ('F05', '11:39–13:17', '절·구분 및 적재/로드 등 논리명과 단어 의미 맞추기', '구조 단위는 법규구조단위ID로 정의하고 장·절·조·항·호를 포함한다고 설명. 별도 SECTION/절명 컬럼을 임의 생성하지 않음.', 'LGL_DOC_UNIT_S·UNIT_ID', '표 작성 반영'),
 ('F06', '13:17–15:59', '문서 ID는 범용 문서 용어와 충돌하지 않도록 업무 상세화', '법규문서ID(LGL_DOC_ID)로 제안. 원문·조회·온톨로지의 동일 ID에 같은 이름·VARCHAR2(512 BYTE)를 적용.', 'DOC_ID 전체', '표 작성 반영; ID 예외 승인 확인'),
 ('F07', '13:17–14:44', '청크ID VARCHAR 240 용어는 재사용 가능 여부 검토', '우리 본문조각ID는 청크와 의미·길이가 같다는 확인이 없고 현행 512 BYTE다. 240 또는 UUID 36으로 축소하지 않고 법규본문조각ID로 제안.', 'LGL_DOC_BLK_S.BLK_ID', '동등성 확인 전 대체하지 않음'),
 ('F08', '15:59–18:02', 'bbox 좌표는 대상과 표현 의미를 논리명·물리명·정의에서 일치', '새 온톨로지 색인은 이미지 bbox가 아닌 원문 좌표의 해시다. 원문좌표해시값으로 작성. bbox·제목경로는 현재 별도 물리 컬럼이 없어 새 컬럼을 추가하지 않음.', 'LGL_ONT_ANC_A.ANC_HASH_VAL', '표 작성 반영'),
 ('F09', '06:04–07:50 / 18:02–19:24', '가변 원문은 CLOB 가능; 짧은 항목은 필요 길이 산정', '본문·JSON CLOB 유지 사유를 각 열에 작성. 문서명 CLOB은 법규문서명내용으로 제안하고 최대 길이 실측 뒤 제한형 전환 검토.', 'CLOB 전체', '내용 도메인 반영; 실측 미수행'),
 ('F10', '20:45–21:12', '운영 골드 테이블명에 _G 등 레이어 접미사를 붙이지 않음', 'TOBE 테이블은 IDD_대표과제코드_LGL_* 형식, _G·_S·_A 제거. 현재 개발계 이름은 매핑표에 보존.', '골드 10테이블', '표 작성 반영'),
 ('F11', '21:12–25:50', '한글 3바이트·기존 2바이트 표준 대비 길이 조정 검토', '현재 BYTE 계약과 한글 가능성을 컬럼별 기록. 기존 표준 재사용 시 LENGTHB 실측과 문자셋 확인 후 조정; 모든 열을 일괄 1.5배 확대하지 않음.', '한글 가능 문자열', '길이 검토표 작성; 현장 실측 필요'),
 ('F12', '23:37–26:38', 'NVARCHAR2 자동 생성을 피하고 VARCHAR 계열로 사전 생성', '현행 VARCHAR2 BYTE·CLOB 계약을 사용. 승인된 DDL로 먼저 생성하고 Dataiku는 매핑·적재하도록 이행 작업을 기록.', '운영 문자열 컬럼', '표 작성 반영; DB 생성 미수행'),
 ('F13', '21:12–23:27', 'PK·인덱스 확인, 테이블스페이스는 안내값 사용', '현행 PK·FK·CHECK·인덱스를 목표 이름으로 대조. 녹취의 테이블스페이스 이름은 불명확하므로 확정값을 만들지 않고 DBA 확인으로 표시.', '제약인덱스·등록관리', '제약 반영; TS 확인 전'),
 ('F14', '26:38–29:04', '카드/필드 등 용어와 키·순번 의미 재검토, 물리명 길이 확인', '우리 시스템에 없는 상품 카드·필드 테이블은 제외. 49컬럼 물리명·논리명 UTF-8 30바이트 예비 검사, 순번의 0/1 시작 차이를 별도 정의.', '컬럼·표준용어검토', '표 작성 반영'),
 ('F15', '29:04–30:27', '용어 등록을 먼저 하고 모델 등록; 재검토한 엑셀로 협의', '용어별 조회 검색어·재사용 조건·신규 후보·승인상태 및 테이블별 메타/DBA/적재/조회 상태를 별도 기록.', '표준용어검토·등록관리', '재검토용 통합본 작성'),
 ('F16', '04:07', '벡터는 새 벡터 도메인 사용', '우리 현행 10테이블에 벡터 물리 컬럼이 없으므로 ELS 임베딩 테이블을 복사하지 않음. 향후 별도 벡터 컬럼 설계 시 해당 도메인 대조.', '제외후속', '현재 대상 없음'),
 ('F17', '사용자 후속', '3번·5번은 우리 법률 에이전트; 2번은 참고용', '공통 지식 테이블 10개를 3번·5번 공동 사용으로 작성. 2번 상품 데이터·테이블·코드값은 등록 대상에서 제외.', '테이블·Bizmeta', '범위 반영'),
 ('F18', '최신 구현 대조', '최근 온톨로지 게시 지식을 기존 골드 목록에 통합', '게시본·활성 선택·원문 좌표 색인 3개 13컬럼 추가. 작업 상태·이벤트 2개 10컬럼은 Agent로 유지.', '온톨로지 3테이블', '표 작성 반영; 운영 이행 미수행'),
]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_csv(path):
    return list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))

def field(text, prefix):
    match = re.search(re.escape(prefix) + r':\s*(.*?)(?=\n\n|\Z)', text, re.S)
    return re.sub(r'\s+', ' ', match.group(1)).strip() if match else ''

def wrap(text, pixels, font=FONT):
    lines=[]
    for block in str(text or '').split('\n'):
        line=''
        for ch in block:
            if line and font.getlength(line+ch)>pixels:
                lines.append(line);line=ch
            else:line+=ch
        lines.append(line)
    return lines

def format_sheet(ws, widths, source_header=None):
    ws.freeze_panes = 'D2' if ws.title in ('테이블', '컬럼') else 'A2'
    ws.auto_filter.ref=ws.dimensions
    ws.sheet_view.showGridLines=False
    ws.sheet_view.zoomScale=80
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.print_title_rows='1:1';ws.print_area=ws.dimensions
    ws.oddFooter.center.text='법률 에이전트 3·5 | 골드 통합 검토본 | 2026-10-28'
    ws.oddFooter.right.text='&P / &N'
    border=Border(bottom=Side(style='thin',color='DBE2EA'))
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=width
    for row in ws:
        longest=1
        for c in row:
            header=c.row==1
            if header and source_header:
                c._style=copy(source_header[c.column-1])
            else:
                c.fill=PatternFill('solid',fgColor='20354D' if header else ('F3F6FA' if c.row%2==0 else 'FFFFFF'))
                c.font=Font(name='맑은 고딕',size=11,bold=header,color='FFFFFF' if header else '202D3A')
            c.alignment=Alignment(vertical='center',wrap_text=True,horizontal='center' if header else 'left')
            c.border=border
            longest=max(longest,len(wrap(c.value,widths[c.column-1]*7-14,FONT_BOLD if header else FONT)))
        ws.row_dimensions[row[0].row].height=max(34 if row[0].row==1 else 42,longest*15+12)

def build_model(prefix, confirmed):
    model=OrderedDict()
    for k in GOLD_KEYS:
        t=MAPPING['tables'][k]
        logical,definition,origin,process,status=previous.TABLES[k]
        model[k]=dict(key=k,source_owner='SIDDS',source_name=t['name'],name=f'IDD_{prefix}03_'+t['name'][:-2],logical=logical,
                      definition=definition,origin=origin,process=process,kind='MASTER' if k=='query_active' else 'SNAPSHOT',
                      classification='기존 지식' if t['role']=='gold_knowledge' else '기존 게시 지원',columns=[],pk=[],checks=[],fks=[],indexes=[])
        o=model[k]
        for old,c in t['columns'].items():
            name,log,words,domain=TERMS[c['name']]
            definition=previous.COLS[c['name']][2]
            if k=='query_row' and old=='DOCUMENT_ID':definition='조회 자료가 속한 문서의 ID. 문서별 접근 범위 검사에 쓰며 공통 용어집처럼 문서에 속하지 않는 행은 NULL일 수 있다.'
            target_type=c['type'];conversion='원천 값을 변환 없이 보존.'
            if c['name']=='JSON_TXT_OMIT_YN':
                target_type='CHAR(1)'
                definition='JSON 안의 중복 본문 생략 표시. Y=생략, N=미생략, NULL=미지정. 별도 본문 내용의 부재를 뜻하지 않는다.'
                conversion='제안 변환: 1→Y, 0→N, NULL 유지. 그 외 값은 오류로 분리. 조회 시 Y→1/N→0 역변환과 왕복 검사 필요; 현재 구현 미적용.'
            d=dict(old=old,current=c['name'],name=name,logical=log,words=words,domain=domain,type=target_type,current_type=c['type'],nullable=c['nullable'],default=c['default'],definition=definition,conversion=conversion,
                   allowed=field(c['description'],'허용값·코드·범위'),generation=field(c['description'],'산식·생성 규칙'),source_description=c['description'],korean=previous.korean(c))
            o['columns'].append(d)
        lookup={c['old']:c['name'] for c in o['columns']}
        o['pk']=[lookup[x] for x in t['pk']]
        for ck in t['checks']:
            col=lookup[ck['columns'][0]]
            expr=col+' IS JSON' if ck['kind']=='is_json' else col+' >= 1'
            o['checks'].append(dict(columns=[lookup[x] for x in ck['columns']],expr=expr,status='현행 보존'))
        if k=='block_payload':o['checks'].append(dict(columns=['JSON_TXT_OMIT_YN'],expr="JSON_TXT_OMIT_YN IN ('Y','N')",status='여부형 이행 제안'))
        for fk in t['foreign_keys']:o['fks'].append(dict(columns=[lookup[x] for x in fk['columns']],target=fk['target'],target_columns=[TERMS[MAPPING['tables'][fk['target']]['columns'][x]['name']][0] for x in fk['target_columns']]))
        for idx in t['indexes']:o['indexes'].append(dict(columns=[lookup[x] for x in idx['columns']],purpose='게시·유형 내 '+','.join(lookup[x] for x in idx['columns'][2:])+' 점조회'))
    oc=read_csv(ONT/'TABLE_COLUMNS.csv')
    om=json.loads((ROOT/'00_SYSTEM/SCHEMAS/ontology-db-mapping-v1.json').read_text())['tables']
    for k in ('publication','head','anchor'):
        source=om[k]['name'];log,definition,origin,process,kind=ONT_DESC[k]
        o=dict(key=k,source_owner='SIDDA',source_name=source,name=f'IDD_{prefix}03_'+source[:-2],logical=log,definition=definition,origin=origin,process=process,kind=kind,classification='신규 온톨로지 지식' if k!='head' else '신규 온톨로지 게시 지원',columns=[],pk=[],checks=[],fks=[],indexes=[])
        model[k]=o
        for row in [r for r in oc if r['테이블명']==source]:
            n=row['물리명']
            term=TERMS[n] if n!='CHG_SEQ_NO' else ('ONT_CHG_SEQ_NO','지식변경순번','지식+변경+순번','순번')
            d=dict(old=n,current=n,name=term[0],logical=term[1],words=term[2],domain=term[3],type=row['Oracle타입'],current_type=row['Oracle타입'],nullable=row['NULL']=='Y',default=None,definition=ONT_COL_DEF[n],conversion='원천 값·JSON 의미·해시를 변환 없이 보존.',allowed='현행 생성기·스키마 및 승인 게시 계약을 따른다.',generation='02_BACKEND/semantic_runtime/ontology_work/repository.py 및 schema.py',source_description=row['논리명'],korean='Y' if n in ('PKG_JSON_CN','DOC_ID','SRC_VER_ID','UNIT_ID') else 'N')
            if k=='head' and n=='PUB_ID':d['definition']='해당 개념 묶음에서 활성화한 온톨로지 게시본 ID. NULL은 활성 게시본 없음 또는 게시 중지이며 이전 게시 이력은 삭제하지 않는다.'
            o['columns'].append(d)
            if row['PK']=='Y':o['pk'].append(d['name'])
        if k=='publication':o['checks'].append(dict(columns=['ONT_PKG_JSON_CTNT'],expr='ONT_PKG_JSON_CTNT IS JSON',status='현행 보존'))
        if k=='head':o['checks'].append(dict(columns=['ONT_CHG_SEQ_NO'],expr='ONT_CHG_SEQ_NO >= 0',status='현행 보존; 0 허용'))
        if k in ('head','anchor'):o['fks'].append(dict(columns=['ONT_PBLS_ID'],target='publication',target_columns=['ONT_PBLS_ID']))
        if k=='anchor':o['indexes'].append(dict(columns=['SRC_ANCHOR_HASH_VALU'],purpose='원문 anchor 해시로 게시본 점조회'))
    return model

def constraints(t,c,model):
    parts=['NULL 허용' if c['nullable'] else 'NOT NULL']
    if c['name'] in t['pk']:parts.append('PK('+', '.join(t['pk'])+')')
    for ck in t['checks']:
        if c['name'] in ck['columns']:parts.append('CHECK('+ck['expr']+')'+(' [신규 제안]' if ck['status']=='여부형 이행 제안' else ''))
    for fk in t['fks']:
        if c['name'] in fk['columns']:parts.append('FK → SIDDG.'+model[fk['target']]['name']+'('+', '.join(fk['target_columns'])+')')
    if c['default']:parts.append('DEFAULT '+c['default'])
    return '\n'.join(parts)

def review(c):
    if c['current']=='JSON_TXT_OMIT_YN':return '여부 도메인 CHAR(1) 제안. 0/1/NULL 변환과 소비자 역변환 필요. 기존 코드에 적용된 상태가 아님.'
    if c['current']=='REG_DTM':return '일시 도메인 후보. 시간대 포함 현행 타입을 보존. 참고 예시 TIMESTAMP(6)로 시간대를 임의 제거하지 않음.'
    if c['current']=='DOC_NM':return 'CLOB과 내용 도메인 일치. 문서명 실측 전 제한형 문자열로 축소하지 않음.'
    if c['domain']=='ID':return '고유 식별값이므로 ID 예외 제안. 기존 용어 의미·타입·BYTE 길이 일치 확인 후 재사용; 불일치 시 업무 상세 용어 신청.'
    if c['current']=='ANC_HASH_VAL':return '문서·판본·구조 단위 3항목의 좌표 해시. 표시명·본문 해시는 별도 검증하며 이미지 bbox가 아님. 해시값 도메인·HASH 약어 대조.'
    if c['type']=='CLOB':return '가변 원문·JSON 내용으로 CLOB 유지. 기존 내용 도메인·인포타입 우선; JSON 직렬화와 해시 규칙 보존.'
    if c['current']=='ROW_KIND_CD':return '전사 코드 승인 미확인. 법규조회유형값으로 의미 구체화; 현행 문자열과 길이 보존.'
    if c['domain']=='순번':return '순번 도메인·기존 NUMBER(18) 인포타입 확인. 조회채널 >=1, 온톨로지 선택 >=0 차이 보존.'
    return '업무 대상·도메인 종결 반영. 기존 표준단어·용어·인포타입의 의미·타입·길이 대조 후 재사용 또는 신청.'

def main(prefix, confirmed):
    model=build_model(prefix,confirmed)
    usage=f'{prefix}03·{prefix}05 (공통)' if confirmed else f'3·5 공통\n({prefix}03·{prefix}05 잠정)'
    prefix_note='공식 접두어 확인됨' if confirmed else 'A 접두어는 참고 파일명 기준 잠정; 공식 A/B 표기 확인 필요'
    sources=[TEMPLATE,REF/'build_workbook.py',REF/'삼성증권_AI기반PI대표과제_법규_골드컬럼마스터_검토초안_20261027.xlsx',BASE/'physical_mapping.yaml',BASE/'01_CREATE_TABLES.sql',ONT/'01_CREATE_TABLES.sql',ONT/'TABLE_COLUMNS.csv',ONT/'TABLE_BIZMETA.csv',ROOT/'02_BACKEND/semantic_runtime/ontology_work/repository.py',ROOT/'02_BACKEND/semantic_runtime/ontology_work/schema.py',ROOT/'02_BACKEND/semantic_runtime/legal_agent/ontology_compiler.py',ROOT/'02_BACKEND/semantic_runtime/contracts.py']
    before={str(p.relative_to(ROOT)):sha(p) for p in sources}
    w=openpyxl.load_workbook(TEMPLATE)
    original_headers={s.title:[c.value for c in s[1]] for s in w}
    original_styles={s.title:[copy(c._style) for c in s[1]] for s in w}
    for s in w:s.delete_rows(2,s.max_row)
    tw,cw=w['테이블'],w['컬럼']
    bw=w.create_sheet('Bizmeta');bw.append(['No.','에이전트번호','스키마','테이블명','데이터논리명','데이터출처','데이터유형','데이터 가공 프로세스 설명','생성시각','등록 구분'])
    mw=w.create_sheet('개발운영매핑');mw.append(['공통 사용','개발 스키마','개발 테이블','개발 컬럼','개발 타입','운영 스키마 후보','운영 테이블 후보','운영 컬럼 후보','운영 타입 후보','값 이행·소비자 변경','현장 확인 상태'])
    terms=OrderedDict()
    for no,(k,t) in enumerate(model.items(),1):
        origin=t['origin']
        for src in model.values():origin=origin.replace(src['source_name'],src['name'])
        origin=origin.replace('LGL_FILE_PART_S','별도 파일 보관 목록·해시')
        reflected='표 작성 반영: 3·5번 공통, 3번을 대표 명명 후보로 사용. 운영 레이어 접미사 없음. 메타 승인·DB 생성은 미수행.'
        tw.append([usage,'SIDDG',t['source_owner']+'.'+t['source_name'],t['name'],t['logical'],t['definition'],origin,reflected])
        tw.cell(tw.max_row,3).comment=Comment('현재=개발계 전달 DDL/코드 계약이며 현장 실재 조회가 아닙니다. 운영 테이블은 신규 등록 후보입니다.','작성 기준')
        tw.cell(tw.max_row,4).comment=Comment('두 과제가 공유할 단일 객체의 대표 명명 후보입니다. 대표 과제를 5번으로 정하면 '+t['name'].replace(prefix+'03',prefix+'05')+'로 함께 매핑합니다. 두 이름의 중복 생성 요청이 아닙니다. '+prefix_note,'명명 검토')
        timing='검증된 구축 세대 게시 시. 외규 일일·내규 업로드 후 반영 목표; 고정 완료시각 미확정.'
        if k=='query_active':timing='완료 조회 게시본을 선택·변경할 때.'
        if k=='publication' or k=='anchor':timing='사람이 승인한 작업 판본을 DB에 게시할 때.'
        if k=='head':timing='게시·중지·롤백 때. 진행 중 요청은 이미 결속한 게시본 유지.'
        bw.append([no,usage,'SIDDG',t['name'],t['logical'],origin,t['kind'],t['process'],timing,t['classification']])
        for seq,c in enumerate(t['columns'],1):
            reflected='표 수정: '+c['current']+' → '+c['name']+'; '+c['logical']+'.'
            if c['current_type']!=c['type']:reflected+=' 타입 변경은 이행 제안.'
            cw.append([usage,'SIDDG',t['name'],c['current'],seq,c['current_type'],c['name'],c['logical'],c['type'],review(c),reflected,constraints(t,c,model),'Y' if c['name'] in t['pk'] else 'N',c['definition'],c['korean']])
            cw.cell(cw.max_row,14).comment=Comment('허용값: '+c['allowed']+'\n생성: '+c['generation']+'\n원천 설명: '+c['source_description'],'계약 근거')
            cw.cell(cw.max_row,15).comment=Comment('Y=허용 입력/현행 계약상 한글 가능. N=현재 생성·직렬화 계약상 ASCII 예상. 전체 실제 데이터 실측 결과는 아니며 DB 제약으로 금지한다는 뜻이 아닙니다.','문자 길이 검토')
            change=c['conversion']
            if k in ('publication','head','anchor'):change+=' 현재 repository.py는 5표 단일 owner·고정명. Gold 3표/Agent 2표의 개별 매핑 및 같은 게시 트랜잭션 유지 구현 필요.'
            else:change+=' 승인 물리명·프로필의 조회/적재 매핑 동시 변경 필요.'
            mw.append([usage,t['source_owner'],t['source_name'],c['current'],c['current_type'],'SIDDG',t['name'],c['name'],c['type'],change,'설계 대조만; 운영 생성·적재·조회 미확인'])
            key=(c['name'],c['logical'],c['type'])
            if key not in terms:terms[key]=dict(c=c,tables=[])
            terms[key]['tables'].append(t['name'])

    sw=w.create_sheet('표준용어검토')
    sw.append(['No.','논리명 후보','물리명 후보','구성 단어 후보','종결 도메인','타입·길이 후보','기존 표준 검색어','재사용 조건 / 없을 때 처리','한글명 UTF8 바이트','물리명 바이트','한글 길이 검토','사용 테이블','표준용어·인포타입 ID','승인 상태'])
    for no,v in enumerate(terms.values(),1):
        c=v['c'];domain=c['domain']
        reuse='의미·타입·길이·허용값이 같은 기존 용어 우선. 없거나 다르면 해당 업무 수식어의 신규 용어 신청 검토.'
        if domain=='ID':reuse+=' ID 예외와 외부 식별값 보존 근거 첨부.'
        length='ASCII 생성/직렬화 계약; 전체 데이터의 저장 BYTE 최대값 별도 확인.'
        if c['korean']=='Y':length='현장 문자셋·LENGTHB 최대값 확인. 기존 2바이트 기준 표준 재사용 시 한글 3바이트 차이 검토. 현재 BYTE 한도를 일괄 1.5배 변경하지 않음.'
        if c['type']=='CLOB':length='가변 원문/JSON CLOB. 실측·기존 인포타입 확인 전 짧은 VARCHAR2로 축소하지 않음.'
        sw.append([no,c['logical'],c['name'],c['words'],domain,c['type'],c['logical']+' / '+c['words'].replace('+',' '),reuse,len(c['logical'].encode()),len(c['name'].encode()),length,'\n'.join(v['tables']),'담당자 조회 후 기입','미조회·미신청'])

    fw=w.create_sheet('피드백반영')
    fw.append(['번호','녹취 구간 / 근거','피드백 요지','이번 표의 적용','대상','반영·확인 상태'])
    for row in FEEDBACK:fw.append(row)

    xw=w.create_sheet('제외후속')
    xw.append(['구분','기존 대상 / 개념','현행 컬럼수','처리·목표 레이어','제외 / 후속 사유','이번 통합 범위'])
    for row in [
        ('골드 제외','SIDDS.LGL_FILE_PART_S',5,'파일 보관·이관 영역; 현행 개발계 SIDDS 유지','복원용 압축/Base64 파일 조각. 직접 재사용 지식 조회 대상과 구분. 기존 파일·게시 의존성 보존.','기존 9표 중 제외; 삭제 요청 아님'),
        ('골드 제외','SIDDA.LGL_EXEC_ST_A',5,'에이전트','대화·요청 실행 상태와 재개 정보.','기존 9표 중 제외'),
        ('골드 제외','SIDDA.LGL_ONT_WORK_A',6,'에이전트 + S3 작업 JSON','생성 대기·초안·승인 작업 판본 상태. 승인 작업 원장은 보존하고 게시 지식만 골드에 둠.','신규 5표 중 제외'),
        ('골드 제외','SIDDA.LGL_ONT_EVT_A',4,'에이전트','검토·게시·중지·롤백 행위자·시간·영수증. 게시 지식과 출처 연결 유지.','신규 5표 중 제외'),
        ('포함 범위 설명','용어·정의·명시 참조·검색 자료','별도 표 아님','LGL_SRCH_ROW의 종류별 조회 행 + 조회 게시 명세','현재 물리 계약에서 이미 조회 행에 포함되는 범위. 같은 역할의 용어·관계 테이블을 중복 생성하지 않음.','골드 10표에 포함'),
        ('추가 설계','승인 용어·별칭의 독립 관리','미확정','향후 골드 후보','기존 용어집 조회와 사람 승인 별칭의 관리·게시 전용 모델은 구분. 현재 49컬럼에 가상의 별도 컬럼을 추가하지 않음.','등록 대상 수에 미포함'),
        ('추가 설계','LLM Wiki·숏컷·착지 사례','미확정','검토된 재사용 지식은 골드 후보','질문·실행 로그를 그대로 복사하지 않으며 승인된 원문 근거 단위·물리 모델·소비자 이행을 별도 확정.','전체 골드 목표의 후속 범위'),
        ('참고 전용','2번 ELS 상품·조건·청크 임베딩','51(참고)','이번 법률 과제 제외','2번 예시의 상품코드·벡터·bbox·제목경로를 법률 데이터로 복사하지 않음.','양식·피드백만 참조'),
    ]:xw.append(row)

    iw=w.create_sheet('제약인덱스')
    iw.append(['운영 테이블 후보','종류','이름 후보','컬럼 / 조건','참조 대상','현행·변경 구분','주의사항'])
    for k,t in model.items():
        iw.append([t['name'],'PK',t['name']+'_P',', '.join(t['pk']),'—','현행 키 보존','자동 생성 PK 인덱스와 추가 조회 인덱스 구분'])
        for no,ck in enumerate(t['checks'],1):iw.append([t['name'],'CHECK',t['name']+'_C'+str(no),ck['expr'],'—',ck['status'],'기존에 없는 원문 JSON/양수 조건을 임의 추가하지 않음'])
        for no,fk in enumerate(t['fks'],1):iw.append([t['name'],'FK',t['name']+'_F'+str(no),', '.join(fk['columns']),'SIDDG.'+model[fk['target']]['name']+'('+','.join(fk['target_columns'])+')','현행 관계 보존','두 과제 공유 객체의 동일 대상 참조'])
        for no,idx in enumerate(t['indexes'],1):iw.append([t['name'],'INDEX',t['name']+'_I'+str(no),', '.join(idx['columns']),'—','현행 추가 인덱스 보존',idx['purpose']])

    dw=w.create_sheet('상세Description')
    dw.append(['운영 테이블 후보','요약','1행 단위·PK','조회 질문','포함·제외','보유기간·기준시점','갱신·완료 기준','산식·단위','원천·가공','주의사항','업무 오너','예시 SQL'])
    grains={'document':'세대 내 문서 1건','source_unit':'세대·문서 내 구조 단위 1건','block_payload':'세대·문서 내 본문 조각 1건','query_row':'조회 게시본·종류 내 조회 행 1건','source_release':'원문 게시본 1건','query_release':'조회 게시본 1건','query_active':'조회 채널별 선택 1건','publication':'승인 작업 판본의 게시본 1건','head':'개념 묶음별 활성 선택 1건','anchor':'게시본 내 원문 좌표 1건'}
    questions={'document':'이 세대의 문서 이름과 원본 해시는 무엇인가?','source_unit':'이 조항의 상위 장·절은 무엇인가?','block_payload':'이 조항의 실제 인용 원문은 무엇인가?','query_row':'이 용어·문서·참조에 연결된 조회 자료는 무엇인가?','source_release':'이 원문 게시본은 어느 데이터 세대에 속하는가?','query_release':'조회 게시본은 어느 원문·검색 자료와 결속되는가?','query_active':'이 채널은 어느 조회 게시본을 사용하는가?','publication':'이 승인 묶음의 적용 조건·산정·예외·근거는 무엇인가?','head':'이 묶음에서 활성 게시본은 무엇이며 중지됐는가?','anchor':'이 원문 판본·조항에 연결된 승인 게시본은 무엇인가?'}
    for k,t in model.items():
        where=' AND '.join(n+'=:p'+str(i) for i,n in enumerate(t['pk'],1))
        dw.append([t['name'],t['definition'],grains[k]+' / '+', '.join(t['pk']),questions[k],
          '원문 기반 재사용 지식·게시 지원 포함. 개별 질문 답변·실행 로그·복원용 파일 조각 제외.',
          '완료 원문·게시 이력은 보존. 공식 기간·삭제 기준은 업무 오너 확인 필요.',
          t['process']+' 재조회 해시·건수·활성 선택·권한 검증 후 완료 판단.',
          '업무 집계 없음. 해시·식별자·변경 순번은 현행 생성 규칙 보존. 법률 산식의 실행 결과를 생성하는 표가 아님.',
          t['origin'],
          '개발계 계약과 운영 신청 후보를 구분. 현재 DB 생성·적재·GENOS 조회 완료 근거 없음. 원문 버전·권한을 함께 확인.',
          '3번·5번 법률 에이전트 담당 부서·담당자 기입',
          'SELECT '+', '.join(t['pk'])+' FROM SIDDG.'+t['name']+' WHERE '+where+';'])

    aw=w.create_sheet('등록관리')
    aw.append(['공통 사용','운영 테이블 후보','대표명 사용','표준용어 대조','메타 신청번호','메타 승인번호','DBA 생성 신청','DBA 생성 결과','적재 검증','RAG 조회 검증','테이블스페이스','관리 부서·담당자','보유기간'])
    for t in model.values():aw.append([usage,t['name'],'3번 대표명 제안; 5번 공동사용','미조회','미신청','미승인','미신청','미확인','미수행','미수행','DBA 확인 필요','담당자 기입','담당자 기입'])

    rw=w.create_sheet('작성기준')
    rw.append(['항목','내용','근거·확인 상태'])
    rows=[
      ('대상','사용자 지정 3번·5번 법률 에이전트 공동 사용. 2번 ELS는 참고 양식만 사용.','사용자 후속: 3번·5번 둘 다, 법률 에이전트 한정'),
      ('공통 물리 모델','기존 골드 후보 7표·36컬럼 + 온톨로지 게시 3표·13컬럼 = 10표·49컬럼. 과제별로 같은 표를 중복 생성하지 않는 공동사용안.','개발 계약 14표·69컬럼 중 Agent/파일 보관 4표·20컬럼 제외'),
      ('과제 표기',usage+'; '+prefix_note,'원본 파일명 A02와 본문 B02의 불일치 보존. 확인된 과제 번호 3·5와 공식 접두어를 구분.'),
      ('대표 테이블명','공유 객체의 대표 명명은 '+prefix+'03을 제안하고 '+prefix+'05는 공동 소비자로 기록. 운영 신청 시 공통 객체 담당 과제 확인.','공동 사용 자체와 대표 물리명 승인 상태를 구분'),
      ('운영 스키마','SIDDG는 제공 양식의 운영 골드 스키마 기준으로 작성. 실제 생성 권한·객체·테이블스페이스는 미확인.','개발계 SIDDS/SIDDA와 구분'),
      ('표의 현재 값','테이블명(현재)은 개발계 전달 DDL의 객체 이름. 데이터 타입(현재)은 코드 계약. 현장 DB 조회 결과가 아님.','개발운영매핑 시트에 owner·컬럼·타입·값 이행 연결'),
      ('표준 승인','한글명·영문 약어·도메인은 재검토 후보. 사내 표준사전 접속 없이 기존 표준의 등록·승인을 주장하지 않음.','기존 용어 검색어와 의미·타입·길이 대조 조건 작성'),
      ('한글·문자열','한글 3바이트 기준과 기존 2바이트 표준의 차이를 검토. 현재 VARCHAR2 BYTE/원문 CLOB 보존; 일괄 1.5배 확대 또는 길이 축소하지 않음.','실제 LENGTHB·문자셋·인포타입 대조 필요'),
      ('여부형 이행','JSON본문생략여부는 CHAR(1) Y/N/NULL로 제안. 기존 1/0/NULL의 왕복 변환·허용값 검사·소비자 수정이 필요.','표 수정은 완료; DB/제품 코드 적용은 미수행'),
      ('일시형','원문게시등록일시는 현행 TIMESTAMP WITH TIME ZONE 및 SYSTIMESTAMP 유지안. 참고의 시간대 없는 타입으로 임의 변환하지 않음.','도메인/인포타입 승인 후 기준 시간대·변환 방식 확정'),
      ('현재 온톨로지 배선','repository.py가 5테이블에 한 owner와 고정명을 사용한다. 운영 Gold 3표/Agent 2표 분리와 새 이름·컬럼은 설정만으로 반영되지 않는다.','개별 테이블/컬럼 매핑과 게시·활성·감사 동일 트랜잭션 보존 구현 필요'),
      ('상태','MAIN111은 코드·스키마 반영 및 기본 OFF. 운영 원문/온톨로지 데이터 적재·메타 신청·DBA 생성·현장 조회는 이번 작업에서 수행하지 않음.','WORKFLOW_CONNECTED_20261028.md'),
      ('이전 초안 정리','2026-10-27 R1의 9표에는 파일 보관·실행 상태가 포함됐다. 이번 본표는 골드 후보 7표만 승계하고 신규 게시 3표를 추가.','이전 원본·개발계 요청 목록은 수정하지 않음'),
      ('녹취 해석','사용자가 붙여넣은 녹취의 요지를 시간대별로 정리했다. 음성 원본은 없으며 m바차·ETF·TS 등 불명확 표기를 확정 기술값으로 사용하지 않음.','VARCHAR2/한글 기준은 기존 제공 가이드와 대조; TS는 확인 필요'),
      ('미포함 후속','LLM Wiki·숏컷·별칭의 독립 운영 물리 모델은 후속 설계. 기존 검색 행의 용어·정의·참조 조회와 중복하지 않음.','제외후속 시트'),
      ('제약 기준','PK 10, FK 3, CHECK 6(현행 5+여부형 신규안 1), 추가 인덱스 5. 본문조각 여부와 시간대·변경순번의 의미 차이 유지.','제약인덱스 및 검증 JSON'),
    ]
    for r in rows:rw.append(r)
    ew=w.create_sheet('작성근거');ew.append(['자료','용도','SHA-256 / 출처'])
    for p in sources:ew.append([str(p.relative_to(ROOT)),'양식·현재 계약·이전 작성 내용 정적 대조',before[str(p.relative_to(ROOT))]])
    ew.append(['사용자 제공 녹취 00:00–30:27','이번 명명·타입·등록 피드백; 피드백반영 시트에 구간별 연결','이 대화의 사용자 메시지; 원음 미제공'])
    ew.append(['사용자 후속: 3번·5번 모두 / 2번 참고용','대상 과제와 공동 사용 범위','이 대화의 사용자 메시지'])

    layouts={
      '테이블':[16,12,30,33,28,64,58,64],
      '컬럼':[16,12,32,25,8,27,28,26,27,62,55,68,6,76,12],
      'Bizmeta':[6,16,12,32,28,62,14,76,62,28],
      '개발운영매핑':[16,12,27,25,27,12,32,28,27,100,40],
      '표준용어검토':[6,28,28,42,12,28,52,86,12,12,78,34,28,20],
      '피드백반영':[8,24,60,94,42,40],
      '제외후속':[18,42,12,40,98,48],
      '제약인덱스':[32,12,35,85,72,32,60],
      '상세Description':[32,76,64,56,65,62,95,82,68,76,40,100],
      '등록관리':[16,32,44,18,22,22,22,22,18,20,24,30,26],
      '작성기준':[26,120,88],
      '작성근거':[110,65,90],
    }
    for s in w:format_sheet(s,layouts[s.title],original_styles.get(s.title))
    # The two original header sequences and yellow review column are preserved.
    for row in cw.iter_rows(min_row=2):
        for i in (6,7):row[i].fill=PatternFill('solid',fgColor='E7F1EC')
        if row[5].value!=row[8].value:row[8].fill=PatternFill('solid',fgColor='FFF0CB')
    for row in tw.iter_rows(min_row=9):
        for c in row:c.fill=PatternFill('solid',fgColor='E8F0FA')
    w.properties.title='3번·5번 법률 에이전트 골드 테이블·컬럼 마스터'
    w.properties.subject='기존 골드 후보와 온톨로지 게시 지식 통합 / 제공 피드백 반영'
    w.properties.creator='법률 에이전트 설계'
    w.properties.description='공통 10테이블·49컬럼 검토본. 2번 ELS는 참고 양식. 메타 승인·DB 생성 미수행.'
    w.active=0
    w.save(OUT)
    (HERE/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
    validate(w,model,original_headers,before,prefix,confirmed)
    preview(w)
    print(json.dumps({'file':str(OUT),'tables':len(model),'columns':sum(len(t['columns']) for t in model.values()),'terms':len(terms),'sheets':w.sheetnames},ensure_ascii=False))

def validate(w,model,headers,before,prefix,confirmed):
    loaded=openpyxl.load_workbook(OUT)
    with zipfile.ZipFile(OUT) as z:assert z.testzip() is None
    assert loaded['테이블'].max_row==11 and loaded['컬럼'].max_row==50
    for s in ('테이블','컬럼'):assert [c.value for c in loaded[s][1]]==headers[s]
    assert len(model)==10 and sum(len(t['columns']) for t in model.values())==49
    assert sum(len(t['columns']) for k,t in model.items() if k in GOLD_KEYS)==36
    assert sum(len(t['columns']) for k,t in model.items() if k not in GOLD_KEYS)==13
    term_by_name={};seen=set()
    for key,t in model.items():
        assert t['name'] not in seen;seen.add(t['name'])
        assert re.fullmatch('[A-Z][A-Z0-9_]{0,29}',t['name'])
        assert not t['name'].endswith(('_G','_S','_A'))
        names=[c['name'] for c in t['columns']]
        assert len(set(names))==len(names)
        assert set(t['pk'])<=set(names)
        for c in t['columns']:
            assert re.fullmatch('[A-Z][A-Z0-9_]{0,29}',c['name'])
            assert len(c['logical'].encode())<=30,(c['logical'],len(c['logical'].encode()))
            assert c['logical'].endswith(c['domain'])
            assert c['name'].endswith({'ID':'ID','내용':'CTNT','값':'VALU','일시':'DATE_TIME','여부':'YN','명':'NAME','순번':'SEQ_NO','번호':'NO'}[c['domain']])
            signature=(c['logical'],c['type'],c['domain'])
            assert term_by_name.setdefault(c['name'],signature)==signature
            assert 'NVARCHAR' not in c['type']
            if c['current']=='DOC_ID':assert c['name']=='LGL_DOC_ID' and c['type']=='VARCHAR2(512 BYTE)'
            if c['current']=='UNIT_ID':assert c['name']=='LGL_UNIT_ID'
        for fk in t['fks']:
            assert set(fk['columns'])<=set(names)
            assert set(fk['target_columns'])<=set(c['name'] for c in model[fk['target']]['columns'])
        if key in GOLD_KEYS:
            src=MAPPING['tables'][key]
            assert len(src['columns'])==len(t['columns'])
            for c,original in zip(t['columns'],src['columns'].values()):
                assert (c['current'],c['current_type'],c['nullable'])==(original['name'],original['type'],original['nullable'])
    # Independent DDL extraction for the existing 36 columns, including time-zone default.
    base_sql=(BASE/'01_CREATE_TABLES.sql').read_text()
    for k in GOLD_KEYS:
        t=model[k]
        body=re.search(r'CREATE TABLE SIDDS\.'+t['source_name']+r' \((.*?)\n\);',base_sql,re.S).group(1)
        actual=[]
        for line in body.splitlines():
            m=re.match(r'\s*(\w+) (VARCHAR2\(\d+ BYTE\)|NUMBER\(\d+\)|CLOB|TIMESTAMP WITH TIME ZONE)(?: DEFAULT (\w+))?( NOT NULL)?[,\s]*$',line)
            if m:actual.append((m[1],m[2],not bool(m[4]),m[3]))
        assert actual==[(c['current'],c['current_type'],c['nullable'],c['default']) for c in t['columns']]
        actual_pk=re.search(r'PRIMARY KEY \(([^)]+)\)',body)[1].split(',')
        assert actual_pk==[c['current'] for c in t['columns'] if c['name'] in t['pk']]
    # Independent DDL extraction for newly added ontology rows.
    sql=(ONT/'01_CREATE_TABLES.sql').read_text()
    for k in ('publication','head','anchor'):
        t=model[k]
        body=re.search(r'CREATE TABLE SIDDA\.'+t['source_name']+r' \((.*?)\n\);',sql,re.S).group(1)
        actual=[]
        for line in body.splitlines():
            m=re.match(r'\s*(\w+) (VARCHAR2\(\d+ BYTE\)|NUMBER\(\d+\)|CLOB)( NOT NULL)?[,\s]*$',line)
            if m:actual.append((m[1],m[2],not bool(m[3])))
        assert actual==[(c['current'],c['current_type'],c['nullable']) for c in t['columns']]
        actual_pk=re.search(r'PRIMARY KEY \(([^)]+)\)',body)[1].split(',')
        assert actual_pk==[c['current'] for c in t['columns'] if c['name'] in t['pk']]
    counts={'pk':len(model),'check':sum(len(t['checks']) for t in model.values()),'fk':sum(len(t['fks']) for t in model.values()),'additional_index':sum(len(t['indexes']) for t in model.values())}
    assert counts==dict(pk=10,check=6,fk=3,additional_index=5),counts
    for row in loaded['제약인덱스'].iter_rows(min_row=2):assert len(row[2].value.encode())<=30,row[2].value
    assert all(sha(ROOT/p)==v for p,v in before.items())
    assert all(c.data_type!='f' for s in loaded for row in s for c in row)
    assert not loaded._external_links
    assert all(s.freeze_panes and s.auto_filter.ref for s in loaded)
    overflow=[(s.title,n,d.height) for s in loaded for n,d in s.row_dimensions.items() if d.height and d.height>409]
    assert not overflow,overflow
    result=dict(status='PASS_DOCUMENT_CHECK',workbook=OUT.name,sha256=sha(OUT),bytes=OUT.stat().st_size,agent_numbers=[prefix+'03',prefix+'05'],agent_prefix_confirmed=confirmed,shared_tables=10,columns=49,existing_tables=7,existing_columns=36,ontology_tables=3,ontology_columns=13,excluded_tables=4,excluded_columns=20,unique_terms=loaded['표준용어검토'].max_row-1,constraints=counts,headers_match_reference=True,current_columns_match_contract=True,logical_names_utf8_bytes_max=max(len(c['logical'].encode()) for t in model.values() for c in t['columns']),source_hashes_unchanged=True,database_access=False,product_modified=False,metadata_approval=False,official_dictionary_checked=False,native_excel_render=False,source_files=before)
    (HERE/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

def draw_preview(ws,columns,rows,path,title):
    widths=[185,275,245,250,600] if ws.title=='테이블' else [240,285,245,260,560]
    font=ImageFont.truetype(FONT_PATH,18);bold=ImageFont.truetype(FONT_BOLD_PATH,18)
    data=[[ws.cell(r,c).value for c in columns] for r in rows]
    heights=[]
    for row in data:heights.append(max(54,max(len(wrap(v,widths[i]-24,font)) for i,v in enumerate(row))*27+24))
    im=Image.new('RGB',(sum(widths)+48,sum(heights)+130),'white');d=ImageDraw.Draw(im)
    d.text((24,20),title,font=ImageFont.truetype(FONT_BOLD_PATH,28),fill='#20354D')
    d.text((24,65),'엑셀 주요 열 미리보기 · 전체 정의와 검토 내용은 XLSX에 포함',font=font,fill='#59697C')
    y=110
    for i,(row,h) in enumerate(zip(data,heights)):
        x=24;bg='#20354D' if i==0 else ('#E9F0F7' if i%2 else '#F7F9FC')
        for j,(v,width) in enumerate(zip(row,widths)):
            d.rectangle((x,y,x+width,y+h),fill=bg,outline='#CFD9E4')
            for n,line in enumerate(wrap(v,width-24,bold if i==0 else font)):d.text((x+12,y+12+27*n),line,font=bold if i==0 else font,fill='white' if i==0 else '#20354D')
            x+=width
        y+=h
    im.save(path)

def preview(w):
    draw_preview(w['테이블'],[1,4,5,3,6],list(range(1,12)),HERE/'테이블_미리보기.png','법률 에이전트 3·5 | 공통 골드 10테이블')
    draw_preview(w['컬럼'],[4,7,8,9,10],[1,3,4,19,23,39,42,45,47],HERE/'컬럼_미리보기.png','피드백 반영 | 주요 컬럼 검토')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prefix',default='A',choices=['A','B']);p.add_argument('--confirmed',action='store_true');args=p.parse_args()
    main(args.prefix,args.confirmed)
