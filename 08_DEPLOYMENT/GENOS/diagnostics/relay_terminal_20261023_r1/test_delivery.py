import gzip
import http.server
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'GENOS_RELAY_CHECK_20261023_R1.txt'
BODY = ('<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령ID>010513</법령ID>'
        '<법령명_한글>자본시장과 금융투자업에 관한 법률</법령명_한글></기본정보>'
        '<조문><조문단위><조문내용>제1조 합성 검사 조문</조문내용></조문단위></조문></법령>').encode()


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='genos-relay-test-')
        cls.root = Path(cls.temp.name)
        cls.cert, cls.key = cls.root / 'ca.pem', cls.root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(cls.key), '-out', str(cls.cert), '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.records = []
        cls.payload, cls.status, cls.head_status, cls.delay = BODY, 200, 405, 0
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, method):
                cls.records.append((method, self.path, dict(self.headers)))
                if method == 'HEAD' and cls.delay:
                    time.sleep(cls.delay)
                self.send_response(cls.head_status if method == 'HEAD' else cls.status)
                self.send_header('Content-Type', 'application/xml; charset=utf-8')
                self.send_header('Content-Length', str(0 if method == 'HEAD' else len(cls.payload)))
                if cls.status == 302:
                    self.send_header('Location', 'https://127.0.0.1:9/never-follow')
                self.end_headers()
                if method == 'GET':
                    try:
                        self.wfile.write(cls.payload)
                    except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                        pass

            def do_HEAD(self):
                self.send('HEAD')

            def do_GET(self):
                self.send('GET')
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, cls.key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = 'https://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        type(self).records.clear()
        type(self).payload, type(self).status, type(self).head_status, type(self).delay = BODY, 200, 405, 0
        self.output = self.root / self._testMethodName

    def command(self, *extra):
        return [sys.executable, str(SCRIPT), '--relay', self.origin, '--ca', str(self.cert),
                '--output', str(self.output), *extra]

    def invoke(self, *extra, expected=0):
        env = dict(os.environ, LAW_OC='fake-oc-fixture', RELAY_COOKIE='JSESSIONID=fake-session-fixture; second=fake-other-fixture',
                   HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9')
        result = subprocess.run(self.command(*extra), env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        for secret in ('fake-oc-fixture', 'fake-session-fixture', 'fake-other-fixture'):
            self.assertNotIn(secret, result.stdout + result.stderr)
        return result

    def state(self, run_id='relay-check-01'):
        return json.loads((self.output / run_id / 'result.json').read_text())

    def test_actual_txt_network_then_body_and_duplicate(self):
        self.invoke()
        self.assertEqual(['HEAD'], [r[0] for r in self.records])
        self.assertEqual('/law/DRF', self.records[0][1])
        self.assertNotIn('target_url', self.records[0][2])
        self.assertNotIn('Cookie', self.records[0][2])
        self.invoke('--body')
        self.assertEqual(['HEAD', 'GET'], [r[0] for r in self.records])
        request = self.records[1]
        self.assertEqual('http://www.law.go.kr/DRF/lawService.do?target=law', request[2]['target_url'])
        self.assertEqual({'OC': ['fake-oc-fixture'], 'ID': ['010513'], 'type': ['XML']}, parse_qs(urlsplit(request[1]).query))
        self.assertEqual('JSESSIONID=fake-session-fixture; second=fake-other-fixture', request[2]['Cookie'])
        state = self.state()
        self.assertEqual('BODY_OK', state['stages']['law']['status'])
        self.assertEqual(3, state['attempts'])
        self.assertEqual(BODY, gzip.decompress((self.output/'relay-check-01/law_response.xml.gz').read_bytes()))
        self.assertEqual(0o600, (self.output/'relay-check-01/result.json').stat().st_mode & 0o777)
        self.invoke('--body')
        self.assertEqual(2, len(self.records))

    def test_get_http_errors_and_redirect_do_not_retry(self):
        for status in (401, 403, 429, 302):
            with self.subTest(status=status):
                type(self).status = status
                self.invoke('--body', '--run-id', 'http-'+str(status), expected=2)
                self.assertEqual('HTTP_'+str(status), self.state('http-'+str(status))['stages']['law']['status'])
        self.assertEqual(8, len(self.records))

    def test_html_error_wrong_id_and_entity_are_rejected(self):
        for index, payload in enumerate((b'<html>login</html>', BODY.replace(b'010513', b'999999'),
                                        b'<!DOCTYPE x [<!ENTITY y "bad">]><x>&y;</x>', BODY[:80])):
            with self.subTest(index=index):
                type(self).payload = payload
                self.invoke('--body', '--run-id', 'bad-'+str(index), expected=2)
                self.assertEqual('RESPONSE_REJECTED', self.state('bad-'+str(index))['stages']['law']['status'])

    def test_failed_get_is_not_reissued(self):
        type(self).status = 403
        self.invoke('--body', expected=2)
        type(self).status = 200
        self.invoke('--body', expected=2)
        self.assertEqual(2, len(self.records))

    def test_secret_redaction_in_saved_error_response(self):
        type(self).status = 403
        type(self).payload = b'<error>fake-oc-fixture fake-session-fixture fake-other-fixture</error>'
        self.invoke('--body', expected=2)
        folder = self.output/'relay-check-01'
        contents = (folder/'result.json').read_bytes()+(folder/'events.jsonl').read_bytes()+gzip.decompress((folder/'law_response.xml.gz').read_bytes())
        for secret in (b'fake-oc-fixture', b'fake-session-fixture', b'fake-other-fixture'):
            self.assertNotIn(secret, contents)
        self.assertTrue(self.state()['stages']['law']['credential_redacted'])

    def test_binding_change_is_blocked(self):
        self.invoke()
        result = self.invoke('--law-origin', 'https://www.law.go.kr', expected=2)
        self.assertIn('BINDING_CHANGED', result.stderr)
        self.assertEqual(1, len(self.records))

    def test_expired_budget_stops_new_body(self):
        self.invoke()
        state = self.state()
        state['deadline'] = time.time()-1
        (self.output/'relay-check-01/result.json').write_text(json.dumps(state))
        self.invoke('--body', expected=2)
        self.assertEqual(1, len(self.records))

    def test_unknown_inflight_is_not_reissued(self):
        self.invoke()
        state = self.state()
        state['stages']['law'] = {'status': 'IN_FLIGHT'}
        state['attempts'] = 3
        (self.output/'relay-check-01/result.json').write_text(json.dumps(state))
        self.invoke('--body', expected=2)
        self.assertEqual(1, len(self.records))

    def test_untrusted_tls_blocks_body(self):
        args = self.command('--body')
        index = args.index('--ca')
        del args[index:index+2]
        result = subprocess.run(args, text=True, capture_output=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertEqual('TLS_ERROR', self.state()['stages']['https']['status'])
        self.assertEqual([], self.records)

    def test_closed_tcp_port_preserves_failure(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.invoke('--relay', 'https://127.0.0.1:'+str(port), expected=2)
        self.assertEqual('CONNECTION_ERROR', self.state()['stages']['tcp']['status'])
        self.assertNotIn('https', self.state()['stages'])

    def test_concurrent_run_and_user_interrupt(self):
        type(self).delay = 2
        proc = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time()+5
            while time.time()<deadline:
                if self.records:
                    break
                time.sleep(.02)
            self.assertTrue(self.records)
            second = self.invoke(expected=2)
            self.assertIn('RUN_BUSY', second.stderr)
            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(130, proc.returncode, stdout+stderr)
            self.assertEqual('INTERRUPTED', self.state()['stages']['https']['status'])
            self.invoke(expected=2)
            self.assertEqual(1, len(self.records))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_stage_hard_deadline_and_size_limit(self):
        loader = importlib.machinery.SourceFileLoader('relay_final', str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        start = time.monotonic()
        with self.assertRaises(module.StageDeadline):
            with module.bounded(.02):
                time.sleep(2)
        self.assertLess(time.monotonic()-start, 1)
        type(self).payload = b'x'*(module.MAX_BYTES+1)
        self.invoke('--body', expected=2)
        self.assertEqual('RESPONSE_SIZE_LIMIT', self.state()['stages']['law']['reason'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
