#!/usr/bin/env bash
set -euo pipefail

failures=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

pass() {
  printf 'PASS: %s\n' "$1"
}

if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  pass 'running inside WSL'
else
  fail 'run this repository with the WSL agent, not a Windows-native or generic Linux agent'
fi

repo_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
case "$repo_root" in
  /home/*)
    pass "repository is on the WSL Linux filesystem ($repo_root)"
    ;;
  /mnt/*)
    fail "repository is on a Windows-mounted drive ($repo_root)"
    ;;
  '')
    fail 'current directory is not inside a Git repository'
    ;;
  *)
    fail "expected the repository under /home, found $repo_root"
    ;;
esac

autocrlf=$(git config --local --get core.autocrlf 2>/dev/null || true)
if [[ "$autocrlf" == 'false' ]]; then
  pass 'Git core.autocrlf=false'
else
  fail "set local Git core.autocrlf=false (found: ${autocrlf:-unset})"
fi

eol=$(git config --local --get core.eol 2>/dev/null || true)
if [[ "$eol" == 'lf' ]]; then
  pass 'Git core.eol=lf'
else
  fail "set local Git core.eol=lf (found: ${eol:-unset})"
fi

filemode=$(git config --local --get core.filemode 2>/dev/null || true)
if [[ "$filemode" == 'true' ]]; then
  pass 'Git core.filemode=true'
else
  fail "set local Git core.filemode=true (found: ${filemode:-unset})"
fi

if git diff --check >/dev/null; then
  pass 'working-tree diff has no whitespace errors'
else
  fail 'git diff --check reported whitespace errors'
fi

if ((failures > 0)); then
  printf '\n%d WSL development boundary check(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nWSL development boundary is healthy.\n'
