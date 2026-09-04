#!/usr/bin/env bash
# 배포된 GenOS 코드 서빙을 환경변수만으로 단계별 점검한다.
#
#   export GENOS_CODE_URL='https://.../json'
#   read -rsp 'Code serving key: ' GENOS_CODE_KEY; export GENOS_CODE_KEY; echo
#   export GENOS_DATA_ROOT=/workspace/8-agent-runtime/data
#   bash scripts/genos_smoke.sh --all
#
# --all은 ping, health, 영속 데이터, 일반 검색, vector 검색, LLM 답변을 순서대로 호출한다.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
call="$here/genos_call.sh"
data_root="${GENOS_DATA_ROOT:-/workspace/8-agent-runtime/data}"
search_question="${GENOS_SMOKE_SEARCH:-설명의무의 법적 근거}"
ask_question="${GENOS_SMOKE_ASK:-신탁재산을 고유재산과 구분해야 하는 근거는?}"
with_search=0
with_vector=0
with_ask=0

usage() {
  cat <<'EOF'
사용법: bash scripts/genos_smoke.sh [--search] [--vector] [--ask] [--all]

필수 환경변수: GENOS_CODE_URL, GENOS_CODE_KEY
선택 환경변수: GENOS_DATA_ROOT, GENOS_SMOKE_SEARCH, GENOS_SMOKE_ASK,
               GENOS_CALL_TIMEOUT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --search) with_search=1 ;;
    --vector) with_vector=1 ;;
    --ask) with_ask=1 ;;
    --all) with_search=1; with_vector=1; with_ask=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

[[ -n "${GENOS_CODE_URL:-}" ]] || { echo '오류: GENOS_CODE_URL을 설정하세요.' >&2; exit 2; }
[[ -n "${GENOS_CODE_KEY:-}" ]] || { echo '오류: GENOS_CODE_KEY를 설정하세요.' >&2; exit 2; }

run() {
  local name="$1"
  shift
  printf '\n===== %s =====\n' "$name"
  "$call" "$@"
}

run '1/6 코드 서빙 연결' ping
run '2/6 애플리케이션 health' health
run '3/6 영속 데이터 경로' ls "$data_root"

if [[ "$with_search" == 1 ]]; then
  run '4/6 일반 RAG 검색' search "$search_question"
fi
if [[ "$with_vector" == 1 ]]; then
  run '5/6 Vector DB 검색' search-vector "$search_question"
fi
if [[ "$with_ask" == 1 ]]; then
  run '6/6 LLM 답변 생성' ask "$ask_question"
fi

printf '\n완료. Vector DB는 5/6 응답의 vector_hits 또는 refs, LLM은 6/6의 answer와 refs를 확인하세요.\n'
