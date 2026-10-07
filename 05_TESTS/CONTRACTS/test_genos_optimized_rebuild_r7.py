"""Mixed onsite baseline inconsistencies remain unchanged through scoped code application."""
import importlib.util
import json
import zipfile
import pytest
from semantic_runtime.contracts import sha
from test_genos_optimized_rebuild_r6 import historical
from test_genos_optimized_rebuild_r5 import real_checkout
import package_genos_optimized_rebuild_r7 as pack


@pytest.fixture
def mixed(historical):
    payload, dev, _, _, _ = historical
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z: z.extractall(payload)
    spec = importlib.util.spec_from_file_location('r7_field_apply', payload / 'APPLY.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    pipeline = dev / '00_SYSTEM/PIPELINE.json'; config = json.loads(pipeline.read_text())
    schema = dev / '00_SYSTEM/field-schema.json'; schema.write_text('{"existing":true}')
    config['contracts'] = {'test': {'schema_path': str(schema.relative_to(dev)), 'schema_sha256': 'old-schema-pin'}}
    config['engines']['test']['sha256'] = 'old-engine-manifest-pin'
    pipeline.write_text(json.dumps(config))
    control = dev / '02_BACKEND/semantic_runtime/control.py'; control.write_text('raise RuntimeError("not a code-install dependency")\n')
    extension = dev / '02_BACKEND/semantic_runtime/field_extension.py'; extension.write_text('field = 1\n')
    engine = dev / config['engines']['test']['manifest']; value = json.loads(engine.read_text())
    value['files']['02_BACKEND/semantic_runtime/historical_removed.py'] = 'missing-file-pin'
    engine.write_text(json.dumps(value))
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    manifest = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    return payload, dev, manifest, module, config, value, before


def test_all_prior_field_inconsistencies_together_apply_verify_and_rollback(mixed, capsys):
    payload, dev, manifest, module, config, old_engine, before = mixed
    module.apply(dev, check=True)
    assert all(sha(dev / p) == expected for p, expected in before.items())
    module.apply(dev)
    for row in manifest['files']:
        if row['role'] == 'code': assert sha(dev / row['path']) == row['sha256']
    pipeline = json.loads((dev / '00_SYSTEM/PIPELINE.json').read_text())
    assert {k: v for k, v in pipeline.items() if k != 'engines'} == {k: v for k, v in config.items() if k != 'engines'}
    new_engine = json.loads((dev / config['engines']['test']['manifest']).read_text())
    package_paths = {r['path'] for r in manifest['files'] if r['role'] == 'code'}
    assert {k: v for k, v in old_engine['files'].items() if k not in package_paths} == {k: v for k, v in new_engine['files'].items() if k not in package_paths}
    assert '02_BACKEND/semantic_runtime/field_extension.py' not in new_engine['files']
    base = module.dependency(); report = base.engine_plan(dev)
    assert not report['changed_code'] and not report['engine_manifests']
    assert report['serving_verified'] is False
    assert {r['kind'] for r in report['preserved_existing_drift']} >= {'code', 'schema', 'unlisted'}
    for p, expected in before.items():
        if p not in package_paths and not p.startswith('02_BACKEND/ENGINES/') and p != '00_SYSTEM/PIPELINE.json': assert sha(dev / p) == expected
    base.rollback(next((dev / '.genos-pipeline-optimization-backups').iterdir()))
    assert all(sha(dev / p) == expected for p, expected in before.items())
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()
    assert 'EXISTING STATE PRESERVED' in capsys.readouterr().out


def test_unknown_package_file_not_overwritten_even_when_baseline_is_mixed(mixed):
    payload, dev, _, module, _, _, _ = mixed
    target = dev / '02_BACKEND/semantic_runtime/fulltext.py'; target.write_text(target.read_text() + '\n# unknown package change\n')
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='FILE_DRIFT'): module.apply(dev)
    assert all(sha(dev / p) == expected for p, expected in before.items())


def test_new_outside_package_change_aborts_without_overwriting_it(mixed, monkeypatch):
    payload, dev, _, module, _, _, _ = mixed
    base = module.dependency(); copy = base.atomic_copy
    extension = dev / '02_BACKEND/semantic_runtime/field_extension.py'
    def concurrent(source, target):
        copy(source, target)
        if str(target).endswith('lawrag/pipeline/glossary_linking.py'):
            extension.write_text('field = 2\n')
    monkeypatch.setattr(base, 'atomic_copy', concurrent)
    monkeypatch.setattr(module, 'dependency', lambda: base)
    with pytest.raises(ValueError, match='Concurrent change outside package'): module.apply(dev)
    assert extension.read_text() == 'field = 2\n'
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()


def test_concurrent_metadata_is_preserved_on_rollback(mixed, monkeypatch):
    payload, dev, _, module, _, _, _ = mixed
    base = module.dependency(); copy = base.atomic_copy
    pipeline = dev / '00_SYSTEM/PIPELINE.json'
    def concurrent(source, target):
        copy(source, target)
        if str(target).endswith('lawrag/pipeline/glossary_linking.py'):
            config = json.loads(pipeline.read_text()); config['external_edit'] = True; pipeline.write_text(json.dumps(config))
    monkeypatch.setattr(base, 'atomic_copy', concurrent); monkeypatch.setattr(module, 'dependency', lambda: base)
    with pytest.raises(ValueError, match='Concurrent engine metadata drift'): module.apply(dev)
    assert json.loads(pipeline.read_text())['external_edit'] is True


def test_package_bytes_unchanged_except_adapter_and_guide():
    with zipfile.ZipFile(pack.PREVIOUS) as old, zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as new:
        for name in old.namelist():
            if name not in {'APPLY_R2.py', 'GUIDE_UTF8.txt', 'CODE_MANIFEST.json'}: assert old.read(name) == new.read(name)
