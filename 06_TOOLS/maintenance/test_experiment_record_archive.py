"""Small destructive-operation contracts, entirely within temporary fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

class ArchiveContracts(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('archive_under_test', Path(__file__).with_name('experiment_record_archive.py'))
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.m.ROOT = Path(self.tmp.name)
        self.m.AUDIT = self.m.ROOT / 'audit'; self.m.PLAN = self.m.AUDIT / 'plan.json'
        self.m.active_handles = lambda: (set(), [])
        self.raw = (b'{"failed":true,"original":"preserve every byte"}\n' * 5000)
        self.p = self.m.ROOT / '04_EXPERIMENTS/ADR/ADR-9000-fixture/artifacts/raw.json'
        self.p.parent.mkdir(parents=True); self.p.write_bytes(self.raw)
        self.row = dict(path=str(self.p.relative_to(self.m.ROOT)), before=self.m.metadata(self.p),
                        archive=str(self.p.relative_to(self.m.ROOT)) + '.gz',
                        receipt=str(self.p.relative_to(self.m.ROOT)) + '.gz.archive-receipt.json')

    def tearDown(self): self.tmp.cleanup()

    def test_archive_and_exact_restore(self):
        r = self.m.archive_one(self.row)
        self.assertFalse(self.p.exists()); self.assertTrue(r['verified_lossless'])
        self.assertEqual(r['original_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.m.save(self.m.PLAN, {'files': [self.row]})
        self.m.restore(path=self.row['path'])
        self.assertEqual(self.p.read_bytes(), self.raw)
        self.assertEqual(self.p.stat().st_mtime_ns, self.row['before']['mtime_ns'])
        self.assertEqual(self.p.stat().st_mode & 0o777, self.row['before']['mode'])

    def test_source_change_rejected(self):
        self.p.write_bytes(b'new evidence')
        with self.assertRaises(AssertionError): self.m.archive_one(self.row)
        self.assertEqual(self.p.read_bytes(), b'new evidence')

    def test_open_source_rejected(self):
        s = self.p.stat(); self.m.active_handles = lambda: ({(s.st_dev, s.st_ino)}, [])
        with self.assertRaises(AssertionError): self.m.archive_one(self.row)
        self.assertTrue(self.p.exists())

    def test_corrupt_archive_never_removes_source(self):
        r = self.m.archive_one(self.row)
        self.p.write_bytes(self.raw)
        self.row['before'] = self.m.metadata(self.p)
        receipt = self.m.ROOT / self.row['receipt']; r.update(status='VERIFIED', before=self.row['before'])
        self.m.save(receipt, r)
        archive = self.m.ROOT / self.row['archive']; archive.chmod(0o600); archive.write_bytes(b'corruption')
        with self.assertRaises(AssertionError): self.m.archive_one(self.row)
        self.assertEqual(self.p.read_bytes(), self.raw)

    def test_interrupted_receipt_recovery(self):
        r = self.m.archive_one(self.row); r['status'] = 'VERIFIED'
        self.m.save(self.m.ROOT / self.row['receipt'], r)
        self.assertEqual(self.m.archive_one(self.row)['status'], 'ARCHIVED')

    def test_existing_partial_preserved(self):
        archive = self.m.ROOT / self.row['archive']
        partial = archive.with_name('.' + archive.name + '.compressing'); partial.write_bytes(b'old partial')
        with self.assertRaises(AssertionError): self.m.archive_one(self.row)
        self.assertTrue(self.p.exists()); self.assertEqual(partial.read_bytes(), b'old partial')

if __name__ == '__main__': unittest.main()
