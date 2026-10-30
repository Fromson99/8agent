"""Apply confirmed ONTL / POST abbreviations and 100 BYTE capacity to R9."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import zipfile

from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'DATAIKU_GOLD_REGISTER_20261028_R9'
spec = importlib.util.spec_from_file_location('r9_format', PREVIOUS / 'build_workbooks.py')
formatting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatting)
OLD_TOKEN = re.compile(r'(?<![A-Z0-9])(ONT|PBLS|PUB)(?![A-Z0-9])')
TOKEN_MAP = {'ONT': 'ONTL', 'PBLS': 'POST', 'PUB': 'POST'}
EXPECTED_SUFFIXES = ['DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST',
                     'SRCH_ROW', 'SRCH_CHNL', 'ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revised(value):
    if not isinstance(value, str):
        return value
    value = OLD_TOKEN.sub(lambda match: TOKEN_MAP[match.group(0)], value)
    value = re.sub(r'\bR9\b', 'R10', value)
    return '100 BYTE' if value == '64 BYTE' else value


def build(agent):
    source = PREVIOUS / f'법률에이전트_{agent}_골드등록용_테이블별_R9.xlsx'
    original_hash = sha(source)
    workbook = load_workbook(source)
    changes = []
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                old = cell.value
                new = revised(old)
                if old != new:
                    changes.append(dict(sheet=sheet.title,cell=cell.coordinate,before=old,after=new))
                    cell.value = new
        for footer_name in ('oddFooter', 'evenFooter', 'firstFooter', 'oddHeader', 'evenHeader', 'firstHeader'):
            footer = getattr(sheet, footer_name)
            for side in ('left', 'center', 'right'):
                part = getattr(footer, side)
                if part.text:
                    part.text = revised(part.text)
        for table in sheet.tables.values():
            table.displayName = revised(table.displayName)
            table.name = revised(table.name)
    workbook.properties.title = f'{agent} 테이블·엔티티·컬럼 정의서 R10'
    workbook.properties.description = '온톨로지 약어 ONTL, 게시 약어 POST 및 관련 식별자 100 BYTE를 적용한 테이블·엔티티·컬럼 정의서.'
    output = HERE / f'법률에이전트_{agent}_골드등록용_테이블별_R10.xlsx'
    workbook.save(output)
    assert sha(source) == original_hash
    (HERE / f'CHANGE_AUDIT_{agent}.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n')
    return source, output, changes


def validate(source, output, agent, changes):
    previous, workbook = load_workbook(source), load_workbook(output)
    assert workbook.sheetnames == previous.sheetnames and len(workbook.sheetnames) == 11
    schemas, common, definition_count, renamed_tables, widened, cells = {}, {}, 0, 0, 0, 0
    for before, sheet in zip(previous, workbook):
        for row in before:
            for cell in row:
                assert sheet[cell.coordinate].value == revised(cell.value), (sheet.title,cell.coordinate)
                cells += 1
    for index, sheet in enumerate(workbook.worksheets[1:], 1):
        table = re.search(r'IDD_\w+', sheet['A2'].value)[0]
        assert table == f'IDD_{agent}_LGL_{EXPECTED_SUFFIXES[index-1]}'
        assert workbook.worksheets[0].cell(index+6,3).value == table
        assert workbook.worksheets[0].cell(index+6,2).value == sheet['A1'].value.split(': ',1)[1]
        assert len(table.encode()) <= 30
        if previous[sheet.title]['A2'].value != sheet['A2'].value:
            renamed_tables += 1
        rows = [list(row) for row in sheet.iter_rows(min_row=7,max_col=12,values_only=True) if isinstance(row[0],int)]
        schema = {row[2]:row for row in rows}
        assert len(schema) == len(rows)
        schemas[table] = schema
        pk = [row[2] for row in sorted((r for r in rows if isinstance(r[7],int)),key=lambda r:r[7])]
        for row in rows:
            physical = row[2]
            assert len(physical.encode()) <= 30
            assert ('NOT NULL' in row[9]) == (row[8] == 'Y')
            if 'PK (' in row[9]:
                keys = [v.strip() for v in re.search(r'PK \(([^)]+)\)',row[9])[1].split(',')]
                assert keys == pk and set(keys) <= set(schema) and row[8] == 'Y'
            signature = (row[1],row[3],row[5],row[6],row[10],row[11])
            if physical in common:
                assert signature == common[physical]
            common[physical] = signature
            assert row[10] == previous[sheet.title].cell(row[0]+6,11).value
            assert not formatting.FORBIDDEN.search(row[10])
            if physical == 'ONTL_POST_ID':
                assert row[5:7] == ['VARCHAR2','100 BYTE']
                widened += 1
            definition_count += 1
    fk_count = check_count = 0
    for table, schema in schemas.items():
        for row in schema.values():
            if 'FK →' in row[9]:
                target, col = re.search(r'FK → (\w+) \((\w+)\)',row[9]).groups()
                other = schemas[target][col]
                assert other[7] == 1 and other[8] == 'Y' and other[5:7] == row[5:7]
                fk_count += 1
            if 'CHECK (' in row[9]:
                assert re.search(r'CHECK \((\w+)',row[9])[1] == row[2]
                check_count += 1
    assert (definition_count,renamed_tables,widened,fk_count,check_count) == (49,5,3,3,6)
    assert len(common) == 32
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                assert cell.comment is None and cell.data_type != 'f'
                if isinstance(cell.value,str):
                    assert not OLD_TOKEN.search(cell.value)
                    assert '64 BYTE' not in cell.value and '512 BYTE' not in cell.value
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            assert not name.lower().endswith(('.js','.jsx','.mjs','.cjs','.bin'))
            if name.endswith('.xml'):
                xml = archive.read(name).decode()
                assert not OLD_TOKEN.search(xml), name
                assert '64 BYTE' not in xml and not re.search(r'\bR9\b',xml)
    return dict(status='PASS_DOCUMENT_CONSISTENCY',tables=10,columns=49,renamed_tables=renamed_tables,
                renamed_and_widened_columns=widened,foreign_keys_checked=fk_count,checks_checked=check_count,
                cells_compared=cells,cells_changed=len(changes),definitions_preserved=definition_count,
                old_abbreviations_remaining=0,byte64_remaining=0,source_preserved=True,
                database_updated=False,native_excel_render=False)


def preview(output, sheetname):
    sheet = load_workbook(output)[sheetname]
    overview = sheetname == '00_테이블목록'
    columns = [1,2,3,4] if overview else [2,3,6,7,8,9,10]
    widths = [65,250,345,900] if overview else [230,300,160,170,80,65,620]
    last = 16 if overview else max(row[0].row for row in sheet.iter_rows(min_row=7) if isinstance(row[0].value,int))
    data = [[sheet.cell(row,col).value for col in columns] for row in range(6,last+1)]
    normal,bold = ImageFont.truetype(formatting.FONT,18),ImageFont.truetype(formatting.BOLD,18)
    heights = [max(65,max(len(formatting.wrap(value,widths[i]-24,bold if n==0 else normal)) for i,value in enumerate(row))*27+24) for n,row in enumerate(data)]
    image = Image.new('RGB',(sum(widths)+48,sum(heights)+150),'white')
    draw = ImageDraw.Draw(image)
    draw.text((24,20),'R10 | '+sheet['A1'].value,font=ImageFont.truetype(formatting.BOLD,27),fill='#21374E')
    draw.text((24,65),sheet['A2'].value,font=normal,fill='#455F72')
    y = 115
    for n,row in enumerate(data):
        x = 24
        for i,value in enumerate(row):
            draw.rectangle((x,y,x+widths[i],y+heights[n]),fill='#244B60' if n==0 else '#F0F5F7' if n%2==0 else 'white',outline='#D8E0E8')
            for k,line in enumerate(formatting.wrap(value,widths[i]-24,bold if n==0 else normal)):
                draw.text((x+12,y+12+k*27),line,font=bold if n==0 else normal,fill='white' if n==0 else '#21374E')
            x += widths[i]
        y += heights[n]
    image.save(HERE / (sheetname+'_검토미리보기.png'))


def main():
    results, outputs = [], []
    for agent in ('B03','B05'):
        source,output,changes = build(agent)
        validation = validate(source,output,agent,changes)
        results.append(dict(file=output.name,bytes=output.stat().st_size,sha256=sha(output),source_sha256=sha(source),validation=validation))
        outputs.append(output)
    books = [load_workbook(path) for path in outputs]
    parity = 0
    for left,right in zip(*books):
        for arow,brow in zip(left,right):
            for a,b in zip(arow,brow):
                normalize = lambda x:x.replace('B03','BXX').replace('B05','BXX') if isinstance(x,str) else x
                assert normalize(a.value) == normalize(b.value)
                parity += 1
    report = dict(files=results,agent_parity_cells=parity)
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for sheet in ('00_테이블목록','08_온톨로지게시','10_원문지식연결'):
        preview(outputs[0],sheet)
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    main()
