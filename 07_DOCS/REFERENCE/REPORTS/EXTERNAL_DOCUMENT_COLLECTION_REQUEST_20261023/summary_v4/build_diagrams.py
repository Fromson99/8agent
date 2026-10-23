"""Deterministic process diagrams: vector PDF/SVG and lossless DOCX previews."""
from pathlib import Path
import json
from html import escape
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.graphics import renderPDF, renderSVG
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import fitz

OUT=Path(__file__).resolve().parent
ASSETS=OUT/'diagrams'
ASSETS.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('Malgun','/mnt/c/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','/mnt/c/Windows/Fonts/malgunbd.ttf'))
NAVY='#153B55'; TEAL='#087F8C'; INK='#253544'; PALE='#EDF4F7'

SPECS={
 'api_flow': {
  'width':507, 'height':516, 'node_height':62, 'gap':31,
  'columns':[
   {'title':'법령 37종 · target=eflaw','nodes':[
    ['① 목록 API 요청','GET lawSearch.do','query=정식명 · nw=2,3','display=100 · page=1부터 끝까지'],
    ['② 응답에서 대상 판본 선택','법령일련번호 + 해당 시행일','문서명·법령ID 대조','현행 / 시행예정 구분'],
    ['③ 본문 API 요청','GET lawService.do','target=eflaw','MST + efYd로 판본 지정'],
    ['④ XML 본문과 첨부 링크 수신','조문·부칙·별표 정보 확인','별표·서식의 실제 파일 링크 추출'],
    ['⑤ 첨부 파일 개별 다운로드','응답 링크·파라미터 그대로 사용','XML 원본 + 파일 원본 보존']
   ],'edges':[
    '목록 XML 응답','MST ← 일련번호  /  efYd ← 시행일','본문 XML 응답','flSeq 등 ← 실제 링크값'
   ]},
   {'title':'행정규칙 12종 · target=admrul','nodes':[
    ['① 목록 API 요청','GET lawSearch.do','query=정식명 · nw=1','display=100 · page=1부터 끝까지'],
    ['② 응답에서 대상 판본 선택','행정규칙일련번호 확보','정식 규칙명·소관기관 대조','응답의 실제 판본 확인'],
    ['③ 본문 API 요청','GET lawService.do','target=admrul','ID에 행정규칙일련번호 지정'],
    ['④ XML 본문과 첨부 링크 수신','조문·부칙·별표 정보 확인','별표·첨부의 실제 파일 링크 추출'],
    ['⑤ 첨부 파일 개별 다운로드','응답 링크·파라미터 그대로 사용','XML 원본 + 파일 원본 보존']
   ],'edges':[
    '목록 XML 응답','ID ← 행정규칙일련번호','본문 XML 응답','첨부 URL·파일 식별자 ← 실제 링크'
   ]}
  ],
  'footer':['문서·판본 ID와 원본·첨부를 묶어 검증 → AIDP 원본 저장','필수 파일 저장·해시 검증 완료 후 구조화·Oracle 적재로 연결']
 },
 'web_flow': {
  'width':507, 'height':562, 'node_height':56, 'gap':28,
  'columns':[
   {'title':'거래소 규정 9종','nodes':[
    ['① 화면·세션 준비','/out/index.do 진입','Cookie·CSRF 확보'],
    ['② 규정 트리 조회','getTreeNode.do','정식명으로 bookid 탐색'],
    ['③ 규정 상세 HTML','regulationView.do','STATEHISTORYID 확보'],
    ['④ 전문·첨부 파일 정보','전문: filecd=JUN','별표·서식 목록도 조회'],
    ['⑤ 다운로드 토큰 갱신','getData.do → 새 _csrf','실제 파일 정보와 결합'],
    ['⑥ 파일 다운로드','POST /Download.do','파일 정보 + 새 _csrf']
   ],'edges':[
    'Cookie·CSRF 유지','bookid 전달','bookid + statehistoryid','fileMap·첨부의 파일 정보','Serverfile·Pcfilename 등'
   ]},
   {'title':'금투협 5종','nodes':[
    ['① 규정 트리 조회','정식명과 seq 연결','seq = 규정ID'],
    ['② 현행 상세 조회','lawView.do','historySeq=0 · gubun=cur'],
    ['③ 판본 본문 HTML','lawFullScreenContent.do','실제 historySeq 사용'],
    ['④ 전문·첨부 요청 구분','전문: gubun=101','별표: gubun=102'],
    ['⑤ 다운로드 seq 선택','전문 ← historySeq','별표 ← 첨부ID'],
    ['⑥ 파일 다운로드','GET /download.do','gubun + 해당 seq']
   ],'edges':[
    'seq=규정ID 전달','응답의 실제 historySeq','본문·첨부 링크 확보','다운로드별 ID 구분','첨부마다 별도 요청'
   ]},
   {'title':'거래소 공개 별첨 5종','unconfirmed':True,'nodes':[
    ['① 게시판 목록 확인','기업실사 게시물 탐색','현재 탐색 요청 확인 필요'],
    ['② 최신 게시물 선택','bbsId = 게시판ID','bbsSeq = 게시물ID'],
    ['③ 첨부 목록 확보','attachFileSeq 확인','파일명과 대상 5종 대조'],
    ['④ 다운로드 버튼 확인','GET/POST·필수값 확인','과거 번호 고정 금지'],
    ['⑤ 요청 파라미터 조립','게시판·게시물·첨부ID','filetype·url 등 실제 값'],
    ['⑥ 원본 파일 다운로드','file.krx.co.kr','/download.jspx']
   ],'edges':[
    '현재 게시물 정보','게시물의 첨부 연결','파일별 실제 버튼 요청','현행 요청 규약 사용','첨부마다 별도 요청'
   ]}
  ],
  'footer':['본문 HTML + 원본 파일 + 문서·판본·첨부 연결 정보를 함께 보존','ID·파일 미확보 시 미완료 표시 → 성공 파일은 유지하고 해당 단계부터 재개']
 }
}

def diagram_text(spec):
    return [text for col in spec['columns'] for text in [col['title'],*[t for node in col['nodes'] for t in node],*col['edges']]]+spec['footer']

def make_drawing(spec):
    w,h=spec['width'],spec['height']; d=Drawing(w,h)
    n=len(spec['columns']);gutter=15 if n==2 else 11; cw=(w-gutter*(n-1))/n
    nh=spec['node_height'];gap=spec['gap'];top=h-42
    body_size=9.1 if n==2 else 8.0
    title_size=10 if n==2 else 8.8
    edge_size=8.5 if n==2 else 7.7
    def text(x,y,s,size=9,bold=False,color=INK):
        assert pdfmetrics.stringWidth(s,'MalgunBold' if bold else 'Malgun',size)<=cw-10 or x==w/2, s
        d.add(String(x,y,s,fontName='MalgunBold' if bold else 'Malgun',fontSize=size,textAnchor='middle',fillColor=colors.HexColor(color)))
    for ci,col in enumerate(spec['columns']):
        x=ci*(cw+gutter);cx=x+cw/2
        hc='#9A6615' if col.get('unconfirmed') else NAVY
        d.add(Rect(x,h-29,cw,29,rx=4,ry=4,fillColor=colors.HexColor(hc),strokeColor=None))
        text(cx,h-19,col['title'],10 if n==2 else 9.2,True,'#FFFFFF')
        for ni,lines in enumerate(col['nodes']):
            y=top-ni*(nh+gap)-nh
            d.add(Rect(x,y,cw,nh,rx=5,ry=5,fillColor=colors.HexColor('#F7FAFC' if ni%2==0 else PALE),strokeColor=colors.HexColor('#BDD3DD'),strokeWidth=.7))
            line_height=11.9 if n==2 else 11.5
            content_h=(len(lines)-1)*line_height+title_size
            baseline=y+(nh+content_h)/2-title_size
            for li,line in enumerate(lines):
                text(cx,baseline-li*line_height,line,title_size if li==0 else body_size,li==0,NAVY if li==0 else INK)
            if ni<len(col['edges']):
                # Break the arrow around the white label to preserve readable value flow.
                d.add(Line(cx,y-1,cx,y-gap+5,strokeColor=colors.HexColor(TEAL),strokeWidth=1.1))
                label=col['edges'][ni];lw=pdfmetrics.stringWidth(label,'MalgunBold',edge_size)+8
                d.add(Rect(cx-lw/2,y-gap/2-3,lw,edge_size+4,fillColor=colors.white,strokeColor=None))
                text(cx,y-gap/2,label,edge_size,True,TEAL)
                d.add(Polygon([cx,y-gap+1,cx-3,y-gap+7,cx+3,y-gap+7],fillColor=colors.HexColor(TEAL),strokeColor=None))
        bottom=top-(len(col['nodes'])-1)*(nh+gap)-nh
        d.add(Line(cx,bottom-2,cx,38,strokeColor=colors.HexColor(TEAL),strokeWidth=1.1))
        d.add(Polygon([cx,34,cx-3,40,cx+3,40],fillColor=colors.HexColor(TEAL),strokeColor=None))
    d.add(Rect(0,0,w,34,rx=4,ry=4,fillColor=colors.HexColor(PALE),strokeColor=colors.HexColor(TEAL),strokeWidth=.7))
    for i,line in enumerate(spec['footer']):
        d.add(String(w/2,21-i*12,line,fontName='MalgunBold' if i==0 else 'Malgun',fontSize=9 if n==2 else 8.5,textAnchor='middle',fillColor=colors.HexColor(NAVY)))
    return d

def build_assets():
    for name,spec in SPECS.items():
        drawing=make_drawing(spec)
        renderPDF.drawToFile(drawing,str(ASSETS/(name+'.pdf')))
        renderSVG.drawToFile(drawing,str(ASSETS/(name+'.svg')))
        svg=(ASSETS/(name+'.svg')).read_text().replace("font-family: 'MalgunBold'","font-family: 'Malgun Gothic'; font-weight: bold").replace("font-family: 'Malgun'","font-family: 'Malgun Gothic'")
        (ASSETS/(name+'.svg')).write_text(svg)
        pdf=fitz.open(ASSETS/(name+'.pdf'))
        # PNGs are exact rasterizations of the vector source for Word compatibility.
        pdf[0].get_pixmap(matrix=fitz.Matrix(2,2)).save(ASSETS/(name+'.png'))
        got=''.join(pdf[0].get_text().split())
        missing=[s for s in diagram_text(spec) if ''.join(s.split()) not in got]
        assert not missing,missing
    (OUT/'DIAGRAMS.json').write_text(json.dumps(SPECS,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    build_assets()
    print('Built 2 process diagrams: SVG + PDF + PNG')
