"""GENOS HTTP using urllib, Python's default CA store, and bounded requests.

No process-global opener or SSL policy is changed. Redirects never resend a
request to another endpoint. A legal-agent deadline also interrupts body reads
and prevents a delayed connection from sending after its caller has timed out.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import contextmanager
from contextvars import copy_context
from dataclasses import dataclass
import functools
import http.client
import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request


REVISION = "genos-urllib-tls-20261008-r1"
NETWORK_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError)


def is_timeout(exc):
    return isinstance(exc, TimeoutError) or (isinstance(exc, urllib.error.URLError)
                                           and isinstance(exc.reason, TimeoutError))


@dataclass(frozen=True)
class Timeout:
    read: float
    connect: float


class Deadline:
    def __init__(self, seconds=None):
        self.ends = None if seconds is None else time.monotonic() + seconds
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.sockets = []

    def check(self):
        if self.cancelled.is_set() or self.ends is not None and time.monotonic() >= self.ends:
            raise TimeoutError("total HTTP deadline exceeded")

    def limit(self, seconds):
        self.check()
        return seconds if self.ends is None else min(seconds, max(.000001, self.ends - time.monotonic()))

    def register(self, sock):
        with self.lock:
            self.sockets.append(sock)
            cancelled = self.cancelled.is_set()
        if cancelled:
            self._close(sock)
            self.check()

    @staticmethod
    def _close(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            sockets, self.sockets = self.sockets, []
        for sock in sockets:
            self._close(sock)


def run_with_deadline(seconds, operation):
    """One worker, one send, bounded caller wait including DNS/header/body IO."""
    if seconds <= 0:
        raise TimeoutError("total HTTP deadline exceeded")
    deadline, future, context = Deadline(seconds), Future(), copy_context()

    def work():
        try:
            future.set_result(context.run(operation, deadline))
        except BaseException as exc:
            future.set_exception(exc)

    worker = threading.Thread(target=work, name="genos-urllib-request", daemon=True)
    worker.start()
    try:
        return future.result(timeout=deadline.limit(seconds))
    except FutureTimeout as exc:
        raise TimeoutError("total HTTP deadline exceeded") from exc
    finally:
        deadline.cancel()


class _Connection:
    def __init__(self, *args, limits, deadline, **kwargs):
        self.limits, self.deadline = limits, deadline
        super().__init__(*args, **kwargs)

    def connect(self):
        self.deadline.check()
        super().connect()
        self.deadline.register(self.sock)
        self.sock.settimeout(self.deadline.limit(self.limits.read))

    def send(self, data):
        self.deadline.check()
        if self.sock is not None:
            self.sock.settimeout(self.deadline.limit(self.limits.read))
        return super().send(data)


class _HTTPConnection(_Connection, http.client.HTTPConnection):
    pass


class _HTTPSConnection(_Connection, http.client.HTTPSConnection):
    pass


class _HTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, limits, deadline):
        super().__init__()
        self.connection = functools.partial(_HTTPConnection, limits=limits, deadline=deadline)

    def http_open(self, request):
        return self.do_open(self.connection, request)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, limits, deadline):
        # Python/OpenSSL defaults load OS roots and SSL_CERT_FILE/SSL_CERT_DIR.
        super().__init__(context=ssl.create_default_context())
        self.connection = functools.partial(_HTTPSConnection, limits=limits, deadline=deadline)

    def https_open(self, request):
        return self.do_open(self.connection, request, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class Response:
    def __init__(self, response, limits, deadline):
        self.raw, self.limits, self.deadline = response, limits, deadline
        self.status_code = response.code
        self.headers = {key.lower(): value for key, value in response.headers.items()}

    def _before_read(self):
        self.deadline.check()
        fp = getattr(self.raw, "fp", None)
        sock = getattr(getattr(fp, "raw", None), "_sock", None)
        if sock is not None:
            sock.settimeout(self.deadline.limit(self.limits.read))

    def read(self):
        chunks = []
        reader = getattr(self.raw, "read1", self.raw.read)
        while True:
            self._before_read()
            chunk = reader(65536)
            self.deadline.check()
            if not chunk:
                if getattr(self.raw, "length", 0):
                    raise http.client.IncompleteRead(b"".join(chunks), self.raw.length)
                return b"".join(chunks)
            chunks.append(chunk)

    def iter_lines(self):
        while True:
            self._before_read()
            line = self.raw.readline(16 * 1024 * 1024 + 1)
            self.deadline.check()
            if not line:
                return
            yield line.decode("utf-8", "replace").rstrip("\r\n")


@contextmanager
def open_response(method, url, *, headers, body, timeout, deadline=None):
    owns_deadline = deadline is None
    deadline = deadline or Deadline()
    response = None
    try:
        deadline.check()
        encoded = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        if encoded is not None:
            request.add_header("Content-Type", "application/json")
        opener = urllib.request.build_opener(
            _HTTPHandler(timeout, deadline), _HTTPSHandler(timeout, deadline), _NoRedirect())
        try:
            response = opener.open(request, timeout=deadline.limit(timeout.connect))
        except urllib.error.HTTPError as exc:
            # Preserve the received status/body, including 3xx and Retry-After.
            response = exc
        deadline.check()
        yield Response(response, timeout, deadline)
    finally:
        if response is not None:
            response.close()
        if owns_deadline:
            deadline.cancel()


class BufferedResponse:
    def __init__(self, response):
        self.status_code, self.headers = response.status_code, response.headers
        self.content = response.read()
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)


class Client:
    """Buffered urllib client; the optional injected session contract stays intact."""
    def request(self, method, url, *, headers, json=None, timeout, follow_redirects=False):
        if follow_redirects:
            raise ValueError("GENOS transport does not follow redirects")
        with open_response(method, url, headers=headers, body=json, timeout=timeout) as response:
            return BufferedResponse(response)

    def close(self):
        pass
