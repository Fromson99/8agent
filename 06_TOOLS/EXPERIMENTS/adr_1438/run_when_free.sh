#!/bin/bash
# ADR-1438: each live cell starts only when no other live cell / test run is active and memory has recovered.
# contract re-check (isolated MAIN168 copy) -> freeze -> per case: preflight -> live -> read-choice audit.
# A previous UNKNOWN or resource stop makes live.py refuse every later cell (no sending after an unknown outcome).
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1438
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1438-guided-chapter-title-qwen/artifacts; mkdir -p "$ART"; LOG=$ART/run-when-free.log
ISO=/tmp/a8-followup-iso168
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
calm() {
  pgrep -f "[l]ive[.]py" >/dev/null && return 1
  pgrep -f "[b]atch[.]py" >/dev/null && return 1
  pgrep -f "[p]ytest" >/dev/null && return 1
  pgrep -f "[c]heck[0-9]*[.]py" >/dev/null && return 1
  pgrep -f "[p]robe[.]py" >/dev/null && return 1
  pgrep -f "[r]un_offline[.]py" >/dev/null && return 1
  local avail
  avail=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  [ "$avail" -gt $((6*1024*1024)) ]
}
wait_calm() { local ok=0; while [ $ok -lt 4 ]; do if calm; then ok=$((ok+1)); else ok=0; fi; sleep 15; done; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
say "waiting for a free machine"; wait_calm; say "machine free: $(free -m | awk '/Mem:/{print "avail="$7"MB"}')"
# 1. Contract re-check on the isolated copy that the freeze binds (work code must equal it).
( cd "$ISO" && timeout 900 $PY -m pytest -q -p no:cacheprovider 05_TESTS/CONTRACTS/test_guided_followup_reads.py 05_TESTS/CONTRACTS/test_guided_continue_bounds.py \
    05_TESTS/CONTRACTS/test_guided_answer.py 05_TESTS/CONTRACTS/test_multiturn_dialogue_api.py 05_TESTS/CONTRACTS/test_multiturn_dialogue.py ) > "$ART/contract-recheck.log" 2>&1
tail -1 "$ART/contract-recheck.log" | tee -a "$LOG"
if ! tail -1 "$ART/contract-recheck.log" | grep -q " passed" || tail -1 "$ART/contract-recheck.log" | grep -q "failed"; then say "STOP: contract re-check failed"; exit 3; fi
# 2. Freeze (no model call).
( cd "$HERE" && $PY setup.py design ) >> "$LOG" 2>&1 || { say "STOP: freeze failed"; exit 4; }
say "frozen"
# 3. Cells in the frozen order, each alone.
for CASE in board-resolution dissolution-resolution capital-reduction-resolution articles-amendment-2turn shareholder-resolution-3turn; do
  if stopped; then say "skip $CASE: earlier UNKNOWN or resource stop"; continue; fi
  wait_calm
  ( cd "$HERE" && timeout 900 $PY live.py "$CASE" candidate --preflight ) > "$ART/preflight-$CASE.log" 2>&1 || { say "STOP: preflight failed $CASE"; exit 5; }
  say "preflight ready $CASE"; wait_calm; say "live start $CASE"
  ( cd "$HERE" && timeout 3000 $PY live.py "$CASE" candidate ) > "$ART/live-$CASE.log" 2>&1; rc=$?
  say "live exit $CASE $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$CASE.log" | cut -c1-400 | tee -a "$LOG"
  $PY "$HERE/audit.py" "$ART/public-live/$CASE-candidate" 2>&1 | tail -1 | tee -a "$LOG"
done
say "done"
