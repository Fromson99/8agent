"""Build the user-requested complete parameter and LSW registration handoff.

No network calls. Credential-bearing output remains in ignored private_delivery.
"""
import ast
import base64
from collections import Counter
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / 'private_delivery'
SOURCE = ROOT / '07_DOCS/REFERENCE/REPORTS/EXTERNAL_DOCUMENT_COLLECTION_REQUEST_20261023/DOCUMENT_INVENTORY.json'
RELAY = 'https://45.101.64.86:8443/law/DRF'
ORIGIN = 'http://www.law.go.kr/DRF/'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def norm(value):
    return unicodedata.normalize('NFKC', value.replace('ㆍ', '·')).replace('\u119e', '·').replace(' ', '')


def write(name, value):
    path = OUT / name
    path.write_text(value, encoding='utf-8')
    return path


def request(endpoint, target, params, oc):
    query = {'OC': oc, 'type': 'XML', **params}
    origin_query = {'target': target, **query}
    return {
        'method': 'GET',
        'origin_url': ORIGIN + endpoint,
        'origin_params': origin_query,
        'origin_full_url': ORIGIN + endpoint + '?' + urlencode(origin_query),
        'relay_url': RELAY,
        'headers': {'target_url': ORIGIN + endpoint + '?target=' + target, 'Accept': 'application/xml'},
        'relay_params': query,
        'relay_full_url': RELAY + '?' + urlencode(query),
    }


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True, mode=0o700)
    values = [line.split('=', 1)[1].strip() for line in (ROOT / '.env').read_text().splitlines() if line.startswith('LAW_OC=')]
    assert len(values) == 1, 'Expected one local LAW_OC setting'
    raw = values[0]
    oc = ast.literal_eval(raw) if raw[:1] in ('"', "'") else raw
    assert isinstance(oc, str) and oc and not any(c in oc for c in '\r\n'), 'Invalid OC setting'
    rows = [r for r in json.loads(SOURCE.read_text()) if r['group'] in ('A', 'B')]
    assert Counter(r['group'] for r in rows) == {'A': 37, 'B': 12}
    xml_files = sorted((ROOT / '01_DATA/RAW/external').glob('*/law/*/*.xml'))
    targets, assets, bindings = [], [], []
    for row in rows:
        candidates = [p for p in xml_files if norm(p.parent.name) == norm(row['name'])]
        assert candidates, 'Missing source XML for ' + row['id']
        p = candidates[0]
        tree = ET.parse(p)
        target = 'eflaw' if row['group'] == 'A' else 'admrul'
        name_tag = '법령명_한글' if row['group'] == 'A' else '행정규칙명'
        actual_name = tree.findtext('.//' + name_tag)
        assert actual_name and norm(actual_name) == norm(row['name']), 'Source title mismatch: ' + row['id']
        effective = tree.findtext('.//시행일자') or ''
        if row['group'] == 'A':
            document_id = tree.findtext('.//법령ID')
            assert document_id
            body_params = {'ID': document_id}
            binding = {'MST': {'from': 'selected_list_row', 'field': '법령일련번호'}, 'efYd': {'from': 'selected_list_row', 'field': '시행일자', 'format': 'YYYYMMDD'}}
        else:
            document_id = tree.findtext('.//행정규칙ID') or ''
            body_params = {'LM': actual_name}
            binding = {'ID': {'from': 'selected_list_row', 'field': '행정규칙일련번호'}}
        list_req = request('lawSearch.do', target, {'search': '1', 'query': actual_name, 'nw': '2,3' if target == 'eflaw' else '1', 'display': '100', 'page': '1'}, oc)
        body_req = request('lawService.do', target, body_params, oc)
        t = {'management_id': row['id'], 'name': actual_name, 'group': row['group'], 'document_id_from_archived_xml': document_id,
             'list_first_page': list_req, 'body_by_stable_id_or_exact_name': body_req,
             'production_version_body': {'method': 'GET', 'relay_url': RELAY,
                'headers': body_req['headers'], 'fixed_params': {'OC': oc, 'type': 'XML'},
                'response_bindings': binding, 'omit_params': ['ID', 'JO'] if target == 'eflaw' else ['LM']},
             'pagination': {'initial_page': 1, 'increment': 1, 'display': 100, 'total_count_field': 'totalCnt', 'stop': 'all result pages consumed'},
             'archived_xml_effective_date': effective}
        targets.append(t)
        for element in tree.iter():
            link = (element.text or '').strip()
            if '파일링크' not in element.tag or not link:
                continue
            parsed = urlsplit(link)
            assert not parsed.scheme or parsed.scheme in ('http', 'https')
            full = urljoin('https://www.law.go.kr', link)
            u = urlsplit(full)
            assert u.hostname in ('www.law.go.kr', 'law.go.kr') and u.path in ('/LSW/flDownload.do', '/flDownload.do')
            qs = parse_qs(u.query)
            assert set(qs) == {'flSeq'} and len(qs['flSeq']) == 1 and qs['flSeq'][0].isdigit()
            kind = 'PDF' if 'PDF' in element.tag else '이미지' if '이미지' in element.tag else '원천 파일(실제 형식 유지)'
            assets.append({'management_id': row['id'], 'document': actual_name, 'archived_effective_date': effective,
                          'xml_field': element.tag, 'format_hint': kind, 'raw_xml_url': link, 'resolved_url': full,
                          'flSeq': qs['flSeq'][0], 'source_path': str(p.relative_to(ROOT))})
        bindings.append({'management_id': row['id'], 'xml': str(p.relative_to(ROOT)), 'sha256': sha(p), 'effective_date': effective})
        del tree

    routes = Counter((urlsplit(a['resolved_url']).scheme, urlsplit(a['resolved_url']).netloc, urlsplit(a['resolved_url']).path) for a in assets)
    unique_urls = set(a['resolved_url'] for a in assets)
    examples = []
    for route in routes:
        for kind in ('원천 파일(실제 형식 유지)', 'PDF', '이미지'):
            item = next((a for a in assets if (urlsplit(a['resolved_url']).scheme, urlsplit(a['resolved_url']).netloc, urlsplit(a['resolved_url']).path) == route and a['format_hint'] == kind), None)
            if item:
                examples.append(item)
    lsw = '''법제처 파일 다운로드 추가 등록 요청 — 2026-10-27 R2

업무명: 법령·행정규칙 별표/서식/첨부 원본 수집
사용 시스템: Dataiku 일일 배치가 호출하는 GENOS 수집·구조화 코드서빙
방향: GENOS → 기존 사내 API 중계 → 법제처 파일 서버 → GENOS 응답
기존 DRF 연결을 사용하는 전체 수집에 아래 파일 다운로드 경로를 추가 등록 요청합니다.

등록 대상 1
  프로토콜/포트: HTTPS / TCP 443
  원천 도메인: www.law.go.kr
  원천 경로: /LSW/flDownload.do
  HTTP 메서드: GET
  필수 쿼리: flSeq (파일마다 달라지는 숫자형 파일 식별자)
  요청 본문: 없음
  근거: 보관 XML의 /LSW/flDownload.do 상대링크를 기존 파일 수집 기준 HTTPS 원천에 결합.

등록 대상 2 — 보관 XML에 실제 포함된 별도 표기
  프로토콜/포트: HTTP / TCP 80
  원천 도메인: law.go.kr (www 없음)
  원천 경로: /flDownload.do (LSW 접두 경로 없음)
  HTTP 메서드: GET
  필수 쿼리: flSeq
  요청 본문: 없음
  근거: 행정규칙 XML의 첨부파일링크에 이 절대 URL이 실제 포함됨.
  URL을 임의로 www/LSW 주소로 바꾸지 않고 반환 링크대로 전달할 수 있도록 요청.

중계 개발·등록에 필요한 계약
  - flSeq는 예시 번호 한 개로 제한하지 않고, 수집 대상 49종 본문이 반환하는 파일별 값 전달.
  - GET 요청, 원천 URL과 쿼리 전달. 기존 target_url 헤더 전달 구조를 파일 다운로드에도 지원 요청.
  - 신규 내부 중계 경로와 서비스 ID는 등록 담당자가 부여하는 값이다. 현재 값으로 만들어 적지 않음.
  - 요청 헤더 Accept: */*. 파일 URL 자체에는 OC/Cookie가 없으며, 별도 OC/Cookie를 임의로 덧붙이지 않음.
  - 응답 HWP/HWPX/PDF/이미지/기타 원천 파일을 바이너리 그대로 전달. XML/JSON/HTML로 강제 변환하지 않음.
  - 원천 HTTP 상태, Content-Type, Content-Disposition(파일명), Content-Length(있을 때)를 보존.
  - 스트리밍 전송 지원 요청. 원천 오류 HTML·4xx/5xx는 성공 파일로 바꾸지 않음.
  - 리다이렉트는 상태·Location을 전달하고 승인 범위 내 목적지만 처리. 미확보 호스트를 미리 추가하지 않음.
  - 파일 크기·속도 제한의 새 수치는 근거 없이 정하지 않음. 중계 제공 한도를 등록 결과에 기재.

수집 규모·이용 계획
  법령 37종 + 행정규칙 12종. 최초 전체 수집 후 매일 06:00 KST 변경 확인 계획.
  08:30 결과 요약, 일요일 18:00 전체 대조는 기존 요청 설정이며 중계 호출 증설 수치가 아님.
  파일은 각 문서 본문에서 받은 링크로 순차 수집. 같은 파일 URL/해시는 중복 저장하지 않음.
  실제 일일 변경량·최대 파일 크기는 현재 확보된 메타데이터만으로 확정하지 않음.

담당자가 등록할 내부 인프라 값
  중계 출구 IP/NAT, 목적지 도메인에 대응하는 방화벽 정책 IP, 새 중계 경로·서비스 ID,
  사내 신청서의 조직/시스템 코드와 정책 유효기간은 내부 등록 담당자의 관리값이다.
  기존 DRF 등록의 동일 호출 시스템/출발지 정책을 재사용하여 위 목적지 경로를 추가 요청한다.
  우리 측 추가 OC·파일 번호 신청이 필요한 구조가 아니며 실제 파일 번호는 XML에서 받는다.
  내부 원천 인증 요구가 추가되면 담당자의 등록 규격으로 처리한다.

실제 보관 XML에서 추출한 URL 예시 (현행 판본 고정값이 아닌 등록용 사례)
'''
    for a in examples:
        lsw += f"  {a['document']} / {a['format_hint']} / XML 시행일 {a['archived_effective_date']}\n  {a['resolved_url']}\n"
    lsw += f'\n첨부 CSV: 문서별 파일 링크 {len(assets):,}행, 고유 URL {len(unique_urls):,}개. 전체 49종 XML에서 추출.\n'
    lsw += '보관판본 링크는 등록 경로의 근거이며, 정기 수집에서는 새 본문이 반환한 링크로 갱신한다.\n'
    lsw_path = write('03_LSW_추가등록_요청서_R2.txt', lsw)

    instructions = '''전체 수집 요청값 — 2026-10-27 R2

이 자료는 연결 재확인용 네 건 샘플을 대신하는 법제처 전체 수집 요청값이다.
담당자가 안내한 기존 DRF 연결을 사용하며 별도 연결 진단·테스트 실행을 요구하지 않는다.
구성: 법령 37종·행정규칙 12종의 목록/본문 요청값, 실제 OC, LSW 추가 등록 명세와 실제 파일 URL 목록.

기존 중계: https://45.101.64.86:8443/law/DRF
원천 목록: http://www.law.go.kr/DRF/lawSearch.do
원천 본문: http://www.law.go.kr/DRF/lawService.do
요청: GET. target은 target_url 헤더의 원천 URL에, OC/type와 나머지 조회값은 중계 GET 쿼리에 전달.
문서별 인코딩된 전체 URL·헤더·파라미터는 JSON과 Excel에 모두 입력했다.
실제 OC는 기존 로컬 설정에서 가져와 이 전달 묶음에 포함했다. 관련 업무 담당자에게만 전달한다.

수집 흐름
  1. 전체 49종의 명칭별 목록을 page=1부터 시작해 totalCnt에 맞춰 끝까지 조회한다.
  2. 정확한 문서명/ID로 응답을 선택한다. 시행령·시행규칙을 부분일치로 혼합하지 않는다.
  3. 법령은 nw=2,3(시행예정·현행), 행정규칙은 nw=1(현행).
  4. 법령 판본 본문은 목록의 법령일련번호→MST, 시행일자→efYd(YYYYMMDD)로 매핑한다.
     이 모드에서는 ID와 JO를 넣지 않아 해당 판본의 전체 조문을 받는다.
  5. 행정규칙 판본 본문은 목록의 행정규칙일련번호→ID로 매핑한다. LM과 함께 넣지 않는다.
  6. 본문 XML의 실제 파일 링크를 LSW 중계로 순차 수집한다. 파일·본문의 판본을 연결해 보관한다.

초기 본문 조회값도 모든 문서에 채웠다: 법령은 보관 XML에서 확인한 법령ID, 행정규칙은 정확한 LM 명칭.
정기 수집에서는 위 응답 연계 규칙으로 판본을 고정한다. MST/efYd/ID/flSeq/page는 실행 응답에 따라
바뀌는 값이므로 과거 숫자를 현행 값으로 하드코딩하지 않는다. 이는 미입력 항목이 아니라 자동 연결 규칙이다.

일정은 기존 요청 설정을 유지한다: 매일 06:00 KST 수집, 08:30 결과 요약, 일요일 18:00 전체 대조.
과거 연혁 전체 소급수집은 기본 제외. 수집 자료는 Dataiku 관리 폴더에 원문·메타데이터로 보존하고
기존 구조화·Oracle 적재 흐름에 연결한다. API 등록과 실제 전체 수집/저장/적재 완료는 별도다.

LSW 신규 등록 내용은 03 문서에 모두 정리했다. www.law.go.kr/LSW 경로 외에
보관 XML에서 발견한 http://law.go.kr/flDownload.do 경로도 포함했다.
중계 내부 경로·서비스 ID·방화벽 IP는 담당자 등록 결과로 부여된다.

파일 설명
  01: 이 안내
  02: 실제 OC를 포함한 49종 전체 요청 JSON (명세 자료이며 실행 프로그램 아님)
  03: LSW 추가 등록 요청서
  04: 보관 XML에서 추출한 파일 URL·flSeq·문서/판본 연결 목록 CSV
  05: Excel 전체 값 표 (49종 목록/본문/판본 연결/LSW 등록/실제 URL 예시)

공식 파라미터 근거
https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide
https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide
https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide
https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide
'''
    guide_path = write('01_전체수집_전달안내_R2.txt', instructions)
    config = {'schema': 'law-relay-complete-handoff-v2', 'date': '2026-10-27', 'purpose': 'full_collection_request_values_not_connectivity_probe',
        'credential': {'LAW_OC': oc, 'source': 'existing user-authorized local setting'},
        'relay_endpoint': RELAY, 'target_count': 49, 'schedule': {'timezone': 'Asia/Seoul', 'daily_start': '06:00', 'daily_status': '08:30', 'weekly_reconcile': 'Sunday 18:00', 'status': 'requested_schedule_not_installed'},
        'targets': targets,
        'attachments': {'method': 'GET', 'source': 'body XML actual links', 'new_relay_path': {'assigned_by': 'relay registration owner'},
            'origin_routes': [{'scheme': s, 'host': h, 'port': 443 if s == 'https' else 80, 'path': p, 'query_field': 'flSeq', 'archived_rows': n} for (s,h,p),n in routes.items()],
            'archived_link_rows': len(assets), 'archived_unique_urls': len(unique_urls), 'archive_role': 'registration evidence; refresh links from collected body'}}
    json_path = write('02_전체49종_실제요청값_R2.json', json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    csv_path = OUT / '04_LSW_실제파일URL_전체목록_R2.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(assets[0]))
        w.writeheader()
        w.writerows(assets)

    wb = Workbook()
    ws = wb.active
    ws.title = '공통값'
    for row in [('항목','값'),('대상','법령 37종 + 행정규칙 12종'),('OC',oc),('중계 GET',RELAY),('일일 시작','06:00 Asia/Seoul'),('상태 요약','08:30'),('전체 대조','Sunday 18:00'),('LSW 링크 수',len(assets)),('고유 URL',len(unique_urls)),('동적 값','판본·페이지·파일번호는 응답 필드에서 자동 연결'),('신규 중계 경로','등록 담당자 부여')]: ws.append(row)
    a = wb.create_sheet('49종_목록요청')
    a.append(['관리번호','문서명','target','OC','type','search','query','nw','display','page','target_url 헤더','중계 GET 전체 URL','원천 전체 URL'])
    b = wb.create_sheet('49종_본문요청')
    b.append(['관리번호','문서명','target','OC','type','ID 또는 LM','실제값','target_url 헤더','중계 GET 전체 URL','원천 전체 URL','판본 수집 연결 규칙'])
    for t in targets:
        r = t['list_first_page']; q = r['origin_params']
        a.append([t['management_id'],t['name'],q['target'],oc,q['type'],q['search'],q['query'],q['nw'],q['display'],q['page'],r['headers']['target_url'],r['relay_full_url'],r['origin_full_url']])
        r = t['body_by_stable_id_or_exact_name']; q = r['origin_params']; key = 'ID' if t['group']=='A' else 'LM'
        rule = '목록 법령일련번호→MST, 시행일자→efYd; ID/JO 생략' if t['group']=='A' else '목록 행정규칙일련번호→ID; LM 생략'
        b.append([t['management_id'],t['name'],q['target'],oc,q['type'],key,q[key],r['headers']['target_url'],r['relay_full_url'],r['origin_full_url'],rule])
    s = wb.create_sheet('LSW_등록값'); s.append(['프로토콜','도메인','TCP포트','경로','메서드','쿼리','보관XML_행수'])
    for (scheme,host,path),count in routes.items():s.append([scheme,host,443 if scheme=='https' else 80,path,'GET','flSeq',count])
    s = wb.create_sheet('LSW_실제URL예시'); s.append(['관리번호','문서명','보관판본시행일','XML필드','파일분류','실제 URL','flSeq'])
    for a in examples:s.append([a['management_id'],a['document'],a['archived_effective_date'],a['xml_field'],a['format_hint'],a['resolved_url'],a['flSeq']])
    for s in wb:
        s.freeze_panes = 'A2'; s.auto_filter.ref = s.dimensions
        for cell in s[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17365D')
        for column in s.columns:
            letter=column[0].column_letter
            s.column_dimensions[letter].width=min(75,max(16,max(len(str(c.value or '')) for c in column)+2))
        for row in s.iter_rows(min_row=2):
            for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    xlsx_path = OUT/'05_전체49종_실제요청값_LSW등록_R2.xlsx'; wb.save(xlsx_path)
    files=[guide_path,json_path,lsw_path,csv_path,xlsx_path]
    # Verify all document requests and concrete parameters without printing secrets.
    assert len(targets)==49 and len({t['management_id'] for t in targets})==49
    for t in targets:
        for key in ('list_first_page','body_by_stable_id_or_exact_name'):
            r=t[key]
            assert r['origin_params']['OC']==oc
            assert not any(x in r['relay_full_url'] for x in ('{','}','<','>'))
            rq={k:v[0] for k,v in parse_qs(urlsplit(r['relay_full_url']).query).items()}
            oq={k:v[0] for k,v in parse_qs(urlsplit(r['headers']['target_url']).query).items()}
            assert not rq.keys() & oq.keys() and {**rq,**oq}==r['origin_params']
    check=load_workbook(xlsx_path,read_only=True,data_only=False)
    assert check['49종_목록요청'].max_row==50 and check['49종_본문요청'].max_row==50
    assert check['공통값']['B3'].value==oc
    check.close()
    assert len(list(csv.DictReader(csv_path.open(encoding='utf-8-sig'))))==len(assets)
    assert len(routes)==2
    zip_path=OUT/'법제처_전체49종_실제값_LSW추가등록_20261027_R2.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:
            assert f.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(f,f.name)
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None and set(z.namelist())=={f.name for f in files}
        for f in files:assert z.read(f.name)==f.read_bytes()
    body=f'''<html><body>
<p>법제처 <b>전체 49종(법령 37종·행정규칙 12종)의 실제 요청값과 LSW 추가 등록 자료</b>입니다. 앞선 4건 확인용 R1 및 10월23일 URL/설정부록의 요청값은 이번 R2로 대체해 사용해 주세요.</p>
<p>기존 DRF 연결이 제공된다는 안내를 기준으로 <b>전체 수집에 사용할 값</b>을 정리했습니다. 별도 연결 진단 요청은 포함하지 않았습니다. 보관된 실제 OC, 중계 주소, 원천 HTTP 주소, 49종 문서별 GET 쿼리·target_url 헤더·인코딩된 전체 URL을 JSON과 Excel에 입력했습니다. 실제 OC가 포함된 업무 전달 자료입니다.</p>
<p><b>LSW 등록에는 다음 두 경로를 넣었습니다.</b></p>
<ul><li>HTTPS / TCP 443 / www.law.go.kr /LSW/flDownload.do / GET / flSeq</li>
<li>HTTP / TCP 80 / law.go.kr /flDownload.do / GET / flSeq — 행정규칙 원문이 실제 반환한 별도 주소</li></ul>
<p>등록 요청서에 사용 목적·호출 시스템·수집 주기·실제 파일 URL·쿼리 전달·바이너리 응답·필요 응답 헤더·오류/리다이렉트 처리를 추가했습니다. 보관 XML 49종에서 추출한 <b>{len(assets):,}개 링크 행, 고유 URL {len(unique_urls):,}개</b>도 CSV로 동봉했습니다. 이 링크들은 보관판본의 등록 근거이며 현행 파일로 고정하지 않습니다.</p>
<p>개정 때 달라지는 MST/efYd/행정규칙 ID/flSeq와 페이지는 응답에서 자동으로 가져오는 규칙을 명시했습니다. 신규 중계 경로·서비스 ID·방화벽 출구 IP는 중계 담당자가 기존 DRF 등록 정보를 기준으로 부여하는 내부 값으로 구분했습니다.</p>
<p>첨부: 전체 ZIP(안내·JSON·LSW 요청서·전체 파일 URL CSV·Excel), Excel 별도, LSW 요청서 별도. 실행 프로그램이 아닌 수집/등록 명세 자료입니다.</p>
</body></html>'''
    write('EMAIL_BODY.html',body)
    attachments=[zip_path,xlsx_path,lsw_path]
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    attachment_meta=[]
    for f in attachments:
        mime={'.zip':'application/zip','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.txt':'text/plain'}[f.suffix]
        part={'mime_type':mime,'filename':f.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(f.read_bytes()).decode().rstrip('=')}}
        if f.suffix=='.txt':part['charset']='UTF-8'
        parts.append(part)
        attachment_meta.append({'name':f.name,'bytes':f.stat().st_size,'sha256':sha(f),'mime_type':mime})
    payload={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[법제처 수집] 전체49종 실제 요청값·OC 포함 + LSW 추가 등록 자료 R2','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    write('EMAIL_PAYLOAD.json',json.dumps(payload,ensure_ascii=False))
    report={'status':'READY','scope':'49 full request specifications and LSW registration; no runtime changes',
        'counts':{'laws':37,'administrative_rules':12,'concrete_request_pairs':49,'asset_rows':len(assets),'unique_asset_urls':len(unique_urls),'origin_file_routes':len(routes)},
        'credentials_in_private_delivery':True,'credential_source':'.env LAW_OC; value not logged',
        'checks':['49 source XML names match requested scope','all 98 origin/relay query mappings equal','OC prefilled in JSON and XLSX','49 list and 49 body rows in workbook','all asset URLs traced to XML and have numeric flSeq','ZIP membership and bytes match; no JS files'],
        'attachments':attachment_meta,'source_inventory_sha256':sha(SOURCE),'source_xml_bindings':bindings,
        'not_performed':['connection tests','law API calls','GENOS access','runtime deployment','actual full collection']}
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'READY','to':payload['to'],'counts':report['counts'],'attachments':attachment_meta},ensure_ascii=False))


if __name__=='__main__':
    main()
