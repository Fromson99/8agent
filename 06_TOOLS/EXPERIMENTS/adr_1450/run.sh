#!/bin/bash
# ADR-1450: candidate r7 only (baseline = ADR-1449 MAIN176 cell).
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1450
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1450-multiturn-related-judgments-qwen/artifacts; LOG=$ART/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$HERE"
for ARM in candidate; do
  if stopped; then say "skip $ARM: earlier UNKNOWN or resource stop"; continue; fi
  timeout 900 $PY live.py earlier-topics-4turn $ARM --preflight > "$ART/preflight-$ARM.log" 2>&1 || { say "STOP: preflight failed $ARM"; break; }
  say "live start $ARM"
  timeout 3000 $PY live.py earlier-topics-4turn $ARM > "$ART/live-$ARM.log" 2>&1; say "live exit $ARM $?"
  grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$ARM.log" | cut -c1-200 | tee -a "$LOG"
done
say done
