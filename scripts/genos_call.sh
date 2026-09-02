#!/usr/bin/env bash
# 배포된 GenOS 코드 서빙의 단일 JSON 게이트웨이를 안전하게 호출한다.
#
#   export GENOS_CODE_URL='https://<host>/api/gateway/code_serving/<id>/json'
#   export GENOS_CODE_KEY='<코드 서빙 인증키>'
#   scripts/genos_call.sh ping
#   scripts/genos_call.sh health
#   scripts/genos_call.sh ls /mnt/8-agent/data
#   scripts/genos_call.sh search '설명의무 근거'
#   scripts/genos_call.sh search-vector '설명의무 근거'
#   scripts/genos_call.sh ask '신탁재산을 구분해야 하는 근거는?'
#   scripts/genos_call.sh upload '현장내규.pdf' '내규'
#   scripts/genos_call.sh report > report.json
#   scripts/genos_call.sh file payload.json
set -euo pipefail

url="${GENOS_CODE_URL:-}"
key="${GENOS_CODE_KEY:-}"
timeout="${GENOS_CALL_TIMEOUT:-300}"

[[ -n "$url" ]] || { printf '오류: GENOS_CODE_URL을 설정하세요.\n' >&2; exit 2; }
[[ -n "$key" ]] || { printf '오류: GENOS_CODE_KEY를 설정하세요.\n' >&2; exit 2; }

command="${1:-}"
shift || true

case "$command" in
  ping)
    payload='{"op":"ping"}'
    ;;
  health)
    payload='{"op":"call","method":"GET","path":"/health"}'
    ;;
  ls)
    path="${1:-/mnt/8-agent/data}"
    payload="$(python3 - "$path" <<'PY'
import json
import sys

print(json.dumps({"op": "ls", "path": sys.argv[1]}, ensure_ascii=False))
PY
)"
    ;;
  search)
    [[ $# -ge 1 ]] || { printf '사용법: %s search <질문>\n' "$0" >&2; exit 2; }
    payload="$(python3 - "$1" <<'PY'
import json
import sys

print(json.dumps({"op": "call", "method": "GET",
                  "path": "/v1/rag/search",
                  "params": {"q": sys.argv[1], "mode": "auto"}},
                 ensure_ascii=False))
PY
)"
    ;;
  search-vector)
    [[ $# -ge 1 ]] || { printf '사용법: %s search-vector <질문>\n' "$0" >&2; exit 2; }
    payload="$(python3 - "$1" <<'PY'
import json
import sys

print(json.dumps({"op": "call", "method": "GET",
                  "path": "/v1/rag/search",
                  "params": {"q": sys.argv[1], "mode": "vector"}},
                 ensure_ascii=False))
PY
)"
    ;;
  ask)
    [[ $# -ge 1 ]] || { printf '사용법: %s ask <질문>\n' "$0" >&2; exit 2; }
    payload="$(python3 - "$1" <<'PY'
import json
import sys

print(json.dumps({"op": "call", "method": "POST", "path": "/v1/rag/ask",
                  "json": {"question": sys.argv[1]}}, ensure_ascii=False))
PY
)"
    ;;
  upload)
    [[ $# -ge 1 && -f "$1" ]] || {
      printf '사용법: %s upload <파일> [폴더]\n' "$0" >&2; exit 2;
    }
    file="$1"
    folder="${2:-현장반입}"
    bytes="$(wc -c < "$file")"
    [[ "$bytes" -le 512000 ]] || {
      printf '오류: JSON 게이트웨이 업로드는 500KB 이하 카나리 파일만 허용합니다(%s bytes).\n' "$bytes" >&2
      exit 2
    }
    payload="$(python3 - "$file" "$folder" <<'PY'
import base64
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
print(json.dumps({
    "op": "upload",
    "filename": path.name,
    "file_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
    "form": {"folder": sys.argv[2], "use_llm": False},
}, ensure_ascii=False))
PY
)"
    ;;
  report)
    payload='{"op":"report"}'
    ;;
  file)
    [[ $# -eq 1 && -f "$1" ]] || { printf '사용법: %s file <payload.json>\n' "$0" >&2; exit 2; }
    payload="$(<"$1")"
    ;;
  *)
    printf '사용법: %s {ping|health|ls [경로]|search <질문>|search-vector <질문>|ask <질문>|upload <파일> [폴더]|report|file <payload.json>}\n' "$0" >&2
    exit 2
    ;;
esac

curl --fail-with-body --silent --show-error --location \
  --connect-timeout 10 --max-time "$timeout" \
  "$url" \
  --header 'Content-Type: application/json' \
  --header "Authorization: Bearer $key" \
  --data-binary "$payload"
printf '\n'
