#!/bin/bash
# ADR-1511 continuation after the split start (deviation-split-start-2.json): the light cell could not finish beside
# ADR-1509's two workers (free RAM ~3.4GiB, our cell yielded after 18 calls). Everything left now waits until no
# other experiment driver/batch/live/rerun process ran for 10 minutes, then runs in the frozen order:
# cmp-liquidity --rerun (its first run yielded), cmp-soundness, cmp-riskcommittee; then one rerun of soundness or
# riskcommittee if their run had a provider failure or no result; then collect.py. Physical calls capped at 200.
set -u
cd "$(dirname "$0")"
PY=/home/jin/8-AGENT/.venv/bin/python
A=$($PY -c "from common import ART;print(ART)")
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libeatmydata.so
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
run() {  # case [--rerun]
  [ -f $A/STOP_ALL.json ] && return 1
  local n=$(calls_so_far); if [ $n -gt $((200-64)) ]; then log "$1 ${2:-} skipped: $n physical calls already (limit 200)"; return 0; fi
  log "=== $1 candidate ${2:-} $(date '+%H:%M:%S') free_KiB $(awk '/MemAvailable/{print $2}' /proc/meminfo)"
  $PY live.py $1 candidate ${2:-} > $A/log-candidate-$1${2:+-rerun}.txt 2>&1
  log "exit $? $(date +%H:%M:%S)"
}
log "rest start $(date '+%F %T') pid $$ (waits for no other experiment for 10 minutes)"
quiet=0; last=""
while [ $quiet -lt 600 ]; do
  [ -f $A/STOP_ALL.json ] && { log "operator stop $(date '+%F %T')"; exit 0; }
  busy=$(others)
  if [ -n "$busy" ]; then quiet=0; [ "$busy" != "$last" ] && echo "waiting $(date '+%F %T') other experiment pids: $busy" >> $A/start.log; last=$busy
  else quiet=$((quiet+30)); fi
  sleep 30
done
log "no other experiment for 10 minutes $(date '+%F %T')"
$PY live.py cmp-riskcommittee candidate --preflight > $A/log-preflight-cmp-riskcommittee.txt 2>&1 && grep -q PREFLIGHT_READY $A/log-preflight-cmp-riskcommittee.txt \
  || { log "preflight failed cmp-riskcommittee $(date '+%F %T')"; echo "preflight failed" >> $A/start.log; exit 1; }
run cmp-liquidity --rerun
run cmp-soundness
run cmp-riskcommittee
for c in cmp-soundness cmp-riskcommittee; do
  if [ -f $A/live/candidate/$c/STOP_EXTERNAL.json ] || [ ! -f $A/live/candidate/$c/turn-1/result.json ]; then run $c --rerun; fi
done
log "STOP: $([ -f $A/STOP_ALL.json ] && echo 'operator stop file' || echo none)"
$PY collect.py > $A/collect.stdout 2>&1; log "collect exit $?"
log ALL_DONE
echo "run_all exit 0 $(date '+%F %T') (rest done)" >> $A/start.log
