"""Actual cumulative ZIP installation and isolated stage execution (fake model)."""
import ast
import inspect
import json
import os
import shutil
import subprocess
import sys
import zipfile
import pytest
from . import test_genos_latest_compatible as prior
from .test_genos_latest_compatible import (
    test_install_latest_preserved_and_registry_closed,
    test_failure_is_prewrite_and_unknowns_all_reported,
    test_crlf_known_version_and_check_only,
    test_failed_second_write_rolls_back,
    test_python311_installed_entrypoints,
)

ROOT = prior.ROOT
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-four-stage-20260910.zip'
INSTALLER = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos_apply_four_stage.sh'


@pytest.fixture(autouse=True)
def delivered(monkeypatch):
    monkeypatch.setattr(prior, 'PATCH', PATCH)
    monkeypatch.setattr(prior, 'INSTALLER', INSTALLER)
    monkeypatch.setattr(prior, 'LATEST', ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-staged-authoring-20260910.zip')


def test_zip_hashes_live_files_and_311_syntax():
    import hashlib
    with zipfile.ZipFile(PATCH) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
        for name, entry in manifest['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
            if name.endswith('.py'):
                ast.parse(z.read(name), feature_version=(3, 11))
        for name in ('genos_stages.py', 'genos_progress.py', 'genos_raw_move.py', 'genos_build.py'):
            path = '02_BACKEND/lawrag/pipeline/' + name
            assert z.read(path) == (ROOT / path).read_bytes()


def test_isolated_zip_migration_structure_llm_vector(tmp_path):
    from .test_genos_build import Fake, XML
    from .test_genos_staged import StagedFake
    from .test_genos_four_stage import PhaseFake
    root = prior.host(tmp_path, latest=True)
    result = prior.run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    fixture = root / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    fixture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json', fixture)
    source = root / 'data/corpus/internal/synthetic.xml'
    source.write_text(XML)
    env = {**os.environ, 'PYTHONPATH': str(root / '02_BACKEND'),
           'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)}
    moved = subprocess.run([sys.executable, '06_TOOLS/COMMANDS/genos_move_raw.py', '--apply'],
                            cwd=root, env=env, text=True, capture_output=True)
    assert moved.returncode == 0, moved.stdout + moved.stderr
    assert (root / '01_DATA/RAW/internal/synthetic.xml').read_text() == XML
    checked = subprocess.run(['bash', '06_TOOLS/COMMANDS/genos_data_stages.sh', '--check-only'],
                             cwd=root, env=env, text=True, capture_output=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    code = '''import io, json
from pathlib import Path
from types import SimpleNamespace
from lawrag.pipeline import genos_build as build, genos_stages as stages
from lawrag.pipeline.genos_staged import GROUPS
from lawrag.pipeline.genos_progress import Progress
'''
    code += inspect.getsource(Fake) + '\n' + inspect.getsource(StagedFake) + '\n' + inspect.getsource(PhaseFake)
    code += '''
assert build.ROOT == Path.cwd()
raw = Path('01_DATA/RAW/internal').resolve()
args = build.parser().parse_args(['build', '--input-root', str(raw), '--build-dir', 'unused', '--extraction-mode', 'staged'])
args.bindings = None
data = Path('01_DATA').resolve()
plan = build.inventory(raw, 'internal')
progress = Progress(data / 'LOGS/test-isolated', io.StringIO())
try:
    result = stages.execute(plan, args, data, 'test-isolated', 'all', provider_factory=PhaseFake, progress=progress)
    assert result['ok'], result
    assert [p.kind for p in Fake.instances] == ['llm', 'embed']
    assert not Fake.instances[-1].calls
finally:
    progress.close()
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_installer_b64_and_help(tmp_path):
    import base64
    assert base64.b64decode(INSTALLER.with_name(INSTALLER.name + '.b64.txt').read_bytes()) == INSTALLER.read_bytes()
    root = prior.host(tmp_path, latest=True)
    assert prior.run(root).returncode == 0
    result = subprocess.run([sys.executable, '06_TOOLS/pipeline.py', 'build-data-stages', '--help'],
                             cwd=root, text=True, capture_output=True)
    assert result.returncode == 0 and '--stage' in result.stdout
