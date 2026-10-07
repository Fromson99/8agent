"""Whole code replacement: preserve onsite data and recover any partial change."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('code_replace', ROOT / '06_TOOLS/OFFLINE/genos_code_replace.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def fixture(tmp_path):
    root, bundle = tmp_path / 'workspace', tmp_path / 'bundle'
    root.mkdir(); bundle.mkdir()
    original = {'service.py': 'old service', '02_BACKEND/obsolete.py': 'old backend',
                '06_TOOLS/custom.sh': 'old custom', '00_SYSTEM/config.json': '{}',
                '.env': 'SECRET=synthetic', '.venv/marker': 'venv', '.git/marker': 'git',
                '01_DATA/PDF/internal/mock.pdf': 'synthetic input',
                '01_DATA/TERM/old/result.json': 'old output', 'GENOS_DATA/CURRENT.json': 'old binding'}
    for name, text in original.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    files = {'service.py': b'value=1\n', '02_BACKEND/new.py': b'value=2\n',
             '00_SYSTEM/config.json': b'{"new": true}', '06_TOOLS/new.py': b'value=3\n'}
    with zipfile.ZipFile(bundle / 'code.zip', 'w') as z:
        for name, data in files.items():z.writestr(name, data)
        z.writestr('CODE_MANIFEST.json', json.dumps({'files': [
            {'path': n, 'sha256': hashlib.sha256(b).hexdigest()} for n, b in files.items()]}))
    (bundle / 'DELIVERY.json').write_text(json.dumps({'id': 'synthetic',
        'code_zip_sha256': hashlib.sha256((bundle / 'code.zip').read_bytes()).hexdigest()}))
    return root, bundle, original


def original_intact(root, original):
    for name, text in original.items():assert (root / name).read_text() == text


def test_replace_repeat_and_restore(fixture):
    root, bundle, original = fixture
    installer.install(root, bundle)
    original_intact(root, original)
    backup = installer.install(root, bundle, True)
    assert not (root / '02_BACKEND/obsolete.py').exists()
    assert (backup / 'old/06_TOOLS/custom.sh').read_text() == 'old custom'
    for name in original:
        if name.split('/')[0] not in {'00_SYSTEM', '02_BACKEND', '06_TOOLS', 'service.py'}:
            assert (root / name).read_text() == original[name]
    cache = root / '02_BACKEND/__pycache__'; cache.mkdir(); (cache / 'new.pyc').write_bytes(b'cache')
    assert installer.install(root, bundle, True) == backup
    installer.rollback(backup)
    original_intact(root, original)
    assert not (root / '02_BACKEND/new.py').exists()
    installer.rollback(backup)


def test_rollback_refuses_new_user_edits(fixture):
    root, bundle, original = fixture
    backup = installer.install(root, bundle, True)
    (root / '02_BACKEND/new.py').write_text('user change')
    with pytest.raises(ValueError, match='Changed code'):
        installer.rollback(backup)
    assert (root / '02_BACKEND/new.py').read_text() == 'user change'
    assert (root / '.env').read_text() == original['.env']


def test_failure_between_renames_restores_everything(fixture, monkeypatch):
    root, bundle, original = fixture
    move = installer.move
    calls = 0
    def interrupted(source, destination):
        nonlocal calls
        calls += 1
        if calls == 6:raise OSError('synthetic interrupted move')
        move(source, destination)
    monkeypatch.setattr(installer, 'move', interrupted)
    with pytest.raises(OSError, match='synthetic interrupted'):
        installer.install(root, bundle, True)
    original_intact(root, original)
    assert not (root / '02_BACKEND/new.py').exists()


def test_payload_tamper_does_not_modify_code(fixture):
    root, bundle, original = fixture
    with (bundle / 'code.zip').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError, match='SHA256'):
        installer.install(root, bundle, True)
    original_intact(root, original)


def test_syntax_error_names_file_and_stops_before_backup(fixture):
    root, bundle, original = fixture
    with zipfile.ZipFile(bundle / 'code.zip') as z:
        files = {n: z.read(n) for n in z.namelist()}
    files['02_BACKEND/new.py'] = b'def broken(:\n'
    manifest = json.loads(files['CODE_MANIFEST.json'])
    for row in manifest['files']:
        if row['path'] == '02_BACKEND/new.py':
            row['sha256'] = hashlib.sha256(files[row['path']]).hexdigest()
    files['CODE_MANIFEST.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(bundle / 'code.zip', 'w') as z:
        for n, raw in files.items():z.writestr(n, raw)
    delivery = json.loads((bundle / 'DELIVERY.json').read_text())
    delivery['code_zip_sha256'] = hashlib.sha256((bundle / 'code.zip').read_bytes()).hexdigest()
    (bundle / 'DELIVERY.json').write_text(json.dumps(delivery))
    with pytest.raises(ValueError, match='Python syntax: 02_BACKEND/new.py:1'):
        installer.install(root, bundle, True)
    assert not (root / '09_ARTIFACTS/BACKUPS').exists()
    original_intact(root, original)


def test_code_symlink_is_rejected_without_writes(fixture, tmp_path):
    root, bundle, original = fixture
    (root / '02_BACKEND/foreign').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='Symlink'):
        installer.install(root, bundle, True)
    original_intact(root, original)


def test_recover_after_hard_interruption(fixture, monkeypatch):
    root, bundle, original = fixture
    move, rollback = installer.move, installer.rollback
    def die(source, destination):
        if source == root / 'service.py':raise OSError('power loss')
        move(source, destination)
    monkeypatch.setattr(installer, 'move', die)
    monkeypatch.setattr(installer, 'rollback', lambda folder: None)
    with pytest.raises(OSError):installer.install(root, bundle, True)
    with pytest.raises(ValueError, match='Recover previous'):
        installer.install(root, bundle, True)
    monkeypatch.setattr(installer, 'move', move)
    backup = next((root / '09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
    rollback(backup)
    original_intact(root, original)


def full_archive(bundle, files):
    path = bundle / 'full.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('CODE_MANIFEST.json', json.dumps({'format': '8agent-code/1', 'files': [
            {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            for name, raw in files.items()]}))
    return path


def test_full_overlay_repeat_and_rollback_preserve_environment_data_and_js(fixture):
    root, bundle, original = fixture
    js = root / '02_BACKEND/viewer.js'; js.write_text('preserved')
    archive = full_archive(bundle, {'service.py': b'VALUE=1800\n',
        '02_BACKEND/new.py': b'VALUE=1800\n', '08_DEPLOYMENT/GENOS/workflow/example.py': b'VALUE=2100\n'})
    backup = installer.install(root, bundle, True, archive=archive)
    assert (root / 'service.py').read_text() == 'VALUE=1800\n'
    assert (root / '.env').read_text() == original['.env']
    assert (root / 'GENOS_DATA/CURRENT.json').read_text() == original['GENOS_DATA/CURRENT.json']
    assert js.read_text() == 'preserved'
    assert installer.install(root, bundle, True, archive=archive) == backup
    installer.rollback(backup)
    original_intact(root, original)
    assert not (root / '02_BACKEND/new.py').exists()
    assert js.read_text() == 'preserved'


@pytest.mark.parametrize('name', ['.env', '01_DATA/RAW/private.json', '02_BACKEND/private.js', '../escape.py'])
def test_full_overlay_rejects_private_data_and_unsafe_paths_before_writing(fixture, name):
    root, bundle, original = fixture
    archive = full_archive(bundle, {name: b'VALUE=1\n'})
    with pytest.raises(ValueError):
        installer.install(root, bundle, True, archive=archive)
    original_intact(root, original)


def test_full_overlay_failure_recovers_before_any_second_install(fixture, monkeypatch):
    root, bundle, original = fixture
    archive = full_archive(bundle, {'service.py': b'VALUE=1800\n', '02_BACKEND/new.py': b'VALUE=1800\n'})
    move = installer.move
    def fail(source, destination):
        if source == root / 'service.py':
            raise OSError('synthetic full update interruption')
        move(source, destination)
    monkeypatch.setattr(installer, 'move', fail)
    with pytest.raises(OSError):
        installer.install(root, bundle, True, archive=archive)
    original_intact(root, original)
    assert not (root / '02_BACKEND/new.py').exists()
