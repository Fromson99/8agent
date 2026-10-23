"""V3 expands request semantics; earlier delivered versions remain unchanged."""
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
PARENT = OUT.parent
def b(kind, text): return {'kind': kind, 'text': text}
def table(headers, rows, widths=None):
    return {'kind': 'table', 'headers': headers, 'rows': rows, 'widths': widths or [.25,.75]}
def ref(text, url): return {'kind':'source','text':text,'href':url}
guide='https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName='

pages=[
 [
  b('eyebrow','뭉타 전달용  |  2026.10.23  |  V3 · 파라미터와 운영 조건 보강'),
  b('title','외규 수집 구축 요청'),
  b('lead','원본·첨부를 주기적으로 수집하고, 판본과 수집 상태를 함께 AIDP에 전달합니다.'),
  {'kind':'metrics','items':[['68종','자동 수집 대상'],['49종','법제처 API'],['19종','웹 크롤링']]},
  b('heading','01  수집 범위'),
  table(['대상','수량','수집할 원본'],[
   ['법령·시행령·시행규칙','37종','XML 본문 + 별표·서식 파일'],
   ['감독규정·시행세칙 등 행정규칙','12종','XML 본문 + 별표·첨부파일'],
   ['거래소 상장·공시규정 등','9종','전체 HTML + 전문·첨부 원본'],
   ['금투협 규정·모범규준 등','5종','전체 HTML + 전문·첨부 원본'],
   ['거래소 공개 기업실사 별첨','5종','게시판의 첨부 원본 파일']],[.42,.12,.46]),
  b('note','전체 명칭은 Excel 「수집대상68」 참조. 수동 반입 10종·금감원 작성기준/별지서식 2종은 자동 수집에서 제외합니다. 68종은 문서 종류 수이며, 첨부와 판본 수만큼 실제 파일·요청 수는 늘어납니다.'),
  b('heading','02  배치 타이밍  ·  운영 협의안'),
  table(['언제','수행 내용'],[
   ['매일 06:00 KST','주말 포함 현행·예정 판본 확인 → 바뀐 원문·첨부 수집'],
   ['매일 08:30 KST','성공·미완료·실패 및 마지막 정상 확인 시각 보고'],
   ['일요일 18:00 KST','전체 목록·원본 해시 대조 → 같은 URL의 파일 교체 확인']],[.30,.70]),
  b('note','최초 전체 적재는 별도 1회. 08:30은 상태 보고 시각이며 완료 보장 시각이 아닙니다. 일 1회 확인이므로 게시 직후 반영은 보장하지 않습니다.'),
  b('heading','03  저장과 납품'),
  table(['산출물','저장 위치'],[
   ['XML·HTML·HWP/HWPX·PDF·이미지','AIDP 원본 저장소 / Dataiku 관리 폴더'],
   ['구조화 데이터·온톨로지·위키','Oracle 골드 레이어'],
   ['LLM 질의·판단·실행 기록','에이전트 레이어']],[.44,.56]),
  b('callout','뭉타 납품: 수집 코드 + 주기 배치·실패 재개 + 원본·메타데이터 + AIDP 인계'),
  b('note','S3는 사용 승인·연결이 확보되면 선택합니다. 현재 확인한 연결은 SFTP 기반이며, 관리 폴더의 쓰기·다시 읽기를 먼저 검증해야 합니다. GENOS 코드서빙에 원문을 영구 보관하지 않습니다.'),
  b('source','읽는 순서: 2~3쪽 API → 4~5쪽 웹 수집 → 6쪽 운영·완료 조건. 전체 26개 요청 주소와 상세 파라미터는 Excel에 수록했습니다.')
 ],
 [
  b('eyebrow','API  |  법령 37종  |  요청 프로필 A1·A2'),
  b('title','법령 API: 목록에서 판본 선택'),
  b('lead','목록으로 대상 문서와 판본을 찾고, 그 판본의 본문을 받습니다. 목록 응답만 저장하면 원문 수집이 완료되지 않습니다.'),
  b('url','목록 GET  https://www.law.go.kr/DRF/lawSearch.do\n본문 GET  https://www.law.go.kr/DRF/lawService.do'),
  b('heading','공통값과 목록 조건'),
  table(['파라미터 · 적용','설명과 이번 요청값'],[
   ['OC · 필수','승인된 API 인증값. LAW_OC 같은 비밀 설정으로 주입하고 URL·오류 로그에서 가립니다. 중계서버의 접속 인증과는 별개입니다.'],
   ['target / type · 필수','법령은 target=eflaw, 반환은 type=XML. XML은 응답 본문이며 .xml 원본 파일로 저장합니다.'],
   ['search / query · 수집 기준','search=1로 문서명 검색. query는 목록의 정식명이며 UTF-8 URL 인코딩합니다. 결과의 정식명·법령ID를 대조해 유사명·시행령 혼입을 막습니다.'],
   ['nw · 수집 기준','nw=2,3으로 시행예정(2)과 현행(3)을 함께 확인합니다. 1은 연혁입니다. 예정 판본을 현행으로 덮어쓰지 않습니다.'],
   ['display / page · 수집 기준','display=100(최대), page=1부터 증가. totalCnt까지 전 페이지를 확인합니다. ID를 알면 목록의 LID로 대상 법령을 지정할 수 있습니다.']],[.27,.73]),
  b('heading','본문: 두 요청 방식 중 하나 선택'),
  table(['방식','필요값과 사용 조건'],[
   ['판본 고정 · 권장','MST=목록의 법령일련번호 + efYd=그 판본의 시행일(YYYYMMDD). 저장할 판본을 재현할 때 사용합니다.'],
   ['현행 단순 조회 · 대안','ID=법령ID. 이 방식은 현행 본문을 반환하며 MST·efYd는 생략합니다. 응답에서 실제 판본·시행일을 다시 확인합니다.'],
   ['JO · 선택','특정 조문만 조회하는 6자리 값. 예: 001002는 제10조의2. 이번 전체 문서 수집에서는 생략합니다.']],[.27,.73]),
  b('url','목록 예시  lawSearch.do?OC={LAW_OC}&target=eflaw&type=XML\n&search=1&query={정식명}&nw=2,3&display=100&page=1\n본문 예시  lawService.do?OC={LAW_OC}&target=eflaw&type=XML\n&MST={목록의_법령일련번호}&efYd={해당_시행일}'),
  b('note','예시는 조립 형식이며 중괄호를 실제 값으로 바꿉니다. query와 기타 값은 HTTP 라이브러리의 params로 전달합니다. 목록의 efYd는 날짜 범위, 본문의 efYd는 단일 시행일입니다.'),
  ref('공식 근거 S1 · 법령 목록 파라미터',guide+'lsEfYdListGuide'),
  ref('공식 근거 S2 · 법령 본문 파라미터',guide+'lsEfYdInfoGuide')
 ],
 [
  b('eyebrow','API  |  행정규칙 12종  |  요청 프로필 B1·B2·AB-F'),
  b('title','행정규칙 API와 첨부 조건'),
  b('lead','요청 주소와 OC·type은 법령과 같습니다. target을 admrul로 바꾸되, ID와 nw의 의미도 함께 바뀐다는 점에 주의합니다.'),
  b('heading','행정규칙의 요청값'),
  table(['파라미터 · 적용','설명과 이번 요청값'],[
   ['target · 필수','목록·본문 모두 target=admrul. type=XML을 지정합니다.'],
   ['목록 nw · 수집 기준','nw=1은 현행, nw=2는 연혁입니다. 법령의 nw=2(시행예정)를 복사하면 다른 범위를 수집하게 됩니다.'],
   ['목록 검색·페이지','search=1, query=정식명, display=100, page=1부터 끝까지. 소관기관·정식명도 함께 대조합니다.'],
   ['본문 ID · 권장','ID=목록에서 받은 행정규칙일련번호. 특정 판본을 지정하는 값입니다. 법령 본문의 ID=법령ID와 혼동하지 않습니다.'],
   ['본문 LID / LM · 대안','LID는 행정규칙ID, LM은 정확한 규칙명입니다. 이번 배치는 판본 추적을 위해 목록→ID 방식을 우선하고, 대안 조회 후에도 응답 판본을 검증합니다.']],[.27,.73]),
  b('url','목록 예시  https://www.law.go.kr/DRF/lawSearch.do\n?OC={LAW_OC}&target=admrul&type=XML&search=1\n&query={정식명}&nw=1&display=100&page=1\n본문 예시  https://www.law.go.kr/DRF/lawService.do\n?OC={LAW_OC}&target=admrul&type=XML&ID={행정규칙일련번호}'),
  b('heading','날짜 필터는 보조 조건으로 사용'),
  table(['필터','의미와 적용 조건'],[
   ['법령 목록 efYd / ancYd','각각 시행일 / 공포일 범위. 형식은 YYYYMMDD~YYYYMMDD입니다.'],
   ['행정규칙 prmlYd / modYd','각각 발령일 / 수정일 범위. 둘은 의미가 다르므로 동일 날짜로 취급하지 않습니다.'],
   ['기본 수집 방침','매일 대상 목록을 대조하고 날짜 필터는 보조로 사용합니다. 오늘 날짜만 조회하면 지연 게시·정정·첨부 교체를 놓칠 수 있습니다.']],[.31,.69]),
  b('heading','반환값과 첨부 저장'),
  b('callout','본문 XML + XML이 가리키는 별표·서식·첨부 파일을 각각 저장하고, 같은 문서 판본에 연결합니다.'),
  b('note','예: https://www.law.go.kr/LSW/flDownload.do?flSeq={응답값}. 경로·번호를 추측하지 않고 실제 응답 링크를 따릅니다. 원본 바이트를 보존하고 파일 형식·크기·SHA-256을 검사합니다. PDF/HWP 요청에 오류 HTML이 오면 실패입니다.'),
  b('note','공포일·발령일·개정일·시행일·수집 시각을 분리합니다. 시행일을 확인하지 못하면 null과 사유를 남깁니다. 공포본(target=law)은 별도 필요할 때만 추가하며 시행 기준 본문을 대신하지 않습니다.'),
  ref('공식 근거 S3 · 행정규칙 목록',guide+'admrulListGuide'),
  ref('공식 근거 S4 · 행정규칙 본문·첨부',guide+'admrulInfoGuide')
 ],
 [
  b('eyebrow','크롤링  |  거래소 규정 9종  |  요청 프로필 C1~C9'),
  b('title','거래소: 세션과 판본을 유지'),
  b('lead','규정 웹사이트의 HTML·내부 JSON·다운로드 파일을 함께 수집합니다. 아래 요청은 기존 수집 코드에서 확인한 경로로, 공식 공개 API 계약은 아닙니다.'),
  b('url','기준 주소  https://rule.krx.co.kr\n진입 GET  /out/index.do'),
  b('heading','요청 순서와 핵심 파라미터'),
  table(['단계 · 경로','입력·응답과 처리 조건'],[
   ['① 세션·목록 준비\n/out/regulation/\nregulationMain.do','POST form: Menucd=BYLAW, index=law_rule, gbn=out, _csrf. 진입 화면의 Cookie·CSRF를 같은 세션으로 이어갑니다.'],
   ['② 규정 트리\n/out/regulation/\ngetTreeNode.do','POST form: node=0부터 하위 노드 탐색, statecd=현행, mtype=htree. 정식 규정명으로 현재 bookid를 찾습니다.'],
   ['③ 해당 판본 HTML\n/out/regulation/\nregulationView.do','POST form: bookid, noformyn=노드 값(없으면 N), _csrf 등. 응답의 STATEHISTORYID를 판본 식별자로 확보합니다.'],
   ['④ 전문 파일 정보\n/web/regulation/\ndownloadRuleFile.do','POST form: bookid, statehistoryid, filecd. JUN=전문, GAE=개정문, SIN=신구대비표. 응답 fileMap의 실제 파일명을 사용합니다.'],
   ['⑤ 별표·서식 목록\n/web/regulation/\nregulationListData.do','목록 화면 선행 조회 후 POST form. start=0, limit=100; total까지 이동합니다. gbnid는 BYUL(별표)·BYULSEO(서식) 등 실제 분류, TITLE은 대상 규정명과 대조합니다.'],
   ['⑥ 파일 다운로드\n/login/getData.do\n→ /Download.do','POST로 새 다운로드 _csrf를 받고, Serverfile·Pcfilename·folder=ATTACH·_csrf를 POST form으로 전달해 바이너리를 받습니다.']],[.35,.65]),
  b('note','각 경로 앞에 기준 주소를 붙입니다. X-CSRF-TOKEN·Referer 등 헤더와 추가 고정 필드는 Excel 「요청주소26」에 있습니다. 토큰·Cookie·파일명을 코드에 고정하지 않습니다.'),
  b('heading','완료로 인정할 조건'),
  table(['확인점','판정 기준'],[
   ['같은 판본인가','본문의 bookid·statehistoryid와 전문·첨부의 연결 근거를 보존합니다. 수집 중 판본이 바뀌면 서로 섞지 않고 다시 확인합니다.'],
   ['내용이 보존됐는가','원본 HTML과 참조 이미지·파일을 보존합니다. 장·조·항·호, 표의 행·열 병합, 각주를 구조화 결과와 대조합니다. 텍스트만 추출하면 표 구조가 소실될 수 있습니다.'],
   ['진짜 파일인가','HTTP 200도 alert·로그인·오류 화면이면 실패입니다. 첨부 목록 조회 오류를 “첨부 없음”으로 기록하지 않습니다.']],[.25,.75]),
  b('source','근거: 기존 KRX 수집 코드·확보 기록. 현행 사이트 동작·이용 조건은 착수 시 재확인합니다. HTML 구조화 품질과 운영 수집 성공은 별도 검증 대상입니다.')
 ],
 [
  b('eyebrow','크롤링  |  금투협 5종 + 거래소 공개 별첨 5종  |  D1~D9·E1~E2'),
  b('title','금투협·공개 별첨의 요청 조건'),
  b('heading','금투협: seq가 어느 ID인지 구분'),
  b('url','기준 주소  https://law.kofia.or.kr\n진입 GET  /service/law/lawCurrentPartTree.do'),
  table(['요청 · 경로','파라미터와 의미'],[
   ['현행 판본 찾기\nGET /service/law/lawView.do','seq=규정ID, historySeq=0, gubun=cur, tree=part. 0은 현행 탐색에 사용하고 응답에서 실제 historySeq를 확보합니다.'],
   ['본문 HTML\nGET /service/law/\nlawFullScreenContent.do','seq=규정ID, historySeq=확보한 판본ID. 두 값을 함께 보존하고 본문·부칙·표·첨부 링크를 받습니다.'],
   ['전문 파일\nGET /download.do','gubun=101, seq=historySeq. 이때 seq는 규정ID가 아니라 판본ID입니다.'],
   ['별표·서식 파일\nGET /download.do','gubun=102, seq=본문에서 얻은 첨부ID. 전문 파일의 seq를 재사용하지 않습니다.'],
   ['개정문·신구대비표\nGET /download.do','개정 상세 버튼의 gubun=104(개정문) 또는 105(대비표), seq=그 버튼의 파일ID. 과거 대비표는 해당 과거 판본에 연결합니다.']],[.40,.60]),
  b('note','규정 정식명→seq 매핑을 재확인합니다. revisionInfo.do의 개정일을 시행일로 복사하지 않습니다. 공개 원문은 HTTP 수집을 우선하며 화면 실행이 필요한 구간만 Selenium을 사용합니다.'),
  b('heading','거래소 공개 기업실사 별첨: 게시판 → 파일'),
  b('url','게시판  https://listing.krx.co.kr/board/LST09000000/bbs\n파일  https://file.krx.co.kr/download.jspx'),
  table(['항목','설명과 확인 조건'],[
   ['bbsId / bbsSeq','게시판 / 게시물 식별자. 기존 확보값은 LST09000000 / 291입니다. 최신 게시물 번호로 고정해서는 안 됩니다.'],
   ['attachFileSeq','게시물 안의 첨부 식별자. 기존 확보값 1~5는 과거 기록이며, 현재 버튼의 파일명·첨부 연결을 다시 확인합니다.'],
   ['filetype / url','기존 요청값 att / COM/board_attach_down. HTTP GET·POST 방식과 현재 필수 필드는 실제 다운로드 버튼 요청으로 확인합니다.'],
   ['최신 게시물 탐색','목록의 실제 XHR·페이지 이동 규약은 미확인입니다. #view=291은 화면 fragment이며 서버로 보내는 query 값이 아닙니다.']],[.28,.72]),
  b('callout','공개 별첨은 최신 게시물 발견 → 첨부 목록 확인 → 5종 매핑까지 검증해야 자동 수집 완료입니다. 과거 URL 다운로드 성공만으로 최신성 확인을 대신할 수 없습니다.'),
  b('source','근거: 기존 금투협 수집 코드 / 2026-09-17 공개 별첨 원본 기록. 이 경로들은 웹 내부 요청이며, 사이트 변경 시 보수가 필요합니다. 대상 외 문서는 자동으로 추가하지 않습니다.')
 ],
 [
  b('eyebrow','공통 운영  |  제안값은 뭉타·AIDP·원천 제공기관과 최종 확정'),
  b('title','운영 조건과 AIDP 인계 기준'),
  b('heading','접속·재시도·중계 조건'),
  table(['항목','요청 조건 · 수치가 있는 항목은 운영 제안'],[
   ['호출 간격·실행 한도','동시 1개, 요청 시작 간 최소 1초. 제공기관 한도가 더 엄격하면 우선 적용합니다. 일일 배치 한도는 120분, 최초 적재는 별도 산정합니다.'],
   ['일시 오류 재시도','연결 10초·응답 대기 60초. 타임아웃·429·503 등은 최초 포함 최대 4회. Retry-After 우선, 없으면 2·8·32초에 소폭 분산해 재시도합니다. 재개해도 횟수를 초기화하지 않습니다.'],
   ['재시도하지 않을 오류','키·권한 오류는 설정 확인, 캡차·차단은 중단·담당자 통보. CSRF 만료가 확인되면 같은 총 한도 안에서 1회 갱신합니다. 요청 경로 변경은 실패 원인과 함께 보수 대상으로 남깁니다.'],
   ['중계서버 전달 계약','GET query·POST form·필요 헤더·세션 Cookie, 원본 상태 코드·Content-Type·파일 응답을 지원해야 합니다. 큰 파일은 스트리밍하고 키·토큰은 로그에서 가립니다.'],
   ['허용 범위 확인','대상 호스트의 이용약관·robots 정책·제공기관 제한을 확인합니다. 위 간격은 사이트가 승인한 값이라는 뜻이 아닙니다.']],[.26,.74]),
  b('heading','원본마다 함께 넘길 메타데이터'),
  table(['묶음','필드와 의미'],[
   ['출처·판본','run_id, source, document_id, version_id, title, source_url(비밀값 제거). 재현 가능한 요청 방식·공개 파라미터도 함께 기록합니다.'],
   ['날짜·원본','공포/발령일·개정일·시행일·collected_at(KST 또는 UTC 표기), 파일 역할(본문/전문/첨부), 형식·크기·sha256·storage_uri. 미확보 값은 null과 사유를 남깁니다.'],
   ['연결·진행 상태','본문 판본→첨부 연결, 예상/확보 파일 수, status·error_code·시도 횟수·마지막 정상 확인 시각. 파일 교체 시 새 해시·판본 기록을 만들고 원본을 덮어쓰지 않습니다.']],[.26,.74]),
  b('heading','완료 판정과 재개'),
  b('note','COLLECTED: 필수 원본·첨부 저장 후 다시 읽기·해시 검증 완료. UNCHANGED: 확인 성공·기존과 동일. PARTIAL: 일부 파일 미확보. FAILED/BLOCKED: 장애/차단으로 확인 실패. 변경 없는 상태와 확인 실패를 구분합니다.'),
  b('note','문서 판본별 완료 표시 이후에 구조화·Oracle 적재를 시작합니다. 재개 시 성공 파일을 재사용하고 중복 적재를 막습니다. 실패한 새 판본은 미완료로 남기며, 이전 정상 판본은 마지막 확인 시각과 함께 유지합니다.'),
  b('confirm','착수 전 확정: ① OC 승인·중계 인증/허용 호스트  ② AIDP 폴더·권한·용량\n③ 웹 이용 조건·공개 별첨 탐색 요청  ④ 뭉타 수집/AIDP 적재의 담당 경계'),
  b('note','인수 확인: 최초 68종 대조, 변경·무변경·첨부 누락·토큰 만료·재개·중복 실행·저장 실패 시나리오를 기록합니다. 일부 문서 실패가 다른 문서의 정상 완료를 취소하지 않도록 합니다.'),
  b('source','문서·설계 보강 V3. 실제 수집 실행·운영 배포 완료를 의미하지 않습니다. API 공식 근거·웹 확인 출처는 Excel 「출처」, 필수·선택·대체 조건은 「파라미터설명」을 참조합니다.')
 ]
]

# Vendor-editable parameter dictionary. Requirement distinguishes provider-required
# fields from values selected for this collection request.
params=[]
def p(group,request,name,required,value,meaning,caution):
    params.append([group,request,name,required,value,meaning,caution])
p('법제처 공통','A1~B2','OC','API 필수','{LAW_OC}','신청·승인된 API 인증값','실제 키는 비밀 설정. URL·로그에서 마스킹. 중계 인증은 별도.')
p('법제처 공통','A1~B2','type','API 필수 명시','XML','응답 형식을 XML로 통일','바이너리 첨부는 이 값으로 XML로 변환되지 않음.')
p('목록 공통','A1·B1','search / query','수집 기준','1 / 정식 문서명','문서명 검색; HTTP params로 UTF-8 인코딩','검색 결과는 정식명·기관·ID로 대조. 유사 문서 제외.')
p('목록 공통','A1·B1','display / page','수집 기준','100 / 1부터','한 페이지 최대 100건, totalCnt까지 순회','응답 페이지·건수 검증. 중간 페이지 실패는 완료 아님.')
p('법령 목록','A1','target','API 필수','eflaw','시행일 기준 법령 조회','공포 기준 law와 구분.')
p('법령 목록','A1','nw','수집 기준','2,3','1=연혁 / 2=시행예정 / 3=현행','생략 기본값 전체. 예정은 현행으로 자동 전환하지 않음.')
p('법령 목록','A1','LID','선택','{법령ID}','확정한 법령 식별자로 목록 조회','MST인 법령일련번호와 다름.')
p('법령 목록','A1','efYd / ancYd','선택·보조','YYYYMMDD~YYYYMMDD','각각 시행일 / 공포일 범위','일일 수집을 오늘 날짜만으로 제한하지 않음.')
p('법령 본문','A2','MST + efYd','판본 고정 방식 필수','{법령일련번호} / YYYYMMDD','목록에서 선택한 판본과 해당 시행일','ID 방식과 섞지 않음. 본문 efYd는 범위가 아님.')
p('법령 본문','A2','ID','현행 조회 대안','{법령ID}','현행 본문 조회','MST·efYd 생략. 응답에서 실제 판본 확인.')
p('법령 본문','A2','JO','선택·이번에는 생략','001002','제10조의2처럼 특정 조문 조회','6자리 문자열로 선행 0 유지. 생략하면 전체 조문.')
p('법령 본문','A2','chrClsCd','선택','010202','한글; 010201은 원문','생략 기본은 한글. 반환 텍스트를 임의 수정하지 않음.')
p('공포본','A3','target / MST','별도 필요 시','law / {법령일련번호}','공포 기준 본문 확보','시행 기준 eflaw를 대체하지 않음.')
p('행정규칙','B1·B2','target','API 필수','admrul','행정규칙 대상','법령 target 값 복사 금지.')
p('행정규칙 목록','B1','nw','수집 기준','1','1=현행 / 2=연혁','법령 nw와 의미가 다름. 2는 시행예정이 아님.')
p('행정규칙 목록','B1','prmlYd / modYd','선택·보조','YYYYMMDD~YYYYMMDD','발령일 / 수정일 범위','현행 목록 대조를 보완하는 필터로 사용.')
p('행정규칙 본문','B2','ID','판본 고정 방식 필수','{행정규칙일련번호}','목록에서 받은 특정 판본 번호','법령 ID와 의미가 다름.')
p('행정규칙 본문','B2','LID / LM','대안 조회','{행정규칙ID} / 정확한 명칭','문서 식별자 또는 정확한 규칙명 조회','기본 배치는 목록→ID. 반환 판본 확인.')
p('법제처 첨부','AB-F','파일 링크·flSeq 등','응답 링크에 따름','{XML의 실제 파일 링크}','별표·서식·첨부 바이너리','주소·번호 추정 금지. 승인된 원천/리디렉션 범위 확인.')
p('KRX 세션','C1~C9','Cookie / _csrf','해당 요청 필수','같은 세션에서 취득','화면·XHR·다운로드 세션 연결','토큰을 코드·납품 자료·로그에 기록하지 않음.')
p('KRX 화면','C2','Menucd / index / gbn','기존 경로 기준','BYLAW / law_rule / out','규정 화면 초기화','POST form + _csrf. 현행 화면 동작 재확인.')
p('KRX 트리','C3','node / statecd','기존 경로 기준','0 및 하위노드 / 현행','현재 규정 트리를 순회','응답의 정식명으로 현재 bookid 찾기.')
p('KRX 트리','C3','mtype / Menucd / webgbn / gbnid / gbn2','기존 경로 기준','htree / BYLAW / OUT / 0 / out','트리 조회 고정값','X-CSRF-TOKEN 헤더 등 현재 요청 재확인.')
p('KRX 본문','C4','bookid / noformyn','기존 경로 기준','{트리값} / {노드값, 없으면 N}','규정 본문 선택','bookid 영구 고정 금지. 응답 STATEHISTORYID 보존.')
p('KRX 본문','C4','gbnid / mtype / searchForm / Menucd','기존 경로 기준','0 / htree / 빈값 / BYLAW','본문 화면 보조값','POST form, 같은 세션의 _csrf.')
p('KRX 전문','C5','bookid / statehistoryid','기존 경로 기준','{규정값} / {응답 판본값}','파일과 본문 판본 연결','조회 전후 판본이 바뀌면 묶음 재확인.')
p('KRX 전문','C5','filecd','수집할 파일별 지정','JUN / GAE / SIN','전문 / 개정문 / 신구대비표','없는 파일과 조회 실패 구분. fileMap의 실제 파일값 사용.')
p('KRX 첨부 준비','C6','Menucd / mtype / gbnid / smType / index / gbn','기존 경로 기준','BYLAW / byul / BYUL / byul / law_rule / out','별표·서식 목록 화면 초기화','목록 데이터 조회에 앞서 POST form + _csrf.')
p('KRX 첨부 목록','C7','start / limit','수집 기준','0부터 / 100','오프셋 페이지 이동, total까지 확인','0·100·200… 요청. 오류를 첨부 0건으로 취급하지 않음.')
p('KRX 첨부 목록','C7','gbnid / stit','기존 경로 기준','BYUL 또는 BYULSEO 등 / 규정','별표·서식 등 분류와 검색 기준','분류별 실제 결과 확인. TITLE 정식명 대조.')
p('KRX 첨부 목록','C7','mtype / Menucd / gbn2','기존 경로 기준','byul / BYLAW / out','목록 조회 보조값','X-CSRF-TOKEN·X-Requested-With·Referer 확인.')
p('KRX 토큰 갱신','C8','_csrf / X-CSRF-TOKEN','기존 경로 기준','현재 토큰','다운로드용 data._csrf 취득','다운로드 전에 새 토큰 사용. 만료 복구도 총 재시도 한도 내.')
p('KRX 다운로드','C9','Serverfile / Pcfilename / folder / _csrf','기존 경로 기준','{fileMap 값} / {fileMap 값} / ATTACH / {새 토큰}','파일 바이너리 요청','응답 필드 SERVERFILE·PCFILENAME을 요청 이름에 맞게 매핑. Referer 규정 상세.')
p('금투협 현행','D2','seq / historySeq / gubun / tree','기존 경로 기준','{규정ID} / 0 / cur / part','현재 판본을 탐색','응답의 실제 historySeq를 이후 요청에 사용.')
p('금투협 본문','D3','seq / historySeq','기존 경로 기준','{규정ID} / {판본ID}','정확한 판본 HTML 조회','규정 ID와 판본 ID 분리 저장.')
p('금투협 전문','D4','gubun / seq','기존 경로 기준','101 / {historySeq}','전문 원본 파일','여기서 seq는 규정ID가 아님.')
p('금투협 첨부','D5','gubun / seq','응답 링크에 따름','102 / {첨부ID}','별표·서식 원본','본문 실제 링크의 ID 사용.')
p('금투협 개정정보','D6','historySeq','기존 경로 기준','{판본ID}','개정 정보 확인','개정일을 시행일로 임의 복사하지 않음.')
p('금투협 개정목록','D7','page / searchValue','필요 이력 조회','1부터 / 정식 규정명','개정 이력 목록','POST form. 필요한 이력 범위까지 순회.')
p('금투협 개정상세','D8','historySeq','필요 이력 조회','{개정 판본ID}','실제 개정문·대비표 링크 확보','현재 규정과 과거 파일 연결 관계 구분.')
p('금투협 개정파일','D9','gubun / seq','응답 링크에 따름','104 또는 105 / {버튼 파일ID}','개정문 / 신구대비표','본문·첨부의 seq를 무조건 재사용하지 않음.')
p('KRX 공개 별첨','E1','목록 XHR·페이지·#view','미확인·착수 확인','과거 화면 #view=291','현재 게시물 탐색 요청을 확인해야 함','fragment는 서버 파라미터가 아님. 최신 탐색 구현 완료로 간주하지 않음.')
p('KRX 공개 별첨','E2','bbsId / bbsSeq / attachFileSeq','과거 기록·착수 확인','LST09000000 / 291 / 1~5','게시판 / 게시물 / 첨부 식별자','현재 파일명·게시물·첨부에 재매핑. 291을 최신으로 고정 금지.')
p('KRX 공개 별첨','E2','filetype / url / HTTP method','과거 기록·착수 확인','att / COM/board_attach_down / 미확인','기존 다운로드 요청값','현행 버튼에서 GET/POST 및 필수값 확인.')

(OUT/'SUMMARY_CONTENT.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
(OUT/'PARAMETERS.json').write_text(json.dumps(params,ensure_ascii=False,indent=2)+'\n')
print(f'pages={len(pages)}, parameter_rows={len(params)}')
