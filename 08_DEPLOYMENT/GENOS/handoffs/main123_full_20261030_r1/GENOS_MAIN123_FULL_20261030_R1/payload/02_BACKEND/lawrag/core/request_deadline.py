"""One physical HTTP request with an absolute deadline and bounded cleanup.

The short-lived worker owns only this request's socket and bytes. It has no
job registry, persistence, retry or provider policy. Credentials travel through
stdin, never argv or diagnostic frames. Killing/reaping it stops local I/O;
it cannot establish whether the remote provider stopped computing.
"""
from __future__ import annotations
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import httpx


class AbsoluteDeadlineExceeded(httpx.TimeoutException):
    def __init__(self, diagnostics, partial_body=b''):
        super().__init__('absolute model request deadline exceeded')
        self.diagnostics = diagnostics
        self.partial_body = partial_body


def _frames(raw):
    headers = {}; chunks = []; final = None; times = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
            if row['event'] == 'headers': headers = row
            elif row['event'] == 'chunk':
                chunks.append(base64.b64decode(row['data'], validate=True)); times.append(row['at'])
            elif row['event'] in ('done', 'error'): final = row
        except (ValueError, KeyError, TypeError):
            # The process may be killed in the middle of its final pipe frame.
            continue
    body = b''.join(chunks)
    diag = {'headers_received': bool(headers), 'received_http_status': headers.get('status'),
            'response_headers': headers.get('headers', {}), 'headers_at': headers.get('at'),
            'received_chunks': len(chunks), 'received_bytes': len(body),
            'first_chunk_at': times[0] if times else None, 'last_chunk_at': times[-1] if times else None,
            'received_sha256': hashlib.sha256(body).hexdigest(),
            'whitespace_only': bool(body) and not body.strip(), 'complete': bool(final and final['event'] == 'done')}
    return headers, body, final, diag


def post_json(url, *, headers, json_body, deadline, transport=None):
    """No retry. Deadline covers startup, request, complete body and IPC.

    MockTransport is an explicit synchronous test seam, not production I/O;
    arbitrary injected real transports cannot bypass the deadline worker.
    """
    start = time.monotonic()
    if not math.isfinite(deadline) or deadline <= start:
        raise AbsoluteDeadlineExceeded({'sent': False, 'worker_reaped': True, 'complete': False, 'elapsed_seconds': 0})
    if transport is not None:
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError('injected transport must be a synchronous MockTransport fixture')
        with httpx.Client(transport=transport, timeout=deadline-start, trust_env=False, follow_redirects=False) as client:
            response = client.post(url, headers=headers, json=json_body)
        if time.monotonic() >= deadline:
            raise AbsoluteDeadlineExceeded({'sent': True, 'worker_reaped': True, 'complete': True, 'test_transport': True})
        return response
    wire = json.dumps({'url': str(url), 'headers': headers, 'body': json_body,
                       'deadline': deadline}, ensure_ascii=False).encode()
    if time.monotonic() >= deadline:
        raise AbsoluteDeadlineExceeded({'sent': False, 'worker_reaped': True, 'complete': False})
    proc = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '--worker', str(os.getpid())],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    expired = False
    try:
        try:
            raw, _ = proc.communicate(wire, timeout=max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            expired = True
            proc.kill()
            raw, _ = proc.communicate(timeout=1.0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=1.0)
        for pipe in (proc.stdin, proc.stdout):
            if pipe is not None: pipe.close()
    head, body, final, diag = _frames(raw)
    diag.update(worker_pid=proc.pid, worker_reaped=proc.returncode is not None,
                worker_returncode=proc.returncode, elapsed_seconds=time.monotonic()-start,
                deadline=deadline, sent=None, enforcement='absolute-process-v1')
    if expired or time.monotonic() >= deadline:
        raise AbsoluteDeadlineExceeded(diag, body)
    if final and final['event'] == 'error':
        # Preserve known pre-accept failures; all other uncertainty stays unknown.
        cls = {n:getattr(httpx,n) for n in ('ConnectError','ConnectTimeout','PoolTimeout','ReadTimeout','ReadError','WriteTimeout','WriteError','RemoteProtocolError')}.get(final['type'], httpx.TransportError)
        error = cls('model HTTP worker failed: '+final['type'])
        error.diagnostics = diag; error.partial_body = body
        raise error
    if not final or final['event'] != 'done' or not head:
        error = httpx.TransportError('model HTTP worker exited without complete response')
        error.diagnostics = diag; error.partial_body = body
        raise error
    response = httpx.Response(head['status'], headers=head['headers'], content=body,
                              request=httpx.Request('POST', url))
    response.extensions['absolute_deadline'] = diag
    return response


def _worker(parent_pid):
    if sys.platform.startswith('linux'):
        import ctypes
        import signal
        # Parent interruption must not leave a request process behind.
        ctypes.CDLL(None).prctl(1, signal.SIGKILL)
        if os.getppid() != parent_pid: return
    def emit(event, **fields):
        print(json.dumps({'event': event, 'at': time.monotonic(), **fields}, separators=(',',':')), flush=True)
    try:
        args = json.load(sys.stdin)
        remaining = args['deadline']-time.monotonic()
        if remaining <= 0:
            emit('error', type='DeadlineBeforeSend'); return
        with httpx.Client(timeout=remaining, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', args['url'], headers=args['headers'], json=args['body']) as response:
                allowed = ('retry-after','content-type','x-request-id','x-openrouter-request-id','cf-ray')
                emit('headers', status=response.status_code, headers={k:response.headers[k] for k in allowed if k in response.headers})
                for chunk in response.iter_bytes():
                    emit('chunk', data=base64.b64encode(chunk).decode('ascii'))
                emit('done')
    except BaseException as exc:
        emit('error', type=type(exc).__name__)


if __name__ == '__main__' and sys.argv[1:2] == ['--worker']:
    _worker(int(sys.argv[2]))
