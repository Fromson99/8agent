"""Two physical tables, six visible columns. Required metadata stays explicit in JSON."""
import re
from semantic_runtime.initial_vector import ddl,table,VectorError,DOC,SOURCE,ACTIVE_KEY

COLUMNS={
 'release':[
  ('PUB_ID','VARCHAR2(64 BYTE)',False,'벡터게시식별값','불변 manifest의 SHA-256. PK. 작업 상태와 활성 순번은 hash 계산에서 제외.'),
  ('PAYLOAD_JSON','CLOB',False,'벡터게시메타내용','manifest에 원문/조회 판본·문서 범위·모델·차원·분할 기준, status에 BUILDING/READY, lease에 현재 적재 잠금, active_revision에 활성 순번. 상세 실행 기록은 Dataiku에 저장.')],
 'segment':[
  ('PUB_ID','VARCHAR2(64 BYTE)',False,'벡터게시식별값','같은 모델·원문 판본으로 만든 게시본. 게시 정보 FK, SEG_ID와 복합 PK.'),
  ('SEG_ID','VARCHAR2(64 BYTE)',False,'벡터구역식별값','조회 릴리스와 원문 좌표·내용 해시로 만든 SHA-256.'),
  ('META_JSON','CLOB',False,'벡터구역메타내용','document_id·source_id·unit_id·block_id·start/end·원문/블록/입력 해시. 원문 본문은 기존 테이블 참조. 문서/원문 ID 속성에 함수 색인 적용.'),
  ('EMBEDDING','VECTOR(*,FLOAT32)',False,'임베딩벡터값','GENOS 내부 임베딩 모델의 L2 정규화 숫자 배열. 게시 정보의 모델·버전·차원과 일치해야 함.')]
}
TABLE_META={
 'release':('벡터게시정보','MASTER/SNAPSHOT','게시본 1건 / PUB_ID','어느 원문·모델의 벡터이며 완료·활성 상태인가?','manifest 불변, 적재 잠금·활성 순번만 변경. 상세 로그 제외.'),
 'segment':('원문구역벡터','SNAPSHOT','게시본 내 구간 1건 / PUB_ID, SEG_ID','질문과 가까운 원문의 위치는 어디인가?','800자/100자 겹침 파생 벡터와 원문 좌표. 원문·질문·정답 본문 제외.')
}
def description(key):
 logical,kind,grain,question,scope=TABLE_META[key]
 return (f'논리명(미승인 후보): {logical}. 유형: {kind}. 행단위/PK: {grain}. 질문: {question} 포함/제외: {scope} '
         '원천: SIDDS 완료 원문·조회 게시본. 갱신: 원문 이관 완료 후 Dataiku LEGAL_04_VECTOR_SILVER_R4 실행, 전량 검증 뒤 활성화. '
         '보유기간·관리부서: 확인 필요, 기존 게시본 자동 삭제 없음. 산식: 컬럼 설명 참조. '
         '주의: 권한·원문 판본·모델 바인딩 유지. 개발 SIDDS.*_S, 운영 Gold 표준용어·도메인·인포타입·JSON/VECTOR 승인·DBA 생성 미완료.')

def statements(owner='SIDDS'):
 out=ddl(owner)
 for key,cols in COLUMNS.items():
  out.append(f"COMMENT ON TABLE {table(key,owner)} IS '"+description(key).replace("'","''")+"'")
  for name,typ,nullable,logical,desc in cols:
   text=f'논리명(미승인 후보): {logical}. {desc} 타입: {typ}; NULL: {nullable}. 표준매핑 미확인.'
   out.append(f"COMMENT ON COLUMN {table(key,owner)}.{name} IS '"+text.replace("'","''")+"'")
 return out

def ensure(sql,owner='SIDDS'):
 for statement in statements(owner):
  body="BEGIN EXECUTE IMMEDIATE '"+statement.replace("'","''")+"';"
  if statement.startswith('CREATE '):body+=' EXCEPTION WHEN OTHERS THEN IF SQLCODE<>-955 THEN RAISE; END IF;'
  sql.request(body+' END;',write=True)
 return validate(sql,owner)

def validate(sql,owner='SIDDS'):
 names={k:table(k,owner).split('.')[1] for k in COLUMNS}
 binds=[('owner',owner,'VARCHAR2'),('r',names['release'],'VARCHAR2'),('s',names['segment'],'VARCHAR2')]
 rows=sql.query('SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,NULLABLE,COLUMN_ID FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME IN (:r,:s) ORDER BY TABLE_NAME,COLUMN_ID',binds,limit=50)
 for key,cols in COLUMNS.items():
  got=[r for r in rows if r['TABLE_NAME']==names[key]]
  if [r['COLUMN_NAME'] for r in got]!=[c[0] for c in cols]:raise VectorError('VECTOR_DDL_COLUMNS: '+names[key])
  for row,(name,typ,nullable,*_) in zip(got,cols):
   if row['DATA_TYPE']!=typ.split('(')[0] or row['NULLABLE']!=('Y' if nullable else 'N'):raise VectorError('VECTOR_DDL_TYPE_NULL: '+name)
   if typ.startswith('VARCHAR2') and (row['CHAR_USED']!='B' or int(row['DATA_LENGTH'])!=64):raise VectorError('VECTOR_DDL_LENGTH: '+name)
 rows=sql.query('SELECT c.TABLE_NAME,c.CONSTRAINT_NAME,c.CONSTRAINT_TYPE,c.STATUS,c.VALIDATED,c.R_OWNER,c.R_CONSTRAINT_NAME,c.SEARCH_CONDITION_VC,x.COLUMN_NAME,x.POSITION FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS x ON c.OWNER=x.OWNER AND c.CONSTRAINT_NAME=x.CONSTRAINT_NAME WHERE c.OWNER=:owner AND c.TABLE_NAME IN (:r,:s)',binds,limit=80)
 groups={}
 for row in rows:groups.setdefault(row['CONSTRAINT_NAME'],[]).append(row)
 def find(key,kind,columns):
  return [rs for rs in groups.values() if rs[0]['TABLE_NAME']==names[key] and rs[0]['CONSTRAINT_TYPE']==kind
          and all(r['STATUS']=='ENABLED' and r['VALIDATED']=='VALIDATED' for r in rs)
          and [r['COLUMN_NAME'] for r in sorted(rs,key=lambda r:r['POSITION'] or 0)]==columns]
 for key,cols in [('release',['PUB_ID']),('segment',['PUB_ID','SEG_ID'])]:
  if not find(key,'P',cols):raise VectorError('VECTOR_DDL_PK: '+names[key])
 release_pk={rs[0]['CONSTRAINT_NAME'] for rs in find('release','P',['PUB_ID'])}
 if not any(rs[0]['R_OWNER']==owner and rs[0]['R_CONSTRAINT_NAME'] in release_pk for rs in find('segment','R',['PUB_ID'])):raise VectorError('VECTOR_DDL_FK')
 for name,column in [('LVM_SET_JSON','PAYLOAD_JSON'),('LVM_ITEM_JSON','META_JSON')]:
  rs=groups.get(name,[])
  condition=re.sub(r'[\s"()]','',rs[0].get('SEARCH_CONDITION_VC') or '').upper() if rs else ''
  if not rs or rs[0]['STATUS']!='ENABLED' or rs[0]['VALIDATED']!='VALIDATED' or condition!=column+'ISJSONWITHUNIQUEKEYS':raise VectorError('VECTOR_DDL_JSON: '+name)
 indexes=sql.query('SELECT INDEX_NAME,TABLE_NAME,UNIQUENESS,STATUS,FUNCIDX_STATUS FROM ALL_INDEXES WHERE OWNER=:owner AND INDEX_NAME IN (:i,:a)',[('owner',owner,'VARCHAR2'),('i','LGL_VCTR_ITEM_IX_S','VARCHAR2'),('a','LGL_VCTR_SET_ACT_IX_S','VARCHAR2')],limit=2)
 if len(indexes)!=2 or any(r['STATUS']!='VALID' or r['FUNCIDX_STATUS']!='ENABLED' for r in indexes):raise VectorError('VECTOR_DDL_INDEX')
 for row in indexes:
  active=row['INDEX_NAME']=='LGL_VCTR_SET_ACT_IX_S'
  if row['TABLE_NAME']!=names['release' if active else 'segment'] or row['UNIQUENESS']!=('UNIQUE' if active else 'NONUNIQUE'):raise VectorError('VECTOR_DDL_INDEX_BINDING')
 # Verify expression definitions, not only index names. Oracle normalizes
 # identifiers/case and may add FORMAT JSON / explicit BYTE during storage.
 def normalized(value):
  parts=re.split(r"('(?:''|[^'])*')",str(value))
  for i in range(0,len(parts),2):
   parts[i]=re.sub(r'\s+','',parts[i]).replace('"','').upper().replace('FORMATJSON','').replace('BYTE','').replace('TYPE(LAX)','')
  return ''.join(parts)
 for name,expected in [('LGL_VCTR_ITEM_IX_S',[DOC,SOURCE]),('LGL_VCTR_SET_ACT_IX_S',[ACTIVE_KEY])]:
  expressions=sql.query('SELECT COLUMN_POSITION,COLUMN_EXPRESSION FROM ALL_IND_EXPRESSIONS WHERE INDEX_OWNER=:owner AND INDEX_NAME=:name ORDER BY COLUMN_POSITION',
                        [('owner',owner,'VARCHAR2'),('name',name,'VARCHAR2')],limit=3)
  if ([row['COLUMN_POSITION'] for row in expressions]!=([2,3] if len(expected)==2 else [1])
      or [normalized(row['COLUMN_EXPRESSION']) for row in expressions]!=[normalized(e) for e in expected]):
   raise VectorError('VECTOR_DDL_INDEX_EXPRESSION: '+name)
 # Native VECTOR capability check, not a production latency benchmark.
 probe=sql.query("SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)) AS DIM,VECTOR_DISTANCE(TO_VECTOR('[1,0]',2,FLOAT32),TO_VECTOR('[1,0]',2,FLOAT32),COSINE) AS DISTANCE FROM DUAL",limit=1)
 if int(probe[0]['DIM'])!=2 or abs(float(probe[0]['DISTANCE']))>0.000001:raise VectorError('VECTOR_NATIVE_SUPPORT')
 return {'tables':2,'columns':6,'native_vector':True}
