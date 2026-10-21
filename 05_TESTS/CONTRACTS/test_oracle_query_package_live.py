"""Local disposable Oracle only: execute the exact Dataiku JDBC SQL strings.

DSS itself is unavailable; query_to_df is represented by a DB-API session.
"""
import json
import os
from pathlib import Path
import subprocess
import uuid
import pytest
from test_oracle_query_package import package
from test_oracle_query_handoff_20261020 import handoff
from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation
from lawrag.pipeline import oracle_query_package as pack
from lawrag.pipeline.oracle_query_dataiku import DataikuClient,render
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as q
from semantic_runtime.oracle_dp_assets import clob_text

pytestmark=pytest.mark.skipif(os.environ.get('A8_QUERY_PARTS_LIVE')!='1',reason='local disposable Oracle opt-in')

@pytest.fixture
def live():
    import oracledb
    import pandas as pd
    inspected=json.loads(subprocess.check_output(['docker','inspect','a8-query-parts-20261020']))[0]
    assert inspected['Config']['Labels']['a8.task']=='query-parts-20261020'
    endpoint=inspected['NetworkSettings']['Ports']['1521/tcp'][0]
    assert endpoint['HostIp']=='127.0.0.1'
    conn=oracledb.connect(user='SIDDA',password=Path('/tmp/a8-query-parts-docker/test-password').read_text(),dsn='127.0.0.1:'+endpoint['HostPort']+'/FREEPDB1')
    class Executor:
        def query_to_df(self,text,pre_queries=(),post_queries=(),infer_from_schema=False,parse_dates=True):
            try:
                with conn.cursor() as cur:
                    for statement in pre_queries:cur.execute(statement)
                    cur.execute(text)
                    names=[c[0] for c in cur.description]
                    rows=[[v.read() if isinstance(v,oracledb.LOB) else v for v in row] for row in cur]
                    for statement in post_queries:cur.execute(statement)
                    return pd.DataFrame(rows,columns=names)
            except BaseException:conn.rollback();raise
    try:yield conn,DataikuClient(Executor(),'LOCAL_SYNTHETIC','LOCAL_TEST')
    finally:conn.close()


def test_live_jdbc_full_transfer_matches_query_release(live,package,tmp_path):
    conn,client=live
    with conn.cursor() as cur:
        for statement in q.DDL:
            try:cur.execute(statement)
            except Exception as exc:
                if 'ORA-00955' not in str(exc):raise
        try:cur.execute('CREATE TABLE SIDDA.LEGAL_RAG_RELEASE_A(RELEASE_ID VARCHAR2(64 BYTE) PRIMARY KEY,DATASET_VERSION VARCHAR2(64 BYTE),RELEASE_JSON CLOB)')
        except Exception as exc:
            if 'ORA-00955' not in str(exc):raise
        source=pack.verify_db(package[0]/pack.DB_NAME)['source_release'];sid=io.digest(source)
        cur.execute('INSERT INTO SIDDA.LEGAL_RAG_RELEASE_A VALUES(:r,:v,:body)',r=sid,v=source['dataset_version'],body=io.canonical(source));conn.commit()
    binding,target=client.identity()
    assert target['LOGIN_USER']=='SIDDA'
    args=dict(target_binding=binding,directory=tmp_path/'jdbc-import')
    assert pack.import_db(client,package[0]/pack.DB_NAME,action='check',**args)['status']=='READY_TO_IMPORT'
    result=pack.import_db(client,package[0]/pack.DB_NAME,action='publish',**args)
    assert result['status']=='COMPLETE'
    assert pack.import_db(client,package[0]/pack.DB_NAME,action='status',**args)['status']=='QUERY_PUBLICATION_VERIFIED'
    # Read through the actual serving catalogue and selective row port.
    sql=io.SQL(client,journal=tmp_path/'reader.jsonl',binding=binding)
    value=q.read_release(sql,result['release_id'])
    assert value==pack.verify_db(package[0]/pack.DB_NAME)['query_manifest']
    from semantic_runtime.oracle_query import QuerySQL
    import time
    reader=q.Records(QuerySQL(client,binding=binding,deadline=time.monotonic()+60),result['release_id'],value)
    firstkind=next(k for k,v in value['tables'].items() if v['rows'])
    assert reader.page(firstkind,limit=2)['rows']
    assert q.active(sql,'main') is None


def test_live_unicode_large_clob_literal_and_rollback(live,tmp_path):
    conn,client=live
    table='QP_CLOB_'+uuid.uuid4().hex[:12].upper()
    with conn.cursor() as cur:
        cur.execute('CREATE TABLE '+table+'(ID VARCHAR2(50),BODY CLOB)')
    content="한글😀' & :id /* :body */\n"*10000
    statement='BEGIN INSERT INTO '+table+' VALUES(:id,:body); COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;'
    sql=io.SQL(client,journal=tmp_path/'clob.jsonl',binding='local-clob')
    identifier="x'); --"
    sql.request(statement,[('id',identifier,'VARCHAR2'),('body',content,'CLOB')],write=True)
    assert clob_text(sql,table,'BODY','ID=:id',[('id',identifier,'VARCHAR2')])==content
    # Transaction failure remains a failure; original row remains the only row.
    bad='BEGIN INSERT INTO '+table+' VALUES(:id,:body); RAISE_APPLICATION_ERROR(-20099,\'test\'); COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;'
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):
        sql.request(bad,[('id','failed','VARCHAR2'),('body','not saved','CLOB')],write=True)
    assert sql.query('SELECT COUNT(*) AS N FROM '+table)==[{'N':1}]
