import ast
import contextlib
import hashlib
import http.server
import io
import json
from pathlib import Path
import socket
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
SOURCE = (HERE / 'DATAIKU_NETWORK_EVIDENCE_20261015_R1_CELL.txt').read_text()
sys.path.insert(0, str(HERE.parent / 'law_api_20261015_r1'))
from relay_check import RelayCheck
NS = {}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(SOURCE, 'delivered-cell', 'exec'), NS)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def check(self, origin=None, cookie='fixture-cookie', ca=None):
        session = requests.Session(); session.trust_env = False
        return RelayCheck(dict(relay_origin=origin or NS['PHOTO_ORIGIN'], output_root=str(self.root), ca_bundle=ca),
                          'fixture-oc', cookie=cookie, session=session)

    def run_mock(self, c, tcp=None, curl=None):
        tcp = tcp or {'status': 'TCP_TIMEOUT'}
        curl = curl or {'status': 'CURL_CONNECT_PHASE_TIMEOUT'}
        with patch.dict(NS, evidence_tcp=lambda *_: tcp, evidence_curl=lambda *_: curl), contextlib.redirect_stdout(io.StringIO()):
            return NS['collect_network_evidence'](c)

    def test_exact_delivered_cell_no_parent_mutation_duplicate(self):
        c = self.check(); c.calls = 1; c.blocked = True
        before = (c.out / 'summary.json').read_bytes()
        attempts = []
        ns = {'check': c}
        # Load definitions without main, then execute the actual delivered main branch twice.
        split = SOURCE.index('\nif "check" not in globals():')
        exec(compile(SOURCE[:split], 'delivered-definitions', 'exec'), ns)
        ns['evidence_tcp'] = lambda *_: attempts.append('tcp') or {'status': 'TCP_TIMEOUT'}
        ns['evidence_curl'] = lambda *_: attempts.append('curl') or {'status': 'CURL_CONNECT_PHASE_TIMEOUT'}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SOURCE[split:], 'delivered-main', 'exec'), ns)
            exec(compile(SOURCE[split:], 'delivered-main', 'exec'), ns)
        self.assertEqual(attempts, ['tcp', 'curl'])
        self.assertEqual(c.calls, 1); self.assertTrue(c.blocked)
        self.assertEqual((c.out / 'summary.json').read_bytes(), before)
        self.assertFalse(ns['_network_evidence']['firewall_block_confirmed'])

    def test_timeout_never_claims_firewall_confirmed(self):
        r = self.run_mock(self.check())
        self.assertFalse(r['firewall_block_confirmed'])
        self.assertIn('구분 불가', r['interpretation'])
        self.assertEqual(r['application_attempts_started'], 2)

    def test_missing_cookie_disclosed(self):
        c = self.check(cookie='')
        with patch('getpass.getpass', return_value=''):
            r = self.run_mock(c)
        self.assertFalse(r['request']['cookie_present'])
        self.assertTrue(any('Cookie 미입력' in s for s in r['differences_from_photo']))
        self.assertEqual(c.cookie, '')

    def test_proxy_path_skips_direct_tcp_and_redacts(self):
        c = self.check(); c.session.proxies = {'https': 'http://user:secret@proxy.example:8080'}
        r = self.run_mock(c)
        self.assertEqual(r['tcp']['status'], 'SKIPPED_PROXY_ROUTE')
        self.assertEqual(r['application_attempts_started'], 1)
        self.assertEqual(r['proxy_host'], 'proxy.example:8080')
        self.assertNotIn('user:secret', json.dumps(r))

    def test_wrong_environment_no_call(self):
        c = self.check('https://other.example:8443')
        with self.assertRaises(ValueError): self.run_mock(c)
        self.assertFalse((c.out / 'network_evidence_r1.json').exists())

    def test_missing_curl_no_call(self):
        with patch('shutil.which', return_value=None), self.assertRaises(RuntimeError):
            self.run_mock(self.check())

    def test_control_character_injection_rejected(self):
        for value in ('a\nb', 'a\rb', 'a\x00b', 'a\tb'):
            with self.assertRaises(ValueError): NS['evidence_config_value'](value)

    def test_interruption_preserves_attempt_and_no_repeat(self):
        c = self.check()
        def interrupt(*args): raise KeyboardInterrupt()
        with patch.dict(NS, evidence_tcp=interrupt), self.assertRaises(KeyboardInterrupt):
            NS['collect_network_evidence'](c)
        with patch.dict(NS, evidence_tcp=lambda *_: self.fail('duplicate network call')), contextlib.redirect_stdout(io.StringIO()):
            r = NS['collect_network_evidence'](c)
        self.assertEqual(r['status'], 'INTERRUPTED_NO_AUTORETRY')
        self.assertEqual(r['application_attempts_started'], 1)

    def test_tcp_timeout_refusal_and_source_socket(self):
        for exc, status in [(socket.timeout('timed out'), 'TCP_TIMEOUT'),
                            (ConnectionRefusedError(111, 'refused'), 'TCP_REFUSED'),
                            (OSError(101, 'unreachable'), 'NETWORK_UNREACHABLE')]:
            with patch('socket.socket') as factory:
                s = factory.return_value; s.connect.side_effect = exc; s.getsockname.return_value = ('10.0.0.5', 45678)
                r = NS['evidence_tcp']('192.0.2.1', 8443)
            self.assertEqual(r['status'], status); self.assertEqual(r['local_port'], 45678)
            s.close.assert_called_once(); s.connect.assert_called_once()

    def test_curl_stage_and_secret_filter(self):
        for code, tcp, tls, http, status in [
            (28, 0, 0, '000', 'CURL_CONNECT_PHASE_TIMEOUT'),
            (28, .01, 0, '000', 'CURL_TCP_CONNECTED_TLS_OR_PROXY_WAIT_TIMEOUT'),
            (28, .01, .02, '000', 'CURL_AFTER_TLS_TIMEOUT'),
            (60, .01, 0, '000', 'CURL_TLS_ERROR'),
            (0, .01, .02, '403', 'HTTP_RESPONSE_403')]:
            stdout = f'http_code={http}\ntime_connect={tcp}\ntime_appconnect={tls}\n'.encode()
            stderr = b'> GET /?OC=fixture-oc HTTP/1.1\n> Cookie: fixture-cookie\n< Set-Cookie: new-secret\ncurl: timeout OC=fixture-oc\n* Connected to 127.0.0.1\n'
            with patch('subprocess.run', return_value=subprocess.CompletedProcess([], code, stdout, stderr)) as run:
                r = NS['evidence_curl']('curl', 'https://192.0.2.1:8443', 'fixture-oc', 'fixture-cookie', '', True)
                args = run.call_args.args[0]
                self.assertNotIn('fixture-oc', str(args)); self.assertNotIn('fixture-cookie', str(args))
                self.assertEqual(args[1], '--disable'); self.assertIn('--max-redirs', args)
            self.assertEqual(r['status'], status)
            self.assertNotIn('fixture-oc', json.dumps(r)); self.assertNotIn('fixture-cookie', json.dumps(r))
            self.assertNotIn('new-secret', json.dumps(r)); self.assertFalse(r['legal_data_success'])

    def test_managed_folder_existing_consumer(self):
        c = self.check(); self.run_mock(c)
        class Folder:
            def __init__(self): self.data = {}
            def upload_data(self, name, data): self.data[name] = data
            def get_download_stream(self, name): return io.BytesIO(self.data[name])
        folder = Folder()
        with patch.dict(sys.modules, dataiku=types.SimpleNamespace(Folder=lambda _: folder)), contextlib.redirect_stdout(io.StringIO()):
            c.export_to_dataiku('fixture')
        saved = next(v for k, v in folder.data.items() if k.endswith('/network_evidence_r1.json'))
        self.assertEqual(saved, (c.out / 'network_evidence_r1.json').read_bytes())

    def test_real_local_tls_photo_query_and_redirect_bound(self):
        cert, key = self.root / 'cert.pem', self.root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
        received = []; response_code = [200]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlsplit(self.path)
                received.append({'path': u.path, 'params': parse_qs(u.query), 'target': self.headers.get('target_url'),
                                 'cookie': self.headers.get('Cookie')})
                body = b'<fixture>network only</fixture>'
                self.send_response(response_code[0]); self.send_header('Content-Length', str(len(body)))
                if response_code[0] == 302: self.send_header('Location', '/should-not-follow')
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            origin = 'https://127.0.0.1:' + str(server.server_port)
            # Entire delivered cell with only the fixed destination replaced by local fixture.
            c = self.check(origin, ca=str(cert)); ns = {'check': c}
            exact_fixture_source = SOURCE.replace('PHOTO_ORIGIN = "https://45.101.64.86:8443"', 'PHOTO_ORIGIN = ' + repr(origin))
            with contextlib.redirect_stdout(io.StringIO()): exec(compile(exact_fixture_source, 'delivered-cell-loopback', 'exec'), ns)
            r = ns['_network_evidence']
            self.assertEqual(r['tcp']['status'], 'TCP_CONNECTED')
            self.assertEqual(r['curl']['status'], 'HTTP_RESPONSE_200')
            self.assertTrue(r['curl']['metrics_complete']); self.assertTrue(r['curl']['http_request_sent_observed'])
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]['path'], '/law/making')
            self.assertEqual(received[0]['target'], NS['PHOTO_TARGET'])
            self.assertEqual(received[0]['cookie'], 'fixture-cookie')
            self.assertEqual(received[0]['params'], {k: [v] for k, v in {'OC': 'fixture-oc', **NS['PHOTO_PARAMS']}.items()})
            response_code[0] = 302
            redirect = NS['evidence_curl']('curl', origin, 'fixture-oc', 'fixture-cookie', '', str(cert))
            self.assertEqual(redirect['status'], 'HTTP_RESPONSE_302'); self.assertEqual(redirect['exit_code'], 47)
            self.assertEqual(len(received), 2)
            self.assertFalse(r['firewall_block_confirmed'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_python39_syntax(self):
        ast.parse(SOURCE, feature_version=(3, 9))


if __name__ == '__main__':
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (HERE / 'TEST_TRANSCRIPT.txt').write_text(stream.getvalue())
    print(stream.getvalue())
    report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'delivered_cell_sha256': hashlib.sha256(SOURCE.encode()).hexdigest(),
              'local_https_curl_photo_request_verified': result.wasSuccessful(),
              'managed_folder_existing_consumer_verified': result.wasSuccessful(),
              'samsung_internal_calls': 0, 'public_law_calls': 0, 'field_firewall_status': 'UNCONFIRMED',
              'scope': 'Local loopback HTTPS and synthetic failure tests only; no corporate network access'}
    (HERE / 'VALIDATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
