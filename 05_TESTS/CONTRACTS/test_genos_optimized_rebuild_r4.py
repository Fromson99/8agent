"""Reproduce both photographed drifts, then apply and roll back exact field bytes."""
import json
from pathlib import Path
import zipfile
import pytest
from semantic_runtime.contracts import sha
from test_genos_optimized_rebuild_r3 import legacy
import test_genos_optimized_rebuild_r3 as prior_tests
import genos_optimization_apply_r3 as apply3
import package_genos_optimized_rebuild_r4 as pack


@pytest.fixture
def photographed(legacy):
    payload, dev, _, _ = legacy
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z:
        z.extractall(payload)
        for path in pack.FIELD_FILES:
            (dev / path).write_bytes(z.read('field-predecessors/' + path))
    manifest = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    before = {str(p.relative_to(dev)): sha(p) for p in dev.rglob('*') if p.is_file()}
    return payload, dev, manifest, before


def test_reproduce_photo_then_accept_only_the_verified_patch_bytes(photographed):
    payload, dev, manifest, before = photographed
    old = json.loads((payload / 'CODE_MANIFEST.json').read_text())
    for row in old['files']:
        if row['path'] in pack.FIELD_FILES:
            row['allowed_predecessors'].remove(pack.FIELD_FILES[row['path']][1])
    (payload / 'CODE_MANIFEST.json').write_text(json.dumps(old))
    with pytest.raises(ValueError, match='FILE_DRIFT'):
        apply3.preflight(dev)
    report = json.loads((payload.parent / 'field-code-preflight.json').read_text())
    assert {r['path'] for r in report['drift']} == set(pack.FIELD_FILES)
    (payload / 'CODE_MANIFEST.json').write_text(json.dumps(manifest))
    report = apply3.preflight(dev)
    assert not report['drift']
    for row in report['files']:
        if row['path'] in pack.FIELD_FILES:
            assert row['actual_sha256'] == pack.FIELD_FILES[row['path']][1]
    assert all(sha(dev / p) == expected for p, expected in before.items())


def test_photographed_transition_and_rollback(photographed, monkeypatch):
    prior_tests.test_apply_legacy_transition_then_restore_all_original_bytes(photographed, monkeypatch)


def test_unknown_change_still_rejected_and_preserved(photographed, capsys):
    payload, dev, _, _ = photographed
    target = dev / '02_BACKEND/semantic_runtime/fulltext.py'
    target.write_text(target.read_text() + '\n# unrecognized change\n')
    actual = target.read_bytes()
    with pytest.raises(ValueError, match='no files applied'):
        apply3.apply(dev, check=True)
    assert target.read_bytes() == actual
    assert not (dev / '.genos-pipeline-optimization-backups').exists()
    assert sha(target) in capsys.readouterr().out


def test_core_bytes_preserved_only_two_predecessors_added_and_script_order():
    with zipfile.ZipFile(pack.PREVIOUS) as old, zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as new:
        old_rows = json.loads(old.read('CODE_MANIFEST.json'))['files']
        rows = {r['path']: r for r in json.loads(new.read('CODE_MANIFEST.json'))['files']}
        for row in old_rows:
            path = row['path']
            if row['role'] == 'code':
                assert new.read(path) == old.read(path)
                extra = set(rows[path].get('allowed_predecessors', [])) - set(row.get('allowed_predecessors', []))
                assert extra == ({pack.FIELD_FILES[path][1]} if path in pack.FIELD_FILES else set())
        for row in rows.values():
            assert __import__('hashlib').sha256(new.read(row['path'])).hexdigest() == row['sha256']
            assert Path(row['path']).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
    script = (pack.OUT / (pack.STEM + '.txt')).read_text()
    assert script.index('run_stage code-preflight') < script.index('run_stage stop-old')
    assert 'financial-risk-success-20261002-opt-r4' in script
