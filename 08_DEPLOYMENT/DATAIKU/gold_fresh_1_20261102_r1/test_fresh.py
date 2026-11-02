import ast
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import types
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
from gold_io import Contract,digest
import run as runner


def test_suffix_changes_only_physical_names_not_columns_pk_or_indexes():
    old=json.loads((HERE.parent/'gold_shape_silver_20261102_r1/package/contract.json').read_text())
    new=json.loads((HERE/'package/contract.json').read_text())
    rename=json.loads((HERE/'RENAME_MAP.json').read_text())
    old_contract=Contract(HERE.parent/'gold_shape_silver_20261102_r1/package/contract.json')
    new_contract=Contract(HERE/'package/contract.json')
    assert old_contract.sha256!=new_contract.sha256 and len(new['tables'])==17
    for key,t in new['tables'].items():
        previous=old['tables'][key]
        assert t['name']==previous['name']+'_1' and t['owner']==previous['owner']
        for field in ('columns','primary_key','indexes','group'):assert t[field]==previous[field]
        expected=old_contract.ddl(key)
        # For generated DDL, the suffix follows the generated table-based PK name too.
        for n in sorted(rename,key=len,reverse=True):expected=re.sub(r'\b'+re.escape(n)+r'\b',rename[n],expected)
        expected=expected.replace('X0_'+previous['name']+' PRIMARY','X0_'+previous['name']+'_1 PRIMARY')
        assert new_contract.ddl(key)==expected
        for ddl in new_contract.indexes(key):
            assert re.search(r'CREATE INDEX \w+\.(\w+)',ddl)[1].endswith('_1')
            assert ' ON '+new_contract.table(key)+' ' in ddl


def test_fresh_entry_has_no_reset_delete_or_table_lock():
    for filename in ('run.py','gold_io.py','pipeline_entry.py','vector_stage.py'):
        text=(HERE/'package'/filename).read_text()
        assert 'LOCK TABLE ' not in text and 'DELETE FROM ' not in text and 'TRUNCATE TABLE ' not in text
    assert not (HERE/'package/reset_source.py').exists()
    assert 'reset_if_needed' not in (HERE/'package/pipeline_entry.py').read_text()


def test_old_state_is_separate_and_untouched(tmp_path):
    old=Contract(HERE.parent/'gold_shape_silver_20261102_r1/package/contract.json')
    new=Contract(HERE/'package/contract.json')
    previous=tmp_path/('gold-shape-'+old.sha256[:12]);previous.mkdir()
    (previous/'state.json').write_text('prior failed checkpoint')
    fresh=tmp_path/('gold-shape-'+new.sha256[:12]);fresh.mkdir()
    job=runner.Job(None,new,fresh,{'new':True},types.SimpleNamespace())
    assert job.state['status']=='NEW' and job.state['source']=={} and job.state['pending'] is None
    assert (previous/'state.json').read_text()=='prior failed checkpoint'


def test_same_fresh_contract_resumes_checkpoint(tmp_path):
    c=Contract(HERE/'package/contract.json')
    job=runner.Job(None,c,tmp_path,{'fresh':True},types.SimpleNamespace())
    job.state['source']={'document':{'rows':123}};job.save()
    again=runner.Job(None,c,tmp_path,{'fresh':True},types.SimpleNamespace())
    assert again.state['source']=={'document':{'rows':123}}


def test_bootstrap_uses_one_zip_and_sequential_load_verify_vector():
    text=(HERE/'DATAIKU_GOLD_FRESH_1_RUN_R1.txt').read_text()
    ast.parse(text)
    assert "for action in ('load','verify_publish','vector')" in text
    assert "'legal-gold-fresh-1-'" in text and 'HELPER_ZIP_NAME' not in text
    assert 'gold_restart' not in text


def test_nonempty_existing_suffix_without_checkpoint_stops_before_inputs(tmp_path,monkeypatch):
    old=tmp_path/'old';old.mkdir();events=[]
    class C:
        sha256='f'*64;tables={'DOC':{}}
        def __init__(self,path):pass
        def create(self,*args):pass
        def table(self,key):return 'SIDDS.TEST_1'
        def probe(self,*args):return 0
    class DB:
        def __init__(self,e):pass
        def query(self,sql):
            return [{'LOGIN_USER':'PIDD2APP'}] if 'SYS_CONTEXT' in sql else [{'N':1}]
    monkeypatch.setattr(runner,'Contract',C);monkeypatch.setattr(runner,'Database',DB)
    monkeypatch.setattr(runner,'verify_code',lambda:'code')
    monkeypatch.setattr(runner,'inputs',lambda *a:events.append('inputs'))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:None))
    with pytest.raises(Exception,match='NEW_SUFFIX_TABLE_ALREADY_HAS_ROWS'):runner.run('load',old)
    assert events==[]


@pytest.mark.parametrize('fail_first',[False,True])
def test_complete_notebook_bootstrap_runs_stages_or_stops_on_error(tmp_path,monkeypatch,fail_first):
    import io,os,subprocess,tempfile
    script=(HERE/'DATAIKU_GOLD_FRESH_1_RUN_R1.txt').read_text()
    tree=ast.parse(script)
    constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
               and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Constant)}
    raw=(HERE/constants['ZIP_NAME']).read_bytes()
    folder=types.SimpleNamespace(list_paths_in_partition=lambda:[constants['ZIP_NAME']],get_download_stream=lambda p:io.BytesIO(raw))
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda n:folder,
        get_custom_variables=lambda:{'LEGAL_EMBED_LLM_ID':'test-model','LEGAL_EMBED_DIMENSIONS':1024}))
    monkeypatch.setitem(sys.modules,'IPython',types.ModuleType('IPython'))
    monkeypatch.setitem(sys.modules,'IPython.display',types.SimpleNamespace(clear_output=lambda **k:None))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path));monkeypatch.chdir(tmp_path)
    actions=[]
    def spawn(args,**kwargs):
        actions.append(args[-1])
        assert Path(args[-2]).name=='pipeline_entry.py'
        assert kwargs['env']['LEGAL_EMBED_DIMENSIONS']=='1024'
        reader,writer=os.pipe()
        value={'phase':'DIAGNOSTIC_ERROR','context':{'stage':'CREATE'},'causes':[{'type':'Exception','message':'ORA-01031: insufficient privileges'}]} if fail_first else {'phase':'TEST_OK'}
        os.write(writer,(json.dumps(value)+'\n').encode());os.close(writer)
        return types.SimpleNamespace(stdout=os.fdopen(reader,'rb'),wait=lambda **k:1 if fail_first else 0,poll=lambda:1 if fail_first else 0)
    monkeypatch.setattr(subprocess,'Popen',spawn)
    if fail_first:
        with pytest.raises(RuntimeError,match='ORA-01031'):exec(compile(script,'complete-notebook','exec'),{})
        assert actions==['load']
    else:
        exec(compile(script,'complete-notebook','exec'),{})
        assert actions==['load','verify_publish','vector']
    assert len(list((tmp_path/'gold-progress-logs').glob('*.log')))==len(actions)
