#!/usr/bin/env bash
# Confirm one actual LLM reply before patching the connection check.
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
"$python_bin" - <<'PY'
import ast
import hashlib
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / '02_BACKEND'))
try:
    if Path('.env').is_file():
        from dotenv import load_dotenv
        load_dotenv('.env', override=False)
    import requests
    from semantic_runtime import genos
except ImportError:
    raise SystemExit('필수 패키지가 없습니다. requirements-serving.txt 설치 상태를 확인하세요. 변경 없음.')

REPLACEMENT = json.loads("\"def check(\\n    kind: str, *, execute: bool = False, _vector_sink: list[float] | None = None\\n) -> dict[str, Any]:\\n    \\\"\\\"\\\"Resolve the advertised API model, then optionally test a short reply.\\\"\\\"\\\"\\n\\n    started = time.monotonic()\\n    result: dict[str, Any] = {\\\"component\\\": kind, \\\"generation_requested\\\": execute}\\n    try:\\n        target, configured = from_env(kind)\\n        model = advertised_model(target, configured)\\n        result.update(model=model, models=\\\"PASS\\\")\\n        if execute:\\n            payload = (\\n                {\\n                    \\\"model\\\": model,\\n                    \\\"messages\\\": [{\\\"role\\\": \\\"user\\\", \\\"content\\\": \\\"Reply with OK.\\\"}],\\n                    \\\"max_tokens\\\": 256,\\n                    \\\"temperature\\\": 0,\\n                    \\\"stream\\\": False,\\n                    \\\"chat_template_kwargs\\\": {\\\"enable_thinking\\\": False},\\n                }\\n                if kind == \\\"llm\\\"\\n                else {\\\"model\\\": model, \\\"input\\\": [\\\"GENOS connectivity check\\\"]}\\n            )\\n            value = request_json(\\n                target,\\n                \\\"/chat/completions\\\" if kind == \\\"llm\\\" else \\\"/embeddings\\\",\\n                payload,\\n            )\\n            if kind == \\\"llm\\\":\\n                choice = value[\\\"choices\\\"][0]\\n                content = choice[\\\"message\\\"].get(\\\"content\\\")\\n                result[\\\"finish_reason\\\"] = choice.get(\\\"finish_reason\\\")\\n                if result[\\\"finish_reason\\\"] == \\\"length\\\":\\n                    raise ServingError(\\\"GENOS llm generation hit output token limit\\\")\\n                if not isinstance(content, str) or not content.strip():\\n                    raise ServingError(\\\"GENOS llm returned empty content\\\")\\n                result[\\\"response_chars\\\"] = len(content)\\n                result[\\\"usage\\\"] = value.get(\\\"usage\\\") or {}\\n            else:\\n                vector = value[\\\"data\\\"][0][\\\"embedding\\\"]\\n                if (\\n                    not isinstance(vector, list)\\n                    or not vector\\n                    or any(\\n                        type(item) not in {int, float} or not math.isfinite(item)\\n                        for item in vector\\n                    )\\n                ):\\n                    raise ServingError(\\\"GENOS embed returned an invalid vector\\\")\\n                if _vector_sink is not None:\\n                    _vector_sink.extend(float(item) for item in vector)\\n                result[\\\"dimensions\\\"] = len(vector)\\n            result[\\\"inference\\\"] = \\\"PASS\\\"\\n        else:\\n            result[\\\"inference\\\"] = \\\"NOT_RUN\\\"\\n        result[\\\"status\\\"] = \\\"PASS\\\"\\n    except Exception as exc:\\n        result.update(status=\\\"FAIL\\\", error=type(exc).__name__)\\n        if isinstance(exc, ServingError):\\n            # Transport messages contain classifications, never provider bodies.\\n            result[\\\"detail\\\"] = str(exc)\\n    result[\\\"seconds\\\"] = round(time.monotonic() - started, 3)\\n    return result\\n\"")
ALLOWED = ["432a733ea7cedf8da74d2a21eb852124ebdcf8198615e44b7c85380bfddb253f","48649fe5c325e0291593f6906e3de2be4cd9c189d6a99cb4f4664e7636f201db","eae23e52fa247b1371517fbdb0ca5abc895a14bd10bc97009e7814d801683f4e"]
target_file = Path('02_BACKEND/semantic_runtime/genos.py')
if target_file.is_symlink() or not target_file.is_file():
    raise SystemExit('패치 대상이 없거나 심볼릭 링크입니다. 변경 없음.')
original = target_file.read_bytes()
code = original.decode('utf-8')
lines = code.splitlines(keepends=True)
nodes = [n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name == 'check']
if len(nodes) != 1:
    raise SystemExit('지원하지 않는 코드 구조입니다. 변경 없음.')
node = nodes[0]
old_check = ''.join(lines[node.lineno - 1:node.end_lineno])
if old_check != REPLACEMENT and hashlib.sha256(old_check.encode()).hexdigest() not in ALLOWED:
    raise SystemExit('알려진 배포본과 다른 check 함수입니다. 덮어쓰지 않았습니다.')

secrets = [v for k, v in os.environ.items()
           if v and re.search(r'KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL', k, re.I)]
def scrub(value):
    text = str(value)
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+', r'\1 [REDACTED]', text)
    text = re.sub(r'''(?ix)(["']?(?:authorization|api[_-]?key|access[_-]?token|token|password|secret|cookie|set-cookie)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)''', r'\1[REDACTED]', text)
    text = re.sub(r'(https?://)[^/\s@]+@', r'\1[REDACTED]@', text)
    text = re.sub(r'''(https?://[^\s?'"<>]+)\?[^\s'"<>]*''', r'\1?[REDACTED]', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127))

def stop(message):
    print(message, flush=True)
    raise SystemExit(1)

def deadline(signum, frame):
    raise TimeoutError('55 second overall request deadline')

print('LLM 목록 조회 + 짧은 답변 생성 1회. 임베딩/DB/데이터 처리 없음.', flush=True)
print('서빙 ID·URL·키는 그대로 사용하며 모델 값은 서버 목록에서 선택합니다.', flush=True)
print('생성 성공이 확인되어야 check 함수만 백업 후 패치합니다.', flush=True)
signal.signal(signal.SIGALRM, deadline)
signal.alarm(55)
try:
    target, configured = genos.from_env('llm')
    for val in target.headers.values():
        if val and val != 'application/json':
            secrets.append(val)
    print('호출 경로:', scrub(target.url('/models')), flush=True)
    transport_node = next(n for n in ast.parse(code).body
                          if isinstance(n, ast.FunctionDef) and n.name == 'request_json')
    transport_code = ast.get_source_segment(code, transport_node)
    is_httpx = 'import httpx' in transport_code
    if is_httpx:
        import httpx
        session = httpx.Client(trust_env=True, follow_redirects=False)
    else:
        session = requests.Session()
        session.trust_env = 'client.trust_env = False' not in transport_code
    print('설치된 전송 방식:', 'httpx' if is_httpx else 'requests', flush=True)
    with session as client:
        def request(method, path, body=None, read_timeout=15):
            options = {'headers': target.headers, 'json': body}
            if is_httpx:
                options.update(timeout=httpx.Timeout(read_timeout, connect=5), follow_redirects=False)
            else:
                options.update(timeout=(5, read_timeout),
                               allow_redirects='allow_redirects=True' in transport_code)
            return client.request(method, target.url(path), **options)
        response = request('GET', '/models')
        print('모델 목록 HTTP:', response.status_code, flush=True)
        if response.status_code != 200:
            print(scrub(response.text)[:4000])
            stop('모델 조회 실패. 코드 변경 없음.')
        listing = response.json()
        ids = [row['id'] for row in listing.get('data', [])
               if isinstance(row, dict) and isinstance(row.get('id'), str) and row['id']]
        if configured:
            if configured not in ids:
                stop('설정한 MODEL이 서버 목록에 없습니다. 서빙 ID와 요청 본문의 model은 서로 다른 값입니다. 코드 변경 없음.')
            model = configured
        elif len(ids) == 1:
            model = ids[0]
        else:
            stop('모델 자동 선택 불가. 실제 목록의 모델을 GENOS_QWEN_MODEL 등에 명시해야 합니다. 코드 변경 없음.')
        body = {
            'model': model,
            'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 256, 'temperature': 0, 'stream': False,
            'chat_template_kwargs': {'enable_thinking': False},
        }
        print('실제 답변 생성 요청 중 (최대 45초)...', flush=True)
        response = request('POST', '/chat/completions', body, read_timeout=45)
        print('답변 생성 HTTP:', response.status_code, flush=True)
        if response.status_code != 200:
            print('서버 오류 본문 (민감값 마스킹):', scrub(response.text)[:4000])
            stop('생성 요청이 거절됐습니다. 원인 미확정 상태에서 코드는 변경하지 않았습니다.')
        data = response.json()
        choices = data.get('choices') or []
        choice = choices[0] if choices else {}
        message = choice.get('message') or {}
        content = message.get('content')
        finish = choice.get('finish_reason')
        print('finish_reason:', scrub(finish), flush=True)
        if finish in ('length', 'content_filter') or not isinstance(content, str) or not content.strip():
            reasoning = message.get('reasoning_content') or ''
            print('content 길이:', len(content) if isinstance(content, str) else 0)
            print('reasoning_content 길이:', len(reasoning) if isinstance(reasoning, str) else 0)
            print('응답 본문 (민감값 마스킹):', scrub(response.text)[:4000])
            stop('유효한 답변이 없습니다. length는 출력 상한 도달, reasoning만 있으면 추론만 생성된 상태입니다. 코드 변경 없음.')
        print('LLM 실제 답변:', scrub(content)[:1000], flush=True)
except Exception as exc:
    print('실패:', type(exc).__name__, scrub(exc)[:3000])
    stop('코드 변경 없음. 위 오류 결과를 확인해야 합니다.')
finally:
    signal.alarm(0)

# Persist only the tested request shape in check(); leave transport and URLs alone.
if old_check == REPLACEMENT:
    print('LLM 답변 생성 성공. 이 점검 패치는 이미 적용되어 있습니다.')
    raise SystemExit(0)
updated = ''.join(lines[:node.lineno - 1]) + REPLACEMENT + ''.join(lines[node.end_lineno:])
compile(updated, str(target_file), 'exec')
if target_file.read_bytes() != original:
    stop('작업 중 파일이 바뀌어 패치하지 않았습니다.')
backup = target_file.with_name(target_file.name + '.before-reply-' + uuid.uuid4().hex[:12] + '.bak')
with backup.open('xb') as handle:
    handle.write(original)
shutil.copystat(target_file, backup)
fd, name = tempfile.mkstemp(prefix='.genos-reply-', dir=target_file.parent)
temp = Path(name)
try:
    with os.fdopen(fd, 'wb') as handle:
        handle.write(updated.encode('utf-8'))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, target_file.stat().st_mode & 0o777)
    if target_file.read_bytes() != original:
        stop('작업 중 파일이 바뀌어 백업만 보존하고 중단합니다.')
    os.replace(temp, target_file)
finally:
    if temp.exists():
        temp.unlink()
print('답변 생성 확인 후 check 함수 패치 완료. 원본 백업:', backup.resolve())
print('모델 자동 선택, 출력 상한 256, 추론 비활성화 요청, 실패 분류 표시를 적용했습니다.')
print('URL·포트·서빙 ID·키·전송 함수·데이터는 변경하지 않았습니다.')
print('임베딩 Invalid token은 별개이며 GENOS_EMBED_KEY 확인이 필요합니다.')
print('기존 실행 프로세스는 재시작, 별도 코드 서빙은 수정 커밋의 재배포가 필요합니다.')
PY
