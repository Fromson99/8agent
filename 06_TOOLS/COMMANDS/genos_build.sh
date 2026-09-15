#!/usr/bin/env bash
set -euo pipefail
umask 077
GENOS_BUILD_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$GENOS_BUILD_ROOT"
if [[ -x .venv/bin/python ]]; then
  GENOS_BUILD_PYTHON="$GENOS_BUILD_ROOT/.venv/bin/python"
else
  GENOS_BUILD_PYTHON=python3
fi
export PYTHONUNBUFFERED=1
exec "$GENOS_BUILD_PYTHON" 06_TOOLS/COMMANDS/genos_unified_pipeline.py build --execute "$@"
