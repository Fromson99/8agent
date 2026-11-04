import ast
import copy
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'gold_zip_flow_20261104_r1'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


old = module('original_notebook_fixture', HERE.parent / 'gold_zip_upload_20261104_r1/test_notebook.py')
repair_module = module('s3_repair_fixture', HERE / 'repair.py')
tree = ast.parse((PARENT / 'DATAIKU_GOLD_ZIP_FLOW_RUN_R1.txt').read_text())
BOOTSTRAP = ast.literal_eval(next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                                and isinstance(n.func, ast.Name) and n.func.id == 'install').args[1])
PARAMS = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == 'PARAMS'))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(PARENT / 'package'))
    monkeypatch.delitem(sys.modules, 'zip_config', raising=False)
    config = __import__('zip_config')
    installer = module('original_s3_installer', PARENT / 'package/zip_install.py')
    project = old.Project()
    project.stores = {}; project.fail_upload_id = None; project.past_runs = []
    project.old_readable = False
    source = project.folders['ehA8dpVm']
    source.type = 'S3'; source.params = {'connection':'OBS','path':'/dataiku/${projectKey}/${odbId}'}
    source_original = dict(source.files)
    def info(folder, sensitive_info=False):
        assert sensitive_info is False
        p = folder.params
        root = p['path'].replace('${projectKey}', project.project_key).replace('${odbId}', folder.id)
        return {'accessInfo':{'bucket':p.get('bucket','APPROVED_BUCKET'),'root':root,'ignored_secret':'must_not_emit'}}
    def store(folder):
        access = info(folder)['accessInfo']
        key = (access['bucket'], access['root'])
        if not project.old_readable and (key[0] != 'APPROVED_BUCKET' or not key[1].startswith('/dataiku/')):
            raise Exception('S3 bucket does not exist or is not authorized (Status Code: 404)')
        return project.stores.setdefault(key, {})
    def upload(folder, path, stream):
        if folder.id == project.fail_upload_id:
            raise ConnectionError('synthetic write failure')
        store(folder)[path.lstrip('/')] = stream.read()
    monkeypatch.setattr(old.Folder, 'get_info', info, raising=False)
    monkeypatch.setattr(old.Folder, 'list_paths_in_partition', lambda f:['/'+n for n in store(f)])
    monkeypatch.setattr(old.Folder, 'get_download_stream', lambda f,p:io.BytesIO(store(f)[p.lstrip('/')]))
    monkeypatch.setattr(old.Folder, 'upload_stream', upload)
    factory = project.create_managed_folder
    def create(*a, **kw):
        f = factory(*a, **kw); f.params['bucket'] = 'OLD_DEFAULT'; return f
    project.create_managed_folder = create
    monkeypatch.setattr(old.Scenario, 'get_current_run', lambda s:None, raising=False)
    monkeypatch.setattr(old.Scenario, 'get_last_runs', lambda s,limit=10:project.past_runs, raising=False)
    api = SimpleNamespace(api_client=lambda:project, Folder=lambda key,**kw:project.folders[key])
    monkeypatch.setitem(sys.modules, 'dataiku', api)
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    params = dict(PARAMS, INPUT_FOLDER_ID=source.id, GOLD_OWNER='FIELD_OWNER', RUN_AFTER_INSTALL=False)
    # Reproduce the original failure with the actual unmodified R1 installer.
    with pytest.raises(Exception, match='bucket.*404'):
        installer.install(params, BOOTSTRAP)
    before = {f.id:copy.deepcopy(f.params) for f in project.folders.values()}
    scripts = {n:r.get_code() for n,r in project.recipes.items()}
    def run(mode='REPAIR'):
        return repair_module.repair(api, BOOTSTRAP, config.STAGES, mode=mode)
    yield SimpleNamespace(project=project, api=api, run=run, before=before, scripts=scripts,
                          source=source, source_original=source_original, store=store)
    sys.modules.pop('zip_config', None)


def test_delivered_txt_preserves_ids_and_recipes_and_fixes_inherited_bucket(env, capsys):
    namespace = {}
    exec(compile((HERE/'DATAIKU_GOLD_S3_REPAIR_RUN_R1.txt').read_text(), '<delivered-repair>', 'exec'), namespace)
    assert namespace['REPAIR_RESULT']['status'] == 'REPAIR_COMPLETE'
    assert set(env.before) == set(env.project.folders)
    assert env.scripts == {n:r.get_code() for n,r in env.project.recipes.items()}
    assert env.source.files == env.source_original
    assert env.source.params == env.before[env.source.id]
    assert all(f.params == env.source.params for f in env.project.folders.values())
    assert env.project.scenarios['scenario1'].runs == 0
    assert len(env.project.stores) == 8
    assert 'must_not_emit' not in capsys.readouterr().out


def test_repeat_and_rollback_preserve_old_objects_and_settings(env):
    env.run(); env.run()
    env.run('ROLLBACK')
    assert env.before == {f.id:f.params for f in env.project.folders.values()}
    assert len(env.project.stores) == 8  # rollback never deletes new-location objects


def test_partial_failure_resumes_and_does_not_launch(env):
    env.project.fail_upload_id = 'folder4'
    with pytest.raises(ConnectionError): env.run()
    env.project.fail_upload_id = None
    assert env.run()['status'] == 'REPAIR_COMPLETE'
    assert env.project.scenarios['scenario1'].runs == 0


def test_partial_failure_can_rollback_even_when_original_bucket_is_inaccessible(env):
    env.project.fail_upload_id = 'folder4'
    with pytest.raises(ConnectionError): env.run()
    assert env.run('ROLLBACK')['status'] == 'ROLLBACK_COMPLETE'
    assert env.before == {f.id:f.params for f in env.project.folders.values()}


@pytest.mark.parametrize('change,match', [('history','ALREADY_STARTED'),('recipe','RECIPE_CODE_CHANGED'),
                                        ('connection','CONNECTION_CHANGED'),('template','TEMPLATE_DIFFERS')])
def test_incompatible_state_stops_before_settings_change(env, change, match):
    if change == 'history': env.project.past_runs = [object()]
    if change == 'recipe': env.project.recipes['G19ZIP_00_INPUT'].script = '#changed\n' + env.project.recipes['G19ZIP_00_INPUT'].script
    if change == 'connection': env.project.folders['folder4'].params['connection'] = 'OTHER'
    if change == 'template': env.source.params['path'] = '/fixed-upload-path'
    before = copy.deepcopy({f.id:f.params for f in env.project.folders.values()})
    with pytest.raises(ValueError, match=match): env.run()
    assert before == {f.id:f.params for f in env.project.folders.values()}


def test_existing_checkpoint_blocks_relocation(env):
    env.project.old_readable = True
    env.store(env.project.folders['folder4'])['workspace.json'] = b'keep'
    with pytest.raises(ValueError, match='HAS_EXISTING_DATA'): env.run()
    assert env.before == {f.id:f.params for f in env.project.folders.values()}


def test_success_does_not_make_original_installer_safe_to_rerun(env):
    env.run()
    params = dict(PARAMS, INPUT_FOLDER_ID=env.source.id, GOLD_OWNER='FIELD_OWNER', RUN_AFTER_INSTALL=False)
    installer = module('original_installer_after_repair', PARENT/'package/zip_install.py')
    with pytest.raises(ValueError, match='EXISTING_FOLDER_CONFLICT'):
        installer.install(params, BOOTSTRAP)
