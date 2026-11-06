from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
PKG=OUT/'package'
SOURCE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main152_oneclick_mail_20261105_r1/MAIN152_FULL_20261105_R1.zip'
KEYS=['AGT_BODY','AGT_REC','AGT_RUN','EXEC_ST']
sha=lambda b:hashlib.sha256(b).hexdigest()
with ZipFile(SOURCE) as z:
    rel='00_SYSTEM/ORACLE/development_g19_1.json'
    raw=z.read(next(n for n in z.namelist() if n.endswith(rel)))
    mapping=json.loads(raw)
    tables={k:mapping['tables'][k] for k in KEYS}
    sources={rel:sha(raw)}
    for rel in ['02_BACKEND/semantic_runtime/oracle_gold_mapping.py','02_BACKEND/semantic_runtime/oracle_agent_records.py']:
        sources[rel]=sha(z.read(next(n for n in z.namelist() if n.endswith(rel))))
assert all(t['owner']=='SIDDA' and t['name'].endswith('_A_1') for t in tables.values())
files={}
def add(name,sql):
    assert not sql.rstrip().endswith(';')
    files[name]=sql.rstrip()+'\n'
NAMES=','.join("'"+t['name']+"'" for t in tables.values())
add('00_CHECK_EXISTING.sql',f"SELECT USER AS CONNECTION_USER, SYS_CONTEXT('USERENV','DB_NAME') AS DB_NAME,\n       X.EXPECTED_TABLE, O.OWNER, O.OBJECT_TYPE, O.STATUS\nFROM ("+'\n      UNION ALL '.join("SELECT '"+t['name']+"' AS EXPECTED_TABLE FROM DUAL" for t in tables.values())+f") X\nLEFT JOIN ALL_OBJECTS O ON O.OWNER='SIDDA' AND O.OBJECT_NAME=X.EXPECTED_TABLE\nORDER BY X.EXPECTED_TABLE,O.OBJECT_TYPE")
pks={'AGT_BODY':'LGL_AR03_PK_A_1','AGT_REC':'LGL_AR02_PK_A_1','AGT_RUN':'LGL_AR01_PK_A_1','EXEC_ST':'LGL_EXEC_ST_PK_A_1'}
for i,(k,t) in enumerate(tables.items(),1):
    definitions=[c['name']+' '+c['type']+(' NOT NULL' if c['required'] else '') for c in t['columns'].values()]
    definitions.append('CONSTRAINT '+pks[k]+' PRIMARY KEY ('+', '.join(t['primary_key'])+')')
    if k=='EXEC_ST':
        definitions+=['CONSTRAINT LGL_EXEC_ST_RCK_A_1 CHECK (CHG_SEQ_NO >= 1)','CONSTRAINT LGL_EXEC_ST_JCK_A_1 CHECK (ST_JSON_CN IS JSON)']
    add('%02d_CREATE_%s.sql'%(i,t['name']), 'CREATE TABLE '+t['owner']+'.'+t['name']+' (\n  '+',\n  '.join(definitions)+'\n)')
indices=[]
old=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r3'
for i,p in enumerate(sorted(old.glob('*.sql')),0):
    text=p.read_text().strip()
    if not text.startswith('CREATE INDEX '):continue
    text=re.sub(r'\b(LGL_[A-Z0-9_]+_A)\b',r'\1_1',text)
    m=re.fullmatch(r'CREATE INDEX SIDDA\.([A-Z0-9_]+) ON SIDDA\.([A-Z0-9_]+) \(([^)]+)\)',text)
    assert m
    index={'name':m[1],'table':m[2],'columns':[x.strip() for x in m[3].split(',')]}
    indices.append(index)
    add('%02d_CREATE_%s.sql'%(4+len(indices),m[1]),text)
assert len(indices)==7
# Exact column/type/nullability comparison (the runtime contract) and enabled, validated PK.
expected=[]
for k,t in tables.items():
    for c in t['columns'].values():
        typ=c['type']; length='NULL';precision='NULL';scale='NULL';char='NULL'
        if typ.startswith('VARCHAR2'):
            length=re.search(r'\((\d+)',typ)[1];typ='VARCHAR2';char="'B'"
        elif typ.startswith('NUMBER'):
            precision='18';scale='0';typ='NUMBER'
        elif typ.startswith('TIMESTAMP'):
            scale='6';typ='TIMESTAMP(6) WITH TIME ZONE'
        expected.append("SELECT '%s' T, '%s' C, '%s' DT, %s DL, %s DP, %s DS, %s CU, '%s' NU FROM DUAL"%(t['name'],c['name'],typ,length,precision,scale,char,'N' if c['required'] else 'Y'))
pk_rows=["SELECT '%s' T, '%s' PK_COLS FROM DUAL"%(t['name'],','.join(t['primary_key'])) for t in tables.values()]
add('12_VERIFY_TABLES.sql',"WITH E AS (\n  "+'\n  UNION ALL '.join(expected)+"\n), P AS (\n  "+'\n  UNION ALL '.join(pk_rows)+f"\n), A AS (\n  SELECT TABLE_NAME T,COLUMN_NAME C,DATA_TYPE DT,DATA_LENGTH DL,DATA_PRECISION DP,DATA_SCALE DS,CHAR_USED CU,NULLABLE NU\n  FROM ALL_TAB_COLUMNS WHERE OWNER='SIDDA' AND TABLE_NAME IN ({NAMES})\n), ERRORS AS (\n  SELECT COALESCE(E.T,A.T) T, COALESCE(E.C,A.C) C\n  FROM E FULL OUTER JOIN A ON E.T=A.T AND E.C=A.C\n  WHERE E.C IS NULL OR A.C IS NULL OR E.DT<>A.DT OR E.NU<>A.NU\n     OR (E.DL IS NOT NULL AND NVL(A.DL,-1)<>E.DL)\n     OR (E.DP IS NOT NULL AND NVL(A.DP,-1)<>E.DP)\n     OR (E.DS IS NOT NULL AND NVL(A.DS,-1)<>E.DS)\n     OR (E.CU IS NOT NULL AND NVL(A.CU,'?')<>E.CU)\n), ACTUAL_PK AS (\n  SELECT C.TABLE_NAME T, LISTAGG(K.COLUMN_NAME,',') WITHIN GROUP (ORDER BY K.POSITION) PK_COLS\n  FROM ALL_CONSTRAINTS C JOIN ALL_CONS_COLUMNS K\n    ON C.OWNER=K.OWNER AND C.CONSTRAINT_NAME=K.CONSTRAINT_NAME AND C.TABLE_NAME=K.TABLE_NAME\n  WHERE C.OWNER='SIDDA' AND C.TABLE_NAME IN ({NAMES})\n    AND C.CONSTRAINT_TYPE='P' AND C.STATUS='ENABLED' AND C.VALIDATED='VALIDATED'\n  GROUP BY C.TABLE_NAME\n)\nSELECT P.T TABLE_NAME,\n       CASE WHEN (SELECT COUNT(*) FROM ERRORS X WHERE X.T=P.T)=0 THEN 'PASS' ELSE 'FAIL' END COLUMNS_RESULT,\n       CASE WHEN P.PK_COLS=K.PK_COLS THEN 'PASS' ELSE 'FAIL' END PK_RESULT,\n       (SELECT COUNT(*) FROM A WHERE A.T=P.T) ACTUAL_COLUMNS,\n       (SELECT LISTAGG(X.C,',') WITHIN GROUP (ORDER BY X.C) FROM ERRORS X WHERE X.T=P.T) MISMATCH_COLUMNS\nFROM P LEFT JOIN ACTUAL_PK K ON P.T=K.T\nORDER BY P.T")
# Time-zone index expressions are reported separately as Oracle LONG metadata.
ix_expected=[]
for idx in indices:
    for pos,col in enumerate(idx['columns'],1):
        ix_expected.append("SELECT '%s' I, '%s' T, %d POS, '%s' C FROM DUAL"%(idx['name'],idx['table'],pos,col))
add('13_VERIFY_INDEXES.sql',"WITH E AS (\n  "+'\n  UNION ALL '.join(ix_expected)+"\n)\nSELECT E.I EXPECTED_INDEX,E.T EXPECTED_TABLE,E.POS COLUMN_POSITION,E.C EXPECTED_COLUMN,\n       I.STATUS,I.UNIQUENESS,C.COLUMN_NAME ACTUAL_COLUMN,X.COLUMN_EXPRESSION\nFROM E LEFT JOIN ALL_INDEXES I ON I.OWNER='SIDDA' AND I.INDEX_NAME=E.I\nLEFT JOIN ALL_IND_COLUMNS C ON C.INDEX_OWNER=I.OWNER AND C.INDEX_NAME=I.INDEX_NAME\n  AND C.TABLE_OWNER='SIDDA' AND C.TABLE_NAME=E.T AND C.COLUMN_POSITION=E.POS\nLEFT JOIN ALL_IND_EXPRESSIONS X ON X.INDEX_OWNER=I.OWNER AND X.INDEX_NAME=I.INDEX_NAME\n  AND X.COLUMN_POSITION=E.POS\nORDER BY E.I,E.POS")
PKG.mkdir(exist_ok=True)
for n,v in files.items(): (PKG/n).write_text(v,encoding='utf-8')
assert len(files)==14
combined='-- Gold 매핑의 Agent 기록 4표만 생성합니다. Gold 데이터 테이블은 변경하지 않습니다.\n-- Dataiku SQL 노트북: 각 파일/번호의 SQL 한 문장씩 별도 Query에서 실행합니다.\n-- 이 TXT 전체를 한 Query에 붙이지 않습니다. 문장 끝 세미콜론은 없습니다.\n-- 00 조회 → 없는 표의 01~04 → 없는 인덱스의 05~11 → 12/13 검증 순서입니다.\n-- 기존 객체가 있으면 생성하지 말고 12/13으로 먼저 비교합니다. DROP/ALTER/TRUNCATE/GRANT는 포함하지 않습니다.\n\n'
combined+='\n\n'.join('-- '+n+'\n'+v for n,v in files.items())
(OUT/'AGENT_GOLD_SQL_RUN_R1.txt').write_text(combined,encoding='utf-8')
zip_path=OUT/'AGENT_GOLD_SQL_20261105_R1.zip'
with ZipFile(zip_path,'w',ZIP_DEFLATED) as z:
    for n,v in files.items():z.writestr(n,v.encode())
manifest={'version':'agent-gold-layer-sql-20261105-r1','profile':'gold','source_zip':str(SOURCE.relative_to(ROOT)),'source_zip_sha256':sha(SOURCE.read_bytes()),'source_files':sources,'tables':tables,'indexes':indices,'sql_files':{n:sha(v.encode()) for n,v in files.items()},'zip_sha256':sha(zip_path.read_bytes()),'ddl_tables':4,'ddl_indexes':7,'gold_table_changes':0,'product_code_changes':0}
(OUT/'BUILD.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'sql_files':len(files),'tables':4,'indexes':7,'zip_bytes':zip_path.stat().st_size,'txt_bytes':(OUT/'AGENT_GOLD_SQL_RUN_R1.txt').stat().st_size}))
