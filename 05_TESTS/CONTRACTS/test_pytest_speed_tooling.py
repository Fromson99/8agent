"""Test-speed tooling: experiment tool import slot, fsync-free restart, parallel runner."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys

import pytest

import conftest

ROOT = Path(__file__).resolve().parents[2]


def load_runner():
    spec = importlib.util.spec_from_file_location('run_tests_under_test', ROOT / '06_TOOLS/maintenance/run_tests.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_experiment_directories_take_one_sys_path_entry():
    entries = set(sys.path)
    assert conftest.EXPERIMENT_PATH_SLOT in entries
    assert not any(str(path) in entries for path in conftest.EXPERIMENT_TOOL_DIRS)
    assert any(isinstance(finder, conftest.ExperimentToolFinder) for finder in sys.meta_path)


def test_experiment_module_resolves_to_first_directory_in_historical_order():
    finder = next(f for f in sys.meta_path if isinstance(f, conftest.ExperimentToolFinder))
    slot = sys.path.index(conftest.EXPERIMENT_PATH_SLOT)
    expanded = [*sys.path[:slot], *finder.directories, *sys.path[slot + 1:]]
    checked = 0
    for name in sorted(finder.names):
        if not name.isidentifier() or name in sys.modules:
            continue
        expected = importlib.machinery.PathFinder.find_spec(name, expanded)
        actual = importlib.util.find_spec(name)
        assert (expected and expected.origin) == (actual and actual.origin), name
        checked += 1
        if checked == 200:
            break
    assert checked


def test_command_line_pytest_runs_without_fsync_unless_opted_out():
    if os.environ.get('LAWRAG_TEST_KEEP_FSYNC') == '1' or not os.path.exists(conftest.EATMYDATA_LIBRARY):
        pytest.skip('real fsync requested or libeatmydata missing')
    if not conftest._started_as_pytest_command():
        pytest.skip('pytest started from a script; only command-line runs restart')
    assert 'libeatmydata' in os.environ.get('LD_PRELOAD', '')
    assert not conftest._restart_without_fsync_required()


def write_junit(path, cases):
    body = ''.join(f'<testcase classname="{c}" name="{n}" time="{t}">{x}</testcase>' for c, n, t, x in cases)
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite>{body}</testsuite></testsuites>')


def test_runner_maps_junit_classnames_back_to_node_ids(tmp_path):
    runner = load_runner()
    junit = tmp_path / 'batch.xml'
    write_junit(junit, [
        ('05_TESTS.CONTRACTS.test_a', 'test_plain', '1.5', ''),
        ('05_TESTS.CONTRACTS.test_a', 'test_param[x-1]', '0.5', '<failure message="boom&#10;more" />'),
        ('05_TESTS.CONTRACTS.test_a.TestGroup', 'test_method', '0.25', '<skipped />'),
        ('05_TESTS.CONTRACTS.legal_knowledge.test_b', 'test_error', '0', '<error message="setup" />'),
    ])
    rows = runner.read_junit(junit, ['05_TESTS/CONTRACTS/test_a.py', '05_TESTS/CONTRACTS/legal_knowledge/test_b.py'])
    assert [(nodeid, outcome, message) for nodeid, _, outcome, _, message in rows] == [
        ('05_TESTS/CONTRACTS/test_a.py::test_plain', 'passed', None),
        ('05_TESTS/CONTRACTS/test_a.py::test_param[x-1]', 'failed', 'boom'),
        ('05_TESTS/CONTRACTS/test_a.py::TestGroup::test_method', 'skipped', None),
        ('05_TESTS/CONTRACTS/legal_knowledge/test_b.py::test_error', 'error', 'setup'),
    ]
    assert sum(row[3] for row in rows if row[1] == '05_TESTS/CONTRACTS/test_a.py') == 2.25


def test_runner_batches_cover_every_file_once_longest_first():
    runner = load_runner()
    files = [f'05_TESTS/CONTRACTS/test_{i}.py' for i in range(12)]
    durations = {name: float(i) for i, name in enumerate(files)}
    batches = runner.make_batches(files, durations, workers=3, batch_seconds=10)
    flat = [name for _, batch in batches for name in batch]
    assert sorted(flat) == sorted(files) and len(flat) == len(set(flat))
    seconds = [total for total, _ in batches]
    assert seconds == sorted(seconds, reverse=True)
    assert all(total <= 10 or len(batch) == 1 for total, batch in batches)


def test_runner_reuses_batch_layout_only_for_the_same_files():
    runner = load_runner()
    earlier = {'files': ['b.py', 'a.py', 'c.py'],
               'batches': [{'batch': 1, 'files': ['c.py']}, {'batch': 0, 'files': ['b.py', 'a.py']}]}
    assert runner.earlier_layout(earlier, ['a.py', 'c.py', 'b.py']) == [(0.0, ['b.py', 'a.py']), (0.0, ['c.py'])]
    assert runner.earlier_layout(earlier, ['a.py', 'b.py']) is None
