"""Export the maintained repository guide to editable Word and a readable PDF."""
from pathlib import Path
import hashlib
import json
import re
from html import escape
from urllib.parse import quote
import zipfile

from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, KeepTogether
import fitz

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCES=ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022'
SOURCE=SOURCES/'GOLD_AUTHORING_GUIDE_20261028.md'
STEM='법률에이전트_골드테이블_컬럼_작성가이드_20261028'
PDF=HERE/(STEM+'.pdf')
DOCX=HERE/(STEM+'.docx')
NAVY='#20354D';TEAL='#276B63';LIGHT='#F1F5F8';LINE='#CDD8E3'
FONT='/mnt/c/Windows/Fonts/malgun.ttf'
BOLD='/mnt/c/Windows/Fonts/malgunbd.ttf'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def parse(text):
    out=[];lines=text.splitlines();i=0
    while i<len(lines):
        l=lines[i].strip()
        if not l:i+=1;continue
        if l=='<!-- PAGE_BREAK -->':out.append(('break',None));i+=1;continue
        if l.startswith('# '):out.append(('title',l[2:]));i+=1;continue
        if l.startswith('## '):out.append(('heading',l[3:]));i+=1;continue
        if l.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                vals=[v.strip() for v in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(':?-+:?',v) for v in vals):rows.append(vals)
                i+=1
            out.append(('table',rows));continue
        if l.startswith('- '):out.append(('bullet',l[2:]));i+=1;continue
        if re.match(r'^\d+\. ',l):out.append(('number',l));i+=1;continue
        paras=[l];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].lstrip().startswith(('#','|','- ','<!--')):
            if re.match(r'^\d+\. ',lines[i].strip()):break
            paras.append(lines[i].strip());i+=1
        out.append(('source' if l.startswith('근거:') else 'para',' '.join(paras)))
    return out

def plain(s):
    s=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',s)
    return s.replace('**','').replace('`','')

def inline_pdf(s):
    s=escape(s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font color="#276B63">\1</font>',s)
    return s

def add_word_inline(p,s):
    parts=re.split(r'(\*\*.*?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))',s)
    for part in parts:
        if not part:continue
        if part.startswith('**'):
            run=p.add_run(part[2:-2]);run.bold=True
        elif part.startswith('`'):
            run=p.add_run(part[1:-1]);run.font.color.rgb=RGBColor.from_string('276B63')
        elif re.fullmatch(r'\[[^\]]+\]\([^)]+\)',part):
            match=re.match(r'\[([^\]]+)\]\(([^)]+)\)',part)
            run=p.add_run(match[1]);run.font.color.rgb=RGBColor.from_string('276B63')
            # Local paths remain visible in the maintained Markdown source.
        else:p.add_run(part)

def widths(rows,total):
    n=len(rows[0])
    ratios={2:[.28,.72],3:[.24,.34,.42],4:[.20,.26,.27,.27]}.get(n,[1/n]*n)
    if rows[0][0] in ('순서','확인'):ratios=[.09]+[.91/(n-1)]*(n-1)
    if rows[0][0]=='개발계 계약':ratios=[.31,.47,.22]
    return [r*total for r in ratios]

def word(blocks):
    d=Document();s=d.sections[0]
    s.page_width=Mm(210);s.page_height=Mm(297)
    s.top_margin=Mm(18);s.bottom_margin=Mm(18);s.left_margin=Mm(18);s.right_margin=Mm(18)
    s.header_distance=Mm(8);s.footer_distance=Mm(8)
    for name in ('Normal','Title','Heading 1','Heading 2'):
        st=d.styles[name];st.font.name='맑은 고딕';st._element.rPr.rFonts.set(qn('w:eastAsia'),'맑은 고딕')
    normal=d.styles['Normal'];normal.font.size=Pt(10)
    normal.paragraph_format.line_spacing=1.16;normal.paragraph_format.space_after=Pt(6)
    d.styles['Title'].font.size=Pt(22);d.styles['Title'].font.bold=True;d.styles['Title'].font.color.rgb=RGBColor.from_string('20354D')
    d.styles['Heading 1'].font.size=Pt(16);d.styles['Heading 1'].font.color.rgb=RGBColor.from_string('20354D')
    d.styles['Heading 1'].paragraph_format.space_after=Pt(10)
    hp=s.header.paragraphs[0];hp.text='3·5번 법률 에이전트  |  골드 데이터 작성 기준';hp.runs[0].font.size=Pt(8);hp.runs[0].font.color.rgb=RGBColor.from_string('64748B')
    fp=s.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    fp.add_run('2026-10-28  ·  ')
    fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');fp._p.append(fld)
    for kind,value in blocks:
        if kind=='break':d.add_page_break();continue
        if kind=='table':
            t=d.add_table(rows=0,cols=len(value[0]));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
            ws=widths(value,174)
            for c,w in zip(t.columns,ws):c.width=Mm(w)
            for idx,row in enumerate(value):
                cells=t.add_row().cells
                for cell,txt,width in zip(cells,row,ws):
                    cell.width=Mm(width);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(3);p.paragraph_format.space_before=Pt(3);p.paragraph_format.line_spacing=1.08
                    add_word_inline(p,txt)
                    for run in p.runs:run.font.size=Pt(9)
                    tcPr=cell._tc.get_or_add_tcPr();shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'20354D' if idx==0 else ('F1F5F8' if idx%2 else 'FFFFFF'));tcPr.append(shade)
                    if idx==0:
                        for r in p.runs:r.bold=True;r.font.color.rgb=RGBColor(255,255,255)
                if idx==0:
                    repeat=OxmlElement('w:tblHeader');t.rows[idx]._tr.get_or_add_trPr().append(repeat)
                keep=OxmlElement('w:cantSplit');t.rows[idx]._tr.get_or_add_trPr().append(keep)
            d.add_paragraph().paragraph_format.space_after=Pt(1)
            continue
        if kind=='title':p=d.add_paragraph(style='Title')
        elif kind=='heading':p=d.add_paragraph(style='Heading 1')
        else:p=d.add_paragraph()
        add_word_inline(p,('• ' if kind=='bullet' else '')+value)
        if kind=='source':
            for r in p.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('64748B')
        if kind in ('bullet','number'):p.paragraph_format.space_after=Pt(4)
    d.core_properties.title='법률 에이전트 골드 테이블과 컬럼 작성 가이드'
    d.core_properties.subject='사용자 녹취·PPT·골드 안내·엑셀 양식 통합 작성 기준'
    d.core_properties.author='법률 에이전트 프로젝트'
    d.save(DOCX)

def pdf(blocks):
    pdfmetrics.registerFont(TTFont('Malgun',FONT))
    pdfmetrics.registerFont(TTFont('MalgunBold',BOLD))
    pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold',italic='Malgun',boldItalic='MalgunBold')
    sty={
     'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=20,leading=28,textColor=colors.HexColor(NAVY),spaceAfter=10,wordWrap='CJK',keepWithNext=True),
     'heading':ParagraphStyle('heading',fontName='MalgunBold',fontSize=15.5,leading=23,textColor=colors.HexColor(NAVY),spaceAfter=12,wordWrap='CJK',keepWithNext=True),
     'para':ParagraphStyle('para',fontName='Malgun',fontSize=10,leading=15.3,spaceAfter=9,wordWrap='CJK'),
     'source':ParagraphStyle('source',fontName='Malgun',fontSize=8,leading=12,textColor=colors.HexColor('#64748B'),spaceBefore=3,spaceAfter=3,wordWrap='CJK'),
     'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=8.7,leading=12.8,wordWrap='CJK'),
     'th':ParagraphStyle('th',fontName='MalgunBold',fontSize=9,leading=13.2,wordWrap='CJK',textColor=colors.white),
    }
    story=[];total_width=A4[0]-102
    for kind,value in blocks:
        if kind=='break':story.append(PageBreak());continue
        if kind=='table':
            data=[[Paragraph(inline_pdf(v),sty['th'] if i==0 else sty['cell']) for v in row] for i,row in enumerate(value)]
            t=Table(data,colWidths=widths(value,total_width),repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor(LIGHT),colors.white]),('LINEBELOW',(0,0),(-1,-1),.35,colors.HexColor(LINE)),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.extend([t,Spacer(1,9)]);continue
        text=('• ' if kind=='bullet' else '')+value
        story.append(Paragraph(inline_pdf(text),sty.get(kind,sty['para'])))
    def draw(c,d):
        c.setFont('Malgun',8);c.setFillColor(colors.HexColor('#64748B'))
        c.drawString(51,A4[1]-29,'3·5번 법률 에이전트  |  골드 데이터 작성 기준')
        c.setStrokeColor(colors.HexColor(LINE));c.line(51,A4[1]-37,A4[0]-51,A4[1]-37)
        c.drawString(51,26,'2026-10-28 · 사용자 제공 녹취와 PPT 사진 통합')
        c.drawRightString(A4[0]-51,26,str(d.page))
    doc=SimpleDocTemplate(str(PDF),pagesize=A4,leftMargin=51,rightMargin=51,topMargin=51,bottomMargin=45,title='법률 에이전트 골드 테이블과 컬럼 작성 가이드',author='법률 에이전트 프로젝트')
    doc.build(story,onFirstPage=draw,onLaterPages=draw)

def validate(blocks):
    with zipfile.ZipFile(DOCX) as z:assert z.testzip() is None
    wd=Document(DOCX)
    assert len(wd.tables)==sum(1 for k,_ in blocks if k=='table')
    pdfdoc=fitz.open(PDF);texts=[p.get_text() for p in pdfdoc]
    alltext='\n'.join(texts)
    headings=[plain(v) for k,v in blocks if k=='heading']
    locations={h:[i+1 for i,t in enumerate(texts) if h in t] for h in headings}
    assert all(locations.values()),locations
    for token in ('49컬럼','34개','512 BYTE','30바이트','표준용어','원문좌표해시값','테이블스페이스','00:00–30:27'):
        assert token in alltext,token
    over=[]
    for n,page in enumerate(pdfdoc,1):
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line.get('spans',[]):
                    x0,y0,x1,y1=span['bbox']
                    if x0<35 or x1>page.rect.width-35 or y0<10 or y1>page.rect.height-15:over.append([n,span['text'],span['bbox']])
    assert not over,over
    image_manifest=json.loads((SOURCES/'SOURCE_MANIFEST.json').read_text())
    image_ok=[]
    for item in image_manifest['images']:
        p=SOURCES/item['saved_path'];assert sha(p)==item['sha256'];image_ok.append(item['saved_path'])
    missing_links=[]
    for label,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',SOURCE.read_text()):
        if not (SOURCE.parent/target).resolve().exists():missing_links.append(target)
    assert not missing_links,missing_links
    # Render low-memory page previews from the final PDF.
    preview=HERE/'preview';preview.mkdir(exist_ok=True)
    for i,page in enumerate(pdfdoc):page.get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False).save(preview/f'page-{i+1:02}.png')
    result=dict(status='PASS',source=str(SOURCE.relative_to(ROOT)),source_sha256=sha(SOURCE),pdf_pages=len(pdfdoc),sections=len(headings),section_pages=locations,docx_tables=len(wd.tables),photo_hashes_verified=len(image_ok),local_links_valid=True,pdf_text_in_page_bounds=True,native_word_render=False,source_audio='user_pasted_transcript_00:00-30:27',original_audio_listened=False,files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (PDF,DOCX)})
    (HERE/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    blocks=parse(SOURCE.read_text())
    word(blocks);pdf(blocks);validate(blocks)
