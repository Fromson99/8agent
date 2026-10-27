"""Create a three-page API settings appendix; preserve the earlier full specification."""
from pathlib import Path
import json, hashlib, re
from html import escape
from zipfile import ZipFile
from math import ceil
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
import fitz

OUT=Path(__file__).resolve().parent
PARENT=OUT.parent
BASE='API_최신화_대상49종_설정부록A_20261023'
NAVY='153B55'; TEAL='087F8C'; PALE='EDF4F7'; INK='253544'
pages=json.loads((OUT/'SUMMARY_CONTENT.json').read_text())

doc=Document();sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.45);sec.bottom_margin=Cm(1.35);sec.left_margin=sec.right_margin=Cm(1.6)
sec.header_distance=sec.footer_distance=Cm(.65)
for name in ['Normal','Body Text']:
 s=doc.styles[name];s.font.name='Malgun Gothic';s.font.size=Pt(9.5)
 s.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Malgun Gothic')
 s.paragraph_format.space_after=Pt(4);s.paragraph_format.line_spacing=1.08
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
footer.add_run('API 최신화 대상·설정 부록 A  |  ')
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
for r in footer.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('617585')
def runfont(run,size=9.5,bold=False,color=INK):
 run.font.name='Malgun Gothic';run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Malgun Gothic')
 run.font.size=Pt(size);run.bold=bold;run.font.color.rgb=RGBColor.from_string(color)
def shade(cell,color):
 e=OxmlElement('w:shd');e.set(qn('w:fill'),color);cell._tc.get_or_add_tcPr().append(e)
def dtable(rows,widths,metrics=False):
 tab=doc.add_table(rows=0,cols=len(widths));tab.autofit=False;tab.alignment=WD_TABLE_ALIGNMENT.CENTER
 for c,w in zip(tab.columns,widths):c.width=Cm(17.8*w)
 for ri,row in enumerate(rows):
  tr=tab.add_row();pr=tr._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
  if ri==0:pr.append(OxmlElement('w:tblHeader'))
  for ci,text in enumerate(row):
   c=tr.cells[ci];c.width=Cm(17.8*widths[ci]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
   shade(c,NAVY if ri==0 else PALE if ri%2 else 'FFFFFF')
   p=c.paragraphs[0];p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(4)
   runfont(p.add_run(text),10.5 if metrics else 9.1,ri==0,'FFFFFF' if ri==0 else INK)
 doc.add_paragraph().paragraph_format.space_after=Pt(0)
for pi,blocks in enumerate(pages):
 if pi:doc.add_page_break()
 for b in blocks:
  k=b['kind']
  if k=='metrics':dtable([[a+'\n'+z for a,z in b['items']]],[1/3]*3,True);continue
  if k=='table':dtable([b['headers']]+b['rows'],b['widths']);continue
  p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(5)
  size,bold,col={'eyebrow':(8,False,TEAL),'title':(21,True,NAVY),'lead':(10,False,INK),'heading':(12,True,TEAL),'note':(8.5,False,INK),'url':(8.8,False,INK),'callout':(10,True,NAVY),'confirm':(9.3,True,NAVY),'source':(7.7,False,'617585')}[k]
  if k in ['title','heading']:p.paragraph_format.keep_with_next=True
  if k=='heading':p.paragraph_format.space_before=Pt(6)
  if k in ['callout','url','confirm']:
   e=OxmlElement('w:shd');e.set(qn('w:fill'),PALE);p._p.get_or_add_pPr().append(e)
  if b.get('href'):
   from docx.opc.constants import RELATIONSHIP_TYPE as RT
   rid=doc.part.relate_to(b['href'],RT.HYPERLINK,is_external=True)
   link=OxmlElement('w:hyperlink');link.set(qn('r:id'),rid)
   r=OxmlElement('w:r');pr=OxmlElement('w:rPr')
   f=OxmlElement('w:rFonts');f.set(qn('w:ascii'),'Malgun Gothic');f.set(qn('w:eastAsia'),'Malgun Gothic');pr.append(f)
   sz=OxmlElement('w:sz');sz.set(qn('w:val'),str(int(size*2)));pr.append(sz)
   cl=OxmlElement('w:color');cl.set(qn('w:val'),TEAL);pr.append(cl)
   r.append(pr);t=OxmlElement('w:t');t.text=b['text'];r.append(t);link.append(r);p._p.append(link)
  else:runfont(p.add_run(b['text']),size,bold,col)
doc.core_properties.title='API 최신화 대상·설정 부록 A';doc.core_properties.subject='법령37·행정규칙12 / 정기 최신화 구현 요청'
docx=OUT/(BASE+'.docx');doc.save(docx)

pdfmetrics.registerFont(TTFont('Malgun','/mnt/c/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','/mnt/c/Windows/Fonts/malgunbd.ttf'))
W=A4[0]-88
def sty(size=9.5,bold=False,color=INK,space=4,leading=None):
 return ParagraphStyle('x',fontName='MalgunBold' if bold else 'Malgun',fontSize=size,leading=leading or size*1.4,wordWrap='CJK',spaceAfter=space,textColor=colors.HexColor('#'+color),splitLongWords=True)
style={
 'eyebrow':sty(8,False,TEAL,6),'title':sty(22,True,NAVY,9),'lead':sty(10,False,INK,8),
 'heading':sty(12,True,TEAL,6),'note':sty(8.5,False,INK,6),'url':sty(8.7,False,INK,7),
 'callout':sty(9.8,True,NAVY,6),'confirm':sty(9.2,True,NAVY,6),'source':sty(7.4,False,'617585',0)}
def ptext(text,s):return Paragraph(escape(text).replace('\n','<br/>'),s)
def ptable(rows,widths,metrics=False):
 data=[[ptext(v,sty(10.5 if metrics else 9,ri==0,'FFFFFF' if ri==0 else INK,0)) for v in row] for ri,row in enumerate(rows)]
 t=Table(data,colWidths=[W*w for w in widths],hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#'+NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#'+PALE),colors.white]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6 if metrics else 5),('BOTTOMPADDING',(0,0),(-1,-1),6 if metrics else 5)]))
 return t
story=[]
for pi,blocks in enumerate(pages):
 if pi:story.append(PageBreak())
 for b in blocks:
  k=b['kind']
  if k=='metrics':story.extend([ptable([[a+'\n'+z for a,z in b['items']]],[1/3]*3,True),Spacer(1,7)]);continue
  if k=='table':story.extend([ptable([b['headers']]+b['rows'],b['widths']),Spacer(1,6)]);continue
  if k=='heading':story.append(Spacer(1,4))
  p=Paragraph('<link href="'+escape(b['href'],quote=True)+'" color="#087F8C">'+escape(b['text'])+'</link>',style[k]) if b.get('href') else ptext(b['text'],style[k])
  if k in ['title','heading']:p.keepWithNext=True
  if k in ['callout','confirm']:
   box=Table([[p]],colWidths=[W]);box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#'+PALE)),('BOX',(0,0),(-1,-1),.6,colors.HexColor('#'+TEAL)),('LEFTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
   story.extend([box,Spacer(1,6)])
  else:story.append(p)
def footer_pdf(c,d):
 c.saveState();c.setFont('Malgun',7.5);c.setFillColor(colors.HexColor('#617585'))
 c.drawString(44,23,'API 최신화 대상·설정 부록 A  |  뭉타 전달용')
 c.drawRightString(A4[0]-44,23,str(d.page));c.restoreState()
pdf=OUT/(BASE+'.pdf')
SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=38,bottomMargin=37,title='API 최신화 대상·설정 부록 A',author='손형진').build(story,onFirstPage=footer_pdf,onLaterPages=footer_pdf)

wb=Workbook();wb.remove(wb.active)
def sheet(name,headers,rows,widths):
 ws=wb.create_sheet(name);ws.append(headers)
 for row in rows:ws.append(row)
 ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;ws.sheet_view.showGridLines=False
 for i,w in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=w
 for row in ws:
  lines=1
  for c in row:
   c.font=Font(name='맑은 고딕',size=10,bold=c.row==1,color='FFFFFF' if c.row==1 else INK)
   c.fill=PatternFill('solid',fgColor=NAVY if c.row==1 else PALE if c.row%2==0 else 'FFFFFF')
   c.alignment=Alignment(vertical='top',wrap_text=True);c.number_format='@'
   v=str(c.value or '');weight=sum(2 if ord(ch)>127 else 1 for ch in v)
   lines=max(lines,ceil(weight/max(5,widths[c.column-1]-2)))
   if v.startswith('https://') and ' ' not in v:c.hyperlink=v
  ws.row_dimensions[row[0].row].height=min(150,max(28,lines*15+8))
 ws.print_title_rows='1:1';ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True
settings=json.loads((OUT/'REQUEST_SETTINGS.json').read_text());targets=settings['targets']
rows=[]
for r in targets:
 bp='OC={LAW_OC}&type=XML&target=eflaw&MST={목록의 법령일련번호}&efYd={해당 판본 시행일}' if r['group']=='A' else 'OC={LAW_OC}&type=XML&target=admrul&ID={목록의 행정규칙일련번호}'
 rows.append([r['management_id'],r['query'],r['list_params']['target'],r['list_params']['nw'],r['list_url'],r['readable_query'],r['encoded_url_template'],r['body_url'],bp])
sheet('대상49_목록요청',['내부 관리번호','query · 정식 문서명','target','nw','목록 GET URL','전체 목록 파라미터','인코딩 URL 템플릿','본문 GET URL','본문 파라미터 · 매회 응답값 매핑'],rows,[18,65,16,12,60,100,110,60,95])
request_rows=json.loads((OUT/'REQUEST_ROWS.json').read_text())
sheet('본문·첨부요청',['요청','URL','파라미터','조건'],request_rows,[22,70,100,85])
setting_rows=json.loads((OUT/'SETTINGS_ROWS.json').read_text())
sheet('최신화설정',['항목','원하는 설정','설명·조건'],setting_rows,[23,65,110])
source_rows=json.loads((PARENT/'SOURCES.json').read_text())[:4]
sheet('공식근거',['ID','가이드','URL'],source_rows,[12,40,120])
xlsx=OUT/'API_대상49종_파라미터_최신화설정_20261023.xlsx';wb.save(xlsx)
pdfdoc=fitz.open(pdf);joined=''.join(p.get_text() for p in pdfdoc)
normalize=lambda s:re.sub(r'\s+','',s)
expected=[]
for page in pages:
 for b in page:
  if b['kind']=='table':expected.extend(b['headers']);expected.extend(v for row in b['rows'] for v in row)
  elif b['kind']=='metrics':expected.extend(a+'\n'+z for a,z in b['items'])
  else:expected.append(b['text'])
missing=[s for s in expected if normalize(s) not in normalize(joined)]
assert not missing,missing
assert len(pdfdoc)==3,f'Expected 3 pages, got {len(pdfdoc)}; page starts: {[p.get_text()[:100] for p in pdfdoc]}'
with ZipFile(docx) as z:
 assert z.testzip() is None
 from lxml import etree
 root=etree.fromstring(z.read('word/document.xml'))
 text=''.join(root.xpath('//w:t/text()',namespaces={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}))
 assert all(normalize(s) in normalize(text) for s in expected)
book=load_workbook(xlsx)
assert book['대상49_목록요청'].max_row==50
assert book['본문·첨부요청'].max_row==6
assert book['최신화설정'].max_row==len(setting_rows)+1
assert book['공식근거'].max_row==5
from urllib.parse import urlsplit,parse_qs
for r in targets:
 parsed={k:v[0] for k,v in parse_qs(urlsplit(r['encoded_url_template']).query).items()}
 assert parsed==r['list_params'],r['management_id']
 assert normalize(r['query']) in normalize(joined)
outside=[]
for n,p in enumerate(pdfdoc):
 p.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(OUT/f'preview-{n+1}.png')
 for b in p.get_text('dict')['blocks']:
  for line in b.get('lines',[]):
   for span in line['spans']:
    x0,y0,x1,y1=span['bbox']
    if x0<40 or x1>A4[0]-38 or y0<10 or y1>A4[1]-12:outside.append([n+1,span['text']])
assert not outside,outside
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [docx,pdf,xlsx]}
validation={'version':'api-settings-appendix-a','pdf_pages':len(pdfdoc),'content_units_verified':len(expected),'scope':{'laws':37,'administrative_rules':12,'total':49},'docx_xml_text':'PASS','docx_visual_render':'not performed; PDF independently rendered from shared source','pdf_text_bounds':'PASS','pdf_visual_review':'pending','all_49_names_in_pdf':'PASS','encoded_url_roundtrip_49':'PASS','fixed_historical_version_ids':'excluded; bind fresh list response','xlsx_rows':{'targets':49,'requests':5,'settings':len(setting_rows),'sources':4},'files':files,'state':'request specification only; no scheduler or production API changes'}
(OUT/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(validation,ensure_ascii=False))
