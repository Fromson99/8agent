"""Compatibility with exact previously shipped source, no model calls."""
import ast
import hashlib
import importlib.util
import linecache
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from lawrag.pipeline import genos_build as build
from .test_genos_build import setup
from . import test_genos_structure_optimized as contracts

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('optimizer_v2', ROOT/'06_TOOLS/COMMANDS/genos_structure_optimized_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def archived_function(name, function):
    with zipfile.ZipFile(ROOT/'09_ARTIFACTS/HANDOFF/GENOS/genos-four-stage-20260910.zip') as archive:
        text = archive.read('02_BACKEND/lawrag/pipeline/'+name).decode()
    if name == 'genos_build.py':
        assert hashlib.sha256(text.encode()).hexdigest() == 'cfa42e40ebbe114ee5ab3533ebfd71f0ea00ca5bcd54d643863e7b3e258caacb'
    filename = '/archived-genos-fixture/'+name
    linecache.cache[filename] = (len(text), None, text.splitlines(True), filename)
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == function)
    namespace = dict(vars(build))
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
    return namespace[function]


def test_actual_mailed_producer_and_consumer_recognized():
    producer = archived_function('genos_build.py', 'source_jobs')
    consumer = archived_function('genos_authoring_runtime.py', 'prepare')
    assert v2.assert_producer_compatible(SimpleNamespace(source_jobs=producer)) is False
    v2.assert_consumer_compatible(SimpleNamespace(prepare=consumer))
    assert v2.assert_producer_compatible(build) is True


def test_attachment_policy_is_preserved_not_silently_upgraded():
    blocks = [{'idx': 0}, {'idx': 1}, {'idx': 2}]
    units = [dict(id=0, family='chapter', span=[0,3]),
             dict(id=1, family='kr_article', span=[0,1], attachments=[{'block':2}])]
    old_groups, _ = v2.indexed_groups(blocks, units, include_attachments=False)
    new_groups, _ = v2.indexed_groups(blocks, units, include_attachments=True)
    assert old_groups['0'] == [{'idx': 1}, {'idx': 2}]
    assert new_groups['1'] == [{'idx': 0}, {'idx': 2}]


@pytest.mark.parametrize('seed', range(25))
def test_current_equivalence_contracts_retained(seed, monkeypatch):
    monkeypatch.setattr(contracts, 'opt', v2)
    contracts.test_indexed_exact_ownership_and_context(seed)


def test_actual_legacy_queue_inputs_equal(setup, monkeypatch):
    producer = archived_function('genos_build.py', 'source_jobs')
    monkeypatch.setattr(build, 'source_jobs', producer)
    monkeypatch.setattr(contracts, 'opt', v2)
    contracts.test_actual_queue_inputs_and_requests_identical(setup)


def test_legacy_mode_frozen_and_restored(monkeypatch):
    producer = archived_function('genos_build.py', 'source_jobs')
    monkeypatch.setattr(build, 'source_jobs', producer)
    with v2.enabled(ROOT) as identity:
        assert identity['ownership_attachments'] is False
    assert build.source_jobs is producer
