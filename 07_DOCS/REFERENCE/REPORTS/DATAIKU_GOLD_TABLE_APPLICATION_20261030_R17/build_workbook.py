"""One clear column sheet per table; four requested fields always come first."""
import hashlib
import json
from pathlib import Path
import unicodedata
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT=Path('/home/jin/8-AGENT')
OUT=Path(__file__).resolve().parent
SOURCE=OUT.parent/'DATAIKU_GOLD_TABLE_APPLICATION_20261030_R16/법률에이전트_B03_테이블신청_등록확정컬럼_R16.xlsx'
TARGET=OUT/'법률에이전트_B03_테이블별_컬럼정의_R17.xlsx'
NAVY='17365D'; BLUE='145E96'; INK='26384B'; PALE='F1F5F9'


def width(text):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(text))


def setup(ws,widths,freeze='C6'):
    ws.sheet_view.showGridLines=False;ws.sheet_view.zoomScale=90
    ws.freeze_panes=freeze
    for col,val in enumerate(widths,1):ws.column_dimensions[get_column_letter(col)].width=val
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.oddFooter.center.text='B03 컬럼 정의 R17 · 명세해시값 DTLS_HASH_VALU'
    ws.oddFooter.right.text='&P / &N'


def header(ws,row,labels):
    for col,value in enumerate(labels,1):
        c=ws.cell(row,col,value)
        c.fill=PatternFill('solid',fgColor=NAVY)
        c.font=Font(name='맑은 고딕',size=12,bold=True,color='FFFFFF')
        c.alignment=Alignment(vertical='center',wrap_text=True,horizontal='center' if col in (3,4,5) else 'left')
    ws.row_dimensions[row].height=34


def cell_style(ws,row,widths):
    lines=1
    for c in ws[row]:
        c.font=Font(name='맑은 고딕',size=11,color=INK)
        c.alignment=Alignment(vertical='center',wrap_text=True)
        c.fill=PatternFill('solid',fgColor='FFFFFF' if row%2 else PALE)
        c.border=Border(bottom=Side(style='thin',color='DDE5EE'))
        if c.value is not None:
            if isinstance(c.value,str):c.number_format='@'
            lines=max(lines,1+width(c.value)//max(8,int(widths[c.column-1])-2))
    ws.row_dimensions[row].height=max(36,min(118,lines*18+12))


def plain_sheet(wb,title,labels,rows,widths):
    ws=wb.create_sheet(title);setup(ws,widths,'C2');header(ws,1,labels)
    for row in rows:
        ws.append(list(row));cell_style(ws,ws.max_row,widths)
    ws.auto_filter.ref=ws.dimensions;ws.print_title_rows='1:1'
    return ws


def main():
    original_sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    src=load_workbook(SOURCE,data_only=True)
    tables=list(src['01_테이블'].values)[1:]
    cols=list(src['02_컬럼'].values)[1:]
    wb=Workbook();wb.remove(wb.active)
    overview=plain_sheet(wb,'00_테이블목록',
        ['컬럼 시트','테이블 논리명','테이블 물리명','컬럼 수','테이블 정의','파티션'],[],[25,25,34,11,86,12])
    expected={};layout={}
    for i,t in enumerate(tables,1):
        name,logical,definition,count,*_=t
        short=logical.removesuffix('내역')
        title=f'{i:02d}_{short}'
        ws=wb.create_sheet(title);ws.sheet_properties.tabColor='167E94'
        widths=[26,34,8,12,10,31,20,72]
        setup(ws,widths)
        for row,text,size,color in [(1,logical+' · 컬럼 정보',20,NAVY),(2,name,12,BLUE),(3,'PK: Y = 기본키  |  NULL 허용: N = 필수값, Y = 빈 값 허용  |  행 순서 = 컬럼 순서',11,INK)]:
            ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=8)
            c=ws.cell(row,1,text);c.font=Font(name='맑은 고딕',size=size,bold=row<3,color=color)
            c.alignment=Alignment(vertical='center')
            ws.row_dimensions[row].height=35 if row==1 else 26
        labels=['논리명','물리명','PK','NULL 허용','PK 순서','타입·길이','기본값','컬럼 정의']
        header(ws,5,labels)
        table_cols=[c for c in cols if c[0]==name]
        rows=[]
        for n,c in enumerate(table_cols,6):
            values=[c[4],c[3],c[10],c[9],c[11],c[6],c[12],c[5]]
            rows.append(values)
            for col,value in enumerate(values,1):ws.cell(n,col,value)
            cell_style(ws,n,widths)
            for col in (3,4,5):ws.cell(n,col).alignment=Alignment(horizontal='center',vertical='center')
            for col in (1,2):ws.cell(n,col).font=Font(name='맑은 고딕',size=11,bold=True,color=INK)
            pk=ws.cell(n,3)
            pk.fill=PatternFill('solid',fgColor='DDEBFF' if pk.value=='Y' else 'F3F5F7')
            pk.font=Font(name='맑은 고딕',size=12,bold=True,color='12528C' if pk.value=='Y' else '718096')
            null=ws.cell(n,4)
            null.fill=PatternFill('solid',fgColor='FFE7DE' if null.value=='N' else 'E4F3EB')
            null.font=Font(name='맑은 고딕',size=12,bold=True,color='9C3B20' if null.value=='N' else '206B48')
        assert len(rows)==count
        ws.auto_filter.ref=f'A5:H{5+count}';ws.print_title_rows='1:5'
        ws.print_area=ws.dimensions
        expected[title]=rows
        overview.append([title,logical,name,count,definition,'N'])
        cell_style(overview,overview.max_row,[25,25,34,11,86,12])
        link=overview.cell(overview.max_row,1);link.hyperlink=f"#'{title}'!A1"
        link.font=Font(name='맑은 고딕',size=11,bold=True,color='0563C1',underline='single')
        layout[title]={'table':name,'data_range':ws.auto_filter.ref,'columns':labels}
    overview.auto_filter.ref=overview.dimensions
    overview.sheet_properties.tabColor=NAVY
    # Keep the previously requested registration details in two clearly separated reference tabs.
    for source,title,widths in [('03_인덱스','14_참고_인덱스',[33,24,37,35,13,10,10,85,9,12,42,70]),
                              ('06_파티션','15_참고_파티션',[33,24,12,16,16,20,20,22,16,60])]:
        values=list(src[source].values)
        ws=plain_sheet(wb,title,values[0],values[1:],widths)
        ws.sheet_properties.tabColor='8A98A6'
    wb.active=1
    wb.properties.creator='8-AGENT'
    wb.properties.title='법률에이전트 B03 테이블별 컬럼 정의 R17'
    wb.properties.subject='논리명·물리명·PK·NULL 허용 여부를 첫 네 열에 표시'
    wb.save(TARGET)
    check=load_workbook(TARGET,data_only=False)
    assert len(check.worksheets)==16
    total=0
    for name,rows in expected.items():
        ws=check[name]
        assert list(ws.values)[5:]==[tuple(r) for r in rows]
        assert [ws.cell(5,i).value for i in range(1,5)]==['논리명','물리명','PK','NULL 허용']
        assert all(ws.cell(r,4).value=='N' for r in range(6,ws.max_row+1) if ws.cell(r,3).value=='Y')
        assert all(not any(cell.coordinate in merged for merged in ws.merged_cells.ranges) for row in ws.iter_rows(min_row=5) for cell in row)
        total+=len(rows)
    assert total==60
    assert sum(r[1]=='DTLS_HASH_VALU' for rows in expected.values() for r in rows)==4
    for ws in check:
        for row in ws:
            for c in row:
                assert c.data_type!='f'
                if isinstance(c.value,str):assert 'MNFST_HASH_VALU' not in c.value
    assert list(check['14_참고_인덱스'].values)==list(src['03_인덱스'].values)
    assert list(check['15_참고_파티션'].values)==list(src['06_파티션'].values)
    with zipfile.ZipFile(TARGET) as z:
        assert z.testzip() is None
        assert not any(n.lower().endswith(('.js','.jsx','.mjs','.cjs')) for n in z.namelist())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==original_sha
    result={'status':'PASS','file':str(TARGET.relative_to(ROOT)),'bytes':TARGET.stat().st_size,
            'sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest(),'source_sha256':original_sha,
            'table_column_sheets':13,'columns':60,'all_sheets':16,'first_four_columns':['논리명','물리명','PK','NULL 허용'],
            'pk_null_consistent':True,'column_values_equal_r16':True,'index_partition_values_preserved':True,'data_cells_merged':False,
            'initial_sheet':check.active.title,'native_excel_rendered':False,'layout':layout}
    (OUT/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='layout'},ensure_ascii=False))


if __name__=='__main__':main()
