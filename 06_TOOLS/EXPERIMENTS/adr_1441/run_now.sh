#!/bin/bash
# ADR-1441: quick test gate on the staged promotion tree -> freeze -> five live cells, each alone on a quiet machine
# -> afterwards (no model): full regression MAIN170 vs staged170, row compare, real-Oracle read-only check.
# A previous UNKNOWN or resource stop makes live.py refuse every later cell (no sending after an unknown outcome).
set -u
ROOT=/home/jin/8-AGENT; PY=$ROOT/.venv/bin/python; HERE=$ROOT/06_TOOLS/EXPERIMENTS/adr_1441
ART=$ROOT/04_EXPERIMENTS/ADR/ADR-1441-guided-reads-fixes-qwen/artifacts; mkdir -p "$ART"; LOG=$ART/run.log
P=$ROOT/09_ARTIFACTS/AUDITS/20261106-guided-followup-reads/main_prep; STAGED=$P/staged170
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
calm() {
  pgrep -f "[l]ive[.]py" >/dev/null && return 1
  pgrep -f "[b]atch[.]py" >/dev/null && return 1
  pgrep -f "[p]ytest" >/dev/null && return 1
  pgrep -f "[c]heck[0-9]*[.]py" >/dev/null && return 1
  pgrep -f "[p]robe[.]py" >/dev/null && return 1
  pgrep -f "[r]un_offline[.]py" >/dev/null && return 1
  pgrep -f "[r]un_tests[.]py" >/dev/null && return 1
  local avail; avail=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  [ "$avail" -gt $((6*1024*1024)) ]
}
wait_calm() { while pgrep -f "[l]ive[.]py" >/dev/null; do sleep 10; done; }
stopped() { ls "$ART"/public-live/*/STOP_EXTERNAL.json "$ART"/public-live/*/resource-stop.json 2>/dev/null | grep -q .; }
cd "$ROOT"
say "user-directed start (시작해봐): no wait for other sessions; avail=$(free -m | awk '/Mem:/{print $7}')MB"
# 1. Quick gate on the exact staged tree (the tests that cover this work).
$PY $P/run_offline.py --code-root $STAGED --name gate-staged170-adr1441 \
  $P/overlay/tests/test_guided_followup_reads.py $P/overlay/tests/test_guided_continue_bounds.py $P/overlay/tests/test_multiturn_dialogue_api.py \
  05_TESTS/CONTRACTS/test_guided_answer.py > "$ART/gate.log" 2>&1
tail -1 "$ART/gate.log" | tee -a "$LOG"
grep -q " failed 0 " "$ART/gate.log" || { say "STOP: quick gate failed"; exit 3; }
# 2. Freeze (no model call).
( cd "$HERE" && $PY setup.py design ) >> "$LOG" 2>&1 || { say "STOP: freeze failed"; exit 4; }
say "frozen"
# 3. Five cells in the frozen order.
for CASE in board-resolution dissolution-resolution capital-reduction-resolution articles-amendment-2turn shareholder-resolution-3turn; do
  if stopped; then say "skip $CASE: earlier UNKNOWN or resource stop"; continue; fi
  wait_calm
  ( cd "$HERE" && timeout 900 $PY live.py "$CASE" candidate --preflight ) > "$ART/preflight-$CASE.log" 2>&1 || { say "STOP: preflight failed $CASE"; break; }
  say "preflight ready $CASE"; wait_calm; say "live start $CASE"
  ( cd "$HERE" && timeout 3000 $PY live.py "$CASE" candidate ) > "$ART/live-$CASE.log" 2>&1; rc=$?
  say "live exit $CASE $rc"; grep -E "^LIVE_RESULT|^RESOURCE_STOP" "$ART/live-$CASE.log" | cut -c1-300 | tee -a "$LOG"
  $PY "$HERE/audit.py" "$ART/public-live/$CASE-candidate" 2>&1 | tail -1 | cut -c1-300 | tee -a "$LOG"
done
say "live cells done"
# 4. No-model checks of the promotion tree.
B=$($PY -c "import json;print(json.load(open('$P/baseline.json'))['release']['code_root'])")
wait_calm; say "regression base start"
$PY $P/run_offline.py --code-root "$ROOT/$B" --name reg-main170 $(cat $P/regression-tests.txt) > $P/reg-main170.log 2>&1; say "regression base exit $?"
wait_calm; say "regression staged start"
$PY $P/run_offline.py --code-root $STAGED --name reg-staged170 $(cat $P/regression-tests.txt) > $P/reg-staged170.log 2>&1; say "regression staged exit $?"
$PY $P/compare.py reg-main170 reg-staged170 2>&1 | tee -a "$LOG"
wait_calm; say "oracle check start"
$PY $P/oracle_check.py --code-root $STAGED --name oracle-staged170 > $P/oracle-staged170.log 2>&1; say "oracle check exit $?"
grep -E "^CASE|passed .* failed" $P/oracle-staged170.log | cut -c1-200 | tee -a "$LOG"
say "done"
