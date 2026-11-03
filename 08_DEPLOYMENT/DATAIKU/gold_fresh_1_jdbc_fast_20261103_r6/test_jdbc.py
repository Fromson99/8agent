import ast
import copy
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import pytest
HERE=Path(__file__).resolve().parent
PACKAGE=Path(os.environ.get('R6_PACKAGE_DIR',HERE/'package'))
sys.path.insert(0,str(PACKAGE))
import run_full as loader
import jdbc_transport as jdbc
from gold_io import Contract,Database,Stop,digest
from transport_resume import migrate
from pipeline_entry import select_mode


class Progress:
    def emit(self, *a, **k): pass

@pytest.mark.parametrize('parent', json.loads((PACKAGE/'RESUME_PARENTS.json').read_text())['parents'])
def test_migrate_preserves_checkpoint(tmp_path, parent):
    binding={'code':parent['code_binding'],'contract':'fixed','database':['fixed'],'query_release':'unchanged'}
    if parent['mode']=='reduced': binding['projection_policy']='unchanged'
    state={'binding':binding,'deadline':time.time()+3600,'source':{'d':{'rows':444}},'query':{'a':{'rows':5000}},
           'verify_source':{'d':{'rows':100}},'verify_query':{},'pending':{'uncertain':'preserve'},'status':'WRITE_UNCONFIRMED',
           'arbitrary_extension':{'keep':True}}
    path=tmp_path/'state.json';loader.atomic(path,state)
    new=dict(binding,code='r5')
    result=migrate(loader,path,state,new,Progress())
    assert {k:v for k,v in result.items() if k not in {'binding','code_transitions'}} == {k:v for k,v in state.items() if k!='binding'}
    assert loader.read(tmp_path/result['code_transitions'][-1]['backup'])==state
    assert migrate(loader,path,result,new,Progress())==result

@pytest.mark.parametrize('change', ['data','unknown_code','vector'])
def test_migration_refusal_no_mutation(tmp_path, change):
    prior=json.loads((PACKAGE/'RESUME_PARENTS.json').read_text())['parents'][0]['code_binding']
    state={'binding':{'code':prior,'query_release':'q'},'deadline':time.time()+100}
    if change=='unknown_code':state['binding']['code']='unregistered'
    new=dict(state['binding'],code='r5')
    if change=='data':new['query_release']='other'
    if change=='vector':
        (tmp_path/'vectors/v').mkdir(parents=True);(tmp_path/'vectors/v/state.json').write_text('{}')
    path=tmp_path/'state.json';loader.atomic(path,state);before=path.read_bytes()
    with pytest.raises(Stop):migrate(loader,path,state,new,Progress())
    assert path.read_bytes()==before and not list(tmp_path.glob('state-before*'))

def test_auto_mode_preserves_selected_release(tmp_path):
    old=tmp_path/'old';old.mkdir()
    full=tmp_path/('gold-shape-'+Contract(PACKAGE/'contract.json').sha256[:12]);full.mkdir()
    parents=json.loads((PACKAGE/'RESUME_PARENTS.json').read_text())['parents']
    loader.atomic(full/'state.json',{'binding':{'code':parents[1]['code_binding']}})
    assert select_mode(old,PACKAGE)==('full',full)
    reduced=full.with_name(full.name+'-reduced-r4');reduced.mkdir()
    loader.atomic(reduced/'state.json',{'binding':{'code':parents[2]['code_binding'],'projection_policy':'v1'}})
    assert select_mode(old,PACKAGE)==('reduced',reduced)
    loader.atomic(reduced/'state.json',{'binding':{'code':'unknown'}})
    with pytest.raises(Stop):select_mode(old,PACKAGE)

def test_mapping_and_schema_stay_unchanged():
    base=HERE.parent/'gold_fresh_1_transport_20261103_r3/package'
    for name in ('contract.json','legacy_gold_mapping.py'):
        assert (PACKAGE/name).read_bytes()==(base/name).read_bytes()

def test_sql_shape_independent_of_payload():
    from fast_insert import Contract as FastContract
    contract=FastContract(PACKAGE/'contract.json')
    row={'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc','DOC_NAME':'법령','DOC_HASH_VALU':'b'*64,'DOC_ADDN_IFMN_CTNT':'본문'}
    a,b=contract.batch('DOC_VER',[row]);c,d=contract.batch('DOC_VER',[dict(row,DOC_ID='other',DOC_ADDN_IFMN_CTNT='한글😀'*20000)])
    assert a==c and b!=d and ':payload' in a and '한글' not in a
    assert all(token not in a for token in ('COUNT(', 'DBMS_LOB.COMPARE', 'NOT EXISTS', ':expected'))

@pytest.mark.parametrize('present,expected',[(1,0),(0,1),(2,None)])
def test_pending_reconciliation_only_on_interruption(tmp_path,monkeypatch,present,expected):
    import fast_loader as fast
    class FakeContract:
        def batch(self,k,r,**kw):return 'INSERT_ONLY',[]
        def table(self,k):return k
        def pending_count(self,*a):return present
    calls=[]
    db=NS(block=lambda s,b,**kw:(calls.append(s) or 0.1))
    binding={'code':'same'}
    state={'binding':binding,'deadline':0,'source':{},'query':{},'verify_source':{},'verify_query':{},'pending':None}
    rows=[{'x':1}];nxt={'rows':1}
    state['pending']={'table':'T','rows':1,'sha256':digest(rows),'verify_only':False,'section':'query','slot':'s','next':nxt}
    loader.atomic(tmp_path/'state.json',state)
    monkeypatch.setattr(loader,'resource_check',lambda p:None)
    progress=NS(emit=lambda *a,**k:None,set=lambda *a,**k:None)
    job=fast.Job(db,FakeContract(),tmp_path,binding,progress)
    if expected is None:
        with pytest.raises(Stop):job.batch('T',rows,next_progress=nxt,section='query',slot='s')
        assert job.state['pending']==state['pending'] and calls==[]
    else:
        job.batch('T',rows,next_progress=nxt,section='query',slot='s')
        assert len(calls)==expected and job.state['pending'] is None and job.state['query']['s']==nxt

def test_normal_batch_has_no_pre_or_post_select(tmp_path,monkeypatch):
    import fast_loader as fast
    from fast_insert import Contract as FastContract
    db=NS(block=lambda s,b,**kw:0.1)
    contract=FastContract(PACKAGE/'contract.json')
    monkeypatch.setattr(contract,'pending_count',lambda *a:pytest.fail('normal batch must not check existence'))
    monkeypatch.setattr(loader,'resource_check',lambda p:None)
    binding={'code':'same'}
    loader.atomic(tmp_path/'state.json',{'binding':binding,'deadline':0,'source':{},'query':{},'pending':None})
    job=fast.Job(db,contract,tmp_path,binding,NS(emit=lambda *a,**k:None,set=lambda *a,**k:None))
    row={'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc','DOC_NAME':'법령','DOC_HASH_VALU':'b'*64,'DOC_ADDN_IFMN_CTNT':'본문'}
    job.batch('DOC_VER',[row],next_progress={'rows':1},section='source',slot='document')
    assert job.state['source']['document']=={'rows':1}

def test_failed_insert_keeps_pending_without_automatic_retry(tmp_path,monkeypatch):
    import fast_loader as fast
    from fast_insert import Contract as FastContract
    calls=[]
    def fail(*a,**k):calls.append(1);raise Stop('ORA-01654')
    monkeypatch.setattr(loader,'resource_check',lambda p:None)
    binding={'code':'same'}
    loader.atomic(tmp_path/'state.json',{'binding':binding,'source':{},'query':{},'pending':None})
    job=fast.Job(NS(block=fail),FastContract(PACKAGE/'contract.json'),tmp_path,binding,Progress())
    row={'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc','DOC_NAME':'법령','DOC_HASH_VALU':'b'*64,'DOC_ADDN_IFMN_CTNT':'본문'}
    with pytest.raises(Stop):job.batch('DOC_VER',[row],next_progress={'rows':1},section='source',slot='document')
    saved=loader.read(tmp_path/'state.json')
    assert saved['pending']['rows']==1 and saved['source']=={} and saved['status']=='WRITE_UNCONFIRMED' and len(calls)==1

def test_existing_dataiku_only_no_driver_credentials_or_direct_connect(monkeypatch):
    import builtins
    original=builtins.__import__
    def checked_import(name,*a,**kw):
        if name in {'oracledb','cx_Oracle','dataikuapi'}:pytest.fail('new driver/credential API imported: '+name)
        return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',checked_import)
    statements=[]
    class Frame:
        iloc=[{'OK':1}]
        def __len__(self):return 1
    class Executor:
        def query_to_df(self,sql,**kw):statements.append((sql,kw));return Frame()
    class DB(Database):pass
    jdbc.install(NS(Database=DB))
    db=DB(Executor())
    db.block('BEGIN NULL; COMMIT; END;',transaction_managed=True)
    db.close()
    assert statements==[('SELECT 1 AS OK FROM DUAL',{'pre_queries':['BEGIN NULL; COMMIT; END;'],'post_queries':[]})]
    assert db.last_transport['mode']=='DATAIKU_JDBC_LITERAL' and db.last_transport['native_binds'] is False


def test_pending_pk_only_query_escapes_payload():
    from fast_insert import Contract as FastContract
    queries=[]
    def query(sql):queries.append(sql);return [{'N':1}]
    contract=FastContract(PACKAGE/'contract.json')
    row={'MNFST_HASH_VALU':'a'*64,'DOC_ID':"quote'한글"}
    assert contract.pending_count(NS(query=query),'DOC_VER',[row])==1
    assert "quote'한글" not in queries[0] and ':payload' not in queries[0]
    assert 'JSON_TABLE' in queries[0] and 'DBMS_LOB.COMPARE' not in queries[0]


def test_real_entry_imports_without_oracledb_in_fresh_process(tmp_path):
    import subprocess
    code='''import sys
class Block:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'oracledb','cx_Oracle','dataikuapi','native_transport'}:
            raise AssertionError('unexpected dependency '+fullname)
sys.meta_path.insert(0,Block())
import pipeline_entry,run_full,fast_loader,jdbc_transport
jdbc_transport.install(run_full)
run_full.verify_code()
print('DATAIKU_ONLY_IMPORT_PASS')
'''
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
    result=subprocess.run([sys.executable,'-c',code],cwd=PACKAGE,env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert 'DATAIKU_ONLY_IMPORT_PASS' in result.stdout
