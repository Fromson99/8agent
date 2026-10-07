"""Installed report variants preserve onsite changes and require valid pins."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '08_DEPLOYMENT/GENOS/patches'
PATCH = BASE / 'thinking_log_20260928_r3'
TXT = BASE / 'GENOS_THINKING_LOG_20260928_R3_APPLY.txt'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('version', ['latency_20260928_r1', 'latency_20260928_r2',
    'relation_wait_20260928_r1', 'thinking_log_20260928_r2', 'thinking_log_20260928_r3'])
@pytest.mark.parametrize('style', ['unknown_bytes', 'unicode_and_crlf'])
def test_compatible_non_whitelisted_file_preserves_local_changes(version, style):
    source = BASE / version / ('baseline' if version.startswith('thinking_log') else 'payload') / REPORT
    raw = source.read_bytes()
    sentinel = '# 현장 로그 수정 보존\nONSITE_LOG_EXTENSION = 731\n'.encode()
    raw = sentinel + raw + sentinel
    if style == 'unicode_and_crlf':
        raw = raw.replace(b'\n', b'\r\n'); sentinel = sentinel.replace(b'\n', b'\r\n')
    implementation = module('report_transform_fixture', PATCH / 'structural_report.py')
    templates = implementation.load_templates(PATCH)
    after = implementation.transform(raw, templates)
    assert after.startswith(sentinel) and after.endswith(sentinel)
    assert b'thinking-live-20260928-r3' in after
    ast.parse(after, feature_version=(3, 11))
    assert implementation.transform(after, templates) == after


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / 'DEV'; root.mkdir()
    package = tmp_path / 'patch'; shutil.copytree(PATCH, package)
    spec = json.loads((package / 'PATCH_MANIFEST.json').read_bytes())
    for name in spec['files']:
        dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
        data = (PATCH / 'baseline' / name).read_bytes()
        if name == REPORT:
            data += b'\n# Additional onsite display code, unknown to the R2 hash list\nONSITE_LOG_EXTENSION = 731\n'
        dest.write_bytes(data)
    (root / 'other.py').write_text('OTHER_UNCHANGED = True\n')
    manifest = root / '02_BACKEND/ENGINES/fixture.json'; manifest.parent.mkdir(parents=True)
    files = {name: sha((root/name).read_bytes()) for name in [*spec['files'], 'other.py']}
    manifest.write_text(json.dumps({'files': files}, indent=2)+'\n')
    schema = root / '00_SYSTEM/schema.json'; schema.parent.mkdir(); schema.write_text('{}\n')
    (root / '00_SYSTEM/PIPELINE.json').write_text(json.dumps({'engines': {'fixture': {
        'manifest': str(manifest.relative_to(root)), 'sha256': sha(manifest.read_bytes())}},
        'contracts': {'fixture': {'schema_path': str(schema.relative_to(root)),
                                 'schema_sha256': sha(schema.read_bytes())}}})+'\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '00_SYSTEM', '02_BACKEND', 'other.py'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'unknown onsite report with valid engine pins'], check=True)
    implementation = module('report_apply_fixture', package / 'apply.py')
    monkeypatch.setattr(implementation, 'PATCH', package)
    monkeypatch.setattr('sys.argv', ['apply.py', '--deploy-root', str(root)])
    return root, package, implementation


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def test_final_txt_unknown_file_apply_reapply_commit_gate_and_rollback(installed, tmp_path):
    root, package, implementation = installed
    before = snapshot(root)
    env = {**os.environ, 'DEPLOY_ROOT': str(root), 'PYTHON_BIN': sys.executable, 'TMPDIR': str(tmp_path), 'MODE': 'apply'}
    def execute():
        return subprocess.run(['bash', str(TXT)], env=env, capture_output=True, text=True)
    first = execute(); assert first.returncode == 0, first.stdout+first.stderr
    assert 'STRUCTURAL_CHECK_PASS' in first.stdout and 'BACKUP_READY' in first.stdout
    assert b'ONSITE_LOG_EXTENSION = 731' in (root / REPORT).read_bytes()
    assert b'thinking-live-20260928-r3' in (root / REPORT).read_bytes()
    second = execute(); assert second.returncode == 0 and 'ALREADY_APPLIED' in second.stdout
    backups = list((root / 'TRANSFER/thinking-log-20260928-r3').glob('backup-*')); assert len(backups) == 1
    subprocess.run(['git', '-C', str(root), 'add', '00_SYSTEM', '02_BACKEND'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'display edits preserve onsite code'], check=True)
    gate = subprocess.run([sys.executable, str(package/'gate.py'), '--code-only', '--code-zip',
        str(root/'TRANSFER/thinking-log-20260928-r3/applied-code.zip'), '--deploy-root', str(root)], capture_output=True, text=True)
    assert gate.returncode == 0 and 'CODE_CHECK PASS' in gate.stdout, gate.stdout+gate.stderr
    env.update(MODE='rollback', ROLLBACK_FROM=str(backups[0])); restored=execute()
    assert restored.returncode == 0 and 'ROLLED_BACK' in restored.stdout
    assert snapshot(root) == before
    logs = list(tmp_path.glob('genos-thinking-log-r3-*.log'))
    assert len(logs) == 3 and all('FINISHED status=0' in f.read_text() for f in logs)


@pytest.mark.parametrize('kind', ['report_pin', 'unrelated_pin', 'manifest', 'asset'])
def test_invalid_integrity_refuses_before_writes(installed, kind):
    root, package, implementation = installed
    target = {'report_pin': root/REPORT, 'unrelated_pin': root/'other.py',
        'manifest': root/'02_BACKEND/ENGINES/fixture.json', 'asset': package/'REPORT_TEMPLATES.json'}[kind]
    with target.open('ab') as stream: stream.write(b'\n# unexpected change\n')
    before=snapshot(root)
    with pytest.raises(ValueError): implementation.main()
    assert snapshot(root) == before


def test_incompatible_conversion_refuses_without_bypassing_validation():
    implementation = module('report_transform_rejection', PATCH/'structural_report.py')
    raw=(BASE/'latency_20260928_r2/payload'/REPORT).read_bytes()
    raw=raw.replace(b'_live_value(fields[key])', b'_live_value(str(fields[key]))')
    with pytest.raises(ValueError, match='field conversion'):
        implementation.transform(raw, implementation.load_templates(PATCH))


def test_interrupted_write_restores_original_code_and_pins(installed, monkeypatch):
    root, package, implementation=installed
    before=snapshot(root);original=implementation.atomic;failed=False
    def fail_once(path,data):
        nonlocal failed
        if path==root/REPORT and not failed:
            failed=True;raise OSError('simulated report write failure')
        return original(path,data)
    monkeypatch.setattr(implementation,'atomic',fail_once)
    with pytest.raises(OSError): implementation.main()
    assert snapshot(root)==before


def test_rollback_preserves_later_onsite_edits(installed):
    root, package, implementation=installed;implementation.main()
    with (root/REPORT).open('ab') as stream: stream.write(b'\n# later onsite edit\n')
    before=snapshot(root);backup=next((root/'TRANSFER/thinking-log-20260928-r3').glob('backup-*'))
    with pytest.raises(ValueError,match='rollback refused'):implementation.rollback(root,backup)
    assert snapshot(root)==before
