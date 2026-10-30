"""Content preview only; does not claim to render Excel's layout engine."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from openpyxl import load_workbook

BASE=Path(__file__).resolve().parent
FONT=ImageFont.truetype('/mnt/c/Windows/Fonts/malgun.ttf',18)
BOLD=ImageFont.truetype('/mnt/c/Windows/Fonts/malgunbd.ttf',18)
TITLE=ImageFont.truetype('/mnt/c/Windows/Fonts/malgunbd.ttf',30)

def wrap(text,width,font=FONT):
    result=[]
    for line in str(text if text is not None else '').split('\n'):
        buf=''
        for char in line:
            if font.getlength(buf+char)>width and buf:
                result.append(buf);buf=char
            else:buf+=char
        result.append(buf)
    return result

def render(book,sheet,columns,widths,filename):
    s=book[sheet];rows=[]
    for i in range(4,s.max_row+1):
        values=[s.cell(i,c).value for c in columns]
        lines=[wrap(v,w-18,BOLD if i==4 else FONT) for v,w in zip(values,widths)]
        rows.append((lines,max(54,max(map(len,lines))*27+24),i==4))
    width=sum(widths)+48;height=sum(r[1] for r in rows)+150
    image=Image.new('RGB',(width,height),'#FFFFFF');d=ImageDraw.Draw(image)
    d.text((24,18),s['A1'].value,font=TITLE,fill='#17354A')
    d.text((24,68),'R11 설계 후보 | Excel 셀 내용 기반 미리보기 · 실제 Excel 렌더링 아님',font=FONT,fill='#526777')
    y=120
    for n,(lines,h,header) in enumerate(rows):
        x=24
        for value,w in zip(lines,widths):
            d.rectangle((x,y,x+w,y+h),fill='#17354A' if header else '#EDF4F6' if n%2 else '#FFFFFF',outline='#D5E1E6')
            for j,line in enumerate(value):d.text((x+9,y+10+27*j),line,font=BOLD if header else FONT,fill='#FFFFFF' if header else '#243D4B')
            x+=w
        y+=h
    image.save(BASE/filename)

if __name__=='__main__':
    w=load_workbook(BASE/'법률에이전트_B03_골드재설계_R11.xlsx',data_only=True)
    render(w,'01_테이블목록',[1,2,3,4,5,6],[55,230,350,180,70,560],'PREVIEW_TABLES.png')
    render(w,'13_원문벡터',[1,2,3,6,7,8,9,11],[55,190,270,180,180,60,60,480],'PREVIEW_VECTOR.png')
