#!/usr/bin/env bash
set -euo pipefail
umask 077
SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ -x "$SCRIPT_ROOT/.venv/bin/python" ]]; then
  exec "$SCRIPT_ROOT/.venv/bin/python" "$SCRIPT_ROOT/06_TOOLS/COMMANDS/genos_data_stages.py" "$@"
fi
exec python3 "$SCRIPT_ROOT/06_TOOLS/COMMANDS/genos_data_stages.py" "$@"
