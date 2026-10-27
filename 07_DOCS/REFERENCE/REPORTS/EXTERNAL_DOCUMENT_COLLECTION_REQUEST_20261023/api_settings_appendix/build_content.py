"""Appendix to the API-URL email: selected scope and requested refresh settings."""
from pathlib import Path
from urllib.parse import urlencode,quote
from html import escape
import json,hashlib

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
inventory=json.loads((ROOT/'DOCUMENT_INVENTORY.json').read_text())
targets=[r for r in inventory if r['group'] in ['A','B']]
laws=[r for r in targets if r['group']=='A'];rules=[r for r in targets if r['group']=='B']
assert len(laws)==37 and len(rules)==12 and len({r['name'] for r in targets})==49
LIST='https://www.law.go.kr/DRF/lawSearch.do'
BODY='https://www.law.go.kr/DRF/lawService.do'
def b(k,t):return {'kind':k,'text':t}
def tab(h,rs,w):return {'kind':'table','headers':h,'rows':rs,'widths':w}
def ref(t,u):return {'kind':'source','text':t,'href':u}
G='https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName='

settings=[
 ['대상 범위','기존 설정의 API 대상 49종만','법령 37종 + 행정규칙 12종. 하위 법령·유사 문서는 자동 추가하지 않음.'],
 ['매일 최신화','매일 06:00 · Asia/Seoul','주말 포함. 대상별 목록·판본·본문·첨부 변경을 확인하는 요청 기본값.'],
 ['상태 보고','매일 08:30 · Asia/Seoul','성공·변경 없음·미완료·실패·마지막 정상 확인 시각. 완료 보장 시각은 아님.'],
 ['전체 재대조','매주 일요일 18:00 · Asia/Seoul','일일 확인과 별도로 49종 누락·원본/첨부 해시·미완료를 재대조.'],
 ['최초 수집','대상 전량 1회','수집할 현행·시행예정 판본과 본문·첨부를 확보하고 기준 메타데이터 생성.'],
 ['법령 범위','target=eflaw / nw=2,3','현행(3)과 시행예정(2)을 구분 저장. 예정 판본으로 현행을 덮어쓰지 않음.'],
 ['행정규칙 범위','target=admrul / nw=1','현행 목록. 응답의 시행일·현행여부도 확인. nw=2는 연혁이므로 이번 기본값에서 제외.'],
 ['검색 범위','search=1 / query=정식명','대상 표의 이름을 그대로 query에 넣고 응답 명칭·종류·문서ID를 대조.'],
 ['페이지 처리','display=100 / page=1부터','모든 페이지를 totalCnt까지 확인. 한 페이지만 받고 완료 처리하지 않음.'],
 ['날짜 필터','기본 생략','목록의 efYd·ancYd·prmlYd·modYd 등으로 오늘 날짜만 제한하지 않음. 본문 efYd는 필수 매핑값.'],
 ['ID 관리','목록 응답에서 매회 판본 확보','문서ID와 판본 일련번호를 분리. 과거 MST·행정규칙일련번호·시행일을 고정하지 않음.'],
 ['동일 ID/URL 정정','매일 본문·첨부 변경 확인','지원이 확인된 조건부 요청은 기존 파일에 연결해 재사용; 미지원은 수신 후 SHA-256 비교.'],
 ['저장·재처리','변경된 산출물만 신규 저장·갱신','원본·첨부·판본 연결·해시 보존. 변경 없으면 확인 시각만 갱신. 과거 판본 삭제 금지.'],
 ['장애 처리','부분 성공·실패를 분리','본문/첨부 미확보는 완료 아님. 기존 정상 자료와 확인 시각 유지, 성공 파일 재사용 후 재개.'],
 ['문서 미검색','오류·개칭·폐지 여부 확인','0건을 변경 없음으로 처리하지 않음. 기존 문서를 삭제하지 않고 확인 필요로 보고.'],
 ['호출 부하','동시 1개 / 최소 간격 1초','제공기관 제한을 우선 적용. 재시도·한도·재개는 V4 공통 운영 조건 준수.'],
 ['실행 상태','구현 요청 설정','배치 배포·스케줄 등록·API 호출 성공을 의미하지 않음. 실제 키·중계 내부 주소는 별도 설정.']
]
request_rows=[
 ['법령 목록',LIST,'OC={LAW_OC}&target=eflaw&type=XML&search=1&query={표의 법령명}&nw=2,3&display=100&page={PAGE}','각 대상마다 page=1부터 totalCnt까지. 오늘 날짜 필터 없음.'],
 ['행정규칙 목록',LIST,'OC={LAW_OC}&target=admrul&type=XML&search=1&query={표의 행정규칙명}&nw=1&display=100&page={PAGE}','법령의 nw 값을 복사하지 않음.'],
 ['법령 본문',BODY,'OC={LAW_OC}&target=eflaw&type=XML&MST={목록의 법령일련번호}&efYd={그 판본 시행일 YYYYMMDD}','고정 숫자 없이 목록 응답에서 매핑. JO 생략으로 전체 조문 수집.'],
 ['행정규칙 본문',BODY,'OC={LAW_OC}&target=admrul&type=XML&ID={목록의 행정규칙일련번호}','행정규칙 본문의 ID는 판본 일련번호. 법령의 문서ID와 의미가 다름.'],
 ['별표·서식·첨부','본문 XML이 반환한 실제 파일 URL','응답 링크의 파일 파라미터 그대로 사용','대표: https://www.law.go.kr/LSW/flDownload.do?flSeq={응답값}; 다른 링크도 확인.']
]
combined=[]
for i in range(19):
 left=laws[i];right=laws[i+19] if i+19<len(laws) else None
 combined.append([left['id'],left['name'],right['id'] if right else '',right['name'] if right else ''])

pages=[[
 b('eyebrow','API URL 안내 보완 부록 A  |  2026.10.23  |  뭉타 전달용'),
 b('title','우리 대상 49종, 매일 최신화'),
 b('lead','아래 목록에 등록한 문서만 정기 확인합니다. 고정된 과거 ID로 반복 다운로드하는 방식이 아니라, 매 배치에서 해당 문서의 현행·예정 판본을 다시 찾습니다.'),
 b('heading','A-1  우리가 원하는 운영 설정'),
 tab(['항목','요청 기본값'],[
  ['대상','법령 37종 + 행정규칙 12종. 전체 명칭은 2~3쪽.'],
  ['주기','매일 06:00 KST · 주말 포함 / 08:30 상태 보고'],
  ['최초·주간','최초 전체 수집 1회 / 일요일 18:00 전체 누락·해시 재대조'],
  ['수집 결과','XML 전문 + 별표·서식·첨부 원본 + 문서·판본·시행일·해시'],
  ['매일 변경 확인','본문·첨부도 확인. 같은 ID·URL이어도 정정·파일 교체를 확인하고 변경분만 신규 저장·후속 갱신.']],[.24,.76]),
 b('note','시각은 구현 요청 기본값입니다. 실제 배치 등록·운영 적용은 별도입니다. 이 부록의 일일 본문·첨부 확인 기준을 앞선 V4의 주간 재대조 설명보다 우선 적용합니다.'),
 b('heading','A-2  API 주소와 고정·변동 파라미터'),
 b('url','목록 GET  '+LIST+'\n본문 GET  '+BODY),
 b('note','공통: OC={LAW_OC}, type=XML. 목록 공통: search=1, query=다음 표의 정식명, display=100, page=1부터 끝까지. query 값은 HTTP 라이브러리로 UTF-8 인코딩합니다.'),
 tab(['요청','추가로 넣을 값'],[
  ['법령 목록','target=eflaw / nw=2,3 → 현행·시행예정 구분'],
  ['행정규칙 목록','target=admrul / nw=1 → 현행'],
  ['법령 본문','target=eflaw / MST=목록의 법령일련번호 / efYd=그 판본 시행일(YYYYMMDD)'],
  ['행정규칙 본문','target=admrul / ID=목록의 행정규칙일련번호'],
  ['첨부','본문 XML의 실제 링크·파일 식별자를 사용. 대표 경로: https://www.law.go.kr/LSW/flDownload.do?flSeq={응답값}']],[.24,.76]),
 b('callout','고정: 대상 문서명·target·nw·출력 형식·배치 주기\n매회 갱신: 실제 판본 일련번호·시행일·첨부 링크·파일 해시'),
 b('note','목록 날짜 필터는 기본 생략합니다. 오늘 공포/발령된 문서만 조회하면 지연 게시·정정을 놓칠 수 있습니다. 본문 요청의 efYd는 생략 대상이 아닙니다.'),
 ref('공식 근거: 법령 목록',G+'lsEfYdListGuide'),ref('공식 근거: 법령 본문',G+'lsEfYdInfoGuide')
],[
 b('eyebrow','부록 A-3  |  법령 37종  |  전체 행에 동일한 목록 프로필 적용'),
 b('title','법령 목록: 이 이름을 query에 입력'),
 b('lead','관리번호 A01~A37은 우리 목록의 번호이며 API에 넣을 ID가 아닙니다. 이름으로 찾은 결과에서 실제 법령ID·판본 일련번호를 확인합니다.'),
 b('url','공통 목록값: target=eflaw · nw=2,3 · search=1 · type=XML\nOC={LAW_OC} · query={아래 정식명} · display=100 · page=1부터 끝까지'),
 tab(['번호','query 값 · 정식 법령명','번호','query 값 · 정식 법령명'],combined,[.08,.42,.08,.42]),
 b('note','예: A03의 query=자본시장과 금융투자업에 관한 법률. A04·A05는 각각 별도 문서로 조회합니다. 검색 결과에 나오는 유사명·시행령·시행규칙을 자동으로 모두 추가하지 않습니다.'),
 b('note','검증한 문서ID는 문서 식별에 재사용할 수 있지만, 수집 판본의 MST·efYd는 매회 확인합니다. 현재 자료에 남은 과거 일련번호·시행일은 최신화 고정값으로 전달하지 않습니다.')
],[
 b('eyebrow','부록 A-4  |  행정규칙 12종  |  전체 행에 동일한 목록 프로필 적용'),
 b('title','행정규칙 목록과 갱신 판정'),
 b('url','공통 목록값: target=admrul · nw=1 · search=1 · type=XML\nOC={LAW_OC} · query={아래 정식명} · display=100 · page=1부터 끝까지'),
 tab(['번호','query 값 · 정식 행정규칙명'],[[r['id'],r['name']] for r in rules],[.12,.88]),
 b('note','B01~B12도 내부 관리번호입니다. 본문 요청 ID에는 매 배치 목록에서 받은 “행정규칙일련번호”를 넣습니다. nw=2는 시행예정이 아니라 연혁입니다.'),
 b('heading','A-5  한 번의 최신화가 끝나는 조건'),
 tab(['단계','처리 기준'],[
  ['① 대상·판본 확인','49종을 순회하고 전 페이지의 명칭·종류·문서ID를 대조합니다. 검색 0건·개칭·폐지 의심은 확인 필요로 남깁니다.'],
  ['② 원문·첨부 대조','새 판본뿐 아니라 같은 판본의 정정도 확인합니다. 조건부 요청을 지원하면 검증된 기존 파일과 연결하고, 미지원이면 수신 후 SHA-256을 비교합니다.'],
  ['③ 변경분 반영','문서 메타·시행 상태·본문·첨부 중 변경된 부분을 갱신합니다. 현행과 시행예정을 분리하고, 예정→현행 전환도 다시 확인합니다.'],
  ['④ 완료·실패 보고','필수 원본·첨부 저장·해시 검증 후 문서별 완료. 변경 없으면 정상 확인 시각 갱신, 누락은 부분 성공/실패로 보고하고 성공 파일부터 재사용합니다.']],[.24,.76]),
 b('note','원본·메타데이터는 AIDP 저장소에 인계하며 과거 판본을 보존합니다. 문서 실패를 변경 없음으로 처리하지 않습니다. 이 부록은 API 49종의 설정이며 크롤링 19종의 기존 범위는 변경하지 않습니다.'),
 ref('공식 근거: 행정규칙 목록',G+'admrulListGuide'),ref('공식 근거: 행정규칙 본문·첨부',G+'admrulInfoGuide')
]]

request_targets=[]
for r in targets:
 params={'OC':'{LAW_OC}','target':'eflaw' if r['group']=='A' else 'admrul','type':'XML','search':'1','query':r['name'],'nw':'2,3' if r['group']=='A' else '1','display':'100','page':'{PAGE}'}
 readable='&'.join(k+'='+v for k,v in params.items())
 assert readable==r['request_parameters'],r['id']
 encoded=urlencode(params,quote_via=quote,safe='{},')
 request_targets.append({'management_id':r['id'],'query':r['name'],'group':r['group'],'list_url':LIST,'list_params':params,'readable_query':readable,'encoded_url_template':LIST+'?'+encoded,'body_url':BODY,'version_binding':'MST←법령일련번호; efYd←해당 판본 시행일' if r['group']=='A' else 'ID←행정규칙일련번호'})
config={'schema':'external-api-refresh-request-v1','state':'specification_only_not_deployed','scope_count':49,'timezone':'Asia/Seoul','daily_start':'06:00','daily_status':'08:30','weekly_reconcile':'Sunday 18:00','history_backfill':False,'daily_body_and_attachment_change_check':True,'date_filters_default':None,'credential_reference':'LAW_OC','targets':request_targets}
(OUT/'SUMMARY_CONTENT.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
(OUT/'REQUEST_SETTINGS.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
(OUT/'SETTINGS_ROWS.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
(OUT/'REQUEST_ROWS.json').write_text(json.dumps(request_rows,ensure_ascii=False,indent=2)+'\n')
print('Prepared 3-page appendix with exact 37+12 names, query templates and refresh settings')
