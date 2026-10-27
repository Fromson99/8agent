"""Build a credential-free relay registration email and actual response evidence."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import hashlib
import html
import io
import json
import re
import zipfile
from urllib.parse import quote, quote_plus

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from capture import load_oc

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'
DELIVERY = HERE / 'delivery'
DELIVERY.mkdir(exist_ok=True)
RECIPIENT = 'hyungjininfocz.son@partner.samsung.com'
SUBJECT = 'RE: API중계서버 URL추가 문의 — 법제처 중계 등록 및 실제 호출 예시'

captures = {name: json.loads((EVIDENCE / f'{name}.json').read_text())
            for name in ('01_body_http', '02_annex', '03_attachment')}
validation = json.loads((EVIDENCE / 'FORMAT_VALIDATION.json').read_text())
selected = json.loads((EVIDENCE / 'SELECTED_LINKS.json').read_text())
xml_bytes = (EVIDENCE / '금융투자업규정_본문응답.xml').read_bytes()
xml_text = xml_bytes.decode('utf-8')
tags = ('행정규칙명', '행정규칙일련번호', '시행일자', '별표서식파일링크', '첨부파일링크')
excerpt = '\n'.join(re.search(fr'<{tag}>.*?</{tag}>', xml_text, re.S).group(0) for tag in tags)
input_url = 'http://www.law.go.kr/DRF/lawService.do?OC={기관_OC}&target=admrul&type=XML&LM=금융투자업규정'

body = f'''안녕하세요. 안내 감사합니다.

Dataiku 배치에서 사용할 법제처 API 중계 경로의 등록·개발을 요청드립니다. 담당 범위는 아래 원천 접속 경로와 XML·파일 응답의 중계입니다. 실제 배치 실행과 XML에서 파일 링크를 읽어 후속 호출하는 처리는 Dataiku에서 수행합니다.

1. 등록에 필요한 접속 정보 (모두 GET)

[기존 제공 경로: DRF / HTTP / www.law.go.kr / TCP 80]
- /DRF/lawSearch.do: 목록 XML
  전달 파라미터: OC, target, type, search, query, nw, display, page
- /DRF/lawService.do: 본문 XML
  전달 파라미터: OC, target, type, MST, efYd, ID, LM
  target은 eflaw 또는 admrul이며, 조회 유형별 필요한 파라미터와 값은 호출자가 제공합니다.

[추가 등록: 파일 다운로드 및 실제 리다이렉트 목적지]
- HTTPS / www.law.go.kr / TCP 443 / /LSW/flDownload.do
- HTTP / law.go.kr / TCP 80 / /flDownload.do
- HTTPS / law.go.kr / TCP 443 / /LSW/flDownload.do
  전달 파라미터는 flSeq입니다. 마지막 경로는 두 번째 경로의 실제 301 이동 목적지입니다.

2. 실제 호출 예시: 금융투자업규정 입력 → XML → HWP 다운로드

아래는 2026-10-27 09:53(KST), 외부 개발환경에서 법제처 원천에 직접 요청하여 확인한 결과입니다. 사내 중계서버·Dataiku를 통한 실행 결과는 아닙니다. OC만 {{기관_OC}}로 가렸으며, 문서번호·파일번호·응답 파일은 실제 값입니다.

① 본문 요청
GET {input_url}
※ LM은 행정규칙명이며 실제 전송 시 한글을 URL 인코딩합니다. OC는 호출 시 별도로 제공합니다.

실제 응답: HTTP 200 / text/xml;charset=UTF-8 / 1,758,451바이트
XML 응답에서 관련 필드만 발췌한 내용입니다. 아래 필드들은 원문 내 서로 다른 위치에 있습니다.

{excerpt}

② XML의 별표서식파일링크로 별표 파일 요청
XML에는 /LSW/flDownload.do?flSeq=169196331이라는 상대경로가 들어 있습니다. 이번 예시에서는 https://www.law.go.kr을 붙여 아래 주소로 요청했습니다.
GET https://www.law.go.kr/LSW/flDownload.do?flSeq=169196331
→ HTTP 200 / HWP / 33,792바이트
→ 파일: [별표 1] (예비)인가절차 흐름도(제2-2조제1항 관련)(금융투자업규정).hwp

③ XML의 첨부파일링크로 개정전문 파일 요청
GET http://law.go.kr/flDownload.do?flSeq=169196311
→ HTTP 301
→ Location: https://law.go.kr/LSW/flDownload.do?flSeq=169196311
→ 위 Location을 GET으로 요청: HTTP 200 / HWP / 526,848바이트
→ 파일: 금융투자업규정 개정전문(금융위원회고시 제2026-38호)(20260909).hwp

즉, “원문 XML에서 반환되는 다운로드 구조”란 본문 API가 XML 안에 파일 주소를 내려주고, 그 주소를 다시 GET으로 호출하면 실제 파일이 내려오는 구조입니다. flSeq는 XML에서 받은 파일번호이며 예시 번호로 고정하지 않습니다. 위 두 다운로드 요청에는 OC를 넣지 않았습니다.

3. 중계 처리 요청

- 호출자가 지정한 등록 대상 원천 URL과 GET 쿼리를 전달하고, 동일 파라미터가 중복되지 않도록 처리 부탁드립니다. 한글 쿼리를 지원해 주세요.
- DRF는 XML, 다운로드는 원본 파일 바이너리로 반환해 주세요. 파일을 문자열이나 HTML로 변환하지 않아야 합니다.
- 위 301 이동까지 완료할 수 있도록 최종 HTTPS 목적지를 함께 등록해 주세요. 중계에서 이동을 따라가는 경우 최종 파일 응답을 반환하고, 이동 응답을 반환하는 방식이면 상태코드·Location을 전달해 Dataiku가 해당 목적지를 다시 중계 호출할 수 있어야 합니다.
- 응답의 상태코드, Content-Type, Content-Disposition(파일명), Content-Length(있는 경우)를 전달해 주세요.
- 개인 계정의 OC·API 키는 메일과 첨부에서 제외했습니다. 인증값은 호출 시 별도로 제공합니다.

필요한 네트워크·방화벽·중계 개발을 요청드립니다. 등록 후 사용할 내부 중계 경로와 요청 규격, 리다이렉트 처리 방식을 회신 부탁드립니다.

4. 첨부파일 설명

① 법제처_중계등록_실제호출예시.xlsx
   원천별 주소·포트·경로·파라미터·응답 형식, 중계 처리 요청, 실제 입력값과 응답·다운로드 결과를 정리했습니다.

② 법제처_중계등록_요청문.txt
   이 메일과 동일한 문안입니다. 신청서 작성이나 내부 전달 시 사용할 수 있습니다.

③ 법제처_실제응답_예시.zip
   실제 받은 본문 XML 전체, 별표 HWP, 개정전문 HWP와 호출·응답 기록(JSON), 파일 크기·SHA-256 및 읽는 순서를 담았습니다. 별도 실행이 필요한 프로그램은 없습니다.

감사합니다.
'''

txt_name = '법제처_중계등록_요청문.txt'
xlsx_name = '법제처_중계등록_실제호출예시.xlsx'
zip_name = '법제처_실제응답_예시.zip'
(DELIVERY / txt_name).write_text(body, encoding='utf-8')
html_body = '<!doctype html><html><body><div style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere">' + html.escape(body) + '</div></body></html>'
(DELIVERY / 'EMAIL_BODY.html').write_text(html_body, encoding='utf-8')

wb = Workbook()
ws = wb.active
ws.title = '원천등록표'
ws.append(['구분', '용도', '프로토콜', '도메인', 'TCP 포트', '경로', '메서드', '전달 파라미터', '응답·처리', '실제 예시·확인 범위'])
rows = [
 ['기존 제공 안내', '목록 조회', 'HTTP', 'www.law.go.kr', 80, '/DRF/lawSearch.do', 'GET', 'OC, target, type, search, query, nw, display, page\n조회 유형별 필요한 값 전달', 'XML', '이번 실호출 예시는 본문 조회부터 시작; 목록 API는 이번에 호출하지 않음'],
 ['기존 제공 안내', '본문 조회', 'HTTP', 'www.law.go.kr', 80, '/DRF/lawService.do', 'GET', 'OC, target, type, MST, efYd, ID, LM\n조회 유형별 필요한 값 전달', 'XML', 'OC={기관_OC}, target=admrul, type=XML, LM=금융투자업규정\n실제 200 / 1,758,451바이트'],
 ['추가 등록 요청', '별표 다운로드', 'HTTPS', 'www.law.go.kr', 443, '/LSW/flDownload.do', 'GET', 'flSeq (XML에서 받은 값)', '원본 파일 바이너리', 'flSeq=169196331\n실제 200 / HWP / 33,792바이트'],
 ['추가 등록 요청', '첨부 다운로드 시작', 'HTTP', 'law.go.kr', 80, '/flDownload.do', 'GET', 'flSeq (XML에서 받은 값)', '이번 예시는 301 및 Location 반환', 'flSeq=169196311\nLocation=https://law.go.kr/LSW/flDownload.do?flSeq=169196311'],
 ['추가 등록 요청', '첨부 다운로드 최종 목적지', 'HTTPS', 'law.go.kr', 443, '/LSW/flDownload.do', 'GET', 'flSeq (Location에서 받은 값)', '원본 파일 바이너리', 'flSeq=169196311\n실제 200 / HWP / 526,848바이트'],
]
for row in rows:
    ws.append(row)

ws = wb.create_sheet('전달계약')
ws.append(['항목', '요청 내용'])
contracts = [
 ('사용 흐름', 'Dataiku 배치 → API 중계서버 → 법제처 원천'),
 ('등록 담당 범위', '원천 접속 등록·네트워크/방화벽·API 중계 개발. 배치 실행과 XML 파싱·후속 파일 선택은 Dataiku 담당.'),
 ('요청 전달', '등록 대상 원천 URL과 GET 쿼리 전달. 한글 인코딩 지원, 동일 쿼리 중복 추가 방지. 내부 중계 경로와 요청 규격 회신 요청.'),
 ('DRF target', 'eflaw 또는 admrul. 필요한 파라미터는 조회 유형에 맞게 호출자가 제공. 이번 실제 예시는 admrul.'),
 ('XML 상대경로 처리', '이번 별표 링크 /LSW/flDownload.do?...는 Dataiku 쪽에서 https://www.law.go.kr을 붙여 요청하는 예시. 중계가 XML 내용을 해석할 필요 없음.'),
 ('301 처리', 'law.go.kr:80/flDownload.do → law.go.kr:443/LSW/flDownload.do를 등록. 중계가 따라가면 최종 파일 반환. 301을 호출자에게 반환하는 규격이면 상태·Location 전달 후 Dataiku가 최종 목적지를 다시 중계 호출.'),
 ('응답 전달', 'XML·원본 바이너리 유지. HTTP 상태, Content-Type, Content-Disposition 및 Content-Length(있을 때) 전달. 301 전달 시 Location 유지.'),
 ('인증값', '개인 계정 발급값은 문서·첨부에서 제외. OC는 {기관_OC}로 표기하고 실행 시 별도 제공. 실제 두 파일 다운로드 요청에는 OC 미사용.'),
 ('예시 번호', 'flSeq는 XML에서 받은 값. 예시 파일번호를 운영 고정값으로 등록하지 않음.'),
 ('실제 확인 범위', '2026-10-27 09:53 KST 외부 WSL → 법제처 본문 XML → 선택한 링크 두 건 → HWP 두 파일. 사내 중계·Dataiku 실행 미수행.'),
 ('담당자 회신 요청', '내부 중계 주소·요청 규격·리다이렉트 처리 방식. 네트워크·방화벽·중계 등록/개발 진행 요청.'),
]
for row in contracts:
    ws.append(row)

ws = wb.create_sheet('실제호출예시')
ws.append(['단계', '입력·XML 필드', '실제 요청 URL·파라미터', '응답', '증빙 ZIP 내 파일·설명'])
ws.append(['1. 본문 XML', 'LM=금융투자업규정\ntarget=admrul\ntype=XML\nOC={기관_OC}', input_url, '200 / text/xml;charset=UTF-8\n1,758,451바이트\n일련번호 2100000285020\n시행일자 20260915', '금융투자업규정_본문응답.xml\n호출응답기록.json'])
ws.append(['2. XML에서 별표 링크', '별표서식파일링크\n/LSW/flDownload.do?flSeq=169196331', captures['02_annex']['requested_url'], '200 / application/hwp;;charset=UTF-8\n33,792바이트', '별표1_인가절차흐름도.hwp\n응답의 원래 파일명은 호출응답기록.json에 보존'])
ws.append(['3. XML에서 첨부 링크', '첨부파일링크\nhttp://law.go.kr/flDownload.do?flSeq=169196311', captures['03_attachment']['requested_url'], '301\nLocation: https://law.go.kr/LSW/flDownload.do?flSeq=169196311', '호출응답기록.json: 첫 번째 hop'])
ws.append(['4. Location 후속 요청', '301 응답의 Location', captures['03_attachment']['final_url'], '200 / application/hwp;;charset=UTF-8\n526,848바이트', '금융투자업규정_개정전문.hwp\n호출응답기록.json: 두 번째 hop'])
ws.append(['형식 확인', '실제 반환된 파일 확인', 'XML 파싱 및 HWP OLE FileHeader 확인', '두 파일 모두 HWP Document File 서명 확인', '파일검증.json: 원본 파일 크기·SHA-256\nHWP 본문 법률 내용 검토나 화면 렌더링 확인을 뜻하지 않음'])
ws.append(['범위', '외부 원천 직접 호출 예시', '사내 중계서버 및 Dataiku에서는 실행하지 않음', '2026-10-27 09:53 KST', '개인 OC 제외. 발송 XML과 HWP는 실제 수신 바이트와 동일.'])

widths = {'원천등록표': [20,24,13,22,13,29,12,48,37,65], '전달계약': [28,120], '실제호출예시': [25,53,90,61,65]}
for ws in wb:
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.zoomScale = 80
    ws.print_title_rows = '1:1'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    for i, width in enumerate(widths[ws.title], 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for cell in ws[1]:
        cell.fill = PatternFill('solid', fgColor='17365D')
        cell.font = Font(name='맑은 고딕', size=11, color='FFFFFF', bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[1].height = 30
    for row in ws.iter_rows(min_row=2):
        ws.row_dimensions[row[0].row].height = 80 if ws.title != '전달계약' else 61
        for cell in row:
            cell.font = Font(name='맑은 고딕', size=11)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if cell.row % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='EFF4FA')
wb.save(DELIVERY / xlsx_name)

record = {'확인시각_KST': '2026-10-27 09:53',
          '범위': '외부 WSL에서 법제처 원천 직접 호출. 사내 중계서버·Dataiku 실행 결과가 아님.',
          '인증값': '개인 OC는 {기관_OC}로 대체. 파일 요청에는 OC를 사용하지 않음.',
          '문서': validation['document_metadata'], '호출': []}
kept = ('label','started_utc','method','requested_url','params','hops','status','content_type','content_disposition','final_url','bytes','sha256','elapsed_seconds')
for label, capture in captures.items():
    item = {key: capture[key] for key in kept if key in capture}
    item['started_KST'] = datetime.fromisoformat(capture['started_utc']).astimezone(ZoneInfo('Asia/Seoul')).isoformat()
    if label != '01_body_http':
        item.update(next(link for link in selected['selected_links'] if link['label'] == label))
        item['decoded_content_disposition'] = next(v['decoded_content_disposition'] for v in validation['hwp_files'] if v['label'] == label)
    record['호출'].append(item)

readme = '''법제처 실제 응답 예시 — 2026-10-27

읽는 순서
1. 실제호출설명.txt: 입력 → XML → 별표·첨부 다운로드 흐름과 등록 요청.
2. 금융투자업규정_본문응답.xml: 본문 API에서 실제 받은 전체 XML.
3. 별표1_인가절차흐름도.hwp: XML 별표서식파일링크에서 받은 실제 파일.
4. 금융투자업규정_개정전문.hwp: XML 첨부파일링크에서 301 Location을 따라 받은 실제 파일.
5. 호출응답기록.json: OC를 가린 입력값, 실제 요청 주소·상태·헤더·301 이동·원래 파일명.
6. 파일검증.json: 원본과 전달 XML의 동일성, 실제 HWP 형식·크기·SHA-256.

HWP의 전달 파일명은 읽기 쉽게 줄였으며 내용 바이트는 수신 원본과 동일합니다.
이는 외부 개발환경 → 법제처 원천에서 확인한 예시입니다. 사내 중계·Dataiku를 통한 실행 결과가 아닙니다.
개인 계정의 OC·API 키·쿠키를 포함하지 않습니다. 실행 프로그램은 없으며 문서와 실제 응답 파일을 열어 확인하면 됩니다.
'''
members = {
 'README.txt': readme.encode('utf-8'),
 '실제호출설명.txt': body.encode('utf-8'),
 '금융투자업규정_본문응답.xml': xml_bytes,
 '별표1_인가절차흐름도.hwp': (HERE/'private_raw/02_annex.body').read_bytes(),
 '금융투자업규정_개정전문.hwp': (HERE/'private_raw/03_attachment.body').read_bytes(),
 '호출응답기록.json': (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
 '파일검증.json': (json.dumps(validation, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
}
with zipfile.ZipFile(DELIVERY/zip_name, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name, data in members.items():
        z.writestr(name, data)

# Check document values, exact raw-output hashes, nested Office/archive content,
# and absence of the private authentication value before constructing email.
assert hashlib.sha256(xml_bytes).hexdigest() == validation['xml_original_sha256']
for label, filename in [('02_annex','별표1_인가절차흐름도.hwp'), ('03_attachment','금융투자업규정_개정전문.hwp')]:
    assert hashlib.sha256(members[filename]).hexdigest() == captures[label]['sha256']
assert captures['03_attachment']['hops'][0]['status'] == 301
assert captures['03_attachment']['hops'][0]['headers']['Location'] == captures['03_attachment']['final_url']
assert all(c['status'] == 200 for c in captures.values())
check_wb = load_workbook(DELIVERY/xlsx_name, read_only=True)
assert check_wb.sheetnames == ['원천등록표','전달계약','실제호출예시']
assert check_wb['원천등록표'].max_row == 6
check_wb.close()

oc = load_oc()
tokens = {v.encode(enc) for v in (oc, quote(oc,safe=''), quote_plus(oc)) for enc in ('utf-8','utf-16le','utf-16be')}
scanned = []
def scan(name, data):
    assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}, 'Forbidden email attachment type'
    assert not any(token in data for token in tokens), 'Private credential found; do not send'
    scanned.append(name)
    if data[:4] == b'PK\x03\x04':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            for child in z.namelist():
                scan(name+'!'+child, z.read(child))
for name in (txt_name, xlsx_name, zip_name, 'EMAIL_BODY.html'):
    scan(name, (DELIVERY/name).read_bytes())

mime_types = ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','text/plain','application/zip']
parts = [{'mime_type':'text/html','charset':'UTF-8','body':{'content':html_body}}]
attachments = []
for name, mime in zip((xlsx_name, txt_name, zip_name), mime_types):
    data = (DELIVERY/name).read_bytes()
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(data).decode('ascii')}})
    attachments.append({'filename':name,'mime_type':mime,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
payload = {'to':RECIPIENT,'subject':SUBJECT,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(DELIVERY/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
manifest = {'status':'READY_TO_SEND','recipient':RECIPIENT,'subject':SUBJECT,'attachments':attachments,
            'private_credential_scan':'PASS; real OC and encoded variants excluded, including nested XLSX/ZIP members',
            'forbidden_javascript_scan':'PASS','scanned_entries':len(scanned),'zip_members':list(members),
            'origin_evidence':'Actual public-origin XML and two HWP files; captured bytes preserved.',
            'internal_relay_or_dataiku_execution':False}
(HERE/'DELIVERY_VALIDATION.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
print('Payload bytes:', (DELIVERY/'EMAIL_PAYLOAD.json').stat().st_size)
