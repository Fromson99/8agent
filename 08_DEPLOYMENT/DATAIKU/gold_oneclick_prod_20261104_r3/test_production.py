import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import zipfile
import pytest

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
sys.path.insert(0,str(PACKAGE))
from prod_run import configure,LiveLog
from prod_storage import PrefixFolder,open_folder
from prod_state import initialize


def params():
    return {'CODE_FOLDER_ID':'existing','INPUT_FOLDER_ID':'','ORACLE_CONNECTION':'AIDP',
            'EXPECTED_DB_USER':'PIDD2APP','GOLD_OWNER':'SIDDS','TABLE_PREFIX':'IDD_B003_LGL_',
            'TABLE_NAMES':{},'EMBED_MODEL':'stub','EMBED_DIMENSIONS':4,'WORK_DIR':''}


class Folder:
    def __init__(self):self.files={}
    def list_paths_in_partition(self):return ['/'+p for p in self.files]
    def get_download_stream(self,p):return io.BytesIO(self.files[p.lstrip('/')])
    def upload_stream(self,p,s):self.files[p]=s.read()


@pytest.mark.parametrize('project',['LEGAL_RAG','OTHER_EXISTING_PROJECT'])
def test_production_defaults_use_existing_folder_and_registered_tables(project):
    cfg,root=configure(params(),project)
    assert cfg['params']['EXPECTED_PARTS']==34
    assert cfg['input_folder']==cfg['folders']['report']=='existing'
    assert cfg['storage']['input']==''
    assert len(cfg['target']['tables'])==13
    assert all(t['name'].startswith('IDD_B003_LGL_') and t['owner']=='SIDDS' for t in cfg['target']['tables'].values())
    assert cfg['params']['EXPECTED_DB_USER']=='PIDD2APP'
    assert root.name in cfg['storage']['result']


@pytest.mark.parametrize('change',[{'GOLD_OWNER':'OTHER_OWNER'},{'EMBED_MODEL':'different'},
                                  {'CODE_FOLDER_ID':'different'},{'INPUT_FOLDER_ID':'separate'},
                                  {'TABLE_NAMES':{'DOC_VER':'REGISTERED_DOCUMENTS'}}])
def test_changed_identity_isolates_local_and_remote_without_reset(change):
    old,work=configure(params(),'LEGAL_RAG')
    new,next_work=configure(dict(params(),**change),'LEGAL_RAG')
    assert work!=next_work and old['storage']['result']!=new['storage']['result']
    assert configure(params(),'LEGAL_RAG')==(old,work)


def test_explicit_workdir_is_base_and_moving_it_does_not_evade_remote_guard(tmp_path):
    old,work=configure(dict(params(),WORK_DIR=str(tmp_path/'first')),'LEGAL_RAG')
    new,moved=configure(dict(params(),WORK_DIR=str(tmp_path/'second')),'LEGAL_RAG')
    assert old['storage']==new['storage'] and work!=moved
    assert work.parent==tmp_path/'first'
    remote=Folder();initialize(old,work,remote)
    with pytest.raises(ValueError,match='CHECKPOINT_WORKSPACE_MISSING_OR_CHANGED'):initialize(new,moved,remote)


def test_owner_correction_keeps_previous_receipt_bytes(tmp_path):
    p=dict(params(),WORK_DIR=str(tmp_path))
    old,work=configure(p,'LEGAL_RAG');folder=Folder();remote=PrefixFolder(folder,old['storage']['result'])
    initialize(old,work,remote);saved=dict(folder.files);local=(work/'workspace.json').read_bytes()
    new,newwork=configure(dict(p,GOLD_OWNER='CORRECT_OWNER'),'LEGAL_RAG')
    initialize(new,newwork,PrefixFolder(folder,new['storage']['result']))
    assert all(folder.files[k]==v for k,v in saved.items())
    assert (work/'workspace.json').read_bytes()==local


def test_separate_data_folder_has_no_writes(monkeypatch):
    calls=[]
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda key,**kw:calls.append(key) or Folder()))
    cfg,_=configure(dict(params(),INPUT_FOLDER_ID='already_uploaded'),'LEGAL_RAG')
    input_folder=open_folder(cfg,'input');open_folder(cfg,'result')
    assert calls==['already_uploaded','existing']
    with pytest.raises(ValueError,match='INPUT_FOLDER_IS_READ_ONLY'):input_folder.upload_stream('x',io.BytesIO(b'x'))


@pytest.mark.parametrize('bad',[{'WORK_DIR':'relative'},{'EXPECTED_PARTS':2},{'RUN_AFTER_INSTALL':True},
                               {'GOLD_OWNER':''},{'TABLE_NAMES':{'BAD':'X'}},{'EMBED_DIMENSIONS':True}])
def test_invalid_or_old_flow_parameters_stop_before_work(bad):
    with pytest.raises(ValueError):configure(dict(params(),**bad),'LEGAL_RAG')


def test_scoped_files_and_traversal():
    folder=Folder();folder.files={'code.zip':b'code','scope/input/a':b'a','scope/input2/b':b'b'}
    view=PrefixFolder(folder,'scope/input');assert view.list_paths_in_partition()==['/a']
    view.upload_stream('b',io.BytesIO(b'b'));assert folder.files['code.zip']==b'code'
    for path in ('../escape','/absolute','nested/../../escape','back\\slash'):
        with pytest.raises(ValueError):view.upload_stream(path,io.BytesIO(b'x'))


def test_full_raw_log_survives_throttled_display():
    out=io.StringIO();log=LiveLog(out)
    raw='raw line\n'+json.dumps({'phase':'VECTOR_PROGRESS','rows':1,'total_rows':2})+'\n'+'x'*70000
    log.write(raw[:7]);log.write(raw[7:]);log.flush()
    assert out.getvalue()==raw and log.take()['rows']==1 and log.take() is None


def test_code_corruption_stops_before_extract_or_SQL(monkeypatch,tmp_path):
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path));folder=Folder()
    folder.files={'DATAIKU_GOLD_ONECLICK_PROD_20261104_R3.zip':b'corrupt'}
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda key:folder))
    code=(HERE/'DATAIKU_GOLD_PROD_RUN_R3.txt').read_text()
    with pytest.raises(ValueError,match='CODE_ZIP_HASH'):exec(compile(code,'<delivered>','exec'),{})
    assert not list(tmp_path.iterdir())


def test_actual_package_hashes_and_unchanged_engine():
    with zipfile.ZipFile(HERE/'DATAIKU_GOLD_ONECLICK_PROD_20261104_R3.zip') as z:
        names=z.namelist();manifest=json.loads(z.read('FLOW_MANIFEST.json'))
        assert len(names)==len(set(names))
        assert not any(n.startswith('sample/') or Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in names)
        assert not any(n in names for n in ('dev_install.py','zip_install.py','oneclick_db.py'))
        for name,sha in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
        for name in names:
            if name.endswith('.py'):compile(z.read(name),name,'exec')
        parent=json.loads((HERE/'PARENT_ENGINE_HASHES.json').read_text())
        assert {n[7:]:s for n,s in manifest['files'].items() if n.startswith('engine/')}==parent['files']
    assert (HERE/'DATAIKU_GOLD_PROD_RUN_R3.py').read_bytes()==(HERE/'DATAIKU_GOLD_PROD_RUN_R3.txt').read_bytes()
