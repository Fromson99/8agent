#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_dir"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_bin="$PYTHON_BIN"
elif [[ -x .venv/bin/python ]]; then
  python_bin=.venv/bin/python
else
  python_bin=python3
fi

"$python_bin" -B 06_TOOLS/ontology_pipeline.py validate
"$python_bin" -B -m pytest -s -q \
  05_TESTS/REGRESSION/architecture/test_definition_projection_schema.py \
  05_TESTS/REGRESSION/core/test_feedback_lifecycle.py \
  05_TESTS/REGRESSION/core/test_ontology_pipeline.py \
  05_TESTS/REGRESSION/core/test_batch.py \
  05_TESTS/REGRESSION/core/test_legal_graph_v1.py \
  05_TESTS/REGRESSION/rag/test_feedback_api_recovery.py \
  05_TESTS/REGRESSION/rag/test_tuples.py

if command -v node >/dev/null 2>&1; then
  node --check 02_BACKEND/lawrag/api/viewer/pipeline/app.js
fi
