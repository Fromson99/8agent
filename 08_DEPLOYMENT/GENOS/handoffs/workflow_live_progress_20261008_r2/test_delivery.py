"""Validate the exact editor-file preparation TXT without mutating backend/data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

OUT = Path(__file__).resolve().parent
NAME = 'GENOS_WORKFLOW_LIVE_CARDS_20261008_R2'


def prepare(dev):
    env = {**os.environ, 'GENOS_DEV_ROOT': str(dev)}
    return subprocess.run(['bash', str(OUT / (NAME + '_PREPARE.txt'))],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)


def test_archive_identity_and_all_members():
    hand = json.loads((OUT / 'HANDOFF.json').read_bytes())
    archive = OUT / (NAME + '_EDITOR.zip')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == hand['editor_zip_sha256']
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not [n for n in z.namelist() if Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}]
        for name in z.namelist():
            assert z.read(name) == (OUT / name).read_bytes()
        assert z.read(NAME + '_PASTE_ALL.txt').endswith(z.read('genos_rag_chat.py'))
    check = subprocess.run(['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=OUT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert check.returncode == 0, check.stdout


def test_exact_prepare_replays_idempotently_and_preserves_existing_dev(tmp_path):
    dev = tmp_path / 'existing DEV with spaces'
    dev.mkdir()
    before = {'service.py': b'existing backend\n', 'CURRENT': b'original generation\n',
        'history.db': b'existing case history\n'}
    for name, data in before.items():
        (dev / name).write_bytes(data)
    first = prepare(dev)
    assert first.returncode == 0, first.stdout
    assert 'EDITOR_FILES_READY' in first.stdout and 'EDITOR_FILES_VERIFIED' in first.stdout
    assert 'EXIT=0' in first.stdout
    output = dev / 'TRANSFER/workflow-live-cards-r2-editor'
    assert (output / (NAME + '_PASTE_ALL.txt')).read_bytes() == (OUT / (NAME + '_PASTE_ALL.txt')).read_bytes()
    second = prepare(dev)
    assert second.returncode == 0, second.stdout
    assert all((dev / name).read_bytes() == raw for name, raw in before.items())
    logs = list((dev / 'TRANSFER/workflow-live-cards-r2-logs').glob('*.log'))
    assert len(logs) == 2
    assert all('EDITOR_FILES_READY' in log.read_text() and 'EXIT=0' in log.read_text() for log in logs)


def test_changed_editor_file_is_preserved_with_persistent_failure_log(tmp_path):
    dev = tmp_path / 'DEV'
    first = prepare(dev)
    assert first.returncode == 0, first.stdout
    paste = dev / 'TRANSFER/workflow-live-cards-r2-editor' / (NAME + '_PASTE_ALL.txt')
    changed = paste.read_bytes() + b'\n# user change preserved\n'
    paste.write_bytes(changed)
    second = prepare(dev)
    assert second.returncode != 0
    assert 'Existing different editor file preserved' in second.stdout
    assert paste.read_bytes() == changed
    logs = list((dev / 'TRANSFER/workflow-live-cards-r2-logs').glob('*.log'))
    assert any('EXIT=1' in log.read_text() for log in logs)


def test_prepare_rejects_member_symlink_without_writing_its_target(tmp_path):
    dev = tmp_path / 'DEV'
    output = dev / 'TRANSFER/workflow-live-cards-r2-editor'
    output.mkdir(parents=True)
    target = tmp_path / 'protected.py'
    target.write_bytes(b'preserved\n')
    (output / 'genos_rag_chat.py').symlink_to(target)
    result = prepare(dev)
    assert result.returncode != 0
    assert 'Existing symlink preserved' in result.stdout
    assert target.read_bytes() == b'preserved\n'
