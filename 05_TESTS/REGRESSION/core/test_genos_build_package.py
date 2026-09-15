import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-schema-build-20260909.zip'
PRIOR = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-unified-dev-root-20260908.zip'
E2E = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-e2e-patch-20260909.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_schema_build.sh'


@pytest.mark.parametrize('case', ['original', 'e2e', 'modified', 'symlink', 'corrupt'])
def test_patch_preserves_existing_state(tmp_path, case):
    root = tmp_path / 'DEV'; transfer = root / 'TRANSFER'; transfer.mkdir(parents=True)
    shutil.copyfile(PATCH, transfer / PATCH.name)
    shutil.copyfile(INSTALLER, transfer / INSTALLER.name)
    with zipfile.ZipFile(PATCH) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
    for archive in [PRIOR] + ([E2E] if case == 'e2e' else []):
        with zipfile.ZipFile(archive) as z:
            for name in [*manifest['files'], '00_SYSTEM/WORKSPACE.json', '02_BACKEND/semantic_runtime/genos.py']:
                if name in z.namelist():
                    target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
    transport = root / '02_BACKEND/semantic_runtime/genos.py'
    transport.write_text(transport.read_text() + '\n# onsite connection repair\n')
    (root / '.env').write_text('DO_NOT_TOUCH=yes\n')
    victim = root / '06_TOOLS/COMMANDS/genos_unified_pipeline.py'
    if case == 'modified':
        victim.write_text(victim.read_text() + '\n# manual edit\n')
    if case == 'symlink':
        external = tmp_path / 'external.py'; shutil.move(victim, external); victim.symlink_to(external)
    if case == 'corrupt':
        (transfer / PATCH.name).write_bytes(b'not a zip')
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
              if p.is_file() and transfer not in p.parents}
    env = {**os.environ, 'GENOS_SCHEMA_BUILD_ROOT': str(root)}
    run = lambda: subprocess.run(['bash', str(transfer / INSTALLER.name), '--install-only'],
                                cwd=transfer, env=env, text=True, capture_output=True)
    result = run()
    assert hashlib.sha256(transport.read_bytes()).hexdigest() == before[transport]
    assert (root / '.env').read_text() == 'DO_NOT_TOUCH=yes\n'
    if case in {'original', 'e2e'}:
        assert result.returncode == 0, result.stdout + result.stderr
        for name, entry in manifest['files'].items():
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == entry['sha256']
        assert run().returncode == 0
        assert len(list((root / 'runtime/patch-backups').glob('*/receipt.json'))) == 1
    else:
        assert result.returncode != 0
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == fingerprint for p, fingerprint in before.items())
        assert not (root / 'runtime/patch-backups').exists()


def test_mailed_bundle_plus_patch_runs_without_checkout_dependencies(tmp_path):
    from .test_genos_build import Fake, XML
    root = tmp_path / 'DEV'; root.mkdir()
    prefixes = ('00_SYSTEM/', '02_BACKEND/lawrag/',
                '02_BACKEND/semantic_runtime/', '02_BACKEND/ENGINES/')
    with zipfile.ZipFile(PRIOR) as z:
        for name in z.namelist():
            if name.endswith('/'):
                continue
            if name.startswith(prefixes) or name in {'service.py', '02_BACKEND/lawrag/__init__.py'}:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(z.read(name))
    with zipfile.ZipFile(PATCH) as z:
        for name in json.loads(z.read('patch-manifest.json'))['files']:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(z.read(name))
    fixture = root / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    fixture.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json', fixture)
    raw = tmp_path / 'raw'; raw.mkdir(); (raw / 'test.xml').write_text(XML)
    code = 'import json\nfrom types import SimpleNamespace\nfrom lawrag.pipeline import genos_build as build\n'
    code += inspect.getsource(Fake)
    code += '\nargs=build.parser().parse_args(' + repr(['build', '--input-root', str(raw), '--build-dir', str(tmp_path / 'result'),
                                                       '--model-revision', 'fixture-v1', '--execute']) + ')\n'
    code += 'args.bindings=None\nassert build.execute(args,provider_factory=Fake)["ok"]\n'
    env = {**os.environ, 'PYTHONPATH': str(root / '02_BACKEND'), 'LAWRAG_WORKSPACE_ROOT': str(root),
           'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)}
    result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
