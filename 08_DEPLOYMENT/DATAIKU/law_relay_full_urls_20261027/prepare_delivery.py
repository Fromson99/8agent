"""Add a grouped complete-URL reference to the validated relay handoff."""
from pathlib import Path
import base64
import hashlib
import html
import io
import json
import sys
import zipfile
from urllib.parse import quote, quote_plus, urlsplit, parse_qs
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'law_relay_list_examples_20261027'
EVIDENCE=HERE.parent/'law_relay_e2e_20261027'
OUT=HERE/'delivery';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(EVIDENCE))
from capture import load_oc

old_excel='법제처_중계등록_목록포함.xlsx'
excel='법제처_중계등록_전체URL포함.xlsx'
guide='법제처_API_시험예시.txt'
mail='법제처_중계등록_요청문.txt'
archive='법제처_목록본문파일_실제응답.zip'
url_file='법제처_전체호출URL.txt'
subject='RE: API중계서버 URL추가 문의 — 법제처 원천 접속정보 및 전체 호출 URL'
recipient='hyungjininfocz.son@partner.samsung.com'
specs=[
 ('① 행정규칙 목록 — 금융투자업규정 검색','05_list_admrul',False),
 ('② 법령 목록 — 자본시장법 검색','04_list_eflaw',False),
 ('③ 행정규칙 본문 — 행정규칙일련번호를 ID에 입력','06_body_admrul_id',False),
 ('④ 법령 본문 — 법령일련번호·시행일자를 MST·efYd에 입력','07_body_eflaw_date',False),
 ('⑤ 별표 HWP — 본문 XML에서 받은 파일 링크','02_annex',False),
 ('⑥ 개정전문 HWP — 본문 XML에서 받은 파일 링크','03_attachment',False),
 ('⑦ 개정전문 HWP 최종 주소 — ⑥의 301 이동 목적지','03_attachment',True),
]
rows=[]
for label,capture,final in specs:
    r=json.loads((EVIDENCE/'evidence'/(capture+'.json')).read_text())
    url=r['final_url'] if final else r['hops'][0]['url']
    p=urlsplit(url);q=parse_qs(p.query)
    assert p.hostname in ('www.law.go.kr','law.go.kr')
    if '/DRF/' in p.path:assert q['OC']==['{기관_OC}']
    rows.append((label,url))
assert parse_qs(urlsplit(rows[0][1]).query)['nw']==['1']
assert parse_qs(urlsplit(rows[1][1]).query)['nw']==['3']

block='''[전체 호출 URL 모음 — 모두 GET]
기본 주소와 입력값을 합친 시험용 URL입니다. ①~④의 {기관_OC}만 기관 인증값으로 교체하세요.
한글 검색어는 URL 인코딩되어 있습니다. ⑤~⑦의 파일 다운로드 요청에는 OC를 넣지 않습니다.

'''+ '\n\n'.join(label+'\n'+url for label,url in rows)+'''

문서번호·파일번호는 2026-10-27 실제 확인한 예시입니다. 운영에서는 목록·본문 XML에서 새로 받은 값을 사용합니다.
위 URL은 법제처 원천 주소입니다. 사내 시험에서는 담당 부서의 내부 중계 규격으로 해당 원천 URL과 쿼리를 전달합니다.
'''
(OUT/url_file).write_text(block)

body=(PREV/'delivery'/mail).read_text()
marker='2. 목록 조회 입력값과 실제 결과'
assert body.count(marker)==1
body=body.replace(marker,block+'\n'+marker)
body=body.replace(old_excel,excel)
body=body.replace('원천별 주소·포트·경로, 법령/행정규칙의 목록 입력값 비교,','원천별 주소·포트·경로, 전체 호출 URL 7개를 모은 시트, 법령/행정규칙의 목록 입력값 비교,')
body=body.replace('시험 도구에 복사할 GET URL, 기관 OC 입력 위치,','앞부분에 전체 호출 URL 7개를 모았으며, 기관 OC 입력 위치,')
body=body.replace('실제 목록 XML 2개, 본문 XML 2개, HWP 2개, 호출·응답 기록과 파일 검증정보, 시험 예시 문서를 담았습니다.','실제 목록 XML 2개, 본문 XML 2개, HWP 2개, 호출·응답 기록과 파일 검증정보, 시험 예시 및 전체 호출 URL 문서를 담았습니다.')
(OUT/mail).write_text(body)
guide_body=(PREV/'delivery'/guide).read_text()
assert guide_body.count('시험 방법\n')==1
guide_body=guide_body.replace('시험 방법\n',block+'\n시험 방법\n',1)
(OUT/guide).write_text(guide_body)
html_body='<!doctype html><html><body><div style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere">'+html.escape(body)+'</div></body></html>'
(OUT/'EMAIL_BODY.html').write_text(html_body)

wb=load_workbook(PREV/'delivery'/old_excel)
ws=wb.create_sheet('전체호출URL',1)
ws.append(['용도','메서드','전체 원천 URL','입력 안내'])
for i,(label,url) in enumerate(rows):
    ws.append([label,'GET',url,'{기관_OC}만 기관 인증값으로 교체' if i<4 else 'OC 없이 호출. flSeq는 실제 예시 값'])
ws.append(['사용 기준','','','문서·파일번호는 2026-10-27 확인한 값. 운영에서는 반환된 번호 사용. 원천 URL이며 내부 중계 규격은 별도.'])
for col,width in {'A':63,'B':12,'C':120,'D':54}.items():ws.column_dimensions[col].width=width
ws.freeze_panes='A2';ws.auto_filter.ref='A1:D8';ws.sheet_view.zoomScale=80
ws.print_title_rows='1:1';ws.sheet_properties.pageSetUpPr.fitToPage=True
ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
ws.row_dimensions[1].height=30
for c in ws[1]:
    c.font=Font(name='맑은 고딕',size=11,bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='17365D')
    c.alignment=Alignment(wrap_text=True,vertical='center')
for cells in ws.iter_rows(min_row=2):
    ws.row_dimensions[cells[0].row].height=90
    for c in cells:
        c.font=Font(name='맑은 고딕',size=11);c.alignment=Alignment(wrap_text=True,vertical='top')
        if c.row%2==0:c.fill=PatternFill('solid',fgColor='EFF4FA')
wb.save(OUT/excel)

unchanged=[]
with zipfile.ZipFile(PREV/'delivery'/archive) as old,zipfile.ZipFile(OUT/archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as new:
    for name in old.namelist():
        data=old.read(name)
        if name==mail:data=body.encode()
        elif name==guide:data=guide_body.encode()
        elif name=='README.txt':data=('전체 URL을 한 번에 보려면 '+url_file+'를 먼저 열어 주세요.\n\n').encode()+data
        else:unchanged.append({'file':name,'sha256':hashlib.sha256(data).hexdigest()})
        new.writestr(name,data)
    new.writestr(url_file,block.encode())

oc=load_oc()
tokens={s.encode(enc) for s in (oc,quote(oc,safe=''),quote_plus(oc)) for enc in ('utf-8','utf-16le','utf-16be')}
scanned=[]
def scan(name,data):
    assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
    assert not any(t in data for t in tokens),'Private authentication value detected'
    scanned.append(name)
    if data[:4]==b'PK\x03\x04':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            for child in z.namelist():scan(name+'!'+child,z.read(child))
for name in (excel,guide,mail,archive,url_file,'EMAIL_BODY.html'):scan(name,(OUT/name).read_bytes())
with zipfile.ZipFile(OUT/archive) as z:
    for item in unchanged:assert hashlib.sha256(z.read(item['file'])).hexdigest()==item['sha256']
    assert z.read(mail)==(OUT/mail).read_bytes() and z.read(guide)==(OUT/guide).read_bytes()
check=load_workbook(OUT/excel,read_only=True)
assert check.sheetnames[1]=='전체호출URL'
assert [check['전체호출URL'].cell(i+2,3).value for i in range(7)]==[url for _,url in rows]
check.close()
assert body.index('[전체 호출 URL 모음')>body.index('1. 원천 접속 정보')
assert body.index('[전체 호출 URL 모음')<body.index(marker)
attachments=[]
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':html_body}}]
for name,mime in [(excel,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),(guide,'text/plain'),(mail,'text/plain'),(archive,'application/zip')]:
    data=(OUT/name).read_bytes()
    attachments.append({'filename':name,'mime_type':mime,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(data).decode()}})
payload={'to':recipient,'subject':subject,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False))
manifest={'status':'READY_TO_SEND','recipient':recipient,'subject':subject,'attachments':attachments,'grouped_urls':rows,'private_credential_scan':'PASS including recursive XLSX/ZIP contents','javascript_scan':'PASS','scanned_entries':len(scanned),'preserved_evidence':unchanged,'new_origin_requests':0,'internal_relay_or_dataiku_execution':False}
(HERE/'DELIVERY_VALIDATION.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('status','recipient','subject','attachments','private_credential_scan','new_origin_requests')},ensure_ascii=False,indent=2))
print('Payload characters:',len((OUT/'EMAIL_PAYLOAD.json').read_text()))
