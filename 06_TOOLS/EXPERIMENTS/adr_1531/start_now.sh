#!/bin/bash
# ADR-1531 (baseline MAIN226 vs candidate staged8, interleaved per question; ADR-1524 driver). Runs after other sessions' experiments: before the first cell
# it waits until no live.py/batch.py/run_all.sh/rerun.py/start_now.sh of another 06_TOOLS/EXPERIMENTS/adr_* folder has
# run for 2 minutes (user rule: real-model cells alone; 2 hours wait at most, then it does not start). Same admission/
# yield rule as ADR-1515: a cell starts only with >=5GiB free and yields below 3.4GiB twice 5 s apart. Frozen order:
# cmp-liquidity, cmp-soundness, cmp-riskcommittee; then one rerun of a cell whose every fallback provider failed
# (STOP_EXTERNAL), a yield or no result; then collect.py. Physical calls capped at 500 in total (a cell starts only
# while at most 500-100 are used).
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
GIB=1048576  # KiB
avail() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
log() { echo "$*" >> $A/driver.log; }
calls_so_far() { $PY -c "
from common import *
print(sum(len(read(p)) for p in (ART/'live').glob('*/*/calls.json')))" 2>/dev/null || echo 0; }
cell() {  # case arm [--rerun]
  local c=$1 arm=$2 rr=${3:-} waited=0
  [ -f $A/STOP_ALL.json ] && return 1
  local n=$(calls_so_far); if [ $n -gt $((500-100)) ]; then log "$c $arm $rr skipped: $n physical calls already (limit 500)"; return 0; fi
  while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  if [ $(avail) -lt $((5*GIB)) ]; then log "=== $c $arm $rr not started: free RAM below 5GiB for 30 minutes $(date '+%T')"; return 0; fi
  log "=== $c $arm $rr $(date '+%H:%M:%S') waited $waited free_KiB $(avail)"
  $PY live.py $c $arm $rr > $A/log-$arm-$c${rr:+-rerun}.txt 2>&1 &
  local pid=$! low=0
  while kill -0 $pid 2>/dev/null; do
    if [ $(avail) -lt $((34*GIB/10)) ]; then low=$((low+1)); else low=0; fi
    if [ $low -ge 2 ]; then
      kill $pid; sleep 2; kill -9 $pid 2>/dev/null
      printf '{"case":"%s","arm":"%s","rerun":"%s","reason":"free RAM below 3.4GiB twice (5s apart); our cell yields","free_KiB":%s,"at":"%s","provider_outcome_unknown":true}\n' "$c" "$arm" "$rr" "$(avail)" "$(date -Is)" > $A/yield-$arm-$c${rr:+-rerun}.json
      log "yield-stop $c $arm $rr $(date '+%H:%M:%S') free_KiB $(avail)"; break
    fi
    sleep 5
  done
  wait $pid 2>/dev/null; log "exit $? $(date +%H:%M:%S)"
}
others() {  # processes of another experiment folder (cwd under 06_TOOLS/EXPERIMENTS/adr_*, not ours)
  for p in $(pgrep -f "live.py|start_now.sh|run_all.sh|batch.py|rerun.py"); do
    d=$(readlink /proc/$p/cwd 2>/dev/null) || continue
    case $d in */EXPERIMENTS/adr_1531) ;; */EXPERIMENTS/adr_*) echo $p;; esac
  done
}
quiet=0; waited=0
while [ $quiet -lt 120 ] && [ $waited -lt 7200 ]; do
  if [ -z "$(others)" ]; then quiet=$((quiet+15)); else quiet=0; fi
  sleep 15; waited=$((waited+15))
done
if [ $quiet -lt 120 ]; then log "not started: another experiment still running after 2 hours $(date '+%F %T')"; exit 0; fi
log "other experiments quiet for 2 minutes after ${waited}s $(date '+%T')"
log "now start $(date '+%F %T') pid $$"
for arm in baseline candidate; do
  for c in cmp-riskcommittee cmp-liquidity; do
    $PY live.py $c $arm --preflight > $A/log-preflight-$arm-$c.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-$arm-$c.txt \
      || { log "preflight failed $arm $c $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
  done
done
for c in cmp-liquidity cmp-soundness cmp-riskcommittee; do
  cell $c baseline
  cell $c candidate
done
for c in cmp-liquidity cmp-soundness cmp-riskcommittee; do
  for arm in baseline candidate; do
    if [ -f $A/live/$arm/$c/STOP_EXTERNAL.json ] || [ -f $A/yield-$arm-$c.json ] || [ ! -f $A/live/$arm/$c/turn-1/result.json ]; then cell $c $arm --rerun; fi
  done
done
log "STOP: $([ -f $A/STOP_ALL.json ] && echo 'operator stop file' || echo none)"
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $?"
log ALL_DONE
echo "run_all exit 0 $(date '+%F %T') (now done)" >> $A/start.log
