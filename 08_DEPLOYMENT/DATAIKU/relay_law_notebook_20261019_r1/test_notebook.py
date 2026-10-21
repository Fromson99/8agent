import contextlib
import gzip
import io
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "DATAIKU_RELAY_LAW_20261019_R1.ipynb"
LAW = ('<법령><기본정보><법령ID>010513</법령ID>'
       '<법령명_한글>자본시장과 금융투자업에 관한 법률</법령명_한글>'
       '<시행일자>20261002</시행일자></기본정보>'
       '<조문><조문단위><조문내용>제1조 목적</조문내용></조문단위></조문></법령>').encode()
SECRET = "SYNTHETIC_LAW_OC_123"
COOKIE = "JSESSIONID=SYNTHETIC_COOKIE_456"


class Response:
    def __init__(self, status=200, body=LAW):
        self.status_code, self.body = status, body
        self.headers = {"Content-Type": "application/xml"}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, size): yield self.body


class Transport:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []
    def mount(self, *args): pass
    def close(self): pass
    def merge_environment_settings(self, *args):
        return {"proxies": {}}
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = next(self.values)
        if isinstance(result, BaseException): raise result
        return result


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cells = [''.join(c['source']) for c in json.loads(NOTEBOOK.read_text())['cells']
                      if c['cell_type'] == 'code']
        self.ns = {"__name__": "notebook_validation"}
        exec(self.cells[0], self.ns)
        self.ns['CONFIG']['output_root'] = self.temp.name
        exec(self.cells[1], self.ns)
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def fake(self, responses):
        transport = Transport(responses)
        patcher = patch.object(self.ns['requests'], 'Session', return_value=transport)
        patcher.start(); self.addCleanup(patcher.stop)
        pause = patch.object(self.ns['time'], 'sleep')
        pause.start(); self.addCleanup(pause.stop)
        return transport

    def steps(self):
        exec(self.cells[2], self.ns)
        with patch('getpass.getpass', side_effect=[SECRET, COOKIE]):
            exec(self.cells[3], self.ns)
        exec(self.cells[4], self.ns)
        return self.ns['run']

    def test_exact_notebook_success_and_two_requests(self):
        t = self.fake([Response(405), Response()]); run = self.steps()
        self.assertEqual([c[0][0] for c in t.calls], ['HEAD', 'GET'])
        self.assertEqual(t.calls[0][0][1], t.calls[1][0][1])
        self.assertNotIn('headers', t.calls[0][1]); self.assertNotIn('params', t.calls[0][1])
        get = t.calls[1][1]
        self.assertEqual(get['headers']['target_url'], 'http://www.law.go.kr/DRF/lawService.do?target=law')
        self.assertEqual(get['params'], {'ID': '010513', 'type': 'XML', 'OC': SECRET})
        self.assertEqual(get['headers']['Cookie'], COOKIE)
        self.assertTrue(get['verify']); self.assertFalse(get['allow_redirects'])
        self.assertEqual(run.state['law']['status'], 'BODY_OK')
        self.assertEqual(json.loads(run.path.read_text())['attempts'], 2)

    def test_connect_timeout_blocks_law_without_prompt(self):
        t = self.fake([self.ns['requests'].exceptions.ConnectTimeout('secret URL')])
        exec(self.cells[2], self.ns)
        with patch('getpass.getpass', side_effect=AssertionError('must not prompt')):
            exec(self.cells[3], self.ns)
        exec(self.cells[4], self.ns)
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(self.ns['run'].state['relay']['status'], 'CONNECT_TIMEOUT')
        self.assertIsNone(self.ns['run'].state['law'])

    def test_tls_and_connection_failures(self):
        for error, status in [(self.ns['requests'].exceptions.SSLError('bad cert'), 'TLS_ERROR'),
                              (self.ns['requests'].exceptions.ConnectionError('route'), 'CONNECTION_ERROR')]:
            t = self.fake([error]); self.ns['CONFIG']['run_id'] = status
            run = self.steps(); self.assertEqual(run.state['relay']['status'], status)
            self.assertIsNone(run.state['law']); self.assertEqual(len(t.calls), 1)

    def test_head_401_still_allows_authenticated_get(self):
        t = self.fake([Response(401), Response()]); run = self.steps()
        self.assertEqual(run.state['law']['status'], 'BODY_OK'); self.assertEqual(len(t.calls), 2)

    def test_html_200_not_law_success(self):
        self.fake([Response(404), Response(200, b'<html>login</html>')]); run = self.steps()
        self.assertEqual(run.state['law']['status'], 'REJECTED')
        self.assertNotIn('확인 완료:', self.output.getvalue())

    def test_wrong_law_id_rejected(self):
        self.fake([Response(), Response(body=LAW.replace(b'010513', b'999999'))]); run = self.steps()
        self.assertEqual(run.state['law']['reason'], 'BODY_ID_MISMATCH')

    def test_get_timeout_preserves_relay_success(self):
        t = self.fake([Response(), self.ns['requests'].exceptions.ReadTimeout('secret')]); run = self.steps()
        self.assertEqual(run.state['relay']['status'], 'HTTP_RESPONSE_RECEIVED')
        self.assertEqual(run.state['law']['status'], 'TIMEOUT'); self.assertEqual(len(t.calls), 2)

    def test_duplicate_and_restart_no_calls(self):
        t = self.fake([Response(), Response()]); run = self.steps(); original = run.path.read_bytes()
        self.steps(); self.assertEqual(len(t.calls), 2)
        fresh = self.ns['NotebookRun'](self.ns['CONFIG'])
        fresh.preflight(); fresh.call_law(SECRET, COOKIE)
        self.assertEqual(fresh.path.read_bytes(), original); self.assertEqual(len(t.calls), 2)

    def test_interrupted_preflight_does_not_retry(self):
        t = self.fake([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt): exec(self.cells[2], self.ns)
        run = self.ns['NotebookRun'](self.ns['CONFIG']); run.preflight()
        self.assertFalse(run.law_ready()); self.assertEqual(len(t.calls), 1)
        self.assertEqual(run.state['relay']['status'], 'INTERRUPTED')

    def test_get_interrupt_preserves_receipt_and_attempt(self):
        t = self.fake([Response(), KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt): self.steps()
        run = self.ns['NotebookRun'](self.ns['CONFIG'])
        row = run.call_law(SECRET, COOKIE)
        self.assertEqual(row['status'], 'INTERRUPTED'); self.assertEqual(len(t.calls), 2)
        self.assertTrue(Path(row['receipt_folder']).is_dir())

    def test_deadline_restored_on_restart(self):
        t = self.fake([Response()]); exec(self.cells[2], self.ns); run = self.ns['run']
        with run.transaction():
            run.state['deadline'] = time.time() - 1; run.save()
        resumed = self.ns['NotebookRun'](self.ns['CONFIG'])
        self.assertFalse(resumed.law_ready())
        row = resumed.call_law(SECRET)
        self.assertEqual(row['status'], 'BUDGET_EXHAUSTED'); self.assertEqual(len(t.calls), 1)

    def test_configuration_change_rejected_without_overwrite(self):
        self.fake([Response()]); exec(self.cells[2], self.ns); run = self.ns['run']; before = run.path.read_bytes()
        cfg = dict(self.ns['CONFIG'], law_id='999999')
        with self.assertRaises(ValueError): self.ns['NotebookRun'](cfg)
        self.assertEqual(run.path.read_bytes(), before)
        with self.assertRaises(ValueError): run.ensure_config(cfg)

    def test_concurrent_same_run_blocked(self):
        run = self.ns['NotebookRun'](self.ns['CONFIG'])
        with run.transaction():
            with self.assertRaises(RuntimeError): self.ns['NotebookRun'](self.ns['CONFIG'])

    def test_secret_redaction_and_saved_body(self):
        raw = LAW + ('<!--' + SECRET + ' ' + COOKIE + '-->').encode()
        self.fake([Response(), Response(body=raw)]); run = self.steps()
        self.assertNotIn(SECRET, self.output.getvalue()); self.assertNotIn(COOKIE, self.output.getvalue())
        for p in run.out.rglob('*'):
            if p.is_file():
                blob = gzip.decompress(p.read_bytes()) if p.suffix == '.gz' else p.read_bytes()
                self.assertNotIn(SECRET.encode(), blob); self.assertNotIn(COOKIE.encode(), blob)

    def test_real_local_tls_same_notebook_cells(self):
        folder = Path(self.temp.name)
        cert, key = folder/'cert.pem', folder/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost', '-addext', 'basicConstraints=critical,CA:TRUE'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_HEAD(self):
                seen.append(('HEAD', self.path, dict(self.headers)))
                self.send_response(405); self.send_header('Content-Length', '0'); self.end_headers()
            def do_GET(self):
                seen.append(('GET', self.path, dict(self.headers)))
                self.send_response(200); self.send_header('Content-Type', 'application/xml')
                self.send_header('Content-Length', str(len(LAW))); self.end_headers(); self.wfile.write(LAW)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert, key)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            self.ns['CONFIG'].update(relay_origin='https://localhost:' + str(server.server_port), ca_bundle=str(cert))
            with patch.dict('os.environ', {'NO_PROXY': 'localhost,127.0.0.1', 'no_proxy': 'localhost,127.0.0.1'}):
                run = self.steps()
            self.assertEqual([r[0] for r in seen], ['HEAD', 'GET'])
            self.assertEqual(seen[0][1], '/law/DRF')
            self.assertNotIn('Cookie', seen[0][2]); self.assertNotIn('target_url', seen[0][2])
            query = parse_qs(urlsplit(seen[1][1]).query)
            self.assertEqual(query['OC'], [SECRET]); self.assertEqual(query['ID'], ['010513'])
            self.assertEqual(seen[1][2]['target_url'], 'http://www.law.go.kr/DRF/lawService.do?target=law')
            self.assertEqual(run.state['law']['status'], 'BODY_OK')
            self.assertEqual(json.loads(run.path.read_text())['attempts'], 2)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__': unittest.main(verbosity=2)
