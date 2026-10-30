import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from experiment_json import write_raw_json, write_summary, SUMMARY_LIMIT

class WriterContracts(unittest.TestCase):
    def test_raw_roundtrip_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'raw.json.gz'
            value = {'status':'FAILED', 'reason':'원문 보존', 'rows':[{'text':'abc'*100}] * 300}
            ref = write_raw_json(p, value)
            with gzip.open(p, 'rb') as f: data = f.read()
            self.assertEqual(json.loads(data), value)
            self.assertEqual(hashlib.sha256(data).hexdigest(), ref['content_sha256'])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), ref['stored_sha256'])
            self.assertLess(ref['stored_bytes'], ref['original_bytes'])
            out = Path(d) / 'summary.json'; write_summary(out, {'status':'FAILED', 'raw':ref})
            self.assertEqual(json.loads(out.read_text())['raw'], ref)

    def test_oversized_summary_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'summary.json'
            with self.assertRaises(ValueError): write_summary(p, {'raw':['x'*1024]*1100})
            self.assertFalse(p.exists()); self.assertEqual(list(Path(d).iterdir()), [])

    def test_existing_record_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'summary.json'; p.write_bytes(b'original')
            with self.assertRaises(AssertionError): write_summary(p, {'new':True})
            self.assertEqual(p.read_bytes(), b'original')

if __name__ == '__main__': unittest.main()
