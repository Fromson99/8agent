#!/usr/bin/env bash
# 배포된 GenOS 코드 서빙의 단일 JSON 게이트웨이를 안전하게 호출한다.
#
#   export GENOS_CODE_URL='https://<host>/api/gateway/code_serving/<id>/json'
#   export GENOS_CODE_KEY='<코드 서빙 인증키>'
#   scripts/genos_call.sh ping
#   scripts/genos_call.sh health
#   scripts/genos_call.sh search '설명의무 근거'
#   scripts/genos_call.sh ask '신탁재산을 구분해야 하는 근거는?'
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
  file)
    [[ $# -eq 1 && -f "$1" ]] || { printf '사용법: %s file <payload.json>\n' "$0" >&2; exit 2; }
    payload="$(<"$1")"
    ;;
  *)
    printf '사용법: %s {ping|health|search <질문>|ask <질문>|file <payload.json>}\n' "$0" >&2
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
