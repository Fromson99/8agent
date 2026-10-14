"""Actual local HTTP/TLS IO for the GENOS standard-library model transport."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import ssl
import subprocess
import threading
import time

import pytest

from semantic_runtime import genos, stdlib_http
from semantic_runtime.legal_agent.errors import TransportError
from semantic_runtime.legal_agent.transport import GenosTransport


MODEL = 'local-synthetic-model'


@pytest.fixture(scope='module')
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp('genos-urllib-ca')
    config = root / 'extensions.txt'
    config.write_text('subjectAltName=IP:127.0.0.1\nbasicConstraints=CA:FALSE\n'
                      'keyUsage=critical,digitalSignature,keyEncipherment\n'
                      'extendedKeyUsage=serverAuth\n')
    commands = [
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
         '-subj', '/CN=Synthetic local CA', '-keyout', str(root/'ca.key'), '-out', str(root/'ca.pem'),
         '-addext', 'basicConstraints=critical,CA:TRUE',
         '-addext', 'keyUsage=critical,keyCertSign,cRLSign'],
        ['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=127.0.0.1',
         '-keyout', str(root/'server.key'), '-out', str(root/'server.csr')],
        ['openssl', 'x509', '-req', '-days', '1', '-in', str(root/'server.csr'),
         '-CA', str(root/'ca.pem'), '-CAkey', str(root/'ca.key'), '-CAcreateserial',
         '-extfile', str(config), '-out', str(root/'server.pem')],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True)
    (root/'chain.pem').write_bytes((root/'server.pem').read_bytes() + (root/'ca.pem').read_bytes())
    return root


@pytest.fixture(autouse=True)
def local_network_only(monkeypatch):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy',
                 'SSL_CERT_FILE', 'SSL_CERT_DIR'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')


@contextmanager
def server(certificates=None, *, mode='json'):
    calls, release = [], threading.Event()
    state = {'mode': mode, 'calls': calls, 'release': release}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def record(self):
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length)) if length else None
            calls.append({'method': self.command, 'path': self.path, 'body': body,
                          'authorization': self.headers.get('Authorization')})
            return body

        def reply(self, body, status=200, headers=None):
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

        def do_GET(self):
            self.record()
            self.reply({'data': [{'id': MODEL}]})

        def do_POST(self):
            self.record()
            mode = state['mode']
            try:
                if mode == 'redirect':
                    return self.reply({}, 302, {'Location': '/must-not-be-called'})
                if mode == 'error':
                    return self.reply({'error': {'message': 'synthetic upstream rejection'}},
                                      429, {'Retry-After': '7'})
                if mode == 'json':
                    return self.reply({'model': MODEL, 'choices': [
                        {'message': {'content': '{}'}, 'finish_reason': 'stop'}]})
                if mode == 'slow-headers':
                    time.sleep(.4)
                    return self.reply({})
                if mode == 'slow-body':
                    self.send_response(200)
                    self.send_header('Content-Length', '1000')
                    self.end_headers()
                    for _ in range(100):
                        self.wfile.write(b' ')
                        self.wfile.flush()
                        time.sleep(.015)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Connection', 'close')
                self.end_headers()

                def frame(text=None, finish=None):
                    data = {'model': MODEL, 'choices': [{'index': 0,
                        'delta': {'content': text} if text is not None else {}, 'finish_reason': finish}]}
                    self.wfile.write(('data: ' + json.dumps(data, ensure_ascii=False) + '\n\n').encode())
                    self.wfile.flush()

                frame('첫 답변')
                if mode == 'stream':
                    if not release.wait(1):
                        return
                    frame(' 마지막')
                    frame(finish='stop')
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                elif mode == 'disconnect':
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                else:
                    for _ in range(100):
                        frame(' 조각')
                        time.sleep(.015)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    serving = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    serving.daemon_threads = True
    if certificates:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificates/'chain.pem', certificates/'server.key')
        serving.socket = context.wrap_socket(serving.socket, server_side=True)
    thread = threading.Thread(target=lambda: serving.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    scheme = 'https' if certificates else 'http'
    target = genos.endpoint(f'{scheme}://127.0.0.1:{serving.server_port}', token='synthetic-key',
                            api_prefix='none', max_retries=1, connect_timeout=.5, read_timeout=1)
    binding = {'provider': 'genos', 'trust_zone': 'internal', 'adapter_version': 'genos-single-send-v1',
               'model': MODEL, 'endpoint_identity': hashlib.sha256(target.root.encode()).hexdigest()}
    try:
        yield target, GenosTransport(target, binding), state
    finally:
        release.set()
        serving.shutdown()
        serving.server_close()
        thread.join(1)


def test_https_os_ca_environment_is_used_for_discovery_validation_and_json(certificates, monkeypatch):
    monkeypatch.setenv('SSL_CERT_FILE', str(certificates/'ca.pem'))
    # Requests uses a different variable. Its value must not select our CA.
    monkeypatch.setenv('REQUESTS_CA_BUNDLE', '/missing/unused-requests-ca.pem')
    with server(certificates) as (target, transport, state):
        assert genos.advertised_model(target) == MODEL
        assert transport.validate_model()['verified']
        result = transport.send_once(body={'model': MODEL}, ticket={'remaining_seconds': 1})
        assert result['body_json']['model'] == MODEL
        assert len(state['calls']) == 3
        assert all(row['authorization'] == 'Bearer synthetic-key' for row in state['calls'])


def test_untrusted_https_certificate_is_rejected_before_http(certificates):
    with server(certificates) as (target, transport, state):
        with pytest.raises(genos.ServingError) as failure:
            genos.request_json(target, '/models')
        assert isinstance(failure.value.__cause__, __import__('urllib.error').error.URLError)
        assert isinstance(failure.value.__cause__.reason, ssl.SSLCertVerificationError)
        with pytest.raises(TransportError, match='connection failed'):
            transport.validate_model()
        assert not state['calls']


def test_trusted_ca_still_checks_hostname(certificates, monkeypatch):
    monkeypatch.setenv('SSL_CERT_FILE', str(certificates/'ca.pem'))
    with server(certificates) as (target, _, state):
        target = genos.endpoint(target.root.replace('127.0.0.1', 'localhost'), api_prefix='none',
                                max_retries=1)
        with pytest.raises(genos.ServingError) as failure:
            genos.request_json(target, '/models')
        assert isinstance(failure.value.__cause__.reason, ssl.SSLCertVerificationError)
        assert not state['calls']


def test_https_answer_stream_is_incremental_and_sent_once(certificates, monkeypatch):
    monkeypatch.setenv('SSL_CERT_FILE', str(certificates/'ca.pem'))
    with server(certificates, mode='stream') as (_, transport, state):
        tokens = []
        def content(text):
            tokens.append(text)
            state['release'].set()
        result = transport.send_stream_once(body={'model': MODEL, 'stream': True},
            ticket={'remaining_seconds': 2}, on_content=content)
        assert tokens == ['첫 답변', ' 마지막']
        assert result['body_json']['choices'][0]['message']['content'] == ''.join(tokens)
        assert len(state['calls']) == 1 and state['calls'][0]['body']['stream']


def test_buffered_json_does_not_resend_stream_request():
    with server() as (_, transport, state):
        result = transport.send_stream_once(body={'stream': True},
            ticket={'remaining_seconds': 1}, on_content=lambda value: pytest.fail('buffered response'))
        assert result['body_json']['model'] == MODEL and len(state['calls']) == 1


@pytest.mark.parametrize('stream', [False, True])
def test_redirect_cannot_forward_authorization_or_resend(stream):
    with server(mode='redirect') as (_, transport, state):
        with pytest.raises(TransportError) as failure:
            if stream:
                transport.send_stream_once(body={'stream': True},
                    ticket={'remaining_seconds': 1}, on_content=lambda value: None)
            else:
                transport.send_once(body={}, ticket={'remaining_seconds': 1})
        assert failure.value.response['status_code'] == 302
        assert len(state['calls']) == 1 and state['calls'][0]['path'] == '/chat/completions'


@pytest.mark.parametrize('stream', [False, True])
def test_error_body_retry_after_and_single_send_are_preserved(stream):
    with server(mode='error') as (_, transport, state):
        with pytest.raises(TransportError) as failure:
            if stream:
                transport.send_stream_once(body={'stream': True},
                    ticket={'remaining_seconds': 1}, on_content=lambda value: None)
            else:
                transport.send_once(body={}, ticket={'remaining_seconds': 1})
        assert failure.value.response['status_code'] == 429
        assert failure.value.response['retry_after'] == '7'
        assert failure.value.response['body_json']['error']['message'] == 'synthetic upstream rejection'
        assert failure.value.retryable and len(state['calls']) == 1


@pytest.mark.parametrize('mode', ['slow-headers', 'slow-body', 'drip-stream'])
def test_total_deadline_interrupts_headers_body_and_active_stream_without_late_output(mode):
    with server(mode=mode) as (_, transport, state):
        tokens, started = [], time.monotonic()
        with pytest.raises(TransportError, match='timed out') as failure:
            if mode == 'drip-stream':
                transport.send_stream_once(body={'stream': True},
                    ticket={'remaining_seconds': .12}, on_content=tokens.append)
            else:
                transport.send_once(body={}, ticket={'remaining_seconds': .12})
        assert time.monotonic() - started < .7
        assert failure.value.unknown and len(state['calls']) == 1
        before = list(tokens)
        time.sleep(.07)
        assert tokens == before


def test_delayed_connect_cannot_send_after_total_deadline(monkeypatch):
    connect = stdlib_http._HTTPConnection.connect
    entered = threading.Event()
    def delayed(self):
        entered.set()
        time.sleep(.15)
        connect(self)
    monkeypatch.setattr(stdlib_http._HTTPConnection, 'connect', delayed)
    with server() as (_, transport, state):
        with pytest.raises(TransportError, match='timed out'):
            transport.send_once(body={}, ticket={'remaining_seconds': .06})
        assert entered.is_set()
        time.sleep(.17)
        assert not state['calls']


def test_incomplete_model_stream_is_not_completed_or_replayed():
    with server(mode='disconnect') as (_, transport, state):
        with pytest.raises(TransportError) as failure:
            transport.send_stream_once(body={'stream': True},
                ticket={'remaining_seconds': 1}, on_content=lambda value: None)
        assert failure.value.unknown and len(state['calls']) == 1
        assert failure.value.response['stream_complete'] is False
