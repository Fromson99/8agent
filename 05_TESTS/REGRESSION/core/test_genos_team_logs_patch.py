"""The handoff must preserve installed pins and be reversible with new files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches/team_request_logs_20260928_r1'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
GATEWAY = '02_BACKEND/semantic_runtime/legal_agent/gateway.py'
NEW_FILES = ['02_BACKEND/semantic_runtime/request_summary.py',
             '02_BACKEND/semantic_runtime/legal_agent/readable_log.py']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load(PATCH / 'apply.py', 'team_log_installer')
gate = load(PATCH / 'gate.py', 'team_log_gate')


def base_reports():
    parent = PATCH.parent
    values = []
    for name in ['relation_wait_20260928_r1/payload', 'request_unlimited_20260928_r1/payload',
                 'thinking_log_20260928_r2/payload', 'thinking_log_20260928_r2/baseline']:
        values.append((parent / name / REPORT).read_bytes())
    transformer = load(parent / 'thinking_log_20260928_r3/structural_report.py', 'thinking_report_transformer')
    templates = transformer.load_templates(parent / 'thinking_log_20260928_r3')
    values += [transformer.transform(raw, templates) for raw in list(values)]
    return values


def put(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def checkout(root, report):
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    put(root, REPORT, report)
    put(root, GATEWAY, b'# pinned gateway fixture\n')
    put(root, 'unchanged.py', b'FIXTURE = True\n')
    put(root, '.gitignore', b'TRANSFER/\n')
    put(root, 'schema.json', b'{"fixture":true}\n')
    config = {'engines': {}, 'contracts': {'fixture': {'schema_path': 'schema.json',
                  'schema_sha256': installer.sha((root / 'schema.json').read_bytes())}},
              'datasets': {'generation': 'existing-fixture-generation', 'sha256': 'do-not-rewrite'}}
    for ident, files in [('term', [REPORT, GATEWAY, 'unchanged.py']), ('legal', [GATEWAY, 'unchanged.py'])]:
        name = 'engines/' + ident + '.json'
        manifest = {'id': ident, 'files': {f: installer.sha((root / f).read_bytes()) for f in files},
                    'experiment_binding': {'unchanged': True}}
        raw = installer.dump(manifest)
        put(root, name, raw)
        config['engines'][ident] = {'manifest': name, 'sha256': installer.sha(raw)}
    put(root, '00_SYSTEM/PIPELINE.json', installer.dump(config))
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'fixture baseline')
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob('*') if path.is_file() and '.git' not in path.parts}


def invoke(root, *extra, ok=True):
    result = subprocess.run([sys.executable, str(PATCH / 'apply.py'), '--deploy-root', str(root), *extra],
                            capture_output=True, text=True)
    assert (result.returncode == 0) == ok, result.stdout + result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]


@pytest.mark.parametrize('raw', base_reports(), ids=lambda raw: hashlib.sha256(raw).hexdigest()[:10])
def test_supported_baseline_apply_pins_idempotency_commit_gate_and_rollback(tmp_path, raw):
    root = tmp_path / 'DEV'
    before = checkout(root, raw)
    checked = invoke(root, '--check-only')[-1]
    assert checked['status'] == 'CHECK_PASS' and all((root / name).read_bytes() == data for name, data in before.items())
    applied = invoke(root)[-1]
    assert applied['status'] == 'APPLIED' and applied['code_serving_revision'] is None
    assert applied['onsite_workflow_verified'] is False
    assert invoke(root)[-1]['status'] == 'ALREADY_APPLIED'
    config = json.loads((root / '00_SYSTEM/PIPELINE.json').read_bytes())
    assert config['datasets']['sha256'] == 'do-not-rewrite'
    for entry in config['engines'].values():
        manifest_raw = (root / entry['manifest']).read_bytes()
        assert installer.sha(manifest_raw) == entry['sha256']
        manifest = json.loads(manifest_raw)
        assert manifest['experiment_binding'] == {'unchanged': True}
        for name in [REPORT, *NEW_FILES]:
            assert manifest['files'][name] == installer.sha((root / name).read_bytes())
    report = (root / REPORT).read_text()
    assert 'deadline_scope' in report and 'thinking-live-20260928-r3' in report
    with pytest.raises(ValueError, match='uncommitted'):
        gate.compare_zip_to_checkout(Path(applied['gate_zip']), root)
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'team request logs fixture')
    assert gate.compare_zip_to_checkout(Path(applied['gate_zip']), root)['commit'] == git(root, 'rev-parse', 'HEAD')
    invoke(root, '--rollback-from', applied['backup'])
    assert all((root / name).read_bytes() == data for name, data in before.items())
    assert all(not (root / name).exists() for name in NEW_FILES)


@pytest.mark.parametrize('drift', ['report', 'other', 'manifest', 'schema', 'new-file', 'symlink'])
def test_refuses_unknown_versions_drift_and_symlinks_before_code_change(tmp_path, drift):
    root = tmp_path / 'DEV'
    before = checkout(root, base_reports()[0])
    if drift == 'report':
        put(root, REPORT, before[REPORT] + b'\n# unknown edit\n')
    elif drift == 'other':
        put(root, 'unchanged.py', b'FIXTURE = False\n')
    elif drift == 'manifest':
        put(root, 'engines/legal.json', before['engines/legal.json'] + b'\n')
    elif drift == 'schema':
        put(root, 'schema.json', b'{}\n')
    elif drift == 'new-file':
        put(root, NEW_FILES[0], b'# unrelated existing file\n')
    else:
        (root / REPORT).unlink()
        (root / REPORT).symlink_to(root / 'unchanged.py')
    result = invoke(root, ok=False)
    assert not result
    assert (root / '00_SYSTEM/PIPELINE.json').read_bytes() == before['00_SYSTEM/PIPELINE.json']
    assert (root / 'engines/term.json').read_bytes() == before['engines/term.json']
    assert not (root / NEW_FILES[1]).exists()


def test_payload_tamper_and_post_apply_edit_refuse_without_overwrite(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'
    before = checkout(root, base_reports()[0])
    spec = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    spec['files'][REPORT]['new_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='payload hash mismatch'):
        installer.prepare(root, spec)
    assert (root / REPORT).read_bytes() == before[REPORT]
    applied = invoke(root)[-1]
    changed = (root / NEW_FILES[0]).read_bytes() + b'\n# later user edit\n'
    put(root, NEW_FILES[0], changed)
    with pytest.raises(ValueError, match='changed after patch'):
        installer.rollback(root, Path(applied['backup']))
    assert (root / NEW_FILES[0]).read_bytes() == changed
    assert (root / REPORT).read_bytes() == (PATCH / 'payload' / REPORT).read_bytes()
