"""Existing 14-column contract, explicit byte semantics and Korean metadata."""
import re

from semantic_runtime.initial_vector import ddl, table, VectorError

# name, type, nullable, logical name, meaning/generation/allowed values
COLUMNS = {
 'release': [
  ('PUB_ID','VARCHAR2(64 BYTE)',False,'벡터게시식별값','게시 manifest의 canonical JSON SHA-256. 소문자 16진수 64자리.'),
  ('QUERY_ID','VARCHAR2(64 BYTE)',False,'조회게시식별값','원천 COMPLETE 조회 릴리스의 SHA-256 식별값. 원문 판본과 결속.'),
  ('MANIFEST_JSON','CLOB',False,'벡터게시명세내용','원천·조회 릴리스·데이터세대·문서범위·설정·분할 버전을 담은 불변 JSON.'),
  ('STATUS','VARCHAR2(16 BYTE)',False,'벡터게시상태코드','BUILDING 또는 READY. 실패 세부 이력은 Dataiku에 보관하며 불완전 게시본은 BUILDING으로 유지.'),
  ('LEASE_ID','VARCHAR2(64 BYTE)',True,'적재잠금식별값','동시 적재 차단용 임시 난수. 현재 생성값은 48자리 16진수. 완료·정상 종료 시 NULL.')],
 'segment': [
  ('PUB_ID','VARCHAR2(64 BYTE)',False,'벡터게시식별값','게시정보 PUB_ID 외래키. SEG_ID와 복합 PK.'),
  ('SEG_ID','VARCHAR2(64 BYTE)',False,'벡터구역식별값','조회 릴리스와 원문 좌표·내용 해시 메타의 canonical JSON SHA-256.'),
  ('DOC_ID','VARCHAR2(512 BYTE)',False,'문서식별값','해당 판본의 원천 문서 식별값. 512바이트 이내. 문자열·선행 0 유지.'),
  ('SOURCE_ID','VARCHAR2(512 BYTE)',False,'원문위치식별값','조회 릴리스의 원문 구조 항목 식별값. 본문·부칙·별표 등 분리된 좌표 유지.'),
  ('META_JSON','CLOB',False,'벡터구역메타내용','문서·구조·블록 ID, start/end 문자좌표, 원문·블록·입력 해시 JSON. 원문 본문은 원천 테이블 참조.'),
  ('EMBEDDING','VECTOR(*,FLOAT32)',False,'임베딩벡터값','GENOS 내부 모델이 생성한 숫자 배열을 L2 정규화. 차원은 MANIFEST_JSON.profile로 검증. 모델 간 혼용 금지.')],
 'active': [
  ('QUERY_ID','VARCHAR2(64 BYTE)',False,'조회게시식별값','조회 릴리스마다 한 행. 원문 조회채널 자체를 변경하는 테이블은 아님.'),
  ('PUB_ID','VARCHAR2(64 BYTE)',False,'활성벡터게시식별값','동일 QUERY_ID의 READY 게시본만 선택. 게시정보 PUB_ID 외래키.'),
  ('REVISION','NUMBER',False,'활성버전순번','최초 1, 교체 때 1 증가. 현재 값 조건부 UPDATE로 동시 교체 충돌 차단.')]
}
TABLE_META = {
 'release': ('벡터게시정보','SNAPSHOT','게시본 1건 / PUB_ID',
             '어떤 원문과 임베딩 모델로 생성되었고 전량 적재가 완료되었는가?',
             '게시 명세·작업 잠금 포함; 건수 검증 결과는 Dataiku에 보관; 상세 실행 로그·질문 답변 제외.'),
 'segment': ('원문구역벡터','SNAPSHOT','게시본 내 원문 구역 1건 / PUB_ID, SEG_ID',
             '질문과 의미가 가까운 원문 조항의 좌표는 무엇인가?',
             '제목과 원문 블록을 800자·100자 겹침으로 분할한 파생 벡터. 원문·정답 본문은 제외.'),
 'active': ('활성벡터게시정보','MASTER','조회 릴리스 1건 / QUERY_ID',
            '해당 원문 조회 릴리스에 사용할 READY 벡터 게시본은 무엇인가?',
            '현재 벡터 선택 정보. 원문 조회채널 변경·과거 전환 이력은 제외; 이력은 Dataiku 보관.')
}

def description(key):
    logical, kind, grain, question, scope = TABLE_META[key]
    return (f'논리명(표준미확인 후보): {logical}\n요약: 법률 RAG 초기 원문 검색용 파생 벡터 {logical}. '
            f'행단위와PK: {grain}. 질문: {question} 포함·제외: {scope} '
            '원천: SIDDS의 완료된 문서·원문·조회 게시 릴리스. '
            '갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R3 실행; 전량 검증 후 READY/활성 선택. '
            '보유기간: 기존 게시본 보존; 공식 보유기간과 관리 부서는 확인 필요. '
            '산식: 개별 컬럼 설명 참조; 금액 집계 해당 없음. '
            '주의: 문서 권한·판본·모델/가중치/차원 일치 필수, 게시본 간 중복 집계 금지. '
            '개발: SIDDS.*_S. 운영 Gold 후보이며 표준단어·도메인·인포타입·JSON/VECTOR 승인 및 DBA 생성은 미완료.')

def statements(owner='SIDDS'):
    out = [re.sub(r'VARCHAR2\((\d+)\)',r'VARCHAR2(\1 BYTE)',s) for s in ddl(owner)]
    for key, cols in COLUMNS.items():
        out.append("COMMENT ON TABLE " + table(key,owner) + " IS '" + description(key).replace("'","''") + "'")
        for name, typ, nullable, logical, desc in cols:
            text = f'논리명(미승인 후보): {logical}. {desc} 타입: {typ}; NULL: {nullable}. 표준매핑 미확인.'
            out.append(f"COMMENT ON COLUMN {table(key,owner)}.{name} IS '" + text.replace("'","''") + "'")
    return out

def ensure(sql, owner='SIDDS'):
    for statement in statements(owner):
        if statement.startswith('CREATE '):
            body = "BEGIN EXECUTE IMMEDIATE '" + statement.replace("'","''") + "'; EXCEPTION WHEN OTHERS THEN IF SQLCODE<>-955 THEN RAISE; END IF; END;"
        else:
            body = "BEGIN EXECUTE IMMEDIATE '" + statement.replace("'","''") + "'; END;"
        sql.request(body,write=True)
    return validate(sql,owner)

def validate(sql, owner='SIDDS'):
    names = {key:table(key,owner).split('.')[1] for key in COLUMNS}
    rows = sql.query('SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,NULLABLE,COLUMN_ID '
                     'FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME IN (:r,:s,:a) ORDER BY TABLE_NAME,COLUMN_ID',
                     [('owner',owner,'VARCHAR2')]+[(k,names[key],'VARCHAR2') for k,key in [('r','release'),('s','segment'),('a','active')]],limit=100)
    for key, cols in COLUMNS.items():
        got = [row for row in rows if row['TABLE_NAME']==names[key]]
        if [row['COLUMN_NAME'] for row in got] != [c[0] for c in cols]:
            raise VectorError('VECTOR_DDL_COLUMNS: '+names[key]+'; run 01_CREATE_VECTOR_SILVER.sql and inspect 02_CHECK_VECTOR.sql')
        for row, (name,typ,nullable,*_) in zip(got,cols):
            if row['DATA_TYPE'] != typ.split('(')[0] or row['NULLABLE'] != ('Y' if nullable else 'N'):
                raise VectorError('VECTOR_DDL_TYPE_NULL: '+names[key]+'.'+name)
            if typ.startswith('VARCHAR2') and (row['CHAR_USED']!='B' or int(row['DATA_LENGTH'])!=int(re.search(r'\((\d+)',typ).group(1))):
                raise VectorError('VECTOR_DDL_LENGTH: '+names[key]+'.'+name)
    constraints = sql.query('SELECT c.TABLE_NAME,c.CONSTRAINT_NAME,c.CONSTRAINT_TYPE,c.STATUS,c.VALIDATED,c.R_OWNER,c.R_CONSTRAINT_NAME,c.SEARCH_CONDITION_VC, '
                           'x.COLUMN_NAME,x.POSITION FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS x '
                           'ON c.OWNER=x.OWNER AND c.CONSTRAINT_NAME=x.CONSTRAINT_NAME '
                           'WHERE c.OWNER=:owner AND c.TABLE_NAME IN (:r,:s,:a)',
                           [('owner',owner,'VARCHAR2')]+[(k,names[key],'VARCHAR2') for k,key in [('r','release'),('s','segment'),('a','active')]],limit=100)
    groups = {}
    for row in constraints:
        groups.setdefault(row['CONSTRAINT_NAME'],[]).append(row)
    def find(key,kind,columns):
        return [rs for rs in groups.values() if rs[0]['TABLE_NAME']==names[key] and rs[0]['CONSTRAINT_TYPE']==kind
                and all(r['STATUS']=='ENABLED' and r['VALIDATED']=='VALIDATED' for r in rs)
                and [r['COLUMN_NAME'] for r in sorted(rs,key=lambda r:r['POSITION'] or 0)]==columns]
    for key,cols in [('release',['PUB_ID']),('segment',['PUB_ID','SEG_ID']),('active',['QUERY_ID'])]:
        if not find(key,'P',cols):
            raise VectorError('VECTOR_DDL_PK: '+names[key])
    release_pk = {rs[0]['CONSTRAINT_NAME'] for rs in find('release','P',['PUB_ID'])}
    for key in ('segment','active'):
        if not any(rs[0]['R_OWNER']==owner and rs[0]['R_CONSTRAINT_NAME'] in release_pk for rs in find(key,'R',['PUB_ID'])):
            raise VectorError('VECTOR_DDL_FK: '+names[key])
    for name,column in [('LV_MANIFEST_JSON','MANIFEST_JSON'),('LV_META_JSON','META_JSON')]:
        if name not in groups or groups[name][0]['STATUS']!='ENABLED' or groups[name][0]['VALIDATED']!='VALIDATED':
            raise VectorError('VECTOR_DDL_JSON: '+name)
        condition=re.sub(r'[\s"()]','',groups[name][0].get('SEARCH_CONDITION_VC') or '').upper()
        if condition!=column+'ISJSON':
            raise VectorError('VECTOR_DDL_JSON_EXPRESSION: '+name)
    indexes = sql.query('SELECT COLUMN_NAME,COLUMN_POSITION FROM ALL_IND_COLUMNS WHERE INDEX_OWNER=:owner AND TABLE_OWNER=:owner AND TABLE_NAME=:tab AND INDEX_NAME=:name ORDER BY COLUMN_POSITION',
                        [('owner',owner,'VARCHAR2'),('tab',names['segment'],'VARCHAR2'),('name','LGL_VCTR_ROOT_IX_S','VARCHAR2')],limit=10)
    if [r['COLUMN_NAME'] for r in indexes] != ['PUB_ID','DOC_ID','SOURCE_ID']:
        raise VectorError('VECTOR_DDL_INDEX')
    probe = sql.query("SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)) AS DIM, "
                      "VECTOR_DISTANCE(TO_VECTOR('[1,0]',2,FLOAT32),TO_VECTOR('[1,0]',2,FLOAT32),COSINE) AS DISTANCE FROM DUAL",limit=1)
    if int(probe[0]['DIM'])!=2 or abs(float(probe[0]['DISTANCE']))>0.000001:
        raise VectorError('VECTOR_NATIVE_SUPPORT')
    return {'tables':3,'columns':14,'native_vector':True}
