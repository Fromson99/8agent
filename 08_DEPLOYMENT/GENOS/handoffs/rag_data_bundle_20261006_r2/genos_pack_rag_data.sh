#!/usr/bin/env bash
# GENOS: place this launcher beside genos_rag_data_bundle.py, then run in DEV.
set -euo pipefail
umask 077
GENOS_RAG_BUNDLE_TOOL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
GENOS_RAG_BUNDLE_DEV="${GENOS_DEV:-$HOME/DEV}"
if [[ ! -d "$GENOS_RAG_BUNDLE_DEV" ]]; then
  printf 'ERROR: existing DEV directory missing; set GENOS_DEV to its absolute path.\n' >&2
  exit 2
fi
exec python3 "$GENOS_RAG_BUNDLE_TOOL_DIR/genos_rag_data_bundle.py" pack --code-root "$GENOS_RAG_BUNDLE_DEV" --output-dir "$GENOS_RAG_BUNDLE_DEV" "$@"
