"""Render the reviewed specification to editable DOCX, PDF and XLSX."""
from pathlib import Path
import importlib.util
import json
import re
import hashlib
from html import escape
from math import ceil

from markdown_it import MarkdownIt
from docx.shared import Cm, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
import fitz

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
STEM='외규_API_크롤링_수집_구축요청서_20261023'
SOURCE=HERE/(STEM+'.md')
TITLE='외규 API 및 웹 문서 수집 구축 요청서'
tokens=MarkdownIt('commonmark').enable('table').parse(SOURCE.read_text())
inventory=json.loads((HERE/'DOCUMENT_INVENTORY.json').read_text())
endpoints=json.loads((HERE/'ENDPOINTS.json').read_text())

def plain(t):
    if t.type in ('text','code_inline'): return t.content
    if t.type in ('softbreak','hardbreak'): return ' '
    return ''.join(plain(c) for c in t.children or [])

def get_table(start):
    rows=[]; row=[]; i=start+1
    while tokens[i].type!='table_close':
        t=tokens[i]
        if t.type=='tr_open': row=[]
        elif t.type=='inline': row.append(t)
        elif t.type=='tr_close': rows.append(row)
        i+=1
    return rows,i+1

def proportions(headers):
    n=len(headers)
    if n==2: return [.20,.80]
    if headers[0]=='관리번호': return [.12,.66,.22]
    if '전체 요청 주소' in headers: return [.16,.40,.44]
    if headers[0]=='요청': return [.19,.25,.56]
    if headers[0]=='필드': return [.28,.48,.24]
    if headers[0]=='기존 방식·관측': return [.36,.32,.32]
    if headers[0]=='구분' and headers[1]=='기본 문서 수': return [.29,.14,.57]
    if headers[0]=='작업': return [.20,.27,.53]
    return [.23,.37,.40] if n==3 else [1/n]*n

skill=Path('/mnt/c/Users/Jin/.codex/skills/implementation-design-report/scripts/build_report_docx.py')
spec=importlib.util.spec_from_file_location('report_renderer',skill)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class VendorRenderer(module.Renderer):
    def cover(self):
        p=self.doc.add_paragraph(); p.paragraph_format.space_before=Pt(55)
        module.font(p.add_run('DOCUMENT COLLECTION REQUEST'),10,module.TEAL,True)
        p=self.doc.add_paragraph(); p.paragraph_format.space_before=Pt(14)
        module.font(p.add_run('외규 API 및 웹 문서\n수집 구축 요청서'),26,module.NAVY,True)
        p=self.doc.add_paragraph('뭉타 구축 담당자 전달용\n2026년 10월 23일 · 버전 1.0')
        for r in p.runs: module.font(r,12,'617585')
        p=self.doc.add_paragraph('API 49종  +  크롤링 19종\n원본 수집 · 판본 관리 · AIDP 인계')
        p.paragraph_format.space_before=Pt(24)
        for r in p.runs: module.font(r,16,module.TEAL,True)
        p=self.doc.add_paragraph('인증·주소·파라미터부터 배치, 저장 구조, 실패 처리와 검수까지\n확인된 명세와 운영 협의 사항을 구분했습니다.')
        p.paragraph_format.space_before=Pt(20)
        for r in p.runs: module.font(r,11,module.INK)
        self.doc.add_page_break()
        self.doc.add_heading('목차',level=1)
        for n,t in enumerate(self.tokens):
            if t.type=='heading_open' and t.tag=='h2':
                p=self.doc.add_paragraph()
                p.paragraph_format.space_after=Pt(10)
                r=p.add_run(plain(self.tokens[n+1])); module.font(r,11,module.NAVY)
                link=OxmlElement('w:hyperlink'); link.set(qn('w:anchor'),self.heading_bookmarks[n])
                link.append(r._r); p._p.append(link)
        self.doc.add_page_break()

renderer=VendorRenderer(SOURCE,TITLE,'뭉타 전달용 · API 49종 / 크롤링 19종','', '외규 수집 구축 요청')
doc=renderer.render()
for n,p in enumerate(doc.paragraphs):
    if p._p.xpath('./w:pPr/w:shd'):
        nxt=doc.paragraphs[n+1] if n+1<len(doc.paragraphs) else None
        p.paragraph_format.keep_with_next=bool(nxt is not None and nxt._p.xpath('./w:pPr/w:shd'))
for tab in doc.tables:
    headers=[c.text for c in tab.rows[0].cells]
    widths=[17.4*x for x in proportions(headers)]
    for col,w in zip(tab.columns,widths): col.width=Cm(w)
    for row in tab.rows:
        for cell,w in zip(row.cells,widths):
            cell.width=Cm(w)
            for p in cell.paragraphs:
                p.paragraph_format.space_before=Pt(3)
                p.paragraph_format.space_after=Pt(3)
                for r in p.runs: r.font.size=Pt(9)
docx_path=HERE/(STEM+'.docx')
doc.save(docx_path)
docx_check=renderer.verify(docx_path)

pdfmetrics.registerFont(TTFont('Malgun','/mnt/c/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','/mnt/c/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold',italic='Malgun',boldItalic='MalgunBold')
NAVY=colors.HexColor('#153B55'); TEAL=colors.HexColor('#087F8C'); INK=colors.HexColor('#253544')
styles={
 'body':ParagraphStyle('body',fontName='Malgun',fontSize=9.4,leading=15,wordWrap='CJK',spaceAfter=7,textColor=INK,splitLongWords=True),
 'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=16,leading=22,wordWrap='CJK',spaceBefore=15,spaceAfter=9,keepWithNext=True,textColor=NAVY),
 'h3':ParagraphStyle('h3',fontName='MalgunBold',fontSize=11.4,leading=17,wordWrap='CJK',spaceBefore=11,spaceAfter=7,keepWithNext=True,textColor=TEAL),
 'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=8.4,leading=12.7,wordWrap='CJK',textColor=INK,splitLongWords=True),
 'th':ParagraphStyle('th',fontName='MalgunBold',fontSize=8.4,leading=12.7,wordWrap='CJK',textColor=colors.white),
 'code':ParagraphStyle('code',fontName='Malgun',fontSize=8.4,leading=12.3,wordWrap='CJK',leftIndent=8,rightIndent=8,backColor=colors.HexColor('#F2F5F7'),spaceAfter=1),
 'cover':ParagraphStyle('cover',fontName='MalgunBold',fontSize=28,leading=40,textColor=NAVY,spaceAfter=23,wordWrap='CJK'),
}

def inlines(t):
    out=[]
    for c in t.children or []:
        if c.type in ('text','code_inline'): out.append(escape(c.content))
        elif c.type in ('softbreak','hardbreak'): out.append('<br/>')
        elif c.type=='strong_open': out.append('<b>')
        elif c.type=='strong_close': out.append('</b>')
        elif c.type=='em_open': out.append('<i>')
        elif c.type=='em_close': out.append('</i>')
        elif c.type=='link_open': out.append('<link href="'+escape(c.attrGet('href'),quote=True)+'" color="#087F8C">')
        elif c.type=='link_close': out.append('</link>')
        else: raise ValueError(c.type)
    return ''.join(out)

class PDFDocument(SimpleDocTemplate):
    def afterFlowable(self,flow):
        if hasattr(flow,'heading_key'):
            self.canv.bookmarkPage(flow.heading_key)
            self.canv.addOutlineEntry(flow.getPlainText(),flow.heading_key,level=0,closed=False)

def page_decor(canvas,document):
    canvas.saveState()
    if document.page>1:
        canvas.setFont('Malgun',7.5); canvas.setFillColor(colors.HexColor('#617585'))
        canvas.drawString(45,A4[1]-27,'외규 API 및 웹 문서 수집 구축 요청서  |  뭉타 전달용')
        canvas.setStrokeColor(colors.HexColor('#D7E2E8')); canvas.line(45,A4[1]-34,A4[0]-45,A4[1]-34)
    canvas.setFont('Malgun',7.5); canvas.setFillColor(colors.HexColor('#617585'))
    canvas.drawRightString(A4[0]-45,25,f'2026.10.23  |  {document.page}')
    canvas.restoreState()

story=[Spacer(1,70),Paragraph('DOCUMENT COLLECTION REQUEST',styles['h3']),
       Paragraph('외규 API 및 웹 문서<br/>수집 구축 요청서',styles['cover']),
       Paragraph('뭉타 구축 담당자 전달용<br/>2026년 10월 23일 · 버전 1.0',styles['body']),Spacer(1,30),
       Paragraph('API 49종  +  크롤링 19종',styles['h2']),
       Paragraph('원본 수집 · 판본 관리 · AIDP 인계',styles['h3']),Spacer(1,30),
       Paragraph('인증·주소·파라미터부터 배치, 저장 구조, 실패 처리와 검수까지<br/>확인된 명세와 운영 협의 사항을 구분했습니다.',styles['body']),PageBreak(),Paragraph('목차',styles['h2'])]
for n,t in enumerate(tokens):
    if t.type=='heading_open' and t.tag=='h2':
        story.append(Paragraph('<link href="#section_'+str(n)+'" color="#153B55">'+escape(plain(tokens[n+1]))+'</link>',styles['h3']))
story.append(PageBreak())
i=0; list_stack=[]; tables=[]
while i<len(tokens):
    t=tokens[i]
    if t.type=='heading_open':
        if t.tag!='h1':
            p=Paragraph(inlines(tokens[i+1]),styles['h2' if t.tag=='h2' else 'h3'])
            if t.tag=='h2': p.heading_key='section_'+str(i)
            story.append(p)
        i+=3; continue
    if t.type=='paragraph_open':
        text=inlines(tokens[i+1])
        if list_stack:
            prefix='• ' if list_stack[-1][0]=='bullet' else str(list_stack[-1][1])+'. '
            list_stack[-1][1]+=1; text=prefix+text
        story.append(Paragraph(text,styles['body'])); i+=3; continue
    if t.type=='table_open':
        rows,j=get_table(i); tables.append(rows)
        heads=[plain(c) for c in rows[0]]
        table_data=[[Paragraph(inlines(c),styles['th' if ri==0 else 'cell']) for c in row] for ri,row in enumerate(rows)]
        tab=Table(table_data,colWidths=[(A4[0]-90)*x for x in proportions(heads)],repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#EDF4F7'),colors.white]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.5,TEAL)]))
        story.extend([tab,Spacer(1,9)]); i=j; continue
    if t.type=='fence':
        code_lines=[Paragraph(escape(line),styles['code']) if line else Spacer(1,6) for line in t.content.rstrip().splitlines()]
        story.extend([KeepTogether(code_lines),Spacer(1,8)])
    elif t.type=='bullet_list_open': list_stack.append(['bullet',1])
    elif t.type=='ordered_list_open': list_stack.append(['ordered',int(t.attrGet('start') or 1)])
    elif t.type in ('bullet_list_close','ordered_list_close'): list_stack.pop()
    elif t.type in ('list_item_open','list_item_close','blockquote_open','blockquote_close'): pass
    else: raise ValueError(t.type)
    i+=1
pdf_path=HERE/(STEM+'.pdf')
PDFDocument(str(pdf_path),pagesize=A4,rightMargin=45,leftMargin=45,topMargin=48,bottomMargin=43,
            title=TITLE,author='외규 수집 구축 요청').build(story,onFirstPage=page_decor,onLaterPages=page_decor)

wb=Workbook(); wb.remove(wb.active)
def sheet(name,headers,rows,widths):
    ws=wb.create_sheet(name); ws.append(headers)
    for row in rows: ws.append(row)
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for ci,width in enumerate(widths,1): ws.column_dimensions[get_column_letter(ci)].width=width
    for row in ws:
        lines=1
        for cell in row:
            cell.font=Font(name='맑은 고딕',size=10,color='FFFFFF' if cell.row==1 else '253544',bold=cell.row==1)
            cell.fill=PatternFill('solid',fgColor='153B55' if cell.row==1 else 'EDF4F7' if cell.row%2==0 else 'FFFFFF')
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            cell.border=Border(bottom=Side(style='hair',color='D7E2E8'))
            cell.number_format='@'
            val=str(cell.value or '')
            weighted=sum(2 if ord(c)>127 else 1 for c in val)
            lines=max(lines,ceil(weighted/max(5,widths[cell.column-1]-2)))
            if val.startswith('https://') and ' ' not in val:
                cell.hyperlink=val
        ws.row_dimensions[row[0].row].height=min(160,max(30,lines*15+8))
    ws.sheet_view.showGridLines=False
    ws.print_options.horizontalCentered=True
    ws.page_setup.orientation='landscape'; ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.print_title_rows='1:1'
    return ws

sheet('안내',['항목','내용'],[
('문서','외규 API 및 웹 문서 수집 구축 요청서 / 2026-10-23 / 뭉타 전달용'),
('범위','자동 68종 = API 49종(법령37·행정규칙12) + 웹19종(거래소규정9·금투협5·공개별첨5)'),
('별도','수동 반입10종·제외2종을 포함해 원래 지정80종을 전체목록 시트에 대조'),
('주소','요청주소26은 API·웹 요청 단계별 명세다. 동일 URL에 다른 요청 역할이 있는 경우 행을 나눔'),
('인증','OC는 {LAW_OC} 자리표시자. 실제 인증값·사내 주소는 포함하지 않음'),
('과거ID','과거보관ID·시행일은 2026-09-17 카탈로그 기준 참고값. 최신 판본·현재 원천 ID로 사용하지 말 것'),
('웹경로','기존 코드·수집기록 기준. E2 공개 별첨 HTTP method와 최신 게시물 탐색 요청은 추가 확인'),
('배치','06:00 일일·08:30 현황·일요일18:00 대조는 제안. 실제 스케줄 등록 없음'),
('문서우선','상세 조건·실패 처리·저장·검수는 함께 제공한 DOCX/PDF를 따른다')],[22,115])
sheet('전체목록80',['관리번호','구분','처리','문서명','요청프로필','진입주소','목록 요청 파라미터','과거보관ID 참고','과거시행일 참고'],[
    [r['id'],r['group'],r['status'],r['name'],r['profile'],r['entry_url'],r['request_parameters'],r['historical_id'],r['historical_effective']] for r in inventory],[12,9,13,62,20,65,85,22,20])
sheet('요청주소26',['ID','그룹','HTTP 방식','전체 요청주소','파라미터','응답 형식','주의사항','확인근거'],[
    [e[k] for k in ['code','group','method','url','params','response','note','evidence']] for e in endpoints],[12,18,25,65,90,30,75,40])
param_rows=[]
for rows in tables:
    if [plain(c) for c in rows[0]]==['요청','파라미터','요청값·의미']:
        group='A 법령' if not param_rows else 'B 행정규칙'
        param_rows.extend([[group]+[plain(c) for c in row] for row in rows[1:]])
sheet('API파라미터',['API 그룹','요청','파라미터','값·의미'],param_rows,[18,20,25,100])
for name,header in [('배치제안','작업'),('인계메타','필드'),('확정항목','확정 항목')]:
    selected=next(rows for rows in tables if plain(rows[0][0])==header)
    heads=[plain(c) for c in selected[0]]
    sheet(name,heads,[[plain(c) for c in row] for row in selected[1:]], [28,95] if len(heads)==2 else [35,60,80])
xlsx_path=HERE/'외규_전체문서_API주소_파라미터_20261023.xlsx'; wb.save(xlsx_path)
loaded=load_workbook(xlsx_path,data_only=False)
assert loaded['전체목록80'].max_row==81
assert loaded['요청주소26'].max_row==27
assert len({r[0].value for r in loaded['전체목록80'].iter_rows(min_row=2)})==80

pdf=fitz.open(pdf_path)
pdf_text=''.join(page.get_text() for page in pdf)
compact=lambda s:re.sub(r'\s+','',s)
expected=[plain(t) for t in tokens if t.type=='inline']
missing=[x for x in expected if compact(x) not in compact(pdf_text)]
# The source H1 is presented as the cover title with a deliberate line break.
assert not missing, missing[:3]
outside=[]
for pn,page in enumerate(pdf,1):
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines',[]):
            for span in line['spans']:
                x0,y0,x1,y1=span['bbox']
                if x0<40 or x1>page.rect.width-38 or y0<10 or y1>page.rect.height-15:
                    outside.append({'page':pn,'text':span['text'],'bbox':span['bbox']})
assert not outside,outside[:3]
preview_dir=HERE/'preview'; preview_dir.mkdir(exist_ok=True)
for pn in sorted(set([0,2,4,8,12,len(pdf)-1])):
    if pn<len(pdf): pdf[pn].get_pixmap(matrix=fitz.Matrix(1.1,1.1)).save(preview_dir/f'page-{pn+1:02d}.png')

source_files=[
 '01_DATA/CATALOG/SCOPES/photo-required-80-hwpx-20260917.json',
 '01_DATA/CATALOG/BUILD_EXCLUSIONS.json',
 '02_BACKEND/lawrag/sources/lawgo.py','02_BACKEND/lawrag/sources/krx.py',
 '02_BACKEND/lawrag/sources/kofia.py','02_BACKEND/lawrag/sources/common.py',
 '02_BACKEND/lawrag/pipeline/collect.py','02_BACKEND/lawrag/core/structure/rulehtml.py',
 '00_SYSTEM/ARCHITECTURE.md','GENOS.md',
 '01_DATA/PACKAGES/EXTERNAL/photo-required-public-supplement-f24dc8270c903716/gen-f24dc8270c90371698f32c83/ARTIFACTS/SOURCE_MANIFEST.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
validation={
 'date':'2026-10-23','review':'author self-review; no independent reviewer',
 'counts':{'law':37,'admrul':12,'krx_rules':9,'kofia':5,'krx_forms':5,'automatic':68,'manual':10,'excluded':2,'total':80,'request_profiles':26},
 'docx':docx_check,'pdf':{'pages':len(pdf),'text_units_checked':len(expected),'missing_text':missing,'outside_page_bounds':outside,'rendered_from':'same Markdown source; not a DOCX print rendering','visual_review':'pending'},
 'xlsx':{'sheets':loaded.sheetnames,'inventory_rows':80,'endpoint_rows':26,'readback':'PASS'},
 'artifacts':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in [SOURCE,docx_path,pdf_path,xlsx_path]},
 'evidence_files':{s:sha(ROOT/s) for s in source_files},
 'not_performed':['live collection with credentials','production deployment','scheduler registration','MAIN activation','vendor transmission']}
(HERE/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'docx':str(docx_path),'pdf':str(pdf_path),'xlsx':str(xlsx_path),'pages':len(pdf),'tables':len(tables),'checks':'text, inventory, XML links, XLSX readback, PDF bounds passed'},ensure_ascii=False))
