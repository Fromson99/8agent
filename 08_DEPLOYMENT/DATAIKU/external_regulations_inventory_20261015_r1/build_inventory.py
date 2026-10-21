"""Read-only source inventory; does not run collectors or contact any endpoint."""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATE = "2026-10-15"


def rows(text):
    return [line.split(" | ") for line in text.strip().splitlines()]


sources = rows("""
S01 | 필수 | 국가법령정보센터: 법령 | https://www.law.go.kr | 공식 Open API / GET / XML | 자본시장법·시행령·시행규칙, 금소법, 지배구조법, 외국환거래법, 상법, 세법 등 | lawSearch(target=law) → 법령 ID/MST 확인 → lawService(target=eflaw 또는 law) → 부칙·별표·서식 링크 다운로드 | lawgo.py + collect.py 존재; 법령·행정규칙 합계 62개 선언 | 사진 목록에 본문 law는 있음. 목록 law, 시행일 본문 eflaw, 첨부 다운로드는 명시되지 않아 추가 확인/요청 | 공식 문서와 현행 코드 확인. 삼성 중계 성공 미확인
S02 | 필수 | 국가법령정보센터: 행정규칙 | https://www.law.go.kr | 공식 Open API / GET / XML | 금융투자업규정·세칙, 증권 발행·공시 규정·세칙, 외감·회계 규정, 전자금융감독규정 등 | lawSearch(target=admrul) → 현행 일련번호 → lawService(target=admrul) → 부칙·별표·서식·첨부 | lawgo.py + collect.py 존재 | 본문 admrul 있음. 일반 목록 admrul, 첨부 다운로드 추가 확인/요청 | admrulOldAndNew 목록은 일반 admrul 목록을 대체하지 않음
S03 | 필수 | 금융투자협회 법규정보시스템 | https://law.kofia.or.kr | 웹 조회 경로 / GET·POST form / HTML·HWP | 표준투자권유준칙, 인수업무규정, 대표주관업무 모범기준, 영업·업무규정 및 세칙, 모범규준 | 분류·규정 트리 → seq/historySeq → 본문 HTML·전문 HWP → 별표·개정문·신구대비표 | kofia.py 존재; 지정 5개 + 모범규준 분류 1개. 분류는 여러 문서로 전개 | 신규 도메인·조회/다운로드 경로 및 POST form 중계 요청 | 공개 Open API 계약은 확인하지 못함. 코드상 웹 경로이며 현행 운영 재검증 필요
S04 | 필수 | 한국거래소 법규서비스 | https://rule.krx.co.kr/out/index.do | 웹 조회 경로 / 세션·CSRF / GET·POST form / HTML·JSON·HWP | 유가·코스닥·코넥스 상장규정, 유가·코스닥 공시규정 및 세칙; 매매·시장감시·회원·파생상품 규정은 확대 후보 | 세션 생성 → 규정 트리 → bookid/statehistoryid → 본문·파일정보 → 토큰 갱신 → 전문·별표 다운로드 | krx.py 존재; 상장·공시 중심 11개 선언 | 신규 도메인, Cookie/Set-Cookie, Referer, X-CSRF-TOKEN, POST form, 파일 응답 중계 요청 | GET target_url 한 번만으로 전 과정 지원된다고 볼 수 없음
S05 | 보완 필수 | 금융위·금감원 규정 원문/시행자료 | https://www.fsc.go.kr/po040200 | 게시판 목록·상세·첨부 수집; 공개 API 계약 미확인 | 법제처 누락·시차가 있는 고시/훈령/시행세칙, 개정문·신구대비표·업무해설 자료 | 법제처 명칭/버전과 대조 → 발행기관 게시판 원문·첨부 수집 → 중복 연결 | 해당 게시판 전용 수집 경로는 이번에 확인한 6개 수집기에서 확인되지 않음 | fsc.go.kr 게시판과 첨부 경로 요청. 금감원 law.fss.or.kr 현행 경로/다운로드는 추가 확인 | 금융위 게시판 확인. 금감원 법규 포털은 이번 조회 실패; 실제 URL·요청 방식 확인 필요
S06 | 해석 자료 | 금융위 법령해석·비조치의견서 | https://better.fsc.go.kr/fsc_new/replyCase/TotalReplyList.do?muGpNo=88&muNo=117&stNo=11 | 웹 조회 경로 / POST form / JSON 목록·HTML 상세 | 자본시장법·금융투자업규정·금소법 등 금융위 소관 법규의 회신 사례 | 통합목록 페이지 순회 → 유형별 상세 → 회신일·질의·회신·이유·관련 법규 보존 | fsc.py + collect_fsc.py 존재. 상세 HTML 수집; 첨부 파일 다운로드는 별도 보완 필요 | 신규 도메인·목록/상세 POST 및 첨부 경로 요청 | 법규 원문과 분리. 비조치의견서의 전제·범위·유효성 확인 필요
S07 | 해석 자료 | 법제처 법령해석례·판례 | https://open.law.go.kr | 공식 Open API / GET / XML | 소관 법령의 법제처 해석례, 법원 판례 및 참조조문 | lawSearch(target=expc/prec) → 일련번호 → lawService(target=expc/prec) → 법령·조문·기준시점 연결 | expc.py/prec.py + collect_expc.py/collect_prec.py 존재 | 같은 law.go.kr 도메인에 target=expc/prec 목록·본문 추가 요청 | 이름 검색만으로 전체 관련 사례를 빠짐없이 얻는 것은 아님. 조문 인용·검색어 확장 필요
S08 | 변경 감시 | 국민참여입법센터 | https://www.lawmaking.go.kr | 제공 사진의 REST/XML; 운영 명세 추가 확인 | 자본시장법 등 입법예고, 금융투자업규정 등 행정예고, 수정 예고 | 목록 → 예고 식별값 → 상세·첨부 → 발표/마감/수정일 → 확정·공포본과 연결 | 사진에 개발 완료 안내 있음. 이번에 확인한 기본 수집기와의 연결은 미확인 | 사진 목록 6경로 범위 확인; www와 opinion 호스트 차이, 파라미터, 인증, 첨부 규칙 확인 | 예고안은 현행 법규가 아님. 삭제/수정/철회도 상태로 보존
S09 | 업무별 확대 | 금융정보분석원(FIU) | https://www.kofiu.go.kr | 법령/행정규칙은 법제처 API, 기관 자료는 게시판·첨부 | 특정금융정보법 및 하위법령, 특정 금융거래정보 보고 및 감독규정, AML 업무규정·안내 | 법제처 대상 추가 → FIU 공지/규정 원문·HWPX/PDF 보완 | 현재 62개 대상에 AML 법령군 미등록 | FIU 규정/지침 게시판 목록·상세·첨부 요청. 정확한 AML 문서 마스터는 담당부서 확정 | 공식 고시 첨부 존재 확인. 기관별 API 계약은 미확인
S10 | 업무별 확대 | 한국은행 법규 | https://www.bok.or.kr/portal/singl/law/view.do?lawId=&menuNo=200200 | 법규 목록·버전 상세·첨부 / 웹 수집 | 외국환거래업무 취급세칙·취급절차, 관련 지급결제 자료 | 법규 ID·개정 이력 → 해당 버전 본문·첨부 → 상위 외국환거래법/규정 연결 | 외국환거래법·시행령·규정은 선언됨. 한국은행 전용 연결은 미확인 | bok.or.kr 법규 경로 및 실제 첨부 배포 호스트 허용 요청 | 첨부 CDN URL은 만료 가능하므로 원문 페이지에서 매번 취득; 고정 토큰 저장 금지
S11 | 업무별 확대 | 한국예탁결제원(KSD) | https://www.ksd.or.kr | 공식 규정 제공 경로/파일 공급 방식 추가 확인 | 전자등록·예탁·결제·권리처리 관련 업무규정·세칙 | 규정 목록·버전·첨부 계약 확보 → 웹/파일 수집; 제한 자료는 승인된 파일 공급 | 전자등록법·시행령은 선언됨. KSD 전용 수집기/규정 경로는 미확인 | 규정 전체 목록, 상세/다운로드 URL, 공개/회원 전용 구분, 제공 방식 요청 | 홈페이지 확인만으로 규정 API가 있다고 판단하지 않음
S12 | 업무별 확대 | 국세청 국세법령정보시스템 | https://taxlaw.nts.go.kr/?lang=ko | 세법 원문은 법제처 API; 해석/예규는 웹 제공방식 확인 | 법인세·소득세·증권거래세·국제조세 등 법령과 세법해석·예규 | 법령은 중복 수집 연결 → 해석/예규 목록·상세 → 세목·일자·관련 조문 보존 | 주요 세법 일부 선언됨. 국세청 사례 전용 수집기 연결 미확인 | 세법해석·예규 목록/상세/첨부와 공식 제공/API 유무 확인 요청 | 판례 API만으로 국세청 예규 전체를 확보할 수 없음
S13 | 업무별 확대 | 개인정보보호위원회 | https://www.pipc.go.kr | 법령/고시는 법제처 우선; 기관 게시판·첨부 보완 | 개인정보 보호법·시행령, 개인정보의 안전성 확보조치 기준, 가이드라인 | 법제처 법령·고시 → 기관 공지/해설서·첨부 → 문서 성격·버전 분리 | 개인정보법·시행령 선언됨. 고시 추가와 기관 게시판 연결 확인 필요 | pipc.go.kr/www.pipc.go.kr 실제 목록·상세·첨부 및 리디렉션 범위 확인 | 가이드라인과 고시를 같은 종류로 저장하지 않음
S14 | 업무별 확대 | 기타 거래·업무 기관 | 기관별 공식 주소와 규정 제공 경로를 담당부서가 확정 | 공개 웹/계약 파일/승인된 수동 반입 | 대체거래소, 한국증권금융, 퇴직연금, 신탁·유동화, 공정거래·노무 등 실제 영위 업무 관련 외규 | 사업/인가/회원 자격별 적용 문서 마스터 → 기관별 공급 계약 → 동일 원문 보존·버전 계약으로 반입 | 이번 고정 대상만으로 전사 적용 범위를 포괄하지 않음 | 기관명·정확한 규정명·담당부서·공식 URL·파일 제공 권한 먼저 확정 | 국내 범위. 해외 업무 규제는 국가/업무별 별도 목록 필요; 기관명만 보고 적용 단정하지 않음
""")

endpoints = []
def ep(group, use, method, url, params, response, status, note):
    endpoints.append([f"E{len(endpoints)+1:02d}", group, use, method, url, params, response, status, note])

LAW = "https://www.law.go.kr"
for target, title in [("law", "법령 목록"), ("admrul", "행정규칙 목록"), ("expc", "법령해석례 목록"), ("prec", "판례 목록")]:
    ep("법제처", title, "GET", LAW+"/DRF/lawSearch.do", f"OC=<승인된 인증값>; target={target}; type=XML; query=<정확한 명칭/검색어>; display=100; page=<페이지>", "XML 목록", "공식 문서+현행 코드", "사진에는 일반 law/admrul/expc/prec 목록이 명시되지 않음. 명칭·유형·현행 여부·페이지 총수 검증; OC를 코드/로그에 노출하지 않음")
ep("법제처", "시행일 기준 법령 본문", "GET", LAW+"/DRF/lawService.do", "OC; target=eflaw; type=XML; ID=<법령ID> 또는 MST=<일련번호>&efYd=YYYYMMDD", "XML 조문·부칙·별표", "공식 문서+현행 코드", "ID는 현행 본문, 특정 버전은 MST+efYd. 미래 시행·조문별 시행일과 공포일을 구분")
ep("법제처", "공포일 기준 법령 본문", "GET", LAW+"/DRF/lawService.do", "OC; target=law; type=XML; MST=<검색 결과의 법령일련번호>", "XML", "사진+현행 코드", "공포본과 현재 시행본은 다를 수 있음; 사진 중계 target_url은 http 스킴. 코드의 https와 허용 URL 일치 확인")
ep("법제처", "행정규칙 본문", "GET", LAW+"/DRF/lawService.do", "OC; target=admrul; type=XML; ID=<행정규칙일련번호>", "XML 조문·부칙·별표·첨부", "공식 문서+사진+현행 코드", "현재 어댑터는 ID에 일련번호 사용. 행정규칙ID와 혼동하지 않음; 공식 API에는 LID도 별도 존재")
for target, title in [("expc", "법령해석례 본문"), ("prec", "판례 본문")]:
    ep("법제처", title, "GET", LAW+"/DRF/lawService.do", f"OC; target={target}; type=XML; ID=<목록에서 받은 일련번호>", "XML", "공식 문서+현행 코드", "원문·일자·관련 조문 보존. 일부 국세청 판례는 공식 안내상 HTML만 지원하므로 형식별 예외 확인" if target=="prec" else "회신 당시 법령 버전과 현재 버전을 구분")
ep("법제처", "별표·서식·첨부 파일", "GET", LAW+"/LSW/flDownload.do", "본문 XML의 실제 파일 링크 그대로 사용; flSeq 등 반환 값", "HWP/PDF 등 바이너리", "공식 본문 응답 필드+현행 코드", "다운로드 URL을 추정 생성하지 않음. 다른 반환 경로/호스트는 별도 허용 확인. 파일명·크기·SHA-256 보존")
for target,title,kind in [("oldAndNew","법령 신구법 비교","lawService"),("lsStmd","법령 체계도","lawService"),("admrulOldAndNew","행정규칙 신구법 비교 목록","lawSearch"),("admrulOldAndNew","행정규칙 신구법 비교 본문","lawService")]:
    ep("법제처",title,"GET",LAW+f"/DRF/{kind}.do",f"OC; target={target}; 나머지 식별자·형식은 해당 공식 명세 확인","XML 등 명세 확인","사진에 포함","법령 본문·현행 목록·별표 수집을 대체하지 않음. 체계도는 하위 법령/위임 규정 누락 점검에 사용")

K="https://law.kofia.or.kr"
for title,method,path,params,out,note in [
 ("현행 규정 트리","GET","/service/law/lawCurrentPartTree.do","없음","HTML","seq/lawType/historySeq 추출; 현재 어댑터는 lawType=1 대상"),
 ("분류별 목록","POST form","/service/law/lawPartCurrentList.do","page; selectedSeq=<분류ID>","HTML","모범규준 분류 3을 코드에서 전개. 모든 페이지 순회"),
 ("현행 버전 식별","GET","/service/law/lawView.do","seq; historySeq=0; gubun=cur; tree=part","HTML","현재 historySeq 추출"),
 ("규정 본문","GET","/service/law/lawFullScreenContent.do","seq; historySeq","HTML","조문·부칙·별표 링크 추출"),
 ("전문 파일","GET","/download.do","gubun=101; seq=<historySeq>","HWP","규정 고유 seq와 버전 historySeq 구분"),
 ("별표 파일","GET","/download.do","gubun=102; seq=<본문 링크의 첨부ID>","HWP 등","첨부ID는 본문에서 취득; historySeq로 대체하지 않음"),
 ("개정 이력 목록","POST form","/service/revision/revisionlist.do","page; searchValue=<규정명>","HTML","기준 버전과 모든 필요한 개정 이력 연결"),
 ("개정 이력 상세","GET","/service/revision/revisionView.do","historySeq","HTML","실제 버튼에서 개정문/신구대비표 링크 추출"),
 ("개정문/신구대비표","GET","/download.do","gubun=104 또는 105; seq=<상세에서 받은 값>","HWP 등","개정 건별 가용 여부 확인"),
 ("개정 메타정보","GET","/service/law/revisionInfo.do","historySeq","HTML","코드는 개정일/부서 기록. 개정일을 시행일로 치환하지 않음")]:
    ep("금투협",title,method,K+path,params,out,"현행 kofia.py의 웹 경로",note)

K="https://rule.krx.co.kr"
for title,method,path,params,out,note in [
 ("세션/토큰 생성","GET","/out/index.do","없음","HTML + Cookie","같은 세션 유지; 중계가 Set-Cookie를 처리하는 방식 확인"),
 ("규정 화면 초기화","POST form","/out/regulation/regulationMain.do","Menucd=BYLAW; index=law_rule; gbn=out; _csrf","HTML","상세 조회 전에 초기화"),
 ("규정 트리","POST form","/out/regulation/getTreeNode.do","node=<0 또는 하위 노드>; statecd=현행; mtype=htree; Menucd=BYLAW; webgbn=OUT; gbnid=0; gbn2=out","JSON","X-CSRF-TOKEN/Referer/세션; bookid 얻음"),
 ("규정 본문","POST form","/out/regulation/regulationView.do","bookid; noformyn=N; gbnid=0; mtype=htree; searchForm=; Menucd=BYLAW; _csrf","HTML","statehistoryid 추출"),
 ("전문/개정문/신구대비표 파일정보","POST form","/web/regulation/downloadRuleFile.do","bookid; statehistoryid; filecd=JUN/GAE/SIN","JSON fileMap","실제 SERVERFILE/PCFILENAME을 다운로드에 사용"),
 ("별표 화면 초기화","POST form","/out/regulation/regulationList.do","Menucd=BYLAW; mtype=byul; gbnid=BYUL; smType=byul; index=law_rule; gbn=out; _csrf","HTML","현재 코드가 먼저 여는 화면"),
 ("별표/별지 등 목록","POST form","/web/regulation/regulationListData.do","start; limit=100; mtype=byul; Menucd=BYLAW; stit=규정; gbnid=BYUL/BYULSEO/BYULCH/BYULBU/BYULJI; gbn2=out","JSON","규정명/버전 정확히 대조; 현재 코드의 분류별 성공률은 별도 검증"),
 ("다운로드 토큰 갱신","POST form","/login/getData.do","_csrf; X-CSRF-TOKEN 헤더","토큰 응답","현행 코드상 파일마다 새 토큰 취득; Cookie 세션 유지"),
 ("실제 파일 다운로드","POST form","/Download.do","Serverfile; Pcfilename; folder=ATTACH; _csrf=<새 토큰>","HWP 등 바이너리","Referer 유지. HTTP 200이어도 HTML 오류이면 파일 수집 실패")]:
    ep("거래소",title,method,K+path,params,out,"현행 krx.py의 웹 경로",note)

F="https://better.fsc.go.kr"
ep("금융위 해석", "회신사례 목록", "POST form",F+"/fsc_new/replyCase/selectReplyCaseTotalReplyList.do","draw=1; start; length=100; searchCondition=all; searchKeyword=<법규명>","JSON recordsTotal/data","현행 fsc.py의 웹 경로","목록의 dataIdx/pastreqType을 상세 요청에 사용; 전체 페이지와 관련성 점검")
for name,path,key in [("법령해석","LawreqDetail.do","lawreqIdx"),("비조치의견서","OpinionDetail.do","opinionIdx"),("2014년 이전 회신","PastReqDetail.do","pastreqIdx")]:
    ep("금융위 해석",name,"POST form",F+"/fsc_new/replyCase/"+path,f"{key}=<dataIdx>; muNo=117; stNo=11; actCd=R","HTML","현행 fsc.py의 웹 경로","첨부 파일 전량 다운로드는 현재 수집 코드에 별도 구현 필요")
for use,path,query in [("시행 중 행정지도","OpertnList.do","muNo=127&stNo=11&tab1=0&tab2=1"),("행정지도 예고","PrvntcList.do","muNo=127&stNo=11&tab1=0&tab2=0")]:
    ep("금융위 행정지도",use,"GET (화면)",F+"/fsc_new/status/adminMap/"+path+"?"+query,"실제 목록 AJAX·상세·첨부 요청 명세는 추가 조사","웹 화면","공식 페이지 확인; 수집기 연결 미확인","시행일·존속기간·종료/연장 상태 보존. 예고와 시행 분리")

L="https://www.lawmaking.go.kr"
for title,path in [("입법예고 목록","ogLmPp.xml"),("입법예고 목록(수정일 기준)","ogLmPpMod.xml"),("행정예고 목록","ptcpAdmPp.xml"),("입법예고 상세","ogLmPp/{ogLmPpSeq}/{mappingLbicId}/{announceType}.xml"),("입법예고 상세(수정일 기준)","ogLmPpMod/{ogLmPpSeq}/{mappingLbicId}/{announceType}.xml"),("행정예고 상세","ptcpAdmPp/{ogAdmPpSeq}/{mappingAdmRulSeq}/{announceType}.xml")]:
    ep("입법센터",title,"GET",L+"/rest/"+path,"제공 사진 기준; 목록/상세 필수값·페이지·인증·첨부 명세는 담당자 확인","XML","사진의 제공 목록; 현행 운영 미검증","사진 예시는 opinion.lawmaking.go.kr 호스트 사용. www/opinion 동등성이나 리디렉션 허용을 추정하지 않음")

for group,use,url,note in [
 ("금융위","규정·고시·공고·훈령","https://www.fsc.go.kr/po040200","목록→상세→첨부 실제 링크를 추출; 별도 Open API 계약 미확인"),
 ("금감원","법규·시행세칙","https://law.fss.or.kr/","이번 웹 조회 실패. 현행 목록/상세/다운로드 주소를 기관 또는 중계 담당자에게 요청"),
 ("FIU","감독규정 고시 예시","https://www.kofiu.go.kr/kor/law/announce_view.do?lawordInfoOrdrNo=90&seCd=001","공식 고시 페이지 확인. 이것은 단일 게시물이며 전체 목록 주소/첨부 요청은 별도 확인"),
 ("한국은행","외국환 법규 진입","https://www.bok.or.kr/portal/singl/law/view.do?lawId=&menuNo=200200","lawseq/hseq로 법규·버전 식별. 전체 조회/첨부 요청 명세는 현장 연계 전 확인"),
 ("국세청","세법 목록","https://taxlaw.nts.go.kr/st/USESTA001M.do","법령 원문 중복보다는 해석/예규 보완; 목록·상세 데이터 계약 추가 확인"),
 ("개인정보위","안전성 확보조치 기준 고시 게시 예시","https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020010000&nttId=11531","단일 고시 게시물; 현행 버전 보장은 아님. 목록/개정 이력 추적 필요"),
 ("예탁결제원","공식 홈페이지","https://www.ksd.or.kr/","규정 목록·상세·첨부·인증 계약 미확인. 이 홈페이지 주소를 API로 취급하지 않음")]:
    ep(group,use,"GET (페이지)",url,"사이트별 상세 계약 확인","HTML/첨부","공식 페이지 확인" if group!="금감원" else "접속 확인 실패",note)

business = rows("""
증권업·자본시장 공통 | 자본시장과 금융투자업에 관한 법률·시행령·시행규칙; 금융투자업규정·시행세칙 | 법제처 law/admrul + 금융위·금감원 원문 보완 | 법령군과 감독규정 선언됨 | 별표·보고서식·위임 규정·시행 예정본까지 확인 | 인가업무/업무행위·기준시점에 따라 적용
판매·투자권유·소비자보호 | 금소법·시행령·감독규정; 표준투자권유준칙; 금투협 영업·업무규정·세칙; 관련 모범규준 | 법제처 + 금투협 + 금융위 회신/행정지도 | 주요 법규와 협회 지정 대상 존재 | 모범규준 분류를 전체 전개하고 적용 제외·존속기간 확인 | 모범규준을 모두 법률과 동일 효력으로 분류하지 않음
IB·IPO·인수·상장·공시 | 증권의 발행 및 공시 등에 관한 규정·세칙; 인수업무규정; 대표주관업무 모범기준; 상장·공시규정·세칙 | 법제처 + 금투협 + KRX | 현행 대상이 집중된 영역 | 시장별 별표·별지·심사기준, 변경 이력의 완결성 확인 | 거래소 시장/주관 업무 범위로 적용 구분
매매·시장감시·파생상품 | 거래소 업무규정·시장감시규정·회원관리규정·파생상품시장 관련 규정 및 세칙 | KRX 규정 전체 트리 | 현재 11개는 상장/공시 중심 | 담당부서 확정 명칭으로 대상 확대; 대체거래소 업무 시 별도 외규 추가 | 각 규정 정확한 현행 명칭/시행 여부는 규정 목록에서 확정
지배구조·내부통제·리스크 | 금융회사 지배구조법·시행령·감독규정·세칙; 금융투자업규정; 금융복합기업집단법령 | 법제처 + 금융위/금감원 | 주요 문서 선언됨 | 금융지주회사법 하위법령 등 위임 체인 누락 점검 | 기업집단·지주회사 적용 여부는 회사 구조에 따라 별도 판단
외환·해외투자·결제 | 외국환거래법·시행령·규정; 한국은행 외국환거래업무 취급세칙·취급절차 | 법제처 + 한국은행 | 법제처 3종 선언됨 | 한국은행 규정·절차/별표 추가, 해외 규제는 국가별 별도 | 신고·보고 주체 및 영위 업무 기준으로 선정
AML·고객확인·금융실명 | 특정금융정보법·하위법령; 특정 금융거래정보 보고 및 감독규정; AML 업무규정; 금융실명법령 | 법제처 + FIU | 현재 62개 고정 대상에서 이 법령군 미확인 | 법률/하위법령/감독규정/업무규정/서식 추가 | 정식 명칭·현행 버전·소관 부서는 원문 대조로 확정
전자금융·IT·보안·업무위탁 | 전자금융거래법·시행령; 전자금융감독규정·세칙; 금융기관 업무위탁 규정 | 법제처 + 금융위/금감원 | 감독규정·세칙·업무위탁 규정 선언됨 | 전자금융거래법·시행령 대상 추가, 관련 해설/행정지도 보완 | 기술 가이드와 행정규칙 종류 분리
개인정보·신용정보 | 개인정보 보호법·시행령; 신용정보법·시행령; 안전성 확보조치 기준; 신용정보 감독규정류 | 법제처 + 개인정보위 + 금융위/금감원 | 두 법령군 일부 선언됨 | 고시·감독규정·세칙·고객정보 처리 업무별 기준 확대 | 최신 고시와 안내서 버전 구분
전자등록·예탁·청산·결제 | 주식ㆍ사채 등의 전자등록에 관한 법률·시행령; 예탁결제 관련 기관 업무규정·세칙 | 법제처 + KSD + KRX(거래소 담당 범위) | 전자등록 법률·시행령 선언됨 | KSD 정확한 규정명/제공 경로/회원 전용 여부 확보 | 거래소와 예탁결제원 역할별 자료 구분
회계·외부감사 | 외감법·시행령·시행규칙; 외부감사 및 회계 등에 관한 규정·세칙; 적용 회계기준 | 법제처 + 금융위/금감원; 회계기준 제공기관은 별도 계약 확인 | 외감 법령/규정 선언됨 | 회계기준 원문까지 범위에 포함하면 별도 제공/이용 방식 확인 | 법규와 회계기준을 문서 유형별 보존
세무·원천징수 | 법인세·소득세·상증세·조특법 등; 증권거래세·국제조세·부가가치세 관련 법령은 업무별 추가 | 법제처 + 국세청 해석/예규 | 주요 세법 일부 선언됨 | 원천징수·거래세·해외 과세 적용 업무에 맞게 법령군/예규 확대 | 세법·기본통칙·예규·판례를 구분
회사법·투자·신탁·유동화 | 상법; 벤처기업법령; 공정거래법령; 신탁법·자산유동화법·담보부사채신탁법 등 업무별 법령 | 법제처 + 관련 소관기관/거래기관 | 상법·벤처·공정거래 등 일부 선언됨 | 신탁·유동화·퇴직연금 등 실제 업무별 문서군 확정 | 예시 약칭은 API 검색 때 정식 명칭으로 치환
퇴직연금·노무·시설·안전 | 근로자퇴직급여 보장법·퇴직연금 감독규정; 노동/산업안전 등 전사 관리 법령 | 법제처 + 고용노동부 등 담당기관 | 이번 증권업 중심 고정 대상만으로 전체 범위 판단 불가 | 전사 준법 범위에 포함할지 업무 담당부서별 마스터 확정 | 모든 문서를 증권업 핵심 규제로 일괄 분류하지 않음
해석·판례·개정 동향 | 금융위 해석/비조치의견; 법제처 해석례; 판례; 입법·행정예고; 행정지도 | better.fsc.go.kr + law.go.kr + lawmaking.go.kr | 해석/판례 별도 수집 코드 존재; 예고/행정지도 통합 연결 미확인 | 회신/판결 당시 법령, 유효기간, 확정본 연결·검색 완전성 보완 | 규정 본문·해석·예고를 서로 다른 자료 종류로 관리
""")

requirements = rows("""
R01 | 우선 | 대상 문서 마스터 | 기관·정확한 문서명·상위법/하위법·업무·담당자·현행/연혁/시행예정·첨부 유무가 있는 전체 목록 | 위 목록과 기관별 전체 목록 대조 후 대상/제외/미확인을 명시 | 키워드 검색 결과만으로 전체 외규 수집 완료 판정 금지
R02 | 우선 | 법제처 추가 연계 | lawSearch.do target=law/admrul, lawService.do target=eflaw, 실제 반환 첨부 링크 | 목록→정확한 ID→현재 시행 본문→부칙→별표/서식 1세트 수신 | 사진 목록에 없음은 미개발 확정이 아님; 기존 허용범위 확인 후 추가 요청
R03 | 우선 | 외부 사이트 중계 방식 | 금투협·거래소·금융위 회신 웹 경로에 GET, POST application/x-www-form-urlencoded 지원 | 한 세션에서 목록→상세→파일까지 실행하고 원본 파일 검증 | JSON 응답 지원만으로 HWP/PDF 수집 지원을 판단할 수 없음
R04 | 우선 | 세션·헤더 | Cookie/Set-Cookie, X-CSRF-TOKEN, Referer, Content-Type 전달 및 저장 주체 | KRX 새 세션/토큰으로 전체 순서 성공, 만료 시 제한된 재시도 | 사진 Cookie 하드코딩은 전체 수집 설계가 아님; 세션 쿠키 자동 취득·갱신
R05 | 우선 | 파일/리디렉션 | 바이너리 무변환, Content-Disposition·Content-Type, 크기·시간 한도, 반환된 첨부 호스트/경로 | HWP/PDF/HWPX 식별·길이·SHA-256; HTTP 200 오류 HTML 거부 | law.go.kr DRF 경로만 허용하면 LSW 첨부가 빠질 수 있음
R06 | 우선 | 인증·식별자 | 승인된 LAW_OC, 발급/갱신·유효성·IP 허용 정책; 기관별 필요한 인증 계약 | 유효한 OC로 법령/행정규칙 목록과 본문 성공 | LAW_OC는 코드의 설정 이름; 공식 요청 필드는 OC. 사진 샘플값의 현 유효성 미확인
R07 | 우선 | 네트워크 양 구간 | Dataiku 실행 서버/NAT→중계, 중계→원천 도메인/포트·DNS·TLS·프록시 | 같은 시각 송신원/NAT/목적지/포트별 접속·방화벽 로그와 응답 증거 | 기존 사진은 연결 시간초과 증거. 방화벽 DROP 확정에는 장비 로그 등 추가 근거 필요
R08 | 운영 전 | 운영 주소/IP 선택 | 운영 중계 URL·FQDN, IP 조회 API 요청/응답 스키마·기관코드·장애전환 계약 | 정확한 운영 목적지 선택 및 실패 시 처리 확인 | 사진의 IP 조회 POST JSON EXTR_INSN_SECT_CODE=0은 개발 예시; 운영 값 추정 금지
R09 | 운영 전 | 전체 수집·증분 갱신 | 초기 전체 페이지/버전 수집, 공포·시행·개정·폐지·삭제·연혁 확인, 목록 스냅샷/해시 비교 | 예정 시행본과 현행본 분리; 원문 덮어쓰기 없이 새 버전 저장 | 수정일 필터만으로 소급 정정·삭제 전부 탐지된다고 가정하지 않음
R10 | 운영 전 | 수집 한도·실패 처리 | 페이지 제한·호출량·타임아웃·재시도·429/5xx·차단/인증오류·재개 상태 | 요청/성공/실패/건너뜀/미수집을 분리하고 총수 대조 | expc/prec 현재 페이지 상한 50, fsc 200. 상한 도달 시 전체 완료로 판정하지 않음
R11 | 운영 전 | 근거·버전·완료 기준 | 기관·원문 URL·문서ID·버전ID·공포/발령/시행일·수집시각·해시·공개범위·실제/모의 구분 | 목록상 예상 문서/첨부 수와 실제 수신 일치, 실패 0 또는 명시 승인된 제외 | 선언 개수/HTTP 200/로컬 코드 존재는 현장 수집 완료 증거가 아님
R12 | 확대 | 법제처 외 자료 제공 | FIU·한국은행·KSD·국세청·개인정보위·기타 기관의 목록/상세/첨부와 제공 권한 | 공식 원천·공개범위·문서 마스터·갱신 방식 확인 후 연결 | API 미확인 기관은 임의 URL 제작 없이 공식 제공 방식 확인
""")

notes = rows("""
작성 기준 | 2026-10-15; 국내 증권사 업무 관련 외규 수집의 설계/요청 목록. 회사 전체 적용 법규를 확정한 법률 의견이 아님
전체의 의미 | 법률→시행령·시행규칙→행정규칙/감독규정→협회·거래소·업무기관 규정→부칙·별표·서식·개정이력. 해석·판례·예고·가이드는 별도 자료 종류
현재 코드 대상 | collect.py 기준 법제처 62개, KRX 11개, KOFIA 지정 5개+모범규준 분류 1개. 79개 선언은 79개 문서 수집 완료를 뜻하지 않음
별도 수집기 | collect_fsc, collect_expc, collect_prec 모듈 존재. 기존 법령 manifest 기반 검색어로 회신/해석/판례 수집. 현재 로컬/GENOS 서빙 선택·수집 성공 상태는 이번에 인증하지 않음
검증 범위 | 공식 공개 문서·페이지 및 현행 작업 코드 읽기. 삼성 Dataiku/GENOS 내부 호출·운영 방화벽 확인·대량 원문 수집은 수행하지 않음
사진 목록 해석 | 법제처 본문/비교/체계도 및 예고 REST 경로는 제공 사진에 기재됨. 목록·eflaw·첨부·해석/판례·웹 수집 지원은 개발팀에 확인할 항목
공식 API와 웹 경로 | 법제처 DRF는 공식 Open API. 금투협·KRX·better.fsc 경로는 기존 코드가 쓰는 웹 요청이며 안정성/지원 계약은 별도 확인 필요
법제처 HTTP/HTTPS | 공식 가이드 일부는 http URL, 현재 소스는 https 사용. 중계의 target_url 허용 계약과 실제 원천 스킴·리디렉션을 맞춰야 함
식별자/비밀값 | 실제 OC·Cookie·인증값은 포함하지 않음. ID/seq/historySeq/bookid/첨부ID는 목록·상세에서 반환된 값을 사용
현장 네트워크 | 최신 사진은 Cookie 포함 요청에서도 45.101.64.86:8443 연결 단계 시간초과, HTTP 응답 없음. 방화벽 원인 확정 또는 외부 API 장애 증거로 확대 해석하지 않음
사진 개발 중계 | https://45.101.64.86:8443/law/DRF ; https://45.101.64.86:8443/law/making ; 헤더 target_url. 운영 주소/인증/응답 한도는 담당자 확인
사진 IP 조회 예시 | https://45.1.81.80:8443/oap/common/query/ip ; POST JSON. 개발 예시이며 운영 기관코드·응답 구조·IP 선택/장애전환은 미확인
기본 저장 원칙 | RAW 원문+목록 스냅샷+버전/시행일+SHA-256를 보존. DatasetPackage/SourceSet 및 기존 반입 경로로 연결. 이번 산출물은 수집 목록이며 데이터나 MAIN을 변경하지 않음
추가 범위 | 해외 규제, 계약/회원 전용 문서, 회계기준, 전사 노무/안전 등은 담당부서가 적용 범위·공식 제공 경로를 확정
""")

guides = rows("""
법령 목록 API | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwListGuide | 공식 가이드; 이번 조사 확인
시행일 법령 본문 API | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide | 공식 가이드; ID와 MST+efYd, 별표 링크 확인
행정규칙 목록 API | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide | 공식 가이드; 이번 조사 확인
행정규칙 본문 API | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide | 공식 가이드; ID/LID 및 첨부 필드 확인
법령해석례 목록 | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide | 공식 가이드; 이번 조사 확인
판례 목록 | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide | 공식 가이드; 이번 조사 확인
판례 본문 | https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide | 공식 가이드; 일부 국세청 판례 HTML 제한 확인
금투협 법규 | https://law.kofia.or.kr/ | 공식 사이트 및 현재 kofia.py; 웹 반환 텍스트 제한. 세부 경로는 코드 근거
거래소 법규 | https://rule.krx.co.kr/out/index.do | 공식 사이트 및 현재 krx.py; 세부 경로는 코드 근거
금융위 소관규정 | https://www.fsc.go.kr/po040200 | 공식 게시판 확인
금융위 회신사례 | https://better.fsc.go.kr/fsc_new/replyCase/TotalReplyList.do?muGpNo=88&muNo=117&stNo=11 | 공식 페이지 및 현재 fsc.py
금융위 행정지도 | https://better.fsc.go.kr/fsc_new/status/adminMap/OpertnList.do?muNo=127&stNo=11&tab1=0&tab2=1 | 공식 시행 목록 확인
FIU 고시 사례 | https://www.kofiu.go.kr/kor/law/announce_view.do?lawordInfoOrdrNo=90&seCd=001 | 2026-2 고시 첨부 예시; 전체 목록/최신성 보장은 아님
한국은행 외국환 규정 | https://www.bok.or.kr/portal/singl/law/view.do?lawId=&menuNo=200200 | 공식 법규 조회 진입
국세청 | https://taxlaw.nts.go.kr/?lang=ko | 공식 세법/해석 서비스; 별도 API 계약 미확인
개인정보위 고시 사례 | https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020010000&nttId=11531 | 공식 고시 게시물; 현행 버전은 추가 대조
예탁결제원 | https://www.ksd.or.kr/ | 공식 홈페이지; 규정 수집 경로 미확인
제공 사진 1~4 | 대화에 첨부된 삼성 API 플랫폼 안내와 API 목록 | 중계 URL/target_url, 법령 6종 및 예고 6경로의 출처. 사진 속 OC/Cookie는 이 문서에 재수록하지 않음
""")

target_path = ROOT / "02_BACKEND/lawrag/pipeline/collect.py"
tree = ast.parse(target_path.read_text("utf-8"))
target_ast = next(n.value for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "TARGETS")
targets = []
counts = {}
for group_ast, calls in zip(target_ast.keys, target_ast.values):
    group = ast.literal_eval(group_ast)
    counts[group] = len(calls.elts)
    for call in calls.elts:
        args = [ast.literal_eval(v) for v in call.args]
        hints = next((ast.literal_eval(k.value) for k in call.keywords if k.arg == "hints"), {})
        targets.append([len(targets)+1, group, args[2], hints.get("kind", "기관규정"), "분류 전개" if "folder_seq" in hints else "개별 문서", json.dumps(hints, ensure_ascii=False), f"02_BACKEND/lawrag/pipeline/collect.py:{call.lineno}", "수집 대상 선언; 현장 수집 완료/적용 여부 확인값 아님"])
assert counts == {"kofia": 6, "law": 62, "krx": 11}, counts

code_paths = ["02_BACKEND/lawrag/pipeline/collect.py", "02_BACKEND/lawrag/sources/lawgo.py", "02_BACKEND/lawrag/sources/kofia.py", "02_BACKEND/lawrag/sources/krx.py", "02_BACKEND/lawrag/sources/fsc.py", "02_BACKEND/lawrag/sources/expc.py", "02_BACKEND/lawrag/sources/prec.py", "02_BACKEND/lawrag/pipeline/collect_fsc.py", "02_BACKEND/lawrag/pipeline/collect_expc.py", "02_BACKEND/lawrag/pipeline/collect_prec.py"]
fingerprints = []
for rel in code_paths:
    fingerprints.append([rel, hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(), "현행 작업 파일 읽기; 실행/활성 릴리스 확인이 아님"])

sheets = [
 ("읽어주세요", ["항목", "내용"], notes, [25, 140]),
 ("출처별_연계", ["ID", "우선순위", "출처", "주소", "방식", "어떤 법규에 필요한가", "수집 순서", "현재 코드", "추가 요청", "근거·제한"], sources, [9, 16, 29, 48, 35, 58, 65, 55, 65, 60]),
 ("API_주소_상세", ["ID", "기관", "용도", "HTTP 방식", "주소", "요청값", "응답", "확인 수준", "주의·방법"], endpoints, [9, 20, 35, 20, 70, 78, 30, 40, 85]),
 ("업무별_법규", ["업무", "법규·자료군", "수집 출처", "현재 코드 범위", "추가 확보", "적용·분류 유의"], business, [31, 90, 50, 55, 70, 70]),
 ("현재_79개_선언", ["번호", "출처", "명칭", "법규 유형", "선언 종류", "hints", "코드 위치", "상태 해석"], targets, [9, 13, 62, 20, 18, 48, 65, 70]),
 ("중계_추가요청", ["ID", "시점", "항목", "요청 내용", "검증 기준", "주의"], requirements, [9, 18, 29, 100, 90, 90]),
 ("출처_문서", ["자료", "URL/출처", "확인 내용"], guides, [33, 110, 100]),
 ("코드_지문", ["파일", "SHA-256", "확인 수준"], fingerprints, [80, 70, 70]),
]

wb = Workbook()
wb.remove(wb.active)
for title, headers, data, widths in sheets:
    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in data:
        assert len(row) == len(headers), (title, row)
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    for cell in ws[1]:
        cell.font = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    for j, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = width
    for i in range(2, ws.max_row+1):
        max_lines = 1
        for j in range(1, len(headers)+1):
            cell = ws.cell(i, j)
            value = str(cell.value or "")
            cell.font = Font(name="맑은 고딕", size=10, color="243746")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor="F0F5FA" if i % 2 == 0 else "FFFFFF")
            if value.startswith("https://") and " " not in value and "{" not in value:
                cell.hyperlink = value
                cell.font = Font(name="맑은 고딕", size=10, color="0563C1", underline="single")
            display_len = sum(2 if ord(c)>127 else 1 for c in value)
            max_lines = max(max_lines, math.ceil(display_len/max(widths[j-1]-2, 1)))
        ws.row_dimensions[i].height = min(160, max(30, max_lines*15+8))
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:1"

path = OUT / "외규수집_주소_API_법규매핑_20261015_R1.xlsx"
wb.save(path)
check = load_workbook(path)
assert len(check.sheetnames) == len(sheets)
for title, headers, data, widths in sheets:
    assert check[title].max_row == len(data)+1
    assert check[title].max_column == len(headers)

payload = {"date": DATE, "scope": "국내 증권사 외규 수집 원천/연계 요청 목록; 적용 범위 확정 전", "sheets": {title: [dict(zip(headers, row)) for row in data] for title,headers,data,_ in sheets}}
(OUT/"inventory.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", "utf-8")
summary = f"""외규 수집 연계 요청 요약 ({DATE})

1. 국내 증권사 외규는 법제처의 법률/하위법령/행정규칙, 금투협/거래소/업무기관 규정, 부칙/별표/서식/연혁을 함께 확보해야 합니다. 해석/판례/예고/행정지도는 별도 종류로 수집합니다.
2. 현재 코드에는 법제처 62개, KRX 11개, KOFIA 지정 5개+모범규준 분류 1개가 선언되어 있으며, 금융위 회신/법제처 해석례/판례 수집기가 별도로 있습니다. 이 숫자는 전사 외규 전체 개수나 수집 성공 수가 아닙니다.
3. 제공 사진 목록에 추가 확인할 우선 항목: lawSearch target=law/admrul, lawService target=eflaw, 본문 반환 별표·첨부 링크, target=expc/prec 목록/본문, KOFIA/KRX/금융위 회신 웹 경로.
4. 웹 경로에는 GET 외 POST form, Cookie/Set-Cookie, CSRF·Referer, 바이너리 파일 전달이 필요합니다. 현재 중계의 지원 계약과 사이트별 허용 주소를 확인해야 합니다.
5. 확대 범위: AML/FIU, 전자금융거래법령, KRX 매매·시장감시·파생상품, 한국은행 외환 절차, KSD 예탁결제, 세법해석, 개인정보 고시 및 실제 업무별 전사 외규. 상세 명칭/적용 여부는 담당부서별 마스터로 확정합니다.
6. 최신 현장 사진은 Cookie 포함 요청도 중계 8443 연결 단계 시간초과라는 증거입니다. 방화벽 차단 확정은 송신원/NAT·목적지·시각 기준 방화벽/서버 로그가 필요합니다.

첨부 엑셀: {path.name}
- 출처별_연계: {len(sources)}개 출처/자료군
- API_주소_상세: {len(endpoints)}개 요청 경로/용도 (공식 API·웹 요청·사진 제공·미확인 상태 구분)
- 업무별_법규: {len(business)}개 업무 묶음
- 현재_79개_선언: 현행 collect.py에서 자동 추출한 79개 대상 선언
- 중계_추가요청: {len(requirements)}개 확인 항목
- 출처_문서, 코드_지문: 근거와 조회 시점 코드 SHA-256

실제 OC/Cookie는 포함하지 않았습니다. 삼성 내부 API 재호출, 데이터 수집, MAIN/GENOS 변경은 수행하지 않았습니다.
"""
(OUT/"외규수집_추가연계요청_요약.txt").write_text(summary, "utf-8")
print(json.dumps({"xlsx": str(path), "source_groups": len(sources), "endpoint_uses": len(endpoints), "business_groups": len(business), "target_declarations": counts, "sheets": len(sheets), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, ensure_ascii=False))
