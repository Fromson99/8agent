"""R8: reconcile twelve user photos and issue corrected registration workbooks."""
from pathlib import Path
from copy import copy
import hashlib, json, re, zipfile
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont

ROOT=Path('/home/jin/8-AGENT')
HERE=Path(__file__).resolve().parent
R7=HERE.parent/'DATAIKU_GOLD_REGISTER_20261028_R7'
SOURCE_MODEL=json.loads((HERE.parent/'DATAIKU_GOLD_MASTER_20261028_R3/model.json').read_text())
HEADERS=['순번','논리명 (용어 검색)','컬럼명(영문)','도메인명','수식어 단어 (단어 검색)','데이터 타입','길이 / 정밀도','PK 순서','필수','제약조건','컬럼정의','문자열 한글 포함 여부']
WIDTHS=[5,27,31,10,24,21,18,8,6,53,83,16]
FONT_PATH='/mnt/c/Windows/Fonts/malgun.ttf'
BOLD_PATH='/mnt/c/Windows/Fonts/malgunbd.ttf'
MEASURE=ImageFont.truetype(FONT_PATH,15)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def col(logical,physical,domain,words,typ,length,definition,korean='N'):
    return dict(logical=logical,physical=physical,domain=domain,words=words.split('·'),type=typ,length=length,definition=definition,korean=korean)
def v(logical,physical,domain,words,length,definition,korean='N'):
    return col(logical,physical,domain,words,'VARCHAR2',f'{length} BYTE',definition,korean)
def lob(logical,physical,words,definition,korean='Y'):
    return col(logical,physical,'내용',words,'CLOB','가변',definition,korean)
T={
'manifest':v('명세해시값','MNFST_HASH_VALU','값','명세·해시',100,'원문 데이터 구성 명세 파일(manifest.json)의 전체 내용에 SHA-256을 적용한 64자리 영문 소문자·숫자 해시값이다. 함께 구축한 문서·구조·본문 데이터의 동일한 구성 버전을 식별하며, 각 표를 같은 버전으로 연결한다.'),
'doc':v('문서ID','DOC_ID','ID','문서',1000,'데이터 구축 과정에서 부여한 문서 식별 문자열이다. 같은 명세해시값 안에서 문서 한 건을 구분하고 문서구조·문서본문과 연결한다. 원천값을 그대로 저장하며, 숫자 형태라도 숫자형 변환이나 선행 0 제거를 하지 않는다.'),
'name':v('문서명','DOC_NAME','명','문서',2250,'법령·내규 문서를 구분하여 표시하는 이름 또는 제목이다. 구조화 결과의 원천 표시명을 그대로 저장하며, 표시명에 파일명이나 경로가 포함된 경우 함께 보존한다. 원천에 표시명이 없으면 NULL로 저장한다.','Y'),
'doc_hash':v('문서해시값','DOC_HASH_VALU','값','문서·해시',100,'원본 문서 파일의 전체 바이트에 SHA-256을 적용한 64자리 영문 소문자·숫자 해시값이다. 동일한 원본 파일인지 확인하고 파일 내용이 변경된 판본을 구분하는 데 사용한다. 문서명이나 추출 본문만으로 계산한 값과 구분한다.'),
'doc_meta':lob('문서부가정보내용','DOC_ADDN_IFMN_CTNT','문서·부가·정보','문서의 파일명·경로·출처·담당 조직 및 구조화 과정에서 수집한 부가정보를 JSON 객체로 저장한 내용이다. 문서의 원천과 처리 정보를 확인할 때 사용한다. 별도 부가정보가 없으면 NULL로 저장하며, 가변 길이의 원천 속성을 보존하기 위해 CLOB을 사용한다.'),
'unit':v('구조단위ID','STRC_UNIT_ID','ID','구조·단위',1000,'문서 안의 장·절·조·항·호 등 구조 단위에 부여한 식별 문자열이다. 명세해시값·문서ID와 함께 원문 내 위치를 구분한다. 조문 번호를 표시한 제목과는 별개이며, 원천 식별값을 문자열로 보존한다.'),
'parent':v('상위구조단위ID','UPPR_STRC_UNIT_ID','ID','상위·구조·단위',1000,'같은 명세해시값·문서ID에 속한 구조 단위 중 바로 위 단계의 구조단위ID이다. 문서의 상하위 계층을 연결하는 데 사용한다. 상위 단위가 없는 최상위 구조는 NULL로 저장하며, 문자열 0을 NULL로 대체하지 않는다.'),
'unit_meta':lob('구조단위부가정보내용','STRC_UNIT_ADDN_IFMN_CTNT','구조·단위·부가·정보','구조 단위의 종류·조문 번호·제목·계층·원문 위치 등 상세 속성을 JSON 객체로 저장한 내용이다. 목차와 조문 위치를 확인할 때 사용한다. 별도 속성이 없으면 NULL로 저장하며, 문서별로 달라지는 구조 속성을 CLOB으로 보존한다.'),
'block':v('본문조각ID','BODY_SLC_ID','ID','본문·조각',1000,'문서에서 추출한 본문 조각에 부여한 식별 문자열이다. 명세해시값·문서ID와 함께 본문 조각 한 건을 구분하여 조회·인용하는 데 사용한다. 구조단위ID와는 별개이며, 원천값을 재번호화하거나 숫자형으로 변환하지 않는다.'),
'body':lob('본문내용','BODY_CTNT','본문','문서에서 추출하여 본문 조각별로 보관하는 실제 원문 텍스트이다. 답변 근거의 확인과 인용에 사용하며 요약문이나 모델의 판단으로 대체하지 않는다. 본문이 제공되지 않은 조각은 NULL을 허용한다. 길이가 일정하지 않은 원문을 보존하기 위해 CLOB을 사용한다.'),
'block_meta':lob('본문조각부가정보내용','BODY_SLC_ADDN_IFMN_CTNT','본문·조각·부가·정보','본문 조각의 원문 위치·출처 및 추출 과정의 상세 속성을 JSON 객체로 저장한 내용이다. 부가정보본문생략여부가 Y이면 JSON에서 중복 본문을 생략하고 본문내용과 함께 읽는다. 별도 부가정보가 없으면 NULL을 허용하며 가변 속성을 CLOB으로 보존한다.'),
'omit':col('부가정보본문생략여부','ADD_INFO_TEXT_OMIT_YN','여부','부가·정보·본문·생략','CHAR','1 BYTE','본문조각부가정보내용의 JSON에서 본문내용과 중복되는 본문 항목을 생략했는지 구분하는 값이다. Y는 생략, N은 미생략, NULL은 미지정을 뜻한다. 전체 부가정보의 삭제 여부나 본문내용의 존재 여부를 뜻하지 않는다.'),
'source_pub':v('원문게시해시값','DOC_POST_HASH_VALU','값','원문·게시·해시',100,'검증을 마친 원문 게시 명세를 정해진 방식으로 정규화하고 SHA-256을 적용한 64자리 해시값이다. 원문 데이터와 관련 파일을 함께 사용할 게시본 한 건을 식별한다. 원본 파일의 문서해시값 및 데이터 구성의 명세해시값과는 계산 대상이 다르다.'),
'source_meta':lob('원문게시정보내용','DOC_POST_IFMN_CTNT','원문·게시·정보','검증을 마친 원문 데이터의 구성 버전, 자료 건수, 관련 파일 목록 및 검증 결과를 JSON으로 저장한 내용이다. 함께 사용할 원문 자료의 범위를 확인하며, 게시할 때 반드시 저장한다. 가변 목록을 보존하기 위해 CLOB을 사용한다.','N'),
'time':col('등록일시','RGSN_AITM','일시','등록','TIMESTAMP\nWITH TIME ZONE','소수초 정밀도 6','원문 게시정보가 데이터베이스에 등록된 날짜와 시간이다. 별도 값이 지정되지 않으면 DB 서버의 현재 시각(SYSTIMESTAMP)을 저장하며, 소수초와 시간대 정보를 함께 보존한다. 원본 문서의 제정일·개정일·수집일과 구분한다.','해당 없음'),
'query_pub':v('조회게시해시값','RFRN_POST_HASH_VALU','값','조회·게시·해시',100,'조회에 함께 사용할 원문 게시본과 검색 자료의 명세를 정규화하고 SHA-256을 적용한 64자리 해시값이다. 조회 게시본 한 건을 식별하며 조회자료·조회채널을 동일한 게시본에 연결한다. 원문게시해시값과는 계산 대상이 다르다.'),
'query_meta':lob('조회게시정보내용','RFRN_POST_IFMN_CTNT','조회·게시·정보','조회 게시본이 사용하는 원문 게시본, 데이터 구성 버전, 자료 유형별 건수와 검증 해시 등을 JSON으로 저장한 내용이다. 조회 중 서로 다른 버전의 자료가 섞이지 않도록 사용할 자료 구성을 확인한다. 게시할 때 필수이며 가변 목록을 CLOB으로 보존한다.','N'),
'kind':v('조회자료유형값','RFRN_DTA_TYPE_VALU','값','조회·자료·유형',100,'조회자료가 문서 구조·용어·정의·명시 참조 등 어떤 자료 유형에 속하는지 구분하는 문자열이다. 해당 조회 게시 명세와 자료 생성기에 정의된 유형값을 저장한다. 조회자료ID와 함께 유형별 자료를 구분하며, 유형값을 임의로 재부여하지 않는다.'),
'row_id':v('조회자료ID','RFRN_DTA_ID','ID','조회·자료',100,'조회자료 생성기가 자료의 원천 식별 키를 정규화하고 SHA-256으로 계산한 64자리 식별 문자열이다. 조회게시해시값·조회자료유형값과 함께 자료 한 건을 구분한다. 자료 내용 전체의 변경 검사용 조회자료해시값과는 별개이다.'),
'lookup':v('조회자료식별내용','RFRN_DTA_IDNF_CTNT','내용','조회·자료·식별',1000,'조회자료를 검색하는 데 사용하는 용어 표기 또는 원천 식별 문자열이다. 검색키가 없는 자료는 NULL을 허용한다. 긴 검색키는 정해진 생성 규칙에 따라 sha256: 접두어와 해시로 저장하고, 전체 원천값은 조회자료내용에 보존한다.','Y'),
'owner':v('소속자료식별내용','BLNG_DTA_IDNF_CTNT','내용','소속·자료·식별',1000,'조회자료가 속한 구조 단위·정의·참조 등 출발 자료의 식별 문자열을 저장한 내용이다. 관계가 시작되는 자료를 찾는 데 사용하며, 값의 대상은 조회자료유형값에 따라 정해진다. 소속 자료가 없는 유형은 NULL을 허용한다.','Y'),
'target':v('대상자료식별내용','TAGT_DTA_IDNF_CTNT','내용','대상·자료·식별',1000,'조회자료의 관계가 가리키는 대상 자료 또는 상위 단위의 식별 문자열을 저장한 내용이다. 대상의 종류와 연결 의미는 조회자료유형값에 따라 정해진다. 별도 연결 대상이 없는 유형은 NULL을 허용한다.','Y'),
'row_hash':v('조회자료해시값','SRCH_DATA_HASH_VALU','값','조회·자료·해시',100,'자료 유형·조회자료ID·문서ID·검색 및 관계 식별값·조회자료내용을 정해진 방식으로 정규화하고 SHA-256으로 계산한 64자리 해시값이다. 게시된 조회자료 한 건의 내용 변경 여부를 검증하며, 조회자료ID와는 계산 대상이 다르다.'),
'row_meta':lob('조회자료내용','SRCH_DATA_CTNT','조회·자료','원문 위치·용어·정의·참조 등 조회에 필요한 자료를 유형별 구조에 맞춘 JSON으로 저장한 내용이다. 검색·연결용 열에 모두 담지 않은 원천 속성과 상세 내용을 보존한다. 각 조회자료 행에 필수이며 가변 구조를 CLOB으로 저장한다.','N'),
'channel':v('조회채널명','RFRN_CHNL_NAME','명','조회·채널',100,'사용할 조회 게시본을 선택하는 내부 채널의 이름이다. 채널 한 건마다 조회게시해시값과 변경순번을 관리한다. 현행 생성 규칙은 영문·숫자·밑줄·마침표·하이픈을 사용하며, 사용자에게 표시하는 한글 채널명과 구분한다.'),
'qseq':col('변경순번','CHAN_NO','순번','변경','NUMBER','정밀도 30 / 소수자리 0','조회채널이 가리키는 게시본을 변경할 때 증가시키는 정수 순번이다. 1부터 시작하며, 변경 요청의 예상 순번과 저장된 순번을 비교하여 동시 수정 충돌을 확인한다. 게시본의 작업버전번호와는 별개이다.','해당 없음'),
'ont_pub':v('온톨로지게시ID','ONT_PBLS_ID','ID','온톨로지·게시',64,'승인된 온톨로지 게시본 한 건을 식별하는 64자리 문자열이다. 개념그룹ID·승인 작업버전·승인 영수증·게시내용해시값을 결합하여 생성한다. 같은 개념그룹의 새 게시본은 별도 ID로 보관하며, 기존 게시본을 덮어쓰지 않는다.'),
'group':v('개념그룹ID','CNCP_GROP_ID','ID','개념·그룹',100,'서로 관련된 개념과 원문 검토 내용을 하나로 묶은 그룹의 식별 문자열이다. 그룹의 작업버전이나 게시본이 바뀌어도 같은 그룹을 연결하는 데 사용한다. 원천에서 부여한 값을 보존하며 질문 한 건의 식별번호와 구분한다.'),
'version':col('작업버전번호','WORK_VER_NO','번호','작업·버전','NUMBER','정밀도 30 / 소수자리 0','온톨로지 게시본을 생성할 때 승인받은 작업본의 버전 번호이다. 같은 개념그룹 안에서 작업본이 갱신될 때 증가하는 1 이상의 정수이며, 어떤 검토·승인 결과에서 게시되었는지 추적하는 데 사용한다.','해당 없음'),
'package_hash':v('게시내용해시값','POST_CTNT_HASH_VALU','값','게시·내용·해시',100,'게시할 온톨로지 지식과 원문 위치 등 게시 JSON 전체를 정해진 방식으로 정규화하고 SHA-256으로 계산한 64자리 해시값이다. 승인 후 게시 내용이 변경되지 않았는지 검증한다. 승인 영수증 등을 함께 결속하는 온톨로지게시ID와 구분한다.'),
'package':lob('게시지식내용','POST_KNWL_CTNT','게시·지식','승인된 개념그룹의 적용 조건·산정 방법·효과·예외·미확인 사항·원문 근거와 사전에 조립한 조사 경로를 JSON으로 저장한 내용이다. 관련 원문을 조회할 때 재사용하며, 특정 질문의 답변만을 저장하는 항목은 아니다. 게시 시 필수이며 CLOB으로 보존한다.'),
'oseq':col('변경순번','CHAN_NO','순번','변경','NUMBER','정밀도 30 / 소수자리 0','개념그룹의 활성 게시본을 게시·중지·이전 게시본으로 복귀할 때 증가시키는 정수 순번이다. 초기 상태는 0을 허용하며 이후 변경마다 증가한다. 요청의 예상 순번과 비교하여 동시 수정 충돌을 확인한다.','해당 없음'),
'anchor':v('문서위치해시값','DOC_LCT_HASH_VALU','값','문서·위치·해시',100,'문서ID·원문 판본 식별값·구조단위ID의 세 문자열을 정해진 JSON 형식으로 정규화하고 SHA-256으로 계산한 64자리 해시값이다. 같은 원문 판본의 구조 위치에 연결된 온톨로지 게시본을 찾는 데 사용한다. 현 원천의 판본 식별값은 문서해시값이다.'),
}
LAYOUT=[['manifest','doc','name','doc_hash','doc_meta'],['manifest','doc','unit','parent','unit_meta'],['manifest','doc','block','unit','body','doc_hash','block_meta','omit'],['source_pub','manifest','source_meta','time'],['query_pub','query_meta'],['query_pub','kind','row_id','doc','lookup','owner','target','row_hash','row_meta'],['channel','query_pub','qseq'],['ont_pub','group','version','package_hash','package'],['group','ont_pub','oseq'],['ont_pub','anchor','doc','doc_hash','unit']]
PKS=[[1,2],[1,2,3],[1,2,3],[1],[1],[1,2,3],[1],[1],[1],[1,2]]
FKS={(7,2):(5,1),(9,2):(8,1),(10,1):(8,1)}
CHECKS={(3,8):"{c} IN ('Y','N')",(5,2):'{c} IS JSON',(6,9):'{c} IS JSON',(7,3):'{c} >= 1',(8,5):'{c} IS JSON',(9,3):'{c} >= 0'}
TABLE_DEFS=[
'구축한 데이터 구성 버전별 문서의 식별값·이름·원본 해시와 부가정보를 보관한다. 한 행은 명세해시값 안의 문서 한 건이다.',
'문서의 장·절·조·항·호 등 구조 단위와 상하위 관계를 보관한다. 한 행은 동일한 명세해시값·문서ID에 속한 구조 단위 한 건이다.',
'문서에서 읽고 인용할 원문 본문을 조각별로 보관한다. 한 행은 동일한 명세해시값·문서ID에 속한 본문 조각 한 건이며 구조 단위와 연결한다.',
'검증을 마친 원문 데이터와 관련 파일의 게시 구성을 보관한다. 한 행은 원문 게시본 한 건이며 등록 시각을 함께 관리한다.',
'함께 사용할 원문 게시본과 검색 자료의 구성을 보관한다. 한 행은 조회 게시본 한 건이며 자료의 유형·건수·검증 정보를 결속한다.',
'문서 구조·용어·정의·명시 참조 등 조회자료와 검색·연결용 식별값을 보관한다. 한 행은 조회 게시본·자료 유형 안의 자료 한 건이다.',
'조회채널별로 사용할 조회 게시본과 변경순번을 관리한다. 한 행은 채널 한 건이며 동시 변경 충돌을 확인한다.',
'승인된 개념그룹의 지식·원문 근거·조사 경로를 게시본으로 보관한다. 한 행은 게시본 한 건이며 새 게시본을 이전 게시 이력과 구분한다.',
'개념그룹별로 사용할 활성 게시본과 변경순번을 관리한다. 한 행은 개념그룹 한 건이며 게시 중지 시 게시ID를 NULL로 보관한다.',
'문서 판본의 구조 위치와 온톨로지 게시본 사이의 연결을 보관한다. 한 행은 게시본 안의 원문 위치 한 건이며 원문에서 관련 지식을 찾는 데 사용한다.',
]

def wrap(value,pixels,font=MEASURE):
    out=[]
    for para in str(value or '').split('\n'):
        line=''
        for c in para:
            if line and font.getlength(line+c)>pixels:out.append(line);line=c
            else:line+=c
        out.append(line)
    return out

def final_definition(t,j,term,required):
    d=term['definition']
    if term['physical']=='DOC_ID' and t==6:
        return '조회자료가 속한 원문 문서의 식별 문자열이다. 문서별 조회 범위와 접근권한을 확인하는 데 사용하며 문서판본의 문서ID와 같은 값을 저장한다. 특정 문서에 속하지 않는 공통 용어 등은 NULL을 허용한다.'
    if term['physical']=='DOC_ID' and t==10:
        return '온톨로지 근거가 속한 원문 문서의 식별 문자열이다. 문서해시값·구조단위ID와 함께 원문 판본의 위치를 지정하고 접근권한을 확인한다. 문서판본의 문서ID와 같은 원천값을 필수로 저장한다.'
    if term['physical']=='STRC_UNIT_ID' and t==3:
        return '본문 조각이 속한 문서 구조 단위의 식별 문자열이다. 동일한 명세해시값·문서ID의 문서구조내역과 연결하여 원문의 계층 위치를 찾는다. 대응 구조 단위가 지정되지 않은 본문 조각은 NULL을 허용한다.'
    if term['physical']=='STRC_UNIT_ID' and t==10:
        return '온톨로지 근거가 위치한 원문 구조 단위의 식별 문자열이다. 문서ID·문서해시값과 함께 해당 판본의 장·절·조·항·호 위치를 지정한다. 검증한 원천 구조단위ID를 문자열로 필수 저장하며, 조문 제목으로 대체하지 않는다.'
    if term['physical']=='DOC_HASH_VALU':
        if t==10:
            return '온톨로지 근거로 사용하는 원본 문서 파일의 전체 SHA-256 해시값이다. 현재 원천에서는 이 64자리 문자열을 원문 판본 식별값으로 사용한다. 문서ID·구조단위ID와 함께 근거 위치를 고정하므로 게시 시 필수이며, 문서판본의 동일 원본 해시와 일치해야 한다.'
        return d+' 원천에서 전체 해시가 제공되지 않은 경우 NULL을 허용한다.'
    if t==9 and j==2:
        return '해당 개념그룹에서 현재 사용하도록 선택한 온톨로지 게시본의 식별값이다. 온톨로지게시내역에 존재하는 같은 개념그룹의 게시본을 연결한다. 아직 게시하지 않았거나 게시를 중지한 경우 NULL로 저장하며 이전 게시 이력은 보존한다.'
    return d

def constraint(t,j,term,required,table_names):
    c=term['physical'];parts=['NOT NULL' if required else 'NULL 허용']
    if j in PKS[t-1]:parts.append('PK ('+', '.join(T[LAYOUT[t-1][p-1]]['physical'] for p in PKS[t-1])+')')
    if (t,j) in FKS:
        dest,colno=FKS[t,j];target=T[LAYOUT[dest-1][colno-1]]['physical']
        parts.append(f'FK → {table_names[dest-1]} ({target})')
    if (t,j) in CHECKS:parts.append('CHECK ('+CHECKS[t,j].format(c=c)+')')
    if (t,j)==(4,4):parts.append('DEFAULT SYSTIMESTAMP')
    return '\n'.join(parts)

def build(agent):
    src=R7/f'법률에이전트_{agent}_골드등록용_테이블별_R7.xlsx';before=sha(src)
    w=load_workbook(src);names=[re.search(r'IDD_\w+',s['A2'].value)[0] for s in w]
    source_tables=list(SOURCE_MODEL.values());mapping=[]
    for t,s in enumerate(w,1):
        last=6+len(LAYOUT[t-1]);s['A3']=TABLE_DEFS[t-1]
        s['A4']='R8 · 2026-10-28 | 문자열 길이: BYTE 기준 | 한글 Y=실제 저장 가능 / N=현행 저장 형식상 미포함 | 표준 승인·DB 반영 전 등록용 수정본'
        s.row_dimensions[3].height=34;s.row_dimensions[4].height=30
        for j,key in enumerate(LAYOUT[t-1],1):
            r=j+6;term=T[key].copy();old=[s.cell(r,c).value for c in range(1,13)]
            required=old[8]=='Y';definition=final_definition(t,j,term,required)
            values=[j,term['logical'],term['physical'],term['domain'],' · '.join(term['words']),term['type'],term['length'],PKS[t-1].index(j)+1 if j in PKS[t-1] else '—','Y' if required else 'N',constraint(t,j,term,required,names),definition,term['korean']]
            current=source_tables[t-1]['columns'][j-1]
            for c,value in enumerate(values,1):s.cell(r,c,value);s.cell(r,c).comment=None
            source_ref=source_tables[t-1]['source_owner']+'.'+source_tables[t-1]['source_name']+'.'+current['current']
            change=[]
            if '512' in current['current_type']:change.append('등록 타입은 사용자 지정 인포타입 1000 BYTE를 기본 적용. 문서 판본 참조가 문서해시값인 열은 현 원천의 64자리 해시 계약에 맞춰 100 BYTE 적용.')
            if (t,j)==(3,8):change.append('이행 규칙: 1→Y, 0→N, NULL 유지. 소비자 역변환 Y→1/N→0. DB/제품 코드에 적용한 상태는 아님.')
            if (t,j)==(1,3):change.append('현 로컬 1,547건 문서명 최대1,163 BYTE. 등록 한도2250 BYTE. 원천 초과값은 절단하지 않고 오류로 분리. CLOB→VARCHAR2 적재 매핑 필요.')
            if (t,j)==(10,4):change.append('현행 SRC_VER_ID의 실제 원천인 전체 문서 SHA-256을 문서해시값으로 명시. 비해시 판본 식별값을 이 열에 임의로 넣지 않음. 적재/조회 매핑은 별도 적용.')
            s.cell(r,3).comment=Comment('현재 개발계 매핑: '+source_ref+'\n현재 타입: '+current['current_type']+'\n등록안: '+term['physical']+' / '+term['type'].replace('\n',' ')+' / '+term['length']+'\n'+'\n'.join(change),'원천·이행 매핑')
            s.cell(r,4).comment=Comment('수식어 + 도메인: '+''.join(term['words'])+' + '+term['domain']+'\n실제 승인 표준사전 조회·승인을 완료했다는 표시는 아닙니다.','표준 매핑')
            korean_note='숫자/일시형으로 한글 여부의 적용 대상이 아니다.' if term['korean']=='해당 없음' else '한글이 원문 또는 검색·관계 문자열에 직접 저장될 수 있다.' if term['korean']=='Y' else '현행 생성·저장 표현은 영문·숫자·기호이다.'
            if key in ('source_meta','query_meta','row_meta'):korean_note='현행 게시 직렬화 ensure_ascii=True. 논리 JSON 값에는 한글이 있어도 저장 문자열은 유니코드 이스케이프이므로 N. 한글을 직접 저장하도록 변경하면 Y로 조정한다.'
            if key=='package':korean_note='온톨로지 게시 직렬화 ensure_ascii=False로 한글 원문·설명을 직접 저장하므로 Y.'
            s.cell(r,12).comment=Comment(korean_note,'저장 문자열 기준')
            if key=='lookup':s.cell(r,11).comment=Comment('1000 BYTE는 DB 저장 한도이다. 기존 검색키 생성기의 512 BYTE 초과 해시 처리 임계값을 변경한 것이 아니다.','검색 계약')
            mapping.append(dict(agent=agent,sheet=s.title,table=names[t-1],sequence=j,current_source=source_ref,current_type=current['current_type'],before=old,after=values,source_mapping_notes=change))
        # Replace old notes, which referred to an incomplete R7 draft.
        if t==3:
            s['A15']='이행 규칙: 기존 1→Y, 0→N, NULL 유지. 여부값은 JSON 내부의 중복 본문 생략만 뜻하며 본문내용의 유무와 별개이다.'
            s.row_dimensions[15].height=35
        for c,h in enumerate(HEADERS,1):s.cell(6,c,h)
        for c,width in enumerate(WIDTHS,1):s.column_dimensions[get_column_letter(c)].width=width
        for row in s.iter_rows(min_row=6,max_row=last,max_col=12):
            maxlines=1
            for cell in row:
                header=cell.row==6
                cell.font=Font(name='맑은 고딕',size=10,bold=header or cell.column in (2,3),color='FFFFFF' if header else '21374E')
                color=('236C65' if cell.column in (2,3,4,5) else '21374E') if header else ('EAF3FB' if cell.column in (2,3,4) else 'ECF6F1' if cell.column in (5,12) else 'FFFFFF' if cell.row%2 else 'F4F6F9')
                cell.fill=PatternFill('solid',fgColor=color)
                cell.alignment=Alignment(horizontal='center' if cell.column in (1,4,6,7,8,9,12) else 'left',vertical='center',wrap_text=True)
                cell.border=Border(bottom=Side(style='thin',color='D8E0E8'),right=Side(style='hair',color='E4E9EF'))
                maxlines=max(maxlines,len(wrap(cell.value,WIDTHS[cell.column-1]*7-22)))
            s.row_dimensions[row[0].row].height=max(50 if row[0].row==6 else 82,maxlines*16+20)
        s.sheet_view.zoomScale=75;s.freeze_panes='F7'
        s.oddFooter.left.text=f'법률 에이전트 {agent} · 골드 등록용 R8'
        s.oddFooter.right.text='표 작성 완료 · DB 미반영'
        s.sheet_properties.pageSetUpPr.fitToPage=True
        s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A3
        s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=1
    w.properties.title=f'법률에이전트 {agent} 골드 등록용 테이블별 R8'
    w.properties.description='사용자 사진 12장 반영. 512 BYTE 인포타입을 1000 BYTE로 조정. 타입·길이·PK·필수·제약·정의·한글여부 정합성 수정. 표준승인 및 DB 반영은 별도.'
    out=HERE/f'법률에이전트_{agent}_골드등록용_테이블별_R8.xlsx';w.save(out)
    (HERE/f'COLUMN_MAPPING_{agent}.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    assert sha(src)==before
    return out,mapping,before

def validate(out,mapping):
    w=load_workbook(out);assert len(w.sheetnames)==10 and len(mapping)==49
    schemas={};definitions=0;types1000=0;checks=0;fk_count=0;common={}
    for t,s in enumerate(w,1):
        table=re.search(r'IDD_\w+',s['A2'].value)[0]
        rows=[list(x) for x in s.iter_rows(min_row=7,max_row=6+len(LAYOUT[t-1]),max_col=12,values_only=True)]
        schema={r[2]:r for r in rows};assert len(schema)==len(rows)
        schemas[table]=schema
        assert s.sheet_state=='visible' and len(s.tables)==1
        assert [s.cell(6,c).value for c in range(1,13)]==HEADERS
        expected_pk=[rows[p-1][2] for p in PKS[t-1]]
        for j,r in enumerate(rows,1):
            assert r[0]==j and r[8] in ('Y','N') and r[11] in ('Y','N','해당 없음')
            assert ''.join(r[4].split(' · '))+r[3]==r[1],r
            assert len(r[1].encode())<=30 and len(r[2].encode())<=30,(s.title,r[1],r[2])
            assert r[5] in ('VARCHAR2','CLOB','NUMBER','CHAR','TIMESTAMP\nWITH TIME ZONE')
            assert '512' not in r[6] and 'BIGINT' not in r[5] and 'DATETIME' not in r[5]
            if r[5]=='VARCHAR2':assert re.fullmatch(r'(64|100|1000|2250) BYTE',r[6])
            if r[6]=='1000 BYTE':types1000+=1
            assert len(r[10])>=60 and r[10]!=mapping[sum(map(len,LAYOUT[:t-1]))+j-1]['before'][10]
            definitions+=1
            assert ('NOT NULL' in r[9])==(r[8]=='Y')
            if j in PKS[t-1]:
                assert r[7]==PKS[t-1].index(j)+1 and r[8]=='Y'
                actual=[x.strip() for x in re.search(r'PK \(([^)]+)\)',r[9])[1].split(',')]
                assert actual==expected_pk and set(actual)<=set(schema)
            else:assert r[7]=='—' and 'PK (' not in r[9]
            if 'CHECK (' in r[9]:
                checks+=1;check=re.search(r'CHECK \(([^)]+)',r[9])[1]
                assert check.split()[0]==r[2],(s.title,check,r[2])
            signature=(r[1],r[3],r[5],r[6],r[11])
            if r[2] in common:assert common[r[2]]==signature,(r[2],common[r[2]],signature)
            else:common[r[2]]=signature
        assert [c.hidden for c in s.column_dimensions.values()].count(True)==0
    for s in w:
        for row in s.iter_rows(min_row=7,max_col=12):
            if not isinstance(row[0].value,int):continue
            text=row[9].value
            if 'FK →' in text:
                target,colname=re.search(r'FK → (\w+) \((\w+)\)',text).groups()
                other=schemas[target][colname];fk_count+=1
                assert other[7]==1 and other[8]=='Y'
                assert (row[5].value,row[6].value)==(other[5],other[6])
        assert all(c.data_type!='f' for row in s for c in row)
    assert definitions==49 and checks==6 and fk_count==3
    assert w['06_검색관계']['L11'].value=='Y'
    assert w['03_원문본문']['J9'].value.endswith('BODY_SLC_ID)')
    assert w['09_온톨로지선택']['I8'].value=='N'
    assert '>= 0' in w['09_온톨로지선택']['J9'].value
    assert '>= 1' in w['07_조회채널']['J9'].value
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert not any(n.lower().endswith(('.js','.jsx','.mjs','.cjs','.bin')) for n in z.namelist())
    return dict(status='PASS_DOCUMENT_CONSISTENCY',tables=10,columns=49,definitions_rewritten=definitions,varchar1000_columns=types1000,foreign_keys_checked=fk_count,checks_checked=checks,pk_names_and_order_valid=True,required_null_consistent=True,common_columns_consistent=True,logical_physical_names_within30bytes=True,original_preserved=True,standard_dictionary_approved=False,database_updated=False,native_excel_render=False)

def preview(out,sheetname):
    s=load_workbook(out,data_only=True)[sheetname]
    cols=[2,3,6,7,10,11,12];widths=[210,280,185,175,440,650,100]
    normal=ImageFont.truetype(FONT_PATH,17);bold=ImageFont.truetype(BOLD_PATH,17)
    rows=list(range(6,7+len(LAYOUT[int(sheetname[:2])-1])))
    data=[[s.cell(r,c).value for c in cols] for r in rows]
    heights=[max(64,max(len(wrap(v,widths[i]-24,bold if n==0 else normal)) for i,v in enumerate(row))*25+24) for n,row in enumerate(data)]
    im=Image.new('RGB',(sum(widths)+48,sum(heights)+145),'white');d=ImageDraw.Draw(im)
    d.text((24,22),'R8 | '+s['A1'].value,font=ImageFont.truetype(BOLD_PATH,28),fill='#21374E')
    d.text((24,65),s['A2'].value,font=normal,fill='#45616D');y=115
    for n,row in enumerate(data):
        x=24
        for i,v in enumerate(row):
            d.rectangle((x,y,x+widths[i],y+heights[n]),fill='#244B60' if n==0 else '#F0F5F7' if n%2==0 else 'white',outline='#CFDAE0')
            for k,line in enumerate(wrap(v,widths[i]-24,bold if n==0 else normal)):
                d.text((x+12,y+12+k*25),line,font=bold if n==0 else normal,fill='white' if n==0 else '#21374E')
            x+=widths[i]
        y+=heights[n]
    im.save(HERE/(sheetname+'_검토미리보기.png'))

if __name__=='__main__':
    results=[]
    for agent in ('B03','B05'):
        out,mapping,before=build(agent)
        results.append(dict(file=out.name,bytes=out.stat().st_size,sha256=sha(out),source_sha256=before,validation=validate(out,mapping)))
        if agent=='B03':
            for sheet in ('03_원문본문','04_원문게시','06_검색관계','09_온톨로지선택'):preview(out,sheet)
    (HERE/'VALIDATION.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))
