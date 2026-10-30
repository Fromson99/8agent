"""Build review-only Gold R11 documents; never connect to or modify a database."""
from pathlib import Path
from copy import deepcopy
import csv
import hashlib
import json
import re
import shutil
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
R10 = OUT.parent / 'DATAIKU_GOLD_REGISTER_20261028_R10'
OLD = OUT.parent / 'DATAIKU_GOLD_MASTER_20261028_R3/model.json'
STATUS = '설계 후보 · 표준/모델 미승인 · DB/제품 미반영'
NAMES = ['DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST','SRCH_POST','SRCH_ROW','SRCH_CHNL','ONTL_POST','ONTL_HEAD','ONTL_ANC']
KEYS = ['document','source_unit','block_payload','source_release','query_release','query_row','query_active','publication','head','anchor']
SHORT = ['문서판본','문서구조','원문본문','원문게시','조회게시','검색관계','조회채널','온톨로지게시','온톨로지선택','원문지식연결']
BASE_HEADERS = ['순번','논리명(한글)','물리명(영문)','도메인명','수식어 단어','데이터 타입','길이 / 정밀도','PK 순서','필수','물리 제약조건','컬럼정의','문자열 한글 포함 여부']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v): Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def col(name,logical,typ,definition,source,*,pk=0,required=True,rule='',korean='N',domain=None):
    if typ.startswith('VARCHAR2'):
        dtype='VARCHAR2';size=re.search(r'\((.*)\)',typ)[1]
    elif typ.startswith('NUMBER'):
        dtype='NUMBER';size='정밀도 30 / 소수자리 0'
    elif typ.startswith('TIMESTAMP'):
        dtype='TIMESTAMP\nWITH TIME ZONE';size='소수초 정밀도 6'
    elif typ.startswith('VECTOR'):
        dtype='VECTOR';size='가변 차원 / FLOAT32'
    else: dtype=typ;size='가변'
    domain=domain or ('ID' if name.endswith('_ID') else '값' if name.endswith('_VALU') else '명' if name.endswith('_NAME') else '내용' if dtype=='CLOB' else '일시' if dtype.startswith('TIMESTAMP') else '수' if name.endswith('_CNT') else '번호')
    words=logical[:-len(domain)] if logical.endswith(domain) else logical
    return dict(name=name,logical=logical,type=typ,dtype=dtype,size=size,domain=domain,words=words,pk=pk,required=required,definition=definition,source=source,rule=rule,korean=korean,change='R11 신규',default=None)

def new_table(suffix,short,logical,definition,columns,source,phase):
    return dict(suffix=suffix,short=short,logical=logical,definition=definition,columns=columns,source=source,phase=phase,change='R11 신규',indexes=[],kind='SNAPSHOT',process='Dataiku가 원천 판본을 고정해 구성·검증하고 봉인된 게시본만 사용 대상으로 전환한다.')

def load_base():
    book=load_workbook(R10/'법률에이전트_B03_골드등록용_테이블별_R10.xlsx',read_only=True,data_only=True)
    old=json.loads(OLD.read_text());tables=[]
    for i,sheet in enumerate(list(book)[1:]):
        prior=old[KEYS[i]];columns=[]
        rows=[r for r in sheet.iter_rows(min_row=7,values_only=True) if isinstance(r[0],int)]
        for r,orig in zip(rows,prior['columns'],strict=True):
            dt=str(r[5]).replace('\n',' ')
            typ=(f'VARCHAR2({r[6]})' if dt=='VARCHAR2' else f'CHAR({r[6]})' if dt=='CHAR' else 'NUMBER(30,0)' if dt=='NUMBER' else 'TIMESTAMP(6) WITH TIME ZONE' if dt.startswith('TIMESTAMP') else dt)
            rule='; '.join(x for x in str(r[9]).splitlines() if x.startswith(('CHECK','FK')))
            rule=rule.replace('CHECK ', '코드로 확인: ').replace('FK → IDD_B03_LGL_', '같은 명명안의 논리 참조 → ')
            columns.append(dict(name=r[2],logical=r[1],domain=r[3],words=r[4],type=typ,dtype=r[5],size=r[6],pk=r[7] if isinstance(r[7],int) else 0,required=r[8]=='Y',definition=r[10],korean=r[11],source=f"{prior['source_owner']}.{prior['source_name']}.{orig['current']}",rule=rule,change='R10 정의·타입·필수·PK 유지; 물리 FK/CHECK는 코드 검증으로 이관' if rule else 'R10 유지',default='SYSTIMESTAMP' if 'DEFAULT SYSTIMESTAMP' in str(r[9]) else None))
        tables.append(dict(suffix=NAMES[i],short=SHORT[i],logical=str(sheet['A1'].value).split(': ',1)[1],definition=str(sheet['A3'].value).split(': ',1)[1],columns=columns,source=prior['source_owner']+'.'+prior['source_name'],phase='A · 기본 골드',change='기존 모델 유지·소프트 FK 전환',indexes=[],kind=prior['kind'],process=prior['process']))
    return tables

def model():
    ts=load_base();by={t['suffix']:t for t in ts}
    by['DOC_BLK']['columns'].append(col('BODY_SLC_ORD_NO','본문조각순서번호','NUMBER(30,0)','문서 판본 안에서 본문 조각이 나타나는 순서를 나타내는 번호이다. 본문조각ID의 문자열 값은 별도로 유지한다.','현재 원문 block 순서; 현행 숫자 block_id 정렬과 동등성 확인',rule='문서·판본 내 순서 유일성, 0 이상; 숫자 ID 추정이나 문자열 자르기 금지'))
    by['DOC_BLK']['change']='본문조각순서번호 1열 추가; 함수 기반 숫자 정렬 의존 축소'
    by['SRCH_POST']['columns'] += [
        col('DOC_POST_HASH_VALU','원문게시해시값','VARCHAR2(100 BYTE)','조회 게시본이 사용하는 원문 게시본의 식별값이다.','현행 manifest.source_release_id',rule='SRC_POST의 PK 존재 및 manifest 값과 일치'),
        col('MNFST_HASH_VALU','명세해시값','VARCHAR2(100 BYTE)','조회 게시본이 사용하는 데이터 구성 버전의 식별값이다.','현행 manifest.dataset_version',rule='SRC_POST.MNFST_HASH_VALU 및 manifest 값과 일치')]
    by['SRCH_POST']['change']='원문 게시·데이터 판본 연결 2열 추출; 기존 manifest 원문·해시 보존'
    vpost=new_table('VCTR_POST','벡터게시','벡터게시내역','동일 원문 판본과 임베딩 모델 설정으로 생성하여 검증을 마친 벡터 묶음을 관리한다. 한 건은 불변 벡터 게시본 한 건이다.',[
        col('VCTR_POST_ID','벡터게시ID','VARCHAR2(100 BYTE)','검증한 벡터 게시본을 구분하는 식별값이다.','LGL_VCTR_SET_S.PUB_ID',pk=1,rule='기존 canonical manifest digest 계약 유지; 새 조회 게시 ID 결속 시 새 ID'),
        col('RFRN_POST_HASH_VALU','조회게시해시값','VARCHAR2(100 BYTE)','벡터 생성의 기준이 된 조회 게시본의 식별값이다.','PAYLOAD_JSON.manifest.query_id',rule='SRCH_POST 존재; 원문·판본 결속 일치'),
        col('MNFST_HASH_VALU','명세해시값','VARCHAR2(100 BYTE)','벡터가 참조하는 원문 데이터 구성 버전의 식별값이다.','PAYLOAD_JSON.manifest.dataset_version',rule='조회 게시본의 명세해시값과 동일'),
        col('MODL_PRFL_HASH_VALU','모델프로필해시값','VARCHAR2(100 BYTE)','모델·불변 버전·차원·정규화·거리 기준·분할 설정을 구분하는 해시값이다.','manifest.profile의 기존 정규화 digest',rule='차원만 같다는 이유로 다른 모델과 혼용 금지'),
        col('VCTR_CNT','벡터수','NUMBER(30,0)','검증을 마친 게시본에 속하는 벡터의 수이다.','검증 완료 ITEM 실제 건수',rule='실제 행 수와 일치; 1 이상'),
        col('VCTR_POST_IFMN_CTNT','벡터게시정보내용','CLOB','벡터 게시본의 원문 구성, 모델 설정, 분할 기준 및 검증 정보를 담은 내용이다.','R3 manifest 및 완료 검증 정보; BUILDING/lease는 Agent 제어로 분리',rule='중복 키 없는 JSON; 기존 manifest·hash 의미 보존',korean='Y',domain='내용'),
        col('RGSN_AITM','등록일시','TIMESTAMP(6) WITH TIME ZONE','검증한 게시본이 등록된 일시이다.','게시 봉인 시각',rule='시간대 보존',domain='일시')],
        'SIDDS.LGL_VCTR_SET_S + 완료 검증 영수증','A · 벡터 포함');ts.append(vpost)
    ts.append(new_table('VCTR_ITEM','원문벡터','원문구간벡터내역','원문의 일정 구간에서 생성한 벡터와 해당 구간의 연결 정보를 관리한다. 한 건은 벡터 게시본 안의 원문 구간 한 건이다.',[
        col('VCTR_POST_ID','벡터게시ID','VARCHAR2(100 BYTE)','벡터가 속한 게시본의 식별값이다.','LGL_VCTR_ITEM_S.PUB_ID',pk=1,rule='게시 완료 시 VCTR_POST 존재'),
        col('VCTR_SEG_ID','벡터구간ID','VARCHAR2(100 BYTE)','원문 구간과 생성 입력을 구분하는 식별값이다.','LGL_VCTR_ITEM_S.SEG_ID',pk=2,rule='기존 digest([query_release,meta]) 재현'),
        col('DOC_ID','문서ID','VARCHAR2(1000 BYTE)','벡터 생성에 사용한 원문 문서의 식별값이다.','META_JSON.document_id',rule='해당 게시본 판본의 DOC_VER 존재; JSON과 일치',korean='Y'),
        col('SRC_UNIT_ID','원문단위ID','VARCHAR2(1000 BYTE)','검색 결과를 묶고 원문을 읽는 기준이 되는 원문 단위의 식별값이다.','META_JSON.source_id',rule='navigation source.id; 문서 구조의 STRC_UNIT_ID와 구분; 현재 권한으로 원문 조회',korean='Y'),
        col('INPT_HASH_VALU','입력해시값','VARCHAR2(100 BYTE)','벡터 생성에 실제 사용한 입력 내용의 해시값이다.','META_JSON.input_sha256',rule='모델 프로필·입력 해시 둘 다 같을 때만 벡터 재사용'),
        col('VCTR_META_CTNT','벡터메타정보내용','CLOB','원문 구조·본문 조각·구간 위치와 원문 및 입력 확인값을 담은 내용이다.','LGL_VCTR_ITEM_S.META_JSON 전체',rule='unit_id/block_id/start/end/source_sha256/block_sha256/input_sha256 모두 보존; 일반 컬럼과 일치',korean='Y',domain='내용'),
        col('EMBD_VCTR_VALU','임베딩벡터값','VECTOR(*,FLOAT32)','원문 구간의 의미를 임베딩 모델로 표현한 숫자 배열이다.','LGL_VCTR_ITEM_S.EMBEDDING',rule='실제 모델 차원·FLOAT32·유한값·0 아닌 norm·L2 정규화 확인',domain='값',korean='해당 없음')],
        'SIDDS.LGL_VCTR_ITEM_S','A · 벡터 포함'))
    ts.append(new_table('VCTR_HEAD','벡터선택','벡터게시선택내역','조회 게시본별로 현재 사용할 벡터 게시본과 변경 순서를 관리한다. 한 건은 조회 게시본 한 건의 벡터 선택 상태이다.',[
        col('RFRN_POST_HASH_VALU','조회게시해시값','VARCHAR2(100 BYTE)','벡터 선택의 기준이 되는 조회 게시본 식별값이다.','R3 활성 게시본 manifest.query_id',pk=1,rule='SRCH_POST 존재; 조회 게시본당 HEAD 1행'),
        col('VCTR_POST_ID','벡터게시ID','VARCHAR2(100 BYTE)','현재 선택한 벡터 게시본의 식별값이다. 선택이 없으면 비어 있다.','R3 active_revision이 있는 PUB_ID',required=False,rule='NULL이면 벡터 비활성; 대상 VCTR_POST의 조회 게시 ID 일치'),
        col('CHAN_NO','변경순번','NUMBER(30,0)','벡터 게시본의 선택 상태가 바뀔 때마다 증가하는 순번이다.','R3 active_revision; 신규 비활성 0',rule='0 이상; 활성 시 1 이상; 이전 ID+순번 CAS 및 증가; A→B→A도 증가')],
        'R3 PAYLOAD_JSON.active_revision/manifest.query_id를 명시 열로 분리','A · 벡터 포함'))
    ts[-1]['kind']='MASTER'
    ts.append(new_table('FTS_UNIT','전문검색단위','전문검색단위내역','전문검색의 단위별 문서·원문 위치·길이 및 적중 상세를 관리한다. 한 건은 조회 게시본 안의 검색 단위 한 건이다.',[
        col('RFRN_POST_HASH_VALU','조회게시해시값','VARCHAR2(100 BYTE)','전문검색 데이터가 속하는 조회 게시본의 식별값이다.','현행 query release',pk=1),
        col('FTS_UNIT_KEY_VALU','전문검색단위키값','VARCHAR2(1000 BYTE)','기존 전문검색 단위를 구분하고 동점 순서를 결정하는 키값이다.','unit.key / unit_fts_length.key 원문 그대로',pk=2,rule='기존 Oracle 이관 성공 범위는 512 BYTE 이내; 확대는 별도 검증; hash로 바꿔 동점 순서 변경 금지',korean='Y'),
        col('DOC_ID','문서ID','VARCHAR2(1000 BYTE)','검색 단위가 속하는 문서의 식별값이다.','unit.document_id',rule='조회 게시본 판본의 문서 존재; 현재 권한 필터 적용',korean='Y'),
        col('SRC_UNIT_ID','원문단위ID','VARCHAR2(1000 BYTE)','검색 단위를 원문 읽기 위치에 연결하는 식별값이다.','unit.source_id',rule='navigation source.id와 동일',korean='Y'),
        col('TOKEN_CNT','토큰수','NUMBER(30,0)','해당 검색 단위의 순위 계산에 사용하는 토큰 수이다.','unit_fts_length.length',rule='0 이상; tokenizer/positions와 일치'),
        col('ROW_HASH_VALU','행해시값','VARCHAR2(100 BYTE)','검색 단위의 내용과 위치 정보가 변하지 않았는지 확인하는 해시값이다.','신규 projection-v2 canonical row hash',rule='기존 unit 논리 payload/hash도 manifest에 결속; 새 논리 해시로 과거 해시를 대체하지 않음'),
        col('FTS_UNIT_IFMN_CTNT','전문검색단위정보내용','CLOB','검색 단위의 표시·원문 연결·적중 상세를 담은 내용이다.','기존 unit.json 전체',rule='기존 hit payload 전체 보존; 선택 페이지에서만 읽기',korean='Y',domain='내용')],
        'SRCH_ROW의 unit·unit_fts_length 논리 행','B · 전문검색 전용 투영'))
    ts.append(new_table('FTS_POST','전문검색색인','전문검색토큰위치내역','토큰이 등장하는 검색 단위와 위치를 관리한다. 한 건은 조회 게시본·토큰·검색 단위·검색 필드 조합 한 건이다.',[
        col('RFRN_POST_HASH_VALU','조회게시해시값','VARCHAR2(100 BYTE)','전문검색 색인이 속하는 조회 게시본의 식별값이다.','query release',pk=1),
        col('TOKEN_VALU','토큰값','VARCHAR2(1000 BYTE)','색인에서 실제 사용하는 검색 토큰의 문자열 값이다.','unit_fts_posting.token',pk=2,rule='기존 tokenizer의 원형 보존; 원천 512 BYTE 제한을 조용히 완화하거나 자르지 않음; 대상 collation 확인',korean='Y'),
        col('FTS_UNIT_KEY_VALU','전문검색단위키값','VARCHAR2(1000 BYTE)','토큰이 등장하는 검색 단위의 키값이다.','unit_fts_posting.key',pk=3,korean='Y'),
        col('FTS_FLD_NAME','전문검색필드명','VARCHAR2(100 BYTE)','토큰 위치를 구분하는 원천 검색 필드의 이름이다.','unit_fts_posting.column',pk=4,rule='원천 col 보존; 현재 body 한 필드 계약'),
        col('TERM_FREQ','토큰출현수','NUMBER(30,0)','해당 검색 단위와 필드에 토큰이 나타난 횟수이다.','unit_fts_posting.tf',rule='1 이상; 위치 배열 길이와 동일'),
        col('POS_LIST_CTNT','토큰위치목록내용','CLOB','문구 일치 판정에 사용하는 토큰 위치의 정렬된 목록이다.','unit_fts_posting.positions',rule='정수·0 이상·순서·중복 계약 보존; 선택 토큰에 한해 JSON_TABLE 확장',domain='내용'),
        col('ROW_HASH_VALU','행해시값','VARCHAR2(100 BYTE)','토큰과 검색 단위 및 위치가 변하지 않았는지 확인하는 해시값이다.','신규 projection-v2 canonical row hash',rule='기존 posting 논리 payload 대조 후 투영 hash 생성')],
        'SRCH_ROW의 unit_fts_posting 논리 행','B · 전문검색 전용 투영'))
    ts.append(new_table('FTS_STAT','전문검색통계','전문검색통계내역','전문검색 순위 계산에 사용하는 전체 색인 통계와 토큰화 설정을 관리한다. 한 건은 조회 게시본의 단위 전문검색 색인 한 건이다.',[
        col('RFRN_POST_HASH_VALU','조회게시해시값','VARCHAR2(100 BYTE)','통계가 속하는 조회 게시본의 식별값이다.','query release',pk=1),
        col('FTS_UNIT_CNT','전문검색단위수','NUMBER(30,0)','해당 전문검색 색인의 전체 검색 단위 수이다.','unit_fts_stats.documents',rule='법령 문서 수와 다름; 접근권한 필터 전 기존 전체 통계 보존'),
        col('TOKEN_CNT','토큰수','NUMBER(30,0)','해당 색인 전체의 토큰 수이다.','unit_fts_stats.tokens',rule='단위 길이 합과 기존 통계 일치'),
        col('FTS_PRFL_CTNT','전문검색프로필내용','CLOB','토큰화·정규화·필드·구문·순위 계산과 색인 판본을 재현하는 설정이다.','기존 fulltext manifest 및 FTS5 unicode61/PeCab 구축 계약',rule='PeCab 구축 입력과 질의 unicode61 경계를 보존; BM25 상수·동점 순서·global df 기준 보존',korean='Y',domain='내용'),
        col('ROW_HASH_VALU','행해시값','VARCHAR2(100 BYTE)','통계와 검색 설정이 변하지 않았는지 확인하는 해시값이다.','신규 projection-v2 canonical row hash',rule='실제 집계와 manifest 결속')],
        'SRCH_ROW의 unit_fts_stats + fulltext manifest','B · 전문검색 전용 투영'))
    by={t['suffix']:t for t in ts}
    indexes={
      'DOC_UNIT':[['MNFST_HASH_VALU','DOC_ID','UPPR_STRC_UNIT_ID','STRC_UNIT_ID']],
      'DOC_BLK':[['MNFST_HASH_VALU','DOC_ID','BODY_SLC_ORD_NO'],['MNFST_HASH_VALU','DOC_ID','STRC_UNIT_ID','BODY_SLC_ORD_NO']],
      'SRC_POST':[['MNFST_HASH_VALU','DOC_POST_HASH_VALU']],
      'SRCH_POST':[['DOC_POST_HASH_VALU','RFRN_POST_HASH_VALU']],
      'SRCH_ROW':[['RFRN_POST_HASH_VALU','RFRN_DTA_TYPE_VALU',x] for x in ['RFRN_DTA_IDNF_CTNT','BLNG_DTA_IDNF_CTNT','TAGT_DTA_IDNF_CTNT','DOC_ID']],
      'ONTL_POST':[['CNCP_GROP_ID','WORK_VER_NO']],
      'ONTL_HEAD':[['ONTL_POST_ID','CNCP_GROP_ID']],
      'ONTL_ANC':[['DOC_LCT_HASH_VALU','ONTL_POST_ID']],
      'VCTR_POST':[['RFRN_POST_HASH_VALU','MODL_PRFL_HASH_VALU','VCTR_POST_ID']],
      'VCTR_ITEM':[['VCTR_POST_ID','DOC_ID','SRC_UNIT_ID','VCTR_SEG_ID']],
      'FTS_UNIT':[['RFRN_POST_HASH_VALU','DOC_ID','SRC_UNIT_ID','FTS_UNIT_KEY_VALU']],
      'FTS_POST':[['RFRN_POST_HASH_VALU','FTS_UNIT_KEY_VALU','TOKEN_VALU','FTS_FLD_NAME']],
    }
    for suffix,ix in indexes.items():by[suffix]['indexes']=ix
    return ts

RELATIONS = [
 ('DOC_UNIT','MNFST_HASH_VALU,DOC_ID','DOC_VER','MNFST_HASH_VALU,DOC_ID'),
 ('DOC_UNIT','MNFST_HASH_VALU,DOC_ID,UPPR_STRC_UNIT_ID','DOC_UNIT','MNFST_HASH_VALU,DOC_ID,STRC_UNIT_ID'),
 ('DOC_BLK','MNFST_HASH_VALU,DOC_ID','DOC_VER','MNFST_HASH_VALU,DOC_ID'),
 ('DOC_BLK','MNFST_HASH_VALU,DOC_ID,STRC_UNIT_ID','DOC_UNIT','MNFST_HASH_VALU,DOC_ID,STRC_UNIT_ID'),
 ('SRCH_POST','DOC_POST_HASH_VALU','SRC_POST','DOC_POST_HASH_VALU'),
 ('SRCH_ROW','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
 ('SRCH_CHNL','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
 ('ONTL_HEAD','ONTL_POST_ID','ONTL_POST','ONTL_POST_ID'),
 ('ONTL_ANC','ONTL_POST_ID','ONTL_POST','ONTL_POST_ID'),
 ('VCTR_POST','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
 ('VCTR_ITEM','VCTR_POST_ID','VCTR_POST','VCTR_POST_ID'),
 ('VCTR_HEAD','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
 ('VCTR_HEAD','VCTR_POST_ID','VCTR_POST','VCTR_POST_ID'),
 ('FTS_UNIT','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
 ('FTS_POST','RFRN_POST_HASH_VALU,FTS_UNIT_KEY_VALU','FTS_UNIT','RFRN_POST_HASH_VALU,FTS_UNIT_KEY_VALU'),
 ('FTS_STAT','RFRN_POST_HASH_VALU','SRCH_POST','RFRN_POST_HASH_VALU'),
]
# Human-readable Korean constraints; source/target fields above are machine-checked.
REL_TEXT = [
 ('필수','같은 판본의 문서가 존재해야 한다.'),('상위 ID가 있을 때','부모 누락·순환을 거절하고 루트는 NULL로 보존한다.'),
 ('필수','본문이 속한 같은 판본의 문서를 확인한다.'),('구조 ID가 있을 때','같은 문서·판본의 구조 단위를 확인한다.'),
 ('필수','원문 게시본 존재와 양쪽 명세해시값 일치를 확인한다.'),('게시 봉인 시 필수','행 종류별 건수·내용·manifest 해시를 확인한다.'),
 ('필수','완료된 게시본만 선택하며 이전 ID와 변경순번을 함께 비교한다.'),('게시 ID가 있을 때','개념그룹 일치도 확인한다. NULL은 선택 중지다.'),
 ('필수','원문 위치 해시와 게시본의 모든 근거를 대조한다.'),('필수','조회 게시본의 명세해시값과 일치해야 한다.'),
 ('게시 봉인 시 필수','건수·모델·입력·원문 구간을 모두 확인한다.'),('필수','조회 게시본마다 PK 1행으로 선택 상태를 관리한다.'),
 ('게시 ID가 있을 때','대상 벡터 게시본의 조회 게시 ID 일치와 CAS를 확인한다.'),('게시 봉인 시 필수','manifest가 선택한 전문검색 저장 계약과 일치해야 한다.'),
 ('필수','검색 단위 존재·위치·출현수·필드·문구 일치를 확인한다.'),('게시 봉인 시 필수','전체 단위 수·토큰 수·검색 설정이 일치해야 한다.'),
]

def relationships():
    out=[]
    for n,(r,txt) in enumerate(zip(RELATIONS,REL_TEXT,strict=True),1):
        a,ac,b,bc=r
        out.append(dict(id=f'R{n:02}',child=a,child_columns=ac.split(','),parent=b,parent_columns=bc.split(','),condition=txt[0],validation=txt[1],enforcement='SOFT · 코드 배치 검증; 물리 FK 없음'))
    return out

def setup(ws,title,subtitle,headers,widths):
    n=len(headers);ws.sheet_view.showGridLines=False
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=n);ws.cell(1,1,title)
    ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=n);ws.cell(2,1,subtitle)
    ws.row_dimensions[1].height=30;ws.row_dimensions[2].height=42
    ws.cell(1,1).font=Font(name='맑은 고딕',size=17,bold=True,color='17354A')
    ws.cell(2,1).font=Font(name='맑은 고딕',size=10,color='526777');ws.cell(2,1).alignment=Alignment(wrap_text=True,vertical='center')
    for i,(h,width) in enumerate(zip(headers,widths,strict=True),1):
        c=ws.cell(4,i,h);c.fill=PatternFill('solid',fgColor='17354A');c.font=Font(name='맑은 고딕',bold=True,color='FFFFFF',size=10);c.alignment=Alignment(wrap_text=True,vertical='center')
        ws.column_dimensions[get_column_letter(i)].width=width
    ws.row_dimensions[4].height=30;ws.freeze_panes='D5'
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.print_title_rows='1:4';ws.oddFooter.center.text='R11 · 설계 후보 · &P / &N'

def add_rows(ws,rows,heights=58):
    for row in rows:
        ws.append(row)
        n=ws.max_row;ws.row_dimensions[n].height=heights
        for cell in ws[n]:
            cell.font=Font(name='맑은 고딕',size=10,color='243D4B');cell.alignment=Alignment(vertical='top',wrap_text=True)
            cell.fill=PatternFill('solid',fgColor='EDF4F6' if n%2 else 'FFFFFF')
            cell.border=Border(bottom=Side(style='hair',color='D5E1E6'))
    ws.auto_filter.ref=f'A4:{get_column_letter(ws.max_column)}{ws.max_row}'
    ws.print_area=f'A1:{get_column_letter(ws.max_column)}{ws.max_row}'

def physical(c,pk):
    text='NOT NULL' if c['required'] else 'NULL 허용'
    if c['pk']:text+='\nPK ('+', '.join(pk)+')'
    if c.get('default'):text+='\nDEFAULT '+c['default']
    return text

def workbook(tables,rels,agent):
    w=Workbook();ws=w.active;ws.title='00_설계요약'
    setup(ws,'골드 레이어 재설계 R11',f'{agent} 명명안 | B03·B05 공통 논리모델 | {STATUS}', ['항목','설계 결정','적용 경계'],[25,90,85])
    add_rows(ws,[
        ['전체 범위',f'{len(tables)}개 테이블 · {sum(len(t["columns"]) for t in tables)}개 컬럼: 기존 10개 + 벡터 3개 + 전문검색 3개','A단계 13표 후 B단계 전문검색 3표를 연결한다. 최종 대상은 16표다.'],
        ['소프트 FK','연결 ID·PK·필수값 유지; 물리 FK/CHECK/추가 UNIQUE 제약은 만들지 않음','관계 유효성은 적재·봉인 시 배치 검사. 요청 권한·판본·원문 확인은 계속 수행.'],
        ['인덱스','PK용 X0_; 일반 B-tree X1_ 이후. 함수 인덱스 없음','PK 자체의 유일성은 유지. 전문 벡터 ANN 인덱스는 별도 기술·현장 승인 검토.'],
        ['벡터','Oracle native VECTOR 저장. DOC_ID·SRC_UNIT_ID는 일반 컬럼; 활성 선택은 별도 HEAD','정확 검색 기준선 유지. ANN은 기본 DDL에 포함하지 않음; 전체 규모 성능은 미측정.'],
        ['전문검색','토큰·검색 단위·통계 전용 투영. 기존 tokenizer·phrase·BM25·정렬 보존','페이지 재계산 제거는 추가 코드 작업; 표 생성만으로 해결되지 않음.'],
        ['상태·로그','질문·실행·임베딩 작업 잠금·부분 실패·검증 영수증은 Agent/Dataiku 작업 영역','Gold에는 재사용 지식, 불변 게시본, 서비스용 선택 포인터를 둔다.'],
        ['B03 / B05','같은 설계의 명명 선택안 두 파일. 공통 데이터를 두 벌 생성하라는 뜻이 아님','대표 등록 과제·공유 조회 권한·실제 owner는 승인 시 확정.'],
        ['기존 명명','R10의 B03/B05·ONTL·POST·100/1000 BYTE·업무 정의를 유지','신규 약어·도메인·VECTOR 타입과 기존 2250 BYTE 문서명 길이의 실제 적합성은 확인 필요.'],
        ['실행 상태','문서·DDL 템플릿·자체 일관성 검사만 작성','DB 생성·적재·모델 호출·MAIN/GENOS 변경·메일 발송 없음.'],
    ],72)
    overview=w.create_sheet('01_테이블목록');setup(overview,'테이블 목록',STATUS,['번호','엔티티명','테이블명 후보','구분','컬럼수','행 단위·정의','원천/현재','변경'],[8,24,34,25,10,75,46,65])
    for i,t in enumerate(tables,1):
        name=f'IDD_{agent}_LGL_'+t['suffix'];sheetname=f'{i+1:02}_{t["short"]}'
        add_rows(overview,[[i,t['logical'],name,t['phase'],len(t['columns']),t['definition'],t['source'],t['change']]],64)
        overview.cell(i+4,2).hyperlink=f"#'{sheetname}'!A1";overview.cell(i+4,2).font=Font(name='맑은 고딕',color='087C92',underline='single')
        s=w.create_sheet(sheetname);setup(s,t['logical']+' | '+name,STATUS+' | '+t['definition'],BASE_HEADERS,[7,24,32,12,24,22,22,9,8,44,70,15])
        pk=[c['name'] for c in sorted(t['columns'],key=lambda x:x['pk']) if c['pk']]
        add_rows(s,[[j,c['logical'],c['name'],c['domain'],c['words'],c['dtype'],c['size'],c['pk'] or '—','Y' if c['required'] else 'N',physical(c,pk),c['definition'],c['korean']] for j,c in enumerate(t['columns'],1)],78)
    s=w.create_sheet('18_인덱스');setup(s,'PK 및 일반 인덱스', '추가 UNIQUE·함수 인덱스 없음. 실제 인덱스 키 바이트 한도와 통계·실행계획은 현장에서 확인.', ['테이블','인덱스명 후보','종류','컬럼 순서','용도'],[34,36,20,100,55])
    rows=[]
    for t in tables:
        name=f'IDD_{agent}_LGL_'+t['suffix'];pk=[c['name'] for c in sorted(t['columns'],key=lambda x:x['pk']) if c['pk']]
        rows.append([name,'X0_'+name,'PK 기반',', '.join(pk),'행 식별·중복 방지·동시 최초 등록 충돌 검출'])
        for i,ix in enumerate(t['indexes'],1):rows.append([name,f'X{i}_'+name,'일반 B-tree',', '.join(ix),'판본을 먼저 제한한 연결·범위·조회키 검색; 사용 여부는 실제 SQL로 검증'])
    add_rows(s,rows,52)
    s=w.create_sheet('19_소프트FK');setup(s,'논리 관계와 코드 검증','물리 FK 생성 없음. 아래 직접 관계 외 판본 경유·다형 관계는 20_코드검증 시트에서 정의.', ['ID','출발 테이블','출발 컬럼','도착 테이블','도착 컬럼','조건','검증'],[8,30,65,30,65,24,80])
    add_rows(s,[[r['id'],f'IDD_{agent}_LGL_'+r['child'],', '.join(r['child_columns']),f'IDD_{agent}_LGL_'+r['parent'],', '.join(r['parent_columns']),r['condition'],r['validation']] for r in rels],64)
    s=w.create_sheet('20_코드검증');setup(s,'코드 검증·원천 매핑','문자열·원문 hash는 변환 없이 보존. 컬럼 확대는 소비자 입력 상한 확대를 뜻하지 않는다.', ['테이블','컬럼','원천/추출식','규칙','이행 메모'],[32,32,70,95,65])
    rows=[[t['suffix'],c['name'],c['source'],c['rule'] or '원천값·타입·필수·PK 계약 유지',c['change']] for t in tables for c in t['columns']]
    rows += [
      ['SRCH_ROW','다형 연결','manifest가 선언한 각 logical table 및 reference JSON','행 종류별 실제 키 의미를 사용. OWNER/TARGET 전체를 DOC_ID FK로 취급하지 않는다. UNRESOLVED·후보·누락 상태를 보존한다.','직접 원문 목표로 확정된 연결만 대상 존재를 강제; 미해결 관계를 자동 삭제하지 않음'],
      ['SRCH_ROW / VCTR_ITEM / FTS_UNIT','문서·원문 단위','게시본→명세해시값→DOC_VER/DOC_UNIT 및 navigation source','DOC_ID는 같은 판본 문서로 검증; SRC_UNIT_ID는 navigation source.id로 검증. STRC_UNIT_ID와 혼용 금지.','권한은 요청의 실제 allowed 문서와 교집합; Gold 등록 여부가 접근 허용을 뜻하지 않음'],
      ['ONTL_ANC','원문 판본 연결','DOC_ID + DOC_HASH_VALU + STRC_UNIT_ID','현재 요청의 문서 판본으로 anchor 재계산 후 원문·span 대조. 같은 ID의 다른 판본을 대체하지 않음.','DOC_HASH_VALU를 데이터 구성 MNFST_HASH_VALU와 혼용 금지'],
      ['게시·삭제','동시성','기존 Agent SQL 제어키 / Gold HEAD PK·revision','대용량 적재 중 장기 Gold 잠금 없음. 봉인 직전 단일 writer 확인, HEAD 짧은 CAS. 자동 물리 삭제 없음.','직접 DML 계정 통제·중단된 작업 lease 수동 확인·삭제와 게시의 동일 제어키 필요'],
    ]
    add_rows(s,rows,80)
    s=w.create_sheet('21_변경지도');setup(s,'구현 변경 지도','아래는 구현할 지점이며 현재 연결 완료를 뜻하지 않는다.', ['영역','현재 파일/진입점','제안 변경','완료 확인'],[23,75,100,85])
    add_rows(s,CHANGE_MAP,80)
    s=w.create_sheet('22_테이블정의');setup(s,'테이블 Description 작성안','소유 부서·보유기간·실제 스키마 미확정. 예시 SQL은 컬럼 확인용이며 서비스의 권한·봉인 필터는 별도 적용한다.', ['테이블','행 단위·PK','답할 수 있는 질문','포함·제외','기준 시점·보유기간','갱신·완료 기준','원천·산식','오너·주의','예시 조회'],[32,65,70,70,55,75,90,65,95])
    questions=['이 판본의 문서는 무엇인가?','이 원문 단위의 상위 구조는 무엇인가?','이 판본의 원문 조각과 순서는 무엇인가?','어떤 원문 묶음이 검증되어 게시됐는가?','이 조회 게시본은 어떤 원문 판본에 속하는가?','선택한 원문의 정의·참조·후보 연결은 무엇인가?','어떤 조회 게시본이 채널에 선택되어 있는가?','어떤 원문 근거의 지식 묶음이 게시됐는가?','이 개념그룹에서 사용할 게시본은 무엇인가?','현재 원문에 연결할 수 있는 지식은 무엇인가?','이 벡터 묶음은 어느 판본·모델에서 만들어졌는가?','선택한 원문 단위에 어떤 구간 벡터가 속하는가?','조회 게시본에서 사용할 벡터 묶음은 무엇인가?','검색 단위의 문서·원문 위치·길이는 무엇인가?','특정 토큰은 어느 검색 단위의 어떤 위치에 있는가?','이 전문검색 색인의 전체 길이와 토큰화 설정은 무엇인가?']
    rows=[]
    for t,question in zip(tables,questions,strict=True):
        name=f'IDD_{agent}_LGL_'+t['suffix'];pk=[c['name'] for c in sorted(t['columns'],key=lambda x:x['pk']) if c['pk']]
        selection=t['suffix'] in ('SRCH_CHNL','ONTL_HEAD','VCTR_HEAD')
        rows.append([name,t['definition']+' PK: '+', '.join(pk),question,'선택 포인터와 변경순번; 질문·실행 로그 제외' if selection else '검증된 재사용 데이터; 작성 중 상태·임베딩 작업 lease·질문/답변 로그 제외', '선택 시점의 고정 판본. 보유기간 미확정; 자동 삭제 없음', '선택 변경 시 짧은 CAS; 진행 요청의 기존 판본 유지' if selection else '원천/설정 변경 시 새 게시본; 일괄 검증 후 봉인. 갱신 시각·주기 미확정',t['source']+'; 파생식은 20_코드검증과 DESIGN.md 참조', '소유·관리 부서 미확정. 같은 이름의 다른 판본·모델 혼용 금지', 'SELECT '+', '.join(pk)+' FROM {{APPROVED_GOLD_OWNER}}.'+name+' WHERE '+pk[0]+' = :bound_key;'])
    add_rows(s,rows,108)
    w.properties.title=f'{agent} 골드 레이어 재설계 R11';w.properties.description=STATUS
    path=OUT/f'법률에이전트_{agent}_골드재설계_R11.xlsx';w.save(path);return path

CHANGE_MAP=[
 ['물리 매핑','semantic_runtime/physical_mapping.py; 00_SYSTEM/ORACLE/physical_mapping.yaml','Gold 전용 새 스키마 계약·B03/B05/owner 승인 매핑. physical FK/CHECK 필수 검사 대신 소프트 검증 영수증 확인. 기존 dev_silver 계약 유지.','테이블·열·PK·일반 인덱스 실제 대조. 기존 코드를 설정만 바꿔 사용하지 않음.'],
 ['원문·조회 적재','lawrag/pipeline/oracle_migration.py, oracle_query_publish.py, oracle_full_package.py','R10 타입/명칭·본문 순서·게시 판본 열·FTS 전용 투영을 writer/reader에 동시에 연결. schema fingerprint/manifest 새 버전.','원문·행/hash·BLOB 무손실·재개/부분 실패·부모 존재 배치 검사; 봉인 전 비노출.'],
 ['관계 탐색','semantic_runtime/oracle_query_db.py, oracle_query_index.py; legal_agent/definition_entry.py','ID 묶음·IN·JOIN 조건도 실제 일반 키 인덱스로 좁히는 전용 경로 추가. payload 전체 VIEW 생성 억제.','양방향·순환·미해결·NULL·긴 키·권한·판본 동일, Oracle SQL 왕복/계획/반환량 확인.'],
 ['전문검색','semantic_runtime/oracle_query_fulltext.py: UnitIndex._matches/_page','FTS_UNIT/POST/STAT 어댑터. 위치 JSON 확장은 선택 토큰만. 동일 질문의 적중 ID·점수를 요청 범위에서 재사용; 본문은 페이지 대상만.','global phrase df·BM25·동점 순서·total/cursor·허용 범위 동일; 무제한 캐시/조용한 상위K 자르기 금지.'],
 ['벡터 적재','vector_silver_20261029_r3의 payload/semantic_runtime/vector_publish.py 및 vector_silver/publisher.py','소프트FK+일반열+별도HEAD 소비자. BUILDING/lease/오류는 기존 Agent 제어와 Dataiku 원장으로 이동.','같은 profile+input hash 벡터만 재사용; 부분 적재 미노출, 중복·취소·재개·CAS·소비자 확인.'],
 ['벡터 조회','vector_silver_20261029_r3의 payload/semantic_runtime/initial_vector.py: Repository/ Retriever','Gold 매핑; DOC_ID/SRC_UNIT_ID 일반 열 필터; HEAD를 query ID로 PK 조회. 원문 단위별 최소 거리 집계 보존.','문서 권한·모델·차원·판본 일치; 정확 검색 결과 동일; ANN은 별도 정확도 검증.'],
 ['온톨로지','semantic_runtime/ontology_work/repository.py, runtime.py, schema.py; legal_agent/ontology_compiler.py','게시/HEAD/ANC는 Gold, WORK/EVT는 Agent로 매핑. 동일 Oracle transaction 가능한 계정 권한 확인.','한 DB transaction에 Gold 게시·HEAD와 Agent 감사 기록 결속. 불가능하면 별도 outbox 설계 전 운영 전환 금지.'],
 ['서빙·출시','service.py; oracle_query_service.py; 실제 GENOS workflow 경로','승인 mapping+manifest+code pin을 함께 선택. 신규 요청부터 전환; 진행 요청 판본 고정.','실제 Oracle/GENOS 확인 별도. 전체 원문·색인을 서빙 파일/SQLite로 내려받지 않음.'],
]

def ddl(tables,agent):
    lines=['-- REVIEW TEMPLATE ONLY. {{APPROVED_GOLD_OWNER}} must be an approved schema.', '-- No execution performed. New names/domains/types require metadata review.', '-- Gold R11: physical PK/NOT NULL; soft FK and CHECK rules are enforced by publishing code.', '-- No DROP, physical FK, CHECK, extra UNIQUE or function index. VECTOR ANN is separate.','']
    for t in tables:
        name=f'IDD_{agent}_LGL_'+t['suffix'];pk=[c['name'] for c in sorted(t['columns'],key=lambda x:x['pk']) if c['pk']]
        fields=[]
        for c in t['columns']:
            fields.append('  '+c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c.get('default') else '')+(' NOT NULL' if c['required'] else ''))
        fields.append('  CONSTRAINT X0_'+name+' PRIMARY KEY ('+', '.join(pk)+')')
        lines += ['-- '+t['logical']+' | '+t['phase'],'CREATE TABLE {{APPROVED_GOLD_OWNER}}.'+name+' (',',\n'.join(fields),');']
        for i,ix in enumerate(t['indexes'],1):lines.append(f'CREATE INDEX {{{{APPROVED_GOLD_OWNER}}}}.X{i}_{name} ON {{{{APPROVED_GOLD_OWNER}}}}.{name} ('+', '.join(ix)+');')
        lines.append('')
    (OUT/f'GOLD_{agent}_DDL_REVIEW.sql').write_text('\n'.join(lines),encoding='utf-8')

def validate(tables,rels,paths):
    by={t['suffix']:t for t in tables};checks=[]
    assert len(tables)==16
    assert sum(len(t['columns']) for t in tables[:10])==52
    assert sum(len(t['columns']) for t in tables)==88
    for t in tables:
        cs={c['name']:c for c in t['columns']};assert len(cs)==len(t['columns'])
        pks=sorted(c['pk'] for c in t['columns'] if c['pk']);assert pks==list(range(1,len(pks)+1)) and pks
        assert all(c['required'] for c in t['columns'] if c['pk'])
        for c in t['columns']:assert len(c['name'].encode())<=30
        for ix in t['indexes']:assert len(ix)==len(set(ix)) and set(ix)<=cs.keys()
        for a in ('B03','B05'):assert len(('X0_IDD_'+a+'_LGL_'+t['suffix']).encode())<=30
    for r in rels:
        child={c['name']:c for c in by[r['child']]['columns']};parent={c['name']:c for c in by[r['parent']]['columns']}
        assert len(r['child_columns'])==len(r['parent_columns'])
        assert r['parent_columns']==[c['name'] for c in sorted(parent.values(),key=lambda c:c['pk']) if c['pk']]
        for a,b in zip(r['child_columns'],r['parent_columns'],strict=True):assert child[a]['type']==parent[b]['type'],r
    # R10's 49 definitions, names, capacities, PKs and nullability must remain.
    baseline=load_base()
    for before,after in zip(baseline,tables[:10],strict=True):
        for a,b in zip(before['columns'],after['columns'][:len(before['columns'])],strict=True):
            for field in ('name','logical','type','definition','pk','required'):assert a[field]==b[field],(before['suffix'],field)
    originals=[load_workbook(R10/f'법률에이전트_{a}_골드등록용_테이블별_R10.xlsx',data_only=True) for a in ('B03','B05')]
    for a,b in zip(*originals,strict=True):
        for ar,br in zip(a.iter_rows(values_only=True),b.iter_rows(values_only=True),strict=True):
            norm=lambda v:v.replace('B03','BXX').replace('B05','BXX') if isinstance(v,str) else v
            assert [norm(v) for v in ar]==[norm(v) for v in br]
    counts=[]
    for path in paths:
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
        w=load_workbook(path,data_only=False);assert len(w.worksheets)==23
        data_count=0
        for s in w.worksheets[2:18]:
            data=[r for r in s.iter_rows(min_row=5,values_only=True) if isinstance(r[0],int)]
            data_count+=len(data)
            for r in data:
                assert not re.search(r'FOREIGN KEY|CHECK\s*\(|FK\s*→|UNIQUE\s*\(',str(r[9]),re.I)
        assert data_count==88
        assert not any(c.data_type=='f' for s in w for row in s for c in row)
        counts.append(dict(path=path.name,tables=16,columns=data_count,sheets=len(w.worksheets),sha256=sha(path),bytes=path.stat().st_size))
    books=[load_workbook(p,data_only=True) for p in paths]
    for a,b in zip(books[0],books[1],strict=True):
        assert a.title==b.title and (a.max_row,a.max_column)==(b.max_row,b.max_column)
        for ar,br in zip(a.iter_rows(values_only=True),b.iter_rows(values_only=True),strict=True):
            for av,bv in zip(ar,br,strict=True):
                norm=lambda v:v.replace('B03','BXX').replace('B05','BXX') if isinstance(v,str) else v
                assert norm(av)==norm(bv)
    for a in ('B03','B05'):
        sql=(OUT/f'GOLD_{a}_DDL_REVIEW.sql').read_text();body='\n'.join(x for x in sql.splitlines() if not x.startswith('--'))
        assert body.count('CREATE TABLE ')==16
        assert not re.search(r'FOREIGN KEY|\bREFERENCES\b|CHECK\s*\(|CREATE UNIQUE INDEX|JSON_VALUE\s*\(',body,re.I)
        assert body.count('PRIMARY KEY')==16
        parsed=re.findall(r'CREATE TABLE \{\{APPROVED_GOLD_OWNER\}\}\.([A-Z0-9_]+) \(\n(.*?)\n\);',body,re.S)
        assert len(parsed)==len(tables)
        for (name,definition),t in zip(parsed,tables,strict=True):
            assert name==f'IDD_{a}_LGL_'+t['suffix']
            lines=definition.splitlines();assert len(lines)==len(t['columns'])+1
            for line,c in zip(lines[:-1],t['columns'],strict=True):
                expected=c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c.get('default') else '')+(' NOT NULL' if c['required'] else '')
                assert line.strip().removesuffix(',')==expected
    return dict(status='PASS_STATIC_DESIGN_CONSISTENCY',tables=16,columns=88,baseline_tables=10,baseline_columns=49,retained_baseline_columns=49,added_existing_columns=3,vector_tables=3,vector_columns=17,fts_tables=3,fts_columns=19,core_phase_A_tables=13,core_phase_A_columns=69,direct_soft_relations=len(rels),additional_indexes=sum(len(t['indexes']) for t in tables),primary_keys=16,physical_foreign_keys=0,physical_checks=0,non_pk_unique_constraints=0,function_indexes=0,workbooks=counts,oracle_ddl_executed=False,performance_measured=False,native_excel_render=False,independent_review=False,review_kind='SELF_REVIEW')

def main():
    ts=model();rels=relationships();dump(OUT/'MODEL.json',dict(version='gold-redesign-r11',status=STATUS,tables=ts,relationships=rels,change_map=CHANGE_MAP))
    paths=[]
    for a in ('B03','B05'):paths.append(workbook(ts,rels,a));ddl(ts,a)
    for filename,headers,rows in [
      ('TABLES.csv',['suffix','logical','phase','columns','source','change'],[[t['suffix'],t['logical'],t['phase'],len(t['columns']),t['source'],t['change']] for t in ts]),
      ('COLUMNS.csv',['table','column','logical','type','pk_order','required','source','code_rule'],[[t['suffix'],c['name'],c['logical'],c['type'],c['pk'],c['required'],c['source'],c['rule']] for t in ts for c in t['columns']])]:
        with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.writer(f);wr.writerow(headers);wr.writerows(rows)
    result=validate(ts,rels,paths);dump(OUT/'VALIDATION.json',result)
    sources=[R10/f'법률에이전트_{a}_골드등록용_테이블별_R10.xlsx' for a in ('B03','B05')]+[OLD,ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/'02_BACKEND/semantic_runtime/oracle_query_fulltext.py',ROOT/'02_BACKEND/semantic_runtime/oracle_query_db.py',ROOT/'08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/payload/02_BACKEND/semantic_runtime/initial_vector.py',ROOT/'08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/payload/02_BACKEND/semantic_runtime/vector_publish.py']
    active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    selected=ROOT/Path(active['manifest_path']).parent/'code/02_BACKEND/semantic_runtime'
    sources += [ROOT/'02_BACKEND/semantic_runtime/physical_mapping.py',ROOT/'02_BACKEND/lawrag/pipeline/oracle_query_publish.py',ROOT/'08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/payload/vector_silver/schema.py']
    sources += [p for p in [selected/'oracle_query_fulltext.py',selected/'oracle_query_db.py'] if p.is_file()]
    photos=[]
    for i in (1,2):
        original=Path(f'/tmp/codex-remote-attachments/01a18634-ff7c-7ef3-a360-0fdbf3b9364b/E81D940A-DCDB-4F5B-A79F-673903A666D4/{i}-사진-{i}.jpg')
        target=OUT/f'evidence/photo_{i}.jpg'
        if original.is_file():
            target.parent.mkdir(exist_ok=True);shutil.copyfile(original,target);assert sha(original)==sha(target)
            photos.append(dict(original=str(original),copy=str(target.relative_to(OUT)),sha256=sha(target)))
    dump(OUT/'SOURCES.json',dict(files=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in sources],photos=photos,selected_release=active['release_id'],scope='Read-only evidence snapshot; no field deployment claimed'))
    print(json.dumps({k:result[k] for k in ('status','tables','columns','additional_indexes','direct_soft_relations')},ensure_ascii=False))

if __name__=='__main__':main()
