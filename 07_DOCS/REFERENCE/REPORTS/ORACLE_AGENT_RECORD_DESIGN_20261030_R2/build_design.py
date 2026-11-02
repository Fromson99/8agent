"""R2 compact Agent schema review artifacts. No database connections or mutations."""
from pathlib import Path
import importlib.util
import json
import hashlib
import csv
import re
import ast

OUT=Path(__file__).resolve().parent
BASE=OUT.parent/'ORACLE_AGENT_RECORD_DESIGN_20261030_R1'/'build_design.py'
spec=importlib.util.spec_from_file_location('agent_design_shared',BASE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.OUT=OUT;m.TABLES=[];m.EXPECTED_NEW_TABLE_COUNT=3;m.DESIGN_LABEL='R2'
H,N,T=m.H,m.N,m.T

m.table('run','LGL_AGT_RUN_A','에이전트실행정보',
        '실행 목록·요청 멱등 연결·복구 후보를 찾는 작은 색인. 상세는 공통 기록/기존 상태 표',[
    m.S,
    ('실행키해시값','RUN_KEY_HASH_VAL',H,False,'버전 있는 namespace+원 run ID의 해시. 원 ID는 본문 보존'),
    ('대화키해시값','SESS_KEY_HASH_VAL',H,True,'인증 주체와 원 세션 ID 결속; 비대화 실행 NULL'),
    ('요청키해시값','REQ_KEY_HASH_VAL',H,False,'주체·세션·원 request ID 결속. 멱등 소유권은 기존 상태 표'),
    ('부모실행키해시값','PRNT_RUN_KEY_HASH_VAL',H,True,'부모 실행; 없는 경우 NULL'),
    ('상태코드','ST_CD','VARCHAR2(32 BYTE)',False,'원 상태를 보존하는 복구 조회용 투영. 최종 상태는 transaction에서 결속'),
    ('시작일시','STRT_DTTM',T,False,'최초 실행 시작; 원 시각 문자열도 상세에 보존'),
    ('변경일시','CHG_DTTM',T,False,'실행 상태 마지막 변경; DB 시각 사용'),
    m.B,
],['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL'],[
    ['SCOPE_HASH_VAL','SESS_KEY_HASH_VAL','STRT_DTTM','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','REQ_KEY_HASH_VAL','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','PRNT_RUN_KEY_HASH_VAL','RUN_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','ST_CD','CHG_DTTM','RUN_KEY_HASH_VAL'],
])

m.table('record','LGL_AGT_REC_A','에이전트공통기록정보',
        '대화·사건·판단·근거·호출·연결·색인을 종류별 계약으로 통합. 본문은 별도',[
    m.S,
    ('소유객체키해시값','OWNER_KEY_HASH_VAL',H,False,'실행/세션/사건/승인된 공간 등 종류를 포함한 안정 소유키'),
    ('기록종류코드','REC_KIND_CD','VARCHAR2(64 BYTE)',False,'명시 registry의 종류; 임의 종류를 묵인하지 않음'),
    ('기록키해시값','REC_KEY_HASH_VAL',H,False,'종류·원 저장소 ID·원 PK tuple 결속. 원 PK값은 상세 보존'),
    ('기록판본순번','REC_REV_NO',N,False,'1 이상은 불변 보존판본, 0은 재생성 가능한 현재/검색 투영. 원 판본과 별도'),
    ('정렬순번','ORD_SEQ_NO',N,False,'사건 seq·질문 ordinal·span 순서·우선순위 등 종류별 한 가지 의미; 비정렬은 0'),
    ('조회키해시값','LOOKUP_HASH_VAL',H,True,'등록된 상태/원문/용어/관계 끝점의 조회키. 복수 조회는 IX 종류 행으로 추가'),
    m.B,
],['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_KEY_HASH_VAL','REC_REV_NO'],[
    ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_REV_NO','ORD_SEQ_NO','REC_KEY_HASH_VAL'],
    ['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_REV_NO','LOOKUP_HASH_VAL','ORD_SEQ_NO'],
    ['SCOPE_HASH_VAL','REC_KIND_CD','REC_REV_NO','LOOKUP_HASH_VAL','REC_KEY_HASH_VAL','OWNER_KEY_HASH_VAL'],
])

m.table('body','LGL_AGT_BODY_A','에이전트본문조각정보',
        '큰 입출력·원기록을 정확 바이트로 분할 보관. codec/hash/크기/개수는 조각 JSON에 보존',[
    m.S,
    ('본문해시값','BODY_HASH_VAL',H,False,'전체 복원 바이트 SHA256. 같은 권한 영역 안에서만 중복 공유'),
    ('조각순번','PART_SEQ_NO',N,False,'0=완성 manifest, 1..N=데이터. manifest는 모든 조각 대조 뒤 마지막에 추가'),
    ('조각JSON내용','PART_JSON_CN','CLOB',False,'ASCII JSON: codec·원/저장 hash·크기·base64. 0번에는 전체 조각수/크기/hash/format'),
],['SCOPE_HASH_VAL','BODY_HASH_VAL','PART_SEQ_NO'])

old_target=m.target
old_note=m.korean_note


def target(item):
    keys=old_target(item)[0].split(',')
    return ','.join(dict.fromkeys(k if k in {'run','state','body'} else 'record' for k in keys)),''


def note(item):
    n=item['table'];extra=''
    if n in m.EDGES:extra=' 양방향 조회는 REF_OUT/REF_IN 투영 행; 원 관계는 불변 판본.'
    elif n in {'model_attempt','workflow_call','ad_language_call'}:extra=' CALL 보존판본 + 현재판본(0) + 상태 조회키. 별도 호출 표 없음.'
    elif n=='session':extra=' SESSION 기록 + 사용자/팀 조회 투영. 별도 대화 표 없음.'
    elif n=='event' or n.endswith('_event'):extra=' EVENT 고정 종류로 원 사건마다 불변 1판본; 원 event kind는 본문과 IX에 보존, ORD_SEQ_NO로 증분 조회.'
    return old_note(item)+extra


m.target=target;m.korean_note=note


def project(item,col):
    """Design mapping only. Not executable row migration/semantic certification."""
    n,g=item['table'],item['group'];c=col['name']
    if n=='journal_blob_v1':
        return 'BODY.PART_JSON_CN; 원 codec/size/hash를 복원하여 새 manifest와 연결'
    if g=='journal-v6' and n=='run':
        return {'run_id':'RUN.RUN_KEY_HASH_VAL의 입력 + 본문 원 ID',
                'status':'RUN.ST_CD + REC 보존판본 + STATE 현재 상태',
                'started_at':'RUN.STRT_DTTM + 원 시각 문자열',
                'query_id':'RUN.REQ_KEY_HASH_VAL의 결속 입력; 원 query ID도 별도 보존',
                'deadline_at':'STATE 요청 deadline + REC 원값',
                'binding_hash':'REC 상세의 원 binding_hash; 목표 BODY 해시로 치환 금지'}.get(c,'REC의 원 run 상세 + 필요 시 STATE 현재 투영')
    if n=='event' or n.endswith('_event'):
        if c in {'seq','id'}:return 'REC.ORD_SEQ_NO 또는 REC_KEY_HASH_VAL의 종류별 입력 + 원값'
        return 'REC(EVENT).BODY_HASH_VAL → BODY 복원 원 사건 필드'
    if n in m.EDGES:return 'REC(관계 원판본) + REC(REF_OUT/REF_IN) LOOKUP_HASH_VAL 투영; 원 컬럼 모두 본문 보존'
    if n in {'model_attempt','workflow_call','ad_language_call'}:
        return {'status':'REC(CALL,판본0).LOOKUP_HASH_VAL 상태 조회키 + 원 ST 값',
                'attempt_id':'REC_KEY_HASH_VAL의 입력 + 원 attempt ID',
                'call_id':'REC_KEY_HASH_VAL의 입력 + 원 call ID',
                'attempt_no':'CALL 원 본문; 논리호출·시도 조합 IX 키',
                'view_id':'CALL 원 본문 + REF_VIEW 투영'}.get(c,'REC(CALL).BODY_HASH_VAL → 원 입력/출력/영수증/사용량')
    if n=='session':return 'REC(SESSION).BODY_HASH_VAL → 원 식별값; 사용자/팀 IX 해시의 입력'
    if n in m.STATES:return 'STATE.ST_JSON_CN 현재 값 + REC 불변 판본; 기존 상태 hash 계약 유지'
    return 'REC(종류별 원 행).BODY_HASH_VAL → BODY 원 컬럼값; 필요한 검색만 IX 행으로 투영'


def main():
    m.main()
    schema=json.loads((OUT/'schema_proposal.json').read_text())
    schema['revision']='R2';schema['replaces_design']='../ORACLE_AGENT_RECORD_DESIGN_20261030_R1'
    schema['all_agent_columns_including_reused']=26
    schema['role_mapping']={k:('record' if k in {'session','event','edge','call'} else k)
                            for k in ['session','run','event','record','edge','call','body','state']}
    m.write_json('schema_proposal.json',schema)
    data=json.loads((OUT/'source_inventory.json').read_text())
    rows=[]
    for item in data['tables']:
        for col in item['columns']:
            rows.append([item['group'],item['table'],col['name'],col['definition'],
                         target(item)[0],project(item,col),
                         '원 컬럼명·값·NULL·원 PK·원 검증 hash 무손실 보존; 실제 이관 코드 아님',item['source']])
    headers=['원장군','기존표','기존컬럼','기존정의','목표역할','컬럼투영·본문위치','보존계약','근거파일']
    m.write_csv('existing_column_mapping.csv',headers,rows)
    from openpyxl import load_workbook
    path=OUT/'Agent_테이블컬럼_및_기록대응_R2.xlsx'
    wb=load_workbook(path);del wb['기존컬럼대응']
    m.sheet(wb,'기존컬럼대응',headers,rows,[20,30,28,65,24,95,85,70])
    m.sheet(wb,'R1대비축소',['항목','R1 초안','R2 제안','설명'],[
        ['신규 표',7,3,'세션/사건/판단/연결/호출을 공통 기록 표에 통합'],
        ['신규 컬럼',85,21,'인덱스에 필요한 식별·종류·순번만 컬럼. 나머지는 원값 JSON'],
        ['기존 상태',5,5,'1표·5컬럼 그대로 재사용. 새 다중행 transaction adapter 필요'],
        ['Gold DDL',0,0,'기존 13표·60컬럼 유지'],
        ['실행 인덱스',16,9,'바인딩·단계·deadline·결과 상세는 REC/STATE'],
        ['공통 기록',None,8,'불변판본과 현재/검색 투영을 구분; 종류별 계약 필수'],
        ['본문 조각',11,4,'압축·크기·hash·개수는 조각 JSON에 보존'],
        ['교환 조건','표별 전용 SQL','종류별 adapter + 투영 행','표 수 감소는 코드 작업량·통신 감소와 같지 않음'],
        ['검토 상태','초안 보존','현재 검토안','미등록·미생성·Oracle 미검증'],
    ],[22,28,36,95])
    m.sheet(wb,'조회계약',['ID','업무 조회','제안 접근 인덱스','미구현·미검증 경계'],[
        ['Q01','세션별 실행 목록','RUN I1','인증된 세션; 시각/키 페이지, 상태 변경은 보일 수 있음'],
        ['Q02','요청별 실행 목록','RUN I2 + STATE PK','목록만으로 요청 멱등 소유권이 생기지 않음'],
        ['Q03','상태별 복구 후보','RUN I4','lease/fence/budget 재검증; 후보 조회는 전송 허가가 아님'],
        ['Q04','모든 종류의 사건 증분','REC I1','고정 EVENT·판본1·원장별 seq와 watermark'],
        ['Q05','정정 전후 보존판본','REC PK','보존판본1 이상; 현재 투영0 제외'],
        ['Q06','실행 안의 상태별 호출','REC I2','현재 CALL + 상태 조회키; 원 전송 영수증 확인'],
        ['Q07','출처·원문 연결 정/역방향','REC I2','정확 끝점 판본과 원 REF/head 대조'],
        ['Q08','현재 정확 기록','REC PK','STATE head/revision와 결속 확인'],
        ['Q09','원장 밖 등록 검색 후보','REC I3','각 owner 현재 ACL; 기존 위키 순위/승인 동등성은 별도'],
        ['Q10','완성 본문 manifest','BODY PK','권한 있는 원기록 참조에서만 읽기'],
        ['Q11','본문 조각 묶음','BODY PK','CLOB 잘림·누락·전체 크기/hash 검증 필요'],
    ],[12,32,26,105])
    wb.save(path)
    v=json.loads((OUT/'validation.json').read_text())
    checks=v['checks']
    def check(name,passed,detail):
        checks.append(dict(name=name,passed=bool(passed),detail=detail))
        if not passed:raise AssertionError(name)
    check('r2_counts',len(m.TABLES)==3 and sum(len(t['columns']) for t in m.TABLES)==21,'3표21컬럼 + 기존1표5컬럼')
    check('r2_projection_rows',len(rows)==832,'정적 소스 컬럼별 투영/본문 보존 위치 작성')
    import sqlglot
    sql=(OUT/'agent_schema_review.sql').read_text().replace('__AGENT_OWNER__','DESIGN_AGENT')
    # sqlglot does not parse these owner-qualified CREATE INDEX statements.
    # Check table grammar and index definitions separately; neither is a DB trial.
    statements=[s.strip() for s in re.sub(r'--[^\n]*','',sql).split(';') if s.strip()]
    table_sql=[s for s in statements if s.startswith('CREATE TABLE ')]
    parsed=[sqlglot.parse_one(s,read='oracle') for s in table_sql]
    check('oracle_create_table_parser',len(parsed)==3 and all(
          isinstance(x,sqlglot.exp.Create) and x.args.get('kind')=='TABLE' for x in parsed),
          'CREATE TABLE 3문장만 sqlglot Oracle 방언으로 정적 파싱; 인덱스 파싱·실제 DB 실행 아님')
    expected_indexes={
        (f'LGL_AR{idx:02d}_I{j}_A',t['name'],tuple(cols))
        for idx,t in enumerate(m.TABLES,1) for j,cols in enumerate(t['indexes'],1)}
    actual_indexes=set()
    index_sql=[s for s in statements if s.startswith('CREATE INDEX ')]
    for stmt in index_sql:
        match=re.fullmatch(r'CREATE INDEX DESIGN_AGENT\.([A-Z0-9_]+) ON DESIGN_AGENT\.([A-Z0-9_]+) \(([A-Z0-9_, ]+)\)',stmt)
        if match:
            actual_indexes.add((match[1],match[2],tuple(c.strip() for c in match[3].split(','))))
    check('index_definition_match',len(index_sql)==7 and actual_indexes==expected_indexes,
          'CREATE INDEX 7문장 이름·표·순서 있는 컬럼 목록을 설계 정의와 대조; Oracle 구문 실행 검증 아님')
    query_text=(OUT/'agent_query_review.sql').read_text()
    query_sql=re.sub(r'--[^\n]*','',query_text).replace('__AGENT_OWNER__','DESIGN_AGENT')
    queries=[q.strip() for q in query_sql.split(';') if q.strip()]
    query_ast=[sqlglot.parse_one(q,read='oracle') for q in queries]
    check('select_templates_parser',len(query_ast)==11 and all(isinstance(x,sqlglot.exp.Select) for x in query_ast),
          'SELECT 예시 11문장 Oracle 방언 정적 파싱; 실제 adapter·Oracle 실행·실행 계획 확인 아님')
    allowed={t['name'] for t in m.TABLES}
    check('select_template_boundaries',all(
          'SCOPE_HASH_VAL = :scope' in q and all(t.name in allowed and t.db=='DESIGN_AGENT' for t in a.find_all(sqlglot.exp.Table))
          for q,a in zip(queries,query_ast)),'모든 예시는 scope bind와 신규 Agent 표만 참조; 인증·권한 검증을 대신하지 않음')
    book=load_workbook(path,read_only=True)
    check('final_workbook',book['기존컬럼대응'].max_row==833 and all(book[t['key']].max_row-1==len(t['columns']) for t in m.TABLES),
          'R2 Excel 최종 컬럼·대응표 행수 확인');book.close()
    protected=[h for h in data['snapshot']['sources']
               if hashlib.sha256((m.ROOT/h['path']).read_bytes()).hexdigest()!=h['sha256']]
    check('source_files_preserved',not protected,'자료 작성 중 제품·선택·Gold 소스 해시 동일')
    v['counts']['query_templates']=11
    v['known_limitations']=[
        '최초 R2 SQL 파싱에서 owner-qualified CREATE INDEX 7문장이 generic Command로 fallback됨. 현재는 TABLE 파싱과 INDEX 정의 대조를 분리했으며 최초 결과를 Oracle 인덱스 구문 검증으로 해석하지 않음.',
        '정적 컬럼 대응은 실제 데이터 무손실 이관·동등한 SQL 소비 동작·성능을 증명하지 않음.',
    ]
    v['status']='R2_STATIC_DOCUMENT_CHECKS_PASSED';m.write_json('validation.json',v)
    print(json.dumps({'revision':'R2','new_tables':3,'new_columns':21,'existing_state_columns':5,'checks':len(checks)}))


if __name__=='__main__':main()
