"""Install the actual cumulative staged ZIP; no private model calls."""
import ast
import json
import os
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
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-staged-authoring-20260910.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_staged_authoring.sh'


@pytest.fixture(autouse=True)
def delivered(monkeypatch):
    monkeypatch.setattr(prior, 'PATCH', PATCH)
    monkeypatch.setattr(prior, 'INSTALLER', INSTALLER)
    monkeypatch.setattr(prior, 'LATEST', ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-korean-progress-20260910.zip')


def test_scoped_payload_and_python311():
    with zipfile.ZipFile(PATCH) as current, zipfile.ZipFile(prior.LATEST) as old:
        changes = {n for n in current.namelist() if n not in old.namelist() or current.read(n) != old.read(n)}
        assert changes == {'patch-manifest.json', '02_BACKEND/lawrag/pipeline/genos_build.py',
            '02_BACKEND/lawrag/pipeline/genos_batch.py', '02_BACKEND/lawrag/pipeline/genos_authoring_runtime.py',
            '02_BACKEND/lawrag/pipeline/genos_staged.py', '06_TOOLS/pipeline.py',
            '06_TOOLS/COMMANDS/genos_data_e2e.sh', '07_DOCS/REFERENCE/OPERATIONS/GENOS_STAGED_AUTHORING.md'}
        # Historical delivery is immutable; a later patch may legitimately change
        # checkout files. Validate the archived receipt, not latest working bytes.
        import hashlib
        manifest = json.loads(current.read('patch-manifest.json'))
        for name in changes - {'patch-manifest.json'}:
            assert hashlib.sha256(current.read(name)).hexdigest() == manifest['files'][name]['sha256']
        for name in current.namelist():
            if name.endswith('.py'):
                ast.parse(current.read(name), filename=name, feature_version=(3, 11))


def test_installed_main_and_genos_accept_same_staged_parameter(tmp_path):
    root = prior.host(tmp_path, latest=True)
    assert prior.run(root).returncode == 0
    for cmd in ([sys.executable, str(root / '06_TOOLS/pipeline.py'), 'build-data'],
                ['bash', str(root / '06_TOOLS/COMMANDS/genos_data_e2e.sh')]):
        result = subprocess.run([*cmd, '--help'], cwd=root, capture_output=True, text=True)
        assert result.returncode == 0 and '--extraction-mode staged' in result.stdout
    code = "from lawrag.pipeline.genos_build import parser; from lawrag.pipeline.genos_staged import STAGES; a=parser().parse_args(['build','--build-dir','never-created','--extraction-mode','staged']); assert a.extraction_mode=='staged'; assert len(STAGES)==4"
    result = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True,
                            env={**os.environ, 'PYTHONPATH': str(root / '02_BACKEND')})
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / 'never-created').exists()


def test_b64_installer_matches():
    import base64
    path = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos_apply_staged_authoring.sh.b64.txt'
    assert base64.b64decode(path.read_bytes()) == INSTALLER.read_bytes()


def test_actual_zip_staged_e2e_without_checkout_imports(tmp_path):
    import inspect
    import shutil
    from .test_genos_build import Fake, XML
    from .test_genos_staged import StagedFake
    root = prior.host(tmp_path, latest=True)
    installed = prior.run(root)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    fixture = root / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    fixture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json', fixture)
    raw = root / 'data/corpus/law'; raw.mkdir()
    (raw / 'synthetic.xml').write_text(XML)
    code = 'import json\nfrom types import SimpleNamespace\nfrom pathlib import Path\nfrom lawrag.pipeline import genos_build as build\nfrom lawrag.pipeline.genos_staged import GROUPS\n'
    code += inspect.getsource(Fake) + '\n' + inspect.getsource(StagedFake)
    code += '\nassert str(build.ROOT)==str(Path.cwd())\n'
    code += "args=build.parser().parse_args(['build','--source','external','--input-root',str(Path('data/corpus/law').resolve()),'--build-dir','data/builds/synthetic-staged','--extraction-mode','staged','--execute'])\n"
    code += "args.bindings=None\nresult=build.execute(args,provider_factory=StagedFake)\nassert result['ok'] and not result['activated']\nassert len(Fake.instances[-1].calls)==5\n"
    result = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': str(root / '02_BACKEND'), 'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)})
    assert result.returncode == 0, result.stdout + result.stderr
