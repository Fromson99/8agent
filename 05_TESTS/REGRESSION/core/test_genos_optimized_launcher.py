"""Launcher contracts only; no document processing or model calls."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / 'DEV with spaces'
    commands = root / '06_TOOLS/COMMANDS'
    commands.mkdir(parents=True)
    for name in ('genos_data_optimized.sh', 'genos_structure_optimized_v2.py'):
        shutil.copyfile(ROOT / '06_TOOLS/COMMANDS' / name, commands / name)
    interpreter = root / '.venv/bin/python'
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text('#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({"cwd":os.getcwd(),"args":sys.argv[1:]}))\n')
    interpreter.chmod(0o700)
    return root, commands / 'genos_data_optimized.sh'


def test_forwarding_and_physical_root(installed, tmp_path):
    root, launcher = installed
    args = ['--run-id', 'fresh-opt-001', '--exclude-internal', '--stage', 'structure', '--execute']
    result = subprocess.run(['bash', str(launcher), *args], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['cwd'] == str(root)
    assert output['args'] == ['-u', str(launcher.parent / 'genos_structure_optimized_v2.py'), '--root', str(root), '--pipeline', *args]


@pytest.mark.parametrize('fault', ['missing', 'changed', 'symlink'])
def test_invalid_optimizer_fails_before_interpreter(installed, fault):
    root, launcher = installed
    optimizer = launcher.parent / 'genos_structure_optimized_v2.py'
    if fault == 'changed':
        optimizer.write_text('invalid optimizer\n')
    else:
        optimizer.unlink()
        if fault == 'symlink':
            optimizer.symlink_to(ROOT / '06_TOOLS/COMMANDS/genos_structure_optimized_v2.py')
    result = subprocess.run(['bash', str(launcher)], text=True, capture_output=True)
    assert result.returncode == 2
    assert result.stdout == ''


def test_original_entrypoint_does_not_select_optimizer():
    original = (ROOT / '06_TOOLS/COMMANDS/genos_data_stages.sh').read_text()
    assert 'genos_data_stages.py' in original
    assert 'optimized' not in original
