#!/usr/bin/env bash
# Read-only configuration report. No model or database calls.
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
if [[ -z "$code_root" ]]; then
  echo '설치 폴더를 찾지 못했습니다. GENOS_CODE_ROOT에 service.py가 있는 폴더를 지정하세요.' >&2
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
"$python_bin" - "$code_root" <<'PY'
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

root = Path(sys.argv[1]).resolve()
env_path = root / '.env'
file_values = {}
if env_path.is_file():
    try:
        from dotenv import dotenv_values
        file_values = dotenv_values(env_path)
    except ImportError:
        print('주의: python-dotenv가 없어 .env를 확인하지 못했습니다. 환경변수만 확인합니다.')
    except Exception as exc:
        print('주의: .env 읽기 실패:', type(exc).__name__)

names = [
    'GENOS_BASE_URL', 'GENOS_LLM_PROFILE',
    'GENOS_LLM_URL', 'GENOS_LLM_SERVING_ID', 'GENOS_LLM_MODEL',
    'GENOS_LLM_KEY', 'GENOS_LLM_API_PREFIX',
    'GENOS_EMBED_URL', 'GENOS_EMBED_SERVING_ID', 'GENOS_EMBED_MODEL',
    'GENOS_EMBED_KEY', 'GENOS_EMBED_API_PREFIX',
    'SEMANTIC_LLM_ENDPOINT', 'SEMANTIC_LLM_API_KEY', 'SEMANTIC_LLM_API_PREFIX',
    'GENOS_DATA_ROOT', 'GENOS_RUNTIME_DIR', 'RAG_VECTOR_STORE', 'RAG_VECTOR_BACKEND',
]

def effective(name):
    if name in os.environ:
        return os.environ[name], '환경변수'
    if name in file_values:
        return file_values[name] or '', '.env'
    return '', '없음'

profile = effective('GENOS_LLM_PROFILE')[0].strip().upper() or 'QWEN'
profiles = ['QWEN', 'GEMMA']
if re.fullmatch(r'[A-Z0-9_]+', profile) and profile not in profiles:
    profiles.append(profile)
for prefix in profiles:
    names.extend('GENOS_' + prefix + '_' + suffix for suffix in ('SERVING_ID', 'MODEL', 'KEY'))

# Known credentials are scrubbed even if mistakenly copied into another field.
secrets = set()
for mapping in (file_values, os.environ):
    for key, value in mapping.items():
        if value and re.search(r'(KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL)', key, re.I):
            secrets.add(str(value))

def safe(name, value):
    if not value.strip():
        return '미설정/빈 값'
    if re.search(r'(KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL)', name, re.I):
        return '설정됨 (값 숨김)'
    if name.endswith(('_URL', '_ENDPOINT')):
        try:
            url = urlsplit(value.strip())
            if url.scheme not in ('http', 'https') or not url.hostname:
                return 'URL 형식 오류 (값 숨김)'
            # Paths can also contain API keys. Only print useful gateway routes.
            path = url.path.rstrip('/')
            match = re.fullmatch(r'(/api/gateway/rep/serving/[0-9]+)(/v1)?(/models|/chat/completions|/embeddings)?', path)
            visible_path = path if match or path in ('', '/v1', '/models', '/chat/completions', '/embeddings') else '/[경로 숨김]'
            host = '[' + url.hostname + ']' if ':' in url.hostname else url.hostname
            value = url.scheme + '://' + host + (':' + str(url.port) if url.port else '') + visible_path
            if url.username or url.password or url.query or url.fragment:
                value += ' [인증정보·쿼리 숨김]'
        except ValueError:
            return 'URL 형식 오류 (값 숨김)'
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, '[비밀값 숨김]')
    return value.replace('\n', ' ').replace('\r', ' ')

print('설치 폴더:', root)
print('.env 파일:', '있음' if env_path.is_file() else '없음')
print('우선순위: 현재 프로세스 환경변수 > .env (빈 환경변수도 우선합니다)')
print('이 점검은 모델·DB를 호출하거나 설정을 변경하지 않습니다.\n')
for name in names:
    value, source = effective(name)
    print(f'{name} = {safe(name, value)} [{source}]')

print('\n빈 환경변수가 .env 값을 가리는 항목:')
shadowed = [name for name in names if name in os.environ and not os.environ[name].strip() and file_values.get(name)]
print(', '.join(shadowed) if shadowed else '없음')
print('\nLLM은 선택한 프로필의 SERVING_ID/KEY/MODEL이 일반 GENOS_LLM_*보다 우선합니다.')
print('CONFIGURED 여부와 실제 접속 성공은 별개입니다. 위 결과를 공유해 주세요.')
PY
