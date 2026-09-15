#!/usr/bin/env bash
# Back up and patch GENOS transport, then run read-only model-list diagnostics.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
code_root="${GENOS_CODE_ROOT:-}"
if [[ -z "$code_root" ]]; then
  for candidate in "$script_dir" "$script_dir/.." "$PWD" /home/genos/DEV /workspace; do
    if [[ -f "$candidate/service.py" && -d "$candidate/02_BACKEND" ]]; then
      code_root="$(cd -- "$candidate" && pwd)"
      break
    fi
  done
fi
if [[ -z "$code_root" || ! -f "$code_root/service.py" ]]; then
  echo '설치 폴더를 찾지 못했습니다. GENOS_CODE_ROOT를 지정하세요.' >&2
  exit 2
fi
python_bin="$code_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "$python_bin" ]]; then
  echo 'Python3를 찾지 못했습니다.' >&2
  exit 2
fi
cd -- "$code_root"
"$python_bin" - "$@" <<'PATCHPY'
import ast
import os
import shlex
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

if sys.argv[1:] not in ([], ['--patch-only']):
    raise SystemExit('사용법: bash genos_requests_hotfix.sh [--patch-only]')
target = Path('02_BACKEND/semantic_runtime/genos.py')
if target.is_symlink() or not target.is_file():
    raise SystemExit('대상 genos.py가 없거나 심볼릭 링크입니다. 변경하지 않았습니다.')
original = target.read_bytes()
source = original.decode('utf-8')
tree = ast.parse(source)
matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'request_json']
if len(matches) != 1:
    raise SystemExit('지원하지 않는 코드 구조입니다. 변경하지 않았습니다.')
node = matches[0]
lines = source.splitlines(keepends=True)
block = ''.join(lines[node.lineno - 1:node.end_lineno])
for old, new in [('client.trust_env = False', 'client.trust_env = True'),
                 ('allow_redirects=False', 'allow_redirects=True')]:
    if block.count(old) == 1 and block.count(new) == 0:
        block = block.replace(old, new)
    elif block.count(old) == 0 and block.count(new) == 1:
        pass
    else:
        raise SystemExit('예상과 다른 전송 옵션입니다. 변경하지 않았습니다.')
updated = ''.join(lines[:node.lineno - 1]) + block + ''.join(lines[node.end_lineno:])
compile(updated, str(target), 'exec')
if updated == source:
    print('이미 적용된 패치입니다. 추가 변경 없음.')
else:
    if target.read_bytes() != original:
        raise SystemExit('코드가 작업 중 변경되었습니다. 중단합니다.')
    backup = target.with_name(target.name + '.before-requests-' +
                             datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') +
                             '-' + uuid.uuid4().hex[:8] + '.bak')
    with backup.open('xb') as handle:
        handle.write(original)
    shutil.copystat(target, backup)
    fd, name = tempfile.mkstemp(prefix='.genos-requests-', suffix='.tmp', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(updated.encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, target.stat().st_mode & 0o777)
        if target.read_bytes() != original:
            raise SystemExit('코드가 작업 중 변경되었습니다. 백업만 보존하고 중단합니다.')
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    print('패치 완료: 프록시/CA 환경설정 반영 및 리다이렉트 허용.')
    print('원본 백업:', backup.resolve())
    print('되돌리기: cp -- ' + shlex.quote(str(backup.resolve())) + ' ' + shlex.quote(str(target.resolve())))
print('URL·키·환경변수·데이터·Git·배포 설정은 변경하지 않았습니다.')
PATCHPY
if [[ $# -eq 1 ]]; then
  exit 0
fi
echo '이어서 모델 목록의 HTTP 응답을 확인합니다. FAIL이어도 코드 패치는 유지됩니다.'
"$python_bin" - <<'PY'
import os
import re
import signal
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

sys.path.insert(0, str(Path.cwd() / '02_BACKEND'))
try:
    if Path('.env').is_file():
        from dotenv import load_dotenv
        load_dotenv('.env', override=False)
    import requests
    from semantic_runtime import genos
except Exception as exc:
    print('준비 실패:', type(exc).__name__)
    raise SystemExit(2)

secrets = set()
for key, value in os.environ.items():
    if value and re.search(r'KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL', key, re.I):
        secrets.update((value, quote(value, safe=''), quote_plus(value)))

def scrub(value):
    text = str(value)
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+', r'\1 [REDACTED]', text)
    text = re.sub(r'''(?ix)(["']?(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|cookie|set-cookie)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)''', r'\1[REDACTED]', text)
    text = re.sub(r'(https?://)[^/\s@]+@', r'\1[REDACTED]@', text)
    text = re.sub(r'''(https?://[^\s?'"<>]+)\?[^\s'"<>]*''', r'\1?[REDACTED]', text)
    # Remove terminal escape/control characters from untrusted server content.
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127))

def show_exception(exc):
    pending, seen = [exc], set()
    while pending and len(seen) < 10:
        item = pending.pop(0)
        if id(item) in seen:
            continue
        seen.add(id(item))
        print(type(item).__name__ + ': ' + scrub(item)[:3000], flush=True)
        children = [getattr(item, '__cause__', None), getattr(item, '__context__', None),
                    getattr(item, 'reason', None), *getattr(item, 'args', ())]
        pending.extend(child for child in children if isinstance(child, BaseException))

def deadline(signum, frame):
    raise TimeoutError('diagnostic total time limit (40 seconds)')

signal.signal(signal.SIGALRM, deadline)
print('GET /models 상세 점검: LLM 생성·임베딩 생성·DB 호출 없음.', flush=True)
print('requests 기본 방식: 프록시/CA 환경설정 반영, 리다이렉트 허용, TLS 검증 유지.', flush=True)
print('비밀값은 가리지만 내부 주소/서버 메시지가 포함될 수 있으니 공유 전에 확인하세요.', flush=True)
failed = False
for kind in ('llm', 'embed'):
    print('\n[' + kind + ']', flush=True)
    received = False
    signal.alarm(40)
    try:
        target, configured = genos.from_env(kind)
        for value in target.headers.values():
            if value and value != 'application/json':
                secrets.add(value)
        print('GET ' + scrub(target.url('/models')), flush=True)
        with requests.Session() as client:
            client.trust_env = True
            with client.get(target.url('/models'), headers=target.headers,
                            timeout=(5, 15), allow_redirects=True, stream=True) as response:
                received = True
                print('HTTP:', response.status_code, flush=True)
                print('Content-Type:', scrub(response.headers.get('Content-Type', ''))[:200], flush=True)
                chunks, size, oversized = [], 0, False
                for chunk in response.iter_content(chunk_size=4096):
                    size += len(chunk)
                    if size > 32768:
                        oversized = True
                        break
                    chunks.append(chunk)
                if oversized:
                    print('응답 본문이 32KB를 넘어 출력하지 않습니다.')
                else:
                    body = b''.join(chunks).decode('utf-8', errors='replace')
                    print('응답 본문 (민감값 마스킹, 최대 3000자):')
                    print(scrub(body)[:3000] or '(빈 본문)')
                if not 200 <= response.status_code < 300:
                    failed = True
    except Exception as exc:
        failed = True
        print('응답 수신 후 처리 실패:' if received else 'HTTP 응답을 받기 전 실패 — GENOS 응답 본문 없음:')
        show_exception(exc)
    finally:
        signal.alarm(0)
print('\nHTTP 2xx여도 모델 선택·실제 생성·RAG 연결 성공까지 검증한 것은 아닙니다.')
raise SystemExit(1 if failed else 0)
PY
