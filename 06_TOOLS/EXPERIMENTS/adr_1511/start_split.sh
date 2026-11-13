#!/bin/bash
# ADR-1511 split start (user 2026-11-12 15:4x: "R4실험 바로 같이 할수 없나"), replaces start.sh after freeze; recorded in
# artifacts/deviation-split-start.json. The other session's ADR-1509 (2 workers, ~2.9GB each) stops a cell when free RAM
# falls below 3GiB (5GiB at its start). So:
#  1) light cells now (cmp-liquidity, cmp-soundness; peak RSS 1.3/1.5GB in ADR-1510): start only with >=5GiB free; while
#     the cell runs, if free RAM falls below 3.4GiB this script stops OUR cell (ours yields before theirs reach 3GiB).
#  2) cmp-riskcommittee (peak 3.5GB) waits until no other experiment driver/batch/live/rerun process ran for 10 minutes.
#  3) one rerun of a cell with a provider failure (STOP_EXTERNAL) or a yield stop, also after the others are done.
#  4) collect.py. Physical calls are capped at 200 in total (frozen limit).
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
GIB=1048576  # KiB
avail() { awk '/MemAvailable/{print $2}' /proc/meminfo; }
log() { echo "$*" >> $A/driver.log; }
others() {
  for pid in $(pgrep -f 'run_all.sh|batch.py|live.py|rerun.py'); do
    cwd=$(readlink /proc/$pid/cwd 2>/dev/null); cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    case "$cwd $cmd" in *adr_1511*) continue;; esac
    case "$cwd $cmd" in *06_TOOLS/EXPERIMENTS/adr_*) echo -n "$pid ";; esac
  done
}
calls_so_far() { $PY -c "
from common import *
print(sum(len(read(p)) for p in (ART/'live/candidate').glob('*/calls.json')))" 2>/dev/null || echo 0; }
wait_quiet() {
  local quiet=0 last=""
  while [ $quiet -lt 600 ]; do
    [ -f $A/STOP_ALL.json ] && return 1
    local busy=$(others)
    if [ -n "$busy" ]; then quiet=0; [ "$busy" != "$last" ] && log "waiting $(date '+%F %T') other experiment pids: $busy"; last=$busy
    else quiet=$((quiet+30)); fi
    sleep 30
  done
  log "no other experiment for 10 minutes $(date '+%F %T')"
}
light_cell() {  # case [--rerun] ; admission >=5GiB free, yield below 3.4GiB
  local c=$1 waited=0
  while [ $(avail) -lt $((5*GIB)) ] && [ $waited -lt 1800 ]; do sleep 15; waited=$((waited+15)); done
  if [ $(avail) -lt $((5*GIB)) ]; then log "=== $c candidate ${2:-} not started: free RAM below 5GiB for 30 minutes $(date '+%T')"; return; fi
  log "=== $c candidate ${2:-} $(date '+%H:%M:%S') waited $waited free_KiB $(avail) (light, beside other experiments)"
  $PY live.py $c candidate ${2:-} > $A/log-candidate-$c${2:+-rerun}.txt 2>&1 &
  local pid=$! low=0
  while kill -0 $pid 2>/dev/null; do
    if [ $(avail) -lt $((34*GIB/10)) ]; then low=$((low+1)); else low=0; fi
    if [ $low -ge 2 ]; then
      kill $pid; sleep 2; kill -9 $pid 2>/dev/null
      printf '{"case":"%s","rerun":"%s","reason":"free RAM below 3.4GiB twice (5s apart) while other experiments ran; our cell yields","free_KiB":%s,"at":"%s","provider_outcome_unknown":true}\n' "$c" "${2:-}" "$(avail)" "$(date -Is)" > $A/yield-$c${2:+-rerun}.json
      log "yield-stop $c ${2:-} $(date '+%H:%M:%S') free_KiB $(avail)"; break
    fi
    sleep 5
  done
  wait $pid 2>/dev/null; log "exit $? $(date +%H:%M:%S)"
}
heavy_cell() {  # case [--rerun] ; only when no other experiment runs
  wait_quiet || { log "operator stop $(date '+%F %T')"; return 1; }
  log "=== $1 candidate ${2:-} $(date '+%H:%M:%S') waited quiet free_KiB $(avail)"
  $PY live.py $1 candidate ${2:-} > $A/log-candidate-$1${2:+-rerun}.txt 2>&1
  log "exit $? $(date +%H:%M:%S)"
}
log "split start $(date '+%F %T') pid $$"
$PY live.py cmp-liquidity candidate --preflight > $A/log-preflight-cmp-liquidity.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-cmp-liquidity.txt \
  || { log "preflight failed cmp-liquidity $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
for c in cmp-liquidity cmp-soundness; do [ -f $A/STOP_ALL.json ] || light_cell $c; done
if [ ! -f $A/STOP_ALL.json ] && wait_quiet; then
  $PY live.py cmp-riskcommittee candidate --preflight > $A/log-preflight-cmp-riskcommittee.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-cmp-riskcommittee.txt \
    || { log "preflight failed cmp-riskcommittee $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
  log "=== cmp-riskcommittee candidate  $(date '+%H:%M:%S') waited quiet free_KiB $(avail)"
  $PY live.py cmp-riskcommittee candidate > $A/log-candidate-cmp-riskcommittee.txt 2>&1
  log "exit $? $(date +%H:%M:%S)"
  # One rerun of a cell with a provider failure or a yield stop, now with no other experiment running.
  for c in cmp-liquidity cmp-soundness cmp-riskcommittee; do
    [ -f $A/STOP_ALL.json ] && break
    if [ -f $A/live/candidate/$c/STOP_EXTERNAL.json ] || [ -f $A/yield-$c.json ] || [ ! -f $A/live/candidate/$c/turn-1/result.json ]; then
      n=$(calls_so_far); if [ $n -gt $((200-64)) ]; then log "rerun $c skipped: $n physical calls already (limit 200)"; continue; fi
      log "=== $c candidate --rerun $(date '+%H:%M:%S') free_KiB $(avail)"
      $PY live.py $c candidate --rerun > $A/log-candidate-$c-rerun.txt 2>&1
      log "exit $? $(date +%H:%M:%S)"
    fi
  done
fi
log "STOP: $([ -f $A/STOP_ALL.json ] && echo 'operator stop file' || echo none)"
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $?"
log ALL_DONE
echo "run_all exit 0 $(date '+%F %T') (split start done)" >> $A/start.log
