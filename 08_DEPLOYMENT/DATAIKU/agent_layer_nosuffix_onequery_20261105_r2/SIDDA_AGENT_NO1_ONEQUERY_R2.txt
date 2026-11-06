DECLARE
  v_create BOOLEAN := FALSE;

  PROCEDURE ensure_table(
    p_table VARCHAR2, p_columns SYS.ODCIVARCHAR2LIST,
    p_pk_name VARCHAR2, p_pk VARCHAR2, p_checks VARCHAR2 DEFAULT NULL
  ) IS
    n NUMBER;
    ddl_text VARCHAR2(32767);
    col_name VARCHAR2(128);
    expected_type VARCHAR2(128);
    expected_null VARCHAR2(1);
    actual_type VARCHAR2(128);
    actual_null VARCHAR2(1);
    actual_pk VARCHAR2(4000);
  BEGIN
    SELECT COUNT(*) INTO n FROM ALL_TABLES
    WHERE OWNER='SIDDA' AND TABLE_NAME=p_table;
    IF n=0 THEN
      SELECT COUNT(*) INTO n FROM ALL_OBJECTS
      WHERE OWNER='SIDDA' AND OBJECT_NAME=p_table;
      IF n>0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Expected TABLE: SIDDA.'||p_table);
      END IF;
      IF NOT v_create THEN RETURN; END IF;
      ddl_text := 'CREATE TABLE SIDDA.'||p_table||' (';
      FOR i IN 1..p_columns.COUNT LOOP
        IF i>1 THEN ddl_text := ddl_text||','; END IF;
        ddl_text := ddl_text||p_columns(i);
      END LOOP;
      ddl_text := ddl_text||', CONSTRAINT '||p_pk_name||
                  ' PRIMARY KEY ('||p_pk||')'||p_checks||')';
      EXECUTE IMMEDIATE ddl_text;
    END IF;

    SELECT COUNT(*) INTO n FROM ALL_TAB_COLUMNS
    WHERE OWNER='SIDDA' AND TABLE_NAME=p_table;
    IF n<>p_columns.COUNT THEN
      RAISE_APPLICATION_ERROR(-20002, 'Column count differs: SIDDA.'||p_table);
    END IF;
    FOR i IN 1..p_columns.COUNT LOOP
      col_name := SUBSTR(p_columns(i),1,INSTR(p_columns(i),' ')-1);
      expected_type := SUBSTR(p_columns(i),INSTR(p_columns(i),' ')+1);
      expected_null := 'Y';
      IF SUBSTR(expected_type,-9)=' NOT NULL' THEN
        expected_null := 'N';
        expected_type := SUBSTR(expected_type,1,LENGTH(expected_type)-9);
      END IF;
      BEGIN
        SELECT CASE
          WHEN DATA_TYPE IN ('VARCHAR2','CHAR') THEN
            DATA_TYPE||'('||CASE WHEN CHAR_USED='B' THEN DATA_LENGTH ELSE CHAR_LENGTH END||
            CASE WHEN CHAR_USED='B' THEN ' BYTE)' ELSE ' CHAR)' END
          WHEN DATA_TYPE='NUMBER' AND DATA_SCALE=0 THEN
            'NUMBER('||DATA_PRECISION||')'
          WHEN DATA_TYPE IN ('TIMESTAMP WITH TIME ZONE','TIMESTAMP(6) WITH TIME ZONE')
               AND DATA_SCALE=6 THEN 'TIMESTAMP(6) WITH TIME ZONE'
          ELSE DATA_TYPE END, NULLABLE
        INTO actual_type,actual_null
        FROM ALL_TAB_COLUMNS
        WHERE OWNER='SIDDA' AND TABLE_NAME=p_table AND COLUMN_NAME=col_name;
      EXCEPTION WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20003, 'Missing column: SIDDA.'||p_table||'.'||col_name);
      END;
      IF actual_type<>expected_type OR actual_null<>expected_null THEN
        RAISE_APPLICATION_ERROR(-20004, 'Column differs: SIDDA.'||p_table||'.'||col_name||
          ' expected='||expected_type||' nullable='||expected_null||
          ' actual='||actual_type||' nullable='||actual_null);
      END IF;
    END LOOP;
    SELECT LISTAGG(K.COLUMN_NAME,',') WITHIN GROUP (ORDER BY K.POSITION)
    INTO actual_pk
    FROM ALL_CONSTRAINTS C JOIN ALL_CONS_COLUMNS K
      ON C.OWNER=K.OWNER AND C.CONSTRAINT_NAME=K.CONSTRAINT_NAME
      AND C.TABLE_NAME=K.TABLE_NAME
    WHERE C.OWNER='SIDDA' AND C.TABLE_NAME=p_table
      AND C.CONSTRAINT_TYPE='P' AND C.STATUS='ENABLED' AND C.VALIDATED='VALIDATED';
    IF NVL(actual_pk,'?')<>p_pk THEN
      RAISE_APPLICATION_ERROR(-20005, 'Primary key differs: SIDDA.'||p_table);
    END IF;
  END;

  PROCEDURE ensure_index(p_index VARCHAR2,p_table VARCHAR2,p_columns VARCHAR2) IS
    n NUMBER;
    actual_columns VARCHAR2(4000);
    expression_text VARCHAR2(32767);
    col_name VARCHAR2(128);
  BEGIN
    SELECT COUNT(*) INTO n FROM ALL_INDEXES
    WHERE OWNER='SIDDA' AND INDEX_NAME=p_index;
    IF n=0 THEN
      IF NOT v_create THEN RETURN; END IF;
      EXECUTE IMMEDIATE 'CREATE INDEX SIDDA.'||p_index||
        ' ON SIDDA.'||p_table||' ('||p_columns||')';
    END IF;
    SELECT COUNT(*) INTO n FROM ALL_INDEXES
    WHERE OWNER='SIDDA' AND INDEX_NAME=p_index
      AND TABLE_OWNER='SIDDA' AND TABLE_NAME=p_table
      AND STATUS='VALID' AND UNIQUENESS='NONUNIQUE'
      AND INDEX_TYPE IN ('NORMAL','FUNCTION-BASED NORMAL');
    IF n<>1 THEN
      RAISE_APPLICATION_ERROR(-20006, 'Index differs: SIDDA.'||p_index);
    END IF;
    FOR r IN (SELECT COLUMN_NAME,COLUMN_POSITION FROM ALL_IND_COLUMNS
              WHERE INDEX_OWNER='SIDDA' AND INDEX_NAME=p_index
              ORDER BY COLUMN_POSITION) LOOP
      expression_text := NULL;
      BEGIN
        SELECT COLUMN_EXPRESSION INTO expression_text FROM ALL_IND_EXPRESSIONS
        WHERE INDEX_OWNER='SIDDA' AND INDEX_NAME=p_index
          AND COLUMN_POSITION=r.COLUMN_POSITION;
      EXCEPTION WHEN NO_DATA_FOUND THEN NULL;
      END;
      col_name := r.COLUMN_NAME;
      IF expression_text IS NOT NULL THEN
        col_name := REGEXP_SUBSTR(expression_text,
          '^SYS_EXTRACT_UTC\("([A-Z0-9_]+)"\)$',1,1,NULL,1);
        IF col_name IS NULL THEN
          RAISE_APPLICATION_ERROR(-20007, 'Index expression differs: SIDDA.'||p_index);
        END IF;
      END IF;
      IF actual_columns IS NOT NULL THEN actual_columns := actual_columns||','; END IF;
      actual_columns := actual_columns||col_name;
    END LOOP;
    IF NVL(actual_columns,'?')<>p_columns THEN
      RAISE_APPLICATION_ERROR(-20008, 'Index columns differ: SIDDA.'||p_index);
    END IF;
  END;
BEGIN
  -- First validate existing objects; then create missing objects and validate.
  FOR phase IN 1..2 LOOP
    v_create := phase=2;

    ensure_table('LGL_AGT_BODY_A',SYS.ODCIVARCHAR2LIST(
      'SCOPE_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'BODY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'PART_SEQ_NO NUMBER(18) NOT NULL',
      'PART_JSON_CN CLOB NOT NULL'),
      'LGL_AR03_PK_A','SCOPE_HASH_VAL,BODY_HASH_VAL,PART_SEQ_NO');

    ensure_table('LGL_AGT_REC_A',SYS.ODCIVARCHAR2LIST(
      'SCOPE_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'OWNER_KEY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'REC_KIND_CD VARCHAR2(64 BYTE) NOT NULL',
      'REC_KEY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'REC_REV_NO NUMBER(18) NOT NULL',
      'ORD_SEQ_NO NUMBER(18) NOT NULL',
      'LOOKUP_HASH_VAL VARCHAR2(64 BYTE)',
      'BODY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL'),
      'LGL_AR02_PK_A','SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO');

    ensure_table('LGL_AGT_RUN_A',SYS.ODCIVARCHAR2LIST(
      'SCOPE_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'RUN_KEY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'SESS_KEY_HASH_VAL VARCHAR2(64 BYTE)',
      'REQ_KEY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'PRNT_RUN_KEY_HASH_VAL VARCHAR2(64 BYTE)',
      'ST_CD VARCHAR2(32 BYTE) NOT NULL',
      'STRT_DTTM TIMESTAMP(6) WITH TIME ZONE NOT NULL',
      'CHG_DTTM TIMESTAMP(6) WITH TIME ZONE NOT NULL',
      'BODY_HASH_VAL VARCHAR2(64 BYTE) NOT NULL'),
      'LGL_AR01_PK_A','SCOPE_HASH_VAL,RUN_KEY_HASH_VAL');

    ensure_table('LGL_EXEC_ST_A',SYS.ODCIVARCHAR2LIST(
      'SCOPE_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'ST_KEY_ID VARCHAR2(128 BYTE) NOT NULL',
      'CHG_SEQ_NO NUMBER(18) NOT NULL',
      'ST_HASH_VAL VARCHAR2(64 BYTE) NOT NULL',
      'ST_JSON_CN CLOB NOT NULL'),
      'LGL_EXEC_ST_PK_A','SCOPE_HASH_VAL,ST_KEY_ID',
      ', CONSTRAINT LGL_EXEC_ST_RCK_A CHECK (CHG_SEQ_NO >= 1)'||
      ', CONSTRAINT LGL_EXEC_ST_JCK_A CHECK (ST_JSON_CN IS JSON)');

    ensure_index('LGL_AR01_I1_A','LGL_AGT_RUN_A',
      'SCOPE_HASH_VAL,SESS_KEY_HASH_VAL,STRT_DTTM,RUN_KEY_HASH_VAL');
    ensure_index('LGL_AR01_I2_A','LGL_AGT_RUN_A',
      'SCOPE_HASH_VAL,REQ_KEY_HASH_VAL,RUN_KEY_HASH_VAL');
    ensure_index('LGL_AR01_I3_A','LGL_AGT_RUN_A',
      'SCOPE_HASH_VAL,PRNT_RUN_KEY_HASH_VAL,RUN_KEY_HASH_VAL');
    ensure_index('LGL_AR01_I4_A','LGL_AGT_RUN_A',
      'SCOPE_HASH_VAL,ST_CD,CHG_DTTM,RUN_KEY_HASH_VAL');
    ensure_index('LGL_AR02_I1_A','LGL_AGT_REC_A',
      'SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_REV_NO,ORD_SEQ_NO,REC_KEY_HASH_VAL');
    ensure_index('LGL_AR02_I2_A','LGL_AGT_REC_A',
      'SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_REV_NO,LOOKUP_HASH_VAL,ORD_SEQ_NO');
    ensure_index('LGL_AR02_I3_A','LGL_AGT_REC_A',
      'SCOPE_HASH_VAL,REC_KIND_CD,REC_REV_NO,LOOKUP_HASH_VAL,REC_KEY_HASH_VAL,OWNER_KEY_HASH_VAL');
  END LOOP;
  DBMS_OUTPUT.PUT_LINE('SIDDA_AGENT_NO1_READY: 4 tables / 26 columns / 7 indexes');
END;
-- DKU_END_STATEMENT
