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
TEMP=tempfile.TemporaryDirectory(prefix='nfs-r5-contract-')
CODE=Path(TEMP.name)
with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R5.zip') as z: z.extractall(CODE)
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


def expected_rows(count=20):
    return [dict(DATASET_VERSION='a'*64,DOCUMENT_ID="doc'한글",BLOCK_ID=f'{i:04}',UNIT_ID='0001',
                 TEXT=("가"*999+"😀'\r\n ")*8,SOURCE_ARTIFACT_SHA256='b'*64,
                 SOURCE_JSON=' { "공백": "'+('나😀'*2500)+'" } ',JSON_TEXT_ELIDED=1) for i in range(count)]


class BulkOracle(Oracle):
    source_clob_batch_size=32
    source_native_clob=True
    source_verify_batch_rows=100
    def __init__(self):
        super().__init__();self.physical=[];self.fault=None
    def request(self,method,path,json):
        self.physical.append(copy.deepcopy(json))
        text=json['statementText']
        if 'CASE WHEN DBMS_LOB.GETLENGTH' in text:
            if self.fault=='unavailable': raise RuntimeError('full CLOB unsupported')
            kind=next(k for k,t in io.TABLES.items() if ('FROM SIDDA.'+t) in text)
            binds={b['name']:b['value'] for b in json.get('binds',[])}
            indices={int(n.split('_')[0][1:]) for n in binds if n.startswith('k')}
            wanted={tuple(binds[f'k{i}_{j}'] for j in range(len(io.KEYS[kind]))) for i in indices}
            result=[]
            for key,row in self.data[kind].items():
                if key not in wanted: continue
                value=dict(row)
                for c in io.CLOBS.intersection(io.COLUMNS[kind]):
                    value[c+'__TOTAL']=None if row[c] is None else io.units(row[c])
                result.append(value)
            if result:
                if self.fault=='truncate': result[0]['TEXT']=result[0]['TEXT'][:50]
                if self.fault=='same_length': result[0]['TEXT']='X'+result[0]['TEXT'][1:]
                if self.fault=='wrong_key': result[0]['BLOCK_ID']='unexpected'
                if self.fault=='duplicate': result[-1]=dict(result[0])
                if self.fault=='missing': result.pop()
                if self.fault=='metadata': result[0]['TEXT__TOTAL']=-1
            return {'items':[{'resultSet':{'items':list(reversed(result)),'hasMore':False,'offset':0}}]}
        if ' AS CLOB_SLOT' in text:
            return batch_response(super().request,method,path,json)
        return super().request(method,path,json)


def backend(rows):
    client=BulkOracle()
    client.data['block_payload']={tuple(r[k] for k in io.KEYS['block_payload']):dict(r) for r in rows}
    return client


def sql(client,path):
    return io.SQL(client,journal=path/'calls.jsonl',binding='same-fixture')


def test_exact_package_and_pins():
    assert Path(io.__file__).is_relative_to(CODE)
    assert Path(migration.__file__).is_relative_to(CODE)
    for n,h in json.loads((CODE/'PACKAGE_FILES.json').read_text()).items():
        assert io.file_sha(CODE/n)==h
    for n,h in json.loads((CODE/'client/CODE_PINS.json').read_text())['files'].items():
        assert io.file_sha(CODE/'client'/n)==h
    with zipfile.ZipFile(HERE.with_name('existing_nfs_continuous_20261030_r4')/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R4.zip') as z:
        changed=[n for n in z.namelist() if z.read(n)!=(CODE/n).read_bytes()]
    assert len(changed)==6


def test_direct_payload_cap_uses_original_piece_reader(tmp_path,monkeypatch):
    from semantic_runtime import oracle_dp_native_read as native
    rows=expected_rows(3);client=backend(rows)
    monkeypatch.setattr(native,'MAX_RESULT_BYTES',1)
    observed=io.read_batch(sql(client,tmp_path),'block_payload',rows)
    io.compare_batch('block_payload',rows,observed)
    assert not any('CASE WHEN DBMS_LOB.GETLENGTH' in x['statementText'] for x in client.physical)


def test_target_oversize_rejected_without_truncated_acceptance(tmp_path):
    rows=expected_rows(2);client=backend(rows)
    next(iter(client.data['block_payload'].values()))['TEXT']+='longer than the frozen input'
    with pytest.raises(io.DPError,match='ROW_CONFLICT'):
        io.read_batch(sql(client,tmp_path),'block_payload',rows)


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


def test_direct_and_original_piece_read_exact_same_content(tmp_path):
    rows=expected_rows();client=backend(rows)
    old=sql(client,tmp_path/'pieces');client.source_native_clob=False
    baseline=io.read_batch(old,'block_payload',rows)
    client.source_native_clob=True;new=sql(client,tmp_path/'native')
    candidate=io.read_batch(new,'block_payload',rows)
    io.compare_batch('block_payload',baseline,candidate)
    assert new.calls==1 and old.calls>1
    (HERE/'SYNTHETIC_SQL_COUNTS.json').write_text(json.dumps({'rows':20,'R4_piece_calls':old.calls,'R5_native_calls':new.calls,'bytes_equal':True},indent=2)+'\n')


@pytest.mark.parametrize('fault',['truncate','unavailable'])
def test_driver_failure_disables_full_read_and_preserves_contents(tmp_path,fault):
    rows=expected_rows(3);client=backend(rows);client.fault=fault;s=sql(client,tmp_path)
    result=io.read_batch(s,'block_payload',rows)
    io.compare_batch('block_payload',rows,result)
    assert client.source_native_clob_disabled
    n=sum('CASE WHEN DBMS_LOB.GETLENGTH' in x['statementText'] for x in client.physical)
    io.read_batch(s,'block_payload',rows)
    assert sum('CASE WHEN DBMS_LOB.GETLENGTH' in x['statementText'] for x in client.physical)==n==1
    assert 'SOURCE_NATIVE_CLOB_FALLBACK' in s.journal.read_text()


@pytest.mark.parametrize('fault',['same_length','wrong_key','duplicate','missing','metadata'])
def test_corruption_and_missing_rejected(tmp_path,fault):
    rows=expected_rows(3);client=backend(rows);client.fault=fault
    with pytest.raises(io.DPError):
        observed=io.read_batch(sql(client,tmp_path),'block_payload',rows)
        io.compare_batch('block_payload',rows,observed)


def test_verify_large_batch_same_chain_and_detects_later_mutation(tmp_path):
    source=fixture_source(tmp_path/'source',n=205);client=BulkOracle()
    # source write still uses <=20 rows; fixture has a long first block.
    first=migration.transfer(client,source,target_binding='test',directory=tmp_path/'log',action='run')
    assert first['status']=='SOURCE_COMPLETE'
    original=json.loads(Path(first['receipt']).read_text())
    client.source_native_clob=False;client.source_verify_batch_rows=20
    before=len(client.physical)
    baseline=migration.transfer(client,source,target_binding='test',directory=tmp_path/'log',action='verify')
    old_calls=len(client.physical)-before
    client.source_native_clob=True;client.source_verify_batch_rows=100
    before=len(client.physical)
    new=migration.transfer(client,source,target_binding='test',directory=tmp_path/'log',action='verify')
    new_calls=len(client.physical)-before
    assert old_calls>new_calls and baseline['status']==new['status']=='VERIFIED'
    state=json.loads(Path(first['receipt']).read_text())
    assert state['tables']==original['tables'] and state['deadline']==original['deadline']
    assert all(x['statementText'].count('THEN INSERT INTO')<=20 for x in client.physical if x['statementText'].startswith('DECLARE'))
    # Earlier verify result does not authorize skipping a now-changed first row.
    next(iter(client.data['block_payload'].values()))['TEXT']='changed'
    with pytest.raises(io.DPError,match='ROW_CONFLICT'):
        migration.transfer(client,source,target_binding='test',directory=tmp_path/'log',action='verify')
    (HERE/'VERIFY_SQL_COUNTS.json').write_text(json.dumps({'block_rows':205,'R4_equivalent_calls':old_calls,'R5_calls':new_calls,'chain_equal':True,'later_mutation_rejected':True},indent=2)+'\n')


@pytest.mark.parametrize('origin',['r23','r4','r23_via_r4'])
def test_upgrade_preserves_state_and_history(tmp_path,origin):
    r23='36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'
    r4='6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0'
    identity={'target':'DB','data':'DATA','generation':'PATH','code':r4 if origin=='r4' else r23}
    expected=dict(identity,code=io.file_sha(full.__file__))
    state={'identity':identity,'deadline':12345,'status':'PAUSED','stages':{'source':{'rows':100}},'pending':{'rows':4}}
    if origin=='r23_via_r4':
        state['compatible_executor']={'origin_code_sha256':r23,'execution_code_sha256':r4,'policy':'existing-nfs-r4-remove-invocation-cap-v1'}
    io.atomic_json(tmp_path/'full-state.json',state);before=copy.deepcopy(state);raw=(tmp_path/'full-state.json').read_bytes()
    assert full._import_identity(state,expected,tmp_path)==identity
    for k,v in before.items():
        if k!='compatible_executor': assert state[k]==v
    record=state['compatible_executor']
    assert (tmp_path/record['prior_receipt_file']).read_bytes()==raw
    if origin=='r23_via_r4':assert state['compatible_executor_history']==[before['compatible_executor']]
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


def test_actual_mapped_oracle_full_clob_and_piece_equivalence(actual_oracle,tmp_path):
    import pandas as pd
    conn,schema,user,rows=actual_oracle
    class Executor:
        def query_to_df(self,statement,**kwargs):
            statement=statement.replace('SIDDS.',user+'.')
            with conn.cursor() as c:
                c.execute(statement);names=[x[0] for x in c.description]
                result=[[v.read() if hasattr(v,'read') else v for v in row] for row in c.fetchall()]
            return pd.DataFrame(result,columns=names)
    client=DataikuClient(Executor(),'LOCAL_SYNTHETIC','LOCAL_TEST',schema_map=schema)
    client.source_clob_batch_size=32;client.source_native_clob=False
    baseline=sql(client,tmp_path/'old');old=io.read_batch(baseline,'block_payload',rows)
    client.source_native_clob=True
    new=sql(client,tmp_path/'new');result=io.read_batch(new,'block_payload',rows)
    io.compare_batch('block_payload',rows,old);io.compare_batch('block_payload',old,result)
    assert new.calls==1 and baseline.calls>new.calls
    indexed={r['BLOCK_ID']:r for r in result}
    assert indexed['0000']['TEXT'] is None and indexed['0001']['TEXT']==''
    (HERE/'ORACLE_SQL_COUNTS.json').write_text(json.dumps({'rows':20,'R4_piece_calls':baseline.calls,'R5_native_calls':new.calls,'byte_equal':True,'model_calls':0,'driver':'oracledb behind fake SQLExecutor2; field JDBC untested'},indent=2)+'\n')
