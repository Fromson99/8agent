"""Use the retained control implementation in real subprocesses, without engine mocks."""
import importlib.util
import json
import sys
from pathlib import Path
import zipfile
import pytest
from semantic_runtime.contracts import sha
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '06_TOOLS/OFFLINE'))
import package_genos_optimized_rebuild_r5 as pack
import package_genos_optimized_rebuild_r3 as older


@pytest.fixture
def real_checkout(tmp_path):
    payload = tmp_path / 'payload'; dev = tmp_path / 'DEV'; dev.mkdir()
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z:
        z.extractall(payload)
    manifest = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    with zipfile.ZipFile(older.LEGACY) as z:
        for name in z.namelist():
            if name.startswith('02_BACKEND/') and name.endswith('.py'):
                target = dev / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(z.read(name))
    for path in pack.r4.FIELD_FILES:
        (dev / path).write_bytes((payload / 'field-predecessors' / path).read_bytes())
    pins = {str(p.relative_to(dev)): sha(p) for p in (dev / '02_BACKEND/semantic_runtime').glob('*.py')}
    for row in manifest['files']:
        if row['role'] == 'code' and (dev / row['path']).exists(): pins[row['path']] = sha(dev / row['path'])
    engine = dev / '02_BACKEND/ENGINES/test/1/runtime.json'; engine.parent.mkdir(parents=True)
    engine.write_text(json.dumps({'files': pins, 'entrypoint': {'path': '02_BACKEND/semantic_runtime/term_index.py'}}))
    pipeline = dev / '00_SYSTEM/PIPELINE.json'; pipeline.parent.mkdir()
    pipeline.write_text(json.dumps({'engines': {'test': {'manifest': str(engine.relative_to(dev)), 'sha256': sha(engine)}}, 'contracts': {}, 'profiles': {}}))
    spec = importlib.util.spec_from_file_location('r5_field_apply', payload / 'APPLY.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return payload, dev, manifest, module


def test_real_archived_control_apply_verify_and_rollback(real_checkout):
    payload, dev, manifest, module = real_checkout
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    module.apply(dev)
    for row in manifest['files']:
        if row['role'] == 'code': assert sha(dev / row['path']) == row['sha256']
    base = module.dependency()
    verified = base.engine_plan(dev)
    assert not verified['changed_code'] and not verified['schemas'] and not verified['engine_manifests']
    backup = next((dev / '.genos-pipeline-optimization-backups').iterdir())
    base.rollback(backup)
    for name, expected in before.items(): assert sha(dev / name) == expected
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()
    reports = list(payload.parent.glob('engine-command-*.json'))
    assert len(reports) == 3
    assert all('ENGINE CONTROL ' in json.loads(p.read_text())['stderr'] for p in reports)


def test_missing_module_main_guard_does_not_skip_engine_inspection(real_checkout):
    payload, dev, _, module = real_checkout
    control = dev / '02_BACKEND/semantic_runtime/control.py'
    control.write_text(control.read_text().replace("if __name__=='__main__':main()", ''))
    report = module.dependency().engine_plan(dev)
    assert '02_BACKEND/semantic_runtime/control.py' in report['changed_code']


def test_real_unrelated_code_drift_rolls_back_all_package_changes(real_checkout):
    payload, dev, _, module = real_checkout
    target = dev / '02_BACKEND/semantic_runtime/control.py'
    target.write_text(target.read_text() + '\n# unrelated field change\n')
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Unrelated engine/schema drift'):
        module.apply(dev)
    assert all(sha(dev / name) == expected for name, expected in before.items())
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()


def test_failed_engine_command_retains_output_and_rolls_back(real_checkout):
    payload, dev, _, module = real_checkout
    target = dev / '02_BACKEND/semantic_runtime/control.py'
    target.write_text('raise RuntimeError("test engine failure")\n')
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Engine rehash did not return JSON; diagnostics='):
        module.apply(dev)
    assert all(sha(dev / name) == expected for name, expected in before.items())
    result = json.loads(next(payload.parent.glob('engine-command-*.json')).read_text())
    assert 'test engine failure' in result['stderr']


def test_only_apply_adapter_changes_and_manifest_matches():
    with zipfile.ZipFile(pack.PREVIOUS) as old, zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as new:
        assert set(old.namelist()) == set(new.namelist())
        for name in old.namelist():
            if name not in {'APPLY_R2.py', 'GUIDE_UTF8.txt', 'CODE_MANIFEST.json'}: assert old.read(name) == new.read(name)
        for row in json.loads(new.read('CODE_MANIFEST.json'))['files']:
            assert __import__('hashlib').sha256(new.read(row['path'])).hexdigest() == row['sha256']
