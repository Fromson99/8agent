"""Validate the mailed E2E launcher's orchestration with a simulated delegate."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HANDOFFS = ROOT / '08_DEPLOYMENT/GENOS/handoffs'
BASE = HANDOFFS / 'reference_build_20261003_r1'
MAIL = HANDOFFS / 'reference_build_mail_20261003_r1'
LAUNCHER = 'GENOS_REFERENCE_E2E_RUN_20261003_R1.txt'


@pytest.fixture
def launch(tmp_path):
    for name in ('GENOS_REFERENCE_BUILD_20261003_R1.zip',
                 'GENOS_REFERENCE_BUILD_20261003_R1.txt'):
        shutil.copyfile(BASE / name, tmp_path / name)
    shutil.copyfile(MAIL / LAUNCHER, tmp_path / LAUNCHER)
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    (binaries / 'python3').symlink_to(sys.executable)
    delegate = binaries / 'bash'
    delegate.write_text('#!' + sys.executable + '\n' + '''
import hashlib,json,os,sys
from pathlib import Path
step=sys.argv[2]
trace=Path(os.environ['TEST_TRACE'])
with trace.open('a') as stream:stream.write(step+'\\n')
if step==os.environ.get('TEST_FAIL_STEP'):sys.exit(7)
if step=='build':
    root=Path(os.environ['GENOS_DATA_ROOT'])/'TERM_RELEASES'/os.environ['GENOS_REUSE_RUN']/'serving'
    generation=root/'baseline/generation'
    generation.mkdir(parents=True)
    manifest=generation/'manifest.json'
    manifest.write_text('{"test_fixture":true}')
    report=root/'offline-e2e.json'
    report.write_text('{"status":"PASS","test_fixture":true}')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    receipt={'completed':True,'serving_verified':True,'offline_e2e':'PASS',
             'settings':{'storage_profile':'compact-v2','fulltext_granularity':'unit'},
             'generation_path':str(generation),'manifest_sha256':sha(manifest),
             'offline_e2e_sha256':sha(report)}
    defect=os.environ.get('TEST_DEFECT')
    if defect=='incomplete':receipt['completed']=False
    if defect=='profile':receipt['settings']['storage_profile']='compact-v1'
    if defect=='report_hash':receipt['offline_e2e_sha256']='0'*64
    if defect=='manifest_hash':receipt['manifest_sha256']='0'*64
    (root/'release.json').write_text(json.dumps(receipt))
''')
    delegate.chmod(0o755)
    data = tmp_path / 'data'
    data.mkdir()
    trace = tmp_path / 'trace.txt'
    env = {k: v for k, v in os.environ.items() if not k.startswith('GENOS_')}
    env.update(GENOS_DATA_ROOT=str(data), GENOS_PREPARED_RUN='fixture-completed',
               GENOS_REUSE_RUN='fixture-output', GENOS_PYTHON_DIR=str(binaries),
               TEST_TRACE=str(trace))

    def run(**changes):
        selected = {**env, **changes}
        selected = {k: v for k, v in selected.items() if v is not None}
        result = subprocess.run(['/bin/bash', str(tmp_path / LAUNCHER)],
                                env=selected, text=True, capture_output=True, timeout=30)
        steps = trace.read_text().splitlines() if trace.exists() else []
        logs = list((tmp_path / 'reference-e2e-logs').glob('*.log'))
        assert logs, result.stdout + result.stderr
        assert 'E2E_LAUNCH_EXIT=' in logs[0].read_text()
        return result, steps

    return run, tmp_path


def test_default_runs_through_verified_offline_e2e(launch):
    run, _ = launch
    result, steps = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert steps == ['check', 'apply', 'verify', 'build']
    assert 'OFFLINE_E2E=PASS' in result.stdout
    assert 'LIVE_WORKFLOW_E2E=NOT_RUN' in result.stdout


def test_delegate_failure_stops_later_steps(launch):
    run, _ = launch
    result, steps = run(TEST_FAIL_STEP='apply')
    assert result.returncode == 7
    assert steps == ['check', 'apply']
    assert 'OFFLINE_E2E=PASS' not in result.stdout


@pytest.mark.parametrize('defect', ['incomplete', 'profile', 'report_hash', 'manifest_hash'])
def test_invalid_receipt_cannot_report_success(launch, defect):
    run, _ = launch
    result, steps = run(TEST_DEFECT=defect)
    assert result.returncode != 0
    assert steps == ['check', 'apply', 'verify', 'build']
    assert 'OFFLINE_E2E=PASS' not in result.stdout


def test_missing_input_selection_does_not_apply_code(launch):
    run, _ = launch
    result, steps = run(GENOS_PREPARED_RUN=None)
    assert result.returncode != 0
    assert steps == []


def test_tampered_code_zip_does_not_apply_code(launch):
    run, folder = launch
    with (folder / 'GENOS_REFERENCE_BUILD_20261003_R1.zip').open('ab') as stream:
        stream.write(b'tampered')
    result, steps = run()
    assert result.returncode != 0
    assert steps == []
