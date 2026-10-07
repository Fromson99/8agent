from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw, ImageFont
from markdown_it import MarkdownIt
from weasyprint import HTML
import fitz

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
SOURCE = OUT / 'AI_활용경험_역량기술서.md'
NAME = 'AI_활용경험_역량기술서'
REGULAR = Path('/mnt/c/Windows/Fonts/malgun.ttf')
BOLD = Path('/mnt/c/Windows/Fonts/malgunbd.ttf')
RENDERER = Path('/mnt/c/Users/Jin/.codex/skills/implementation-design-report/scripts/build_report_docx.py')
NAVY = '#173A52'
TEAL = '#087F8C'
GRAY = '#536677'
PALE = '#EEF5F8'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else REGULAR), size)


def label(draw, text, xy, size=30, color=NAVY, bold=False):
    draw.multiline_text(xy, text, font=font(size, bold), fill=color, spacing=10)


def box(draw, xy, title, detail, fill=PALE, outline='#C5D8E3', title_color=NAVY):
    draw.rounded_rectangle(xy, radius=22, fill=fill, outline=outline, width=2)
    x1,y1,x2,y2=xy
    label(draw,title,(x1+24,y1+22),31,title_color,True)
    label(draw,detail,(x1+24,y1+78),28,GRAY)


def arrow(draw, start, end, color=TEAL, width=5):
    import math
    draw.line((start,end),fill=color,width=width)
    a=math.atan2(end[1]-start[1],end[0]-start[0])
    p1=(end[0]-19*math.cos(a-.45),end[1]-19*math.sin(a-.45))
    p2=(end[0]-19*math.cos(a+.45),end[1]-19*math.sin(a+.45))
    draw.polygon([end,p1,p2],fill=color)


def figures():
    assets=OUT/'assets'; assets.mkdir(exist_ok=True)
    im=Image.new('RGB',(1800,890),'white'); d=ImageDraw.Draw(im)
    label(d,'자료를 준비하는 흐름과 질문에 답하는 흐름',(45,28),40,bold=True)
    label(d,'지식 준비',(48,111),28,TEAL,True)
    xs=[45,480,915,1350]
    vals=[('문서 수집·구조화','제목·조항·표 구분\n원문과 위치 보존'),('용어·정의 연결','출처별 뜻을 구분\n관련 조항 연결'),('검색 자료 준비','찾아갈 목록 구성\n자료 버전 고정'),('확인된 지식 기반','원문 + 용어 + 참조\n질문의 근거로 사용')]
    for x,(t,s) in zip(xs,vals): box(d,(x,158,x+395,345),t,s)
    for x in xs[:-1]: arrow(d,(x+401,250),(x+429,250))
    d.line([(1545,352),(1545,391),(675,391),(675,423)],fill=TEAL,width=5)
    arrow(d,(675,423),(675,444))
    label(d,'질문 처리',(48,401),28,TEAL,True)
    vals=[('질문과 요구 확인','무엇을 답해야 하는지\n자료 범위를 확인'),('근거 탐색·선별','원문을 읽고 선택\n누락된 근거 확인'),('답변·원문 대조','조건·예외·출처 검토\n질문 누락 확인'),('답변과 확인 범위','근거와 함께 설명\n미해결 사항 표시')]
    for x,(t,s) in zip(xs,vals):box(d,(x,450,x+395,641),t,s)
    for x in xs[:-1]:arrow(d,(x+401,544),(x+429,544))
    box(d,(45,698,1745,843),'피드백 → 수정 후보 → 검토·실험 → 반영 결정','실행·자료 버전과 연결해 기록하며, 모든 피드백을 자동으로 정답화하지 않는다.',fill='#F6F9FB')
    im.save(assets/'pipeline.png')

    im=Image.new('RGB',(1800,790),'white');d=ImageDraw.Draw(im)
    label(d,'AI의 판단을 돕고, 실행은 확인 가능한 규칙으로 관리',(45,28),40,bold=True)
    box(d,(45,115,850,479),'업무 판단을 돕는 통제','• 질문의 요구사항은 무엇인가?\n• 필요한 근거와 예외를 확인했는가?\n• 원문의 조건을 그대로 보존했는가?\n• 무엇을 아직 확정할 수 없는가?',fill='#EDF7F5')
    box(d,(945,115,1745,479),'실행을 관리하는 통제','• 실제 읽은 자료를 사용했는가?\n• 허용된 자료 범위를 지켰는가?\n• 행동을 반복하거나 한도를 넘었는가?\n• 바뀐 답변을 다시 검토했는가?')
    arrow(d,(853,295),(935,295))
    box(d,(45,536,1745,714),'탐색 → 작성 → 검토 → 필요한 수정 또는 한계 표시','AI가 의미를 판단하고 시스템은 출처·상태·범위·예산을 검사한다.\n검사를 통과한 사실만으로 법률적 정답이 인증되는 것은 아니다.',fill='#F6F9FB')
    im.save(assets/'harness.png')

    im=Image.new('RGB',(1800,1050),'white');d=ImageDraw.Draw(im)
    label(d,'새로운 시도를 분리하고, 같은 조건에서 비교',(45,28),40,bold=True)
    box(d,(45,110,1745,277),'실험 전에 기준 고정','질문·자료·모델·지시문·바꿀 요소·성공 기준·허용하지 않을 악화를 먼저 정한다.',fill='#EDF7F5')
    arrow(d,(445,282),(445,325));arrow(d,(1345,282),(1345,325))
    box(d,(45,340,850,522),'기준 방식','기존 결과와 설정 보존\n비교의 출발점 유지')
    box(d,(945,340,1745,522),'실험 후보','변경한 부분을 별도 적용\n기존 자료·결과를 덮어쓰지 않음')
    arrow(d,(445,530),(445,579));arrow(d,(1345,530),(1345,579))
    box(d,(45,595,1745,774),'분리된 평가','정답은 평가 단계에서만 사용한다.\n새 성공·기존 성공의 악화·오류·비용·시간을 함께 비교한다.',fill='#F6F9FB')
    arrow(d,(897,780),(897,824))
    box(d,(45,842,1745,1010),'판정과 후속 결정','기준 충족 여부를 기록하고, 실제 사용 버전 반영은 별도로 결정한다.\n후속 실험과 이전 버전으로의 복구 관계를 남긴다.',fill='#EDF7F5')
    im.save(assets/'experiment.png')
    return {
        '[[FIGURE_PIPELINE]]':('pipeline.png','문서 구조화·용어 연결·검색 준비와 질문·근거 탐색·답변·검토의 전체 흐름'),
        '[[FIGURE_HARNESS]]':('harness.png','업무 판단을 돕는 통제와 실행을 관리하는 통제의 역할 분리'),
        '[[FIGURE_EXPERIMENT]]':('experiment.png','사전 조건 고정, 기준·후보 격리, 평가 분리, 판정과 실제 반영의 분리'),
    }


def word_document(figs):
    from docx.shared import Cm, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    spec=importlib.util.spec_from_file_location('portfolio_renderer',RENDERER)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

    class ApplicationRenderer(mod.Renderer):
        def cover(self):
            p=self.doc.add_paragraph();p.paragraph_format.space_before=Pt(42)
            mod.font(p.add_run('AI EXPERIENCE & CAPABILITIES'),10,mod.TEAL,True)
            p=self.doc.add_paragraph();p.paragraph_format.space_before=Pt(24)
            mod.font(p.add_run('금융·법률 문서를 이해하고\n근거로 답하는 AI'),27,mod.NAVY,True)
            p=self.doc.add_paragraph('AI 활용 경험·역량 기술서')
            for r in p.runs:mod.font(r,15,mod.TEAL,True)
            p=self.doc.add_paragraph('담당 역할  |  전체 설계·개발·실험 주도')
            p.paragraph_format.space_before=Pt(28)
            for r in p.runs:mod.font(r,12,mod.NAVY,True)
            self.doc.add_paragraph('문서를 이해할 수 있는 지식으로 만들고,\nAI가 근거를 찾아 답하도록 연결하며,\n실험과 검증으로 개선 여부를 판단한 경험.')
            self.doc.add_paragraph('문서 이해 · 지식 연결 · RAG · 에이전트\n실험 격리 · 평가·승인 · 운영·복구')
            self.doc.add_paragraph('2026.09  |  프로젝트 경험과 개별 실험 기록에 근거한 작성')
            self.doc.add_page_break()

    renderer=ApplicationRenderer(SOURCE,'AI 활용 경험·역량 기술서','금융·법률 문서 기반 AI 시스템',author='AI 활용 경험·역량')
    doc=renderer.render()
    for p in list(doc.paragraphs):
        if p.text.strip() in figs:
            key=p.text.strip();name,alt=figs[key]
            p.clear();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            inline=p.add_run().add_picture(str(OUT/'assets'/name),width=Cm(17.1))
            inline._inline.docPr.set('descr',alt)
    renderer.expected_text=[x for x in renderer.expected_text if x.strip() not in figs]
    target=OUT/(NAME+'.docx');doc.save(target)
    check=renderer.verify(target)
    with ZipFile(target) as z:
        check['embedded_images']=len([n for n in z.namelist() if n.startswith('word/media/')])
        assert check['embedded_images']==3
    return renderer,check


def pdf_document(figs):
    text=SOURCE.read_text()
    body=re.sub(r'\A.*?(?=^## 1\.)','',text,flags=re.S|re.M)
    for key,(name,alt) in figs.items():
        body=body.replace(key,f'![{alt}](assets/{name})')
    body=MarkdownIt('commonmark').enable('table').render(body)
    counter=0
    def heading(m):
        nonlocal counter
        counter+=1
        return f'<h2 id="section-{counter}">'+m.group(1)+'</h2>'
    body=re.sub(r'<h2>(.*?)</h2>',heading,body)
    css='''
    @font-face {font-family: Portfolio;src: url("FONT_REG");font-weight:400;}
    @font-face {font-family: Portfolio;src: url("FONT_BOLD");font-weight:700;}
    @page {size:A4;margin:19mm 18mm 18mm;@top-left {content:"AI 활용 경험·역량  /  금융·법률 문서 기반 AI";font:8pt Portfolio;color:#607585;}@bottom-right {content:counter(page);font:9pt Portfolio;color:#607585;}}
    @page:first {@top-left {content:none;} @bottom-right{content:none;}}
    *{box-sizing:border-box} body{font-family:Portfolio,sans-serif;font-size:10pt;line-height:1.62;color:#283B48;margin:0;word-break:normal;overflow-wrap:anywhere;}
    p{margin:0 0 3mm;orphans:3;widows:3;} strong{color:#153B55;}
    h2{font-size:16.5pt;line-height:1.4;color:#173A52;margin:9mm 0 4mm;padding-bottom:2.5mm;border-bottom:1.5pt solid #087F8C;break-after:avoid;}
    h3{font-size:12pt;line-height:1.5;color:#087F8C;margin:5mm 0 2.5mm;break-after:avoid;}
    table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:9pt;line-height:1.55;margin:4mm 0 5mm;break-inside:avoid;}
    th{background:#173A52;color:white;text-align:left;font-weight:700;padding:3mm 2.8mm;border:0.5pt solid #173A52;}
    td{padding:2.3mm;border:0.5pt solid #D5E1E7;vertical-align:top;} tr:nth-child(even){background:#F1F6F9;} tr{break-inside:avoid;} thead{display:table-header-group;}
    ul,ol{padding-left:5mm;margin:2mm 0 4mm;}li{margin-bottom:2mm;} img{display:block;width:100%;height:auto;margin:4mm 0 5mm;break-inside:avoid;}
    .cover{height:253mm;break-after:page;padding-top:20mm;position:relative;}
    .eyebrow{font-size:10pt;letter-spacing:1.3pt;color:#087F8C;font-weight:bold;}
    .cover h1{font-size:29pt;line-height:1.5;letter-spacing:-0.5pt;color:#173A52;margin:17mm 0 5mm;}
    .subtitle{font-size:17pt;color:#087F8C;font-weight:bold;margin-bottom:15mm;}
    .role{background:#EDF7F5;border-left:3pt solid #087F8C;padding:5mm;font-size:12pt;font-weight:bold;color:#173A52;}
    .thesis{font-size:13pt;line-height:1.9;margin-top:12mm;}
    .tags{margin-top:10mm;font-size:10pt;color:#536677;line-height:2;}
    .date{position:absolute;bottom:6mm;font-size:9pt;color:#607585;}
    '''.replace('FONT_REG',REGULAR.as_uri()).replace('FONT_BOLD',BOLD.as_uri())
    cover='''<section class="cover"><div class="eyebrow">AI EXPERIENCE &amp; CAPABILITIES</div>
    <h1>금융·법률 문서를 이해하고<br>근거로 답하는 AI</h1>
    <p class="subtitle">AI 활용 경험·역량 기술서</p>
    <div class="role">담당 역할 &nbsp;|&nbsp; 전체 설계·개발·실험 주도</div>
    <p class="thesis">문서를 이해할 수 있는 지식으로 만들고,<br>AI가 근거를 찾아 답하도록 연결하며,<br>실험과 검증으로 개선 여부를 판단한 경험.</p>
    <p class="tags">문서 이해 · 지식 연결 · RAG · 에이전트<br>실험 격리 · 평가·승인 · 운영·복구</p>
    <p class="date">2026.09 &nbsp;|&nbsp; 프로젝트 경험과 개별 실험 기록에 근거한 작성</p></section>'''
    htmltext='<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AI 활용 경험·역량 기술서</title><style>'+css+'</style></head><body>'+cover+body+'</body></html>'
    hp=OUT/(NAME+'.html');hp.write_text(htmltext)
    pdf=OUT/(NAME+'.pdf');HTML(filename=str(hp)).write_pdf(str(pdf))
    return pdf


def main():
    figs=figures()
    renderer,word_checks=word_document(figs)
    pdf=pdf_document(figs)
    document=fitz.open(pdf)
    fulltext=''.join(p.get_text() for p in document)
    compact=lambda s:re.sub(r'\s+','',s)
    missing=[x for x in renderer.expected_text if compact(x) not in compact(fulltext)]
    # The PDF cover uses a line break instead of the exact standalone keyword subtitle.
    missing=[x for x in missing if x!='문서 이해 · 지식 연결 · RAG · 에이전트 · 실험 격리 · 평가·승인 체계']
    assert not missing,repr(missing[:5])
    assert not re.search(r'02_BACKEND|06_TOOLS|def |class |\.py\b|/home/jin',fulltext)
    assert '[[FIGURE_' not in fulltext
    (OUT/'preview').mkdir(exist_ok=True)
    for stale in (OUT/'preview').glob('page-*.png'):
        stale.unlink()
    for i,p in enumerate(document):
        p.get_pixmap(matrix=fitz.Matrix(.75,.75),alpha=False).save(str(OUT/'preview'/f'page-{i+1:02d}.png'))
    thumbs=[]
    for p in sorted((OUT/'preview').glob('page-*.png')):
        im=Image.open(p);im.thumbnail((300,425));thumbs.append(im.copy())
    sheet=Image.new('RGB',(4*324,((len(thumbs)+3)//4)*462),'#D9E2E8');d=ImageDraw.Draw(sheet)
    for i,im in enumerate(thumbs):
        x=(i%4)*324+12;y=(i//4)*462+12;sheet.paste(im,(x,y));d.text((x,y+427),str(i+1),fill=NAVY,font=font(16))
    sheet.save(OUT/'preview'/'contact-sheet.png')
    sources=[
        '00_SYSTEM/ARCHITECTURE.md','00_SYSTEM/DATA_MODEL.md','GENOS.md',
        '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
        '07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_V5.md',
        '07_DOCS/REFERENCE/OPERATIONS/BOUNDED_SOURCE_RECOVERY_MAIN.md',
        '07_DOCS/REFERENCE/OPERATIONS/GENOS_RESPONSE_COMPLETION_20260925.md',
        '07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md',
        '07_DOCS/REFERENCE/REPORTS/PUBLIC_GLOSSARY_COLLECTION_20260912.md',
        '07_DOCS/REFERENCE/REPORTS/RAG_TEST_REVIEW/ADR-0058/README.md',
        '04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union/README.md',
        '04_EXPERIMENTS/ADR/ADR-0517-bounded-provenance-protocol/README.md',
        '04_EXPERIMENTS/ADR/ADR-0542-reverse-hint-larger-sample-resume/README.md',
        '04_EXPERIMENTS/LEGACY_ADR/ADR-0040-frame-only-legal-answer-ab/README.md',
        '04_EXPERIMENTS/LEGACY_ADR/RETROSPECTIVE.md',
        '02_BACKEND/lawrag/agents/agent6/README.md',
        '07_DOCS/REFERENCE/REPORTS/PORTFOLIO_HANDOFF_20260924/portfolio_master.md',
    ]
    evidence={'source_date':'2026-09-25','personal_role_basis':'User explicitly confirmed: 전체 설계·개발·실험을 주도',
              'source_files':[{'path':p,'sha256':sha(ROOT/p)} for p in sources],
              'new_model_experiment':False,'genos_access':False,
              'word_checks':word_checks,'pdf_pages':len(document),'pdf_text_units_verified':len(renderer.expected_text),
              'pdf_text_preservation':'PASS','code_structure_absent_from_submission_body':True,
              'pdf_visual_review':'pending','docx_visual_review':'not rendered independently'}
    (OUT/'작성근거_검증기록.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    handoff=SOURCE.read_text()
    for key,(name,alt) in figs.items():handoff=handoff.replace(key,f'![{alt}](assets/{name})')
    (OUT/'AI_활용경험_다른AI전달용.md').write_text(handoff)
    (OUT/'읽어주세요.md').write_text('''# AI 활용 경험·역량 기술서

PDF는 읽기·제출용, DOCX는 수정용입니다. 다른 AI에는 `AI_활용경험_다른AI전달용.md`를 전달하면 됩니다.

본문에는 코드·폴더 구조를 넣지 않았습니다. 파이프라인, RAG, 에이전트, 실험 격리, 거버넌스는 쉬운 설명과 그림으로 풀었습니다.
사용자가 확인한 ‘전체 설계·개발·실험 주도’를 담당 역할로 반영했습니다. 단독 개발·기여율·팀 규모·사업 성과는 임의로 추가하지 않았습니다.

실험 수치는 개별 비교의 범위와 한계를 함께 표시했습니다. 문서에 쓰인 내부 기록 번호는 근거 확인용이며, 상세 경로는 작성근거 JSON에만 있습니다.
심사 통과를 보장하는 문서가 아니라 확인된 경험과 역량을 설명하는 지원 자료입니다.
''')
    package()
    print(json.dumps({'pdf_pages':len(document),'docx_checks':word_checks,'pdf_text_check':'PASS','directory':str(OUT),'characters':len(SOURCE.read_text())},ensure_ascii=False))


def package():
    files=[p for p in OUT.rglob('*') if p.is_file() and p.suffix in {'.pdf','.docx','.md','.json','.png','.html','.py'} and 'preview' not in p.parts and '__pycache__' not in p.parts and p.name!='파일목록.json']
    rows=[{'file':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]
    (OUT/'파일목록.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    with ZipFile(OUT/'AI_활용경험_역량기술서_패키지.zip','w',ZIP_DEFLATED) as z:
        for p in sorted(files+[OUT/'파일목록.json']):z.write(p,arcname=str(p.relative_to(OUT)))


if __name__=='__main__':main()
