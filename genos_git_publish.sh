#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || "$1" != "--confirm-replace-main" ]]; then
  echo "사용법: ./genos_git_publish.sh --confirm-replace-main <REMOTE_URL>" >&2
  exit 2
fi

remote_url="$2"
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$repo_dir"

if [[ -d .git ]]; then
  backup_dir="$(cd -- "$repo_dir/.." && pwd)/.genos-git-backups"
  mkdir -p -- "$backup_dir"
  backup="$backup_dir/DEV-$(date -u +%Y%m%dT%H%M%SZ)"
  mv -- .git "$backup"
  echo "기존 Git 메타데이터를 $backup 에 보관했습니다."
fi

git init -b main
git remote add origin "$remote_url"
git add --all

forbidden="$(git diff --cached --name-only | grep -E '(^|/)(\.env|\.venv|90_RUNTIME|09_ARTIFACTS|99_ARCHIVE|GENOS_INPUT|GENOS_DATA|GENOS_UPLOAD|TRANSFER|01_DATA/(PACKAGES|INBOX|SEMANTIC|ACTIVE|INDEXES|QUARANTINE|BACKUPS|PROJECTIONS))(/|$)|(^|/)structured-prellm\.sqlite$|genos-unified-raw-.*\.zip($|\.)|\.zip\.part[0-9]+$' || true)"
if [[ -n "$forbidden" ]]; then
  echo "Git에 데이터/산출물이 올라가려 합니다:" >&2
  echo "$forbidden" >&2
  exit 3
fi

git commit -m "Replace main with unified GENOS raw pipeline"
local_sha="$(git rev-parse HEAD)"
git push --force --set-upstream origin main
remote_sha="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
if [[ "$remote_sha" != "$local_sha" ]]; then
  echo "원격 SHA 검증 실패: local=$local_sha remote=$remote_sha" >&2
  exit 4
fi
echo "PUSH 완료: $remote_sha"
