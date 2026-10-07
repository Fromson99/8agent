#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
handoff_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
handoff_mode="${1:-check}"
handoff_root="$(cd -- "${MAIN_DEV_ROOT:-$HOME/DEV}" && pwd -P)"
handoff_runtime="${GENOS_RUNTIME_DIR:-/nfs-root/diamo/8-agent/runtime}"
mkdir -p "$handoff_dir/logs"
handoff_log="$handoff_dir/logs/$(date -u +%Y%m%dT%H%M%SZ)-${handoff_mode}-$$.log"
exec > >(tee -a "$handoff_log") 2>&1
trap 'handoff_exit=$?; trap - EXIT; printf "HANDOFF_EXIT=%s MODE=%s LOG=%s\n" "$handoff_exit" "$handoff_mode" "$handoff_log"; exit "$handoff_exit"' EXIT
printf 'HANDOFF_START ROOT=%s RUNTIME=%s MODE=%s\n' "$handoff_root" "$handoff_runtime" "$handoff_mode"
cd "$handoff_root"
python3 "$handoff_dir/verify.py"
case "$handoff_mode" in
 check) python3 "$handoff_dir/apply.py" --root "$handoff_root" --archive "$handoff_dir/code.zip" ;;
 apply)
  python3 "$handoff_dir/apply.py" --root "$handoff_root" --archive "$handoff_dir/code.zip" --apply
  python3 "$handoff_dir/verify.py" --root "$handoff_root"
  ;;
 verify) python3 "$handoff_dir/verify.py" --root "$handoff_root" ;;
 runtime)
  python3 "$handoff_dir/runtime_check.py" --runtime "$handoff_runtime"
  printf 'Set these in CODE-SERVING revision (shell exports alone do not configure it):\n'
  printf 'GENOS_RUNTIME_DIR=%s\nGENOS_MEMORY_JOURNAL_MODE=DELETE\nGENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6\n' "$handoff_runtime"
  ;;
 gate)
  : "${GENOS_GENERATION:?Set the exact existing serving generation absolute path; do not use an unfinished reindex directory}"
  python3 "$handoff_root/06_TOOLS/COMMANDS/genos_release_gate.py" --code-zip "$handoff_dir/code.zip" --deploy-root "$handoff_root" --generation "$GENOS_GENERATION"
  ;;
 rollback)
  : "${2:?Supply the exact code backup folder printed at apply}"
  python3 "$handoff_dir/apply.py" --root "$handoff_root" --rollback "$2"
  ;;
 *) printf 'Modes: check apply verify runtime gate rollback\n'; exit 2 ;;
esac
