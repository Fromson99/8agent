"""Execute the delivered TXT with real ZIP/installer and a local DSS API substitute."""
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ARCHIVE = 'genos-rag-data-20261007T002029Z-7c0b050f.zip'
CODE = 'DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip'


class Folder:
    def __init__(self, project, key, name):
        self.project, self.id, self.name = project, key, name
        self.type = 'Filesystem'
        self.params = {'connection': 'filesystem_folders'}
        self.files = {}
    def get_settings(self): return self
    def get_raw_params(self): return self.params
    def save(self): pass
    def move_to_zone(self, zone): pass
    def list_paths_in_partition(self): return ['/' + n for n in self.files]
    def get_download_stream(self, path): return io.BytesIO(self.files[path.lstrip('/')])
    def upload_stream(self, path, stream): self.files[path] = stream.read()


class Dataset:
    def __init__(self, kind, params): self.raw = {'type': kind, 'params': params}
    def get_settings(self): return self
    def get_raw(self): return self.raw
    def save(self): pass
    def set_schema(self, schema): self.schema = schema
    def get_schema(self): return self.schema
    def move_to_zone(self, zone): pass


class Recipe:
    def __init__(self, project, name):
        self.project, self.name, self.inputs, self.outputs = project, name, [], []
    def with_input(self, ref): self.inputs.append(ref); return self
    def with_output(self, ref, append=False):
        assert append
        self.outputs.append(ref); return self
    def with_script(self, script): self.script = script; return self
    def create(self): self.project.recipes[self.name] = self; return self
    def get_settings(self): return self
    def set_code_env(self, **kw): assert kw == {'inherit': True}
    def save(self): pass
    def get_code(self): return self.script
    def get_flat_input_refs(self): return self.inputs
    def get_flat_output_refs(self): return self.outputs


class Scenario:
    def __init__(self, name): self.id, self.name, self.runs, self.fail_launch = 'scenario1', name, 0, False
    def get_settings(self): return self
    def save(self): pass
    def run(self):
        self.runs += 1
        if self.fail_launch: raise ConnectionError('launch response lost')


class Project:
    project_key = 'LEGAL_RAG'
    def __init__(self):
        self.folders, self.datasets, self.recipes, self.scenarios, self.zones = {}, {}, {}, {}, []
        inp = Folder(self, 'ehA8dpVm', 'existing uploads')
        inp.files = {ARCHIVE + '.part%06d' % i: b'data' for i in range(34)}
        inp.files.update({CODE: (HERE / CODE).read_bytes(), 'PARTS.sha256': b'metadata', 'ORIGINAL.sha256': b'metadata'})
        self.folders[inp.id] = inp
    def get_default_project(self): return self
    def get_managed_folder(self, key): return self.folders[key]
    def list_managed_folders(self): return [{'id': f.id, 'name': f.name} for f in self.folders.values()]
    def get_flow(self): return self
    def list_zones(self): return self.zones
    def create_zone(self, name):
        zone = SimpleNamespace(name=name); self.zones.append(zone); return zone
    def create_managed_folder(self, name, folder_type=None, connection_name=None):
        folder = Folder(self, 'folder' + str(len(self.folders)), name)
        folder.type = folder_type; folder.params['connection'] = connection_name
        self.folders[folder.id] = folder; return folder
    def list_datasets(self): return [{'name': n} for n in self.datasets]
    def get_dataset(self, name): return self.datasets[name]
    def create_dataset(self, name, type=None, params=None):
        ds = Dataset(type, params); self.datasets[name] = ds; return ds
    def list_recipes(self): return [{'name': n} for n in self.recipes]
    def get_recipe(self, name): return self.recipes[name]
    def new_recipe(self, kind, name): assert kind == 'python'; return Recipe(self, name)
    def list_scenarios(self): return [{'id': s.id, 'name': s.name} for s in self.scenarios.values()]
    def get_scenario(self, key): return self.scenarios[key]
    def create_scenario(self, name, kind):
        assert kind == 'custom_python'
        scenario = Scenario(name); self.scenarios[scenario.id] = scenario; return scenario


@pytest.fixture
def setup(monkeypatch, tmp_path):
    project = Project()
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    monkeypatch.setattr(sys, 'path', sys.path[:])
    for name in ('zip_config', 'zip_install'):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, 'dataiku', SimpleNamespace(
        api_client=lambda: project,
        Folder=lambda key, **kw: project.folders[key]))
    text = (HERE / 'DATAIKU_GOLD_ZIP_UPLOAD_RUN_R1.txt').read_text()
    def run(owner='FIELD_OWNER', changes=()):
        code = text.replace("'GOLD_OWNER': ''", "'GOLD_OWNER': " + repr(owner))
        for before, after in changes: code = code.replace(before, after)
        ns = {}; exec(compile(code, '<delivered-notebook>', 'exec'), ns); return ns
    yield project, run
    for name in ('zip_config', 'zip_install'): sys.modules.pop(name, None)


def test_actual_notebook_installs_eight_stages_and_starts_once(setup):
    project, run = setup
    before = dict(project.folders['ehA8dpVm'].files)
    ns = run()
    assert len(project.recipes) == 8 and len(project.datasets) == 13
    assert len(project.folders) == 9  # existing shared code/data + eight result folders
    assert ns['FLOW_CONFIG']['input_folder'] == 'ehA8dpVm'
    assert project.scenarios['scenario1'].runs == 1
    assert all(d.raw['managed'] is False for d in project.datasets.values())
    assert all(d.raw['params']['schema'] == 'FIELD_OWNER' for d in project.datasets.values())
    assert project.folders['ehA8dpVm'].files == before
    saved = project.folders[ns['FLOW_CONFIG']['folders']['report']].files['installation.json']
    assert json.loads(saved)['scenario'] == 'scenario1'


def test_reinstall_reuses_flow_without_start_when_disabled(setup):
    project, run = setup
    first = run(changes=[("'RUN_AFTER_INSTALL': True", "'RUN_AFTER_INSTALL': False")])
    second = run(changes=[("'RUN_AFTER_INSTALL': True", "'RUN_AFTER_INSTALL': False")])
    assert first['FLOW_CONFIG'] == second['FLOW_CONFIG']
    assert len(project.recipes) == 8 and len(project.folders) == 9
    assert project.scenarios['scenario1'].runs == 0


@pytest.mark.parametrize('problem,match', [('missing', '누락'), ('nested', '누락'),
                                         ('checksum', 'ORIGINAL.sha256'), ('code', 'CODE_ZIP_HASH')])
def test_bad_upload_stops_before_flow_mutation(setup, problem, match):
    project, run = setup
    files = project.folders['ehA8dpVm'].files
    if problem == 'missing': files.pop(ARCHIVE + '.part000030')
    if problem == 'nested': files['sub/' + ARCHIVE + '.part000000'] = files.pop(ARCHIVE + '.part000000')
    if problem == 'checksum': files.pop('ORIGINAL.sha256')
    if problem == 'code': files[CODE] += b'tampered'
    with pytest.raises(ValueError, match=match): run()
    assert not project.recipes and not project.datasets and len(project.folders) == 1


def test_wrong_project_and_missing_owner_stop_before_creation(setup):
    project, run = setup
    with pytest.raises(ValueError, match='GOLD_OWNER'): run(owner='')
    project.project_key = 'OTHER'
    with pytest.raises(ValueError, match='프로젝트 불일치'): run()
    assert not project.zones and len(project.folders) == 1


def test_ambiguous_launch_is_not_retried(setup):
    project, run = setup
    run(changes=[("'RUN_AFTER_INSTALL': True", "'RUN_AFTER_INSTALL': False")])
    project.scenarios['scenario1'].fail_launch = True
    with pytest.raises(ConnectionError, match='launch response lost'): run()
    assert project.scenarios['scenario1'].runs == 1


def test_parent_code_zip_is_unchanged():
    assert (HERE / CODE).read_bytes() == (HERE.parent / 'gold_zip_flow_20261104_r1' / CODE).read_bytes()
