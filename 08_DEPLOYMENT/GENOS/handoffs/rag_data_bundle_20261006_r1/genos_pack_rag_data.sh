#!/usr/bin/env bash
# GENOS: place this launcher beside genos_rag_data_bundle.py, then run in DEV.
set -euo pipefail
umask 077
GENOS_RAG_BUNDLE_TOOL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$GENOS_RAG_BUNDLE_TOOL_DIR/genos_rag_data_bundle.py" pack "$@"
