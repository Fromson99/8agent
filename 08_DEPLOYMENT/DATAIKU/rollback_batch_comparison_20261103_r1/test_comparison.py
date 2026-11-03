import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import types
import pytest

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'gold_fresh_1_20261102_r1/package'
sys.path.insert(0,str(HERE/'package'))
import g19cmp_core as core
import g19cmp_source as source
import g19cmp_worker as worker
import g19cmp_notebook as notebook
from g19cmp_common import canonical, read, write
spec=importlib.util.spec_from_file_location('comparison_test_loader',BASE/'run.py')
loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
from lawrag.pipeline import oracle_query_publish as pub
import jdbc_transport
from gold_io import Stop


def rows(n):
    return [loader.query_row('b'*64,pub.record('asset_fixture.unit',{'id':i,'text':"원문 😀 'COMMIT;' "+str(i)},key=i)) for i in range(n)]


def contract():return core.expanded_contract(loader.Contract,BASE/'contract.json')


@pytest.mark.parametrize('weights',[([400]*10000),([900]*10000),([3*1024**2,1,1]),([1]*5001)])
def test_same_partition_algorithm_and_exact_order(weights):
    for maxrows,maxbytes in core.POLICIES.values():
        spans=core.partitions(weights,maxrows,maxbytes)
        assert [i for a,b in spans for i in range(a,b)]==list(range(len(weights)))
        expected=[];batch=[];size=0
        for i,n in enumerate(weights):
            if batch and (len(batch)>=maxrows or size+n>maxbytes):expected.append(batch);batch=[];size=0
            batch.append(i);size+=n
        if batch:expected.append(batch)
        assert [list(range(a,b)) for a,b in spans]==expected


def test_full_contract_and_cross_chunk_rejections():
    c=contract();value=rows(10000);before=copy.deepcopy(value)
    sql,binds=c.batch('SRCH_ROW',value)
    assert len(json.loads(binds[0][1]))==10000 and value==before
    assert 'DBMS_LOB.COMPARE' in sql and 'ERROR ON ERROR' in sql
    with pytest.raises(ValueError):c.batch('SRCH_ROW',value+[value[0]])
    value[9999]=value[0]
    with pytest.raises(ValueError,match='DUPLICATE'):c.batch('SRCH_ROW',value)
    value=rows(5001);value[-1]['bad']='x'
    with pytest.raises(Stop,match='UNKNOWN_COLUMN'):c.batch('SRCH_ROW',value)


def test_only_release_changes_and_payload_preserves_unicode_sql_text():
    c=contract();original=rows(4);changed=core.isolated_rows(original,c,'c'*64)
    key=c.tables['SRCH_ROW']['primary_key'][0]
    assert [{k:v for k,v in r.items() if k!=key} for r in original]==[{k:v for k,v in r.items() if k!=key} for r in changed]
    sql,binds=c.batch('SRCH_ROW',changed);nonce='a'*32
    a=core.response_sql(sql,nonce,'normal');b=core.response_sql(sql,nonce,'exception')
    assert a.replace('IF 0 = 1 THEN','IF 1 = 1 THEN')==b
    compiled=core.payload_clock(jdbc_transport.render(a,binds,write=True))
    assert not re.search(r'\bCOMMIT\b',compiled)
    assert compiled.index('g19_transport_t0:=')<compiled.index('d0:=DBMS_UTILITY.GET_TIME')
    assert "COMMIT;" in binds[0][1] and '😀' in binds[0][1]


@pytest.mark.parametrize('mode',['same_rows','conflict','missing'])
def test_integrity_uses_installed_full_equality_and_no_commit(mode):
    original=rows(4);before=copy.deepcopy(original)
    sql,binds=core.integrity_sql(contract(),original,mode)
    compiled=jdbc_transport.render(sql,binds,write=True)
    assert 'COMMIT' not in compiled and 'DBMS_LOB.COMPARE' in sql and original==before
    assert len({n for n,v,t in binds})==len(binds)
    payloads=[json.loads(v) for n,v,t in binds if t=='CLOB']
    if mode=='same_rows':assert payloads[0]==payloads[1]
    if mode=='conflict':assert sum(a!=b for a,b in zip(payloads[0],payloads[1]))==1 and 'SQLCODE=-20042' in sql
    if mode=='missing':assert len(payloads[0])==3 and len(payloads[1])==4 and 'SQLCODE=-20042' in sql


@pytest.mark.parametrize('message',['ORA-01654: no space','ORA-20084: G19CMP_OK_'+'b'*32+' i=1 v=1 r=1 p=1','ORA-20084: G19CMP_OK_'+'a'*32+' i=1 v=1 r=1 p=1 ORA-00600','network unknown'])
def test_unexpected_or_wrong_receipt_rejected(message):
    assert core.receipt(Exception(message),'a'*32) is None


def test_receipt_and_sql_grammar_guard():
    assert core.receipt(Exception('ORA-20084: G19CMP_OK_'+'a'*32+' i=12 v=3 r=1 p=4\nORA-06512: at line 3'),'a'*32)['insert_db_s']==.12
    with pytest.raises(ValueError):core.response_sql('BEGIN COMMIT; END;','a'*32,'normal')
    with pytest.raises(ValueError):core.payload_clock('BEGIN NULL; END;')


def make_source(tmp_path,table='unit',n=10003):
    p=tmp_path/'source.sqlite'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE '+table+' (id INTEGER PRIMARY KEY, text TEXT)')
        db.executemany('INSERT INTO '+table+' VALUES(?,?)',[(i,'가나다 '+str(i)) for i in range(n)])
    kind=pub._kind('source.sqlite',table)
    ctx={'root':str(tmp_path),'state':{'binding':{'files':{'source.sqlite':'bound'},'query_release':'b'*64}},
        'descriptor':{'tables':{kind:{'asset':'source.sqlite','table':table,'rows':n}}}}
    return p,ctx,kind


def test_source_10000_distinct_matches_projection_weights_and_no_writes(tmp_path):
    p,ctx,kind=make_source(tmp_path);before=p.read_bytes()
    sampled,weights,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    original=[r for r in pub.asset_rows(p,'source.sqlite') if r['kind']==kind][:10000]
    assert sampled==[loader.query_row('b'*64,r) for r in original]
    assert len(sampled)==10000 and weights==[len(canonical(r).encode()) for r in original]
    assert meta['status']=='OK' and p.read_bytes()==before


def test_changed_source_and_active_journal_discard_all(tmp_path,monkeypatch):
    p,ctx,kind=make_source(tmp_path,n=4)
    journal=Path(str(p)+'-journal');journal.write_bytes(b'active')
    assert source.sample(ctx,loader,'SRCH_ROW',kind)[0]==[]
    journal.unlink();original=source.ordinary
    def change(*args):
        yield from original(*args)
        with sqlite3.connect(p) as db:db.execute("INSERT INTO unit VALUES(999,'new')")
    monkeypatch.setattr(source,'ordinary',change)
    sampled,weights,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert not sampled and not weights and meta['status']=='SOURCE_SAMPLE_UNMEASURED'


def test_fts_oversize_term_skipped_complete_positions_kept(tmp_path):
    p=tmp_path/'source.sqlite'
    with sqlite3.connect(p) as db:
        db.execute('CREATE VIRTUAL TABLE words USING fts5(body)')
        db.execute('INSERT INTO words VALUES(?)',(' '.join(['alpha']*4200+['beta','beta']),))
    kind=pub._kind('source.sqlite','words_posting')
    ctx={'root':str(tmp_path),'state':{'binding':{'files':{'source.sqlite':'bound'},'query_release':'b'*64}},
        'descriptor':{'tables':{kind:{'asset':'source.sqlite','table':'words_posting','rows':2}}}}
    before=p.read_bytes();sampled,weights,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert len(sampled)==1 and json.loads(sampled[0]['SRCH_DATA_CTNT'])['positions']==[4200,4201]
    assert meta['oversize_terms_skipped']==1 and p.read_bytes()==before


def setup_worker(tmp_path,monkeypatch,failure=None):
    import pandas as pd
    state={'status':'WRITE_UNCONFIRMED','pending':{'rows':2000,'sha256':'original'},'binding':{'code':'same','database':[{'LOGIN_USER':'PIDD2APP'}],'objects':['fixed']}}
    write(tmp_path/'state.json',state);before=(tmp_path/'state.json').read_bytes()
    kind='asset_fixture.unit';fixed=rows(6000);calls=[]
    fake=types.SimpleNamespace(__file__=str(BASE/'run.py'),Contract=loader.Contract,verify_code=lambda:'same',object_binding=lambda db,c:['fixed'])
    monkeypatch.setitem(sys.modules,'run',fake)
    monkeypatch.setattr(loader.Contract,'preflight',lambda *args:None)
    monkeypatch.setattr(worker,'KINDS',('unit',))
    monkeypatch.setattr(worker,'sample',lambda *args:(fixed,[400]*len(fixed),{'status':'OK','sample_rows':len(fixed)}))
    class Executor:
        def query_to_df(self,sql,**kw):
            if 'pre_queries' in kw:
                rendered=kw['pre_queries'][0];calls.append(rendered)
                assert not re.search(r'\b(COMMIT|DELETE|CREATE|ALTER|TRUNCATE)\b',rendered)
                assert kw['post_queries']==['ROLLBACK']
                if failure=='space':raise RuntimeError('ORA-01654: extent failure')
                if failure=='unknown':return pd.DataFrame({'OK':[0]})
                if failure=='state':write(tmp_path/'state.json',{**state,'changed':True})
                if 'IF 1 = 1 THEN' in rendered:
                    nonce=re.search('G19CMP_OK_([a-f0-9]{32})',rendered)[1]
                    raise RuntimeError('ORA-20084: G19CMP_OK_'+nonce+' i=1 v=2 r=0 p=1\nORA-06512: at line 5')
                return pd.DataFrame({'OK':[1]})
            if 'SYS_CONTEXT' in sql:return pd.DataFrame(state['binding']['database'])
            return pd.DataFrame({'N':[1 if failure=='residual' and calls else 0]})
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **kwargs:Executor()))
    ctx={'package':str(BASE),'state_dir':str(tmp_path),'state':state,'descriptor':{'tables':{kind:{'table':'unit','rows':100000}}}}
    worker.run({'context':ctx,'run_id':'test','plan_sha256':'fixed'},tmp_path/'result.json')
    return read(tmp_path/'result.json'),calls,before


def test_worker_complete_balanced_same_source_and_full_integrity(tmp_path,monkeypatch):
    result,calls,before=setup_worker(tmp_path,monkeypatch)
    assert result['status']=='COMPLETE' and result['original_state_unchanged']
    assert (tmp_path/'state.json').read_bytes()==before
    assert len(result['summaries'])==2 and all(p['complete_pairs']==3 for p in result['summaries'])
    assert all(p['status']=='ROLLED_BACK_VERIFIED' for p in result['integrity'])
    for phase in ('response','batch'):
        trials=[p for p in result['trials'] if p['phase']==phase]
        assert len({p['source_sha256'] for p in trials})==1
        assert trials[0]['arm']==trials[3]['arm']==trials[4]['arm']
    assert len(calls)==19


@pytest.mark.parametrize('failure',['space','unknown','residual','state'])
def test_worker_stops_first_failure_no_retry(tmp_path,monkeypatch,failure):
    result,calls,before=setup_worker(tmp_path,monkeypatch,failure)
    assert result['status'].startswith('STOPPED') and len(calls)==1
    if failure!='state':assert (tmp_path/'state.json').read_bytes()==before
    else:assert result['original_state_unchanged'] is False
    assert not result['summaries']


def test_summary_requires_three_pairs_and_exact_hash():
    values=[]
    for pair in range(3):
        for arm in ('normal','exception'):
            values.append({'kind':'unit','phase':'response','pair':pair,'arm':arm,'status':'ROLLED_BACK_VERIFIED',
                'source_sha256':'same','rows':10,'request_s':1 if arm=='normal' else 2,'elapsed_s':3,'batches':[{}]})
    assert core.summaries(values)[0]['median_right_over_left']==2
    assert core.summaries(values[:-1])[0]['median_right_over_left'] is None
    values[1]['source_sha256']='changed'
    with pytest.raises(ValueError):core.summaries(values)


def test_saved_pages_no_queries_and_escape(monkeypatch):
    monkeypatch.setattr(notebook,'display',lambda value:None)
    r={'status':'STOPPED','reason':'<script>','skipped':[],'queries':1}
    assert '&lt;script&gt;' in notebook.show('상태',r)
    for page in ('요약','응답','배치','정확성'):assert 'SQL/INSERT를 다시 실행하지 않습니다' in notebook.show(page,r)


def test_monitor_timeout_and_child_stop(tmp_path,monkeypatch):
    class Process:
        def __init__(self):self.returncode=None;self.terminated=False
        def poll(self):return self.returncode
        def terminate(self):self.terminated=True;self.returncode=-15
        def wait(self,timeout):return self.returncode
    p=Process();monkeypatch.setattr(notebook,'display',lambda v:None)
    monkeypatch.setattr(notebook.time,'monotonic',lambda:700)
    assert notebook.monitor(p,tmp_path/'none.json',0)=='CLIENT_TIMEOUT_DB_OUTCOME_UNCONFIRMED'
    notebook.stop_child(p);assert p.terminated and p.returncode==-15


def test_all_python_and_launch_support_field_python39():
    for p in [*HERE.glob('*.py'),* (HERE/'package').glob('*.py'),HERE/'01_RUN_RESPONSE_BATCH_CHECK_R1.txt']:
        ast.parse(p.read_text(),feature_version=(3,9))


@pytest.mark.parametrize('bad_zip',[False,True])
def test_actual_txt_zip_download_hash_extract_and_import(tmp_path,monkeypatch,bad_zip):
    import io
    import tempfile
    raw=(HERE/'G19_RESPONSE_BATCH_CHECK_20261103_R1.zip').read_bytes()
    if bad_zip:raw+=b'wrong bytes'
    class Folder:
        def list_paths_in_partition(self):return ['/G19_RESPONSE_BATCH_CHECK_20261103_R1.zip']
        def get_download_stream(self,path):return io.BytesIO(raw)
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda name:Folder()))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    code=(HERE/'01_RUN_RESPONSE_BATCH_CHECK_R1.txt').read_text().split('\ntry:\n    _g19_comparison =')[0]
    namespace={};modules={k:v for k,v in sys.modules.items() if k.startswith('g19cmp_')};paths=list(sys.path)
    try:
        exec(compile(code,'actual-mail-txt','exec'),namespace)
        if bad_zip:
            with pytest.raises(ValueError,match='ZIP_HASH'):namespace['_g19_diag_bootstrap']()
        else:
            mod=namespace['_g19_diag_bootstrap']()
            extracted=Path(mod.__file__).parent
            manifest=read(extracted/'MANIFEST.json')
            assert manifest['files'] and callable(mod.run)
            assert all(hashlib.sha256((extracted/n).read_bytes()).hexdigest()==sha for n,sha in manifest['files'].items())
    finally:
        for k in list(sys.modules):
            if k.startswith('g19cmp_'):sys.modules.pop(k)
        sys.modules.update(modules);sys.path[:]=paths


def test_parent_interrupt_preserves_partial_result_and_reconciliation_select(tmp_path,monkeypatch):
    state_dir=tmp_path/'state';state_dir.mkdir();write(state_dir/'state.json',{'pending':{'original':1}})
    ctx={'state_dir':str(state_dir),'contract':read(BASE/'contract.json')}
    monkeypatch.setattr(notebook,'context',lambda *a,**k:ctx)
    monkeypatch.setattr(notebook,'display',lambda value:None)
    monkeypatch.chdir(tmp_path)
    class Process:
        def __init__(self,args,**kwargs):
            self.returncode=None
            write(Path(args[-1]),{'status':'RUNNING','trials':[{'probe_release':'a'*64,'status':'PREPARING','phase':'response'}]})
        def poll(self):return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,timeout):return self.returncode
    monkeypatch.setattr(notebook.subprocess,'Popen',Process)
    def interrupt(*args):raise KeyboardInterrupt
    monkeypatch.setattr(notebook,'monitor',interrupt)
    result=notebook.run()
    assert result['status']=='USER_INTERRUPTED_DB_OUTCOME_UNCONFIRMED'
    assert result['db_cancellation_confirmed'] is False and result['original_state_unchanged'] is True
    sql=Path(result['reconciliation_select_file']).read_text()
    assert 'SELECT' in sql and 'COUNT(*)' in sql and 'DELETE' in sql.splitlines()[0] and 'DELETE' not in '\n'.join(sql.splitlines()[1:])
    assert read(Path(result['output']))==result
