import contextlib
import io
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

import cleanup_temp as c


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cleanup-contract-')
        self.root = Path(self.tmp.name)
        self.job = self.root / c.NFS / c.JOB
        self.job.mkdir(parents=True)
        self.archive = self.job / 'oracle-receipts.zip'
        self.extracted = self.job / 'oracle-import-r2'
        self.extracted.mkdir()
        self.values = {'full-state.json': b'{"stage":"FAILED"}', 'source/journal.jsonl': b'{"seq":1}\n'}
        for name, value in self.values.items():
            target = self.extracted / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, value in self.values.items():
                z.writestr(name, value)
        self.age(self.archive)
        # Most mutation contracts assume a fully visible, idle process namespace.
        # Local WSL has two same-user non-dumpable processes; the separate real
        # visibility test below verifies that this correctly blocks deletion.
        self.real_process_files = c.process_files
        self.process_mock = patch.object(c, 'process_files', return_value=(set(), [], []))
        self.process_mock.start()

    def tearDown(self):
        self.process_mock.stop()
        self.tmp.cleanup()

    def age(self, path):
        os.utime(path, (time.time() - 3600, time.time() - 3600))

    def clean(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return c.clean_one(self.archive, 'receipt_archive', apply=True, **kw)

    def test_identical_archive_deleted_checkpoint_unchanged(self):
        before = {name: c.signature(self.extracted / name) for name in self.values}
        self.assertEqual(self.clean()['result'], 'DELETED_DUPLICATE')
        self.assertFalse(self.archive.exists())
        for name, value in self.values.items():
            self.assertEqual((self.extracted / name).read_bytes(), value)
            self.assertEqual(c.signature(self.extracted / name), before[name])

    def test_changed_receipt_preserved(self):
        (self.extracted / 'full-state.json').write_bytes(b'{"stage":"COMPLETE"}')
        with self.assertRaisesRegex(ValueError, 'NO_IDENTICAL'):
            self.clean()
        self.assertTrue(self.archive.exists())

    def test_missing_receipt_preserved(self):
        (self.extracted / 'source/journal.jsonl').unlink()
        with self.assertRaisesRegex(ValueError, 'NO_IDENTICAL'):
            self.clean()

    def test_symlink_receipt_preserved(self):
        path = self.extracted / 'full-state.json'
        value = path.read_bytes()
        path.unlink()
        outside = self.root / 'outside.json'
        outside.write_bytes(value)
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'NO_IDENTICAL'):
            self.clean()
        self.assertEqual(outside.read_bytes(), value)

    def test_open_archive_preserved_real_fd(self):
        with self.archive.open('rb'):
            opened, deleted, errors = self.real_process_files()
            self.assertIn(c.signature(self.archive)[:2], opened)
            with patch.object(c, 'process_files', return_value=(opened, deleted, errors)):
                with self.assertRaisesRegex(ValueError, 'OPEN_IN_PROCESS'):
                    self.clean()
        self.assertTrue(self.archive.exists())

    def test_recent_archive_preserved(self):
        self.archive.touch()
        with self.assertRaisesRegex(ValueError, 'RECENT'):
            self.clean()

    def test_process_visibility_failure_preserved(self):
        with patch.object(c, 'process_files', return_value=(set(), [], ['permission'])):
            with self.assertRaisesRegex(ValueError, 'VISIBILITY'):
                self.clean()

    def test_actual_process_visibility_preserved_when_incomplete(self):
        opened, deleted, errors = self.real_process_files()
        with patch.object(c, 'process_files', return_value=(opened, deleted, errors)):
            if errors:
                with self.assertRaisesRegex(ValueError, 'VISIBILITY'):
                    self.clean()
                self.assertTrue(self.archive.exists())
            else:
                self.assertEqual(self.clean()['result'], 'DELETED_DUPLICATE')

    def test_unknown_file_and_current_db_not_candidates(self):
        for path in (self.job / 'generation/fulltext/units.sqlite',
                     self.job / 'generation/store.sqlite',
                     self.extracted / 'full-state.json',
                     self.root / 'other/oracle-receipts.zip',
                     self.job / 'full-data.zip'):
            self.assertIsNone(c.candidate(path, self.root))

    def test_changed_after_proof_preserved(self):
        original = c.prove
        def changed(*args):
            value = original(*args)
            (self.extracted / 'full-state.json').write_text('new')
            return value
        with patch.object(c, 'prove', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CHANGED_BEFORE_DELETE'):
                self.clean()

    def test_zip_traversal_refused(self):
        with zipfile.ZipFile(self.archive, 'a') as z:
            z.writestr('../outside.json', b'anything')
        self.age(self.archive)
        with self.assertRaisesRegex(ValueError, 'NO_IDENTICAL'):
            self.clean()

    def test_delivered_r6b_archive_deleted_extracted_code_retained(self):
        directory = self.root / 'legal-recipes-test'
        directory.mkdir()
        archive = directory / 'package.zip'
        delivered = Path(__file__).resolve().parent.parent / 'existing_nfs_deferred_verify_20261030_r6b' / 'DATAIKU_EXISTING_NFS_CLIENT_20261030_R6B.zip'
        shutil.copyfile(delivered, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(directory / 'code')
        self.age(archive)
        code = directory / 'code/existing_client.py'
        before = c.signature(code)
        with contextlib.redirect_stdout(io.StringIO()):
            result = c.clean_one(archive, 'code_archive', apply=True)
        self.assertEqual(result['result'], 'DELETED_DUPLICATE')
        self.assertEqual(c.signature(code), before)

    def test_inventory_detects_large_files_without_following_links(self):
        large = self.job / 'generation/store.sqlite'
        large.parent.mkdir()
        large.write_bytes(b'X' * 100000)
        outside = self.root / 'external'
        outside.mkdir()
        (outside / 'linked.txt').write_text('protected')
        (self.job / 'symlink').symlink_to(outside, target_is_directory=True)
        inv, candidates = c.inventory(self.root)
        self.assertEqual(inv['largest_files'][0]['path'], str(large))
        self.assertFalse(any('/symlink/' in item['path'] for item in inv['largest_files']))
        self.assertEqual(candidates, [(self.archive, 'receipt_archive')])

    def test_inspect_never_deletes_and_rerun_idempotent(self):
        with contextlib.redirect_stdout(io.StringIO()):
            first = c.run_cleanup([self.root], apply=False)
            self.assertTrue(self.archive.exists())
            cleaned = c.run_cleanup([self.root], apply=True)
            repeated = c.run_cleanup([self.root], apply=True)
        self.assertEqual(first['deleted_archive_count'], 0)
        self.assertEqual(cleaned['deleted_archive_count'], 1)
        self.assertEqual(repeated['deleted_archive_count'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
