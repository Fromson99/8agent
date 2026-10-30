"""B03/B05 submission workbooks with visible constraints, definitions and Korean flags."""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

HERE=Path(__file__).resolve().parent
R4=HERE.parent/'DATAIKU_GOLD_REGISTER_20261028_R4'
SOURCE=R4/'법률에이전트_골드등록용_테이블별.xlsx'
spec=importlib.util.spec_from_file_location('gold_r4',R4/'build_workbook.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.apply_domain_revision()
HEADERS=base.HEADERS[:9]+['제약조건','컬럼정의','문자열 한글 포함 여부']
WIDTHS=[5,30,31,12,25,17,13,8,6,48,55,16]
OUTS=[]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def constraints(t,c,model):
    parts=['NULL 허용' if c['nullable'] else 'NOT NULL']
    if c['name'] in t['pk']:parts.append('PK ('+', '.join(t['pk'])+')')
    for ck in t['checks']:
        if c['name'] in ck['columns']:
            parts.append('CHECK ('+ck['expr']+')'+(' [신규 제안]' if ck['status']=='여부형 이행 제안' else ''))
    for fk in t['fks']:
        if c['name'] in fk['columns']:
            parts.append('FK → '+model[fk['target']]['name']+' ('+', '.join(fk['target_columns'])+')')
    if c['default'] is not None:parts.append('DEFAULT '+c['default'])
    return '\n'.join(parts)

def korean_flag(c):
    if not c['type'].startswith(('VARCHAR','CHAR','CLOB')):return '해당 없음'
    return c['korean']

def korean_note(c):
    flag=korean_flag(c)
    if flag=='해당 없음':return '숫자 또는 일시형이므로 문자열 한글 포함 여부의 적용 대상이 아닙니다.'
    if flag=='Y':return '문서명·원문·식별 문자열·JSON 등에 한글이 포함될 수 있어 Y로 표시했습니다. 설계 기준이며 실제 적재값 전체의 실측 결과는 아닙니다.'
    if c['current'] in ('PBLS_JSON_CN','MNFST_JSON_CN','ROW_JSON_CN'):
        return '현재 생성 경로는 ensure_ascii=True로 JSON을 직렬화합니다. 의미상 한글이 있어도 저장 문자열에는 유니코드 이스케이프로 들어가므로 N입니다. 직렬화 방식이 바뀌면 재검토합니다.'
    return '현재 생성·검증 규칙의 영문/숫자/기호 문자열이므로 N입니다. 실제 적재값 전체의 실측 결과는 아닙니다.'

def column_comment(t,c,model):
    parts=['영문 물리 컬럼명 등록 후보입니다.',
           '종결 도메인: '+c['domain']+' → '+base.DOMAIN_SUFFIX[c['domain']],
           '현행 원천: '+t['source_owner']+'.'+t['source_name']+'.'+c['current'],
           '현행 타입: '+c['current_type'],'등록 제안 타입: '+c['type'],constraints(t,c,model)]
    for ix in t['indexes']:
        if c['name'] in ix['columns']:parts.append('보조 인덱스 ('+', '.join(ix['columns'])+')')
    if c['current_type']!=c['type']:parts.append(c['conversion'])
    return '\n'.join(parts)

def build(agent):
    model=copy.deepcopy(base.MODEL)
    for t in model.values():t['name']=t['name'].replace('_A03_','_'+agent+'_')
    w=load_workbook(SOURCE)
    for idx,(key,t) in enumerate(model.items(),1):
        s=w[base.TABS[key]]
        last=6+len(t['columns'])
        for merged in list(s.merged_cells.ranges):s.unmerge_cells(str(merged))
        for region in ('A1:L1','A2:G2','H2:L2','A3:L3','A4:L4'):s.merge_cells(region)
        s['A2']='운영 테이블명(안)  '+t['name']
        s['H2']=agent+' 법률 에이전트 · 공통 스키마'
        s['A4']='명칭·인포타입은 메타 조회 후 확정 | 한글: Y=포함 가능 / N=현재 저장 형식상 미포함 / 해당 없음=비문자열 (실측 전)'
        s['A4'].alignment=Alignment(wrap_text=True,vertical='center');s.row_dimensions[4].height=25
        for col,h in enumerate(HEADERS,1):s.cell(6,col,h)
        s['J6'].comment=Comment('현행 계약을 등록 후보 컬럼명으로 표현합니다. PK는 괄호 안 전체 컬럼 조합이며 개별 컬럼의 단독 고유성을 뜻하지 않습니다. 신규 제안은 별도 표시합니다.','제약조건 기준')
        s['L6'].comment=Comment('저장 문자열의 한글 포함 가능 여부입니다. Y=한글 포함 가능, N=현행 생성·직렬화 규칙상 한글 미포함, 해당 없음=숫자·일시형. 실제 데이터 전수 실측 결과가 아닙니다.','한글 표기 기준')
        for seq,c in enumerate(t['columns'],1):
            row=6+seq
            s.cell(row,10,constraints(t,c,model))
            s.cell(row,11,c['definition'])
            s.cell(row,12,korean_flag(c))
            s.cell(row,3).comment=Comment(column_comment(t,c,model),'현행 계약·등록 제안')
            s.cell(row,10).comment=Comment('현재 DB에 이 명칭으로 생성되었다는 뜻이 아닙니다.\n'+constraints(t,c,model),'제약조건')
            s.cell(row,11).comment=Comment('실제 저장값의 업무 의미입니다. 타입·NULL·허용범위는 같은 행의 관련 열을 함께 확인합니다.','컬럼정의')
            s.cell(row,12).comment=Comment(korean_note(c),'문자열 한글 포함 여부')
        for name in list(s.tables):del s.tables[name]
        table=Table(displayName=f'{agent}GoldTable{idx:02}',ref=f'A6:L{last}')
        table.tableStyleInfo=TableStyleInfo(name=None,showRowStripes=False,showColumnStripes=False)
        s.add_table(table)
        for col,width in enumerate(WIDTHS,1):s.column_dimensions[get_column_letter(col)].width=width
        edge=Side(style='thin',color='D8E0E8')
        for row in s.iter_rows(min_row=6,max_row=last,max_col=12):
            count=1
            for cell in row:
                header=cell.row==6
                fill=(base.TEAL if cell.column in (2,3,4,5) else base.NAVY) if header else (base.BLUE if cell.column in (2,3,4) else (base.GREEN if cell.column in (5,12) else ('FFFFFF' if cell.row%2 else base.GREY)))
                cell.fill=PatternFill('solid',fgColor=fill)
                cell.font=Font(name='맑은 고딕',size=10 if cell.column in (3,10,11) else 11,bold=header or cell.column in (2,3),color='FFFFFF' if header else base.NAVY)
                cell.alignment=Alignment(horizontal='center' if cell.column in (1,4,6,7,8,9,12) else 'left',vertical='center',wrap_text=True)
                cell.border=Border(bottom=edge,right=Side(style='hair',color='E4E9EF'))
                count=max(count,len(base.lines(cell.value,WIDTHS[cell.column-1]*7-16)))
            s.row_dimensions[row[0].row].height=max(42 if row[0].row==6 else 60,count*17+16)
        if key=='block_payload':s.merge_cells(start_row=last+2,start_column=1,end_row=last+2,end_column=12)
        s.freeze_panes='E7';s.print_area=f'A1:L{s.max_row}';s.sheet_view.zoomScale=80
        s.oddFooter.left.text='법률 에이전트 '+agent+' · 메타 등록 검토용 R5'
        s.oddFooter.right.text=t['logical']
    w.properties.title='법률 에이전트 '+agent+' 골드 등록용 테이블별 컬럼표 R5'
    w.properties.description='각 시트에 테이블 1개. 제약조건·컬럼정의·저장 문자열 한글 포함 여부. 법률 공통 스키마의 '+agent+' 등록 검토본.'
    out=HERE/f'법률에이전트_{agent}_골드등록용_테이블별_R5.xlsx'
    w.save(out)
    report=validate(out,model,agent)
    OUTS.append({'file':out.name,'bytes':out.stat().st_size,'sha256':sha(out),'validation':report})
    if agent=='B03':preview(w[base.TABS['query_active']],HERE/'preview_B03_추가항목.png')

def validate(path,model,agent):
    w=load_workbook(path);total=0
    assert w.sheetnames==list(base.TABS.values())
    for key,t in model.items():
        s=w[base.TABS[key]]
        assert s.sheet_state=='visible' and len(s.tables)==1 and s.max_column==12
        assert [s.cell(6,c).value for c in range(1,13)]==HEADERS
        assert s['A2'].value=='운영 테이블명(안)  '+t['name']
        assert len(t['name'].encode('ascii'))<=30
        for seq,c in enumerate(t['columns'],1):
            row=6+seq;typ,length=base.split_type(c['type'])
            expected=[seq,c['logical'],c['name'],c['domain'],' · '.join(c['words'].split('+')[:-1]),typ,length,t['pk'].index(c['name'])+1 if c['name'] in t['pk'] else '—','N' if c['nullable'] else 'Y',constraints(t,c,model),c['definition'],korean_flag(c)]
            assert [s.cell(row,i).value for i in range(1,13)]==expected
            assert c['logical'].endswith(c['domain']) and c['name'].endswith('_'+base.DOMAIN_SUFFIX[c['domain']])
            for fk in t['fks']:
                if c['name'] in fk['columns']:assert '_'+agent+'_' in s.cell(row,10).value
            total+=1
        assert all(not c.hidden for c in s.column_dimensions.values())
        assert all(c.data_type!='f' for row in s for c in row)
    assert total==49
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert not any(n.lower().endswith(('.js','.jsx','.mjs','.cjs','.bin')) for n in z.namelist())
        text='\n'.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.xml'))
        assert 'A03' not in text and 'A05' not in text and ('B05' if agent=='B03' else 'B03') not in text
    return {'status':'PASS','sheets':10,'tables':10,'column_rows':49,'table_prefix':agent,'constraints_definitions_korean_flags_complete':True,'types_lengths_pk_fk_check_defaults_preserved':True,'database_modified':False,'standard_registration_completed':False,'native_excel_render':False}

def preview(s,path):
    # Focused readable layout preview of the new columns; workbook keeps all 12 columns.
    cols=[2,3,10,11,12];widths=[240,285,530,560,140]
    normal=ImageFont.truetype(base.FONT_PATH,17);bold=ImageFont.truetype(base.BOLD_PATH,17)
    rows=[[s.cell(r,c).value for c in cols] for r in range(6,10)]
    heights=[max(60,max(len(base.lines(v,widths[i]-20,bold if n==0 else normal)) for i,v in enumerate(row))*25+20) for n,row in enumerate(rows)]
    im=Image.new('RGB',(sum(widths)+40,sum(heights)+135),'white');d=ImageDraw.Draw(im)
    d.rectangle((20,15,sum(widths)+20,63),fill='#'+base.NAVY)
    d.text((35,22),s['A1'].value+' · B03',font=ImageFont.truetype(base.BOLD_PATH,25),fill='white')
    d.text((20,78),s['A2'].value,font=normal,fill='#'+base.NAVY)
    y=115
    for n,(row,h) in enumerate(zip(rows,heights)):
        x=20
        for i,(v,width) in enumerate(zip(row,widths)):
            d.rectangle((x,y,x+width,y+h),fill='#'+(base.TEAL if n==0 else (base.BLUE if i<2 else (base.GREEN if i==4 else 'FFFFFF'))),outline='#D8E0E8')
            for j,line in enumerate(base.lines(v,width-20,bold if n==0 else normal)):
                d.text((x+10,y+10+j*25),line,font=bold if n==0 else normal,fill='white' if n==0 else '#'+base.NAVY)
            x+=width
        y+=h
    im.save(path)

def prepare_email():
    body='''<p>안녕하세요.</p>
<p>법률 에이전트 골드 등록용 엑셀을 B03용과 B05용으로 각각 전달드립니다. 기존 A03 표기 초안(R4)을 대체하는 이번 R5 첨부를 사용해 주세요.</p>
<ul><li>파일별 10개 테이블·49개 컬럼, 한 시트에 한 테이블 구성</li>
<li>테이블명과 FK 참조명을 각 B03·B05 기준으로 변경</li>
<li>제약조건(PK·FK·CHECK·NULL·기본값), 컬럼정의, 문자열 한글 포함 여부 표시</li>
<li>한글 여부: Y=포함 가능, N=현재 저장 형식상 미포함, 해당 없음=숫자·일시형. 실제 데이터 전수 실측 전 설계 기준입니다.</li></ul>
<p>두 파일은 공통 스키마를 과제번호별로 표현한 등록 검토본입니다. 논리명·영문 컬럼명·도메인·인포타입은 메타 조회 결과로 확정하며, 여부형 CHAR(1) 전환과 신규 CHECK 제안은 본문 시트에 표시했습니다.</p>
<p>감사합니다.</p>'''
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    for o in OUTS:
        p=HERE/o['file'];assert sha(p)==o['sha256']
        parts.append({'mime_type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','filename':p.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode('ascii')}})
    args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[법률 에이전트 B03·B05] 골드 등록용 테이블별 엑셀 R5 — 제약조건·컬럼정의·한글 여부 반영','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (HERE/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False),encoding='utf-8')
    (HERE/'EMAIL_PLAN.json').write_text(json.dumps({'to':args['to'],'subject':args['subject'],'attachments':OUTS,'status':'PREPARED_NOT_SENT'},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    source_hash=sha(SOURCE)
    for agent in ('B03','B05'):build(agent)
    assert sha(SOURCE)==source_hash
    (HERE/'VALIDATION.json').write_text(json.dumps({'status':'PASS','source_r4_sha256':source_hash,'source_unchanged':True,'workbooks':OUTS},ensure_ascii=False,indent=2)+'\n')
    prepare_email()
    print(json.dumps({'workbooks':OUTS,'mail':'PREPARED_NOT_SENT'},ensure_ascii=False))
