"""Plain one-statement SQL files for the existing Dataiku Oracle SQL notebook."""
from pathlib import Path
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r1'
SOURCE=ROOT/'07_DOCS/REFERENCE/REPORTS/ORACLE_AGENT_RECORD_DESIGN_20261030_R2/agent_schema_review.sql'
OUT.mkdir(parents=True,exist_ok=True)
def write(name,text):
 p=OUT/name;p.parent.mkdir(exist_ok=True)
 if p.exists():raise RuntimeError('Do not overwrite delivered SQL: '+name)
 p.write_text(text.rstrip()+'\n')
text=re.sub(r'--[^\n]*','',SOURCE.read_text()).replace('__AGENT_OWNER__','SIDDA')
statements=[s.strip() for s in text.split(';') if s.strip()]
tables=[s for s in statements if s.startswith('CREATE TABLE')]
indexes=[s for s in statements if s.startswith('CREATE INDEX')]
assert len(tables)==3 and len(indexes)==7
names=[]
for i,sql in enumerate([*tables,*indexes],1):
 obj=sql.split()[2].split('.')[1];name=f'{i:02d}_CREATE_{obj}.sql';write(name,sql);names.append(name)
target="('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A')"
write('00_CHECK_CONNECTION.sql',"SELECT USER AS CONNECTION_USER,SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS CURRENT_SCHEMA,SYS_CONTEXT('USERENV','DB_NAME') AS DB_NAME FROM DUAL")
write('00_CHECK_EXISTING.sql',f"SELECT OWNER,OBJECT_NAME,OBJECT_TYPE,STATUS FROM ALL_OBJECTS WHERE OWNER='SIDDA' AND (OBJECT_NAME IN {target} OR OBJECT_NAME LIKE 'LGL_AR01_%' OR OBJECT_NAME LIKE 'LGL_AR02_%' OR OBJECT_NAME LIKE 'LGL_AR03_%') ORDER BY OBJECT_TYPE,OBJECT_NAME")
write('11_CHECK_COLUMNS.sql',f"SELECT TABLE_NAME,COLUMN_ID,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,DATA_PRECISION,DATA_SCALE,CHAR_USED,NULLABLE FROM ALL_TAB_COLUMNS WHERE OWNER='SIDDA' AND TABLE_NAME IN {target} ORDER BY TABLE_NAME,COLUMN_ID")
write('12_CHECK_INDEXES.sql',f"SELECT TABLE_NAME,INDEX_NAME,INDEX_TYPE,UNIQUENESS,STATUS FROM ALL_INDEXES WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME IN {target} ORDER BY TABLE_NAME,INDEX_NAME")
write('13_CHECK_PRIMARY_KEYS.sql',f"SELECT C.TABLE_NAME,C.CONSTRAINT_NAME,C.STATUS,C.VALIDATED,K.COLUMN_NAME,K.POSITION FROM ALL_CONSTRAINTS C JOIN ALL_CONS_COLUMNS K ON C.OWNER=K.OWNER AND C.CONSTRAINT_NAME=K.CONSTRAINT_NAME WHERE C.OWNER='SIDDA' AND C.TABLE_NAME IN {target} AND C.CONSTRAINT_TYPE='P' ORDER BY C.TABLE_NAME,K.POSITION")
write('14_CHECK_INDEX_COLUMNS.sql',f"SELECT TABLE_NAME,INDEX_NAME,COLUMN_POSITION,COLUMN_NAME FROM ALL_IND_COLUMNS WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME IN {target} ORDER BY TABLE_NAME,INDEX_NAME,COLUMN_POSITION")
write('15_CHECK_UTC_EXPRESSIONS.sql',f"SELECT TABLE_NAME,INDEX_NAME,COLUMN_POSITION,COLUMN_EXPRESSION FROM ALL_IND_EXPRESSIONS WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME IN {target} ORDER BY TABLE_NAME,INDEX_NAME,COLUMN_POSITION")
write('optional/90_CREATE_STATE_ONLY_IF_MISSING.sql',"""CREATE TABLE SIDDA.LGL_EXEC_ST_A (
  SCOPE_HASH_VAL VARCHAR2(64 BYTE) NOT NULL,
  ST_KEY_ID VARCHAR2(128 BYTE) NOT NULL,
  CHG_SEQ_NO NUMBER(18) NOT NULL,
  ST_HASH_VAL VARCHAR2(64 BYTE) NOT NULL,
  ST_JSON_CN CLOB NOT NULL,
  CONSTRAINT LGL_EXEC_ST_PK_A PRIMARY KEY (SCOPE_HASH_VAL,ST_KEY_ID),
  CONSTRAINT LGL_EXEC_ST_RCK_A CHECK (CHG_SEQ_NO>=1),
  CONSTRAINT LGL_EXEC_ST_JCK_A CHECK (ST_JSON_CN IS JSON)
)""")
write('DATAIKU_실행안내.txt',"""Dataiku SQL 노트북 — 신규 Agent 기록 3표21컬럼

1. 기존 Oracle 연결로 SQL notebook을 엽니다. Dataiku Flow의 데이터셋 생성이 아니라
   Oracle SIDDA의 영구 테이블을 생성하는 SQL입니다.
2. 00_CHECK_CONNECTION.sql, 00_CHECK_EXISTING.sql을 각각 별도 Query에서 실행합니다.
   이미 있는 표·기록은 지우지 않습니다. 조회 결과가 비어도 해당 계정의 권한을 확인합니다.
3. 01~03의 CREATE TABLE 세 파일을 각각 한 Query에서 실행합니다.
4. 04~10의 CREATE INDEX 일곱 파일도 각각 별도 Query에서 실행합니다.
   각 파일에는 한 문장만 있고 BEGIN/END, /, SQL*Plus 명령, 끝 세미콜론은 없습니다.
   이 안내문 전체나 파일 여러 개를 한 Query에 붙이지 않습니다.
5. 11~15 확인 SQL도 한 파일씩 실행합니다.
   RUN9 + REC8 + BODY4 = 신규21개 사용자 컬럼, 기존 STATE5 포함26개입니다.
   PK3와 조회 인덱스7을 확인합니다. 시간대 인덱스2개는 Oracle 내부 UTC 표현식과
   SYS_NC 숨김컬럼으로 표시될 수 있습니다. CLOB 내부 인덱스도 자동 생성됩니다.

기존 상태 표
  SIDDA.LGL_EXEC_ST_A는 기존 표를 재사용합니다. 기본 실행 순서에는 CREATE가 없습니다.
  실제 부재를 계정/권한과 함께 확인한 경우에만 optional/90_CREATE_STATE_ONLY_IF_MISSING.sql을
  한 번 실행합니다. 이미 있는 표를 DROP/ALTER해 맞추지 않습니다.

중간 오류
  ORA-00955: 같은 이름의 객체가 존재합니다. 삭제하거나 무조건 성공 처리하지 말고
  확인 SQL로 표/컬럼/PK/인덱스를 대조한 후 미생성 문장만 이어서 실행합니다.
  ORA-01031: 연결 계정에 SIDDA 생성 권한이 부족합니다. 기존 SIDDA owner/담당 계정으로 생성합니다.
  ORA-00942: 선행 표 또는 조회권한을 확인합니다. owner를 임의로 바꾸어 우회하지 않습니다.
  Oracle DDL은 문장별 자동 커밋입니다. 후속 실패가 앞선 CREATE를 되돌리지 않습니다.

이번 SQL에는 Gold 수정, DROP/TRUNCATE, quota 변경, 임의 계정 GRANT가 없습니다.
실제 코드서빙 ORDS 계정에는 기존 STATE 및 새 Agent 표의 필요한 조회/쓰기 권한이 필요합니다.
ORDS alias와 데이터 owner SIDDA는 별개이며 기존 인증값을 그대로 사용합니다.

설정 계약
  DP 미설정 또는 DP=nfs: 기존 NFS 경로.
  DP=oracle: 지식·기록 전체 Oracle 경로를 사용하는 메인 코드와 함께 반입해야 합니다.
  DP_QUERY_CHANNEL=main 또는 DP_QUERY_RELEASE_ID 중 한 가지로 게시된 조회 버전을 선택합니다.
  기존 GENOS_RUNTIME_DIR/STATE_DIR/SHARED_LOG_DIR 값은 Oracle 모드에서 논리 식별자가 됩니다.
  실제 코드 검증·메인 선택 결과는 이 패키지의 최종 CODE_STATUS.json을 확인합니다.
  표를 만들었다는 사실만으로 기존 NFS 이력 이관이나 현장 코드 반입이 완료되지는 않습니다.

Dataiku 공식 설명: https://doc.dataiku.com/dss/latest/notebooks/sql-notebook.html
SQL notebook은 DDL을 지원하며 Query별 셀을 분리해 관리할 수 있습니다.
""")
hashes={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file()}
(OUT/'SHA256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(OUT.with_suffix('.zip'),'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(OUT.rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(OUT)))
print('Dataiku plain SQL package:',OUT.relative_to(ROOT),'new tables',len(tables),'indexes',len(indexes))
