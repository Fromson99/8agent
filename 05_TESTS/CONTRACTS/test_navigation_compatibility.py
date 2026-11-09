"""Serving reads Oracle navigation rows from registered, output-identical compiler versions.

Field case (2026-11-06): the dev G19 publication was built by the Dataiku
loader's vendored navigation_match.py (f318d57b...), serving MAIN164 has
8d498d65... (a refactor adding document_starts). The exact-bytes rule refused
every request with QUERY_STRUCTURE_COMPILER although the rows are identical.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from semantic_runtime import navigation_compatibility as nc
from semantic_runtime.oracle_dp_io import DPError

CODE = Path(nc.__file__).resolve().parents[2]
REPO = Path(__file__).resolve().parents[2]


def registry():
    return json.loads((CODE / nc.REGISTRY).read_text(encoding='utf-8'))


def field_loader_version():
    # The registered loader entry, located by its navigation_match prefix.
    rows = [v['modules'] for g in registry()['groups'] for v in g['versions']
            if v['modules']['semantic_runtime.navigation_match'].startswith('f318d57b6a5d')]
    assert len(rows) == 1
    return rows[0]


def test_registry_is_valid_and_lists_this_code():
    known = nc.validate(registry())
    assert tuple(nc.current()[n] for n in nc.MODULES) in known


def test_exact_bytes_need_no_registry(tmp_path):
    assert nc.require(nc.current(), root=tmp_path) == {'status': 'EXACT'}


def test_field_loader_rows_are_accepted():
    result = nc.require(field_loader_version())
    assert result == {'status': 'COMPATIBLE', 'fingerprint': registry()['groups'][0]['fingerprint'],
                      'differs': ['navigation_match']}


def test_unknown_loader_is_refused_with_republish():
    recorded = {**field_loader_version(), 'semantic_runtime.navigation_match': '0' * 64}
    with pytest.raises(DPError, match='QUERY_STRUCTURE_COMPILER: Oracle navigation rows were built by loader code with a different derivation'):
        nc.require(recorded)


def test_missing_manifest_entry_is_refused():
    with pytest.raises(DPError, match='QUERY_STRUCTURE_COMPILER'):
        nc.require({})


def test_unregistered_serving_code_is_refused():
    fake = {name: hashlib.sha256(name.encode()).hexdigest() for name in nc.MODULES}
    with pytest.raises(DPError, match='this serving code version is not registered'):
        nc.require(field_loader_version(), now=fake)


def test_without_registry_the_exact_rule_remains(tmp_path):
    with pytest.raises(DPError, match='no compatibility registry'):
        nc.require(field_loader_version(), root=tmp_path, now={n: '1' * 64 for n in nc.MODULES})


def test_registry_shape_is_enforced():
    value = registry()
    broken = copy.deepcopy(value)
    broken['groups'].append({'fingerprint': 'a' * 64, 'versions': [copy.deepcopy(value['groups'][0]['versions'][0])]})
    with pytest.raises(DPError, match='two groups'):
        nc.validate(broken)
    broken = copy.deepcopy(value)
    broken['modules'] = {**broken['modules'], 'semantic_runtime.extra': 'x.py'}
    with pytest.raises(DPError, match='invalid navigation compatibility registry'):
        nc.validate(broken)
    broken = copy.deepcopy(value)
    broken['groups'][0]['versions'][0]['modules']['semantic_runtime.navigation_match'] = 'not-a-hash'
    with pytest.raises(DPError, match='invalid navigation compatibility version'):
        nc.validate(broken)


def _preflight():
    spec = importlib.util.spec_from_file_location('navcompat_preflight', REPO / '06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def test_engine_preflight_requires_registration(tmp_path):
    (tmp_path / '00_SYSTEM/ORACLE').mkdir(parents=True)
    (tmp_path / '00_SYSTEM/PIPELINE.json').write_text('{"engines": {}}')
    for relative in nc.MODULES.values():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((CODE / relative).read_bytes())
    (tmp_path / nc.REGISTRY).write_text(json.dumps(registry()))
    check = _preflight()
    assert check(tmp_path)[2] == []
    edited = tmp_path / nc.MODULES['semantic_runtime.navigation_match']
    edited.write_bytes(edited.read_bytes() + b'\n# edit without registering\n')
    errors = check(tmp_path)[2]
    assert len(errors) == 1 and 'NAVIGATION COMPATIBILITY UNREGISTERED' in errors[0]
    (tmp_path / nc.REGISTRY).unlink()
    assert check(tmp_path)[2] == []


def test_tool_check_matches_serving(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('navcompat_tool', REPO / '06_TOOLS/maintenance/navigation_compatibility.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.MODULES == nc.MODULES and tool.REGISTRY == nc.REGISTRY and tool.SCHEMA == nc.SCHEMA
    assert tool.main(['check', '--code-root', str(CODE)]) == 0
    assert 'REGISTERED' in capsys.readouterr().out
