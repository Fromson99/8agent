#!/usr/bin/env bash
set -euo pipefail
TERM_STAGES_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$TERM_STAGES_ROOT/06_TOOLS/COMMANDS/genos_data_stages.sh" "$@"
