"""Create the R2 staging table through a Dataiku Oracle connection, then verify it."""
import re

OWNER='SIDDA'
TABLE='LGL_PIPE_RESULT_A'
FQN=OWNER+'.'+TABLE
CHECK='BYTE_CNT > 0 AND ((SEQ_NO = 0 AND PART_CNT > 0) OR (SEQ_NO > 0 AND PART_CNT = 0))'
COLS=[
    ('JOB_ID','VARCHAR2',32,None,'N'),('SEQ_NO','NUMBER',12,0,'N'),
    ('BIND_HASH','VARCHAR2',64,None,'N'),('DATA_HASH','VARCHAR2',64,None,'N'),
    ('BYTE_CNT','NUMBER',14,0,'N'),('PART_CNT','NUMBER',12,0,'N'),('BODY_B64','CLOB',None,None,'Y')]
DDL="""CREATE TABLE SIDDA.LGL_PIPE_RESULT_A (
 JOB_ID VARCHAR2(32 BYTE) NOT NULL, SEQ_NO NUMBER(12) NOT NULL,
 BIND_HASH VARCHAR2(64 BYTE) NOT NULL, DATA_HASH VARCHAR2(64 BYTE) NOT NULL,
 BYTE_CNT NUMBER(14) NOT NULL, PART_CNT NUMBER(12) NOT NULL, BODY_B64 CLOB,
 PRIMARY KEY (JOB_ID, SEQ_NO), CHECK ("""+CHECK+'))'


def rows(db,sql):
    frame=db.query_to_df(sql)
    frame=frame.astype(object).where(frame.notna(),None)
    return [tuple(row) for row in frame.itertuples(index=False,name=None)]


def block(db,statement):
    db.query_to_df('SELECT 1 AS OK FROM DUAL',pre_queries=[statement])


def identity(db):
    return rows(db,"SELECT SYS_CONTEXT('USERENV','DB_UNIQUE_NAME'),SYS_CONTEXT('USERENV','CON_NAME'),"
                   "SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL")[0]


def verify(db):
    pred=" OWNER='SIDDA' AND TABLE_NAME='LGL_PIPE_RESULT_A'"
    found=rows(db,"SELECT COLUMN_NAME,DATA_TYPE,CASE WHEN DATA_TYPE='VARCHAR2' AND CHAR_USED='B' "
                  "THEN DATA_LENGTH WHEN DATA_TYPE='NUMBER' THEN DATA_PRECISION END,DATA_SCALE,NULLABLE "
                  "FROM ALL_TAB_COLUMNS WHERE"+pred+" ORDER BY COLUMN_ID")
    if found!=COLS:
        raise ValueError('EXISTING_AGENT_TABLE_COLUMNS_DIFFER')
    pk=rows(db,"SELECT cc.COLUMN_NAME FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS cc ON "
               "c.OWNER=cc.OWNER AND c.CONSTRAINT_NAME=cc.CONSTRAINT_NAME WHERE c.OWNER='SIDDA' AND "
               "c.TABLE_NAME='LGL_PIPE_RESULT_A' AND c.CONSTRAINT_TYPE='P' AND c.STATUS='ENABLED' "
               "AND c.VALIDATED='VALIDATED' ORDER BY cc.POSITION")
    checks=rows(db,"SELECT SEARCH_CONDITION_VC FROM ALL_CONSTRAINTS WHERE"+pred+
                " AND CONSTRAINT_TYPE='C' AND STATUS='ENABLED' AND VALIDATED='VALIDATED'")
    normalize=lambda s:re.sub(r'[\s"]+','',s.upper())
    if pk!=[('JOB_ID',),('SEQ_NO',)] or not any(normalize(c[0])==normalize(CHECK) for c in checks):
        raise ValueError('EXISTING_AGENT_TABLE_KEY_OR_CHECK_DIFFERS')


def setup(config):
    import dataiku
    admin=dataiku.SQLExecutor2(connection=config['SETUP_CONNECTION'])
    reader=dataiku.SQLExecutor2(connection=config['AGENT_CONNECTION'])
    db,pdb,operator=identity(admin)
    rdb,rpdb,reader_user=identity(reader)
    if (db,pdb)!=(rdb,rpdb) or operator!=config['EXPECTED_SETUP_USER']:
        raise ValueError('SETUP_DB_OR_ACCOUNT_MISMATCH')
    writer=config['GENOS_DB_USER']
    for user in (writer,reader_user):
        if not re.fullmatch('[A-Z][A-Z0-9_$#]{0,127}',user or '') or user in ('SYS','SYSTEM','PUBLIC'):
            raise ValueError('SPECIFY_ACTUAL_APPLICATION_DATABASE_USER')
    if not rows(admin,"SELECT 1 FROM ALL_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_PIPE_RESULT_A'"):
        # Concurrent creation or a lost DDL acknowledgement is reconciled by the dictionary check.
        block(admin,"BEGIN EXECUTE IMMEDIATE '"+DDL+"'; EXCEPTION WHEN OTHERS THEN "
                    "IF SQLCODE != -955 THEN RAISE; END IF; END;")
    verify(admin)
    privileges={writer:{'SELECT','INSERT'}}
    privileges.setdefault(reader_user,set()).add('SELECT')
    for user,wanted in privileges.items():
        if user==OWNER:
            continue
        if rows(admin,"SELECT USERNAME FROM ALL_USERS WHERE USERNAME='"+user+"'")!=[(user,)]:
            raise ValueError('UNKNOWN_DATABASE_USER:'+user)
        def actual():
            return {r[0] for r in rows(admin,"SELECT PRIVILEGE FROM ALL_TAB_PRIVS WHERE TABLE_SCHEMA='SIDDA' "
                "AND TABLE_NAME='LGL_PIPE_RESULT_A' AND GRANTEE='"+user+"'")}
        missing=sorted(wanted-actual())
        if missing:
            block(admin,"BEGIN EXECUTE IMMEDIATE 'GRANT "+','.join(missing)+" ON "+FQN+" TO "+user+"'; END;")
        if wanted-actual():
            raise ValueError('STAGE_GRANT_NOT_CONFIRMED:'+user)
    rows(reader,'SELECT JOB_ID FROM '+FQN+' WHERE 1=0')
    print('AGENT_LAYER_READY',FQN,db,pdb)
