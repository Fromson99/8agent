"""Storage-only diagnostic tests; no model/provider evaluation."""
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '08_DEPLOYMENT/GENOS/handoffs/sql_candidates_20261006_r1'
spec = importlib.util.spec_from_file_location('sql_diag', FOLDER / 'diagnose_sql.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class SQLDiagnosticTests(unittest.TestCase):
    def test_mount_longest_match_and_classification(self):
        rows = [{'target': '/', 'fs': 'overlay', 'readonly': False},
                {'target': '/tmp/diag-mount', 'fs': 'nfs4', 'readonly': False}]
        self.assertEqual(diag.classify(diag.mount_for('/tmp/diag-mount/data', rows)), 'NETWORK_STORAGE')
        self.assertEqual(diag.classify(rows[0]), 'CONTAINER_LAYER_PERSISTENCE_UNKNOWN')

    def test_secrets_not_in_exported_settings_or_endpoint_result(self):
        secret = 'private-password-canary'
        env = {'DATABASE_URL': f'postgresql://user:{secret}@127.0.0.1:9/private-db',
               'PGPASSWORD': secret}
        value = diag.endpoint_probe(diag.configured_endpoints(env)[0])
        exported = json.dumps([diag.settings_present(env), value])
        self.assertNotIn(secret, exported)
        self.assertNotIn('private-db', exported)
        self.assertEqual(value['source'], 'DATABASE_URL')

    def test_scratch_preserves_existing_database_and_checks_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = Path(folder) / 'cases-v4.sqlite'
            previous.write_bytes(b'operational-database-canary')
            result = diag.scratch_probe(folder)
            self.assertEqual(result['status'], 'PASS', result)
            self.assertTrue(result['interrupted_transaction_recovery'])
            self.assertEqual(previous.read_bytes(), b'operational-database-canary')

    def test_failure_does_not_expose_exception_path(self):
        result = diag.scratch_probe('/nonexistent/private-secret-canary/base')
        self.assertEqual(result['status'], 'ERROR')
        self.assertNotIn('private-secret-canary', json.dumps(result))

    def test_complete_txt_keeps_original_and_writes_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ)
            for key in diag.SETTINGS: env.pop(key, None)
            env.update(GENOS_RUNTIME_DIR=folder, GENOS_SQL_DIAG_CONTEXT='local-mock', PGPASSWORD='secret-canary')
            previous = Path(folder) / 'case-memory/cases-v4.sqlite'
            previous.parent.mkdir()
            previous.write_bytes(b'untouched-DB')
            script = FOLDER / 'GENOS_SQL_CANDIDATES_20261006_R1.txt'
            run = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=40)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            output = next((Path(folder) / 'sql-candidate-diagnostics').iterdir())
            report = json.loads((output / 'report.json').read_text())
            receipt = json.loads((output / 'failure.json').read_text())
            self.assertEqual(receipt['exit_code'], 0)
            self.assertFalse(report['production_ready'])
            self.assertFalse(report['operational_database_opened'])
            self.assertEqual(previous.read_bytes(), b'untouched-DB')
            self.assertNotIn('secret-canary', (output / 'run.log').read_text())
            self.assertIn('NOT_VERIFIED', json.dumps(report))


if __name__ == '__main__': unittest.main()
