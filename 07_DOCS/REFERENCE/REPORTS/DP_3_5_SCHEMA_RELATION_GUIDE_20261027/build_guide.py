from pathlib import Path
from html import escape
import json, hashlib, yaml
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path('/home/jin/8-AGENT')
OUT = Path(__file__).parent
STEM = 'DP_3_5_Schema_Relationship_Guide_20261027'
MAPPING = ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1/physical_mapping.yaml'
mapping = yaml.safe_load(MAPPING.read_text())
NAVY, BLUE, TEAL = '#17324D', '#245F9B', '#087F8C'
GREY, LIGHT = '#536577', '#F0F5F9'
pages = []

def page(title, subtitle):
    p = {'title':title, 'subtitle':subtitle, 'blocks':[]}; pages.append(p); return p
def text(p, value, kind='p'): p['blocks'].append({'type':kind,'text':value})
def table(p, headers, rows, widths=None): p['blocks'].append({'type':'table','headers':headers,'rows':rows,'widths':widths})
def flow(p, lines): text(p, '\n↓\n'.join(lines), 'flow')

p=page('DP 구조와 질문 처리 흐름', '3·5번 과제 공통 법규 RAG | 핵심 스키마·연결 탐색 설명서')
text(p,'한 질문이 용어·정의에서 출발해 관련 조항을 찾고, 명시 참조 또는 검토 관계를 따라 실제 원문을 확보하는 구조를 설명합니다. 핵심 데이터는 4개 물리 테이블이며, 버전 선택·상태·보관을 포함한 개발 스키마는 9개입니다.','lead')
text(p,'01  전체 흐름','h')
flow(p,['질문 + 인증된 문서 접근권한','검색 게시 버전·원문 데이터 세대 고정','용어·정의·본문 검색 → 내규 원문 읽기','명시 참조 / 검토 관계 → 연결 외규 원문 읽기','추가 연결 확인 → 인용·해석·미확인 사항을 함께 응답'])
text(p,'02  핵심 테이블의 역할','h')
table(p,['물리 테이블','저장 단위','질문 처리에서 하는 일'],[
['LGL_DOC_VER','세대 내 문서 1건','문서명·문서 식별값·원본 해시 확인'],
['LGL_DOC_UNIT','문서 구조 단위 1건','장·절·조·항·호·목과 상위 구조·본문 범위 확인'],
['LGL_DOC_BLK','본문 블록 1건','답변 인용에 사용할 실제 원문 조회'],
['LGL_SRCH_ROW','종류별 조회 행 1건','용어·정의·출현·참조·관계·전문검색 데이터 조회']], [0.26,0.24,0.50])
text(p,'03  저장 책임과 현재 상태','h')
table(p,['영역','저장 내용·상태'],[
['Gold 지식','구조화 원문·재사용 지식·온톨로지·LLM Wiki. 원문 판본·조항·span을 중심으로 관리합니다.'],
['Agent / 작업 후보','질문·판단·실행 로그는 Agent. 온톨로지 작업 후보는 Dataiku S3 관리 폴더의 JSON이며, 승인·신청·SQL 적재 후 Gold에서 사용합니다.'],
['이 문서의 범위','LGL_*는 AIDP/SIDDA 개발 실버 검증용 명명입니다. DDL·매핑·조회 코드를 대조한 설명이며 운영 Gold 승인·현장 적재·조회 전환 완료를 뜻하지 않습니다.']], [0.22,0.78])
text(p,'원문 데이터는 Oracle/조회 API에서 필요한 범위만 읽습니다. GENOS 서빙에 전체 원문·색인을 내려받아 보관하는 구조로 설명하지 않습니다.','note')

p=page('핵심 물리 스키마', '기존 실행 YAML의 컬럼·타입·키를 발췌 | owner: SIDDA')
desc={
'DATA_VER_ID':'데이터 구축 세대 ID', 'DOC_ID':'문서 ID', 'DOC_NM':'문서명', 'SRC_DATA_HASH_VAL':'원본자료 SHA-256', 'DOC_JSON_CN':'문서 메타 JSON',
'UNIT_ID':'구조 단위 ID', 'PRNT_UNIT_ID':'상위 구조 단위 ID', 'UNIT_JSON_CN':'제목·구조·본문 span JSON',
'BLK_ID':'본문 블록 ID','BLK_TXT_CN':'실제 원문','BLK_JSON_CN':'본문 구조·메타 JSON','JSON_TXT_OMIT_YN':'JSON 내 본문 생략 여부(0/1/NULL)',
'SRCH_PBLS_ID':'검색 게시 ID','ROW_KIND_CD':'논리 데이터 종류','ROW_ID':'조회 행 ID','SRCH_KEY_ID':'보조 조회 키','OWNR_REF_ID':'소속·출발 참조용 키','TGT_REF_ID':'대상 참조용 키','ROW_HASH_VAL':'조회 행 SHA-256','ROW_JSON_CN':'종류별 상세 JSON'}
for key in ('document','source_unit','block_payload','query_row'):
    t=mapping['tables'][key]; text(p,t['name'],'h')
    rows=[]
    for old,c in t['columns'].items():
        mark='PK' if old in t['pk'] else ('필수' if not c['nullable'] else '선택')
        rows.append([c['name'],c['type'],mark,desc[c['name']]])
    table(p,['컬럼','타입','키/NULL','의미'],rows,[0.30,0.25,0.10,0.35])
    p['blocks'][-1]['compact']=True
text(p,'복합 PK는 표의 PK 컬럼 전체 조합입니다. DATA_VER_ID는 데이터 세대 식별값이며 법령 시행일·개정번호와 다릅니다. 원문 3테이블의 문서·구조 연결은 논리 관계이며 모두 물리 FK로 선언된 것은 아닙니다.','note')

p=page('조회 행 내부의 연결 스키마', 'LGL_SRCH_ROW가 여러 논리 테이블·뷰를 종류별로 담습니다')
text(p,'SRCH_PBLS_ID + ROW_KIND_CD로 조회 범위를 정하고, SRCH_KEY_ID·OWNR_REF_ID·TGT_REF_ID·DOC_ID로 후보를 좁힙니다. 실제 논리 필드와 연결 원문은 ROW_JSON_CN에 있습니다. 보조 키의 의미는 종류에 따라 달라지므로 모든 관계를 TGT_REF_ID 하나로 연결하지 않습니다.')
table(p,['논리 테이블·뷰','핵심 필드','연결 역할'],[
['term / term_surface','id, json / term_id, key, text','질문 표현 → 용어 ID'],
['edge','id; json의 source, target, code','용어 → 관련 용어. 방향·종류 유지'],
['occurrence','term_id, source_id','용어 → 해당 용어가 등장하는 원문'],
['source','id, document_id, article, json','탐색용 원문 ID → 문서·구조·블록'],
['definition','id, document_id, json','정의 ID → 정의의 원문 위치·범위'],
['definition_reference','definition_id, reference_id','정의 → 정의 안의 명시 참조'],
['reference','id, document_id, json','참조 출발 원문·인용 문구·해결 상태'],
['reference_end','source_id, reference_id','출발·도착 양쪽에서 참조 ID 찾기'],
['reference_target','reference_id, ordinal, source_id, unit_id, unit_path, block_ids, target_level','참조 → 대상 원문과 정확한 구조·블록 범위'],
['전문검색·구조 투영','unit_fts_posting 등 / native.unit, native.source 등','본문 표현·구조 좌표로 원문 위치 찾기']], [0.25,0.39,0.36])
text(p,'용어에서 원문으로 내려가는 연결','h')
flow(p,['term_surface / term → term_id','occurrence.term_id → source_id','source.id → document_id + unit_id + 본문 블록','LGL_DOC_VER → LGL_DOC_UNIT → LGL_DOC_BLK'])
text(p,'source_id는 탐색용 원문 묶음 ID입니다. DOC_ID·UNIT_ID·BLK_ID와 같은 키가 아니므로 source를 통해 위치를 확인합니다. 상위 구조는 PRNT_UNIT_ID, 본문 범위는 UNIT_JSON_CN의 span 등 저장 계약으로 해석합니다.','note')
text(p,'게시 종류는 native.* 또는 asset_<경로 해시 일부>.<논리 테이블명> 형태입니다. 해당 게시 manifest가 포함 목록과 구조를 고정합니다. compact 저장의 occurrence/reference가 뷰인 경우에도 소비자는 같은 논리 계약을 사용합니다.','note')

p=page('명시 참조를 따라가는 과정', '정방향·역방향·정의 연결 | 문서명·조항·ID는 설명용 가상 예시')
text(p,'내규 I 제10조(S_I10)가 “외규 A 제20조”를 인용하고, 외규 A 제20조(S_A20)가 “외규 B 제5조”를 인용한다고 가정합니다. 실제 법률 내용이나 실측 실행 결과가 아닙니다.','note')
flow(p,['내규 I 제10조 · S_I10','참조 R01 → 외규 A 제20조 · S_A20','참조 R02 → 외규 B 제5조 · S_B05'])
text(p,'정방향 OUTGOING: 현재 원문이 가리키는 대상','h')
table(p,['순서','조회·검사','다음에 얻는 값'],[
['1','reference_end.source_id = S_I10','참조 ID R01'],
['2','reference.id = R01','출발 source_id·원문 문구·위치·해시·해결 상태'],
['3','reference의 출발 source_id == S_I10','현재 원문에서 나가는 정방향임을 확인'],
['4','reference_target의 R01 또는 reference JSON의 targets','대상 S_A20·unit_id·block_ids'],
['5','source.id = S_A20 → 원문 테이블','외규 A 제20조의 실제 원문'],
['6','읽은 S_A20의 연결을 같은 방식으로 확인','필요하면 R02를 거쳐 외규 B 제5조 읽기']], [0.08,0.48,0.44])
text(p,'현재 런타임은 reference JSON의 targets를 읽는 경로도 사용합니다. reference_target은 같은 대상의 논리 투영이며, 매번 이 테이블을 별도 SQL로 조회한다는 뜻은 아닙니다.','note')
text(p,'역방향 INCOMING: 현재 원문을 인용한 출발점','h')
text(p,'reference_end에는 (S_I10, R01)과 (S_A20, R01)이 함께 등록됩니다. S_A20에서 R01을 찾았을 때 reference의 출발점은 S_I10이므로 역방향입니다. S_I10의 실제 인용 문구가 속한 구조·본문을 읽습니다. 탐색 방향이 바뀌어도 “I가 A를 인용한다”는 관계 의미는 유지됩니다.')
text(p,'정의 연결: 질문의 용어에서 참조 대상까지','h')
text(p,'질문 표현 → definition(D01) → 정의 원문·용어 span 확인 → definition_reference(D01, R03) → reference(R03)의 원문 인용 확인 → 대상 위치 → 실제 원문 읽기. 같은 단어라도 문서·조항별 정의 범위를 합치지 않습니다.')
text(p,'연결 목록은 읽을 위치를 보여줍니다. 원문 열람과 답변 근거 채택은 별도 상태이며, 한 참조가 여러 조항을 가리키면 ordinal과 각 대상 범위를 보존합니다.','note')

p=page('검토한 내규–외규 관계 원장', '명시 참조와 별도로 관리하는 basis_* 논리 스키마')
text(p,'내규에 외규 번호가 직접 적혀 있지 않아도, 실제 양쪽 원문을 검토해 근거 관계를 제안·승인할 수 있습니다. 이 원장은 앞의 LGL_* 9테이블에 포함되지 않으며, Oracle 어댑터의 현장 매핑·적재·소비자 연결은 별도입니다.','lead')
table(p,['논리 테이블','키·주요 컬럼','역할'],[
['basis_head','PK link_id; team_id, revision','팀별 관계의 현재 revision'],
['basis_revision','PK(link_id, revision); payload CLOB, hash','관계 종류·상태·이유와 내규/외규 끝점'],
['basis_binding','PK binding_id; link_id, revision, generation, payload CLOB, hash','현재 데이터 세대의 실제 원문 위치 연결. (link_id, revision, generation) 유일'],
['basis_lineage','PK version_id; family_id, payload CLOB, hash','문서 판본의 계보']], [0.24,0.43,0.33])
text(p,'관계 payload의 핵심 항목','h')
table(p,['항목','내용'],[
['kind / status / reason','BASIS·IMPLEMENTS·RELATED / PROPOSED·APPROVED·REJECTED·REVOKED 등 / 검토 이유'],
['internal[] / external[]','내규·외규 끝점 목록. document_id, document_version, generation_id, unit_id, side, source_artifact_hash'],
['spans[] / endpoint_hash','block_id, start_cp, end_cp, text, block_hash, span_hash / 끝점 전체의 해시']], [0.29,0.71])
text(p,'현재 읽은 내규에서 외규로 이동','h')
flow(p,['읽은 내규의 document_id + 실제 span','팀별 원장에서 같은 내규·겹치는 범위의 관계 찾기','basis_head → basis_revision: 현재 revision·상태·이유','basis_binding: 같은 revision + 현재 generation의 위치 확인','external[]의 권한·원문·해시 확인 → 외규 실제 원문 읽기'])
text(p,'APPROVED 상태의 현재 근거 관계와 미검토 후보를 구분합니다. 일부 배치 조사 후보는 UNREVIEWED_CANDIDATE로 탐색에 쓰는 경로가 있으나 승인 관계로 표시하지 않습니다. 관계 revision·승인·접근권한이 바뀌거나 현재 위치 결속이 유효하지 않으면 이전 경로를 그대로 사용하지 않습니다.','note')

p=page('질문 하나의 실행 시나리오', '검색 → 내규 원문 → 연결 외규 → 추가 참조 → 해석')
text(p,'예시 질문: “우리 회사 레버리지비율 관리 기준과 관련 외규 근거를 알려줘.”','lead')
table(p,['단계','테이블·연결 경로','확인·전달하는 것'],[
['1. 버전 고정','LGL_SRCH_CHNL → LGL_SRCH_PBLS → LGL_SRC_PBLS','검색 게시 ID, 원문 데이터 세대, 현재 문서 권한. 게시 ID 직접 지정 시 채널 조회 생략'],
['2. 내규 후보','LGL_SRCH_ROW의 용어·정의·전문검색','문서·조항 후보. 이름·검색 점수는 적용 판단이 아님'],
['3. 내규 읽기','LGL_DOC_VER → LGL_DOC_UNIT → LGL_DOC_BLK','문서명·조항·상위 문맥·선택 범위의 실제 원문'],
['4. 연결 회수','reference_end → reference → targets / 별도 basis_*','명시 참조와 검토 관계를 구분하고 출발·도착·근거 확인'],
['5. 외규 읽기','대상 source → DOC_VER / DOC_UNIT / DOC_BLK','선택한 외규 범위의 실제 원문·판본·인용 위치'],
['6. 추가 연결','정방향·역방향·정의 연결을 필요한 범위에서 반복','다른 조항의 기준·예외·산정방법을 추가 확인'],
['7. 응답','확보 원문 + 연결 경로 + LLM 판단','내규·외규 실제 원문, 해석과 미확인 사항을 같은 행에서 제시']], [0.15,0.43,0.42])
text(p,'연결 탐색에서 지키는 경계','h')
table(p,['상황','처리'],[
['참조 대상 위치가 미해결','찾은 것처럼 읽지 않습니다. 문서명·조문번호로 구조 조회하고 필요하면 추가 검색합니다.'],
['조회된 연결이 없음','현재 범위·색인에서 미확보임을 기록합니다. 관련 외규가 존재하지 않는다고 단정하지 않습니다.'],
['선택 범위·권한·해시 불일치','잘못된 연결 또는 원문을 전달하지 않고 오류·미완료 상태를 보존합니다.'],
['이미 읽은 대상·남은 예산 제한','확보 범위를 확인해 반복을 줄이고, 남은 자료는 미확인으로 표시합니다.'],
['적용성·충분성에 불확실성','읽은 원문은 전달하며 판단과 미확인을 함께 표시합니다. 불확실성만으로 확보 원문을 버리지 않습니다.']], [0.27,0.73])
text(p,'최종 답변의 표시 형태','h')
table(p,['내규 출처·원문','연결 경로','외규 출처·원문','해석·미확인'],[
['내규 I 제10조의 실제 확보 구간','R01 또는 검토 관계 link_id','외규 A 제20조의 실제 확보 구간','어떤 기준이 연결되는지, 적용 사실·범위'],
['같은 내규 원문','R01 → R02','외규 B 제5조의 실제 확보 구간','추가 기준·예외 및 미확인 사항']], [0.26,0.20,0.27,0.27])
text(p,'문서명·조항·관계 ID는 설명용 예시입니다. 실제 답변에는 실행에서 확보·확인한 값만 표시합니다.','note')

p=page('명칭 대응·지원 스키마·근거', '기존 LEGAL_* 계약과 개발 LGL_* 매핑을 함께 확인합니다')
table(p,['기존 테이블명','개발용 대응명','책임'],[
['LEGAL_SRC_DOCUMENT_A','LGL_DOC_VER','Gold 지식 후보'],
['LEGAL_SRC_SOURCE_UNIT_A','LGL_DOC_UNIT','Gold 지식 후보'],
['LEGAL_SRC_BLOCK_PAYLOAD_A','LGL_DOC_BLK','Gold 지식 후보'],
['LEGAL_RAG_QUERY_ROW_A','LGL_SRCH_ROW','Gold 지식 후보'],
['LEGAL_RAG_RELEASE_A','LGL_SRC_PBLS','게시 지원·배치 승인 검토'],
['LEGAL_RAG_QUERY_RELEASE_A','LGL_SRCH_PBLS','게시 지원·배치 승인 검토'],
['LEGAL_RAG_QUERY_ACTIVE_A','LGL_SRCH_CHNL','채널 선택·배치 승인 검토'],
['LEGAL_RAG_QUERY_STATE_A','LGL_EXEC_ST','Agent 실행 상태 포트'],
['LEGAL_RAG_ASSET_PART_A','LGL_FILE_PART','이관·복구용 파일 조각']], [0.46,0.25,0.29])
text(p,'지원 테이블의 키와 주요 필드','h')
table(p,['테이블','키·주요 필드'],[
['LGL_SRC_PBLS','PK SRC_PBLS_ID; DATA_VER_ID, PBLS_JSON_CN(CLOB), REG_DTM(TIMESTAMP WITH TIME ZONE)'],
['LGL_SRCH_PBLS','PK SRCH_PBLS_ID; MNFST_JSON_CN(CLOB). JSON 내부 source_release_id로 원문 게시 연결'],
['LGL_SRCH_CHNL','PK CHNL_NM; SRCH_PBLS_ID(FK), CHG_SEQ_NO(NUMBER(18))'],
['LGL_EXEC_ST','PK(SCOPE_HASH_VAL, ST_KEY_ID); CHG_SEQ_NO, ST_HASH_VAL, ST_JSON_CN(CLOB)'],
['LGL_FILE_PART','PK(FILE_HASH_VAL, PART_SEQ_NO); ORG_BYTE_CNT, PART_HASH_VAL, PART_B64_CN(CLOB)']], [0.28,0.72])
text(p,'LGL_EXEC_ST 포트 제공과 실제 대화 이력의 Oracle 이전은 별도입니다. 현재 Oracle 서비스의 기존 이력은 외부 NFS/CIFS 바인딩을 사용합니다. LGL_FILE_PART는 직접 RAG 조회 대상이 아닙니다. 운영 Gold의 owner·명칭 승인·적재 및 기존 RAG의 LGL 조회 전환은 이 문서에서 완료로 확인하지 않았습니다.','note')
text(p,'확인 근거 — 저장소 상대 경로','h')
for s in [
'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1/01_CREATE_TABLES.sql · physical_mapping.yaml · GUIDE.txt',
'02_BACKEND/semantic_runtime/oracle_query_request.py · oracle_query.py · oracle_query_catalog.py',
'02_BACKEND/lawrag/pipeline/oracle_query_publish.py · oracle_query_navigation_publish.py',
'02_BACKEND/semantic_runtime/term_index.py · term_references.py · reference_build.py',
'02_BACKEND/semantic_runtime/legal_agent/unit_relations.py · definition_entry.py · connection_scope.py',
'02_BACKEND/semantic_runtime/basis_links/oracle.py · repository.py · resolver.py · sources.py',
'00_SYSTEM/ARCHITECTURE.md · 07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/ORACLE_GOLD_SELECTION.md']:
    text(p,s,'source')
text(p,'검토 범위: 저장된 DDL·매핑·작업 코드의 정적 대조. DB 변경, 모델 호출, 현장 조회·배포·법률 품질 검증은 수행하지 않았습니다. 작성 기준: 2026-10-27.','note')

# PDF: selectable text, embedded Korean font, fixed chapter pagination.
pdfmetrics.registerFont(TTFont('Malgun','/mnt/c/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','/mnt/c/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold')
styles={
'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=20,leading=27,textColor=colors.HexColor(NAVY),spaceAfter=6,wordWrap='CJK'),
'sub':ParagraphStyle('sub',fontName='Malgun',fontSize=9,leading=14,textColor=colors.HexColor(GREY),spaceAfter=15,wordWrap='CJK'),
'p':ParagraphStyle('p',fontName='Malgun',fontSize=9,leading=14,spaceAfter=7,wordWrap='CJK'),
'lead':ParagraphStyle('lead',fontName='Malgun',fontSize=10,leading=16,spaceAfter=10,wordWrap='CJK',textColor=colors.HexColor(NAVY)),
'h':ParagraphStyle('h',fontName='MalgunBold',fontSize=11,leading=16,spaceBefore=9,spaceAfter=5,textColor=colors.HexColor(BLUE),keepWithNext=True,wordWrap='CJK'),
'note':ParagraphStyle('note',fontName='Malgun',fontSize=8,leading=12,spaceBefore=4,spaceAfter=6,textColor=colors.HexColor(GREY),wordWrap='CJK'),
'source':ParagraphStyle('source',fontName='Malgun',fontSize=7.5,leading=11,spaceAfter=4,wordWrap='CJK'),
'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=8,leading=11.3,wordWrap='CJK'),
'compact':ParagraphStyle('compact',fontName='Malgun',fontSize=8,leading=11,wordWrap='CJK'),
'th':ParagraphStyle('th',fontName='MalgunBold',fontSize=8,leading=11.3,textColor=colors.white,wordWrap='CJK'),
'flow':ParagraphStyle('flow',fontName='MalgunBold',fontSize=9,leading=12.2,alignment=1,textColor=colors.HexColor(NAVY),wordWrap='CJK')}
def para(value,kind='p'): return Paragraph(escape(value).replace('\n','<br/>'),styles[kind])
W,H=A4; WIDTH=W-84
def pdf_table(block):
    rows=[[para(x,'th') for x in block['headers']]]+[[para(str(x),'compact' if block.get('compact') else 'cell') for x in row] for row in block['rows']]
    widths=[WIDTH*x for x in (block['widths'] or [1/len(rows[0])]*len(rows[0]))]
    t=Table(rows,colWidths=widths,hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(LIGHT)]),('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#D7E2EB')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    if block.get('compact'):t.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),2.5),('BOTTOMPADDING',(0,0),(-1,-1),2.5)]))
    return t
def furniture(c,d):
    c.setStrokeColor(colors.HexColor(TEAL));c.setLineWidth(3);c.line(42,H-28,W-42,H-28)
    c.setFont('Malgun',7.5);c.setFillColor(colors.HexColor(GREY));c.drawString(42,25,'DP 스키마·연결 탐색 가이드  |  2026.10.27')
    c.drawRightString(W-42,25,str(d.page))
story=[]
for i,p in enumerate(pages):
    if i:story.append(PageBreak())
    story += [para(p['title'],'title'),para(p['subtitle'],'sub')]
    for b in p['blocks']:
        if b['type']=='table':story += [pdf_table(b),Spacer(1,5)]
        elif b['type']=='flow':
            t=Table([[para(b['text'],'flow')]],colWidths=[WIDTH]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#EAF4F5')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#B7D9DC')),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]));story += [t,Spacer(1,5)]
        else:story.append(para(b['text'],b['type']))
pdf=OUT/(STEM+'.pdf')
SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=44,bottomMargin=42,title='3·5번 과제 DP 스키마와 연결 탐색',author='').build(story,onFirstPage=furniture,onLaterPages=furniture)

# Word: native editable text/tables from exactly the same content model.
doc=Document();section=doc.sections[0];section.page_width=Cm(21);section.page_height=Cm(29.7)
section.top_margin=Cm(1.5);section.bottom_margin=Cm(1.5);section.left_margin=Cm(1.5);section.right_margin=Cm(1.5)
for name,size in [('Normal',9),('Title',20),('Subtitle',9),('Heading 1',11)]:
    s=doc.styles[name];s.font.name='맑은 고딕';s.font.size=Pt(size);s._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'맑은 고딕')
    s.paragraph_format.space_after=Pt(5);s.paragraph_format.line_spacing=1.08
doc.styles['Heading 1'].font.color.rgb=RGBColor.from_string(BLUE[1:])
doc.styles['Title'].font.color.rgb=RGBColor.from_string(NAVY[1:])
foot=section.footer.paragraphs[0];foot.text='DP 스키마·연결 탐색 가이드 | 2026.10.27   ·   '
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');foot._p.append(field)
for pnum,p in enumerate(pages):
    if pnum:doc.add_page_break()
    doc.add_paragraph(p['title'],'Title');doc.add_paragraph(p['subtitle'],'Subtitle')
    for b in p['blocks']:
        if b['type']=='table':
            t=doc.add_table(rows=1,cols=len(b['headers']));t.autofit=False
            widths=b['widths'] or [1/len(b['headers'])]*len(b['headers'])
            for col,ratio in zip(t.columns,widths):col.width=Cm(18*ratio)
            for cell,value,ratio in zip(t.rows[0].cells,b['headers'],widths):
                cell.text=value;cell.width=Cm(18*ratio)
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),NAVY[1:]);cell._tc.get_or_add_tcPr().append(sh)
                for r in cell.paragraphs[0].runs:r.font.bold=True;r.font.color.rgb=RGBColor(255,255,255)
            repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
            for n,row in enumerate(b['rows']):
                cells=t.add_row().cells
                for cell,value,ratio in zip(cells,row,widths):
                    cell.text=str(value);cell.width=Cm(18*ratio)
                    if n%2:
                        sh=OxmlElement('w:shd');sh.set(qn('w:fill'),LIGHT[1:]);cell._tc.get_or_add_tcPr().append(sh)
            for row in t.rows:
                row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                for cell in row.cells:
                    for q in cell.paragraphs:
                        q.paragraph_format.space_after=Pt(1 if b.get('compact') else 3);q.paragraph_format.space_before=Pt(1 if b.get('compact') else 3)
                        for r in q.runs:r.font.size=Pt(8)
            doc.add_paragraph().paragraph_format.space_after=Pt(1)
        else:
            q=doc.add_paragraph(b['text'],'Heading 1' if b['type']=='h' else 'Normal')
            if b['type']=='flow':
                q.alignment=1;q.paragraph_format.keep_together=True
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'EAF4F5');q._p.get_or_add_pPr().append(sh)
                for r in q.runs:r.font.bold=True
            if b['type'] in ('note','source'):
                for r in q.runs:r.font.size=Pt(8 if b['type']=='note' else 7.5);r.font.color.rgb=RGBColor.from_string(GREY[1:])
doc.core_properties.title='3·5번 과제 DP 스키마와 연결 탐색';doc.core_properties.subject='핵심 테이블·질문 조회 경로·정방향/역방향·내규–외규 관계';doc.core_properties.author=''
doc.save(OUT/(STEM+'.docx'))

# Readable HTML source and concise email body, with no JavaScript.
css='body{font-family:"Malgun Gothic",sans-serif;color:#17324d;line-height:1.65;max-width:960px;margin:36px auto;padding:0 24px}h1{font-size:26px}h2{font-size:18px;color:#245f9b}section{margin:36px 0 60px}table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}td,th{border-bottom:1px solid #d7e2eb;text-align:left;padding:9px;vertical-align:top;overflow-wrap:anywhere}th{background:#17324d;color:white}tr:nth-child(even){background:#f0f5f9}.flow{white-space:pre-line;text-align:center;background:#eaf4f5;padding:18px}.note,.source{color:#536577;font-size:12px}.lead{font-size:16px}'
html=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>DP 스키마와 연결 탐색</title><style>'+css+'</style><body>']
for p in pages:
    html+=['<section><h1>'+escape(p['title'])+'</h1><p>'+escape(p['subtitle'])+'</p>']
    for b in p['blocks']:
        if b['type']=='table':html+=['<table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in b['rows'])+'</tbody></table>']
        elif b['type']=='h':html+=['<h2>'+escape(b['text'])+'</h2>']
        else:html+=['<p class="'+b['type']+'">'+escape(b['text']).replace('\n','<br>')+'</p>']
    html+=['</section>']
html+=['</body></html>'];(OUT/(STEM+'.html')).write_text('\n'.join(html),encoding='utf-8')
email='''<div style="font-family:Arial,'Malgun Gothic',sans-serif;font-size:14px;line-height:1.75;color:#23364a;max-width:880px">
<p>안녕하세요.</p><p>3·5번 과제 공통 법규 RAG의 <b>DP 핵심 테이블 스키마와 질문별 연결 탐색 흐름</b>을 정리해 전달드립니다.</p>
<table style="border-collapse:collapse;width:100%;font-size:13px"><tr style="background:#17324d;color:white"><th style="padding:10px;text-align:left">핵심 테이블</th><th style="padding:10px;text-align:left">역할</th></tr>
<tr><td style="padding:9px;border-bottom:1px solid #d7e2eb">LGL_DOC_VER / LGL_DOC_UNIT / LGL_DOC_BLK</td><td style="padding:9px;border-bottom:1px solid #d7e2eb">문서·조항 구조·실제 원문</td></tr>
<tr style="background:#f0f5f9"><td style="padding:9px">LGL_SRCH_ROW</td><td style="padding:9px">용어·정의·참조·관계·본문 검색의 조회 데이터</td></tr></table>
<p style="background:#eaf4f5;padding:14px"><b>질문 → 버전·권한 고정 → 용어·정의·본문 검색 → 내규 원문 → 연결 외규 원문 → 추가 참조 확인 → 인용·해석·미확인 응답</b></p>
<p>첨부 문서에는 다음 내용을 담았습니다.</p><ol><li>핵심 4테이블의 전체 컬럼·타입·PK와 전체 9테이블의 명칭 대응</li><li>용어·정의에서 문서·조항·본문으로 이동하는 연결 키</li><li>명시 참조의 정방향·역방향 탐색 및 두 단계 참조 예시</li><li>검토·승인한 내규–외규 관계의 별도 basis_* 원장과 세대별 원문 연결</li><li>질문 하나의 전체 조회 순서, 원문·권한·버전 검사, 답변 표시 예시</li></ol>
<p><b>자료 기준:</b> LGL_*는 AIDP/SIDDA 개발 실버 검증용 명명입니다. 코드·DDL을 대조한 구조 설명이며 운영 Gold 승인, 현장 적재·조회 전환 또는 basis_*의 현장 Oracle 배포 완료를 의미하지 않습니다. 문서 내 사례 문서명·조항·ID는 설명용 가상 예시입니다.</p>
<p><b>첨부:</b> 열람용 PDF, 수정 가능한 Word(DOCX).<br>감사합니다.</p></div>'''
(OUT/'EMAIL_BODY.html').write_text(email,encoding='utf-8')
(OUT/'CONTENT.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
artifacts={f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in OUT.iterdir() if f.suffix in ('.pdf','.docx','.html')}
(OUT/'ARTIFACTS.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(artifacts,ensure_ascii=False))
