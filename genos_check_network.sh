#!/usr/bin/env bash
# Read-only DNS/TCP diagnostics. Uses only GENOS_BASE_URL from this shell.
set -euo pipefail
python_bin="$(command -v python3 || true)"
if [[ -z "$python_bin" ]]; then
  echo 'Python3를 찾지 못했습니다.' >&2
  exit 2
fi
"$python_bin" - <<'PY'
import os
import signal
import socket
from urllib.parse import urlsplit

def deadline(signum, frame):
    raise TimeoutError('diagnostic deadline')

signal.signal(signal.SIGALRM, deadline)
print('현재 터미널의 GENOS_BASE_URL로 DNS와 TCP 연결만 확인합니다.', flush=True)
print('키·URL·IP는 출력하지 않고 파일이나 설정은 변경하지 않습니다.', flush=True)
try:
    u = urlsplit(os.environ.get('GENOS_BASE_URL', '').strip())
    if (u.scheme not in ('http', 'https') or not u.hostname
            or u.username or u.password or u.query or u.fragment):
        raise ValueError('invalid base URL')
    port = u.port or (443 if u.scheme == 'https' else 80)
except ValueError:
    print('CONFIG: FAIL — GENOS_BASE_URL이 없거나 올바른 HTTP(S) URL이 아닙니다.')
    raise SystemExit(2)

signal.alarm(15)
try:
    socket.getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    print('DNS: PASS', flush=True)
except OSError as exc:
    print(f'DNS: FAIL ({type(exc).__name__}, errno={exc.errno})')
    raise SystemExit(1)
finally:
    signal.alarm(0)

signal.alarm(30)
try:
    with socket.create_connection((u.hostname, port), timeout=5):
        print('TCP 포트 연결: PASS', flush=True)
except OSError as exc:
    print(f'TCP 포트 연결: FAIL ({type(exc).__name__}, errno={exc.errno})')
    raise SystemExit(1)
finally:
    signal.alarm(0)
print('DNS/TCP 성공입니다. HTTPS 인증서·인증키·모델 API 성공은 별도 확인이 필요합니다.')
PY
