"""Prepared-input OFF rebuilding, failure/resume and durable logs; scripted models only."""
from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import zipfile

import pytest
from semantic_runtime.contracts import sha
from lawrag.pipeline import glossary_review, term_generation, document_release
from test_genos_meaning_variants import prepared, reference_calls

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '06_TOOLS/OFFLINE'))
import genos_optimized_rebuild as runner
from genos_rebuild_logging import BuildLog, observe
import genos_optimization_apply_r2 as apply_tool
import package_genos_optimized_rebuild_r2 as package


@pytest.fixture
def context(prepared, tmp_path, monkeypatch):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{"code":"synthetic-contract"}')
    monkeypatch.setenv('GENOS_VARIANTS_TOOL_PATH', runner.__file__)
    data = prepared['parent'].parents[1]
    return runner.fork_prepared(prepared, data, 'optimized', manifest), manifest


def test_new_run_reuses_prepared_bytes_and_rejects_input_changes(context, prepared):
    ctx, manifest = context
    assert ctx['source'] == prepared['source'] and ctx['draft'] == prepared['draft']
    assert ctx['parent'] != prepared['parent']
    data = prepared['parent'].parents[1]
    assert runner.fork_prepared(prepared, data, 'optimized', manifest) == ctx
    with pytest.raises(ValueError, match='settings changed'):
        runner.fork_prepared(prepared, data, 'optimized', manifest, reference_batch=7)
    with pytest.raises(ValueError, match='new output run'):
        runner.fork_prepared(prepared, data, prepared['parent'].name, manifest)


def test_applied_zip_code_drift_cannot_enter_new_run(tmp_path):
    dev = tmp_path / 'DEV'; dev.mkdir()
    source = dev / 'toy.py'; source.write_text('value=1\n')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'files': [{'role': 'code', 'path': 'toy.py', 'sha256': sha(source)}]}))
    assert runner.verified_code_pins(dev, manifest) == {str(source): sha(source)}
    source.write_text('value=2\n')
    with pytest.raises(ValueError, match='differs from selected ZIP'):
        runner.verified_code_pins(dev, manifest)


def test_off_rebuild_refs_fulltext_publish_and_cached_resume(context, prepared, reference_calls, monkeypatch, tmp_path):
    ctx, manifest = context
    protected = {p: sha(p) for p in (prepared['source'], prepared['draft'] / 'dictionary.sqlite',
                 prepared['parent'] / 'review/review.sqlite', prepared['parent'] / 'plan.json')}
    def forbidden(*args, **kwargs):
        raise AssertionError('New meaning review must not run')
    monkeypatch.setattr(glossary_review, 'run', forbidden)
    shared = tmp_path / 'shared'; shared.mkdir()
    log = BuildLog(tmp_path / 'log', interval=.02, terminal=io.StringIO())
    try:
        result = runner.rebuild(ctx, shared_root=shared, log=log)
        assert result['meaning_review_status'] == 'SKIPPED' and result['reference_llm']
        assert result['completed'] and not result['activated']
        assert (Path(result['generation_path']) / 'fulltext/manifest.json').is_file()
        assert (shared / 'optimized-meaning-off/generation/manifest.json').is_file()
        assert len(reference_calls) == 1
        assert runner.rebuild(ctx, shared_root=shared, log=log) == result
        assert len(reference_calls) == 1
    finally:
        log.close(0)
    assert all(sha(p) == expected for p, expected in protected.items())
    rows = [json.loads(line) for line in (tmp_path / 'log/events.jsonl').read_text().splitlines()]
    assert any(r['phase'] == 'glossary-file-hash' for r in rows)
    assert any(r['phase'] == 'explicit-reference-model' for r in rows)
    assert rows[-1]['status'] == 'FINISHED'


def test_fulltext_failure_preserves_checkpoint_and_resumes(context, reference_calls, tmp_path, monkeypatch):
    ctx, _ = context
    native = term_generation.fulltext.build
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic fulltext failure')
    fail.__code__ = fail.__code__.replace(co_filename=native.__code__.co_filename)
    monkeypatch.setattr(term_generation.fulltext, 'build', fail)
    log = BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        with pytest.raises(RuntimeError, match='fulltext failure'):
            runner.rebuild(ctx, log=log)
    finally:
        log.close(1)
    checkpoint = ctx['parent'] / 'meaning-variants/off/baseline-recovery-r1.json'
    assert checkpoint.exists()
    monkeypatch.setattr(term_generation.fulltext, 'build', native)
    compile_index = term_generation.compile_index
    def forbidden(*args, **kwargs):
        raise AssertionError('Completed navigation must not repeat')
    forbidden.__code__ = forbidden.__code__.replace(co_filename=compile_index.__code__.co_filename)
    monkeypatch.setattr(term_generation, 'compile_index', forbidden)
    log = BuildLog(tmp_path / 'resume', terminal=io.StringIO())
    try:
        assert runner.rebuild(ctx, log=log)['completed']
    finally:
        log.close(0)


def test_heartbeat_error_redaction_and_sequence_continuity(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_API_KEY', 'secret-fixture-value')
    terminal = io.StringIO()
    log = BuildLog(tmp_path, interval=.01, terminal=terminal)
    with pytest.raises(ValueError):
        with log.phase('slow-copy', path='/prepared/source.sqlite'):
            time.sleep(.04)
            raise ValueError('error secret-fixture-value')
    log.close(1)
    rows = [json.loads(x) for x in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert any(r['status'] == 'RUNNING' and r['phase'] == 'slow-copy' for r in rows)
    assert any(r['status'] == 'FAILED' for r in rows)
    assert 'secret-fixture-value' not in terminal.getvalue()
    assert '[REDACTED]' in terminal.getvalue()
    seq = rows[-1]['seq']
    log = BuildLog(tmp_path, terminal=terminal); log.close(0)
    assert json.loads((tmp_path / 'current.json').read_text())['seq'] > seq
    assert (tmp_path / 'phases.csv').read_text().count('time_utc') == 1


def test_runtime_logging_restores_functions_and_file_identity(tmp_path):
    import shutil
    original = shutil.copyfile
    log = BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        with pytest.raises(RuntimeError):
            with observe(log):
                assert shutil.copyfile.__code__.co_filename == original.__code__.co_filename
                raise RuntimeError('interrupted')
        assert shutil.copyfile is original
    finally:
        log.close(1)


def test_recycled_pid_record_is_never_signalled(tmp_path, monkeypatch):
    metadata = runner.old_records(tmp_path, 'prepared')[0]
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({'pid': 123, 'boot_id': 'old', 'start_time': '1'}))
    monkeypatch.setattr(runner, 'process_identity', lambda pid: {'pid': pid, 'boot_id': 'new', 'start_time': '2'})
    monkeypatch.setattr(os, 'kill', lambda *_: pytest.fail('Recycled pid signalled'))
    log = BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        runner.stop_recorded(tmp_path, 'prepared', log)
    finally:
        log.close(0)


def test_unrecorded_old_variant_lock_blocks_code_apply(tmp_path):
    import fcntl
    variant = tmp_path / 'TERM_RELEASES/prepared/prepared-bulk-r2/meaning-variants/off'
    variant.mkdir(parents=True)
    with (variant / '.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='previous run holds'):
            runner.check_idle(tmp_path, 'prepared')


@pytest.fixture
def patch_fixture(tmp_path, monkeypatch):
    payload = tmp_path / 'payload'; payload.mkdir()
    dev = tmp_path / 'DEV'; dev.mkdir()
    existing = dev / '02_BACKEND/toy.py'; existing.parent.mkdir(); existing.write_text('value=0\n')
    config = dev / '00_SYSTEM/PIPELINE.json'; config.parent.mkdir(); config.write_text('{"before":true}')
    paths = [('02_BACKEND/toy.py', 'value=1\n', False),
             ('02_BACKEND/navigation_storage.py', 'new=1\n', True)]
    rows = []
    for name, body, allow in paths:
        source = payload / name; source.parent.mkdir(exist_ok=True); source.write_text(body)
        target = dev / name
        rows.append({'path': name, 'sha256': sha(source), 'role': 'code', 'allow_missing': allow,
                     'allowed_predecessors': [sha(target)] if target.exists() else []})
    (payload / 'CODE_MANIFEST.json').write_text(json.dumps({'files': rows}))
    monkeypatch.setattr(apply_tool, 'HERE', payload)
    def engine(dev, *, apply=False, add_new=False):
        if apply:
            assert add_new
            config.write_text('{"after":true}')
        return {'changed_code': ['02_BACKEND/toy.py'], 'unlisted_runtime_files': ['02_BACKEND/navigation_storage.py']}
    monkeypatch.setattr(apply_tool, 'engine_plan', engine)
    return dev, existing, config


def test_new_required_module_is_hash_bound_and_rollback_removes_only_addition(patch_fixture):
    dev, existing, config = patch_fixture
    apply_tool.apply(dev, check=True)
    assert not (dev / '02_BACKEND/navigation_storage.py').exists()
    apply_tool.apply(dev)
    backup = next((dev / '.genos-pipeline-optimization-backups').iterdir())
    assert (dev / '02_BACKEND/navigation_storage.py').read_text() == 'new=1\n'
    apply_tool.rollback(backup)
    assert not (dev / '02_BACKEND/navigation_storage.py').exists()
    assert existing.read_text() == 'value=0\n' and config.read_text() == '{"before":true}'


def test_engine_failure_rolls_back_before_run(patch_fixture, monkeypatch):
    dev, existing, config = patch_fixture
    monkeypatch.setattr(apply_tool, 'engine_plan', lambda *a, **k: {'changed_code': ['unrelated.py']})
    with pytest.raises(ValueError, match='Unrelated'):
        apply_tool.apply(dev)
    assert existing.read_text() == 'value=0\n'
    assert not (dev / '02_BACKEND/navigation_storage.py').exists()


def test_field_code_drift_is_not_overwritten(patch_fixture):
    dev, existing, _ = patch_fixture
    existing.write_text('value=99\n')
    with pytest.raises(ValueError, match='FILE_DRIFT'):
        apply_tool.apply(dev)
    assert existing.read_text() == 'value=99\n'
    assert not (dev / '.genos-pipeline-optimization-backups').exists()


def test_final_archive_preserves_r1_optimized_code_and_no_js():
    path = package.OUT / (package.STEM + '.zip')
    with zipfile.ZipFile(path) as z:
        m = json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist()) == {r['path'] for r in m['files']} | {'CODE_MANIFEST.json'}
        for row in m['files']:
            assert __import__('hashlib').sha256(z.read(row['path'])).hexdigest() == row['sha256']
            assert Path(row['path']).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
        old = json.loads((package.OLD / 'CODE_MANIFEST.json').read_text())
        for row in old['files']:
            if row['role'] == 'code':
                assert z.read(row['path']) == (package.OLD / row['path']).read_bytes()


def test_bad_archive_keeps_initial_and_failure_logs(tmp_path):
    dev = tmp_path / 'DEV'; (dev / '02_BACKEND').mkdir(parents=True)
    archive = tmp_path / 'bad.zip'; archive.write_bytes(b'wrong archive')
    env = {**os.environ, 'GENOS_DEV': str(dev), 'GENOS_DATA_ROOT': str(tmp_path / 'data'),
           'GENOS_OPTIMIZATION_ZIP': str(archive), 'GENOS_PREPARED_RUN': 'prepared',
           'GENOS_OPTIMIZED_RUN': 'optimized', 'GENOS_LOG_INTERVAL': '.02'}
    result = subprocess.run(['bash', str(package.OUT / (package.STEM + '.txt'))], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'START UTC=' in result.stdout and 'ZIP hash mismatch' in result.stdout
    assert 'FINISHED status=' in result.stdout
    logs = list((tmp_path / 'data/LOGS/optimized/optimized-rebuild-r2').glob('*/run.log'))
    assert len(logs) == 1 and 'ZIP hash mismatch' in logs[0].read_text()
    assert not (dev / '.genos-pipeline-optimization-backups').exists()
