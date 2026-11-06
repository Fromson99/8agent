"""Build one Oracle anonymous block for Dataiku; never execute field SQL."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = ROOT / '08_DEPLOYMENT/DATAIKU/agent_gold_layer_20261105_r1'
KEYS = ['AGT_BODY', 'AGT_REC', 'AGT_RUN', 'EXEC_ST']
mapping = json.loads((ROOT / '00_SYSTEM/ORACLE/development_g19_1.json').read_text())
tables = {k: mapping['tables'][k] for k in KEYS}
prior = json.loads((OLD / 'BUILD.json').read_text())
for k, table in tables.items():
    assert table == {**prior['tables'][k], 'name': prior['tables'][k]['name'].removesuffix('_1')}
indexes = [{**i, 'name': i['name'].removesuffix('_1'), 'table': i['table'].removesuffix('_1')}
           for i in prior['indexes']]
verify = (OLD / 'package/12_VERIFY_TABLES.sql').read_text().replace('_A_1', '_A').strip()
assert verify.startswith('WITH E AS') and not verify.endswith(';')
prefix = '''-- Dataiku Oracle SQL notebook: paste this entire file into ONE Query and Run.
-- One anonymous PL/SQL block. Keep END; and do not append a SQL*Plus slash (/).
-- Creates only missing SIDDA Agent tables/indexes. Existing objects are checked.
-- No DROP, ALTER, GRANT, row deletion, or automatic A_1 history migration.
-- Oracle DDL commits each successful CREATE; after an error, correct its cause and rerun.
DECLARE
  c_owner CONSTANT VARCHAR2(30) := 'SIDDA';
  FUNCTION has_table(p_name VARCHAR2) RETURN BOOLEAN IS
    n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM ALL_TABLES WHERE OWNER=c_owner AND TABLE_NAME=p_name;
    RETURN n=1;
  END;
  PROCEDURE verify_tables(p_existing_only BOOLEAN) IS
  BEGIN
    FOR r IN (
'''
after_verify = '''
    ) LOOP
      IF NOT p_existing_only OR has_table(r.TABLE_NAME) THEN
        IF r.COLUMNS_RESULT <> 'PASS' OR r.PK_RESULT <> 'PASS' THEN
          RAISE_APPLICATION_ERROR(-20051, 'AGENT_A_SCHEMA ' || c_owner || '.' || r.TABLE_NAME ||
            ' columns=' || r.COLUMNS_RESULT || ' pk=' || r.PK_RESULT ||
            ' mismatch=' || SUBSTR(NVL(r.MISMATCH_COLUMNS,'-'),1,1000));
        END IF;
      END IF;
    END LOOP;
  END;
  PROCEDURE verify_index(p_name VARCHAR2, p_table VARCHAR2, p_cols VARCHAR2,
                         p_existing_only BOOLEAN) IS
    n NUMBER; expected_count NUMBER; actual_count NUMBER;
    actual_owner VARCHAR2(128); actual_table VARCHAR2(128);
    actual_status VARCHAR2(30); actual_unique VARCHAR2(30);
    wanted VARCHAR2(128); actual_col VARCHAR2(128); direction VARCHAR2(4);
    expression_text VARCHAR2(32767);
  BEGIN
    SELECT COUNT(*) INTO n FROM ALL_INDEXES WHERE OWNER=c_owner AND INDEX_NAME=p_name;
    IF n=0 AND p_existing_only THEN RETURN; END IF;
    IF n<>1 THEN RAISE_APPLICATION_ERROR(-20052,'AGENT_A_INDEX_MISSING ' || p_name); END IF;
    SELECT TABLE_OWNER,TABLE_NAME,STATUS,UNIQUENESS
      INTO actual_owner,actual_table,actual_status,actual_unique
      FROM ALL_INDEXES WHERE OWNER=c_owner AND INDEX_NAME=p_name;
    IF actual_owner<>c_owner OR actual_table<>p_table OR actual_status<>'VALID'
       OR actual_unique<>'NONUNIQUE' THEN
      RAISE_APPLICATION_ERROR(-20053,'AGENT_A_INDEX_STRUCTURE ' || p_name);
    END IF;
    expected_count := REGEXP_COUNT(p_cols,',')+1;
    SELECT COUNT(*) INTO actual_count FROM ALL_IND_COLUMNS
      WHERE INDEX_OWNER=c_owner AND INDEX_NAME=p_name;
    IF actual_count<>expected_count THEN
      RAISE_APPLICATION_ERROR(-20054,'AGENT_A_INDEX_COLUMNS ' || p_name);
    END IF;
    FOR pos IN 1..expected_count LOOP
      wanted := REGEXP_SUBSTR(p_cols,'[^,]+',1,pos);
      SELECT COLUMN_NAME,DESCEND INTO actual_col,direction FROM ALL_IND_COLUMNS
        WHERE INDEX_OWNER=c_owner AND INDEX_NAME=p_name AND COLUMN_POSITION=pos;
      expression_text := NULL;
      BEGIN
        SELECT COLUMN_EXPRESSION INTO expression_text FROM ALL_IND_EXPRESSIONS
          WHERE INDEX_OWNER=c_owner AND INDEX_NAME=p_name AND COLUMN_POSITION=pos;
      EXCEPTION WHEN NO_DATA_FOUND THEN NULL;
      END;
      IF direction<>'ASC' THEN
        RAISE_APPLICATION_ERROR(-20055,'AGENT_A_INDEX_ORDER ' || p_name);
      END IF;
      IF wanted IN ('STRT_DTTM','CHG_DTTM') THEN
        IF NVL(REGEXP_REPLACE(expression_text,'[[:space:]]',''),'?') <>
           'SYS_EXTRACT_UTC("' || wanted || '")' THEN
          RAISE_APPLICATION_ERROR(-20056,'AGENT_A_INDEX_TIME ' || p_name || '.' || wanted);
        END IF;
      ELSIF actual_col<>wanted OR expression_text IS NOT NULL THEN
        RAISE_APPLICATION_ERROR(-20057,'AGENT_A_INDEX_COLUMN ' || p_name || '.' || wanted);
      END IF;
    END LOOP;
  END;
  PROCEDURE create_missing(p_name VARCHAR2, p_kind VARCHAR2, p_ddl VARCHAR2) IS
    n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM ALL_OBJECTS
      WHERE OWNER=c_owner AND OBJECT_NAME=p_name AND OBJECT_TYPE=p_kind;
    IF n=0 THEN
      BEGIN
        EXECUTE IMMEDIATE p_ddl;
      EXCEPTION WHEN OTHERS THEN
        -- A concurrent identical CREATE is accepted only after final verification.
        IF SQLCODE<>-955 THEN RAISE; END IF;
        SELECT COUNT(*) INTO n FROM ALL_OBJECTS
          WHERE OWNER=c_owner AND OBJECT_NAME=p_name AND OBJECT_TYPE=p_kind;
        IF n<>1 THEN RAISE; END IF;
      END;
    END IF;
  END;
BEGIN
  -- Check all visible existing objects before issuing any CREATE.
  verify_tables(TRUE);
'''

def index_check(i, existing):
    return "  verify_index('%s','%s','%s',%s);\n" % (i['name'], i['table'], ','.join(i['columns']), existing)

sql = prefix + '\n'.join('      '+line for line in verify.splitlines()) + after_verify
sql += ''.join(index_check(i, 'TRUE') for i in indexes)
pks = {'AGT_BODY': 'LGL_AR03_PK_A', 'AGT_REC': 'LGL_AR02_PK_A',
       'AGT_RUN': 'LGL_AR01_PK_A', 'EXEC_ST': 'LGL_EXEC_ST_PK_A'}
ddls = {}
for key, table in tables.items():
    cols = [c['name']+' '+c['type']+(' NOT NULL' if c['required'] else '')
            for c in table['columns'].values()]
    cols.append('CONSTRAINT '+pks[key]+' PRIMARY KEY ('+', '.join(table['primary_key'])+')')
    if key=='EXEC_ST':
        cols += ['CONSTRAINT LGL_EXEC_ST_RCK_A CHECK (CHG_SEQ_NO >= 1)',
                 'CONSTRAINT LGL_EXEC_ST_JCK_A CHECK (ST_JSON_CN IS JSON)']
    ddl='CREATE TABLE SIDDA.'+table['name']+' (\n    '+',\n    '.join(cols)+'\n  )'
    ddls[table['name']]=ddl
    sql+="  create_missing('%s','TABLE',q'~%s~');\n" % (table['name'],ddl)
sql+='  verify_tables(FALSE);\n'
for i in indexes:
    ddl='CREATE INDEX SIDDA.'+i['name']+' ON SIDDA.'+i['table']+' ('+', '.join(i['columns'])+')'
    ddls[i['name']]=ddl
    sql+="  create_missing('%s','INDEX',q'~%s~');\n" % (i['name'],ddl)
sql+=''.join(index_check(i, 'FALSE') for i in indexes)
sql+="  DBMS_OUTPUT.PUT_LINE('AGENT_A_READY: 4 tables / 26 columns / 7 indexes verified');\nEND;\n"
assert not re.search(r'^\s*/\s*$',sql,re.M)
for extension in ('sql','txt'):
    (OUT/('AGENT_A_CREATE_ALL_R1.'+extension)).write_text(sql,encoding='utf-8')
(OUT/'VERIFY_TABLES.sql').write_text(verify+'\n')
record={'schema_version':'agent-a-create-block-v1','owner':'SIDDA','tables':tables,'indexes':indexes,
        'ddl':ddls,'sql_sha256':hashlib.sha256(sql.encode()).hexdigest(),
        'mapping_sha256':hashlib.sha256((ROOT/'00_SYSTEM/ORACLE/development_g19_1.json').read_bytes()).hexdigest(),
        'source_reference':str(OLD.relative_to(ROOT)),'external_execution':False}
(OUT/'BUILD.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'tables':4,'columns':26,'indexes':7,'block_bytes':len(sql.encode()),'sql_statements':1}))
