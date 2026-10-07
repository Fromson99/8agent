"""Final R4 ZIP/TXT executes actual delivered logging and intent repair."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_genos_selective_handoff import checkout, git, installed, repin, snapshot, CORE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-raw-log-r4'
TXT = OUT / 'GENOS_MODEL_DECISION_REPAIR_RAW_LOG_20260929_R4_APPLY.txt'
BUNDLE_ID = 'genos-llm-raw-log-20260929-r4'


def execute(root, mode='apply', python=sys.executable, ok=True, **extra):
    result = subprocess.run(['bash', str(TXT)], env={**os.environ,
        'DEPLOY_ROOT': str(root), 'PYTHON_BIN': python, 'MODE': mode, **extra},
        capture_output=True, text=True)
    assert (result.returncode == 0) == ok, result.stdout + result.stderr
    return result.stdout + result.stderr


@pytest.mark.parametrize('variant', ['photo', 'r2-photo', 'r3-photo', 'integrated', 'r2-integrated'])
def test_r4_final_zip_preserves_site_code_reapplies_and_rolls_back(checkout, variant):
    if 'integrated' in variant:
        feature = json.loads((OUT / 'bundle/SELECTIVE_MANIFEST.json').read_bytes())['features']['decision-repair']
        base = ROOT / '08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-20260929-r1/code'
        for name in feature['files']:
            (checkout / name).write_bytes((base / name).read_bytes())
        repin(checkout)
    if variant.startswith('r2-'):
        installed(checkout)
    if variant.startswith('r3-'):
        from test_turn_intent_handoff import execute as install_r3
        install_r3(checkout)
    name = '02_BACKEND/semantic_runtime/legal_agent/question_obligations.py'
    path = checkout / name
    path.write_bytes(path.read_bytes() + b'\n# retained field diagnostic\ndef field_diagnostic(): return 17\n')
    repin(checkout)
    before = snapshot(checkout)
    assert 'CHECK_PASS' in execute(checkout, mode='check')
    assert snapshot(checkout) == before
    assert 'APPLIED' in execute(checkout)
    after = snapshot(checkout)
    assert b'def field_diagnostic(): return 17' in after[name]
    allowed = set(json.loads((OUT / 'bundle/SELECTIVE_MANIFEST.json').read_bytes())[
        'features']['decision-repair']['files'])
    changed = {n for n in before if before[n] != after[n]}
    assert all(n in allowed or '/ENGINES/' in n or n == '00_SYSTEM/PIPELINE.json' for n in changed)
    for python in dict.fromkeys([sys.executable, shutil.which('python3.11')]):
        if python:
            assert 'ALREADY_APPLIED' in execute(checkout, python=python)
            assert snapshot(checkout) == after
    CORE.verify_pins(checkout)
    state = checkout / 'TRANSFER' / BUNDLE_ID
    git(checkout, 'add', '-u')
    git(checkout, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'R4 validated synthetic checkout')
    spec = importlib.util.spec_from_file_location('r3_gate', ROOT / '06_TOOLS/COMMANDS/genos_release_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert gate.compare_zip_to_checkout(state / 'applied-code.zip', checkout)['code_files'] >= 5
    assert 'ROLLED_BACK' in execute(checkout, mode='rollback', ROLLBACK_FROM=str(next(state.glob('backup-*'))))
    assert snapshot(checkout) == before


def test_unknown_turn_validator_refused_before_source_writes(checkout):
    path = checkout / '02_BACKEND/semantic_runtime/legal_agent/obligation_protocol.py'
    raw = path.read_bytes().replace(b'def validate_wire(name, value):',
                                   b'def validate_wire(name, value):\n    site_modified = True')
    path.write_bytes(raw)
    repin(checkout)
    before = snapshot(checkout)
    output = execute(checkout, ok=False)
    assert 'unknown decision function; no writes: validate_wire' in output
    assert snapshot(checkout) == before


def run_delivered(checkout, *targets):
    regression = checkout / '05_TESTS/REGRESSION/core'
    regression.mkdir(parents=True, exist_ok=True)
    for name in ('test_genos_llm_raw_log.py', 'test_genos_agent_plain_log.py'):
        shutil.copy2(ROOT / '05_TESTS/REGRESSION/core' / name, regression / name)
    shutil.copytree(ROOT / '05_TESTS/CONTRACTS', checkout / '05_TESTS/CONTRACTS',
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    shutil.copy2(ROOT / '05_TESTS/conftest.py', checkout / '05_TESTS/conftest.py')
    shutil.copy2(ROOT / 'pytest.ini', checkout / 'pytest.ini')
    workspace = json.loads((checkout / '00_SYSTEM/WORKSPACE.json').read_bytes())
    for row in workspace['roots']:
        (checkout / row['canonical_path']).mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *targets], cwd=checkout,
        env={**os.environ, 'LAWRAG_WORKSPACE_ROOT': str(checkout),
             'LAWRAG_TOOL_WORKSPACE_ROOT': str(checkout)}, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_r2_photo_to_r4_runs_real_gateway_http_and_raw_logging(checkout):
    installed(checkout)
    assert 'APPLIED' in execute(checkout, python=shutil.which('python3.11') or sys.executable)
    output = run_delivered(checkout, '05_TESTS/CONTRACTS/test_turn_intent_repair.py',
                           '05_TESTS/REGRESSION/core/test_genos_llm_raw_log.py')
    assert '14 passed' in output


SPEC = json.loads((OUT / 'bundle/SELECTIVE_MANIFEST.json').read_bytes())
sources = {}
for row in SPEC['raw_log_variant_sources']:
    sources.setdefault(row['source_sha256'], row['source'])


@pytest.mark.parametrize('source', list(sources.values()))
def test_approved_live_log_variants_execute_literal_output(checkout, source):
    import zipfile
    name = '02_BACKEND/semantic_runtime/request_report.py'
    if source == 'audit-before':
        raw = (ROOT / '09_ARTIFACTS/AUDITS/20260929-llm-raw-log/before' / name).read_bytes()
    elif source == 'integrated-mail-code.zip':
        with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFFS/20260929-rag-main-integrated/code.zip') as z:
            raw = z.read(name)
    elif source.endswith('.py'):
        raw = (ROOT / source).read_bytes()
    else:
        raw = (ROOT / source / name).read_bytes()
    (checkout / name).write_bytes(raw)
    repin(checkout)
    assert 'APPLIED' in execute(checkout)
    assert '7 passed' in run_delivered(checkout, '05_TESTS/REGRESSION/core/test_genos_llm_raw_log.py')


def test_unknown_journal_reader_refuses_all_writes(checkout):
    path = checkout / '02_BACKEND/semantic_runtime/request_report.py'
    path.write_bytes(path.read_bytes().replace(b'def _poll_journal(self) -> None:',
        b'def _poll_journal(self) -> None:\n        unknown_site_change = True'))
    repin(checkout)
    before = snapshot(checkout)
    output = execute(checkout, ok=False)
    assert 'unknown decision function; no writes: _LiveLog._poll_journal' in output
    assert snapshot(checkout) == before


def test_mailed_viewer_prints_literal_content_and_preserves_file(tmp_path):
    path = tmp_path / 'fixture.llm_raw.jsonl'
    original = ' {\n   "intent": "DRAFT"\n }\r\n' + '가' * 20000
    row = {'request_id': 'req-fixture', 'choices': [{'position': 0,
        'content': original, 'finish_reason': 'content_filter', 'refusal': '거절\n원문'}],
        'received_body': {'unknown_guard_field': 'fixture-policy'}}
    raw = (json.dumps(row, ensure_ascii=False) + '\n').encode()
    path.write_bytes(raw)
    viewer = OUT / 'GENOS_LLM_RAW_VIEW_20260929_R4.txt'
    for python in dict.fromkeys([sys.executable, shutil.which('python3.11')]):
        if python:
            result = subprocess.run(['bash', str(viewer), str(path)], capture_output=True,
                env={**os.environ, 'PYTHON_BIN': python, 'SHOW_BODY': '1'})
            assert result.returncode == 0, result.stderr
            output = result.stdout.decode('utf-8')
            assert original in output and '거절\n원문' in output
            assert 'content_filter' in output and 'fixture-policy' in output
            assert path.read_bytes() == raw
