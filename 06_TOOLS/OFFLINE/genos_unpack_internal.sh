#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ -x "$TASK_ROOT/.venv/bin/python" ]]; then
  exec "$TASK_ROOT/.venv/bin/python" "$TASK_ROOT/06_TOOLS/OFFLINE/genos_unpack_internal.py" "$@"
fi
exec python3 "$TASK_ROOT/06_TOOLS/OFFLINE/genos_unpack_internal.py" "$@"
