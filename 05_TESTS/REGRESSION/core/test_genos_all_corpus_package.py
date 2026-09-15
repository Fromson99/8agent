"""Exact delivered ZIP installation and isolated baseline contracts."""
import pytest
from . import test_genos_data_folders_package as previous
from . import test_genos_build_package as base


@pytest.fixture
def patched(monkeypatch):
    patch = base.ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-all-corpus-20260909.zip'
    installer = base.ROOT / '06_TOOLS/COMMANDS/genos_apply_all_corpus.sh'
    for module in (base, previous):
        monkeypatch.setattr(module, 'PATCH', patch)
        monkeypatch.setattr(module, 'INSTALLER', installer)


@pytest.mark.parametrize('case', ['original', 'e2e', 'modified', 'symlink', 'corrupt'])
def test_delivery_safety(tmp_path, patched, case):
    base.test_patch_preserves_existing_state(tmp_path, case)


def test_isolated_zip(tmp_path, patched):
    base.test_mailed_bundle_plus_patch_runs_without_checkout_dependencies(tmp_path)
    import inspect
    import os
    import subprocess
    import sys
    from .test_genos_all_corpus import fixture_corpus, save
    from .test_genos_build import Fake, XML, BODY
    root = tmp_path / 'DEV'
    code = ('import json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
            'from lawrag.pipeline import genos_build as build, genos_corpus as corpus\n')
    code += 'XML=' + repr(XML) + '\nBODY=' + repr(BODY) + '\n'
    code += inspect.getsource(Fake) + '\n' + inspect.getsource(save) + '\n' + inspect.getsource(fixture_corpus)
    code += '\nraw=fixture_corpus(Path("data"))\nplan,report=corpus.collect(raw)\nassert report["ok"],report["errors"]\n'
    code += 'args=build.parser().parse_args(["build","--build-dir","data/builds/all","--model-revision","fixture","--execute"])\n'
    code += 'args.bindings=None\nassert build.execute(args,prepared_plan=plan,provider_factory=Fake)["counts"]["document"]==8\n'
    # Fixture uses absolute manifest paths, as bootstrap does on the GENOS host.
    code = code.replace('fixture_corpus(Path("data"))', 'fixture_corpus(Path("data").resolve())')
    result = subprocess.run([sys.executable, '-c', code], cwd=root, text=True, capture_output=True,
                            env={**os.environ, 'PYTHONPATH': str(root / '02_BACKEND'),
                                 'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)})
    assert result.returncode == 0, result.stdout + result.stderr


def test_previous_schema_upgrade(tmp_path, patched):
    previous.test_previous_schema_patch_upgrade(tmp_path)
