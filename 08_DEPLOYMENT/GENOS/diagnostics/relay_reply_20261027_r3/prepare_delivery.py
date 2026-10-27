"""Prepare a concise forwardable response using the verified R2 request values."""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import zipfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'relay_request_20261027_r2'
OUT = HERE / 'private_delivery'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True, mode=0o700)
    src = PARENT / 'private_delivery'
    previous = json.loads((PARENT / 'EMAIL_VERIFIED.json').read_text())
    xlsx_src = src / '05_전체49종_실제요청값_LSW등록_R2.xlsx'
    assert sha(xlsx_src) == next(x['sha256'] for x in previous['attachments'] if x['name'] == xlsx_src.name)
    config = json.loads((src / '02_전체49종_실제요청값_R2.json').read_text())
    assert len(config['targets']) == 49

    plain = '''안녕하세요. 안내 감사합니다.

법제처 API를 통해 법령 37종과 행정규칙 12종의 본문 및 별표·서식 파일을 수집하려고 합니다.
말씀해 주신 기존 DRF 경로를 이용하고, 파일 다운로드용 LSW 경로는 추가 등록을 요청드립니다.

1. 기존 DRF 경로 — 조회 파라미터 전달

원천 주소
  목록: http://www.law.go.kr/DRF/lawSearch.do
  본문: http://www.law.go.kr/DRF/lawService.do
공통: GET / type=XML / OC는 첨부 Excel의 「공통값」에 실제 값 기재

법령 목록: target=eflaw, search=1, query=문서명, nw=2,3, display=100, page=1부터 순회
법령 본문: target=eflaw, MST=목록의 법령일련번호, efYd=해당 판본 시행일
행정규칙 목록: target=admrul, search=1, query=문서명, nw=1, display=100, page=1부터 순회
행정규칙 본문: target=admrul, ID=목록의 행정규칙일련번호

49종 전체 문서명·실제 OC·초기 본문 조회값·인코딩된 전체 요청 URL을 첨부 Excel에 넣었습니다.
기존 중계 주소는 https://45.101.64.86:8443/law/DRF 이며,
target_url 헤더에 원천 주소와 target을 넣고 나머지 값은 GET 쿼리로 전달하는 형식입니다.
개정 때 바뀌는 판본 번호·시행일과 페이지는 위 규칙에 따라 목록 응답에서 연결합니다.

2. LSW 추가 등록 — 법제처 파일 다운로드 접속 정보

기본 경로
  도메인: www.law.go.kr
  프로토콜/포트: HTTPS / TCP 443
  경로: /LSW/flDownload.do
  방식/쿼리: GET / flSeq=파일 식별번호
  실제 링크 예: https://www.law.go.kr/LSW/flDownload.do?flSeq=162138219

일부 행정규칙 원문에 포함된 추가 경로
  도메인: law.go.kr
  프로토콜/포트: HTTP / TCP 80
  경로: /flDownload.do
  방식/쿼리: GET / flSeq=파일 식별번호
  실제 링크 예: http://law.go.kr/flDownload.do?flSeq=141869659

DRF 본문에는 조문과 파일 링크가 들어 있고, 위 경로에서 HWP·PDF 등의 실제 파일을 받습니다.
본문에서 반환하는 파일별 flSeq를 전달하고, 응답은 원본 파일 바이트와 파일명·Content-Type을
보존하여 받을 수 있도록 중계 등록을 요청드립니다. 위 번호는 보관 원문의 실제 사례이며
수집 시에는 해당 판본의 본문이 반환한 링크를 사용합니다.

3. 사용 목적 및 추가 등록 요청

호출 시스템: Dataiku 배치가 호출하는 GENOS 수집·구조화 코드서빙
사용 계획: 최초 전체 수집 후 매일 변경 자료 수집
수집 대상: 법령·행정규칙 49종과 연결된 별표·서식·첨부파일

위 도메인·포트·경로를 기준으로 LSW 네트워크·방화벽·파일 응답 중계 작업을 요청드립니다.
방화벽 신청에 고정 목적지 IP가 필수인 경우 필요한 항목을 알려주시기 바랍니다.
현재 전달 자료에는 원천 도메인을 기재했으며 법제처가 확정한 고정 IP는 포함되어 있지 않습니다.
개발요청 등록 양식과 신규 중계 경로는 안내 부탁드립니다.

첨부 Excel에는 전체 요청값과 접속 정보를, 상세 ZIP에는 같은 Excel·JSON 요청값·실제 파일 URL
5,126개 목록·이 회신 문안을 넣었습니다. 이번 R3 자료를 사용해 주세요.
실제 OC가 포함되어 있으므로 관련 업무 담당자에게 전달 부탁드립니다.

감사합니다.
'''
    reply = OUT / '법제처_API_LSW_회신본문_R3.txt'
    reply.write_text(plain, encoding='utf-8')
    # Same words in the mail and copyable TXT; only emphasis is added in HTML.
    paragraphs = plain.strip().split('\n\n')
    pieces = []
    for para in paragraphs:
        escaped = html.escape(para).replace('\n', '<br>')
        if para.startswith(('1. ', '2. ', '3. ')) and '\n' not in para:
            escaped = '<b>' + escaped + '</b>'
        pieces.append('<p style="margin:0 0 12px 0">' + escaped + '</p>')
    body = '<html><body style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.65">' + ''.join(pieces) + '</body></html>'
    (OUT/'EMAIL_BODY.html').write_text(body,encoding='utf-8')

    xlsx = OUT / '법제처_API49종_요청값_LSW접속정보_R3.xlsx'
    wb = load_workbook(xlsx_src)
    common = wb['공통값']
    common.append(['자료 버전','2026-10-27 R3: 회신용 정리. DRF 실제 요청값은 R2와 동일'])
    common.append(['고정 목적지 IP','법제처가 확정한 고정 IP는 미확보. 임의 DNS 값을 고정 IP로 기재하지 않음'])
    sheet = wb['LSW_등록값']
    sheet.append([])
    additions = [
        ['업무','법령·행정규칙의 별표·서식·첨부 원본 수집'],
        ['호출 시스템','Dataiku 배치 → GENOS 수집·구조화 코드서빙 → 사내 중계'],
        ['수집 계획','최초 전체 수집 후 매일 변경 자료 수집'],
        ['파일 식별자','본문 XML이 반환한 flSeq. 고정 예시 번호로 제한하지 않음'],
        ['요청 본문','없음'],
        ['요청 헤더','Accept: */*'],
        ['응답','원본 바이너리; HTTP 상태·Content-Type·Content-Disposition 및 Content-Length(있을 때) 보존'],
        ['인증 자료의 범위','보관 파일 URL에는 flSeq가 포함됨. 별도 인증 불필요를 법제처가 확인한 자료는 아님'],
        ['리다이렉트','상태와 Location 전달; 승인 범위 내 목적지 처리'],
        ['고정 목적지 IP','미확보; 도메인 기준 접속 정보를 제공. IP 필수 신청서이면 보완 항목'],
        ['신규 중계 경로·서비스 ID','등록 담당자가 부여할 값'],
    ]
    for row in additions: sheet.append(row)
    note=wb.create_sheet('회신본문')
    note.append(['내용'])
    for line in plain.splitlines():note.append([line])
    note.column_dimensions['A'].width=110
    for s in (sheet,note,common):
        for row in s:
            for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
    for c in note[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='17365D')
    wb.save(xlsx)
    check=load_workbook(xlsx,read_only=True,data_only=False)
    original=load_workbook(xlsx_src,read_only=True,data_only=False)
    for name in ('49종_목록요청','49종_본문요청'):
        assert list(check[name].values)==list(original[name].values)
    assert check['공통값']['B3'].value==config['credential']['LAW_OC']
    check.close();original.close()

    archive=OUT/'법제처_API_LSW_회신자료_20261027_R3.zip'
    members=[(reply,reply.name),(xlsx,xlsx.name),
        (src/'02_전체49종_실제요청값_R2.json','전체49종_실제요청값.json'),
        (src/'04_LSW_실제파일URL_전체목록_R2.csv','LSW_실제파일URL_전체목록.csv')]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p,name in members:
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(p,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())=={name for _,name in members}
        for p,name in members:assert z.read(name)==p.read_bytes()
    attached=[xlsx,archive,reply]
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    metadata=[]
    for f in attached:
        mime={'.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.zip':'application/zip','.txt':'text/plain'}[f.suffix]
        part={'mime_type':mime,'filename':f.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(f.read_bytes()).decode().rstrip('=')}}
        if f.suffix=='.txt':part['charset']='UTF-8'
        parts.append(part)
        metadata.append({'name':f.name,'mime_type':mime,'bytes':f.stat().st_size,'sha256':sha(f)})
    message={'to':'hyungjininfocz.son@partner.samsung.com','subject':'RE: API중계서버 URL추가 문의 — 법제처 조회 파라미터 및 LSW 추가 등록',
        'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(message,ensure_ascii=False))
    report={'status':'READY','recipient':message['to'],'subject':message['subject'],'attachments':metadata,
        'checks':['49 list and 49 body rows exactly match sent R2 values','actual OC preserved in spreadsheet','reply text and email use identical words','archive member bytes verified; no JavaScript'],
        'scope':'Direct reply wording for DRF and LSW; 49 target values unchanged; fixed destination IP explicitly not supplied',
        'network_calls':0,'runtime_changes':0,'source_email':'1a17a8f1e1893626'}
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'READY','to':message['to'],'attachments':metadata},ensure_ascii=False))


if __name__=='__main__':
    main()
