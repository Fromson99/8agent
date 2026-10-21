"""Render the report's synthetic, typed knowledge graph to PNG and SVG."""
from pathlib import Path
import html
import math
from PIL import Image, ImageDraw, ImageFont


def build_graph(destination):
    destination = Path(destination)
    width, height, scale = 1200, 1430, 2
    image = Image.new('RGB', (width * scale, height * scale), 'white')
    draw = ImageDraw.Draw(image)
    regular = '/mnt/c/Windows/Fonts/malgun.ttf'
    boldfont = '/mnt/c/Windows/Fonts/malgunbd.ttf'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
    labels = []

    def text(x, y, value, size=24, bold=False, color='#263c50', limit=None):
        font = ImageFont.truetype(boldfont if bold else regular, size * scale)
        length = draw.textlength(value, font=font) / scale
        if limit is not None and length > limit:
            raise ValueError('Label overflow: ' + value)
        labels.append(value)
        draw.text((x * scale, y * scale), value, font=font, fill=color, anchor='lt')
        svg.append(f'<text x="{x}" y="{y+size}" font-family="Malgun Gothic,Noto Sans CJK KR,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(value)}</text>')

    def node(x, y, w, h, title, lines, fill='#eff5fc', border='#9ab3cc'):
        draw.rounded_rectangle((x*scale,y*scale,(x+w)*scale,(y+h)*scale),radius=12*scale,fill=fill,outline=border,width=2*scale)
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        text(x+18,y+17,title,27,True,limit=w-36)
        for i,line in enumerate(lines):text(x+18,y+61+i*32,line,21,limit=w-36)

    def arrow(points, dashed=False, color='#5d7489'):
        for start,end in zip(points,points[1:]):
            ax,ay=start;bx,by=end
            distance=math.hypot(bx-ax,by-ay)
            if dashed:
                for step in range(0,math.ceil(distance),17):
                    f=step/distance;g=min(step+9,distance)/distance
                    draw.line(((ax+(bx-ax)*f)*scale,(ay+(by-ay)*f)*scale,(ax+(bx-ax)*g)*scale,(ay+(by-ay)*g)*scale),fill=color,width=3*scale)
            else:draw.line((ax*scale,ay*scale,bx*scale,by*scale),fill=color,width=3*scale)
        dash=' stroke-dasharray="9 8"' if dashed else ''
        svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        a,b=points[-2:];dx=b[0]-a[0];dy=b[1]-a[1];d=math.hypot(dx,dy);ux,uy=dx/d,dy/d
        tri=[b,(b[0]-ux*12-uy*6,b[1]-uy*12+ux*6),(b[0]-ux*12+uy*6,b[1]-uy*12-ux*6)]
        draw.polygon([(x*scale,y*scale) for x,y in tri],fill=color)
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in tri)}" fill="{color}"/>')

    text(80,25,'온톨로지와 지식그래프의 내부 연결',34,True)
    text(80,77,'노드: 문서·개념·정의·경험·계획   간선: 의미와 방향이 있는 관계',22)
    node(80,130,400,140,'원문 U-I12',['모의 내규 V3 · 제12조','외규 제3조를 명시적으로 참조'])
    node(720,130,400,140,'원문 U-E03',['모의 외규 V5 · 제3조','보고에 관한 정의와 본문'])
    arrow([(480,200),(720,200)])
    text(530,156,'명시 참조',24,True,limit=180)
    text(492,218,'EXPLICITLY_REFERENCES',17,limit=225)

    node(445,330,310,135,'근거 관계 후보 R-1',['BASIS · PROPOSED','양측 위치 current'],fill='#fff5e9',border='#d5a363')
    arrow([(445,370),(360,370),(360,270)],True,'#be833b')
    arrow([(755,370),(840,370),(840,270)],True,'#be833b')
    text(391,298,'내규 끝점',19,color='#94662f')
    text(744,298,'외규 끝점',19,color='#94662f')

    node(80,550,380,115,'개념 C-1',['보고 절차 · 업무 개념'],fill='#edf7f3',border='#88b6a5')
    node(740,550,380,115,'정의 D-1',['U-E03 판본·문서 범위의 정의'],fill='#edf7f3',border='#88b6a5')
    arrow([(270,270),(270,550)])
    text(285,479,'MENTIONS',23)
    arrow([(930,550),(930,270)])
    text(945,479,'원문 근거',22)
    arrow([(740,610),(460,610)])
    text(535,570,'DEFINES',24,True)

    node(80,870,380,125,'조사 계획 P-1',['보고 주체·시점·예외 확인','현재 원문을 읽는 절차'])
    node(740,870,380,125,'Legal Wiki W-1',['보고 절차 비교 경험','조건·주장·근거·한계'])
    arrow([(270,870),(270,665)])
    text(285,743,'TARGETS',23)
    arrow([(740,900),(600,900),(600,712),(440,712),(440,665)])
    text(613,778,'ABOUT',23)
    arrow([(740,958),(460,958)])
    text(487,926,'SUGGESTS_PLAN',22)
    arrow([(80,935),(35,935),(35,200),(80,200)])
    text(80,790,'READS 원문 읽기',22)
    arrow([(1120,935),(1165,935),(1165,200),(1120,200)])
    text(947,790,'CITES 원문 인용',22,limit=215)

    node(365,1170,470,125,'이번 판단 J-1',['의견 · 이유 · 인용 · 미확인','현재 사실과 읽은 원문에 결속'],fill='#edf0f7',border='#9daac2')
    arrow([(270,995),(270,1125),(600,1125),(600,1170)])
    text(292,1080,'계획 실행 + 원문 읽기 + LLM 의미 판단',23,limit=655)
    text(80,1334,'실선: 원문·기록 연결   주황 점선: 승인 전 근거 관계 후보',23)
    text(80,1380,'모의 값으로 표현한 목표 그래프 · 관계별 근거·범위·버전·권한을 함께 저장',21)
    svg.append('</svg>')
    image.save(destination/'knowledge-graph.png',optimize=True)
    (destination/'knowledge-graph.svg').write_text('\n'.join(svg),encoding='utf-8')
    return {'graph_labels_checked':len(labels),'graph_canvas':[width,height],'mock_data':True}


if __name__=='__main__':
    build_graph(Path(__file__).resolve().parent)
