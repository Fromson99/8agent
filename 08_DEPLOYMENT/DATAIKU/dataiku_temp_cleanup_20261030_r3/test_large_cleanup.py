import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import cleanup_large_archives as c


class Folder:
    def __init__(self, objects):
        self.objects = objects
    def list_paths_in_partition(self):
        return list(self.objects)
    def get_download_stream(self, path):
        return io.BytesIO(self.objects[path])


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='large-cleanup-contract-')
        self.root = Path(self.tmp.name)
        self.work = self.root / 'legal-recipes-test'
        self.work.mkdir()
        self.file = self.work / 'PIPELINE_SUPPORT.zip'
        self.payload = b'synthetic ZIP content for deletion contract' * 200
        self.file.write_bytes(self.payload)
        os.utime(self.file, (time.time() - 3600, time.time() - 3600))
        self.checkpoint = self.work / 'state.json'
        self.checkpoint.write_text('{"status":"FAILED"}')
        self.folder = Folder({'/PIPELINE_SUPPORT.zip': self.payload})
        self.guard = patch.object(c, 'process_guard', return_value=None)
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.tmp.cleanup()

    def clean(self, folder=None, lookup=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return c.delete_verified(self.file, folder or self.folder,
                                     lookup or (lambda f, h, n: c.support_backup(f)), len(self.payload))

    def test_matching_retained_object_only_zip_deleted(self):
        before = c.stamp(self.checkpoint)
        out = self.clean()
        self.assertEqual(out['result'], 'DELETED_VERIFIED_BACKUP')
        self.assertFalse(self.file.exists())
        self.assertEqual(c.stamp(self.checkpoint), before)
        self.assertEqual(self.folder.objects['/PIPELINE_SUPPORT.zip'], self.payload)

    def test_corrupted_backup_preserves_local(self):
        with self.assertRaisesRegex(ValueError, 'NO_VERIFIED_BACKUP'):
            self.clean(Folder({'/PIPELINE_SUPPORT.zip': b'X' * len(self.payload)}))
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_truncated_backup_preserves_local(self):
        with self.assertRaisesRegex(ValueError, 'NO_VERIFIED_BACKUP'):
            self.clean(Folder({'/PIPELINE_SUPPORT.zip': self.payload[:-1]}))
        self.assertTrue(self.file.exists())

    def test_missing_remote_preserves_local(self):
        with self.assertRaisesRegex(ValueError, 'NOT_FOUND'):
            self.clean(Folder({}))
        self.assertTrue(self.file.exists())

    def test_duplicate_names_match_actual_bytes(self):
        folder = Folder({'/PIPELINE_SUPPORT.zip': b'old copy',
                         '/PIPELINE_SUPPORT (1).zip': self.payload})
        result = self.clean(folder)
        self.assertEqual(result['retained_remote'], '/PIPELINE_SUPPORT (1).zip')
        self.assertEqual(len(result['candidate_failures']), 1)
        self.assertFalse(self.file.exists())

    def test_nested_and_numbered_name_supported(self):
        result = self.clean(Folder({'/old-inputs/PIPELINE_SUPPORT (3).zip': self.payload}))
        self.assertEqual(result['retained_remote'], '/old-inputs/PIPELINE_SUPPORT (3).zip')

    def test_local_changed_during_backup_check_preserved(self):
        def changed(folder, sha, size):
            self.file.write_bytes(b'new version')
            return ['/PIPELINE_SUPPORT.zip']
        with self.assertRaisesRegex(ValueError, 'LOCAL_CHANGED_BEFORE_DELETE'):
            self.clean(lookup=changed)
        self.assertTrue(self.file.exists())

    def test_unknown_process_visibility_blocks_mutation(self):
        with patch.object(c, 'process_guard', side_effect=ValueError('PROCESS_VISIBILITY_INCOMPLETE')):
            with self.assertRaisesRegex(ValueError, 'VISIBILITY'):
                self.clean()
        self.assertTrue(self.file.exists())

    def test_link_and_recent_file_refused(self):
        link = self.work / 'linked.zip'
        link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            c.stamp(link)
        self.file.touch()
        with self.assertRaisesRegex(ValueError, 'RECENT'):
            self.clean()

    def test_locator_ignores_generation_and_detects_ambiguity(self):
        other = self.root / 'generation'
        other.mkdir()
        (other / self.file.name).write_bytes(self.payload)
        self.assertEqual(c.locate(self.root, self.file.name, len(self.payload)), self.file)
        second = self.root / 'legal-recipes-second'
        second.mkdir()
        (second / self.file.name).write_bytes(self.payload)
        with self.assertRaisesRegex(ValueError, 'MULTIPLE'):
            c.locate(self.root, self.file.name, len(self.payload))

    def audit_folder(self, *, referenced=True):
        sha = hashlib.sha256(self.payload).hexdigest()
        relative = '_pipeline/blobs/' + sha + '.zip'
        value = {'audit_blob': {'path': relative, 'sha256': sha, 'bytes': len(self.payload)}} if referenced else {}
        raw = json.dumps(value).encode()
        checkpoint = c.NAMESPACE + '_pipeline/jobs/test/checkpoint-0000000001-' + hashlib.sha256(raw).hexdigest() + '.json'
        return Folder({c.NAMESPACE + relative: self.payload, checkpoint: raw}), sha

    def test_audit_verifies_actual_backup(self):
        folder, sha = self.audit_folder()
        remote = c.audit_backup(folder, sha, len(self.payload))
        self.assertEqual(folder.objects[remote[0]], self.payload)
        result = self.clean(folder, c.audit_backup)
        self.assertEqual(result['result'], 'DELETED_VERIFIED_BACKUP')

    def test_audit_without_current_reference_but_identical_backup_deleted(self):
        folder, _ = self.audit_folder(referenced=False)
        result = self.clean(folder, c.audit_backup)
        self.assertEqual(result['result'], 'DELETED_VERIFIED_BACKUP')
        self.assertFalse(self.file.exists())

    def test_checkpoint_untouched_and_not_used_as_backup_proof(self):
        folder, _ = self.audit_folder()
        key = next(k for k in folder.objects if 'checkpoint-' in k)
        folder.objects[key] = b'{}'
        self.clean(folder, c.audit_backup)
        self.assertEqual(folder.objects[key], b'{}')

    def test_audit_hash_filename_does_not_replace_content_verification(self):
        folder, _ = self.audit_folder(referenced=False)
        key = next(k for k in folder.objects if k.endswith('.zip'))
        folder.objects[key] = b'X' * len(self.payload)
        with self.assertRaisesRegex(ValueError, 'NO_VERIFIED_BACKUP'):
            self.clean(folder, c.audit_backup)
        self.assertTrue(self.file.exists())

    def test_read_failure_preserves_local(self):
        with patch.object(self.folder, 'get_download_stream', side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError, 'NO_VERIFIED_BACKUP'):
                self.clean()
        self.assertTrue(self.file.exists())

    def test_recipe_configuration_parsed_without_execution(self):
        cfg = dict(landing='ehA8dpVm', structured='known-id', raw='r', load='l', connection='c')
        code = 'raise RuntimeError("must not execute")\nrun_recipe("structure", ' + repr(cfg) + ')'
        self.assertEqual(c.recipe_config(code), cfg)
        with self.assertRaises(ValueError):
            c.recipe_config('run_recipe("structure", fetch_remote_configuration())')

    def test_actual_open_file_guard(self):
        self.guard.stop()
        try:
            with self.file.open('rb'):
                with self.assertRaisesRegex(ValueError, 'FILE_IN_USE'):
                    c.process_guard(c.stamp(self.file))
        finally:
            self.guard.start()


if __name__ == '__main__':
    unittest.main(verbosity=2)
