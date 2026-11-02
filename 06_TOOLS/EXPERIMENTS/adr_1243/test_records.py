"""Local Oracle storage/consumer contracts, no external models or NFS."""
from pathlib import Path
from contextlib import contextmanager
import importlib.util
import json
import os
import sqlite3
import threading
import time
import uuid

import pytest
import oracledb

from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL,ACTIVE_LEASES
from semantic_runtime.oracle_dp_io import DPError,digest
from semantic_runtime import oracle_runtime_paths as paths,runtime_sqlite

ROOT=Path(__file__).resolve().parents[3]

class LocalOracle:
    SQL_PATH='/local-agent-contract'
    def __init__(self,db):
        self.db=db;self.lock=threading.RLock();self.errors=[];self.fail_after_operation=False;self.operation_writes=0
    def request(self,method,path,json):
        assert (method,path)==('POST',self.SQL_PATH)
        types={'CLOB':oracledb.DB_TYPE_CLOB,'VARCHAR2':oracledb.DB_TYPE_VARCHAR,'NUMBER':oracledb.DB_TYPE_NUMBER}
        with self.lock:
            try:
                with self.db.cursor() as c:
                    binds=json.get('binds',[])
                    c.setinputsizes(**{b['name']:types[b['data_type']] for b in binds})
                    c.execute(json['statementText'],{b['name']:b['value'] for b in binds})
                    if c.description is None:
                        if "VALUES(:scope,:owner,'OPERATION'" in json['statementText']:
                            self.operation_writes+=1
                            if self.fail_after_operation:
                                self.fail_after_operation=False;raise TimeoutError('synthetic lost acknowledgement after commit')
                        return {'items':[{'result':c.rowcount}]}
                    names=[d[0] for d in c.description];rows=c.fetchmany(json['limit']+1)
                    value=lambda v:v.read() if isinstance(v,oracledb.LOB) else v
                    return {'items':[{'resultSet':{'offset':0,'hasMore':len(rows)>json['limit'],
                        'items':[{k:value(v) for k,v in zip(names,r)} for r in rows[:json['limit']]]}}]}
            except oracledb.DatabaseError as exc:
                error=exc.args[0];self.errors.append({'code':error.code,'message':error.message})
                return {'items':[{'errorCode':error.code}]}

@pytest.fixture
def oracle_agent(monkeypatch):
    p=ROOT/'06_TOOLS/maintenance/agent_record_oracle_r2.py'
    sp=importlib.util.spec_from_file_location('agent_contract_admin',p);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
    db=a.connection();client=LocalOracle(db)
    sql=RecordSQL(client,binding='local-record-contract',deadline=time.monotonic()+600,max_calls=10000)
    store=AgentRecords(sql,namespace='contract-'+uuid.uuid4().hex)
    monkeypatch.setenv('DP','oracle');monkeypatch.setenv('GENOS_RUNTIME_DIR','/unmounted-oracle-runtime/'+uuid.uuid4().hex)
    for k in ('GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR'):monkeypatch.delenv(k,raising=False)
    with paths.using(store):
        try:yield store,client,paths.Path(os.environ['GENOS_RUNTIME_DIR'])
        finally:
            db.rollback()
            with db.cursor() as c:
                for name in ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A','LGL_AGT_BODY_A'):
                    c.execute('DELETE FROM SIDDA.'+name+' WHERE SCOPE_HASH_VAL=:scope',scope=store.scope)
            db.commit();db.close()

def test_no_mount_files_row_types_and_reconnect(oracle_agent,monkeypatch):
    store,client,root=oracle_agent
    assert store.preflight()['persistent_sqlite'] is False
    original=sqlite3.connect
    def memory_only(database,*args,**kwargs):
        assert str(database)==':memory:','Oracle record computation attempted a file-backed SQLite connection'
        return original(database,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',memory_only)
    root.mkdir(exist_ok=True);p=root/'journal.sqlite'
    conn=runtime_sqlite.connect(p,isolation_level=None)
    conn.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY,text TEXT,data BLOB);PRAGMA user_version=9;')
    conn.execute('BEGIN IMMEDIATE')
    conn.executemany('INSERT INTO t VALUES(?,?,?)',[(1,'',b'\x00\xff'),(2,None,None),(3,'한글🌱\r\n',b'')])
    conn.execute('COMMIT');conn.close()
    conn=runtime_sqlite.connect(p,isolation_level=None)
    assert conn.execute('SELECT * FROM t ORDER BY id').fetchall()==[(1,'',b'\x00\xff'),(2,None,None),(3,'한글🌱\r\n',b'')]
    conn.execute('BEGIN IMMEDIATE');conn.execute('DELETE FROM t');conn.rollback();conn.close()
    conn=runtime_sqlite.connect(p,isolation_level=None)
    assert conn.execute('SELECT count(*) FROM t').fetchone()[0]==3;conn.close()
    assert not Path(str(root)).exists(),'Test accidentally created its unmounted physical runtime'
    assert not client.errors

def test_immutable_body_parts_and_incomplete_manifest_rejected(oracle_agent):
    store,client,root=oracle_agent
    raw=('본문😀\n'*5000).encode();import hashlib
    h=hashlib.sha256(raw).hexdigest();store.put_bodies([raw]);assert store.body(h)==raw
    with client.db.cursor() as c:
        c.execute('DELETE FROM SIDDA.LGL_AGT_BODY_A WHERE SCOPE_HASH_VAL=:scope AND BODY_HASH_VAL=:hash AND PART_SEQ_NO=0',scope=store.scope,hash=h)
    client.db.commit()
    fresh=AgentRecords(store.sql,namespace='unused')
    fresh.scope=store.scope
    with pytest.raises(DPError,match='INCOMPLETE'):fresh.body(h)

def test_commit_acknowledgement_loss_reconciles_without_redispatch(oracle_agent):
    store,client,root=oracle_agent
    owner=digest('response-loss');client.fail_after_operation=True
    assert store.commit(owner,0,{'type':'technical','original':None},[])==1
    assert client.operation_writes==1
    assert store.state('a1:head:'+owner)['value']['original'] is None

def test_expired_or_replaced_fence_cannot_commit(oracle_agent):
    store,client,root=oracle_agent
    with store.lease(['owner','fence-contract']):
        cert=ACTIVE_LEASES.get()[-1];old=store.state(cert['key'])
        changed={**old['value'],'token':'different-owner'}
        revision=old['revision']+1
        h=digest({'scope_hash':store.scope,'key':cert['key'],'revision':revision,'value':changed})
        with client.db.cursor() as c:
            c.execute('UPDATE SIDDA.LGL_EXEC_ST_A SET CHG_SEQ_NO=:r,ST_HASH_VAL=:h,ST_JSON_CN=:v WHERE SCOPE_HASH_VAL=:s AND ST_KEY_ID=:k',
                      r=revision,h=h,v=json.dumps(changed,ensure_ascii=False,sort_keys=True,separators=(',',':')),s=store.scope,k=cert['key'])
        client.db.commit()
        owner=digest('stale-owner')
        with pytest.raises(DPError):store.commit(owner,0,{'type':'stale'},[])
        assert store.state('a1:head:'+owner) is None
    assert client.errors[-1]['code']==20043

def test_shared_generation_reader_and_exclusive_writer_conflict(oracle_agent):
    store,client,root=oracle_agent
    with store.shared_lease(['generation'],wait=0):
        assert len(ACTIVE_LEASES.get())==1
        with pytest.raises(BlockingIOError):
            with store.shared_lease(['generation'],exclusive=True,wait=0):pass
    assert ACTIVE_LEASES.get()==()
    with store.shared_lease(['generation'],exclusive=True,wait=0):
        with pytest.raises(BlockingIOError):
            with store.shared_lease(['generation'],wait=0):pass
    assert ACTIVE_LEASES.get()==()

def test_v3_v4_original_artifact_and_history_survive_reopen(oracle_agent):
    store,client,root=oracle_agent
    from semantic_runtime.legal_agent.case_repository import CaseRepository
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    case=CaseRepository(root/'cases-v3.sqlite',None,None)
    with case.transaction():case.identity('s',{'user_id':'u','team_id':'t'})
    case.close();case=CaseRepository(root/'cases-v3.sqlite',None,None)
    assert case.db.execute('SELECT owner,team FROM session WHERE id=?',('s',)).fetchone()[0]=='u';case.close()
    repo=ShortcutRepository(root/'cases-v4.sqlite')
    principal={'user_id':'u','team_id':'t','authenticated':True,'document_ids':['d']}
    raw=b'original\x00binary'
    with repo.transaction():ident=repo.artifact(raw,principal,documents=['d'])
    repo.close();repo=ShortcutRepository(root/'cases-v4.sqlite')
    assert repo.read_artifact(ident,principal)==raw
    with pytest.raises(Exception):repo.read_artifact(ident,{**principal,'user_id':'other'})
    repo.close();assert not client.errors

def test_source_database_mirrors_are_rejected(oracle_agent):
    _,_,root=oracle_agent
    with pytest.raises(DPError,match='SOURCE_MIRROR_FORBIDDEN'):runtime_sqlite.connect(root/'store.sqlite')


def test_original_history_migration_preserves_bytes_rows_and_is_idempotent(oracle_agent,tmp_path):
    from semantic_runtime.oracle_records_migration import migrate_tree,inventory
    store,client,root=oracle_agent
    source=tmp_path/'original-runtime';source.mkdir()
    p=source/'past'/'journal.sqlite';p.parent.mkdir()
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE old_event(id INTEGER PRIMARY KEY AUTOINCREMENT,raw TEXT,blob BLOB)')
        db.executemany('INSERT INTO old_event VALUES(?,?,?)',[(5,'',b'\x00\xff'),(9,None,None),(12,'한글\r\n',b'')])
        db.execute('PRAGMA user_version=7')
    (source/'original.json').write_bytes(b'{"raw":"original"}\r\n')
    (source/'owner.lock').write_bytes(b'control preserved')
    before=inventory(source)
    with pytest.raises(DPError,match='QUIESCE'):migrate_tree(source,root,store=store)
    receipt=migrate_tree(source,root,store=store,quiesced=True)
    assert receipt['status']=='COMPLETE' and inventory(source)==before
    assert (root/'original.json').read_bytes()==(source/'original.json').read_bytes()
    db=runtime_sqlite.connect(root/'past/journal.sqlite',isolation_level=None)
    assert db.execute('SELECT * FROM old_event ORDER BY id').fetchall()==[(5,'',b'\x00\xff'),(9,None,None),(12,'한글\r\n',b'')]
    assert db.execute('PRAGMA user_version').fetchone()[0]==7
    assert db.execute('INSERT INTO old_event(raw) VALUES(?)',('next',)).lastrowid==13
    db.close()
    assert migrate_tree(source,root,store=store,quiesced=True)['status']=='ALREADY_IMPORTED'
    assert inventory(source)==before and not Path(str(root)).exists()
    assert not client.errors


def test_interrupted_import_cannot_be_opened_and_resumes_same_original(oracle_agent,tmp_path,monkeypatch):
    from semantic_runtime.oracle_records_migration import migrate_tree,inventory
    store,client,root=oracle_agent
    source=tmp_path/'original-runtime';source.mkdir()
    with sqlite3.connect(source/'journal.sqlite') as db:
        db.execute('CREATE TABLE event(id INTEGER PRIMARY KEY,value TEXT)')
        db.executemany('INSERT INTO event VALUES(?,?)',[(i,str(i)) for i in range(201)])
    before=inventory(source);commit=store.commit
    def interrupt(owner,expected,value,changes,**kwargs):
        if value.get('type')=='sqlite' and value.get('migration',{}).get('rows',0)>=200:
            raise TimeoutError('synthetic stopped transfer before the second batch')
        return commit(owner,expected,value,changes,**kwargs)
    monkeypatch.setattr(store,'commit',interrupt)
    with pytest.raises(TimeoutError):migrate_tree(source,root,store=store,quiesced=True)
    marker=digest({'migration_root':str(root)})
    assert store.state('a1:head:'+marker)['value']['status']=='IN_PROGRESS'
    with pytest.raises(DPError,match='INCOMPLETE'):runtime_sqlite.connect(root/'journal.sqlite')
    monkeypatch.setattr(store,'commit',commit)
    assert migrate_tree(source,root,store=store,quiesced=True)['status']=='COMPLETE'
    db=runtime_sqlite.connect(root/'journal.sqlite');assert db.execute('SELECT count(*) FROM event').fetchone()[0]==201;db.close()
    assert inventory(source)==before and not client.errors


def test_writers_refresh_a_stale_connection_and_keep_both_changes(oracle_agent):
    _,client,root=oracle_agent
    a=runtime_sqlite.connect(root/'shared.sqlite',isolation_level=None)
    a.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT)');a.commit()
    b=runtime_sqlite.connect(root/'shared.sqlite',isolation_level=None)
    a.execute('INSERT INTO t VALUES(1,?)',('first',))
    b.execute('BEGIN IMMEDIATE');b.execute('INSERT INTO t VALUES(2,?)',('second',));b.commit()
    a.close();b.close()
    db=runtime_sqlite.connect(root/'shared.sqlite');assert db.execute('SELECT * FROM t ORDER BY id').fetchall()==[(1,'first'),(2,'second')];db.close()
    assert not client.errors


def test_replace_unique_key_removes_the_previous_rowid_durably(oracle_agent):
    _,client,root=oracle_agent
    p=root/'replace.sqlite';db=runtime_sqlite.connect(p,isolation_level=None)
    db.execute('CREATE TABLE t(value TEXT UNIQUE,payload TEXT)')
    db.execute('INSERT INTO t VALUES(?,?)',('key','before'))
    db.execute('INSERT OR REPLACE INTO t VALUES(?,?)',('key','after'));db.close()
    db=runtime_sqlite.connect(p);assert db.execute('SELECT rowid,* FROM t').fetchall()==[(2,'key','after')];db.close()
    assert not client.errors


def test_administration_reports_trace_and_workflow_ownership_use_oracle(oracle_agent):
    _,client,root=oracle_agent
    from semantic_runtime.ad_store import Store
    from semantic_runtime.request_summary import write_row,atomic_file,summary_lock
    from semantic_runtime.process_trace import ProcessTrace
    from workflow.repository import execution_lock
    ad=Store(root/'ad/state.sqlite')
    with ad.transaction():session=ad.session('w','web','s')
    ad.close();ad=Store(root/'ad/state.sqlite')
    assert ad.db.execute('SELECT workspace FROM ad_session WHERE id=?',(session['id'],)).fetchone()[0]=='w';ad.close()
    directory=root/'reports';directory.mkdir(parents=True)
    row=write_row(directory,'r1',{'question':'원래 질문','status':'failed'})
    assert json.loads(row.read_text())['question']=='원래 질문'
    with summary_lock(directory):
        with atomic_file(directory/'summary.txt','w',encoding='utf-8') as stream:stream.write('기록')
    assert (directory/'summary.txt').read_text()=='기록'
    trace=ProcessTrace(directory/'trace.txt','request-1');trace.block('failed',{'original':'원문'})
    trace.stream.close();assert '원문' in (directory/'trace.txt').read_text()
    with execution_lock(root/'workflows','a'*32):
        with pytest.raises(Exception,match='같은 실행'):
            with execution_lock(root/'workflows','a'*32):pass
    assert not Path(str(root)).exists() and not client.errors


def test_runtime_default_is_oracle_without_an_additional_environment_variable(monkeypatch):
    monkeypatch.setenv('DP','oracle');monkeypatch.delenv('GENOS_RUNTIME_DIR',raising=False)
    assert hasattr(paths,'runtime_directory'),'MAIN126 lacks the common service/chat default resolver'
    assert str(paths.runtime_directory('/legacy/service/runtime'))=='/__oracle_agent__/runtime'
    monkeypatch.setenv('GENOS_RUNTIME_DIR','/existing/nfs/runtime')
    assert str(paths.runtime_directory('/legacy/service/runtime'))=='/existing/nfs/runtime'
    assert paths.virtual(paths.runtime_directory('/legacy/service/runtime'))


def test_runtime_default_nfs_behavior_is_preserved(monkeypatch):
    monkeypatch.delenv('DP',raising=False);monkeypatch.delenv('GENOS_RUNTIME_DIR',raising=False)
    assert hasattr(paths,'runtime_directory'),'MAIN126 lacks the common service/chat default resolver'
    assert str(paths.runtime_directory('/legacy/service/runtime'))=='/legacy/service/runtime'
    monkeypatch.setenv('GENOS_RUNTIME_DIR','/existing/nfs/runtime')
    assert str(paths.runtime_directory('/legacy/service/runtime'))=='/existing/nfs/runtime'
    assert not paths.virtual(paths.runtime_directory('/legacy/service/runtime'))
