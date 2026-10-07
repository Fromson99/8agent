"""Offline archive/restore contracts; all data and target paths are synthetic."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rag_data_bundle', ROOT / '06_TOOLS/COMMANDS/genos_rag_data_bundle.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class BundleContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.destination = self.base / 'destination'
        self.destination.mkdir()
        self.output = self.base / 'output'
        self.dev = self.base / 'DEV'
        self.dev.mkdir()
        self.gen = self.source / tool.GENERATION.relative_to('/')
        self.gen.mkdir(parents=True)
        self.runtime = self.source / tool.RUNTIME.relative_to('/')
        (self.runtime / 'case-memory/artifacts/empty').mkdir(parents=True)
        (self.runtime / 'case-memory/artifacts/한글 공백.json').write_text('{"path":"/nfs-root/diamo/unchanged"}')
        self.db = self.runtime / 'case-memory/cases-v4.sqlite'
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE sw_knowledge(payload TEXT)')
            db.execute('INSERT INTO sw_knowledge VALUES(?)', (json.dumps({'journal_ref': str(tool.RUNTIME / 'legal-agent/runs/day/run/journal.sqlite')}),))
        journal = self.runtime / 'legal-agent/runs/day/run/journal.sqlite'
        journal.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(journal)) as db, db:
            db.execute('CREATE TABLE case_commit(case_db TEXT, binding TEXT)')
            db.execute('INSERT INTO case_commit VALUES(?,?)', (str(tool.RUNTIME / 'case-memory/cases-v4.sqlite'), '/workspace'))
        (self.gen / 'store.sqlite').write_bytes(b'synthetic generation bytes')
        (self.gen / 'manifest.json').write_text(json.dumps({'schema_version': 'term-source-generation-v2',
                  'generation_id': 'fixture', 'store_sha256': tool.sha(self.gen / 'store.sqlite')}))
        self.before = {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}

    def invoke(self, *args):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            return tool.main([*map(str, args), '--output-dir', str(self.output)])

    def pack(self, *args):
        result = self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                             '--writers-stopped', *args)
        self.assertEqual(result, 0)
        archive = next(self.output.glob('genos-rag-data-*.zip'))
        unpack = self.base / 'unpacked'
        with zipfile.ZipFile(archive) as data:
            data.extractall(unpack)
        bundle = next(unpack.iterdir())
        return archive, bundle

    def restore(self, bundle, *args):
        return self.invoke('restore', '--bundle', bundle, '--destination-prefix', self.destination,
                           '--writers-stopped', *args)

    def test_roundtrip_original_paths_bytes_and_idempotence(self):
        archive, bundle = self.pack()
        self.assertEqual(archive.parent, self.output)
        status = json.loads((self.output / archive.stem / 'STATUS.json').read_text())
        self.assertEqual(status['zip'], str(archive))
        self.assertTrue(archive.with_suffix('.zip.sha256').is_file())
        self.assertEqual(archive.with_suffix('.zip.sha256').read_text().split()[0], tool.sha(archive))
        with zipfile.ZipFile(archive) as data:
            member = bundle.name + '/payload' + str(tool.RUNTIME / 'case-memory/cases-v4.sqlite')
            self.assertEqual(data.read(member), self.before[str(self.db)])
        self.assertEqual(self.restore(bundle), 0)
        self.assertEqual(self.restore(bundle), 0)
        for source, content in self.before.items():
            path = Path(source).relative_to(self.source)
            self.assertEqual((self.destination / path).read_bytes(), content)
            self.assertEqual(Path(source).read_bytes(), content)
        empty = self.destination / tool.RUNTIME.relative_to('/') / 'case-memory/artifacts/empty'
        self.assertTrue(empty.is_dir())
        db = self.destination / tool.RUNTIME.relative_to('/') / 'legal-agent/runs/day/run/journal.sqlite'
        with contextlib.closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
            self.assertEqual(conn.execute('SELECT case_db FROM case_commit').fetchone()[0], str(tool.RUNTIME / 'case-memory/cases-v4.sqlite'))

    def test_default_zip_is_directly_in_dev_transfer_on_an_nfs_checkout(self):
        def mounted(path):
            return {'mount_point': str(self.dev), 'fs_type': 'nfs'} if path.is_relative_to(self.dev) else {'mount_point': '/', 'fs_type': 'ext4'}
        with patch.dict(os.environ, {'GENOS_RAG_DATA_OUTPUT_DIR': '/tmp/stale-export-setting'}, clear=True), patch.object(tool, 'output_mount', side_effect=mounted), contextlib.redirect_stdout(io.StringIO()):
            result = tool.main(['pack', '--source-prefix', str(self.source),
                                '--code-root', str(self.dev), '--writers-stopped'])
        self.assertEqual(result, 0)
        archive = next((self.dev / 'TRANSFER').glob('genos-rag-data-*.zip'))
        self.assertEqual(archive.parent, self.dev / 'TRANSFER')
        self.assertFalse(list(self.dev.glob('genos-rag-data-*')))
        self.assertTrue((self.dev / 'TRANSFER' / archive.stem / 'RUN.log').is_file())
        for path, content in self.before.items():
            self.assertEqual(Path(path).read_bytes(), content)

    def test_pack_from_dev_alias_preserves_paths_and_resolves_local_output(self):
        alias = self.base / 'home/genos/DEV'
        alias.parent.mkdir(parents=True)
        alias.symlink_to(self.dev, target_is_directory=True)
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            result = tool.main(['pack', '--source-prefix', str(self.source),
                                '--code-root', str(alias), '--output-dir', str(alias), '--writers-stopped'])
        self.assertEqual(result, 0)
        archive = next(self.dev.glob('genos-rag-data-*.zip'))
        self.assertTrue(alias.is_symlink())
        status = json.loads((self.dev / archive.stem / 'STATUS.json').read_text())
        self.assertEqual(status['zip'], str(archive))
        self.assertEqual(status['generation'], str(tool.GENERATION))

    def test_nfs_output_is_allowed_without_changing_source_data(self):
        with patch.object(tool, 'output_mount', return_value={'mount_point': str(self.output), 'fs_type': 'nfs4'}):
            self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                                        '--writers-stopped'), 0)
        self.assertTrue(list(self.output.glob('*.zip')))
        for path, raw in self.before.items():
            self.assertEqual(Path(path).read_bytes(), raw)

    def test_unknown_output_filesystem_is_logged_without_blocking_zip(self):
        with patch.object(tool, 'output_mount', return_value={'status': 'UNVERIFIED'}):
            self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                                        '--writers-stopped'), 0)
        self.assertTrue(list(self.output.glob('*.zip')))
        self.assertIn('UNVERIFIED', next(self.output.glob('*/RUN.log')).read_text())
        for path, raw in self.before.items():
            self.assertEqual(Path(path).read_bytes(), raw)

    def test_requires_stopped_writer_declaration_and_persists_failure(self):
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev), 1)
        status = json.loads(next(self.output.glob('*/STATUS.json')).read_text())
        self.assertEqual(status['status'], 'FAILED')
        self.assertTrue(next(self.output.glob('*/RUN.log')).is_file())
        self.assertFalse(list(self.output.rglob('*.zip')))

    def test_plan_only_does_not_create_zip(self):
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev, '--plan-only'), 0)
        self.assertFalse(list(self.output.rglob('*.zip')))

    def test_source_sidecar_refused_without_modifying_database(self):
        Path(str(self.db) + '-wal').write_bytes(b'synthetic active WAL')
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev, '--writers-stopped'), 1)
        self.assertEqual(self.db.read_bytes(), self.before[str(self.db)])

    def test_corrupt_generation_anchor_never_publishes_zip(self):
        (self.gen / 'store.sqlite').write_bytes(b'corrupt')
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev, '--writers-stopped'), 1)
        self.assertFalse(list(self.output.rglob('*.zip')))

    def test_strict_source_change_reports_the_exact_path_without_publishing(self):
        changed = self.runtime / 'case-memory/artifacts/한글 공백.json'
        original = tool.enumerate_paths
        calls = 0
        def inventory(*args, **kwargs):
            nonlocal calls
            value = original(*args, **kwargs)
            calls += 1
            if calls == 1:
                changed.write_text('modified while packaging')
            return value
        with patch.object(tool, 'enumerate_paths', side_effect=inventory):
            self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                                        '--writers-stopped'), 1)
        self.assertFalse(list(self.output.glob('*.zip')))
        report = json.loads(next(self.output.glob('*/SOURCE_CHANGES.json')).read_text())
        target = '/' + changed.relative_to(self.source).as_posix()
        self.assertIn(target, [row['path'] for row in report['inventory_changes']])
        self.assertIn(target, next(self.output.glob('*/SOURCE_CHANGES.txt')).read_text())

    def test_live_zip_reports_additions_and_missing_files_and_finishes(self):
        removed = self.runtime / 'case-memory/artifacts/한글 공백.json'
        added = removed.parent / 'new.txt'
        original = tool.enumerate_paths
        calls = 0
        def inventory(*args, **kwargs):
            nonlocal calls
            value = original(*args, **kwargs)
            calls += 1
            if calls == 1:
                removed.unlink()
                added.write_text('added after first inventory')
            return value
        with patch.object(tool, 'enumerate_paths', side_effect=inventory):
            _, bundle = self.pack('--allow-source-changes')
        manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        report = manifest['source_changes']
        changes = {row['path']: row['change'] for row in report['inventory_changes']}
        self.assertEqual(changes['/' + added.relative_to(self.source).as_posix()], 'added')
        self.assertEqual(changes['/' + removed.relative_to(self.source).as_posix()], 'removed')
        self.assertIn('/' + removed.relative_to(self.source).as_posix(), [row['path'] for row in report['skipped_files']])
        self.assertFalse(manifest['archive_restore_eligible'])
        self.assertFalse(report['cross_file_atomic'])
        self.assertTrue((bundle / 'SOURCE_CHANGES.txt').is_file())
        self.assertEqual(self.restore(bundle, '--accept-live-archive'), 1)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_live_raw_copy_stops_at_opened_size_and_records_growth(self):
        growing = self.runtime / 'growing.log'
        growing.write_bytes(b'abcdefgh1234')
        original_open = Path.open
        injected = False
        class GrowingReader:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, size):
                nonlocal injected
                chunk = self.stream.read(size)
                if not injected:
                    injected = True
                    with original_open(growing, 'ab') as writer:
                        writer.write(b'new ongoing writes' * 100)
                return chunk
        def open_path(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return GrowingReader(stream) if path == growing and args == ('rb',) else stream
        with patch.object(Path, 'open', open_path), patch.object(tool, 'CHUNK', 4):
            _, bundle = self.pack('--allow-source-changes')
        self.assertEqual((bundle / 'payload' / growing.relative_to(self.source)).read_bytes(), b'abcdefgh1234')
        data = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        target = '/' + growing.relative_to(self.source).as_posix()
        self.assertEqual(data['files'][target]['bytes'], 12)
        self.assertIn(target, [row['path'] for row in data['source_changes']['copy_changes']])

    def test_live_sqlite_wal_copies_committed_rows_without_checkpointing_source(self):
        with contextlib.closing(sqlite3.connect(self.db)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('INSERT INTO sw_knowledge VALUES(?)', ('committed in WAL',))
            writer.commit()
            source_bytes = self.db.read_bytes()
            wal_path = Path(str(self.db) + '-wal')
            wal_bytes = wal_path.read_bytes()
            _, bundle = self.pack('--allow-source-changes')
            self.assertEqual(self.db.read_bytes(), source_bytes)
            self.assertEqual(wal_path.read_bytes(), wal_bytes)
            copy = bundle / 'payload' / self.db.relative_to(self.source)
            with contextlib.closing(sqlite3.connect(copy.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT payload FROM sw_knowledge').fetchall()[-1][0], 'committed in WAL')
            self.assertFalse(Path(str(copy) + '-wal').exists())
            data = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
            self.assertEqual(data['schema_version'], tool.LIVE_FORMAT)
            self.assertIn(str(tool.RUNTIME / 'case-memory/cases-v4.sqlite-wal'),
                          data['source_changes']['sqlite_sidecars_excluded'])
            self.assertEqual(self.restore(bundle), 1)
            self.assertEqual(list(self.destination.iterdir()), [])
            self.assertEqual(self.restore(bundle, '--accept-live-archive'), 0)

    def test_live_generation_mismatch_is_archived_and_flagged_without_automatic_restore(self):
        (self.gen / 'store.sqlite').write_bytes(b'changed generation file')
        _, bundle = self.pack('--allow-source-changes')
        data = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        self.assertFalse(data['archive_restore_eligible'])
        self.assertEqual(data['source_changes']['generation_binding_mismatches'][0]['path'],
                         str(tool.GENERATION / 'store.sqlite'))
        self.assertEqual(self.restore(bundle, '--accept-live-archive'), 1)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_live_backup_timeout_reports_omissions_and_publishes_zip(self):
        with patch.object(tool, 'sqlite_snapshot', side_effect=TimeoutError('busy SQLite')):
            _, bundle = self.pack('--allow-source-changes')
        data = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        self.assertFalse(data['archive_restore_eligible'])
        self.assertTrue(data['source_changes']['skipped_files'])
        self.assertEqual(data['source_changes']['skipped_files'][0]['error_type'], 'TimeoutError')
        self.assertFalse(list(self.output.glob('*/sqlite-backup-*')))

    def test_sqlite_backup_deadline_removes_only_temporary_copy(self):
        output = self.base / 'timeout.sqlite'
        before = self.db.read_bytes()
        with self.assertRaises(TimeoutError):
            tool.sqlite_snapshot(self.db, output, timeout=-1)
        self.assertFalse(output.exists())
        self.assertEqual(self.db.read_bytes(), before)

    def test_live_pack_does_not_require_a_false_stopped_writer_declaration(self):
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                                    '--allow-source-changes'), 0)
        data = json.loads(next(self.output.glob('*/DATA_MANIFEST.json')).read_text())
        self.assertFalse(data['writers_stopped_declared'])
        self.assertFalse(data['consistency']['cross_file_atomic'])

    def test_corrupt_unpacked_payload_copies_nothing(self):
        _, bundle = self.pack()
        (bundle / 'payload' / tool.GENERATION.relative_to('/') / 'store.sqlite').write_bytes(b'corrupt')
        self.assertEqual(self.restore(bundle), 1)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_existing_different_destination_is_not_overwritten(self):
        _, bundle = self.pack()
        path = self.destination / tool.RUNTIME.relative_to('/') / 'case-memory/cases-v4.sqlite'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'existing authority')
        self.assertEqual(self.restore(bundle), 1)
        self.assertEqual(path.read_bytes(), b'existing authority')
        self.assertFalse((self.destination / tool.GENERATION.relative_to('/')).exists())

    def test_symlink_source_and_destination_refused(self):
        link = self.runtime / 'case-memory/link'
        link.symlink_to(self.db)
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev, '--writers-stopped'), 1)
        link.unlink()
        _, bundle = self.pack()
        target_base = self.destination / tool.BASE.relative_to('/')
        target_base.mkdir(parents=True)
        (target_base / '8-agent').symlink_to(self.source / tool.BASE.relative_to('/') / '8-agent', target_is_directory=True)
        self.assertEqual(self.restore(bundle), 1)

    def test_mount_entry_alias_pack_and_restore_preserve_logical_paths_and_bytes(self):
        source_entry = self.source / tool.BASE.relative_to('/')
        actual_source = self.base / 'actual-source-volume'
        shutil.move(source_entry, actual_source)
        source_entry.symlink_to(actual_source, target_is_directory=True)
        _, bundle = self.pack()
        manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        self.assertEqual(manifest['generation'], str(tool.GENERATION))
        self.assertNotIn(str(actual_source), json.dumps(manifest['files']))
        actual_destination = self.base / 'actual-destination-volume'
        actual_destination.mkdir()
        destination_entry = self.destination / tool.BASE.relative_to('/')
        destination_entry.parent.mkdir(parents=True)
        destination_entry.symlink_to(actual_destination, target_is_directory=True)
        self.assertEqual(self.restore(bundle), 0)
        self.assertEqual(self.restore(bundle), 0)
        self.assertTrue(source_entry.is_symlink())
        self.assertTrue(destination_entry.is_symlink())
        for source, raw in self.before.items():
            self.assertEqual(Path(source).read_bytes(), raw)
            destination = self.destination / Path(source).relative_to(self.source)
            self.assertEqual(destination.read_bytes(), raw)

    def test_explicit_field_paths_and_unset_state_bypass_stale_codespace_settings(self):
        (self.dev / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_RUNTIME_DIR=/home/genos/DEV/GENOS_DATA/runtime\nGENOS_STATE_DIR=/home/genos/DEV/GENOS_DATA/state\n')
        _, bundle = self.pack('--generation', tool.GENERATION, '--runtime', tool.RUNTIME, '--state-unset')
        manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        self.assertEqual(manifest['generation'], str(tool.GENERATION))
        self.assertEqual(manifest['runtime'], str(tool.RUNTIME))
        self.assertIsNone(manifest['state'])
        self.assertEqual(self.restore(bundle), 0)

    def test_separate_state_and_shortcut_pointer_generation(self):
        state = tool.BASE / 'state'
        memory = self.source / state.relative_to('/') / 'case-memory'
        selected_db = memory / 'generations/g1/cases-v4.sqlite'
        selected_db.parent.mkdir(parents=True)
        selected_db.write_bytes(self.db.read_bytes())
        (selected_db.parent / 'artifacts').mkdir()
        receipt = {'fixture': True}
        digest = hashlib.sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        (memory / 'SHORTCUT_CURRENT.json').write_text(json.dumps({'schema_version': 'shortcut-store-pointer-v1',
           'path': 'generations/g1/cases-v4.sqlite', 'receipt': receipt, 'receipt_hash': digest}))
        _, bundle = self.pack('--state', state)
        manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        self.assertEqual(manifest['shortcut_database'], str(state / 'case-memory/generations/g1/cases-v4.sqlite'))
        self.assertEqual(self.restore(bundle), 0)
        self.assertEqual((self.destination / selected_db.relative_to(self.source)).read_bytes(), selected_db.read_bytes())

    def test_current_selection_and_secret_environment_omission(self):
        root = tool.BASE / '8-agent'
        pointer = self.source / root.relative_to('/') / 'generations/CURRENT.json'
        pointer.parent.mkdir()
        pointer.write_text(json.dumps({'schema_version': 'genos-current-generation-v1',
                                      'path': str(tool.GENERATION), 'manifest_sha256': tool.sha(self.gen / 'manifest.json')}))
        (self.dev / '.env').write_text('GENOS_DATA_ROOT=' + str(root) + '\nAPI_KEY=FAKE_SECRET_NEVER_PACK\n')
        _, bundle = self.pack()
        text = (bundle / 'DATA_MANIFEST.json').read_text()
        self.assertNotIn('FAKE_SECRET', text)
        self.assertEqual(json.loads(text)['selection'], 'GENOS_DATA_ROOT/CURRENT')
        self.assertEqual(self.restore(bundle), 0)
        self.assertEqual((self.destination / pointer.relative_to(self.source)).read_bytes(), pointer.read_bytes())

    def test_outside_shared_prefix_refused(self):
        self.assertEqual(self.invoke('pack', '--source-prefix', self.source, '--code-root', self.dev,
                                    '--state', '/var/lib/agent', '--writers-stopped'), 1)

    def test_destination_sidecar_refused_before_copy(self):
        _, bundle = self.pack()
        path = self.destination / tool.RUNTIME.relative_to('/') / 'case-memory/cases-v4.sqlite'
        path.parent.mkdir(parents=True)
        Path(str(path) + '-wal').write_bytes(b'not a stopped target')
        self.assertEqual(self.restore(bundle), 1)
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
