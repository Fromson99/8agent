#!/usr/bin/env bash
# Explicit optimized DRAFT entrypoint; does not change MAIN or the old command.
set -euo pipefail
umask 077
SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
OPTIMIZER="$SCRIPT_ROOT/06_TOOLS/COMMANDS/genos_structure_optimized_v2.py"
EXPECTED_SHA=81b9621eff2a8837b221ad5b9d5ef5cc57e5130fa823419398c22006e1583777
if [[ ! -f "$OPTIMIZER" || -L "$OPTIMIZER" ]]; then
  echo 'Missing regular v2 optimizer; install the matching code bundle.' >&2
  exit 2
fi
ACTUAL_SHA="$(sha256sum -- "$OPTIMIZER")"
if [[ "${ACTUAL_SHA%% *}" != "$EXPECTED_SHA" ]]; then
  echo 'Optimizer hash mismatch; use the reviewed matching version.' >&2
  exit 2
fi
cd -- "$SCRIPT_ROOT"
if [[ -x "$SCRIPT_ROOT/.venv/bin/python" ]]; then
  exec "$SCRIPT_ROOT/.venv/bin/python" -u "$OPTIMIZER" --root "$SCRIPT_ROOT" --pipeline "$@"
fi
exec python3 -u "$OPTIMIZER" --root "$SCRIPT_ROOT" --pipeline "$@"
