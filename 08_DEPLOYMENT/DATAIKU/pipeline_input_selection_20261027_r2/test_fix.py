"""Field duplicate-name repair: preserved originals, SDK update and exact byte checks."""
import ast
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import zipfile
import pytest

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_recipes_20261027_r1'
REF=json.loads((HERE/'REFERENCE.json').read_text())
EXTRACT=tempfile.TemporaryDirectory(prefix='a8-input-selection-test-')
ROOT=Path(EXTRACT.name)
with zipfile.ZipFile(BASE/'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip') as z:z.extractall(ROOT)
sys.path[:0]=[str(ROOT),str(ROOT/'client'),str(ROOT/'client/02_BACKEND')]
import recipes_runtime as runtime
import install_flow
import input_selection as fix
import update_recipes as updater
spec=importlib.util.spec_from_file_location('prior_sdk_test',BASE/'test_sdk.py')
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)


class Folder:
    def __init__(self):self.data={};self.writes=0
    def list_paths_in_partition(self):return ['/'+p for p in self.data]
    def get_download_stream(self,path):return io.BytesIO(self.data[path.lstrip('/')])
    def upload_stream(self,name,stream):self.writes+=1;self.data[name.lstrip('/')]=stream.read()


@pytest.fixture
def raw(tmp_path,monkeypatch):
    source=Folder()
    for name,member in [('RAW_INPUT.zip','01_DATA/RAW/internal/team/원문.txt'),
                        ('PIPELINE_SUPPORT.zip','01_DATA/CATALOG/fixture.txt')]:
        file=tmp_path/(name+'.input');file.write_bytes(b'correct original')
        packed=tmp_path/name
        receipt=runtime.t.pack({member:file},packed)
        source.data[name]=packed.read_bytes()
        source.data[name+'.receipt.json']=json.dumps({'archive':name,**receipt}).encode()
        # Even a different duplicate must be preserved and cannot be auto-selected.
        source.data[name.replace('.zip',' (1).zip')]=b'different duplicate'
        source.data[name+'.receipt (1).json']=b'not the selected receipt'
    original=runtime.input_receipts
    monkeypatch.setattr(runtime,'input_receipts',original)
    return source


def test_reproduce_then_fix_both_names_without_source_mutation(raw,tmp_path):
    with pytest.raises(ValueError,match='INPUT_NAME_AMBIGUOUS_OR_MISSING'):
        runtime.input_receipts(raw)
    before=copy.deepcopy(raw.data)
    fix.install_input_selection(runtime)
    chosen=runtime.input_receipts(raw)
    assert chosen['RAW_INPUT.zip']['remote']=='/RAW_INPUT.zip'
    assert chosen['PIPELINE_SUPPORT.zip']['remote']=='/PIPELINE_SUPPORT.zip'
    output=Folder();work=tmp_path/'work';work.mkdir()
    result=runtime.unpack_raw(raw,output,work)
    assert result['status']=='RAW_SAVED' and result['files']==1
    assert raw.data==before and raw.writes==0
    assert any(v==b'correct original' for v in output.data.values())


@pytest.mark.parametrize('name',fix.SELECTED_INPUT_NAMES)
def test_missing_explicit_file_never_falls_back(raw,name):
    del raw.data[name]
    fix.install_input_selection(runtime)
    with pytest.raises(ValueError,match='SELECTED_INPUT_MISSING') as error:
        runtime.input_receipts(raw)
    assert name in str(error.value) and raw.writes==0


def test_original_receipt_checks_preserved(raw):
    raw.data['RAW_INPUT.zip.receipt.json']=json.dumps({'archive':'another.zip','bytes':1,'sha256':'0'*64}).encode()
    fix.install_input_selection(runtime)
    with pytest.raises(runtime.legacy.RunError,match='RECEIPT_INVALID'):runtime.input_receipts(raw)


def test_raw_hash_check_preserved(raw,tmp_path):
    raw.data['RAW_INPUT.zip']=b'corrupt'
    fix.install_input_selection(runtime)
    work=tmp_path/'corrupt-run';work.mkdir()
    output=Folder()
    with pytest.raises(runtime.legacy.RunError,match='DOWNLOAD_HASH_OR_SIZE'):
        runtime.unpack_raw(raw,output,work)
    assert not output.data and raw.writes==0


def test_wrapper_is_idempotent(raw):
    fix.install_input_selection(runtime);first=runtime.input_receipts
    fix.install_input_selection(runtime)
    assert runtime.input_receipts is first


def setup_backend(backend=None):
    backend=backend or sdk.Backend();project=sdk.DSSProject(backend,'LEGAL_RAG')
    cfg=install_flow.install(project,REF['baseline_bootstrap'],'ehA8dpVm')
    return backend,project,cfg


def apply(project,tmp_path,action='apply'):
    return updater.update(project,REF['baseline_bootstrap'],REF['adapter_source'],REF['datasets'],tmp_path/'backup',action)


def test_real_sdk_apply_idempotent_rollback_preserves_edges_and_objects(tmp_path):
    backend,project,cfg=setup_backend();before=copy.deepcopy(backend.items)
    assert apply(project,tmp_path)['status']=='INPUT_SELECTION_APPLIED'
    after=copy.deepcopy(backend.items)
    assert before['managedfolders']==after['managedfolders']
    assert before['datasets']==after['datasets']
    assert before['recipes']['LEGAL_00_CHECK_GENOS_R1']==after['recipes']['LEGAL_00_CHECK_GENOS_R1']
    for name in before['recipes']:
        assert before['recipes'][name]['recipe']==after['recipes'][name]['recipe']
    backend.calls=[]
    apply(project,tmp_path)
    assert backend.items==after and all(call[0]=='GET' for call in backend.calls)
    assert apply(project,tmp_path,'rollback')['status']=='INPUT_SELECTION_ROLLED_BACK'
    assert backend.items==before


@pytest.mark.parametrize('change',['code','flow'])
def test_unknown_change_refused_before_any_save(tmp_path,change):
    backend,project,cfg=setup_backend()
    item=backend.items['recipes']['LEGAL_03_LOAD_SILVER_R1']
    if change=='code':item['payload']='# user edit\n'+item['payload']
    else:item['recipe']['inputs']['main']['items'].append({'ref':'unrelated'})
    before=copy.deepcopy(backend.items);backend.calls=[]
    with pytest.raises(ValueError,match='CHANGED'):apply(project,tmp_path)
    assert backend.items==before and all(call[0]=='GET' for call in backend.calls)


def test_saved_but_reply_lost_can_resume_remaining_recipes(tmp_path):
    class Backend(sdk.Backend):
        lose=False
        def _perform_json(self,method,path,body=None,**kwargs):
            result=super()._perform_json(method,path,body=body,**kwargs)
            if self.lose and method=='PUT' and path.endswith('/recipes/LEGAL_02_STRUCTURE_GENOS_R1'):
                self.lose=False
                raise RuntimeError('simulated lost save response')
            return result
    backend,project,cfg=setup_backend(Backend());backend.lose=True
    with pytest.raises(RuntimeError,match='lost save response'):apply(project,tmp_path)
    backend.calls=[]
    assert apply(project,tmp_path)['status']=='INPUT_SELECTION_APPLIED'
    writes=[p for method,p,_ in backend.calls if method=='PUT']
    assert writes==['/projects/LEGAL_RAG/recipes/LEGAL_03_LOAD_SILVER_R1']


def test_final_full_notebook_cell_through_sdk_and_selected_read_only_folder(raw,tmp_path,monkeypatch):
    backend,project,cfg=setup_backend();monkeypatch.chdir(tmp_path)
    fake=SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',api_client=lambda:backend,Folder=lambda name:raw)
    monkeypatch.setitem(sys.modules,'dataiku',fake)
    script=(HERE/'DATAIKU_INPUT_SELECTION_FIX_20261027_R2.txt').read_text()
    ns={'__name__':'__main__'};exec(compile(script,'delivered-fix','exec'),ns)
    assert ns['FIX_RESULT']['status']=='INPUT_SELECTION_APPLIED'
    assert raw.writes==0
    # Actual updated recipe source still loads the original pinned ZIP; wrapper is
    # inside run_recipe so it applies again in each separate DSS recipe process.
    for name in ('LEGAL_01_UNZIP_RAW_R1','LEGAL_02_STRUCTURE_GENOS_R1','LEGAL_03_LOAD_SILVER_R1'):
        source=backend.items['recipes'][name]['payload']
        tree=ast.parse(source)
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run_recipe')
        assert 'install_input_selection(recipes_runtime)' in ast.unparse(function)
        assert REF['old_package_sha256'] in source


def test_syntax_python39_and_delivered_zip_contains_exact_txt():
    name='DATAIKU_INPUT_SELECTION_FIX_20261027_R2.txt'
    source=(HERE/name).read_text()
    ast.parse(source,feature_version=(3,9))
    with zipfile.ZipFile(HERE/name.replace('.txt','.zip')) as z:
        assert z.read(name)==source.encode()
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    manifest=json.loads((HERE/'DELIVERY_MANIFEST.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest


def test_updated_recipe_runs_real_unpack_with_duplicate_names_present(raw,tmp_path,monkeypatch):
    backend,project,cfg=setup_backend()
    apply(project,tmp_path)
    output=Folder()
    fake=SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',get_custom_variables=lambda:{},
                         Folder=lambda name:raw if name==cfg['landing'] else output)
    monkeypatch.setitem(sys.modules,'dataiku',fake)
    source=backend.items['recipes']['LEGAL_01_UNZIP_RAW_R1']['payload']
    tree=ast.parse(source);tree.body.pop()  # Control the verified local ZIP extraction only.
    ns={'__name__':'recipe_fixture'};exec(compile(tree,'updated-recipe','exec'),ns)
    work=tmp_path/'actual-recipe-work';work.mkdir()
    ns['verified_package']=lambda:(work,ROOT)
    before=copy.deepcopy(raw.data)
    ns['run_recipe']('unpack',cfg)
    assert not work.exists() and raw.data==before and raw.writes==0
    assert any(path.endswith('/manifest.json') for path in output.data)
