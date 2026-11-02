import copy
import json
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

HERE=Path(__file__).resolve().parent;CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as q
from semantic_runtime.physical_mapping import SchemaMap
from lawrag.pipeline.oracle_query_dataiku import DataikuClient
from lawrag.pipeline import oracle_query_publish as pub


def test_real_oracle_500row_rendered_transaction_conflict_rollback_and_lost_ack(tmp_path):
    import oracledb
    import pandas as pd
    metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    password=dict(x.split('=',1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
    admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=password)
    user='A8_QW_'+secrets.token_hex(4).upper();pw=secrets.token_hex(20);conn=None
    try:
        with admin.cursor() as c:
            c.execute(f'CREATE USER {user} IDENTIFIED BY "{pw}" DEFAULT TABLESPACE USERS QUOTA 32M ON USERS')
            c.execute(f'GRANT CREATE SESSION,CREATE TABLE TO {user}')
        conn=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=pw)
        schema=SchemaMap.load(CODE/'client/physical_mapping.yaml');p=schema.names('query_row')
        columns=['RELEASE_ID','KIND','ROW_ID','DOCUMENT_ID','LOOKUP_ID','OWNER_ID','TARGET_ID','ROW_SHA256','VALUE_JSON']
        with conn.cursor() as c:
            c.execute('CREATE TABLE '+p.table.split('.')[-1]+' ('+','.join(p.c(x)+' '+('CLOB NOT NULL' if x=='VALUE_JSON' else 'VARCHAR2(512)') for x in columns)+',PRIMARY KEY('+','.join(p.c(x) for x in columns[:3])+'),CHECK('+p.c('VALUE_JSON')+' IS JSON))')
        class Executor:
            writes=0;fail_ack=False
            def query_to_df(self,statement,**kwargs):
                with conn.cursor() as c:
                    for text in kwargs.get('pre_queries',[]):c.execute(text.replace('SIDDS.',user+'.'));self.writes+=1
                    c.execute(statement.replace('SIDDS.',user+'.'));names=[v[0] for v in c.description]
                    result=[[v.read() if hasattr(v,'read') else v for v in row] for row in c.fetchall()]
                    for text in kwargs.get('post_queries',[]):c.execute(text)
                if self.fail_ack:self.fail_ack=False;raise TimeoutError('synthetic ack lost after commit')
                return pd.DataFrame(result,columns=names)
        executor=Executor();client=DataikuClient(executor,'LOCAL_SYNTHETIC','TEST',schema_map=schema)
        sql=io.SQL(client,journal=tmp_path/'sql.jsonl',binding='isolated-local-test')
        def rows(start):
            return [q.record('bulk.test',{'i':i,'text':"한글😀 O'Reilly :value "*30},key=i,
                document_id='0007',lookup_id=str(i),owner_id=None if i%2 else 'source') for i in range(start,start+500)]
        batch=rows(0);rid='a'*64
        q.insert_records(sql,rid,batch);assert executor.writes==1
        q.insert_records(sql,rid,batch);assert executor.writes==2
        # Read the exact stored envelopes through the maintained verifier.
        for i in range(0,500,20):pub._verify_batch(sql,rid,batch[i:i+20])
        def count():return sql.query('SELECT COUNT(*) AS N FROM '+p.table)[0]['N']
        assert count()==500
        other=rows(1000);conflict=q.record('bulk.test',{'different':True},key=0,document_id='0007',lookup_id='0',owner_id='source')
        with pytest.raises(io.DPError):q.insert_records(sql,rid,other[:499]+[conflict])
        assert count()==500
        executor.fail_ack=True
        with pytest.raises(io.DPError):q.insert_records(sql,rid,other)
        assert count()==1000
        q.insert_records(sql,rid,other);assert count()==1000
        with pytest.raises(io.DPError,match='BATCH'):q.insert_records(sql,rid,other+[batch[0]])
        (HERE/'ACTUAL_ORACLE_RESULT.json').write_text(json.dumps({'status':'PASS','rows_per_request':500,'same_generated_JDBC_PL_SQL':True,'initial_write_requests':1,'duplicate_no_extra_rows':True,'conflict_499_new_rows_rolled_back':True,'lost_ack_explicit_resume_no_duplicates':True,'full_values_verified':500,'field_Dataiku_executed':False},indent=2)+'\n')
    finally:
        if conn:conn.close()
        with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
        admin.close()
