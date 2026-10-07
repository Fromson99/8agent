#!/usr/bin/env bash
# Run this file from the transferred handoff folder. Existing ~/DEV is the target.
set -Eeuo pipefail
umask 077
handoff_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
handoff_mode="${1:-check}"
handoff_root="${MAIN_DEV_ROOT:-$HOME/DEV}"
mkdir -p -- "$handoff_dir/logs"
handoff_log="$handoff_dir/logs/$(date -u +%Y%m%dT%H%M%SZ)-${handoff_mode}-$$.log"
exec > >(tee -a "$handoff_log") 2>&1
trap 'handoff_exit=$?; trap - EXIT; printf "HANDOFF_EXIT=%s MODE=%s LOG=%s\n" "$handoff_exit" "$handoff_mode" "$handoff_log"; exit "$handoff_exit"' EXIT
printf 'HANDOFF_START MODE=%s ROOT=%s LOG=%s\n' "$handoff_mode" "$handoff_root" "$handoff_log"
cd -- "$handoff_root"
# Verifies checksums before executing the installer. No credentials are printed.
python3 "$handoff_dir/verify.py"
case "$handoff_mode" in
  check)
    python3 "$handoff_dir/apply.py" --root "$handoff_root" --archive "$handoff_dir/code.zip"
    ;;
  apply)
    python3 "$handoff_dir/apply.py" --root "$handoff_root" --archive "$handoff_dir/code.zip" --apply
    python3 "$handoff_dir/verify.py" --root "$handoff_root"
    ;;
  verify)
    python3 "$handoff_dir/verify.py" --root "$handoff_root"
    ;;
  generation)
    python3 "$handoff_root/06_TOOLS/COMMANDS/genos_generation_e2e.py" --code-root "$handoff_root" --auto
    ;;
  gate)
    python3 "$handoff_root/06_TOOLS/COMMANDS/genos_release_gate.py" --code-zip "$handoff_dir/code.zip" --deploy-root "$handoff_root"
    ;;
  evidence)
    python3 "$handoff_dir/verify.py" --include-evidence
    ;;
  rollback)
    if [[ -z "${2:-}" ]]; then
      printf 'Provide the exact backup folder containing receipt.json as the second argument.\n'
      exit 2
    fi
    python3 "$handoff_dir/apply.py" --root "$handoff_root" --rollback "$2"
    ;;
  *) printf 'Modes: check apply verify generation gate evidence rollback\n'; exit 2 ;;
esac
