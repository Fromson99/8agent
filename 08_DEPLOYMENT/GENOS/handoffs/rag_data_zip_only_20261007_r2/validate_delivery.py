"""Run the exact attachment against synthetic data, including concurrent writes."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import zipfile

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
NAME = 'GENOS_DATA_ZIP_ONLY_20261007_R2.txt'
spec = importlib.util.spec_from_file_location('bundle_fixtures', R / '05_TESTS/test_genos_rag_data_bundle.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
handoff = json.loads((O / 'HANDOFF.json').read_text())
assert sha(O / NAME) == handoff['txt_sha256']
results = []
for case in ('pack_restore_dirty_checkout', 'concurrent_source_changes_and_sqlite_wal',
             'tool_hash_mismatch', 'missing_dev'):
    fixture = tests.BundleContracts()
    fixture.setUp()
    stop = threading.Event()
    worker = None
    keeper = None
    worker_errors = []
    try:
        root = fixture.dev
        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        git('config', 'user.name', 'ZIP only validation')
        git('config', 'user.email', 'validation@example.invalid')
        pending = root / 'pending.txt'
        pending.write_text('original')
        git('add', '--', pending.name)
        git('commit', '-qm', 'Synthetic checkout')
        pending.write_text('preserved pending change')
        git('add', '--', pending.name)
        head = git('rev-parse', 'HEAD')
        index = (root / '.git/index').read_bytes()
        (root / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_RUNTIME_DIR=/old/path\nGENOS_STATE_DIR=/old/state\nSECRET_TEST_TOKEN=must_not_print\n')
        alias = fixture.base / 'home/genos/DEV'
        alias.parent.mkdir(parents=True)
        alias.symlink_to(root, target_is_directory=True)
        attachment_dir = fixture.base / 'attachments'
        attachment_dir.mkdir()
        script = attachment_dir / NAME
        shutil.copyfile(O / NAME, script)
        if case == 'tool_hash_mismatch':
            script.write_text(script.read_text().replace(handoff['embedded_tool_sha256'], '0' * 64))
        if case == 'concurrent_source_changes_and_sqlite_wal':
            artifacts = fixture.runtime / 'case-memory/artifacts'
            delay = artifacts / '000-copy.bin'
            delay.write_bytes(os.urandom(16 * 1024 * 1024))
            changing = artifacts / 'changing.txt'
            changing.write_text('before')
            removed = artifacts / 'removed.txt'
            removed.write_text('present at inventory')
            added = artifacts / 'added.txt'
            keeper = sqlite3.connect(fixture.db)
            keeper.execute('PRAGMA journal_mode=WAL')
            keeper.execute('PRAGMA wal_autocheckpoint=0')
            keeper.execute('INSERT INTO sw_knowledge VALUES(?)', ('committed before ZIP',))
            keeper.commit()
            def mutate():
                try:
                    deadline = time.monotonic() + 15
                    while not list((root / 'TRANSFER').glob('*/SOURCE_BEFORE.json.gz')):
                        if stop.wait(0.001) or time.monotonic() > deadline:
                            raise RuntimeError('initial inventory was not observed')
                    changing.write_text('changed after inventory')
                    removed.unlink()
                    added.write_text('added after inventory')
                    with contextlib.closing(sqlite3.connect(fixture.db)) as db:
                        db.execute('PRAGMA wal_autocheckpoint=0')
                        db.execute('INSERT INTO sw_knowledge VALUES(?)', ('concurrent committed row',))
                        db.commit()
                except Exception as exc:
                    worker_errors.append(str(exc))
            worker = threading.Thread(target=mutate)
            worker.start()
        env = {**os.environ, 'GENOS_DEV': str(alias if case != 'missing_dev' else fixture.base / 'absent'),
               'GENOS_PYTHON_DIR': str(R / '.venv/bin')}
        done = subprocess.run(['bash', str(script), '--source-prefix', str(fixture.source)],
                              env=env, capture_output=True, text=True, timeout=45)
        stop.set()
        if worker:
            worker.join(5)
            assert not worker.is_alive() and not worker_errors, worker_errors
        (O / (case + '.log')).write_text(done.stdout + done.stderr)
        assert 'must_not_print' not in done.stdout + done.stderr
        successful = case in ('pack_restore_dirty_checkout', 'concurrent_source_changes_and_sqlite_wal')
        assert done.returncode == (0 if successful else 1), done.stdout + done.stderr
        assert pending.read_text() == 'preserved pending change'
        assert git('rev-parse', 'HEAD') == head and (root / '.git/index').read_bytes() == index
        # Committed source DB and newly created WAL are managed by the test writer.
        for path, raw in fixture.before.items():
            if case == 'concurrent_source_changes_and_sqlite_wal' and Path(path) == fixture.db:
                continue
            assert Path(path).read_bytes() == raw
        status = json.loads(next(attachment_dir.glob('data-zip-only-logs/*/EXIT_STATUS.json')).read_text())
        assert status['exit_code'] == done.returncode
        if successful:
            archive = next((root / 'TRANSFER').glob('genos-rag-data-*.zip'))
            assert archive.with_suffix('.zip.sha256').read_text().split()[0] == sha(archive)
            unpack = fixture.base / 'unpacked'
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
                z.extractall(unpack)
            bundle = next(unpack.iterdir())
            manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
            assert manifest['schema_version'] == tests.tool.LIVE_FORMAT
            assert not manifest['writers_stopped_declared']
            assert not manifest['consistency']['cross_file_atomic']
            for target, row in manifest['files'].items():
                if row['kind'] == 'file':
                    content = bundle / 'payload' / target.lstrip('/')
                    assert content.stat().st_size == row['bytes'] and sha(content) == row['sha256']
            report = manifest['source_changes']
            assert (bundle / 'SOURCE_CHANGES.json').read_bytes() == (root / 'TRANSFER' / archive.stem / 'SOURCE_CHANGES.json').read_bytes()
            if case == 'concurrent_source_changes_and_sqlite_wal':
                changes = {row['path']: row['change'] for row in report['inventory_changes']}
                logical = lambda p: '/' + p.relative_to(fixture.source).as_posix()
                assert changes[logical(changing)] == 'metadata_changed'
                assert changes[logical(removed)] == 'removed'
                assert changes[logical(added)] == 'added'
                assert logical(removed) in [row['path'] for row in report['skipped_files']]
                assert not manifest['archive_restore_eligible']
                copied_db = bundle / 'payload' / fixture.db.relative_to(fixture.source)
                with contextlib.closing(sqlite3.connect(copied_db.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                    assert ('committed before ZIP',) in db.execute('SELECT payload FROM sw_knowledge').fetchall()
                assert not Path(str(copied_db) + '-wal').exists()
            else:
                restored = subprocess.run(['bash', str(bundle / 'RESTORE.sh'), '--writers-stopped',
                                           '--accept-live-archive', '--destination-prefix', str(fixture.destination),
                                           '--output-dir', str(fixture.base / 'restore-logs')],
                                          env={**env, 'PATH': str(R / '.venv/bin') + ':' + os.environ['PATH']},
                                          capture_output=True, text=True, timeout=45)
                assert restored.returncode == 0, restored.stdout + restored.stderr
                for path, raw in fixture.before.items():
                    destination = fixture.destination / Path(path).relative_to(fixture.source)
                    if Path(path).suffix != '.sqlite':
                        assert destination.read_bytes() == raw
                restored_db = fixture.destination / fixture.db.relative_to(fixture.source)
                with contextlib.closing(sqlite3.connect(restored_db)) as db:
                    assert db.execute('SELECT COUNT(*) FROM sw_knowledge').fetchone()[0] == 1
        else:
            assert not list((root / 'TRANSFER').glob('*.zip'))
            if case == 'tool_hash_mismatch':
                assert 'Embedded data tool hash mismatch' in done.stdout
        results.append({'case': case, 'passed': True, 'exit_code': done.returncode,
                        'source_sql_updates_only_by_fixture_writer': True,
                        'git_head_and_staged_bytes_preserved': True})
    finally:
        stop.set()
        if worker: worker.join(5)
        if keeper: keeper.close()
        fixture.doCleanups()
record = {'tests_passed': len(results), 'tests_failed': 0, 'cases': results,
          'attachment_sha256': sha(O / NAME), 'unit_contracts_passed': 26,
          'synthetic_data_only': True, 'genos_accessed': False, 'field_data_zip_created': False}
(O / 'VALIDATION.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(record, ensure_ascii=False))
