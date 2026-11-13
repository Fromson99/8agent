#!/bin/bash
# ADR-1519 (r7: 외규 회수 + 80 model calls / 1800 s per request). Runs after other sessions' experiments: before the first cell
# it waits until no live.py/batch.py/run_all.sh/rerun.py/start_now.sh of another 06_TOOLS/EXPERIMENTS/adr_* folder has
# run for 2 minutes (user rule: real-model cells alone; 3 hours wait at most, then it does not start). Same admission/
# yield rule as ADR-1515: a cell starts only with >=5GiB free and yields below 3.4GiB twice 5 s apart. Frozen order:
# cmp-liquidity, cmp-soundness, cmp-riskcommittee; then one rerun of a cell whose every fallback provider failed
# (STOP_EXTERNAL), a yield or no result; then collect.py. Physical calls capped at 320 in total (a cell starts only
# while at most 320-100 are used).
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
print(sum(len(read(p)) for p in (ART/'live/candidate').glob('*/calls.json')))" 2>/dev/null || echo 0; }
cell() {  # case [--rerun]
  local c=$1 waited=0
  [ -f $A/STOP_ALL.json ] && return 1
  local n=$(calls_so_far); if [ $n -gt $((320-100)) ]; then log "$c ${2:-} skipped: $n physical calls already (limit 320)"; return 0; fi
  while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  if [ $(avail) -lt $((5*GIB)) ]; then log "=== $c candidate ${2:-} not started: free RAM below 5GiB for 30 minutes $(date '+%T')"; return 0; fi
  log "=== $c candidate ${2:-} $(date '+%H:%M:%S') waited $waited free_KiB $(avail)"
  $PY live.py $c candidate ${2:-} > $A/log-candidate-$c${2:+-rerun}.txt 2>&1 &
  local pid=$! low=0
  while kill -0 $pid 2>/dev/null; do
    if [ $(avail) -lt $((34*GIB/10)) ]; then low=$((low+1)); else low=0; fi
    if [ $low -ge 2 ]; then
      kill $pid; sleep 2; kill -9 $pid 2>/dev/null
      printf '{"case":"%s","rerun":"%s","reason":"free RAM below 3.4GiB twice (5s apart); our cell yields","free_KiB":%s,"at":"%s","provider_outcome_unknown":true}\n' "$c" "${2:-}" "$(avail)" "$(date -Is)" > $A/yield-$c${2:+-rerun}.json
      log "yield-stop $c ${2:-} $(date '+%H:%M:%S') free_KiB $(avail)"; break
    fi
    sleep 5
  done
  wait $pid 2>/dev/null; log "exit $? $(date +%H:%M:%S)"
}
others() {  # processes of another experiment folder (cwd under 06_TOOLS/EXPERIMENTS/adr_*, not ours)
  for p in $(pgrep -f "live.py|start_now.sh|run_all.sh|batch.py|rerun.py"); do
    d=$(readlink /proc/$p/cwd 2>/dev/null) || continue
    case $d in */EXPERIMENTS/adr_1519) ;; */EXPERIMENTS/adr_*) echo $p;; esac
  done
}
quiet=0; waited=0
while [ $quiet -lt 120 ] && [ $waited -lt 10800 ]; do
  if [ -z "$(others)" ]; then quiet=$((quiet+15)); else quiet=0; fi
  sleep 15; waited=$((waited+15))
done
if [ $quiet -lt 120 ]; then log "not started: another experiment still running after 3 hours $(date '+%F %T')"; exit 0; fi
log "other experiments quiet for 2 minutes after ${waited}s $(date '+%T')"
log "now start $(date '+%F %T') pid $$"
$PY live.py cmp-riskcommittee candidate --preflight > $A/log-preflight-cmp-riskcommittee.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-cmp-riskcommittee.txt \
  || { log "preflight failed cmp-riskcommittee $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
$PY live.py cmp-liquidity candidate --preflight > $A/log-preflight-cmp-liquidity.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-cmp-liquidity.txt \
  || { log "preflight failed cmp-liquidity $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
cell cmp-liquidity
cell cmp-soundness
cell cmp-riskcommittee
for c in cmp-liquidity cmp-soundness cmp-riskcommittee; do
  if [ -f $A/live/candidate/$c/STOP_EXTERNAL.json ] || [ -f $A/yield-$c.json ] || [ ! -f $A/live/candidate/$c/turn-1/result.json ]; then cell $c --rerun; fi
done
log "STOP: $([ -f $A/STOP_ALL.json ] && echo 'operator stop file' || echo none)"
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $?"
log ALL_DONE
echo "run_all exit 0 $(date '+%F %T') (now done)" >> $A/start.log
