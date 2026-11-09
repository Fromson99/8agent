#!/bin/bash
# ADR-1446 (ADR-1445 follow-up, r6; user-directed concurrent run while MAIN171 is prepared by another session):
# quick gate on staged170g -> freeze -> three multi-turn cells (field-photo 3-turn first) (no regression here).
# Cells do not wait for other sessions' tests (user-directed); another python live.py is never run at the same time.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1446
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1446-guided-answer-title-matches-elided-subject-qwen/artifacts; mkdir -p "$ART"; LOG=$ART/run.log
P=$ROOT/09_ARTIFACTS/AUDITS/20261106-guided-followup-reads/main_prep; STAGED=$P/staged170g
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
no_live() { while pgrep -f "bin/python[0-9.]* ([^ ]*/)?live[.]py" >/dev/null; do sleep 10; done; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$ROOT"
say "user-directed start: avail=$(free -m | awk '/Mem:/{print $7}')MB"
$PY $P/run_offline.py --code-root $STAGED --name gate-staged170g-adr1446 \
  $P/overlay/tests/test_guided_followup_reads.py $P/overlay/tests/test_guided_continue_bounds.py $P/overlay/tests/test_multiturn_dialogue_api.py \
  05_TESTS/CONTRACTS/test_guided_answer.py > "$ART/gate.log" 2>&1
tail -1 "$ART/gate.log" | tee -a "$LOG"
grep -q " failed 0 " "$ART/gate.log" || { say "STOP: quick gate failed"; exit 3; }
( cd "$HERE" && $PY setup.py design ) >> "$LOG" 2>&1 || { say "STOP: freeze failed"; exit 4; }
say "frozen"
for CASE in shareholder-resolution-3turn articles-amendment-2turn board-shareholder-articles-3turn; do
  if stopped; then say "skip $CASE: earlier UNKNOWN or resource stop"; continue; fi
  no_live
  ( cd "$HERE" && timeout 900 $PY live.py "$CASE" candidate --preflight ) > "$ART/preflight-$CASE.log" 2>&1 || { say "STOP: preflight failed $CASE"; break; }
  say "preflight ready $CASE"; no_live; say "live start $CASE"
  ( cd "$HERE" && timeout 3000 $PY live.py "$CASE" candidate ) > "$ART/live-$CASE.log" 2>&1; rc=$?
  say "live exit $CASE $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$CASE.log" | cut -c1-300 | tee -a "$LOG"
  $PY "$HERE/audit.py" "$ART/public-live/$CASE-candidate" 2>&1 | tail -1 | cut -c1-300 | tee -a "$LOG"
done
say "live cells done (regression and Oracle check run on the MAIN171-based staged tree before promotion)"
say "done"
