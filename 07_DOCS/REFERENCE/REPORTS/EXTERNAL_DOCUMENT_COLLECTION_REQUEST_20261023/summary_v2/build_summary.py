"""Create a concise two-page handoff; preserve the earlier full specification."""
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
BASE='외규수집_핵심요약_20261023_V2'
NAVY='153B55'; TEAL='087F8C'; PALE='EDF4F7'; INK='253544'
pages=[
 [
  {'kind':'eyebrow','text':'뭉타 전달용  |  2026.10.23  |  요약 V2'},
  {'kind':'title','text':'외규 수집, 요청할 핵심만'},
  {'kind':'lead','text':'원본과 첨부를 주기적으로 수집하고, 판본 정보와 함께 AIDP에 전달합니다.'},
  {'kind':'metrics','items':[('68종','자동 수집 대상'),('49종','법제처 API'),('19종','웹 크롤링')]},
  {'kind':'heading','text':'01  수집 범위'},
  {'kind':'table','headers':['대상','수량','받을 원본'], 'widths':[.42,.12,.46], 'rows':[
   ['법령·시행령·시행규칙','37종','XML 본문 + 별표·서식 파일'],
   ['감독규정·시행세칙 등 행정규칙','12종','XML 본문 + 별표·첨부파일'],
   ['거래소 상장·공시규정 등','9종','전체 HTML + 전문·첨부 원본'],
   ['금투협 규정·모범규준 등','5종','전체 HTML + 전문·첨부 원본'],
   ['거래소 공개 기업실사 별첨','5종','게시판의 첨부 원본 파일']]},
  {'kind':'note','text':'전체 문서명은 Excel 「수집대상68」 참조. 수동 반입 10종·금감원 작성기준/별지서식 2종은 자동 수집에서 제외합니다. 68종에 딸린 첨부는 별도로 수집합니다.'},
  {'kind':'heading','text':'02  배치 타이밍  ·  운영 협의안'},
  {'kind':'table','headers':['언제','무엇을 하나'], 'widths':[.30,.70], 'rows':[
   ['매일 06:00 KST','주말 포함 변경 확인 → 변경된 원문·첨부 수집'],
   ['매일 08:30 KST','성공·미완료·실패와 마지막 정상 확인 시각 보고'],
   ['일요일 18:00 KST','전체 목록·파일 재대조; 같은 URL의 파일 교체 확인']]},
  {'kind':'note','text':'최초 전체 적재는 별도 1회. 구조화·DB 적재는 원본 검증이 끝난 뒤 시작합니다. 배치 시각은 제안이며 완료 보장 시각은 아닙니다.'},
  {'kind':'heading','text':'03  저장과 납품'},
  {'kind':'table','headers':['저장 대상','저장 위치'], 'widths':[.42,.58], 'rows':[
   ['XML·HTML·HWP/HWPX·PDF·이미지','AIDP 원본 저장소 / Dataiku 관리 폴더'],
   ['조문·표·용어·관계·위키','Oracle 골드 레이어'],
   ['LLM 질의·판단·실행 기록','에이전트 레이어']]},
  {'kind':'callout','text':'뭉타 납품: 수집 코드 + 배치·실패 재개 + 원본·메타데이터 + AIDP 인계 연결'},
  {'kind':'note','text':'S3 사용 여부·관리 폴더는 AIDP 담당자와 확정합니다. 현재 확인한 연결은 SFTP 기반입니다. GENOS 코드서빙에는 원문을 영구 보관하지 않습니다.'}
 ],
 [
  {'kind':'eyebrow','text':'구현 담당자 확인용  |  상세 요청 주소·문서별 매핑은 Excel 별첨'},
  {'kind':'title','text':'API·크롤링 구현 조건'},
  {'kind':'heading','text':'04  API  ·  같은 API는 함께 묶기'},
  {'kind':'lead','text':'인증: 승인된 OC(API 인증값) 1개로 대상 서비스 사용 범위를 확인합니다. 반환 형식은 XML로 통일하고 실제 키는 비밀 설정으로 주입합니다.'},
  {'kind':'url','text':'목록 GET  https://www.law.go.kr/DRF/lawSearch.do\n본문 GET  https://www.law.go.kr/DRF/lawService.do'},
  {'kind':'table','headers':['구분','필수 요청값'], 'widths':[.25,.75], 'rows':[
   ['법령 목록 37종','target=eflaw · nw=2,3(시행예정·현행)'],
   ['법령 본문','target=eflaw · MST=법령일련번호 · efYd=해당 판본 시행일'],
   ['행정규칙 목록 12종','target=admrul · nw=1(현행)'],
   ['행정규칙 본문','target=admrul · ID=행정규칙일련번호']]},
  {'kind':'note','text':'공통: OC={LAW_OC}, type=XML. 목록: search=1, query=정식 문서명, display=100, page=1부터 끝까지. 법령 현행 본문만 조회할 때는 ID=법령ID를 쓰고 MST·efYd는 생략합니다.'},
  {'kind':'note','text':'첨부는 XML의 실제 링크를 따라 파일로 받습니다. 대표 경로: https://www.law.go.kr/LSW/flDownload.do?flSeq={응답값}. 시행예정 판본은 현행과 구분해 저장합니다.'},
  {'kind':'heading','text':'05  크롤링  ·  HTML과 원본 첨부를 함께 받기'},
  {'kind':'table','headers':['원천','수집 방식·받는 구조'], 'widths':[.28,.72], 'rows':[
   ['거래소 규정 9종\nrule.krx.co.kr','규정 트리 → 현행 판본 → HTML·파일.\nPOST·Cookie·CSRF 갱신 필요.'],
   ['금투협 5종\nlaw.kofia.or.kr','규정 seq → 현행 historySeq → HTML·파일.\n규정ID·판본ID·첨부ID 구분.'],
   ['거래소 공개 별첨 5종\nlisting.krx.co.kr','게시판 변경 확인 → file.krx.co.kr 원본 다운로드.\n최신 게시물·첨부 탐색 요청은 착수 시 확인.']]},
  {'kind':'note','text':'HTTP 수집 우선, 동적 화면에 필요한 경우만 Selenium 사용. HTML은 장·조·항·호·목, 표 셀 병합, 각주·이미지를 보존합니다. 화면 캡처·텍스트 추출만으로 완료 처리하지 않습니다.'},
  {'kind':'heading','text':'06  인계에 꼭 포함할 것'},
  {'kind':'callout','text':'원본 파일 + 문서명·출처 URL·문서/판본 ID·시행일·수집 시각·SHA-256·저장 경로 + 첨부 관계·성공/실패 상태'},
  {'kind':'note','text':'이전 판본은 덮어쓰지 않습니다. HTTP 200이어도 오류 화면인지 검사하고, 첨부 미확보는 부분 성공으로 표시합니다. 재개 시 성공 파일을 재사용하며 중복 적재를 막습니다.'},
  {'kind':'heading','text':'착수 전, 이 3가지만 확정'},
  {'kind':'confirm','text':'① OC·중계 연결  —  GET/POST·세션·파일 응답 지원\n② AIDP 저장소  —  S3/SFTP·관리 폴더·권한·용량\n③ 사이트 수집 조건  —  허용 범위·호출 한도·공개 별첨 탐색'},
  {'kind':'note','text':'호출 간격 최소 1초·동시 1개는 제안값입니다. 이용 조건을 확인하고 차단·캡차는 중단합니다. 상세 요청 26개와 문서별 파라미터는 Excel 「요청주소26」에 있습니다.'},
  {'kind':'source','text':'근거: 법제처 공식 API 가이드 + 기존 KRX·금투협 수집 코드/원본 기록. 2026-10-23 확인. 이 문서는 구축 요청안이며 운영 실행·배포 완료를 뜻하지 않습니다.'}
 ]]
(OUT/'SUMMARY_CONTENT.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')

doc=Document();sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.45);sec.bottom_margin=Cm(1.35);sec.left_margin=sec.right_margin=Cm(1.6)
sec.header_distance=sec.footer_distance=Cm(.65)
for name in ['Normal','Body Text']:
 s=doc.styles[name];s.font.name='Malgun Gothic';s.font.size=Pt(9.5)
 s.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Malgun Gothic')
 s.paragraph_format.space_after=Pt(4);s.paragraph_format.line_spacing=1.08
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
footer.add_run('외규 수집 핵심요약 V2  |  ')
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
  runfont(p.add_run(b['text']),size,bold,col)
doc.core_properties.title='외규 수집 핵심요약 V2';doc.core_properties.subject='API 49종·크롤링 19종 / 뭉타 전달용'
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
  p=ptext(b['text'],style[k])
  if k in ['title','heading']:p.keepWithNext=True
  if k in ['callout','confirm']:
   box=Table([[p]],colWidths=[W]);box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#'+PALE)),('BOX',(0,0),(-1,-1),.6,colors.HexColor('#'+TEAL)),('LEFTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
   story.extend([box,Spacer(1,6)])
  else:story.append(p)
def footer_pdf(c,d):
 c.saveState();c.setFont('Malgun',7.5);c.setFillColor(colors.HexColor('#617585'))
 c.drawString(44,23,'외규 수집 핵심요약 V2  |  뭉타 전달용')
 c.drawRightString(A4[0]-44,23,str(d.page));c.restoreState()
pdf=OUT/(BASE+'.pdf')
SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=38,bottomMargin=37,title='외규 수집 핵심요약 V2',author='손형진').build(story,onFirstPage=footer_pdf,onLaterPages=footer_pdf)

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
xlsx=OUT/'외규수집_문서목록_요청주소_별첨_V2.xlsx';wb.save(xlsx)

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
assert len(pdfdoc)==2,f'Expected 2 pages, got {len(pdfdoc)}'
with ZipFile(docx) as z:
 assert z.testzip() is None
 from lxml import etree
 root=etree.fromstring(z.read('word/document.xml'))
 text=''.join(root.xpath('//w:t/text()',namespaces={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}))
 assert all(normalize(s) in normalize(text) for s in expected)
book=load_workbook(xlsx);assert book['수집대상68'].max_row==69;assert book['요청주소26'].max_row==27;assert book['수동·제외12'].max_row==13
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
validation={'version':'summary-v2','pdf_pages':len(pdfdoc),'content_units_verified':len(expected),'docx_xml_text':'PASS','docx_visual_render':'not performed; separate PDF rendered from same content','pdf_text_bounds':'PASS','pdf_visual_review':'pending','xlsx_rows':{'automatic':68,'requests':26,'manual_excluded':12},'files':files,'original_20page_report':'preserved; not included in outgoing email'}
(OUT/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(validation,ensure_ascii=False))
