"""Preserve missing historical data pins while rehashing only selected code metadata."""
import importlib.util
import json
import zipfile
import pytest
from semantic_runtime.contracts import sha
from test_genos_optimized_rebuild_r5 import real_checkout
import package_genos_optimized_rebuild_r6 as pack


@pytest.fixture
def historical(real_checkout):
    payload, dev, manifest, _ = real_checkout
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z: z.extractall(payload)
    spec = importlib.util.spec_from_file_location('r6_field_apply', payload / 'APPLY.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    config = dev / '00_SYSTEM/PIPELINE.json'
    value = json.loads(config.read_text())
    value['profiles'] = {'legal-rag': {'nodes': [{'parameters': {'term_agent': {
        'index': {'path': '01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation/navigation', 'manifest_sha256': 'absent-history'},
        'fulltext': {'path': 'fulltext', 'manifest_sha256': 'also-absent'},
        'origin_projections': [{'path': '01_DATA/old-projection.json', 'sha256': 'never-rewrite'}]}}}]}}
    config.write_text(json.dumps(value))
    return payload, dev, manifest, module, value


def test_missing_historical_pin_reproduced_then_code_apply_preserves_profiles(historical):
    payload, dev, manifest, module, old_config = historical
    base = module.dependency()
    with pytest.raises(ValueError, match='FileNotFoundError'):
        base.native_engine_plan(dev, control_dev=dev)
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    module.apply(dev)
    for row in manifest['files']:
        if row['role'] == 'code': assert sha(dev / row['path']) == row['sha256']
    new_config = json.loads((dev / '00_SYSTEM/PIPELINE.json').read_text())
    assert new_config['profiles'] == old_config['profiles']
    assert new_config['contracts'] == old_config['contracts']
    assert new_config['engines'] != old_config['engines']
    report = base.engine_plan(dev)
    assert not report['changed_code'] and not report['engine_manifests']
    assert report['legacy_data_pins_validated'] is False
    assert report['legacy_profiles_preserved'] is True
    backup = next((dev / '.genos-pipeline-optimization-backups').iterdir())
    base.rollback(backup)
    assert all(sha(dev / name) == expected for name, expected in before.items())
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()


def test_unrelated_code_still_rejected_and_exact_original_metadata_restored(historical):
    payload, dev, _, module, _ = historical
    target = dev / '02_BACKEND/semantic_runtime/control.py'
    target.write_text(target.read_text() + '\n# unrelated code drift\n')
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Unrelated engine/schema drift'): module.apply(dev)
    assert all(sha(dev / name) == expected for name, expected in before.items())


def test_schema_drift_still_rejected_without_data_profile_mutation(historical):
    payload, dev, _, module, _ = historical
    schema = dev / '00_SYSTEM/test-schema.json'; schema.write_text('{}')
    pipeline = dev / '00_SYSTEM/PIPELINE.json'
    config = json.loads(pipeline.read_text())
    config['contracts'] = {'test': {'schema_path': str(schema.relative_to(dev)), 'schema_sha256': 'wrong'}}
    pipeline.write_text(json.dumps(config))
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Unrelated engine/schema drift'): module.apply(dev)
    assert all(sha(dev / name) == expected for name, expected in before.items())


def test_core_and_predecessors_identical_only_adapter_changes():
    with zipfile.ZipFile(pack.PREVIOUS) as old, zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as new:
        assert set(old.namelist()) == set(new.namelist())
        for name in old.namelist():
            if name not in {'APPLY_R2.py', 'GUIDE_UTF8.txt', 'CODE_MANIFEST.json'}: assert old.read(name) == new.read(name)
        for row in json.loads(new.read('CODE_MANIFEST.json'))['files']:
            assert __import__('hashlib').sha256(new.read(row['path'])).hexdigest() == row['sha256']
