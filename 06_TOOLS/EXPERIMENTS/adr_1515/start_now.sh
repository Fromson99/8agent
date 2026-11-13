#!/bin/bash
# ADR-1515 run beside ADR-1509's single lane (pre-registered; same admission/yield rule as ADR-1511 start_now.sh).
# ADR-1509 now runs one request at a time (~2.9GB); its cell stops below 3GiB free (5GiB at its start; its lane waits for
# 4.5GiB before starting a request). Every cell here starts only with >=5GiB free (30 minutes wait at most) and yields
# (our process stopped) when free RAM is below 3.4GiB twice 5 s apart. Frozen order: cmp-liquidity, cmp-soundness,
# cmp-riskcommittee; then one rerun of a cell whose every fallback provider failed (STOP_EXTERNAL), a yield or no
# result; then collect.py. Physical calls capped at 200 in total.
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
  local n=$(calls_so_far); if [ $n -gt $((200-64)) ]; then log "$c ${2:-} skipped: $n physical calls already (limit 200)"; return 0; fi
  while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  if [ $(avail) -lt $((5*GIB)) ]; then log "=== $c candidate ${2:-} not started: free RAM below 5GiB for 30 minutes $(date '+%T')"; return 0; fi
  log "=== $c candidate ${2:-} $(date '+%H:%M:%S') waited $waited free_KiB $(avail) (beside ADR-1509 single lane)"
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
