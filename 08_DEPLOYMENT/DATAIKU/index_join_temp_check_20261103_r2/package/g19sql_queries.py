"""SELECT-only dictionary and cached cursor inspection. No application data reads."""
import re
from g19sql_common import identifier, literal

IDENTITY = "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL"


def bounded(sql, limit):
    return 'SELECT * FROM ('+sql+') WHERE ROWNUM <= '+str(limit+1)


def metadata(ctx):
    owner,table = literal(identifier(ctx['owner'])),literal(identifier(ctx['table']))
    where = 'OWNER='+owner+' AND TABLE_NAME='+table
    idxwhere = 'TABLE_OWNER='+owner+' AND TABLE_NAME='+table
    queries = [
        ('object',"SELECT OWNER,OBJECT_NAME,OBJECT_ID,DATA_OBJECT_ID FROM ALL_OBJECTS WHERE OBJECT_TYPE='TABLE' AND OWNER="+owner+' AND OBJECT_NAME='+table,2),
        ('table_stats',"SELECT OWNER,TABLE_NAME,NUM_ROWS,BLOCKS,AVG_ROW_LEN,PARTITIONED,TEMPORARY,TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED FROM ALL_TABLES WHERE "+where,2),
        ('indexes',"SELECT OWNER,INDEX_NAME,INDEX_TYPE,UNIQUENESS,STATUS,VISIBILITY,PARTITIONED,NUM_ROWS,DISTINCT_KEYS,LEAF_BLOCKS,CLUSTERING_FACTOR,TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED FROM ALL_INDEXES WHERE "+idxwhere+' ORDER BY OWNER,INDEX_NAME',64),
        ('index_columns','SELECT INDEX_OWNER,INDEX_NAME,COLUMN_NAME,COLUMN_POSITION,DESCEND FROM ALL_IND_COLUMNS WHERE '+idxwhere+' ORDER BY INDEX_OWNER,INDEX_NAME,COLUMN_POSITION',256),
        ('constraints',"SELECT OWNER,CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED,INDEX_OWNER,INDEX_NAME FROM ALL_CONSTRAINTS WHERE "+where+" AND CONSTRAINT_TYPE IN ('P','U') ORDER BY CONSTRAINT_NAME",32),
        ('constraint_columns',"SELECT c.CONSTRAINT_NAME,c.COLUMN_NAME,c.POSITION FROM ALL_CONS_COLUMNS c JOIN ALL_CONSTRAINTS k ON k.OWNER=c.OWNER AND k.CONSTRAINT_NAME=c.CONSTRAINT_NAME WHERE c.OWNER="+owner+' AND c.TABLE_NAME='+table+" AND k.CONSTRAINT_TYPE IN ('P','U') ORDER BY c.CONSTRAINT_NAME,c.POSITION",128),
        ('column_types','SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,CHAR_LENGTH,NULLABLE FROM ALL_TAB_COLUMNS WHERE '+where+' ORDER BY COLUMN_ID',64),
        ('stats_state',"SELECT OWNER,TABLE_NAME,OBJECT_TYPE,STALE_STATS,STATTYPE_LOCKED,TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED FROM ALL_TAB_STATISTICS WHERE "+where+" AND OBJECT_TYPE='TABLE'",2),
    ]
    return [(n,bounded(s,limit),limit) for n,s,limit in queries]


def candidates(ctx):
    owner,table = literal(ctx['owner']),literal(ctx['table'])
    login = literal(ctx['database'][0]['LOGIN_USER'])
    # Every selected cursor actually references this table or an index on it in its cached plan.
    # The same account/table can have other jobs: selection does NOT establish run ownership.
    sql = ("SELECT q.INST_ID,q.SQL_ID,q.CHILD_NUMBER,q.PLAN_HASH_VALUE,q.EXECUTIONS,q.ELAPSED_TIME,q.CPU_TIME,q.BUFFER_GETS,q.DISK_READS,q.ROWS_PROCESSED,q.PARSING_SCHEMA_NAME,TO_CHAR(q.LAST_ACTIVE_TIME,'YYYY-MM-DD HH24:MI:SS') AS LAST_ACTIVE_TIME "
        'FROM GV$SQL q WHERE q.PARSING_SCHEMA_NAME='+login+" AND q.LAST_ACTIVE_TIME>=SYSDATE-1 AND q.COMMAND_TYPE IN (2,3) AND EXISTS ("
        'SELECT 1 FROM GV$SQL_PLAN p WHERE p.INST_ID=q.INST_ID AND p.SQL_ID=q.SQL_ID AND p.CHILD_NUMBER=q.CHILD_NUMBER AND '
        '((p.OBJECT_OWNER='+owner+' AND p.OBJECT_NAME='+table+') OR EXISTS ('
        'SELECT 1 FROM ALL_INDEXES i WHERE i.TABLE_OWNER='+owner+' AND i.TABLE_NAME='+table+' AND i.OWNER=p.OBJECT_OWNER AND i.INDEX_NAME=p.OBJECT_NAME))) '
        'ORDER BY q.LAST_ACTIVE_TIME DESC,q.INST_ID,q.SQL_ID,q.CHILD_NUMBER')
    return bounded(sql,12)


def cursor_where(sql_id, child, plan, instance):
    if not re.fullmatch('[0-9a-z]{13}',str(sql_id)): raise ValueError('INVALID_SQL_ID')
    if type(child) is not int or child<0 or type(plan) is not int or plan<0 or type(instance) is not int or instance<1: raise ValueError('INVALID_CURSOR_ID')
    return 'INST_ID='+str(instance)+' AND SQL_ID='+literal(sql_id)+' AND CHILD_NUMBER='+str(child)+' AND PLAN_HASH_VALUE='+str(plan)


def plans(cursor, pk_columns=()):
    where = cursor_where(cursor['SQL_ID'],cursor['CHILD_NUMBER'],cursor['PLAN_HASH_VALUE'],cursor['INST_ID'])
    markers=''.join(
        ',CASE WHEN INSTR(UPPER('+predicate+'),'+literal('"'+identifier(column)+'"')+
        ')>0 THEN 1 ELSE 0 END AS PK_'+kind+'_'+str(i+1)
        for i,column in enumerate(pk_columns)
        for predicate,kind in (('ACCESS_PREDICATES','ACCESS'),('FILTER_PREDICATES','FILTER')))
    return [
        ('plan','SELECT ID,PARENT_ID,OPERATION,OPTIONS,OBJECT_OWNER,OBJECT_NAME,CARDINALITY,BYTES,COST,TEMP_SPACE'+markers+' FROM GV$SQL_PLAN WHERE '+where+' ORDER BY ID',256),
        ('runtime','SELECT ID,LAST_STARTS,LAST_OUTPUT_ROWS,LAST_CR_BUFFER_GETS,LAST_DISK_READS,LAST_DISK_WRITES,LAST_ELAPSED_TIME,LAST_MEMORY_USED,LAST_TEMPSEG_SIZE,MAX_TEMPSEG_SIZE,LAST_EXECUTION FROM GV$SQL_PLAN_STATISTICS_ALL WHERE '+where+' ORDER BY ID',256)
    ]


def temp(ctx):
    sql = ('SELECT INST_ID,USERNAME,SQL_ID,SQL_ID_TEMPSEG,TABLESPACE,SEGTYPE,SUM(BLOCKS) AS BLOCKS '
           'FROM GV$TEMPSEG_USAGE WHERE USERNAME='+literal(ctx['database'][0]['LOGIN_USER'])+
           ' GROUP BY INST_ID,USERNAME,SQL_ID,SQL_ID_TEMPSEG,TABLESPACE,SEGTYPE ORDER BY BLOCKS DESC')
    return bounded(sql,100)


def readonly(sql):
    # Quoted strings are data. All executable tokens must be a single SELECT.
    scrubbed = re.sub(r"'(?:''|[^'])*'", "''", sql)
    if not re.match(r'^\s*SELECT\b',scrubbed,re.I) or ';' in scrubbed or '--' in scrubbed or '/*' in scrubbed:
        raise ValueError('READONLY_SQL_GUARD')
    if re.search(r'\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|COMMIT|ROLLBACK|BEGIN|DECLARE|EXECUTE|EXPLAIN|DBMS_STATS|DBMS_LOB|DBMS_XPLAN|FOR\s+UPDATE)\b',scrubbed,re.I):
        raise ValueError('READONLY_SQL_GUARD')
    return sql


def local_view_sql(sql):
    """Equivalent local-instance query; retain an explicit instance gate for cursors.

    V$ access can also fail. This does not grant privileges or reconstruct past TEMP.
    Each JDBC request can land on another RAC instance. A cursor from another
    instance is therefore excluded, never silently substituted.
    """
    instance="TO_NUMBER(SYS_CONTEXT('USERENV','INSTANCE'))"
    sql=re.sub(r'\b([qp])\.INST_ID\b',instance,sql)
    # Local projections still emit the original INST_ID result column.
    sql=sql.replace('SELECT '+instance+',','SELECT '+instance+' AS INST_ID,',1)
    sql=sql.replace('SELECT INST_ID,','SELECT '+instance+' AS INST_ID,',1)
    sql=re.sub(r'(?<![A-Za-z_])INST_ID=(\d+)',lambda m:instance+'='+m.group(1),sql)
    sql=sql.replace('GROUP BY INST_ID,','GROUP BY '+instance+',')
    return sql.replace('GV$','V$')
