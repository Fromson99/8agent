#!/bin/bash
# ADR-1439 user-directed run (그냥 돌릴수 없나): remaining cells start without waiting for other sessions' tests.
# Kept: frozen candidate/cases/live.py, RAM/worker guards inside live.py, no other live cell at the same time,
# and the rule that an earlier UNKNOWN or resource stop refuses every later cell.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1439
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1439-guided-chapter-title-qwen-r2/artifacts; LOG=$ART/run-when-free.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
for CASE in articles-amendment-2turn shareholder-resolution-3turn; do
  if stopped; then say "skip $CASE: earlier UNKNOWN or resource stop"; continue; fi
  while pgrep -f "[l]ive[.]py" >/dev/null; do sleep 10; done
  ( cd "$HERE" && timeout 900 $PY live.py "$CASE" candidate --preflight ) > "$ART/preflight-$CASE.log" 2>&1 || { say "STOP: preflight failed $CASE"; exit 5; }
  say "preflight ready $CASE (user-directed, concurrent tests running)"; say "live start $CASE"
  ( cd "$HERE" && timeout 3000 $PY live.py "$CASE" candidate ) > "$ART/live-$CASE.log" 2>&1; rc=$?
  say "live exit $CASE $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$CASE.log" | cut -c1-400 | tee -a "$LOG"
  $PY "$HERE/audit.py" "$ART/public-live/$CASE-candidate" 2>&1 | tail -1 | tee -a "$LOG"
done
say "done"
