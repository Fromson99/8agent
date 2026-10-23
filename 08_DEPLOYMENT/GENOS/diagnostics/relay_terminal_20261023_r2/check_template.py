#!/usr/bin/env python3
"""One direct relay GET with separately observed DNS, TCP, TLS and HTTP phases."""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import gzip
import hashlib
import http.client
import ipaddress
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

VERSION = 'genos-relay-terminal-20261023-r2'
MAX_BYTES = 12 * 1024 * 1024
LAW_NAME = '자본시장과 금융투자업에 관한 법률'
__XML_HELPERS__


class StageDeadline(TimeoutError):
    pass


@contextmanager
def bounded(seconds):
    def expired(signum, frame):
        raise StageDeadline('TOTAL_TIME_LIMIT')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def secret_values(oc, cookie):
    values = [oc, cookie]
    values.extend(item.split('=', 1)[1].strip() for item in cookie.split(';') if '=' in item)
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def atomic(path, value):
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def request_config(args):
    if args.request == 'notice':
        return {'method': 'GET', 'path': '/law/making',
                'target_url': args.notice_origin + '/rest/ptcpAdmPp.xml',
                'params': {'lsClsCd': 'BA0103', 'closing': 'Y',
                           'asndOfiNm': '금융위원회', 'admRulNm': '지주'},
                'kind': 'notice', 'credential_env': 'MAKING_OC'}
    if args.request == 'law':
        return {'method': 'GET', 'path': '/law/DRF',
                'target_url': args.law_origin + '/DRF/lawService.do?target=law',
                'params': {'ID': '010513', 'type': 'XML'}, 'kind': 'law_body', 'credential_env': 'LAW_OC'}
    return {'kind': 'tls', 'method': None, 'path': None, 'target_url': None, 'params': {}}


class Run:
    def __init__(self, args):
        self.args, self.secrets = args, ()
        self.request = request_config(args)
        self.url = urlsplit(args.relay.rstrip('/'))
        if (self.url.scheme != 'https' or not self.url.hostname or self.url.username or self.url.password
                or self.url.path or self.url.query or self.url.fragment):
            raise ValueError('RELAY_FORMAT: https://승인주소:포트 형식이 필요합니다.')
        self.port = self.url.port or 443
        run_id = args.run_id or args.request + '-01'
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', run_id):
            raise ValueError('RUN_ID_FORMAT')
        if not all(0 < value <= 120 for value in (args.connect_timeout, args.tls_timeout, args.read_timeout)):
            raise ValueError('TIMEOUT_RANGE: 각 제한은 0초 초과 120초 이하입니다.')
        ca = Path(args.ca).resolve(strict=True) if args.ca else None
        self.context = ssl.create_default_context(cafile=str(ca) if ca else None)
        self.context.set_alpn_protocols(['http/1.1'])
        try:
            ipaddress.ip_address(self.url.hostname)
            sni = None
        except ValueError:
            sni = self.url.hostname
        self.config = {'relay': args.relay.rstrip('/'), 'request': self.request,
                       'proxy_mode': 'DIRECT_NO_ENV_PROXY', 'sni_name': sni,
                       'certificate_identity': self.url.hostname,
                       'ca_sha256': sha(ca.read_bytes()) if ca else None,
                       'connect_timeout': args.connect_timeout, 'tls_timeout': args.tls_timeout,
                       'read_timeout': args.read_timeout, 'total_timeout': 120,
                       'code_sha256': sha(Path(__file__).read_bytes())}
        ca_env = os.environ.get('SSL_CERT_FILE')
        self.config['environment_ca_sha256'] = sha(Path(ca_env).read_bytes()) if ca_env and Path(ca_env).is_file() else None
        self.binding = sha(json.dumps(self.config, sort_keys=True).encode())
        self.folder = Path(args.output) / run_id
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
                raise ValueError('BINDING_CHANGED: 기존 결과를 보존하고 새 --run-id로 실행하세요.')
        else:
            self.state = {'version': VERSION, 'binding': self.binding, 'config': self.config,
                          'created': time.time(), 'deadline': time.time() + 900,
                          'status': 'READY', 'phase': 'READY', 'attempts': 0,
                          'physical_connections': 0, 'automatic_retries': 0,
                          'tcp_connected': False, 'tls_established': False,
                          'http_request_sent': False, 'http_response_received': False,
                          'environment': {'python': sys.version, 'executable': sys.executable,
                                          'hostname': socket.gethostname(), 'scope': 'this terminal only'}}
            self.save()
        self.event('OPEN', '터미널과 파일에 같은 진행 로그를 기록합니다.',
                   result=str(self.file.resolve()), request=args.request)

    def close(self):
        self.lock.close()

    def save(self):
        atomic(self.file, self.state)

    def event(self, event, message='', **fields):
        record = {'at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'event': event, 'message': message, **fields}
        record = json.loads(masked(json.dumps(record, ensure_ascii=False), self.secrets))
        line = '[' + record['at_utc'] + '] ' + event + ' ' + record['message']
        details = {k: v for k, v in record.items() if k not in ('at_utc', 'event', 'message')}
        if details:
            line += ' ' + json.dumps(details, ensure_ascii=False)
        # Persist before showing the same line; flush each event in both destinations.
        for name, content in (('events.jsonl', json.dumps(record, ensure_ascii=False)), ('terminal.log', line)):
            with (self.folder / name).open('a', encoding='utf-8') as stream:
                stream.write(content + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        print(line, flush=True)

    def phase(self, name, message, **fields):
        self.state['phase'] = name
        self.save()
        self.event(name, message, **fields)

    def credentials(self):
        if self.request['kind'] == 'tls':
            return '', ''
        key = self.request['credential_env']
        oc, cookie = os.environ.get(key, '').strip(), os.environ.get('RELAY_COOKIE', '').strip()
        if not oc:
            self.event('CREDENTIAL_INPUT', '현재 등록 OC와 필요한 경우 Cookie를 비표시 입력하세요.', variable=key)
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                label = '국민참여입법센터' if key == 'MAKING_OC' else '국가법령정보센터'
                oc = getpass.getpass(label + ' 등록 OC (표시 안 됨): ').strip()
                if not cookie:
                    cookie = getpass.getpass('중계 Cookie (필요 없으면 Enter, 표시 안 됨): ').strip()
        if not oc or oc.lower() == 'test' or any(c in oc + cookie for c in '\r\n'):
            raise ValueError('CREDENTIAL_INPUT_INVALID')
        try:
            cookie.encode('latin-1')
        except UnicodeEncodeError:
            raise ValueError('COOKIE_HEADER_ENCODING') from None
        self.secrets = secret_values(oc, cookie)
        return oc, cookie

    def exchange(self, oc, cookie):
        sock = tls = connection = response = None
        raw = bytearray()
        try:
            self.phase('DNS_START', '목적지 주소 확인', host=self.url.hostname, port=self.port)
            addresses = socket.getaddrinfo(self.url.hostname, self.port, type=socket.SOCK_STREAM)
            if not addresses:
                raise ValueError('DNS_EMPTY')
            family, kind, proto, _, address = addresses[0]
            self.event('DNS_OK', '첫 주소 한 곳에만 연결합니다.', address=list(address), address_count=len(addresses))
            self.state['physical_connections'] = 1
            self.phase('TCP_START', 'TCP 연결 시작', address=list(address), timeout=self.args.connect_timeout)
            start = time.monotonic()
            sock = socket.socket(family, kind, proto)
            sock.settimeout(self.args.connect_timeout)
            sock.connect(address)
            self.state.update(tcp_connected=True, tcp_seconds=round(time.monotonic()-start, 3),
                              local=list(sock.getsockname()), peer=list(sock.getpeername()))
            self.phase('TCP_OK', 'TCP 연결 성공', seconds=self.state['tcp_seconds'],
                       local=self.state['local'], peer=self.state['peer'])
            self.phase('TLS_START', '같은 TCP 연결에서 TLS 협상 시작', timeout=self.args.tls_timeout,
                       sni_name=self.config['sni_name'], verify=True)
            start = time.monotonic()
            sock.settimeout(self.args.tls_timeout)
            tls = self.context.wrap_socket(sock, server_hostname=self.url.hostname, do_handshake_on_connect=False)
            tls.do_handshake()
            self.state.update(tls_established=True, tls_seconds=round(time.monotonic()-start, 3),
                              tls_version=tls.version(), cipher=tls.cipher()[0])
            self.phase('TLS_OK', 'TLS 협상·서버 인증서 검증 성공', seconds=self.state['tls_seconds'],
                       tls_version=tls.version(), cipher=tls.cipher()[0])
            if self.request['kind'] == 'tls':
                self.state['status'] = 'TLS_OK'
                return
            tls.settimeout(self.args.read_timeout)
            # Attach the verified socket, disallow HTTPConnection's implicit reconnect.
            connection = http.client.HTTPConnection(self.url.hostname, self.port, timeout=self.args.read_timeout)
            connection.sock = tls
            connection.auto_open = 0
            params = {'OC': oc, **self.request['params']}
            path = self.request['path'] + '?' + urlencode(params)
            headers = {'target_url': self.request['target_url'], 'Accept': 'application/xml',
                       'Accept-Encoding': 'identity', 'User-Agent': VERSION, 'Connection': 'close'}
            if cookie:
                headers['Cookie'] = cookie
            # A write failure can occur after some request bytes have left the socket.
            # None means send completion is unknown; it must not become "not sent".
            self.state['http_request_sent'] = None
            self.phase('HTTP_SEND', 'GET 요청 전송 시작', method='GET', relay_path=self.request['path'],
                       target_url=self.request['target_url'], params={**self.request['params'], 'OC': '[HIDDEN]'},
                       cookie_present=bool(cookie))
            connection.request('GET', path, headers=headers)
            self.state['http_request_sent'] = True
            self.phase('HTTP_WAIT', 'GET 전송 완료, 응답 헤더 대기', timeout=self.args.read_timeout)
            response = connection.getresponse()
            self.state.update(http_response_received=True, http_status=response.status,
                              content_type=masked(response.getheader('Content-Type', ''), self.secrets))
            self.phase('HTTP_HEADERS', '응답 헤더 수신', status=response.status,
                       content_type=self.state['content_type'])
            self.phase('HTTP_BODY', '응답 본문 수신 시작', limit_bytes=MAX_BYTES)
            next_progress = 1
            while True:
                block = response.read1(min(65536, MAX_BYTES-len(raw)+1))
                if not block:
                    break
                raw.extend(block)
                if len(raw) >= next_progress:
                    self.event('BODY_PROGRESS', '본문 수신 중', received_bytes=len(raw))
                    next_progress = len(raw)+1024*1024
                if len(raw) > MAX_BYTES:
                    raise ValueError('RESPONSE_SIZE_LIMIT')
            if response.length not in (None, 0):
                raise ValueError('TRUNCATED_HTTP_BODY')
            self.phase('XML_VALIDATE', 'HTTP 응답과 XML 종류 확인', received_bytes=len(raw))
            if response.status != 200:
                self.state['status'] = 'HTTP_'+str(response.status)
                return
            if response.getheader('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                raise ValueError('UNEXPECTED_CONTENT_ENCODING')
            meta = inspect_xml(bytes(raw), self.request['kind'],
                               LAW_NAME if self.args.request == 'law' else '',
                               '010513' if self.args.request == 'law' else '')
            meta.pop('sample', None)
            self.state.update(json.loads(masked(json.dumps(meta, ensure_ascii=False), self.secrets)))
            self.state['business_validation'] = 'LAW_BODY_VERIFIED' if self.args.request == 'law' else 'REVIEW_REQUIRED'
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()
            if tls is not None:
                tls.close()
            if sock is not None:
                sock.close()
            self.state.update(received_bytes=len(raw), received_sha256=sha(raw))
            if raw:
                self.save_response(bytes(raw))

    def save_response(self, raw):
        clean = raw
        values = set()
        for value in self.secrets:
            values.update((value, quote(value, safe=''), quote_plus(value)))
        for value in sorted(values, key=len, reverse=True):
            clean = clean.replace(value.encode(), b'REDACTED')
        target = self.folder / 'response.body.gz'
        with target.open('wb') as stream:
            stream.write(gzip.compress(clean, mtime=0))
            stream.flush()
            os.fsync(stream.fileno())
        preview = clean.decode('utf-8', errors='replace')[:800]
        self.state.update(response_file=target.name, credential_redacted=raw != clean,
                          saved_content_sha256=sha(clean), saved_file_sha256=sha(target.read_bytes()))
        self.event('RESPONSE_SAVED', '본문 저장 완료. 원수신 해시와 자격값 제거 저장본 해시는 구분합니다.',
                   bytes=len(raw), file=str(target.resolve()))
        self.event('BODY_PREVIEW', '응답 앞부분 (자격값 제거, 최대 800자)', preview=preview)

    def execute(self):
        if self.state['status'] != 'READY':
            self.event('REUSED', '이전 성공·실패·중단 기록입니다. 새 요청을 보내지 않습니다.',
                       status=self.state['status'], phase=self.state['phase'],
                       http_status=self.state.get('http_status'))
            return self.exit_code()
        if time.time() >= self.state['deadline']:
            raise ValueError('BUDGET_EXHAUSTED: 새 --run-id가 필요합니다.')
        oc, cookie = self.credentials()
        if time.time() >= self.state['deadline']:
            raise ValueError('BUDGET_EXHAUSTED: 새 --run-id가 필요합니다.')
        self.state.update(status='IN_FLIGHT', attempts=1, started=time.time())
        self.save()
        start = time.monotonic()
        try:
            with bounded(min(120, max(.001, self.state['deadline']-time.time()))):
                self.exchange(oc, cookie)
        except ssl.SSLError as exc:
            self.fail('TLS_ERROR', exc)
        except TimeoutError as exc:
            self.fail('TIMEOUT', exc)
        except socket.gaierror as exc:
            self.fail('DNS_ERROR', exc)
        except (ConnectionError, http.client.HTTPException) as exc:
            self.fail('CONNECTION_ERROR', exc)
        except (ET.ParseError, ValueError, UnicodeError) as exc:
            self.fail('RESPONSE_REJECTED', exc)
        except OSError as exc:
            self.fail('OS_ERROR', exc)
        except KeyboardInterrupt:
            self.state.update(status='INTERRUPTED', failure_phase=self.state['phase'])
            raise
        except Exception as exc:
            self.fail('LOCAL_ERROR', exc)
            raise
        finally:
            self.state['elapsed_seconds'] = round(time.monotonic()-start, 3)
            self.save()
            self.event('RESULT', '실행 결과', status=self.state['status'], phase=self.state['phase'],
                       http_status=self.state.get('http_status'), tcp=self.state['tcp_connected'],
                       tls=self.state['tls_established'], request_sent=self.state['http_request_sent'],
                       response_received=self.state['http_response_received'], seconds=self.state['elapsed_seconds'])
        return self.exit_code()

    def fail(self, status, exc):
        self.state.update(status=status, failure_phase=self.state['phase'], error_class=type(exc).__name__,
                          reason=masked(str(exc), self.secrets), errno=getattr(exc, 'errno', None))
        self.event('ERROR', '이 단계에서 중단했습니다. 자동 재시도는 하지 않습니다.',
                   phase=self.state['phase'], error_class=type(exc).__name__, reason=self.state['reason'])

    def exit_code(self):
        if self.state['status'] in ('TLS_OK', 'BODY_OK'):
            return 0
        if self.state['status'] == 'NOTICE_XML_REVIEW_REQUIRED':
            return 3
        return 2


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='사진의 행정예고 GET 또는 법령 GET. TCP/TLS/HTTP 실시간 로그.')
    parser.add_argument('--request', choices=['notice', 'law', 'tls'], default='notice')
    parser.add_argument('--relay', default='https://45.101.64.86:8443')
    parser.add_argument('--ca', default='')
    parser.add_argument('--notice-origin', default='https://opinion.lawmaking.go.kr',
                        choices=['https://opinion.lawmaking.go.kr', 'https://www.lawmaking.go.kr'])
    parser.add_argument('--law-origin', default='http://www.law.go.kr',
                        choices=['http://www.law.go.kr', 'https://www.law.go.kr'])
    parser.add_argument('--run-id', default=None)
    parser.add_argument('--output', default='./GENOS_RELAY_RESULTS_R2')
    parser.add_argument('--connect-timeout', type=float, default=8)
    parser.add_argument('--tls-timeout', type=float, default=15)
    parser.add_argument('--read-timeout', type=float, default=20)
    args = parser.parse_args()
    run = None
    try:
        run = Run(args)
        return run.execute()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if run is not None:
            run.state['last_local_error'] = {'error_class': type(exc).__name__, 'reason': masked(str(exc), run.secrets)}
            try:
                run.save()
                run.event('LOCAL_OR_CONFIG_ERROR', '로컬 설정/저장/입력 오류', **run.state['last_local_error'])
            except OSError:
                print('LOCAL_LOG_WRITE_FAILED: '+type(exc).__name__, flush=True)
        else:
            print('LOCAL_OR_CONFIG_ERROR: '+type(exc).__name__, flush=True)
        if isinstance(exc, ValueError) and str(exc).startswith(('RELAY_FORMAT','RUN_ID_FORMAT','RUN_BUSY',
                'BINDING_CHANGED','BUDGET_EXHAUSTED','CREDENTIAL_INPUT_INVALID','COOKIE_HEADER_ENCODING','TIMEOUT_RANGE')):
            print(str(exc), flush=True)
        return 2
    finally:
        if run is not None:
            print('결과: '+str(run.file.resolve()), flush=True)
            print('터미널 로그 사본: '+str((run.folder/'terminal.log').resolve()), flush=True)
            run.close()


if __name__ == '__main__':
    sys.exit(main())
