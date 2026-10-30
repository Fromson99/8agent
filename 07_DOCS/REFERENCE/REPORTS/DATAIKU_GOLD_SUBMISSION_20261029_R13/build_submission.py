"""Trim R12 review workbooks to DB model/request definitions; no schema change."""
from pathlib import Path
from copy import copy
import hashlib
import json
import re
import zipfile
from openpyxl import load_workbook

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
SOURCE=OUT.parent/'DATAIKU_GOLD_COMPACT_20261029_R12'
REMOVED=['00_축소요약','16_소프트관계','17_축소내역','18_코드검증','19_원천과정의']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def make(agent):
    original=SOURCE/f'법률에이전트_{agent}_골드축소안_R12.xlsx'
    w=load_workbook(original)
    for name in REMOVED:del w[name]
    overview=w['01_테이블목록']
    for merged in list(overview.merged_cells.ranges):overview.unmerge_cells(str(merged))
    overview.delete_cols(6)
    overview.merge_cells('A1:E1');overview.merge_cells('A2:E2')
    overview['A1']='골드 테이블 목록'
    overview['A2']='R13 신청용 정의서 · 13개 테이블 / 60개 컬럼 · 표준 승인 및 DB 생성 미완료'
    overview.auto_filter.ref='A4:E17';overview.print_area='A1:E17'
    overview.title='00_테이블목록'
    for i,s in enumerate(w.worksheets[1:14],1):
        s.title=f'{i:02}_'+s.title.split('_',1)[1]
        s['A2']='R13 신청용 정의서 · 테이블·컬럼·PK·필수값·기본값 · 표준 승인 및 DB 생성 미완료'
        overview.cell(i+4,2).hyperlink=f"#'{s.title}'!A1"
    index=w['15_인덱스']
    for row in range(index.max_row,4,-1):
        if index.cell(row,3).value=='PK':index.delete_rows(row)
    index.title='14_추가인덱스'
    index['A1']='추가 일반 인덱스 생성 요청 목록'
    index['A2']='일반 B-tree 11개 · PK 인덱스는 각 테이블의 PK 정의로 처리 · 생성 완료를 뜻하지 않음'
    index.auto_filter.ref=f'A4:D{index.max_row}';index.print_area=f'A1:D{index.max_row}'
    for s in w:
        s.oddFooter.center.text='R13 신청용 정의서 · &P / &N'
        s.sheet_state='visible'
    w.active=0
    w.properties.title=f'{agent} 골드 테이블·컬럼·추가인덱스 신청용 R13'
    w.properties.description='R12 데이터 모델 유지. 내부 설계 시트와 PK 인덱스 중복 목록 제외.'
    out=OUT/f'법률에이전트_{agent}_골드신청용_R13.xlsx';w.save(out)
    return original,out

def verify(pairs):
    results=[]
    model=json.loads((SOURCE/'MODEL.json').read_text())
    for original,path in pairs:
        before=load_workbook(original,data_only=True);after=load_workbook(path,data_only=True)
        assert len(after.worksheets)==15
        assert after.sheetnames[0]=='00_테이블목록' and after.sheetnames[-1]=='14_추가인덱스'
        assert not any(s.sheet_state!='visible' for s in after)
        assert not set(REMOVED)&set(after.sheetnames)
        assert after.worksheets[0].max_column==5
        count=0
        for old,new,t in zip(before.worksheets[2:15],after.worksheets[1:14],model['tables'],strict=True):
            a=list(old.iter_rows(min_row=4,values_only=True));b=list(new.iter_rows(min_row=4,values_only=True))
            assert a==b,(old.title,new.title)
            assert len(b)-1==len(t['columns'])
            count+=len(b)-1
        assert count==60
        index=after.worksheets[-1]
        oldindex=[row for row in before['15_인덱스'].iter_rows(min_row=5,values_only=True) if row[2]!='PK']
        newindex=list(index.iter_rows(min_row=5,values_only=True))
        assert oldindex==newindex and len(newindex)==11
        assert all(r[2]=='일반 B-tree' and re.match(r'X[1-9][0-9]*_',r[1]) for r in newindex)
        for row in range(5,18):
            link=after.worksheets[0].cell(row,2).hyperlink.target
            assert link==f"#'{after.worksheets[row-4].title}'!A1"
        assert not any(c.data_type=='f' for s in after for row in s for c in row)
        assert all(s.max_column==12 for s in after.worksheets[1:14])
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
        results.append({'file':path.name,'sha256':sha(path),'bytes':path.stat().st_size,'sheets':15,'tables':13,'columns':60,'pk_definitions':13,'additional_indexes':11,'pk_index_duplicate_rows':0,'table_and_column_values_unchanged':True,'ordinary_index_definitions_unchanged':True})
    books=[load_workbook(p,data_only=True) for _,p in pairs]
    normalize=lambda value:value.replace('B03','BXX').replace('B05','BXX') if isinstance(value,str) else value
    for a,b in zip(*books,strict=True):
        assert a.title==b.title
        for ar,br in zip(a.iter_rows(values_only=True),b.iter_rows(values_only=True),strict=True):
            assert list(map(normalize,ar))==list(map(normalize,br))
    return {'status':'PASS_SUBMISSION_CONTENT_CHECK','workbooks':results,'removed_review_sheets':REMOVED,'removed_table_list_columns':['변경'],'removed_pk_index_rows_per_workbook':13,'model_changed':False,'database_changed':False,'metaminer_import_tested':False,'native_excel_render':False,'mail_sent':False}

def main():
    pairs=[make(a) for a in ('B03','B05')]
    result=verify(pairs);dump('VALIDATION.json',result)
    evidence=OUT.parent/'DATAIKU_GOLD_REDESIGN_20261029_R11/evidence/photo_2.jpg'
    sourcefiles=[p for p,_ in pairs]+[SOURCE/'MODEL.json',SOURCE/'GOLD_B03_DDL_REVIEW.sql',SOURCE/'GOLD_B05_DDL_REVIEW.sql',evidence]
    dump('SOURCES.json',{'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sourcefiles]})
    print(json.dumps({'status':result['status'],'sheets_per_workbook':15,'tables':13,'columns':60,'additional_indexes':11,'removed_review_sheets':len(REMOVED),'removed_pk_index_rows':13},ensure_ascii=False))

if __name__=='__main__':main()
