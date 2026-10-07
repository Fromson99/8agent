"""Offline install uses existing selections without changing data or calling a model."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('auto_generation', ROOT / '06_TOOLS/COMMANDS/genos_generation_e2e.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ('GENOS_GENERATION', 'GENOS_DATA_ROOT'):
        monkeypatch.delenv(name, raising=False)


def generation(path):
    path.mkdir(parents=True)
    (path / 'manifest.json').write_text(json.dumps({'schema_version': 'term-source-generation-v1', 'generation_id': 'synthetic'}))
    return path


def current(root, path):
    pointer = root / 'generations/CURRENT.json'
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({'schema_version': 'genos-current-generation-v1', 'path': str(path),
        'manifest_sha256': hashlib.sha256((path / 'manifest.json').read_bytes()).hexdigest()}))
    return pointer


def test_environment_generation_wins_and_data_is_unchanged(tmp_path, monkeypatch):
    first = generation(tmp_path / 'first'); second = generation(tmp_path / 'second')
    (tmp_path / '.env').write_text('GENOS_GENERATION=' + str(second))
    monkeypatch.setenv('GENOS_GENERATION', str(first))
    before = (first / 'manifest.json').read_bytes()
    assert tool.operator_generation(tmp_path) == first
    assert (first / 'manifest.json').read_bytes() == before


def test_existing_dotenv_only_reads_literal_data_settings(tmp_path):
    selected = generation(tmp_path / 'generation with spaces')
    (tmp_path / '.env').write_text('PRIVATE_KEY=$(touch /must-never-run)\nexport GENOS_GENERATION="' + str(selected) + '" # data\n')
    assert tool.operator_generation(tmp_path) == selected


@pytest.mark.parametrize('where', ['environment', 'dotenv', 'documented_setup'])
def test_current_is_automatically_reused(tmp_path, monkeypatch, where):
    root = tmp_path / '01_DATA'; selected = generation(root / 'generations/existing')
    pointer = current(root, selected); before = pointer.read_bytes()
    if where == 'environment': monkeypatch.setenv('GENOS_DATA_ROOT', str(root))
    if where == 'dotenv': (tmp_path / '.env').write_text('GENOS_DATA_ROOT=' + str(root))
    assert tool.operator_generation(tmp_path) == selected
    assert pointer.read_bytes() == before


def test_unselected_generation_directories_are_not_used(tmp_path):
    generation(tmp_path / '01_DATA/generations/newest-looking')
    with pytest.raises(tool.GenerationUnavailable): tool.operator_generation(tmp_path)
    assert tool.main(['--code-root', str(tmp_path), '--auto', '--resolve-only']) == 3


def test_invalid_configured_pointer_does_not_fall_back(tmp_path, monkeypatch):
    root = tmp_path / 'selected'; selected = generation(root / 'generations/existing')
    pointer = current(root, selected)
    value = json.loads(pointer.read_text()); value['manifest_sha256'] = '0' * 64; pointer.write_text(json.dumps(value))
    other = generation(tmp_path / '01_DATA/generations/other'); current(tmp_path / '01_DATA', other)
    monkeypatch.setenv('GENOS_DATA_ROOT', str(root))
    with pytest.raises(ValueError, match='hash mismatch'): tool.operator_generation(tmp_path)


def test_previous_verified_binding_is_reused(tmp_path):
    selected = generation(tmp_path / 'published/generation'); receipt = tmp_path / 'TRANSFER/r2/VERIFIED_CHECKOUT.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'code_root': str(tmp_path), 'generation': str(selected),
        'generation_manifest_sha256': hashlib.sha256((selected / 'manifest.json').read_bytes()).hexdigest()}))
    assert tool.operator_generation(tmp_path) == selected
    (selected / 'manifest.json').write_text('{}')
    with pytest.raises(ValueError): tool.operator_generation(tmp_path)


def test_conflicting_existing_current_selections_are_rejected(tmp_path):
    for name in ('01_DATA', 'GENOS_DATA'):
        selected = generation(tmp_path / name / 'generations/g'); current(tmp_path / name, selected)
    with pytest.raises(ValueError, match='disagree'): tool.operator_generation(tmp_path)


def test_pointer_cannot_escape_data_root(tmp_path, monkeypatch):
    selected = generation(tmp_path / 'outside'); root = tmp_path / 'data'; current(root, selected)
    monkeypatch.setenv('GENOS_DATA_ROOT', str(root))
    with pytest.raises(ValueError): tool.operator_generation(tmp_path)
