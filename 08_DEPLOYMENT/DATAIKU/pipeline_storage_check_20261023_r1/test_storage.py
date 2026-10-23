"""Test the exact delivered cell, reusing the pinned client/service fixture."""
from pathlib import Path
import hashlib
import importlib.util
import json
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('recovery_fixture', HERE.parent/'pipeline_recovery_20261023_r1/test_recovery.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class StorageTests(base.RecoveryTests):
    def setUp(self):
        super().setUp()
        self.payload = (HERE/'DATAIKU_PIPELINE_STORAGE_CHECK_20261023_R1.txt').read_bytes()
        exec(compile(self.payload, 'delivered-storage', 'exec'), self.ns)
        self.before = dict(self.folder.data)
        self.initial_calls = len(self.calls)

    def check(self):
        result = self.ns['pipeline_recovery_storage_check']('old-job')
        self.assertEqual(len(self.calls), self.initial_calls)
        self.assertFalse(result['pipeline_released'])
        self.assertEqual(self.server_state()['status'], 'FAILED')
        for path, raw in self.before.items():
            self.assertEqual(self.folder.data[path], raw)
        return json.loads(Path(result['report_file']).read_text())

    def test_four_small_probes_do_not_claim_large_upload_works(self):
        report = self.check()
        self.assertEqual(report['diagnosis'], 'SMALL_FILES_OK_LARGE_UPLOAD_UNVERIFIED')
        added = set(self.folder.data)-set(self.before)
        self.assertEqual(len(added), 4)
        self.assertEqual(sum(len(self.folder.data[p]) for p in added), 8192)
        self.assertEqual(report['remote_capacity'], 'UNKNOWN')
        self.assertFalse(report['local_support']['hash_checked'])
        self.assertEqual(report['current_sql_calls'], 64)

    def test_reproduce_photo_nested_path_failure(self):
        original = self.folder.upload_stream
        def fail(path, stream):
            if '/files/' in path or path.startswith('_pipeline/diagnostics/'):
                raise OSError("None: b'4: Failure, caused by: SftpException: Failure'")
            return original(path, stream)
        self.folder.upload_stream = fail
        report = self.check()
        self.assertEqual(report['diagnosis'], 'RECOVERY_CHILD_PATH_DIFFERS')
        for row in report['probes'][2:]:
            self.assertEqual(row['operation'], 'UPLOAD')
            self.assertEqual(row['status'], 'FAILED')
            self.assertIn('SftpException', row['errors'][0]['message'])
        self.assertIn('RECOVERY_CHILD_PATH_DIFFERS', self.output.getvalue())

    def test_global_write_failure_still_has_local_report(self):
        self.folder.fail_save = True
        report = self.check()
        self.assertEqual(report['diagnosis'], 'STORAGE_WRITE_OR_READBACK_FAILED')
        self.assertEqual(len(self.folder.data), len(self.before))
        self.assertNotIn('DIAGNOSTIC_MANAGED_SAVE_FAILED', self.output.getvalue())

    def test_readback_failure_distinct_from_write(self):
        original = self.folder.get_download_stream
        def fail(path):
            if 'storage-probe-' in path:
                raise PermissionError('read denied')
            return original(path)
        self.folder.get_download_stream = fail
        report = self.check()
        self.assertTrue(all(p['operation'] == 'READBACK' for p in report['probes']))
        self.assertTrue(all(p['status'] == 'FAILED' for p in report['probes']))

    def test_readback_corruption_not_success(self):
        original = self.folder.upload_stream
        def corrupt(path, stream):
            original(path, stream)
            self.folder.data[path] = b'truncated'
        self.folder.upload_stream = corrupt
        report = self.check()
        self.assertTrue(all(p['status'] == 'FAILED' for p in report['probes']))
        self.assertIn('STORAGE_PROBE_READBACK_MISMATCH', self.output.getvalue())

    def test_repeat_reuses_results_no_new_writes(self):
        first = self.check()
        before = list(self.folder.uploads)
        second = self.check()
        self.assertEqual(first['probes'], second['probes'])
        self.assertEqual(before, self.folder.uploads)
        self.assertIn('PROBE_REUSED', self.output.getvalue())

    def test_uncertain_write_not_retried(self):
        original = self.folder.upload_stream
        def drop(path, stream):
            original(path, stream)
            raise ConnectionResetError('after write')
        self.folder.upload_stream = drop
        report = self.check()
        self.assertTrue(all(p['status'] == 'FAILED' for p in report['probes']))
        before = list(self.folder.uploads)
        self.check()
        self.assertEqual(before, self.folder.uploads)

    def test_process_interruption_recovers_by_readback_only(self):
        original = self.folder.upload_stream
        def interrupt(path, stream):
            original(path, stream)
            raise KeyboardInterrupt('simulated interrupt')
        self.folder.upload_stream = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.check()
        self.folder.upload_stream = original
        report = self.check()
        self.assertEqual(report['probes'][0]['operation'], 'READBACK_AFTER_INTERRUPTION')
        self.assertEqual(report['probes'][0]['status'], 'PASS')
        self.assertEqual(sum('storage-probe-' in p for p in self.folder.uploads), 4)

    def test_existing_partial_old_archive_preserved_unread(self):
        expected = self.old_state['archives']['support']
        remote = '_pipeline/recovery/'+self.old_id+'/files/'+expected['sha256']+'.bin'
        self.folder.data[remote] = b'old partial'
        original = self.folder.get_download_stream
        def forbid(path):
            if path == remote or path.endswith('.zip'):
                raise AssertionError('large file read forbidden')
            return original(path)
        self.folder.get_download_stream = forbid
        report = self.check()
        self.assertTrue(report['old_upload_listed'])
        self.assertEqual(report['old_upload_completeness'], 'NOT_VERIFIED')
        self.assertEqual(self.folder.data[remote], b'old partial')

    def test_expired_recovery_is_reported_without_reset(self):
        # Seed the same recovery event format as the shipped release helper.
        value = {'identity': {'old_job_id': self.old_id, 'new_job_id': self.new_id,
                              'current_job_name': 'new-job'}, 'deadline': time.time()-1,
                 'api_calls': 37, 'phase': 'CREATED'}
        raw = json.dumps(value).encode()
        path = '_pipeline/recovery/'+self.old_id+'/event-0000000001-'+hashlib.sha256(raw).hexdigest()+'.json'
        self.folder.data[path] = raw
        report = self.check()
        self.assertTrue(report['recovery_record']['deadline_expired'])
        self.assertEqual(report['recovery_record']['api_calls'], 37)
        self.assertEqual(self.folder.data[path], raw)
        self.assertIn('RECOVERY_DEADLINE_EXHAUSTED', self.output.getvalue())

    def test_own_deadline_is_preserved_after_interruption(self):
        original = self.folder.upload_stream
        def interrupt(path, stream):
            raise KeyboardInterrupt()
        self.folder.upload_stream = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.check()
        self.folder.upload_stream = original
        with patch.object(self.ns['time'], 'time', return_value=time.time()+400):
            report = self.check()
        self.assertTrue(all(p['status'] == 'NOT_ATTEMPTED' for p in report['probes']))
        self.assertEqual(set(self.folder.data), set(self.before))

    def test_failed_local_intent_save_prevents_remote_write(self):
        def fail(*args):
            raise OSError('local disk full')
        self.ns['_sc_append'] = fail
        with self.assertRaisesRegex(self.ns['RunError'], 'local disk full'):
            self.check()
        self.assertEqual(set(self.folder.data), set(self.before))
        self.assertEqual(len(self.calls), self.initial_calls)

    def test_bad_checkpoint_hash_blocks_all_writes(self):
        path = next(p for p in self.folder.data if p.startswith('_pipeline/jobs/old-job/'))
        self.folder.data[path] += b' '
        before = list(self.folder.uploads)
        with self.assertRaisesRegex(self.ns['RunError'], 'STORAGE_CHECKPOINT_HASH'):
            self.check()
        self.assertEqual(before, self.folder.uploads)

    def test_secrets_redacted_in_console_journal_and_report(self):
        def fail(path, stream):
            raise OSError('SftpException api-secret '+self.old_state['job_token']+' password=not-for-display')
        self.folder.upload_stream = fail
        report = self.check()
        text = self.output.getvalue()+json.dumps(report)
        for path in (self.work/'diagnostics/storage-checks').iterdir():
            text += path.read_text()
        for secret in ('api-secret', self.old_state['job_token'], 'not-for-display'):
            self.assertNotIn(secret, text)

    def test_checkpoint_change_does_not_reuse_unrelated_check(self):
        self.check()
        changed = {**self.old_checkpoint, 'reserved_sql_calls': 129}
        self.put_checkpoint('old-job', changed, 2)
        before = list(self.folder.uploads)
        with self.assertRaisesRegex(self.ns['RunError'], 'STORAGE_CHECK_IDENTITY_CHANGED'):
            self.check()
        self.assertEqual(before, self.folder.uploads)

    def test_whole_cell_uses_photo_job_and_inherited_current_settings(self):
        old_name = 'run_20261023_01_20261023_01'
        new_name = 'run_20261023_01_20261023_r2_01'
        self.put_checkpoint(old_name, self.old_checkpoint)
        self.put_checkpoint(new_name, self.new_checkpoint)
        self.ns['run'].__defaults__ = ('prepare', 'LEGAL_PIPELINE_WORKSPACE', str(self.work), new_name)
        for name in list(self.ns):
            if name.startswith('_rc_') or name in ('_Recovery', 'pipeline_release_previous'):
                del self.ns[name]
        self.ns['__name__'] = '__main__'
        exec(compile(self.payload, 'delivered-complete-cell', 'exec'), self.ns)
        result = self.ns['STORAGE_CHECK_RESULT']
        report = json.loads(Path(result['report_file']).read_text())
        self.assertEqual(report['failed_job'], old_name)
        self.assertEqual(report['current_job'], new_name)
        self.assertEqual(report['status'], 'CHECK_COMPLETE')
        self.assertEqual(len(self.calls), self.initial_calls)
        self.assertFalse(result['pipeline_released'])


if __name__ == '__main__':
    suite = unittest.TestSuite(StorageTests(name) for name in StorageTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
