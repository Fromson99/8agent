"""Bounded synthetic integration: real projection/SQL renderer; no field Oracle."""
import copy
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import pandas as pd
import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from lawrag.pipeline import oracle_clean_import as clean, oracle_import_stop as stop
from lawrag.pipeline import oracle_query_dataiku as bridge
from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q


class Database:
    """Execute fixed loader statements against exact in-memory rows, atomic commits."""
    SQL_PATH = '/sql'
    def __init__(self, delegate):
        self.delegate = delegate
        self.rows = {t: [] for t in (*clean.TABLES,q.ACTIVE,q.STATE)}
        self.statements = []
        self.fail = None
        self.fail_phase = None
        self.extra_trigger = False
        self.outside = False
        self.after_commit = None

    def request(self, method, path, json):
        sql = json['statementText']; self.statements.append(sql)
        binds = {b['name']: b['value'] for b in json.get('binds', [])}
        def result(rows):
            return {'items':[{'resultSet':{'items':rows,'hasMore':False,'offset':0}}]}
        if sql.startswith('SELECT CHANNEL,RELEASE_ID,REVISION FROM '): return result(self.rows[q.ACTIVE])
        if 'ALL_TRIGGERS' in sql: return result([{'TRIGGER_NAME':'OTHER'}] if self.extra_trigger else [])
        if 'c.R_OWNER' in sql: return result([{'OWNER':'OTHER','TABLE_NAME':'SHARED'}] if self.outside else [])
        if 'c.TABLE_NAME=:table_name' in sql:
            cols = ('ASSET_SHA256','PART_NO') if binds['table_name']==assets.PART_TABLE.split('.')[1] else ('RELEASE_ID',)
            return result([{'COLUMN_NAME':c,'POSITION':i,'STATUS':'ENABLED','VALIDATED':'VALIDATED'} for i,c in enumerate(cols,1)])
        if 'ALL_' in sql or 'WHERE 1=0' in sql:
            return self.delegate.request('POST','/sql',json)
        if sql.startswith(('BEGIN ', 'DECLARE ')):
            candidate = copy.deepcopy(self.rows)
            if 'DELETE FROM' in sql:
                if self.rows[q.ACTIVE]: raise RuntimeError('ORA-20062')
                assert all(f'LOCK TABLE {t} IN EXCLUSIVE MODE NOWAIT;' in sql for t in clean.TABLES)
                if self.fail=='reset_busy':
                    self.fail=None
                    raise io.DPError('JDBC_FAILURE: ORA-00054')
                for table in re.findall(r'DELETE FROM ([A-Z0-9_.]+);', sql):
                    candidate[table] = []
                if self.fail == 'reset_before':
                    self.fail = None; raise RuntimeError('reset failed before commit')
            if 'INSERT INTO' in sql:
                for table, cols, vals in re.findall(r'INSERT INTO ([A-Z0-9_.]+) \(([^)]+)\) VALUES \((.*?)\);', sql):
                    expressions = vals.split(',')
                    value = lambda x: binds[x[1:]] if x.startswith(':') else '' if x=='EMPTY_CLOB()' else None if x=='NULL' else 1/0
                    row = dict(zip(cols.split(','),map(value,expressions)))
                    keys = self.keys(table)
                    if any(all(old[k]==row[k] for k in keys) for old in candidate[table]):
                        raise RuntimeError('ORA-00001')
                    candidate[table].append(row)
                if self.fail == 'insert_before' and (self.fail_phase is None or self.fail_phase in sql):
                    self.fail = None; raise RuntimeError('insert before commit')
            if 'CLEAN_RECOVERY_CONFLICT' in sql:
                for table, condition in re.findall(r'SELECT COUNT\(\*\) INTO n FROM ([A-Z0-9_.]+) WHERE (.*?);',sql):
                    prefix = re.search(r':(r\d+)_',condition).group(1)
                    columns = self.columns(table)
                    expected={}
                    for j,col in enumerate(columns):
                        name=f'{prefix}_{j}'
                        expected[col]=binds[name] if name in binds else None if f'{col} IS NULL' in condition else ''
                    if sum(r==expected for r in candidate[table]) != 1:
                        raise RuntimeError('ORA-20061')
            self.rows = candidate
            if self.fail == 'reset_after' and 'DELETE FROM' in sql:
                self.fail = None; raise RuntimeError('reset committed, ACK lost')
            if self.fail == 'insert_after' and 'INSERT INTO' in sql and (self.fail_phase is None or self.fail_phase in sql):
                self.fail = None; raise RuntimeError('insert committed, ACK lost')
            if self.after_commit and 'INSERT INTO' in sql:
                callback=self.after_commit; self.after_commit=None; callback()
            return {'items':[{'result':0}]}
        if 'AS TABLE_NAME,COUNT(*)' in sql:
            return result([{'TABLE_NAME':t,'N':len(self.rows[t])} for t in clean.TABLES])
        if ' AS I,COUNT(*) AS N' in sql:
            output=[]
            for idx,table,condition in re.findall(r'SELECT (\d+) AS I,COUNT\(\*\) AS N FROM ([A-Z0-9_.]+) WHERE (.*?)(?= UNION ALL |$)',sql):
                pairs=re.findall(r'(\w+)=:(\w+)',condition)
                output.append({'I':int(idx),'N':sum(all(r[c]==binds[n] for c,n in pairs) for r in self.rows[table])})
            return result(output)
        if 'GROUP BY KIND' in sql:
            from collections import Counter
            return result([{'KIND':k,'N':n} for k,n in Counter(r['KIND'] for r in self.rows[q.ROW]).items()])
        match=re.search(r'SELECT TO_CLOB\((\w+)\) AS VALUE, DBMS_LOB.GETLENGTH\(\w+\) AS N FROM ([A-Z0-9_.]+) WHERE (.*)',sql)
        if match:
            col,table,where=match.groups()
            key,param=re.search(r'(\w+)=:(\w+)',where).groups()
            return result([{'VALUE':r[col],'N':io.units(r[col])} for r in self.rows[table] if r[key]==binds[param]])
        raise AssertionError('Unmodeled SQL: '+sql[:160])

    def keys(self,t):
        if t in ('SIDDA.'+n for n in io.TABLES.values()):
            return io.KEYS[next(k for k,v in io.TABLES.items() if 'SIDDA.'+v==t)]
        return clean.PART_COLS[:2] if t==assets.PART_TABLE else clean.QUERY_COLS[:3] if t==q.ROW else ('RELEASE_ID',)

    def columns(self,t):
        if t in ('SIDDA.'+n for n in io.TABLES.values()):
            return io.COLUMNS[next(k for k,v in io.TABLES.items() if 'SIDDA.'+v==t)]
        return clean.PART_COLS if t==assets.PART_TABLE else clean.QUERY_COLS if t==q.ROW else (
            ('RELEASE_ID','DATASET_VERSION','RELEASE_JSON') if t==assets.RELEASE_TABLE else ('RELEASE_ID','MANIFEST_JSON'))


@pytest.fixture
def setup(full,tmp_path):
    work=tmp_path/'work'; work.mkdir()
    (full[4]).rename(work/'restored')
    (work/'oracle-import-r3').mkdir()
    (work/'oracle-import-r3/job.lock').touch()
    io.atomic_json(work/'oracle-import-r3/full-state.json',{'identity':{'target':'fixture'},'status':'INTERRUPTED'})
    return Database(full[0]), work


def run(setup,action='plan',**kwargs):
    return clean.run(setup[0],setup[1],target_binding='fixture',action=action,**kwargs)


def test_plan_reset_insert_counts_manifests_and_duplicate_run(setup):
    db,work=setup
    for t in clean.TABLES: db.rows[t]=[{'old':'development'}]
    db.rows[q.STATE]=[{'SCOPE_HASH':'x','STATE_KEY':'keep','REVISION':3,'VALUE_JSON':'saved'}]
    before=copy.deepcopy(db.rows)
    plan=run(setup)
    assert plan['status']=='CLEAN_PLAN_READY' and db.rows==before
    result=run(setup,'replace')
    assert result['status']=='CLEAN_LOAD_COUNTS_CONFIRMED' and not result['full_body_readback']
    assert {t:len(db.rows[t]) for t in clean.TABLES}==plan['after_counts']
    assert db.rows[q.ACTIVE]==[] and db.rows[q.STATE]==before[q.STATE]
    assert all('DELETE FROM '+t not in s and 'INSERT INTO '+t not in s and 'UPDATE '+t not in s for t in (q.ACTIVE,q.STATE) for s in db.statements)
    assert not any(' AS PIECE' in s or 'CLEAN_RECOVERY_CONFLICT' in s for s in db.statements)
    assert not any('SELECT COUNT(*) INTO n' in s for s in db.statements if 'INSERT INTO' in s)
    writes=sum(s.startswith(('BEGIN ','DECLARE ')) for s in db.statements)
    assert run(setup,'replace')==result  # Never DELETE or INSERT again.
    assert writes==sum(s.startswith(('BEGIN ','DECLARE ')) for s in db.statements)
    assert run(setup,'status')['result']==result
    assert sum('DELETE FROM' in s for s in db.statements)==1


@pytest.mark.parametrize('phase',[None,assets.PART_TABLE,q.ROW,q.RELEASE])
@pytest.mark.parametrize('failure',['insert_before','insert_after'])
def test_uncertain_batch_resume_without_duplicates(setup,phase,failure):
    db,work=setup; run(setup)
    db.fail=failure; db.fail_phase=phase
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):run(setup,'replace')
    path=work/'oracle-clean-r1/state.json'; failed=json.loads(path.read_text())
    assert failed['pending']
    result=run(setup,'resume')
    state=json.loads(path.read_text())
    assert state['deadline']==failed['deadline'] and state['pending'] is None
    assert result['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'
    for t,rows in db.rows.items():
        if rows: assert len(rows)==len({tuple(r[k] for k in db.keys(t)) for r in rows})
    assert sum('DELETE FROM' in s for s in db.statements)==1
    assert any('CLEAN_RECOVERY_CONFLICT' in s for s in db.statements)==(failure=='insert_after')


@pytest.mark.parametrize('failure',['reset_before','reset_after'])
def test_reset_transaction_uncertain_reconciliation(setup,failure):
    db,work=setup
    for t in clean.TABLES: db.rows[t]=[{'old':'data'}]
    run(setup);db.fail=failure
    with pytest.raises(io.DPError):run(setup,'replace')
    if failure=='reset_before': assert all(db.rows[t] for t in clean.TABLES)
    else: assert not any(db.rows[t] for t in clean.TABLES)
    with pytest.raises(io.DPError,match='CLEAN_RESET_UNCONFIRMED'):run(setup,'replace')
    assert sum('DELETE FROM' in s for s in db.statements)==1


@pytest.mark.parametrize('defect',['trigger','external_fk','changed_count','wrong_target','mutated_source','expired','old_write'])
def test_failures_prevent_destructive_reset(setup,defect):
    db,work=setup;run(setup)
    if defect=='trigger':db.extra_trigger=True
    if defect=='external_fk':db.outside=True
    if defect=='changed_count':db.rows[q.ROW].append({'new':'data'})
    if defect=='wrong_target':io.atomic_json(work/'oracle-import-r3/full-state.json',{'identity':{'target':'other'}})
    if defect=='mutated_source':
        with (work/'restored/generation/store.sqlite').open('ab') as f:f.write(b'x')
    if defect=='expired':
        p=work/'oracle-clean-r1/state.json';s=json.loads(p.read_text());s['deadline']=1;io.atomic_json(p,s)
    if defect=='old_write':
        (work/'oracle-import-r3/calls.jsonl').write_text(json.dumps({'status':'STARTED','write':True,'call':1})+'\\n'.replace('\\n','\n'))
    with pytest.raises(io.DPError):run(setup,'replace')
    assert not any('DELETE FROM' in s for s in db.statements)


def test_read_failure_after_commit_does_not_advance_pending(setup):
    db,work=setup;run(setup)
    db.fail='insert_after'
    with pytest.raises(io.DPError):run(setup,'replace')
    table='SIDDA.LEGAL_SRC_DOCUMENT_A';db.rows[table][0]['NAME']='changed'
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):run(setup,'resume')
    assert json.loads((work/'oracle-clean-r1/state.json').read_text())['pending']


def test_reset_lock_rejection_is_retryable_without_repeat_delete(setup):
    db,work=setup;run(setup);db.fail='reset_busy'
    with pytest.raises(io.DPError,match='ORA-00054'):run(setup,'replace')
    state=json.loads((work/'oracle-clean-r1/state.json').read_text())
    assert state['reset_pending'] is False and not any(db.rows.values())
    assert run(setup,'replace')['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'


def test_real_dataiku_adapter_and_renderer_boundary(setup,monkeypatch):
    db,work=setup; captured={}
    original=bridge.render
    def render(text,binds,**kw):
        captured.update(statementText=text,binds=[{'name':n,'value':v,'data_type':k} for n,v,k in binds])
        return original(text,binds,**kw)
    monkeypatch.setattr(bridge,'render',render)
    class Executor:
        def query_to_df(self,text,**kw):
            result=db.request('POST','/sql',{**captured,'limit':1000})
            if kw.get('pre_queries'):
                assert kw['post_queries']==['COMMIT']
                assert all(len(m.group(1).replace("''","'").encode())<=4000 for m in re.finditer(r"'((?:''|[^'])*)'",kw['pre_queries'][0]))
                return pd.DataFrame([{'OK':1}])
            assert kw.get('infer_from_schema') is True and kw['parse_dates'] is False
            return pd.DataFrame(result['items'][0]['resultSet']['items'])
    client=bridge.DataikuClient(Executor(),'AIDP','LEGAL_RAG')
    args=(client,work)
    clean.run(*args,target_binding='fixture',action='plan')
    result=clean.run(*args,target_binding='fixture',action='replace')
    assert result['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'


def test_bounded_batches_and_plain_sql_call_reduction():
    rows=[{'A':str(i),'B':"한글😀'\r\n"*300} for i in range(1000)]
    chunks=list(clean.batches(iter(rows)))
    assert all(len(b)<=100 for b in chunks)
    assert sum(map(len,chunks))==1000
    calls=0
    for batch in chunks:
        statement,binds=clean.insert_sql(q.RELEASE,('A','B'),('VARCHAR2','CLOB'),batch)
        assert 'SELECT ' not in statement and statement.count('INSERT INTO')==len(batch)
        rendered=bridge.render(statement,binds,write=True)
        assert 'DBMS_LOB.CREATETEMPORARY' in rendered
        calls+=1
    assert calls<=20  # Former 20-row base reads plus per-row/per-CLOB continuation calls.


def test_active_pointer_blocks_reset_and_is_never_modified(setup):
    db,work=setup
    active={'CHANNEL':'dev','RELEASE_ID':'a'*64,'REVISION':9}
    db.rows[q.ACTIVE]=[active]
    db.rows[q.RELEASE]=[{'RELEASE_ID':'a'*64,'MANIFEST_JSON':'old'}]
    db.rows[q.STATE]=[{'key':'saved'}]
    before=copy.deepcopy(db.rows)
    result=run(setup)
    assert result['status']=='ACTIVE_IN_USE_NO_CHANGES' and result['active']==[active]
    with pytest.raises(io.DPError,match='CLEAN_ACTIVE_IN_USE'):run(setup,'replace')
    assert db.rows==before and not any('DELETE FROM' in s for s in db.statements)


def test_active_created_after_plan_prevents_reset(setup):
    db,work=setup;run(setup)
    db.rows[q.ACTIVE]=[{'CHANNEL':'dev','RELEASE_ID':'a'*64,'REVISION':1}]
    with pytest.raises(io.DPError,match='CLEAN_ACTIVE_IN_USE'):run(setup,'replace')
    assert not any('DELETE FROM' in s for s in db.statements)


def test_control_tables_rejected_by_writer():
    for table in (q.ACTIVE,q.STATE,'OTHER.BUSINESS'):
        with pytest.raises(io.DPError,match='CLEAN_WRITE_SCOPE'):
            clean.insert_sql(table,('ID',),('VARCHAR2',),[{'ID':'x'}])


def test_keyboard_interrupt_after_commit_preserves_recovery(setup):
    db,work=setup;run(setup)
    def interrupt(): raise KeyboardInterrupt()
    db.after_commit=interrupt
    with pytest.raises(KeyboardInterrupt):run(setup,'replace')
    state=json.loads((work/'oracle-clean-r1/state.json').read_text())
    assert state['status']=='INTERRUPTED' and state['pending']
    result=run(setup,'resume')
    assert result['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'
    assert sum('DELETE FROM' in s for s in db.statements)==1


def test_partial_or_changed_pending_batch_never_overwritten(setup):
    db,work=setup;run(setup);db.fail='insert_after';db.fail_phase=q.ROW
    with pytest.raises(io.DPError):run(setup,'replace')
    assert len(db.rows[q.ROW])>1
    db.rows[q.ROW].pop()
    with pytest.raises(io.DPError,match='CLEAN_PARTIAL_BATCH'):run(setup,'resume')


def test_numeric_looking_ids_empty_clob_and_null_render_losslessly():
    columns=('RELEASE_ID','MANIFEST_JSON')
    for value in ['0007','1e3','0','123456789012345678901234567890']:
        sql,binds=clean.insert_sql(q.RELEASE,columns,['VARCHAR2','CLOB'],[dict(zip(columns,[value,None]))])
        rendered=bridge.render(sql,binds,write=True)
        assert "'"+value+"'" in rendered and ',NULL)' in rendered
    sql,binds=clean.insert_sql(q.RELEASE,columns,['VARCHAR2','CLOB'],[dict(zip(columns,['x','']))])
    assert 'EMPTY_CLOB()' in bridge.render(sql,binds,write=True)


def test_new_clean_job_lock_is_visible_to_stop_inspection(setup):
    db,work=setup
    with clean.transport.job(work/'oracle-clean-r1'):
        result=stop.inspect(work)
        assert any(r['pid']==os.getpid() for r in result['processes'])
        with pytest.raises(io.DPError,match='STOP_SELF'):stop.stop(work)


def test_stop_only_exact_locked_notebook_and_force_kill(tmp_path):
    work=tmp_path/'work';(work/'restored').mkdir(parents=True)
    (work/'restored/full-manifest.json').write_text('{}')
    old=work/'oracle-import-r3';old.mkdir();lock=old/'job.lock';lock.touch()
    ready=tmp_path/'ready'
    code="import fcntl,signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); f=open(sys.argv[1],'r+'); fcntl.flock(f,fcntl.LOCK_EX); pathlib.Path(sys.argv[2]).touch(); time.sleep(60)"
    p=subprocess.Popen([sys.executable,'-c',code,str(lock),str(ready),'ipykernel-test'])
    other=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    try:
        until=time.monotonic()+5
        while not ready.exists() and time.monotonic()<until:time.sleep(.01)
        assert ready.exists()
        assert stop.inspect(work)['processes'][0]['pid']==p.pid
        with pytest.raises(io.DPError,match='OLD_IMPORT_RUNNING'):
            with stop.guard(work):pass
        result=stop.stop(work,grace_seconds=0)
        assert result['terminated']==[{'pid':p.pid,'forced':True}]
        p.wait(timeout=5)
        assert other.poll() is None
        assert result['status']=='LOCAL_IMPORT_LOCKS_FREE' and result['oracle_sessions_checked'] is False
    finally:
        for proc in [p,other]:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=5)


@pytest.mark.parametrize('release',['r1','r2'])
def test_exact_packaged_notebook_with_real_dataiku_adapter(setup,tmp_path,release):
    exercise_packaged_notebook(setup,tmp_path,release)


def exercise_packaged_notebook(setup,tmp_path,release):
    from test_oracle_deferred_indexes import _mock_code
    root=Path(__file__).resolve().parents[2]
    delivery=root/('08_DEPLOYMENT/DATAIKU/legal_oracle_clean_import_20261020_'+release)
    work=setup[1]
    original=(work/'oracle-import-r3/full-state.json').read_bytes()
    code=(delivery/'package/DATAIKU_CLEAN_IMPORT_RUN.txt').read_text()
    code=code.replace('WORK_DIR = ""', 'WORK_DIR = '+repr(str(work)))
    source=Path(__file__).read_text()
    database=next(ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Database')
    boundary=_mock_code()+'\nfrom lawrag.pipeline import oracle_clean_import as clean\nfrom semantic_runtime import oracle_dp_assets as assets\n'+database
    shim=f'''import sys,types,json
from pathlib import Path
m=types.ModuleType('dataiku')
class Folder:
 def __init__(self,name): assert name=='LEGAL_DATA_ZIP_IMPORT'
 def get_download_stream(self,name): return (Path({str(delivery)!r})/name.lstrip('/')).open('rb')
m.Folder=Folder
m.default_project_key=lambda:'fixture'
remote_db=None
def executor(**kwargs):
 global remote_db
 import pandas as pd
 from lawrag.pipeline import oracle_query_dataiku as bridge
 if remote_db is None:
  exec({boundary!r},globals())
  source=AssetOracle();query=QueryOracle();schema=SchemaOracle()
  schema.created=set(schema.columns)
  class Delegate:
   def request(self,method,path,json):
    text=json['statementText']
    if 'WHERE 1=0' in text:return {{'items':[{{'resultSet':{{'items':[],'hasMore':False,'offset':0}}}}]}}
    target=schema if ':owner' in text and 'ALL_' in text else query if 'LEGAL_RAG_QUERY_' in text else source
    return target.request('POST','/sql',json)
  remote_db=Database(Delegate())
  remote_db.rows[q.STATE]=[{{'saved':'preserve'}}]
  captured={{}}
  original_render=bridge.render
  def render(text,binds,**kw):
   captured.update(statementText=text,binds=[{{'name':n,'value':v,'data_type':k}} for n,v,k in binds])
   return original_render(text,binds,**kw)
  bridge.render=render
  bridge.DataikuClient.identity=lambda self:('fixture',{{'TEST_ONLY':True}})
  class Executor:
   def query_to_df(self,text,**kw):
    result=remote_db.request('POST','/sql',{{**captured,'limit':1000}})
    if kw.get('pre_queries'):return pd.DataFrame([{{'OK':1}}])
    assert kw.get('infer_from_schema') is True
    return pd.DataFrame(result['items'][0]['resultSet']['items'])
  m.saved_executor=Executor()
 return m.saved_executor
m.SQLExecutor2=executor
sys.modules['dataiku']=m
'''
    driver=tmp_path/'exact_notebook.py'
    default_action='inspect_processes' if release=='r1' else 'plan'
    driver.write_text(shim+f"\ntext={code!r}\ndefault_action={default_action!r}\n"+
        "for action in ['inspect_processes','plan','replace','status']:\n"+
        " exec(compile(text.replace('ACTION = \"'+default_action+'\"','ACTION = '+repr(action)), 'DELIVERED_TXT', 'exec'),globals())\n"+
        "assert CLEAN_RESULT['result']['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'\n"+
        "assert remote_db.rows[q.STATE]==[{'saved':'preserve'}]\n"+
        "print('EXACT_PACKAGE_AND_ADAPTER_PASS')\n")
    proc=subprocess.run([sys.executable,str(driver)],cwd=tmp_path,text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout[-6000:]+proc.stderr[-6000:]
    assert 'EXACT_PACKAGE_AND_ADAPTER_PASS' in proc.stdout
    assert (work/'oracle-import-r3/full-state.json').read_bytes()==original
    assert (work/('code-clean-'+release)/'lawrag').exists() is False
    assert (work/('code-clean-'+release)/'runtime/lawrag/pipeline/oracle_clean_import.py').read_bytes()==(delivery/'package/runtime/lawrag/pipeline/oracle_clean_import.py').read_bytes()
