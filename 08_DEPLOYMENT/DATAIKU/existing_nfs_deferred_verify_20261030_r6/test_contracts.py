"""Exact R5 package contracts. Models/internal networks are never used."""
import ast
import copy
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TEMP=tempfile.TemporaryDirectory(prefix='nfs-r6-contract-')
CODE=Path(TEMP.name)
with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R6.zip') as z: z.extractall(CODE)
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from semantic_runtime import oracle_dp_io as io
from lawrag.pipeline import oracle_migration as migration, oracle_full_package as full
from lawrag.pipeline.oracle_query_dataiku import DataikuClient,render
from semantic_runtime.physical_mapping import SchemaMap
from managed_job import BudgetClient

for source, names in [(ROOT/'05_TESTS/CONTRACTS/test_oracle_dp.py',{'fixture_source','substring','Oracle'}),
                      (HERE.with_name('existing_nfs_fast_20261030_r3')/'test_batch_read.py',{'batch_response'})]:
    text=source.read_text()
    for node in ast.parse(text).body:
        if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names:
            exec(compile(ast.get_source_segment(text,node),str(source),'exec'),globals())



def test_exact_package_and_pins():
    assert Path(io.__file__).is_relative_to(CODE)
    assert Path(migration.__file__).is_relative_to(CODE)
    for n,h in json.loads((CODE/'PACKAGE_FILES.json').read_text()).items():
        assert io.file_sha(CODE/n)==h
    for n,h in json.loads((CODE/'client/CODE_PINS.json').read_text())['files'].items():
        assert io.file_sha(CODE/'client'/n)==h
    with zipfile.ZipFile(HERE.with_name('existing_nfs_bulk_verify_20261030_r5')/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R5.zip') as z:
        changed=[n for n in z.namelist() if z.read(n)!=(CODE/n).read_bytes()]
    assert len(changed)==5
    assert (CODE/'client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py').is_file()

@pytest.mark.parametrize('exhausted',['deadline','calls'])
def test_original_job_limits_cannot_be_reset(exhausted):
    from types import SimpleNamespace
    value=dict(deadline=0 if exhausted=='deadline' else 10**12,reserved_sql_calls=1000000 if exhausted=='calls' else 0)
    calls=[]
    client=SimpleNamespace(SQL_PATH='fake',schema_map=None,request=lambda *a,**k:calls.append(1))
    store=SimpleNamespace(value=value,save=lambda:calls.append('save'))
    budget=BudgetClient(client,store)
    with pytest.raises(io.BudgetPause,match='JOB_'):
        budget.request()
    assert calls==[]

@pytest.mark.parametrize('origin',['r23','r4','r5','r23_via_r4','r23_via_r5','r4_via_r5'])
def test_upgrade_preserves_state_and_history(tmp_path,origin):
    r23='36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'
    r4='6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0'
    r5='10b657b98b1a92ec0c17e56deb42c472fcfce6f794dbb3d2800b7bb999b2b47f'
    identity={'target':'DB','data':'DATA','generation':'PATH','code':r5 if origin=='r5' else r4 if origin in {'r4','r4_via_r5'} else r23}
    expected=dict(identity,code=io.file_sha(full.__file__))
    state={'identity':identity,'deadline':12345,'status':'PAUSED','stages':{'source':{'rows':100}},'pending':{'rows':4}}
    if origin=='r23_via_r4':
        state['compatible_executor']={'origin_code_sha256':r23,'execution_code_sha256':r4,'policy':'existing-nfs-r4-remove-invocation-cap-v1'}
    if origin.endswith('_via_r5'):
        state['compatible_executor']={'origin_code_sha256':identity['code'],'execution_code_sha256':r5,'policy':'existing-nfs-r5-native-source-verify-v1'}
    io.atomic_json(tmp_path/'full-state.json',state);before=copy.deepcopy(state);raw=(tmp_path/'full-state.json').read_bytes()
    assert full._import_identity(state,expected,tmp_path)==identity
    for k,v in before.items():
        if k!='compatible_executor': assert state[k]==v
    record=state['compatible_executor']
    assert (tmp_path/record['prior_receipt_file']).read_bytes()==raw
    if '_via_' in origin:assert state['compatible_executor_history']==[before['compatible_executor']]
    io.atomic_json(tmp_path/'full-state.json',state);saved=copy.deepcopy(state)
    assert full._import_identity(state,expected,tmp_path)==identity and state==saved

@pytest.mark.parametrize('field',['data','target','generation','code'])
def test_wrong_binding_rejected(tmp_path,field):
    original=dict(target='D',data='S',generation='P',code='6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0')
    current=dict(original,code=io.file_sha(full.__file__));original[field]='wrong'
    with pytest.raises(io.DPError,match='IMPORT_BINDING'):
        full._import_identity({'identity':original},current,tmp_path)

def test_unknown_previous_executor_rejected(tmp_path):
    identity=dict(target='D',data='S',code='6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0')
    state={'identity':identity,'compatible_executor':{'origin_code_sha256':identity['code'],'execution_code_sha256':'unapproved'}}
    with pytest.raises(io.DPError,match='compatible executor'):
        full._import_identity(state,dict(identity,code=io.file_sha(full.__file__)),tmp_path)

@pytest.fixture(scope='module')
def actual_oracle():
    import oracledb,secrets
    meta=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert meta['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    password=dict(x.split('=',1) for x in meta['Config']['Env'])['ORACLE_PASSWORD']
    admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=password)
    user='A8_BULK_'+secrets.token_hex(4).upper();pw=secrets.token_hex(20)
    conn=None
    try:
        with admin.cursor() as c:
            c.execute(f'CREATE USER {user} IDENTIFIED BY "{pw}" DEFAULT TABLESPACE USERS QUOTA 16M ON USERS')
            c.execute(f'GRANT CREATE SESSION,CREATE TABLE TO {user}')
        conn=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=pw)
        schema=SchemaMap.load(CODE/'client/physical_mapping.yaml')
        with conn.cursor() as c:
            n=schema.names('block_payload')
            cols=[n.c(k)+' '+('CLOB' if k in io.CLOBS else 'NUMBER' if k=='JSON_TEXT_ELIDED' else 'VARCHAR2(512)') for k in io.COLUMNS['block_payload']]
            c.execute('CREATE TABLE '+n.table.split('.')[-1]+' ('+','.join(cols)+',PRIMARY KEY('+','.join(n.c(k) for k in io.KEYS['block_payload'])+'))')
            rows=expected_rows()
            rows[0]['TEXT']=None;rows[1]['TEXT']=''
            for row in rows:
                values=[row[k] for k in io.COLUMNS['block_payload']]
                # Empty CLOB must remain different from SQL NULL.
                for i,k in enumerate(io.COLUMNS['block_payload']):
                    if k in io.CLOBS and values[i]=='': values[i]=conn.createlob(oracledb.DB_TYPE_CLOB)
                c.execute('INSERT INTO '+n.table.split('.')[-1]+' VALUES('+','.join(':'+str(i+1) for i in range(len(values)))+')',values)
        conn.commit()
        yield conn,schema,user,rows
    finally:
        if conn: conn.close()
        with admin.cursor() as c: c.execute('DROP USER '+user+' CASCADE')
        admin.close()


def expected_rows():
    return [dict(DATASET_VERSION='a'*64,DOCUMENT_ID='doc',BLOCK_ID=str(i),UNIT_ID='u',TEXT='가😀',
        SOURCE_ARTIFACT_SHA256='b'*64,SOURCE_JSON='{}',JSON_TEXT_ELIDED=0) for i in range(3)]


def test_source_stage_no_readback_and_explicit_verify(tmp_path,monkeypatch):
    source=fixture_source(tmp_path/'source');remote=Oracle()
    original=migration.read_batch
    monkeypatch.setattr(migration,'read_batch',lambda *a,**k:pytest.fail('readback while loading'))
    remote.mode='after_timeout'
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):
        migration.transfer(remote,source,target_binding='t',directory=tmp_path/'log',action='stage')
    result=migration.transfer(remote,source,target_binding='t',directory=tmp_path/'log',action='stage')
    assert result['status']=='SOURCE_STAGED'
    writes=remote.writes
    migration.transfer(remote,source,target_binding='t',directory=tmp_path/'log',action='stage')
    assert remote.writes==writes
    monkeypatch.setattr(migration,'read_batch',original)
    assert migration.transfer(remote,source,target_binding='t',directory=tmp_path/'log',action='verify')['status']=='VERIFIED'
    next(iter(remote.data['block_payload'].values()))['TEXT']='changed'
    with pytest.raises(io.DPError,match='ROW_CONFLICT'):
        migration.transfer(remote,source,target_binding='t',directory=tmp_path/'log',action='verify')


def test_actual_oracle_staged_parts_and_release_guards(actual_oracle,tmp_path):
    import pandas as pd
    from lawrag.pipeline import oracle_deferred_import as deferred
    from semantic_runtime import oracle_dp_assets as assets,oracle_query_catalog as q
    conn,schema,user,rows=actual_oracle
    part=schema.names('asset_part');release=schema.names('query_release')
    with conn.cursor() as c:
        c.execute('CREATE TABLE '+part.table.split('.')[-1]+' ('+
            ','.join(part.c(k)+' '+t for k,t in [('ASSET_SHA256','VARCHAR2(100)'),('PART_NO','NUMBER'),
            ('RAW_BYTES','NUMBER'),('PART_SHA256','VARCHAR2(100)'),('DATA_B64','CLOB')])+',PRIMARY KEY ('+
            part.c('ASSET_SHA256')+','+part.c('PART_NO')+'))')
        c.execute('CREATE TABLE '+release.table.split('.')[-1]+' ('+release.c('RELEASE_ID')+' VARCHAR2(100) PRIMARY KEY,'+
            release.c('MANIFEST_JSON')+' CLOB)')
    class Executor:
        def query_to_df(self,statement,**kwargs):
            with conn.cursor() as c:
                for text in kwargs.get('pre_queries',[]): c.execute(text.replace('SIDDS.',user+'.'))
                c.execute(statement.replace('SIDDS.',user+'.')); names=[x[0] for x in c.description]
                result=[[v.read() if hasattr(v,'read') else v for v in row] for row in c.fetchall()]
                for text in kwargs.get('post_queries',[]): c.execute(text)
            return pd.DataFrame(result,columns=names)
    client=DataikuClient(Executor(),'LOCAL_SYNTHETIC','LOCAL_TEST',schema_map=schema)
    sql=io.SQL(client,journal=tmp_path/'calls.jsonl',binding='test')
    raw=('한글😀'*6000).encode();item={'sha256':hashlib.sha256(raw).hexdigest()}
    deferred.put_staged_part(sql,item,0,raw)
    deferred.put_staged_part(sql,item,0,raw)
    assert assets.get_part(sql,item['sha256'],0)==raw
    with pytest.raises(io.DPError): deferred.put_staged_part(sql,item,0,b'wrong')
    assert assets.get_part(sql,item['sha256'],0)==raw
    value={'schema_version':q.SCHEMA,'status':'COMPLETE','source_release_id':'a'*64,
           'dataset_version':'b'*64,'tables':{'nav.source':{'rows':3}}}
    rid=io.digest(value)
    deferred.put_query_release(sql,rid,value)
    deferred.put_query_release(sql,rid,value)
    assert q.read_release(sql,rid)==value
    with conn.cursor() as c:
        c.execute('UPDATE '+release.table.replace('SIDDS.',user+'.')+' SET '+release.c('MANIFEST_JSON')+"='{}' WHERE "+release.c('RELEASE_ID')+'=:r',{'r':rid})
    conn.commit()
    with pytest.raises(io.DPError):deferred.put_query_release(sql,rid,value)
