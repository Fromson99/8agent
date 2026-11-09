#!/bin/bash
# ADR-1448 r5 cells, one at a time: candidate plain, candidate inject (baseline cells unchanged from r4).
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1448
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1448-multiturn-new-topic-branch-qwen/artifacts; LOG=$ART/run-r5.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$HERE"
for SPEC in "candidate --plain" "candidate"; do
  set -- $SPEC; ARM=$1; FLAG=${2:-}; NAME=$ARM${FLAG:+-plain}
  if stopped; then say "skip $NAME: earlier UNKNOWN or resource stop"; continue; fi
  timeout 900 $PY live_inject.py topic-switch-3turn $ARM $FLAG --preflight > "$ART/preflight-r5-$NAME.log" 2>&1 || { say "STOP: preflight failed $NAME"; break; }
  say "live start $NAME"
  timeout 3000 $PY live_inject.py topic-switch-3turn $ARM $FLAG > "$ART/live-r5-$NAME.log" 2>&1; say "live exit $NAME $?"
  grep -E "^LIVE_RESULT|^RESOURCE_STOP|^INJECTED" "$ART/live-r5-$NAME.log" | cut -c1-260 | tee -a "$LOG"
done
say done
