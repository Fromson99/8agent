"""Strict pre-audit code migration and complete diagnostics before worker interruption."""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest
from semantic_runtime.contracts import sha

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '06_TOOLS/OFFLINE'))
import genos_optimization_apply_r3 as apply3
import package_genos_optimized_rebuild_r3 as pack


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    payload = tmp_path / 'payload'
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z:
        z.extractall(payload)
    dev = tmp_path / 'DEV'; dev.mkdir()
    manifest = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    with zipfile.ZipFile(pack.LEGACY) as z:
        for row in manifest['files']:
            if row['role'] != 'code' or not row['path'].startswith('02_BACKEND/'):
                continue
            if row['path'] not in z.namelist():
                continue
            destination = dev / row['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(z.read(row['path']))
    config = dev / '00_SYSTEM/PIPELINE.json'; config.parent.mkdir(); config.write_text('{"before":true}')
    monkeypatch.setattr(apply3, 'HERE', payload)
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    return payload, dev, manifest, before


def test_reproduces_r2_rejection_of_the_real_retained_delivery(legacy):
    payload, dev, manifest, before = legacy
    r2 = apply3.dependency()
    old = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    for row in old['files']:
        if row['path'] in pack.LEGACY_FILES:
            row['allowed_predecessors'].remove(pack.LEGACY_FILES[row['path']])
    (payload / 'CODE_MANIFEST.json').write_text(json.dumps(old))
    with pytest.raises(ValueError, match='FILE_DRIFT: 02_BACKEND/lawrag/pipeline/term_generation.py'):
        r2.apply(dev, check=True)
    assert all(sha(dev / path) == expected for path, expected in before.items())
    assert not (dev / '.genos-pipeline-optimization-backups').exists()


def test_r3_accepts_exact_known_legacy_sha_and_records_all_actual_files(legacy, capsys):
    payload, dev, manifest, before = legacy
    report = apply3.preflight(dev)
    assert not report['drift']
    rows = {r['path']: r for r in report['files']}
    for path, expected in pack.LEGACY_FILES.items():
        assert rows[path]['actual_sha256'] == expected and rows[path]['accepted']
    assert rows['02_BACKEND/semantic_runtime/navigation_storage.py']['actual_sha256'] is None
    assert all(sha(dev / path) == expected for path, expected in before.items())
    assert 'actual=ceab4c33' in capsys.readouterr().out


def test_unknown_field_code_is_preserved_with_source_diff_and_hash_report(legacy, capsys):
    payload, dev, manifest, before = legacy
    target = dev / '02_BACKEND/lawrag/pipeline/term_generation.py'
    target.write_text(target.read_text() + '\n# unknown field change\n')
    changed = target.read_bytes()
    with pytest.raises(ValueError, match='no files applied'):
        apply3.apply(dev, check=True)
    assert target.read_bytes() == changed
    assert not (dev / '.genos-pipeline-optimization-backups').exists()
    report = json.loads((payload.parent / 'field-code-preflight.json').read_text())
    assert report['drift'][0]['actual_sha256'] == sha(target)
    archives = list(payload.parent.glob('GENOS_OPTIMIZATION_FIELD_DRIFT_*.zip'))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as z:
        assert len(z.namelist()) == 3
        assert z.read('field/02_BACKEND/lawrag/pipeline/term_generation.py') == changed
        assert '-# unknown field change' in z.read('diff/02_BACKEND/lawrag/pipeline/term_generation.py.diff').decode()
        assert not any(Path(n).suffix in {'.sqlite', '.env', '.js'} for n in z.namelist())
    output = capsys.readouterr().out
    assert 'FIELD DRIFT DIAGNOSTIC ZIP ' in output and sha(target) in output


def test_apply_legacy_transition_then_restore_all_original_bytes(legacy, monkeypatch):
    payload, dev, manifest, before = legacy
    base = apply3.dependency()
    def engine(dev, *, apply=False, add_new=False):
        if apply:
            assert add_new
        return {'changed_code': [r['path'] for r in manifest['files'] if r['role'] == 'code'],
                'unlisted_runtime_files': ['02_BACKEND/semantic_runtime/navigation_storage.py'], 'schemas': []}
    monkeypatch.setattr(base, 'engine_plan', engine)
    monkeypatch.setattr(apply3, 'dependency', lambda: base)
    apply3.apply(dev)
    for row in manifest['files']:
        if row['role'] == 'code':
            assert sha(dev / row['path']) == row['sha256']
    assert (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').is_file()
    backup = next((dev / '.genos-pipeline-optimization-backups').iterdir())
    base.rollback(backup)
    assert all(sha(dev / path) == expected for path, expected in before.items())
    assert not (dev / '02_BACKEND/semantic_runtime/navigation_storage.py').exists()
    assert not (dev / '06_TOOLS/OFFLINE/genos_optimized_rebuild.py').exists()


def test_preflight_before_stop_and_only_three_known_predecessors_added():
    script = (pack.OUT / (pack.STEM + '.txt')).read_text()
    assert script.index('run_stage code-preflight') < script.index('run_stage stop-old')
    with zipfile.ZipFile(pack.PREVIOUS) as previous, zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as new:
        m2 = json.loads(previous.read('CODE_MANIFEST.json'))
        m3 = json.loads(new.read('CODE_MANIFEST.json'))
        rows = {r['path']: r for r in m3['files']}
        for row in m2['files']:
            if row['role'] == 'code':
                assert previous.read(row['path']) == new.read(row['path'])
                extra = set(rows[row['path']].get('allowed_predecessors', [])) - set(row.get('allowed_predecessors', []))
                assert extra == ({pack.LEGACY_FILES[row['path']]} if row['path'] in pack.LEGACY_FILES else set())
        for row in m3['files']:
            assert __import__('hashlib').sha256(new.read(row['path'])).hexdigest() == row['sha256']
            assert Path(row['path']).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
