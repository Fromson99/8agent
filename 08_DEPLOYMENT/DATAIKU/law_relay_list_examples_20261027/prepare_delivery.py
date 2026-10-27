"""Prepare the requested list/body/download examples for relay registration."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import hashlib
import html
import io
import json
import re
import sys
import zipfile
from urllib.parse import quote, quote_plus
import xml.etree.ElementTree as ET

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'law_relay_e2e_20261027'
sys.path.insert(0, str(SOURCE))
from capture import load_oc, redact

OUT = HERE / 'delivery'
OUT.mkdir(exist_ok=True)
RECIPIENT = 'hyungjininfocz.son@partner.samsung.com'
SUBJECT = 'RE: API중계서버 URL추가 문의 — 법제처 목록·본문·파일 조회 접속정보 및 시험 예시'
EXCEL = '법제처_중계등록_목록포함.xlsx'
GUIDE = '법제처_API_시험예시.txt'
MAIL = '법제처_중계등록_요청문.txt'
ZIP = '법제처_목록본문파일_실제응답.zip'
E = SOURCE / 'evidence'
labels = ['04_list_eflaw', '05_list_admrul', '06_body_admrul_id', '07_body_eflaw_date', '02_annex', '03_attachment']
reports = {k: json.loads((E / (k+'.json')).read_text()) for k in labels}
for r in reports.values():
    assert r['transport_complete'] and r['status'] == 200
lists = {r['label']:r for r in json.loads((E/'LIST_EXAMPLES.json').read_text())}
body_examples = {r['label']:r for r in json.loads((E/'LIST_TO_BODY_EXAMPLES.json').read_text())}
validation = json.loads((E/'FORMAT_VALIDATION.json').read_text())
urls = {k:r['hops'][0]['url'] for k,r in reports.items()}
admrul_xml = (SOURCE/'private_raw/06_body_admrul_id.body').read_bytes()
admrul_root = ET.fromstring(admrul_xml)
law_xml = (SOURCE/'private_raw/07_body_eflaw_date.body').read_bytes()
law_root = ET.fromstring(law_xml)
assert admrul_root.findtext('.//행정규칙일련번호') == '2100000285020'
assert law_root.findtext('.//법령ID') == '010513'
assert law_root.findtext('.//시행일자') == '20261002'
assert admrul_root.findtext('.//별표서식파일링크').strip() == '/LSW/flDownload.do?flSeq=169196331'
assert admrul_root.findtext('.//첨부파일링크').strip() == reports['03_attachment']['requested_url']
admrul_row = next(r for r in lists['05_list_admrul']['rows'] if r['행정규칙명']=='금융투자업규정')
law_row = next(r for r in lists['04_list_eflaw']['rows'] if r['법령명한글']=='자본시장과 금융투자업에 관한 법률')
assert admrul_row['행정규칙일련번호'] == reports['06_body_admrul_id']['params']['ID']
assert law_row['법령일련번호'] == reports['07_body_eflaw_date']['params']['MST']
assert law_row['시행일자'] == reports['07_body_eflaw_date']['params']['efYd']

registry = [
 ['기존 제공 경로', '목록 XML', 'HTTP', 'www.law.go.kr', 80, '/DRF/lawSearch.do', 'GET', 'OC, target, type, search, query, nw, display, page', 'eflaw: nw=3 / admrul: nw=1 (현행 기준)'],
 ['기존 제공 경로', '본문 XML', 'HTTP', 'www.law.go.kr', 80, '/DRF/lawService.do', 'GET', 'OC, target, type, ID, MST, efYd, LM', '필요한 조회 방식의 값만 전달. 실제 예시는 admrul+ID, eflaw+MST+efYd'],
 ['추가 등록', '별표 파일', 'HTTPS', 'www.law.go.kr', 443, '/LSW/flDownload.do', 'GET', 'flSeq', '이번 예시: 169196331 → 200 HWP'],
 ['추가 등록', '첨부 파일 시작 주소', 'HTTP', 'law.go.kr', 80, '/flDownload.do', 'GET', 'flSeq', '이번 예시: 169196311 → 301 및 Location'],
 ['추가 등록', '첨부 파일 최종 주소', 'HTTPS', 'law.go.kr', 443, '/LSW/flDownload.do', 'GET', 'flSeq', '위 301의 실제 이동 목적지 → 200 HWP'],
]
parameters = [
 ['OC', '{기관_OC}', '{기관_OC}', '신청한 기관 인증값. 문서의 자리표시자를 실제 기관 값으로 교체. 개인 발급값 제외.'],
 ['target', 'eflaw', 'admrul', 'eflaw: 시행일 기준 법령 / admrul: 행정규칙'],
 ['type', 'XML', 'XML', '반환 형식'],
 ['search', '1', '1', '문서명에서 검색'],
 ['query', '자본시장과 금융투자업에 관한 법률', '금융투자업규정', '검색할 이름. 이름이 포함된 관련 문서도 반환될 수 있음. 한글은 URL 인코딩.'],
 ['nw', '3', '1', '둘 다 현행을 의미하나 코드가 다름. eflaw: 1 연혁/2 시행예정/3 현행, admrul: 1 현행/2 연혁'],
 ['display', '10', '10', '한 페이지 최대 10건. 공식 최대값 100. 전체 수집 건수라는 뜻이 아님.'],
 ['page', '1', '1', '첫 페이지. 다음 페이지는 2. 운영 반복 조회는 Dataiku가 담당.'],
]

guide = f'''법제처 API 시험 예시 — 목록 → 본문 → 파일
작성일: 2026-10-27

시험 방법
- 각 예시는 HTTP GET입니다. 아래 URL 한 줄을 API 시험 도구의 URL 칸에 넣어 호출할 수 있습니다.
- DRF URL의 {{기관_OC}}를 사용 가능한 기관 인증값으로 바꿔 넣습니다. 중괄호는 제거합니다. 개인 계정 발급값은 제공하지 않습니다.
- 한글 검색어는 아래 URL에서 이미 인코딩했습니다. URL을 붙여넣은 뒤 같은 쿼리를 Params에 다시 추가하지 마세요.
- Params 화면에서 직접 입력한다면 query에는 표에 있는 한글 원문을 넣고 도구의 URL 인코딩을 사용합니다.
- 아래는 법제처 원천 URL입니다. 중계 시험에서는 등록된 내부 중계 규격으로 이 원천 URL·쿼리를 전달합니다. 내부 중계 주소와 인증 규격은 담당 부서에서 정합니다.
- 법제처 원천의 실제 응답을 첨부했습니다. 사내 중계서버·Dataiku에서 실행한 결과는 아닙니다.

공통 목록 경로
http://www.law.go.kr/DRF/lawSearch.do
공통 입력: OC={{기관_OC}}, type=XML, search=1, display=10, page=1
법령 입력: target=eflaw, nw=3, query=자본시장과 금융투자업에 관한 법률
행정규칙 입력: target=admrul, nw=1, query=금융투자업규정
※ nw는 두 유형에서 뜻에 대응하는 숫자가 다릅니다. 같은 값을 공통 고정하지 않습니다.
※ 목록 검색어는 query입니다. LM은 행정규칙 본문에서 이름으로 찾을 때 쓰는 값입니다.

A. 행정규칙: 목록 → 선택 → 본문 → 파일

A1. 목록 조회
GET {urls['05_list_admrul']}
실제 응답: HTTP 200 / XML / 1,784바이트 / totalCnt=2 / page=1
1) 금융투자업규정: 행정규칙일련번호=2100000285020, 행정규칙ID=36022, 시행일자=20260915
2) 금융투자업규정시행세칙: 행정규칙일련번호=2200000108855, 행정규칙ID=2034226, 시행일자=20260708
결과 비교 파일: 01_행정규칙_목록.xml

A2. 목록에서 정확한 문서명 '금융투자업규정'을 선택하여 본문 조회
입력 연결: 목록의 행정규칙일련번호 → 본문 요청 ID
ID=2100000285020을 사용합니다. 행정규칙ID=36022를 ID에 넣는 예시는 아닙니다.
GET {urls['06_body_admrul_id']}
실제 응답: HTTP 200 / XML / 1,758,451바이트
행정규칙명=금융투자업규정, 행정규칙일련번호=2100000285020, 시행일자=20260915
결과 비교 파일: 02_금융투자업규정_본문.xml
※ 이름으로 직접 조회하는 LM 방식도 있으나 여기서는 목록에서 받은 번호를 연결합니다.

A3. 본문 XML의 별표서식파일링크로 파일 요청
XML 값: /LSW/flDownload.do?flSeq=169196331
이번 예시는 https://www.law.go.kr을 붙여 아래 주소로 요청합니다.
GET {urls['02_annex']}
실제 응답: HTTP 200 / application/hwp;;charset=UTF-8 / 33,792바이트
원래 파일명: [별표 1] (예비)인가절차 흐름도(제2-2조제1항 관련)(금융투자업규정).hwp
결과 비교 파일: 03_별표1_인가절차흐름도.hwp

A4. 본문 XML의 첨부파일링크로 파일 요청
XML 값: http://law.go.kr/flDownload.do?flSeq=169196311
GET {urls['03_attachment']}
실제 첫 응답: HTTP 301
Location: {reports['03_attachment']['final_url']}
자동 이동을 꺼 둔 도구에서는 301과 Location을 확인할 수 있습니다.
자동 이동을 켜면 최종 파일까지 받게 됩니다. 수동으로 확인하려면 다음 주소를 GET으로 요청합니다.
GET {reports['03_attachment']['final_url']}
실제 최종 응답: HTTP 200 / application/hwp;;charset=UTF-8 / 526,848바이트
원래 파일명: 금융투자업규정 개정전문(금융위원회고시 제2026-38호)(20260909).hwp
결과 비교 파일: 04_금융투자업규정_개정전문.hwp
※ A3/A4 파일 요청에는 OC를 넣지 않았습니다.

B. 법령: 목록 → 선택 → 본문

B1. 목록 조회
GET {urls['04_list_eflaw']}
실제 응답: HTTP 200 / XML / 2,843바이트 / totalCnt=3 / page=1
1) 자본시장과 금융투자업에 관한 법률: 법령일련번호=288615, 법령ID=010513, 시행일자=20261002
2) 자본시장과 금융투자업에 관한 법률 시행규칙: 법령일련번호=291415, 법령ID=010820, 시행일자=20261020
3) 자본시장과 금융투자업에 관한 법률 시행령: 법령일련번호=291081, 법령ID=010817, 시행일자=20261013
결과 비교 파일: 05_법령_목록.xml

B2. 목록에서 정확한 문서명 '자본시장과 금융투자업에 관한 법률'을 선택하여 본문 조회
입력 연결: 목록의 법령일련번호 → MST, 목록의 시행일자 → efYd
GET {urls['07_body_eflaw_date']}
실제 응답: HTTP 200 / XML / 2,185,564바이트
법령명_한글=자본시장과 금융투자업에 관한 법률, 법령ID=010513, 시행일자=20261002
결과 비교 파일: 06_자본시장법_본문.xml
※ 이 예시는 목록에서 선택한 판본을 MST+efYd로 지정합니다. 법령ID를 ID에 넣어 현행 본문을 찾는 방법도 있지만 혼동을 줄이기 위해 예시는 한 방식으로 작성했습니다.

시험 결과 읽는 법
- 검색 결과의 첫 행을 무조건 선택하지 말고 정확한 문서명과 반환된 번호를 확인합니다.
- totalCnt는 검색 전체 건수, display는 한 페이지 건수입니다. 모든 문서를 한 번에 받는 의미가 아닙니다.
- 표의 건수·파일번호·크기는 2026-10-27에 실제 확인한 값입니다. 이후 갱신 시 목록 결과가 바뀔 수 있으므로 운영에서는 새 응답의 번호를 사용합니다.
- XML은 정상 파싱 여부와 문서명·번호를 확인하고, 파일은 HTML 오류 페이지가 아닌 HWP 바이너리가 내려오는지 확인합니다.
- 다운로드의 상태·Content-Type·Content-Disposition(파일명), 301 응답의 Location도 확인합니다.
- 중계에서 자동 이동을 처리하면 최종 파일 응답을 반환합니다. 301을 반환하는 규격이라면 Dataiku가 Location의 목적지를 중계로 다시 요청할 수 있게 전달해야 합니다.
- 중계 담당 범위는 접속 경로·파라미터·XML/바이너리·리다이렉트의 전달입니다. 운영 배치와 XML 파싱·문서 선택은 Dataiku가 담당합니다.

실제 증빙
목록·본문·파일은 각 요청 시점의 실제 응답입니다. 요청별 시각·상태·헤더·크기·SHA-256은 호출응답기록.json과 파일검증.json에 있습니다.
행정규칙 ID 본문의 다운로드 링크가 실제 첨부 HWP 요청의 링크와 일치함을 확인했습니다.
개인 OC는 요청 기록에서 {{기관_OC}}로 가렸습니다. XML 내부에 개인 인증값이 있으면 그 값도 가립니다.

공식 API 안내
법령 목록: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide
행정규칙 목록: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide
법령 본문: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide
행정규칙 본문: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide
'''

body = f'''안녕하세요. 안내 감사합니다.

Dataiku 배치에서 사용할 법제처 API 중계 경로의 등록·개발을 요청드립니다. 접속 정보와 함께 담당자께서 직접 시험하실 수 있는 목록·본문·파일 요청 예시 및 실제 응답을 전달드립니다.
등록·시험에는 이 메일의 첨부 문서를 사용해 주세요.

1. 원천 접속 정보 (모두 GET)

[기존 제공 경로 / HTTP / www.law.go.kr / TCP 80]
- /DRF/lawSearch.do: 목록 XML
  전달 파라미터: OC, target, type, search, query, nw, display, page
- /DRF/lawService.do: 본문 XML
  전달 파라미터: OC, target, type, ID, MST, efYd, LM (조회 방식에 맞는 값만 사용)

[추가 등록: 파일 및 리다이렉트 목적지]
- HTTPS / www.law.go.kr / TCP 443 / /LSW/flDownload.do
- HTTP / law.go.kr / TCP 80 / /flDownload.do
- HTTPS / law.go.kr / TCP 443 / /LSW/flDownload.do
  파일의 전달 파라미터는 flSeq입니다. 마지막 경로는 두 번째 경로의 실제 301 이동 목적지입니다.

2. 목록 조회 입력값과 실제 결과

목록 조회는 같은 /DRF/lawSearch.do를 사용합니다. 조회 대상별로 target·query·nw를 바꿉니다.
- 공통: OC={{기관_OC}}, type=XML, search=1(문서명 검색), display=10(페이지당 최대 10건), page=1
- 법령: target=eflaw, nw=3(현행), query=자본시장과 금융투자업에 관한 법률
- 행정규칙: target=admrul, nw=1(현행), query=금융투자업규정
※ 현행 자료의 nw 값은 법령 3, 행정규칙 1로 서로 다릅니다. 목록의 검색어는 query에 넣습니다.

① 행정규칙 목록 GET
{urls['05_list_admrul']}
실제 결과: HTTP 200 / 2건 — 금융투자업규정, 금융투자업규정시행세칙
금융투자업규정의 행정규칙일련번호: 2100000285020

② 법령 목록 GET
{urls['04_list_eflaw']}
실제 결과: HTTP 200 / 3건 — 자본시장과 금융투자업에 관한 법률, 시행규칙, 시행령
법률의 법령일련번호: 288615 / 시행일자: 20261002

위 URL은 한글 검색어가 인코딩되어 있습니다. {{기관_OC}}만 기관에서 사용할 인증값으로 교체하여 시험할 수 있습니다. 같은 검색어가 이름에 포함된 관련 문서도 나오므로 결과에서 원하는 문서를 선택합니다.

3. 목록에서 받은 번호로 본문 조회

① 행정규칙: 행정규칙일련번호 → ID
GET {urls['06_body_admrul_id']}
실제 결과: HTTP 200 / 금융투자업규정 본문 XML / 1,758,451바이트
※ 여기의 ID에는 행정규칙일련번호 2100000285020을 넣습니다.

② 법령: 법령일련번호 → MST, 시행일자 → efYd
GET {urls['07_body_eflaw_date']}
실제 결과: HTTP 200 / 자본시장과 금융투자업에 관한 법률 본문 XML / 2,185,564바이트

4. 본문 XML에서 받은 링크로 파일 다운로드

금융투자업규정 XML의 별표서식파일링크는 /LSW/flDownload.do?flSeq=169196331입니다.
GET {urls['02_annex']}
→ HTTP 200 / 별표 1 (예비)인가절차 흐름도 HWP / 33,792바이트

같은 XML의 첨부파일링크는 http://law.go.kr/flDownload.do?flSeq=169196311입니다.
GET {urls['03_attachment']}
→ HTTP 301 / Location: {reports['03_attachment']['final_url']}
→ Location 주소 GET: HTTP 200 / 금융투자업규정 개정전문 HWP / 526,848바이트

이처럼 목록에서 문서번호를 받아 본문 XML을 조회하고, XML이 제공한 파일 주소를 다시 GET으로 호출하면 실제 파일을 받습니다. flSeq는 XML에서 받은 값이며 예시 번호로 고정하지 않습니다.

5. 중계 처리 요청

- 호출 시스템은 Dataiku이며 운영 배치·XML 파싱·문서 선택은 Dataiku에서 수행합니다.
- 중계 담당 범위는 위 원천 접속 경로의 등록과 GET 쿼리·XML·파일 바이너리 전달입니다. 한글 인코딩을 지원하고 동일 파라미터의 중복 추가를 방지해 주세요.
- 파일 다운로드의 최종 HTTPS 목적지를 함께 등록해 주세요. 중계에서 301을 따라가면 최종 파일 응답을 반환하고, 301을 그대로 전달하는 규격이면 상태·Location을 전달해 후속 중계 호출이 가능해야 합니다.
- HTTP 상태, Content-Type, Content-Disposition(파일명), Content-Length(있는 경우)를 전달해 주세요. 파일 바이너리는 그대로 반환해 주세요.
- 내부 중계 주소·요청 규격·리다이렉트 처리 방식을 회신 부탁드립니다.

예시 결과는 2026-10-27 외부 개발환경에서 법제처 원천에 직접 호출한 기록입니다. 사내 중계·Dataiku 실행 결과와 구분합니다. 개인 계정의 OC·API 키는 모두 제외했으며 인증값은 시험 시 별도로 넣습니다.

6. 첨부파일 설명

① {EXCEL}
   원천별 주소·포트·경로, 법령/행정규칙의 목록 입력값 비교, 목록 번호→본문 입력값 연결, 실제 응답과 중계 처리 요청을 정리했습니다.

② {GUIDE}
   시험 도구에 복사할 GET URL, 기관 OC 입력 위치, 단계별 실제 결과와 비교 기준을 담았습니다. 별도 프로그램 설치 없이 사용하는 요청 예시 문서입니다.

③ {MAIL}
   이 메일과 동일한 문안입니다. 신청서 작성이나 내부 전달 시 사용할 수 있습니다.

④ {ZIP}
   실제 목록 XML 2개, 본문 XML 2개, HWP 2개, 호출·응답 기록과 파일 검증정보, 시험 예시 문서를 담았습니다. 요청별 시각·상태·301 이동·파일명을 확인할 수 있습니다.

감사합니다.
'''
(OUT/GUIDE).write_text(guide)
(OUT/MAIL).write_text(body)
html_body = '<!doctype html><html><body><div style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere">'+html.escape(body)+'</div></body></html>'
(OUT/'EMAIL_BODY.html').write_text(html_body)

contracts = [
 ['사용 흐름', 'Dataiku 배치 → API 중계서버 → 법제처'],
 ['중계 담당 범위', '접속 경로 등록·네트워크/방화벽·중계 개발·요청 및 응답 전달. 배치 실행·XML 파싱·후속 문서/파일 선택은 Dataiku 담당.'],
 ['목록 공통점·차이', 'GET /DRF/lawSearch.do 공통. target/query/nw 등 입력값은 자료 유형별 전달. 현행 eflaw nw=3, admrul nw=1.'],
 ['본문 번호 연결', 'admrul: 행정규칙일련번호→ID. eflaw 예시: 법령일련번호→MST, 시행일자→efYd.'],
 ['시험 입력', 'URL의 {기관_OC}를 기관 인증값으로 교체. 인코딩된 URL과 Params에 같은 쿼리를 중복 추가하지 않음.'],
 ['파일 전달', 'XML 및 원본 파일 바이너리 유지. HTTP 상태, Content-Type, Content-Disposition, Content-Length(있는 경우) 전달.'],
 ['리다이렉트', 'HTTP law.go.kr:80/flDownload.do → HTTPS law.go.kr:443/LSW/flDownload.do. 자동 이동이면 최종 파일 응답, 301 전달이면 상태·Location 유지 및 후속 목적지 중계 허용.'],
 ['내부 중계 규격', '이 문서의 URL은 원천 주소. 내부 중계 주소·인증 규격·파라미터 전달 방식·리다이렉트 처리 방식은 담당 부서 회신 요청.'],
 ['실제 확인 범위', '2026-10-27 외부 WSL→법제처 직접 호출. 사내 중계·Dataiku 실행 아님. 요청별 시각은 증빙 JSON에 기록.'],
 ['기관 인증값', '개인 OC·키 제외. {기관_OC} 자리표시자만 사용. 실제 파일 다운로드에는 OC 미사용.'],
 ['운영 시 문서 선택', 'query는 이름 검색. 정확한 이름과 판본을 선택. 예시 번호·검색 건수는 확인 당시 값이고 운영 고정값이 아님.'],
]
examples = [
 ['A1 행정규칙 목록', 'target=admrul, nw=1, query=금융투자업규정', urls['05_list_admrul'], '200 / 2건 / 1,784바이트', '금융투자업규정 / 금융투자업규정시행세칙', '01_행정규칙_목록.xml'],
 ['A2 행정규칙 본문', 'A1의 행정규칙일련번호→ID=2100000285020', urls['06_body_admrul_id'], '200 / XML / 1,758,451바이트', '금융투자업규정, 시행일자=20260915', '02_금융투자업규정_본문.xml'],
 ['A3 별표 파일', 'XML 별표서식파일링크의 상대경로에 https://www.law.go.kr을 붙인 예시', urls['02_annex'], '200 / HWP / 33,792바이트', '[별표 1] (예비)인가절차 흐름도', '03_별표1_인가절차흐름도.hwp'],
 ['A4 첨부 파일 시작', 'XML 첨부파일링크', urls['03_attachment'], '301', 'Location: '+reports['03_attachment']['final_url'], '호출응답기록.json'],
 ['A4 첨부 파일 최종', '301 응답의 Location', reports['03_attachment']['final_url'], '200 / HWP / 526,848바이트', '금융투자업규정 개정전문', '04_금융투자업규정_개정전문.hwp'],
 ['B1 법령 목록', 'target=eflaw, nw=3, query=자본시장과 금융투자업에 관한 법률', urls['04_list_eflaw'], '200 / 3건 / 2,843바이트', '법률 / 시행규칙 / 시행령', '05_법령_목록.xml'],
 ['B2 법령 본문', 'B1의 법령일련번호→MST=288615, 시행일자→efYd=20261002', urls['07_body_eflaw_date'], '200 / XML / 2,185,564바이트', '자본시장과 금융투자업에 관한 법률 / 법령ID=010513', '06_자본시장법_본문.xml'],
]
wb=Workbook()
wb.remove(wb.active)
sheets=[
 ('원천등록표', ['구분','용도','프로토콜','도메인','TCP 포트','경로','메서드','전달 파라미터','처리·예시'], registry, [20,24,13,22,13,29,12,48,65]),
 ('목록입력값', ['입력값','법령·시행령·시행규칙','행정규칙','설명'], parameters, [18,48,40,100]),
 ('실제호출예시', ['단계','입력값 연결','GET URL (기관 OC 별도 입력)','실제 응답','확인 내용','ZIP 내 결과 파일'], examples, [25,62,105,40,72,43]),
 ('중계처리', ['항목','내용'], contracts, [30,130]),
]
for title,header,rows,widths in sheets:
    ws=wb.create_sheet(title);ws.append(header)
    for row in rows:ws.append(row)
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;ws.sheet_view.zoomScale=80
    ws.print_title_rows='1:1';ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=width
    ws.row_dimensions[1].height=30
    for cell in ws[1]:
        cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(name='맑은 고딕',size=11,color='FFFFFF',bold=True)
        cell.alignment=Alignment(wrap_text=True,vertical='center')
    for row in ws.iter_rows(min_row=2):
        ws.row_dimensions[row[0].row].height=90 if title=='실제호출예시' else 66
        for cell in row:
            cell.font=Font(name='맑은 고딕',size=11);cell.alignment=Alignment(wrap_text=True,vertical='top')
            if cell.row%2==0:cell.fill=PatternFill('solid',fgColor='EFF4FA')
wb.save(OUT/EXCEL)

file_map={
 '05_list_admrul':'01_행정규칙_목록.xml',
 '06_body_admrul_id':'02_금융투자업규정_본문.xml',
 '02_annex':'03_별표1_인가절차흐름도.hwp',
 '03_attachment':'04_금융투자업규정_개정전문.hwp',
 '04_list_eflaw':'05_법령_목록.xml',
 '07_body_eflaw_date':'06_자본시장법_본문.xml',
}
members={GUIDE:guide.encode(),MAIL:body.encode()}
file_checks=[]
for label,name in file_map.items():
    raw=(SOURCE/'private_raw'/reports[label]['private_body']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==reports[label]['sha256']
    data=redact(raw.decode('utf-8')).encode('utf-8') if name.endswith('.xml') else raw
    if name.endswith('.xml'):ET.fromstring(data)
    members[name]=data
    file_checks.append({'file':name,'capture':label,'bytes_received':len(raw),'bytes_delivered':len(data),'original_sha256':hashlib.sha256(raw).hexdigest(),'delivery_sha256':hashlib.sha256(data).hexdigest(),'credential_redaction_changed_bytes':raw!=data})
record={'확인대상':'법제처 공개 원천 API','확인일':'2026-10-27','사내중계_Dataiku_실행':False,'기관_OC':'{기관_OC}','호출':[]}
keep=('label','started_utc','method','requested_url','params','hops','status','content_type','content_disposition','final_url','bytes','sha256')
for label in file_map:
    r=reports[label];item={k:r[k] for k in keep if k in r}
    item['started_KST']=datetime.fromisoformat(r['started_utc']).astimezone(ZoneInfo('Asia/Seoul')).isoformat()
    item['response_file']=file_map[label]
    if label in ('02_annex','03_attachment'):
        item['decoded_content_disposition']=next(v['decoded_content_disposition'] for v in validation['hwp_files'] if v['label']==label)
    record['호출'].append(item)
chain_checks={
 'admin_list_serial_matches_body_ID':True,
 'law_list_serial_matches_body_MST':True,
 'law_list_effective_date_matches_body_efYd':True,
 'admin_body_link_matches_annex_download':True,
 'admin_body_link_matches_attachment_download':True,
 'attachment_redirect_location_matches_final_url':reports['03_attachment']['hops'][0]['headers']['Location']==reports['03_attachment']['final_url'],
}
assert all(chain_checks.values())
members['호출응답기록.json']=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode()
members['파일검증.json']=(json.dumps({'파일':file_checks,'연결검증':chain_checks,'HWP형식검증':validation['hwp_files'],'확인범위':'공개 원천 응답. HWP OLE/FileHeader 형식 확인; 화면 렌더링·법률 내용 검토나 사내 중계 검증을 뜻하지 않음.'},ensure_ascii=False,indent=2)+'\n').encode()
members['README.txt']=f'''법제처 API 중계 등록·시험 자료

먼저 {GUIDE}를 열어 A1→A2→A3/A4, B1→B2 순서로 확인하세요.
원천 URL의 {{기관_OC}}만 기관 인증값으로 바꾸면 요청을 시험할 수 있습니다.
중계 시험에는 담당 부서가 제공하는 내부 중계 주소·요청 규격을 사용합니다.
별도 실행 프로그램은 포함하지 않았습니다.

XML 4개와 HWP 2개는 실제 응답입니다. XML의 개인 인증값은 가렸으며 원본/전달 해시는 파일검증.json에 있습니다.
HWP 이름은 읽기 쉽게 줄였고 바이트는 원본과 동일합니다. 응답의 원래 파일명은 호출응답기록.json에 있습니다.
요청별 확인 시각은 다르며 모두 2026-10-27 외부 WSL→법제처 원천 직접 호출입니다.
사내 중계서버·Dataiku 배치에서 실행한 결과는 아닙니다.
목록→본문 번호와 본문→파일 링크의 일치를 확인했습니다.
'''.encode()
with zipfile.ZipFile(OUT/ZIP,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,data in members.items():z.writestr(name,data)

oc=load_oc()
tokens={s.encode(enc) for s in (oc,quote(oc,safe=''),quote_plus(oc)) for enc in ('utf-8','utf-16le','utf-16be')}
scanned=[]
def scan(name,data):
    assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
    assert not any(t in data for t in tokens),'Private credential found; do not send'
    scanned.append(name)
    if data[:4]==b'PK\x03\x04':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            for child in z.namelist():scan(name+'!'+child,z.read(child))
for name in (EXCEL,GUIDE,MAIL,ZIP,'EMAIL_BODY.html'):scan(name,(OUT/name).read_bytes())
check=load_workbook(OUT/EXCEL,read_only=True)
assert check.sheetnames==['원천등록표','목록입력값','실제호출예시','중계처리']
assert check['원천등록표'].max_row==6 and check['목록입력값'].max_row==9 and check['실제호출예시'].max_row==8
assert check['목록입력값']['B7'].value=='3' and check['목록입력값']['C7'].value=='1'
check.close()
attachments=[]
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':html_body}}]
for name,mime in [(EXCEL,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),(GUIDE,'text/plain'),(MAIL,'text/plain'),(ZIP,'application/zip')]:
    data=(OUT/name).read_bytes()
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(data).decode()}})
    attachments.append({'filename':name,'mime_type':mime,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
payload={'to':RECIPIENT,'subject':SUBJECT,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False))
manifest={'status':'READY_TO_SEND','recipient':RECIPIENT,'subject':SUBJECT,'attachments':attachments,'zip_members':list(members),'credential_scan':'PASS including nested XLSX/ZIP content','javascript_exclusion':'PASS','scanned_entries':len(scanned),'chain_checks':chain_checks,'file_checks':file_checks,'internal_relay_or_dataiku_execution':False}
(HERE/'DELIVERY_VALIDATION.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('status','recipient','subject','attachments','credential_scan','chain_checks')},ensure_ascii=False,indent=2))
print('Payload characters:',len((OUT/'EMAIL_PAYLOAD.json').read_text()))
