"""Test exact delivered notebook plus failures before any Oracle/model execution."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import zipfile
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('old_fakes', HERE.parent/'gold_zip_upload_20261104_r1/test_notebook.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
NAME = 'DATAIKU_GOLD_DEV_TEST_20261104_R1.zip'


class Folder(old.Folder):
    def __init__(self, project, key, name):
        super().__init__(project,key,name)
        self.type='S3'; self.params={'connection':'OBS_DEV','path':'/dataiku/${projectKey}/${odbId}'}
    def get_info(self, sensitive_info=False):
        assert sensitive_info is False
        root='/dataiku/'+self.project.project_key+'/'+self.id
        if self.project.overlap: root='/same'
        return {'type':'S3','accessInfo':{'bucket':'allowed-dev-bucket','root':root}}
    def move_to_zone(self, zone): self.zone=zone.name
    def upload_stream(self, path, stream):
        if self.name==self.project.fail_folder:
            raise OSError('S3 404 bucket missing or unauthorized')
        super().upload_stream(path,stream)


class Recipe(old.Recipe):
    def move_to_zone(self, zone): self.zone=zone.name
    def get_metadata(self): return {'description':'','label':self.name}
    def set_metadata(self, metadata): self.metadata=metadata


class Project(old.Project):
    project_key='LEGAL_RAG_DEV_TEST'
    def __init__(self):
        self.folders,self.datasets,self.recipes,self.scenarios,self.zones={},{},{},{},[]
        self.fail_folder=''; self.overlap=False
        f=Folder(self,'code123','GOLD_TEST_CODE'); f.files[NAME]=(HERE/NAME).read_bytes()
        self.folders[f.id]=f
    def create_managed_folder(self, name, folder_type=None, connection_name=None):
        f=Folder(self,'folder'+str(len(self.folders)),name)
        assert folder_type=='S3' and connection_name=='OBS_DEV'
        self.folders[f.id]=f; return f
    def new_recipe(self, kind, name): assert kind=='python'; return Recipe(self,name)


@pytest.fixture
def setup(monkeypatch,tmp_path):
    project=Project()
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    monkeypatch.setattr(sys,'path',sys.path[:])
    modules=('zip_config','zip_runtime','dev_install','dev_guard','dev_watch','progress_panel')
    for name in modules: monkeypatch.delitem(sys.modules,name,raising=False)
    monkeypatch.setitem(sys.modules,'dataiku',SimpleNamespace(api_client=lambda:project,
        Folder=lambda key,**kw:project.folders[key]))
    text=(HERE/'DATAIKU_GOLD_DEV_TEST_RUN_R1.txt').read_text()
    text=text.replace("'CODE_FOLDER_ID': ''","'CODE_FOLDER_ID': 'code123'")
    text=text.replace("'ORACLE_CONNECTION': ''","'ORACLE_CONNECTION': 'ORACLE_DEV'")
    text=text.replace("'EXPECTED_DB_USER': ''","'EXPECTED_DB_USER': 'TEST_USER'")
    text=text.replace("'GOLD_OWNER': ''","'GOLD_OWNER': 'TEST_OWNER'")
    def run(changes=()):
        code=text
        for a,b in changes: code=code.replace(a,b)
        ns={}; exec(compile(code,'<delivered>', 'exec'),ns); return ns['FLOW_CONFIG']
    yield project,run
    for name in modules: sys.modules.pop(name,None)


def test_delivered_installs_and_seeds_exact_two_parts(setup):
    p,run=setup; cfg=run()
    assert len(p.folders)==10 and len(p.recipes)==8 and len(p.datasets)==10
    assert len(p.zones)==7 and all(r.zone!='default' for r in p.recipes.values())
    assert all(r.metadata['label'] for r in p.recipes.values())
    files=p.folders[cfg['input_folder']].files
    assert len(files)==4 and len([n for n in files if '.part' in n])==2
    raw=b''.join(files[n] for n in sorted(files) if '.part' in n)
    with zipfile.ZipFile(io.BytesIO(raw)) as z: assert any(n.endswith('DATA_MANIFEST.json') for n in z.namelist())
    assert all(f.params=={'connection':'OBS_DEV','path':'/dataiku/${projectKey}/${odbId}'} for f in p.folders.values())
    assert p.scenarios['scenario1'].runs==0
    assert all(d.raw['params']['table'].startswith('TST_B003_LGL_') and d.raw['managed'] is False for d in p.datasets.values())
    assert cfg==run()  # no duplicate objects or automatic launch


@pytest.mark.parametrize('name',['GOLD_TEST_CODE','GTEST_00_INPUT_RESULT','GTEST_07_REPORT_RESULT'])
def test_storage_failure_before_oracle_objects_or_launch(setup,name):
    p,run=setup; p.fail_folder=name
    with pytest.raises(RuntimeError,match='STORAGE_CHECK_FAILED'): run()
    assert not p.datasets and not p.recipes and not p.scenarios
    p.fail_folder=''; run()  # idempotent setup resumes with existing folder IDs


def test_wrong_project_and_production_names_rejected_before_creation(setup):
    p,run=setup; p.project_key='LEGAL_RAG'
    with pytest.raises(ValueError,match='TEST_PROJECT_REQUIRED'): run()
    assert len(p.folders)==1 and not p.zones
    p.project_key='LEGAL_RAG_DEV_TEST'
    with pytest.raises(ValueError,match='TEST_TABLE_NAMES_REQUIRED'):
        run([("'TABLE_PREFIX': 'TST_B003_LGL_'","'TABLE_PREFIX': 'IDD_B003_LGL_'")])
    assert len(p.folders)==1


def test_overlapping_storage_is_rejected(setup):
    p,run=setup; p.overlap=True
    with pytest.raises(ValueError,match='FOLDER_LOCATION_OVERLAP'): run()
    assert not p.datasets and not p.recipes
    assert all(not any(n.startswith('_connection') for n in f.files) for f in p.folders.values())


@pytest.mark.parametrize('fault',['changed','extra','partial'])
def test_sample_is_never_overwritten_or_mixed(setup,fault):
    p,run=setup; cfg=run(); files=p.folders[cfg['input_folder']].files
    name='gold-dev-sample.zip.part000000'
    if fault=='changed': files[name]=b'corrupt'
    if fault=='extra': files['production.zip.part000000']=b'wrong'
    if fault=='partial':
        files.pop(name); assert run()==cfg; assert files[name]; return
    before=dict(files)
    with pytest.raises(ValueError,match='TEST_INPUT_'):run()
    assert files==before


def test_changed_connection_config_cannot_adopt_checkpoint(setup):
    p,run=setup; run()
    with pytest.raises(ValueError,match='EXISTING_INSTALLATION_CHANGED'):
        run([("'GOLD_OWNER': 'TEST_OWNER'","'GOLD_OWNER': 'OTHER_OWNER'")])


def test_code_tampering_detected(setup):
    p,run=setup; p.folders['code123'].files[NAME]+=b'tampered'
    with pytest.raises(ValueError,match='CODE_ZIP_HASH'):run()
    assert len(p.folders)==1


def test_monitor_ignores_stale_completed_report(setup):
    p,run=setup;cfg=run()
    import dev_watch
    for stage,ref in cfg['folders'].items():
        p.folders[ref].files['latest.json']=json.dumps({'status':'SUCCESS','started_at':10,'ended_at':20}).encode()
    report=p.folders[cfg['folders']['report']]
    report.files['report.json']=json.dumps({'status':'GOLD_LOADED','row_counts_and_publications_verified':True,'counts':{'DOC_VER':2}}).encode()
    assert dev_watch.snapshot(cfg)['complete']
    p.folders[cfg['folders']['source']].files['latest.json']=json.dumps({'status':'SUCCESS','started_at':30,'ended_at':40}).encode()
    assert not dev_watch.snapshot(cfg)['complete']
    p.folders[cfg['folders']['source']].files['latest.json']=json.dumps({'status':'FAILED','started_at':30,'ended_at':40,'error':'boom'}).encode()
    state=dev_watch.snapshot(cfg)
    assert not state['complete'] and 'boom' in dev_watch.render(state,1)[1]


def test_final_archive_members_and_syntax():
    with zipfile.ZipFile(HERE/NAME) as z:
        names=z.namelist()
        assert sum('.part' in n for n in names)==2
        assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in names)
        for name in names:
            if name.endswith('.py'):compile(z.read(name),name,'exec')
    for p in HERE.glob('*RUN*.txt'):compile(p.read_text(),p.name,'exec')
