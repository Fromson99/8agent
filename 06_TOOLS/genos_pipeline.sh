#!/usr/bin/env bash
# Offline glossary + existing GENOS authoring, embedding and SQLite pipeline.
set -euo pipefail
umask 077
GENOS_PIPELINE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$GENOS_PIPELINE_ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$GENOS_PIPELINE_ROOT/02_BACKEND${PYTHONPATH:+:$PYTHONPATH}"
if [[ -x "$GENOS_PIPELINE_ROOT/.venv/bin/python" ]]; then
  exec "$GENOS_PIPELINE_ROOT/.venv/bin/python" -u 06_TOOLS/COMMANDS/genos_all_pipeline.py "$@"
fi
exec python3 -u 06_TOOLS/COMMANDS/genos_all_pipeline.py "$@"
