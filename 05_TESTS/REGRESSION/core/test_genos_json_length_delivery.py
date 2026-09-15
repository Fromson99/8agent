"""Exercise the delivered archive and inherited safe installer."""
import json
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
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-json-length-20260910.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_json_length.sh'


@pytest.fixture(autouse=True)
def delivered(monkeypatch):
    monkeypatch.setattr(prior, 'PATCH', PATCH)
    monkeypatch.setattr(prior, 'INSTALLER', INSTALLER)
    monkeypatch.setattr(prior, 'LATEST', ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-external-only-20260910.zip')


def test_only_scoped_payload_changed():
    import ast
    with zipfile.ZipFile(PATCH) as current, zipfile.ZipFile(prior.LATEST) as old:
        changes = {n for n in current.namelist() if n not in old.namelist() or current.read(n) != old.read(n)}
        assert changes == {'patch-manifest.json', '02_BACKEND/lawrag/pipeline/genos_build.py',
            '02_BACKEND/lawrag/pipeline/genos_batch.py', '02_BACKEND/lawrag/pipeline/genos_authoring_runtime.py',
            '06_TOOLS/COMMANDS/genos_build_all.py', '07_DOCS/REFERENCE/OPERATIONS/GENOS_JSON_LENGTH.md'}
        for name in changes - {'patch-manifest.json'}:
            assert current.read(name) == (ROOT / name).read_bytes()
        for name in current.namelist():
            if name.endswith('.py'):
                ast.parse(current.read(name), filename=name, feature_version=(3, 11))


def test_latest_host_requirements_and_data_preserved(tmp_path):
    root = prior.host(tmp_path, latest=True)
    requirement = root / 'requirements-pipeline.txt'
    requirement.write_text('# onsite dependency repair\n')
    assert prior.run(root).returncode == 0
    assert requirement.read_text() == '# onsite dependency repair\n'
    assert '--exclude-internal' in (root / '06_TOOLS/COMMANDS/genos_data_e2e.sh').read_text()
