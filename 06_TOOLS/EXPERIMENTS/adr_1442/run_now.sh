#!/bin/bash
# ADR-1442 (user-directed parallel run, "같이 병렬로 못하나"):
# wait for ADR-1441's MAIN170 base regression, stop that run's outdated staged170 checks, then
# quick gate on staged170c -> freeze -> five cells (3-turn first) -> regression staged170c vs reg-main170 -> Oracle check.
# Cells do not wait for other sessions' tests; another python live.py is never run at the same time.
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1442
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1442-guided-exception-candidates-qwen/artifacts; mkdir -p "$ART"; LOG=$ART/run.log
P=$ROOT/09_ARTIFACTS/AUDITS/20261106-guided-followup-reads/main_prep; STAGED=$P/staged170c
OLD=$ROOT/04_EXPERIMENTS/ADR/ADR-1441-guided-reads-fixes-qwen/artifacts/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
no_live() { while pgrep -f "bin/python[0-9.]* ([^ ]*/)?live[.]py" >/dev/null; do sleep 10; done; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$ROOT"
say "user-directed immediate start (실험해봐): ADR-1441 runner already stopped; its reg-main170 base regression keeps running for the later compare"
say "user-directed start: avail=$(free -m | awk '/Mem:/{print $7}')MB"
$PY $P/run_offline.py --code-root $STAGED --name gate-staged170c-adr1442 \
  $P/overlay/tests/test_guided_followup_reads.py $P/overlay/tests/test_guided_continue_bounds.py $P/overlay/tests/test_multiturn_dialogue_api.py \
  05_TESTS/CONTRACTS/test_guided_answer.py > "$ART/gate.log" 2>&1
tail -1 "$ART/gate.log" | tee -a "$LOG"
grep -q " failed 0 " "$ART/gate.log" || { say "STOP: quick gate failed"; exit 3; }
( cd "$HERE" && $PY setup.py design ) >> "$LOG" 2>&1 || { say "STOP: freeze failed"; exit 4; }
say "frozen"
for CASE in shareholder-resolution-3turn board-resolution dissolution-resolution capital-reduction-resolution articles-amendment-2turn; do
  if stopped; then say "skip $CASE: earlier UNKNOWN or resource stop"; continue; fi
  no_live
  ( cd "$HERE" && timeout 900 $PY live.py "$CASE" candidate --preflight ) > "$ART/preflight-$CASE.log" 2>&1 || { say "STOP: preflight failed $CASE"; break; }
  say "preflight ready $CASE"; no_live; say "live start $CASE"
  ( cd "$HERE" && timeout 3000 $PY live.py "$CASE" candidate ) > "$ART/live-$CASE.log" 2>&1; rc=$?
  say "live exit $CASE $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$CASE.log" | cut -c1-300 | tee -a "$LOG"
  $PY "$HERE/audit.py" "$ART/public-live/$CASE-candidate" 2>&1 | tail -1 | cut -c1-300 | tee -a "$LOG"
done
say "live cells done"
no_live; while pgrep -f "[r]un_offline[.]py --code-root [^ ]*structure-catalogue" >/dev/null; do sleep 20; done
while [ ! -f $P/reg-main170.json ]; do sleep 20; done
say "regression staged170c start"
$PY $P/run_offline.py --code-root $STAGED --name reg-staged170c $(cat $P/regression-tests.txt) > $P/reg-staged170c.log 2>&1; say "regression staged170c exit $?"
$PY $P/compare.py reg-main170 reg-staged170c 2>&1 | tee -a "$LOG"
no_live; say "oracle check start"
$PY $P/oracle_check.py --code-root $STAGED --name oracle-staged170c > $P/oracle-staged170c.log 2>&1; say "oracle check exit $?"
grep -E "^CASE|passed .* failed" $P/oracle-staged170c.log | cut -c1-200 | tee -a "$LOG"
say "done"
