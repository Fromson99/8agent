"""GENOS archive boundaries independent of local Git ignore/tracking state."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ignore_ship', ROOT / '06_TOOLS/COMMANDS/code_ship.py')
ship = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ship)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setattr(ship, 'ROOT', root)
    monkeypatch.setattr(ship, 'REQUIRED_FILES', ('service.py',))
    files = {
        'genosIgnore': 'data/\ncache/\n.env*\n!.env.example\nold/*\n!old/current/\n',
        '.gitignore': 'ui/\n',
        'service.py': 'answer = 42\n',
        'ui/nav.js': 'console.log("kept");\n',
        'data/original.json': '{}',
        'old/retired/module.py': 'old = True\n',
        'old/current/module.py': 'current = True\n',
        '.env': 'SYNTHETIC=secret\n',
        '.env.example': 'SYNTHETIC=\n',
        'credentials.pem': 'synthetic',
    }
    for name, value in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
    return root


def test_full_archive_respects_negation_keeps_js_and_ignores_local_git_rules(workspace, tmp_path):
    archive = ship.pack(tmp_path / 'code.zip', workspace / 'genosIgnore')
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {
            'genosIgnore', '.gitignore', 'service.py', 'ui/nav.js',
            'old/current/module.py', '.env.example', ship.MANIFEST,
        }
    ship.verify(archive)


def test_ignored_symlink_is_not_followed_but_selected_symlink_is_rejected(workspace, tmp_path):
    (workspace / 'cache').symlink_to(tmp_path, target_is_directory=True)
    ship._ignore_files(workspace / 'genosIgnore')
    (workspace / 'foreign').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match='심볼릭 링크'):
        ship._ignore_files(workspace / 'genosIgnore')


def test_required_file_cannot_be_excluded(workspace):
    with (workspace / 'genosIgnore').open('a') as f:
        f.write('service.py\n')
    with pytest.raises(RuntimeError, match='service.py'):
        ship._ignore_files(workspace / 'genosIgnore')


def test_verify_rejects_excluded_file_even_with_matching_manifest(workspace, tmp_path):
    archive = ship.pack(tmp_path / 'original.zip', workspace / 'genosIgnore')
    with zipfile.ZipFile(archive) as z:
        payloads = {name: z.read(name) for name in z.namelist()}
    payloads['data/injected.json'] = b'{}'
    manifest = json.loads(payloads[ship.MANIFEST])
    manifest['files'].append({'path': 'data/injected.json', 'bytes': 2,
                              'sha256': ship._sha256(b'{}')})
    payloads[ship.MANIFEST] = json.dumps(manifest).encode()
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        for name, raw in payloads.items():
            z.writestr(name, raw)
    with pytest.raises(RuntimeError, match='제외 규칙 위반'):
        ship.verify(bad)
