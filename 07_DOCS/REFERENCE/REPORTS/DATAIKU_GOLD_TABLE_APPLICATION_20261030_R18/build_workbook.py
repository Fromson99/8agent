"""Preserve R17 layout; apply the user's vector section ID name to R18."""
import hashlib
import json
from pathlib import Path
import zipfile
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
SOURCE=OUT.parent/'DATAIKU_GOLD_TABLE_APPLICATION_20261030_R17/법률에이전트_B03_테이블별_컬럼정의_R17.xlsx'
TARGET=OUT/'법률에이전트_B03_테이블별_컬럼정의_R18.xlsx'
OLD,NEW='VCTR_SEG_ID','VCTR_SCTN_ID'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    original_sha=sha(SOURCE)
    original=load_workbook(SOURCE)
    wb=load_workbook(SOURCE)
    changes=[]
    for ws in wb:
        for row in ws:
            for c in row:
                if isinstance(c.value,str) and OLD in c.value:
                    changes.append({'sheet':ws.title,'cell':c.coordinate,'before':c.value,'after':c.value.replace(OLD,NEW)})
                    c.value=c.value.replace(OLD,NEW)
        if ws.oddFooter.center.text:
            ws.oddFooter.center.text=ws.oddFooter.center.text.replace('R17','R18')+' · 벡터구간ID '+NEW
    wb.properties.title='법률에이전트 B03 테이블별 컬럼 정의 R18'
    wb.save(TARGET)
    check=load_workbook(TARGET)
    assert check.sheetnames==original.sheetnames and len(check.worksheets)==16
    for before,after in zip(original,check):
        assert before.max_row==after.max_row and before.max_column==after.max_column
        for row in before:
            for c in row:
                expected=c.value.replace(OLD,NEW) if isinstance(c.value,str) else c.value
                assert after[c.coordinate].value==expected,(before.title,c.coordinate)
                assert after[c.coordinate].style_id==c.style_id
        assert str(before.merged_cells)==str(after.merged_cells)
        assert before.freeze_panes==after.freeze_panes and before.auto_filter.ref==after.auto_filter.ref
    mapping=json.loads((ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_r18_registration.json').read_text())
    tables={v['name']:v for v in mapping['tables'].values()}
    columns=0
    for ws in check.worksheets[1:14]:
        table=tables[ws['A2'].value]
        assert [ws.cell(5,c).value for c in range(1,5)]==['논리명','물리명','PK','NULL 허용']
        assert [ws.cell(r,2).value for r in range(6,ws.max_row+1)]==[c['name'] for c in table['columns'].values()]
        columns+=ws.max_row-5
    assert columns==60 and len(changes)==3,changes
    assert sha(SOURCE)==original_sha
    with zipfile.ZipFile(TARGET) as z:assert z.testzip() is None
    result={'status':'PASS','file':str(TARGET.relative_to(ROOT)),'sha256':sha(TARGET),'source_sha256':original_sha,
            'table_sheets':13,'columns':60,'mapping_names_match':True,'other_cell_values_and_styles_unchanged':True,
            'native_excel_rendered':False,'changes':changes}
    (OUT/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
