"""Rename the dataset-version hash consistently in the B03/B05 registration workbooks."""
from pathlib import Path
import base64
import hashlib
import json
import zipfile
from openpyxl import load_workbook
from openpyxl.comments import Comment

HERE=Path(__file__).resolve().parent
R5=HERE.parent/'DATAIKU_GOLD_REGISTER_20261028_R5'
OLD_LOGICAL='데이터구축세대ID'
OLD_PHYSICAL='DATA_VER_ID'
LOGICAL='명세해시데이터값'
PHYSICAL='MNFST_HASH_DATA_VALU'
DOMAIN='데이터값'
WORDS='명세 · 해시'
DEFINITION='데이터 구성을 기록한 명세 파일(manifest.json)의 원시 바이트를 SHA-256으로 계산한 해시값. 구축된 데이터 버전을 구분한다.'
OUTS=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace_terms(v):
    if not isinstance(v,str):return v
    return (v.replace(OLD_LOGICAL,LOGICAL).replace(OLD_PHYSICAL,PHYSICAL)
            .replace('데이터 구축 세대','데이터 버전').replace('데이터 구축세대','데이터 버전')
            .replace('데이터 세대','데이터 버전'))

def update(agent, expected_hash):
    src=R5/f'법률에이전트_{agent}_골드등록용_테이블별_R5.xlsx'
    assert sha(src)==expected_hash, 'R5 원본이 달라져 검증 없이 덮어쓰지 않습니다.'
    w=load_workbook(src);hits=[]
    for sheet in w:
        for row in sheet:
            for cell in row:
                if cell.value is not None:cell.value=replace_terms(cell.value)
                # Preserve the original source-column name in physical-column comments.
                if cell.comment and cell.column!=3:
                    cell.comment.text=replace_terms(cell.comment.text)
        for row in range(7,sheet.max_row+1):
            if sheet.cell(row,3).value!=PHYSICAL:continue
            hits.append((sheet.title,row))
            sheet.cell(row,2,LOGICAL);sheet.cell(row,4,DOMAIN);sheet.cell(row,5,WORDS)
            sheet.cell(row,11,DEFINITION)
            sheet.cell(row,2).comment=Comment('용어 검색 후보: '+LOGICAL+'\n구성: 명세 + 해시 + 데이터값\n'+DEFINITION,'메타 검색')
            sheet.cell(row,3).comment=Comment('영문 물리 컬럼명 등록 후보: '+PHYSICAL+'\n현행 원천 컬럼: '+OLD_PHYSICAL+'\n타입: VARCHAR2(64 BYTE)\n'+sheet.cell(row,10).value,'현행 계약·등록 제안')
            sheet.cell(row,4).comment=Comment('도메인 검색어: 데이터값\n영문 종결 후보: DATA_VALU\nVARCHAR2(64 BYTE)에 맞는 등록 인포타입과 표준 약어를 메타에서 확인합니다.','메타 검색')
            sheet.cell(row,5).comment=Comment('도메인을 제외한 수식어 후보: 명세 · 해시. 등록 단어와 약어를 확인합니다.','단어 검색')
        if sheet.oddFooter.left.text:sheet.oddFooter.left.text=sheet.oddFooter.left.text.replace('R5','R6')
    assert {s for s,r in hits}=={'01_문서판본','02_문서구조','03_원문본문','04_원문게시'} and len(hits)==4
    w.properties.title=w.properties.title.replace('R5','R6')
    output=HERE/f'법률에이전트_{agent}_골드등록용_테이블별_R6.xlsx'
    w.save(output)
    check(output,src,hits)
    OUTS.append({'file':output.name,'bytes':output.stat().st_size,'sha256':sha(output),'changed_rows':len(hits),'sheets':len(w.sheetnames)})

def check(output,src,hits):
    before=load_workbook(src,data_only=False);after=load_workbook(output,data_only=False)
    assert before.sheetnames==after.sheetnames and len(after.sheetnames)==10
    constraints_changed=0
    for old,new in zip(before,after):
        assert len(new.tables)==1 and new.max_column==12 and new.freeze_panes=='E7'
        for row in old:
            for c in row:
                x=new[c.coordinate]
                if (old.title,c.row) in hits and c.column in (2,3,4,5,11):
                    expected={2:LOGICAL,3:PHYSICAL,4:DOMAIN,5:WORDS,11:DEFINITION}[c.column]
                else:expected=replace_terms(c.value)
                assert x.value==expected,(old.title,c.coordinate,c.value,x.value,expected)
                if c.column==10 and isinstance(c.value,str) and OLD_PHYSICAL in c.value:constraints_changed+=1
                assert not (isinstance(x.value,str) and (OLD_LOGICAL in x.value or OLD_PHYSICAL in x.value))
        for title,row in hits:
            if title==new.title:
                assert new.cell(row,6).value=='VARCHAR2' and new.cell(row,7).value=='64 BYTE'
                assert new.cell(row,9).value=='Y' and new.cell(row,12).value=='N'
    assert constraints_changed==8
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert not any(n.lower().endswith(('.js','.jsx','.mjs','.cjs','.bin')) for n in z.namelist())

def mail():
    body='''<p>안녕하세요.</p>
<p>법률 에이전트 B03·B05 골드 등록용 엑셀 수정본을 보내드립니다. 기존 R5 첨부를 대신해 이번 R6 파일을 사용해 주세요.</p>
<p>데이터구축세대ID를 명세해시데이터값으로 변경하고 영문 컬럼명, 도메인, 구성 단어, 관련 PK 표기를 일치시켰습니다. 실제 저장값과 VARCHAR2(64 BYTE) 계약은 같습니다.</p>
<p>각 파일은 10개 테이블을 한 시트씩 정리하고 제약조건·컬럼정의·문자열 한글 포함 여부를 유지합니다. 표준 용어·영문 약어·도메인·인포타입은 메타 조회 후 확정할 후보입니다.</p>
<p>감사합니다.</p>'''
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    for o in OUTS:
        p=HERE/o['file'];assert sha(p)==o['sha256']
        parts.append({'mime_type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','filename':p.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode('ascii')}})
    args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[법률 에이전트 B03·B05] 골드 등록용 엑셀 R6 — 명세해시데이터값 통일','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (HERE/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False),encoding='utf-8')
    (HERE/'EMAIL_PLAN.json').write_text(json.dumps({'status':'PREPARED_NOT_SENT','to':args['to'],'subject':args['subject'],'attachments':OUTS,'replaces':'R5'},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    prev=json.loads((R5/'VALIDATION.json').read_text())
    for entry in prev['workbooks']:
        agent='B03' if '_B03_' in entry['file'] else 'B05'
        update(agent,entry['sha256'])
    (HERE/'VALIDATION.json').write_text(json.dumps({'status':'PASS','workbooks':OUTS,'rows_per_workbook':4,'constraints_updated_per_workbook':8,'source_r5_unchanged':True,'actual_database_or_runtime_changed':False,'metadata_approved':False},ensure_ascii=False,indent=2)+'\n')
    mail()
    print(json.dumps({'workbooks':OUTS,'mail':'PREPARED_NOT_SENT'},ensure_ascii=False))
