"""Create a self-contained reply with account credentials omitted everywhere."""
import base64
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote, urlencode
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'relay_request_20261027_r2/private_delivery'
OUT = HERE / 'delivery'
PLACEHOLDER = '{기관_OC}'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def clean_request(request):
    origin = dict(request['origin_params'])
    relay = dict(request['relay_params'])
    origin['OC'] = relay['OC'] = PLACEHOLDER
    return {'method': 'GET', 'origin_url': request['origin_url'], 'origin_params': origin,
            'origin_url_template': request['origin_url'] + '?' + urlencode(origin),
            'relay_url': request['relay_url'], 'headers': dict(request['headers']),
            'relay_params': relay, 'relay_url_template': request['relay_url'] + '?' + urlencode(relay)}


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True)
    source = json.loads((SOURCE / '02_전체49종_실제요청값_R2.json').read_text())
    private_oc = source['credential']['LAW_OC']
    assert private_oc and len(source['targets']) == 49
    targets = []
    for item in source['targets']:
        production = item['production_version_body']
        fixed = dict(production['fixed_params'])
        fixed['OC'] = PLACEHOLDER
        targets.append({'management_id': item['management_id'], 'name': item['name'], 'group': item['group'],
            'list_first_page': clean_request(item['list_first_page']),
            'initial_body': clean_request(item['body_by_stable_id_or_exact_name']),
            'production_version_body': {'method': 'GET', 'relay_url': production['relay_url'],
                'headers': dict(production['headers']), 'fixed_params': fixed,
                'response_bindings': production['response_bindings'], 'omit_params': production['omit_params']},
            'pagination': item['pagination']})
    config = {'document_type': 'law_collection_request_specification', 'date': '2026-10-27',
        'authentication': {'required_parameter': 'OC', 'placeholder': PLACEHOLDER,
            'note': '개인 계정 발급값은 포함하지 않음. 실제 호출 시 사용 권한이 있는 기관 OC를 별도로 설정.',
            'personal_credentials_included': False},
        'scope': {'laws': 37, 'administrative_rules': 12, 'total': 49},
        'targets': targets,
        'files': {'method': 'GET', 'query_parameter': 'flSeq', 'source': '해당 판본 본문 XML의 실제 파일 링크',
            'origin_routes': source['attachments']['origin_routes'],
            'relay_path': '추가 등록 후 담당자가 부여',
            'archived_link_rows': 5126, 'archived_links_role': '등록 참고용 보관판본 사례; 수집 시 새 본문 링크 사용'}}
    json_path = OUT / '법제처_49종_요청명세.json'
    json_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fields = ['management_id','document','archived_effective_date','xml_field','format_hint','raw_xml_url','resolved_url','flSeq']
    with (SOURCE / '04_LSW_실제파일URL_전체목록_R2.csv').open(encoding='utf-8-sig') as f:
        assets = [{k: r[k] for k in fields} for r in csv.DictReader(f)]
    assert len(assets) == 5126
    csv_path = OUT / 'LSW_파일URL_목록.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(assets)

    text = '''안녕하세요. 안내 감사합니다.

법제처 API를 통해 법령 37종과 행정규칙 12종의 본문 및 별표·서식 파일을 수집하려고 합니다.
안내해 주신 DRF 경로의 조회 조건을 전달드리며, 파일 다운로드용 LSW 경로의 추가 등록을 요청드립니다.

1. DRF 조회 주소 및 파라미터

목록 주소: http://www.law.go.kr/DRF/lawSearch.do
본문 주소: http://www.law.go.kr/DRF/lawService.do
공통 요청: GET / type=XML / OC=기관에서 사용할 인증값

법령 목록: target=eflaw, search=1, query=문서명, nw=2,3, display=100, page=1부터 순회
법령 본문: target=eflaw, MST=목록의 법령일련번호, efYd=해당 판본 시행일
행정규칙 목록: target=admrul, search=1, query=문서명, nw=1, display=100, page=1부터 순회
행정규칙 본문: target=admrul, ID=목록의 행정규칙일련번호

첨부 Excel에 49종 전체 문서명, 문서별 조회 파라미터, 초기 본문 조회값, 요청 URL 형식을 기재했습니다.
중계 요청은 GET 방식이며, target_url 헤더에는 원천 주소와 target을 넣고 나머지는 GET 쿼리로 전달합니다.
판본 번호·시행일·페이지·파일 번호는 수집 응답에서 받아 다음 요청에 연결합니다.

인증값 안내: 개인 계정에서 발급받은 OC·API 키·쿠키·토큰은 본문과 첨부에 포함하지 않았습니다.
OC는 필수 파라미터이므로 자료에는 {기관_OC}로 표시했습니다.
실제 호출 시에는 사용 권한이 있는 기관 OC를 별도로 설정해야 합니다.

2. LSW 파일 다운로드 추가 등록 정보

기본 경로
  도메인: www.law.go.kr
  프로토콜·포트: HTTPS / TCP 443
  경로: /LSW/flDownload.do
  요청: GET / flSeq=파일 식별번호
  실제 링크 예: https://www.law.go.kr/LSW/flDownload.do?flSeq=162138219

일부 행정규칙 원문에 포함된 추가 경로
  도메인: law.go.kr
  프로토콜·포트: HTTP / TCP 80
  경로: /flDownload.do
  요청: GET / flSeq=파일 식별번호
  실제 링크 예: http://law.go.kr/flDownload.do?flSeq=141869659

DRF에서 조문과 파일 링크를 받고, 위 다운로드 경로에서 HWP·PDF 등의 원본 파일을 받습니다.
본문이 반환하는 파일별 flSeq를 전달하고, 원본 파일 바이트와 파일명·Content-Type을 보존하여
받을 수 있도록 중계 등록을 요청드립니다. 예시 번호는 보관판본의 사례이며 수집 시에는
해당 판본 본문이 반환한 링크를 사용합니다.

호출 시스템은 Dataiku 배치가 호출하는 GENOS 수집·구조화 코드서빙이며,
최초 전체 수집 후 매일 변경 자료를 수집할 계획입니다.
위 도메인·포트·경로를 기준으로 필요한 네트워크·방화벽·중계 개발을 요청드립니다.
고정 목적지 IP는 현재 자료에 포함하지 않았습니다. 신청 양식에서 IP가 필수라면 필요한 항목을
안내 부탁드립니다. 개발요청 등록 양식과 신규 중계 경로도 함께 안내해 주시면 감사하겠습니다.

3. 첨부파일 설명

① 법제처_API_요청값_접속정보.xlsx
   49종 문서 목록, 목록·본문 조회 파라미터와 URL 형식, 판본 연결 규칙,
   LSW 도메인·포트·경로·파일 응답 요구사항을 정리한 표입니다.
   OC는 실제 값 대신 {기관_OC}로 표시했습니다.

② 법제처_API_상세자료.zip
   위 Excel과 함께 개발용 「법제처_49종_요청명세.json」,
   보관 원문에서 추출한 실제 파일 링크 5,126개를 담은 「LSW_파일URL_목록.csv」,
   이 메일의 문안을 담은 「법제처_API_회신본문.txt」가 들어 있습니다.
   JSON에도 실제 인증값은 없으며, CSV 링크는 등록 참고용 보관판본 사례입니다.

③ 법제처_API_회신본문.txt
   이 메일과 같은 내용을 담은 일반 텍스트 파일입니다. 문안을 복사하거나 신청서에 옮길 때 사용할 수 있습니다.

감사합니다.
'''
    reply = OUT / '법제처_API_회신본문.txt'
    reply.write_text(text, encoding='utf-8')
    body = '<html><body style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.6">'
    for para in text.strip().split('\n\n'):
        para = html.escape(para).replace('\n','<br>')
        if para.startswith(('1. ','2. ','3. ')) and '<br>' not in para: para = '<b>' + para + '</b>'
        body += '<p style="margin:0 0 12px 0">' + para + '</p>'
    body += '</body></html>'
    (OUT/'EMAIL_BODY.html').write_text(body,encoding='utf-8')

    wb = Workbook()
    common = wb.active; common.title='이용안내'
    for row in [('항목','내용'),('대상','법령 37종 + 행정규칙 12종 = 49종'),
        ('인증값','개인 계정 OC·API 키·쿠키·토큰 미포함'),('OC',PLACEHOLDER),
        ('실제 호출','사용 권한이 있는 기관 OC를 별도로 설정'),
        ('수집 계획','최초 전체 수집 후 매일 변경 자료 수집'),
        ('중계 요청','GET / target_url 헤더에 원천 URL 및 target; 나머지 값은 GET 쿼리'),
        ('본문 판본','목록 응답의 식별자·시행일을 연결. 과거 판본 번호 고정 금지'),
        ('파일 링크','CSV는 보관판본 사례. 수집 시 해당 판본 XML의 새 링크 사용'),
        ('고정 목적지 IP','미확보. 신청서에서 IP가 필수라면 보완 필요')]: common.append(row)
    lists=wb.create_sheet('49종_목록조회');lists.append(['관리번호','문서명','target','OC','type','search','query','nw','display','첫페이지','target_url 헤더','중계 URL 형식','원천 URL 형식'])
    bodies=wb.create_sheet('49종_본문조회');bodies.append(['관리번호','문서명','target','OC','type','초기 조회필드','초기 조회값','target_url 헤더','중계 URL 형식','원천 URL 형식','정기수집 판본 연결'])
    for item in targets:
        r=item['list_first_page'];q=r['origin_params']
        lists.append([item['management_id'],item['name'],q['target'],PLACEHOLDER,q['type'],q['search'],q['query'],q['nw'],q['display'],q['page'],r['headers']['target_url'],r['relay_url_template'],r['origin_url_template']])
        r=item['initial_body'];q=r['origin_params'];k='ID' if item['group']=='A' else 'LM'
        rule='목록 법령일련번호→MST, 시행일자→efYd; ID/JO 생략' if item['group']=='A' else '목록 행정규칙일련번호→ID; LM 생략'
        bodies.append([item['management_id'],item['name'],q['target'],PLACEHOLDER,q['type'],k,q[k],r['headers']['target_url'],r['relay_url_template'],r['origin_url_template'],rule])
    lsw=wb.create_sheet('LSW_접속정보');lsw.append(['항목','내용'])
    for row in [('기본 주소','https://www.law.go.kr/LSW/flDownload.do'),('포트','TCP 443'),
        ('추가 원문 주소','http://law.go.kr/flDownload.do'),('추가 포트','TCP 80'),('메서드','GET'),
        ('쿼리','flSeq=해당 본문이 반환한 파일 식별번호'),('요청 본문','없음'),('요청 헤더','Accept: */*'),
        ('응답','원본 파일 바이트·파일명·Content-Type·HTTP 상태 보존'),
        ('인증 참고','보관 파일 링크 쿼리는 flSeq. 별도 인증 불필요를 확정한 자료는 아님'),
        ('신규 중계 경로','등록 담당자가 부여'),('고정 목적지 IP','현재 자료 미포함'),
        ('원본 예시','https://www.law.go.kr/LSW/flDownload.do?flSeq=162138219'),
        ('추가 경로 예시','http://law.go.kr/flDownload.do?flSeq=141869659')]:lsw.append(row)
    for sheet in wb:
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17365D')
        for col in sheet.columns:sheet.column_dimensions[col[0].column_letter].width=min(78,max(16,max(len(str(c.value or '')) for c in col)+2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:cell.alignment=Alignment(wrap_text=True,vertical='top')
    xlsx=OUT/'법제처_API_요청값_접속정보.xlsx';wb.save(xlsx)
    check=load_workbook(xlsx,read_only=True,data_only=False)
    assert check['49종_목록조회'].max_row==50 and check['49종_본문조회'].max_row==50
    assert all(row[3]==PLACEHOLDER for row in list(check['49종_목록조회'].values)[1:])
    check.close()

    members=[xlsx,json_path,csv_path,reply]
    archive=OUT/'법제처_API_상세자료.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in members:
            assert p.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(p,p.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())=={p.name for p in members}
        for p in members:assert z.read(p.name)==p.read_bytes()

    # Inspect every text payload, plus nested XLSX XML inside the ZIP.
    forbidden_values={private_oc,quote(private_oc,safe=''),quote_plus(private_oc)}
    history_terms=('R2','R3','private_delivery','로컬 설정','앞서 보낸','이전 발송','실제 OC가 포함')
    def inspect(raw,name):
        if name.lower().endswith(('.zip','.xlsx')):
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for child in z.namelist():inspect(z.read(child),child)
        else:
            s=raw.decode('utf-8-sig')
            for secret in forbidden_values:assert secret not in s and secret not in unquote(s), 'Credential found in '+name
            if not name.lower().endswith('.xml'):
                assert not any(t in s for t in history_terms), 'History wording in '+name
    for p in [archive,xlsx,reply,json_path,csv_path,OUT/'EMAIL_BODY.html']:inspect(p.read_bytes(),p.name)
    for sheet in wb:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value,str):assert not any(t in cell.value for t in history_terms)
    assert 'credential' not in config

    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    attachments=[]
    for p in [xlsx,archive,reply]:
        mime={'.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.zip':'application/zip','.txt':'text/plain'}[p.suffix]
        part={'mime_type':mime,'filename':p.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode().rstrip('=')}}
        if p.suffix=='.txt':part['charset']='UTF-8'
        parts.append(part);attachments.append({'name':p.name,'mime_type':mime,'bytes':p.stat().st_size,'sha256':sha(p)})
    payload={'to':'hyungjininfocz.son@partner.samsung.com','subject':'RE: API중계서버 URL추가 문의 — 법제처 조회 조건 및 파일 다운로드 등록 요청',
        'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False))
    report={'status':'READY','recipient':payload['to'],'subject':payload['subject'],'attachments':attachments,
        'checks':['49 list and 49 body request rows','OC placeholders throughout JSON and URLs and workbook','known personal OC absent in raw and URL-encoded form','all ZIP members and nested XLSX XML inspected','no historical version references in visible content or filenames','each attachment explained by filename in email','ZIP byte equality and no JavaScript'],
        'personal_credentials_included':False,'source_credential_printed':False,
        'scope':'standalone reply with institution OC placeholder; historical emails left unchanged'}
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'READY','to':payload['to'],'attachments':attachments,'personal_credentials_included':False},ensure_ascii=False))


if __name__=='__main__':main()
