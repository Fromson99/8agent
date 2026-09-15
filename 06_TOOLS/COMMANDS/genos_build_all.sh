#!/usr/bin/env bash
set -euo pipefail
umask 077
GENOS_ALL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$GENOS_ALL_ROOT"
GENOS_ALL_PYTHON=python3
if [[ -x .venv/bin/python ]]; then GENOS_ALL_PYTHON="$GENOS_ALL_ROOT/.venv/bin/python"; fi
export PYTHONUNBUFFERED=1
exec "$GENOS_ALL_PYTHON" 06_TOOLS/COMMANDS/genos_build_all.py "$@"
