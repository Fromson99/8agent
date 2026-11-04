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
from oneclick_storage import PrefixFolder
from oneclick import configure, LiveLog


def params():
    return {'CODE_FOLDER_ID':'existing','ORACLE_CONNECTION':'AIDP','EXPECTED_DB_USER':'TEST_USER',
            'GOLD_OWNER':'TEST_OWNER','EMBED_MODEL':'stub','EMBED_DIMENSIONS':4,'WORK_DIR':''}


@pytest.mark.parametrize('project',['LEGAL_RAG','OTHER_DEV','LEGAL_RAG_DEV_TEST'])
def test_existing_project_is_accepted_without_flow_objects(project):
    cfg,root=configure(params(),project)
    assert cfg['project']==project
    assert cfg['input_folder']==cfg['folders']['report']=='existing'
    assert cfg['storage']['input']!=cfg['storage']['result']
    assert all(t['name'].startswith('TST_B003_LGL_') for t in cfg['target']['tables'].values())


@pytest.mark.parametrize('bad',[{'TABLE_PREFIX':'IDD_B003_LGL_'},{'EXPECTED_PARTS':34},{'TARGET_MODE':'DEV_1'}])
def test_sample_cannot_be_redirected_to_production_table_names(bad):
    with pytest.raises(ValueError,match='UNKNOWN_ONECLICK_PARAMETER'):configure(dict(params(),**bad),'EXISTING')


def test_scoped_files_exclude_other_inputs_and_path_escape():
    files={'code.zip':b'code','scope/input/a':b'a','scope/input2/b':b'b','other/PARTS.sha256':b'other'}
    class Folder:
        def list_paths_in_partition(self):return list(files)
        def get_download_stream(self,p):return io.BytesIO(files[p])
        def upload_stream(self,p,s):files[p]=s.read()
    folder=PrefixFolder(Folder(),'scope/input')
    assert folder.list_paths_in_partition()==['/a']
    assert folder.get_download_stream('/a').read()==b'a'
    folder.upload_stream('b',io.BytesIO(b'new'))
    assert files['scope/input/b']==b'new' and files['code.zip']==b'code'
    for p in ('../escape','nested/../../escape','/absolute','back\\slash'):
        with pytest.raises(ValueError):folder.upload_stream(p,io.BytesIO(b'bad'))


def test_raw_log_is_complete_when_display_events_are_throttled():
    output=io.StringIO();log=LiveLog(output)
    content='ordinary raw log\n'+json.dumps({'phase':'VECTOR_PROGRESS','rows':2,'total_rows':3})+'\n'+'x'*70000
    log.write(content[:19]);log.write(content[19:]);log.flush()
    assert output.getvalue()==content
    assert log.take()=={'phase':'VECTOR_PROGRESS','rows':2,'total_rows':3}
    assert log.take() is None


def test_bootstrap_rejects_corrupt_zip_before_data_or_db(monkeypatch,tmp_path):
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    called=[]
    class Folder:
        def __init__(self,key):assert key=='existing'
        def list_paths_in_partition(self):return ['/DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip']
        def get_download_stream(self,name):return io.BytesIO(b'corrupt')
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=Folder))
    code=(HERE/'DATAIKU_GOLD_ONECLICK_RUN_R1.txt').read_text().replace("'CODE_FOLDER_ID': ''","'CODE_FOLDER_ID': 'existing'")
    with pytest.raises(ValueError,match='CODE_ZIP_HASH'):exec(compile(code,'<delivered>','exec'),{})
    assert not list(tmp_path.iterdir())


def test_oneclick_delivery_has_two_parts_no_flow_installer_and_valid_hashes():
    archive=HERE/'DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip'
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();manifest=json.loads(z.read('FLOW_MANIFEST.json'))
        assert len(names)==len(set(names))
        assert sum('.part' in n for n in names)==2
        assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in names)
        assert 'dev_install.py' not in names and 'zip_install.py' not in names
        for name,h in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==h
        for name in names:
            if name.endswith('.py'):compile(z.read(name),name,'exec')
    assert (HERE/'DATAIKU_GOLD_ONECLICK_RUN_R1.txt').read_bytes()==(HERE/'DATAIKU_GOLD_ONECLICK_RUN_R1.py').read_bytes()
