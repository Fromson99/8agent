"""Disposable local Oracle, all nine actual DDL tables, exact JDBC SQL strings.

No connection to GENOS/Dataiku. DB-API represents SQLExecutor2's execution port.
"""
import json
import os
from pathlib import Path
import re
import subprocess

import pytest
from test_compact_v2_rag import structured_generation
from lawrag.pipeline import oracle_full_package as pack
from lawrag.pipeline.oracle_query_dataiku import DataikuClient
from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.skipif(os.environ.get('A8_FULL_PARTS_LIVE')!='1',reason='disposable local Oracle opt-in')


@pytest.fixture
def live():
    import oracledb
    import pandas as pd
    inspected=json.loads(subprocess.check_output(['docker','inspect','a8-full-parts-20261020']))[0]
    assert inspected['Config']['Labels']['a8.task']=='full-parts-20261020'
    endpoint=inspected['NetworkSettings']['Ports']['1521/tcp'][0]
    assert endpoint['HostIp']=='127.0.0.1'
    conn=oracledb.connect(user='SIDDA',password=Path('/tmp/a8-full-parts-docker/test-password').read_text(),dsn='127.0.0.1:'+endpoint['HostPort']+'/FREEPDB1')
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
    try:yield conn,DataikuClient(Executor(),'LOCAL_SYNTHETIC_FULL','LOCAL_TEST')
    finally:conn.close()


def test_actual_full_dataiku_sql_empty_oracle_to_serving_read(live,structured_generation,tmp_path):
    conn,client=live
    ddl=(ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_all_tables_20261019_r1/LEGAL_ORACLE_ALL_9_TABLES_20261019_R1.sql').read_text()
    ddl=re.sub(r'--[^\n]*','',ddl)
    with conn.cursor() as cur:
        for statement in ddl.split(';'):
            if statement.strip().startswith(('CREATE TABLE','CREATE INDEX')):cur.execute(statement.strip())
    pack.export(structured_generation,tmp_path/'out')
    pack.restore(tmp_path/'out/download',tmp_path/'restored')
    binding,_=client.identity()
    kwargs={'target_binding':binding,'directory':tmp_path/'logs'}
    assert pack.import_generation(client,tmp_path/'restored',action='check',**kwargs)['writes'] is False
    result=pack.import_generation(client,tmp_path/'restored',action='publish',**kwargs)
    assert result['status']=='FULL_DATA_VERIFIED'
    assert pack.import_generation(client,tmp_path/'restored',action='status',**kwargs)==result
    assert pack.import_generation(client,tmp_path/'restored',action='publish',**kwargs)==result
    sql=io.SQL(client,journal=tmp_path/'serving.jsonl',binding=binding)
    value=q.read_release(sql,result['query_release_id'])
    from semantic_runtime.oracle_query import QuerySQL
    import time
    reader=q.Records(QuerySQL(client,binding=binding,deadline=time.monotonic()+60),result['query_release_id'],value)
    first=next(k for k,v in value['tables'].items() if v['rows'])
    assert reader.page(first,limit=2)['rows']
    assert q.active(sql,'main') is None
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM SIDDA.LEGAL_RAG_QUERY_STATE_A');assert cur.fetchone()[0]==0
    # Old COMPLETE is not accepted after one asset part is deleted.
    with conn.cursor() as cur:
        cur.execute('DELETE FROM SIDDA.LEGAL_RAG_ASSET_PART_A WHERE ROWNUM=1');conn.commit()
    with pytest.raises(io.DPError,match='ASSET_MISSING'):
        pack.import_generation(client,tmp_path/'restored',action='status',**kwargs)
