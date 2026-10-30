"""Local synthetic HTTP contracts; never contact GENOS or a model."""
import argparse
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('probe', ROOT / 'probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calls = []
        self.reply = 'path'
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.calls.append(body)
                status, headers = 200, {}
                if outer.reply == 'path':
                    self.assertion = Path(body['file_path']).read_bytes()
                    token = re.search(rb'GENOSPROBE[A-F0-9]{16}', self.assertion).group().decode()
                    response = {'code': 0, 'data': [{'text': token}]}
                elif outer.reply == 'base64':
                    assert 'file_path' not in body
                    raw = base64.b64decode(body['file_content_base64'])
                    token = re.search(rb'GENOSPROBE[A-F0-9]{16}', raw).group().decode()
                    response = {'code': 0, 'data': {'document': {'texts': [{'text': token}]}}}
                elif outer.reply == 'missing':
                    response = {'code': 1, 'errMsg': 'file not found'}
                elif outer.reply == 'echo':
                    response = {'code': 0, 'data': {'request': body, 'text': body.get('file_path', '')}}
                elif outer.reply == 'wrong_text':
                    response = {'code': 0, 'data': [{'text': 'GENOSPROBE0000000000000000'}]}
                elif outer.reply == 'redirect':
                    status, headers = 302, {'Location': '/second'}
                    response = {'code': 0, 'data': []}
                elif outer.reply == 'secret':
                    response = {'code': 1, 'errMsg': 'test-only-secret'}
                elif outer.reply == 'malformed':
                    response = b'not json'
                else:
                    status, response = 503, {'code': 1}
                raw = response if isinstance(response, bytes) else json.dumps(response).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%s/run' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def execute(self, mode='path'):
        args = argparse.Namespace(root=str(self.root), remote_root=None, mode=mode,
                                  url=self.url, id=None, timeout=5, context='unknown')
        with contextlib.redirect_stdout(io.StringIO()):
            return probe.run(args)

    def test_path_only_reads_unique_pdf_and_recommends_root(self):
        result = self.execute()
        self.assertEqual(result['status'], 'PATH_READ_CONFIRMED')
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('file_content_base64', self.calls[0])
        self.assertNotIn(result['marker'], json.dumps(self.calls[0]))
        self.assertFalse(result['field_code_serving_proven'])
        self.assertEqual(Path(result['source_path']).stat().st_mode & 0o777, 0o640)
        self.assertEqual(result['settings_if_test_ran_in_actual_serving_pod']['GENOS_PREPROCESSOR_SHARED_ROOT'], str(self.root))

    def test_base64_has_no_path_and_does_not_recommend_shared_root(self):
        self.reply = 'base64'
        result = self.execute('base64')
        self.assertEqual(result['status'], 'BASE64_READ_CONFIRMED')
        self.assertNotIn('file_path', self.calls[0])
        self.assertNotIn('settings_if_test_ran_in_actual_serving_pod', result)

    def test_http_success_is_not_file_visibility(self):
        for reply in ('echo', 'wrong_text'):
            with self.subTest(reply=reply):
                self.reply = reply
                result = self.execute()
                self.assertEqual(result['status'], 'HTTP_OK_BUT_PDF_CONTENT_UNCONFIRMED')

    def test_missing_path_is_not_success_and_preserves_source(self):
        self.reply = 'missing'
        result = self.execute()
        self.assertEqual(result['status'], 'API_ERROR')
        self.assertTrue(Path(result['source_path']).is_file())
        self.assertTrue((Path(result['evidence_dir']) / 'result.json').is_file())

    def test_no_redirect_or_retry(self):
        for reply in ('redirect', 'unavailable'):
            with self.subTest(reply=reply):
                self.reply = reply
                before = len(self.calls)
                result = self.execute()
                self.assertEqual(result['status'], 'HTTP_ERROR')
                self.assertEqual(len(self.calls) - before, 1)

    def test_invalid_json(self):
        self.reply = 'malformed'
        self.assertEqual(self.execute()['status'], 'INVALID_JSON')

    def test_timeout_preserves_input_without_retry(self):
        with patch.object(probe, 'post_once', side_effect=TimeoutError('timeout')) as call:
            result = self.execute()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['status'], 'TRANSPORT_UNKNOWN')
        self.assertTrue(result['remote_processing_may_continue'])
        self.assertTrue(Path(result['source_path']).is_file())

    def test_secret_not_in_reports_or_saved_response(self):
        self.reply = 'secret'
        with patch.dict(os.environ, {'GENOS_PREPROCESSOR_API_KEY': 'test-only-secret'}):
            result = self.execute()
        for file in Path(result['evidence_dir']).iterdir():
            self.assertNotIn(b'test-only-secret', file.read_bytes())

    def test_invalid_root_and_symlink_before_http(self):
        link = self.root / 'link'
        link.symlink_to(self.root)
        for root in ('tmp', '/tmp/../tmp', str(link)):
            with self.assertRaises(ValueError):
                probe.local_root(root)
        self.assertEqual(len(self.calls), 0)

    def test_response_limit(self):
        with patch.object(probe, 'post_once', return_value=(200, b'x' * (probe.MAX_RESPONSE + 1))):
            result = self.execute()
        self.assertEqual(result['status'], 'RESPONSE_TOO_LARGE')

    def test_final_shell_txt_runs_the_same_probe(self):
        command = ['bash', str(ROOT / 'GENOS_187_TEST_20261027_R1.txt'), str(self.root), '--url', self.url]
        child = subprocess.run(command, text=True, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn('PATH_READ_CONFIRMED', child.stdout)
        self.assertEqual(len(self.calls), 1)

    def test_real_pdf_text_and_page(self):
        import fitz
        marker = 'GENOSPROBE1234567890ABCDEF'
        doc = fitz.open(stream=probe.pdf_bytes(marker), filetype='pdf')
        self.assertEqual(len(doc), 1)
        self.assertIn(marker, doc[0].get_text())
        doc.close()

    def test_exact_r3_settings_diagnostic(self):
        code_root = self.root / 'code'
        settings = code_root / '02_BACKEND/lawrag/core/genos_preprocessor.py'
        settings.parent.mkdir(parents=True)
        import zipfile
        archive = ROOT.parent / 'pipeline_preprocessor_20261027_r3/GENOS_DATAIKU_COMPUTE_20261027_R3.zip'
        with zipfile.ZipFile(archive) as source:
            settings.write_bytes(source.read('GENOS_DATAIKU_COMPUTE_20261027_R3/02_BACKEND/lawrag/core/genos_preprocessor.py'))
        env = dict(GENOS_PREPROCESSOR_ID='187', GENOS_PREPROCESSOR_SHARED_ROOT='tmp')
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()) as out:
            rc = probe.main(['--check-r3-config', '--code-root', str(code_root)])
        self.assertEqual(rc, 2)
        self.assertIn('must be absolute', out.getvalue())
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
