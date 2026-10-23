#!/usr/bin/env python3
"""GENOS terminal -> approved relay diagnostic; Python standard library only."""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import sys
import time
from urllib.parse import quote, quote_plus, urlencode, urlsplit
import warnings
import xml.etree.ElementTree as ET

VERSION = 'genos-relay-terminal-20261023-r1'
MAX_BYTES = 12 * 1024 * 1024
LAW_NAME = '자본시장과 금융투자업에 관한 법률'

# Reused verbatim from the previously checked law API diagnostic.
__XML_HELPERS__


class StageDeadline(TimeoutError):
    pass


@contextmanager
def bounded(seconds):
    def expired(signum, frame):
        raise StageDeadline('STAGE_TIME_LIMIT')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def secret_values(secrets):
    values = [value for value in secrets if value]
    if len(secrets) > 1 and secrets[1]:
        values.extend(item.split('=', 1)[1].strip() for item in secrets[1].split(';') if '=' in item)
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def atomic(path, value):
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class Run:
    def __init__(self, args):
        self.args = args
        origin = args.relay.rstrip('/')
        self.url = urlsplit(origin)
        if (self.url.scheme != 'https' or not self.url.hostname or self.url.username
                or self.url.password or self.url.path or self.url.query or self.url.fragment):
            raise ValueError('RELAY_FORMAT: https://승인된주소:포트 형식이 필요합니다.')
        self.port = self.url.port or 443
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.run_id):
            raise ValueError('RUN_ID_FORMAT')
        ca = Path(args.ca).resolve(strict=True) if args.ca else None
        self.context = ssl.create_default_context(cafile=str(ca) if ca else None)
        # Environment proxies are intentionally not used: this checks direct GENOS egress.
        self.config = {'relay': origin, 'proxy_mode': 'DIRECT_NO_ENV_PROXY',
                       'target_url': args.law_origin + '/DRF/lawService.do?target=law',
                       'law_id': '010513', 'law_name': LAW_NAME,
                       'ca_sha256': sha(ca.read_bytes()) if ca else None,
                       'tls_defaults': {name: sha(Path(value).read_bytes()) if value and Path(value).is_file() else None
                                        for name in ('SSL_CERT_FILE',)
                                        for value in (os.environ.get(name),)},
                       'code_sha256': sha(Path(__file__).read_bytes())}
        self.binding = sha(json.dumps(self.config, sort_keys=True).encode())
        self.folder = Path(args.output) / args.run_id
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = (self.folder / 'run.lock').open('a')
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise ValueError('RUN_BUSY: 같은 작업이 실행 중입니다.') from None
        self.file = self.folder / 'result.json'
        if self.file.exists():
            self.state = json.loads(self.file.read_text(encoding='utf-8'))
            if self.state.get('binding') != self.binding:
                raise ValueError('BINDING_CHANGED: 기존 기록을 보존하고 새 --run-id를 지정하세요.')
        else:
            self.state = {'version': VERSION, 'binding': self.binding, 'config': self.config,
                          'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'deadline': time.time() + 900, 'stages': {}, 'attempts': 0,
                          'automatic_retries': 0,
                          'environment': {'python': sys.version, 'executable': sys.executable,
                                          'hostname': socket.gethostname(),
                                          'scope': 'this terminal process; serving container not verified'}}
            self.save()
        self.event('OPEN', version=VERSION)

    def close(self):
        self.lock.close()

    def save(self):
        atomic(self.file, self.state)

    def event(self, event, **fields):
        with (self.folder / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(at=time.time(), event=event, **fields), ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def stage(self, name, action, seconds, secrets=()):
        if name in self.state['stages']:
            row = self.state['stages'][name]
            print(name, row['status'], '(저장된 기록; 추가 호출 없음)', flush=True)
            return row
        if time.time() >= self.state['deadline'] or self.state['attempts'] >= 3:
            raise ValueError('BUDGET_EXHAUSTED: 기존 기록을 보존하고 새 --run-id로 확인하세요.')
        self.state['attempts'] += 1
        row = {'status': 'IN_FLIGHT', 'phase': 'START', 'started': time.time()}
        self.state['stages'][name] = row
        self.save()
        self.event('STAGE_START', stage=name, attempt=self.state['attempts'])
        print(name, '확인 중...', flush=True)
        start = time.monotonic()
        try:
            with bounded(min(seconds, max(0.001, self.state['deadline'] - time.time()))):
                action(row)
        except ssl.SSLError as exc:
            row.update(status='TLS_ERROR', error_class=type(exc).__name__, reason=masked(str(exc), secrets))
        except (TimeoutError, socket.timeout) as exc:
            row.update(status='TIMEOUT', error_class=type(exc).__name__)
        except socket.gaierror as exc:
            row.update(status='DNS_ERROR', errno=exc.errno)
        except (ConnectionError, http.client.HTTPException) as exc:
            row.update(status='CONNECTION_ERROR', error_class=type(exc).__name__,
                       reason=masked(str(exc), secrets))
        except (ET.ParseError, ValueError, UnicodeError) as exc:
            row.update(status='RESPONSE_REJECTED', error_class=type(exc).__name__,
                       reason=masked(str(exc), secrets))
        except KeyboardInterrupt:
            row.update(status='INTERRUPTED')
            raise
        except OSError as exc:
            row.update(status='OS_ERROR', error_class=type(exc).__name__, errno=exc.errno,
                       reason=masked(str(exc), secrets))
        except Exception as exc:
            row.update(status='LOCAL_ERROR', error_class=type(exc).__name__)
            raise
        finally:
            row['elapsed_seconds'] = round(time.monotonic() - start, 3)
            self.save()
            self.event('STAGE_END', stage=name, status=row['status'])
        print(name, row['status'], 'HTTP', row.get('http_status', '-'),
              row['elapsed_seconds'], '초', flush=True)
        return row

    def tcp(self, row):
        row['phase'] = 'TCP_CONNECT'
        with socket.create_connection((self.url.hostname, self.port), timeout=8) as sock:
            row.update(status='TCP_OK', local=list(sock.getsockname()), peer=list(sock.getpeername()))

    def http(self, row, method, secrets=()):
        connection = http.client.HTTPSConnection(self.url.hostname, self.port, timeout=8, context=self.context)
        response = None
        raw = bytearray()
        try:
            row['phase'] = 'TCP_TLS_CONNECT'
            connection.connect()
            row.update(tls_version=connection.sock.version(),
                       local=list(connection.sock.getsockname()), peer=list(connection.sock.getpeername()))
            connection.sock.settimeout(20 if method == 'GET' else 10)
            headers = {'Accept': 'application/xml', 'Accept-Encoding': 'identity',
                       'User-Agent': VERSION, 'Connection': 'close'}
            path = '/law/DRF'
            if method == 'GET':
                oc, cookie = secrets
                headers['target_url'] = self.config['target_url']
                if cookie:
                    headers['Cookie'] = cookie
                path += '?' + urlencode({'OC': oc, 'ID': self.config['law_id'], 'type': 'XML'})
            row['phase'] = 'HTTP_SEND'
            connection.request(method, path, headers=headers)
            row['phase'] = 'HTTP_HEADERS'
            response = connection.getresponse()
            row.update(http_status=response.status,
                       content_type=masked(response.getheader('Content-Type', ''), secret_values(secrets)))
            if method == 'HEAD':
                row['status'] = 'HTTP_RESPONSE_RECEIVED'
                return
            row['phase'] = 'HTTP_BODY'
            while True:
                block = response.read1(min(65536, MAX_BYTES - len(raw) + 1))
                if not block:
                    break
                raw.extend(block)
                if len(raw) > MAX_BYTES:
                    raise ValueError('RESPONSE_SIZE_LIMIT')
            row['phase'] = 'XML_VALIDATE'
            if response.status != 200:
                row['status'] = 'HTTP_' + str(response.status)
                return
            if response.getheader('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                raise ValueError('UNEXPECTED_CONTENT_ENCODING')
            meta = inspect_xml(bytes(raw), 'law_body', self.config['law_name'], self.config['law_id'])
            meta.pop('sample', None)
            row.update(json.loads(masked(json.dumps(meta, ensure_ascii=False), secret_values(secrets))))
        finally:
            if response is not None:
                response.close()
            connection.close()
            if method == 'GET':
                row.update(received_bytes=len(raw), received_sha256=sha(raw))
                if raw:
                    clean = bytes(raw)
                    values = set()
                    for secret in secret_values(secrets):
                        if secret:
                            values.update((secret, quote(secret, safe=''), quote_plus(secret)))
                    for value in sorted(values, key=len, reverse=True):
                        clean = clean.replace(value.encode(), b'REDACTED')
                    target = self.folder / 'law_response.xml.gz'
                    with target.open('wb') as stream:
                        stream.write(gzip.compress(clean, mtime=0))
                        stream.flush()
                        os.fsync(stream.fileno())
                    row.update(response_file=target.name, credential_redacted=clean != raw,
                               saved_content_sha256=sha(clean), saved_file_sha256=sha(target.read_bytes()))

    def execute(self):
        tcp = self.stage('tcp', self.tcp, 10)
        if tcp['status'] != 'TCP_OK':
            return 2
        head = self.stage('https', lambda row: self.http(row, 'HEAD'), 20)
        if head['status'] != 'HTTP_RESPONSE_RECEIVED':
            return 2
        if not self.args.body:
            print('중계 HTTP 응답 수신 확인. 법령 본문은 --body 실행으로 확인합니다.')
            return 0
        if 'law' in self.state['stages']:
            row = self.stage('law', None, 60)
            return 0 if row['status'] == 'BODY_OK' else 2
        if time.time() >= self.state['deadline']:
            raise ValueError('BUDGET_EXHAUSTED: 새 --run-id가 필요합니다.')
        oc = os.environ.get('LAW_OC', '').strip()
        cookie = os.environ.get('RELAY_COOKIE', '').strip()
        if not oc:
            # Never fall back to echoed stdin when a real terminal is unavailable.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                oc = getpass.getpass('법제처 등록 OC (표시 안 됨): ').strip()
                if not cookie:
                    cookie = getpass.getpass('중계 Cookie (필요 없으면 Enter, 표시 안 됨): ').strip()
        if not oc or oc.lower() == 'test' or any(c in oc + cookie for c in '\r\n'):
            raise ValueError('CREDENTIAL_INPUT_INVALID')
        try:
            cookie.encode('latin-1')
        except UnicodeEncodeError:
            raise ValueError('COOKIE_HEADER_ENCODING') from None
        row = self.stage('law', lambda record: self.http(record, 'GET', (oc, cookie)), 60, secret_values((oc, cookie)))
        if row['status'] == 'BODY_OK':
            print('법령 본문 확인:', row['document_name'], 'ID', row['id'], '조문', row['article_blocks'])
        return 0 if row['status'] == 'BODY_OK' else 2


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='GENOS 터미널의 직접 TCP/HTTPS 중계 연결 및 법령 본문 확인')
    parser.add_argument('--relay', default='https://45.101.64.86:8443', help='확인된 개발계 샘플; 운영 주소 아님')
    parser.add_argument('--body', action='store_true', help='중계를 통한 법령 XML GET 1회 추가')
    parser.add_argument('--ca', default='', help='필요한 경우 사내 CA PEM 파일')
    parser.add_argument('--law-origin', default='http://www.law.go.kr',
                        choices=['http://www.law.go.kr', 'https://www.law.go.kr'])
    parser.add_argument('--run-id', default='relay-check-01', help='같은 ID 재실행은 기록 재사용; 새 확인은 다른 ID')
    parser.add_argument('--output', default='./GENOS_RELAY_RESULTS')
    args = parser.parse_args()
    run = None
    try:
        run = Run(args)
        print('GENOS 터미널 중계 확인:', run.config['relay'])
        print('직접 연결 / 자동 재시도 0 / TLS 검증 사용 / 코드서빙 배포 변경 없음')
        return run.execute()
    except KeyboardInterrupt:
        print('INTERRUPTED: 기존 결과와 중단 기록을 보존했습니다.', file=sys.stderr)
        return 130
    except Exception as exc:
        # Credentials, remote headers, request URL and arbitrary exception text are not printed.
        print('LOCAL_OR_CONFIG_ERROR:', type(exc).__name__, file=sys.stderr)
        if isinstance(exc, ValueError) and str(exc).startswith(('RELAY_FORMAT', 'RUN_ID_FORMAT', 'RUN_BUSY',
                'BINDING_CHANGED', 'BUDGET_EXHAUSTED', 'CREDENTIAL_INPUT_INVALID', 'COOKIE_HEADER_ENCODING')):
            print(str(exc), file=sys.stderr)
        return 2
    finally:
        if run is not None:
            print('결과:', run.file.resolve())
            print('지속 로그:', (run.folder / 'events.jsonl').resolve())
            run.close()


if __name__ == '__main__':
    sys.exit(main())
