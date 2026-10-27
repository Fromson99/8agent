"""Produce the self-contained Dataiku batch request email with two attachments."""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote
import zipfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DIAGNOSTICS=ROOT/'08_DEPLOYMENT/GENOS/diagnostics'
SOURCE=DIAGNOSTICS/'relay_reply_no_personal_credentials_20261027/delivery'
OUT=HERE/'delivery'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True)
    text='''안녕하세요. 안내 감사합니다.

Dataiku에서 배치를 실행하여 법령 37종과 행정규칙 12종의 본문 및 별표·서식 파일을 수집할 계획입니다.
호출 흐름은 「Dataiku 배치 → API 중계서버 → 법제처」이며, 최초 전체 수집 후 매일 변경 자료를 수집합니다.
DRF 조회 조건을 전달드리며, 파일 다운로드용 LSW 경로의 추가 등록을 요청드립니다.

1. DRF 조회 조건

목록 주소: http://www.law.go.kr/DRF/lawSearch.do
본문 주소: http://www.law.go.kr/DRF/lawService.do
공통: GET / type=XML / OC=기관에서 사용할 인증값

법령 목록: target=eflaw, search=1, query=문서명, nw=2,3, display=100, page=1부터 순회
법령 본문: target=eflaw, MST=목록의 법령일련번호, efYd=해당 판본 시행일
행정규칙 목록: target=admrul, search=1, query=문서명, nw=1, display=100, page=1부터 순회
행정규칙 본문: target=admrul, ID=목록의 행정규칙일련번호

중계 요청은 GET 방식으로, target_url 헤더에 원천 주소와 target을 넣고 나머지 값은 GET 쿼리로 전달합니다.
49종 전체 문서명과 문서별 요청값·URL 형식은 첨부 Excel에 정리했습니다.
개인 계정의 OC·API 키·쿠키·토큰은 포함하지 않았으며, OC는 {기관_OC}로 표시했습니다.
실제 호출 시 사용 권한이 있는 기관 OC를 별도로 설정해야 합니다.

2. LSW 파일 다운로드 추가 등록

기본 접속 정보
  도메인: www.law.go.kr / HTTPS / TCP 443
  경로: /LSW/flDownload.do
  방식·파라미터: GET / flSeq=파일 식별번호
  대표 링크: https://www.law.go.kr/LSW/flDownload.do?flSeq=162138219

일부 행정규칙 원문에 포함된 추가 접속 정보
  도메인: law.go.kr / HTTP / TCP 80
  경로: /flDownload.do
  방식·파라미터: GET / flSeq=파일 식별번호
  대표 링크: http://law.go.kr/flDownload.do?flSeq=141869659

DRF 본문이 반환하는 파일별 flSeq를 전달하여 HWP·PDF 등의 원본 파일을 받으려고 합니다.
응답은 원본 파일 바이트와 파일명·Content-Type·HTTP 상태를 보존해 전달해 주시면 됩니다.
대표 링크는 접속 형식을 설명하는 보관판본 사례이며, 실제 수집 시 해당 본문이 반환한 링크를 사용합니다.

Dataiku 배치에서 위 경로를 이용할 수 있도록 네트워크·방화벽·파일 다운로드 중계 등록을 요청드립니다.
개발요청 등록 양식과 필수 신청 항목, 신규 중계 경로를 안내 부탁드립니다.

3. 첨부파일 설명

① 법제처_API_요청값_접속정보.xlsx
   Dataiku 배치 수집 흐름, 49종 문서명, 문서별 목록·본문 조회값과 URL 형식,
   판본 연결 규칙, LSW 접속 정보와 대표 링크를 정리한 표입니다.
   인증값은 {기관_OC}로 표시했습니다.

② 법제처_API_회신본문.txt
   이 메일과 동일한 내용의 일반 텍스트 파일입니다. 문안을 복사하거나 신청서에 옮길 때 사용할 수 있습니다.

감사합니다.
'''
    reply=OUT/'법제처_API_회신본문.txt';reply.write_text(text,encoding='utf-8')
    body='<html><body style="font-family:Arial,Malgun Gothic,sans-serif;font-size:14px;line-height:1.6">'
    for para in text.strip().split('\n\n'):
        para=html.escape(para).replace('\n','<br>')
        if para.startswith(('1. ','2. ','3. ')) and '<br>' not in para:para='<b>'+para+'</b>'
        body+='<p style="margin:0 0 12px 0">'+para+'</p>'
    body+='</body></html>'
    (OUT/'EMAIL_BODY.html').write_text(body,encoding='utf-8')

    wb=load_workbook(SOURCE/'법제처_API_요청값_접속정보.xlsx')
    original=load_workbook(SOURCE/'법제처_API_요청값_접속정보.xlsx',read_only=True,data_only=False)
    sheet=wb['이용안내'];sheet.delete_rows(1,sheet.max_row)
    for row in [('항목','내용'),('실행 위치','Dataiku 배치'),('호출 흐름','Dataiku 배치 → API 중계서버 → 법제처'),
        ('대상','법령 37종 + 행정규칙 12종 = 49종'),('수집 계획','최초 전체 수집 후 매일 변경 자료 수집'),
        ('인증값','개인 계정 OC·API 키·쿠키·토큰 미포함'),('OC','{기관_OC}'),
        ('실제 호출','사용 권한이 있는 기관 OC를 별도로 설정'),
        ('중계 요청','GET / target_url 헤더에 원천 URL 및 target; 나머지는 GET 쿼리'),
        ('판본 연결','목록 응답의 식별자·시행일을 다음 본문 조회에 연결'),
        ('파일 식별자','본문이 반환한 flSeq를 사용. 접속 정보에는 대표 링크만 기재'),
        ('고정 목적지 IP','현재 자료 미포함. IP가 필수인 신청서이면 보완 항목')]:sheet.append(row)
    lsw=wb['LSW_접속정보'];lsw.append(['호출 위치','Dataiku 배치에서 API 중계서버 호출'])
    for s in (sheet,lsw):
        for c in s[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='17365D')
        for row in s:
            for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
    for name in ('49종_목록조회','49종_본문조회'):
        assert list(wb[name].values)==list(original[name].values)
    original.close()
    xlsx=OUT/'법제처_API_요청값_접속정보.xlsx';wb.save(xlsx)
    check=load_workbook(xlsx,read_only=True,data_only=False)
    banned=('GENOS','5126','5,126','R2','R3','CSV','ZIP','파일URL_목록','이전 발송','앞서 보낸')
    for value in [text,body]+[str(c.value) for s in check for row in s for c in row if c.value is not None]:
        assert not any(term in value for term in banned),'Unexpected obsolete content'
    assert check['49종_목록조회'].max_row==50 and check['49종_본문조회'].max_row==50
    assert all(row[3]=='{기관_OC}' for row in list(check['49종_목록조회'].values)[1:])
    check.close()
    old=json.loads((DIAGNOSTICS/'relay_request_20261027_r2/private_delivery/02_전체49종_실제요청값_R2.json').read_text())
    secret=old['credential']['LAW_OC'];variants={secret,quote(secret,safe=''),quote_plus(secret)}
    with zipfile.ZipFile(xlsx) as z:
        for name in z.namelist():
            raw=z.read(name).decode('utf-8')
            assert not any(v in raw or v in unquote(raw) for v in variants),'Credential found'
            assert 'GENOS' not in raw
    assert not any(v in text or v in body for v in variants)

    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];metadata=[]
    for p in (xlsx,reply):
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if p.suffix=='.xlsx' else 'text/plain'
        part={'mime_type':mime,'filename':p.name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode().rstrip('=')}}
        if p.suffix=='.txt':part['charset']='UTF-8'
        parts.append(part);metadata.append({'name':p.name,'mime_type':mime,'bytes':p.stat().st_size,'sha256':sha(p)})
    payload={'to':'hyungjininfocz.son@partner.samsung.com','subject':'RE: API중계서버 URL추가 문의 — Dataiku 배치 수집 조회 조건 및 파일 다운로드 등록 요청',
        'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
    (OUT/'EMAIL_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False))
    report={'status':'READY','recipient':payload['to'],'subject':payload['subject'],'attachments':metadata,
        'flow':'Dataiku batch -> API relay -> law.go.kr','personal_credentials_included':False,
        'checks':['49 document list and body request rows preserved','Dataiku is the stated caller in email and workbook','no full file URL list or count in sent material','only two representative download links','no GENOS or historical version references in visible content','personal OC absent in workbook XML and mail','each of two attachments described in mail'],
        'network_api_calls':0,'runtime_changes':0}
    (HERE/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'READY','to':payload['to'],'attachments':metadata},ensure_ascii=False))


if __name__=='__main__':main()
