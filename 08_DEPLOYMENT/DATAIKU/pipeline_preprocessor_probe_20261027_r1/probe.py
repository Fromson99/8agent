"""One synthetic PDF request. No production imports, source documents or retries."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

VERSION = 'genos-187-path-probe-20261027-r1'
R3_SETTINGS_SHA256 = '6b3165e536fcd63e171b41f9be1db2c2378d38e1c4fb64c31247c1dab6e4da24'
MAX_RESPONSE = 4 * 1024 * 1024
PARAMS = dict(img_desc=0, chart_desc=0, doc_summary=0, table_desc=0,
              table_refine=0, table_text_desc=0)


def pdf_bytes(marker):
    """Valid one-page PDF; Helvetica text needs no installed fonts or packages."""
    if not re.fullmatch('[A-Z0-9]+', marker):
        raise ValueError('MARKER_FORMAT')
    stream = ('BT /F1 18 Tf 40 740 Td (' + marker + ') Tj ET\n').encode('ascii')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream',
    ]
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(('%d 0 obj\n' % number).encode() + body + b'\nendobj\n')
    start = len(out)
    out.extend(('xref\n0 %d\n0000000000 65535 f \n' % len(offsets)).encode())
    for offset in offsets[1:]:
        out.extend(('%010d 00000 n \n' % offset).encode())
    out.extend(('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
                % (len(offsets), start)).encode())
    return bytes(out)


def local_root(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('ROOT_MUST_BE_ABSOLUTE_WITHOUT_DOTDOT')
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('ROOT_SYMLINK_NOT_ALLOWED_AS_IN_R3')
    if not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError('ROOT_MUST_EXIST_AND_BE_READABLE_WRITABLE_TRAVERSABLE')
    return path


def endpoint(args):
    url = args.url or os.environ.get('GENOS_PREPROCESSOR_URL', '').strip()
    if not url:
        ident = args.id or os.environ.get('GENOS_PREPROCESSOR_ID', '').strip() or '187'
        if not re.fullmatch('[1-9][0-9]*', ident):
            raise ValueError('PREPROCESSOR_ID_INVALID')
        url = 'http://preprocessor-' + ident + ':8080/run'
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('URL_REQUIRES_HTTP_WITHOUT_CREDENTIALS_QUERY_FRAGMENT')
    if parsed.path in ('', '/'):
        url = url.rstrip('/') + '/run'
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_once(url, payload, timeout, key):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        status = response.code
        raw = response.read(MAX_RESPONSE + 1)
    return status, raw


def extracted_texts(value):
    """Read actual text fields, not request echoes, paths, messages or metadata."""
    stack = [value]
    remaining = 100000
    while stack and remaining:
        remaining -= 1
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ('request', 'payload', 'params', 'metadata', 'provenance'):
                    continue
                if key in ('text', 'full_text', 'orig') and isinstance(child, str):
                    yield child
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    path.chmod(0o600)


def run(args):
    root = local_root(args.root)
    remote_root = args.remote_root or str(root)
    if not PurePosixPath(remote_root).is_absolute() or '..' in PurePosixPath(remote_root).parts:
        raise ValueError('REMOTE_ROOT_INVALID')
    url = endpoint(args)
    key = os.environ.get('GENOS_PREPROCESSOR_API_KEY', '')
    # Request path ID is independent of the PDF text: echoing a path cannot pass.
    request_id = uuid.uuid4().hex
    marker = 'GENOSPROBE' + uuid.uuid4().hex[:16].upper()
    work = root / ('genos-probe-' + request_id)
    work.mkdir(mode=0o770)
    work.chmod(0o2770)  # Same staging permissions as the R3 parser.
    source = work / 'source.pdf'
    pdf = pdf_bytes(marker)
    with source.open('xb') as stream:
        stream.write(pdf)
    source.chmod(0o640)
    evidence = work / 'evidence'
    evidence.mkdir(mode=0o700)
    remote_file = str(PurePosixPath(remote_root) / work.name / 'source.pdf')
    if args.mode == 'path':
        payload = {'file_path': remote_file, 'params': dict(PARAMS)}
    else:
        # No readable file_path: a pass must come from the provided file bytes.
        payload = {'file_name': 'source.pdf', 'file_content_base64': base64.b64encode(pdf).decode(),
                   'params': dict(PARAMS)}
    save(evidence / 'request.json', payload)
    report = dict(version=VERSION, mode=args.mode, request_id=request_id,
                  declared_context=args.context, hostname=socket.gethostname(), pid=os.getpid(),
                  cwd=str(Path.cwd()), uid=os.getuid(), gid=os.getgid(), groups=os.getgroups(),
                  local_root=str(root), remote_root=remote_root, source_path=str(source),
                  remote_file_path=remote_file if args.mode == 'path' else None,
                  source_sha256=hashlib.sha256(pdf).hexdigest(), source_bytes=len(pdf),
                  marker=marker, endpoint=url, timeout_seconds=args.timeout,
                  max_http_attempts=1, http_attempts=0, redirects=False, retries=False,
                  stage_directory_mode='2770', source_mode='0640',
                  status='PREPARED', marker_found=False,
                  field_code_serving_proven=False,
                  context_note='Only execution in the actual serving Pod proves its visibility. '
                               'The context label/hostname alone does not prove this.',
                  evidence_dir=str(evidence), source_retained=True)
    save(evidence / 'prepared.json', report)
    print('PROBE_START ' + json.dumps({k: report[k] for k in
          ('mode', 'hostname', 'pid', 'cwd', 'local_root', 'endpoint', 'source_path', 'evidence_dir')},
          ensure_ascii=False), flush=True)
    started = time.monotonic()
    report['http_attempts'] = 1
    try:
        status, raw = post_once(url, payload, args.timeout, key)
        report['http_status'] = status
        report['response_bytes_received'] = len(raw)
        report['response_sha256'] = hashlib.sha256(raw).hexdigest()
        # Keep the bounded original response private; redact credentials if echoed by a server.
        private = raw.replace(key.encode(), b'[REDACTED]') if key else raw
        with (evidence / 'response.bin').open('xb') as stream:
            stream.write(private)
        (evidence / 'response.bin').chmod(0o600)
        if len(raw) > MAX_RESPONSE:
            report['status'] = 'RESPONSE_TOO_LARGE'
        elif status != 200:
            report['status'] = 'HTTP_ERROR'
        else:
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError):
                report['status'] = 'INVALID_JSON'
            else:
                valid = (isinstance(body, dict) and not isinstance(body.get('code'), bool)
                         and body.get('code') in (0, '0'))
                if not valid:
                    report['status'] = 'API_ERROR'
                else:
                    report['marker_found'] = any(
                        marker in re.sub(r'\s+', '', text) for text in extracted_texts(body.get('data')))
                    report['status'] = (('PATH_READ_CONFIRMED' if args.mode == 'path'
                                         else 'BASE64_READ_CONFIRMED') if report['marker_found']
                                        else 'HTTP_OK_BUT_PDF_CONTENT_UNCONFIRMED')
                if isinstance(body, dict):
                    message = str(body.get('errMsg', ''))
                    if key:
                        message = message.replace(key, '[REDACTED]')
                    report['api_message'] = message[:1500]
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        report['status'] = 'TRANSPORT_UNKNOWN'
        report['error_type'] = type(exc).__name__
        message = str(exc)
        if key:
            message = message.replace(key, '[REDACTED]')
        report['error_message'] = message[:1500]
        report['remote_processing_may_continue'] = True
    except Exception as exc:
        report['status'] = 'PROBE_ERROR'
        report['error_type'] = type(exc).__name__
        report['remote_processing_may_continue'] = True
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    if report['status'] == 'PATH_READ_CONFIRMED':
        report['settings_if_test_ran_in_actual_serving_pod'] = {
            'GENOS_PREPROCESSOR_SHARED_ROOT': str(root)}
        if remote_root != str(root):
            report['settings_if_test_ran_in_actual_serving_pod']['GENOS_PREPROCESSOR_REMOTE_ROOT'] = remote_root
    report['interpretation'] = {
        'PATH_READ_CONFIRMED': '187 returned text unique to this PDF. Use this root only for the tested execution environment. R3 review-model configuration remains separate.',
        'BASE64_READ_CONFIRMED': '187 accepted these file bytes without file_path. R3 needs a transport change before SHARED_ROOT can be omitted.',
    }.get(report['status'], 'Not a success. Failure alone does not prove a missing mount; check response.bin for path, permissions, schema or parser errors.')
    save(evidence / 'result.json', report)
    print('PROBE_RESULT ' + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    print('RESULT_FILE=' + str(evidence / 'result.json'), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='/tmp', help='Existing absolute directory; default /tmp')
    parser.add_argument('--remote-root', help='Only if the same storage has another path in 187')
    parser.add_argument('--mode', choices=('path', 'base64'), default='path')
    parser.add_argument('--url', help='Exact API URL; overrides environment. No automatic route guessing.')
    parser.add_argument('--id', help='Preprocessor ID when URL is not configured; default 187')
    parser.add_argument('--timeout', type=int, default=120, help='HTTP socket timeout seconds, 5..300')
    parser.add_argument('--context', choices=('unknown', 'dev', 'serving-pod'), default='unknown',
                        help='Operator declaration; does not detect or prove runtime location')
    parser.add_argument('--check-r3-config', action='store_true',
                        help='Read the exact installed R3 Settings; no PDF or HTTP request')
    parser.add_argument('--code-root', default=str(Path.home() / 'DEV'),
                        help='Installed R3 code root for --check-r3-config')
    args = parser.parse_args(argv)
    if not 5 <= args.timeout <= 300:
        parser.error('--timeout must be 5..300')
    if args.check_r3_config:
        source = Path(args.code_root) / '02_BACKEND/lawrag/core/genos_preprocessor.py'
        try:
            if hashlib.sha256(source.read_bytes()).hexdigest() != R3_SETTINGS_SHA256:
                raise ValueError('R3_SETTINGS_CODE_MISMATCH')
            spec = importlib.util.spec_from_file_location('_probe_r3_settings', source)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            module.Settings.from_env()
        except Exception as exc:
            # Settings validates only non-secret fields. Never dump the environment.
            message = str(exc)
            for key_name in ('GENOS_PREPROCESSOR_API_KEY', 'GENOS_LLM_KEY'):
                secret = os.environ.get(key_name, '')
                if secret:
                    message = message.replace(secret, '[REDACTED]')
            print('CONFIG_INVALID_REASON=' + message)
            print('CONTEXT=' + args.context + ' HOSTNAME=' + socket.gethostname())
            return 2
        print('CONFIG_FORMAT_OK; remote file visibility and model connectivity NOT_CHECKED')
        return 0
    try:
        result = run(args)
    except (ValueError, OSError) as exc:
        print('PROBE_SETUP_FAILED ' + str(exc), file=sys.stderr)
        return 2
    return 0 if result['status'] in ('PATH_READ_CONFIRMED', 'BASE64_READ_CONFIRMED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
