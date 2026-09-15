"""Latest DOC/skip patch safety and frozen mailed dependency compatibility."""
import json
import os
import shutil
import subprocess
import zipfile
import pytest
from . import test_genos_latest_compatible as prior
from .test_genos_latest_compatible import (
    test_install_latest_preserved_and_registry_closed,
    test_failure_is_prewrite_and_unknowns_all_reported,
    test_crlf_known_version_and_check_only,
    test_exact_zip_isolated_full_build,
    test_latest_mail_bytes_and_python311_syntax,
    test_failed_second_write_rolls_back,
    test_python311_installed_entrypoints,
)

ROOT = prior.ROOT
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-doc-skip-20260910.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_doc_skip.sh'


@pytest.fixture(autouse=True)
def delivered(monkeypatch):
    monkeypatch.setattr(prior, 'PATCH', PATCH)
    monkeypatch.setattr(prior, 'INSTALLER', INSTALLER)
    monkeypatch.setattr(prior, 'LATEST', ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-qwen-response-fix-20260910.zip')


@pytest.mark.parametrize('arguments,expected,code', [
    ([], ['--skip-failed', '--check-only'], 0),
    (['--run-id', 'a', '--execute'], ['--run-id', 'a', '--skip-failed'], 0),
    (['--execute', '--resume'], ['--resume', '--skip-failed'], 0),
    (['--execute', '--fail-fast'], [], 0),
    (['--fail-fast'], ['--check-only'], 0),
    (['--execute', '--skip-failed'], ['--skip-failed'], 0),
    (['--execute', '--check-only'], [], 2),
    (['--resume'], [], 2),
])
def test_shell_modes(tmp_path, arguments, expected, code):
    commands = tmp_path / '06_TOOLS/COMMANDS'; commands.mkdir(parents=True)
    script = commands / 'genos_data_e2e.sh'
    with zipfile.ZipFile(PATCH) as z:
        script.write_bytes(z.read('06_TOOLS/COMMANDS/genos_data_e2e.sh'))
    (commands / 'genos_build_all.sh').write_text('for argument in "$@"; do printf "ARG:%s\\n" "$argument"; done\nexit 0\n')
    result = subprocess.run(['bash', str(script), *arguments], text=True, capture_output=True)
    assert result.returncode == code
    assert [line[4:] for line in result.stdout.splitlines() if line.startswith('ARG:')] == expected


def test_install_over_exact_last_mailed_patch(tmp_path):
    root = prior.host(tmp_path, latest=True)
    prior.unpack(ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-data-e2e-20260910.zip', root)
    result = prior.run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ('genos_doc.py', 'genos_batch.py'):
        assert (root / '02_BACKEND/lawrag/pipeline' / name).is_file()


def test_payload_matches_scoped_changes_only():
    with zipfile.ZipFile(PATCH) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
        assert manifest['scope'] == 'DATA_BUILD_DOC_SKIP_CATALOG_NO_OQL_NO_ANSWER'
        for name in ('02_BACKEND/lawrag/pipeline/genos_doc.py', '02_BACKEND/lawrag/pipeline/genos_batch.py',
                     '02_BACKEND/lawrag/pipeline/genos_build.py', '02_BACKEND/lawrag/pipeline/genos_corpus.py',
                     '06_TOOLS/COMMANDS/genos_build_all.py', '06_TOOLS/COMMANDS/genos_data_e2e.sh'):
            # Historical mailed bytes stay immutable when a later patch changes checkout.
            assert prior.sha(z.read(name)) == manifest['files'][name]['sha256']
        assert not any(n.startswith(('data/', '01_DATA/', '.git/', '.env')) for n in z.namelist())


def test_installed_all_source_cli_partial_accounting(tmp_path):
    import inspect
    import sys
    from .test_genos_all_corpus import fixture_corpus, save
    from .test_genos_build import Fake, XML, BODY
    root = prior.host(tmp_path, latest=True)
    result = prior.run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    fixture = '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    target = root / fixture
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / fixture).read_bytes())
    code = ('import json,runpy,sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
            'from lawrag.pipeline import genos_build as build,genos_corpus as corpus,genos_batch as batch\n')
    code += 'XML=' + repr(XML) + '\nBODY=' + repr(BODY) + '\n'
    code += inspect.getsource(Fake) + '\n' + inspect.getsource(save) + '\n' + inspect.getsource(fixture_corpus)
    code += '\nraw=fixture_corpus(Path("data").resolve())\nsave(raw/"internal/bad.xml","bad XML")\nsave(raw/"internal/bad.gul","unsupported")\n'
    code += 'original=batch.execute\nbatch.execute=lambda *a,**kw:original(*a,**kw,provider_factory=Fake)\n'
    code += 'sys.argv=["genos_build_all.py","--run-id","installed","--skip-failed","--model-revision","fixture"]\n'
    code += 'try:runpy.run_path("06_TOOLS/COMMANDS/genos_build_all.py",run_name="__main__")\nexcept SystemExit as exc:assert exc.code==0,exc.code\n'
    code += 'r=json.loads(Path("data/builds/installed/batch-result.json").read_text())\n'
    code += 'assert r["status"]=="COMPLETED_WITH_SKIPS",r\nassert r["accounting"]==batch.accounting(8,2),r\nassert len(r["generations"])==8\n'
    result = subprocess.run([sys.executable, '-c', code], cwd=root, text=True, capture_output=True,
                            env={**os.environ, 'PYTHONPATH': str(root / '02_BACKEND'),
                                 'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)})
    assert result.returncode == 0, result.stdout + result.stderr
