import ast
import contextlib
import hashlib
import http.server
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / 'private_delivery'
SOURCE = (OUT / 'DATAIKU_PHOTO_INPUTS_20261015_R1_CELL.txt').read_text()
MAIN = '_photo_replay_result = collect_photo_replay(globals().get("check"))'
DEFS = SOURCE[:SOURCE.rindex(MAIN)]
NS = {}
exec(compile(DEFS, 'delivered-definitions', 'exec'), NS)
REAL_INPUTS = dict(NS['PHOTO_INPUTS'])
FIXTURE_COOKIE = 'JSESSIONID=fixture-session; elevisor_for_j2ee_uid=fixture-uid'
FIXTURE_INPUTS = {**REAL_INPUTS, 'OC': 'fixture-oc', 'Cookie': FIXTURE_COOKIE}
NS['PHOTO_INPUTS'] = FIXTURE_INPUTS
sys.path.insert(0, str(HERE.parent / 'law_api_20261015_r1'))
from relay_check import RelayCheck


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def parent(self):
        s = requests.Session(); s.trust_env = False
        c = RelayCheck({'relay_origin': REAL_INPUTS['relay_origin'], 'output_root': str(self.root)}, 'different-parent-oc', session=s)
        c.calls = 1; c.blocked = True
        return c

    def test_all_photo_fields_prefilled_no_prompt(self):
        inp = json.loads(Path('/tmp/dataiku_photo_inspect/photo_inputs.json').read_text())
        self.assertTrue(REAL_INPUTS == inp)
        self.assertTrue(REAL_INPUTS['OC'] and REAL_INPUTS['Cookie'])
        self.assertNotIn('getpass', SOURCE)
        self.assertNotIn('input(', SOURCE)
        ast.parse(SOURCE, feature_version=(3, 9))

    def test_photo_values_override_parent_and_no_mutation(self):
        c = self.parent(); before = (c.out / 'summary.json').read_bytes(); captured = []
        def curl(*args):
            captured.append(args)
            return {'status': 'CURL_CONNECT_PHASE_TIMEOUT'}
        with patch.dict(NS, evidence_curl=curl), contextlib.redirect_stdout(io.StringIO()):
            r = NS['collect_photo_replay'](c)
            second = NS['collect_photo_replay'](c)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][2:4], ('fixture-oc', FIXTURE_COOKIE))
        self.assertEqual(r, second); self.assertEqual(c.calls, 1); self.assertTrue(c.blocked)
        self.assertEqual((c.out / 'summary.json').read_bytes(), before)
        self.assertFalse(r['firewall_block_confirmed']); self.assertTrue(r['request']['photo_cookie_present'])

    def test_result_redacts_credentials_and_errors(self):
        c = self.parent()
        def fail(*args): raise RuntimeError('fixture-oc ' + FIXTURE_COOKIE)
        with patch.dict(NS, evidence_curl=fail), self.assertRaises(RuntimeError): NS['collect_photo_replay'](c)
        saved = (c.out / 'photo_sample_replay_r1.json').read_text()
        self.assertNotIn('fixture-oc', saved); self.assertNotIn(FIXTURE_COOKIE, saved)
        self.assertEqual(json.loads(saved)['status'], 'DIAGNOSTIC_ERROR_NO_AUTORETRY')

    def test_interruption_no_duplicate(self):
        c = self.parent()
        def interrupt(*args): raise KeyboardInterrupt()
        with patch.dict(NS, evidence_curl=interrupt), self.assertRaises(KeyboardInterrupt): NS['collect_photo_replay'](c)
        with patch.dict(NS, evidence_curl=lambda *_: self.fail('repeat')), contextlib.redirect_stdout(io.StringIO()):
            r = NS['collect_photo_replay'](c)
        self.assertEqual(r['status'], 'INTERRUPTED_NO_AUTORETRY'); self.assertEqual(r['physical_curl_attempts'], 1)

    def test_wrong_origin_and_missing_values_stop(self):
        c = self.parent()
        for change in ({'relay_origin': 'https://other.example:8443'}, {'OC': ''}, {'Cookie': ''}, {'method': 'POST'}):
            with patch.dict(NS, PHOTO_INPUTS={**FIXTURE_INPUTS, **change}), self.assertRaises(ValueError):
                NS['collect_photo_replay'](c)
        self.assertFalse((c.out / 'photo_sample_replay_r1.json').exists())

    def test_existing_managed_folder_consumer(self):
        c = self.parent()
        with patch.dict(NS, evidence_curl=lambda *_: {'status': 'HTTP_RESPONSE_401'}), contextlib.redirect_stdout(io.StringIO()):
            r = NS['collect_photo_replay'](c)
        class Folder:
            def __init__(self): self.data = {}
            def upload_data(self, n, b): self.data[n] = b
            def get_download_stream(self, n): return io.BytesIO(self.data[n])
        folder = Folder()
        with patch.dict(sys.modules, dataiku=types.SimpleNamespace(Folder=lambda _: folder)), contextlib.redirect_stdout(io.StringIO()):
            c.export_to_dataiku('fixture')
        self.assertTrue(any(k.endswith('/photo_sample_replay_r1.json') for k in folder.data))
        self.assertFalse(r['legal_data_success'])

    def test_notebook_and_txt_same_code(self):
        nb = json.loads((OUT / 'DATAIKU_PHOTO_INPUTS_20261015_R1.ipynb').read_text())
        code = '\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code')
        self.assertTrue(ast.dump(ast.parse(code)) == ast.dump(ast.parse(SOURCE)))
        self.assertTrue(all(not c.get('outputs') for c in nb['cells']))

    def test_full_delivered_txt_real_curl_loopback_and_independent_notebook(self):
        cert, key = self.root / 'cert.pem', self.root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                        '-out', str(cert), '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
        received = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlsplit(self.path)
                received.append((u.path, parse_qs(u.query), self.headers.get('target_url'), self.headers.get('Cookie')))
                body = b'<fixture>ok</fixture>'; self.send_response(200); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            origin = 'https://127.0.0.1:' + str(server.server_port)
            src = SOURCE.replace(REAL_INPUTS['OC'], 'fixture-oc').replace(REAL_INPUTS['Cookie'], FIXTURE_COOKIE)
            src = src.replace(REAL_INPUTS['relay_origin'], origin).replace('PHOTO_HOST = "45.101.64.86"', 'PHOTO_HOST = "127.0.0.1"').replace('PHOTO_PORT = 8443', 'PHOTO_PORT = ' + str(server.server_port))
            env = {'REQUESTS_CA_BUNDLE': str(cert), 'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'}
            import os
            cwd = Path.cwd()
            try:
                os.chdir(self.root)
                with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                    ns = {}; exec(compile(src, 'exact-txt-local-fixture', 'exec'), ns)
                    exec(compile(src, 'exact-txt-repeat', 'exec'), ns)
            finally: os.chdir(cwd)
            r = ns['_photo_replay_result']
            self.assertEqual(r['curl']['status'], 'HTTP_RESPONSE_200')
            self.assertTrue(r['curl']['http_request_sent_observed']); self.assertEqual(len(received), 1)
            self.assertEqual(received[0][0], '/law/making')
            self.assertEqual(received[0][1], {k: [v] for k, v in {'OC': 'fixture-oc', **REAL_INPUTS['params']}.items()})
            self.assertEqual(received[0][2], REAL_INPUTS['target_url']); self.assertEqual(received[0][3], FIXTURE_COOKIE)
            self.assertFalse(r['uses_existing_check_folder'])
        finally: server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (HERE / 'TEST_TRANSCRIPT.txt').write_text(stream.getvalue()); print(stream.getvalue())
    report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'cell_sha256': hashlib.sha256(SOURCE.encode()).hexdigest(),
              'exact_txt_loopback_curl_verified': result.wasSuccessful(), 'ipynb_ast_equals_txt': result.wasSuccessful(),
              'managed_folder_existing_consumer_verified': result.wasSuccessful(), 'samsung_internal_calls': 0,
              'real_photo_credentials_used_in_network_tests': False, 'photo_transcription_byte_identity_verified': False,
              'photo_credentials_current_validity': 'UNKNOWN', 'field_firewall_status': 'UNCONFIRMED'}
    (HERE / 'VALIDATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
