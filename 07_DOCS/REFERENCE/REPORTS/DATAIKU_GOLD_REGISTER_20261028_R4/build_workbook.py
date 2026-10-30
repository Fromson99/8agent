"""One sheet per Gold table, focused on fields for metadata lookup."""
from pathlib import Path
import copy
import hashlib
import json
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'DATAIKU_GOLD_MASTER_20261028_R3/model.json'
OUT=HERE/'법률에이전트_골드등록용_테이블별.xlsx'
ORIGINAL_MODEL=json.loads(SOURCE.read_text())
MODEL=copy.deepcopy(ORIGINAL_MODEL)
DOMAIN_SUFFIX={'ID':'ID','내용':'CTNT','데이터값':'DATA_VALU','일시':'DATE_TIME','여부':'YN','명':'NAME','순번':'SEQ_NO','번호':'NO'}
DOMAIN_CHANGES=[]
HEADERS=['순번','논리명 (용어 검색)','컬럼명(영문)','도메인명','수식어 단어 (단어 검색)','데이터 타입','길이 / 정밀도','PK 순서','필수','컬럼 설명']
WIDTHS=[5,30,31,12,25,17,13,8,6,47]
FONT_PATH='/mnt/c/Windows/Fonts/malgun.ttf'
BOLD_PATH='/mnt/c/Windows/Fonts/malgunbd.ttf'
FONT=ImageFont.truetype(FONT_PATH,15)
NAVY='21374E';TEAL='236C65';BLUE='EAF3FB';GREEN='ECF6F1';GREY='F4F6F9'
TABS={
 'document':'01_문서판본','source_unit':'02_문서구조','block_payload':'03_원문본문',
 'source_release':'04_원문게시','query_release':'05_조회게시','query_row':'06_검색관계',
 'query_active':'07_조회채널','publication':'08_온톨로지게시','head':'09_온톨로지선택','anchor':'10_원문지식연결',
}
TABLE_DESC={
 'document':'문서의 이름·출처·원본 해시를 데이터 구축 세대별로 보관합니다.',
 'source_unit':'문서를 장·절·조·항·호 등으로 나누고 상위 구조와 연결합니다.',
 'block_payload':'답변에서 읽고 인용할 원문 본문과 문서·구조 단위 연결을 보관합니다.',
 'source_release':'검증된 원문 데이터 세대와 파일 목록을 하나의 게시본으로 묶습니다.',
 'query_release':'조회에 사용할 원문 게시본과 검색 자료의 종류·건수·해시를 묶습니다.',
 'query_row':'용어·정의·명시 참조·문서 구조·검색 자료를 종류별 조회 행으로 보관합니다.',
 'query_active':'조회 채널마다 사용할 게시본과 동시 변경 검사용 순번을 관리합니다.',
 'publication':'승인된 온톨로지의 조건·산정·효과·예외·근거를 조립한 게시본을 보관합니다.',
 'head':'개념 묶음마다 활성화한 게시본을 선택하고 게시 중지·롤백을 관리합니다.',
 'anchor':'문서·판본·조항에서 연결된 온톨로지 게시본을 찾는 색인입니다.',
}
SHORT={
 'DATA_VER_ID':'원문·목차·용어집을 함께 구축한 데이터 세대의 식별값.',
 'DOC_ID':'법규 문서의 원천 식별값. 구조·본문·지식 연결에 사용.',
 'DOC_NM':'법령·내규의 원문 문서 이름.',
 'SRC_DATA_HASH_VAL':'참조하는 원본 자료의 SHA-256 해시값.',
 'DOC_JSON_CN':'문서의 판본·출처 등 부가 정보를 담은 JSON.',
 'UNIT_ID':'장·절·조·항·호 등 원문 구조 단위의 식별값.',
 'PRNT_UNIT_ID':'같은 문서의 바로 위 구조 단위 ID. 최상위는 NULL.',
 'UNIT_JSON_CN':'조문 번호·제목·위치 등 구조 정보 JSON.',
 'BLK_ID':'문서 안의 원문 본문 조각 식별값.',
 'BLK_TXT_CN':'답변의 근거로 읽고 인용하는 실제 원문.',
 'BLK_JSON_CN':'본문 조각의 위치·출처 등 부가 정보 JSON.',
 'JSON_TXT_OMIT_YN':'JSON 중복 본문 생략 표시. Y=생략, N=미생략, NULL=미지정.',
 'SRC_PBLS_ID':'검증된 원문·파일 묶음 게시본의 식별값.',
 'PBLS_JSON_CN':'게시한 데이터 세대·파일 목록·설정 JSON.',
 'REG_DTM':'원문 게시 행의 등록 일시. 시간대를 함께 저장.',
 'SRCH_PBLS_ID':'원문·검색 자료를 함께 사용할 조회 게시본 ID.',
 'MNFST_JSON_CN':'조회 게시본의 원문·자료 종류·건수·해시 명세.',
 'ROW_KIND_CD':'문서 구조·용어·정의·참조 등 조회 자료의 종류.',
 'ROW_ID':'조회 게시본의 같은 자료 종류 안에서 구분하는 행 ID.',
 'SRCH_KEY_ID':'용어 표기 또는 식별 문자열로 자료를 찾는 검색키.',
 'OWNR_REF_ID':'조회 자료가 속한 구조 단위·정의·참조 등의 ID.',
 'TGT_REF_ID':'관계가 가리키는 대상 또는 상위 단위의 ID.',
 'ROW_HASH_VAL':'조회 행의 종류·식별자·연결키·JSON을 결속한 해시.',
 'ROW_JSON_CN':'원문 좌표·용어·정의 등 조회 자료의 JSON.',
 'CHNL_NM':'사용할 조회 게시본을 선택하는 채널의 이름.',
 'CHG_SEQ_NO':'조회 채널 변경 때 증가하는 순번. 1 이상.',
 'PUB_ID':'승인한 온톨로지 게시본을 구분하는 식별값.',
 'BNDL_ID':'여러 작업 판본·게시본이 공유하는 개념 묶음 ID.',
 'REV_NO':'게시할 때 승인받은 온톨로지 작업 판본 번호.',
 'PKG_HASH_VAL':'사전 조립 시나리오·원문 좌표가 담긴 게시 내용 해시.',
 'PKG_JSON_CN':'승인한 조건·산정·효과·예외·근거의 사전 조립 JSON.',
 'ANC_HASH_VAL':'문서 ID·원문 판본·구조 단위 ID 세 항목의 해시.',
 'SRC_VER_ID':'근거 원문의 판본 식별값. 데이터 구축 세대와 구분.',
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def apply_domain_revision():
    """Use the photographed 데이터값 domain as a lookup candidate, not an approval."""
    maps={}
    for key,t in MODEL.items():
        maps[key]={}
        for c in t['columns']:
            if c['domain']!='값':continue
            before={n:c[n] for n in ('name','logical','words','domain')}
            assert c['logical'].endswith('값') and c['name'].endswith('_VALU')
            c['logical']=c['logical'][:-1]+'데이터값'
            c['words']=c['words'][:-1]+'데이터값'
            c['name']=c['name'][:-5]+'_DATA_VALU'
            c['domain']='데이터값'
            if c['current']=='ROW_HASH_VAL':
                # Keep the explicit row meaning within the guide's 30-byte name limit.
                c['logical']='법규행해시데이터값'
                c['words']='법규+행+해시+데이터값'
            maps[key][before['name']]=c['name']
            DOMAIN_CHANGES.append({'table':t['name'],'current_column':c['current'],'before':before,'after':{n:c[n] for n in before}})
    for key,t in MODEL.items():
        rename=lambda names:[maps[key].get(n,n) for n in names]
        t['pk']=rename(t['pk'])
        for ck in t['checks']:
            ck['columns']=rename(ck['columns'])
            for old,new in maps[key].items():ck['expr']=re.sub(r'\b'+re.escape(old)+r'\b',new,ck['expr'])
        for fk in t['fks']:
            fk['columns']=rename(fk['columns'])
            fk['target_columns']=[maps[fk['target']].get(n,n) for n in fk['target_columns']]
        for ix in t['indexes']:ix['columns']=rename(ix['columns'])

def split_type(value):
    m=re.fullmatch(r'(VARCHAR2|CHAR)\((\d+)( BYTE| CHAR)?\)',value)
    if m:return m[1],m[2]+(m[3] or '')
    m=re.fullmatch(r'NUMBER\((\d+)(?:,(\d+))?\)',value)
    if m:return 'NUMBER','정밀도 '+m[1]+('\n소수 '+m[2] if m[2] else '')
    if value=='CLOB':return 'CLOB','가변'
    if value=='TIMESTAMP WITH TIME ZONE':return 'TIMESTAMP\nWITH TIME ZONE','—'
    raise ValueError(value)

def lines(text,pixels,font=FONT):
    result=[]
    for piece in str(text or '').split('\n'):
        line=''
        for ch in piece:
            if line and font.getlength(line+ch)>pixels:result.append(line);line=ch
            else:line+=ch
        result.append(line)
    return result

def details(t,c):
    parts=['현재: '+t['source_owner']+'.'+t['source_name']+'.'+c['current'],
           '현재 타입: '+c['current_type'],'목표 타입: '+c['type'],c['definition']]
    if c['default']:parts.append('기본값: '+c['default'])
    for ck in t['checks']:
        if c['name'] in ck['columns']:parts.append('CHECK: '+ck['expr'])
    for fk in t['fks']:
        if c['name'] in fk['columns']:parts.append('FK: '+MODEL[fk['target']]['name']+'('+', '.join(fk['target_columns'])+')')
    if c['current_type']!=c['type']:parts.append(c['conversion'])
    return '\n'.join(parts)

def build():
    before=sha(SOURCE)
    w=Workbook();w.remove(w.active)
    for number,(key,t) in enumerate(MODEL.items(),1):
        s=w.create_sheet(TABS[key]);s.sheet_view.showGridLines=False;s.sheet_view.zoomScale=85
        s.sheet_properties.tabColor=TEAL if number<=7 else '7464A0'
        s.merge_cells('A1:J1');s['A1']=t['logical'];s['A1'].font=Font(name='맑은 고딕',size=20,bold=True,color='FFFFFF');s['A1'].fill=PatternFill('solid',fgColor=NAVY);s['A1'].alignment=Alignment(vertical='center',indent=1);s.row_dimensions[1].height=42
        s.merge_cells('A2:G2');s['A2']='운영 테이블명(안)  '+t['name'];s['A2'].font=Font(name='맑은 고딕',size=11,bold=True,color=NAVY)
        s.merge_cells('H2:J2');s['H2']='3·5번 법률 에이전트 공통';s['H2'].font=Font(name='맑은 고딕',size=10,bold=True,color=TEAL);s['H2'].alignment=Alignment(horizontal='right',vertical='center')
        s.row_dimensions[2].height=27
        s.merge_cells('A3:J3');s['A3']=TABLE_DESC[key];s['A3'].font=Font(name='맑은 고딕',size=11,color='435369');s['A3'].alignment=Alignment(vertical='center');s.row_dimensions[3].height=27
        s.merge_cells('A4:J4');s['A4']='논리명 = 수식어 + 도메인명  |  영문명도 대응 약어로 종결 · 이름/약어/인포타입은 사전 조회 후 확정 · A03 잠정';s['A4'].font=Font(name='맑은 고딕',size=9,color='64748B');s.row_dimensions[4].height=22
        s.row_dimensions[5].height=10
        for col,h in enumerate(HEADERS,1):s.cell(6,col,h)
        for seq,c in enumerate(t['columns'],1):
            datatype,length=split_type(c['type'])
            parts=c['words'].split('+');assert parts[-1]==c['domain']
            short=SHORT[c['current']]
            if key=='head' and c['current']=='PUB_ID':short='활성화한 게시본 ID. NULL이면 미선택 또는 게시 중지.'
            if key=='head' and c['current']=='CHG_SEQ_NO':short='활성 게시 변경 때 증가하는 순번. 초기 0 허용.'
            if key=='query_row' and c['current']=='DOC_ID':short='자료의 소속 문서 ID. 문서 비소속 공통 자료는 NULL.'
            values=[seq,c['logical'],c['name'],c['domain'],' · '.join(parts[:-1]),datatype,length,t['pk'].index(c['name'])+1 if c['name'] in t['pk'] else '—','Y' if not c['nullable'] else 'N',short]
            s.append(values)
            row=s.max_row
            s.cell(row,2).comment=Comment('용어 검색 후보: '+c['logical']+'\n구성: '+''.join(parts[:-1])+' + '+c['domain']+'\n'+c['definition'],'메타 검색')
            evidence=('사용자 사진에서 데이터값 도메인과 DATA_VALU 종결 예시를 확인했습니다. 사진의 데이터값VC60은 60자리 예시이므로 이 컬럼에 그대로 적용하지 않습니다.' if c['domain']=='데이터값' else '기존 가이드·음성 녹취를 바탕으로 한 검색 후보입니다. 실제 표준사전 등록명·약어는 확인이 필요합니다.')
            s.cell(row,4).comment=Comment('도메인 검색어: '+c['domain']+'\n영문 종결 후보: '+DOMAIN_SUFFIX[c['domain']]+'\n'+evidence+'\n인포타입 조회 조건: '+c['type']+'\n도메인명과 인포타입명은 별개입니다. 이 타입·길이·의미에 맞는 등록 인포타입을 선택하세요. 적합한 항목이 없으면 신규 신청을 검토합니다.','메타 검색')
            s.cell(row,5).comment=Comment('도메인 종결어를 제외한 수식어 단어 후보입니다. 등록 단일어·복합어를 먼저 검색하세요.','단어 검색')
            s.cell(row,3).comment=Comment('영문 물리 컬럼명 등록 후보입니다.\n종결 도메인: '+c['domain']+' → '+DOMAIN_SUFFIX[c['domain']]+'\n'+details(t,c),'현재 계약·제약')
        last=6+len(t['columns'])
        table=Table(displayName=f'GoldTable{number:02}',ref=f'A6:J{last}')
        table.tableStyleInfo=TableStyleInfo(name=None,showFirstColumn=False,showLastColumn=False,showRowStripes=False,showColumnStripes=False)
        s.add_table(table);s.freeze_panes='E7'
        for col,width in enumerate(WIDTHS,1):s.column_dimensions[get_column_letter(col)].width=width
        edge=Side(style='thin',color='D8E0E8')
        for row in s.iter_rows(min_row=6,max_row=last):
            line_count=1
            for c in row:
                header=c.row==6
                fill=(TEAL if c.column in (2,3,4,5) else NAVY) if header else (BLUE if c.column in (2,3,4) else (GREEN if c.column==5 else ('FFFFFF' if c.row%2 else GREY)))
                c.fill=PatternFill('solid',fgColor=fill)
                c.font=Font(name='맑은 고딕',size=10 if c.column==3 else 11,bold=header or c.column in (2,3),color='FFFFFF' if header else NAVY)
                c.alignment=Alignment(horizontal='center' if c.column in (1,4,6,7,8,9) else 'left',vertical='center',wrap_text=True)
                c.border=Border(bottom=edge,right=Side(style='hair',color='E4E9EF'))
                line_count=max(line_count,len(lines(c.value,WIDTHS[c.column-1]*7-12)))
            s.row_dimensions[row[0].row].height=max(36 if row[0].row==6 else 48,line_count*16+14)
        # One concise note only where a material type migration is proposed.
        if key=='block_payload':
            note_row=last+2;s.merge_cells(start_row=note_row,start_column=1,end_row=note_row,end_column=10)
            cell=s.cell(note_row,1,'여부형은 CHAR(1) 제안입니다. 현재 0/1/NULL → N/Y/NULL 변환과 조회 코드 적용 후 사용합니다.')
            cell.font=Font(name='맑은 고딕',size=9,color='805D26');cell.alignment=Alignment(wrap_text=True,vertical='center');s.row_dimensions[note_row].height=25
        s.print_area=f'A1:J{s.max_row}';s.print_title_rows='1:6'
        s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A3
        s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=1;s.sheet_properties.pageSetUpPr.fitToPage=True
        s.oddFooter.left.text='법률 에이전트 3·5 · 메타 등록용';s.oddFooter.right.text=t['logical']
    w.properties.title='법률 에이전트 골드 등록용 테이블별 컬럼표';w.properties.creator='법률 에이전트 프로젝트'
    w.properties.description='10개 시트에 각 1개 테이블. 논리명·도메인명·단어 검색 중심. 등록 후보.'
    w.active=0;w.save(OUT)
    validate(before)
    preview(w['01_문서판본'],HERE/'preview.png')
    print(json.dumps({'file':str(OUT),'sheets':w.sheetnames,'tables':10,'columns':49},ensure_ascii=False))

def validate(before):
    w=load_workbook(OUT)
    assert len(w.sheetnames)==10
    assert w.sheetnames==list(TABS.values())
    total=0
    for key,t in MODEL.items():
        s=w[TABS[key]];assert len(s.tables)==1 and s.sheet_state=='visible'
        assert [s.cell(6,c).value for c in range(1,11)]==HEADERS
        assert s.freeze_panes=='E7'
        for seq,c in enumerate(t['columns'],1):
            row=6+seq;typ,length=split_type(c['type'])
            assert [s.cell(row,n).value for n in (2,4,6,7,3)]==[c['logical'],c['domain'],typ,length,c['name']]
            assert s.cell(row,5).value.replace(' · ','')+c['domain']==c['logical']
            assert c['logical'].endswith(c['domain'])
            assert c['name'].endswith('_'+DOMAIN_SUFFIX[c['domain']])
            assert len(c['logical'].encode('utf-8'))<=30 and len(c['name'].encode('ascii'))<=30
            original=ORIGINAL_MODEL[key]['columns'][seq-1]
            for field in ('current','type','current_type','nullable','default','definition'):
                assert c[field]==original[field]
            assert (c['name'] in t['pk'])==(original['name'] in ORIGINAL_MODEL[key]['pk'])
            assert s.cell(row,8).value==(t['pk'].index(c['name'])+1 if c['name'] in t['pk'] else '—')
            assert s.cell(row,9).value==('N' if c['nullable'] else 'Y')
            total+=1
        assert s.max_column==10
        assert all(not d.hidden for d in s.column_dimensions.values())
        assert all(c.data_type!='f' for row in s for c in row)
    assert total==49 and sha(SOURCE)==before
    with zipfile.ZipFile(OUT) as z:assert z.testzip() is None
    assert len(DOMAIN_CHANGES)==7
    assert len({change['after']['name'] for change in DOMAIN_CHANGES})==6
    evidence_path=HERE/'sources/metadata_domain_example.jpg'
    (HERE/'DOMAIN_REVISION.json').write_text(json.dumps({'source_photo':str(evidence_path.relative_to(HERE)),'source_photo_sha256':sha(evidence_path),'observed_domain':'데이터값','observed_physical_suffix':'DATA_VALU','observed_infotype_example':'데이터값VC60','infotype_example_is_not_our_required_length':True,'changes':DOMAIN_CHANGES,'registration_verified':False},ensure_ascii=False,indent=2)+'\n')
    (HERE/'VALIDATION.json').write_text(json.dumps({'status':'PASS','workbook':OUT.name,'sha256':sha(OUT),'sheet_count':10,'table_count':10,'column_rows':49,'one_table_per_sheet':True,'extra_sheets':0,'hidden_sheets':0,'search_fields_separate':True,'same_values_as_r3':False,'renamed_column_rows':len(DOMAIN_CHANGES),'same_types_lengths_nullability_defaults_and_pk_as_r3':True,'logical_and_physical_domain_suffixes_match':True,'all_names_within_30_utf8_bytes':True,'source_sha256':before,'database_modified':False,'metadata_approval':False,'native_excel_render':False},ensure_ascii=False,indent=2)+'\n')

def preview(s,path):
    scale=1.2
    sizes=[int(v*7*scale) for v in WIDTHS];W=sum(sizes)
    normal=ImageFont.truetype(FONT_PATH,17);bold=ImageFont.truetype(BOLD_PATH,17)
    # Reconstruct the visible cells for layout review without altering source images.
    rows=[[s.cell(r,c).value for c in range(1,11)] for r in range(6,12)]
    heights=[max(48,max(len(lines(v,sizes[i]-16,bold if n==0 or i in (1,2) else normal)) for i,v in enumerate(row))*25+18) for n,row in enumerate(rows)]
    im=Image.new('RGB',(W+40,sum(heights)+175),'white');d=ImageDraw.Draw(im)
    d.rectangle((20,15,W+20,65),fill='#'+NAVY)
    d.text((36,24),s['A1'].value,font=ImageFont.truetype(BOLD_PATH,26),fill='white')
    d.text((20,78),s['A2'].value+'   |   3·5번 공통',font=normal,fill='#'+NAVY)
    d.text((20,108),s['A3'].value,font=normal,fill='#435369')
    y=150
    for n,(row,height) in enumerate(zip(rows,heights)):
        x=20
        for i,(value,width) in enumerate(zip(row,sizes)):
            bg=(TEAL if i in (1,2,3,4) else NAVY) if n==0 else (BLUE if i in (1,2,3) else (GREEN if i==4 else ('FFFFFF' if n%2 else GREY)))
            d.rectangle((x,y,x+width,y+height),fill='#'+bg,outline='#D8E0E8')
            font=bold if n==0 or i in (1,2) else normal
            for j,line in enumerate(lines(value,width-16,font)):d.text((x+8,y+9+j*25),line,font=font,fill='white' if n==0 else '#'+NAVY)
            x+=width
        y+=height
    im.save(path)

if __name__=='__main__':
    apply_domain_revision()
    build()
