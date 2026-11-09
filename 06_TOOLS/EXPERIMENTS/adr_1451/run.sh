#!/bin/bash
# ADR-1451: candidate r9, injected disagreement first, then plain; one cell at a time.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1451
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1451-multiturn-pending-reply-related-qwen/artifacts; LOG=$ART/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$HERE"
for SPEC in "candidate" "candidate --plain"; do
  set -- $SPEC; ARM=$1; FLAG=${2:-}; NAME=$ARM${FLAG:+-plain}
  if stopped; then say "skip $NAME: earlier UNKNOWN or resource stop"; continue; fi
  timeout 900 $PY live_inject.py topic-switch-3turn $ARM $FLAG --preflight > "$ART/preflight-$NAME.log" 2>&1 || { say "STOP: preflight failed $NAME"; break; }
  say "live start $NAME"
  timeout 3000 $PY live_inject.py topic-switch-3turn $ARM $FLAG > "$ART/live-$NAME.log" 2>&1; say "live exit $NAME $?"
done
say done
