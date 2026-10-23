"""Add two request/response diagrams to the delivered V3 without overwriting it."""
from pathlib import Path
import json
from copy import deepcopy

OUT=Path(__file__).resolve().parent
PREVIOUS=OUT.parent/'summary_v3'
pages=deepcopy(json.loads((PREVIOUS/'SUMMARY_CONTENT.json').read_text()))
def b(kind,text):return {'kind':kind,'text':text}
pages[0][0]['text']='뭉타 전달용  |  2026.10.23  |  V4 · 수집 프로세스 다이어그램 추가'
pages[0][-1]['text']='읽는 순서: 2~3쪽 프로세스 → 4~5쪽 API → 6~7쪽 웹 수집 → 8쪽 운영·완료 조건. 전체 26개 요청 주소와 상세 파라미터는 Excel에 있습니다.'
pages[-1][-1]['text']=pages[-1][-1]['text'].replace('문서·설계 보강 V3.','프로세스 도식 추가 V4.')
api=[
 b('eyebrow','프로세스 01  |  목록 응답의 값을 다음 API 요청에 넣는 순서'),
 b('title','API: ID를 받은 뒤 본문 요청'),
 b('lead','문서명을 검색해 대상 판본을 고른 다음, 응답에서 받은 번호·시행일로 본문을 요청합니다. 화살표는 다음 단계에 전달하는 값입니다.'),
 {'kind':'diagram','name':'api_flow','caption':'그림 1. 법령·행정규칙의 목록 → 판본 선택 → 본문 → 첨부 → 저장'},
 b('note','공통 OC·type=XML은 모든 목록·본문 요청에 포함합니다. 법령 본문의 MST는 “법령일련번호”, 행정규칙 본문의 ID는 “행정규칙일련번호”입니다. 이름이 비슷해도 서로 바꾸어 쓰지 않습니다.'),
 b('note','매 배치에서 목록과 판본을 다시 확인합니다. 검증된 기존 판본과 같으면 성공 파일을 재사용하고, 새 판본이면 본문·첨부를 받습니다. 같은 URL의 파일 교체는 정기 해시 대조로 확인합니다.'),
 b('source','판본 고정 수집의 목표 흐름입니다. 현행 단순 조회 대안(ID=법령ID)과 상세 파라미터는 4~5쪽을 참조합니다. 실제 운영 수집 완료를 뜻하지 않습니다.')
]
web=[
 b('eyebrow','프로세스 02  |  웹 응답에서 문서·판본·파일 ID를 이어 받기'),
 b('title','크롤링: 화면 → ID → 파일'),
 b('lead','같은 수집 세션에서 조회 결과를 이어 사용합니다. 거래소·금투협·공개 별첨은 ID와 다운로드 방식이 달라 각각의 흐름으로 처리합니다.'),
 {'kind':'diagram','name':'web_flow','caption':'그림 2. 원천별 문서·판본·첨부 ID 전달과 파일 다운로드'},
 b('note','거래소의 statehistoryid는 상세 응답의 STATEHISTORYID입니다. 금투협은 전문 요청의 seq에 판본ID를, 별표 요청의 seq에 첨부ID를 넣습니다. ID나 Cookie·CSRF를 과거 값으로 고정하지 않습니다.'),
 b('source','주황색 공개 별첨 흐름은 구현 목표이며 최신 목록 탐색·GET/POST는 착수 시 확인해야 합니다. 거래소·금투협의 추가 필드·요청 주소는 6~7쪽과 Excel을 참조합니다.')
]
pages=pages[:1]+[api,web]+pages[1:]
(OUT/'SUMMARY_CONTENT.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
(OUT/'PARAMETERS.json').write_bytes((PREVIOUS/'PARAMETERS.json').read_bytes())
print(f'{len(pages)} pages; diagrams inserted at pages 2 and 3')
