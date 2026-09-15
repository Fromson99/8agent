#!/usr/bin/env bash
# One-document invocation of the existing GENOS pipeline entrypoint.
set -euo pipefail
umask 077
GENOS_E2E_CODE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$GENOS_E2E_CODE_ROOT"
if [[ -x .venv/bin/python ]]; then
  GENOS_E2E_PYTHON=.venv/bin/python
else
  GENOS_E2E_PYTHON=python3
fi
export PYTHONUNBUFFERED=1
exec "$GENOS_E2E_PYTHON" 06_TOOLS/COMMANDS/genos_unified_pipeline.py \
  e2e --backend genos --execute "$@"
