#!/usr/bin/env bash
# Patch to integration-branch gateway transport; preserve URL, keys and data.
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
import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

if sys.argv[1:] not in ([], ['--patch-only']):
    raise SystemExit('사용법: bash genos_branch_hotfix.sh [--patch-only]')
try:
    import httpx
except ImportError:
    raise SystemExit('httpx가 없습니다. requirements-serving.txt의 의존성 설치 후 다시 실행하세요. 변경 없음.')
PAYLOAD = json.loads("{\"endpoint\":{\"source\":\"def endpoint(\\n    base_url: str,\\n    *,\\n    serving_id: str = \\\"\\\",\\n    token: str = \\\"\\\",\\n    user_id: str = \\\"\\\",\\n    label: str = \\\"GENOS\\\",\\n    connect_timeout: float = 5.0,\\n    read_timeout: float = 120.0,\\n    max_retries: int = 3,\\n    api_prefix: str | None = None,\\n) -> Endpoint:\\n    \\\"\\\"\\\"Build an endpoint from either a direct serving URL or a GENOS base URL.\\\"\\\"\\\"\\n\\n    raw = base_url.strip().rstrip(\\\"/\\\")\\n    if serving_id:\\n        if not serving_id.isdigit():\\n            raise ValueError(\\\"GENOS serving ID must be numeric\\\")\\n        raw += _SERVING_PATH.format(serving_id=serving_id)\\n    headers = {\\\"Content-Type\\\": \\\"application/json\\\"}\\n    if token:\\n        headers[\\\"Authorization\\\"] = f\\\"Bearer {token}\\\"\\n    if user_id:\\n        headers[\\\"x-genos-user-id\\\"] = user_id\\n    return Endpoint(\\n        root=_canonical_root(raw, api_prefix if api_prefix is not None else (\\\"none\\\" if serving_id else \\\"/v1\\\")),\\n        label=label,\\n        connect_timeout=connect_timeout,\\n        read_timeout=read_timeout,\\n        max_retries=max_retries,\\n        headers=headers,\\n    )\\n\",\"allowed\":[\"8e943f0c7b62ba6a73d650483c7edb6664247ef3a4f9db8808c82023c616fbe1\",\"bfd49e5c56e42d5161026a14d4ab581133fefc0c2a4c073e08d943d5763ba5a0\"]},\"from_env\":{\"source\":\"def from_env(kind: str) -> tuple[Endpoint, str]:\\n    \\\"\\\"\\\"Resolve the LLM or embedding endpoint and configured model from env.\\\"\\\"\\\"\\n\\n    if kind not in {\\\"llm\\\", \\\"embed\\\"}:\\n        raise ValueError(\\\"kind must be llm or embed\\\")\\n    prefix = \\\"GENOS_LLM\\\" if kind == \\\"llm\\\" else \\\"GENOS_EMBED\\\"\\n    profile = _profile() if kind == \\\"llm\\\" else \\\"\\\"\\n\\n    def value(suffix: str) -> str:\\n        profiled = os.environ.get(f\\\"GENOS_{profile}_{suffix}\\\", \\\"\\\") if profile else \\\"\\\"\\n        return (profiled or os.environ.get(f\\\"{prefix}_{suffix}\\\", \\\"\\\")).strip()\\n\\n    direct = os.environ.get(f\\\"{prefix}_URL\\\", \\\"\\\").strip()\\n    serving_id = value(\\\"SERVING_ID\\\")\\n    base = direct or os.environ.get(\\\"GENOS_BASE_URL\\\", \\\"\\\").strip()\\n    if not base:\\n        raise ValueError(f\\\"{prefix} endpoint is not configured\\\")\\n    if not direct and not serving_id:\\n        raise ValueError(f\\\"{prefix} serving ID is not configured\\\")\\n    target = endpoint(\\n        base,\\n        serving_id=\\\"\\\" if direct else serving_id,\\n        token=value(\\\"KEY\\\"),\\n        user_id=(\\n            os.environ.get(\\\"GENOS_USER_ID\\\", \\\"\\\").strip()\\n            if kind == \\\"llm\\\"\\n            else os.environ.get(\\\"GENOS_EMBED_TENANT_ID\\\", \\\"\\\").strip()\\n        ),\\n        label=f\\\"GENOS {kind}\\\",\\n        read_timeout=float(os.environ.get(f\\\"{prefix}_TIMEOUT\\\", \\\"120\\\")),\\n        max_retries=int(os.environ.get(f\\\"{prefix}_MAX_RETRIES\\\", \\\"3\\\")),\\n        # Integration branch gateways expose /models and /chat/completions\\n        # directly. Legacy *_API_PREFIX applies only to direct model servers.\\n        api_prefix=(\\n            os.environ.get(\\\"GENOS_GATEWAY_API_PREFIX\\\", \\\"none\\\")\\n            if not direct or \\\"/api/gateway/rep/serving/\\\" in urlsplit(base).path\\n            else os.environ.get(f\\\"{prefix}_API_PREFIX\\\", \\\"/v1\\\")\\n        ),\\n    )\\n    return target, value(\\\"MODEL\\\")\\n\",\"allowed\":[\"58fc3cf0a783e9c649694bd4f189a101ee95a7da575c707a6fab8743db48a23d\",\"e9e0a3c2db2c6c24cf8d7c19e443f0c6fb3bb853534990b22c00c609149a294f\"]},\"request_json\":{\"source\":\"def request_json(\\n    target: Endpoint,\\n    path: str,\\n    payload: dict[str, Any] | None = None,\\n    *,\\n    session=None,\\n) -> dict[str, Any]:\\n    \\\"\\\"\\\"Issue one GET/POST request, retrying only network, 429, and transient 5xx.\\\"\\\"\\\"\\n\\n    import httpx\\n\\n    owned = session is None\\n    client = session if session is not None else httpx.Client(trust_env=True, follow_redirects=False)\\n    last = \\\"\\\"\\n    last_exception = None\\n    try:\\n        for attempt in range(1, target.max_retries + 1):\\n            try:\\n                response = client.request(\\n                    \\\"GET\\\" if payload is None else \\\"POST\\\",\\n                    target.url(path),\\n                    headers=target.headers,\\n                    json=payload,\\n                    timeout=httpx.Timeout(target.read_timeout, connect=target.connect_timeout),\\n                    follow_redirects=False,\\n                )\\n            except httpx.RequestError as exc:\\n                last = type(exc).__name__\\n                last_exception = exc\\n            else:\\n                if 200 <= response.status_code < 300:\\n                    try:\\n                        value = response.json()\\n                    except ValueError as exc:\\n                        raise ServingError(f\\\"{target.label} returned invalid JSON\\\") from exc\\n                    if not isinstance(value, dict):\\n                        raise ServingError(f\\\"{target.label} returned a non-object JSON response\\\")\\n                    return value\\n                if response.status_code not in RETRY_STATUS:\\n                    raise ServingError(f\\\"{target.label} HTTP {response.status_code}\\\")\\n                last = f\\\"HTTP {response.status_code}\\\"\\n                last_exception = None\\n            if attempt < target.max_retries:\\n                time.sleep(2.0 * attempt)\\n        raise ServingError(\\n            f\\\"{target.label} request failed after {target.max_retries} attempts: {last}\\\"\\n        ) from last_exception\\n    finally:\\n        if owned:\\n            client.close()\\n\",\"allowed\":[\"3c30267156978ddc6f4b238bfecea5115cce8a94b04cb5d5c68120259eebc485\",\"43e310c0a1dd3dbdc5d63122838224b80a74ffe76d67e02bfbb6a8ed8b187c07\",\"6ec699809dac70fe2d565da15d9432c5fe502b4fed1c8e9d6c206ff39d869def\",\"7d23ed69dcb56d68f6e74761515f3138a4b90cc513634c99576d8af0ca6415e7\",\"cd59946a5aa435d21737af81d6d5ff653d2ddc9dafcb22953bdad3c18b5cb3dd\"]},\"check\":{\"source\":\"def check(\\n    kind: str, *, execute: bool = False, _vector_sink: list[float] | None = None\\n) -> dict[str, Any]:\\n    \\\"\\\"\\\"Model-list diagnostic, or tiny inference (gateway POST skips discovery).\\\"\\\"\\\"\\n\\n    started = time.monotonic()\\n    result: dict[str, Any] = {\\\"component\\\": kind, \\\"generation_requested\\\": execute}\\n    try:\\n        target, configured = from_env(kind)\\n        if execute and \\\"/api/gateway/rep/serving/\\\" in urlsplit(target.root).path:\\n            # Match the integration branch: serving ID routes the request;\\n            # model discovery is a separate diagnostic, not a POST prerequisite.\\n            model = configured or \\\"genos\\\"\\n            result.update(model=model, models=\\\"NOT_RUN\\\")\\n        else:\\n            model = advertised_model(target, configured)\\n            result.update(model=model, models=\\\"PASS\\\")\\n        if execute:\\n            payload = (\\n                {\\n                    \\\"model\\\": model,\\n                    \\\"messages\\\": [{\\\"role\\\": \\\"user\\\", \\\"content\\\": \\\"Reply with OK.\\\"}],\\n                    \\\"max_tokens\\\": 32,\\n                    \\\"temperature\\\": 0,\\n                    \\\"stream\\\": False,\\n                    \\\"chat_template_kwargs\\\": {\\\"enable_thinking\\\": False},\\n                }\\n                if kind == \\\"llm\\\"\\n                else {\\\"model\\\": model, \\\"input\\\": [\\\"GENOS connectivity check\\\"]}\\n            )\\n            value = request_json(\\n                target,\\n                \\\"/chat/completions\\\" if kind == \\\"llm\\\" else \\\"/embeddings\\\",\\n                payload,\\n            )\\n            if kind == \\\"llm\\\":\\n                content = value[\\\"choices\\\"][0][\\\"message\\\"][\\\"content\\\"]\\n                if not isinstance(content, str) or not content.strip():\\n                    raise ServingError(\\\"GENOS llm returned empty content\\\")\\n                result[\\\"response_chars\\\"] = len(content)\\n                result[\\\"usage\\\"] = value.get(\\\"usage\\\") or {}\\n            else:\\n                vector = value[\\\"data\\\"][0][\\\"embedding\\\"]\\n                if (\\n                    not isinstance(vector, list)\\n                    or not vector\\n                    or any(\\n                        type(item) not in {int, float} or not math.isfinite(item)\\n                        for item in vector\\n                    )\\n                ):\\n                    raise ServingError(\\\"GENOS embed returned an invalid vector\\\")\\n                if _vector_sink is not None:\\n                    _vector_sink.extend(float(item) for item in vector)\\n                result[\\\"dimensions\\\"] = len(vector)\\n            result[\\\"inference\\\"] = \\\"PASS\\\"\\n        else:\\n            result[\\\"inference\\\"] = \\\"NOT_RUN\\\"\\n        result[\\\"status\\\"] = \\\"PASS\\\"\\n    except Exception as exc:\\n        result.update(status=\\\"FAIL\\\", error=type(exc).__name__)\\n    result[\\\"seconds\\\"] = round(time.monotonic() - started, 3)\\n    return result\\n\",\"allowed\":[\"432a733ea7cedf8da74d2a21eb852124ebdcf8198615e44b7c85380bfddb253f\",\"48649fe5c325e0291593f6906e3de2be4cd9c189d6a99cb4f4664e7636f201db\",\"eae23e52fa247b1371517fbdb0ca5abc895a14bd10bc97009e7814d801683f4e\"]}}")
target = Path('02_BACKEND/semantic_runtime/genos.py')
if target.is_symlink() or not target.is_file():
    raise SystemExit('대상 genos.py가 없거나 심볼릭 링크입니다. 변경 없음.')
original = target.read_bytes()
source = original.decode('utf-8')
lines = source.splitlines(keepends=True)
nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in PAYLOAD]
if len(nodes) != len(PAYLOAD) or len({n.name for n in nodes}) != len(PAYLOAD):
    raise SystemExit('지원하지 않는 코드 구조입니다. 변경 없음.')
# Verify every target BEFORE writing any file. Preserve all unrelated functions.
for node in nodes:
    segment = ''.join(lines[node.lineno - 1:node.end_lineno])
    if hashlib.sha256(segment.encode()).hexdigest() not in PAYLOAD[node.name]['allowed']:
        raise SystemExit('알려진 배포본과 다른 함수입니다: ' + node.name + '. 변경 없음.')
for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
    lines[node.lineno - 1:node.end_lineno] = [PAYLOAD[node.name]['source']]
updated = ''.join(lines)
compile(updated, str(target), 'exec')
if updated == source:
    print('브랜치 패치가 이미 적용되어 있습니다. 추가 변경 없음.')
else:
    if target.read_bytes() != original:
        raise SystemExit('작업 중 코드가 변경되었습니다. 변경 없음.')
    backup = target.with_name(target.name + '.before-branch-' +
                             datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') +
                             '-' + uuid.uuid4().hex[:8] + '.bak')
    with backup.open('xb') as handle:
        handle.write(original)
    shutil.copystat(target, backup)
    fd, name = tempfile.mkstemp(prefix='.genos-branch-', suffix='.tmp', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(updated.encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, target.stat().st_mode & 0o777)
        if target.read_bytes() != original:
            raise SystemExit('작업 중 코드가 변경되었습니다. 백업만 보존하고 중단합니다.')
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    print('브랜치 패치 완료: 게이트웨이 /v1 자동 추가 제거, httpx 전송, 직접 생성 호출.')
    print('원본 백업:', backup.resolve())
    print('되돌리기: cp -- ' + shlex.quote(str(backup.resolve())) + ' ' + shlex.quote(str(target.resolve())))
print('URL·포트·키·환경변수·데이터·Git·배포 설정은 변경하지 않았습니다.')
print('게이트웨이에는 기존 GENOS_LLM_API_PREFIX/GENOS_EMBED_API_PREFIX 대신')
print('GENOS_GATEWAY_API_PREFIX(기본 none)가 적용됩니다. 직결 주소 설정은 유지합니다.')
PATCHPY
if [[ $# -eq 1 ]]; then
  exit 0
fi
echo '이어서 httpx로 모델 목록만 조회합니다. FAIL이어도 코드 패치는 유지됩니다.'
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
    import httpx
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
print('integration 브랜치 방식: httpx, 프록시/CA 환경설정 반영, 리다이렉트 미추적, TLS 검증 유지.', flush=True)
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
        with httpx.Client(trust_env=True, follow_redirects=False) as client:
            with client.stream('GET', target.url('/models'), headers=target.headers,
                               timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as response:
                received = True
                print('HTTP:', response.status_code, flush=True)
                print('Content-Type:', scrub(response.headers.get('Content-Type', ''))[:200], flush=True)
                chunks, size, oversized = [], 0, False
                for chunk in response.iter_bytes(chunk_size=4096):
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
