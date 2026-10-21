"""Metadata-only CLI: no payload access, reversible rename, and failure recovery."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SCRIPT = HERE / 'GENOS_TERM_RELEASE_STORAGE_20261016_R1.txt'
KEEP = 'financial-risk-success-20261005-schema-r2'


def module_at(tmp):
    source = SCRIPT.read_text().split("<<'STORAGE_PY'\n", 1)[1].rsplit('\nSTORAGE_PY', 1)[0]
    ast.parse(source, feature_version=(3, 11))
    source = source.rsplit('\ntry:\n    main()', 1)[0]
    namespace = {}
    previous = sys.argv
    sys.argv = ['test', str(tmp)]
    try:
        exec(compile(source, str(SCRIPT), 'exec'), namespace)
    finally:
        sys.argv = previous
    namespace['STATE'].mkdir()
    return namespace


@pytest.fixture
def staged(tmp_path):
    module = module_at(tmp_path)
    base = tmp_path / 'term-releases'; base.mkdir()
    (base / KEEP).mkdir()
    rows = []
    for name in ['fulltext-repair-test-a', 'smoke-test-b']:
        child = base / name; child.mkdir()
        (child / 'original.bin').write_bytes(name.encode())
        rows.append({'name': name, 'identity': module['directory'](child)})
    plan = {'schema_version': module['VERSION'], 'binding': {'base': str(base), 'dev': str(tmp_path)},
            'quarantine': str(base.parent / 'term-releases-quarantine-20261016-r1'), 'candidates': rows}
    return module, base, plan


def test_repeat_isolate_restore_preserves_bytes_and_inodes(staged):
    mod, base, plan = staged
    mod['move'](plan); mod['move'](plan)
    assert (base / KEEP).is_dir()
    assert all(row[3] for row in mod['locations'](plan))
    mod['move'](plan, restore=True); mod['move'](plan, restore=True)
    for row in plan['candidates']:
        assert mod['directory'](base / row['name']) == row['identity']
        assert (base / row['name'] / 'original.bin').read_bytes() == row['name'].encode()


@pytest.mark.parametrize('lost_receipt', [False, True])
def test_interrupted_move_recovers_by_filesystem_identity(staged, lost_receipt):
    mod, base, plan = staged
    real_rename, real_event = mod['rename_without_replacement'], mod['event']
    count = 0
    def fail_rename(source, target):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('simulated second rename failure')
        real_rename(source, target)
    def fail_event(kind, **fields):
        if kind == 'ISOLATED_ONE':
            raise OSError('simulated receipt failure after rename')
        real_event(kind, **fields)
    mod['rename_without_replacement'] = real_rename if lost_receipt else fail_rename
    mod['event'] = fail_event if lost_receipt else real_event
    with pytest.raises(OSError):
        mod['move'](plan)
    assert sum(row[3] for row in mod['locations'](plan)) == 1
    mod['rename_without_replacement'], mod['event'] = real_rename, real_event
    mod['move'](plan, restore=True)
    assert all(not row[3] for row in mod['locations'](plan))


def test_restore_refuses_conflict_without_overwriting(staged):
    mod, base, plan = staged
    mod['move'](plan)
    conflict = base / plan['candidates'][0]['name']; conflict.mkdir()
    (conflict / 'new-user-file').write_text('preserve')
    with pytest.raises(ValueError, match='conflicting'):
        mod['move'](plan, restore=True)
    assert (conflict / 'new-user-file').read_text() == 'preserve'
    assert len(list(Path(plan['quarantine']).iterdir())) == 2


def test_atomic_no_replace_even_for_empty_target(staged):
    mod, base, plan = staged
    destination = base.parent / 'empty-destination'; destination.mkdir()
    with pytest.raises(FileExistsError):
        mod['rename_without_replacement'](base / plan['candidates'][0]['name'], destination)
    assert (base / plan['candidates'][0]['name']).exists()


@pytest.mark.parametrize('kind', ['symlink', 'unexpected'])
def test_unknown_or_linked_candidate_cannot_be_isolated(staged, kind):
    mod, base, plan = staged
    if kind == 'symlink':
        (base / 'smoke-link').symlink_to(base / KEEP)
    else:
        (base / 'another-active-generation').mkdir()
    with pytest.raises(ValueError):
        mod['candidates'](base)
    assert all((base / row['name']).exists() for row in plan['candidates'])




def test_changed_directory_identity_blocks_restore(staged):
    mod, base, plan = staged
    mod['move'](plan)
    target = Path(plan['quarantine']) / plan['candidates'][0]['name']
    target.rename(target.with_name('preserved-original'))
    target.mkdir()
    with pytest.raises(ValueError):
        mod['move'](plan, restore=True)
    assert (target.with_name('preserved-original') / 'original.bin').exists()


def test_unsafe_plan_name_rejected(staged):
    mod, base, plan = staged
    plan['candidates'][0]['name'] = KEEP
    with pytest.raises(ValueError, match='Invalid candidate'):
        mod['validate_plan'](plan, base, base.parent)


def test_same_filesystem_requirement(staged):
    mod, base, plan = staged
    original = mod['directory']
    mod['directory'] = lambda p: ([999999, 1] if str(p) == plan['quarantine'] else original(p))
    with pytest.raises(ValueError, match='Cross-filesystem'):
        mod['move'](plan)
    assert all((base / row['name']).exists() for row in plan['candidates'])


def small_fixture(tmp_path):
    delivery = tmp_path / 'TRANSFER'; delivery.mkdir()
    script = delivery / SCRIPT.name; shutil.copyfile(SCRIPT, script)
    base = tmp_path / 'term-releases'; base.mkdir()
    active = base / KEEP; active.mkdir()
    generation = active / 'generation'; generation.mkdir()
    for name in ['navigation', 'fulltext', 'glossary/bundle', 'glossary/cache']:
        (generation / name).mkdir(parents=True)
    for name in ['store.sqlite', 'navigation/navigation.sqlite', 'fulltext/units.sqlite', 'glossary/dictionary.sqlite']:
        (generation / name).write_bytes(b'PAYLOAD_MUST_NOT_BE_OPENED')
    manifest = {'schema_version': 'term-source-generation-v2', 'navigation': {'path': 'navigation'},
                'fulltext': {'path': 'fulltext'}, 'glossary': {'bundle': 'glossary/bundle',
                'dictionary': 'glossary/dictionary.sqlite', 'cache': 'glossary/cache'}}
    (generation / 'manifest.json').write_text(json.dumps(manifest))
    for name in ['fulltext-repair-original', 'smoke-original']:
        (base / name).mkdir()
        (base / name / 'keep.txt').write_text(name)
    dev = tmp_path / 'DEV'; dev.mkdir()
    (dev / '00_SYSTEM').mkdir()
    for name in ['service.py', 'main_router.py', '00_SYSTEM/PIPELINE.json']:
        (dev / name).write_text('NEVER_IMPORT_OR_READ_THIS_CONTENT')
    config = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
              'generation': str(generation), 'runtime': str(tmp_path / 'runtime'), 'state': None,
              'generation_manifest_sha256': hashlib.sha256((generation / 'manifest.json').read_bytes()).hexdigest()}
    (dev / '00_SYSTEM/GENOS_SERVING_PATHS.json').write_text(json.dumps(config))
    return delivery, script, base, active, generation, dev, config


def test_binding_never_reads_payload_or_code_and_does_not_walk(tmp_path, monkeypatch):
    delivery, script, base, active, generation, dev, config = small_fixture(tmp_path)
    mod = module_at(delivery)
    original_open = Path.open
    def guard(path, *args, **kwargs):
        assert path.name in {'manifest.json', 'GENOS_SERVING_PATHS.json'}, path
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guard)
    monkeypatch.setattr(os, 'walk', lambda *a, **k: pytest.fail('recursive walk'))
    pin = mod['binding'](base, dev)
    assert pin['payload_content_verified'] is False
    assert mod['READ_BYTES'] < 4096


def test_oversize_metadata_is_rejected_before_open(tmp_path, monkeypatch):
    mod = module_at(tmp_path)
    path = tmp_path / 'huge.json'
    with path.open('wb') as stream:
        stream.truncate(2 * 1024 * 1024)
    monkeypatch.setattr(Path, 'open', lambda *a, **k: pytest.fail('oversize file opened'))
    with pytest.raises(ValueError, match='budget'):
        mod['small_bytes'](path)
    assert mod['READ_BYTES'] == 0


def test_external_bound_asset_link_rejected(tmp_path):
    delivery, script, base, active, generation, dev, config = small_fixture(tmp_path)
    mod = module_at(delivery)
    (generation / 'glossary/dictionary.sqlite').unlink()
    (generation / 'glossary/dictionary.sqlite').symlink_to(base / 'smoke-original/keep.txt')
    with pytest.raises(ValueError, match='outside retained'):
        mod['binding'](base, dev)


def test_script_metadata_cli_roundtrip(tmp_path):
    delivery, script, base, active, generation, dev, config = small_fixture(tmp_path)
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
    transcript = []
    def run(command, expect=0):
        result = subprocess.run(['bash', str(script), command, '--base', str(base), '--dev', str(dev)],
                                cwd=delivery, env=env, text=True, capture_output=True, timeout=15)
        transcript.append({'command': command, 'exit': result.returncode, 'output': result.stdout + result.stderr})
        assert result.returncode == expect, transcript[-1]
        return result.stdout
    before = {str(p.relative_to(active)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in active.rglob('*') if p.is_file()}
    assert 'METADATA_CHECK_PASS' in run('check')
    assert 'Existing plan preserved' in run('check', 1)
    run('verify', 1)
    run('isolate'); run('isolate')
    assert set(p.name for p in base.iterdir()) == {KEEP}
    assert 'ISOLATED_METADATA_PASS' in run('verify')
    assert 'payload_content_verified": false' in run('verify')
    config['generation_manifest_sha256'] = '0' * 64
    (dev / '00_SYSTEM/GENOS_SERVING_PATHS.json').write_text(json.dumps(config))
    run('verify', 1)
    run('restore'); run('restore'); run('status')
    assert all((base / name / 'keep.txt').read_text() == name for name in ['fulltext-repair-original', 'smoke-original'])
    after = {str(p.relative_to(active)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in active.rglob('*') if p.is_file()}
    assert before == after
    (HERE / 'TEST_COMMAND_TRANSCRIPT.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2))
