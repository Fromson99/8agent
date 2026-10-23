"""Create a expanded six-page handoff; preserve the earlier full specification."""
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
BASE='외규수집_구축요청_파라미터상세_20261023_V3'
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
footer.add_run('외규 수집 구축요청 V3  |  ')
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
doc.core_properties.title='외규 수집 구축요청 V3';doc.core_properties.subject='API 49종·크롤링 19종 / 뭉타 전달용'
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
 c.drawString(44,23,'외규 수집 구축요청 V3  |  뭉타 전달용')
 c.drawRightString(A4[0]-44,23,str(d.page));c.restoreState()
pdf=OUT/(BASE+'.pdf')
SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=38,bottomMargin=37,title='외규 수집 구축요청 V3',author='손형진').build(story,onFirstPage=footer_pdf,onLaterPages=footer_pdf)

inv=json.loads((PARENT/'DOCUMENT_INVENTORY.json').read_text());eps=json.loads((PARENT/'ENDPOINTS.json').read_text())
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
sheet('수집대상68',['번호','방식','문서명','요청 프로필','진입 주소','목록 요청값'],[
 [r['id'],'API' if r['group'] in ['A','B'] else '크롤링',r['name'],r['profile'],r['entry_url'],r['request_parameters']] for r in inv if r['group'] in 'ABCDE'],[12,13,66,23,70,85])
sheet('요청주소26',['요청 ID','구분','HTTP','전체 주소','파라미터','응답','주의사항'],[
 [e[k] for k in ['code','group','method','url','params','response','note']] for e in eps],[13,20,27,65,90,28,85])
sheet('수동·제외12',['번호','문서명','처리'],[[r['id'],r['name'],'현업 수동 반입' if r['group']=='M' else '이번 수집 제외'] for r in inv if r['group'] in ['M','X']],[13,90,30])
parameter_rows=json.loads((OUT/'PARAMETERS.json').read_text())
sheet('파라미터설명',['그룹','요청 ID','파라미터','필수·선택 조건','값·예시','의미','주의·대체 조건'],parameter_rows,[21,16,48,28,55,65,85])
source_rows=json.loads((PARENT/'SOURCES.json').read_text())
sheet('출처',['근거 ID','설명','공식 URL'],source_rows,[15,38,112])
xlsx=OUT/'외규수집_문서목록_요청주소_파라미터_별첨_V3.xlsx';wb.save(xlsx)

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
assert len(pdfdoc)==6,f'Expected 6 pages, got {len(pdfdoc)}; page starts: {[p.get_text()[:100] for p in pdfdoc]}'
with ZipFile(docx) as z:
 assert z.testzip() is None
 from lxml import etree
 root=etree.fromstring(z.read('word/document.xml'))
 text=''.join(root.xpath('//w:t/text()',namespaces={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}))
 assert all(normalize(s) in normalize(text) for s in expected)
book=load_workbook(xlsx);assert book['파라미터설명'].max_row==len(parameter_rows)+1;assert book['출처'].max_row==len(source_rows)+1;assert book['수집대상68'].max_row==69;assert book['요청주소26'].max_row==27;assert book['수동·제외12'].max_row==13
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
validation={'version':'summary-v3','pdf_pages':len(pdfdoc),'content_units_verified':len(expected),'docx_xml_text':'PASS','docx_visual_render':'not performed; separate PDF rendered from same content','pdf_text_bounds':'PASS','pdf_visual_review':'pending','xlsx_rows':{'automatic':68,'requests':26,'manual_excluded':12,'parameter_descriptions':len(parameter_rows),'sources':len(source_rows)},'files':files,'original_20page_report':'preserved; not included in outgoing email'}
(OUT/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(validation,ensure_ascii=False))
