#!/usr/bin/env bash
# Read-only model-list diagnostics; no generation, data writes, or config edits.
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
  echo '설치 폴더를 찾지 못했습니다. GENOS_CODE_ROOT에 설치 폴더를 지정하세요.' >&2
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
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / '02_BACKEND'))
try:
    if Path('.env').is_file():
        from dotenv import load_dotenv
        load_dotenv('.env', override=False)
    from semantic_runtime import genos
except Exception as exc:
    print('준비 실패:', type(exc).__name__)
    raise SystemExit(2)

secrets = [v for k, v in os.environ.items()
           if v and re.search(r'KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL', k, re.I)]

def safe_error(exc):
    # Only expose known transport-generated messages, never a response body.
    message = str(exc)
    patterns = [
        r'GENOS (?:llm|embed) HTTP [0-9]{3}',
        r'GENOS (?:llm|embed) request failed after [0-9]+ attempts: (?:HTTP [0-9]{3}|[A-Za-z]+Error|[A-Za-z]*Timeout)',
        r'GENOS (?:llm|embed) returned (?:invalid JSON|a non-object JSON response|an invalid model list)',
        r'GENOS (?:llm|embed) configured model is not advertised',
        r'GENOS (?:llm|embed) requires an explicit model when [0-9]+ models are advertised',
    ]
    if not any(re.fullmatch(p, message) for p in patterns):
        return type(exc).__name__ + ' (상세 메시지 숨김)'
    for secret in sorted(secrets, key=len, reverse=True):
        message = message.replace(secret, '[숨김]')
    return message

print('모델 목록 GET 조회만 수행합니다. 생성·임베딩·DB 호출은 하지 않습니다.')
print('키·응답 본문은 출력하지 않으며 파일·환경설정은 변경하지 않습니다.')
print('각 모델은 재시도 없이 연결 5초/읽기 15초 제한으로 확인합니다.')
failed = False
for kind in ('llm', 'embed'):
    print('\n[' + kind + ']', flush=True)
    try:
        target, configured = genos.from_env(kind)
        target = replace(target, max_retries=1, connect_timeout=5.0, read_timeout=15.0)
        genos.advertised_model(target, configured)
        print('PASS: 모델 목록 조회 및 모델 선택 성공')
    except genos.ServingError as exc:
        failed = True
        print('FAIL:', safe_error(exc))
    except Exception as exc:
        failed = True
        print('FAIL:', type(exc).__name__)
print('\nVDB는 이번 점검에서 제외합니다. PASS여도 실제 생성 성공을 뜻하지 않습니다.')
raise SystemExit(1 if failed else 0)
PY
