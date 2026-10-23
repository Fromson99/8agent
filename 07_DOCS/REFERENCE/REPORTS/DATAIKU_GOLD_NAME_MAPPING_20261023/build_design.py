"""Generate review artifacts only. Does not connect to a database or alter runtime."""
from pathlib import Path
import ast
import csv
import hashlib
import json
import re
import zipfile

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from metadata_details import column_metadata, table_metadata, RULES, WORKBOOK
from operational_details import build_operational_details
from example_workbook import build_example_workbook

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = ROOT / '07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022'
DDL = ROOT / '08_DEPLOYMENT/DATAIKU/legal_oracle_all_tables_20261019_r1/LEGAL_ORACLE_ALL_9_TABLES_20261019_R1.sql'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def csv_out(name, rows):
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

# Candidate abbreviations, not approved Metaminer terms.
TABLES = {
    'LEGAL_SRC_DOCUMENT_A': ('document', 'LGL_DOC_VER', 'gold_knowledge', '문서판본정보'),
    'LEGAL_SRC_SOURCE_UNIT_A': ('source_unit', 'LGL_DOC_UNIT', 'gold_knowledge', '문서구조단위정보'),
    'LEGAL_SRC_BLOCK_PAYLOAD_A': ('block_payload', 'LGL_DOC_BLK', 'gold_knowledge', '문서본문블록정보'),
    'LEGAL_RAG_QUERY_ROW_A': ('query_row', 'LGL_SRCH_ROW', 'gold_knowledge', '지식조회행정보'),
    'LEGAL_RAG_RELEASE_A': ('source_release', 'LGL_SRC_PBLS', 'gold_support', '원문게시정보'),
    'LEGAL_RAG_QUERY_RELEASE_A': ('query_release', 'LGL_SRCH_PBLS', 'gold_support', '지식조회게시정보'),
    'LEGAL_RAG_QUERY_ACTIVE_A': ('query_active', 'LGL_SRCH_CHNL', 'gold_support', '지식조회채널정보'),
    'LEGAL_RAG_QUERY_STATE_A': ('query_state', 'LGL_EXEC_ST', 'agent', '에이전트실행상태정보'),
    'LEGAL_RAG_ASSET_PART_A': ('asset_part', 'LGL_FILE_PART', 'transfer_archive', '파일분할보관정보'),
}
DESCRIPTION = {
    'document': ('이 세대의 문서명과 원본자료 해시는 무엇인가?', '구조화된 문서 메타; 원문 파일 자체와 질문 답변 제외', '동일 DOCUMENT_ID라도 DATASET_VERSION이 다르면 별도 행; 구축 세대와 법령 개정 판본을 구분하고 세대 간 중복 집계 주의'),
    'source_unit': ('이 조문의 상위 장·절과 하위 구조 단위는 무엇인가?', '문서 내부 구조·부모 관계; 의미 해석 및 승인되지 않은 추정 관계 제외', '부모 관계는 같은 문서·세대 안에서 확인; 서로 다른 편의 같은 장 번호를 합치지 않음'),
    'block_payload': ('이 조항의 정확한 원문은 무엇인가?', '본문 블록·구조 단위 연결·원본 해시; 생성 답변 제외', '본문 생략 플래그는 JSON 중복 본문 처리 계약; 원문 부재로 해석하지 않음'),
    'query_row': ('지정 릴리스에서 용어·정의·구조·참조를 어떻게 찾는가?', 'manifest에 정의된 조회 투영; 새로운 온톨로지/위키 전체 정본 제외', 'KIND별 논리 스키마가 다름; 단일 개념 테이블로 집계 금지'),
    'source_release': ('이 게시본은 어느 원문 세대·파일 자산에 결속되는가?', '완료 게시 명세와 등록시각; 미완료 게시·임시 작업 상태 제외', '직접 조회도 참조하는 필수 게시 지원 정보; 자산 보관 테이블과 함께 삭제하지 않음'),
    'query_release': ('조회 게시본의 원문 세대와 투영 해시는 무엇인가?', '완료 조회 manifest; 미완료 행을 완료 게시로 표시하지 않음', 'manifest와 release 해시 확인 필요; 게시 완료와 활성 채널 선택을 구분'),
    'query_active': ('이 채널이 선택한 조회 릴리스는 무엇인가?', '채널 현재 선택과 CAS revision; 과거 선택 이력 자체는 포함하지 않음', '활성 변경은 검증 후 명시 수행; revision 조건 없는 덮어쓰기 금지'),
    'query_state': ('이 범위의 상태와 변경 순번은 무엇인가?', '포트가 저장한 작은 요청/세션 상태; 전체 원문 DB·모든 현행 이력 포함 아님', 'scope hash가 접근권한 검사를 대체하지 않음; 미확정 쓰기는 revision/hash로 재조회'),
    'asset_part': ('이 자산의 분할 조각이 원본 해시와 일치하는가?', 'zlib+Base64 파일 조각; 직접 지식 조회·원문 문장 테이블 아님', '조각 순서는 0부터; 합쳐 복원할 때 크기·조각/전체 hash 검증'),
}
COLS = {
    'DATASET_VERSION': ('DATA_VER_ID', '데이터판본ID', 'ID'),
    'DOCUMENT_ID': ('DOC_ID', '문서ID', 'ID'),
    'NAME': ('DOC_NM', '문서명', '명'),
    'SOURCE_ARTIFACT_SHA256': ('SRC_DATA_HASH_VAL', '원본자료해시값', '값'),
    'SOURCE_JSON': ('SRC_JSON_CN', '원천JSON내용', '내용'),
    'UNIT_ID': ('UNIT_ID', '구조단위ID', 'ID'),
    'PARENT_ID': ('PRNT_UNIT_ID', '상위구조단위ID', 'ID'),
    'BLOCK_ID': ('BLK_ID', '본문블록ID', 'ID'),
    'TEXT': ('BLK_TXT_CN', '블록본문내용', '내용'),
    'JSON_TEXT_ELIDED': ('JSON_TXT_OMIT_YN', 'JSON본문생략여부', '여부'),
    'KIND': ('ROW_KIND_CD', '조회행종류코드', '코드'),
    'ROW_ID': ('ROW_ID', '조회행ID', 'ID'),
    'LOOKUP_ID': ('SRCH_KEY_ID', '검색키ID', 'ID'),
    'OWNER_ID': ('OWNR_REF_ID', '소유참조ID', 'ID'),
    'TARGET_ID': ('TGT_REF_ID', '대상참조ID', 'ID'),
    'ROW_SHA256': ('ROW_HASH_VAL', '조회행해시값', '값'),
    'RELEASE_JSON': ('PBLS_JSON_CN', '게시JSON내용', '내용'),
    'CREATED_AT': ('REG_DTM', '등록일시', '일시'),
    'MANIFEST_JSON': ('MNFST_JSON_CN', '명세JSON내용', '내용'),
    'CHANNEL': ('CHNL_NM', '게시채널명', '명'),
    'REVISION': ('CHG_SEQ_NO', '변경순번', '번호'),
    'SCOPE_HASH': ('SCOPE_HASH_VAL', '범위해시값', '값'),
    'STATE_KEY': ('ST_KEY_ID', '상태키ID', 'ID'),
    'VALUE_SHA256': ('ST_HASH_VAL', '상태해시값', '값'),
    'ASSET_SHA256': ('FILE_HASH_VAL', '파일해시값', '값'),
    'PART_NO': ('PART_SEQ_NO', '분할순번', '번호'),
    'RAW_BYTES': ('ORG_BYTE_CNT', '원본바이트수', '수'),
    'PART_SHA256': ('PART_HASH_VAL', '분할해시값', '값'),
    'DATA_B64': ('PART_B64_CN', '분할인코딩내용', '내용'),
}

def col_spec(table, col):
    if col == 'RELEASE_ID':
        return ('SRC_PBLS_ID', '원문게시ID', 'ID') if table == 'source_release' else ('SRCH_PBLS_ID', '조회게시ID', 'ID')
    if col == 'VALUE_JSON':
        return ('ST_JSON_CN', '상태JSON내용', '내용') if table == 'query_state' else ('ROW_JSON_CN', '조회행JSON내용', '내용')
    if col == 'SOURCE_JSON':
        return {'document': ('DOC_JSON_CN', '문서JSON내용', '내용'),
                'source_unit': ('UNIT_JSON_CN', '구조JSON내용', '내용'),
                'block_payload': ('BLK_JSON_CN', '블록JSON내용', '내용')}[table]
    return COLS[col]

source_tables = read_csv(BASE/'ORACLE_GOLD_TABLES.csv')
source_columns = read_csv(BASE/'ORACLE_GOLD_COLUMNS.csv')
assert len(source_tables) == 9 and len(source_columns) == 46
assert {r['DDL근거SHA256'] for r in source_columns} == {sha(DDL)}
roles = sorted({v[2] for v in TABLES.values()})
mapping = {
    'schema_version': 'legal-db-physical-map-design-v1',
    'mapping_revision': '20261023-candidate-r3-operations',
    'status': 'DRAFT_UNAPPROVED_NOT_WIRED',
    'runtime_enabled': False,
    'standard_dictionary_status': 'NOT_PROVIDED',
    'purpose': 'Review design; no existing runtime reads this file yet.',
    'metadata_reference': [RULES, WORKBOOK],
    'documentation_fingerprint_policy': 'metadata descriptions do not alter logical row/content hashes; exclude documentation fields from the proposed physical execution-map hash',
    'policies': {'preserve_logical_payload_keys': True, 'preserve_content_hashes': True,
                 'implicit_profile_fallback': False, 'identifier_limit_candidate_bytes': 30,
                 'identifier_separator_approval': 'PENDING', 'ddl_on_service_start': False,
                 'rename_only_first': True, 'automatic_numeric_id_conversion': False},
    'profiles': {
        'legacy_sidda': {'deployment_enabled': False, 'name_set': 'legacy',
                         'owner_by_role': {r: 'SIDDA' for r in roles},
                         'layer': 'LEGACY_LAYER_UNVERIFIED'},
        'dev_silver': {'deployment_enabled': False, 'name_set': 'candidate',
                       'owner_by_role': {r: None for r in roles},
                       'layer': 'SILVER', 'note': 'Fill authorized dev owner; all names match the future approved target.'},
        'prod_gold': {'deployment_enabled': False, 'name_set': 'candidate',
                      'owner_by_role': {r: None for r in roles},
                      'layer': 'MIXED_BY_ROLE',
                      'note': 'gold knowledge/support require approval; agent and archive retain separate storage roles.'},
    },
    'tables': {},
}
table_rows, column_rows = [], []
bizmeta_rows, table_description_rows, column_description_rows = [], [], []
for r in source_tables:
    old = r['현재물리테이블명']
    key, proposed, role, label = TABLES[old]
    selected = [c for c in source_columns if c['현재물리테이블명'] == old]
    spec = {'logical_name_ko': label, 'legacy_name': old, 'candidate_name': proposed,
            'storage_role': role, 'standard_approval': 'PENDING',
            'columns': {}, 'primary_key': [], 'indexes': [], 'foreign_keys': [], 'checks': []}
    for c in selected:
        name = c['현재물리컬럼명']
        candidate, korean, domain = col_spec(key, name)
        cid = name.lower()
        note = '물리명만 매핑; API/JSON 키·값·해시 보존'
        if name == 'JSON_TEXT_ELIDED':
            note = '기존 NUMBER(1)·NULL 보존. 승인 여부 도메인이 CHAR이면 별도 codec/데이터 이행 설계 필요; Y/N 자동 변환 금지.'
        elif name == 'NAME':
            note = '기존 CLOB 보존. 명 도메인의 승인 인포타입·실측 최대 길이 확인 전 VARCHAR로 축소 금지.'
        elif name == 'KIND':
            note = '기존 동적 KIND 문자열과 manifest 매핑 유지. 코드값 재번호화는 별도 계약 변경.'
        elif name == 'CREATED_AT':
            note = '코드 INSERT가 생략하는 DB 기본값 컬럼도 매핑. 신규 복제 시 원래 등록시각 보존; 시행일과 다름.'
        elif name == 'DATA_B64':
            note = '현행 zlib 압축 후 Base64 인코딩·해시·복호화 계약 유지. 지식 조회 테이블이 아님.'
        elif domain == 'ID':
            note += '; 외부 인터페이스/불변 ID 예외 승인 확인; 승인 논리명이 번호여도 값·문자형은 유지'
        meaning = c['업무의미']
        formula = c['산식생성근거']
        if name == 'DATA_B64':
            meaning = '원본 파일 조각을 zlib로 압축한 바이트의 Base64 문자열'
            formula = 'base64(zlib.compress(raw_part, 6))'
        item = {'application_key': name, 'legacy_name': name, 'candidate_name': candidate,
                'logical_name_ko_candidate': korean, 'current_type': c['현행DDL타입'],
                'candidate_type': c['현행DDL타입'], 'nullable': c['현행DDL_NULL허용'] == 'Y',
                'default': c['기본값'] or None, 'codec': 'identity',
                'standard': {'term_id': None, 'word_ids': [], 'domain_id': None, 'infotype_id': None,
                             'domain_label_candidate': domain, 'status': 'PENDING'}, 'note': note}
        meta = column_metadata(key, name, item, c)
        item['metadata'] = meta
        meaning, formula = meta['business_meaning'], meta['derivation']
        spec['columns'][cid] = item
        if c['PK순번']:
            spec['primary_key'].append((int(c['PK순번']), cid))
        column_rows.append({
            '논리테이블ID': key, '현재테이블명': old,
            '후보테이블명': proposed, '목표저장책임': role, '순번': int(c['컬럼순번']),
            '코드계약키': name, '현재컬럼명': name, '후보컬럼명': candidate, '후보논리명': korean,
            '현재타입': c['현행DDL타입'], '1차후보타입': c['현행DDL타입'],
            'NULL허용': c['현행DDL_NULL허용'], 'PK순번': c['PK순번'], '기본값': c['기본값'],
            '업무의미': meaning, '허용값': meta['allowed_values'], '생성산식': formula,
            '명칭선정이유': meta['naming_rationale'], '타입유지변경이유': meta['type_rationale'],
            '기존FK': c['물리FK'], '도메인말후보': domain, '표준용어ID': '미제공',
            '표준단어ID': '미제공', '표준도메인ID': '미제공', '인포타입ID': '미제공',
            '승인상태': '미승인 후보', '이행방식': 'identity', '검토사항': note,
            '컬럼Description': meta['description_plain_text'], '설명근거': meta['evidence'],
        })
        column_description_rows.append({'테이블명후보':proposed, '컬럼명후보':candidate,
            '한글논리명후보':korean, '업무의미':meaning, '허용값코드범위':meta['allowed_values'],
            '산식생성규칙':formula, '명칭선정이유':meta['naming_rationale'],
            '타입유지변경이유':meta['type_rationale'], 'Description붙여넣기':meta['description_plain_text'],
            '설명근거':meta['evidence'], '표준승인':'미확인·미승인'})
    spec['primary_key'] = [c for _, c in sorted(spec['primary_key'])]
    spec['pk_name_candidate'] = proposed + '_PK'
    mapping['tables'][key] = spec
    question, inclusion, caution = DESCRIPTION[key]
    pkcols = [spec['columns'][k]['candidate_name'] for k in spec['primary_key']]
    metadata, example, completion = table_metadata(key, spec, r, question, inclusion, caution)
    spec['metadata'] = metadata
    table_rows.append({
        '논리테이블ID': key, '현재스키마': 'SIDDA', '현재테이블명': old, '후보테이블명': proposed,
        '후보논리명': label, '개발위치': '승인된 개발계 Silver owner 미확정',
        '업무설명': metadata['business_description'], '명칭선정이유': metadata['naming_rationale'],
        '운영저장책임': role, '골드후보': r['골드후보'], '등록차수': r['등록차수제안'],
        '컬럼수': len(selected), '행단위': r['행단위'],
        '후보PK': ' + '.join(spec['columns'][k]['candidate_name'] for k in spec['primary_key']),
        '데이터유형': r['데이터유형제안'], '출처': r['데이터출처'], '가공과정': r['가공프로세스'],
        '데이터유형선정이유': metadata['data_type_classification_rationale'],
        '레이어선정이유': metadata['layer_selection_rationale'],
        '생성시각': r['생성시각계획'], '소비자': r['실제코드소비자'], '사용조건': r['사용조건'],
        '답할수있는질문': question, '포함제외': inclusion,
        '갱신완료기준': completion,
        '산식단위': '합산 산식 해당 없음; 컬럼별 hash/byte/순번 생성 계약 참조',
        '주의': caution, '예시SQL_실행불가초안': example,
        '에이전트번호': '미확정', '관리부서': '미확정', '보유기간': r['보유기간'],
        '메타상태': '후보; 신청·승인 미수행', 'DBA상태': '생성신청·생성 미수행',
        '현장상태': '기존 9개 이름 조회 사진만 확인; 신규 이름/스키마 미검증',
        '테이블Description': metadata['description_plain_text'], '설명근거':metadata['evidence'],
    })
    bizmeta_rows.append({'번호':len(bizmeta_rows)+1, '에이전트번호':'담당자 확인 필요',
        '현재스키마':'SIDDA', '목표스키마':'담당자 확인 필요', '테이블명후보':proposed,
        '한글논리명후보':label,'데이터논리명_업무설명':metadata['business_description'],
        '데이터출처':r['데이터출처'],'데이터유형후보':r['데이터유형제안'],
        '유형선정이유':metadata['data_type_classification_rationale'],
        '데이터가공프로세스설명':r['가공프로세스'],'생성시각계획':r['생성시각계획'],
        '등록분류':r['등록차수제안'],'등록선정제외이유':metadata['layer_selection_rationale'],
        '실제등록상태':'신청·승인·생성 미수행'})
    table_description_rows.append({'테이블명후보':proposed,'한글논리명후보':label,
        **metadata['description_fields'], '명칭선정이유':metadata['naming_rationale'],
        '유형선정이유':metadata['data_type_classification_rationale'],
        '레이어선정이유':metadata['layer_selection_rationale'],
        'Description붙여넣기':metadata['description_plain_text'],'설명근거':metadata['evidence']})

def check(table, name, op, columns, value=None):
    mapping['tables'][table]['checks'].append({'name_candidate': name, 'operator': op,
                                              'columns': columns, 'value': value})
check('query_release', 'LGL_SRCH_PBLS_JCK', 'is_json', ['manifest_json'])
check('query_row', 'LGL_SRCH_ROW_JCK', 'is_json', ['value_json'])
check('query_active', 'LGL_SRCH_CHNL_RCK', 'ge', ['revision'], 1)
check('query_state', 'LGL_EXEC_ST_RCK', 'ge', ['revision'], 1)
check('query_state', 'LGL_EXEC_ST_JCK', 'is_json', ['value_json'])
check('asset_part', 'LGL_FILE_PART_CK', 'asset_part_bounds', ['part_no', 'raw_bytes'],
      {'part_no_min': 0, 'raw_bytes_min_exclusive': 0, 'raw_bytes_max': 1048576})
mapping['tables']['query_active']['foreign_keys'] = [{
    'name_candidate': 'LGL_SRCH_CHNL_PBLS_FK', 'columns': ['release_id'],
    'target_table': 'query_release', 'target_columns': ['release_id'], 'delete_rule': 'NO ACTION'}]
for col, short in [('lookup_id','KEY'),('owner_id','OWNR'),('target_id','TGT'),('document_id','DOC')]:
    mapping['tables']['query_row']['indexes'].append({
        'name_candidate': 'LGL_SRCH_ROW_' + short + '_IX', 'columns': ['release_id','kind',col],
        'unique': False, 'required_before_serving': True})
mapping['tables']['source_release']['columns']['created_at']['writer_mode'] = 'database_default_on_new_insert_preserve_on_copy'
mapping['logical_relationships_not_new_fks'] = [
    'source_unit(data_ver,doc) -> document(data_ver,doc)',
    'source_unit parent is in the same dataset and document; root parent may be NULL',
    'block_payload(data_ver,doc,unit) -> source_unit(data_ver,doc,unit)',
    'query_release.manifest.source_release_id -> source_release.release_id',
    'asset_part hash/sequence -> source_release asset manifest',
]
mapping['required_binding_receipt_proposal'] = [
    'logical_contract_version','mapping_revision','logical_map_sha256','effective_target_map_sha256',
    'profile','database_identity','code_sha256','dataset_version','result_sha256','load_job_id']

operational_exports=build_operational_details(mapping)
for title,filename,rows in operational_exports:
    csv_out(filename,rows)

(OUT/'physical_mapping.draft.yaml').write_text(yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False))
csv_out('TABLE_MAPPING.csv', table_rows)
csv_out('COLUMN_MAPPING.csv', column_rows)
csv_out('BIZMETA.csv',bizmeta_rows)
csv_out('TABLE_DESCRIPTIONS.csv',table_description_rows)
csv_out('COLUMN_DESCRIPTIONS.csv',column_description_rows)
coverage=[]
for field in next(iter(mapping['tables'].values()))['metadata']['description_fields']:
    unconfirmed = 9 if field in {'보유기간과기준시점','갱신주기와완료기준','오너'} else 0
    coverage.append({'대상':'테이블 Description','필수항목':field,'대상수':9,'작성수':9,'미작성수':0,
                     '추가확인필요수':unconfirmed,'근거':RULES,
                     '확인사항':'현장 보유기간·시각·담당자 확정 필요' if unconfirmed else '코드/설계 근거 초안; 메타 승인 아님'})
for field in ['한글논리명','업무의미','허용값코드범위','산식생성규칙','명칭선정이유','타입유지변경이유']:
    coverage.append({'대상':'컬럼 Description','필수항목':field,'대상수':46,'작성수':46,'미작성수':0,
                     '추가확인필요수':46 if field in {'한글논리명','명칭선정이유','타입유지변경이유'} else 0,
                     '근거':RULES if field not in {'명칭선정이유','타입유지변경이유'} else WORKBOOK+' + 사용자 변경 이유 요청',
                     '확인사항':'정적 계약 설명; 현장 데이터 전수검사·표준 승인과 구분'})
csv_out('METADATA_COVERAGE.csv',coverage)
unresolved_rows=[
    {'확인항목':'과제 에이전트번호','상태':'미확정','필요한이유':'과제별 활용테이블 목록과 Bizmeta의 식별정보','반영위치':'BIZMETA / tables.*.metadata.unresolved.agent_number'},
    {'확인항목':'개발 Silver 및 운영 Gold/Agent/보관 owner','상태':'미확정','필요한이유':'실제 생성·조회·쓰기 대상과 권한 결속','반영위치':'profiles.*.owner_by_role'},
    {'확인항목':'관리 부서·담당자','상태':'미확정','필요한이유':'테이블 Description 오너·변경관리 책임','반영위치':'테이블설명 / metadata.description_fields.오너'},
    {'확인항목':'보유기간·삭제 기준','상태':'공식 기간 미확정','필요한이유':'원문·판본·감사 이력의 보존 정책','반영위치':'테이블설명 / metadata.description_fields.보유기간과기준시점'},
    {'확인항목':'운영 배치 시각·완료 기준 담당','상태':'목표 흐름만 확인; 고정 시각 미확정','필요한이유':'Bizmeta 생성시각과 당일 데이터 반영 범위','반영위치':'BIZMETA / metadata.bizmeta.creation_schedule'},
    {'확인항목':'표준단어·용어·도메인·인포타입','상태':'미확인·미승인','필요한이유':'한글 논리명·영문 약어·타입의 전사 표준 매핑','반영위치':'컬럼명_46개 / columns.*.standard'},
    {'확인항목':'지원 테이블 3개 Gold 등록 범위','상태':'후보; 거버넌스 확인 필요','필요한이유':'원문 게시·조회 게시·채널 선택의 운영 배치','반영위치':'BIZMETA 등록분류·선정이유'},
    {'확인항목':'CLOB 명·숫자 여부·동적 종류 코드','상태':'기존 타입 보존안; 표준 도메인 조정 필요 여부 미확정','필요한이유':'명칭 변경과 값/타입 변환을 분리하고 무손실 이행','반영위치':'컬럼설명 / 표준 인포타입 확인란'},
    {'확인항목':'문서 범위·JSON 내부정보·계정별 권한','상태':'현장 책임자·실제 grant 미확인','필요한이유':'내규·외규의 공개 범위와 상태 객체 접근 권한 보존','반영위치':'권한보존 / tables.*.metadata.operational_review'},
    {'확인항목':'Dataiku 반환물 지속 보관·자동 재개·ACK 시점','상태':'일반 적재 전 ACK 경로 확인; 지속 보관 및 자동 재개 보장 미확인','필요한이유':'GENOS 작업 완료 이후에도 목표 Oracle 적재 실패를 복구','반영위치':'품질완료기준 Q05/Q06 / PLAN.txt'},
    {'확인항목':'현장 용량·조회 조건·DBA 물리 구성','상태':'행 수·증가량·CLOB/인덱스 용량·파티션 필요성 미실측','필요한이유':'등록 후 실제 DB 생성 및 운영 부하 확인','반영위치':'승인진행 DBA검토·물리객체정의'},
]
csv_out('METADATA_OPEN_ITEMS.csv',unresolved_rows)
plain=['메타마이너 등록용 설명 초안 — 2026-10-23 보완본',
       '상태: 미승인 후보. 9개 테이블·46개 컬럼의 코드/DDL 계약에 근거한 설명이며 실제 등록·DB 생성은 수행하지 않았습니다.',
       '담당자·보유기간·운영 시각·표준 식별값은 확인 필요로 표시했습니다. SQL의 <승인스키마>는 검토용 자리표시자입니다.',
       '이 텍스트는 붙여넣기용입니다. 필수 항목 전체는 엑셀의 Bizmeta/테이블설명/컬럼설명에도 있습니다.']
for key,t in mapping['tables'].items():
    plain += ['\n'+'='*64,t['candidate_name']+' / '+t['logical_name_ko'],t['metadata']['description_plain_text']]
    for col in t['columns'].values():
        plain += ['\n'+t['candidate_name']+'.'+col['candidate_name'],col['metadata']['description_plain_text']]
(OUT/'METAMINER_DESCRIPTIONS.txt').write_text('\n\n'.join(plain)+'\n')

changes = [
    ('공통 물리 매핑', '02_BACKEND/semantic_runtime/physical_mapping.py (제안 신규 모듈)', '엄격 YAML 로더·불변 SchemaMap·식별자 검증·논리/대상 hash; 현재 없음', 'Dataiku writer와 GENOS reader가 같은 계약 사용'),
    ('원문 적재·검증', '02_BACKEND/semantic_runtime/oracle_dp_io.py', 'OWNER/TABLES/COLUMNS/KEYS와 CLOB SQL·ALL_TAB_COLUMNS·PK 검사를 SchemaMap으로 해석', '내부 행 키/행 hash는 기존 계약 보존'),
    ('자산·원문 게시', '02_BACKEND/semantic_runtime/oracle_dp_assets.py', '자산과 게시의 owner/컬럼·CLOB 읽기/쓰기·정합성 검사 매핑', 'archive와 gold_support를 별도 owner로 허용; 필요 권한 확인'),
    ('조회 게시·채널', '02_BACKEND/semantic_runtime/oracle_query_catalog.py', 'RELEASE/ROW/ACTIVE/STATE·DDL·조건·CAS의 물리 이름 분리', 'content release와 물리 저장 binding을 별도 보존'),
    ('DB 스키마 검사', '02_BACKEND/lawrag/pipeline/oracle_query_publish.py', '고정 SIDDA DDL 정규식·이름 목록 대신 같은 구조 명세에서 DDL/검사 생성', '컬럼뿐 아니라 PK/FK/CHECK/index·NULL·BYTE/CHAR·정밀도 검증'),
    ('원문 읽기', '02_BACKEND/semantic_runtime/oracle_query_store.py', '고정 SIDDA 제거; SELECT alias와 조건/JOIN/CLOB 검사에 매핑 적용', '기존 내부 컬럼 이름과 source integrity 그대로 반환'),
    ('조회 행·JSON 투영', '02_BACKEND/semantic_runtime/oracle_query.py; oracle_query_db.py; oracle_query_index.py; oracle_query_fulltext.py', '물리 ROW 테이블·컬럼만 해석; JSON_TABLE의 논리 필드/manifest/허용 SQL 유지', '문서·용어·정의·구조·검색 reader 전부 회귀'),
    ('상태 읽기·쓰기', '02_BACKEND/semantic_runtime/oracle_query_state.py', 'agent 역할 owner와 컬럼·SQL 허용목록·revision CAS 변경', '작은 상태 포트; 현재 모든 대화 이력 저장이 완료된 것은 아님'),
    ('Dataiku 연결 식별', '02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py', '현재 identity에 profile/owner map/매핑 hash 결속을 추가', '같은 DB/connection 안 다른 schema도 다른 대상 binding'),
    ('파이프라인 인계 진입', '08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1/src/dataiku_run.py; pipeline_service_20261022_r3/runner_template.py', '프로필 선택→원격 작업 전 대상 preflight→manifest/receipt→적재 검증까지 연결', 'R3 인계본은 미지원; 수정 검증 뒤 새 client/service ZIP 필요'),
    ('다른 게시·이관 소비자', '02_BACKEND/lawrag/pipeline/oracle_migration.py; oracle_publish.py; oracle_query_package.py; oracle_full_package.py; oracle_clean_import.py', '활성 경로 전체 매핑; 정리/reset 대상과 외부 FK 검사도 역할별 해석', '이름 변경으로 기존 삭제 도구가 새/옛 대상 혼동하지 않게 차단'),
    ('실제 서빙 진입', 'service.py:_oracle_factory; 02_BACKEND/semantic_runtime/oracle_query_service.py:Factory', '요청 시작 시 명시 mapping/profile을 읽고 고정한 map을 Request/Snapshot에 전달', '작업 코드·선택 MAIN102·GENOS 리비전은 각각 새 검증 필요'),
    ('향후 지식·근거 adapter', '02_BACKEND/lawrag/legal_knowledge/adapters/oracle.py; 02_BACKEND/semantic_runtime/basis_links/oracle.py', '기존 table_map을 공통 registry로 확장; 컬럼은 전역 문자열 replace 대신 구조화 SQL 매핑', 'namespace 혼재와 Agent/Gold 물리 분리는 별도 구현'),
]
change_rows = [dict(zip(['영역','기존위치또는제안','변경계획','소비자검증'],x)) for x in changes]
csv_out('CODE_CHANGE_MAP.csv', change_rows)

extensions = []
for group,names,role,note in [
    ('Oracle adapter 존재', ['lk_record','lk_head','lk_lookup'], '혼재; namespace별 Gold/Agent 분리 설계', '현장 이름 미확정; 현재 9테이블 적재가 만들지 않음. operation/feedback을 지식과 일괄 배치하지 않음.'),
    ('Oracle adapter 존재', ['basis_head','basis_revision','basis_binding','basis_lineage'], 'Gold 후보', '관계 정본·판본 대응. table_map 주입; 현재 DEV 패키지 실행 경로와 구분.'),
    ('Oracle adapter 존재', ['basis_event','basis_receipt','basis_migration','basis_view_head'], 'Agent/처리·감사 역할 검토', '이벤트·receipt·세션 상태를 지식 테이블로 일괄 전환하지 않음.'),
]:
    for name in names:
        extensions.append({'대상':name,'확인상태':group,'목표저장책임':role,'이번범위':'후속 계획; 1차 9테이블 개명에서 제외','주의':note})
future = json.loads((ROOT/'07_DOCS/REFERENCE/REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/database/SCHEMA_DRAFT.json').read_text())
for t in future['tables']:
    name=t['name']
    if name in {'LK_RUN','LK_CLAIM','LK_USE'}: role='Agent'
    elif name in {'LK_OUTBOX','LK_SYNC'}: role='처리·동기화 상태'
    elif name=='LK_DEPENDENCY': role='지식/실행 의존 혼재; 분리 설계'
    elif name in {'LK_REVIEW','LK_CONTROL','LK_SCOPE_GATE','LK_RELEASE','LK_RELEASE_ITEM'}:role='Gold 지원 후보; 승인 검토'
    else:role='Gold 지식 후보'
    extensions.append({'대상':name,'확인상태':'v3 설계 초안; 현장 생성 아님','목표저장책임':role,
                       '이번범위':'후속 계획; 현재 이름은 승인 물리명 아님','주의':t['purpose']})
extensions.append({'대상':'sw_* / llm_wiki','확인상태':'현행 SQLite/artifact 소비자','목표저장책임':'지식 본문·근거 Gold / 질문·실행 Agent',
                   '이번범위':'별도 저장 adapter와 원문 anchor 이행 설계','주의':'WIKI_LINK는 참조만 보관. YAML 개명만으로 Oracle 저장 또는 전체 MAIN 연결이 구현되지 않음.'})
csv_out('FOLLOWUP_SCOPE.csv',extensions)

wb=Workbook();wb.remove(wb.active)
notes=[{'항목':'문서 상태','내용':'개발계 Silver → 승인 Gold 명명 전환 계획. 후보이며 DB·코드·배포 변경 없음.'},
       {'항목':'1차 전체 범위','내용':'현행 Oracle 9테이블 46컬럼. Gold 후보 7개 36컬럼; Agent 1개 5컬럼; 이관/보관 1개 5컬럼.'},
       {'항목':'개발·운영 이름','내용':'승인될 하나의 테이블/컬럼명 세트를 개발 Silver에서도 사용. owner/connection/권한은 환경별 매핑.'},
       {'항목':'후보 약어','내용':'LGL/PBLS 등 모두 제안. 전사 표준 단어·용어·도메인·인포타입 확인 필요. 영어·한글 30바이트 검사는 초안 UTF-8 기준이며 승인 문자셋 아님.'},
       {'항목':'YAML','내용':'physical_mapping.draft.yaml은 설계 초안. 현재 인계 R2/R3가 자동으로 읽지 않음.'},
       {'항목':'전체 목표와 구분','내용':'29개 연계·설계 테이블과 sw_* 계열은 후속범위 시트. 현재 파이프라인에 없던 테이블이 생성됐다는 뜻이 아님.'},
       {'항목':'타입','내용':'1차 후보는 현재 타입/NULL/PK/기본값 보존. 표준 도메인과 충돌하면 별도 codec/스키마 버전으로 검토.'},
       {'항목':'세부 계획','내용':'PLAN.txt의 코드 변경·실패 복구·검증·전환·롤백 기준 참조.'}]
notes.append({'항목':'설명 보완','내용':'Bizmeta·테이블설명·컬럼설명에 한글명, 업무 설명, 명칭/유형/레이어 선정 이유, 허용값, 산식, 주의·원천·예시 질의를 보완. YAML metadata와 동일 내용. 메타마이너 붙여넣기 TXT 제공.'})
notes.append({'항목':'확인 필요','내용':'확인필요 시트의 실제 owner·담당자·보유기간·시각·표준 승인 값은 미확정으로 보존. 작성 완료와 승인 완료를 구분.'})
notes.append({'항목':'운영 보완 6개 시트','내용':'컬럼계보·관계결합·적재재처리·품질완료기준·권한보존·승인진행. 추가 메타 설계이며 실행 정책·DB 적용 아님.'})
notes.append({'항목':'일반 적재 범위','내용':'현재 load_oracle은 7테이블 적재. query_active는 별도 활성화, query_state는 별도 소비자 연결. 9테이블 모두에 배치가 행을 넣어야 성공인 것은 아님.'})
notes.append({'항목':'완료와 ACK','내용':'GENOS 처리 완료와 Oracle 적재 완료를 구분. 현재 반환물 복원 후 ACK하므로 지속 보관 검증 또는 적재 후 ACK로 개선할 필요. 실제 개선 미구현.'})
for title,rows in [('읽어주세요',notes),('테이블명_9개',table_rows),('컬럼명_46개',column_rows),
                   ('Bizmeta',bizmeta_rows),('테이블설명',table_description_rows),
                   ('컬럼설명',column_description_rows),('필수항목대조',coverage),('확인필요',unresolved_rows),
                   ('코드변경',change_rows),('후속범위',extensions),
                   *((title,rows) for title,_,rows in operational_exports)]:
    ws=wb.create_sheet(title);ws.append(list(rows[0]))
    for row in rows:ws.append(list(row.values()))
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    for cell in ws[1]:cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(color='FFFFFF',bold=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    for i,header in enumerate(rows[0],1):
        ws.column_dimensions[get_column_letter(i)].width=75 if 'Description' in header else 48 if any(word in header for word in ['내용','설명','이유','규칙','의미','주의','질의','기준','산식']) else 27
    for i in range(2,ws.max_row+1):ws.row_dimensions[i].height=150 if title in {'테이블설명','컬럼설명','Bizmeta'} else 90
    ws.sheet_view.zoomScale=85
wb.save(OUT/'TABLE_COLUMN_MAPPING_PLAN.xlsx')
example_validation=build_example_workbook(ROOT,OUT,mapping,table_rows,column_rows)

# Static artifact checks, not a database/runtime test.
loaded=yaml.safe_load((OUT/'physical_mapping.draft.yaml').read_text())
assert loaded==mapping
assert len(mapping['tables'])==9
assert sum(len(t['columns']) for t in mapping['tables'].values())==46
assert {(r['현재테이블명'],r['현재컬럼명']) for r in column_rows} == {(r['현재물리테이블명'],r['현재물리컬럼명']) for r in source_columns}
for t in mapping['tables'].values():
    assert len(t['metadata']['description_fields'])==11
    assert all(isinstance(v,str) and v.strip() for v in t['metadata']['description_fields'].values())
    assert re.fullmatch('[A-Z][A-Z0-9_]*',t['candidate_name']) and len(t['candidate_name'].encode())<=30
    assert len({c['candidate_name'] for c in t['columns'].values()})==len(t['columns'])
    for c in t['columns'].values():
        assert all(c['metadata'][k].strip() for k in ['business_meaning','allowed_values','derivation','naming_rationale','type_rationale','description_plain_text','evidence'])
        assert re.fullmatch('[A-Z][A-Z0-9_]*',c['candidate_name']) and len(c['candidate_name'].encode())<=30
        assert len(c['logical_name_ko_candidate'].encode('utf-8'))<=30
    assert all(k in t['columns'] for k in t['primary_key'])
    for idx in t['indexes']: assert set(idx['columns'])<=t['columns'].keys() and len(idx['name_candidate'])<=30
    for fk in t['foreign_keys']:
        assert set(fk['columns'])<=t['columns'].keys()
        assert set(fk['target_columns'])<=mapping['tables'][fk['target_table']]['columns'].keys()
book=load_workbook(OUT/'TABLE_COLUMN_MAPPING_PLAN.xlsx',read_only=True)
assert book['테이블명_9개'].max_row==10 and book['컬럼명_46개'].max_row==47
assert book['Bizmeta'].max_row==10 and book['테이블설명'].max_row==10 and book['컬럼설명'].max_row==47
assert len(table_description_rows)==9 and len(column_description_rows)==46
for row in table_description_rows:
    table=next(t for t in mapping['tables'].values() if t['candidate_name']==row['테이블명후보'])
    assert table['metadata']['description_plain_text']==row['Description붙여넣기']
for row in column_description_rows:
    table=next(t for t in mapping['tables'].values() if t['candidate_name']==row['테이블명후보'])
    column=next(c for c in table['columns'].values() if c['candidate_name']==row['컬럼명후보'])
    assert column['metadata']['description_plain_text']==row['Description붙여넣기']
for sheet,filename,rows in [('Bizmeta','BIZMETA.csv',bizmeta_rows),
                            ('테이블설명','TABLE_DESCRIPTIONS.csv',table_description_rows),
                            ('컬럼설명','COLUMN_DESCRIPTIONS.csv',column_description_rows)]:
    assert read_csv(OUT/filename)==[{k:str(v) for k,v in row.items()} for row in rows]
    actual=list(book[sheet].values)
    assert actual[0]==tuple(rows[0])
    assert actual[1:]==[tuple(row.values()) for row in rows]
for table in mapping['tables'].values():
    assert table['metadata']['description_plain_text'] in '\n\n'.join(plain)
    for column in table['columns'].values():
        assert column['metadata']['description_plain_text'] in '\n\n'.join(plain)
assert len(book.sheetnames)==16
assert len(operational_exports[0][2])==46
assert {r['논리테이블ID'] for r in operational_exports[2][2]}==set(mapping['tables'])
assert sum(r['실행구분']=='일반 적재' for r in operational_exports[2][2])==7
for relation in mapping['operational_review']['relationships']:
    assert relation['출발논리ID'] in mapping['tables'] and relation['도착논리ID'] in mapping['tables']
for title,filename,rows in operational_exports:
    assert read_csv(OUT/filename)==[{k:str(v) for k,v in row.items()} for row in rows]
    assert list(book[title].values)==[tuple(rows[0]),*(tuple(row.values()) for row in rows)]
book.close()
paths=['02_BACKEND/semantic_runtime/oracle_dp_io.py','02_BACKEND/semantic_runtime/oracle_dp_assets.py',
       '02_BACKEND/semantic_runtime/oracle_query_catalog.py','02_BACKEND/semantic_runtime/oracle_query_store.py',
       '02_BACKEND/lawrag/pipeline/oracle_query_publish.py','02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py']
package=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3/GENOS_PIPELINE_SERVICE_20261022_R2.zip'
with zipfile.ZipFile(package) as z:
    parity={p:z.read('GENOS_PIPELINE_SERVICE_20261022_R2/'+p)==(ROOT/p).read_bytes() for p in paths}
assert all(parity.values())
evidence={'state':'DESIGN_ONLY','current_ddl_tables':9,'current_ddl_columns':46,
          'gold_candidate_tables':7,'gold_candidate_columns':36,'runtime_sources_equal_sealed_r2':parity,
          'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [DDL,BASE/'ORACLE_GOLD_TABLES.csv',BASE/'ORACLE_GOLD_COLUMNS.csv',ROOT/'00_SYSTEM/ARCHITECTURE.md',ROOT/WORKBOOK,*(ROOT/p for p in paths),ROOT/'02_BACKEND/lawrag/pipeline/oracle_migration.py',ROOT/'02_BACKEND/lawrag/pipeline/oracle_query_package.py',ROOT/'02_BACKEND/semantic_runtime/oracle_query_state.py',ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1/src/dataiku_run.py']},
          'artifact_checks':['all 9/46 current entries covered once','YAML roundtrip','physical candidates <=30 ASCII bytes',
                             'logical column candidates <=30 UTF-8 bytes (approval encoding pending)',
                             'PK/FK/index references resolve','46 column XLSX reload',
                             '9 tables x 11 Description fields present','46 column meanings/allowed values/derivations/rationales present',
                             'YAML, CSV, XLSX and paste text registration descriptions agree',
                             '46 lineage entries; 9 table load/access/approval reviews; 9 relationships; 10 quality checks',
                             '6 operational sheets roundtrip; 7 regular load targets and 2 separate consumers distinguished'],
          'metadata_table_count':9,'metadata_column_count':46,
          'operational_review_counts':{title:len(rows) for title,_,rows in operational_exports},
          'example_workbook':{'name':'DATAIKU_GOLD_EXAMPLE_FORMAT.xlsx',
                              'tables':example_validation['table_count'],
                              'columns':example_validation['column_count'],
                              'scope':'Visible photo layout; not an original XLSX clone'},
          'metadata_open_items':len(unresolved_rows),
          'standard_approval':'PENDING','runtime_mapping_implemented':False,'db_created':False,
          'silver_integration_test':'NOT_RUN','main_changed':False,'genos_deployed':False}
(OUT/'VALIDATION.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
artifact_paths=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='ARTIFACTS.json')
artifact_paths+=sorted(p for p in (OUT/'history').iterdir() if p.is_file())
manifest={'status':'DESIGN_ONLY_NOT_APPLIED','mapping_revision':mapping['mapping_revision'],
          'files':{str(p.relative_to(OUT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in artifact_paths}}
(OUT/'ARTIFACTS.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in evidence.items() if k not in {'source_sha256','runtime_sources_equal_sealed_r2'}},ensure_ascii=False))
