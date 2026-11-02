from pathlib import Path
import json
import sys
import types
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from error_diagnostics import safe_message,event,banner,install


def test_nested_oracle_detail_retained_and_payload_hidden():
    inner=RuntimeError('ORA-12801: error signaled in parallel query server P003\nORA-01691: unable to extend lob segment SIDDS.SYS_LOB001 by 128 in tablespace TS_LOB\nSQL: INSERT SECRET_SOURCE_TEXT')
    outer=RuntimeError('Dataiku query failed');outer.__cause__=inner
    output=banner(event(outer,{'stage':'LOAD','table':'SIDDS.LGL_G19_DOC_BLK_S','batch_rows':1000}))
    assert 'SIDDS.SYS_LOB001' in output and 'TS_LOB' in output
    assert 'ORA-01691' in output and '1000' in output
    assert 'SECRET_SOURCE_TEXT' not in output


def test_credentials_removed(monkeypatch):
    monkeypatch.setenv('GENOS_EMBED_KEY','private-credential-123')
    result=safe_message(RuntimeError('HTTP failure private-credential-123 password=hunter2 Authorization: Bearer TOKEN'))
    assert 'private-credential' not in result and 'hunter2' not in result and 'TOKEN' not in result


def test_diagnostic_preserves_call_return_and_exception_identity(tmp_path,capsys):
    expected=RuntimeError('ORA-01691: unable to extend lob segment SIDDS.LOB1 by 128 in tablespace TS1')
    calls=[]
    class DB:
        def query(self,sql,limit=200):calls.append((sql,limit));return [{'N':7}]
        def block(self,sql,binds=(),rollback=False):
            calls.append((sql,binds,rollback));raise expected
    class Job:
        contract=types.SimpleNamespace(table=lambda k:'SIDDS.TARGET')
        def batch(self,key,rows,**kwargs):return DB().block('INSERT INTO SIDDS.TARGET VALUES(:payload)',[('payload','secret','CLOB')],rollback=True)
    loader=types.SimpleNamespace(Database=DB,Job=Job)
    path=tmp_path/'errors.jsonl';install(loader,path)
    assert DB().query('SELECT 7 FROM DUAL',limit=1)==[{'N':7}]
    with pytest.raises(RuntimeError) as info:Job().batch('X',[{}]*3,verify_only=True)
    assert info.value is expected
    assert calls==[('SELECT 7 FROM DUAL',1),('INSERT INTO SIDDS.TARGET VALUES(:payload)',[('payload','secret','CLOB')],True)]
    value=json.loads(path.read_text())
    assert value['context']=={'stage':'VERIFY','table':'SIDDS.TARGET','batch_rows':3}
    assert 'secret' not in path.read_text()
    assert 'ORA-01691' in capsys.readouterr().out


def test_diagnostic_disk_failure_does_not_mask_original(tmp_path,capsys):
    class DB:
        def query(self,sql):raise ValueError('original error')
        def block(self,*a,**k):pass
    loader=types.SimpleNamespace(Database=DB,Job=type('Job',(),{'batch':lambda *a,**k:None}))
    install(loader,tmp_path/'missing'/'errors.jsonl')
    with pytest.raises(ValueError,match='original error'):DB().query('SELECT 1')
    assert 'diagnostic_log_error' in capsys.readouterr().out


def test_failed_progress_disables_eta(tmp_path):
    from progress_display import Display
    path=tmp_path/'gold-shape-aaaaaaaaaaaa';path.mkdir()
    (path/'state.json').write_text(json.dumps({'status':'WRITE_UNCONFIRMED','source':{'x':{'rows':12}},'query':{}}))
    view=Display(tmp_path/'old','a'*64,'load');view.totals={'source':100,'query':200}
    assert '중단됨 — 예상 시간 계산 안 함' in view.render()


def test_actual_r1_entry_with_diagnostic_adapter(tmp_path):
    import subprocess
    here=Path(__file__).resolve().parent
    package=here.parent/'gold_shape_silver_20261102_r1/package'
    old=tmp_path/'old';old.mkdir()
    script='''import sys,types,os
sys.path.insert(0,sys.argv[1])
class Executor:
    def __init__(self,**kwargs):pass
    def query_to_df(self,*args,**kwargs):
        raise RuntimeError('ORA-01691: unable to extend lob segment SIDDS.SYS_LOB1 by 128 in tablespace TS_LOB')
sys.modules['dataiku']=types.SimpleNamespace(SQLExecutor2=Executor)
import diagnostic_runner
sys.argv=['diagnostic_runner.py',sys.argv[2],'load']
raise SystemExit(diagnostic_runner.main())
'''
    import os
    env=dict(os.environ,G19_OLD_JOB_DIR=str(old),G19_DIAGNOSTIC_FILE=str(tmp_path/'errors.jsonl'))
    result=subprocess.run([sys.executable,'-c',script,str(here),str(package)],env=env,capture_output=True,text=True)
    assert result.returncode==1,result.stderr
    assert 'TS_LOB' in result.stdout and 'DIAGNOSTIC_ERROR' in result.stdout
    assert 'ORA-01691' in (tmp_path/'errors.jsonl').read_text()


def test_final_notebook_keeps_error_beyond_18_lines(tmp_path,monkeypatch,capsys):
    import ast,collections,hashlib,io,os,subprocess,tempfile,zipfile
    from pathlib import PurePosixPath
    import progress_display
    here=Path(__file__).resolve().parent
    script=(here/'DATAIKU_GOLD_ALL_WITH_VECTOR_R3.txt').read_text()
    tree=ast.parse(script)
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_run_gold_shape')
    values={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Constant)}
    raw=(here.parent/'gold_shape_silver_20261102_r1'/values['ZIP_NAME']).read_bytes()
    folder=types.SimpleNamespace(list_paths_in_partition=lambda:[values['ZIP_NAME']],get_download_stream=lambda p:io.BytesIO(raw))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda n:folder))
    clears=[]
    monkeypatch.setitem(sys.modules,'IPython',types.ModuleType('IPython'))
    monkeypatch.setitem(sys.modules,'IPython.display',types.SimpleNamespace(clear_output=lambda **k:clears.append(1)))
    failure=event(RuntimeError('ORA-01691: unable to extend lob segment SIDDS.LOB1 in tablespace TS_LOB'),{'stage':'LOAD','table':'SIDDS.TARGET','batch_rows':999})
    process=types.SimpleNamespace(stdout=iter([json.dumps(failure)+'\n']+[json.dumps({'phase':'notice'+str(i)})+'\n' for i in range(25)]),wait=lambda:1)
    namespace=dict(vars(progress_display),collections=collections,hashlib=hashlib,io=io,json=json,os=os,
                   Path=Path,PurePosixPath=PurePosixPath,subprocess=types.SimpleNamespace(Popen=lambda *a,**k:process,PIPE=-1,STDOUT=-2),sys=sys,
                   tempfile=types.SimpleNamespace(gettempdir=lambda:str(tmp_path)),zipfile=zipfile,
                   helper_root=tmp_path,error_banner=banner)
    namespace.update(values)
    namespace['ACTION']='load'
    monkeypatch.chdir(tmp_path)
    exec(compile(ast.Module(body=[function],type_ignores=[]),'notebook-function','exec'),namespace)
    with pytest.raises(RuntimeError) as result:namespace['_run_gold_shape']()
    assert 'TS_LOB' in str(result.value) and 'SIDDS.TARGET' in str(result.value)
    assert clears==[]
    assert 'TS_LOB' in capsys.readouterr().out
