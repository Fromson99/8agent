import ast
import os
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import pytest

HERE = Path(__file__).resolve().parent
PACKAGE = Path(os.environ.get('R5_PACKAGE_DIR', HERE/'package'))
sys.path.insert(0, str(PACKAGE))
import native_transport as native
import run_full as loader
from gold_io import Contract, Database, Stop, digest
from transport_resume import migrate
from pipeline_entry import select_mode

class Progress:
    def emit(self, *a, **k): pass

@pytest.mark.parametrize('parent', json.loads((PACKAGE/'NATIVE_PARENTS.json').read_text())['parents'])
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
    prior=json.loads((PACKAGE/'NATIVE_PARENTS.json').read_text())['parents'][0]['code_binding']
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
    parents=json.loads((PACKAGE/'NATIVE_PARENTS.json').read_text())['parents']
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

@pytest.mark.parametrize('raw,expected', [('jdbc:oracle:thin:@//db.example:1521/svc','db.example:1521/svc'),('db:1521/svc','db:1521/svc'),('jdbc:oracle:thin:@db:1521:SID',('db',1521,'SID'))])
def test_dsn(raw,expected):
    driver=NS(makedsn=lambda h,p,sid:(h,p,sid))
    assert native.dsn_from_params({'jdbcURL':raw},driver,raw if not raw.startswith('jdbc:') else '')==expected

@pytest.mark.parametrize('raw',['user/pass@host:1521/svc','jdbc:oracle:oci:@db','host:0/s','host:65536/s','host:1521/s?password=secret','(DESCRIPTION=unsafe)','tcps://host:1521/s'])
def test_unsupported_dsn(raw):
    with pytest.raises(Stop):native.dsn_from_params({},NS(),raw)

@pytest.mark.parametrize('binds',[[('a',True,'NUMBER')],[('a','x'*4001,'VARCHAR2')],[('a','x\0y','CLOB')],[('b',1,'NUMBER')],[('a',1,'NUMBER'),('a',2,'NUMBER')]])
def test_invalid_binds(binds):
    with pytest.raises(Stop):native.validate_binds('BEGIN :a; END;',binds)


def test_bind_tokens_in_comments_and_literals_ignored():
    assert native.validate_binds("BEGIN -- :fake\n :a := ':not_bind'; /* :also_fake */ END;", [('a','text','CLOB')])=={'a':('text','CLOB')}


def test_credentials_exception_does_not_leak(monkeypatch):
    secret='private-sentinel-DO-NOT-LOG'
    def fail(*a,**k):raise RuntimeError(secret)
    monkeypatch.setitem(sys.modules,'dataiku',NS(api_client=fail))
    monkeypatch.setattr(native.importlib,'import_module',lambda n:NS())
    with pytest.raises(Stop) as caught:native.connect_checked(NS())
    from error_diagnostics import event
    assert secret not in json.dumps(event(caught.value))
    assert caught.value.__context__ is None


def test_execution_unknown_is_poisoned_and_sanitized(capsys):
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def setinputsizes(self,**k):pass
        def execute(self,*a):raise RuntimeError('ORA-03113: private-body-sentinel')
    conn=NS(cursor=Cursor,rollback=lambda:None)
    driver=NS(DB_TYPE_CLOB=1,DB_TYPE_NUMBER=2,DB_TYPE_VARCHAR=3)
    db=NS(native=conn,native_driver=driver,native_broken=False,calls=0)
    with pytest.raises(Stop) as caught:native.block(db,'BEGIN :payload; END;',[('payload','source-secret','CLOB')])
    from error_diagnostics import event
    log=json.dumps(event(caught.value))+capsys.readouterr().out
    assert 'ORA-03113' in log and 'private-body-sentinel' not in log and 'source-secret' not in log
    with pytest.raises(Stop,match='RESTART_REQUIRED'):native.block(db,'BEGIN NULL; END;')
    assert db.calls==1



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
