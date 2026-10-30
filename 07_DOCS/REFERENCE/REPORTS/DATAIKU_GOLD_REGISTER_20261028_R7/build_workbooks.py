"""R7: plain business names and accurate descriptions for all Gold registration columns."""
from pathlib import Path
import base64
import hashlib
import json
import re
import zipfile

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
R6=HERE.parent/'DATAIKU_GOLD_REGISTER_20261028_R6'
MODEL_PATH=HERE.parent/'DATAIKU_GOLD_MASTER_20261028_R3/model.json'
SOURCE_MODEL=json.loads(MODEL_PATH.read_text())
HEADERS=['순번','논리명 (용어 검색)','컬럼명(영문)','도메인명','수식어 단어 (단어 검색)','데이터 타입','길이 / 정밀도','PK 순서','필수','제약조건','컬럼정의','문자열 한글 포함 여부']
WIDTHS=[5,28,31,11,25,17,13,8,6,48,61,16]
NAVY='21374E';TEAL='236C65';BLUE='EAF3FB';GREEN='ECF6F1';GREY='F4F6F9'
FONT_PATH='/mnt/c/Windows/Fonts/malgun.ttf'
BOLD_PATH='/mnt/c/Windows/Fonts/malgunbd.ttf'
FONT=ImageFont.truetype(FONT_PATH,15)
DOMAIN_SUFFIX={'ID':'ID','명':'NAME','값':'VALU','내용':'CTNT','여부':'YN','일시':'DATE_TIME','번호':'NO','순번':'SEQ_NO'}

def term(logical,physical,domain,words,definition,korean=None):
    return dict(logical=logical,physical=physical,domain=domain,words=words,definition=definition,korean=korean)

TERMS={
 'MNFST_HASH_DATA_VALU':term('명세해시값','MNFST_HASH_VALU','값',['명세','해시'],
     '데이터 구성을 기록한 명세 파일(manifest.json)의 SHA-256 해시값. 함께 구축한 데이터 버전을 구분한다.','N'),
 'LGL_DOC_ID':term('문서ID','DOC_ID','ID',['문서'],
     '문서를 구분하고 문서 구조·본문·관련 지식을 연결하는 식별값. 같은 명세해시값 안에서 문서를 구분한다.','N'),
 'LGL_DOC_NAME_CTNT':term('문서명','DOC_NAME','명',['문서'],
     '문서의 이름 또는 제목. 현재 원천 표시명에 경로가 포함된 경우 그 표시명을 보존한다.','Y'),
 'SRC_DATA_HASH_DATA_VALU':term('문서해시값','DOC_HASH_VALU','값',['문서','해시'],
     '원본 문서 파일에 대해 기록된 전체 SHA-256 해시값. 파일의 동일 여부와 내용 변경을 확인한다.','N'),
 'LGL_DOC_JSON_CTNT':term('문서부가정보내용','DOC_ADD_INFO_CTNT','내용',['문서','부가','정보'],
     '문서의 파일명·경로·출처·담당 팀 및 구조화 관련 부가정보를 묶어 저장한 내용. 저장 형식은 JSON이다.','Y'),
 'LGL_UNIT_ID':term('구조단위ID','STRCT_UNIT_ID','ID',['구조','단위'],
     '문서 안의 장·절·조·항·호 등 구조 단위를 구분하는 식별값. 문서ID와 함께 해당 위치를 찾는다.','N'),
 'PRNT_LGL_UNIT_ID':term('상위구조단위ID','PRNT_STRCT_UNIT_ID','ID',['상위','구조','단위'],
     '같은 문서에서 바로 위에 있는 구조단위ID. 문서의 계층 구조를 연결하며 최상위 단위는 비워 둔다.','N'),
 'LGL_UNIT_JSON_CTNT':term('구조단위부가정보내용','STRCT_UNIT_ADD_INFO_CTNT','내용',['구조','단위','부가','정보'],
     '조문 번호·제목·계층·원문 위치 등 구조 단위의 세부 정보를 묶어 저장한 내용. 저장 형식은 JSON이다.','Y'),
 'LGL_BLK_ID':term('본문조각ID','TEXT_BLK_ID','ID',['본문','조각'],
     '문서 안의 원문 본문 조각을 구분하는 식별값. 문서ID와 함께 해당 본문을 조회한다.','N'),
 'LGL_TEXT_CTNT':term('원문내용','SRC_TEXT_CTNT','내용',['원문'],
     '문서에서 추출한 실제 원문 본문. 답변의 근거를 읽고 인용하는 데 사용한다.','Y'),
 'LGL_BLK_JSON_CTNT':term('본문조각부가정보내용','TEXT_BLK_ADD_INFO_CTNT','내용',['본문','조각','부가','정보'],
     '본문 조각의 원문 위치·출처 등 세부 정보를 묶어 저장한 내용. 중복 본문이 생략되면 원문내용과 함께 읽는다. 저장 형식은 JSON이다.','Y'),
 'JSON_TXT_OMIT_YN':term('부가정보본문생략여부','ADD_INFO_TEXT_OMIT_YN','여부',['부가','정보','본문','생략'],
     '본문 부가정보에서 중복 본문을 생략했는지 표시한다. Y는 생략, N은 미생략, NULL은 미지정이다. 원문내용의 유무와는 별개다.','N'),
 'SRC_PBLS_ID':term('원문게시ID','SRC_PBLS_ID','ID',['원문','게시'],
     '검증이 끝난 원문 데이터 묶음의 게시본을 구분하는 식별값. 사용할 원문 데이터 버전을 조회할 때 사용한다.','N'),
 'SRC_PBLS_JSON_CTNT':term('원문게시정보내용','SRC_PBLS_INFO_CTNT','내용',['원문','게시','정보'],
     '원문 게시본의 데이터 버전·원문 건수·관련 파일 목록·검증 정보 등을 묶어 저장한 내용. 저장 형식은 JSON이다.','N'),
 'SRC_PBLS_REG_DATE_TIME':term('등록일시','REG_DATE_TIME','일시',['등록'],
     '원문 게시정보가 DB에 등록된 날짜와 시간. 시간대 정보를 함께 저장한다.'),
 'SRCH_PBLS_ID':term('조회게시ID','SRCH_PBLS_ID','ID',['조회','게시'],
     '원문과 검색 자료를 함께 사용할 조회 게시본의 식별값. 조회 자료와 조회 채널을 같은 게시본에 연결한다.','N'),
 'SRCH_MNFST_JSON_CTNT':term('조회게시정보내용','SRCH_PBLS_INFO_CTNT','내용',['조회','게시','정보'],
     '조회 게시본이 사용하는 원문 게시본·데이터 버전·자료 종류·건수·해시 등을 묶어 저장한 내용. 저장 형식은 JSON이다.','N'),
 'LGL_ROW_KIND_DATA_VALU':term('조회자료유형값','SRCH_DATA_KIND_VALU','값',['조회','자료','유형'],
     '조회 자료가 문서 구조·용어·정의·참조 등 어느 종류인지 구분하는 값. 해당 게시본에 정의된 유형을 사용한다.','N'),
 'LGL_ROW_ID':term('조회자료ID','SRCH_DATA_ID','ID',['조회','자료'],
     '같은 조회 게시본과 자료 유형 안에서 개별 조회 자료를 구분하는 식별값.','N'),
 'LGL_SRCH_KEY_DATA_VALU':term('검색키값','SRCH_KEY_VALU','값',['검색','키'],
     '용어 표기나 식별 문자열로 조회 자료를 찾는 값. 긴 값은 정해진 규칙에 따라 해시로 저장하고 전체 값은 조회자료내용에 보관한다.','Y'),
 'LGL_OWNR_REF_ID':term('소속참조ID','OWNR_REF_ID','ID',['소속','참조'],
     '조회 자료가 속한 구조 단위·정의·참조 등의 식별값. 자료가 연결되는 출발 위치를 찾는 데 사용한다.'),
 'LGL_TGT_REF_ID':term('대상참조ID','TGT_REF_ID','ID',['대상','참조'],
     '관계가 가리키는 대상 또는 상위 단위의 식별값. 참조 대상의 의미는 조회자료유형값에 따라 정해진다.'),
 'LGL_ROW_HASH_DATA_VALU':term('조회자료해시값','SRCH_DATA_HASH_VALU','값',['조회','자료','해시'],
     '자료 유형·식별값·문서·연결키·조회자료내용을 함께 계산한 SHA-256 해시값. 조회 자료 전체의 변경 여부를 확인한다.','N'),
 'LGL_ROW_JSON_CTNT':term('조회자료내용','SRCH_DATA_CTNT','내용',['조회','자료'],
     '원문 위치·용어·정의·참조 등 조회 자료를 유형에 맞춰 묶어 저장한 내용. 저장 형식은 JSON이다.','N'),
 'LGL_CHNL_NAME':term('조회채널명','SRCH_CHNL_NAME','명',['조회','채널'],
     '사용할 조회 게시본을 선택하는 채널의 이름. 채널마다 현재 사용할 조회게시ID를 연결한다.','N'),
 'SRCH_CHG_SEQ_NO':term('변경순번','CHG_SEQ_NO','순번',['변경'],
     '조회 채널의 게시본을 바꿀 때 증가하는 순번. 1부터 시작하며 여러 요청이 동시에 수정하는 충돌을 확인한다.'),
 'ONT_PBLS_ID':term('온톨로지게시ID','ONT_PBLS_ID','ID',['온톨로지','게시'],
     '승인된 온톨로지 게시본을 구분하는 식별값. 개념 묶음·작업 버전·승인 정보·게시 내용의 해시를 결속한다.','N'),
 'ONT_BNDL_ID':term('개념묶음ID','CNCP_BNDL_ID','ID',['개념','묶음'],
     '서로 관련된 개념과 검토 내용을 하나로 묶은 식별값. 작업 버전이 바뀌어도 같은 개념 묶음을 연결한다.','N'),
 'ONT_WORK_VER_NO':term('작업버전번호','WORK_VER_NO','번호',['작업','버전'],
     '게시할 때 승인받은 온톨로지 작업본의 버전 번호. 어떤 검토·승인 결과로 게시했는지 확인한다.'),
 'ONT_PKG_HASH_DATA_VALU':term('게시내용해시값','PBLS_CTNT_HASH_VALU','값',['게시','내용','해시'],
     '게시할 지식과 원문 위치 정보를 정해진 규칙으로 정규화해 계산한 SHA-256 해시값. 승인된 게시 내용의 변경 여부를 확인한다.','N'),
 'ONT_PKG_JSON_CTNT':term('게시지식내용','PBLS_KNWLG_CTNT','내용',['게시','지식'],
     '승인된 개념 묶음의 조건·산정 방법·효과·예외·미확인 사항·근거 및 사전 조립한 조사 경로를 저장한 내용. 저장 형식은 JSON이다.','Y'),
 'ONT_CHG_SEQ_NO':term('변경순번','CHG_SEQ_NO','순번',['변경'],
     '개념 묶음의 활성 게시본을 바꿀 때 증가하는 순번. 초기값 0을 허용하며 게시·중지·롤백 때 변경한다.'),
 'SRC_ANCHOR_HASH_DATA_VALU':term('원문위치해시값','SRC_LOC_HASH_VALU','값',['원문','위치','해시'],
     '문서ID·원문버전ID·구조단위ID의 세 항목을 결합해 계산한 해시값. 해당 원문 위치에 연결된 지식을 찾는다.','N'),
 'SRC_VER_ID':term('원문버전ID','SRC_VER_ID','ID',['원문','버전'],
     '근거로 사용하는 원문의 버전을 구분하는 식별값. 현재 원천 경로에서는 해당 문서의 전체 원본 해시값을 사용한다.','N'),
}
TABLES={
 '01_문서판본':('문서판본내역','데이터 버전별 문서의 식별값·이름·원본 해시와 부가정보를 보관합니다.'),
 '02_문서구조':('문서구조내역','문서의 장·절·조·항·호 등 구조 단위와 상하위 관계를 보관합니다.'),
 '03_원문본문':('문서본문내역','읽고 인용할 원문 본문을 문서·구조 단위와 연결해 보관합니다.'),
 '04_원문게시':('원문게시내역','검증을 마친 원문 데이터 묶음의 게시정보와 등록일시를 관리합니다.'),
 '05_조회게시':('조회게시내역','함께 사용할 원문과 검색 자료를 하나의 조회 게시본으로 묶습니다.'),
 '06_검색관계':('검색관계내역','용어·정의·원문 위치·참조 등 조회 자료와 연결 관계를 보관합니다.'),
 '07_조회채널':('조회채널내역','조회 채널별로 현재 사용할 조회 게시본과 변경순번을 관리합니다.'),
 '08_온톨로지게시':('온톨로지게시내역','승인한 개념 묶음과 조사 경로·근거를 게시본으로 보관합니다.'),
 '09_온톨로지선택':('온톨로지선택내역','개념 묶음별 활성 게시본을 선택하고 게시 중지·롤백을 관리합니다.'),
 '10_원문지식연결':('원문지식연결내역','문서의 원문 위치에서 관련 온톨로지 게시본을 찾도록 연결합니다.'),
}
RENAME={old:t['physical'] for old,t in TERMS.items()}
PATTERN=re.compile(r'\b(?:'+'|'.join(re.escape(x) for x in sorted(RENAME,key=len,reverse=True))+r')\b')
OUTS=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def renamed(text):return PATTERN.sub(lambda m:RENAME[m[0]],text) if isinstance(text,str) else text

def lines(value,pixels,font=FONT):
    out=[]
    for part in str(value or '').split('\n'):
        line=''
        for ch in part:
            if line and font.getlength(line+ch)>pixels:out.append(line);line=ch
            else:line+=ch
        out.append(line)
    return out

def definition(sheet,t):
    if t['logical']=='文書ID':raise AssertionError('unexpected language')
    if t['logical']=='문서ID' and sheet=='06_검색관계':
        return '조회 자료가 속한 문서의 식별값. 문서별 조회 범위를 확인한다. 문서에 속하지 않는 공통 자료는 비워 둘 수 있다.'
    if t['logical']=='문서ID' and sheet=='10_원문지식연결':
        return '온톨로지 근거가 속한 문서의 식별값. 원문 문서와 연결하고 조회 권한을 확인한다.'
    if t['logical']=='온톨로지게시ID' and sheet=='09_온톨로지선택':
        return '해당 개념 묶음에서 활성화한 온톨로지 게시본의 식별값. 비어 있으면 활성 게시본이 없거나 게시가 중지된 상태다.'
    return t['definition']

def korean(t,old):
    if old in ('해당 없음',None):return '해당 없음'
    return t['korean'] if t['korean'] is not None else old

def build(agent,expected_hash):
    src=R6/f'법률에이전트_{agent}_골드등록용_테이블별_R6.xlsx'
    assert sha(src)==expected_hash,'R6 원본이 변경되어 확인이 필요합니다.'
    w=load_workbook(src);mapping=[]
    keys=list(SOURCE_MODEL)
    for i,s in enumerate(w):
        last=int(re.search(r'\d+$',next(iter(s.tables.values())).ref)[0])
        old_rows={r: [s.cell(r,c).value for c in range(1,13)] for r in range(7,last+1)}
        s['A1']=TABLES[s.title][0];s['A3']=TABLES[s.title][1]
        s['A4']='수식어 + 도메인 | 용어·영문 약어·값/명 도메인·인포타입은 메타 조회 후 확정 | 한글: Y=가능 / N=현행 형식상 미포함'
        s.row_dimensions[4].height=25
        for c,h in enumerate(HEADERS,1):s.cell(6,c,h)
        for row,old in old_rows.items():
            t=TERMS[old[2]];d=definition(s.title,t)
            values=old[:]
            values[1]=t['logical'];values[2]=t['physical'];values[3]=t['domain'];values[4]=' · '.join(t['words'])
            values[9]=renamed(old[9]);values[10]=d;values[11]=korean(t,old[11])
            for c,value in enumerate(values,1):s.cell(row,c,value)
            source_t=SOURCE_MODEL[keys[i]];source_c=source_t['columns'][row-7]
            s.cell(row,2).comment=Comment('용어 검색 후보: '+t['logical']+'\n구성: '+' + '.join(t['words']+[t['domain']])+'\n'+d,'메타 검색')
            detail=['영문 컬럼명 후보: '+t['physical'],
                    '현행 원천: '+source_t['source_owner']+'.'+source_t['source_name']+'.'+source_c['current'],
                    '현행 원천 타입: '+source_c['current_type'],'제약조건: '+values[9]]
            if source_c['current_type']!=source_c['type']:detail.append(source_c['conversion'])
            if old[2]!=t['physical']:detail.append('이전 R6 영문 후보: '+old[2])
            s.cell(row,3).comment=Comment('\n'.join(detail),'원천 매핑·영문 후보')
            s.cell(row,4).comment=Comment('도메인 검색 후보: '+t['domain']+'\n영문 종결 후보: '+DOMAIN_SUFFIX[t['domain']]+'\n조회할 타입·길이: '+old[5].replace('\n',' ')+' / '+old[6]+'\n실제 등록 도메인·약어·인포타입을 조회한 뒤 확정합니다. 특히 값 도메인과 문서명의 CLOB 인포타입은 승인 확인 전입니다.','도메인 검색')
            s.cell(row,5).comment=Comment('수식어 단어 검색: '+' · '.join(t['words'])+'\n등록 표준단어와 약어를 먼저 확인합니다.','단어 검색')
            s.cell(row,10).comment=Comment('괄호 안 PK 컬럼 전체의 조합으로 고유성을 판단합니다. 신규 제안은 별도로 표시합니다.\n'+values[9],'제약조건')
            s.cell(row,11).comment=Comment(d+'\n현행 저장 형식과 허용값을 보존한 등록 검토 설명입니다.','컬럼정의')
            kmsg=('숫자 또는 일시형으로 문자열 한글 여부의 적용 대상이 아닙니다.' if values[11]=='해당 없음' else
                  '원문·제목·부가정보·검색 문자열 등에 한글이 포함될 수 있습니다.' if values[11]=='Y' else
                  '현재 생성·저장 형식상 영문·숫자·기호 문자열입니다. JSON 직렬화의 유니코드 이스케이프도 한글 직접 저장과 구분합니다.')
            s.cell(row,12).comment=Comment(kmsg+'\n현행 저장 방식과 확인한 로컬 자료 기준이며, 현장 매핑 형식이 바뀌면 재확인합니다.','한글 여부')
            mapping.append({'sheet':s.title,'sequence':old[0],'old_logical':old[1],'logical':t['logical'],'old_physical':old[2],'physical':t['physical'],'domain':t['domain'],'words':t['words'],'definition':d,'type':old[5],'length':old[6],'korean_before':old[11],'korean':values[11]})
        for c,width in enumerate(WIDTHS,1):s.column_dimensions[get_column_letter(c)].width=width
        for row in s.iter_rows(min_row=6,max_row=last,max_col=12):
            n=1
            for c in row:
                header=c.row==6
                color=(TEAL if c.column in (2,3,4,5) else NAVY) if header else (BLUE if c.column in (2,3,4) else GREEN if c.column in (5,12) else 'FFFFFF' if c.row%2 else GREY)
                c.fill=PatternFill('solid',fgColor=color)
                c.font=Font(name='맑은 고딕',size=10 if c.column in (3,10,11) else 11,bold=header or c.column in (2,3),color='FFFFFF' if header else NAVY)
                c.alignment=Alignment(horizontal='center' if c.column in (1,4,6,7,8,9,12) else 'left',vertical='center',wrap_text=True)
                c.border=Border(bottom=Side(style='thin',color='D8E0E8'),right=Side(style='hair',color='E4E9EF'))
                n=max(n,len(lines(c.value,WIDTHS[c.column-1]*7-16)))
            s.row_dimensions[row[0].row].height=max(44 if row[0].row==6 else 66,n*17+16)
        s.oddFooter.left.text=f'법률 에이전트 {agent} · 메타 등록 검토용 R7'
        s.oddFooter.right.text=TABLES[s.title][0]
    w.properties.title=f'법률 에이전트 {agent} 골드 등록용 테이블별 컬럼표 R7'
    w.properties.description='논리명·영문 후보·도메인·수식어·컬럼정의 통일. 현장 표준 등록 전 검토본.'
    out=HERE/f'법률에이전트_{agent}_골드등록용_테이블별_R7.xlsx'
    w.save(out)
    report=validate(src,out,mapping,agent)
    OUTS.append({'file':out.name,'bytes':out.stat().st_size,'sha256':sha(out),'validation':report})
    (HERE/f'COLUMN_MAPPING_{agent}.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    if agent=='B03':
        preview(w['01_문서판본'],HERE/'preview_문서판본.png',range(6,12))
        preview(w['08_온톨로지게시'],HERE/'preview_온톨로지게시.png',range(6,12))
    assert sha(src)==expected_hash

def validate(src,out,mapping,agent):
    old=load_workbook(src);w=load_workbook(out)
    assert len(w.sheetnames)==10 and old.sheetnames==w.sheetnames and len(mapping)==49
    assert [w['01_문서판본'].cell(r,2).value for r in range(7,12)]==['명세해시값','문서ID','문서명','문서해시값','문서부가정보내용']
    renamed_count=flag_count=0
    for m in mapping:
        s=w[m['sheet']];r=6+m['sequence'];prior=old[s.title]
        assert len(s.tables)==1 and s.sheet_state=='visible' and s.max_column==12
        assert [s.cell(6,c).value for c in range(1,13)]==HEADERS
        assert s.cell(r,2).value==m['logical'] and s.cell(r,3).value==m['physical']
        assert ''.join(m['words'])+m['domain']==m['logical']
        assert m['physical'].endswith('_'+DOMAIN_SUFFIX[m['domain']])
        assert len(m['logical'].encode('utf-8'))<=30 and len(m['physical'].encode('ascii'))<=30
        assert 'JSON' not in m['logical'] and '법규' not in m['logical'] and '세대' not in m['logical']
        for col in (1,6,7,8,9):assert s.cell(r,col).value==prior.cell(r,col).value
        assert s.cell(r,10).value==renamed(prior.cell(r,10).value)
        assert s.cell(r,11).value==m['definition']
        if 'JSON' in m['old_physical'] and m['type']=='CLOB':assert 'JSON' in m['definition']
        if m['logical']=='문서ID':assert s.cell(r,12).value=='N'
        renamed_count+=m['logical']!=m['old_logical'];flag_count+=m['korean']!=m['korean_before']
    for s in w:
        last=int(re.search(r'\d+$',next(iter(s.tables.values())).ref)[0])
        names=[s.cell(r,3).value for r in range(7,last+1)]
        assert len(names)==len(set(names))
        assert all(c.data_type!='f' for row in s for c in row)
        assert all(not c.hidden for c in s.column_dimensions.values())
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert not any(n.lower().endswith(('.js','.jsx','.mjs','.cjs','.bin')) for n in z.namelist())
    return {'status':'PASS','agent':agent,'sheets':10,'tables':10,'column_rows':49,'logical_names_changed':renamed_count,'descriptions_reviewed':49,'korean_flags_corrected':flag_count,'types_lengths_pk_nullability_preserved':True,'foreign_keys_and_checks_renamed_consistently':True,'first_five_names_match_user':True,'source_r6_unchanged':True,'database_or_runtime_changed':False,'standard_dictionary_approved':False,'native_excel_render':False}

def preview(s,path,rows):
    cols=[2,3,4,11,12];widths=[250,300,100,630,140]
    normal=ImageFont.truetype(FONT_PATH,17);bold=ImageFont.truetype(BOLD_PATH,17)
    cells=[[s.cell(r,c).value for c in cols] for r in rows]
    heights=[max(60,max(len(lines(v,widths[i]-20,bold if n==0 else normal)) for i,v in enumerate(row))*25+20) for n,row in enumerate(cells)]
    im=Image.new('RGB',(sum(widths)+40,sum(heights)+140),'white');d=ImageDraw.Draw(im)
    d.rectangle((20,15,sum(widths)+20,65),fill='#'+NAVY)
    d.text((35,24),s['A1'].value+' · R7',font=ImageFont.truetype(BOLD_PATH,26),fill='white')
    d.text((20,80),s['A2'].value,font=normal,fill='#'+NAVY)
    y=120
    for n,(row,h) in enumerate(zip(cells,heights)):
        x=20
        for i,(v,width) in enumerate(zip(row,widths)):
            d.rectangle((x,y,x+width,y+h),fill='#'+(TEAL if n==0 else BLUE if i<3 else GREEN if i==4 else 'FFFFFF'),outline='#D8E0E8')
            for j,line in enumerate(lines(v,width-20,bold if n==0 else normal)):
                d.text((x+10,y+10+j*25),line,font=bold if n==0 else normal,fill='white' if n==0 else '#'+NAVY)
            x+=width
        y+=h
    im.save(path)

def prepare_email():
    body='''<p>안녕하세요.</p>
<p>법률 에이전트 B03·B05 골드 등록용 엑셀 R7 수정본을 전달드립니다. 기존 R6 첨부 대신 이번 R7 파일을 사용해 주세요.</p>
<p>문서판본의 5개 논리명을 명세해시값·문서ID·문서명·문서해시값·문서부가정보내용으로 맞추고, 같은 기준으로 전체 49개 컬럼의 논리명과 설명을 정리했습니다. 수식어·도메인·영문 컬럼명 후보와 PK/FK/CHECK 표기도 함께 맞췄습니다.</p>
<p>문서ID의 한글 포함 여부는 N으로 바로잡았습니다. 부가정보 등은 업무 의미로 이름을 쓰고, 실제 JSON 저장 형식은 컬럼정의에 명시했습니다.</p>
<p>파일별 10개 시트에 테이블 하나씩 배치했습니다. 메타 검색 후 확정할 등록 검토본이며, 값·명 도메인과 타입별 인포타입, 영문 약어는 사전 조회가 필요합니다.</p>
<p>감사합니다.</p>'''
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    for o in OUTS:
        p=HERE/o['file'];assert sha(p)==o['sha256']
        parts.append({'mime_type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','filename':p.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode('ascii')}})
    args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[법률 에이전트 B03·B05] 골드 등록용 엑셀 R7 — 전체 논리명·컬럼정의 정리','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (HERE/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False),encoding='utf-8')
    (HERE/'EMAIL_PLAN.json').write_text(json.dumps({'status':'PREPARED_NOT_SENT','to':args['to'],'subject':args['subject'],'replaces':'R6','attachments':OUTS},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    original_model_hash=sha(MODEL_PATH)
    previous=json.loads((R6/'VALIDATION.json').read_text())
    for f in previous['workbooks']:
        build('B03' if '_B03_' in f['file'] else 'B05',f['sha256'])
    assert sha(MODEL_PATH)==original_model_hash
    (HERE/'VALIDATION.json').write_text(json.dumps({'status':'PASS','workbooks':OUTS,'source_model_unchanged':True},ensure_ascii=False,indent=2)+'\n')
    prepare_email()
    print(json.dumps({'workbooks':OUTS,'mail':'PREPARED_NOT_SENT'},ensure_ascii=False))
