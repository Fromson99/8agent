#!/usr/bin/env bash
set -euo pipefail
GENOS_BUNDLE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$GENOS_BUNDLE_ROOT/06_TOOLS/OFFLINE/genos_cli.py" ]]; then
  GENOS_CLI="$GENOS_BUNDLE_ROOT/06_TOOLS/OFFLINE/genos_cli.py"
else
  GENOS_CLI="$GENOS_BUNDLE_ROOT/genos_cli.py"
fi
if [[ -n "${GENOS_PYTHON:-}" ]]; then
  exec "$GENOS_PYTHON" "$GENOS_CLI" "$@"
elif [[ -x "$GENOS_BUNDLE_ROOT/.venv/bin/python" ]]; then
  exec "$GENOS_BUNDLE_ROOT/.venv/bin/python" "$GENOS_CLI" "$@"
else
  exec python3 "$GENOS_CLI" "$@"
fi
