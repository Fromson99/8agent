#!/usr/bin/env bash
# Latest schema runtime only. ACTIVE_RELEASE is the sole serving selector.
set -euo pipefail
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
export PYTHONDONTWRITEBYTECODE=1
exec "$workspace_root/.venv/bin/uvicorn" --app-dir "$workspace_root" service:application --factory --host "${HOST:-0.0.0.0}" --port "${PORT:-5566}"
