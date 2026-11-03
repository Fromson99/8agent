import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import runpy
import sys
import types
import zipfile
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
import g19sql_common as common
import g19sql_queries as queries
import g19sql_worker as worker
import g19sql_notebook as notebook


def fixture(tmp_path):
    package=tmp_path/'loader';package.mkdir()
    contract={'tables':{'SRCH_ROW':{'owner':'SIDDS','name':'LGL_G19_SRCH_ROW_S_1',
        'primary_key':['release','id'],'columns':{'release':{'name':'PUB_ID','type':'VARCHAR2(100)'},'id':{'name':'ROW_ID','type':'VARCHAR2(100)'}}}}}
    common.write(package/'contract.json',contract)
    (package/'run.py').write_text('raise AssertionError("LOADER_MUST_NOT_BE_IMPORTED")\n')
    manifest={'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir()}}
    common.write(package/'CODE_MANIFEST.json',manifest)
    database=[{'LOGIN_USER':'PIDD2APP','DB_NAME':'MOCK_DB','SERVICE_NAME':'MOCK_SERVICE'}]
    obj=[{'OWNER':'SIDDS','OBJECT_NAME':'LGL_G19_SRCH_ROW_S_1','OBJECT_ID':42,'DATA_OBJECT_ID':42}]
    state={'status':'WRITE_UNCONFIRMED','pending':{'sha256':'unchanged'},'binding':{
        'code':common.digest(manifest),'contract':common.digest(contract),'database':database,'objects':obj}}
    state_dir=tmp_path/'state';state_dir.mkdir();common.write(state_dir/'state.json',state)
    sha=hashlib.sha256((state_dir/'state.json').read_bytes()).hexdigest()
    report={'run_id':'abc','plan_sha256':'def','status':'PARTIAL','original_state_unchanged':True,
        'original_state_sha256_after':sha,'binding':state['binding'],'skipped':[{'target':'unit','reason':'KIND_ABSENT_OR_AMBIGUOUS'}],
        'trials':[{'kind':'asset.unit_fts_posting','phase':'response','arm':'exception','pair':i,'rows':2000,
                   'status':'ROLLED_BACK_VERIFIED','batches':[{'request_s':3+i*.1,'payload_db_s':1.5,
                    'insert_db_s':.6,'verify_db_s':.4,'rollback_db_s':.1}]} for i in range(3)]}
    directory=tmp_path/'gold-comparison-reports'/'original';directory.mkdir(parents=True)
    common.write(directory/'COMPARISON.json',report)
    common.write(directory/'worker-config.json',{'run_id':'abc','plan_sha256':'def','context':{
        'state':state,'state_dir':str(state_dir),'package':str(package),'contract':contract}})
    return directory/'COMPARISON.json'


def answer(sql,ctx):
    queries.readonly(sql)
    if 'SYS_CONTEXT' in sql:return copy.deepcopy(ctx['database'])
    if 'FROM ALL_OBJECTS' in sql:return copy.deepcopy(ctx['object'])
    if 'FROM ALL_TABLES' in sql:return [{'OWNER':ctx['owner'],'TABLE_NAME':ctx['table'],'NUM_ROWS':1234,'BLOCKS':100,'PARTITIONED':'NO','LAST_ANALYZED':None}]
    if 'FROM GV$SQL q' in sql:return [{'INST_ID':1,'SQL_ID':'a'*13,'CHILD_NUMBER':0,'PLAN_HASH_VALUE':123,'EXECUTIONS':6,'LAST_ACTIVE_TIME':'2026-11-03 10:10:10'}]
    if 'FROM GV$SQL_PLAN_STATISTICS_ALL' in sql:return [{'ID':1,'LAST_STARTS':0,'LAST_OUTPUT_ROWS':0,'LAST_TEMPSEG_SIZE':None,'MAX_TEMPSEG_SIZE':None}]
    if 'FROM GV$SQL_PLAN WHERE' in sql:return [{'ID':1,'PARENT_ID':0,'OPERATION':'TABLE ACCESS','OPTIONS':'FULL','OBJECT_OWNER':'SIDDS','OBJECT_NAME':ctx['table'],'CARDINALITY':1000000,'TEMP_SPACE':50000}]
    if 'FROM ALL_INDEXES' in sql:return [{'OWNER':'SIDDS','INDEX_NAME':'I_PK','INDEX_TYPE':'NORMAL','UNIQUENESS':'UNIQUE','STATUS':'VALID','VISIBILITY':'VISIBLE','PARTITIONED':'NO','LAST_ANALYZED':None}]
    if 'FROM ALL_IND_COLUMNS' in sql:return [{'INDEX_OWNER':'SIDDS','INDEX_NAME':'I_PK','COLUMN_NAME':n,'COLUMN_POSITION':i+1} for i,n in enumerate(ctx['pk_columns'])]
    if 'FROM ALL_CONSTRAINTS' in sql:return [{'OWNER':'SIDDS','CONSTRAINT_NAME':'PK','CONSTRAINT_TYPE':'P','STATUS':'ENABLED','VALIDATED':'VALIDATED','INDEX_OWNER':'SIDDS','INDEX_NAME':'I_PK'}]
    if 'FROM ALL_CONS_COLUMNS' in sql:return [{'CONSTRAINT_NAME':'PK','COLUMN_NAME':n,'POSITION':i+1} for i,n in enumerate(ctx['pk_columns'])]
    if 'FROM ALL_TAB_STATISTICS' in sql:return [{'STALE_STATS':None,'STATTYPE_LOCKED':None,'LAST_ANALYZED':None}]
    if 'FROM ALL_TAB_COLUMNS' in sql:return [{'COLUMN_NAME':n,'DATA_TYPE':'VARCHAR2'} for n in ctx['pk_columns']]
    if 'FROM GV$TEMPSEG_USAGE' in sql:return []
    raise AssertionError('Unexpected query: '+sql)


def collect(tmp_path, transform=None):
    path=fixture(tmp_path);ctx=common.bind(path)
    output=tmp_path/'new';output.mkdir()
    before={p:p.read_bytes() for p in (path,path.parent/'worker-config.json',Path(ctx['state_path']))}
    calls=[]
    def query(sql):
        calls.append(sql)
        return transform(sql,ctx) if transform else answer(sql,ctx)
    result=worker.collect(ctx,output,query)
    assert all(p.read_bytes()==raw for p,raw in before.items())
    return ctx,result,output,calls


def test_success_consumes_real_metadata_shapes_and_preserves_state(tmp_path):
    ctx,r,out,calls=collect(tmp_path)
    assert r['status']=='COLLECTED' and r['original_state_unchanged'] is True
    assert r['index_summary'][0]['pk_leading_columns'] is True
    assert r['loader_status']=='WRITE_UNCONFIRMED'
    assert r['plan_summary'][0]['nonzero_last_starts'] is False
    assert r['plan_summary'][0]['workarea_last_temp_bytes']==[]
    assert r['comparison_skipped'][0]['target']=='unit'
    assert len(calls)==13 and all(s.startswith('SELECT') for s in calls)
    assert 'RAW_SQL' not in common.canonical(r) and 'LOADER_MUST_NOT_BE_IMPORTED' not in common.canonical(r)
    assert (out/'DBA_READONLY_CHECK.sql').exists()
    assert r['timing'][0]['medians']['unseparated_s']==pytest.approx(.5)


@pytest.mark.parametrize('code',['ORA-00942','ORA-01031','ORA-00904'])
def test_optional_permissions_do_not_become_zero_or_success(tmp_path,code):
    def transform(sql,ctx):
        if 'GV$SQL' in sql or 'GV$TEMPSEG_USAGE' in sql:raise RuntimeError(code+': secret raw SQL must not be copied')
        return answer(sql,ctx)
    ctx,r,out,calls=collect(tmp_path,transform)
    assert r['status']=='PARTIAL' and r['cursors']==[]
    assert r['queries']['current_account_temp']['status']=='UNAVAILABLE'
    assert 'secret raw' not in (out/'worker-result.json').read_text()


@pytest.mark.parametrize('fault',['identity','object','unexpected'])
def test_wrong_database_object_and_unexpected_failure_stop_without_retry(tmp_path,fault):
    def transform(sql,ctx):
        if fault=='identity' and 'SYS_CONTEXT' in sql:return [{'LOGIN_USER':'OTHER'}]
        if fault=='object' and 'ALL_OBJECTS' in sql:return []
        if fault=='unexpected' and 'ALL_TABLES' in sql:raise RuntimeError('ORA-03113: lost connection')
        return answer(sql,ctx)
    ctx,r,out,calls=collect(tmp_path,transform)
    assert r['status']=='STOPPED' and len(calls)<=3
    assert r['queries_count']==len(calls)


def test_no_cached_cursor_is_partial_and_empty_temp_not_historical_zero(tmp_path):
    def transform(sql,ctx):
        return [] if 'FROM GV$SQL q' in sql else answer(sql,ctx)
    ctx,r,out,calls=collect(tmp_path,transform)
    assert r['status']=='PARTIAL'
    html=notebook.page(r,'TEMP')
    assert '과거 TEMP=0 증명이 아닙니다' in html


def test_cursor_limit_is_explicit_and_never_exceeds_query_budget(tmp_path):
    def transform(sql,ctx):
        rows=answer(sql,ctx)
        if 'FROM GV$SQL q' in sql:return [dict(rows[0],CHILD_NUMBER=i) for i in range(13)]
        return rows
    ctx,r,out,calls=collect(tmp_path,transform)
    assert r['status']=='PARTIAL' and len(r['cursors'])==12
    assert r['queries']['cached_candidates']['status']=='TRUNCATED'
    assert r['queries_count']==35 and r['queries_count']<=40


def test_runtime_permission_failure_is_not_retried_for_each_cursor(tmp_path):
    def transform(sql,ctx):
        if 'GV$SQL_PLAN_STATISTICS_ALL' in sql:raise RuntimeError('ORA-01031: denied')
        rows=answer(sql,ctx)
        return [dict(rows[0],CHILD_NUMBER=i) for i in range(3)] if 'FROM GV$SQL q' in sql else rows
    ctx,r,out,calls=collect(tmp_path,transform)
    assert sum('GV$SQL_PLAN_STATISTICS_ALL' in s for s in calls)==1
    assert r['status']=='PARTIAL'


@pytest.mark.parametrize('change',['code','contract','state','config','report'])
def test_input_binding_changes_rejected_before_database_access(tmp_path,change):
    path=fixture(tmp_path)
    if change=='code':(tmp_path/'loader'/'run.py').write_text('pass\n')
    if change=='contract':(tmp_path/'loader'/'contract.json').write_text('{}')
    if change=='state':(tmp_path/'state'/'state.json').write_text('{}')
    if change=='config':
        p=path.parent/'worker-config.json';value=common.read(p);value['run_id']='different';common.write(p,value)
    if change=='report':
        value=common.read(path);value['status']='STOPPED';common.write(path,value)
    with pytest.raises(ValueError):common.bind(path)


def test_discovery_requires_exact_one_and_never_chooses_latest(tmp_path):
    path=fixture(tmp_path)
    assert common.locate(cwd=tmp_path)==path
    second=path.parent.parent/'newer';second.mkdir();(second/'COMPARISON.json').write_bytes(path.read_bytes())
    with pytest.raises(ValueError,match='EXACT'):common.locate(cwd=tmp_path)
    assert common.locate(hints=[str(path),str(path)],cwd=tmp_path)==path


@pytest.mark.parametrize('sql',['DELETE FROM x','SELECT 1 FROM DUAL; DELETE FROM x','EXPLAIN PLAN FOR SELECT 1 FROM DUAL','BEGIN NULL; END;','SELECT * FROM x FOR UPDATE','SELECT /* hint */ 1 FROM DUAL'])
def test_readonly_guard_rejects_mutation_and_multiple_statements(sql):
    with pytest.raises(ValueError,match='READONLY'):queries.readonly(sql)


def test_generated_dba_queries_pass_same_guard(tmp_path):
    ctx=common.bind(fixture(tmp_path))
    content=worker.dba_sql(ctx)
    text='\n'.join(line for line in content.splitlines() if not line.startswith('--'))
    for sql in text.split(';'):
        if sql.strip():queries.readonly(sql.strip())
    assert 'SQL_FULLTEXT' not in text and 'ACCESS_PREDICATES' not in text
    # Source strings can look like SQL but never become executable syntax.
    assert queries.readonly("SELECT 'COMMIT; DROP' FROM DUAL")


def test_incomplete_time_and_clock_rounding_are_not_fabricated(tmp_path):
    report=common.read(fixture(tmp_path))
    report['trials'].pop()
    assert common.timing(report)[0]['medians']=={}
    report['trials'][0]['batches'][0]['request_s']=.01
    assert common.timing(report)[0]['samples'][0]['unseparated_s']<0
    report['trials'][0]['batches'][0].pop('payload_db_s')
    assert len(common.timing(report)[0]['samples'])==1
    assert common.timing({'trials':[]})==[]


def test_display_is_database_free_and_escapes_metadata(tmp_path):
    _,r,_,_=collect(tmp_path)
    r['index_summary'][0]['INDEX_NAME']='<script>bad</script>'
    for name in ('요약','시간','인덱스','계획','계획상세','TEMP','상태'):
        html=notebook.page(r,name)
        assert '<script>' not in html
    assert '&lt;script&gt;' in notebook.page(r,'인덱스')


def test_original_state_change_during_query_stops_next_query(tmp_path):
    path=fixture(tmp_path);ctx=common.bind(path);out=tmp_path/'result';out.mkdir();calls=[]
    def query(sql):
        calls.append(sql)
        Path(ctx['state_path']).write_text('{}')
        return ctx['database']
    r=worker.collect(ctx,out,query)
    assert len(calls)==1 and r['status']=='STOPPED_ORIGINAL_STATE_CHANGED'


def test_job_lock_conflict_makes_no_queries(tmp_path):
    import fcntl
    path=fixture(tmp_path);ctx=common.bind(path);out=tmp_path/'result';out.mkdir()
    with (tmp_path/'state'/'job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=worker.collect(ctx,out,lambda _:pytest.fail('DB call while locked'))
    assert r['status']=='STOPPED' and r['queries_count']==0


def test_python39_and_zip_manifest_and_no_javascript_or_nested_zip():
    for path in (HERE/'package').glob('*.py'):ast.parse(path.read_text(),feature_version=(3,9))
    ast.parse((HERE/'01_RUN_INDEX_JOIN_TEMP_CHECK_R1.txt').read_text(),feature_version=(3,9))
    with zipfile.ZipFile(HERE/'G19_INDEX_JOIN_TEMP_CHECK_20261103_R1.zip') as archive:
        manifest=json.loads(archive.read('MANIFEST.json'))
        assert set(archive.namelist())==set(manifest['files'])|{'MANIFEST.json'}
        for name,sha in manifest['files'].items():assert hashlib.sha256(archive.read(name)).hexdigest()==sha
        assert all(Path(n).suffix in ('.py','.json') for n in archive.namelist())


def test_oracle_dialect_select_syntax_and_instance_binding(tmp_path):
    import sqlglot
    ctx=common.bind(fixture(tmp_path))
    cursor={'INST_ID':2,'SQL_ID':'a'*13,'CHILD_NUMBER':0,'PLAN_HASH_VALUE':123}
    sqls=[queries.IDENTITY,*[s for _,s,_ in queries.metadata(ctx)],queries.candidates(ctx),queries.temp(ctx),
          *[queries.bounded(s,n) for _,s,n in queries.plans(cursor,ctx['pk_columns'])]]
    for sql in sqls:sqlglot.parse_one(sql,read='oracle')
    for _,sql,_ in queries.plans(cursor,ctx['pk_columns']):assert 'INST_ID=2' in sql
    dba='\n'.join(l for l in worker.dba_sql(ctx).splitlines() if not l.startswith('--'))
    for sql in dba.split(';'):
        if sql.strip():sqlglot.parse_one(sql,read='oracle')


def test_parent_timeout_reclaims_one_child_without_retry(tmp_path,monkeypatch):
    path=fixture(tmp_path);monkeypatch.chdir(tmp_path)
    processes=[]
    class Process:
        def __init__(self,*args,**kwargs):self.returncode=None;self.terminated=False;processes.append(self)
        def poll(self):return self.returncode
        def terminate(self):self.terminated=True;self.returncode=-15
        def wait(self,timeout):return self.returncode
    monkeypatch.setattr(notebook.subprocess,'Popen',Process)
    counter=iter(range(0,10000,300))
    monkeypatch.setattr(notebook.time,'monotonic',lambda:next(counter))
    monkeypatch.setattr(notebook,'display',lambda _:None)
    result=notebook.run(str(path))
    assert result['status']=='CLIENT_TIMEOUT_REMOTE_SELECT_UNCONFIRMED'
    assert result['remote_select_cancellation_confirmed'] is False
    assert len(processes)==1 and processes[0].terminated


def test_corrupt_attachment_zip_is_rejected_before_extraction_or_database(tmp_path,monkeypatch):
    class Folder:
        def __init__(self,name):pass
        def list_paths_in_partition(self):return ['/G19_INDEX_JOIN_TEMP_CHECK_20261103_R1.zip']
        def get_download_stream(self,path):return io.BytesIO(b'changed')
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=Folder))
    with pytest.raises(ValueError,match='SQL_CHECK_ZIP_HASH'):
        exec(compile((HERE/'01_RUN_INDEX_JOIN_TEMP_CHECK_R1.txt').read_text(),'attachment.txt','exec'),{})


def test_actual_attachment_bootstrap_and_child_worker_with_fake_dataiku(tmp_path,monkeypatch):
    path=fixture(tmp_path);ctx=common.bind(path)
    adapter=tmp_path/'fake_modules';adapter.mkdir()
    common.write(adapter/'fixture.json',ctx)
    # Child uses the real collector and real SQL construction, with only the SQL transport replaced.
    (adapter/'dataiku.py').write_text('''import json
import importlib.util
from pathlib import Path
import pandas as pd
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('saved_test', %r)
test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)
class SQLExecutor2:
    def __init__(self,connection):assert connection=='AIDP'
    def query_to_df(self,sql,**kwargs):
        assert kwargs=={'infer_from_schema':True,'parse_dates':False}
        ctx=json.loads((HERE/'fixture.json').read_text())
        with (HERE/'calls.jsonl').open('a') as f:f.write(json.dumps(sql)+'\\n')
        return pd.DataFrame(test.answer(sql,ctx))
''' % str(HERE/'test_readonly.py'))
    archive=(HERE/'G19_INDEX_JOIN_TEMP_CHECK_20261103_R1.zip').read_bytes()
    class Folder:
        def __init__(self,name):assert name=='ehA8dpVm'
        def list_paths_in_partition(self):return ['/G19_INDEX_JOIN_TEMP_CHECK_20261103_R1.zip']
        def get_download_stream(self,path):return io.BytesIO(archive)
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=Folder))
    monkeypatch.syspath_prepend(str(adapter));monkeypatch.chdir(tmp_path)
    import tempfile
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    display=types.ModuleType('IPython.display')
    display.HTML=lambda value:value
    display.display=lambda *a,**k:None
    display.clear_output=lambda **k:None
    ipython=types.ModuleType('IPython');ipython.display=display
    monkeypatch.setitem(sys.modules,'IPython',ipython)
    monkeypatch.setitem(sys.modules,'IPython.display',display)
    namespace={'_g19_comparison_result':{'output':str(path)}}
    script=(HERE/'01_RUN_INDEX_JOIN_TEMP_CHECK_R1.txt').read_text()
    exec(compile(script,'actual_attachment.txt','exec'),namespace)
    r=namespace['_g19_sqlcheck_result']
    assert r['status']=='COLLECTED',r
    assert r['original_state_unchanged'] is True
    calls=(adapter/'calls.jsonl').read_text().splitlines()
    assert len(calls)==13
    namespace['SHOW_SQL_CHECK']('계획상세',1)
    assert len((adapter/'calls.jsonl').read_text().splitlines())==13
    # The installed loader raising at import was never imported by the diagnostic.
    assert r['binding']['code_sha256']==ctx['code_sha256']
