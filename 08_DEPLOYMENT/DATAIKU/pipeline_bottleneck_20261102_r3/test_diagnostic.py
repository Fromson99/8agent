import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import types
import zipfile
import pytest

HERE = Path(__file__).parent
sys.path.insert(0,str(HERE/'package'))
import g19diag_common as common
import g19diag_snapshot as snap
import g19diag_oracle_worker as worker
import g19diag_profiler as profiler
import g19diag_notebook as notebook

BASE = HERE.parent/'gold_fresh_1_20261102_r1/package'
sys.path.insert(0,str(BASE))
import gold_io


def contract(): return gold_io.Contract(BASE/'contract.json')


@pytest.mark.parametrize('key', ['DOC_VER','DOC_UNIT','DOC_BLK','SRCH_ROW'])
def test_real_generated_sql_never_commits(key):
    c = contract(); row = {}
    for name,col in c.tables[key]['columns'].items():
        if col['default']: continue
        row[name] = 'Y' if col['type'].startswith('CHAR(') else '본문 "COMMIT;" 원문' if col['type']=='CLOB' else 'fixture'
    sql,binds = c.batch(key,[row]); nonce='a'*32
    changed = worker.rollback_probe_sql(sql,nonce)
    assert 'COMMIT' not in changed
    assert 'INSERT INTO '+c.table(key) in changed and 'DBMS_LOB.COMPARE' in changed
    assert changed.count('ROLLBACK;')==2
    assert binds[0][1] and 'COMMIT;' in binds[0][1]  # data unchanged, not treated as SQL
    assert worker.marker_times(Exception('ORA-20084: G19_PROBE_OK_'+nonce+' i=12 v=34 r=1'),nonce)=={
        'insert_db_seconds':.12,'verify_db_seconds':.34,'rollback_db_seconds':.01}
    assert worker.marker_times(Exception('ORA-01654: no extent'),nonce) is None
    assert worker.marker_times(Exception('ORA-20084: G19_PROBE_OK_'+'b'*32+' i=1 v=1 r=1'),nonce) is None


@pytest.mark.parametrize('sql', ['BEGIN COMMIT; END;', 'DECLARE n NUMBER; BEGIN COMMIT; COMMIT; END;', 'DECLARE n NUMBER; BEGIN EXECUTE IMMEDIATE x; SELECT COUNT(*) INTO n FROM t; COMMIT; END;'])
def test_probe_rejects_unknown_sql(sql):
    with pytest.raises(ValueError): worker.rollback_probe_sql(sql,'a'*32)


def test_readonly_sample_and_no_payload_leak(tmp_path):
    path=tmp_path/'data.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sample(id INTEGER, text TEXT)')
        db.executemany('INSERT INTO sample VALUES (?,?)',[(i,'PRIVATE_SOURCE_BODY') for i in range(80)])
        db.execute('CREATE VIEW expanded AS SELECT a.id,a.text,b.id AS other FROM sample a JOIN sample b ON a.id=b.id')
    before=path.read_bytes()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        result=snap.sample_table(db,'expanded')
        assert result['sample_rows']==32 and result['status']=='OK'
        assert 'PRIVATE_SOURCE_BODY' not in common.canonical(result)
        result=snap.sample_table(db,'missing')
        assert result['status']=='UNMEASURED_OR_INTERRUPTED'
        with pytest.raises(ValueError): snap.sample_table(db,'sample; DROP TABLE sample')
    assert path.read_bytes()==before


def test_progress_heartbeat_not_double_counted(tmp_path):
    rows=[{'phase':'LOAD','table':'T','rows':100,'elapsed_s':10,'request_s':1},
          {'phase':'LOAD','table':'T','rows':100,'elapsed_s':20,'request_s':1},
          {'phase':'LOAD','table':'T','rows':200,'elapsed_s':30,'request_s':2}]
    (tmp_path/'date-fresh1-load-run.log').write_text('\n'.join(map(json.dumps,rows)))
    result=snap.historical_logs(tmp_path)
    assert result[0]['observations']==2 and result[0]['rows_per_second']==5
    assert 'binding unverified' in result[0]['scope']


def test_nested_time_and_exception_identity(tmp_path):
    now=[0.]; rec=profiler.Recorder(tmp_path/'metrics.json',clock=lambda:now[0])
    with rec.span('parent'):
        now[0]=1
        with rec.span('child'): now[0]=4
        now[0]=5
    assert rec.metrics['setup|setup|parent']['exclusive_seconds']==2
    assert rec.metrics['setup|setup|child']['exclusive_seconds']==3
    exc=RuntimeError('original'); holder=types.SimpleNamespace(call=lambda:(_ for _ in ()).throw(exc))
    rec.wrap(holder,'call')
    with pytest.raises(RuntimeError) as caught: holder.call()
    assert caught.value is exc


def fixture_context(tmp_path):
    job=tmp_path/'input/oracle-import-r2';job.mkdir(parents=True)
    root=job.parent/'generation';root.mkdir()
    manifest={'counts':{'document':1,'source_unit':2,'source_block':3}}
    common.write(root/'manifest.json',manifest)
    files={'manifest.json':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()}
    package=tmp_path/'legal-gold-fresh-1-fixture';package.mkdir()
    (package/'contract.json').write_bytes((BASE/'contract.json').read_bytes())
    code={'files':{'contract.json':hashlib.sha256((package/'contract.json').read_bytes()).hexdigest()}}
    common.write(package/'CODE_MANIFEST.json',code)
    binding={'source_release':'a'*64,'files':files,'generation':str(root),'code':common.digest(code),'contract':common.digest(contract().value)}
    state_dir=job.parent/('gold-shape-'+binding['contract'][:12]);state_dir.mkdir();common.write(state_dir/'state.json',{'binding':binding,'status':'WRITE_UNCONFIRMED','pending':{'original':'keep'}})
    body={'binding':{'source':binding['source_release'],'files':files},'tables':{'kind':{'asset':'sample.sqlite','rows':1}}}
    common.write(job/'projection-descriptor-r7.json',dict(body,checksum=common.digest(body)))
    common.write(job/'full-state.json',{'identity':{'generation':str(root)}})
    return job,state_dir,package,root


def test_exact_context_and_tamper_rejection(tmp_path):
    job,state_dir,package,root=fixture_context(tmp_path)
    ctx=common.context(job,state_dir,package)
    assert ctx['state']['status']=='WRITE_UNCONFIRMED'
    (root/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='SOURCE_MANIFEST_HASH'): common.context(job,state_dir,package)


def test_package_tamper_rejection(tmp_path):
    job,state_dir,package,root=fixture_context(tmp_path)
    (package/'contract.json').write_text('{}')
    with pytest.raises(ValueError,match='INSTALLED_PACKAGE_HASH'): common.context(job,state_dir,package)


@pytest.mark.parametrize('failure', [None,'permission','insert','remaining'])
def test_worker_actual_contract_sql_end_to_end(tmp_path,monkeypatch,failure):
    import pandas as pd
    c=contract(); code='c'*64; identity=[{'LOGIN_USER':'fixture','DB_NAME':'test','SERVICE_NAME':'svc'}]
    state={'binding':{'code':code,'database':identity,'objects':[], 'query_release':'q'*64,'files':{'manifest.json':'s'*64}}}
    state_dir=tmp_path/'state';state_dir.mkdir();common.write(state_dir/'state.json',state)
    common.write(tmp_path/'contract.json',c.value)
    ctx={'package':str(tmp_path),'state_dir':str(state_dir),'state':state,'descriptor':{'tables':{}}}
    active=[]; counts={}; sqls=[]
    class FakeExecutor:
        def query_to_df(self,sql,**kwargs):
            if kwargs.get('pre_queries'):
                sqls.append(kwargs['pre_queries'][0]); nonce=re.search(r'G19_PROBE_OK_([a-f0-9]{32})',sqls[-1])[1]
                assert ' COMMIT;' not in sqls[-1] and kwargs['post_queries']==['ROLLBACK']
                if failure=='insert': raise RuntimeError('ORA-01654: no extent')
                raise RuntimeError('ORA-20084: G19_PROBE_OK_'+nonce+' i=10 v=2 r=1 p=3')
            if 'SYS_CONTEXT' in sql and ' AS LOGIN_USER' in sql: return pd.DataFrame(identity)
            if 'COUNT(*) AS N' in sql:
                n=counts.get(sql,0);counts[sql]=n+1
                return pd.DataFrame([{'N':1 if failure=='remaining' and n else 0}])
            if 'V$SQL' in sql and failure=='permission': raise RuntimeError('ORA-00942: missing permission')
            if sql=='SELECT 1 AS OK FROM DUAL': return pd.DataFrame([{'OK':1}])
            if 'ROWNUM<=32' in sql:
                key=next(k for k,t in c.tables.items() if c.table(k) in sql)
                row={n:None if not col['required'] else 'fixture' for n,col in c.tables[key]['columns'].items() if not col['default']}
                for n,col in c.tables[key]['columns'].items():
                    if col['type']=='CLOB': row[n]='PRIVATE_TEXT'
                    if col['type'].startswith('CHAR'): row[n]='N'
                return pd.DataFrame([row])
            return pd.DataFrame([])
    fake=FakeExecutor(); monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:fake))
    loader=types.SimpleNamespace(verify_code=lambda:code,Contract=lambda p:c,object_binding=lambda db,co:[])
    monkeypatch.setitem(sys.modules,'run',loader)
    monkeypatch.setattr(c,'preflight',lambda *a:None)
    monkeypatch.setitem(sys.modules,'jdbc_transport',types.SimpleNamespace(render=lambda s,b,write:'DECLARE\nx CLOB;\nBEGIN\n'+s+'\nEND;'))
    def fake_source(ctx,loader,key,kind):
        row={n:None if not col['required'] else 'fixture' for n,col in c.tables[key]['columns'].items() if not col['default']}
        for n,col in c.tables[key]['columns'].items():
            if col['type']=='CLOB': row[n]='PRIVATE_TEXT'
            if col['type'].startswith('CHAR'): row[n]='N'
        return [row],{'table':key,'kind':kind,'status':'OK','sample_rows':1}
    monkeypatch.setattr(worker,'source_sample',fake_source)
    output=tmp_path/'oracle.json';worker.run({'context':ctx,'insert_probes':True},output)
    result=common.read(output)
    assert 'PRIVATE_TEXT' not in output.read_text()
    assert state==common.read(state_dir/'state.json')
    if failure in ('insert','remaining'):
        assert result['status']=='STOPPED' and len(sqls)==1
    else:
        assert result['status']=='COMPLETE' and len(sqls)==9
        assert all(p['status']=='ROLLED_BACK_VERIFIED' for p in result['insert_probes'])


def test_html_escaped_and_unmeasured_not_zero(monkeypatch):
    monkeypatch.setattr(notebook,'display_html',lambda x:None)
    value=notebook.show('요약',{'status':'<script>x</script>'})
    assert '<script>' not in value and '미측정' in value
    assert '미실행' in value


def test_profile_default_does_not_execute(monkeypatch):
    monkeypatch.setattr(notebook,'display_html',lambda x:None)
    monkeypatch.setattr(notebook.subprocess,'Popen',lambda *a,**k:pytest.fail('must not launch'))
    assert notebook.profile()['status']=='실행 안 함'


@pytest.mark.parametrize('script_name', ['01_DIAG_AND_ROLLBACK_INSERT_RUN_R3.txt','02_PROFILE_EXISTING_STAGE_RUN_R3.txt'])
def test_complete_notebook_launcher(tmp_path,monkeypatch,script_name):
    import builtins
    raw=(HERE/'G19_BOTTLENECK_DIAGNOSTIC_20261102_R3.zip').read_bytes()
    calls=[]
    folder=types.SimpleNamespace(list_paths_in_partition=lambda:['/G19_BOTTLENECK_DIAGNOSTIC_20261102_R3.zip'],get_download_stream=lambda p:io.BytesIO(raw))
    fake_dataiku=types.SimpleNamespace(Folder=lambda value:folder)
    fake_notebook=types.SimpleNamespace(snapshot=lambda *a,**k:calls.append(('snapshot',a,k)),profile=lambda *a,**k:calls.append(('profile',a,k)),show=lambda x:calls.append(('show',x)))
    original_import=builtins.__import__
    def imported(name,*args,**kwargs):
        if name=='dataiku':return fake_dataiku
        if name=='g19diag_notebook':return fake_notebook
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',imported)
    monkeypatch.setattr('tempfile.gettempdir',lambda:str(tmp_path))
    with contextlib.redirect_stdout(io.StringIO()) as out:
        scope={};exec(compile((HERE/script_name).read_text(),script_name,'exec'),scope)
        scope['SHOW_DIAG_PAGE']('삽입')
    assert out.getvalue()=='' and calls[-1]==('show','삽입')
    assert len(calls)==2
    if script_name.startswith('01'):assert calls[0][0]=='snapshot' and calls[0][2]['insert_probes'] is True
    else:assert calls[0][0]=='profile' and calls[0][1][0]==''
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        target=next(tmp_path.glob('g19-bottleneck-observer-*'))
        assert all((target/n).read_bytes()==z.read(n) for n in z.namelist())


def test_installed_observer_preserves_call_return_exception_and_payload(tmp_path,monkeypatch):
    # Coarse observer on one real-shaped source/query/vector stage, no DB or model calls.
    from collections import deque
    seen=[]
    class Executor:
        def query_to_df(self,*a,**k):seen.append(('rpc',a,k));return 'frame'
    class Database:
        def __init__(self,executor):self.executor=executor
        def block(self,sql,binds=(),rollback=False):return self.executor.query_to_df(sql,binds=binds,rollback=rollback)
        def query(self,sql):return self.executor.query_to_df(sql)
    class Contract:
        def batch(self,key,rows,**k):return ('exact SQL',[('payload',rows,'CLOB')])
    class Job:
        def __init__(self):self.contract=Contract();self.db=Database(Executor())
        def batch(self,key,rows,**kwargs):
            sql,binds=self.contract.batch(key,rows,**kwargs)
            return self.db.block(sql,binds,rollback=kwargs.get('verify_only',False))
    loader=types.SimpleNamespace(Contract=Contract,Database=Database,Job=Job,inputs=lambda:'inputs',file_hash=lambda p:'hash',atomic=lambda *a:None,publish=lambda *a:'published',grouped=lambda it,**k:iter(it),load_sources=lambda job,rows,**k:job.batch('DOC_BLK',rows,**k),load_query=lambda job,rows,**k:job.batch('SRCH_ROW',rows,**k))
    migration=types.SimpleNamespace(source_batch=lambda *a:'read')
    pipeline=types.ModuleType('lawrag.pipeline');pipeline.oracle_migration=migration
    parent=types.ModuleType('lawrag');parent.pipeline=pipeline
    monkeypatch.setitem(sys.modules,'lawrag',parent);monkeypatch.setitem(sys.modules,'lawrag.pipeline',pipeline)
    monkeypatch.setitem(sys.modules,'jdbc_transport',types.SimpleNamespace(install=lambda l:None,render=lambda *a,**k:'rendered'))
    mesh=types.SimpleNamespace(encode=lambda *a:['vector']);vector=types.SimpleNamespace(vector_sql=lambda *a:'vector sql')
    monkeypatch.setitem(sys.modules,'mesh_embedding',mesh);monkeypatch.setitem(sys.modules,'vector_stage',vector)
    rec=profiler.Recorder(tmp_path/'profile.json');profiler.install(loader,rec)
    job=Job();rows=[{'text':'PRIVATE_VALUE'}]
    assert loader.load_sources(job,rows)=='frame'
    assert loader.load_query(job,rows,verify_only=True)=='frame'
    assert list(loader.grouped([[1],[2]]))==[[1],[2]]
    assert mesh.encode(None)==['vector'] and vector.vector_sql(None)=='vector sql'
    assert seen[0][1]==('exact SQL',) and seen[0][2]['binds'][0][1] is rows
    assert seen[1][2]['rollback'] is True
    rec.save();data=common.read(tmp_path/'profile.json')
    assert data['batch_metrics']['load|DOC_BLK']['successful_rows']==1
    assert data['batch_metrics']['verify|SRCH_ROW']['successful_rows']==1
    assert 'PRIVATE_VALUE' not in (tmp_path/'profile.json').read_text()
    assert any('embedding_model_request' in k for k in data['metrics'])


def test_timeout_retains_unknown_and_does_not_retry(tmp_path,monkeypatch):
    job,state_dir,package,root=fixture_context(tmp_path)
    ctx=common.context(job,state_dir,package);ctx['state']['binding']['query_release']='q'*64
    before=(state_dir/'state.json').read_bytes()
    monkeypatch.setattr(notebook,'context',lambda *a,**k:ctx)
    monkeypatch.setattr(notebook,'prepared',lambda *a:ctx)
    monkeypatch.setattr(notebook,'local_samples',lambda *a:[])
    monkeypatch.setattr(notebook,'historical_logs',lambda *a:[])
    monkeypatch.setattr(notebook,'resources',lambda *a:{})
    monkeypatch.setattr(notebook,'display_html',lambda *a:None)
    monkeypatch.chdir(tmp_path)
    calls=[]
    class Process:
        returncode=None
        def poll(self):return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,timeout):return self.returncode
        def kill(self):self.returncode=-9
    def launch(args,**kwargs):
        calls.append(args)
        common.write(args[-1],{'status':'RUNNING','active_query':{'name':'INSERT rollback','started_epoch':0},'insert_probes':[{'table':'SRCH_ROW','status':'IN_FLIGHT','probe_release':'p'*64}]})
        return Process()
    monkeypatch.setattr(notebook.subprocess,'Popen',launch)
    result=notebook.snapshot()
    assert len(calls)==1 and result['oracle']['status']=='CLIENT_TIMEOUT_DB_OUTCOME_UNCONFIRMED'
    assert result['oracle']['insert_probes'][0]['probe_release']=='p'*64
    assert (state_dir/'state.json').read_bytes()==before


def add_other_state(job, package_root, original_state, old_targets=False):
    c=json.loads((BASE/'contract.json').read_text())
    c['version']='test-other-contract'
    if old_targets:
        for t in c['tables'].values():t['name']=t['name'][:-2]
    package_root.mkdir()
    common.write(package_root/'contract.json',c)
    code={'files':{'contract.json':hashlib.sha256((package_root/'contract.json').read_bytes()).hexdigest()}}
    common.write(package_root/'CODE_MANIFEST.json',code)
    state=json.loads(json.dumps(original_state));state['binding']['contract']=common.digest(c);state['binding']['code']=common.digest(code)
    state['status']='FAILED'
    directory=job.parent/('gold-shape-'+common.digest(c)[:12]);directory.mkdir()
    common.write(directory/'state.json',state)
    return directory,package_root


def test_r1_multiple_source_states_reproduced_then_r2_selects_fresh(tmp_path,monkeypatch):
    job,state_dir,package,root=fixture_context(tmp_path)
    legacy,pkg=add_other_state(job,tmp_path/'legal-gold-shape-legacy',common.read(state_dir/'state.json'),old_targets=True)
    spec=importlib.util.spec_from_file_location('prior_bottleneck_common',HERE.parent/'pipeline_bottleneck_20261102_r1/package/g19diag_common.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    with pytest.raises(ValueError,match='STATE_MATCH_REQUIRED_SET_STATE_DIR'):
        old.context(job,package_dir=package)
    before={p:p.read_bytes() for p in (state_dir/'state.json',legacy/'state.json')}
    monkeypatch.setattr(common.tempfile,'gettempdir',lambda:str(tmp_path))
    ctx=common.context(job)
    assert ctx['state_dir']==str(state_dir) and ctx['package']==str(package)
    assert ctx['state']['status']=='WRITE_UNCONFIRMED' and ctx['state']['pending']=={'original':'keep'}
    assert ctx['discovery']['source_matching_states']==2 and ctx['discovery']['fresh_matching_states']==1
    assert any(p['reason']=='NOT_FRESH_1_TARGET' for p in ctx['discovery']['packages'])
    assert all(p.read_bytes()==data for p,data in before.items())


def test_two_actual_fresh_states_need_exact_hint_not_latest(tmp_path,monkeypatch):
    job,state_dir,package,root=fixture_context(tmp_path)
    other,other_package=add_other_state(job,tmp_path/'legal-gold-fresh-1-second',common.read(state_dir/'state.json'))
    monkeypatch.setattr(common.tempfile,'gettempdir',lambda:str(tmp_path))
    with pytest.raises(common.ContextError,match='MULTIPLE_VERIFIED_FRESH_STATES_SET_STATE_DIR') as caught:
        common.context(job)
    assert caught.value.details['fresh_matching_states']==2
    ctx=common.context(job,hints={'package_paths':[str(package)]})
    assert ctx['state_dir']==str(state_dir)
    ctx=common.context(job,hints={'contract_hash':common.read(other/'state.json')['binding']['contract']})
    assert ctx['state_dir']==str(other)


def test_identical_package_copies_not_ambiguous(tmp_path,monkeypatch):
    import shutil
    job,state_dir,package,root=fixture_context(tmp_path)
    shutil.copytree(package,tmp_path/'legal-gold-fresh-1-identical-copy')
    monkeypatch.setattr(common.tempfile,'gettempdir',lambda:str(tmp_path))
    assert common.context(job)['state_dir']==str(state_dir)


def test_unreadable_unrelated_state_does_not_hide_valid_state(tmp_path,monkeypatch):
    job,state_dir,package,root=fixture_context(tmp_path)
    bad=job.parent/'gold-shape-broken';bad.mkdir();(bad/'state.json').write_text('broken')
    monkeypatch.setattr(common.tempfile,'gettempdir',lambda:str(tmp_path))
    ctx=common.context(job)
    assert ctx['state_dir']==str(state_dir)
    assert any(s['reason'].startswith('STATE_UNREADABLE') for s in ctx['discovery']['states'])


def test_binding_failure_preserves_plan_and_shows_not_zero(tmp_path,monkeypatch):
    job,state_dir,package,root=fixture_context(tmp_path)
    state=common.read(state_dir/'state.json');state['binding']['files']={'different':'files'};common.write(state_dir/'state.json',state)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(notebook,'display_html',lambda *a:None)
    monkeypatch.setattr(notebook.subprocess,'Popen',lambda *a,**k:pytest.fail('unbound context must not start DB worker'))
    result=notebook.snapshot(job,package_dir=package)
    assert result['status']=='CONTEXT_UNRESOLVED' and result['items'][0]['rows']==1
    assert result['oracle']['status']=='NOT_STARTED_CONTEXT_UNRESOLVED'
    assert result['discovery']['states'][0]['reason']=='FILES_MISMATCH'
    value=notebook.show(report=result)
    assert '미실행' in value and '0회 / 전체 기록 0건' not in value
    assert '미측정' in value
    assert '입력 파일 결속 불일치' in notebook.show('경로',result)


def test_no_plan_does_not_show_zero_rows(monkeypatch):
    monkeypatch.setattr(notebook,'display_html',lambda *a:None)
    value=notebook.show(report={'status':'STOPPED'})
    assert '미측정 / 미측정행' in value and '0 / 0행' not in value


def test_failed_metadata_binding_blocks_actual_profile_launch(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(notebook,'display_html',lambda *a:None)
    exc=common.ContextError('MULTIPLE_VERIFIED_FRESH_STATES_SET_STATE_DIR',{'states':[]})
    def fail(*a,**k):raise exc
    monkeypatch.setattr(notebook,'context',fail)
    monkeypatch.setattr(notebook.subprocess,'Popen',lambda *a,**k:pytest.fail('must not execute actual stage'))
    assert notebook.profile('load')['status']=='CONTEXT_UNRESOLVED'
