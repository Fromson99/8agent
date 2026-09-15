#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash 06_TOOLS/COMMANDS/genos_prepare_code_only_git.sh [--fresh]

Environment:
  GENOS_CODE_ROOT  Code root (default: current directory)
  GENOS_GIT_URL    origin URL, required only when origin is not already set
  GENOS_DATA_ROOT  Persistent data root used to keep a recoverable .git backup

Default mode preserves existing Git history and prepares a code-only index.
--fresh moves existing .git metadata to the ignored persistent data area,
creates a clean main branch, and then prepares the code-only index. It never
deletes working files, commits, pushes, or force-pushes.
EOF
}

fresh=0
case "${1:-}" in
  "") ;;
  --fresh) fresh=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

code_root="${GENOS_CODE_ROOT:-$PWD}"
code_root="$(cd "$code_root" && pwd -P)"
data_root="${GENOS_DATA_ROOT:-$code_root/GENOS_DATA}"

if [[ ! -f "$code_root/service.py" || ! -f "$code_root/requirements-serving.txt" ]]; then
  echo "FAIL: service.py와 requirements-serving.txt가 있는 코드 루트에서 실행하세요." >&2
  echo "확인된 경로: $code_root" >&2
  exit 1
fi

cd "$code_root"

origin_url="${GENOS_GIT_URL:-}"
if git rev-parse --git-dir >/dev/null 2>&1; then
  current_origin="$(git remote get-url origin 2>/dev/null || true)"
  if [[ -z "$origin_url" ]]; then
    origin_url="$current_origin"
  fi

  if (( fresh )); then
    git_dir="$(git rev-parse --git-dir)"
    if [[ "$git_dir" != ".git" || ! -d .git ]]; then
      echo "FAIL: --fresh는 일반 checkout의 .git 디렉터리에서만 사용할 수 있습니다." >&2
      exit 1
    fi
    stamp="$(date +%Y%m%d-%H%M%S)"
    backup_dir="$data_root/git-backups/$stamp"
    mkdir -p "$backup_dir"
    mv .git "$backup_dir/dot-git"
    echo "기존 Git 메타데이터 백업: $backup_dir/dot-git"
    git init -b main
  fi
else
  git init -b main
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  if [[ -z "$origin_url" ]]; then
    echo "FAIL: origin이 없습니다. GENOS_GIT_URL에 새 저장소 URL을 넣고 다시 실행하세요." >&2
    echo "예: GENOS_GIT_URL='http://.../repo.git' bash $0" >&2
    exit 1
  fi
  git remote add origin "$origin_url"
fi

# Removing files from today's index cannot remove multi-gigabyte blobs from old
# commits. Refuse the common failed-push state and require an explicit,
# recoverable metadata restart.
if (( ! fresh )) && git rev-parse --verify HEAD >/dev/null 2>&1; then
  object_kib="$(git count-objects -v | awk '/^(size|size-pack):/{sum += $2} END{print sum+0}')"
  if (( object_kib > 250 * 1024 )); then
    echo "FAIL: 기존 Git object 이력이 ${object_kib} KiB로 너무 큽니다." >&2
    echo "gitignore만 바꿔서는 과거 commit의 대용량 blob이 사라지지 않습니다." >&2
    echo "코드와 데이터 파일은 보존하고 Git 이력만 백업·재생성하려면 다음을 실행하세요:" >&2
    echo "  bash $0 --fresh" >&2
    exit 1
  fi
fi

# Ignored files that were already committed stay tracked until removed from the
# index. --cached keeps every working-tree/data-volume file intact.
cached_excludes=(
  GENOS_DATA GENOS_UPLOAD TRANSFER runtime
  90_RUNTIME 09_ARTIFACTS 99_ARCHIVE 04_EXPERIMENTS
  01_DATA/INBOX 01_DATA/SEMANTIC 01_DATA/INDEXES 01_DATA/ACTIVE
  01_DATA/QUARANTINE 01_DATA/BACKUPS 01_DATA/PROJECTIONS 01_DATA/PACKAGES
  01_DATA/FEEDBACK 01_DATA/corpus 01_DATA/structure 01_DATA/custom
  01_DATA/rag 01_DATA/pipeline 01_DATA/rules 01_DATA/embeddings
  01_DATA/domain_graph 01_DATA/legal_graph 01_DATA/lexicon
  01_DATA/expc 01_DATA/review 01_DATA/wiki 01_DATA/bench
  02_BACKEND/GENERATIONS 02_BACKEND/lawrag/research/candidates
  05_TESTS/GENERATIONS 06_TOOLS/GENERATIONS 08_DEPLOYMENT/RELEASES
  02_BACKEND/lawrag/agents/agent6/corpus/raw
  02_BACKEND/lawrag/agents/agent6/corpus/structured
)
git rm -r -q --cached --ignore-unmatch -- "${cached_excludes[@]}"
git add -A

for required in .gitignore service.py requirements-serving.txt; do
  if ! git ls-files --error-unmatch "$required" >/dev/null 2>&1; then
    echo "FAIL: 필수 코드서빙 파일이 Git index에 없습니다: $required" >&2
    exit 1
  fi
done

forbidden_re='^(GENOS_DATA|GENOS_UPLOAD|TRANSFER|runtime|90_RUNTIME|09_ARTIFACTS|99_ARCHIVE|04_EXPERIMENTS|02_BACKEND/GENERATIONS|02_BACKEND/lawrag/research/candidates|05_TESTS/GENERATIONS|06_TOOLS/GENERATIONS|08_DEPLOYMENT/RELEASES)/|^01_DATA/(INBOX|SEMANTIC|INDEXES|ACTIVE|QUARANTINE|BACKUPS|PROJECTIONS|PACKAGES|FEEDBACK|corpus|structure|custom|rag|pipeline|rules|embeddings|domain_graph|legal_graph|lexicon|expc|review|wiki|bench)/|^02_BACKEND/lawrag/agents/[^/]+/corpus/(raw|structured)/|(^|/)\.env$|\.zip(\.part[0-9]+)?$|\.b64\.txt$'
bad_paths="$(git ls-files | grep -E "$forbidden_re" || true)"
if [[ -n "$bad_paths" ]]; then
  echo "FAIL: 데이터/비밀/전송 파일이 아직 Git index에 있습니다:" >&2
  printf '%s\n' "$bad_paths" | head -50 >&2
  exit 1
fi

read -r total_bytes largest_bytes largest_path < <(
  git ls-files -z | xargs -0 -r stat -c '%s %n' 2>/dev/null |
    awk 'BEGIN{sum=0; max=0; path="-"} {size=$1; sum+=size; if(size>max){max=size; $1=""; sub(/^ /,""); path=$0}} END{print sum, max, path}'
)
total_bytes="${total_bytes:-0}"
largest_bytes="${largest_bytes:-0}"
if (( largest_bytes > 20 * 1024 * 1024 )); then
  echo "FAIL: Git에 넣을 단일 파일이 20 MiB를 넘습니다: $largest_path ($largest_bytes bytes)" >&2
  exit 1
fi
if (( total_bytes > 200 * 1024 * 1024 )); then
  echo "FAIL: 코드 snapshot이 200 MiB를 넘습니다: $total_bytes bytes" >&2
  exit 1
fi

branch="$(git branch --show-current 2>/dev/null || true)"
origin="$(git remote get-url origin)"
echo
echo "CODE-ONLY GIT 준비 완료"
echo "root   : $code_root"
echo "branch : ${branch:-main (첫 commit 전)}"
echo "origin : $origin"
echo "tracked: $total_bytes bytes"
echo "largest: $largest_bytes bytes - $largest_path"
echo
echo "검토: git status --short && git diff --cached --stat"
echo "확정: git commit -m 'Deploy GENOS code serving'"
echo "전송: git push -u origin main"
echo
echo "주의: GENOS_DATA_ROOT가 코드서빙 인스턴스에도 마운트되어 있는지는 별도 확인해야 합니다."
