import ast
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import re
import sys
import types
import zipfile
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
import jdbc_transport as transport
import run as runner
import transport_resume
import transport_gate
from gold_io import Contract, Stop, canonical, digest


def old_module(name):
    path=HERE.parent/'gold_fresh_1_20261102_r1/package'/(name+'.py')
    spec=importlib.util.spec_from_file_location('r1_'+name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def unpack(sql):
    pieces=re.findall(r"DBMS_LOB.WRITEAPPEND\(g8_zip_0,(\d+),UTL_ENCODE.BASE64_DECODE\(UTL_RAW.CAST_TO_RAW\('([A-Za-z0-9+/=]+)'\)\)\);",sql)
    if pieces:
        raw=[]
        for count,text in pieces:
            data=base64.b64decode(text,validate=True)
            assert len(text)<=3600 and len(data)==int(count)
            raw.append(data)
        return gzip.decompress(b''.join(raw)).decode('utf-8')
    chunks=re.findall(r"DBMS_LOB.APPEND\(g8_lob_0,TO_CLOB\(UTL_I18N.RAW_TO_CHAR\(HEXTORAW\('([0-9A-F]+)'\),'AL32UTF8'\)\)\);",sql)
    return b''.join(bytes.fromhex(x) for x in chunks).decode('utf-8')


@pytest.mark.parametrize('value',['',"'\\\n\t:payload -- /* SQL */ 한글𠀀😀",'x'*32768,'x'*32769,('a'*1798+'𠀀한')*600])
def test_complete_wire_reconstructs_exact_text_at_encoding_boundaries(value):
    sql=transport.render('BEGIN consume(:payload); END;',[('payload',value,'CLOB')],write=True)
    assert unpack(sql)==value
    assert sql.isascii()
    assert 'consume(g8_lob_0);' in sql


def test_many_compressed_chunks_roundtrip_and_lob_lifetime_order():
    rng=random.Random(12345)
    value=''.join(rng.choice('abcABC012한글😀𠀀\\\n\t\'') for _ in range(120000))
    sql=transport.render('BEGIN consume(:payload); END;',[('payload',value,'CLOB')],write=True)
    assert unpack(sql)==value
    assert sql.count('UTL_ENCODE.BASE64_DECODE')>10
    assert sql.index('LZ_UNCOMPRESS')<sql.index('FREETEMPORARY(g8_zip_0)')<sql.index('CONVERTTOCLOB')
    assert sql.index('CONVERTTOCLOB')<sql.index('FREETEMPORARY(g8_raw_0)')<sql.index('consume(g8_lob_0)')
    assert sql.index('consume(g8_lob_0)')<sql.index('FREETEMPORARY(g8_lob_0)')
    assert 'DBMS_LOB.CALL' in sql
    handler=sql.split('EXCEPTION WHEN OTHERS THEN')[-1]
    for name in ('g8_lob_0','g8_zip_0','g8_raw_0'):assert 'ISTEMPORARY('+name+')' in handler


def test_original_dml_and_all_contract_data_are_unchanged():
    original=HERE.parent/'gold_fresh_1_20261102_r1/package'
    assert (HERE/'package/contract.json').read_bytes()==(original/'contract.json').read_bytes()
    current=ast.parse((HERE/'package/gold_io.py').read_text())
    previous=ast.parse((original/'gold_io.py').read_text())
    methods=lambda t:{n.name:ast.dump(n,include_attributes=False) for c in t.body if isinstance(c,ast.ClassDef) and c.name=='Contract' for n in c.body if isinstance(n,ast.FunctionDef)}
    assert methods(current)['batch']==methods(previous)['batch']
    assert ast.dump(next(n for n in ast.parse((HERE/'package/run.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='grouped'))==ast.dump(next(n for n in ast.parse((original/'run.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='grouped'))
    prior=json.loads((HERE/'package/PREDECESSOR.json').read_text())
    assert prior['code_binding']==digest(json.loads((original/'CODE_MANIFEST.json').read_text()))


@pytest.mark.parametrize('statement,binds',[('BEGIN x(:x); END;',[('x','q','UNKNOWN')]),('BEGIN x(:x); END;',[('x',True,'NUMBER')]),('BEGIN x(:x); END;',[('x','a\0','CLOB')]),('BEGIN x(:x); END;',[]),('BEGIN x(:x); END;',[('x','q','CLOB'),('x','q','CLOB')]),('BEGIN NULL; END;',[('x','q','CLOB')])])
def test_bad_binds_stop_before_transport(statement,binds):
    with pytest.raises(ValueError):transport.render(statement,binds,write=True)


def test_literals_comments_and_numeric_varchar_bind_semantics_unchanged():
    statement="BEGIN x(:n,:text); x(':n'); -- :ignored\n /* :other */ END;"
    binds=[('n',123,'NUMBER'),('text',"'😀한\\",'VARCHAR2')]
    assert transport.render(statement,binds,write=True)==old_module('jdbc_transport').render(statement,binds,write=True)


class Progress:
    def __init__(self):self.events=[]
    def emit(self,*a,**k):self.events.append((a,k))
    def set(self,*a,**k):self.events.append((a,k))


def state_fixture(tmp_path):
    prior=runner.read(HERE/'package/PREDECESSOR.json')
    binding={'code':prior['code_binding'],'contract':prior['contract_sha256'],'database':[{'DB':'same'}],'files':{'source':'hash'}}
    state={'binding':binding,'deadline':123456789,'status':'WRITE_UNCONFIRMED','source':{'doc':{'rows':101}},'query':{'a':{'rows':12}},'pending':{'sha256':'uncertain','rows':20},'verify_source':{},'verify_query':{},'last_error':{'codes':['ORA-01654']}}
    runner.atomic(tmp_path/'state.json',state)
    return state,{**binding,'code':runner.verify_code()}


def test_r1_checkpoint_migration_and_repeat_preserve_unknown_write_and_offsets(tmp_path):
    state,binding=state_fixture(tmp_path);path=tmp_path/'state.json'
    result=transport_resume.migrate(runner,path,state,binding,Progress())
    assert {k:v for k,v in result.items() if k not in ('binding','code_transitions')}=={k:v for k,v in state.items() if k!='binding'}
    backups=list(tmp_path.glob('state-before-r3-*.json'));assert len(backups)==1
    assert runner.read(backups[0])==state
    assert transport_resume.migrate(runner,path,result,binding,Progress())==result


@pytest.mark.parametrize('change',['code','files','database','contract','vectors'])
def test_unregistered_binding_or_started_vectors_never_mutates_checkpoint(tmp_path,change):
    state,binding=state_fixture(tmp_path)
    if change=='vectors':
        p=tmp_path/'vectors'/'some';p.mkdir(parents=True);(p/'state.json').write_text('{}')
    elif change=='code':state['binding']['code']='not-registered';runner.atomic(tmp_path/'state.json',state)
    else:binding[change]='changed'
    before=(tmp_path/'state.json').read_bytes()
    with pytest.raises(Stop):transport_resume.migrate(runner,tmp_path/'state.json',state,binding,Progress())
    assert (tmp_path/'state.json').read_bytes()==before and not list(tmp_path.glob('state-before-r3-*'))


@pytest.mark.parametrize('saved',['present','missing','unknown'])
def test_pending_result_is_verified_and_never_blindly_reinserted(tmp_path,monkeypatch,saved):
    state,binding=state_fixture(tmp_path)
    rows=[{'a':'한글'}];marker={'table':'X','rows':1,'sha256':digest(rows),'verify_only':False,'section':'query','slot':'a','next':{'rows':13}}
    state['binding']=binding;state['pending']=marker;runner.atomic(tmp_path/'state.json',state)
    calls=[]
    def block(sql,binds,rollback=False):
        calls.append((sql,rollback))
        if saved=='missing':raise RuntimeError('ORA-20042: missing or conflict')
        if saved=='unknown':raise RuntimeError('ORA-03113: unknown')
        return 0
    db=types.SimpleNamespace(block=block)
    contract=types.SimpleNamespace(batch=lambda k,r,verify_only=False:('VERIFY' if verify_only else 'INSERT',[]),table=lambda k:k)
    job=runner.Job(db,contract,tmp_path,binding,Progress());monkeypatch.setattr(job,'guard',lambda:None)
    if saved=='present':
        job.batch('X',rows,{'rows':13},'query','a');assert job.state['pending'] is None
    else:
        with pytest.raises(Stop,match='RECONCILIATION'):job.batch('X',rows,{'rows':13},'query','a')
        assert job.state['pending']==marker and job.state['query']['a']['rows']==12
    assert calls==[('VERIFY',True)]


def test_native_gate_has_no_target_sql_and_independent_reference():
    calls=[];transport_gate.check(types.SimpleNamespace(block=lambda *a,**k:calls.append((a,k))))
    (sql,binds),kwargs=calls[0]
    rendered=transport.render(sql,binds,write=True)
    assert unpack(rendered)==binds[0][1]
    assert len(binds[0][1].encode())>32768 and kwargs=={'rollback':True}
    assert 'DBMS_LOB.COMPARE' in sql and not re.search(r'\b(INSERT|DELETE|UPDATE|CREATE|ALTER|DROP)\b',sql)


def test_no_checkpoint_refuses_resume_before_connect(tmp_path,monkeypatch):
    old=tmp_path/'old';old.mkdir()
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:pytest.fail('unexpected connection')))
    with pytest.raises(Stop,match='EXISTING_R1_CHECKPOINT'):runner.run('load',old)


def test_missing_table_never_creates_during_resume():
    contract=Contract(HERE/'package/contract.json');calls=[]
    class DB:
        def query(self,sql):return [{'N':2}] if 'VECTOR_DIMENSION_COUNT' in sql else []
        def block(self,*a,**k):pytest.fail('DDL attempted')
    with pytest.raises(Stop,match='RESUME_TABLE_MISSING'):contract.create(DB(),lambda *a,**k:None,allow_create=False)


def test_package_zip_and_python39():
    with zipfile.ZipFile(HERE/'DATAIKU_GOLD_FRESH_1_TRANSPORT_20261103_R3.zip') as archive:
        manifest=json.loads(archive.read('CODE_MANIFEST.json'))
        assert set(archive.namelist())==set(manifest['files'])|{'CODE_MANIFEST.json'}
        for name,sha in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==sha
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.zip'}
    for name in ('jdbc_transport','run','transport_resume','transport_gate','pipeline_entry','gold_io'):
        ast.parse((HERE/'package'/(name+'.py')).read_text(),feature_version=(3,9))


@pytest.mark.parametrize('failed',[False,True])
def test_complete_attachment_bootstrap_loads_once_without_model_or_verify(tmp_path,monkeypatch,failed):
    import subprocess,tempfile
    script=(HERE/'DATAIKU_GOLD_FRESH_1_RUN_R3.txt').read_text()
    raw=(HERE/'DATAIKU_GOLD_FRESH_1_TRANSPORT_20261103_R3.zip').read_bytes()
    folder=types.SimpleNamespace(list_paths_in_partition=lambda:['DATAIKU_GOLD_FRESH_1_TRANSPORT_20261103_R3.zip'],get_download_stream=lambda p:io.BytesIO(raw))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda n:folder))
    monkeypatch.setitem(sys.modules,'IPython',types.ModuleType('IPython'))
    monkeypatch.setitem(sys.modules,'IPython.display',types.SimpleNamespace(clear_output=lambda **k:None))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path));monkeypatch.chdir(tmp_path)
    actions=[]
    def spawn(args,**kwargs):
        actions.append(args[-1]);assert Path(args[-2]).name=='pipeline_entry.py'
        assert 'G19_RETRY_MISSING' not in kwargs['env']
        reader,writer=os.pipe();os.write(writer,b'{"phase":"TEST"}\n');os.close(writer)
        return types.SimpleNamespace(stdout=os.fdopen(reader,'rb'),wait=lambda **k:1 if failed else 0,poll=lambda:1 if failed else 0)
    monkeypatch.setattr(subprocess,'Popen',spawn)
    if failed:
        with pytest.raises(RuntimeError):exec(compile(script,'attachment.txt','exec'),{})
    else:exec(compile(script,'attachment.txt','exec'),{})
    assert actions==['load']


@pytest.mark.parametrize('gate_failure',[False,True])
def test_real_pipeline_entry_calls_resume_gate_and_load_only(tmp_path,monkeypatch,gate_failure):
    import pandas as pd
    import pipeline_entry
    import error_diagnostics
    old=tmp_path/'old';old.mkdir()
    sha=Contract(HERE/'package/contract.json').sha256
    directory=old.parent/('gold-shape-'+sha[:12]);directory.mkdir()
    prior=runner.read(HERE/'package/PREDECESSOR.json')
    identity=[{'LOGIN_USER':'PIDD2APP','DB_NAME':'MOCK','SERVICE_NAME':'MOCK'}]
    objects=[{'OWNER':'SIDDS','OBJECT_NAME':'MOCK_1','OBJECT_ID':1,'DATA_OBJECT_ID':1}]
    binding={'code':prior['code_binding'],'contract':sha,'database':identity,'objects':objects,'generation':str(tmp_path),'files':{},'source_release':digest({}),'query_release':digest({})}
    state={'binding':binding,'deadline':9999999999,'status':'LOADING','source':{},'query':{},'verify_source':{},'verify_query':{},'pending':None,'phase':'LOAD'}
    runner.atomic(directory/'state.json',state);before=(directory/'state.json').read_bytes()
    events=[];sqls=[]
    class FakeContract:
        sha256=sha
        value={'physical_suffix':'_1'}
        tables={'ONE':{'name':'MOCK_1','owner':'SIDDS'}}
        def __init__(self,*a):pass
        def create(self,db,emit,*,allow_create):assert allow_create is False;events.append('readonly_schema')
        def probe(self,*a):pytest.fail('old per-table INSERT probe')
    class Executor:
        def query_to_df(self,sql,**kwargs):
            sqls.append((sql,kwargs))
            if kwargs.get('pre_queries'):
                assert 'BASE64_DECODE' in kwargs['pre_queries'][0]
                assert kwargs['post_queries']==['ROLLBACK']
                events.append('codec_roundtrip')
                if gate_failure:raise RuntimeError('ORA-06550: codec not available')
                return pd.DataFrame([{'OK':1}])
            return pd.DataFrame(identity if 'SYS_CONTEXT' in sql else objects)
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:Executor()))
    monkeypatch.setattr(runner,'Contract',FakeContract)
    monkeypatch.setattr(runner,'inputs',lambda *a:(tmp_path,{}, {},{},{}))
    monkeypatch.setattr(runner,'load_sources',lambda *a,**k:events.append(('sources',k['verify_only'])))
    monkeypatch.setattr(runner,'load_query',lambda *a,**k:events.append(('query',k['verify_only'])))
    monkeypatch.setattr(runner,'publish',lambda *a:pytest.fail('automatic full verify/publish'))
    monkeypatch.setattr(error_diagnostics,'install',lambda *a:lambda *a,**k:None)
    monkeypatch.setenv('G19_OLD_JOB_DIR',str(old));monkeypatch.setenv('G19_DIAGNOSTIC_FILE',str(tmp_path/'errors.jsonl'))
    monkeypatch.setattr(sys,'argv',['pipeline_entry.py','load'])
    # Restore the class after install() so this test does not change other tests.
    monkeypatch.setattr(runner.Database,'block',runner.Database.block)
    monkeypatch.setattr(runner.Database,'_g8_transport',False,raising=False)
    assert pipeline_entry.main()==(1 if gate_failure else 0)
    current=runner.read(directory/'state.json')
    if gate_failure:
        assert (directory/'state.json').read_bytes()==before
        assert not list(directory.glob('state-before-r3-*'))
        assert events==['readonly_schema','codec_roundtrip']
    else:
        assert events==['readonly_schema','codec_roundtrip',('sources',False),('query',False)]
        assert current['status']=='LOADED_UNVERIFIED' and current['binding']['code']==runner.verify_code()
        assert current['deadline']==state['deadline']
        assert runner.read(next(directory.glob('state-before-r3-*')))==state
