"""Separate the development request inventory from the production Gold design.

Creates workbooks only; never writes a database or product configuration.
"""
from pathlib import Path
from copy import copy
import argparse
import hashlib
import importlib.util
import json
import re
import zipfile

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREV = HERE.parent / 'DATAIKU_COLUMN_MASTER_20261027_R1'
spec = importlib.util.spec_from_file_location('r1', PREV / 'build_workbook.py')
r1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r1)
MAPPING = yaml.safe_load((r1.BASE / 'physical_mapping.yaml').read_text())
GOLD_KEYS = [k for k in r1.ORDER if MAPPING['tables'][k]['role'] in ('gold_knowledge', 'gold_support')]
DEV_FILE = HERE / '법규_개발계_테이블요청목록_20261027_R2.xlsx'
GOLD_FILE = HERE / '삼성증권_AI기반PI대표과제_법규_운영골드컬럼마스터_20261027_R2.xlsx'

def comment(text):
    return Comment(text, '작성 기준')

def finish(w, path):
    for ws in w:
        ws.sheet_view.zoomScale = 85
    w.properties.creator = 'Codex'
    w.properties.description = '2026-10-27 사용자 요청에 따른 개발계 요청 목록 / 운영 골드 설계 분리본. 실제 DB 변경 없음.'
    w.save(path)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None

def development():
    w = openpyxl.Workbook()
    ws = w.active
    ws.title = '테이블요청목록'
    ws.append(['No.', '과제', '연결명', '레이어', '스키마', '개발계 테이블명', '논리명', '컬럼수', '업무 용도', '요청 사항', '현행 배치 사용', '확인 결과'])
    for i, key in enumerate(r1.ORDER, 1):
        t = MAPPING['tables'][key]
        layer = '에이전트' if key == 'query_state' else '실버'
        use = '구조 검사 대상. 이번 원문 배치는 쓰지 않음.' if key in ('query_active', 'query_state') else '원문 배치의 적재·재조회 검증 대상.'
        ws.append([i, '법규 RAG', 'AIDP', layer, r1.owner(MAPPING, key), t['name'], r1.TABLES[key][0], len(t['columns']), r1.TABLES[key][1], '동일 객체가 있으면 구조 대조, 없으면 생성 검토. 필요한 계정의 조회·적재 권한 확인.', use, '담당자 기입'])
    r1.format_sheet(ws, [6, 15, 12, 12, 12, 28, 28, 10, 68, 64, 52, 24])
    cols = w.create_sheet('개발계컬럼')
    cols.append(['No.', '스키마', '테이블명', '컬럼번호', '현재 컬럼명', '현재 데이터 타입', '한글명', '현재 제약조건', 'PK', '컬럼 정의'])
    no = 0
    for key in r1.ORDER:
        t = MAPPING['tables'][key]
        for seq, (old, c) in enumerate(t['columns'].items(), 1):
            no += 1
            logical = r1.descfield(c['description'], '논리명(미승인 후보)')
            cols.append([no, r1.owner(MAPPING, key), t['name'], seq, c['name'], c['type'], logical, r1.constraints(MAPPING, key, old), 'Y' if old in t['pk'] else None, r1.COLS[c['name']][2]])
            cols.cell(cols.max_row, 10).comment = comment(c['description'])
    r1.format_sheet(cols, [6, 12, 28, 10, 26, 28, 26, 66, 6, 78])
    req = w.create_sheet('요청본문')
    req.append(['항목', '내용'])
    for row in [
        ('제목', '[법규 RAG] 개발계 SIDDS·SIDDA 테이블 생성·구조·접근권한 확인 요청'),
        ('요청 대상', '실버 SIDDS 8테이블·41컬럼, 에이전트 SIDDA 1테이블·5컬럼. 총 9테이블·46컬럼.'),
        ('요청 내용', '첨부 목록의 개발계 객체를 확인해 주세요. 기존 객체는 재생성하지 않고 컬럼·타입·PK·CHECK·FK·인덱스를 대조해 주시고, 미존재 객체는 지정 스키마로 생성 가능한지 확인 부탁드립니다.'),
        ('연결·스키마', 'Dataiku 연결은 AIDP입니다. AIDP는 연결 이름이며 owner는 SIDDS 또는 SIDDA입니다. 테이블의 _S·_A 접미사를 유지합니다.'),
        ('접근권한', '원문 배치 적재 대상 7표는 실제 배치 계정의 SELECT·INSERT, 조회 소비자는 담당자가 승인한 범위의 SELECT가 필요합니다. 조회채널·실행상태는 이번 배치의 검사 대상입니다. 활성화·상태 쓰기 권한은 해당 소비자 연결 시 별도 확정합니다.'),
        ('제약·인덱스', 'PK 9개, 명시 CHECK 6개, FK 1개, 추가 조회 인덱스 4개입니다. FK는 LGL_SRCH_CHNL_S.SRCH_PBLS_ID → LGL_SRCH_PBLS_S.SRCH_PBLS_ID입니다.'),
        ('보존', '기존 테이블의 이름 변경·삭제·데이터 이동을 요청하는 목록이 아닙니다. 현장 생성·적재 완료 여부는 담당자 확인 결과를 기록해 주세요.'),
        ('운영계 구분', '운영 골드 SIDDG의 명명·타입 변경안은 별도 운영골드컬럼마스터에 있습니다. 이 개발계 요청 목록에는 적용하지 않습니다.'),
        ('정의 근거', 'pipeline_layers_20261027_r1/01_CREATE_TABLES.sql 및 physical_mapping.yaml. 최신 pipeline_stateless_20261027_r1 전달 ZIP의 같은 파일과 일치.'),
    ]:
        req.append(row)
    r1.format_sheet(req, [28, 125])
    indexes = w.create_sheet('추가인덱스')
    indexes.append(['스키마', '테이블명', '인덱스명', '인덱스 컬럼', '구분'])
    for key, t in MAPPING['tables'].items():
        for idx in t['indexes']:
            indexes.append([r1.owner(MAPPING, key), t['name'], idx['name'], ', '.join(t['columns'][x]['name'] for x in idx['columns']), 'PK 인덱스 외 추가 조회 인덱스'])
    r1.format_sheet(indexes, [12, 28, 36, 85, 40])
    finish(w, DEV_FILE)
    return DEV_FILE

def target_col(c):
    old = c['name']
    name, logical, definition = r1.COLS[old]
    datatype = c['type']
    conversion = '기존 값을 변환 없이 보존한다.'
    rule = '명칭과 도메인 표기 정리. 타입·길이는 현재 저장 계약 보존.'
    # These long identifiers are not the UUID-sized generic DOC_ID in the sample.
    overrides = {
        'DATA_VER_ID': ('DATA_VER_ID', '데이터구축세대ID'),
        'DOC_ID': ('LGL_DOC_ID', '법규문서ID'),
        'UNIT_ID': ('LGL_UNIT_ID', '법규구조단위ID'),
        'PRNT_UNIT_ID': ('PRNT_LGL_UNIT_ID', '상위법규구조단위ID'),
        'BLK_ID': ('LGL_BLK_ID', '법규본문조각ID'),
        'DOC_NM': ('DOC_NAME_CTNT', '문서명내용'),
    }
    if old in overrides:
        name, logical = overrides[old]
    if old == 'DOC_NM':
        rule = '길이 제한 없는 현재 문서명 보존. CLOB의 내용 도메인에 맞춰 문서명내용으로 작성.'
    elif old == 'JSON_TXT_OMIT_YN':
        datatype = 'CHAR(1)'
        definition = 'JSON 안의 중복 본문을 생략했는지 표시한다. Y는 생략, N은 미생략이며 NULL은 원천의 미지정 상태다. 원문 본문 자체의 부재를 뜻하지 않는다.'
        conversion = '1→Y, 0→N, NULL→NULL. 다른 값은 적재 오류로 분리한다. 역변환은 Y→1, N→0, NULL 유지.'
        rule = '첨부 여부 도메인에 맞춰 CHAR(1), Y·N 값 CHECK, 원천 NULL 보존으로 수정.'
    elif old == 'REG_DTM':
        datatype = 'TIMESTAMP(6)'
        logical = '원문게시등록일시'
        definition = '원문 게시 행이 DB에 등록된 한국 시간(Asia/Seoul) 기준 일시. 운영 저장값에는 시간대 표기를 포함하지 않는다.'
        conversion = "기존 시간대 포함 값을 Asia/Seoul로 변환 후 TIMESTAMP(6)에 저장한다. 세션 시간대에 맡기지 않는다. 원천 등록시각은 개발계와 이행 이력에 보존한다."
        rule = '첨부 일시 타입 TIMESTAMP(6) 적용. 한국 시간으로 변환 후 저장하며 신규 기본값도 동일 기준.'
    elif old.endswith('_ID'):
        rule = 'ID 식별자 예외 적용. 문서·단위·본문 ID는 현행 512 BYTE를 보존하고 범용 36자 UUID로 축소하지 않음.'
    return dict(name=name, logical=logical, type=datatype, nullable=c['nullable'], definition=definition, conversion=conversion, rule=rule)

def gold(agent):
    assert re.fullmatch(r'[A-Z][0-9]{2}', agent), '정확한 에이전트번호 필요 (예: A06)'
    w = openpyxl.load_workbook(r1.TEMPLATE)
    for ws in w:
        ws.delete_rows(2, ws.max_row)
    t_ws, c_ws = w['테이블'], w['컬럼']
    headers = {s.title: [c.value for c in s[1]] for s in w}
    model = {}
    for key in GOLD_KEYS:
        source = MAPPING['tables'][key]
        model[key] = dict(name='IDD_' + agent + '_' + source['name'][:-2], schema='SIDDG', columns={old: target_col(c) for old, c in source['columns'].items()}, pk=source['pk'])
    def name(k, old):
        return model[k]['columns'][old]['name']
    def target_constraints(key, old):
        source, target = MAPPING['tables'][key], model[key]
        c = target['columns'][old]
        parts = ['NULL 허용' if c['nullable'] else 'NOT NULL']
        if old in target['pk']:
            parts.append('PK(' + ', '.join(name(key, x) for x in target['pk']) + ')')
        for check in source['checks']:
            if old not in check['columns']:
                continue
            if check['kind'] == 'is_json':
                parts.append('CHECK(' + c['name'] + ' IS JSON)')
            elif check['kind'] == 'revision':
                parts.append('CHECK(' + c['name'] + ' >= 1)')
        for fk in source['foreign_keys']:
            if old in fk['columns']:
                parts.append('FK(SIDDG.' + model[fk['target']]['name'] + '.' + name(fk['target'], fk['target_columns'][0]) + ')')
        if old == 'JSON_TEXT_ELIDED':
            parts.append("CHECK(JSON_TXT_OMIT_YN IN ('Y','N'))")
        if old == 'CREATED_AT':
            parts.append("DEFAULT CAST(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul' AS TIMESTAMP(6))")
        return '\n'.join(parts)

    for key in GOLD_KEYS:
        source, target = MAPPING['tables'][key], model[key]
        logical, definition, origin, process, classification = r1.TABLES[key]
        for k, t in model.items():
            origin = origin.replace(MAPPING['tables'][k]['name'], t['name'])
        origin = origin.replace('LGL_FILE_PART_S', '별도 파일 보관 영역의 파일 목록·해시')
        t_ws.append([agent, 'SIDDG', '신규 생성', target['name'], logical, definition, origin, '반영 — 운영 골드 이름과 논리명 작성. IDD_' + agent + '_ 형식, _G 접미사 없음.'])
        t_ws.cell(t_ws.max_row, 3).comment = comment('운영계 신규 모델로 작성. 실제 운영 DB 존재 여부는 확인하지 않았습니다. 개발계 물리명은 별도 개발계 요청 목록 및 개발운영매핑 시트에서 확인합니다.')
        for seq, (old, current) in enumerate(source['columns'].items(), 1):
            col = target['columns'][old]
            review = col['rule']
            reflected = '반영 — 운영 설계에 적용.'
            if current['name'] != col['name']:
                reflected += ' ' + current['name'] + ' → ' + col['name'] + '.'
            if current['type'] != col['type']:
                reflected += ' ' + current['type'] + ' → ' + col['type'] + '.'
            definition = col['definition']
            if key == 'query_row' and old == 'DOCUMENT_ID':
                definition = '조회 자료가 속한 문서의 식별자. 문서별 조회 권한을 제한하는 데 쓰며 공통 용어집 등 문서 비소속 행은 NULL일 수 있다.'
            c_ws.append([agent, 'SIDDG', target['name'], current['name'], seq, current['type'], col['name'], col['logical'], col['type'], review, reflected, target_constraints(key, old), 'Y' if old in target['pk'] else None, definition, r1.korean(current)])
            r = c_ws.max_row
            c_ws.cell(r, 9).comment = comment(col['conversion'])
            c_ws.cell(r, 14).comment = comment('현재 코드의 업무 의미·허용값·생성 근거:\n' + current['description'] + '\n운영 변환 규칙: ' + col['conversion'])
            c_ws.cell(r, 15).comment = comment('Y는 원문 또는 식별자에 한글 저장 가능. N은 숫자·영문·해시 또는 ASCII 직렬화 계약. ASCII JSON은 한글을 \\u 형태로 보존하므로 해석한 내용에는 한글이 있을 수 있습니다. 전수 값 실측 결과는 아닙니다.')

    cross = w.create_sheet('개발운영매핑')
    cross.append(['개발 스키마', '개발 테이블', '개발 컬럼', '개발 타입', '운영 스키마', '운영 테이블', '운영 컬럼', '운영 타입', '데이터 변환 규칙', '소비자 변경'])
    for key in GOLD_KEYS:
        source, target = MAPPING['tables'][key], model[key]
        for old, current in source['columns'].items():
            c = target['columns'][old]
            consumer = '운영 매핑에서 새 이름으로 적재·조회한다. JSON 내부 필드명·원문 ID 값은 바꾸지 않는다.'
            if old in ('JSON_TEXT_ELIDED', 'CREATED_AT'):
                consumer = '적재 시 변환기를 적용하고 조회 소비자의 타입 계약을 맞춘 뒤 이행·재조회 검증한다.'
            cross.append([r1.owner(MAPPING, key), source['name'], current['name'], current['type'], 'SIDDG', target['name'], c['name'], c['type'], c['conversion'], consumer])
    biz = w.create_sheet('Bizmeta')
    biz.append(['No.', '에이전트번호', '스키마', '테이블명', '데이터논리명', '데이터출처', '데이터유형', '데이터 가공 프로세스 설명', '생성시각', '등록 구분'])
    for i, key in enumerate(GOLD_KEYS, 1):
        target = model[key]
        logical, definition, origin, process, classification = r1.TABLES[key]
        origin = '법제처 등 외규·현업 업로드 내규의 구조화 결과 및 게시 자료' if key != 'query_active' else '운영 조회게시 표의 완료 게시본과 채널 선택 요청'
        timing = '원문·검색 자료 구축과 검증 완료 시 생성. 외규 일일 갱신·내규 업로드 반영을 목표로 하며 운영 실행 시각은 배치 설정으로 관리.'
        if key == 'query_active':
            timing = '완료된 조회 게시본을 명시적으로 선택·변경할 때.'
        biz.append([i, agent, 'SIDDG', target['name'], logical, origin, 'MASTER' if key == 'query_active' else 'SNAPSHOT', process, timing, '지식 데이터' if MAPPING['tables'][key]['role'] == 'gold_knowledge' else '게시·조회 운영지원'])

    rules = w.create_sheet('등록정보')
    rules.append(['항목', '작성 내용', '등록·적용 상태'])
    for row in [
        ('문서 범위', '운영 골드 7테이블·36컬럼. 개발계 9테이블·46컬럼 요청 목록은 별도 파일.', '운영 설계 작성본 R2'),
        ('명명 기준', 'SIDDG / IDD_' + agent + '_테이블명. 운영 테이블명에 개발계 _S·_A 또는 _G를 붙이지 않음.', '첨부 양식에 맞춘 명명안; 사내 메타 등록 승인 전'),
        ('현재 / TOBE', '테이블의 현재는 운영 신규 생성 상태. 컬럼의 현재 이름·타입은 개발 계약 비교값이며 TOBE가 운영 작성값.', '본 파일의 반영 표시는 설계 표 수정 완료를 뜻함'),
        ('표준용어', '내용 CTNT, 값 VALU, 명 NAME, 일시 DATE_TIME, 여부 YN, 식별자 ID의 도메인 표기를 통일. 현재 문서명 CLOB은 문서명내용으로 작성.', '표준사전 조회·신규 용어 신청·승인번호는 별도 확보'),
        ('타입·길이', 'ID·해시·검색키의 기존 바이트 길이를 보존한다. CLOB을 실측 없이 짧은 VARCHAR2로 축소하지 않는다.', '문자셋·BYTE/CHAR·한글 최대 길이를 현장 표준 인포타입과 대조'),
        ('여부값', 'NUMBER(1)의 0/1/NULL → CHAR(1)의 N/Y/NULL. 운영 CHECK는 Y·N만 허용하되 NULL을 허용한다.', '소비자 변환·원천 범위 검사·NULL 보존·왕복 검증 후 이행'),
        ('등록일시', 'TIMESTAMP(6), Asia/Seoul 기준. 과거 값은 시간대 변환 후 저장, 신규 기본값도 한국 시간으로 명시.', '시간대 변환·소수초 정밀도·운영 조회 의미 확인 후 이행'),
        ('관계·제약', 'PK 7개, CHECK 4개(기존 JSON 2·변경순번 1·추가 여부 1), FK 1개, 추가 조회 인덱스 4개. 기존 논리 관계를 임의 FK로 추가하지 않는다.', '제약의 컬럼명·참조 대상은 모두 운영 명칭으로 작성'),
        ('NULL·JSON', '기존 NULL 허용을 보존한다. 원문 문서·구조·본문·게시 JSON에 없던 IS JSON 제약은 임의로 추가하지 않는다. 원천 형식과 소비자 검증을 유지한다.', '원천 JSON·NULL·빈 CLOB 및 내용 해시 이행 검증 필요'),
        ('운영 골드 제외', '실행상태는 에이전트 레이어, 파일분할보관은 별도 보관 영역으로 관리한다. 골드 7표에 합치지 않는다.', '두 표는 개발계 요청 목록에 보존'),
        ('후속 지식', '온톨로지·숏컷·위키의 별도 물리 모델은 이 9표의 원문 적재 DDL에 포함되지 않는다. 전용 모델이 추가되면 검토·승인·소비자 연결을 함께 작성한다.', '이번 파일로 전용 모델 구현·등록 완료를 뜻하지 않음'),
        ('등록 요청', '표준단어·용어·도메인·인포타입 대조, 업무 오너·보유기간·운영 배치시각 확정, 메타 신청·승인 후 DBA 생성 요청.', '신청번호·승인번호·DBA 생성 결과 미확보'),
        ('검증 범위', '현재 정의와 운영 모델의 36컬럼 대응, 명칭 중복·길이·도메인, PK·FK·CHECK·타입·변환 규칙 일치 점검.', 'DB·코드·MAIN 변경 및 사내 운영계 실행 없음'),
    ]:
        rules.append(row)
    idx = w.create_sheet('추가인덱스')
    idx.append(['스키마', '운영 테이블명', '운영 인덱스명', '운영 인덱스 컬럼', '용도'])
    for key in GOLD_KEYS:
        for i, old in enumerate(MAPPING['tables'][key]['indexes'], 1):
            idx.append(['SIDDG', model[key]['name'], model[key]['name'] + '_I' + str(i), ', '.join(name(key, c) for c in old['columns']), '게시본·유형 범위의 검색키/소속/대상/문서 점조회'])
    r1.format_sheet(t_ws, [12, 12, 20, 32, 28, 66, 60, 60])
    r1.format_sheet(c_ws, [12, 12, 32, 26, 8, 25, 27, 26, 25, 55, 58, 76, 6, 68, 12])
    r1.format_sheet(cross, [12, 28, 26, 25, 12, 32, 27, 25, 94, 80])
    r1.format_sheet(biz, [6, 12, 12, 32, 28, 64, 14, 76, 76, 28])
    r1.format_sheet(rules, [28, 120, 80])
    r1.format_sheet(idx, [12, 32, 36, 90, 65])
    for ws in (t_ws, c_ws):
        ws.freeze_panes = 'D2'
        for c in ws[1]:
            c.comment = comment('运营 골드 설계 작성본입니다. 이름·타입의 사내 표준 승인과 DB 생성은 별도입니다.'.replace('运营', '운영'))
    for row in c_ws.iter_rows(min_row=2):
        row[10].fill = PatternFill('solid', fgColor='E2F0D9')
        if row[5].value != row[8].value:
            row[8].fill = PatternFill('solid', fgColor='FFF2CC')
    c_ws['L1'].comment = comment('TOBE 운영 제약조건. PK·FK·CHECK·DEFAULT 모두 운영 명칭과 타입 기준입니다.')
    finish(w, GOLD_FILE)
    (HERE / 'gold_model.json').write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n')
    validate_gold(model, headers)
    return GOLD_FILE

def validate_gold(model, headers):
    w = openpyxl.load_workbook(GOLD_FILE)
    assert w['테이블'].max_row == 8 and w['컬럼'].max_row == 37
    assert w['개발운영매핑'].max_row == 37
    assert [c.value for c in w['테이블'][1]] == headers['테이블']
    assert [c.value for c in w['컬럼'][1]] == headers['컬럼']
    tables = set()
    for key, t in model.items():
        assert t['schema'] == 'SIDDG'
        assert re.fullmatch('[A-Z][A-Z0-9_]{0,29}', t['name'])
        assert t['name'] not in tables
        tables.add(t['name'])
        names = set()
        assert len(t['columns']) == len(MAPPING['tables'][key]['columns'])
        for old, c in t['columns'].items():
            assert re.fullmatch('[A-Z][A-Z0-9_]{0,29}', c['name'])
            assert c['name'] not in names
            names.add(c['name'])
            assert len(c['logical'].encode()) <= 30 and ' ' not in c['logical']
            assert c['nullable'] == MAPPING['tables'][key]['columns'][old]['nullable']
            assert c['name'].endswith(('_ID', '_CTNT', '_VALU', '_YN', '_TIME', '_NAME', '_NO'))
    for row in w['컬럼'].iter_rows(min_row=2, values_only=True):
        assert row[1] == 'SIDDG' and row[2] in tables
        if row[3] == 'JSON_TXT_OMIT_YN':
            assert row[8] == 'CHAR(1)' and "IN ('Y','N')" in row[11] and 'NULL 허용' in row[11]
        if row[3] == 'REG_DTM':
            assert row[8] == 'TIMESTAMP(6)' and 'Asia/Seoul' in row[11]
        if row[3] == 'DOC_ID':
            assert row[6] == 'LGL_DOC_ID' and row[8] == 'VARCHAR2(512 BYTE)'
    allnames = '\n'.join(str(c.value or '') for ws in (w['테이블'], w['컬럼']) for row in ws for c in row)
    assert 'IDD_XXX_' not in allnames and 'SIDDS' not in allnames and 'SIDDA' not in allnames
    assert 'LGL_EXEC_ST_A' not in allnames and 'LGL_FILE_PART_S' not in allnames
    assert len(list(w['추가인덱스'].iter_rows(min_row=2))) == 4

def manifest(files, agent):
    result = {'version': '20261027-R2', 'status': 'VALIDATED', 'agent_number': agent,
              'dev_tables': 9, 'dev_columns': 46, 'gold_tables': 7 if agent else None, 'gold_columns': 36 if agent else None,
              'database_modified': False, 'metadata_approval_verified': False,
              'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    (HERE / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent')
    args = parser.parse_args()
    files = [development()]
    if args.agent:
        files.append(gold(args.agent))
    manifest(files, args.agent)
